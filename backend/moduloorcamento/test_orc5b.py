# backend/moduloorcamento/test_orc5b.py
"""Testes do ORC.5b — bancos da empresa, importação, reprecificação e duplicação.

O que estas fatias têm em comum é que **todas escrevem preço**, e preço errado
num orçamento não quebra nada: vira número plausível no meio de uma peça de
licitação. Por isso os testes daqui se concentram nas travas, não no caminho
feliz — banco travado que não aceita edição, importação que não grava antes da
conferência, desfazer que restaura procedência e não só valor, duplicação que
não carrega etapa de outra obra.
"""
from datetime import date, timedelta
from decimal import Decimal

from obras.models import EtapaObra, Obra

from funcoesimpexp import importacao as motor
from funcoesimpexp.models import Importacao, LinhaImportacao
from funcoesimpexp.registro import ContextoInvalido, obter

from . import bancos, duplicacao, planilha, reprecificacao
from .models import (
    BancoPreco, BaseReferencial, ComponenteBancoPreco, Fonte, InsumoReferencia,
    ItemBancoPreco, ItemOrcado, Orcamento, PastaComposicao, Reprecificacao,
)
from .test_planilha import PlanilhaTestBase


def _csv(linhas: list[str]) -> bytes:
    return "\n".join(linhas).encode("utf-8")


CABECALHO = "codigo;descricao;unidade;preco;grupo"


class BancoPrecoTests(PlanilhaTestBase):
    """A trava do banco vale para o conteúdo, não só para o cabeçalho."""

    def setUp(self):
        super().setUp()
        self.banco = BancoPreco.objects.create(
            tenant=self.tenant, nome="Prefeitura X", uf="SP", mes_referencia=date(2026, 7, 1),
        )

    def test_travar_registra_quem_e_quando(self):
        bancos.travar(self.banco, usuario_nome="fulano")
        self.banco.refresh_from_db()
        self.assertTrue(self.banco.travado)
        self.assertEqual(self.banco.travado_por_nome, "fulano")
        self.assertIsNotNone(self.banco.travado_em)
        self.assertFalse(self.banco.editavel)

    def test_destravar_tambem_deixa_rastro(self):
        bancos.travar(self.banco, usuario_nome="fulano")
        bancos.destravar(self.banco, usuario_nome="ciclano")
        self.banco.refresh_from_db()
        self.assertFalse(self.banco.travado)
        self.assertEqual(self.banco.travado_por_nome, "ciclano")
        self.assertIsNone(self.banco.travado_em)

    def test_banco_travado_recusa_copia_da_base(self):
        base = BaseReferencial.objects.create(
            fonte=Fonte.SINAPI, uf="SP", mes_referencia=date(2026, 7, 1),
        )
        referencia = InsumoReferencia.objects.create(
            base=base, codigo="123", descricao="CIMENTO", unidade="KG",
            custo_unitario=Decimal("0.72"),
        )
        bancos.travar(self.banco)
        with self.assertRaises(bancos.BancoTravado):
            bancos.copiar_da_base_publica([referencia], banco_destino=self.banco)

    def test_copiar_da_base_publica_nao_altera_a_base(self):
        """O pedido explícito: editar cópia sem tocar em SINAPI/ORSE."""
        base = BaseReferencial.objects.create(
            fonte=Fonte.SINAPI, uf="SP", mes_referencia=date(2026, 7, 1),
        )
        composicao = InsumoReferencia.objects.create(
            base=base, tipo=InsumoReferencia.Tipo.COMPOSICAO, codigo="87879",
            descricao="CHAPISCO", unidade="M2", custo_unitario=Decimal("5.42"),
        )
        bancos.copiar_da_base_publica([composicao], banco_destino=self.banco)

        copia = ItemBancoPreco.objects.get(banco=self.banco, codigo="87879")
        copia.custo_unitario = Decimal("9.99")
        copia.save()

        composicao.refresh_from_db()
        self.assertEqual(composicao.custo_unitario, Decimal("5.4200"))

    def test_recontar_atualiza_o_desnormalizado(self):
        ItemBancoPreco.objects.create(
            tenant=self.tenant, banco=self.banco, codigo="A", descricao="A",
            unidade="UN", custo_unitario=Decimal("1"),
        )
        bancos.recontar(self.banco)
        self.banco.refresh_from_db()
        self.assertEqual(self.banco.total_itens, 1)

    def test_duplicar_item_leva_a_composicao_junto(self):
        destino = BancoPreco.objects.create(tenant=self.tenant, nome="Banco Obra Alfa")
        pai = ItemBancoPreco.objects.create(
            tenant=self.tenant, banco=self.banco, codigo="C1", descricao="COMPOSICAO",
            unidade="M2", tipo=InsumoReferencia.Tipo.COMPOSICAO, custo_unitario=Decimal("10"),
        )
        filho = ItemBancoPreco.objects.create(
            tenant=self.tenant, banco=self.banco, codigo="I1", descricao="INSUMO",
            unidade="KG", custo_unitario=Decimal("2"),
        )
        ComponenteBancoPreco.objects.create(
            tenant=self.tenant, composicao=pai, filho=filho, coeficiente=Decimal("3"),
        )

        clone = bancos.duplicar_item(pai, banco_destino=destino)
        self.assertEqual(clone.banco_id, destino.pk)
        self.assertEqual(ComponenteBancoPreco.objects.filter(composicao=clone).count(), 1)
        # O insumo foi trazido junto, senão a composição clonada não teria custo.
        self.assertTrue(ItemBancoPreco.objects.filter(banco=destino, codigo="I1").exists())

    def test_pasta_pertence_ao_banco(self):
        pasta = PastaComposicao.objects.create(
            tenant=self.tenant, banco=self.banco, nome="Estrutura",
        )
        self.assertEqual(pasta.banco_id, self.banco.pk)


