#!/usr/bin/env bash
# E2E do D11 — recuperação de senha, troca de e-mail e trilha de identidade.
#
# Desenho validado aqui:
#   • UM caminho de recuperação: o token vai para o e-mail do PRÓPRIO usuário;
#     os admins do tenant recebem AVISO, nunca o link.
#   • Troca de e-mail ASSIMÉTRICA (o admin é o dono da empresa): direta quando o
#     alvo é funcionário, confirmada no endereço ANTIGO quando o alvo é admin.
#   • E-mail obrigatório e único.
#
# Endereços parametrizáveis para o roteiro valer nos DOIS ambientes — foi
# exatamente o defeito D10 (phaseC com container de dev fixo lia o banco errado
# enquanto o webhook escrevia no outro). No staging:
#   SGI_GW=https://localhost:8443 SGI_MP=http://localhost:8026 \
#   SGI_IAM_CONTAINER=sgi-stg-iam bash testes/e2e/d11_recuperacao_senha_test.sh
GW="${SGI_GW:-http://localhost:8090}"
MP="${SGI_MP:-http://localhost:8025}"
IAM_CONTAINER="${SGI_IAM_CONTAINER:-sgi-iam}"
MPPY="$(cd "$(dirname "$0")" && pwd)/d11_mailpit_helper.py"

ok=0; fail=0
check() {
  if [ "$2" = "$3" ]; then echo "  OK   $1 ($3)"; ok=$((ok + 1));
  else echo "  FALHA $1: esperado [$2], obtido [$3]"; fail=$((fail + 1)); fi
}

# -k: o staging usa cert self-signed. Inofensivo no dev (HTTP).
req()  { curl -sk "$@"; }
code() { curl -sk -o /dev/null -w '%{http_code}' "$@"; }
limpar_caixa() { curl -sk -X DELETE "$MP/api/v1/messages" >/dev/null; }
resumo() { MAILPIT_BASE="$MP" python3 "$MPPY" resumo; }
token()  { MAILPIT_BASE="$MP" python3 "$MPPY" token; }

usuario_id() {  # $1 = username
  req "$GW/iam/usuarios/" -H "Authorization: Bearer $AT" | python3 -c '
import json, sys
d = json.load(sys.stdin)
its = d["results"] if isinstance(d, dict) and "results" in d else d
alvo = sys.argv[1]
print([u["id"] for u in its if u["username"] == alvo][0])' "$1"
}

email_de() {  # $1 = id
  req "$GW/iam/usuarios/$1/" -H "Authorization: Bearer $AT" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["email"])'
}

# Estado do harness: o teto de solicitações por hora e por CONTA é silencioso
# (resposta genérica), então rodar o E2E várias vezes na mesma hora esgota a cota
# do `demo` e as checagens falhariam sem motivo real. Zeramos os tokens e o
# cooldown antes de começar — o limite de produção fica intacto, só o harness é
# que não briga consigo mesmo. (Mesma disciplina do espaçamento no validate.sh.)
echo "== Preparando estado (limpa cota e cooldown do demo) =="
docker exec -e PYTHONPATH=/app "$IAM_CONTAINER" python -c '
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iam_project.settings")
django.setup()
from identity.models import TokenRecuperacaoSenha, TrocaEmailPendente, Usuario
u = Usuario.objects.get(username="demo")
TokenRecuperacaoSenha.objects.filter(usuario=u).delete()
TrocaEmailPendente.objects.filter(usuario=u).delete()
u.set_password("demo123")
u.email = "demo@demo.com"
u.email_alterado_em = None
u.save()
print("  cota e cooldown do demo zerados")'

echo
echo "== Recuperacao: um caminho, link so para o usuario =="
limpar_caixa
check "solicitacao aceita" 200 \
  "$(code -X POST "$GW/auth/senha/esqueci/" -H 'Content-Type: application/json' -d '{"identificador":"demo"}')"
sleep 2

R=$(resumo)
check "link vai p/ o usuario"     "sim" "$(printf '%s\n' "$R" | grep '^demo@demo.com|' | cut -d'|' -f2)"
check "admin recebe aviso"        "1"   "$(printf '%s\n' "$R" | grep -c '^admin@demo.com|')"
check "aviso do admin SEM o link" "nao" "$(printf '%s\n' "$R" | grep '^admin@demo.com|' | cut -d'|' -f2)"

TK=$(token)
check "redefine sem a senha antiga" 200 \
  "$(code -X POST "$GW/auth/senha/redefinir/" -H 'Content-Type: application/json' -d "{\"token\":\"$TK\",\"nova_senha\":\"senha-nova-d11\"}")"
check "token e de uso unico" 400 \
  "$(code -X POST "$GW/auth/senha/redefinir/" -H 'Content-Type: application/json' -d "{\"token\":\"$TK\",\"nova_senha\":\"terceira-senha\"}")"
