"""Seed de demonstração da IAM (Fases 2 + 6 + 8.5 + 9.A).

Tenant 'demo' com os módulos drone/erp_financeiro/crm/rh assinados, e os papéis
de fábrica provisionados (Fase 9), para exercitar as DUAS camadas de acesso:
  - Entitlement de módulo (camada 1): quem tem o módulo no token.
  - RBAC por papel/permissão (camada 2): o papel compõe permissões do catálogo
    (identity/catalog.py); o JWT passa a carregar `permissions`.

Um SEGUNDO tenant 'acme' (Fase 8.5) com o módulo drone existe só para provar o
isolamento entre tenants no drone.

Papéis de fábrica: criados por `sync_authz` a partir dos templates do catálogo
(diretoria, rh_gestor, rh_medico, rh_financeiro, financeiro, tesouraria, fiscal,
comercial, engenharia, campo, drone_analista, auditor, gestor_lixo, operacional).

Usuários:
  demo     / demo123     -> tenant demo | módulos: drone,erp,crm,rh,scm,sil | papéis: financeiro + RH + suprimentos + almoxarife
  semdrone / semdrone123 -> tenant demo | módulos: erp_financeiro    | papel: operacional (restrito — exercita mascaramento)
  acme     / acme123     -> tenant acme | módulos: drone             | papel: operacional

Rodar (no container):  docker compose exec -T iam python manage.py shell < iam/seed_demo.py
"""
import uuid

from django.core.management import call_command
from identity.models import (
    Tenant, Modulo, Usuario, AssinaturaTenant, AcessoUsuarioModulo, Perfil,
)

# IDs determinísticos e ESTÁVEIS dos tenants de demonstração. O backend espelha o
# tenant da IAM POR ID (nucleo.authentication._sync_tenant → get_or_create(id=<jwt.tenant_id>)):
# num ambiente greenfield (staging/prod), se o backend nascer com outro id, o 1º login
# colide em slug='demo' e responde 500. Derivar por uuid5 do MESMO nome garante o mesmo
# valor aqui e no backend/seed_demo_data.py, sem literal duplicado que possa divergir.
DEMO_TENANT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "sgi.tenant.demo")
ACME_TENANT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "sgi.tenant.acme")

# --- Catálogo de módulos vendáveis (global, compartilhado entre tenants) ---
modulos = {}
for cod, nome in [
    ("drone", "Mapeamento por Drone"),
    ("erp_financeiro", "ERP Financeiro"),
    ("crm", "CRM"),
    ("rh", "Recursos Humanos"),
    ("scm", "Suprimentos (SCM)"),
    ("sil", "Estoque & Logística (SIL)"),
    ("orcamento", "Orçamento de Obra"),
]:
    modulos[cod], _ = Modulo.objects.get_or_create(codigo=cod, defaults={"nome": nome})


def assinar(tenant, codigos):
    """A empresa contrata (assina) os módulos informados."""
    for cod in codigos:
        AssinaturaTenant.objects.get_or_create(
            tenant=tenant, modulo=modulos[cod],
            defaults={"status": AssinaturaTenant.Status.ATIVA},
        )


def upsert_user(tenant, username, password, modulos_acesso, papeis, is_admin=False):
    u, _ = Usuario.objects.get_or_create(
        username=username, defaults={"email": f"{username}@{tenant.slug}.com", "tenant": tenant}
    )
    u.tenant = tenant
    u.is_tenant_admin = is_admin
    u.set_password(password)
    u.save()
    # Acesso por usuário (subconjunto dos módulos do tenant)
    u.acessos_modulo.all().delete()
    for cod in modulos_acesso:
        AcessoUsuarioModulo.objects.get_or_create(usuario=u, modulo=modulos[cod])
    # Papéis (Perfil por tenant, já provisionados pelo sync_authz)
    perfis = list(Perfil.objects.filter(tenant=tenant, nome__in=papeis))
    u.perfis.set(perfis)
    return u


# --- Tenants (empresas) ---
# D24 — o `plano` é EXPLÍCITO desde o seed. Tenant sem plano cai no `free`
# (1 seat, 2 obras) e, com a trava de quota ligada, o dev não conseguiria criar o
# segundo usuário nem a terceira obra — a demo pareceria quebrada. Os dois seeds
# (este e o do backend) têm de concordar, pela mesma razão do D10: quando eles
# divergem, o defeito só aparece num ambiente greenfield.
#
# `demo` fica em `profissional` para exercitar o produto inteiro; `acme` fica no
# `free` de propósito, para que exista sempre um tenant onde a parede de quota é
# alcançável à mão, sem reconfigurar nada.
tenant, _ = Tenant.objects.get_or_create(
    slug="demo", defaults={"id": DEMO_TENANT_ID, "nome": "Empresa Demo", "plano": "profissional"}
)
if tenant.plano != "profissional":  # idempotente sobre banco já semeado
    tenant.plano = "profissional"
    tenant.save(update_fields=["plano"])
assinar(tenant, modulos.keys())

acme_tenant, _ = Tenant.objects.get_or_create(
    slug="acme", defaults={"id": ACME_TENANT_ID, "nome": "Empresa Acme", "plano": "free"}
)
assinar(acme_tenant, ["drone"])

# --- Catálogo de permissões + papéis de fábrica nos dois tenants (Fase 9.A) ---
call_command("sync_authz", all_tenants=True)

# --- Usuários e seus papéis ---
demo = upsert_user(
    tenant, "demo", "demo123", ["drone", "erp_financeiro", "crm", "rh", "scm", "sil", "orcamento"],
    # Power-user: papéis cobrindo todos os módulos do tenant (erp, crm, obras, drone, rh, scm,
    # sil, orcamento).
    ["financeiro", "tesouraria", "fiscal", "comercial", "engenharia",
     "drone_analista", "rh_gestor", "rh_medico", "rh_financeiro", "suprimentos", "almoxarife",
     "orcamentista"],
)
semdrone = upsert_user(tenant, "semdrone", "semdrone123", ["erp_financeiro"], ["operacional"])
acme = upsert_user(acme_tenant, "acme", "acme123", ["drone"], ["operacional"])
# Admin do tenant 'demo': gere papéis/personas e permissões na tela de Administração.
admin = upsert_user(
    tenant, "admin", "admin123", ["drone", "erp_financeiro", "crm", "rh"], [], is_admin=True
)

print("SEED OK | tenants:", tenant.slug, "+", acme_tenant.slug)
print("  demo     -> modulos:", demo.modulos_efetivos(), "| papeis:", demo.nomes_perfis())
print("            permissoes:", len(demo.permissoes_efetivas()), "codigos")
print("  admin    -> tenant_admin:", admin.is_tenant_admin, "| permissoes:", len(admin.permissoes_efetivas()))
print("  semdrone -> modulos:", semdrone.modulos_efetivos(), "| papeis:", semdrone.nomes_perfis())
print("  acme     -> modulos:", acme.modulos_efetivos(), "| papeis:", acme.nomes_perfis())
