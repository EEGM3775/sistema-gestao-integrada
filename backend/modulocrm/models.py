# backend/modulocrm/models.py
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from clientes.models import Cliente
from empreendimentos.models import Empreendimento
from fornecedores.models import ProdutoServicoFornecedor
from nucleo.tenancy import TenantScopedModel
import logging

logger = logging.getLogger(__name__)

# Modelo Base Abstrato para campos comuns
class BaseModel(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(_("Data de Criação"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Última Atualização"), auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


# 1. Campaign: A marketing campaign
class Campaign(BaseModel):
    name = models.CharField(_("Nome da Campanha"), max_length=255)
    description = models.TextField(_("Descrição"), blank=True)
    start_date = models.DateField(_("Data de Início"))
    end_date = models.DateField(_("Data de Fim"))
    budget = models.DecimalField(_("Orçamento"), max_digits=12, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta(BaseModel.Meta):
        verbose_name = _("Campanha")
        verbose_name_plural = _("Campanhas")


# 2. Lead: O ponto de entrada do funil
class Lead(BaseModel):
    class StatusChoices(models.TextChoices):
        NOVO = 'NOVO', _('Novo')
        CONTATADO = 'CONTATADO', _('Contatado')
        QUALIFICADO = 'QUALIFICADO', _('Qualificado')
        CONVERTIDO = 'CONVERTIDO', _('Convertido')
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
    score = models.IntegerField(_("Pontuação"), default=0, help_text=_("Pontuação do Lead gerada por IA ou regras"))
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True, blank=True, related_name='leads', verbose_name=_("Campanha"))

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

    @property
    def amount(self):
        """Calculates the total amount from related products."""
        return self.products.aggregate(
            total=models.Sum(models.F('quantity') * models.F('unit_price'))
        )['total'] or 0

    def __str__(self):
        return self.name

    class Meta(BaseModel.Meta):
        verbose_name = _("Oportunidade")
        verbose_name_plural = _("Oportunidades")


# 4.1. OpportunityProduct: The products/services associated with an opportunity
class OpportunityProduct(BaseModel):
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name='products', verbose_name=_("Oportunidade"))
    product = models.ForeignKey(ProdutoServicoFornecedor, on_delete=models.PROTECT, related_name='opportunity_products', verbose_name=_("Produto/Serviço"))
    quantity = models.DecimalField(_("Quantidade"), max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(_("Preço Unitário"), max_digits=12, decimal_places=2, help_text=_("Preço no momento da adição. Pode ser diferente do catálogo."))

    def __str__(self):
        return f"{self.quantity} x {self.product.nome_produto_servico} @ {self.opportunity.name}"

    class Meta(BaseModel.Meta):
        verbose_name = _("Produto da Oportunidade")
        verbose_name_plural = _("Produtos da Oportunidade")
        unique_together = (('opportunity', 'product'),)


from .signals import interaction_changed
from nucleo.models import Usuario

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

    def _get_user_id(self):
        assigned_object = self.assigned_to

        # Caso 1: Atribuído diretamente a um usuário
        if isinstance(assigned_object, Usuario):
            return assigned_object.id

        # Caso 2: Atribuído a um Lead, encontrar o usuário responsável pelo Lead
        if isinstance(assigned_object, Lead):
            if assigned_object.assigned_to:
                return assigned_object.assigned_to.id

        # Adicionar outros casos se necessário (ex: Contato, Oportunidade)

        return None

    def save(self, *args, **kwargs):
        old_user_id = None
        if self.pk:
            try:
                old_instance = Interaction.objects.get(pk=self.pk)
                old_user_id = old_instance._get_user_id()
            except Interaction.DoesNotExist:
                pass

        super().save(*args, **kwargs)
        new_user_id = self._get_user_id()

        if old_user_id and old_user_id != new_user_id:
            interaction_changed.send(sender=self.__class__, user_id=old_user_id)
        
        if new_user_id:
            interaction_changed.send(sender=self.__class__, user_id=new_user_id)

    def delete(self, *args, **kwargs):
        user_id = self._get_user_id()
        super().delete(*args, **kwargs)
        if user_id:
            interaction_changed.send(sender=self.__class__, user_id=user_id)

    class Meta(BaseModel.Meta):
        verbose_name = _("Interação/Tarefa")
        verbose_name_plural = _("Interações/Tarefas")
