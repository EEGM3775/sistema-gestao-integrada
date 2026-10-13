# backend/moduloscm/financeiro.py
"""A ponte Suprimentos → ERP: o que a compra faz no contas a pagar (D284).

*Dono, 11/10/2026:* "quando o pedido gera uma cobrança ela deve ir ao contas a
pagar. Quando o pedido é recebido ele pode ou não gerar uma nota, mas mesmo
assim fica esperando a nota" e "essas edições também têm que ir como anotações
ao ERP".

Quatro gestos, e só estes, tocam o ERP a partir daqui:

1. **gerar os títulos** — cada parcela da cobrança vira um `ContaPagar`, com a
   obra do centro de custo (é o que leva a compra à DRE da obra) e a situação da
   NF-e ("aguardando NF-e" até a nota chegar);
2. **anotar** — divergência de recebimento, edição do pedido, nota divergente:
   uma `AnotacaoContaPagar` em cada título vivo. A anotação não muda valor nem
   vencimento: quem decide o título é quem dá a baixa;
3. **sincronizar a NF-e** — número e situação da nota na linha do título;
4. **cancelar** — só o título sem pagamento. O que já teve baixa fica, anotado,
   para o financeiro resolver (estorno é ato dele, não da compra).

O SCM não depende do ERP no carregamento (imports tardios), como o PDCA faz:
instalação sem o financeiro registra o histórico e segue sem título.
"""
from __future__ import annotations

from decimal import Decimal

from .models import EventoPedido, ParcelaPedido

CANCELADO = "CANCELADO"
_TIPO_DA_ANOTACAO = {
    EventoPedido.Tipo.EDICAO: "edicao",
    EventoPedido.Tipo.DIVERGENCIA: "divergencia",
    EventoPedido.Tipo.NFE: "nfe",
    EventoPedido.Tipo.COBRANCA: "cobranca",
    EventoPedido.Tipo.CANCELAMENTO: "cancelamento",
}


def _erp():
    try:
        from moduloerp.models import AnotacaoContaPagar, ContaPagar
    except ImportError:  # pragma: no cover - instalação sem o financeiro
        return None
    return ContaPagar, AnotacaoContaPagar


def titulos(pedido, *, vivos: bool = True) -> list:
    erp = _erp()
    if erp is None:
        return []
    qs = erp[0].objects.filter(tenant_id=pedido.tenant_id, pedido_compra_ref=pedido.pk)
    if vivos:
        qs = qs.exclude(status=CANCELADO)
    return list(qs.order_by("data_vencimento", "pk"))


def situacao_nfe(pedido) -> tuple[str, str]:
    """(situação, números) que a linha do título mostra."""
    notas = list(pedido.notas_fiscais.all())
    if not notas:
        return "aguardando_nota", ""
    situacoes = {n.situacao for n in notas}
    if "divergente" in situacoes:
        situacao = "divergente"
    elif "aguardando_documento" in situacoes:
        situacao = "aguardando_documento"
    else:
        situacao = "conferida"
    return situacao, ", ".join(n.numero for n in notas)[:20]


def sincronizar_nfe(pedido) -> int:
    erp = _erp()
    if erp is None:
        return 0
    situacao, numeros = situacao_nfe(pedido)
    return (erp[0].objects.filter(tenant_id=pedido.tenant_id, pedido_compra_ref=pedido.pk)
            .exclude(status=CANCELADO).update(nfe_situacao=situacao, nfe_numero=numeros))


def _anotar(pedido, evento, contas) -> None:
    erp = _erp()
    if erp is None or not contas:
        return
    Anotacao = erp[1]
    Anotacao.objects.bulk_create([
        Anotacao(
            tenant_id=pedido.tenant_id, conta_pagar=conta,
            tipo=_TIPO_DA_ANOTACAO.get(evento.tipo, "nota"), origem="scm",
            texto=f"Pedido de compra #{pedido.pk} — {evento.texto}",
            valor=evento.valor, autor=evento.autor,
        )
        for conta in contas
    ])


def registrar_evento(pedido, tipo, texto, *, valor=None, autor=None, vai_ao_erp: bool = False) -> EventoPedido:
    """Grava no histórico do pedido e, se mexe no que se paga, anota os títulos."""
    evento = EventoPedido.objects.create(
        tenant_id=pedido.tenant_id, pedido=pedido, tipo=tipo, texto=texto[:4000],
        valor=valor, vai_ao_erp=vai_ao_erp, autor=autor if getattr(autor, "pk", None) else None,
    )
    if vai_ao_erp:
        _anotar(pedido, evento, titulos(pedido))
    return evento


def _avisar_financeiro(pedido, *, titulo: str, mensagem: str, decidir: bool = True) -> None:
    """Regra do dono (11/10/2026): escrita cruzada tem aviso."""
    from nucleo.models import Notificacao
    from nucleo.notificacoes import avisar_quem_pode

    avisar_quem_pode(
        tenant_id=pedido.tenant_id, permissao="erp.conta_pagar.baixar",
        titulo=titulo, mensagem=mensagem, url="/app/erp/contas-a-pagar",
        nivel=Notificacao.Nivel.DECIDIR if decidir else Notificacao.Nivel.SABER,
    )


