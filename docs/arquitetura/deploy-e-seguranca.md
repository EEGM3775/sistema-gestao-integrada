# Prancha — Deploy & segurança

> Como a plataforma é empacotada, posta no ar e protegida. Visão macro em
> [../arquitetura.md](../arquitetura.md) §4. Como rodar no dia a dia:
> [../desenvolvimento.md](../desenvolvimento.md). Orquestração:
> [../../docker-compose.yml](../../docker-compose.yml).

## 1. Topologia de deploy

Um único `docker-compose.yml` na raiz, **com profiles**:
- **sem perfil** → só infra: `postgres` + `redis`.
- **`--profile full`** → os **11 serviços** numa rede `sgi`: `iam`, `erp`, `react`, `funcoesodm-db`,
  `nodeodm`, `potree-converter`, `java-service`, `drone-nginx`, `gateway` (+ `postgres`, `redis`).

**Só o gateway publica porta** (`:8090`); os demais são internos à rede `sgi` e acessíveis por nome de
container. O gateway sobe apenas quando `iam`/`erp`/`java-service` estão **healthy**
(`depends_on: condition`).

| Container | Porta(s) | Volume(s) | Healthcheck |
|---|---|---|---|
| sgi-gateway | 8090→80 | nginx.unified.conf | — |
| sgi-iam | 8001 | infra/keys (ro) | `/admin/login/` |
| sgi-erp | 8000 | infra/keys (ro) | `/admin/login/` |
| sgi-react | 80 | — | — |
| sgi-odm-java | 8080 | uploads, nodeodm, potree, keys | `/api/v1/health` |
| sgi-odm-nginx | 80 | potree (ro) | — |
| sgi-nodeodm / sgi-potree | — / 5001 | nodeodm_data, potree_data | — |
| sgi-postgres | 5432 | pg_data + init | `pg_isready` |
| sgi-odm-db | 5432 | odm_db_data | `pg_isready` |
| sgi-redis | 6379 | redis_data | `redis-cli ping` |

## 2. Imagens

- **ERP** [backend/Dockerfile](../../backend/Dockerfile) — Python + libs do WeasyPrint (geração de PDF);
  roda `migrate` na subida.
- **IAM** [iam/Dockerfile](../../iam/Dockerfile) — Python + `argon2-cffi`; `migrate` na subida.
- **React** [frontend/Dockerfile](../../frontend/Dockerfile) — build Vite → estáticos servidos por nginx.
- **Drone** — `java-service`, `nodeodm` (com fix de numpy), `potree-converter`, `drone-nginx`
  (em [ImgDrone/funcoesODM/](../../ImgDrone/funcoesODM/)).
- **Pin de versão:** `Django>=5.2,<5.3` no ERP e IAM (evita regressões de major, ex.: CheckConstraint).

## 3. Gateway de borda (segurança)

[infra/gateway/nginx.unified.conf](../../infra/gateway/nginx.unified.conf):
- **Único ponto público**; roteamento em [servicos-e-integracoes.md](servicos-e-integracoes.md) §2.
- **Headers de segurança:** `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, CSP
  `frame-ancestors` (o drone roda embutido em iframe sob o mesmo domínio).
- **Rate limit** no `/auth/login` (429) contra força bruta.
- **TLS/HSTS** terminam na borda em produção; WAF e revisão final de CORS/CSP fazem parte do desenho.

## 4. Segredos & chaves

- `.env` e `infra/keys/*.pem` são **gitignored**; o repositório versiona só `.env.example` (placeholders).
- Chaves RSA do JWT geradas por [infra/keys/generate.sh](../../infra/keys/generate.sh); a **privada**
  só na IAM, a **pública** montada (ro) em ERP e drone (ver [auth-sso.md](auth-sso.md)).
- **Cofre de segredos** (Vault / Secrets Manager) injeta `JWT`/DB/API por env no runtime, com rotação —
  nada de segredo em arquivo versionado.

## 5. Modelo de ameaças (resumo)

| Ameaça | Mitigação no desenho |
|---|---|
| Token forjado | RS256: resource servers só têm a chave pública; segredo HS256 antigo → 401 |
| Acesso entre tenants | `TenantScopedViewSetMixin` (app) + **RLS** no Postgres ([dados-e-tenancy.md](dados-e-tenancy.md)) |
| Endpoint sem dono | `RequireModule`/`RequireRole` (ERP) e `MODULE_drone` (drone) → 403 |
| Acesso a objeto por ID alheio | queries escopadas por tenant; `perform_update` reforça o tenant |
| Vazamento de PII (CPF, médicos, bancários) | LGPD: cifra em repouso, mascaramento de campos por papel, mascaramento em logs |
| Brute force no login | rate limit na borda + lockout na IAM |

## 6. Escala & resiliência

- Serviços de aplicação **stateless** atrás do gateway → escala horizontal; estado em Postgres/Redis.
- **Réplica de leitura** para BI/relatórios; **Redis** para cache e fila Celery.
- **DR:** backups + **PITR** (WAL) agendados, ensaios periódicos de restore, **RPO/RTO** definidos.
- **Observabilidade:** logs estruturados centralizados, métricas e **alertas**; ações sensíveis na
  auditoria (`nucleo.LogAtividadeUsuario`).

## 7. Validação de integração

Os fluxos ponta a ponta são exercitados por scripts em [infra/gateway/](../../infra/gateway/)
(`phase4_e2e.py`, `phase5_rs256_test.py`, `phase6_rbac_test.py`). O que cada um cobre e o estado atual
estão no [../roadmap.md](../roadmap.md).
