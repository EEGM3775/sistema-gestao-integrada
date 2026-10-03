"""Boletos em lote (item 52 do dono).

Contas a receber não tinha como gerar boletos para várias contas de uma vez: o
carnê de um loteamento, mês a mês, era um clique por parcela. Aqui a pessoa
escolhe as linhas (ou "todas do filtro"), vê a prévia — quantos saem, quantos já
têm boleto válido, quantos estão vencidos e vão com multa e juros — e confirma.

Duas saídas, a mesma triagem:

- **Asaas** — uma task por conta, no ritmo do gateway; cada item do lote recebe
  o boleto ou a frase de por que não saiu.
- **Banco (CNAB)** — os boletos nascem aqui com nosso número e código de barras
  e saem juntos num arquivo de remessa (`cnab/`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from funcoescobrancas.segunda_via import encargos_ate
from payment.planos import ERP_SEGUNDA_VIA_PRAZO_DIAS

from .models import Boleto, ContaReceber, ItemLoteCobranca, LoteCobranca, StatusConta

# O ritmo do Asaas: espaça as tasks para o lote não chegar ao gateway como uma
# rajada. É o protocolo do terceiro (§5.6 do planos.py), não um limite nosso.
INTERVALO_ENTRE_EMISSOES_S = 0.25

ATIVOS = (Boleto.StatusBoleto.EMITIDO, Boleto.StatusBoleto.VENCIDO, Boleto.StatusBoleto.AGUARDANDO)


class LoteRecusado(Exception):
    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


@dataclass
class Triagem:
    emitir: list = field(default_factory=list)          # (conta, vencimento | None)
    segunda_via: list = field(default_factory=list)     # (conta, vencimento)
    com_boleto_valido: list = field(default_factory=list)
    encerradas: list = field(default_factory=list)
    valor_total: Decimal = Decimal('0')
    encargos_total: Decimal = Decimal('0')

    def cadastro_incompleto(self) -> list[dict]:
        """Quem o banco recusaria por falta de endereço — antes de emitir.

        O CNAB registra o boleto com o endereço completo do pagador, e o banco
        recusa o registro sem ele. Dizer isso depois de tentar, sem o caminho,
        foi o que fez o dono perguntar "por que não consigo emitir cnab".
        """
        from .cnab.titulo import pagador_do_cliente

        vistos, saida = set(), []
        for conta, _ in self.emitir + self.segunda_via:
            if conta.cliente_id in vistos:
                continue
            vistos.add(conta.cliente_id)
            _, falta = pagador_do_cliente(conta.cliente)
            if falta:
                saida.append({'cliente_id': conta.cliente_id, 'cliente_nome': conta.cliente.nome_completo, 'falta': falta})
        return saida

    def resumo(self) -> dict:
        incompletos = self.cadastro_incompleto()
        clientes_fora = {c['cliente_id'] for c in incompletos}
        return {
            'cadastro_incompleto': incompletos[:50],
            'cadastro_incompleto_total': len(incompletos),
            'boletos_sem_cadastro': sum(
                1 for conta, _ in self.emitir + self.segunda_via if conta.cliente_id in clientes_fora
            ),
            'emitir': len(self.emitir),
            'segunda_via': len(self.segunda_via),
            'com_boleto_valido': len(self.com_boleto_valido),
            'encerradas': len(self.encerradas),
            'total_boletos': len(self.emitir) + len(self.segunda_via),
            'valor_total': str(self.valor_total),
            'encargos_total': str(self.encargos_total),
            'vencimento_segunda_via': (
                (timezone.localdate() + timedelta(days=ERP_SEGUNDA_VIA_PRAZO_DIAS)).isoformat()
                if self.segunda_via else None
            ),
        }


def triar(contas, vencimento_segunda_via: date | None = None) -> Triagem:
    """Separa o que sai, o que sai como segunda via e o que fica de fora.

    Encargos da prévia contados até a data pedida, sem o ajuste de feriado de
    cada praça — o boleto final pode andar um dia útil, e a emissão refaz a
    conta exata por título (`segunda_via.planejar`).
    """
    hoje = timezone.localdate()
    nova_data = vencimento_segunda_via or hoje + timedelta(days=ERP_SEGUNDA_VIA_PRAZO_DIAS)
    t = Triagem()
    for conta in contas:
        if conta.status not in (StatusConta.ABERTO, StatusConta.PARCIAL):
            t.encerradas.append(conta)
            continue
        # Boleto que ainda vale: registrado no Asaas (tem id lá) ou no banco (CNAB).
        ativos = [
            b for b in conta.boletos.all()
            if b.status in ATIVOS and (b.gateway_id or b.canal == Boleto.Canal.CNAB)
        ]
        valido = any(b.data_vencimento >= hoje for b in ativos)
        if valido:
            t.com_boleto_valido.append(conta)
            continue
        saldo = conta.saldo_aberto
        if conta.data_vencimento < hoje:
            enc = encargos_ate(conta, nova_data)
            t.segunda_via.append((conta, nova_data))
            t.valor_total += saldo + enc.total
            t.encargos_total += enc.total
        else:
            t.emitir.append((conta, None))
            t.valor_total += saldo
    return t


def carregar(queryset, ids: list[int] | None, *, usuario):
    """As contas do lote, se couberem no limite de quem pede (§5.5u):
    o da empresa, dentro do plano, dentro da infraestrutura."""
    from .limites_lote import BOLETOS, recusa

    qs = queryset.select_related('cliente', 'empreendimento', 'cliente_empreendimento').prefetch_related('boletos')
    if ids is not None:
        qs = qs.filter(pk__in=ids)
    frase = recusa(usuario, BOLETOS, qs.count())
    if frase:
        raise LoteRecusado(frase)
    return list(qs)


def emitir_pelo_asaas(triagem: Triagem, *, usuario) -> LoteCobranca:
    from funcoescobrancas.tasks import criar_cobranca

    alvo = triagem.emitir + triagem.segunda_via
    if not alvo:
        raise LoteRecusado("Nenhuma das contas escolhidas precisa de boleto agora.")
    tenant = alvo[0][0].tenant
    with transaction.atomic():
        lote = LoteCobranca.objects.create(
            tenant=tenant, canal=Boleto.Canal.ASAAS, criado_por=usuario, total=len(alvo),
        )
        itens = [
            ItemLoteCobranca.objects.create(tenant=tenant, lote=lote, conta_receber=conta, vencimento=venc)
            for conta, venc in alvo
        ]
        for conta in triagem.com_boleto_valido:
            ItemLoteCobranca.objects.create(
                tenant=tenant, lote=lote, conta_receber=conta, situacao=ItemLoteCobranca.Situacao.IGNORADO,
                mensagem="Já tem boleto válido.",
            )

        def enfileirar():
            for i, item in enumerate(itens):
                criar_cobranca.apply_async(
                    args=[item.conta_receber_id],
                    kwargs={
                        'vencimento': item.vencimento.isoformat() if item.vencimento else None,
                        'item_lote_id': item.item_id,
                    },
                    countdown=i * INTERVALO_ENTRE_EMISSOES_S,
                )
        # Só depois do commit: a task procura o item, e antes disso ele não existe.
        transaction.on_commit(enfileirar)

    from nucleo.auditoria import registrar_auditoria
    registrar_auditoria(
        acao="gerar_cobrancas_lote", instance=lote, usuario=usuario,
        detalhes={"boletos": len(alvo), "valor_total": str(triagem.valor_total)},
    )
    return lote


def andamento(lote: LoteCobranca) -> dict:
    from django.db.models import Count

    contagem = dict(lote.itens.values_list('situacao').annotate(n=Count('pk')))
    falhas = [
        {
            'conta_receber_id': i.conta_receber_id,
            'cliente_nome': i.conta_receber.cliente.nome_completo,
            'descricao': i.conta_receber.descricao,
            'mensagem': i.mensagem,
        }
        for i in lote.itens.filter(situacao=ItemLoteCobranca.Situacao.ERRO)
        .select_related('conta_receber__cliente')[:100]
    ]
    return {
        'lote_id': lote.lote_id,
        'canal': lote.canal,
        'criado_em': lote.criado_em,
        'total': lote.total,
        'emitidos': contagem.get(ItemLoteCobranca.Situacao.EMITIDO, 0),
        'erros': contagem.get(ItemLoteCobranca.Situacao.ERRO, 0),
        'pendentes': contagem.get(ItemLoteCobranca.Situacao.PENDENTE, 0),
        'ignorados': contagem.get(ItemLoteCobranca.Situacao.IGNORADO, 0),
        'remessa_id': lote.remessa_id,
        'remessa_nome': lote.remessa.nome_arquivo if lote.remessa_id else None,
        'falhas': falhas,
    }
