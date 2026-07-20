# Frontend — Projeto de Interiores

> **Planta** do shell React: visual identity, estrutura de shell, inventário de páginas, hierarquia
> de componentes, roteamento, fluxo de auth e camada de dados. Descreve o sistema **inteiro**
> (pronto e planejado), **sem status** — o status por módulo e o fluxo testável estão na
> [tabela de frontend do roadmap](roadmap.md#estado-dos-módulos--frontend-react-08062026); as
> **convenções de código** (obrigatórias para quem desenvolve) em
> [frontend-convencoes.md](frontend-convencoes.md)
> Stack: React 19 · Vite 7 · TypeScript 5.8 · Tailwind CSS 4 · React Router v7 · Axios ·
> TanStack Query/Table · RHF+zod · Recharts
> Infra: container `react` atrás do Nginx gateway em `:8090`; código em `frontend/src/`.


## 1. Design Language

### 1.1 Inspiração e contexto

O SGI atende incorporadoras e construtoras — ambiente de obra, engenharia, drone e IA.
Referências que norteiam as decisões visuais:

| Referência | O que tomar |
|---|---|
| **Procore** | Sidebar com project-switcher, data-density alta, orange accent |
| **Autodesk Construction Cloud** | Navy/slate primário, ícones de linha fina, mapas |
| **DroneDeploy** | Fundo escuro para visualizações, teal para telemetria/IA |
| **BIM 360** | Hierarquia clara: empreendimento → obra → etapa |
| **Linear** (SaaS moderno) | Sidebar collapsível elegante, keyboard-nav, atalhos |

### 1.2 Paleta de cores

A cor primária da marca já existe na v01: **navy `#0A2A5B`**. O sistema app (sidebar/topbar)
usa uma variação escurecida desse mesmo tom, mantendo a identidade visual.

```
Marca / Navy    #0A2A5B   — logo, CTAs primários na landing, final CTA bg
App primário    #0f1f3d   — sidebar, topbar (navy escuro para contraste)
App superfície  #1a2f52   — sidebar itens ativos, hover
Fundo app       #f0f2f5   — fundo da área de conteúdo (exato da v01)
Fundo landing   #FFFFFF   — seções brancas da landing
Fundo alt       #F0F2F5   — seções acinzentadas (modules, security)
Accent          #f59e0b   — badges de status ativo, hover de item de menu (amber)
Drone/IA        #3b82f6   — features de drone, IA, mapeamento (blue)
Sucesso         #1AAB7B   — status concluído (exato da v01)
Perigo          #ef4444   — erros, exclusão
Texto           #495057   — body text (exato da v01)
Texto muted     #64748b   — labels, metadados
```

> **Fonte da verdade:** `--color-primary: #0A2A5B` do CSS da v01. O navy é a identidade da marca.
> Modo claro é o padrão; dark mode fica para fase futura.

### 1.3 Tipografia

A v01 usa Montserrat (títulos) + Roboto (corpo) — fontes estabelecidas na identidade do produto.

- **Títulos**: Montserrat (via Google Fonts) — `font-heading`
- **Corpo**: Roboto (via Google Fonts) — `font-body`
- **Escala**: Tailwind padrão (`text-sm` tabelas/labels, `text-base` body, `text-lg/xl` títulos de página, `text-2xl–3xl` hero)
- **Peso**: 400 body · 500 labels · 600 subtítulos · 700 títulos

### 1.4 Iconografia

- **Lucide React** (já na dep) — ícones de linha fina, 24px padrão
- Ícones de módulo específicos (Lucide):
  - Empreendimentos: `Building2`
  - Obras: `HardHat`
  - Clientes: `Users`
  - Fornecedores: `Truck`
  - ERP/Financeiro: `BarChart3`
  - RH: `UserCog`
  - CRM: `TrendingUp`
  - Drone: `Plane`
  - Diário/IA: `Brain`
  - Calendário: `CalendarDays`
  - Dashboard: `LayoutDashboard`

### 1.5 Princípios de UI

1. **Data-density controlada** — tabelas compactas com `text-sm`, espaçamento generoso apenas nos dashboards
2. **Hierarquia visual clara** — empreendimento > obra > etapa sempre visível no breadcrumb
3. **Entitlement invisível** — módulos não contratados simplesmente não aparecem, sem mensagem de bloqueio na sidebar
4. **Estado sempre legível** — badges coloridos para status de obra/etapa/financeiro, sem ícones ambíguos
5. **IA como feature diferencial** — análise de IA destacada visualmente (cor `blue-500`, ícone `Brain`)

---

## 2. Biblioteca de Componentes — shadcn/ui

### Por que shadcn/ui

- Componentes acessíveis (Radix UI primitives) sem biblioteca externa de runtime
- Código copiado direto em `src/components/ui/` — totalmente customizável
- Tailwind 4 nativo — sem conflito de versão
- Tem exatamente o que o sistema precisa: `Table`, `Dialog`, `Sheet`, `Tabs`, `Card`,
  `Badge`, `Form`, `Select`, `Popover`, `Toast`, `Skeleton`

### Componentes a instalar (via `npx shadcn@latest add`)

```
button      input       label       textarea    select
card        badge       table       tabs        separator
dialog      sheet       alert       toast       skeleton
avatar      dropdown-menu  tooltip  progress    calendar
```

### Componentes de domínio (escritos no projeto)

```
src/components/
├── ui/                          ← shadcn (gerado, não editar manualmente)
├── layout/
│   ├── AppShell.tsx             ← Sidebar + Topbar + <Outlet />
│   ├── Sidebar.tsx              ← colapsível, entitlement-aware
│   ├── Topbar.tsx               ← breadcrumb + tenant badge + user menu
│   └── PageHeader.tsx           ← título de página + ações primárias
├── data/
│   ├── DataTable.tsx            ← wrapper de <Table> com sorting/pagination
│   ├── EmptyState.tsx           ← ilustração + CTA quando lista vazia
│   └── LoadingSkeleton.tsx      ← skeleton de tabela/card
├── obra/
│   ├── StatusBadge.tsx          ← badge colorido por status_obra/etapa
│   ├── KpiCard.tsx              ← card de KPI (valor + label + delta)
│   ├── ObraCard.tsx             ← card clicável na grade de obras
│   ├── EtapaRow.tsx             ← linha da lista/gantt de etapas
│   ├── GanttBar.tsx             ← barra de gantt inline (CSS puro)
│   └── MapaObra.tsx             ← Leaflet isolado (lazy-load)
├── ia/
│   ├── AnaliseCard.tsx          ← card de resultado de análise IA
│   └── AnaliseStatus.tsx        ← badge de status de análise (pending/done/fail)
└── shared/
    ├── ConfirmDialog.tsx        ← Dialog de confirmação de exclusão
    ├── UploadZone.tsx           ← drag-and-drop de arquivo
    ├── CurrencyDisplay.tsx      ← formata BRL
    └── DateDisplay.tsx          ← formata data pt-BR
```

---

## 3. AppShell — Estrutura Global

### 3.1 Layout

```
┌─────────────────────────────────────────────────────────────────┐
│                         TOPBAR (h-14)                           │
│  [≡ SGI]  Breadcrumb: Empreendimentos / Residencial Alfa / Obras│
│                                    [🔔] [Tenant: Alfa Ltda ▼]  │
├────────────┬────────────────────────────────────────────────────┤
│  SIDEBAR   │                                                    │
│  (w-56 /   │              CONTENT AREA                         │
│   w-14     │          <Outlet /> da rota ativa                 │
│  colapsada)│                                                    │
│            │                                                    │
│  Base:     │                                                    │
│  🏠 Home   │                                                    │
│  🏗 Empreen│                                                    │
│  🦺 Obras  │                                                    │
│  👥 Clientes                                                   │
│  🚛 Fornec.│                                                    │
│  ─────────│                                                    │
│  Módulos:  │                                                    │
│  💰 ERP    │                                                    │
│  👤 RH     │                                                    │
│  📈 CRM    │                                                    │
│  ─────────│                                                    │
│  Extras:   │                                                    │
│  ✈ Drone   │                                                    │
│  🧠 IA/Di. │                                                    │
│  📅 Agenda │                                                    │
│            │                                                    │
└────────────┴────────────────────────────────────────────────────┘
```

### 3.2 Sidebar — comportamento

- **Expandida** (padrão desktop): w-56, ícone + texto
- **Colapsada** (toggle ou tela < lg): w-14, só ícone + tooltip
- Estado guardado em `localStorage` (`sgi_sidebar_collapsed`)
- Seções separadas por `<Separator>`: Base / Módulos pagos / Extras
- Itens de Módulos pagos visíveis apenas via `hasModule(code)`
- Itens sem rota ativa ficam ocultos, não desabilitados

### 3.3 Topbar

- Botão de colapso da sidebar (ícone `PanelLeft`)
- Breadcrumb automático baseado na rota ativa
- Badge do tenant atual (nome do tenant do JWT)
- Ícone de notificações `Bell` (placeholder — conteúdo futuro)
- Avatar + dropdown: `Perfil`, `Configurações`, `Sair`

---

## 4. Roteamento

Utiliza `createBrowserRouter` com rotas aninhadas.

```
/                       → LandingPage (pública)
/login                  → LoginPage (pública)
/app                    → AppShell (PrivateRoute — exige token válido)
  /app/dashboard        → DashboardPage
  /app/empreendimentos  → EmpreendimentosListPage
  /app/empreendimentos/:eId
                        → EmpreendimentoDetailPage
  /app/empreendimentos/:eId/obras
                        → ObrasListPage (filtrado por empreendimento)
  /app/empreendimentos/:eId/obras/:obraId
                        → ObraDetailPage
  /app/obras            → ObrasListPage (todas as obras do tenant)
  /app/clientes         → ClientesListPage
  /app/clientes/:id     → ClienteDetailPage
  /app/fornecedores     → FornecedoresListPage
  /app/erp                    → ErpDashboardPage ✅      (hasModule: erp_financeiro — lazy/Suspense, hub D.1.0)
  /app/erp/contas-a-pagar     → ContasAPagarPage ✅      (rota-irmã, D.1.1 07/06/2026 — workspace: lançar/editar/ver/baixa)
  /app/erp/contas-a-receber   → ContasAReceberPage ✅    (idem, espelhado p/ cliente/NF — D.1.1 07/06/2026)
  /app/erp/boletos            → BoletosListPage ✅       (rota-irmã, D.1.2 08/06/2026 — telas dedicadas, somente leitura)
  /app/erp/boletos/:id        → BoletoDetailPage ✅      (gateway + timeline de eventos do webhook Asaas)
  /app/rh               → RHPage               (hasModule: rh)
  /app/rh/funcionarios  → FuncionariosListPage (hasModule: rh)
  /app/crm              → CrmDashboardPage     (hasModule: crm)
  /app/crm/leads        → LeadsPage            (hasModule: crm)
  /app/diario           → DiarioObraPage       (base)
  /app/drone            → DroneWrapperPage     (hasModule: drone)
  /app/calendario       → CalendarioPage       (base)
  /app/admin/papeis     → PersonasPage ✅       (adminOnly — Papéis e Acessos, Fase 9.A)
  /app/admin/usuarios   → UsuariosPage ✅       (adminOnly — Usuários e seus papéis, Fase 9.A)
  *                     → NotFoundPage
```

> **Guard de entitlement:** `<ModuleRoute module="erp_financeiro">` wrapping a rota
> redireciona para `/app/dashboard` com toast "Módulo não disponível no seu plano"
> se `!hasModule(module)`.

> **Área de Administração (Fase 9.A):** [modules/admin/](../frontend/src/modules/admin/) — `PersonasPage`
> (CRUD de papéis/personas com picker de permissões por módulo + clonar) e `UsuariosPage` (atribui
> papéis a usuários). Itens de menu só aparecem para `is_tenant_admin` (`AuthContext.isTenantAdmin`).
> Falam com a IAM pelo cliente `iamAdminClient` (baseURL `/iam`, roteado pelo gateway → IAM). Detalhe
> do modelo em [arquitetura/rbac-abac.md §9.1](arquitetura/rbac-abac.md).

---

## 5. Mapa de Páginas

### 5.1 LandingPage (`/`)

A porta de entrada do produto. A **estrutura e o copy já existem na v01** (`01sistema_gestao_integrada`)
e devem ser portados — não reinventados. Adaptar apenas para Tailwind + shadcn + nova paleta navy.

**Asset a reaproveitar:** `01sistema_gestao_integrada/frontend/src/components/HomeSections/dashboard-mockup.png`
→ copiar para `frontend/public/dashboard-mockup.png`.

#### Estrutura das seções (v01 → v02)

```
┌──────────────────────────────────────────────────────────────────┐
│  HEADER — fixo, bg branco, sombra                                │
│  [SGI Logo]    Funcionalidades  Módulos  Segurança   [Acessar →] │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  HERO — bg branco, duas colunas (desktop)                        │
│                                                                  │
│  TEXTO (esquerda)              │  IMAGEM (direita)               │
│  h1: "O Fim do Improviso       │  <dashboard-mockup.png>         │
│  na Sua Obra."                 │  rounded + sombra               │
│  "Inteligência, Gestão,        │                                 │
│  Controle e Lucro em um        │                                 │
│  só lugar."                    │                                 │
│                                │                                 │
│  p: "Nossa plataforma          │                                 │
│  integra todos os seus         │                                 │
│  processos, do canteiro de     │                                 │
│  obras ao financeiro..."       │                                 │
│                                │                                 │
│  [Solicitar Demonstração]      │                                 │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  MÓDULOS — bg #F0F2F5                                            │
│  h2: "Uma plataforma completa para cada desafio da sua           │
│        construtora"                                              │
│                                                                  │
│  Grid 3 colunas (desktop), 2 (tablet), 1 (mobile)               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │ 🔧 Gestão de │ │ 💰 Gestão    │ │ 📈 CRM de    │            │
│  │    Obras     │ │  Financeira  │ │    Vendas    │            │
│  │ Acompanhe    │ │ Controle     │ │ Gerencie     │            │
│  │ cronograma,  │ │ contas a     │ │ leads e      │            │
│  │ diário e     │ │ pagar,       │ │ clientes do  │            │
│  │ recursos     │ │ receber e    │ │ primeiro     │            │
│  │ em tempo     │ │ fluxo de     │ │ contato ao   │            │
│  │ real.        │ │ caixa.       │ │ contrato.    │            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │ 💬 Diário   │ │ 📂 Gestão de │ │ 🧠 Relatórios│            │
│  │  por        │ │  Documentos  │ │    com IA    │            │
│  │  WhatsApp   │ │              │ │              │            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  SOCIAL PROOF — bg branco                                        │
│  h2: "Construindo Relações de Confiança"                         │
│                                                                  │
│  Depoimento:                                                     │
│  "O sistema transformou nossa gestão. A visão integrada do       │
│  financeiro com o progresso das obras nos deu um poder de        │
│  decisão que não tínhamos antes."                                │
│  — João da Silva, Diretor na Construtora Exemplo                 │
│                                                                  │
│  Métricas (3 colunas):                                           │
│  [+30h economizadas/mês] [15% ↓ desperdício] [100% nos prazos]  │
│                                                                  │
│  Logos de clientes (placeholders → preencher com reais)          │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  SEGURANÇA — bg #F0F2F5, duas colunas (desktop)                  │
│                                                                  │
│  TEXTO                         │  BADGES                        │
│  h3: "Segurança em Nível       │  🛡 Criptografia AES-256       │
│        Empresarial"            │  🔒 OWASP Top 10 Mitigado      │
│  "Seus dados são seu maior     │  ☁ Backups Diários             │
│  ativo..."                     │  🛡 Conformidade LGPD          │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  FINAL CTA — bg #0A2A5B (navy), texto branco                     │
│  h2: "Pronto para revolucionar a gestão da sua construtora?"     │
│  p: "Veja na prática como nossa plataforma pode aumentar         │
│     sua eficiência e rentabilidade."                             │
│  [Solicitar Demonstração Gratuita]  ← botão branco/claro        │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  FOOTER — bg #495057, texto #aeb9c7                              │
│  © SGI 2026   Links: Política de Privacidade · Termos · Contato │
└──────────────────────────────────────────────────────────────────┘
```

#### Notas de implementação

- Header fixo (`sticky top-0 z-50`) com `backdrop-blur` e sombra sutil
- Hero: `pt-[140px]` para compensar o header fixo
- Módulos usam **Lucide React** no lugar do Phosphor Icons (v01 usava Phosphor — não instalar)
- Ícones dos 6 cards: `HardHat`, `BarChart3`, `TrendingUp`, `MessageCircle`, `FolderOpen`, `Brain`
- Métricas da SocialProof animadas com contagem (opcional — Fase B.2)
- FinalCTA ancora para `#solicitar-demo` (form de contato ou link WhatsApp)
- Responsivo: mobile-first, breakpoints `md:` (768px) e `lg:` (1024px)

### 5.2 LoginPage (`/login`) ✅ Construída

Layout **dois painéis** (desktop): painel navy à esquerda com feature bullets; painel branco à
direita com o formulário. Mobile: só o formulário com logo no topo.

```
┌──────────────────────────┬──────────────────────────────────────┐
│  PAINEL ESQUERDO (navy)  │  PAINEL DIREITO (branco)             │
│                          │                                      │
│  [SGI]  Gestão Integrada │  "Entrar na sua conta"               │
│                          │  "Acesse a plataforma com suas       │
│  "A plataforma completa  │   credenciais."                      │
│  para sua construtora."  │                                      │
│                          │  [Erro] ← aparece se login falhar    │
│  ✓ Obras e empreend.     │                                      │
│  ✓ Financeiro, RH e CRM  │  Usuário ________________           │
│  ✓ Análise de IA         │  Senha  ______________ 👁            │
│  ✓ LGPD e multi-tenant   │                                      │
│                          │  [⟳ Entrando… / → Entrar]           │
│  © 2026 SGI              │                                      │
│                          │  Esqueci minha senha                 │
│                          │  ← Voltar para o início              │
└──────────────────────────┴──────────────────────────────────────┘
```

- `POST /auth/login/` via `AuthContext.login()` → token em `localStorage` (cookie `HttpOnly` na Fase 10.6)
- Spinner e botão desabilitado durante submit; alerta vermelho inline em caso de erro
- Redireciona para `/app/dashboard` ou `location.state.from`

### 5.3 AppHomePage / Hub de módulos (`/app/dashboard`) ✅ Construída

Tela inicial pós-login. Não é um dashboard de KPIs (ainda) — é um **hub de módulos** que exibe
toda a plataforma com estado claro de acesso: base, contratado, adicional ou em desenvolvimento.
Os botões ficam desabilitados até cada módulo ter sua página implementada.

```
┌──────────────────────────────────────────────────────────────┐
│  Bom dia, demo!                    Quarta, 4 de junho de 2026│
│  Plano base                                                  │
├──────────────────────────────────────────────────────────────┤
│  MÓDULOS BASE  [Inclusos]                                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │🏗 Obras  │ │🏢 Empreen│ │👥 Client.│ │🚛 Fornec.│       │
│  │[Acessar▷]│ │[Acessar▷]│ │[Acessar▷]│ │[Acessar▷]│       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐                                  │
│  │🧠 Diário │ │📅 Agenda │                                  │
│  │[Acessar▷]│ │[Acessar▷]│                                  │
│  └──────────┘ └──────────┘                                  │
├──────────────────────────────────────────────────────────────┤
│  MÓDULOS ADICIONAIS  [À la carte]                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │💰 ERP    │ │👤 RH     │ │📈 CRM    │ │✈ Drone   │       │
│  │[Contratar│ │[Contratar│ │[Contratar│ │[Contratar│       │
│  │ módulo]  │ │ módulo]  │ │ módulo]  │ │ módulo]  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
├──────────────────────────────────────────────────────────────┤
│  EM DESENVOLVIMENTO                                          │
│  [SCM] [DMS] [PDCA] [APS] [SIL] [Maps]  ← mini cards       │
└──────────────────────────────────────────────────────────────┘
```

- Cards de módulos pagos mostram "Contratar módulo" se `!hasModule(code)`, "Acessar" se contratado
- Todos os botões `disabled` enquanto as páginas dos módulos não existem (`implemented: false`)
- Para ativar um módulo: setar `implemented: true` no catálogo + adicionar rota no `App.tsx`

**Substituição futura:** quando o dashboard de KPIs (Fase C.1) for construído, esta página
passa a ser o hub de módulos acessível por `/app/modulos` e o dashboard de KPIs ocupa `/app/dashboard`.

### 5.4 EmpreendimentosListPage

- Tabela com colunas: Nome, CNPJ, Status, Orçamento, Ações
- Filtro por status (`<Select>`)
- Botão "+ Novo Empreendimento" abre `<Sheet>` lateral com form
- Click na linha → `/app/empreendimentos/:eId`

### 5.5 EmpreendimentoDetailPage

```
Header: nome + status badge + [Editar]
Tabs: Visão Geral | Obras | Financeiro (hasModule) | Documentos | Custos
─ Visão Geral: dados cadastrais + mapa da localização
─ Obras: ObrasListPage filtrada por empreendimentoId
─ Financeiro: contas bancárias, custos, faturas vinculadas
─ Documentos: lista + upload
─ Custos: CustoEmpreendimento com fornecedores
```

### 5.6 ObrasListPage

- Seletor de empreendimento no topo (select ou breadcrumb)
- Tabela: ID, Nome, Endereço, Status badge, Início/Fim previsto
- Click → `/app/empreendimentos/:eId/obras/:obraId`

### 5.7 ObraDetailPage — página mais complexa

```
Breadcrumb: Empreendimentos / Residencial Alfa / Obras / Bloco A
Header: nome + status badge + [Editar]
KPI row: [Progresso geral] [Etapas concluídas/total] [Dias restantes] [Orçamento]

Layout duas colunas (lg:grid-cols-[320px_1fr]):

COLUNA ESQUERDA (320px fixo):
  ┌─────────────────────┐
  │ Localização         │
  │ MapaObra (Leaflet)  │
  ├─────────────────────┤
  │ Documentos          │
  │ lista + [Upload]    │
  ├─────────────────────┤
  │ Projeto 3D/Drone    │
  │ BluePrint / iframe  │
  └─────────────────────┘

COLUNA DIREITA (Tabs):
  [Visão Geral] [Cronograma] [Diário] [Financeiro] [Equipe]

  Visão Geral:
    datas previstas/reais, orçamento, descrição, responsáveis

  Cronograma:
    lista de EtapaObra com GanttBar inline por etapa
    status badge + % conclusão + datas + responsável

  Diário (ObraTimeline):
    linha do tempo de DiarioObra
    cada entrada: data + descrição + fotos com AnaliseStatus IA

  Financeiro (hasModule erp_financeiro):
    ContasPagar/Receber da obra
    gráfico de execução financeira vs orçado

  Equipe:
    M2M responsaveis_tecnicos + equipe (rh.Funcionario)
```

### 5.8 ClientesListPage / ClienteDetailPage

- Lista: Nome, CPF/CNPJ, Email, Telefone
- Detalhe (Sheet ou página): dados + contratos + cobranças + histórico CRM

### 5.9 FornecedoresListPage

- Lista: Nome, CNPJ, produtos/serviços, obras relacionadas

### 5.10 ERP (hasModule: erp_financeiro) ✅ Fundação UI + Contas a pagar/receber + Boletos 08/06/2026

> Fundação (D.1.0) e Contas a pagar/receber (D.1.1) construídas — modelo de frontend específico em
> [docs/modulos/moduloerp.md §5](modulos/moduloerp.md#5-frontend-do-erp--navegação-e-arquitetura)
> (estende, não substitui, o modelo geral deste documento: TanStack Query/Table, Recharts,
> RHF+zod, `MoneyInput`/centavos inteiros, code-splitting).

- **`ErpDashboardPage`** (`/app/erp`, hub) ✅ — `KpiCard` (a receber/a pagar/saldo projetado/fluxo do
  mês) + `FluxoCaixaChart` (receitas x despesas mensais) + `AgingChart` (aging a receber/a pagar),
  todos sobre `useErpDashboard()` → `GET /api/erp/dashboard/` (cacheado, React Query); cards
  `WorkspaceLinkCard` → `/app/erp/contas-a-{pagar,receber}`. No header, `DivergenciasErpButton` —
  botão-alerta (colorido + contagem quando há divergências banco × Asaas) que abre modal com o
  `DivergenciasAsaasPanel`; visível só com as permissões de usuário `erp.cobranca.view` + `cadastro.cliente.view`
  (gate LGPD+escopo — `hasModule` não basta, é do tenant; reforçado no backend), documento mascarado sem
  `cadastro.cliente_doc.view`. Sem `erp.relatorio.view`, os KPIs/gráficos degradam para um aviso amigável
  (403 velado, F4)
- **`ContasAPagarPage`/`ContasAReceberPage`** (`/app/erp/contas-a-{pagar,receber}`, rotas-irmãs) ✅ —
  arquétipo "Workspace de lista financeira" ([moduloerp.md §5.5](modulos/moduloerp.md#55-arquétipos-de-página-layouts-reutilizáveis)):
  `FilterBar`+`FinanceDataTable` (paginação/ordenação server-side) + `Sheet` lateral com 4 modos
  (`create`/`edit`/`view`/`baixa`) — lançar conta com `RateioField` (centro de custo), ver detalhe
  (rateios, boletos, ações), editar, dar baixa parcial ou total. Breadcrumb de volta ao hub.
- **`Sheet`** (slide-over) ✅ — **1º uso no projeto**; `open/onClose/title/description/footer/width`
- **Formulários RHF+zod** ✅ — **1ª adoção de `react-hook-form`+`zod` no projeto** (ver
  [moduloerp.md §5.3](modulos/moduloerp.md#53-stack-adicional-estende-o-do-projeto)):
  `ContaPagarForm`/`ContaReceberForm` (`useFieldArray` para `RateioField`, `setError`+
  `parseApiErrors`/`FormErrorBanner` para erros de API) e `BaixaForm` (compartilhado, espelha
  `dar_baixa()` do backend — juros/multa/desconto via `MoneyInput`+`Controller`)
- **Camada de dados** ✅ — `erpKeys` (fábrica de chaves) → `endpoints/{contasAPagar,contasAReceber,
  centrosCusto,lotesRemessa,dashboard}` → `hooks/{useContasAPagar,useContasAReceber,useCentrosCusto,
  useLotesRemessa,useEntityOptions,useErpDashboard}`; mutações (criar/editar/baixa) invalidam
  `erpKeys.contasA{Pagar,Receber}` + `erpKeys.dashboard.all` → hub e listas atualizam sozinhos
- **Componentes compartilhados** ✅ — `FilterBar` · `FinanceDataTable` (TanStack Table headless,
  server-side sobre `ErpPageNumberPagination`) · `MoneyInput`/`MoneyDisplay` (centavos inteiros) ·
  `KpiCard` · `StatusContaBadge` (`STATUS_CONTA_CONFIG`: ABERTO/PARCIAL/QUITADO/CANCELADO)
- **Code-splitting** ✅ — `modules/erp/routes.tsx` com `lazy`/`Suspense`, rotas-irmãs (mesmo padrão
  de `empreendimentos`/`empreendimentos/:id`, não aninhadas) — chunks `ErpDashboardPage`/
  `ContasAPagarPage`/`ContasAReceberPage`/`BaixaForm` separados do bundle principal
- **Validado (golden path, 07/06/2026)** ✅ — CRUD completo, baixa parcial→total, rateio por centro
  de custo, lote de remessa e aging do dashboard testados via API/gateway; dados de teste limpos.
  **Achado:** `dar_baixa()` aceita baixa repetida em título já `QUITADO` — ver
  [moduloerp.md "Dívidas técnicas"](modulos/moduloerp.md#dívidas-técnicas-conhecidas) (decidir regra
  antes de D.1.2/webhook Asaas)
- **`BoletosListPage`/`BoletoDetailPage`** (`/app/erp/boletos`, `/app/erp/boletos/:id`, rotas-irmãs)
  ✅ D.1.2 08/06/2026 — **telas dedicadas** (decisão do usuário, não Sheet/drill-down): a lista é um
  workspace só-leitura (`FilterBar`+`FinanceDataTable`, filtra por status/vencimento — o boleto nasce
  do gateway Asaas, não de lançamento manual); o detalhe mostra os dados do gateway (linha digitável,
  link do PDF) + **timeline de eventos do webhook** (`useEventosWebhookAsaas` →
  `GET /api/erp/cobrancas/eventos/?boleto={id}`), provando evento a evento como a baixa automática
  aconteceu. `StatusBoletoBadge`/`statusBoleto.ts` espelham `StatusContaBadge`. Botão
  **"Gerar cobrança (Asaas)"** no Sheet de detalhe de `ContaReceber` (`useGerarCobrancaContaAReceber`)
  enfileira a emissão real no Asaas sandbox. Detalhe completo:
  [funcoescobrancas.md "UI dedicada"](modulos/funcoescobrancas.md#ui-dedicada--telas-de-boletos-entregue-08062026-)
  e [moduloerp.md §6](modulos/moduloerp.md#6-boletos--cobrança--integração-asaas).
- **Próximas telas (❌ ainda não construídas)**: notas fiscais (abas emitidas/recebidas/canceladas,
  D.1.3), financeiro por obra (DRE, D.1.4) — ver roadmap em
  [docs/modulos/moduloerp.md §13](modulos/moduloerp.md#13-roadmap-em-sub-fases-fase-d1x)

### 5.11 RH (hasModule: rh) ✅ 06/06/2026

Módulo completo. Rotas: `/app/rh` · `/app/rh/cargos` · `/app/rh/:id`.

**FuncionariosListPage** (`/app/rh`):
- Tabela: Nome/email, CPF, Cargo, Status badge (ativo/férias/licença/inativo/desligado), Admissão, Salário
- Filtros client-side: busca (nome+CPF) + select de status
- Botão "Cargos" → CargosPage; botão "+ Novo Funcionário" → FuncionarioForm (Sheet)
- `useFuncionarios()` + `useCargos()` com `cargoMap` para join client-side

**CargosPage** (`/app/rh/cargos`):
- Tabela: Nome do Cargo, Departamento, Descrição (truncada)
- CRUD completo (criar, editar modal, excluir com confirmação)
- Back → FuncionariosListPage

**FuncionarioDetailPage** (`/app/rh/:id`):
- 4 abas:
  - **Dados Pessoais** — 4 cards: Identificação, Contato & Endereço, Contrato, Documentos Trabalhistas
  - **Documentos (N)** — upload de arquivo (tipo + nome + arquivo) + listagem com link externo + exclusão
  - **Saúde** — `DadoMedicoFuncionario` (1-to-1); mostra cadeado + mensagem se `rh_medico` negado (403)
  - **Financeiro** — 3 seções: Dados Bancários (lista+CRUD), Pagamentos (lista+CRUD), Folhas de Pagamento (lista+CRUD); mostra cadeado se `rh_financeiro` negado (403)
- `Promise.allSettled` para 6 fetches paralelos; 403 não quebra a página
- Editar funcionário (Sheet FuncionarioForm), excluir com modal de confirmação

### 5.12 CRM (hasModule: crm)

- **CrmDashboardPage**: funil de leads (Kanban ou funil visual)
- **LeadsPage**: tabela de leads + pipeline de conversão

### 5.13 DiarioObraPage (`/app/diario`)

- Seletor de obra no topo
- Timeline de entradas do diário
- Cada entrada: data, condições climáticas, descrição, fotos
- Fotos: badge de análise IA (pendente / concluída / falha)
- Click na foto → modal com `AnaliseCard` (resultado da IA)
- FAB "+" para novo diário (com form inline ou Sheet)

### 5.14 DroneWrapperPage (`/app/drone`) — hasModule: drone

- Topbar da rota injeta `empreendimento_id` e `obra_id` da URL
- `<iframe src="/drone/?token=JWT&empreendimento_id=X&obra_id=Y">`
- Spinner enquanto carrega
- Badge "Módulo Drone" no Topbar

### 5.15 CalendarioPage (`/app/calendario`)

- Grade mensal de `CalendarEvent`
- Eventos coloridos por tipo (obra, reunião, prazo financeiro)

### 5.16 Plano e quotas (D24) — 📋 planejado

O backend já **trava** a criação acima da quota do plano (402) e serve o medidor;
falta a camada visual. O desenho abaixo é o contrato do frontend com o que já existe.

**Princípio que organiza tudo:** o 402 tem de ser a **confirmação de algo já visível**, nunca a
primeira notícia. Descobrir o limite depois de preencher um cadastro inteiro faz o produto parecer
quebrado; descobrir antes faz o plano parecer pequeno — que é a leitura correta e a que vende
upgrade. Daí a ordem de prioridade: **medidor → botão desabilitado → diálogo de upgrade**. Se só uma
coisa for construída, que seja o medidor.

#### 5.16.1 O contrato vindo do backend

`GET /api/plano/` devolve plano vigente, medidores, próximo degrau e o catálogo inteiro:

```jsonc
{
  "plano": { "slug": "free", "nome": "Free", "preco_mensal": 0, "publico": "..." },
  "quotas": [
    { "recurso": "obras", "rotulo": "obras", "limite": 2, "uso": 1,
      "ilimitado": false, "restante": 1, "excedido": false, "fonte": "backend" },
    { "recurso": "seats", "rotulo": "seats", "limite": 1, "uso": null,
      "ilimitado": false, "restante": null, "excedido": false, "fonte": "iam" }
  ],
  "proximo_plano": { "slug": "essencial", "nome": "Essencial", "preco_mensal": 149 },
  "catalogo": [ { "slug": "...", "nome": "...", "preco_mensal": 149, "quotas": { ... } } ]
}
```

Três regras que não devem ser reinterpretadas na tela:

- **Preço nunca é escrito no frontend.** Sai de `catalogo`, que vem de `payment/planos.py` — a mesma
  tabela que a IAM usa para emitir os tetos. Um preço em código de frontend é um preço que vai
  divergir da cobrança, e quem descobre a divergência é o cliente, na fatura.
- **`limite: 0` ≠ `ilimitado`.** `0` significa "não incluído neste plano" (o `free` usa isso) e
  `ilimitado: true` significa sem teto. Tratar os dois como "sem limite" mostraria como disponível
  justamente o que o plano de entrada não vende.
- **`uso: null` não é zero.** É o caso de `seats`, cuja `fonte` é `"iam"`: o backend não conta
  usuários (o `Usuario` de lá é espelho JIT). A barra de seats se abastece de `GET /iam/usuarios/`,
  ou mostra só o limite. Desenhar `null` como `0` diria ao cliente que ele tem todos os seats livres.

#### 5.16.2 Tratamento global do 402

O 402 chega de **qualquer** criação — quatro recursos no backend e o cadastro de usuário na IAM — e
com **o mesmo corpo** nos dois serviços:

```jsonc
{ "detail": "…texto pronto para exibir…", "code": "quota_excedida",
  "quota": "obras", "limite": 2, "uso": 2, "plano": "free" }
```

Por isso o tratamento é **um interceptor de resposta**, irmão do que já trata 401 em
[`api/session.ts`](../frontend/src/api/session.ts) — e não um `catch` por formulário. Tratar por
formulário significa repetir a lógica em cinco telas e esquecer na sexta, que é exatamente a tela
nova que alguém vai escrever depois.

O interceptor reconhece `code === "quota_excedida"`, abre o `UpgradeDialog` e **não** deixa o erro
virar toast genérico. Ler `code`, nunca a string de `detail`: o texto muda, o código é contrato (é
por isso que o backend devolve os dois).

#### 5.16.3 Componentes

| Componente | Papel |
|---|---|
| `usePlano()` | Hook sobre `GET /api/plano/`. Invalidado após criar/excluir qualquer recurso contado — senão o medidor mente até o F5. |
| `QuotaMeter` | Barra uso/limite com rótulo. Estados: normal · atenção (≥80%) · esgotado. Trata `ilimitado` e `uso: null` sem inventar número. |
| `QuotaBanner` | Aviso discreto no topo da listagem quando o recurso daquela tela está ≥80%. É o que transforma o 402 em confirmação. |
| `UpgradeDialog` | Aberto pelo interceptor. Diz qual limite bateu, o uso atual, o plano vigente e o próximo com preço. Duas saídas: liberar espaço (link para a listagem) ou subir de plano. |
| `NovoButton` desabilitado | Nas listagens dos 4 recursos contados: com `excedido`, o botão fica inativo com tooltip explicando — padrão de botão inativo já definido em [frontend-convencoes.md](frontend-convencoes.md). Evita a pior sequência possível, que é preencher tudo e perder no submit. |

#### 5.16.4 Página `/app/admin/plano`

Ao lado de `/app/admin/papeis` e `/app/admin/usuarios`, sob o mesmo guard de `is_tenant_admin`:

- **Plano vigente** — nome, preço, público-alvo.
- **Medidores** — um `QuotaMeter` por quota, os esgotados primeiro.
- **Comparativo** — tabela do `catalogo`, plano atual destacado, quotas lado a lado.
- **CTA de upgrade.**

#### 5.16.5 O CTA enquanto não há checkout

O autoserviço (landing → checkout → Asaas → provisionamento) é o **item 3** do faseamento do
[monetizacao.md §10](arquitetura/monetizacao.md) e **não existe**. Até existir, o CTA abre um
formulário de contato ou um `mailto` — e deve dizer isso com todas as letras ("solicitar upgrade",
não "assinar agora"). Um botão que promete pagamento imediato e entrega um e-mail queima a conversão
uma vez por cliente, e é a impressão que fica.

Quando o checkout entrar, muda **só o destino do botão** — todo o resto desta seção continua valendo.

---

## 6. Auth & Entitlement

### 6.1 AuthContext (mantido e expandido)

```ts
interface AuthContextType {
  isAuthenticated: boolean
  user: User | null
  tenant: string | null        // ← novo: nome do tenant (para o Topbar)
  modules: string[]
  roles: string[]              // ← novo: claims de papéis do JWT
  loading: boolean
  token: string | null         // ← exposto explicitamente (corrige bug atual)
  login(username, password): Promise<void>
  logout(): void
  hasModule(code: string): boolean
  hasRole(role: string): boolean  // ← novo
}
```

- `GET /auth/me/` retorna `{ id, username, email, tenant, modules, roles }`
- `token` exposto diretamente (elimina o acesso via `localStorage` nos hooks)
- A migração para cookie `HttpOnly` (Fase 10.6) acontece sem mudar os consumers

### 6.2 Guards de rota

```tsx
// PrivateRoute — autentica
<Route element={<PrivateRoute />}>
  <Route path="/app" element={<AppShell />}>
    ...
  </Route>
</Route>

// ModuleRoute — entitlement
<ModuleRoute module="erp_financeiro">
  <Route path="erp" element={<ERPDashboardPage />} />
</ModuleRoute>
```

### 6.3 Sidebar entitlement-aware

```tsx
const navItems = [
  { label: 'Dashboard',      icon: LayoutDashboard, to: '/app/dashboard' },
  { label: 'Empreendimentos',icon: Building2,        to: '/app/empreendimentos' },
  { label: 'Obras',          icon: HardHat,          to: '/app/obras' },
  { label: 'Clientes',       icon: Users,            to: '/app/clientes' },
  { label: 'Fornecedores',   icon: Truck,            to: '/app/fornecedores' },
  // módulos pagos — só exibe se hasModule()
  { label: 'ERP',            icon: BarChart3,        to: '/app/erp',   module: 'erp_financeiro' },
  { label: 'RH',             icon: UserCog,          to: '/app/rh',    module: 'rh' },
  { label: 'CRM',            icon: TrendingUp,       to: '/app/crm',   module: 'crm' },
  // extras
  { label: 'Diário / IA',   icon: Brain,            to: '/app/diario' },
  { label: 'Drone',          icon: Plane,            to: '/app/drone', module: 'drone' },
  { label: 'Calendário',     icon: CalendarDays,     to: '/app/calendario' },
]
```

---

## 7. Camada de Dados

### 7.1 apiClient (mantido)

```ts
// src/api/apiClient.ts
const apiClient = axios.create({ baseURL: '/api' })
apiClient.interceptors.request.use(config => {
  const token = localStorage.getItem('token') // → cookie HttpOnly na Fase 10.6
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
```

### 7.2 Padrão de hooks por módulo

Cada módulo tem seus próprios hooks em `src/modules/<modulo>/hooks/`:

```ts
// src/modules/obras/hooks/useObras.ts
export function useObras(empreendimentoId?: number) { ... }

// src/modules/obras/hooks/useObra.ts
export function useObra(obraId: number) { ... }

// src/modules/obras/hooks/useEtapas.ts
export function useEtapas(obraId: number) { ... }

// src/modules/obras/hooks/useDocumentos.ts
export function useDocumentos(obraId: number) { ... }
```

Padrão interno de cada hook:

```ts
function useObra(obraId: number) {
  const { token } = useAuth()
  const [data, setData] = useState<Obra | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!obraId) return
    setLoading(true)
    apiClient.get(`/obras/${obraId}/`)
      .then(r => setData(r.data))
      .catch(() => setError('Erro ao carregar obra'))
      .finally(() => setLoading(false))
  }, [obraId, token])

  return { data, loading, error }
}
```

### 7.3 Endpoints consumidos por módulo

| Módulo | Endpoints |
|---|---|
| Auth | `POST /auth/login` · `GET /auth/me` · `POST /auth/logout` |
| Empreendimentos | `GET/POST /api/empreendimentos/` · `GET/PUT/DELETE /api/empreendimentos/:id/` |
| Obras | `GET/POST /api/obras/` · `GET/PUT /api/obras/:id/` |
| Etapas | `GET/POST /api/etapas-obras/` · `PUT /api/etapas-obras/:id/` |
| Documentos obra | `GET/POST /api/documentos-obras/` (multipart) |
| Clientes | `GET/POST /api/clientes/` · `GET/PUT /api/clientes/:id/` |
| Fornecedores | `GET /api/fornecedores/` |
| ERP | `GET /api/erp/dashboard/` · `GET/POST /api/erp/contas-a-pagar/` (+ `dar-baixa`, `gerar-lote-remessa`) · `GET/POST /api/erp/contas-a-receber/` (+ `dar-baixa`, `emitir-nfse`/`emitir-nfe`) · `GET/POST /api/erp/centros-custo/` · `GET /api/erp/lotes-remessa/` · etc. |
| RH | `GET /api/funcionarios/` |
| CRM | `GET /api/crm/leads/` · `GET /api/crm/oportunidades/` |
| Diário | `GET/POST /api/diario/diarios/` · `/api/diario/entradas/` · `/api/diario/documentos/` |
| IA | `GET /api/ia/analises/` · `GET /api/ia/analises/:id/` |
| Calendário | `GET/POST /api/calendar/events/` |
| Plano/quotas | `GET /api/plano/` (plano vigente + medidores + catálogo). O **402** `quota_excedida` pode voltar de qualquer criação de empreendimento/obra/cliente/fornecedor e de `POST /iam/usuarios/` — ver §5.16 |

---

## 8. Estrutura de arquivos (`src/`)

Legenda: ✅ existe · 📋 planejado

```
src/
├── main.tsx                          ✅ entry; wraps <AuthProvider>
├── App.tsx                           ✅ BrowserRouter + Routes (/ /login /app/*)
├── api/
│   └── apiClient.ts                  ✅ axios instance; interceptor Bearer
├── contexts/
│   └── AuthContext.tsx               ✅ auth, modules, loading, login, logout, hasModule
├── hooks/
│   ├── useAuth.ts                    ✅ consumer do AuthContext
│   └── useFileUpload.ts              ✅ upload c/ progresso + download autenticado + config da API
├── components/
│   ├── PrivateRoute.tsx              ✅ guard de autenticação
│   ├── ModuleRoute.tsx               ✅ guard de entitlement de módulo (hasModule) — tela amigável se não contratado
│   ├── AccessNotice.tsx              ✅ tela reutilizável de acesso negado (módulo/permissão)
│   ├── layout/
│   │   ├── LandingHeader.tsx         ✅ header fixo da landing (logo, nav, CTA)
│   │   ├── LandingFooter.tsx         ✅ footer da landing
│   │   ├── AppShell.tsx              ✅ sidebar + topbar + <Outlet />
│   │   ├── AppSidebar.tsx            ✅ collapsível, entitlement-aware, lock em não-implementados
│   │   └── AppTopbar.tsx             ✅ tenant badge, user dropdown, logout
│   ├── HomeSections/                 ✅ seções da landing page
│   │   ├── HeroSection.tsx
│   │   ├── ModulesSection.tsx
│   │   ├── SocialProofSection.tsx
│   │   ├── SecuritySection.tsx
│   │   └── FinalCTASection.tsx
│   ├── data/                         📋 DataTable, EmptyState, LoadingSkeleton
│   ├── obra/                         📋 StatusBadge, KpiCard, ObraCard, GanttBar, MapaObra
│   ├── ia/                           📋 AnaliseCard, AnaliseStatus
│   └── shared/                       📋 UploadZone, CurrencyDisplay
├── pages/
│   ├── LandingPage.tsx               ✅ / (pública) — 5 seções
│   ├── LoginPage.tsx                 ✅ /login — dois painéis navy+branco
│   └── app/
│       └── AppHomePage.tsx           ✅ /app/dashboard — hub de módulos com entitlement
├── modules/
│   ├── empreendimentos/              ✅ (04/06/2026)
│   │   ├── hooks/
│   │   │   ├── useEmpreendimentos.ts ← lista com filtro client-side (busca + status)
│   │   │   └── useEmpreendimento.ts  ← detalhe + contas + custos; create/update/delete
│   │   ├── components/
│   │   │   ├── EmpreendimentoStatusBadge.tsx
│   │   │   └── EmpreendimentoForm.tsx ← sheet c/ CNPJ (utils/masks), fone e moeda; fix close drag
│   │   └── pages/
│   │       ├── EmpreendimentosListPage.tsx  ← /app/empreendimentos
│   │       └── EmpreendimentoDetailPage.tsx ← /app/empreendimentos/:id (4 abas + modal excluir)
│   ├── obras/                        ✅ (04/06/2026)
│   │   ├── hooks/
│   │   │   ├── useObras.ts           ← lista; filtro servidor (empreendimento_id) + cliente (search, status)
│   │   │   └── useObra.ts            ← detalhe; fetch paralelo etapas+docs; CRUD obra/etapa
│   │   ├── components/
│   │   │   ├── ObraStatusBadge.tsx
│   │   │   ├── ObraForm.tsx          ← sheet; select empreendimento; máscara moeda
│   │   │   └── EtapaForm.tsx         ← sheet; slider % conclusão; ordem; máscara moeda
│   │   └── pages/
│   │       ├── ObrasListPage.tsx     ← /app/obras (3 filtros: busca, status, empreendimento)
│   │       └── ObraDetailPage.tsx    ← /app/obras/:id (KPIs + barra progresso + 3 abas)
│   ├── clientes/                     ✅ 04/06/2026
│   ├── fornecedores/                 ✅ 05/06/2026
│   ├── erp/                          ✅ Fundação UI (D.1.0) + Contas a pagar/receber (D.1.1) 07/06/2026 — modelo próprio, ver moduloerp.md §5
│   │   ├── routes.tsx                ← sub-rotas-irmãs lazy/Suspense (code-splitting; não aninhadas)
│   │   ├── types.ts                  ← payload da API (strings) + tipos normalizados p/ UI
│   │   ├── api/
│   │   │   ├── erpClient.ts · queryKeys.ts (fábrica `erpKeys`)
│   │   │   └── endpoints/            ← contasAPagar, contasAReceber, centrosCusto, lotesRemessa, dashboard
│   │   ├── hooks/                    ← useContasAPagar/useContasAReceber (query+mutations+useDarBaixa),
│   │   │                                useCentrosCusto, useLotesRemessa, useEntityOptions, useErpDashboard
│   │   ├── components/
│   │   │   ├── shared/               ← FilterBar, FinanceDataTable, Sheet (slide-over, 1º uso),
│   │   │   │                            MoneyInput, MoneyDisplay, KpiCard, StatusContaBadge
│   │   │   ├── forms/                ← ContaPagarForm/ContaReceberForm/BaixaForm/RateioField/FormField
│   │   │   │                            (RHF + zod, 1º uso no projeto) · schemas.ts · formStyles.ts
│   │   │   └── charts/               ← FluxoCaixaChart, AgingChart (Recharts)
│   │   └── pages/
│   │       ├── ErpDashboardPage.tsx  ← /app/erp (hub: KPIs + gráficos + cards p/ workspaces)
│   │       ├── ContasAPagarPage.tsx  ← /app/erp/contas-a-pagar   (workspace: listão + Sheet)
│   │       └── ContasAReceberPage.tsx← /app/erp/contas-a-receber (idem, espelhado)
│   ├── rh/                           ✅ 06/06/2026
│   │   ├── hooks/
│   │   │   ├── useCargos.ts          ← CRUD de Cargo
│   │   │   ├── useFuncionarios.ts    ← lista de Funcionario
│   │   │   └── useFuncionario.ts     ← detalhe + 7 sub-recursos (incl. asos); Promise.allSettled; 403 flags
│   │   ├── components/
│   │   │   ├── CargoForm.tsx         ← modal criar/editar Cargo
│   │   │   ├── FuncionarioForm.tsx   ← sheet criar/editar Funcionario (5 seções)
│   │   │   ├── DadoMedicoForm.tsx    ← sheet rh_medico (dados de saúde gerais, 1-para-1: emergência, tipo sanguíneo)
│   │   │   ├── ASOForm.tsx           ← sheet rh_medico (ASO — registro múltiplo, 1 por exame/ano; upload de arquivo)
│   │   │   ├── DadoBancarioRHForm.tsx← modal rh_financeiro (conta + PIX)
│   │   │   ├── PagamentoForm.tsx     ← modal rh_financeiro (descontos, adicionais, líquido)
│   │   │   └── FolhaPagamentoForm.tsx← modal rh_financeiro (folha mensal)
│   │   └── pages/
│   │       ├── FuncionariosListPage.tsx  ← /app/rh
│   │       ├── CargosPage.tsx            ← /app/rh/cargos
│   │       └── FuncionarioDetailPage.tsx ← /app/rh/:id (4 abas)
│   ├── crm/                          📋 Fase D.3
│   ├── diario/                       ✅ 06/06/2026
│   ├── drone/                        📋 Fase E.1
│   └── calendario/                   📋 Fase E.2
├── types/
│   └── index.ts                      ✅ Empreendimento, Obra, EtapaObra, DocumentoObra + domínio
├── utils/
│   ├── formErrors.ts                 ✅ parseApiErrors · FieldError · FormErrorBanner (erros inline por campo)
│   ├── masks.ts                      ✅ maskCPF/CNPJ/PIS · validateCPF/CNPJ/PIS · formatCPF/CNPJ/PIS
│   ├── dates.ts                      ✅ maskDate · parseDateBR · dateFromBR/ToBR · min/maxISO · validateISO_* · validateDataNasc/Admissao/Demissao
│   ├── fileUpload.ts                 ✅ validateFile · uploadFile · downloadFile · buildAcceptAttr · UploadConfig
│   └── money.ts                      ✅ 07/06/2026 — formatBRL · maskMoney · digitsToCents · centsToApiDecimal · apiDecimalToCents (centavos inteiros, D.1.0)
└── lib/
    ├── utils.ts                      ✅ cn() helper
    └── queryClient.ts                ✅ 07/06/2026 — instância TanStack Query (staleTime 60s, retry 1) — `QueryClientProvider` em `main.tsx`
```

---

## 9. Dependências do `package.json`

### Estado atual (07/06/2026)

```json
"dependencies": {
  "@hookform/resolvers": "^5.4.0",
  "@tanstack/react-query": "^5.101.0",
  "@tanstack/react-table": "^8.21.3",
  "axios": "^1.7.9",
  "class-variance-authority": "^0.7.1",
  "clsx": "^2.1.1",
  "date-fns": "^4.1.0",
  "lucide-react": "^0.460.0",
  "react": "^19.1.1",
  "react-dom": "^19.1.1",
  "react-hook-form": "^7.77.0",
  "react-is": "^19.2.7",
  "react-router-dom": "^7.1.1",
  "recharts": "^3.8.1",
  "tailwind-merge": "^2.6.0",
  "zod": "^4.4.3"
}
```

> **Adicionadas em 07/06/2026 (D.1.0/D.1.1 — fundação UI + Contas a pagar/receber do ERP,
> [§5.3](modulos/moduloerp.md#53-stack-adicional-estende-o-do-projeto)):**
> `@tanstack/react-query` (estado de servidor/cache/invalidação — o "upgrade central"),
> `@tanstack/react-table` (data-grid headless server-side), `recharts` (gráficos financeiros),
> `react-hook-form` + `zod` + `@hookform/resolvers` (**1º uso em D.1.1** — `ContaPagarForm`/
> `ContaReceberForm`/`BaixaForm` com `useFieldArray` para rateio por centro de custo).
> `react-is` foi adicionada à parte — é peer dependency (não declarada) do `recharts`; sem ela o
> `vite build` falha com `Rollup failed to resolve import "react-is"`.

### Removidas (eram bloqueadores)

```
leaflet / react-leaflet / @types/leaflet  → react-leaflet@4.x incompatível com react@19
frappe-gantt                              → Gantt será implementado com CSS/div (GanttBar)
react-hot-toast                           → removido; feedback via estado local por enquanto
```

### A adicionar quando necessário

```
react-leaflet@5 (ou maplibre-gl)  → quando MapaObra for implementado
@radix-ui/react-* (via shadcn)    → quando componentes shadcn específicos forem instalados
```

---

## 10. Fases de construção (A–F)

O rebuild acontece **módulo a módulo**, em fases nomeadas por letra. O **status vivo** de cada uma
está na [tabela de frontend do roadmap](roadmap.md#estado-dos-módulos--frontend-react-08062026) —
aqui só a definição do escopo:

| Fase | Escopo |
|---|---|
| A | Fundação — Tailwind, `AuthContext`, `AppShell`, roteamento |
| B | Landing + Login + Hub de módulos |
| C | Core — Dashboard de KPIs (C.1) · Empreendimentos (C.2) · Obras (C.3) · Clientes (C.4) · Fornecedores (C.5) · Diário+IA (C.6) |
| D | Módulos pagos — ERP `erp_financeiro` (D.1.x, sub-fases em [moduloerp.md §13](modulos/moduloerp.md#13-roadmap-em-sub-fases-fase-d1x)) · RH `rh` (D.2) · CRM `crm` (D.3) |
| E | Extras — Drone wrapper iframe+SSO (E.1) · Calendário (E.2) · SCM/SIL/PDCA/DMS/APS/Maps (E.3, aguarda backend) |
| F | Dashboard de KPIs real substitui o hub (F.1) |
| G | Paywall — medidores de quota, tratamento global do 402 e página de plano (§5.16). Independe de A–F: o backend já trava e já serve o medidor. |

---

## 11. Convenções de código

Vivem em [**frontend-convencoes.md**](frontend-convencoes.md) — leitura obrigatória antes de tocar o
frontend: convenções gerais, erros de formulário, máscaras CPF/CNPJ/PIS, datas, upload/download,
botões inativos e o procedimento para ativar um módulo concluído.
