# backend/moduloorcamento/exportacao.py
"""ORC.5b — a planilha sai do sistema: XLSX e PDF.

Exportar não é conveniência: é a **entrega**. A planilha vai para o edital, para
o cliente e para o cartório, e nesses destinos o arquivo *é* o produto. Por isso
o que sai daqui carrega o cabeçalho completo (obra, versão, data-base, regime de
encargos, BDI) — uma planilha de custo sem data-base declarada não é conferível,
e é a primeira coisa que um analista de licitação procura.

Duas saídas com propósitos diferentes:

- **XLSX** é para trabalhar: o destinatário vai filtrar, somar e comparar. Sai
  com as colunas separadas e os números como número (não texto), senão a primeira
  coisa que a pessoa faz é reconverter tudo.
- **PDF** é para arquivar e assinar: layout fixo, totais fechados, sem risco de
  alguém "ajustar" uma célula no caminho.

O sintético e o analítico são o mesmo dado em dois níveis de leitura (a
convenção da própria SINAPI) — quem escolhe é quem exporta.
"""
from __future__ import annotations

import io
from decimal import Decimal

from django.template.loader import render_to_string
from django.utils import timezone

from .models import ItemOrcado, Orcamento
from .planilha import dinheiro


class ExportacaoIndisponivel(Exception):
    """Biblioteca de exportação ausente no ambiente."""


CABECALHO_PLANILHA = (
    "Item", "Fonte", "Código", "Descrição", "Und", "Quantidade",
    "Custo unitário", "Total custo direto", "BDI %", "Total com BDI", "Peso %",
)


def _linhas_da_planilha(orcamento: Orcamento, *, analitico: bool) -> list[dict]:
    """Árvore achatada na ordem de leitura da EAP."""
    itens = list(
        ItemOrcado.objects.filter(orcamento=orcamento)
        .select_related("etapa")
        .order_by("codigo_eap", "ordem", "item_orcado_id")
    )
    if not analitico:
        # Sintético mostra os agrupadores e o primeiro nível — a leitura de quem
        # quer o total por etapa, não a composição item a item.
        itens = [i for i in itens if i.tipo_linha == ItemOrcado.TipoLinha.SINTETICO
                 or i.codigo_eap.count(".") <= 1]

    total = orcamento.valor_total or Decimal("0")
    bdi_padrao = orcamento.bdi_percentual or Decimal("0")
    return [
        {
            "codigo_eap": item.codigo_eap,
            "fonte": (item.fonte_referencia or "").upper(),
            "codigo_referencia": item.codigo_referencia,
            "descricao": item.descricao,
            "unidade": item.unidade,
            "quantidade": item.quantidade if item.custa else None,
            "custo_unitario": item.custo_unitario if item.custa else None,
            "total_custo_direto": item.total_custo_direto,
            "bdi": bdi_padrao,
            "total_com_bdi": item.total_com_bdi,
            "peso": (
                (item.total_com_bdi / total * Decimal("100")).quantize(Decimal("0.01"))
                if total else Decimal("0")
            ),
            "sintetico": item.tipo_linha == ItemOrcado.TipoLinha.SINTETICO,
            "nivel": item.codigo_eap.count("."),
        }
        for item in itens
    ]


def contexto_do_cabecalho(orcamento: Orcamento) -> dict:
    return {
        "obra": orcamento.obra.nome_obra,
        "descricao": orcamento.descricao,
        "versao": orcamento.versao,
        "status": orcamento.get_status_display(),
        "base": (
            orcamento.base_referencial.rotulo or orcamento.base_referencial.rotulo_automatico()
            if orcamento.base_referencial_id else "sem base referencial"
        ),
        "data_base": orcamento.data_base,
        "regime_encargos": orcamento.get_regime_encargos_display(),
        "encargos": orcamento.encargos_sociais_percentual,
        "bdi": orcamento.bdi_percentual,
        "custo_direto_total": orcamento.custo_direto_total,
        "valor_total": orcamento.valor_total,
        "emitido_em": timezone.now(),
    }


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------


