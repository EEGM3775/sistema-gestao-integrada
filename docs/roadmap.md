# Roadmap — status e plano

> **O que está pronto e o que falta** para concluir a plataforma (visão em
> [arquitetura.md](arquitetura.md)). Este documento guarda **só status e plano**; a narrativa datada
> de cada entrega (bugs encontrados, decisões, validações) e os
> achados de revisão ainda abertos em [pendencias.md](pendencias.md). A **ordem importa**: a fundação
> precede a integração — não faz sentido federar um módulo sobre SQLite e sem isolamento de tenant.

## Status das fases

| Fase | Tema                                                                             | Status                                               |
| ---- | -------------------------------------------------------------------------------- | ---------------------------------------------------- |
| 0    | Fundação (banco, IAM, multi-tenancy no ERP)                                    | ✅                                                   |
| 1    | SSO ponta a ponta (entitlement por módulo)                                      | ✅ 31/05/2026                                        |
| 2    | UI integrada (gateway, domínio único)                                          | ✅ 31/05/2026                                        |
| 3    | Vínculo drone ↔ obra/empreendimento                                            | ✅ 31/05/2026                                        |
| 4    | Deploy unificado (`docker compose --profile full`)                             | ✅ 31/05/2026                                        |
| 5    | Endurecimento — RS256/JWKS + borda                                              | ✅ 01/06/2026 (núcleo); operacionais → Fase 10     |
| 6    | Consolidação de identidade & RBAC de plataforma                                | ✅ 02/06/2026                                        |
| 7    | Migração v01 → v02 (frontend + backend dos módulos vazios)                   | 🚧 em andamento                                      |
| 8    | Fundação de dados: Postgres real +`tenant` obrigatório + uniques por-tenant | ✅ 04/07/2026 (8.1–8.5)                             |
| 9    | RBAC de campo — catálogo de permissões + mascaramento de PII                  | 🚧 A–E ✅ 11/07 (suíte 71/71 + E2E 15/15); D3/D4/D5 ✅ 11/07; residual D6 |
| 10   | Observabilidade & redução de superfície operacional                           | 📋 planejado                                         |
| 11   | Consolidação de linguagens (Python como stack principal)                       | 🚧 11.2 ✅ 03/07/2026 (funcoeslead); resto planejado |

Cada fase concluída foi validada por um script E2E em [infra/gateway/](../infra/gateway/)
(`phase4_e2e.py`, `phase5_rs256_test.py`, `phase6_rbac_test.py`).

> **Bloqueio para produção:** as Fases **8 e 9** são **pré-requisito para operar com dados reais** —
> travam o *cutover* da Fase 7 com dados de cliente. Prioridade: **8 → 9 → 10**. A Fase 10 é
> transversal e absorve as pendências operacionais da Fase 5. Os **4 achados críticos** da revisão
> v02 foram **corrigidos em 03/07/2026** (o L4 pela antecipação da Fase 11.2 — `funcoeslead`
> absorvido pelo ERP); os demais achados seguem em [pendencias.md](pendencias.md).

---

## Fases concluídas (0–6) — o que existe e o que ficou pendente

Narrativa completa de cada entrega (validações, bugs corrigidos) no histórico do git (`git log`).

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

| Módulo                                                                          | Entitlement        | Status                                                                                                                     |
| -------------------------------------------------------------------------------- | ------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| nucleo, empreendimentos, obras, fornecedores, modulodiario, moduloapi, funcoesia | —                 | ✅ Completo                                                                                                                |
| clientes                                                                         | —                 | ✅ 04/06/2026                                                                                                              |
| modulocalendar                                                                   | —                 | ✅ Completo + testes                                                                                                       |
| rh                                                                               | `rh`             | ✅ Completo                                                                                                                |
| moduloerp                                                                        | `erp_financeiro` | ✅ 07/06/2026 (`Fatura`→`ContaPagar`/`ContaReceber`; +`CentroCusto`/`Rateio*`/`LoteRemessa`/`RevisaoBaixa`) |
| modulocrm                                                                        | `crm`            | ✅ Completo                                                                                                                |
| funcoescobrancas (Asaas)                                                         | via`moduloerp`   | ✅ MVP 08/06/2026 ([doc](modulos/funcoescobrancas.md))                                                                      |
| moduloaps · modulodms · modulopdca · moduloscm · modulosil · modulomaps     | próprio           | 📋 Placeholder (alvos do porte v01)                                                                                        |

