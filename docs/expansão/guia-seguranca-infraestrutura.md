# Guia de Segurança e Infraestrutura — verificação de cobertura para quando for feita a expansão

> Auditoria item a item do "Guia de Segurança e Infraestrutura" contra o código e a documentação do projeto (18/07/2026). Cada item traz status, evidências (docs/código) e ressalvas (pendências documentadas).

## Legenda

- ✅ **Presente** — implementado e documentado
- ⚠️ **Parcial** — parte implementada ou com ressalvas documentadas
- ❌ **Ausente** — não implementado e sem planejamento explícito

---

## Identidade & Acesso

### Autenticação (JWT, Sessões, cookies) — ✅ PRESENTE

- **JWT RS256 + JWKS** (padrão produção) / HS256 (fallback dev); **refresh token em cookie HttpOnly** (`SameSite=Strict`, `Secure` em prod); **access token em memória** (5 min); rotação com blacklist; revogação imediata por época no Redis.
- **Docs:** [auth-sso.md](../arquitetura/auth-sso.md), [acesso-e-permissoes.md](../acesso-e-permissoes.md) §5.1–5.2
- **Código:** `iam/identity/` (views, cookies, tokens, revocation), `backend/nucleo/authentication.py`, `backend/nucleo/revocation.py`

### Autorização (roles, permissões) — ✅ PRESENTE

- **3 camadas:** entitlement (`RequireModule`), RBAC por permissão (`RequirePermission`), ABAC por objeto (parcial — fatia D pendente); catálogo global de 99 permissões (`modulo.recurso.acao`); personas por tenant; mascaramento de campo PII.
- **Docs:** [rbac-abac.md](../arquitetura/rbac-abac.md), [acesso-e-permissoes.md](../acesso-e-permissoes.md)
- **Código:** `iam/identity/catalog.py`, `backend/nucleo/permissions.py`, `backend/nucleo/field_masking.py`

### OAuth 2.0 / SSO (Google, GitHub) — ⚠️ PARCIAL

- **SSO interno entre serviços** via JWT da IAM: ✅ implementado e documentado.
- **OAuth 2.0 com terceiros (Google/GitHub login):** existe modelo `GoogleAccount` em `backend/moduloapi/` (tokens OAuth do Google para integrações), mas **não há login social** (Google/GitHub como provedor de identidade para autenticação de usuários). O [06-dados-ia-automacao.md](06-dados-ia-automacao.md) cita "Google (OAuth via `moduloapi`) ✅" como conector, não como login SSO.

### Autenticação Multifator — ❌ AUSENTE

- Busca por MFA/2FA/OTP/TOTP retornou **0 resultados**. Não há implementação nem planejamento explícito no roadmap.

---

## Proteção de Dados

### Hash de Senhas (bcrypt, não MD5) — ✅ PRESENTE

- **Argon2** (preferencial) + PBKDF2 + BCrypt em `iam/iam_project/settings.py` (`PASSWORD_HASHERS`). Sem MD5. Pacote `argon2-cffi` no `iam/requirements.txt`.

### Criptografia em Repouso — ⚠️ PARCIAL / PLANEJADO

- **RLS** (Row-Level Security) no Postgres para isolamento: ✅
- **Mascaramento de PII** na serialização (CPF, salário, dados médicos/bancários): ✅ (`FieldMaskingSerializerMixin`)
- **Criptografia de campo no banco** (Fernet/AES/pgcrypto): ❌ não implementado. O [deploy-e-seguranca.md](../arquitetura/deploy-e-seguranca.md) §5 cita "cifra em repouso" como desenho LGPD, mas o pacote `cryptography` é usado apenas para chaves JWT, não para cifrar dados.
- **TLS na conexão com o banco:** ⚠️ **D14 corrigido 19/07/2026** — `DB_SSLMODE` deixou de ser literal no compose (`${DB_SSLMODE:-disable}`) e `DB_SSLROOTCERT` foi adicionado, então `verify-full` passou a ser alcançável por configuração; `deploy/env/prod.env.example` já nasce assim. **Ainda não exercitado contra um Postgres com TLS real**, e dev/staging seguem em `disable` (o Postgres do compose não tem certificado).

### Criptografia em Trânsito (HTTPS/TLS) — ✅ PRESENTE (com ressalva D14)

- **Gateway termina TLS** em staging/produção (`nginx.staging.conf`); **HSTS**, `SECURE_SSL_REDIRECT`, cookies `Secure`, `SECURE_PROXY_SSL_HEADER`.
- **Ressalva:** TLS na conexão com o banco não funciona (D14 acima).

### Mascaramento de Dados (nunca logar senhas/tokens/cartões) — ✅ PRESENTE

