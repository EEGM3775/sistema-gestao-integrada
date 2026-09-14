"""O nome da obra é único no empreendimento — e a recusa traz um nome pronto.

Decisão do dono, 13/09/2026: *"quando a pessoa tenta criar uma obra nova e o nome
já existe, avisa que o nome já existe e dá um aviso com a nova renomeação. Então
a regra ainda continua existindo e a pessoa, quando for selecionar a obra em
algum módulo, não tem que ficar adivinhando."*

O achado que motivou: o seed criou **duas** "Torre A — Fundações" no mesmo
empreendimento, e ninguém percebeu porque (a) o `ObraSerializer` não tinha
validador de unicidade — as duas `UniqueConstraint` são condicionais e incluem
`tenant`, e o DRF descarta ambas — e (b) o índice do banco estava corrompido e
deixava a duplicata entrar. Este arquivo cobre a metade que é código.
"""
from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from empreendimentos.models import Empreendimento
from nucleo.models import Tenant, Usuario

from .models import Obra
from .nomes import obra_em_conflito, sugerir_nome_livre


class BaseNomes(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="nomes", nome="Construtora Nomes")
        cls.empreendimento = Empreendimento.objects.create(
            tenant=cls.tenant, razao_social="Alphaville S/A", cnpj="11222333000181",
        )
        cls.outro = Empreendimento.objects.create(
            tenant=cls.tenant, razao_social="Beta Ltda", cnpj="11222333000262",
        )
        cls.usuario = Usuario.objects.create(
            username="cadastrador", tenant=cls.tenant, is_tenant_admin=True,
        )

    def setUp(self):
        self.obra = Obra.objects.create(
            tenant=self.tenant, empreendimento=self.empreendimento,
            nome_obra="Torre A — Fundações", endereco="Av. Principal, 100",
            data_inicio_prevista=date(2026, 4, 19),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.usuario)


class SugestaoTests(BaseNomes):
    def test_o_sufixo_e_o_mes_de_inicio_da_obra_nova(self):
        sugerido = sugerir_nome_livre(
            tenant_id=self.tenant.id, empreendimento_id=self.empreendimento.pk,
            nome="Torre A — Fundações", data_inicio=date(2026, 5, 23),
        )
        self.assertEqual(sugerido, "Torre A — Fundações (05/2026)")

    def test_duas_no_mesmo_mes_caem_para_o_numero(self):
        """A data parou de distinguir — e aí o número é o que sobra."""
        Obra.objects.create(
            tenant=self.tenant, empreendimento=self.empreendimento,
            nome_obra="Torre A — Fundações (05/2026)", endereco="x",
            data_inicio_prevista=date(2026, 5, 23),
        )
        sugerido = sugerir_nome_livre(
            tenant_id=self.tenant.id, empreendimento_id=self.empreendimento.pk,
            nome="Torre A — Fundações", data_inicio=date(2026, 5, 30),
        )
        self.assertEqual(sugerido, "Torre A — Fundações (05/2026) 2")

    def test_sem_data_prevista_usa_o_mes_corrente_em_vez_de_desistir(self):
        sugerido = sugerir_nome_livre(
            tenant_id=self.tenant.id, empreendimento_id=self.empreendimento.pk,
            nome="Torre A — Fundações", data_inicio=None,
        )
        self.assertRegex(sugerido, r"^Torre A — Fundações \(\d{2}/\d{4}\)$")

    def test_o_sufixo_nunca_e_cortado_pela_largura_do_campo(self):
        """Base truncada com sufixo inteiro ainda distingue; o contrário não cabe."""
        longo = "T" * 255
        Obra.objects.create(
            tenant=self.tenant, empreendimento=self.empreendimento,
            nome_obra=longo, endereco="x",
        )
        sugerido = sugerir_nome_livre(
            tenant_id=self.tenant.id, empreendimento_id=self.empreendimento.pk,
            nome=longo, data_inicio=date(2026, 5, 1),
        )
        self.assertLessEqual(len(sugerido), 255)
        self.assertTrue(sugerido.endswith(" (05/2026)"))


