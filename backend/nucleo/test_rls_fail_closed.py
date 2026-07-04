"""
S2 — prova da RLS **fail-closed** (migration 0010) no PostgreSQL.

Estes testes só têm sentido no Postgres: a RLS é no-op no SQLite (fallback de
dev). São pulados automaticamente fora do Postgres. Rodam como o role `erp_app`
(não superuser, não BYPASSRLS) sobre tabelas em `FORCE ROW LEVEL SECURITY`, então
a política vale de fato — é o cenário real de produção.

Provam o que o S1 (correção pontual) não fechava: **qualquer** caminho sem
contexto de tenant (APIView, comando, task, webhook) não enxerga nem grava linha
alguma — a proteção deixa de depender de a view lembrar do mixin.
"""
import datetime

from django.db import connection, transaction
from django.db.utils import Error as DBError
from django.test import TestCase
from unittest import skipUnless

from clientes.models import Cliente
from nucleo.models import Tenant
from nucleo.tenancy import (
    arm_rls_bypass,
    arm_rls_for_tenant,
    clear_rls_context,
    rls_bypass,
)

IS_POSTGRES = connection.vendor == "postgresql"


@skipUnless(IS_POSTGRES, "RLS só é real no PostgreSQL (no-op no SQLite de dev)")
class RLSFailClosedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(slug="tenant-a", nome="Tenant A")
        cls.tenant_b = Tenant.objects.create(slug="tenant-b", nome="Tenant B")
        # As linhas de negócio precisam de contexto para nascer sob fail-closed;
        # o seed roda sob bypass explícito (papel de plataforma/migração).
        with rls_bypass():
            cls.cli_a = Cliente.objects.create(
                tenant=cls.tenant_a, nome_completo="Cliente A",
                cpf_cnpj="11111111111", email="a@ex.com",
                data_nascimento=datetime.date(1990, 1, 1),
            )
            cls.cli_b = Cliente.objects.create(
                tenant=cls.tenant_b, nome_completo="Cliente B",
                cpf_cnpj="22222222222", email="b@ex.com",
                data_nascimento=datetime.date(1990, 1, 1),
            )

    def test_sem_contexto_nao_enxerga_nada(self):
        """O coração do S2: sessão sem tenant nem bypass → 0 linhas (fail-closed).
        Antes (fail-open), esta mesma consulta devolvia TODAS as linhas."""
        clear_rls_context()
        self.assertEqual(Cliente.objects.count(), 0)

    def test_tenant_armado_ve_so_o_proprio(self):
        arm_rls_for_tenant(self.tenant_a.id)
        ids = set(Cliente.objects.values_list("cliente_id", flat=True))
        self.assertEqual(ids, {self.cli_a.cliente_id})

        arm_rls_for_tenant(self.tenant_b.id)
        ids = set(Cliente.objects.values_list("cliente_id", flat=True))
        self.assertEqual(ids, {self.cli_b.cliente_id})

    def test_bypass_ve_todos(self):
        arm_rls_bypass()
        self.assertEqual(Cliente.objects.count(), 2)

    def test_insert_sem_contexto_e_bloqueado(self):
        """WITH CHECK fail-closed: gravar sem contexto é barrado pelo banco."""
        clear_rls_context()
        with self.assertRaises(DBError):
            with transaction.atomic():
                Cliente.objects.create(
                    tenant=self.tenant_a, nome_completo="Fantasma",
                    cpf_cnpj="33333333333", email="c@ex.com",
                    data_nascimento=datetime.date(1990, 1, 1),
                )

    def test_nao_grava_em_outro_tenant(self):
        """Contexto do tenant A não pode inserir linha do tenant B (WITH CHECK)."""
        arm_rls_for_tenant(self.tenant_a.id)
        with self.assertRaises(DBError):
            with transaction.atomic():
                Cliente.objects.create(
                    tenant=self.tenant_b, nome_completo="Intruso",
                    cpf_cnpj="44444444444", email="d@ex.com",
                    data_nascimento=datetime.date(1990, 1, 1),
                )

    def tearDown(self):
        # Não vaza contexto entre testes (is_local morre no fim da transação,
        # mas limpamos por higiene já que várias asserções compartilham conexão).
        clear_rls_context()
