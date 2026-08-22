# backend/moduloprancheta/motores/hachura.py
"""Hachura desenhada **como hachura** — contorno mais padrão, não milhões de traços.

**O defeito que este módulo corrige.** Um DWG guarda a hachura como *declaração*:
"preencha este contorno com o padrão X, na escala Y, a partir deste ponto". São
algumas centenas de bytes, e o AutoCAD nunca os expande — ele pinta o padrão
recortado pelo contorno na hora de rasterizar, com custo proporcional aos
**pixels na tela**. O nosso caminho fazia o oposto: o `draw_hatch_pattern` do
`ezdxf` materializa cada passada do padrão sobre a área inteira, em coordenadas
de mundo, antes de saber que pedaço vai aparecer. A conta é *área ÷ espaçamento*
— duas grandezas que o tamanho do arquivo não limita.

Medido em 12/08/2026 sobre o acervo real: um DWG de **1,0 MB** com 83 hachuras
custava **1,7 GB**, e cinco arquivos de 1 a 9,6 MB matavam um contêiner de 3 GB
na política fiel. O contorno dos mesmos desenhos tem **8 a 22 comandos de
caminho**. Ver a planta, §4.1.

**Por que o SVG resolve isto sem aproximar.** Uma família de linhas de padrão DXF
é um **reticulado**: linhas paralelas a uma direção, repetidas a cada vetor de
deslocamento, com um tracejado que se repete ao longo da linha. Ou seja, uma
malha gerada por dois vetores. O `<pattern>` do SVG ladrilha um retângulo e
aceita um `patternTransform` **afim arbitrário** — e é exatamente essa a matriz
que leva o quadrado unitário no paralelogramo do reticulado. Não há
arredondamento nem amostragem no meio: o que se emite é a mesma definição que
estava no arquivo, e quem expande é o rasterizador do navegador, com o custo
limitado pela tela.

**O deslocamento não é perpendicular, e isso importa.** Num padrão `_USER` ele é
(o desenho só declara espaçamento), mas os padrões de arquitetura escalonam as
linhas — o `AR-SAND` do acervo tem componente ao longo da própria linha. Um
`<pattern>` montado com largura e altura separadas erraria justamente esses; a
matriz do reticulado acerta os dois casos pelo mesmo caminho, porque *stagger* é
só um vetor não-ortogonal.

**Limite declarado:** famílias sem deslocamento (reticulado degenerado) e padrões
que o `ezdxf` não resolve voltam para a expansão antiga, que continua no lugar
como caminho de escape. Nada aqui remove a escada do orçamento — ela vira rede.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from xml.etree import ElementTree as ET

#: Abaixo disto o reticulado é degenerado (duas linhas sobrepostas, ou
#: deslocamento nulo) e não define ladrilho nenhum. Relativo ao próprio
#: reticulado, não absoluto: um desenho em UTM e outro em milímetros têm ordens
#: de grandeza diferentes, e um piso fixo reprovaria um dos dois.
_DEGENERADO = 1e-9

#: A linha é desenhada no **meio** do ladrilho, não na borda. O conteúdo de um
#: `<pattern>` é recortado pelo retângulo do ladrilho: uma linha em `y=0` teria
#: metade da espessura cortada, e o padrão sairia mais claro do que é. Meio
#: ladrilho de deslocamento é devolvido na translação, para a fase não mudar.
_MEIO = 0.5


@dataclass(frozen=True)
class Familia:
    """Uma família de linhas paralelas do padrão, já resolvida em coordenadas
    do desenho (o `ezdxf` entrega escala e rotação do `HATCH` já aplicadas).

    `passo` é o vetor entre duas linhas vizinhas — **não** necessariamente
    perpendicular à direção; `ciclo` é o comprimento do tracejado ao longo da
    linha, que é o segundo gerador do reticulado.
    """

    direcao: tuple[float, float]
    passo: tuple[float, float]
    base: tuple[float, float]
    tracos: tuple[float, ...]
    ciclo: float


def capturar(polygon) -> tuple[Familia, ...] | None:
    """A definição do padrão do `HATCH`, ou `None` quando não dá para ladrilhar.

    `None` é resposta boa e tem um único destino: o chamador expande do jeito
    antigo. Preferimos desenhar caro a desenhar errado.
    """
    padrao = getattr(polygon, "pattern", None)
    linhas = getattr(padrao, "lines", None) if padrao is not None else None
    if not linhas:
        return None

    familias: list[Familia] = []
    for linha in linhas:
        try:
            angulo = math.radians(float(linha.angle))
            passo = (float(linha.offset.x), float(linha.offset.y))
            base = (float(linha.base_point.x), float(linha.base_point.y))
            tracos = tuple(float(t) for t in (linha.dash_length_items or ()))
        except (AttributeError, TypeError, ValueError):
            return None

        if math.hypot(*passo) <= _DEGENERADO:
            return None  # sem deslocamento não há ladrilho — deixa expandir

        ciclo = sum(abs(t) for t in tracos)
        if ciclo <= _DEGENERADO:
            # Linha contínua: qualquer período serve como gerador ao longo da
            # linha. O do próprio deslocamento mantém o ladrilho bem
            # condicionado (nem agulha, nem panqueca), que é o que faz a
            # espessura de traço no espaço do padrão continuar legível.
            tracos, ciclo = (), math.hypot(*passo)

        familias.append(Familia(
            direcao=(math.cos(angulo), math.sin(angulo)),
            passo=passo, base=base, tracos=tracos, ciclo=ciclo,
        ))
    return tuple(familias)


def _reticulado(familia: Familia, matriz):
    """Os dois geradores e a origem, levados ao espaço de saída da folha.

    A geometria gravada já foi transformada pelo `Player.transform` antes da
    reprodução; o padrão precisa atravessar **a mesma** matriz, senão o
    preenchimento anda em relação ao contorno que ele preenche.
    """
    from ezdxf.math import Vec3

    def direcao(v):
        r = matriz.transform_direction(Vec3(v[0], v[1], 0))
        return (r.x, r.y)

    def ponto(v):
        r = matriz.transform(Vec3(v[0], v[1], 0))
        return (r.x, r.y)

    u = direcao((familia.direcao[0] * familia.ciclo, familia.direcao[1] * familia.ciclo))
    v = direcao(familia.passo)
    b = ponto(familia.base)

    # Área do paralelogramo: é ela que dá a distância real entre linhas depois
    # da transformação, e é zero exatamente quando o ladrilho não existe.
    area = abs(u[0] * v[1] - u[1] * v[0])
    if area <= _DEGENERADO or math.hypot(*u) <= _DEGENERADO:
        return None
    return u, v, b, area


def _tracos_do_ladrilho(familia: Familia) -> list[tuple[float, float]]:
    """O tracejado em fração do ladrilho — `[(inicio, fim), …]` dentro de [0, 1].

    Item positivo é traço, negativo é vão e **zero é ponto** (a convenção do
    `.pat`). O ponto vira um segmento curtíssimo porque `stroke-linecap` aqui é
    `butt`: com `round` ele viraria uma bolha do tamanho da espessura, e o
    padrão pontilhado de concreto ficaria uma mancha.
    """
    if not familia.tracos:
        return [(0.0, 1.0)]

    marcas: list[tuple[float, float]] = []
    posicao = 0.0
    ponto = familia.ciclo / 1000.0
    for item in familia.tracos:
        comprimento = abs(item)
        if item > 0:
            marcas.append((posicao / familia.ciclo,
                           (posicao + comprimento) / familia.ciclo))
        elif item == 0:
            marcas.append((posicao / familia.ciclo,
                           (posicao + ponto) / familia.ciclo))
        posicao += comprimento
    return marcas


def elemento(familias, matriz, *, ident: str, cor: str, espessura: float):
    """O `<pattern>` pronto, ou `None` se alguma família não ladrilhar.

    Uma família por `<g>` dentro do mesmo ladrilho não serve — cada uma tem o
    seu próprio reticulado —, então o elemento devolvido é o da **primeira** e
    as demais saem em elementos irmãos, empilhados pelo chamador. É por isso que
    a função devolve uma lista.
    """
    elementos: list[ET.Element] = []
    for indice, familia in enumerate(familias):
        montado = _reticulado(familia, matriz)
        if montado is None:
            return None
        u, v, b, area = montado

        # A espessura é dada no espaço da folha; dentro do ladrilho o eixo `y`
        # vale `v`, então a mesma espessura em unidades de padrão é a fração da
        # distância REAL entre linhas — que é a área do paralelogramo dividida
        # pela base. Sem esta conversão o traço engrossaria ou sumiria conforme
        # a escala do padrão, que é o defeito mais visível de todos.
        largura_padrao = espessura * math.hypot(*u) / area
        # Traço mais grosso que o vão entre linhas fecharia a área num bloco
        # sólido — a tarja preta do D46 pela porta dos fundos.
        largura_padrao = min(largura_padrao, 0.5)

        padrao = ET.Element("pattern", {
            "id": ident if indice == 0 else f"{ident}-{indice}",
            "patternUnits": "userSpaceOnUse",
            "width": "1", "height": "1",
            # O quadrado unitário vai no paralelogramo do reticulado. A
            # translação desconta meio deslocamento porque a linha é desenhada
            # no meio do ladrilho (ver `_MEIO`).
            "patternTransform": (
                f"matrix({u[0]:.6g},{u[1]:.6g},{v[0]:.6g},{v[1]:.6g},"
                f"{b[0] - _MEIO * v[0]:.6g},{b[1] - _MEIO * v[1]:.6g})"
            ),
        })
        desenho = " ".join(
            f"M{inicio:.6g},{_MEIO} L{fim:.6g},{_MEIO}"
            for inicio, fim in _tracos_do_ladrilho(familia)
        )
        ET.SubElement(padrao, "path", {
            "d": desenho, "fill": "none", "stroke": cor,
            "stroke-width": f"{largura_padrao:.6g}",
            "stroke-linecap": "butt",
        })
        elementos.append(padrao)
    return elementos


def chave(familias, cor: str, espessura: float):
    """Identidade do padrão, para dois `HATCH` iguais dividirem um `<pattern>`.

    Um desenho com 1.400 hachuras costuma ter uma dúzia de padrões distintos; a
    deduplicação é o que impede o `<defs>` de virar o novo custo.
    """
    return (cor, round(espessura, 6), tuple(
        (f.direcao, f.passo, f.base, f.tracos, round(f.ciclo, 9))
        for f in familias
    ))
