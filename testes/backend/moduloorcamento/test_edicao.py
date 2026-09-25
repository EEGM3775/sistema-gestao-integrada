# testes/backend/moduloorcamento/test_edicao.py
"""Testes da ORC.10 — a planilha como documento que se edita.

Arquivo próprio pelo mesmo critério de `test_planilha.py`: ali mora o recálculo
e o ciclo de vida do documento, aqui moram os **verbos de edição estrutural**
que a ORC.10 trouxe — mover, indentar, duplicar, lote, composição editável e o
destrave do aprovado.

O que cada bloco protege está no docstring da classe. O fio comum: nenhum verbo
pode deixar a árvore inconsistente (ciclo, ordem com buraco, total defasado), e
é isso que a maioria das asserções confere.
"""
from decimal import Decimal

from catalogo.models import Item

from moduloorcamento import edicao, planilha
from moduloorcamento.models import (
    BancoPreco,
    ComponenteBancoPreco,
    ItemBancoPreco,
    ItemOrcado,
    ItemOrcadoInsumo,
    LinhaMedicao,
    Orcamento,
)
from .test_planilha import PlanilhaTestBase


class ArvoreTestBase(PlanilhaTestBase):
    """Uma planilha de três etapas com dois serviços cada — o mínimo para mover.

        1 Serviços preliminares
          1.1 Tapume
          1.2 Placa de obra
        2 Fundação
          2.1 Escavação
        3 Estrutura
    """

    def setUp(self):
        super().setUp()
        self.orc = self._orcamento()
        self.preliminares = self._linha(
            self.orc, "Serviços preliminares", tipo=ItemOrcado.TipoLinha.SINTETICO, ordem=0,
        )
        self.tapume = self._linha(
            self.orc, "Tapume", pai=self.preliminares, quantidade="10", custo="50", ordem=0,
        )
        self.placa = self._linha(
            self.orc, "Placa de obra", pai=self.preliminares, quantidade="1", custo="800", ordem=1,
        )
        self.fundacao = self._linha(
            self.orc, "Fundação", tipo=ItemOrcado.TipoLinha.SINTETICO, ordem=1,
        )
        self.escavacao = self._linha(
            self.orc, "Escavação", pai=self.fundacao, quantidade="20", custo="35", ordem=0,
        )
        self.estrutura = self._linha(
            self.orc, "Estrutura", tipo=ItemOrcado.TipoLinha.SINTETICO, ordem=2,
        )
        planilha.recalcular_orcamento(self.orc)

    def eap(self, linha) -> str:
        linha.refresh_from_db()
        return linha.codigo_eap


