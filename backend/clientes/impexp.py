# backend/clientes/impexp.py
"""D70 — `documentos_clientes/` sai pela porta única.

RG, CPF, CNH, comprovante de residência e certidão de casamento **do titular**:
é a mesma natureza dos documentos do RH, com um agravante de alcance — o cliente
não é empregado da empresa, e o dado dele está aqui por causa de um contrato.

**`entitlement = None` porque cadastro de cliente é fundação.** As permissões
`cadastro.*` moram no módulo `base` (catálogo da IAM), que todo tenant tem: não
há módulo a cobrar, e cobrar um faria a ficha do cliente exigir assinatura que
ninguém vende. É o mesmo caso do `maps.local`, e por isso a herança do padrão
(`entitlement = modulo`) precisa ser desligada à mão.
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

from .models import DocumentoCliente

RECURSO_DOCUMENTOS = "cadastro.documento_cliente"
ESPECIE_DOCUMENTO = "documento"


@registrar(RECURSO_DOCUMENTOS)
class DocumentosDoCliente(Recurso):
    """Os documentos anexados à ficha do cliente."""

    rotulo = "Documentos do cliente"
    modulo = "cadastro"
    entitlement = None  # fundação — ver o cabeçalho
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("cadastro.cliente.view", "cadastro.cliente.edit")
    permissoes_entrega = ("cadastro.cliente.view",)

    colunas = (
        Coluna("cliente", "Cliente"),
        Coluna("tipo_documento", "Tipo de documento"),
        Coluna("nome_documento", "Nome do documento"),
        Coluna("arquivo", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie != ESPECIE_DOCUMENTO:
            raise EntregaInvalida(f"Espécie '{especie}' não existe nos documentos do cliente.")
        doc = buscar_do_tenant(DocumentoCliente, chave, tenant_id)
        return entregar_campo(doc, doc.arquivo, alternativa="documento")
