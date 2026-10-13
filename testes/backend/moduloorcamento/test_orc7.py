# testes/backend/moduloorcamento/test_orc7.py
"""Testes do ORC.7 — encargos analíticos e memória do quantitativo (o reajuste foi para o contrato).

O fio comum das três peças é o mesmo do ORC.5b: **nenhuma delas quebra quando
erra**. Encargo com grupo D digitado à mão fecha uma conta plausível; parcial de
medição sem dimensão vira zero e o total continua sendo um número; fórmula de
reajuste com um peso a menos devolve um fator que parece correção monetária e é
desconto. Os três defeitos são silenciosos, então os testes daqui perseguem as
travas — não o caminho feliz.
"""
from datetime import date
from decimal import Decimal

from catalogo.models import Item

from moduloorcamento import encargos, insumos, quantitativos, services
from nucleo.models import IndiceEconomico
from moduloorcamento.models import (
    ComposicaoEncargos,
    ComposicaoReferenciaItem,
    InsumoReferencia,
    ItemOrcado,
    LinhaMedicao,
    Orcamento,
    ParcelaEtapa,
    RubricaEncargos,
)
from .test_planilha import PlanilhaTestBase


class ComposicaoTestBase(PlanilhaTestBase):
    """Base para os testes que precisam de insumo **com preço**.

    O preço não mora no `catalogo.Item` — vem da publicação, pelo par
    (fonte, código na fonte) que a adoção grava. Montar o cenário pelo caminho
    real é o que faz estes testes exercitarem a explosão de verdade em vez de um
    atalho que só existe na suíte.
    """

    def _composicao(self, codigo, descricao, unidade, insumos_refs):
        """Cria a composição na base e a adota no catálogo do tenant."""
        composicao = self._ref(
            self.base, codigo=codigo, descricao=descricao, unidade=unidade,
            tipo=InsumoReferencia.Tipo.COMPOSICAO, custo="0",
        )
        for referencia, coeficiente in insumos_refs:
            ComposicaoReferenciaItem.objects.create(
                composicao=composicao, filho=referencia, coeficiente=Decimal(coeficiente),
            )
        return services.adotar_no_catalogo(composicao, self.tenant.id)


# ---------------------------------------------------------------------------
# Encargos sociais analíticos
# ---------------------------------------------------------------------------


