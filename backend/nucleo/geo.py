# backend/nucleo/geo.py
"""Serviço **compartilhado** de resolução de endereço → município (cidade/UF/IBGE).

Reutilizável por qualquer módulo (calendário → feriados por localidade da Fatia F,
maps, drone, NF/relatórios) para não reimplementar a consulta a cada função. Dois
caminhos, nesta ordem de confiança:

1. **Com CEP:** [ViaCEP](https://viacep.com.br/) devolve cidade, UF **e** código
   IBGE de uma vez.
2. **Sem CEP (pelo nome):** extrai `cidade + UF` do texto livre (ou recebe-os
   prontos) e casa contra a lista de municípios do estado na API de localidades
   do **IBGE**, resolvendo o código IBGE.

Puro (sem modelo/tenant): apenas HTTP externo + cache longo (município e CEP
mudam pouco). Falhas de rede degradam para `None`, nunca estouram.
"""
from __future__ import annotations

import difflib
import logging
import re
import unicodedata

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

VIACEP_URL = "https://viacep.com.br/ws"
IBGE_URL = "https://servicodados.ibge.gov.br/api/v1/localidades"
TIMEOUT = (5, 10)          # (connect, read)
CACHE_TTL = 60 * 60 * 24 * 30  # 30 dias — CEP/município são estáveis

NOME_ESTADOS = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul",
    "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}
UFS = set(NOME_ESTADOS)


def _normalizar(texto: str) -> str:
    """Minúsculas sem acento nem espaço nas bordas — para casar nomes de cidade."""
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.strip().lower()


NOME_PARA_UF = {_normalizar(nome): uf for uf, nome in NOME_ESTADOS.items()}


def _uf_de_fragmento(fragmento: str):
    """Resolve uma UF a partir de um fragmento de texto: **sigla** (`BA`), **nome
    por extenso** (`Bahia`) ou nome com **pequeno erro de digitação** (fuzzy).
    Retorna a sigla ou `None`."""
    if not fragmento:
        return None
    sigla = fragmento.strip().upper()
    if len(sigla) == 2 and sigla in UFS:
        return sigla
    norm = _normalizar(fragmento)
    if norm in NOME_PARA_UF:
        return NOME_PARA_UF[norm]
    aprox = difflib.get_close_matches(norm, NOME_PARA_UF.keys(), n=1, cutoff=0.82)
    return NOME_PARA_UF[aprox[0]] if aprox else None


def _limpar_cidade(cidade: str):
    """Higieniza o candidato a cidade: remove "<número> - " residual e hífens
    soltos nas bordas (ex.: "500 - São Paulo" → "São Paulo")."""
    if not cidade:
        return None
    cidade = re.sub(r"^\d[\d\s\-]*", "", cidade).strip(" -/")
    cidade = re.sub(r"[-–]\s*$", "", cidade).strip(" -/")
    return cidade or None


def parse_endereco(texto: str):
    """Extrai `(cidade, uf)` de um endereço em texto livre — melhor esforço.

    **Ancorado no fim** (no Brasil o estado vem por último), o que naturalmente
    separa nome de rua de nome de cidade/estado: só o trecho adjacente à UF é
    tratado como cidade; o resto é logradouro/bairro. Reconhece a UF por sigla,
    nome por extenso ou grafia aproximada. Retorna `(None, None)` sem UF.
    """
    if not texto:
        return None, None
    segmentos = [s.strip() for s in re.split(r"[,/]", texto) if s.strip()]
    if not segmentos:
        return None, None

    # Varre do fim para o começo: a UF pode ser o segmento inteiro
    # ("…/Bahia", "…, SP") ou o sufixo de um segmento ("Campinas - SP").
    for i in range(len(segmentos) - 1, -1, -1):
        seg = segmentos[i]
        uf = _uf_de_fragmento(seg)
        if uf:
            cidade = segmentos[i - 1] if i - 1 >= 0 else None
            return _limpar_cidade(cidade), uf
        palavras = seg.split()
        for n in (3, 2, 1):  # nome de estado tem até 3 palavras (Rio Grande do Sul)
            if len(palavras) > n:  # precisa sobrar texto para a cidade
                uf = _uf_de_fragmento(" ".join(palavras[-n:]))
                if uf:
                    return _limpar_cidade(" ".join(palavras[:-n])), uf
    return None, None


