import base64
import hashlib
import hmac
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from . import emails, quotas, recuperacao, segundo_fator, sessoes
from .models import (
    AcessoUsuarioModulo,
    AssinaturaTenant,
    EventoSeguranca,
    Modulo,
    Perfil,
    Permissao,
    Tenant,
    Usuario,
)
from .cookies import clear_refresh_cookie, set_refresh_cookie
from .permissions import IsPlatformAdmin, IsTenantAdmin
from .serializers import (
    AcessoUsuarioModuloSerializer,
    AssinaturaTenantSerializer,
    IamTokenObtainPairSerializer,
    ModuloSerializer,
    PerfilSerializer,
    PermissaoSerializer,
    TenantSerializer,
    UsuarioSerializer,
)
from payment.planos import (
    CONFIRMACAO_JANELA_MAX_MIN,
    CONFIRMACAO_JANELA_MIN_MIN,
    CONFIRMACAO_JANELA_PADRAO_MIN,
)

from .revocation import bump_session_epoch
from .tokens import (
    access_with_claims,
    claims_de_acesso,
    cookie_max_age,
    issue_refresh,
    issue_service_token,
    revoke_all_sessions,
)


# --- Autenticação / SSO ---
# Modelo de sessão (Fase 10.6 / F1): o **access token** (15 min) volta no corpo e
# vive em memória no cliente; o **refresh** vive só num cookie HttpOnly. O cliente
# renova o access em silêncio via /auth/refresh/ (cookie) → nunca desloga. Rotação
# + blacklist detectam reuso; o refresh recalcula as claims (permissões atualizam).


def _bloqueia_origem_estranha(request) -> None:
    """Defesa de CSRF no refresh/logout (que dependem do cookie): rejeita origem
    cross-site. Same-origin (via gateway) e clientes sem `Origin` passam.

    Compara **hostname sem porta**: atrás do gateway, `proxy_set_header Host $host`
    entrega o Host sem porta (`localhost`), mas o `Origin` do browser traz a porta
    (`localhost:8090`) — comparar netloc com porta daria falso 403."""
    origin = request.headers.get("Origin")
    if not origin:
        return  # apps nativos / same-origin sem header Origin
    origin_host = urlparse(origin).hostname or ""
    request_host = request.get_host().split(":")[0]
    if origin_host and origin_host == request_host:
        return  # mesma origem (mesmo host), ignorando porta
    if origin in set(getattr(settings, "CORS_ALLOWED_ORIGINS", [])):
        return  # origem de dev explicitamente permitida
    raise PermissionDenied("Origem não permitida.")


def _corpo_sessao(user, access, refresh) -> dict:
    """Corpo devolvido no login: access + identidade + entitlements (sem refresh).

    `session_expires_at` é o `exp` do REFRESH (época em segundos). O refresh vive
    num cookie HttpOnly — opaco ao JS —, então sem este campo o front não teria como
    saber quando a sessão cai nem agendar o aviso. É só um instante, não vaza segredo.
    """
    tenant = user.tenant
    return {
        "access": str(access),
        "session_expires_at": int(refresh.payload["exp"]),
        "session_warn_seconds": settings.SESSION_WARN_SECONDS,
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "is_tenant_admin": user.is_tenant_admin,
            "is_platform_admin": user.is_superuser,
        },
        "tenant": (
            {"id": str(tenant.id), "slug": tenant.slug, "nome": tenant.nome} if tenant else None
        ),
        "modules": user.modulos_efetivos(),
    }


def _abrir_sessao(user, *, remember: bool, amr: list[str], extra: dict | None = None):
    """Emite a sessão (access no corpo, refresh no cookie). Único ponto por onde
    o login — com ou sem segundo fator — entrega uma sessão nova."""
    refresh = issue_refresh(user, remember=remember, amr=amr)
    resp = Response({**_corpo_sessao(user, access_with_claims(refresh, user), refresh), **(extra or {})})
    # Sem "manter conectado" → cookie de sessão (some ao fechar o navegador/
    # desligar o PC → novo login). Com → persistente (sobrevive ao reboot).
    set_refresh_cookie(resp, str(refresh), cookie_max_age(refresh), persistent=remember)
    return resp


_AMR_COM_SEGUNDO_FATOR = ["pwd", "otp"]


class LoginView(TokenObtainPairView):
    """Primeira etapa: a senha. Para quem tem segundo fator — ou é obrigado a
    ter e ainda não cadastrou — a senha certa **não** abre sessão: devolve o
    desafio da segunda etapa (`segundo_fator.emitir_desafio`)."""

    serializer_class = IamTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # valida credenciais → 401 se erradas
        user = serializer.user
        remember = bool(request.data.get("remember"))

        if segundo_fator.ativo(user) is not None:
            return Response({
                "segundo_fator": "codigo",
                "desafio": segundo_fator.emitir_desafio(user, remember=remember, etapa="codigo"),
            })
        if segundo_fator.obrigatorio(user):
            return Response({
                "segundo_fator": "cadastro",
                "desafio": segundo_fator.emitir_desafio(user, remember=remember, etapa="cadastro"),
            })
        return _abrir_sessao(user, remember=remember, amr=["pwd"])


