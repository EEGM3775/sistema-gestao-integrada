# Pendências — revisão técnica consolidada

> **Documento único** que consolida os dois laudos de revisão de 02/07/2026 (v01: segurança;
> v02: bugs/arquitetura/frontend) **e** serve de rastreador vivo. Os laudos originais foram
> absorvidos aqui e excluídos. Cada achado traz problema e direção de correção; ao corrigir,
> troque o status para `✅ corrigido DD/MM/AAAA` e registre a entrega no
> [historico.md](historico.md). IDs: `S*` segurança · `L*` bugs de lógica · `A*` backend/arquitetura ·
> `F*` frontend · `D*` achados de auditoria posteriores.

**Ordem de ataque recomendada:**
1. **L1–L4** — módulos inoperantes (**✅ todos corrigidos 03/07/2026**).
2. **S1–S4** — pré-requisito para operar como SaaS real (S1+S2 juntos: RLS por middleware + fail-closed resolve a classe inteira).
3. **L5–L7 + A1** — pacote "integridade financeira sob concorrência" (mesma sprint).
4. O restante por severidade, aproveitando as fases do [roadmap](roadmap.md) indicadas.

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
**Falta a parte estrutural (S2):** RLS fail-closed + armar o tenant em middleware fecha a classe
inteira (todo caminho fora do mixin — comando, shell, task, webhook).

### S2 — RLS fail-open · 🔴 aberto · Fase 8.4
A política RLS (`nucleo/migrations/0007`) **libera todas as linhas** quando `app.current_tenant`
não está setado — e só o mixin o seta. Qualquer caminho fora dele (APIView, comando, shell, task,
webhook) roda sem proteção, silenciosamente.
**Correção:** (a) armar a RLS em **middleware/base view** para toda requisição autenticada;
(b) política **fail-closed** (`USING (tenant_id::text = current_setting(...))`), com role
`BYPASSRLS` explícita para migrações/jobs.

### S3 — Fallback HS256 com segredo compartilhado · 🔴 aberto · Fase 10
Sem `JWT_PUBLIC_KEY_PATH`, IAM e ERP caem em HS256 com o mesmo `JWT_SECRET` — quem valida também
**assina**: qualquer serviço (ou `.env` vazado) forja tokens de qualquer usuário/tenant.
**Correção:** em produção, **exigir RS256** (`ImproperlyConfigured` se a chave faltar); manter
HS256 só como opção explícita de dev; evoluir para validação via JWKS + `kid` (rotação sem deploy).

### S4 — Defaults inseguros ligados por omissão · 🔴 aberto
`DEBUG=True`, `SECRET_KEY` e `JWT_SECRET` têm fallback embutido (ERP e IAM): produção sem as
variáveis **sobe silenciosamente** com stack traces expostos e segredos conhecidos.
**Correção:** default `DEBUG=False`; **falhar-rápido** se `SECRET_KEY`/`JWT_SECRET`/
`ALLOWED_HOSTS` faltarem fora de DEBUG; ligar cookies/HSTS de produção; `manage.py check
--deploy` como gate no CI.

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

### L4 — Integração `funcoeslead` ↔ ERP morta · ✅ corrigido 03/07/2026 (Fase 11.2 antecipada)
O serviço Node autentica com `Authorization: Token …`; desde a Fase 6 o ERP só aceita **JWT da
IAM** → tudo recebe 401. Agravante: os ViewSets do CRM não configuram `filter_backends`, então os
filtros da agenda (`assigned_to_id`, `due_date__gte`…) seriam ignorados mesmo autenticado.
**Correção recomendada:** antecipar a **Fase 11.2** (conversão de lead vira signal handler Python
em `modulocrm` — o problema desaparece por construção). Alternativa de curto prazo: JWT de serviço
emitido pela IAM + `DjangoFilterBackend`/`filterset_fields` no `InteractionViewSet`.

