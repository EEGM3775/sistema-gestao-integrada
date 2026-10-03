# Desenvolvimento — setup & execução

> Como subir a plataforma (Docker) e como rodar os serviços Python localmente. Arquitetura em
> [arquitetura.md](arquitetura.md).

## Subir tudo com Docker (recomendado)

```bash
cp deploy/env/dev.env.example .env
bash infra/keys/generate.sh            # par de chaves RSA do JWT (RS256), em infra/keys/ (gitignored)
docker compose --profile full up -d    # sobe os 11 serviços
# abra http://localhost:8090/  → login demo/demo123
```

Sem o perfil, sobe **só a infra** (PostgreSQL + Redis), útil para rodar backend/IAM localmente:

```bash
docker compose up -d                   # postgres + redis apenas
```

O compose ([deploy/compose/base.yml](../deploy/compose/base.yml), ver [deploy/README.md](../deploy/README.md)) usa **profiles**: `full` liga IAM, backend,
React, funcoesODM (java-service, drone-nginx, nodeodm, potree-converter, funcoesodm-db) e o gateway,
todos numa rede `sgi`. O gateway só sobe quando IAM/backend/Java estão *healthy*.

O **drone** é versionado neste repositório, em [funcoesODM/](../funcoesODM/) (Java em
`backend/java-service`, Angular em `frontend`, `init-db`, imagens NodeODM/Potree em `docker/`); o
compose builda de lá. Mudou o drone → `docker compose ... build java-service drone-nginx`. O
`ImgDrone/` (fora do git) guarda só os fontes do ODM de terceiros e uma cópia antiga do drone que
**não** é mais usada.

## Portas

| Serviço | Porta | Observação |
|---|---|---|
| Gateway (borda) | **8090** | único ponto público; roteia tudo |
| backend (Django) | 8000 | resource server |
| IAM | 8001 | autoridade de identidade / SSO |
| funcoesODM (Java) | 8080 | `/odm-api` → `/api/v1` |
| PostgreSQL | 5432 | bancos `iam_db` e `erp_db` |
| Redis | 6379 | cache Django + broker/result Celery |

Rotas no gateway: `/`→React · `/api`→Django · `/auth`→IAM · `/drone`→Angular · `/odm-api`→Java ·
`/ws`→Java (WebSocket). Ver [infra/gateway/nginx.unified.conf](../infra/gateway/nginx.unified.conf).

## Staging (produção-like) — Fase 10.7

Ambiente **idêntico a produção** (DEBUG=False, RS256, cookies `Secure`+HSTS, gateway com
TLS, Celery assíncrono) com **dados separados**, para validar a leva 8→11 integrada antes
do cutover. Coexiste com o dev na mesma máquina (projeto/containers/portas/banco próprios).
Runbook + checklist de validação em [infra/staging/README.md](../infra/staging/README.md).

```bash
cp deploy/env/staging.env.example deploy/env/staging.env   # troque TODOS os TROQUE-* por segredos fortes
bash infra/keys/generate.sh            # chaves RSA do JWT, se ainda não existirem
bash infra/staging/up.sh               # gera o cert TLS, builda e sobe (https://localhost:8443/)
bash testes/seeds/seed_staging.sh             # fixtures demo/acme (uma vez)
bash infra/staging/validate.sh         # gate automático da leva 8→11 pelos E2E das fases
```

## Backup e ensaio de restore (Fase 10.3)

```bash
bash infra/backup/backup.sh                                   # dev: 4 bancos + arquivos, numa pasta datada em ~/backups/sgi
bash infra/backup/backup.sh --prefixo sgi-stg --projeto sgi-staging --env deploy/env/staging.env --manter 7
bash infra/backup/ensaio_restore.sh ~/backups/sgi/<pasta>     # restaura num PostGIS descartável e confere contra o manifesto
```

O backup grava `pg_dump -Fc` de `erp_db`, `iam_db`, `spicedb_db` e `funcoesodm`, o volume de
arquivos (`media.tgz`), um `MANIFESTO.tsv` com as linhas de cada tabela e `SHA256SUMS`. O ensaio
confere as somas, restaura tudo, compara tabela a tabela com o manifesto e grava `ENSAIO.txt` com o
tempo de cada etapa — a medida do RTO. Em produção o PITR do banco é do provedor; o backup lógico
continua sendo a cópia independente dele e o único dos arquivos.

## Segredos por arquivo (Fase 10.3)