def _resposta_recusa(erro: "segundo_fator.CodigoRecusado"):
    if erro.motivo == "bloqueado":
        return Response(
            {
                "detail": (
                    "Muitos códigos errados seguidos. Por segurança, o segundo fator "
                    "desta conta está travado por alguns minutos."
                ),
                "bloqueado": True,
            },
            status=429,
        )
    return Response({"detail": "Código incorreto ou já usado."}, status=400)


_DESAFIO_VENCIDO = {"detail": "O tempo para confirmar passou. Entre com a senha de novo."}


class LoginSegundoFatorView(APIView):
    """Segunda etapa: o código do app (ou um de recuperação) troca o desafio
    por uma sessão com `amr` = senha + segundo fator."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        aberto = segundo_fator.abrir_desafio(request.data.get("desafio"), "codigo")
        if aberto is None:
            return Response(_DESAFIO_VENCIDO, status=401)
        user, remember, nonce = aberto
        try:
            modo = segundo_fator.verificar(user, request.data.get("codigo"), request=request)
        except segundo_fator.CodigoRecusado as erro:
            return _resposta_recusa(erro)
        segundo_fator.gastar_desafio(nonce)
        extra = {}
        if modo == "recuperacao":
            extra["codigos_restantes"] = segundo_fator.codigos_restantes(user)
        return _abrir_sessao(user, remember=remember, amr=_AMR_COM_SEGUNDO_FATOR, extra=extra)


class RefreshView(APIView):
    """Renova o access token a partir do refresh no cookie. Rotaciona o refresh
    (blacklist do antigo → reuso de um token velho cai em 401 e derruba a sessão)
    e **recalcula as claims** (permissão revogada/alterada vale em ≤ 15 min)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        _bloqueia_origem_estranha(request)
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not raw:
            return Response({"detail": "Sessão ausente."}, status=401)

        def falha(msg, token=None):
            resp = Response({"detail": msg}, status=401)
            if token is not None:
                try:
                    token.blacklist()
                except (AttributeError, TokenError):
                    pass
            clear_refresh_cookie(resp)
            return resp

        try:
            old = RefreshToken(raw)  # valida assinatura, exp e blacklist (reuso)
        except TokenError:
            return falha("Sessão inválida ou expirada.")

        now = int(timezone.now().timestamp())
        sst = int(old.get("sst") or now)
        remember = bool(old.get("rem"))
        cap = settings.SESSION_ABS_CAP if remember else settings.SESSION_IDLE_CAP
        if now - sst > int(cap.total_seconds()):
            return falha("Sessão expirada (tempo máximo atingido).", token=old)

        try:
            user = Usuario.objects.get(id=old["user_id"])
        except Usuario.DoesNotExist:
            return falha("Usuário inexistente.", token=old)
        if not user.is_active:
            return falha("Usuário inativo.", token=old)

        # Fase 4 — a sessão é que se revoga (logout, troca de senha, "encerrar
        # todas"). Refresh de antes da fase 4 não tem `sid`: renova e ganha uma.
        sid = old.get("sid")
        if sid and not sessoes.ativa(sid):
            return falha("Sessão encerrada.", token=old)

        # Fase 1 — a sessão aberta só com senha não sobrevive a quem tem (ou
        # passou a ser obrigado a ter) segundo fator. É o que faz a regra valer
        # no dia do deploy, e não 30 dias depois, quando a última sessão
        # "lembrada" do admin expirar.
        amr = list(old.get("amr") or ["pwd"])
        if "otp" not in amr and (
            segundo_fator.obrigatorio(user) or segundo_fator.ativo(user) is not None
        ):
            return falha("Esta conta passou a exigir o segundo fator. Entre de novo.", token=old)

        # Rotação: invalida o antigo e emite um novo preservando o início da sessão.
        try:
            old.blacklist()
        except (AttributeError, TokenError):
            pass
        novo = issue_refresh(user, remember=remember, sst=sst, amr=amr,
                             sid=sid, auth_time=old.get("auth_time"))
        resp = Response({
            "access": str(access_with_claims(novo, user)),
            # Cada rotação estende a janela deslizante: o front reagenda o aviso de
            # queda a partir daqui (não consegue ler o `exp` do cookie HttpOnly).
            "session_expires_at": int(novo.payload["exp"]),
            "session_warn_seconds": settings.SESSION_WARN_SECONDS,
        })
        set_refresh_cookie(resp, str(novo), cookie_max_age(novo), persistent=remember)
        return resp


