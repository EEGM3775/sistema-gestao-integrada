from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from nucleo.tenancy import TenantScopedModel


class Calendar(TenantScopedModel):
    """Uma agenda com nome e cor (Fatia D) — o que se mostra e se esconde.

    O **escopo** decide quem a vê; ver é também poder lançar nela:

    - `pessoal` — só o dono;
    - `equipe` — o dono e os membros (`CalendarMember`);
    - `empresa` — todos da empresa (a RLS já fecha o tenant).

    Evento sem calendário é da agenda pessoal implícita do seu dono ("Meus
    eventos") — o comportamento de antes da Fatia D, sem migração de dado.
    Renomear, recolorir, mexer nos membros ou apagar é só do dono.
    """

    class Scope(models.TextChoices):
        PESSOAL = 'pessoal', 'Pessoal'
        EQUIPE = 'equipe', 'Equipe'
        EMPRESA = 'empresa', 'Empresa'

    name = models.CharField(max_length=120)
    # Cor da agenda no grid (hex `#rrggbb`).
    color = models.CharField(max_length=7, default='#1e40af')
    scope = models.CharField(max_length=10, choices=Scope.choices, default=Scope.PESSOAL)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='calendars',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name', 'id']

    def __str__(self):
        return self.name


class CalendarMember(TenantScopedModel):
    """Membro de uma agenda de equipe. Tabela explícita (não um M2M solto) para
    carregar `tenant_id` e entrar na RLS como toda tabela de negócio."""

    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='calendar_memberships',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['calendar', 'user'], name='uniq_calendar_member'),
        ]

    def __str__(self):
        return f"{self.user_id} em {self.calendar_id}"


class CalendarEvent(TenantScopedModel):
    EVENT_TYPE_CHOICES = [
        ('tarefa', 'Tarefa'),
        ('reuniao', 'Reunião'),
        ('lembrete', 'Lembrete'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    all_day = models.BooleanField(default=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='calendar_events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES, default='tarefa')
    # Agenda do evento (Fatia D). Vazio = a agenda pessoal implícita do `user`.
    calendar = models.ForeignKey(
        Calendar, on_delete=models.CASCADE, null=True, blank=True, related_name='events',
    )
    # Onde acontece (Fatia E): texto livre — endereço, sala, "canteiro da obra X".
    location = models.CharField(max_length=255, blank=True, default='')
    # Identidade do evento num `.ics` importado (Fatia E): reimportar o mesmo
    # arquivo não duplica. Vazio para o que nasceu aqui.
    ical_uid = models.CharField(max_length=255, blank=True, default='', db_index=True)

    # --- Recorrência (Fatia B) ---
    # Regra RRULE do iCalendar (RFC 5545), SEM o DTSTART — a âncora é sempre
    # `start_time`. Ex.: "FREQ=WEEKLY;BYDAY=MO,WE;COUNT=10". Vazio = evento único.
    # As ocorrências são VIRTUAIS: expandidas no feed do período, nunca gravadas.
    recurrence_rule = models.CharField(max_length=255, blank=True, default='')
    # Datas de ocorrência puladas na expansão (EXDATE) — uma por "excluir só esta"
    # ou por override de "editar só esta". ISO 8601, separadas por vírgula.
    excluded_dates = models.TextField(blank=True, default='')
    # Override de uma ocorrência específica ("editar só esta"): aponta para o
    # evento-mestre e guarda a data da ocorrência original que substitui.
    recurrence_master = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='overrides',
    )
    original_start = models.DateTimeField(null=True, blank=True)

    # Generic foreign key to link to any other model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey('content_type', 'object_id')

    @property
    def is_recurring(self):
        return bool(self.recurrence_rule)

    def excluded_dates_list(self):
        """EXDATE persistidas como lista de strings ISO (sem vazios)."""
        return [d for d in (self.excluded_dates or '').split(',') if d.strip()]

    def __str__(self):
        return self.title


class EventAttendee(TenantScopedModel):
    """Convidado de um evento, com a resposta dele (Fatia D).

    Convidar é mostrar: o convidado vê o evento no próprio calendário, mesmo
    que a agenda não seja dele, e responde aceito / recusado. Quem aceita
    recebe os lembretes do evento. Numa série, o convite vale para a série
    (o convidado responde no mestre)."""

    class Status(models.TextChoices):
        PENDENTE = 'pendente', 'Pendente'
        ACEITO = 'aceito', 'Aceito'
        RECUSADO = 'recusado', 'Recusado'

    event = models.ForeignKey(CalendarEvent, on_delete=models.CASCADE, related_name='attendees')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='calendar_invites',
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDENTE)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['event', 'user'], name='uniq_event_attendee'),
        ]
        ordering = ['id']

    def __str__(self):
        return f"{self.user_id} · {self.event_id} · {self.status}"


