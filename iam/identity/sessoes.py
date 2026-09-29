"""As sessões (`sid`) — abrir, revogar e dizer se ainda valem (fase 4, §10.5).

A revogação vale em segundos em todo serviço porque é **publicada**: a linha da
`Sessao` ganha `revogada_em` e o `sid` vai para o Redis da revogação
(`funcoesautorizacao.chaves.sessao_revogada`), com a vida de um access token
mais a margem — depois disso, nenhum access daquela sessão existe mais, e a
chave se apaga sozinha. A tabela continua sendo a autoridade: o PEP que não
alcança o Redis pergunta à IAM (`SessaoInternaView`).
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from funcoesautorizacao import chaves

from .models import Sessao
from .revocation import _redis

logger = logging.getLogger(__name__)


def abrir(usuario) -> Sessao:
    return Sessao.objects.create(usuario=usuario)


def publicar_revogacao(sid) -> bool:
    try:
        _redis().set(chaves.sessao_revogada(str(sid)), 1, ex=settings.SESSION_REVOKE_TTL_SECONDS)
        return True
    except Exception:  # noqa: BLE001 - a tabela já diz; o PEP sem Redis pergunta à IAM
        logger.exception("sessao.revogacao_nao_publicada sid=%s", sid)
        return False


def revogar(sid, motivo: str) -> bool:
    """Revoga uma sessão. Devolve se ela estava ativa."""
    n = Sessao.objects.filter(sid=sid, revogada_em__isnull=True).update(
        revogada_em=timezone.now(), motivo=motivo[:40]
    )
    publicar_revogacao(sid)
    return bool(n)


def revogar_todas(usuario, motivo: str, *, exceto=None) -> int:
    """`usuario` pode ser só um objeto com `.id` — a desativação por sinal
    (`signals.py`) revoga a partir do id, sem a linha carregada."""
    ativas = Sessao.objects.filter(usuario_id=usuario.id, revogada_em__isnull=True)
    if exceto:
        ativas = ativas.exclude(sid=exceto)
    sids = list(ativas.values_list("sid", flat=True))
    ativas.update(revogada_em=timezone.now(), motivo=motivo[:40])
    for sid in sids:
        publicar_revogacao(sid)
    return len(sids)


def ativa(sid) -> bool:
    """A sessão existe, não foi revogada e a pessoa segue ativa."""
    if not sid:
        return False
    return Sessao.objects.filter(
        sid=sid, revogada_em__isnull=True, usuario__is_active=True
    ).exists()