def gerar_titulos(pedido, *, autor=None) -> list[int]:
    """Cada parcela ainda sem título vira um `ContaPagar` — e herda a trilha.

    A trilha anterior (o que já foi anotado no pedido antes de haver título) é
    copiada para os títulos novos: o financeiro não recebe a conta sem saber que
    o pedido já foi editado ou que chegou faltando.
    """
    erp = _erp()
    if erp is None:
        return []
    ContaPagar = erp[0]
    parcelas = list(
        ParcelaPedido.objects.filter(tenant_id=pedido.tenant_id, meio__pedido=pedido, conta_pagar_ref__isnull=True)
        .select_related("meio").order_by("meio__ordem", "numero")
    )
    if not parcelas:
        return []
    centro = pedido.centro_custo
    obra = getattr(centro, "obra", None)
    empreendimento_id = (getattr(centro, "empreendimento_id", None)
                         or getattr(obra, "empreendimento_id", None))
    situacao, numeros = situacao_nfe(pedido)
    novos = []
    for parcela in parcelas:
        meio = parcela.meio
        descricao = (f"Pedido de compra #{pedido.pk} — {meio.get_tipo_display()} "
                     f"{parcela.numero}/{meio.parcelas}")
        if meio.descricao:
            descricao += f" · {meio.descricao}"
        conta = ContaPagar.objects.create(
            tenant_id=pedido.tenant_id, fornecedor_id=pedido.fornecedor_id,
            empreendimento_id=empreendimento_id, obra=obra, descricao=descricao,
            valor=parcela.valor, data_emissao=pedido.data_pedido, data_vencimento=parcela.vencimento,
            pedido_compra_ref=pedido.pk, nfe_numero=numeros, nfe_situacao=situacao,
        )
        parcela.conta_pagar_ref = conta.pk
        parcela.save(update_fields=["conta_pagar_ref"])
        novos.append(conta)

    for evento in pedido.eventos.filter(vai_ao_erp=True).order_by("criado_em", "evento_id"):
        _anotar(pedido, evento, novos)
    if pedido.conta_pagar_ref is None:
        pedido.conta_pagar_ref = novos[0].pk
        pedido.save(update_fields=["conta_pagar_ref"])
    total = sum((c.valor for c in novos), Decimal("0"))
    _avisar_financeiro(
        pedido,
        titulo=f"Pedido de compra #{pedido.pk} gerou {len(novos)} título(s) a pagar",
        mensagem=(f"{pedido.fornecedor.razao_social} · R$ {total} · "
                  f"{'aguardando NF-e' if situacao == 'aguardando_nota' else 'NF-e ' + numeros}."),
    )
    return [c.pk for c in novos]


def cancelar_titulos(pedido, *, motivo: str, autor=None) -> tuple[list[int], list[int]]:
    """Cancela os títulos sem pagamento. Devolve `(cancelados, com_pagamento)`."""
    erp = _erp()
    if erp is None:
        return [], []
    Anotacao = erp[1]
    cancelados, pagos = [], []
    for conta in titulos(pedido):
        if conta.valor_pago and conta.valor_pago > 0:
            pagos.append(conta.pk)
            Anotacao.objects.create(
                tenant_id=pedido.tenant_id, conta_pagar=conta, tipo="cancelamento", origem="scm",
                texto=(f"Pedido de compra #{pedido.pk} — {motivo} O título já tem pagamento e "
                       "não foi cancelado: confira o estorno com o fornecedor."),
                autor=autor if getattr(autor, "pk", None) else None,
            )
            continue
        conta.status = CANCELADO
        conta.save(update_fields=["status"])
        Anotacao.objects.create(
            tenant_id=pedido.tenant_id, conta_pagar=conta, tipo="cancelamento", origem="scm",
            texto=f"Pedido de compra #{pedido.pk} — {motivo}",
            autor=autor if getattr(autor, "pk", None) else None,
        )
        cancelados.append(conta.pk)
    if cancelados or pagos:
        _avisar_financeiro(
            pedido,
            titulo=f"Pedido de compra #{pedido.pk}: {len(cancelados)} título(s) cancelado(s)",
            mensagem=motivo + (f" {len(pagos)} já tinha(m) pagamento e ficou(aram)." if pagos else ""),
        )
    return cancelados, pagos


def avisar_divergencia(pedido, texto: str) -> None:
    """Divergência que pede ajuste do título (item a mais, saldo encerrado, nota)."""
    if not titulos(pedido):
        return
    # O texto entra no título do aviso: dois fatos diferentes não podem ser
    # engolidos pela regra "um aviso por fato ainda não lido".
    _avisar_financeiro(pedido, titulo=f"Pedido de compra #{pedido.pk}: {texto}"[:200], mensagem=texto)
