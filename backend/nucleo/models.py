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
