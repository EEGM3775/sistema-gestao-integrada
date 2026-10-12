#!/usr/bin/env bash
# ------------------------------------------------------------
# Sobe (ou atualiza) o SGI no VPS: modo produção, sem drone, entrada pelo túnel Cloudflare.
#
#   bash infra/vps/up.sh            # builda e sobe tudo
#   bash infra/vps/up.sh erp react  # só esses serviços (rebuild de código novo)
#
# Args extras vão para o `docker compose up`. Pré-requisitos: bootstrap.sh e gerar-env.sh.
# ------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

[[ -f deploy/env/vps.env ]] || {
  echo "ERRO: falta deploy/env/vps.env. Rode:  bash infra/vps/gerar-env.sh"; exit 1; }
if grep -qE '=TROQUE-' deploy/env/vps.env; then
  echo "ERRO: deploy/env/vps.env ainda tem placeholders TROQUE-*."; exit 1
fi
[[ -f infra/keys/jwt_private.pem ]] || {
  echo "== Gerando chaves RSA do JWT (RS256) =="; bash infra/keys/generate.sh; }

# Build em paralelo estoura a memória de um VPS de 12 GB (npm + tsc + imagens Python).
export COMPOSE_PARALLEL_LIMIT=2

dc() {
  docker compose --env-file deploy/env/vps.env \
    -f deploy/compose/base.yml -f deploy/compose/vps.yml --profile full "$@"
}

dc up -d --build "$@"

echo
echo "Subindo (aguarde os healthchecks, ~2-3 min). Acompanhe com:"
echo "  docker compose --env-file deploy/env/vps.env -f deploy/compose/base.yml -f deploy/compose/vps.yml --profile full ps"
echo "Entrada pública: https://app.gmaxis.com/  (túnel: hostname app.gmaxis.com → http://gateway:80)"
echo "Primeiro acesso: bash infra/vps/criar-admin.sh"
