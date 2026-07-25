"""Testes do SIL — estoque & logística interna (SIL.1–SIL.3).

Cobre: custo médio ponderado móvel, guarda de saldo insuficiente, a **entrada
automática do Recebimento do SCM** (integração-estrela), reserva/atendimento de
requisição, transferência, devolução, fechamento de inventário, geração de
Demanda (origem=estoque) e isolamento por tenant.
"""
from decimal import Decimal

from rest_framework.test import APITestCase

from catalogo.models import Item
from fornecedores.models import Fornecedor
from moduloscm.models import (
    Demanda,
    ItemPedido,
    ItemRecebimento,
    PedidoCompra,
    Recebimento,
)
from nucleo.models import Tenant, Usuario

from .models import (
    Devolucao,
    Inventario,
    ItemDevolucao,
    ItemInventario,
    ItemRequisicao,
    ItemTransferencia,
    LocalEstoque,
    MovimentacaoEstoque,
    Requisicao,
    SaldoEstoque,
    Transferencia,
)
from . import services

SIL_PERMS_FULL = [
    "sil.local.view", "sil.local.edit",
    "sil.saldo.view", "sil.saldo.edit",
    "sil.movimentacao.view", "sil.movimentacao.edit",
    "sil.requisicao.view", "sil.requisicao.edit", "sil.requisicao.aprovar", "sil.requisicao.atender",
    "sil.transferencia.view", "sil.transferencia.edit", "sil.transferencia.executar",
    "sil.devolucao.view", "sil.devolucao.edit", "sil.devolucao.executar",
    "sil.lote.view", "sil.lote.edit",
    "sil.inventario.view", "sil.inventario.edit", "sil.inventario.fechar",
    "sil.epi.view", "sil.epi.edit",
    "sil.ferramenta.view", "sil.ferramenta.edit",
    "sil.relatorio.view",
]


class SilTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="sil-a", nome="Empresa A")
        cls.tenant_b = Tenant.objects.create(slug="sil-b", nome="Empresa B")
        cls.user = Usuario.objects.create(username="almox_a", tenant=cls.tenant)

    def autenticar(self, user=None, modules=("sil",), perms=SIL_PERMS_FULL):
        user = user or self.user
        user.iam_modules = list(modules)
        user.iam_permissions = list(perms)
        self.client.force_authenticate(user=user)
        return user

    def _item(self, codigo="CIM", estocavel=True, tenant=None):
        return Item.objects.create(tenant=tenant or self.tenant, codigo_interno=codigo, descricao=f"Item {codigo}", unidade="un", estocavel=estocavel)

    def _local(self, nome="Central", tipo=LocalEstoque.Tipo.CENTRAL, tenant=None):
        return LocalEstoque.objects.create(tenant=tenant or self.tenant, nome=nome, tipo=tipo)


class EntitlementTests(SilTestBase):
    def test_sem_modulo_sil_recebe_403(self):
        self.autenticar(modules=[])
        self.assertEqual(self.client.get("/api/sil/locais/").status_code, 403)

    def test_com_modulo_sem_permissao_recebe_403(self):
        self.autenticar(modules=["sil"], perms=[])
        self.assertEqual(self.client.get("/api/sil/locais/").status_code, 403)

    def test_com_modulo_e_permissao_recebe_200(self):
        self.autenticar()
        self.assertEqual(self.client.get("/api/sil/locais/").status_code, 200)


class LocalCrudTests(SilTestBase):
    def test_post_injeta_tenant(self):
        self.autenticar()
        resp = self.client.post("/api/sil/locais/", {"nome": "Almoxarifado Obra 1", "tipo": "canteiro"})
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(LocalEstoque.objects.get(nome="Almoxarifado Obra 1").tenant_id, self.tenant.id)


