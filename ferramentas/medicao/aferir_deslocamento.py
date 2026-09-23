#!/usr/bin/env python3
"""Afere o **deslocamento dos símbolos** do `dwg2SVG` sobre um acervo de DWGs.

Pergunta do dono (15/09/2026): *"Pranchetas tem uma função de deslocamento,
testar vários dwg para saber se esse deslocamento tá certo."*

A correção (`svg_do_motor.deslocamento_dos_simbolos`) foi derivada e conferida
sobre **um** arquivo de referência, em 10/08/2026. Ela decide, símbolo a símbolo,
entre duas interpretações — crua e deslocada — ficando com a que cai mais perto
da origem, e o docstring afirma que *"a diferença é de seis ordens de grandeza —
não há empate a arbitrar"*. Este script põe as duas afirmações à prova num
acervo real:

1. **O deslocamento é derivável?** O `viewBox` existe e é legível em todo arquivo?
2. **A decisão é inequívoca?** Para cada símbolo, mede-se a distância à origem
   nas duas interpretações. Razão perto de 1 é EMPATE: ali a escolha é sorteio,
   e um símbolo sorteado errado vai para milhões de unidades de distância.
3. **O resultado presta?** Que fração da geometria de topo cai dentro do
   `viewBox` que o próprio arquivo declara, antes e depois da correção.

Uso (dentro de um container que tenha `dwg2SVG` e o código do backend):

    python aferir_deslocamento.py /acervo [--teto-segundos 120] [--limite N]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app")

from moduloprancheta.motores.svg_do_motor import (  # noqa: E402
    _ELEMENTO,
    _caixa_do_elemento,
    _caixa_do_simbolo,
    _mover,
    _longe_de_zero,
    _partir_documento,
    _trecho_completo,
    deslocamento_dos_simbolos,
    folhas,
)
import re  # noqa: E402

#: Acima disto as duas interpretações são de ordens de grandeza diferentes e a
#: escolha é óbvia — que é exatamente o que o docstring afirma. Abaixo, não.
RAZAO_INEQUIVOCA = 10.0


def viewbox(svg: bytes):
    achado = re.search(rb'viewBox="([^"]+)"', svg[:4096])
    if not achado:
        return None
    try:
        x0, y0, largura, altura = (float(n) for n in achado.group(1).split())
    except ValueError:
        return None
    return x0, y0, largura, altura


def dentro(caixa, vb) -> bool:
    """O centro da caixa cai dentro do `viewBox` declarado?"""
    x0, y0, largura, altura = vb
    cx = (caixa[0] + caixa[2]) / 2
    cy = (caixa[1] + caixa[3]) / 2
    return x0 <= cx <= x0 + largura and y0 <= cy <= y0 + altura


def aferir(caminho: Path, teto: int) -> dict:
    inicio = time.monotonic()
    try:
        proc = subprocess.run(
            ["dwg2SVG", str(caminho)],
            capture_output=True, timeout=teto, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"arquivo": str(caminho), "veredito": "estourou o relógio"}
    if proc.returncode != 0 or not proc.stdout:
        return {"arquivo": str(caminho), "veredito": "motor não converteu"}

    svg = proc.stdout
    vb = viewbox(svg)
    desloc = deslocamento_dos_simbolos(svg)
    corpo, _defs, simbolos = _partir_documento(svg)

    # --- 2. a decisão por símbolo é inequívoca? -----------------------------
    cache_cru: dict = {}
    empates, graves, deslocados, locais, ambiguidade_min = 0, 0, 0, 0, None
    pior_grave = 0.0
    # A escala do desenho: um empate a 2 unidades é inofensivo; o mesmo empate a
    # 4 milhões põe o bloco fora do mundo. Sem esta régua os dois se confundem.
    escala = max(vb[2], vb[3]) if vb else max(abs(desloc[0]), abs(desloc[1]), 1.0)
    for nome in simbolos:
        crua = _caixa_do_simbolo(nome, simbolos, cache_cru, 0, (0.0, 0.0))
        if crua is None:
            continue
        movida = _mover(crua, desloc)
        d_crua, d_movida = _longe_de_zero(crua), _longe_de_zero(movida)
        perto, longe = sorted((d_crua, d_movida))
        if d_movida < d_crua:
            deslocados += 1
        else:
            locais += 1
        razao = (longe / perto) if perto > 1e-9 else float("inf")
        if razao < RAZAO_INEQUIVOCA:
            empates += 1
            # **Grave = a escolha é sorteio E o erro sairia caro.** Mesmo a
            # interpretação vencedora deixa o símbolo a mais de 1% da folha da
            # origem: ali as duas respostas são "longe", e a que perdeu está a
            # uma distância da mesma ordem — é onde o critério não decide nada.
            if perto > escala * 0.01:
                graves += 1
                pior_grave = max(pior_grave, perto)
        if ambiguidade_min is None or razao < ambiguidade_min:
            ambiguidade_min = razao

    # --- 3. a geometria cai dentro do viewBox? ------------------------------
    antes = depois = total = 0
    if vb:
        cache_corrigido: dict = {}
        for achado in _ELEMENTO.finditer(corpo):
            tag = achado.group(1).lower()
            trecho, atributos = _trecho_completo(corpo, achado.start(), tag)
            if trecho is None:
                continue
            crua, _ = _caixa_do_elemento(tag, atributos, trecho, simbolos, cache_cru, (0.0, 0.0))
            corrigida, _ = _caixa_do_elemento(
                tag, atributos, trecho, simbolos, cache_corrigido, desloc,
            )
            if crua is None or corrigida is None:
                continue
            total += 1
            antes += dentro(crua, vb)
            depois += dentro(corrigida, vb)

    partes, truncados = folhas(svg)
    return {
        "arquivo": str(caminho),
        "veredito": "ok",
        "segundos": round(time.monotonic() - inicio, 1),
        "viewbox": bool(vb),
        "desloc_x": round(desloc[0], 3),
        "desloc_y": round(desloc[1], 3),
        "simbolos": len(simbolos),
        "deslocados": deslocados,
        "ja_locais": locais,
        "empates": empates,
        "graves": graves,
        "pior_grave": round(pior_grave, 1),
        "razao_minima": None if ambiguidade_min is None else round(min(ambiguidade_min, 1e9), 2),
        "elementos": total,
        "dentro_antes_pct": round(100 * antes / total, 1) if total else None,
        "dentro_depois_pct": round(100 * depois / total, 1) if total else None,
        "folhas": len(partes),
        "truncados": truncados,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("acervo")
    ap.add_argument("--teto-segundos", type=int, default=120)
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--saida", default="")
    args = ap.parse_args()

    arquivos = sorted(
        p for p in Path(args.acervo).rglob("*")
        if p.is_file() and p.suffix.lower() == ".dwg"
    )
    if args.limite:
        arquivos = arquivos[: args.limite]

    linhas = []
    for i, caminho in enumerate(arquivos, 1):
        linha = aferir(caminho, args.teto_segundos)
        linhas.append(linha)
        nome = caminho.name[:44]
        if linha["veredito"] != "ok":
            print(f"[{i}/{len(arquivos)}] {nome:<44} {linha['veredito']}", flush=True)
        else:
            print(
                f"[{i}/{len(arquivos)}] {nome:<44} "
                f"simb={linha['simbolos']:<5} desl={linha['deslocados']:<5} "
                f"empates={linha['empates']:<4} graves={linha['graves']:<4} "
                f"dentro {linha['dentro_antes_pct']}%→{linha['dentro_depois_pct']}%",
                flush=True,
            )

    if args.saida:
        Path(args.saida).write_text(json.dumps(linhas, indent=2), encoding="utf-8")

    bons = [linha for linha in linhas if linha["veredito"] == "ok"]
    com_simbolo = [linha for linha in bons if linha["simbolos"]]
    print("\n" + "=" * 78)
    print(f"arquivos lidos ............. {len(bons)}/{len(arquivos)}")
    print(f"com símbolo no <defs> ...... {len(com_simbolo)}")
    print(f"sem viewBox legível ........ {sum(1 for linha in bons if not linha['viewbox'])}")
    print(f"com ao menos um EMPATE ..... {sum(1 for linha in com_simbolo if linha['empates'])}")
    print(f"com EMPATE GRAVE ........... {sum(1 for linha in com_simbolo if linha['graves'])}")
    piorou = [
        linha for linha in com_simbolo
        if linha["dentro_antes_pct"] is not None
        and linha["dentro_depois_pct"] < linha["dentro_antes_pct"]
    ]
    print(f"correção PIOROU o arquivo .. {len(piorou)}")
    for linha in piorou:
        print(f"    {linha['arquivo']}  {linha['dentro_antes_pct']}% → {linha['dentro_depois_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
