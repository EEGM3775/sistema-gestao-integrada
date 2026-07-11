# Acesso & Permissões — modelo de plataforma

> Como a plataforma controla **quem entra**, **o que cada empresa contratou** e **o que cada
> usuário pode acessar** — de forma **genérica, reutilizável por qualquer módulo** (nunca específica
> do ERP). O módulo de drone (`funcoesODM`) é a **implementação de referência**.
> Roadmap de execução: ver [roadmap.md](roadmap.md), **Fase 6**.

## 1. Princípio

A autoridade de identidade é **uma só: a IAM**. Nenhum produto cria/autentica usuários; todos
recebem um **JWT assinado pela IAM** (RS256) e apenas o validam. Sobre isso existem **três níveis
independentes** de controle:

```
   AUTENTICAÇÃO        →  você é quem diz ser?            (login único na IAM, SSO)
   ENTITLEMENT (cam.1) →  a empresa contratou o módulo?   (AssinaturaTenant)
                          este usuário pode usá-lo?        (AcessoUsuarioModulo)
   RBAC (camada 2)     →  dentro do módulo, seu papel
                          pode ver/fazer isto?             (Perfil/Permissao)
   + ISOLAMENTO        →  só dados do seu tenant           (tenant_id em tudo + RLS)
```

As camadas são **ortogonais**: um usuário pode ter o módulo `rh` (camada 1) mas só com papel
"operacional" que não vê salários (camada 2); e jamais enxerga dados de outra empresa (isolamento).

## 2. Modelo de dados (na IAM — fonte de verdade)

| Entidade | Papel |
|---|---|
| `Tenant` | a empresa-cliente; fronteira de isolamento |
| `Usuario` | pertence a um tenant; `username` global (vira `sub` no JWT) |
| `Modulo` | **catálogo** de produtos vendáveis: `drone`, `crm`, `rh`, `erp_financeiro`, … |
| `AssinaturaTenant` | **camada 1 (empresa):** quais módulos o tenant **contratou** (+ vigência) |
| `AcessoUsuarioModulo` | **camada 1 (usuário):** quais desses módulos **este usuário** pode usar |
| `Perfil` / `Permissao` | **camada 2:** papéis/permissões dentro do tenant (RBAC) |

`Usuario.modulos_efetivos()` = **interseção** entre as assinaturas ativas do tenant e o acesso do
usuário (admins do tenant recebem todos os módulos ativos). É esse conjunto que entra no JWT.

## 3. O que viaja no JWT

```jsonc
{
  "sub": "username",                 // identidade
  "tenant_id": "...", "tenant_slug": "...",
  "modules":     ["erp_financeiro", "drone"],        // CAMADA 1 — entitlements efetivos
  "permissions": ["rh.dado_medico.view", "erp.conta_pagar.baixar"], // CAMADA 2 — permissões efetivas
  "roles":       ["financeiro"],                     // CAMADA 2 — nomes (transição/exibição)
  "is_tenant_admin": false, "iss": "sgi-iam", "exp": 0
}
```

Todo serviço valida a assinatura (RS256, chave pública/JWKS) e lê essas claims. **Nenhuma decisão
de acesso depende de tabela local de permissão** — a verdade está no token. Desde a **Fase 9.A**, a
checagem da camada 2 é por **permissão** (`permissions`); `roles` fica para transição/exibição.

## 4. Enforcement genérico (o padrão que TODO módulo segue)

A regra é sempre a mesma, independente da tecnologia do módulo:

1. **Entitlement (camada 1):** o endpoint exige um **código de módulo**; se ele não está em
   `modules`, responde **403** (`RequireModule`).
2. **RBAC por permissão (camada 2):** o endpoint declara `required_resource`/`required_permission` e
   `RequirePermission` checa o claim `permissions`; senão **403**. Token legado (sem `permissions`)
   cai no `RequireRole` (papel) durante a transição.
3. **Isolamento:** toda query filtra por `tenant_id` do token (+ RLS no Postgres).

### Implementação de referência — o drone (`funcoesODM`, Java)
- `SecurityConfig` exige a authority `MODULE_drone` em todo endpoint de negócio → **403** sem o
  módulo. O código exigido é **configurável** (`app.module.required`) — ou seja, **é um padrão
  genérico**, não algo "do drone".
- Prova: usuário **sem** `drone` recebe **403**; **com** `drone`, **200** (ver
  `infra/gateway/phase4_e2e.py`).

O drone também demonstra que um módulo pode ser uma **stack inteiramente separada** (Spring +
Angular) e ainda assim plugar na **mesma** identidade/entitlement — sem reimplementar nada.

## 5. Estado atual (honesto) por serviço/módulo

| Serviço / módulo | Autenticação | Entitlement (cam.1) | RBAC (cam.2) | Isolamento |
|---|---|---|---|---|
| **IAM** | é a autoridade | emite os entitlements | dono do catálogo + papéis (personas por tenant) | dono dos tenants |
| **Drone** (`funcoesODM`) | ✅ JWT IAM | ✅ `MODULE_drone` (403) | ⚠️ por owner | ✅ `tenant_id` |
| **ERP — `modulocrm` (`crm`)** | ✅ JWT IAM | ✅ `RequireModule` (403) | ✅ `RequirePermission` por recurso (fecha o S5) | ✅ tenant-scope |
| **ERP — `rh` (`rh`)** | ✅ | ✅ `RequireModule` | ✅ `RequirePermission` — `rh.dado_medico`/`rh.dado_bancario`/`rh.folha` (papéis provisionados, 403 destravado) | ✅ |
| **ERP — `moduloerp` (`erp_financeiro`)** | ✅ | ✅ `RequireModule` | ✅ `RequireRole("financeiro")` (migra p/ permissão na 9.B) | ✅ |
| **ERP — base** (`clientes`/`fornecedores`/`obras`/`empreendimentos`) | ✅ | n/a (sempre disponível) | ✅ `RequirePermission` por recurso (`cadastro.*`/`obra.*`) — 05/07/2026 | ✅ |
| **ERP — `modulodiario`** | ✅ | n/a (base) | ✅ ABAC próprio (`PodeModerarDiario` + equipe/responsável) | ✅ |
| **Sistema de lixo** (`/api/lixo/`) — 📋 **planejado, não implementado** | 📋 JWT IAM | n/a (base) | 📋 `plataforma.lixo.*` | 📋 tenant-scope |

