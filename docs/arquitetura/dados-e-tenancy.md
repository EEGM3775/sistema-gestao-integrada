# Prancha — Dados & multi-tenancy

> Como os dados são particionados e isolados. Visão macro em [../arquitetura.md](../arquitetura.md)
> §4; entidades de negócio em [../dominio.md](../dominio.md). Código do mecanismo:
> [backend/nucleo/tenancy.py](../../backend/nucleo/tenancy.py).

## 1. Um banco por produto (AD-7)

Cada produto é uma unidade destacável, com **banco próprio** — isolamento de falhas e de venda.

| Banco | Dono | Conteúdo |
|---|---|---|
| `iam_db` | IAM | tenants, usuários, perfis/permissões, módulos, assinaturas |
| `erp_db` | ERP | todo o domínio de negócio (empreendimentos, obras, clientes, financeiro, RH, CRM, …) |
| banco do funcoesODM | drone | projetos, tasks, imagens, ortofotos (stack própria) |

`iam_db` e `erp_db` vivem no mesmo cluster PostgreSQL; o drone tem o seu. Não há FK entre bancos
(ver §5). Cache e fila (Celery) em **Redis**.

## 2. PostgreSQL como banco de registro

- Conexão por env (`DB_HOST`, `POSTGRES_*`, `DB_SSLMODE`); SQLite só como fallback de dev.
- **Cluster endurecido:** instância gerenciada com **backups + PITR**, **réplica de leitura** (BI não
  compete com a carga transacional), **roles de menor privilégio** por serviço (`iam_app`, `erp_app`,
  `odm_app`, `bi_readonly`, role administrativo só para migrações), **TLS** obrigatório.
- Inicialização dos bancos/roles: [infra/postgres/init/](../../infra/postgres/init/).

## 3. Fronteira de tenant

Toda entidade de negócio do ERP herda o mixin **`TenantScopedModel`**
([nucleo/tenancy.py](../../backend/nucleo/tenancy.py)), que adiciona o FK `tenant` (indexado). É
aplicado de forma ampla — empreendimentos, obras, clientes, fornecedores, moduloerp, rh, modulocrm,
modulodiario, modulocalendar, moduloapi, funcoesia. O drone carrega `tenant_id` nas suas entidades.

```python
class TenantScopedModel(models.Model):
    tenant = models.ForeignKey("nucleo.Tenant", on_delete=CASCADE, db_index=True, ...)
    class Meta: abstract = True
```

## 4. Enforcement do isolamento (duas camadas)

### 4.1 Aplicação — `TenantScopedViewSetMixin`
Aplicado nos ViewSets do ERP. Escopa em **dois pontos** para cobrir todos os caminhos:
- `get_queryset` — pega `list()` customizados que chamam `self.get_queryset()`.
- `filter_queryset` — pega o caminho padrão de `list()` e de `get_object()` (detail/update/destroy).

Na escrita, `perform_create` injeta o `tenant` do usuário e `perform_update` o reforça (impede mover um
registro para outro tenant via payload). **Superusuário** (admin de plataforma) vê tudo.

> Nota construtiva: mesmo que um ViewSet sobrescreva `get_queryset` (ex.: para otimizar com
> `select_related`) e esqueça de chamar `super()`, o `filter_queryset` do mixin ainda garante o
> escopo em list/detail. Filtrar duas vezes pelo mesmo tenant é idempotente.
> ⚠️ `APIView` puras **não** passam pelo mixin — nem escopam nem armam a RLS (achados S1/S2 da
> revisão v01; ver [pendencias.md](../pendencias.md)).

### 4.2 Banco — Row-Level Security (defesa em profundidade)
No `initial()` da requisição, o mixin executa
`SELECT set_config('app.current_tenant', <tenant_id>, true)`; políticas RLS por tabela usam
`current_setting('app.current_tenant')`. Requer `ATOMIC_REQUESTS=True` (o `is_local=true` vale por
toda a requisição). No SQLite é no-op. Assim, **um bug de aplicação não vaza dados entre clientes**.

## 5. Integridade & cross-DB

- **Constraints no banco:** NOT NULL, UNIQUE, **CHECK** (ex.: `Boleto` exige *exatamente uma* das
  associações conta-a-pagar/conta-a-receber), FKs com `on_delete` correto. Dinheiro sempre em
  `DECIMAL`. `tenant` NOT NULL e constraints `unique` **por-tenant** fazem parte do desenho.
- **Sem FK entre bancos:** o vínculo drone↔obra/empreendimento é por **id** (`obraId`,
  `empreendimentoId` no `Project` do drone). A exclusão é tratada por **evento/soft-unlink**
  (`DELETE /odm-api/projects/links/{obra,empreendimento}/{id}` zera a referência e preserva o projeto)
  + reconciliação de órfãos. Ver [servicos-e-integracoes.md](servicos-e-integracoes.md).

## 6. Identidade espelhada (JIT)

O ERP **não** é dono da identidade. Em `nucleo` há espelhos locais provisionados a partir do JWT:
`Tenant` e `Usuario` (`Usuario.tenant`), criados/atualizados na primeira requisição (chave = `sub`).
Preserva as FKs locais (ex.: `LogAtividadeUsuario`, `obras.DocumentoObra.aprovador`).
`nucleo.Perfil`/`Permissao` são legado — a fonte de papéis é a IAM, via claims.

## 7. Auditoria & migrations

- **Trilha de auditoria:** `nucleo.LogAtividadeUsuario` (usuário, ação, entidade-alvo, detalhes JSON,
  timestamp) cobre ações sensíveis; a `AuditLog` imutável para RH/financeiro é a Fase 9.5.
  `nucleo.FailedTask` é a *dead-letter* de tarefas Celery (tasks com `base=nucleo.tasks.DLQTask`).
- **Migrations versionadas** por serviço, revisadas; nada de alteração manual em produção. IAM e ERP
  rodam `migrate` na subida do container.

## 8. Modelo de dados macro

As entidades e suas ligações (Empreendimento↔Obra↔Cliente↔Fornecedor↔Financeiro↔RH↔CRM↔Diário) estão
em [../dominio.md](../dominio.md). Detalhe campo a campo em [../modulos/README.md](../modulos/README.md).