class QuadroDeEncargosTests(PlanilhaTestBase):
    """O grupo D é derivado — é a razão de o quadro existir."""

    def setUp(self):
        super().setUp()
        self.orcamento = self._orcamento()

    def test_quadro_de_partida_traz_os_quatro_grupos(self):
        quadro = encargos.criar_quadro_padrao(self.orcamento)
        grupos = set(
            RubricaEncargos.objects.filter(composicao=quadro).values_list("grupo", flat=True)
        )
        self.assertEqual(grupos, {"A", "B", "C", "D"})

    def test_grupo_d_e_calculado_e_nao_aceito_digitado(self):
        """A×B/100 sai da conta, mesmo que alguém grave outro número na rubrica."""
        quadro = encargos.criar_quadro_padrao(self.orcamento)
        d1 = RubricaEncargos.objects.get(
            composicao=quadro, base_calculo=RubricaEncargos.BaseCalculo.A_SOBRE_B
        )
        d1.percentual = Decimal("999")
        d1.save()

        encargos.salvar_encargos(quadro)
        quadro.refresh_from_db()
        d1.refresh_from_db()

        esperado = (quadro.total_grupo_a * quadro.total_grupo_b / Decimal("100")).quantize(
            Decimal("0.0001")
        )
        self.assertEqual(d1.percentual, esperado)
        self.assertNotEqual(d1.percentual, Decimal("999"))

    def test_total_e_a_soma_dos_quatro_grupos(self):
        quadro = encargos.criar_quadro_padrao(self.orcamento)
        quadro.refresh_from_db()
        self.assertEqual(
            quadro.percentual_calculado,
            quadro.total_grupo_a + quadro.total_grupo_b
            + quadro.total_grupo_c + quadro.total_grupo_d,
        )

    def test_desonerado_nao_traz_a_cpp_nem_zerada(self):
        """Ausência, não zero: uma linha 'INSS 0,00%' alegaria contribuição apurada."""
        quadro = encargos.criar_quadro_padrao(
            self.orcamento, regime=ComposicaoEncargos.Regime.DESONERADO
        )
        codigos = set(
            RubricaEncargos.objects.filter(composicao=quadro, grupo="A")
            .values_list("codigo", flat=True)
        )
        self.assertNotIn("A1", codigos)
        self.assertIn("A8", codigos)  # FGTS continua — desoneração é da CPP

    def test_mensalista_tem_grupo_b_menor_que_o_horista(self):
        """O salário do mês já contém repouso e feriado — somá-los pagaria duas vezes."""
        horista = encargos.criar_quadro_padrao(
            self.orcamento, tipo=ComposicaoEncargos.TipoMaoDeObra.HORISTA
        )
        mensalista = encargos.criar_quadro_padrao(
            self.orcamento, tipo=ComposicaoEncargos.TipoMaoDeObra.MENSALISTA
        )
        horista.refresh_from_db()
        mensalista.refresh_from_db()
        self.assertLess(mensalista.total_grupo_b, horista.total_grupo_b)

    def test_padrao_propaga_para_o_cabecalho_do_orcamento(self):
        quadro = encargos.criar_quadro_padrao(self.orcamento)
        quadro.refresh_from_db()
        self.orcamento.refresh_from_db()
        self.assertEqual(
            self.orcamento.encargos_sociais_percentual,
            quadro.percentual_calculado.quantize(Decimal("0.01")),
        )

    def test_so_existe_um_padrao_por_orcamento(self):
        primeiro = encargos.criar_quadro_padrao(self.orcamento)
        segundo = encargos.criar_quadro_padrao(
            self.orcamento, tipo=ComposicaoEncargos.TipoMaoDeObra.MENSALISTA
        )
        segundo.padrao = True
        encargos.salvar_encargos(segundo)

        primeiro.refresh_from_db()
        self.assertFalse(primeiro.padrao)
        self.assertEqual(
            ComposicaoEncargos.objects.filter(orcamento=self.orcamento, padrao=True).count(), 1
        )

    def test_aliquota_negativa_e_recusada(self):
        quadro = encargos.criar_quadro_padrao(self.orcamento)
        rubrica = RubricaEncargos.objects.filter(composicao=quadro, grupo="A").first()
        rubrica.percentual = Decimal("-5")
        rubrica.save()
        with self.assertRaises(encargos.QuadroInvalido):
            encargos.calcular_encargos(quadro)

    def test_quadro_traz_a_conta_das_derivadas(self):
        """A tela mostra o campo bloqueado com a conta ao lado — sem ela não confere."""
        quadro = encargos.criar_quadro_padrao(self.orcamento)
        dados = encargos.quadro(quadro)
        grupo_d = next(g for g in dados["grupos"] if g["grupo"] == "D")
        self.assertTrue(all(r["derivada"] for r in grupo_d["rubricas"]))
        self.assertIn("×", grupo_d["rubricas"][0]["conta"])


