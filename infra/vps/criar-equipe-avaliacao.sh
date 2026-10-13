#!/usr/bin/env bash
# ------------------------------------------------------------
# Cria uma empresa de avaliação no VPS com um usuário por área:
#   admin@<slug>  contas@<slug>  obras@<slug>  engenharia@<slug>  compras@<slug>  carteira@<slug>
#
#   bash infra/vps/criar-equipe-avaliacao.sh <slug> "<Nome da empresa>"
#   bash infra/vps/criar-equipe-avaliacao.sh taluma "Taluma"
#
# A senha (a mesma para todos) é pedida no terminal e não é impressa nem gravada; para rodar
# sem pergunta, passe-a em SGI_SENHA. O admin cadastra o segundo fator no primeiro login.
# Os papéis de cada área estão em infra/vps/criar_equipe.py. Idempotente.
# ------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

SLUG="${1:?uso: criar-equipe-avaliacao.sh <slug> \"<Nome da empresa>\"}"
NOME="${2:?uso: criar-equipe-avaliacao.sh <slug> \"<Nome da empresa>\"}"
if [[ -z "${SGI_SENHA:-}" ]]; then
  read -rsp "Senha dos usuários de ${SLUG}: " SGI_SENHA
  echo
fi
[[ -n "$SGI_SENHA" ]] || { echo "Senha vazia." >&2; exit 1; }

iam() {
  docker compose --env-file deploy/env/vps.env \
    -f deploy/compose/base.yml -f deploy/compose/vps.yml --profile full \
    exec -T -e SGI_TENANT_SLUG="$SLUG" "$@" iam python manage.py shell
}

# Empresa (plano empresarial, módulos assinados, sync_authz) e o admin.
iam -e SGI_TENANT_NOME="$NOME" -e SGI_ADMIN_USER="admin@${SLUG}" \
  -e SGI_ADMIN_EMAIL="admin@${SLUG}.invalid" -e SGI_ADMIN_SENHA="$SGI_SENHA" \
  < infra/vps/criar_admin.py

# As áreas.
iam -e SGI_SENHA="$SGI_SENHA" < infra/vps/criar_equipe.py

echo "Pronto: entre em https://www.gmaxis.com/ com <area>@${SLUG}."
