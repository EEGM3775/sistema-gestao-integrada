# backend/funcoesimpexp/acesso.py
"""IE.0 — a regra do §3 da planta, num lugar só: **acesso total ou nada**.

Só opera quem tem o conjunto INTEIRO de `permissoes_exigidas` do recurso. Meia
permissão bloqueia; permissão nenhuma idem. Não há operação parcial nem arquivo
com coluna capada.

Por que de conjunto, e não campo a campo em tempo de request: nas telas, o
mascaramento 9.C protege o campo e a página segue útil (CPF vira `•••123`). Num
arquivo, não — a planilha sai parecendo completa, viaja para fora do sistema e é
somada por quem não estava na tela e não tem como saber que a coluna foi capada.
Bloquear na entrada dá a mesma garantia, é previsível e não custa nada no
caminho quente, **desde que a declaração inclua a permissão de máscara de toda
coluna sensível** — obrigação registrada no contrato (`registro.Recurso`).

O backend não conhece o catálogo da IAM: as permissões chegam como lista plana na
claim `permissions` do JWT. Por isso o conjunto é declarado pelo módulo dono, que
conhece as próprias.
"""
from __future__ import annotations

from rest_framework.exceptions import PermissionDenied

from .registro import Recurso


def permissoes_faltantes(user, recurso: Recurso) -> tuple[str, ...]:
    """O que falta para esta pessoa operar este recurso. Vazio = pode."""
    if _privilegiado(user):
        return ()
    concedidas = set(getattr(user, "iam_permissions", None) or [])
    return tuple(p for p in recurso.permissoes_exigidas if p not in concedidas)


def pode_operar(user, recurso: Recurso) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return not permissoes_faltantes(user, recurso)


def exigir_acesso_total(user, recurso: Recurso) -> None:
    """403 nomeando o que falta — mensagem de erro tem de ser acionável.

    "Você não tem permissão" manda a pessoa abrir chamado; dizer *qual*
    permissão falta manda ela ao admin do tenant com o pedido pronto.
    """
    if not user or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Autenticação necessária.")
    faltam = permissoes_faltantes(user, recurso)
    if not faltam:
        return
    raise PermissionDenied(
        f"Importar e exportar '{recurso.rotulo}' exige acesso total ao recurso, e faltam: "
        f"{', '.join(faltam)}. Arquivo sai inteiro ou não sai — não há exportação parcial."
    )


def recursos_permitidos(user, recursos) -> tuple[Recurso, ...]:
    """Para o frontend sumir com o botão antes do clique (planta §10)."""
    return tuple(r for r in recursos if pode_operar(user, r))


def _privilegiado(user) -> bool:
    """Mesmo bypass que já vale em `RequirePermission` — um único modelo mental."""
    return bool(
        getattr(user, "is_tenant_admin", False)
        or getattr(user, "is_platform_admin", False)
        or getattr(user, "is_superuser", False)
    )
