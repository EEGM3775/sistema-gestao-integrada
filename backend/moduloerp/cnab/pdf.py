"""O boleto em PDF — recibo do pagador e ficha de compensação.

O código de barras é o **intercalado 2 de 5** que toda leitora bancária lê:
cada par de dígitos vira cinco barras (o primeiro) entremeadas com cinco espaços
(o segundo), largas ou estreitas. A proporção 3:1 e a altura de 13 mm são as
da especificação FEBRABAN para a ficha de compensação.
"""
from __future__ import annotations

from html import escape

from .bancos import banco_de

PADROES = {
    "0": "nnwwn", "1": "wnnnw", "2": "nwnnw", "3": "wwnnn", "4": "nnwnw",
    "5": "wnwnn", "6": "nwwnn", "7": "nnnww", "8": "wnnwn", "9": "nwnwn",
}
ESTREITA, LARGA = 1, 3


def svg_codigo_barras(codigo: str) -> str:
    """O I2of5 como SVG (unidades relativas; a largura final vem do CSS)."""
    barras = []  # (é barra?, largura)
    barras += [(True, ESTREITA), (False, ESTREITA), (True, ESTREITA), (False, ESTREITA)]  # início
    for i in range(0, len(codigo), 2):
        a, b = PADROES[codigo[i]], PADROES[codigo[i + 1]]
        for x, y in zip(a, b):
            barras.append((True, LARGA if x == "w" else ESTREITA))
            barras.append((False, LARGA if y == "w" else ESTREITA))
    barras += [(True, LARGA), (False, ESTREITA), (True, ESTREITA)]  # fim
    x, rects = 0, []
    for eh_barra, largura in barras:
        if eh_barra:
            rects.append(f'<rect x="{x}" y="0" width="{largura}" height="50"/>')
        x += largura
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {x} 50" preserveAspectRatio="none" '
        f'style="width:103mm;height:13mm">{"".join(rects)}</svg>'
    )


