"""D24 — trava de quota de objeto (camada 3) e o medidor que a antecede.

O que estes testes protegem, em ordem de importância:

1. **A trava vale** — atingido o teto do plano, a criação vira 402 com corpo
   estruturado (a UI depende dos campos, não da frase).
2. **A trava é do TENANT, não global** — duas empresas no mesmo servidor têm
   contadores independentes. É a regressão que importa num SaaS: um bug aqui
   faria o cliente pagante esbarrar no limite por causa do uso de outro.
3. **O que NÃO trava continua não travando** — edição, exclusão e os recursos de
   COGS. A regra de ouro do monetizacao.md §4 é fácil de violar por engano ao
   adicionar um recurso novo ao registro.
4. **Fail-open sem a claim** — token de serviço/legado não pode ficar sem
   escrever porque o paywall existe.
"""
from __future__ import annotations

from rest_framework.test import APITestCase

from clientes.models import Cliente
from fornecedores.models import Fornecedor
from nucleo.models import Tenant, Usuario
from nucleo.quotas import QuotaExcedida, checar_quota, uso_atual
from obras.models import Obra


def criar_cliente(tenant, n: int) -> Cliente:
    """Cliente direto no ORM, para montar estado sem passar pela API (e sem,
    portanto, esbarrar na quota que o teste ainda vai exercitar)."""
    return Cliente.objects.create(
        nome_completo=f"Cliente {n}",
        cpf_cnpj=f"{n:011d}",
        email=f"cliente{n}@exemplo.com",
        data_nascimento="1990-01-01",
        tenant=tenant,
    )


class QuotaTestBase(APITestCase):
    """Um tenant no plano `free` (1 empreendimento, 2 obras, 20 clientes)."""

    PERMS = [
        "cadastro.cliente.view", "cadastro.cliente.edit",
        "cadastro.fornecedor.view", "cadastro.fornecedor.edit",
        "obra.obra.view", "obra.obra.edit",
        "obra.empreendimento.view", "obra.empreendimento.edit",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="quota-a", nome="Construtora A")
        cls.user = Usuario.objects.create(username="admin_quota_a", tenant=cls.tenant)

    def autenticar(self, user=None, quotas=None, plano="free"):
        user = user or self.user
        user.iam_permissions = list(self.PERMS)
        user.iam_modules = []
        user.iam_plano = plano
        # `object()` não serve de sentinela aqui: o código distingue "dict" de
        # "qualquer outra coisa", então o default precisa ser um dict de verdade.
        user.iam_quotas = {"clientes": 2, "obras": 2, "fornecedores": 2,
                           "empreendimentos": 1} if quotas is None else quotas
        self.client.force_authenticate(user=user)
        return user


def payload_cliente(n: int) -> dict:
    """Cliente válido e distinto. `cpf_cnpj` e `email` são únicos POR TENANT
    (Fase 8.3), então repetir um deles daria 400 de duplicata e mascararia o que
    estes testes medem — um 402 que nunca chegou a ser avaliado."""
    return {
        "nome_completo": f"Cliente {n}",
        "cpf_cnpj": f"{n:011d}",
        "email": f"cliente{n}@exemplo.com",
        "data_nascimento": "1990-01-01",
    }


class QuotaDeObjetoTests(QuotaTestBase):
    URL = "/api/clientes/"

    def _payload(self, n):
        return payload_cliente(n)

    def test_cria_ate_o_limite_e_o_proximo_leva_402(self):
        self.autenticar(quotas={"clientes": 2})
        for i in range(2):
            resposta = self.client.post(self.URL, self._payload(i))
            self.assertEqual(resposta.status_code, 201, resposta.data)

        estourado = self.client.post(self.URL, self._payload(3))
        self.assertEqual(estourado.status_code, 402)
        self.assertEqual(Cliente.objects.filter(tenant=self.tenant).count(), 2)

    def test_corpo_do_402_traz_o_que_a_ui_precisa(self):
        """A tela monta o CTA a partir destes campos. Se virar só `detail`, o
        frontend passa a interpretar string — que quebra na primeira reescrita
        da mensagem."""
        self.autenticar(quotas={"clientes": 0})
        corpo = self.client.post(self.URL, self._payload(1)).data
        self.assertEqual(corpo["code"], "quota_excedida")
        self.assertEqual(corpo["quota"], "clientes")
        self.assertEqual(corpo["limite"], 0)
        self.assertEqual(corpo["uso"], 0)
        self.assertEqual(corpo["plano"], "free")

    def test_quota_zero_bloqueia_desde_o_primeiro(self):
        """`0` é quota real ("não incluído no plano"), não ausência de quota —
        confundi-lo com `None` liberaria justamente o que o plano não vende."""
        self.autenticar(quotas={"clientes": 0})
        self.assertEqual(self.client.post(self.URL, self._payload(1)).status_code, 402)

    def test_ilimitado_nao_trava(self):
        self.autenticar(quotas={"clientes": None})
        self.assertEqual(self.client.post(self.URL, self._payload(1)).status_code, 201)

    def test_sem_a_claim_nao_trava_e_nao_quebra(self):
        """Token de serviço/legado. Fail-open é decisão registrada em
        `nucleo/quotas.py`: quem forja token tem a chave da plataforma e não
        precisa burlar quota; fail-closed viraria indisponibilidade de escrita."""
        self.autenticar(quotas="isto-nao-e-dict")
        self.assertEqual(self.client.post(self.URL, self._payload(1)).status_code, 201)