class ResolvedorDeEncargosTests(PlanilhaTestBase):
    """Quem escolhe o percentual de cada insumo de mão de obra."""

    def setUp(self):
        super().setUp()
        self.orcamento = self._orcamento(encargos_sociais_percentual=Decimal("80"))

    def test_sem_quadro_usa_o_cabecalho(self):
        """O caminho de quem não detalhou continua exatamente como antes do ORC.7."""
        resolvedor = encargos.ResolvedorEncargos(self.orcamento)
        self.assertEqual(resolvedor.percentual("H"), Decimal("80"))
        self.assertFalse(resolvedor.detalhado)

    def test_unidade_mes_puxa_o_quadro_do_mensalista(self):
        encargos.criar_quadro_padrao(self.orcamento, tipo=ComposicaoEncargos.TipoMaoDeObra.HORISTA)
        mensal = encargos.criar_quadro_padrao(
            self.orcamento, tipo=ComposicaoEncargos.TipoMaoDeObra.MENSALISTA
        )
        mensal.refresh_from_db()

        resolvedor = encargos.ResolvedorEncargos(self.orcamento)
        self.assertEqual(resolvedor.percentual("MES"), mensal.percentual_calculado)
        self.assertNotEqual(resolvedor.percentual("H"), mensal.percentual_calculado)

    def test_fator_e_um_mais_a_fracao(self):
        resolvedor = encargos.ResolvedorEncargos(self.orcamento)
        self.assertEqual(resolvedor.fator("H"), Decimal("1.8"))


class EncargosNaExplosaoTests(ComposicaoTestBase):
    """O quadro tem de chegar ao custo do insumo — senão é decoração."""

    def setUp(self):
        super().setUp()
        self.base = self._base()
        self.orcamento = self._orcamento(
            base_referencial=self.base, encargos_sociais_percentual=Decimal("0"),
        )
        pedreiro = self._ref(
            self.base, codigo="88309", descricao="PEDREIRO", unidade="H", custo="100",
        )
        self.servico = self._composicao("92873", "ALVENARIA", "M2", [(pedreiro, "1")])
        self.linha = ItemOrcado.objects.create(
            tenant=self.tenant, orcamento=self.orcamento, item=self.servico,
            descricao="ALVENARIA", unidade="M2", quantidade=Decimal("1"),
        )

    def test_sem_quadro_o_custo_e_o_do_cabecalho(self):
        from moduloorcamento import precificacao

        precificacao.explodir_item(self.linha)
        self.linha.refresh_from_db()
        self.assertEqual(self.linha.custo_unitario, Decimal("100.0000"))

    def test_com_quadro_o_custo_da_mao_de_obra_sobe(self):
        quadro = encargos.criar_quadro_padrao(self.orcamento)
        quadro.refresh_from_db()

        from moduloorcamento import precificacao

        precificacao.explodir_item(self.linha)
        self.linha.refresh_from_db()

        esperado = (Decimal("100") * (1 + quadro.percentual_calculado / 100)).quantize(
            Decimal("0.0001")
        )
        self.assertEqual(self.linha.custo_unitario, esperado)
        self.assertGreater(self.linha.custo_unitario, Decimal("100"))


# ---------------------------------------------------------------------------
# Memória do quantitativo
# ---------------------------------------------------------------------------


class FormulaTests(PlanilhaTestBase):
    """A fórmula é AST restrita — não há nome nem chamada na lista de nós."""

    def test_aritmetica_com_virgula_decimal(self):
        self.assertEqual(
            quantitativos.avaliar_formula("(3,5*2,8)-0,8*2,1"), Decimal("8.12")
        )

    def test_decimal_e_nao_float(self):
        """0.1+0.2 em ponto flutuante é 0.30000000000000004 — cauda vira centavo."""
        self.assertEqual(quantitativos.avaliar_formula("0,1+0,2"), Decimal("0.3"))

    def test_nome_e_chamada_sao_recusados(self):
        for expressao in ("__import__('os')", "a*2", "open('x')", "1 if 1 else 2"):
            with self.assertRaises(quantitativos.FormulaInvalida):
                quantitativos.avaliar_formula(expressao)

    def test_divisao_por_zero_e_erro_de_dominio(self):
        with self.assertRaises(quantitativos.FormulaInvalida):
            quantitativos.avaliar_formula("10/0")

    def test_vazia_e_recusada(self):
        with self.assertRaises(quantitativos.FormulaInvalida):
            quantitativos.avaliar_formula("   ")


