#!/usr/bin/env python3
"""Compara dois `dwg2dxf` sobre os mesmos DWGs — o D43, na parte que não é nossa.

**A pergunta.** Depois dos consertos de 09/08/2026 o balde
`dxf_intermediario_ilegivel` tem 19 arquivos, e quase todos são do **grupo A**:
o `dwg2dxf` não consegue decodificar o DWG, escreve um DXF truncado (sem a tag
`EOF`) e **sai com código 0**. Nenhum reparo de saída traz de volta um dado que
não está no intermediário — os três que existem em `motores/dwg.py`
(continuação órfã, registro vazio, seta de cota órfã) consertam DXF malformado,
não DXF incompleto. O que resta é o decodificador, e o decodificador é do
LibreDWG.

Este script responde a uma pergunta só, e por medida: **o git master decodifica
o que o 0.13.3 não decodifica?**

**Por que o veredito não é "abriu".** O `--as rNNNN` já ensinou a lição neste
mesmo achado: com ele os arquivos ilegíveis passavam a abrir no `ezdxf` — e
saíam com `msp=0`, zero entidade, sem envolvente. Legibilidade sem geometria é
o [D52](../../docs/historico-correcoes.md) outra vez, e desta vez disfarçado de
ganho de cobertura. Por isso cada arquivo aqui é medido em **entidade de
modelspace e envolvente**, e o relatório trata `abriu com msp=0` como
**suspeita**, nunca como conversão.

**O controle está embutido.** Os dois binários rodam sobre os mesmos arquivos,
na mesma passada: o 0.13.3 é a linha de base medida agora, não a lembrada do
log anterior. Sem isso, uma diferença de ambiente viraria mérito do commit.

**Teto de recurso** — a lição do [D57](../../docs/historico-correcoes.md): cada
subprocesso leva `RLIMIT_AS` (o mesmo orçamento da produção) e relógio próprio,
e o contêiner que roda isto leva `--memory`/`--cpus`. Estourar o teto é
resultado (`recurso_excedido`), não travar a estação.

Uso (dentro da imagem `medicao-libredwg-master`):

    python /opt/comparar_decodificador.py /acervo \\
        --lista /saida/d43-alvos-19.txt --saida /saida/comparacao.json

    python /opt/comparar_decodificador.py --sonda ARQUIVO.dxf   # uso interno
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import tempfile
import time

#: Orçamento de memória por subprocesso, em MB. É o mesmo número da produção
#: (`PRANCHETA_CONVERSAO_MEMORIA_MB`), de propósito: medir com folga que o
#: cliente não tem produziria uma taxa que a produção não entrega.
MEMORIA_MB = int(os.environ.get("PRANCHETA_CONVERSAO_MEMORIA_MB", "1536"))

#: Relógio por etapa. A conversão mais lenta medida até aqui levou 26 s (D53);
#: 300 s é folga de uma ordem de grandeza e ainda assim termina.
SEGUNDOS = int(os.environ.get("PRANCHETA_CONVERSAO_SEGUNDOS", "300"))

BASE = os.environ.get("BINARIO_BASE", "dwg2dxf")
CANDIDATO = os.environ.get("BINARIO_CANDIDATO", "dwg2dxf-master")

#: Raiz do backend dentro da imagem — de onde `config.settings` é importável.
APP = os.environ.get("APP_DIR", "/app")


def _com_teto():
    """Aplica o orçamento de memória no filho, antes do `exec`."""
    limite = MEMORIA_MB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limite, limite))


def _rodar(cmd: list[str], segundos: int) -> tuple[int, str, float]:
    inicio = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, errors="replace",
            timeout=segundos, preexec_fn=_com_teto,
        )
        return proc.returncode, (proc.stderr or "") + (proc.stdout or ""), time.monotonic() - inicio
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT", time.monotonic() - inicio


# ---------------------------------------------------------------------------
# A sonda — roda em processo próprio, com teto próprio
# ---------------------------------------------------------------------------
# Processo separado por dois motivos, e o segundo é o que importa: memória que
# o `ezdxf` aloca em extensão C não volta ao sistema quando o Python solta o
# objeto — volta quando o processo morre. Medir 19 arquivos num processo só é
# como a passada de 06/08 chegou a 62 GB.


def sondar(dxf: str) -> dict:
    """Mede um DXF: abre? por qual caminho? com quanta geometria?"""
    saida: dict = {"bytes": 0, "eof": False, "abriu": "nao", "msp": 0,
                   "envolvente": None, "erro": "", "reparos": {}}
    if not os.path.exists(dxf):
        saida["erro"] = "o binário não escreveu arquivo"
        return saida

    saida["bytes"] = os.path.getsize(dxf)
    with open(dxf, "rb") as fh:
        fh.seek(max(0, saida["bytes"] - 4096))
        rabo = fh.read()
    # O critério do `_conferir_decodificacao`: a tag `EOF` depois do último
    # `ENDSEC`. É definicional — DXF sem ela está incompleto —, ao contrário de
    # "tem linha ERROR:", que reprovaria 83% das conversões que funcionam.
    saida["eof"] = b"EOF" in rabo.split(b"ENDSEC")[-1]

    bruto = None
    try:  # o caminho da produção, com os três reparos do D43
        import django
        # `/app` na frente do path porque a sonda roda de qualquer diretório e
        # `config.settings` mora na raiz do backend. Sem isto o `django.setup()`
        # falha, a sonda mede o DXF **cru** e reporta `reparos: indisponivel` —
        # que é medida honesta, mas de outra coisa: a produção nunca entrega o
        # cru ao `ezdxf`.
        if APP not in sys.path:
            sys.path.insert(0, APP)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()
        from moduloprancheta.motores.dwg import reparar_intermediario
        with open(dxf, "rb") as fh:
            bruto, contagem = reparar_intermediario(fh.read())
        saida["reparos"] = {k: v for k, v in contagem.items() if v}
    except Exception as exc:  # sem Django: mede o cru e diz que mediu o cru
        saida["reparos"] = {"indisponivel": str(exc)[:80]}

    alvo = dxf
    if bruto is not None and saida["reparos"] and "indisponivel" not in saida["reparos"]:
        alvo = dxf + ".reparado"
        with open(alvo, "wb") as fh:
            fh.write(bruto)

    import ezdxf
    from ezdxf import recover

    doc = None
    try:
        doc = ezdxf.readfile(alvo)
        saida["abriu"] = "readfile"
    except Exception as exc:
        saida["erro"] = f"{type(exc).__name__}: {exc}"[:200]
        try:
            doc, _ = recover.readfile(alvo)
            saida["abriu"] = "recover"
        except Exception as exc2:
            saida["erro"] += f" | recover: {type(exc2).__name__}: {exc2}"[:200]
            return saida

    msp = doc.modelspace()
    entidades = list(msp)
    saida["msp"] = len(entidades)
    try:
        from ezdxf.bbox import extents
        caixa = extents(entidades, fast=True)
        if caixa.has_data:
            saida["envolvente"] = [round(caixa.size.x, 1), round(caixa.size.y, 1)]
    except Exception:
        pass
    return saida


# ---------------------------------------------------------------------------
# A passada
# ---------------------------------------------------------------------------


def medir(binario: str, dwg: str, pasta: str) -> dict:
    destino = os.path.join(pasta, os.path.basename(binario) + ".dxf")
    rc, log, secs = _rodar([binario, "-y", "-o", destino, dwg], SEGUNDOS)
    erros = [l for l in log.splitlines() if l.strip().startswith("ERROR:")]
    medida = {
        "rc": rc,
        "segundos": round(secs, 1),
        "erros_decodificador": len(erros),
        "primeiro_erro": erros[0][len("ERROR:"):].strip()[:120] if erros else "",
    }
    if rc == -9:
        medida.update(bytes=0, eof=False, abriu="nao", msp=0,
                      envolvente=None, erro="TIMEOUT", reparos={})
        return medida

    sonda = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--sonda", destino],
        capture_output=True, text=True, errors="replace", timeout=SEGUNDOS,
    )
    try:
        medida.update(json.loads(sonda.stdout.strip().splitlines()[-1]))
    except Exception:
        medida.update(bytes=0, eof=False, abriu="nao", msp=0, envolvente=None,
                      erro=f"sonda falhou: {(sonda.stderr or '')[-160:]}", reparos={})
    for resto in os.listdir(pasta):
        os.unlink(os.path.join(pasta, resto))
    return medida


def veredito(base: dict, cand: dict) -> str:
    """Compara as duas medidas de um arquivo. Geometria manda, não legibilidade."""
    if cand["msp"] > 0 and base["msp"] == 0:
        return "CONSERTA"
    if cand["msp"] == 0 and base["msp"] > 0:
        return "REGRIDE"
    if cand["msp"] == 0 and base["msp"] == 0:
        if cand["abriu"] != "nao" and base["abriu"] == "nao":
            return "abre vazio (suspeito)"
        if cand["eof"] and not base["eof"]:
            return "decodifica inteiro, ezdxf ainda recusa"
        return "igual"
    delta = cand["msp"] - base["msp"]
    return "igual" if delta == 0 else f"msp {base['msp']}→{cand['msp']}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("acervo", nargs="?", default="")
    ap.add_argument("--lista", default="")
    ap.add_argument("--saida", default="")
    ap.add_argument("--sonda", default="")
    args = ap.parse_args()

    if args.sonda:
        print(json.dumps(sondar(args.sonda), ensure_ascii=False))
        return 0

    if not args.acervo or not args.lista:
        ap.error("informe o acervo e a --lista")

    with open(args.lista, encoding="utf-8") as fh:
        alvos = [l.rstrip("\n") for l in fh if l.strip() and not l.startswith("#")]

    versoes = {}
    for b in (BASE, CANDIDATO):
        rc, log, _ = _rodar([b, "--version"], 30)
        versoes[b] = log.strip().splitlines()[0] if log.strip() else f"rc={rc}"
    print(f"base      : {BASE} · {versoes[BASE]}")
    print(f"candidato : {CANDIDATO} · {versoes[CANDIDATO]}")
    print(f"alvos     : {len(alvos)} · teto {MEMORIA_MB} MB / {SEGUNDOS} s por etapa\n")

    linhas = []
    for i, rel in enumerate(alvos, 1):
        dwg = os.path.join(args.acervo, rel)
        nome = os.path.basename(rel)
        if not os.path.exists(dwg):
            print(f"[{i:2}/{len(alvos)}] {nome[:60]:60} AUSENTE NO ACERVO")
            linhas.append({"arquivo": rel, "ausente": True})
            continue
        with tempfile.TemporaryDirectory() as pasta:
            base = medir(BASE, dwg, pasta)
            cand = medir(CANDIDATO, dwg, pasta)
        v = veredito(base, cand)
        linhas.append({"arquivo": rel, "base": base, "candidato": cand, "veredito": v})
        print(f"[{i:2}/{len(alvos)}] {nome[:52]:52} "
              f"base: {base['abriu']:8} msp={base['msp']:<6} eof={int(base['eof'])} | "
              f"master: {cand['abriu']:8} msp={cand['msp']:<6} eof={int(cand['eof'])} | {v}")
        if v == "CONSERTA":
            print(f"          envolvente {cand['envolvente']} · {cand['segundos']}s "
                  f"· {cand['erros_decodificador']} erros de decodificador")

    conserta = [l for l in linhas if l.get("veredito") == "CONSERTA"]
    regride = [l for l in linhas if l.get("veredito") == "REGRIDE"]
    vazio = [l for l in linhas if l.get("veredito") == "abre vazio (suspeito)"]
    print(f"\n{'=' * 70}")
    print(f"CONSERTA (msp > 0 onde a base tinha 0) : {len(conserta)}/{len(alvos)}")
    print(f"REGRIDE  (perdeu geometria)            : {len(regride)}")
    print(f"abre vazio — NÃO é conserto (D52)      : {len(vazio)}")
    for l in conserta:
        print(f"  + {l['arquivo']}")
    for l in regride:
        print(f"  ! {l['arquivo']}")

    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as fh:
            json.dump({"versoes": versoes, "memoria_mb": MEMORIA_MB,
                       "arquivos": linhas}, fh, ensure_ascii=False, indent=1)
        print(f"\nDetalhe por arquivo: {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
