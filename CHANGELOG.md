# Changelog

Todas as mudanças notáveis desta versão são documentadas aqui.

## [1.0.11] - 2026-07-19

### Visão geral

Versão de consolidação pós-Fase 10.6/F1 com ajustes de infraestrutura, documentação e organização do repositório.

#### Infraestrutura e deploy
- `docker-compose.yml` e `.env.example` movidos para `deploy/compose/` e `deploy/env/` com variants por ambiente (dev/staging/prod).
- `.dockerignore` e `.trivyignore` adicionados na raiz.
- `infra/serve_spa.py` centralizado (removido da raiz).
- Gateway nginx com `resolver` dinâmico e configs de staging.

#### Backend
- Módulos Node legados (`funcoesia`, `funcoeslead`, `funcoesnf`, `funcoeswhatsapp`) removidos em favor das implementações Django integradas.
- `funcoeswhatsapp` reescrito em Django (models, flows, router, tasks, security, tenant resolver).
- `funcoesia` com `llm_client.py` e tasks Celery.
- `modulocalendar`: recurrence, feriados, lembretes e management commands.
- `moduloerp`: cancelamento/retorno gateway, `nfe_client`, tasks e migrações.
- `nucleo`: notificações, quotas, rate limit, observability, geo/drone sync, upload validation, revocation, middleware.
- `iam`: recuperação de senha, eventos de segurança, quotas, observability, signals, middleware, health views.

#### Frontend
- Recuperação de senha (esqueci/redefinir/confirmar e-mail).
- Módulo de calendário.
- Notas fiscais (ERP) com divergências e emissão NFS-e.
- Notificações e avisos de acesso.
- Session clock e warning de expiração.
- AuthShell e ModuleRoute para roteamento protegido.

#### Documentação
- `docs/comandos.md`, `docs/arquitetura/rate-limiting.md` e seção de expansão adicionados.
- Atualizações em arquitetura, módulos, desenvolvimento, domínio, frontend e roadmap.

---

## [1.1.0] - 2026-07-11

### Sessão sem relogin — access curto + refresh em cookie HttpOnly (Fase 10.6 / F1)

Fim do logout forçado a cada 60 min. Modelo de sessão padrão de SaaS: a segurança
vem da rotação/detecção de reuso e do cookie HttpOnly, não da inconveniência.

#### IAM (backend) — validado, testes 19/19
- **Access token 15 min** ([settings](iam/iam_project/settings.py)); volta no corpo, vive em memória.
- **Refresh em cookie HttpOnly** (`SameSite=Strict`, path `/auth/`) — imune a XSS de leitura
  ([cookies.py](iam/identity/cookies.py)). Nunca no corpo/localStorage.
- **RefreshView custom** ([views.py](iam/identity/views.py)): lê o cookie, **rotaciona** (blacklist do
  antigo → reuso de token velho = 401 e derruba a sessão), **recalcula as claims** (`build_claims` →
  permissão revogada/alterada vale em ≤15 min) e respeita o **teto absoluto** de sessão.
- **"Lembrar de mim"**: 12h fixas sem marcar · 30d deslizantes (cap 90d) marcando
  ([tokens.py](iam/identity/tokens.py) `issue_refresh`).
- **Logout** blacklista o refresh do cookie e o limpa; **CSRF**: `SameSite=Strict` + checagem de `Origin`.
- Testes `identity` 19/19 (login/cookie, rotação, detecção de reuso, remember, logout).

#### React (shell) — code-complete, requer rebuild do container p/ E2E
- Access token **em memória** ([tokenStore.ts](frontend/src/api/tokenStore.ts)); saiu do `localStorage`.
- `attachAuth` ([attachAuth.ts](frontend/src/api/attachAuth.ts)): `withCredentials` + **401 → refresh →
  retry**; refresh **proativo** ~1 min antes de expirar (nenhuma requisição falha).
- **Bootstrap** na carga chama `/auth/refresh/` (cookie) e repopula a sessão sem relogar
  ([session.ts](frontend/src/api/session.ts), [AuthContext](frontend/src/contexts/AuthContext.tsx)).
- Login com checkbox **"Manter conectado"**.

#### Drone (Angular, repo separado) — code-complete, requer rebuild p/ E2E
- Iframe deixou o `?token=` da URL: recebe o access token do shell por **postMessage** e o atualiza a
  cada rotação; guard assíncrono aguarda a 1ª injeção (sem corrida); token em memória.