- `sanitizar_payload()` no WhatsApp (mascara número/conteúdo); `FieldMaskingSerializerMixin` (mascara PII na resposta); logs estruturados JSON sem segredos; `AuditLog` grava só metadados não-PII.
- **Código:** `backend/funcoeswhatsapp/payload.py`, `backend/nucleo/field_masking.py`, `backend/nucleo/auditoria.py`

---

## Entrada & Saída

### Validação & Sanitização — ✅ PRESENTE

- DRF serializers com validação; `TenantScopedUniqueSerializerMixin` (unique por-tenant → 400 limpo); `AUTH_PASSWORD_VALIDATORS` (similaridade, tamanho mínimo, comuns, numérica).
- **Ressalva (A12, aberto):** validador CPF/CNPJ sem dígito verificador no backend.

### Prevenção de SQL Injection — ✅ PRESENTE

- **Django ORM** (parameterizado por padrão); raw SQL só em migrações DDL (RLS) com nomes de tabela de introspecção, não input de usuário; `cursor.execute("SELECT set_config(%s, %s, true)", [key, value])` usa parâmetros.

### Prevenção de XSS — ✅ PRESENTE

- **CSP** `frame-ancestors 'self'`; `X-Content-Type-Options nosniff`; `X-XSS-Protection`; React (auto-escape); refresh em cookie HttpOnly (imune a leitura por XSS). Sem `mark_safe` encontrado.

### Validação de Upload — ✅ PRESENTE

- `UploadValidationMixin` (`backend/nucleo/upload_validation.py`) valida tamanho + tipo; Content-Type genérico cai para checagem de extensão (não confia só no header). Aplicado a obras, clientes, diário, RH, empreendimentos. (A4 — corrigido 14/07)

---

## Segurança de API

### Rate Limiting — ✅ PRESENTE

- **Login:** ✅ rate limit no gateway nginx (`/auth/login` — 10 req/min por IP, 429).
- **API geral:** ✅ **S8 corrigido 19/07/2026** — `DEFAULT_THROTTLE_*` no backend e na IAM (`anon` 120/min, `user` 3000/hora, mais escopos nomeados via `ScopedRateThrottle`), taxas ajustáveis por env. O endpoint público de recuperação de senha tem escopo próprio (30/hora por origem), que complementa o teto de 5/hora **por conta** — este não cobria rajada contra contas diferentes.
- **Código:** `backend/config/settings.py`, `iam/iam_project/settings.py`; testes `backend/nucleo/test_s8_jwt_throttle.py`.

### Configuração de CORS — ✅ PRESENTE

- `CORS_ALLOWED_ORIGINS` com origens explícitas (localhost:3000/5173, etc.), **não `*`**; `CORS_ALLOW_CREDENTIALS = True`. Configurado em backend e IAM. Drone tem `APP_CORS_ALLOWED_ORIGINS` configurável.

### Versionamento de API — ⚠️ PARCIAL

- Drone: `/api/v1/` ✅. Backend: `/api/` sem versão explícita no path (há `/api/api/` para moduloapi). [02-arquitetura-de-expansao.md](02-arquitetura-de-expansao.md) cita "versionamento `/api/v1/` público e estável" como **desenho futuro** para API pública.

### Esconder Erros Internos — ⚠️ PARCIAL

- **DEBUG=False por padrão** (S4) — sem página de debug com stack trace.
- **Ressalva (A9, aberto):** várias views retornam `f'Erro interno: {str(e)}'` no corpo do 500, vazando detalhes internos da exceção. Deveria ser mensagem genérica + traceback só no log.

---

## Infraestrutura

### Gerenciamento de Secrets — ✅ PRESENTE (com ressalvas)

- `.env` gitignored; `.env.example` com placeholders; `_config` fail-fast em produção; chaves RSA gitignored.
- **Ressalvas:** (1) **D15 corrigido 19/07/2026** — as 23 variáveis estão documentadas em `deploy/env/dev.env.example`, com um comando de auditoria registrado em [historico-correcoes.md](../historico-correcoes.md) para reconferir periodicamente; (2) **Vault/Secrets Manager** segue **planejado** (Fase 10.3), não implementado — segredos ainda em `.env`.

### Vulnerabilidades de Dependências — ✅ PRESENTE

- CI com `npm audit --omit=dev --audit-level=high`, `pip-audit`, `trivy fs` (bloqueante em HIGH/CRITICAL); **Dependabot** semanal; allow-lists de triagem (`.trivyignore`, `pip-audit-ignore.txt`). (Roadmap 10.4 ✅ 14/07)

### Proteção contra DDoS — ⚠️ PLANEJADO / DESENHO

