# nucleo/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import Usuario, Perfil, Permissao, LogAtividadeUsuario, FailedTask


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'cpf', 'telefone', 'is_active', 'is_staff']
    list_filter = ['is_active', 'is_staff', 'is_superuser', 'perfil', 'date_joined']
    search_fields = ['username', 'first_name', 'last_name', 'email', 'cpf']
    readonly_fields = ['date_joined', 'last_login']
    ordering = ['username']
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Informações Pessoais'), {'fields': ('first_name', 'last_name', 'email', 'cpf', 'telefone')}),
        (_('Permissões'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'is_data_admin', 'perfil', 'groups', 'user_permissions')}),
        (_('Datas Importantes'), {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'cpf', 'password1', 'password2', 'perfil'),
        }),
    )
    
    filter_horizontal = ('groups', 'user_permissions')


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ['perfil_id', 'nome', 'descricao']
    search_fields = ['nome', 'descricao']
    readonly_fields = ['perfil_id']
    ordering = ['nome']
    
    fieldsets = (
        (_('Informações Básicas'), {
            'fields': ('perfil_id', 'nome', 'descricao')
        }),
        (_('Permissões'), {
            'fields': ('permissoes',)
        })
    )
    
    filter_horizontal = ['permissoes']


@admin.register(Permissao)
class PermissaoAdmin(admin.ModelAdmin):
    list_display = ['permissao_id', 'nome', 'codename']
    search_fields = ['nome', 'codename']
    readonly_fields = ['permissao_id']
    ordering = ['nome']
    
    fieldsets = (
        (_('Identificação'), {
            'fields': ('permissao_id', 'nome', 'codename')
        }),
    )


@admin.register(LogAtividadeUsuario)
class LogAtividadeUsuarioAdmin(admin.ModelAdmin):
    list_display = ['log_id', 'usuario', 'acao', 'entidade_alvo', 'alvo_id', 'timestamp']
    list_filter = ['acao', 'entidade_alvo', 'timestamp']
    search_fields = ['usuario__username', 'acao', 'entidade_alvo']
    readonly_fields = ['log_id', 'timestamp']
    ordering = ['-timestamp']
    
    fieldsets = (
        (_('Identificação'), {
            'fields': ('log_id', 'usuario', 'acao')
        }),
        (_('Detalhes'), {
            'fields': ('entidade_alvo', 'alvo_id', 'detalhes')
        }),
        (_('Timestamp'), {
            'fields': ('timestamp',)
        })
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
