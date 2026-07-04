from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    AcessoUsuarioModulo,
    AssinaturaTenant,
    Modulo,
    Perfil,
    Permissao,
    Tenant,
    Usuario,
)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "status", "data_criacao")
    search_fields = ("nome", "slug", "cnpj")
    list_filter = ("status",)


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("username", "email", "tenant", "is_tenant_admin", "is_active")
    list_filter = ("tenant", "is_tenant_admin", "is_active", "is_superuser")
    fieldsets = UserAdmin.fieldsets + (
        ("Plataforma", {"fields": ("tenant", "is_tenant_admin", "perfis")}),
    )


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ("nome", "tenant")
    list_filter = ("tenant",)
    filter_horizontal = ("permissoes",)


@admin.register(Modulo)
class ModuloAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nome")
    search_fields = ("codigo", "nome")


@admin.register(AssinaturaTenant)
class AssinaturaTenantAdmin(admin.ModelAdmin):
    list_display = ("tenant", "modulo", "status", "inicio", "fim")
    list_filter = ("status", "modulo")


admin.site.register(Permissao)
admin.site.register(AcessoUsuarioModulo)
