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
import io
from decimal import Decimal

from django.template.loader import render_to_string


class EscritaIndisponivel(Exception):
    """Biblioteca de escrita ausente no ambiente."""


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
    return str(valor)


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

    for pos, coluna in enumerate(colunas, start=1):
        largura = 46 if coluna.tipo is str and pos == 2 else max(12, min(34, len(coluna.rotulo) + 6))
        ws.column_dimensions[get_column_letter(pos)].width = largura
        if coluna.tipo is Decimal:
            for celula in ws[get_column_letter(pos)][linha_cabecalho:]:
                celula.number_format = "#,##0.00"
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
            else:
                saida.append(str(valor))
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
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - dependência de requirements
        raise EscritaIndisponivel(
            "WeasyPrint não instalado — necessário para exportar PDF."
        ) from exc

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
    return HTML(string=html).write_pdf()


def _texto_pdf(coluna, valor) -> str:
    if valor is None:
        return ""
    if coluna.tipo is Decimal:
        return f"{Decimal(valor):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    if coluna.tipo is bool:
        return "Sim" if valor else "Não"
    return str(valor)
