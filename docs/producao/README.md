# Produção — o sistema no ar (www.gmaxis.com)

> Como o SGI roda no servidor de teste real, o que sobe e o que **não** sobe, e onde estão os
> procedimentos para publicar atualização e módulo novo. Os scripts estão em
> [../../infra/vps/](../../infra/vps/README.md); o desenho do compose, em
> [../../deploy/compose/vps.yml](../../deploy/compose/vps.yml).

| Documento                                         | Para quê                                                             |
| ------------------------------------------------- | --------------------------------------------------------------------- |
| [publicar-atualizacao.md](publicar-atualizacao.md) | levar código novo e**módulo novo** ao servidor, passo a passo |
| [dados-e-restauracao.md](dados-e-restauracao.md)   | levar o banco do staging local ao servidor; backup e restauração    |
| [armadilhas.md](armadilhas.md)                     | o que já deu errado e como evitar                                    |

## O ambiente

| Item                | Valor                                                                                                                                                    |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Endereço           | **https://www.gmaxis.com/** (único endereço do app; o cookie de sessão vale para um host só) antes era app.gmaxis.com agora é www.gmaxis.com |
| Servidor            | Contabo Cloud VPS 6 — 6 vCPU, 12 GB, ~200 GB, Ubuntu 24.04, datacenter na Europa                                                                        |
| Código no servidor | `/opt/sgi` (sem `.git`: o código chega por `git archive`)                                                                                         |
| Entrada             | Cloudflare Tunnel (`cloudflared` dentro do compose) → `gateway:80`. **Nenhuma porta aberta** além do SSH                                    |
| DNS                 | Cloudflare (o e-mail do Google Workspace usa os mesmos nameservers; não mexer em MX/SPF/DKIM)                                                           |
| Acesso              | SSH**só por chave**; a senha do root está desligada. Chave `~/.ssh/gmaxis` na WSL                                                              |
| Modo                | produção:`DEBUG=False`, JWT RS256, cookies `Secure` (`__Host-`), HSTS, Celery assíncrono                                                        |
| Segredos            | `deploy/env/vps.env` — só no servidor (permissão 600), nunca no git                                                                                 |

Serviços que rodam: `postgres` (PostGIS), `redis`, `spicedb` (+banco e migração), `iam`, `iam-pdp`,
`pdp-invalidador`, `erp`, `worker`, `worker-conversao`, `beat`, `react`, `gateway`, `mailpit`,
`cloudflared`. Postgres, Redis e mailpit escutam só em `127.0.0.1` (o Docker fura o firewall ao
publicar porta, então nada é publicado).

## O que NÃO sobe para o servidor *(decisão do dono, 12/10/2026)*

O servidor roda **imagens de produção**. Não precisam ir para lá, e não devem:

- **Os testes** — `testes/` inteiro (backend, E2E, seeds). Nenhum Dockerfile nem o compose os usam.
- **O ambiente dev** — `deploy/compose/dev.yml`, `deploy/env/dev.env.example`, o `.env` local, o
  `staging.yml` e o `staging.env` (o staging local é outra máquina, com outros segredos).
- **O drone** — `funcoesODM` não roda (os cinco serviços ficam no perfil `drone`, que ninguém liga).
- **Ferramentas e rascunhos** — `ferramentas/`, `HTTP/`, `ImgDrone/`, `docs/`, `node_modules/`, e os
  `backup_*.sql` e logs soltos na raiz do repositório.
- **Dados da demo** — `demo/demo123`, `dono/dono123` e semelhantes não existem no servidor (ver
  [dados-e-restauracao.md](dados-e-restauracao.md)).

O que as imagens de fato usam, conforme os `COPY` dos Dockerfiles: `backend/`, `iam/`, `frontend/`,
`payment/`, `funcoesemail/`, `funcoesautorizacao/`, `THIRD-PARTY-LICENSES.md`; e o compose precisa de
`deploy/compose/base.yml`, `deploy/compose/vps.yml`, `infra/` e, só para o `base.yml` resolver, a
pasta `funcoesODM/`.

## Pendências conhecidas do ambiente

- E-mail real: `MAIL_*` ainda aponta para o mailpit (e-mails só visíveis por túnel SSH). A recuperação
  de senha só funciona de verdade depois de configurar um SMTP (por exemplo o do Workspace).
- Redirecionar `gmaxis.com` e `app.gmaxis.com` para `www.gmaxis.com` (regra de redirecionamento grátis
  do Cloudflare).
- Girar o token do túnel (foi colado numa conversa) e conferir a retirada de `chaves.env` de
  `/root/restaurar/` no servidor.
- Uploads acima de **100 MB** não passam pelo Cloudflare grátis (erro 413): cargas grandes
  (`IMPEXP_TETO_INFRA_ARQUIVO_MB` = 300, `ORCAMENTO_CARGA_TETO_MB` = 250) devem ser feitas dentro do servidor.
- Backup automático do servidor (o Contabo oferece, US$ 4/mês) ainda não está ligado; o
  `infra/backup/backup.sh` não foi ensaiado no VPS.
