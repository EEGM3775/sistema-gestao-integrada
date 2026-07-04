# nucleo/models.py
import uuid

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _


class Tenant(models.Model):
    """
    Espelho local do tenant (empresa-cliente) cuja autoridade é a IAM.
    O ERP é resource server: usuários e tenants são provisionados (JIT) a
    partir das claims do JWT da IAM. Ver docs/arquitetura.md (Fase 0.3).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(_("Slug"), max_length=100, unique=True)
    nome = models.CharField(_("Nome"), max_length=255)
    data_sincronizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Tenant")
        verbose_name_plural = _("Tenants")
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.slug})"

# ... (restante dos imports e modelos existentes) ...

class FailedTask(models.Model):
    """
    Atua como uma Dead Letter Queue para tarefas Celery que falharam permanentemente.
    """
    task_id = models.CharField(_("ID da Tarefa Celery"), max_length=36, unique=True)
    task_name = models.CharField(_("Nome da Tarefa"), max_length=255, db_index=True)
    args = models.JSONField(_("Argumentos"))
    kwargs = models.JSONField(_("Argumentos Chave-Valor"))
    exception = models.TextField(_("Exceção"))
    traceback = models.TextField(_("Traceback"))
    timestamp = models.DateTimeField(_("Timestamp da Falha"), auto_now_add=True)
    
    STATUS_CHOICES = [
        ('failed', 'Falhou'),
        ('resolved', 'Resolvido'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='failed',
        verbose_name=_("Status")
    )

    class Meta:
        verbose_name = _("Tarefa Falha")
        verbose_name_plural = _("Tarefas Falhas")
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.task_name} ({self.task_id})"

class PreCadastro(models.Model):
    """
    Armazena informações de contatos via WhatsApp que não foram
    encontrados no sistema para aprovação manual.
    """
    precadastro_id = models.AutoField(primary_key=True)
    nome_completo = models.CharField(_("Nome Completo"), max_length=255)
    telefone = models.CharField(_("Telefone"), max_length=20, unique=True)
    
    TIPO_INTERESSE_CHOICES = [
        ('cliente', 'Cliente'),
        ('fornecedor', 'Fornecedor'),
        ('candidato', 'Candidato a Vaga'),
        ('outro', 'Outro'),
    ]
    tipo_interesse = models.CharField(_("Tipo de Interesse"), max_length=20, choices=TIPO_INTERESSE_CHOICES)
    mensagem_inicial = models.TextField(_("Mensagem Inicial"), blank=True, null=True)
    
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('aprovado', 'Aprovado'),
        ('rejeitado', 'Rejeitado'),
    ]
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='pendente')
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Pré-Cadastro")
        verbose_name_plural = _("Pré-Cadastros")
        ordering = ['-data_criacao']

    def __str__(self):
        return f"{self.nome_completo} ({self.telefone})"

class Usuario(AbstractUser):
    """
    Espelho local do usuário provisionado JIT a partir das claims do JWT da IAM.
    Papéis (RBAC) e módulos (entitlement) vêm do token — não de tabelas locais.
    """
    cpf = models.CharField(_("CPF"), max_length=14, unique=True, null=True, blank=True)
    telefone = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("Telefone"))
    is_data_admin = models.BooleanField(default=False, verbose_name=_("Administrador de Dados"))
    tenant = models.ForeignKey('Tenant', on_delete=models.CASCADE, null=True, blank=True, related_name='usuarios', verbose_name=_("Tenant"))
    is_tenant_admin = models.BooleanField(default=False, verbose_name=_("Administrador do Tenant"))

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name = _("Usuário")
        verbose_name_plural = _("Usuários")
        ordering = ['username']

    def __str__(self):
        return self.username


class ConfiguracaoArquivos(models.Model):
    """
    Configuração de upload de arquivos por tenant, editável pelo administrador.
    Use tenant=null para o padrão global (fallback).
    """
    tenant = models.OneToOneField(
        'Tenant', on_delete=models.CASCADE, null=True, blank=True,
        related_name='configuracao_arquivos', verbose_name=_("Tenant"),
    )
    max_tamanho_mb = models.PositiveSmallIntegerField(
        _("Tamanho máximo (MB)"), default=10,
    )
    tipos_aceitos = models.JSONField(
        _("Tipos MIME aceitos"),
        default=list,
        help_text=_(
            'Ex: ["application/pdf","image/jpeg","image/png"]. '
            'Lista vazia = todos os tipos.'
        ),
    )

    class Meta:
        verbose_name = _("Configuração de Arquivos")
        verbose_name_plural = _("Configurações de Arquivos")

    def __str__(self) -> str:
        tenant_label = self.tenant.nome if self.tenant else 'Global'
        return f"Config Arquivos — {tenant_label} (max {self.max_tamanho_mb} MB)"


class LogAtividadeUsuario(models.Model):
    """
    Registra as ações importantes realizadas pelos usuários no sistema.
    """
    log_id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, verbose_name=_("Usuário"))
    acao = models.CharField(max_length=255, verbose_name=_("Ação Realizada"))
    entidade_alvo = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Entidade Alvo"))
    alvo_id = models.PositiveIntegerField(blank=True, null=True, verbose_name=_("ID do Alvo"))
    detalhes = models.JSONField(blank=True, null=True, verbose_name=_("Detalhes"))
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_("Timestamp"))

    class Meta:
        verbose_name = _("Log de Atividade do Usuário")
        verbose_name_plural = _("Logs de Atividades dos Usuários")
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp} - {self.usuario}: {self.acao}"
