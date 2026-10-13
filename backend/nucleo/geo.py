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
from django.conf import settings
from django.core.cache import cache

from .rate_limit import LimiteFornecedorExcedido, consumir

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
    """Higieniza o candidato a cidade: fica com o que vem depois do último
    " - " (o que vem antes é número, bairro ou loteamento — ex.: "500 - São
    Paulo", "Loteamento Villa Privillege - Nazaré") e tira hífens soltos nas
    bordas. Hífen sem espaço é do nome ("Embu-Guaçu") e fica."""
    if not cidade:
        return None
    cidade = re.split(r"\s+[-–]\s+", cidade.strip())[-1]
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


# ===========================================================================
# COORDENADA — a cascata de geocodificação (MAP.0)
# ===========================================================================
# Nada aqui devolve um ponto sem dizer **de onde ele veio e quão perto está do
# lugar real**. É a regra de ouro do módulo Maps: um pin de centroide de
# município e um pin arrastado à mão não podem parecer a mesma coisa. Por isso
# toda função devolve `(lon, lat, precisao, fonte)` e nunca só a coordenada.
#
# As strings de `precisao`/`fonte` são o CONTRATO com `modulomaps.models`
# (`Precisao` / `FonteGeo`) — repetidas como texto de propósito: este módulo é
# `nucleo` e não pode importar um app de negócio. O teste amarra as duas listas.
#
# Ordem (a de confiança, docs/modulos/modulomaps.md §5): pin à mão e EXIF são
# resolvidos pelo chamador (já são `exata`); daqui para baixo é o que exige rede.

PRECISAO_ENDERECO = "endereco"
PRECISAO_CEP = "cep"
PRECISAO_MUNICIPIO = "municipio"


def _externo(fornecedor: str, url: str, params=None, headers=None):
    """GET a um provedor geo com o limite de saída da camada 2 aplicado.

    Devolve o JSON ou `None`. Nunca estoura: geocodificação é melhor-esforço, e
    a alternativa a um degrau indisponível é o degrau seguinte (mais grosso),
    não uma tela de erro. Inclusive o estouro de cota vira `None` — quem chamou
    recebe uma precisão pior, que é uma resposta honesta, em vez de um 429 no
    meio de um cadastro.
    """
    try:
        consumir(fornecedor)
    except LimiteFornecedorExcedido:
        logger.warning("Limite de saída atingido em %s; degradando a cascata geo.", fornecedor)
        return None
    try:
        resp = requests.get(
            url, params=params or {}, headers=headers or {},
            timeout=getattr(settings, "GEO_TIMEOUT", TIMEOUT),
        )
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as e:
        # Sem `e` no log: o texto de um HTTPError traz a URL **com a query**, e
        # a query de provedor com chave (`?key=`) levaria a credencial ao log.
        status = getattr(getattr(e, "response", None), "status_code", "")
        logger.warning("Provedor geo %s falhou (%s): %s %s", fornecedor, url, type(e).__name__, status)
        return None


def geocodificar_endereco(endereco: str):
    """Endereço em texto → coordenada de **porta**, via Nominatim.

    Sem `NOMINATIM_URL` configurada a função devolve `None` e a cascata cai no
    degrau seguinte: o padrão do produto é grátis/self-host, e geocodificação
    fina é add-on (planta §9). Vale dizer o que NÃO se faz aqui: chutar a
    coordenada do centro da cidade e chamar de "endereço".
    """
    base = getattr(settings, "NOMINATIM_URL", "")
    if not base or not endereco:
        return None
    chave = f"geo:nominatim:{_normalizar(endereco)}"
    cacheado = cache.get(chave)
    if cacheado is not None:
        return cacheado or None
    params = {"q": endereco, "format": "json", "countrycodes": "br", "limit": 1}
    # Provedor compatível com chave (LocationIQ): mesma API, mais `key`. O
    # `format=json` (e não `jsonv2`) é o que os dois falam — os campos lidos
    # aqui (`lon`, `lat`) são iguais nos dois formatos.
    if getattr(settings, "NOMINATIM_API_KEY", ""):
        params["key"] = settings.NOMINATIM_API_KEY
    dados = _externo(
        "geo", f"{base.rstrip('/')}/search",
        params=params,
        # Exigência da política de uso do Nominatim público; num self-host é rastro.
        headers={"User-Agent": getattr(settings, "NOMINATIM_USER_AGENT", "sgi-plataforma/1.0")},
    )
    if not dados:
        return None
    try:
        lon, lat = float(dados[0]["lon"]), float(dados[0]["lat"])
    except (KeyError, IndexError, TypeError, ValueError):
        cache.set(chave, "", CACHE_TTL)
        return None
    ponto = {"lon": lon, "lat": lat, "precisao": PRECISAO_ENDERECO, "fonte": "geocoder"}
    cache.set(chave, ponto, CACHE_TTL)
    return ponto


def coordenada_por_cep(cep: str):
    """CEP → coordenada do logradouro (BrasilAPI v2), quando a base a conhece.

    O ViaCEP, que já usamos para cidade/UF/IBGE, **não devolve coordenada** —
    daí o segundo provedor. Quando a base não tem o ponto do logradouro, ela
    responde sem `location`, e devolvemos `None` em vez do centro do bairro.
    """
    digitos = re.sub(r"\D", "", cep or "")
    if len(digitos) != 8:
        return None
    chave = f"geo:cepgeo:{digitos}"
    cacheado = cache.get(chave)
    if cacheado is not None:
        return cacheado or None
    base = getattr(settings, "BRASILAPI_CEP_URL", "")
    if not base:
        return None
    dados = _externo("geo", f"{base.rstrip('/')}/{digitos}")
    coords = ((dados or {}).get("location") or {}).get("coordinates") or {}
    try:
        lon, lat = float(coords["longitude"]), float(coords["latitude"])
    except (KeyError, TypeError, ValueError):
        cache.set(chave, "", CACHE_TTL)
        return None
    ponto = {"lon": lon, "lat": lat, "precisao": PRECISAO_CEP, "fonte": "cep"}
    cache.set(chave, ponto, CACHE_TTL)
    return ponto


def _centroide_anel(anel):
    """Centroide de um anel (fórmula do polígono / *shoelace*).

    Em Python puro, e não via GEOS, por uma razão prática: este módulo é
    `nucleo` — compartilhado com calendário e NF — e não deve exigir a stack
    geoespacial para ser importado. São 10 linhas, e o resultado é o centro de
    massa de verdade, não o centro do retângulo envolvente (que numa cidade em
    "L" cai fora do município).
    """
    area = cx = cy = 0.0
    for i in range(len(anel) - 1):
        x0, y0 = anel[i][0], anel[i][1]
        x1, y1 = anel[i + 1][0], anel[i + 1][1]
        cruz = x0 * y1 - x1 * y0
        area += cruz
        cx += (x0 + x1) * cruz
        cy += (y0 + y1) * cruz
    if abs(area) < 1e-12:  # degenerado → média simples dos vértices
        n = max(1, len(anel))
        return sum(p[0] for p in anel) / n, sum(p[1] for p in anel) / n
    area *= 0.5
    return cx / (6 * area), cy / (6 * area)


def _aneis_do_geojson(geometria):
    """Todos os anéis externos de um Polygon/MultiPolygon do GeoJSON."""
    tipo = (geometria or {}).get("type")
    coords = (geometria or {}).get("coordinates") or []
    if tipo == "Polygon":
        return [coords[0]] if coords else []
    if tipo == "MultiPolygon":
        return [poligono[0] for poligono in coords if poligono]
    return []


def centroide_municipio(ibge: str):
    """Código IBGE → centroide do município, pela **malha oficial** do IBGE.

    É o último degrau da cascata, e o mais grosso: diz "em algum lugar desta
    cidade". Existe porque é melhor que nada — uma obra que aparece na cidade
    certa já responde "quais obras tenho no interior?" —, mas só presta se a
    tela declarar a precisão, que é o que a `Precisao.MUNICIPIO` faz.
    """
    codigo = re.sub(r"\D", "", str(ibge or ""))
    if len(codigo) != 7:
        return None
    chave = f"geo:centroide:{codigo}"
    cacheado = cache.get(chave)
    if cacheado is not None:
        return cacheado or None
    base = getattr(settings, "IBGE_MALHAS_URL", "")
    if not base:
        return None
    dados = _externo(
        "geo", f"{base.rstrip('/')}/{codigo}",
        params={"formato": "application/vnd.geo+json", "qualidade": "minima"},
    )
    # A malha vem como FeatureCollection; pegamos a geometria da 1ª feature.
    geometria = None
    if isinstance(dados, dict):
        if dados.get("type") == "FeatureCollection" and dados.get("features"):
            geometria = dados["features"][0].get("geometry")
        elif dados.get("type") in ("Polygon", "MultiPolygon"):
            geometria = dados
    aneis = _aneis_do_geojson(geometria)
    if not aneis:
        cache.set(chave, "", CACHE_TTL)
        return None
    # Vários polígonos (ilhas): fica com o maior anel, que é o continente do
    # município — o centroide da média incluiria ilhas distantes e sairia no mar.
    maior = max(aneis, key=len)
    lon, lat = _centroide_anel(maior)
    ponto = {"lon": lon, "lat": lat, "precisao": PRECISAO_MUNICIPIO, "fonte": "ibge"}
    cache.set(chave, ponto, CACHE_TTL)
    return ponto


def geocodificar(endereco: str = None, cep: str = None, cidade: str = None,
                 uf: str = None, ibge: str = None):
    """**A cascata.** Devolve o melhor ponto disponível, sempre com procedência.

    Ordem: endereço (porta) → CEP (logradouro) → município (centro de massa).
    Os dois degraus mais confiáveis — pin à mão e EXIF — não estão aqui porque
    não dependem de rede: quem os tem já grava `precisao=exata`.

    Retorna `{"lon", "lat", "precisao", "fonte"}` ou `None` quando nem o
    município foi possível resolver. `None` é resposta legítima e vira
    `precisao=desconhecida` no `Local` — é o que alimenta a fila "obras sem
    coordenada" em vez de um pin inventado.
    """
    ponto = geocodificar_endereco(endereco)
    if ponto:
        return ponto

    # O CEP pode vir do campo ou estar embutido no texto do endereço — o mesmo
    # padrão que `resolver()` já usa uma camada acima.
    if not cep and endereco:
        m = re.search(r"\b(\d{5})-?(\d{3})\b", endereco)
        if m:
            cep = m.group(1) + m.group(2)
    ponto = coordenada_por_cep(cep)
    if ponto:
        return ponto

    if not ibge:
        localidade = resolver(cep=cep, endereco=endereco, cidade=cidade, uf=uf)
        ibge = (localidade or {}).get("ibge")
    return centroide_municipio(ibge) if ibge else None
