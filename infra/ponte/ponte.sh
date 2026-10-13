#!/usr/bin/env bash
# =============================================================================
# infra/ponte/ponte.sh — a ponte temporária, com prazo de validade
# =============================================================================
# Acessar o SGI de fora de casa (celular), sem abrir porta de roteador e sem
# tocar no compose:
#
#     celular -> cloudflared (URL pública, TLS) -> nginx porteiro (senha)
#                                               -> sgi-gateway:80
#
# -----------------------------------------------------------------------------
# POR QUE ESTE ARQUIVO EXISTE
# -----------------------------------------------------------------------------
# A receita nasceu em 13/09/2026 como quatro comandos colados do `terminal.txt`,
# e a regra que a encerrava — "levantou, usou, DERRUBOU" — morava na memória de
# uma pessoa. Em 14/09 o dono perguntou se a ponte estava ativa: estava, havia
# **7 horas**, sem ninguém do outro lado (D146).
#
# **O conserto não é lembrar melhor. É a ponte morrer de velhice.** Esquecê-la
# passa a derrubá-la, em vez de a manter.
#
# -----------------------------------------------------------------------------
# LEIA ANTES DE LEVANTAR — o que fica exposto
# -----------------------------------------------------------------------------
# O stack de desenvolvimento NÃO é seguro para ficar na internet:
#   * DEBUG=True nos dois Djangos -> a página de erro mostra traceback, nomes de
#     settings e a SQL que falhou;
#   * SECRET_KEY=django-insecure-dev-erp-0531 está versionada no compose;
#   * dono/dono123 é superusuário e está escrito na documentação do repositório.
#
# A senha do porteiro é a **segunda** camada (o `/api/` exige o JWT da IAM de
# qualquer jeito), mas é a única que separa a página de erro do Django de quem
# achar a URL. A URL do trycloudflare é aleatória, e "aleatória" não é "secreta":
# esses domínios são varridos — o log do D146 registrou o próprio scanner da
# Cloudflare batendo duas vezes.
#
# Já a nosso favor: `/media/` responde 404 no gateway, então arquivo de obra não
# sai pela ponte; e o Drone está barrado de propósito (`/drone/`, `/odm-api/`,
# `/ws/` caem em 403 com aviso) — consome banda e máquina demais para um túnel
# doméstico.
#
# -----------------------------------------------------------------------------
# COMO O PRAZO É IMPOSTO — duas travas, e elas são independentes
# -----------------------------------------------------------------------------
# 1. **O vigia** (`nohup` no hospedeiro) dorme até o prazo e faz o `docker rm -f`
#    dos dois containers. É ele que limpa de verdade.
# 2. **O porteiro morre sozinho**: o nginx roda sob `timeout` DENTRO do
#    container. Se o vigia morrer (o WSL do usuário desligar, por exemplo), o
#    porteiro ainda expira no mesmo instante e a URL passa a responder 502 —
#    o app deixa de ser alcançável mesmo com o túnel de pé.
#
# A segunda existe porque a primeira tem um modo de falha: o vigia é um processo
# do WSL, e o Docker Desktop roda em outra distro. Derrubar o WSL mata o vigia
# **sem** matar os containers. Uma trava só, aqui, seria confiar em quem pode
# morrer primeiro.
#
# O que nenhuma das duas cobre: uma queda do Docker Desktop leva tudo junto —
# containers e ponte —, e nada volta sozinho. É de propósito (os containers
# nascem sem `restart`), e é o comportamento certo: a ponte não deve renascer.
#
# -----------------------------------------------------------------------------
# USO
# -----------------------------------------------------------------------------
#   ./ponte.sh subir [horas] [stg] # padrão: 4h, no dev (8090); `stg` = staging (8443)
#   ./ponte.sh status             # o que está no ar e quanto falta
#   ./ponte.sh prorrogar [horas]  # re-arma o prazo (não mexe na senha nem na URL)
#   ./ponte.sh derrubar           # agora, sem esperar o prazo
# =============================================================================
set -euo pipefail

