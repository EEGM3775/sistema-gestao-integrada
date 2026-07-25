# backend/moduloorcamento/test_precificacao.py
"""Testes do ORC.2 — composição analítica, encargos, BDI e curva ABC.

O teste que mais importa aqui é o da **fórmula do BDI**: ela é a diferença
entre o preço que fecha a obra e o preço que dá prejuízo, e o erro clássico
(somar os tributos em vez de dividir por 1−I) produz um número plausível — não
quebra nada, só empobrece a empresa.

Por isso a fórmula é checada por dois ângulos independentes do código: a
**aritmética conferida à mão** (com a conta escrita no docstring do teste, para
quem revisar poder refazê-la) e a **faixa publicada pelo acórdão** para
edificações, que um cálculo errado não acerta por acaso.
"""
from decimal import Decimal

from catalogo.models import ComponenteComposicao, Item
from modulosil.models import LocalEstoque, MovimentacaoEstoque, SaldoEstoque
from moduloscm.models import ItemPedido, PedidoCompra
from fornecedores.models import Fornecedor

from . import planilha, precificacao, services
from .models import ComposicaoBDI, ItemOrcado, ItemOrcadoInsumo
from .test_planilha import PlanilhaTestBase


class CalculoDoBDITests(PlanilhaTestBase):
    """Fórmula do Acórdão 2622/2013-TCU."""

    def _bdi(self, **kwargs):
        # O orçamento default é criado sob demanda: instanciá-lo no dicionário
        # criaria uma v1 extra da mesma obra mesmo quando o teste passa a sua,
        # esbarrando no unique (obra, versao).
        dados = {
            "administracao_central": Decimal("4.00"), "seguro": Decimal("0.80"),
            "risco": Decimal("1.27"), "garantia": Decimal("0.40"),
            "despesas_financeiras": Decimal("1.23"), "lucro": Decimal("7.40"),
            "pis": Decimal("0.65"), "cofins": Decimal("3.00"), "iss": Decimal("5.00"),
        }
        dados.update(kwargs)
        if "orcamento" not in dados:  # criado só quando o teste não passa o seu
            dados["orcamento"] = self._orcamento()
        return ComposicaoBDI(tenant=self.tenant, **dados)

    def test_formula_do_acordao_confere_com_a_aritmetica(self):
        """AC 4,00 · S 0,80 · R 1,27 · G 0,40 · DF 1,23 · L 7,40 · I 8,65
        (PIS 0,65 + COFINS 3,00 + ISS 5,00):

            (1 + 0,0647) × 1,0123 × 1,0740 / (1 − 0,0865) − 1
            = 1,157551 / 0,9135 − 1 = 0,267162 → **26,7162%**
        """
        percentual = precificacao.calcular_bdi(self._bdi())
        self.assertEqual(percentual, Decimal("26.7162"))

    def test_parametros_medianos_caem_na_faixa_do_acordao(self):
        """O acórdão publica faixa de referência por tipo de obra; para
        *construção de edifícios* é 20,34% – 25,00% (mediana 22,12%).

        Com as parcelas medianas e ISS de 2% — alíquota municipal comum — o
        resultado cai dentro da faixa. Serve de sanidade: uma fórmula com o
        erro clássico (somar os tributos) sairia dela.
        """
        percentual = precificacao.calcular_bdi(self._bdi(iss=Decimal("2.00")))
        self.assertGreater(percentual, Decimal("20.34"))
        self.assertLess(percentual, Decimal("25.00"))

    def test_tributos_dividem_e_nao_somam(self):
        """O erro clássico de planilha: somar I subestimaria o BDI.

        Com as mesmas parcelas, somar daria ~15,10% + 8,65% = 23,75% de forma
        aditiva ingênua; a fórmula correta separa custo de faturamento e dá um
        resultado que NÃO é a soma das partes.
        """
        composicao = self._bdi()
        com_tributos = precificacao.calcular_bdi(composicao)

        composicao.pis = composicao.cofins = composicao.iss = Decimal("0")
        sem_tributos = precificacao.calcular_bdi(composicao)

        self.assertGreater(com_tributos, sem_tributos)
        # Se os tributos apenas somassem, a diferença seria exatamente 8,65 —
        # ela é maior, porque a alíquota incide sobre o preço, não sobre o custo.
        self.assertGreater(
            (com_tributos - sem_tributos).quantize(Decimal("0.01")), Decimal("8.65")
        )

    def test_tributos_de_cem_por_cento_sao_recusados(self):
        composicao = self._bdi(iss=Decimal("96.35"))  # total = 100%
        with self.assertRaises(precificacao.ComposicaoInvalida):
            precificacao.calcular_bdi(composicao)

    def test_bdi_padrao_propaga_para_o_orcamento_e_para_o_total(self):
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="10", custo="400")
        composicao = self._bdi(orcamento=orc)
        precificacao.salvar_bdi(composicao)
        planilha.recalcular_orcamento(orc)
        orc.refresh_from_db()

        self.assertEqual(orc.bdi_percentual, Decimal("26.72"))
        self.assertEqual(orc.custo_direto_total, Decimal("4000.00"))
        self.assertEqual(orc.valor_total, Decimal("5068.80"))

    def test_so_um_bdi_padrao_por_orcamento(self):
        orc = self._orcamento()
        primeiro = precificacao.salvar_bdi(self._bdi(orcamento=orc, nome="Serviços"))
        precificacao.salvar_bdi(self._bdi(orcamento=orc, nome="Equipamentos", lucro=Decimal("5.00")))

        primeiro.refresh_from_db()
        self.assertFalse(primeiro.padrao)
        self.assertEqual(ComposicaoBDI.objects.filter(orcamento=orc, padrao=True).count(), 1)

    def test_bdi_diferenciado_na_linha_vence_o_padrao(self):
        """TCU admite BDI próprio p/ fornecimento de equipamento."""
        orc = self._orcamento()
        padrao = precificacao.salvar_bdi(self._bdi(orcamento=orc, nome="Serviços"))
        equipamentos = self._bdi(
            orcamento=orc, nome="Equipamentos", padrao=False,
            administracao_central=Decimal("1.50"), risco=Decimal("0.50"),
            garantia=Decimal("0"), seguro=Decimal("0"),
            despesas_financeiras=Decimal("0.59"), lucro=Decimal("3.83"),
        )
        precificacao.salvar_bdi(equipamentos)

        self._linha(orc, "Serviço", quantidade="1", custo="1000", ordem=1)
        elevador = self._linha(orc, "Elevador", quantidade="1", custo="1000", ordem=2)
        ItemOrcado.objects.filter(pk=elevador.pk).update(bdi=equipamentos)
        planilha.recalcular_orcamento(orc)

        elevador.refresh_from_db()
        servico = ItemOrcado.objects.get(orcamento=orc, descricao="Serviço")
        self.assertGreater(servico.total_com_bdi, elevador.total_com_bdi)
        self.assertEqual(padrao.percentual_calculado, Decimal("26.7162"))