class CustoMedioTests(SilTestBase):
    def test_entrada_recalcula_custo_medio_ponderado(self):
        self.autenticar()
        item, local = self._item(), self._local()
        base = {"item": item.item_id, "local": local.local_id, "tipo": "entrada"}
        self.client.post("/api/sil/movimentacoes/registrar/", {**base, "quantidade": "100", "custo_unitario": "10"})
        self.client.post("/api/sil/movimentacoes/registrar/", {**base, "quantidade": "100", "custo_unitario": "20"})
        saldo = SaldoEstoque.objects.get(tenant=self.tenant, item=item, local=local)
        self.assertEqual(saldo.quantidade, Decimal("200.000"))
        self.assertEqual(saldo.custo_medio, Decimal("15.0000"))

    def test_saida_insuficiente_da_400(self):
        self.autenticar()
        item, local = self._item(), self._local()
        resp = self.client.post("/api/sil/movimentacoes/registrar/", {"item": item.item_id, "local": local.local_id, "tipo": "saida", "quantidade": "5"})
        self.assertEqual(resp.status_code, 400)

    def test_saida_reduz_saldo(self):
        self.autenticar()
        item, local = self._item(), self._local()
        services.aplicar_entrada(self.tenant.id, item.item_id, local.local_id, 10, 5)
        resp = self.client.post("/api/sil/movimentacoes/registrar/", {"item": item.item_id, "local": local.local_id, "tipo": "saida", "quantidade": "4"})
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(SaldoEstoque.objects.get(item=item, local=local).quantidade, Decimal("6.000"))


class RecebimentoIntegracaoTests(SilTestBase):
    """Integração-estrela: um item de recebimento do SCM entra no estoque."""

    def test_item_recebimento_gera_entrada(self):
        item = self._item(codigo="AC-125")
        local = self._local(nome="Almox Central")
        forn = Fornecedor.objects.create(tenant=self.tenant, razao_social="Alfa", email="a@ex.com")
        pedido = PedidoCompra.objects.create(tenant=self.tenant, origem=PedidoCompra.Origem.MANUAL, fornecedor=forn, status=PedidoCompra.Status.APROVADO)
        ip = ItemPedido.objects.create(tenant=self.tenant, pedido=pedido, produto=item, quantidade=Decimal("50"), preco_unitario=Decimal("12.00"))
        receb = Recebimento.objects.create(tenant=self.tenant, pedido=pedido, tipo=Recebimento.Tipo.TOTAL, local_entrega=str(local.local_id))
        # Cria a linha → o signal deve dar entrada no estoque.
        ItemRecebimento.objects.create(tenant=self.tenant, recebimento=receb, item_pedido=ip, quantidade_recebida=Decimal("50"))
        saldo = SaldoEstoque.objects.get(tenant=self.tenant, item=item, local=local)
        self.assertEqual(saldo.quantidade, Decimal("50.000"))
        self.assertEqual(saldo.custo_medio, Decimal("12.0000"))
        self.assertTrue(MovimentacaoEstoque.objects.filter(tenant=self.tenant, recebimento_scm_ref=receb.recebimento_id, tipo="entrada").exists())

    def test_entrada_de_recebimento_e_idempotente(self):
        item = self._item(codigo="X")
        local = self._local()
        forn = Fornecedor.objects.create(tenant=self.tenant, razao_social="Alfa", email="a@ex.com")
        pedido = PedidoCompra.objects.create(tenant=self.tenant, origem=PedidoCompra.Origem.MANUAL, fornecedor=forn, status=PedidoCompra.Status.APROVADO)
        ip = ItemPedido.objects.create(tenant=self.tenant, pedido=pedido, produto=item, quantidade=Decimal("10"), preco_unitario=Decimal("3"))
        receb = Recebimento.objects.create(tenant=self.tenant, pedido=pedido, tipo=Recebimento.Tipo.TOTAL, local_entrega=str(local.local_id))
        ir = ItemRecebimento.objects.create(tenant=self.tenant, recebimento=receb, item_pedido=ip, quantidade_recebida=Decimal("10"))
        services.registrar_entrada_de_item_recebimento(ir)  # reprocessa: não deve duplicar
        self.assertEqual(MovimentacaoEstoque.objects.filter(tenant=self.tenant, item_recebimento_ref=ir.pk).count(), 1)

    def test_item_servico_nao_gera_entrada(self):
        servico = self._item(codigo="SRV", estocavel=False)
        local = self._local()
        forn = Fornecedor.objects.create(tenant=self.tenant, razao_social="Alfa", email="a@ex.com")
        pedido = PedidoCompra.objects.create(tenant=self.tenant, origem=PedidoCompra.Origem.MANUAL, fornecedor=forn, status=PedidoCompra.Status.APROVADO)
        ip = ItemPedido.objects.create(tenant=self.tenant, pedido=pedido, produto=servico, quantidade=Decimal("1"), preco_unitario=Decimal("100"))
        receb = Recebimento.objects.create(tenant=self.tenant, pedido=pedido, tipo=Recebimento.Tipo.TOTAL, local_entrega=str(local.local_id))
        ItemRecebimento.objects.create(tenant=self.tenant, recebimento=receb, item_pedido=ip, quantidade_recebida=Decimal("1"))
        self.assertFalse(SaldoEstoque.objects.filter(tenant=self.tenant, item=servico).exists())


