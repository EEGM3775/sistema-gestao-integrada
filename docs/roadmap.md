# Roadmap — status e plano

> **O que está pronto e o que falta** para concluir a plataforma (visão em
> [arquitetura.md](arquitetura.md)). Este documento guarda **só status e plano**; a narrativa datada
> de cada entrega (bugs encontrados, decisões, validações) vive no [historico.md](historico.md), e os
> achados de revisão ainda abertos em [pendencias.md](pendencias.md). A **ordem importa**: a fundação
> precede a integração — não faz sentido federar um módulo sobre SQLite e sem isolamento de tenant.

## Status das fases

| Fase | Tema | Status |
|---|---|---|
| 0 | Fundação (banco, IAM, multi-tenancy no ERP) | ✅ |
| 1 | SSO ponta a ponta (entitlement por módulo) | ✅ 31/05/2026 |
| 2 | UI integrada (gateway, domínio único) | ✅ 31/05/2026 |
| 3 | Vínculo drone ↔ obra/empreendimento | ✅ 31/05/2026 |
| 4 | Deploy unificado (`docker compose --profile full`) | ✅ 31/05/2026 |
| 5 | Endurecimento — RS256/JWKS + borda | ✅ 01/06/2026 (núcleo); operacionais → Fase 10 |
| 6 | Consolidação de identidade & RBAC de plataforma | ✅ 02/06/2026 |
| 7 | Migração v01 → v02 (frontend + backend dos módulos vazios) | 🚧 em andamento |
| 8 | Fundação de dados: Postgres real + `tenant` obrigatório + uniques por-tenant | 📋 planejado |
| 9 | RBAC de campo — mascaramento de PII por papel (RH/financeiro) | 📋 planejado |
| 10 | Observabilidade & redução de superfície operacional | 📋 planejado |
| 11 | Consolidação de linguagens (Python como stack principal) | 🚧 11.2 ✅ 03/07/2026 (funcoeslead); resto planejado |

Cada fase concluída foi validada por um script E2E em [infra/gateway/](../infra/gateway/)
(`phase4_e2e.py`, `phase5_rs256_test.py`, `phase6_rbac_test.py`).

> **Bloqueio para produção:** as Fases **8 e 9** são **pré-requisito para operar com dados reais** —
> travam o *cutover* da Fase 7 com dados de cliente. Prioridade: **8 → 9 → 10**. A Fase 10 é
> transversal e absorve as pendências operacionais da Fase 5. Os **4 achados críticos** da revisão
> v02 foram **corrigidos em 03/07/2026** (o L4 pela antecipação da Fase 11.2 — `funcoeslead`
> absorvido pelo ERP); os demais achados seguem em [pendencias.md](pendencias.md).

---

## Fases concluídas (0–6) — o que existe e o que ficou pendente

Narrativa completa de cada entrega (validações, bugs corrigidos) no [historico.md](historico.md).

### Fase 0 — Fundação

Banco por env (PostgreSQL+Redis via compose), serviço **IAM** próprio ([iam/](../iam/)) e ERP como
**resource server** com tenancy (`TenantScopedModel` + `TenantScopedViewSetMixin` + RLS).
**Pendências → Fase 8:** `tenant` nullable; `unique` globais; RLS validada só no SQLite/no-op.

### Fase 1 — SSO ponta a ponta

funcoesODM valida o JWT da IAM (JIT por `sub`, entitlement `drone` → 403); Angular captura o token;
middleware `iamAuth` nos serviços Node.
**Pendências:** entidades-filhas do drone escopadas por owner, não tenant → **Fase 8.5**; auth do
WebSocket → **Fase 10.8**.

### Fase 2 — UI integrada

Gateway nginx em `:8090` roteia tudo (`/`, `/api`, `/auth`, `/drone`, `/odm-api`, `/ws`); React com
`AuthContext`→IAM, menu condicional `hasModule`, drone em iframe com token injetado.

### Fase 3 — Vínculo drone ↔ obra

`Project` ganhou `empreendimentoId`/`obraId` + filtros + soft-unlink; contexto propagado
React→iframe→Angular.
**Pendências:** gatilho `post_delete` no ERP (auth serviço→serviço) → **Fase 10.8**; exibição na
ficha da obra no React.

