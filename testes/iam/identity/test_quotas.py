"""D24 — trava de **seats** (a quota que a IAM aplica) e a claim `quotas`.

O que estes testes protegem:

1. **O seat trava de verdade** — atingido o teto do plano, criar usuário vira
   402 com o corpo estruturado que a UI usa para oferecer upgrade.
2. **Reativar consome seat** — sem isso a trava seria contornável desativando
   alguém, criando o novo e reativando o antigo.
3. **Desativar libera seat** — é a saída sem checkout, e é o que faz a trava ser
   administrável em vez de só punitiva.
4. **A claim leva o que é aplicado, e só isso** — quota inerte no token convida
   alguém a aplicá-la sem contador do outro lado.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from identity.models import AssinaturaTenant, Modulo, Tenant, Usuario
from payment.planos import QUOTAS_APLICADAS
from payment.regras import quotas_efetivas
from identity.quotas import QuotaExcedida, checar_seats
from identity.tokens import claims_de_acesso
from payment.planos import PLANOS


class SeatsTestBase(TestCase):
    def setUp(self):
        # `free` = 1 seat: o menor teto possível é também o mais fácil de exercitar.
        self.tenant = Tenant.objects.create(nome="T", slug="t", plano="free")
        self.admin = Usuario.objects.create(
            username="adm", email="adm@teste.com", tenant=self.tenant, is_tenant_admin=True
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _criar(self, username):
        return self.client.post(
            "/usuarios/",
            {"username": username, "email": f"{username}@teste.com", "password": "senha-forte-123"},
            format="json",  # a IAM só aceita JSON — multipart devolve 415
        )


class TravaDeSeatsTests(SeatsTestBase):
    def test_seat_ocupado_bloqueia_a_criacao(self):
        """O `free` inclui 1 seat e o admin já o ocupa."""
        resposta = self._criar("segundo")
        self.assertEqual(resposta.status_code, 402)
        self.assertEqual(Usuario.objects.filter(tenant=self.tenant).count(), 1)

    def test_corpo_do_402_e_o_mesmo_contrato_do_backend(self):
        """O frontend trata UM contrato de quota; os dois serviços têm de falar
        a mesma língua. Os números precisam sair como números — o `APIException`
        do DRF os converteria em string se o corpo fosse pelo construtor."""
        corpo = self._criar("segundo").data
        self.assertEqual(corpo["code"], "quota_excedida")
        self.assertEqual(corpo["quota"], "seats")
        self.assertEqual(corpo["limite"], 1)
        self.assertEqual(corpo["uso"], 1)
        self.assertEqual(corpo["plano"], "free")
        self.assertIsInstance(corpo["limite"], int)

    def test_plano_maior_libera(self):
        self.tenant.plano = "essencial"  # 3 seats
        self.tenant.save(update_fields=["plano"])
        self.assertEqual(self._criar("segundo").status_code, 201)
        self.assertEqual(self._criar("terceiro").status_code, 201)
        self.assertEqual(self._criar("quarto").status_code, 402)

    def test_desativar_libera_o_seat(self):
        """A saída sem passar pelo checkout quando alguém sai da empresa — é o
        caso comum por trás de "preciso de mais um usuário"."""
        self.assertEqual(self._criar("segundo").status_code, 402)
        self.admin.is_active = False
        self.admin.save(update_fields=["is_active"])
        self.assertEqual(self._criar("segundo").status_code, 201)

    def test_reativar_consome_seat(self):
        """A porta dos fundos: desativar, criar o novo e reativar o antigo
        terminaria com mais ativos do que o contratado, sem nunca ver um 402."""
        antigo = Usuario.objects.create(
            username="antigo", email="antigo@teste.com", tenant=self.tenant, is_active=False
        )
        resposta = self.client.patch(
            f"/usuarios/{antigo.pk}/", {"is_active": True}, format="json"
        )
        self.assertEqual(resposta.status_code, 402)
        antigo.refresh_from_db()
        self.assertFalse(antigo.is_active)

    def test_edicao_que_nao_reativa_passa_no_teto(self):
        """Estar no teto não pode impedir de corrigir o cadastro de quem já existe."""
        resposta = self.client.patch(
            f"/usuarios/{self.admin.pk}/", {"first_name": "Ana"}, format="json"
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)

    def test_contrato_vence_o_plano(self):
        """`AssinaturaTenant.limites` é onde o "Sob Medida" grava o negociado."""
        modulo = Modulo.objects.create(codigo="rh", nome="RH")
        AssinaturaTenant.objects.create(tenant=self.tenant, modulo=modulo, limites={"seats": 5})
        self.assertEqual(self._criar("segundo").status_code, 201)

    def test_dono_da_plataforma_provisiona_acima_do_teto(self):
        """Caminho de resgate: suporte e migração não podem depender do plano."""
        dono = Usuario.objects.create(
            username="dono", email="dono@teste.com", is_superuser=True, is_staff=True
        )
        self.client.force_authenticate(dono)
        resposta = self.client.post(
            "/usuarios/",
            {"username": "extra", "email": "extra@teste.com",
             "password": "senha-forte-123", "tenant": str(self.tenant.id)},
            format="json",
        )
        self.assertEqual(resposta.status_code, 201, resposta.data)


class ChecarSeatsDiretoTests(SeatsTestBase):
    def test_sem_tenant_e_no_op(self):
        checar_seats(None)  # não levanta

    def test_ilimitado_nao_trava(self):
        self.tenant.plano = "sob_medida"  # seats = None
        self.assertIsNone(checar_seats(self.tenant))

    def test_levanta_402_no_teto(self):
        with self.assertRaises(QuotaExcedida) as ctx:
            checar_seats(self.tenant)
        self.assertEqual(ctx.exception.status_code, 402)


class ClaimDeQuotasTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="T", slug="t", plano="profissional")
        self.user = Usuario.objects.create(
            username="u", email="u@teste.com", tenant=self.tenant
        )

    def test_claim_traz_as_quotas_do_plano(self):
        quotas = claims_de_acesso(self.user)["quotas"]
        self.assertEqual(quotas["obras"], PLANOS["profissional"]["obras"])
        self.assertEqual(quotas["seats"], PLANOS["profissional"]["seats"])

    def test_claim_leva_so_o_que_e_aplicado(self):
        """Publicar quota inerte no token convida alguém a aplicá-la mais adiante
        sem que o contador exista — e engorda um claim que viaja em toda
        requisição. Quota nova entra aqui JUNTO com o medidor dela."""
        quotas = claims_de_acesso(self.user)["quotas"]
        self.assertEqual(set(quotas), set(QUOTAS_APLICADAS))
        self.assertNotIn("notas_fiscais_mes", quotas)
        self.assertNotIn("armazenamento_gb", quotas)

    def test_plano_desconhecido_cai_no_menor_sem_levantar(self):
        """Mesmo princípio do `plano_valido`: plano escrito errado no banco não
        pode derrubar a emissão de token nem, pior, liberar tudo."""
        self.tenant.plano = "plano-que-nao-existe"
        quotas = quotas_efetivas(self.tenant.plano)
        self.assertEqual(quotas["obras"], PLANOS["free"]["obras"])

    def test_contrato_tem_precedencia_sobre_o_plano(self):
        quotas = quotas_efetivas("free", {"obras": 99})
        self.assertEqual(quotas["obras"], 99)

    def test_contrato_com_lixo_cai_no_plano(self):
        """Um `limites` mal preenchido no provisionamento não pode virar quota:
        `"muitas"` não é teto, e tratá-lo como um abriria o plano inteiro."""
        quotas = quotas_efetivas("free", {"obras": "muitas"})
        self.assertEqual(quotas["obras"], PLANOS["free"]["obras"])
