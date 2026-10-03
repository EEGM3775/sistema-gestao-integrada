#!/usr/bin/env bash
# ------------------------------------------------------------
# Ensaio de restore (Fase 10.3): backup que nunca foi restaurado não é backup.
#
#   bash infra/backup/ensaio_restore.sh ~/backups/sgi/20261003_120000_sgi
#
# Sobe um PostGIS descartável (sem porta publicada, sem volume nomeado),
# restaura os dumps da pasta, extrai o media.tgz e confere tudo contra o
# MANIFESTO.tsv que o backup gravou: cada tabela tem de existir e ter as mesmas
# linhas; os arquivos, a mesma contagem. O relatório (ENSAIO.txt, na pasta)
# traz o tempo de cada etapa — é a medida do RTO, que só existe medida.
#
# Diferença de linhas numa tabela de movimento (sessão, notificação, fila) é
# esperada: o manifesto é contado logo depois do dump, e o sistema seguiu
# vivo. O ensaio a mostra e não reprova por ela; reprova por tabela que
# sumiu, banco que não restaurou ou soma de verificação que não bate.
# ------------------------------------------------------------
set -uo pipefail

PASTA="${1:?uso: ensaio_restore.sh <pasta do backup>}"
IMAGEM="postgis/postgis:16-3.4"
NOME="sgi-ensaio-restore-$$"
RELATORIO="$PASTA/ENSAIO.txt"
falhas=0
inicio=$(date +%s)

log() { echo "$*" | tee -a "$RELATORIO"; }
: > "$RELATORIO"
log "Ensaio de restore — $(date '+%d/%m/%Y %H:%M') — $PASTA"

( cd "$PASTA" && sha256sum -c SHA256SUMS --quiet ) || { log "XX soma de verificação não bate"; exit 1; }
log "ok  somas de verificação"

limpar() { docker rm -f "$NOME" >/dev/null 2>&1; }
trap limpar EXIT
docker run -d --name "$NOME" -e POSTGRES_PASSWORD="ensaio-$$" "$IMAGEM" >/dev/null
for _ in $(seq 1 60); do docker exec "$NOME" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done
# O init do PostGIS reinicia o servidor uma vez; esperar o segundo "pronto".
sleep 3
for _ in $(seq 1 60); do docker exec "$NOME" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done

for dump in "$PASTA"/*.dump; do
  banco="$(basename "$dump" .dump)"
  t0=$(date +%s)
  docker exec "$NOME" createdb -U postgres "$banco"
  # --no-owner/--no-privileges: os roles de app não existem aqui, e o ensaio
  # confere DADO, não permissão (a RLS é coberta pela suíte e pelo phase8).
  if docker exec -i "$NOME" pg_restore -U postgres -d "$banco" --no-owner --no-privileges < "$dump" 2>"$PASTA/restore_$banco.err"; then
    log "ok  restaurado $banco em $(( $(date +%s) - t0 )) s"
  else
    # pg_restore sai com erro também por avisos (extensão já existente); o
    # que decide é a conferência de linhas abaixo.
    log "!!  $banco restaurou com avisos ($(wc -l < "$PASTA/restore_$banco.err") linhas em restore_$banco.err) em $(( $(date +%s) - t0 )) s"
  fi
done

restaurado="$(mktemp)"
for dump in "$PASTA"/*.dump; do
  banco="$(basename "$dump" .dump)"
  docker exec "$NOME" psql -U postgres -d "$banco" -At -F $'\t' -c "
    SELECT '$banco', table_name,
           (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text
      FROM information_schema.tables
     WHERE table_schema = 'public' AND table_type = 'BASE TABLE'" >> "$restaurado"
done

t0=$(date +%s)
arquivos=$(docker exec -i "$NOME" sh -c 'mkdir -p /tmp/m && tar xzf - -C /tmp/m && find /tmp/m -type f | wc -l' < "$PASTA/media.tgz")
echo -e "media\tarquivos\t$arquivos" >> "$restaurado"
log "ok  arquivos extraídos em $(( $(date +%s) - t0 )) s"

tabelas=0; iguais=0; diferentes=""; sumidas=""
while IFS=$'\t' read -r banco tabela linhas; do
  tabelas=$((tabelas + 1))
  achado="$(awk -F'\t' -v b="$banco" -v t="$tabela" '$1==b && $2==t {print $3}' "$restaurado")"
  if [[ -z "$achado" ]]; then
    sumidas+=" $banco.$tabela"
  elif [[ "$achado" == "$linhas" ]]; then
    iguais=$((iguais + 1))
  else
    diferentes+=" $banco.$tabela($linhas→$achado)"
  fi
done < "$PASTA/MANIFESTO.tsv"
rm -f "$restaurado"

log "ok  $iguais de $tabelas tabelas com as mesmas linhas do manifesto (inclui a contagem de arquivos)"
[[ -n "$diferentes" ]] && log "!!  diferem (movimento entre o dump e a contagem):$diferentes"
if [[ -n "$sumidas" ]]; then log "XX  não restauradas:$sumidas"; falhas=1; fi

log "Tempo total (RTO medido nesta máquina): $(( $(date +%s) - inicio )) s"
if [[ $falhas -eq 0 ]]; then log "RESULTADO: restore ensaiado com sucesso"; else log "RESULTADO: FALHOU"; fi
exit $falhas
