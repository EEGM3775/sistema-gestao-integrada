# Pendências — revisão técnica consolidada

> **Documento único** que consolida os dois laudos de revisão de 02/07/2026 (v01: segurança;
> v02: bugs/arquitetura/frontend) **e** serve de rastreador vivo. Os laudos originais foram
> absorvidos aqui e excluídos. Cada achado traz problema e direção de correção; ao corrigir,
> troque o status para `✅ corrigido DD/MM/AAAA`
> IDs: `S*` segurança · `L*` bugs de lógica · `A*` backend/arquitetura ·
> `F*` frontend · `D*` achados de auditoria posteriores.

**Ordem de ataque recomendada:**

1. **L1–L4** — módulos inoperantes (**✅ todos corrigidos 03/07/2026**).
2. **S1–S4** — pré-requisito para operar como SaaS real (**✅ todos corrigidos**: S1+S2 04/07/2026 —
   RLS armada na autenticação + fail-closed fecharam o vazamento entre tenants; **S3+S4 12/07/2026** —
   fail-fast de config + RS256 obrigatório em produção).
3. **L5–L7 + A1** — pacote "integridade financeira sob concorrência" (**✅ todos corrigidos 12/07/2026**).
4. **S8 + D12/D14/D15 + D20–D22** — pacote "borda e limites" (**✅ todos corrigidos 19/07/2026**):
   `iss`/`aud` + throttle de entrada, revogação de sessão em qualquer caminho, TLS no banco
   configurável, knobs documentados, e-mail do backend voltando a sair e **camada 2** (limite de saída
   por fornecedor, que protege cota de terceiro e dinheiro).
5. **D23** — limite por **tenant** (camada 1) (**✅ corrigido 19/07/2026**): eixo por empresa somado aos
   de IP e usuário, teto de usuário derivado do teto da empresa e `limit_req` geral de `/api/` no
   gateway. Restam da área só a **camada 3** (**D24**, cota por plano — anda junto do paywall).
6. O restante por severidade, aproveitando as fases do [roadmap](roadmap.md) indicadas.

---

## 🔴 Críticos

### S1 — Vazamento entre tenants (dashboard ERP + views de NF) · ✅ corrigido 04/07/2026 (pontual)

`ERPDashboardView`, `AtualizarStatusNFView` e `ConsultarStatusNFView` eram `APIView` puras — não
usavam o `TenantScopedViewSetMixin`, logo **não filtravam por tenant nem armavam a RLS**. O
dashboard somava valores de **todos** os tenants; as views de NF liam/gravavam NF de qualquer
tenant por `id`.
**Correção (pontual):** novo `TenantScopedAPIViewMixin` em [nucleo/tenancy.py](../backend/nucleo/tenancy.py)
— arma a RLS em `initial()` e expõe `scope_qs()`; as três views herdam e escopam cada queryset →
cross-tenant some do somatório do dashboard e vira 404 nas NF. Vale em SQLite e Postgres. Testes:
`moduloerp/tests.py::S1TenantIsolationAPIViewTests` (3).
**Parte estrutural (S2) resolvida em 04/07/2026** — ver abaixo.

### S2 — RLS fail-open · ✅ corrigido 04/07/2026 · Fase 8.4

A política RLS (`nucleo/migrations/0007`) **liberava todas as linhas** quando `app.current_tenant`
não estava setado — e só o mixin o setava. Qualquer caminho fora dele (APIView, comando, shell,
task, webhook) rodava sem proteção, silenciosamente.
**Correção (entregue):** (a) contexto armado na **classe de autenticação** (`IamJWTAuthentication`),
não em middleware — o tenant vem do JWT resolvido em `initial()`, dentro da transação do
`ATOMIC_REQUESTS`; um middleware Django clássico veria `AnonymousUser` e rodaria fora da transação.
Assim **toda** requisição autenticada arma o contexto, mesmo views que não herdam o mixin (a brecha
do S1). (b) política **fail-closed** (`nucleo/migrations/0011`): sem contexto → 0 linhas; só passa
quem bate o `tenant_id` **ou** liga o bypass explícito `app.rls_bypass='on'` (superusuário/webhook/
migração/job, via `arm_rls_bypass()`/`rls_bypass()`). O role `erp_app` não é superuser nem BYPASSRLS
e as tabelas estão em `FORCE ROW LEVEL SECURITY`, então a política vale de fato; migrações/jobs
cruzam tenants sob o role `postgres` (BYPASSRLS) ou `rls_bypass()`. Webhook do Asaas e o comando
`analisar_divergencias_asaas` ajustados para armar o contexto. **Provado em Postgres**: sessão sem
contexto vê/insere 0 linhas; tenant A não enxerga B; bypass vê tudo (`nucleo/test_rls_fail_closed.py`,
pulado no SQLite). **Resta da Fase 8:** rodar a suíte inteira sobre Postgres (8.1 — hoje muitos
testes criam linhas via ORM sem contexto e quebrariam sob fail-closed), `tenant` NOT NULL (8.2) e
uniques por-tenant (8.3).

### S10 — Vazamento entre tenants nas filhas do drone · ✅ corrigido 04/07/2026 · Fase 8.5

No funcoesODM (Java), os recursos-filhos sob `/api/v1/projects/{projectId}/...` eram escopados
**só por `projectId`**: os serviços carregavam o projeto por `findById` **sem conferir o tenant**
(`MeasurementService`/`AnnotationService.validateProject` só checavam existência, e os controllers
não tinham guard). Um usuário do tenant A que passasse o `projectId` do tenant B **lia e gravava**
medições/anotações/chunks/tasks daquele projeto. As entidades-filhas também não tinham coluna de
tenant (isolamento apenas transitivo).
**Correção (Fase 8.5):** `tenant_id` **NOT NULL** nas 6 filhas (herdado do projeto na criação) +
`ProjectTenantInterceptor` na borda — todo `/api/v1/projects/{projectId}/**` exige que o projeto da
URL pertença ao tenant do token, senão **404** (não vaza existência). Endurece de quebra o
`update`/`delete` do próprio projeto (antes só o dono por username) e barra anexo de imagem
cross-projeto em `addImagesToChunk`. Provado por [phase8_tenancy_test.py](../infra/gateway/phase8_tenancy_test.py)
(2º tenant `acme` no seed). **Correlato revisado em 10.8 (15/07/2026):** `/api/v1/chunks/*/assets/*` segue
`permitAll` (download público por UUID) **por desenho** — o visualizador Potree/GeoTIFF carrega os assets por
URL simples, sem header de auth; o UUID opaco é a proteção. Mantido; endurecer exigiria token de asset
assinado (fora de escopo).

### S3 — Fallback HS256 com segredo compartilhado · ✅ corrigido 12/07/2026

Sem `JWT_PUBLIC_KEY_PATH`, IAM e backend caíam em HS256 com o mesmo `JWT_SECRET` — quem valida também
**assina**: qualquer serviço (ou `.env` vazado) forjava tokens de qualquer usuário/tenant.
**Corrigido (12/07):** fora de DEBUG o backend **exige** RS256 (`JWT_PUBLIC_KEY_PATH`) e a IAM exige a
privada (`JWT_PRIVATE_KEY_PATH`) — chave ausente → `ImproperlyConfigured` no boot; HS256 só com
`DEBUG=True`. Provado: prod sem chave não sobe; com chave sobe em `RS256`. **Gate no CI (14/07):** o job
backend roda `check --deploy` em modo produção (RS256 efêmera). **Resta (Fase 10):** validação via
JWKS + `kid` (rotação sem redeploy).

### S4 — Defaults inseguros ligados por omissão · ✅ corrigido 12/07/2026

`DEBUG=True`, `SECRET_KEY` e `JWT_SECRET` tinham fallback embutido (backend e IAM): produção sem as
variáveis **subia silenciosamente** com stack traces expostos e segredos conhecidos.
**Corrigido (12/07):** `DEBUG`/`IAM_DEBUG` default = **False**; helper `_config` **falha-rápido**
(`ImproperlyConfigured`) se `SECRET_KEY`/`ALLOWED_HOSTS` faltarem fora de DEBUG (o `JWT_SECRET` só vive
no ramo HS256/dev, coberto pelo S3); bloco de produção liga `SESSION/CSRF_COOKIE_SECURE`, HSTS e
`nosniff` (`SECURE_PROXY_SSL_HEADER` atrás do gateway). **Corrigido (14/07):** `manage.py check --deploy`
é gate no CI (job backend, modo produção + RS256 efêmera, `--fail-level WARNING`; só `security.W008`/SSL-redirect
silenciado — TLS no gateway).

### L1 — Calendário 500 em toda listagem · ✅ corrigido 03/07/2026

`modulocalendar/views.py` filtra `DiarioObra.objects.filter(usuario=...)` — o campo real é
**`criado_por`** → `FieldError` → todo `GET /api/calendar/events/` responde 500. Adjacentes: os
eventos locais são serializados **sem `id`** (impossível editar/excluir no front) e os feriados
só do ano de `start` (range dez→jan perde o ano seguinte).
**Correção:** `criado_por=request.user`; incluir `id` no `values()`; iterar
`range(start.year, end.year+1)` nos feriados; adicionar o smoke test de 1 linha que pegaria isso.

### L2 — Dead Letter Queue nunca grava · ✅ corrigido 03/07/2026

Dois defeitos: `FailedTask.task_id` é `PositiveIntegerField` mas o id do Celery é **UUID string**
(o create sempre falha e o `except` engole); e o hook é registrado como
`on_failure=handle_failed_task.s()`, assinatura incompatível com o protocolo do Celery. Falha
permanente (ex.: cobrança Asaas que esgotou retries) desaparece sem rastro.
**Correção:** `task_id = CharField(max_length=36, unique=True)`; registrar via
`link_error=handle_failed_task.s()` (assinatura `(request, exc, traceback)`) ou `BaseTask` com
`on_failure`; teste que força falha e verifica a linha na DLQ.

### L3 — NF emitida sem tenant e sem documento do tomador · ✅ corrigido 03/07/2026

`_emitir_nf_para_conta_receber` cria a NF **sem `tenant`** (nasce `NULL` e some das listagens
escopadas) e monta o payload com `getattr(cliente, 'cpf'/'cnpj', '')` — campos que não existem
(o real é **`cpf_cnpj`**) → documento sempre vazio; endereço vai sem cidade/UF/CEP.
**Correção:** `tenant=conta.tenant` no create; usar `cliente.cpf_cnpj` + endereço completo.
**Regra geral:** objeto criado fora de `perform_create` herda `tenant` explicitamente do pai.

### L4 — Integração `funcoeslead` ↔ backend morta · ✅ corrigido 03/07/2026 (Fase 11.2 antecipada)

O serviço Node autentica com `Authorization: Token …`; desde a Fase 6 o backend só aceita **JWT da
IAM** → tudo recebe 401. Agravante: os ViewSets do CRM não configuram `filter_backends`, então os
filtros da agenda (`assigned_to_id`, `due_date__gte`…) seriam ignorados mesmo autenticado.
**Correção recomendada:** antecipar a **Fase 11.2** (conversão de lead vira signal handler Python
em `modulocrm` — o problema desaparece por construção). Alternativa de curto prazo: JWT de serviço
emitido pela IAM + `DjangoFilterBackend`/`filterset_fields` no `InteractionViewSet`.

### D1 — Callbacks Node→backend usam o Token morto · ✅ corrigido 16/07/2026 (IA 14/07 + WhatsApp 15/07 + NF 16/07 absorvidos) · Fase 11

`funcoesia` (`services/apiService.js`), `funcoesnf` (`config.js`) e `funcoeswhatsapp`
(`services/apiClient.js`) usam o `DJANGO_API_TOKEN` legado — análise de IA, atualização de status
de NF e o bot recebem 401. **Confirmado por teste** (`nucleo/test_legacy_token.py`): todos os
endpoints-alvo exigem JWT da IAM e respondem 401 ao header `Token` (o `/api/log-interno/` também,
então nem o log central recebe os eventos). O `funcoeslead` saiu da lista: absorvido (L4).
**Correção:** Fase 11 (absorção em Python, caminho preferido) ou JWT de serviço (Fase 10.8).
**Progresso (14/07/2026 — Fase 11.3):** o **`funcoesia`** foi absorvido — a análise de IA virou a Celery
task Python `analisar_documento_ia` (lê a imagem in-process e chama a LLM local; não há mais callback
Node→backend com `Token`). **Progresso (15/07/2026 — Fase C.0–C.3):** o **`funcoeswhatsapp`** foi
absorvido — app Django `funcoeswhatsapp` com webhook (HMAC da Meta) + Celery, escrevendo **in-process**
(sem `Token`, sem auto-HTTP): fluxos diário/lead pelo ORM sob `tenant_context`. **O servidor Node do
WhatsApp foi removido (fatia C.4, 15/07/2026)** — sem resíduo Node no `grep`. **E2E validado 15/07/2026**
pelo gateway ([phaseC_whatsapp_test.py](../infra/gateway/phaseC_whatsapp_test.py), 13/13). **Progresso
(16/07/2026 — Fase 11.1):** o **`funcoesnf`** foi absorvido — emissão/consulta de NFS-e viraram Celery
tasks Python ([moduloerp.tasks](../backend/moduloerp/tasks.py)) que falam REST direto com a NFE.io
([nfe_client.py](../backend/moduloerp/nfe_client.py)); as views não chamam mais `localhost:3003` e o Node +
bridge PHP foram removidos. **Sem callback `Token` restante** → D1 fechado. **Falta:** só credencial NFE.io
real + E2E no stack vivo (validação sob demanda).

### D2 — Boleto Asaas emitido no cliente errado · ✅ corrigido 04/07/2026

