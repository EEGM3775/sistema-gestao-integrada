# Prancha — Identidade & SSO

> Como a plataforma autentica e propaga identidade entre serviços. Visão macro em
> [../arquitetura.md](../arquitetura.md) §4; **política** de quem-pode-o-quê (entitlement + RBAC) em
> [../acesso-e-permissoes.md](../acesso-e-permissoes.md). Código: [iam/identity/](../../iam/identity/).

## 1. Princípio

A autoridade de identidade é **uma só: a IAM**. Nenhum outro produto cria ou autentica usuários —
todos recebem um **JWT assinado pela IAM**, emitido **para eles** (`aud` por serviço), e apenas o
**validam**. Cada produto é, nesse sentido, um *resource server*. O token prova **quem é**; o "pode?"
é do PDP (SpiceDB) — ver [../acesso-e-permissoes.md §10](../acesso-e-permissoes.md).

O **navegador não tem token**: tem dois cookies HttpOnly, e o gateway (o BFF) troca o da sessão pelo
access do serviço de destino em cada chamada (§6).

## 2. Modelo de identidade (na IAM)

[iam/identity/models.py](../../iam/identity/models.py):

| Entidade | Papel |
|---|---|
| `Tenant` | empresa-cliente; fronteira de isolamento (`id` UUID, `slug`, `status`, `plano`) |
| `Usuario` | `AbstractUser` com `id` UUID; pertence a um `tenant`; `username` global (vira `sub`); `is_tenant_admin`; M2M `perfis` |
| `Sessao` | a sessão (`sid`) de cada login: credencial do cookie (só o hash), `amr`, `auth_time`, validade |
| `Perfil` / `Permissao` | RBAC intra-tenant (papéis agregam permissões; `Perfil` é por tenant) |
| `Modulo` | catálogo vendável (`erp_financeiro`, `crm`, `rh`, `drone`, …) |
| `AssinaturaTenant` | módulos que o **tenant** contratou (+ vigência/limites) |
| `AcessoUsuarioModulo` | módulos que o **usuário** pode usar (subconjunto dos do tenant) |
| `ConsentimentoSuporte` | a empresa deixa o supervisor da plataforma enxergar as pessoas dela, com prazo |

As tabelas continuam a fonte das relações; a IAM as reconcilia no PDP
([../acesso-e-permissoes.md §10.15](../acesso-e-permissoes.md)).

## 3. Assinatura do token

- **RS256 + JWKS (padrão):** a IAM assina com **chave privada RSA** (`infra/keys/jwt_private.pem`) e
  publica a **pública** em `GET /.well-known/jwks.json` (com `kid`, que vai também no cabeçalho do
  token). backend e drone validam só com a pública (montada em `/keys`) — **não conhecem segredo e
  não podem forjar** token. Chaves geradas por [infra/keys/generate.sh](../../infra/keys/generate.sh)
  (não versionadas).
- **HS256 (fallback de dev):** sem chave RSA, os serviços usam HS256 com **segredo compartilhado**.
  > ⚠️ **Invariante HS256:** o `JWT_SECRET` precisa ser **idêntico** em todos os serviços e ter
  > **≥32 bytes** (o `jjwt` do drone rejeita chaves menores). Segredos divergentes → 401.
- **Rotação:** a evolução é validar por **`JWK_URL` + `kid`** (fetch dinâmico do JWKS).

## 4. O token — de pessoa e de serviço

**Access de pessoa** (`typ: at+jwt`, 5 minutos, [iam/identity/emissao.py](../../iam/identity/emissao.py)):

```jsonc
{
  "iss": "sgi-iam", "aud": "sgi-api",        // um aud por serviço: sgi-api, sgi-drone, sgi-iam
  "sub": "username", "user_id": "uuid",       // quem é
  "tenant_id": "uuid",                        // a empresa da sessão (confere com a RLS e o PDP)
  "sid": "uuid", "sst": 0,                    // a sessão (revogação em segundos)
  "amr": ["pwd", "otp"], "acr": "aal2",       // como provou quem é (RFC 8176 / NIST 800-63B)
  "auth_time": 0,                             // quando provou pela última vez (step-up, RFC 9470)
  "iat": 0, "nbf": 0, "exp": 0, "jti": "...", "token_type": "access"
}
```

Sem listas, papéis, flags de admin, plano nem e-mail (fase 4): perto de 950 B na linha
`Authorization` para qualquer persona. A lista exata vem do `GET /auth/me/`, lida das tabelas.

**Token de serviço** (`typ: svc+jwt`, `emissao.token_de_servico`): `sub: svc-<chamador>`, `tenant_id`,
o `aud` do produto de destino e **um** `scope` — hoje só `drone.projetos.desvincular`, que o drone
aceita só na rota de desvínculo. Nenhum serviço o aceita onde espera uma pessoa.

## 5. Endpoints de autenticação (IAM)

[iam/identity/urls.py](../../iam/identity/urls.py):

