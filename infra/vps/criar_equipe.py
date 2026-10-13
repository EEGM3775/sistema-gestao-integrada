"""Cria a equipe de avaliação de uma empresa no VPS (IAM): um usuário por área.

Rodar via `bash infra/vps/criar-equipe-avaliacao.sh` — ele roda antes o `criar_admin.py`
(empresa, módulos assinados, `sync_authz` e o `admin@<slug>`) e depois este arquivo.
Variáveis: SGI_TENANT_SLUG, SGI_SENHA.

Cada área vira `<area>@<slug>` com os módulos e os papéis de fábrica da tabela abaixo
(os papéis são os templates de `identity/catalog.py`, já provisionados pelo `sync_authz`).
O e-mail é `<area>@<slug>.invalid`: conta de avaliação não recupera senha por e-mail.
Idempotente: rodar de novo regrava senha, módulos e papéis dos mesmos usuários.
"""
import os

from identity.models import AcessoUsuarioModulo, Modulo, Perfil, Tenant, Usuario

slug = os.environ["SGI_TENANT_SLUG"]
senha = os.environ["SGI_SENHA"]

# área -> (módulos que o usuário usa, papéis de fábrica). Quem apura a medição
# (`gestor_contratos`, em obras) não a atesta: o atesto fica com o admin.
EQUIPE = {
    "contas": (["erp_financeiro"], ["financeiro", "tesouraria", "fiscal"]),
    "obras": (
        ["pdca", "prancheta", "maps", "orcamento"],
        ["engenharia", "planejador", "gestor_contratos", "tecnico_qualidade", "tecnico_seguranca"],
    ),
    "engenharia": (["orcamento", "prancheta", "maps"], ["orcamentista", "projetista", "topografo"]),
    "compras": (["scm", "sil"], ["suprimentos", "almoxarife"]),
    "carteira": (["crm", "erp_financeiro"], ["comercial", "tesouraria"]),
}

tenant = Tenant.objects.get(slug=slug)
contratados = set(tenant.modulos_ativos())

for area, (modulos, papeis) in EQUIPE.items():
    username = f"{area}@{slug}"
    faltam = set(modulos) - contratados
    if faltam:
        raise SystemExit(f"{username}: a empresa não assina {sorted(faltam)}")
    perfis = list(Perfil.objects.filter(tenant=tenant, nome__in=papeis))
    if len(perfis) != len(papeis):
        raise SystemExit(f"{username}: papéis ausentes no tenant — rode o sync_authz")

    usuario, criado = Usuario.objects.get_or_create(
        username=username, defaults={"email": f"{area}@{slug}.invalid", "tenant": tenant}
    )
    if usuario.tenant_id != tenant.id:
        raise SystemExit(f"{username} já existe em outra empresa")
    usuario.is_tenant_admin = False
    usuario.is_active = True
    usuario.set_password(senha)
    usuario.save()
    usuario.acessos_modulo.exclude(modulo__codigo__in=modulos).delete()
    for modulo in Modulo.objects.filter(codigo__in=modulos):
        AcessoUsuarioModulo.objects.get_or_create(usuario=usuario, modulo=modulo)
    usuario.perfis.set(perfis)

    print(f"OK | {username} {'criado' if criado else 'atualizado'} | módulos: "
          f"{sorted(usuario.modulos_efetivos())} | papéis: {sorted(usuario.nomes_perfis())}")