def _documento(valor) -> str:
    """CPF ou CNPJ com a pontuação de leitura — o banco de dados guarda só os dígitos."""
    d = "".join(ch for ch in str(valor or "") if ch.isdigit())
    if len(d) == 14:
        return f"CNPJ {d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"CPF {d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return d


def _reais(v) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def html_do_boleto(boleto) -> str:
    conta = boleto.conta_receber
    carteira = boleto.conta_cobranca
    banco = banco_de(carteira)
    cliente = conta.cliente
    nn = (boleto.dados_retorno_api or {}).get("nosso_numero_impresso") or boleto.nosso_numero
    venc = boleto.data_vencimento.strftime("%d/%m/%Y")
    emissao = boleto.data_emissao.strftime("%d/%m/%Y")
    instrucoes = [carteira.instrucoes] if carteira.instrucoes else []
    if boleto.valor_multa or boleto.valor_juros:
        instrucoes.append(
            f"Segunda via: inclui multa de R$ {_reais(boleto.valor_multa)} e juros de R$ {_reais(boleto.valor_juros)}."
        )
    endereco = ", ".join(p for p in (cliente.endereco, cliente.numero_endereco, cliente.bairro) if p)
    cidade = f"{cliente.cidade}/{cliente.estado} · CEP {cliente.cep}"
    campos = {
        "banco": f"{banco.codigo}-{_dv_banco(banco.codigo)}",
        "linha": escape(boleto.linha_digitavel or ""),
        "beneficiario": escape(f"{carteira.beneficiario_nome} · {_documento(carteira.beneficiario_documento)}"),
        "agencia": escape(banco.beneficiario_impresso(carteira)),
        "nn": escape(nn), "venc": venc, "emissao": emissao,
        "valor": _reais(boleto.valor), "doc": conta.conta_receber_id,
        "pagador": escape(f"{cliente.nome_completo} · {_documento(cliente.cpf_cnpj)}"),
        "endereco": escape(f"{endereco} — {cidade}"),
        "descricao": escape(conta.descricao),
        "instrucoes": "<br>".join(escape(i) for i in instrucoes) or "&nbsp;",
        "carteira": escape(carteira.carteira), "barras": svg_codigo_barras(boleto.codigo_barras),
    }
    return _MODELO.format(**campos)


def _dv_banco(codigo: str) -> str:
    return {"001": "9", "033": "7", "104": "0", "237": "2", "341": "7", "748": "X", "756": "0"}.get(codigo, "0")


def pdf_do_boleto(boleto) -> bytes:
    # A porta única de PDF (D73): o buscador fechado impede que o HTML, que leva
    # nome e endereço do pagador, faça o servidor buscar qualquer coisa na rede.
    from funcoesimpexp.formatos.escrita import html_para_pdf
    return html_para_pdf(html_do_boleto(boleto))


_MODELO = """<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 12mm; }}
body {{ font-family: Arial, Helvetica, sans-serif; font-size: 8.5pt; color: #000; }}
.cab {{ display: flex; align-items: flex-end; border-bottom: 2px solid #000; padding-bottom: 2mm; }}
.cab .bco {{ font-size: 15pt; font-weight: bold; border-left: 2px solid #000; border-right: 2px solid #000; padding: 0 3mm; margin-right: 3mm; }}
.cab .linha {{ font-size: 11pt; font-weight: bold; margin-left: auto; letter-spacing: .3pt; }}
table {{ width: 100%; border-collapse: collapse; }}
td {{ border: 1px solid #000; padding: 1mm 1.5mm; vertical-align: top; }}
td small {{ display: block; font-size: 6.5pt; color: #333; }}
td b {{ font-size: 9pt; }}
.dir {{ width: 42mm; }}
.corte {{ border-top: 1px dashed #000; margin: 7mm 0 5mm; font-size: 6.5pt; text-align: right; }}
.barras {{ margin-top: 3mm; }}
</style></head><body>
<div class="cab"><span class="bco">{banco}</span><b>Recibo do pagador</b><span class="linha">{linha}</span></div>
<table>
<tr><td colspan="3"><small>Beneficiário</small>{beneficiario}</td><td class="dir"><small>Vencimento</small><b>{venc}</b></td></tr>
<tr><td colspan="3"><small>Pagador</small>{pagador}</td><td class="dir"><small>Valor do documento</small><b>R$ {valor}</b></td></tr>
<tr><td colspan="3"><small>Referência</small>{descricao}</td><td class="dir"><small>Nosso número</small>{nn}</td></tr>
</table>
<div class="corte">Autenticação mecânica — corte aqui</div>
<div class="cab"><span class="bco">{banco}</span><span class="linha">{linha}</span></div>
<table>
<tr><td colspan="4"><small>Local de pagamento</small>Pagável em qualquer banco até o vencimento</td><td class="dir"><small>Vencimento</small><b>{venc}</b></td></tr>
<tr><td colspan="4"><small>Beneficiário</small>{beneficiario}</td><td class="dir"><small>Agência / código do beneficiário</small>{agencia}</td></tr>
<tr><td><small>Data do documento</small>{emissao}</td><td><small>Nº do documento</small>{doc}</td><td><small>Espécie doc.</small>DM</td><td><small>Aceite</small>N</td><td class="dir"><small>Nosso número</small>{nn}</td></tr>
<tr><td><small>Carteira</small>{carteira}</td><td><small>Espécie</small>R$</td><td colspan="2"><small>Data de processamento</small>{emissao}</td><td class="dir"><small>(=) Valor do documento</small><b>R$ {valor}</b></td></tr>
<tr><td colspan="4" rowspan="3"><small>Instruções (de responsabilidade do beneficiário)</small>{instrucoes}</td><td class="dir"><small>(−) Desconto / abatimento</small>&nbsp;</td></tr>
<tr><td class="dir"><small>(+) Mora / multa</small>&nbsp;</td></tr>
<tr><td class="dir"><small>(=) Valor cobrado</small>&nbsp;</td></tr>
<tr><td colspan="5"><small>Pagador</small>{pagador}<br>{endereco}</td></tr>
</table>
<div class="barras">{barras}</div>
<div style="font-size:6.5pt;text-align:right">Ficha de compensação</div>
</body></html>"""
