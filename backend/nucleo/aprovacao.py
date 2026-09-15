# backend/nucleo/aprovacao.py
"""O motor da escada de atesto — fundação de plataforma (PDCA.0).

Os modelos moram em `models.py` (como os da frota); a **política** mora aqui. O
que este arquivo decide, e que nenhuma tela pode redecidir:

1. **Quem executa não aprova.** Quem abriu o pedido não ateste nenhum degrau,
   salvo se o fluxo declarar `permite_autoatesto` — e essa é uma escolha que o
   cliente faz por escrito, para a obra pequena onde o mesmo engenheiro apura e
   assina. O padrão recusa.
2. **A permissão é a do degrau**, conferida contra a claim `permissions` do token
   (mesma leitura fail-closed do `RequirePermission`). Admin de tenant e
   superusuário passam, como em toda a casa.
3. **Reprovar encerra.** Não há "voltar um degrau": a escada morre reprovada e a
   correção nasce como objeto novo (a medição retificadora da §11.5). Reabrir
   apagaria o atesto que recusou, que é justamente o registro que importa.
4. **Uma escada por objeto**, garantida por constraint parcial no banco — não por
   confiança no chamador.
5. **O `nucleo` não sabe o que aprovou.** Terminada a escada, ele emite o sinal
   `aprovacao_concluida`; congelar a medição, gerar o título no ERP ou publicar o
   cronograma é do módulo dono do alvo. É o que mantém a máquina genérica sem que
   o `nucleo` importe módulo nenhum.

Corrida: `decidir()` trava a linha do pedido com `select_for_update()`. Aqui o
lock se paga (é a mesma classe do L5, a baixa de título): dois atestos
simultâneos no último degrau poderiam concluir a escada duas vezes e disparar o
efeito colateral — um título a pagar em duplicidade — duas vezes.
"""
from __future__ import annotations

import logging

import django.dispatch
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from payment.planos import PDCA_TETO_NIVEIS_APROVACAO

from .models import Atesto, FluxoAprovacao, NivelAprovacao, PedidoAprovacao

logger = logging.getLogger(__name__)

#: Emitido quando a escada termina — aprovada OU reprovada. `sender` é a classe
#: do alvo, para o módulo dono conectar sem filtro em Python.
#: Argumentos: `pedido`, `alvo` (a instância, ou `None` se já não existir),
#: `aprovado` (bool).
aprovacao_concluida = django.dispatch.Signal()


def _nome_de(usuario) -> str:
    if usuario is None:
        return ""
    nome = (getattr(usuario, "get_full_name", lambda: "")() or "").strip()
    return nome or getattr(usuario, "username", "") or ""


def pode_atestar(usuario, nivel: NivelAprovacao) -> bool:
    """Espelha o `RequirePermission`: admin de tenant e superusuário passam; os
    demais precisam do código exato na claim do token. Sem claim → nega (a
    fatia E da Fase 9 tirou o fallback por papel de toda a casa)."""
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return False
    if getattr(usuario, "is_tenant_admin", False) or getattr(usuario, "is_superuser", False):
        return True
    return nivel.permissao_exigida in (getattr(usuario, "iam_permissions", None) or [])


def validar_fluxo(fluxo: FluxoAprovacao) -> None:
    """Uma escada só serve se tiver degrau e se os degraus forem contíguos a
    partir de 1. Buraco na ordem (1, 2, 5) faria `_proximo_nivel` parar no 3 e o
    pedido morrer parado num degrau que não existe."""
    ordens = list(fluxo.niveis.order_by("ordem").values_list("ordem", flat=True))
    if not ordens:
        raise ValidationError("Um fluxo de aprovação precisa de pelo menos um nível.")
    if len(ordens) > PDCA_TETO_NIVEIS_APROVACAO:
        raise ValidationError(
            f"Um fluxo aceita no máximo {PDCA_TETO_NIVEIS_APROVACAO} níveis "
            f"(este tem {len(ordens)})."
        )
    if ordens != list(range(1, len(ordens) + 1)):
        raise ValidationError(
            f"Os níveis precisam ser numerados de 1 a {len(ordens)}, sem buracos "
            f"nem repetição (recebido: {ordens})."
        )


#: Faixa de manobra do `reordenar_niveis`. **Não é teto de plano** (§5.6 do
#: `planos.py`): é constante física do algoritmo — o intervalo onde os degraus
#: estacionam entre as duas passadas, escolhido por caber no `SmallInteger`
#: (32.767) e nunca colidir com uma ordem real.
_ESTACIONAMENTO = 30_000