def buscar_por_cep(cep: str):
    """ViaCEP por CEP (8 dígitos). Retorna o JSON do ViaCEP ou `None`."""
    digitos = re.sub(r"\D", "", cep or "")
    if len(digitos) != 8:
        return None
    chave = f"geo:cep:{digitos}"
    cacheado = cache.get(chave)
    if cacheado is not None:
        return cacheado or None  # '' negativo em cache → None
    try:
        resp = requests.get(f"{VIACEP_URL}/{digitos}/json/", timeout=TIMEOUT)
        resp.raise_for_status()
        dados = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("ViaCEP falhou para %s: %s", digitos, e)
        return None
    if dados.get("erro"):
        cache.set(chave, "", CACHE_TTL)
        return None
    cache.set(chave, dados, CACHE_TTL)
    return dados


def _municipios_uf(uf: str):
    """Lista de municípios da UF (IBGE), em cache — cada um com `id` e `nome`."""
    chave = f"geo:ibge:mun:{uf}"
    cacheado = cache.get(chave)
    if cacheado is not None:
        return cacheado
    try:
        resp = requests.get(f"{IBGE_URL}/estados/{uf}/municipios", timeout=TIMEOUT)
        resp.raise_for_status()
        municipios = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("IBGE falhou para UF %s: %s", uf, e)
        return []
    cache.set(chave, municipios, CACHE_TTL)
    return municipios


def listar_municipios(uf: str):
    """Municípios da UF como `[{ibge, nome}]` (ordenados por nome) — para popular
    o seletor de município. Reutiliza o cache do IBGE."""
    if not uf or uf.upper() not in UFS:
        return []
    itens = [
        {"ibge": str(m["id"]), "nome": m["nome"]}
        for m in _municipios_uf(uf.upper())
    ]
    return sorted(itens, key=lambda m: m["nome"])


def buscar_municipio(cidade: str, uf: str):
    """Casa `cidade` (nome) + `uf` → `{cidade, uf, ibge}` via IBGE, ou `None`.

    Faz match **exato** (normalizado, tolerante a acento/caixa) e, falhando,
    **aproximado** (fuzzy) contra os municípios da UF — corrige pequenos erros de
    digitação (ex.: "Santo Antonio de Jesuz" → "Santo Antônio de Jesus"). O nome
    devolvido é sempre o **oficial** do IBGE. O cutoff alto evita casar cidade
    errada (se nada casa bem, devolve `None` em vez de chutar)."""
    if not cidade or not uf or uf.upper() not in UFS:
        return None
    municipios = _municipios_uf(uf.upper())
    if not municipios:
        return None
    alvo = _normalizar(cidade)
    por_nome = {_normalizar(m.get("nome", "")): m for m in municipios}

    municipio = por_nome.get(alvo)
    if municipio is None:
        aprox = difflib.get_close_matches(alvo, por_nome.keys(), n=1, cutoff=0.86)
        municipio = por_nome[aprox[0]] if aprox else None
    if municipio is None:
        return None
    return {"cidade": municipio["nome"], "uf": uf.upper(), "ibge": str(municipio["id"])}


def resolver(cep: str = None, endereco: str = None, cidade: str = None, uf: str = None):
    """Resolve cidade/UF/IBGE. Ordem: CEP (ViaCEP) → nome (IBGE).

    Retorna dict com `cidade`, `uf`, `ibge` (+ `cep`/`logradouro`/`bairro` quando
    vindos do CEP) e `fonte` (`viacep_cep` | `ibge_nome`), ou `None` se nada casou.
    """
    # CEP no texto do endereço (formato NNNNN-NNN) → prefere o ViaCEP, mais
    # confiável que o parse por nome. Exige o hífen p/ não confundir com número.
    if not cep and endereco:
        m = re.search(r"\b(\d{5})-(\d{3})\b", endereco)
        if m:
            cep = m.group(1) + m.group(2)

    if cep:
        via = buscar_por_cep(cep)
        if via and via.get("ibge"):
            return {
                "cidade": via.get("localidade"),
                "uf": via.get("uf"),
                "ibge": str(via.get("ibge")),
                "cep": re.sub(r"\D", "", cep),
                "logradouro": via.get("logradouro") or "",
                "bairro": via.get("bairro") or "",
                "fonte": "viacep_cep",
            }

    if not (cidade and uf) and endereco:
        cidade_parse, uf_parse = parse_endereco(endereco)
        cidade = cidade or cidade_parse
        uf = uf or uf_parse

    if uf:
        uf = uf.upper()
        if cidade:
            municipio = buscar_municipio(cidade, uf)
            if municipio:
                municipio["fonte"] = "ibge_nome"
                return municipio
        # UF resolvida mas município não (cidade ausente/irreconhecível) →
        # devolve só o estado: ainda habilita os feriados estaduais e o seletor.
        if uf in UFS:
            return {"cidade": "", "uf": uf, "ibge": "", "fonte": "uf_apenas"}

    return None
