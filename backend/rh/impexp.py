# backend/rh/impexp.py
"""D70 — os quatro arquivos do RH saindo pela porta única, e não por `/media/`.

**Por que o RH primeiro.** O levantamento de 09/08/2026 varreu todo `upload_to`
do backend e achou 13 prefixos sob `/media/`; quatro são daqui, e são os piores
do conjunto: `asos_funcionarios/` é **dado de saúde** (LGPD art. 11),
`holerites/` é remuneração, `carteiras_trabalho/` e `documentos_funcionarios/`
são RG, CPF, CNH e comprovante de residência de gente real. Nenhum desses
caminhos carrega tenant — então, servidos por `/media/`, nem o isolamento entre
clientes sobrevivia.

**E era um desvio do mascaramento, não só um buraco de gateway.** A 9.C esconde
o *valor* na ficha (`cpf` vira `•••123`, salário some sem `rh.folha.view`) e o
mesmo JSON entregava a URL do PDF que contém tudo aquilo em claro. Quem só tinha
`rh.funcionario.view` lia a ficha capada e baixava o ASO inteiro — a máscara
existia e o arquivo passava por baixo dela.

**São três recursos e não um, porque são três gates.** Um `Recurso` tem um
conjunto de permissões; pendurar o ASO no mesmo recurso do RG trocaria o gate do
prontuário médico em silêncio, e para mais gente. A segregação já existia no
catálogo (`rh.documento`, `rh.dado_medico`, `rh.folha`) e é a mesma razão pela
qual a Prancheta separou acervo de marcação.

**O que este arquivo NÃO faz:** a entrada. Subir o ASO continua sendo POST no
endpoint do RH, com o `UploadValidationMixin` por cima. Levar também a entrada
para a porta única é a R17 valendo para os módulos v01 — trabalho maior, com
migração de tela, e que não pode ser pré-requisito de fechar um vazamento de
leitura.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from funcoesimpexp.cadastro import RecursoDeCadastro
from funcoesimpexp.entrega import buscar_do_tenant, entregar_campo
from funcoesimpexp.registro import (
    NATUREZA_ARQUIVO,
    ArquivoEntregue,
    Coluna,
    EntregaInvalida,
    Guardado,
    Recurso,
    registrar,
)

from .models import ASOFuncionario, Cargo, DocumentoFuncionario, FolhaPagamento, Funcionario

#: Os três recursos do RH no registry. Constantes porque o serializer os cita
#: para montar a URL, e um erro de digitação daria 404 só naquele campo.
RECURSO_DOCUMENTOS = "rh.documentos"
RECURSO_ASO = "rh.aso"
RECURSO_HOLERITE = "rh.holerite"
RECURSO_CARGOS = "rh.cargo"
RECURSO_FUNCIONARIOS = "rh.funcionario"


# ---------------------------------------------------------------------------
# Os cadastros — entram e saem como planilha (14/10/2026)
# ---------------------------------------------------------------------------


@registrar(RECURSO_CARGOS)
class CadastroDeCargos(RecursoDeCadastro):
    """Os cargos. Importam-se **antes** dos funcionários, que apontam para eles."""

    rotulo = "Cargos"
    modulo = "rh"
    permissoes_exigidas = ("rh.cargo.view", "rh.cargo.edit")
    modelo = Cargo
    chave = "nome_cargo"
    ordem = ("nome_cargo",)
    campos_de_busca = ("nome_cargo", "departamento")
    busca_por_palavra = False  # a tela filtra no navegador, pela frase

    colunas = (
        Coluna("nome_cargo", "Cargo", obrigatoria=True, exemplo="Mestre de obras",
               aliases=("nome", "nome do cargo", "funcao", "função")),
        Coluna("departamento", "Departamento", exemplo="Engenharia", aliases=("setor",)),
        Coluna("descricao", "Descrição", exemplo="Coordena as equipes do canteiro"),
    )


@registrar(RECURSO_FUNCIONARIOS)
class CadastroDeFuncionarios(RecursoDeCadastro):
    """A ficha do funcionário — a admissão de turma é onde a carga em lote mais paga.

    **O gate soma as máscaras** (§3): a planilha traz CPF e salário, então quem
    exporta precisa de `rh.cpf.view` e `rh.folha.view`, e quem importa precisa de
    `rh.folha.edit` — a mesma trava que o serializer põe na escrita do salário.
    Os dados médicos, bancários e os documentos ficam fora do arquivo: são outros
    gates, e cada um tem a sua tela.
    """

    rotulo = "Funcionários"
    modulo = "rh"
    permissoes_exigidas = (
        "rh.funcionario.view", "rh.funcionario.create",
        "rh.cpf.view", "rh.folha.view", "rh.folha.edit",
    )
    modelo = Funcionario
    chave = "cpf"
    ordem = ("nome_completo",)
    campos_de_busca = ("nome_completo", "cpf")
    busca_por_palavra = False  # a tela filtra no navegador, pela frase
    filtros = {"status": "status_contrato", "status_contrato": "status_contrato", "cargo": "cargo"}
    nao_validar = ("usuario", "carteira_trabalho")

    @property
    def referencias(self) -> dict:
        from empreendimentos.models import Empreendimento

        return {
            "cargo": (Cargo, "nome_cargo"),
            "empreendimento_vinculado": (Empreendimento, "empreendimento"),
        }

    colunas = (
        Coluna("cpf", "CPF", obrigatoria=True, exemplo="12345678909"),
        Coluna("nome_completo", "Nome completo", obrigatoria=True, exemplo="José Pereira",
               aliases=("nome", "funcionario", "funcionário")),
        Coluna("data_nascimento", "Data de nascimento", tipo=date, obrigatoria=True,
               exemplo="20/07/1990", aliases=("nascimento",)),
        Coluna("genero", "Gênero", obrigatoria=True, exemplo="Masculino", aliases=("sexo",)),
        Coluna("estado_civil", "Estado civil", exemplo="Solteiro(a)"),
        Coluna("rg", "RG", exemplo="1234567"),
        Coluna("telefone_celular", "Celular (WhatsApp)", exemplo="+5571999990000",
               aliases=("celular", "whatsapp")),
        Coluna("telefone_pessoal", "Telefone", exemplo="(71) 3333-0000"),
        Coluna("email_pessoal", "E-mail", exemplo="jose@exemplo.com", aliases=("email",)),
        Coluna("endereco_completo", "Endereço", obrigatoria=True,
               exemplo="Rua A, 10 — Salvador/BA", aliases=("endereco",)),
        Coluna("cargo", "Cargo", exemplo="Mestre de obras"),
        Coluna("empreendimento_vinculado", "Empreendimento", exemplo="Residencial Aurora"),
        Coluna("data_admissao", "Data de admissão", tipo=date, obrigatoria=True,
               exemplo="02/01/2026", aliases=("admissao", "admissão")),
        Coluna("data_demissao", "Data de demissão", tipo=date, exemplo=""),
        Coluna("salario_base", "Salário base", tipo=Decimal, obrigatoria=True,
               exemplo="3.500,00", aliases=("salario", "salário")),
        Coluna("status_contrato", "Situação", exemplo="Ativo", aliases=("status",)),
        Coluna("pis_pasep", "PIS/PASEP", exemplo="12345678901", aliases=("pis",)),
        Coluna("numero_ctps", "CTPS (número)", exemplo="1234567"),
        Coluna("serie_ctps", "CTPS (série)", exemplo="0012"),
    )

    def normalizar_chave(self, valor) -> str:
        # A ficha grava o CPF só com dígitos (`FuncionarioForm`).
        return re.sub(r"\D", "", str(valor or ""))

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        # Situação em branco é "ativo", como na ficha — o `default` do model só
        # vale quando o campo não é passado, e aqui ele sempre é.
        saida["status_contrato"] = saida.get("status_contrato") or "ativo"
        return saida

    def validar_regras(self, objeto, dados, tenant_id) -> str:
        from nucleo.documentos import cpf_valido

        if not cpf_valido(objeto.cpf):
            return f"CPF “{dados.get('cpf')}” não é válido (confira os dígitos)."
        if objeto.salario_base is not None and objeto.salario_base < 0:
            return "Salário base negativo."
        if objeto.data_demissao and objeto.data_demissao < objeto.data_admissao:
            return "Data de demissão anterior à de admissão."
        return ""

#: Espécies — o vocabulário que o motor repassa inteiro ao gancho.
ESPECIE_DOCUMENTO = "documento"
ESPECIE_CTPS = "ctps"
ESPECIE_ASO = "aso"
ESPECIE_HOLERITE = "holerite"


# Os quatro saem com `RASTRO_AUDITADO` e `no-store`, que é o padrão de
# `entregar_campo` — e aqui o padrão é mais que suficiente: é PII de titular, em
# dois casos (ASO e holerite) da espécie que a LGPD trata à parte. Quem baixou o
# ASO de quem é exatamente a pergunta que a trilha existe para responder.


@registrar(RECURSO_DOCUMENTOS)
class DocumentosDoFuncionario(Recurso):
    """RG, CPF, CNH, comprovante, certificado — e a CTPS, que mora na ficha.

    **Duas espécies num recurso só porque o gate é um só.** O
    `DocumentoFuncionario` é a pasta do colaborador; a `carteira_trabalho` é um
    `FileField` na própria `Funcionario`, herdado do v01. São modelos diferentes
    e o mesmo `rh.documento.view` responde pelos dois — separá-los em dois
    recursos daria dois nomes para uma decisão de acesso só.
    """

    rotulo = "Documentos do funcionário"
    modulo = "rh"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("rh.documento.view", "rh.documento.edit")
    permissoes_entrega = ("rh.documento.view",)
    guardados = (
        Guardado(ESPECIE_DOCUMENTO, DocumentoFuncionario, "arquivo", quando="data_upload",
                 titulo="nome_documento", onde="funcionario__nome_completo"),
        Guardado(ESPECIE_CTPS, Funcionario, "carteira_trabalho", onde="nome_completo"),
    )

    colunas = (
        Coluna("funcionario", "Funcionário"),
        Coluna("tipo_documento", "Tipo de documento"),
        Coluna("nome_documento", "Nome do documento"),
        Coluna("arquivo", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie == ESPECIE_DOCUMENTO:
            doc = buscar_do_tenant(DocumentoFuncionario, chave, tenant_id)
            return entregar_campo(doc, doc.arquivo, alternativa="documento")
        if especie == ESPECIE_CTPS:
            funcionario = buscar_do_tenant(Funcionario, chave, tenant_id)
            return entregar_campo(
                funcionario, funcionario.carteira_trabalho, alternativa="ctps",
            )
        raise EntregaInvalida(f"Espécie '{especie}' não existe nos documentos do RH.")


@registrar(RECURSO_ASO)
class ASOsDoFuncionario(Recurso):
    """O atestado de saúde ocupacional — LGPD art. 11, gate próprio.

    `rh.dado_medico.view` é a mesma permissão que mascara o prontuário no
    `DadoMedicoFuncionarioSerializer`. Ter o arquivo atrás de um gate mais fraco
    que o do campo é o desvio que o D70 achou; aqui os dois voltam a ser o
    mesmo.
    """

    rotulo = "ASOs do funcionário"
    modulo = "rh"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("rh.dado_medico.view", "rh.dado_medico.edit")
    permissoes_entrega = ("rh.dado_medico.view",)
    guardados = (Guardado(ESPECIE_ASO, ASOFuncionario, "arquivo", quando="data_exame",
                          titulo="tipo_exame", onde="funcionario__nome_completo"),)

    colunas = (
        Coluna("funcionario", "Funcionário"),
        Coluna("tipo_exame", "Tipo de exame"),
        Coluna("data_exame", "Data do exame"),
        Coluna("arquivo", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie != ESPECIE_ASO:
            raise EntregaInvalida(f"Espécie '{especie}' não existe nos ASOs.")
        aso = buscar_do_tenant(ASOFuncionario, chave, tenant_id)
        return entregar_campo(aso, aso.arquivo, alternativa="aso")


@registrar(RECURSO_HOLERITE)
class HoleritesDaFolha(Recurso):
    """O contracheque — mesmo gate que já mascara os valores da folha."""

    rotulo = "Holerites da folha"
    modulo = "rh"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("rh.folha.view", "rh.folha.edit")
    permissoes_entrega = ("rh.folha.view",)
    guardados = (Guardado(ESPECIE_HOLERITE, FolhaPagamento, "holerite", quando="mes_referencia",
                          onde="funcionario__nome_completo"),)

    colunas = (
        Coluna("funcionario", "Funcionário"),
        Coluna("mes_referencia", "Mês de referência"),
        Coluna("holerite", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie != ESPECIE_HOLERITE:
            raise EntregaInvalida(f"Espécie '{especie}' não existe na folha.")
        folha = buscar_do_tenant(FolhaPagamento, chave, tenant_id)
        return entregar_campo(folha, folha.holerite, alternativa="holerite")
