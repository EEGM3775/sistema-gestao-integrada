"""As sessões (`sid`) — abrir, revogar e dizer se ainda valem (fase 4, §10.5).

A revogação vale em segundos em todo serviço porque é **publicada**: a linha da
`Sessao` ganha `revogada_em` e o `sid` vai para o Redis da revogação
(`funcoesautorizacao.chaves.sessao_revogada`), com a vida de um access token
mais a margem — depois disso, nenhum access daquela sessão existe mais, e a
chave se apaga sozinha. A tabela continua sendo a autoridade: o PEP que não
alcança o Redis pergunta à IAM (`SessaoInternaView`).

**Fase 5 (BFF).** A sessão ganha uma credencial — o valor do cookie HttpOnly que
o navegador guarda no lugar do token. Ela nasce aqui, sai daqui uma vez (no
login, para o cookie) e fica na linha só como hash: um dump da tabela não abre
sessão de ninguém. O gateway a troca por access (`identity.bff`), e revogar a
sessão apaga também os access que o BFF guardou para ela.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone as tz

from django.conf import settings
from django.utils import timezone

from funcoesautorizacao import audiencias, chaves

from .models import Sessao
from .revocation import _redis, redis_caiu

logger = logging.getLogger(__name__)

#: Bytes aleatórios da credencial do cookie (256 bits, como a chave de sessão
#: de qualquer framework sério). É largura de segredo, não limite de produto.
_BYTES_DA_CREDENCIAL = 32


def hash_da_credencial(credencial: str) -> str:
    return hashlib.sha256(credencial.encode("utf-8")).hexdigest()


def _nova_credencial(sessao: Sessao) -> str:
    credencial = secrets.token_urlsafe(_BYTES_DA_CREDENCIAL)
    sessao.credencial_hash = hash_da_credencial(credencial)
    sessao.credencial = credencial  # só em memória: é o valor que vai para o cookie
    return credencial


def abrir(usuario, *, lembrar: bool = False, amr: list[str] | None = None) -> Sessao:
    """Abre a sessão do login. A credencial em claro fica em `sessao.credencial`
    (fora do banco) para quem vai gravar o cookie."""
    sessao = Sessao(
        usuario=usuario, lembrar=bool(lembrar), amr=list(amr or ["pwd"]), auth_time=timezone.now(),
    )
    _nova_credencial(sessao)
    sessao.save()
    return sessao


def trocar_credencial(sessao: Sessao) -> str:
    """Credencial nova para uma sessão que continua (a renovação que chegou sem o
    cookie do BFF, ou a sessão aberta antes da fase 5). A antiga deixa de abrir
    a sessão, e os access guardados com ela saem."""
    antiga = sessao.credencial_hash
    credencial = _nova_credencial(sessao)
    sessao.save(update_fields=["credencial_hash"])
    esquecer_tokens(antiga)
    return credencial


def prolongar(sid, exp_epoch: int) -> None:
    """A sessão vale até onde vale o refresh — que desliza a cada renovação com
    interação e para no teto absoluto (`tokens._aplicar_validade`)."""
    Sessao.objects.filter(sid=sid).update(
        expira_em=datetime.fromtimestamp(int(exp_epoch), tz=tz.utc)
    )


def pela_credencial(credencial: str | None) -> Sessao | None:
    """A sessão do cookie, se ela ainda vale: existe, não foi revogada, não
    expirou e a pessoa segue ativa. Qualquer outra coisa é `None` — o gateway
    segue sem token, e o serviço responde 401."""
    if not credencial:
        return None
    sessao = (
        Sessao.objects.select_related("usuario", "usuario__tenant")
        .filter(credencial_hash=hash_da_credencial(credencial), revogada_em__isnull=True)
        .first()
    )
    if sessao is None or not sessao.usuario.is_active:
        return None
    if sessao.expira_em is None or sessao.expira_em <= timezone.now():
        return None
    return sessao


def esquecer_tokens(credencial_hash: str | None) -> None:
    """Apaga os access que o BFF guardou para a sessão. Redis fora não impede
    nada: a sessão revogada já cai no PEP pelo `sid`."""
    if not credencial_hash:
        return
    try:
        _redis().delete(*[chaves.token_da_sessao(credencial_hash, a) for a in audiencias.DO_BFF.values()])
    except Exception:  # noqa: BLE001
        redis_caiu()
        logger.warning("sessao.tokens_nao_esquecidos", exc_info=True)


def confirmar(sessao: Sessao, *, com_segundo_fator: bool) -> None:
    """O step-up (fase 6): a pessoa provou quem é de novo. O `auth_time` anda, e
    os access guardados saem — o próximo já nasce com a hora nova."""
    sessao.auth_time = timezone.now()
    campos = ["auth_time"]
    if com_segundo_fator and "otp" not in (sessao.amr or []):
        sessao.amr = [*(sessao.amr or ["pwd"]), "otp"]
        campos.append("amr")
    sessao.save(update_fields=campos)
    esquecer_tokens(sessao.credencial_hash)


def publicar_revogacao(sid) -> bool:
    try:
        _redis().set(chaves.sessao_revogada(str(sid)), 1, ex=settings.SESSION_REVOKE_TTL_SECONDS)
        return True
    except Exception:  # noqa: BLE001 - a tabela já diz; o PEP sem Redis pergunta à IAM
        redis_caiu()
        logger.exception("sessao.revogacao_nao_publicada sid=%s", sid)
        return False


def revogar(sid, motivo: str) -> bool:
    """Revoga uma sessão. Devolve se ela estava ativa."""
    hashes = list(Sessao.objects.filter(sid=sid).values_list("credencial_hash", flat=True))
    n = Sessao.objects.filter(sid=sid, revogada_em__isnull=True).update(
        revogada_em=timezone.now(), motivo=motivo[:40]
    )
    publicar_revogacao(sid)
    for h in hashes:
        esquecer_tokens(h)
    return bool(n)


def revogar_todas(usuario, motivo: str, *, exceto=None) -> int:
    """`usuario` pode ser só um objeto com `.id` — a desativação por sinal
    (`signals.py`) revoga a partir do id, sem a linha carregada."""
    ativas = Sessao.objects.filter(usuario_id=usuario.id, revogada_em__isnull=True)
    if exceto:
        ativas = ativas.exclude(sid=exceto)
    linhas = list(ativas.values_list("sid", "credencial_hash"))
    ativas.update(revogada_em=timezone.now(), motivo=motivo[:40])
    for sid, credencial_hash in linhas:
        publicar_revogacao(sid)
        esquecer_tokens(credencial_hash)
    return len(linhas)


def ativa(sid) -> bool:
    """A sessão existe, não foi revogada e a pessoa segue ativa."""
    if not sid:
        return False
    return Sessao.objects.filter(
        sid=sid, revogada_em__isnull=True, usuario__is_active=True
    ).exists()
