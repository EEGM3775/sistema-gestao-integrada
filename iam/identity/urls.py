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
    # Interna (o gateway devolve 404): o PEP sem Redis pergunta se a sessão vale.
    path("auth/interno/sessao/<uuid:sid>/", views.SessaoInternaView.as_view(), name="sessao-interna"),
    # Fase 5 — o BFF: o gateway troca o cookie da sessão pelo access do serviço.
    path("auth/interno/bff/<str:servico>/", views.TokenDaSessaoView.as_view(), name="bff-token"),
    # Fase 6 — o step-up: provar quem é de novo antes do ato grave.
    path("auth/confirmar/", views.ConfirmarIdentidadeView.as_view(), name="confirmar-identidade"),
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
    # Remodelagem, fase 1 — segundo fator (acesso-e-permissoes.md §10.5). A
    # segunda etapa do login mora sob `auth/login/` de propósito: o gateway a
    # limita por IP como limita a senha.
    path(
        "auth/login/segundo-fator/",
        views.LoginSegundoFatorView.as_view(),
        name="login-segundo-fator",
    ),
    path(
        "auth/segundo-fator/cadastro/",
        views.CadastroSegundoFatorView.as_view(),
        name="segundo-fator-cadastro",
    ),
    path(
        "auth/segundo-fator/cadastro/confirmar/",
        views.ConfirmarCadastroSegundoFatorView.as_view(),
        name="segundo-fator-confirmar",
    ),
    path(
        "auth/segundo-fator/desativar/",
        views.DesativarSegundoFatorView.as_view(),
        name="segundo-fator-desativar",
    ),
    path(
        "auth/segundo-fator/codigos/",
        views.CodigosSegundoFatorView.as_view(),
        name="segundo-fator-codigos",
    ),
    path("auth/conta/seguranca/", views.SegurancaDaContaView.as_view(), name="conta-seguranca"),
    path("catalogo-permissoes/", views.CatalogoPermissoesView.as_view(), name="catalogo-permissoes"),
    # Fase 6 — o suporte da plataforma só entra com consentimento (§10.7).
    path("suporte/", views.SuporteDaEmpresaView.as_view(), name="suporte-da-empresa"),
    path(".well-known/jwks.json", views.JwksView.as_view(), name="jwks"),
    path("", include(router.urls)),
]
