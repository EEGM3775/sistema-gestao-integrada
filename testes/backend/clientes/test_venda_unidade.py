"""A venda de uma unidade, ponta a ponta pela API.

Cobre o que a mudança de modelo promete: a unidade é cadastro do empreendimento,
uma unidade tem um dono só, o preço parte da tabela e o carnê só nasce quando o
usuário manda — sem boleto junto.
"""
from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from clientes.models import ClienteEmpreendimento, MeioPagamento
from empreendimentos.models import Empreendimento, Unidade
from moduloerp.models import ContaReceber
from nucleo.models import Tenant, Usuario
from .tests import CarteiraBaseTestCase


class VendaBaseTestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="vendas", nome="Loteadora Vendas")
        cls.user = Usuario.objects.create(username="vendedor", tenant=cls.tenant)
        cls.emp = Empreendimento.objects.create(
            tenant=cls.tenant, empreendimento="Residencial Ipê", razao_social="Ipê SPE",
            cnpj="11222333000181", telefone="1133334444", endereco="Rua das Flores, 1",
            cidade="Palhoça", estado="SC",
        )
        from clientes.models import Cliente
        cls.cliente = Cliente.objects.create(
            tenant=cls.tenant, nome_completo="Marina Rocha", cpf_cnpj="52998224725",
            email="marina@exemplo.com", telefone="48999990003",
            data_nascimento=date(1990, 1, 1), cidade="Palhoça", estado="SC",
        )
        cls.unidade = Unidade.objects.create(
            tenant=cls.tenant, empreendimento=cls.emp, quadra="1", lote="01",
            valor_base=Decimal("100000.00"),
        )

    def autenticar(self, permissoes=None):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = permissoes if permissoes is not None else [
            "cadastro.cliente.view", "cadastro.cliente.edit",
            # A venda tem permissão própria — cadastro não vende nem emite carnê.
            "cadastro.venda.view", "cadastro.venda.edit", "cadastro.venda.gerar_carne",
            "obra.empreendimento.view", "obra.empreendimento.edit",
            "erp.cobranca.view",
        ]
        self.client.force_authenticate(user=self.user)


class CadastroDeUnidadeTests(VendaBaseTestCase):

    def test_cria_unidade_com_valor_de_tabela(self):
        self.autenticar()
        r = self.client.post("/api/unidades/", {
            "empreendimento": self.emp.pk, "quadra": "2", "lote": "07",
            "valor_base": "150000.00", "tipo": "lote",
        })
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["rotulo"], "QD 2 · LT 07")
        self.assertEqual(r.data["situacao"], "disponivel")

    def test_unidade_sem_nenhum_nivel_de_identificacao_e_recusada(self):
        """Uma unidade sem quadra, lote, bloco, andar nem apto não tem nome —
        e nome é como ela aparece em toda a plataforma."""
        self.autenticar()
        r = self.client.post("/api/unidades/", {
            "empreendimento": self.emp.pk, "valor_base": "150000.00",
        })
        self.assertEqual(r.status_code, 400)

    def test_identificacao_repetida_no_mesmo_empreendimento_e_recusada(self):
        self.autenticar()
        r = self.client.post("/api/unidades/", {
            "empreendimento": self.emp.pk, "quadra": "1", "lote": "01",
            "valor_base": "111000.00",
        })
        self.assertEqual(r.status_code, 400)

    def test_lista_sai_na_ordem_do_endereco_e_nao_alfabetica(self):
        self.autenticar()
        for quadra, lote in [("2", "10"), ("10", "01"), ("2", "02")]:
            Unidade.objects.create(
                tenant=self.tenant, empreendimento=self.emp, quadra=quadra, lote=lote,
                valor_base=Decimal("100000.00"),
            )
        r = self.client.get("/api/unidades/", {"empreendimento": self.emp.pk})
        rotulos = [u["rotulo"] for u in r.data["results"]]
        self.assertEqual(rotulos, [
            "QD 1 · LT 01", "QD 2 · LT 02", "QD 2 · LT 10", "QD 10 · LT 01",
        ])

    def test_unidade_vendida_nao_pode_ser_excluida(self):
        self.autenticar()
        ClienteEmpreendimento.objects.create(
            tenant=self.tenant, cliente=self.cliente, empreendimento=self.emp,
            unidade=self.unidade, data_compra=date(2026, 1, 10),
            valor_tabela=Decimal("100000.00"), valor_compra=Decimal("100000.00"),
            condicoes_pagamento="a_vista",
        )
        r = self.client.delete(f"/api/unidades/{self.unidade.pk}/")
        self.assertEqual(r.status_code, 409)

    def test_empreendimento_traz_a_contagem_de_unidades(self):
        self.autenticar()
        r = self.client.get(f"/api/empreendimentos/{self.emp.pk}/")
        self.assertEqual(r.data["unidades_total"], 1)
        self.assertEqual(r.data["unidades_disponiveis"], 1)
        self.assertEqual(r.data["unidades_vendidas"], 0)


