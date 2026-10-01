"""Editar uma conta que já tem boleto — o boleto acompanha, ou a edição para.

**O defeito (item 57 do dono, revisão de 01/10/2026).** "Posso editar, mas não
faz sentido, já que o boleto continua igual." A parcela 46/48 de um contrato
vencia em 01/01/2030; o boleto saiu nessa data, alguém corrigiu a conta para
02/01, e o boleto seguiu vencendo no feriado — com o valor e a data antigos
impressos e registrados no Asaas. A conta dizia uma coisa, o boleto que o
cliente tem na mão dizia outra.

**Como os ERPs conhecidos tratam (pesquisa de 01/10/2026):**

- **Conta Azul / Omie com boleto por integradora** — alterar valor ou
  vencimento de parcela com boleto emitido cancela o boleto e emite outro (ou
  altera a cobrança na integradora); a tela avisa antes de salvar.
- **TOTVS / Omie com CNAB** — boleto registrado no banco só muda por
  **instrução de remessa** (alteração de vencimento, abatimento, baixa); o
  título fica travado até a instrução ir e o retorno confirmar.
- **Todos** — trocar o sacado de um boleto emitido não existe: cancela-se o
  boleto e emite-se outro para o novo pagador.

Daí as regras daqui:

1. **Asaas:** valor ou vencimento mudou e há boleto vivo → a edição precisa
   da confirmação explícita (`atualizar_boleto`), e ao salvar o boleto antigo é
   cancelado e o novo é emitido pela mesma via da segunda via
   (`funcoescobrancas.services.gerar_cobranca_asaas`), com feriado e encargos
   recalculados. Sem a confirmação, a API recusa com a frase do que vai
   acontecer — nenhum cliente de API muda um boleto sem querer.
2. **CNAB:** o SGI ainda não gera remessa de instrução (pendência D245);
   valor e vencimento travam com o caminho (baixa pelo banco).
3. **Cliente:** com boleto vivo, trava — o boleto está no nome de outra pessoa.
"""
from __future__ import annotations

from decimal import Decimal

from .models import Boleto, ContaReceber

ATIVOS = (Boleto.StatusBoleto.EMITIDO, Boleto.StatusBoleto.VENCIDO, Boleto.StatusBoleto.AGUARDANDO)


def boleto_vivo(conta):
    """O boleto que o cliente pode pagar agora: o do Asaas (tem id lá) ou o do banco."""
    if conta is None or conta.pk is None or not isinstance(conta, ContaReceber):
        return None
    # Ordenado em Python: `order_by` furaria o `prefetch_related` da grade e
    # viraria uma consulta por linha (a trava é lida em toda linha da lista).
    for boleto in sorted(conta.boletos.all(), key=lambda b: b.criado_em, reverse=True):
        if boleto.status in ATIVOS and (boleto.gateway_id or boleto.canal == Boleto.Canal.CNAB):
            return boleto
    return None


def _data_br(dia) -> str:
    return dia.strftime('%d/%m/%Y')


def _reais(valor: Decimal) -> str:
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def vencimento_contratual_do_boleto(boleto):
    """A data do contrato que o boleto carregava ao nascer (antes do ajuste de feriado)."""
    from datetime import date

    ajuste = (boleto.dados_retorno_api or {}).get('ajuste_de_vencimento') if isinstance(boleto.dados_retorno_api, dict) else None
    if ajuste and ajuste.get('contratual'):
        try:
            return date.fromisoformat(ajuste['contratual'])
        except ValueError:
            pass
    return boleto.data_vencimento


