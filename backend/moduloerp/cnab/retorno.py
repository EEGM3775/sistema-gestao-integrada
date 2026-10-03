"""O arquivo de retorno do banco — o que aconteceu com cada boleto.

Cada linha de detalhe diz o boleto (pelo número que pusemos no campo "uso da
empresa" — o id do boleto — ou, na falta, pelo nosso número) e a ocorrência:

| Ocorrência | O que o SGI faz |
|---|---|
| 02 entrada confirmada | o boleto passa a "Emitido" (registrado no banco) |
| 03 entrada rejeitada | "Erro", com o motivo do banco |
| 06, 15, 17 liquidação | baixa da conta pelo `dar_baixa(origem='cnab')` e boleto "Pago" |
| 09, 10 baixa | "Cancelado" |

**Ler o mesmo arquivo duas vezes não paga duas vezes**: boleto já pago não
recebe outra baixa — senão o `dar_baixa` mandaria o título para a revisão de
baixas com um pagamento que não existiu.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone

LIQUIDACAO = {"06", "15", "17"}
BAIXA = {"09", "10"}
OCORRENCIAS = {
    "02": "Entrada confirmada",
    "03": "Entrada rejeitada",
    "06": "Liquidação",
    "09": "Baixa",
    "10": "Baixa conforme instrução",
    "15": "Liquidação em cartório",
    "17": "Liquidação após baixa",
}


@dataclass
class Evento:
    uso_empresa: str
    nosso_numero: str
    ocorrencia: str
    data: date | None
    valor_pago: Decimal
    encargos: Decimal
    motivo: str


def _valor(trecho: str) -> Decimal:
    trecho = trecho.strip()
    return Decimal(int(trecho)) / 100 if trecho.isdigit() else Decimal("0")


def _data(trecho: str, formato: str) -> date | None:
    try:
        return datetime.strptime(trecho, formato).date()
    except ValueError:
        return None


def ler(conteudo: str) -> tuple[str, list[Evento]]:
    """`(layout, eventos)` — o layout sai do tamanho da primeira linha."""
    linhas = [l.rstrip("\r\n") for l in conteudo.splitlines() if l.strip()]
    if not linhas:
        raise ValueError("O arquivo está vazio.")
    largura = len(linhas[0])
    if largura >= 400:
        return "400", _ler_400(linhas)
    if largura >= 240:
        return "240", _ler_240(linhas)
    raise ValueError("Este arquivo não parece um retorno CNAB (linhas de 240 ou 400 posições).")


def _ler_240(linhas):
    eventos, atual = [], None
    for l in linhas:
        if len(l) < 240 or l[7] != "3":
            continue
        segmento = l[13]
        if segmento == "T":
            atual = Evento(
                uso_empresa=l[105:130].strip(), nosso_numero=l[37:57].strip(), ocorrencia=l[15:17],
                data=None, valor_pago=Decimal("0"), encargos=Decimal("0"), motivo=l[213:223].strip(),
            )
            eventos.append(atual)
        elif segmento == "U" and atual is not None:
            atual.encargos = _valor(l[17:32])
            atual.valor_pago = _valor(l[77:92])
            atual.data = _data(l[137:145], "%d%m%Y")
    return eventos


def _ler_400(linhas):
    eventos = []
    for l in linhas:
        if len(l) < 400 or l[0] != "1":
            continue
        eventos.append(Evento(
            uso_empresa=l[37:62].strip(), nosso_numero=l[62:82].strip(), ocorrencia=l[108:110],
            data=_data(l[110:116], "%d%m%y"), valor_pago=_valor(l[253:266]), encargos=_valor(l[266:279]),
            motivo=l[364:372].strip() if len(l) >= 372 else "",
        ))
    return eventos


def aplicar(carteira, conteudo: str, *, usuario) -> dict:
    """Lê o arquivo e aplica cada ocorrência. Devolve o resumo da tela."""
    from ..models import BaixaRequerRevisao, Boleto

    layout, eventos = ler(conteudo)
    resumo = {"layout": layout, "lidos": len(eventos), "registrados": 0, "rejeitados": 0,
              "pagos": 0, "baixados": 0, "ja_processados": 0, "nao_encontrados": 0,
              "em_revisao": 0, "valor_recebido": Decimal("0"), "detalhes": []}
    boletos = Boleto.objects.filter(conta_cobranca=carteira).select_related("conta_receber")
    por_id = {b.boleto_id: b for b in boletos}
    # O banco devolve o nosso número no formato dele (com carteira, DV, zeros);
    # o que guardamos está contido nele.
    por_nosso_numero = sorted(
        ((b.nosso_numero, b) for b in por_id.values() if b.nosso_numero), key=lambda p: -len(p[0]),
    )

    for ev in eventos:
        boleto = por_id.get(int(ev.uso_empresa)) if ev.uso_empresa.isdigit() else None
        if boleto is None and ev.nosso_numero:
            digitos = "".join(ch for ch in ev.nosso_numero if ch.isdigit())
            boleto = next((b for nn, b in por_nosso_numero if nn in digitos), None)
        if boleto is None:
            resumo["nao_encontrados"] += 1
            resumo["detalhes"].append({"nosso_numero": ev.nosso_numero, "ocorrencia": ev.ocorrencia,
                                       "resultado": "Boleto não encontrado nesta carteira"})
            continue

        rotulo = OCORRENCIAS.get(ev.ocorrencia, f"Ocorrência {ev.ocorrencia}")
        if ev.ocorrencia == "02":
            if boleto.status == Boleto.StatusBoleto.AGUARDANDO:
                boleto.status = Boleto.StatusBoleto.EMITIDO
                boleto.save(update_fields=["status", "atualizado_em"])
            resumo["registrados"] += 1
        elif ev.ocorrencia == "03":
            boleto.status = Boleto.StatusBoleto.ERRO
            boleto.dados_retorno_api = {"erro": f"O banco recusou o registro (motivo {ev.motivo or '—'}).",
                                        "motivo_banco": ev.motivo}
            boleto.save(update_fields=["status", "dados_retorno_api", "atualizado_em"])
            resumo["rejeitados"] += 1
        elif ev.ocorrencia in LIQUIDACAO:
            if boleto.status == Boleto.StatusBoleto.PAGO:
                resumo["ja_processados"] += 1
                continue
            conta = boleto.conta_receber
            pago = ev.valor_pago or boleto.valor
            multa = juros = Decimal("0")
            if (boleto.valor_multa or boleto.valor_juros) and pago >= boleto.valor:
                multa, juros = boleto.valor_multa, boleto.valor_juros
                juros += max(Decimal("0"), pago - boleto.valor)
            elif ev.encargos:
                juros = min(ev.encargos, pago)
            try:
                conta.dar_baixa(
                    valor=pago - multa - juros, multa=multa, juros=juros,
                    data=ev.data or timezone.localdate(), meio_pagamento="Boleto (CNAB)",
                    usuario=usuario, origem="cnab",
                )
            except BaixaRequerRevisao:
                resumo["em_revisao"] += 1
            boleto.status = Boleto.StatusBoleto.PAGO
            boleto.data_pagamento = timezone.now()
            boleto.save(update_fields=["status", "data_pagamento", "atualizado_em"])
            resumo["pagos"] += 1
            resumo["valor_recebido"] += pago
        elif ev.ocorrencia in BAIXA:
            if boleto.status not in (Boleto.StatusBoleto.PAGO, Boleto.StatusBoleto.CANCELADO):
                boleto.status = Boleto.StatusBoleto.CANCELADO
                boleto.data_cancelamento = timezone.now()
                boleto.save(update_fields=["status", "data_cancelamento", "atualizado_em"])
            resumo["baixados"] += 1
        resumo["detalhes"].append({"boleto_id": boleto.boleto_id, "ocorrencia": ev.ocorrencia, "resultado": rotulo})

    resumo["valor_recebido"] = str(resumo["valor_recebido"])
    resumo["detalhes"] = resumo["detalhes"][:500]
    return resumo