class LinhaMedicaoTests(PlanilhaTestBase):
    def setUp(self):
        super().setUp()
        self.orcamento = self._orcamento()
        self.linha = self._linha(self.orcamento, "Alvenaria", quantidade="0", custo="50")

    def _parcial(self, **kwargs):
        dados = {
            "tenant": self.tenant, "item_orcado": self.linha,
            "repeticoes": Decimal("1"),
        }
        dados.update(kwargs)
        return quantitativos.salvar_linha(LinhaMedicao(**dados))

    def test_n_vezes_dimensoes(self):
        parcial = self._parcial(
            descricao="Parede eixo B", repeticoes=Decimal("2"),
            comprimento=Decimal("3.5"), largura=Decimal("2.8"),
        )
        self.assertEqual(parcial.total, Decimal("19.6000"))

    def test_dimensao_ausente_nao_zera_a_contagem(self):
        """`n = 12 unidades` sem a/b/c precisa dar 12, não 0."""
        parcial = self._parcial(descricao="Blocos", repeticoes=Decimal("12"))
        self.assertEqual(parcial.total, Decimal("12.0000"))

    def test_subtracao_e_sinal_e_nao_numero_negativo(self):
        parcial = self._parcial(
            descricao="Vão de porta", sinal=LinhaMedicao.Sinal.SUBTRACAO,
            comprimento=Decimal("0.8"), altura=Decimal("2.1"),
        )
        self.assertEqual(parcial.total, Decimal("-1.6800"))
        self.assertEqual(parcial.comprimento, Decimal("0.8"))  # guardado positivo

    def test_formula_manda_sobre_as_dimensoes(self):
        parcial = self._parcial(
            repeticoes=Decimal("99"), comprimento=Decimal("99"), formula="2*3",
        )
        self.assertEqual(parcial.total, Decimal("6.0000"))

    def test_soma_das_parciais_vira_a_quantidade_da_linha(self):
        self._parcial(repeticoes=Decimal("2"), comprimento=Decimal("3.5"), largura=Decimal("2.8"))
        self._parcial(
            sinal=LinhaMedicao.Sinal.SUBTRACAO,
            comprimento=Decimal("0.8"), altura=Decimal("2.1"),
        )
        self.linha.refresh_from_db()
        self.assertEqual(self.linha.quantidade, Decimal("17.9200"))

    def test_apagar_a_ultima_parcial_nao_zera_a_quantidade(self):
        """Remover a memória é 'desisti de detalhar', não 'o serviço sumiu'."""
        parcial = self._parcial(repeticoes=Decimal("5"))
        self.linha.refresh_from_db()
        self.assertEqual(self.linha.quantidade, Decimal("5.0000"))

        parcial.delete()
        quantitativos.sincronizar_quantidade(self.linha)
        self.linha.refresh_from_db()
        self.assertEqual(self.linha.quantidade, Decimal("5.0000"))

    def test_linha_sintetica_nao_aceita_medicao(self):
        grupo = self._linha(
            self.orcamento, "Estrutura", tipo=ItemOrcado.TipoLinha.SINTETICO,
        )
        with self.assertRaises(quantitativos.MedicaoInvalida):
            quantitativos.salvar_linha(
                LinhaMedicao(tenant=self.tenant, item_orcado=grupo, repeticoes=Decimal("1"))
            )

    def test_teto_de_parciais_vem_do_payment(self):
        from payment.planos import ORCAMENTO_TETO_LINHAS_MEDICAO_POR_ITEM

        LinhaMedicao.objects.bulk_create([
            LinhaMedicao(
                tenant=self.tenant, item_orcado=self.linha,
                repeticoes=Decimal("1"), total=Decimal("1"), ordem=i,
            )
            for i in range(ORCAMENTO_TETO_LINHAS_MEDICAO_POR_ITEM)
        ])
        with self.assertRaises(quantitativos.MedicaoInvalida):
            self._parcial(repeticoes=Decimal("1"))

    def test_memoria_separa_somado_de_subtraido(self):
        """Parede com 0 m² de vão é planilha que esqueceu as portas."""
        self._parcial(repeticoes=Decimal("2"), comprimento=Decimal("50"))
        self._parcial(sinal=LinhaMedicao.Sinal.SUBTRACAO, comprimento=Decimal("40"))
        memoria = quantitativos.memoria_do_quantitativo(self.linha)
        self.assertEqual(memoria["total_somado"], "100.0000")
        self.assertEqual(memoria["total_subtraido"], "-40.0000")
        self.assertTrue(memoria["confere"])
        self.assertTrue(memoria["derivada"])

    def test_cobertura_e_ponderada_por_valor_e_nao_por_contagem(self):
        """Dez itens baratos medidos não cobrem o item que concentra o custo."""
        caro = self._linha(self.orcamento, "Estrutura", quantidade="1", custo="9000")
        for _ in range(3):
            self._linha(self.orcamento, "Item barato", quantidade="1", custo="10")

        from moduloorcamento import planilha as servico_planilha

        quantitativos.salvar_linha(
            LinhaMedicao(tenant=self.tenant, item_orcado=caro, repeticoes=Decimal("1"))
        )
        servico_planilha.recalcular_orcamento(self.orcamento)

        cobertura = quantitativos.cobertura_do_orcamento(self.orcamento)
        self.assertGreater(Decimal(cobertura["cobertura_pct"]), Decimal("90"))
        self.assertEqual(cobertura["linhas_com_memoria"], 1)