class ExplosaoDaComposicaoTests(PlanilhaTestBase):
    """A memória de cálculo — o que separa analítico de lista de preços."""

    def setUp(self):
        super().setUp()
        self.base = self._base()
        # Composição SINAPI-like: concretagem = cimento + servente.
        self.ref_cimento = self._ref(self.base, codigo="1379", descricao="CIMENTO CP II-32",
                                     unidade="KG", custo="0.58")
        self.ref_servente = self._ref(self.base, codigo="88309", descricao="SERVENTE",
                                      unidade="H", custo="19.42")
        self.ref_concretagem = self._ref(
            self.base, codigo="92873", descricao="CONCRETAGEM DE PILARES", unidade="M3",
            tipo=self.ref_cimento.Tipo.COMPOSICAO, custo="0",
        )
        from .models import ComposicaoReferenciaItem
        ComposicaoReferenciaItem.objects.create(
            composicao=self.ref_concretagem, filho=self.ref_cimento, coeficiente=Decimal("350"),
        )
        ComposicaoReferenciaItem.objects.create(
            composicao=self.ref_concretagem, filho=self.ref_servente, coeficiente=Decimal("2.5"),
        )
        self.item = services.adotar_no_catalogo(self.ref_concretagem, self.tenant.id)

    def test_explosao_calcula_custo_a_partir_dos_insumos(self):
        orc = self._orcamento(base_referencial=self.base)
        linha = services.linha_a_partir_do_item(orcamento=orc, item=self.item, quantidade="10")

        precificacao.explodir_item(linha)
        linha.refresh_from_db()

        # 350 × 0,58 = 203,00 · 2,5 × 19,42 = 48,55 → 251,55
        self.assertEqual(linha.custo_unitario, Decimal("251.5500"))
        self.assertEqual(ItemOrcadoInsumo.objects.filter(item_orcado=linha).count(), 2)

    def test_encargos_incidem_so_sobre_mao_de_obra(self):
        """Com 80% de encargos: servente sobe, cimento não."""
        orc = self._orcamento(base_referencial=self.base,
                              encargos_sociais_percentual=Decimal("80.00"))
        linha = services.linha_a_partir_do_item(orcamento=orc, item=self.item, quantidade="10")
        precificacao.explodir_item(linha)

        insumos = {i.descricao: i for i in ItemOrcadoInsumo.objects.filter(item_orcado=linha)}
        cimento = insumos["CIMENTO CP II-32"]
        servente = insumos["SERVENTE"]

        self.assertEqual(cimento.categoria, ItemOrcadoInsumo.Categoria.MATERIAL)
        self.assertEqual(cimento.custo_no_item, Decimal("203.0000"))
        self.assertEqual(servente.categoria, ItemOrcadoInsumo.Categoria.MAO_DE_OBRA)
        # 2,5 × 19,42 × 1,80 = 87,39
        self.assertEqual(servente.custo_no_item, Decimal("87.3900"))
        linha.refresh_from_db()
        self.assertEqual(linha.custo_unitario, Decimal("290.3900"))

    def test_composicao_aninhada_multiplica_coeficientes(self):
        """Composição auxiliar (SINAPI aninha): coeficiente da folha é o produto
        dos coeficientes no caminho."""
        estrutura = Item.objects.create(
            tenant=self.tenant, codigo_interno="EST-01", descricao="Estrutura completa",
            unidade="M3", tipo=Item.Tipo.COMPOSICAO,
        )
        ComponenteComposicao.objects.create(
            tenant=self.tenant, item_pai=estrutura, item_filho=self.item, coeficiente=Decimal("2"),
        )
        orc = self._orcamento(base_referencial=self.base)
        linha = services.linha_a_partir_do_item(orcamento=orc, item=estrutura, quantidade="1")

        precificacao.explodir_item(linha)
        insumos = {i.descricao: i for i in ItemOrcadoInsumo.objects.filter(item_orcado=linha)}

        # 2 (estrutura→concretagem) × 350 (concretagem→cimento) = 700 kg
        self.assertEqual(insumos["CIMENTO CP II-32"].coeficiente, Decimal("700.000000"))
        linha.refresh_from_db()
        self.assertEqual(linha.custo_unitario, Decimal("503.1000"))

    def test_ciclo_na_composicao_nao_trava_a_explosao(self):
        """Dado sujo (A ⊃ B ⊃ A) na base pública não pode virar recursão infinita."""
        ComponenteComposicao.objects.create(
            tenant=self.tenant, item_pai=Item.objects.get(codigo_interno="SINAPI-1379"),
            item_filho=self.item, coeficiente=Decimal("1"),
        )
        orc = self._orcamento(base_referencial=self.base)
        linha = services.linha_a_partir_do_item(orcamento=orc, item=self.item, quantidade="1")

        precificacao.explodir_item(linha)  # não pode levantar RecursionError
        self.assertGreater(ItemOrcadoInsumo.objects.filter(item_orcado=linha).count(), 0)

    def test_item_sem_composicao_e_recusado_com_mensagem_util(self):
        avulso = Item.objects.create(
            tenant=self.tenant, codigo_interno="AVULSO", descricao="Item solto", unidade="UN",
        )
        orc = self._orcamento(base_referencial=self.base)
        linha = services.linha_a_partir_do_item(orcamento=orc, item=avulso, quantidade="1")

        with self.assertRaises(precificacao.ComposicaoInvalida) as ctx:
            precificacao.explodir_item(linha)
        self.assertIn("não tem composição", str(ctx.exception))

    def test_explodir_de_novo_nao_duplica_a_memoria(self):
        orc = self._orcamento(base_referencial=self.base)
        linha = services.linha_a_partir_do_item(orcamento=orc, item=self.item, quantidade="10")
        precificacao.explodir_item(linha)
        precificacao.explodir_item(linha)
        self.assertEqual(ItemOrcadoInsumo.objects.filter(item_orcado=linha).count(), 2)

    def test_memoria_traz_peso_e_resumo_por_categoria(self):
        orc = self._orcamento(base_referencial=self.base)
        linha = services.linha_a_partir_do_item(orcamento=orc, item=self.item, quantidade="10")
        precificacao.explodir_item(linha)
        linha.refresh_from_db()

        memoria = precificacao.memoria_de_calculo(linha)
        self.assertEqual(len(memoria["insumos"]), 2)
        self.assertEqual(memoria["por_categoria"]["material"]["valor"], "203.0000")
        # 203,00 / 251,55 = 80,70%
        self.assertEqual(memoria["por_categoria"]["material"]["pct"], "80.70")

    def test_explodir_sem_atualizar_mantem_o_preco_proprio(self):
        orc = self._orcamento(base_referencial=self.base)
        linha = services.linha_a_partir_do_item(
            orcamento=orc, item=self.item, quantidade="10", custo_unitario="300.00",
        )
        precificacao.explodir_item(linha, atualizar_custo=False)
        linha.refresh_from_db()

        self.assertEqual(linha.custo_unitario, Decimal("300.0000"))
        self.assertEqual(ItemOrcadoInsumo.objects.filter(item_orcado=linha).count(), 2)


