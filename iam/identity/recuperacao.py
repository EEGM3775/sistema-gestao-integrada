"""Recuperação de senha e troca de e-mail (D11) — regras de domínio.

Separado das views de propósito: as regras que sustentam a segurança do fluxo
(uso único, expiração, cooldown, atribuição na trilha) não podem depender de
alguém lembrar de repeti-las em cada endpoint.

**Modelo de ameaça que este módulo endereça.** A recuperação por e-mail resolve
o usuário que esqueceu a senha, mas sozinha ela *move* o problema do admin
comprometido em vez de resolvê-lo: quem pode editar o e-mail de um usuário pode
apontá-lo para a própria caixa e pedir a recuperação. Por isso o fluxo aqui é
sempre um trio — token de uso único, carência após troca de e-mail
(`cooldown_ativo`) e evento na trilha com atribuição explícita.

**Existe um caminho só:** o token vai para o e-mail do próprio usuário, sempre. O
admin é *notificado* de que houve o pedido, mas não recebe o link — ele fica
sabendo de tudo sem ganhar poder de assumir conta alguma. É por isso que o e-mail
é obrigatório e único no `Usuario`: sem endereço próprio não há recuperação
possível, e sem unicidade o fluxo não sabe para qual conta resolver.
"""
import hashlib
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import EventoSeguranca, TokenRecuperacaoSenha, TrocaEmailPendente


# --- token ------------------------------------------------------------------
# 32 bytes de urandom em base64url: ~256 bits. O que trafega no link é este valor
# em claro; no banco fica só o SHA-256. Não usamos o hasher de senha do Django
# aqui de propósito — ele é lento por desenho (proteção contra força bruta em
# segredo de baixa entropia), e num token aleatório de 256 bits isso só serve
# para tornar a validação cara sem ganho: não há dicionário a percorrer.
def gerar_token():
    """Devolve `(claro, hash)`. O claro só existe em memória e no e-mail."""
    claro = secrets.token_urlsafe(32)
    return claro, hash_token(claro)


def hash_token(claro):
    return hashlib.sha256(claro.encode("utf-8")).hexdigest()


def mascarar_email(email):
    """`edison@empresa.com` → `e••••n@empresa.com`.

    Usado nas respostas da API e na trilha: confirma ao usuário *qual* caixa
    receberá o token sem expor o endereço a quem apenas chutou um username.
    """
    if not email or "@" not in email:
        return ""
    local, _, dominio = email.partition("@")
    if len(local) <= 2:
        visivel = local[:1]
        return f"{visivel}{'•' * 4}@{dominio}"
    return f"{local[0]}{'•' * 4}{local[-1]}@{dominio}"


# --- trilha -----------------------------------------------------------------
def registrar_evento(tipo, alvo, autor=None, request=None, **detalhes):
    """Grava um `EventoSeguranca`. Nunca levanta — trilha não derruba o fluxo.

    A trilha é append-only e a perda de um evento é ruim, mas derrubar um reset
    legítimo porque a auditoria falhou seria pior: o usuário ficaria travado, que
    é exatamente o problema que o D11 existe para resolver.
    """
    try:
        ip, agent = _origem(request)
        EventoSeguranca.objects.create(
            tipo=tipo,
            alvo=alvo,
            alvo_username=getattr(alvo, "username", "") or "",
            autor=autor,
            autor_username=getattr(autor, "username", "") or "",
            tenant=getattr(alvo, "tenant", None),
            ip=ip,
            user_agent=agent,
            detalhes=detalhes,
        )
    except Exception:  # pragma: no cover - defensivo
        import logging

        logging.getLogger(__name__).exception(
            "Falha ao gravar EventoSeguranca (%s) para %s", tipo, getattr(alvo, "id", None)
        )