class ImportacaoConferenciaTests(PlanilhaTestBase):
    """Nada é gravado antes da conferência — agora provado **pelo motor**.

    Depois do IE.1 a importação de preço não tem mais código próprio: o que
    existe é a declaração `orcamento.banco_preco` ([impexp.py](impexp.py)) rodando
    no `funcoesimpexp`. Estes testes seguem aqui, e não no motor, porque o que
    eles verificam é a **declaração do Orçamento** — que a trava do banco é
    respeitada, que o preço atualiza em vez de duplicar, que o total do banco
    reconta. O motor tem os seus, com um destino de mentira.
    """

    def setUp(self):
        super().setUp()
        self.banco = BancoPreco.objects.create(tenant=self.tenant, nome="Prefeitura Y")

    @property
    def recurso(self):
        return obter("orcamento.banco_preco").com_contexto({"banco": self.banco.pk})

    def _preparar(self, linhas, **kwargs):
        return motor.preparar(
            recurso=self.recurso,
            conteudo=_csv([CABECALHO, *linhas]),
            nome_arquivo="tabela.csv",
            tenant_id=self.tenant.id,
            **kwargs,
        )

    def test_classifica_nova_duplicada_e_invalida(self):
        ItemBancoPreco.objects.create(
            tenant=self.tenant, banco=self.banco, codigo="0002",
            descricao="JA EXISTE", unidade="UN", custo_unitario=Decimal("1"),
        )
        registro = self._preparar([
            "0001;AREIA MEDIA;M3;89,50;Agregados",
            "0002;JA EXISTE;UN;1,00;",
            ";SEM CODIGO;UN;5,00;",
            "0004;;M2;3,00;",
            "0001;REPETIDO NO ARQUIVO;M3;89,50;",
        ])

        self.assertEqual(registro.status, Importacao.Status.CONFERINDO)
        self.assertEqual(registro.total_linhas, 5)

        # Indexado por número da linha, não por código: a 5ª repete o código da
        # 2ª de propósito, e é exatamente esse caso que precisa cair em inválida.
        situacoes = dict(registro.linhas.values_list("numero", "situacao"))
        self.assertEqual(situacoes[2], LinhaImportacao.Situacao.NOVA)        # 0001
        self.assertEqual(situacoes[3], LinhaImportacao.Situacao.DUPLICADA)   # 0002, já no banco
        self.assertEqual(situacoes[4], LinhaImportacao.Situacao.INVALIDA)    # sem código
        self.assertEqual(situacoes[5], LinhaImportacao.Situacao.INVALIDA)    # sem descrição
        self.assertEqual(situacoes[6], LinhaImportacao.Situacao.INVALIDA)    # código repetido
        self.assertIn("repetida", registro.linhas.get(numero=6).motivo.lower())

    def test_preparar_nao_grava_nada_no_destino(self):
        self._preparar(["0001;AREIA;M3;89,50;"])
        self.assertEqual(ItemBancoPreco.objects.filter(banco=self.banco).count(), 0)

    def test_invalida_nasce_desmarcada_e_nunca_grava(self):
        registro = self._preparar([
            "0001;AREIA;M3;89,50;",
            ";SEM CODIGO;UN;5,00;",
        ])
        invalida = registro.linhas.get(situacao=LinhaImportacao.Situacao.INVALIDA)
        self.assertFalse(invalida.aceita)

        # Mesmo marcando à força, aplicar não grava a inválida.
        registro.linhas.update(aceita=True)
        motor.aplicar(registro, recurso=self.recurso)
        self.assertEqual(ItemBancoPreco.objects.filter(banco=self.banco).count(), 1)

    def test_confirmar_tudo_grava_as_validas(self):
        registro = self._preparar([
            "0001;AREIA MEDIA;M3;89,50;Agregados",
            "0002;BRITA 1;M3;112,40;Agregados",
        ])
        motor.aplicar(registro, recurso=self.recurso)
        registro.refresh_from_db()
        self.assertEqual(registro.status, Importacao.Status.APLICADA)
        self.assertEqual(ItemBancoPreco.objects.filter(banco=self.banco).count(), 2)
        self.banco.refresh_from_db()
        self.assertEqual(self.banco.total_itens, 2, "a declaração reconta o banco")

    def test_confirmar_selecao_grava_so_o_escolhido(self):
        registro = self._preparar([
            "0001;AREIA MEDIA;M3;89,50;",
            "0002;BRITA 1;M3;112,40;",
        ])
        escolhida = registro.linhas.get(chave="0001")
        motor.marcar(registro, aceitar=False)
        motor.marcar(registro, aceitar=True, linhas=[escolhida.linha_id])
        motor.aplicar(registro, recurso=self.recurso)

        codigos = set(
            ItemBancoPreco.objects.filter(banco=self.banco).values_list("codigo", flat=True)
        )
        self.assertEqual(codigos, {"0001"})

    def test_negar_tudo_nao_grava_e_deixa_rastro(self):
        registro = self._preparar(["0001;AREIA;M3;89,50;"])
        motor.descartar(registro)
        registro.refresh_from_db()
        self.assertEqual(registro.status, Importacao.Status.DESCARTADA)
        self.assertEqual(ItemBancoPreco.objects.filter(banco=self.banco).count(), 0)
        # O registro continua existindo — é o rastro do que foi recusado.
        self.assertTrue(Importacao.objects.filter(pk=registro.pk).exists())

    def test_duplicada_aceita_atualiza_o_preco(self):
        ItemBancoPreco.objects.create(
            tenant=self.tenant, banco=self.banco, codigo="0001",
            descricao="AREIA", unidade="M3", custo_unitario=Decimal("50.00"),
        )
        registro = self._preparar(["0001;AREIA MEDIA;M3;89,50;"])
        motor.aplicar(registro, recurso=self.recurso)
        item = ItemBancoPreco.objects.get(banco=self.banco, codigo="0001")
        self.assertEqual(item.custo_unitario, Decimal("89.5000"))

    def test_desfazer_devolve_o_preco_anterior(self):
        """R6 — o lote inteiro volta, criação apaga e atualização restaura."""
        ItemBancoPreco.objects.create(
            tenant=self.tenant, banco=self.banco, codigo="0001",
            descricao="AREIA", unidade="M3", custo_unitario=Decimal("50.00"),
        )
        registro = self._preparar([
            "0001;AREIA MEDIA;M3;89,50;",
            "0002;BRITA 1;M3;112,40;",
        ])
        motor.aplicar(registro, recurso=self.recurso)
        motor.desfazer(registro, recurso=self.recurso)

        antigo = ItemBancoPreco.objects.get(banco=self.banco, codigo="0001")
        self.assertEqual(antigo.custo_unitario, Decimal("50.0000"))
        self.assertEqual(antigo.descricao, "AREIA", "restaura a linha inteira, não só o preço")
        self.assertFalse(
            ItemBancoPreco.objects.filter(banco=self.banco, codigo="0002").exists(),
            "desfazer uma criação é apagar",
        )

    def test_arquivo_sem_cabecalho_reconhecivel_pede_de_para(self):
        """Mudou de forma no IE.1: era registro de ERRO, virou 422 com o que se viu.

        É melhor: o operador recebe os cabeçalhos lidos e mapeia à mão (R4), em
        vez de só descobrir que "não deu".
        """
        with self.assertRaises(motor.ColunasNaoReconhecidas) as caso:
            motor.preparar(
                recurso=self.recurso, tenant_id=self.tenant.id,
                conteudo=_csv(["a;b;c", "1;2;3"]), nome_arquivo="ruim.csv",
            )
        self.assertTrue(caso.exception.cabecalhos_vistos)
        self.assertIn("Código", caso.exception.obrigatorias)

    def test_formato_nao_suportado_vira_registro_de_erro(self):
        registro = motor.preparar(
            recurso=self.recurso, conteudo=b"qualquer",
            nome_arquivo="tabela.docx", tenant_id=self.tenant.id,
        )
        self.assertEqual(registro.status, Importacao.Status.ERRO)
        self.assertIn("Formato não suportado", registro.mensagem)

    def test_banco_travado_recusa_importacao(self):
        """A trava vale na porta: `validar_contexto` roda antes de ler o arquivo."""
        bancos.travar(self.banco)
        with self.assertRaises(ContextoInvalido):
            self.recurso.validar_contexto({"banco": self.banco.pk}, None, self.tenant.id)

    def test_banco_de_outro_tenant_nao_e_destino(self):
        alheio = BancoPreco.objects.create(tenant=self.tenant_b, nome="Do vizinho")
        recurso = obter("orcamento.banco_preco")
        with self.assertRaises(ContextoInvalido):
            recurso.validar_contexto({"banco": alheio.pk}, None, self.tenant.id)

    def test_importacao_ja_decidida_nao_aceita_segunda_decisao(self):
        registro = self._preparar(["0001;AREIA;M3;89,50;"])
        motor.aplicar(registro, recurso=self.recurso)
        with self.assertRaises(motor.ImportacaoInvalida):
            motor.descartar(registro)