class CurvaABCDoOrcadoTests(PlanilhaTestBase):
    def test_classes_pela_acumulada_anterior(self):
        orc = self._orcamento()
        self._linha(orc, "Estrutura", quantidade="1", custo="80000", ordem=1)
        self._linha(orc, "Alvenaria", quantidade="1", custo="15000", ordem=2)
        self._linha(orc, "Pintura", quantidade="1", custo="5000", ordem=3)
        planilha.recalcular_orcamento(orc)

        curva = precificacao.curva_abc(orc)
        classes = {i["descricao"]: i["classe"] for i in curva["itens"]}

        self.assertEqual(curva["total"], "100000.00")
        # O de maior valor é sempre A, mesmo passando de 80% sozinho.
        self.assertEqual(classes["Estrutura"], "A")
        self.assertEqual(classes["Alvenaria"], "B")
        self.assertEqual(classes["Pintura"], "C")
        self.assertEqual(curva["resumo"]["A"]["pct"], "80.00")

    def test_sintetico_fica_de_fora_da_curva(self):
        orc = self._orcamento()
        grupo = self._linha(orc, "Estrutura", tipo=ItemOrcado.TipoLinha.SINTETICO, ordem=1)
        self._linha(orc, "Concreto", pai=grupo, quantidade="1", custo="1000", ordem=1)
        planilha.recalcular_orcamento(orc)

        curva = precificacao.curva_abc(orc)
        self.assertEqual([i["descricao"] for i in curva["itens"]], ["Concreto"])
        self.assertEqual(curva["total"], "1000.00")

    def test_orcamento_vazio_nao_divide_por_zero(self):
        curva = precificacao.curva_abc(self._orcamento())
        self.assertEqual(curva["total"], "0.00")
        self.assertEqual(curva["itens"], [])


