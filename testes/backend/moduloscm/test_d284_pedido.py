"""D284 — o pedido de compra ponta a ponta: recebimento por linha (Estoque),
cobrança (ERP), NF-e da compra, edição, cancelamento, envio e o item que nasce
da compra (catálogo + teto do plano).

O defeito de origem (11/10/2026): o recebimento pela tela gravava só o cabeçalho,
sem linhas, e por isso nada entrava no estoque; e nada chegava ao ERP.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from catalogo.models import Item
from fornecedores.models import Fornecedor
from moduloerp.models import AnotacaoContaPagar, ContaPagar
from modulosil.models import SaldoEstoque
from nucleo.models import Tenant, Usuario
from obras.models import Obra

from moduloscm.models import (
    CentroCusto,
    EventoPedido,
    ItemPedido,
    NotaFiscalCompra,
    OfertaFornecedor,
    PedidoCompra,
)
from moduloscm.notas import dv_da_chave, partes_da_chave

PERMS = [
    "scm.pedido.view", "scm.pedido.edit", "scm.pedido.criar",
    "scm.recebimento.view", "scm.recebimento.edit",
]
#: A chave da nota do Pedido #6 que o dono registrou (11/10/2026): NF-e 529,
#: série 1, emitida pelo CNPJ 04.450.693/0001-75.
CHAVE_REAL = "29261004450693000175550010000005291000005286"
CNPJ_REAL = "04.450.693/0001-75"


def _xml(*, chave=CHAVE_REAL, numero="529", cnpj="04450693000175", valor="79.00", dups=()):
    cobr = "".join(f"<dup><nDup>{i:03d}</nDup><dVenc>{v}</dVenc><vDup>{x}</vDup></dup>" for i, (v, x) in enumerate(dups, 1))
    corpo = (
        '<?xml version="1.0" encoding="UTF-8"?><nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">'
        f'<NFe><infNFe Id="NFe{chave}" versao="4.00"><ide><nNF>{numero}</nNF><serie>1</serie>'
        "<dhEmi>2026-10-06T10:00:00-03:00</dhEmi></ide>"
        f"<emit><CNPJ>{cnpj}</CNPJ><xNome>MENEZES MATERIAIS</xNome></emit>"
        f"<total><ICMSTot><vNF>{valor}</vNF></ICMSTot></total>"
        + (f"<cobr>{cobr}</cobr>" if cobr else "")
        + "</infNFe></NFe></nfeProc>"
    )
    return SimpleUploadedFile("nota.xml", corpo.encode(), content_type="application/xml")


class PedidoBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="d284", nome="Construtora D284")
        cls.user = Usuario.objects.create(username="comprador_d284", tenant=cls.tenant)
        cls.fornecedor = Fornecedor.objects.create(
            tenant=cls.tenant, razao_social="MENEZES MATERIAIS", email="vendas@menezes.ex", cnpj=CNPJ_REAL,
        )
        cls.obra = Obra.objects.create(tenant=cls.tenant, nome_obra="Rede de Drenagem", endereco="Rua A, 1")
        cls.centro = CentroCusto.objects.create(
            tenant=cls.tenant, nome="Rede de Drenagem e Água", tipo=CentroCusto.Tipo.OBRA, obra=cls.obra,
        )

    def setUp(self):
        self.luva = Item.objects.create(tenant=self.tenant, codigo_interno="LV32", descricao="Luva 32mm", unidade="un")
        self.autenticar()
        resp = self.client.post("/api/scm/pedidos/compra_avulsa/", {
            "fornecedor": self.fornecedor.pk, "centro_custo": self.centro.pk,
            "itens": [
                {"produto": self.luva.pk, "quantidade": "10", "preco_unitario": "5.00"},
                {"descricao": "Serra Starrett", "unidade": "un", "quantidade": "1", "preco_unitario": "13.00"},
            ],
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.pedido = PedidoCompra.objects.get(pk=resp.data["pedido_id"])
        self.l_luva = self.pedido.itens.get(produto=self.luva)
        self.l_serra = self.pedido.itens.get(produto__isnull=True)

    def autenticar(self, perms=PERMS, quotas=None):
        self.user.iam_modules = ["scm"]
        self.user.iam_permissions = list(perms)
        if quotas is not None:
            self.user.iam_quotas = quotas
        elif hasattr(self.user, "iam_quotas"):
            del self.user.iam_quotas
        self.client.force_authenticate(user=self.user)

    def receber(self, linhas, **extra):
        return self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/receber/", {
            "itens": [{"item_pedido": ip.pk, "quantidade": q} for ip, q in linhas], **extra,
        }, format="json")

    def cobrar(self, meios):
        return self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/cobranca/", {"meios": meios}, format="json")

    def boleto(self, valor, parcelas=1):
        return {"tipo": "boleto", "valor": valor, "parcelas": parcelas,
                "primeiro_vencimento": (date.today() + timedelta(days=30)).isoformat(), "intervalo_dias": 30}


class RecebimentoPorLinhaTests(PedidoBase):
    def test_recebimento_pela_tela_da_entrada_no_estoque(self):
        """O defeito de origem: agora a linha existe e o SIL dá a entrada."""
        resp = self.receber([(self.l_luva, "4"), (self.l_serra, "1")])
        self.assertEqual(resp.status_code, 201, resp.content)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, PedidoCompra.Status.RECEBIDO_PARCIAL)
        saldo = SaldoEstoque.objects.get(tenant=self.tenant, item=self.luva)
        self.assertEqual(saldo.quantidade, Decimal("4.000"))
        self.assertTrue(resp.data["aguardando_nfe"])

    def test_a_menos_sem_finalizar_nao_e_divergencia(self):
        self.receber([(self.l_luva, "4")])
        self.assertFalse(self.pedido.eventos.filter(tipo=EventoPedido.Tipo.DIVERGENCIA).exists())

    def test_finalizar_com_saldo_a_menos_vai_ao_erp_como_divergencia(self):
        self.assertEqual(self.cobrar([self.boleto("63.00")]).status_code, 201)
        resp = self.receber([(self.l_luva, "8"), (self.l_serra, "1")], encerrar=True)
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["valor_encerrado"], "10.00")
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, PedidoCompra.Status.RECEBIDO_TOTAL)
        self.l_luva.refresh_from_db()
        self.assertEqual(self.l_luva.quantidade_encerrada, Decimal("2.000"))
        anotacao = AnotacaoContaPagar.objects.get(tipo="divergencia")
        self.assertEqual(anotacao.valor, Decimal("10.00"))
        self.assertIn("saldo a menos", anotacao.texto)

    def test_chegou_a_mais_e_aceito_e_anotado(self):
        self.cobrar([self.boleto("63.00")])
        resp = self.receber([(self.l_luva, "12"), (self.l_serra, "1")])
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["valor_a_mais"], "10.00")
        self.assertEqual(SaldoEstoque.objects.get(item=self.luva).quantidade, Decimal("12.000"))
        self.assertTrue(AnotacaoContaPagar.objects.filter(tipo="divergencia", valor=Decimal("10.00")).exists())

    def test_linha_de_outro_pedido_e_recusada(self):
        outro = ItemPedido.objects.create(tenant=self.tenant, pedido=PedidoCompra.objects.create(
            tenant=self.tenant, fornecedor=self.fornecedor), descricao="x", quantidade=1, preco_unitario=1)
        resp = self.receber([(outro, "1")])
        self.assertEqual(resp.status_code, 400)

    def test_receber_com_a_nota_no_mesmo_envio(self):
        resp = self.receber([(self.l_luva, "10"), (self.l_serra, "1")], nf_numero="529", nf_chave=CHAVE_REAL)
        self.assertEqual(resp.status_code, 201, resp.content)
        nota = NotaFiscalCompra.objects.get(pk=resp.data["nota"])
        self.assertEqual(nota.recebimento_id, resp.data["recebimento_id"])
        self.assertFalse(resp.data["aguardando_nfe"])


class CobrancaTests(PedidoBase):
    def test_meios_viram_titulos_no_erp_com_a_obra(self):
        resp = self.cobrar([
            {"tipo": "pix", "valor": "13.00", "parcelas": 1, "primeiro_vencimento": date.today().isoformat()},
            self.boleto("50.00", parcelas=3),
        ])
        self.assertEqual(resp.status_code, 201, resp.content)
        titulos = ContaPagar.objects.filter(pedido_compra_ref=self.pedido.pk).order_by("data_vencimento", "pk")
        self.assertEqual(titulos.count(), 4)
        self.assertEqual(sorted(t.valor for t in titulos), [Decimal("13.00"), Decimal("16.66"), Decimal("16.66"), Decimal("16.68")])
        self.assertTrue(all(t.obra_id == self.obra.pk for t in titulos))
        self.assertTrue(all(t.nfe_situacao == "aguardando_nota" for t in titulos))
        self.pedido.refresh_from_db()
        self.assertIsNotNone(self.pedido.conta_pagar_ref)

    def test_soma_diferente_do_pedido_e_recusada(self):
        resp = self.cobrar([self.boleto("60.00")])
        self.assertEqual(resp.status_code, 400)
        self.assertIn("faltam R$ 3.00", resp.data["detail"])

    def test_redefinir_cancela_os_titulos_sem_pagamento(self):
        self.cobrar([self.boleto("63.00")])
        antigo = ContaPagar.objects.get(pedido_compra_ref=self.pedido.pk)
        resp = self.cobrar([self.boleto("63.00", parcelas=2)])
        self.assertEqual(resp.status_code, 201, resp.content)
        antigo.refresh_from_db()
        self.assertEqual(antigo.status, "CANCELADO")
        self.assertEqual(ContaPagar.objects.filter(pedido_compra_ref=self.pedido.pk).exclude(status="CANCELADO").count(), 2)

    def test_titulo_pago_impede_redefinir(self):
        self.cobrar([self.boleto("63.00")])
        ContaPagar.objects.filter(pedido_compra_ref=self.pedido.pk).update(valor_pago=Decimal("10.00"), status="PARCIAL")
        resp = self.cobrar([self.boleto("63.00", parcelas=2)])
        self.assertEqual(resp.status_code, 400)

    def test_titulo_novo_herda_a_trilha_anterior(self):
        """Editado antes de ter cobrança: o título que nasce depois já sabe."""
        resp = self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/editar/", {
            "itens": [{"item_pedido": self.l_luva.pk, "quantidade": "12", "preco_unitario": "5.00"},
                      {"item_pedido": self.l_serra.pk, "quantidade": "1", "preco_unitario": "13.00"}],
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.cobrar([self.boleto("73.00")])
        conta = ContaPagar.objects.get(pedido_compra_ref=self.pedido.pk)
        self.assertTrue(conta.anotacoes.filter(tipo="edicao").exists())
        self.assertTrue(conta.anotacoes.filter(tipo="cobranca").exists())


class NotaFiscalTests(PedidoBase):
    def test_o_dv_da_chave_real_confere(self):
        self.assertEqual(dv_da_chave(CHAVE_REAL[:43]), int(CHAVE_REAL[43]))
        self.assertEqual(int(partes_da_chave(CHAVE_REAL)["numero"]), 529)

    def test_so_o_numero_vai_ao_erp_aguardando_documento(self):
        self.cobrar([self.boleto("63.00")])
        resp = self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/notas/", {"numero": "529"})
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["situacao"], "aguardando_documento")
        conta = ContaPagar.objects.get(pedido_compra_ref=self.pedido.pk)
        self.assertEqual((conta.nfe_situacao, conta.nfe_numero), ("aguardando_documento", "529"))

    def test_numero_que_nao_e_o_da_chave_diverge(self):
        resp = self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/notas/", {"numero": "530", "chave": CHAVE_REAL})
        self.assertEqual(resp.data["situacao"], "divergente")
        self.assertTrue(any("não é o da chave" in d for d in resp.data["divergencias"]))

    def test_chave_invalida_e_avisada_nao_recusada(self):
        """Dono, 11/10/2026: testada igual CPF/CNPJ, mas só avisa — a nota entra."""
        errada = CHAVE_REAL[:-1] + "0"
        for chave, motivo in [(errada, "confira a digitação"), (CHAVE_REAL[:40], "40 de 44")]:
            resp = self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/notas/", {"numero": "529", "chave": chave})
            self.assertEqual(resp.status_code, 201, resp.content)
            self.assertEqual(resp.data["situacao"], "divergente")
            self.assertTrue(any(motivo in d for d in resp.data["divergencias"]), resp.data["divergencias"])

    def test_nota_em_nome_de_outro_cnpj_entra_com_aviso(self):
        outra = "29261011222333000181550010000005291000005286"[:43]
        outra += str(dv_da_chave(outra))
        resp = self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/notas/", {"numero": "529", "chave": outra})
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(any("outra empresa" in d for d in resp.data["divergencias"]), resp.data["divergencias"])

    def test_validar_chave(self):
        from moduloscm.notas import validar_chave

        self.assertIsNone(validar_chave(CHAVE_REAL))
        # Modelo 57 (CT-e) com o DV recalculado: a conta fecha, o documento não é NF-e.
        cte = CHAVE_REAL[:20] + "57" + CHAVE_REAL[22:43]
        cte += str(dv_da_chave(cte))
        self.assertIn("modelo 57", validar_chave(cte))

    def test_documento_depois_confere_e_atualiza_o_erp(self):
        self.cobrar([self.boleto("63.00")])
        nota = self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/notas/", {"numero": "529"}).data
        resp = self.client.post(f"/api/scm/notas-fiscais/{nota['nota_id']}/documento/",
                                {"xml": _xml(valor="63.00")}, format="multipart")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["situacao"], "conferida", resp.data["divergencias"])
        self.assertEqual(resp.data["chave_acesso"], CHAVE_REAL)
        self.assertEqual(ContaPagar.objects.get(pedido_compra_ref=self.pedido.pk).nfe_situacao, "conferida")
        # O XML sai pela porta única, nunca por /media/.
        self.assertTrue(resp.data["url_xml"].startswith("/api/impexp/scm.nota_compra/arquivo/xml/"))
        self.assertIsNone(resp.data["url_pdf"])
        baixado = self.client.get(resp.data["url_xml"])
        self.assertEqual(baixado.status_code, 200)
        self.assertIn(b"infNFe", b"".join(baixado.streaming_content) if baixado.streaming else baixado.content)

    def test_xml_de_outro_emitente_diverge(self):
        resp = self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/notas/",
                                {"xml": _xml(cnpj="11222333000181")}, format="multipart")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data["situacao"], "divergente")

    def test_pdf_com_a_chave_conta_como_documento(self):
        pdf = SimpleUploadedFile("danfe.pdf", b"%PDF-1.4 teste", content_type="application/pdf")
        resp = self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/notas/",
                                {"numero": "529", "chave": CHAVE_REAL, "pdf": pdf}, format="multipart")
        self.assertEqual(resp.data["situacao"], "conferida", resp.data["divergencias"])

    def test_arquivo_que_nao_e_pdf_e_recusado(self):
        falso = SimpleUploadedFile("danfe.pdf", b"nao sou pdf", content_type="application/pdf")
        resp = self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/notas/",
                                {"numero": "529", "pdf": falso}, format="multipart")
        self.assertEqual(resp.status_code, 400)


class EdicaoTests(PedidoBase):
    def _editar(self, corpo):
        return self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/editar/", corpo, format="json")

    def test_edicao_livre_antes_do_recebimento(self):
        resp = self._editar({"itens": [
            {"item_pedido": self.l_luva.pk, "quantidade": "20", "preco_unitario": "4.50"},
            {"descricao": "Adesivo PVC", "unidade": "un", "quantidade": "1", "preco_unitario": "8.00"},
        ]})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.valor_total, Decimal("98.00"))
        self.assertEqual(self.pedido.revisao, 1)
        self.assertEqual(self.pedido.itens.count(), 2)  # a serra saiu, o adesivo entrou

    def test_depois_do_recebimento_so_o_saldo(self):
        self.receber([(self.l_luva, "4")])
        corpo = {"itens": [{"item_pedido": self.l_luva.pk, "quantidade": "10", "preco_unitario": "6.00"},
                           {"item_pedido": self.l_serra.pk, "quantidade": "1"}]}
        self.assertEqual(self._editar(corpo).status_code, 400)  # preço travado
        corpo["itens"][0] = {"item_pedido": self.l_luva.pk, "quantidade": "3"}
        self.assertEqual(self._editar(corpo).status_code, 400)  # abaixo do recebido
        corpo["itens"][0] = {"item_pedido": self.l_luva.pk, "quantidade": "6"}
        self.assertEqual(self._editar(corpo).status_code, 200)

    def test_edicao_com_titulo_vira_anotacao(self):
        self.cobrar([self.boleto("63.00")])
        self._editar({"data_entrega_prevista": (date.today() + timedelta(days=5)).isoformat()})
        conta = ContaPagar.objects.get(pedido_compra_ref=self.pedido.pk)
        self.assertTrue(conta.anotacoes.filter(tipo="edicao", texto__contains="entrega prevista").exists())

    def test_cancelar_sem_recebimento_cancela_os_titulos(self):
        self.cobrar([self.boleto("63.00")])
        resp = self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/cancelar/", {"motivo": "obra parou"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(ContaPagar.objects.get(pedido_compra_ref=self.pedido.pk).status, "CANCELADO")

    def test_cancelar_com_recebimento_e_recusado(self):
        self.receber([(self.l_luva, "1")])
        resp = self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/cancelar/", {}, format="json")
        self.assertEqual(resp.status_code, 400)


class EnvioEPainelTests(PedidoBase):
    def test_pdf_do_pedido(self):
        resp = self.client.get(f"/api/scm/pedidos/{self.pedido.pk}/pdf/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_whatsapp_marca_enviado(self):
        resp = self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/enviar/", {"canal": "whatsapp"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, PedidoCompra.Status.ENVIADO)
        self.assertTrue(self.pedido.eventos.filter(tipo=EventoPedido.Tipo.ENVIO).exists())

    def test_painel_diz_o_que_falta(self):
        self.receber([(self.l_luva, "10")])
        resp = self.client.get(f"/api/scm/pedidos/{self.pedido.pk}/painel/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("aguardando_nfe", resp.data["pendencias"])
        self.assertIn("sem_cobranca", resp.data["pendencias"])
        self.assertEqual(resp.data["regime"], "saldo")
        luva = next(l for l in resp.data["linhas"] if l["item_pedido"] == self.l_luva.pk)
        self.assertEqual(Decimal(luva["pendente"]), Decimal("0"))


class CadastrarItemTests(PedidoBase):
    def test_linha_de_texto_vira_item_e_loja(self):
        resp = self.client.post("/api/scm/pedidos/cadastrar_item/", {"item_pedido": self.l_serra.pk}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        item = Item.objects.get(pk=resp.data["item_id"])
        self.assertTrue(item.codigo_interno.startswith("ITM-"))
        self.assertEqual(item.origem, Item.Origem.COMPRA)
        self.l_serra.refresh_from_db()
        self.assertEqual(self.l_serra.produto_id, item.pk)
        oferta = OfertaFornecedor.objects.get(produto=item, fornecedor=self.fornecedor)
        self.assertEqual(oferta.preco_direto, Decimal("13.00"))

    def test_codigo_nunca_repete(self):
        Item.objects.create(tenant=self.tenant, codigo_interno="ITM-000007", descricao="Outro", unidade="un")
        resp = self.client.post("/api/scm/pedidos/cadastrar_item/", {"descricao": "Adesivo PVC", "unidade": "un"}, format="json")
        self.assertEqual(resp.data["codigo_interno"], "ITM-000008")

    def test_mesmo_texto_devolve_o_mesmo_item(self):
        a = self.client.post("/api/scm/pedidos/cadastrar_item/", {"descricao": "Luva 25 mm", "unidade": "un"}, format="json")
        b = self.client.post("/api/scm/pedidos/cadastrar_item/", {"descricao": "LUVA 25MM", "unidade": "UN"}, format="json")
        self.assertEqual(b.status_code, 200)
        self.assertEqual(a.data["item_id"], b.data["item_id"])

    def test_teto_do_plano_barra_com_402(self):
        # A luva do setUp já ocupa a única vaga; item de base de referência não conta.
        Item.objects.create(tenant=self.tenant, codigo_interno="SINAPI-1", descricao="Cimento", unidade="sc",
                            fonte_referencia=Item.Fonte.SINAPI)
        self.autenticar(quotas={"catalogo_itens": 1})
        resp = self.client.post("/api/scm/pedidos/cadastrar_item/", {"descricao": "Adesivo PVC"}, format="json")
        self.assertEqual(resp.status_code, 402)
        self.assertEqual(resp.data["quota"], "catalogo_itens")


class NotasDasComprasNoErpTests(PedidoBase):
    """Dono, 11/10/2026: "em NF-e era para ficar a nota com pendência"."""

    def _erp(self, **params):
        self.user.iam_modules = ["scm", "erp_financeiro"]
        self.user.iam_permissions = list(PERMS) + ["erp.nf.view"]
        return self.client.get("/api/erp/notas-das-compras/", params)

    def test_compra_recebida_sem_nota_e_pendencia(self):
        self.receber([(self.l_luva, "10")])
        resp = self._erp()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["pendentes"], 1)
        linha = resp.data["results"][0]
        self.assertEqual((linha["pedido"], linha["situacao"], linha["nota"]), (self.pedido.pk, "aguardando_nota", None))

    def test_nota_so_com_numero_fica_pendente_e_conferida_vai_para_o_fim(self):
        self.receber([(self.l_luva, "10")])
        self.client.post(f"/api/scm/pedidos/{self.pedido.pk}/notas/", {"numero": "529"})
        linhas = self._erp().data["results"]
        self.assertEqual([(l["numero"], l["situacao"]) for l in linhas], [("529", "aguardando_documento")])
        self.assertEqual(self._erp(pendentes="1").data["count"], 1)

    def test_sem_permissao_de_nota_no_erp_recebe_403(self):
        self.user.iam_modules = ["scm", "erp_financeiro"]
        self.user.iam_permissions = list(PERMS)
        self.assertEqual(self.client.get("/api/erp/notas-das-compras/").status_code, 403)


class FichaDoItemTests(PedidoBase):
    def test_ficha_junta_origem_lojas_precos_e_estoque(self):
        self.receber([(self.l_luva, "10")])
        self.user.iam_permissions = ["cadastro.item.view"]
        resp = self.client.get(f"/api/catalogo/itens/{self.luva.pk}/ficha/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["origem"]["tipo"], "manual")
        loja = resp.data["lojas"][0]
        self.assertEqual(loja["fornecedor_nome"], "MENEZES MATERIAIS")
        self.assertEqual(loja["ultimo_preco_pago"], "5.00")
        self.assertEqual(resp.data["historico_precos"][0]["pedido"], self.pedido.pk)
        self.assertEqual(Decimal(resp.data["estoque_total"]), Decimal("10"))
        self.assertEqual(resp.data["uso"]["pedidos"], 1)
