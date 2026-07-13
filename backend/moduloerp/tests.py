"""
Testes da emissão de NF a partir de ContaReceber (achado L3): a NF herda o
tenant do título e o snapshot do cliente traz os campos reais (`cpf_cnpj`,
endereço completo com cidade/UF/CEP/IBGE) exigidos pelo funcoesnf.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import requests
from rest_framework.test import APITestCase

from clientes.models import Cliente
from nucleo.models import Tenant, Usuario
from nucleo.tenancy import rls_bypass
from .models import (
    ContaReceber, NotaFiscalServico, StatusNFE,
    StatusConta, StatusRevisaoBaixa, RevisaoBaixa, Transacao, CentroCusto,
    Boleto,
)


class EmitirNFSETests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="emp-a", nome="Empresa A")
        cls.user = Usuario.objects.create(username="fin_a", tenant=cls.tenant)
        cls.cliente = Cliente.objects.create(
            nome_completo="Cliente A",
            cpf_cnpj="11111111111",
            email="a@a.com",
            data_nascimento=date(1990, 1, 1),
            endereco="Rua das Obras",
            numero_endereco="10",
            bairro="Centro",
            cidade="Curitiba",
            estado="PR",
            cep="80000-000",
            cidade_ibge="4106902",
            tenant=cls.tenant,
        )
        cls.conta = ContaReceber.objects.create(
            cliente=cls.cliente,
            descricao="Serviço de engenharia",
            valor=1000,
            data_vencimento=date(2026, 8, 1),
            tenant=cls.tenant,
        )

    @patch("moduloerp.views.requests.post",
           side_effect=requests.exceptions.ConnectionError("microserviço de NF fora do ar"))
    def test_nfse_herda_tenant_e_snapshot_completo_do_cliente(self, _post):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = ["erp.nf.emitir"]  # verbo da action emitir-nfse
        self.client.force_authenticate(user=self.user)

        resp = self.client.post(
            f"/api/erp/contas-a-receber/{self.conta.conta_receber_id}/emitir-nfse/",
            {}, format="json",
        )

        self.assertEqual(resp.status_code, 201)
        nf = NotaFiscalServico.objects.get()
        self.assertEqual(nf.tenant_id, self.tenant.id)
        self.assertEqual(nf.borrower_data["cpf_cnpj"], self.cliente.cpf_cnpj)
        self.assertEqual(nf.borrower_data["nome_completo"], self.cliente.nome_completo)
        for campo in ("cidade", "estado", "cep", "cidade_ibge"):
            self.assertEqual(nf.borrower_data[campo], getattr(self.cliente, campo))


class S1TenantIsolationAPIViewTests(APITestCase):
    """
    Achado S1: `ERPDashboardView`, `AtualizarStatusNFView` e
    `ConsultarStatusNFView` eram `APIView` puras (fora do
    `TenantScopedViewSetMixin`) e liam/gravavam dados de qualquer tenant. Após a
    correção (`TenantScopedAPIViewMixin` + `scope_qs`), cada uma só enxerga o
    tenant do usuário.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(slug="s1-a", nome="Empresa A")
        cls.tenant_b = Tenant.objects.create(slug="s1-b", nome="Empresa B")
        cls.user_a = Usuario.objects.create(username="s1_fin_a", tenant=cls.tenant_a)

        cls.cli_a = Cliente.objects.create(
            nome_completo="Cliente A", cpf_cnpj="11111111111", email="a@a.com",
            data_nascimento=date(1990, 1, 1), tenant=cls.tenant_a,
        )
        cls.cli_b = Cliente.objects.create(
            nome_completo="Cliente B", cpf_cnpj="22222222222", email="b@b.com",
            data_nascimento=date(1990, 1, 1), tenant=cls.tenant_b,
        )
        # Um título em aberto em cada tenant (saldo = valor; status ABERTO por padrão).
        ContaReceber.objects.create(
            cliente=cls.cli_a, descricao="Receber A", valor=Decimal("1000"),
            data_vencimento=date(2026, 8, 1), tenant=cls.tenant_a,
        )
        ContaReceber.objects.create(
            cliente=cls.cli_b, descricao="Receber B", valor=Decimal("500"),
            data_vencimento=date(2026, 8, 1), tenant=cls.tenant_b,
        )
        # NF de serviço do tenant B — alvo do acesso cruzado.
        cls.nf_b = NotaFiscalServico.objects.create(
            tenant=cls.tenant_b, city_service_code="101", description="Serviço B",
            services_amount=Decimal("500"), borrower_data={"cpf_cnpj": "22222222222"},
        )

    def _auth_user_a(self):
        self.user_a.iam_modules = ["erp_financeiro"]
        # Teste de ISOLAMENTO (não de autorização): admin de tenant passa a camada 2
        # sem depender de permissão específica — o escopo por tenant (RLS + scope_qs)
        # segue valendo e é o que está sob prova. (As APIViews de NF exigiriam um
        # `erp.nf.edit` que nem existe no catálogo, só alcançável por admin.)
        self.user_a.is_tenant_admin = True
        self.client.force_authenticate(user=self.user_a)

    def test_dashboard_soma_apenas_o_proprio_tenant(self):
        # Antes da correção somava 1500 (A + B); agora só os 1000 do tenant A.
        self._auth_user_a()
        resp = self.client.get("/api/erp/dashboard/")
        self.assertEqual(resp.status_code, 200)
        total = sum(float(f["total"]) for f in resp.json()["agingContasAReceber"])
        self.assertEqual(total, 1000.0)

    def test_atualizar_status_nf_cross_tenant_da_404_e_nao_grava(self):
        self._auth_user_a()
        resp = self.client.post(
            "/api/erp/atualizar-status-nf/",
            {"nf_id": self.nf_b.id, "nf_tipo": "servico", "status": StatusNFE.EMITIDA},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        # A NF é do tenant B; sob a RLS fail-closed, o contexto do request (tenant
        # A) a esconde. Lemos sob bypass de plataforma só para provar que o write
        # foi bloqueado (status intacto).
        with rls_bypass():
            self.nf_b.refresh_from_db()
        self.assertEqual(self.nf_b.status, StatusNFE.AGUARDANDO)  # write bloqueado

    def test_consultar_status_nf_cross_tenant_da_404(self):
        self._auth_user_a()
        resp = self.client.post(f"/api/erp/nf/{self.nf_b.id}/consultar/")
        self.assertEqual(resp.status_code, 404)


class IntegridadeFinanceiraBaixaTests(APITestCase):
    """
    Pacote "integridade financeira sob concorrência" (L5–L7):
    - L5: a baixa roda sob `select_for_update()` numa transação (lock de linha).
    - L6: baixa em excesso do saldo vira RevisaoBaixa; edição de título não deixa
      saldo negativo nem quebra o rateio existente.
    - L7: a `Transacao` carrega a data real do pagamento (competência), não o
      instante de processamento.

    Tudo pela API (o `TenantScopedViewSetMixin` arma a RLS do request); as linhas
    de verificação em outras tabelas são lidas sob `rls_bypass()`.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="fin-l", nome="Empresa L")
        cls.user = Usuario.objects.create(username="fin_l", tenant=cls.tenant)
        cls.cliente = Cliente.objects.create(
            nome_completo="Cliente L", cpf_cnpj="33333333333", email="l@l.com",
            data_nascimento=date(1990, 1, 1), tenant=cls.tenant,
        )

    def setUp(self):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = [
            "erp.conta_receber.create", "erp.conta_receber.edit",
            "erp.conta_receber.baixar",
        ]
        self.client.force_authenticate(user=self.user)

    def _criar_conta(self, valor="1000", rateios=None):
        body = {
            "cliente": self.cliente.cliente_id,
            "descricao": "Receber L",
            "valor": valor,
            "data_vencimento": "2026-08-01",
        }
        if rateios is not None:
            body["rateios"] = rateios
        resp = self.client.post("/api/erp/contas-a-receber/", body, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        return resp.json()["conta_receber_id"]

    def _dar_baixa(self, conta_id, valor, data="2026-03-15"):
        return self.client.post(
            f"/api/erp/contas-a-receber/{conta_id}/dar-baixa/",
            {"valor": valor, "data": data}, format="json",
        )

    # --- L7 ---
    def test_transacao_usa_data_do_pagamento_como_competencia(self):
        conta_id = self._criar_conta("1000")
        resp = self._dar_baixa(conta_id, "1000", data="2026-03-15")
        self.assertEqual(resp.status_code, 200, resp.content)
        with rls_bypass():
            tx = Transacao.objects.get(conta_receber_id=conta_id)
        # Competência = data informada na baixa (mar/2026), não "hoje" (jul/2026).
        self.assertEqual(tx.data_transacao.date(), date(2026, 3, 15))
        self.assertIsNotNone(tx.data_lancamento)  # carimbo de sistema preservado

    # --- L6: baixa em excesso ---
    def test_baixa_maior_que_saldo_vira_revisao_e_nao_aplica(self):
        conta_id = self._criar_conta("1000")
        resp = self._dar_baixa(conta_id, "1500")  # excede o saldo de 1000
        self.assertEqual(resp.status_code, 202, resp.content)
        with rls_bypass():
            conta = ContaReceber.objects.get(pk=conta_id)
            revisao = RevisaoBaixa.objects.get(conta_receber_id=conta_id)
        self.assertEqual(conta.status, StatusConta.ABERTO)
        self.assertEqual(conta.valor_pago, Decimal("0"))
        self.assertEqual(revisao.status, StatusRevisaoBaixa.PENDENTE)
        # Nenhuma Transacao lançada para a baixa represada.
        with rls_bypass():
            self.assertFalse(Transacao.objects.filter(conta_receber_id=conta_id).exists())

    def test_baixa_parcial_dentro_do_saldo_aplica_normalmente(self):
        conta_id = self._criar_conta("1000")
        self.assertEqual(self._dar_baixa(conta_id, "400").status_code, 200)
        with rls_bypass():
            conta = ContaReceber.objects.get(pk=conta_id)
        self.assertEqual(conta.status, StatusConta.PARCIAL)
        self.assertEqual(conta.valor_pago, Decimal("400"))

    # --- L6: edição de título ---
    def test_patch_nao_reduz_valor_abaixo_do_ja_baixado(self):
        conta_id = self._criar_conta("1000")
        self.assertEqual(self._dar_baixa(conta_id, "400").status_code, 200)
        resp = self.client.patch(
            f"/api/erp/contas-a-receber/{conta_id}/", {"valor": "300"}, format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("valor", resp.json())

    def test_patch_valor_que_quebra_rateio_existente_e_rejeitado(self):
        with rls_bypass():
            cc1 = CentroCusto.objects.create(tenant=self.tenant, nome="CC1")
            cc2 = CentroCusto.objects.create(tenant=self.tenant, nome="CC2")
        conta_id = self._criar_conta("1000", rateios=[
            {"centro_custo": cc1.centro_custo_id, "valor": "600"},
            {"centro_custo": cc2.centro_custo_id, "valor": "400"},
        ])
        # Muda só o valor (sem reenviar rateios) → soma 1000 != 800.
        resp = self.client.patch(
            f"/api/erp/contas-a-receber/{conta_id}/", {"valor": "800"}, format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("valor", resp.json())

    # --- L5: consistência do read-modify-write sob lock ---
    def test_baixas_sequenciais_acumulam_sob_lock(self):
        conta_id = self._criar_conta("1000")
        self.assertEqual(self._dar_baixa(conta_id, "300").status_code, 200)
        self.assertEqual(self._dar_baixa(conta_id, "700").status_code, 200)
        with rls_bypass():
            conta = ContaReceber.objects.get(pk=conta_id)
            n_tx = Transacao.objects.filter(conta_receber_id=conta_id).count()
        self.assertEqual(conta.valor_pago, Decimal("1000"))
        self.assertEqual(conta.status, StatusConta.QUITADO)
        self.assertEqual(n_tx, 2)


class D3BaixaPropagaBoletoTests(APITestCase):
    """
    Achado D3: ao dar baixa manual numa conta a receber, o boleto vinculado
    continuava exibido como "Emitido" ("como se a mudança não tivesse sido
    aplicada"). Causa: só o handler do webhook Asaas marcava o boleto como PAGO;
    a baixa manual (mesmo choke point `dar_baixa`) não propagava. Correção:
    `ContaReceber.dar_baixa` marca os boletos vinculados como PAGO quando o título
    fica QUITADO. Prova a propagação pela API (o mixin arma a RLS do request).
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="fin-d3", nome="Empresa D3")
        cls.user = Usuario.objects.create(username="fin_d3", tenant=cls.tenant)
        cls.cliente = Cliente.objects.create(
            nome_completo="Cliente D3", cpf_cnpj="44444444444", email="d3@d3.com",
            data_nascimento=date(1990, 1, 1), tenant=cls.tenant,
        )

    def setUp(self):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = [
            "erp.conta_receber.create", "erp.conta_receber.edit",
            "erp.conta_receber.baixar",
        ]
        self.client.force_authenticate(user=self.user)

    def _criar_conta_com_boleto(self, valor="1000", status_boleto=Boleto.StatusBoleto.EMITIDO):
        resp = self.client.post("/api/erp/contas-a-receber/", {
            "cliente": self.cliente.cliente_id, "descricao": "Receber D3",
            "valor": valor, "data_vencimento": "2026-08-01",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        conta_id = resp.json()["conta_receber_id"]
        with rls_bypass():
            boleto = Boleto.objects.create(
                tenant=self.tenant, conta_receber_id=conta_id,
                status=status_boleto, valor=valor, data_vencimento="2026-08-01",
            )
        return conta_id, boleto.boleto_id

    def _dar_baixa(self, conta_id, valor, data="2026-03-15"):
        return self.client.post(
            f"/api/erp/contas-a-receber/{conta_id}/dar-baixa/",
            {"valor": valor, "data": data}, format="json",
        )

    def test_baixa_total_marca_boleto_como_pago(self):
        conta_id, boleto_id = self._criar_conta_com_boleto("1000")
        self.assertEqual(self._dar_baixa(conta_id, "1000", data="2026-03-15").status_code, 200)
        with rls_bypass():
            boleto = Boleto.objects.get(pk=boleto_id)
        self.assertEqual(boleto.status, Boleto.StatusBoleto.PAGO)
        # data_pagamento = data da baixa (competência), não o instante do processamento.
        self.assertIsNotNone(boleto.data_pagamento)
        self.assertEqual(boleto.data_pagamento.date(), date(2026, 3, 15))

    def test_baixa_parcial_mantem_boleto_emitido(self):
        conta_id, boleto_id = self._criar_conta_com_boleto("1000")
        self.assertEqual(self._dar_baixa(conta_id, "400").status_code, 200)
        with rls_bypass():
            boleto = Boleto.objects.get(pk=boleto_id)
        # Título só PARCIAL → boleto segue em aberto (não é quitação).
        self.assertEqual(boleto.status, Boleto.StatusBoleto.EMITIDO)
        self.assertIsNone(boleto.data_pagamento)

    def test_boleto_cancelado_nao_e_reaberto_para_pago(self):
        conta_id, boleto_id = self._criar_conta_com_boleto(
            "1000", status_boleto=Boleto.StatusBoleto.CANCELADO,
        )
        self.assertEqual(self._dar_baixa(conta_id, "1000").status_code, 200)
        with rls_bypass():
            boleto = Boleto.objects.get(pk=boleto_id)
        self.assertEqual(boleto.status, Boleto.StatusBoleto.CANCELADO)


class D3DashboardPermissionTests(APITestCase):
    """
    Achado D3 ("gráficos não carregam"): o hub `/api/erp/dashboard/` exige
    `erp.relatorio.view`. Personas com o módulo `erp_financeiro` mas sem essa
    permissão recebiam 403 → KPIs vazios + gráficos sem dados. Prova o gate:
    sem a permissão nega; com ela passa; admin de tenant faz bypass.
    (A concessão da permissão às personas de dinheiro — tesouraria/fiscal — é
    coberta no catálogo da IAM: `identity/tests.py`.)
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="dash-d3", nome="Empresa Dash")
        cls.user = Usuario.objects.create(username="dash_d3", tenant=cls.tenant)

    def _auth(self, *, permissions=None, admin=False):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = permissions or []
        self.user.is_tenant_admin = admin
        self.client.force_authenticate(user=self.user)

    def test_sem_relatorio_view_nega(self):
        self._auth(permissions=["erp.conta_receber.view"])  # tem o módulo, não o relatório
        self.assertEqual(self.client.get("/api/erp/dashboard/").status_code, 403)

    def test_com_relatorio_view_passa(self):
        self._auth(permissions=["erp.relatorio.view"])
        self.assertEqual(self.client.get("/api/erp/dashboard/").status_code, 200)

    def test_admin_de_tenant_faz_bypass(self):
        self._auth(admin=True)  # sem nenhuma permissão explícita
        self.assertEqual(self.client.get("/api/erp/dashboard/").status_code, 200)


class D7NfApiViewPermissionTests(APITestCase):
    """
    Achado D7: os APIViews de NF exigiam `erp.nf.edit`, permissão inexistente no
    catálogo → só admin passava. Correção: `erp.nf.edit` criado (persona `fiscal`
    o recebe via `erp.nf.*`); a consulta (leitura) passou a exigir `erp.nf.view`.
    Prova o gate por permissão sem depender do microserviço (o 400/200 mostra que
    a requisição passou da camada de autorização e chegou à lógica da view).
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="d7-nf", nome="Empresa NF")
        cls.user = Usuario.objects.create(username="fiscal_d7", tenant=cls.tenant)
        cls.nf = NotaFiscalServico.objects.create(
            tenant=cls.tenant, city_service_code="101", description="Serviço",
            services_amount=Decimal("500"), borrower_data={"cpf_cnpj": "11111111111"},
        )  # sem nfe_io_id de propósito → consulta para em 400 antes do microserviço

    def _auth(self, permissions):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = list(permissions)
        self.client.force_authenticate(user=self.user)

    def test_consultar_sem_view_nega(self):
        self._auth(["erp.nf.emitir"])  # tem emitir, mas não view
        resp = self.client.post(f"/api/erp/nf/{self.nf.id}/consultar/")
        self.assertEqual(resp.status_code, 403)

    def test_consultar_com_view_passa_do_gate(self):
        self._auth(["erp.nf.view"])
        resp = self.client.post(f"/api/erp/nf/{self.nf.id}/consultar/")
        # Passou a autorização; a NF não tem nfe_io_id → 400 (não 403).
        self.assertEqual(resp.status_code, 400)

    def test_atualizar_status_sem_edit_nega(self):
        self._auth(["erp.nf.view"])  # leitura não autoriza a escrita de status
        resp = self.client.post(
            "/api/erp/atualizar-status-nf/",
            {"nf_id": self.nf.id, "nf_tipo": "servico", "status": StatusNFE.EMITIDA},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_atualizar_status_com_edit_grava(self):
        self._auth(["erp.nf.edit"])
        resp = self.client.post(
            "/api/erp/atualizar-status-nf/",
            {"nf_id": self.nf.id, "nf_tipo": "servico", "status": StatusNFE.EMITIDA},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        with rls_bypass():
            self.nf.refresh_from_db()
        self.assertEqual(self.nf.status, StatusNFE.EMITIDA)