# ---------------------------------------------------------------------------
# Relação de insumos e curva ABC de insumos
# ---------------------------------------------------------------------------


class RelacaoDeInsumosTests(ComposicaoTestBase):
    """O insumo consolidado é o que a curva de serviços não mostra."""

    def setUp(self):
        super().setUp()
        self.base = self._base()
        self.orcamento = self._orcamento(
            base_referencial=self.base, encargos_sociais_percentual=Decimal("0"),
        )
        ref_aco = self._ref(
            self.base, codigo="00000043", descricao="ACO CA-50", unidade="KG", custo="10",
        )
        # O mesmo aço em dois serviços diferentes: é o caso que a curva ABC de
        # serviços dilui e a de insumos revela.
        for codigo, nome, coeficiente, quantidade in (
            ("92873", "Pilares", "5", "10"), ("92874", "Vigas", "3", "20"),
        ):
            servico = self._composicao(codigo, nome, "M3", [(ref_aco, coeficiente)])
            linha = ItemOrcado.objects.create(
                tenant=self.tenant, orcamento=self.orcamento, item=servico,
                descricao=nome, unidade="M3", quantidade=Decimal(quantidade),
                etapa=self.estrutura,
            )
            from moduloorcamento import precificacao

            precificacao.explodir_item(linha)

        self.aco = Item.objects.get(tenant=self.tenant, codigo_referencia="00000043")

        from moduloorcamento import planilha as servico_planilha

        servico_planilha.recalcular_orcamento(self.orcamento)

    def test_o_mesmo_insumo_entra_uma_vez_somado(self):
        """5×10 + 3×20 = 110 kg — que é o que a compra precisa saber."""
        relacao = insumos.relacao_de_insumos(self.orcamento)
        aco = next(i for i in relacao["itens"] if i["item"] == self.aco.pk)
        self.assertEqual(Decimal(aco["quantidade"]), Decimal("110.0000"))
        self.assertEqual(aco["servicos"], 2)

    def test_relacao_leva_o_codigo_da_fonte(self):
        """Sem o código SINAPI, nem o comprador acha nem o analista confere."""
        relacao = insumos.relacao_de_insumos(self.orcamento)
        aco = next(i for i in relacao["itens"] if i["item"] == self.aco.pk)
        self.assertEqual(aco["codigo_referencia"], "00000043")
        self.assertEqual(aco["fonte_referencia"], "sinapi")

    def test_filtro_por_categoria(self):
        relacao = insumos.relacao_de_insumos(self.orcamento, categoria="mao_de_obra")
        self.assertEqual(relacao["itens"], [])

    def test_cobertura_declarada_mesmo_quando_e_total(self):
        relacao = insumos.relacao_de_insumos(self.orcamento)
        self.assertIn("cobertura_pct", relacao)
        self.assertEqual(relacao["linhas_sem_composicao"], 0)

    def test_cobertura_cai_quando_ha_linha_nao_explodida(self):
        self._linha(self.orcamento, "Serviço digitado", quantidade="1", custo="100000")

        from moduloorcamento import planilha as servico_planilha

        servico_planilha.recalcular_orcamento(self.orcamento)
        relacao = insumos.relacao_de_insumos(self.orcamento)
        self.assertEqual(relacao["linhas_sem_composicao"], 1)
        self.assertLess(Decimal(relacao["cobertura_pct"]), Decimal("50"))

    def test_curva_abc_de_insumos_usa_a_convencao_do_sil(self):
        """Classe decidida pela acumulada ANTES do item — o maior é sempre A."""
        curva = insumos.curva_abc_insumos(self.orcamento)
        self.assertEqual(curva["itens"][0]["classe"], "A")
        self.assertEqual(
            sum(int(v["itens"]) for v in curva["resumo"].values()), len(curva["itens"])
        )

    def test_composicao_da_linha_separa_as_tres_naturezas(self):
        linha = ItemOrcado.objects.filter(orcamento=self.orcamento, descricao="Pilares").first()
        dados = insumos.composicao_por_natureza(linha)
        categorias = {g["categoria"] for g in dados["grupos"]}
        self.assertEqual(categorias, {"material"})
        self.assertTrue(dados["confere_com_a_linha"])

    def test_resumo_por_natureza_com_corte_de_etapa(self):
        resumo = insumos.resumo_por_natureza(self.orcamento, por_etapa=True)
        self.assertEqual(len(resumo["etapas"]), 1)
        self.assertEqual(resumo["etapas"][0]["etapa"], self.estrutura.pk)