- **Cloudflare Tunnel** recomendado (10.3.2) com WAF + rate limit + anti-bot — documentado mas **não implementado** (ngrok é andaime de dev). Alternativa LB gerenciado + WAF também no desenho.

### Firewall & Whitelist de IPs — ⚠️ PARCIAL

- **Isolamento de rede Docker:** só o gateway publica porta; demais serviços internos à rede `sgi`.
- **IP whitelist explícita para o banco:** não implementado (DB é interno ao Docker network). Ingress por path (Cloudflare Tunnel) é desenho futuro.

---

## Monitoramento

### Logging — ✅ PRESENTE

- **Logs estruturados JSON** (`JsonLogFormatter`) com `request_id`/`tenant_id` de correlação; `ObservabilityMiddleware` (timing, log de acesso); Prometheus metrics. Python logging (SLF4J/Logback é Java — o drone usa Spring).
- **Código:** `backend/nucleo/observability.py`, `iam/identity/observability.py`, `backend/nucleo/middleware.py`

### Alertas de Atividade Suspeita — ⚠️ PARCIAL

- **Trilha de auditoria** registra quem fez o quê; **métricas Prometheus** coletadas. Mas **Grafana/alertas** estão pendentes (roadmap: "falta Grafana/alertas"). Não há notificação proativa de atividade suspeita automatizada.

### Trilhas de Auditoria — ✅ PRESENTE

- `AuditLog` **imutável** (append-only, `save`/`delete` bloqueados, trigger no Postgres); tenant-scoped com RLS fail-closed; `registrar_auditoria()` helper; `AuditedModelViewSetMixin`/`PiiReadAuditMixin`; API `GET /api/auditoria/` read-only com `plataforma.auditoria.view`. Cobertura: RH, financeiro, LGPD. (Fase 9.E ✅)

---

## Resumo consolidado

| Item | Status |
|---|---|
| Autenticação (JWT/Sessões/cookies) | ✅ |
| Autorização (roles/permissões) | ✅ |
| OAuth 2.0 / SSO (Google/GitHub) | ⚠️ SSO interno sim; login social não |
| Autenticação Multifator | ❌ |
| Hash de Senhas | ✅ (Argon2) |
| Criptografia em Repouso | ⚠️ RLS+mascaramento sim; cifra de campo não; TLS no banco configurável 19/07 (D14), não exercitado |
| Criptografia em Trânsito | ✅ (gateway TLS+HSTS); ⚠️ banco em claro em dev/staging — `verify-full` disponível (D14) |
| Mascaramento de Dados | ✅ |
| Validação & Sanitização | ✅ (ressalva A12: CPF/CNPJ sem dígito) |
| Prevenção de SQL Injection | ✅ |
| Prevenção de XSS | ✅ |
| Validação de Upload | ✅ |
| Rate Limiting | ✅ login (nginx) + throttle DRF anon/user/escopos (S8, 19/07) |
| Configuração de CORS | ✅ (não `*`) |
| Versionamento de API | ⚠️ drone sim; backend sem `/v1/` |
| Esconder Erros Internos | ⚠️ DEBUG=False sim; mas `str(e)` no 500 (A9) |
| Gerenciamento de Secrets | ✅ `.env`+fail-fast; ⚠️ Vault planejado; D15 fechado 19/07 |
| Vulnerabilidades de Dependências | ✅ (npm audit + pip-audit + trivy + Dependabot) |
| Proteção contra DDoS | ⚠️ desenho Cloudflare; não implementado |
| Firewall & Whitelist de IPs | ⚠️ rede Docker isolada; sem IP whitelist explícita |
| Logging | ✅ (JSON estruturado + correlação) |
| Alertas de Atividade Suspeita | ⚠️ métricas sim; alertas não (Grafana pendente) |
| Trilhas de Auditoria | ✅ (AuditLog imutável) |

**Totais (revisado 19/07/2026):** 14 itens totalmente presentes · 8 parciais/com ressalvas · 1 ausente (MFA)

---

## Pendências relacionadas (rastreadoras vivas)

As ressalvas acima correspondem a achados já registrados em [pendências.md](../pendencias.md):

| ID | Item afetado | Status |
|---|---|---|
| A9 | Esconder Erros Internos (`str(e)` no 500) | 🔴 aberto |
| A12 | Validação CPF/CNPJ sem dígito verificador | 🔴 aberto |
| D14 | TLS no banco (`DB_SSLMODE` hardcoded `disable`) | ✅ corrigido 19/07/2026 |
| D15 | 23 vars lidas pelo código ausentes do `.env.example` | ✅ corrigido 19/07/2026 |
| S8 | DRF sem throttling (rate limit geral) | 🔴 aberto |