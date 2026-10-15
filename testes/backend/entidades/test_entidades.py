"""Entidades — o dono jurídico de cada lançamento (docs/modulos/entidades.md).

O que estes testes protegem:
- a regra do §2: obra → a da obra; empreendimento do grupo → a dona; de terceiro
  ou sem nada → a matriz; e a conta nova ganha a matriz sozinha;
- o intercompany do §3: rateio para centro de custo de outra entidade e cota de
  co-dona geram o par no mesmo gesto, o par acompanha a origem, a baixa quita o
  espelho e o encontro de contas compensa os dois lados;
- a DRE do §6: a despesa rateada sai de quem pagou e entra em quem consumiu, e o
  consolidado não muda;
- o recorte do §4: quem só tem a entidade A não vê o financeiro da B; o
  administrador e o modo simples não têm recorte.
"""
from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from clientes.models import Cliente
from empreendimentos.models import Empreendimento
from entidades import escopo, regras
from entidades.models import ConcessaoEmpreendimento, ConcessaoEntidade, Entidade, ParticipacaoEmpreendimento
from fornecedores.models import Fornecedor
from moduloerp import dre_entidade, intercompany
from moduloerp.models import (
    CentroCusto, ContaPagar, ContaReceber, NaturezaIntercompany, ParIntercompany, RateioContaPagar,
    StatusConta, Transacao,
)
from nucleo.models import Tenant, Usuario
from nucleo.tenancy import rls_bypass
from obras.models import Obra

VENC = date(2026, 11, 10)
PERMISSOES = [
    "erp.conta_pagar.view", "erp.conta_pagar.edit", "erp.conta_pagar.baixar",
    "erp.conta_receber.view", "erp.conta_receber.edit", "erp.conta_receber.baixar",
    "erp.relatorio.view", "erp.cobranca.view", "erp.cobranca.emitir", "erp.centro_custo.view",
    "cadastro.entidade.view", "cadastro.entidade.edit",
]


class _Base(APITestCase):
    @classmethod
    def setUpTestData(cls):
        with rls_bypass():
            cls.tenant = Tenant.objects.create(slug="grupo-ent", nome="Grupo GM")
            cls.user = Usuario.objects.create(username="fin_ent", tenant=cls.tenant)
            cls.fornecedor = Fornecedor.objects.create(
                tenant=cls.tenant, razao_social="Pedreira Sul", cnpj="11222333000181", email="p@x.com",
            )
            cls.cliente = Cliente.objects.create(
                tenant=cls.tenant, nome_completo="Comprador Um", cpf_cnpj="52998224725", email="c@x.com",
                data_nascimento=date(1980, 1, 1),
            )

    def setUp(self):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = list(PERMISSOES)
        escopo.esquecer(self.user)
        self.client.force_authenticate(user=self.user)

    # ── ajudantes ──
    def entidade(self, nome, **extra):
        with rls_bypass():
            return Entidade.objects.create(tenant=self.tenant, nome=nome, **extra)

    def matriz(self):
        with rls_bypass():
            return regras.matriz(self.tenant.pk)

    def pagar(self, valor="1000", **extra):
        with rls_bypass():
            return ContaPagar.objects.create(
                tenant=self.tenant, fornecedor=self.fornecedor, descricao="Brita",
                valor=Decimal(valor), data_vencimento=VENC, **extra,
            )

    def empreendimento(self, nome, **extra):
        with rls_bypass():
            return Empreendimento.objects.create(
                tenant=self.tenant, empreendimento=nome, razao_social=f"{nome} SA",
                cnpj=extra.pop("cnpj", ""), telefone="48", endereco="Rua", **extra,
            )