REPO="/home/eegm/projetos/02sistema_gestao_integrada"
DIR="$HOME/ponte-temporaria"
CONF="$REPO/infra/ponte/nginx.conf"
#: Para que stack a ponte aponta — `dev` (8090) ou `stg` (8443). Fica gravado
#: aqui enquanto ela vive, para o `prorrogar` recriar o porteiro no mesmo alvo.
ALVO_ARQ="$DIR/alvo"
PORTA="sgi-ponte-porta"
TUNEL="sgi-ponte-tunel"
HORAS_PADRAO=4
#: Teto duro. Acima disto não é mais "temporária" — é hospedagem de um stack de
#: desenvolvimento na internet, e aí a conversa é outra (staging de verdade).
HORAS_MAXIMO=12
#: Endereço fixo (opcional). O trycloudflare sorteia uma URL a cada subida; com
#: o domínio estático do ngrok gravado aqui (`./ponte.sh dominio <nome>`), a
#: ponte sobe sempre no mesmo link. O domínio é da conta do ngrok já configurada
#: nesta máquina (a do webhook do Asaas) e precisa ser reservado uma vez no
#: painel dela — o script não cria domínio.
DOMINIO_FIXO="$DIR/dominio"
NGROK_CONF="$HOME/.config/ngrok/ngrok.yml"

vermelho() { printf '\033[31m%s\033[0m\n' "$*"; }
verde()    { printf '\033[32m%s\033[0m\n' "$*"; }
amarelo()  { printf '\033[33m%s\033[0m\n' "$*"; }

# --- utilitários -------------------------------------------------------------

no_ar() { docker ps --filter "name=$1" --format '{{.Names}}' | grep -q "^$1$"; }

define_alvo() {
  case "$1" in
    dev) REDE="02sistema_gestao_integrada_sgi"; GATEWAY="sgi-gateway"
         COMO_SUBIR="docker compose --profile full up -d" ;;
    stg) REDE="sgi-staging_sgi"; GATEWAY="sgi-stg-gateway"
         COMO_SUBIR="bash infra/staging/up.sh" ;;
    *)   vermelho "Alvo inválido: '$1'. Use dev ou stg."; exit 1 ;;
  esac
  ALVO="$1"
}

# O nginx.conf versionado aponta para o dev. O gateway do staging só atende de
# verdade no :443 (o :80 de lá redireciona), e a IAM de lá espera a origem
# `https://localhost:8443` — então, para `stg`, o porteiro usa uma cópia derivada
# na hora, e o arquivo versionado continua um só. Se a troca não pegar (o texto
# do nginx.conf mudou), para aqui em vez de subir um porteiro apontado para o dev.
gera_conf() {
  if [ "$ALVO" = dev ]; then CONF_USADO="$CONF"; return; fi
  CONF_USADO="$DIR/nginx.$ALVO.conf"
  sed -e 's#http://sgi-gateway:80#https://sgi-stg-gateway:443#g' \
      -e 's#"http://localhost"#"https://localhost:8443"#' "$CONF" > "$CONF_USADO"
  if grep -q 'sgi-gateway:80' "$CONF_USADO" || ! grep -q 'https://localhost:8443' "$CONF_USADO"; then
    vermelho "Não consegui derivar o nginx do staging de $CONF (o texto mudou?)."
    exit 1
  fi
}

alvo_gravado() { cat "$ALVO_ARQ" 2>/dev/null || echo dev; }

valida_horas() {
  local h="$1"
  if ! printf '%s' "$h" | grep -qE '^[0-9]+$' || [ "$h" -lt 1 ] || [ "$h" -gt "$HORAS_MAXIMO" ]; then
    vermelho "Prazo inválido: '$h'. Use um inteiro de 1 a $HORAS_MAXIMO horas."
    exit 1
  fi
}

# Mata o vigia anterior, se houver. Sem isto, prorrogar deixaria dois vigias
# vivos e o mais antigo derrubaria a ponte no prazo velho.
mata_vigia() {
  if [ -f "$DIR/vigia.pid" ]; then
    kill "$(cat "$DIR/vigia.pid")" 2>/dev/null || true
    rm -f "$DIR/vigia.pid"
  fi
}

