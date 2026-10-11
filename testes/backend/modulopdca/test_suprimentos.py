"""O cronograma puxa a compra — `modulopdca.suprimentos`.

Orçamento (quanto), plano (quando), estoque e Suprimentos (quanto já há) numa
lista só: insumo, quantidade, chegar até, a comprar.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from catalogo.models import Item
from fornecedores.models import Fornecedor
from modulocalendar.models import Feriado
from modulopdca import services, suprimentos
from modulopdca.models import AntecedenciaDeCompra, Atividade, CalendarioTrabalho, Cronograma
from moduloorcamento.models import ItemOrcado, ItemOrcadoInsumo, Orcamento
from moduloscm.models import CentroCusto, Demanda, ItemPedido, ItemRecebimento, PedidoCompra, Recebimento
from modulosil.models import LocalEstoque, SaldoEstoque
from nucleo.models import Tenant, Usuario
from obras.models import EtapaObra, Obra


class _Cenario:
    """Obra com orçamento aprovado (alvenaria e reboco), plano com a alvenaria
    ligada ao item orçado e o reboco só pela etapa."""

    @classmethod
    def montar(cls, slug):
        cls.tenant = Tenant.objects.create(slug=slug, nome="Construtora Suprimento")
        cls.obra = Obra.objects.create(tenant=cls.tenant, nome_obra="Drenagem", endereco="Rua 1")
        cls.e1 = EtapaObra.objects.create(tenant=cls.tenant, obra=cls.obra, nome_etapa="Alvenaria", ordem=1)
        cls.e2 = EtapaObra.objects.create(tenant=cls.tenant, obra=cls.obra, nome_etapa="Reboco", ordem=2)
        cls.cimento = Item.objects.create(tenant=cls.tenant, codigo_interno="CIM", descricao="Cimento CP-II", unidade="SC")
        cls.areia = Item.objects.create(tenant=cls.tenant, codigo_interno="ARE", descricao="Areia média", unidade="M3")
        orc = Orcamento.objects.create(
            tenant=cls.tenant, obra=cls.obra, descricao="Orçamento", versao=1,
            status=Orcamento.Status.APROVADO,
        )
        cls.alvenaria = ItemOrcado.objects.create(
            tenant=cls.tenant, orcamento=orc, etapa=cls.e1, descricao="Alvenaria", codigo_eap="1.1",
            unidade="M2", quantidade=Decimal("100"),
        )
        reboco = ItemOrcado.objects.create(
            tenant=cls.tenant, orcamento=orc, etapa=cls.e2, descricao="Reboco",
            unidade="M2", quantidade=Decimal("50"),
        )
        for linha, item, coef in ((cls.alvenaria, cls.cimento, "0.2"), (cls.alvenaria, cls.areia, "0.05"),
                                  (reboco, cls.cimento, "0.1")):
            ItemOrcadoInsumo.objects.create(
                tenant=cls.tenant, item_orcado=linha, item=item, descricao=item.descricao,
                unidade=item.unidade, coeficiente=Decimal(coef), custo_unitario=Decimal("10"),
            )
        # Mão de obra não se compra: fica fora da fila.
        ItemOrcadoInsumo.objects.create(
            tenant=cls.tenant, item_orcado=cls.alvenaria, descricao="Pedreiro", unidade="H",
            categoria=ItemOrcadoInsumo.Categoria.MAO_DE_OBRA, coeficiente=Decimal("1"),
        )
        cls.calendario = CalendarioTrabalho.objects.create(tenant=cls.tenant, obra=cls.obra, nome="Comercial")

    def plano(self):
        Feriado.objects.all().delete()
        crono = Cronograma.objects.create(
            tenant=self.tenant, obra=self.obra, descricao="Plano",
            data_inicio=date(2026, 6, 1), calendario=self.calendario,
        )
        r1 = Atividade.objects.create(tenant=self.tenant, cronograma=crono, codigo="1", nome="Alvenaria",
                                      profundidade=1, etapa=self.e1, ordem=0)
        self.a11 = Atividade.objects.create(
            tenant=self.tenant, cronograma=crono, pai=r1, codigo="1.1", nome="Levantar paredes",
            profundidade=2, duracao_dias=5, item_orcado=self.alvenaria,
        )
        self.r2 = Atividade.objects.create(tenant=self.tenant, cronograma=crono, codigo="2", nome="Reboco",
                                           profundidade=1, etapa=self.e2, ordem=1)
        Atividade.objects.create(tenant=self.tenant, cronograma=crono, pai=self.r2, codigo="2.1",
                                 nome="Rebocar", profundidade=2, duracao_dias=3)
        services.calcular_cpm(crono)
        self.a11.refresh_from_db()
        self.r2.refresh_from_db()
        return crono


class NecessidadeDeMaterialTests(_Cenario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.montar("pdca-sup")

    def setUp(self):
        self.crono = self.plano()

    def _linhas(self, **filtro):
        n = suprimentos.necessidade_de_material(self.crono, hoje=date(2026, 5, 1))
        return [l for l in n["linhas"] if all(l[k] == v for k, v in filtro.items())], n

    def test_quantidade_pela_atividade_e_pela_etapa(self):
        """A alvenaria vem do item orçado ligado; o reboco, que nenhuma atividade
        cita, cai na etapa — e a mão de obra não entra."""
        cim, n = self._linhas(atividade=self.a11.pk, item=self.cimento.pk)
        self.assertEqual(cim[0]["quantidade"], "20.000")
        self.assertEqual(cim[0]["origem"], "atividade")
        are, _ = self._linhas(atividade=self.a11.pk, item=self.areia.pk)
        self.assertEqual(are[0]["quantidade"], "5.000")
        reb, _ = self._linhas(atividade=self.r2.pk)
        self.assertEqual((reb[0]["quantidade"], reb[0]["origem"]), ("5.000", "etapa"))
        self.assertFalse(any(l["categoria"] == "mao_de_obra" for l in n["linhas"]))
        self.assertEqual(n["cobertura"]["folhas_fora_da_conta"], 0)

    def test_o_executado_sai_da_conta(self):
        services.publicar(self.crono)
        services.registrar_apontamento(atividade=self.a11, percentual=Decimal("50"),
                                       data=date(2026, 6, 2), por="Teste")
        cim, _ = self._linhas(atividade=self.a11.pk, item=self.cimento.pk)
        self.assertEqual(cim[0]["restante"], "10.000")

    def test_antecedencia_atividade_vence_insumo_que_vence_obra(self):
        AntecedenciaDeCompra.objects.create(tenant=self.tenant, obra=self.obra, dias=10)
        AntecedenciaDeCompra.objects.create(tenant=self.tenant, obra=self.obra, item=self.areia, dias=3)
        inicio = self.a11.inicio_cedo
        cim, _ = self._linhas(atividade=self.a11.pk, item=self.cimento.pk)
        are, _ = self._linhas(atividade=self.a11.pk, item=self.areia.pk)
        self.assertEqual(cim[0]["chegar_ate"], (inicio - timedelta(days=10)).isoformat())
        self.assertEqual((are[0]["chegar_ate"], are[0]["antecedencia_origem"]),
                         ((inicio - timedelta(days=3)).isoformat(), "insumo"))
        Atividade.objects.filter(pk=self.a11.pk).update(antecedencia_compra_dias=1)
        are, _ = self._linhas(atividade=self.a11.pk, item=self.areia.pk)
        self.assertEqual(are[0]["antecedencia_origem"], "atividade")

    def test_sem_antecedencia_cadastrada_chega_no_inicio(self):
        cim, n = self._linhas(atividade=self.a11.pk, item=self.cimento.pk)
        self.assertIsNone(n["antecedencia_padrao"])
        self.assertEqual(cim[0]["chegar_ate"], self.a11.inicio_cedo.isoformat())
        self.assertEqual(cim[0]["antecedencia_origem"], "nenhuma")

    def test_abate_estoque_da_obra_e_pedido_em_aberto(self):
        """Cimento: precisa 25; o canteiro tem 8 livres e o pedido aberto ainda
        deve 5 (7 pedidos, 2 entregues). Os 2 entregues entram no canteiro pelo
        recebimento (a ponte Suprimentos → estoque), então faltam 25 − 10 − 5."""
        canteiro = LocalEstoque.objects.create(tenant=self.tenant, nome="Canteiro", tipo="canteiro", obra=self.obra)
        SaldoEstoque.objects.create(tenant=self.tenant, item=self.cimento, local=canteiro,
                                    quantidade=Decimal("10"), reservado=Decimal("2"))
        centro = CentroCusto.objects.create(tenant=self.tenant, nome="Drenagem", obra=self.obra)
        forn = Fornecedor.objects.create(tenant=self.tenant, razao_social="Alfa", email="a@ex.com")
        pedido = PedidoCompra.objects.create(tenant=self.tenant, fornecedor=forn, centro_custo=centro,
                                             status=PedidoCompra.Status.ENVIADO)
        ip = ItemPedido.objects.create(tenant=self.tenant, pedido=pedido, produto=self.cimento,
                                       quantidade=Decimal("7"), preco_unitario=Decimal("30"))
        rec = Recebimento.objects.create(tenant=self.tenant, pedido=pedido, tipo="parcial")
        ItemRecebimento.objects.create(tenant=self.tenant, recebimento=rec, item_pedido=ip,
                                       quantidade_recebida=Decimal("2"))
        _, n = self._linhas()
        cim = next(r for r in n["por_insumo"] if r["item"] == self.cimento.pk)
        self.assertEqual(cim["necessario"], "25.000")
        self.assertEqual(cim["em_pedido"], "5.000")
        self.assertEqual(cim["estoque"], "10.000")
        self.assertEqual(cim["a_comprar"], "10.000")

    def test_gerar_a_demanda_nao_compra_duas_vezes(self):
        criadas = suprimentos.gerar_demandas_do_plano(self.crono)
        self.assertEqual(len(criadas), 1)
        demanda = Demanda.objects.get(pk=criadas[0]["demanda"])
        self.assertEqual(demanda.origem, Demanda.Origem.PLANO)
        quantidades = {i.produto_id: i.quantidade for i in demanda.itens.all()}
        self.assertEqual(quantidades, {self.cimento.pk: Decimal("25.000"), self.areia.pk: Decimal("5.000")})
        # A obra não tinha centro de custo: nasce um, e é por ele que a segunda
        # leitura já vê a primeira demanda.
        self.assertEqual(demanda.centro_custo.obra_id, self.obra.pk)
        self.assertEqual(suprimentos.gerar_demandas_do_plano(self.crono), [])

    def test_gerar_so_o_insumo_escolhido(self):
        CentroCusto.objects.create(tenant=self.tenant, nome="Drenagem", obra=self.obra)
        criadas = suprimentos.gerar_demandas_do_plano(self.crono, insumos=[f"i{self.areia.pk}"])
        demanda = Demanda.objects.get(pk=criadas[0]["demanda"])
        self.assertEqual([i.produto_id for i in demanda.itens.all()], [self.areia.pk])
        self.assertEqual(demanda.centro_custo.obra_id, self.obra.pk)

    def test_antecedencia_atravessa_o_replanejamento(self):
        Atividade.objects.filter(pk=self.a11.pk).update(antecedencia_compra_dias=4)
        services.publicar(self.crono)
        nova = services.replanejar(self.crono, motivo="Chuva")
        self.assertEqual(nova.atividades.get(codigo="1.1").antecedencia_compra_dias, 4)


class ApiDeSuprimentosTests(_Cenario, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.montar("pdca-sup-api")
        cls.usuario = Usuario.objects.create(username="compra", tenant=cls.tenant)

    def setUp(self):
        self.crono = self.plano()
        CentroCusto.objects.create(tenant=self.tenant, nome="Drenagem", obra=self.obra)

    def _autenticar(self, permissions):
        self.usuario.iam_modules = ["pdca", "scm"]
        self.usuario.iam_permissions = list(permissions)
        self.client.force_authenticate(user=self.usuario)

    def test_quem_le_o_plano_ve_a_fila(self):
        self._autenticar(["pdca.cronograma.view"])
        r = self.client.get(f"/api/pdca/cronogramas/{self.crono.pk}/suprimentos/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["linhas"])

    def test_gerar_demanda_exige_a_permissao_de_comprar(self):
        url = f"/api/pdca/cronogramas/{self.crono.pk}/suprimentos/gerar-demanda/"
        self._autenticar(["pdca.cronograma.view"])
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 403)
        self._autenticar(["pdca.cronograma.view", "scm.demanda.edit"])
        r = self.client.post(url, {}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        # A segunda vez não há mais o que comprar.
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 400)

    def test_planejador_cadastra_a_antecedencia(self):
        self._autenticar(["pdca.cronograma.view", "pdca.cronograma.edit"])
        r = self.client.post("/api/pdca/antecedencias/", {"obra": self.obra.pk, "dias": 7}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(suprimentos.antecedencias_da_obra(self.obra.pk, tenant_id=self.tenant.pk)[0], 7)

    def test_o_suprimentos_ve_a_mesma_fila_por_insumo(self):
        """O comprador vê a fila das obras (plano vigente) e gera dali mesmo."""
        services.publicar(self.crono)
        self._autenticar(["scm.demanda.view"])
        r = self.client.get("/api/scm/demandas/do-cronograma/")
        self.assertEqual(r.status_code, 200, r.data)
        cim = next(g for g in r.data["por_insumo"] if g["item"] == self.cimento.pk)
        self.assertEqual(cim["a_comprar"], "25.000")
        self.assertEqual(cim["obras"][0]["obra"], self.obra.pk)
        self.assertEqual(self.client.post("/api/scm/demandas/do-cronograma/gerar/",
                                          {"cronograma": self.crono.pk}, format="json").status_code, 403)
        self._autenticar(["scm.demanda.view", "scm.demanda.edit"])
        r = self.client.post("/api/scm/demandas/do-cronograma/gerar/",
                             {"cronograma": self.crono.pk, "insumos": [f"i{self.cimento.pk}"]}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        r = self.client.get("/api/scm/demandas/do-cronograma/")
        self.assertFalse(any(g["item"] == self.cimento.pk for g in r.data["por_insumo"]))


class RestricaoAcompanhaACompraTests(_Cenario, TestCase):
    """A trava de material mostra a compra e sugere destravar quando chega."""

    @classmethod
    def setUpTestData(cls):
        cls.montar("pdca-sup-trava")

    def test_a_trava_segue_demanda_pedido_e_recebimento(self):
        from modulopdca.models import Restricao, TipoRestricao
        from modulopdca.serializers import RestricaoSerializer

        crono = self.plano()
        services.publicar(crono)
        r = Restricao.objects.create(tenant=self.tenant, atividade=self.a11,
                                     tipo=TipoRestricao.MATERIAL, descricao="Cimento")
        services.gerar_demanda_scm(restricao=r)
        r.refresh_from_db()
        self.assertEqual(RestricaoSerializer(r).data["compra"]["etapa"], "demanda")
        forn = Fornecedor.objects.create(tenant=self.tenant, razao_social="Alfa", email="a@ex.com")
        pedido = PedidoCompra.objects.create(tenant=self.tenant, fornecedor=forn, demanda=r.demanda_scm,
                                             status=PedidoCompra.Status.ENVIADO)
        compra = RestricaoSerializer(Restricao.objects.get(pk=r.pk)).data["compra"]
        self.assertEqual((compra["etapa"], compra["sugerir_destravar"]), ("pedido", False))
        PedidoCompra.objects.filter(pk=pedido.pk).update(status=PedidoCompra.Status.RECEBIDO_TOTAL)
        compra = RestricaoSerializer(Restricao.objects.get(pk=r.pk)).data["compra"]
        self.assertEqual((compra["etapa"], compra["sugerir_destravar"]), ("recebido", True))
        # Sugerir não é destravar: a trava continua aberta até a pessoa confirmar.
        self.assertEqual(Restricao.objects.get(pk=r.pk).status, Restricao.Status.ABERTA)


class SemanaEAlmoxarifadoTests(_Cenario, TestCase):
    """O compromisso pede o material; o apontamento avisa a baixa que falta."""

    @classmethod
    def setUpTestData(cls):
        cls.montar("pdca-sup-semana")

    def setUp(self):
        from modulopdca.models import ItemProgramacao

        self.crono = self.plano()
        services.publicar(self.crono)
        self.canteiro = LocalEstoque.objects.create(tenant=self.tenant, nome="Canteiro", tipo="canteiro", obra=self.obra)
        prog = services.abrir_programacao(obra=self.obra, semana_inicio=self.a11.inicio_cedo, tenant_id=self.tenant.pk)
        self.item = ItemProgramacao.objects.create(
            tenant=self.tenant, programacao=prog, atividade=self.a11, responsavel="Equipe A",
            percentual_previsto=Decimal("40"),
        )

    def test_pedir_material_da_semana_em_rascunho(self):
        from modulosil.models import Requisicao

        req = suprimentos.pedir_material_da_semana(self.item)
        self.assertEqual(req.status, Requisicao.Status.RASCUNHO)
        self.assertEqual((req.local_id, req.obra_id, req.etapa_id), (self.canteiro.pk, self.obra.pk, self.e1.pk))
        # A semana prevê 40%: 40% de 20 sacos de cimento e de 5 m³ de areia.
        self.assertEqual({i.item_id: i.quantidade for i in req.itens.all()},
                         {self.cimento.pk: Decimal("8.000"), self.areia.pk: Decimal("2.000")})
        self.item.refresh_from_db()
        self.assertEqual(self.item.requisicao_sil_id, req.pk)
        self.assertEqual(suprimentos.pedir_material_da_semana(self.item).pk, req.pk)

    def test_sem_canteiro_a_requisicao_nao_tem_de_onde_sair(self):
        from django.core.exceptions import ValidationError

        self.canteiro.delete()
        with self.assertRaises(ValidationError):
            suprimentos.pedir_material_da_semana(self.item)

    def test_o_apontamento_avisa_a_baixa_que_falta(self):
        from modulosil.models import MovimentacaoEstoque

        services.registrar_apontamento(atividade=self.a11, percentual=Decimal("50"),
                                       data=self.a11.inicio_cedo, por="Teste")
        linhas = {l["item"]: l for l in suprimentos.consumo_a_baixar(self.tenant.pk)}
        self.assertEqual(linhas[self.cimento.pk]["a_baixar"], "10.000")
        self.assertEqual(linhas[self.areia.pk]["etapa"], self.e1.pk)
        MovimentacaoEstoque.objects.create(
            tenant=self.tenant, item=self.cimento, local=self.canteiro, tipo="saida",
            quantidade=Decimal("4"), obra=self.obra, etapa=self.e1,
        )
        linhas = {l["item"]: l for l in suprimentos.consumo_a_baixar(self.tenant.pk)}
        self.assertEqual(linhas[self.cimento.pk]["a_baixar"], "6.000")

    def test_a_revisao_do_orcamento_vale_no_plano(self):
        """Aditivo: o orçamento v2 dobrou a alvenaria; a atividade ligada ao item
        da v1 passa a ser lida pelo item de mesmo código EAP na v2."""
        orc2 = Orcamento.objects.create(tenant=self.tenant, obra=self.obra, descricao="Revisão",
                                        versao=2, status=Orcamento.Status.APROVADO)
        alv2 = ItemOrcado.objects.create(tenant=self.tenant, orcamento=orc2, etapa=self.e1, codigo_eap="1.1",
                                         descricao="Alvenaria", unidade="M2", quantidade=Decimal("200"))
        ItemOrcadoInsumo.objects.create(tenant=self.tenant, item_orcado=alv2, item=self.cimento,
                                        descricao="Cimento CP-II", unidade="SC", coeficiente=Decimal("0.2"))
        n = suprimentos.necessidade_de_material(self.crono, hoje=date(2026, 5, 1))
        cim = [l for l in n["linhas"] if l["atividade"] == self.a11.pk and l["item"] == self.cimento.pk]
        self.assertEqual(cim[0]["quantidade"], "40.000")
        self.assertEqual(n["cobertura"]["ligadas_a_versao_anterior"], 1)


class CustoNoPlanoTests(_Cenario, TestCase):
    """Orçado × comprometido × recebido × aplicado, por etapa e atividade."""

    @classmethod
    def setUpTestData(cls):
        cls.montar("pdca-sup-custo")

    def test_o_pedido_e_rateado_e_o_aplicado_vai_para_a_etapa(self):
        from modulosil.models import MovimentacaoEstoque

        crono = self.plano()
        ItemOrcado.objects.filter(pk=self.alvenaria.pk).update(total_custo_direto=Decimal("1000"))
        centro = CentroCusto.objects.create(tenant=self.tenant, nome="Drenagem", obra=self.obra)
        forn = Fornecedor.objects.create(tenant=self.tenant, razao_social="Alfa", email="a@ex.com")
        pedido = PedidoCompra.objects.create(tenant=self.tenant, fornecedor=forn, centro_custo=centro,
                                             status=PedidoCompra.Status.ENVIADO)
        # 25 sacos de cimento: 20 na alvenaria (1.1) e 5 no reboco (etapa 2).
        ItemPedido.objects.create(tenant=self.tenant, pedido=pedido, produto=self.cimento,
                                  quantidade=Decimal("25"), preco_unitario=Decimal("40"))
        canteiro = LocalEstoque.objects.create(tenant=self.tenant, nome="Canteiro", tipo="canteiro", obra=self.obra)
        MovimentacaoEstoque.objects.create(tenant=self.tenant, item=self.cimento, local=canteiro, tipo="saida",
                                           quantidade=Decimal("3"), custo_unitario=Decimal("40"),
                                           obra=self.obra, etapa=self.e1)
        custo = suprimentos.custo_do_plano(crono)
        e1 = next(e for e in custo["etapas"] if e["etapa"] == self.e1.pk)
        a11 = next(a for a in e1["atividades"] if a["atividade"] == self.a11.pk)
        self.assertEqual(a11["orcado"], "1000.00")
        self.assertEqual(a11["comprometido"], "800.00")  # 20/25 de R$ 1.000
        self.assertEqual(e1["aplicado"], "120.00")
        e2 = next(e for e in custo["etapas"] if e["etapa"] == self.e2.pk)
        self.assertEqual(e2["comprometido"], "200.00")
        self.assertEqual(custo["total"]["comprometido"], "1000.00")
        self.assertTrue(custo["rateado"])


class RevisaoESobraTests(_Cenario, TestCase):
    """O aditivo religa o plano; a sobra de outro almoxarifado avisa antes de comprar."""

    @classmethod
    def setUpTestData(cls):
        cls.montar("pdca-sup-revisao")

    def test_religar_ao_orcamento_vigente(self):
        crono = self.plano()
        orc2 = Orcamento.objects.create(tenant=self.tenant, obra=self.obra, descricao="Revisão",
                                        versao=2, status=Orcamento.Status.APROVADO)
        alv2 = ItemOrcado.objects.create(tenant=self.tenant, orcamento=orc2, codigo_eap="1.1",
                                         descricao="Alvenaria", quantidade=Decimal("200"))
        self.assertEqual(suprimentos.religar_ao_orcamento_vigente(crono), 1)
        self.assertEqual(Atividade.objects.get(pk=self.a11.pk).item_orcado_id, alv2.pk)
        services.publicar(crono)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            suprimentos.religar_ao_orcamento_vigente(crono)

    def test_sobra_no_central_aparece_antes_de_comprar(self):
        crono = self.plano()
        central = LocalEstoque.objects.create(tenant=self.tenant, nome="Central", tipo="central")
        SaldoEstoque.objects.create(tenant=self.tenant, item=self.areia, local=central, quantidade=Decimal("4"))
        n = suprimentos.necessidade_de_material(crono, hoje=date(2026, 5, 1))
        areia = next(r for r in n["por_insumo"] if r["item"] == self.areia.pk)
        self.assertEqual(areia["fora_da_obra"], "4.000")
        self.assertEqual(areia["a_comprar"], "5.000")  # não abate: só avisa


class MedicaoXServicoTests(_Cenario, TestCase):
    """A empreitada pedida no Suprimentos conversa com o contrato que a mede."""

    @classmethod
    def setUpTestData(cls):
        cls.montar("pdca-sup-servico")

    def test_pedido_de_servico_no_contrato_e_no_custo(self):
        from modulopdca.models import ContratoObra, ItemContrato
        from modulopdca.serializers import ContratoObraSerializer
        from moduloscm.serializers import PedidoCompraSerializer

        crono = self.plano()
        centro = CentroCusto.objects.create(tenant=self.tenant, nome="Drenagem", obra=self.obra)
        forn = Fornecedor.objects.create(tenant=self.tenant, razao_social="Empreiteira", email="e@ex.com")
        pedido = PedidoCompra.objects.create(tenant=self.tenant, fornecedor=forn, centro_custo=centro,
                                             status=PedidoCompra.Status.APROVADO)
        ItemPedido.objects.create(tenant=self.tenant, pedido=pedido, descricao="Empreitada de alvenaria",
                                  quantidade=Decimal("1"), preco_unitario=Decimal("500"))
        contrato = ContratoObra.objects.create(
            tenant=self.tenant, obra=self.obra, fornecedor=forn, numero="7/2026", objeto="Alvenaria",
            data_inicio=date(2026, 6, 1), data_fim=date(2026, 12, 31),
            status=ContratoObra.Status.VIGENTE, pedido_scm=pedido,
        )
        ItemContrato.objects.create(tenant=self.tenant, contrato=contrato, codigo="1", descricao="Alvenaria",
                                    unidade="m2", quantidade_contratada=Decimal("10"), preco_unitario=Decimal("50"),
                                    atividade=self.a11)
        resumo = ContratoObraSerializer(contrato).data["pedido_scm_resumo"]
        self.assertEqual((resumo["valor_pedido"], resumo["medido_aprovado"], resumo["saldo"]),
                         ("500.00", "0.00", "500.00"))
        self.assertEqual(PedidoCompraSerializer(pedido).data["medicao_pdca"][0]["numero"], "7/2026")
        custo = suprimentos.custo_do_plano(crono)
        a11 = next(a for e in custo["etapas"] for a in e["atividades"] if a["atividade"] == self.a11.pk)
        self.assertEqual(a11["comprometido"], "500.00")
        self.assertEqual(custo["nao_alocado"]["comprometido"], "0.00")
