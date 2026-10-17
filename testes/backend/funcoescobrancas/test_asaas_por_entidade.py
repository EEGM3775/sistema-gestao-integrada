"""D293 — com mais de uma entidade, o boleto sai na conta Asaas do dono do título.

A conta do ambiente é a da matriz. A SPE (ou qualquer outra entidade do grupo)
só emite pelo Asaas com a conta própria cadastrada; sem ela, a emissão é
recusada com o motivo — antes, saía com o CNPJ da matriz. O boleto guarda em
que conta nasceu, e cancelar e conferir vão à mesma.
"""
from datetime import date
from unittest.mock import patch

from rest_framework.test import APITestCase

from clientes.models import Cliente
from entidades.models import Entidade
from funcoescobrancas import services
from funcoescobrancas.client import AsaasClient
from moduloerp.models import Boleto, ContaReceber, IntegracaoAsaas
from nucleo.models import Tenant, Usuario
from nucleo.tenancy import rls_bypass, tenant_context


class AsaasPorEntidadeTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="d293", nome="Grupo D293")
        cls.matriz = Entidade.objects.create(
            tenant=cls.tenant, nome="Matriz SA", documento="11222333000181", papel=Entidade.Papel.MATRIZ,
        )
        cls.spe = Entidade.objects.create(
            tenant=cls.tenant, nome="SPE Alfa", documento="44555666000192", papel=Entidade.Papel.SPE,
        )
        cls.user = Usuario.objects.create(username="fin_d293", tenant=cls.tenant, is_tenant_admin=True)
        cls.cliente = Cliente.objects.create(
            nome_completo="Comprador", cpf_cnpj="11111111111", email="c@x.com",
            data_nascimento=date(1990, 1, 1), tenant=cls.tenant,
        )

    def _conta(self, entidade):
        with rls_bypass():
            return ContaReceber.objects.create(
                cliente=self.cliente, entidade=entidade, descricao="Parcela", valor=1000,
                data_vencimento=date(2026, 12, 1), tenant=self.tenant,
            )

    def _emitir(self, conta, chaves):
        """Emite com o gateway simulado; `chaves` recebe a chave de cada chamada."""
        def criar_payment(cliente_asaas, **kwargs):
            chaves.append(cliente_asaas.api_key)
            return {"id": f"pay_{len(chaves)}", "bankSlipUrl": "https://x/b.pdf"}

        with patch.object(AsaasClient, "buscar_customer_por_cpf_cnpj", return_value=None), \
             patch.object(AsaasClient, "criar_customer", return_value={"id": "cus_1"}), \
             patch.object(AsaasClient, "criar_payment", autospec=True, side_effect=criar_payment), \
             patch.object(AsaasClient, "buscar_linha_digitavel", return_value={}), \
             patch("funcoescobrancas.segunda_via.timezone.localdate", return_value=date(2026, 7, 1)), \
             tenant_context(self.tenant.pk):
            return services.gerar_cobranca_asaas(conta)

    def test_spe_sem_conta_propria_e_recusada(self):
        conta = self._conta(self.spe)
        with self.assertRaises(services.EntidadeSemContaAsaas) as erro:
            self._emitir(conta, [])
        self.assertIn("SPE Alfa", erro.exception.mensagem)
        self.assertFalse(Boleto.objects.filter(conta_receber=conta).exists())

    def test_matriz_segue_na_conta_do_ambiente(self):
        chaves = []
        with self.settings(ASAAS_API_KEY="chave-do-ambiente"):
            boleto = self._emitir(self._conta(self.matriz), chaves)
        self.assertEqual(chaves, ["chave-do-ambiente"])
        self.assertEqual(boleto.conta_asaas, services.CONTA_DO_AMBIENTE)

    def test_spe_com_conta_propria_emite_nela_e_cancela_nela(self):
        with rls_bypass():
            cadastro = IntegracaoAsaas(tenant=self.tenant, entidade=self.spe)
            cadastro.definir_api_key("chave-da-spe")
            cadastro.save()
        chaves = []
        boleto = self._emitir(self._conta(self.spe), chaves)
        self.assertEqual(chaves, ["chave-da-spe"])
        self.assertEqual(boleto.conta_asaas, services.CONTA_DA_ENTIDADE)
        # O vínculo do cadastro é o da conta da matriz: não é trocado.
        self.cliente.refresh_from_db()
        self.assertNotEqual(self.cliente.id_cliente_gateway, "cus_1")

        usadas = []

        def cancelar(cliente_asaas, gateway_id):
            usadas.append(cliente_asaas.api_key)
            return {"deleted": True}

        with patch.object(AsaasClient, "cancelar_payment", autospec=True, side_effect=cancelar), \
             tenant_context(self.tenant.pk):
            services.cancelar_cobranca_asaas(boleto)
        self.assertEqual(usadas, ["chave-da-spe"])

    def test_uma_entidade_so_usa_o_ambiente_como_sempre(self):
        tenant = Tenant.objects.create(slug="d293-simples", nome="Simples")
        unica = Entidade.objects.create(tenant=tenant, nome="Única", papel=Entidade.Papel.SPE)
        with tenant_context(tenant.pk):
            cliente, conta = services.conta_asaas_da_entidade(tenant.pk, unica)
        self.assertEqual(conta, services.CONTA_DO_AMBIENTE)

    def test_tela_recusa_antes_de_enfileirar(self):
        conta = self._conta(self.spe)
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = ["erp.cobranca.emitir"]
        self.client.force_authenticate(user=self.user)
        with patch("moduloerp.views.criar_cobranca.delay") as delay:
            resp = self.client.post(
                f"/api/erp/contas-a-receber/{conta.conta_receber_id}/gerar-cobranca/", {}, format="json",
            )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "entidade_sem_conta_asaas")
        delay.assert_not_called()

    def test_cadastro_da_conta_pela_tela_nao_devolve_a_chave(self):
        self.user.iam_modules = ["erp_financeiro"]
        self.client.force_authenticate(user=self.user)
        url = "/api/erp/configuracao/integracao-asaas/"
        antes = self.client.get(url, {"entidade": self.spe.pk}).json()
        self.assertEqual(antes["origem"], "nenhuma")
        self.assertFalse(antes["emite_pelo_asaas"])
        resp = self.client.put(url, {"entidade": self.spe.pk, "api_key": "$aact_abc123XYZ9"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        corpo = resp.json()
        self.assertEqual(corpo["origem"], "entidade")
        self.assertEqual(corpo["chave_final"], "XYZ9")
        self.assertNotIn("$aact_abc123XYZ9", resp.content.decode())
        with rls_bypass():
            self.assertEqual(IntegracaoAsaas.objects.get(entidade=self.spe).api_key, "$aact_abc123XYZ9")
        # Vazia tira a conta própria.
        self.client.put(url, {"entidade": self.spe.pk, "api_key": ""}, format="json")
        self.assertEqual(self.client.get(url, {"entidade": self.spe.pk}).json()["origem"], "nenhuma")