class DesembolsoPorInsumoTests(ComposicaoTestBase):
    """A curva do insumo é herdada da etapa — o módulo não fabrica planejamento."""

    def setUp(self):
        super().setUp()
        self.base = self._base()
        self.orcamento = self._orcamento(
            base_referencial=self.base, encargos_sociais_percentual=Decimal("0"),
        )
        ref_cimento = self._ref(
            self.base, codigo="1379", descricao="CIMENTO", unidade="KG", custo="1",
        )
        servico = self._composicao("92873", "CONCRETO", "M3", [(ref_cimento, "100")])
        self.linha = ItemOrcado.objects.create(
            tenant=self.tenant, orcamento=self.orcamento, item=servico,
            descricao="CONCRETO", unidade="M3", quantidade=Decimal("10"),
            etapa=self.estrutura,
        )
        from moduloorcamento import planilha as servico_planilha, precificacao

        precificacao.explodir_item(self.linha)
        servico_planilha.recalcular_orcamento(self.orcamento)

    def test_insumo_sem_cronograma_fica_fora_da_grade(self):
        """Jogá-lo no primeiro mês fabricaria compra que ninguém planejou."""
        from moduloorcamento import cronograma as controle

        dados = controle.desembolso_por_insumo(self.orcamento)
        self.assertEqual(dados["insumos"], [])
        self.assertEqual(len(dados["sem_distribuicao"]), 1)
        self.assertIn("fora da grade", dados["nota_sem_distribuicao"])

    def test_distribuicao_herda_o_percentual_da_etapa(self):
        from moduloorcamento import cronograma as controle

        for competencia, percentual in ((date(2026, 9, 1), "60"), (date(2026, 10, 1), "40")):
            ParcelaEtapa.objects.create(
                # A linha é de 1º nível, então é ela mesma a etapa do orçamento.
                tenant=self.tenant, orcamento=self.orcamento, grupo=self.linha,
                competencia=competencia, percentual=Decimal(percentual),
            )

        dados = controle.desembolso_por_insumo(self.orcamento)
        self.assertEqual(len(dados["insumos"]), 1)
        cimento = dados["insumos"][0]
        self.assertEqual(Decimal(cimento["meses"]["2026-09-01"]["quantidade"]), Decimal("600.0000"))
        self.assertEqual(Decimal(cimento["meses"]["2026-10-01"]["quantidade"]), Decimal("400.0000"))
        self.assertEqual(dados["sem_distribuicao"], [])


