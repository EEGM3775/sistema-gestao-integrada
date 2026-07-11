import base64
import hashlib

from django.conf import settings
from rest_framework import viewsets
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
from .tokens import build_claims


# --- Autenticação / SSO ---

class LoginView(TokenObtainPairView):
    serializer_class = IamTokenObtainPairSerializer


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response({"detail": "refresh é obrigatório"}, status=400)
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return Response({"detail": "token inválido"}, status=400)
        return Response({"detail": "logout efetuado"}, status=205)


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