Relatado por usuário: criou um `Cliente` novo e ao gerar cobrança o boleto saiu no nome de um
cadastro **pré-existente** no Asaas ("EEGM"), não no cliente do sistema ("Edison Goes").
Duas causas em `funcoescobrancas`: (a) `client.buscar_customer_por_cpf_cnpj` com documento vazio
fazia `GET /customers?cpfCnpj=` → o Asaas ignora o filtro vazio, devolve a **conta inteira** e o
código adotava `dados[0]`; (b) `garantir_customer_asaas` reusava qualquer customer com o mesmo
CPF/CNPJ **sem conferir o nome** e confiava cegamente no `id_cliente_gateway` salvo (já contaminado).
**Correção:** trava de identidade — nunca emitir para cadastro cujo **nome + CPF/CNPJ** não bata
com o cliente. `buscar_customer_por_cpf_cnpj` retorna `None` sem documento e confere o `cpfCnpj`
do candidato; nova `validar_cliente_para_cobranca` (leitura pura) roda **síncrona na view**
(`gerar-cobranca` → `409` com mensagem ao usuário, sem enfileirar) e também dentro de
`garantir_customer_asaas`; CPF igual + nome diferente vira bloqueio (provável digitação, comparação
tolerante a acento/caixa/espaço); `tasks.criar_cobranca` trata `CobrancaBloqueada` como falha
permanente (sem retry, registrada na DLQ); UI destaca o motivo no Sheet da conta. Testes:
`funcoescobrancas/tests.py` (12). Ver [modulos/funcoescobrancas.md](modulos/funcoescobrancas.md#trava-de-identidade--nunca-emitir-para-cadastro-divergente).

## 🟠 Altas

### D3 — UI e dashboards do ERP não sincronizam estado após criação/baixa · ✅ corrigido 13/07/2026

Ao criar um `Cliente`, ele não entra imediatamente no fluxo de cobrança até recarregar a página (browser);
ao gerar boleto, as divergências/pêndencias entre Asaas e banco/ERP não aparecem da mesma forma quando coloco em criar cliente;
os gráficos de custos e recebimentos do ERP não carregam ou ficam defasados; e, após clicar em
dar baixa, o boleto continua sendo exibido como `emitido` como se a mudança não tivesse sido
aplicada.
**Corrigido (12/07/2026):** (a) **boleto preso em `emitido` após baixa** era comportamento do backend —
só o handler do webhook Asaas marcava o boleto `PAGO`; a baixa **manual** não propagava. `ContaReceber.dar_baixa`
(choke point único) passou a marcar os boletos vinculados como `PAGO` quando o título fica `QUITADO`
(estados terminais `PAGO`/`CANCELADO` preservados) — `moduloerp/tests.py::D3BaixaPropagaBoletoTests` (3).
(b) o invalidador de contas a receber no front (`useContasAReceber`) passou a invalidar também `boletos.all`,
para o badge do boleto atualizar sem refresh. (c) **cliente novo não entrava na cobrança** — os selects de
entidade do ERP (`useEntityOptions`) cacheavam por 5 min e os cadastros vivem em outro módulo (não
invalidam esse cache); agora revalidam no mount (`refetchOnMount: 'always'`).
(d) **gráficos "não carregam"** — o hub `/api/erp/dashboard/` exige `erp.relatorio.view`, permissão que só
existia em `diretoria`/`financeiro`/`auditor`; personas com o módulo ERP mas sem ela (`tesouraria`, `fiscal`)
recebiam **403** → KPIs vazios + gráficos sem dados. `erp.relatorio.view` concedido a `tesouraria`/`fiscal`
no catálogo ([iam/identity/catalog.py](../iam/identity/catalog.py); `sync_authz` aditivo propaga no boot).
Admin de tenant já passava (bypass do `RequirePermission`). Testes: `moduloerp/tests.py::D3DashboardPermissionTests` (3)

+ `identity/tests.py::…relatorio_financeiro_visivel_aos_papeis_de_dinheiro`.
  (e) **rótulo do mês** do fluxo de caixa vinha como timestamp ISO cru (`TruncMonth` sem serializer) — o front
  passou a formatá-lo como `jul/2026` (`mesToBR` em [utils/dates.ts](../frontend/src/utils/dates.ts)).
  (f) **divergências Asaas × ERP inconsistentes entre as telas** — ao criar cliente havia um painel proativo
  (lista global banco × Asaas), mas ao **gerar boleto** o bloqueio só surgia reativo (409) depois do clique.
  Padronizado: o botão "Gerar cobrança" abre um **dialog de confirmação** ([GerarCobrancaDialog](../frontend/src/modules/erp/components/GerarCobrancaDialog.tsx))
  com opção de **ver as divergências** (mesmo painel, agora componente compartilhado
  [DivergenciasAsaasPanel](../frontend/src/modules/clientes/components/DivergenciasAsaasPanel.tsx)); confirmação
  dispara a cobrança (o 409 de bloqueio segue valendo). **Falha silenciosa corrigida:** quando a auditoria não
  roda (Asaas fora/sem permissão), as duas telas avisam "não foi possível verificar agora" em vez de painel
  vazio (falso "tudo certo"). **LGPD:** o relatório expunha CPF/CNPJ em texto puro fora do mascaramento 9.C —
  agora `divergencias-asaas` mascara o documento para quem não tem `cadastro.cliente_doc.view`
  ([nucleo/field_masking.mask_document_unless](../backend/nucleo/field_masking.py)). Testes:
  `funcoescobrancas/tests.py::AnalisarDivergenciasTests` (máscara com/sem permissão).
  **Fechado (13/07/2026, junto do F4):** a degradação amigável do hub para quem não tem `erp.relatorio.view` — o
  `ErpDashboardPage` detecta o **403** e vela só os indicadores consolidados (aviso âmbar, permissão nomeada),
  mantendo os atalhos de workspace; o banner de erro vermelho cru sobrou só para falhas reais de carga.
  **Correção de escopo (13/07/2026):** o painel de divergências banco × Asaas foi **removido do formulário Novo
  Cliente** ([ClienteForm](../frontend/src/modules/clientes/components/ClienteForm.tsx)) — o cadastro-base é
  escopo de dados pessoais, não de cobrança. A auditoria de divergências é escopo financeiro (ERP): passou a viver
  (a) sob demanda no [GerarCobrancaDialog](../frontend/src/modules/erp/components/GerarCobrancaDialog.tsx) na hora de
  emitir, e (b) num **botão-alerta permanente no hub do ERP**
  ([DivergenciasErpButton](../frontend/src/modules/erp/components/DivergenciasErpButton.tsx)) — colorido como alerta
  com a contagem quando há divergências, abrindo um modal com os dados (mesmo `DivergenciasAsaasPanel`). **Gate LGPD +
  escopo:** é dado financeiro com PII de cliente, então exige as DUAS permissões de **usuário** — `erp.cobranca.view`
  (ver cobranças) **e** `cadastro.cliente.view` (acesso aos clientes); `hasModule` **não** basta (é entitlement do
  tenant, não do usuário — um `operacional` num tenant com ERP não deve ver). Reforçado no **backend**
  ([clientes/views.py::divergencias_asaas](../backend/clientes/views.py)): checagem explícita de `erp.cobranca.view`
  além do `cadastro.cliente.view` do viewset; regressão em `funcoescobrancas/tests.py` (operacional → 403). O
  documento segue mascarado sem `cadastro.cliente_doc.view`. Isso reverte, de propósito, a duplicação do item (f).

### S5 — Bypass de entitlement no CRM · ✅ corrigido 04/07/2026 · Fase 9.B

`OpportunityProductViewSet` só tinha `IsAuthenticated` — tenant sem o módulo `crm` acessava
`/api/crm/opportunity-products/`. **Correção:** o viewset ganhou `RequireModule("crm")` +
`RequirePermission` (`required_resource="crm.oportunidade_produto"`); os demais viewsets do CRM já
herdavam de `BaseCrmViewSet` (agora com `RequireModule`+`RequirePermission`). Testes em
[modulocrm/tests.py](../backend/modulocrm/tests.py)::`S5EntitlementCrmTests` (sem módulo→403; com
módulo sem permissão→403; com permissão→200) — validados na lógica; execução DRF aguarda o Postgres.

### S6 — Rotas do `funcoeslead` sem autenticação · ✅ resolvido 03/07/2026 (serviço descomissionado — absorvido na Fase 11.2)

O serviço tem o middleware `iamAuth` mas **não o aplica**; quem alcança a porta 3004 executa
ações com o token de serviço. **Correção:** aplicar `requireModule('crm')` nas rotas; rede Docker
interna sem porta publicada; segredo dedicado por serviço nas chamadas internas.

### S7 — Segredos de serviço fracos · ✅ corrigido 14/07/2026

`IA_SERVICE_SECRET_TOKEN` tinha fallback público no código; o token do webhook Asaas era comparado
com `!=` (não constante). **Corrigido (14/07):** `IA_SERVICE_SECRET_TOKEN` passou pelo `_config`
(fail-fast fora de DEBUG, sem fallback público — o valor de dev nunca vale como segredo real) e os
4 usos em [funcoesia/views.py](../backend/funcoesia/views.py) leem `settings.IA_SERVICE_SECRET_TOKEN`
direto (sem `getattr` com default que ressuscitasse o token público); webhook Asaas
([funcoescobrancas/views.py](../backend/funcoescobrancas/views.py)) agora usa `hmac.compare_digest`
(tempo constante) e segue fail-closed sem token configurado. Passthrough da var no `docker-compose.yml`
(erp/worker/beat) e no gate `check --deploy` do CI; documentada no `.env.example`. Testes
`funcoescobrancas/tests.py::WebhookAsaasTokenTests` (4).

### L5 — Corrida na baixa (sem lock de linha) · ✅ corrigido 12/07/2026 *(v01-B3)*

`dar_baixa` fazia read-modify-write sem `select_for_update`, com dois produtores reais concorrentes
(baixa manual × webhook Asaas) — um sobrescrevia o `valor_pago` do outro.
**Corrigido (12/07):** ambos os `dar_baixa` (`ContaPagar`/`ContaReceber`) passaram a rodar dentro de
`transaction.atomic()` travando a linha do título (`select_for_update().get(pk=...)` + `refresh_from_db()`)
antes do read-modify-write; efetivo no Postgres (no-op no SQLite, que não é mais suportado). Prova de
consistência em `moduloerp/tests.py::IntegridadeFinanceiraBaixaTests` (baixas sequenciais acumulam).

### L6 — Edição de título não revalida consistência · ✅ corrigido 12/07/2026

`PATCH` podia reduzir `valor` abaixo de `valor_pago` (saldo negativo); rateios existentes não eram
revalidados quando só o `valor` mudava; a baixa aceitava valor **maior** que o saldo.
**Corrigido (12/07):** `_validar_edicao_valor` nos serializers de `ContaPagar`/`ContaReceber`
(novo total devido ≥ `valor_pago`; se o valor muda sem reenviar rateios, os existentes têm de
continuar fechando) e guard de **overpay** no `dar_baixa` — baixa que excede o saldo é represada em
`RevisaoBaixa` (mesma filosofia do guard de título já quitado/cancelado), não aplicada. Testes cobrem
os três casos (saldo negativo, rateio quebrado, baixa em excesso → 202).

### L7 — `Transacao.data_transacao = auto_now_add` · ✅ corrigido 12/07/2026 *(v01-B5)*

A data real do pagamento (inclusive a do webhook Asaas) não ia para o ledger → fluxo de caixa mensal
no mês errado. **Corrigido (12/07):** `Transacao.data_transacao` deixou de ser `auto_now_add` e virou
a data de **competência** (`default=timezone.now`), gravada por `dar_baixa` a partir da data da baixa
(`_data_baixa_para_datetime`); o carimbo imutável de lançamento no sistema migrou para o novo campo
`data_lancamento` (`auto_now_add`). Migration `moduloerp/0011`. Teste confirma competência = data do
pagamento, não "hoje".

### A1 — Celery sem executor no deploy · ✅ corrigido 12/07/2026 · Fase 10

O compose não tinha serviços `worker`/`beat` — em produção as tasks enfileirariam para sempre.
**Corrigido (12/07):** serviços `worker` (`celery -A config worker`, com healthcheck `inspect ping`)
e `beat` (`celery -A config beat`, dispara o `CELERY_BEAT_SCHEDULE` — hoje o lembrete de tarefas do
CRM) adicionados ao `docker-compose.yml` (perfil `full`), reusando a imagem do backend. A stack `full`
passou a rodar **assíncrona de verdade**: `CELERY_TASK_ALWAYS_EAGER=False` por padrão no `erp`/`worker`/
`beat` (antes o `erp` rodava eager por `DEBUG=True` e o worker ficaria ocioso). Validação E2E do fluxo
enfileirado depende de subir o compose (Docker).

### A2 — Microsserviços fora do compose + URLs fixas · ✅ corrigido 16/07/2026 · Fase 11 *(v01-B4)*

`funcoesnf`/`funcoeswhatsapp` não estavam no `docker-compose.yml` e o backend os chamava em
`localhost:300x` fixo (o `funcoeslead` foi absorvido — Fase 11.2). **`funcoeswhatsapp`** foi absorvido como
app Django (Fase C.0–C.4, 15/07/2026) — webhook vira rota do backend + worker Celery; Node removido.
**`funcoesnf`** foi absorvido (Fase 11.1, 16/07/2026) — emissão/consulta de NFS-e viraram Celery tasks que
chamam a NFE.io direto ([nfe_client.py](../backend/moduloerp/nfe_client.py)); sem `localhost:3003`, Node +
bridge PHP removidos. Nenhum microsserviço Node com URL fixa restante no backend → A2 fechado (o worker de
`funcoesia` já era in-process). **Fase 11.4 concluída 16/07/2026:** diretório Node do `funcoeslead` excluído
e resíduo Node do `funcoesia` limpo — zero `.js` no backend.

### A3 — Uniques por tenant + `tenant` NOT NULL · ✅ corrigido 04/07/2026 · Fase 8.2/8.3 *(v01-B1/B6)*

Unicidade global (CPF/CNPJ, e-mail, nº NF) impedia dois tenants de cadastrarem o mesmo documento e
`tenant` nullable era furo de isolamento. **Corrigido:** `tenant` **NOT NULL** (8.2) + cada
`unique=True` global escalar virou `UniqueConstraint(fields=["tenant", …])` (8.3), com validador DRF
escopado ao tenant (400 limpo em duplicata).

### A4 — Upload sem validação server-side · ✅ corrigido 14/07/2026 *(v01-B2)*

Tipo/tamanho só eram validados no cliente — POST direto à API subia arquivo de qualquer tipo/tamanho.
**Corrigido (14/07):** [nucleo/upload_validation.py](../backend/nucleo/upload_validation.py) —
`resolve_upload_config(tenant)` (fonte única compartilhada com o `ConfiguracaoUploadView`, mesma
precedência tenant→global→padrão) + `UploadValidationMixin` que valida tamanho e tipo de todo
FileField/ImageField escrito no serializer (só quando há upload novo; Content-Type genérico cai para
checagem de extensão, não confia só no header). Aplicado aos serializers com upload: `obras`
(DocumentoObra), `clientes` (DocumentoCliente), `modulodiario` (DocumentoDiario), `rh`
(Funcionario/ASO/Documento/Folha), `empreendimentos` (CustoEmpreendimento). Testes
`nucleo/test_upload_validation.py` (6).

### D3 — `tenant` obrigatório no POST quebra a criação via API · ✅ corrigido 11/07/2026

Regressão da **Fase 8.2** (`tenant` virou NOT NULL): o DRF passou a **exigir `tenant` no payload**,
mas o `perform_create` do `TenantScopedViewSetMixin` injeta o tenant **depois** do `is_valid()` → todo
`POST` de recurso tenant-scoped cujo serializer usa `fields='__all__'` **sem** `read_only_fields=['tenant']`
responde **400 "tenant é obrigatório"** (o front não envia tenant). Descoberto ao criar cargo/funcionário.
**Corrigido (11/07):** serializer-base `TenantReadOnlyFieldMixin` em
[nucleo/tenant_validators.py](../backend/nucleo/tenant_validators.py) — força `tenant` read-only quando
exposto (no-op se o modelo não tem `tenant`); dobrado dentro do `TenantScopedUniqueSerializerMixin`
(todo serializer que já o usava ficou coberto de graça) e exposto como base pronta
`TenantScopedModelSerializer`. Varredura sistêmica concluída: `read_only_fields=['tenant']` nos
serializers `__all__` remanescentes de **moduloerp** (Boleto/Transacao/CobrancaCliente), **empreendimentos**
(ContaBancaria), **obras** (Obra/Etapa/Documento), **modulocrm** (Interaction/OpportunityProduct/
Opportunity/Contact), **modulocalendar**, **moduloapi** e **funcoesia** (RH/clientes/fornecedores já tinham).

### D4 — `RequirePermission` é fail-open com `permissions` vazia · ✅ corrigido 11/07/2026

Como a autenticação sempre setava `iam_permissions = [...] or []`, não havia como distinguir "token legado
sem a claim" de "usuário sem nenhuma permissão" — e o fallback de transição (`permissions` vazia → cai
no `RequireRole`) **liberava** quem não tem papel exigido em endpoints sem `required_role`.
**Corrigido (11/07):** a autenticação passou a distinguir claim **ausente** → `iam_permissions = None`
(token legado → fallback por papel, zero-downtime) de claim **presente porém vazia** → `[]` (era das
permissões → checagem estrita, conjunto vazio **nega**). `RequirePermission` só cai no `RequireRole` quando
`iam_permissions is None` ([nucleo/permissions.py](../backend/nucleo/permissions.py),
[nucleo/authentication.py](../backend/nucleo/authentication.py)). Fecha o fail-open sem quebrar o fallback
legado (provado: `S5EntitlementCrmTests`, `RequirePermissionRHTests`). O `RequireRole` some de vez na fatia **E**.

### D5 — Cadastros-base sem camada 2 (broken access control) · ✅ corrigido 11/07/2026

Relatado por teste do usuário: `semdrone` (papel **operacional**, só `cadastro.cliente.view`)
**criou e editou clientes e criou uma "venda"** (`ClienteEmpreendimento`) — só não viu o CPF (mascarado
pela 9.C). Causa: a **fatia B** (`RequirePermission`) só fora aplicada a **RH e CRM**; os cadastros-base
(`clientes`, `fornecedores`, `obras`, `empreendimentos`) tinham apenas `IsAuthenticated` → qualquer papel
escrevia. O mascaramento de campo protege o **campo**, não a **operação** de escrita.
**Corrigido (05/07):** `RequirePermission` + `required_resource` em todos os viewsets de `clientes`
(`cadastro.cliente`/`cadastro.cliente_banco`), `fornecedores`, `obras` (`obra.obra`) e `empreendimentos`
(`obra.empreendimento`/`empreend_conta`/`empreend_custo`). Provado: `semdrone` vê (200) mas não escreve
(403); `demo` (comercial/engenharia) cria normalmente. `modulodiario` já tinha ABAC próprio
(`PodeModerarDiario`). **Concluído (11/07):** a fatia B foi fechada em todo o backend —
`moduloerp` migrou de `RequireRole("financeiro")` para `RequirePermission` nos 14 viewsets/APIViews,
com os verbos de domínio (baixa, cobrança, emissão de NF, lote de remessa, resolver revisão) gateados por
permissão específica via novo `action_permission_map` do `RequirePermission`; `modulocalendar`
(`calendario.evento`), `moduloapi` (`plataforma.integracao`) e `funcoesia` (`ia.analise.view`/`.executar`,
inclusive os proxies FBV) ganharam camada 2. Template `financeiro` recebeu `erp.lote_remessa.*`
(órfão no catálogo). Suíte 71/71 verde. **Deploy sem passo manual:** o `sync_authz` ficou **aditivo**
(soma as permissões do modelo aos papéis de fábrica sem apagar ajustes do admin; `--reset` para
realinhamento explícito) e roda `--all-tenants` no boot do IAM (CMD do Dockerfile), propagando o catálogo
e o `lote_remessa` automaticamente. Usuários pegam a permissão nova no próximo **refresh** do token
(tempos vigentes em [acesso-e-permissoes.md §5.2](acesso-e-permissoes.md)).

