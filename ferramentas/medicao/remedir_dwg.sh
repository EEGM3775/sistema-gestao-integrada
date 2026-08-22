#!/usr/bin/env bash
#
# Remedição da cobertura do motor livre de DWG — a PRA.1d, item 5 (D57/D42).
#
# **Por que em lotes, e por que um container por lote.** A passada de 06/08/2026
# rodou o acervo inteiro num processo só e chegou a 62 GB de RAM numa estação de
# 64, tendo de ser interrompida. O conserto não é medir menos: é que o processo
# que mede **termine** de tempos em tempos. Memória alocada por extensão C (o
# `ezdxf` desenhando, o LibreDWG lendo) não volta ao sistema operacional só
# porque o Python liberou o objeto — volta quando o processo morre. Cada lote
# aqui é um `docker run --rm` próprio:
#
#   1. o container tem teto duro (`--memory`/`--cpus`), então o pior caso de um
#      lote é o lote morrer — nunca a estação travar;
#   2. o fim do lote devolve a memória ao host, medida ou não;
#   3. dá para interromper entre lotes (Ctrl-C) sem perder o que já foi medido;
#   4. relançar o script **pula** os lotes que já têm parcial e continua de onde
#      parou.
#
# Dentro do lote, cada arquivo ainda tem os tetos de produção: o
# `orcamento_de_conversao` (RLIMIT_AS, `PRANCHETA_CONVERSAO_MEMORIA_MB`) e o
# relógio do `--teto-segundos`. Este script é a camada de fora, não a única.
#
# **`--detalhe` desde 08/08/2026, e ele não é verbosidade.** A passada de 07/08
# rodou sem ele: o relatório disse que 11 arquivos estouraram o orçamento e 21
# geraram DXF ilegível, e **nenhum deles ficou com nome** — nem nos logs, nem nos
# parciais. Cada achado virou um número que a investigação seguinte teria de
# reconquistar remedindo o acervo. Agora o veredito por arquivo vai no log do
# lote e, o que importa mais, dentro do parcial JSON (v2).
#
# Uso:
#   ferramentas/medicao/remedir_dwg.sh /caminho/do/acervo [SAIDA] [LOTE] [AMOSTRA]
#
#   ACERVO  pasta com os DWGs (montada SÓ-LEITURA no container)
#   SAIDA   onde ficam a lista da amostra, os parciais e os logs
#   LOTE    arquivos por lote (padrão 10)
#   AMOSTRA 1 a cada N do acervo (padrão 7 — a amostra de 02/08, para a
#           comparação antes/depois falar do mesmo corpus)
#
set -euo pipefail

ACERVO="${1:?informe a pasta do acervo de DWGs}"
SAIDA="${2:-$HOME/medicao-dwg}"
LOTE="${3:-10}"
AMOSTRA="${4:-7}"

IMAGEM="${IMAGEM:-02sistema_gestao_integrada-erp}"
# `DOCKER_USER=1000:1000` roda o container como você, para os parciais nascerem
# com o seu dono. Vazio (o padrão) roda como root: no Docker Desktop do Windows o
# UID do Git Bash não existe dentro do container e a gravação em /saida falha.
MEMORIA_CONTAINER="${MEMORIA_CONTAINER:-3g}"
CPUS_CONTAINER="${CPUS_CONTAINER:-2}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# **`COMANDO_PY=` vazio desliga a montagem** e usa o comando que já está na
# imagem. Duas situações pedem isso: (a) o repositório vive num caminho que o
# daemon do Docker não consegue montar — é o caso de `\\wsl.localhost\…` com o
# Docker Desktop rodando no Windows, onde o bind falha com "not a directory"; e
# (b) a imagem acabou de ser construída deste mesmo repositório, e então a
# montagem é redundante. Confira antes com `md5sum` dos dois lados: se
# divergirem, monte — medir com comando velho é medir outra coisa.
COMANDO_PY="${COMANDO_PY-$REPO/backend/moduloprancheta/management/commands/medir_cobertura_dwg.py}"
# **`MOTOR_PY=` monta o motor junto, e existe pela mesma razão que o de cima.**
# O que a medição vê depende de dois arquivos, não de um: o comando classifica e
# o motor produz a falha que ele classifica. Em 09/08/2026 o conserto do stderr
# truncado (`_stderr_util`) ficou no motor, e medir com o comando novo sobre o
# motor velho teria devolvido a mesma frase inútil, agora com aparência de
# medição nova. Vazio (o padrão) usa o motor da imagem.
MOTOR_PY="${MOTOR_PY-}"

[ -d "$ACERVO" ] || { echo "Acervo '$ACERVO' não é um diretório." >&2; exit 1; }
mkdir -p "$SAIDA"