class SimulacaoTests(VendaBaseTestCase):

    def test_simula_pela_unidade_sem_gravar_nada(self):
        self.autenticar()
        r = self.client.post("/api/clientes-empreendimentos/simular/", {
            "unidade": self.unidade.pk, "desconto_percentual": "10",
            "data_compra": "2026-01-10",
            "meios": [
                {"tipo": "entrada", "valor": "20000", "parcelas": 2},
                {"tipo": "financiamento_direto", "valor": "70000", "parcelas": 12,
                 "juros_mensal": "1", "sistema_amortizacao": "price"},
            ],
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["valorTabela"], "100000.00")
        self.assertEqual(r.data["valorNegociado"], "90000.00")
        self.assertEqual(r.data["saldoFinanciado"], "70000.00")
        # 70.000 em 12x a 1% a.m. pelo Price → 6.219,42
        self.assertEqual(r.data["primeiraParcela"], "6219.42")
        self.assertEqual(len(r.data["parcelas"]), 14)  # 2 de entrada + 12
        self.assertEqual(ClienteEmpreendimento.objects.count(), 0)

    def test_proposta_impossivel_volta_400_com_o_motivo(self):
        self.autenticar()
        r = self.client.post("/api/clientes-empreendimentos/simular/", {
            "unidade": self.unidade.pk,
            "meios": [{"tipo": "entrada", "valor": "500000"}],
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("passam R$ 400.000,00", r.data["detail"])
        # O negociado volta mesmo com a conta aberta: é ele que a tela usa para
        # dizer quanto falta e oferecer "usar o restante".
        self.assertEqual(r.data["valorNegociado"], "100000.00")


class VendaTests(VendaBaseTestCase):

    def _vender(self, **extra):
        dados = {
            "cliente": self.cliente.pk, "unidade": self.unidade.pk,
            "data_compra": "2026-01-10", "desconto_percentual": "10",
            "meios": [
                {"tipo": "entrada", "valor": "20000", "parcelas": 2,
                 "primeiro_vencimento": "2026-01-10"},
                {"tipo": "financiamento_direto", "valor": "70000", "parcelas": 12,
                 "juros_mensal": "1", "sistema_amortizacao": "price",
                 "primeiro_vencimento": "2026-02-10"},
            ],
        }
        dados.update(extra)
        return self.client.post("/api/clientes-empreendimentos/", dados, format="json")

    def test_venda_grava_o_negociado_e_marca_a_unidade(self):
        self.autenticar()
        r = self._vender()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["valor_compra"], "90000.00")
        self.assertEqual(r.data["valor_tabela"], "100000.00")
        self.unidade.refresh_from_db()
        self.assertEqual(self.unidade.situacao, "vendida")

    def test_empreendimento_vem_da_unidade_e_nao_do_payload(self):
        """Aceitar o empreendimento do cliente da API deixaria gravar uma venda
        cujo empreendimento contradiz o da unidade."""
        outro = Empreendimento.objects.create(
            tenant=self.tenant, empreendimento="Outro", razao_social="Outro SPE",
            cnpj="11222333000262", telefone="1133335555", endereco="Rua B",
        )
        self.autenticar()
        r = self._vender(empreendimento=outro.pk)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["empreendimento"], self.emp.pk)

    def test_mesma_unidade_nao_pode_ser_vendida_duas_vezes(self):
        self.autenticar()
        self.assertEqual(self._vender().status_code, 201)
        segunda = self._vender()
        self.assertEqual(segunda.status_code, 400)
        self.assertIn("já tem uma aquisição", str(segunda.data))

    def test_desconto_maior_que_a_tabela_e_recusado(self):
        self.autenticar()
        r = self._vender(desconto_percentual="120", meios=[])
        self.assertEqual(r.status_code, 400)


class GerarParcelasTests(VendaBaseTestCase):

    def setUp(self):
        self.autenticar()
        self.aquisicao = ClienteEmpreendimento.objects.create(
            tenant=self.tenant, cliente=self.cliente, empreendimento=self.emp,
            unidade=self.unidade, data_compra=date(2026, 1, 10),
            condicoes_pagamento="financiamento_direto",
            valor_tabela=Decimal("100000.00"), valor_compra=Decimal("100000.00"),
        )
        MeioPagamento.objects.create(
            tenant=self.tenant, aquisicao=self.aquisicao, ordem=1, tipo="entrada",
            valor=Decimal("20000.00"), parcelas=2, primeiro_vencimento=date(2026, 1, 10),
        )
        MeioPagamento.objects.create(
            tenant=self.tenant, aquisicao=self.aquisicao, ordem=2, tipo="financiamento_direto",
            valor=Decimal("80000.00"), parcelas=12, juros_mensal=Decimal("1"),
            sistema_amortizacao="price", primeiro_vencimento=date(2026, 2, 10),
        )

    def test_gera_um_titulo_por_parcela_amarrado_a_unidade(self):
        r = self.client.post(f"/api/clientes-empreendimentos/{self.aquisicao.pk}/gerar-parcelas/")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["geradas"], 14)
        titulos = ContaReceber.objects.filter(cliente_empreendimento=self.aquisicao)
        self.assertEqual(titulos.count(), 14)
        self.assertTrue(all("QD 1 · LT 01" in t.descricao for t in titulos))
        self.assertEqual(
            sum(t.valor for t in titulos), Decimal(r.data["total"]),
        )

    def test_nao_emite_boleto(self):
        """Gerar parcela é registrar dívida; cobrar é decisão do ERP, depois."""
        self.client.post(f"/api/clientes-empreendimentos/{self.aquisicao.pk}/gerar-parcelas/")
        titulos = ContaReceber.objects.filter(cliente_empreendimento=self.aquisicao)
        self.assertFalse(any(t.boletos.exists() for t in titulos))

    def test_segunda_chamada_nao_duplica_o_carne(self):
        self.client.post(f"/api/clientes-empreendimentos/{self.aquisicao.pk}/gerar-parcelas/")
        segunda = self.client.post(f"/api/clientes-empreendimentos/{self.aquisicao.pk}/gerar-parcelas/")
        self.assertEqual(segunda.status_code, 409)
        self.assertEqual(
            ContaReceber.objects.filter(cliente_empreendimento=self.aquisicao).count(), 14,
        )

    def test_parcelas_alimentam_a_carteira(self):
        """O ponto de gerar: a adimplência da tela de Clientes passa a existir."""
        self.client.post(f"/api/clientes-empreendimentos/{self.aquisicao.pk}/gerar-parcelas/")
        r = self.client.get("/api/clientes/carteira/", {"visao": "unidades"})
        linha = next(l for l in r.data["results"] if l["unidade"] == "QD 1 · LT 01")
        self.assertGreater(Decimal(linha["valorAberto"]), 0)


