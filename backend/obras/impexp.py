# backend/obras/impexp.py
"""D70 — `documentos_obras/` sai pela porta única.

Contrato, ART/RRT, licença, memorial: documento da obra, com status e aprovador
próprios. Não é PII de titular como o do RH, e continua sendo **arquivo do
cliente saindo do perímetro** — que é a linha que o R12 usa, e não a gravidade
do conteúdo.

**Não confundir com o acervo da Prancheta.** Ali estão os *desenhos*, com
revisão, conversão e visualizador; aqui está a papelada administrativa da obra,
que ninguém converte. Os dois vizinhos justificam a pergunta e a resposta é o
gate: `obra.obra.view` contra `prancheta.documento.view`.
"""
from __future__ import annotations

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

from .models import DocumentoObra

RECURSO_DOCUMENTOS = "obra.documento"
ESPECIE_DOCUMENTO = "documento"


@registrar(RECURSO_DOCUMENTOS)
class DocumentosDaObra(Recurso):
    """A papelada da obra — contrato, licença, memorial."""

    rotulo = "Documentos da obra"
    modulo = "obra"
    entitlement = None  # obra é fundação: as permissões `obra.*` são do `base`
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("obra.obra.view", "obra.obra.edit")
    permissoes_entrega = ("obra.obra.view",)
    guardados = (Guardado(ESPECIE_DOCUMENTO, DocumentoObra, "arquivo", quando="data_cadastro",
                          titulo="nome_documento", onde="obra__nome_obra"),)

    colunas = (
        Coluna("obra", "Obra"),
        Coluna("tipo_documento", "Tipo de documento"),
        Coluna("nome_documento", "Nome do documento"),
        Coluna("versao", "Versão"),
        Coluna("arquivo", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie != ESPECIE_DOCUMENTO:
            raise EntregaInvalida(f"Espécie '{especie}' não existe nos documentos da obra.")
        doc = buscar_do_tenant(DocumentoObra, chave, tenant_id)
        return entregar_campo(doc, doc.arquivo, alternativa="documento")
