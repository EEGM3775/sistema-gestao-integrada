from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("tenants", views.TenantViewSet, basename="tenant")
router.register("modulos", views.ModuloViewSet, basename="modulo")
router.register("assinaturas", views.AssinaturaTenantViewSet, basename="assinatura")
router.register("permissoes", views.PermissaoViewSet, basename="permissao")
router.register("usuarios", views.UsuarioViewSet, basename="usuario")
router.register("perfis", views.PerfilViewSet, basename="perfil")
router.register("acessos-modulo", views.AcessoUsuarioModuloViewSet, basename="acessomodulo")

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/refresh/", views.RefreshView.as_view(), name="refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/service-token/", views.ServiceTokenView.as_view(), name="service-token"),
    path("auth/senha/", views.ChangePasswordView.as_view(), name="change-password"),
    # D11 — recuperação de senha. Públicas (sem autenticação): quem esqueceu a
    # senha, por definição, não consegue se autenticar. O gateway aplica rate
    # limit nestes paths, como já faz no login.
    path("auth/senha/esqueci/", views.EsqueciSenhaView.as_view(), name="esqueci-senha"),
    path(
        "auth/senha/redefinir/",
        views.RedefinirSenhaComTokenView.as_view(),
        name="redefinir-senha-token",
    ),
    path(
        "auth/email/confirmar/",
        views.ConfirmarTrocaEmailView.as_view(),
        name="confirmar-troca-email",
    ),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("catalogo-permissoes/", views.CatalogoPermissoesView.as_view(), name="catalogo-permissoes"),
    path(".well-known/jwks.json", views.JwksView.as_view(), name="jwks"),
    path("", include(router.urls)),
]
