# testes/backend/funcoesimpexp/test_erp.py
"""O financeiro pelo motor (15/10/2026).

Contas a pagar e a receber importam — nascem em aberto, com a entidade da regra
e dentro do alcance de quem importa; baixa e situação só saem. Boleto, NFS-e e
os relatórios (DRE, intercompany, financeiro por obra) só exportam, e saem pela
view da própria tela.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from clientes.models import Cliente
from empreendimentos.models import Empreendimento
from entidades import escopo, regras
from entidades.models import ConcessaoEntidade, Entidade
from fornecedores.models import Fornecedor
from moduloerp.models import ContaPagar, ContaReceber
from nucleo.models import Tenant, Usuario
from nucleo.tenancy import rls_bypass
from obras.models import Obra

from funcoesimpexp import importacao as motor
from funcoesimpexp.models import LinhaImportacao
from funcoesimpexp.registro import obter

NOVA = LinhaImportacao.Situacao.NOVA
INVALIDA = LinhaImportacao.Situacao.INVALIDA
PERMISSOES = [
    "erp.conta_pagar.view", "erp.conta_pagar.edit", "erp.conta_receber.view", "erp.conta_receber.edit",
    "erp.relatorio.view", "erp.cobranca.view", "erp.nf.view",
]
CAB = "Fornecedor;Descrição;Valor;Vencimento;Empreendimento;Obra;Situação (só sai)"


def _csv(linhas: list[str]) -> bytes:
    return "\n".join(linhas).encode("utf-8")


class ErpImpexpBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        with rls_bypass():
            cls.tenant = Tenant.objects.create(slug="erp-imp", nome="Grupo ERP")
            cls.user = Usuario.objects.create(username="fin_imp", tenant=cls.tenant)
            cls.fornecedor = Fornecedor.objects.create(
                tenant=cls.tenant, razao_social="Pedreira Sul", email="p@x.com",
            )
            cls.cliente = Cliente.objects.create(
                tenant=cls.tenant, nome_completo="Comprador Um", cpf_cnpj="52998224725",
                email="c@x.com", data_nascimento=date(1980, 1, 1),
            )

    def setUp(self):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = list(PERMISSOES)
        self.user.iam_quotas = None
        escopo.esquecer(self.user)
        self.client.force_authenticate(user=self.user)

    def recurso(self, recurso_id):
        recurso = obter(recurso_id)
        contexto = recurso.validar_contexto({}, self.user, self.tenant.id)
        return recurso.com_contexto({**contexto, "tenant_id": str(self.tenant.id)})

    def preparar(self, recurso_id, linhas):
        with rls_bypass():
            return motor.preparar(
                recurso=self.recurso(recurso_id), conteudo=_csv(linhas),
                nome_arquivo="erp.csv", tenant_id=self.tenant.id, usuario_nome="op",
            )

    def aplicar(self, recurso_id, lote):
        with rls_bypass():
            motor.aplicar(lote, recurso=obter(recurso_id).com_contexto(lote.contexto))

    def situacoes(self, lote):
        return [(l.situacao, l.motivo) for l in lote.linhas.order_by("numero")]

    def texto(self, resposta):
        corpo = b"".join(resposta.streaming_content if resposta.streaming else [resposta.content])
        return corpo.decode("utf-8-sig")


class ContasAPagarTests(ErpImpexpBase):
    def test_nasce_em_aberto_com_a_entidade_da_regra_e_situacao_do_arquivo_e_ignorada(self):
        lote = self.preparar("erp.conta_pagar", [CAB, "Pedreira Sul;Brita 1;1.500,00;30/11/2026;;;Quitado"])
        self.assertEqual(self.situacoes(lote), [(NOVA, "")])
        self.aplicar("erp.conta_pagar", lote)
        with rls_bypass():
            conta = ContaPagar.objects.get(tenant=self.tenant)
            matriz = regras.matriz(self.tenant.pk)
        self.assertEqual((conta.status, conta.valor_pago, conta.valor), ("ABERTO", Decimal("0"), Decimal("1500.00")))
        self.assertEqual(conta.entidade_id, matriz.pk)

    def test_mesmo_titulo_ja_lancado_trava(self):
        with rls_bypass():
            ContaPagar.objects.create(tenant=self.tenant, fornecedor=self.fornecedor, descricao="Brita 1",
                                      valor=Decimal("1500"), data_vencimento=date(2026, 11, 30))
        lote = self.preparar("erp.conta_pagar", [CAB, "Pedreira Sul;brita 1;1500;30/11/2026;;;"])
        with self.assertRaises(motor.ImportacaoInvalida):
            self.aplicar("erp.conta_pagar", lote)

    def test_obra_e_achada_dentro_do_empreendimento(self):
        with rls_bypass():
            aurora = Empreendimento.objects.create(tenant=self.tenant, empreendimento="Aurora", razao_social="Aurora SA", cnpj="11")
            sol = Empreendimento.objects.create(tenant=self.tenant, empreendimento="Sol", razao_social="Sol SA", cnpj="22")
            torre_aurora = Obra.objects.create(tenant=self.tenant, nome_obra="Torre A", empreendimento=aurora,
                                               endereco="x")
            Obra.objects.create(tenant=self.tenant, nome_obra="Torre A", empreendimento=sol, endereco="y")
        lote = self.preparar("erp.conta_pagar", [
            CAB, "Pedreira Sul;Brita;100;30/11/2026;Aurora;Torre A;",
            "Pedreira Sul;Areia;100;30/11/2026;;Torre A;",
        ])
        (s1, _), (s2, m2) = self.situacoes(lote)
        self.assertEqual((s1, s2), (NOVA, INVALIDA))
        self.assertIn("Torre A", m2)
        with self.assertRaises(motor.ImportacaoInvalida):  # tudo ou nada
            self.aplicar("erp.conta_pagar", lote)
        lote = self.preparar("erp.conta_pagar", [CAB, "Pedreira Sul;Brita;100;30/11/2026;Aurora;Torre A;"])
        self.aplicar("erp.conta_pagar", lote)
        with rls_bypass():
            self.assertEqual(ContaPagar.objects.get(tenant=self.tenant).obra, torre_aurora)

    def test_entidade_fora_do_alcance_trava(self):
        with rls_bypass():
            matriz = regras.matriz(self.tenant.pk)
            spe = Entidade.objects.create(tenant=self.tenant, nome="SPE B", papel="spe", documento="11444777000161")
            ConcessaoEntidade.objects.create(tenant=self.tenant, usuario=self.user, entidade=matriz)
        escopo.esquecer(self.user)
        lote = self.preparar("erp.conta_pagar", [
            "Fornecedor;Descrição;Valor;Vencimento;Entidade (CNPJ do grupo)",
            f"Pedreira Sul;Brita;100;30/11/2026;{spe.nome}",
        ])
        situacao, motivo = self.situacoes(lote)[0]
        self.assertEqual(situacao, INVALIDA)
        self.assertIn("acesso", motivo)

    def test_valor_zero_e_vencimento_antes_da_emissao_travam(self):
        lote = self.preparar("erp.conta_pagar", [
            "Fornecedor;Descrição;Valor;Emissão;Vencimento",
            "Pedreira Sul;A;0;01/11/2026;30/11/2026",
            "Pedreira Sul;B;10;01/12/2026;30/11/2026",
        ])
        self.assertEqual([s for s, _ in self.situacoes(lote)], [INVALIDA, INVALIDA])


class ContasAReceberTests(ErpImpexpBase):
    def test_cria_pelo_nome_do_cliente_e_desfazer_apaga(self):
        lote = self.preparar("erp.conta_receber", [
            "Cliente;Descrição;Valor;Vencimento", "Comprador Um;Sinal;5.000,00;10/12/2026",
        ])
        self.assertEqual(self.situacoes(lote), [(NOVA, "")])
        self.aplicar("erp.conta_receber", lote)
        with rls_bypass():
            self.assertEqual(ContaReceber.objects.get(tenant=self.tenant).cliente, self.cliente)
            motor.desfazer(lote, recurso=obter("erp.conta_receber").com_contexto(lote.contexto))
            self.assertFalse(ContaReceber.objects.filter(tenant=self.tenant).exists())


class ExportacaoDoErpTests(ErpImpexpBase):
    def test_contas_a_pagar_saem_com_a_busca_da_tela(self):
        with rls_bypass():
            outro = Fornecedor.objects.create(tenant=self.tenant, razao_social="Aço Norte", email="a@x.com")
            for forn, desc in ((self.fornecedor, "Brita"), (outro, "Vergalhão")):
                ContaPagar.objects.create(tenant=self.tenant, fornecedor=forn, descricao=desc,
                                          valor=Decimal("10"), data_vencimento=date(2026, 11, 30))
        resposta = self.client.get("/api/impexp/erp.conta_pagar/exportar/", {"formato": "csv", "search": "pedreira"})
        self.assertEqual(resposta.status_code, 200, getattr(resposta, "data", ""))
        texto = self.texto(resposta)
        self.assertIn("Brita", texto)
        self.assertNotIn("Vergalhão", texto)

    def test_documentos_e_relatorios_so_exportam(self):
        recursos = {r["id"]: r for r in self.client.get("/api/impexp/recursos/").data["recursos"]}
        for rid in ("erp.boleto", "erp.nfse", "erp.dre_entidades", "erp.financeiro_obras", "erp.intercompany"):
            self.assertTrue(recursos[rid]["exporta"], rid)
            self.assertFalse(recursos[rid]["importa"], rid)
        self.assertTrue(recursos["erp.conta_pagar"]["importa"])
        for rid in ("erp.dre_entidades", "erp.financeiro_obras", "erp.intercompany", "erp.boleto"):
            resposta = self.client.get(f"/api/impexp/{rid}/exportar/", {"formato": "csv"})
            self.assertEqual(resposta.status_code, 200, (rid, getattr(resposta, "data", "")))
        self.assertIn("Consolidado", self.texto(
            self.client.get("/api/impexp/erp.dre_entidades/exportar/", {"formato": "csv"})))
