"""Editar um título já baixado — e o estorno que abre o que a baixa fechou.

**O defeito (item 57 do dono).** Em Contas a pagar, abrir uma conta com baixa e
clicar em "Editar" não fazia nada visível: a API recusava a mudança de valor e
o formulário engolia a resposta. E não havia caminho nenhum para corrigir uma
baixa lançada errado.

**Como os ERPs conhecidos resolvem, e o que este módulo copia (pesquisa de
30/09/2026):**

- **Omie** — depois do pagamento, só os detalhes (observação, número do
  documento) continuam editáveis; para mudar o financeiro, "Cancelar
  pagamento"; conta com pagamento não se exclui.
- **TOTVS Protheus** (FINA080) — o "cancelamento de baixa" não apaga a baixa:
  gera um **registro de estorno** na movimentação bancária, para o extrato
  mostrar o histórico, e o título volta ao fluxo de caixa.
- **Conta Azul** — "Voltar para em aberto" e só então editar.

Daí as três regras:

1. Com baixa, o que é **descrição** do título segue editável (descrição,
   empreendimento, datas de emissão/agendamento, rateio, nota); o que é
   **dinheiro ou contraparte** (valor, vencimento, fornecedor/cliente) trava, e
   a trava diz por quê e qual é a saída.
2. A saída é **estornar a baixa**: verbo próprio (`erp.conta_*.estornar`),
   motivo obrigatório, trilha de auditoria.
3. O estorno **acrescenta** ao ledger — uma `Transacao` de valor negativo que
   anula as baixas — e nunca apaga a original (o ledger é somente-leitura, D204).
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import Boleto, ContaPagar, ContaReceber, StatusConta, Transacao

CAMPOS_FINANCEIROS = {
    # A entidade é dinheiro também: a baixa saiu do caixa dela (entidades.md §2).
    ContaPagar: ('fornecedor', 'valor', 'data_vencimento', 'entidade'),
    ContaReceber: ('cliente', 'valor', 'data_vencimento', 'entidade'),
}
ROTULOS = {
    'fornecedor': 'fornecedor', 'cliente': 'cliente', 'valor': 'valor', 'data_vencimento': 'vencimento',
    'entidade': 'entidade',
}


class EstornoRecusado(Exception):
    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


def _reais(valor: Decimal) -> str:
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def travas(conta) -> tuple[list[str], str]:
    """`(campos travados, por quê)` — o que a tela desabilita e a API recusa."""
    if conta is None or conta.pk is None:
        return [], ""
    if conta.status == StatusConta.CANCELADO:
        return list(CAMPOS_FINANCEIROS[type(conta)]), "Conta cancelada: o financeiro dela não muda mais."
    if conta.natureza:
        return (
            list(CAMPOS_FINANCEIROS[type(conta)]),
            "Título intercompany: valor e vencimento acompanham o título de origem — mude a origem.",
        )
    if conta.valor_pago > 0:
        return (
            list(CAMPOS_FINANCEIROS[type(conta)]),
            f"Esta conta já tem baixa de {_reais(conta.valor_pago)}. Para mudar valor, vencimento ou "
            f"{'fornecedor' if isinstance(conta, ContaPagar) else 'cliente'}, estorne a baixa primeiro.",
        )
    # Sem baixa, quem trava é o boleto vivo (revisão do item 57, 01/10/2026).
    from .boleto_da_conta import travas_do_boleto
    return travas_do_boleto(conta)


def recusa_de_edicao(conta, novos: dict) -> dict:
    """Os campos travados que o pedido tenta mudar, com a frase para cada um."""
    travados, motivo = travas(conta)
    erros = {}
    for campo in travados:
        if campo not in novos:
            continue
        atual = getattr(conta, f"{campo}_id") if campo in ('fornecedor', 'cliente', 'entidade') else getattr(conta, campo)
        novo = novos[campo]
        novo = getattr(novo, 'pk', novo)
        if novo != atual:
            erros[campo] = motivo
    return erros


def motivo_para_nao_estornar(conta) -> str:
    if conta.valor_pago <= 0:
        return "Esta conta não tem baixa para estornar."
    if conta.status == StatusConta.CANCELADO:
        return "Conta cancelada não tem baixa a estornar."
    if isinstance(conta, ContaReceber) and conta.boletos.filter(status=Boleto.StatusBoleto.PAGO).exists():
        return (
            "O pagamento desta conta chegou pelo banco (boleto pago). Estornar aqui não devolve o "
            "dinheiro ao cliente: faça a devolução pelo banco e registre a correção na revisão de baixas."
        )
    return ""


def estornar_baixas(conta, *, usuario, motivo: str):
    """Anula todas as baixas da conta e a devolve para "Aberto"."""
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise EstornoRecusado("Diga o motivo do estorno — ele fica no histórico da conta.")
    with transaction.atomic():
        type(conta).objects.select_for_update().get(pk=conta.pk)
        conta.refresh_from_db()
        impedimento = motivo_para_nao_estornar(conta)
        if impedimento:
            raise EstornoRecusado(impedimento)

        liquido = conta.transacoes.aggregate(t=Sum('valor'))['t'] or Decimal('0')
        valor_pago = conta.valor_pago
        eh_pagar = isinstance(conta, ContaPagar)
        Transacao.objects.create(
            tenant=conta.tenant,
            conta_pagar=conta if eh_pagar else None,
            conta_receber=None if eh_pagar else conta,
            empreendimento=conta.empreendimento,
            descricao=f"Estorno de baixa — {motivo[:200]}",
            valor=-liquido,
            tipo=Transacao.TipoTransacao.SAIDA if eh_pagar else Transacao.TipoTransacao.ENTRADA,
            meio_pagamento='Estorno',
            usuario=usuario,
            data_transacao=timezone.now(),
        )
        conta.valor_pago = Decimal('0')
        conta.juros = conta.multa = conta.desconto = Decimal('0')
        conta.status = StatusConta.ABERTO
        if eh_pagar:
            conta.data_pagamento = None
        else:
            conta.data_recebimento = None
        conta.save()

        from nucleo.auditoria import registrar_auditoria
        registrar_auditoria(
            acao="estornar_baixa", instance=conta, usuario=usuario,
            detalhes={"valor_estornado": str(valor_pago), "motivo": motivo[:500]},
        )
        # Intercompany: o espelho na outra entidade volta junto — foi um dinheiro só.
        if conta.natureza and not getattr(conta, '_estorno_do_espelho', False):
            from .intercompany import espelho_de
            espelho = espelho_de(conta)
            if espelho is not None and espelho.valor_pago > 0:
                espelho._estorno_do_espelho = True
                estornar_baixas(espelho, usuario=usuario, motivo=f"Espelho do estorno na outra entidade — {motivo}")
    return conta
