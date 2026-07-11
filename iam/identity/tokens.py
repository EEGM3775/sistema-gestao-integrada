"""Claims do JWT emitido pela IAM e consumido por todos os produtos."""


def build_claims(user):
    """Claims customizadas que viajam no access/refresh token.

    `sub`=username é lido pelo funcoesODM (Java) para buscar/provisionar o
    usuário; `tenant_id` dá o isolamento; `modules` carrega os entitlements.
    """
    tenant = user.tenant
    return {
        "sub": user.username,
        "email": user.email,
        "tenant_id": str(tenant.id) if tenant else None,
        "tenant_slug": tenant.slug if tenant else None,
        "roles": user.nomes_perfis(),
        "permissions": user.permissoes_efetivas(),
        "modules": user.modulos_efetivos(),
        "is_tenant_admin": user.is_tenant_admin,
        "is_platform_admin": user.is_superuser,
    }