class LogoutView(APIView):
    """Encerra a sessão: blacklista o refresh do cookie e limpa o cookie. Aceita
    mesmo sem access válido (o usuário pode estar com o access já expirado)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        _bloqueia_origem_estranha(request)
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        resp = Response({"detail": "logout efetuado"}, status=200)
        clear_refresh_cookie(resp)
        if raw:
            try:
                refresh = RefreshToken(raw)
                refresh.blacklist()
                # Fase 4: o access desta sessão deixa de valer em todo serviço
                # na requisição seguinte, e não quando expira.
                if refresh.get("sid"):
                    sessoes.revogar(refresh["sid"], "logout")
            except TokenError:
                pass
        return resp


class ServiceTokenView(APIView):
    """Emite um JWT **serviço→serviço** de vida curta (Fase 10.8).

    Não é login de usuário: o chamador é um serviço da plataforma (ex.: o
    backend), autenticado por um segredo compartilhado no header
    `X-Service-Secret` (comparação em tempo constante). O token resultante
    carrega só o `tenant_id` e o `modules` pedidos — o suficiente para passar no
    gate de módulo do produto-alvo (drone). Ver `tokens.issue_service_token`.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        segredo = request.headers.get("X-Service-Secret", "")
        esperado = settings.SERVICE_TOKEN_SECRET or ""
        # Fail-closed: sem segredo configurado ou divergente → 401 (tempo constante).
        if not esperado or not hmac.compare_digest(segredo, esperado):
            return Response({"detail": "credencial de serviço inválida"}, status=401)

        tenant_id = request.data.get("tenant_id")
        if not tenant_id:
            return Response({"detail": "tenant_id é obrigatório"}, status=400)
        audience = request.data.get("audience") or "drone"
        caller = request.data.get("caller") or "backend"

        token = issue_service_token(caller=caller, tenant_id=tenant_id, audience=audience)
        return Response({"access": token, "expires_in": settings.SERVICE_TOKEN_TTL_SECONDS})


class ChangePasswordView(APIView):
    """Troca da própria senha. Valida a senha atual, aplica a nova e **encerra
    todas as outras sessões** do usuário (blacklist) — reemitindo uma sessão nova
    só para este dispositivo. Assim, uma senha vazada/roubada é cortada em todos
    os outros lugares no ato da troca."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        _bloqueia_origem_estranha(request)
        user = request.user
        atual = request.data.get("senha_atual") or ""
        nova = request.data.get("nova_senha") or ""

        if not user.check_password(atual):
            return Response({"detail": "Senha atual incorreta."}, status=400)
        if len(nova) < 8:
            return Response({"detail": "A nova senha deve ter ao menos 8 caracteres."}, status=400)
        if nova == atual:
            return Response({"detail": "A nova senha deve ser diferente da atual."}, status=400)

        # Preserva o "lembrar" e o `amr` da sessão atual para a nova sessão deste
        # dispositivo — trocar a senha não desfaz o segundo fator já provado.
        remember = False
        amr = ["pwd"]
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if raw:
            try:
                atual_refresh = RefreshToken(raw)
                remember = bool(atual_refresh.get("rem"))
                amr = list(atual_refresh.get("amr") or ["pwd"])
            except TokenError:
                pass

        user.set_password(nova)
        user.save(update_fields=["password"])
        revoke_all_sessions(user, motivo="troca_de_senha")  # TODAS, inclui a atual
        # Corta na hora o access residual das outras sessões (stateless, ≤ TTL).
        # Antes de reemitir: o novo access abaixo tem iat >= carimbo → sobrevive.
        bump_session_epoch(user.id)

        # Reemite uma sessão nova só para quem trocou a senha (não é deslogado).
        refresh = issue_refresh(user, remember=remember, amr=amr)
        resp = Response({
            "detail": "Senha alterada. As outras sessões foram encerradas.",
            "access": str(access_with_claims(refresh, user)),
            # Sessão nova → o front precisa reagendar o aviso de queda.
            "session_expires_at": int(refresh.payload["exp"]),
            "session_warn_seconds": settings.SESSION_WARN_SECONDS,
        })
        set_refresh_cookie(resp, str(refresh), cookie_max_age(refresh), persistent=remember)
        return resp


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        # O que a tela precisa para esconder o que a pessoa não pode — lido das
        # tabelas, e não do token, que desde a fase 4 não carrega listas.
        return Response(
            {"id": str(u.id), "username": u.username, "email": u.email, **claims_de_acesso(u)}
        )


class SessaoInternaView(APIView):
    """A sessão ainda vale? — para o PEP que não alcança o Redis (fase 4, §10.8).

    Responde só sim ou não sobre um `sid` (UUID aleatório, que só quem tem o
    token conhece). É **interna**: o gateway devolve 404 para `/auth/interno/`,
    como faz com o `service-token`; só a rede dos serviços a alcança.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, sid):
        return Response({"ativa": sessoes.ativa(sid)})


# ---------------------------------------------------------------------------
# Remodelagem, fase 1 — segundo fator e janela de confirmação (§10.5)
# ---------------------------------------------------------------------------


