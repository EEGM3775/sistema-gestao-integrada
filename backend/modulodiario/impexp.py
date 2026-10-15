# backend/modulodiario/impexp.py
"""D70 — `diario_obra_media/` sai pela porta única.

A foto e o vídeo que o encarregado anexa ao diário do dia, muitos deles vindos
do WhatsApp. É o prefixo de maior **volume de leitura** dos nove: a linha do
tempo do diário mostra dezenas de miniaturas por página.

**Rastro auditado, como os outros oito — e a consequência está declarada.** A
regra do R12 é de autoria, não de gravidade: o arquivo é do cliente, então o
download entra na trilha. Isso significa uma linha de `AuditLog` por miniatura
carregada, e uma página de diário com 20 fotos grava 20 linhas — o risco de
afogar o [D67](../../docs/historico-correcoes.md) que a Prancheta evitou
declarando a derivada como `RASTRO_INTERNO`.

Não foi resolvido baixando o rastro deste recurso, e a escolha é deliberada:
enfraquecer auditoria no mesmo commit que fecha um vazamento é trocar um
problema por outro, em silêncio. **A saída certa é a mesma da Prancheta** — uma
*miniatura* gerada por nós, servida como `RASTRO_INTERNO` na linha do tempo,
deixando o original (auditado) para quem pedir o arquivo. Ela não existe ainda;
está declarada como decisão em aberto na planta do módulo, com este gatilho.
"""
from __future__ import annotations

from datetime import date

from funcoesimpexp.cadastro import RecursoDeLista
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

from .models import DocumentoDiario, EntradaDiario

RECURSO_MIDIA = "obra.diario_midia"
RECURSO_REGISTROS = "obra.diario"
ESPECIE_MIDIA = "midia"


@registrar(RECURSO_MIDIA)
class MidiaDoDiario(Recurso):
    """Foto e vídeo do diário de obra."""

    rotulo = "Mídia do diário de obra"
    modulo = "obra"
    entitlement = None  # diário é fundação: `obra.diario.*` mora no `base`
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("obra.diario.view", "obra.diario.edit")
    permissoes_entrega = ("obra.diario.view",)
    guardados = (Guardado(ESPECIE_MIDIA, DocumentoDiario, "arquivo", quando="data_criacao",
                          titulo="descricao", onde="diario_obra__obra__nome_obra"),)

    colunas = (
        Coluna("diario_obra", "Diário"),
        Coluna("autor", "Autor"),
        Coluna("origem", "Origem"),
        Coluna("descricao", "Descrição"),
        Coluna("arquivo", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie != ESPECIE_MIDIA:
            raise EntregaInvalida(f"Espécie '{especie}' não existe na mídia do diário.")
        doc = buscar_do_tenant(DocumentoDiario, chave, tenant_id)
        return entregar_campo(doc, doc.arquivo, alternativa="midia")


# ---------------------------------------------------------------------------
# Os registros do diário saem como planilha (15/10/2026)
# ---------------------------------------------------------------------------
#
# **Só exporta** (decisão do dono, 15/10/2026): o diário é documento — cada
# registro tem autor, hora e origem (web, WhatsApp, IA), e um registro em lote
# por planilha seria um diário escrito depois, que é justamente o que ele não
# pode ser. Uma linha por registro, no recorte da tela (a obra escolhida).


@registrar(RECURSO_REGISTROS)
class RegistrosDoDiario(RecursoDeLista):
    rotulo = "Registros do diário de obra"
    modulo = "obra"
    entitlement = None  # diário é fundação: `obra.diario.*` mora no `base`
    permissoes_exigidas = ("obra.diario.view",)
    modelo = EntradaDiario
    ordem = ("-diario_obra__data", "data_criacao")
    filtros = {"obra": "diario_obra__obra_id", "data": "diario_obra__data"}
    campos_de_busca = ("texto",)

    colunas = (
        Coluna("diario_obra__data", "Dia", tipo=date),
        Coluna("diario_obra__obra__nome_obra", "Obra"),
        Coluna("diario_obra__condicoes_climaticas", "Clima"),
        Coluna("autor", "Autor"),
        Coluna("origem", "Origem"),
        Coluna("eh_ocorrencia", "Ocorrência"),
        Coluna("texto", "Registro"),
        Coluna("data_criacao", "Registrado em", tipo=date),
    )

    def escopo(self, qs, request):
        return qs.select_related("diario_obra__obra", "autor")

    def serializar_objeto(self, obj) -> dict:
        saida = super().serializar_objeto(obj)
        saida["autor"] = obj.autor.nome_completo if obj.autor_id else ""
        saida["eh_ocorrencia"] = "Sim" if obj.eh_ocorrencia else "Não"
        return saida
