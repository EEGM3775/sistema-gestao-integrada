"""
Ativa Row-Level Security (RLS) por tenant em todas as tabelas de negócio
(defesa em profundidade — Fase 0.3d). É no-op fora do PostgreSQL (ex.: SQLite
de dev), pois RLS é específico do Postgres.

A política libera quando `app.current_tenant` não está definido (migrações,
admin, callbacks de microserviço), e caso contrário exige `tenant_id` igual ao
tenant da sessão. O valor é definido por requisição pelo TenantScopedViewSetMixin.

Tabelas de identidade (app `nucleo`, incl. Usuario) ficam de fora para não
quebrar a autenticação/provisionamento JIT.
"""
from django.db import migrations

EXCLUDED_APPS = {"nucleo"}
POLICY = "tenant_isolation"


def _tenant_tables(apps):
    tables = []
    for model in apps.get_models():
        if model._meta.app_label in EXCLUDED_APPS:
            continue
        try:
            field = model._meta.get_field("tenant")
        except Exception:
            continue
        if getattr(field, "is_relation", False):
            tables.append(model._meta.db_table)
    return tables


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in _tenant_tables(apps):
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
            cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;')
            cursor.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{table}";')
            cursor.execute(
                f'''
                CREATE POLICY {POLICY} ON "{table}"
                USING (
                    current_setting('app.current_tenant', true) IS NULL
                    OR current_setting('app.current_tenant', true) = ''
                    OR tenant_id::text = current_setting('app.current_tenant', true)
                )
                WITH CHECK (
                    current_setting('app.current_tenant', true) IS NULL
                    OR current_setting('app.current_tenant', true) = ''
                    OR tenant_id::text = current_setting('app.current_tenant', true)
                );
                '''
            )


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in _tenant_tables(apps):
            cursor.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{table}";')
            cursor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("nucleo", "0006_tenant_usuario_is_tenant_admin_usuario_tenant"),
        ("clientes", "0005_cliente_tenant_clienteempreendimento_tenant_and_more"),
        ("empreendimentos", "0002_contabancariaempreendimento_tenant_and_more"),
        ("fornecedores", "0002_dadobancariofornecedor_tenant_fornecedor_tenant_and_more"),
        ("funcoesia", "0002_analiseimagemia_tenant"),
        ("moduloapi", "0002_googleaccount_tenant"),
        ("modulocalendar", "0002_calendarevent_tenant"),
        ("modulocrm", "0005_account_tenant_contact_tenant_interaction_tenant_and_more"),
        ("modulodiario", "0002_diarioobra_tenant_documentodiario_tenant"),
        ("moduloerp", "0007_boleto_tenant_cobrancacliente_tenant_and_more"),
        ("obras", "0003_documentoobra_tenant_etapaobra_tenant_obra_tenant"),
        ("rh", "0003_cargo_tenant_dadobancariofuncionario_tenant_and_more"),
    ]

    operations = [migrations.RunPython(enable_rls, disable_rls)]