# O comando é montado avulso porque `payment/` vive na RAIZ do repo e não em
# `backend/`: montar `backend/` inteiro sobre /app esconderia `payment.planos` e
# o Django nem sobe. Um arquivo, só-leitura — o resto vem da imagem.
lote() {
  local pular="$1" limite="$2" nome="$3"; shift 3
  local monta_comando=()
  [ -n "$COMANDO_PY" ] && monta_comando=(-v "$COMANDO_PY:/app/moduloprancheta/management/commands/medir_cobertura_dwg.py:ro")
  [ -n "$MOTOR_PY" ] && monta_comando+=(-v "$MOTOR_PY:/app/moduloprancheta/motores/dwg.py:ro")
  docker run --rm \
    --memory "$MEMORIA_CONTAINER" --cpus "$CPUS_CONTAINER" \
    ${DOCKER_USER:+--user "$DOCKER_USER"} \
    -e DEBUG=True -e SECRET_KEY=medicao-local-sem-rede \
    -e PRANCHETA_CONVERSAO_MEMORIA_MB="${PRANCHETA_CONVERSAO_MEMORIA_MB:-1536}" \
    -e PRANCHETA_CONVERSAO_SEGUNDOS="${PRANCHETA_CONVERSAO_SEGUNDOS:-300}" \
    "${monta_comando[@]}" \
    -v "$ACERVO:/acervo:ro" \
    -v "$SAIDA:/saida" \
    "$IMAGEM" \
    nice -n 19 python manage.py medir_cobertura_dwg /acervo --recursivo \
      --pular "$pular" --limite "$limite" \
      --parcial "/saida/$nome.json" \
      --detalhe --preview --resgate "$@"
}

LISTA="$SAIDA/amostra.txt"

# ---- CORPUS: remedir um conjunto JÁ definido, em vez de sortear um novo ------
# **Por que existe.** Uma passada que troca o motor (e não o código) só diz
# alguma coisa contra o **mesmo** conjunto da anterior: com amostra nova, a
# diferença entre 84% e 96% pode ser sorte do sorteio. `CORPUS=…` aponta a lista
# versionada (`corpus-160.txt`) e o sorteio não acontece — nem o `--amostra`, nem
# o `--salvar-lista`, que sobrescreveria justamente o que se quer preservar.
#
#   CORPUS=ferramentas/medicao/corpus-160.txt IMAGEM=sgi-erp:libredwg-master \
#     ferramentas/medicao/remedir_dwg.sh ~/acervo ~/medicao-dwg-0908
CORPUS="${CORPUS:-}"

if [ -n "$CORPUS" ]; then
  [ -f "$CORPUS" ] || { echo "CORPUS '$CORPUS' não existe." >&2; exit 1; }
  cp "$CORPUS" "$LISTA"
  echo "== corpus FIXO: $(basename "$CORPUS") — sem sorteio"
  pular=0
else
  # ---- lote 0: monta a amostra, salva a lista e já mede a primeira janela ----
  # `--salvar-lista` grava o corpus INTEIRO (não a janela), então a partir daqui
  # todos os lotes falam do mesmo conjunto — e é isso que `--consolidar` confere.
  if [ ! -f "$SAIDA/lote-000.json" ]; then
    echo "== lote 000 (monta a amostra 1-em-$AMOSTRA e mede os primeiros $LOTE)"
    lote 0 "$LOTE" "lote-000" --amostra "$AMOSTRA" --salvar-lista /saida/amostra.txt \
      2>&1 | tee "$SAIDA/lote-000.log"
  else
    echo "== lote 000 já medido, pulando"
  fi
  pular="$LOTE"
fi

[ -f "$LISTA" ] || { echo "A lista da amostra não foi gravada em $LISTA." >&2; exit 1; }
TOTAL="$(wc -l < "$LISTA")"
echo "== corpus: $TOTAL arquivos · lotes de $LOTE"

# ---- lotes seguintes: mesma lista, janelas que se encaixam -------------------
while [ "$pular" -lt "$TOTAL" ]; do
  nome="$(printf 'lote-%03d' "$pular")"
  if [ -f "$SAIDA/$nome.json" ]; then
    echo "== $nome já medido, pulando"
  else
    echo "== $nome (arquivos $pular–$((pular + LOTE - 1)) de $TOTAL)"
    lote "$pular" "$LOTE" "$nome" --lista /saida/amostra.txt \
      2>&1 | tee "$SAIDA/$nome.log"
  fi
  pular=$((pular + LOTE))
done

# ---- a soma: UMA taxa sobre o corpus ----------------------------------------
# Roda sem acervo e sem motor de propósito: consolidar é aritmética sobre
# trabalho já feito, e recusa lotes de corpus ou de motor diferentes.
echo "== consolidando"
docker run --rm ${DOCKER_USER:+--user "$DOCKER_USER"} \
  -e DEBUG=True -e SECRET_KEY=medicao-local-sem-rede \
  ${COMANDO_PY:+-v "$COMANDO_PY:/app/moduloprancheta/management/commands/medir_cobertura_dwg.py:ro"} \
  -v "$SAIDA:/saida" \
  "$IMAGEM" \
  sh -c 'python manage.py medir_cobertura_dwg --consolidar /saida/lote-*.json' \
  2>&1 | tee "$SAIDA/consolidado.log"

echo
echo "Relatório do corpus: $SAIDA/consolidado.log"
echo "Registre o resultado em docs/modulos/moduloprancheta.md §4.1."
