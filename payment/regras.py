"""Regras que INTERPRETAM os valores de `planos.py` — a engenharia do modelo.

Fica em `payment/` para que **tudo que trata de plano/pagamento more numa pasta
só** (pedido do dono do software, para facilitar a manutenção), mas a fronteira
dentro da pasta é clara e vale ler antes de editar:

- **`planos.py` / `addons.py`** — os NÚMEROS (preços, quotas, o que trava). Muda
  com decisão COMERCIAL, sem revisão de código. É o que o dono edita à vontade.
- **este arquivo** — como esses números são LIDOS (precedência do contrato sobre
  o plano, como o teto deriva dos seats, o que vale sem assinatura). Muda com
  decisão de ENGENHARIA. Mexer aqui sem entender o efeito pode liberar o que o
  plano não vende — não edite para "ajustar um preço"; para isso é `planos.py`.

Por que aqui e não dentro de um serviço: estas funções são Python puro (sem
Django) e são consumidas pelos **dois** serviços — a IAM, ao montar as claims do
JWT, e o backend, ao servir o medidor de `/api/plano/` e o CTA de upgrade. Um
pacote na raiz sem dependência de framework é o que permite os dois importarem
sem duplicar a regra nem abrir um hop de rede. Foi também o que eliminou a
duplicação do `proximo_plano`, que antes o backend precisava reescrever por não
alcançar o código da IAM.

Precedência das quotas, do mais forte para o mais fraco (fail-closed no fim):

1. **`AssinaturaTenant.limites`** — o que foi *contratado de fato*, gravado no
   provisionamento. É o que permite o "Sob Medida" existir sem plano em código.
2. **o plano** (`Tenant.plano` → `PLANOS`).
3. **o plano padrão** (`free`) — todo tenant sem assinatura cai aqui, nunca sem
   limite. Mesmo princípio fail-closed do `RequirePermission`.
"""
from __future__ import annotations

from payment.planos import (
    ORDEM_PLANOS,
    PLANO_PADRAO,
    PLANOS,
    QUOTAS_APLICADAS,
    RATE_BASE_HORA,
    RATE_POR_SEAT_HORA,
    RATE_TETO_INFRA_HORA,
)

# Chaves de wire-protocol (JWT / `AssinaturaTenant.limites`). São contrato entre
# os serviços, não número comercial — por isso vivem com as regras, não com os
# valores.
CLAIM_REQUISICOES_HORA = "rate_hora"
CLAIM_QUOTAS = "quotas"
LIMITE_REQUISICOES_HORA = "requisicoes_hora"


def plano_valido(slug: str | None) -> str:
    """Slug conhecido, ou o plano padrão. Nunca levanta: um plano escrito errado
    no banco não pode derrubar a emissão de token — degrada para o menor."""
    return slug if slug in PLANOS else PLANO_PADRAO


def quotas_do_plano(slug: str | None) -> dict:
    """Todas as quotas do plano, como estão declaradas em `planos.py` — inclusive
    as inertes. Serve à vitrine (tabela de preços, comparativo de planos), não ao
    enforcement: para esse, use `quotas_efetivas`, que aplica a precedência do
    contratado e devolve só o que é realmente aplicado."""
    return dict(PLANOS[plano_valido(slug)])


def quota_efetiva(
    nome: str, slug: str | None, limites_contratados: dict | None = None
) -> int | None:
    """Valor de UMA quota com a precedência já resolvida:
    `AssinaturaTenant.limites` → plano → `free`.

    `None` significa **ilimitado** (o "Sob Medida" negociado sem teto naquele
    eixo) e é diferente de `0`, que é uma quota real de valor zero — o `free` usa
    `0` para dizer "este recurso não vem no plano". Confundir os dois liberaria
    justamente o que o plano de entrada não vende, então quem consome este valor
    tem de distinguir os dois casos explicitamente.
    """
    contratados = limites_contratados or {}
    if nome in contratados:
        valor = contratados[nome]
        # Contrato com lixo (string, negativo) não pode virar quota: cai no plano.
        if valor is None or (isinstance(valor, int) and valor >= 0):
            return valor
    return PLANOS[plano_valido(slug)].get(nome)


def quotas_efetivas(slug: str | None, limites_contratados: dict | None = None) -> dict:
    """As quotas **aplicadas**, prontas para virar claim do JWT.

    Só entram as de `QUOTAS_APLICADAS` (a lista comercial de `planos.py` §4).
    Publicar quota inerte no token seria pior que não publicar: convida alguém a
    "aplicar" mais adiante um número cujo contador ainda não existe — e engorda um
    claim que viaja em toda requisição. Quando um medidor novo nascer, o nome
    entra em `QUOTAS_APLICADAS` **junto** com ele.
    """
    return {
        nome: quota_efetiva(nome, slug, limites_contratados)
        for nome in QUOTAS_APLICADAS
    }


def teto_requisicoes_hora(slug: str | None, limites_contratados: dict | None = None) -> int:
    """Teto de requisições/hora de UM tenant. É o número que vai no JWT.

    Fórmula: ``base + seats × por_seat``, limitada pelo teto de infraestrutura.

    A escolha de derivar de **seats contratados** (e não de usuários ativos) é do
    dono do produto e tem duas consequências que valem lembrar aqui: o cliente
    recebe o que comprou mesmo antes de cadastrar todo mundo (previsível, e é o
    que ele pagou), e **comprar o add-on de usuário extra aumenta o teto
    sozinho** — o limite acompanha a receita em vez de brigar com ela.

    `limites_contratados` (de `AssinaturaTenant.limites`) tem precedência: é onde
    o "Sob Medida" grava o que foi negociado.
    """
    contratados = limites_contratados or {}

    # 1. Teto negociado explicitamente no contrato.
    explicito = contratados.get(LIMITE_REQUISICOES_HORA)
    if isinstance(explicito, int) and explicito > 0:
        return min(explicito, RATE_TETO_INFRA_HORA)

    plano = PLANOS[plano_valido(slug)]

    # 2. Seats: os contratados vencem os do plano (add-on de usuário extra).
    seats = contratados.get("seats", plano.get("seats"))
    if not isinstance(seats, int) or seats < 0:
        # Plano sem seats definidos = "Sob Medida" sem contrato preenchido.
        # Ilimitado no papel não pode virar ilimitado no eixo de requisições:
        # um tenant sozinho consumiria a capacidade dos outros.
        return int(plano.get("requisicoes_hora_default", RATE_TETO_INFRA_HORA))

    return min(RATE_BASE_HORA + seats * RATE_POR_SEAT_HORA, RATE_TETO_INFRA_HORA)


def proximo_plano(slug: str | None) -> str | None:
    """Plano imediatamente acima, para o CTA de upgrade. `None` no topo."""
    atual = plano_valido(slug)
    indice = ORDEM_PLANOS.index(atual)
    return ORDEM_PLANOS[indice + 1] if indice + 1 < len(ORDEM_PLANOS) else None
