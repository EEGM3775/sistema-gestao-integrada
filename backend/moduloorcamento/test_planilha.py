# backend/moduloorcamento/test_planilha.py
"""Testes do ORC.1 — a planilha orçamentária.

Arquivo próprio (como `rh/test_field_masking.py` e `nucleo/test_lgpd.py`) porque
`tests.py` cobre a base referencial e a adoção, que é a outra metade do módulo.

Cobre: recálculo bottom-up e numeração EAP, snapshot que não segue o catálogo,
aprovação que congela, revisão que versiona, o seam do SIL (orçado × aplicado) e
a API — entitlement, permissão de aprovar separada da de editar, 409 em
documento fechado e isolamento por tenant.
"""
from datetime import date
from decimal import Decimal

from catalogo.models import Item
from modulosil.models import LocalEstoque, MovimentacaoEstoque
from obras.models import EtapaObra, Obra

from . import planilha, services
from .models import Fonte, ItemOrcado, Orcamento, RevisaoOrcamento
from .tests import ORC_PERMS_FULL, OrcamentoTestBase


class PlanilhaTestBase(OrcamentoTestBase):
    """Base com obra + etapas: a planilha só existe pendurada numa obra."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Residencial Aurora", endereco="Rua A, 100"
        )
        cls.fundacao = EtapaObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, nome_etapa="Fundação", ordem=1
        )
        cls.estrutura = EtapaObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, nome_etapa="Estrutura", ordem=2
        )

    def _orcamento(self, **kwargs):
        dados = {
            "tenant": self.tenant, "obra": self.obra, "descricao": "Orçamento executivo",
            "bdi_percentual": Decimal("0"), "data_base": date(2026, 7, 1),
        }
        dados.update(kwargs)
        return Orcamento.objects.create(**dados)

    def _linha(self, orcamento, descricao, *, pai=None, quantidade="0", custo="0",
               tipo=ItemOrcado.TipoLinha.ANALITICO, etapa=None, ordem=0):
        return ItemOrcado.objects.create(
            tenant=self.tenant, orcamento=orcamento, pai=pai, descricao=descricao,
            quantidade=Decimal(quantidade), custo_unitario=Decimal(custo),
            tipo_linha=tipo, etapa=etapa, ordem=ordem,
        )


class RecalculoDaPlanilhaTests(PlanilhaTestBase):
    def test_eap_numerada_pela_arvore(self):
        orc = self._orcamento()
        servicos = self._linha(orc, "Serviços preliminares", tipo=ItemOrcado.TipoLinha.SINTETICO, ordem=1)
        estrutura = self._linha(orc, "Estrutura", tipo=ItemOrcado.TipoLinha.SINTETICO, ordem=2)
        self._linha(orc, "Canteiro", pai=servicos, quantidade="1", custo="100", ordem=1)
        pilares = self._linha(orc, "Pilares", pai=estrutura, tipo=ItemOrcado.TipoLinha.SINTETICO, ordem=1)
        self._linha(orc, "Concretagem", pai=pilares, quantidade="10", custo="400", ordem=1)

        planilha.recalcular_orcamento(orc)
        codigos = dict(
            ItemOrcado.objects.filter(orcamento=orc).values_list("descricao", "codigo_eap")
        )
        self.assertEqual(codigos["Serviços preliminares"], "1")
        self.assertEqual(codigos["Canteiro"], "1.1")
        self.assertEqual(codigos["Estrutura"], "2")
        self.assertEqual(codigos["Pilares"], "2.1")
        self.assertEqual(codigos["Concretagem"], "2.1.1")

    def test_sintetico_soma_filhos_sem_duplicar_no_total(self):
        orc = self._orcamento()
        grupo = self._linha(orc, "Estrutura", tipo=ItemOrcado.TipoLinha.SINTETICO, ordem=1)
        self._linha(orc, "Concreto", pai=grupo, quantidade="10", custo="400", ordem=1)
        self._linha(orc, "Aço", pai=grupo, quantidade="500", custo="8", ordem=2)

        planilha.recalcular_orcamento(orc)
        orc.refresh_from_db()
        grupo.refresh_from_db()
        # 10×400 + 500×8 = 8.000. O total do orçamento é a soma das RAÍZES — se
        # somasse todas as linhas daria 16.000 (o grupo contado duas vezes).
        self.assertEqual(grupo.total_custo_direto, Decimal("8000.00"))
        self.assertEqual(orc.custo_direto_total, Decimal("8000.00"))

    def test_bdi_multiplica_linha_a_linha(self):
        orc = self._orcamento(bdi_percentual=Decimal("25.00"))
        self._linha(orc, "Concreto", quantidade="10", custo="400", ordem=1)

        planilha.recalcular_orcamento(orc)
        orc.refresh_from_db()
        self.assertEqual(orc.custo_direto_total, Decimal("4000.00"))
        self.assertEqual(orc.valor_total, Decimal("5000.00"))

    def test_ciclo_na_arvore_nao_estoura_a_pilha(self):
        """Dado corrompido (A vira filho do próprio filho) não derruba o recálculo."""
        orc = self._orcamento()
        a = self._linha(orc, "A", tipo=ItemOrcado.TipoLinha.SINTETICO)
        b = self._linha(orc, "B", pai=a, tipo=ItemOrcado.TipoLinha.SINTETICO)
        ItemOrcado.objects.filter(pk=a.pk).update(pai=b)

        planilha.recalcular_orcamento(orc)  # não pode levantar RecursionError
        orc.refresh_from_db()
        self.assertEqual(orc.custo_direto_total, Decimal("0.00"))

    def test_arredondamento_e_meio_para_cima(self):
        """0,125 → 0,13, e não 0,12 do bankers' rounding (default do Decimal)."""
        self.assertEqual(planilha.dinheiro(Decimal("0.125")), Decimal("0.13"))


