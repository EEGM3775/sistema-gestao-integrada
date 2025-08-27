# backend/modulocrm/admin.py
from django.contrib import admin
from .models import Lead, Account, Contact, Opportunity, Interaction

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'status', 'source', 'assigned_to', 'created_at')
    list_filter = ('status', 'source', 'assigned_to', 'created_at')
    search_fields = ('first_name', 'last_name', 'email', 'company')
    raw_id_fields = ('assigned_to',)
    date_hierarchy = 'created_at'

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'industry', 'assigned_to', 'created_at')
    list_filter = ('industry', 'assigned_to')
    search_fields = ('name', 'email', 'website')
    raw_id_fields = ('assigned_to', 'cliente_associado')

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'account', 'email', 'phone', 'title')
    list_filter = ('account', 'title')
    search_fields = ('first_name', 'last_name', 'email', 'account__name')
    raw_id_fields = ('account', 'cliente_associado')

@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ('name', 'account', 'stage', 'amount', 'probability', 'close_date', 'assigned_to')
    list_filter = ('stage', 'assigned_to', 'close_date', 'empreendimento')
    search_fields = ('name', 'account__name', 'contact__first_name', 'contact__last_name')
    raw_id_fields = ('account', 'contact', 'assigned_to', 'empreendimento')
    date_hierarchy = 'close_date'

@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ('subject', 'type', 'opportunity', 'contact', 'lead', 'due_date', 'completed')
    list_filter = ('type', 'completed', 'due_date')
    search_fields = ('subject', 'notes', 'opportunity__name', 'contact__first_name', 'lead__first_name')
    raw_id_fields = ('opportunity', 'contact', 'lead')
    date_hierarchy = 'due_date'
