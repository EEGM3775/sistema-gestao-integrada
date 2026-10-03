"""Testes da carteira de clientes (a grade tipo planilha da tela de Clientes).

Cobrem o que a tela promete e o que a LGPD exige: as duas visões, a adimplência
derivada do vencimento, o gate de duas pontas dos números financeiros, os
subtotais de grupo calculados sobre a carteira inteira e as abas Financeiro/Obra
da ficha.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from clientes.models import Cliente, ClienteEmpreendimento
from empreendimentos.models import Empreendimento, Unidade
from moduloerp.models import ContaReceber, StatusConta
from nucleo.models import Tenant, Usuario
from obras.models import EtapaObra, Obra


class CarteiraBaseTestCase(APITestCase):
    """Uma carteira pequena e explícita: dois clientes, três unidades.

    Ana comprou dois lotes na mesma quadra (o caso que o vínculo parcela↔unidade
    existe para resolver) e está atrasada em um deles; Bruno comprou um lote e
    está em dia.
    """

    @classmethod
    def setUpTestData(cls):
        cls.hoje = timezone.localdate()
        cls.tenant = Tenant.objects.create(slug="carteira", nome="Loteadora Teste")
        cls.user = Usuario.objects.create(username="carteira_user", tenant=cls.tenant)

        cls.emp = Empreendimento.objects.create(
            tenant=cls.tenant, empreendimento="Residencial Alfa", razao_social="Alfa SPE",
            cnpj="11222333000181", telefone="1133334444", endereco="Rod. BR-101, km 12",
            cidade="Palhoça", estado="SC",
        )
        cls.emp2 = Empreendimento.objects.create(
            tenant=cls.tenant, empreendimento="Residencial Beta", razao_social="Beta SPE",
            cnpj="11222333000262", telefone="1133335555", endereco="Av. Central, 900",
            cidade="Biguaçu", estado="SC",
        )

        cls.ana = Cliente.objects.create(
            tenant=cls.tenant, nome_completo="Ana Souza", cpf_cnpj="52998224725",
            email="ana@exemplo.com", telefone="48999990001", data_nascimento=date(1985, 3, 12),
            cidade="Florianópolis", estado="SC",
        )
        cls.bruno = Cliente.objects.create(
            tenant=cls.tenant, nome_completo="Bruno Lima", cpf_cnpj="15350946056",
            email="bruno@exemplo.com", telefone="48999990002", data_nascimento=date(1979, 8, 30),
            cidade="São José", estado="SC",
        )

        # As unidades existem antes do comprador — cadastro do empreendimento.
        cls.un_lote5 = Unidade.objects.create(
            tenant=cls.tenant, empreendimento=cls.emp, quadra="12", lote="05",
            valor_base=Decimal("180000.00"), endereco="Rua A, 100",
        )
        cls.un_lote6 = Unidade.objects.create(
            tenant=cls.tenant, empreendimento=cls.emp, quadra="12", lote="06",
            valor_base=Decimal("200000.00"), endereco="Rua A, 120",
        )
        cls.un_lote1 = Unidade.objects.create(
            tenant=cls.tenant, empreendimento=cls.emp2, quadra="3", lote="01",
            valor_base=Decimal("150000.00"), endereco="Rua B, 10",
        )

        cls.ana_lote5 = ClienteEmpreendimento.objects.create(
            tenant=cls.tenant, cliente=cls.ana, empreendimento=cls.emp,
            unidade=cls.un_lote5, data_compra=date(2025, 2, 10),
            valor_tabela=Decimal("180000.00"), valor_compra=Decimal("180000.00"),
            condicoes_pagamento="financiamento_direto",
        )
        cls.ana_lote6 = ClienteEmpreendimento.objects.create(
            tenant=cls.tenant, cliente=cls.ana, empreendimento=cls.emp,
            unidade=cls.un_lote6, data_compra=date(2025, 6, 1),
            valor_tabela=Decimal("200000.00"), valor_compra=Decimal("200000.00"),
            condicoes_pagamento="a_vista",
        )
        cls.bruno_lote1 = ClienteEmpreendimento.objects.create(
            tenant=cls.tenant, cliente=cls.bruno, empreendimento=cls.emp2,
            unidade=cls.un_lote1, data_compra=date(2024, 11, 20),
            valor_tabela=Decimal("150000.00"), valor_compra=Decimal("150000.00"),
            condicoes_pagamento="a_vista",
        )

        # Ana: uma parcela vencida há 45 dias no lote 5 (faixa 31-60) e uma a
        # vencer no lote 6 — a inadimplência é do lote 5, não do 6.
        cls.parcela_atrasada = ContaReceber.objects.create(
            tenant=cls.tenant, cliente=cls.ana, empreendimento=cls.emp,
            cliente_empreendimento=cls.ana_lote5, descricao="Parcela 3/60",
            valor=Decimal("1500.00"), data_vencimento=cls.hoje - timedelta(days=45),
            status=StatusConta.ABERTO,
        )
        ContaReceber.objects.create(
            tenant=cls.tenant, cliente=cls.ana, empreendimento=cls.emp,
            cliente_empreendimento=cls.ana_lote6, descricao="Parcela 1/12",
            valor=Decimal("900.00"), data_vencimento=cls.hoje + timedelta(days=15),
            status=StatusConta.ABERTO,
        )
        # Bruno: tudo quitado.
        ContaReceber.objects.create(
            tenant=cls.tenant, cliente=cls.bruno, empreendimento=cls.emp2,
            cliente_empreendimento=cls.bruno_lote1, descricao="À vista",
            valor=Decimal("150000.00"), valor_pago=Decimal("150000.00"),
            data_vencimento=cls.hoje - timedelta(days=200), status=StatusConta.QUITADO,
        )

    def autenticar(self, *, permissoes=None, admin=False):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = permissoes if permissoes is not None else [
            "cadastro.cliente.view", "cadastro.cliente_doc.view", "erp.cobranca.view",
        ]
        self.user.is_tenant_admin = admin
        self.client.force_authenticate(user=self.user)


class CarteiraVisoesTests(CarteiraBaseTestCase):

    def test_visao_clientes_tem_uma_linha_por_pessoa(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 2)
        ana = next(l for l in r.data["results"] if l["nome"] == "Ana Souza")
        self.assertEqual(ana["unidadesTotal"], 2)
        # A unidade exibida é a última compra (LT 06), com o contador ao lado.
        self.assertEqual(ana["unidade"], "QD 12 · LT 06")

    def test_visao_unidades_tem_uma_linha_por_aquisicao(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "unidades"})
        self.assertEqual(r.data["count"], 3)
        rotulos = sorted(l["unidade"] for l in r.data["results"])
        self.assertEqual(rotulos, ["QD 12 · LT 05", "QD 12 · LT 06", "QD 3 · LT 01"])

    def test_atraso_fica_no_lote_certo(self):
        """O motivo de existir do vínculo parcela↔unidade."""
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "unidades"})
        por_unidade = {l["unidade"]: l for l in r.data["results"]}
        self.assertFalse(por_unidade["QD 12 · LT 05"]["adimplente"])
        self.assertEqual(por_unidade["QD 12 · LT 05"]["faixa"], "d31_60")
        self.assertTrue(por_unidade["QD 12 · LT 06"]["adimplente"])
        self.assertEqual(por_unidade["QD 12 · LT 06"]["faixa"], "em_dia")

    def test_cliente_herda_a_pior_situacao_das_unidades(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes"})
        ana = next(l for l in r.data["results"] if l["nome"] == "Ana Souza")
        self.assertFalse(ana["adimplente"])
        self.assertEqual(ana["parcelasAtraso"], 1)
        self.assertEqual(Decimal(ana["valorAtraso"]), Decimal("1500.00"))
        # A parcela a vencer entra no aberto, não no atraso.
        self.assertEqual(Decimal(ana["valorAberto"]), Decimal("2400.00"))

    def test_venda_sem_parcela_nao_e_adimplente(self):
        """Item 60 — sem carnê gerado não há adimplência a afirmar."""
        carla = Cliente.objects.create(
            tenant=self.tenant, nome_completo="Carla Sem Carnê", cpf_cnpj="11144477735",
            email="carla@exemplo.com", telefone="48999990003", data_nascimento=date(1990, 1, 1),
            cidade="Florianópolis", estado="SC",
        )
        lote2 = Unidade.objects.create(
            tenant=self.tenant, empreendimento=self.emp2, quadra="3", lote="02",
            valor_base=Decimal("1"), endereco="Rua B, 20",
        )
        ClienteEmpreendimento.objects.create(
            tenant=self.tenant, cliente=carla, empreendimento=self.emp2, unidade=lote2,
            data_compra=date(2026, 9, 1), valor_tabela=Decimal("1"), valor_compra=Decimal("1"),
        )
        # Parcela cancelada também não conta como histórico de pagamento.
        ContaReceber.objects.create(
            tenant=self.tenant, cliente=carla, empreendimento=self.emp2, descricao="Cancelada",
            valor=Decimal("10.00"), data_vencimento=self.hoje - timedelta(days=5),
            status=StatusConta.CANCELADO,
        )
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes"})
        linha = next(l for l in r.data["results"] if l["nome"] == "Carla Sem Carnê")
        self.assertIsNone(linha["adimplente"])
        self.assertEqual(linha["faixa"], "sem_parcelas")

        filtro = self.client.get("/api/clientes/carteira/", {"visao": "clientes", "faixa": "sem_parcelas"})
        self.assertEqual([l["nome"] for l in filtro.data["results"]], ["Carla Sem Carnê"])
        em_dia = self.client.get("/api/clientes/carteira/", {"visao": "clientes", "faixa": "em_dia"})
        self.assertNotIn("Carla Sem Carnê", [l["nome"] for l in em_dia.data["results"]])

        ficha = self.client.get(f"/api/clientes/{carla.pk}/financeiro/")
        self.assertIsNone(ficha.data["resumo"]["adimplente"])

    def test_titulo_quitado_nao_conta_como_aberto(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes"})
        bruno = next(l for l in r.data["results"] if l["nome"] == "Bruno Lima")
        self.assertTrue(bruno["adimplente"])
        self.assertEqual(Decimal(bruno["valorAberto"]), Decimal("0"))


class CarteiraGateFinanceiroTests(CarteiraBaseTestCase):
    """LGPD: a situação é de todos, os números são de quem tem `erp.cobranca.view`."""

    def test_sem_permissao_financeira_a_pilula_aparece_sem_numeros(self):
        self.autenticar(permissoes=["cadastro.cliente.view"])
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["podeFinanceiro"])
        ana = next(l for l in r.data["results"] if l["nome"] == "Ana Souza")
        self.assertIn("adimplente", ana)
        self.assertFalse(ana["adimplente"])
        for campo in ("parcelasAtraso", "valorAtraso", "valorAberto", "diasAtraso"):
            self.assertNotIn(campo, ana)
        self.assertIsNone(ana["valorVenda"])

    def test_sem_permissao_de_documento_o_cpf_vem_mascarado(self):
        self.autenticar(permissoes=["cadastro.cliente.view", "erp.cobranca.view"])
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes"})
        ana = next(l for l in r.data["results"] if l["nome"] == "Ana Souza")
        self.assertNotEqual(ana["documento"], "52998224725")
        self.assertIn("•", ana["documento"])

    def test_ordenar_por_valor_e_ignorado_sem_permissao(self):
        """Ordenar por dívida é ler a dívida — sem a permissão, cai na ordem padrão."""
        self.autenticar(permissoes=["cadastro.cliente.view"])
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes", "ordenar": "-valor_atraso"})
        self.assertEqual([l["nome"] for l in r.data["results"]], ["Ana Souza", "Bruno Lima"])

    def test_extrato_do_cliente_exige_permissao_financeira(self):
        self.autenticar(permissoes=["cadastro.cliente.view"])
        self.assertEqual(self.client.get(f"/api/clientes/{self.ana.pk}/financeiro/").status_code, 403)


class BuscaPorDocumentoLgpdTests(CarteiraBaseTestCase):
    """D257 — o CPF só é critério de busca para quem pode lê-lo.

    Buscar por um CPF e ver quem volta é ler o documento que a máscara esconde:
    sem `cadastro.cliente_doc.view` a resposta não pode depender dele — nem na
    carteira, nem na busca do cadastro, nem no filtro `?cpf_cnpj=`.
    """
    CPF_ANA = "52998224725"

    def test_carteira_sem_permissao_nao_acha_pelo_cpf(self):
        self.autenticar(permissoes=["cadastro.cliente.view"])
        for visao in ("clientes", "unidades"):
            for busca in (self.CPF_ANA, "529.982.247-25", "98224"):
                r = self.client.get("/api/clientes/carteira/", {"visao": visao, "busca": busca})
                self.assertEqual(r.data["count"], 0, (visao, busca))
        # O resto da busca continua de pé.
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes", "busca": "Ana"})
        self.assertEqual([l["nome"] for l in r.data["results"]], ["Ana Souza"])

    def test_carteira_com_permissao_acha_pelo_cpf(self):
        self.autenticar()
        for visao in ("clientes", "unidades"):
            r = self.client.get("/api/clientes/carteira/", {"visao": visao, "busca": "529.982.247-25"})
            self.assertEqual({l["nome"] for l in r.data["results"]}, {"Ana Souza"}, visao)

    def test_cadastro_sem_permissao_nao_acha_pelo_cpf(self):
        self.autenticar(permissoes=["cadastro.cliente.view"])
        self.assertEqual(self.client.get("/api/clientes/", {"search": self.CPF_ANA}).data["count"], 0)
        self.assertEqual(self.client.get("/api/clientes/", {"cpf_cnpj": self.CPF_ANA}).data["count"], 0)
        self.assertEqual(self.client.get("/api/clientes/", {"search": "Ana"}).data["count"], 1)

    def test_cadastro_com_permissao_acha_pelo_cpf(self):
        self.autenticar()
        self.assertEqual(self.client.get("/api/clientes/", {"search": self.CPF_ANA}).data["count"], 1)
        self.assertEqual(self.client.get("/api/clientes/", {"cpf_cnpj": self.CPF_ANA}).data["count"], 1)


class CarteiraOrdenacaoTests(CarteiraBaseTestCase):
    """Cada visão tem a sua ordem padrão, e toda coluna é ordenável."""

    def test_clientes_saem_em_ordem_alfabetica_por_padrao(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes"})
        self.assertEqual([l["nome"] for l in r.data["results"]], ["Ana Souza", "Bruno Lima"])

    def test_unidades_saem_na_ordem_do_endereco_por_padrao(self):
        """Quadra › lote › bloco › andar › apto — e **numérica**: a quadra 3 vem
        antes da 12, que em ordem alfabética viria primeiro ("12" < "3")."""
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "unidades"})
        self.assertEqual(
            [l["unidade"] for l in r.data["results"]],
            ["QD 3 · LT 01", "QD 12 · LT 05", "QD 12 · LT 06"],
        )

    def test_ordenar_pela_unidade_na_visao_de_clientes(self):
        """A pessoa ordenada pela unidade dela — Bruno (QD 3) antes de Ana (QD 12)."""
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes", "ordenar": "unidade"})
        self.assertEqual([l["nome"] for l in r.data["results"]], ["Bruno Lima", "Ana Souza"])

    def test_ordem_descendente_inverte_a_composta_inteira(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "unidades", "ordenar": "-unidade"})
        self.assertEqual(
            [l["unidade"] for l in r.data["results"]],
            ["QD 12 · LT 06", "QD 12 · LT 05", "QD 3 · LT 01"],
        )

    def test_colunas_de_cadastro_sao_ordenaveis(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "unidades", "ordenar": "-empreendimento"})
        self.assertEqual(
            [l["empreendimento"] for l in r.data["results"]],
            ["Residencial Beta", "Residencial Alfa", "Residencial Alfa"],
        )

    def test_ordenar_por_documento_e_ignorado_sem_a_permissao_do_cpf(self):
        """Ordenar por CPF é lê-lo: sem `cadastro.cliente_doc.view` cai no padrão.

        Sem o gate, quem só vê `••••25` reconstruiria o documento comparando as
        posições da lista.
        """
        self.autenticar(permissoes=["cadastro.cliente.view"])
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes", "ordenar": "documento"})
        self.assertEqual([l["nome"] for l in r.data["results"]], ["Ana Souza", "Bruno Lima"])

        self.autenticar(permissoes=["cadastro.cliente.view", "cadastro.cliente_doc.view"])
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes", "ordenar": "documento"})
        self.assertEqual([l["nome"] for l in r.data["results"]], ["Bruno Lima", "Ana Souza"])


class CarteiraFiltrosTests(CarteiraBaseTestCase):

    def test_filtro_por_faixa_de_atraso(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "unidades", "faixa": "d31_60"})
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["unidade"], "QD 12 · LT 05")

    def test_filtro_em_dia_traz_quem_nao_tem_vencido(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "unidades", "faixa": "em_dia"})
        self.assertEqual(r.data["count"], 2)

    def test_busca_por_quadra_e_lote(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "unidades", "busca": "12"})
        self.assertEqual(r.data["count"], 2)

    def test_busca_pela_unidade_como_a_tela_escreve(self):
        """Item do dono (03/10/2026): "QD 14" não achava nada."""
        self.autenticar()
        for busca, esperado in (
            ("QD 12", ["QD 12 · LT 05", "QD 12 · LT 06"]),
            ("QD 12 · LT 05", ["QD 12 · LT 05"]),
            ("qd12 lt5", ["QD 12 · LT 05"]),
            ("quadra 12 lote 6", ["QD 12 · LT 06"]),
            ("Ana LT 06", ["QD 12 · LT 06"]),
            ("5", ["QD 12 · LT 05"]),
        ):
            r = self.client.get("/api/clientes/carteira/", {"visao": "unidades", "busca": busca})
            self.assertEqual(sorted(l["unidade"] for l in r.data["results"]), esperado, busca)

    def test_busca_por_unidade_de_predio_e_de_casa(self):
        """Vertical e casas: o bloco é texto livre ("Torre A" ou "B"), casa e
        sala moram no número."""
        def vender(nome, cpf, **unidade):
            cliente = Cliente.objects.create(
                tenant=self.tenant, nome_completo=nome, cpf_cnpj=cpf, email=f"{cpf}@x.com",
                telefone="48999990009", data_nascimento=date(1990, 1, 1), cidade="Itajaí", estado="SC",
            )
            un = Unidade.objects.create(
                tenant=self.tenant, empreendimento=self.emp2, valor_base=Decimal("1"), **unidade,
            )
            ClienteEmpreendimento.objects.create(
                tenant=self.tenant, cliente=cliente, empreendimento=self.emp2, unidade=un,
                data_compra=date(2026, 1, 1), valor_tabela=Decimal("1"), valor_compra=Decimal("1"),
            )
        vender("Davi Torre", "11144477735", bloco_torre="Torre A", andar="3", apto="302")
        vender("Eva Bloco", "52998224726", bloco_torre="B", andar="12", apto="1201")
        vender("Fábio Casa", "52998224727", apto="Casa 7")
        self.autenticar()
        for busca, esperado in (
            ("Torre A apto 302", ["Davi Torre"]),
            ("torre a", ["Davi Torre"]),
            ("BL B AP 1201", ["Eva Bloco"]),
            ("bla", ["Davi Torre"]),  # bloco e torre são o mesmo nível
            ("BLB", ["Eva Bloco"]),
            ("3º andar", ["Davi Torre"]),
            ("pav 12", ["Eva Bloco"]),
            ("302", ["Davi Torre"]),
            ("casa 7", ["Fábio Casa"]),
            ("cs07", ["Fábio Casa"]),
        ):
            r = self.client.get("/api/clientes/carteira/", {"visao": "unidades", "busca": busca})
            self.assertEqual(sorted(l["nome"] for l in r.data["results"]), esperado, busca)

    def test_busca_pelo_nome_do_empreendimento_com_numero(self):
        """"Loteamento Demo 1" não pode virar "Loteamento" + "Demo" + quadra 1."""
        self.emp.empreendimento = "Loteamento Demo 1"
        self.emp.save()
        self.emp2.empreendimento = "Loteamento Demo 10"
        self.emp2.save()
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "unidades", "busca": "Loteamento Demo 1"})
        self.assertEqual(sorted(l["unidade"] for l in r.data["results"]), ["QD 12 · LT 05", "QD 12 · LT 06"])
        r = self.client.get("/api/clientes/carteira/", {"visao": "unidades", "busca": "demo 10 qd 3"})
        self.assertEqual([l["unidade"] for l in r.data["results"]], ["QD 3 · LT 01"])

    def test_busca_casa_pelo_comeco_da_palavra(self):
        """"Ro" acha Rocha, não Ribei-ro (mesma régua do listão, D242)."""
        self.ana.nome_completo = "Ana Ribeiro"
        self.ana.save()
        self.bruno.nome_completo = "Bruno Rocha"
        self.bruno.save()
        self.autenticar()
        for visao in ("clientes", "unidades"):
            r = self.client.get("/api/clientes/carteira/", {"visao": visao, "busca": "Ro"})
            self.assertEqual({l["nome"] for l in r.data["results"]}, {"Bruno Rocha"}, visao)
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes", "busca": "ribe"})
        self.assertEqual([l["nome"] for l in r.data["results"]], ["Ana Ribeiro"])

    def test_busca_por_unidade_na_visao_clientes_nao_duplica(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "clientes", "busca": "QD 12"})
        self.assertEqual([l["nome"] for l in r.data["results"]], ["Ana Souza"])

    def test_filtro_por_empreendimento_na_visao_clientes_nao_duplica(self):
        """Ana comprou dois lotes no mesmo empreendimento — tem de vir UMA vez."""
        self.autenticar()
        r = self.client.get(
            "/api/clientes/carteira/", {"visao": "clientes", "empreendimento": self.emp.pk}
        )
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(len(r.data["results"]), 1)

    def test_paginacao_nao_devolve_a_carteira_inteira(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/", {"visao": "unidades", "page_size": 10, "page": 1})
        self.assertEqual(len(r.data["results"]), 3)
        self.assertFalse(r.data["temMais"])


class CarteiraGruposTests(CarteiraBaseTestCase):

    def test_agrupa_por_empreendimento_com_contagem_e_subtotal(self):
        self.autenticar()
        r = self.client.get(
            "/api/clientes/carteira/grupos/", {"visao": "unidades", "por": "empreendimento"}
        )
        self.assertEqual(r.status_code, 200)
        grupos = {g["rotulos"][0]: g for g in r.data["grupos"]}
        self.assertEqual(grupos["Residencial Alfa"]["contagem"], 2)
        self.assertEqual(grupos["Residencial Beta"]["contagem"], 1)
        self.assertEqual(Decimal(grupos["Residencial Alfa"]["valorVenda"]), Decimal("380000.00"))
        self.assertEqual(Decimal(grupos["Residencial Alfa"]["valorAtraso"]), Decimal("1500.00"))

    def test_agrupa_em_dois_niveis(self):
        self.autenticar()
        r = self.client.get(
            "/api/clientes/carteira/grupos/", {"visao": "unidades", "por": "empreendimento,quadra"}
        )
        combinacoes = {tuple(g["rotulos"]) for g in r.data["grupos"]}
        self.assertIn(("Residencial Alfa", "12"), combinacoes)
        self.assertIn(("Residencial Beta", "3"), combinacoes)

    def test_grupos_em_ordem_de_leitura(self):
        """Quadra 3 antes da 12 (era texto: "12" < "3"); empreendimento pelo nome."""
        self.emp.empreendimento = "Zeta"
        self.emp.save()
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/grupos/", {"visao": "unidades", "por": "quadra"})
        self.assertEqual([g["chaves"][0] for g in r.data["grupos"]], ["3", "12"])
        r = self.client.get("/api/clientes/carteira/grupos/", {"visao": "unidades", "por": "empreendimento"})
        self.assertEqual([g["rotulos"][0] for g in r.data["grupos"]], ["Residencial Beta", "Zeta"])
        r = self.client.get("/api/clientes/carteira/grupos/", {"visao": "unidades", "por": "faixa"})
        self.assertEqual([g["chaves"][0] for g in r.data["grupos"]], ["em_dia", "d31_60"])

    def test_agrupa_por_faixa_de_atraso(self):
        self.autenticar()
        r = self.client.get("/api/clientes/carteira/grupos/", {"visao": "unidades", "por": "faixa"})
        grupos = {g["chaves"][0]: g["contagem"] for g in r.data["grupos"]}
        self.assertEqual(grupos["d31_60"], 1)
        self.assertEqual(grupos["em_dia"], 2)

    def test_clientes_por_empreendimento_conta_pessoas_distintas(self):
        self.autenticar()
        r = self.client.get(
            "/api/clientes/carteira/grupos/", {"visao": "clientes", "por": "empreendimento"}
        )
        grupos = {g["rotulos"][0]: g["contagem"] for g in r.data["grupos"]}
        self.assertEqual(grupos["Residencial Alfa"], 1)  # Ana, com dois lotes, conta uma vez

    def test_subtotais_somem_sem_permissao_financeira(self):
        self.autenticar(permissoes=["cadastro.cliente.view"])
        r = self.client.get(
            "/api/clientes/carteira/grupos/", {"visao": "unidades", "por": "empreendimento"}
        )
        self.assertNotIn("valorAberto", r.data["grupos"][0])
        self.assertIn("contagem", r.data["grupos"][0])

    def test_subtotal_do_grupo_cobre_a_carteira_e_nao_a_pagina(self):
        """Com página de 1 linha, o subtotal do grupo continua sendo o total real."""
        self.autenticar()
        r = self.client.get(
            "/api/clientes/carteira/grupos/",
            {"visao": "unidades", "por": "empreendimento", "page_size": 1},
        )
        grupos = {g["rotulos"][0]: g["contagem"] for g in r.data["grupos"]}
        self.assertEqual(grupos["Residencial Alfa"], 2)


class FichaClienteTests(CarteiraBaseTestCase):

    def test_extrato_lista_parcelas_com_a_unidade_de_cada_uma(self):
        self.autenticar()
        r = self.client.get(f"/api/clientes/{self.ana.pk}/financeiro/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["resumo"]["parcelasAtraso"], 1)
        self.assertEqual(Decimal(r.data["resumo"]["valorAberto"]), Decimal("2400.00"))
        unidades = {p["unidade"] for p in r.data["parcelas"]}
        self.assertEqual(unidades, {"QD 12 · LT 05", "QD 12 · LT 06"})

    def test_aba_obra_traz_o_andamento_do_empreendimento_comprado(self):
        obra = Obra.objects.create(
            tenant=self.tenant, empreendimento=self.emp, nome_obra="Infraestrutura Alfa",
            status_obra="em_execucao",
        )
        EtapaObra.objects.create(
            tenant=self.tenant, obra=obra, nome_etapa="Terraplenagem", ordem=1,
            percentual_conclusao=Decimal("100.00"), status_etapa="concluida",
        )
        EtapaObra.objects.create(
            tenant=self.tenant, obra=obra, nome_etapa="Drenagem", ordem=2,
            percentual_conclusao=Decimal("40.00"), status_etapa="em_execucao",
        )
        self.autenticar()
        r = self.client.get(f"/api/clientes/{self.ana.pk}/obra/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["obras"]), 1)
        self.assertEqual(r.data["obras"][0]["percentual"], 70.0)
        self.assertEqual(r.data["obras"][0]["etapasTotal"], 2)

    def test_obra_sem_etapa_nao_inventa_zero(self):
        Obra.objects.create(
            tenant=self.tenant, empreendimento=self.emp, nome_obra="Obra sem etapas",
            status_obra="planejamento",
        )
        self.autenticar()
        r = self.client.get(f"/api/clientes/{self.ana.pk}/obra/")
        obra = next(o for o in r.data["obras"] if o["nome"] == "Obra sem etapas")
        self.assertIsNone(obra["percentual"])


class RotuloUnidadeTests(CarteiraBaseTestCase):
    """O rótulo é da unidade — a venda só o repete."""

    def test_monta_rotulo_de_loteamento(self):
        self.assertEqual(self.un_lote5.rotulo, "QD 12 · LT 05")

    def test_monta_rotulo_vertical(self):
        vertical = Unidade.objects.create(
            tenant=self.tenant, empreendimento=self.emp2,
            bloco_torre="Torre A", andar="3", apto="302",
            valor_base=Decimal("450000.00"), endereco="Av. Central, 900",
        )
        self.assertEqual(vertical.rotulo, "Torre A · 3º · 302")

    def test_aquisicao_le_o_rotulo_da_unidade(self):
        self.assertEqual(self.ana_lote5.rotulo_unidade, self.un_lote5.rotulo)
