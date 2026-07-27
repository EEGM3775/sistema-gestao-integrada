# backend/modulomaps/rotas.py
"""MAP.2 — traçado e ordenação de rota de suprimento.

Duas responsabilidades separadas de propósito:

- **Traçar** (`tracar`) é geometria de rua e vem de fora: OSRM self-host. Sem
  motor configurado, o traçado é a reta entre as paradas e a rota inteira sai
  carimbada `procedencia=estimada` — número aproximado que se declara aproximado
  é útil (dá ordem de grandeza da entrega); número aproximado que se passa por
  rota de rua faz o comprador prometer prazo que não cumpre.
- **Ordenar** (`otimizar`) é combinatória e roda aqui dentro.

**Sobre o otimizador.** A planta previa OR-Tools. O que MAP.2 entrega é um
problema menor do que aquilo resolve: **um** veículo, sem capacidade, saindo de
uma origem fixa — um TSP aberto de dezenas de paradas. Para esse porte,
vizinho-mais-próximo + 2-opt chega ao ótimo ou a fração de por cento dele, em
milissegundos e sem acrescentar ~100 MB de dependência nativa à imagem e ao CI.
OR-Tools volta quando entrarem **capacidade, frota e janela dura** — aí o
problema vira VRPTW de verdade e heurística de troca de pares não basta. A
decisão está registrada em docs/modulos/modulomaps.md §9.

Janela de horário: as paradas têm janela, e o otimizador **não a viola em
silêncio**. Ele ordena por tempo de viagem e devolve, junto, as violações que a
ordem produziu — quem decide remanejar é o operador, com a informação na tela.
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings

from .services import distancia_m

logger = logging.getLogger(__name__)

# Velocidade média para estimar duração quando não há motor de rota. 40 km/h é
# entrega urbana com paradas; deliberadamente conservadora — estimativa que
# promete pouco e cumpre é melhor que a otimista.
VELOCIDADE_ESTIMADA_MS = 40_000 / 3600


def _osrm(caminho: str, coordenadas, params=None):
    """Chamada ao OSRM. `None` quando não há motor ou ele falhou."""
    base = getattr(settings, "OSRM_URL", "")
    if not base or len(coordenadas) < 2:
        return None
    pares = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coordenadas)
    url = f"{base.rstrip('/')}/{caminho}/v1/driving/{pares}"
    try:
        resp = requests.get(url, params=params or {}, timeout=getattr(settings, "GEO_TIMEOUT", (5, 15)))
        resp.raise_for_status()
        dados = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("OSRM falhou (%s): %s", url, e)
        return None
    return dados if dados.get("code") == "Ok" else None


def matriz_duracao(coordenadas) -> list[list[float]]:
    """Matriz tempo-a-tempo (segundos) entre todas as coordenadas.

    Do OSRM `/table` quando há motor; senão, haversine ÷ velocidade média. A
    matriz é o insumo do otimizador — e é por isso que ordenar funciona mesmo
    sem OSRM: a ordem relativa entre paradas próximas e distantes se mantém.
    """
    dados = _osrm("table", coordenadas, {"annotations": "duration"})
    if dados and dados.get("durations"):
        return dados["durations"]
    n = len(coordenadas)
    return [
        [
            0.0 if i == j else distancia_m(*coordenadas[i], *coordenadas[j]) / VELOCIDADE_ESTIMADA_MS
            for j in range(n)
        ]
        for i in range(n)
    ]


def tracar(coordenadas):
    """Geometria + distância + duração da rota, na ordem dada.

    Devolve `(LineString, distancia_m, duracao_s, procedencia)`.
    """
    from django.contrib.gis.geos import LineString

    dados = _osrm("route", coordenadas, {"overview": "full", "geometries": "geojson"})
    if dados and dados.get("routes"):
        rota = dados["routes"][0]
        pontos = rota["geometry"]["coordinates"]
        return (
            LineString([(p[0], p[1]) for p in pontos], srid=4326),
            float(rota.get("distance") or 0),
            int(rota.get("duration") or 0),
            "osrm",
        )

    # Fallback declarado: reta entre paradas.
    metros = sum(
        distancia_m(*coordenadas[i], *coordenadas[i + 1]) for i in range(len(coordenadas) - 1)
    )
    linha = LineString([(lon, lat) for lon, lat in coordenadas], srid=4326)
    return linha, metros, int(metros / VELOCIDADE_ESTIMADA_MS), "estimada"


def _vizinho_mais_proximo(matriz) -> list[int]:
    """Ordem inicial: da origem (índice 0), sempre para a parada mais próxima."""
    n = len(matriz)
    ordem, restantes = [0], set(range(1, n))
    while restantes:
        atual = ordem[-1]
        proximo = min(restantes, key=lambda j: matriz[atual][j])
        ordem.append(proximo)
        restantes.discard(proximo)
    return ordem


def _duas_opt(ordem: list[int], matriz) -> list[int]:
    """2-opt: desfaz cruzamentos invertendo trechos enquanto houver ganho.

    A origem (posição 0) fica fixa — é de onde o caminhão sai, não uma parada
    negociável. Rota aberta: não se soma o retorno à origem.
    """
    def custo(seq):
        return sum(matriz[seq[i]][seq[i + 1]] for i in range(len(seq) - 1))

    melhor, melhor_custo = ordem[:], custo(ordem)
    houve_ganho = True
    while houve_ganho:
        houve_ganho = False
        for i in range(1, len(melhor) - 1):
            for j in range(i + 1, len(melhor)):
                candidato = melhor[:i] + melhor[i:j + 1][::-1] + melhor[j + 1:]
                c = custo(candidato)
                if c < melhor_custo - 1e-9:
                    melhor, melhor_custo, houve_ganho = candidato, c, True
    return melhor


def otimizar(coordenadas) -> tuple[list[int], list[float]]:
    """Melhor ordem de visita a partir da origem (índice 0).

    Devolve `(ordem, chegadas_em_segundos)` — a chegada acumulada é o que
    permite confrontar a ordem com as janelas de horário sem refazer a conta na
    view.
    """
    if len(coordenadas) <= 2:
        indices = list(range(len(coordenadas)))
        if len(coordenadas) < 2:
            return indices, [0.0] * len(indices)
        matriz = matriz_duracao(coordenadas)
        return indices, [0.0, matriz[0][1]]

    matriz = matriz_duracao(coordenadas)
    ordem = _duas_opt(_vizinho_mais_proximo(matriz), matriz)

    chegadas, acumulado = [0.0], 0.0
    for i in range(len(ordem) - 1):
        acumulado += matriz[ordem[i]][ordem[i + 1]]
        chegadas.append(acumulado)
    return ordem, chegadas


def violacoes_de_janela(paradas, chegadas_s, partida_hora=None) -> list[dict]:
    """Paradas cuja chegada estimada cai fora da janela declarada.

    Existe porque o otimizador é de tempo de viagem, não de janela: entregar o
    número sem dizer que ele fura a janela do canteiro das 7h às 11h seria
    esconder o único dado que faz o operador remanejar.
    """
    from datetime import datetime, time, timedelta

    base = datetime.combine(datetime.today(), partida_hora or time(8, 0))
    problemas = []
    for parada, chegada_s in zip(paradas, chegadas_s):
        if not (parada.janela_inicio or parada.janela_fim):
            continue
        chegada = (base + timedelta(seconds=float(chegada_s))).time()
        if parada.janela_inicio and chegada < parada.janela_inicio:
            problemas.append({
                "parada": parada.pk, "local": parada.local_id, "chegada": chegada.isoformat(),
                "motivo": f"chega antes da janela ({parada.janela_inicio:%H:%M})",
            })
        elif parada.janela_fim and chegada > parada.janela_fim:
            problemas.append({
                "parada": parada.pk, "local": parada.local_id, "chegada": chegada.isoformat(),
                "motivo": f"chega depois da janela ({parada.janela_fim:%H:%M})",
            })
    return problemas
