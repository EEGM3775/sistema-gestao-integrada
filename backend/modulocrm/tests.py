"""
Testes do CRM (achado L4 / Fase 11.2): conversão e scoring de lead agora são
in-process (portados do microsserviço funcoeslead), e a listagem de
interações não pode quebrar para usuário não-staff (o filtro antigo em
GenericFK levantava FieldError).
"""
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework.test import APITestCase

from nucleo.models import Tenant, Usuario
from .models import Account, Contact, Interaction, Lead, Opportunity


class CrmTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="emp-a", nome="Empresa A")
        cls.user = Usuario.objects.create(username="vendedor_a", tenant=cls.tenant)
        cls.outro = Usuario.objects.create(username="vendedor_b", tenant=cls.tenant)

    # Conjunto de um usuário comercial pleno (persona `comercial` = crm.*), para os
    # testes FUNCIONAIS do CRM — que não estão exercendo a camada de autorização.
    CRM_PERMS_FULL = [
        "crm.campanha.view", "crm.campanha.edit",
        "crm.lead.view", "crm.lead.create", "crm.lead.edit", "crm.lead.delete",
        "crm.conta.view", "crm.conta.edit",
        "crm.contato.view", "crm.contato.edit",
        "crm.oportunidade.view", "crm.oportunidade.create",
        "crm.oportunidade.edit", "crm.oportunidade.delete",
        "crm.oportunidade_produto.view", "crm.oportunidade_produto.edit",
        "crm.interacao.view", "crm.interacao.create",
    ]

    def autenticar(self, user):
        user.iam_modules = ["crm"]
        user.iam_permissions = list(self.CRM_PERMS_FULL)
        self.client.force_authenticate(user=user)


class ConvertLeadTests(CrmTestBase):
    def _novo_lead(self, **kwargs):
        dados = dict(
            first_name="Ana", last_name="Souza", email="ana@exemplo.com",
            phone="41999990000", company="Construtora Alfa", source="Indicação",
            status=Lead.StatusChoices.QUALIFICADO,
            assigned_to=self.user, tenant=self.tenant,
        )
        dados.update(kwargs)
        return Lead.objects.create(**dados)

    def test_convert_cria_account_contact_opportunity_e_marca_convertido(self):
        lead = self._novo_lead()
        self.autenticar(self.user)

        resp = self.client.post(f"/api/crm/leads/{lead.id}/convert/")

        self.assertEqual(resp.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual(lead.status, Lead.StatusChoices.CONVERTIDO)

        account = Account.objects.get(name="Construtora Alfa")
        contact = Contact.objects.get(account=account, email="ana@exemplo.com")
        opportunity = Opportunity.objects.get(account=account)
        self.assertEqual(opportunity.stage, Opportunity.StageChoices.PROPOSTA)
        for obj in (account, contact, opportunity):
            self.assertEqual(obj.tenant_id, self.tenant.id)

    def test_convert_exige_status_qualificado(self):
        lead = self._novo_lead(status=Lead.StatusChoices.NOVO, email="novo@exemplo.com")
        self.autenticar(self.user)

        resp = self.client.post(f"/api/crm/leads/{lead.id}/convert/")

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Opportunity.objects.count(), 0)

    def test_score_aplica_regras_de_pontuacao(self):
        lead = self._novo_lead(email="score@exemplo.com")  # indicação(30) + empresa(20) + fone(10)
        self.autenticar(self.user)

        resp = self.client.post(f"/api/crm/leads/{lead.id}/score/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["score"], 60)


class InteractionListTests(CrmTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        agora = timezone.now()
        ct_usuario = ContentType.objects.get_for_model(Usuario)
        cls.minha = Interaction.objects.create(
            type=Interaction.TypeChoices.TAREFA, subject="Minha tarefa",
            due_date=agora, tenant=cls.tenant,
            assigned_to_content_type=ct_usuario, assigned_to_object_id=cls.user.pk,
        )
        lead_alheio = Lead.objects.create(
            first_name="Beto", last_name="Lima", email="beto@exemplo.com",
            assigned_to=cls.outro, tenant=cls.tenant,
        )
        Interaction.objects.create(
            type=Interaction.TypeChoices.REUNIAO, subject="Tarefa alheia",
            due_date=agora, lead=lead_alheio, tenant=cls.tenant,
        )

    def test_nao_staff_lista_so_o_que_e_seu_sem_500(self):
        self.autenticar(self.user)

        resp = self.client.get("/api/crm/interactions/")

        self.assertEqual(resp.status_code, 200)
        assuntos = {i["subject"] for i in resp.json()}
        self.assertEqual(assuntos, {"Minha tarefa"})

    def test_filtros_da_agenda_funcionam(self):
        self.autenticar(self.user)

        resp = self.client.get("/api/crm/interactions/", {"type": "REUNIAO"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])


class S5EntitlementCrmTests(CrmTestBase):
    """Achado S5: `OpportunityProductViewSet` só tinha `IsAuthenticated` — tenant
    sem o módulo `crm` acessava `/api/crm/opportunity-products/`. Corrigido com
    `RequireModule('crm')` + `RequirePermission` (camadas 1 e 2, Fase 9.B)."""

    URL = "/api/crm/opportunity-products/"

    def test_sem_o_modulo_crm_nega(self):
        self.user.iam_modules = []          # tenant não assina crm
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.client.get(self.URL).status_code, 403)

    def test_com_modulo_mas_sem_a_permissao_nega(self):
        # era das permissões: tem crm, mas não `crm.oportunidade_produto` → 403.
        self.user.iam_modules = ["crm"]
        self.user.iam_permissions = ["crm.lead.view"]
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.client.get(self.URL).status_code, 403)

    def test_com_permissao_concede(self):
        self.user.iam_modules = ["crm"]
        self.user.iam_permissions = ["crm.oportunidade_produto.view"]
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.client.get(self.URL).status_code, 200)

    def test_sem_permissao_nega_fail_closed(self):
        # Fatia E: token com o módulo mas sem `permissions` (conjunto vazio) → 403.
        # O fallback de papel (RequireRole) foi removido — nada mais passa sem a permissão.
        self.user.iam_modules = ["crm"]
        self.user.iam_permissions = []
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.client.get(self.URL).status_code, 403)
