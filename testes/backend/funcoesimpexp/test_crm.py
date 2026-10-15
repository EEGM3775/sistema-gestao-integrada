# testes/backend/funcoesimpexp/test_crm.py
"""O CRM entrando e saindo pelo motor (15/10/2026).

Mesma régua dos cadastros — importar só cria, e qualquer linha estranha trava
o lote — mais a do CRM: o arquivo vê o que a tela vê (quem não é staff exporta
só o que é seu) e o que entra fica com quem importou.
"""
from __future__ import annotations

from datetime import date

from django.test import TestCase
from rest_framework.test import APITestCase

from nucleo.models import Tenant, Usuario
from modulocrm.models import Account, Contact, Lead, Opportunity

from funcoesimpexp import importacao as motor
from funcoesimpexp.models import LinhaImportacao
from funcoesimpexp.registro import obter

NOVA = LinhaImportacao.Situacao.NOVA
INVALIDA = LinhaImportacao.Situacao.INVALIDA


def _csv(linhas: list[str]) -> bytes:
    return "\n".join(linhas).encode("utf-8")


class CrmImpexpBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="crm-imp", nome="Construtora CRM")
        cls.user = Usuario.objects.create(username="crm_op", tenant=cls.tenant)

    def recurso(self, recurso_id):
        recurso = obter(recurso_id)
        contexto = recurso.validar_contexto({}, self.user, self.tenant.id)
        return recurso.com_contexto({**contexto, "tenant_id": str(self.tenant.id)})

    def preparar(self, recurso_id, linhas):
        return motor.preparar(
            recurso=self.recurso(recurso_id), conteudo=_csv(linhas),
            nome_arquivo="crm.csv", tenant_id=self.tenant.id, usuario_nome="op",
        )

    def aplicar(self, recurso_id, lote):
        motor.aplicar(lote, recurso=obter(recurso_id).com_contexto(lote.contexto))

    def situacoes(self, lote):
        return [(l.situacao, l.motivo) for l in lote.linhas.order_by("numero")]

    def conta(self, nome="Souza Incorporações", **kw):
        return Account.objects.create(tenant=self.tenant, name=nome, assigned_to=self.user, **kw)


class LeadTests(CrmImpexpBase):
    CAB = "E-mail;Nome;Sobrenome;Status;Origem"

    def test_cria_com_status_pelo_rotulo_e_fica_com_quem_importou(self):
        lote = self.preparar("crm.lead", [self.CAB, "ana@x.com;Ana;Souza;Qualificado;Indicação"])
        self.assertEqual(self.situacoes(lote), [(NOVA, "")])
        self.aplicar("crm.lead", lote)
        lead = Lead.objects.get(tenant=self.tenant)
        self.assertEqual(lead.status, Lead.StatusChoices.QUALIFICADO)
        self.assertEqual(lead.assigned_to, self.user)

    def test_status_em_branco_e_novo(self):
        lote = self.preparar("crm.lead", [self.CAB, "bia@x.com;Bia;Lima;;"])
        self.aplicar("crm.lead", lote)
        self.assertEqual(Lead.objects.get(tenant=self.tenant).status, Lead.StatusChoices.NOVO)

    def test_email_ja_cadastrado_trava_mesmo_com_outra_caixa(self):
        Lead.objects.create(tenant=self.tenant, first_name="Ana", last_name="S", email="ana@x.com")
        lote = self.preparar("crm.lead", [self.CAB, "ANA@X.com;Ana;Souza;;"])
        with self.assertRaises(motor.ImportacaoInvalida):
            self.aplicar("crm.lead", lote)
        self.assertEqual(Lead.objects.filter(tenant=self.tenant).count(), 1)

    def test_email_malformado_e_invalido(self):
        lote = self.preparar("crm.lead", [self.CAB, "ana-sem-arroba;Ana;Souza;;"])
        self.assertEqual(self.situacoes(lote)[0][0], INVALIDA)


class ContaTests(CrmImpexpBase):
    def test_site_sem_esquema_ganha_https(self):
        lote = self.preparar("crm.conta", ["Conta (empresa);Site", "Alfa Ltda;www.alfa.com.br"])
        self.assertEqual(self.situacoes(lote), [(NOVA, "")])
        self.aplicar("crm.conta", lote)
        conta = Account.objects.get(tenant=self.tenant)
        self.assertEqual(conta.website, "https://www.alfa.com.br")
        self.assertEqual(conta.assigned_to, self.user)


class ContatoTests(CrmImpexpBase):
    CAB = "E-mail;Conta (empresa);Nome;Sobrenome"

    def test_conta_inexistente_trava(self):
        lote = self.preparar("crm.contato", [self.CAB, "c@x.com;Fantasma SA;Carlos;Souza"])
        situacao, motivo = self.situacoes(lote)[0]
        self.assertEqual(situacao, INVALIDA)
        self.assertIn("Fantasma SA", motivo)

    def test_mesmo_email_em_outra_conta_e_contato_novo(self):
        alfa, beta = self.conta("Alfa"), self.conta("Beta")
        Contact.objects.create(tenant=self.tenant, account=alfa, first_name="C", last_name="S",
                               email="c@x.com")
        lote = self.preparar("crm.contato", [self.CAB, "c@x.com;Beta;Carlos;Souza"])
        self.assertEqual(self.situacoes(lote), [(NOVA, "")])
        self.aplicar("crm.contato", lote)
        self.assertTrue(Contact.objects.filter(account=beta, email="c@x.com").exists())


