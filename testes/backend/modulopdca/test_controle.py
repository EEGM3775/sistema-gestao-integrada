# testes/backend/modulopdca/test_controle.py
"""O posto Controle (decisão do dono, 10/10/2026): o custo e o material da obra.

As colunas vieram do Orçamento (ORC.3) e continuam sendo leituras distintas —
somar comprometido com realizado, ou ratear despesa de empreendimento por
aproximação, dá um número que parece certo e não é. O que mudou: o contrato de
empreiteiro entra no comprometido (só o que não tem pedido de serviço, que já
está no pedido), o medido vira coluna e o valor agregado projeta o custo final.
"""
from datetime import date
from decimal import Decimal
from unittest import mock

from catalogo.models import Item
from fornecedores.models import Fornecedor
from moduloerp.models import ContaPagar
from modulosil.models import LocalEstoque, MovimentacaoEstoque
from moduloscm.models import CentroCusto, PedidoCompra

from moduloorcamento import planilha
from moduloorcamento.models import ItemOrcadoInsumo
from modulopdca import controle
from modulopdca.models import ContratoObra, Cronograma, RegimeContrato

from testes.backend.moduloorcamento.test_planilha import PlanilhaTestBase


class ControleTestBase(PlanilhaTestBase):
    def setUp(self):
        super().setUp()
        self.fornecedor = Fornecedor.objects.create(
            tenant=self.tenant, razao_social="Fornecedor A LTDA",
            cnpj="11222333000181", email="compras@a.com.br",
        )
        self.centro = CentroCusto.objects.create(
            tenant=self.tenant, nome="Obra Aurora", tipo=CentroCusto.Tipo.OBRA, obra=self.obra,
        )
        self.item = Item.objects.create(
            tenant=self.tenant, codigo_interno="CIM-01", descricao="Cimento", unidade="KG",
        )

    def _orcamento_aprovado(self, valor="100000"):
        orc = self._orcamento()
        linha = self._linha(orc, "Estrutura", quantidade="1", custo=valor, etapa=self.fundacao)
        planilha.aprovar_orcamento(orc)
        return orc, linha

    def _pedido(self, valor, *, status=PedidoCompra.Status.ENVIADO, conta=None):
        return PedidoCompra.objects.create(
            tenant=self.tenant, fornecedor=self.fornecedor, centro_custo=self.centro,
            status=status, valor_total=Decimal(valor), conta_pagar_ref=conta,
        )

    def _saida(self, quantidade, custo, tipo=MovimentacaoEstoque.Tipo.SAIDA):
        local = LocalEstoque.objects.create(
            tenant=self.tenant, nome=f"Canteiro {quantidade}{tipo}", obra=self.obra,
        )
        return MovimentacaoEstoque.objects.create(
            tenant=self.tenant, item=self.item, local=local, tipo=tipo,
            quantidade=Decimal(quantidade), custo_unitario=Decimal(custo),
            obra=self.obra, etapa=self.fundacao,
        )

    def _contrato(self, valor, *, pedido=None, status=ContratoObra.Status.VIGENTE):
        return ContratoObra.objects.create(
            tenant=self.tenant, obra=self.obra, fornecedor=self.fornecedor,
            numero=f"C-{valor}", objeto="Empreitada", regime=RegimeContrato.GLOBAL,
            valor_global=Decimal(valor), data_inicio=date(2026, 8, 1), status=status,
            pedido_scm=pedido,
        )

    def custo(self):
        return controle.custo_da_obra(obra=self.obra, tenant_id=self.tenant.id)