class QuotaPorTenantTests(QuotaTestBase):
    """O contador é por empresa. Um bug aqui faria o cliente pagante esbarrar no
    limite por causa do uso de OUTRA empresa no mesmo servidor — o mesmo tipo de
    vazamento que a Fase 8 fechou nos dados, agora no eixo comercial."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.tenant_b = Tenant.objects.create(slug="quota-b", nome="Construtora B")
        cls.user_b = Usuario.objects.create(username="admin_quota_b", tenant=cls.tenant_b)

    def test_uso_de_um_tenant_nao_conta_para_o_outro(self):
        self.autenticar(quotas={"clientes": 1})
        self.assertEqual(self.client.post("/api/clientes/", payload_cliente(1)).status_code, 201)
        # Tenant A no teto...
        self.assertEqual(self.client.post("/api/clientes/", payload_cliente(2)).status_code, 402)
        # ...e o B, com o mesmo plano, começa do zero — inclusive podendo usar o
        # MESMO documento, que é único por tenant desde a Fase 8.3.
        self.autenticar(self.user_b, quotas={"clientes": 1})
        self.assertEqual(self.client.post("/api/clientes/", payload_cliente(1)).status_code, 201)


class QuotaNaoTravaOQueNaoDeveTests(QuotaTestBase):
    def test_edicao_e_exclusao_passam_acima_do_teto(self):
        """Downgrade de plano não pode deixar os dados do cliente reféns: acima
        do teto ele ainda arruma a casa, só não cresce."""
        self.autenticar(quotas={"clientes": 10})
        criado = self.client.post("/api/clientes/", payload_cliente(1))
        self.assertEqual(criado.status_code, 201, criado.data)
        pk = criado.data["cliente_id"]

        self.autenticar(quotas={"clientes": 0})  # plano encolheu
        editar = self.client.patch(f"/api/clientes/{pk}/", {"nome_completo": "X2"})
        self.assertEqual(editar.status_code, 200, editar.data)
        self.assertEqual(self.client.delete(f"/api/clientes/{pk}/").status_code, 204)

    def test_recurso_de_cogs_nao_entra_no_registro(self):
        """Regra de ouro do monetizacao.md §4: limite de CUSTO mede e cobra, não
        trava. Este teste é a trava contra alguém adicionar `notas_fiscais_mes`
        ao registro por simetria e parar a emissão fiscal de um cliente."""
        from nucleo.quotas import RECURSOS_CONTADOS

        proibidos = {
            "notas_fiscais_mes", "cobrancas_mes", "analises_ia_mes",
            "processamentos_drone_mes", "armazenamento_gb",
        }
        self.assertEqual(proibidos & set(RECURSOS_CONTADOS), set())

    def test_lista_comercial_e_os_contadores_nao_divergem(self):
        """**A trava que protege o dono do software.**

        Quais quotas travam é decisão comercial e vive em `payment/planos.py` §4;
        qual tabela contar é engenharia e vive em `nucleo/quotas.py`. Se os dois
        se separarem, o defeito é SILENCIOSO nos dois sentidos — e caro:

        - quota na lista comercial sem contador → o cliente é barrado por um
          limite que ninguém sabe medir;
        - contador sem a quota na lista → o limite não morde, o cliente do `free`
          cadastra sem parar e nunca vê motivo para pagar. Receita vazando sem
          nada quebrar.

        Por isso a igualdade é exata, não inclusão: sobra de qualquer lado falha.
        """
        from payment.planos import QUOTAS_DE_OBJETO

        from nucleo.quotas import RECURSOS_CONTADOS

        self.assertEqual(
            set(QUOTAS_DE_OBJETO),
            set(RECURSOS_CONTADOS),
            "payment/planos.py §4 e nucleo/quotas.py divergiram — ver docstring",
        )

    def test_dono_da_plataforma_nao_tem_plano(self):
        plataforma = Usuario.objects.create(
            username="dono", tenant=self.tenant, is_superuser=True
        )
        self.autenticar(plataforma, quotas={"clientes": 0})
        self.assertEqual(self.client.post("/api/clientes/", payload_cliente(7)).status_code, 201)


class QuotaOutrosRecursosTests(QuotaTestBase):
    """Os outros três recursos travados usam o mesmo mixin, mas com modelos e
    permissões diferentes — um erro de fiação (recurso apontando para a tabela
    errada) só aparece exercitando cada um."""

    def test_obras_e_fornecedores_travam_no_proprio_contador(self):
        self.autenticar(quotas={"obras": 1, "fornecedores": 1})

        obra = {"nome_obra": "Obra 1", "endereco": "Rua A, 100"}
        self.assertEqual(self.client.post("/api/obras/", obra).status_code, 201)
        self.assertEqual(
            self.client.post("/api/obras/", {**obra, "nome_obra": "Obra 2"}).status_code, 402
        )
        # Fornecedor tem contador próprio: a obra no teto não o afeta.
        self.assertEqual(
            self.client.post(
                "/api/fornecedores/",
                {"razao_social": "Forn 1", "cnpj": "11111111000100",
                 "email": "forn1@exemplo.com"},
            ).status_code,
            201,
        )
        self.assertEqual(Obra.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(Fornecedor.objects.filter(tenant=self.tenant).count(), 1)


class ContagemDiretaTests(QuotaTestBase):
    """`checar_quota`/`uso_atual` fora do ciclo HTTP — são o que um medidor ou um
    job de billing chamaria."""

    def test_uso_atual_conta_so_o_tenant_pedido(self):
        outro = Tenant.objects.create(slug="quota-c", nome="C")
        criar_cliente(self.tenant, 1)
        criar_cliente(outro, 2)
        self.assertEqual(uso_atual("clientes", self.tenant.id), 1)

    def test_checar_quota_levanta_com_o_contexto_do_erro(self):
        self.user.iam_quotas = {"clientes": 0}
        self.user.iam_plano = "free"
        with self.assertRaises(QuotaExcedida) as ctx:
            checar_quota(self.user, "clientes")
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertEqual(ctx.exception.detail["quota"], "clientes")


class PlanoEndpointTests(QuotaTestBase):
    URL = "/api/plano/"

    def test_medidor_traz_uso_limite_e_proximo_degrau(self):
        criar_cliente(self.tenant, 1)
        self.autenticar(quotas={"clientes": 20}, plano="free")

        corpo = self.client.get(self.URL).data
        self.assertEqual(corpo["plano"]["slug"], "free")
        self.assertEqual(corpo["proximo_plano"]["slug"], "essencial")

        clientes = next(q for q in corpo["quotas"] if q["recurso"] == "clientes")
        self.assertEqual((clientes["uso"], clientes["limite"], clientes["restante"]), (1, 20, 19))
        self.assertFalse(clientes["excedido"])

    def test_seats_aparece_sem_uso_por_ser_contado_na_iam(self):
        """O `Usuario` do backend é espelho JIT — contar seats aqui daria um
        número menor que o real. Melhor `null` declarado que plausível e errado."""
        self.autenticar(quotas={"seats": 1, "clientes": 20})
        seats = next(q for q in self.client.get(self.URL).data["quotas"]
                     if q["recurso"] == "seats")
        self.assertIsNone(seats["uso"])
        self.assertEqual(seats["fonte"], "iam")

    def test_acima_do_teto_nao_devolve_restante_negativo(self):
        for i in range(3):
            criar_cliente(self.tenant, i)
        self.autenticar(quotas={"clientes": 2})
        clientes = next(q for q in self.client.get(self.URL).data["quotas"]
                        if q["recurso"] == "clientes")
        self.assertEqual(clientes["restante"], 0)
        self.assertTrue(clientes["excedido"])

    def test_catalogo_vem_do_payment_para_a_ui_nao_repetir_preco(self):
        self.autenticar()
        catalogo = self.client.get(self.URL).data["catalogo"]
        self.assertEqual([p["slug"] for p in catalogo][0], "free")
        essencial = next(p for p in catalogo if p["slug"] == "essencial")
        self.assertEqual(essencial["preco_mensal"], 149)
        self.assertEqual(essencial["quotas"]["obras"], 8)
