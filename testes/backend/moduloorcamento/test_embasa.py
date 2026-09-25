"""Testes da ORC.8b — a carga da EMBASA, que publica em PDF.

O que estes testes protegem, em ordem de quanto custa errar:

1. **`DESONERADO` × `TRADICIONAL`.** A EMBASA chama de "tradicional" o regime
   que o resto do sistema chama de `onerado`. Trocar os dois inverte o custo de
   toda a tabela sem quebrar nada visível.
2. **A `variante` na chave da publicação.** Seis tabelas do mesmo semestre e do
   mesmo regime trazem os mesmos 6.992 códigos com preços diferentes, uma por
   convenção coletiva. Sem o eixo, a sexta carga sobrescreve as cinco anteriores
   em silêncio — e o orçamento fica com o preço de outra região.
3. **Insumo da EMBASA é custo puro** e entra como `sem encargos`. Lê-lo como
   onerado faria a leis sociais ser aplicada sobre preço que já a tem dentro.
4. **`0,00` é valor publicado, não ausência.** O inverso da regra da SINAPI, e é
   o inverso porque a célula vem **preenchida**.
5. **A data-base é a do artefato.** A EMBASA publica por semestre; a competência
   pedida é palpite, a declarada no PDF não é.
6. **A URL do documento é amarrada ao host cadastrado.** O endpoint manda o
   worker buscar um endereço — sem a amarra, é SSRF com convite.

O PDF de teste é **gerado aqui**, com o mesmo weasyprint que o módulo de
exportação já usa: o documento real tem 6 MB e 268 páginas e não entra no
repositório (a lição do D41). O que está escrito abaixo é, ao mesmo tempo, o
teste e a documentação executável do layout que a EMBASA publica.
"""
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from nucleo.models import Tenant, Usuario

from moduloorcamento import carga, embasa, services
from moduloorcamento.models import BaseReferencial, CargaBase, Fonte, FonteOficial, InsumoReferencia
from .tests import OrcamentoTestBase

# O cabeçalho do documento real, linha a linha. A folga entre as colunas é o que
# faz o `LS H:` cair à direita no PDF, como no original.
CABECALHO_SERVICOS = """
<p>Data:18/08/2026</p>
<p>EMBASA - Empresa Baiana de Águas e Saneamento S/A. &nbsp;&nbsp; LS H: 158,56%</p>
<p>Relatório de Serviços Junho/2026 - R2 SEM BDI &nbsp;&nbsp; LS M: 119,40%</p>
<p>BDI: 0,00%</p>
<p>DESONERADO - EXPANSÃO - SINTRACOM</p>
"""

CABECALHO_INSUMOS = """
<p>Data:18/08/2026</p>
<p>EMBASA - Empresa Baiana de Águas e Saneamento S/A.</p>
<p>Relatório de Insumos Genéricos Junho/2026 - R2</p>
<p>LISTA DE INSUMOS - JUNHO/26</p>
"""

# Paisagem e borda declarada: sem as duas, o weasyprint não desenha as linhas de
# grade que o `extract_tables` usa para achar as colunas — é a mesma exigência
# que o PDF da EMBASA cumpre por ser gerado do Excel com moldura de relatório.
ESTILO = """
<style>
  @page { size: A4 landscape; margin: 8mm; }
  body { font-family: sans-serif; font-size: 7pt; }
  table { border-collapse: collapse; width: 100%; }
  td, th { border: 0.6pt solid #000; padding: 2pt; }
</style>
"""


def _pdf(html_do_corpo: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=f"<html><head>{ESTILO}</head><body>{html_do_corpo}</body></html>").write_pdf()


def _linha(*celulas: str) -> str:
    return "<tr>" + "".join(f"<td>{c}</td>" for c in celulas) + "</tr>"


