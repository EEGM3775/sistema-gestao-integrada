#!/usr/bin/env bash
# ------------------------------------------------------------
# O cofre de produção (Fase 10.3): Docker Compose secrets, um arquivo por segredo.
#
#   sudo bash infra/segredos/criar.sh                 # em /etc/sgi/segredos
#   sudo SGI_SEGREDOS=/srv/sgi/segredos bash infra/segredos/criar.sh
#
# Cria a pasta (root, 0700) e um arquivo 0400 por segredo que o `prod.yml` monta
# em /run/secrets/ de quem usa. **Nunca sobrescreve** um arquivo que já existe:
# trocar um segredo é apagar o arquivo de propósito e rodar de novo (ou editar).
#
#   - INTERNOS — gerados aqui, aleatórios: chaves do Django, a Fernet do segundo
#     fator, o token entre serviços e a chave do SpiceDB. Perder a Fernet obriga
#     todo mundo a recadastrar o segundo fator: faça backup da pasta, cifrado,
#     FORA do servidor.
#   - EXTERNOS — nascem vazios para preencher: senhas do banco gerenciado (as do
#     provedor), Asaas, NFE.io, SMTP. O serviço que precisar de um vazio se recusa
#     a subir (fail-fast S4) ou desliga a integração, conforme o caso.
# ------------------------------------------------------------
set -euo pipefail

PASTA="${SGI_SEGREDOS:-/etc/sgi/segredos}"
umask 077
mkdir -p "$PASTA"
chmod 700 "$PASTA"

aleatorio() { head -c 48 /dev/urandom | base64 | tr -d '\n=+/' | cut -c1-64; }
fernet() { head -c 32 /dev/urandom | base64 | tr '+/' '-_'; }

criar() {  # $1 nome, $2 valor
  local alvo="$PASTA/$1"
  if [[ -e "$alvo" ]]; then
    echo "  mantido   $1"
    return
  fi
  printf '%s' "$2" > "$alvo"
  chmod 400 "$alvo"
  if [[ -n "$2" ]]; then echo "  gerado    $1"; else echo "  VAZIO     $1  ← preencher"; fi
}

echo "Segredos em $PASTA"
criar secret_key "$(aleatorio)"
criar iam_secret_key "$(aleatorio)"
criar iam_segundo_fator_chave "$(fernet)"
criar service_token_secret "$(aleatorio)"
criar spicedb_chave "$(aleatorio)"
criar ia_service_secret_token "$(aleatorio)"
criar postgres_password ""
criar iam_postgres_password ""
criar asaas_api_key ""
criar asaas_webhook_token ""
criar nfe_io_api_key ""
criar mail_pass ""
echo "Pronto. Preencha os VAZIOS (printf '%s' 'valor' > arquivo) e guarde uma cópia cifrada fora do servidor."
