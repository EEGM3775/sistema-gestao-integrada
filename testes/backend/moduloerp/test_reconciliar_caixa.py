"""O caixa tem de bater com os títulos pagos (item 88 do dono).

O fluxo de caixa lê o ledger (`Transacao`). Título quitado por fora da baixa
sumia do fluxo; `reconciliar_caixa` acha e lança o que falta.
"""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase

from clientes.models import Cliente
from moduloerp.models import ContaReceber, StatusConta, Transacao
from nucleo.models import Tenant
from nucleo.tenancy import rls_bypass


class ReconciliarCaixaTests(TestCase):
    def setUp(self):
        with rls_bypass():
            self.tenant = Tenant.objects.create(slug="caixa-rec", nome="Caixa")
            cliente = Cliente.objects.create(
                tenant=self.tenant, nome_completo="Comprador", cpf_cnpj="52998224725",
                data_nascimento=date(1980, 1, 1),
            )
            self.quitado = ContaReceber.objects.create(
                tenant=self.tenant, cliente=cliente, descricao="Parcela 1", valor=Decimal("1000"),
                valor_pago=Decimal("1000"), status=StatusConta.QUITADO,
                data_vencimento=date(2026, 3, 10), data_recebimento=date(2026, 3, 10),
            )

    def _total(self):
        with rls_bypass():
            return Transacao.objects.filter(conta_receber=self.quitado).aggregate(s=Sum("valor"))["s"]

    def test_sem_aplicar_so_relata(self):
        saida = StringIO()
        call_command("reconciliar_caixa", stdout=saida)
        self.assertIn("1 sem lançamento", saida.getvalue())
        self.assertIsNone(self._total())

    def test_aplicar_lanca_o_que_falta_e_e_idempotente(self):
        call_command("reconciliar_caixa", "--aplicar", stdout=StringIO())
        self.assertEqual(self._total(), Decimal("1000"))
        call_command("reconciliar_caixa", "--aplicar", stdout=StringIO())
        self.assertEqual(self._total(), Decimal("1000"))
