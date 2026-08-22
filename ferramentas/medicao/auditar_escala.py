"""Auditoria da escala derivada — a régua que o desenho declara bate com a nossa?

**Preventiva, não reativa.** Ninguém relatou número errado; a pergunta é se a
escala que o motor publica pode estar errada em silêncio, que é o modo de falha
caro deste módulo. Uma escala 3,28× maior (pé lido como metro) não parece defeito
na tela: produz uma fachada de 98 m que cabe na janela de plausibilidade e vira
parede no lugar errado no canteiro.

O método é conferir **duas fontes independentes** do mesmo fato:

1. o que o ARQUIVO declara — `$INSUNITS` e `$EXTMIN`/`$EXTMAX` lidos direto do
   DXF pelo `ezdxf`, sem passar pelo nosso pipeline;
2. o que NÓS publicamos — `escala_do_desenho()` sobre o SVG realmente emitido.

Divergência acima da tolerância é o achado. Concordância não prova que a unidade
declarada no arquivo é a verdadeira (projetista que modela em metros e declara
milímetro engana as duas leituras igualmente) — isso é limite do método, e a
calibração humana é a resposta para ele.

Uso:

    python ferramentas/medicao/auditar_escala.py /app/media/prancheta --amostra 30
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

#: Quanto a régua pode divergir antes de virar achado, em fração.
#: 1% cobre arredondamento de emissão e a margem da folha; abaixo disso não há
#: erro de unidade possível — o menor engano real (polegada→cm) é de 2,54×.
TOLERANCIA = 0.01


def medir(caminho: str) -> dict:
    from moduloprancheta.motores.dxf import (
        MotorDxf, _agrupar, _caixas, _envolvente, _unidade_efetiva,
        escala_do_desenho,
    )

    linha = {"arquivo": os.path.basename(caminho)}
    motor = MotorDxf()
    try:
        documento, _rec = motor._ler(caminho)
    except Exception as exc:
        return {**linha, "erro": f"leitura: {type(exc).__name__}"}

    # --- fonte 1: o que o ARQUIVO diz, sem passar por nós -------------------
    cabecalho = getattr(documento, "header", {})
    declarada = cabecalho.get("$INSUNITS", 0) if hasattr(cabecalho, "get") else 0
    linha["insunits"] = declarada

    try:
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.recorder import Recorder

        gravador = Recorder()
        Frontend(RenderContext(documento), gravador,
                 config=motor._configuracao("")).draw_layout(documento.modelspace())
        player = gravador.player()
        caixas = _caixas(getattr(player, "records", []))
    except Exception as exc:
        return {**linha, "erro": f"gravacao: {type(exc).__name__}"}
    if not caixas:
        return {**linha, "erro": "sem desenho no modelspace"}

    grupos, _t = _agrupar(caixas)
    unidades, _geo = _unidade_efetiva(documento, grupos)
    linha["unidade_efetiva"] = unidades

    # A largura do maior grupo, em unidades de desenho, direto da geometria.
    envolvente = _envolvente(max(grupos, key=len))
    largura_desenho = envolvente[2] - envolvente[0]
    linha["largura_unidades"] = round(largura_desenho, 3)

    # --- fonte 2: o que NÓS publicamos, do SVG emitido ----------------------
    from ezdxf.addons.drawing import layout, svg

    from moduloprancheta.motores.dxf import (
        ESCALA_SAIDA_MM_POR_UNIDADE, MARGEM_MM,
    )

    backend = svg.SVGBackend()
    player.replay(backend)
    conteudo = backend.get_string(
        layout.Page(0, 0, layout.Units.mm, layout.Margins.all(MARGEM_MM)),
        settings=layout.Settings(scale=ESCALA_SAIDA_MM_POR_UNIDADE),
    )
    publicada = escala_do_desenho(conteudo, unidades)
    # **`escala_largura_m` e não `escala_valor`.** O motor devolve a grandeza
    # com o nome do que ela é (metros na largura da folha); `escala_valor` é o
    # nome da COLUNA, escrito depois por `pipeline._publicar_escala`. Ler o nome
    # errado aqui devolvia `None` em 25 de 25 e a auditoria "passava" sem ter
    # conferido nada — um falso verde, que é pior que um vermelho.
    linha["escala_publicada"] = publicada.get("escala_largura_m")
    if "escala_recusada" in publicada:
        # A prancha caiu fora da janela de plausibilidade. Não é achado desta
        # auditoria: é o motor recusando régua absurda, que é o comportamento
        # desejado — mas fica visível, porque recusa demais também é sintoma.
        linha["escala_recusada"] = publicada["escala_recusada"]

    # --- o confronto --------------------------------------------------------
    metros_por_unidade = _metros_por_unidade(unidades)
    if metros_por_unidade and publicada.get("escala_largura_m"):
        # `escala_valor` = quantas unidades REAIS cabem na largura da FOLHA, e a
        # folha é o desenho mais duas margens. O confronto tem de somá-las, ou
        # acusaria erro em toda prancha pequena — onde 20 mm de margem pesam.
        esperada = (largura_desenho + 2 * MARGEM_MM) * metros_por_unidade
        linha["escala_esperada"] = round(esperada, 6)
        if esperada > 0:
            desvio = abs(publicada["escala_largura_m"] - esperada) / esperada
            linha["desvio"] = round(desvio, 6)
            linha["achado"] = desvio > TOLERANCIA
    return linha


def _metros_por_unidade(codigo: int) -> float | None:
    """A mesma tabela que o motor usa — de propósito.

    Duplicá-la aqui daria uma auditoria que confere a tabela contra si mesma e
    aprova qualquer erro que ELA tenha. O que este script confronta é a
    aplicação da tabela (a conta que chega ao SVG), não a tabela.
    """
    from moduloprancheta.motores.dxf import METROS_POR_UNIDADE

    entrada = METROS_POR_UNIDADE.get(codigo)
    return entrada[0] if entrada else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("raiz")
    ap.add_argument("--amostra", type=int, default=30)
    ap.add_argument("--extensoes", default=".dxf,.dwg")
    args = ap.parse_args()

    from medir_snap import desenhos, para_dxf

    extensoes = tuple(e.strip() for e in args.extensoes.split(",") if e.strip())
    todos = desenhos(args.raiz, extensoes)
    passo = max(1, len(todos) // args.amostra)
    amostra = todos[::passo][:args.amostra]

    print(f"# {len(todos)} desenhos únicos · auditando {len(amostra)}", flush=True)
    linhas = []
    for i, bruto in enumerate(amostra, 1):
        try:
            caminho, temporario = para_dxf(bruto)
        except Exception as exc:
            linhas.append({"arquivo": os.path.basename(bruto),
                           "erro": f"dwg2dxf: {type(exc).__name__}"})
            continue
        try:
            linha = medir(caminho)
        finally:
            if temporario and os.path.exists(caminho):
                os.unlink(caminho)
        linha["arquivo"] = os.path.basename(bruto)
        linhas.append(linha)
        print(f"[{i}/{len(amostra)}] {json.dumps(linha, ensure_ascii=False)}", flush=True)

    conferidos = [l for l in linhas if "desvio" in l]
    achados = [l for l in conferidos if l.get("achado")]
    print("\n" + "=" * 72)
    print(f"conferidos {len(conferidos)}/{len(linhas)} · ACHADOS {len(achados)}")
    if conferidos:
        desvios = sorted(l["desvio"] for l in conferidos)
        print(f"  desvio  mediana {statistics.median(desvios):.2e}"
              f" · p90 {desvios[int(len(desvios) * 0.9)]:.2e}"
              f" · max {desvios[-1]:.2e}")
    for l in achados:
        print(f"  ACHADO {l['arquivo']}: publicada={l.get('escala_publicada')} "
              f"esperada={l.get('escala_esperada')} desvio={l['desvio']:.3f}")
    # Sem escala não é achado: é o caso declarado (PDF, foto, DXF sem $INSUNITS)
    # em que a calibração humana é o caminho — ver `models.RevisaoDocumento`.
    sem_regua = [l for l in linhas if l.get("escala_publicada") in (None, 0)]
    print(f"  sem régua (calibração humana é o caminho): {len(sem_regua)}")
    return 1 if achados else 0


if __name__ == "__main__":
    raise SystemExit(main())
