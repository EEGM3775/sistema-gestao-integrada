# deploy/ — como cada ambiente sobe

Tudo que define **onde e como** o sistema roda mora aqui. Antes estava espalhado
pela raiz (`docker-compose.yml`, `docker-compose.staging.yml`, `.env.example`,
`.env.staging.example`) e não dava para responder, olhando um arquivo só, o que
muda de desenvolvimento para produção.

```
deploy/
├── compose/
│   ├── base.yml       topologia: serviços, rede, volumes, healthchecks
│   ├── dev.yml        override de DESENVOLVIMENTO  (DEBUG, Mailpit, Asaas sandbox)
│   ├── staging.yml    override de STAGING          (TLS na borda)  ← validado
│   └── prod.yml       override de PRODUÇÃO         (esqueleto)     ← NÃO validado
└── env/
    ├── dev.env.example       modelo do .env de desenvolvimento
    ├── staging.env.example   modelo do staging
    └── prod.env.example      checklist de cutover
```

## Os três ambientes

| | **dev** | **staging** | **produção** |
|---|---|---|---|
| Estado | uso diário | **validado** (`validate.sh` 6/6) | **esqueleto, nunca executado** |
| `DEBUG` | `True` | `False` | `False` |
| Assinatura JWT | HS256 (segredo) | RS256 | RS256 |
| Borda | HTTP `:8090` | HTTPS `:8443` (self-signed) | HTTPS (cert real) |
| Banco / Redis | container | container | **gerenciados**, fora do compose |
| TLS no banco | `disable` | `disable` | `verify-full` |
| E-mail | Mailpit (captura) | Mailpit (captura) | SMTP/ESP real |
| Cobrança / NF | sandbox | sandbox | **reais** |
| Celery | worker real | worker real | worker real |

O staging é deliberadamente **idêntico** a produção onde importa (modo produção,
RS256, cookies `Secure`, Celery assíncrono). A diferença estrutural é só o
certificado ser self-signed e o banco ainda ser container.

## Subir

**Desenvolvimento** — o `.env` da raiz aponta o `COMPOSE_FILE` para `base+dev`,
então os comandos de sempre continuam valendo:

```bash
cp deploy/env/dev.env.example .env      # na RAIZ (é de lá que tudo lê)
docker compose --profile full up -d     # http://localhost:8090/
```

**Staging** — pelos helpers, que também geram o certificado e rodam o gate:

```bash
cp deploy/env/staging.env.example deploy/env/staging.env   # troque os TROQUE-*
bash infra/staging/up.sh
bash infra/staging/validate.sh      # roda os E2E das fases 4/5/6/8/9/C
bash infra/staging/down.sh
```

**Produção** — não suba com o esqueleto sem antes resolver o que está listado no
topo de [compose/prod.yml](compose/prod.yml) e em
[env/prod.env.example](env/prod.env.example): segredos fora de arquivo, ingress
dos webhooks, backup/PITR com ensaio de restore e imagens versionadas por tag.

## Por que o `.env` real fica na RAIZ, e não aqui

Porque é de lá que ele é lido por três caminhos independentes: o `docker compose`
o carrega sozinho do diretório de trabalho, e o `load_dotenv()` do backend e da
IAM o procuram na raiz do repositório ao rodar **fora** do Docker. Movê-lo para
cá quebraria o desenvolvimento local sem Docker. Nesta pasta ficam os
**modelos** (`*.env.example`), versionados; o `.env` real nunca é versionado.

Exceção: o staging usa `deploy/env/staging.env`, porque é passado explicitamente
com `--env-file` pelos helpers — não depende de carga automática.

## Contexto de build

As imagens do **backend** e da **IAM** buildam com contexto na **raiz** do
repositório (não em `backend/` e `iam/`), para enxergarem o pacote compartilhado
[`funcoesemail/`](../funcoesemail/README.md). É por isso que os `Dockerfile`
copiam `backend/…` e `iam/…` com o prefixo, e que existe um
[`.dockerignore` na raiz](../.dockerignore) — sem ele, cada build arrastaria
`ImgDrone/`, o drone (`funcoesODM/`, que builda do próprio diretório), `node_modules/` e o `.git`.
