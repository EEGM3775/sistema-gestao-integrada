# Integrações de API externas (`moduloapi`)

> Centraliza credenciais/tokens de APIs de terceiros por usuário (hoje: Google).
> Código: [backend/moduloapi/](../../backend/moduloapi/).

## Acesso
App **base** — sem `required_module`. Isolado por tenant (`BaseModel` → `TenantScopedModel`, PK UUID).

## Modelos
| Modelo | Guarda |
|---|---|
| `GoogleAccount` | Tokens de acesso/refresh e expiração da conta Google de um usuário (OAuth) |

## Endpoints (`/api/api/`)
`/google-accounts/` — CRUD das contas Google. (O prefixo duplo `api/api/` vem de
[config/urls.py](../../backend/config/urls.py).)

## Status / pendências
Pequeno e ativo. Ponto de extensão para futuras integrações OAuth; tokens são secretos — tratar como
dado sensível.