def pdf_de_servicos(cabecalho: str = CABECALHO_SERVICOS) -> bytes:
    """O *Relatório de Serviços*: 7 colunas, preço unitário na sexta."""
    linhas = [
        _linha("CÓDIGO", "DESCRIÇÃO", "CLASS", "UNIDADE", "QUANT",
               "PREÇO (R$)", "PREÇO TOTAL (R$)"),
        # O cabeçalho de seção do relatório: não tem código e não é dado.
        _linha("1", "SERVIÇOS", "", "", "", "", ""),
        _linha("01.01.00/EMBASA", "MOBILIZACAO, DESMOBILIZACAO E INSTALACAO DE CANTEIRO",
               "SER.CG", "UN", "1,00", "0,00", "0,00"),
        _linha("01.91.02/EMBASA", "LOCACAO DE VEICULO 1.0 INCLUINDO MOTORISTA",
               "SER.CG", "MÊS", "1,00", "11.686,54", "11.686,54"),
        _linha("04.01.01/EMBASA", "ESCAVACAO MANUAL DE VALA", "SER.CG", "M3",
               "1,00", "62,35", "62,35"),
    ]
    return _pdf(cabecalho + "<table>" + "".join(linhas) + "</table>")


def pdf_de_insumos() -> bytes:
    """O *Relatório de Insumos Genéricos*: 5 colunas, preço na quinta."""
    linhas = [
        _linha("CÓDIGO", "DESCRIÇÃO", "CLASS", "UNIDADE", "PREÇO(R$)"),
        _linha("1", "INSUMOS", "", "", ""),
        # Rótulo de família da árvore de códigos: sem unidade e sem preço. Não é
        # insumo, e entrar como um o poria na planilha a R$ 0,00.
        _linha("B010000000/EMBASA", "MAO DE OBRA - HORISTAS", "M.O.", "", ""),
        _linha("B010000001/EMBASA", "AJUDANTE DE ARMADOR", "M.O.", "H", "7,84"),
        _linha("D010000002/EMBASA", "ASFALTO OXIDADO", "MAT.", "KG", "7,44"),
        _linha("F020000534/EMBASA", "RESPIRADOR CONTRA PO", "EQ.AQ.", "UN", "18,41"),
    ]
    return _pdf(CABECALHO_INSUMOS + "<table>" + "".join(linhas) + "</table>")


# ---------------------------------------------------------------------------
# A identidade que o documento declara
# ---------------------------------------------------------------------------


