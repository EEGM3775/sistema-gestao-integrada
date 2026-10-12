# VPS — teste real em www.gmaxis.com

Topologia do staging (modo produção) numa máquina só, **sem o drone**, com entrada pelo
**Cloudflare Tunnel**: nenhuma porta pública além do SSH. Compose: [base.yml](../../deploy/compose/base.yml)
+ [vps.yml](../../deploy/compose/vps.yml) · gateway: [nginx.vps.conf](../gateway/nginx.vps.conf).

| Script | Para quê |
|---|---|
| `bootstrap.sh` | uma vez, como root: Docker, swap 4 GB, firewall (só SSH), fail2ban, SSH sem senha |
| `gerar-env.sh` | cria `deploy/env/vps.env` com segredos fortes (pede só o token do túnel) |
| `up.sh` | builda e sobe; reexecute após cada atualização de código |
| `criar-admin.sh` | cria a empresa e o admin com senha forte (sem as senhas da demo) |

## Ordem

1. **Cloudflare (painel):** Zero Trust → Networks → Tunnels → criar túnel → copiar o token →
   *Public Hostname*: `www.gmaxis.com` → serviço `HTTP` `gateway:80`. O DNS do `www` é criado sozinho.
2. **Servidor:** `git clone` em `/opt/sgi` (branch `drone-no-repositorio`), depois
   `bash infra/vps/bootstrap.sh`, `CLOUDFLARE_TUNNEL_TOKEN=… bash infra/vps/gerar-env.sh`,
   `bash infra/vps/up.sh`, `bash infra/vps/criar-admin.sh`.
3. Abra `https://www.gmaxis.com/`, entre com a credencial de `/root/sgi-credenciais-<usuario>.txt` e
   cadastre o segundo fator.

## Operação

- Estado: `docker compose --env-file deploy/env/vps.env -f deploy/compose/base.yml -f deploy/compose/vps.yml --profile full ps`
- Atualizar: `git pull && bash infra/vps/up.sh`.
- Backup: `bash infra/backup/backup.sh --prefixo sgi-vps --projeto sgi-vps --env deploy/env/vps.env --manter 7`
  (copie a pasta gerada para fora do servidor).
- Os e-mails do sistema caem no mailpit (só no loopback): `ssh -L 8025:127.0.0.1:8025 root@IP` e abra
  `http://localhost:8025`. Para enviar e-mail de verdade, troque `MAIL_*` no `vps.env` por um SMTP real.
- Os dados da demo (`demo/demo123`, `dono/dono123`) **não** são semeados: a internet não pode ter senha conhecida.