class ColunasTests(ControleTestBase):
    def test_as_colunas_sao_leituras_distintas(self):
        self._orcamento_aprovado("100000")
        self._pedido("60000")
        self._saida("100", "400")  # 40.000 aplicados

        colunas = self.custo()["colunas"]
        self.assertEqual(colunas["orcado"], "100000.00")
        self.assertEqual(colunas["comprometido"], "60000.00")
        self.assertEqual(colunas["aplicado"], "40000.00")
        self.assertEqual(colunas["realizado"], "0.00")
        self.assertEqual(colunas["saldo"], "40000.00")
        self.assertFalse(colunas["estourado"])

    def test_devolucao_desconta_do_aplicado(self):
        self._orcamento_aprovado("100000")
        self._saida("100", "400")
        self._saida("10", "400", tipo=MovimentacaoEstoque.Tipo.DEVOLUCAO)
        self.assertEqual(self.custo()["colunas"]["aplicado"], "36000.00")

    def test_contrato_de_empreiteiro_compromete_e_nao_conta_duas_vezes(self):
        """O contrato com pedido de serviço já está no pedido."""
        self._orcamento_aprovado("100000")
        pedido = self._pedido("20000")
        self._contrato("20000", pedido=pedido)
        self._contrato("30000")
        self._contrato("99999", status=ContratoObra.Status.RASCUNHO)

        colunas = self.custo()["colunas"]
        self.assertEqual(colunas["comprometido_pedidos"], "20000.00")
        self.assertEqual(colunas["comprometido_contratos"], "30000.00")
        self.assertEqual(colunas["comprometido"], "50000.00")

    def test_comprometido_acima_do_orcado_marca_estouro(self):
        self._orcamento_aprovado("50000")
        self._pedido("60000")
        colunas = self.custo()["colunas"]
        self.assertTrue(colunas["estourado"])
        self.assertEqual(colunas["saldo"], "-10000.00")

    def test_rascunho_e_cancelado_nao_comprometem(self):
        self._orcamento_aprovado("100000")
        self._pedido("10000", status=PedidoCompra.Status.RASCUNHO)
        self._pedido("20000", status=PedidoCompra.Status.CANCELADO)
        self._pedido("30000")
        self.assertEqual(self.custo()["colunas"]["comprometido"], "30000.00")

    def test_realizado_vem_da_baixa_do_erp_pelo_caminho_do_scm(self):
        conta = ContaPagar.objects.create(
            tenant=self.tenant, fornecedor=self.fornecedor, descricao="NF 123",
            valor=Decimal("60000"), data_vencimento=date(2026, 8, 10),
            valor_pago=Decimal("25000"),
        )
        self._orcamento_aprovado("100000")
        self._pedido("60000", conta=conta.pk)
        self.assertEqual(self.custo()["colunas"]["realizado"], "25000.00")

    def test_obra_sem_orcamento_aprovado_tem_orcado_nulo(self):
        """Zero se leria como 'estourou 100%' — o honesto é não ter régua."""
        self._pedido("10000")
        dados = self.custo()
        self.assertIsNone(dados["colunas"]["orcado"])
        self.assertIsNone(dados["colunas"]["saldo"])
        self.assertFalse(dados["colunas"]["estourado"])
        self.assertIsNone(dados["valor_agregado"]["idc"])

    def test_pedido_sem_centro_de_custo_de_obra_nao_entra(self):
        self._orcamento_aprovado("100000")
        administrativo = CentroCusto.objects.create(
            tenant=self.tenant, nome="Administrativo", tipo=CentroCusto.Tipo.ADMINISTRATIVO,
        )
        PedidoCompra.objects.create(
            tenant=self.tenant, fornecedor=self.fornecedor, centro_custo=administrativo,
            status=PedidoCompra.Status.ENVIADO, valor_total=Decimal("9999"),
        )
        self.assertEqual(self.custo()["colunas"]["comprometido"], "0.00")


