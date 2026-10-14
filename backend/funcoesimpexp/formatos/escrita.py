# backend/funcoesimpexp/formatos/escrita.py
"""Linhas → arquivo. XLSX, CSV e PDF, com a mesma forma para todo recurso.

Duas saídas com propósitos diferentes, e a diferença é de desenho (é a lição já
escrita no `moduloorcamento/exportacao.py`, agora valendo para todos):

- **XLSX é para trabalhar.** O destinatário vai filtrar, somar e comparar — então
  número sai como número (R8), senão a primeira coisa que a pessoa faz é
  reconverter a planilha inteira, e reconversão de `1.234,56` erra.
- **PDF é para arquivar e assinar.** Layout fixo, totais fechados, sem risco de
  alguém "ajustar" uma célula no caminho.

CSV existe para quem vai ler com script — é o formato que nenhum sistema recusa.

Todo arquivo carrega o **cabeçalho de procedência** (R9): o que é, de qual
recorte, emitido por quem e quando. Peça sem procedência não é conferível.
"""
from __future__ import annotations

import csv
import functools
import io
from datetime import date
from decimal import Decimal

from django.template.loader import render_to_string


class EscritaIndisponivel(Exception):
    """Biblioteca de escrita ausente no ambiente."""


class RecursoExternoRecusado(Exception):
    """O PDF pediu um recurso de fora; o buscador não busca fora (D73)."""


@functools.cache
def _classe_do_buscador():
    """A subclasse de `URLFetcher` — criada só quando o WeasyPrint é importado.

    Desde a 70 o `url_fetcher` é um **objeto** `URLFetcher`, não uma função: o
    WeasyPrint lê atributos dele (`_fail_on_errors`) justamente no caminho da
    recusa, e o `default_url_fetcher` deixou de existir. Uma função solta
    quebraria o PDF na importação e de novo ao recusar a primeira URL.
    """
    from weasyprint.urls import URLFetcher

    class BuscadorSemRede(URLFetcher):
        def fetch(self, url, headers=None):
            if not url.startswith("data:"):
                raise RecursoExternoRecusado(url)
            return super().fetch(url, headers)

    return BuscadorSemRede


def _novo_buscador():
    # `allowed_protocols` é a segunda trava, a da própria biblioteca: mesmo que o
    # `fetch` acima mude, nada além de `data:` é aberto. Sem redirecionamento
    # porque `data:` não redireciona, e um redirecionamento seria rede.
    return _classe_do_buscador()(allowed_protocols={"data"}, allow_redirects=False)


def _buscador_sem_rede(url: str):
    """`url_fetcher` do WeasyPrint que só entrega o que já veio embutido.

    **O padrão do WeasyPrint busca URL de verdade** — `http://`, `file://`, o
    que estiver no HTML. Hoje nenhum dos dois templates tem `img`, `url()` ou
    `|safe`, e o autoescape do Django segura o resto, então não há SSRF; o
    problema é que a primeira pessoa a pôr o logo do tenant no cabeçalho abre a
    porta para metadado de nuvem (`169.254.169.254`) e para `file:///etc/…`, e
    não vai lembrar disto. É a diferença entre *não estar sendo explorado* e
    *não ser explorável*.

    `data:` passa porque não é busca: o conteúdo já está no documento. Todo o
    resto é recusado, e o WeasyPrint trata exceção de `url_fetcher` **pulando o
    recurso** — o PDF sai sem a imagem, em vez de não sair. Quando um logo
    embutido for pedido de verdade, o caminho é o `data:` URI, que este
    buscador já aceita.
    """
    return _novo_buscador()(url)


def html_para_pdf(html: str) -> bytes:
    """HTML → PDF, com o buscador fechado. **A única porta de PDF do sistema.**

    Existe como função e não como linha repetida porque `HTML(string=…)` sem
    `url_fetcher` é seguro por acidente (depende do template do dia), e um
    segundo `write_pdf()` em outro módulo reabriria o D73 sem ninguém notar.
    """
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - dependência de requirements
        raise EscritaIndisponivel(
            "WeasyPrint não instalado — necessário para exportar PDF."
        ) from exc

    return HTML(string=html, url_fetcher=_novo_buscador()).write_pdf()