class RequisicaoTests(SilTestBase):
    def _setup_saldo(self, qtd=100):
        item, local = self._item(), self._local()
        services.aplicar_entrada(self.tenant.id, item.item_id, local.local_id, qtd, 10)
        return item, local

    def test_aprovar_reserva_e_atender_baixa(self):
        item, local = self._setup_saldo(100)
        req = Requisicao.objects.create(tenant=self.tenant, local=local, status=Requisicao.Status.PENDENTE)
        ItemRequisicao.objects.create(tenant=self.tenant, requisicao=req, item=item, quantidade=Decimal("30"))
        self.autenticar()
        # aprovar → reserva
        r1 = self.client.post(f"/api/sil/requisicoes/{req.requisicao_id}/aprovar/")
        self.assertEqual(r1.status_code, 200, r1.content)
        self.assertEqual(SaldoEstoque.objects.get(item=item, local=local).reservado, Decimal("30.000"))
        # atender → baixa + libera reserva
        r2 = self.client.post(f"/api/sil/requisicoes/{req.requisicao_id}/atender/")
        self.assertEqual(r2.status_code, 200, r2.content)
        saldo = SaldoEstoque.objects.get(item=item, local=local)
        self.assertEqual(saldo.quantidade, Decimal("70.000"))
        self.assertEqual(saldo.reservado, Decimal("0.000"))
        req.refresh_from_db()
        self.assertEqual(req.status, Requisicao.Status.ATENDIDA)

    def test_atender_exige_permissao_dedicada(self):
        item, local = self._setup_saldo(50)
        req = Requisicao.objects.create(tenant=self.tenant, local=local, status=Requisicao.Status.APROVADA)
        ItemRequisicao.objects.create(tenant=self.tenant, requisicao=req, item=item, quantidade=Decimal("10"))
        self.autenticar(perms=["sil.requisicao.view", "sil.requisicao.edit"])  # sem .atender
        resp = self.client.post(f"/api/sil/requisicoes/{req.requisicao_id}/atender/")
        self.assertEqual(resp.status_code, 403)