class QuotaDeImportacaoTests(PlanilhaTestBase):
    """O teto do plano é do dono do produto (payment/), não do código.

    O de **operação** (`importacao_linhas`) é do motor e vale para todo recurso;
    o de **acervo** (`banco_preco_linhas`) é do Orçamento e chega pelo gancho
    `checar_quota_objeto` da declaração. Os dois continuam valendo depois do IE.1.
    """

    def setUp(self):
        super().setUp()
        self.banco = BancoPreco.objects.create(tenant=self.tenant, nome="Prefeitura Z")

    @property
    def recurso(self):
        return obter("orcamento.banco_preco").com_contexto({"banco": self.banco.pk})

    def test_teto_por_importacao_barra_antes_de_materializar(self):
        with self.assertRaises(motor.LimiteDoPlano) as caso:
            motor.preparar(
                recurso=self.recurso, tenant_id=self.tenant.id,
                conteudo=_csv([CABECALHO, "1;A;UN;1,00;", "2;B;UN;2,00;", "3;C;UN;3,00;"]),
                nome_arquivo="grande.csv", limites={"importacao_linhas": 2},
            )
        self.assertEqual(caso.exception.quota, "importacao_linhas")
        # Nada foi materializado: nem a importação, nem as linhas.
        self.assertEqual(Importacao.objects.count(), 0)
        self.assertEqual(LinhaImportacao.objects.count(), 0)

    def test_teto_acumulado_considera_o_que_ja_existe(self):
        for n in range(3):
            ItemBancoPreco.objects.create(
                tenant=self.tenant, banco=self.banco, codigo=f"X{n}",
                descricao="X", unidade="UN", custo_unitario=Decimal("1"),
            )
        with self.assertRaises(motor.LimiteDoPlano) as caso:
            motor.preparar(
                recurso=self.recurso, tenant_id=self.tenant.id,
                conteudo=_csv([CABECALHO, "1;A;UN;1,00;"]),
                nome_arquivo="mais.csv", limites={"banco_preco_linhas": 3},
            )
        self.assertEqual(caso.exception.quota, "banco_preco_linhas")

    def test_sem_a_claim_nao_trava(self):
        """Fail-open logado, como as demais camadas de limite do projeto."""
        registro = motor.preparar(
            recurso=self.recurso, tenant_id=self.tenant.id,
            conteudo=_csv([CABECALHO, "1;A;UN;1,00;"]),
            nome_arquivo="ok.csv", limites=None,
        )
        self.assertEqual(registro.status, Importacao.Status.CONFERINDO)


