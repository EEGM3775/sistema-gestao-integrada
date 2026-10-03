"""Revisão do dono dos itens 55, 57 e 58 (01/10/2026), e as notas em lote.

- 55: o boleto do Asaas nascia sem linha digitável (ela mora num endpoint à
  parte), e o feriado de 01/01/2030 passava porque a tabela parava em 2028.
- 57: editar valor ou vencimento de conta com boleto vivo deixava o boleto
  antigo valendo; agora a edição pede confirmação e emite a segunda via.
- 58: a nota ficava "Processando" para sempre — a NFE.io emite depois e o SGI
  não voltava a perguntar.
- Pedido novo: NFS-e em lote, junto do lote de boletos ou sozinha.
- Pedido novo: o limite do lote é do plano (paywall), e a empresa escolhe o dela
  abaixo dele — quem muda é o admin ou quem tem `erp.lote.configurar`.
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from funcoescobrancas.client import AsaasAPIError, AsaasClient
from modulocalendar.models import Feriado
from moduloerp.models import Boleto, NotaFiscalServico, StatusNFE
from nucleo.models import AuditLog
from nucleo.tenancy import rls_bypass, tenant_context

from .test_itens_51_58 import HOJE, _Base

LINHA = "46191110000000000000013431604019327740000210080"
BARRAS = "46193277400002100801110000000000001343160401"


def _asaas(**extra):
    """Os patches de uma emissão no Asaas que dá certo."""
    return [
        patch.object(AsaasClient, "buscar_customer_por_cpf_cnpj", return_value=None),
        patch.object(AsaasClient, "criar_customer", return_value={"id": "cus"}),
        patch.object(AsaasClient, "criar_payment", return_value={
            "id": "pay_novo", "bankSlipUrl": "https://sandbox.asaas.com/b/pdf/x", "nossoNumero": "13431604",
        }),
        patch.object(AsaasClient, "buscar_linha_digitavel", **(extra or {"return_value": {
            "identificationField": LINHA, "barCode": BARRAS, "nossoNumero": "13431604",
        }})),
    ]


class LinhaDigitavelDoAsaasTests(_Base):
    """55 — a linha digitável vem de `/payments/{id}/identificationField`."""

    def _emitir(self, conta, **extra):
        from funcoescobrancas import services
        patches = _asaas(**extra)
        for p in patches:
            p.start()
        try:
            with tenant_context(self.tenant.pk):
                return services.gerar_cobranca_asaas(conta)
        finally:
            for p in patches:
                p.stop()

    def test_emissao_traz_linha_digitavel_e_codigo_de_barras(self):
        boleto = self._emitir(self.conta())
        self.assertEqual(boleto.linha_digitavel, LINHA)
        self.assertEqual(boleto.codigo_barras, BARRAS)
        self.assertEqual(boleto.nosso_numero, "13431604")

    def test_falha_na_linha_nao_derruba_o_boleto(self):
        boleto = self._emitir(self.conta(), side_effect=AsaasAPIError("fora", status_code=503))
        self.assertEqual(boleto.status, Boleto.StatusBoleto.EMITIDO)
        self.assertEqual(boleto.linha_digitavel, "")

    def test_abrir_o_documento_completa_boleto_antigo(self):
        """Os boletos emitidos antes da correção ganham a linha na primeira abertura."""
        conta = self.conta()
        with rls_bypass():
            boleto = Boleto.objects.create(tenant=self.tenant, conta_receber=conta, valor=conta.valor,
                                           data_vencimento=conta.data_vencimento, gateway_id="pay_velho",
                                           status=Boleto.StatusBoleto.EMITIDO, linha_digitavel="")
        with patch.object(AsaasClient, "buscar_payment", return_value={"status": "PENDING"}), \
             patch.object(AsaasClient, "buscar_linha_digitavel", return_value={"identificationField": LINHA, "barCode": BARRAS}):
            resp = self.client.get(f"/api/erp/boletos/{boleto.pk}/documento/")
        self.assertEqual(resp.data["linha_digitavel"], LINHA)
        with rls_bypass():
            boleto.refresh_from_db()
        self.assertEqual((boleto.linha_digitavel, boleto.codigo_barras), (LINHA, BARRAS))


class FeriadoNoBoletoTests(_Base):
    """55 — a parcela de 01/01/2030 do dono: o boleto vai para 02/01, e diz por quê."""

    def test_previa_de_2030_conhece_o_1_de_janeiro_sem_a_tabela(self):
        Feriado.objects.all().delete()
        conta = self.conta(venc=date(2030, 1, 1))
        p = self.client.get(f"/api/erp/contas-a-receber/{conta.pk}/previa-cobranca/").data
        self.assertEqual(p["vencimento_bancario"], "2030-01-02")
        self.assertEqual(p["motivo_ajuste"], "Confraternização Universal")
        self.assertEqual(Decimal(p["total"]), conta.valor)  # empurrão de feriado não é atraso

    def test_carnaval_empurra_o_boleto(self):
        conta = self.conta(venc=date(2030, 3, 5))
        p = self.client.get(f"/api/erp/contas-a-receber/{conta.pk}/previa-cobranca/").data
        self.assertEqual((p["vencimento_bancario"], p["motivo_ajuste"]), ("2030-03-06", "Carnaval"))


class EditarContaComBoletoTests(_Base):
    """57 — o boleto acompanha a conta, ou a edição para com o motivo."""

    def setUp(self):
        super().setUp()
        self.c = self.conta(venc=date(2030, 1, 2), valor="2100.80")
        with rls_bypass():
            self.boleto = Boleto.objects.create(
                tenant=self.tenant, conta_receber=self.c, valor=Decimal("2100.80"),
                data_vencimento=date(2030, 1, 2), gateway_id="pay_vivo", status=Boleto.StatusBoleto.EMITIDO,
            )

    def _put(self, **mudar):
        base = {"cliente": self.joao.pk, "empreendimento": self.emp.pk, "descricao": self.c.descricao,
                "valor": "2100.80", "data_vencimento": "2030-01-02"}
        return self.client.put(f"/api/erp/contas-a-receber/{self.c.pk}/", base | mudar, format="json")

    def test_mudar_vencimento_sem_confirmar_e_recusado_com_o_que_vai_acontecer(self):
        resp = self._put(data_vencimento="2030-01-03")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("cancelado", str(resp.data["atualizar_boleto"]))

    @patch("funcoescobrancas.tasks.criar_cobranca.delay")
    def test_confirmado_salva_e_emite_a_segunda_via(self, delay):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._put(data_vencimento="2030-01-03", atualizar_boleto=True)
        self.assertEqual(resp.status_code, 200, resp.data)
        delay.assert_called_once_with(self.c.pk)
        with rls_bypass():
            log = AuditLog.objects.get(acao="editar_financeiro", objeto_id=str(self.c.pk))
        self.assertEqual(log.detalhes["mudancas"]["data_vencimento"], ["2030-01-02", "2030-01-03"])
        self.assertTrue(log.detalhes["boleto_reemitido"])

    @patch("funcoescobrancas.tasks.criar_cobranca.delay")
    def test_descricao_muda_sem_mexer_no_boleto(self, delay):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._put(descricao="Parcela 46/48 — QD 6 · LT 14")
        self.assertEqual(resp.status_code, 200, resp.data)
        delay.assert_not_called()

    def test_trocar_o_cliente_com_boleto_vivo_e_recusado(self):
        resp = self._put(cliente=self.maria.pk, atualizar_boleto=True)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("boleto não muda de pagador", str(resp.data["cliente"]))

    def test_boleto_do_banco_trava_valor_e_vencimento(self):
        with rls_bypass():
            self.boleto.canal = Boleto.Canal.CNAB
            self.boleto.gateway_id = ""
            self.boleto.save()
        resp = self._put(valor="2000.00", atualizar_boleto=True)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("registrado no banco", str(resp.data["valor"]))

    def test_detalhe_avisa_o_boleto_que_ficou_para_tras(self):
        """O caso do dono: a conta foi para 02/01 e o boleto ficou em 01/01."""
        with rls_bypass():
            self.boleto.data_vencimento = date(2030, 1, 1)
            self.boleto.save()
        detalhe = self.client.get(f"/api/erp/contas-a-receber/{self.c.pk}/").data
        self.assertIn("01/01/2030", detalhe["boleto_desatualizado"])
        self.assertIn("02/01/2030", detalhe["boleto_desatualizado"])

    def test_boleto_empurrado_por_feriado_nao_e_desatualizado(self):
        with rls_bypass():
            self.boleto.data_vencimento = date(2030, 1, 3)
            self.boleto.dados_retorno_api = {"ajuste_de_vencimento": {"contratual": "2030-01-02", "bancario": "2030-01-03"}}
            self.boleto.save()
        detalhe = self.client.get(f"/api/erp/contas-a-receber/{self.c.pk}/").data
        self.assertEqual(detalhe["boleto_desatualizado"], "")

    def test_editar_conta_a_pagar_deixa_rastro(self):
        from fornecedores.models import Fornecedor
        from moduloerp.models import ContaPagar
        with rls_bypass():
            forn = Fornecedor.objects.create(tenant=self.tenant, razao_social="Brita SA", email="b@b.com")
            cp = ContaPagar.objects.create(tenant=self.tenant, fornecedor=forn, descricao="Brita",
                                           valor=Decimal("300"), data_vencimento=HOJE)
        resp = self.client.put(f"/api/erp/contas-a-pagar/{cp.pk}/", {
            "fornecedor": forn.pk, "empreendimento": None, "descricao": "Brita", "valor": "350.00",
            "data_vencimento": HOJE.isoformat(),
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        with rls_bypass():
            self.assertTrue(AuditLog.objects.filter(acao="editar_financeiro", objeto_id=str(cp.pk)).exists())


class AcompanharNotaTests(_Base):
    """58 — "Created" na NFE.io não é fim: o SGI volta a perguntar."""

    def setUp(self):
        super().setUp()
        with rls_bypass():
            self.nf = NotaFiscalServico.objects.create(
                tenant=self.tenant, status=StatusNFE.PROCESSANDO, city_service_code="010701",
                description="Parcela", services_amount=Decimal("100"), nfe_io_id="inv_1",
                borrower_data={"cpf_cnpj": "52998224725", "cep": "88130000", "cidade_ibge": "4211900",
                               "nome_completo": "João", "endereco": "Rua A", "numero_endereco": "10",
                               "bairro": "Centro", "cidade": "Palhoça", "estado": "SC", "email": "j@x.com"},
            )

    @patch("moduloerp.tasks.consultar_nota_fiscal_servico.apply_async")
    @patch("moduloerp.nfe_client.NFeClient.emitir_nfse",
           return_value={"nfe_io_id": "inv_1", "status": "Created", "full_response": {}})
    def test_emissao_em_processamento_agenda_a_consulta(self, _emitir, agenda):
        from moduloerp.tasks import emitir_nota_fiscal_servico
        emitir_nota_fiscal_servico.apply(args=[self.nf.pk])
        agenda.assert_called_once()
        self.assertEqual(agenda.call_args.kwargs["kwargs"], {"tentativa": 1})

    @patch("moduloerp.tasks.consultar_nota_fiscal_servico.apply_async")
    @patch("moduloerp.nfe_client.NFeClient.consultar_nfse",
           return_value={"nfe_io_id": "inv_1", "status": "Processing", "full_response": {}})
    def test_segue_perguntando_ate_o_teto(self, _consultar, agenda):
        from moduloerp.tasks import consultar_nota_fiscal_servico
        from payment.planos import ERP_NFSE_CONSULTA_TENTATIVAS
        consultar_nota_fiscal_servico.apply(args=[self.nf.pk], kwargs={"tentativa": 3})
        self.assertEqual(agenda.call_args.kwargs["kwargs"], {"tentativa": 4})
        agenda.reset_mock()
        consultar_nota_fiscal_servico.apply(args=[self.nf.pk], kwargs={"tentativa": ERP_NFSE_CONSULTA_TENTATIVAS})
        agenda.assert_not_called()

    @patch("moduloerp.tasks.consultar_nota_fiscal_servico.apply_async")
    @patch("moduloerp.nfe_client.NFeClient.resolver_url_arquivo", return_value=None)
    @patch("moduloerp.nfe_client.NFeClient.consultar_nfse",
           return_value={"nfe_io_id": "inv_1", "status": "Issued", "numero": 6, "full_response": {}})
    def test_emitida_para_de_perguntar(self, _consultar, _url, agenda):
        from moduloerp.tasks import consultar_nota_fiscal_servico
        consultar_nota_fiscal_servico.apply(args=[self.nf.pk], kwargs={"tentativa": 2})
        agenda.assert_not_called()
        with rls_bypass():
            self.nf.refresh_from_db()
        self.assertEqual((self.nf.status, self.nf.numero), (StatusNFE.EMITIDA, "6"))

    @patch("moduloerp.tasks.consultar_nota_fiscal_servico.apply_async")
    @patch("moduloerp.nfe_client.NFeClient.consultar_nfse",
           return_value={"nfe_io_id": "inv_1", "status": "Processing", "full_response": {}})
    def test_consulta_da_tela_nao_encadeia(self, _consultar, agenda):
        from moduloerp.tasks import consultar_nota_fiscal_servico
        consultar_nota_fiscal_servico.apply(args=[self.nf.pk])
        agenda.assert_not_called()


@patch("nucleo.geo.resolver", return_value={"ibge": "4211900"})
class NotasEmLoteTests(_Base):
    """Pedido do dono (01/10/2026): as notas do mês num clique, com a mesma escolha da grade."""

    def test_previa_separa_quem_sai_quem_tem_nota_e_quem_falta_cadastro(self, _geo):
        a, b = self.conta(), self.conta()
        sem_cep = self.conta(cliente=self.maria)
        with rls_bypass():
            nf = NotaFiscalServico.objects.create(tenant=self.tenant, status=StatusNFE.EMITIDA, city_service_code="1",
                                                  description="x", services_amount=1, borrower_data={})
            b.nota_fiscal_servico = nf
            b.save()
        p = self.client.post("/api/erp/contas-a-receber/previa-lote-nfse/",
                             {"ids": [a.pk, b.pk, sem_cep.pk]}, format="json").data
        self.assertEqual((p["emitir"], p["com_nota"], p["sem_cadastro"]), (1, 1, 1))
        self.assertEqual(p["cadastro_incompleto"][0]["falta"], ["CEP"])

    @patch("moduloerp.views.emitir_nota_fiscal_servico.apply_async")
    @patch("moduloerp.views.emitir_nota_fiscal_servico.delay")
    def test_emite_espacado_e_diz_quem_ficou_de_fora(self, delay, apply_async, _geo):
        contas = [self.conta() for _ in range(3)]
        sem_cep = self.conta(cliente=self.maria)
        resp = self.client.post("/api/erp/contas-a-receber/emitir-lote-nfse/",
                                {"ids": [c.pk for c in contas] + [sem_cep.pk]}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["enviadas"], 3)
        self.assertEqual(resp.data["recusadas"][0]["cliente_id"], self.maria.pk)
        # A primeira sai já; as outras, espaçadas.
        self.assertEqual(delay.call_count + apply_async.call_count, 3)
        with rls_bypass():
            self.assertEqual(NotaFiscalServico.objects.count(), 3)

    @patch("moduloerp.views.emitir_nota_fiscal_servico.apply_async")
    @patch("moduloerp.views.emitir_nota_fiscal_servico.delay")
    def test_todas_do_filtro_menos_as_desmarcadas(self, delay, apply_async, _geo):
        a, b, c = self.conta(), self.conta(), self.conta()
        resp = self.client.post(
            f"/api/erp/contas-a-receber/emitir-lote-nfse/?cliente={self.joao.pk}",
            {"todos_do_filtro": True, "excluir_ids": [b.pk]}, format="json",
        )
        self.assertEqual(resp.data["enviadas"], 2)
        with rls_bypass():
            self.assertIsNone(type(b).objects.get(pk=b.pk).nota_fiscal_servico_id)

    def test_teto_do_lote(self, _geo):
        self.user.iam_plano = "profissional"
        self.user.iam_quotas = {"notas_por_lote": 1}
        resp = self.client.post("/api/erp/contas-a-receber/previa-lote-nfse/",
                                {"ids": [self.conta().pk, self.conta().pk]}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("até 1 notas", resp.data["detail"])

    def test_sem_permissao_de_emitir_nota_e_negado(self, _geo):
        self.user.iam_permissions = [p for p in self.user.iam_permissions if p != "erp.nf.emitir"]
        resp = self.client.post("/api/erp/contas-a-receber/emitir-lote-nfse/", {"ids": [self.conta().pk]}, format="json")
        self.assertEqual(resp.status_code, 403)



class LimiteDoLoteTests(_Base):
    """§5.5u — infraestrutura ≥ plano ≥ empresa; quem muda é o admin ou `erp.lote.configurar`."""

    URL = "/api/erp/configuracao/lotes/"

    def setUp(self):
        super().setUp()
        self.user.iam_plano = "profissional"
        self.user.iam_quotas = {"boletos_por_lote": 500, "notas_por_lote": 500}

    def _pode_configurar(self):
        self.user.iam_permissions = [*self.user.iam_permissions, "erp.lote.configurar"]

    def _previa_boletos(self, n):
        ids = [self.conta().pk for _ in range(n)]
        return self.client.post("/api/erp/contas-a-receber/previa-cobrancas-lote/", {"ids": ids}, format="json")

    def test_mostra_o_teto_do_plano_e_quem_pode_mudar(self):
        r = self.client.get(self.URL).data
        self.assertEqual(r["plano"], "Profissional")
        self.assertEqual(r["boletos_por_lote"], {"valor": 500, "escolhido": None, "teto_plano": 500, "teto_infra": 5000})
        self.assertFalse(r["pode_editar"])

    def test_sem_a_permissao_especial_nao_muda(self):
        resp = self.client.put(self.URL, {"boletos_por_lote": 2}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_o_admin_do_tenant_muda_sem_a_permissao(self):
        self.user.is_tenant_admin = True
        resp = self.client.put(self.URL, {"boletos_por_lote": 2}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(resp.data["pode_editar"])

    def test_a_empresa_trava_abaixo_do_plano_e_a_recusa_diz_o_caminho(self):
        self._pode_configurar()
        resp = self.client.put(self.URL, {"boletos_por_lote": 2, "notas_por_lote": 1}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["boletos_por_lote"]["valor"], 2)
        recusa = self._previa_boletos(3)
        self.assertEqual(recusa.status_code, 400)
        self.assertIn("limite da sua empresa é 2 boletos", recusa.data["detail"])
        self.assertIn("o plano permite até 500", recusa.data["detail"])
        self.assertEqual(self._previa_boletos(2).data["teto"], 2)
        with rls_bypass():
            log = AuditLog.objects.get(acao="configurar_limite_lote")
        self.assertEqual(log.detalhes["boletos_por_lote"], [None, 2])

    def test_acima_do_plano_e_recusado(self):
        self._pode_configurar()
        resp = self.client.put(self.URL, {"boletos_por_lote": 501}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("até 500 boletos", str(resp.data["boletos_por_lote"]))

    def test_vazio_volta_ao_maximo_do_plano(self):
        self._pode_configurar()
        self.client.put(self.URL, {"boletos_por_lote": 2}, format="json")
        resp = self.client.put(self.URL, {"boletos_por_lote": None}, format="json")
        self.assertEqual(resp.data["boletos_por_lote"]["valor"], 500)

    def test_o_teto_do_plano_oferece_o_plano_seguinte(self):
        self.user.iam_quotas = {"boletos_por_lote": 2}
        recusa = self._previa_boletos(3)
        self.assertEqual(recusa.status_code, 400)
        self.assertIn("plano Profissional emite até 2 boletos", recusa.data["detail"])
        self.assertIn("No plano Empresarial, até 2.000", recusa.data["detail"])

    def test_plano_que_desce_vence_o_numero_antigo_da_empresa(self):
        self._pode_configurar()
        self.client.put(self.URL, {"boletos_por_lote": 400}, format="json")
        self.user.iam_quotas = {"boletos_por_lote": 50}
        self.assertEqual(self.client.get(self.URL).data["boletos_por_lote"]["valor"], 50)

    def test_ficha_sem_a_quota_usa_o_plano(self):
        """Ficha da empresa publicada antes da quota existir: vale o plano da claim."""
        self.user.iam_plano = "essencial"
        self.user.iam_quotas = {"obras": 8}
        self.assertEqual(self.client.get(self.URL).data["notas_por_lote"]["teto_plano"], 50)