class TransferenciaTests(SilTestBase):
    def test_executar_move_saldo_entre_locais(self):
        item = self._item()
        origem, destino = self._local("Central"), self._local("Obra 1", tipo=LocalEstoque.Tipo.CANTEIRO)
        services.aplicar_entrada(self.tenant.id, item.item_id, origem.local_id, 100, 8)
        transf = Transferencia.objects.create(tenant=self.tenant, origem=origem, destino=destino)
        ItemTransferencia.objects.create(tenant=self.tenant, transferencia=transf, item=item, quantidade=Decimal("40"))
        self.autenticar()
        resp = self.client.post(f"/api/sil/transferencias/{transf.transferencia_id}/executar/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(SaldoEstoque.objects.get(item=item, local=origem).quantidade, Decimal("60.000"))
        d = SaldoEstoque.objects.get(item=item, local=destino)
        self.assertEqual(d.quantidade, Decimal("40.000"))
        self.assertEqual(d.custo_medio, Decimal("8.0000"))  # custo preservado


class DevolucaoTests(SilTestBase):
    def test_devolucao_ao_fornecedor_da_saida(self):
        item, local = self._item(), self._local()
        services.aplicar_entrada(self.tenant.id, item.item_id, local.local_id, 20, 5)
        dev = Devolucao.objects.create(tenant=self.tenant, tipo=Devolucao.Tipo.FORNECEDOR, local=local)
        ItemDevolucao.objects.create(tenant=self.tenant, devolucao=dev, item=item, quantidade=Decimal("5"))
        self.autenticar()
        resp = self.client.post(f"/api/sil/devolucoes/{dev.devolucao_id}/executar/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(SaldoEstoque.objects.get(item=item, local=local).quantidade, Decimal("15.000"))


class InventarioTests(SilTestBase):
    def test_fechar_gera_ajuste(self):
        item, local = self._item(), self._local()
        services.aplicar_entrada(self.tenant.id, item.item_id, local.local_id, 100, 10)
        inv = Inventario.objects.create(tenant=self.tenant, local=local)
        ItemInventario.objects.create(tenant=self.tenant, inventario=inv, item=item, quantidade_sistema=Decimal("100"), quantidade_contada=Decimal("92"))
        self.autenticar()
        resp = self.client.post(f"/api/sil/inventarios/{inv.inventario_id}/fechar/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(SaldoEstoque.objects.get(item=item, local=local).quantidade, Decimal("92.000"))
        inv.refresh_from_db()
        self.assertEqual(inv.status, Inventario.Status.FECHADO)
        self.assertTrue(MovimentacaoEstoque.objects.filter(inventario=inv, tipo="ajuste").exists())


class GerarDemandaTests(SilTestBase):
    def test_gerar_demanda_cria_demanda_de_estoque_no_scm(self):
        item, local = self._item(), self._local()
        saldo = SaldoEstoque.objects.create(tenant=self.tenant, item=item, local=local, quantidade=Decimal("2"), ponto_reposicao=Decimal("10"))
        self.autenticar()
        resp = self.client.post(f"/api/sil/saldos/{saldo.saldo_id}/gerar_demanda/", {"quantidade": "50"})
        self.assertEqual(resp.status_code, 201, resp.content)
        demanda = Demanda.objects.get(pk=resp.data["demanda_id"])
        self.assertEqual(demanda.origem, Demanda.Origem.ESTOQUE)
        self.assertEqual(demanda.tenant_id, self.tenant.id)
        self.assertEqual(demanda.itens.first().produto_id, item.item_id)


class ApropriacaoEtapaTests(SilTestBase):
    """Físico-financeiro: o consumo (saída ao atender requisição) carrega obra E
    etapa, e o endpoint `aplicado` soma por obra/etapa."""

    def test_atender_propaga_obra_e_etapa_para_a_saida(self):
        from empreendimentos.models import Empreendimento
        from obras.models import EtapaObra, Obra
        emp = Empreendimento.objects.create(tenant=self.tenant, empreendimento="E1", razao_social="E1 Ltda", cnpj="11111111000191")
        obra = Obra.objects.create(tenant=self.tenant, empreendimento=emp, nome_obra="Obra 1")
        etapa = EtapaObra.objects.create(tenant=self.tenant, obra=obra, nome_etapa="Fundações", ordem=1)
        item, local = self._item(), self._local()
        services.aplicar_entrada(self.tenant.id, item.item_id, local.local_id, 100, 10)
        req = Requisicao.objects.create(tenant=self.tenant, local=local, obra=obra, etapa=etapa, status=Requisicao.Status.APROVADA)
        ItemRequisicao.objects.create(tenant=self.tenant, requisicao=req, item=item, quantidade=Decimal("40"))
        self.autenticar()
        self.client.post(f"/api/sil/requisicoes/{req.requisicao_id}/atender/")
        mov = MovimentacaoEstoque.objects.get(requisicao=req, tipo="saida")
        self.assertEqual(mov.obra_id, obra.obra_id)
        self.assertEqual(mov.etapa_id, etapa.etapa_id)
        # endpoint aplicado agrega por obra/etapa
        resp = self.client.get("/api/sil/aplicado/")
        self.assertEqual(resp.status_code, 200, resp.content)
        linha = next(r for r in resp.data if r["etapa"] == etapa.etapa_id)
        self.assertEqual(Decimal(linha["aplicado"]), Decimal("400.0000"))  # 40 * 10
        self.assertIsNone(linha["orcado"])  # módulo Orçamento (em breve)


class CurvaABCTests(SilTestBase):
    def test_classifica_a_b_c_por_valor(self):
        local = self._local()
        # A: 900 de valor; B: 90; C: 10 → acum 90%/99%/100%
        for cod, qtd, custo in (("A", 90, 10), ("B", 9, 10), ("C", 1, 10)):
            it = self._item(codigo=cod)
            services.aplicar_entrada(self.tenant.id, it.item_id, local.local_id, qtd, custo)
        self.autenticar()
        resp = self.client.get("/api/sil/curva-abc/")
        self.assertEqual(resp.status_code, 200, resp.content)
        classes = {it["codigo"]: it["classe"] for it in resp.data["itens"]}
        self.assertEqual(classes["A"], "A")
        self.assertEqual(resp.data["resumo"]["A"]["itens"], 1)

    def test_relatorio_exige_permissao(self):
        self.autenticar(perms=["sil.saldo.view"])  # sem sil.relatorio.view
        self.assertEqual(self.client.get("/api/sil/curva-abc/").status_code, 403)


class EPITests(SilTestBase):
    def _epi(self, codigo="CAP"):
        return Item.objects.create(tenant=self.tenant, codigo_interno=codigo, descricao="Capacete", unidade="un", tipo="epi", estocavel=True)

    def test_entrega_epi_baixa_estoque_quando_pedido(self):
        epi, local = self._epi(), self._local()
        services.aplicar_entrada(self.tenant.id, epi.item_id, local.local_id, 10, 20)
        self.autenticar()
        resp = self.client.post("/api/sil/entregas-epi/", {
            "item": epi.item_id, "local": local.local_id, "colaborador_nome": "José",
            "quantidade": "1", "ca_numero": "12345", "baixar_estoque": "true",
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(resp.data["baixou_estoque"])
        self.assertEqual(SaldoEstoque.objects.get(item=epi, local=local).quantidade, Decimal("9.000"))

    def test_epi_exige_permissao_dedicada(self):
        self.autenticar(perms=["sil.saldo.view"])  # sem sil.epi.*
        self.assertEqual(self.client.get("/api/sil/entregas-epi/").status_code, 403)


class FerramentariaTests(SilTestBase):
    def test_emprestar_marca_emprestada_e_devolver_disponibiliza(self):
        from .models import Ferramenta, EmprestimoFerramenta
        self.autenticar()
        rf = self.client.post("/api/sil/ferramentas/", {"nome": "Furadeira", "patrimonio": "F-001"})
        self.assertEqual(rf.status_code, 201, rf.content)
        fid = rf.data["ferramenta_id"]
        re = self.client.post("/api/sil/emprestimos/", {"ferramenta": fid, "colaborador_nome": "Ana"})
        self.assertEqual(re.status_code, 201, re.content)
        self.assertEqual(Ferramenta.objects.get(pk=fid).estado, Ferramenta.Estado.EMPRESTADA)
        eid = re.data["emprestimo_id"]
        rd = self.client.post(f"/api/sil/emprestimos/{eid}/devolver/")
        self.assertEqual(rd.status_code, 200, rd.content)
        self.assertEqual(Ferramenta.objects.get(pk=fid).estado, Ferramenta.Estado.DISPONIVEL)
        self.assertEqual(EmprestimoFerramenta.objects.get(pk=eid).status, EmprestimoFerramenta.Status.DEVOLVIDA)


class IsolamentoTests(SilTestBase):
    def test_saldo_nao_vaza_entre_tenants(self):
        item_a, local_a = self._item("A-1"), self._local("A")
        item_b = self._item("B-1", tenant=self.tenant_b)
        local_b = self._local("B", tenant=self.tenant_b)
        services.aplicar_entrada(self.tenant.id, item_a.item_id, local_a.local_id, 10, 1)
        services.aplicar_entrada(self.tenant_b.id, item_b.item_id, local_b.local_id, 99, 1)
        self.autenticar()
        resp = self.client.get("/api/sil/saldos/")
        self.assertEqual(resp.status_code, 200)
        data = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        locais = {row["local_nome"] for row in data}
        self.assertIn("A", locais)
        self.assertNotIn("B", locais)