def _lembrar_da_sessao(request) -> bool:
    raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
    if not raw:
        return False
    try:
        return bool(RefreshToken(raw).get("rem"))
    except TokenError:
        return False


def _quem_cadastra(request):
    """O cadastro tem duas portas: a tela de perfil (sessão aberta) e o login do
    admin que ainda não tem segundo fator (desafio da etapa `cadastro`).
    Devolve `(usuario, desafio_aberto)`; `(None, None)` se nenhuma abriu."""
    if request.user and request.user.is_authenticated:
        return request.user, None
    aberto = segundo_fator.abrir_desafio(request.data.get("desafio"), "cadastro")
    if aberto is None:
        return None, None
    return aberto[0], aberto


class CadastroSegundoFatorView(APIView):
    """Começa (ou recomeça) o cadastro: segredo novo, QR e a URI `otpauth://`.
    Nada muda no login até a confirmação."""

    permission_classes = [AllowAny]

    def post(self, request):
        _bloqueia_origem_estranha(request)
        user, _aberto = _quem_cadastra(request)
        if user is None:
            return Response(_DESAFIO_VENCIDO, status=401)
        try:
            segredo, uri = segundo_fator.iniciar_cadastro(user)
        except ValueError as erro:
            return Response({"detail": str(erro)}, status=409)
        return Response({"segredo": segredo, "uri": uri, "qr": segundo_fator.qr_svg(uri)})


class ConfirmarCadastroSegundoFatorView(APIView):
    """O primeiro código certo liga o segundo fator. Devolve os códigos de
    recuperação — a única vez em que aparecem — e uma sessão nova com `otp`.

    Pela tela de perfil, as **outras** sessões caem: foram abertas só com senha,
    e o refresh já as recusaria na próxima volta; derrubar aqui fecha a janela
    do access que ainda estiver vivo."""

    permission_classes = [AllowAny]

    def post(self, request):
        _bloqueia_origem_estranha(request)
        user, aberto = _quem_cadastra(request)
        if user is None:
            return Response(_DESAFIO_VENCIDO, status=401)
        try:
            codigos = segundo_fator.confirmar_cadastro(
                user, request.data.get("codigo"), request=request,
            )
        except segundo_fator.CodigoRecusado as erro:
            return _resposta_recusa(erro)
        if aberto is not None:
            _usuario, remember, nonce = aberto
            segundo_fator.gastar_desafio(nonce)
        else:
            remember = _lembrar_da_sessao(request)
            revoke_all_sessions(user, motivo="segundo_fator")
            bump_session_epoch(user.id)  # antes de reemitir: o access novo sobrevive
        return _abrir_sessao(
            user, remember=remember, amr=_AMR_COM_SEGUNDO_FATOR, extra={"codigos": codigos},
        )


class DesativarSegundoFatorView(APIView):
    """Tira o segundo fator. Pede **os dois**: a senha e um código — quem tem os
    dois já é dono da conta, então exigi-los não enfraquece nada.

    Vale também para o obrigado a ter: é o "trocar de celular". A sessão atual
    segue (ela provou os dois fatores), e o próximo login pede o cadastro de
    novo; a tela leva direto a ele."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        _bloqueia_origem_estranha(request)
        user = request.user
        if not user.check_password(request.data.get("senha") or ""):
            return Response({"detail": "Senha incorreta."}, status=400)
        try:
            segundo_fator.verificar(user, request.data.get("codigo"), request=request)
        except segundo_fator.CodigoRecusado as erro:
            return _resposta_recusa(erro)
        segundo_fator.remover(user)
        recuperacao.registrar_evento(
            EventoSeguranca.Tipo.SEGUNDO_FATOR_DESATIVADO, alvo=user, autor=user, request=request,
        )
        emails.enviar_aviso_segundo_fator(user, "desativado")
        return Response({"detail": "Segundo fator desativado.", **segundo_fator.estado(user)})


class CodigosSegundoFatorView(APIView):
    """Troca os códigos de recuperação. Só com o código do app — um código de
    recuperação não gera outros dez."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        _bloqueia_origem_estranha(request)
        user = request.user
        try:
            segundo_fator.verificar(
                user, request.data.get("codigo"), request=request, aceita_recuperacao=False,
            )
        except segundo_fator.CodigoRecusado as erro:
            return _resposta_recusa(erro)
        codigos = segundo_fator.gerar_codigos(user)
        recuperacao.registrar_evento(
            EventoSeguranca.Tipo.SEGUNDO_FATOR_CODIGOS, alvo=user, autor=user, request=request,
        )
        emails.enviar_aviso_segundo_fator(user, "codigos")
        return Response({"codigos": codigos})