@transaction.atomic
def reordenar_niveis(fluxo: FluxoAprovacao, ids: list[int]) -> FluxoAprovacao:
    """Reescreve a ordem dos degraus de uma escada, **tudo ou nada**.

    **Por que não é a tela que faz isso com dois `PATCH`.** A
    `UniqueConstraint(fluxo, ordem)` é imediata: trocar 1↔2 exige um valor
    temporário, e uma falha entre as duas escritas deixa a escada com numeração
    quebrada — `validar_fluxo` passa a recusá-la e o documento que dependia dela
    para de andar **sem que ninguém o tenha tocado**.

    **Duas passadas, estacionando alto e não em negativo.** `ordem` é
    `PositiveSmallIntegerField`: o negativo, que seria o espaço óbvio, viola o
    check do banco e derruba a transação no meio.

    A numeração 1..N é **derivada da posição** na lista, e não recebida — assim
    quem chama não tem como inventar um buraco na escada.
    """
    atuais = {n.pk: n for n in fluxo.niveis.all()}
    if sorted(ids) != sorted(atuais):
        raise ValidationError(
            "A lista precisa conter exatamente os degraus deste fluxo, cada um "
            "uma vez — reordenar não cria nem apaga degrau."
        )

    for posicao, nivel_id in enumerate(ids, start=1):
        NivelAprovacao.objects.filter(pk=nivel_id).update(
            ordem=_ESTACIONAMENTO + posicao,
        )
    for posicao, nivel_id in enumerate(ids, start=1):
        NivelAprovacao.objects.filter(pk=nivel_id).update(ordem=posicao)

    fluxo.refresh_from_db()
    return fluxo


def fluxo_para(alvo, *, tenant_id: int) -> FluxoAprovacao | None:
    """O fluxo padrão ativo daquele tipo de alvo, ou `None` se o tenant não
    configurou nenhum — e `None` é resposta legítima: módulo sem escada
    configurada aprova em um passo, do jeito que já aprovava."""
    ct = ContentType.objects.get_for_model(alvo)
    return (
        FluxoAprovacao.objects.filter(
            tenant_id=tenant_id, alvo=ct, ativo=True, padrao=True
        ).first()
    )


def pedido_de(alvo) -> PedidoAprovacao | None:
    """A escada aberta sobre este objeto, se houver."""
    ct = ContentType.objects.get_for_model(alvo)
    return PedidoAprovacao.objects.filter(
        tenant_id=getattr(alvo, "tenant_id", None),
        alvo_tipo=ct,
        alvo_id=alvo.pk,
        estado=PedidoAprovacao.Estado.EM_APROVACAO,
    ).first()


@transaction.atomic
def abrir(*, alvo, solicitante, fluxo: FluxoAprovacao | None = None,
          resumo: str = "", valor: object = None) -> PedidoAprovacao:
    """Põe um objeto na escada e devolve o pedido parado no 1º degrau.

    `alvo` é qualquer instância de `TenantScopedModel`; o tenant do pedido é o
    **do alvo**, nunca o do solicitante — assim um usuário de plataforma que
    abrisse a escada em nome de uma empresa não criaria a linha no tenant errado.
    """
    tenant_id = getattr(alvo, "tenant_id", None)
    if not tenant_id:
        raise ValidationError("O alvo da aprovação precisa pertencer a um tenant.")

    fluxo = fluxo or fluxo_para(alvo, tenant_id=tenant_id)
    if fluxo is None:
        raise ValidationError(
            "Nenhum fluxo de aprovação padrão configurado para este tipo de documento."
        )
    if fluxo.tenant_id != tenant_id:
        raise ValidationError("O fluxo escolhido é de outra empresa.")
    if not fluxo.ativo:
        raise ValidationError(f"O fluxo '{fluxo.nome}' está inativo.")

    ct = ContentType.objects.get_for_model(alvo)
    if fluxo.alvo_id != ct.id:
        raise ValidationError(
            f"O fluxo '{fluxo.nome}' aprova {fluxo.alvo}, não {ct}."
        )
    validar_fluxo(fluxo)

    primeiro = fluxo.niveis.order_by("ordem").first()
    pedido = PedidoAprovacao.objects.create(
        tenant_id=tenant_id,
        fluxo=fluxo,
        alvo_tipo=ct,
        alvo_id=alvo.pk,
        nivel_atual=primeiro,
        solicitado_por=solicitante if getattr(solicitante, "pk", None) else None,
        solicitante_nome=_nome_de(solicitante),
        resumo=(resumo or str(alvo))[:240],
        valor_referencia=valor,
    )
    logger.info(
        "aprovacao.abrir pedido=%s alvo=%s#%s fluxo=%s niveis=%s",
        pedido.pk, ct, alvo.pk, fluxo.codigo, fluxo.niveis.count(),
    )
    return pedido


