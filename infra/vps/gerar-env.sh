#!/usr/bin/env bash
# ------------------------------------------------------------
# Cria deploy/env/vps.env a partir do exemplo, trocando todo `TROQUE-*` por segredo forte.
#
#   CLOUDFLARE_TUNNEL_TOKEN=eyJ... bash infra/vps/gerar-env.sh
#
# Se a variável não vier, o token é pedido sem eco. Recusa sobrescrever um vps.env existente:
# os segredos do banco são gravados no volume na primeira subida, e trocá-los depois deixaria
# o Postgres com uma senha e o app com outra. Para recomeçar do zero, apague o volume antes.
# ------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

EXEMPLO=deploy/env/vps.env.example
ALVO=deploy/env/vps.env

[[ -f "$EXEMPLO" ]] || { echo "ERRO: falta $EXEMPLO"; exit 1; }
[[ ! -e "$ALVO" ]] || { echo "ERRO: $ALVO já existe — não vou sobrescrever (ver comentário no topo)."; exit 1; }

TOKEN="${CLOUDFLARE_TUNNEL_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  read -r -s -p "Token do túnel Cloudflare (não aparece enquanto digita): " TOKEN
  echo
fi
[[ -n "$TOKEN" ]] || { echo "ERRO: token vazio."; exit 1; }

umask 077
cp "$EXEMPLO" "$ALVO"

forte()  { openssl rand -hex 32; }
fernet() { openssl rand -base64 32 | tr '+/' '-_'; }   # 32 bytes em base64 url-safe = chave Fernet

while IFS= read -r nome; do
  case "$nome" in
    IAM_SEGUNDO_FATOR_CHAVE) valor="$(fernet)" ;;
    CLOUDFLARE_TUNNEL_TOKEN) valor="$TOKEN" ;;
    *)                       valor="$(forte)" ;;
  esac
  # `|` como delimitador: o token do túnel é base64 e pode ter `/`.
  sed -i "s|^${nome}=TROQUE-.*|${nome}=${valor}|" "$ALVO"
done < <(grep -oE '^[A-Z0-9_]+=TROQUE-' "$EXEMPLO" | cut -d= -f1)

if grep -qE '=TROQUE-' "$ALVO"; then
  echo "ERRO: sobrou placeholder em $ALVO:"; grep -nE '=TROQUE-' "$ALVO"; exit 1
fi
chmod 600 "$ALVO"
echo "OK: $ALVO criado (permissão 600). Guarde uma cópia num gerenciador de senhas."
echo "Próximo passo: bash infra/vps/up.sh"