arma_vigia() {
  local segundos="$1"
  mata_vigia
  nohup sh -c "sleep $segundos; \
    docker rm -f $TUNEL $PORTA >/dev/null 2>&1; \
    rm -f '$DIR/htpasswd' '$DIR/expira-em' '$DIR/vigia.pid' '$ALVO_ARQ'; \
    echo \"\$(date '+%F %T') ponte derrubada pelo prazo\" >> '$DIR/prazo.log'" \
    </dev/null >>"$DIR/prazo.log" 2>&1 &
  echo $! > "$DIR/vigia.pid"
}

url_do_tunel() {
  docker logs "$TUNEL" 2>&1 \
    | grep -oE 'https://[a-z0-9.-]+\.(trycloudflare\.com|ngrok-free\.app|ngrok-free\.dev|ngrok\.app|ngrok\.dev)' \
    | tail -1
}

# O túnel: ngrok no domínio fixo, se houver um gravado; senão, trycloudflare.
sobe_tunel() {
  if [ -s "$DOMINIO_FIXO" ]; then
    if [ ! -f "$NGROK_CONF" ]; then
      vermelho "Há domínio fixo gravado, mas não há conta ngrok em $NGROK_CONF."
      exit 1
    fi
    docker run -d --name "$TUNEL" --network "$REDE" \
      -v "$NGROK_CONF:/etc/ngrok/ngrok.yml:ro" \
      ngrok/ngrok:latest \
      http "http://$PORTA:80" --url "https://$(cat "$DOMINIO_FIXO")" \
      --config /etc/ngrok/ngrok.yml --log stdout --log-format logfmt >/dev/null
  else
    docker run -d --name "$TUNEL" --network "$REDE" \
      cloudflare/cloudflared:latest \
      tunnel --no-autoupdate --url "http://$PORTA:80" >/dev/null
  fi
}

# --- subir -------------------------------------------------------------------

subir() {
  # `subir`, `subir 6`, `subir stg`, `subir 6 stg` — a ordem não importa.
  local horas='' alvo=dev a
  for a in "$@"; do
    case "$a" in
      dev|stg) alvo="$a" ;;
      '')      ;;
      *)       horas="$a" ;;
    esac
  done
  horas="${horas:-$HORAS_PADRAO}"
  valida_horas "$horas"
  define_alvo "$alvo"
  local segundos=$(( horas * 3600 ))

  if no_ar "$TUNEL" || no_ar "$PORTA"; then
    amarelo "A ponte já está no ar. Use 'status' para ver o prazo, ou"
    amarelo "'prorrogar' para esticá-lo — subir de novo trocaria a URL."
    amarelo "Para trocar de alvo (dev ↔ stg): 'derrubar' e subir de novo."
    exit 1
  fi
  if ! no_ar "$GATEWAY"; then
    vermelho "O stack não está de pé ($GATEWAY não responde)."
    vermelho "Suba-o primeiro: $COMO_SUBIR"
    exit 1
  fi

  mkdir -p "$DIR"
  gera_conf
  echo "$ALVO" > "$ALVO_ARQ"
  # Sobra de uma queda do Docker Desktop: os containers param (não somem) e o
  # nome ocupado faria o `docker run` abaixo falhar.
  docker rm -f "$TUNEL" "$PORTA" >/dev/null 2>&1 || true

  # A senha vive poucas horas e trafega em Basic auth (protegido pelo TLS do
  # túnel). Gerada, e não escolhida: senha reaproveitada de outra coisa é o que
  # transforma uma exposição de 4 horas num problema permanente.
  #
  # Sem cano: `tr < /dev/urandom | head -c 20` morre de SIGPIPE quando o `head`
  # fecha, e com `pipefail` o script inteiro saía com 141 antes de subir nada.
  # Lê-se um bloco finito e corta no bash.
  local senha=''
  while [ "${#senha}" -lt 20 ]; do
    senha="$senha$(head -c 256 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9')"
  done
  senha="${senha:0:20}"
  docker run --rm httpd:alpine htpasswd -nb sgi "$senha" > "$DIR/htpasswd" 2>/dev/null
  chmod 644 "$DIR/htpasswd"

  # O porteiro morre sozinho no prazo — a 2ª trava. `timeout` é o busybox do
  # nginx:alpine; quando ele dispara, o container sai e a URL passa a dar 502.
  docker run -d --name "$PORTA" --network "$REDE" \
    -v "$CONF_USADO:/etc/nginx/conf.d/default.conf:ro" \
    -v "$DIR/htpasswd:/etc/nginx/htpasswd:ro" \
    nginx:alpine \
    sh -c "timeout $segundos nginx -g 'daemon off;'" >/dev/null

  sobe_tunel

  local expira_em
  expira_em="$(date -d "+$horas hours" '+%F %T')"
  echo "$expira_em" > "$DIR/expira-em"
  arma_vigia "$segundos"

  printf 'Aguardando a URL do túnel'
  local url=''
  for _ in $(seq 1 20); do
    url="$(url_do_tunel || true)"
    [ -n "$url" ] && break
    printf '.'; sleep 2
  done
  echo

  if [ -z "$url" ]; then
    vermelho "O túnel subiu mas ainda não anunciou a URL. Veja:"
    vermelho "  docker logs $TUNEL"
  else
    verde "URL:     $url"
  fi
  verde "Usuário: sgi"
  verde "Senha:   $senha"
  verde "Expira:  $expira_em  (em ${horas}h)"
  echo
  amarelo "A ponte se derruba sozinha no prazo. Para fechar antes: ./ponte.sh derrubar"
}

