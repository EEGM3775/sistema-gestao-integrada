#!/usr/bin/env bash
# ------------------------------------------------------------
# Backup completo de um ambiente (Fase 10.3): os quatro bancos e os arquivos.
#
#   bash infra/backup/backup.sh                       # dev (prefixo sgi, projeto do compose de dev)
#   bash infra/backup/backup.sh --prefixo sgi-stg --projeto sgi-staging --env deploy/env/staging.env
#   bash infra/backup/backup.sh --destino /mnt/backups --manter 7
#
# O que sai, numa pasta datada:
#   erp_db.dump · iam_db.dump · spicedb_db.dump · funcoesodm.dump   (pg_dump -Fc)
#   media.tgz                                                        (o volume de arquivos — todo
#                                                                     arquivo que o DMS registra)
#   MANIFESTO.tsv   linhas de cada tabela no instante do backup (o ensaio confere contra ele)
#   SHA256SUMS
#
# **Em produção** o banco é gerenciado e o PITR é do provedor (prod.yml); este
# script continua valendo como cópia lógica independente do provedor — é o que
# permite restaurar em OUTRO lugar — e é o único backup dos arquivos.
#
# Tudo sai por stdout do contêiner: no Docker Desktop um bind mount de caminho
# da WSL chega vazio, então nada aqui monta pasta do host.
# ------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PREFIXO=sgi
PROJETO=02sistema_gestao_integrada
ENV_FILE="$ROOT/.env"
DESTINO="${HOME}/backups/sgi"
MANTER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefixo) PREFIXO="$2"; shift 2 ;;
    --projeto) PROJETO="$2"; shift 2 ;;
    --env) ENV_FILE="$2"; shift 2 ;;
    --destino) DESTINO="$2"; shift 2 ;;
    --manter) MANTER="$2"; shift 2 ;;
    *) echo "argumento desconhecido: $1"; exit 2 ;;
  esac
done

valor() { { grep -E "^$1=" "$ENV_FILE" || true; } | tail -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*$//'; }
SUPER="$(valor POSTGRES_SUPERUSER)"; SUPER="${SUPER:-postgres}"
# Os defaults são os do compose (base.yml): o env do ambiente só os declara quando muda.
padrao() { local v; v="$(valor "$1")"; echo "${v:-$2}"; }
BANCOS=("$(padrao POSTGRES_DB erp_db)" "$(padrao IAM_POSTGRES_DB iam_db)" "$(padrao SPICEDB_DB spicedb_db)")
ODM_DB="$(padrao ODM_POSTGRES_DB funcoesodm)"; ODM_USER="$(padrao ODM_POSTGRES_USER funcoesodm)"

PG="${PREFIXO}-postgres"
ODM="${PREFIXO}-odm-db"
PASTA="$DESTINO/$(date +%Y%m%d_%H%M%S)_${PREFIXO}"
mkdir -p "$PASTA"
inicio=$(date +%s)
echo "Backup de '$PREFIXO' em $PASTA"

contar_linhas() {  # $1 contêiner, $2 usuário, $3 banco → "banco\ttabela\tlinhas"
  docker exec "$1" psql -U "$2" -d "$3" -At -F $'\t' -c "
    SELECT '$3', table_name,
           (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text
      FROM information_schema.tables
     WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
     ORDER BY table_name"
}

: > "$PASTA/MANIFESTO.tsv"
for banco in "${BANCOS[@]}"; do
  echo "  pg_dump $banco"
  docker exec "$PG" pg_dump -U "$SUPER" -Fc -d "$banco" > "$PASTA/$banco.dump"
  contar_linhas "$PG" "$SUPER" "$banco" >> "$PASTA/MANIFESTO.tsv"
done
if docker inspect "$ODM" >/dev/null 2>&1; then
  echo "  pg_dump $ODM_DB (drone)"
  docker exec "$ODM" pg_dump -U "$ODM_USER" -Fc -d "$ODM_DB" > "$PASTA/$ODM_DB.dump"
  contar_linhas "$ODM" "$ODM_USER" "$ODM_DB" >> "$PASTA/MANIFESTO.tsv"
fi

echo "  arquivos (volume ${PROJETO}_media_data)"
docker run --rm -v "${PROJETO}_media_data:/m:ro" alpine sh -c 'tar czf - -C /m . ' > "$PASTA/media.tgz"
docker run --rm -v "${PROJETO}_media_data:/m:ro" alpine sh -c 'find /m -type f | wc -l' \
  | awk '{print "media\tarquivos\t" $1}' >> "$PASTA/MANIFESTO.tsv"

( cd "$PASTA" && sha256sum *.dump media.tgz MANIFESTO.tsv > SHA256SUMS )
echo "  $(du -sh "$PASTA" | cut -f1) em $(( $(date +%s) - inicio )) s"

if [[ -n "$MANTER" ]]; then
  ls -1d "$DESTINO"/*_"$PREFIXO" 2>/dev/null | sort | head -n -"$MANTER" | while read -r velho; do
    echo "  removendo backup antigo $velho"; rm -rf "$velho"
  done
fi
echo "$PASTA"