# ---------------------------------------------------------------------------
# O seam com o SCM
# ---------------------------------------------------------------------------


class DemandaDoOrcamentoTests(ComposicaoTestBase):
    """A compra que nasce da planilha — o elo que faltava no laço."""

    def setUp(self):
        super().setUp()
        self.base = self._base()
        self.orcamento = self._orcamento(
            base_referencial=self.base, encargos_sociais_percentual=Decimal("0"),
        )
        self.ref_cimento = self._ref(
            self.base, codigo="1379", descricao="CIMENTO", unidade="KG", custo="1",
        )
        servico = self._composicao("92873", "CONCRETO", "M3", [(self.ref_cimento, "100")])
        self.linha = ItemOrcado.objects.create(
            tenant=self.tenant, orcamento=self.orcamento, item=servico,
            descricao="CONCRETO", unidade="M3", quantidade=Decimal("10"),
        )
        self.cimento = Item.objects.get(tenant=self.tenant, codigo_referencia="1379")

    def test_demanda_nasce_rascunho_com_a_quantidade_consolidada(self):
        from moduloscm.do_orcamento import demanda_do_orcamento
        from moduloscm.models import Demanda, ItemDemanda

        from moduloorcamento import planilha as servico_planilha, precificacao

        precificacao.explodir_item(self.linha)
        servico_planilha.recalcular_orcamento(self.orcamento)

        resultado = demanda_do_orcamento(self.orcamento)
        demanda = Demanda.objects.get(pk=resultado["demanda"])
        item = ItemDemanda.objects.get(demanda=demanda)

        self.assertEqual(demanda.status, Demanda.Status.RASCUNHO)
        self.assertEqual(item.produto_id, self.cimento.pk)
        self.assertEqual(item.quantidade, Decimal("1000.000"))

    def test_linha_ainda_nao_explodida_e_aberta_sozinha_sem_mexer_no_preco(self):
        """Sem ida e volta (dono, 10/10/2026): o Suprimentos abre a composição
        que faltava, e o preço que o orçamentista fechou continua o dele."""
        from moduloscm.do_orcamento import demanda_do_orcamento
        from moduloscm.models import ItemDemanda

        self.linha.custo_unitario = Decimal("777")
        self.linha.save(update_fields=["custo_unitario"])
        resultado = demanda_do_orcamento(self.orcamento)
        item = ItemDemanda.objects.get(demanda_id=resultado["demanda"])
        self.assertEqual(item.produto_id, self.cimento.pk)
        self.assertEqual(item.quantidade, Decimal("1000.000"))
        self.linha.refresh_from_db()
        self.assertEqual(self.linha.custo_unitario, Decimal("777"))

    def test_orcamento_sem_composicao_no_catalogo_e_recusado(self):
        from catalogo.models import ComponenteComposicao
        from moduloscm.do_orcamento import GeracaoInvalida, demanda_do_orcamento

        ComponenteComposicao.objects.filter(item_pai=self.linha.item).delete()
        with self.assertRaises(GeracaoInvalida):
            demanda_do_orcamento(self.orcamento)

    def test_mao_de_obra_nao_vira_compra(self):
        """RFQ pedindo preço de 'PEDREIRO (H)' é o que isso evita."""
        from catalogo.models import ComponenteComposicao

        ref_pedreiro = self._ref(
            self.base, codigo="88309", descricao="PEDREIRO", unidade="H", custo="30",
        )
        pedreiro = services.adotar_no_catalogo(ref_pedreiro, self.tenant.id)
        ComponenteComposicao.objects.create(
            tenant=self.tenant, item_pai=self.linha.item, item_filho=pedreiro,
            coeficiente=Decimal("8"),
        )

        from moduloscm.do_orcamento import demanda_do_orcamento
        from moduloscm.models import ItemDemanda

        from moduloorcamento import planilha as servico_planilha, precificacao

        precificacao.explodir_item(self.linha)
        servico_planilha.recalcular_orcamento(self.orcamento)

        resultado = demanda_do_orcamento(self.orcamento)
        descricoes = set(
            ItemDemanda.objects.filter(demanda_id=resultado["demanda"]).values_list(
                "produto__descricao", flat=True
            )
        )
        self.assertEqual(descricoes, {"CIMENTO"})

    def test_resultado_carrega_a_cobertura(self):
        from moduloscm.do_orcamento import demanda_do_orcamento

        from moduloorcamento import planilha as servico_planilha, precificacao

        precificacao.explodir_item(self.linha)
        self._linha(self.orcamento, "Serviço digitado", quantidade="1", custo="10000")
        servico_planilha.recalcular_orcamento(self.orcamento)

        resultado = demanda_do_orcamento(self.orcamento)
        self.assertLess(Decimal(resultado["cobertura_pct"]), Decimal("100"))
        self.assertIn("não foi explodido não entrou", resultado["nota_cobertura"])