class IdentidadeTests(SimpleTestCase):
    """O cabeçalho é a chave da publicação — e por isso não se adivinha."""

    def test_servicos_desonerado_expansao(self):
        identidade = embasa.identidade_do_documento(
            CABECALHO_SERVICOS.replace("<p>", "").replace("</p>", "").splitlines()
        )
        self.assertEqual(identidade.relatorio, "servicos")
        self.assertEqual(identidade.regime, BaseReferencial.Regime.DESONERADO)
        self.assertEqual(identidade.escopo, "EXPANSÃO")
        self.assertEqual(identidade.sindicato, "SINTRACOM")
        self.assertEqual(identidade.competencia, date(2026, 6, 1))
        self.assertEqual(identidade.revisao, "R2")
        self.assertEqual(identidade.ls_horista, Decimal("158.56"))
        self.assertEqual(identidade.variante, "expansao-sintracom")

    def test_tradicional_da_embasa_e_o_onerado_do_sistema(self):
        """A dobra de nomenclatura da fonte, resolvida no lugar certo.

        Trocar os dois não quebra nada visível: inverte o custo de toda a tabela,
        calado, porque 'tradicional' soa como 'o normal'.
        """
        identidade = embasa.identidade_do_documento([
            "Relatório de Serviços Junho/2026 - R2 SEM BDI",
            "TRADICIONAL - EXPANSÃO - SINTRACOM",
        ])
        self.assertEqual(identidade.regime, BaseReferencial.Regime.ONERADO)

    def test_escopo_com_hifen_dentro_nao_e_confundido_com_a_convencao(self):
        """`OPERAÇÃO ÁGUA - UN FIXA - SINTRACOM` tem três hifens e quatro campos.

        Desmembrar pelo primeiro hífen daria escopo `OPERAÇÃO ÁGUA` e convenção
        `UN FIXA - SINTRACOM` — duas publicações diferentes com a mesma variante.
        """
        identidade = embasa.identidade_do_documento([
            "Relatório de Serviços Junho/2026 - R2 SEM BDI",
            "DESONERADO - OPERAÇÃO ÁGUA - UN FIXA - SINTRACOM",
        ])
        self.assertEqual(identidade.escopo, "OPERAÇÃO ÁGUA - UN FIXA")
        self.assertEqual(identidade.sindicato, "SINTRACOM")
        self.assertEqual(identidade.variante, "operacao-agua-un-fixa-sintracom")

    def test_manutencao_industrial_nao_tem_convencao_e_entra_assim(self):
        """`- MANUT IND` é fim de escopo, não sindicato — e são duas palavras.

        As quatro tabelas de manutenção industrial da operação de água foram as
        únicas das 65 que a carga do semestre recusou: o último pedaço do
        cabeçalho vinha com espaço, o regex exigia palavra única, e a leitura
        parava. Gravar `MANUT IND` no campo `sindicato` faria a recusa sumir e
        poria no banco, como convenção coletiva, algo que não é convenção
        nenhuma.
        """
        identidade = embasa.identidade_do_documento([
            "Relatório de Serviços Junho/2026 - R2 SEM BDI",
            "DESONERADO - OPERAÇÃO ÁGUA - PRODUÇÃO - MANUT IND",
        ])
        self.assertEqual(identidade.escopo, "OPERAÇÃO ÁGUA - PRODUÇÃO - MANUT IND")
        self.assertEqual(identidade.sindicato, "")
        self.assertEqual(identidade.variante, "operacao-agua-producao-manut-ind")

    def test_variante_sem_convencao_nao_termina_em_hifen(self):
        """A variante é chave de unicidade; um hífen pendurado é outra chave.

        Colar um sindicato vazio daria `…-manut-ind-`, e a mesma publicação lida
        antes e depois da correção viraria duas linhas para o mesmo preço.
        """
        identidade = embasa.identidade_do_documento([
            "Relatório de Serviços Junho/2026 - R2 SEM BDI",
            "TRADICIONAL - OPERAÇÃO ÁGUA - UN. FIXA - MANUT IND",
        ])
        self.assertEqual(identidade.variante, "operacao-agua-un-fixa-manut-ind")
        self.assertFalse(identidade.variante.endswith("-"))

    def test_rotulo_sem_convencao_nao_fica_com_espaco_dobrado(self):
        identidade = embasa.identidade_do_documento([
            "Relatório de Serviços Junho/2026 - R2 SEM BDI",
            "LS H: 238,47%",
            "LS M: 199,32%",
            "DESONERADO - OPERAÇÃO ÁGUA - PRODUÇÃO - MANUT IND",
        ])
        rotulo = identidade.rotulo()
        self.assertNotIn("  ", rotulo)
        self.assertIn("Operação Água - Produção - Manut Ind", rotulo)
        self.assertIn("238,47%", rotulo)

    def test_insumos_entram_sem_encargos_e_sem_variante(self):
        identidade = embasa.identidade_do_documento([
            "Relatório de Insumos Genéricos Junho/2026 - R2",
            "LISTA DE INSUMOS - JUNHO/26",
        ])
        self.assertEqual(identidade.relatorio, "insumos")
        self.assertEqual(identidade.regime, BaseReferencial.Regime.SEM_ENCARGOS)
        self.assertEqual(identidade.variante, "")

    def test_rotulo_traz_a_ls_com_virgula_como_o_pdf_escreve(self):
        identidade = embasa.identidade_do_documento(
            CABECALHO_SERVICOS.replace("<p>", "").replace("</p>", "").splitlines()
        )
        rotulo = identidade.rotulo()
        self.assertIn("158,56%", rotulo)
        self.assertIn("SINTRACOM", rotulo)
        self.assertNotIn("158.56", rotulo)

    def test_quadro_de_encargos_sociais_e_recusado_com_o_motivo(self):
        """Os PDFs `1.7`, `2.7`… são a memória de cálculo da LS, não base de preço.

        Eles estão na mesma página e têm nome parecido; aceitar um deles gravaria
        percentuais como se fossem preço unitário.
        """
        with self.assertRaises(embasa.DocumentoDesconhecido) as erro:
            embasa.identidade_do_documento([
                "COMPOSIÇÃO DE ENCARGOS SOCIAIS E TRABALHISTAS PARA OBRA",
                "DESONERADO - JUNHO 2026",
                "A1 - Previdência Social (INSS) 10,00%",
            ])
        self.assertIn("Encargos Sociais", str(erro.exception))

    def test_servico_sem_a_linha_de_identidade_para_a_leitura(self):
        with self.assertRaises(embasa.DocumentoDesconhecido):
            embasa.identidade_do_documento([
                "Relatório de Serviços Junho/2026 - R2 SEM BDI",
                "CÓDIGO DESCRIÇÃO CLASS UNIDADE QUANT PREÇO (R$)",
            ])

    def test_mes_que_o_leitor_nao_conhece_para_em_vez_de_chutar(self):
        with self.assertRaises(embasa.DocumentoDesconhecido):
            embasa.identidade_do_documento([
                "Relatório de Serviços Jnuho/2026 - R2 SEM BDI",
                "DESONERADO - EXPANSÃO - SINTRACOM",
            ])


