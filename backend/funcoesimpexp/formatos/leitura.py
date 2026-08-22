# backend/funcoesimpexp/formatos/leitura.py
"""Arquivo que entra → linhas. Promovido de `moduloorcamento/leitura.py` (ORC.5b).

Sobe inteiro porque cada peça daqui custou caro para descobrir e não tem nada de
específico de orçamento — o `1.234,56` do XLSX de uma prefeitura é o mesmo de uma
carteira de clientes. O que ficou para trás foram os aliases de preço, que eram
de domínio: aqui o de-para vem das colunas que o **recurso** declarou.

Só mora aqui o que é **puro**: normalizar, converter, detectar delimitador e
casar cabeçalho. Gravar é de quem chama.
"""
from __future__ import annotations

import csv
import io
import unicodedata
from decimal import Decimal, InvalidOperation


class LeituraInvalida(Exception):
    """Arquivo que não dá para ler (formato, cabeçalho, dependência ausente)."""


def normalizar(texto) -> str:
    """"Preço Mediano R$" → "preco mediano r$" (comparável entre publicações)."""
    if texto is None:
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().replace("\n", " ").split())


def para_decimal(valor) -> Decimal:
    """Aceita float do XLSX e texto no formato brasileiro ("1.234,56")."""
    if valor is None or valor == "":
        return Decimal("0")
    if isinstance(valor, (int, float, Decimal)):
        return Decimal(str(valor))
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")  # 1.234,56
    elif "," in texto:
        texto = texto.replace(",", ".")  # 1234,56
    try:
        return Decimal(texto)
    except InvalidOperation:
        return Decimal("0")


def para_inteiro(valor) -> int:
    return int(para_decimal(valor))


def para_booleano(valor) -> bool:
    return normalizar(valor) in {"1", "true", "verdadeiro", "sim", "s", "x", "v"}


def detectar_delimitador(amostra: str) -> str:
    """Delimitador de CSV com preferência brasileira: **`;` vence**.

    `csv.Sniffer` não serve aqui. Numa linha como ``1379;CIMENTO;KG;0,58`` ele
    elege a vírgula (que é o separador **decimal**) e parte a última coluna em
    duas — sem erro, só com dado silenciosamente errado.

    **Divergência proposital da versão do ORC.5b**, que olhava só a primeira
    linha: arquivo que começa com título e legenda (o caso que a detecção de
    cabeçalho existe para resolver) tem a primeira linha *sem* delimitador
    nenhum, caía na vírgula e transformava a planilha inteira numa coluna só.
    Aqui a decisão é por **maioria** das primeiras linhas não vazias — o que
    também impede que um `;` solto no meio de uma descrição vire o arquivo
    inteiro do avesso.
    """
    linhas = [l for l in amostra.splitlines() if l.strip()][:20]
    if not linhas:
        return ","
    for candidato in (";", "\t", "|"):
        presentes = sum(1 for linha in linhas if candidato in linha)
        if presentes >= max(1, len(linhas) // 2):
            return candidato
    return ","


# ---------------------------------------------------------------------------
# De-para de colunas (R4)
# ---------------------------------------------------------------------------


def mapear_colunas(linhas: list[list], recurso, *, limite: int = 25, manual: dict | None = None):
    """Acha a linha de cabeçalho e casa cada coluna declarada com uma posição.

    Devolve `(mapa, indice_do_cabecalho, cabecalhos_vistos)`. `mapa` é
    `campo -> índice`; `indice` é a linha onde o cabeçalho foi encontrado (os
    dados começam na seguinte).

    Procura nas primeiras `limite` linhas porque publicação oficial põe título,
    brasão e legenda antes da tabela — casar só na linha 1 recusaria metade dos
    arquivos reais.

    Falha explícita, nunca adivinhação (R4): não casando as obrigatórias, quem
    chama recebe `mapa=None` e a lista de cabeçalhos vistos, e mostra isso ao
    operador para o de-para à mão. `manual` (campo → índice) tem precedência
    sobre tudo — é o resultado desse de-para voltando.
    """
    manual = {k: v for k, v in (manual or {}).items() if isinstance(v, int) and v >= 0}
    obrigatorias = tuple(c.campo for c in recurso.obrigatorias())
    vistos: list[list[str]] = []

    for indice, linha in enumerate(linhas[:limite]):
        celulas = [normalizar(c) for c in linha]
        if not any(celulas):
            continue
        vistos.append([c for c in celulas if c])

        mapa: dict[str, int] = dict(manual)
        usados: set[int] = set(mapa.values())
        for coluna in recurso.colunas:
            if coluna.campo in mapa:
                continue
            # O rótulo declarado vale como primeiro alias — quem baixou o modelo
            # e devolveu preenchido casa sempre, sem precisar declarar sinônimo.
            for alias in (coluna.rotulo, *coluna.aliases):
                alvo = normalizar(alias)
                for pos, celula in enumerate(celulas):
                    if pos in usados or celula != alvo:
                        continue
                    mapa[coluna.campo] = pos
                    usados.add(pos)
                    break
                if coluna.campo in mapa:
                    break

        if all(campo in mapa for campo in obrigatorias):
            return mapa, indice, vistos

    return None, -1, vistos


def extrair(bruta: list, mapa: dict[str, int], recurso) -> dict:
    """Linha bruta + mapa → dicionário `campo -> valor` já no tipo declarado."""
    dados: dict = {}
    for coluna in recurso.colunas:
        pos = mapa.get(coluna.campo)
        cru = bruta[pos] if pos is not None and pos < len(bruta) else None
        if coluna.tipo is Decimal:
            dados[coluna.campo] = para_decimal(cru)
        elif coluna.tipo is int:
            dados[coluna.campo] = para_inteiro(cru)
        elif coluna.tipo is bool:
            dados[coluna.campo] = para_booleano(cru)
        else:
            dados[coluna.campo] = "" if cru is None else str(cru).strip()
    return dados


# ---------------------------------------------------------------------------
# Leitores por formato
# ---------------------------------------------------------------------------


def ler_bytes(
    conteudo: bytes,
    nome: str,
    *,
    delimitador: str | None = None,
    formato: str | None = None,
) -> list[list]:
    """Lê XLSX, CSV/TXT ou PDF enviado por upload e devolve as linhas como listas.

    O arquivo veio pela rede e já está inteiro em memória, então a leitura é
    materializada numa lista. **O teto que protege esta função não é o de linhas
    do plano** (a R13, checada só depois, quando já se sabe quantas linhas há):
    é o `orcamento_de_leitura` armado por quem chama, porque o que explode aqui
    é a DESCOMPRESSÃO — um XLSX de poucos MB expande sem relação com o tamanho
    do arquivo, e antes do orçamento isso não tinha limite superior nenhum.

    `formato` é o código já reconhecido pela assinatura de bytes
    (`funcoesimpexp.limites.detectar_formato`). Sem ele, cai no sufixo do nome —
    caminho mantido só para chamada interna com arquivo que já passou pela porta.
    """
    # **Erro de programação não se disfarça de arquivo ruim** (D76). Passar aqui o
    # `FormatoEntrada` em vez do seu `.codigo` fazia todo `==` abaixo falhar e o
    # fluxo cair no `raise LeituraInvalida` do fim — que diz "formato não
    # suportado", acusa o arquivo do cliente e some dentro do `_com_erro` como um
    # lote em ERRO. É a mesma lição do D34 e do D57, agora na terceira reincidência:
    # quando um defeito nosso veste a roupa de defeito do arquivo, ninguém o acha.
    if formato is not None and not isinstance(formato, str):
        raise TypeError(
            f"ler_bytes(formato=...) espera o CÓDIGO do formato (str), não "
            f"{type(formato).__name__}. Use `formato.codigo`."
        )
    codigo = formato or _codigo_pelo_sufixo(nome)
    if codigo == "csv":
        texto = conteudo.decode("utf-8-sig", errors="replace")
        sep = delimitador or detectar_delimitador(texto[:8192])
        return [linha for linha in csv.reader(io.StringIO(texto), delimiter=sep)]
    if codigo == "xlsx":
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover - dependência de requirements
            raise LeituraInvalida("openpyxl não instalado — necessário para ler .xlsx.") from exc
        wb = load_workbook(filename=io.BytesIO(conteudo), read_only=True, data_only=True)
        try:
            planilha = wb.worksheets[0]
            return [list(linha) for linha in planilha.iter_rows(values_only=True)]
        finally:
            wb.close()
    if codigo == "pdf":
        return ler_pdf(conteudo)
    raise LeituraInvalida(f"Formato não suportado ({nome}). Use .xlsx, .csv ou .pdf.")


def _codigo_pelo_sufixo(nome: str) -> str:
    minusculo = (nome or "").lower()
    if minusculo.endswith((".csv", ".txt")):
        return "csv"
    if minusculo.endswith(".xlsx"):
        return "xlsx"
    if minusculo.endswith(".pdf"):
        return "pdf"
    return ""


def ler_pdf(conteudo: bytes) -> list[list]:
    """Extrai tabelas de PDF.

    **Frágil por natureza, e é por isso que a conferência da R1 não é opcional
    neste caminho.** Órgão público publica PDF gerado de mil maneiras: a coluna
    de valor quebra em duas, o cabeçalho repete a cada página, a descrição
    envolve em várias linhas. O extrator entrega o que conseguir e marca o resto
    como inválido — o que ele **não** faz é adivinhar.
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise LeituraInvalida(
            "pdfplumber não instalado — necessário para ler PDF. "
            "Use planilha XLSX/CSV ou instale a dependência."
        ) from exc

    linhas: list[list] = []
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for pagina in pdf.pages:
            for tabela in pagina.extract_tables() or []:
                for linha in tabela:
                    if any(celula not in (None, "") for celula in linha):
                        linhas.append(list(linha))
    if not linhas:
        raise LeituraInvalida(
            "Nenhuma tabela reconhecida neste PDF. PDFs de imagem (digitalizados) "
            "não têm texto extraível — peça a planilha à fonte."
        )
    return linhas