class ValorAgregadoTests(ControleTestBase):
    def _avanco(self, previsto, realizado):
        Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano", data_inicio=date(2026, 8, 1),
            status=Cronograma.Status.VIGENTE,
        )
        linha = {"etapa": self.fundacao.pk, "previsto_pct": previsto, "realizado_pct": realizado}
        return mock.patch("modulopdca.services.avanco_fisico_financeiro", return_value={
            "linhas": [linha], "obra": {"previsto_pct": previsto, "realizado_pct": realizado},
        })

    def test_projecao_do_custo_final(self):
        """ONT 100.000; previsto 50%, feito 40% → VA 40.000; gasto 50.000 →
        IDC 0,8; falta (100.000 − 40.000) ÷ 0,8 = 75.000; ENT 125.000."""
        self._orcamento_aprovado("100000")
        self._saida("125", "400")  # 50.000 incorridos
        with self._avanco(50.0, 40.0):
            dados = self.custo()
        va = dados["valor_agregado"]
        self.assertEqual((va["vp"], va["va"], va["cr"]), ("50000.00", "40000.00", "50000.00"))
        self.assertEqual((va["idc"], va["idp"]), ("0.800", "0.800"))
        self.assertEqual((va["a_incorrer"], va["ent"], va["vnt"]), ("75000.00", "125000.00", "-25000.00"))
        etapa = dados["etapas"][0]
        self.assertEqual((etapa["etapa"], etapa["idc"]), (self.fundacao.pk, "0.800"))

    def test_sem_custo_incorrido_nao_inventa_indice(self):
        self._orcamento_aprovado("100000")
        with self._avanco(50.0, 40.0):
            va = self.custo()["valor_agregado"]
        self.assertIsNone(va["idc"])
        self.assertIsNone(va["ent"])
        self.assertEqual(va["idp"], "0.800")


class MateriaisTests(ControleTestBase):
    def test_orcado_aplicado_e_esperado_pelo_avanco(self):
        _orc, linha = self._orcamento_aprovado("100000")
        ItemOrcadoInsumo.objects.create(
            tenant=self.tenant, item_orcado=linha, item=self.item, descricao="Cimento", unidade="KG",
            categoria=ItemOrcadoInsumo.Categoria.MATERIAL, coeficiente=Decimal("1000"),
            custo_unitario=Decimal("1"), custo_no_item=Decimal("1000"),
        )
        self._saida("600", "1")
        Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano", data_inicio=date(2026, 8, 1),
            status=Cronograma.Status.VIGENTE,
        )
        with mock.patch("modulopdca.services.avanco_fisico_financeiro",
                        return_value={"linhas": [], "obra": {"realizado_pct": 50.0}}):
            dados = controle.materiais_da_obra(obra=self.obra, tenant_id=self.tenant.id)
        cimento = dados["insumos"][0]
        self.assertEqual((cimento["orcado_qtd"], cimento["aplicado_qtd"]), ("1000.000", "600.000"))
        self.assertEqual(cimento["consumido_pct"], "60.0")
        # 50% feito → esperava-se 500 kg; saíram 600: 20% acima do avanço.
        self.assertEqual((cimento["esperado_qtd"], cimento["desvio_pct"]), ("500.000", "20.0"))


class ControleAPITests(ControleTestBase):
    def test_custo_e_materiais_pela_api(self):
        self._orcamento_aprovado("100000")
        self.autenticar(modules=("pdca", "orcamento"), perms=["pdca.cronograma.view"])
        resp = self.client.get(f"/api/pdca/controle/custo/?obra={self.obra.pk}")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["colunas"]["orcado"], "100000.00")
        resp = self.client.get(f"/api/pdca/controle/materiais/?obra={self.obra.pk}")
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_exige_permissao_e_obra(self):
        self.autenticar(modules=("pdca",), perms=["pdca.medicao.view"])
        self.assertEqual(self.client.get(f"/api/pdca/controle/custo/?obra={self.obra.pk}").status_code, 403)
        self.autenticar(modules=("pdca",), perms=["pdca.cronograma.view"])
        self.assertEqual(self.client.get("/api/pdca/controle/custo/").status_code, 400)

    def test_controle_saiu_do_orcamento(self):
        self.autenticar()
        self.assertEqual(self.client.get("/api/orcamento/controle/").status_code, 404)
