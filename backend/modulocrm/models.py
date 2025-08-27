# backend/modulocrm/models.py
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from clientes.models import Cliente
from empreendimentos.models import Empreendimento

# Modelo Base Abstrato para campos comuns
class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(_("Data de Criação"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Última Atualização"), auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']

# 1. Lead: O ponto de entrada do funil
class Lead(BaseModel):
    class StatusChoices(models.TextChoices):
        NOVO = 'NOVO', _('Novo')
        CONTATADO = 'CONTATADO', _('Contatado')
        QUALIFICADO = 'QUALIFICADO', _('Qualificado')
        PERDIDO = 'PERDIDO', _('Perdido')

    first_name = models.CharField(_("Nome"), max_length=100)
    last_name = models.CharField(_("Sobrenome"), max_length=100)
    email = models.EmailField(_("E-mail"), max_length=254, unique=True, db_index=True)
    phone = models.CharField(_("Telefone"), max_length=20, blank=True)
    company = models.CharField(_("Empresa"), max_length=255, blank=True)
    status = models.CharField(_("Status"), max_length=20, choices=StatusChoices.choices, default=StatusChoices.NOVO)
    source = models.CharField(_("Origem do Lead"), max_length=100, blank=True, help_text=_("Ex: Site, Indicação, Evento"))
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_leads',
        verbose_name=_("Responsável")
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    class Meta(BaseModel.Meta):
        verbose_name = _("Lead")
        verbose_name_plural = _("Leads")

# 2. Account: A empresa cliente
class Account(BaseModel):
    name = models.CharField(_("Nome da Conta/Empresa"), max_length=255, unique=True, db_index=True)
    email = models.EmailField(_("E-mail Principal"), blank=True)
    phone = models.CharField(_("Telefone Principal"), max_length=20, blank=True)
    website = models.URLField(_("Website"), blank=True)
    industry = models.CharField(_("Setor"), max_length=100, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_accounts',
        verbose_name=_("Gerente da Conta")
    )
    # Vincula a conta a um Cliente já existente no sistema, se aplicável
    cliente_associado = models.OneToOneField(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='account_crm')


    def __str__(self):
        return self.name

    class Meta(BaseModel.Meta):
        verbose_name = _("Conta (Empresa)")
        verbose_name_plural = _("Contas (Empresas)")

# 3. Contact: O contato individual dentro de uma Account
class Contact(BaseModel):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='contacts', verbose_name=_("Conta"))
    first_name = models.CharField(_("Nome"), max_length=100)
    last_name = models.CharField(_("Sobrenome"), max_length=100)
    email = models.EmailField(_("E-mail"), max_length=254, db_index=True)
    phone = models.CharField(_("Telefone"), max_length=20, blank=True)
    title = models.CharField(_("Cargo"), max_length=100, blank=True)
    # Vincula o contato a um Cliente já existente no sistema, se aplicável
    cliente_associado = models.OneToOneField(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='contact_crm')


    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    class Meta(BaseModel.Meta):
        verbose_name = _("Contato")
        verbose_name_plural = _("Contatos")
        unique_together = ('account', 'email')

# 4. Opportunity: A negociação em andamento
class Opportunity(BaseModel):
    class StageChoices(models.TextChoices):
        QUALIFICACAO = 'QUALIFICACAO', _('Qualificação')
        PROPOSTA = 'PROPOSTA', _('Proposta Apresentada')
        NEGOCIACAO = 'NEGOCIACAO', _('Em Negociação')
        GANHO = 'GANHO', _('Ganha')
        PERDIDO = 'PERDIDO', _('Perdida')

    name = models.CharField(_("Nome da Oportunidade"), max_length=255)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='opportunities', verbose_name=_("Conta"))
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name='opportunities', verbose_name=_("Contato Principal"))
    stage = models.CharField(_("Estágio"), max_length=20, choices=StageChoices.choices, default=StageChoices.QUALIFICACAO)
    amount = models.DecimalField(_("Valor Estimado"), max_digits=12, decimal_places=2, null=True, blank=True)
    probability = models.FloatField(_("Probabilidade (%)"), default=0.0, help_text=_("Probabilidade de fechar o negócio"))
    close_date = models.DateField(_("Data de Fechamento Estimada"))
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_opportunities',
        verbose_name=_("Responsável")
    )
    empreendimento = models.ForeignKey(Empreendimento, on_delete=models.SET_NULL, null=True, blank=True, related_name='opportunities_crm')

    def __str__(self):
        return self.name

    class Meta(BaseModel.Meta):
        verbose_name = _("Oportunidade")
        verbose_name_plural = _("Oportunidades")

# 5. Interaction: Registros de contatos e tarefas
class Interaction(BaseModel):
    class TypeChoices(models.TextChoices):
        LIGACAO = 'LIGACAO', _('Ligação')
        EMAIL = 'EMAIL', _('E-mail')
        REUNIAO = 'REUNIAO', _('Reunião')
        TAREFA = 'TAREFA', _('Tarefa')
        OUTRO = 'OUTRO', _('Outro')

    # Relações Genéricas para ligar a qualquer objeto (Lead, Contact, etc)
    # Para simplificar, vamos começar com ForeignKey para Opportunity
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name='interactions', null=True, blank=True)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='interactions', null=True, blank=True)
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='interactions', null=True, blank=True)

    type = models.CharField(_("Tipo de Interação"), max_length=20, choices=TypeChoices.choices)
    subject = models.CharField(_("Assunto"), max_length=255)
    notes = models.TextField(_("Anotações"), blank=True)
    due_date = models.DateTimeField(_("Data/Hora"), null=True, blank=True)
    completed = models.BooleanField(_("Concluída"), default=False)

    # Generic foreign key to link to any other model for assignment
    assigned_to_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    assigned_to_object_id = models.PositiveIntegerField(null=True, blank=True)
    assigned_to = GenericForeignKey('assigned_to_content_type', 'assigned_to_object_id')

    def __str__(self):
        return f"{self.get_type_display()}: {self.subject}"

    class Meta(BaseModel.Meta):
        verbose_name = _("Interação/Tarefa")
        verbose_name_plural = _("Interações/Tarefas")
