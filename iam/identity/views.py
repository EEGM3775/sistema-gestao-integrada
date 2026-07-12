import base64
import hashlib
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

from .models import (
    AcessoUsuarioModulo,
    AssinaturaTenant,
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
from .tokens import (
    access_with_claims,
    build_claims,
    cookie_max_age,
    issue_refresh,
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


def _corpo_sessao(user, access) -> dict:
    """Corpo devolvido no login: access + identidade + entitlements (sem refresh)."""
    tenant = user.tenant
    return {
        "access": str(access),
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


class LoginView(TokenObtainPairView):
    serializer_class = IamTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # valida credenciais → 401 se erradas
        user = serializer.user
        remember = bool(request.data.get("remember"))

        refresh = issue_refresh(user, remember=remember)
        resp = Response(_corpo_sessao(user, access_with_claims(refresh, user)))
        # Sem "manter conectado" → cookie de sessão (some ao fechar o navegador/
        # desligar o PC → novo login). Com → persistente (sobrevive ao reboot).
        set_refresh_cookie(resp, str(refresh), cookie_max_age(refresh), persistent=remember)
        return resp


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
        cap = settings.SESSION_ABS_CAP if remember else settings.SESSION_SHORT
        if now - sst > int(cap.total_seconds()):
            return falha("Sessão expirada (tempo máximo atingido).", token=old)

        try:
            user = Usuario.objects.get(id=old["user_id"])
        except Usuario.DoesNotExist:
            return falha("Usuário inexistente.", token=old)
        if not user.is_active:
            return falha("Usuário inativo.", token=old)

        # Rotação: invalida o antigo e emite um novo preservando o início da sessão.
        try:
            old.blacklist()
        except (AttributeError, TokenError):
            pass
        novo = issue_refresh(user, remember=remember, sst=sst)
        resp = Response({"access": str(access_with_claims(novo, user))})
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
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        return resp


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

        # Preserva o "lembrar" da sessão atual para a nova sessão deste dispositivo.
        remember = False
        raw = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if raw:
            try:
                remember = bool(RefreshToken(raw).get("rem"))
            except TokenError:
                pass

        user.set_password(nova)
        user.save(update_fields=["password"])
        revoke_all_sessions(user)  # derruba TODAS as sessões (inclui a atual)

        # Reemite uma sessão nova só para quem trocou a senha (não é deslogado).
        refresh = issue_refresh(user, remember=remember)
        resp = Response({
            "detail": "Senha alterada. As outras sessões foram encerradas.",
            "access": str(access_with_claims(refresh, user)),
        })
        set_refresh_cookie(resp, str(refresh), cookie_max_age(refresh), persistent=remember)
        return resp


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        return Response(
            {"id": str(u.id), "username": u.username, "email": u.email, **build_claims(u)}
        )


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def jwk_kid(public_pem: str) -> str:
    """Identificador estável da chave (thumbprint curto do PEM público)."""
    return hashlib.sha256(public_pem.encode("utf-8")).hexdigest()[:16]


class JwksView(APIView):
    """JWKS: publica a chave pública RSA para validação por qualquer serviço.

    /.well-known/jwks.json — usado pelos validadores (ERP, drone, microsserviços)
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
    queryset = Usuario.objects.select_related("tenant").all()
    serializer_class = UsuarioSerializer
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

    @action(detail=True, methods=["post"], url_path="redefinir-senha")
    def redefinir_senha(self, request, pk=None):
        """Admin redefine a senha de um usuário — **exigindo a senha atual** dele
        (a recuperação/esqueci-minha-senha, sem a antiga, é etapa futura). Verifica
        a senha atual do alvo, aplica a nova e encerra todas as sessões dele."""
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
        revoke_all_sessions(alvo)
        return Response({"detail": "Senha redefinida. As sessões do usuário foram encerradas."})


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
