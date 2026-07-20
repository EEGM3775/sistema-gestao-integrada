# backend/funcoeswhatsapp/tenant_resolver.py
"""
Resolução de tenant na borda do webhook (Fase C, §4.1).

`metadata.phone_number_id` → `CanalWhatsApp` → tenant. O lookup roda sob
`rls_bypass()` porque a borda ainda **não** tem contexto de tenant (é o próprio
canal que o determina). Número desconhecido → `None` (o webhook descarta sem
vazar existência).

Dev/single-tenant: sem `CanalWhatsApp` no banco, cai para um canal efêmero
montado a partir de `settings.WHATSAPP_DEFAULT_*` (andaime de dev, aposentado
antes do go-live).
"""
from django.conf import settings

from nucleo.tenancy import rls_bypass


def resolver_canal(phone_number_id):
    """Retorna o `CanalWhatsApp` (persistido ou efêmero de dev) do
    `phone_number_id`, ou `None` se desconhecido/ inativo."""
    if not phone_number_id:
        return None

    from .models import CanalWhatsApp

    with rls_bypass():
        canal = (
            CanalWhatsApp.objects
            .select_related('tenant')
            .filter(phone_number_id=phone_number_id, ativo=True)
            .first()
        )
    if canal is not None:
        return canal
    return _canal_dev_fallback(phone_number_id)


def _canal_dev_fallback(phone_number_id):
    """Canal efêmero a partir de `settings` — só em DEBUG e só para o número
    default configurado. Não é persistido; serve o fluxo de dev single-tenant."""
    if not settings.DEBUG:
        return None
    default_pnid = getattr(settings, 'WHATSAPP_DEFAULT_PHONE_NUMBER_ID', '')
    slug = getattr(settings, 'WHATSAPP_DEFAULT_TENANT_SLUG', '')
    if not (default_pnid and slug and phone_number_id == default_pnid):
        return None

    from nucleo.models import Tenant
    from .models import CanalWhatsApp

    with rls_bypass():
        tenant = Tenant.objects.filter(slug=slug).first()
    if tenant is None:
        return None
    # Instância não salva: só leitura de credenciais/tenant pelo pipeline.
    return CanalWhatsApp(
        tenant=tenant,
        phone_number_id=default_pnid,
        access_token=getattr(settings, 'WHATSAPP_DEFAULT_ACCESS_TOKEN', ''),
        app_secret=getattr(settings, 'WHATSAPP_DEFAULT_APP_SECRET', ''),
        verify_token=getattr(settings, 'WHATSAPP_DEFAULT_VERIFY_TOKEN', ''),
    )
