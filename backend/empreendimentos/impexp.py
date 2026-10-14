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

from .models import CustoEmpreendimento, Empreendimento

RECURSO_CUSTO_NFE = "obra.custo_nfe"
RECURSO_EMPREENDIMENTOS = "obra.empreendimento"
ESPECIE_XML = "xml"


@registrar(RECURSO_EMPREENDIMENTOS)
class CadastroDeEmpreendimentos(RecursoDeCadastro):
    """Os empreendimentos. A chave é o CNPJ, único por tenant como a razão social.

    As unidades, as contas bancárias e os custos ficam fora: são outras tabelas,
    com tela própria. Aqui entra o cadastro do empreendimento em si.
    """

    rotulo = "Empreendimentos"
    modulo = "obra"
    entitlement = None  # empreendimento é fundação: `obra.*` mora no `base`
    permissoes_exigidas = ("obra.empreendimento.view", "obra.empreendimento.edit")
    modelo = Empreendimento
    chave = "cnpj"
    quota = "empreendimentos"
    ordem = ("empreendimento",)
    campos_de_busca = ("empreendimento", "razao_social")
    busca_por_palavra = False  # a tela filtra no navegador, pela frase
    filtros = {"status": "status_empreendimento", "status_empreendimento": "status_empreendimento"}

    @property
    def referencias(self) -> dict:
        from entidades.models import Entidade

        return {"entidade_propria": (Entidade, "nome")}

    colunas = (
        Coluna("cnpj", "CNPJ", obrigatoria=True, exemplo="12.345.678/0001-90"),
        Coluna("empreendimento", "Empreendimento", obrigatoria=True, exemplo="Residencial Aurora",
               aliases=("nome", "nome do empreendimento")),
        Coluna("razao_social", "Razão social", obrigatoria=True, exemplo="Aurora SPE Ltda"),
        Coluna("entidade_propria", "Entidade (SPE)", exemplo="Aurora SPE Ltda",
               aliases=("entidade", "spe")),
        Coluna("telefone", "Telefone", obrigatoria=True, exemplo="(71) 3333-0000"),
        Coluna("endereco", "Endereço", obrigatoria=True, exemplo="Av. Paralela, 1000"),
        Coluna("cidade", "Cidade", exemplo="Salvador"),
        Coluna("estado", "UF", exemplo="BA"),
        Coluna("status_empreendimento", "Situação", exemplo="Planejamento", aliases=("status",)),
        Coluna("data_inicio_prevista", "Início previsto", tipo=date, exemplo="01/02/2026"),
        Coluna("data_fim_prevista", "Fim previsto", tipo=date, exemplo="30/06/2028"),
        Coluna("data_inicio_real", "Início real", tipo=date),
        Coluna("data_fim_real", "Fim real", tipo=date),
        Coluna("orcamento_total", "Orçamento total", tipo=Decimal, exemplo="12.500.000,00"),
        Coluna("descricao", "Descrição"),
    )

    def normalizar_chave(self, valor) -> str:
        # A ficha grava o CNPJ só com dígitos (`EmpreendimentoForm`).
        return re.sub(r"\D", "", str(valor or ""))

    def recortar(self, qs, recorte: dict, request):
        """R7 — a busca da tela também acha pelos dígitos do CNPJ
        (`useEmpreendimentos`), além do nome e da razão social."""
        busca = str(recorte.get("search") or "").strip()
        qs = super().recortar(qs, {k: v for k, v in recorte.items() if k != "search"}, request)
        if not busca:
            return qs
        from django.db.models import Q

        condicao = Q(empreendimento__unaccent__icontains=busca) | Q(
            razao_social__unaccent__icontains=busca,
        )
        digitos = re.sub(r"\D", "", busca)
        if digitos:
            condicao |= Q(cnpj__contains=digitos)
        return qs.filter(condicao)

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        saida["estado"] = (saida.get("estado") or "").upper()
        saida["status_empreendimento"] = saida.get("status_empreendimento") or "planejamento"
        return saida

    def validar_regras(self, objeto, dados, tenant_id) -> str:
        from nucleo.documentos import cnpj_valido

        if not cnpj_valido(objeto.cnpj):
            return f"CNPJ “{dados.get('cnpj')}” não é válido (confira os dígitos)."
        if objeto.data_fim_prevista and objeto.data_inicio_prevista and (
            objeto.data_fim_prevista < objeto.data_inicio_prevista
        ):
            return "Fim previsto anterior ao início previsto."
        return ""


@registrar(RECURSO_CUSTO_NFE)
class NfeDoCustoDoEmpreendimento(Recurso):
    """O XML da nota que comprova um custo do empreendimento."""

    rotulo = "NF-e do custo do empreendimento"
    modulo = "obra"
    entitlement = None  # empreendimento é fundação: `obra.*` mora no `base`
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("obra.empreend_custo.view", "obra.empreend_custo.edit")
    permissoes_entrega = ("obra.empreend_custo.view",)
    guardados = (Guardado(ESPECIE_XML, CustoEmpreendimento, "arquivo_xml", quando="data_upload",
                          titulo="chave_acesso", onde="empreendimento__empreendimento"),)

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
