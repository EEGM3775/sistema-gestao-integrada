# backend/nucleo/migrations/0028_decisao_acesso.py
"""Remodelagem da segurança, fase 4: a auditoria de decisão (§10.9).

Sem RLS, pelo mesmo motivo da divergência (0027): a tabela é da plataforma e a
leitura passa pela tela de quem pode auditar. O gatilho barra UPDATE sempre e
DELETE a não ser que a transação tenha se identificado como a purga da janela
do plano (`SET LOCAL sgi.purga_auditoria_decisao = 'on'`, em
`nucleo/auditoria_decisao.py`) — o registro é append-only para todo o resto,
inclusive para quem entrou no banco pela porta dos fundos sem saber a senha.
"""
from django.db import migrations, models

_IMUTAVEL = """
CREATE OR REPLACE FUNCTION nucleo_decisao_imutavel() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('sgi.purga_auditoria_decisao', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'nucleo_decisaoacesso é append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER nucleo_decisao_imutavel
    BEFORE UPDATE OR DELETE ON nucleo_decisaoacesso
    FOR EACH ROW EXECUTE FUNCTION nucleo_decisao_imutavel();
"""

_SEM_IMUTAVEL = """
DROP TRIGGER IF EXISTS nucleo_decisao_imutavel ON nucleo_decisaoacesso;
DROP FUNCTION IF EXISTS nucleo_decisao_imutavel();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("nucleo", "0027_autorizacao_pdp"),
    ]

    operations = [
        migrations.CreateModel(
            name="DecisaoAcesso",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("instante", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("requisicao", models.CharField(blank=True, max_length=64)),
                ("tenant_id", models.UUIDField(null=True)),
                ("usuario_id", models.CharField(max_length=64)),
                ("sid", models.CharField(blank=True, max_length=64)),
                ("acao", models.CharField(max_length=100)),
                ("recurso", models.CharField(max_length=140)),
                ("decisao", models.BooleanField()),
                ("classe", models.CharField(max_length=1)),
                ("origem", models.CharField(max_length=20)),
                ("zedtoken", models.CharField(blank=True, max_length=160)),
            ],
            options={
                "verbose_name": "Decisão de acesso",
                "verbose_name_plural": "Decisões de acesso",
                "ordering": ["-instante"],
                "indexes": [models.Index(fields=["tenant_id", "-instante"], name="authz_dec_tenant_idx")],
            },
        ),
        migrations.RunSQL(_IMUTAVEL, _SEM_IMUTAVEL),
    ]
