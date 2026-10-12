#!/usr/bin/env bash
# ------------------------------------------------------------
# Cria a empresa e o primeiro administrador no VPS, com senha FORTE gerada aqui.
#
#   bash infra/vps/criar-admin.sh [slug] [usuario] [email]
#   bash infra/vps/criar-admin.sh eegm egan egan@gmaxis.com      # (padrões)
#
# A senha é gravada em /root/sgi-admin-credenciais.txt (permissão 600) e NÃO é impressa.
# Leia o arquivo você mesmo, copie para o gerenciador de senhas e apague.
# No primeiro login o sistema pede o cadastro do segundo fator (app autenticador).
# ------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

SLUG="${1:-eegm}"
USUARIO="${2:-egan}"
EMAIL="${3:-egan@gmaxis.com}"
NOME="${SGI_TENANT_NOME:-EEGM Engenharia}"
SENHA="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-20)A1!"

umask 077
ARQ=/root/sgi-admin-credenciais.txt
printf 'URL:     https://app.gmaxis.com/\nEmpresa: %s\nUsuário: %s\nE-mail:  %s\nSenha:   %s\n' \
  "$SLUG" "$USUARIO" "$EMAIL" "$SENHA" > "$ARQ"

docker compose --env-file deploy/env/vps.env \
  -f deploy/compose/base.yml -f deploy/compose/vps.yml --profile full \
  exec -T \
  -e SGI_TENANT_SLUG="$SLUG" -e SGI_TENANT_NOME="$NOME" \
  -e SGI_ADMIN_USER="$USUARIO" -e SGI_ADMIN_EMAIL="$EMAIL" -e SGI_ADMIN_SENHA="$SENHA" \
  iam python manage.py shell < infra/vps/criar_admin.py

echo "Credenciais em $ARQ (leia, guarde no gerenciador de senhas e apague o arquivo)."
