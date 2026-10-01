"""Notas fiscais de serviço em lote (pedido do dono, 01/10/2026).

"Queria que tivesse como emitir a nota geral quando emitir os boletos em
bloco — não só da cobrança." O carnê do mês sai num clique (item 52); a nota de
cada parcela era um clique por conta. Aqui a mesma escolha da grade (as linhas
marcadas, ou todas do filtro menos as desmarcadas) vira uma prévia — quantas
notas saem, quantas contas já têm nota, de quem falta cadastro — e a emissão.

O endpoint `emitir-lote-nfse` existia desde a fase 11, mas nenhuma tela o
chamava, e ele só aceitava ids soltos, sem prévia e sem teto.

A nota de cada conta segue o caminho da emissão avulsa
(`views._emitir_nf_para_conta_receber`): tomador conferido antes de a nota
nascer, task na NFE.io e o acompanhamento até sair de "Processando".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .models import StatusConta

# O ritmo da NFE.io: espaça as tasks do lote para não chegar como rajada. É o
# protocolo do terceiro (§5.6 do planos.py), o mesmo do lote do Asaas.
INTERVALO_ENTRE_EMISSOES_S = 0.25


@dataclass
class TriagemNotas:
    emitir: list = field(default_factory=list)
    com_nota: list = field(default_factory=list)
    canceladas: list = field(default_factory=list)
    sem_cadastro: list = field(default_factory=list)   # (conta, faltando)
    valor_total: Decimal = Decimal('0')

    def resumo(self) -> dict:
        vistos, incompletos = set(), []
        for conta, faltando in self.sem_cadastro:
            if conta.cliente_id in vistos:
                continue
            vistos.add(conta.cliente_id)
            incompletos.append({
                'cliente_id': conta.cliente_id, 'cliente_nome': conta.cliente.nome_completo, 'falta': faltando,
            })
        return {
            'emitir': len(self.emitir),
            'com_nota': len(self.com_nota),
            'canceladas': len(self.canceladas),
            'sem_cadastro': len(self.sem_cadastro),
            'cadastro_incompleto': incompletos[:50],
            'cadastro_incompleto_total': len(incompletos),
            'valor_total': str(self.valor_total),
        }


def triar(contas) -> TriagemNotas:
    """Quem ganha nota agora, quem já tem, e de quem falta cadastro."""
    from .views import _conferir_tomador, _nf_substituivel

    t = TriagemNotas()
    faltando_por_cliente: dict[int, list[str]] = {}
    for conta in contas:
        if conta.status == StatusConta.CANCELADO:
            t.canceladas.append(conta)
            continue
        if not _nf_substituivel(conta.nota_fiscal_servico):
            t.com_nota.append(conta)
            continue
        if conta.cliente_id not in faltando_por_cliente:
            faltando_por_cliente[conta.cliente_id] = _conferir_tomador(conta.cliente)
        faltando = faltando_por_cliente[conta.cliente_id]
        if faltando:
            t.sem_cadastro.append((conta, faltando))
            continue
        t.emitir.append(conta)
        t.valor_total += conta.valor
    return t


def emitir(triagem: TriagemNotas, *, usuario, city_service_code: str = '010701') -> dict:
    """Cria as notas e enfileira a emissão, espaçada. Cada conta tem o seu desfecho."""
    from types import SimpleNamespace

    from .views import _emitir_nf_para_conta_receber

    enviadas, recusadas = 0, []
    for i, conta in enumerate(triagem.emitir):
        pedido = SimpleNamespace(data={'city_service_code': city_service_code}, user=usuario)
        resposta = _emitir_nf_para_conta_receber(
            pedido, conta, 'servico', countdown=i * INTERVALO_ENTRE_EMISSOES_S,
        )
        if resposta.status_code in (201, 202):
            enviadas += 1
        else:
            recusadas.append(_falha(conta, resposta.data.get('detail') or resposta.data.get('error') or ''))
    for conta, faltando in triagem.sem_cadastro:
        recusadas.append(_falha(
            conta, f"Falta no cadastro de {conta.cliente.nome_completo}: {', '.join(faltando)}.",
        ))

    from nucleo.auditoria import registrar_auditoria
    if triagem.emitir:
        registrar_auditoria(
            acao="emitir_lote_nfse", instance=triagem.emitir[0], usuario=usuario,
            detalhes={"notas": enviadas, "valor_total": str(triagem.valor_total)},
        )
    return {
        'enviadas': enviadas,
        'com_nota': len(triagem.com_nota),
        'recusadas': recusadas[:100],
        'recusadas_total': len(recusadas),
    }


def _falha(conta, frase: str) -> dict:
    return {
        'conta_receber_id': conta.conta_receber_id,
        'cliente_id': conta.cliente_id,
        'cliente_nome': conta.cliente.nome_completo,
        'descricao': conta.descricao,
        'mensagem': frase or 'Não foi possível emitir a nota desta conta.',
    }
