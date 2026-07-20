#!/usr/bin/env bash
# ------------------------------------------------------------
# Cert TLS self-signed para o gateway de STAGING (Fase 10.7).
#
# Andaime LOCAL: em produção o TLS vem do ingress gerenciado (Cloudflare Tunnel,
# Fase 10.3.2), não deste cert. O SAN inclui localhost/127.0.0.1 para o browser e
# os scripts E2E confiarem nele (via SSL_CERT_FILE, ver validate.sh).
#
# Idempotente: não sobrescreve um cert existente (use --force para regenerar).
# ------------------------------------------------------------
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/certs"
mkdir -p "$DIR"
CRT="$DIR/fullchain.pem"
KEY="$DIR/privkey.pem"

if [[ -f "$CRT" && -f "$KEY" && "${1:-}" != "--force" ]]; then
  echo "Cert já existe em $CRT (use --force para regenerar)."
  exit 0
fi

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$KEY" -out "$CRT" -days 825 \
  -subj "/C=BR/O=SGI Staging/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,DNS:gateway,IP:127.0.0.1"

chmod 600 "$KEY"
echo "Cert self-signed gerado em $CRT (SAN: localhost, 127.0.0.1, gateway; validade 825 dias)."