class EscopoTests(BaseNomes):
    def test_o_mesmo_nome_em_outro_empreendimento_e_livre(self):
        """A regra é por empreendimento, e sempre foi — não é global."""
        self.assertIsNone(obra_em_conflito(
            tenant_id=self.tenant.id, empreendimento_id=self.outro.pk,
            nome="Torre A — Fundações",
        ))

    def test_a_obra_nao_conflita_consigo_mesma(self):
        self.assertIsNone(obra_em_conflito(
            tenant_id=self.tenant.id, empreendimento_id=self.empreendimento.pk,
            nome="Torre A — Fundações", excluir_pk=self.obra.pk,
        ))

    def test_obra_na_lixeira_nao_segura_o_nome(self):
        """Integração com o D116: a lápide libera o nome na hora.

        Quem exclui e recadastra com o mesmo nome não deve receber sugestão
        nenhuma — não há conflito, porque a obra excluída saiu de circulação.
        """
        from nucleo.lixo import mover_para_lixo

        mover_para_lixo(self.obra, usuario=self.usuario)
        self.assertIsNone(obra_em_conflito(
            tenant_id=self.tenant.id, empreendimento_id=self.empreendimento.pk,
            nome="Torre A — Fundações",
        ))


class ApiTests(BaseNomes):
    def _payload(self, **extra):
        base = {
            "nome_obra": "Torre A — Fundações",
            "endereco": "Av. Principal, 100",
            "empreendimento": self.empreendimento.pk,
            "data_inicio_prevista": "2026-05-23",
        }
        base.update(extra)
        return base

    def test_nome_livre_cria_normalmente(self):
        resp = self.client.post(
            "/api/obras/", self._payload(nome_obra="Torre B — Alvenaria"), format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)

    def test_nome_repetido_e_400_com_conflito_e_sugestao(self):
        """Era 500 (`IntegrityError`) — quando o índice não estava corrompido."""
        resp = self.client.post("/api/obras/", self._payload(), format="json")

        self.assertEqual(resp.status_code, 400)
        self.assertIn("nome_obra", resp.data)
        self.assertEqual(resp.data["conflito"]["obra_id"], self.obra.pk)
        self.assertEqual(resp.data["conflito"]["nome_obra"], "Torre A — Fundações")
        self.assertEqual(resp.data["sugestao_nome"], "Torre A — Fundações (05/2026)")

    def test_a_sugestao_e_aceita_de_fato(self):
        """O nome que o servidor propõe tem de passar — senão é palpite inútil."""
        resp = self.client.post("/api/obras/", self._payload(), format="json")
        sugestao = resp.data["sugestao_nome"]

        criada = self.client.post(
            "/api/obras/", self._payload(nome_obra=sugestao), format="json",
        )
        self.assertEqual(criada.status_code, 201, criada.data)
        self.assertEqual(criada.data["nome_obra"], "Torre A — Fundações (05/2026)")

    def test_o_conflito_diz_quantas_atividades_a_obra_existente_tem(self):
        """É o número que separa a obra de verdade da casca abandonada."""
        resp = self.client.post("/api/obras/", self._payload(), format="json")
        self.assertEqual(resp.data["conflito"]["atividades"], 0)
        self.assertEqual(resp.data["conflito"]["etapas"], 0)

    def test_editar_a_propria_obra_sem_trocar_o_nome_passa(self):
        resp = self.client.patch(
            f"/api/obras/{self.obra.pk}/", {"endereco": "Rua Nova, 50"}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_renomear_uma_obra_para_o_nome_de_outra_e_recusado(self):
        outra = Obra.objects.create(
            tenant=self.tenant, empreendimento=self.empreendimento,
            nome_obra="Torre C — Acabamento", endereco="x",
            data_inicio_prevista=date(2026, 7, 1),
        )
        resp = self.client.patch(
            f"/api/obras/{outra.pk}/",
            {"nome_obra": "Torre A — Fundações"}, format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["sugestao_nome"], "Torre A — Fundações (07/2026)")
