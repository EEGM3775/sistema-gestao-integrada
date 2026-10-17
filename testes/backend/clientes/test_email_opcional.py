"""E-mail de cliente e fornecedor: opcional, único quando preenchido, e o
fornecedor aceita mais de um (itens 82 e 87 do dono)."""
from rest_framework.test import APITestCase

from fornecedores.models import Fornecedor
from nucleo.models import Tenant, Usuario
from nucleo.tenancy import rls_bypass

PERMISSOES = [
    "cadastro.fornecedor.view", "cadastro.fornecedor.edit",
    "cadastro.cliente.view", "cadastro.cliente.edit",
]


class EmailOpcionalTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        with rls_bypass():
            cls.tenant = Tenant.objects.create(slug="email-opc", nome="Email Opcional")
            cls.user = Usuario.objects.create(username="email_opc", tenant=cls.tenant)

    def setUp(self):
        self.user.iam_modules = ["erp_financeiro", "crm"]
        self.user.iam_permissions = list(PERMISSOES)
        self.client.force_authenticate(user=self.user)

    def _forn(self, nome, **extra):
        return self.client.post(
            "/api/fornecedores/", {"razao_social": nome, "cnpj": None, **extra}, format="json",
        )

    def test_fornecedor_sem_email_e_dois_sem_email_convivem(self):
        self.assertEqual(self._forn("A").status_code, 201)
        self.assertEqual(self._forn("B").status_code, 201)

    def test_email_repetido_diz_curto_e_no_campo(self):
        self.assertEqual(self._forn("A", email="a@x.com").status_code, 201)
        r = self._forn("B", email="a@x.com")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["email"], ["E-mail já cadastrado."])

    def test_email_adicional_nao_repete_o_de_outro_fornecedor(self):
        self._forn("A", email="a@x.com", emails_adicionais=["a2@x.com"])
        r = self._forn("B", email="b@x.com", emails_adicionais=["a2@x.com"])
        self.assertEqual(r.status_code, 400)
        self.assertIn("emails_adicionais", r.json())

    def test_email_repetido_dentro_do_mesmo_fornecedor(self):
        r = self._forn("A", email="a@x.com", emails_adicionais=["A@x.com"])
        self.assertEqual(r.status_code, 400)

    def test_editar_o_proprio_fornecedor_nao_conflita_consigo(self):
        r = self._forn("A", email="a@x.com", emails_adicionais=["a2@x.com"])
        pk = r.json()["fornecedor_id"]
        r = self.client.patch(f"/api/fornecedores/{pk}/", {"contato": "João"}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_cliente_sem_email_e_email_repetido(self):
        base = {"cpf_cnpj": "52998224725", "data_nascimento": "1980-01-01"}
        r = self.client.post("/api/clientes/", {**base, "nome_completo": "Um"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = self.client.post("/api/clientes/", {
            **base, "cpf_cnpj": "11144477735", "nome_completo": "Dois", "email": "c@x.com"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = self.client.post("/api/clientes/", {
            **base, "cpf_cnpj": "39053344705", "nome_completo": "Três", "email": "c@x.com"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["email"], ["E-mail já cadastrado."])
