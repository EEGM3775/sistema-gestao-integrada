# backend/funcoesimpexp/modelo.py
"""IE.0 — a planilha-modelo, gerada das mesmas colunas que validam a importação.

É a R2 na prática, e a razão de ela existir: se o modelo que o usuário baixa
nascer num lugar e o validador da importação noutro, um campo muda em um só e a
pessoa passa a preencher o modelo "certo" que a importação recusa — ou, pior,
aceita torto. Aqui os dois saem do mesmo `recurso.colunas`, então não há como
divergirem.

O modelo traz três coisas além dos cabeçalhos, e cada uma evita uma ida e volta
de suporte: a **coluna-chave marcada** (é ela que decide atualizar × duplicar),
as **obrigatórias em destaque** e uma **linha de exemplo** preenchida — ninguém
acerta o formato de data ou de decimal na primeira tentativa olhando só o título
da coluna.
"""
from __future__ import annotations

import io

from .formatos.escrita import EscritaIndisponivel
from .registro import Recurso


def planilha_modelo(recurso: Recurso) -> bytes:
    """XLSX modelo do recurso: cabeçalhos, instruções e uma linha de exemplo."""
    try:
        from openpyxl import Workbook
        from openpyxl.comments import Comment
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as exc:  # pragma: no cover - dependência de requirements
        raise EscritaIndisponivel(
            "openpyxl não instalado — necessário para gerar o modelo."
        ) from exc

    wb = Workbook()
    ws = wb.active
    ws.title = "Modelo"

    ws.append([f"Modelo de importação — {recurso.rotulo}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([
        "Preencha a partir da linha 5. Não altere os títulos: é por eles que o "
        "sistema reconhece as colunas."
    ])
    chave = recurso.coluna_chave
    if chave is not None:
        ws.append([
            f"Coluna-chave: «{chave.rotulo}». Linha com chave que já existe "
            "ATUALIZA o registro; chave nova cria."
        ])
    else:
        ws.append([])
    ws.append([])

    linha_cabecalho = ws.max_row + 1
    ws.append([c.rotulo for c in recurso.colunas])

    obrigatoria = PatternFill("solid", fgColor="FDE8C8")
    normal = PatternFill("solid", fgColor="E8EDF5")
    for pos, coluna in enumerate(recurso.colunas, start=1):
        celula = ws.cell(row=linha_cabecalho, column=pos)
        celula.font = Font(bold=True)
        celula.fill = obrigatoria if coluna.obrigatoria else normal
        celula.alignment = Alignment(horizontal="center", wrap_text=True)
        nota = [f"Campo: {coluna.campo}", f"Tipo: {_tipo_legivel(coluna)}"]
        if coluna.obrigatoria:
            nota.append("OBRIGATÓRIA")
        if coluna.campo == recurso.chave:
            nota.append("Coluna-chave (decide criar × atualizar)")
        if coluna.exemplo:
            nota.append(f"Exemplo: {coluna.exemplo}")
        celula.comment = Comment("\n".join(nota), "SGI")
        ws.column_dimensions[get_column_letter(pos)].width = max(
            14, min(38, len(coluna.rotulo) + 8),
        )

    ws.append([c.exemplo or _exemplo_padrao(c) for c in recurso.colunas])
    for pos in range(1, len(recurso.colunas) + 1):
        ws.cell(row=ws.max_row, column=pos).font = Font(italic=True, color="94A3B8")

    ws.freeze_panes = ws.cell(row=linha_cabecalho + 1, column=1)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def nome_do_modelo(recurso: Recurso) -> str:
    base = "".join(
        c if c.isalnum() or c in "-_" else "-" for c in f"modelo-{recurso.rotulo}".lower()
    )
    while "--" in base:
        base = base.replace("--", "-")
    return f"{base.strip('-')}.xlsx"


def _tipo_legivel(coluna) -> str:
    from datetime import date
    from decimal import Decimal

    return {
        str: "texto",
        int: "número inteiro",
        Decimal: "número decimal (use vírgula: 1.234,56)",
        bool: "Sim/Não",
        date: "data (dd/mm/aaaa)",
    }.get(coluna.tipo, "texto")


def _exemplo_padrao(coluna) -> str:
    from datetime import date
    from decimal import Decimal

    return {
        str: "texto", int: "10", Decimal: "0,00", bool: "Sim", date: "31/01/2026",
    }.get(coluna.tipo, "")