#### Gateway
- Cookie (path `/auth/`) trafega pelo nginx (mesma origem).
- **502 pós-reboot corrigido de vez:** o nginx resolvia o IP dos upstreams uma vez no start e cacheava
  → após reboot/restart de container (IP novo) dava **502 (connect refused)**. Agora usa `resolver
  127.0.0.11` (DNS do Docker) + `proxy_pass` por variável → re-resolve em runtime, sem `restart gateway`
  manual. Nota WSL: ao editar `nginx.unified.conf`, recriar com `docker compose up -d --force-recreate
  gateway` (o `restart` falha o bind-mount).

#### Correção durante o rebuild
- Refresh token passou a ser **mínimo** (`user_id` + `sst`/`rem`); as claims pesadas (permissions/roles/
  modules) foram movidas p/ o **access token**. Sem isso o `Set-Cookie` estourava o buffer do nginx
  (502 "too big header") e o limite de ~4 KB de cookie do browser. Cookie final: ~636 B.
- `.env`/compose: `JWT_ACCESS_MINUTES` 60→**15**, `JWT_REFRESH_DAYS` 7→30.
- **Checagem de `Origin` (CSRF) corrigida**: o gateway repassa `Host` sem porta (`$host`) em `/auth/`,
  então comparar o `Origin` do browser (`localhost:8090`) com `get_host()` (`localhost`) dava **403 no
  refresh após ~15 min**. Passou a comparar **hostname sem porta** (same-origin OK; origem externa segue 403).

#### Validação (stack ao vivo, gateway :8090)
- Backend E2E: login (cookie, sem refresh no corpo) → refresh (rotação, access 15 min) → reuso de refresh
  antigo = 401 → logout = 401. IAM 19/19. React/drone rebuildados (TS compilou limpo) e servindo (200).

### Sessão: "desligar o PC" e troca de senha (follow-up)

- **Sem "manter conectado" → cookie de sessão** (sem `Max-Age`): o navegador o descarta ao fechar/
  desligar → exige novo login. Com "manter conectado" → cookie persistente (~30d, sobrevive ao reboot).
  ([cookies.py](iam/identity/cookies.py) `set_refresh_cookie(..., persistent=)`).
- **Trocar a senha encerra as OUTRAS sessões**: `revoke_all_sessions` blacklista todos os refresh do
  usuário; o dispositivo que trocou recebe uma sessão nova (não desloga). Endpoint self-service
  `POST /auth/senha/` ([views.py](iam/identity/views.py) `ChangePasswordView`) + reset de senha pelo admin
  (`UsuarioViewSet`) também derruba as sessões do usuário. Frontend: `changePassword` em
  [session.ts](frontend/src/api/session.ts) + `AuthContext`.
- **UI — self-service:** item **"Alterar senha"** no menu do usuário (topbar) →
  [ChangePasswordModal](frontend/src/components/ChangePasswordModal.tsx) (senha atual + nova + confirmação).
- **UI — admin:** ação **"Redefinir senha"** por usuário em `/app/admin/usuarios`
  ([UsuariosPage](frontend/src/modules/admin/pages/UsuariosPage.tsx)) com **confirmação explícita**
  (aviso + checkbox + nova senha em dobro); backend gateado por `IsTenantAdmin` (escopo do tenant).

#### Correções (troca de senha)
- **`changePassword` do frontend não enviava o Bearer** → o `/auth/senha/` respondia 401 (self-service
  quebrada). Agora anexa o access token da memória ([session.ts](frontend/src/api/session.ts)).
- **Admin reset passou a exigir a senha ATUAL do usuário** (decisão do produto): nova ação
  `POST /iam/usuarios/{id}/redefinir-senha/` (`{senha_atual, nova_senha}`, verifica a atual e encerra as
  sessões do alvo). O `PATCH {password}` **não troca mais senha** de usuário existente — fecha o caminho
  de troca sem a senha antiga. Recuperação (sem a antiga) fica para etapa futura.
- Modal self-service mostra **de qual conta** é a senha (evita trocar a conta errada). `check_password`
  validado contra o usuário do token (sem vazamento cross-user — comprovado).
