# Staging (Fase 10.7) — runbook

> Ambiente **idêntico a produção**, com **dados separados**, para validar a leva de
> fundação (Fases 8→11) integrada **antes** do cutover com tenant real. Desenho de
> deploy em [../../docs/arquitetura/deploy-e-seguranca.md](../../docs/arquitetura/deploy-e-seguranca.md).

## O que torna isto "produção" (e não dev)

Staging usa **as mesmas imagens e a mesma topologia** do dev — o `docker-compose.yml`
base. A diferença é o **`.env.staging`** (modo produção) mais **um override de gateway**:

| Eixo | Dev (`.env`) | Staging (`.env.staging`) |
|---|---|---|
| `DEBUG` / `IAM_DEBUG` | `True` | **`False`** → RS256 obrigatório, cookies `Secure`, HSTS, fail-fast de config |
| Assinatura JWT | HS256 (dev) | **RS256** (chaves em `infra/keys/`) |
| Gateway | HTTP :8090 | **HTTPS :8443 (TLS)** + redirect 80→443 ([../gateway/nginx.staging.conf](../gateway/nginx.staging.conf)) |
| Celery | eager (in-process) | **assíncrono** (worker+beat consomem do broker) |
| Segredos | valores de dev | **gerados** (staging trata segredo como produção) |
| Projeto / containers / portas / **banco** | `sgi` / `sgi-*` / 8090,5432,6379 | `sgi-staging` / `sgi-stg-*` / 8443,5433,6380 → **coexiste com o dev** |

> **Por que TLS no staging:** com `DEBUG=False` o backend emite cookies `Secure`, que o
> browser só devolve sobre HTTPS. Sem TLS, o fluxo de sessão da Fase 10.6 (refresh
> silencioso) não seria fiel a produção. O cert self-signed é o **andaime local**
> equivalente ao ingress gerenciado de produção (Cloudflare Tunnel — Fase 10.3.2).

## Subir

```bash
# 1. env de staging (uma vez) — troque TODOS os TROQUE-* por segredos fortes
cp .env.staging.example .env.staging

# 2. chaves RSA do JWT, se ainda não existirem (compartilhadas com o dev)
bash infra/keys/generate.sh

# 3. sobe o stack (gera o cert TLS, builda e sobe em modo produção)
bash infra/staging/up.sh

# 4. fixtures demo/acme (uma vez, após os containers ficarem healthy)
bash testes/seeds/seed_staging.sh
```

Entrada: **https://localhost:8443/** (login `demo`/`demo123`). O browser vai alertar
sobre o cert self-signed — aceite (é o andaime local).

## Validar a leva 8→11 (gate automático)

```bash
bash infra/staging/validate.sh
```

Reusa os E2E das fases apontados ao gateway HTTPS de staging (confiando no cert via
`SSL_CERT_FILE`). Cada verde prova, **em modo produção**, o que a fase entregou:

| Script | Prova | Fase |
|---|---|---|
| `phase4_e2e.py` | SSO ponta a ponta pelo domínio único | 2 / 4 |
| `phase5_rs256_test.py` | assinatura **RS256** (HS256 recusado — só vale sob `DEBUG=False`) | 5 |
| `phase6_rbac_test.py` | entitlement de módulo + RBAC por permissão | 6 / 9 |
| `phase8_tenancy_test.py` | isolamento multi-tenant: RLS, `tenant` NOT NULL, uniques por-tenant | 8 |
| `phase9_auditoria_test.py` | trilha de auditoria imutável (`AuditLog`) | 9.E |
| `phaseC_whatsapp_test.py` | WhatsApp in-process (webhook HMAC + Celery) | 11.3 / C |
| `seg1_segundo_fator_test.py` | segundo fator (TOTP) para admin e supervisor | remodelagem 1 |
| `seg4_token_enxuto_test.py` | token enxuto, `sid`, PDP decidindo em todo módulo | remodelagem 4 |
| `seg5_bff_test.py` | BFF: nenhum token no navegador, `aud` por serviço, anti-CSRF | remodelagem 5 |
| `seg6_step_up_test.py` | step-up na classe C | remodelagem 6 |

Os roteiros moram em `testes/e2e/`; o gate usa o `.venv` (seg5 e seg6 abrem o navegador) e aceita
nomes para repetir só alguns: `bash infra/staging/validate.sh seg5_bff_test.py`. Ficam fora do gate o `seg6_caos_test.py` (derruba SpiceDB,
Redis e IAM — é do dev) e o `seg2_pdp_sombra_test.py` (fase 2, aposentada pela 4). Antes do gate, o
PDP precisa estar populado e virado: `sincronizar_pdp` na IAM e `modo_autorizacao --todos pdp
--forcar` no backend.

## Checagens manuais (fora do gate)

- **Sessão 10.6 (no browser):** login → **F5 mantém a sessão** (bootstrap via
  `/auth/refresh`, cookie HttpOnly) → trocar a senha na IAM **revoga em ≤5 min**
  (época no Redis DB 2). É o cenário que só é fiel sob HTTPS.
- **WebSocket 10.8 (`phase10_8_service_ws_test.py`):** a parte **service-token na
  borda** roda sob HTTPS (`SGI_GW=https://localhost:8443 python testes/e2e/phase10_8_service_ws_test.py`);
  o frame `/ws` usa **socket cru sem TLS** — aponte `SGI_WS_PORT` a um listener em
  claro se quiser exercitá-lo aqui (já validado E2E no stack de dev).
- **NF-e (11.1):** emissão real depende de credencial NFE.io (`NFE_IO_*`) — validação
  sob demanda.

## Parar

```bash
bash infra/staging/down.sh        # para os containers (mantém o banco)
bash infra/staging/down.sh -v     # + apaga os volumes sgi-staging_* (banco zerado)
```

## Andaimes de staging a substituir no go-live

Mesma disciplina do dev — conveniência local, não escopo de produção
([deploy-e-seguranca.md §3.1](../../docs/arquitetura/deploy-e-seguranca.md)):

- **cert TLS self-signed** → ingress gerenciado com TLS (Cloudflare Tunnel, 10.3.2);
- **segredos em `.env.staging`** → cofre de segredos (Vault / Secrets Manager, 10.3);
- **Asaas sandbox** → conta de produção por tenant;
- **cluster Postgres do compose** → Postgres gerenciado + PITR (DR, 10.3).
