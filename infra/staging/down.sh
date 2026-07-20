#!/usr/bin/env bash
# ------------------------------------------------------------
# Para o stack de STAGING (Fase 10.7). Args extras vão para `docker compose down`:
#   bash infra/staging/down.sh        # para os containers (mantém o banco)
#   bash infra/staging/down.sh -v     # + apaga os volumes sgi-staging_* (banco zerado)
# ------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

docker compose --env-file deploy/env/staging.env \
  -f deploy/compose/base.yml -f deploy/compose/staging.yml \
  --profile full down "$@"

echo "Staging parado. (Volumes 'sgi-staging_*' persistem; use '-v' para apagar o banco.)"
