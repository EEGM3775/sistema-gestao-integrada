# testes/backend/funcoesimpexp/test_scm.py
"""Suprimentos e catálogo pelo motor (15/10/2026).

Item do catálogo e oferta de fornecedor importam (só criam, tudo ou nada);
demanda, cotação e pedido **só exportam** — documento de fluxo nasce pela tela
(decisão do dono, 15/10/2026).
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from catalogo.models import Item
from fornecedores.models import Fornecedor
from moduloscm.models import OfertaFornecedor, PedidoCompra
from nucleo.models import Tenant, Usuario

from funcoesimpexp import importacao as motor
from funcoesimpexp.models import LinhaImportacao
from funcoesimpexp.registro import obter

NOVA = LinhaImportacao.Situacao.NOVA
INVALIDA = LinhaImportacao.Situacao.INVALIDA


def _csv(linhas: list[str]) -> bytes:
    return "\n".join(linhas).encode("utf-8")


class ScmImpexpBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="scm-imp", nome="Construtora SCM")
        cls.fornecedor = Fornecedor.objects.create(
            tenant=cls.tenant, razao_social="Concreto Forte Ltda", email="cf@x.com",
        )
        cls.item = Item.objects.create(
            tenant=cls.tenant, codigo_interno="CIM-50", descricao="Cimento 50 kg", unidade="sc",
        )

    def recurso(self, recurso_id):
        return obter(recurso_id).com_contexto({"tenant_id": str(self.tenant.id)})

    def preparar(self, recurso_id, linhas, **kw):
        return motor.preparar(
            recurso=self.recurso(recurso_id), conteudo=_csv(linhas),
            nome_arquivo="scm.csv", tenant_id=self.tenant.id, usuario_nome="op", **kw,
        )

    def situacoes(self, lote):
        return [(l.situacao, l.motivo) for l in lote.linhas.order_by("numero")]


class ItemDoCatalogoTests(ScmImpexpBase):
    CAB = "Código;Descrição;Unidade;Tipo"

    def test_cria_item_proprio_com_tipo_pelo_rotulo(self):
        lote = self.preparar("cadastro.item", [self.CAB, "ARE-M;Areia média;m³;Material"])
        self.assertEqual(self.situacoes(lote), [(NOVA, "")])
        motor.aplicar(lote, recurso=self.recurso("cadastro.item"))
        item = Item.objects.get(tenant=self.tenant, codigo_interno="ARE-M")
        self.assertEqual((item.tipo, item.origem, item.fonte_referencia), ("material", "manual", ""))

    def test_codigo_ja_cadastrado_trava(self):
        lote = self.preparar("cadastro.item", [self.CAB, "CIM-50;Outro cimento;sc;"])
        with self.assertRaises(motor.ImportacaoInvalida):
            motor.aplicar(lote, recurso=self.recurso("cadastro.item"))

    def test_quota_de_itens_proprios(self):
        with self.assertRaises(motor.LimiteDoPlano):
            self.preparar("cadastro.item", [self.CAB, "A;A;un;", "B;B;un;"],
                          limites={"catalogo_itens": 2})


class OfertaTests(ScmImpexpBase):
    def test_cria_oferta_com_item_e_fornecedor_pelo_nome(self):
        lote = self.preparar("scm.oferta", [
            "Código do item;Fornecedor;Preço;Compra direta",
            "cim-50;concreto forte ltda;38,90;Sim",
        ])
        self.assertEqual(self.situacoes(lote), [(NOVA, "")])
        motor.aplicar(lote, recurso=self.recurso("scm.oferta"))
        oferta = OfertaFornecedor.objects.get(tenant=self.tenant)
        self.assertEqual((oferta.preco_direto, oferta.compra_direta, oferta.ativo),
                         (Decimal("38.90"), True, True))

    def test_item_inexistente_e_sim_nao_torto_travam(self):
        lote = self.preparar("scm.oferta", [
            "Código do item;Fornecedor;Preço;Compra direta",
            "XYZ;Concreto Forte Ltda;10;Sim",
            "CIM-50;Concreto Forte Ltda;10;talvez",
        ])
        (s1, m1), (s2, m2) = self.situacoes(lote)
        self.assertEqual((s1, s2), (INVALIDA, INVALIDA))
        self.assertIn("XYZ", m1)
        self.assertIn("talvez", m2)

    def test_mesma_oferta_ja_existente_trava(self):
        OfertaFornecedor.objects.create(tenant=self.tenant, produto=self.item,
                                        fornecedor=self.fornecedor, preco_direto=Decimal("30"))
        lote = self.preparar("scm.oferta", [
            "Código do item;Fornecedor;Preço", "CIM-50;Concreto Forte Ltda;31",
        ])
        with self.assertRaises(motor.ImportacaoInvalida):
            motor.aplicar(lote, recurso=self.recurso("scm.oferta"))


class DocumentosSoExportamTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="scm-api", nome="SCM API")
        self.user = Usuario.objects.create(username="comprador", tenant=self.tenant)
        forn = Fornecedor.objects.create(tenant=self.tenant, razao_social="Loja Alfa", email="a@x.com")
        PedidoCompra.objects.create(tenant=self.tenant, fornecedor=forn, valor_total=Decimal("1500"))
        self.user.iam_modules = ["scm"]
        self.user.iam_permissions = ["scm.pedido.view", "scm.demanda.view", "scm.cotacao.view"]
        self.user.iam_quotas = None
        self.client.force_authenticate(user=self.user)

    def test_pedido_exporta_e_nao_importa(self):
        recursos = {r["id"]: r for r in self.client.get("/api/impexp/recursos/").data["recursos"]}
        for rid in ("scm.pedido", "scm.demanda", "scm.cotacao"):
            self.assertTrue(recursos[rid]["exporta"], rid)
            self.assertFalse(recursos[rid]["importa"], rid)
        resposta = self.client.get("/api/impexp/scm.pedido/exportar/", {"formato": "csv"})
        self.assertEqual(resposta.status_code, 200, getattr(resposta, "data", ""))
        corpo = b"".join(resposta.streaming_content if resposta.streaming else [resposta.content])
        self.assertIn("Loja Alfa", corpo.decode("utf-8-sig"))
