"""Testes da trilha de auditoria — Fase 9.E.

Cobre a fundação: gravação via helper, imutabilidade (`save`/`delete` bloqueados)
e o fail-safe sem tenant. Arma o contexto RLS (`tenant_context`) para o INSERT
passar sob o runner Postgres fail-closed (banco de teste único do projeto).

O E2E (RH cria funcionário → linha na trilha; leitura só com
`plataforma.auditoria.view`) vive no `phase9_field_mask_test.py` / testes DRF.
"""
from django.db import IntegrityError
from django.test import TestCase

from nucleo.auditoria import registrar_auditoria
from nucleo.models import AuditLog, Tenant
from nucleo.tenancy import tenant_context


class AuditoriaHelperTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="acme", nome="ACME")

    def test_registrar_grava_linha(self):
        with tenant_context(self.tenant.id):
            log = registrar_auditoria(
                acao="baixa", modelo="moduloerp.ContaReceber", objeto_id="7",
                tenant=self.tenant, detalhes={"valor": "100.00", "origem": "manual"},
            )
            self.assertIsNotNone(log)
            self.assertEqual(log.acao, "baixa")
            self.assertEqual(log.objeto_id, "7")
            self.assertEqual(AuditLog.objects.filter(pk=log.pk).count(), 1)

    def test_sem_tenant_nao_grava_mas_nao_quebra(self):
        # Fail-safe: sem tenant a auditoria é ignorada (retorna None), sem erro.
        self.assertIsNone(registrar_auditoria(acao="criar", modelo="x", objeto_id="1"))
        self.assertEqual(AuditLog.objects.count(), 0)


class AuditoriaImutabilidadeTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="acme", nome="ACME")

    def test_update_bloqueado(self):
        with tenant_context(self.tenant.id):
            log = registrar_auditoria(acao="criar", modelo="rh.Funcionario",
                                      objeto_id="1", tenant=self.tenant)
            log.acao = "excluir"
            with self.assertRaises(IntegrityError):
                log.save()

    def test_delete_bloqueado(self):
        with tenant_context(self.tenant.id):
            log = registrar_auditoria(acao="criar", modelo="rh.Funcionario",
                                      objeto_id="2", tenant=self.tenant)
            with self.assertRaises(IntegrityError):
                log.delete()