@transaction.atomic
def decidir(*, pedido: PedidoAprovacao, usuario, aprovar: bool,
            observacao: str = "") -> PedidoAprovacao:
    """Registra um atesto no degrau atual e move (ou encerra) a escada.

    Levanta `PermissionDenied` quando falta a permissão do degrau ou quando o
    solicitante tenta atestar o próprio pedido; `ValidationError` quando a escada
    já terminou. As duas são exceções que o DRF traduz sozinho — 403 e 400.
    """
    # Sem `select_related` aqui, e não é esquecimento: `nivel_atual` é nulável,
    # então o JOIN é externo, e o Postgres recusa `FOR UPDATE` sobre o lado
    # nulável de um outer join. O lock é o que importa nesta consulta — as duas
    # relações se resolvem em consultas próprias, dentro da mesma transação.
    pedido = PedidoAprovacao.objects.select_for_update().get(pk=pedido.pk)
    if pedido.estado != PedidoAprovacao.Estado.EM_APROVACAO:
        raise ValidationError(
            f"Este pedido já foi {pedido.get_estado_display().lower()} e não aceita atesto."
        )
    nivel = pedido.nivel_atual
    if nivel is None:
        raise ValidationError(
            "O pedido está em aprovação sem degrau atual — o fluxo foi alterado "
            "embaixo dele. Cancele e reabra."
        )

    # Segregação (§8): quem executa não aprova.
    if (
        not pedido.fluxo.permite_autoatesto
        and pedido.solicitado_por_id
        and pedido.solicitado_por_id == getattr(usuario, "pk", None)
    ):
        # **A recusa diz a saída, e a saída é uma decisão escrita.** A regra
        # existe para proteger a empresa, não para tutelar o usuário — e na obra
        # pequena o mesmo engenheiro apura e assina. Sem esta frase, quem esbarra
        # (inclusive o administrador do tenant, que é quem pode resolver) fica
        # com um documento parado e nenhum caminho: a válvula existe desde a
        # PDCA.0 e ninguém tinha como descobri-la.
        raise PermissionDenied(
            "Quem solicitou não pode atestar o próprio pedido — é a segregação "
            "que protege a empresa: quem executa não aprova. Três saídas: peça a "
            f"outra pessoa com '{nivel.permissao_exigida}' que ateste; cancele o "
            "pedido e reabra em nome de quem vai assinar; ou, se na sua operação "
            "a mesma pessoa apura e assina mesmo, o administrador liga "
            f"'Permitir autoatesto' no fluxo '{pedido.fluxo.nome}' "
            "(Administração → Aprovações)."
        )
    if not pode_atestar(usuario, nivel):
        raise PermissionDenied(
            f"O degrau '{nivel.nome}' exige a permissão '{nivel.permissao_exigida}'."
        )

    Atesto.objects.create(
        tenant_id=pedido.tenant_id,
        pedido=pedido,
        nivel=nivel,
        nivel_ordem=nivel.ordem,
        nivel_nome=nivel.nome,
        decisao=Atesto.Decisao.APROVADO if aprovar else Atesto.Decisao.REPROVADO,
        autor=usuario if getattr(usuario, "pk", None) else None,
        autor_nome=_nome_de(usuario),
        permissao_conferida=nivel.permissao_exigida,
        observacao=observacao or "",
    )

    if not aprovar:
        pedido.estado = PedidoAprovacao.Estado.REPROVADO
        pedido.nivel_atual = None
        pedido.concluido_em = timezone.now()
        pedido.save(update_fields=["estado", "nivel_atual", "concluido_em"])
        _anunciar(pedido, aprovado=False)
        return pedido

    proximo = (
        pedido.fluxo.niveis.filter(ordem__gt=nivel.ordem).order_by("ordem").first()
    )
    if proximo is not None:
        pedido.nivel_atual = proximo
        pedido.save(update_fields=["nivel_atual"])
        return pedido

    pedido.estado = PedidoAprovacao.Estado.APROVADO
    pedido.nivel_atual = None
    pedido.concluido_em = timezone.now()
    pedido.save(update_fields=["estado", "nivel_atual", "concluido_em"])
    _anunciar(pedido, aprovado=True)
    return pedido