class AprovacaoTests(PlanilhaTestBase):
    def test_aprovar_congela_e_bloqueia_edicao(self):
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="10", custo="400")
        planilha.aprovar_orcamento(orc, usuario_nome="Eng. Responsável")
        orc.refresh_from_db()

        self.assertEqual(orc.status, Orcamento.Status.APROVADO)
        self.assertEqual(orc.custo_direto_total, Decimal("4000.00"))
        self.assertIsNotNone(orc.aprovado_em)
        self.assertEqual(orc.aprovado_por_nome, "Eng. Responsável")
        self.assertFalse(orc.editavel)
        with self.assertRaises(planilha.OrcamentoNaoEditavel):
            planilha.exigir_editavel(orc)

    def test_aprovar_recalcula_antes_de_congelar(self):
        """Edição feita direto no banco não pode congelar um total defasado."""
        orc = self._orcamento()
        linha = self._linha(orc, "Concreto", quantidade="10", custo="400")
        planilha.recalcular_orcamento(orc)
        ItemOrcado.objects.filter(pk=linha.pk).update(quantidade=Decimal("20"))

        planilha.aprovar_orcamento(orc)
        orc.refresh_from_db()
        self.assertEqual(orc.custo_direto_total, Decimal("8000.00"))

    def test_orcamento_sem_itens_nao_aprova(self):
        orc = self._orcamento()
        with self.assertRaises(planilha.OrcamentoNaoEditavel):
            planilha.aprovar_orcamento(orc)


class RevisaoTests(PlanilhaTestBase):
    def test_revisar_cria_versao_nova_e_supera_a_anterior(self):
        orc = self._orcamento()
        grupo = self._linha(orc, "Estrutura", tipo=ItemOrcado.TipoLinha.SINTETICO, ordem=1)
        self._linha(orc, "Concreto", pai=grupo, quantidade="10", custo="400", ordem=1)
        planilha.aprovar_orcamento(orc)

        nova = planilha.revisar_orcamento(
            orc, tipo=RevisaoOrcamento.Tipo.ADITIVO, motivo="Acréscimo de 2 pilares",
            usuario_nome="Eng. Responsável",
        )
        orc.refresh_from_db()

        self.assertEqual(orc.status, Orcamento.Status.SUPERADO)
        self.assertEqual(nova.versao, 2)
        self.assertEqual(nova.status, Orcamento.Status.RASCUNHO)
        self.assertEqual(nova.orcamento_origem_id, orc.orcamento_id)
        self.assertTrue(nova.editavel)

    def test_revisao_clona_a_arvore_preservando_hierarquia(self):
        orc = self._orcamento()
        grupo = self._linha(orc, "Estrutura", tipo=ItemOrcado.TipoLinha.SINTETICO, ordem=1)
        self._linha(orc, "Concreto", pai=grupo, quantidade="10", custo="400", ordem=1)
        self._linha(orc, "Aço", pai=grupo, quantidade="500", custo="8", ordem=2)
        planilha.aprovar_orcamento(orc)

        nova = planilha.revisar_orcamento(orc, tipo=RevisaoOrcamento.Tipo.ADITIVO, motivo="x")

        clonados = ItemOrcado.objects.filter(orcamento=nova)
        self.assertEqual(clonados.count(), 3)
        clone_grupo = clonados.get(descricao="Estrutura")
        clone_concreto = clonados.get(descricao="Concreto")
        # A hierarquia veio junto — e aponta para o CLONE, não para o original.
        self.assertEqual(clone_concreto.pai_id, clone_grupo.item_orcado_id)
        self.assertNotEqual(clone_grupo.item_orcado_id, grupo.item_orcado_id)
        self.assertEqual(nova.custo_direto_total, orc.custo_direto_total)

    def test_revisao_registra_o_delta(self):
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="10", custo="400")
        planilha.aprovar_orcamento(orc)
        nova = planilha.revisar_orcamento(
            orc, tipo=RevisaoOrcamento.Tipo.ADITIVO, motivo="Mais 5 m³",
        )
        ItemOrcado.objects.filter(orcamento=nova).update(quantidade=Decimal("15"))
        planilha.recalcular_orcamento(nova)

        revisao = RevisaoOrcamento.objects.get(orcamento=nova)
        self.assertEqual(revisao.numero, 1)
        self.assertEqual(revisao.valor_anterior, Decimal("4000.00"))
        self.assertEqual(revisao.motivo, "Mais 5 m³")
        self.assertEqual(revisao.orcamento_anterior_id, orc.orcamento_id)

    def test_rascunho_nao_gera_revisao(self):
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="1", custo="1")
        with self.assertRaises(planilha.RevisaoInvalida):
            planilha.revisar_orcamento(orc, tipo=RevisaoOrcamento.Tipo.ADITIVO, motivo="x")


class SnapshotDaLinhaTests(PlanilhaTestBase):
    """O snapshot é o que faz o orçamento aprovado ser régua histórica."""

    def setUp(self):
        super().setUp()
        self.base = self._base()
        self.referencia = self._ref(
            self.base, codigo="92873", descricao="CONCRETAGEM", custo="412.80"
        )
        self.item = services.adotar_no_catalogo(self.referencia, self.tenant.id)

    def test_linha_copia_preco_da_base_do_orcamento(self):
        orc = self._orcamento(base_referencial=self.base)
        linha = services.linha_a_partir_do_item(orcamento=orc, item=self.item, quantidade="10")

        self.assertEqual(linha.custo_unitario, Decimal("412.8000"))
        self.assertEqual(linha.codigo_referencia, "92873")
        self.assertEqual(linha.fonte_referencia, Fonte.SINAPI)
        self.assertEqual(linha.data_base_preco, date(2026, 7, 1))

    def test_preco_informado_ganha_do_de_referencia(self):
        orc = self._orcamento(base_referencial=self.base)
        linha = services.linha_a_partir_do_item(
            orcamento=orc, item=self.item, quantidade="10", custo_unitario="380.00",
        )
        self.assertEqual(linha.custo_unitario, Decimal("380.0000"))
        # Preço próprio não carrega data-base da publicação — não veio dela.
        self.assertIsNone(linha.data_base_preco)

    def test_snapshot_nao_segue_o_catalogo(self):
        orc = self._orcamento(base_referencial=self.base)
        linha = services.linha_a_partir_do_item(orcamento=orc, item=self.item, quantidade="10")
        planilha.aprovar_orcamento(orc)

        self.item.descricao = "CONCRETAGEM (descrição corrigida)"
        self.item.save()
        linha.refresh_from_db()
        orc.refresh_from_db()

        self.assertEqual(linha.descricao, "CONCRETAGEM")
        self.assertEqual(orc.custo_direto_total, Decimal("4128.00"))

    def test_item_sem_preco_conhecido_nasce_zerado(self):
        """Sem preço na base e sem preço informado, a linha não inventa número."""
        orc = self._orcamento()  # sem base_referencial
        linha = services.linha_a_partir_do_item(orcamento=orc, item=self.item, quantidade="10")
        self.assertEqual(linha.custo_unitario, Decimal("0"))