class MoverTests(ArvoreTestBase):
    """ORC.10b — arrastar, indentar, desindentar e reordenar."""

    def test_indentar_pendura_na_linha_de_cima(self):
        edicao.mover(self.orc, [self.fundacao.pk], operacao="indentar")
        self.fundacao.refresh_from_db()
        self.assertEqual(self.fundacao.pai_id, self.preliminares.pk)
        self.assertEqual(self.eap(self.fundacao), "1.3")
        # A subárvore acompanha — mover uma etapa sem os serviços dela seria
        # desmontar a etapa, não movê-la.
        self.assertEqual(self.eap(self.escavacao), "1.3.1")

    def test_indentar_sem_linha_acima_e_recusado(self):
        with self.assertRaises(edicao.EdicaoInvalida):
            edicao.mover(self.orc, [self.preliminares.pk], operacao="indentar")

    def test_desindentar_sobe_e_pousa_logo_depois_do_antigo_pai(self):
        edicao.mover(self.orc, [self.placa.pk], operacao="desindentar")
        self.placa.refresh_from_db()
        self.assertIsNone(self.placa.pai_id)
        # Preliminares é 1; a placa vira 2 e empurra Fundação e Estrutura.
        self.assertEqual(self.eap(self.placa), "2")
        self.assertEqual(self.eap(self.fundacao), "3")
        self.assertEqual(self.eap(self.estrutura), "4")

    def test_desindentar_na_raiz_e_recusado(self):
        with self.assertRaises(edicao.EdicaoInvalida):
            edicao.mover(self.orc, [self.preliminares.pk], operacao="desindentar")

    def test_baixo_troca_com_o_irmao_seguinte(self):
        edicao.mover(self.orc, [self.preliminares.pk], operacao="baixo")
        self.assertEqual(self.eap(self.fundacao), "1")
        self.assertEqual(self.eap(self.preliminares), "2")
        self.assertEqual(self.eap(self.estrutura), "3")

    def test_cima_na_primeira_posicao_e_recusado(self):
        with self.assertRaises(edicao.EdicaoInvalida):
            edicao.mover(self.orc, [self.preliminares.pk], operacao="cima")

    def test_bloco_de_irmaos_anda_junto_e_mantem_a_ordem_interna(self):
        edicao.mover(self.orc, [self.preliminares.pk, self.fundacao.pk], operacao="baixo")
        self.assertEqual(self.eap(self.estrutura), "1")
        self.assertEqual(self.eap(self.preliminares), "2")
        self.assertEqual(self.eap(self.fundacao), "3")

    def test_selecao_de_niveis_diferentes_e_recusada(self):
        with self.assertRaises(edicao.EdicaoInvalida):
            edicao.mover(self.orc, [self.preliminares.pk, self.tapume.pk], operacao="baixo")

    def test_arrastar_para_pai_e_posicao_explicitos(self):
        edicao.mover(self.orc, [self.escavacao.pk], pai_id=self.preliminares.pk, posicao=0)
        self.escavacao.refresh_from_db()
        self.assertEqual(self.escavacao.pai_id, self.preliminares.pk)
        self.assertEqual(self.eap(self.escavacao), "1.1")
        self.assertEqual(self.eap(self.tapume), "1.2")
        self.assertEqual(self.eap(self.placa), "1.3")

    def test_posicao_alem_do_fim_cai_no_fim(self):
        edicao.mover(self.orc, [self.escavacao.pk], pai_id=self.preliminares.pk, posicao=99)
        self.assertEqual(self.eap(self.escavacao), "1.3")

    def test_mover_para_dentro_de_si_mesma_e_recusado(self):
        """A guarda de ciclo — sem ela o recálculo giraria para sempre."""
        with self.assertRaises(edicao.EdicaoInvalida):
            edicao.mover(self.orc, [self.preliminares.pk], pai_id=self.tapume.pk)

    def test_mover_recalcula_os_totais(self):
        """Etapa que muda de dono muda o total da etapa — não só a numeração."""
        edicao.mover(self.orc, [self.escavacao.pk], pai_id=self.preliminares.pk)
        self.preliminares.refresh_from_db()
        self.fundacao.refresh_from_db()
        # 10×50 + 1×800 + 20×35 = 2000
        self.assertEqual(self.preliminares.total_custo_direto, Decimal("2000.00"))
        self.assertEqual(self.fundacao.total_custo_direto, Decimal("0.00"))

    def test_ordem_fica_densa_depois_de_mover(self):
        edicao.mover(self.orc, [self.fundacao.pk], operacao="baixo")
        raizes = ItemOrcado.objects.filter(orcamento=self.orc, pai__isnull=True).order_by("ordem")
        self.assertEqual([r.ordem for r in raizes], [0, 1, 2])

    def test_orcamento_aprovado_recusa_mover(self):
        planilha.aprovar_orcamento(self.orc)
        with self.assertRaises(planilha.OrcamentoNaoEditavel):
            edicao.mover(self.orc, [self.fundacao.pk], operacao="baixo")

    def test_linha_de_outro_orcamento_e_recusada(self):
        outro = self._orcamento(descricao="Outra planilha", versao=2)
        forasteira = self._linha(outro, "De fora")
        with self.assertRaises(edicao.EdicaoInvalida):
            edicao.mover(self.orc, [forasteira.pk], operacao="baixo")


