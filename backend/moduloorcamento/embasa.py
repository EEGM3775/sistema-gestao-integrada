# backend/moduloorcamento/embasa.py
"""ORC.8b — o leitor da EMBASA: do PDF publicado às publicações do semestre.

A EMBASA (Empresa Baiana de Águas e Saneamento) publica a tabela de preços de
saneamento da Bahia **em PDF**, e é a primeira fonte do sistema que não entrega
planilha nenhuma. Não é descuido de quem publica: o artefato é gerado do Excel
deles com moldura de relatório (`Página 1 de 268`, cabeçalho repetido, linhas de
grade) e serve para licitação impressa. Quem precisa do dado é quem o lê.

Três coisas deste dado que quem for mexer aqui precisa saber antes:

1. **O documento declara a própria identidade, e ela é a chave.** A quinta linha
   de toda tabela de serviços diz `DESONERADO - EXPANSÃO - SINTRACOM`:
   regime × escopo × convenção coletiva. Não é ornamento — 1.1 e 1.2 trazem os
   **mesmos 6.992 códigos com preços diferentes** (6.093 dos 6.992 divergem),
   porque a leis sociais muda com o sindicato da região. Ler a identidade do
   nome do arquivo seria possível e errado: o nome traz `h-158-56`, não traz o
   sindicato, e é o sindicato que separa duas publicações que de outro modo
   colidiriam na mesma chave.
2. **São duas tabelas de natureza diferente, e só uma leva encargo.** O
   *Relatório de Insumos Genéricos* traz o custo **puro** (ajudante de armador a
   R$ 7,84/h — salário, sem leis sociais), e por isso entra como regime
   `sem`. O *Relatório de Serviços* traz o preço **já com** a LS do cabeçalho
   embutida, e por isso entra como `desonerado`/`onerado`. Trocar os dois
   aplicaria encargo sobre preço que já tem encargo dentro — o D109 renascido
   nesta fonte.
3. **`0,00` aqui é valor publicado, não ausência.** Na SINAPI, preço em branco
   significa "não houve pesquisa" e a linha não entra (§4.1 da planta). Na
   EMBASA a célula vem **preenchida** com `0,00` para o que a fonte não precifica
   (mobilização, fiscalização — verba do contrato). A linha entra com o zero que
   a fonte escreveu, e a contagem `itens_com_preco_zero` do resumo diz quantas
   são: some-las em silêncio seria inventar dado, escondê-las seria perder
   código que o orçamentista precisa ver na planilha.

**O que este arquivo não faz, e é deliberado:** não lê os PDFs de *Encargos
Sociais* (`1.7`, `2.7`, `1.8`…). Eles são a memória de cálculo da LS — grupos A,
B, C e D em quatro colunas — e o lugar deles é o quadro de encargos da ORC.7,
não a base referencial. Os dois números que a base precisa (LS horista e LS
mensalista) já vêm no cabeçalho de **toda** tabela de serviços e ficam no rótulo
da publicação e no resumo da corrida.

**Analítica não existe nesta fonte.** A EMBASA publica o preço sintético do
serviço, não a composição dele. As composições entram com custo e sem memória de
cálculo — a leitura avisa, pelo mesmo caminho que a SINAPI avisa quando a aba
analítica falta.

Desenho em docs/modulos/moduloorcamento.md §12.8.
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from urllib.parse import urljoin

from funcoesimpexp.formatos.leitura import para_decimal

from .carga import CargaInvalida, Leitura, TabelaLarga
from .models import BaseReferencial, InsumoReferencia

logger = logging.getLogger(__name__)

# A EMBASA é fonte de **uma** UF, e não por acaso: é a companhia estadual de
# saneamento da Bahia. A tabela larga da SINAPI guarda UFs em colunas; aqui a
# coluna é uma só, e reusar a mesma estrutura mantém a escrita, o resumo e a
# gravação das publicações num caminho só.
UF = "BA"

# O endereço-mãe. Não é template de mês (a EMBASA publica por **semestre**, e a
# página tem nome próprio — `2026.11`), então ele mora na `FonteOficial` como
# está e é a lista de documentos que sai dele.
PAGINA_PADRAO = "https://www.embasa.ba.gov.br/2026.11"

MESES: dict[str, int] = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11,
    "dezembro": 12,
}

# `DESONERADO - EXPANSÃO - SINTRACOM`, `TRADICIONAL - OPERAÇÃO ÁGUA - UN FIXA -
# SINTRACOM`. O escopo tem hífen dentro, então o desmembramento é pelas pontas:
# o primeiro pedaço é o regime, o último é a convenção, o miolo é o escopo.
#
# **E a convenção é opcional, porque nem toda tabela se divide por sindicato.**
# As quatro tabelas de manutenção industrial da operação de água terminam em
# `- MANUT IND` (`DESONERADO - OPERAÇÃO ÁGUA - PRODUÇÃO - MANUT IND`): não é
# convenção nenhuma, é o escopo dizendo qual manutenção, e ela é **uma só** por
# regime — não há a divisão por sindicato que as outras seis têm. O que separa
# os dois casos é a gramática do próprio documento: sigla de sindicato é
# **uma palavra** (`SINTRACOM`, `SITICCAN`), e `MANUT IND` são duas. Por isso o
# último pedaço só vira convenção quando vem sozinho; do contrário ele é o fim
# do escopo, e o campo `sindicato` fica vazio em vez de guardar o que não é
# sindicato. Lista fixa de siglas seria o outro caminho, e quebraria no dia em
# que a EMBASA fechasse acordo com um sindicato novo.
RE_IDENTIDADE = re.compile(
    r"^\s*(DESONERADO|TRADICIONAL)\s*-\s*(.+?)"
    r"(?:\s*-\s*(?P<convencao>[A-ZÇÃÕÁÉÍÓÚ0-9]{3,}))?\s*$"
)
RE_RELATORIO = re.compile(
    r"Relat[óo]rio\s+de\s+(Servi[çc]os|Insumos\s+Gen[ée]ricos)\s+"
    r"([A-Za-zçÇãÃéÉê]+)\s*/\s*(\d{4})(?:\s*-\s*(R\d+))?",
    re.IGNORECASE,
)
RE_LS_HORISTA = re.compile(r"LS\s*H\s*:?\s*([\d.,]+)\s*%", re.IGNORECASE)
RE_LS_MENSALISTA = re.compile(r"LS\s*M\s*:?\s*([\d.,]+)\s*%", re.IGNORECASE)

# `01.91.02/EMBASA`, `B010000001/EMBASA`. O sufixo é o que separa uma linha de
# dado do cabeçalho de seção (`1  SERVIÇOS`) e da moldura do relatório.
RE_CODIGO = re.compile(r"^[A-Z0-9][A-Z0-9.\-]*\s*/\s*EMBASA$", re.IGNORECASE)

# `TRADICIONAL` é como a EMBASA chama a folha **sem** desoneração da CPRB — o
# regime que o resto do sistema chama de `onerado`. A dobra de nomenclatura é da
# fonte, e resolvê-la aqui, uma vez, é o que impede que ela vire condicional
# espalhada pelo motor (a mesma razão do `ABAS_SINAPI` em `carga.py`).
REGIMES: dict[str, str] = {
    "DESONERADO": BaseReferencial.Regime.DESONERADO,
    "TRADICIONAL": BaseReferencial.Regime.ONERADO,
}

# Quantas páginas do começo bastam para achar o cabeçalho de identidade. Ele
# está na primeira, e se repete em todas; duas é folga contra uma capa avulsa.
PAGINAS_DE_CABECALHO = 2

# Largura da coluna `BaseReferencial.variante`. Está aqui, e não em
# `payment/planos.py`, porque é largura de campo e não teto de produto (§5.6).
LARGURA_VARIANTE = 60


class DocumentoDesconhecido(CargaInvalida):
    """O PDF chegou e não é tabela de preço da EMBASA que saibamos ler."""


# ---------------------------------------------------------------------------
# A identidade que o próprio documento declara
# ---------------------------------------------------------------------------


@dataclass
class Identidade:
    """Quem é este documento, segundo ele mesmo.

    É o objeto que decide em **qual publicação** as linhas entram, e por isso
    não tem default nenhum: um campo faltando é motivo para a leitura parar, não
    para gravar num lugar plausível.
    """

    relatorio: str  # "servicos" | "insumos"
    competencia: date
    regime: str
    escopo: str = ""
    sindicato: str = ""
    revisao: str = ""
    ls_horista: Decimal | None = None
    ls_mensalista: Decimal | None = None

    @property
    def variante(self) -> str:
        """O eixo de identidade que a EMBASA acrescenta — `expansao-sintracom`.

        Vazio para a tabela de insumos: ela é única no semestre, e inventar uma
        variante para ela faria a publicação de insumos parecer uma entre várias.

        Sem convenção (as tabelas de `MANUT IND`), a variante é o escopo sozinho
        — `operacao-agua-producao-manut-ind`. O hífen final que sairia de colar
        um sindicato vazio não é cosmético: esta string é **chave de unicidade**,
        e a mesma publicação lida com e sem o hífen seriam duas linhas.
        """
        if self.relatorio != "servicos":
            return ""
        pedacos = [_ascii_slug(self.escopo), _ascii_slug(self.sindicato)]
        return "-".join(p for p in pedacos if p)[:LARGURA_VARIANTE]

    @property
    def tipo_do_item(self) -> str:
        return (
            InsumoReferencia.Tipo.COMPOSICAO
            if self.relatorio == "servicos"
            else InsumoReferencia.Tipo.INSUMO
        )

    def rotulo(self) -> str:
        """O que a tela mostra — e é aqui que a LS fica legível.

        A LS não vira campo da publicação de propósito: o preço de serviço da
        EMBASA **já vem com ela embutida**, então ninguém a aplica de novo. O que
        se precisa dela é saber qual tabela se está usando, e isso é rótulo.
        """
        partes = ["EMBASA", UF, self.competencia.strftime("%m/%Y")]
        if self.relatorio == "insumos":
            partes.append("· insumos (sem encargos)")
        else:
            partes.append(f"· {self.escopo.title()}")
            if self.sindicato:
                partes.append(self.sindicato)
            if self.ls_horista is not None and self.ls_mensalista is not None:
                # Vírgula decimal porque isto é texto que o orçamentista lê, e
                # ele confere o rótulo contra o PDF da EMBASA, que escreve
                # `LS H: 158,56%`. Um ponto aqui já basta para a conferência
                # virar dúvida.
                horista = f"{self.ls_horista:.2f}".replace(".", ",")
                mensalista = f"{self.ls_mensalista:.2f}".replace(".", ",")
                partes.append(f"(LS H {horista}% · M {mensalista}%)")
        if self.revisao:
            partes.append(self.revisao)
        return " ".join(partes)[:120]


def _ascii_slug(texto: str) -> str:
    """`OPERAÇÃO ÁGUA - UN FIXA` → `operacao-agua-un-fixa`.

    Sem acento e sem pontuação porque este texto vira **chave de unicidade** no
    banco: `OPERAÇÃO` e `OPERACAO` são a mesma publicação, e duas linhas para ela
    seriam duas verdades sobre o mesmo preço.
    """
    sem_acento = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    limpo = re.sub(r"[^a-z0-9]+", "-", sem_acento.lower())
    return limpo.strip("-")


def _competencia(mes: str, ano: str) -> date:
    numero = MESES.get(_ascii_slug(mes).replace("-", ""))
    if numero is None:
        raise DocumentoDesconhecido(
            f'O cabeçalho diz "{mes}/{ano}" e "{mes}" não é um mês que este leitor '
            "conheça. Se a EMBASA passou a escrever o mês de outro jeito, é aqui "
            "(MESES, em embasa.py) que a tradução mora."
        )
    return date(int(ano), numero, 1)


def identidade_do_documento(linhas_de_cabecalho: list[str]) -> Identidade:
    """Lê o bloco de cabeçalho e devolve quem o documento diz que é.

    Falha explícita quando não reconhece: gravar preço de saneamento numa
    publicação escolhida por eliminação é o defeito que não aparece em teste
    nenhum e aparece na planilha de uma licitação.
    """
    texto = "\n".join(linhas_de_cabecalho)
    relatorio = RE_RELATORIO.search(texto)
    if relatorio is None:
        raise DocumentoDesconhecido(
            "Nenhuma linha 'Relatório de Serviços …/AAAA' ou 'Relatório de Insumos "
            "Genéricos …/AAAA' no começo do PDF. Confira se a URL aponta para a "
            "tabela e não para a página que a anuncia — e note que os PDFs de "
            "Encargos Sociais da EMBASA não entram por aqui: eles são quadro de "
            "encargos (ORC.7), não base de preço.\n"
            f"Começo lido: {texto[:300]}"
        )

    qual = "insumos" if "insumo" in _ascii_slug(relatorio.group(1)) else "servicos"
    competencia = _competencia(relatorio.group(2), relatorio.group(3))
    revisao = (relatorio.group(4) or "").upper()

    if qual == "insumos":
        # O insumo da EMBASA é custo puro — salário sem leis sociais, material
        # sem BDI. `sem` é exatamente o regime que a ORC.8 criou para isso.
        return Identidade(
            relatorio=qual, competencia=competencia, revisao=revisao,
            regime=BaseReferencial.Regime.SEM_ENCARGOS,
        )

    identidade = None
    for linha in linhas_de_cabecalho:
        achado = RE_IDENTIDADE.match(linha.strip())
        if achado is not None:
            identidade = achado
            break
    if identidade is None:
        raise DocumentoDesconhecido(
            "A tabela de serviços não declarou regime, escopo e convenção — a linha "
            "'DESONERADO - EXPANSÃO - SINTRACOM' não foi encontrada. Sem ela não há "
            "como saber em qual das publicações do semestre estes preços entram, e "
            "seis tabelas da EMBASA trazem os mesmos códigos com preços diferentes.\n"
            f"Começo lido: {texto[:300]}"
        )

    horista = RE_LS_HORISTA.search(texto)
    mensalista = RE_LS_MENSALISTA.search(texto)
    return Identidade(
        relatorio=qual,
        competencia=competencia,
        revisao=revisao,
        regime=REGIMES[identidade.group(1).upper()],
        escopo=" ".join(identidade.group(2).split()),
        sindicato=(identidade.group("convencao") or "").strip(),
        ls_horista=para_decimal(horista.group(1)) if horista else None,
        ls_mensalista=para_decimal(mensalista.group(1)) if mensalista else None,
    )


# ---------------------------------------------------------------------------
# A leitura do PDF
# ---------------------------------------------------------------------------


def _abrir(conteudo: bytes):
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - declarada em requirements
        raise CargaInvalida(
            "pdfplumber não instalado — a EMBASA publica só em PDF e sem ele não há "
            "como ler a tabela. É dependência fixa do backend (requirements.txt)."
        ) from exc
    try:
        return pdfplumber.open(io.BytesIO(conteudo))
    except Exception as exc:  # noqa: BLE001 - pdfplumber levanta de tudo
        raise CargaInvalida(
            f"O arquivo não abriu como PDF ({type(exc).__name__}). A EMBASA serve o "
            "documento em /documents/d/guest/<slug>; uma página HTML de erro salva "
            "com nome de PDF chega exatamente assim."
        ) from exc


def _texto(celula) -> str:
    """Célula do PDF → uma linha. A descrição vem quebrada em várias."""
    if celula is None:
        return ""
    return " ".join(str(celula).split())


def ler_documento(conteudo: bytes, nome: str = "") -> Leitura:
    """Do PDF ao `Leitura` — sem tocar no banco.

    Uma tabela larga de uma coluna só (`BA`), para que resumo, gravação e
    contagem sigam pelo mesmo caminho da SINAPI. O documento traz **um** tipo de
    item e **uma** identidade, então a leitura produz uma tabela e uma
    publicação — diferente do arquivo nacional, que rende 54.
    """
    linhas_dado: list[tuple[str, str, str, str, dict[str, Decimal]]] = []
    zerados = 0
    vistos: set[str] = set()
    repetidos = 0

    with _abrir(conteudo) as pdf:
        paginas = len(pdf.pages)
        if not paginas:
            raise CargaInvalida("O PDF veio sem páginas.")

        # A identidade vem **antes** de qualquer linha de dado, e de propósito:
        # é ela que diz quantas colunas a tabela tem (7 nos serviços, 5 nos
        # insumos). Descobrir isso pelo formato das linhas seria adivinhar o
        # tipo do documento a partir do dado dele.
        cabecalho: list[str] = []
        for pagina in pdf.pages[:PAGINAS_DE_CABECALHO]:
            cabecalho.extend((pagina.extract_text() or "").splitlines())
            cabecalho.extend(
                _texto(celula)
                for tabela in pagina.extract_tables() or []
                for linha in tabela for celula in linha
                if _texto(celula)
            )
        identidade = identidade_do_documento(cabecalho)
        colunas = 7 if identidade.relatorio == "servicos" else 5
        posicao_preco = 5 if colunas == 7 else 4

        for pagina in pdf.pages:
            for tabela in pagina.extract_tables() or []:
                for linha in tabela:
                    if len(linha) != colunas:
                        continue
                    codigo = _texto(linha[0])
                    if not RE_CODIGO.match(codigo):
                        continue
                    unidade = _texto(linha[3])
                    bruto = _texto(linha[posicao_preco])
                    if not unidade or not bruto:
                        # Linha de árvore do catálogo de insumos
                        # (`B010000000/EMBASA  MAO DE OBRA - HORISTAS  M.O.`):
                        # rótulo de família, sem unidade nem preço. Não é insumo.
                        continue
                    if codigo in vistos:
                        repetidos += 1
                        continue
                    vistos.add(codigo)
                    preco = para_decimal(bruto)
                    zerados += 1 if preco == 0 else 0
                    linhas_dado.append((
                        codigo, _texto(linha[1]), unidade, _texto(linha[2]),
                        {UF: preco},
                    ))
            # O relatório tem centenas de páginas e o pdfplumber guarda o mapa de
            # texto de cada uma; sem soltar, um documento de 446 páginas mora
            # inteiro na memória do worker (o orçamento é de
            # `ORCAMENTO_CARGA_MEMORIA_MB`, e ele é para a corrida toda).
            pagina.flush_cache()
            pagina.get_textmap.cache_clear()

    if not linhas_dado:
        raise CargaInvalida(
            f"Nenhuma linha de preço reconhecida em {paginas} páginas de "
            f"{nome or 'PDF'}. PDF de imagem (digitalizado) não tem texto "
            "extraível — nesse caso é a EMBASA que precisa publicar o arquivo "
            "de novo, e não há plano B deste lado."
        )

    tabela = TabelaLarga(
        tipo=identidade.tipo_do_item,
        regime=identidade.regime,
        ufs=(UF,),
        linhas=linhas_dado,
    )
    leitura = Leitura(
        tabelas=[tabela],
        planilha=nome or "",
        variante=identidade.variante,
        competencia=identidade.competencia,
        rotulo=identidade.rotulo(),
    )
    leitura.avisos.append(
        "A EMBASA publica o preço sintético do serviço, não a composição dele — "
        "as composições entram com custo e sem memória de cálculo."
        if identidade.relatorio == "servicos"
        else "Insumo da EMBASA é custo puro (salário sem leis sociais): a publicação "
        "entra no regime `sem encargos`, e o quadro de encargos é aplicado por cima."
    )
    if zerados:
        leitura.avisos.append(
            f"{zerados} item(ns) vêm publicados a R$ 0,00 — na EMBASA isso é valor "
            "escrito pela fonte (verba do contrato), não ausência de pesquisa."
        )
    if repetidos:
        leitura.avisos.append(
            f"{repetidos} linha(s) repetiram código já lido e foram descartadas — "
            "cabeçalho de página capturado como dado é a causa usual."
        )
    leitura.extras = {
        "relatorio": identidade.relatorio,
        "escopo": identidade.escopo,
        "sindicato": identidade.sindicato,
        "revisao": identidade.revisao,
        "ls_horista": str(identidade.ls_horista) if identidade.ls_horista else "",
        "ls_mensalista": str(identidade.ls_mensalista) if identidade.ls_mensalista else "",
        "paginas": paginas,
        "itens_com_preco_zero": zerados,
    }
    return leitura


# ---------------------------------------------------------------------------
# A lista de documentos do semestre
# ---------------------------------------------------------------------------


@dataclass
class Documento:
    """Um link da página da EMBASA, já classificado pelo que dá para saber dele.

    O que sai daqui é **menu**, não verdade: regime e escopo vêm do nome do
    arquivo, que é o que a página oferece, e a convenção coletiva não está no
    nome. Quem decide a identidade é o cabeçalho do PDF, na hora de ler. Por isso
    `carregavel` diz só se vale tentar — nunca onde o preço vai parar.
    """

    url: str
    rotulo: str
    slug: str
    especie: str  # "insumos" | "servicos" | "encargos" | "outro"

    @property
    def carregavel(self) -> bool:
        return self.especie in ("insumos", "servicos")


RE_LINK = re.compile(
    r'<a\s[^>]*href="([^"]*/documents/d/guest/[^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
RE_TAG = re.compile(r"<[^>]+>")


def _especie(slug: str, rotulo: str) -> str:
    chave = f"{_ascii_slug(slug)} {_ascii_slug(rotulo)}"
    if "encargos-sociais" in chave or "encargos sociais" in chave:
        return "encargos"
    if "insumo" in chave:
        return "insumos"
    if "serv" in chave:
        return "servicos"
    return "outro"


def listar_documentos(html: bytes | str, pagina: str = PAGINA_PADRAO) -> list[Documento]:
    """Os documentos anunciados na página do semestre, em ordem de publicação.

    Parser de expressão regular e não de árvore HTML: a página é Liferay, o texto
    do link vem enterrado em quatro `<span>` de estilo, e o que interessa são
    duas coisas — o `href` e o texto sem marcação. Trazer um parser de HTML para
    o backend por causa disto seria dependência nova para um problema de duas
    linhas.
    """
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")

    encontrados: dict[str, Documento] = {}
    for href, miolo in RE_LINK.findall(html):
        rotulo = " ".join(RE_TAG.sub(" ", miolo).split())
        url = urljoin(pagina, href)
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        if slug in encontrados:
            continue
        encontrados[slug] = Documento(
            url=url, rotulo=rotulo or slug, slug=slug, especie=_especie(slug, rotulo),
        )
    return list(encontrados.values())


def baixar_lista(pagina: str = PAGINA_PADRAO) -> list[Documento]:
    """Busca a página do semestre e devolve o menu. Rede mora no `oficial`.

    Sem teto próprio: o `baixar` já usa o do dono
    (`planos.ORCAMENTO_CARGA_TETO_MB`). Inventar aqui um número menor "porque
    página é pequena" seria escrever um teto em código de engenharia, que é
    justamente o que a régua de 08/08/2026 proíbe.
    """
    from . import oficial

    baixado = oficial.baixar(pagina)
    return listar_documentos(baixado.conteudo, pagina)
