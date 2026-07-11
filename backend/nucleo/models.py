# nucleo/models.py
import uuid

from django.db import IntegrityError, models
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
    """Log OPERACIONAL (telemetria) — ciclo de vida de tasks Celery
    (`signals.py`) e sink de microsserviços (`LogInternoView`).

    **Demovido na Fase 9.E:** a *trilha de auditoria sensível* (RH/financeiro/
    LGPD, imutável e por-tenant) passou para `AuditLog`. Este modelo é **mutável**
    (o `task_postrun` atualiza a linha de início) e **não é tenant-scoped**
    (tasks de sistema não têm tenant) — por isso não serve como trilha LGPD. A API
    de leitura `/api/logs-atividade/` foi removida (use `/api/auditoria/`); a
    remoção do modelo e a migração da telemetria para logs estruturados são da
    **Fase 10** (observabilidade).
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


from datetime import timedelta

from django.utils import timezone
from nucleo.tenancy import TenantScopedModel


class IncidenteLGPD(TenantScopedModel):
    """Incidente de segurança com dado pessoal (Fase 9.D — LGPD art. 48).

    Fluxo com trava de falso-positivo: um incidente nasce **pendente**; só o
    **dono da plataforma** (superuser da IAM) o **confirma** (aí começa o prazo
    de 72h para notificar a ANPD) ou o **descarta** (falso positivo). Isso evita
    notificação automática indevida à ANPD.
    """

    class Status(models.TextChoices):
        PENDENTE = "pendente", _("Pendente de confirmação")
        CONFIRMADO = "confirmado", _("Confirmado (prazo ANPD correndo)")
        DESCARTADO = "descartado", _("Descartado (falso positivo)")
        NOTIFICADO = "notificado", _("ANPD notificada")

    descricao = models.TextField(_("Descrição do incidente"))
    dados_afetados = models.TextField(_("Dados/titulares afetados"), blank=True, default="")
    detectado_em = models.DateTimeField(_("Detectado em"), default=timezone.now)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
    reportado_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="incidentes_reportados",
    )
    confirmado_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="incidentes_confirmados",
    )
    confirmado_em = models.DateTimeField(null=True, blank=True)
    prazo_anpd = models.DateTimeField(null=True, blank=True, help_text="confirmado_em + 72h")
    notificado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Incidente LGPD")
        verbose_name_plural = _("Incidentes LGPD")
        ordering = ["-detectado_em"]

    def __str__(self):
        return f"[{self.status}] {self.descricao[:40]}"

    def confirmar(self, usuario):
        """Dono confirma o incidente: inicia o prazo de 72h para a ANPD."""
        agora = timezone.now()
        self.status = self.Status.CONFIRMADO
        self.confirmado_por = usuario
        self.confirmado_em = agora
        self.prazo_anpd = agora + timedelta(hours=72)
        self.save(update_fields=["status", "confirmado_por", "confirmado_em", "prazo_anpd"])

    def descartar(self, usuario):
        self.status = self.Status.DESCARTADO
        self.confirmado_por = usuario
        self.confirmado_em = timezone.now()
        self.save(update_fields=["status", "confirmado_por", "confirmado_em"])

    def marcar_notificado(self):
        self.status = self.Status.NOTIFICADO
        self.notificado_em = timezone.now()
        self.save(update_fields=["status", "notificado_em"])


class AuditLog(TenantScopedModel):
    """Trilha de auditoria imutável (Fase 9.E) — *append-only*.

    Registra QUEM fez O QUÊ em QUAL objeto e QUANDO nas operações sensíveis de
    **RH** e **financeiro** (rastreabilidade LGPD). A linha nunca é alterada:
    `save()` rejeita atualização, `delete()` é bloqueado no nível do modelo, o
    `AuditLogViewSet` é *read-only* (a API não expõe verbo de escrita) e a RLS
    fail-closed (migration companion) isola por tenant. Imutabilidade forte no
    banco (trigger que barra UPDATE/DELETE) fica como reforço opcional.

    `detalhes` guarda **contexto não-PII** (ex.: valor da baixa, origem, status
    novo, campos alterados) — nunca o valor de um campo sensível, para não
    recriar em texto puro o que a 9.C ([field_masking.py](field_masking.py))
    mascara. Ver [auditoria.py](auditoria.py) para o helper e o mixin de ViewSet.
    """

    class Acao(models.TextChoices):
        CRIAR = "criar", _("Criação")
        ATUALIZAR = "atualizar", _("Atualização")
        EXCLUIR = "excluir", _("Exclusão")
        BAIXA = "baixa", _("Baixa financeira")
        EMITIR_NF = "emitir_nf", _("Emissão de NF")
        GERAR_COBRANCA = "gerar_cobranca", _("Geração de cobrança")
        EXPORTAR_LGPD = "exportar_lgpd", _("Exportação LGPD (portabilidade)")
        ANONIMIZAR_LGPD = "anonimizar_lgpd", _("Anonimização LGPD (esquecimento)")
        VISUALIZAR_PII = "visualizar_pii", _("Visualização de PII")

    # FK "congelado": db_constraint=False + DO_NOTHING → excluir um usuário NÃO
    # dispara UPDATE nesta tabela (que o trigger de imutabilidade da migration
    # 0017 barraria). A identidade de QUEM agiu fica durável em `usuario_nome`.
    usuario = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.DO_NOTHING,
        db_constraint=False, related_name="auditorias", verbose_name=_("Usuário"),
    )
    usuario_nome = models.CharField(_("Usuário (rótulo)"), max_length=150, blank=True, default="")
    acao = models.CharField(_("Ação"), max_length=32, choices=Acao.choices)
    modelo = models.CharField(_("Modelo"), max_length=100)
    objeto_id = models.CharField(_("ID do objeto"), max_length=64, blank=True, default="")
    detalhes = models.JSONField(_("Detalhes (não-PII)"), null=True, blank=True)
    timestamp = models.DateTimeField(_("Timestamp"), auto_now_add=True)

    class Meta:
        verbose_name = _("Registro de Auditoria")
        verbose_name_plural = _("Trilha de Auditoria")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["tenant", "modelo", "objeto_id"], name="audit_tenant_obj_idx"),
            models.Index(fields=["tenant", "timestamp"], name="audit_tenant_ts_idx"),
        ]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.usuario_nome} {self.acao} {self.modelo}#{self.objeto_id}"

    def save(self, *args, **kwargs):
        # Append-only: uma linha de auditoria nunca é atualizada. `_state.adding`
        # é True só no primeiro INSERT; qualquer save posterior é rejeitado.
        if not self._state.adding:
            raise IntegrityError("AuditLog é imutável: atualização não permitida.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise IntegrityError("AuditLog é imutável: exclusão não permitida.")