# ---------------------------------------------------------------------------
# Peças de documento
# ---------------------------------------------------------------------------


class ValorPorExtensoTests(PlanilhaTestBase):
    """Em divergência com o algarismo, o extenso é que prevalece."""

    def test_casos_do_dominio(self):
        from moduloorcamento.exportacao import valor_por_extenso

        casos = {
            Decimal("0"): "zero real",
            Decimal("1"): "um real",
            Decimal("100"): "cem reais",
            Decimal("1000"): "mil reais",
            Decimal("2500"): "dois mil e quinhentos reais",
            Decimal("1000000"): "um milhão de reais",
            Decimal("1234.56"): "mil duzentos e trinta e quatro reais e cinquenta e seis centavos",
        }
        for valor, esperado in casos.items():
            self.assertEqual(valor_por_extenso(valor), esperado, f"falhou em {valor}")


class TasksDeManutencaoTests(PlanilhaTestBase):
    """A varredura devolve relatório — job que só loga é job que ninguém lê."""

    def test_base_atrasada_aparece_no_relatorio(self):
        from moduloorcamento.models import BaseReferencial, Fonte
        from moduloorcamento.tasks import verificar_bases_desatualizadas

        BaseReferencial.objects.create(
            fonte=Fonte.SINAPI, uf="SP", mes_referencia=date(2026, 1, 1), ativa=True,
        )
        relatorio = verificar_bases_desatualizadas(referencia="2026-08-01")
        self.assertEqual(len(relatorio["atrasadas"]), 1)
        self.assertEqual(relatorio["atrasadas"][0]["meses_de_atraso"], 7)

    def test_indice_sem_serie_e_reportado_a_parte(self):
        from moduloorcamento.tasks import verificar_indices_desatualizados

        IndiceEconomico.objects.create(codigo="IGP-M", nome="IGP-M (FGV)")
        relatorio = verificar_indices_desatualizados(referencia="2026-08-01")
        self.assertEqual([i["codigo"] for i in relatorio["sem_serie"]], ["IGP-M"])