# --- status ------------------------------------------------------------------

status() {
  local t=0 p=0
  no_ar "$TUNEL" && t=1
  no_ar "$PORTA" && p=1

  if [ "$t" -eq 0 ] && [ "$p" -eq 0 ]; then
    verde "A ponte está FECHADA — nada exposto."
    return 0
  fi

  amarelo "A ponte está NO AR."
  echo "  alvo:     $(alvo_gravado)"
  [ "$t" -eq 1 ] && echo "  túnel:    no ar  ($(url_do_tunel || echo 'URL ainda não anunciada'))"
  [ "$t" -eq 0 ] && echo "  túnel:    FORA — a URL já morreu"
  [ "$p" -eq 1 ] && echo "  porteiro: no ar"
  [ "$p" -eq 0 ] && echo "  porteiro: FORA — a URL responde 502 (o prazo dele já venceu)"

  if [ -f "$DIR/expira-em" ]; then
    local expira agora restam
    expira="$(cat "$DIR/expira-em")"
    agora=$(date +%s)
    restam=$(( $(date -d "$expira" +%s) - agora ))
    if [ "$restam" -gt 0 ]; then
      echo "  expira:   $expira  (faltam $(( restam / 3600 ))h $(( (restam % 3600) / 60 ))min)"
    else
      vermelho "  expira:   $expira — JÁ VENCEU e ainda há container de pé."
      vermelho "            Derrube agora: ./ponte.sh derrubar"
    fi
  else
    vermelho "  expira:   SEM PRAZO REGISTRADO."
    vermelho "            Esta ponte foi levantada fora deste script. Derrube-a."
  fi

  # O vigia é a trava que limpa de verdade. Sem ele, o porteiro ainda expira
  # sozinho (a URL passa a dar 502), mas os containers ficam de pé.
  if [ -f "$DIR/vigia.pid" ] && kill -0 "$(cat "$DIR/vigia.pid")" 2>/dev/null; then
    echo "  vigia:    vivo (pid $(cat "$DIR/vigia.pid"))"
  else
    vermelho "  vigia:    MORTO — ninguém vai limpar os containers no prazo."
    vermelho "            Re-arme com './ponte.sh prorrogar' ou derrube."
  fi
}

# --- prorrogar ---------------------------------------------------------------

