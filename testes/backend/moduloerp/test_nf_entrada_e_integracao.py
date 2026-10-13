"""Achados do dono de 10/10/2026 no ERP.

- "Como vou cadastrar minha API?" — a conta da NFE.io é **por empresa**, a chave
  vai cifrada e nunca volta para a tela, e o cliente da emissão a usa.
- "Como adiciono minhas NF-e sem API?" — o XML da NF-e entra pela porta única
  (DMS): a conferência mostra o que o XML diz, aplicar grava a nota de entrada
  e uma conta a pagar por duplicata, e desfazer leva tudo.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APITestCase

from empreendimentos.models import Empreendimento
from fornecedores.models import Fornecedor
from funcoesimpexp.limites import detectar_formato
from funcoesimpexp.registro import CAMPO_ARQUIVO, ArquivoRecebido, obter
from nucleo.models import Tenant, Usuario
from nucleo.tenancy import rls_bypass
from moduloerp import nfe_client
from moduloerp.impexp import RECURSO_NOTA_ENTRADA
from moduloerp.models import ContaPagar, IntegracaoFiscal, NotaFiscal
from moduloerp.nfe_xml import XmlNaoEhNfe, ler_nfe

CHAVE = "35261011222333000181550010000012341000012345"

XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe xmlns="http://www.portalfiscal.inf.br/nfe">
    <infNFe Id="NFe{CHAVE}" versao="4.00">
      <ide><nNF>1234</nNF><serie>1</serie><dhEmi>2026-10-05T10:00:00-03:00</dhEmi></ide>
      <emit><CNPJ>11222333000181</CNPJ><xNome>Cimento Forte LTDA</xNome></emit>
      <total><ICMSTot><vNF>3000.00</vNF></ICMSTot></total>
      <cobr>
        <dup><nDup>001</nDup><dVenc>2026-11-05</dVenc><vDup>1500.00</vDup></dup>
        <dup><nDup>002</nDup><dVenc>2026-12-05</dVenc><vDup>1500.00</vDup></dup>
      </cobr>
    </infNFe>
  </NFe>
</nfeProc>""".encode()


class LerXmlTests(TestCase):
    def test_le_chave_emitente_valor_e_duplicatas(self):
        nota = ler_nfe(XML)
        self.assertEqual(nota["chave_acesso"], CHAVE)
        self.assertEqual(nota["numero"], "1234")
        self.assertEqual(nota["data_emissao"], date(2026, 10, 5))
        self.assertEqual(nota["emitente_cnpj"], "11222333000181")
        self.assertEqual(nota["valor_total"], Decimal("3000.00"))
        self.assertEqual([d["vencimento"] for d in nota["duplicatas"]], [date(2026, 11, 5), date(2026, 12, 5)])

    def test_xml_que_nao_e_nfe_e_recusado(self):
        with self.assertRaises(XmlNaoEhNfe):
            ler_nfe(b"<?xml version='1.0'?><CompNfse><Numero>1</Numero></CompNfse>")

    def test_a_porta_unica_reconhece_o_xml_da_nfe_pelo_conteudo(self):
        self.assertEqual(detectar_formato("qualquer-nome.txt", XML).codigo, "nfe_xml")


class ImportarNfeDeEntradaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="nf-entrada", nome="Construtora NF")
        cls.emp = Empreendimento.objects.create(
            tenant=cls.tenant, empreendimento="Residencial A", razao_social="Residencial A SA",
            cnpj="99888777000166", telefone="48999990000", endereco="Rua X, 1", cidade="Palhoça", estado="SC",
        )
        cls.fornecedor = Fornecedor.objects.create(
            tenant=cls.tenant, razao_social="Cimento Forte LTDA", cnpj="11.222.333/0001-81", email="c@f.com",
        )

    def _recurso(self):
        recurso = obter(RECURSO_NOTA_ENTRADA)
        contexto = recurso.validar_contexto({"empreendimento": self.emp.pk}, None, self.tenant.pk)
        return recurso.com_contexto(contexto)

    def _dados(self, recurso, conteudo=XML):
        recebido = ArquivoRecebido(nome="nfe.xml", caminho="nfe.xml", tamanho=len(conteudo), hash="h", formato="nfe_xml")
        dados = {**recurso.dados_do_arquivo(recebido), **recurso.dados_do_conteudo(recebido, BytesIO(conteudo))}
        return dados

    def test_conferencia_mostra_o_que_o_xml_diz_e_casa_o_fornecedor_pelo_cnpj(self):
        recurso = self._recurso()
        dados = self._dados(recurso)
        self.assertEqual(dados["chave_acesso"], CHAVE)
        self.assertEqual(dados["fornecedor"], "Cimento Forte LTDA")
        self.assertEqual(dados["parcelas"], 2)
        self.assertEqual(recurso.validar_linha(dados), "")

    def test_emitente_nao_cadastrado_e_linha_invalida_com_o_motivo(self):
        recurso = self._recurso()
        dados = self._dados(recurso, XML.replace(b"11222333000181", b"55666777000199"))
        self.assertIn("não está cadastrado", recurso.validar_linha(dados))

    def test_aplicar_grava_nota_e_contas_e_desfazer_leva_tudo(self):
        recurso = self._recurso()
        dados = self._dados(recurso)
        dados[CAMPO_ARQUIVO] = SimpleUploadedFile("nfe.xml", XML, content_type="text/xml")
        with rls_bypass():
            estado = recurso.aplicar_linha(dados, None, self.tenant.pk)
            nota = NotaFiscal.objects.get(pk=estado["nota"])
            self.assertEqual(nota.valor_total, Decimal("3000.00"))
            self.assertEqual(nota.fornecedor_id, self.fornecedor.pk)
            contas = ContaPagar.objects.filter(nota_fiscal=nota).order_by("data_vencimento")
            self.assertEqual([c.valor for c in contas], [Decimal("1500.00"), Decimal("1500.00")])
            self.assertEqual(recurso.localizar(dados, self.tenant.pk), nota)

            recurso.desfazer_linha(estado, self.tenant.pk)
            self.assertFalse(NotaFiscal.todos.filter(pk=nota.pk).exists())
            self.assertFalse(ContaPagar.todos.filter(pk__in=estado["contas"]).exists())


class IntegracaoFiscalTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="nfe-io", nome="Loteadora NFE")
        cls.user = Usuario.objects.create(username="fin_nfe", tenant=cls.tenant)

    def setUp(self):
        self.user.iam_modules = ["erp_financeiro"]
        self.user.iam_permissions = ["erp.nf.view", "erp.lote.configurar"]
        self.client.force_authenticate(user=self.user)

    def test_cadastrar_a_chave_cifra_e_nao_devolve(self):
        resp = self.client.put("/api/erp/configuracao/integracao-fiscal/", {
            "company_id": "empresa-123", "api_key": "chave-secreta-ABCD",
        }, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data["chave_final"], "ABCD")
        self.assertEqual(resp.data["origem"], "empresa")
        self.assertNotIn("chave-secreta", str(resp.data))
        with rls_bypass():
            cadastro = IntegracaoFiscal.objects.get(tenant=self.tenant)
        self.assertNotIn("chave-secreta", cadastro.api_key_cifrada)
        self.assertEqual(cadastro.api_key, "chave-secreta-ABCD")

        cliente = nfe_client.cliente_do_tenant(self.tenant.pk)
        self.assertEqual(cliente.api_key, "chave-secreta-ABCD")
        self.assertEqual(cliente.company_id, "empresa-123")

    def test_sem_permissao_de_configurar_nao_grava(self):
        self.user.iam_permissions = ["erp.nf.view"]
        resp = self.client.put("/api/erp/configuracao/integracao-fiscal/", {"company_id": "x"}, format="json")
        self.assertEqual(resp.status_code, 403)
