# backend/funcoeswhatsapp/models.py
"""
Configuração do canal WhatsApp por tenant (Fase 11.3 / Fase C).

Uma conta WhatsApp Business (Meta Cloud API) pode atender vários tenants; o
payload do webhook traz o `metadata.phone_number_id` que **recebeu** a mensagem.
Esse id é a chave de resolução determinística (1:1) do tenant — daí o `unique`
**global** (intencional; não é um dado de negócio escopado por tenant, e sim a
rota de entrada). Ver docs/modulos/funcoeswhatsapp.md §4.1.

Credenciais da Meta (access token, app secret, verify token) são **secretas** e
ficam por tenant; a gestão em cofre entra na Fase 10.3 (por ora, campo no
modelo). O modelo herda `TenantScopedModel` (RLS + tenant NOT NULL).
"""
from django.db import models
from django.utils.translation import gettext_lazy as _

from nucleo.tenancy import TenantScopedModel


class CanalWhatsApp(TenantScopedModel):
    canal_id = models.AutoField(primary_key=True)
    phone_number_id = models.CharField(
        _("Phone Number ID (Meta)"), max_length=64, unique=True,
        help_text=_("Identificador do número na Meta Cloud API; chave de resolução do tenant."),
    )
    nome_exibicao = models.CharField(_("Nome de exibição"), max_length=120, blank=True)
    # Segredos da Meta (por tenant). Fase 10.3 move para cofre de segredos.
    access_token = models.CharField(_("Access Token (Meta)"), max_length=512, blank=True)
    app_secret = models.CharField(_("App Secret (Meta)"), max_length=255, blank=True)
    verify_token = models.CharField(_("Verify Token (webhook)"), max_length=255, blank=True)
    api_version = models.CharField(_("Versão da Graph API"), max_length=10, default='v20.0')
    ativo = models.BooleanField(_("Ativo"), default=True)
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Canal WhatsApp")
        verbose_name_plural = _("Canais WhatsApp")

    def __str__(self):
        return f"{self.nome_exibicao or self.phone_number_id} (tenant {self.tenant_id})"
