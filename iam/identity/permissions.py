from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import SAFE_METHODS, BasePermission

from funcoesautorizacao import confirmacao
from payment.planos import (
    CONFIRMACAO_JANELA_MAX_MIN,
    CONFIRMACAO_JANELA_MIN_MIN,
    CONFIRMACAO_JANELA_PADRAO_MIN,
)


class IsPlatformAdmin(BasePermission):
    """Administrador da plataforma (superuser) — gere tenants/módulos/assinaturas."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class IsTenantAdmin(BasePermission):
    """Administrador do próprio tenant — gere usuários/perfis/acessos do tenant."""

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_tenant_admin or u.is_superuser))


# ---------------------------------------------------------------------------
# Fase 6 — step-up no ato que muda quem pode (`plataforma.papel.gerir`, classe C)
# ---------------------------------------------------------------------------


class ConfirmacaoNecessaria(APIException):
    """401 com o desafio da RFC 9470: a tela pede a confirmação e refaz o pedido."""

    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = confirmacao.CODIGO

    def __init__(self, janela_s: int):
        super().__init__(detail=confirmacao.corpo(janela_s))
        # O `exception_handler` do DRF põe isto no `WWW-Authenticate`.
        self.auth_header = confirmacao.desafio(janela_s)


def janela_da_pessoa(usuario) -> int:
    return confirmacao.janela_em_segundos(
        getattr(usuario, "janela_confirmacao_min", None), CONFIRMACAO_JANELA_PADRAO_MIN,
        CONFIRMACAO_JANELA_MIN_MIN, CONFIRMACAO_JANELA_MAX_MIN,
    )


def auth_time_do_pedido(request):
    """Quando a sessão deste pedido provou quem é pela última vez: da linha da
    sessão (navegador) ou do token (Bearer da IAM)."""
    from .models import Sessao

    if isinstance(request.auth, Sessao):
        return int(request.auth.auth_time.timestamp()) if request.auth.auth_time else None
    try:
        return request.auth.get("auth_time") if request.auth is not None else None
    except AttributeError:
        return None


def exigir_confirmacao_recente(request) -> None:
    janela = janela_da_pessoa(request.user)
    if not confirmacao.recente(auth_time_do_pedido(request), janela):
        raise ConfirmacaoNecessaria(janela)


class AtoGraveConfirmado(BasePermission):
    """A escrita deste recurso muda quem pode — papel, acesso a módulo, admin —
    e pede autenticação recente (§10.5, §10.8 classe C). Leitura passa."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        exigir_confirmacao_recente(request)
        return True


class PapelDoUsuarioConfirmado(BasePermission):
    """No cadastro de usuário, só a escrita que mexe no papel ou na flag de admin
    é ato grave; trocar o nome ou desativar alguém não pede confirmação."""

    CAMPOS = frozenset({"perfis", "is_tenant_admin"})

    def has_permission(self, request, view):
        if getattr(view, "action", None) not in ("create", "update", "partial_update"):
            return True
        dados = request.data if hasattr(request.data, "keys") else {}
        if self.CAMPOS & set(dados.keys()):
            exigir_confirmacao_recente(request)
        return True
