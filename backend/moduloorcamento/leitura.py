# backend/moduloorcamento/leitura.py
"""Cabeçalho das publicações oficiais — o que só o comando de importação usa.

**IE.1 esvaziou este arquivo pela metade, de propósito.** As primitivas que
estavam aqui (normalizar, número brasileiro, delimitador, leitor de XLSX/CSV/PDF)
não têm nada de orçamento — o `1.234,56` de uma prefeitura é o mesmo de uma
carteira de clientes — e subiram inteiras para
[funcoesimpexp/formatos/leitura.py](../funcoesimpexp/formatos/leitura.py). Duas
cópias da heurística de cabeçalho divergiriam na primeira publicação com layout
novo, e a divergência apareceria como **preço errado**, não como erro.

O que sobrou é o que é de domínio e **não** cabe numa declaração de recurso: a
tabela de sinônimos da **analítica** (composição → item → coeficiente). Aquele
arquivo é uma tabela de ligação, não um recurso que alguém importa pela tela;
declarar um `Recurso` para ele só para reusar aliases seria inventar uma entrada
de menu que ninguém pediu.

Os sinônimos de insumo/composição que a **API** usa não estão mais aqui: moram na
declaração ([impexp.py](impexp.py)), que é a fonte única da R2.
"""
from __future__ import annotations

# Reexportados do motor: o comando é a interface pública destes nomes desde a
# ORC.0, e trocar o import de quem já os usa não vale o churn.
from funcoesimpexp.formatos.leitura import (  # noqa: F401
    LeituraInvalida,
    detectar_delimitador,
    normalizar,
    para_decimal,
)

# Sinônimos de cabeçalho por campo lógico, já normalizados (sem acento, minúsculo).
# A ordem importa: o primeiro alias que casar vence, então os mais específicos
# vêm antes ("codigo da composicao" antes de "codigo").
ALIASES: dict[str, tuple[str, ...]] = {
    "codigo": ("codigo do insumo", "codigo insumo", "codigo", "cod", "cod insumo"),
    "descricao": ("descricao do insumo", "descricao insumo", "descricao", "descricao do item"),
    "unidade": ("unidade", "unid", "und", "un", "unidade de medida"),
    "preco": (
        "preco mediano", "preco mediano r$", "custo unitario", "preco unitario",
        "custo total", "preco", "valor", "custo",
    ),
    "grupo": ("grupo", "classe", "descricao da classe", "grupo classe", "categoria"),
    # --- analítica (composição → item) ---
    "codigo_composicao": ("codigo da composicao", "codigo composicao", "cod composicao", "codigo"),
    "descricao_composicao": ("descricao da composicao", "descricao composicao"),
    "unidade_composicao": ("unidade da composicao", "unidade composicao", "unidade"),
    "codigo_item": ("codigo do item", "codigo item", "cod item", "codigo do insumo", "codigo insumo"),
    "descricao_item": ("descricao do item", "descricao item", "descricao do insumo", "descricao insumo"),
    "unidade_item": ("unidade do item", "unidade item", "und item"),
    "tipo_item": ("tipo de item", "tipo item", "tipo"),
    "coeficiente": ("coeficiente", "coef", "consumo", "quantidade"),
}

OBRIGATORIOS = {
    "insumos": ("codigo", "descricao", "unidade", "preco"),
    "composicoes": ("codigo", "descricao", "unidade", "preco"),
    "analitica": ("codigo_composicao", "codigo_item", "coeficiente"),
}


def detectar_colunas(linhas, obrigatorios: tuple[str, ...], limite: int = 25):
    """Procura, nas primeiras `limite` linhas, a que serve de cabeçalho.

    Devolve `(mapa, indice_da_linha, cabecalhos_vistos)`. Falha explícita é
    melhor que adivinhação: quem chama mostra `cabecalhos_vistos` para o operador
    escolher o de-para à mão.

    Irmão do `mapear_colunas` do motor, e a diferença é a fonte dos sinônimos:
    lá vêm das colunas que o recurso **declarou**; aqui, do `ALIASES` acima,
    porque a analítica não é um recurso declarado.
    """
    vistos: list[list[str]] = []
    for indice, linha in enumerate(linhas[:limite]):
        celulas = [normalizar(c) for c in linha]
        if not any(celulas):
            continue
        vistos.append([c for c in celulas if c])
        mapa: dict[str, int] = {}
        usados: set[int] = set()
        for campo in obrigatorios + tuple(c for c in ALIASES if c not in obrigatorios):
            for alias in ALIASES[campo]:
                for pos, celula in enumerate(celulas):
                    if pos in usados or celula != alias:
                        continue
                    mapa[campo] = pos
                    usados.add(pos)
                    break
                if campo in mapa:
                    break
        if all(campo in mapa for campo in obrigatorios):
            return mapa, indice, vistos
    return None, -1, vistos