def planilha_xlsx(orcamento: Orcamento, *, analitico: bool = True) -> bytes:
    """Planilha orçamentária como arquivo Excel, com números como número."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError as exc:  # pragma: no cover - dependência de requirements
        raise ExportacaoIndisponivel(
            "openpyxl não instalado — necessário para exportar XLSX."
        ) from exc

    cabecalho = contexto_do_cabecalho(orcamento)
    wb = Workbook()
    ws = wb.active
    ws.title = "Orçamento"

    negrito = Font(bold=True)
    titulo = Font(bold=True, size=13)
    fundo = PatternFill("solid", fgColor="E8EDF5")
    fundo_sintetico = PatternFill("solid", fgColor="F3F5F9")
    borda = Border(bottom=Side(style="thin", color="C9D2E0"))

    ws.append([f"{cabecalho['descricao']} — {cabecalho['obra']}"])
    ws["A1"].font = titulo
    ws.append([
        f"Versão {cabecalho['versao']} ({cabecalho['status']})",
        f"Base: {cabecalho['base']}",
        f"Data-base: {cabecalho['data_base'] or '—'}",
        f"Encargos: {cabecalho['encargos']}% ({cabecalho['regime_encargos']})",
        f"BDI: {cabecalho['bdi']}%",
    ])
    ws.append([f"Emitido em {cabecalho['emitido_em']:%d/%m/%Y %H:%M}"])
    ws.append([])

    linha_cabecalho = ws.max_row + 1
    ws.append(list(CABECALHO_PLANILHA))
    for coluna in range(1, len(CABECALHO_PLANILHA) + 1):
        celula = ws.cell(row=linha_cabecalho, column=coluna)
        celula.font = negrito
        celula.fill = fundo
        celula.border = borda
        celula.alignment = Alignment(horizontal="center", wrap_text=True)

    for linha in _linhas_da_planilha(orcamento, analitico=analitico):
        ws.append([
            linha["codigo_eap"],
            linha["fonte"],
            linha["codigo_referencia"],
            ("    " * linha["nivel"]) + linha["descricao"],
            linha["unidade"],
            float(linha["quantidade"]) if linha["quantidade"] is not None else None,
            float(linha["custo_unitario"]) if linha["custo_unitario"] is not None else None,
            float(linha["total_custo_direto"]),
            float(linha["bdi"]),
            float(linha["total_com_bdi"]),
            float(linha["peso"]),
        ])
        if linha["sintetico"]:
            for coluna in range(1, len(CABECALHO_PLANILHA) + 1):
                celula = ws.cell(row=ws.max_row, column=coluna)
                celula.font = negrito
                celula.fill = fundo_sintetico

    ws.append([])
    ws.append([
        "", "", "", "TOTAL", "", "", "",
        float(cabecalho["custo_direto_total"]), "", float(cabecalho["valor_total"]), "",
    ])
    for coluna in (4, 8, 10):
        ws.cell(row=ws.max_row, column=coluna).font = negrito

    for coluna, largura in enumerate(
        (12, 10, 14, 62, 8, 14, 16, 18, 8, 18, 9), start=1,
    ):
        ws.column_dimensions[get_column_letter(coluna)].width = largura
    for coluna in ("F", "G", "H", "J"):
        for celula in ws[coluna]:
            celula.number_format = "#,##0.00"
    ws.freeze_panes = ws.cell(row=linha_cabecalho + 1, column=1)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def curva_abc_xlsx(orcamento: Orcamento, dados: dict) -> bytes:
    """Curva ABC como planilha — a lista que vai para a negociação de compra."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as exc:  # pragma: no cover
        raise ExportacaoIndisponivel("openpyxl não instalado.") from exc

    wb = Workbook()
    ws = wb.active
    ws.title = "Curva ABC"
    ws.append([f"Curva ABC — {orcamento.descricao} (v{orcamento.versao})"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])

    ws.append(["Classe", "Item", "Descrição", "Und", "Quantidade", "Valor", "%", "% acumulado"])
    for coluna in range(1, 9):
        celula = ws.cell(row=3, column=coluna)
        celula.font = Font(bold=True)
        celula.fill = PatternFill("solid", fgColor="E8EDF5")

    for linha in dados.get("itens", []):
        ws.append([
            linha["classe"], linha["codigo_eap"], linha["descricao"], linha["unidade"],
            float(linha["quantidade"]), float(linha["valor"]),
            float(linha["pct"]), float(linha["pct_acumulado"]),
        ])

    for coluna, largura in enumerate((9, 12, 64, 8, 14, 16, 9, 13), start=1):
        ws.column_dimensions[get_column_letter(coluna)].width = largura

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def cronograma_xlsx(orcamento: Orcamento, dados: dict) -> bytes:
    """Cronograma físico-financeiro: etapas nas linhas, competências nas colunas."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as exc:  # pragma: no cover
        raise ExportacaoIndisponivel("openpyxl não instalado.") from exc

    competencias = dados.get("competencias", [])
    wb = Workbook()
    ws = wb.active
    ws.title = "Cronograma"
    ws.append([f"Cronograma físico-financeiro — {orcamento.descricao} (v{orcamento.versao})"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])

    ws.append(["Etapa", *competencias, "Total"])
    for coluna in range(1, len(competencias) + 3):
        celula = ws.cell(row=3, column=coluna)
        celula.font = Font(bold=True)
        celula.fill = PatternFill("solid", fgColor="E8EDF5")

    for linha in dados.get("linhas", []):
        valores = []
        for competencia in competencias:
            celula = linha["parcelas"].get(competencia)
            valores.append(float(celula["valor_previsto"]) if celula else 0.0)
        ws.append([linha["etapa_nome"], *valores, float(linha["total"])])

    ws.append([])
    totais = []
    for competencia in competencias:
        soma = sum(
            float(l["parcelas"][competencia]["valor_previsto"])
            for l in dados.get("linhas", []) if competencia in l["parcelas"]
        )
        totais.append(soma)
    ws.append(["Desembolso previsto", *totais, float(dados.get("total", 0))])
    for coluna in range(1, len(competencias) + 3):
        ws.cell(row=ws.max_row, column=coluna).font = Font(bold=True)

    ws.column_dimensions["A"].width = 34
    for coluna in range(2, len(competencias) + 3):
        ws.column_dimensions[get_column_letter(coluna)].width = 15

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def planilha_pdf(orcamento: Orcamento, *, analitico: bool = True) -> bytes:
    """Planilha em PDF pelo WeasyPrint, a partir de um template HTML.

    HTML → PDF em vez de desenho programático porque a peça precisa de cabeçalho
    repetido por página, quebra que não parte uma linha ao meio e numeração —
    tudo isso o motor de impressão do WeasyPrint resolve com CSS, e uma
    biblioteca de desenho exigiria reimplementar cada um.
    """
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - dependência de requirements
        raise ExportacaoIndisponivel(
            "WeasyPrint não instalado — necessário para exportar PDF."
        ) from exc

    html = render_to_string("moduloorcamento/planilha.html", {
        "cabecalho": contexto_do_cabecalho(orcamento),
        "linhas": _linhas_da_planilha(orcamento, analitico=analitico),
        "analitico": analitico,
    })
    return HTML(string=html).write_pdf()


def nome_do_arquivo(orcamento: Orcamento, *, sufixo: str, extensao: str) -> str:
    """`orcamento-residencial-alfa-v2-analitico.xlsx` — legível na pasta de downloads."""
    base = f"{orcamento.descricao}-v{orcamento.versao}-{sufixo}"
    limpo = "".join(c if c.isalnum() or c in "-_" else "-" for c in base.lower())
    while "--" in limpo:
        limpo = limpo.replace("--", "-")
    return f"{limpo.strip('-')}.{extensao}"


def totais_conferencia(orcamento: Orcamento) -> dict:
    """Números que o rodapé de qualquer exportação repete, para conferência."""
    return {
        "custo_direto": str(dinheiro(orcamento.custo_direto_total or Decimal("0"))),
        "valor_total": str(dinheiro(orcamento.valor_total or Decimal("0"))),
        "linhas": ItemOrcado.objects.filter(orcamento=orcamento).count(),
    }
