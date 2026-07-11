# Changelog

Todas as mudanças notáveis desta versão são documentadas aqui.

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
- L4 - Integração `funcoeslead` ↔ ERP morta
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
- ERP como resource server com tenancy
- SSO ponta a ponta
- UI integrada (gateway, domínio único)
- Vínculo drone ↔ obra/empreendimento
- Deploy unificado
- Endurecimento RS256/JWKS + borda
- Consolidação de identidade & RBAC