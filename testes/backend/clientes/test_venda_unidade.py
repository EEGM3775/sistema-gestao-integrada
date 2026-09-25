"""A venda de uma unidade, ponta a ponta pela API.

Cobre o que a mudança de modelo promete: a unidade é cadastro do empreendimento,
uma unidade tem um dono só, o preço parte da tabela e o carnê só nasce quando o
usuário manda — sem boleto junto.
"""
from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from clientes.models import ClienteEmpreendimento
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
            condicoes_pagamento="a_vista", entrada_valor=Decimal("100000.00"),
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
            "entrada_valor": "20000", "entrada_parcelas": 2,
            "sistema_amortizacao": "price", "juros_mensal": "1",
            "num_parcelas": 12, "data_compra": "2026-01-10",
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
            "unidade": self.unidade.pk, "entrada_valor": "500000",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("balões", r.data["detail"])


class VendaTests(VendaBaseTestCase):

    def _vender(self, **extra):
        dados = {
            "cliente": self.cliente.pk, "unidade": self.unidade.pk,
            "data_compra": "2026-01-10", "condicoes_pagamento": "financiamento_direto",
            "desconto_percentual": "10", "entrada_valor": "20000", "entrada_parcelas": 2,
            "entrada_primeiro_vencimento": "2026-01-10",
            "sistema_amortizacao": "price", "juros_mensal": "1", "num_parcelas": 12,
            "primeiro_vencimento": "2026-02-10",
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
        r = self._vender(desconto_percentual="120", entrada_valor="0")
        self.assertEqual(r.status_code, 400)


class GerarParcelasTests(VendaBaseTestCase):

    def setUp(self):
        self.autenticar()
        self.aquisicao = ClienteEmpreendimento.objects.create(
            tenant=self.tenant, cliente=self.cliente, empreendimento=self.emp,
            unidade=self.unidade, data_compra=date(2026, 1, 10),
            condicoes_pagamento="financiamento_direto",
            valor_tabela=Decimal("100000.00"), valor_compra=Decimal("100000.00"),
            entrada_valor=Decimal("20000.00"), entrada_parcelas=2,
            entrada_primeiro_vencimento=date(2026, 1, 10),
            sistema_amortizacao="price", juros_mensal=Decimal("1"), num_parcelas=12,
            primeiro_vencimento=date(2026, 2, 10),
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
            "data_compra": "2026-01-10", "condicoes_pagamento": "a_vista",
            "entrada_valor": "100000.00",
        }

    def test_cadastro_de_cliente_nao_vende_unidade(self):
        self.autenticar(["cadastro.cliente.view", "cadastro.cliente.edit"])
        r = self.client.post("/api/clientes-empreendimentos/", self._payload())
        self.assertEqual(r.status_code, 403)

    def test_venda_edit_vende(self):
        self.autenticar(["cadastro.venda.view", "cadastro.venda.edit"])
        r = self.client.post("/api/clientes-empreendimentos/", self._payload())
        self.assertEqual(r.status_code, 201, r.data)

    def test_simular_e_leitura_nao_exige_vender(self):
        """Cotar é anterior a fechar: o corretor simula sem poder vender."""
        self.autenticar(["cadastro.venda.view"])
        r = self.client.post("/api/clientes-empreendimentos/simular/", {
            "unidade": self.unidade.pk, "num_parcelas": 10,
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)

    def test_vender_nao_basta_para_gerar_o_carne(self):
        self.autenticar(["cadastro.venda.view", "cadastro.venda.edit"])
        criada = self.client.post("/api/clientes-empreendimentos/", self._payload())
        self.assertEqual(criada.status_code, 201, criada.data)
        aquisicao_id = criada.data["cliente_empreendimento_id"]

        r = self.client.post(f"/api/clientes-empreendimentos/{aquisicao_id}/gerar-parcelas/")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(ContaReceber.objects.filter(cliente_empreendimento_id=aquisicao_id).exists())

    def test_gerar_carne_com_a_permissao_propria(self):
        self.autenticar([
            "cadastro.venda.view", "cadastro.venda.edit", "cadastro.venda.gerar_carne",
        ])
        criada = self.client.post("/api/clientes-empreendimentos/", self._payload())
        aquisicao_id = criada.data["cliente_empreendimento_id"]
        r = self.client.post(f"/api/clientes-empreendimentos/{aquisicao_id}/gerar-parcelas/")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(ContaReceber.objects.filter(cliente_empreendimento_id=aquisicao_id).exists())


class CondicaoDePagamentoTests(VendaBaseTestCase):
    """A condição de pagamento deixou de ser rótulo e passou a reger o plano."""

    def test_a_vista_e_pagamento_unico_sem_prazo(self):
        self.autenticar()
        r = self.client.post("/api/clientes-empreendimentos/simular/", {
            "unidade": self.unidade.pk, "condicoes_pagamento": "a_vista",
            "desconto_percentual": "10",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["valorNegociado"], "90000.00")
        self.assertEqual(r.data["entrada"], "90000.00")
        self.assertEqual(r.data["totalJuros"], "0.00")
        self.assertEqual(r.data["total"], "90000.00")
        self.assertEqual(len(r.data["parcelas"]), 1)

    def test_a_vista_ignora_prazo_e_juros_que_venham_no_payload(self):
        """A condição manda: mandar 60x junto de 'à vista' não cria 60 parcelas."""
        self.autenticar()
        r = self.client.post("/api/clientes-empreendimentos/simular/", {
            "unidade": self.unidade.pk, "condicoes_pagamento": "a_vista",
            "num_parcelas": 60, "juros_mensal": "1.5", "entrada_valor": "1000",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(len(r.data["parcelas"]), 1)
        self.assertEqual(r.data["totalJuros"], "0.00")

    def test_venda_a_vista_grava_o_plano_sem_parcelas(self):
        self.autenticar()
        r = self.client.post("/api/clientes-empreendimentos/", {
            "cliente": self.cliente.pk, "unidade": self.unidade.pk,
            "data_compra": "2026-01-10", "condicoes_pagamento": "a_vista",
            "num_parcelas": 60, "juros_mensal": "1.5",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["num_parcelas"], 0)
        self.assertEqual(r.data["valor_total_plano"], "100000.00")

    def test_carne_a_vista_tem_um_titulo_so(self):
        self.autenticar()
        criada = self.client.post("/api/clientes-empreendimentos/", {
            "cliente": self.cliente.pk, "unidade": self.unidade.pk,
            "data_compra": "2026-01-10", "condicoes_pagamento": "a_vista",
        }, format="json")
        aquisicao_id = criada.data["cliente_empreendimento_id"]
        r = self.client.post(f"/api/clientes-empreendimentos/{aquisicao_id}/gerar-parcelas/")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["geradas"], 1)


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
                entrada_valor=unidade.valor_base,
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
