#!/usr/bin/env bash
# Gera o par de chaves RSA do JWT (RS256/JWKS) para desenvolvimento.
# A IAM assina com a privada; ERP e drone validam com a pública (que também é
# servida em /.well-known/jwks.json). NUNCA versionar os .pem (ver .gitignore).
#
# Uso:  bash infra/keys/generate.sh
set -euo pipefail
cd "$(dirname "$0")"
openssl genpkey -algorithm RSA -out jwt_private.pem -pkeyopt rsa_keygen_bits:2048
openssl pkey -in jwt_private.pem -pubout -out jwt_public.pem
chmod 600 jwt_private.pem
echo "Chaves geradas:"
echo "  infra/keys/jwt_private.pem  -> só a IAM (assina)"
echo "  infra/keys/jwt_public.pem   -> ERP + drone (validam) e JWKS"