class PrecoRealTests(PlanilhaTestBase):
    """A integração visível: orçar com o histórico da própria empresa."""

    def setUp(self):
        super().setUp()
        self.item = Item.objects.create(
            tenant=self.tenant, codigo_interno="CIM-01", descricao="Cimento CP II", unidade="KG",
        )
        self.fornecedor = Fornecedor.objects.create(
            tenant=self.tenant, razao_social="Fornecedor A LTDA",
            cnpj="11222333000181", email="compras@fornecedor-a.com.br",
        )

    def _pedido(self, preco, quantidade="100"):
        pedido = PedidoCompra.objects.create(
            tenant=self.tenant, fornecedor=self.fornecedor, status=PedidoCompra.Status.ENVIADO,
        )
        return ItemPedido.objects.create(
            tenant=self.tenant, pedido=pedido, produto=self.item,
            quantidade=Decimal(quantidade), preco_unitario=Decimal(preco),
        )

    def test_preco_medio_e_ultimo_do_scm(self):
        self._pedido("0.50")
        self._pedido("0.70")

        real = precificacao.preco_real_do_item(self.tenant.id, self.item.pk)
        self.assertEqual(Decimal(real["scm"]["preco_medio"]), Decimal("0.60"))
        self.assertEqual(Decimal(real["scm"]["quantidade_comprada"]), Decimal("200"))

    def test_rascunho_do_scm_nao_conta_como_historico(self):
        """Pedido em rascunho é intenção, não compra."""
        pedido = PedidoCompra.objects.create(
            tenant=self.tenant, fornecedor=self.fornecedor, status=PedidoCompra.Status.RASCUNHO,
        )
        ItemPedido.objects.create(
            tenant=self.tenant, pedido=pedido, produto=self.item,
            quantidade=Decimal("10"), preco_unitario=Decimal("99.00"),
        )
        real = precificacao.preco_real_do_item(self.tenant.id, self.item.pk)
        self.assertIsNone(real["scm"]["preco_medio"])

    def test_custo_medio_do_sil(self):
        local = LocalEstoque.objects.create(tenant=self.tenant, nome="Central")
        SaldoEstoque.objects.create(
            tenant=self.tenant, item=self.item, local=local,
            quantidade=Decimal("100"), custo_medio=Decimal("0.62"),
        )
        real = precificacao.preco_real_do_item(self.tenant.id, self.item.pk)
        self.assertEqual(Decimal(real["sil"]["custo_medio"]), Decimal("0.62"))

    def test_sem_historico_devolve_none_e_nao_zero(self):
        """'Nunca comprei' e 'comprei a R$ 0,00' são coisas diferentes."""
        real = precificacao.preco_real_do_item(self.tenant.id, self.item.pk)
        self.assertIsNone(real["scm"]["preco_medio"])
        self.assertIsNone(real["sil"]["custo_medio"])

    def test_aplicar_preco_real_troca_a_fonte_para_propria(self):
        self._pedido("0.50")
        self._pedido("0.70")
        orc = self._orcamento()
        linha = services.linha_a_partir_do_item(orcamento=orc, item=self.item, quantidade="1000")
        linha.fonte_referencia = "sinapi"
        linha.save()

        precificacao.aplicar_preco_real(linha, origem="scm")
        linha.refresh_from_db()

        self.assertEqual(linha.custo_unitario, Decimal("0.6000"))
        self.assertEqual(linha.fonte_referencia, "")
        self.assertIn("SCM", linha.observacao)

    def test_aplicar_sem_historico_e_recusado(self):
        orc = self._orcamento()
        linha = services.linha_a_partir_do_item(orcamento=orc, item=self.item, quantidade="1")
        with self.assertRaises(precificacao.ComposicaoInvalida):
            precificacao.aplicar_preco_real(linha, origem="sil")


