# Núcleo (`nucleo`)

> A fundação do ERP: **espelho JIT da identidade** (a IAM é a dona — ver
> [../acesso-e-permissoes.md](../acesso-e-permissoes.md)), **tenancy**, **permissões genéricas de
> módulo/papel**, dead-letter de Celery e log de atividades.
> Código: [backend/nucleo/](../../backend/nucleo/).

## O que vive aqui

| Peça | Arquivo | O que faz |
|---|---|---|
| `Tenant` / `Usuario` (espelhos JIT) | `models.py` | Criados/atualizados a partir das claims do JWT na 1ª requisição (chave = `sub`); preservam FKs locais |
| `TenantScopedModel` / `TenantScopedViewSetMixin` | `tenancy.py` | FK `tenant` em todo modelo de negócio + escopo automático nos ViewSets + RLS (`set_config`) — ver [prancha dados-e-tenancy](../arquitetura/dados-e-tenancy.md) |
| `RequireModule("codigo")` / `RequireRole("papel")` | `permissions.py` | Entitlement (camada 1) e RBAC (camada 2) lendo as claims `modules`/`roles` — ver [../acesso-e-permissoes.md](../acesso-e-permissoes.md) |
| `FailedTask` (DLQ) | `models.py` + `tasks.py` | Dead-letter de tarefas Celery que esgotaram os retries |
| `LogAtividadeUsuario` | `models.py` + `signals.py` | Log central de atividades (tarefas Celery + microsserviços) |
| `Perfil` / `Permissao` | `models.py` | **Legado** — a fonte de papéis é a IAM (claims); remover os modelos é pendência da Fase 6 |
| `PreCadastro` | `models.py` | Contatos desconhecidos vindos do bot de WhatsApp |

## Dead Letter Queue (`FailedTask`)

Task declarada com `@shared_task(bind=True, base=nucleo.tasks.DLQTask, ...)` grava, ao esgotar as
retentativas (`on_failure`), o `task_id` (UUID), nome, argumentos, exceção e traceback em
`FailedTask` — diagnosticável e reprocessável pelo Django Admin ("Tarefas Falhas").

**Diretriz para tasks:** passar **identificadores, não dados brutos** — em caso de falha os `args`
são persistidos em texto plano.
`processar_pagamento.delay(pagamento_id=456)` ✅ · `processar_pagamento.delay(numero_cartao=…)` ❌

## Log de atividades (`LogAtividadeUsuario`)

- **Tarefas Celery:** logadas automaticamente por signals (início + fim/status). Passar
  `user_id=` nos `kwargs` para associar ao usuário.
  > ⚠️ Os signals gravam 2+ linhas por task com os args completos e sem índice — achado **A6**.
- **Microsserviços:** `POST /api/log-interno/` (`{acao, entidade_alvo, detalhes, user_id?}`).
  > ⚠️ O endpoint é `AllowAny` — endurecer antes de produção (achado **S7**, e o desenho-alvo de
  > auth serviço→serviço é a Fase 10.8).

## Autenticação de serviço (legado morto)

O comando `create_service_token` (`management/commands/`) gerava tokens estáticos DRF para
microsserviços chamarem a API do ERP (`Authorization: Token …`). **Esse mecanismo está morto desde
a Fase 6** — o ERP só aceita JWT da IAM; tokens gerados por ele recebem 401 (achado **D1**,
confirmado por teste em `nucleo/test_legacy_token.py`: afeta os callbacks de `funcoesia`,
`funcoesnf` e `funcoeswhatsapp`; o `funcoeslead` foi absorvido pelo ERP na Fase 11.2). O substituto
planejado é **JWT de serviço de vida curta emitido pela IAM** (Fase 10.8 do
[roadmap](../roadmap.md)); o comando e as instruções antigas de "criar Perfil no Django Admin"
não devem ser usados.