# ---------------------------------------------------------------------------
# A leitura do PDF
# ---------------------------------------------------------------------------


class LeituraDoPdfTests(SimpleTestCase):
    """O que o leitor entende do documento — sem tocar no banco."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.servicos = embasa.ler_documento(pdf_de_servicos(), "1-1serv-exp-deson.pdf")
        cls.insumos = embasa.ler_documento(pdf_de_insumos(), "insumos.pdf")

    def test_servico_vira_composicao_de_uma_publicacao_da_bahia(self):
        self.assertEqual(self.servicos.publicacoes, [("BA", BaseReferencial.Regime.DESONERADO)])
        tabela = self.servicos.tabelas[0]
        self.assertEqual(tabela.tipo, InsumoReferencia.Tipo.COMPOSICAO)
        self.assertEqual(len(tabela.linhas), 3)

    def test_preco_brasileiro_com_milhar_vira_decimal(self):
        itens = self.servicos.tabelas[0].itens_da_uf("BA")
        self.assertEqual(itens["01.91.02/EMBASA"].custo_unitario, Decimal("11686.54"))
        self.assertEqual(itens["04.01.01/EMBASA"].unidade, "M3")

    def test_zero_publicado_entra_e_e_contado(self):
        """O inverso da regra da SINAPI, e é o inverso de propósito.

        Lá, célula em branco significa "não houve pesquisa" e a linha fica fora.
        Aqui a célula vem **preenchida** com `0,00`: é verba de contrato, valor
        que a fonte escreveu. Descartá-la sumiria com um código que o
        orçamentista precisa ver na planilha.
        """
        itens = self.servicos.tabelas[0].itens_da_uf("BA")
        self.assertEqual(itens["01.01.00/EMBASA"].custo_unitario, Decimal("0"))
        self.assertEqual(self.servicos.extras["itens_com_preco_zero"], 1)
        self.assertTrue(any("R$ 0,00" in a for a in self.servicos.avisos))

    def test_cabecalho_de_secao_nao_vira_item(self):
        """`1  SERVIÇOS` não tem código no formato da fonte, e por isso cai fora."""
        codigos = {linha[0] for linha in self.servicos.tabelas[0].linhas}
        self.assertNotIn("1", codigos)

    def test_insumo_entra_como_insumo_sem_encargos(self):
        self.assertEqual(self.insumos.publicacoes, [("BA", BaseReferencial.Regime.SEM_ENCARGOS)])
        tabela = self.insumos.tabelas[0]
        self.assertEqual(tabela.tipo, InsumoReferencia.Tipo.INSUMO)
        self.assertEqual(
            tabela.itens_da_uf("BA")["B010000001/EMBASA"].custo_unitario, Decimal("7.84")
        )

    def test_rotulo_de_familia_sem_preco_nao_vira_insumo(self):
        """`B010000000/EMBASA  MAO DE OBRA - HORISTAS` é nó da árvore de códigos.

        Tem código e classe, não tem unidade nem preço. Entrar como insumo o
        poria na planilha a R$ 0,00 com cara de item real.
        """
        codigos = {linha[0] for linha in self.insumos.tabelas[0].linhas}
        self.assertNotIn("B010000000/EMBASA", codigos)
        self.assertEqual(len(self.insumos.tabelas[0].linhas), 3)

    def test_classes_da_publicacao_de_insumos_saem_para_o_de_para(self):
        self.assertEqual(self.insumos.classes, {"M.O.", "MAT.", "EQ.AQ."})

    def test_resumo_carrega_variante_rotulo_e_a_data_base_lida(self):
        resumo = self.servicos.resumo()
        self.assertEqual(resumo["variante"], "expansao-sintracom")
        self.assertEqual(resumo["competencia_lida"], "2026-06-01")
        self.assertEqual(resumo["sindicato"], "SINTRACOM")
        self.assertIn("SINTRACOM", resumo["rotulo"])

    def test_composicao_da_embasa_avisa_que_nao_tem_memoria_de_calculo(self):
        self.assertTrue(any("sintético" in a for a in self.servicos.avisos))

    def test_arquivo_que_nao_e_pdf_falha_dizendo_isso(self):
        with self.assertRaises(carga.CargaInvalida):
            embasa.ler_documento(b"<html>pagina de erro do portal</html>", "tabela.pdf")


# ---------------------------------------------------------------------------
# A lista de documentos do semestre
# ---------------------------------------------------------------------------


PAGINA = "https://www.embasa.ba.gov.br/2026.11"

HTML_DA_PAGINA = """
<p><a href="/documents/d/guest/fator-m-junho-2026-2"><span>Fator M - JUNHO-2026</span></a></p>
<p><a href="/documents/d/guest/1-1serv-exp-deson-jun-2026-h-158-56-m-119-40-r2">
   <span><span>1.1Serv-Exp-Deson-JUN-2026 (H=158,56 M=119,40)-R2</span></span></a></p>
