"""O custo REAL da retomada, medido nos arquivos que têm mais de uma folha.

**Por que existe uma segunda passada de medição.** A primeira
([medir_retomada.py](medir_retomada.py)) cronometrou a *gravação* da geometria e
tratou todo o resto do relógio como emissão de folha — o que faria a retomada
custar 1,35× num arquivo de 4 folhas. A aferição direta do
`01_LOTEAMENTO_PORTAL_RESIDENCE` deu **3,20×**. A diferença é o `dwg2dxf` e a
leitura do DXF, que **também** rodam inteiros a cada volta e não estavam na conta.

Aqui a medição é exata e do outro lado: cronometra-se a **emissão** (`_folha`,
que é o único trabalho que a retomada pula) e o custo fixo sai por subtração —
`fixo = total − emissão`. Com isso:

    N passadas = N × fixo + emissão_total
    1 passada  =     fixo + emissão_total

Só os arquivos com mais de uma folha entram: no de folha única não há onde parar,
o pipeline nem oferece prazo, e incluí-los só diluiria a mediana com 1,00×.
"""
from __future__ import annotations

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


def medir(caminho: str) -> dict | None:
    """Converte uma vez, cronometrando só a emissão de folha."""
    marca = {"emissao": 0.0, "folhas": 0}
    original = MotorDxf._folha

    def cronometrado(self, *a, **kw):
        inicio = time.monotonic()
        try:
            return original(self, *a, **kw)
        finally:
            marca["emissao"] += time.monotonic() - inicio
            marca["folhas"] += 1

    MotorDxf._folha = cronometrado
    try:
        inicio = time.monotonic()
        saida = MotorDwg().converter(caminho, formato="dwg", tipo="vetor_2d")
        total = time.monotonic() - inicio
    except Exception as exc:
        print(f"  -- {type(exc).__name__}: {os.path.basename(caminho)[:40]}")
        return None
    finally:
        MotorDxf._folha = original

    n = len(saida.partes)
    if n < 2:
        return None
    emissao = marca["emissao"]
    fixo = total - emissao
    return {
        "arquivo": os.path.basename(caminho),
        "mb": os.path.getsize(caminho) / 1048576,
        "folhas": n,
        "total": total,
        "fixo": fixo,
        "emissao": emissao,
        # O que custa terminar em N passadas emitindo uma folha por vez.
        "sobrecusto": (n * fixo + emissao) / total if total > 0 else 0,
    }


def main() -> None:
    alvos = [l.strip() for l in sys.stdin if l.strip()]
    print(f"# {len(alvos)} arquivos com mais de uma folha")
    print(f"# {'MB':>6} {'folhas':>6} {'total':>7} {'fixo':>7} {'emissão':>8} "
          f"{'fixo%':>6} {'N passadas':>11}  arquivo")
    linhas = []
    for caminho in alvos:
        r = medir(caminho)
        if r is None:
            continue
        linhas.append(r)
        print(f"  {r['mb']:>6.1f} {r['folhas']:>6} {r['total']:>7.1f} {r['fixo']:>7.1f} "
              f"{r['emissao']:>8.1f} {100 * r['fixo'] / r['total']:>5.0f}% "
              f"{r['sobrecusto']:>10.2f}×  {r['arquivo'][:40]}")
        sys.stdout.flush()

    if not linhas:
        print("# nenhum arquivo multi-folha convergiu")
        return

    print()
    print("=" * 78)
    print("PARÂMETROS — só arquivos multi-folha (onde a retomada existe)")
    print("=" * 78)
    fixos = [r["fixo"] / r["total"] for r in linhas]
    custos = [r["sobrecusto"] for r in linhas]
    print(f"arquivos: {len(linhas)} · folhas: mediana "
          f"{statistics.median(r['folhas'] for r in linhas):.0f}, "
          f"máximo {max(r['folhas'] for r in linhas)}")
    print()
    print(f"CUSTO FIXO (repete a cada volta: dwg2dxf + leitura + gravação)")
    print(f"   mediana {100 * statistics.median(fixos):.0f}% do relógio · "
          f"mínimo {100 * min(fixos):.0f}% · máximo {100 * max(fixos):.0f}%")
    print()
    print(f"EMISSÃO DE FOLHA (o único trabalho que a retomada pula)")
    print(f"   mediana {100 * (1 - statistics.median(fixos)):.0f}% do relógio")
    print()
    print(f"SOBRECUSTO de terminar uma folha por passada")
    print(f"   mediana {statistics.median(custos):.2f}× · "
          f"mínimo {min(custos):.2f}× · máximo {max(custos):.2f}×")
    print()
    print("   por número de folhas:")
    for n in sorted({r["folhas"] for r in linhas}):
        g = [r["sobrecusto"] for r in linhas if r["folhas"] == n]
        print(f"      {n} folhas · {len(g):>2} arquivo(s) · mediana {statistics.median(g):.2f}×")

    print()
    print("LEITURA")
    print("  O trabalho que a retomada pula é a MENOR parte do relógio. Ela não")
    print("  economiza: ela troca 'nunca terminar' por 'terminar mais caro', e o")
    print("  preço é o custo fixo multiplicado pelas voltas. Isso é aceitável")
    print("  porque a alternativa era o arquivo não sair — mas diz onde o próximo")
    print("  ganho está: baratear o custo FIXO (o `dwg2SVG` da PRA.1e), não")
    print("  picar mais fino.")


if __name__ == "__main__":
    main()