class CarteiraComUnidadeTests(CarteiraBaseTestCase):
    """A carteira continua de pé lendo a identificação pela FK."""

    def test_visao_de_unidades_mostra_o_rotulo_da_unidade(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "unidades"})
        self.assertEqual(
            [l["unidade"] for l in r.data["results"]],
            ["QD 3 · LT 01", "QD 12 · LT 05", "QD 12 · LT 06"],
        )

    def test_agrupar_por_quadra_atravessa_a_unidade(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/grupos/", {"visao": "unidades", "por": "quadra"})
        rotulos = sorted(g["rotulos"][0] for g in r.data["grupos"])
        self.assertEqual(rotulos, ["12", "3"])


class PermissaoDeVendaTests(VendaBaseTestCase):
    """Vender e emitir o carnê saíram de `cadastro.cliente` (F17).

    Enquanto dividiam a permissão do cadastro, quem podia corrigir o telefone de
    um comprador podia vender um lote e criar a dívida dele no ERP.
    """

    def _payload(self):
        return {
            "cliente": self.cliente.pk, "unidade": self.unidade.pk,
            "data_compra": "2026-01-10",
            "meios": [{"tipo": "a_vista", "valor": "100000.00"}],
        }

    def test_cadastro_de_cliente_nao_vende_unidade(self):
        self.autenticar(["cadastro.cliente.view", "cadastro.cliente.edit"])
        r = self.client.post("/api/clientes-empreendimentos/", self._payload(), format="json")
        self.assertEqual(r.status_code, 403)

    def test_venda_edit_vende(self):
        self.autenticar(["cadastro.venda.view", "cadastro.venda.edit"])
        r = self.client.post("/api/clientes-empreendimentos/", self._payload(), format="json")
        self.assertEqual(r.status_code, 201, r.data)

    def test_simular_e_leitura_nao_exige_vender(self):
        """Cotar é anterior a fechar: o corretor simula sem poder vender."""
        self.autenticar(["cadastro.venda.view"])
        r = self.client.post("/api/clientes-empreendimentos/simular/", {
            "unidade": self.unidade.pk,
            "meios": [{"tipo": "financiamento_direto", "valor": "100000", "parcelas": 10}],
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)

    def test_vender_nao_basta_para_gerar_o_carne(self):
        self.autenticar(["cadastro.venda.view", "cadastro.venda.edit"])
        criada = self.client.post("/api/clientes-empreendimentos/", self._payload(), format="json")
        self.assertEqual(criada.status_code, 201, criada.data)
        aquisicao_id = criada.data["cliente_empreendimento_id"]

        r = self.client.post(f"/api/clientes-empreendimentos/{aquisicao_id}/gerar-parcelas/")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(ContaReceber.objects.filter(cliente_empreendimento_id=aquisicao_id).exists())

    def test_gerar_carne_com_a_permissao_propria(self):
        self.autenticar([
            "cadastro.venda.view", "cadastro.venda.edit", "cadastro.venda.gerar_carne",
        ])
        criada = self.client.post("/api/clientes-empreendimentos/", self._payload(), format="json")
        aquisicao_id = criada.data["cliente_empreendimento_id"]
        r = self.client.post(f"/api/clientes-empreendimentos/{aquisicao_id}/gerar-parcelas/")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(ContaReceber.objects.filter(cliente_empreendimento_id=aquisicao_id).exists())


class MeiosDaVendaTests(VendaBaseTestCase):
    """A venda é uma lista livre de meios de pagamento, e a condição é o nome
    que eles dão a ela — não uma escolha à parte."""

    def _vender(self, meios, **extra):
        return self.client.post("/api/clientes-empreendimentos/", {
            "cliente": self.cliente.pk, "unidade": self.unidade.pk,
            "data_compra": "2026-01-10", "meios": meios, **extra,
        }, format="json")

    def test_catalogo_de_meios_vem_do_backend(self):
        self.autenticar()
        r = self.client.get("/api/clientes-empreendimentos/condicoes/")
        self.assertEqual(r.status_code, 200)
        tipos = {m["codigo"]: m for m in r.data["meios"]}
        self.assertEqual(tipos["outro"]["descricao"], "obrigatoria")
        self.assertTrue(tipos["entrada"]["juros"])
        self.assertFalse(tipos["fgts"]["noCarne"])
        self.assertGreater(r.data["tetoMeios"], 1)

    def test_a_vista_e_um_titulo_so(self):
        self.autenticar()
        r = self.client.post("/api/clientes-empreendimentos/simular/", {
            "unidade": self.unidade.pk, "desconto_percentual": "10",
            "meios": [{"tipo": "a_vista", "valor": "90000"}],
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["valorNegociado"], "90000.00")
        self.assertEqual(r.data["totalJuros"], "0.00")
        self.assertEqual(r.data["total"], "90000.00")
        self.assertEqual(len(r.data["parcelas"]), 1)
        self.assertEqual(r.data["condicao"], "a_vista")

    def test_venda_combinada_grava_os_meios_e_deriva_a_condicao(self):
        """Sinal + banco + FGTS: a condição é a do banco, que responde pela maior
        parte, e o que se grava é o que o motor leu — sem os juros que um FGTS
        não comporta."""
        self.autenticar()
        r = self._vender([
            {"tipo": "entrada", "valor": "10000", "parcelas": 2},
            {"tipo": "financiamento_bancario", "valor": "80000", "descricao": "Caixa"},
            {"tipo": "fgts", "valor": "10000", "juros_mensal": "2", "parcelas": 12},
        ], condicoes_pagamento="a_vista")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["condicoes_pagamento"], "financiamento_bancario")
        self.assertEqual([m["tipo"] for m in r.data["meios"]],
                         ["entrada", "financiamento_bancario", "fgts"])
        self.assertEqual([m["ordem"] for m in r.data["meios"]], [1, 2, 3])
        fgts = MeioPagamento.objects.get(tipo="fgts")
        self.assertEqual((fgts.juros_mensal, fgts.parcelas), (Decimal("0"), 1))
        self.assertEqual(r.data["valor_total_plano"], "10000.00")
        rotulos = [m["rotulo"] for m in r.data["plano"]["meios"]]
        self.assertEqual(rotulos, ["Entrada", "Financiado pelo banco — Caixa", "Pago com FGTS"])

    def test_meios_que_nao_fecham_o_negociado_voltam_400(self):
        self.autenticar()
        r = self._vender([{"tipo": "entrada", "valor": "10000"}])
        self.assertEqual(r.status_code, 400)
        self.assertIn("Faltam R$ 90.000,00", str(r.data["meios"]))
        self.assertFalse(ClienteEmpreendimento.objects.exists())

    def test_outro_sem_explicacao_volta_400(self):
        self.autenticar()
        r = self._vender([{"tipo": "outro", "valor": "100000"}])
        self.assertEqual(r.status_code, 400)
        self.assertIn("explique a condição", str(r.data["meios"]))

    def test_patch_sem_meios_mantem_os_gravados_e_revalida(self):
        """Mudar o desconto de uma venda com os mesmos meios não fecha mais a
        conta — e o PATCH precisa dizer isso, não gravar um plano furado."""
        self.autenticar()
        criada = self._vender([{"tipo": "a_vista", "valor": "100000"}])
        url = f"/api/clientes-empreendimentos/{criada.data['cliente_empreendimento_id']}/"
        r = self.client.patch(url, {"desconto_percentual": "10"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.patch(url, {"observacoes_compra": "cliente pediu boleto por e-mail"},
                              format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(len(r.data["meios"]), 1)

    def test_patch_com_meios_substitui_a_lista(self):
        self.autenticar()
        criada = self._vender([{"tipo": "a_vista", "valor": "100000"}])
        url = f"/api/clientes-empreendimentos/{criada.data['cliente_empreendimento_id']}/"
        r = self.client.patch(url, {"meios": [
            {"tipo": "permuta", "valor": "40000", "descricao": "Gol 2019"},
            {"tipo": "cartao", "valor": "60000", "parcelas": 10},
        ]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(MeioPagamento.objects.count(), 2)
        self.assertEqual(r.data["condicoes_pagamento"], "cartao")
        # A resposta já é a lista nova — não a que o prefetch tinha em cache.
        self.assertEqual([m["tipo"] for m in r.data["meios"]], ["permuta", "cartao"])
        self.assertEqual(r.data["plano"]["foraDoCarne"], "40000.00")

    def test_datas_livres_gravam_a_lista_e_viram_titulos(self):
        """Item 76: o valor do meio vem da soma das linhas (o enviado é
        ignorado), a lista fica gravada em ordem de data, e cada linha vira um
        título com a data que o vendedor digitou."""
        self.autenticar()
        criada = self._vender([
            {"tipo": "entrada", "valor": "40000"},
            {"tipo": "datas_livres", "valor": "1", "cronograma": [
                {"vencimento": "2026-12-20", "valor": "35000"},
                {"vencimento": "2026-06-20", "valor": "25000"},
            ]},
        ])
        self.assertEqual(criada.status_code, 201, criada.data)
        meio = MeioPagamento.objects.get(tipo="datas_livres")
        self.assertEqual(meio.valor, Decimal("60000.00"))
        self.assertEqual([l["vencimento"] for l in meio.cronograma], ["2026-06-20", "2026-12-20"])
        r = self.client.post(
            f"/api/clientes-empreendimentos/{criada.data['cliente_empreendimento_id']}/gerar-parcelas/")
        self.assertEqual(r.status_code, 201, r.data)
        descricoes = set(ContaReceber.objects.values_list("descricao", flat=True))
        self.assertIn("Parcela 2/2 — Residencial Ipê · QD 1 · LT 01", descricoes)

    def test_carne_numera_por_meio(self):
        """Dois financiamentos diretos são duas séries no boleto."""
        self.autenticar()
        criada = self._vender([
            {"tipo": "financiamento_direto", "valor": "40000", "parcelas": 2},
            {"tipo": "financiamento_direto", "valor": "60000", "parcelas": 3, "juros_mensal": "1"},
        ])
        self.assertEqual(criada.status_code, 201, criada.data)
        aquisicao_id = criada.data["cliente_empreendimento_id"]
        r = self.client.post(f"/api/clientes-empreendimentos/{aquisicao_id}/gerar-parcelas/")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["geradas"], 5)
        descricoes = set(ContaReceber.objects.values_list("descricao", flat=True))
        self.assertIn("Parcela 2/2 (1ª série) — Residencial Ipê · QD 1 · LT 01", descricoes)
        self.assertIn("Parcela 3/3 (2ª série) — Residencial Ipê · QD 1 · LT 01", descricoes)


class ResumoDeUnidadesTests(VendaBaseTestCase):
    """O estoque inteiro contado no banco — não as linhas que a página baixou.

    Dois números da aba Unidades eram calculados sobre a **página carregada** e
    apresentados como se fossem do empreendimento: "40 à venda · 160 vendidas" e
    a lista de quadras do filtro. Num loteamento de 800 lotes com página de 100,
    o primeiro é uma amostra com cara de total e o segundo obriga a clicar
    "Carregar mais" até o fim para poder filtrar — carregar tudo para poder não
    carregar tudo.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Quadras fora de ordem alfabética de propósito: "10" tem de vir depois
        # de "2", como na grade.
        for quadra, lote, situacao in [
            ("2", "01", "disponivel"), ("2", "02", "vendida"),
            ("10", "01", "reservada"), ("10", "02", "indisponivel"),
            ("10", "03", "vendida"),
        ]:
            Unidade.objects.create(
                tenant=cls.tenant, empreendimento=cls.emp, quadra=quadra, lote=lote,
                situacao=situacao, valor_base=Decimal("50000.00"),
            )

    def _resumo(self, **params):
        self.autenticar()
        r = self.client.get("/api/unidades/resumo/", {"empreendimento": self.emp.pk, **params})
        self.assertEqual(r.status_code, 200, r.data)
        return r.data

    def test_conta_as_quatro_situacoes_sobre_o_estoque_inteiro(self):
        dados = self._resumo()
        # 5 criadas aqui + a `cls.unidade` da base, que nasce disponível.
        self.assertEqual(dados["total"], 6)
        self.assertEqual(dados["por_situacao"], {
            "disponivel": 2, "reservada": 1, "vendida": 2, "indisponivel": 1,
        })

    def test_quadras_saem_todas_e_em_ordem_natural(self):
        self.assertEqual(self._resumo()["quadras"], ["1", "2", "10"])

    def test_o_filtro_de_quadra_nao_encolhe_a_lista_de_quadras(self):
        """Um seletor que se reduz à escolha já feita não deixa trocar de
        escolha — os contadores respeitam o filtro, a lista não."""
        dados = self._resumo(quadra="10")
        self.assertEqual(dados["quadras"], ["1", "2", "10"])
        self.assertEqual(dados["total"], 3)
        self.assertEqual(dados["por_situacao"]["vendida"], 1)

    def test_a_situacao_filtrada_reduz_os_contadores(self):
        dados = self._resumo(situacao="vendida")
        self.assertEqual(dados["total"], 2)
        self.assertEqual(dados["por_situacao"]["disponivel"], 0)

    def test_situacoes_vem_rotuladas_para_a_tela_nao_traduzir(self):
        rotulos = {s["valor"]: s["rotulo"] for s in self._resumo()["situacoes"]}
        self.assertEqual(rotulos["disponivel"], "Disponível")
        self.assertEqual(len(rotulos), 4)


class BuscaDeUnidadesTests(VendaBaseTestCase):
    """Item 78: a busca da aba Unidades acha a unidade como a tela a escreve.

    Antes era `icontains` sobre cada campo: "QD 2 LT 01" procurava "QD" num
    campo que guarda "2" e não voltava nada, e "1" trazia a quadra 10 junto.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for quadra, lote in [("2", "01"), ("2", "10"), ("10", "01"), ("12", "05")]:
            Unidade.objects.create(
                tenant=cls.tenant, empreendimento=cls.emp, quadra=quadra, lote=lote,
                valor_base=Decimal("50000.00"),
            )
        cls.vendida = Unidade.objects.get(quadra="12", lote="05")
        ClienteEmpreendimento.objects.create(
            tenant=cls.tenant, cliente=cls.cliente, empreendimento=cls.emp,
            unidade=cls.vendida, data_compra=date(2026, 1, 10),
            valor_tabela=Decimal("50000.00"), valor_compra=Decimal("50000.00"),
            condicoes_pagamento="a_vista",
        )

    def _rotulos(self, busca):
        self.autenticar()
        r = self.client.get("/api/unidades/", {"empreendimento": self.emp.pk, "search": busca})
        self.assertEqual(r.status_code, 200, r.data)
        return [u["rotulo"] for u in r.data["results"]]

    def test_acha_pelo_rotulo_que_a_tela_mostra(self):
        self.assertEqual(self._rotulos("QD 2 · LT 01"), ["QD 2 · LT 01"])
        self.assertEqual(self._rotulos("qd2 lt1"), ["QD 2 · LT 01"])
        self.assertEqual(self._rotulos("quadra 12"), ["QD 12 · LT 05"])

    def test_numero_solto_e_o_nivel_inteiro_e_nao_um_trecho(self):
        """"1" é a quadra 1 ou o lote 1 — não a quadra 10 nem o lote 10."""
        self.assertEqual(self._rotulos("1"), [
            "QD 1 · LT 01", "QD 2 · LT 01", "QD 10 · LT 01",
        ])

    def test_acha_pelo_comprador_e_combina_com_o_endereco(self):
        self.assertEqual(self._rotulos("marina"), ["QD 12 · LT 05"])
        self.assertEqual(self._rotulos("rocha qd 12"), ["QD 12 · LT 05"])

    def test_o_resumo_conta_pela_mesma_busca(self):
        self.autenticar()
        r = self.client.get("/api/unidades/resumo/", {"empreendimento": self.emp.pk, "search": "QD 2"})
        self.assertEqual(r.data["total"], 2)


class ContagemDaCarteiraAgrupadaTests(VendaBaseTestCase):
    """Agrupar não pode mudar quantos clientes existem.

    O contador da barra somava os cabeçalhos. Agrupar pessoas por uma dimensão
    de muitos (empreendimento) põe quem comprou em dois lugares nos dois grupos
    — cada grupo conta distinto e está certo dentro de si —, então a soma
    passava do total e o número de clientes "mudava" por causa de um clique.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.emp2 = Empreendimento.objects.create(
            tenant=cls.tenant, empreendimento="Residencial Jacarandá",
            razao_social="Jacarandá SPE", cnpj="11222333000262",
            telefone="1133334445", endereco="Rua B, 2", cidade="Palhoça", estado="SC",
        )
        cls.unidade2 = Unidade.objects.create(
            tenant=cls.tenant, empreendimento=cls.emp2, quadra="1", lote="02",
            valor_base=Decimal("80000.00"),
        )
        # O MESMO cliente comprando nos dois empreendimentos.
        for unidade, emp in ((cls.unidade, cls.emp), (cls.unidade2, cls.emp2)):
            ClienteEmpreendimento.objects.create(
                tenant=cls.tenant, cliente=cls.cliente, empreendimento=emp,
                unidade=unidade, data_compra=date(2026, 1, 10),
                condicoes_pagamento="a_vista",
                valor_tabela=unidade.valor_base, valor_compra=unidade.valor_base,
            )

    def test_o_total_nao_muda_ao_agrupar(self):
        self.autenticar()
        plana = self.client.get("/api/clientes/carteira/", {"visao": "clientes"})
        agrupada = self.client.get(
            "/api/clientes/carteira/grupos/",
            {"visao": "clientes", "por": "empreendimento"},
        )
        self.assertEqual(agrupada.data["count"], plana.data["count"])

    def test_a_soma_dos_grupos_vem_declarada_quando_diverge(self):
        """A divergência não é escondida: ela é explicada. Somar dois grupos de
        um cliente só dá dois, e a tela precisa poder dizer por quê."""
        self.autenticar()
        r = self.client.get(
            "/api/clientes/carteira/grupos/",
            {"visao": "clientes", "por": "empreendimento"},
        )
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["somaDosGrupos"], 2)
        self.assertEqual(len(r.data["grupos"]), 2)

    def test_na_visao_de_unidades_a_soma_fecha(self):
        """Ali a linha é a aquisição, e cada aquisição tem um empreendimento só."""
        self.autenticar()
        r = self.client.get(
            "/api/clientes/carteira/grupos/",
            {"visao": "unidades", "por": "empreendimento"},
        )
        self.assertEqual(r.data["somaDosGrupos"], r.data["count"])
