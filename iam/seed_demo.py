"""Seed de demonstração da IAM (Fases 2 + 6).

Tenant 'demo' com os módulos drone/erp_financeiro/crm/rh assinados, e papéis
financeiro/operacional, para exercitar as DUAS camadas de acesso:
  - Entitlement de módulo (camada 1): quem tem o módulo no token.
  - RBAC por papel (camada 2): quem tem o papel.

Usuários:
  demo     / demo123     -> módulos: drone, erp_financeiro, crm, rh | papel: financeiro
  semdrone / semdrone123 -> módulos: erp_financeiro                 | papel: operacional

Rodar (no container):  docker compose exec -T iam python manage.py shell < iam/seed_demo.py
"""
from identity.models import (
    Tenant, Modulo, Usuario, AssinaturaTenant, AcessoUsuarioModulo, Perfil,
)

tenant, _ = Tenant.objects.get_or_create(slug="demo", defaults={"nome": "Empresa Demo"})

# --- Catálogo de módulos vendáveis ---
modulos = {}
for cod, nome in [
    ("drone", "Mapeamento por Drone"),
    ("erp_financeiro", "ERP Financeiro"),
    ("crm", "CRM"),
    ("rh", "Recursos Humanos"),
]:
    modulos[cod], _ = Modulo.objects.get_or_create(codigo=cod, defaults={"nome": nome})

# --- Assinaturas do tenant (a empresa contratou TODOS) ---
for cod in modulos:
    AssinaturaTenant.objects.get_or_create(
        tenant=tenant, modulo=modulos[cod],
        defaults={"status": AssinaturaTenant.Status.ATIVA},
    )

# --- Perfis (papéis) do tenant ---
financeiro, _ = Perfil.objects.get_or_create(tenant=tenant, nome="financeiro")
operacional, _ = Perfil.objects.get_or_create(tenant=tenant, nome="operacional")


def upsert_user(username, password, modulos_acesso, perfil):
    u, _ = Usuario.objects.get_or_create(
        username=username, defaults={"email": f"{username}@demo.com", "tenant": tenant}
    )
    u.tenant = tenant
    u.set_password(password)
    u.save()
    # Acesso por usuário (subconjunto dos módulos do tenant)
    u.acessos_modulo.all().delete()
    for cod in modulos_acesso:
        AcessoUsuarioModulo.objects.get_or_create(usuario=u, modulo=modulos[cod])
    u.perfis.set([perfil])
    return u


demo = upsert_user("demo", "demo123", ["drone", "erp_financeiro", "crm", "rh"], financeiro)
semdrone = upsert_user("semdrone", "semdrone123", ["erp_financeiro"], operacional)

print("SEED OK | tenant:", tenant.slug)
print("  demo     -> modulos:", demo.modulos_efetivos(), "| papeis:", demo.nomes_perfis())
print("  semdrone -> modulos:", semdrone.modulos_efetivos(), "| papeis:", semdrone.nomes_perfis())
