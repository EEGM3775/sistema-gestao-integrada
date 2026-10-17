# Calendário (`modulocalendar`)

> Agenda unificada: agrega eventos de múltiplas fontes numa única API compatível com FullCalendar,
> com uma UI React de nível profissional (mês/semana/dia/lista, arrastar-e-soltar, CRUD).
> Backend: [backend/modulocalendar/](../../backend/modulocalendar/) ·
> Frontend: [frontend/src/modules/calendar/](../../frontend/src/modules/calendar/).
> **Status das fatias** vive no [roadmap](../roadmap.md) (E.2) — aqui fica só o desenho.

## 1. Visão

Uma agenda só, com paridade funcional com calendários de mercado (Google/Outlook), respeitando o
contrato da plataforma (tenancy + base, sem entitlement pago). A entrega é **fatiada A→E**: a UI
completa entra primeiro sobre a API atual (Fatia A) e cada recurso avançado (recorrência, lembretes,
compartilhamento, extras) estende backend + frontend em seguida.

## 2. Fontes de dados (feed de leitura)

O `GET` agrega, para o período consultado, quatro origens já no formato FullCalendar:

1. **Eventos locais** — modelo `CalendarEvent` (criados no próprio calendário). **Editáveis.**
2. **Feriados** — hoje só **nacionais** (API externa [Nager.Date](https://date.nager.at/), dia
   inteiro, por ano coberto pelo período). Na **Fatia F** passam a ser **por localidade** (nacionais +
   estaduais + municipais) das cidades onde o tenant opera. Somente leitura.
3. **CRM** — tarefas e reuniões (`Interaction`) atribuídas ao usuário (direto ou via lead sob sua
   responsabilidade), consultadas **in-process** no `modulocrm` (funcoeslead absorvido — Fase 11.2).
   Somente leitura.
4. **Diário de obra** — registros `DiarioObra` do usuário, dia inteiro. Somente leitura.

`extendedProps.type` identifica a origem: `local`, `holiday`, `tarefa`, `reuniao`, `diario_obra`.

## 3. API

`GET /api/calendar/events/` (rota em `modulocalendar/urls.py`, incluída por `config/urls.py`)

- **Auth:** `IsAuthenticated` + `RequirePermission` (`calendario.evento`; GET→`.view`, escrita→`.edit`).
  Módulo **base** (sem `RequireModule`).
- **Query (list):** `start` e `end` em ISO 8601 (ex.: `2026-01-01T00:00:00-03:00`).
- **Resposta (list):** array de eventos FullCalendar; só os `type === 'local'` trazem `id` numérico
  (edição/exclusão via CRUD do ViewSet).
- **CRUD (`CalendarEvent`):** `GET/POST/PATCH/DELETE /api/calendar/events/{id}/`. `tenant` **e**
  `user` são read-only, injetados no `perform_create` (o dono é sempre quem cria). O `get_queryset`
  devolve o que a pessoa **vê** (`modulocalendar/acesso.py`): os eventos dela, os das agendas que ela vê
  e os convites. Alterar é do dono ou de quem vê a agenda do evento; o convidado só responde (403).
  Escopo por tenant pelo `TenantScopedViewSetMixin` + RLS.
- **Agendas (Fatia D):** `GET/POST/PATCH/DELETE /api/calendar/calendars/` — as que a pessoa vê; mexer
  numa existente é do dono (ou do admin da empresa).
- **Convite (Fatia D):** `POST /api/calendar/events/{id}/responder/ {status: aceito|recusado}` — exige
  só `calendario.evento.view`.
- **Pessoas (Fatia D):** `GET /api/calendar/pessoas/?search=` — usuários ativos da empresa (só o nome),
  paginado (`PAGINA_*["calendario"]`), para o seletor de convidados e membros.
- **Busca (Fatia E):** `GET /api/calendar/events/busca/?search=` — título, descrição ou local, sem
  acento, paginado; a série aparece uma vez (o mestre).
- **iCalendar (Fatia E):** `GET /api/calendar/events/exportar-ics/?calendar=<id|meus>` e
  `POST /api/calendar/events/importar-ics/` (multipart `arquivo` + `calendar`).

### Modelo `CalendarEvent`

`title`, `description`, `start_time`, `end_time`, `all_day`, `event_type`
(`tarefa`/`reuniao`/`lembrete`), `user` (dono), GenericFK opcional (`content_type`/`object_id`) para
vincular a qualquer objeto. Herda `TenantScopedModel`.

## 4. Frontend (Fatia A)

Estrutura em [frontend/src/modules/calendar/](../../frontend/src/modules/calendar/):

| Arquivo | Papel |
|---|---|
| `pages/CalendarPage.tsx` | Página: FullCalendar + toolbar + legenda + botão "Novo evento" |
| `components/EventDialog.tsx` | Dialog de criar/editar/excluir evento próprio (+ recorrência) |
| `components/RecurrenceEditor.tsx` | Editor de repetição (RRULE) — Fatia B |
| `components/ScopeChooser.tsx` | Escolha do alcance ao editar/excluir série: este/série/futuros — Fatia B |
| `hooks/useCalendarEvents.ts` | TanStack Query: feed + retrieve + create/update/delete + update/deleteOccurrence |
| `api/` | `calendarClient`, `queryKeys`, `endpoints/events` |
| `recurrence.ts` | Conversão estado do editor ↔ string RRULE — Fatia B |
| `types.ts` · `utils.ts` · `formStyles.ts` | Tipos, cores por origem + datas, estilos de formulário |

- **Biblioteca:** **FullCalendar v6** (plugins `daygrid`/`timegrid`/`list`/`interaction`, todos
  **MIT** — os módulos pagos `resource`/`timeline` não são usados). O backend já emite o formato dele.
- **Views:** mês, semana, dia e lista/agenda; navegação prev/próximo/hoje; `locale` pt-BR.
- **Interações:** selecionar faixa → novo evento pré-preenchido; clicar num evento **próprio** → editar;
  arrastar/redimensionar eventos próprios persiste via `PATCH` (só `type === 'local'`; feriado/CRM/
  diário são somente leitura). Erro reverte o movimento na hora.
- **Visual:** cor por origem (legenda), tema alinhado ao navy do SGI via variáveis `--fc-*`.
- **Rota:** `/app/calendario` — **módulo base** (sem entitlement), item destravado no `AppSidebar`
  e no hub (`AppHomePage`).

## 5. Cache (backend)

- Django cache com Redis (`django-redis`); chave por usuário + intervalo; **TTL 30 s**.
- Invalidação automática quando: (a) um `CalendarEvent` do usuário muda; (b) uma `Interaction`
  associada a ele muda (signal `interaction_changed` do `modulocrm` → `receivers.py`).

---

## 6. Roadmap em fatias (A→E)

> Objetivo: paridade com calendários de mercado, sem quebrar o contrato da plataforma. **Ordem** =
> valor primeiro (UI utilizável), depois profundidade. Status por fatia no [roadmap](../roadmap.md).

### Fatia A — Calendário funcional (sobre a API atual)

**Frontend** completo (tabela §4) + **tweak mínimo de backend**: `user` read-only e setado no
`perform_create` (antes o dono não era gravado, embora o `get_queryset` filtrasse por ele).
Sem mudança de modelo. **Entrega:** ver, criar, editar, excluir, arrastar e redimensionar; 4 views;
feed agregado colorido por origem.

### Fatia B — Recorrência (RRULE)

**Backend:** `CalendarEvent` ganhou `recurrence_rule` (string **RRULE** iCalendar, sem `DTSTART` — a
âncora é `start_time`), `excluded_dates` (EXDATE), `recurrence_master` (FK p/ si) e `original_start`.
Expansão em [`recurrence.py`](../../backend/modulocalendar/recurrence.py) (`dateutil.rrule`); o feed
(`list`) emite as ocorrências como eventos individuais (`extendedProps.isRecurring` + `masterId` +
`occurrenceStart`). Editar/excluir por escopo em **actions** do ViewSet (`update-recurrence`/
`delete-recurrence`, POST → `.edit`): `this` (override + EXDATE), `all` (altera o mestre, deslocando
pela diferença desta ocorrência) e `future` (divide a série via `UNTIL`, descontando o `COUNT`
consumido). **Frontend:** editor de repetição ([`RecurrenceEditor`](../../frontend/src/modules/calendar/components/RecurrenceEditor.tsx):
diária/semanal/mensal/anual, intervalo, dias da semana, término por data/contagem) +
[`ScopeChooser`](../../frontend/src/modules/calendar/components/ScopeChooser.tsx) (este/série/futuros).
**Decisão de modelo:** ocorrências são **virtuais** (nunca materializadas); uma exceção vira um
`CalendarEvent` de override apontando para o mestre. **Decisão de render (13/07):** a expansão é
**server-side** (coerente com o feed agregado, sem `@fullcalendar/rrule` no cliente); ocorrências
virtuais não arrastam (mover exige escolher o escopo no diálogo).

### Fatia C — Lembretes e notificações ✅ 14/07/2026

**Entregue (MVP).** Lembretes por evento + centro de notificações in-app.

- **Modelo `EventReminder`** ([backend/modulocalendar/models.py](../../backend/modulocalendar/models.py)) —
  tenant-scoped, FK ao `CalendarEvent` (`related_name='reminders'`), `offset_minutes` (0 = na hora;
  teto de 4 semanas) 1‑N por evento, `last_sent_occurrence` (dedupe por ocorrência). RLS fail-closed
  na migration (`0006_eventreminder`).
- **Modelo `Notificacao`** (em **`nucleo`** — infra de plataforma, não só do calendário;
  [nucleo/models.py](../../backend/nucleo/models.py)): tenant-scoped, endereçada a um `user`,
  `titulo`/`mensagem`/`tipo`/`url`/`lida_em`. RLS fail-closed (`nucleo/0019`). Helper único
  `criar_notificacao` ([nucleo/notificacoes.py](../../backend/nucleo/notificacoes.py)).
- **CRUD:** o serializer do evento expõe `reminders` (lista de offsets em minutos — write pelo campo,
  read via `to_representation`); o ViewSet sincroniza as linhas em `perform_create`/`perform_update`
  (`reminders` ausente = não altera; presente = substitui).
- **Recorrência:** as actions `update-recurrence` também propagam `reminders` pelo escopo — `all`
  substitui os do mestre (valem para todas as ocorrências virtuais), `future` abastece o novo mestre
  (o truncado conserva os seus) e `this` os grava no override. Sem `reminders` no payload, a
  ocorrência/série derivada **herda os do mestre** (`_reminders_for`) — editar a série não perde aviso.
- **Despacho:** task Celery beat `despachar_lembretes` ([tasks.py](../../backend/modulocalendar/tasks.py),
  a cada 60 s) varre os lembretes vencendo sob `rls_bypass()`, cria a `Notificacao` in-app (+ **e-mail**
  se `MAIL_HOST` — no-op sem, paridade com o CRM) e carimba `last_sent_occurrence` (não repete).
  Tolerância de catch-up de 1 h p/ worker fora do ar; recorrentes avisam por ocorrência.
- **API de notificações:** `GET /api/notificacoes/` (as do usuário; `?unread=1`),
  `…/unread-count/` (badge), `…/{id}/marcar-lida/`, `…/marcar-todas-lidas/`
  ([nucleo/notificacoes_views.py](../../backend/nucleo/notificacoes_views.py); módulo base, só do
  próprio usuário).
- **Frontend:** chips de lembrete no [`EventDialog`](../../frontend/src/modules/calendar/components/EventDialog.tsx)
  (na hora / 10 min / 30 min / 1 h / 1 dia) + **sino** no `AppTopbar`
  ([components/notifications/](../../frontend/src/components/notifications/): badge de não-lidas com
  polling de 60 s, lista, marcar lida/todas, clique navega para a `url`).

**Limite do MVP:** canal **WhatsApp** fica para uma extensão (hoje in-app + e-mail). **Depende** do
executor Celery (Fase 10.9, já no compose).

### Fatia D — Compartilhamento, equipe e convidados

**Modelos:** `Calendar` (`owner`, `name`, `color`, `scope`: `pessoal` / `equipe` / `empresa`),
`CalendarMember` (tabela explícita para levar `tenant_id` e entrar na RLS) e `EventAttendee` (`user`,
`status` pendente/aceito/recusado, `responded_at`). `CalendarEvent.calendar` vazio = a agenda pessoal
implícita do dono ("Meus eventos") — o comportamento anterior, sem migração de dado.

**Acesso** (`modulocalendar/acesso.py`, um lugar para o feed, o CRUD, a recorrência e os lembretes):
vê a agenda o dono; os membros, se é de equipe; todos, se é da empresa. **Ver a agenda é poder lançar
nela.** Vê o evento quem é dono dele, vê a agenda dele ou foi convidado; altera o dono ou quem vê a
agenda. O convidado de fora da agenda só responde. Nunca cruza tenant (RLS).

**Convite:** convidar avisa no sino (nível *decidir*, com link `/app/calendario?evento=<id>`); tirar da
lista e cancelar o evento avisam (quem recusou não recebe o cancelamento); responder avisa o organizador.
Numa série, o convite e a resposta valem para a série; o override e o novo mestre de "futuras" herdam
os convidados com as respostas, sem novo convite. **Lembrete** vai ao dono e a quem aceitou. Teto de
convidados por evento: `CALENDAR_TETO_CONVIDADOS` (`payment/planos.py`).

**Frontend:** painel de agendas ao lado do grid (mostrar/ocultar, cor, nova/editar com escopo e
membros); a cor da agenda pinta o evento; convite pendente tracejado e recusado apagado; o evento que a
pessoa não altera abre o `ConviteDialog` (quando, onde, quem organiza, quem vai, aceitar/recusar);
convidados e membros escolhidos pelo `PessoasPicker` (busca no servidor pelo `SelectComBusca`).

### Fatia E — Extras (paridade fina)

**Local** (`CalendarEvent.location`) no diálogo, no convite e no `.ics`. **Busca** no servidor pela
caixa do cabeçalho (o `SelectComBusca` sobre `events/busca/`): escolher leva o grid à data e abre o
evento. **iCalendar** (`modulocalendar/ics.py`, sem biblioteca nova — o `dateutil` resolve fuso):
exporta por agenda (ou "Meus eventos") em UTC, com série (`RRULE`/`EXDATE`) e exceção
(`RECURRENCE-ID`); importa `VEVENT` com data, hora UTC, hora com `TZID` ou flutuante, `DURATION`,
série e exceção da série do mesmo arquivo. A importação **só cria e é tudo ou nada**, como toda
importação da plataforma: evento ilegível, UID repetido no arquivo ou UID já importado na agenda
recusam o arquivo inteiro com a lista do porquê. Tetos: `CALENDAR_ICS_TETO_KB` e
`CALENDAR_ICS_TETO_EVENTOS`. Ficaram fora: anexos, link de reunião e fuso por evento.

### Fatia F — Feriados por localidade (federais, estaduais e municipais) ✅ 13/07/2026

**Entregue.** Feriados **federais/estaduais/municipais**, cada um com **cor própria** e o **nome da
localidade** (país/estado/cidade) no título. Seletor no topo (ao lado de "Calendário"): **obra →
estado → município** — a obra determina estado+município (resolvidos do endereço via `nucleo.geo`);
sem endereço ou sem obra, o usuário escolhe estado/município livremente (o município só habilita
após o estado). O usuário **nunca informa IBGE** (resolvido internamente).

- **Modelos** (referência **global**, não tenant-scoped): `Feriado` (`data`/`nome`/`escopo`/`uf`/
  `ibge`/`cidade`) e `FeriadoSync` (carimbo da última sincronização).
- **Fontes:** federal + estadual via **`python-holidays`** (offline, pt-BR; estadual = o que a UF
  acrescenta sobre o nacional); municipal via **dataset MIT `joaopbini/feriados-brasil`** (um JSON
  por ano, baixado pela API raw do GitHub; nome da cidade resolvido pelo IBGE). Comando
  `manage.py sincronizar_feriados [--anos …] [--anos-municipais …] [--sem-municipal]`: sem `--anos`,
  grava nacional e estadual **de 1900 a 2100** (`CALENDARIO_ANO_*` do `planos.py`; a biblioteca aplica
  a lei de cada época, e o estadual dela começa em 1996) e baixa o municipal de ano−1 a ano+2; o
  municipal de um ano só é trocado se o download trouxe algo. Também **task Celery semanal**
  (`modulocalendar.tasks`, em `CELERY_BEAT_SCHEDULE`). **Fallback:** sem sync, o feed usa o
  Nager.Date só p/ o nacional.
- **Feed:** nacional sempre; estadual se `?uf=`; municipal se `?ibge=` (params derivados do seletor).
- **Endpoints:** `GET /api/calendar/localidades/` (obras + localidade resolvida), `GET /api/geo/municipios/?uf=`
  (via serviço geo), `GET /api/calendar/feriados/status/` (**só superuser/`is_platform_admin`** — a
  mensagem "sistema atualizado com os feriados").
- **Frontend:** [`LocalidadeSelector`](../../frontend/src/modules/calendar/components/LocalidadeSelector.tsx),
  cores por escopo (`HOLIDAY_SCOPE_STYLE` em `utils.ts`), banner de atualização ao superuser.

**Desenho original (mantido como referência):**

**Objetivo:** além dos nacionais, exibir os feriados **estaduais** (por UF) e **municipais** (por
cidade) das localidades onde o tenant opera — derivadas do **endereço** de empreendimentos/obras.

**Achar a cidade a partir do endereço** — já implementado como **serviço compartilhado**
[`nucleo.geo`](../../backend/nucleo/geo.py) (reutilizável por qualquer módulo: maps, drone via o
endpoint, NF/relatórios — sem reimplementar), com endpoint fino `GET /api/geo/resolver/`
(`?cep=`/`?endereco=`/`?cidade=`/`?uf=`). Dois caminhos, nesta ordem:
- **Com CEP:** [ViaCEP](https://viacep.com.br/) (grátis, sem chave) devolve `localidade` (cidade),
  `uf` **e** `ibge` — resolve tudo de uma vez.
- **Sem CEP (pelo nome):** extrai `cidade + UF` do texto livre e casa `cidade+UF` → IBGE contra a
  lista de municípios do estado (API de localidades do IBGE, cache longo). Parser **robusto a erros**:
  reconhece a UF por **sigla** (`BA`) ou **nome por extenso** (`Bahia`), tolera **erro de digitação**
  em estado e cidade (fuzzy `difflib`, cutoff alto p/ não chutar), e **distingue rua de cidade/estado**
  ancorando a leitura no fim do endereço (o estado vem por último) — "Ba 026" (via) não vira "Bahia".
  Se a cidade não casar mas a UF sim, devolve só o estado. Testes em
  [`testes/backend/nucleo/test_geo.py`](../../testes/backend/nucleo/test_geo.py).
- Recomendado ainda assim **persistir `cidade`/`estado`** em `Obra`/`Empreendimento` (espelhando
  `clientes`), preenchidos no cadastro — mais confiável que reparsear texto e útil p/ NF/ERP/relatórios.

**Fonte dos feriados** (confirmado que existem, cobertura boa; cidades minúsculas <1k hab. ficam de
fora e não são foco):
- **Nacionais + estaduais:** `python-holidays` (`holidays.Brazil(subdiv=UF)`) — offline, sem HTTP.
- **Municipais:** **dataset [`joaopbini/feriados-brasil`](https://github.com/joaopbini/feriados-brasil)**
  — **licença MIT (uso comercial OK)**, cobre os **5.570 municípios**, em JSON/CSV/SQL, com tabela de
  municípios (nome+UF ↔ IBGE). **Recomendado:** *vendorizar* o dataset (offline, sem custo nem
  rate-limit) e carregar por `(UF, IBGE)`. Alternativa online: **feriadosapi.com** (grátis só cobre
  nacional/estadual/27 capitais; municípios além das capitais são pagos; 60 req/min).
- **Override do tenant:** modelo `Feriado` **editável** (opcional) só para **corrigir/completar**
  lacunas do dataset numa cidade específica — não é mais a fonte primária.

**Resolução no feed:**
- Derivar as `(UF, IBGE)` **distintas** das obras/empreendimentos do tenant (opcionalmente só as
  atribuídas ao usuário) — sempre **tenant-scoped** (RLS).
- Merge com `extendedProps.type='holiday'` + `scope` (`nacional`/`estadual`/`municipal`) + `local`
  (cidade/UF); sub-legenda por escopo, origem no tooltip e filtro para ligar/desligar localidades.
- **Cache:** feriados por `(ano, UF, IBGE)` mudam pouco → dataset em memória/tabela ou TTL longo,
  separado do feed de 30 s.

> **Decisão em aberto (sua):** (1) fonte municipal — **dataset MIT vendorizado** [recomendado] × API
> online (feriadosapi paga p/ municípios) × só override editável; (2) persistir `cidade`/`estado` em
> `Obra`/`Empreendimento` nesta fatia ou antecipar (ajuda NF/ERP/relatórios).

---

## 6.1 Dia útil **bancário** (`dias_uteis.py`)

A tabela `Feriado` tem um segundo consumidor, e ele não é de agenda: é o **vencimento** que vai ao
carnê e ao boleto. `AjusteDeVencimento(uf, ibge)` empurra para o próximo dia útil a data que cai em
sábado, domingo ou feriado, e `explicar(dia)` devolve `(data_ajustada, motivo)` — "domingo", "Nossa
Senhora Aparecida" — para a tela dizer **por que** a data mudou.

**Por que não reusa o `CalendarioTrabalho` do PDCA.** As duas perguntas só parecem a mesma. O PDCA
pergunta *"a equipe trabalha neste dia?"*, e a resposta pode ser "sim" num sábado de mutirão; o
financeiro pergunta *"o banco compensa neste dia?"*, e aí não há calendário de obra nenhum. Misturar
os dois faria a obra que trabalha aos sábados receber boleto aos sábados.

**Escopo por localidade, com a mesma régua de dado honesto da §6:** nacional sempre; estadual só com
a UF; municipal só com o código IBGE. Sem o código, não se afirma feriado municipal.

**Desempenho:** os feriados são carregados **uma vez por ano tocado** e ficam no objeto — ajustar um
carnê de 360 parcelas é uma consulta, não 360. Por isso o ajuste é injetado como objeto em
`clientes.plano_pagamento.montar()`, e não resolvido dentro do laço.

**De 1900 a 2100, com ou sem a tabela** ([`feriados.py`](../../backend/modulocalendar/feriados.py)).
Três camadas, nesta ordem de precedência no nome do dia:

1. **Lei** — da tabela; o ano que faltar nela é calculado pelo `python-holidays` na hora
   (`anos_calculados`), em vez de virar "dia útil por não saber";
2. **Município** — da tabela nos anos que o dataset publica; nos outros, **projetado** pela regra que
   os anos publicados mostram, linha a linha: o mesmo dia/mês em dois anos é fixo, a mesma distância
   da Páscoa é móvel (Corpus Christi), e o visto num ano só decide pelo nome. O ajuste diz quando uma
   data projetada decidiu o vencimento (`municipal_projetado`);
3. **Banco** — só com `bancario=True` (o vencimento de título liga; a CAT do PDCA não): Carnaval
   (segunda e terça) e Corpus Christi, dias sem expediente bancário do calendário ANBIMA.

`base_sincronizada()` responde sempre sim — a lei nunca falta — e fica porque as telas leem o campo.
Quem consome:
[clientes.md](clientes.md) (carnê) e [funcoescobrancas.md](funcoescobrancas.md) (`dueDate` do Asaas).

---

## 7. Convenções e decisões

- **Datas:** o backend fala ISO 8601 com offset; a UI converte para `datetime-local`/`date` em
  `utils.ts` (helpers locais do módulo — os utilitários BR de `@/utils/dates.ts` cobrem `DD/MM/AAAA`,
  não `datetime-local`).
- **Dono implícito:** o cliente nunca envia `user`/`tenant`; ambos são injetados no create.
- **Somente `local` é editável:** feriado, CRM e diário são projeções de leitura — a UI bloqueia
  arrastar/editar/excluir dessas origens.
- **FullCalendar sem CSS de arquivo:** v6 injeta estilos via JS; o tema vem de variáveis `--fc-*`
  inline, respeitando a convenção "sem `.css` por componente".
- **Feriados por localidade (Fatia F):** a cidade vem do **endereço** (ViaCEP pelo CEP, ou parse) —
  o usuário nunca digita IBGE (resolvido internamente). Municipais **têm fonte**: dataset MIT
  `joaopbini/feriados-brasil` (5.570 municípios), vendorizável offline; override editável só p/ lacunas.