### Fase 4 — Deploy unificado

`docker-compose.yml` raiz com profiles: `--profile full` sobe os 11 serviços numa rede `sgi`, com
healthchecks e migrações no start.
**Pendências:** fluxo visual upload→processa→ortofoto no browser.

### Fase 5 — Endurecimento (RS256/JWKS + borda)

IAM assina RS256 (chave em `infra/keys/`, não versionada) e publica JWKS; ERP/drone validam só com a
pública; gateway com headers de segurança + rate limit no login.
**Pendências operacionais → Fase 10:** JWK_URL + `kid` (rotação sem redeploy), LGPD, gestão de
segredos, observabilidade, DR, pentest.

### Fase 6 — Consolidação de identidade & RBAC

Login local do ERP removido; entitlement genérico `RequireModule("codigo")` + RBAC `RequireRole`
([nucleo/permissions.py](../backend/nucleo/permissions.py)); detalhe da política em
[acesso-e-permissoes.md](acesso-e-permissoes.md).
**Pendências:** remover modelos `nucleo.Perfil`/`Permissao` (migration); mascaramento de campos →
**Fase 9**; aplicar o contrato aos módulos vazios ([modulos-planejados.md](modulos/modulos-planejados.md)).

---

## Fase 7 — Migração v01 → v02 🚧

**Objetivo:** abastecer a v02 com o que vale a pena da versão anterior
(`01sistema_gestao_integrada`) — sem reescrever o que já existe nem migrar dados. Plano completo em
[arquitetura/migracao-v01.md](arquitetura/migracao-v01.md).

- **Dados:** **greenfield** — banco novo, sem ETL da v01. Tenants/usuários (re)provisionados na IAM.
- **Frontend:** reconstruído do zero (04/06/2026, base de design da v01); módulos entram um a um.
  Padrão de porte: [migracao-v01.md §6](arquitetura/migracao-v01.md).
- **Backend (caso a caso):** onde a v02 já é mais madura, nada se porta; os módulos vazios recebem a
  lógica da v01 adaptada a tenancy/entitlement/RBAC: [migracao-v01.md §5](arquitetura/migracao-v01.md).
- **Cutover:** v01 (GCP) e v02 coexistem; rollback = reapontar domínio. **Com dados reais, o cutover
  depende das Fases 8 e 9.**

### Estado dos módulos — backend (07/06/2026)

| Módulo | Entitlement | Status |
|---|---|---|
| nucleo, empreendimentos, obras, fornecedores, modulodiario, moduloapi, funcoesia | — | ✅ Completo |
| clientes | — | ✅ 04/06/2026 |
| modulocalendar | — | ✅ Completo + testes |
| rh | `rh` | ✅ Completo |
| moduloerp | `erp_financeiro` | ✅ 07/06/2026 (`Fatura`→`ContaPagar`/`ContaReceber`; +`CentroCusto`/`Rateio*`/`LoteRemessa`/`RevisaoBaixa`) |
| modulocrm | `crm` | ✅ Completo |
| funcoescobrancas (Asaas) | via `moduloerp` | ✅ MVP 08/06/2026 ([doc](modulos/funcoescobrancas.md)) |
| moduloaps · modulodms · modulopdca · moduloscm · modulosil · modulomaps | próprio | 📋 Placeholder (alvos do porte v01) |

> Rotas de apps simples registradas direto em `config/urls.py` (padrão correto, sem `urls.py` local).
> Cobertura de testes ainda pontual: `modulocalendar`, `modulocrm`, `nucleo` e `moduloerp`.
> `tenant` nullable e `unique` globais são bloqueadores da **Fase 8**.

### Estado dos módulos — frontend React (08/06/2026)

Arquitetura, design system e convenções em [frontend.md](frontend.md); fases de construção
(A/B/C/D/E/F) definidas lá na §10 equivalem às linhas abaixo.