class RegraDoDonoTests(_Base):
    def test_conta_nova_ganha_a_matriz_com_o_nome_do_tenant(self):
        m = self.matriz()
        self.assertEqual((m.nome, m.papel, m.externa), ("Grupo GM", "matriz", False))

    def test_titulo_sem_nada_e_da_matriz_e_a_transacao_herda(self):
        conta = self.pagar()
        self.assertEqual(conta.entidade_id, self.matriz().pk)
        with rls_bypass():
            conta.dar_baixa(valor=Decimal("1000"), data=VENC, meio_pagamento="PIX")
            self.assertEqual(Transacao.objects.get(conta_pagar=conta).entidade_id, self.matriz().pk)

    def test_empreendimento_com_spe_e_obra_dele_lancam_na_spe(self):
        spe = self.entidade("SPE Loteamento Sol", papel="spe")
        emp = self.empreendimento("Loteamento Sol", entidade_propria=spe)
        with rls_bypass():
            obra = Obra.objects.create(tenant=self.tenant, nome_obra="Infra Sol", endereco="x", empreendimento=emp)
        self.assertEqual(obra.entidade_id, spe.pk)
        self.assertEqual(self.pagar(empreendimento=emp).entidade_id, spe.pk)
        self.assertEqual(self.pagar(obra=obra).entidade_id, spe.pk)

    def test_empreendimento_de_terceiro_obra_e_titulos_ficam_com_quem_executa(self):
        """O caso da empreitada (Villa Privilege): o dono é de fora, quem executa e
        paga é a construtora."""
        valdick = self.entidade("Valdick", externa=True, papel="outra", documento="02702475000155")
        emp = self.empreendimento("Villa Privilege", entidade_propria=valdick)
        with rls_bypass():
            obra = Obra.objects.create(tenant=self.tenant, nome_obra="Pavimentação", endereco="x", empreendimento=emp)
        self.assertEqual(obra.entidade_id, self.matriz().pk)
        self.assertEqual(self.pagar(empreendimento=emp).entidade_id, self.matriz().pk)

    def test_api_recusa_titulo_em_entidade_externa(self):
        valdick = self.entidade("Valdick", externa=True, papel="outra")
        r = self.client.post("/api/erp/contas-a-pagar/", {
            "fornecedor": self.fornecedor.pk, "descricao": "x", "valor": "10.00",
            "data_vencimento": VENC.isoformat(), "entidade": valdick.pk,
        }, format="json")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("entidade", r.data)


