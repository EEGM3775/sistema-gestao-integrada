"""O índice de snap descreve o desenho que está na tela? — a bancada do D90.

**Existe porque pixel não se afere no olho, e três tentativas de conserto
falharam por diagnóstico aritmético.** As hipóteses eram plausíveis, calculáveis
e erradas; o que fechou o caso foi comparar o sidecar com o SVG **que saiu**, e
não com uma folha deduzida. Esta bancada faz isso em Python puro, sem navegador —
é o passo 2 e o passo 4 da receita do D90 num comando só, e é o teste mais barato
que existe para a pergunta "a mira gruda no traço?".

A `verificar_snap.mjs` ao lado responde a mesma coisa **pela tela**, com
`getScreenCTM()` do navegador de verdade; use-a quando a suspeita for da
transformação do frontend. Quando a suspeita for do backend — o caso do D90 —,
esta aqui responde em segundos e não precisa de contêiner de Playwright.

O que ela mede, por folha:

1. **onde o índice cai em relação ao traço** — distância de cada ponto do sidecar
   ao segmento de `<path>` mais próximo, em pixels de tela a 81× (o zoom do
   relato original). Mediana perto de zero e ~95% abaixo de 1 px é o estado bom;
2. **de onde vêm os pontos** — quanto é geometria que se mede (reta, arco,
   polilinha) e quanto é preenchimento (hachura, sólido, texto em contorno), que
   é o que enche o índice e disputa o teto do plano;
3. **o que a folha custou** — pontos, bytes de sidecar e se o teto cortou.

**A comparação é com o traço, não com o nó do `<path>`**, e a diferença não é
detalhe: o índice guarda vértice de curva achatada, que fica *entre* dois nós por
construção. Medindo contra nós, um índice perfeito acusa vários pixels de erro e
a bancada mente para o lado que dói — dizendo que há defeito onde não há.

Uso, dentro do contêiner que tem o `ezdxf`:

    docker exec sgi-worker-conversao python /app/../ferramentas/medicao/conferir_snap.py \
        /app/media/prancheta/<tenant>/obra-12/001.dwg

    # ou o acervo inteiro, com amostra por folha:
    docker exec sgi-worker-conversao sh -c 'cd /app && python conferir_snap.py \
        media/prancheta/*/obra-12/*.dwg'
"""
from __future__ import annotations

import argparse
import math
import os
import re
import statistics
import struct
import sys

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from moduloprancheta.motores import dxf as mdxf  # noqa: E402
from moduloprancheta.motores import snap as snapmod  # noqa: E402

#: Largura da folha na tela, em pixels, no enquadramento "ajustar à tela". É o
#: que converte desvio normalizado em pixel; 1128 é uma janela de trabalho comum.
#: Só muda a unidade do relatório, nunca o veredito.
LARGURA_AJUSTE_PX = 1128

#: O zoom do relato original do D90 — "a 81× a borda de baixo do quadrado do snap
#: alinha com a linha". Medir aqui é medir na régua de quem reportou.
ZOOM = 81

#: Abaixo disto o ponto está **sobre** o traço: menos de um pixel a 81× é menos
#: que a espessura da linha que ele deveria medir.
SOBRE_O_TRACO_PX = 1.0

#: Subdivisões por bezier ao achatar os `<path>` do SVG. Oito é folgado: o erro
#: da corda fica muito abaixo da própria quantização inteira do arquivo.
SUBDIVISOES = 8

#: Lado da célula da grade de busca, em fração da largura da folha.
LADO_DA_CELULA = 1.0 / 256

#: Segmento cuja caixa cobre mais células que isto não entra na grade — é a
#: diagonal que atravessa a folha, e indexá-la custaria mais que o resto junto.
#: Declarado porque **é uma amostra incompleta**, e amostra silenciosa mente.
TETO_DE_CELULAS = 4096

_NUMERO = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
_PATHS = re.compile(r'<path\b[^>]*\bd="([^"]*)"')
_COMANDOS = re.compile(r"([MmLlHhVvCcQqSsTtAaZz])([^MmLlHhVvCcQqSsTtAaZz]*)")
_VIEWBOX = re.compile(r'viewBox="0 0 ([\d.]+) ([\d.]+)"')

_ARGUMENTOS = {"M": 2, "L": 2, "T": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "A": 7}