<p><a href="/documents/d/guest/1-7-encargos-sociais-2026-06-desonerado-servicos-expansao-2">
   <span>1.7 Encargos Sociais - 2026.06 DESONERADO - SERVIÇOS EXPANSÃO</span></a></p>
<p><a href="/documents/d/guest/1-tabela-de-precos-2026-insumos-junho-r2">
   <span>1.Tabela de Preços 2026 - INSUMOS JUNHO - R2</span></a></p>
<p><a href="/documents/d/guest/1-1serv-exp-deson-jun-2026-h-158-56-m-119-40-r2">repetido</a></p>
"""


class ListagemDeDocumentosTests(SimpleTestCase):
    """O menu que a tela mostra antes de oferecer o botão."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.documentos = {d.slug: d for d in embasa.listar_documentos(HTML_DA_PAGINA, PAGINA)}

    def test_link_relativo_vira_endereco_absoluto(self):
        documento = self.documentos["1-tabela-de-precos-2026-insumos-junho-r2"]
        self.assertTrue(documento.url.startswith("https://www.embasa.ba.gov.br/documents/"))

    def test_texto_do_link_sobrevive_aos_spans_de_estilo(self):
        documento = self.documentos["1-1serv-exp-deson-jun-2026-h-158-56-m-119-40-r2"]
        self.assertEqual(documento.rotulo, "1.1Serv-Exp-Deson-JUN-2026 (H=158,56 M=119,40)-R2")

    def test_encargos_sociais_aparece_na_lista_mas_nao_e_carregavel(self):
        """Estar na lista é honesto — é o que a página publica. Oferecer o botão
        para ele não é: o quadro de encargos é da ORC.7, não base de preço."""
        documento = self.documentos["1-7-encargos-sociais-2026-06-desonerado-servicos-expansao-2"]
        self.assertEqual(documento.especie, "encargos")
        self.assertFalse(documento.carregavel)

    def test_insumos_e_servicos_sao_carregaveis(self):
        self.assertTrue(self.documentos["1-tabela-de-precos-2026-insumos-junho-r2"].carregavel)
        self.assertTrue(
            self.documentos["1-1serv-exp-deson-jun-2026-h-158-56-m-119-40-r2"].carregavel
        )

    def test_link_repetido_entra_uma_vez_so(self):
        self.assertEqual(len(self.documentos), 4)