class ReprecificacaoTests(PlanilhaTestBase):
    """Trocar a data-base: prévia, aplicar, desfazer — sem virar versão."""

    def setUp(self):
        super().setUp()
        self.base_jun = BaseReferencial.objects.create(
            fonte=Fonte.SINAPI, uf="SP", mes_referencia=date(2026, 6, 1),
        )
        self.base_jul = BaseReferencial.objects.create(
            fonte=Fonte.SINAPI, uf="SP", mes_referencia=date(2026, 7, 1),
        )
        for base, preco in ((self.base_jun, "10.00"), (self.base_jul, "12.00")):
            InsumoReferencia.objects.create(
                base=base, codigo="0001", descricao="CIMENTO", unidade="KG",
                custo_unitario=Decimal(preco),
            )

        self.orcamento = self._orcamento(base_referencial=self.base_jun, data_base=date(2026, 6, 1))
        self.linha = self._linha(
            self.orcamento, "Cimento", quantidade="100", custo="10.00",
        )
        self.linha.fonte_referencia = Fonte.SINAPI
        self.linha.codigo_referencia = "0001"
        self.linha.data_base_preco = date(2026, 6, 1)
        self.linha.save()
        planilha.recalcular_orcamento(self.orcamento)
        self.orcamento.refresh_from_db()

    def test_previa_nao_altera_a_planilha(self):
        lote = reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jul)
        self.assertEqual(lote.status, Reprecificacao.Status.PREVIA)
        self.assertEqual(lote.linhas_afetadas, 1)

        self.linha.refresh_from_db()
        self.assertEqual(self.linha.custo_unitario, Decimal("10.0000"))

    def test_aplicar_troca_preco_data_base_e_recalcula(self):
        lote = reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jul)
        reprecificacao.aplicar(lote)

        self.linha.refresh_from_db()
        self.orcamento.refresh_from_db()
        self.assertEqual(self.linha.custo_unitario, Decimal("12.0000"))
        self.assertEqual(self.linha.data_base_preco, date(2026, 7, 1))
        self.assertEqual(self.orcamento.data_base, date(2026, 7, 1))
        self.assertEqual(self.orcamento.custo_direto_total, Decimal("1200.00"))

    def test_desfazer_restaura_preco_e_procedencia(self):
        lote = reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jul)
        reprecificacao.aplicar(lote)
        reprecificacao.desfazer(lote)

        self.linha.refresh_from_db()
        self.orcamento.refresh_from_db()
        self.assertEqual(self.linha.custo_unitario, Decimal("10.0000"))
        # Procedência também volta — rastro é o que a auditoria confere.
        self.assertEqual(self.linha.data_base_preco, date(2026, 6, 1))
        self.assertEqual(self.orcamento.custo_direto_total, Decimal("1000.00"))
        lote.refresh_from_db()
        self.assertEqual(lote.status, Reprecificacao.Status.DESFEITA)

    def test_aplicar_selecao_deixa_o_resto_intacto(self):
        outra = self._linha(self.orcamento, "Outro", quantidade="10", custo="10.00")
        outra.fonte_referencia = Fonte.SINAPI
        outra.codigo_referencia = "0001"
        outra.save()
        planilha.recalcular_orcamento(self.orcamento)

        lote = reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jul)
        escolhida = lote.linhas.get(item_orcado=self.linha)
        reprecificacao.aplicar(lote, selecionadas=[escolhida.linha_id])

        self.linha.refresh_from_db()
        outra.refresh_from_db()
        self.assertEqual(self.linha.custo_unitario, Decimal("12.0000"))
        self.assertEqual(outra.custo_unitario, Decimal("10.0000"))

    def test_data_de_corte_preserva_preco_mais_novo(self):
        self.linha.data_base_preco = date(2026, 8, 1)
        self.linha.save()
        lote = reprecificacao.gerar_previa(
            self.orcamento, base_destino=self.base_jul, somente_ate=date(2026, 7, 1),
        )
        self.assertEqual(lote.linhas_afetadas, 0)

    def test_data_de_corte_aceita_a_string_que_a_api_manda(self):
        """JSON não tem tipo data: o POST manda `"2026-07-01"`, e comparar isso
        com um `date` derrubava a requisição com 500. Os testes não viam porque
        chamavam o serviço com `date` já pronto."""
        self.linha.data_base_preco = date(2026, 8, 1)
        self.linha.save()
        lote = reprecificacao.gerar_previa(
            self.orcamento, base_destino=self.base_jul, somente_ate="2026-07-01",
        )
        self.assertEqual(lote.linhas_afetadas, 0)

    def test_data_de_corte_aceita_o_formato_brasileiro(self):
        self.linha.data_base_preco = date(2026, 8, 1)
        self.linha.save()
        lote = reprecificacao.gerar_previa(
            self.orcamento, base_destino=self.base_jul, somente_ate="01/07/2026",
        )
        self.assertEqual(lote.linhas_afetadas, 0)

    def test_data_de_corte_ilegivel_e_pedido_ruim_e_nao_erro_de_servidor(self):
        with self.assertRaises(reprecificacao.ReprecificacaoInvalida):
            reprecificacao.gerar_previa(
                self.orcamento, base_destino=self.base_jul, somente_ate="ontem",
            )

    def test_orcamento_aprovado_nao_reprecifica(self):
        planilha.aprovar_orcamento(self.orcamento)
        self.orcamento.refresh_from_db()
        with self.assertRaises(planilha.OrcamentoNaoEditavel):
            reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jul)

    def test_desfazer_fora_de_ordem_e_recusado(self):
        primeiro = reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jul)
        reprecificacao.aplicar(primeiro)
        segundo = reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jun)
        reprecificacao.aplicar(segundo)

        with self.assertRaises(reprecificacao.ReprecificacaoInvalida):
            reprecificacao.desfazer(primeiro)

    def test_previa_nova_descarta_a_anterior(self):
        reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jul)
        reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jun)
        abertas = Reprecificacao.objects.filter(
            orcamento=self.orcamento, status=Reprecificacao.Status.PREVIA
        )
        self.assertEqual(abertas.count(), 1)

    def test_sem_destino_recusa(self):
        with self.assertRaises(reprecificacao.ReprecificacaoInvalida):
            reprecificacao.gerar_previa(self.orcamento)


