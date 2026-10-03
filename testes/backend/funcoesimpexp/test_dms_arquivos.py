"""DMS — o registro de todo arquivo, dentro e fora do sistema (`funcoesimpexp/arquivos.py`).

Duas coisas protegidas aqui. A primeira é estrutural, no molde do D70: **todo**
`FileField` com arquivo vindo do cliente aparece no registro — quem criar um
upload novo e esquecer o `guardados` vê este teste falhar com o nome do campo.
A segunda é o gate: o registro mostra só o que a pessoa poderia baixar, e o link
é o da entrega.
"""
from __future__ import annotations

from datetime import date

from django.apps import apps
from django.core.files.base import ContentFile
from django.db import models
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from clientes.models import Cliente, DocumentoCliente
from funcoesimpexp.models import Exportacao
from funcoesimpexp.registro import listar
from nucleo.models import Tenant, Usuario
from obras.models import DocumentoObra, Obra

#: Arquivos que **não** são do cliente: o motor os produz (derivada, snap,
#: snapshot do visualizador), são as próprias lentes de entrada e saída do DMS
#: (`Importacao`, `Exportacao`, `MapaColunas`) ou são da base-mãe sem tenant (o
#: ZIP oficial do ORC.8, que nenhuma porta serve — ver o teste do D70).
FORA_DO_REGISTRO = {
    "moduloprancheta.DerivadaProjeto.arquivo",
    "moduloprancheta.DerivadaProjeto.snap",
    "moduloprancheta.PontoDeVista.snapshot",
    "funcoesimpexp.Importacao.arquivo",
    "funcoesimpexp.Exportacao.arquivo",
    "funcoesimpexp.LinhaImportacao.arquivo",
    "moduloorcamento.CargaBase.arquivo",
}


class TodoArquivoDoClienteEstaNoRegistro(SimpleTestCase):
    def test_todo_file_field_tem_guardado(self):
        declarados = {
            f"{g.modelo._meta.label}.{g.campo}" for r in listar() for g in r.guardados
        }
        faltam = [
            f"{m._meta.label}.{c.name}"
            for m in apps.get_models() for c in m._meta.get_fields()
            if isinstance(c, models.FileField)
            and f"{m._meta.label}.{c.name}" not in declarados
            and f"{m._meta.label}.{c.name}" not in FORA_DO_REGISTRO
        ]
        self.assertFalse(
            faltam,
            "Arquivo sem lugar no DMS: declare um `Guardado` no recurso que o entrega "
            f"(o mesmo do `entregar_arquivo`) — {faltam}",
        )


class RegistroDeArquivosTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="dms-a", nome="Construtora DMS")
        cls.user = Usuario.objects.create(username="dms_a", tenant=cls.tenant)
        cls.obra = Obra.objects.create(tenant=cls.tenant, nome_obra="Edifício Aurora", endereco="Rua A, 1")
        cls.cliente = Cliente.objects.create(
            tenant=cls.tenant, nome_completo="Maria Conceição", cpf_cnpj="52998224725",
            email="m@x.com", data_nascimento=date(1985, 1, 1),
        )

    def setUp(self):
        self.doc_obra = DocumentoObra(tenant=self.tenant, obra=self.obra, nome_documento="Alvará de construção")
        self.doc_obra.arquivo.save("alvara.pdf", ContentFile(b"%PDF-1.4 alvara"), save=True)
        self.doc_cliente = DocumentoCliente(
            tenant=self.tenant, cliente=self.cliente, tipo_documento="rg", nome_documento="RG frente",
        )
        self.doc_cliente.arquivo.save("rg.pdf", ContentFile(b"%PDF-1.4 rg"), save=True)

    def _entrar(self, *permissoes):
        self.user.iam_modules = []
        self.user.iam_permissions = list(permissoes)
        self.client.force_authenticate(user=self.user)

    def test_lista_o_que_a_pessoa_pode_baixar_e_nada_alem(self):
        self._entrar("obra.obra.view")
        resp = self.client.get("/api/impexp/arquivos/")
        self.assertEqual(resp.status_code, 200, resp.content)
        nomes = [a["titulo"] for a in resp.data["arquivos"]]
        self.assertEqual(nomes, ["Alvará de construção"])
        linha = resp.data["arquivos"][0]
        self.assertEqual((linha["recurso"], linha["onde"]), ("obra.documento", "Edifício Aurora"))
        self.assertEqual(self.client.get(linha["link"]).status_code, 200)

    def test_quem_pode_os_dois_ve_os_dois_e_a_busca_ignora_acento(self):
        self._entrar("obra.obra.view", "cadastro.cliente.view")
        todos = self.client.get("/api/impexp/arquivos/").data
        self.assertEqual({a["recurso"] for a in todos["arquivos"]}, {"obra.documento", "cadastro.documento_cliente"})
        achados = self.client.get("/api/impexp/arquivos/", {"busca": "conceicao"}).data["arquivos"]
        self.assertEqual([a["titulo"] for a in achados], ["RG frente"])

    def test_outra_empresa_nao_aparece(self):
        outro = Tenant.objects.create(slug="dms-b", nome="Outra")
        obra_b = Obra.objects.create(tenant=outro, nome_obra="Alheia", endereco="X")
        alheio = DocumentoObra(tenant=outro, obra=obra_b, nome_documento="Contrato alheio")
        alheio.arquivo.save("c.pdf", ContentFile(b"%PDF-1.4 x"), save=True)
        self._entrar("obra.obra.view")
        titulos = [a["titulo"] for a in self.client.get("/api/impexp/arquivos/").data["arquivos"]]
        self.assertNotIn("Contrato alheio", titulos)

    def test_lente_dos_que_sairam(self):
        Exportacao.objects.create(tenant=self.tenant, recurso="obra.documento", formato="xlsx", linhas=3,
                                  usuario_nome="dms_a")
        self._entrar("obra.obra.view")
        self.client.get(self.client.get("/api/impexp/arquivos/").data["arquivos"][0]["link"])
        sairam = self.client.get("/api/impexp/arquivos/", {"lente": "sairam"}).data["sairam"]
        self.assertEqual({s["tipo"] for s in sairam}, {"exportacao", "entrega"})
        self.assertEqual(self.client.get("/api/impexp/arquivos/", {"lente": "entraram"}).status_code, 200)
        self.assertEqual(self.client.get("/api/impexp/arquivos/", {"lente": "outra"}).status_code, 400)
