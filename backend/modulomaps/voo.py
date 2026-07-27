# backend/modulomaps/voo.py
"""MAP.4 — cálculo do plano de voo e exportação para os formatos de campo.

**A conta que ninguém deveria digitar à mão.** Altura e GSD não são dois campos
independentes: eles se determinam pela geometria da câmera. Deixar o operador
digitar os dois é o erro clássico do setor — o voo sai com resolução diferente
da prometida e isso só aparece semanas depois, no processamento, quando revoar
custa uma diária de equipe.

    GSD = (altura × largura_do_sensor) / (focal × largura_da_imagem)
    ⇒ altura = GSD × focal × largura_da_imagem / largura_do_sensor

O cálculo roda num **plano métrico local** (equirretangular em torno do
centroide da área), não em graus: espaçamento de linha em graus daria faixas de
largura diferente conforme a latitude, e a sobreposição — que é o que garante o
processamento fechar — deixaria de ser a pedida. A área é pequena (um canteiro),
então o erro da aproximação é de centímetros.

Exportação: **KML** (visualização/prova), **MAVLink `.plan`** (QGroundControl,
padrão aberto), **Litchi CSV** e **DJI WPML/KMZ** (Pilot 2). São quatro porque
não existe um: cada fabricante lê o seu, e o plano que não embarca no drone da
empresa não serve para nada.
"""
from __future__ import annotations

import io
import json
import math
import zipfile
from decimal import Decimal

# Metros por grau. Latitude é praticamente constante; longitude encurta com o
# cosseno da latitude — é a correção que faz o grid ficar quadrado no chão.
M_POR_GRAU_LAT = 110_540.0
M_POR_GRAU_LON = 111_320.0


# ---------------------------------------------------------------------------
# Plano métrico local
# ---------------------------------------------------------------------------
class PlanoLocal:
    """Conversor ida-e-volta entre (lon, lat) e metros em torno de uma origem."""

    def __init__(self, lon0: float, lat0: float):
        self.lon0, self.lat0 = lon0, lat0
        self.escala_lon = M_POR_GRAU_LON * math.cos(math.radians(lat0))

    def para_m(self, lon, lat):
        return (lon - self.lon0) * self.escala_lon, (lat - self.lat0) * M_POR_GRAU_LAT

    def para_graus(self, x, y):
        return self.lon0 + x / self.escala_lon, self.lat0 + y / M_POR_GRAU_LAT


def _girar(x, y, rad):
    return x * math.cos(rad) - y * math.sin(rad), x * math.sin(rad) + y * math.cos(rad)


# ---------------------------------------------------------------------------
# Fotogrametria
# ---------------------------------------------------------------------------
def altura_para_gsd(gsd_cm, focal_mm, largura_px, sensor_mm) -> float:
    """Altura de voo (m) que entrega o GSD pedido com aquela câmera."""
    gsd_m = float(gsd_cm) / 100.0
    return gsd_m * float(focal_mm) * float(largura_px) / float(sensor_mm)


def pegada(gsd_cm, largura_px, altura_px) -> tuple[float, float]:
    """Área coberta por uma foto, em metros (largura, altura)."""
    gsd_m = float(gsd_cm) / 100.0
    return gsd_m * float(largura_px), gsd_m * float(altura_px)


def parametros(plano) -> dict:
    """Altura, espaçamento entre linhas e distância entre fotos.

    O espaçamento sai da **sobreposição lateral** (entre faixas vizinhas) e o
    intervalo entre disparos, da **frontal** (ao longo da faixa). Trocar as duas
    é o engano mais comum, e produz um voo que parece certo e não fecha.
    """
    altura = altura_para_gsd(
        plano.gsd_alvo_cm, plano.distancia_focal_mm, plano.imagem_largura_px, plano.sensor_largura_mm
    )
    largura_m, altura_foto_m = pegada(plano.gsd_alvo_cm, plano.imagem_largura_px, plano.imagem_altura_px)
    espacamento = largura_m * (1 - plano.sobreposicao_lateral_pct / 100.0)
    intervalo = altura_foto_m * (1 - plano.sobreposicao_frontal_pct / 100.0)
    return {
        "altura_m": altura,
        "espacamento_m": max(1.0, espacamento),
        "intervalo_foto_m": max(0.5, intervalo),
        "pegada_m": (largura_m, altura_foto_m),
    }