class DuplicarTests(ArvoreTestBase):
    """ORC.10d — copiar um trecho conferido, com o que o torna conferível."""

    def test_duplica_a_subarvore_inteira(self):
        antes = ItemOrcado.objects.filter(orcamento=self.orc).count()
        edicao.duplicar(self.orc, [self.preliminares.pk])
        depois = ItemOrcado.objects.filter(orcamento=self.orc).count()
        self.assertEqual(depois - antes, 3)  # a etapa + dois serviços

    def test_copia_entra_logo_abaixo_da_original(self):
        edicao.duplicar(self.orc, [self.preliminares.pk])
        raizes = list(
            ItemOrcado.objects.filter(orcamento=self.orc, pai__isnull=True).order_by("ordem")
        )
        self.assertEqual(
            [r.descricao for r in raizes],
            ["Serviços preliminares", "Serviços preliminares", "Fundação", "Estrutura"],
        )

    def test_copia_leva_composicao_e_memoria_do_quantitativo(self):
        ItemOrcadoInsumo.objects.create(
            tenant=self.tenant, item_orcado=self.tapume, descricao="Chapa compensada",
            unidade="M2", coeficiente=Decimal("1.05"), custo_unitario=Decimal("40"),
            custo_no_item=Decimal("42"),
        )
        LinhaMedicao.objects.create(
            tenant=self.tenant, item_orcado=self.tapume, descricao="Frente do lote",
            repeticoes=Decimal("2"), comprimento=Decimal("5"), total=Decimal("10"),
        )
        edicao.duplicar(self.orc, [self.tapume.pk])

        copia = ItemOrcado.objects.filter(
            orcamento=self.orc, descricao="Tapume",
        ).exclude(pk=self.tapume.pk).get()
        self.assertEqual(ItemOrcadoInsumo.objects.filter(item_orcado=copia).count(), 1)
        self.assertEqual(LinhaMedicao.objects.filter(item_orcado=copia).count(), 1)

    def test_selecionado_dentro_de_selecionado_nao_duplica_duas_vezes(self):
        """A etapa e o filho dela marcados juntos geram **uma** cópia da etapa."""
        antes = ItemOrcado.objects.filter(orcamento=self.orc).count()
        edicao.duplicar(self.orc, [self.preliminares.pk, self.tapume.pk])
        depois = ItemOrcado.objects.filter(orcamento=self.orc).count()
        self.assertEqual(depois - antes, 3)

    def test_duplicar_soma_no_total(self):
        edicao.duplicar(self.orc, [self.tapume.pk])
        self.orc.refresh_from_db()
        # 500 + 800 + 700 originais, mais 500 da cópia
        self.assertEqual(self.orc.custo_direto_total, Decimal("2500.00"))


class ExcluirERestaurarTests(ArvoreTestBase):
    """ORC.10d — o Ctrl+Z de exclusão só existe porque `excluir` devolve o material."""

    def test_excluir_leva_a_subarvore(self):
        resultado = edicao.excluir(self.orc, [self.preliminares.pk])
        self.assertEqual(resultado["excluidas"], 3)
        self.assertFalse(ItemOrcado.objects.filter(pk=self.tapume.pk).exists())

    def test_restaurar_refaz_a_forma_da_arvore(self):
        resultado = edicao.excluir(self.orc, [self.preliminares.pk])
        edicao.restaurar(self.orc, resultado["desfazer"])

        etapa = ItemOrcado.objects.get(orcamento=self.orc, descricao="Serviços preliminares")
        filhos = ItemOrcado.objects.filter(pai=etapa).order_by("ordem")
        self.assertEqual([f.descricao for f in filhos], ["Tapume", "Placa de obra"])

    def test_restaurar_devolve_o_total(self):
        antes = self.orc.custo_direto_total
        resultado = edicao.excluir(self.orc, [self.preliminares.pk])
        edicao.restaurar(self.orc, resultado["desfazer"])
        self.orc.refresh_from_db()
        self.assertEqual(self.orc.custo_direto_total, antes)

    def test_ids_mudam_e_isso_e_declarado(self):
        """O banco não reaproveita chave — fingir que reaproveita seria mentir."""
        resultado = edicao.excluir(self.orc, [self.tapume.pk])
        novos = edicao.restaurar(self.orc, resultado["desfazer"])
        self.assertNotIn(self.tapume.pk, novos)


