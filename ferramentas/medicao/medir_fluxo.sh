#!/usr/bin/env bash
# Onde está o custo da conversão — e quanto o caminho EM FLUXO economiza.
#
# **A pergunta que este script responde.** O perfil de 10/08/2026 mostrou que
# **81%** do pico de uma conversão de DWG é uma etapa só: `ezdxf.readfile()`
# materializando o DXF intermediário num grafo de objetos Python (396 MB de um
# pico de 488 MB, contra 39 MB do `Recorder` e 34 MB do `SVGBackend`). Trocar de
# renderizador ou deduplicar bloco mexe nos outros 15% — foi por isso que as duas
# rotas de 10/08 deram em nada (planta §4.1).
#
# O caminho proposto não materializa: carrega só HEADER/TABLES/BLOCKS (o
# "esqueleto", que traz estilos, camadas e os 53 blocos) e **transmite** as
# entidades do modelspace em lotes, pelo `ezdxf.addons.iterdxf`.
#
# **O que precisa ser conferido na saída, e não só o número final:**
#
#   - a etapa 2 (esqueleto) tem de custar uma fração dos 396 MB — é a aposta
#     inteira. Se o esqueleto sozinho já custar centenas de MB, a frente morre e
#     o motivo é que o custo não estava nas entidades;
#   - a contagem de `registros` da etapa 3 tem de bater com a do caminho de hoje
#     (**47.610** no arquivo de referência). Registro a menos é desenho perdido,
#     e aí o número baixo não vale nada — é a lição do D52/D79;
#   - `entidades` tem de bater com o que o modelspace traz. Um `iterdxf` que
#     entrega menos entidades é economia falsa pelo mesmo motivo.
#
# Uso: bash ferramentas/medicao/medir_fluxo.sh [caminho-do-acervo]
#      (o padrão aponta para o OneDrive da estação; um arquivo, não é lote)
set -uo pipefail
ACERVO="${1:-/mnt/c/Users/Edison-Engenharia/OneDrive}"
IMAGEM="${IMAGEM:-02sistema_gestao_integrada-erp}"
ALVO="${ALVO:-02 - Projeto de agua.dwg}"
FILTRO="${FILTRO:-Correcoes}"

cat > /tmp/_fluxo_dentro.sh <<'DENTRO'
#!/bin/sh
set -u
f=$(find /acervo -name "$ALVO" | grep "$FILTRO" | head -1)
[ -n "$f" ] || { echo "não achei '$ALVO' em /acervo"; exit 2; }
echo "ARQUIVO: $(basename "$f")"
dwg2dxf -o /tmp/i.dxf "$f" >/dev/null 2>&1
stat -c%s /tmp/i.dxf | awk '{printf "DXF intermediario: %.0f MB\n", $1/1048576}'
cd /app && python - <<'PY'
import os, django, resource, gc, io, time
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings"); django.setup()
import logging; logging.disable(logging.CRITICAL)

def rss():
    with open("/proc/self/status") as fh:
        for linha in fh:
            if linha.startswith("VmRSS:"):
                return int(linha.split()[1]) / 1024
    return 0.0

pico = lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
print(f"base do processo: {rss():.0f} MB\n")

# 1) Recortar a seção ENTITIES do texto — a mesma cirurgia de texto que o D43 já
#    faz no intermediário, aqui para produzir o esqueleto.
t = time.monotonic()
alvo, dentro, cortadas = [], False, 0
with open("/tmp/i.dxf", "r", encoding="utf-8", errors="ignore") as fh:
    for linha in fh:
        if (linha.strip() == "ENTITIES" and len(alvo) >= 3
                and alvo[-1].strip() == "2" and alvo[-2].strip() == "SECTION"):
            dentro = True
            # O cabeçalho da seção são TRÊS linhas — `0` / `SECTION` / `2` —, e
            # remover só duas deixa o `0` órfão: o `ezdxf` então lê o `SECTION`
            # seguinte como se fosse valor do grupo 0 e morre com
            # `Invalid group code "SECTION"`. Errado na primeira versão deste
            # script, e é o tipo de erro que só aparece no arquivo grande.
            alvo.pop(); alvo.pop(); alvo.pop()
            continue
        if dentro:
            cortadas += 1
            if linha.strip() == "ENDSEC":
                dentro = False
            continue
        alvo.append(linha)
esqueleto = "".join(alvo)
print(f"1) recorte do texto         {time.monotonic()-t:5.1f}s  "
      f"esqueleto={len(esqueleto)/1048576:6.1f} MB  ({cortadas} linhas cortadas)")

# 2) O esqueleto vira documento: estilos, camadas e blocos, sem as entidades.
import ezdxf
t = time.monotonic()
doc = ezdxf.read(io.StringIO(esqueleto))
del esqueleto, alvo
gc.collect()
print(f"2) ezdxf.read SEM entities  {time.monotonic()-t:5.1f}s  "
      f"blocos={len(doc.blocks)} layers={len(doc.layers)}   RSS {rss():7.0f} MB  <<< a aposta")

# 3) As entidades em fluxo, em lotes — nunca todas vivas ao mesmo tempo.
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.recorder import Recorder
from ezdxf.addons import iterdxf

t = time.monotonic()
gravador = Recorder()
frente = Frontend(RenderContext(doc), gravador)
lote, entidades = [], 0
fonte = iterdxf.opendxf("/tmp/i.dxf")
try:
    for entidade in fonte.modelspace():
        entidade.doc = doc          # o entity vem solto; o esqueleto dá o contexto
        lote.append(entidade)
        entidades += 1
        if len(lote) >= 2000:
            try: frente.draw_entities(lote)
            except Exception: pass
            lote = []
    if lote:
        try: frente.draw_entities(lote)
        except Exception: pass
finally:
    fonte.close()

registros = len(gravador.player().records)
print(f"3) iterdxf em fluxo         {time.monotonic()-t:5.1f}s  "
      f"entidades={entidades} registros={registros}   RSS {rss():7.0f} MB")
print(f"\nPICO DO CAMINHO EM FLUXO: {pico():.0f} MB")
print("  referência de hoje: pico 488 MB · readfile 396 MB · 47.610 registros")
print("  CONFIRA: registros ~47.610. Menos que isso é desenho perdido, não economia.")
PY
DENTRO

exec docker run --rm --memory 3g --cpus 2 \
  -e DEBUG=True -e SECRET_KEY=medicao-local-sem-rede \
  -e ALVO="$ALVO" -e FILTRO="$FILTRO" \
  -v "$ACERVO:/acervo:ro" \
  -v /tmp/_fluxo_dentro.sh:/fluxo.sh:ro \
  --entrypoint sh "$IMAGEM" /fluxo.sh
