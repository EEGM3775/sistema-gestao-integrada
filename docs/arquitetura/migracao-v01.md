# Migração v01 → v02

> Como a versão atual (`02sistema_gestao_integrada`) **importa** o que vale a pena da versão
> anterior (`01sistema_gestao_integrada`, pasta irmã): princípios, decisões transversais (dados,
> virada), a régua de backend e o que ainda vale garimpar no frontend. Documento único da migração
> (Fase 7 do [roadmap](../roadmap.md), onde vive o **status**).

---

## 1. Princípios

1. **A v02 é a arquitetura-alvo, não a v01.** A v01 é um app single-tenant com deploy em GCP
   (Cloud Build + Kubernetes + ngrok); a v02 é a plataforma SaaS multi-tenant, federada e modular
   (ver [../arquitetura.md](../arquitetura.md)). **Nada da v01 redefine a v02** — só a abastece.
2. **Reaproveitar, não reescrever do zero** — exceto onde o desenho mudou de forma (ver §3).
3. **Greenfield de dados** — a v02 nasce com banco novo; **não há migração de dados** da v01 (§4).
4. **Tudo entra pelo contrato da plataforma** — todo código importado herda tenancy + entitlement +
   RBAC (ver [../acesso-e-permissoes.md](../acesso-e-permissoes.md)). Nada de login local ou token
   hardcoded da v01 sobrevive.

## 2. Mapa macro v01 → v02

| Aspecto | v01 | v02 (destino) |
|---|---|---|
| **Arquitetura** | App único (Django + React) single-tenant | Microsserviços federados + IAM central + multi-tenant |
| **Identidade/Auth** | Login local, token em localStorage/hardcoded | SSO via JWT da IAM (RS256/JWKS); `AuthContext` no front |
| **Acesso** | Todos veem tudo | Entitlement de módulo + RBAC + isolamento por tenant |
| **Frontend** | React + **Redux** + roteador próprio | React + **Context API** + gateway `/api` |
| **Backend** | Django monolítico (apps `financeiro`, `modulorh`, `moduloscm`…) | Django *resource server* + apps consolidados |
| **Banco** | Postgres single-tenant (sem `tenant_id`) | Um banco por serviço, toda entidade `TenantScopedModel` |
| **Deploy** | GCP: `cloudbuild.yaml`, `kubernetes/`, `deploy-with-ngrok.sh` | `docker compose --profile full` (11 serviços) + gateway Nginx |

### O que **NÃO** vem da v01

| Artefato v01 | Motivo |
|---|---|
| `cloudbuild.yaml`, `kubernetes/`, `deploy-with-ngrok.sh`, `nfs-provisioner`, `secrets.env` | Deploy migrou para Docker Compose + gateway ([deploy-e-seguranca.md](deploy-e-seguranca.md)) |
| `src/store/` (Redux) | A v02 usa Context API |
| Login local, `ProtectedRoute` e token hardcoded | Substituídos por SSO da IAM + `PrivateRoute`/`AuthContext` |
| Emissão de NF embutida no Django (`financeiro`) | Virou o microsserviço [funcoesnf](../modulos/funcoesnf.md) (em consolidação para Python na Fase 11) |
| **Dados** do banco da v01 | Greenfield — ver §4 |

## 3. Dados — greenfield (decisão)

**A v02 começa com banco novo. Não há ETL da v01.** O esquema da v01 é single-tenant (sem
`tenant_id`, sem mapeamento para a IAM, com `unique` globais) — encaixá-lo no modelo multi-tenant
seria um projeto à parte, não um "import".

- Tenants e usuários são (re)criados **na IAM** ([iam/seed_demo.py](../../iam/seed_demo.py) é a referência).
- Dado de produção da v01 é **recadastrado** ou **abandonado**; não há sincronização.
- Se um dia a migração de dados for necessária, é trabalho dedicado (atribuir `tenant_id`, mapear
  usuários → IAM, resolver uniques) — registrar como item de roadmap se/quando surgir.

## 4. Cutover & coexistência

1. **Coexistência** — v01 segue no ar (GCP) enquanto a v02 é abastecida módulo a módulo; ambientes
   independentes (sem banco nem identidade compartilhados).
2. **Critério de virada** — a v02 cobre os módulos em uso real **e** passa nos E2E de
   [infra/gateway/](../../infra/gateway/).
3. **Flip** — onboarding dos tenants/usuários reais na IAM e apontar o domínio para a v02.
   **Com dados reais, o flip depende das Fases 8 e 9** ([roadmap](../roadmap.md)).
4. **Rollback** — reapontar o domínio (sem estado a desfazer).
5. **Desativação** — após observação, desligar o stack GCP da v01 e arquivar o repositório.

---

## 5. Backend — a régua (caso a caso)

Para cada app da v01, classifique antes de mexer:

1. **A v02 já tem o equivalente mais completo?** → **Não portar** (o que falta é só UI).
2. **A v02 está vazia (placeholder) e a v01 tem modelos?** → candidato a porte:
   - **Portar adaptando** quando a lógica é substancial e o gap é mecânico (falta `tenant`,
     `required_module`, RLS);
   - **Reescrever sobre o contrato** quando o app da v01 é pequeno/imaturo ou o desenho mudou de
     forma — a v01 vira **referência funcional**, não código-fonte.

### 5.1 v02 já à frente — não portar backend

`moduloerp` (v02 consolidou e expandiu: contas, NF, boletos), `rh`, `modulocrm` (funil
Lead→Account→Contact→Opportunity muito mais rico), `obras`, `clientes`, `empreendimentos`,
`fornecedores`. A emissão de NF mudou de forma (microsserviço → Python na Fase 11).

### 5.2 v02 vazia — portar / adaptar da v01