# ---------------------------------------------------------------------------
# O de-para de classes
# ---------------------------------------------------------------------------


class ClassesDaEmbasaTests(SimpleTestCase):
    """`dados/classes/embasa.csv` — o que impede os 30 mil insumos da Bahia de
    caírem no plano B da unidade, onde material em `H` viraria mão de obra."""

    def setUp(self):
        services.esquecer_classes_declaradas()

    def test_as_seis_classes_publicadas_tem_traducao(self):
        esperado = {
            "MAT.": "material",
            "M.O.": "mao_de_obra",
            "EQ.LOC": "equipamento",
            "EQ.AQ.": "equipamento",
            "SER.MO": "servico",
            "VERBA": "encargos_complementares",
        }
        for classe, natureza in esperado.items():
            with self.subTest(classe=classe):
                self.assertEqual(
                    services.natureza_da_classificacao(classe, Fonte.EMBASA), natureza
                )
                self.assertFalse(
                    services.classificacao_desconhecida(classe, Fonte.EMBASA)
                )

    def test_o_ponto_faz_parte_da_chave(self):
        """`normalizar` não tira pontuação: `MAT` sem ponto não é `MAT.`.

        Se alguém "limpar" o CSV tirando os pontos, o casamento exato deixa de
        valer e a classe mais comum da fonte volta a ser desconhecida.
        """
        self.assertIsNone(services.natureza_da_classificacao("MAT", Fonte.EMBASA))

    def test_o_de_para_e_da_embasa_e_nao_vaza_para_outras_fontes(self):
        self.assertIsNone(services.natureza_da_classificacao("EQ.LOC", Fonte.SINAPI))


# ---------------------------------------------------------------------------
# A gravação: a variante no eixo da publicação
# ---------------------------------------------------------------------------