class ItemDescontinuadoTests(PlanilhaTestBase):
    """A SINAPI aposenta item todo mês, e a planilha não pode fingir que não viu.

    Antes, `gerar_previa` pulava em silêncio o código ausente na publicação de
    destino: a linha ficava com o preço velho, o cabeçalho passava a anunciar a
    data-base nova, e a peça de licitação saía dizendo "julho" com preço de
    junho dentro. O defeito não é o número — é o silêncio.
    """

    def setUp(self):
        super().setUp()
        self.base_jun = BaseReferencial.objects.create(
            fonte=Fonte.SINAPI, uf="SP", mes_referencia=date(2026, 6, 1),
        )
        self.base_jul = BaseReferencial.objects.create(
            fonte=Fonte.SINAPI, uf="SP", mes_referencia=date(2026, 7, 1),
        )
        # "0001" sobrevive para julho; "0002" é aposentado pela fonte.
        for base, preco in ((self.base_jun, "10.00"), (self.base_jul, "12.00")):
            InsumoReferencia.objects.create(
                base=base, codigo="0001", descricao="CIMENTO", unidade="KG",
                custo_unitario=Decimal(preco),
            )
        InsumoReferencia.objects.create(
            base=self.base_jun, codigo="0002", descricao="TIJOLO MACICO", unidade="UN",
            custo_unitario=Decimal("2.00"),
        )

        self.orcamento = self._orcamento(
            base_referencial=self.base_jun, data_base=date(2026, 6, 1),
        )
        self.viva = self._linha(self.orcamento, "Cimento", quantidade="100", custo="10.00")
        self.aposentada = self._linha(self.orcamento, "Tijolo", quantidade="50", custo="2.00")
        for linha, codigo in ((self.viva, "0001"), (self.aposentada, "0002")):
            linha.fonte_referencia = Fonte.SINAPI
            linha.codigo_referencia = codigo
            linha.data_base_preco = date(2026, 6, 1)
            linha.save()
        planilha.recalcular_orcamento(self.orcamento)
        self.orcamento.refresh_from_db()

    def _linha_do(self, item):
        lote = reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jul)
        return lote, lote.linhas.get(item_orcado=item)

    def test_item_aposentado_aparece_na_previa_em_vez_de_sumir(self):
        lote, linha = self._linha_do(self.aposentada)
        self.assertTrue(linha.descontinuado)
        self.assertFalse(linha.selecionada)
        self.assertIn("0002", linha.motivo)
        self.assertEqual(lote.linhas_descontinuadas, 1)

    def test_descontinuada_nao_conta_como_afetada_nem_move_o_total(self):
        lote = reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jul)
        # Só o cimento muda de preço: 100 × (12 − 10) = 200 sobre o total.
        self.assertEqual(lote.linhas_afetadas, 1)
        self.assertEqual(lote.linhas.count(), 2)
        self.assertEqual(
            lote.total_depois - lote.total_antes, Decimal("200.00"),
        )

    def test_descontinuada_nunca_e_aplicada_mesmo_se_pedida(self):
        """Marcar a linha na seleção não pode gravar preço velho como se fosse novo."""
        lote, linha = self._linha_do(self.aposentada)
        reprecificacao.aplicar(lote, selecionadas=[linha.linha_id])

        self.aposentada.refresh_from_db()
        linha.refresh_from_db()
        self.assertFalse(linha.aplicada)
        self.assertFalse(linha.selecionada)
        self.assertEqual(self.aposentada.custo_unitario, Decimal("2.0000"))
        # A procedência continua sendo junho — é o que torna o aviso possível.
        self.assertEqual(self.aposentada.data_base_preco, date(2026, 6, 1))

    def test_orcamento_avisa_a_linha_que_ficou_para_tras(self):
        lote = reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jul)
        reprecificacao.aplicar(lote)

        self.orcamento.refresh_from_db()
        self.assertEqual(self.orcamento.data_base, date(2026, 7, 1))

        aviso = reprecificacao.avisos_de_data_base(self.orcamento)
        self.assertTrue(aviso["tem_aviso"])
        self.assertEqual(aviso["linhas_atrasadas"], 1)
        self.assertEqual(aviso["linhas"][0]["codigo_referencia"], "0002")
        self.assertIn("07/2026", aviso["mensagem"])

    def test_sem_linha_atrasada_nao_ha_aviso(self):
        """O aviso some sozinho quando a planilha volta a ser honesta."""
        self.aposentada.delete()
        planilha.recalcular_orcamento(self.orcamento)
        self.orcamento.refresh_from_db()

        lote = reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jul)
        reprecificacao.aplicar(lote)
        self.orcamento.refresh_from_db()

        aviso = reprecificacao.avisos_de_data_base(self.orcamento)
        self.assertFalse(aviso["tem_aviso"])
        self.assertEqual(aviso["linhas_atrasadas"], 0)

    def test_desfazer_leva_a_descontinuada_junto_e_zera_o_aviso(self):
        lote = reprecificacao.gerar_previa(self.orcamento, base_destino=self.base_jul)
        reprecificacao.aplicar(lote)
        reprecificacao.desfazer(lote)

        self.orcamento.refresh_from_db()
        self.assertEqual(self.orcamento.data_base, date(2026, 6, 1))
        # Cabeçalho voltou para junho, e a linha aposentada sempre esteve em
        # junho — logo não há mais nada atrasado para avisar.
        aviso = reprecificacao.avisos_de_data_base(self.orcamento)
        self.assertFalse(aviso["tem_aviso"])