Backend e IAM aceitam `NOME_FILE=/caminho` para qualquer variável `NOME` (Docker secrets, Vault
Agent, CSI do Secrets Manager): o segredo é lido do arquivo montado antes de qualquer setting. O
arquivo vence o ambiente — o `base.yml` injeta defaults de dev em toda variável, e eles não podem
ganhar do segredo. Em produção o cofre é o **Docker Compose secrets** (decisão de 03/10/2026, abaixo).

**Produção — o cofre.** SaaS num servidor: um arquivo por segredo em `/etc/sgi/segredos` (dono
root, `0700` na pasta, `0400` nos arquivos), montado pelo `prod.yml` só em `/run/secrets/` de quem
usa — nunca no `.env`, nunca em `docker inspect`, nunca na imagem. Por que não Vault: num servidor
único o cofre guardaria a própria chave no mesmo disco, e seria mais um serviço para manter no ar
sem ganho de isolamento. Criar a pasta e gerar os que nascem aleatórios:

```bash
sudo bash infra/segredos/criar.sh            # gera os internos; os de terceiros (Asaas, NFE.io, WhatsApp, SMTP) ficam vazios para preencher
```

## Imagens publicadas (Fase 10.5.3)

O workflow [`Imagens`](../.github/workflows/imagens.yml) publica no GHCR, a cada merge na `main` que
passou no CI (e a cada tag `v*`), `sgi-backend`, `sgi-iam`, `sgi-react`, `sgi-drone-api`,
`sgi-drone-web`, `sgi-nodeodm` e `sgi-potree`, com a tag imutável `sha-<commit>`. Produção não builda:

```bash
REGISTRY=ghcr.io/eegm3775 TAG=sha-abc1234 \
  docker compose --env-file deploy/env/prod.env -f deploy/compose/base.yml -f deploy/compose/prod.yml --profile full pull
docker compose ... up -d --no-build
```

## Rodar os serviços Python localmente

> A plataforma tem **dois serviços Python**: o **backend** ([backend/](../backend/)) e o **IAM**
> ([iam/](../iam/)). Em **dev** eles compartilham o mesmo virtualenv `.venv` na raiz; em **produção**
> cada um é isolado via Docker, com seu próprio `requirements.txt`.

```bash
# 1. variáveis
cp deploy/env/dev.env.example .env

# 2. infra de dev
docker compose up -d                   # postgres + redis

# 3. virtualenv compartilhado (.venv na raiz)
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt        # deps do backend
.venv/bin/python -m pip install -r iam/requirements.txt    # deps do IAM

# 4. migrar e rodar cada serviço
cd backend && ../.venv/bin/python manage.py migrate && ../.venv/bin/python manage.py runserver        # backend :8000
cd iam     && ../.venv/bin/python manage.py migrate && ../.venv/bin/python manage.py runserver 8001    # IAM :8001 (outro terminal)
```

**Por que um único venv:** o WSL/Ubuntu de dev não tem `python3-venv`/`ensurepip`, então criar um
venv novo do zero não consegue instalar o pip. Use sempre `.venv/bin/python -m pip` (o wrapper
`bin/pip` pode estar quebrado).

**Conserto do venv herdado (binários 0 byte por interação Windows↔WSL):**
```bash
rm -f .venv/bin/python* && python3 -m venv .venv   # regenera symlinks, preserva site-packages
```

## Rodar os testes

**Banco único = PostgreSQL com PostGIS** (não há mais fallback SQLite). Os defaults do `settings.py`
já apontam para o container de dev (`localhost:5432`, `erp_db`/`erp_app`), então basta ter a infra de pé:

```bash
docker compose up -d postgres                                   # se ainda não estiver rodando
# o role de app precisa criar o banco de teste (dev apenas; NÃO conceda em produção):
docker exec sgi-postgres psql -U postgres -c 'ALTER ROLE erp_app CREATEDB;'

cd backend && ../.venv/bin/python manage.py test                # roda a suíte inteira no Postgres
cd backend && ../.venv/bin/python manage.py test moduloorcamento  # só um app
```

Os testes **não** moram dentro dos apps: ficam em [`testes/`](../testes/README.md) na raiz
(`testes/backend/<app>/`, `testes/iam/`), junto das seeds e dos E2E. O `TEST_RUNNER` de cada serviço
sabe disso — sem rótulo, descobre `testes/<serviço>/` inteiro; um rótulo de app (`moduloorcamento`,
`nucleo.test_quotas`) vira `testes.backend.<...>`. Como a imagem não carrega `testes/`, rodar dentro de
um contêiner exige copiar a pasta para `/app/testes` antes.

