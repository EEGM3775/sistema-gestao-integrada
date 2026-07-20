"""Testes do SCM — fatia 1 (catálogo + centro de custo).

Cobre o contrato de módulo novo (migracao-v01 §5.4): isolamento por tenant,
entitlement (`RequireModule`), permissão (`RequirePermission`, camada 2),
unicidade por-tenant e `tenant` read-only no POST. Desenho em
docs/expansão/modulos/moduloscm.md.
"""
from decimal import Decimal

from rest_framework.test import APITestCase

from fornecedores.models import Fornecedor
from nucleo.models import Tenant, Usuario

from .models import (
    CentroCusto,
    Cotacao,
    Demanda,
    ItemDemanda,
    ItemProposta,
    OfertaFornecedor,
    PedidoCompra,
    Produto,
    Proposta,
    Recebimento,
)

SCM_PERMS_FULL = [
    "scm.produto.view", "scm.produto.edit",
    "scm.oferta.view", "scm.oferta.edit",
    "scm.centro_custo.view", "scm.centro_custo.edit",
    "scm.demanda.view", "scm.demanda.edit", "scm.demanda.publicar",
    "scm.cotacao.view", "scm.cotacao.edit", "scm.cotacao.adjudicar",
    "scm.pedido.view", "scm.pedido.edit", "scm.pedido.criar",
    "scm.recebimento.view", "scm.recebimento.edit",
    "scm.avaliacao.view", "scm.avaliacao.edit",
]


class ScmTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="emp-a", nome="Empresa A")
        cls.tenant_b = Tenant.objects.create(slug="emp-b", nome="Empresa B")
        cls.user = Usuario.objects.create(username="comprador_a", tenant=cls.tenant)

    def autenticar(self, user=None, modules=("scm",), perms=SCM_PERMS_FULL):
        user = user or self.user
        user.iam_modules = list(modules)
        user.iam_permissions = list(perms)
        self.client.force_authenticate(user=user)
        return user


class EntitlementTests(ScmTestBase):
    def test_sem_modulo_scm_recebe_403(self):
        self.autenticar(modules=[])
        resp = self.client.get("/api/scm/produtos/")
        self.assertEqual(resp.status_code, 403)

    def test_com_modulo_sem_permissao_recebe_403(self):
        self.autenticar(modules=["scm"], perms=[])
        resp = self.client.get("/api/scm/produtos/")
        self.assertEqual(resp.status_code, 403)

    def test_com_modulo_e_permissao_recebe_200(self):
        self.autenticar()
        resp = self.client.get("/api/scm/produtos/")
        self.assertEqual(resp.status_code, 200)