class SegurancaDaContaView(APIView):
    """A tela Minha conta › Segurança: estado do segundo fator e a janela de
    confirmação que a pessoa escolheu (e os limites dela, que são do dono)."""

    permission_classes = [IsAuthenticated]

    def _corpo(self, user):
        return {
            "segundo_fator": segundo_fator.estado(user),
            "janela_confirmacao": {
                "minutos": user.janela_confirmacao_min,
                "padrao": CONFIRMACAO_JANELA_PADRAO_MIN,
                "minimo": CONFIRMACAO_JANELA_MIN_MIN,
                "maximo": CONFIRMACAO_JANELA_MAX_MIN,
            },
        }

    def get(self, request):
        return Response(self._corpo(request.user))

    def patch(self, request):
        _bloqueia_origem_estranha(request)
        user = request.user
        valor = request.data.get("janela_confirmacao_min")
        try:
            minutos = int(valor)
        except (TypeError, ValueError):
            return Response({"janela_confirmacao_min": ["Informe um número de minutos."]}, status=400)
        if not CONFIRMACAO_JANELA_MIN_MIN <= minutos <= CONFIRMACAO_JANELA_MAX_MIN:
            return Response(
                {"janela_confirmacao_min": [
                    f"Escolha entre {CONFIRMACAO_JANELA_MIN_MIN} e "
                    f"{CONFIRMACAO_JANELA_MAX_MIN} minutos."
                ]},
                status=400,
            )
        user.janela_confirmacao_min = minutos
        user.save(update_fields=["janela_confirmacao_min"])
        return Response(self._corpo(user))


# ---------------------------------------------------------------------------
# D11 — recuperação de senha
# ---------------------------------------------------------------------------

# Resposta única do caminho público. É SEMPRE esta, dê certo ou não: conta
# inexistente, sem e-mail, em cooldown ou com o teto de solicitações estourado
# devolvem exatamente o mesmo corpo e o mesmo status. Qualquer diferença
# perceptível transformaria o endpoint em oráculo de enumeração de usuários —
# um atacante descobriria quem existe no sistema antes mesmo de tentar senha.
_RESPOSTA_GENERICA = {
    "detail": (
        "Se a conta existir e tiver e-mail cadastrado, enviamos um link de "
        "redefinição. Verifique sua caixa de entrada e o spam."
    )
}


class EsqueciSenhaView(APIView):
    """Caminho 1 — autoatendimento. Público, sem autenticação.

    O usuário informa o username (ou e-mail) e o token vai para a caixa DELE.
    Nenhum admin participa, é notificado ou fica sabendo — é o caminho normal e
    o que queremos que seja usado em 99% dos casos.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    # S8 — teto por ORIGEM, complementar ao teto de 5/h por conta. O limite por
    # conta não impede uma rajada contra contas diferentes (varredura de
    # usernames válidos pelo tempo de resposta, ou inundar caixas de e-mail
    # alheias); este fecha por IP.
    throttle_scope = "recuperacao"

    def post(self, request):
        identificador = (request.data.get("identificador") or "").strip()
        if not identificador:
            return Response(_RESPOSTA_GENERICA)

        usuario = (
            Usuario.objects.filter(username__iexact=identificador).first()
            or Usuario.objects.filter(email__iexact=identificador).first()
        )

        # Cada `return` abaixo devolve a MESMA resposta — as diferenças ficam só
        # na trilha e no log, onde não vazam para o solicitante.
        if usuario is None or not usuario.is_active or not usuario.email:
            return Response(_RESPOSTA_GENERICA)

        if recuperacao.cooldown_ativo(usuario):
            # O e-mail da conta mudou há pouco: não emitimos token até o aviso
            # ao endereço antigo ter tido tempo de chegar (ver recuperacao.py).
            recuperacao.registrar_evento(
                EventoSeguranca.Tipo.RESET_SOLICITADO,
                alvo=usuario, request=request, bloqueado="cooldown_troca_email",
            )
            return Response(_RESPOSTA_GENERICA)

        if recuperacao.excedeu_limite(usuario):
            recuperacao.registrar_evento(
                EventoSeguranca.Tipo.RESET_SOLICITADO,
                alvo=usuario, request=request, bloqueado="limite_por_hora",
            )
            return Response(_RESPOSTA_GENERICA)

        claro, _token = recuperacao.emitir_token(usuario, request=request)
        emails.enviar_recuperacao(usuario, claro, settings.PASSWORD_RESET_TTL_MINUTES)

        # Os admins do tenant são NOTIFICADOS, nunca copiados no link. Ficam
        # sabendo que houve o pedido — e podem reagir se não fizer sentido — sem
        # que isso lhes dê a capacidade de assumir a conta. Se o link viesse
        # junto, este endpoint (público, sem autenticação) permitiria a qualquer
        # anônimo fazer cair um token de takeover na caixa do admin.
        ip, _agent = recuperacao._origem(request)
        for admin in recuperacao.admins_do_tenant(usuario):
            emails.enviar_aviso_admin_recuperacao(admin, usuario, ip=ip)

        recuperacao.registrar_evento(
            EventoSeguranca.Tipo.RESET_SOLICITADO,
            alvo=usuario, request=request,
            enviado_para=recuperacao.mascarar_email(usuario.email),
        )
        return Response(_RESPOSTA_GENERICA)


class RedefinirSenhaComTokenView(APIView):
    """Consome o token (dos dois caminhos) e aplica a senha nova. Público.

    Não exige a senha antiga — é o ponto do fluxo. O que autoriza aqui é a posse
    do token de uso único entregue por e-mail, e ele vale por minutos.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        claro = (request.data.get("token") or "").strip()
        nova = request.data.get("nova_senha") or ""

        token = recuperacao.resolver_token(claro)
        if token is None:
            # Token inválido, expirado ou já usado — sem distinguir qual, para
            # não dar pistas a quem está sondando tokens.
            return Response(
                {"detail": "Link inválido ou expirado. Solicite uma nova redefinição."},
                status=400,
            )
        if len(nova) < 8:
            return Response(
                {"detail": "A nova senha deve ter ao menos 8 caracteres."}, status=400
            )

        usuario = recuperacao.consumir_token(token, nova, request=request)
        # Aviso pós-fato ao dono da conta: se a redefinição não foi ele, é aqui
        # que ele descobre.
        emails.enviar_aviso_senha_alterada(usuario)
        return Response({"detail": "Senha redefinida. Faça login com a nova senha."})


