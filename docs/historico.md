# Histórico de execução — diário de obra

> Registro **cronológico reverso** do que foi entregue, validado e corrigido — com as datas, os bugs
> encontrados e as decisões tomadas no caminho. Este é o único lugar onde narrativa datada deve viver:
> o [roadmap.md](roadmap.md) guarda só **status e plano**; a [arquitetura](arquitetura.md) descreve o
> sistema **sem** status. Achados de revisão ainda abertos são rastreados em [pendencias.md](pendencias.md).

---

## 04/07/2026 — S1 corrigido (pontual): dashboard ERP e views de NF cruzavam tenants

Primeiro achado do pacote crítico de segurança S1–S4 fechado. Três endpoints do ERP eram `APIView`
puras, fora do `TenantScopedViewSetMixin`, então **não filtravam por tenant nem armavam a RLS**:

- `ERPDashboardView` (`/api/erp/dashboard/`) somava o aging de contas a receber/pagar e o fluxo de
  caixa de **todos** os tenants — um cliente enxergava os números financeiros dos outros.
- `AtualizarStatusNFView` (`/api/erp/atualizar-status-nf/`) e `ConsultarStatusNFView`
  (`/api/erp/nf/<id>/consultar/`) liam/gravavam NF de qualquer tenant por `id`.

**Correção (pontual — a parte estrutural continua sendo o S2):** novo `TenantScopedAPIViewMixin` em
`backend/nucleo/tenancy.py`, espelho do mixin de ViewSet para `APIView`s puras — arma a RLS do
Postgres em `initial()` (no-op no SQLite) e expõe `scope_qs()`, que filtra pelo tenant do usuário
(superusuário vê tudo). As três views herdam o mixin e passam **cada** queryset por `scope_qs()`; o
acesso cruzado some do somatório do dashboard e vira **404** nas views de NF. A lógica de escopo e a
de armar a RLS viraram funções de módulo (`scope_queryset_by_tenant`, `arm_rls_for_tenant`)
reutilizadas pelos dois mixins, sem alterar o comportamento do `TenantScopedViewSetMixin`.

Validação: `manage.py test moduloerp.tests` — 4 verdes, incluindo `S1TenantIsolationAPIViewTests`
(dashboard soma só o próprio tenant: 1000, não 1500; PATCH/consulta de NF de outro tenant → 404 sem
gravar). As suítes de isolamento adjacentes (nucleo, funcoescobrancas, modulocrm, clientes,
modulocalendar) seguem verdes (28) — o refactor do mixin compartilhado não regrediu nada.
`pendencias.md` (S1) atualizado. **Ainda aberto o S2** (RLS fail-open): comando/shell/task/webhook
continuam sem proteção no Postgres até a política virar fail-closed + middleware por requisição.

## 04/07/2026 — D2 corrigido: boleto Asaas saía no cliente errado (trava de identidade)

Um usuário reportou que, ao cadastrar um cliente novo ("Edison Goes") e gerar cobrança, o boleto
saiu no nome de um cadastro pré-existente no Asaas ("EEGM"). Investigação em `funcoescobrancas`
achou duas causas somadas:

- **Busca por documento vazio adotava a conta inteira:** `client.buscar_customer_por_cpf_cnpj`
  com CPF/CNPJ vazio disparava `GET /customers?cpfCnpj=` — o Asaas ignora o filtro vazio, devolve
  **todos** os customers, e o código pegava `dados[0]` (o primeiro da conta, "EEGM").
- **Reuso por CPF sem conferir o nome:** `garantir_customer_asaas` adotava qualquer customer com
  o mesmo documento sem comparar o nome e ainda confiava cegamente no `id_cliente_gateway` salvo
  (que já podia estar contaminado de uma tentativa anterior) — os dados do cliente do sistema
  nunca chegavam ao gateway.

**Correção — trava de identidade (nunca emitir para cadastro divergente):**

- `buscar_customer_por_cpf_cnpj` retorna `None` sem documento e confere o `cpfCnpj` do candidato
  antes de considerá-lo match.
- Nova `services.validar_cliente_para_cobranca` (só leituras) exige **nome _e_ CPF/CNPJ** batendo:
  sem documento válido (11/14 dígitos) → bloqueia; CPF igual + nome diferente → bloqueia como
  provável erro de digitação (comparação `_normalizar_nome`, tolerante a acento/caixa/espaço mas
  sensível ao conteúdo — `EEGM` ≠ `Edison Goes`); nome batendo → reusa; inexistente → cria. A
  fonte da verdade passou a ser sempre o CPF/CNPJ, e o `id_cliente_gateway` se autocorrige.