- Testes IAM **26/26**; smoke E2E: self-service (nova senha loga / antiga 401) e admin reset (atual
  errada 400 · correta 200) pelo gateway.
- Validado ao vivo (cookie de sessão vs persistente; A troca senha → B cai (401), A mantém (200)) e
  testes IAM **23/23**.

#### Gateway — 502 pós-reboot (correção definitiva)
- nginx cacheava o IP do upstream no start → após reboot/restart (IP novo) dava **502**. Agora
  `resolver 127.0.0.11` + `proxy_pass` por variável → re-resolve em runtime. Provado: restart do IAM
  (IP novo) sem tocar no gateway → login segue 200. (Ao editar o `nginx.unified.conf`: `docker compose
  up -d --force-recreate gateway`, pois `restart` falha o bind-mount no WSL.)

---

## [1.0.10] - 2026-07-11

### Fase 9 — Fecho dos residuais de controle de acesso (D3/D4/D5)

#### Corrigido
- **D5 — Broken access control (fatia B fechada em todo o backend):**
  - `moduloerp` migrou de `RequireRole("financeiro")` para `RequirePermission` nos 14 viewsets/APIViews.
  - Novo `action_permission_map` no `RequirePermission` ([nucleo/permissions.py](backend/nucleo/permissions.py)):
    verbos de domínio por ação — `dar_baixa`→`erp.*.baixar`, `gerar_cobranca`→`erp.cobranca.emitir`,
    `emitir_nf*`→`erp.nf.emitir`, `gerar_lote_remessa`→`erp.lote_remessa.create`, `aprovar`/`rejeitar`→`erp.revisao_baixa.resolver`.
  - Camada 2 adicionada a `modulocalendar` (`calendario.evento`), `moduloapi` (`plataforma.integracao`)
    e `funcoesia` (`ia.analise.view`/`.executar`, inclusive os proxies FBV).
  - Template `financeiro` recebeu `erp.lote_remessa.*` (permissão órfã no catálogo).
- **D4 — `RequirePermission` fail-open com `permissions` vazia (fechado):**
  - Autenticação distingue claim **ausente** (`iam_permissions = None` → fallback legado por papel) de
    claim **presente porém vazia** (`[]` → checagem estrita, conjunto vazio nega).
  - `RequirePermission` só cai no `RequireRole` quando `iam_permissions is None`.
- **D3 — `tenant` obrigatório no POST (fechado sistemicamente):**
  - `TenantReadOnlyFieldMixin` + base `TenantScopedModelSerializer` em
    [nucleo/tenant_validators.py](backend/nucleo/tenant_validators.py); `tenant` read-only dobrado no
    `TenantScopedUniqueSerializerMixin` (todos os serializers que já o usavam cobertos).
  - `read_only_fields = ['tenant']` nos serializers `__all__` remanescentes (moduloerp, empreendimentos,
    obras, modulocrm, modulocalendar, moduloapi, funcoesia).

#### RBAC — sincronização segura e automática
- `sync_authz` agora é **aditivo** por padrão: ao aplicar templates a papéis de fábrica já existentes,
  **soma** as permissões do modelo sem apagar ajustes manuais do admin (`.add`, não `.set`). Papel novo
  ou `--reset` explícito voltam a regravar exatamente ao modelo.
- IAM roda `sync_authz --all-tenants` no boot (CMD do [Dockerfile](iam/Dockerfile)) — o catálogo e as
  permissões de fábrica (incl. `erp.lote_remessa.*`) se propagam no deploy, idempotente e sem passo manual.

#### Notas de operação
- Sem passo manual. A permissão nova só entra no token **no próximo login** (as claims são congeladas no
  login por `build_claims`; o `/auth/refresh/` padrão do SimpleJWT copia claims e **não** recalcula). O
  token de 60 min sem refresh (F1) força esse re-login na prática ao expirar.

#### Testes
- Suíte completa: **71/71 verde** sobre Postgres (RLS real); `check` sem issues.

---

## [1.0.9] - 2026-07-11

### Fase 9.E - Trilha de auditoria imutável (concluída)

#### Adicionado
- **AuditLog imutável** (`backend/nucleo/auditoria.py`):
  - Modelo append-only tenant-scoped
  - `save`/`delete` bloqueados no modelo
  - Trigger PostgreSQL barrando UPDATE/DELETE mesmo em SQL cru
  - FK `usuario` congelado (`db_constraint=False`, rótulo durável em `usuario_nome`)
  - Helper `registrar_auditoria` para registrar eventos
  - Mixins opt-in: `AuditedModelViewSetMixin`, `PiiReadAuditMixin`

