# Cargos, papéis e permissões — RBAC + ABAC (camada 2)

> **Prancha de desenho — em implementação (Fase 9).** Registra o modelo-alvo de controle de
> acesso *dentro* do tenant (a "camada 2"). Decisão em [AD-9](../arquitetura.md#2-decisões-de-arquitetura-registradas);
> o **estado atual** (o que existe hoje no código) fica em
> [../acesso-e-permissoes.md](../acesso-e-permissoes.md); o **status por fatia** em
> [../roadmap.md](../roadmap.md#fase-9). A camada 1 (entitlement de módulo) **não muda** — ver AD-4.
> A **fatia A** (catálogo + permissões no JWT + personas dinâmicas) já está no código:
> [iam/identity/catalog.py](../../iam/identity/catalog.py) é a fonte única; §9 abaixo descreve o
> catálogo real e **como estendê-lo ao importar módulos da v01**.

## 1. Por que redesenhar (contexto)

O acesso tem duas camadas. A **camada 1** (módulo contratado: `AssinaturaTenant ∩ AcessoUsuarioModulo`
→ claim `modules` → `RequireModule`) é sólida. A **camada 2** (papéis) é imatura e **imprevisível**:

1. **Papéis são strings mágicas espalhadas** — só existem 3 no código (`financeiro`, `rh_medico`,
   `rh_financeiro`); não há catálogo de "quais papéis existem e o que cada um pode".
2. **Provisionamento ≠ enforcement** — o seed cria `financeiro`/`operacional`; o código exige
   `financeiro`/`rh_medico`/`rh_financeiro`. `operacional` é papel morto; `rh_medico`/`rh_financeiro`
   são inalcançáveis (nunca semeados) → é a origem dos **403** na ficha do funcionário.
3. **O modelo granular já existe, mas é código morto** — `Permissao` + `Perfil.permissoes` (M2M)
   estão no banco, mas [iam/identity/tokens.py](../../iam/identity/tokens.py) só coloca **nomes** de
   papel no JWT. Zero granularidade (ver × editar), zero campo.
4. **Buraco de consistência/segurança** — como só o *nome* é checado, um tenant-admin pode criar um
   `Perfil` chamado `financeiro` **sem nenhuma permissão** e ele passa no `RequireRole("financeiro")`.

## 2. Decisão (o modelo-alvo)

Modelo **híbrido RBAC + ABAC**, com **papéis definidos por tenant**, granularidade **ação + campo
(PII)**. Quatro peças, uma só fonte de verdade (o catálogo):

```
 CATÁLOGO DE PERMISSÕES  (global, em código)  →  a espinha dorsal previsível
        ▲                                         permissões atômicas: modulo.recurso.acao
        │ bundle
 PAPÉIS  (Perfil, por tenant)                  →  cada empresa compõe do pool (RBAC)
        │ atribuídos a
 USUÁRIO  →  JWT carrega as PERMISSÕES efetivas (não nomes)
        │ refinado por
 POLÍTICAS ABAC  (contexto: dono/obra/valor/hora)  +  MASCARAMENTO DE CAMPO (PII)
```

### 2.1 Catálogo de permissões — global e em código (a previsibilidade)

Mesmo com papéis por tenant, as **permissões precisam ser um vocabulário finito, global e definido
em código** — porque *endpoints* e *serializers* as referenciam. **É daqui que vem a previsibilidade**,
não de papéis fixos. Formato `modulo.recurso.acao`:

| Exemplo | Significado |
|---|---|
| `rh.funcionario.view` / `.edit` | ler / editar cadastro do funcionário |
| `rh.dado_medico.view` / `.edit` | prontuário / ASO (PII sensível) |
| `rh.dado_bancario.view` / `.edit` | conta bancária (PII sensível) |
| `rh.folha.view` / `.edit` | folha e pagamentos |
| `erp.conta_pagar.view` / `.edit` / `.baixar` | financeiro + verbo de negócio |
| `erp.cobranca.emitir` | ação de domínio (não é CRUD) |

Ações padronizadas: `view`, `create`, `edit`, `delete` **+** verbos de domínio (`baixar`, `emitir`,
`aprovar`). O catálogo vive num registry Python (fonte única), sincronizado para a tabela
`Permissao` da IAM por comando/migração. Um **teste de conformidade** garante: toda permissão exigida
no código ∈ catálogo, e todo item do catálogo existe na IAM — **isso mata o problema nº 2 e nº 1**.

### 2.2 Papéis — por tenant, compostos do pool (RBAC)

`Perfil` (já é por tenant, `unique_together (tenant, nome)`) tem seu `permissoes` M2M **ativado**: o
tenant-admin monta cada cargo escolhendo permissões do catálogo. O papel é **do tenant** (renomeia,
recompõe). Para conciliar "papéis por tenant" com previsibilidade, o sistema oferece **templates de
fábrica** (bundles em código: `rh_gestor`, `rh_medico`, `rh_financeiro`, `financeiro`, `operacional`,
…) com que um tenant novo já nasce — e que ele pode **clonar e ajustar**. Ele começa de uma linha de
base sã e documentada, mas manda no resultado. (O que é global e imutável é o **catálogo de
permissões**; o que é do tenant é o **agrupamento** em papéis.)

### 2.3 Políticas ABAC — condições de atributo sobre a permissão

Regras que não cabem numa permissão estática são **políticas** avaliadas em runtime com contexto:
"gestor vê só a folha da **sua** obra", "aprovar acima de R$ X exige papel Y", "acesso só em horário
comercial". Entradas da política:

- **Sujeito** — do JWT (`tenant_id`, `permissions`, `roles`, `is_tenant_admin`) + perfil (obras
  atribuídas, cargo).
- **Recurso** — o objeto acessado (dono, obra, valor, status).
- **Ambiente** — hora, IP (opcional).

Desenho: checagem por objeto via DRF `has_object_permission`, delegando a um **registry de políticas**
indexado por `(permissao, tipo_de_recurso)`. Política = predicado `(sujeito, recurso, ambiente) → bool`.
**Default = RBAC puro** (libera se tem a permissão); políticas ABAC só refinam recursos específicos —
ou seja, ABAC é **opt-in por recurso**, não um custo global.

### 2.4 Campo (PII) — mascarar na leitura, barrar na escrita · ✅ 05/07/2026 (Fase 9.C)

A camada mais fina (a escolha "ação + campo"). Um **mapa de sensibilidade** por serializer
(`sensitive_fields = {campo: permissao_exigida}`), aplicado por um mixin reutilizável —
[`FieldMaskingSerializerMixin`](../../backend/nucleo/field_masking.py):

O mixin tem **dois eixos independentes** (não um derivado do outro):
`sensitive_fields = {campo: permissao_leitura}` e `write_protected_fields = {campo: permissao_escrita}`.

- **Leitura** (`sensitive_fields`): mascara o campo cuja permissão falta — **devolve o registro,
  mascara o campo**, em vez de 403 no endpoint inteiro. (Ex.: quem tem `rh.funcionario.view` vê o
  funcionário, mas CPF vem `••••09` sem `rh.cpf.view` e salário vem `null` sem `rh.folha.view`.)
  Documentos/conta usam máscara **parcial** (`••••` + últimos dígitos); valores monetários, chave PIX
  e texto livre são **redigidos** (`null`). **Fail-closed:** sem usuário no contexto, mascara tudo.
- **Escrita** (`write_protected_fields`): rejeita com 400 (e loga) gravação em campo protegido, com a
  permissão `.edit` **declarada explicitamente**. É **opt-in** e só cobre campos cuja `.edit` existe e
  é concedível (salário→`rh.folha.edit`, banco→`cadastro.*_banco.edit`). **Por quê explícito:** derivar
  a escrita da leitura (`rh.cpf.view`→`rh.cpf.edit`) travaria o cadastro — `rh.cpf.edit` **não existe**
  no catálogo, então ninguém criaria funcionário. A escrita do CPF é do cadastro (`rh.funcionario.edit`,
  gate do endpoint); só a **leitura** do CPF é sensível.

**Mudança de filosofia:** antes o endpoint inteiro dava 403 (tudo-ou-nada); agora é **portão grosso
no endpoint** (módulo + permissão-base) **+ máscara fina no campo**. Resultado prático: a ficha do
funcionário **para de "chover" 403**. **Cobertura:** RH (`Funcionario` CPF/salário, `DadoMedico`,
`DadoBancario`, `Pagamento`, `Folha`), clientes (`Cliente` CPF via `cadastro.cliente_doc.view`,
`DadoBancarioCliente`) e fornecedores (só `DadoBancarioFornecedor` — **CNPJ não é mascarado**, é dado
público de PJ). Testes: `testes/backend/rh/test_field_masking.py` (11) verde sobre Postgres.

## 3. O que passa a viajar no JWT

| Claim | Hoje | Alvo |
|---|---|---|
| `modules` | ✅ entitlements efetivos | igual |
| `roles` | ✅ **nomes** (base da checagem) | mantidos **só para exibição/auditoria** |
| `permissions` | ❌ | **novo** — conjunto efetivo (união das permissões dos papéis ∩ módulos assinados). **A checagem passa a ser por permissão.** |

Tamanho do token: conjuntos de permissão podem crescer → mitigar com códigos compactos e **wildcards**
(`rh.*`); se ficar grande, carregar `perms_version` + hash e o resource server busca/cacheia o
conjunto na IAM (mesmo padrão do JWKS). **Começar embutindo**, revisitar se o tamanho incomodar.
Atributos de runtime do ABAC (dono, obra do recurso) **não** vão no token — são resolvidos no servidor.

## 4. Componentes de enforcement (alvo)

| Componente | Papel | Substitui |
|---|---|---|
| `RequirePermission("code")` | checa `code ∈ token.permissions` | `RequireRole` (nome de papel) |
| `PolicyCheckMixin.has_object_permission` | ABAC por objeto via registry de políticas | — (novo) |
| `FieldMaskingSerializerMixin` | máscara na leitura + guarda na escrita, do mapa de sensibilidade | 403 tudo-ou-nada |

Os três leem o **mesmo catálogo** → fonte única. `RequireModule` (camada 1) permanece intacto.

## 5. Motor de política — sub-decisão em aberto

| Opção | Prós | Contras |
|---|---|---|
| **Predicados em código** (registry próprio em `nucleo/authz/`) | zero dependência, testável, controle total | escreve-se o encanamento à mão |
| **Casbin (pycasbin)** | RBAC+ABAC maduro, integra com Django, arquivos model/policy | curva de aprendizado, mais uma lib |
| **Oso / Polar** | DSL expressiva p/ regras relacionais | lib externa, DSL própria |
| **OpenFGA / OPA(Rego)** | poderosíssimos (Zanzibar / policy-as-service) | **serviço a mais** — contra a meta de reduzir superfície (Fase 10) |

**Recomendação:** começar com **predicados em código** (poucas políticas reais hoje) e só adotar
Casbin se o volume/complexidade justificar — decisão por evidência, não antecipada.

## 6. Migração a partir do estado atual (por fatias, na implementação)

1. **Fatia A — catálogo + destravar:** registry do catálogo + sync p/ `Permissao` + teste de
   conformidade + templates de fábrica; **provisionar `rh_medico`/`rh_financeiro`** nos tenants
   existentes. *(Só isto já resolve o 403 de hoje.)*
2. **Fatia B — permissão no token:** claim `permissions` + `RequirePermission`; migrar os checks de
   `financeiro`/RH; manter `RequireRole` como **alias depreciado** durante a transição.
3. **Fatia C — campo/PII:** `FieldMaskingSerializerMixin` + mapa de sensibilidade (RH e ERP) —
   fecha o DoD da **Fase 9**.
4. **Fatia D — ABAC:** motor de políticas para as regras contextuais que existirem (própria-obra,
   limites de aprovação).
5. **Fatia E — limpeza:** remover `RequireRole`, aposentar `operacional` morto e os checks por nome.

## 7. Consequências (honesto)

- Papéis por tenant **+** ABAC **+** campo = **máxima flexibilidade, máxima complexidade**. A
  previsibilidade passa a vir do **catálogo + teste de conformidade**, não de papéis fixos. O tenant
  ganha poder e o ônus de compor papéis → mitigado por **templates de fábrica** e uma boa UI de admin.
- Checagem por objeto + máscara de campo custam por requisição → cachear o conjunto de permissões (no
  token) e os mapas de sensibilidade (em memória); política de objeto só onde declarada.
- Cresce a superfície da IAM (UI/API de papéis e permissões por tenant) e é uma mudança transversal:
  toca a IAM (claims, modelos) **e** todo resource server (checagem, serializers).

## 8. Decisões em aberto (para a implementação)

- Motor de política: predicados próprios × Casbin × Oso (recomendação: começar próprio).
- Permissões no token × buscadas-e-cacheadas (recomendação: embutir + versão).
- Máscara de campo: redigir (null) × parcial (`•••` + últimos 4) por tipo de campo.
- Oferecer "marketplace" de templates de papel entre tenants? (provavelmente não agora.)

## 9. Catálogo real e extensão (fatia A — implementado)

A fonte única é [iam/identity/catalog.py](../../iam/identity/catalog.py): uma tupla `CATALOGO` de
permissões atômicas `modulo.recurso.acao` e um dicionário `TEMPLATES_PAPEL` de personas de fábrica.
`manage.py sync_authz` reflete o catálogo na tabela `Permissao` e compõe um `Perfil` por template em
cada tenant. O JWT passa a carregar `permissions` (`Usuario.permissoes_efetivas()` — união dos papéis
**∩ módulos assinados**; `base`/`plataforma` não dependem de entitlement).

**Cobertura atual (99 permissões, 6 grupos):** `rh`, `erp_financeiro`, `crm`, `drone` (módulos
vendáveis), `base` (obras/empreendimentos/diário/IA/calendário/cadastros — sem entitlement) e
`plataforma` (auditoria, LGPD, lixeira, config, integrações, **gestão de papéis**). PII sensível é
**recurso próprio** (`rh.dado_medico.*`, `rh.dado_bancario.*`, `cadastro.cliente_banco.*`,
`cadastro.fornecedor_banco.*`) — nunca varrida por wildcard de outro recurso, para a máscara da fatia C.

**Personas de fábrica (14):** `diretoria`, `rh_gestor`, `rh_medico`, `rh_financeiro`, `financeiro`,
`tesouraria`, `fiscal`, `comercial`, `engenharia`, `campo`, `drone_analista`, `auditor` (read-only),
`gestor_lixo`, `operacional`. São **linha de base**: cada tenant clona e recompõe (§2.2).

### 9.1 Personas dinâmicas — tela dedicada de Administração (não no "criar cargo")

As personas fixas **não bastam** para um SaaS completo. Um usuário de **alto poder** (admin do tenant,
ou quem receber `plataforma.papel.gerir`) compõe papéis livremente a partir do catálogo.

**Decisão de superfície:** a gestão de papéis mora numa tela **dedicada de Administração**
(`/app/admin/papeis` — "Papéis e Acessos"), **não** dentro do "Novo Cargo" do RH. Motivo: `Cargo` (RH)
é função na empresa (muitos, ligados a folha/funcionários); `Perfil` (persona) é papel de acesso
(poucos, ligados a usuários de login, sensível a segurança). Misturá-los violaria separação de
responsabilidades (quem edita cargo estaria editando segurança). A ponte opcional — o form de cargo
apontar para um papel de acesso — fica como evolução, sem transformar o cargo num painel de permissões.

Fluxo (frontend → gateway `/iam/` → IAM, guardado por `IsTenantAdmin`):

| Endpoint (IAM, via `/iam/`) | Uso |
|---|---|
| `GET /catalogo-permissoes/` | catálogo agrupado por módulo + flag `atribuivel` (módulo assinado) + `templates` de fábrica p/ clonar. |
| `GET/POST/PATCH/DELETE /perfis/` | CRUD de papéis, escopado ao tenant (`PerfilViewSet`). |
| `GET /permissoes/` | leitura do vocabulário (liberada ao admin de tenant). |

Front: [modules/admin/](../../frontend/src/modules/admin/) (`PersonasPage` + `PersonaForm` com picker
por módulo; módulo não assinado fica bloqueado no picker). Menu "Papéis e Acessos" só aparece p/
`is_tenant_admin`. O gateway ganhou `location /iam/` → IAM (remove o prefixo).

**Trava anti-escalada** (`PerfilSerializer.validate_permissoes`): um papel só recebe permissão do
catálogo e de módulo `base`/`plataforma` **ou** de módulo que o tenant **assina** — o admin nunca
escala além do próprio plano. Superuser de plataforma é isento. Unicidade `(tenant, nome)` validada à
mão (o `UniqueTogether` do DRF exigiria `tenant` no payload; ele é injetado pelo `perform_create`).

### 9.2 Padrão de extensão — ao importar um módulo (inclui os da v01)

Os módulos ainda **placeholder** (`aps`, `dms`, `pdca`, `scm`, `sil`, `maps` — porte da Fase 7) e
qualquer módulo novo **entram no controle de acesso por aqui**, sem tocar enforcement:

1. **Registrar as permissões** do módulo em `CATALOGO` (`catalog.py`), formato `modulo.recurso.acao`,
   `modulo` = código do entitlement (ex.: `scm`) ou `base`/`plataforma`. PII sensível = recurso próprio.
2. **Compor as personas**: adicionar os novos códigos aos `TEMPLATES_PAPEL` que fizerem sentido
   (wildcards `modulo.*` / `modulo.recurso.*` são aceitos na autoria; PII fica **fora** dos wildcards).
3. **Sincronizar**: `manage.py sync_authz --all-tenants` cria as `Permissao` e recompõe os papéis.
4. **Enforcement** (fatias B/C): `RequirePermission("scm.recurso.acao")` no ViewSet e, se houver campo
   sensível, entrada no mapa de sensibilidade do `FieldMaskingSerializerMixin`.

O **teste de conformidade** ([testes/iam/identity/tests.py](../../testes/iam/identity/tests.py)) garante que todo
template ⊆ catálogo e o formato `modulo.recurso.acao` — um código órfão falha o CI, não passa silencioso.
Assim, quando um módulo da v01 é portado, ele **já nasce contemplado**: permissões no catálogo, papéis
compostos, e o admin do tenant podendo delegá-lo a personas sem intervenção de plataforma.