def desencontro(conta, boleto=None) -> str:
    """Por que o boleto vivo não é mais o desta conta — ou `""` se ele ainda é.

    É o aviso que a tela põe em cima do boleto antigo (o caso do dono: conta
    corrigida para 02/01, boleto vencendo em 01/01).
    """
    boleto = boleto or boleto_vivo(conta)
    if boleto is None:
        return ""
    principal = boleto.valor - (boleto.valor_multa or 0) - (boleto.valor_juros or 0)
    if principal != conta.saldo_aberto:
        return (
            f"Este boleto cobra {_reais(principal)} de principal, e o saldo da conta é "
            f"{_reais(conta.saldo_aberto)}. Emita o boleto atualizado — o atual será cancelado."
        )
    segunda_via = (boleto.valor_multa or 0) > 0 or (boleto.valor_juros or 0) > 0
    if not segunda_via and vencimento_contratual_do_boleto(boleto) != conta.data_vencimento:
        return (
            f"Este boleto foi emitido para o vencimento de {_data_br(vencimento_contratual_do_boleto(boleto))}, "
            f"e a conta vence em {_data_br(conta.data_vencimento)}. Emita o boleto atualizado — o atual será cancelado."
        )
    return ""


def _rotulo(boleto) -> str:
    return f"o boleto de {_data_br(boleto.data_vencimento)} ({_reais(boleto.valor)})"


def travas_do_boleto(conta) -> tuple[list[str], str]:
    """`(campos, por quê)` que o boleto vivo trava — lido pela tela e cobrado na escrita.

    Entra no mesmo `campos_travados`/`travado_porque` da baixa (`estorno.travas`):
    o formulário mostra o campo como texto com o cadeado, em vez de deixar
    digitar e recusar depois.
    """
    boleto = boleto_vivo(conta)
    if boleto is None:
        return [], ""
    if boleto.canal == Boleto.Canal.CNAB:
        return ['cliente', 'valor', 'data_vencimento'], (
            f"Esta conta tem {_rotulo(boleto)} registrado no banco. O SGI ainda não envia instrução de "
            "alteração ao banco: para mudar valor, vencimento ou cliente, peça a baixa do boleto pelo "
            "internet banking e, com o retorno processado, edite a conta."
        )
    return ['cliente'], (
        f"Esta conta tem {_rotulo(boleto)} em nome de {conta.cliente.nome_completo}. Para trocar o "
        "cliente, cancele o boleto primeiro — boleto não muda de pagador. Valor e vencimento podem "
        "mudar: o boleto é reemitido."
    )


def recusa_por_boleto(conta, novos: dict, *, confirmado: bool) -> dict:
    """Mudar valor ou vencimento com boleto vivo no Asaas exige a confirmação.

    O que o boleto **trava** (cliente; tudo, no CNAB) já foi recusado antes,
    por `travas_do_boleto`. Aqui fica só o "você sabe que o boleto vai ser
    cancelado e reemitido?".
    """
    boleto = boleto_vivo(conta)
    if boleto is None or boleto.canal != Boleto.Canal.ASAAS or confirmado:
        return {}
    mudou = [
        campo for campo in ('valor', 'data_vencimento')
        if campo in novos and novos[campo] != getattr(conta, campo)
    ]
    if not mudou:
        return {}
    frase = (
        f"Esta conta tem {_rotulo(boleto)} no Asaas. Ao mudar valor ou vencimento, ele é cancelado e um "
        "boleto novo é emitido com os dados corrigidos. Confirme para continuar."
    )
    return {'atualizar_boleto': frase}


def reemitir_se_preciso(conta, *, antes: dict) -> bool:
    """Depois de salvar: valor ou vencimento mudou com boleto Asaas vivo → segunda via.

    Vai pela task (o Asaas é lento e o cancelamento + emissão não cabem na
    requisição de salvar) e só depois do commit — a task relê a conta.
    """
    from django.db import transaction

    boleto = boleto_vivo(conta)
    if boleto is None or boleto.canal != Boleto.Canal.ASAAS:
        return False
    if antes.get('valor') == conta.valor and antes.get('data_vencimento') == conta.data_vencimento:
        return False
    from funcoescobrancas.tasks import criar_cobranca

    conta_id = conta.pk
    transaction.on_commit(lambda: criar_cobranca.delay(conta_id))
    return True
