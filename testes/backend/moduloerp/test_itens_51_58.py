"""Itens 51–58 do dono (30/09/2026) — ERP: contas, boletos, CNAB e nota fiscal.

Cada classe prende um item: a grade que acha pelo cliente e agrupa no banco
(51/53/54), o lote de boletos e o CNAB (52), a segunda via com feriado, multa e
juros (55), o PDF do boleto na tela (56), o estorno de baixa (57) e a nota que
não nasce sem o cadastro do tomador (58).
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from clientes.models import Cliente, ClienteEmpreendimento
from empreendimentos.models import Empreendimento, Unidade
from fornecedores.models import Fornecedor
from nucleo.models import Tenant, Usuario
from nucleo.tenancy import rls_bypass, tenant_context
from moduloerp.models import (
    Boleto, ContaCobrancaBancaria, ContaPagar, ContaReceber, ItemLoteCobranca, NotaFiscalServico,
    StatusConta, StatusNFE, Transacao,
)

HOJE = date(2026, 9, 30)
PERMISSOES = [
    "erp.conta_receber.view", "erp.conta_receber.edit", "erp.conta_receber.estornar",
    "erp.conta_pagar.view", "erp.conta_pagar.edit", "erp.conta_pagar.delete", "erp.conta_pagar.estornar",
    "erp.cobranca.view", "erp.cobranca.emitir", "erp.cobranca.conciliar", "erp.nf.emitir",
]


def _dados():
    tenant = Tenant.objects.create(slug="itens-51", nome="Loteadora 51")
    user = Usuario.objects.create(username="fin_51", tenant=tenant)
    emp = Empreendimento.objects.create(
        tenant=tenant, empreendimento="Jardim das Águas", razao_social="Jardim SA",
        cnpj="11222333000181", telefone="48999990000", endereco="Rua X, 1", cidade="Palhoça", estado="SC",
    )
    joao = Cliente.objects.create(
        tenant=tenant, nome_completo="João da Silva", cpf_cnpj="52998224725", email="j@x.com",
        data_nascimento=date(1980, 1, 1), endereco="Rua A", numero_endereco="10", bairro="Centro",
        cidade="Palhoça", estado="SC", cep="88130000", cidade_ibge="4211900",
    )
    maria = Cliente.objects.create(
        tenant=tenant, nome_completo="Maria Conceição", cpf_cnpj="11144477735", email="m@x.com",
        data_nascimento=date(1985, 1, 1), cidade="Palhoça", estado="SC",
    )
    unidade = Unidade.objects.create(tenant=tenant, empreendimento=emp, quadra="12", lote="05")
    venda = ClienteEmpreendimento.objects.create(
        tenant=tenant, cliente=joao, empreendimento=emp, unidade=unidade, data_compra=date(2025, 1, 1),
        condicoes_pagamento="financiamento_direto", valor_compra=Decimal("100000"),
    )
    return tenant, user, emp, joao, maria, venda


class _Base(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant, cls.user, cls.emp, cls.joao, cls.maria, cls.venda = _dados()

    def setUp(self):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = list(PERMISSOES)
        self.client.force_authenticate(user=self.user)

    def conta(self, cliente=None, venc=HOJE + timedelta(days=10), valor="1000.00", **extra):
        with rls_bypass():
            return ContaReceber.objects.create(
                tenant=self.tenant, cliente=cliente or self.joao, empreendimento=self.emp,
                cliente_empreendimento=self.venda if (cliente or self.joao) == self.joao else None,
                descricao=extra.pop("descricao", "Parcela 1/10 — QD 12 · LT 05"), valor=Decimal(valor),
                data_vencimento=venc, **extra,
            )


class GradeDeContasTests(_Base):
    """51/53/54 — a busca acha pelo cliente, a ordem desempata e os grupos somam no banco."""

    def test_busca_pelo_nome_do_cliente_sem_acento(self):
        self.conta(cliente=self.maria)
        self.conta()
        resp = self.client.get("/api/erp/contas-a-receber/?search=conceicao")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["cliente_nome"], "Maria Conceição")

    def test_cada_palavra_casa_pelo_comeco(self):
        """51 (01/10): `ana ro` é a Ana Ro…, não a Ana Ribei**ro**."""
        with rls_bypass():
            ribeiro = Cliente.objects.create(tenant=self.tenant, nome_completo="Ana Ribeiro", cpf_cnpj="39053344705",
                                             email="ar@x.com", data_nascimento=date(1990, 1, 1))
            rosa = Cliente.objects.create(tenant=self.tenant, nome_completo="Ana Rosa", cpf_cnpj="71428793860",
                                          email="rosa@x.com", data_nascimento=date(1990, 1, 1))
        self.conta(cliente=ribeiro)
        self.conta(cliente=rosa)
        resp = self.client.get("/api/erp/contas-a-receber/?search=ana ro").data
        self.assertEqual([l["cliente_nome"] for l in resp["results"]], ["Ana Rosa"])

    def test_aco_acha_o_aco_e_nao_as_fundacoes(self):
        """53 (01/10): `aco` acha "Aço Forte" — e não toda medição de "Fundações"."""
        with rls_bypass():
            aco = Fornecedor.objects.create(tenant=self.tenant, razao_social="Aço Forte Distribuidora", email="a@f.com")
            obra = Fornecedor.objects.create(tenant=self.tenant, razao_social="Concretos SA", email="c@c.com")
            ContaPagar.objects.create(tenant=self.tenant, fornecedor=aco, descricao="Vergalhão CA-50",
                                      valor=Decimal("10"), data_vencimento=HOJE)
            ContaPagar.objects.create(tenant=self.tenant, fornecedor=obra, descricao="Medição 1 · Torre A — Fundações",
                                      valor=Decimal("10"), data_vencimento=HOJE)
        for termo in ("aco", "aço", "AÇO"):
            linhas = self.client.get(f"/api/erp/contas-a-pagar/?search={termo}").data["results"]
            self.assertEqual([l["fornecedor_nome"] for l in linhas], ["Aço Forte Distribuidora"], termo)

    def test_numero_curto_ignora_o_zero_a_esquerda(self):
        self.conta()                                                  # QD 12 · LT 05
        self.conta(cliente=self.maria, descricao="Parcela avulsa")
        self.assertEqual(self.client.get("/api/erp/contas-a-receber/?search=5").data["count"], 1)

    def test_nomes_e_unidade_vem_prontos(self):
        self.conta()
        linha = self.client.get("/api/erp/contas-a-receber/").data["results"][0]
        self.assertEqual(linha["empreendimento_nome"], "Jardim das Águas")
        self.assertEqual(linha["unidade"], "QD 12 · LT 05")

    def test_cpf_so_busca_quem_pode_ver_o_documento(self):
        self.conta()
        sem = self.client.get("/api/erp/contas-a-receber/?search=529.982.247-25").data["count"]
        self.assertEqual(sem, 0)
        self.user.iam_permissions = PERMISSOES + ["cadastro.cliente_doc.view"]
        com = self.client.get("/api/erp/contas-a-receber/?search=529.982.247-25").data["count"]
        self.assertEqual(com, 1)

    def test_ordena_por_cliente_com_desempate_estavel(self):
        for _ in range(3):
            self.conta(cliente=self.maria)
        self.conta()
        ids = [l["conta_receber_id"] for l in self.client.get("/api/erp/contas-a-receber/?ordering=cliente").data["results"]]
        self.assertEqual(ids[0], ContaReceber.objects.filter(cliente=self.joao).get().pk)
        self.assertEqual(ids[1:], sorted(ids[1:]))

    def test_grupos_e_totais_saem_do_banco(self):
        with patch("moduloerp.listao.hoje_local", return_value=HOJE):
            self.conta(venc=HOJE - timedelta(days=40), valor="100.00")
            self.conta(venc=HOJE + timedelta(days=5), valor="200.00")
            self.conta(venc=HOJE - timedelta(days=5), valor="50.00", status=StatusConta.QUITADO, valor_pago=Decimal("50"))
            resp = self.client.get("/api/erp/contas-a-receber/grupos/?por=faixa")
        self.assertEqual(resp.data["totais"]["contagem"], 3)
        self.assertEqual(Decimal(resp.data["totais"]["saldo"]), Decimal("300.00"))
        self.assertEqual(Decimal(resp.data["totais"]["vencido"]), Decimal("100.00"))
        faixas = {g["chaves"][0]: g["contagem"] for g in resp.data["grupos"]}
        self.assertEqual(faixas, {"a_vencer": 1, "d31_60": 1, "encerrado": 1})

    def test_abrir_o_grupo_pelo_mes(self):
        self.conta(venc=date(2026, 3, 10))
        self.conta(venc=date(2026, 4, 10))
        grupos = self.client.get("/api/erp/contas-a-receber/grupos/?por=mes").data["grupos"]
        marco = next(g for g in grupos if g["rotulos"] == ["mar/2026"])
        linhas = self.client.get(f"/api/erp/contas-a-receber/?mes={marco['chaves'][0]}").data
        self.assertEqual(linhas["count"], 1)

    def test_boleto_diz_de_quem_e(self):
        conta = self.conta()
        with rls_bypass():
            Boleto.objects.create(tenant=self.tenant, conta_receber=conta, valor=conta.valor,
                                  data_vencimento=conta.data_vencimento, status=Boleto.StatusBoleto.EMITIDO)
        linha = self.client.get("/api/erp/boletos/?search=silva").data["results"][0]
        self.assertEqual(linha["pessoa_nome"], "João da Silva")
        self.assertEqual(linha["unidade"], "QD 12 · LT 05")


class SegundaViaTests(_Base):
    """55 — título vencido ganha nova data e leva multa e juros do contrato."""

    def test_previa_de_titulo_vencido_sugere_data_e_calcula_encargos(self):
        conta = self.conta(venc=HOJE - timedelta(days=30))
        with patch("funcoescobrancas.segunda_via.timezone.localdate", return_value=HOJE):
            p = self.client.get(f"/api/erp/contas-a-receber/{conta.pk}/previa-cobranca/").data
        self.assertTrue(p["vencida"])
        self.assertEqual(p["vencimento_escolhido"], (HOJE + timedelta(days=3)).isoformat())
        # 2% de multa sobre 1000 e 1% ao mês pró-rata por dia até o boleto.
        self.assertEqual(Decimal(p["multa"]), Decimal("20.00"))
        dias = (date.fromisoformat(p["vencimento_bancario"]) - conta.data_vencimento).days
        self.assertEqual(Decimal(p["juros"]), (Decimal("1000") * Decimal("0.01") / 30 * dias).quantize(Decimal("0.01")))
        self.assertEqual(Decimal(p["total"]), Decimal("1000") + Decimal(p["multa"]) + Decimal(p["juros"]))

    def test_data_no_passado_e_recusada_com_frase(self):
        conta = self.conta(venc=HOJE - timedelta(days=30))
        with patch("funcoescobrancas.segunda_via.timezone.localdate", return_value=HOJE):
            resp = self.client.post(f"/api/erp/contas-a-receber/{conta.pk}/gerar-cobranca/",
                                    {"vencimento": (HOJE - timedelta(days=1)).isoformat()}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("anterior a hoje", resp.data["detail"])

    def test_emissao_embute_encargos_e_substitui_o_boleto_vencido(self):
        from funcoescobrancas import services
        from funcoescobrancas.client import AsaasClient
        conta = self.conta(venc=HOJE - timedelta(days=30))
        with rls_bypass():
            antigo = Boleto.objects.create(tenant=self.tenant, conta_receber=conta, valor=conta.valor,
                                           data_vencimento=conta.data_vencimento, gateway_id="pay_old",
                                           status=Boleto.StatusBoleto.VENCIDO)
        enviados = {}
        with patch("funcoescobrancas.segunda_via.timezone.localdate", return_value=HOJE), \
             patch.object(AsaasClient, "buscar_customer_por_cpf_cnpj", return_value=None), \
             patch.object(AsaasClient, "criar_customer", return_value={"id": "cus"}), \
             patch.object(AsaasClient, "cancelar_payment", return_value={"deleted": True}) as cancelar, \
             patch.object(AsaasClient, "criar_payment", side_effect=lambda **k: enviados.update(k) or {"id": "pay_new"}):
            with tenant_context(self.tenant.pk):
                novo = services.gerar_cobranca_asaas(conta)
        cancelar.assert_called_once_with("pay_old")
        antigo.refresh_from_db()
        self.assertEqual(antigo.status, Boleto.StatusBoleto.CANCELADO)
        self.assertEqual(novo.valor, conta.valor + novo.valor_multa + novo.valor_juros)
        self.assertEqual(Decimal(str(enviados["valor"])), novo.valor)
        self.assertEqual(novo.valor_multa, Decimal("20.00"))

    def test_webhook_lanca_multa_e_juros_como_encargos(self):
        from funcoescobrancas import services
        conta = self.conta(venc=HOJE - timedelta(days=30))
        with rls_bypass():
            Boleto.objects.create(tenant=self.tenant, conta_receber=conta, valor=Decimal("1030.00"),
                                  valor_multa=Decimal("20.00"), valor_juros=Decimal("10.00"),
                                  data_vencimento=HOJE, gateway_id="pay_sv", status=Boleto.StatusBoleto.EMITIDO)
        services.processar_evento_webhook(evento_id="evt-sv", tipo="PAYMENT_RECEIVED",
                                          payload={"payment": {"id": "pay_sv", "value": 1030.0}})
        with rls_bypass():
            conta.refresh_from_db()
        self.assertEqual(conta.status, StatusConta.QUITADO)
        self.assertEqual((conta.multa, conta.juros, conta.valor_pago), (Decimal("20.00"), Decimal("10.00"), Decimal("1030.00")))


class EstornoTests(_Base):
    """57 — com baixa, o financeiro trava; o estorno reabre e acrescenta ao ledger."""

    def setUp(self):
        super().setUp()
        with rls_bypass():
            self.fornecedor = Fornecedor.objects.create(tenant=self.tenant, razao_social="Areia SA", email="a@a.com")
            self.cp = ContaPagar.objects.create(tenant=self.tenant, fornecedor=self.fornecedor, descricao="Areia",
                                                valor=Decimal("500"), data_vencimento=HOJE)
        with tenant_context(self.tenant.pk):
            self.cp.dar_baixa(valor=Decimal("500"), data=HOJE, usuario=self.user)

    def _payload(self, **mudar):
        base = {"fornecedor": self.fornecedor.pk, "empreendimento": None, "descricao": "Areia lavada",
                "valor": "500.00", "data_vencimento": HOJE.isoformat()}
        return base | mudar

    def test_descricao_segue_editavel(self):
        resp = self.client.put(f"/api/erp/contas-a-pagar/{self.cp.pk}/", self._payload(), format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["descricao"], "Areia lavada")

    def test_valor_trava_com_a_saida_na_frase(self):
        resp = self.client.put(f"/api/erp/contas-a-pagar/{self.cp.pk}/", self._payload(valor="400.00"), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("estorne a baixa", str(resp.data["valor"]))
        detalhe = self.client.get(f"/api/erp/contas-a-pagar/{self.cp.pk}/").data
        self.assertIn("valor", detalhe["campos_travados"])
        self.assertTrue(detalhe["pode_estornar"])

    def test_estorno_reabre_e_anula_no_ledger(self):
        resp = self.client.post(f"/api/erp/contas-a-pagar/{self.cp.pk}/estornar-baixa/",
                                {"motivo": "Baixa lançada na conta errada"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ABERTO")
        with rls_bypass():
            valores = sorted(Transacao.objects.filter(conta_pagar=self.cp).values_list("valor", flat=True))
        self.assertEqual(valores, [Decimal("-500.00"), Decimal("500.00")])

    def test_estorno_sem_permissao_e_negado(self):
        self.user.iam_permissions = [p for p in PERMISSOES if not p.endswith(".estornar")]
        resp = self.client.post(f"/api/erp/contas-a-pagar/{self.cp.pk}/estornar-baixa/",
                                {"motivo": "tentativa"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_estorno_exige_motivo(self):
        resp = self.client.post(f"/api/erp/contas-a-pagar/{self.cp.pk}/estornar-baixa/", {"motivo": ""}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_conta_com_baixa_nao_se_exclui(self):
        resp = self.client.delete(f"/api/erp/contas-a-pagar/{self.cp.pk}/")
        self.assertEqual(resp.status_code, 400)


class NotaFiscalTomadorTests(_Base):
    """58 — a nota não nasce sem o cadastro do tomador; e erro não prende a conta."""

    @patch("moduloerp.views.emitir_nota_fiscal_servico.delay")
    def test_falta_de_cep_recusa_antes_de_criar_a_nota(self, delay):
        conta = self.conta(cliente=self.maria)
        with patch("nucleo.geo.resolver", return_value={"ibge": "4211900"}):
            resp = self.client.post(f"/api/erp/contas-a-receber/{conta.pk}/emitir-nfse/", {}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["faltando"], ["CEP"])
        self.assertEqual(resp.data["cliente_id"], self.maria.pk)
        self.assertFalse(NotaFiscalServico.objects.exists())
        delay.assert_not_called()
        self.maria.refresh_from_db()
        self.assertEqual(self.maria.cidade_ibge, "4211900")  # o município foi completado

    @patch("moduloerp.views.emitir_nota_fiscal_servico.delay")
    def test_nota_com_erro_nao_prende_a_conta(self, delay):
        conta = self.conta()
        with rls_bypass():
            nf = NotaFiscalServico.objects.create(tenant=self.tenant, status=StatusNFE.ERRO, city_service_code="1",
                                                  description="x", services_amount=1, borrower_data={})
            conta.nota_fiscal_servico = nf
            conta.save()
        resp = self.client.post(f"/api/erp/contas-a-receber/{conta.pk}/emitir-nfse/", {}, format="json")
        self.assertEqual(resp.status_code, 202)
        with rls_bypass():
            self.assertEqual(NotaFiscalServico.objects.count(), 2)


class LoteDeBoletosTests(_Base):
    """52 — a triagem separa o que sai, e cada conta do lote tem o seu desfecho."""

    def test_previa_separa_emitir_segunda_via_e_ja_emitidos(self):
        self.conta()
        self.conta(venc=HOJE - timedelta(days=20))
        com_boleto = self.conta()
        with rls_bypass():
            Boleto.objects.create(tenant=self.tenant, conta_receber=com_boleto, valor=com_boleto.valor,
                                  data_vencimento=com_boleto.data_vencimento, gateway_id="pay_x",
                                  status=Boleto.StatusBoleto.EMITIDO)
        with patch("moduloerp.cobranca_lote.timezone.localdate", return_value=HOJE):
            p = self.client.post("/api/erp/contas-a-receber/previa-cobrancas-lote/", {"todos_do_filtro": True}, format="json").data
        self.assertEqual((p["emitir"], p["segunda_via"], p["com_boleto_valido"]), (1, 1, 1))

    def test_todas_do_filtro_menos_as_desmarcadas(self):
        """51 (01/10): marcar todas e desmarcar uma leva as outras."""
        self.conta()
        fora = self.conta()
        self.conta()
        with patch("moduloerp.cobranca_lote.timezone.localdate", return_value=HOJE):
            p = self.client.post("/api/erp/contas-a-receber/previa-cobrancas-lote/",
                                 {"todos_do_filtro": True, "excluir_ids": [fora.pk]}, format="json").data
        self.assertEqual(p["emitir"], 2)

    def test_previa_diz_quem_o_banco_recusaria(self):
        self.conta()                      # João tem endereço completo
        self.conta(cliente=self.maria)    # Maria não tem endereço nem CEP
        p = self.client.post("/api/erp/contas-a-receber/previa-cobrancas-lote/", {"todos_do_filtro": True}, format="json").data
        self.assertEqual(p["boletos_sem_cadastro"], 1)
        self.assertEqual([c["cliente_nome"] for c in p["cadastro_incompleto"]], ["Maria Conceição"])
        self.assertIn("CEP", p["cadastro_incompleto"][0]["falta"])

    def test_lote_asaas_enfileira_uma_task_por_conta(self):
        contas = [self.conta(), self.conta()]
        with patch("funcoescobrancas.tasks.criar_cobranca.apply_async") as fila, \
             self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post("/api/erp/contas-a-receber/gerar-cobrancas-lote/",
                                    {"ids": [c.pk for c in contas]}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["pendentes"], 2)
        self.assertEqual(fila.call_count, 2)
        item_id = fila.call_args_list[0].kwargs["kwargs"]["item_lote_id"]
        with rls_bypass():
            self.assertTrue(ItemLoteCobranca.objects.filter(pk=item_id).exists())


class CnabTests(_Base):
    """52 — código de barras, remessa, retorno e o boleto em PDF."""

    def carteira(self, banco="341", layout="400", **extra):
        with rls_bypass():
            return ContaCobrancaBancaria.objects.create(
                tenant=self.tenant, nome="Cobrança", banco=banco, layout=layout, agencia="1234", conta="12345",
                conta_dv="6", carteira="109" if banco == "341" else "09", convenio=extra.pop("convenio", "1234567"),
                beneficiario_nome="Loteadora 51", beneficiario_documento="11222333000181", **extra,
            )

    def test_cnpj_com_mascara_e_gravado_so_com_digitos(self):
        resp = self.client.post("/api/erp/carteiras-cobranca/", {
            "nome": "Itaú 109", "banco": "341", "layout": "400", "agencia": "1234", "conta": "12345",
            "carteira": "109", "beneficiario_nome": "Loteadora", "beneficiario_documento": "66.774.885/0001-90",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["beneficiario_documento"], "66774885000190")
        curto = self.client.post("/api/erp/carteiras-cobranca/", {
            "nome": "X", "banco": "341", "layout": "400", "agencia": "1", "conta": "1", "carteira": "109",
            "beneficiario_nome": "L", "beneficiario_documento": "6677488500",
        }, format="json")
        self.assertEqual(curto.status_code, 400)

    def test_fator_de_vencimento_reinicia_em_2025(self):
        from moduloerp.cnab.codigo_barras import fator_vencimento
        self.assertEqual(fator_vencimento(date(2025, 2, 21)), "9999")
        self.assertEqual(fator_vencimento(date(2025, 2, 22)), "1000")
        self.assertEqual(fator_vencimento(date(2000, 7, 3)), "1000")

    def test_linha_digitavel_volta_ao_codigo_de_barras(self):
        from moduloerp.cnab.bancos import BANCOS
        from moduloerp.cnab.codigo_barras import de_linha_digitavel, dv_codigo_barras, linha_digitavel, montar
        for codigo, banco in BANCOS.items():
            c = self.carteira(banco=codigo, layout="240", variacao_carteira="01")
            nn = banco.nosso_numero(c, 42)
            barras = montar(codigo, HOJE, Decimal("1234.56"), banco.campo_livre(c, nn))
            self.assertEqual(len(barras), 44, banco.nome)
            self.assertEqual(int(barras[4]), dv_codigo_barras(barras[:4] + barras[5:]), banco.nome)
            self.assertEqual(de_linha_digitavel(linha_digitavel(barras)), barras, banco.nome)

    def _lote_cnab(self, layout):
        c = self.carteira(banco="341", layout=layout)
        conta = self.conta()
        resp = self.client.post("/api/erp/contas-a-receber/gerar-cobrancas-lote/",
                                {"ids": [conta.pk], "canal": "cnab", "conta_cobranca": c.pk}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        return c, conta, resp.data

    def test_remessa_400_tem_linhas_de_400_posicoes(self):
        c, conta, lote = self._lote_cnab("400")
        arquivo = self.client.get(f"/api/erp/remessas-cnab/{lote['remessa_id']}/arquivo/").content.decode("latin-1")
        linhas = arquivo.split("\r\n")[:-1]
        self.assertEqual({len(l) for l in linhas}, {400})
        self.assertEqual(len(linhas), 3)

    def test_remessa_240_tem_linhas_de_240_posicoes(self):
        c, conta, lote = self._lote_cnab("240")
        arquivo = self.client.get(f"/api/erp/remessas-cnab/{lote['remessa_id']}/arquivo/").content.decode("latin-1")
        linhas = arquivo.split("\r\n")[:-1]
        self.assertEqual({len(l) for l in linhas}, {240})
        self.assertEqual(len(linhas), 7)  # 2 headers + P/Q/R + 2 trailers

    def _remessa_240(self, banco):
        c = self.carteira(banco=banco, layout="240", variacao_carteira="01")
        conta = self.conta()
        resp = self.client.post("/api/erp/contas-a-receber/gerar-cobrancas-lote/",
                                {"ids": [conta.pk], "canal": "cnab", "conta_cobranca": c.pk}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        arquivo = self.client.get(f"/api/erp/remessas-cnab/{resp.data['remessa_id']}/arquivo/").content.decode("latin-1")
        return arquivo.split("\r\n")[:-1], conta

    def test_remessa_240_segue_o_febraban_em_todo_banco(self):
        """52 (01/10, laudo do validador): juros e multa a partir do dia seguinte
        ao vencimento, DV da agência cobradora e dias de baixa em branco."""
        from moduloerp.cnab.bancos import BANCOS
        for codigo in BANCOS:
            linhas, _ = self._remessa_240(codigo)
            p, r = linhas[2], linhas[4]
            # O vencimento do boleto (P 78-85) já saiu do fim de semana.
            dia_seguinte = (datetime.strptime(p[77:85], "%d%m%Y") + timedelta(days=1)).strftime("%d%m%Y")
            self.assertEqual(p[118:126], dia_seguinte, f"{codigo}: data dos juros (P 119-126)")
            self.assertEqual(r[66:74], dia_seguinte, f"{codigo}: data da multa (R 67-74)")
            self.assertEqual(p[105], " ", f"{codigo}: DV da agência cobradora (P 106)")
            self.assertEqual(p[224:227], "   ", f"{codigo}: dias para baixa (P 225-227)")
            self.assertEqual(linhas[1][11:13], "00" if codigo == "341" else "  ", f"{codigo}: header de lote 12-13")

    def test_remessa_240_do_sicoob_passa_no_validador_do_sicoob(self):
        """52 (01/10): os campos que o validador CNAB do Sicoob apontou."""
        linhas, _ = self._remessa_240("756")
        header, lote, p = linhas[0], linhas[1], linhas[2]
        self.assertEqual({l[:3] for l in linhas}, {"756"})
        self.assertEqual(header[71], "0")                     # DV agência/conta
        self.assertEqual(header[102:132].strip(), "SICOOB")   # nome do banco
        self.assertEqual(header[163:166], "081")              # versão do arquivo
        self.assertEqual(lote[13:16], "040")                  # versão do lote
        self.assertEqual(lote[33:53], " " * 20)               # convênio do lote
        self.assertEqual(p[58:60], "0 ")                      # forma de cadastramento e tipo de documento

    def test_pagador_sem_cep_fica_fora_com_o_motivo(self):
        c = self.carteira()
        conta = self.conta(cliente=self.maria)
        resp = self.client.post("/api/erp/contas-a-receber/gerar-cobrancas-lote/",
                                {"ids": [conta.pk], "canal": "cnab", "conta_cobranca": c.pk}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("CEP", resp.data["detail"])

    def test_retorno_de_liquidacao_quita_a_conta_uma_vez_so(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        c, conta, _ = self._lote_cnab("400")
        with rls_bypass():
            boleto = Boleto.objects.get(conta_receber=conta)
        detalhe = [" "] * 400
        detalhe[0] = "1"
        for pos, valor in ((37, str(boleto.boleto_id).ljust(25)), (108, "06"), (110, "300926"),
                           (253, f"{int(boleto.valor * 100):013d}"), (266, "0" * 13), (394, "000002")):
            detalhe[pos:pos + len(valor)] = list(valor)
        arquivo = ("0" + " " * 393 + "000001\r\n" + "".join(detalhe) + "\r\n" + "9" + " " * 393 + "000003\r\n")
        for _ in range(2):
            resp = self.client.post("/api/erp/retornos-cnab/enviar/", {
                "conta_cobranca": c.pk, "arquivo": SimpleUploadedFile("ret.RET", arquivo.encode("latin-1")),
            }, format="multipart")
            self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["resumo"]["ja_processados"], 1)
        with rls_bypass():
            conta.refresh_from_db()
            boleto.refresh_from_db()
        self.assertEqual(conta.status, StatusConta.QUITADO)
        self.assertEqual(boleto.status, Boleto.StatusBoleto.PAGO)

    def test_boleto_do_banco_sai_em_pdf(self):
        c, conta, _ = self._lote_cnab("400")
        with rls_bypass():
            boleto = Boleto.objects.get(conta_receber=conta)
        resp = self.client.get(f"/api/erp/boletos/{boleto.pk}/pdf/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))