class ConfirmarTrocaEmailView(APIView):
    """Confirma (ou cancela) a troca de e-mail pelo link do endereço ANTIGO."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        claro = (request.data.get("token") or "").strip()
        pendencia = recuperacao.resolver_troca_email(claro)
        if pendencia is None:
            return Response({"detail": "Link inválido ou expirado."}, status=400)

        if request.data.get("cancelar"):
            # O "não fui eu" do e-mail de aviso: mata a troca e deixa rastro.
            recuperacao.cancelar_troca_email(pendencia, request=request)
            return Response({"detail": "Troca de e-mail cancelada."})

        usuario = recuperacao.confirmar_troca_email(pendencia, request=request)
        return Response(
            {
                "detail": "E-mail atualizado.",
                "email": recuperacao.mascarar_email(usuario.email),
            }
        )


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def jwk_kid(public_pem: str) -> str:
    """Identificador estável da chave (thumbprint curto do PEM público)."""
    return hashlib.sha256(public_pem.encode("utf-8")).hexdigest()[:16]


class JwksView(APIView):
    """JWKS: publica a chave pública RSA para validação por qualquer serviço.

    /.well-known/jwks.json — usado pelos validadores (backend, drone, microsserviços)
    para validar a assinatura RS256 sem conhecer nenhum segredo. Vazio em HS256.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        pub = getattr(settings, "JWT_PUBLIC_KEY", "") or ""
        if not pub:
            return Response({"keys": []})
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        numbers = load_pem_public_key(pub.encode("utf-8")).public_numbers()
        jwk = {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": jwk_kid(pub),
            "n": _b64url_uint(numbers.n),
            "e": _b64url_uint(numbers.e),
        }
        return Response({"keys": [jwk]})


# --- Administração da plataforma (superuser) ---

class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [IsPlatformAdmin]


class PermissaoViewSet(viewsets.ModelViewSet):
    queryset = Permissao.objects.all()
    serializer_class = PermissaoSerializer

    def get_permissions(self):
        # Catálogo de permissões é legível por admin de tenant (para compor papéis);
        # alterá-lo é só via `sync_authz` (superuser), pois a fonte é o código.
        if self.action in ("list", "retrieve"):
            return [IsTenantAdmin()]
        return [IsPlatformAdmin()]


class ModuloViewSet(viewsets.ModelViewSet):
    queryset = Modulo.objects.all()
    serializer_class = ModuloSerializer

    def get_permissions(self):
        # Catálogo de módulos é legível por qualquer autenticado (para a UI);
        # alterações só por admin de plataforma.
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsPlatformAdmin()]


class AssinaturaTenantViewSet(viewsets.ModelViewSet):
    queryset = AssinaturaTenant.objects.select_related("tenant", "modulo").all()
    serializer_class = AssinaturaTenantSerializer
    permission_classes = [IsPlatformAdmin]


# --- Administração do tenant (escopada ao próprio tenant) ---

class CatalogoPermissoesView(APIView):
    """Catálogo de permissões agrupado por módulo — insumo da tela de personas
    ("criar cargo" no RH). Marca quais módulos o tenant assina (o front desabilita
    os demais) e devolve os templates de fábrica para clonar. Só admin de tenant.
    """

    permission_classes = [IsTenantAdmin]

    def get(self, request):
        from . import catalog

        u = request.user
        assinados = set(u.tenant.modulos_ativos()) if getattr(u, "tenant", None) else set()
        ids = {p.codename: p.id for p in Permissao.objects.all()}
        grupos: dict[str, list] = {}
        for p in catalog.CATALOGO:
            grupos.setdefault(p.modulo, []).append(
                {"id": ids.get(p.code), "code": p.code, "nome": p.nome}
            )
        modulos = [
            {
                "modulo": mod,
                "atribuivel": mod in ("base", "plataforma") or mod in assinados,
                "permissoes": perms,
            }
            for mod, perms in grupos.items()
        ]
        return Response({"modulos": modulos, "templates": list(catalog.TEMPLATES_PAPEL)})