class OportunidadeTests(CrmImpexpBase):
    CAB = "Oportunidade;Conta (empresa);E-mail do contato principal;Estágio;Probabilidade (%);Fechamento previsto"

    def test_cria_com_contato_da_conta_e_estagio_pelo_rotulo(self):
        conta = self.conta()
        contato = Contact.objects.create(tenant=self.tenant, account=conta, first_name="Carlos",
                                         last_name="Souza", email="carlos@souza.com")
        lote = self.preparar("crm.oportunidade", [
            self.CAB, "Torre B;Souza Incorporações;CARLOS@souza.com;Em Negociação;40;30/11/2026",
        ])
        self.assertEqual(self.situacoes(lote), [(NOVA, "")])
        self.aplicar("crm.oportunidade", lote)
        op = Opportunity.objects.get(tenant=self.tenant)
        self.assertEqual((op.contact, op.stage, op.probability, op.close_date),
                         (contato, "NEGOCIACAO", 40.0, date(2026, 11, 30)))
        self.assertEqual(op.assigned_to, self.user)

    def test_contato_de_outra_conta_trava(self):
        self.conta()
        outra = self.conta("Outra")
        Contact.objects.create(tenant=self.tenant, account=outra, first_name="X", last_name="Y",
                               email="x@y.com")
        lote = self.preparar("crm.oportunidade", [
            self.CAB, "Torre B;Souza Incorporações;x@y.com;;;30/11/2026",
        ])
        situacao, motivo = self.situacoes(lote)[0]
        self.assertEqual(situacao, INVALIDA)
        self.assertIn("x@y.com", motivo)

    def test_probabilidade_acima_de_100_e_sem_fechamento_travam(self):
        self.conta()
        lote = self.preparar("crm.oportunidade", [
            self.CAB,
            "Torre B;Souza Incorporações;;;150;30/11/2026",
            "Torre C;Souza Incorporações;;;;",
        ])
        self.assertEqual([s for s, _ in self.situacoes(lote)], [INVALIDA, INVALIDA])

    def test_mesmo_nome_na_mesma_conta_trava_e_desfazer_apaga(self):
        conta = self.conta()
        lote = self.preparar("crm.oportunidade", [self.CAB, "Torre B;Souza Incorporações;;;;30/11/2026"])
        self.aplicar("crm.oportunidade", lote)
        de_novo = self.preparar("crm.oportunidade", [self.CAB, "torre b;Souza Incorporações;;;;30/11/2026"])
        with self.assertRaises(motor.ImportacaoInvalida):
            self.aplicar("crm.oportunidade", de_novo)
        motor.desfazer(lote, recurso=obter("crm.oportunidade").com_contexto(lote.contexto))
        self.assertFalse(Opportunity.objects.filter(account=conta).exists())


# ---------------------------------------------------------------------------
# API — o arquivo vê o que a tela vê, e a busca da tela agora filtra
# ---------------------------------------------------------------------------

PERMS = (
    "crm.lead.view", "crm.lead.create", "crm.lead.edit",
    "crm.conta.view", "crm.conta.edit", "crm.contato.view", "crm.contato.edit",
)


class CrmApiTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="crm-api", nome="CRM API")
        self.user = Usuario.objects.create(username="vend_a", tenant=self.tenant)
        self.outro = Usuario.objects.create(username="vend_b", tenant=self.tenant)
        Lead.objects.create(tenant=self.tenant, first_name="Maria", last_name="Souza",
                            email="maria@x.com", assigned_to=self.user)
        Lead.objects.create(tenant=self.tenant, first_name="João", last_name="Lima",
                            email="joao@x.com", assigned_to=self.user)
        Lead.objects.create(tenant=self.tenant, first_name="Mário", last_name="Alheio",
                            email="mario@x.com", assigned_to=self.outro)
        self.user.iam_modules = ["crm"]
        self.user.iam_permissions = list(PERMS)
        self.user.iam_quotas = None
        self.client.force_authenticate(user=self.user)

    def _texto(self, resposta):
        corpo = b"".join(resposta.streaming_content if resposta.streaming else [resposta.content])
        return corpo.decode("utf-8-sig")

    def test_exporta_so_o_que_e_seu_e_o_que_a_busca_mostra(self):
        resposta = self.client.get("/api/impexp/crm.lead/exportar/", {"formato": "csv", "search": "mar"})
        self.assertEqual(resposta.status_code, 200, getattr(resposta, "data", ""))
        texto = self._texto(resposta)
        self.assertIn("maria@x.com", texto)
        self.assertNotIn("joao@x.com", texto)   # fora da busca
        self.assertNotIn("mario@x.com", texto)  # de outro vendedor

    def test_busca_da_tela_filtra_no_servidor(self):
        resposta = self.client.get("/api/crm/leads/", {"search": "souza"})
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        emails = {l["email"] for l in (dados["results"] if isinstance(dados, dict) else dados)}
        self.assertEqual(emails, {"maria@x.com"})

    def test_criar_contato_pela_tela_nao_quebra(self):
        conta = Account.objects.create(tenant=self.tenant, name="Alfa", assigned_to=self.user)
        resposta = self.client.post("/api/crm/contacts/", {
            "account_id": str(conta.pk), "first_name": "Carlos", "last_name": "Souza",
            "email": "carlos@alfa.com",
        }, format="json")
        self.assertEqual(resposta.status_code, 201, getattr(resposta, "data", ""))
        contato = Contact.objects.get(account=conta)
        resposta = self.client.patch(f"/api/crm/contacts/{contato.pk}/", {"title": "Diretor"},
                                     format="json")
        self.assertEqual(resposta.status_code, 200, getattr(resposta, "data", ""))
