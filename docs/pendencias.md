# Pendências — revisão técnica consolidada

> **Documento único** que consolida os dois laudos de revisão de 02/07/2026 (v01: segurança;
> v02: bugs/arquitetura/frontend) **e** serve de rastreador vivo. Os laudos originais foram
> absorvidos aqui e excluídos. Cada achado traz problema e direção de correção; ao corrigir,
> troque o status para `✅ corrigido DD/MM/AAAA`
> IDs: `S*` segurança · `L*` bugs de lógica · `A*` backend/arquitetura ·
> `F*` frontend · `D*` achados de auditoria posteriores.

**Ordem de ataque recomendada:**

1. **L1–L4** — módulos inoperantes (**✅ todos corrigidos 03/07/2026**).
2. **S1–S4** — pré-requisito para operar como SaaS real (**S1+S2 ✅ 04/07/2026**: RLS armada na
   autenticação + política fail-closed fecharam a classe do vazamento entre tenants; faltam **S3, S4**).
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
(2º tenant `acme` no seed). **Pendente correlato:** `/api/v1/chunks/*/assets/*` segue `permitAll`
(download público por UUID) — revisar em **10.8** junto do auth de WebSocket/serviço→serviço.

### S3 — Fallback HS256 com segredo compartilhado · 🔴 aberto · Fase 10

Sem `JWT_PUBLIC_KEY_PATH`, IAM e ERP caem em HS256 com o mesmo `JWT_SECRET` — quem valida também
**assina**: qualquer serviço (ou `.env` vazado) forja tokens de qualquer usuário/tenant.
**Correção:** em produção, **exigir RS256** (`ImproperlyConfigured` se a chave faltar); manter
HS256 só como opção explícita de dev; evoluir para validação via JWKS + `kid` (rotação sem deploy).

### S4 — Defaults inseguros ligados por omissão · 🔴 aberto

`DEBUG=True`, `SECRET_KEY` e `JWT_SECRET` têm fallback embutido (ERP e IAM): produção sem as
variáveis **sobe silenciosamente** com stack traces expostos e segredos conhecidos.
**Correção:** default `DEBUG=False`; **falhar-rápido** se `SECRET_KEY`/`JWT_SECRET`/
`ALLOWED_HOSTS` faltarem fora de DEBUG; ligar cookies/HSTS de produção; `manage.py check --deploy` como gate no CI.

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

### D3 — UI e dashboards do ERP não sincronizam estado após criação/baixa · 🔴 aberto

Ao criar um `Cliente`, ele não entra imediatamente no fluxo de cobrança até recarregar a página (browser);
ao gerar boleto, as divergências/pêndencias entre Asaas e banco/ERP não aparecem da mesma forma quando coloco em criar cliente;
os gráficos de custos e recebimentos do ERP não carregam ou ficam defasados; e, após clicar em
dar baixa, o boleto continua sendo exibido como `emitido` como se a mudança não tivesse sido
aplicada. **Direção de correção:** revisar a invalidação/refetch das queries no frontend após
mutação, garantir que as telas de cobrança e dashboard busquem o estado atualizado no backend e
confirmar que o status de baixa é persistido e refletido na listagem antes de renderizar os cards
e gráficos.

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

### A3 — Uniques por tenant + `tenant` NOT NULL · ✅ corrigido 04/07/2026 · Fase 8.2/8.3 *(v01-B1/B6)*

Unicidade global (CPF/CNPJ, e-mail, nº NF) impedia dois tenants de cadastrarem o mesmo documento e
`tenant` nullable era furo de isolamento. **Corrigido:** `tenant` **NOT NULL** (8.2) + cada
`unique=True` global escalar virou `UniqueConstraint(fields=["tenant", …])` (8.3), com validador DRF
escopado ao tenant (400 limpo em duplicata).

### A4 — Upload sem validação server-side · 🔴 aberto *(v01-B2)*