### D6 — Ampliar dados sensíveis do mascaramento (9.C) a todo o PII · 📋 aberto (fazer depois)

Hoje a 9.C mascara só documento/financeiro/médico/bancário. **Faltam os demais dados pessoais.**
**Prioridade mínima (fazer sempre):** `telefone`, `e-mail` e `nome completo`. **Ideal:** cobrir
**todo o PII** — acrescentar aos `sensitive_fields` dos serializers (sem trava de escrita nova; a
escrita segue o gate do cadastro), com permissão de leitura dedicada por recurso. Campos por modelo:

- **Funcionario:** `nome_completo`, `rg`, `data_nascimento`, `telefone_pessoal`, `telefone_celular`,
  `email_pessoal`, `endereco_completo`, `estado_civil`, `numero_ctps`, `serie_ctps`, `pis_pasep`,
  `carteira_trabalho_*` (CPF/salário já cobertos).
- **Cliente:** `nome_completo`, `email`, `telefone`, `endereco`+`bairro`/`cidade`/`estado`/`cep`,
  `data_nascimento`, `estado_civil`, `profissao` (CPF/CNPJ já coberto).
- **Fornecedor:** `contato`, `email`, `telefone` (CNPJ é público — não mascarar).
- **CRM (`Lead`/`Contact`):** `first_name`, `last_name`, `email`, `phone`.

Decidir a permissão de leitura: reusar `rh.funcionario.view`/`cadastro.cliente.view` (grosso) ou criar
`*.pii.view` dedicada (fino). Requer também estender o **export/anonimização LGPD (9.D)** a esses
campos. **Não implementar agora** — planejado para uma extensão da 9.C.

### D7 — Janela de acesso residual do access token stateless · ✅ corrigido 13/07/2026 (backend+IAM+drone, E2E validado)

Access token é validado só por assinatura+`exp`. Após trocar/resetar senha ou desativar um usuário,
o access **já emitido continuava válido até expirar** — blacklistar o refresh só impede a *renovação*.
Reprodução: senha do `demo` trocada, sessão seguiu ativa (inclusive **gravou** conta a pagar) até o F5.
**Correção:** access TTL 15→**5 min** + **revogação imediata por época no Redis** — a IAM carimba
`sess:revoked_after:<uid>` (DB 2) em troca/reset de senha e desativação; o `IamJWTAuthentication` do backend
rejeita access com `iat` anterior (fail-open + circuit breaker se o Redis cair). Desenho e trade-offs:
[acesso-e-permissoes.md §5.1](acesso-e-permissoes.md). **E2E backend+IAM validado 13/07/2026** (revogação
imediata ~40 ms; fail-open permite / fail-closed nega; carimbo sobrevive a restart com AOF). **Drone
replicado 13/07/2026** (`SessionRevocationService` no `JwtAuthenticationFilter`, mesmo Redis/DB2/chave,
fail-open + breaker, testes de decisão 7/7). Os 3 Node ficam para a Fase 11 (sem rota de usuário na
borda). **E2E do drone validado no stack vivo** (imagem Java rebuildada): token com módulo drone → 200;
carimbo no Redis DB2 → mesmo token **401**; relogin (iat>carimbo) → 200. **Falta:** nada — D7 fechado.

### F1 — Sessão expira sem refresh + sem 401 global · ✅ corrigido 11/07/2026 (junto da Fase 10.6)

O access token valia 60 min e o front não usava o refresh; 401 não deslogava nem redirecionava.
**Corrigido (11/07):** ciclo de sessão completo (ver **Fase 10.6** no roadmap) — access token
**em memória** + **refresh em cookie HttpOnly** renovado em silêncio; interceptor de resposta
(`attachAuth`) trata 401 → `/auth/refresh/` → retry; refresh **proativo** (~1 min antes de expirar) →
nenhuma requisição falha; bootstrap na carga chama `/auth/refresh/` (cookie) e repopula a sessão sem
relogar. **Validado ao vivo pelo gateway (:8090):** login (cookie 636 B,
sem refresh no corpo) → refresh (rotaciona, access com claims) → reuso do refresh antigo = 401
→ logout = 401. IAM 19/19; React e drone rebuildados e no ar (compilaram limpo). Refresh mínimo (só
`user_id`+`sst`/`rem`) p/ caber no limite de cookie; claims só no access.
*(Os TTLs citados na versão original desta entrada — 15 min / 12h / 30d — eram os de 11/07 e ficaram
defasados; tempos vigentes em [acesso-e-permissoes.md §5.2](acesso-e-permissoes.md).)*

### F5 — `.gitignore` engole `frontend/src/lib/` — o frontend não builda em clone limpo · ✅ corrigido 26/07/2026

A linha 13 do `.gitignore` da raiz (`lib/`, padrão de virtualenv Python) casa também com
**`frontend/src/lib/`**. Os dois arquivos de lá nunca foram commitados: `queryClient.ts` (o
`QueryClient` único do TanStack Query, importado por `main.tsx`) e `utils.ts` (usado pelo diário).
Na máquina de quem escreveu eles existem, então nada acusa; num **clone novo ou worktree** o
`tsc`/`vite build` quebra em `Cannot find module './lib/queryClient'`. Confirmado por
`git check-ignore -v frontend/src/lib/queryClient.ts` → `.gitignore:13:lib/`.
**Corrigido:** `lib/`/`lib64/` **ancorados** na raiz (`/lib/`, `/lib64/` — diretório de build do
Python é sempre da raiz, ancorar não perde nada) e os dois arquivos versionados. Mesma lição já
registrada no bloco "Virtual Environment" do `.gitignore`, que aprendeu isso com o `deploy/env/`:
padrão de diretório sem âncora casa **qualquer nível**. Verificado que a âncora não destapa mais
nada — os outros dois `lib/` da árvore (`ImgDrone/`, worktree do `.claude/`) são ignorados por
regra própria.

### F6 — `package-lock.json` do frontend fora de sincronia · ✅ corrigido 26/07/2026