prorrogar() {
  local horas="${1:-$HORAS_PADRAO}"
  valida_horas "$horas"
  if ! no_ar "$TUNEL"; then
    vermelho "O túnel não está no ar — não há o que prorrogar."
    exit 1
  fi
  # O porteiro carrega o `timeout` de quando subiu, e ele não se estica por
  # fora: prorrogar recria o container com o prazo novo. A URL **não** muda,
  # porque quem a define é o túnel, que fica de pé.
  local senha_atual="$DIR/htpasswd"
  if [ ! -f "$senha_atual" ]; then
    vermelho "O htpasswd sumiu — não dá para recriar o porteiro sem a senha."
    vermelho "Derrube e suba de novo (a URL vai mudar)."
    exit 1
  fi
  define_alvo "$(alvo_gravado)"
  gera_conf
  local segundos=$(( horas * 3600 ))
  docker rm -f "$PORTA" >/dev/null 2>&1 || true
  docker run -d --name "$PORTA" --network "$REDE" \
    -v "$CONF_USADO:/etc/nginx/conf.d/default.conf:ro" \
    -v "$senha_atual:/etc/nginx/htpasswd:ro" \
    nginx:alpine \
    sh -c "timeout $segundos nginx -g 'daemon off;'" >/dev/null

  local expira_em
  expira_em="$(date -d "+$horas hours" '+%F %T')"
  echo "$expira_em" > "$DIR/expira-em"
  arma_vigia "$segundos"
  verde "Prazo esticado até $expira_em (mais ${horas}h). A URL e a senha continuam as mesmas."
}

# --- derrubar ----------------------------------------------------------------

derrubar() {
  mata_vigia
  docker rm -f "$TUNEL" "$PORTA" >/dev/null 2>&1 || true
  rm -f "$DIR/htpasswd" "$DIR/expira-em" "$ALVO_ARQ"
  echo "$(date '+%F %T') ponte derrubada à mão" >> "$DIR/prazo.log"
  if [ -s "$DOMINIO_FIXO" ]; then
    verde "Ponte fechada. O link fixo ($(cat "$DOMINIO_FIXO")) volta na próxima subida."
  else
    verde "Ponte fechada. A URL morreu — o trycloudflare sorteia outra na próxima."
  fi
}

# --- dominio -----------------------------------------------------------------

dominio() {
  local nome="${1:-}"
  mkdir -p "$DIR"
  if [ -z "$nome" ]; then
    if [ -s "$DOMINIO_FIXO" ]; then echo "Link fixo: https://$(cat "$DOMINIO_FIXO")"
    else echo "Sem link fixo — a ponte sobe no trycloudflare, com URL nova a cada vez."; fi
    return 0
  fi
  if [ "$nome" = "-" ]; then
    rm -f "$DOMINIO_FIXO"
    verde "Link fixo apagado. A próxima subida volta ao trycloudflare."
    return 0
  fi
  nome="${nome#https://}"; nome="${nome%%/*}"
  if ! printf '%s' "$nome" | grep -qE '^[a-z0-9-]+(\.[a-z0-9-]+)*\.(ngrok-free\.app|ngrok-free\.dev|ngrok\.app|ngrok\.dev)$'; then
    vermelho "Isso não parece um domínio do ngrok: '$nome' (ex.: fulano.ngrok-free.app)."
    exit 1
  fi
  echo "$nome" > "$DOMINIO_FIXO"
  verde "Link fixo gravado: https://$nome — vale a partir da próxima subida."
}

# --- despacho ----------------------------------------------------------------

case "${1:-}" in
  subir)     shift; subir "$@" ;;
  status)    status ;;
  prorrogar) shift; prorrogar "${1:-}" ;;
  derrubar)  derrubar ;;
  dominio)   shift; dominio "${1:-}" ;;
  *)
    cat <<AJUDA
ponte.sh — a ponte temporária do SGI, com prazo de validade

  ./ponte.sh subir [horas] [stg] levanta (padrão ${HORAS_PADRAO}h no dev, teto ${HORAS_MAXIMO}h; stg = staging)
  ./ponte.sh status             o que está no ar e quanto falta
  ./ponte.sh prorrogar [horas]  estica o prazo; URL e senha não mudam
  ./ponte.sh derrubar           fecha agora
  ./ponte.sh dominio [nome|-]   mostra, grava ou apaga (-) o link fixo do ngrok

A ponte expira sozinha. Esquecê-la a fecha — é o conserto do D146.
AJUDA
    ;;
esac
