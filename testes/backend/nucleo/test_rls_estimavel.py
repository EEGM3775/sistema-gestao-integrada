"""D238 — a política `tenant_isolation` na forma estimável (migration `nucleo 0029`).

Três provas, e nenhuma depende de lembrar de olhar:

1. **Toda** política do banco está na forma nova — inclusive a de uma tabela que
   nasça amanhã copiando o texto antigo de outra migration (o padrão da casa é
   repetir o helper). Esta é a trava.
2. As duas expressões, **exatamente como a migration as grava**, dão o mesmo
   resultado em todo caso que o `nucleo.tenancy` produz: tenant certo, outro
   tenant, vazio, nunca definido — com bypass ligado, desligado, vazio e nulo.
3. O motivo da troca: sob a RLS, o planejador volta a estimar a parte do tenant
   pelo `n_distinct` da coluna. Na forma antiga, com o cast para texto, ele
   supunha ~1% das linhas, e todo JOIN grande ia para nested loop.

O isolamento em si (fail-closed, WITH CHECK, bypass) segue provado pelas tabelas
reais em `test_rls_fail_closed` e `test_tenant_isolation`, que rodam sobre a
política nova.
"""
import datetime
import importlib
import itertools
import json
import uuid
from unittest import skipUnless

from django.db import connection
from django.test import SimpleTestCase, TestCase

from clientes.models import Cliente
from nucleo.models import Tenant
from nucleo.tenancy import arm_rls_for_tenant, clear_rls_context, rls_bypass

IS_POSTGRES = connection.vendor == "postgresql"
MIGRATION = importlib.import_module("nucleo.migrations.0029_rls_estimavel")


@skipUnless(IS_POSTGRES, "RLS só é real no PostgreSQL")
class TodaPoliticaEstimavelTests(TestCase):
    def test_nenhuma_politica_na_forma_antiga(self):
        with connection.cursor() as c:
            c.execute(
                "SELECT tablename, qual, with_check FROM pg_policies "
                "WHERE schemaname = current_schema() AND policyname = %s",
                [MIGRATION.POLICY],
            )
            politicas = c.fetchall()
        self.assertGreater(len(politicas), 150, "as políticas sumiram?")
        fora = [
            tabela for tabela, qual, check in politicas
            if "NULLIF(current_setting('app.current_tenant'" not in qual
            or "::text = current_setting('app.current_tenant'" in qual
            or check != qual
        ]
        self.assertEqual(
            fora, [],
            "política tenant_isolation fora da forma estimável (D238): use a expressão "
            "de nucleo/migrations/0029_rls_estimavel.py ao criar RLS numa tabela nova",
        )


@skipUnless(IS_POSTGRES, "RLS só é real no PostgreSQL")
class ExpressaoEquivalenteTests(SimpleTestCase):
    """A antiga e a nova, com `current_setting` trocado por parâmetro — assim o
    caso "nunca definido" (NULL) entra, que `set_config` não sabe produzir."""

    databases = {"default"}

    @staticmethod
    def _parametrizar(expressao):
        return (
            expressao
            .replace("current_setting('app.current_tenant', true)", "%(tenant)s::text")
            .replace("current_setting('app.rls_bypass', true)", "%(bypass)s::text")
        )

    def _avaliar(self, expressao, tenant_id, tenant, bypass):
        sql = f"SELECT ({self._parametrizar(expressao)}) IS TRUE FROM (SELECT %(tid)s::uuid AS tenant_id) AS linha"
        with connection.cursor() as c:
            c.execute(sql, {"tid": str(tenant_id), "tenant": tenant, "bypass": bypass})
            return c.fetchone()[0]

    def test_mesmo_resultado_em_todo_caso(self):
        dono, outro = uuid.uuid4(), uuid.uuid4()
        tenants = {"o próprio": str(dono), "outro": str(outro), "vazio": "", "nunca definido": None}
        bypasses = {"on": "on", "off": "off", "vazio": "", "nunca definido": None}
        for (nome_t, tenant), (nome_b, bypass) in itertools.product(tenants.items(), bypasses.items()):
            with self.subTest(tenant=nome_t, bypass=nome_b):
                antiga = self._avaliar(MIGRATION.ANTIGA, dono, tenant, bypass)
                nova = self._avaliar(MIGRATION.NOVA, dono, tenant, bypass)
                self.assertEqual(nova, antiga)
                # E o que as duas dizem é o desenho: só o bypass ou o próprio tenant abrem.
                self.assertEqual(nova, bypass == "on" or nome_t == "o próprio")


@skipUnless(IS_POSTGRES, "RLS só é real no PostgreSQL")
class PlanejadorEstimaATenantTests(TestCase):
    TOTAL = 300

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(slug="estima-a", nome="Estima A")
        cls.tenant_b = Tenant.objects.create(slug="estima-b", nome="Estima B")
        with rls_bypass():
            for tenant, inicio in ((cls.tenant_a, 0), (cls.tenant_b, cls.TOTAL)):
                Cliente.objects.bulk_create([
                    Cliente(
                        tenant=tenant, nome_completo=f"Cliente {i}", cpf_cnpj=f"{i:011d}",
                        email=f"c{i}@ex.com", data_nascimento=datetime.date(1990, 1, 1),
                    )
                    for i in range(inicio, inicio + cls.TOTAL)
                ])

    def test_a_estimativa_sob_rls_acompanha_a_parte_do_tenant(self):
        with connection.cursor() as c:
            c.execute(f'ANALYZE "{Cliente._meta.db_table}"')
        arm_rls_for_tenant(self.tenant_a.id)
        with connection.cursor() as c:
            c.execute(f'EXPLAIN (FORMAT JSON) SELECT cliente_id FROM "{Cliente._meta.db_table}"')
            plano = c.fetchone()[0]
        plano = json.loads(plano) if isinstance(plano, str) else plano
        estimadas = plano[0]["Plan"]["Plan Rows"]
        # Metade da tabela é do tenant A. A forma antiga estimava ~1% (6 linhas).
        self.assertGreater(estimadas, self.TOTAL // 2, plano)

    def tearDown(self):
        clear_rls_context()