def segmentos_do_svg(texto: str) -> list[tuple[float, float, float, float]]:
    """Todo `<path>` do SVG como lista de segmentos de reta.

    O `SVGBackend` abre cada subcaminho com um `M` **absoluto** e segue em
    comandos **relativos**. Somar os números aos pares, como se fossem todos
    coordenadas, lê `l -785937 0` como um ponto em x = −785.937 — foi assim que a
    primeira versão desta bancada inventou uma folha que ia a menos um milhão.
    """
    segmentos: list[tuple[float, float, float, float]] = []
    for d in _PATHS.findall(texto):
        x = y = inicio_x = inicio_y = 0.0
        for comando, resto in _COMANDOS.findall(d):
            numeros = [float(v) for v in _NUMERO.findall(resto)]
            relativo, letra = comando.islower(), comando.upper()

            if letra == "Z":
                if (x, y) != (inicio_x, inicio_y):
                    segmentos.append((x, y, inicio_x, inicio_y))
                x, y = inicio_x, inicio_y
                continue

            passo = _ARGUMENTOS[letra]
            for i in range(0, len(numeros) - passo + 1, passo):
                a = numeros[i:i + passo]
                if letra in ("M", "L", "T"):
                    nx, ny = (x + a[0], y + a[1]) if relativo else (a[0], a[1])
                    if letra == "M" and i == 0:
                        inicio_x, inicio_y = nx, ny
                    else:
                        segmentos.append((x, y, nx, ny))
                    x, y = nx, ny
                elif letra == "H":
                    nx = x + a[0] if relativo else a[0]
                    segmentos.append((x, y, nx, y))
                    x = nx
                elif letra == "V":
                    ny = y + a[0] if relativo else a[0]
                    segmentos.append((x, y, x, ny))
                    y = ny
                elif letra in ("Q", "C"):
                    x, y = _achatar_bezier(segmentos, x, y, a, relativo)
                else:
                    # `S`, `T` e `A` pela corda. Aparecem raro no que o `ezdxf`
                    # emite, e aproximá-los erra para o lado seguro: a corda fica
                    # DENTRO da curva, então a distância medida sai maior que a
                    # real e a bancada acusa defeito a mais, nunca a menos.
                    nx, ny = (x + a[-2], y + a[-1]) if relativo else (a[-2], a[-1])
                    segmentos.append((x, y, nx, ny))
                    x, y = nx, ny
    return segmentos


def _achatar_bezier(segmentos, x, y, a, relativo):
    pontos = [(x, y)]
    for k in range(0, len(a), 2):
        px, py = a[k], a[k + 1]
        pontos.append((x + px, y + py) if relativo else (px, py))

    ax, ay = x, y
    for passo in range(1, SUBDIVISOES + 1):
        t = passo / SUBDIVISOES
        u = 1 - t
        if len(pontos) == 3:  # quadrática
            bx = u * u * pontos[0][0] + 2 * u * t * pontos[1][0] + t * t * pontos[2][0]
            by = u * u * pontos[0][1] + 2 * u * t * pontos[1][1] + t * t * pontos[2][1]
        else:  # cúbica
            bx = (u ** 3 * pontos[0][0] + 3 * u * u * t * pontos[1][0]
                  + 3 * u * t * t * pontos[2][0] + t ** 3 * pontos[3][0])
            by = (u ** 3 * pontos[0][1] + 3 * u * u * t * pontos[1][1]
                  + 3 * u * t * t * pontos[2][1] + t ** 3 * pontos[3][1])
        segmentos.append((ax, ay, bx, by))
        ax, ay = bx, by
    return ax, ay


def pontos_do_sidecar(octetos: bytes) -> list[tuple[float, float, int]]:
    """Lê o sidecar como o navegador lê (formato em `motores/snap.py::empacotar`)."""
    if octetos[:5] != b"SNAP1":
        return []
    n = struct.unpack_from("<I", octetos, 5)[0]
    if not n:
        return []
    xs = struct.unpack_from(f"<{n}f", octetos, 14)
    ys = struct.unpack_from(f"<{n}f", octetos, 14 + 4 * n)
    tipos = octetos[14 + 8 * n:14 + 9 * n]
    return list(zip(xs, ys, tipos))


def _distancia_ao_segmento(px, py, x1, y1, x2, y2) -> float:
    dx, dy = x2 - x1, y2 - y1
    comprimento2 = dx * dx + dy * dy
    if not comprimento2:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / comprimento2
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return math.hypot(x1 + t * dx - px, y1 + t * dy - py)