check "login com a senha nova" 200 \
  "$(code -X POST "$GW/auth/login/" -H 'Content-Type: application/json' -d '{"username":"demo","password":"senha-nova-d11"}')"
check "senha antiga nao serve mais" 401 \
  "$(code -X POST "$GW/auth/login/" -H 'Content-Type: application/json' -d '{"username":"demo","password":"demo123"}')"

echo
echo "== Enumeracao =="
a=$(req -X POST "$GW/auth/senha/esqueci/" -H 'Content-Type: application/json' -d '{"identificador":"demo"}')
b=$(req -X POST "$GW/auth/senha/esqueci/" -H 'Content-Type: application/json' -d '{"identificador":"fantasma-xyz"}')
check "resposta identica p/ conta inexistente" "iguais" "$([ "$a" = "$b" ] && echo iguais || echo diferentes)"

echo
echo "== Admin nao tem caminho de takeover =="
AT=$(req -X POST "$GW/auth/login/" -H 'Content-Type: application/json' \
     -d '{"username":"admin","password":"admin123"}' \
     | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access",""))')
VID=$(usuario_id demo)
AID=$(usuario_id admin)

req -o /dev/null -X PATCH "$GW/iam/usuarios/$VID/" -H "Authorization: Bearer $AT" \
  -H 'Content-Type: application/json' -d '{"email":"atacante@evil.com"}'
check "PATCH nao troca o e-mail" "demo@demo.com" "$(email_de "$VID")"

# Alvo ADMIN: a conta que dá acesso à empresa inteira só muda com confirmação na
# caixa que já era dela — quem sequestrar a sessão do dono não pode redirecionar
# o e-mail e, com isso, herdar a recuperação de senha de tudo.
limpar_caixa
req -o /dev/null -X POST "$GW/iam/usuarios/$AID/trocar-email/" -H "Authorization: Bearer $AT" \
  -H 'Content-Type: application/json' -d '{"email":"atacante@evil.com"}'
sleep 2
check "troca do ADMIN confirma no e-mail ANTIGO" "admin@demo.com" "$(resumo | head -1 | cut -d'|' -f1)"
check "e-mail do admin NAO mudou" "admin@demo.com" "$(email_de "$AID")"
check "acao assistida foi removida" 404 \
  "$(code -X POST "$GW/iam/usuarios/$VID/recuperacao-assistida/" -H "Authorization: Bearer $AT" \
     -H 'Content-Type: application/json' -d '{"senha_admin":"admin123"}')"

# Alvo FUNCIONARIO: troca direta. Exigir confirmação no endereço antigo travaria
# o caso que motivou o D11 (e-mail errado no cadastro / caixa inacessível).
limpar_caixa
req -o /dev/null -X POST "$GW/iam/usuarios/$VID/trocar-email/" -H "Authorization: Bearer $AT" \
  -H 'Content-Type: application/json' -d '{"email":"demo-corrigido@demo.com"}'
sleep 2
check "troca de FUNCIONARIO vale na hora" "demo-corrigido@demo.com" "$(email_de "$VID")"
check "avisa os DOIS enderecos" "2" "$(resumo | wc -l)"

echo
echo "== E-mail obrigatorio e unico =="
check "criacao sem e-mail recusada" 400 \
  "$(code -X POST "$GW/iam/usuarios/" -H "Authorization: Bearer $AT" -H 'Content-Type: application/json' \
     -d '{"username":"sem-email-teste","password":"senha-forte-1"}')"
check "e-mail duplicado recusado (400, nao 500)" 400 \
  "$(code -X POST "$GW/iam/usuarios/" -H "Authorization: Bearer $AT" -H 'Content-Type: application/json' \
     -d '{"username":"dup-teste","email":"demo-corrigido@demo.com","password":"senha-forte-1"}')"

echo
echo "== Restaurando o ambiente =="
# O roteiro troca a senha e o e-mail do `demo` de propósito (e a validação só
# vale se trocar de verdade). Devolver o estado ao final é responsabilidade do
# harness: rodar o E2E não pode deixar o ambiente com credencial diferente da
# documentada em docs/desenvolvimento.md.
docker exec -e PYTHONPATH=/app "$IAM_CONTAINER" python -c '
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iam_project.settings")
django.setup()
from identity.models import TokenRecuperacaoSenha, TrocaEmailPendente, Usuario
u = Usuario.objects.get(username="demo")
TokenRecuperacaoSenha.objects.filter(usuario=u).delete()
TrocaEmailPendente.objects.filter(usuario=u).delete()
u.set_password("demo123")
u.email = "demo@demo.com"
u.email_alterado_em = None
u.save()
a = Usuario.objects.get(username="admin")
TrocaEmailPendente.objects.filter(usuario=a).delete()
print("  demo restaurado (demo/demo123, demo@demo.com)")'
limpar_caixa

echo
echo "-------------------------------"
echo "  $ok OK / $fail FALHA"
[ "$fail" -eq 0 ]
