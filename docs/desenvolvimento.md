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
bash infra/staging/seed.sh             # fixtures demo/acme (uma vez)
bash infra/staging/validate.sh         # gate automático da leva 8→11 pelos E2E das fases
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
```

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
>    Sem privilégio de instalar, a alternativa é rodar a suíte dentro da imagem do backend (que já
>    tem tudo), montando o repositório — foi assim que a leva do Maps foi validada.

Como o Postgres é o único banco, a RLS *fail-closed* vale de fato e **todos** os testes de isolamento
(`nucleo/test_rls_fail_closed.py`, `test_tenant_isolation.py`) rodam — nenhum é pulado. A suíte roda
como o role `erp_app` (não-superuser, não-BYPASSRLS), o cenário real de produção.

O `TEST_RUNNER` do projeto ([nucleo/test_runner.py](../backend/nucleo/test_runner.py)) arma o bypass
de plataforma **em nível de sessão** durante os testes, para o seed de fixtures (que roda fora de um
request) não ser barrado pela política **fail-closed**; cada request e os testes de isolamento armam
o tenant via `is_local`, que sobrepõe a sessão — então o escopo por tenant continua sendo provado.

## Dados demo

A IAM tem um seed ([iam/seed_demo.py](../iam/seed_demo.py)) que cria os módulos, perfis e usuários de
exemplo. Atrás do gateway:

```bash
cd iam && ../.venv/bin/python manage.py shell < seed_demo.py
```

- `demo` / `demo123` — tem os módulos `crm`/`rh`/`erp_financeiro` (+ `drone`) e o papel `financeiro`.
- `semdrone` / `semdrone123` — usuário sem `drone` (e papel `operacional`), para testar 403/RBAC.

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
