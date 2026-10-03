# backend/moduloerp/impexp.py
"""D70 — `nfe_xmls/` e `notas_fiscais/` saem pela porta única.

**Três modelos e seis campos, num recurso só, porque o gate é um só.** A NFS-e
(serviço) e a NF-e (produto) são as notas que **nós emitimos** pela NFE.io; a
`NotaFiscal` é a nota de **entrada**, que o fornecedor mandou e alguém anexou ao
empreendimento. Os três guardam PDF e/ou XML, e `erp.nf.view` responde pelos
três — foi assim que o catálogo os agrupou desde a Fase 9.

**Por que o XML importa tanto quanto o PDF.** O XML da NF-e carrega CNPJ,
endereço e a lista de itens do que se comprou; é dado fiscal completo, legível
por máquina, e era o mais fácil de varrer em massa a partir de `/media/` — os
caminhos tinham data (`nfe_xmls/2026/08/`) e nada mais, então quem descobrisse
um nome de arquivo enumerava o mês inteiro sem token.

`id` é `erp.nota_fiscal` e `modulo` é `erp_financeiro`: o primeiro segue o
espaço de nomes das permissões (`erp.nf.*`), o segundo é o código do módulo
vendável, que é o que o `entitlement` cobra. São dois vocabulários que já
existiam assim, e forçá-los a coincidir aqui renomearia um dos dois.
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

from .models import NotaFiscal, NotaFiscalProduto, NotaFiscalServico

RECURSO_NOTA_FISCAL = "erp.nota_fiscal"

#: Espécie → (modelo, campo, nome de fallback). Tabela e não uma cadeia de `if`
#: porque são seis casos idênticos: o que muda entre eles é só de onde o binário
#: vem, e um `if` por caso convidaria a divergirem.
_ARQUIVOS = {
    "nfse_pdf": (NotaFiscalServico, "arquivo_pdf", "nfse.pdf"),
    "nfse_xml": (NotaFiscalServico, "arquivo_xml", "nfse.xml"),
    "nfe_pdf": (NotaFiscalProduto, "arquivo_pdf", "nfe.pdf"),
    "nfe_xml": (NotaFiscalProduto, "arquivo_xml", "nfe.xml"),
    "entrada_pdf": (NotaFiscal, "arquivo_pdf", "nota-entrada.pdf"),
    "entrada_xml": (NotaFiscal, "arquivo_xml", "nota-entrada.xml"),
}


@registrar(RECURSO_NOTA_FISCAL)
class ArquivosDeNotaFiscal(Recurso):
    """PDF e XML das notas emitidas e da nota de entrada."""

    rotulo = "Arquivos de nota fiscal"
    modulo = "erp_financeiro"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("erp.nf.view", "erp.nf.edit")
    permissoes_entrega = ("erp.nf.view",)
    guardados = tuple(
        Guardado(especie, modelo, campo) for especie, (modelo, campo, _) in _ARQUIVOS.items()
    )

    colunas = (
        Coluna("numero", "Número da nota"),
        Coluna("chave_acesso", "Chave de acesso"),
        Coluna("data_emissao", "Data de emissão"),
        Coluna("arquivo", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        alvo = _ARQUIVOS.get(especie)
        if alvo is None:
            raise EntregaInvalida(f"Espécie '{especie}' não existe nas notas fiscais.")
        modelo, campo, alternativa = alvo
        nota = buscar_do_tenant(modelo, chave, tenant_id)
        return entregar_campo(nota, getattr(nota, campo), alternativa=alternativa)