`npm ci` falha com `EUSAGE`: faltam do lock os 6 pacotes `@fullcalendar/*` (6.1.21) e `preact`, que
estão no `package.json`. Como o gate de CI roda `npm ci` bloqueante (Fase 12), ele não passa.
Há também conflito de peer dep (`@hookform/resolvers` 5.4.3 exige `valibot ^1.0.0`, resolvido para
0.39.0) — hoje só contornável com `--legacy-peer-deps`.
**Corrigido:** lock regenerado (4936 → 5077 linhas, os 6 `@fullcalendar/*` de volta) e `npm ci`
provado limpo — 294 pacotes, **sem** `--legacy-peer-deps`, tanto no Node 20 (versão do CI) quanto no
22 (versão da imagem). Duas partes do achado envelheceram: **`preact`** saiu do `package.json`, e o
conflito de **`valibot`** dissolveu-se quando o projeto passou a usar `zod` (o `@hookform/resolvers`
v5 declara os validadores como peers *opcionais*) — não havia o que decidir.
**A causa raiz era outra, e foi fechada junto:** o `frontend/Dockerfile` rodava
`npm install --legacy-peer-deps`, que **reresolve tudo e ignora o lock**. Por isso o defeito viveu 7
dias sem sintoma — a imagem buildava e só o CI quebrava. Trocado por `npm ci`, que falha quando o
lock divergir; é o que a Fase **10.4.1** já declarava ("`npm ci` + lockfile obrigatório nos
Dockerfiles/CI") e não valia para o frontend. Imagem rebuildada e validada.

### F7 — Rotas de administração sem guard de `is_tenant_admin` · 🔴 aberto

Em [App.tsx](../frontend/src/App.tsx), `admin/papeis` e `admin/usuarios` têm o comentário
"guardado por `is_tenant_admin`", mas **não há guard na rota** — só a sidebar trava o link. URL
digitada direto entra na tela (a API barra depois, mas a UI já montou). O RH, na mesma página, usa
`<ModuleRoute module="rh">` corretamente.
**Correção:** um `<AdminRoute>` irmão do `ModuleRoute`, reusando o `AccessNotice`.

### F8 — Item "Início" travado na sidebar · ✅ corrigido 25/07/2026

`AppSidebar` marcava `implemented: false` no item Início, que virava `<span>` com cadeado — mas
`/app/dashboard` é a rota-índice e a página existia. O usuário aterrissava na home e não conseguia
voltar a ela depois de navegar. **Corrigido** junto da reconstrução do hub (F.1).

### F17 — Vender lote e emitir carnê andavam na permissão de editar cadastro · ✅ corrigido 26/07/2026

Relatado pelo usuário ("falta authorization em AquisicaoForm — qualquer um pode vender lote?").
`ClienteEmpreendimentoViewSet` declarava `required_resource = "cadastro.cliente"`: pelo contrato do
`RequirePermission`, escrita exigia `cadastro.cliente.edit` — **a mesma permissão de corrigir o
telefone de um comprador**. Quem podia editar cadastro podia registrar uma venda (tirando a unidade
da praça) e, como os `@action` não tinham `action_permission_map`, também **gerar o carnê**, criando
`ContaReceber` no ERP. Ato comercial e ato financeiro atrás de uma permissão de cadastro.
**Corrigido:** três permissões novas na IAM (`cadastro.venda.view`/`.edit`/`.gerar_carne`), o viewset
passou a `required_resource = "cadastro.venda"` com `action_permission_map` (`simular` → `.view`,
porque cotar é anterior a fechar; `gerar_parcelas` e `corrigir` → `.gerar_carne`), personas ajustadas
(**comercial** vende mas não emite; **financeiro** emite; tesouraria/diretoria só leem) e a ficha do
cliente passou a gatear os botões por `hasPermission`. `sync_authz --all-tenants` (aditivo) aplicado.
Testes `PermissaoDeVendaTests` (5).

### F18 — Carteira: "Agrupar por" e todos os filtros vazios (endpoint em 500) · ✅ corrigido 26/07/2026

Relatado pelo usuário. `views.py:521` (`CarteiraOpcoesView`) ainda lia
`aquisicoes.values_list('quadra')` — campo que o **F16** moveu de `ClienteEmpreendimento` para
`Unidade`. `FieldError` → `GET /api/clientes/carteira/opcoes/` respondia **500** → `opcoes` ficava
`undefined` no React e `dimensoes = opcoes?.dimensoes[visao] ?? []` esvaziava o painel. Não era só o
agrupamento: empreendimentos, quadras, cidades, UF e anos vinham vazios pela mesma resposta. Todo o
`carteira.py` já havia sido migrado para `unidade__quadra`; só esta linha ficou.
**Corrigido:** `unidade__quadra`. Verificado ao vivo pelo gateway — 200 com os 16 agrupamentos.

### F19 — Condição de pagamento era rótulo decorativo, e vinha depois do plano · ✅ corrigido 26/07/2026

Relatado pelo usuário. No `AquisicaoForm`, **Condições de pagamento** estava na linha 489 — depois de
entrada, parcelas, juros, balões e do painel de simulação inteiro — e **não gateava nada**: vender
"À Vista" ainda pedia sistema de amortização, juros ao mês e prazo. O campo só aparecia em filtro,
admin e display; nenhuma linha de backend o lia para calcular.
**Corrigido:** a condição virou a **primeira** pergunta depois da unidade e passou a reger o
formulário (`PLANO_DA_CONDICAO`: à vista e permuta sem plano; bancário e cartão só com sinal;
direto e outro com tudo), limpando o que a condição anterior deixou. A regra vive no **motor**
(`plano_pagamento.montar(a_vista=…)`), não na tela, para o simulado e o gravado não divergirem — à
vista vira parcela única na data da compra, sem juros nem prazo. Os balões ganharam o nome de
mercado (**parcelas anuais/intercaladas**). Testes `CondicaoDePagamentoTests` (4).

### F20 — "Gerar parcelas" parecia ter gerado a carteira inteira · ✅ sem defeito, apurado 26/07/2026

Relatado pelo usuário ("cliquei em gerar parcelas e parece que gerou de todos os 5000 clientes").
**Não havia defeito:** `gerar_parcelas` é `detail=True`, opera sobre uma aquisição e recusa a segunda
chamada com 409. A apuração nos carimbos de `parcelas_geradas_em` mostrou 2.182 aquisições marcadas
numa rajada de 3 s (10:19:40–42 — o `semear_carteira_demo`, que já gera os carnês da carteira
semeada) e **exatamente uma** às 10:41:14, que foi o clique. As 86.010 `ContaReceber` já existiam
antes. O que enganou foi a mensagem de sucesso mandando "veja na aba Financeiro" sem dizer de qual
venda, com o ERP mostrando 86 mil linhas.
**Ajustado:** a mensagem passou a nomear a unidade, o total daquela venda e a apontar para a aba
Financeiro **do cliente**, não para o financeiro geral.

### F16 — Unidade cadastrada duas vezes na venda, sem trava contra revenda · ✅ corrigido 26/07/2026

O formulário de aquisição pedia **`Unidade comprada`** (texto livre) **e** os cinco campos da
identificação estruturada, lado a lado e independentes: nada garantia que combinassem, e o mesmo
lote entrava como "Apto 101" numa venda e "apto 101" em outra. O `unique(empreendimento,
unidade_comprada)` que deveria impedir revenda não pegava essas duas — e a unidade não tinha preço,
então o valor da compra era digitado do zero a cada venda.
**Corrigido:** a unidade virou **cadastro do empreendimento** (`empreendimentos.Unidade`, com
identificação estruturada única, preço de tabela e situação) e a aquisição só **aponta** para ela
(`unique(tenant, unidade)`); o texto livre e os campos duplicados foram removidos. A venda ganhou
plano de pagamento (desconto → entrada → Price/SAC → balões) calculado no backend, com simulação
sem gravar e geração de carnê por ato explícito. Migration destrutiva, base de dev recriada com
CPF/CNPJ **válidos** (o Asaas sandbox recusa documento com dígito verificador errado, e a base
antiga não emitiria um boleto sequer). Suíte `clientes` 69/69 sobre PG + fumaça ao vivo pelo gateway.

### F15 — Carteira: a visão "Unidades" abria como a de clientes · ✅ corrigido 26/07/2026

O seletor `Clientes × Unidades` trocava o conjunto de colunas, mas não o que a
visão promete. As preferências eram **uma só para as duas** (`sgi_carteira_clientes_v1`):
a primeira coluna continuava `Cliente` em Unidades, a ordem continuava a de nomes, e as
larguras/agrupamento de uma visão vazavam para a outra. Só 5 das 13 colunas eram
ordenáveis (as demais nem existiam em `ORDENACOES`), e `quadra`/`lote` ordenavam como
texto — o lote 10 antes do 2.
**Corrigido:** cada visão é uma planilha própria, com **coluna-âncora** (Cliente / Unidade,
sempre a primeira e congelada), ordem padrão própria (alfabética / endereço) e preferências
por visão (`sgi_carteira_clientes_v2`); **toda coluna ordena**, por clique ou pelo menu
"Ordenar por" do cabeçalho; ordem natural da unidade (quadra › lote › bloco/torre › andar ›
apto, numérica, vazio por último) com bloco/andar/apto virando colunas; ordenar por
documento passou a exigir `cadastro.cliente_doc.view` (a ordem dos CPFs vaza o CPF) e a
resposta declara `podeDocumento`; toda ordenação ganhou desempate por chave primária, sem o
qual a rolagem infinita duplicava e omitia linhas. Testes `CarteiraOrdenacaoTests` (6);
`clientes` 31/31 sobre PG.

### F2 — Selects carregam tabelas inteiras · 🟠 parcial 25/07/2026

Formulários carregam todos os clientes/fornecedores/empreendimentos para montar selects.
**Correção:** select assíncrono com busca server-side paginada (o backend precisa de
`SearchFilter` + paginação nesses endpoints).
**Andamento (25/07):** o SCM já resolveu dentro dele (`AsyncEntitySelect`) e a **listagem de
clientes** deixou de ser client-side — virou a carteira paginada com rolagem infinita
([frontend.md §5.8](frontend.md)). Efeito colateral tratado: como `/api/clientes/` passou a ser
paginado, `useClienteOptions` ([useEntityOptions.ts](../frontend/src/modules/erp/hooks/useEntityOptions.ts))
truncaria a lista em 50 **em silêncio** — pediria a primeira página e o cliente nº 200 sumiria do
formulário do ERP. Mitigado com `page_size=300` e comentário no código. **Falta** o select com busca
server-side de verdade nos formulários (clientes, fornecedores, empreendimentos).

### D8 — Tasks Celery sem contexto de tenant no worker (cobrança Asaas não gerava boleto) · ✅ corrigido 17/07/2026

Relatado pelo usuário: "Gerar cobrança" respondia 202 mas **nenhum boleto** aparecia — nem no Asaas nem
no banco. Causa (confirmada no log do worker): a task `funcoescobrancas.tasks.criar_cobranca` lia
`ContaReceber.objects.get()` **sem armar `rls_bypass`/`tenant_context`**; no worker real (Postgres, RLS
fail-closed, role `erp_app`, sem `app.current_tenant`) a linha some → `DoesNotExist` → a task morre na DLQ
antes de chamar o Asaas ou gravar o `Boleto`. Latente desde que o worker real entrou (Fase 10.9) — em dev
com `CELERY_TASK_ALWAYS_EAGER=True` rodava no request (contexto armado). **Correção:** `criar_cobranca` passou
a resolver o tenant sob `rls_bypass()` e a rodar o trabalho sob `tenant_context(tenant_id)` (mesmo padrão das
tasks de NF e do webhook Asaas). **Varredura:** mesma classe em `modulocrm.tasks.notificar_tarefas_a_vencer`
(job global de lembrete) → envolto em `rls_bypass()` (só não quebrava por ser no-op sem e-mail). `drone_sync`
recebe o `tenant_id` por argumento — ok. Testes: `funcoescobrancas.tests.TaskCriarCobrancaSemContextoTests`
(a task cria o Boleto sem request). **E2E vivo:** gerar-cobranca → worker → **Boleto no banco + boleto no
Asaas sandbox** (com URL).

### D9 — Download de PDF/XML da NFS-e vazio · ✅ corrigido 17/07/2026

Duas causas encadeadas, ao validar a emissão real: (a) a NFE.io **não** devolve `urlPdf`/`urlXml` no corpo do
invoice — os arquivos vêm dos endpoints `/serviceinvoices/{id}/pdf|xml` (302 → blob assinado público);
`nfe_client.resolver_url_arquivo` passou a seguir o 302 (com auth) e `_aplicar_retorno` baixa o blob (idempotente:
só o que falta); `data_emissao` agora vem de `issuedOn`/`createdOn`. (b) o **worker** gravava o arquivo no seu
filesystem efêmero enquanto o **erp** serve `/media/` — sem volume comum → **404**; adicionado
`media_data:/app/media` em erp/worker/beat no `docker-compose.yml`. **E2E vivo:** emitir → EMITIDA → PDF/XML
baixam pelo gateway (200, `application/pdf`/`text/xml`). Nota: a emissão de NFS-e é **assíncrona** na NFE.io
(pode ficar `PROCESSANDO` até uma consulta atribuir o número) — o botão "Consultar" resolve; um poll agendado
das NFs em PROCESSANDO fica como melhoria.

### D10 — Defeitos de modo-produção na 1ª subida greenfield do staging (Fase 10.7) · ✅ corrigido 18/07/2026

Subir o staging pela 1ª vez (DEBUG=False/RS256/TLS/Celery async, banco novo) expôs 7 defeitos que o dev
(DEBUG=True + dados pré-existentes) escondia. Todos corrigidos → `validate.sh` **6/6 verde** + **phase10_8 7/7**.

- **`worker`/`beat` sem `ALLOWED_HOSTS`** ([docker-compose.yml](../docker-compose.yml)): `settings` roda a
  fail-fast de produção no import mesmo sem servir HTTP → **crash-loop** dos dois. Adicionado `ALLOWED_HOSTS`
  aos serviços (só o `erp` tinha).
- **UUID de tenant desalinhado entre os seeds (crítico p/ greenfield):** `iam/seed_demo.py` e
  `backend/seed_demo_data.py` criavam `demo` com UUIDs **independentes**; como
  [`nucleo.authentication._sync_tenant`](../backend/nucleo/authentication.py) espelha o tenant da IAM **por id**
  (JIT), o 1º login não achava o tenant → tentava criar `slug='demo'` → **UniqueViolation → 500 em todo `/api/*`**.
  Os dois seeds passaram a derivar o id por `uuid5` do mesmo nome (demo/acme alinhados IAM×backend). Em produção
  real não há seed (JIT alinha sozinho); dev só funcionava por alinhamento histórico.
- **Parse do gate (`validate.sh`/`up.sh`):** (a) o guard `grep 'TROQUE-'` batia no comentário do cabeçalho do
  `.env.staging`; (b) `cut -d= -f2` colava o comentário inline do `GATEWAY_HTTPS_PORT` no `SGI_GW` → o `#` virava
  fragmento e **todo request caía no SPA do React** (405/200, login "FALHOU"). Corrigidos (`=TROQUE-`; extrair só o número).
- **phaseC com container de dev fixo** (`ERP_CONTAINER="sgi-erp"`): as checagens no ORM liam o banco de **dev**
  enquanto o webhook escrevia no de **staging** → `Lead count=0`. Tornado configurável (`SGI_ERP_CONTAINER`,
  exportado pelo `validate.sh` a partir do `SGI_PREFIX`).
- **rate-limit do login** (`10r/m burst=5` no gateway) estourava ao rodar os 6 E2E em sequência → **429**;
  `validate.sh` passou a espaçar as corridas (mantém o limite de produção intacto — pausa só o harness).
- **`phase10_8` com `Origin` de dev fixo** (`http://localhost:8090`): o drone recusa o handshake com **403
  antes do upgrade** quando a origem não está em `APP_CORS_ALLOWED_ORIGINS` — no staging a origem é a do
  gateway HTTPS. Tornado configurável (`SGI_WS_ORIGIN`). Com isso o 10.8 fecha **7/7** no staging (WS rodado
  de dentro da rede contra `java-service:8080`, que é onde mora a checagem do CONNECT).
- **Cosmético:** `down.sh -v` imprime "volumes persistem" mesmo tendo removido; `POSTGRES_SUPbackendASSWORD`
  (nome corrompido por rename `erp`→`backend`) é consistente entre `.env`/compose, então funciona.

### D11 — Admin não consegue resetar senha esquecida (e não há recuperação) · ✅ corrigido 18/07/2026

`redefinir-senha` exigia a senha ATUAL do alvo — justamente o que o usuário não tem quando esquece —
e não existia "esqueci minha senha", então **quem esquecia a senha ficava travado sem saída**.

**Decisão de desenho (18/07):** descartada a opção "admin redefine sem conhecer senha alguma"
(padrão de mercado — Okta/Entra/Workspace — mas rejeitada aqui por dar takeover de qualquer conta a
um admin comprometido). Caminho adotado: **recuperação por token de e-mail**.

**Achado durante a implementação — a recuperação por e-mail sozinha só MOVE o buraco.** `email` era
campo gravável no `UsuarioSerializer` sob `IsTenantAdmin`: um admin socialmente engenheirado faria
`PATCH {"email": "atacante@evil.com"}` → "esqueci minha senha" → token na própria caixa. Takeover
idêntico ao que a decisão acima quis evitar, e **pior de detectar**, porque o rastro pareceria uma
recuperação legítima feita pelo próprio usuário. Por isso a entrega inclui as travas de troca de e-mail.

**Entregue — um caminho só:**

- **Recuperação** (`POST /auth/senha/esqueci/`, público, botão na tela de login): token de uso único
  (SHA-256 no banco, claro só no e-mail), TTL 30 min, emissão nova invalida a anterior, teto de 5/hora
  por conta. Resposta **sempre genérica** (conta inexistente/inativa/em cooldown/no teto devolvem o
  mesmo corpo e status) → sem oráculo de enumeração. Consumo em `POST /auth/senha/redefinir/` encerra
  todas as sessões (`revoke_all_sessions` + `bump_session_epoch`).
- **Admin recebe AVISO, nunca o link.** Os admins do tenant são notificados de que houve o pedido —
  enxergam o que acontece e podem reagir (conta de quem saiu da empresa, rajada de pedidos) — mas não
  recebem o token. *Copiar o link para o admin foi avaliado e recusado:* o endpoint é público e sem
  autenticação, então qualquer anônimo que soubesse um username faria cair um token de takeover na
  caixa do admin, e todo admin teria takeover silencioso de qualquer conta. Supervisão sim, poder não.
- **E-mail obrigatório e único** no `Usuario` (migration `0004`, com guarda que falha com mensagem
  legível se houver vazio/duplicata). Deixou de ser dado de contato e virou infraestrutura: conta sem
  e-mail é conta sem caminho de volta; e-mail repetido torna a recuperação ambígua. Único **global**
  (decisão 18/07: a mesma pessoa não tem conta em duas empresas).
- **Troca de e-mail endurecida e ASSIMÉTRICA:** `email` saiu do PATCH genérico; agora só por
  `POST /iam/usuarios/{id}/trocar-email/`, com regra que depende de **quem é o alvo** — porque neste
  produto o admin **é o dono da empresa** (quem paga), e as contas dos funcionários existem a partir
  dele:

  - **alvo funcionário** → troca vale **na hora**, sem confirmação e **sem cooldown**. Exigir
    confirmação no endereço antigo travaria justamente o caso que motivou o D11 (e-mail digitado
    errado no cadastro, ou caixa que a pessoa não acessa mais: a confirmação iria para um endereço
    morto e ninguém nunca corrigiria). O cooldown também fica de fora de propósito — senão o dono
    corrigiria o endereço e a pessoa ainda ficaria 24 h sem recuperar. Compensações: evento na trilha
    e **aviso nos dois endereços**;
  - **alvo admin** (inclusive o próprio) → **confirma no endereço ANTIGO** e, ao confirmar, arma
    `Usuario.email_alterado_em` → **cooldown de 24 h** sem emissão de token. A conta do dono é o ponto
    único de comprometimento da empresa inteira: quem sequestrar a sessão dele não pode redirecionar
    o e-mail e, com isso, herdar a recuperação de senha de tudo.

  *Histórico: a 1ª versão exigia confirmação para todo mundo. Corrigido em 18/07 ao perceber que isso
  reintroduzia o travamento pela porta dos fundos — proteger o funcionário contra o próprio dono não é
  papel do sistema, já que ele acessa os dados da empresa por direito.*
- **Escalada de privilégio auditada:** mudança de `perfis`/`is_tenant_admin` gera evento e avisa o
  dono da conta por e-mail.
- **Trilha própria da IAM:** `EventoSeguranca` append-only (bloqueio no modelo + **trigger PostgreSQL**
  contra UPDATE/DELETE, FKs congeladas `db_constraint=False`), porque o `AuditLog` da Fase 9.E vive no
  backend e **nenhum evento de identidade era auditado em lugar nenhum** até aqui. Só metadados; e-mails
  mascarados (`e••••n@dominio`).
- **Infra:** IAM ganhou SMTP próprio (`MAIL_HOST` **obrigatório** fora de `IAM_DEBUG` — sem ele a
  recuperação aceitaria a solicitação e nunca entregaria o token) + **Mailpit** no compose (perfil
  `mail`, UI em `:8025`) como caixa de captura de dev/staging, andaime a aposentar antes do go-live.
- **Mantido:** `redefinir-senha` (admin informa a senha ATUAL do alvo) segue existindo para o caso
  presencial — não é primitivo de takeover, quem não sabe a senha do alvo não passa dali.

**Validado 18/07/2026:** suíte da IAM **69/69** + **E2E 17/17 no dev E 17/17 no staging**
(TLS + `DEBUG=False` + Celery async; o roteiro é parametrizável por `SGI_GW`/`SGI_MP`/
`SGI_IAM_CONTAINER` justamente para valer nos dois) — antes só rodava contra o dev, ver achado (d).
Detalhe do que cada corrida cobre, pelo gateway
([d11_recuperacao_senha_test.sh](../infra/gateway/d11_recuperacao_senha_test.sh), com o Mailpit como
caixa): recuperação ponta a ponta, link só na caixa do usuário e **aviso do admin sem `token=`**, uso
único, senha antiga invalidada, resposta idêntica p/ conta inexistente, PATCH não troca e-mail,
confirmação no endereço antigo, criação sem e-mail e e-mail duplicado recusados com **400 (não 500)**.

**Achados durante a implementação:**

- (a) declarar `email` no serializer descartava o `UniqueValidator` que o `ModelSerializer` geraria do
  `unique=True` → duplicata escapava e estourava `IntegrityError` (**500**); validador explícito.
- (b) o teto por hora é silencioso por desenho, então o próprio E2E esgotava a cota do `demo` ao rodar
  repetido — o script zera a cota antes de começar, sem afrouxar o limite real (mesma disciplina do
  espaçamento no `validate.sh`, ver D10). O roteiro também **restaura o ambiente ao final** (trocava a
  senha do `demo` e deixava assim).
- (c) **link morto na tela de login** (relatado pelo usuário: "não faz nada"). O `LoginPage` já tinha
  um `<a href="#">Esqueci minha senha</a>` — placeholder da época sem recuperação — e a nova entrega
  acrescentou um segundo link, vivo, em outro ponto da tela. O usuário clicou no morto. Removido o
  placeholder; sobrou **um** link. *Lição: procurar o texto no código antes de adicionar um elemento
  de UI com o mesmo rótulo (parente do F5 — duas gerações de páginas convivendo).* O E2E via `curl`
  jamais pegaria isso: exercitava a API, não a tela.
- (d) **staging não subiria** (achado antes de quebrar): lá `IAM_DEBUG=False` e o `MAIL_HOST` estava
  **vazio** — com o fail-fast novo, a IAM recusaria o boot em crash-loop. `.env.staging`/`.example`
  passaram a apontar para o Mailpit do staging (portas próprias 8026/1026) e a definir
  `FRONTEND_BASE_URL=https://localhost:8443`; sem isso os links do e-mail apontariam para o **dev**
  (`localhost:8090`) e o usuário do staging cairia no ambiente errado. Mesma família do **D10**.

**UI ✅ 18/07/2026:** link "Esqueci minha senha" na [tela de login](../frontend/src/pages/LoginPage.tsx)

+ três telas públicas ([EsqueciSenhaPage](../frontend/src/pages/EsqueciSenhaPage.tsx),
  [RedefinirSenhaPage](../frontend/src/pages/RedefinirSenhaPage.tsx),
  [ConfirmarEmailPage](../frontend/src/pages/ConfirmarEmailPage.tsx)) sobre uma moldura comum
  ([AuthShell](../frontend/src/components/AuthShell.tsx)) e cliente "cru" sem os interceptors de refresh
  ([recuperacaoSenha.ts](../frontend/src/api/recuperacaoSenha.ts) — quem esqueceu a senha não tem sessão
  a renovar). A tela de sucesso é **idêntica** para conta existente e inexistente, para a UI não desfazer
  a proteção anti-enumeração do servidor. Na confirmação de troca, "Não fui eu — recusar" tem o mesmo
  peso visual do confirmar. Rotas batem com os links montados pela IAM (`FRONTEND_BASE_URL` + path).
  Validado: `tsc` limpo nos arquivos novos (o legado caiu de 26 → 25 erros), imagens `iam`/`react`
  rebuildadas, as 3 rotas servidas pelo gateway (200) e o link do e-mail apontando para a tela nova.

**Fica de fora (registrado, não implementado):** **cadastro de usuário pelo frontend**, que virá com o
paywall (decisão 18/07); e leitura unificada das duas trilhas (ver **D17**).

### D12 — Revogação de sessão só cobre a desativação feita pela API · ✅ corrigido 19/07/2026

Na desativação (`is_active` True→False) o serializer faz o certo: `revoke_all_sessions` (blacklista os
refresh) + `bump_session_epoch` (corta o access residual na hora). **Mas** isso só roda nesse caminho:

- desativar por **Django admin, shell ou UPDATE direto no banco** não carimba nada — o access residual
  segue válido por ≤ access TTL (só o `/auth/refresh/` barraria, por checar `is_active`);
- **excluir** um usuário (em vez de desativar) também não carimba; pior, o access residual ainda passa no
  backend, que faz JIT `get_or_create` do espelho local e **recria** o usuário excluído por até 5 min;
- mudança de **papel/permissão** não carimba — propaga no próximo refresh (≤5 min) por recálculo de claims.
  *(este é o desenho documentado, registrado aqui só para não parecer omissão)*

**Corrigido (19/07):** o gatilho migrou para signals do `Usuario`
([iam/identity/signals.py](../iam/identity/signals.py), registrados no `AppConfig.ready`) — `post_save`
revoga na transição ativo→inativo e `post_delete` carimba a época, cobrindo admin, shell e script. O
serializer deixou de revogar (havia dois donos da mesma regra) e ficou só com a auditoria, que precisa
saber QUEM desativou — informação que o signal não tem. No `delete` não se blacklista refresh de
propósito: as linhas de `OutstandingToken` caem em cascata com o usuário, então o que vale é o carimbo.
Do lado do backend, `IamJWTAuthentication.get_user` — que **substitui** o do SimpleJWT e havia perdido a
checagem original — voltou a recusar espelho local inativo. Testes
[test_d12_revogacao.py](../iam/identity/test_d12_revogacao.py) (5): desativar e excluir pelo ORM carimbam;
salvar sem mudar `is_active`, reativar e criar **não** carimbam (revogar a cada `save()` derrubaria a
sessão do usuário a cada edição banal).
**Completado em 19/07 — troca de senha fora da API.** Ao revisar a entrega, apareceu que o mesmo buraco
continuava aberto numa terceira porta: os três caminhos que carimbavam a época em troca de senha eram
todos de aplicação (troca pela API, reset por token, `redefinir-senha` do admin). Trocar a senha pelo
**Django admin ou shell** não encerrava nada — e aqui era pior que na desativação, porque o
`/auth/refresh/` confere `is_active`, **não a senha**: o refresh antigo seguiria renovando o acesso
indefinidamente. Trocar a senha de uma conta comprometida pelo admin parecia cortar o acesso sem cortar.
O `post_save` passou a comparar o **hash** da senha (é o que está no banco; o hash muda a cada
`set_password` mesmo para a mesma senha, o que só causa revogação a mais, nunca a menos) e revoga
blacklistando o refresh + carimbando a época. Os fluxos legítimos não são afetados: eles carimbam antes
de reemitir a sessão, então o token novo (com `iat` ≥ carimbo) sobrevive — a suíte da IAM cobre isso.
**Provado no stack vivo:** token válido → `/api/clientes/` **200**; senha trocada pelo `manage.py shell`
(sem tocar em endpoint algum); **o mesmo token → 401**; relogin → 200.

**Segue de fora, por construção:** `UPDATE`/`DELETE` em SQL cru e `queryset.update()`, que não disparam
signals; e a mudança de papel/permissão, que propaga no próximo refresh (≤5 min) por recálculo de claims.

### D13 — Sem re-autenticação para ação sensível (step-up auth) · 📋 planejado

Os tempos de sessão limitam **por quanto tempo** uma sessão roubada vive, mas não impedem o estrago
**enquanto** ela vive: com a sessão aberta, um malware faz tudo que o usuário faz. O controle que fecha
isso é pedir a senha de novo **na ação sensível** — custo zero de conforto na navegação normal, e é o
padrão de ERP financeiro. Alvos naturais: alterar dado bancário (cliente/fornecedor/funcionário), dar
baixa/aprovar pagamento, gerar lote de remessa, emitir/cancelar NF, exportar ou esquecer titular (LGPD),
ler dado médico/bancário de RH, e criar/editar papéis e usuários (escalada de privilégio).
*Decisão 18/07/2026: não implementar agora — registrado para priorização futura.*

### D14 — `DB_SSLMODE` é knob morto e não há caminho para TLS no banco · ✅ corrigido 19/07/2026

`.env.example` declara `DB_SSLMODE=prefer` e `.env.staging.example` `disable`, mas o
[docker-compose.yml](../docker-compose.yml) **crava `DB_SSLMODE: disable`** nos 4 serviços que falam com o
Postgres (iam, erp, worker, beat). Confirmado em runtime: `disable` **no dev e no staging**. Ou seja:
(a) o knob do `.env` não vale nada; (b) **não existe forma de ligar TLS no banco por configuração** — o
staging, que se propõe idêntico a produção, conversa com o Postgres **em claro**.
**Corrigido (19/07):** o literal virou `${DB_SSLMODE:-disable}` nos 4 serviços
([deploy/compose/base.yml](../deploy/compose/base.yml)) — o knob do `.env` passou a valer. Faltava ainda
o caminho para o modo forte: `verify-full` exige a CA do servidor, então backend e IAM ganharam
`DB_SSLROOTCERT` (repassado pelo compose e aplicado em `OPTIONS` só quando definido — sem ele o modo
falha na verificação, e não cai em conexão insegura silenciosa). `deploy/env/prod.env.example` já nasce
com `verify-full`. **Não validado contra Postgres com TLS real** (não há um disponível): o que se provou
é que o knob chega ao Django e que dev/staging seguem subindo com `disable`.

### D16 — Cookie de refresh emitido SEM `Secure` (staging, sob HTTPS) · ✅ corrigido 18/07/2026

Achado na auditoria 18/07 (doc × código × runtime). O cookie que **é** a sessão saía do staging como
`HttpOnly; Path=/auth/; SameSite=Strict` — **sem `Secure`** —, ou seja, podia trafegar em HTTP puro
(exposição a downgrade/MITM da credencial mais sensível do sistema). Causa: `REFRESH_COOKIE_SECURE` lia
`IAM_COOKIE_SECURE` com default `"0"`, e essa variável **não estava definida em lugar nenhum** (nem
compose, nem `.env`, nem documentada). O endurecimento do bloco de produção (S4) só alcança os cookies do
**Django** (`SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`); o refresh é setado à mão em
[cookies.py](../iam/identity/cookies.py) e ficava de fora. O comentário no próprio settings já afirmava
"Secure=1 sob HTTPS (produção)" — a intenção estava documentada, a implementação não seguia.
**Corrigido:** default passa a ser **ligado fora de `DEBUG`** (mesmo princípio do S4); `IAM_COOKIE_SECURE`
documentado no `.env.example`; regressão `test_cookie_de_refresh_leva_secure_quando_ligado`.
**Confirmado no ar 18/07/2026** (imagem da IAM rebuildada): o login do staging passou a emitir
`sgi_refresh=…; HttpOnly; Path=/auth/; SameSite=Strict; **Secure**`.

### D26 — O CI nunca rodou a suíte do backend: três jobs vermelhos há 7 dias · ✅ corrigido 26/07/2026

Achado ao analisar o estado do projeto. O job `backend-tests` rodava
`manage.py test identity funcoesemail` com `working-directory: backend` — mas **`identity` é app da
IAM**, não existe no backend. O rótulo e o comentário que o explica foram colados no job errado
(introduzidos em `a4c45be`, 19/07). Resultado reproduzido: `ModuleNotFoundError: No module named
'identity'`, **"Ran 1 test"** — o job falhava e **nenhum dos 677 testes do backend rodava**.

Agravante no mesmo comando: o rótulo **`funcoesemail`** (sem `.tests`) roda **0 testes** em silêncio.
Django resolve o rótulo como diretório quando ele existe no cwd, e como *nome de módulo* quando não —
nos dois caminhos cai num **pacote** que não declara testes. Só `funcoesemail.tests` roda os 9. Ou
seja, nem a parte que "funcionava" funcionava, e a mensagem final era `NO TESTS RAN`, não um erro.

E não era um job só. O **`frontend`** e o **`security-scan`** também estavam vermelhos, os dois pelo
mesmo `npm ci` do **F6** — no `security-scan` ele roda *antes* do `npm audit` e do trivy, então o gate
bloqueante de CVE e de segredos também não executava. Dos 4 jobs, **3 vermelhos**; o único verde era
o do IAM.

**Por que importa mais que a soma das partes.** Entre 19 e 26/07 entraram SIL v2, ORC.0–ORC.5b,
IE.0–IE.1 e o pacote clientes/F16–F20 — todos com "suíte X/X verde" registrado aqui e no roadmap,
todos medidos **à mão**, nenhum por um portão. A afirmação era verdadeira e não era verificável: é a
classe de defeito que não quebra nada hoje e remove a rede de proteção de tudo o que vem depois.

**Corrigido:** job do backend passou a `manage.py test . funcoesemail.tests` (`.` dispara a descoberta
a partir de `backend/`; o pacote da raiz entra pelo módulo de teste), o `identity` voltou para o job
do IAM e os comentários dos dois jobs foram corrigidos. **Linha de base medida na correção — 801
testes verdes:** backend **677**, `funcoesemail` **9** (= os 686 que os documentos citavam), IAM
**115**. Nenhuma regressão havia acumulado atrás do portão desligado; o que faltava era a prova.
**Não fechado:** os `continue-on-error` de lint/build do frontend — medidos em clone limpo, `npm run
lint` dá **51 erros** e `tsc -b` dá **45** em 19 arquivos, e o topo **não** é o shell legado que o
comentário do `ci.yml` culpava, é o **SIL v2** (`operacao.tsx` 13, `pessoas.tsx` 6), de 25/07. Ver
**D27**.

### D27 — 45 erros de tipo no frontend, e um import de dependência que não existe · 🔴 aberto

Medido ao tentar transformar lint/build em gate (D26): `tsc -b` acusa **45 erros** em 19 arquivos e
`npm run lint` **51**. Enquanto isso vale, o build do CI não pode bloquear merge — e o `vite build`
da imagem não substitui o gate, porque usa `npx vite build` **sem `tsc`**: o esbuild transpila sem
type-check, então erro de tipo nunca aparece em lugar nenhum.

Concentração (não é dívida uniforme de shell legado): `modules/sil/tabs/operacao.tsx` **13**,
`sil/tabs/pessoas.tsx` **6**, `crm/pages/LeadsPage.tsx` **4**, `obras/ObraDetailPage.tsx` **3**. A
maioria é ruído barato (`no-unused-vars`, TS6133), mas há erros de contrato reais: `obra_nome`/
`etapa_nome` lidos de `MovimentacaoEstoque` e `Requisicao` sem existir no tipo (o backend passou a
mandá-los na apropriação por etapa do SIL v2 e o tipo do front não acompanhou) e
`Property 'token' does not exist on type 'AuthContextType'` em `ObrasListPage`, resíduo da Fase 10.6
(access token saiu para a memória).

**Confirmação independente do `F5` da tabela de Médias** (o do código morto, não o do `.gitignore` —
colisão de IDs herdada dos laudos): 3 dos 45 erros vêm de `modules/obras/ObraDetailPage.tsx`, a
duplicata órfã já inventariada lá, e ela importa **`react-hot-toast`, que não está no
`package.json`** — o mesmo padrão de dependência fantasma que aquela entrada já registrou para o
`frappe-gantt` do `GanttChart.tsx`. Ou seja: **parte dos 45 erros morre com a limpeza do código
morto**, não precisa de correção própria. Fazer o `F5` da tabela antes de atacar o resto reduz o
número real.

**Resíduo à parte:** o `package.json` da **raiz** do repo é da era Node (versão `1.0.14`,
`description` com um cabeçalho markdown solto, deps duplicando o frontend) e está **fora da varredura
do CI**, que só olha `frontend/` — decidir se sai ou entra no escopo do `npm audit`.
**Correção:** limpar o código morto (`F5` da tabela) → zerar os erros de tipo que sobrarem, começando
pelos **contratos do SIL**, que são bug de verdade e não ruído → remover os dois `continue-on-error`
do job `frontend`.

### D25 — `worker`/`beat` ficam com a imagem velha quando só `erp`/`react` são rebuildados · ✅ corrigido 26/07/2026

Achado ao subir o **IE.0b**: a importação de arquivo grande respondia **202** e a tela ficava
progredindo para sempre. O lote ficava em `lendo` com 0 linhas, sem erro em lugar nenhum — nem na
DLQ, porque a task nunca chegou a existir. Causa: `docker compose build erp react` não reconstrói
`worker`/`beat`, que **usam a mesma imagem do backend**; o worker seguia com o código antigo e
descartava `funcoesimpexp.preparar_importacao` como task desconhecida.

É a mesma classe do **D8** (Celery que responde 202 e nunca faz o trabalho), por outro caminho: lá
faltava o contexto de tenant, aqui falta a imagem. E o sintoma é o pior possível — **sucesso
aparente**, porque o 202 é honesto e a falha acontece depois, fora da vista.

O comando certo **já estava** em [comandos.md](comandos.md) (`--build erp worker beat`); o que
faltava era o aviso de que rebuildar parcialmente falha em **silêncio**. Sem isso, a regra parece
zelo e é fácil de encurtar quando "só mexi numa view".

**Corrigido:** `worker`/`beat` recriados e o efeito colateral documentado no `comandos.md`, ao lado
do comando. Provado depois pelo E2E
[ie_impexp_test.py](../infra/gateway/ie_impexp_test.py) (16/16), que exercita justamente o caminho
de job que o bug escondia.

### D17 — Duas trilhas de auditoria sem leitura unificada · 🟠 aberto

Criado junto do **D11**. A plataforma passou a ter **duas** trilhas append-only e independentes:
`nucleo.AuditLog` (backend — escritas de RH, leitura de PII, baixa financeira, NF, LGPD) e
`identity.EventoSeguranca` (IAM — reset de senha, troca de e-mail, escalada de privilégio,
desativação). A separação é consequência de a IAM ser autocontida (mesma razão de ela ter ganhado
SMTP próprio), mas **o auditor não tem onde ver as duas juntas**: `GET /api/auditoria/` só enxerga a
do backend, e a da IAM hoje só é legível por shell/admin.

Isso importa no incidente que motivou o D11: reconstituir "admin comprometido" exige cruzar o
`reset_assistido` (IAM) com o que a conta fez depois (backend), hoje manualmente e sem correlação por
`request_id`.
**Correção sugerida:** endpoint de leitura na IAM (`GET /iam/eventos-seguranca/`, gateado por
`plataforma.auditoria.view` — permissão que **já existe** no catálogo) + uma visão no frontend que
consulte as duas fontes, ou envio dos eventos da IAM ao `AuditLog` por JWT de serviço (Fase 10.8) com
outbox local para não perder evento se o backend estiver fora.

### D23 — Limite de entrada sem dimensão de TENANT (noisy neighbor) · ✅ corrigido 19/07/2026 · camada 1

Aberto ao concluir a **camada 2** (D22): com a saída protegida, a entrada ficou sendo a lacuna. Hoje o
throttle tem eixo por **IP** e por **usuário** — falta o eixo que define um SaaS, o **tenant**.

Consequência prática num produto vendido por empresa: uma empresa com 50 funcionários consome
legitimamente 50× o que uma de 3 consome, e **nada impede que degrade a experiência da outra**. É o
problema conhecido como *noisy neighbor*. A prática de mercado
([AWS](https://aws.amazon.com/builders-library/fairness-in-multi-tenant-systems/),
[AWS API Gateway](https://aws.amazon.com/blogs/architecture/throttling-a-tiered-multi-tenant-rest-api-at-scale-using-api-gateway-part-1/))
é limitar **por tenant** e fazer o teto de usuário ser uma **fração** do teto da empresa, não um valor
independente como está hoje.

**Corrigido (19/07)** — [nucleo/throttling.py](../backend/nucleo/throttling.py): `TenantRateThrottle`
chaveado pelo `tenant_id` do espelho local (`user.tenant_id`, sincronizado do claim pela
`IamJWTAuthentication` — o mesmo idioma de `tenancy.py`; um segundo caminho para o mesmo dado é um
segundo caminho para divergir dele). Sem tenant (anônimo, dono da plataforma) o eixo devolve `None` =
"não se aplica", e os eixos `anon`/`user` seguem valendo.

**O teto de usuário passou a DERIVAR do teto da empresa** (`THROTTLE_TENANT` ×
`THROTTLE_USER_FRACAO`, default 5%), que é o ponto do achado: solto, ele mentia nas duas pontas — 20
funcionários × 3000/h davam 60.000/h à empresa sem ninguém ter declarado esse número, e uma empresa de
3 pessoas ficava com teto efetivo 7× menor sem motivo. A fração default **preserva exatamente** o teto
de usuário vigente antes do D23: o eixo é somado, nenhum limite existente foi afrouxado.
`THROTTLE_USER` continua como escape hatch (definido, vence a derivação).

**Correção da 1ª versão, no mesmo dia — o teto do TENANT era constante e estrangulava o cliente
grande.** Apontado pelo usuário: com `60000/hour` fixo, uma empresa de 1000 funcionários recebia **60
requisições por hora por pessoa** — menos do que o polling do sino de notificações consome sem ninguém
trabalhar (~75/h só com o app aberto). O defeito não era o número e sim a **forma**: teto fixo não tem
valor que funcione — alto o bastante para o cliente de 1000 não protege contra o de 50 abusando; baixo
o bastante para proteger inutiliza o de 1000.

Pesquisa da prática (GitHub: base 5.000/h **+50/h por usuário** da organização, cap 12.500/h; Shopify:
teto por **tier do plano**, 50→100→500 pts/s; AWS SaaS Lens: balde por tenant + tier) mostrou
convergência em três pontos: **balde por tenant**, **teto derivado do plano/tamanho** e **teto duro no
topo**. Adotados os três. Por decisão do dono do produto, o teto passou a sair do **paywall**:

- **[`payment/`](../payment/README.md)** — pacote na raiz com os **valores comerciais** (planos,
  quotas, preços, add-ons e os parâmetros do teto). É o arquivo que o dono do software edita, sem
  revisão de código. Inclui o novo plano **`free`** (1 seat), que é o degrau de aquisição *e* o
  default de quem não tem assinatura — default seguro: tenant provisionado com erro cai no plano
  **menor**, nunca em "sem limite".
- **[`payment/regras.py`](../payment/regras.py)** — as **regras** (derivação, precedência, fallback).
  *(Ficava em `iam/identity/planos.py` até 19/07; movida para `payment/` no D24 para reunir todo o
  modelo comercial numa pasta só — ver a nota no D24.)*
- **Teto = `min(base + seats × por_seat, teto_de_infra)`**, com precedência
  `AssinaturaTenant.limites` → plano → `free`. Deriva de seats **contratados**, então comprar o add-on
  de usuário extra **aumenta o teto sozinho**: o limite acompanha a receita em vez de brigar com ela.
- **A IAM emite o teto como claim `rate_hora`** do access token, e não o backend calcula, porque só
  ela sabe quantos seats foram contratados — o `Usuario` do backend é **espelho JIT** (só existe quem
  já logou), então contar lá daria um teto menor que o contratado e **crescente durante a
  implantação** do cliente. Propaga no próximo refresh, como permissão.
- **`RATE_TETO_INFRA_HORA` fica acima de qualquer plano**, inclusive do *Sob Medida*: "ilimitado" no
  contrato não pode virar ilimitado no eixo de requisições, senão um tenant consome a capacidade dos
  outros. Contrato maior exige projeto de capacidade, não cláusula.

Desenho completo em [monetizacao.md §11](arquitetura/monetizacao.md).

**Também adotado da pesquisa: `X-RateLimit-Limit/Remaining/Reset`** na resposta (GitHub, Stripe e
Shopify retornam; o DRF só manda `Retry-After`, e só no 429). Sem eles o cliente só descobre o teto
**batendo nele** — o comportamento que o teto existe para evitar. Publicados pelo eixo do tenant, que
é o teto que o cliente compra e o único que ele administra. Armadilha encontrada: o `request` do DRF é
um **wrapper**, e `setattr` nele não alcança o `HttpRequest` que o middleware recebe na volta — sem
escrever em `request._request` o header sumia em silêncio.

**Modo de falha (pesquisado a pedido):** o consenso é **dividido por tipo de endpoint** — fail-open em
API de dados (fail-closed transforma queda de cache em queda total do produto) e **fail-closed em
autenticação**, onde liberar durante a queda é o que o atacante quer. É o que já vale aqui por
construção: o anti-brute-force do login mora no **nginx** e não depende do Redis, então a dimensão
crítica de segurança nunca foi fail-open. Mantido.

**Segundo furo fechado no gateway:** `limit_req_zone api` + `limit_req` na `location /api/`
(1200 r/m por IP, `burst=300 nodelay`) em [nginx.unified.conf](../infra/gateway/nginx.unified.conf) e
[nginx.staging.conf](../infra/gateway/nginx.staging.conf) — é o único lugar onde a inundação anônima de
`/api/*` é barrada, já que o DRF resolve permissão **antes** do throttle e o `401` não é contado por
eixo nenhum. Folgado de propósito: um escritório inteiro compartilha um IP via NAT, e o limite fino é o
da aplicação.

**Dois defeitos que a implementação expôs:**

- **Fail-open ausente na camada 1.** `django_redis` com `IGNORE_EXCEPTIONS=True` devolve **`None`**
  (não o default) quando o Redis cai, e o `SimpleRateThrottle` do DRF faz `history.insert(...)` logo
  depois → `AttributeError` → **500 em toda requisição**. O teto derrubaria justamente o que existe
  para proteger. Os **quatro** eixos passaram a ser subclasses locais com `FailOpenMixin` (libera e
  **loga em nível de erro** — protetor fail-open silencioso é indistinguível de protetor funcionando,
  a lição do D21). Inclusive o `ScopedRateThrottle`, que guarda os verbos caros (dashboard, NF, cobrança).
- **Os `THROTTLE_*` nunca chegavam ao container** — mesmo defeito do **D20** com `MAIL_*`: documentados
  no `.env.example` desde o S8 e ausentes do [compose](../deploy/compose/base.yml), então o operador
  ajustava o teto no `.env` e nada mudava, porque valia sempre o default do settings. Repassados ao
  `erp` (só ele serve HTTP), junto do `NUM_PROXIES` — que estava no mesmo estado e é o que define se o
  teto por IP é contornável por `X-Forwarded-For` falso.

Testes: [test_d23_tenant_throttle.py](../backend/nucleo/test_d23_tenant_throttle.py) (13) — o central é
**dois usuários da mesma empresa dividindo o balde**, com a contrapartida obrigatória (empresas
distintas não se afetam), o texto do 429 dizendo que o bloqueio é da *empresa* e não da *conta* (§2.4),
usuário sem tenant não quebrando, a queda do Redis liberando em vez de 500, e **dois tenants com planos
diferentes recebendo tetos diferentes no mesmo servidor**.
[identity/test_planos.py](../iam/identity/test_planos.py) (15) cobre o lado da IAM: teto monotônico por
plano, **empresa grande não estrangulada** (regressão do defeito original), add-on de seat aumentando o
teto, contrato vencendo o plano, nada passando do teto de infra, e plano desconhecido caindo no `free`
sem levantar. **Suítes: backend 239/239 e IAM 99/99**; `nginx -t` verde no unified.

**E2E validado no stack vivo 19/07/2026** (imagens `iam` e `erp` rebuildadas):
[d23_teto_por_plano_test.py](../infra/gateway/d23_teto_por_plano_test.py) **8/8 pelo gateway** — prova a
cadeia inteira que o teste de unidade não cobre: tenant sem assinatura cai em `free` (`rate_hora=6.900`)
→ upgrade para `empresarial` sobe o teto para **42.000** → o backend **usa** esse número
(`X-RateLimit-Limit: 42000`, `Remaining` coerente, `Reset` presente) → downgrade para `essencial`
reduz para **8.700** no token seguinte. O roteiro restaura o plano do tenant ao final.
Regressão dos E2E vizinhos: **phase6 verde** e **phase8 10/10**.

Armadilha registrada: o `manage.py shell -c` imprime um banner **antes** da saída do código, e a 1ª
execução gravou esse banner como nome do plano no restore. Corrigido com marcador (`PLANO=`) — vale
para qualquer roteiro que leia estado pelo shell do Django.

Desenho completo em [arquitetura/rate-limiting.md](arquitetura/rate-limiting.md) §2.

### D24 — Cota comercial por plano (camada 3) · 🟠 parcial · fundação 19/07 · **trava de objeto/seat ✅ 19/07/2026**

Quantas notas, boletos, análises de IA ou mensagens o plano contratado inclui por mês, por tenant.

**Já existia (entregue junto do D23):** o **catálogo de planos em código** — em
[`payment/`](../payment/README.md), com todas as quotas do [monetizacao.md §5](arquitetura/monetizacao.md)
**declaradas**, o plano `free` como default seguro e a precedência
`AssinaturaTenant.limites` → plano → `free`. Isso fechou o **item 1 do faseamento** do §10 daquele documento.

**Entregue 19/07/2026 — item 2 (trava dura de seats e objetos), sem depender do checkout:**

- **Quotas viajam como claim.** A IAM emite `quotas` no access token
  ([tokens.py](../iam/identity/tokens.py) + `quotas_efetivas`), pelo mesmo motivo do `rate_hora`: ela é
  quem sabe o que foi **contratado**, o backend é quem sabe quanto já foi **usado**. Evita um hop de
  rede no caminho de escrita, que cairia junto com a IAM. A claim leva **só o que é aplicado** —
  publicar quota inerte convidaria alguém a aplicá-la sem que o contador existisse do outro lado.
- **Objetos travam no backend** ([nucleo/quotas.py](../backend/nucleo/quotas.py)): `QuotaEnforcedMixin`
  com `quota_recurso` nos 4 viewsets da família de valor (empreendimentos, obras, clientes,
  fornecedores) → **402** com corpo estruturado (`quota`/`limite`/`uso`/`plano`).
- **Seats travam na IAM** ([identity/quotas.py](../iam/identity/quotas.py)), porque quem cria usuário é
  ela; o `Usuario` do backend é espelho JIT e contaria menos que a realidade durante a implantação.
  **Seat = usuário ativo**, então desativar libera — a saída sem checkout quando alguém sai da empresa.
- **Medidor antes da parede:** `GET /api/plano/` ([plano_views.py](../backend/nucleo/plano_views.py))
  serve plano, uso, limite, próximo degrau e o catálogo com preços. É o primeiro consumidor de
  `payment/` no backend (o `Dockerfile` passou a copiar o pacote, como o README de lá já previa).

Decisões que valem registro:

- **Só a família de VALOR trava.** A de CUSTO (IA, NF, boleto, drone, armazenamento) fica de fora por
  desenho — a regra de ouro do [monetizacao.md §4](arquitetura/monetizacao.md) manda medir e cobrar o
  excedente dela. Travar o cliente no meio de um fechamento fiscal para vender um pacote custa mais que
  o excedente evitado. Há teste que **falha** se alguém acrescentar um recurso de COGS ao registro.
- **Trava só a criação.** Editar e excluir passam mesmo acima do teto: um downgrade não pode deixar o
  cliente sem conseguir corrigir nem apagar os próprios dados.
- **Fail-open sem a claim** (token de serviço/legado), e **logado**. Não é brecha: forjar token exige a
  chave da plataforma. Fail-closed trocaria uma feature comercial por indisponibilidade de escrita.
- **Corrida aceita:** duas criações simultâneas podem terminar em `limite + 1`. Serializar exigiria
  travar a linha do tenant em toda escrita — gargalo por empresa — para evitar uma unidade num limite
  comercial. Diferente do L5, onde o que estava em jogo era o valor pago de um título.
- **Reativar consome seat.** Sem isso a trava era contornável: desativar, criar o novo, reativar o
  antigo — e terminar acima do contratado sem ver um 402.
- **Corpo do 402 sai com números, não strings.** O `APIException` do DRF converte todo o `detail` em
  `ErrorDetail` (subclasse de `str`), então `limite: 0` chegaria como `"0"`. Achado ao escrever o teste
  do contrato; corrigido nos **dois** serviços, que precisam falar a mesma língua com o frontend.
- **A lista de "quais quotas travam" é botão COMERCIAL e mora em `payment/planos.py` §4.** A 1ª versão
  a deixou junto das regras de engenharia — correção pedida pelo dono do software em 19/07, com o
  argumento que vale registrar: *o que influencia o valor final tem de estar onde ele enxerga; fora de
  `payment/` passa despercebido*. Tirar um nome da lista faz o limite deixar de morder — **vazamento de
  receita silencioso**, sem erro em log algum. Como o registro de contadores (`nucleo/quotas.py`)
  continua sendo engenharia, um teste garante que os dois **não divergem** em nenhum sentido (provado
  que pega: removendo um recurso da lista comercial, o teste falha).
- **Todo o modelo comercial foi reunido em `payment/` (19/07, a pedido do dono).** As **regras**
  (derivação do teto, precedência, fallback) saíram de `iam/identity/planos.py` — que **deixou de
  existir** — para [`payment/regras.py`](../payment/regras.py), ao lado dos valores. Motivo: quem faz
  manutenção do modelo comercial abre **uma pasta só**. Fronteira dentro dela: `planos.py`/`addons.py`
  = valores (o dono edita); `regras.py` = engenharia. Efeito colateral bom: **matou a duplicação** do
  `proximo_plano`, que o backend antes reescrevia por não alcançar o código da IAM.
  O **enforcement** (`iam/identity/quotas.py` = seats, `nucleo/quotas.py` = objetos) **não** foi para
  `payment/` e não pode ir: precisa do framework (exceção HTTP) e conta linhas **no banco de cada
  serviço** — dois bancos que o pacote compartilhado não alcança. A contagem roda onde o dado está,
  mas pede **todo limite** a `payment/regras.py`. Sem decisão comercial nesses dois arquivos.

**Armadilha exposta pela entrega — tenant sem `plano` fica no `free` (1 seat, 2 obras).** Os seeds não
gravavam plano nenhum, então ligar a trava capava a demo em 1 usuário. `iam/seed_demo.py` passou a
definir o plano **explicitamente** (`demo` → `profissional`; `acme` fica no `free` de propósito, para
existir sempre um tenant onde a parede é alcançável à mão). **Vale para o cutover:** todo tenant real
precisa de `plano` explícito antes de a trava valer para ele, senão será tratado como `free`.

**Falta:** os medidores mensais de consumo com excedente cobrado (**item 5**) e o **checkout** (item 3:
landing → Asaas → provisionamento). A UI é a **fase G** do [frontend.md §5.16](frontend.md) — enquanto
não houver checkout, o CTA de upgrade abre contato, não pagamento.

**Validado:** `nucleo/test_quotas.py` (16) e `identity/test_quotas.py` (16); suítes completas
**backend 255/255** e **IAM 115/115**. Falta E2E no stack vivo (validação sob demanda).

**Não é proteção técnica, é produto:** excedente vira bloqueio comercial ou upsell, não `429`. Por isso
depende do modelo de assinatura e **anda junto do paywall**, não antes dele — mesma decisão já registrada
para o cadastro de usuário pelo frontend (ver D11). O contador é por tenant e por período de faturamento,
e precisa ser **auditável**, porque vira fatura.

Desenho em [arquitetura/rate-limiting.md](arquitetura/rate-limiting.md) §4.

### D22 — Nenhum limite protegia a cota dos fornecedores (saída) · ✅ corrigido 19/07/2026 · camada 2

Auditoria de 19/07 contra a prática de mercado para SaaS multi-tenant. O S8 tinha construído limite de
**entrada** e nada de **saída** — e a saída é onde há dinheiro e cota de terceiro. Estado encontrado:

- **8 integrações**, não 2: NFE.io, Asaas, WhatsApp (Meta), ODM do drone, LLM de visão, geocoding,
  feriados e SMTP. `grep -rn "rate_limit" backend/` → **nada**.
- Toda task de integração com `max_retries=3` → cada ação vira **até 4 chamadas** ao fornecedor.
- O escopo `integracao_externa` (ligado no próprio S8) estava na **camada errada** e errava nos dois
  sentidos: por usuário, 20 funcionários × 300/h = **6.000 chamadas/hora** ao Asaas; e
  [`emitir_lote_nfse`](../backend/moduloerp/views.py) recebe uma **lista** e emite N notas numa
  requisição só — contada como **1**. Guarda que dava sensação de proteção sem proteger.

**Corrigido — camada 2** ([nucleo/rate_limit.py](../backend/nucleo/rate_limit.py), desenho em
[arquitetura/rate-limiting.md](arquitetura/rate-limiting.md)): token bucket no Redis (DB 4 dedicado),
**por fornecedor**, consumido **no cliente HTTP dentro do worker** — o único ponto que conhece o número
real de chamadas. Token bucket porque o trabalho chega em lote (remessa, fechamento) e janela fixa
quebraria o lote legítimo. Ligado em NFE.io, Asaas, WhatsApp, LLM e e-mail; taxa e burst calibráveis por
env, e fornecedor sem config passa (integração nova não trava por esquecimento).

Decisões que valem registro:

- **Sem token → `retry`, nunca bloqueio.** Centralizado no `DLQTask`, com orçamento próprio de
  retentativas (48): esperar a janela do fornecedor não é defeito e não pode consumir as tentativas
  reservadas a falha real. Bloquear o worker pararia a fila inteira, inclusive de outros tenants.
- **A exceção herda de `Throttled` (DRF).** Nem toda chamada vem de task: `gerar-cobranca` e
  `divergencias-asaas` consultam o Asaas **dentro da requisição** e capturam só `AsaasAPIError` — uma
  exceção comum viraria **500**. Sendo `Throttled`, vira **429 com `Retry-After`** em qualquer view,
  inclusive nas que ainda não existem.
- **Fail-open, mas RUIDOSO** (log de erro): travar pararia emissão de nota e boleto do sistema inteiro;
  passar gera, no pior caso, 429 do próprio fornecedor — que o retry trata. O silêncio é que foi o
  problema no D21.
- **`chave_extra` pronta para credencial por tenant** (previsto para o Asaas): aí a cota disputada passa
  a ser de cada empresa, e um balde global limitaria empresas sem relação entre si.

Testes: [test_rate_limit.py](../backend/nucleo/test_rate_limit.py) (11) — rajada passa, teto vira espera,
reposição com o tempo, baldes independentes, fail-open ruidoso, retry com `countdown`, e o caso central:
**lote de N notas consome N tokens** e a chamada não sai sem token. **Provado no stack vivo:** balde
compartilhado entre `erp` e `worker` (erp consome 2 → worker vê 1 → bloqueia na 4ª).

**Falta:** as outras duas camadas — **D23** (limite por tenant, camada 1) e **D24** (cota por plano,
camada 3).

### D21 — Throttle da IAM ficou inerte no Docker (cache morta em silêncio) · ✅ corrigido 19/07/2026

Encontrado em 19/07 ao responder uma pergunta sobre a UX do 429: 34 pedidos seguidos de recuperação de
senha passaram **todos com 200**, com o teto configurado em 30/hora. O throttle do S8 estava **inerte
desde que foi criado**.

Causa: a `IAM_CACHE_REDIS_URL` não foi repassada no compose, então dentro do container o default do
settings (`redis://localhost:6379/3`) apontava para o **próprio container**, onde não há Redis. E como a
cache foi configurada com `IGNORE_EXCEPTIONS: True` — de propósito, para uma queda de Redis não derrubar
o login —, a falha virou **no-op silencioso**: nenhum erro no log, nenhum sintoma, e a contagem do
throttle simplesmente não acontecia.

É a face ruim do fail-open, e vale como lição além deste caso: **um protetor fail-open que perde a
dependência fica indistinguível de um protetor funcionando**. O `/readyz` da IAM não pega isso porque
verifica o Redis da revogação (DB 2), que está configurado corretamente — são conexões diferentes.

**Corrigido:** `IAM_CACHE_REDIS_URL` repassada aos serviços no compose. **Provado no stack vivo:** cache
`VIVA`, e o 429 passa a disparar na requisição **#31**, exatamente no teto configurado.

**Varredura completa (19/07), pedida depois da primeira correção — achou mais dois defeitos:**

- **(a) Teto por IP era contornável por qualquer um.** O gateway usa
  `$proxy_add_x_forwarded_for`, que **acrescenta** o IP real ao `X-Forwarded-For` **enviado pelo cliente**;
  o DRF, sem `NUM_PROXIES`, usa a **cadeia inteira** como identidade. Bastava mandar um XFF falso e
  trocá-lo a cada requisição para ganhar um balde novo — provado no ar: 34 pedidos com XFF rotativo
  criaram 34 baldes e nenhum 429. **Corrigido** com `NUM_PROXIES=1` (env `NUM_PROXIES`) nos dois serviços:
  o DRF passa a usar o endereço acrescentado pelo proxy e ignora o que o cliente afirma. Reprovado no ar:
  os mesmos 34 pedidos caem num balde só e o 429 volta a disparar em #31. **Ajuste obrigatório no
  cutover:** com CDN/ALB na frente, o número tem de bater com a topologia real.
- **(b) A mesma confusão poluía a TRILHA DE AUDITORIA.** `_origem()` pegava `xff.split(",")[0]` — o
  primeiro elemento, 100% controlado pelo cliente — e o comentário afirmava que "a borda reescreve"
  (ela acrescenta). Dava para **gravar IP falso no `EventoSeguranca`**, o registro que existe justamente
  para reconstituir incidente: incriminar outro endereço ou esconder o próprio. Corrigido para usar o
  endereço do proxy confiável, com `NUM_PROXIES` como setting de topo — fonte única para o throttle e
  para a trilha, que não podem divergir. Testes [test_origem_ip.py](../iam/identity/test_origem_ip.py) (7).
- **(c) Dois escopos eram configuração morta.** `relatorio` e `integracao_externa` tinham taxa definida e
  **nenhuma view os declarava** — efeito zero. Ligados: `relatorio` no `ERPDashboardView` (a chamada mais
  cara da API) e `integracao_externa` nas ações que gastam cota de terceiro (gerar cobrança, emitir NFS-e/
  NF-e/lote), via `get_throttles()` por ação — repetir isso em laço não é só carga, é fatura de terceiro e
  documento fiscal indevido. Regressão em `nucleo/test_s8_jwt_throttle.py` garante que não voltem a ser
  letra morta, e que o teto apertado **não vaze** para o CRUD comum.

**Limite conhecido, registrado de propósito:** em endpoint que exige autenticação, o DRF resolve
permissão **antes** do throttle — requisição sem token leva 401 e **não é contada** (provado: 10 chamadas
sem token a `/api/clientes/` criaram zero chaves; as mesmas 10 no endpoint público contaram 10). Ou seja,
o teto `anon` protege as rotas `AllowAny` (webhooks, recuperação de senha), não a inundação anônima de
`/api/*` — para essa, o controle é o do nginx, que hoje cobre só o login. Fechar isso exigiria um
`limit_req` geral no gateway.

**UX do 429 (a pergunta que originou o achado):** o corpo que chegava à tela era o texto do DRF —
*"Pedido foi suprimido. Espera-se que esteja diponível em 3600 segundos."*, em segundos e com o erro de
digitação que vem da tradução do próprio framework. [mensagemDeErro](../frontend/src/api/recuperacaoSenha.ts)
passou a tratar 429 à parte, dizendo em minutos (via `Retry-After`) e deixando claro que o bloqueio é da
**conexão**, não da conta — sem isso a pessoa conclui "minha conta foi bloqueada" e liga para o suporte.
O texto não diz nada sobre a conta existir, pelo mesmo motivo que o teto por conta é silencioso.

### D20 — E-mail do backend nunca saiu: sem `MAIL_HOST` e com STARTTLS forçado · ✅ corrigido 19/07/2026

Encontrado em 19/07 ao migrar os últimos `send_mail` para o `funcoesemail`: ao tentar o primeiro envio
real pelo backend, ele falhou. **Dois defeitos empilhados**, e o de baixo escondia o de cima:

1. **O compose nunca passou `MAIL_*` ao backend.** Só o serviço `iam` recebia `MAIL_HOST`; `erp`, `worker`
   e `beat` subiam sem nenhuma variável de e-mail. Como as duas tasks começam com
   `if not settings.EMAIL_HOST: return`, elas viravam **no-op silencioso** — o lembrete de tarefa do CRM e
   o e-mail de lembrete do calendário **nunca dispararam em nenhum ambiente**. O aviso in-app do
   calendário funcionava e mascarava a ausência (a validação da Fatia C conferiu o sino, não a caixa).
2. **STARTTLS forçado.** `EMAIL_USE_TLS = not EMAIL_USE_SSL` ligava TLS em qualquer porta ≠ 465, e o
   Mailpit (1025) não oferece STARTTLS → `SMTPNotSupportedError` em todo envio. A IAM já excluía a 1025
   (`EMAIL_PORT not in (465, 1025)`); o backend não — as duas configurações haviam divergido.

**Corrigido:** `MAIL_HOST/PORT/USER/PASS/FROM` repassados a `erp`/`worker`/`beat` no compose, e a regra de
TLS do backend alinhada à da IAM (+ `EMAIL_TIMEOUT`, que também faltava: sem ele um SMTP pendurado segura
o worker). **Provado no stack vivo:** os dois e-mails chegam ao Mailpit com assunto e corpo corretos.

### D18 — Diário de obra datado em UTC: contribuição da noite ia para o dia seguinte · ✅ corrigido 19/07/2026

Encontrado **por acidente** em 19/07, ao rodar a suíte depois da meia-noite UTC durante outra entrega:
3 testes do `funcoeswhatsapp` falharam sem que nenhuma linha daquele módulo tivesse mudado.

`modulodiario.services.registrar_contribuicao` usava `timezone.now().date()` — a data em **UTC**. Como o
projeto roda em America/Sao_Paulo (UTC-3), toda contribuição feita entre **21h e meia-noite** era
arquivada no diário do **DIA SEGUINTE**. É exatamente o horário em que a equipe de campo fecha o dia pelo
WhatsApp, e o diário de obra é registro contratual — datar errado não é detalhe cosmético. Duas
contribuições da mesma noite (20h55 e 21h05) caíam em diários diferentes.

**Corrigido:** `timezone.localdate()` nas 4 ocorrências (`modulodiario/services.py`,
`modulodiario/views.py` ×2, `moduloerp/views.py`). Regressão em
[modulodiario/tests.py](../backend/modulodiario/tests.py) (2) com o instante **fixado** por mock — o app
não tinha `tests.py` até aqui, e um teste que dependesse do relógio de quem roda esconderia o bug de novo
(ele só se manifesta em 3 das 24 horas do dia). Provado que pega: revertendo a correção, o teste falha.

### D19 — A suíte dependia do `.env` da máquina de quem a roda · ✅ corrigido 19/07/2026

Também exposto em 19/07. Três acoplamentos faziam o resultado dos testes variar sem mudança de código:

- **Throttle (S8):** a contagem vive na cache, que era o Redis **real e compartilhado** — um teste
  consumia a cota do seguinte, e o teto por hora nem zerava entre execuções. Foi o que quebrou 12 testes
  da IAM na primeira tentativa do S8.
- **Celery:** `CELERY_TASK_ALWAYS_EAGER` tinha default `str(DEBUG)`; bastava alguém pôr `False` no `.env`
  local para 3 testes do diário quebrarem.

**Corrigido:** ambos os `settings.py` passaram a detectar `TESTING = "test" in sys.argv` e, sob teste,
usar **LocMemCache**, **throttle desligado** (quem o exercita reativa a taxa com `@override_settings` /
patch em `THROTTLE_RATES`, que é atributo de CLASSE lido no import — `override_settings` sozinho não o
alcança) e **Celery in-process**. Isso não substitui exercitar o worker real: o **D8** (cobrança sem
contexto de tenant) só apareceu no worker, e continua coberto por E2E no stack vivo.

### D15 — 23 knobs lidos pelo código e ausentes do `.env.example` · ✅ corrigido 19/07/2026

Auditoria 18/07/2026 (declarado × lido) achou 23 variáveis que o código lê mas nenhum `.env` documenta.
As de segurança: **`SESSION_REVOCATION_ENABLED` / `SESSION_REVOCATION_FAIL_OPEN`** (dá para **desligar a
revogação de sessão inteira** sem rastro em documentação), `IAM_COOKIE_SECURE`/`IAM_COOKIE_SAMESITE`/
`IAM_REFRESH_COOKIE`, `SECURE_SSL_REDIRECT`/`SECURE_HSTS_SECONDS`, `JWT_PRIVATE_KEY_PATH`/
`JWT_PUBLIC_KEY_PATH` (base do S3), `JWT_ISSUER` (o S8 vai precisar) e `SERVICE_TOKEN_TTL_SECONDS`.
As operacionais: `LOG_LEVEL`, `LOG_FORMAT`, `DB_CONN_MAX_AGE`, `PROMETHEUS_MULTIPROC_DIR`,
`OBSERVABILITY_SERVICE_NAME` e os timeouts de NFE.io/LLM/serviço.
**Corrigido (19/07):** os 23 estão documentados em
[deploy/env/dev.env.example](../deploy/env/dev.env.example), agrupados por assunto (Redis e a divisão de
DBs, observabilidade, timeouts de integração, tetos do S8). A verificação é mecânica e vale repetir a
cada auditoria — comparar o que o código lê com o que o exemplo declara:

```bash
grep -rhoE "os\.getenv\(\s*['\"]([A-Z0-9_]+)" --include="*.py" backend/ iam/ \
  | grep -oE "[A-Z0-9_]+$" | sort -u > /tmp/lidas.txt
grep -hoE "^#?\s*[A-Z0-9_]+=" deploy/env/dev.env.example | tr -d '#= ' | sort -u > /tmp/doc.txt
comm -23 /tmp/lidas.txt /tmp/doc.txt        # vazio = nenhum knob órfão
```

Hoje esse `comm` sai **vazio**. Foi esta auditoria que revelou o `JWT_REFRESH_DAYS` morto e o D14.

### F13 — Cliente do Orçamento contrariava o contrato do backend em 5 pontos · ✅ corrigido 25/07/2026

O hub do Orçamento quebrava a tela inteira no primeiro acesso
(`TypeError: x is not iterable`, em `montarFila`). Causa: `apiClient.get<T>` é **só um cast** — o
tipo declarado não valida nada em runtime, então uma divergência com o backend só aparece quando a
tela roda. Havia quatro, todas do mesmo feitio (envelope × lista, nome de campo):

| Endpoint | Backend devolve | Cliente esperava | Sintoma |
| --- | --- | --- | --- |
| `controle/` | `{obras, nota_realizado}` | `ControleLinha[]` | **crash** do hub (`for…of` sobre objeto) |
| `referencias/{id}/composicao/` | `{composicao, componentes}` | `ComponenteReferencia[]` | **crash** ao espiar a analítica (`.map`) |
| `referencias/adotar-lote/` | `{adotados: <contagem>, itens: [...]}` | `{adotados: number[], criados}` | **crash** ao inserir item adotado; recado "undefined item(ns)" |
| `bases-resumo/` | `insumos`/`composicoes`/`adotados_no_catalogo` | `total_insumos`/`total_composicoes`/`adotados` | cards de base com `undefined` |
| `obras/` e `etapas-obras/` | `obra_id` / `etapa_id` | `id` (em `ObraOpt`/`EtapaOpt`) | **todo seletor de obra do módulo quebrado** (ver abaixo) |

**Corrigido** no cliente ([orcamentoApi.ts](../frontend/src/modules/orcamento/api/orcamentoApi.ts) +
[types.ts](../frontend/src/modules/orcamento/types.ts)), não no backend: as respostas estão
testadas (`test_resumo_conta_itens_e_adotados`) e os nomes do resumo **não podem** virar
`total_insumos` — são anotações `Count(...)` e o model já tem campos com esse nome. O tipo do
cliente passou a descrever o que a API realmente devolve, com o desembrulho explícito em um lugar só.

O caso `ObraOpt` merece nota própria porque **não gera erro nenhum** — nem no console: com
`id` inexistente, `<option value={o.id}>` sai **sem atributo `value`** e o `<select>` passa a
devolver o *texto visível* da opção. A obra virava `NaN`→`null` no POST (400 "Este campo pode não ser
nulo") e, nos seletores que só filtram (Controlar, Cronograma, Incorporação), a tela simplesmente
não achava nada. Os seis pontos foram corrigidos; o SIL, que já usava `obra_id`, estava certo.

**Dívida que isto expõe (aberta):** nada garante o contrato entre backend e cliente. Enquanto o
`tsc -b` não roda no build da imagem (o Dockerfile do frontend usa `vite build` de propósito, por
causa de ~55 erros herdados do shell v01), o próximo desalinho volta a aparecer só na tela.
Caminho: schema gerado (`drf-spectacular` → tipos) ou validação em runtime no cliente.

### F14 — Só era possível criar **um** orçamento por obra (400 sem explicação) · ✅ corrigido 25/07/2026

`POST /api/orcamento/orcamentos/` respondia **400 "Os campos obra, versao devem criar um set
único"** em qualquer obra que já tivesse planilha. Causa: `versao` é `read_only` no serializer, então
o validador automático do DRF a checava pelo **default do modelo (1)** — e a constraint
`(obra, versao)` recusava. Os outros dois caminhos de criação já numeravam
(`revisar_orcamento`, `duplicar_orcamento`); o POST era o único que não, e nascia sempre v1.
Efeito prático: **reorçamento impossível pela tela** e a única saída era aprovar para poder revisar.

**Corrigido:** `planilha.proxima_versao(obra_id)` virou o numerador único dos três caminhos; o
serializer descarta o validador de `(obra, versao)` (o cliente não envia versão) e atribui o número
no `create`, com retry em `IntegrityError` para o POST simultâneo não virar 500. Testes
`PlanilhaAPITests.test_segundo_orcamento_da_mesma_obra_nasce_na_versao_seguinte` e
`…test_versao_do_post_continua_depois_da_revisao` (suíte do módulo: 202 ✅). Desenho registrado em
[modulos/moduloorcamento.md §4.2](modulos/moduloorcamento.md).

**Achado junto (mesmo sintoma para o usuário):** o modal "Novo orçamento" não tratava erro —
`onCriar` era chamado sem `await`/`catch`, então **qualquer** 400 virava só uma promise rejeitada no
console, com o modal aberto e nenhum recado. Agora mostra a mensagem da API e avisa, ao escolher a
obra, que a planilha nascerá como v*N*.

## 🟡 Médias

| ID  | Achado → correção                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | Status                                                             |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| S8  | backend não valida`iss`/`aud` do JWT e o DRF não tem throttling. **Corrigido 19/07:** a IAM já emitia `iss` e passou a emitir `aud`; o backend agora **exige** os dois (`ISSUER`/`AUDIENCE` no SIMPLE_JWT) — antes, qualquer token assinado com a mesma chave era aceito, viesse de onde viesse. Throttle do DRF (`anon`/`user` + `ScopedRateThrottle`) no backend e na IAM, com taxas por env; escopo `recuperacao` (30/h por origem) no endpoint público de senha, que complementa o teto de 5/h **por conta** — este não cobria rajada contra contas diferentes. A IAM ganhou cache Redis (DB 3) porque com o LocMem o teto valeria por worker do gunicorn. Testes `nucleo/test_s8_jwt_throttle.py` (6) + E2E phase5/6 no stack vivo.                                                                                                                                                                        | ✅ corrigido 19/07/2026                                            |
| S9  | PII em texto puro (CPF, endereço, dados bancários) sem mascaramento/criptografia/endpoints de titular → é a**Fase 9** (LGPD)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | ✅ mascaramento 05/07/2026 (Fase 9.C); endpoints de titular → 9.D |
| L8  | `AtualizarStatusNFView` grava status arbitrário; downloads de NF sem `timeout`. **Corrigido 16/07 (Fase 11.1):** status validado contra `StatusNFE.values` (400 se inválido); `_registrar_arquivos_nf` com `timeout=(5,30)` + nome via `urlparse().path`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | ✅ corrigido 16/07/2026                                            |
| L9  | Lote de remessa soma o**valor cheio** (usar `saldo_aberto`) e aceita título quitado/cancelado/duplicado (filtrar status + excluir já em lote ativo). **Corrigido 16/07:** `gerar-lote-remessa` soma o saldo em aberto, filtra `ABERTO/PARCIAL`, exclui título já em lote ativo (GERADO/ENVIADO/PROCESSADO) e devolve os `ignorados` (os elegíveis são materializados **antes** do `set()`, senão o próprio queryset — que exclui títulos em lote ativo — voltaria vazio depois de vincular). Testes `moduloerp.tests.L9LoteRemessaTests` (4), verdes sobre Postgres 17/07.                                                                                                                                                                                                                                                                                                                                            | ✅ corrigido 16/07/2026                                            |
| A5  | `CobrancaCliente` duplica `ContaReceber`+`Boleto` → consolidar repetindo o playbook da `Fatura`. **Levantado 25/07/2026:** confirmado que **nada escreve** em `CobrancaCliente` (nenhum service, task, seed ou signal — só o CRUD exposto em `/api/erp/cobrancas-cliente/`): a tabela está vazia e a cadeia viva é `ContaReceber`→`Boleto`. A única capacidade que ela tinha a mais — amarrar a parcela ao **contrato/unidade** — passou a existir na `ContaReceber` (FKs `cliente_empreendimento`/`contrato`, migration `moduloerp/0013`), então a consolidação virou basicamente **remover** o modelo e a rota.                                                                                                                                                                                                                                                                                  | 🔴 aberto                                                          |
| A6  | Signals do Celery gravam 2+ linhas por task com args completos e sem índice → logar só a conclusão, sem args, e indexar                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | 🔴 aberto                                                          |
| A7  | N+1 na galeria de IA e no CRM; busca de telefone O(N) em Python →`select_related`/`prefetch_related` + paginação + query no banco *(v01-B9)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | 🔴 aberto                                                          |
| A8  | Acoplamento duro ao Redis (`delete_pattern` do django-redis; sem `IGNORE_EXCEPTIONS`) → cache tolerante a queda. **Parcial 19/07:** `IGNORE_EXCEPTIONS: True` no backend e na IAM — virou obrigatório com o S8, que faz o throttle consultar a cache em TODA requisição (sem isso, Redis fora deixaria de ser lentidão e passaria a ser API inteira fora do ar). **Falta** o `delete_pattern`, que segue amarrando o código ao django-redis.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | 🟠 parcial 19/07/2026                                              |
| A9  | `except Exception → str(e)` no corpo do 500 vaza detalhes internos → mensagem genérica + traceback só no log *(v01-B7)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | 🔴 aberto                                                          |
| F3  | Acessibilidade: ordenação/linhas de tabela sem teclado,`Sheet` sem focus trap, hover via JS → handlers de teclado + focus trap + CSS *(v01-F3)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | 🔴 aberto                                                          |
| F4  | Rotas do ERP sem guard de módulo no front (403 cru) →`ModuleRoute`/`hasModule` com tela amigável. **Corrigido 13/07:** novo [`ModuleRoute`](../frontend/src/components/ModuleRoute.tsx) (layout guard por `hasModule`) envolve as rotas de ERP/CRM/RH; sem o entitlement, navegação direta por URL cai numa tela amigável ([`AccessNotice`](../frontend/src/components/AccessNotice.tsx)) em vez de 403 cru. Hub do ERP degrada o 403 de permissão (D3).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | ✅ corrigido 13/07/2026                                            |
| F9  | **Breadcrumb da topbar não conhece os módulos novos** — `SEGMENT_LABELS` em [AppTopbar.tsx](../frontend/src/components/layout/AppTopbar.tsx) não tem `sil`, `orcamento`, `orcar`, `controlar`, `cronograma`, `bases`, `incorporacao` nem `notas-fiscais`: nessas telas a trilha mostra o **slug cru** (`orcamento › orcar`), quebrando a promessa de "toda tela declara seu endereço" ([frontend.md §3.3](frontend.md)). O mapa é uma lista manual que ninguém atualiza ao criar rota. → completar os rótulos e, de preferência, derivá-los do catálogo de páginas de cada módulo (o Orçamento já tem o seu em `modules/orcamento/paginas.ts`) em vez de manter uma segunda lista.                                                                                                                                                                                                                           | 🔴 aberto                                                          |
| F10 | **`--topbar-h` não existe** — [PaginaShell.tsx](../frontend/src/modules/orcamento/components/PaginaShell.tsx) dimensiona as páginas do Orçamento com `calc(100vh - var(--topbar-h, 56px))`, mas **nenhum arquivo declara** essa variável (nem `index.css`, nem o `AppTopbar`, cuja altura real vem de `padding: 12px` + conteúdo). Sempre cai no fallback, então a grade com `semRolagem` (Orçar) fica com altura errada por alguns pixels — rolagem dupla ou faixa cortada. → declarar `--topbar-h` no `AppShell`/`index.css` a partir da altura real da topbar (ou medir por `ResizeObserver`), já que outros módulos vão precisar do mesmo cálculo.                                                                                                                                                                                                                                                            | 🔴 aberto                                                          |
| F11 | **Duas listas de módulos que divergem** — o farol da sidebar (`NAV_SECTIONS` em [AppSidebar.tsx](../frontend/src/components/layout/AppSidebar.tsx)) e o catálogo do hub (`CATALOGO` em [pages/app/home/catalogo.ts](../frontend/src/pages/app/home/catalogo.ts)) descrevem o mesmo conjunto com vocabulários diferentes (`implemented: boolean` × `situacao: pronto/backend/planejado`) e **já discordam**: Drone é `implemented: false` num e `situacao: 'backend'` no outro; Maps/DMS/APS/PDCA/terrenos/viabilidade estão no hub e não na sidebar. Como os dois são "o farol da edição" ([frontend.md §3.2](frontend.md)), o usuário vê dois inventários da mesma casa. → uma fonte só (o `CATALOGO`, que é mais rico), com a sidebar derivando dela o seu recorte — mesmo remédio do `paginas.ts` do Orçamento, que já resolveu isso dentro do módulo.                                                     | 🔴 aberto                                                          |
| F12 | **A convenção de estilo escrita não é a praticada** — [frontend-convencoes.md](frontend-convencoes.md) manda "Tailwind classes inline; `cn()` para condicionais; sem arquivos `.css` por componente", mas **todo** o código nascido na Malha (sidebar, topbar, hub da home, SCM, SIL, Orçamento) é escrito com objetos `style={{}}` inline, sem Tailwind e sem `cn()`. Some-se a isso **quatro kits de UI paralelos** (`components/malha/` + kit local do SCM + `sil/ui.tsx` + `orcamento/ui.tsx`, cada um com seu `Card`/`Pill`/`Btn`/`Modal`) — a dívida dos kits já está declarada em [frontend.md §2](frontend.md), a da convenção não. Quem ler o documento antes de escrever a próxima tela vai escrever no padrão errado. → decidir o padrão de fato (inline `style` + tokens parece ser o vencedor) e reescrever a regra; e datar a migração dos kits locais para `components/malha/`. | 🔴 aberto                                                          |
| D7  | Recurso`erp.nf` não tinha `.edit` no catálogo → os 3 ViewSets de NF e `AtualizarStatusNFView` (POST→`.edit`) só passavam por admin; `ConsultarStatusNFView`, sendo **leitura**, exigia `.edit` indevidamente. Surgiu explícito ao remover o fallback de papel (fatia E). **Corrigido 12/07:** `erp.nf.edit` criado no catálogo (persona `fiscal` herda via `erp.nf.*`, `sync_authz` aditivo propaga no boot); `ConsultarStatusNFView` passou a exigir `erp.nf.view`. Testes `moduloerp.tests.D7NfApiViewPermissionTests` (4).                                                                                                                                                                                                                                                                                                                                                                                     | ✅ corrigido 12/07/2026                                            |

## 🟢 Baixas

| ID  | Achado → correção                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Status                  |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------- |
| A10 | Higiene do repo:`nul`, `terminal*.txt`, scripts soltos na raiz → remover + `.gitignore` *(v01-G1)*. **Parcial 19/07:** o que tinha valor foi movido em vez de apagado — `terminal.txt` (guia de comandos atualizado) → [docs/comandos.md](comandos.md), `test_browser.py` → `infra/gateway/browser_smoke_test.py`, `serve_spa.py` → `infra/`. Docker e env saíram da raiz para [deploy/](../deploy/README.md). `.gitignore` ganhou `_verify_*.txt` e — achado no caminho — teve os padrões de virtualenv **ancorados** (`/env/` em vez de `env/`): sem a âncora, `env/` casava qualquer diretório com esse nome e escondia o `deploy/env/` inteiro, incluindo os modelos que precisam ser versionados. **Falta (exige decisão/ação do dono do repo):** (a) apagar 4 arquivos mortos na raiz — `nul` (um 502 do nginx capturado por engano), `_verify_testes.txt` (resíduo do bridge PHP removido) e `package.json`/`package-lock.json` (vestígio do monorepo Node; **nada os referencia** — o CI usa `frontend/package-lock.json`); (b) decidir o `requirements.txt` da RAIZ — não é usado por CI nem por Dockerfile algum (esses usam `backend/` e `iam/`), mas é plausível que seja o manifesto do `.venv` que roda as duas suítes localmente, e por isso **não foi tocado**. Se for isso, vale torná-lo explícito (`requirements-dev.txt`, somando backend+iam, hoje desatualizado: falta `django-redis`); se não, pode sair.                                                                                                                             | 🟠 parcial 19/07/2026   |
| A11 | Sem testes/CI — o L1 seria pego por um smoke test de 1 linha → pipeline mínima (Fase 10.5)*(v01-G2)*. **Corrigido 14/07:** GitHub Actions ([.github/workflows/ci.yml](../.github/workflows/ci.yml)) roda backend (Django+Postgres, RLS real), iam e frontend a cada push/PR.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | ✅ corrigido 14/07/2026 |
| A12 | Modelagem: validador CPF/CNPJ sem dígito verificador no backend;`Boleto.VENCIDO` nunca setado; rota duplicada `/api/api/`; duplicata no fallback de tipos de IA *(v01-B8)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | 🔴 aberto               |
| F5  | Código morto/duplicado no frontend (duas gerações de páginas, dois`ObraDetailPage`) → remover a geração antiga *(v01-F4)*. **Inventário confirmado 25/07/2026** (nada disto é alcançável a partir de [App.tsx](../frontend/src/App.tsx)): (a) **ilha de obras** — `modules/obras/ObraDetailPage.tsx` e `ObrasListPage.tsx` na raiz do módulo (duplicatas das versões em `pages/`, que são as roteadas) + os `.module.css` de ambas; elas são as **únicas** consumidoras de todo `components/obra/**` (blueprint · documentslist · finances · ganttchart · interactivemap · kpidashboard · obratimeline · storage, com CSS) e de `hooks/useObraData.ts` — ~18 arquivos que só se referenciam entre si; (b) **avulsos** — `pages/AppStubPage.tsx`, `pages/Clientes.tsx`, `pages/Login.tsx` (a viva é `LoginPage.tsx`), `components/layout/MainLayout.tsx` + `Sidebar.tsx` (+CSS, substituídos pelo `AppShell`), `components/clientes/ClienteForm.tsx` (a viva é `modules/clientes/components/ClienteForm.tsx`), `modules/empreendimentos/pages/EmpreendimentosPage.tsx`, `modules/drone/pages/MapeamentoDronePage.tsx`. Sintoma de que a ilha está mesmo morta: `GanttChart.tsx` importa **`frappe-gantt`, que não consta do `package.json`** — só não quebra porque o `types/frappe-gantt.d.ts` satisfaz o `tsc` e o Vite nunca chega a resolver o módulo (nada o alcança). Esse `.d.ts` sai junto. *(Este `F5` é o da tabela — não confundir com o `### F5` da seção Altas, do `.gitignore`; colisão de IDs herdada dos dois laudos.)* | 🔴 aberto               |
| F6  | Sem`ErrorBoundary` nem padrão de loading/erro/vazio; i18n ausente → padronizar componentes de estado                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | 🔴 aberto               |
| C1  | **Calendário Fatia C (14/07):** lembretes de **série recorrente** só definidos na criação — editar "só esta"/"série" não os altera. **Corrigido 14/07/2026:** `update-recurrence` sincroniza `reminders` nos três escopos — `all` substitui os do mestre (valem p/ todas as ocorrências virtuais), `future` abastece o novo mestre e o truncado conserva os seus, `this` no override; ausência de `reminders` no payload **herda os do mestre** (novo `_reminders_for`), não perde aviso. Front parou de fazer `delete payload.reminders`. Testes `CalendarRecurrenceTests` (4 novos, suíte 25/25) + E2E vivo pelo gateway (all/this/future). Canal **WhatsApp** segue adiado (hoje in-app + e-mail).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | ✅ corrigido 14/07/2026 |
| C2  | **Calendário Fatia C (14/07):** suíte DB-backed + E2E/typecheck do sino pendentes na entrega (Postgres/Docker fora). **Validado 14/07/2026:** suíte **27/27** sobre Postgres (role `erp_app`, RLS real) — `modulocalendar` (reminders CRUD + `LembreteDispatchTests`) + `nucleo.test_notificacoes`; **typecheck** `tsc -b` limpo nos arquivos da Fatia C (os 33 erros restantes são do shell legado, fora da fatia); **E2E vivo pelo gateway** — evento com lembrete `[0]` → beat@60s + worker `despachar_lembretes` → `Notificacao` in-app (badge, texto, `marcar-todas-lidas`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | ✅ validado 14/07/2026  |

---


## Duas coisas para decidir sobre moduloorcamento

**`pdfplumber` entrou no `requirements.txt`.** É dependência nova e passa pelos gates de `pip-audit`/Dependabot. O código faz import tardio e degrada com mensagem clara se faltar — se preferir não adicionar dependência agora, é só remover a linha que o resto continua funcionando sem o caminho PDF.

 **Nenhuma permissão nova foi criada** , de propósito: manter banco de preço usa `orcamento.orcamento.edit`, importar usa `orcamento.base.adotar`. Se na sua operação "quem cuida do banco de preço" for uma pessoa diferente de "quem orça", vale criar `orcamento.banco.*` — mas isso exige rebuild da imagem `sgi-iam` e re-seed, que eu não teria como validar aqui.

## Ideias de novas funcionalidades (backlog, sem compromisso)

Consolidadas das duas revisões; assumem os críticos corrigidos. Ordenadas por valor × esforço.

**Ganhos rápidos:** credencial Asaas por tenant · portal do cliente (2ª via de boleto/PIX) ·
notificações de vencimento (e-mail/WhatsApp) · exportar relatórios (Excel/PDF) · importador de XML
de NF-e → pré-lançamento de contas a pagar · vínculo automático NF ↔ conta pela chave de acesso ·
fluxo de caixa projetado (D+30/60/90) · centro de notificações in-app.

**Médio prazo:** trilha de auditoria completa (vira Fase 9.5) · conciliação bancária e retorno
CNAB · financeiro por obra (curva S / margem — vira D.1.4) · hub de módulos com estado de
assinatura/upsell · medição de empreiteiros (contrato → medições → conta a pagar) · apontamento de
mão de obra por obra (RH → custo real) · slice 2 do Asaas (PIX QR, parcelamento,
cancelamento/estorno) · comprovante anexado à baixa.

**Estratégico:** integração contábil / SPED · app de campo (PWA offline) para o diário de obra ·
observabilidade e operação (vira Fase 10) · orçamento de obra por etapa (orçado × comprometido ×
realizado) · assinatura eletrônica de contratos.