class GravacaoDaEmbasaTests(APITestCase):
    """A corrida inteira, com banco."""

    def setUp(self):
        services.esquecer_classes_declaradas()

    def _carga(self, **campos):
        campos.setdefault("competencia", date(2026, 6, 1))
        return CargaBase.objects.create(
            fonte=Fonte.EMBASA, origem=CargaBase.Origem.UPLOAD,
            arquivo_nome="tabela.pdf", solicitada_por_nome="teste", **campos,
        )

    def test_a_migration_ja_deixou_o_endereco_da_embasa_cadastrado(self):
        """A EMBASA é a única fonte cujo endereço vem do código.

        As demais o dono cadastra (a URL da Caixa já mudou uma vez e o conserto
        tem de ser caixa de texto). Aqui o endereço não é template de mês — é a
        página do semestre —, e o motor já precisa conhecê-lo para listar os
        documentos: deixá-lo fora do banco faria a tela pedir um cadastro que
        ninguém sabe qual é.
        """
        configuracao = FonteOficial.objects.get(fonte=Fonte.EMBASA)
        self.assertIn("embasa.ba.gov.br", configuracao.template_url)
        self.assertEqual(configuracao.dia_do_mes, 0)

    def test_carga_grava_a_publicacao_com_a_variante_e_o_rotulo_da_fonte(self):
        registro = carga.executar(self._carga(), pdf_de_servicos())
        self.assertEqual(registro.estado, CargaBase.Estado.CONCLUIDA, registro.erro)

        publicacao = BaseReferencial.objects.get(
            fonte=Fonte.EMBASA, uf="BA", mes_referencia=date(2026, 6, 1),
            regime_encargos=BaseReferencial.Regime.DESONERADO,
        )
        self.assertEqual(publicacao.variante, "expansao-sintracom")
        self.assertEqual(publicacao.total_composicoes, 3)
        self.assertIn("SINTRACOM", publicacao.rotulo)
        self.assertIn("158,56%", publicacao.rotulo)

    def test_duas_convencoes_do_mesmo_semestre_convivem(self):
        """**O teste que justifica o campo `variante`.**

        Mesma fonte, mesma UF, mesmo mês, mesmo regime — e preços diferentes,
        porque a leis sociais muda com o sindicato. Sem o eixo na chave, a
        segunda carga sobrescreveria a primeira e ninguém veria.
        """
        carga.executar(self._carga(), pdf_de_servicos())
        sintepav = CABECALHO_SERVICOS.replace("SINTRACOM", "SINTEPAV").replace(
            "158,56", "183,54"
        )
        carga.executar(self._carga(), pdf_de_servicos(sintepav))

        publicacoes = BaseReferencial.objects.filter(
            fonte=Fonte.EMBASA, uf="BA", mes_referencia=date(2026, 6, 1),
            regime_encargos=BaseReferencial.Regime.DESONERADO,
        )
        self.assertEqual(publicacoes.count(), 2)
        self.assertEqual(
            set(publicacoes.values_list("variante", flat=True)),
            {"expansao-sintracom", "expansao-sintepav"},
        )

    def test_recarregar_o_mesmo_documento_atualiza_em_vez_de_duplicar(self):
        carga.executar(self._carga(), pdf_de_servicos())
        carga.executar(self._carga(), pdf_de_servicos())
        self.assertEqual(BaseReferencial.objects.filter(fonte=Fonte.EMBASA).count(), 1)
        self.assertEqual(InsumoReferencia.objects.count(), 3)

    def test_data_base_do_documento_vence_a_que_foi_pedida(self):
        """A EMBASA publica por semestre: pedir agosto e receber junho é o normal.

        Gravar junho debaixo de agosto seria datar preço errado — o defeito que
        só aparece quando alguém compara orçado com realizado.
        """
        registro = carga.executar(
            self._carga(competencia=date(2026, 8, 1)), pdf_de_servicos()
        )
        self.assertEqual(registro.competencia, date(2026, 6, 1))
        self.assertTrue(
            BaseReferencial.objects.filter(mes_referencia=date(2026, 6, 1)).exists()
        )
        self.assertTrue(any("06/2026" in a for a in registro.resumo["avisos"]))

    def test_insumos_da_embasa_entram_sem_encargos(self):
        carga.executar(self._carga(), pdf_de_insumos())
        publicacao = BaseReferencial.objects.get(fonte=Fonte.EMBASA)
        self.assertEqual(publicacao.regime_encargos, BaseReferencial.Regime.SEM_ENCARGOS)
        self.assertEqual(publicacao.variante, "")
        self.assertEqual(publicacao.total_insumos, 3)

    def test_carga_sem_documento_escolhido_para_com_motivo(self):
        """65 tabelas no ar e nenhuma é "a do mês" — a corrida devolve a pergunta."""
        registro = carga.executar(
            CargaBase.objects.create(
                fonte=Fonte.EMBASA, competencia=date(2026, 6, 1),
                origem=CargaBase.Origem.DOWNLOAD,
            )
        )
        self.assertEqual(registro.estado, CargaBase.Estado.FALHOU)
        self.assertEqual(registro.resumo["motivo"], "sem_documento")


class MotorEAgendamentoTests(SimpleTestCase):
    def test_a_embasa_tem_motor(self):
        self.assertIn(Fonte.EMBASA, carga.fontes_conhecidas())

    def test_a_embasa_fica_fora_da_varredura_mensal(self):
        """Agendar "a carga da EMBASA" sem dizer qual tabela só sabe falhar —
        e um agendamento que sempre falha ensina a ignorar o alarme."""
        self.assertTrue(carga.exige_escolha_de_documento(Fonte.EMBASA))
        self.assertFalse(carga.exige_escolha_de_documento(Fonte.SINAPI))


# ---------------------------------------------------------------------------
# A porta: escolher o documento sem abrir SSRF
# ---------------------------------------------------------------------------