def _grade(segmentos):
    grade: dict[tuple[int, int], list] = {}
    ignorados = 0
    for s in segmentos:
        cx1 = int(min(s[0], s[2]) // LADO_DA_CELULA)
        cy1 = int(min(s[1], s[3]) // LADO_DA_CELULA)
        cx2 = int(max(s[0], s[2]) // LADO_DA_CELULA)
        cy2 = int(max(s[1], s[3]) // LADO_DA_CELULA)
        if (cx2 - cx1 + 1) * (cy2 - cy1 + 1) > TETO_DE_CELULAS:
            ignorados += 1
            continue
        for cx in range(cx1, cx2 + 1):
            for cy in range(cy1, cy2 + 1):
                grade.setdefault((cx, cy), []).append(s)
    return grade, ignorados


def conferir(caminho: str, *, teto: int, amostra: int) -> None:
    from moduloprancheta.motores.dwg import MotorDwg

    partes: list = []
    original = mdxf.MotorDxf._folha

    def espia(self, player, grupo, **kw):
        parte = original(self, player, grupo, **kw)
        partes.append(parte)
        return parte

    eh_dwg = caminho.lower().endswith(".dwg")
    motor = MotorDwg() if eh_dwg else mdxf.MotorDxf()
    mdxf.MotorDxf._folha = espia
    try:
        motor.converter(caminho, formato="dwg" if eh_dwg else "dxf",
                        tipo="vetor_2d", teto_snap=teto)
    finally:
        mdxf.MotorDxf._folha = original

    for i, parte in enumerate(partes):
        rotulo = f"  folha {i}"
        if not parte.snap:
            print(f"{rotulo}: sem sidecar ({parte.detalhe.get('snap_erro', '—')})")
            continue

        texto = parte.conteudo.decode("utf-8", "replace")
        caixa = _VIEWBOX.search(texto)
        if not caixa:
            print(f"{rotulo}: SVG sem viewBox")
            continue
        vbw = float(caixa.group(1))

        segmentos = [(a / vbw, b / vbw, c / vbw, d / vbw)
                     for a, b, c, d in segmentos_do_svg(texto)]
        if not segmentos:
            print(f"{rotulo}: o SVG não desenha nada")
            continue

        grade, ignorados = _grade(segmentos)
        pontos = pontos_do_sidecar(parte.snap)
        passo = max(1, len(pontos) // amostra)
        conferidos = pontos[::passo]

        distancias = []
        for px, py, _tipo in conferidos:
            cx, cy = int(px // LADO_DA_CELULA), int(py // LADO_DA_CELULA)
            melhor = math.inf
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for s in grade.get((cx + dx, cy + dy), ()):
                        melhor = min(melhor, _distancia_ao_segmento(px, py, *s))
            if melhor < math.inf:
                distancias.append(melhor * LARGURA_AJUSTE_PX * ZOOM)

        if not distancias:
            print(f"{rotulo}: nenhum ponto perto de traço nenhum — o índice não "
                  f"descreve esta folha")
            continue

        distancias.sort()
        sobre = sum(1 for d in distancias if d < SOBRE_O_TRACO_PX) / len(distancias)
        print(
            f"{rotulo}: {len(pontos):>7d} pontos"
            f" | {len(conferidos)} conferidos"
            f" | mediana {statistics.median(distancias):5.2f} px"
            f" | p90 {distancias[int(len(distancias) * 0.9)]:6.2f} px"
            f" | {sobre * 100:5.1f}% sobre o traço"
            f" | sidecar {len(parte.snap) / 1048576:5.2f} MB"
            f"{' | TRUNCADO' if parte.snap_truncado else ''}"
        )
        if parte.detalhe.get("snap_fora_da_folha"):
            print(f"{' ' * 10}⚠ {parte.detalhe['snap_fora_da_folha']} pontos caíram "
                  f"fora da folha — o ezdxf não põe geometria fora da página que "
                  f"ele mesmo dimensionou; isto é espaço de coordenada errado (D90)")
        if ignorados:
            print(f"{' ' * 10}({ignorados} segmentos longos ficaram fora da grade "
                  f"de busca; podem inflar a cauda das distâncias)")


def principal(argv=None) -> int:
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument("desenhos", nargs="+", help="arquivos DWG ou DXF")
    analisador.add_argument("--teto", type=int, default=600_000,
                            help="teto de pontos do plano (padrão: Profissional)")
    analisador.add_argument("--amostra", type=int, default=400,
                            help="quantos pontos conferir por folha")
    opcoes = analisador.parse_args(argv)

    for caminho in opcoes.desenhos:
        print(f"\n{os.path.basename(caminho)}")
        try:
            conferir(caminho, teto=opcoes.teto, amostra=opcoes.amostra)
        except Exception as exc:  # a bancada não pode parar no arquivo ruim
            print(f"  falhou: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