class SeamDoSilTests(PlanilhaTestBase):
    """O orçado que o `aplicado/` do SIL consome."""

    def _item_catalogo(self):
        return Item.objects.create(
            tenant=self.tenant, codigo_interno="CONC-25", descricao="Concreto usinado", unidade="M3",
        )

    def test_orcado_por_etapa_so_conta_analiticos_do_aprovado(self):
        orc = self._orcamento(bdi_percentual=Decimal("20.00"))
        grupo = self._linha(orc, "Estrutura", tipo=ItemOrcado.TipoLinha.SINTETICO,
                            etapa=self.estrutura, ordem=1)
        self._linha(orc, "Concreto", pai=grupo, quantidade="10", custo="400",
                    etapa=self.estrutura, ordem=1)
        self._linha(orc, "Sapatas", quantidade="4", custo="1000", etapa=self.fundacao, ordem=2)
        planilha.aprovar_orcamento(orc)

        orcado = planilha.orcado_por_etapa(self.tenant.id, self.obra.pk)
        self.assertEqual(orcado[(self.obra.pk, self.estrutura.pk)]["orcado"], Decimal("4000.00"))
        self.assertEqual(orcado[(self.obra.pk, self.estrutura.pk)]["orcado_com_bdi"], Decimal("4800.00"))
        self.assertEqual(orcado[(self.obra.pk, self.fundacao.pk)]["orcado"], Decimal("4000.00"))

    def test_sem_orcamento_aprovado_nao_ha_regua(self):
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="10", custo="400", etapa=self.fundacao)
        planilha.recalcular_orcamento(orc)  # continua rascunho
        self.assertEqual(planilha.orcado_por_etapa(self.tenant.id, self.obra.pk), {})

    def test_revisao_troca_a_regua_vigente(self):
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="10", custo="400", etapa=self.fundacao)
        planilha.aprovar_orcamento(orc)
        nova = planilha.revisar_orcamento(orc, tipo=RevisaoOrcamento.Tipo.ADITIVO, motivo="x")
        ItemOrcado.objects.filter(orcamento=nova).update(quantidade=Decimal("15"))
        planilha.aprovar_orcamento(nova)

        orcado = planilha.orcado_por_etapa(self.tenant.id, self.obra.pk)
        self.assertEqual(orcado[(self.obra.pk, self.fundacao.pk)]["orcado"], Decimal("6000.00"))

    def test_aplicado_do_sil_traz_orcado_e_estouro(self):
        """O laço fechado: orçamento aprovado → SIL confronta consumo com a régua."""
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="10", custo="400", etapa=self.fundacao)
        planilha.aprovar_orcamento(orc)

        local = LocalEstoque.objects.create(tenant=self.tenant, nome="Canteiro", obra=self.obra)
        MovimentacaoEstoque.objects.create(
            tenant=self.tenant, item=self._item_catalogo(), local=local,
            tipo=MovimentacaoEstoque.Tipo.SAIDA, quantidade=Decimal("12"),
            custo_unitario=Decimal("400"), obra=self.obra, etapa=self.fundacao,
        )
        self.autenticar(modules=("sil", "orcamento"),
                        perms=[*ORC_PERMS_FULL, "sil.relatorio.view"])
        resp = self.client.get(f"/api/sil/aplicado/?obra={self.obra.pk}")

        self.assertEqual(resp.status_code, 200, resp.content)
        linha = resp.data[0]
        self.assertEqual(Decimal(linha["aplicado"]), Decimal("4800.0000"))
        self.assertEqual(Decimal(linha["orcado"]), Decimal("4000.00"))
        self.assertTrue(linha["estourado"])

    def test_sem_o_modulo_orcamento_o_sil_nao_mostra_regua(self):
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="10", custo="400", etapa=self.fundacao)
        planilha.aprovar_orcamento(orc)

        local = LocalEstoque.objects.create(tenant=self.tenant, nome="Canteiro", obra=self.obra)
        MovimentacaoEstoque.objects.create(
            tenant=self.tenant, item=self._item_catalogo(), local=local,
            tipo=MovimentacaoEstoque.Tipo.SAIDA, quantidade=Decimal("1"),
            custo_unitario=Decimal("400"), obra=self.obra, etapa=self.fundacao,
        )
        self.autenticar(modules=("sil",), perms=["sil.relatorio.view"])
        resp = self.client.get("/api/sil/aplicado/")

        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.data[0]["orcado"])


