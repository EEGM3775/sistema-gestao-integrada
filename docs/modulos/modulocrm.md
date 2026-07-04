# CRM (`modulocrm`)

> Funil comercial: da captação (lead) ao fechamento (oportunidade). Módulo **vendável**.
> Código: [backend/modulocrm/](../../backend/modulocrm/). Toda a lógica roda in-process
> (o antigo microsserviço [funcoeslead](funcoeslead.md) foi absorvido — Fase 11.2).

## Acesso
Entitlement **`crm`** (`required_module = "crm"`, com `[IsAuthenticated, RequireModule]`). Isolado por
tenant (todos os modelos herdam de `BaseModel` → `TenantScopedModel`, com PK UUID).

## Modelos
| Modelo | Guarda |
|---|---|
| `Campaign` | Campanha de marketing (período, orçamento) |
| `Lead` | Entrada do funil (status `NOVO`→`CONTATADO`→`QUALIFICADO`→`CONVERTIDO` ou `PERDIDO`; origem, score) |
| `Account` | Conta/empresa cliente |
| `Contact` | Contato individual dentro de uma conta |
| `Opportunity` | Negociação (estágio, probabilidade, data de fechamento); `amount` calculado dos produtos |
| `OpportunityProduct` | Itens da oportunidade (produto + quantidade + preço) |
| `Interaction` | Ligação/e-mail/reunião/tarefa, com atribuição via GenericForeignKey |

## Relações
`Lead`→`Campaign`; `Contact`→`Account`; `Opportunity`→`Account`/`Contact`/`empreendimentos.Empreendimento`;
`OpportunityProduct`→`Opportunity`/`fornecedores.ProdutoServicoFornecedor`; `Interaction`→
lead/contact/opportunity. **Ligação ao cadastro real:** `Account.cliente_associado` e
`Contact.cliente_associado` são OneToOne com `clientes.Cliente`. `assigned_to` → usuário responsável.

## Comportamento
- **Conversão de lead** (`services.converter_lead`, transacional): lead `QUALIFICADO` →
  Account (reaproveitada por nome no tenant) + Contact + Opportunity (`PROPOSTA`, fechamento
  estimado em 30 dias); o lead vira `CONVERTIDO`. Tudo herda o tenant do lead.
- **Scoring** (`services.calcular_score`): origem (indicação 30 · site 20 · evento 10) +
  empresa (20) + telefone (10).
- **Lembrete de tarefas a vencer:** Celery task `tasks.notificar_tarefas_a_vencer`
  (`CELERY_BEAT_SCHEDULE`, horário; e-mail via `MAIL_*` — sem `MAIL_HOST`, no-op).
- `Interaction.save/delete` emitem o sinal `interaction_changed` — o calendário usa para
  invalidar cache.

## Endpoints (`/api/crm/`)
`/leads/` (+ `POST /leads/{id}/convert/` · `POST /leads/{id}/score/`; filtros `status`, `source`,
`campaign`) · `/accounts/` · `/contacts/` · `/opportunities/` · `/opportunity-products/` ·
`/interactions/` (filtros `type`, `completed`, `due_date__gte/lte`, `lead`, `opportunity`,
`contact`).

## Status / pendências
Ativo e enforced pelo módulo `crm`, com testes (`tests.py`). **Sem UI React ainda.**