| App | v01 (modelos) | Decisão | Entitlement |
|---|---|---|---|
| `moduloscm` (suprimentos) | `PedidoCompra`, `ItemPedido`, `AvaliacaoFornecedor` | **Portar adaptando** (liga a `fornecedores`) | `scm` |
| `modulosil` (estoque) | `ItemCatalogo`, `Estoque`, `ItemEstoque`, `MovimentacaoEstoque` | **Portar adaptando** | `sil` |
| `modulopdca` (planejamento/risco) | `Tarefa`, `Marco`, `Risco` | **Portar adaptando** | `pdca` |
| `modulodms` (documentos) | `Documento`, `VersaoDocumento` | **Avaliar** — pode colidir com mídia/`modulodiario` | `dms` |
| `moduloaps` (BIM/Autodesk) | `APSModel` + proxy de token OAuth | **Portar adaptando** (ver §5.3) | `aps` |
| `modulomaps` (agregador de mapa) | `Map*` (fino) | **Reescrever** como *view* sobre os módulos portados | `maps` |

> Os códigos de entitlement (`scm`, `sil`, …) ainda **não existem** no catálogo da IAM —
> registrá-los é o passo 1 do contrato ([modulos-planejados.md](../modulos/modulos-planejados.md)).
> Ordem sugerida: `scm` → `sil` → `pdca` → `dms` → `aps` → `maps`.

### 5.3 Detalhe — `moduloaps` (Autodesk Platform Services / BIM)

Visualizar plantas/modelos BIM 2D/3D de uma obra via Autodesk Viewer — o lado **projeto/planta**,
complementar ao drone (*as-built*). A v01 tem `APSModel` (FK `Obra`, `urn` unique), o proxy de
credenciais `APSTokenView` (troca `APS_CLIENT_ID/SECRET` por token OAuth 2-legged; credenciais
nunca vão ao front) e `ObraPlantasListView`. Adaptações obrigatórias no porte:

1. **Corrigir vazamento de tenant:** `ObraPlantasListView` filtra só por `obra_id` — herdar
   `TenantScopedModel` e filtrar também por tenant do JWT.
2. **APIView → ViewSet** (ou escopo manual): o `TenantScopedViewSetMixin` não se aplica a APIView.
3. **Entitlement:** `RequireModule("aps")` (registrar `aps` na IAM).
4. **`urn` unique global → por-tenant.**
5. **Credenciais:** decidir conta única da plataforma (global, secrets manager) × credencial
   por-tenant (via [moduloapi](../modulos/moduloapi.md)).

### 5.4 Padrão de adaptação de um app portado

1. **Modelos:** `models.Model` → `TenantScopedModel`; FKs de usuário → `nucleo.Usuario` (espelho
   JIT); uniques globais → `UniqueConstraint(fields=["tenant", …])`; `makemigrations`.
2. **ViewSets:** herdar `TenantScopedViewSetMixin`; declarar `required_module = "<codigo>"` +
   `RequireModule` (e `RequireRole` se houver dado sensível); **remover** auth manual/token
   hardcoded/login da v01.
3. **IAM:** registrar o `Modulo` + `AssinaturaTenant` + `AcessoUsuarioModulo`
   (referência: [iam/seed_demo.py](../../iam/seed_demo.py)).
4. **Verificar:** teste de isolamento (espelhar
   [test_tenant_isolation.py](../../backend/nucleo/test_tenant_isolation.py)) e de entitlement
   (sem módulo → 403; com → 200, espelhar `phase6_rbac_test.py`).

---

## 6. Frontend — estratégia e o que ainda vale garimpar

**Estratégia (decidida em 04/06/2026):** o frontend v02 foi **reconstruído do zero**, não portado —
o código v01 (CSS modules, Redux, auth manual) era incompatível com o design system novo
(Tailwind 4 + shadcn) e com o `AuthContext`→IAM. Da v01 preservou-se a landing (estrutura, copy,
paleta navy `#0A2A5B`, Montserrat+Roboto, `dashboard-mockup.png`). Arquitetura atual:
[../frontend.md](../frontend.md); todo componente novo segue
[../frontend-convencoes.md](../frontend-convencoes.md).

A v01 permanece útil como **mapa de funcionalidades** para o que a v02 ainda não construiu:

| Referência v01 | Serve para (v02) |
|---|---|
| `components/DashBoardWidgets/` (StatCard, AlertsTasks, ObrasGrid, RiskMatrix, cashflowchart, salesfunnel) | Dashboard de KPIs (Fases C.1/F.1) |
| `components/obra/` (ganttchart, interactivemap, kpidashboard, obratimeline, blueprint, storage) | Abas avançadas da ficha de obra (gantt, mapa, 3D) |
| `pages/CrmDashboardPage.tsx` | CRM (Fase D.3) — funil visual |
| `pages/ScmDashboardPage.tsx` / `DMSPage.tsx` | UI de SCM/DMS após o porte de backend (§5.2) |
| `pages/ExportPage.tsx` / `ImportPage.tsx` + `components/impexp/` | Import/export de dados (sem fase definida) |

Regra: nada disso é copiado literalmente — é **referência funcional**; a implementação nasce nos
padrões da v02 (rotas `/api/*` via gateway, `hasModule()` como guard, TanStack Query onde houver
dados de servidor).

## 7. Sequência geral

| Etapa | Frente |
|---|---|
| A | Frontend dos módulos cujo backend já existe (obras/dashboard/RH/CRM/ERP) — em andamento, ver [roadmap](../roadmap.md) |
| B | Backend dos módulos vazios (`scm` → `sil` → `pdca` → `dms` → `aps` → `maps`) |
| C | Frontend dos módulos portados em B (UI depois da API) |
| D | Onboarding + cutover (§4) — bloqueado pelas Fases 8 e 9 para dados reais |