class PrecificacaoAPITests(PlanilhaTestBase):
    def setUp(self):
        super().setUp()
        self.autenticar()

    def test_criar_bdi_pela_api_calcula_e_aplica(self):
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="10", custo="400")

        resp = self.client.post("/api/orcamento/bdi/", {
            "orcamento": orc.pk, "nome": "BDI padrão",
            "administracao_central": "4.00", "seguro": "0.80", "risco": "1.27",
            "garantia": "0.40", "despesas_financeiras": "1.23", "lucro": "7.40",
            "pis": "0.65", "cofins": "3.00", "iss": "5.00",
        }, format="json")

        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Decimal(resp.data["percentual_calculado"]), Decimal("26.7162"))
        orc.refresh_from_db()
        self.assertEqual(orc.valor_total, Decimal("5068.80"))

    def test_percentual_enviado_pelo_cliente_e_ignorado(self):
        orc = self._orcamento()
        resp = self.client.post("/api/orcamento/bdi/", {
            "orcamento": orc.pk, "lucro": "7.40", "percentual_calculado": "99.00",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Decimal(resp.data["percentual_calculado"]), Decimal("7.4000"))

    def test_curva_abc_pela_api(self):
        orc = self._orcamento()
        self._linha(orc, "Estrutura", quantidade="1", custo="80000", ordem=1)
        self._linha(orc, "Pintura", quantidade="1", custo="20000", ordem=2)
        planilha.recalcular_orcamento(orc)

        resp = self.client.get(f"/api/orcamento/orcamentos/{orc.pk}/curva-abc/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["total"], "100000.00")
        self.assertEqual(resp.data["itens"][0]["classe"], "A")

    def test_bdi_em_orcamento_aprovado_e_409(self):
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="1", custo="1")
        planilha.aprovar_orcamento(orc)

        resp = self.client.post("/api/orcamento/bdi/", {
            "orcamento": orc.pk, "lucro": "7.40",
        }, format="json")
        self.assertEqual(resp.status_code, 409, resp.content)