class IntercompanyTests(_Base):
    def setUp(self):
        super().setUp()
        self.a = self.matriz()
        self.b = self.entidade("SPE B", papel="spe", documento="11444777000161")
        with rls_bypass():
            self.cc_b = CentroCusto.objects.create(tenant=self.tenant, nome="Obra B", entidade=self.b)
            for ent in (self.a, self.b):
                ConcessaoEntidade.objects.create(tenant=self.tenant, usuario=self.user, entidade=ent)

    def _rateio(self, conta, valor):
        with rls_bypass():
            RateioContaPagar.objects.create(tenant=self.tenant, conta_pagar=conta, centro_custo=self.cc_b, valor=Decimal(valor))
            return intercompany.sincronizar(conta)

    def test_rateio_para_outra_entidade_gera_o_par(self):
        conta = self.pagar("1000")
        self._rateio(conta, "400")
        with rls_bypass():
            par = ParIntercompany.objects.get(origem_pagar=conta)
            self.assertEqual(par.valor, Decimal("400.00"))
            self.assertEqual((par.titulo_receber.entidade_id, par.titulo_receber.contraparte_id), (self.a.pk, self.b.pk))
            self.assertEqual((par.titulo_pagar.entidade_id, par.titulo_pagar.contraparte_id), (self.b.pk, self.a.pk))
            self.assertEqual(par.titulo_pagar.natureza, NaturezaIntercompany.REPASSE_DESPESA)
            self.assertIsNone(par.titulo_pagar.fornecedor_id)

    def test_par_acompanha_a_origem_e_cancela_com_ela(self):
        conta = self.pagar("1000")
        self._rateio(conta, "400")
        with rls_bypass():
            conta.rateios.update(valor=Decimal("250"))
            intercompany.sincronizar(conta)
            par = ParIntercompany.objects.get(origem_pagar=conta)
            self.assertEqual(par.titulo_pagar.valor, Decimal("250.00"))
            conta.status = StatusConta.CANCELADO
            conta.save()   # o sinal de gravação sincroniza
            par.titulo_pagar.refresh_from_db()
            self.assertEqual(par.titulo_pagar.status, StatusConta.CANCELADO)

    def test_baixa_de_um_lado_quita_o_espelho(self):
        conta = self.pagar("1000")
        self._rateio(conta, "400")
        with rls_bypass():
            par = ParIntercompany.objects.get(origem_pagar=conta)
            par.titulo_pagar.dar_baixa(valor=Decimal("400"), data=VENC, meio_pagamento="TED")
            par.titulo_receber.refresh_from_db()
            self.assertEqual(par.titulo_receber.status, StatusConta.QUITADO)
            self.assertEqual(Transacao.objects.filter(entidade=self.a, conta_receber=par.titulo_receber).count(), 1)

    def test_cota_de_co_dona_sem_entidade_propria(self):
        emp = self.empreendimento("Condomínio Mar")
        with rls_bypass():
            ParticipacaoEmpreendimento.objects.create(tenant=self.tenant, empreendimento=emp, entidade=self.a, cota=Decimal("60"), administradora=True)
            ParticipacaoEmpreendimento.objects.create(tenant=self.tenant, empreendimento=emp, entidade=self.b, cota=Decimal("40"))
        conta = self.pagar("1000", empreendimento=emp)   # o sinal gera o par
        self.assertEqual(conta.entidade_id, self.a.pk)
        with rls_bypass():
            par = ParIntercompany.objects.get(origem_pagar=conta)
        self.assertEqual((par.contraparte_id, par.valor), (self.b.pk, Decimal("400.00")))

    def test_encontro_de_contas_compensa_os_dois_lados(self):
        self._rateio(self.pagar("1000"), "400")                    # B deve 400 a A
        with rls_bypass():
            cc_a = CentroCusto.objects.create(tenant=self.tenant, nome="Sede A", entidade=self.a)
            da_b = ContaPagar.objects.create(
                tenant=self.tenant, fornecedor=self.fornecedor, descricao="Cimento", valor=Decimal("300"),
                data_vencimento=VENC, entidade=self.b,
            )
            RateioContaPagar.objects.create(tenant=self.tenant, conta_pagar=da_b, centro_custo=cc_a, valor=Decimal("300"))
            intercompany.sincronizar(da_b)                          # A deve 300 a B
            resultado = intercompany.encontro_de_contas(self.tenant.pk, self.a.pk, self.b.pk, data=VENC, usuario=self.user)
            self.assertEqual(resultado["compensado"], "300.00")
            previa = intercompany.previa_encontro(self.tenant.pk, self.a.pk, self.b.pk)
            self.assertEqual((previa["a_recebe_de_b"], previa["b_recebe_de_a"]), ("100.00", "0.00"))

    def test_dre_tira_de_quem_pagou_e_poe_em_quem_consumiu(self):
        self._rateio(self.pagar("1000"), "400")
        with rls_bypass():
            dre = dre_entidade.dre(self.tenant.pk, [self.a, self.b])
        por = {e["entidade"]: e for e in dre["entidades"]}
        self.assertEqual(por[self.a.pk]["competencia"]["despesa"], "600.00")
        self.assertEqual(por[self.b.pk]["competencia"]["despesa"], "400.00")
        self.assertEqual(dre["consolidado"]["competencia"]["despesa"], "1000.00")

    def test_titulo_intercompany_nao_gera_boleto(self):
        conta = self.pagar("1000")
        self._rateio(conta, "400")
        with rls_bypass():
            receber = ParIntercompany.objects.get(origem_pagar=conta).titulo_receber
        r = self.client.post(f"/api/erp/contas-a-receber/{receber.pk}/gerar-cobranca/", {}, format="json")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "intercompany")

    def test_dre_por_cota_da_spe(self):
        """A sócia de 40% de uma SPE vê 40% do resultado dela."""
        emp = self.empreendimento("Loteamento Sol", entidade_propria=self.b)
        with rls_bypass():
            ParticipacaoEmpreendimento.objects.create(tenant=self.tenant, empreendimento=emp, entidade=self.a, cota=Decimal("40"))
            ContaReceber.objects.create(
                tenant=self.tenant, cliente=self.cliente, descricao="Lote 1", valor=Decimal("10000"),
                data_vencimento=VENC, empreendimento=emp,
            )
            dre = dre_entidade.dre(self.tenant.pk, [self.a])
        cota = dre["entidades"][0]["cotas"][0]
        self.assertEqual((cota["entidade"], cota["competencia"]), (self.b.pk, "4000.00"))
        self.assertEqual(dre["consolidado"]["resultado"]["competencia"], "4000.00")


