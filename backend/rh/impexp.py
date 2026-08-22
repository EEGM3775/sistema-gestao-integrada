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

from funcoesimpexp.entrega import buscar_do_tenant, entregar_campo
from funcoesimpexp.registro import (
    NATUREZA_ARQUIVO,
    ArquivoEntregue,
    Coluna,
    EntregaInvalida,
    Recurso,
    registrar,
)

from .models import ASOFuncionario, DocumentoFuncionario, FolhaPagamento, Funcionario

#: Os três recursos do RH no registry. Constantes porque o serializer os cita
#: para montar a URL, e um erro de digitação daria 404 só naquele campo.
RECURSO_DOCUMENTOS = "rh.documentos"
RECURSO_ASO = "rh.aso"
RECURSO_HOLERITE = "rh.holerite"

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