| Endpoint | O quê |
|---|---|
| `POST /auth/login/` | senha → cookies da sessão e do refresh + `{user, tenant, modules, session_expires_at}`, **sem token**; com segundo fator, o desafio |
| `POST /auth/login/segundo-fator/` | o código troca o desafio pela sessão |
| `POST /auth/refresh/` | desliza a janela da sessão (rotação do refresh) |
| `POST /auth/logout/` | revoga a sessão e apaga os cookies |
| `GET /auth/me/` | usuário + tenant + módulos + permissões (lidos das tabelas) |
| `GET/POST /auth/confirmar/` | o step-up: o código (ou a senha, sem segundo fator) faz o `auth_time` andar |
| `GET /.well-known/jwks.json` | chave pública (validação RS256) |
| `GET /auth/interno/bff/<serviço>/` | **interna** (404 na borda): o gateway troca o cookie pelo access (`api`, `drone`) |
| `GET /auth/interno/sessao/<sid>/` | **interna**: o PEP sem Redis pergunta se a sessão vale |
| `POST /auth/service-token/` | **interna**: token de serviço, pelo segredo compartilhado |

Sob o gateway, a IAM responde em `/auth` e a administração em `/iam` (ver
[servicos-e-integracoes.md](servicos-e-integracoes.md)).

## 6. Fluxos de sequência

### 6.1 Login (browser)
```
React            Gateway        IAM
  │  POST /auth/login (user,pass) │
  │ ─────────────►  ──────────►   │  valida senha (e o segundo fator, se houver)
  │                               │  abre a Sessao (sid) e o refresh
  │ ◄── Set-Cookie sgi_sessao (/, HttpOnly, SameSite=Strict)
  │ ◄── Set-Cookie sgi_refresh (/auth/, HttpOnly, SameSite=Strict)
  │ ◄── {user, tenant, modules, session_expires_at}      — nenhum token
```
Com HTTPS o cookie da sessão se chama `__Host-sgi_sessao`.

### 6.2 Uma chamada à API (o BFF)
```
React ──cookie + X-SGI-CSRF──► Gateway ──auth_request──► IAM /auth/interno/bff/api/
                                  │ ◄── 204 X-BFF-Authorization: Bearer <access aud=sgi-api>
                                  │ tira o cookie da sessão do pedido; põe o Authorization
                                  └──────────────────────► backend
```
Escrita com o cookie e sem `X-SGI-CSRF` (ou de outra origem) → **403** na borda. O `Authorization`
mandado pelo próprio cliente é descartado. O access fica guardado no Redis (DB 2) até perto de vencer.

### 6.3 O drone
O app do drone (`/drone/`) é da mesma origem: o cookie vai sozinho a `/odm-api/` e `/ws/`, e o
gateway injeta o access `sgi-drone` — inclusive no pedido de upgrade do WebSocket, que o drone lê no
handshake (o CONNECT do STOMP não leva token). O WebSocket de outra origem é recusado (CSWSH).

### 6.4 Validação num resource server (backend ou drone)
```
Gateway ──Bearer (aud do serviço)──► Resource server
                                       1. assinatura, exp, iss, aud do serviço, typ at+jwt
                                       2. sessão (sid) não revogada; época do usuário
                                       3. "usa o módulo?" / "pode?" → PDP (cache por classe)
                                       4. JIT: espelho local do usuário (por sub)
                                       5. RLS pelo tenant_id; ato grave (classe C) exige auth_time recente
```

### 6.5 Renovação, logout e o ato grave
A tela renova a sessão (`/auth/refresh/`) só quando houve interação — é isso que fecha a janela de
inatividade. Logout revoga o `sid`: o access já emitido cai na requisição seguinte em todo serviço.
O ato grave fora da janela de confirmação responde **401 `confirmacao_necessaria`** (RFC 9470); a tela
pede o código (ou a senha), chama `/auth/confirmar/` e refaz o pedido.

## 7. Provisionamento JIT

backend e drone **não** têm cadastro próprio de usuários: na primeira requisição autenticada, criam um
**espelho local** do usuário a partir das claims (chave = `sub`), preservando FKs locais (ex.:
`nucleo.Usuario`). Ver [dados-e-tenancy.md](dados-e-tenancy.md) §6.

## 8. Enforcement (resumo; detalhe na política)

- Toda pergunta "pode?" passa por um lugar só — `nucleo/autorizacao.py` no backend,
  `AutorizacaoService` no drone — e é respondida pelo PDP.
- **Camada 1 — entitlement:** `RequireModule("codigo")` (Django,
  [nucleo/permissions.py](../../backend/nucleo/permissions.py)) e a authority `MODULE_drone` (Java).
- **Camada 2 — RBAC:** `RequirePermission` (código do catálogo); o ato da classe C pede também a
  confirmação recente.
- Regras completas e estado por módulo em [../acesso-e-permissoes.md](../acesso-e-permissoes.md).
