#!/usr/bin/env bash
# ------------------------------------------------------------
# Validação integrada contra o STAGING (Fase 10.7): a leva 8→11 e a remodelagem
# da segurança (fases 1, 4, 5 e 6) — a base do pentest.
#
# Reusa os scripts E2E (testes/e2e/, desde o D95) apontados ao gateway
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
export SGI_ACEITAR_CERT_LOCAL=1     # o Chromium do Playwright não lê o SSL_CERT_FILE
# seg5 e seg6 abrem o navegador (Playwright): o .venv do projeto o tem, o
# python3 do sistema não. O Chromium do Playwright pede libs que o WSL não traz.
if [[ -z "${PY:-}" && -x "$ROOT/.venv/bin/python" ]]; then PY="$ROOT/.venv/bin/python"; fi
PY="${PY:-python3}"
[[ -d "$HOME/.local/chromium-libs" ]] && export LD_LIBRARY_PATH="$HOME/.local/chromium-libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# phaseC faz `docker exec` no backend para checar o efeito colateral (Lead) no ORM;
# deriva o container de staging do SGI_PREFIX (senão o teste checaria o banco de DEV).
PREFIX="$(grep -E '^SGI_PREFIX=' deploy/env/staging.env 2>/dev/null | cut -d= -f2 | awk '{print $1}')"; PREFIX="${PREFIX:-sgi-stg}"
export SGI_ERP_CONTAINER="${PREFIX}-erp"
export SGI_IAM_CONTAINER="${PREFIX}-iam"   # seg6_step_up e o access_do_bff leem a IAM
# Com Secure, o cookie da sessão leva o prefixo `__Host-` (iam settings) — sem
# isto os roteiros não acham a sessão e tudo vira 401 (D228).
export SGI_SESSAO_COOKIE="__Host-sgi_sessao"

# Gate automático: scripts que falam HTTP(S) puro (rodam limpo sob TLS via urllib).
# Fora de propósito: seg6_caos (derruba SpiceDB/Redis/IAM — é do dev) e
# seg2_pdp_sombra (a fase 2, que a fase 4 aposentou).
SCRIPTS=(
  "phase4_e2e.py|Fase 4/2 — plataforma ponta a ponta (SSO + domínio único)"
  "phase5_rs256_test.py|Fase 5 — RS256/JWKS (staging é DEBUG=False → HS256 proibido)"
  "phase6_rbac_test.py|Fase 6/9 — entitlement + RBAC por permissão"
  "phase8_tenancy_test.py|Fase 8 — isolamento multi-tenant (RLS, tenant NOT NULL, uniques)"
  "phase9_auditoria_test.py|Fase 9.E — trilha de auditoria imutável (AuditLog)"
  "phaseC_whatsapp_test.py|Fase 11.3/C — WhatsApp in-process (webhook HMAC + Celery)"
  "seg1_segundo_fator_test.py|Remodelagem 1 — segundo fator (TOTP) para admin e supervisor"
  "seg4_token_enxuto_test.py|Remodelagem 4 — token enxuto, sid e PDP em todo módulo"
  "seg5_bff_test.py|Remodelagem 5 — BFF: sem token no navegador, aud por serviço, anti-CSRF"
  "seg6_step_up_test.py|Remodelagem 6 — step-up na classe C"
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
  script="${entry%%|*}"; desc="${entry##*|}"
  # Com argumentos, roda só os roteiros nomeados (ex.: `validate.sh seg5_bff_test.py`).
  if (( $# > 0 )) && [[ " $* " != *" $script "* ]]; then continue; fi
  # Espaça as corridas: o gateway limita /auth/login a 10r/m (burst 5) e cada script
  # reloga; sem pausa, os últimos scripts tomariam 429. Pausa só ENTRE scripts.
  # 12 s não bastavam: os roteiros entram várias vezes cada (e com segundo fator).
  [[ -n "$first" ]] || sleep "${ESPACO:-50}"
  first=""
  echo "── $script"
  echo "   $desc"
  if "$PY" "testes/e2e/$script"; then
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