class RecorteTests(_Base):
    def setUp(self):
        super().setUp()
        self.a = self.matriz()
        self.b = self.entidade("SPE B", papel="spe")
        self.conta_a = self.pagar("100")
        self.conta_b = self.pagar("200", entidade=self.b)

    def _ids(self):
        r = self.client.get("/api/erp/contas-a-pagar/")
        self.assertEqual(r.status_code, 200)
        return {c["conta_pagar_id"] for c in r.data["results"]}

    def test_sem_concessao_nao_ve_nada(self):
        self.assertEqual(self._ids(), set())

    def test_concessao_em_a_ve_so_a(self):
        with rls_bypass():
            ConcessaoEntidade.objects.create(tenant=self.tenant, usuario=self.user, entidade=self.a)
        self.assertEqual(self._ids(), {self.conta_a.pk})
        r = self.client.patch(f"/api/erp/contas-a-pagar/{self.conta_b.pk}/", {"descricao": "x"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_administradora_ve_a_spe_inteira(self):
        emp = self.empreendimento("Loteamento Sol", entidade_propria=self.b)
        with rls_bypass():
            ConcessaoEntidade.objects.create(tenant=self.tenant, usuario=self.user, entidade=self.a)
            ParticipacaoEmpreendimento.objects.create(
                tenant=self.tenant, empreendimento=emp, entidade=self.a, cota=Decimal("60"), administradora=True,
            )
        self.assertEqual(self._ids(), {self.conta_a.pk, self.conta_b.pk})

    def test_concessao_de_empreendimento_da_o_recorte_dele(self):
        emp = self.empreendimento("Loteamento Sol", entidade_propria=self.b)
        conta = self.pagar("300", empreendimento=emp)
        with rls_bypass():
            ConcessaoEmpreendimento.objects.create(tenant=self.tenant, usuario=self.user, empreendimento=emp)
        self.assertEqual(self._ids(), {conta.pk})

    def test_administrador_nao_tem_recorte(self):
        self.user.is_tenant_admin = True
        self.assertEqual(self._ids(), {self.conta_a.pk, self.conta_b.pk})

    def test_filtro_por_entidade(self):
        self.user.is_tenant_admin = True
        r = self.client.get(f"/api/erp/contas-a-pagar/?entidade={self.b.pk}")
        self.assertEqual({c["conta_pagar_id"] for c in r.data["results"]}, {self.conta_b.pk})


class ModoSimplesTests(_Base):
    def test_uma_entidade_so_nao_recorta(self):
        conta = self.pagar("100")
        r = self.client.get("/api/erp/contas-a-pagar/")
        self.assertEqual({c["conta_pagar_id"] for c in r.data["results"]}, {conta.pk})
        r = self.client.get("/api/entidades/contexto/")
        self.assertTrue(r.data["modo_simples"])

    def test_segunda_entidade_mantem_quem_ja_usava(self):
        conta = self.pagar("100")
        with rls_bypass():
            outro = Usuario.objects.create(username="obra_ent", tenant=self.tenant)
        r = self.client.post("/api/entidades/", {"nome": "SPE Nova", "papel": "spe"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["matriz_nome"], "")  # era "<method-wrapper '__str__' of NoneType…>"
        with rls_bypass():
            self.assertTrue(ConcessaoEntidade.objects.filter(usuario=outro, entidade=self.matriz()).exists())
        self.assertEqual({c["conta_pagar_id"] for c in self.client.get("/api/erp/contas-a-pagar/").data["results"]}, {conta.pk})

    def test_documento_valida_cpf_e_cnpj(self):
        r = self.client.post("/api/entidades/", {"nome": "X", "papel": "spe", "documento": "123"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/entidades/", {
            "nome": "Fulano", "papel": "pessoa_fisica", "tipo_pessoa": "PF", "documento": "529.982.247-25",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["documento"], "52998224725")