- **Visibilidade ao usuário:** a view `gerar-cobranca` roda a validação **síncrona** antes de
  enfileirar e devolve `409` com a mensagem pronta ("Este CPF/CNPJ já está cadastrado no gateway
  em nome de 'EEGM', diferente de 'Edison Goes'…"); o Sheet de detalhe da `ContaReceber` mostra o
  bloqueio em destaque de alerta, então o operador corrige o cadastro **antes** de errar.
- Defesa em profundidade: `garantir_customer_asaas` repete a validação e `tasks.criar_cobranca`
  trata `CobrancaBloqueada` como falha **permanente** (sem retry, gravada na DLQ).

Validação: `manage.py test funcoescobrancas` — **12 testes verdes** (busca com documento
vazio/divergente, normalização de nome, bloqueio/reuso/criação, e o endpoint `gerar-cobranca`
retornando 409 sem enfileirar e 202 no caminho feliz). Doc do módulo e `pendencias.md` (D2)
atualizados.

**Auditoria proativa (a pedido do usuário):** a mesma trava agora roda em modo relatório —
`services.analisar_divergencias_asaas` faz uma varredura paginada da conta Asaas
(`iterar_todos_customers`, dict por CPF/CNPJ, não um GET por cliente) e classifica cada cliente do
tenant em `sem_documento`/`nome_divergente`/`vinculo_divergente`. Exposta de duas formas: o comando
`manage.py analisar_divergencias_asaas [--tenant <slug>]` (ops/cron) e o endpoint
`GET /api/clientes/divergencias-asaas/`, que o frontend chama **ao clicar em "Novo Cliente"** — um
painel no topo do formulário mostra as divergências existentes antes de cadastrar mais um. +2 testes
(relatório classifica cada tipo; endpoint 200 com contagem) → **14 verdes** no `funcoescobrancas`.

**Robustez do painel (a pedido do usuário):** o `DivergenciasAsaasPanel`
(`frontend/src/modules/clientes/components/ClienteForm.tsx`) renderizava a lista **inteira** sem
teto — com milhares de divergências o aviso "tomava" a gaveta de cadastro, enterrava os campos do
formulário e jogava milhares de `<li>` no DOM. Correção: lista limitada a
`MAX_DIVERGENCIAS_VISIVEIS` (50) com rolagem própria (`maxHeight` 220px) e rodapé "+ N outras
divergências não listadas aqui"; o cabeçalho continua exibindo o total real. O painel agora tem
altura fixa independentemente da quantidade de divergências. Rebuild só do serviço `react`; smoke
pós-deploy OK (`/` → 200, `/api/clientes/divergencias-asaas/` → 401 sem login).

## 03/07/2026 — L4 corrigido + D1 confirmado: funcoeslead absorvido pelo ERP (Fase 11.2 antecipada)

O último crítico funcional da revisão v02 foi fechado **por construção** — em vez de remendar a
auth do microsserviço Node, a lógica virou Python in-process:

- **Conversão + scoring de lead** → `modulocrm/services.py` (transacional, tenant herdado do
  lead; status novo `CONVERTIDO` na migration `modulocrm/0006` — o Node marcava convertido como
  `PERDIDO`) + actions `POST /api/crm/leads/{id}/convert|score/`.
- **Agenda do calendário** → `modulocalendar` consulta as `Interaction` direto no ORM (fim da
  chamada HTTP à porta 3004 e do evento vermelho de erro).
- **Notificações de tarefas a vencer** → Celery task `modulocrm.tasks.notificar_tarefas_a_vencer`
  (`CELERY_BEAT_SCHEDULE` horário; no-op sem `MAIL_HOST` — variáveis `MAIL_*` novas no settings).
- **Bugs colaterais corrigidos no caminho:** `InteractionViewSet` dava FieldError/500 para
  não-staff (filtro em GenericFK); `UsuarioSerializer` referenciava `perfil` (campo removido na
  Fase 6) e derrubava qualquer resposta que serializasse o responsável; `Funcionario` sem import
  em `modulocrm/serializers.py`; filtros `django-filter` habilitados em leads/interações (o
  agravante do L4).
- **D1 confirmado por teste** (`nucleo/test_legacy_token.py`): os endpoints-alvo dos callbacks
  respondem 401 ao `Authorization: Token` legado — `funcoesia`/`funcoesnf`/`funcoeswhatsapp`
  seguem mortos até a Fase 11/10.8. **S6** morre junto com o serviço descomissionado.

Validação: `manage.py test modulocalendar modulocrm nucleo moduloerp` — **15 testes verdes**.

## 03/07/2026 — Críticos L1–L3 da revisão v02 corrigidos

- **L1 (calendário 500):** filtro `usuario=` → `criado_por=` no agregador; eventos locais agora
  saem com `id`; feriados buscados para cada ano do período (range dez→jan não perde o ano
  seguinte). Smoke tests em `modulocalendar/tests.py`.
- **L2 (DLQ nunca gravava):** `FailedTask.task_id` virou `CharField(36)` (id do Celery é UUID —
  migration `nucleo/0010`) e o hook `on_failure=<signature>` (nunca invocado pelo protocolo do
  Celery) foi substituído pela base `nucleo.tasks.DLQTask`, adotada nas tasks de IA e de cobrança.
  Teste força falha e verifica a linha na DLQ (`nucleo/test_dlq.py`).
- **L3 (NF sem tenant/documento):** NF emitida de `ContaReceber` agora herda `tenant=conta.tenant`
  e o snapshot do cliente usa os campos reais do model (`cpf_cnpj`, endereço completo com
  cidade/UF/CEP/IBGE — contrato do `emitirNF.js`). Teste em `moduloerp/tests.py`.

Validação: `manage.py test modulocalendar nucleo moduloerp` — 8 testes verdes (novos + isolamento
de tenant preexistente).

## 02/07/2026 — Documentação reorganizada em 3 naturezas + auditoria completa

A `docs/` foi reestruturada para separar **planta** (sem status), **status**
([roadmap](roadmap.md) enxuto + [pendencias.md](pendencias.md)) e **histórico** (este arquivo);
convenções do frontend extraídas para [frontend-convencoes.md](frontend-convencoes.md); regra de
sincronização do [CLAUDE.md](../CLAUDE.md) reescrita. A auditoria subsequente corrigiu conteúdo
desatualizado (referências ao modelo `Fatura`, endpoint do calendário, `nucleo.md`/docs Node
reescritos com avisos de L1–L4) e revelou um **achado novo (D1)**: todos os callbacks Node→ERP
(`funcoesia`, `funcoesnf`, `funcoeswhatsapp`) usam o token estático legado que o ERP rejeita desde
a Fase 6 — registrado em [pendencias.md](pendencias.md) para confirmação por teste.

## 02/07/2026 — Revisões técnicas v01 e v02 (laudos)

Dois laudos de inspeção do código, no mesmo dia: **v01** com foco em **segurança** (isolamento de
tenant, JWT, defaults inseguros — achados S1–S9) e **v02** aprofundando bugs funcionais,
arquitetura, performance e frontend (L1–L9, A1–A12, F1–F6), com 4 críticos funcionais: calendário
500, DLQ que nunca grava, NF sem tenant, `funcoeslead` com auth morta. Por decisão do usuário
(03/07/2026), os dois laudos foram **consolidados num documento único** e excluídos — todo o
conteúdo (problema → correção de cada achado + ideias de funcionalidades) vive em
[pendencias.md](pendencias.md).

## 08/06/2026 — D.1.2: Boletos & Asaas (backend + UI) + 3 bugs de infraestrutura

**Backend/integração (MVP):** novo Django app [funcoescobrancas](modulos/funcoescobrancas.md)
(cliente HTTP Asaas sandbox + Celery tasks + webhook idempotente em
`/api/erp/cobrancas/webhook/asaas/`) e action `gerar-cobranca` em `ContaReceber`; emite cobrança
(espelha `Cliente`→`customer` Asaas, cria `payment`, grava `Boleto` `EMITIDO`) e processa o webhook
de pagamento com **baixa automática** (`dar_baixa(origem='asaas')`, reaproveitando o guard
`RevisaoBaixa` do D.1.1). Escopo MVP por decisão do usuário: golden path apenas (emitir + baixa
automática); cancelamento/estorno/PIX QR/parcelamento ficam para a slice 2. Credencial **global**
via `.env` (`ASAAS_API_KEY`/`ASAAS_BASE_URL`/`ASAAS_WEBHOOK_TOKEN`) — credencial por tenant é
pendência registrada.

**Validado duas vezes:** (1) e2e com `AsaasClient` mockado (sem rede) — emissão idempotente, baixa
automática, idempotência de reenvio de evento, guard `RevisaoBaixa` em pagamento duplicado e a view
HTTP do webhook (token ausente/errado/correto); (2) **ponta a ponta com o sandbox Asaas real** via
túnel ngrok — cobrança real emitida, pagamento simulado via `receiveInCash`, dois eventos
(`PAYMENT_CREATED`/`PAYMENT_RECEIVED`) chegaram pela internet em ~2s e aplicaram a baixa automática
de verdade (`ContaReceber`→`QUITADO`, `Boleto`→`PAGO`, `Transacao` lançada). Webhook de teste
removido do Asaas e dados locais limpos ao final.

**UI dedicada:** `BoletosListPage`/`BoletoDetailPage` (telas dedicadas somente leitura — decisão do
usuário, não Sheet/drill-down), timeline de eventos do webhook, `StatusBoletoBadge` e botão
"Gerar cobrança (Asaas)" em `ContasAReceberPage`
(ver [funcoescobrancas.md "UI dedicada"](modulos/funcoescobrancas.md#ui-dedicada--telas-de-boletos-entregue-08062026-)).

**3 bugs pré-existentes corrigidos na validação real** (bloqueavam todo o golden path; nenhum
específico do D.1.2):

1. `nucleo/signals.py` gravava `task_id` (UUID) num `PositiveIntegerField`, derrubando **qualquer**
   Celery task com `502` de transação atômica;
2. `ASAAS_API_KEY`/`BASE_URL`/`WEBHOOK_TOKEN` nunca chegavam ao container `sgi-erp` (faltava no
   `docker-compose.yml`);
3. `sgi-erp` rodava imagem buildada desatualizada (é preciso `docker compose build erp` a cada
   mudança de backend, como o `sgi-react`).

Detalhe completo em
[funcoescobrancas.md "Bugs corrigidos durante a validação real"](modulos/funcoescobrancas.md#bugs-corrigidos-durante-a-validação-real-08062026).

**Túnel ngrok persistente** montado para webhook ativo contínuo (sem reabrir/registrar a cada
sessão) — ⚠️ **expõe o gateway de dev inteiro na internet pública enquanto ligado** (decisão
consciente do usuário; aviso detalhado em
[funcoescobrancas.md "Túnel ngrok persistente"](modulos/funcoescobrancas.md#túnel-ngrok-persistente-para-testes-contínuos-08062026)).

## 07/06/2026 — D.1.0 + D.1.1: Fundação UI do ERP + Contas a pagar/receber

- **D.1.0 (fundação UI):** camada de dados TanStack Query (`erpKeys` + endpoints + hooks),
  `FilterBar`+`FinanceDataTable` (paginação/ordenação server-side), `MoneyInput`/`MoneyDisplay`
  (centavos inteiros), hub `/app/erp` com KPIs reais do `/api/erp/dashboard/` e gráficos Recharts,
  code-splitting (`lazy`/`Suspense`).
- **D.1.1 (workspaces):** `Sheet` slide-over (1º uso no projeto) · formulários RHF+zod (1ª adoção de
  `react-hook-form`+`zod`: `ContaPagarForm`/`ContaReceberForm`/`BaixaForm`/`RateioField`) ·
  `ContasAPagarPage`/`ContasAReceberPage` (lançar, editar, ver detalhe, dar baixa parcial/total,
  rateio por centro de custo). No backend, `Fatura` foi consolidada em `ContaPagar`/`ContaReceber`
  (+`CentroCusto`/`Rateio*`/`LoteRemessa`/`RevisaoBaixa`).
- **Validado (golden path):** CRUD completo, baixa parcial→total, rateio por centro de custo, lote de
  remessa e aging do dashboard testados via API/gateway; dados de teste limpos.
- **Achado corrigido no mesmo dia:** `dar_baixa()` não impedia baixa repetida em título já
  `QUITADO`/`CANCELADO` — agora detecta e encaminha para revisão do papel `financeiro`
  (`RevisaoBaixa`/`BaixaRequerRevisao`, fila `/api/erp/revisoes-baixa/` com `aprovar`/`rejeitar`).
  Reaproveitado com sucesso pelo webhook Asaas do D.1.2 (`origem='asaas'`).
  Ver [moduloerp.md §15](modulos/moduloerp.md#15-questões-em-aberto-decidir-antes-da-sub-fase-relevante).
- **Dependências adicionadas:** `@tanstack/react-query`, `@tanstack/react-table`, `recharts`,
  `react-hook-form`+`zod`+`@hookform/resolvers`, `react-is` (peer não declarada do `recharts`; sem
  ela o `vite build` falha com `Rollup failed to resolve import "react-is"`).

## 06/06/2026 — Frontend: RH completo + Diário de Obra & IA + utilitários de formulário

- **RH** (`modules/rh/`): cargos CRUD, funcionários CRUD, detalhe com 4 abas (Dados Pessoais,
  Documentos, Saúde, Financeiro) — abas sensíveis exigem papéis `rh_medico`/`rh_financeiro` (403 não
  quebra a página; `Promise.allSettled`).
- **Diário de Obra + IA** (`modules/diario/`): diário do dia compartilhado — contribuição texto+foto
  com autoria, galeria de análises de IA, moderação por responsável técnico.
- **Utilitários de formulário** (`utils/`): erros inline por campo (`formErrors.ts`), máscaras e
  validação de CPF/CNPJ/PIS (`masks.ts`), datas com min/max e validação onBlur (`dates.ts`), upload
  autenticado com progresso + download autenticado (`fileUpload.ts` + `useFileUpload.ts`), config de
  upload por admin. Convenções de uso em [frontend-convencoes.md](frontend-convencoes.md).

## 05/06/2026 — Frontend: Fornecedores

`modules/fornecedores/` — lista + detalhe (produtos/serviços, dados bancários).

## 04/06/2026 — Frontend reconstruído do zero + Empreendimentos, Obras e Clientes

O frontend foi **reconstruído do zero** (não portado da v01). A base de design veio da landing da
v01 (estrutura de seções, copy, paleta navy `#0A2A5B`, tipografia Montserrat+Roboto). O que existia
antes do rebuild permanece disponível no repositório da v01 (`01sistema_gestao_integrada`, pasta irmã).

Entregues no mesmo ciclo: fundação (Tailwind 4, CSS vars, fonts), `AppShell` (sidebar colapsível +
topbar navy), `LandingPage` (5 seções), `LoginPage` (dois painéis), `AppHomePage` (hub de módulos com
entitlement) e os módulos **Empreendimentos** (lista+detalhe+form), **Obras** (lista, detalhe, etapas
CRUD, documentos) e **Clientes** (lista, detalhe: aquisições, contratos, documentos, bancário).
Backend de `clientes` completado na mesma data.

## 02/06/2026 — Fase 6: Consolidação de identidade & RBAC de plataforma ✅

- **Limpeza de legados:** login local do ERP removido (`auth_views.py` + rotas `/api/token`,
  `/api/auth/*`); endpoints `/api/perfis`/`/api/permissoes` removidos (o ERP lê papéis das claims);
  `nucleo.Usuario` segue só como espelho JIT.
- **Entitlement genérico (camada 1):** `RequireModule("codigo")` em
  [nucleo/permissions.py](../backend/nucleo/permissions.py) — espelho do `MODULE_drone`. Mapa:
  `rh`→`rh`, `modulocrm`→`crm`, `moduloerp`→`erp_financeiro`; apps base sem `required_module`.
- **RBAC (camada 2):** `RequireRole` aplicado ao financeiro (`required_role="financeiro"`).
- **Validado (`phase6_rbac_test.py`):** `demo` (crm/rh/erp + papel financeiro) vs `semdrone` (só erp
  + operacional): `/api/funcionarios/` 200 vs 403; `/api/crm/leads/` 200 vs 403; `/api/erp/faturas/`
  200 vs 403 (ambos têm o módulo, só `demo` tem o papel); `/api/clientes/` 200/200; `/api/token/` → 404.

## 01/06/2026 — Fase 5: Endurecimento RS256/JWKS + borda ✅ (núcleo)

- **RS256 + JWKS:** IAM assina com chave privada RSA (`infra/keys/jwt_private.pem`, gerada por
  `generate.sh`, não versionada) e publica a pública em `/.well-known/jwks.json`; ERP e drone validam
  só com a pública (escolha automática RS256↔HS256).
- **Borda:** headers de segurança no gateway (X-Frame-Options, X-Content-Type-Options,
  Referrer-Policy, CSP frame-ancestors) + rate limit no `/auth/login` (429).
- **Validado (`phase5_rs256_test.py`):** token RS256 real → drone/ERP 200; **token forjado com o
  antigo segredo HS256 → 401** — o vetor do segredo compartilhado foi fechado.

## 31/05/2026 — Fases 1–4: SSO, UI integrada, vínculo drone↔obra e deploy unificado ✅

**Fase 1 — SSO ponta a ponta:** funcoesODM (Java) virou resource server da IAM: valida o JWT,
JIT-provisiona o `User` por `sub`, injeta `tenant_id`/`modules`; endpoints exigem o entitlement
`drone` (`MODULE_drone` → 403); `Project`/`User` ganharam `tenant_id`; login local atrás de flag.
Angular captura o token injetado por query param e decodifica `modules`/tenant; middleware `iamAuth`
criado nos microsserviços Node. Validado em Docker: sem token → 401; sem `drone` → 403; com `drone`
→ 200; projeto do tenant A invisível para o B.
*Bug corrigido:* `dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()` (o 403 do entitlement
virava 401 no re-dispatch de erro).

**Fase 2 — UI integrada:** gateway nginx ([infra/gateway/](../infra/gateway/)) roteia `/`→React,
`/api`→Django, `/auth`→IAM, `/drone`→Angular, `/odm-api`→Java, `/ws`→Java; drone servido sob
`/drone/` (base href). React ganhou `AuthContext` (IAM) + menu condicional `hasModule` + wrapper em
iframe com injeção de token. Validado pelo gateway 8090.
> ⚠️ *Bug crítico corrigido:* o `JWT_SECRET` da raiz (IAM/ERP) **diferia** do
> `ImgDrone/funcoesODM/.env` → IAM assinava com um, drone validava com outro → 401. Alinhado para um
> único segredo forte (≥32 bytes). Na Fase 1 "passou" porque os tokens foram forjados com o segredo
> do funcoesODM.

**Fase 3 — Vínculo drone↔obra:** `Project` (Java) ganhou `empreendimentoId`/`obraId`;
`GET /odm-api/projects` filtra por `?obraId=`/`?empreendimentoId=` (escopado ao tenant); soft-unlink
via `DELETE /odm-api/projects/links/{obra,empreendimento}/{id}`. Angular `ProjectContextService`
capta os ids da URL e injeta no `createProject`; o wrapper React repassa. Validado via gateway.

**Fase 4 — Deploy unificado:** `docker-compose.yml` raiz com profiles (`--profile full` → 11 serviços
na rede `sgi`); criados `backend/Dockerfile` (WeasyPrint), `frontend/Dockerfile` (vite→nginx),
`infra/gateway/nginx.unified.conf`; healthchecks IAM/ERP → gateway sobe limpo. Validado por
`phase4_e2e.py`: login único vale no ERP e no drone; sem token 401; `semdrone` 403.
> ⚠️ *Bug corrigido:* `requirements.txt` sem pin instalou **Django 6.0** no container (dev usa
> 5.2.5), quebrando `CheckConstraint(check=...)` → fixado `Django>=5.2,<5.3`.

## Fase 0 — Fundação (sem data registrada) ✅

- **0.1 Banco por env + infra de dev:** `DATABASES` por variáveis de ambiente; PostgreSQL+Redis via
  compose.
- **0.2 Serviço IAM** ([iam/](../iam/)): Django + DRF + SimpleJWT, banco próprio. Modelos `Tenant`,
  `Usuario`, `Perfil`/`Permissao`, `Modulo`, `AssinaturaTenant`, `AcessoUsuarioModulo`. Endpoints
  `/auth/login|refresh|logout|me` + admin de plataforma/tenant.
- **0.3 ERP como resource server + tenancy:** login local do ERP aposentado; FK `tenant` em todos os
  modelos de negócio via `TenantScopedModel`; escopo nos ViewSets via `TenantScopedViewSetMixin`;
  RLS no Postgres (`set_config` por request, no-op no SQLite); testes de isolamento passando.