class EscolhaDeDocumentoPelaApiTests(APITestCase):
    """O endpoint manda o worker buscar um endereço — a amarra não é burocracia."""

    def setUp(self):
        tenant = Tenant.objects.create(slug="orc8b-api", nome="Construtora")
        self.dono = Usuario.objects.create(username="dono", tenant=tenant)
        self.dono.is_platform_admin = True
        self.client.force_authenticate(user=self.dono)
        # A migration já cadastrou a EMBASA; aqui só se fixa o endereço que os
        # testes usam, para a amarra de host não depender do semestre vigente.
        FonteOficial.objects.update_or_create(
            fonte=Fonte.EMBASA, defaults={"template_url": PAGINA},
        )

    def test_documento_de_outro_host_e_recusado(self):
        resposta = self.client.post("/api/orcamento/cargas/", {
            "fonte": Fonte.EMBASA,
            "url": "http://169.254.169.254/latest/meta-data/",
        }, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("url", resposta.data)

    def test_documento_do_host_cadastrado_e_aceito(self):
        alvo = f"{PAGINA.rsplit('/', 1)[0]}/documents/d/guest/1-1serv-exp-deson"
        resposta = self.client.post("/api/orcamento/cargas/", {
            "fonte": Fonte.EMBASA, "url": alvo, "somente_resumo": True,
        }, format="json")
        self.assertEqual(resposta.status_code, 202, resposta.data)
        self.assertEqual(CargaBase.objects.get().url_origem, alvo)


class ResumoLeClassePorFonteTests(OrcamentoTestBase):
    """`bases-resumo/` tem de ler a classe **pela fonte da publicação**.

    O defeito que este teste prende: o `GROUP BY` do resumo não trazia
    `base__fonte`, então `classificacao_desconhecida` era chamada sem fonte e só
    o `PREFIXOS_DE_CLASSE` embutido respondia. O vocabulário em sigla da EMBASA
    (`MAT.`, `M.O.`, `EQ.LOC`) — que `dados/classes/embasa.csv` traduz desde a
    ORC.9c — voltava como *classe ilegível*, e o indicador acendia vermelho numa
    publicação inteiramente compreendida. É a mentira simétrica à que a ORC.9c
    fechou: lá o indicador acendia verde sobre base ilegível, aqui acende
    vermelho sobre base legível — e as duas custam a mesma confiança.
    """

    def setUp(self):
        super().setUp()
        services.esquecer_classes_declaradas()
        self.addCleanup(services.esquecer_classes_declaradas)

    def _publicacao_embasa(self):
        base = BaseReferencial.objects.create(
            fonte=Fonte.EMBASA, uf="BA", mes_referencia=date(2026, 6, 1),
            regime_encargos=BaseReferencial.Regime.SEM_ENCARGOS, variante="expansao-sintracom",
        )
        for codigo, grupo in [("1001", "MAT."), ("1002", "M.O."), ("1003", "EQ.LOC")]:
            InsumoReferencia.objects.create(
                base=base, codigo=codigo, descricao=f"Insumo {codigo}", unidade="UN",
                tipo=InsumoReferencia.Tipo.INSUMO, custo_unitario=Decimal("1"), grupo=grupo,
            )
        return base

    def test_sigla_da_embasa_nao_e_reportada_como_ilegivel(self):
        base = self._publicacao_embasa()
        self.autenticar()
        resposta = self.client.get("/api/orcamento/bases-resumo/")
        self.assertEqual(resposta.status_code, 200, resposta.content)

        linha = next(b for b in resposta.data if b["base_id"] == base.base_id)
        self.assertEqual(linha["classes_desconhecidas"], [])
        self.assertTrue(linha["classifica_insumo"])

    def test_vocabulario_de_verdade_desconhecido_continua_aparecendo(self):
        """O conserto não pode transformar o indicador num sim para tudo."""
        base = self._publicacao_embasa()
        InsumoReferencia.objects.create(
            base=base, codigo="9999", descricao="Insumo de classe estranha", unidade="UN",
            tipo=InsumoReferencia.Tipo.INSUMO, custo_unitario=Decimal("1"),
            grupo="XPTO.INVENTADO",
        )
        self.autenticar()
        resposta = self.client.get("/api/orcamento/bases-resumo/")
        linha = next(b for b in resposta.data if b["base_id"] == base.base_id)
        self.assertEqual(linha["classes_desconhecidas"], ["XPTO.INVENTADO"])
        self.assertFalse(linha["classifica_insumo"])