### D1 — Callbacks Node→ERP usam o Token morto · 🔴 confirmado por teste 03/07/2026 · Fase 11
`funcoesia` (`services/apiService.js`), `funcoesnf` (`config.js`) e `funcoeswhatsapp`
(`services/apiClient.js`) usam o `DJANGO_API_TOKEN` legado — análise de IA, atualização de status
de NF e o bot recebem 401. **Confirmado por teste** (`nucleo/test_legacy_token.py`): todos os
endpoints-alvo exigem JWT da IAM e respondem 401 ao header `Token` (o `/api/log-interno/` também,
então nem o log central recebe os eventos). O `funcoeslead` saiu da lista: absorvido (L4).
**Correção:** Fase 11 (absorção em Python, caminho preferido) ou JWT de serviço (Fase 10.8).

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

### S5 — Bypass de entitlement no CRM · 🔴 aberto
`OpportunityProductViewSet` não declara `RequireModule` — tenant sem o módulo `crm` acessa
`/api/crm/opportunity-products/`. **Correção:** `required_module = "crm"`; criar `CrmBaseViewSet`
para todas as views herdarem + teste que varre o router exigindo `required_module` em módulo pago.

### S6 — Rotas do `funcoeslead` sem autenticação · ✅ resolvido 03/07/2026 (serviço descomissionado — absorvido na Fase 11.2)
O serviço tem o middleware `iamAuth` mas **não o aplica**; quem alcança a porta 3004 executa
ações com o token de serviço. **Correção:** aplicar `requireModule('crm')` nas rotas; rede Docker
interna sem porta publicada; segredo dedicado por serviço nas chamadas internas.

### S7 — Segredos de serviço fracos · 🔴 aberto · Fase 10.3
`IA_SERVICE_SECRET_TOKEN` tem fallback público no código; o token do webhook Asaas é comparado
com `!=` (não constante). **Correção:** sem fallback (ausente = erro em prod);
`hmac.compare_digest` no webhook.

### L5 — Corrida na baixa (sem lock de linha) · 🔴 aberto *(v01-B3)*
`dar_baixa` faz read-modify-write sem `select_for_update`, e agora há dois produtores reais
(baixa manual × webhook Asaas). **Correção:** `select_for_update()` dentro de
`transaction.atomic()` nos dois caminhos; só é efetivo no Postgres → junto com a Fase 8.1.

### L6 — Edição de título não revalida consistência · 🔴 aberto
`PATCH` pode reduzir `valor` abaixo de `valor_pago` (saldo negativo); rateios existentes não são
revalidados quando só o `valor` muda; `BaixaSerializer` aceita baixa **maior** que o saldo.
**Correção:** `validate()` nos serializers (valor ≥ valor_pago; rateios fecham com o novo valor);
baixa com excesso cai na fila `RevisaoBaixa` (mesma filosofia do guard existente).

### L7 — `Transacao.data_transacao = auto_now_add` · 🔴 aberto *(v01-B5)*
A data real do pagamento (inclusive a do webhook Asaas) não vai para o ledger → fluxo de caixa
mensal no mês errado. **Correção:** campo editável (`DateTimeField`), `dar_baixa` grava a data da
baixa; opcional `data_lancamento` separado para auditoria.

### A1 — Celery sem executor no deploy · 🔴 aberto · Fase 10
O compose não tem serviços `worker`/`beat` — em produção as tasks enfileiram para sempre (o
webhook hoje processa síncrono). **Correção:** adicionar `worker` (e `beat` se houver agendadas)
ao compose com healthcheck.

### A2 — Microsserviços fora do compose + URLs fixas · 🔴 aberto · Fase 11 *(v01-B4)*
`funcoesnf`/`funcoeswhatsapp` não estão no `docker-compose.yml` e o ERP os chama em
`localhost:300x` fixo (o `funcoeslead` foi absorvido — Fase 11.2). **Correção:** entrar no compose
com URLs via env — ou antecipar o resto da Fase 11 e eliminá-los.

### A3 — Uniques por tenant + `tenant` NOT NULL · 🔴 aberto · **Fase 8** *(v01-B1/B6)*
Unicidade global (CPF/CNPJ, e-mail, nº NF) impede dois tenants de cadastrarem o mesmo documento e
`tenant` nullable é furo de isolamento. É exatamente o escopo da Fase 8 do roadmap.