Tipo/tamanho só são validados no cliente. **Correção:** validador no backend reutilizando a
`UploadConfig` (mesmos limites do `/api/configuracoes/upload/`), aplicado a todo `FileField`.

### D3 — `tenant` obrigatório no POST quebra a criação via API · 🟠 parcial (05/07/2026)

Regressão da **Fase 8.2** (`tenant` virou NOT NULL): o DRF passou a **exigir `tenant` no payload**,
mas o `perform_create` do `TenantScopedViewSetMixin` injeta o tenant **depois** do `is_valid()` → todo
`POST` de recurso tenant-scoped cujo serializer usa `fields='__all__'` **sem** `read_only_fields=['tenant']`
responde **400 "tenant é obrigatório"** (o front não envia tenant). Descoberto ao criar cargo/funcionário.
**Corrigido (05/07):** `tenant` read-only nos serializers de **RH** (Cargo, Funcionario, DadoMedico,
ASO, Documento, DadoBancario, Pagamento, Folha) e **fornecedores** (`clientes` já tinha). **Pendente:**
varredura sistêmica dos demais apps (moduloerp, empreendimentos, obras, modulocrm…) — provável que
vários tenham o mesmo furo; ideal um serializer-base tenant-scoped que force `tenant` read-only.

### D4 — `RequirePermission` é fail-open com `permissions` vazia · 🟡 mitigado na LGPD (05/07/2026)

Como a autenticação sempre seta `iam_permissions = [...] or []`, não há como distinguir "token legado
sem a claim" de "usuário sem nenhuma permissão" — e o fallback de transição (`permissions` vazia → cai
no `RequireRole`) **libera** quem não tem papel exigido em endpoints sem `required_role`. **Mitigado:**
os endpoints LGPD (novos, sensíveis) usam `RequirePermissionStrict` (fail-closed, sem fallback).
**Pendente:** revisar o fallback do `RequirePermission` para RH/CRM (hoje o CRM depende dele) —
aposentá-lo junto da fatia **E** (remoção do `RequireRole`), tornando tudo fail-closed.

### D5 — Cadastros-base sem camada 2 (broken access control) · 🟠 parcial (05/07/2026)

Relatado por teste do usuário: `semdrone` (papel **operacional**, só `cadastro.cliente.view`)
**criou e editou clientes e criou uma "venda"** (`ClienteEmpreendimento`) — só não viu o CPF (mascarado
pela 9.C). Causa: a **fatia B** (`RequirePermission`) só fora aplicada a **RH e CRM**; os cadastros-base
(`clientes`, `fornecedores`, `obras`, `empreendimentos`) tinham apenas `IsAuthenticated` → qualquer papel
escrevia. O mascaramento de campo protege o **campo**, não a **operação** de escrita.
**Corrigido (05/07):** `RequirePermission` + `required_resource` em todos os viewsets de `clientes`
(`cadastro.cliente`/`cadastro.cliente_banco`), `fornecedores`, `obras` (`obra.obra`) e `empreendimentos`
(`obra.empreendimento`/`empreend_conta`/`empreend_custo`). Provado: `semdrone` vê (200) mas não escreve
(403); `demo` (comercial/engenharia) cria normalmente. `modulodiario` já tinha ABAC próprio
(`PodeModerarDiario`). **Pendente:** varrer `modulocalendar`, `moduloapi`, `funcoesia` e revisar o
`moduloerp` (hoje `RequireRole("financeiro")` — migrar p/ `RequirePermission`), fechando a fatia B em
todo o backend. Some-se a isto o **D3** (tenant read-only nos serializers de obras/empreendimentos) e o
**D4** (fail-open do fallback com permissões vazias).

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

### F1 — Sessão expira sem refresh + sem 401 global · 🔴 aberto *(v01-F1/F2)*

