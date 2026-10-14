"""A migração que dá dono aos dados que já existem — docs/modulos/entidades.md §7.

Roda de verdade: volta o esquema ao estado de antes das entidades, grava dados
como os do staging (a empreitada num empreendimento de terceiro, títulos com
baixa, um centro de custo do SCM com demanda e pedido) e migra para a frente.
É o que vai acontecer no banco com dado real — e o NOT NULL da 0025 do ERP
reprova a migração inteira se sobrar uma linha sem entidade.
"""
from datetime import date
from decimal import Decimal
from unittest import skipUnless

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

ANTES = [
    ("moduloerp", "0023_conta_pagar_da_compra"),
    ("moduloscm", "0008_cobranca_nfe_recebimento"),
    ("obras", "0006_remove_obra_unique_obra_empreendimento_and_more"),
    ("empreendimentos", "0009_remove_empreendimento_empreend_razao_unica_por_tenant_and_more"),
    ("entidades", None),
]
DEPOIS = [
    ("moduloerp", "0025_entidade_obrigatoria"),
    ("moduloscm", "0010_centro_custo_unico_esquema"),
    ("entidades", "0002_dados"),
]


def _bypass(ligado: bool):
    with connection.cursor() as c:
        c.execute("SELECT set_config('app.rls_bypass', %s, false)", ["on" if ligado else ""])


@skipUnless(connection.vendor == "postgresql", "a migração usa a RLS do Postgres")
class MigracaoDasEntidadesTests(TransactionTestCase):
    # Os dados semeados pelas migrations (catálogo, módulos) voltam depois do teste.
    serialized_rollback = True

    def setUp(self):
        _bypass(True)
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(ANTES)
        self.executor.loader.build_graph()

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        _bypass(False)

    def test_dados_de_hoje_ganham_dono(self):
        apps = self.executor.loader.project_state([n for n in ANTES if n[1]]).apps
        Tenant = apps.get_model("nucleo", "Tenant")
        Usuario = apps.get_model("nucleo", "Usuario")
        Empreendimento = apps.get_model("empreendimentos", "Empreendimento")
        Obra = apps.get_model("obras", "Obra")
        Fornecedor = apps.get_model("fornecedores", "Fornecedor")
        Cliente = apps.get_model("clientes", "Cliente")
        ContaPagar = apps.get_model("moduloerp", "ContaPagar")
        Transacao = apps.get_model("moduloerp", "Transacao")
        CentroCustoErp = apps.get_model("moduloerp", "CentroCusto")
        CentroCustoScm = apps.get_model("moduloscm", "CentroCusto")
        Demanda = apps.get_model("moduloscm", "Demanda")
        PedidoCompra = apps.get_model("moduloscm", "PedidoCompra")

        tenant = Tenant.objects.create(slug="eegm-mig", nome="eegm")
        usuario = Usuario.objects.create(username="eegm_mig", tenant=tenant)
        valdick = Cliente.objects.create(
            tenant=tenant, nome_completo="Valdick Figueiredo Souza", cpf_cnpj="02.702.475/0001-55",
            email="v@x.com", data_nascimento=date(1970, 1, 1),
        )
        villa = Empreendimento.objects.create(
            tenant=tenant, empreendimento="Loteamento Villa Privilege", razao_social="VALDICK FIGUEIREDO SOUZA",
            cnpj="02702475000155", telefone="48", endereco="Rua",
        )
        obra = Obra.objects.create(tenant=tenant, nome_obra="Pavimentação", endereco="x", empreendimento=villa)
        fornecedor = Fornecedor.objects.create(tenant=tenant, razao_social="Pedreira", email="p@x.com")
        conta = ContaPagar.objects.create(
            tenant=tenant, fornecedor=fornecedor, descricao="Brita", valor=Decimal("1000"),
            data_vencimento=date(2026, 10, 1), obra=obra, empreendimento=villa,
            valor_pago=Decimal("1000"), status="QUITADO",
        )
        Transacao.objects.create(
            tenant=tenant, conta_pagar=conta, descricao="Baixa", valor=Decimal("1000"), tipo="SAIDA", meio_pagamento="PIX",
        )
        cc_erp = CentroCustoErp.objects.create(tenant=tenant, nome="Pavimentação", obra=obra)
        cc_scm = CentroCustoScm.objects.create(tenant=tenant, nome="Pavimentação", obra=obra, tipo="obra")
        cc_almox = CentroCustoScm.objects.create(tenant=tenant, nome="Almoxarifado", tipo="almoxarifado", local_estoque_ref="A1")
        demanda = Demanda.objects.create(tenant=tenant, centro_custo=cc_scm)
        pedido = PedidoCompra.objects.create(tenant=tenant, fornecedor=fornecedor, centro_custo=cc_almox)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(DEPOIS)
        apps = executor.loader.project_state(DEPOIS).apps
        Entidade = apps.get_model("entidades", "Entidade")
        ConcessaoEntidade = apps.get_model("entidades", "ConcessaoEntidade")
        ConcessaoEmpreendimento = apps.get_model("entidades", "ConcessaoEmpreendimento")

        matriz = Entidade.objects.get(tenant_id=tenant.pk, papel="matriz")
        self.assertEqual((matriz.nome, matriz.externa, matriz.documento), ("eegm", False, ""))

        dono = apps.get_model("empreendimentos", "Empreendimento").objects.get(pk=villa.pk).entidade_propria
        self.assertEqual((dono.documento, dono.externa, dono.cliente_id), ("02702475000155", True, valdick.pk))

        # A obra e o dinheiro ficam com quem executa: a matriz, não o dono de fora.
        self.assertEqual(apps.get_model("obras", "Obra").objects.get(pk=obra.pk).entidade_id, matriz.pk)
        self.assertEqual(apps.get_model("moduloerp", "ContaPagar").objects.get(pk=conta.pk).entidade_id, matriz.pk)
        self.assertEqual(apps.get_model("moduloerp", "Transacao").objects.get(conta_pagar_id=conta.pk).entidade_id, matriz.pk)

        # O centro de custo do SCM com o mesmo nome e obra virou o do ERP; o outro foi criado.
        Demanda2 = apps.get_model("moduloscm", "Demanda")
        Pedido2 = apps.get_model("moduloscm", "PedidoCompra")
        CC = apps.get_model("moduloerp", "CentroCusto")
        self.assertEqual(Demanda2.objects.get(pk=demanda.pk).centro_custo_id, cc_erp.pk)
        almox = CC.objects.get(pk=Pedido2.objects.get(pk=pedido.pk).centro_custo_id)
        self.assertEqual((almox.nome, almox.tipo, almox.local_estoque_ref, almox.entidade_id), ("Almoxarifado", "almoxarifado", "A1", matriz.pk))
        self.assertEqual(CC.objects.get(pk=cc_erp.pk).tipo, "obra")

        # Ninguém perde o que via.
        self.assertTrue(ConcessaoEntidade.objects.filter(usuario_id=usuario.pk, entidade=matriz).exists())
        self.assertTrue(ConcessaoEmpreendimento.objects.filter(usuario_id=usuario.pk, empreendimento_id=villa.pk).exists())