class DuplicacaoTests(PlanilhaTestBase):
    """Duplicar é planilha nova, não revisão."""

    def setUp(self):
        super().setUp()
        self.orcamento = self._orcamento()
        grupo = self._linha(
            self.orcamento, "INFRAESTRUTURA", tipo=ItemOrcado.TipoLinha.SINTETICO, ordem=1,
        )
        self._linha(
            self.orcamento, "Estaca", pai=grupo, quantidade="10", custo="100",
            etapa=self.fundacao, ordem=1,
        )
        planilha.recalcular_orcamento(self.orcamento)
        self.orcamento.refresh_from_db()

    def test_duplicata_nasce_rascunho_na_proxima_versao(self):
        planilha.aprovar_orcamento(self.orcamento)
        self.orcamento.refresh_from_db()

        novo, _ = duplicacao.duplicar_orcamento(self.orcamento)
        self.assertEqual(novo.status, Orcamento.Status.RASCUNHO)
        self.assertEqual(novo.versao, self.orcamento.versao + 1)
        self.assertIsNone(novo.orcamento_origem_id)
        # A origem NÃO é rebaixada — isso é revisão, não duplicação.
        self.orcamento.refresh_from_db()
        self.assertEqual(self.orcamento.status, Orcamento.Status.APROVADO)

    def test_duplicata_copia_arvore_e_totais(self):
        novo, _ = duplicacao.duplicar_orcamento(self.orcamento)
        self.assertEqual(
            ItemOrcado.objects.filter(orcamento=novo).count(),
            ItemOrcado.objects.filter(orcamento=self.orcamento).count(),
        )
        self.assertEqual(novo.custo_direto_total, self.orcamento.custo_direto_total)
        # A hierarquia sobreviveu.
        self.assertTrue(ItemOrcado.objects.filter(orcamento=novo, pai__isnull=False).exists())

    def test_mudar_de_obra_descarta_a_etapa_e_avisa(self):
        outra = Obra.objects.create(
            tenant=self.tenant, nome_obra="Residencial Beta", endereco="Rua B, 200",
        )
        novo, sem_etapa = duplicacao.duplicar_orcamento(self.orcamento, obra_destino=outra)

        self.assertEqual(sem_etapa, 1)
        self.assertEqual(novo.obra_id, outra.pk)
        self.assertFalse(
            ItemOrcado.objects.filter(orcamento=novo, etapa__isnull=False).exists()
        )
        resumo = duplicacao.resumo_da_duplicata(novo, sem_etapa)
        self.assertIn("etapa", resumo["aviso_etapa"])

    def test_mesma_obra_mantem_a_etapa(self):
        novo, sem_etapa = duplicacao.duplicar_orcamento(self.orcamento)
        self.assertEqual(sem_etapa, 0)
        self.assertTrue(
            ItemOrcado.objects.filter(orcamento=novo, etapa=self.fundacao).exists()
        )

    def test_copiar_itens_traz_a_subarvore(self):
        destino = self._orcamento(descricao="Destino", versao=99)
        grupo = ItemOrcado.objects.filter(
            orcamento=self.orcamento, tipo_linha=ItemOrcado.TipoLinha.SINTETICO
        ).first()

        copiadas, _ = duplicacao.copiar_itens(destino=destino, itens=[grupo])
        # O sintético e o filho dele: copiar o agrupador sozinho somaria zero.
        self.assertEqual(copiadas, 2)

    def test_copiar_para_orcamento_aprovado_e_recusado(self):
        destino = self._orcamento(descricao="Fechado", versao=98)
        self._linha(destino, "x", quantidade="1", custo="1")
        planilha.aprovar_orcamento(destino)
        destino.refresh_from_db()

        linha = ItemOrcado.objects.filter(orcamento=self.orcamento).first()
        with self.assertRaises(planilha.OrcamentoNaoEditavel):
            duplicacao.copiar_itens(destino=destino, itens=[linha])

    def test_copiar_de_dois_orcamentos_de_uma_vez_e_recusado(self):
        outro = self._orcamento(descricao="Outro", versao=97)
        linha_outro = self._linha(outro, "y", quantidade="1", custo="1")
        linha_daqui = ItemOrcado.objects.filter(orcamento=self.orcamento).first()
        destino = self._orcamento(descricao="Destino", versao=96)

        with self.assertRaises(duplicacao.CopiaInvalida):
            duplicacao.copiar_itens(destino=destino, itens=[linha_daqui, linha_outro])