> **MAP.0 — duas exigências novas.**
>
> 1. **A extensão espacial precisa estar no `template1`.** O runner cria o `test_erp_db` a cada
>    execução, copiando o template; sem a extensão lá, a primeira migration geométrica quebra — e
>    `erp_app` não pode criá-la (é role comum de propósito, e é disso que a RLS `FORCE` depende).
>    Ambiente novo já nasce certo pelo [init](../infra/postgres/init/01-init-databases.sh); num volume
>    antigo, uma vez à mão:
>    ```bash
>    docker compose exec postgres psql -U postgres -d template1 -c 'CREATE EXTENSION IF NOT EXISTS postgis;'
>    docker compose exec postgres psql -U postgres -d erp_db    -c 'CREATE EXTENSION IF NOT EXISTS postgis;'
>    ```
> 2. **GEOS/GDAL/PROJ no ambiente que roda o Django.** O `django.contrib.gis` os carrega por ctypes no
>    import — sem eles o processo **não sobe** (`ImproperlyConfigured`), não é degradação. Na imagem
>    Docker e no CI já vêm; para rodar a suíte no venv local:
>    ```bash
>    sudo apt-get install -y binutils gdal-bin libgeos-dev libproj-dev
>    ```

> **`unaccent` — mesma exigência, mesmo motivo (16/08/2026).** Toda busca por texto do backend é
> insensível a acento ([`nucleo/busca.py`](../backend/nucleo/busca.py)), e `CREATE EXTENSION unaccent`
> também exige SUPERUSER. Ambiente novo nasce certo pelo
> [init](../infra/postgres/init/01-init-databases.sh); **volume antigo precisa de uma passada à mão**,
> senão toda view com `search_fields` responde 500 (`FieldError` no lookup) e a suíte quebra ao criar
> o `test_erp_db`:
>
> ```bash
> docker compose exec postgres psql -U postgres -d template1 -c 'CREATE EXTENSION IF NOT EXISTS unaccent;'
> docker compose exec postgres psql -U postgres -d erp_db    -c 'CREATE EXTENSION IF NOT EXISTS unaccent;'
> ```
>    Sem privilégio de instalar, a alternativa é rodar a suíte dentro da imagem do backend (que já
>    tem tudo), montando o repositório — foi assim que a leva do Maps foi validada.

> **O PDP nos testes (remodelagem, fases 2 e 3).** Os testes de integração com o SpiceDB — a
> equivalência token × PDP da IAM (`testes/iam/identity/test_pdp.py`) e a revogação do backend
> (`testes/backend/nucleo/test_autorizacao.py`) — rodam contra o `spicedb-testes` do `dev.yml` (em
> memória; cada classe de teste usa uma chave nova, que é um banco isolado). Eles só o procuram com a
> variável definida, e sem ela são pulados **com o motivo escrito**:
>
> ```bash
> docker exec -w /tmp/sgi -e SPICEDB_TESTES_URL=http://spicedb-testes:8443 sgi-erp python manage.py test --noinput
> ```
>
> Na IAM, copie também o `funcoesautorizacao/` da raiz junto do `payment/` e do `funcoesemail/`. Mudou
> o catálogo de permissões? Regere o schema: `python funcoesautorizacao/gerar.py` (a IAM reprova a
> esteira se esquecer).

Como o Postgres é o único banco, a RLS *fail-closed* vale de fato e **todos** os testes de isolamento
(`testes/backend/nucleo/test_rls_fail_closed.py`, `test_tenant_isolation.py`) rodam — nenhum é pulado. A suíte roda
como o role `erp_app` (não-superuser, não-BYPASSRLS), o cenário real de produção.

O `TEST_RUNNER` do projeto ([nucleo/test_runner.py](../backend/nucleo/test_runner.py)) também arma o bypass
de plataforma **em nível de sessão** durante os testes, para o seed de fixtures (que roda fora de um
request) não ser barrado pela política **fail-closed**; cada request e os testes de isolamento armam
o tenant via `is_local`, que sobrepõe a sessão — então o escopo por tenant continua sendo provado.

## Dados demo

A IAM tem um seed ([testes/seeds/seed_demo.py](../testes/seeds/seed_demo.py)) que cria os módulos, perfis e usuários de
exemplo. Atrás do gateway:

```bash
docker compose exec -T iam python manage.py shell < testes/seeds/seed_demo.py
# ou, rodando a IAM local:  cd iam && ../.venv/bin/python manage.py shell < ../testes/seeds/seed_demo.py
```