class LoteTests(ArvoreTestBase):
    """ORC.10d — os verbos de massa, e o que eles se recusam a tocar."""

    def test_percentual_sobe_o_custo_da_selecao(self):
        edicao.aplicar_percentual(self.orc, [self.tapume.pk], "10")
        self.tapume.refresh_from_db()
        self.assertEqual(self.tapume.custo_unitario, Decimal("55.0000"))

    def test_percentual_negativo_desce(self):
        edicao.aplicar_percentual(self.orc, [self.tapume.pk], "-10")
        self.tapume.refresh_from_db()
        self.assertEqual(self.tapume.custo_unitario, Decimal("45.0000"))

    def test_percentual_pula_sintetico(self):
        """Agrupador é soma dos filhos — aplicar percentual nele contaria duas vezes."""
        afetadas = edicao.aplicar_percentual(self.orc, [self.preliminares.pk], "10")
        self.assertEqual(afetadas, 0)

    def test_percentual_pula_linha_com_preco_travado(self):
        self.tapume.preco_travado = True
        self.tapume.save(update_fields=["preco_travado"])
        afetadas = edicao.aplicar_percentual(self.orc, [self.tapume.pk, self.placa.pk], "10")
        self.tapume.refresh_from_db()
        self.assertEqual(afetadas, 1)
        self.assertEqual(self.tapume.custo_unitario, Decimal("50.0000"))

    def test_percentual_na_quantidade(self):
        edicao.aplicar_percentual(self.orc, [self.tapume.pk], "50", campo="quantidade")
        self.tapume.refresh_from_db()
        self.assertEqual(self.tapume.quantidade, Decimal("15.0000"))

    def test_reducao_acima_de_cem_por_cento_e_recusada(self):
        with self.assertRaises(edicao.EdicaoInvalida):
            edicao.aplicar_percentual(self.orc, [self.tapume.pk], "-150")

    def test_arredondar_quantidade(self):
        self.tapume.quantidade = Decimal("10.4567")
        self.tapume.save(update_fields=["quantidade"])
        edicao.arredondar(self.orc, [self.tapume.pk], casas=2)
        self.tapume.refresh_from_db()
        self.assertEqual(self.tapume.quantidade, Decimal("10.4600"))

    def test_substituir_texto_na_descricao(self):
        afetadas = edicao.substituir_texto(self.orc, "Tapume", "Tapume metálico")
        self.tapume.refresh_from_db()
        self.assertEqual(afetadas, 1)
        self.assertEqual(self.tapume.descricao, "Tapume metálico")

    def test_substituir_sem_texto_e_recusado(self):
        with self.assertRaises(edicao.EdicaoInvalida):
            edicao.substituir_texto(self.orc, "", "x")

    def test_lote_recalcula_o_total(self):
        edicao.aplicar_percentual(self.orc, [self.tapume.pk], "100")
        self.orc.refresh_from_db()
        # 10×100 + 800 + 700
        self.assertEqual(self.orc.custo_direto_total, Decimal("2500.00"))


