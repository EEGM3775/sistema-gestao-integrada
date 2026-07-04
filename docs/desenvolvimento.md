# Desenvolvimento — setup & execução

> Como subir a plataforma (Docker) e como rodar os serviços Python localmente. Arquitetura em
> [arquitetura.md](arquitetura.md).

## Subir tudo com Docker (recomendado)

```bash
cp .env.example .env
bash infra/keys/generate.sh            # par de chaves RSA do JWT (RS256), em infra/keys/ (gitignored)
docker compose --profile full up -d    # sobe os 11 serviços
# abra http://localhost:8090/  → login demo/demo123
```

Sem o perfil, sobe **só a infra** (PostgreSQL + Redis), útil para rodar ERP/IAM localmente:

```bash
docker compose up -d                   # postgres + redis apenas
```

O compose raiz ([docker-compose.yml](../docker-compose.yml)) usa **profiles**: `full` liga IAM, ERP,
React, funcoesODM (java-service, drone-nginx, nodeodm, potree-converter, funcoesodm-db) e o gateway,
todos numa rede `sgi`. O gateway só sobe quando IAM/ERP/Java estão *healthy*.

## Portas

| Serviço | Porta | Observação |
|---|---|---|
| Gateway (borda) | **8090** | único ponto público; roteia tudo |
| ERP (Django) | 8000 | resource server |
| IAM | 8001 | autoridade de identidade / SSO |
| funcoesODM (Java) | 8080 | `/odm-api` → `/api/v1` |
| PostgreSQL | 5432 | bancos `iam_db` e `erp_db` |
| Redis | 6379 | cache Django + broker/result Celery |

Rotas no gateway: `/`→React · `/api`→Django · `/auth`→IAM · `/drone`→Angular · `/odm-api`→Java ·
`/ws`→Java (WebSocket). Ver [infra/gateway/nginx.unified.conf](../infra/gateway/nginx.unified.conf).

## Rodar os serviços Python localmente

> A plataforma tem **dois serviços Python**: o **ERP** ([backend/](../backend/)) e o **IAM**
> ([iam/](../iam/)). Em **dev** eles compartilham o mesmo virtualenv `.venv` na raiz; em **produção**
> cada um é isolado via Docker, com seu próprio `requirements.txt`.

```bash
# 1. variáveis
cp .env.example .env

# 2. infra de dev
docker compose up -d                   # postgres + redis

# 3. virtualenv compartilhado (.venv na raiz)
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt        # deps do ERP
.venv/bin/python -m pip install -r iam/requirements.txt    # deps do IAM

# 4. migrar e rodar cada serviço
cd backend && ../.venv/bin/python manage.py migrate && ../.venv/bin/python manage.py runserver        # ERP :8000
cd iam     && ../.venv/bin/python manage.py migrate && ../.venv/bin/python manage.py runserver 8001    # IAM :8001 (outro terminal)
```

**Por que um único venv:** o WSL/Ubuntu de dev não tem `python3-venv`/`ensurepip`, então criar um
venv novo do zero não consegue instalar o pip. Use sempre `.venv/bin/python -m pip` (o wrapper
`bin/pip` pode estar quebrado).

**Conserto do venv herdado (binários 0 byte por interação Windows↔WSL):**
```bash
rm -f .venv/bin/python* && python3 -m venv .venv   # regenera symlinks, preserva site-packages
```

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
> a cada mudança de código Python (descoberto na validação do D.1.2, ver [historico.md](historico.md)).