- **API de auditoria** (`backend/nucleo/auditoria_views.py`):
  - `GET /api/auditoria/` read-only
  - Restrito a `plataforma.auditoria.view` + admin de tenant/plataforma
  - Fail-closed (sem fallback de papel)

- **Catálogo de permissões único** (`iam/identity/catalog.py`):
  - 99 permissões `modulo.recurso.acao`
  - 14 personas de fábrica (diretoria, rh_gestor, rh_medico, rh_financeiro, financeiro, tesouraria, fiscal, comercial, engenharia, campo, drone_analista, auditor, gestor_lixo, operacional)
  - Trava anti-escalada (permissão ⊆ módulos assinados)

- **UI de administração** (`frontend/src/modules/admin/`):
  - `/app/admin/papeis` - CRUD de papéis com picker por módulo
  - `/app/admin/usuarios` - atribuição de papéis a usuários
  - Menu "Papéis e Acessos" só aparece para `is_tenant_admin`

- **Mascaramento de campos PII** (`backend/nucleo/field_masking.py`):
  - `FieldMaskingSerializerMixin` com dois eixos: `sensitive_fields` (leitura) e `write_protected_fields` (escrita)
  - Cobertura: RH (Funcionario CPF/salário, DadoMedico, DadoBancario, Pagamento, Folha), clientes (CPF), fornecedores (DadoBancario)

- **LGPD - Portabilidade e esquecimento** (`backend/nucleo/lgpd.py`):
  - `GET /api/lgpd/<tipo>/<id>/exportar/` - exportação de PII integral
  - `POST /api/lgpd/<tipo>/<id>/esquecer/` - anonimização + desativação de login
  - `IncidenteLGPD` com trava anti-falso-positivo (apenas `is_platform_admin` confirma)

- **Uniques por-tenant** (7 migrações):
  - Cada `unique=True` global escalar virou `UniqueConstraint(fields=["tenant", …])`
  - Validador DRF escopado ao tenant (`tenant_validators.py`)
  - Mesmo CPF em tenants distintos OK; duplicado no mesmo tenant → 400

- **Tenant NOT NULL** (11 migrações):
  - FK `tenant` do `TenantScopedModel` agora NOT NULL
  - Backfill defensivo para órfãs

- **funcoeslead absorvido** (Fase 11.2 antecipada):
  - Lógica de lead integrada a `modulocrm/services.py`
  - Agenda in-process no `modulocalendar`
  - Celery task de lembretes

#### Corrigido
- S1 - Vazamento entre tenants (dashboard ERP + views de NF)
- S2 - RLS fail-open
- S5 - Bypass de entitlement no CRM
- S10 - Vazamento entre tenants nas filhas do drone
- L1 - Calendário 500 em toda listagem
- L2 - Dead Letter Queue nunca grava
- L3 - NF emitida sem tenant e sem documento do tomador
- L4 - Integração `funcoeslead` ↔ backend morta
- D2 - Boleto Asaas emitido no cliente errado
- D3 - `tenant` obrigatório no POST (parcial - RH, fornecedores)
- D4 - `RequirePermission` fail-open com `permissions` vazia (mitigado)
- D5 - Cadastros-base sem camada 2 (parcial - clientes, fornecedores, obras, empreendimentos)

#### Testes
- `nucleo/test_auditoria.py` (7 testes)
- `nucleo/test_lgpd.py` (8 testes)
- `rh/test_field_masking.py` (11 testes)
- `rh/tests.py` (15 testes)
- `modulocrm/tests.py` (15 testes)
- Suíte completa: 71/71 testes verdes sobre Postgres
- E2E: `phase9_auditoria_test.py` (15/15)

---

## [1.0.0] - 2026-05-31

### Fase 0-6 - Fundação e consolidação

- Banco por env (PostgreSQL+Redis via compose)
- Serviço IAM próprio
- backend como resource server com tenancy
- SSO ponta a ponta
- UI integrada (gateway, domínio único)
- Vínculo drone ↔ obra/empreendimento
- Deploy unificado
- Endurecimento RS256/JWKS + borda
- Consolidação de identidade & RBAC