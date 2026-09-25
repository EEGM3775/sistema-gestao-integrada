#!/usr/bin/env bash
# ------------------------------------------------------------
# Sobe o stack de STAGING (Fase 10.7): modo produção, dados isolados do dev.
#
# Coexiste com o stack de dev na mesma máquina — projeto/containers/portas/volumes
# próprios (COMPOSE_PROJECT_NAME + SGI_PREFIX no deploy/env/staging.env). Depois de subir,
# rode `bash testes/seeds/seed_staging.sh` (fixtures) e `bash infra/staging/validate.sh`.
#
# Args extras são repassados ao `docker compose up` (ex.: nomes de serviço).
# ------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

[[ -f deploy/env/staging.env ]] || {
  echo "ERRO: falta deploy/env/staging.env."
  echo "  cp deploy/env/staging.env.example deploy/env/staging.env   # e troque todos os TROQUE-* por segredos fortes"
  exit 1
}
if grep -qE '=TROQUE-' deploy/env/staging.env; then
  echo "ERRO: deploy/env/staging.env ainda tem placeholders 'TROQUE-*'. Gere segredos fortes antes de subir staging."
  echo "  python -c \"import secrets; print(secrets.token_urlsafe(48))\""
  exit 1
fi
[[ -f infra/keys/jwt_private.pem ]] || {
  echo "ERRO: faltam as chaves RSA do JWT (RS256 é obrigatório em staging)."
  echo "  bash infra/keys/generate.sh"
  exit 1
}

bash infra/staging/gen-selfsigned-cert.sh

docker compose --env-file deploy/env/staging.env \
  -f deploy/compose/base.yml -f deploy/compose/staging.yml \
  --profile full up -d --build "$@"

PORT="$(grep -E '^GATEWAY_HTTPS_PORT=' deploy/env/staging.env | cut -d= -f2 | awk '{print $1}')"; PORT="${PORT:-8443}"
echo
echo "Staging subindo (aguarde os healthchecks). Entrada:"
echo "  https://localhost:${PORT}/     (cert self-signed → aceite o aviso do browser)"
echo
echo "Próximos passos:"
echo "  bash testes/seeds/seed_staging.sh       # fixtures demo/acme (uma vez)"
echo "  bash infra/staging/validate.sh   # validação integrada da leva 8→11"
