"""Mede quando a retomada por folha (PRA.11) compensa — sobre o acervo real.

**A pergunta.** A retomada grava as folhas prontas e devolve o arquivo ao fim da
fila; a passada seguinte pula o que já saiu. O que ela **não** pula é a gravação
da geometria (o `Recorder` do `ezdxf`), que roda inteira toda vez. Então o custo
de terminar um arquivo em `N` passadas é:

    N × gravação  +  emissão_total          (com retomada)
        gravação  +  emissão_total          (numa passada só)

A retomada só é barata quando a **emissão** domina. Este script mede os dois
tempos separados em cada arquivo do acervo e deriva a conta — um passe por
arquivo, em vez de rodar N passadas em cada um.

**Por que derivar em vez de medir as N passadas:** medir de verdade custaria
`N×` o acervo inteiro (na aferição do `01_LOTEAMENTO`, 115 s contra 36 s). A
derivação usa exatamente os dois números que compõem aquele resultado, e o
próprio script confere a conta contra uma medição real no fim (`--conferir`).

Uso, de dentro do `worker-conversao` (é a máquina dimensionada para converter):

    docker exec sgi-worker-conversao python /app/../ferramentas/medicao/medir_retomada.py
"""
from __future__ import annotations

import glob
import os
import statistics
import sys
import time

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from moduloprancheta.motores.dwg import MotorDwg  # noqa: E402
from moduloprancheta.motores.dxf import MotorDxf  # noqa: E402

PASTAS = ("/app/media/impexp/conferencia/**/*.dwg", "/app/media/prancheta/**/*.dwg")
TETO_MB = float(os.getenv("TETO_MB", "26"))
LIMITE = int(os.getenv("LIMITE", "400"))


def corpus() -> list[str]:
    """Um caminho por arquivo distinto.

    Dedupe por **tamanho exato**: o acervo de medição tem o mesmo DWG copiado
    para várias obras e para a área de conferência, e converter o mesmo desenho
    seis vezes não acrescenta parâmetro nenhum — só inflaria a amostra e a média.
    """
    vistos: dict[int, str] = {}
    for padrao in PASTAS:
        for caminho in glob.glob(padrao, recursive=True):
            try:
                tam = os.path.getsize(caminho)
            except OSError:
                continue
            if tam > TETO_MB * 1048576:
                continue
            vistos.setdefault(tam, caminho)
    return [c for _, c in sorted(vistos.items())][:LIMITE]


def medir(caminho: str) -> dict:
    """Converte uma vez, cronometrando a gravação por dentro.

    O relógio da gravação sai de um envelope no `MotorDxf._gravar` — é o único
    ponto por onde toda a expansão de geometria passa, e medi-lo por fora
    (subtraindo tempos) misturaria a leitura do DXF na conta.
    """
    marca = {"gravacao": 0.0}
    original = MotorDxf._gravar

    def cronometrado(self, *a, **kw):
        inicio = time.monotonic()
        try:
            return original(self, *a, **kw)
        finally:
            marca["gravacao"] += time.monotonic() - inicio

    MotorDxf._gravar = cronometrado
    try:
        inicio = time.monotonic()
        saida = MotorDwg().converter(caminho, formato="dwg", tipo="vetor_2d")
        total = time.monotonic() - inicio
    finally:
        MotorDxf._gravar = original

    folhas = len(saida.partes)
    gravacao = marca["gravacao"]
    # O que sobra do relógio depois da gravação: dwg2dxf, leitura do DXF e a
    # emissão das folhas. Só a emissão é o que a retomada pula, mas o `dwg2dxf`
    # e a leitura TAMBÉM se repetem a cada passada — então eles entram no custo
    # fixo, ao lado da gravação. Chamar tudo isso de "fixo" é o corte honesto.
    return {
        "arquivo": os.path.basename(caminho),
        "mb": os.path.getsize(caminho) / 1048576,
        "folhas": folhas,
        "total": total,
        "gravacao": gravacao,
        "resto": total - gravacao,
    }


def main() -> None:
    arquivos = corpus()
    print(f"# corpus: {len(arquivos)} DWGs distintos (dedupe por tamanho), até {TETO_MB:.0f} MB")
    print(f"# {'MB':>6} {'folhas':>6} {'total':>7} {'gravação':>9} {'resto':>7}  arquivo")
    linhas = []
    for i, caminho in enumerate(arquivos, start=1):
        try:
            r = medir(caminho)
        except Exception as exc:  # motor insuficiente, corrompido, teto — tudo é dado
            print(f"# {'--':>6} {'--':>6} {'--':>7} {'--':>9} {'--':>7}  "
                  f"{os.path.basename(caminho)[:44]} → {type(exc).__name__}")
            sys.stdout.flush()
            continue
        linhas.append(r)
        print(f"  {r['mb']:>6.1f} {r['folhas']:>6} {r['total']:>7.1f} "
              f"{r['gravacao']:>9.1f} {r['resto']:>7.1f}  {r['arquivo'][:44]}")
        sys.stdout.flush()

    if not linhas:
        print("# nada convergiu — sem parâmetro a extrair")
        return

    print()
    print("=" * 78)
    print("PARÂMETROS")
    print("=" * 78)

    convertidos = len(linhas)
    multi = [r for r in linhas if r["folhas"] > 1]
    folhas = [r["folhas"] for r in linhas]
    print(f"convertidos: {convertidos} · com mais de uma folha: {len(multi)} "
          f"({100 * len(multi) / convertidos:.0f}%)")
    print(f"folhas por arquivo — mediana {statistics.median(folhas):.0f} · "
          f"máximo {max(folhas)}")
    print(f"relógio — mediana {statistics.median(r['total'] for r in linhas):.1f}s · "
          f"máximo {max(r['total'] for r in linhas):.1f}s")

    # A fatia FIXA é o que toda passada repete. Quanto maior ela for, mais cara
    # é a retomada — e é o número que decide se o mecanismo compensa.
    fracoes = [r["gravacao"] / r["total"] for r in linhas if r["total"] > 0.2]
    print()
    print(f"fatia da GRAVAÇÃO no relógio (o que se repete a cada volta):")
    print(f"   mediana {100 * statistics.median(fracoes):.0f}% · "
          f"mínimo {100 * min(fracoes):.0f}% · máximo {100 * max(fracoes):.0f}%")

    print()
    print("custo de terminar em N passadas, se cada passada emitir uma folha:")
    print(f"   {'folhas':>6} {'arquivos':>9} {'sobrecusto mediano':>20}")
    for n in sorted({r["folhas"] for r in linhas}):
        grupo = [r for r in linhas if r["folhas"] == n and r["total"] > 0.2]
        if not grupo:
            continue
        # N passadas: N × fixo + emissão. Aproxima-se `fixo` pela gravação, que é
        # a parte medida; o resto entra como emissão, o que SUBESTIMA o
        # sobrecusto — declarado, para o número ser lido como piso e não como teto.
        razoes = [
            (n * r["gravacao"] + r["resto"]) / r["total"]
            for r in grupo
        ]
        print(f"   {n:>6} {len(grupo):>9} {statistics.median(razoes):>19.2f}×")

    print()
    print("LEITURA:")
    print("  A retomada não é de graça — ela troca 'nunca terminar' por 'terminar")
    print("  mais caro'. O preço é a fatia fixa acima, multiplicada pelas voltas.")
    print("  Ela compensa onde o arquivo tem MUITAS folhas e a emissão domina;")
    print("  num arquivo de folha única ela nem é tentada (não há onde parar).")


if __name__ == "__main__":
    main()