def escrever(formato: str, *, colunas, linhas, procedencia: dict) -> tuple[bytes, str]:
    """Despacha por formato. Devolve `(bytes, content_type)`."""
    if formato == "xlsx":
        return _xlsx(colunas, linhas, procedencia), (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    if formato == "csv":
        return _csv(colunas, linhas), "text/csv; charset=utf-8"
    if formato == "pdf":
        return _pdf(colunas, linhas, procedencia), "application/pdf"
    raise EscritaIndisponivel(f"Formato de saída não suportado: {formato!r}.")


def _valor_para_celula(coluna, valor):
    """openpyxl aceita Decimal, mas grava como texto em algumas versões.

    Converter para float aqui é o que garante a R8 — a célula chega no Excel
    como número, somável, e não como string alinhada à esquerda.
    """
    if valor is None:
        return None
    if coluna.tipo is Decimal:
        return float(valor)
    if coluna.tipo is int:
        return int(valor)
    if coluna.tipo is bool:
        return "Sim" if valor else "Não"
    if coluna.tipo is date:
        # Data de verdade na célula (R8): o Excel ordena e filtra por ela.
        return _como_data(valor)
    return str(valor)


def _como_data(valor) -> date | None:
    """Aceita `date`, `datetime` ou ISO em texto — o que vier do `queryset`."""
    if isinstance(valor, date):
        return valor if type(valor) is date else valor.date()
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _data_br(valor) -> str:
    dia = _como_data(valor)
    return dia.strftime("%d/%m/%Y") if dia else ""


# ---------------------------------------------------------------------------
# Injeção de fórmula — o arquivo que sai não pode ser executável
# ---------------------------------------------------------------------------
# **O defeito é de quem GERA o arquivo, não do Excel** (OWASP, *CSV Injection*).
# Um fornecedor cadastra a razão social como `=cmd|'/c calc'!A1`, o dado entra
# pelo cadastro normal, e quem abre a planilha exportada executa a fórmula — o
# alvo é o cliente do nosso cliente, e o veículo somos nós. É o oposto exato da
# R9: a peça sai executável em vez de conferível.
#
# Os gatilhos são os quatro caracteres que o Excel/Sheets/Calc leem como início
# de fórmula, mais tabulação e retorno de carro, que servem para escondê-los.
_GATILHOS_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _neutraliza_csv(texto: str) -> str:
    """Prefixa `'` no que o Excel leria como fórmula ao ABRIR um CSV.

    A mitigação da OWASP, e ela custa um apóstrofo visível — aceitável aqui e
    não no XLSX porque os dois formatos têm públicos diferentes: o CSV existe
    "para quem vai ler com script", e script ignora o apóstrofo; o XLSX é o que
    a pessoa abre para trabalhar, e lá a correção é outra (`_texto_xlsx`).

    Só o caminho de TEXTO passa por aqui. Número e data saem tipados (R8) e não
    são reinterpretados — então o `-` de um valor negativo continua intacto.
    """
    if texto and texto[0] in _GATILHOS_DE_FORMULA:
        return "'" + texto
    return texto


def _forcar_texto(celula) -> None:
    """Impede o openpyxl de gravar `=...` como FÓRMULA de verdade.

    No XLSX o risco é menor e mais preciso que no CSV: célula de string é
    string, e o Excel não a reinterpreta ao abrir — `+`, `-` e `@` são inofensivos
    ali. O que sobra é o `=`, porque o **openpyxl** infere o tipo no `append` e
    grava um `<f>` no XML; nesse caso o arquivo sai com uma fórmula real dentro.
    Fixar `data_type` depois da atribuição desfaz a inferência sem sujar o valor,
    que é o motivo de não usarmos o apóstrofo aqui.
    """
    if isinstance(celula.value, str) and celula.value.startswith("="):
        celula.data_type = "s"


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------


def _xlsx(colunas, linhas, procedencia: dict) -> bytes:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError as exc:  # pragma: no cover - dependência de requirements
        raise EscritaIndisponivel(
            "openpyxl não instalado — necessário para exportar XLSX."
        ) from exc

    wb = Workbook()
    ws = wb.active
    ws.title = (procedencia.get("recurso_rotulo") or "Dados")[:31]

    ws.append([procedencia.get("recurso_rotulo", "")])
    ws["A1"].font = Font(bold=True, size=13)
    if procedencia.get("recorte"):
        ws.append([f"Recorte: {procedencia['recorte']}"])
    ws.append([
        f"Emitido por {procedencia.get('usuario', '—')} "
        f"em {procedencia.get('emitido_em', '—')} · {procedencia.get('linhas', 0)} linhas"
    ])
    ws.append([])

    linha_cabecalho = ws.max_row + 1
    ws.append([c.rotulo for c in colunas])
    negrito = Font(bold=True)
    fundo = PatternFill("solid", fgColor="E8EDF5")
    borda = Border(bottom=Side(style="thin", color="C9D2E0"))
    for pos in range(1, len(colunas) + 1):
        celula = ws.cell(row=linha_cabecalho, column=pos)
        celula.font = negrito
        celula.fill = fundo
        celula.border = borda
        celula.alignment = Alignment(horizontal="center", wrap_text=True)

    for linha in linhas:
        ws.append([_valor_para_celula(c, linha.get(c.campo)) for c in colunas])
        for celula in ws[ws.max_row]:
            _forcar_texto(celula)

    for pos, coluna in enumerate(colunas, start=1):
        largura = 46 if coluna.tipo is str and pos == 2 else max(12, min(34, len(coluna.rotulo) + 6))
        ws.column_dimensions[get_column_letter(pos)].width = largura
        if coluna.tipo is Decimal:
            for celula in ws[get_column_letter(pos)][linha_cabecalho:]:
                celula.number_format = "#,##0.00"
        elif coluna.tipo is date:
            for celula in ws[get_column_letter(pos)][linha_cabecalho:]:
                celula.number_format = "dd/mm/yyyy"
    ws.freeze_panes = ws.cell(row=linha_cabecalho + 1, column=1)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def _csv(colunas, linhas) -> bytes:
    """`;` como delimitador e vírgula decimal — é o que o Excel-pt-BR abre direto.

    O BOM (`utf-8-sig`) não é enfeite: sem ele o Excel do Windows lê o arquivo
    como latin-1 e todo acento vira mojibake no primeiro duplo-clique.
    """
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    escritor.writerow([c.rotulo for c in colunas])
    for linha in linhas:
        saida = []
        for coluna in colunas:
            valor = linha.get(coluna.campo)
            if valor is None:
                saida.append("")
            elif coluna.tipo is Decimal:
                saida.append(str(valor).replace(".", ","))
            elif coluna.tipo is bool:
                saida.append("Sim" if valor else "Não")
            elif coluna.tipo is date:
                saida.append(_data_br(valor))
            else:
                saida.append(_neutraliza_csv(str(valor)))
        escritor.writerow(saida)
    return buffer.getvalue().encode("utf-8-sig")


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _pdf(colunas, linhas, procedencia: dict) -> bytes:
    """HTML → PDF pelo WeasyPrint.

    Em vez de desenho programático porque a peça precisa de cabeçalho repetido
    por página, quebra que não parte uma linha ao meio e numeração — tudo isso o
    motor de impressão resolve com CSS, e uma biblioteca de desenho exigiria
    reimplementar cada um.
    """
    # O template recebe primitivos, não os dataclasses: o Django proíbe acesso a
    # atributo iniciado por `_` (e `tipo.__name__` seria TemplateSyntaxError), e
    # decidir alinhamento no Python deixa o template só com apresentação.
    numericas = [c.tipo in (Decimal, int) for c in colunas]
    html = render_to_string("funcoesimpexp/tabela.html", {
        "procedencia": procedencia,
        "colunas": [
            {"rotulo": c.rotulo, "numerica": num} for c, num in zip(colunas, numericas)
        ],
        "linhas": [
            [
                {"texto": _texto_pdf(c, linha.get(c.campo)), "numerica": num}
                for c, num in zip(colunas, numericas)
            ]
            for linha in linhas
        ],
    })
    return html_para_pdf(html)


def _texto_pdf(coluna, valor) -> str:
    if valor is None:
        return ""
    if coluna.tipo is Decimal:
        return f"{Decimal(valor):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    if coluna.tipo is bool:
        return "Sim" if valor else "Não"
    if coluna.tipo is date:
        return _data_br(valor)
    return str(valor)
