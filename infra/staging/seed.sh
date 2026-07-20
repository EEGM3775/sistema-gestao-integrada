#!/usr/bin/env bash
# ------------------------------------------------------------
# Aplica o seed demo no STAGING (Fase 10.7) — fixtures que os E2E exigem:
# tenants demo/acme, usuários (demo/demo123, semdrone/…, admin), papéis de fábrica
# e o canal WhatsApp demo. Ordem: IAM primeiro (identidade), depois backend (negócio).
#
# Idempotente na prática (os seeds usam get_or_create / sync_authz aditivo), mas é
# um passo pós-subida único no fluxo normal.
# ------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

dc() {
  docker compose --env-file deploy/env/staging.env \
    -f deploy/compose/base.yml -f deploy/compose/staging.yml "$@"
}

echo "== Seed IAM (identidade / SSO) =="
dc exec -T iam python manage.py shell < iam/seed_demo.py

echo "== Seed backend (dados de negócio) =="
dc exec -T erp python manage.py shell < backend/seed_demo_data.py

echo "Seed aplicado. Login demo/demo123 em https://localhost:<GATEWAY_HTTPS_PORT>/"
