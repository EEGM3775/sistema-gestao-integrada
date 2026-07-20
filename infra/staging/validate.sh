#!/usr/bin/env bash
# ------------------------------------------------------------
# Validação integrada da leva 8→11 contra o STAGING (Fase 10.7).
#
# Reusa os scripts E2E das fases (infra/gateway/phase*.py) apontados ao gateway
# HTTPS de staging via SGI_GW. Confia no cert self-signed exportando SSL_CERT_FILE
# (o ssl padrão do Python/urllib o honra) — sem desabilitar verificação.
#
# Pré-requisitos: `bash infra/staging/up.sh` (stack no ar) + `seed.sh` (fixtures).
# ------------------------------------------------------------
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

CERT="$ROOT/infra/staging/certs/fullchain.pem"
[[ -f "$CERT" ]] || { echo "ERRO: cert de staging ausente ($CERT). Rode infra/staging/up.sh."; exit 1; }

PORT="$(grep -E '^GATEWAY_HTTPS_PORT=' deploy/env/staging.env 2>/dev/null | cut -d= -f2 | awk '{print $1}')"; PORT="${PORT:-8443}"
export SGI_GW="https://localhost:${PORT}"
export SSL_CERT_FILE="$CERT"        # urllib/ssl confiam no cert self-signed
export REQUESTS_CA_BUNDLE="$CERT"   # idem, caso algum script use requests
PY="${PY:-python3}"

# phaseC faz `docker exec` no backend para checar o efeito colateral (Lead) no ORM;
# deriva o container de staging do SGI_PREFIX (senão o teste checaria o banco de DEV).
PREFIX="$(grep -E '^SGI_PREFIX=' deploy/env/staging.env 2>/dev/null | cut -d= -f2 | awk '{print $1}')"; PREFIX="${PREFIX:-sgi-stg}"
export SGI_ERP_CONTAINER="${PREFIX}-erp"

# Gate automático: scripts que falam HTTP(S) puro (rodam limpo sob TLS via urllib).
SCRIPTS=(
  "phase4_e2e.py|Fase 4/2 — plataforma ponta a ponta (SSO + domínio único)"
  "phase5_rs256_test.py|Fase 5 — RS256/JWKS (staging é DEBUG=False → HS256 proibido)"
  "phase6_rbac_test.py|Fase 6/9 — entitlement + RBAC por permissão"
  "phase8_tenancy_test.py|Fase 8 — isolamento multi-tenant (RLS, tenant NOT NULL, uniques)"
  "phase9_auditoria_test.py|Fase 9.E — trilha de auditoria imutável (AuditLog)"
  "phaseC_whatsapp_test.py|Fase 11.3/C — WhatsApp in-process (webhook HMAC + Celery)"
)

echo "=================================================================="
echo " Validação integrada 8→11 — STAGING (modo produção)"
echo " Gateway: $SGI_GW"
echo " Cert   : $CERT"
echo "=================================================================="
echo

pass=0; fail=0; failed=()
first=1
for entry in "${SCRIPTS[@]}"; do
  # Espaça as corridas: o gateway limita /auth/login a 10r/m (burst 5) e cada script
  # reloga; sem pausa, os últimos scripts tomariam 429. Pausa só ENTRE scripts.
  [[ -n "$first" ]] || sleep 12
  first=""
  script="${entry%%|*}"; desc="${entry##*|}"
  echo "── $script"
  echo "   $desc"
  if "$PY" "infra/gateway/$script"; then
    echo "   ✅ PASS"; pass=$((pass+1))
  else
    echo "   ❌ FAIL"; fail=$((fail+1)); failed+=("$script")
  fi
  echo
done

echo "=================================================================="
echo " Resumo: $pass verde / $fail vermelho"
echo "=================================================================="
echo "Fora do gate automático (validar à parte — ver infra/staging/README.md):"
echo "  • phase10_8_service_ws_test.py — service-token na borda roda sob HTTPS;"
echo "    o frame /ws usa socket cru (sem TLS): aponte SGI_WS_PORT a um listener em claro."
echo "  • Fluxo de sessão 10.6 (cookies Secure + refresh) — checar no browser: login →"
echo "    F5 mantém sessão (bootstrap /auth/refresh) → trocar senha revoga em ≤5 min."

if (( fail > 0 )); then
  echo
  printf 'Falharam: %s\n' "${failed[*]}"
  exit 1
fi
echo
echo "Leva 8→11 validada no staging."