### A4 — Upload sem validação server-side · 🔴 aberto *(v01-B2)*
Tipo/tamanho só são validados no cliente. **Correção:** validador no backend reutilizando a
`UploadConfig` (mesmos limites do `/api/configuracoes/upload/`), aplicado a todo `FileField`.

### F1 — Sessão expira sem refresh + sem 401 global · 🔴 aberto *(v01-F1/F2)*
O access token vale 60 min e o front não usa o refresh; 401 não desloga nem redireciona.
**Correção:** interceptor de resposta — 401 → `POST /auth/refresh` → retry; falhou → logout com
aviso.

### F2 — Selects carregam tabelas inteiras · 🔴 aberto
Formulários carregam todos os clientes/fornecedores/empreendimentos para montar selects.
**Correção:** select assíncrono com busca server-side paginada (o backend precisa de
`SearchFilter` + paginação nesses endpoints).

## 🟡 Médias

| ID | Achado → correção | Status |
|---|---|---|
| S8 | ERP não valida `iss`/`aud` do JWT e o DRF não tem throttling → configurar `ISSUER`/`AUDIENCE` no SIMPLE_JWT e `DEFAULT_THROTTLE_*` | 🔴 aberto |
| S9 | PII em texto puro (CPF, endereço, dados bancários) sem mascaramento/criptografia/endpoints de titular → é a **Fase 9** (LGPD) | 🔴 aberto |
| L8 | `AtualizarStatusNFView` grava status arbitrário (validar contra `StatusNFE.values`); downloads de NF sem `timeout` (usar `timeout=(5,30)` + `urlparse().path` no nome) | 🔴 aberto |
| L9 | Lote de remessa soma o **valor cheio** (usar `saldo_aberto`) e aceita título quitado/cancelado/duplicado (filtrar status + excluir já em lote ativo) | 🔴 aberto |
| A5 | `CobrancaCliente` duplica `ContaReceber`+`Boleto` → consolidar repetindo o playbook da `Fatura` | 🔴 aberto |
| A6 | Signals do Celery gravam 2+ linhas por task com args completos e sem índice → logar só a conclusão, sem args, e indexar | 🔴 aberto |
| A7 | N+1 na galeria de IA e no CRM; busca de telefone O(N) em Python → `select_related`/`prefetch_related` + paginação + query no banco *(v01-B9)* | 🔴 aberto |
| A8 | Acoplamento duro ao Redis (`delete_pattern` do django-redis; sem `IGNORE_EXCEPTIONS`) → cache tolerante a queda | 🔴 aberto |
| A9 | `except Exception → str(e)` no corpo do 500 vaza detalhes internos → mensagem genérica + traceback só no log *(v01-B7)* | 🔴 aberto |
| F3 | Acessibilidade: ordenação/linhas de tabela sem teclado, `Sheet` sem focus trap, hover via JS → handlers de teclado + focus trap + CSS *(v01-F3)* | 🔴 aberto |
| F4 | Rotas do ERP sem guard de módulo no front (403 cru) → `ModuleRoute`/`hasModule` com tela amigável | 🔴 aberto |

## 🟢 Baixas

| ID | Achado → correção | Status |
|---|---|---|
| A10 | Higiene do repo: `nul`, `terminal*.txt`, scripts soltos na raiz → remover + `.gitignore` *(v01-G1)* | 🔴 aberto |
| A11 | Sem testes/CI — o L1 seria pego por um smoke test de 1 linha → pipeline mínima (Fase 10.5) *(v01-G2)* | 🔴 aberto |
| A12 | Modelagem: validador CPF/CNPJ sem dígito verificador no backend; `Boleto.VENCIDO` nunca setado; rota duplicada `/api/api/`; duplicata no fallback de tipos de IA *(v01-B8)* | 🔴 aberto |
| F5 | Código morto/duplicado no frontend (duas gerações de páginas, dois `ObraDetailPage`) → remover a geração antiga *(v01-F4)* | 🔴 aberto |
| F6 | Sem `ErrorBoundary` nem padrão de loading/erro/vazio; i18n ausente → padronizar componentes de estado | 🔴 aberto |

---

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