class ExportacaoTests(PlanilhaTestBase):
    """A peça que sai do sistema precisa sair — e com o cabeçalho conferível."""

    def setUp(self):
        super().setUp()
        self.orcamento = self._orcamento(bdi_percentual=Decimal("22.5"))
        grupo = self._linha(
            self.orcamento, "INFRAESTRUTURA", tipo=ItemOrcado.TipoLinha.SINTETICO, ordem=1,
        )
        self._linha(self.orcamento, "Estaca", pai=grupo, quantidade="10", custo="100", ordem=1)
        planilha.recalcular_orcamento(self.orcamento)
        self.orcamento.refresh_from_db()

    def test_xlsx_sai_com_conteudo(self):
        from . import exportacao

        conteudo = exportacao.planilha_xlsx(self.orcamento)
        self.assertGreater(len(conteudo), 2000)
        # Assinatura de arquivo XLSX (zip).
        self.assertEqual(conteudo[:2], b"PK")

    def test_cabecalho_traz_o_que_torna_a_peca_conferivel(self):
        from . import exportacao

        cabecalho = exportacao.contexto_do_cabecalho(self.orcamento)
        for campo in ("obra", "versao", "data_base", "regime_encargos", "bdi", "valor_total"):
            self.assertIn(campo, cabecalho)

    def test_nome_do_arquivo_e_legivel(self):
        from . import exportacao

        nome = exportacao.nome_do_arquivo(self.orcamento, sufixo="analitica", extensao="xlsx")
        self.assertTrue(nome.endswith(".xlsx"))
        self.assertNotIn(" ", nome)


