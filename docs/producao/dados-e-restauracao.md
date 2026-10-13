# Dados — levar o banco do staging local ao servidor, backup e restauração

> Foi assim que o banco real do staging (`localhost:8443`) foi para o servidor em 12/10/2026. O mesmo
> caminho serve para qualquer restauração. **Não existe seed de demo no servidor.**

## O que viaja

Dois bancos do mesmo Postgres — `erp_db` e `iam_db` — e o volume de arquivos (`media.tgz`). O drone
(`funcoesodm`) fica de fora.

**O `spicedb_db` não viaja**, mesmo que o backup traga o `.dump`. O SpiceDB marca cada linha com o
número de transação do Postgres de origem; restaurado em outro cluster, esses números ficam "no
futuro", e tudo o que se grava depois (o schema novo, as relações) fica invisível — todo módulo
responde 403. Ele não guarda nada próprio: a IAM refaz o conteúdo inteiro a partir das tabelas dela
(passo 5).

## 1. Backup no staging local

Docker Desktop ligado e o staging de pé (`sgi-stg-postgres` healthy), na WSL:

```bash
bash infra/backup/backup.sh --prefixo sgi-stg --projeto sgi-staging --env deploy/env/staging.env
```

Gera `~/backups/sgi/<data>_sgi-stg/` com os `.dump`, `media.tgz`, `MANIFESTO.tsv` e `SHA256SUMS`.
**Não use `--manter`** sem querer: ele apaga backups antigos.

## 2. Enviar

```bash
rsync -e 'ssh -i ~/.ssh/gmaxis' -a --info=progress2 --exclude funcoesodm.dump \
  <pasta do backup>/ root@75.119.143.64:/root/restaurar/
```

## 3. As chaves vão junto (ou os dados ficam ilegíveis)

Estas três chaves protegem dado **dentro** do banco. O servidor nasceu com chaves próprias; se não
forem trocadas pelas do staging antes de subir, o que está cifrado não abre:

| Variável | O que protege |
|---|---|
| `IAM_SEGUNDO_FATOR_CHAVE` | os segredos do segundo fator (TOTP) de cada usuário |
| `SECRET_KEY` | segredos de integração cifrados pelo backend (`nucleo/cifra.py`) |
| `IAM_SECRET_KEY` | derivação do segundo fator quando a chave acima falta; consistência |

Copie as três linhas de `deploy/env/staging.env` para `deploy/env/vps.env` **sem exibir** (pipe por
SSH, sem `echo` em tela) e apague a cópia temporária depois (`shred -u`). `JWT_SECRET` e as chaves RSA
**não** precisam acompanhar: as sessões antigas simplesmente expiram.

## 4. Restaurar (túnel parado)

Com o site fora do ar para ninguém usar o meio-termo:

```bash
docker stop sgi-vps-cloudflared
docker compose ... stop erp iam worker worker-conversao beat iam-pdp pdp-invalidador spicedb
```

Para cada banco (dono: `erp_app`, `iam_app`), como superusuário do Postgres:

```bash
docker exec sgi-vps-postgres psql -U postgres -d postgres \
  -c "DROP DATABASE IF EXISTS erp_db WITH (FORCE)" \
  -c "CREATE DATABASE erp_db OWNER erp_app TEMPLATE template0"
docker exec -i sgi-vps-postgres pg_restore -U postgres -d erp_db < erp_db.dump
```

- `TEMPLATE template0` + restauração **como superusuário e sem `--no-owner`**: o dump recria o PostGIS e
  devolve cada objeto ao dono original. Com `--no-owner` as tabelas ficariam do `postgres` e o app não as
  leria.
- O `erp_db` (5,4 GB, 17 milhões de linhas na base referencial) levou ~6 min.

O `spicedb_db` é **recriado vazio** (nunca restaurado), e o cache de autorização do Redis vai junto:

```bash
docker exec sgi-vps-postgres psql -U postgres -d postgres \
  -c "DROP DATABASE IF EXISTS spicedb_db WITH (FORCE)" \
  -c "CREATE DATABASE spicedb_db OWNER spicedb_app TEMPLATE template0"
docker exec sgi-vps-postgres psql -U postgres -d spicedb_db \
  -c "REVOKE ALL ON SCHEMA public FROM PUBLIC; GRANT ALL ON SCHEMA public TO spicedb_app;"
docker exec sgi-vps-redis redis-cli -n 5 DEL authz:watch:cursor
docker exec sgi-vps-redis redis-cli -n 5 INCR authz:v:g
```

O `spicedb-migrar` do passo 5 cria as tabelas, e o `iam-pdp` grava o schema e todas as relações.

Arquivos:

```bash
docker run --rm -i -v sgi-vps_media_data:/m alpine sh -c 'tar xzf - -C /m' < media.tgz
```

## 5. Subir sem o túnel e desativar a demo

```bash
bash infra/vps/up.sh postgres redis mailpit spicedb-banco spicedb-migrar spicedb iam erp worker \
  worker-conversao beat iam-pdp pdp-invalidador react gateway
```

(o `erp` aplica as migrations novas; veja a nota do healthcheck em
[publicar-atualizacao.md](publicar-atualizacao.md)). **Antes de religar o túnel**, desative as contas
da demo que vieram do staging — têm senha conhecida no repositório e o site é público:
`demo`, `semdrone`, `acme`, `campo`, `gerente`, `admin` (senhas `*123`) e `dono` (**supervisor da
plataforma**, `dono123`). No shell do IAM: `is_active = False` para todo usuário das empresas `demo`
e `acme` e para qualquer um cuja senha confira com as da demo. Os usuários reais (empresa `eegm`)
ficam como estão.

Só então: `docker compose ... up -d cloudflared`.

## 6. Conferir

- Linhas do `MANIFESTO.tsv` contra o banco (`select count(*)` das tabelas grandes). Diferenças pequenas
  em `identity_perfil_permissoes` são normais: o sistema sincroniza permissões novas ao subir.
- Arquivos do volume = linha `media … arquivos` do manifesto.
- `docker logs sgi-vps-iam-pdp` mostra `pdp.reconciliado tenant=…` para cada empresa e nenhum
  `volta falhou`. Se aparecer `object definition … not found`, o `spicedb_db` veio de outro cluster:
  refaça o bloco do passo 4.
- Login de um usuário real pelo `https://www.gmaxis.com/`.

## Backup do servidor

`bash infra/backup/backup.sh --prefixo sgi-vps --projeto sgi-vps --env deploy/env/vps.env` gera o mesmo
pacote do staging. Copie a pasta para **fora** do servidor — um backup só na própria máquina não protege
da perda dela. *(O script ainda não foi ensaiado no VPS.)*