# ---------------------------------------------------------------------------
# Geração do traçado
# ---------------------------------------------------------------------------
def _segmentos_do_grid(anel_m, espacamento, angulo_graus):
    """Linhas paralelas cobrindo o polígono, em ida-e-volta (*boustrophedon*).

    O recorte contra o polígono é feito pelo GEOS (`intersection`), não à mão:
    área com reentrância ou buraco produz vários trechos por linha, e um
    clipping caseiro erraria exatamente nesses casos — que são os do mundo real
    (canteiro em L, área com lagoa no meio).
    """
    from django.contrib.gis.geos import LineString, LinearRing, Polygon

    rad = math.radians(angulo_graus)
    girados = [_girar(x, y, -rad) for x, y in anel_m]
    poligono = Polygon(LinearRing(girados + [girados[0]]))

    xs = [p[0] for p in girados]
    ys = [p[1] for p in girados]
    margem = espacamento
    x_min, x_max = min(xs) - margem, max(xs) + margem
    y = min(ys) + espacamento / 2

    faixas, invertida = [], False
    while y <= max(ys):
        recorte = LineString([(x_min, y), (x_max, y)]).intersection(poligono)
        trechos = []
        if recorte and not recorte.empty:
            if recorte.geom_type == "LineString":
                trechos = [list(recorte.coords)]
            elif recorte.geom_type in ("MultiLineString", "GeometryCollection"):
                trechos = [list(g.coords) for g in recorte if g.geom_type == "LineString"]
        for trecho in trechos:
            pontos = sorted(trecho, key=lambda p: p[0])
            if invertida:
                pontos = list(reversed(pontos))
            faixas.append(pontos)
        invertida = not invertida
        y += espacamento

    return [[_girar(x, yy, rad) for x, yy in faixa] for faixa in faixas]


def _orbital(anel_m, espacamento):
    """Círculo em torno do centroide, raio = metade da maior dimensão."""
    xs = [p[0] for p in anel_m]
    ys = [p[1] for p in anel_m]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    raio = max(max(xs) - min(xs), max(ys) - min(ys)) / 2 or espacamento
    lados = max(12, int(2 * math.pi * raio / max(espacamento, 5)))
    return [[(cx + raio * math.cos(2 * math.pi * i / lados),
              cy + raio * math.sin(2 * math.pi * i / lados)) for i in range(lados + 1)]]