class ProdutoCrudTests(ScmTestBase):
    def test_post_injeta_tenant_do_usuario(self):
        self.autenticar()
        resp = self.client.post("/api/scm/produtos/", {
            "codigo_interno": "CIM-50", "descricao": "Cimento CPII 50kg", "unidade": "sc",
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        produto = Produto.objects.get(codigo_interno="CIM-50")
        self.assertEqual(produto.tenant_id, self.tenant.id)

    def test_tenant_no_payload_e_ignorado(self):
        self.autenticar()
        resp = self.client.post("/api/scm/produtos/", {
            "codigo_interno": "VER-10", "descricao": "Vergalhão CA-50 10mm", "unidade": "m",
            "tenant": self.tenant_b.id,  # deve ser ignorado (read-only)
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(Produto.objects.get(codigo_interno="VER-10").tenant_id, self.tenant.id)


class IsolamentoTenantTests(ScmTestBase):
    def test_lista_nao_vaza_produto_de_outro_tenant(self):
        Produto.objects.create(tenant=self.tenant, codigo_interno="A-1", descricao="Item A", unidade="un")
        Produto.objects.create(tenant=self.tenant_b, codigo_interno="B-1", descricao="Item B", unidade="un")
        self.autenticar()
        resp = self.client.get("/api/scm/produtos/")
        self.assertEqual(resp.status_code, 200)
        data = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        codigos = {p["codigo_interno"] for p in data}
        self.assertIn("A-1", codigos)
        self.assertNotIn("B-1", codigos)

    def test_nao_acessa_detalhe_de_outro_tenant(self):
        alheio = Produto.objects.create(tenant=self.tenant_b, codigo_interno="B-2", descricao="Item B", unidade="un")
        self.autenticar()
        resp = self.client.get(f"/api/scm/produtos/{alheio.produto_id}/")
        self.assertEqual(resp.status_code, 404)


class UnicidadePorTenantTests(ScmTestBase):
    def test_codigo_interno_duplicado_no_mesmo_tenant_da_400(self):
        Produto.objects.create(tenant=self.tenant, codigo_interno="DUP", descricao="X", unidade="un")
        self.autenticar()
        resp = self.client.post("/api/scm/produtos/", {
            "codigo_interno": "DUP", "descricao": "Y", "unidade": "un",
        })
        self.assertEqual(resp.status_code, 400)

    def test_mesmo_codigo_em_tenants_distintos_e_permitido(self):
        Produto.objects.create(tenant=self.tenant_b, codigo_interno="COMPART", descricao="X", unidade="un")
        self.autenticar()
        resp = self.client.post("/api/scm/produtos/", {
            "codigo_interno": "COMPART", "descricao": "Y", "unidade": "un",
        })
        self.assertEqual(resp.status_code, 201, resp.content)


class OfertaTests(ScmTestBase):
    def setUp(self):
        self.produto = Produto.objects.create(tenant=self.tenant, codigo_interno="P1", descricao="Item", unidade="un")
        self.fornecedor = Fornecedor.objects.create(tenant=self.tenant, razao_social="Fornecedora Alfa", email="alfa@ex.com")

    def test_estoque_reservado_e_read_only(self):
        self.autenticar()
        resp = self.client.post("/api/scm/ofertas/", {
            "produto": self.produto.produto_id, "fornecedor": self.fornecedor.fornecedor_id,
            "preco_direto": "10.00", "estoque_disponivel": "100.000",
            "estoque_reservado": "50.000",  # deve ser ignorado (system-managed)
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        oferta = OfertaFornecedor.objects.get(oferta_id=resp.data["oferta_id"])
        self.assertEqual(oferta.estoque_reservado, Decimal("0.000"))
        self.assertEqual(oferta.estoque_livre, Decimal("100.000"))

    def test_oferta_unica_por_produto_fornecedor_no_tenant(self):
        OfertaFornecedor.objects.create(
            tenant=self.tenant, produto=self.produto, fornecedor=self.fornecedor, preco_direto=Decimal("10.00"),
        )
        self.autenticar()
        resp = self.client.post("/api/scm/ofertas/", {
            "produto": self.produto.produto_id, "fornecedor": self.fornecedor.fornecedor_id,
            "preco_direto": "12.00",
        })
        self.assertEqual(resp.status_code, 400)


class CentroCustoTests(ScmTestBase):
    def test_cria_centro_custo_administrativo_sem_vinculo(self):
        self.autenticar()
        resp = self.client.post("/api/scm/centros-custo/", {
            "nome": "Almoxarifado Central", "tipo": CentroCusto.Tipo.ALMOXARIFADO,
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        cc = CentroCusto.objects.get(pk=resp.data["centro_custo_id"])
        self.assertEqual(cc.tenant_id, self.tenant.id)
        self.assertEqual(cc.tipo, CentroCusto.Tipo.ALMOXARIFADO)


# ------------------------- Fatia 2 -------------------------
class DemandaTests(ScmTestBase):
    def test_cria_demanda_gera_ref_externa_e_solicitante_default(self):
        self.autenticar()
        resp = self.client.post("/api/scm/demandas/", {"tipo": "material"})
        self.assertEqual(resp.status_code, 201, resp.content)
        demanda = Demanda.objects.get(pk=resp.data["demanda_id"])
        self.assertEqual(demanda.tenant_id, self.tenant.id)
        self.assertIsNotNone(demanda.ref_externa)
        self.assertEqual(demanda.solicitante_id, self.user.id)  # default do perform_create
        self.assertEqual(demanda.status, Demanda.Status.RASCUNHO)
        self.assertEqual(demanda.visibilidade, Demanda.Visibilidade.PRIVADA)

    def test_item_demanda_de_servico_dispensa_produto(self):
        demanda = Demanda.objects.create(tenant=self.tenant, tipo=Demanda.Tipo.SERVICO)
        self.autenticar()
        resp = self.client.post("/api/scm/itens-demanda/", {
            "demanda": demanda.demanda_id, "descricao_servico": "Pintura de fachada",
            "quantidade": "1.000", "unidade": "vb",
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertIsNone(ItemDemanda.objects.get(pk=resp.data["item_demanda_id"]).produto_id)

    def test_publicar_marca_visibilidade_rede_e_abre(self):
        demanda = Demanda.objects.create(tenant=self.tenant, tipo=Demanda.Tipo.MATERIAL)
        self.autenticar()
        resp = self.client.post(f"/api/scm/demandas/{demanda.demanda_id}/publicar/")
        self.assertEqual(resp.status_code, 200, resp.content)
        demanda.refresh_from_db()
        self.assertEqual(demanda.visibilidade, Demanda.Visibilidade.REDE)
        self.assertEqual(demanda.status, Demanda.Status.ABERTA)

    def test_publicar_exige_permissao_dedicada(self):
        demanda = Demanda.objects.create(tenant=self.tenant, tipo=Demanda.Tipo.MATERIAL)
        self.autenticar(perms=["scm.demanda.view", "scm.demanda.edit"])  # sem .publicar
        resp = self.client.post(f"/api/scm/demandas/{demanda.demanda_id}/publicar/")
        self.assertEqual(resp.status_code, 403)


class CotacaoAdjudicacaoTests(ScmTestBase):
    def setUp(self):
        self.demanda = Demanda.objects.create(tenant=self.tenant, tipo=Demanda.Tipo.MATERIAL)
        self.cotacao = Cotacao.objects.create(tenant=self.tenant, demanda=self.demanda)
        self.f1 = Fornecedor.objects.create(tenant=self.tenant, razao_social="Alfa", email="a@ex.com")
        self.f2 = Fornecedor.objects.create(tenant=self.tenant, razao_social="Beta", email="b@ex.com")
        self.p1 = Proposta.objects.create(tenant=self.tenant, cotacao=self.cotacao, fornecedor=self.f1, valor_total=100)
        self.p2 = Proposta.objects.create(tenant=self.tenant, cotacao=self.cotacao, fornecedor=self.f2, valor_total=90)

    def test_adjudicar_marca_vencedora_e_recusa_demais(self):
        self.autenticar()
        resp = self.client.post(
            f"/api/scm/cotacoes/{self.cotacao.cotacao_id}/adjudicar/", {"proposta_id": self.p2.proposta_id},
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.p1.refresh_from_db(); self.p2.refresh_from_db(); self.cotacao.refresh_from_db()
        self.assertEqual(self.p2.status, Proposta.Status.VENCEDORA)
        self.assertEqual(self.p1.status, Proposta.Status.RECUSADA)
        self.assertEqual(self.cotacao.status, Cotacao.Status.ADJUDICADA)

    def test_adjudicar_proposta_de_fora_da_cotacao_da_400(self):
        self.autenticar()
        resp = self.client.post(
            f"/api/scm/cotacoes/{self.cotacao.cotacao_id}/adjudicar/", {"proposta_id": 999999},
        )
        self.assertEqual(resp.status_code, 400)

    def test_adjudicar_exige_permissao_dedicada(self):
        self.autenticar(perms=["scm.cotacao.view", "scm.cotacao.edit"])  # sem .adjudicar
        resp = self.client.post(
            f"/api/scm/cotacoes/{self.cotacao.cotacao_id}/adjudicar/", {"proposta_id": self.p2.proposta_id},
        )
        self.assertEqual(resp.status_code, 403)

    def test_item_proposta_unico_por_proposta_e_item(self):
        item = ItemDemanda.objects.create(tenant=self.tenant, demanda=self.demanda, quantidade=5, unidade="un")
        ItemProposta.objects.create(tenant=self.tenant, proposta=self.p1, item_demanda=item, preco_unitario=10, quantidade=5)
        self.autenticar()
        resp = self.client.post("/api/scm/itens-proposta/", {
            "proposta": self.p1.proposta_id, "item_demanda": item.item_demanda_id,
            "preco_unitario": "11.00", "quantidade": "5.000",
        })
        self.assertEqual(resp.status_code, 400)


# ------------------------- Fatia 3 -------------------------
class CompraDiretaTests(ScmTestBase):
    def setUp(self):
        self.produto = Produto.objects.create(tenant=self.tenant, codigo_interno="P1", descricao="Cimento", unidade="sc")
        self.fornecedor = Fornecedor.objects.create(tenant=self.tenant, razao_social="Alfa", email="a@ex.com")

    def _oferta(self, compra_direta=True):
        return OfertaFornecedor.objects.create(
            tenant=self.tenant, produto=self.produto, fornecedor=self.fornecedor,
            preco_direto=Decimal("10.00"), estoque_disponivel=Decimal("100.000"), compra_direta=compra_direta,
        )

    def test_comprar_direto_gera_pedido_e_item(self):
        oferta = self._oferta(compra_direta=True)
        self.autenticar()
        resp = self.client.post("/api/scm/pedidos/comprar_direto/", {"oferta": oferta.oferta_id, "quantidade": "5"})
        self.assertEqual(resp.status_code, 201, resp.content)
        pedido = PedidoCompra.objects.get(pk=resp.data["pedido_id"])
        self.assertEqual(pedido.origem, PedidoCompra.Origem.COMPRA_DIRETA)
        self.assertEqual(pedido.oferta_origem_id, oferta.oferta_id)
        self.assertEqual(pedido.valor_total, Decimal("50.00"))
        self.assertEqual(pedido.itens.count(), 1)

    def test_comprar_direto_recusa_oferta_sem_compra_direta(self):
        oferta = self._oferta(compra_direta=False)
        self.autenticar()
        resp = self.client.post("/api/scm/pedidos/comprar_direto/", {"oferta": oferta.oferta_id, "quantidade": "5"})
        self.assertEqual(resp.status_code, 400)

    def test_comprar_direto_exige_permissao_criar(self):
        oferta = self._oferta()
        self.autenticar(perms=["scm.pedido.view", "scm.pedido.edit"])  # sem .criar
        resp = self.client.post("/api/scm/pedidos/comprar_direto/", {"oferta": oferta.oferta_id, "quantidade": "5"})
        self.assertEqual(resp.status_code, 403)


class GerarPedidoDeCotacaoTests(ScmTestBase):
    def setUp(self):
        self.produto = Produto.objects.create(tenant=self.tenant, codigo_interno="P1", descricao="Cimento", unidade="sc")
        self.fornecedor = Fornecedor.objects.create(tenant=self.tenant, razao_social="Alfa", email="a@ex.com")
        self.demanda = Demanda.objects.create(tenant=self.tenant, tipo=Demanda.Tipo.MATERIAL)
        self.item = ItemDemanda.objects.create(tenant=self.tenant, demanda=self.demanda, produto=self.produto, quantidade=5, unidade="sc")
        self.cotacao = Cotacao.objects.create(tenant=self.tenant, demanda=self.demanda)

    def test_gerar_de_cotacao_copia_itens_e_atende_demanda(self):
        vencedora = Proposta.objects.create(
            tenant=self.tenant, cotacao=self.cotacao, fornecedor=self.fornecedor,
            valor_total=Decimal("45.00"), status=Proposta.Status.VENCEDORA,
        )
        ItemProposta.objects.create(tenant=self.tenant, proposta=vencedora, item_demanda=self.item, preco_unitario=Decimal("9.00"), quantidade=5)
        self.autenticar()
        resp = self.client.post("/api/scm/pedidos/gerar_de_cotacao/", {"cotacao": self.cotacao.cotacao_id})
        self.assertEqual(resp.status_code, 201, resp.content)
        pedido = PedidoCompra.objects.get(pk=resp.data["pedido_id"])
        self.assertEqual(pedido.origem, PedidoCompra.Origem.COTACAO)
        self.assertEqual(pedido.proposta_vencedora_id, vencedora.proposta_id)
        self.assertEqual(pedido.itens.count(), 1)
        self.demanda.refresh_from_db()
        self.assertEqual(self.demanda.status, Demanda.Status.ATENDIDA)

    def test_gerar_de_cotacao_sem_vencedora_da_400(self):
        Proposta.objects.create(tenant=self.tenant, cotacao=self.cotacao, fornecedor=self.fornecedor, valor_total=45)
        self.autenticar()
        resp = self.client.post("/api/scm/pedidos/gerar_de_cotacao/", {"cotacao": self.cotacao.cotacao_id})
        self.assertEqual(resp.status_code, 400)


class RecebimentoTests(ScmTestBase):
    def setUp(self):
        self.fornecedor = Fornecedor.objects.create(tenant=self.tenant, razao_social="Alfa", email="a@ex.com")
        self.pedido = PedidoCompra.objects.create(
            tenant=self.tenant, origem=PedidoCompra.Origem.MANUAL, fornecedor=self.fornecedor,
            status=PedidoCompra.Status.APROVADO,
        )

    def test_recebimento_total_marca_pedido_recebido_total(self):
        self.autenticar()
        resp = self.client.post("/api/scm/recebimentos/", {
            "pedido": self.pedido.pedido_id, "tipo": Recebimento.Tipo.TOTAL, "nota_fiscal_ref": "NFe-123",
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, PedidoCompra.Status.RECEBIDO_TOTAL)

    def test_recebimento_parcial_marca_pedido_recebido_parcial(self):
        self.autenticar()
        resp = self.client.post("/api/scm/recebimentos/", {
            "pedido": self.pedido.pedido_id, "tipo": Recebimento.Tipo.PARCIAL,
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, PedidoCompra.Status.RECEBIDO_PARCIAL)


class AvaliacaoTests(ScmTestBase):
    def setUp(self):
        self.fornecedor = Fornecedor.objects.create(tenant=self.tenant, razao_social="Alfa", email="a@ex.com")

    def test_cria_avaliacao_valida(self):
        self.autenticar()
        resp = self.client.post("/api/scm/avaliacoes/", {
            "fornecedor": self.fornecedor.fornecedor_id,
            "nota_qualidade": 5, "nota_pontualidade": 4, "nota_atendimento": 5,
            "comentario": "Entregou no prazo.",
        })
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_nota_fora_do_intervalo_da_400(self):
        self.autenticar()
        resp = self.client.post("/api/scm/avaliacoes/", {
            "fornecedor": self.fornecedor.fornecedor_id,
            "nota_qualidade": 6, "nota_pontualidade": 4, "nota_atendimento": 5,
        })
        self.assertEqual(resp.status_code, 400)