| Fase | Módulo / componente | Status |
|---|---|---|
| A | Fundação (Tailwind 4, AuthContext, AppShell, roteamento) | ✅ 04/06/2026 |
| B | Landing + Login + Hub de módulos | ✅ 04/06/2026 |
| C.1 | Dashboard de KPIs | ❌ Pendente |
| C.2–C.4 | Empreendimentos · Obras · Clientes | ✅ 04/06/2026 |
| C.5 | Fornecedores | ✅ 05/06/2026 |
| C.6 | Diário de Obra + IA | ✅ 06/06/2026 |
| D.1.0–D.1.1 | ERP: fundação UI + Contas a pagar/receber | ✅ 07/06/2026 |
| D.1.2 | ERP: Boletos & Asaas (telas + botão gerar cobrança) | ✅ 08/06/2026 |
| D.1.3+ | ERP: notas fiscais, financeiro por obra (DRE) | ❌ ([moduloerp.md §13](modulos/moduloerp.md#13-roadmap-em-sub-fases-fase-d1x)) |
| D.2 | RH | ✅ 06/06/2026 |
| D.3 | CRM | ❌ Pendente |
| E.1–E.2 | Drone wrapper (iframe+SSO) · Calendário | ❌ Pendente |
| E.3 | SCM / SIL / PDCA / DMS / APS / Maps | ❌ Aguarda backend |
| F.1 | Dashboard de KPIs (substitui o hub) | ❌ Pendente |

> **Fluxo testável hoje** (`http://localhost:8090/`, demo/demo123): Landing → Login → Hub →
> Empreendimentos · Obras · Clientes · Fornecedores · Diário+IA · RH (4 abas, mascaramento por
> papel) · ERP (`/app/erp`: hub com KPIs/gráficos; workspaces contas a pagar/receber com baixa e
> rateio; boletos com timeline do webhook Asaas). Rebuild do container React necessário a cada
> mudança de frontend.

### Sistema de Lixo — exclusão segura 📋

Exclusão reversível com auditoria em todos os módulos; implementar após as Fases C–E do frontend.
Decisões já registradas (tabela genérica `Lixo` com payload JSON, papel `gestor_lixo`, auto-purge
configurável por tenant, IDs nunca reutilizados). Plano: [arquitetura/lixo.md](arquitetura/lixo.md).

---

## Fase 8 — Fundação de dados (Postgres real + tenancy forte) 📋

**Objetivo:** fechar o **calcanhar de Aquiles do isolamento**. Hoje `tenant` é `nullable` e os
`unique` são globais — um bug aqui é **vazamento de dados entre empresas**. RLS, `CheckConstraint` e
transações **só são reais no PostgreSQL**, não no SQLite (fallback de dev). Fase de **maior
prioridade**; precede qualquer dado real.

- **8.1 Rodar sobre Postgres:** subir a suíte no Postgres; validar migrations, `CheckConstraint`,
  `ATOMIC_REQUESTS=True` e a RLS ([nucleo/tenancy.py](../backend/nucleo/tenancy.py)).
- **8.2 `tenant` obrigatório:** FK `tenant` do `TenantScopedModel` **NOT NULL** + backfill.
- **8.3 Uniques por-tenant:** trocar cada `unique=True`/`unique_together` global por
  `UniqueConstraint(fields=["tenant", …])` nos modelos de negócio.
- **8.4 RLS ponta a ponta:** ✅ 04/07/2026 (S2) — política **fail-closed** (`migrations/0011`) +
  contexto armado na autenticação; provado no Postgres que sessão sem `app.current_tenant` não
  enxerga nem grava linha e que o acesso *cross-tenant* é bloqueado (defesa além do mixin). Bypass
  explícito (`app.rls_bypass`) para plataforma/webhook/jobs. Ver [historico.md](historico.md).
- **8.5 Tenant nas entidades-filhas do drone:** hoje escopadas por `owner`; adicionar `tenant_id`
  obrigatório às entidades do funcoesODM e validar isolamento cruzado via E2E.

**DoD:** [test_tenant_isolation.py](../backend/nucleo/test_tenant_isolation.py) verde **em
Postgres**; `phase8_tenancy_test.py` provando NOT NULL + unique por-tenant + RLS + isolamento do drone.

## Fase 9 — RBAC de campo (mascaramento de PII por papel) 📋

**Objetivo:** o RBAC atual controla **endpoints**, não **campos**. Para PII do RH
(`DadoMedicoFuncionario`, `DadoBancarioFuncionario`) e dados financeiros, mascaramento por papel é
**requisito LGPD**.

> **Desenho-alvo (AD-9):** o modelo completo — RBAC + ABAC, catálogo global de permissões, papéis
> por tenant e mascaramento de campo — está em [arquitetura/rbac-abac.md](arquitetura/rbac-abac.md).
> Esta Fase 9 é a **fatia C** daquele plano de migração.

- **9.1 Mascaramento na serialização:** redigir/ocultar campos sensíveis quando o papel do JWT não
  autoriza — em vez de barrar o endpoint inteiro.
- **9.2 Mapa de sensibilidade:** por modelo, quais campos são sensíveis e qual papel os vê.
- **9.3 Escrita também protegida:** papel sem permissão não **grava** campo sensível.
- **9.4 LGPD além do mascaramento:** direito ao esquecimento, portabilidade, procedimento de
  notificação de incidente à ANPD em até 72h.
- **9.5 Trilha de auditoria:** tabela imutável `AuditLog` (`tenant`, `usuario`, `acao`, `modelo`,
  `objeto_id`, `timestamp`) nas operações sensíveis de RH e financeiro.

**DoD:** `phase9_field_mask_test.py` verde; procedimento LGPD documentado em [infra/](../infra/);
`AuditLog` populado; exportação e exclusão de titular via endpoint admin.

## Fase 10 — Observabilidade & redução de superfície operacional 📋

**Objetivo:** 11 serviços, 3 stacks e 2 frontends é muita superfície para equipe pequena; sem
observabilidade, incidente multi-serviço é difícil de diagnosticar. Fase **transversal**; absorve as
pendências operacionais da Fase 5.

- **10.1 Observabilidade:** logs estruturados com `request_id`/`tenant_id`; métricas de
  latência/erro; healthchecks estendidos; tracing pelo gateway (opcional).
- **10.2 Reduzir superfície:** coabitar os microsserviços Node; unificar build/CI; runbook único.
- **10.3 Operacional (herdado da Fase 5):** segredos (Vault/Secrets Manager), DR (PITR + ensaios de
  restore), varredura de deps (`pip-audit`/`trivy`), pentest.
- **10.4 Supply chain (frontend):** `npm ci` + lockfile obrigatório nos Dockerfiles/CI (10.4.1);
  `npm audit --audit-level=high` bloqueando build (10.4.2); revisão dos `postinstall` existentes
  (10.4.3); política de adição de dependências com checklist versionado (10.4.4); varredura
  `trivy fs` de vuln+secrets nos dois frontends (10.4.5); cobertura Maven/Angular + Dependabot nos
  três ecossistemas (10.4.6).
- **10.5 CI/CD mínimo:** pipeline a cada push (`pytest` + `mvn test` + `npm test`) (10.5.1); gates
  de qualidade bloqueando merge em CVE alta (10.5.2); build e push de imagens em merge (10.5.3).
- **10.6 JWT em cookie HttpOnly:** hoje o token fica em `localStorage` (exposto a XSS). IAM seta
  cookie `HttpOnly`+`SameSite=Strict` (10.6.1); React deixa o `localStorage` (10.6.2); iframe do
  drone perde o `?token=` da query string (10.6.3); CSRF token nas mutações (10.6.4).
- **10.7 Ambiente de staging:** idêntico ao de produção (mesmo compose, env e banco separados);
  Fases 8, 9 e 11 validam nele antes do cutover real.
- **10.8 Auth do WebSocket e serviço→serviço:** validar JWT no handshake STOMP do `/ws` (pendência
  Fase 1); gatilho `post_delete` ERP→drone com JWT de serviço de vida curta emitido pela IAM
  (pendência Fase 3).

**DoD:** dashboard mínimo (erros+latência) e alertas; runbook em [infra/](../infra/); pipeline CI
verde com gates; `npm ci`+`npm audit`+`trivy`+`pip-audit` automatizados; JWT em cookie `HttpOnly`;
staging funcional; WebSocket e serviço→serviço autenticados; checklist de dependências documentado.

## Fase 11 — Consolidação de linguagens 📋

**Objetivo:** reduzir de **5 stacks para 3**, eliminando o Node.js do backend e planejando a saída
do Angular — sem reescrever o que funciona.

**Decisão permanente de linguagens:** **Python** (negócio, IAM, ERP, integrações — stack dominante),
**Java** (drone e novos serviços onde performance/JVM justifiquem — não é legado tolerado) e
**TypeScript** (todo o frontend). Ver AD-8 em [arquitetura.md](arquitetura.md).

Os microsserviços Node são wrappers finos sobre APIs REST — não justificam um quarto runtime:

| Serviço Node | O que faz | Equivalente Python |
|---|---|---|
| `funcoesnf` | Chama NFE.io REST para emitir NF-e/NFS-e | Celery task + `httpx` |
| `funcoeslead` | Conversão/score de lead, agenda, notificações | ✅ **Absorvido 03/07/2026**: `modulocrm/services.py` + actions, agenda in-process no `modulocalendar`, Celery task de lembretes |
| `funcoeswhatsapp` | Webhook WhatsApp → pré-cadastro do diário | Django view + Celery task |
| worker de `funcoesia` (embutido no app) | Chama o Gemini na análise de imagens | Celery task (+ LLM local — ver [plano](arquitetura/diario-ia-reintegracao.md)) |

O Angular migra por último (Leaflet, Three.js/Potree, GeoTIFF, STOMP): o gatilho é **manutenção
significativa do drone**, não uma data.

- **11.1** `funcoesnf` → Celery task em `moduloerp` (pré-req: Fase 10, Celery observável).
- **11.2** ✅ 03/07/2026 — `funcoeslead` absorvido em `modulocrm`/`modulocalendar` (antecipada
  pelo achado L4, sem esperar a 11.1).
- **11.3** `funcoeswhatsapp` → endpoint Django em `modulodiario` + Celery, e o **worker Node do
  `funcoesia`** → Celery task Python (junto com a troca Gemini → LLM local do
  [plano de reintegração](arquitetura/diario-ia-reintegracao.md)) (pré-req: 11.2).
- **11.4** Descomissionar os processos Node (containers e o worker embutido em `funcoesia`).
- **11.5** Angular → React (oportunístico, sem dependência de 11.1–11.4).

**DoD:** compose sem containers Node; os três serviços operando como Python com testes; `pip-audit`
limpo; decisão de linguagem de cada novo serviço registrada como AD em [arquitetura.md](arquitetura.md).

---

## Gaps conhecidos (resumo)

Achados das revisões técnicas com status vivo: [pendencias.md](pendencias.md).

- **Banco:** Postgres gerenciado + PITR + réplica é operação de produção; SQLite é fallback de dev —
  **Fases 8 e 10**.
- **Tenancy:** `tenant` nullable + `unique` globais + RLS não validada — **Fase 8** (calcanhar de
  Aquiles do isolamento).
- **RBAC fino / LGPD:** mascaramento de campos por papel, esquecimento, portabilidade, auditoria —
  **Fase 9**.
- **Drone:** entidades-filhas por owner (não tenant) — **8.5**; WebSocket e serviço→serviço — **10.8**.
- **Módulos vazios:** `moduloaps`/`modulodms`/`modulopdca`/`moduloscm`/`modulosil`/`modulomaps` —
  porte da **Fase 7** ([plano](arquitetura/migracao-v01.md)).
- **Frontend pendente:** dashboard de KPIs, CRM, drone wrapper, calendário — tabela da Fase 7 acima.
- **Operacional:** LGPD, secrets, observabilidade, DR, pentest — **Fase 10**.
- **Supply chain:** nenhuma varredura automatizada (npm/Maven/pip) — **10.4**.
- **CI/CD ausente:** testes manuais; gates pressupõem pipeline — **10.5**.
- **JWT em `localStorage` e em query param (iframe):** vetor XSS/log — **10.6**.
- **Staging ausente:** validações vão direto para produção — **10.7**.
- **Superfície:** 11 serviços, 3 stacks, 2 frontends — **Fases 10 e 11**.