| Usuário | Senha | Para que serve |
|---|---|---|
| `demo` | `demo123` | Power-user: todos os módulos do tenant e quinze papéis (inclui `planejador` + `engenharia`) |
| `campo` | `campo123` | O canteiro: **aponta e não decide** — marcação da Prancheta sem resolver (PRA.3), avanço do PDCA sem editar o plano (PDCA.2) |
| `semdrone` | `semdrone123` | Sem o módulo `drone` e com papel `operacional` — exercita 403 de camada 1 e mascaramento |
| `acme` | `acme123` | Outro tenant: é a fronteira |
| `admin` | `admin123` | Admin do tenant (gere papéis e permissões na tela) |
| `dono` | `dono123` | Supervisor da plataforma (base-mãe, incidente ANPD) — não atravessa tenant |

Os dados de negócio vêm depois, no backend:

```bash
docker compose exec -T erp python manage.py shell < testes/seeds/seed_demo_data.py   # cadastros base
docker compose exec erp python manage.py semear_carteira_demo --tenant demo     # carteira de clientes
docker compose exec erp python manage.py completar_enderecos_demo --tenant demo # endereço real + CEP + IBGE (NFS-e e CNAB)
docker compose exec erp python manage.py semear_pdca_demo --tenant demo         # obra planejada E em execução
```

O **`semear_pdca_demo`** é o que dá o que olhar no PDCA: ele planeja uma obra que **já existe** no
seed — reaproveitando as etapas e o orçamento aprovado dela —, publica o cronograma e **aponta o
avanço semana a semana** num plano que começou no passado. Sem esse passado a curva realizada é um
ponto só, e o desvio, que é o número da reunião de obra, não existe. Como ele usa uma obra de
verdade, a cobertura do orçamento **não** fecha em 100% e uma folha fica sem peso de propósito: é o
denominador que a tela existe para mostrar.

```bash
# refazer a carga (apaga cronograma, apontamentos e locais daquela obra)
docker compose exec erp python manage.py semear_pdca_demo --tenant demo --obra 7 --limpar
# obra mais adiantada / mais atrasada
docker compose exec erp python manage.py semear_pdca_demo --tenant demo --aderencia 0.95
```

Ele imprime, no fim, o que a tela deve mostrar (avanço físico, previsto até hoje, desvio, realizado
em R$ e o percentual apurado de cada etapa) e o endereço do plano — conferir a tela contra essas
linhas é o teste de fumaça mais barato do módulo.

## Ferramentas de bancada (`ferramentas/`)

Funções resolvidas à mão enquanto o módulo dono delas não existe — rodam na máquina, não sobem em
container nem entram no `.venv` da raiz. **Cada uma tem venv e `requirements.txt` próprios**, de
propósito: as dependências delas (algumas AGPL) não podem chegar às imagens do backend/IAM.

```bash
cd ferramentas/<nome>
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Índice, regra de fronteira e anatomia de uma ferramenta nova em
[ferramentas/README.md](../ferramentas/README.md).

## Frontend React (dev isolado)

```bash
cd frontend
npm install
npm run dev                            # Vite; aponta a IAM via VITE_IAM_BASE_URL (default /auth)
```

Planta do shell em [frontend.md](frontend.md); convenções de código em
[frontend-convencoes.md](frontend-convencoes.md).

## Rebuild do frontend React (gotcha de cache)

Toda mudança de frontend servida pelo gateway (`localhost:8090`) exige rebuild do container:

```bash
docker compose build --no-cache react
docker compose up -d react
```

Faça o build **isolado do serviço `react`** (não de todos de uma vez): o `--no-cache` do Docker nem
sempre invalida layers intermediários quando os fontes são modificados via filesystem do Windows
(`\\wsl.localhost\...`) — os timestamps de inode podem não ser atualizados pelo protocolo 9P.

**Sintoma residual:** mudança ainda não aparece após o rebuild. O Vite gera bundles com hash de
conteúdo (`index-<hash>.js`); se o Docker reutilizou um layer, o hash não muda e o browser responde
`304 Not Modified`. **Solução:** hard refresh — `Ctrl+Shift+R` (Windows/Linux) ou `Cmd+Shift+R` (Mac).

> O mesmo vale para o backend: o container `sgi-erp` roda imagem buildada — `docker compose build erp`
> a cada mudança de código Python (descoberto na validação do D.1.2).