def _corredor(anel_m):
    """Eixo longitudinal da área — o par de vértices mais distante entre si.

    É o suficiente para faixa de duto, estrada ou canal, que é onde o corredor
    se usa. Eixo curvo (poliline de projeto) entra quando houver traçado de
    projeto importado: aí o corredor deixa de ser derivado e passa a ser dado.
    """
    melhor, melhor_d = (anel_m[0], anel_m[-1]), -1.0
    for i, a in enumerate(anel_m):
        for b in anel_m[i + 1:]:
            d = (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
            if d > melhor_d:
                melhor, melhor_d = (a, b), d
    return [[melhor[0], melhor[1]]]


def calcular(plano) -> dict:
    """Traçado + waypoints + estimativas do plano. Não persiste — quem chama grava.

    Devolve `linha` (LineString 4326), `waypoints`, `distancia_m`,
    `duracao_min`, `fotos_estimadas` e `altura_m`.
    """
    from django.contrib.gis.geos import LineString

    p = parametros(plano)
    anel = list(plano.area.exterior_ring.coords)
    centro = plano.area.centroid
    local = PlanoLocal(centro.x, centro.y)
    anel_m = [local.para_m(lon, lat) for lon, lat in anel[:-1]]

    if plano.tipo == plano.Tipo.PERIMETRO:
        faixas = [anel_m + [anel_m[0]]]
    elif plano.tipo == plano.Tipo.ORBITAL:
        faixas = _orbital(anel_m, p["espacamento_m"])
    elif plano.tipo == plano.Tipo.CORREDOR:
        faixas = _corredor(anel_m)
    elif plano.tipo == plano.Tipo.DUPLO_GRID:
        faixas = (_segmentos_do_grid(anel_m, p["espacamento_m"], plano.angulo_graus)
                  + _segmentos_do_grid(anel_m, p["espacamento_m"], plano.angulo_graus + 90))
    else:
        faixas = _segmentos_do_grid(anel_m, p["espacamento_m"], plano.angulo_graus)

    pontos_m = [ponto for faixa in faixas for ponto in faixa]
    if len(pontos_m) < 2:
        raise ValueError(
            "A área é pequena demais para o espaçamento calculado: aumente o GSD alvo "
            "ou reduza a sobreposição lateral."
        )

    coords = [local.para_graus(x, y) for x, y in pontos_m]
    distancia = sum(
        math.dist(pontos_m[i], pontos_m[i + 1]) for i in range(len(pontos_m) - 1)
    )
    velocidade = float(plano.velocidade_ms) or 8.0
    waypoints = [
        {
            "ordem": i,
            "lon": round(lon, 7),
            "lat": round(lat, 7),
            "altura_m": round(p["altura_m"], 1),
            "velocidade_ms": velocidade,
            # Rumo do trecho: no grid o gimbal aponta para baixo e a câmera segue
            # a linha; o heading evita a foto girada a cada virada de faixa.
            "heading": _rumo(coords, i),
        }
        for i, (lon, lat) in enumerate(coords)
    ]

    return {
        "linha": LineString(coords, srid=4326),
        "waypoints": waypoints,
        "distancia_m": round(distancia, 1),
        # +25% de folga: subida, descida, curvas e vento não estão no comprimento
        # da linha. Prometer o tempo teórico faz a equipe perder a janela do dia.
        "duracao_min": round(distancia / velocidade / 60 * 1.25, 1),
        "fotos_estimadas": int(distancia / p["intervalo_foto_m"]) + len(faixas),
        "altura_m": round(p["altura_m"], 1),
        "espacamento_m": round(p["espacamento_m"], 1),
        "intervalo_foto_m": round(p["intervalo_foto_m"], 1),
    }


def _rumo(coords, i) -> int:
    """Azimute (graus) do ponto i para o seguinte; o último herda o anterior."""
    if len(coords) < 2:
        return 0
    a, b = (coords[i], coords[i + 1]) if i < len(coords) - 1 else (coords[i - 1], coords[i])
    dx = (b[0] - a[0]) * math.cos(math.radians(a[1]))
    dy = b[1] - a[1]
    return int((math.degrees(math.atan2(dx, dy)) + 360) % 360)


# ---------------------------------------------------------------------------
# Exportação — um formato por ecossistema de campo
# ---------------------------------------------------------------------------
def para_kml(plano) -> bytes:
    """KML — o formato que qualquer um abre (Google Earth, QGIS) para conferir."""
    pontos = plano.waypoints or []
    linha = " ".join(f"{w['lon']},{w['lat']},{w['altura_m']}" for w in pontos)
    area = " ".join(f"{lon},{lat},0" for lon, lat in plano.area.exterior_ring.coords)
    marcas = "".join(
        f"<Placemark><name>{w['ordem'] + 1}</name><Point>"
        f"<coordinates>{w['lon']},{w['lat']},{w['altura_m']}</coordinates>"
        f"</Point></Placemark>"
        for w in pontos
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<name>{_xml(plano.nome)}</name>"
        f"<Placemark><name>Área</name><Polygon><outerBoundaryIs><LinearRing>"
        f"<coordinates>{area}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
        f"<Placemark><name>Rota</name><LineString><altitudeMode>relativeToGround</altitudeMode>"
        f"<coordinates>{linha}</coordinates></LineString></Placemark>"
        f"{marcas}"
        "</Document></kml>"
    ).encode("utf-8")


def para_mavlink(plano) -> bytes:
    """`.plan` do QGroundControl — padrão aberto (MAVLink), lido por ArduPilot/PX4."""
    pontos = plano.waypoints or []
    primeiro = pontos[0] if pontos else {"lat": 0, "lon": 0, "altura_m": 0}
    itens = [
        {
            "AMSLAltAboveTerrain": None,
            "Altitude": w["altura_m"],
            "AltitudeMode": 1,  # relativo ao ponto de decolagem
            "autoContinue": True,
            "command": 16,  # MAV_CMD_NAV_WAYPOINT
            "doJumpId": i + 1,
            "frame": 3,  # GLOBAL_RELATIVE_ALT
            "params": [0, 0, 0, None, w["lat"], w["lon"], w["altura_m"]],
            "type": "SimpleItem",
        }
        for i, w in enumerate(pontos)
    ]
    plano_json = {
        "fileType": "Plan",
        "geoFence": {"circles": [], "polygons": [], "version": 2},
        "groundStation": "SGI Plataforma",
        "mission": {
            "cruiseSpeed": float(plano.velocidade_ms),
            "firmwareType": 12,
            "hoverSpeed": 5,
            "items": itens,
            "plannedHomePosition": [primeiro["lat"], primeiro["lon"], 0],
            "vehicleType": 2,
            "version": 2,
        },
        "rallyPoints": {"points": [], "version": 2},
        "version": 1,
    }
    return json.dumps(plano_json, indent=2).encode("utf-8")


def para_litchi(plano) -> bytes:
    """CSV do Litchi (Mission Hub) — o caminho de quem voa DJI sem o Pilot 2."""
    cabecalho = (
        "latitude,longitude,altitude(m),heading(deg),curvesize(m),rotationdir,gimbalmode,"
        "gimbalpitchangle,actiontype1,actionparam1,altitudemode,speed(m/s),"
        "poi_latitude,poi_longitude,poi_altitude(m),poi_altitudemode,"
        "photo_timeinterval,photo_distinterval"
    )
    linhas = [cabecalho]
    for w in plano.waypoints or []:
        linhas.append(
            f"{w['lat']:.7f},{w['lon']:.7f},{w['altura_m']:.1f},{w['heading']},0,0,2,-90,"
            f"-1,0,1,{w['velocidade_ms']:.1f},0,0,0,0,-1,-1"
        )
    return ("\r\n".join(linhas) + "\r\n").encode("utf-8")


def para_wpml(plano) -> bytes:
    """KMZ no padrão **WPML** da DJI (Pilot 2 / M300, M350, Mavic 3E).

    O arquivo é um zip com `wpmz/template.kml` (a intenção do voo) e
    `wpmz/waylines.wpml` (as linhas executáveis). Gerar só um dos dois produz um
    arquivo que o Pilot abre e recusa — foi o que motivou empacotar os dois.
    """
    pontos = plano.waypoints or []
    altura = pontos[0]["altura_m"] if pontos else 100

    def _pontos_xml(tag_indice: str) -> str:
        return "".join(
            f'<Placemark><Point><coordinates>{w["lon"]},{w["lat"]}</coordinates></Point>'
            f"<{tag_indice}>{w['ordem']}</{tag_indice}>"
            f"<wpml:executeHeight>{w['altura_m']}</wpml:executeHeight>"
            f"<wpml:waypointSpeed>{w['velocidade_ms']}</wpml:waypointSpeed>"
            f'<wpml:waypointHeadingParam><wpml:waypointHeadingMode>followWayline'
            f"</wpml:waypointHeadingMode></wpml:waypointHeadingParam>"
            f"<wpml:waypointTurnParam><wpml:waypointTurnMode>toPointAndStopWithContinuityCurvature"
            f"</wpml:waypointTurnMode><wpml:waypointTurnDampingDist>0</wpml:waypointTurnDampingDist>"
            f"</wpml:waypointTurnParam></Placemark>"
            for w in pontos
        )

    cabecalho = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="http://www.dji.com/wpmz/1.0.2">'
        "<Document>"
        "<wpml:missionConfig>"
        "<wpml:flyToWaylineMode>safely</wpml:flyToWaylineMode>"
        "<wpml:finishAction>goHome</wpml:finishAction>"
        "<wpml:exitOnRCLost>executeLostAction</wpml:exitOnRCLost>"
        "<wpml:executeRCLostAction>goBack</wpml:executeRCLostAction>"
        f"<wpml:takeOffSecurityHeight>{altura}</wpml:takeOffSecurityHeight>"
        "<wpml:globalTransitionalSpeed>%s</wpml:globalTransitionalSpeed>"
        "<wpml:droneInfo><wpml:droneEnumValue>68</wpml:droneEnumValue>"
        "<wpml:droneSubEnumValue>0</wpml:droneSubEnumValue></wpml:droneInfo>"
        "</wpml:missionConfig>"
    ) % float(plano.velocidade_ms)

    template = (
        cabecalho
        + f"<Folder><wpml:templateType>waypoint</wpml:templateType>"
        f"<wpml:templateId>0</wpml:templateId>"
        f"<wpml:autoFlightSpeed>{float(plano.velocidade_ms)}</wpml:autoFlightSpeed>"
        f"<name>{_xml(plano.nome)}</name>"
        + _pontos_xml("wpml:index")
        + "</Folder></Document></kml>"
    )
    waylines = (
        cabecalho
        + f"<Folder><wpml:templateId>0</wpml:templateId><wpml:waylineId>0</wpml:waylineId>"
        f"<wpml:autoFlightSpeed>{float(plano.velocidade_ms)}</wpml:autoFlightSpeed>"
        + _pontos_xml("wpml:index")
        + "</Folder></Document></kml>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("wpmz/template.kml", template)
        z.writestr("wpmz/waylines.wpml", waylines)
    return buffer.getvalue()


FORMATOS = {
    "kml": (para_kml, "application/vnd.google-earth.kml+xml", "kml"),
    "plan": (para_mavlink, "application/json", "plan"),
    "litchi": (para_litchi, "text/csv", "csv"),
    "wpml": (para_wpml, "application/vnd.google-earth.kmz", "kmz"),
}


def _xml(texto) -> str:
    """Escapa o mínimo para não quebrar o KML com um nome de obra com `&`."""
    if isinstance(texto, Decimal):
        return str(texto)
    return (
        str(texto or "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )
