# backend/modulomaps/services.py
"""Regras do Maps que não são CRUD: cascata aplicada, cerca e vizinhança.

Fica fora das views de propósito — a mesma cascata é chamada pelo endpoint
`geocodificar/`, pelo comando de backfill, pela conferência do `funcoesimpexp`
(MAP.5) e pelo seam da NF-e. Quatro portas, uma regra.
"""
from __future__ import annotations

import logging
import math
import re
import unicodedata

from django.utils import timezone

from nucleo import geo

from .models import FonteGeo, Geofence, Local, Precisao

logger = logging.getLogger(__name__)

# Raio médio da Terra (m). Usado no fallback de distância e no desenho da cerca —
# nos dois casos a alternativa seria reprojetar para UTM, que quebra em obra
# perto de divisa de fuso (o motivo de o armazenamento ser 4326, planta §3).
RAIO_TERRA_M = 6_371_008.8

# Tradução do vocabulário de `nucleo.geo` (strings) para o do modelo (choices).
# As duas listas são amarradas por teste: `nucleo` não pode importar app de
# negócio, então o contrato é textual e precisa de guarda.
_PRECISAO_POR_TEXTO = {
    "endereco": Precisao.ENDERECO,
    "cep": Precisao.CEP,
    "municipio": Precisao.MUNICIPIO,
    "exata": Precisao.EXATA,
}
_FONTE_POR_TEXTO = {
    "geocoder": FonteGeo.GEOCODER,
    "cep": FonteGeo.CEP,
    "ibge": FonteGeo.IBGE,
    "manual": FonteGeo.MANUAL,
    "exif": FonteGeo.EXIF,
}


def distancia_m(lon1, lat1, lon2, lat2) -> float:
    """Distância de grande círculo (haversine), em metros.

    É o que sustenta o fallback de rota e o raio de fornecedor quando não há
    motor de rota. **Não** é distância de rua: quem a usa declara `estimada`.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAIO_TERRA_M * math.asin(min(1.0, math.sqrt(a)))


# ---------------------------------------------------------------------------
# Cascata aplicada ao Local
# ---------------------------------------------------------------------------
def geocodificar_local(local: Local, forcar: bool = False) -> bool:
    """Roda a cascata e grava o resultado. Devolve `True` se mudou algo.

    **Não sobrescreve pin melhor por pin pior.** Um ponto `exata` (arrastado à
    mão ou vindo do EXIF) é a verdade de campo; um backfill noturno que o
    trocasse por centroide de município destruiria o trabalho de quem foi lá.
    `forcar=True` existe para o caso legítimo de reprocessar, e mesmo assim
    respeita o `exata`.
    """
    if local.precisao == Precisao.EXATA:
        return False
    if local.ponto is not None and not forcar:
        return False

    ponto = geo.geocodificar(
        endereco=local.endereco_formatado() or None,
        cep=local.cep or None,
        cidade=local.cidade or None,
        uf=local.uf or None,
        ibge=local.ibge or None,
    )
    if not ponto:
        # Sem coordenada é um estado legítimo, e é o que alimenta a fila de
        # decisão "sem coordenada". Inventar 0,0 poria a obra no golfo da Guiné.
        return False

    from django.contrib.gis.geos import Point

    local.ponto = Point(ponto["lon"], ponto["lat"], srid=4326)
    local.precisao = _PRECISAO_POR_TEXTO.get(ponto["precisao"], Precisao.DESCONHECIDA)
    local.fonte = _FONTE_POR_TEXTO.get(ponto["fonte"], "")
    local.geocodificado_em = timezone.now()
    local.save(update_fields=["ponto", "precisao", "fonte", "geocodificado_em", "atualizado_em"])
    return True


def completar_localidade(local: Local) -> bool:
    """Preenche cidade/UF/IBGE a partir do CEP ou do texto do endereço.

    Roda antes da cascata porque o último degrau (centroide de município)
    depende do código IBGE — e porque cidade/UF estruturados são o que permite
    agrupar a carteira por região, coisa que `endereco` em texto nunca deu.
    """
    if local.cidade and local.uf and local.ibge:
        return False
    achado = geo.resolver(
        cep=local.cep or None,
        endereco=local.endereco_formatado() or None,
        cidade=local.cidade or None,
        uf=local.uf or None,
    )
    if not achado:
        return False
    local.cidade = local.cidade or achado.get("cidade") or ""
    local.uf = local.uf or achado.get("uf") or ""
    local.ibge = local.ibge or achado.get("ibge") or ""
    if not local.logradouro and achado.get("logradouro"):
        local.logradouro = achado["logradouro"]
    if not local.bairro and achado.get("bairro"):
        local.bairro = achado["bairro"]
    local.save(update_fields=["cidade", "uf", "ibge", "logradouro", "bairro", "atualizado_em"])
    return True


# ---------------------------------------------------------------------------
# Vizinhança — "o que está perto de quê"
# ---------------------------------------------------------------------------
def proximos(queryset, ponto, raio_km: float):
    """Locais dentro do raio, do mais perto ao mais longe, com `distancia_m`.

    `ST_DWithin` sobre `geography` (o GeoDjango o escolhe sozinho porque o campo
    é geodésico) — ou seja, o filtro roda no índice GiST, e não em Python. É a
    diferença entre responder "fornecedores num raio de 50 km" em milissegundos
    e varrer a tabela inteira.
    """
    from django.contrib.gis.db.models.functions import Distance
    from django.contrib.gis.measure import D

    return (
        queryset.filter(ponto__isnull=False, ponto__distance_lte=(ponto, D(km=raio_km)))
        .annotate(distancia=Distance("ponto", ponto))
        .order_by("distancia")
    )


def distancias_ate_obra(tenant_id, obra_id, fornecedor_ids) -> dict:
    """`{fornecedor_id: km}` entre a obra e cada fornecedor — o seam do SCM.

    É o que acrescenta **distância** ao mapa comparativo de propostas, que até
    aqui decidia só por preço e reputação. Frete e prazo de entrega saem daqui:
    o fornecedor 3% mais caro a 12 km costuma ganhar do 3% mais barato a 300.

    Devolve `{}` quando a obra não tem coordenada, e omite o fornecedor que não
    tem — nunca um zero. Distância ausente significa "não sei", e a tela mostra
    "—"; um zero seria lido como "está na esquina".
    """
    destino = Local.objects.filter(
        tenant_id=tenant_id, obra_id=obra_id, ponto__isnull=False
    ).first()
    if destino is None:
        return {}
    origens = Local.objects.filter(
        tenant_id=tenant_id, fornecedor_id__in=list(fornecedor_ids), ponto__isnull=False
    ).only("fornecedor_id", "ponto")
    return {
        origem.fornecedor_id: round(
            distancia_m(destino.ponto.x, destino.ponto.y, origem.ponto.x, origem.ponto.y) / 1000, 1
        )
        for origem in origens
    }


# ---------------------------------------------------------------------------
# Geofence
# ---------------------------------------------------------------------------
def poligono_do_raio(ponto, raio_m: int, lados: int = 36):
    """Círculo aproximado em torno de um ponto, em SRID 4326.

    O raio é convertido em graus com a correção de latitude (o grau de longitude
    encurta com o cosseno) em vez de reprojetar para UTM: 36 lados são
    suficientes para uma cerca de canteiro, e a alternativa traria de volta o
    problema de fuso que o SRID único existe para evitar.
    """
    from django.contrib.gis.geos import LinearRing, Polygon

    graus_lat = raio_m / 111_320.0
    cos_lat = max(0.01, math.cos(math.radians(ponto.y)))
    graus_lon = graus_lat / cos_lat

    vertices = [
        (
            ponto.x + graus_lon * math.cos(2 * math.pi * i / lados),
            ponto.y + graus_lat * math.sin(2 * math.pi * i / lados),
        )
        for i in range(lados)
    ]
    vertices.append(vertices[0])  # anel fechado
    return Polygon(LinearRing(vertices), srid=4326)


def gerar_geofence(local: Local, nome: str, tipo: str, raio_m: int | None = None) -> Geofence:
    """Cerca a partir do Local: usa o perímetro real se houver; senão, o raio.

    A ordem importa — quem já desenhou o canteiro tem o polígono certo, e um
    círculo por cima dele seria uma imprecisão gratuita.
    """
    if local.area is not None and raio_m is None:
        area, raio = local.area, None
    else:
        if local.ponto is None:
            raise ValueError("O local não tem coordenada: geocodifique-o antes de criar a cerca.")
        raio = raio_m or 150
        area = poligono_do_raio(local.ponto, raio)

    cerca, _ = Geofence.objects.update_or_create(
        tenant_id=local.tenant_id,
        nome=nome,
        defaults={"local": local, "tipo": tipo, "area": area, "raio_m": raio, "ativo": True},
    )
    return cerca


def dentro_da_cerca(tenant_id, lon: float, lat: float):
    """Cercas ativas que contêm o ponto. É o gancho de ponto por geolocalização
    (RH) e de foto do diário — os dois consumidores vivem em outros módulos."""
    from django.contrib.gis.geos import Point

    return Geofence.objects.filter(
        tenant_id=tenant_id, ativo=True, area__contains=Point(lon, lat, srid=4326)
    )


# ---------------------------------------------------------------------------
# Sincronização com as entidades de cadastro
# ---------------------------------------------------------------------------
# Cada entrada diz: campo do Local ← entidade. É o que o backfill percorre e o
# que o `sincronizar` usa quando alguém cadastra uma obra nova.
VINCULOS = {
    Local.Tipo.OBRA: {
        "modelo": "obras.Obra",
        "nome": lambda o: o.nome_obra,
        "endereco": lambda o: o.endereco or "",
    },
    Local.Tipo.EMPREENDIMENTO: {
        "modelo": "empreendimentos.Empreendimento",
        "nome": lambda e: e.empreendimento,
        "endereco": lambda e: e.endereco or "",
        "cidade": lambda e: e.cidade or "",
        "uf": lambda e: e.estado or "",
    },
    Local.Tipo.FORNECEDOR: {
        "modelo": "fornecedores.Fornecedor",
        "nome": lambda f: f.razao_social,
        "endereco": lambda _f: "",  # fornecedor não tem endereço estruturado hoje
    },
    Local.Tipo.LOCAL_ESTOQUE: {
        "modelo": "modulosil.LocalEstoque",
        "nome": lambda l: l.nome,
        "endereco": lambda l: l.endereco or "",
    },
    # A unidade imobiliária — o lote, o apartamento. É o **único** vínculo cujo
    # endereço pode ser deduzido de outro campo: quando `Unidade.endereco` está
    # vazio, a frente do lote (`confrontante_frente`) é a rua, e é ela que o
    # comprador usa para chegar lá. Deduzir daí é o que tira do mapa um pin
    # "QD 4 · LT 06" sem nenhuma pista de onde isso fica.
    Local.Tipo.UNIDADE: {
        "modelo": "empreendimentos.Unidade",
        "nome": lambda u: (
            f"{u.empreendimento.empreendimento} — {u.rotulo}"
            if u.empreendimento_id else u.rotulo
        ),
        "endereco": lambda u: u.endereco or u.confrontante_frente or "",
        "cidade": lambda u: (u.empreendimento.cidade or "") if u.empreendimento_id else "",
        "uf": lambda u: (u.empreendimento.estado or "") if u.empreendimento_id else "",
    },
}


# ---------------------------------------------------------------------------
# Coerência entre o endereço e a divisa da frente
# ---------------------------------------------------------------------------
#: O que só diz **que tipo** de logradouro é, e nunca **qual**. Some dos dois
#: lados da comparação: "R. das Acácias" e "Rua das Acácias" são a mesma rua, e
#: a diferença entre elas é ruído de quem digitou, não divergência de cadastro.
_TIPOS_DE_LOGRADOURO = {
    "r", "rua", "av", "avenida", "al", "alameda", "tv", "travessa", "rod",
    "rodovia", "pc", "pca", "praca", "est", "estrada", "lgo", "largo",
}
#: Palavras de ligação — "das Acácias" e "de Acácias" não podem virar ruas
#: diferentes por causa do artigo.
_LIGACOES = {"de", "da", "do", "das", "dos", "e"}


def _sem_ruido(texto: str) -> str:
    """O nome da rua reduzido às palavras que a identificam.

    Tira acento, caixa, pontuação, o tipo do logradouro e os artigos — o que
    sobra de "R. das Acácias, 120 — Centro" é "acacias 120 centro", e o que
    sobra de "Rua das Acácias" é "acacias". É o suficiente para reconhecer que
    as duas falam da mesma rua sem exigir que alguém tenha digitado igual nos
    dois cadastros, que é coisa que nunca acontece.
    """
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    palavras = re.split(r"[^a-z0-9]+", sem_acento.lower())
    return " ".join(
        p for p in palavras if p and p not in _TIPOS_DE_LOGRADOURO and p not in _LIGACOES
    )


def rua_confere(unidade, local=None) -> bool | None:
    """A frente do lote bate com o endereço cadastrado?

    `True` bate, `False` diverge, **`None` não dá para dizer** — e o `None` é o
    valor que mais importa. Sem confrontante de frente, ou sem endereço, não há
    comparação a fazer: responder `False` acusaria de errado um cadastro que
    apenas está incompleto, e responder `True` daria por conferido o que ninguém
    conferiu.

    A comparação é por **conteúdo**: basta que um texto contenha o outro depois
    de tirar acento, pontuação e a abreviatura do logradouro ("R.", "Av."). O
    endereço costuma trazer número e complemento que o memorial não tem, e exigir
    igualdade literal acusaria divergência em todo cadastro correto.
    """
    frente = _sem_ruido(getattr(unidade, "confrontante_frente", ""))
    if not frente:
        return None
    candidatos = [getattr(unidade, "endereco", "") or ""]
    if local is not None:
        candidatos += [local.logradouro or "", local.endereco_formatado() or ""]
    candidatos = [_sem_ruido(c) for c in candidatos if _sem_ruido(c)]
    if not candidatos:
        return None
    return any(frente in c or c in frente for c in candidatos)


def sincronizar_local(entidade, tipo: str, tenant_id=None) -> Local:
    """Cria (ou atualiza) o `Local` de uma entidade a partir do endereço dela.

    Idempotente: rodar de novo não duplica nem apaga o que o usuário ajustou —
    o `update_or_create` só mexe no nome e no endereço textual, nunca no `ponto`
    (que é justamente o que a pessoa arrastou).
    """
    regra = VINCULOS[tipo]
    tenant_id = tenant_id or entidade.tenant_id
    texto = regra["endereco"](entidade)

    local, criado = Local.objects.update_or_create(
        tenant_id=tenant_id,
        **{tipo: entidade},
        defaults={"tipo": tipo, "nome": regra["nome"](entidade)},
    )
    if criado or not local.logradouro:
        # Endereço da v01 é texto livre num campo só. Quebrá-lo é melhor-esforço:
        # o que a cascata reconhecer vira campo estruturado, o resto continua
        # legível em `logradouro`. Não descartamos o texto original.
        local.logradouro = local.logradouro or texto[:255]
        if "cidade" in regra:
            local.cidade = local.cidade or regra["cidade"](entidade)
        if "uf" in regra:
            local.uf = local.uf or (regra["uf"](entidade) or "").upper()[:2]
        local.save(update_fields=["logradouro", "cidade", "uf", "atualizado_em"])
    return local
