# nucleo/models.py
import uuid

from django.db import IntegrityError, models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _


class Tenant(models.Model):
    """
    Espelho local do tenant (empresa-cliente) cuja autoridade é a IAM.
    O backend é resource server: usuários e tenants são provisionados (JIT) a
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
        # R12 do `funcoesimpexp`: exportação de dado pelo motor de plataforma.
        # Separada da `EXPORTAR_LGPD` de propósito — aquela é o direito do
        # titular exercido sobre os dados dele; esta é a operação corriqueira de
        # levar um recorte para o Excel. Misturá-las tornaria ilegível o
        # relatório que a LGPD pede, que é justamente o das primeiras.
        EXPORTAR_DADOS = "exportar_dados", _("Exportação de dados (import/export)")

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


class Notificacao(TenantScopedModel):
    """Notificação in-app do centro de notificações (sino do topbar) — Fase 9
    (Calendário, Fatia C). Infra **de plataforma** (não é só do calendário): a
    primeira origem são os lembretes de evento (`modulocalendar`), mas qualquer
    módulo pode criar uma (ex.: vencimentos do ERP) chamando `criar_notificacao`.

    Tenant-scoped (RLS fail-closed na migration companion) e endereçada a um
    `user`; o `NotificacaoViewSet` lista/marca-lida só as do próprio usuário. É
    criada por caminhos **fora de request** (task Celery) sob `rls_bypass()`,
    com o `tenant` herdado explicitamente da origem.
    """

    class Tipo(models.TextChoices):
        LEMBRETE = "lembrete", _("Lembrete de evento")
        SISTEMA = "sistema", _("Sistema")

    user = models.ForeignKey(
        "nucleo.Usuario", on_delete=models.CASCADE, related_name="notificacoes",
    )
    titulo = models.CharField(_("Título"), max_length=200)
    mensagem = models.TextField(_("Mensagem"), blank=True, default="")
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.SISTEMA)
    # Rota do frontend para onde o clique leva (ex.: "/app/calendario"). Opcional.
    url = models.CharField(_("Link"), max_length=300, blank=True, default="")
    lida_em = models.DateTimeField(_("Lida em"), null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("Notificação")
        verbose_name_plural = _("Notificações")
        ordering = ["-criado_em"]
        indexes = [
            # Consulta quente: as do usuário, não-lidas primeiro, mais recentes.
            models.Index(fields=["tenant", "user", "lida_em"], name="notif_user_lida_idx"),
        ]

    def __str__(self):
        return f"[{self.tipo}] {self.titulo} → {self.user_id}"

    @property
    def lida(self):
        return self.lida_em is not None

    def marcar_lida(self):
        if self.lida_em is None:
            self.lida_em = timezone.now()
            self.save(update_fields=["lida_em"])


# ─── Índices econômicos (dado público, sem tenant) ────────────────────────────
# IPCA, INCC e IGP-M são séries **publicadas** — o mesmo número para todo mundo.
# Ficam fora do `TenantScopedModel` pelo mesmo motivo que a base referencial do
# orçamento: replicar a série por tenant criaria N verdades para um dado que tem
# uma só, e o primeiro tenant a digitar errado passaria a ter um IPCA próprio.
# Sem tenant, sem RLS — e a escrita é do administrador da plataforma.

class IndiceEconomico(models.Model):
    """Um índice de correção monetária. A série mensal vive em `ValorIndice`."""

    class Codigo(models.TextChoices):
        IPCA = "ipca", _("IPCA")
        INCC = "incc", _("INCC")
        IGPM = "igpm", _("IGP-M")
        INPC = "inpc", _("INPC")

    codigo = models.CharField(
        max_length=10, choices=Codigo.choices, unique=True, verbose_name=_("Código"),
    )
    nome = models.CharField(max_length=120, verbose_name=_("Nome"))
    fonte = models.CharField(
        max_length=120, blank=True, verbose_name=_("Fonte"),
        help_text=_("Quem publica — IBGE, FGV, Sinduscon."),
    )
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))

    class Meta:
        verbose_name = _("Índice econômico")
        verbose_name_plural = _("Índices econômicos")
        ordering = ["codigo"]

    def __str__(self):
        return self.nome or self.get_codigo_display()


class ValorIndice(models.Model):
    """A variação de **um mês** do índice, em pontos percentuais.

    Guarda a variação do mês, não o número-índice acumulado: é assim que IBGE e
    FGV publicam, e é o que permite compor qualquer intervalo sem depender de uma
    base arbitrária. O acumulado sai da composição em `clientes/correcao.py`.

    `competencia` é sempre o **dia 1** do mês — mesma convenção da data-base do
    orçamento. Guardar o dia da divulgação misturaria "mês a que se refere" com
    "dia em que saiu", e o reajuste usa o primeiro.
    """

    indice = models.ForeignKey(
        IndiceEconomico, on_delete=models.CASCADE, related_name="valores",
        verbose_name=_("Índice"),
    )
    competencia = models.DateField(
        verbose_name=_("Competência"),
        help_text=_("Dia 1 do mês a que a variação se refere."),
    )
    variacao_percentual = models.DecimalField(
        max_digits=9, decimal_places=4, verbose_name=_("Variação no mês (%)"),
        help_text=_("Pode ser negativa — deflação existe e o contrato a acompanha."),
    )

    class Meta:
        verbose_name = _("Valor de índice")
        verbose_name_plural = _("Valores de índice")
        ordering = ["indice", "-competencia"]
        constraints = [
            models.UniqueConstraint(
                fields=["indice", "competencia"], name="indice_competencia_unica",
            ),
        ]
        indexes = [
            models.Index(fields=["indice", "competencia"], name="indice_serie_idx"),
        ]

    def __str__(self):
        return f"{self.indice.codigo} {self.competencia:%m/%Y}: {self.variacao_percentual}%"


# ===========================================================================
# D98 — a frota de trabalho pesado: o porteiro que faltava
# ===========================================================================
# **Por que uma TABELA e não a prioridade do Redis.** O broker sabe entregar a
# próxima mensagem; não sabe dizer *quem está na frente*, não sabe reservar uma
# fração de cadeiras para um plano nem devolver um job ao fim da fila com o
# lugar certo. Tudo isso é consulta sobre um conjunto ordenado — e conjunto
# ordenado com leitura arbitrária é banco. O Celery continua sendo o executor: o
# despachante escolhe a linha e **só então** publica a mensagem.
#
# **Sem `tenant` herdado do `TenantScopedModel`, e é deliberado.** A RLS
# fail-closed é o que impede um tenant de ler linha de outro — e o despachante
# precisa ler as de TODOS para poder ser justo entre eles. Uma fila escopada por
# tenant não é uma fila, são N filas que não se enxergam, que é exatamente o
# desenho que o dono descartou ("fila única com prioridade e cadeira marcada,
# nunca fila separada por plano"). O `tenant` fica como COLUNA — é dado da
# política, não chave de isolamento —, e quem expõe a fila ao cliente filtra por
# ele explicitamente na view, como o `AuditLog` já faz. É o mesmo lugar do
# `FailedTask`: tabela de infraestrutura, lida pelo processo e não pelo inquilino.
class TarefaNaFila(models.Model):
    """Um trabalho pesado esperando cadeira na frota.

    A linha nasce no lugar do `.delay()`: quem enfileira chama
    `nucleo.frota.enfileirar(...)` e recebe de volta a posição, em vez de mandar
    a mensagem direto ao broker. O despachante é quem publica — e é ele que
    aplica a política de `payment/planos.py` §5.4c.
    """

    class Situacao(models.TextChoices):
        #: Na fila, esperando cadeira. É o único estado que conta posição.
        AGUARDANDO = "aguardando", _("Na fila")
        #: O despachante publicou a mensagem; o worker pode ainda não ter pegado.
        #: Ocupa cadeira a partir daqui, porque o que a frota tem de proteger é o
        #: número de jobs em voo — contar só a partir do "executando" deixaria o
        #: despachante publicar cem mensagens no intervalo entre uma e outra.
        DESPACHADA = "despachada", _("Despachada")
        CONCLUIDA = "concluida", _("Concluída")
        #: Saiu da fila sem executar — a revisão foi apagada, o lote desfeito.
        CANCELADA = "cancelada", _("Cancelada")

    tarefa_id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="tarefas_na_fila",
        verbose_name=_("Empresa"),
    )
    #: O plano **no momento de entrar na fila**, e não uma consulta ao IAM na
    #: hora de despachar. O worker não tem token e o despachante não tem usuário;
    #: resolver o plano ali exigiria uma chamada de rede por job, para responder
    #: algo que quem enfileirou já tinha na mão. É a mesma razão pela qual
    #: `tiers` e `teto_snap` viajam como argumento da task.
    plano = models.CharField(max_length=30, blank=True, verbose_name=_("Plano"))
    #: Quantas cadeiras extras os add-ons deste cliente compram, congeladas junto
    #: com o plano e pelo mesmo motivo.
    cadeiras_extras = models.PositiveSmallIntegerField(
        default=0, verbose_name=_("Cadeiras de add-on"),
    )

    #: Qual frota. Hoje só `conversao`; o campo existe porque o endereço é do
    #: `nucleo` justamente para a importação de acervo, a exportação grande e a
    #: ortofoto do Maps entrarem sem uma segunda fila paralela.
    frota = models.CharField(max_length=20, default="conversao", verbose_name=_("Frota"))
    tarefa = models.CharField(max_length=180, verbose_name=_("Task Celery"))
    argumentos = models.JSONField(default=list, blank=True, verbose_name=_("Argumentos"))
    #: Identidade do TRABALHO, não da linha — `prancheta.derivada:123`. É o que
    #: torna `enfileirar` idempotente: o mesmo upload reenviado, o `reprocessar`
    #: clicado duas vezes e o retry do Celery não podem virar três lugares na
    #: fila para o mesmo arquivo.
    chave = models.CharField(max_length=120, db_index=True, verbose_name=_("Chave do trabalho"))

    situacao = models.CharField(
        max_length=12, choices=Situacao.choices, default=Situacao.AGUARDANDO,
        verbose_name=_("Situação"),
    )
    #: Menor sai primeiro. Nasce da classe de cadeira e desce (fica mais urgente)
    #: a cada volta à fila e quando o administrador do tenant sobe o job.
    prioridade = models.IntegerField(default=100, db_index=True, verbose_name=_("Prioridade"))
    #: Quantas vezes este trabalho já voltou ao fim da fila (PRA.11). Guardado
    #: para a tela poder dizer "3ª passada" em vez de deixar o cliente concluir
    #: que o sistema travou, e para o envelhecimento ser auditável.
    voltas = models.PositiveSmallIntegerField(default=0, verbose_name=_("Voltas à fila"))
    #: Quem mandou este job passar na frente dos OUTROS DA MESMA EMPRESA, e
    #: quando. Nunca passa à frente de outro tenant: a ordem entre empresas do
    #: mesmo plano continua sendo a de chegada, e um botão que atrasasse o
    #: vizinho seria um botão que todo mundo aperta sempre — zerando o efeito e
    #: deixando só a fila imprevisível (decisão do dono, 16/08/2026).
    urgente_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="tarefas_priorizadas", verbose_name=_("Priorizada por"),
    )
    urgente_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Priorizada em"))

    criada_em = models.DateTimeField(auto_now_add=True, db_index=True)
    despachada_em = models.DateTimeField(null=True, blank=True)
    concluida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Tarefa na fila")
        verbose_name_plural = _("Tarefas na fila")
        ordering = ["prioridade", "criada_em"]
        constraints = [
            # Um trabalho, um lugar. Parcial porque a chave só é única entre as
            # VIVAS: o mesmo arquivo reprocessado meses depois é um trabalho
            # novo, e uma unicidade total impediria a segunda conversão para
            # sempre — o defeito que só aparece no cliente antigo.
            models.UniqueConstraint(
                fields=["frota", "chave"],
                condition=models.Q(situacao__in=["aguardando", "despachada"]),
                name="frota_um_lugar_por_trabalho",
            ),
        ]
        indexes = [
            # O índice do despachante: ele varre as aguardando de uma frota na
            # ordem da política, e é a consulta que roda a cada job terminado.
            models.Index(
                fields=["frota", "situacao", "prioridade", "criada_em"],
                name="frota_despacho_idx",
            ),
            models.Index(fields=["tenant", "situacao"], name="frota_tenant_idx"),
        ]

    def __str__(self):
        return f"{self.frota}:{self.chave} ({self.situacao})"


# ---------------------------------------------------------------------------
# Fluxo de aprovação multi-nível (PDCA.0) — a escada que aprova dinheiro
# ---------------------------------------------------------------------------
# **Por que no `nucleo` e não no `modulopdca`**, que é quem a pediu: aprovar em
# mais de um nível não é assunto de obra. A medição do empreiteiro é só o
# primeiro caso — o ERP tem pagamento acima de alçada, o SCM tem adjudicação de
# cotação e o Orçamento já tem um `aprovar` de um nível só que um dia vai querer
# ser escada. É o mesmo raciocínio que pôs a frota aqui e não na Prancheta: *a
# Prancheta é a primeira cliente, não a dona* (docs/modulos/modulopdca.md §4.4).
#
# **O alvo é `ContentType`, e não o par de FKs nuláveis do `modulomaps.Local`.**
# Lá o polimorfismo tinha seis tipos conhecidos, todos vizinhos, e a integridade
# referencial valia o preço. Aqui o conjunto de alvos é **aberto por desenho** —
# o `nucleo` é importado por todo módulo e não pode importar nenhum de volta, sob
# pena de dependência circular entre apps. O preço está pago no desenho: quem for
# alvo declara uma `GenericRelation`, e o pedido morre junto com o objeto.
class FluxoAprovacao(TenantScopedModel):
    """O **molde** da escada: quais degraus, em que ordem, exigindo o quê.

    É por tenant porque a alçada é da empresa: uma construtora atesta com
    engenheiro e diretor, outra insere o gerente de contrato no meio. O que a
    plataforma fixa é a máquina; a escada é do cliente.
    """

    fluxo_id = models.AutoField(primary_key=True)
    codigo = models.SlugField(max_length=60, verbose_name=_("Código"))
    nome = models.CharField(max_length=150, verbose_name=_("Nome"))
    #: O tipo de objeto que esta escada aprova (`modulopdca.medicao`, um dia).
    #: `PROTECT` porque apagar o ContentType significa desinstalar o app — e aí
    #: o fluxo tem de ser tratado à mão, não sumir levando o histórico junto.
    alvo = models.ForeignKey(
        "contenttypes.ContentType", on_delete=models.PROTECT,
        related_name="fluxos_aprovacao", verbose_name=_("O que este fluxo aprova"),
    )
    #: O fluxo que vale quando quem abre o pedido não escolhe nenhum. Um por
    #: (tenant, alvo) — a constraint parcial abaixo é quem garante.
    padrao = models.BooleanField(default=False, verbose_name=_("Padrão para este alvo"))
    #: **Quem executa não aprova** (a segregação que o ORC.6 provou necessária).
    #: Ligar isto é decisão consciente do cliente para a obra pequena, onde o
    #: mesmo engenheiro apura e atesta; o padrão recusa, e a recusa é a regra.
    permite_autoatesto = models.BooleanField(
        default=False, verbose_name=_("Permite que quem solicitou ateste"),
    )
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))
    descricao = models.TextField(blank=True, verbose_name=_("Descrição"))
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Fluxo de aprovação")
        verbose_name_plural = _("Fluxos de aprovação")
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "codigo"], name="aprovacao_fluxo_codigo_unico",
            ),
            # Um padrão por alvo. Sem isto, "abrir sem escolher fluxo" viraria
            # escolha arbitrária entre dois moldes — e a diferença entre eles é
            # quantas pessoas precisam assinar antes de o dinheiro sair.
            models.UniqueConstraint(
                fields=["tenant", "alvo"], condition=models.Q(padrao=True),
                name="aprovacao_um_padrao_por_alvo",
            ),
        ]

    def __str__(self):
        return f"{self.nome} ({self.codigo})"


class NivelAprovacao(TenantScopedModel):
    """Um degrau. Declara **qual permissão** ele exige — e é por isso que a
    escada não cria permissão numerada (`…aprovar_nivel_2`), que seria vocabulário
    novo a cada cliente que insere um degrau. O tenant compõe a escada com os
    papéis que já tem (docs/modulos/modulopdca.md §8).
    """

    nivel_id = models.AutoField(primary_key=True)
    fluxo = models.ForeignKey(
        FluxoAprovacao, on_delete=models.CASCADE, related_name="niveis",
        verbose_name=_("Fluxo"),
    )
    ordem = models.PositiveSmallIntegerField(verbose_name=_("Ordem"))
    nome = models.CharField(max_length=120, verbose_name=_("Nome do degrau"))
    #: Código do catálogo da IAM (`modulo.recurso.acao`). Guardado como texto
    #: porque o catálogo é da IAM e o backend é resource server: o que chega no
    #: token é a string, e comparar string com string é o que o
    #: `RequirePermission` já faz.
    permissao_exigida = models.CharField(
        max_length=80, verbose_name=_("Permissão exigida"),
    )
    #: Quantos dias este degrau deveria levar. Não trava nada — alimenta a fila
    #: de decisão ("parado há 9 dias") e, mais tarde, a notificação.
    prazo_dias = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_("Prazo (dias)"),
    )

    class Meta:
        verbose_name = _("Nível de aprovação")
        verbose_name_plural = _("Níveis de aprovação")
        ordering = ["fluxo", "ordem"]
        constraints = [
            models.UniqueConstraint(
                fields=["fluxo", "ordem"], name="aprovacao_nivel_ordem_unica",
            ),
        ]

    def __str__(self):
        return f"{self.ordem}. {self.nome}"


class PedidoAprovacao(TenantScopedModel):
    """Uma escada **em curso** sobre um objeto concreto.

    Guarda `resumo` e `valor_referencia` copiados do alvo de propósito: a fila de
    decisão precisa dizer *o que* está sendo aprovado e *quanto* vale sem abrir
    uma consulta por linha a um módulo que o `nucleo` não conhece. É snapshot,
    não fonte — a verdade continua no alvo.
    """

    class Estado(models.TextChoices):
        EM_APROVACAO = "em_aprovacao", _("Em aprovação")
        APROVADO = "aprovado", _("Aprovado")
        #: Terminal. Correção exige objeto novo (a medição **retificadora** da
        #: §11.5), nunca reabrir este — reabrir apagaria o atesto que recusou.
        REPROVADO = "reprovado", _("Reprovado")
        CANCELADO = "cancelado", _("Cancelado")

    pedido_id = models.AutoField(primary_key=True)
    fluxo = models.ForeignKey(
        FluxoAprovacao, on_delete=models.PROTECT, related_name="pedidos",
        verbose_name=_("Fluxo"),
    )
    alvo_tipo = models.ForeignKey(
        "contenttypes.ContentType", on_delete=models.PROTECT,
        related_name="pedidos_aprovacao", verbose_name=_("Tipo do alvo"),
    )
    alvo_id = models.PositiveIntegerField(verbose_name=_("Id do alvo"))

    estado = models.CharField(
        max_length=14, choices=Estado.choices, default=Estado.EM_APROVACAO,
        db_index=True, verbose_name=_("Estado"),
    )
    #: Em que degrau a escada parou. `SET_NULL` para o histórico sobreviver à
    #: reorganização do fluxo; nulo quando a escada terminou.
    nivel_atual = models.ForeignKey(
        NivelAprovacao, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pedidos_parados_aqui", verbose_name=_("Degrau atual"),
    )

    solicitado_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="aprovacoes_solicitadas", verbose_name=_("Solicitante"),
    )
    #: O nome vale por si: `SET_NULL` acima preserva a linha quando o usuário é
    #: desligado, e uma fila de atesto que diz "solicitado por —" perde a
    #: rastreabilidade justamente no caso em que ela é mais necessária.
    solicitante_nome = models.CharField(max_length=150, blank=True)
    solicitado_em = models.DateTimeField(auto_now_add=True)
    concluido_em = models.DateTimeField(null=True, blank=True)

    resumo = models.CharField(max_length=240, blank=True, verbose_name=_("Resumo"))
    #: Nulo é resposta legítima — nem todo alvo tem valor (uma linha de base de
    #: cronograma não tem). Zerar seria fabricar dado, a mesma régua do
    #: `Local.ponto` do Maps.
    valor_referencia = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        verbose_name=_("Valor de referência"),
    )

    class Meta:
        verbose_name = _("Pedido de aprovação")
        verbose_name_plural = _("Pedidos de aprovação")
        ordering = ["-solicitado_em"]
        constraints = [
            # Um objeto tem no máximo UMA escada correndo. Duas seriam dois
            # atestos válidos sobre a mesma medição, cada um numa metade da
            # escada — e o alvo congelando por qualquer uma delas.
            models.UniqueConstraint(
                fields=["tenant", "alvo_tipo", "alvo_id"],
                condition=models.Q(estado="em_aprovacao"),
                name="aprovacao_um_pedido_aberto_por_alvo",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "estado"], name="aprov_tenant_estado_idx"),
            models.Index(fields=["alvo_tipo", "alvo_id"], name="aprov_alvo_idx"),
        ]

    def __str__(self):
        return f"#{self.pedido_id} {self.resumo or self.alvo_tipo} ({self.estado})"


class Atesto(TenantScopedModel):
    """A assinatura de um degrau — quem, quando, com qual permissão, e o que
    escreveu. **Append-only**: não é editado nem apagado, pelo mesmo motivo que o
    apontamento de avanço não é (§4.3) — é a prova de que o dinheiro foi liberado
    por alguém com alçada.
    """

    class Decisao(models.TextChoices):
        APROVADO = "aprovado", _("Aprovado")
        REPROVADO = "reprovado", _("Reprovado")

    atesto_id = models.AutoField(primary_key=True)
    pedido = models.ForeignKey(
        PedidoAprovacao, on_delete=models.CASCADE, related_name="atestos",
        verbose_name=_("Pedido"),
    )
    nivel = models.ForeignKey(
        NivelAprovacao, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="atestos", verbose_name=_("Degrau"),
    )
    #: Cópia da ordem e do nome do degrau: o fluxo pode ser reorganizado depois,
    #: e o atesto tem de continuar contando a escada como ela era no dia.
    nivel_ordem = models.PositiveSmallIntegerField(verbose_name=_("Ordem do degrau"))
    nivel_nome = models.CharField(max_length=120, blank=True)

    decisao = models.CharField(
        max_length=10, choices=Decisao.choices, verbose_name=_("Decisão"),
    )
    autor = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="atestos", verbose_name=_("Autor"),
    )
    autor_nome = models.CharField(max_length=150, blank=True)
    #: Qual permissão foi conferida na hora. Auditoria: responde "com que
    #: autoridade?" mesmo depois de o papel do usuário mudar.
    permissao_conferida = models.CharField(max_length=80, blank=True)
    decidido_em = models.DateTimeField(auto_now_add=True)
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))

    class Meta:
        verbose_name = _("Atesto")
        verbose_name_plural = _("Atestos")
        ordering = ["pedido", "nivel_ordem"]
        constraints = [
            # Um atesto por degrau por pedido. A reprovação encerra a escada e a
            # correção nasce como pedido novo — então não existe "atestar de novo
            # o mesmo degrau" dentro do mesmo pedido.
            models.UniqueConstraint(
                fields=["pedido", "nivel_ordem"], name="aprovacao_um_atesto_por_degrau",
            ),
        ]

    def __str__(self):
        return f"{self.nivel_ordem}. {self.decisao} por {self.autor_nome or 'sem autor'}"


# ---------------------------------------------------------------------------
# A lixeira (D116) — o índice do que está sob lápide
# ---------------------------------------------------------------------------


class Lixo(TenantScopedModel):
    """Uma linha por objeto que foi para a lixeira — o **índice**, não o dado.

    O dado continua onde sempre esteve, marcado pela lápide do
    `nucleo.tenancy.Excluivel`. Esta tabela existe por dois motivos que a lápide
    sozinha não resolve:

    1. **A página do lixo é uma consulta só.** Sem ela, listar "o que este tenant
       excluiu" exigiria varrer as 16 tabelas que herdam `Excluivel`, ordenar em
       Python e paginar à mão. Com ela, é um `ORDER BY excluido_em DESC` com
       `LIMIT` — e o custo não cresce quando o 17º modelo entrar na lixeira.
    2. **A auditoria sobrevive à purga.** No 15º dia o objeto é apagado de
       verdade; esta linha **fica**, com `purgado_em` preenchido. É o que
       responde "quem apagou o quê, quando, e por quê" depois que não há mais o
       quê. A prancha original mandava hard-deletar esta linha junto — seria
       apagar o log de auditoria no exato momento em que ele passa a ser a única
       prova restante.

    Os campos de auditoria são **desnormalizados** da lápide de propósito, e a
    lápide continua sendo a verdade: as duas escritas acontecem na mesma
    transação (`nucleo/lixo.py`). Sem a cópia, a listagem voltaria a precisar do
    join com as 16 tabelas que ela existe para evitar.
    """

    lixo_id = models.AutoField(primary_key=True)

    #: `PROTECT` porque perder o `ContentType` transformaria a linha de auditoria
    #: em "alguém apagou alguma coisa".
    alvo_tipo = models.ForeignKey(
        "contenttypes.ContentType", on_delete=models.PROTECT,
        related_name="itens_no_lixo", verbose_name=_("Tipo do alvo"),
    )
    alvo_id = models.PositiveBigIntegerField(verbose_name=_("Id do alvo"))

    #: `str(objeto)` no instante da exclusão. Depois da purga é a **única** coisa
    #: que ainda diz o que era: "Residencial Aurora — Torre B" responde o chamado
    #: de suporte que `Obra #412` não responde.
    rotulo = models.CharField(max_length=255, blank=True, verbose_name=_("Rótulo"))

    excluido_em = models.DateTimeField(db_index=True, verbose_name=_("Excluído em"))
    excluido_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="itens_que_excluiu", verbose_name=_("Excluído por"),
    )
    #: Mesmo raciocínio do `solicitante_nome` do `PedidoAprovacao`: o `SET_NULL`
    #: acima preserva a linha quando o usuário é desligado, e uma lixeira que diz
    #: "excluído por —" perde a rastreabilidade justamente no caso difícil.
    excluido_por_nome = models.CharField(max_length=150, blank=True)
    motivo = models.TextField(blank=True, verbose_name=_("Motivo"))

    #: **Gravado, não calculado.** O prazo é congelado no instante da exclusão a
    #: partir da retenção do plano vigente. Calcular na hora da varredura faria um
    #: downgrade de plano encurtar retroativamente a janela de quem já tinha
    #: apagado — o cliente perderia, sem aviso, dado que ainda estava no prazo
    #: quando saiu. E é este campo que a tela mostra: "purga em 11 dias".
    purgar_em = models.DateTimeField(db_index=True, verbose_name=_("Purga em"))

    restaurado_em = models.DateTimeField(null=True, blank=True)
    restaurado_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="itens_que_restaurou", verbose_name=_("Restaurado por"),
    )

    purgado_em = models.DateTimeField(null=True, blank=True)
    #: Nulo com `purgado_em` preenchido significa **purga automática** — o
    #: sistema, não uma pessoa. A tela lê os dois campos e diz qual foi; um
    #: usuário-robô só para assinar isso seria um ator falso no log.
    purgado_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="itens_que_purgou", verbose_name=_("Purgado por"),
    )
    #: Por que a purga do 15º dia não conseguiu apagar (um `PROTECT` que o
    #: desenho do módulo impõe, por exemplo). Vazio é o caso normal.
    falha_na_purga = models.TextField(blank=True, verbose_name=_("Falha na purga"))

    class Meta:
        verbose_name = _("Item no lixo")
        verbose_name_plural = _("Lixo")
        ordering = ["-excluido_em"]
        constraints = [
            # Um objeto está no máximo UMA vez na lixeira. Duas linhas ativas
            # dariam dois botões "Restaurar" para o mesmo objeto e dois relógios
            # de purga concorrentes sobre a mesma lápide.
            models.UniqueConstraint(
                fields=["tenant", "alvo_tipo", "alvo_id"],
                condition=models.Q(restaurado_em__isnull=True, purgado_em__isnull=True),
                name="lixo_um_item_ativo_por_alvo",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "excluido_em"], name="lixo_tenant_data_idx"),
            models.Index(fields=["alvo_tipo", "alvo_id"], name="lixo_alvo_idx"),
        ]

    def __str__(self):
        return f"{self.rotulo or self.alvo_tipo} (excluído em {self.excluido_em:%d/%m/%Y})"

    @property
    def ativo(self) -> bool:
        """Está na lixeira agora — nem restaurado, nem purgado."""
        return self.restaurado_em is None and self.purgado_em is None


# ---------------------------------------------------------------------------
# Remodelagem da segurança, fases 2 e 3 — docs/acesso-e-permissoes.md §10.12
# ---------------------------------------------------------------------------
# Os dois modelos abaixo são **da plataforma**, não do cliente, e por isso não
# herdam `TenantScopedModel`: a flag de um módulo vale para toda empresa, e a
# divergência é gravada pela sombra numa thread de fundo, sem o contexto de RLS
# da requisição (com RLS fail-closed, a linha não entraria). Nenhum dos dois
# guarda conteúdo de cliente — só ids, códigos do catálogo e booleanos.


class ModoAutorizacao(models.Model):
    """Quem decide "pode?" num módulo: o token (hoje) ou o PDP (fase 3).

    É a **volta atrás** da fase 3: `manage.py modo_autorizacao pdca token`
    devolve o módulo ao token na hora, sem deploy nem restart. Módulo sem linha
    aqui decide pelo token — a virada é sempre explícita, módulo a módulo, e só
    depois de a sombra mostrar o módulo sem divergência.

    Os "módulos" são os do catálogo, mais `base` e `plataforma` (os códigos sem
    entitlement). As perguntas "é admin?" e "é o supervisor?" seguem
    `plataforma`.
    """

    class Modo(models.TextChoices):
        TOKEN = "token", _("Token (como sempre foi)")
        PDP = "pdp", _("PDP (SpiceDB)")

    modulo = models.CharField(max_length=40, primary_key=True, verbose_name=_("Módulo"))
    modo = models.CharField(max_length=10, choices=Modo.choices, default=Modo.TOKEN)
    alterado_em = models.DateTimeField(auto_now=True)
    alterado_por = models.CharField(max_length=150, blank=True)

    class Meta:
        verbose_name = _("Modo de autorização")
        verbose_name_plural = _("Modos de autorização")
        ordering = ["modulo"]

    def __str__(self):
        return f"{self.modulo}: {self.modo}"


class DivergenciaAutorizacao(models.Model):
    """Uma pergunta em que token e PDP responderam diferente — *append-only*.

    É a régua da saída da fase 2 (§10.12: "zero divergência por duas semanas em
    uso real"), e por isso guarda o **tipo**: só a `real` conta contra o
    critério. As outras são o sistema funcionando como desenhado — o token
    emitido antes de uma troca de papel ainda diz o que era verdade
    (`token_defasado`), ou o PDP não respondeu (`pdp_indisponivel`).

    Campos fixos e nenhum texto livre (§10.9): quem, que pergunta, o que cada
    lado disse. Nunca o conteúdo que a pessoa estava vendo.
    """

    class Tipo(models.TextChoices):
        REAL = "real", _("Real — defeito a investigar")
        TOKEN_DEFASADO = "token_defasado", _("Token emitido antes da última troca de acesso")
        PDP_INDISPONIVEL = "pdp_indisponivel", _("PDP não respondeu")
        FORA_DO_ESQUEMA = "fora_do_esquema", _("Pergunta que o PDP não conhece")

    id = models.BigAutoField(primary_key=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    tenant_id = models.UUIDField(null=True)
    usuario_id = models.CharField(max_length=64)
    pergunta = models.CharField(max_length=100)
    modulo = models.CharField(max_length=40)
    classe = models.CharField(max_length=1)
    #: Quem decidiu a requisição naquele momento — "token" ou "pdp".
    modo = models.CharField(max_length=10)
    decisao_token = models.BooleanField()
    decisao_pdp = models.BooleanField(null=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    idade_do_token_s = models.IntegerField(null=True)

    class Meta:
        verbose_name = _("Divergência de autorização")
        verbose_name_plural = _("Divergências de autorização")
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["tipo", "-criado_em"], name="authz_div_tipo_idx")]

    def __str__(self):
        return f"{self.criado_em:%d/%m %H:%M} {self.tipo} {self.pergunta}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("DivergenciaAutorizacao é append-only: alteração não é permitida.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("DivergenciaAutorizacao é append-only: exclusão não é permitida.")
