# backend/empreendimentos/impexp.py
"""D70 — o XML de NF-e anexado ao custo do empreendimento.

`CustoEmpreendimento.arquivo_xml` grava em `nfe_xmls/`, o **mesmo prefixo** que
o `moduloerp` usa para a nota fiscal de entrada. Dois apps escrevendo na mesma
pasta é o que tornava a allowlist de `/media/` enganosa: fechar "o prefixo do
ERP" teria deixado este aberto, porque prefixo não é dono — modelo é.

Gate próprio (`obra.empreend_custo.*`) e não o do ERP: quem vê o custo do
empreendimento não é necessariamente quem opera o financeiro, e o catálogo já
separava os dois.
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

from .models import CustoEmpreendimento

RECURSO_CUSTO_NFE = "obra.custo_nfe"
ESPECIE_XML = "xml"


@registrar(RECURSO_CUSTO_NFE)
class NfeDoCustoDoEmpreendimento(Recurso):
    """O XML da nota que comprova um custo do empreendimento."""

    rotulo = "NF-e do custo do empreendimento"
    modulo = "obra"
    entitlement = None  # empreendimento é fundação: `obra.*` mora no `base`
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("obra.empreend_custo.view", "obra.empreend_custo.edit")
    permissoes_entrega = ("obra.empreend_custo.view",)

    colunas = (
        Coluna("empreendimento", "Empreendimento"),
        Coluna("descricao", "Descrição do custo"),
        Coluna("chave_acesso", "Chave de acesso NF-e"),
        Coluna("arquivo_xml", "Arquivo XML"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie != ESPECIE_XML:
            raise EntregaInvalida(f"Espécie '{especie}' não existe no custo do empreendimento.")
        custo = buscar_do_tenant(CustoEmpreendimento, chave, tenant_id)
        return entregar_campo(custo, custo.arquivo_xml, alternativa="nfe.xml")
