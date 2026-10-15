# backend/catalogo/impexp.py
"""Os itens do catálogo entram e saem como planilha (15/10/2026).

**Fundação** (`entitlement = None`): `cadastro.item.*` é do `base`, como o
fornecedor. A chave é o **código interno** (SKU), único por tenant no banco.

**Só item próprio.** A planilha não traz fonte, código nem publicação de
referência: item da SINAPI e das outras bases entra pela adoção da base, que é
do dono da plataforma (`orcamento.base_referencial`). O que entra aqui conta na
quota `catalogo_itens`, como o item cadastrado na tela.
"""
from __future__ import annotations

from funcoesimpexp.cadastro import RecursoDeCadastro
from funcoesimpexp.registro import Coluna, registrar

from .models import Item

RECURSO_ITENS = "cadastro.item"


@registrar(RECURSO_ITENS)
class ItensDoCatalogo(RecursoDeCadastro):
    rotulo = "Itens do catálogo"
    modulo = "cadastro"
    entitlement = None  # fundação — ver o cabeçalho
    permissoes_exigidas = ("cadastro.item.view", "cadastro.item.edit")
    modelo = Item
    chave = "codigo_interno"
    quota = "catalogo_itens"
    ordem = ("descricao",)
    campos_de_busca = ("codigo_interno", "descricao", "categoria", "gtin")
    filtros = {"tipo": "tipo", "categoria": "categoria", "ativo": "ativo", "origem": "origem"}

    colunas = (
        Coluna("codigo_interno", "Código", obrigatoria=True, exemplo="CIM-50",
               aliases=("codigo interno", "sku", "codigo")),
        Coluna("descricao", "Descrição", obrigatoria=True, exemplo="Cimento CP-II 50 kg",
               aliases=("item", "nome")),
        Coluna("unidade", "Unidade", obrigatoria=True, exemplo="sc", aliases=("un", "und")),
        Coluna("categoria", "Categoria", exemplo="Aglomerantes"),
        Coluna("tipo", "Tipo", exemplo="Material", aliases=("natureza",)),
        Coluna("ncm", "NCM", exemplo="25232910"),
        Coluna("gtin", "GTIN/EAN", exemplo="", aliases=("gtin", "ean", "codigo de barras")),
    )

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        # Em branco é material, como na ficha; o cadastro nasce manual e próprio.
        saida["tipo"] = saida.get("tipo") or Item.Tipo.MATERIAL
        saida["origem"] = Item.Origem.MANUAL
        saida["origem_detalhe"] = "Importação de planilha"
        return saida