class PlanilhaAPITests(PlanilhaTestBase):
    def setUp(self):
        super().setUp()
        self.autenticar()

    def test_criar_orcamento_e_linha_recalcula(self):
        resp = self.client.post("/api/orcamento/orcamentos/", {
            "obra": self.obra.pk, "descricao": "Executivo", "bdi_percentual": "25.00",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        orcamento_id = resp.data["orcamento_id"]

        resp = self.client.post("/api/orcamento/itens/", {
            "orcamento": orcamento_id, "descricao": "Concreto", "unidade": "M3",
            "quantidade": "10", "custo_unitario": "400", "etapa": self.fundacao.pk,
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)

        resp = self.client.get(f"/api/orcamento/orcamentos/{orcamento_id}/")
        self.assertEqual(Decimal(resp.data["custo_direto_total"]), Decimal("4000.00"))
        self.assertEqual(Decimal(resp.data["valor_total"]), Decimal("5000.00"))
        self.assertEqual(resp.data["total_itens"], 1)

    def test_segundo_orcamento_da_mesma_obra_nasce_na_versao_seguinte(self):
        """Reorçamento não é erro de formulário.

        `versao` é read-only e a unicidade é `(obra, versao)`: enquanto o POST
        não numerava, a segunda planilha de uma obra respondia 400 *"Os campos
        obra, versao devem criar um set único"* — só dava para criar uma por
        obra, e o hub do módulo quebrava na cara do usuário.
        """
        primeiro = self.client.post("/api/orcamento/orcamentos/", {
            "obra": self.obra.pk, "descricao": "Executivo",
        }, format="json")
        self.assertEqual(primeiro.status_code, 201, primeiro.content)
        self.assertEqual(primeiro.data["versao"], 1)

        segundo = self.client.post("/api/orcamento/orcamentos/", {
            "obra": self.obra.pk, "descricao": "Reorçamento — método alternativo",
        }, format="json")
        self.assertEqual(segundo.status_code, 201, segundo.content)
        self.assertEqual(segundo.data["versao"], 2)
        self.assertNotEqual(segundo.data["orcamento_id"], primeiro.data["orcamento_id"])

    def test_versao_do_post_continua_depois_da_revisao(self):
        """A numeração é uma só por obra — POST, revisar e duplicar compartilham."""
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="10", custo="400")
        planilha.aprovar_orcamento(orc)
        planilha.revisar_orcamento(orc, tipo="aditivo", motivo="Acréscimo")  # → v2

        resp = self.client.post("/api/orcamento/orcamentos/", {
            "obra": self.obra.pk, "descricao": "Reorçamento do zero",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["versao"], 3)

    def test_arvore_devolve_planilha_ordenada(self):
        orc = self._orcamento()
        grupo = self._linha(orc, "Estrutura", tipo=ItemOrcado.TipoLinha.SINTETICO, ordem=1)
        self._linha(orc, "Concreto", pai=grupo, quantidade="10", custo="400", ordem=1)
        planilha.recalcular_orcamento(orc)

        resp = self.client.get(f"/api/orcamento/orcamentos/{orc.pk}/arvore/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([i["codigo_eap"] for i in resp.data["itens"]], ["1", "1.1"])

    def test_linha_do_catalogo_pela_api(self):
        base = self._base()
        referencia = self._ref(base, codigo="92873", descricao="CONCRETAGEM", custo="412.80")
        item = services.adotar_no_catalogo(referencia, self.tenant.id)
        orc = self._orcamento(base_referencial=base)

        resp = self.client.post("/api/orcamento/itens/do-catalogo/", {
            "orcamento": orc.pk, "item": item.pk, "quantidade": "10", "etapa": self.fundacao.pk,
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Decimal(resp.data["custo_unitario"]), Decimal("412.8000"))
        self.assertEqual(Decimal(resp.data["total_custo_direto"]), Decimal("4128.00"))

    def test_editar_aprovado_e_409(self):
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="10", custo="400")
        planilha.aprovar_orcamento(orc)

        resp = self.client.patch(f"/api/orcamento/orcamentos/{orc.pk}/",
                                 {"descricao": "outro"}, format="json")
        self.assertEqual(resp.status_code, 409, resp.content)

    def test_aprovar_e_revisar_pela_api(self):
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="10", custo="400")

        resp = self.client.post(f"/api/orcamento/orcamentos/{orc.pk}/aprovar/", {}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["status"], "aprovado")

        resp = self.client.post(f"/api/orcamento/orcamentos/{orc.pk}/revisar/",
                                {"tipo": "aditivo", "motivo": "Acréscimo de escopo"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["versao"], 2)

    def test_revisar_sem_motivo_e_400(self):
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="10", custo="400")
        planilha.aprovar_orcamento(orc)

        resp = self.client.post(f"/api/orcamento/orcamentos/{orc.pk}/revisar/",
                                {"tipo": "aditivo"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_aprovar_exige_permissao_propria(self):
        """A persona `orcamentista` edita a planilha mas não congela a régua."""
        orc = self._orcamento()
        self._linha(orc, "Concreto", quantidade="10", custo="400")
        self.autenticar(perms=["orcamento.orcamento.view", "orcamento.orcamento.edit",
                               "orcamento.item.view", "orcamento.item.edit"])

        resp = self.client.post(f"/api/orcamento/orcamentos/{orc.pk}/aprovar/", {}, format="json")
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_sem_entitlement_do_modulo_e_403(self):
        self.autenticar(modules=("scm",))
        resp = self.client.get("/api/orcamento/orcamentos/")
        self.assertEqual(resp.status_code, 403)

    def test_etapa_de_outra_obra_e_400(self):
        outra = Obra.objects.create(tenant=self.tenant, nome_obra="Outra", endereco="Rua B")
        etapa_alheia = EtapaObra.objects.create(
            tenant=self.tenant, obra=outra, nome_etapa="Fundação", ordem=1
        )
        orc = self._orcamento()

        resp = self.client.post("/api/orcamento/itens/", {
            "orcamento": orc.pk, "descricao": "Concreto", "quantidade": "1",
            "custo_unitario": "1", "etapa": etapa_alheia.pk,
        }, format="json")
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_orcamento_de_outro_tenant_nao_aparece(self):
        obra_b = Obra.objects.create(tenant=self.tenant_b, nome_obra="Obra B", endereco="Rua C")
        Orcamento.objects.create(tenant=self.tenant_b, obra=obra_b, descricao="Do vizinho")

        resp = self.client.get("/api/orcamento/orcamentos/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Do vizinho", [o["descricao"] for o in resp.data["results"]])

    def test_revisoes_sao_read_only(self):
        resp = self.client.post("/api/orcamento/revisoes/", {}, format="json")
        self.assertEqual(resp.status_code, 405)
