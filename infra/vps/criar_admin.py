"""Cria a empresa e o primeiro administrador no VPS (IAM). NÃO usa as senhas da demo.

Rodar via `bash infra/vps/criar-admin.sh` (ele injeta as variáveis e o container iam).
Variáveis: SGI_TENANT_SLUG, SGI_TENANT_NOME, SGI_ADMIN_USER, SGI_ADMIN_EMAIL, SGI_ADMIN_SENHA.

Cria o tenant com o plano `empresarial` e todos os módulos assinados, o administrador da
empresa (`is_tenant_admin`, herda o catálogo inteiro) e roda o `sync_authz`. O backend espelha
o tenant pelo id no primeiro login. O segundo fator do admin é cadastrado no primeiro acesso.
Idempotente: rodar de novo troca a senha do mesmo usuário.
"""
import os
import uuid

from django.core.management import call_command
from identity.models import AssinaturaTenant, Modulo, Tenant, Usuario

slug = os.environ["SGI_TENANT_SLUG"]
nome = os.environ["SGI_TENANT_NOME"]
username = os.environ["SGI_ADMIN_USER"]
email = os.environ["SGI_ADMIN_EMAIL"]
senha = os.environ["SGI_ADMIN_SENHA"]

# Mesmo catálogo do seed da demo: os módulos são globais; quem assina é o tenant.
MODULOS = [
    ("erp_financeiro", "ERP Financeiro"), ("crm", "CRM"), ("rh", "Recursos Humanos"),
    ("scm", "Suprimentos (SCM)"), ("sil", "Estoque & Logística (SIL)"),
    ("orcamento", "Orçamento de Obra"), ("maps", "Mapas & Território"),
    ("prancheta", "Prancheta — Projeto em Campo"),
    ("pdca", "PDCA — Planejamento & Melhoria Contínua"),
]  # sem `drone`: o produto não roda neste ambiente

# Id derivado do slug, como no seed: o backend cria o espelho por este id.
tenant, _ = Tenant.objects.get_or_create(
    slug=slug,
    defaults={"id": uuid.uuid5(uuid.NAMESPACE_DNS, f"sgi.tenant.{slug}"), "nome": nome, "plano": "empresarial"},
)
for codigo, nome_modulo in MODULOS:
    modulo, _ = Modulo.objects.get_or_create(codigo=codigo, defaults={"nome": nome_modulo})
    AssinaturaTenant.objects.get_or_create(
        tenant=tenant, modulo=modulo, defaults={"status": AssinaturaTenant.Status.ATIVA}
    )

call_command("sync_authz", all_tenants=True)

usuario, criado = Usuario.objects.get_or_create(
    username=username, defaults={"email": email, "tenant": tenant}
)
usuario.tenant = tenant
usuario.email = email
usuario.is_tenant_admin = True
usuario.set_password(senha)
usuario.save()

print(f"OK | empresa '{tenant.slug}' (plano {tenant.plano}) | admin '{username}' "
      f"{'criado' if criado else 'atualizado'} | módulos: {len(MODULOS)}")
