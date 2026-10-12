#!/usr/bin/env bash
# ------------------------------------------------------------
# Prepara um VPS Ubuntu 24.04 limpo para rodar o SGI (rodar UMA vez, como root).
#
#   bash infra/vps/bootstrap.sh
#
# Faz: atualização do sistema, Docker + Compose (versão atual), swap de 4 GB, firewall (só SSH),
# fail2ban, atualizações de segurança automáticas e SSH sem senha.
#
# Trava de segurança: só desliga o login por senha se já houver chave em
# /root/.ssh/authorized_keys — senão você se trancaria para fora do servidor.
# ------------------------------------------------------------
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "ERRO: rode como root."; exit 1; }
export DEBIAN_FRONTEND=noninteractive

if [[ ! -s /root/.ssh/authorized_keys ]]; then
  echo "ERRO: /root/.ssh/authorized_keys vazio. Instale sua chave (ssh-copy-id) antes — senão o"
  echo "      passo que desliga a senha te trancaria para fora."
  exit 1
fi

echo "== Sistema =="
apt-get update -qq
apt-get -y -qq upgrade
apt-get -y -qq install ca-certificates curl git ufw fail2ban unattended-upgrades openssl rsync

echo "== Swap 4 GB (rede de proteção para picos de build/worker) =="
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
sysctl -w vm.swappiness=10 >/dev/null
echo 'vm.swappiness=10' > /etc/sysctl.d/99-sgi-swap.conf

echo "== Docker =="
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
# `!override` no vps.yml exige Compose >= 2.24.4.
docker compose version

echo "== Firewall: só SSH (o app entra pelo túnel de SAÍDA do Cloudflare, sem porta aberta) =="
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw --force enable

echo "== SSH: só por chave =="
# O prefixo `00-` é obrigatório: o sshd vale a PRIMEIRA diretiva que lê, e o `50-cloud-init.conf`
# da imagem liga a senha. Com `99-` o arquivo era ignorado e a senha seguia aberta.
cat > /etc/ssh/sshd_config.d/00-sgi.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
sshd -t
systemctl reload ssh

echo "== fail2ban e atualizações automáticas =="
systemctl enable --now fail2ban
dpkg-reconfigure -f noninteractive unattended-upgrades

mkdir -p /opt/sgi
echo
echo "Pronto. Memória / swap:"; free -h | sed -n 1,3p
echo "Próximo passo: levar o código para /opt/sgi e rodar infra/vps/gerar-env.sh."
