"""
Trava de identidade da cobrança Asaas (regressão do boleto emitido no cliente
errado): NUNCA emitir para um cadastro cujo NOME + CPF/CNPJ não bata com o
cliente escolhido. Cobre `client.buscar_customer_por_cpf_cnpj`,
`services.validar_cliente_para_cobranca`/`garantir_customer_asaas` e o
endpoint síncrono `contas-a-receber/{id}/gerar-cobranca/`.
"""
from datetime import date
from unittest.mock import patch, MagicMock

from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from clientes.models import Cliente
from nucleo.models import Tenant, Usuario
from moduloerp.models import ContaReceber

from .client import AsaasClient
from . import services
from .services import (
    validar_cliente_para_cobranca,
    garantir_customer_asaas,
    analisar_divergencias_asaas,
    ClienteDivergenteNoGateway,
    ClienteSemDocumento,
    DIVERGENCIA_SEM_DOCUMENTO,
    DIVERGENCIA_NOME,
    _normalizar_nome,
)


class BuscarCustomerTests(SimpleTestCase):
    def test_documento_vazio_nao_lista_a_conta_inteira(self):
        """
        O bug original: `GET /customers?cpfCnpj=` fazia o Asaas devolver todos
        os customers e o código pegava o primeiro. Sem documento, retorna None
        e NÃO chama a API.
        """
        client = AsaasClient(base_url="https://x", api_key="k")
        with patch.object(client, "_request") as req:
            self.assertIsNone(client.buscar_customer_por_cpf_cnpj(""))
            self.assertIsNone(client.buscar_customer_por_cpf_cnpj(None))
            req.assert_not_called()

    def test_ignora_customer_com_documento_diferente(self):
        client = AsaasClient(base_url="https://x", api_key="k")
        with patch.object(client, "_request", return_value={"data": [{"id": "cus_x", "cpfCnpj": "99999999999"}]}):
            self.assertIsNone(client.buscar_customer_por_cpf_cnpj("11111111111"))

    def test_retorna_customer_com_documento_igual(self):
        client = AsaasClient(base_url="https://x", api_key="k")
        alvo = {"id": "cus_1", "cpfCnpj": "111.111.111-11", "name": "Fulano"}
        with patch.object(client, "_request", return_value={"data": [alvo]}):
            self.assertEqual(client.buscar_customer_por_cpf_cnpj("11111111111"), alvo)


class NormalizarNomeTests(SimpleTestCase):
    def test_tolerante_a_acento_caixa_espaco(self):
        self.assertEqual(_normalizar_nome("Edison Góes "), _normalizar_nome("EDISON  GOES"))

    def test_sensivel_ao_conteudo(self):
        self.assertNotEqual(_normalizar_nome("EEGM"), _normalizar_nome("Edison Goes"))


class ValidarClienteTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="emp-a", nome="Empresa A")
        cls.cliente = Cliente.objects.create(
            nome_completo="Edison Goes",
            cpf_cnpj="11111111111",
            email="edison@x.com",
            data_nascimento=date(1990, 1, 1),
            tenant=cls.tenant,
        )

    def test_bloqueia_quando_nome_diverge_do_gateway(self):
        existente = {"id": "cus_eegm", "cpfCnpj": "11111111111", "name": "EEGM"}
        with patch.object(AsaasClient, "buscar_customer_por_cpf_cnpj", return_value=existente):
            with self.assertRaises(ClienteDivergenteNoGateway) as ctx:
                validar_cliente_para_cobranca(self.cliente)
        self.assertEqual(ctx.exception.contexto["nome_gateway"], "EEGM")
        self.assertEqual(ctx.exception.contexto["nome_projeto"], "Edison Goes")

    def test_bloqueia_sem_documento_valido(self):
        self.cliente.cpf_cnpj = "123"  # nem CPF nem CNPJ
        with self.assertRaises(ClienteSemDocumento):
            validar_cliente_para_cobranca(self.cliente)

    def test_reusa_quando_nome_bate(self):
        existente = {"id": "cus_ed", "cpfCnpj": "11111111111", "name": "EDISON GOES"}
        with patch.object(AsaasClient, "buscar_customer_por_cpf_cnpj", return_value=existente):
            diag = validar_cliente_para_cobranca(self.cliente)
        self.assertEqual(diag, {"situacao": "reusar", "customer_id": "cus_ed", "nome_gateway": "EDISON GOES"})

    def test_garantir_nao_adota_cadastro_alheio_e_nao_grava_id(self):
        existente = {"id": "cus_eegm", "cpfCnpj": "11111111111", "name": "EEGM"}
        with patch.object(AsaasClient, "buscar_customer_por_cpf_cnpj", return_value=existente):
            with patch.object(AsaasClient, "criar_customer") as criar:
                with self.assertRaises(ClienteDivergenteNoGateway):
                    garantir_customer_asaas(self.cliente)
                criar.assert_not_called()
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.id_cliente_gateway)

    def test_garantir_cria_quando_nao_existe(self):
        with patch.object(AsaasClient, "buscar_customer_por_cpf_cnpj", return_value=None):
            with patch.object(AsaasClient, "criar_customer", return_value={"id": "cus_novo"}) as criar:
                customer_id = garantir_customer_asaas(self.cliente)
        self.assertEqual(customer_id, "cus_novo")
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.id_cliente_gateway, "cus_novo")
        criar.assert_called_once()


class AnalisarDivergenciasTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="emp-c", nome="Empresa C")
        cls.ok = Cliente.objects.create(nome_completo="Maria Souza", cpf_cnpj="22222222222",
                                        email="maria@x.com", data_nascimento=date(1990, 1, 1), tenant=cls.tenant)
        cls.diverge = Cliente.objects.create(nome_completo="Edison Goes", cpf_cnpj="11111111111",
                                             email="edison@x.com", data_nascimento=date(1990, 1, 1), tenant=cls.tenant)
        cls.sem_doc = Cliente.objects.create(nome_completo="Sem Documento", cpf_cnpj="123",
                                             email="s@x.com", data_nascimento=date(1990, 1, 1), tenant=cls.tenant)

    def _asaas(self):
        # Conta Asaas: Maria bate; o CPF do Edison está em nome de EEGM.
        return [
            {"id": "cus_maria", "cpfCnpj": "22222222222", "name": "MARIA SOUZA"},
            {"id": "cus_eegm", "cpfCnpj": "11111111111", "name": "EEGM"},
        ]

    def test_relatorio_classifica_cada_divergencia(self):
        with patch.object(AsaasClient, "iterar_todos_customers", return_value=iter(self._asaas())):
            rel = analisar_divergencias_asaas(Cliente.objects.filter(tenant=self.tenant))
        self.assertEqual(rel["total_clientes"], 3)
        por_id = {d["cliente_id"]: d for d in rel["divergencias"]}
        self.assertNotIn(self.ok.pk, por_id)  # Maria bate → sem divergência
        self.assertEqual(por_id[self.diverge.pk]["tipo"], DIVERGENCIA_NOME)
        self.assertEqual(por_id[self.diverge.pk]["nome_gateway"], "EEGM")
        self.assertEqual(por_id[self.sem_doc.pk]["tipo"], DIVERGENCIA_SEM_DOCUMENTO)

    def test_endpoint_divergencias_asaas(self):
        user = Usuario.objects.create(username="u_c", tenant=self.tenant)
        user.iam_permissions = ["cadastro.cliente.view"]  # action é GET em ClienteViewSet
        self.client.force_authenticate(user=user)
        with patch.object(AsaasClient, "iterar_todos_customers", return_value=iter(self._asaas())):
            resp = self.client.get("/api/clientes/divergencias-asaas/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total_divergencias"], 2)

    def _relatorio_como(self, permissoes):
        user = Usuario.objects.create(username=f"u_c_{'_'.join(permissoes)[:20]}", tenant=self.tenant)
        user.iam_permissions = permissoes
        self.client.force_authenticate(user=user)
        with patch.object(AsaasClient, "iterar_todos_customers", return_value=iter(self._asaas())):
            resp = self.client.get("/api/clientes/divergencias-asaas/")
        self.assertEqual(resp.status_code, 200)
        return {d["cliente_id"]: d for d in resp.data["divergencias"]}

    def test_endpoint_mascara_documento_sem_permissao_de_doc(self):
        """LGPD (D3): sem `cadastro.cliente_doc.view`, o relatório de divergências
        não vaza o CPF/CNPJ inteiro — devolve mascarado (2 últimos dígitos, como a 9.C)."""
        doc = self._relatorio_como(["cadastro.cliente.view"])[self.diverge.pk]["documento"]
        self.assertIn("••••", doc)
        self.assertNotEqual(doc, "11111111111")
        self.assertTrue(doc.endswith("11"))

    def test_endpoint_documento_visivel_com_permissao_de_doc(self):
        por_id = self._relatorio_como(["cadastro.cliente.view", "cadastro.cliente_doc.view"])
        self.assertEqual(por_id[self.diverge.pk]["documento"], "11111111111")


class GerarCobrancaEndpointTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="emp-b", nome="Empresa B")
        cls.user = Usuario.objects.create(username="fin_b", tenant=cls.tenant)
        cls.cliente = Cliente.objects.create(
            nome_completo="Edison Goes",
            cpf_cnpj="11111111111",
            email="edison@x.com",
            data_nascimento=date(1990, 1, 1),
            tenant=cls.tenant,
        )
        cls.conta = ContaReceber.objects.create(
            cliente=cls.cliente,
            descricao="Projeto",
            valor=1000,
            data_vencimento=date(2026, 8, 1),
            tenant=cls.tenant,
        )

    def _auth(self):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = ["erp.cobranca.emitir"]  # action gerar-cobranca
        self.client.force_authenticate(user=self.user)

    def test_endpoint_bloqueia_e_nao_enfileira_quando_diverge(self):
        self._auth()
        existente = {"id": "cus_eegm", "cpfCnpj": "11111111111", "name": "EEGM"}
        with patch.object(AsaasClient, "buscar_customer_por_cpf_cnpj", return_value=existente):
            with patch("moduloerp.views.criar_cobranca.delay") as delay:
                resp = self.client.post(
                    f"/api/erp/contas-a-receber/{self.conta.conta_receber_id}/gerar-cobranca/",
                    {}, format="json",
                )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "cliente_divergente_no_gateway")
        delay.assert_not_called()

    def test_endpoint_enfileira_quando_ok(self):
        self._auth()
        with patch.object(AsaasClient, "buscar_customer_por_cpf_cnpj", return_value=None):
            with patch("moduloerp.views.criar_cobranca.delay") as delay:
                resp = self.client.post(
                    f"/api/erp/contas-a-receber/{self.conta.conta_receber_id}/gerar-cobranca/",
                    {}, format="json",
                )
        self.assertEqual(resp.status_code, 202)
        delay.assert_called_once_with(self.conta.conta_receber_id)
