# backend/moduloscm/impexp.py
"""D70 — o XML e o DANFE da NF-e da compra saem pela porta única (D284).

O XML de uma NF-e carrega CNPJ, endereço e a lista do que se comprou: é dado
fiscal completo, e não pode sair por `/media/` (fora de auth, entitlement e
RLS). Entra pelo recebimento do pedido; sai daqui, com `scm.recebimento.view`,
e aparece no DMS como todo arquivo guardado.
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

from .models import NotaFiscalCompra

RECURSO_NOTA_COMPRA = "scm.nota_compra"

#: Espécie → (campo, nome de fallback).
_ARQUIVOS = {
    "xml": ("arquivo_xml", "nfe.xml"),
    "pdf": ("arquivo_pdf", "danfe.pdf"),
}


@registrar(RECURSO_NOTA_COMPRA)
class ArquivosDaNotaDeCompra(Recurso):
    """XML e DANFE da NF-e lançada no recebimento do pedido de compra."""

    rotulo = "NF-e das compras"
    modulo = "scm"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("scm.recebimento.view", "scm.recebimento.edit")
    permissoes_entrega = ("scm.recebimento.view",)
    guardados = tuple(Guardado(especie, NotaFiscalCompra, campo) for especie, (campo, _) in _ARQUIVOS.items())

    colunas = (
        Coluna("numero", "Número da nota"),
        Coluna("chave_acesso", "Chave de acesso"),
        Coluna("data_emissao", "Data de emissão"),
        Coluna("arquivo", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        alvo = _ARQUIVOS.get(especie)
        if alvo is None:
            raise EntregaInvalida(f"Espécie '{especie}' não existe na NF-e da compra.")
        campo, alternativa = alvo
        nota = buscar_do_tenant(NotaFiscalCompra, chave, tenant_id)
        return entregar_campo(nota, getattr(nota, campo), alternativa=alternativa)