class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.select_related("tenant", "segundo_fator").all()
    serializer_class = UsuarioSerializer
    permission_classes = [IsTenantAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        return qs if u.is_superuser else qs.filter(tenant_id=u.tenant_id)

    def perform_create(self, serializer):
        u = self.request.user
        if u.is_superuser:
            # Dono da plataforma provisionando: não é cliente, não tem plano a
            # respeitar. É também o caminho de resgate quando um tenant precisa
            # de um usuário fora do que contratou (suporte, migração).
            serializer.save()
            return
        quotas.checar_seats(u.tenant)  # D24 — 402 antes de gravar
        serializer.save(tenant=u.tenant)

    def perform_update(self, serializer):
        u = self.request.user
        if u.is_superuser:
            serializer.save()
            return
        # D24 — REATIVAR consome um seat tanto quanto criar. Sem esta checagem a
        # trava do `perform_create` seria contornável pela porta dos fundos:
        # desativar não é obrigatório para chegar ao limite, mas quem já esbarrou
        # nele desativa alguém, cria o novo e reativa o antigo — e termina com
        # mais usuários ativos do que contratou, sem passar pelo 402 nenhuma vez.
        if serializer.validated_data.get("is_active") and not serializer.instance.is_active:
            quotas.checar_seats(u.tenant)
        serializer.save(tenant=u.tenant)

    @action(detail=True, methods=["post"], url_path="redefinir-senha")
    def redefinir_senha(self, request, pk=None):
        """Redefinição **presencial**: exige a senha ATUAL do alvo.

        Serve ao caso do admin sentado ao lado da pessoa, que digita a própria
        senha antiga. Continua existindo porque não é um primitivo de takeover:
        quem não sabe a senha do alvo não passa daqui. Para o usuário que
        *esqueceu* a senha — que não tem como fornecê-la — o caminho é
        `recuperacao-assistida` (ou, melhor, o autoatendimento por e-mail).
        """
        alvo = self.get_object()  # já escopado ao tenant (get_queryset)
        atual = request.data.get("senha_atual") or ""
        nova = request.data.get("nova_senha") or ""
        if not alvo.check_password(atual):
            return Response({"detail": "Senha atual do usuário incorreta."}, status=400)
        if len(nova) < 8:
            return Response({"detail": "A nova senha deve ter ao menos 8 caracteres."}, status=400)
        if nova == atual:
            return Response({"detail": "A nova senha deve ser diferente da atual."}, status=400)
        alvo.set_password(nova)
        alvo.save(update_fields=["password"])
        revoke_all_sessions(alvo, motivo="senha_redefinida")
        bump_session_epoch(alvo.id)  # corta o access residual do alvo na hora
        recuperacao.registrar_evento(
            EventoSeguranca.Tipo.SENHA_ALTERADA,
            alvo=alvo, autor=request.user, request=request, modo="presencial",
        )
        emails.enviar_aviso_senha_alterada(alvo, por_quem=request.user)
        return Response({"detail": "Senha redefinida. As sessões do usuário foram encerradas."})

    @action(detail=True, methods=["post"], url_path="redefinir-segundo-fator")
    def redefinir_segundo_fator(self, request, pk=None):
        """Para quem perdeu o celular **e** os códigos de recuperação.

        Apaga o segundo fator do alvo e derruba todas as sessões dele; no
        próximo login, ele entra só com a senha (ou, se for obrigado a ter,
        cadastra de novo ali mesmo). É poder de verdade — um admin que redefine
        o segundo fator de alguém fica a uma senha da conta —, e por isso nunca
        é silencioso: evento na trilha com o nome de quem fez e e-mail ao alvo.

        O admin do tenant não alcança o supervisor da plataforma (que mora num
        tenant, mas não é dele), e ninguém redefine a própria conta por aqui: o
        caminho para si é o código de recuperação.
        """
        alvo = self.get_object()
        if alvo.pk == request.user.pk:
            return Response(
                {"detail": "Para a própria conta, use Minha conta › Segurança."}, status=400,
            )
        if alvo.is_superuser and not request.user.is_superuser:
            return Response(
                {"detail": "Só o supervisor da plataforma redefine o segundo fator de outro supervisor."},
                status=403,
            )
        if not segundo_fator.remover(alvo):
            return Response({"detail": "Esta conta não tem segundo fator ativo."}, status=400)
        revoke_all_sessions(alvo, motivo="segundo_fator_redefinido")
        bump_session_epoch(alvo.id)
        recuperacao.registrar_evento(
            EventoSeguranca.Tipo.SEGUNDO_FATOR_REDEFINIDO,
            alvo=alvo, autor=request.user, request=request,
        )
        emails.enviar_aviso_segundo_fator(alvo, "redefinido", por_quem=request.user)
        return Response({
            "detail": (
                f"Segundo fator de {alvo.username} redefinido. As sessões dele foram "
                "encerradas, e ele foi avisado por e-mail."
            )
        })

    @action(detail=True, methods=["post"], url_path="trocar-email")
    def trocar_email(self, request, pk=None):
        """Troca de e-mail — **assimétrica**, conforme quem é o alvo.

        O `email` saiu do PATCH genérico porque ele é a chave da recuperação de
        senha: quem o controla, controla a conta. Mas a regra não pode ser a
        mesma para todo mundo, porque o admin **é o dono da empresa** e as contas
        dos funcionários existem a partir dele.

        - **Alvo funcionário** (não-admin): a troca vale **na hora**. Exigir
          confirmação no endereço antigo travaria justamente o caso que motivou o
          D11 — e-mail digitado errado no cadastro, ou caixa que a pessoa não
          acessa mais: a confirmação iria para um endereço morto e ninguém nunca
          conseguiria corrigir. O dono administra essas contas por direito.
          Compensações: evento na trilha e aviso nos **dois** endereços.
        - **Alvo admin** (inclusive o próprio): exige **confirmação no endereço
          ANTIGO**. A conta do dono é o ponto único de comprometimento da empresa
          inteira — quem sequestrar a sessão dele não pode redirecionar o e-mail
          e, com isso, herdar a recuperação de senha de tudo.
        """
        alvo = self.get_object()
        novo = (request.data.get("email") or "").strip().lower()
        if not novo or "@" not in novo:
            return Response({"detail": "Informe um e-mail válido."}, status=400)
        if novo == (alvo.email or "").lower():
            return Response({"detail": "O e-mail informado é o atual."}, status=400)
        # Unicidade global do e-mail (ver `Usuario.email`): duas contas com o
        # mesmo endereço tornariam a recuperação ambígua.
        if Usuario.objects.filter(email__iexact=novo).exclude(pk=alvo.pk).exists():
            return Response({"detail": "Já existe conta com este e-mail."}, status=400)

        if not (alvo.is_tenant_admin or alvo.is_superuser):
            # Alvo funcionário: aplica direto (ver docstring). Não armamos o
            # cooldown de propósito — se armássemos, o dono corrigiria o e-mail
            # errado e a pessoa ainda ficaria 24 h sem conseguir recuperar a
            # senha, que é exatamente o travamento que queremos eliminar.
            antigo = alvo.email
            alvo.email = novo
            alvo.save(update_fields=["email"])
            recuperacao.registrar_evento(
                EventoSeguranca.Tipo.EMAIL_TROCA_CONFIRMADA,
                alvo=alvo, autor=request.user, request=request,
                de=recuperacao.mascarar_email(antigo),
                para=recuperacao.mascarar_email(novo),
                modo="direto_admin",
            )
            emails.enviar_aviso_email_trocado(alvo, antigo, novo, request.user)
            return Response({
                "detail": (
                    f"E-mail de {alvo.username} atualizado. Avisamos o endereço "
                    "anterior e o novo, e o evento ficou registrado na trilha."
                )
            })

        # Alvo admin (ou o próprio): a conta que dá acesso à empresa inteira só
        # muda de e-mail com confirmação na caixa que já era dela.
        claro, pendencia = recuperacao.abrir_troca_email(
            alvo, novo, solicitante=request.user, request=request
        )
        emails.enviar_confirmacao_troca_email(
            alvo, pendencia.email_antigo, novo, claro, settings.EMAIL_CHANGE_TTL_HORAS
        )
        return Response({
            "detail": (
                f"Esta conta é de administrador: enviamos um pedido de confirmação "
                f"para o e-mail ATUAL ({recuperacao.mascarar_email(pendencia.email_antigo)}). "
                "A troca só vale depois que ele for confirmado."
            )
        })


class PerfilViewSet(viewsets.ModelViewSet):
    queryset = Perfil.objects.select_related("tenant").all()
    serializer_class = PerfilSerializer
    permission_classes = [IsTenantAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        return qs if u.is_superuser else qs.filter(tenant_id=u.tenant_id)

    def perform_create(self, serializer):
        u = self.request.user
        serializer.save() if u.is_superuser else serializer.save(tenant=u.tenant)

    def perform_update(self, serializer):
        u = self.request.user
        serializer.save() if u.is_superuser else serializer.save(tenant=u.tenant)


class AcessoUsuarioModuloViewSet(viewsets.ModelViewSet):
    queryset = AcessoUsuarioModulo.objects.select_related("usuario", "modulo").all()
    serializer_class = AcessoUsuarioModuloSerializer
    permission_classes = [IsTenantAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        return qs if u.is_superuser else qs.filter(usuario__tenant_id=u.tenant_id)