def _origem(request):
    """IP de origem para a trilha de segurança — o real, não o que o cliente diz.

    O gateway NÃO reescreve o `X-Forwarded-For`: ele **acrescenta** o IP real ao
    que veio do cliente (`$proxy_add_x_forwarded_for`). Logo o primeiro elemento
    da cadeia é texto arbitrário enviado por quem faz a requisição — pegá-lo,
    como se fazia antes, permitia **escrever IP falso na trilha de auditoria**,
    justamente o registro que existe para reconstituir um incidente (dava para
    incriminar outro endereço ou esconder o próprio).

    O endereço confiável é o ÚLTIMO acrescentado pelo proxy mais próximo. Com N
    proxies confiáveis, é o N-ésimo a partir do fim — mesmo raciocínio do
    `NUM_PROXIES` que o DRF usa no throttle, e o mesmo knob para os dois.
    """
    if request is None:
        return None, ""
    ip = request.META.get("REMOTE_ADDR")
    cadeia = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
    if cadeia:
        n = max(1, getattr(settings, "NUM_PROXIES", 1))
        ip = cadeia[-min(n, len(cadeia))]
    return ip or None, (request.META.get("HTTP_USER_AGENT") or "")[:300]


# --- emissão / consumo ------------------------------------------------------
def cooldown_ativo(usuario):
    """A conta trocou de e-mail há pouco → nenhum token novo por enquanto.

    Esta é a trava que impede o encadeamento "troco o e-mail da vítima → peço a
    recuperação para a minha caixa". Durante a carência o aviso enviado ao
    endereço ANTIGO tem tempo de chegar e a troca, de ser contestada.
    """
    if not usuario.email_alterado_em:
        return False
    horas = settings.PASSWORD_RESET_COOLDOWN_TROCA_EMAIL_HORAS
    return usuario.email_alterado_em > timezone.now() - timezone.timedelta(hours=horas)


def excedeu_limite(usuario):
    """Teto de solicitações por hora — anti-spam contra a caixa da vítima."""
    desde = timezone.now() - timezone.timedelta(hours=1)
    return (
        TokenRecuperacaoSenha.objects.filter(usuario=usuario, criado_em__gte=desde).count()
        >= settings.PASSWORD_RESET_MAX_POR_HORA
    )


@transaction.atomic
def emitir_token(usuario, request=None):
    """Emite um token de uso único, invalidando os anteriores da conta.

    Invalidar os anteriores é deliberado: dois tokens vivos ao mesmo tempo
    dobram a superfície e criam o caso confuso de o usuário consumir um link
    antigo esquecido na caixa.
    """
    claro, digest = gerar_token()
    agora = timezone.now()

    TokenRecuperacaoSenha.objects.filter(
        usuario=usuario, usado_em__isnull=True, invalidado_em__isnull=True
    ).update(invalidado_em=agora)

    ip, _agent = _origem(request)
    token = TokenRecuperacaoSenha.objects.create(
        usuario=usuario,
        token_hash=digest,
        enviado_para=usuario.email,
        expira_em=agora + timezone.timedelta(minutes=settings.PASSWORD_RESET_TTL_MINUTES),
        ip_solicitacao=ip,
    )
    return claro, token


def admins_do_tenant(usuario):
    """Admins que devem ser NOTIFICADOS de um pedido de recuperação.

    Recebem aviso, nunca o link: ficam sabendo que a conta pediu recuperação —
    e podem reagir se não fizer sentido — sem que isso lhes dê a capacidade de
    assumir a conta. É a diferença entre supervisão e poder.
    """
    if not usuario.tenant_id:
        return []
    from .models import Usuario

    return list(
        Usuario.objects.filter(
            tenant_id=usuario.tenant_id, is_tenant_admin=True, is_active=True
        ).exclude(pk=usuario.pk).exclude(email="")
    )


def resolver_token(claro):
    """Devolve o token válido correspondente, ou None.

    Só compara hashes: o valor em claro nunca é buscado no banco, então um
    `LIKE` acidental ou um log de query não expõem credencial utilizável.
    """
    if not claro:
        return None
    token = TokenRecuperacaoSenha.objects.filter(token_hash=hash_token(claro)).select_related(
        "usuario"
    ).first()
    if token is None or not token.valido:
        return None
    return token


