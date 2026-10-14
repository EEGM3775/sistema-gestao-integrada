# testes/backend/funcoesimpexp/test_cadastros.py
"""Os cadastros entrando e saindo pelo motor (14/10/2026).

A régua do dono, nas palavras dele: *"caso haja qualquer coisa estranha em uma
planilha, não importa nada e mostra o que houve"* — e importar **só cria**;
editar é pela tela. Estes testes usam as declarações REAIS (cliente, fornecedor,
funcionário, obra, entidade) sobre o `RecursoDeCadastro`, porque o que está sob
teste é justamente a validação de cada cadastro chegando ao motor.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from clientes.models import Cliente
from empreendimentos.models import Empreendimento
from entidades.models import ConcessaoEntidade, Entidade
from fornecedores.models import Fornecedor
from nucleo.documentos import gerar_cnpj, gerar_cpf
from nucleo.models import Tenant, Usuario
from obras.models import Obra
from rh.models import Cargo, Funcionario

from funcoesimpexp import importacao as motor
from funcoesimpexp.models import Importacao, LinhaImportacao
from funcoesimpexp.registro import obter

NOVA = LinhaImportacao.Situacao.NOVA
DUPLICADA = LinhaImportacao.Situacao.DUPLICADA
INVALIDA = LinhaImportacao.Situacao.INVALIDA


def _csv(linhas: list[str]) -> bytes:
    return "\n".join(linhas).encode("utf-8")


def _formatar_cpf(cpf: str) -> str:
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


class CadastroTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="cad-a", nome="Construtora A")
        cls.user = Usuario.objects.create(username="cad_op", tenant=cls.tenant)

    def recurso(self, recurso_id, **contexto):
        return obter(recurso_id).com_contexto({**contexto, "tenant_id": str(self.tenant.id)})

    def preparar(self, recurso_id, linhas, *, limites=None, **contexto):
        return motor.preparar(
            recurso=self.recurso(recurso_id, **contexto), conteudo=_csv(linhas),
            nome_arquivo="cadastro.csv", tenant_id=self.tenant.id,
            usuario_nome="op", limites=limites,
        )

    def situacoes(self, lote):
        return [(l.situacao, l.motivo) for l in lote.linhas.order_by("numero")]


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------

CAB_CLIENTE = "CPF/CNPJ;Nome completo;E-mail;Data de nascimento;Estado civil;UF"


class ClienteTests(CadastroTestBase):
    def test_cria_com_cpf_formatado_data_brasileira_e_escolha_pelo_rotulo(self):
        cpf = gerar_cpf(1)
        lote = self.preparar("cadastro.cliente", [
            CAB_CLIENTE, f"{_formatar_cpf(cpf)};Maria da Silva;maria@x.com;15/03/1985;Casado(a);ba",
        ])
        self.assertEqual(self.situacoes(lote), [(NOVA, "")])
        motor.aplicar(lote, recurso=self.recurso("cadastro.cliente"))

        maria = Cliente.objects.get(tenant=self.tenant)
        self.assertEqual(maria.cpf_cnpj, cpf, "grava só os dígitos, como a ficha")
        self.assertEqual(maria.data_nascimento, date(1985, 3, 15))
        self.assertEqual(maria.estado_civil, "casado", "o rótulo exportado volta como código")
        self.assertEqual(maria.estado, "BA")

    def test_cpf_ja_cadastrado_trava_mesmo_com_outra_formatacao(self):
        cpf = gerar_cpf(2)
        Cliente.objects.create(
            tenant=self.tenant, nome_completo="Já existe", cpf_cnpj=cpf,
            email="ja@x.com", data_nascimento=date(1980, 1, 1),
        )
        lote = self.preparar("cadastro.cliente", [
            CAB_CLIENTE, f"{_formatar_cpf(cpf)};Outro nome;outro@x.com;01/01/1990;;",
        ])
        self.assertEqual(lote.linhas.get().situacao, DUPLICADA)
        with self.assertRaises(motor.ImportacaoInvalida):
            motor.aplicar(lote, recurso=self.recurso("cadastro.cliente"))
        self.assertEqual(Cliente.objects.get(cpf_cnpj=cpf).nome_completo, "Já existe")

    def test_cpf_com_digito_errado_e_invalido(self):
        lote = self.preparar("cadastro.cliente", [
            CAB_CLIENTE, "111.222.333-00;Fulano;f@x.com;01/01/1990;;",
        ])
        situacao, motivo = self.situacoes(lote)[0]
        self.assertEqual(situacao, INVALIDA)
        self.assertIn("não é válido", motivo)

    def test_data_que_nao_existe_e_invalida_e_nao_vira_vazio(self):
        lote = self.preparar("cadastro.cliente", [
            CAB_CLIENTE, f"{gerar_cpf(3)};Fulano;f@x.com;31/02/1990;;",
        ])
        situacao, motivo = self.situacoes(lote)[0]
        self.assertEqual(situacao, INVALIDA)
        self.assertIn("não é uma data", motivo)

    def test_email_de_outro_cliente_e_invalido_com_frase_legivel(self):
        Cliente.objects.create(
            tenant=self.tenant, nome_completo="Dono do e-mail", cpf_cnpj=gerar_cpf(4),
            email="usado@x.com", data_nascimento=date(1980, 1, 1),
        )
        lote = self.preparar("cadastro.cliente", [
            CAB_CLIENTE, f"{gerar_cpf(5)};Outro;usado@x.com;01/01/1990;;",
        ])
        situacao, motivo = self.situacoes(lote)[0]
        self.assertEqual(situacao, INVALIDA)
        self.assertIn("Já existe outro cadastro com este E-mail", motivo)

    def test_escolha_fora_da_lista_e_invalida(self):
        lote = self.preparar("cadastro.cliente", [
            CAB_CLIENTE, f"{gerar_cpf(6)};Fulano;f6@x.com;01/01/1990;Enrolado;",
        ])
        situacao, motivo = self.situacoes(lote)[0]
        self.assertEqual(situacao, INVALIDA)
        self.assertIn("Estado civil", motivo)

    def test_uma_linha_ruim_trava_as_boas(self):
        lote = self.preparar("cadastro.cliente", [
            CAB_CLIENTE,
            f"{gerar_cpf(7)};Boa;boa@x.com;01/01/1990;;",
            f"{gerar_cpf(8)};Sem e-mail;;01/01/1990;;",
        ])
        with self.assertRaises(motor.ImportacaoInvalida):
            motor.aplicar(lote, recurso=self.recurso("cadastro.cliente"))
        self.assertFalse(Cliente.objects.filter(tenant=self.tenant).exists())

    def test_quota_do_plano_barra_antes_de_materializar(self):
        Cliente.objects.create(
            tenant=self.tenant, nome_completo="Único", cpf_cnpj=gerar_cpf(9),
            email="u@x.com", data_nascimento=date(1980, 1, 1),
        )
        with self.assertRaises(motor.LimiteDoPlano) as caso:
            self.preparar("cadastro.cliente", [
                CAB_CLIENTE, f"{gerar_cpf(10)};Novo;n@x.com;01/01/1990;;",
            ], limites={"clientes": 1})
        self.assertEqual(caso.exception.quota, "clientes")
        self.assertEqual(Importacao.objects.count(), 0)


# ---------------------------------------------------------------------------
# Fornecedor — desfazer
# ---------------------------------------------------------------------------


class FornecedorTests(CadastroTestBase):
    def test_cria_com_documento_so_digitos_e_desfazer_apaga(self):
        cnpj = gerar_cnpj(1)
        lote = self.preparar("cadastro.fornecedor", [
            "Razão social;CNPJ;E-mail",
            f"Concreto Forte;{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]};c@x.com",
        ])
        motor.aplicar(lote, recurso=self.recurso("cadastro.fornecedor"))
        self.assertEqual(Fornecedor.objects.get(tenant=self.tenant).cnpj, cnpj)

        motor.desfazer(lote, recurso=self.recurso("cadastro.fornecedor"))
        self.assertFalse(Fornecedor.objects.filter(tenant=self.tenant).exists())

    def test_numero_que_nao_e_numero_trava(self):
        """R8 estrita: antes, "abc" numa coluna de valor virava zero em silêncio."""
        Empreendimento.objects.create(
            tenant=self.tenant, empreendimento="Aurora", razao_social="Aurora SPE",
            cnpj=gerar_cnpj(2), telefone="1", endereco="Rua",
        )
        lote = self.preparar("obra.obra", [
            "Obra;Empreendimento;Endereço;Orçamento previsto",
            "Torre A;Aurora;Rua 1;muito",
        ])
        situacao, motivo = self.situacoes(lote)[0]
        self.assertEqual(situacao, INVALIDA)
        self.assertIn("não é um número", motivo)


# ---------------------------------------------------------------------------
# Funcionário — referência por nome
# ---------------------------------------------------------------------------

CAB_FUNC = (
    "CPF;Nome completo;Data de nascimento;Gênero;Endereço;Cargo;"
    "Data de admissão;Salário base"
)


class FuncionarioTests(CadastroTestBase):
    def test_cargo_inexistente_trava_em_vez_de_entrar_vazio(self):
        lote = self.preparar("rh.funcionario", [
            CAB_FUNC, f"{gerar_cpf(20)};José;20/07/1990;Masculino;Rua A;Astronauta;02/01/2026;3.500,00",
        ])
        situacao, motivo = self.situacoes(lote)[0]
        self.assertEqual(situacao, INVALIDA)
        self.assertIn("Cargo “Astronauta” não existe", motivo)

    def test_cargo_existente_e_resolvido_pelo_nome(self):
        cargo = Cargo.objects.create(tenant=self.tenant, nome_cargo="Mestre de obras")
        lote = self.preparar("rh.funcionario", [
            CAB_FUNC,
            f"{gerar_cpf(21)};José;20/07/1990;Masculino;Rua A;mestre de obras;02/01/2026;3.500,00",
        ])
        motor.aplicar(lote, recurso=self.recurso("rh.funcionario"))
        jose = Funcionario.objects.get(tenant=self.tenant)
        self.assertEqual(jose.cargo, cargo)
        self.assertEqual(jose.salario_base, Decimal("3500.00"))
        self.assertEqual(jose.status_contrato, "ativo", "situação em branco é ativo, como na ficha")

    def test_salario_em_branco_nao_vira_zero(self):
        lote = self.preparar("rh.funcionario", [
            CAB_FUNC, f"{gerar_cpf(22)};José;20/07/1990;Masculino;Rua A;;02/01/2026;",
        ])
        situacao, motivo = self.situacoes(lote)[0]
        self.assertEqual(situacao, INVALIDA)
        self.assertIn("salário base", motivo)


# ---------------------------------------------------------------------------
# Obra — identidade composta
# ---------------------------------------------------------------------------


class ObraTests(CadastroTestBase):
    def test_mesmo_nome_em_outro_empreendimento_e_obra_nova(self):
        aurora = Empreendimento.objects.create(
            tenant=self.tenant, empreendimento="Aurora", razao_social="Aurora SPE",
            cnpj=gerar_cnpj(3), telefone="1", endereco="Rua",
        )
        Empreendimento.objects.create(
            tenant=self.tenant, empreendimento="Boreal", razao_social="Boreal SPE",
            cnpj=gerar_cnpj(4), telefone="1", endereco="Rua",
        )
        Obra.objects.create(tenant=self.tenant, nome_obra="Torre A", empreendimento=aurora, endereco="R")

        lote = self.preparar("obra.obra", [
            "Obra;Empreendimento;Endereço;Orçamento previsto",
            "Torre A;Boreal;Rua 1;",
            "Torre A;Aurora;Rua 1;",
        ])
        self.assertEqual([s for s, _ in self.situacoes(lote)], [NOVA, DUPLICADA])

    def test_orcamento_em_branco_fica_nulo(self):
        lote = self.preparar("obra.obra", ["Obra;Endereço;Orçamento previsto", "Galpão;Rua 2;"])
        motor.aplicar(lote, recurso=self.recurso("obra.obra"))
        self.assertIsNone(Obra.objects.get(tenant=self.tenant).orcamento_previsto)


# ---------------------------------------------------------------------------
# Entidade — quem importa ganha o acesso, como na tela
# ---------------------------------------------------------------------------


class EntidadeTests(CadastroTestBase):
    def test_quem_importa_ve_o_que_importou(self):
        recurso = obter("cadastro.entidade")
        contexto = recurso.validar_contexto({}, self.user, self.tenant.id)
        cnpj = gerar_cnpj(5)
        lote = motor.preparar(
            recurso=recurso.com_contexto({**contexto, "tenant_id": str(self.tenant.id)}),
            conteudo=_csv(["CPF/CNPJ;Razão social ou nome;Papel", f"{cnpj};Aurora SPE;SPE"]),
            nome_arquivo="e.csv", tenant_id=self.tenant.id,
        )
        motor.aplicar(lote, recurso=recurso.com_contexto(lote.contexto))
        nova = Entidade.objects.get(tenant=self.tenant, documento=cnpj)
        self.assertEqual(nova.papel, "spe")
        self.assertTrue(ConcessaoEntidade.objects.filter(usuario=self.user, entidade=nova).exists())

    def test_filial_sem_matriz_e_invalida(self):
        lote = self.preparar("cadastro.entidade", [
            "CPF/CNPJ;Razão social ou nome;Papel", f"{gerar_cnpj(6)};Filial Sul;Filial",
        ])
        situacao, motivo = self.situacoes(lote)[0]
        self.assertEqual(situacao, INVALIDA)
        self.assertIn("matriz", motivo.lower())


# ---------------------------------------------------------------------------
# Exportação — o recorte da tela (R7) e o gate das máscaras (§3)
# ---------------------------------------------------------------------------


class ExportacaoDeCadastroTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="cad-api", nome="Construtora API")
        self.user = Usuario.objects.create(username="cad_api", tenant=self.tenant)
        for i, nome in enumerate(("Maria Souza", "João Lima")):
            Fornecedor.objects.create(
                tenant=self.tenant, razao_social=nome, email=f"f{i}@x.com",
            )

    def autenticar(self, perms):
        self.user.iam_permissions = list(perms)
        self.user.iam_quotas = None
        self.client.force_authenticate(user=self.user)

    def test_exporta_so_o_que_a_busca_da_tela_mostra(self):
        self.autenticar(("cadastro.fornecedor.view", "cadastro.fornecedor.edit"))
        resposta = self.client.get(
            "/api/impexp/cadastro.fornecedor/exportar/", {"formato": "csv", "search": "maria"},
        )
        self.assertEqual(resposta.status_code, 200, getattr(resposta, "data", ""))
        texto = b"".join(resposta.streaming_content if resposta.streaming else [resposta.content])
        texto = texto.decode("utf-8-sig")
        self.assertIn("Maria Souza", texto)
        self.assertNotIn("João Lima", texto)

    def test_cliente_sem_a_permissao_do_documento_nao_ve_o_recurso(self):
        """O CPF vai no arquivo: sem `cliente_doc.view` a coluna sairia mascarada."""
        self.autenticar(("cadastro.cliente.view", "cadastro.cliente.edit"))
        ids = [r["id"] for r in self.client.get("/api/impexp/recursos/").data["recursos"]]
        self.assertNotIn("cadastro.cliente", ids)
        self.autenticar((
            "cadastro.cliente.view", "cadastro.cliente.edit", "cadastro.cliente_doc.view",
        ))
        ids = [r["id"] for r in self.client.get("/api/impexp/recursos/").data["recursos"]]
        self.assertIn("cadastro.cliente", ids)
