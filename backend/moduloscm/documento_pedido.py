# backend/moduloscm/documento_pedido.py
"""O pedido que vai ao vendedor: o PDF e o envio (D284).

*Dono, 11/10/2026:* "quando cria um pedido ele deve poder ser exportado para
emissão ao vendedor" — PDF, e mandar por WhatsApp ou e-mail.

- **PDF**: pela única porta de PDF do sistema (`funcoesimpexp.formatos.escrita.
  html_para_pdf`, buscador sem rede), com a empresa, o fornecedor, a entrega, as
  linhas, o total e a condição de pagamento — e o pedido para citar o número na
  NF-e, que é o que faz a nota casar com o pedido no recebimento.
- **E-mail**: daqui, com o PDF anexado, pelo SMTP da plataforma e dentro do
  mesmo limitador de envio do `funcoesemail`.
- **WhatsApp**: não há API de envio — o navegador compartilha o arquivo (ou abre
  a conversa com o texto). O backend só registra que o pedido saiu.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone

from . import financeiro
from .models import EventoPedido, PedidoCompra

logger = logging.getLogger(__name__)


class EnvioIndisponivel(RuntimeError):
    pass


def _brl(v) -> str:
    return "R$ " + f"{Decimal(v or 0):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _qtd(v) -> str:
    return f"{Decimal(v).normalize():f}".replace(".", ",")


def condicao_de_pagamento(pedido) -> list[str]:
    saida = []
    for m in pedido.meios_pagamento.prefetch_related("parcelas_geradas"):
        parcelas = list(m.parcelas_geradas.all())
        datas = ", ".join(p.vencimento.strftime("%d/%m/%Y") for p in parcelas[:6])
        if len(parcelas) > 6:
            datas += f" … (+{len(parcelas) - 6})"
        vezes = f" em {m.parcelas}x" if m.parcelas > 1 else ""
        extra = f" — {m.descricao}" if m.descricao else ""
        saida.append(f"{m.get_tipo_display()}{vezes}: {_brl(m.valor)} · vencimento{'s' if len(parcelas) > 1 else ''} {datas}{extra}")
    return saida


def _empresa(pedido) -> str:
    from nucleo.models import Tenant

    tenant = Tenant.objects.filter(pk=pedido.tenant_id).only("nome").first()
    return tenant.nome if tenant else ""


def pdf_do_pedido(pedido: PedidoCompra) -> bytes:
    from funcoesimpexp.formatos.escrita import html_para_pdf

    linhas = []
    for it in pedido.itens.select_related("produto").order_by("item_pedido_id"):
        linhas.append({
            "descricao": it.produto.descricao if it.produto_id else it.descricao,
            "codigo": it.produto.codigo_interno if it.produto_id else "",
            "quantidade": _qtd(it.quantidade),
            "unidade": (it.produto.unidade if it.produto_id else it.unidade) or "un",
            "preco": _brl(it.preco_unitario),
            "subtotal": _brl(it.quantidade * it.preco_unitario),
        })
    centro = pedido.centro_custo
    html = render_to_string("moduloscm/pedido_compra.html", {
        "pedido": pedido, "empresa": _empresa(pedido), "fornecedor": pedido.fornecedor,
        "centro": getattr(centro, "nome", ""), "obra": getattr(centro, "obra", None),
        "linhas": linhas, "total": _brl(pedido.valor_total), "pagamento": condicao_de_pagamento(pedido),
    })
    return html_para_pdf(html)


def nome_do_arquivo(pedido) -> str:
    rev = f"-rev{pedido.revisao}" if pedido.revisao else ""
    return f"pedido-de-compra-{pedido.pedido_id}{rev}.pdf"


def marcar_enviado(pedido, *, canal: str, para: str = "", autor=None) -> None:
    pedido.enviado_em = timezone.now()
    campos = ["enviado_em"]
    if pedido.status in (PedidoCompra.Status.RASCUNHO, PedidoCompra.Status.APROVADO):
        pedido.status = PedidoCompra.Status.ENVIADO
        campos.append("status")
    pedido.save(update_fields=campos)
    rotulo = {"email": "por e-mail", "whatsapp": "por WhatsApp", "impresso": "impresso / baixado"}.get(canal, canal)
    rev = f" (revisão {pedido.revisao})" if pedido.revisao else ""
    financeiro.registrar_evento(
        pedido, EventoPedido.Tipo.ENVIO, f"Pedido{rev} enviado ao fornecedor {rotulo}" + (f" para {para}" if para else "") + ".",
        autor=autor,
    )


def enviar_por_email(pedido, *, para: str, autor=None) -> None:
    """Manda o PDF anexado. Levanta `EnvioIndisponivel` com o motivo."""
    if not getattr(settings, "EMAIL_HOST", ""):
        raise EnvioIndisponivel("O envio de e-mail não está configurado nesta instalação. Baixe o PDF e envie pelo seu e-mail.")
    try:
        from nucleo.rate_limit import LimiteFornecedorExcedido, consumir
    except ImportError:  # pragma: no cover
        consumir = None
    if consumir is not None:
        try:
            consumir("email")
        except LimiteFornecedorExcedido as exc:
            raise EnvioIndisponivel(f"Envio de e-mail temporariamente limitado: {exc}") from exc

    empresa = _empresa(pedido)
    corpo = "\n".join([
        f"Prezados, {pedido.fornecedor.razao_social},",
        "",
        f"Segue o pedido de compra nº {pedido.pedido_id}"
        + (f" (revisão {pedido.revisao})" if pedido.revisao else "") + f" de {empresa}, no valor de {_brl(pedido.valor_total)}.",
        f"Entrega prevista: {pedido.data_entrega_prevista.strftime('%d/%m/%Y') if pedido.data_entrega_prevista else 'a combinar'}.",
        "",
        f"Por favor, cite \"Pedido de compra nº {pedido.pedido_id}\" na NF-e.",
        "",
        empresa,
    ])
    msg = EmailMessage(
        subject=f"Pedido de compra nº {pedido.pedido_id} — {empresa}",
        body=corpo, from_email=settings.DEFAULT_FROM_EMAIL, to=[para],
    )
    msg.attach(nome_do_arquivo(pedido), pdf_do_pedido(pedido), "application/pdf")
    try:
        msg.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001 - SMTP fora do ar vira mensagem, não 500
        logger.exception("Falha ao enviar o pedido %s por e-mail", pedido.pk)
        raise EnvioIndisponivel("O servidor de e-mail recusou o envio. Baixe o PDF e envie pelo seu e-mail.") from exc
    marcar_enviado(pedido, canal="email", para=para, autor=autor)