@transaction.atomic
def consumir_token(token, nova_senha, request=None):
    """Aplica a nova senha e encerra TODAS as sessões do usuário.

    Encerrar tudo é parte da correção, não zelo extra: quem redefine senha ou
    esqueceu a dela (e pode ter sido comprometida) ou está sendo destravado por
    um admin. Nos dois casos, sessão viva anterior é risco.
    """
    from .revocation import bump_session_epoch
    from .tokens import revoke_all_sessions

    usuario = token.usuario
    usuario.set_password(nova_senha)
    usuario.save(update_fields=["password"])

    token.usado_em = timezone.now()
    token.save(update_fields=["usado_em"])
    # Qualquer outro token vivo morre junto: a conta acabou de mudar de mãos.
    TokenRecuperacaoSenha.objects.filter(
        usuario=usuario, usado_em__isnull=True, invalidado_em__isnull=True
    ).update(invalidado_em=timezone.now())

    revoke_all_sessions(usuario)
    bump_session_epoch(usuario.id)  # corta o access residual (≤ TTL) na hora

    registrar_evento(
        EventoSeguranca.Tipo.RESET_CONCLUIDO,
        alvo=usuario,
        autor=None,
        request=request,
        enviado_para=mascarar_email(token.enviado_para),
    )
    return usuario


# --- troca de e-mail --------------------------------------------------------
@transaction.atomic
def abrir_troca_email(usuario, email_novo, solicitante=None, request=None):
    """Registra a troca como PENDENTE e devolve `(claro, pendencia)`.

    O e-mail do usuário **não** muda aqui. Só muda quando o link enviado ao
    endereço ANTIGO for confirmado — que é o que tira o admin comprometido do
    caminho: ele pode pedir a troca, mas o link cai numa caixa que não é dele.
    """
    claro, digest = gerar_token()
    agora = timezone.now()

    TrocaEmailPendente.objects.filter(
        usuario=usuario, confirmado_em__isnull=True, cancelado_em__isnull=True
    ).update(cancelado_em=agora)

    pendencia = TrocaEmailPendente.objects.create(
        usuario=usuario,
        email_antigo=usuario.email,
        email_novo=email_novo,
        token_hash=digest,
        solicitante=solicitante,
        expira_em=agora + timezone.timedelta(hours=settings.EMAIL_CHANGE_TTL_HORAS),
    )
    registrar_evento(
        EventoSeguranca.Tipo.EMAIL_TROCA_SOLICITADA,
        alvo=usuario,
        autor=solicitante,
        request=request,
        de=mascarar_email(usuario.email),
        para=mascarar_email(email_novo),
    )
    return claro, pendencia


def resolver_troca_email(claro):
    if not claro:
        return None
    pendencia = TrocaEmailPendente.objects.filter(
        token_hash=hash_token(claro)
    ).select_related("usuario").first()
    if pendencia is None or not pendencia.pendente:
        return None
    return pendencia


@transaction.atomic
def confirmar_troca_email(pendencia, request=None):
    """Aplica o e-mail novo e ARMA o cooldown de recuperação.

    O carimbo `email_alterado_em` é o que bloqueia a emissão de token de reset
    pelas próximas horas — sem ele, confirmar a troca e pedir "esqueci minha
    senha" em seguida continuaria sendo takeover em dois passos.
    """
    usuario = pendencia.usuario
    usuario.email = pendencia.email_novo
    usuario.email_alterado_em = timezone.now()
    usuario.save(update_fields=["email", "email_alterado_em"])

    pendencia.confirmado_em = timezone.now()
    pendencia.save(update_fields=["confirmado_em"])

    registrar_evento(
        EventoSeguranca.Tipo.EMAIL_TROCA_CONFIRMADA,
        alvo=usuario,
        autor=None,
        request=request,
        para=mascarar_email(usuario.email),
    )
    return usuario


@transaction.atomic
def cancelar_troca_email(pendencia, request=None):
    """Cancelamento pelo dono da conta — o "não fui eu" do e-mail de aviso."""
    pendencia.cancelado_em = timezone.now()
    pendencia.save(update_fields=["cancelado_em"])
    registrar_evento(
        EventoSeguranca.Tipo.EMAIL_TROCA_CANCELADA,
        alvo=pendencia.usuario,
        autor=None,
        request=request,
        para=mascarar_email(pendencia.email_novo),
    )
