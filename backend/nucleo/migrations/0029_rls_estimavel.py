"""D238 — a política `tenant_isolation` passa a ser estimável e indexável.

A forma antiga, `bypass OR tenant_id::text = current_setting(...)`, comparava
texto: o cast na coluna tirava o índice de `tenant_id` do jogo e o planejador,
sem saber estimar a igualdade de texto, supunha uma fração fixa das linhas em
cada tabela. Num JOIN de Contas a receber (86 mil títulos de um tenant só) isso
dava "1 linha" estimada contra 86 mil reais — um nested loop de 110 ms onde o
plano certo leva 1,3 ms. A forma nova compara `uuid` com `uuid`
(`tenant_id = NULLIF(current_setting(...), '')::uuid`): a estimativa sai do
`n_distinct` da coluna e o índice volta a valer.

**A semântica não muda** no domínio que o `nucleo.tenancy` escreve (o UUID
canônico ou vazio): tenant certo vê o próprio, outro tenant não vê, vazio ou
sem contexto não vê nada (fail-closed), bypass vê tudo. Única diferença: um
`app.current_tenant` que não seja UUID passa a dar **erro** na consulta em vez
de zero linhas — falha alta, e ninguém escreve isso.

Reescreve **no lugar** (`ALTER POLICY`) toda política `tenant_isolation` ainda na
forma antiga, qualquer que seja o app; as que já estão na nova ficam. Depende da
última migration de cada app para rodar depois de todas as que criam política.
Política nova, daqui em diante, nasce na forma nova — `test_rls_estimavel` cobra.
"""
from django.db import migrations

POLICY = "tenant_isolation"
ANTIGA = (
    "current_setting('app.rls_bypass', true) = 'on' "
    "OR tenant_id::text = current_setting('app.current_tenant', true)"
)
NOVA = (
    "current_setting('app.rls_bypass', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)
# Como o `pg_policies.qual` mostra cada forma, desmontada pelo Postgres.
_MARCA_ANTIGA = "%(tenant_id)::text = current_setting('app.current_tenant'%"
_MARCA_NOVA = "%NULLIF(current_setting('app.current_tenant'%"


def _reescrever(schema_editor, de, para):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        c.execute(
            "SELECT tablename FROM pg_policies "
            "WHERE schemaname = current_schema() AND policyname = %s AND qual LIKE %s "
            "ORDER BY tablename",
            [POLICY, de],
        )
        for (tabela,) in c.fetchall():
            c.execute(f'ALTER POLICY {POLICY} ON "{tabela}" USING ({para}) WITH CHECK ({para});')


def para_estimavel(apps, schema_editor):
    _reescrever(schema_editor, _MARCA_ANTIGA, NOVA)


def de_volta(apps, schema_editor):
    _reescrever(schema_editor, _MARCA_NOVA, ANTIGA)


class Migration(migrations.Migration):

    dependencies = [
        ("nucleo", "0028_decisao_acesso"),
        ("catalogo", "0006_orc8b_embasa_pdf"),
        ("clientes", "0016_encargos_por_atraso"),
        ("empreendimentos", "0009_remove_empreendimento_empreend_razao_unica_por_tenant_and_more"),
        ("fornecedores", "0006_remove_fornecedor_fornecedor_razao_unica_por_tenant_and_more"),
        ("funcoescobrancas", "0001_initial"),
        ("funcoesia", "0003_alter_analiseimagemia_tenant"),
        ("funcoesimpexp", "0005_ie3_arquivo_em_conferencia"),
        ("funcoeswhatsapp", "0001_initial"),
        ("moduloapi", "0003_alter_googleaccount_tenant"),
        ("modulocalendar", "0006_eventreminder"),
        ("modulocrm", "0009_remove_account_account_name_unico_por_tenant_and_more"),
        ("modulodiario", "0004_alter_diarioobra_tenant_alter_documentodiario_tenant_and_more"),
        ("moduloerp", "0020_configuracao_financeiro"),
        ("modulomaps", "0002_rls_fail_closed"),
        ("moduloorcamento", "0015_orc10_edicao_da_planilha"),
        ("modulopdca", "0023_rls_pdca8"),
        ("moduloprancheta", "0015_pra11_retomada"),
        ("moduloscm", "0005_pdca5_lastplanner"),
        ("modulosil", "0002_movimentacaoestoque_etapa_requisicao_etapa_and_more"),
        ("obras", "0006_remove_obra_unique_obra_empreendimento_and_more"),
        ("rh", "0007_remove_cargo_cargo_nome_unico_por_tenant_and_more"),
    ]

    operations = [
        migrations.RunPython(para_estimavel, de_volta),
    ]