class ComposicaoEditavelTests(ArvoreTestBase):
    """ORC.10c — o núcleo do Arquimedes: mexer na decomposição e ver o preço mudar."""

    def setUp(self):
        super().setUp()
        self.cimento = ItemOrcadoInsumo.objects.create(
            tenant=self.tenant, item_orcado=self.tapume, descricao="Chapa compensada",
            unidade="M2", coeficiente=Decimal("1"), custo_unitario=Decimal("40"),
            custo_no_item=Decimal("40"),
        )

    def test_recompor_refaz_o_custo_pela_soma_dos_insumos(self):
        total = edicao.recompor_linha(self.tapume, espelhar=False)
        self.tapume.refresh_from_db()
        self.assertEqual(total, Decimal("40.0000"))
        self.assertEqual(self.tapume.custo_unitario, Decimal("40.0000"))

    def test_recompor_respeita_preco_travado(self):
        """Travar é dizer que o número é cotação; recompor por cima apagaria a cotação."""
        self.tapume.preco_travado = True
        self.tapume.save(update_fields=["preco_travado"])
        edicao.recompor_linha(self.tapume, espelhar=False)
        self.tapume.refresh_from_db()
        self.assertEqual(self.tapume.custo_unitario, Decimal("50.0000"))

    def test_recompor_propaga_para_o_total(self):
        edicao.recompor_linha(self.tapume, espelhar=False)
        self.orc.refresh_from_db()
        # 10×40 + 800 + 700
        self.assertEqual(self.orc.custo_direto_total, Decimal("1900.00"))

    def test_banco_da_obra_nasce_na_primeira_edicao(self):
        banco = edicao.banco_da_obra(self.orc)
        self.assertEqual(banco.obra_id, self.obra.pk)
        self.assertEqual(banco.tenant_id, self.tenant.id)
        # Idempotente — a segunda edição não cria um segundo banco.
        self.assertEqual(edicao.banco_da_obra(self.orc).pk, banco.pk)

    def test_espelhar_grava_composicao_e_componentes_no_banco(self):
        edicao.recompor_linha(self.tapume)
        banco = edicao.banco_da_obra(self.orc)
        composicao = ItemBancoPreco.objects.get(banco=banco, tipo="composicao")
        self.assertEqual(composicao.descricao, "Tapume")
        self.assertEqual(
            ComponenteBancoPreco.objects.filter(composicao=composicao).count(), 1,
        )

    def test_insumo_tirado_da_linha_sai_do_espelho(self):
        edicao.recompor_linha(self.tapume)
        self.cimento.delete()
        edicao.recompor_linha(self.tapume)
        banco = edicao.banco_da_obra(self.orc)
        composicao = ItemBancoPreco.objects.get(banco=banco, tipo="composicao")
        self.assertEqual(
            ComponenteBancoPreco.objects.filter(composicao=composicao).count(), 0,
        )

    def test_banco_travado_recusa_a_gravacao(self):
        """A trava do banco não pode ter porta dos fundos pela grade do orçamento."""
        banco = edicao.banco_da_obra(self.orc)
        banco.travado = True
        banco.save(update_fields=["travado"])
        with self.assertRaises(edicao.EdicaoInvalida):
            edicao.recompor_linha(self.tapume)

    def test_promover_publica_no_acervo_da_empresa(self):
        acervo = BancoPreco.objects.create(
            tenant=self.tenant, nome="Composições da empresa",
        )
        edicao.promover_para_banco(self.tapume, acervo)
        self.assertTrue(ItemBancoPreco.objects.filter(banco=acervo, tipo="composicao").exists())

    # --- pela API, que é por onde a grade edita ---------------------------

    def test_api_criar_insumo_recompoe_a_linha(self):
        self.autenticar()
        resposta = self.client.post(
            "/api/orcamento/insumos/",
            {
                "item_orcado": self.tapume.pk, "descricao": "Sarrafo",
                "unidade": "M", "categoria": "material",
                "coeficiente": "2", "custo_unitario": "5",
            },
            format="json",
        )
        self.assertEqual(resposta.status_code, 201, resposta.data)
        self.tapume.refresh_from_db()
        # 40 (chapa) + 2×5 (sarrafo)
        self.assertEqual(self.tapume.custo_unitario, Decimal("50.0000"))

    def test_api_custo_no_item_e_derivado_nao_aceito_do_cliente(self):
        self.autenticar()
        resposta = self.client.post(
            "/api/orcamento/insumos/",
            {
                "item_orcado": self.tapume.pk, "descricao": "Prego", "unidade": "KG",
                "categoria": "material", "coeficiente": "1", "custo_unitario": "12",
                "custo_no_item": "99999",
            },
            format="json",
        )
        self.assertEqual(resposta.status_code, 201, resposta.data)
        self.assertEqual(Decimal(resposta.data["custo_no_item"]), Decimal("12.0000"))

    def test_api_mao_de_obra_recebe_encargo_social(self):
        self.orc.encargos_sociais_percentual = Decimal("80")
        self.orc.save(update_fields=["encargos_sociais_percentual"])
        self.autenticar()
        resposta = self.client.post(
            "/api/orcamento/insumos/",
            {
                "item_orcado": self.tapume.pk, "descricao": "Carpinteiro", "unidade": "H",
                "categoria": "mao_de_obra", "coeficiente": "1", "custo_unitario": "20",
            },
            format="json",
        )
        self.assertEqual(resposta.status_code, 201, resposta.data)
        self.assertEqual(Decimal(resposta.data["custo_no_item"]), Decimal("36.0000"))

    def test_api_composicao_em_sintetico_e_recusada(self):
        self.autenticar()
        resposta = self.client.post(
            "/api/orcamento/insumos/",
            {
                "item_orcado": self.preliminares.pk, "descricao": "Qualquer",
                "unidade": "UN", "categoria": "material",
                "coeficiente": "1", "custo_unitario": "1",
            },
            format="json",
        )
        self.assertEqual(resposta.status_code, 400)

    def test_api_editar_coeficiente_muda_o_preco(self):
        self.autenticar()
        resposta = self.client.patch(
            f"/api/orcamento/insumos/{self.cimento.pk}/", {"coeficiente": "2"}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.tapume.refresh_from_db()
        self.assertEqual(self.tapume.custo_unitario, Decimal("80.0000"))

    def test_api_excluir_insumo_recompoe(self):
        self.autenticar()
        resposta = self.client.delete(f"/api/orcamento/insumos/{self.cimento.pk}/")
        self.assertEqual(resposta.status_code, 204)
        self.tapume.refresh_from_db()
        self.assertEqual(self.tapume.custo_unitario, Decimal("0.0000"))


class CamposDestravadosTests(ArvoreTestBase):
    """ORC.10e — o que a linha passou a aceitar, e sob que condição."""

    def test_codigo_eap_manual_sobrevive_ao_recalculo(self):
        self.tapume.eap_manual = True
        self.tapume.codigo_eap = "4.2.7"
        self.tapume.save(update_fields=["eap_manual", "codigo_eap"])
        planilha.recalcular_orcamento(self.orc)
        self.assertEqual(self.eap(self.tapume), "4.2.7")
        # E continua sendo o prefixo de quem pende dele.
        filho = self._linha(self.orc, "Sub", pai=self.tapume, quantidade="1", custo="1")
        planilha.recalcular_orcamento(self.orc)
        self.assertEqual(self.eap(filho), "4.2.7.1")

    def test_api_recusa_codigo_eap_sem_a_marca(self):
        """Aceitar e descartar seria pior que recusar."""
        self.autenticar()
        resposta = self.client.patch(
            f"/api/orcamento/itens/{self.tapume.pk}/", {"codigo_eap": "9.9"}, format="json",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("codigo_eap", resposta.data)

    def test_api_aceita_codigo_eap_com_a_marca(self):
        self.autenticar()
        resposta = self.client.patch(
            f"/api/orcamento/itens/{self.tapume.pk}/",
            {"codigo_eap": "9.9", "eap_manual": True}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(self.eap(self.tapume), "9.9")

    def test_api_recusa_virar_analitico_com_filhos(self):
        self.autenticar()
        resposta = self.client.patch(
            f"/api/orcamento/itens/{self.preliminares.pk}/",
            {"tipo_linha": "analitico"}, format="json",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("tipo_linha", resposta.data)

    def test_api_aceita_virar_analitico_sem_filhos(self):
        """É assim que a etapa vira verba — sem flag nova, pelo tipo da linha."""
        self.autenticar()
        resposta = self.client.patch(
            f"/api/orcamento/itens/{self.estrutura.pk}/",
            {"tipo_linha": "analitico", "unidade": "vb", "quantidade": "1",
             "custo_unitario": "15000"},
            format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.estrutura.refresh_from_db()
        self.assertEqual(self.estrutura.total_custo_direto, Decimal("15000.00"))

    def test_texto_longo_persiste(self):
        self.autenticar()
        resposta = self.client.patch(
            f"/api/orcamento/itens/{self.tapume.pk}/",
            {"texto_longo": "Chapa de compensado resinado 12 mm, h = 2,20 m."}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.tapume.refresh_from_db()
        self.assertTrue(self.tapume.texto_longo.startswith("Chapa de compensado"))


class DestravarTests(ArvoreTestBase):
    """ORC.10e — reabrir o aprovado, com nome e motivo."""

    def test_destravar_volta_para_rascunho_e_registra(self):
        planilha.aprovar_orcamento(self.orc, usuario_nome="Fulana")
        edicao.destravar_orcamento(self.orc, motivo="Erro de digitação na placa", usuario_nome="Beltrano")
        self.orc.refresh_from_db()
        self.assertEqual(self.orc.status, Orcamento.Status.RASCUNHO)
        self.assertTrue(self.orc.editavel)
        self.assertIn("Erro de digitação na placa", self.orc.observacao)
        self.assertIn("Beltrano", self.orc.observacao)
        self.assertIsNone(self.orc.aprovado_em)

    def test_destravar_exige_motivo(self):
        planilha.aprovar_orcamento(self.orc)
        with self.assertRaises(edicao.EdicaoInvalida):
            edicao.destravar_orcamento(self.orc, motivo="   ")

    def test_so_aprovado_se_destrava(self):
        with self.assertRaises(edicao.EdicaoInvalida):
            edicao.destravar_orcamento(self.orc, motivo="qualquer")

    def test_api_exige_a_permissao_propria(self):
        """Quem edita não herda o poder de descongelar a régua."""
        planilha.aprovar_orcamento(self.orc)
        self.autenticar(perms=["orcamento.orcamento.view", "orcamento.orcamento.edit"])
        resposta = self.client.post(
            f"/api/orcamento/orcamentos/{self.orc.pk}/destravar/",
            {"motivo": "Erro de digitação"}, format="json",
        )
        self.assertEqual(resposta.status_code, 403)

    def test_api_destrava_com_a_permissao(self):
        planilha.aprovar_orcamento(self.orc)
        self.autenticar(perms=[
            "orcamento.orcamento.view", "orcamento.orcamento.edit",
            "orcamento.orcamento.destravar",
        ])
        resposta = self.client.post(
            f"/api/orcamento/orcamentos/{self.orc.pk}/destravar/",
            {"motivo": "Erro de digitação"}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.orc.refresh_from_db()
        self.assertEqual(self.orc.status, Orcamento.Status.RASCUNHO)


class VerbosPelaApiTests(ArvoreTestBase):
    """As rotas de lote — escopo por tenant e tradução das exceções."""

    def test_mover_pela_api(self):
        self.autenticar()
        resposta = self.client.post(
            "/api/orcamento/itens/mover/",
            {"orcamento": self.orc.pk, "itens": [self.fundacao.pk], "operacao": "baixo"},
            format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(self.eap(self.estrutura), "2")

    def test_operacao_invalida_vira_400(self):
        self.autenticar()
        resposta = self.client.post(
            "/api/orcamento/itens/mover/",
            {"orcamento": self.orc.pk, "itens": [self.fundacao.pk], "operacao": "teletransporte"},
            format="json",
        )
        self.assertEqual(resposta.status_code, 400)

    def test_aprovado_vira_409_e_nao_400(self):
        """Documento fechado não é pedido inválido — a ORC.1 já fazia essa distinção."""
        planilha.aprovar_orcamento(self.orc)
        self.autenticar()
        resposta = self.client.post(
            "/api/orcamento/itens/mover/",
            {"orcamento": self.orc.pk, "itens": [self.fundacao.pk], "operacao": "baixo"},
            format="json",
        )
        self.assertEqual(resposta.status_code, 409)

    def test_orcamento_de_outro_tenant_vira_404(self):
        # `versao` alta de propósito: a unicidade é `(obra, versao)` e não leva
        # tenant, então v1 colidiria com a planilha deste teste.
        outro = Orcamento.objects.create(
            tenant=self.tenant_b, obra=self.obra, descricao="De outra empresa", versao=99,
        )
        self.autenticar()
        resposta = self.client.post(
            "/api/orcamento/itens/mover/",
            {"orcamento": outro.pk, "itens": [self.fundacao.pk], "operacao": "baixo"},
            format="json",
        )
        self.assertEqual(resposta.status_code, 404)

    def test_excluir_lote_devolve_o_desfazer(self):
        self.autenticar()
        resposta = self.client.post(
            "/api/orcamento/itens/excluir-lote/",
            {"orcamento": self.orc.pk, "itens": [self.preliminares.pk]}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(resposta.data["excluidas"], 3)

        volta = self.client.post(
            "/api/orcamento/itens/restaurar/",
            {"orcamento": self.orc.pk, "linhas": resposta.data["desfazer"]}, format="json",
        )
        self.assertEqual(volta.status_code, 200, volta.data)
        self.assertEqual(volta.data["restauradas"], 3)

    def test_duplicar_pela_api(self):
        self.autenticar()
        resposta = self.client.post(
            "/api/orcamento/itens/duplicar/",
            {"orcamento": self.orc.pk, "itens": [self.tapume.pk]}, format="json",
        )
        self.assertEqual(resposta.status_code, 201, resposta.data)
        self.assertEqual(resposta.data["criadas"], 1)

    def test_aplicar_percentual_pela_api(self):
        self.autenticar()
        resposta = self.client.post(
            "/api/orcamento/itens/aplicar-percentual/",
            {"orcamento": self.orc.pk, "itens": [self.tapume.pk], "percentual": "10"},
            format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(resposta.data["afetadas"], 1)


class PrecoTravadoNaReprecificacaoTests(PlanilhaTestBase):
    """ORC.10e — a trava vale também contra o lote de reprecificação."""

    def setUp(self):
        super().setUp()
        from moduloorcamento import reprecificacao as servico

        self.servico = servico
        self.base_origem = self._base()
        self.base_destino = self._base(mes=self.base_origem.mes_referencia.replace(month=8))
        self._ref(self.base_origem, codigo="92873", custo="100")
        self._ref(self.base_destino, codigo="92873", custo="130")
        self.orc = self._orcamento(base_referencial=self.base_origem)
        self.item = Item.objects.create(
            tenant=self.tenant, codigo_interno="CONC", descricao="Concretagem", unidade="M3",
        )

    def _linha_referenciada(self, *, travado):
        return ItemOrcado.objects.create(
            tenant=self.tenant, orcamento=self.orc, item=self.item, descricao="Concretagem",
            unidade="M3", quantidade=Decimal("1"), custo_unitario=Decimal("100"),
            codigo_referencia="92873", fonte_referencia="sinapi", preco_travado=travado,
        )

    def test_linha_travada_fica_fora_da_previa(self):
        self._linha_referenciada(travado=True)
        lote = self.servico.gerar_previa(self.orc, base_destino=self.base_destino)
        self.assertEqual(lote.linhas.count(), 0)

    def test_linha_solta_entra_na_previa(self):
        self._linha_referenciada(travado=False)
        lote = self.servico.gerar_previa(self.orc, base_destino=self.base_destino)
        self.assertEqual(lote.linhas.count(), 1)