**Leitura (após a Fase 9.A/9.B, 05/07/2026):** a **camada 1** segue genérica (`RequireModule` lê
`modules`). A **camada 2** passou a checar **permissão** (`RequirePermission` lê `permissions`), com
`RequireRole` **depreciado** (fallback p/ token legado). A IAM ganhou um **catálogo global de
permissões** (`modulo.recurso.acao`, [iam/identity/catalog.py](../iam/identity/catalog.py)),
**personas por tenant** compostas do catálogo (com trava anti-escalada) e uma **UI de administração**
(`/app/admin/papeis` e `/app/admin/usuarios`, via gateway `/iam/`). O 403 histórico do RH foi
**destravado** (papéis `rh_medico`/`rh_financeiro` provisionados). A **fatia C** (mascaramento de
campo/PII) também já vale: `FieldMaskingSerializerMixin` mascara campo sem permissão na leitura e
rejeita na escrita (RH, clientes, fornecedores). Validado por `iam/identity/tests.py`,
`backend/rh/tests.py`, `backend/rh/test_field_masking.py` e `backend/modulocrm/tests.py`.
**Pendência:** ABAC por objeto (fatia D) e remover os **modelos** legados `nucleo.Perfil`/`Permissao`.

> **Desenho-alvo (AD-9) — status por fatia:** **A** (catálogo + personas + `permissions` no JWT),
> **B** (`RequirePermission` no enforcement) e **C** (mascaramento de campo/PII) ✅. A **fatia D do
> AD-9** (ABAC por objeto — acesso a empreendimento) segue pendente; a **fatia E** (limpeza do
> `RequireRole`) também. **LGPD** (roadmap 9.D — portabilidade, esquecimento e incidente ANPD com
> confirmação do dono) ✅ 05/07/2026: `GET/POST /api/lgpd/<tipo>/<id>/exportar|esquecer/` e
> `/api/lgpd/incidentes/` ([nucleo/lgpd.py](../backend/nucleo/lgpd.py)). Desenho completo em
> [arquitetura/rbac-abac.md](arquitetura/rbac-abac.md); paywall/planos em
> [arquitetura/monetizacao.md](arquitetura/monetizacao.md).
>
> ⚠️ Numeração: "9.D" no [roadmap](roadmap.md) = **LGPD**; "fatia D" no AD-9 §6 = **ABAC por objeto**.
> São coisas diferentes (herança de dois esquemas).

## 6. Fase 6 — implementada (02/06/2026)

Enforcement **genérico e reutilizável** construído e aplicado:
- `RequireModule("codigo")` / `RequireRole("papel")` em
  [nucleo/permissions.py](../backend/nucleo/permissions.py) — espelho do `MODULE_drone`, lendo os
  claims `modules`/`roles` do JWT.
- Aplicado a `crm`/`rh`/`erp_financeiro` (+ papel `financeiro`).
- Legados removidos (login do ERP; endpoints `Perfil`/`Permissao`).

Pendências: mascaramento de campos por papel; remoção dos modelos `nucleo.Perfil`/`Permissao`;
aplicar o contrato (§7) aos módulos hoje vazios. Detalhe e DoD em
[roadmap.md](roadmap.md), **Fase 6**.

## 7. Papel `gestor_lixo` (planejado)

Papel intra-tenant que controla o ciclo de vida do sistema de lixo:

| Operação | `gestor_lixo` | Usuário comum |
|---|---|---|
| Mover registro para o lixo | ✅ | ✅ |
| Ver itens no lixo | ✅ | ❌ |
| Restaurar item do lixo | ✅ | ❌ |
| Purgar permanentemente | ✅ | ❌ |
| Configurar retenção automática | ✅ | ❌ |

Implementação: `RequireRole("gestor_lixo")` nos endpoints de restauração e purge.
Arquitetura completa do lixo: [arquitetura/lixo.md](arquitetura/lixo.md).

## 8. Contrato de um módulo novo (vendável isoladamente)

Qualquer módulo futuro — um app Django **ou** um serviço separado (estilo drone), incluindo os hoje
vazios (`moduloaps`, `modulodms`, `modulopdca`, `moduloscm`, `modulosil`, `modulomaps`) — segue o
**mesmo contrato**, sem reimplementar identidade:

1. Registrar um `Modulo` (código) no catálogo da IAM.
2. Tornar-se vendável por `AssinaturaTenant` (empresa) e liberável por `AcessoUsuarioModulo` (usuário).
3. Validar o JWT da IAM (RS256/JWKS) e **exigir o código do módulo** (403 se ausente) — via
   `RequireModule` (Django) ou o filtro de authority (estilo drone).
4. Aplicar RBAC por papel quando necessário e filtrar tudo por `tenant_id`.
