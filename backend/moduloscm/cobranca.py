# backend/moduloscm/cobranca.py
"""A cobrança do pedido: do valor da compra aos títulos do ERP (D284).

Mesmo desenho do motor da venda (`clientes.plano_pagamento`), que o dono
apontou como o mais robusto: **uma lista livre de meios**, cada um com o seu
valor e as suas parcelas, e a conta só fecha quando a soma dos meios é o valor
do pedido — nem um centavo a mais, nem a menos. Entrada no Pix, três cheques e
o resto no boleto é uma compra só.

- A parcela é o valor do meio dividido pelo número de parcelas, em centavos; o
  resto da divisão vai **na primeira** (é como o fornecedor emite: 100/3 vira
  33,34 + 33,33 + 33,33).
- O vencimento anda em **dias corridos** ("30/60/90" do comércio).
- Redefinir a cobrança cancela os títulos ainda sem pagamento e gera os novos.
  Com um título já pago, recusa: mexer nele é estorno, que é do financeiro.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation

from django.db import transaction
from django.utils.dateparse import parse_date

from payment.planos import SCM_COBRANCA_TETO_MEIOS, SCM_COBRANCA_TETO_PARCELAS

from . import financeiro
from .models import EventoPedido, MeioPagamentoPedido, ParcelaPedido

CENTAVO = Decimal("0.01")
ZERO = Decimal("0")


class CobrancaInvalida(ValueError):
    """A cobrança enviada não fecha ou não pode ser aplicada."""


def _dinheiro(v) -> Decimal:
    return Decimal(v).quantize(CENTAVO)


def ler_meios(dados) -> list[dict]:
    """Valida o que veio da tela. Devolve meios normalizados ou levanta."""
    if not isinstance(dados, list) or not dados:
        raise CobrancaInvalida("Inclua ao menos um meio de pagamento.")
    if len(dados) > SCM_COBRANCA_TETO_MEIOS:
        raise CobrancaInvalida(f"Uma cobrança comporta até {SCM_COBRANCA_TETO_MEIOS} meios de pagamento.")
    tipos = set(MeioPagamentoPedido.Tipo.values)
    meios, problemas = [], []
    for n, bruto in enumerate(dados, start=1):
        tipo = (bruto or {}).get("tipo")
        if tipo not in tipos:
            problemas.append(f"Meio {n}: escolha a forma de pagamento.")
            continue
        try:
            valor = _dinheiro(str(bruto.get("valor") or "0").replace(",", "."))
            parcelas = int(bruto.get("parcelas") or 1)
            intervalo = int(bruto.get("intervalo_dias") if bruto.get("intervalo_dias") not in (None, "") else 30)
        except (InvalidOperation, ValueError, TypeError):
            problemas.append(f"Meio {n}: valor, parcelas ou intervalo inválido.")
            continue
        vencimento = bruto.get("primeiro_vencimento")
        vencimento = vencimento if isinstance(vencimento, date) else parse_date(str(vencimento or ""))
        descricao = (bruto.get("descricao") or "").strip()[:200]
        if valor <= 0:
            problemas.append(f"Meio {n}: o valor precisa ser positivo.")
        elif not 1 <= parcelas <= SCM_COBRANCA_TETO_PARCELAS:
            problemas.append(f"Meio {n}: de 1 a {SCM_COBRANCA_TETO_PARCELAS} parcelas.")
        elif parcelas > 1 and intervalo < 1:
            problemas.append(f"Meio {n}: diga quantos dias entre as parcelas.")
        elif vencimento is None:
            problemas.append(f"Meio {n}: informe o 1º vencimento.")
        elif tipo == MeioPagamentoPedido.Tipo.OUTRO and not descricao:
            problemas.append(f"Meio {n}: em 'Outro', descreva o meio.")
        elif valor < CENTAVO * parcelas:
            problemas.append(f"Meio {n}: o valor não cobre um centavo por parcela.")
        else:
            meios.append({"tipo": tipo, "valor": valor, "parcelas": parcelas, "intervalo_dias": intervalo,
                          "primeiro_vencimento": vencimento, "descricao": descricao})
    if problemas:
        raise CobrancaInvalida(" ".join(problemas))
    return meios


def montar_parcelas(valor: Decimal, parcelas: int, primeiro_vencimento: date, intervalo_dias: int) -> list[tuple[int, date, Decimal]]:
    """`[(numero, vencimento, valor)]` — o resto dos centavos na primeira."""
    base = (valor / parcelas).quantize(CENTAVO, rounding=ROUND_DOWN)
    resto = valor - base * parcelas
    return [
        (n, primeiro_vencimento + timedelta(days=intervalo_dias * (n - 1)), base + (resto if n == 1 else ZERO))
        for n in range(1, parcelas + 1)
    ]


def conferir_total(meios: list[dict], valor_pedido) -> None:
    soma = sum((m["valor"] for m in meios), ZERO)
    alvo = _dinheiro(valor_pedido or 0)
    if soma != alvo:
        falta = alvo - soma
        raise CobrancaInvalida(
            f"Os meios somam R$ {soma} e o pedido é R$ {alvo} — "
            + (f"faltam R$ {falta}." if falta > 0 else f"sobram R$ {-falta}.")
        )


def _rotulo(meio: dict) -> str:
    nome = MeioPagamentoPedido.Tipo(meio["tipo"]).label
    vezes = f" em {meio['parcelas']}x" if meio["parcelas"] > 1 else ""
    return f"{nome}{vezes} R$ {meio['valor']}"


@transaction.atomic
def definir_cobranca(pedido, dados, *, autor=None) -> list[int]:
    """Grava a cobrança e gera os títulos. Devolve os ids dos títulos novos."""
    meios = ler_meios(dados)
    conferir_total(meios, pedido.valor_total)

    vivos = financeiro.titulos(pedido)
    if any(c.valor_pago and c.valor_pago > 0 for c in vivos):
        raise CobrancaInvalida(
            "Um título deste pedido já tem pagamento no ERP. Para mudar a cobrança, o "
            "financeiro precisa estornar a baixa antes."
        )
    redefinicao = pedido.meios_pagamento.exists()
    if vivos:
        financeiro.cancelar_titulos(pedido, motivo="Cobrança do pedido redefinida.", autor=autor)
    pedido.meios_pagamento.all().delete()

    for ordem, meio in enumerate(meios, start=1):
        registro = MeioPagamentoPedido.objects.create(tenant_id=pedido.tenant_id, pedido=pedido, ordem=ordem, **meio)
        ParcelaPedido.objects.bulk_create([
            ParcelaPedido(tenant_id=pedido.tenant_id, meio=registro, numero=n, vencimento=venc, valor=v)
            for n, venc, v in montar_parcelas(meio["valor"], meio["parcelas"], meio["primeiro_vencimento"], meio["intervalo_dias"])
        ])

    financeiro.registrar_evento(
        pedido, EventoPedido.Tipo.COBRANCA,
        ("Cobrança redefinida: " if redefinicao else "Cobrança: ") + " + ".join(_rotulo(m) for m in meios) + ".",
        valor=_dinheiro(pedido.valor_total or 0), autor=autor, vai_ao_erp=True,
    )
    return financeiro.gerar_titulos(pedido, autor=autor)


def resumo(pedido) -> dict:
    """A cobrança como a tela mostra: meios, parcelas e o título de cada uma."""
    meios = list(pedido.meios_pagamento.prefetch_related("parcelas_geradas"))
    refs = [p.conta_pagar_ref for m in meios for p in m.parcelas_geradas.all() if p.conta_pagar_ref]
    situacao_titulo = {}
    erp = financeiro._erp()
    if erp is not None and refs:
        for c in erp[0].objects.filter(tenant_id=pedido.tenant_id, pk__in=refs):
            situacao_titulo[c.pk] = {"status": c.status, "valor_pago": str(c.valor_pago)}
    soma = sum((m.valor for m in meios), ZERO)
    alvo = _dinheiro(pedido.valor_total or 0)
    return {
        "meios": [{
            "meio_id": m.meio_id, "tipo": m.tipo, "tipo_nome": m.get_tipo_display(), "valor": str(m.valor),
            "parcelas": m.parcelas, "primeiro_vencimento": m.primeiro_vencimento.isoformat(),
            "intervalo_dias": m.intervalo_dias, "descricao": m.descricao,
            "parcelas_geradas": [{
                "numero": p.numero, "vencimento": p.vencimento.isoformat(), "valor": str(p.valor),
                "conta_pagar_ref": p.conta_pagar_ref,
                "titulo_status": situacao_titulo.get(p.conta_pagar_ref, {}).get("status"),
                "titulo_valor_pago": situacao_titulo.get(p.conta_pagar_ref, {}).get("valor_pago"),
            } for p in m.parcelas_geradas.all()],
        } for m in meios],
        "soma": str(soma),
        "valor_pedido": str(alvo),
        # Pedido editado depois da cobrança: a soma deixa de fechar e a tela pede
        # para redefinir. Não se ajusta sozinho — o título é do financeiro.
        "confere": bool(meios) and soma == alvo,
        "tipos": [{"valor": v, "rotulo": r} for v, r in MeioPagamentoPedido.Tipo.choices],
    }
