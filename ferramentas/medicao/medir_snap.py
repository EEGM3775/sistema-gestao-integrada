"""Custo do índice de snap sobre arquivo real — o número que define o teto do plano.

Roda o caminho de produção (`MotorDxf` → `Recorder` → `indice_de_snap`) sobre os
desenhos que já estão no volume de mídia, e responde as três perguntas que o
`payment/planos.py` precisa para ter um número em vez de um palpite:

1. **quantos pontos** uma prancha real rende (é a unidade do teto);
2. **quantos bytes** isso vira no sidecar que o navegador baixa;
3. **quanta RAM e quanto relógio** a extração custa *além* do SVG que já se paga.

O item 3 é o que decide se o snap cabe no orçamento de conversão do D76 ou se
precisa de etapa própria. Medido por dentro (`tracemalloc` para o pico do índice,
`VmHWM` para o do processo), pela mesma razão do D82: `RUSAGE` acumula entre
arquivos e daria o retrato do anterior.

**Esta bancada NÃO emite o SVG, e isso é de propósito** — o que ela quer é o
custo do índice sozinho. O efeito colateral vale ser dito porque foi evidência
desperdiçada: sem a emissão, a geometria fica em unidade de desenho e o índice
sai completo, então os números daqui sempre descreveram o comportamento
**correto**. A produção, que emite, saía com uma fração disso (4.286 pontos onde
esta bancada media centenas de milhares na mesma prancha), e ninguém confrontou
os dois números — era o D90 escrito em duas colunas que nunca foram comparadas.
Quem quiser aferir a produção usa a [conferir_snap.py](conferir_snap.py) ao lado,
que converte pelo `_folha` de verdade.

Uso, dentro do container que tem o `ezdxf`:

    python ferramentas/medicao/medir_snap.py /app/media/prancheta --amostra 40
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
import tracemalloc

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from moduloprancheta.motores import snap as snapmod  # noqa: E402

#: Teto usado durante a medição. Alto de propósito: o objetivo é descobrir o
#: custo REAL da prancha, não confirmar um teto que ainda não existe. O corte de
#: plano entra depois, com o número que esta passada produzir.
TETO_DE_MEDICAO = 50_000_000


def desenhos(raiz: str, extensoes: tuple[str, ...]) -> list[str]:
    """Os arquivos do acervo, **sem repetição de conteúdo**.

    O volume tem o mesmo desenho subido muitas vezes (`planta_UHdZu7k.dxf` e
    irmãos são reenvios). Medir os duplicados inflaria a amostra com um desenho
    só e daria uma mediana que não descreve acervo nenhum. Pareado por SHA-256,
    como o `relatorio_custo_por_caminho.py` já faz.
    """
    vistos: set[str] = set()
    achados: list[str] = []
    for pasta, _subpastas, arquivos in os.walk(raiz):
        for nome in arquivos:
            if not nome.lower().endswith(extensoes):
                continue
            caminho = os.path.join(pasta, nome)
            try:
                with open(caminho, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
            except OSError:
                continue
            if digest in vistos:
                continue
            vistos.add(digest)
            achados.append(caminho)
    return sorted(achados, key=lambda c: os.path.getsize(c))


def pico_do_processo_mb() -> float:
    try:
        with open("/proc/self/status") as fh:
            for linha in fh:
                if linha.startswith("VmHWM:"):
                    return int(linha.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


def para_dxf(caminho: str) -> tuple[str, bool]:
    """DWG vira DXF pelo mesmo `dwg2dxf` da produção; DXF passa reto.

    Devolve `(caminho, temporario)` — o chamador apaga o que for temporário.
    Passar pelo `MotorDwg._para_dxf` e não chamar o binário à mão importa: é lá
    que mora o remendo das continuações órfãs do D43, sem o qual 13,8% do corpus
    nem chega ao `ezdxf` e a amostra ficaria enviesada para os arquivos fáceis.
    """
    if not caminho.lower().endswith(".dwg"):
        return caminho, False
    from moduloprancheta.motores.base import executavel
    from moduloprancheta.motores.dwg import ENV_BINARIO, MotorDwg

    binario = executavel("dwg2dxf", ENV_BINARIO)
    if not binario:
        raise RuntimeError("dwg2dxf ausente")
    destino, _reparos = MotorDwg()._para_dxf(binario, caminho)
    return destino, True


def medir(caminho: str) -> dict:
    """Uma prancha: SVG pelo caminho de produção, depois o índice por cima."""
    from moduloprancheta.motores.dxf import (
        FOLGA_RECORTE, MotorDxf, _agrupar, _caixas, _envolvente)

    tamanho_mb = os.path.getsize(caminho) / (1024 * 1024)
    linha = {"arquivo": os.path.basename(caminho), "mb": round(tamanho_mb, 2)}

    t0 = time.perf_counter()
    try:
        caminho, temporario = para_dxf(caminho)
    except Exception as exc:
        return {**linha, "erro": f"dwg2dxf: {type(exc).__name__}: {exc}"[:120]}
    linha["s_dwg2dxf"] = round(time.perf_counter() - t0, 2)

    motor = MotorDxf()
    t0 = time.perf_counter()
    try:
        documento, _recuperado = motor._ler(caminho)
    except Exception as exc:
        if temporario:
            os.unlink(caminho)
        return {**linha, "erro": f"leitura: {type(exc).__name__}"}
    finally:
        if temporario and os.path.exists(caminho):
            # O DXF intermediário chega a centenas de MB; segurá-lo durante a
            # medição inteira encheria o /tmp do container no meio do corpus.
            os.unlink(caminho)

    try:
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.recorder import Recorder

        config = motor._configuracao("")
        gravador = Recorder()
        Frontend(RenderContext(documento), gravador, config=config).draw_layout(
            documento.modelspace())
        player = gravador.player()
        caixas = _caixas(getattr(player, "records", []))
    except Exception as exc:
        return {**linha, "erro": f"gravacao: {type(exc).__name__}"}
    linha["s_gravar"] = round(time.perf_counter() - t0, 2)

    if not caixas:
        return {**linha, "erro": "sem desenho no modelspace"}

    grupos, _truncados = _agrupar(caixas)
    linha["folhas"] = len(grupos)

    # Mede a folha MAIOR — é ela que define o teto. A média das folhas de um
    # arquivo com uma prancha cheia e seis detalhes esconderia justamente o caso
    # que estoura.
    total_pontos = total_segmentos = total_bytes = 0
    pior = {}
    tracemalloc.start()
    t1 = time.perf_counter()
    for grupo in grupos:
        envolvente = _envolvente(grupo)
        # **Recorta como o `_folha` recorta.** Sem isto a medição passa o desenho
        # INTEIRO para cada folha: o arquivo de duas pranchas mede o dobro do que
        # custa de verdade, e o traço que cai fora da envolvente do grupo
        # normaliza para fora de [0,1], onde a grade de varredura não deveria
        # precisar viver. Foi assim que a primeira passada inventou 626 células
        # densas num arquivo que não tem nenhuma.
        recortado = player
        if len(grupos) > 1:
            largura = envolvente[2] - envolvente[0]
            altura = envolvente[3] - envolvente[1]
            recortado = player.copy()
            recortado.crop_rect(
                (envolvente[0] - FOLGA_RECORTE, envolvente[1] - FOLGA_RECORTE),
                (envolvente[2] + FOLGA_RECORTE, envolvente[3] + FOLGA_RECORTE),
                max(largura, altura) / 10_000 or 1e-9,
            )
        try:
            indice = snapmod.indice_de_snap(recortado, envolvente, teto=TETO_DE_MEDICAO)
        except Exception as exc:
            tracemalloc.stop()
            return {**linha, "erro": f"snap: {type(exc).__name__}: {exc}"}
        octetos = len(snapmod.empacotar(indice))
        total_pontos += indice.total()
        total_segmentos += indice.total_de_segmentos()
        total_bytes += octetos
        if indice.total() > pior.get("pontos", -1):
            pior = {"pontos": indice.total(), "censo": indice.censo,
                    "truncado": indice.truncado, "tipos": indice.censo_por_tipo()}
    _atual, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    linha.update({
        "s_snap": round(time.perf_counter() - t1, 2),
        "pontos": total_pontos,
        "pontos_maior_folha": pior.get("pontos", 0),
        "segmentos": total_segmentos,
        "kb_sidecar": round(total_bytes / 1024, 1),
        "mb_pico_indice": round(pico / (1024 * 1024), 1),
        "celulas_densas": pior.get("censo", {}).get("celulas_densas", 0),
        "tipos": pior.get("tipos", {}),
    })
    return linha


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("raiz")
    ap.add_argument("--amostra", type=int, default=40,
                    help="quantos desenhos medir (espalhados por tamanho)")
    ap.add_argument("--extensoes", default=".dxf")
    ap.add_argument("--saida", default="")
    args = ap.parse_args()

    extensoes = tuple(e.strip() for e in args.extensoes.split(",") if e.strip())
    todos = desenhos(args.raiz, extensoes)
    if not todos:
        print(f"Nenhum {extensoes} em {args.raiz}", file=sys.stderr)
        return 1

    # Amostra espalhada por TAMANHO, não aleatória: o teto é decidido pela cauda
    # (a prancha grande), e um sorteio uniforme quase não a pega.
    passo = max(1, len(todos) // args.amostra)
    amostra = todos[::passo][:args.amostra]
    if todos[-1] not in amostra:
        amostra.append(todos[-1])  # o maior do acervo entra sempre

    print(f"# acervo: {len(todos)} desenhos únicos · medindo {len(amostra)}",
          flush=True)
    linhas = []
    for i, caminho in enumerate(amostra, 1):
        linha = medir(caminho)
        linhas.append(linha)
        print(f"[{i}/{len(amostra)}] {json.dumps(linha, ensure_ascii=False)}",
              flush=True)

    bons = [l for l in linhas if "pontos" in l]
    print("\n" + "=" * 72)
    print(f"medidos {len(bons)}/{len(linhas)} · falhas {len(linhas) - len(bons)}")
    if bons:
        for campo in ("pontos", "pontos_maior_folha", "kb_sidecar",
                      "mb_pico_indice", "s_snap"):
            vals = sorted(l[campo] for l in bons)
            print(f"  {campo:20s} mediana {statistics.median(vals):>12,.1f}"
                  f" · p90 {vals[int(len(vals) * 0.9)]:>12,.1f}"
                  f" · max {vals[-1]:>12,.1f}")
        print(f"  pico VmHWM do processo: {pico_do_processo_mb():.0f} MB")
    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as fh:
            json.dump(linhas, fh, ensure_ascii=False, indent=1)
        print(f"  detalhe em {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