class GateDeApiTests(PlanilhaTestBase):
    """Camada 2 nos ViewSets do ORC.5b — a regressão que quase passou.

    A 1ª versão declarou `permission_map = {"GET": …}` nos cinco ViewSets novos.
    `RequirePermission._needed` só entende as chaves `view`/`write`; com `GET` ele
    devolvia `None`, e `has_permission` trata `None` como "não exige" — resultado:
    **leitura sem gate** do banco de preço da empresa para qualquer usuário com o
    módulo. É a mesma família do achado D5 (broken access control), e a suíte
    ficava verde porque nenhum teste exercia o caminho negado.
    """

    def setUp(self):
        super().setUp()
        self.banco = BancoPreco.objects.create(tenant=self.tenant, nome="Prefeitura W")

    def test_sem_permissao_de_leitura_nao_lista_bancos(self):
        self.autenticar(perms=["orcamento.orcamento.view"])
        self.assertEqual(self.client.get("/api/orcamento/bancos/").status_code, 403)

    def test_com_permissao_de_leitura_lista(self):
        self.autenticar(perms=["orcamento.banco.view"])
        self.assertEqual(self.client.get("/api/orcamento/bancos/").status_code, 200)

    def test_quem_so_ve_a_base_publica_nao_ve_o_banco_da_empresa(self):
        """ORC.9 — as duas leituras se separaram. Consultar SINAPI é uma coisa;
        ver a tabela de preço que a casa negociou é outra, e é dado comercial."""
        self.autenticar(perms=["orcamento.base.view"])
        self.assertEqual(self.client.get("/api/orcamento/bancos/").status_code, 403)

    def test_sem_o_modulo_nao_passa(self):
        self.autenticar(modules=(), perms=["orcamento.banco.view"])
        self.assertEqual(self.client.get("/api/orcamento/bancos/").status_code, 403)

    def test_leitura_nao_autoriza_escrita(self):
        self.autenticar(perms=["orcamento.banco.view"])
        resposta = self.client.post("/api/orcamento/bancos/", {"nome": "Novo"}, format="json")
        self.assertEqual(resposta.status_code, 403)

    def test_quem_orca_nao_mexe_no_banco_de_preco(self):
        """ORC.9 — manter a régua deixou de andar junto com montar a planilha."""
        self.autenticar(perms=["orcamento.orcamento.edit", "orcamento.banco.view"])
        resposta = self.client.post("/api/orcamento/bancos/", {"nome": "Novo"}, format="json")
        self.assertEqual(resposta.status_code, 403)

    def test_quem_cuida_do_banco_escreve(self):
        self.autenticar(perms=["orcamento.banco.view", "orcamento.banco.edit"])
        resposta = self.client.post("/api/orcamento/bancos/", {"nome": "Novo"}, format="json")
        self.assertEqual(resposta.status_code, 201)

    def test_itens_e_pastas_tambem_exigem_leitura(self):
        self.autenticar(perms=["orcamento.orcamento.view"])
        for rota in ("itens-banco", "pastas", "componentes-banco"):
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(f"/api/orcamento/{rota}/").status_code, 403)

    # --- IE.1: a importação saiu de `/api/orcamento/importacoes/` e passou a
    # viver no motor. O gate mudou de forma junto: onde havia uma permissão de
    # ação, agora vale a regra §3 do funcoesimpexp — **acesso total ou nada**.

    def test_importar_exige_o_conjunto_inteiro_de_permissoes(self):
        """Meia permissão bloqueia: não existe arquivo parcial (R11)."""
        self.autenticar(perms=["orcamento.banco.view"])  # falta `.edit`
        resposta = self.client.post(
            "/api/impexp/orcamento.banco_preco/importar/", {}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertIn("orcamento.banco.edit", str(resposta.data))

    def test_recursos_some_com_o_que_a_pessoa_nao_pode_operar(self):
        """O frontend não mostra botão que daria 403 no clique (§10)."""
        self.autenticar(perms=["orcamento.banco.view"])
        ids = {r["id"] for r in self.client.get("/api/impexp/recursos/").data["recursos"]}
        self.assertNotIn("orcamento.banco_preco", ids)

        self.autenticar(perms=["orcamento.banco.view", "orcamento.banco.edit"])
        ids = {r["id"] for r in self.client.get("/api/impexp/recursos/").data["recursos"]}
        self.assertIn("orcamento.banco_preco", ids)

    def test_base_mae_e_recusada_para_quem_nao_e_dono_da_plataforma(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.autenticar(perms=[
            "orcamento.base.view", "orcamento.base.adotar",
            "orcamento.banco.view", "orcamento.banco.edit",
        ])
        arquivo = SimpleUploadedFile(
            "t.csv", _csv([CABECALHO, "1;A;UN;1,00;"]), content_type="text/csv",
        )
        resposta = self.client.post(
            "/api/impexp/orcamento.base_referencial/importar/",
            {"arquivo": arquivo}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("dono da plataforma", str(resposta.data))

    def test_banco_travado_recusa_na_porta_e_nao_depois_de_ler(self):
        bancos.travar(self.banco)
        self.autenticar(perms=["orcamento.banco.view", "orcamento.banco.edit"])
        resposta = self.client.post(
            "/api/impexp/orcamento.banco_preco/importar/",
            {"contexto": f'{{"banco": {self.banco.pk}}}'}, format="multipart",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("travad", str(resposta.data).lower())


class IsolamentoEntreTenantsTests(PlanilhaTestBase):
    """Banco de preço de uma empresa é dado comercial — não pode vazar."""

    def test_banco_de_outro_tenant_nao_aparece_no_resumo(self):
        from nucleo.models import Tenant

        outro = Tenant.objects.create(nome="Outra Construtora", slug="outra")
        BancoPreco.objects.create(tenant=outro, nome="Banco da concorrente")
        BancoPreco.objects.create(tenant=self.tenant, nome="Meu banco")

        nomes = [b["nome"] for b in bancos.resumo(self.tenant.id)]
        self.assertEqual(nomes, ["Meu banco"])

    def test_contagem_de_linhas_conta_so_o_proprio_tenant(self):
        from nucleo.models import Tenant

        outro = Tenant.objects.create(nome="Outra", slug="outra2")
        banco_alheio = BancoPreco.objects.create(tenant=outro, nome="Alheio")
        ItemBancoPreco.objects.create(
            tenant=outro, banco=banco_alheio, codigo="A", descricao="A",
            unidade="UN", custo_unitario=Decimal("1"),
        )
        self.assertEqual(bancos.total_de_linhas(self.tenant.id), 0)
