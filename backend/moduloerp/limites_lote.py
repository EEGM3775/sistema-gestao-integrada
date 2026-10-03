"""Quantos boletos e notas um lote emite — o plano dá o teto, a empresa escolhe o dela.

**O pedido do dono (01/10/2026):** "algo para o admin ou dono do tenant
controlar dentro do limite paywall dele, e alguma permissão especial também".
Antes, o 500 era um número só, igual para todo plano e para toda empresa.

Três camadas, da mais forte para a mais fraca (`payment/planos.py` §5.5u):

1. **Infraestrutura** — `ERP_TETO_COBRANCAS_POR_LOTE` / `ERP_TETO_NOTAS_POR_LOTE`:
   o que o SGI aguenta num clique, até para o Sob Medida ilimitado.
2. **Plano** — a quota `boletos_por_lote` / `notas_por_lote`, que chega na
   claim `quotas` (o contrato do `AssinaturaTenant.limites` por cima do plano).
3. **Empresa** — `ConfiguracaoFinanceiro`: o administrador, ou quem tem
   `erp.lote.configurar`, põe um número menor. Vazio = o máximo do plano.

A recusa diz qual camada bateu e o caminho de cada uma: filtrar, pedir a quem
ajusta o limite da empresa, ou o plano seguinte.
"""
from __future__ import annotations

from dataclasses import dataclass

from payment.planos import ERP_TETO_COBRANCAS_POR_LOTE, ERP_TETO_NOTAS_POR_LOTE, PLANOS
from payment.regras import plano_valido, proximo_plano, quota_efetiva

PERMISSAO = 'erp.lote.configurar'


@dataclass(frozen=True)
class Recurso:
    chave: str          # o campo da configuração e o nome da quota
    teto_infra: int
    plural: str         # "boletos", "notas"


BOLETOS = Recurso('boletos_por_lote', ERP_TETO_COBRANCAS_POR_LOTE, 'boletos')
NOTAS = Recurso('notas_por_lote', ERP_TETO_NOTAS_POR_LOTE, 'notas')
RECURSOS = (BOLETOS, NOTAS)


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def teto_do_plano(user, recurso: Recurso) -> int:
    """O teto do plano (ou do contrato), nunca acima da infraestrutura.

    A claim `quotas` traz o valor resolvido pela IAM. Se ela não trouxer a chave
    (ficha da empresa publicada antes desta quota existir), vale o plano da
    claim `plano`; sem nenhum dos dois, a infraestrutura — o fail-open da casa
    para quota (`nucleo/quotas.py`), com o teto duro ainda valendo.
    """
    quotas = getattr(user, 'iam_quotas', None)
    if isinstance(quotas, dict) and recurso.chave in quotas:
        valor = quotas[recurso.chave]
    elif getattr(user, 'iam_plano', None):
        valor = quota_efetiva(recurso.chave, user.iam_plano)
    else:
        valor = None
    if not isinstance(valor, int) or valor < 0:
        return recurso.teto_infra  # None = ilimitado no contrato: sobra a infraestrutura
    return min(valor, recurso.teto_infra)


def configuracao(tenant_id):
    from .models import ConfiguracaoFinanceiro

    if not tenant_id:
        return None
    return ConfiguracaoFinanceiro.objects.filter(tenant_id=tenant_id).first()


def escolhido_pela_empresa(user, recurso: Recurso) -> int | None:
    config = configuracao(getattr(user, 'tenant_id', None))
    return getattr(config, recurso.chave, None) if config else None


def limite(user, recurso: Recurso) -> int:
    """O que vale agora para este usuário: o da empresa, dentro do plano."""
    plano = teto_do_plano(user, recurso)
    escolhido = escolhido_pela_empresa(user, recurso)
    return min(escolhido, plano) if escolhido else plano


def _nome_do_plano(slug: str | None) -> str:
    return PLANOS[plano_valido(slug)]['nome']


def recusa(user, recurso: Recurso, total: int) -> str | None:
    """A frase de por que `total` contas não cabem num lote — ou `None` se cabem."""
    plano = teto_do_plano(user, recurso)
    escolhido = escolhido_pela_empresa(user, recurso)
    vale = min(escolhido, plano) if escolhido else plano
    if total <= vale:
        return None
    inicio = f"São {_milhar(total)} contas — "
    if escolhido and escolhido < plano:
        return (
            f"{inicio}o limite da sua empresa é {_milhar(escolhido)} {recurso.plural} por lote "
            f"(o plano permite até {_milhar(plano)}). Filtre por mês ou empreendimento, ou peça "
            "a quem administra o financeiro para subir o limite em Configurações do financeiro."
        )
    if plano < recurso.teto_infra:
        slug = getattr(user, 'iam_plano', None)
        seguinte = proximo_plano(slug)
        oferta = ''
        if seguinte:
            teto_seguinte = quota_efetiva(recurso.chave, seguinte)
            teto_seguinte = recurso.teto_infra if teto_seguinte is None else min(teto_seguinte, recurso.teto_infra)
            oferta = f" No plano {_nome_do_plano(seguinte)}, até {_milhar(teto_seguinte)}."
        return (
            f"{inicio}o plano {_nome_do_plano(slug)} emite até {_milhar(plano)} {recurso.plural} por lote. "
            f"Filtre por mês ou empreendimento.{oferta}"
        )
    return (
        f"{inicio}o SGI emite até {_milhar(plano)} {recurso.plural} de uma vez. "
        "Filtre por mês ou empreendimento."
    )


def resumo(user) -> dict:
    """O que a tela de configuração mostra: o valor, o teto do plano e quem pode mudar."""
    from nucleo import autorizacao

    config = configuracao(getattr(user, 'tenant_id', None))
    slug = getattr(user, 'iam_plano', None)
    saida = {
        'plano': _nome_do_plano(slug) if slug else '',
        'pode_editar': autorizacao.pode(user, PERMISSAO),
        'atualizado_em': config.atualizado_em if config else None,
        'atualizado_por': (
            (config.atualizado_por.get_full_name() or config.atualizado_por.username)
            if config and config.atualizado_por_id else ''
        ),
    }
    for recurso in RECURSOS:
        plano = teto_do_plano(user, recurso)
        escolhido = getattr(config, recurso.chave, None) if config else None
        saida[recurso.chave] = {
            'valor': min(escolhido, plano) if escolhido else plano,
            'escolhido': escolhido,
            'teto_plano': plano,
            'teto_infra': recurso.teto_infra,
        }
    return saida