@transaction.atomic
def cancelar(*, pedido: PedidoAprovacao, usuario, motivo: str = "") -> PedidoAprovacao:
    """Tira o objeto da escada sem decidir o mérito — o documento foi retirado,
    não recusado. Só o solicitante ou um administrador do tenant cancelam:
    permitir que qualquer aprovador cancelasse daria a cada degrau um jeito de
    fazer o pedido sumir sem deixar a recusa registrada."""
    pedido = PedidoAprovacao.objects.select_for_update().get(pk=pedido.pk)
    if pedido.estado != PedidoAprovacao.Estado.EM_APROVACAO:
        raise ValidationError("Só um pedido em aprovação pode ser cancelado.")
    dono = pedido.solicitado_por_id == getattr(usuario, "pk", None)
    if not dono and not (
        getattr(usuario, "is_tenant_admin", False) or getattr(usuario, "is_superuser", False)
    ):
        raise PermissionDenied(
            "Só quem solicitou (ou um administrador) pode cancelar o pedido."
        )
    pedido.estado = PedidoAprovacao.Estado.CANCELADO
    pedido.nivel_atual = None
    pedido.concluido_em = timezone.now()
    pedido.resumo = (pedido.resumo + (f" · cancelado: {motivo}" if motivo else ""))[:240]
    pedido.save(update_fields=["estado", "nivel_atual", "concluido_em", "resumo"])
    return pedido


def _anunciar(pedido: PedidoAprovacao, *, aprovado: bool) -> None:
    """Avisa o módulo dono do alvo. Falha de um receptor **não** desfaz o atesto:
    a decisão de quem tem alçada está registrada e é verdade independente de o
    efeito colateral ter dado certo — e o contrário deixaria um erro no ERP
    apagando a assinatura do fiscal. O erro vai para o log com o pedido junto."""
    modelo = pedido.alvo_tipo.model_class()
    alvo = None
    if modelo is not None:
        alvo = modelo.objects.filter(pk=pedido.alvo_id).first()
    try:
        aprovacao_concluida.send(
            sender=modelo, pedido=pedido, alvo=alvo, aprovado=aprovado,
        )
    except Exception:  # noqa: BLE001 - o efeito colateral não derruba o atesto
        logger.exception(
            "aprovacao.efeito_colateral_falhou pedido=%s alvo=%s#%s aprovado=%s",
            pedido.pk, pedido.alvo_tipo, pedido.alvo_id, aprovado,
        )


def pendentes_para(usuario, *, tenant_id: int | None = None):
    """A fila de decisão de uma pessoa: os pedidos parados num degrau que ela
    tem permissão de atestar. É a consulta que a tela de "requer sua decisão"
    faz, e ela filtra pelo mesmo critério que o `decidir` aplica — senão a fila
    ofereceria botão que vai dar 403."""
    tenant_id = tenant_id if tenant_id is not None else getattr(usuario, "tenant_id", None)
    qs = (
        PedidoAprovacao.objects.filter(
            tenant_id=tenant_id, estado=PedidoAprovacao.Estado.EM_APROVACAO
        )
        .select_related("fluxo", "nivel_atual", "alvo_tipo")
    )
    manda_em_tudo = getattr(usuario, "is_tenant_admin", False) or getattr(
        usuario, "is_superuser", False
    )
    if not manda_em_tudo:
        perms = list(getattr(usuario, "iam_permissions", None) or [])
        qs = qs.filter(nivel_atual__permissao_exigida__in=perms)
        # Quem executa não aprova — a fila não mostra o que a pessoa não pode
        # decidir. Fluxo com autoatesto ligado é a exceção, e ela vale aqui
        # também, senão a fila esconderia trabalho que a pessoa pode fazer.
        qs = qs.filter(
            Q(fluxo__permite_autoatesto=True) | ~Q(solicitado_por_id=getattr(usuario, "pk", None))
        )
    return qs.order_by("solicitado_em")
