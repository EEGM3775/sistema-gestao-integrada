# Prancha — Identidade & SSO

> Como a plataforma autentica e propaga identidade entre serviços. Visão macro em
> [../arquitetura.md](../arquitetura.md) §4; **política** de quem-pode-o-quê (entitlement + RBAC) em
> [../acesso-e-permissoes.md](../acesso-e-permissoes.md). Código: [iam/identity/](../../iam/identity/).

## 1. Princípio

A autoridade de identidade é **uma só: a IAM**. Nenhum outro produto cria ou autentica usuários —
todos recebem um **JWT assinado pela IAM** e apenas o **validam** e leem suas claims. Cada produto é,
nesse sentido, um *resource server*.

## 2. Modelo de identidade (na IAM)

[iam/identity/models.py](../../iam/identity/models.py):

| Entidade | Papel |
|---|---|
| `Tenant` | empresa-cliente; fronteira de isolamento (`id` UUID, `slug`, `status`, `plano`) |
| `Usuario` | `AbstractUser` com `id` UUID; pertence a um `tenant`; `username` global (vira `sub`); `is_tenant_admin`; M2M `perfis` |
| `Perfil` / `Permissao` | RBAC intra-tenant (papéis agregam permissões; `Perfil` é por tenant) |
| `Modulo` | catálogo vendável (`erp_financeiro`, `crm`, `rh`, `drone`, …) |
| `AssinaturaTenant` | módulos que o **tenant** contratou (+ vigência/limites) |
| `AcessoUsuarioModulo` | módulos que o **usuário** pode usar (subconjunto dos do tenant) |

`Usuario.modulos_efetivos()` = interseção das assinaturas ativas do tenant com o acesso do usuário
(admin do tenant/superuser recebe todos os ativos). Esse conjunto vira o claim `modules`.

## 3. Assinatura do token

- **RS256 + JWKS (padrão):** a IAM assina com **chave privada RSA** (`infra/keys/jwt_private.pem`) e
  publica a **pública** em `GET /.well-known/jwks.json`. ERP e drone validam só com a pública (montada
  em `/keys`) — **não conhecem segredo e não podem forjar** token. Chaves geradas por
  [infra/keys/generate.sh](../../infra/keys/generate.sh) (não versionadas).
- **HS256 (fallback):** sem chave RSA, os serviços usam HS256 com **segredo compartilhado** (só a IAM
  assina). A escolha RS256↔HS256 é automática conforme a presença da chave.
  > ⚠️ **Invariante HS256:** o `JWT_SECRET` precisa ser **idêntico** em todos os serviços e ter
  > **≥32 bytes** (o `jjwt` do drone rejeita chaves menores). Segredos divergentes → 401.
- **Rotação:** a evolução é validar por **`JWK_URL` + `kid`** (fetch dinâmico do JWKS), permitindo
  trocar a chave sem redeploy dos resource servers.

## 4. Claims do access token

```jsonc
{
  "sub": "username",                         // identidade (resource servers buscam/provisionam por ele)
  "tenant_id": "uuid", "tenant_slug": "...", // tenant
  "roles": ["financeiro"],                   // RBAC (camada 2)
  "modules": ["erp_financeiro","drone"],     // entitlements efetivos (camada 1)
  "is_tenant_admin": false,
  "iss": "sgi-iam", "iat": 0, "exp": 0, "jti": "..."
}
```

Todo serviço valida a assinatura e decide acesso **a partir do token** — sem tabela local de permissão.

## 5. Endpoints de autenticação (IAM)

[iam/identity/urls.py](../../iam/identity/urls.py):

| Endpoint | O quê |
|---|---|
| `POST /auth/login` | `{ access, refresh, user, tenant, modules }` |
| `POST /auth/refresh` | novo `access` |
| `POST /auth/logout` | blacklist do refresh |
| `GET /auth/me` | usuário + tenant + módulos (revalida sessão) |
| `GET /.well-known/jwks.json` | chave pública (validação RS256) |

Sob o gateway, a IAM responde em `/auth` (ver [servicos-e-integracoes.md](servicos-e-integracoes.md)).

## 6. Fluxos de sequência

### 6.1 Login (browser)
```
React            Gateway        IAM
  │  POST /auth/login (user,pass) │
  │ ─────────────►  ──────────►   │  valida senha, monta claims
  │                               │  assina RS256
  │ ◄───────  {access,refresh,modules,user,tenant}
  │ guarda access em localStorage; anexa Authorization nas chamadas a /api
```

### 6.2 Abrir o drone embutido (SSO sem 2º login)
```
React (shell)                         Angular (funcoesODM)
  │ iframe src=/drone/?token=<JWT>&empreendimento_id&obra_id
  │ ───────────────────────────────────►
  │                                   capta token da URL (limpa a URL), decodifica modules/tenant
  │                                   interceptor anexa Bearer nas chamadas /odm-api
```

### 6.3 Validação num resource server (ERP ou drone)
```
Cliente ──Bearer JWT──► Gateway ──► Resource server
                                     1. valida assinatura (chave pública / JWKS)
                                     2. lê sub/tenant_id/roles/modules
                                     3. exige o módulo (RequireModule / MODULE_drone) → 403 se ausente
                                     4. JIT: cria/atualiza espelho do usuário (por sub) se não existe
                                     5. escopa as queries por tenant_id
```

### 6.4 Refresh / logout
`POST /auth/refresh` emite novo access; `POST /auth/logout` faz blacklist do refresh (rotação
centralizada na IAM). O shell descarta o token local no logout.

## 7. Provisionamento JIT

ERP e drone **não** têm cadastro próprio de usuários: na primeira requisição autenticada, criam um
**espelho local** do usuário a partir das claims (chave = `sub`/uuid), preservando FKs locais (ex.:
`nucleo.Usuario`). Ver [dados-e-tenancy.md](dados-e-tenancy.md) §6.

## 8. Enforcement (resumo; detalhe na política)

- **Camada 1 — entitlement:** `RequireModule("codigo")` (Django,
  [nucleo/permissions.py](../../backend/nucleo/permissions.py)) e a authority `MODULE_drone` (Java) →
  **403** sem o módulo no claim `modules`.
- **Camada 2 — RBAC:** `RequireRole("papel")` lê o claim `roles` (ex.: `financeiro`).
- Regras completas e estado por módulo em [../acesso-e-permissoes.md](../acesso-e-permissoes.md).