> Rotas de apps simples registradas direto em `config/urls.py` (padrão correto, sem `urls.py` local).
> Cobertura de testes ainda pontual: `modulocalendar`, `modulocrm`, `nucleo` e `moduloerp`.
> `tenant` nullable e `unique` globais são bloqueadores da **Fase 8**.

### Estado dos módulos — frontend React (08/06/2026)

Arquitetura, design system e convenções em [frontend.md](frontend.md); fases de construção
(A/B/C/D/E/F) definidas lá na §10 equivalem às linhas abaixo.

| Fase         | Módulo / componente                                       | Status                                                                         |
| ------------ | ---------------------------------------------------------- | ------------------------------------------------------------------------------ |
| A            | Fundação (Tailwind 4, AuthContext, AppShell, roteamento) | ✅ 04/06/2026                                                                  |
| B            | Landing + Login + Hub de módulos                          | ✅ 04/06/2026                                                                  |
| C.1          | Dashboard de KPIs                                          | ❌ Pendente                                                                    |
| C.2–C.4     | Empreendimentos · Obras · Clientes                       | ✅ 04/06/2026                                                                  |
| C.5          | Fornecedores                                               | ✅ 05/06/2026                                                                  |
| C.6          | Diário de Obra + IA                                       | ✅ 06/06/2026                                                                  |
| D.1.0–D.1.1 | ERP: fundação UI + Contas a pagar/receber                | ✅ 07/06/2026                                                                  |
| D.1.2        | ERP: Boletos & Asaas (telas + botão gerar cobrança)      | ✅ 08/06/2026                                                                  |
| D.1.3+       | ERP: notas fiscais, financeiro por obra (DRE)              | ❌ ([moduloerp.md §13](modulos/moduloerp.md#13-roadmap-em-sub-fases-fase-d1x)) |
| D.2          | RH                                                         | ✅ 06/06/2026                                                                  |
| D.3          | CRM                                                        | ✅ 05/07/2026 (dashboard + leads + accounts + contacts + opportunities)                                           |
| E.1–E.2     | Drone wrapper (iframe+SSO) · Calendário                  | ❌ Pendente                                                                    |
| E.3          | SCM / SIL / PDCA / DMS / APS / Maps                        | ❌ Aguarda backend                                                             |
| F.1          | Dashboard de KPIs (substitui o hub)                        | ❌ Pendente                                                                    |

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

## Fase 8 — Fundação de dados (Postgres real + tenancy forte) ✅

**Objetivo:** fechar o **calcanhar de Aquiles do isolamento**. Hoje `tenant` é `nullable` e os
`unique` são globais — um bug aqui é **vazamento de dados entre empresas**. RLS, `CheckConstraint` e
transações **só são reais no PostgreSQL**, não no SQLite (fallback de dev). Fase de **maior
prioridade**; precede qualquer dado real.

- **8.1 Rodar sobre Postgres:** ✅ 04/07/2026 — suíte completa **verde sobre Postgres** (37/37) como
  o role `erp_app` (não-superuser/não-BYPASSRLS, `FORCE ROW LEVEL SECURITY`), com a política
  fail-closed valendo de fato; SQLite segue verde (5 RLS pulados). Entregou: `TEST_RUNNER` ciente da
  RLS ([nucleo/test_runner.py](../backend/nucleo/test_runner.py)) que arma o bypass de plataforma por
  sessão para o seed; `arm_rls_for_tenant` passou a **desligar** o bypass (armar um tenant é
  autocontido — corrige vazamento de contexto entre métodos de `TestCase`, achado ao rodar sob PG);
  teste do S1 lê a linha do outro tenant sob `rls_bypass()`. Ver
  [desenvolvimento.md](desenvolvimento.md#rodar-os-testes).
- **8.2 `tenant` obrigatório:** ✅ 04/07/2026 — FK `tenant` do `TenantScopedModel` agora **NOT
  NULL** (11 migrações `AlterField`, uma por app, sobre ~40 modelos concretos). Backfill defensivo
  ([nucleo/migrations/0012](../backend/nucleo/migrations/0012_backfill_tenant.py)) roda antes do
  `SET NOT NULL` (todas dependem dele), sob bypass da RLS (a fail-closed esconde linha `tenant` NULL
  do role de app): órfãs → tenant único; aborta se ambíguo (0 ou >1 tenants). Aplicado no `erp_db`
  (0 órfãs) e provado no test DB (suíte 37/37). `perform_create` + RLS + coluna NOT NULL = 3 camadas.
- **8.3 Uniques por-tenant:** ✅ 04/07/2026 — cada `unique=True` global escalar em modelo de
  negócio (CPF/CNPJ, e-mail, razão social, nº/chave de NF, nome de cargo/obra/conta, etc.) virou
  `UniqueConstraint(fields=["tenant", …])` (7 migrações). Como o DRF descarta o validador quando o
  constraint inclui `tenant`, um mixin reutilizável
  ([nucleo/tenant_validators.py](../backend/nucleo/tenant_validators.py)) reintroduz a checagem
  **escopada ao tenant do request** (deriva o validador das próprias `UniqueConstraint`) → duplicata
  no mesmo tenant dá **400 limpo**, não 500. Necessário também porque no SQLite a RLS é no-op. Os
  `unique_together` sobre FKs já tenant-scoped (ex.: `(obra, nome_etapa)`) permaneceram — a FK-pai já
  amarra o tenant. Provado (`test_tenant_isolation::PerTenantUniquenessTests`): mesmo CPF em tenants
  distintos OK; duplicado no mesmo tenant → 400. Aplicado no `erp_db`; suíte 39/39 (PG e SQLite).
- **8.4 RLS ponta a ponta:** ✅ 04/07/2026 (S2) — política **fail-closed** (`migrations/0011`) +
  contexto armado na autenticação; provado no Postgres que sessão sem `app.current_tenant` não
  enxerga nem grava linha e que o acesso *cross-tenant* é bloqueado (defesa além do mixin). Bypass
  explícito (`app.rls_bypass`) para plataforma/webhook/jobs.
- **8.5 Tenant nas entidades-filhas do drone:** ✅ 04/07/2026 — `tenant_id` **NOT NULL** nas 6
  filhas do funcoesODM (`Chunk`/`ChunkImage`/`Measurement`/`Annotation`/`ProcessingTask`/
  `ProjectImage`), herdado do projeto-pai na criação. Isolamento imposto na **borda** por um
  `ProjectTenantInterceptor` (`config/`): todo `/api/v1/projects/{projectId}/**` exige que o projeto
  da URL pertença ao tenant do token → senão **404** (fechou vazamento real: `Measurement`/`Annotation`
  só validavam existência do projeto, não o tenant). Backfill idempotente no start promove a coluna a
  NOT NULL onde não há nulos. Seed ganhou 2º tenant `acme` (drone) p/ o E2E. Também travado o anexo de
  imagem cross-projeto em `addImagesToChunk`. Ver [phase8_tenancy_test.py](../infra/gateway/phase8_tenancy_test.py).

**DoD:** [test_tenant_isolation.py](../backend/nucleo/test_tenant_isolation.py) verde **em
Postgres**; `phase8_tenancy_test.py` provando NOT NULL + unique por-tenant + RLS + isolamento do drone.

## Fase 9 — RBAC de campo: catálogo de permissões + mascaramento de PII 🚧

**Objetivo:** o RBAC atual controla **endpoints** por *nome de papel* (tudo-ou-nada), não **campos**.
Para PII do RH (`DadoMedicoFuncionario`, `DadoBancarioFuncionario`) e dados financeiros, mascaramento
por permissão é **requisito LGPD**. Hoje só há um mascaramento *ad-hoc* (`salario_base` num único
serializer) e papéis são strings mágicas — três exigidos no código, dois nunca provisionados (origem
dos **403** na ficha do funcionário).

> **Desenho-alvo (AD-9):** RBAC + ABAC, catálogo global de permissões, papéis por tenant e
> mascaramento de campo em [arquitetura/rbac-abac.md](arquitetura/rbac-abac.md). A Fase 9 executa esse
> plano **por fatias A→E**; a fatia C fecha o mascaramento. **Decisão de sequência (04/07/2026):**
> fazer a fundação antes da máscara — sem chavear PII em nome de papel para não re-migrar depois.
> **Decisões resolvidas:** catálogo é registry Python **na IAM** (fonte única) sincronizado p/ a
> tabela `Permissao`; a checagem passa a ser por **permissão** (claim `permissions` no JWT), não por
> nome; máscara de leitura é **parcial** (`•••` + últimos dígitos) onde fizer sentido, `null` no resto.

- **9.A Catálogo + destravar (fundação):** ✅ 05/07/2026 (ativado no stack) — catálogo
  único [catalog.py](../iam/identity/catalog.py) com **99 permissões `modulo.recurso.acao`** (rh,
  erp_financeiro, crm, drone, base, plataforma; PII como recurso próprio) e **14 personas de fábrica**
  (com descrição legível); `sync_authz` reflete p/ `Permissao` e compõe papéis por tenant;
  `permissions` no JWT. **Personas dinâmicas** com trava anti-escalada (permissão ⊆ módulos assinados)
  e **UI de administração** ([modules/admin/](../frontend/src/modules/admin/): `/app/admin/papeis`
  cria/edita/**clona**/exclui papéis com picker por módulo; `/app/admin/usuarios` atribui papéis a
  usuários) — só `is_tenant_admin`, via gateway `/iam/`. Seed ganhou usuário `admin`. Testes 13/13 +
  E2E vivo (o 403 do RH destravado de verdade). Padrão de extensão p/ módulos da v01 em
  [rbac-abac.md §9](arquitetura/rbac-abac.md).
- **9.B Permissão no enforcement:** ✅ 05/07/2026 —
  [`RequirePermission`](../backend/nucleo/permissions.py) substitui `RequireRole`: ViewSet declara
  `required_resource="modulo.recurso"` (GET→`.view`, escrita→`.edit`) ou `permission_map`; auth expõe
  `iam_permissions`. RH (dado_medico/dado_bancario/folha) migrado; `RequireRole` **depreciado** com
  **fallback** (token sem `permissions` cai no papel → zero-downtime). CRM inteiro gateado por
  módulo+permissão, fechando **S5** (`OpportunityProductViewSet` só tinha `IsAuthenticated`). Testes
  DRF verdes sobre Postgres (`rh/tests.py`, `modulocrm/tests.py` — 15/15) + E2E vivo. **Estendido
  05/07** aos cadastros-base (`clientes`/`fornecedores`/`obras`/`empreendimentos`), que estavam sem
  camada 2 — achado **D5** (operacional criava cliente/venda). **Fatia B fechada 11/07 (D3/D4/D5):**
  `moduloerp` migrado de `RequireRole` p/ `RequirePermission` nos 14 viewsets, com verbos de domínio
  (baixa, cobrança, NF, lote, resolver) gateados por `action_permission_map`; camada 2 em
  `modulocalendar`/`moduloapi`/`funcoesia`; fallback agora **fail-closed** (D4: `None`=legado→papel,
  `[]`=nega); `tenant` read-only sistêmico nos serializers (D3, base `TenantScopedModelSerializer`).
  Suíte 71/71 verde. Falta só a fatia **E** (remover o `RequireRole`).
- **9.C Campo/PII (mascaramento):** ✅ 05/07/2026 — `FieldMaskingSerializerMixin`
  ([nucleo/field_masking.py](../backend/nucleo/field_masking.py)) com **dois eixos**:
  `sensitive_fields` (leitura — mascara: CPF/CNPJ/conta → `••••`+dígitos; valores/PIX/texto → `null`;
  **fail-closed** sem contexto) e `write_protected_fields` (escrita — trava explícita com a `.edit`
  concedível). Aplicado em RH (`Funcionario` CPF/salário, `DadoMedico`, `DadoBancario`, `Pagamento`,
  `Folha`), clientes (`Cliente` CPF via `cadastro.cliente_doc.view`, `DadoBancarioCliente`) e
  fornecedores (só `DadoBancarioFornecedor` — CNPJ é público, não mascarado). Substituiu o hack do
  `salario_base`. **Correção pós-revisão (05/07):** a 1ª versão derivava a escrita da leitura
  (`rh.cpf.edit`, inexistente) e **travava a criação** de funcionário/cliente/fornecedor p/ não-admins;
  os eixos foram separados. **Correlato Fase 8.2:** `tenant` obrigatório no POST → `tenant` read-only
  nos serializers de RH/fornecedores. Testes `rh/test_field_masking.py` (11); E2E: não-admin cria ficha.
- **9.D LGPD além da máscara:** ✅ 05/07/2026 — **portabilidade** (`GET /api/lgpd/<tipo>/<id>/exportar/`,
  `plataforma.lgpd.exportar`) e **esquecimento** (`POST …/esquecer/`, `plataforma.lgpd.excluir`) p/
  funcionário/cliente ([nucleo/lgpd.py](../backend/nucleo/lgpd.py): exporta PII integral; anonimiza +
  apaga filhos de PII + desativa login). **Incidente ANPD** (`IncidenteLGPD`, RLS fail-closed): nasce
  **pendente**; só o **dono da plataforma** (`is_platform_admin`) **confirma** (inicia prazo de **72h**)
  ou **descarta** (falso positivo) — a trava anti-falso-positivo. Endpoints usam `RequirePermissionStrict`
  (fail-closed, sem fallback de papel). Testes `nucleo/test_lgpd.py` (8) verde. Falta a UI (Fase 7).
- **9.E Trilha de auditoria:** ✅ 11/07/2026 — `AuditLog` **imutável
  append-only** tenant-scoped: `save`/`delete` bloqueados no modelo
  ([nucleo/models.py](../backend/nucleo/models.py)), **trigger PostgreSQL** barrando UPDATE/DELETE mesmo
  em SQL cru/`queryset` ([migration 0017](../backend/nucleo/migrations/0017_auditlog_imutavel.py)), RLS
  fail-closed ([0016](../backend/nucleo/migrations/0016_auditlog_rls.py)) e API **read-only**
  `GET /api/auditoria/` restrita a `plataforma.auditoria.view` + admin de tenant/plataforma (fail-closed).
  Helper `registrar_auditoria` + mixins opt-in `AuditedModelViewSetMixin`/`PiiReadAuditMixin`
  ([nucleo/auditoria.py](../backend/nucleo/auditoria.py)); FK `usuario` congelado (`db_constraint=False`,
  rótulo durável em `usuario_nome`). **Coberto:** escritas de RH (funcionário, dado médico/bancário, ASO,
  pagamento, folha) com **nomes dos campos alterados** no update; **leitura de PII** (retrieve de
  médico/bancário/ASO → `visualizar_pii`); **baixa** financeira (choke point manual + Asaas); **emissão de
  NF** e **gerar cobrança**; **LGPD** export/forget. `detalhes` só metadados não-PII. **Legado:**
  `LogAtividadeUsuario` demovido a telemetria operacional (Celery/microsserviço) e sua API de leitura
  `/api/logs-atividade/` removida — a trilha sensível é o `AuditLog`; remoção do modelo + telemetria
  estruturada → Fase 10. **Validado:** `nucleo/test_auditoria.py` + **suíte completa verde (71/71)** sob
  Postgres (role `erp_app`, RLS real) **+ E2E [phase9_auditoria_test.py](../infra/gateway/phase9_auditoria_test.py)
  — 15/15 no stack vivo** (criar/atualizar+`campos_alterados`/`visualizar_pii`/`exportar_lgpd`; leitura
  restrita a admin/permissão; POST/DELETE → 405); migrations 0015–0017 aplicadas no `erp_db`.

**DoD:** `phase9_field_mask_test.py` verde; checagem por permissão em todo endpoint pago; procedimento
LGPD documentado em [infra/](../infra/); `AuditLog` populado; exportação e exclusão de titular via
endpoint admin.

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
- **10.6 JWT em cookie HttpOnly:** ✅ 11/07/2026 (antecipada, fecha o **F1**). Ciclo de sessão padrão
  SaaS: **access token de 15 min em memória** + **refresh em cookie HttpOnly** (`SameSite=Strict`,
  path `/auth/`) renovado em silêncio (10.6.1/10.6.2). Rotação + blacklist com **detecção de reuso** e
  **teto absoluto**; login com **"Lembrar de mim"** (12h vs 30d deslizante/cap 90d); o refresh
  **recalcula as claims** (revogação/mudança de permissão vale em ≤15 min). Iframe do drone deixou o
  `?token=` — recebe o token por **postMessage** do shell e o atualiza a cada rotação (10.6.3). CSRF:
  `SameSite=Strict` + checagem de `Origin` no refresh/logout (10.6.4). IAM
  ([tokens.py](../iam/identity/tokens.py)/[cookies.py](../iam/identity/cookies.py)/views) validado
  (19/19); React ([api/session.ts](../frontend/src/api/session.ts) + `attachAuth`/`tokenStore`) e Angular
  do drone (postMessage) exigem rebuild dos containers p/ validação E2E.
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

**Decisão permanente de linguagens:** **Python** (models),
**Java** (drone e serviços onde performance/JVM justifiquem) e
**TypeScript** (todo o frontend). Ver AD-8 em [arquitetura.md](arquitetura.md).

Os microsserviços Node são wrappers finos sobre APIs REST — não justificam um quarto runtime:

| Serviço Node                            | O que faz                                        | Equivalente Python                                                                                                                       |
| ---------------------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `funcoesnf`                            | Chama NFE.io REST para emitir NF-e/NFS-e         | Celery task +`httpx`                                                                                                                   |
| `funcoeslead`                          | Conversão/score de lead, agenda, notificações | ✅**Absorvido 03/07/2026**: `modulocrm/services.py` + actions, agenda in-process no `modulocalendar`, Celery task de lembretes |
| `funcoeswhatsapp`                      | Webhook WhatsApp → pré-cadastro do diário     | Django view + Celery task                                                                                                                |
| worker de`funcoesia` (embutido no app) | Chama o Gemini na análise de imagens            | Celery task (+ LLM local — ver[plano](arquitetura/diario-ia-reintegracao.md))                                                            |

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
- **Drone:** entidades-filhas escopadas por tenant (`tenant_id` NOT NULL + gate na borda) — **✅ 8.5**;
  WebSocket e serviço→serviço — **10.8**.
- **Módulos vazios:** `moduloaps`/`modulodms`/`modulopdca`/`moduloscm`/`modulosil`/`modulomaps` —
  porte da **Fase 7** ([plano](arquitetura/migracao-v01.md)).
- **Monetização / paywall (planejado, sem código):** auto-serviço (landing → checkout → pagamento
  Asaas → código de ativação), planos híbridos (planos + add-ons), **quotas** por plano (usuários,
  empreendimentos, obras, clientes, storage, processamento de drone, IA, NF, boletos), trial de 28
  dias. Vínculo **usuário↔funcionário** (seat = funcionário com login). Estudo do consultor +
  faseamento em [arquitetura/monetizacao.md](arquitetura/monetizacao.md); ABAC por objeto (acesso a
  empreendimento) é a **fatia D** do [AD-9](arquitetura/rbac-abac.md).
- **Frontend pendente:** dashboard de KPIs, CRM, drone wrapper, calendário — tabela da Fase 7 acima.
- **Operacional:** LGPD, secrets, observabilidade, DR, pentest — **Fase 10**.
- **Supply chain:** nenhuma varredura automatizada (npm/Maven/pip) — **10.4**.
- **CI/CD ausente:** testes manuais; gates pressupõem pipeline — **10.5**.
- **JWT em `localStorage` e em query param (iframe):** ✅ **10.6** (11/07) — access em memória + refresh
  em cookie HttpOnly; iframe do drone via postMessage (sem `?token=`).
- **Staging ausente:** validações vão direto para produção — **10.7**.
- **Superfície:** 11 serviços, 3 stacks, 2 frontends — **Fases 10 e 11**.
