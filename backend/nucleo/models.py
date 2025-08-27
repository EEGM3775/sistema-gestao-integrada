# nucleo/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

# ... (restante dos imports e modelos existentes) ...

class FailedTask(models.Model):
    """
    Atua como uma Dead Letter Queue para tarefas Celery que falharam permanentemente.
    """
    task_id = models.PositiveIntegerField(_("ID da Tarefa Celery"), unique=True)
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
    Modelo de usuário customizado, estendendo o AbstractUser do Django.
    """
    cpf = models.CharField(_("CPF"), max_length=14, unique=True, null=True, blank=True)
    telefone = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("Telefone"))
    is_data_admin = models.BooleanField(default=False, verbose_name=_("Administrador de Dados"))
    perfil = models.ForeignKey('Perfil', on_delete=models.SET_NULL, null=True, blank=True, related_name='usuarios', verbose_name=_("Perfil"))

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name = _("Usuário")
        verbose_name_plural = _("Usuários")
        ordering = ['username']

    def __str__(self):
        return self.username


class Perfil(models.Model):
    """
    Define os perfis de usuário (grupos de permissões) no sistema.
    """
    perfil_id = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=100, unique=True, verbose_name=_("Nome do Perfil"))
    descricao = models.TextField(blank=True, null=True, verbose_name=_("Descrição"))
    permissoes = models.ManyToManyField('Permissao', related_name='perfis', verbose_name=_("Permissões"))

    class Meta:
        verbose_name = _("Perfil")
        verbose_name_plural = _("Perfis")
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Permissao(models.Model):
    """
    Define as permissões granulares que podem ser associadas a um perfil.
    """
    permissao_id = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=100, unique=True, verbose_name=_("Nome da Permissão"))
    codename = models.CharField(max_length=100, unique=True, help_text=_("Código único para a permissão, ex: 'pode_criar_usuario'"))

    class Meta:
        verbose_name = _("Permissão")
        verbose_name_plural = _("Permissões")
        ordering = ['nome']

    def __str__(self):
        return self.nome


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