O access token vale 60 min e o front não usa o refresh; 401 não desloga nem redireciona.
**Correção:** interceptor de resposta — 401 → `POST /auth/refresh` → retry; falhou → logout com
aviso.

### F2 — Selects carregam tabelas inteiras · 🔴 aberto

Formulários carregam todos os clientes/fornecedores/empreendimentos para montar selects.
**Correção:** select assíncrono com busca server-side paginada (o backend precisa de
`SearchFilter` + paginação nesses endpoints).

## 🟡 Médias

| ID | Achado → correção                                                                                                                                                              | Status    |
| -- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| S8 | ERP não valida`iss`/`aud` do JWT e o DRF não tem throttling → configurar `ISSUER`/`AUDIENCE` no SIMPLE_JWT e `DEFAULT_THROTTLE_*`                                    | 🔴 aberto |
| S9 | PII em texto puro (CPF, endereço, dados bancários) sem mascaramento/criptografia/endpoints de titular → é a**Fase 9** (LGPD)                                            | ✅ mascaramento 05/07/2026 (Fase 9.C); endpoints de titular → 9.D |
| L8 | `AtualizarStatusNFView` grava status arbitrário (validar contra `StatusNFE.values`); downloads de NF sem `timeout` (usar `timeout=(5,30)` + `urlparse().path` no nome) | 🔴 aberto |
| L9 | Lote de remessa soma o**valor cheio** (usar `saldo_aberto`) e aceita título quitado/cancelado/duplicado (filtrar status + excluir já em lote ativo)                     | 🔴 aberto |
| A5 | `CobrancaCliente` duplica `ContaReceber`+`Boleto` → consolidar repetindo o playbook da `Fatura`                                                                          | 🔴 aberto |
| A6 | Signals do Celery gravam 2+ linhas por task com args completos e sem índice → logar só a conclusão, sem args, e indexar                                                       | 🔴 aberto |
| A7 | N+1 na galeria de IA e no CRM; busca de telefone O(N) em Python →`select_related`/`prefetch_related` + paginação + query no banco *(v01-B9)*                             | 🔴 aberto |
| A8 | Acoplamento duro ao Redis (`delete_pattern` do django-redis; sem `IGNORE_EXCEPTIONS`) → cache tolerante a queda                                                              | 🔴 aberto |
| A9 | `except Exception → str(e)` no corpo do 500 vaza detalhes internos → mensagem genérica + traceback só no log *(v01-B7)*                                                   | 🔴 aberto |
| F3 | Acessibilidade: ordenação/linhas de tabela sem teclado,`Sheet` sem focus trap, hover via JS → handlers de teclado + focus trap + CSS *(v01-F3)*                            | 🔴 aberto |
| F4 | Rotas do ERP sem guard de módulo no front (403 cru) →`ModuleRoute`/`hasModule` com tela amigável                                                                           | 🔴 aberto |

## 🟢 Baixas

| ID  | Achado → correção                                                                                                                                                              | Status    |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| A10 | Higiene do repo:`nul`, `terminal*.txt`, scripts soltos na raiz → remover + `.gitignore` *(v01-G1)*                                                                       | 🔴 aberto |
| A11 | Sem testes/CI — o L1 seria pego por um smoke test de 1 linha → pipeline mínima (Fase 10.5)*(v01-G2)*                                                                         | 🔴 aberto |
| A12 | Modelagem: validador CPF/CNPJ sem dígito verificador no backend;`Boleto.VENCIDO` nunca setado; rota duplicada `/api/api/`; duplicata no fallback de tipos de IA *(v01-B8)* | 🔴 aberto |
| F5  | Código morto/duplicado no frontend (duas gerações de páginas, dois`ObraDetailPage`) → remover a geração antiga *(v01-F4)*                                              | 🔴 aberto |
| F6  | Sem`ErrorBoundary` nem padrão de loading/erro/vazio; i18n ausente → padronizar componentes de estado                                                                          | 🔴 aberto |

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