class EventReminder(TenantScopedModel):
    """Lembrete de um evento (Fatia C): dispara um aviso `offset_minutes` antes
    do início. 1‑N por evento (ex.: 1 dia + 10 min antes). A task Celery
    `despachar_lembretes` varre os lembretes vencendo e cria uma `Notificacao`
    in-app (e e-mail, se configurado), carimbando `last_sent_occurrence` para
    não repetir. Para eventos recorrentes o mesmo lembrete vale por ocorrência —
    o carimbo guarda a última ocorrência já avisada."""

    event = models.ForeignKey(
        CalendarEvent, on_delete=models.CASCADE, related_name='reminders',
    )
    # Minutos antes do início do evento (0 = na hora). Teto de 4 semanas.
    offset_minutes = models.PositiveIntegerField(default=10)
    # Dedupe: início da última ocorrência já notificada por este lembrete.
    last_sent_occurrence = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'offset_minutes'], name='uniq_reminder_event_offset'),
        ]
        ordering = ['offset_minutes']

    def __str__(self):
        return f"Lembrete {self.offset_minutes}min · evento {self.event_id}"


class Feriado(models.Model):
    """Feriado de **referência** (Fatia F) — dado universal, **não** tenant-scoped:
    o mesmo feriado vale para todos os tenants. Populado pelo comando
    `sincronizar_feriados` (federal/estadual via `python-holidays`, municipal via
    o dataset MIT). O feed do calendário lê daqui por escopo/localidade.
    """
    ESCOPO_CHOICES = [
        ('nacional', 'Nacional'),
        ('estadual', 'Estadual'),
        ('municipal', 'Municipal'),
    ]

    data = models.DateField(db_index=True)
    nome = models.CharField(max_length=200)
    escopo = models.CharField(max_length=12, choices=ESCOPO_CHOICES)
    uf = models.CharField(max_length=2, blank=True, default='')       # estadual/municipal
    ibge = models.CharField(max_length=7, blank=True, default='')     # municipal
    cidade = models.CharField(max_length=120, blank=True, default='')  # municipal

    class Meta:
        indexes = [
            models.Index(fields=['data', 'escopo']),
            models.Index(fields=['escopo', 'uf']),
            models.Index(fields=['escopo', 'ibge']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['data', 'nome', 'escopo', 'uf', 'ibge'], name='uniq_feriado'),
        ]

    def __str__(self):
        return f"{self.data} {self.nome} ({self.escopo})"


class FeriadoSync(models.Model):
    """Marca da última sincronização de feriados (singleton, pk=1) — origem da
    mensagem "sistema atualizado com os feriados" exibida ao superuser."""
    atualizado_em = models.DateTimeField(auto_now=True)
    anos = models.CharField(max_length=100, blank=True, default='')
    total = models.PositiveIntegerField(default=0)
    detalhes = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Feriados sincronizados em {self.atualizado_em:%d/%m/%Y %H:%M} ({self.total})"