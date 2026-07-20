# Canal de comunicação WhatsApp (`funcoeswhatsapp`)

> **Canal conversacional do SaaS** — a porta de entrada e saída por WhatsApp para **todos** os módulos,
> não só o diário/IA. Recebe webhooks da Meta (WhatsApp Cloud API), conduz fluxos de conversa com estado
> no Redis e age sobre o backend; contatos desconhecidos viram lead. É um **app Django**:
> [backend/funcoeswhatsapp/](../../backend/funcoeswhatsapp/) (webhook + Celery, in-process).
>
> ✅ **Reescrito Node → Python** (Fase C.0–C.4; ver [roadmap](../roadmap.md)). O serviço Node foi
> **removido**: o webhook é a rota `/webhooks/whatsapp` do backend (autentica pela assinatura HMAC da
> Meta, não por JWT) e o processamento roda no worker Celery. Fecha o **A2** e a parte WhatsApp do **D1**
> (não há mais callback com o `Token` legado). O diário/IA (a que este canal alimenta) tem o
> [plano de reintegração](../arquitetura/diario-ia-reintegracao.md).

## 1. Papel no sistema

O WhatsApp é o **canal de comunicação** do SaaS: onde funcionários, clientes e fornecedores conversam com
a plataforma sem abrir o app web. É **bidirecional** (recebe mensagens e envia respostas/notificações),
**multi-fluxo** (o diário de obra é o primeiro de muitos — §5) e **multi-tenant** (cada tenant com seu
número/credenciais Meta). O diário/IA é **um cliente** deste canal, não o seu propósito.

## 2. Estado atual (app Django)

O canal é o app `funcoeswhatsapp` no backend. A borda ([views.py](../../backend/funcoeswhatsapp/views.py))
recebe o webhook da Meta, valida a assinatura HMAC (app secret **do tenant**), resolve o tenant pelo
`phone_number_id`, deduplica por `message.id` e **enfileira**, respondendo `200` em milissegundos. O worker
Celery ([tasks.py](../../backend/funcoeswhatsapp/tasks.py)) identifica o remetente por telefone (tenant-scoped),
mantém o estado da conversa no Redis e age **in-process** pelo ORM sob `tenant_context` — sem chamar a
própria API por HTTP e sem token de serviço no caminho feliz. Fluxos: **diário de obra** e **pré-cadastro →
lead**. O antigo servidor Node foi **removido** (Fase C.4).

> **Histórico:** até 15/07/2026 este era um microsserviço Node dedicado, inoperante desde a Fase 6 (usava
> `Authorization: Token …`, rejeitado com 401 — [D1](../pendencias.md)) e fora do compose ([A2](../pendencias.md)).

## 3. Desenho-alvo (Python) — princípios

1. **Zero novo container.** O webhook é uma **rota Django** no backend existente; o processamento roda no
   **worker Celery** já provido (Fase 10.9). A superfície **diminui** (−1 Node), fechando [A2](../pendencias.md).
2. **In-process, sem auto-HTTP.** Dentro do backend, o processamento escreve direto pelo ORM sob contexto
   de tenant — não chama a própria API por HTTP. Segue o precedente da **Fase B**
   ([funcoesia/tasks.py](../../backend/funcoesia/tasks.py)): `rls_bypass()` resolve o tenant,
   `tenant_context()` grava. Alinhado ao **AD-8** e ao **CLAUDE.md** (Django app, nunca novo microsserviço).
3. **Tenant-first.** O tenant é resolvido **na borda**, pelo número que **recebeu** a mensagem, não pelo
   remetente (§4.1).
4. **Núcleo de canal + fluxos plugáveis.** Borda → roteador → **fluxos** independentes. Um fluxo novo não
   toca o núcleo (§5). A regra de negócio de cada fluxo vive **no módulo dono** (diário no `modulodiario`,
   lead no `modulocrm`), reusada pela web e pelo WhatsApp — o canal só orquestra a conversa.
5. **Responder rápido, processar depois.** A Meta exige `200` em segundos: a view valida a assinatura,
   **enfileira** e retorna `200`; o trabalho é da task.

### Arquitetura de fluxo

```
Meta Cloud API ──POST /webhooks/whatsapp──►  Django view (backend)
  (mensagem do usuário)                        │  1. valida X-Hub-Signature-256 (app secret do tenant)
                                               │  2. resolve tenant por phone_number_id (metadata)
                                               │  3. dedup por message.id (idempotência)
                                               │  4. enfileira processar_mensagem_whatsapp.delay(payload)
                                               └► responde 200 imediatamente
                                                        │
                                            Celery worker (in-process, fora de request)
                                               │  rls_bypass → identifica remetente (telefone→pessoa)
                                               │  carrega/avança a máquina de estados (Redis)
                                               │  tenant_context → age pelo ORM (diário/lead/…)
                                               └► responde ao usuário via WhatsApp Cloud API (httpx)
```

Ingresso público do webhook: **Cloudflare Tunnel** (andaime de dev = ngrok), restrito ao path do webhook —
ver [deploy-e-seguranca §3.1](../arquitetura/deploy-e-seguranca.md) e Fase 10.3.2 do [roadmap](../roadmap.md).

## 4. Desenho-alvo — mecanismos

### 4.1 Resolução de tenant (decisão central)

Uma conta WhatsApp Business pode atender **vários tenants**; o payload da Meta traz o
`metadata.phone_number_id` que **recebeu** a mensagem. Modela-se a conta como config tenant-scoped:

| Modelo (novo, app Python) | Guarda |
|---|---|
| `CanalWhatsApp` (`TenantScopedModel`) | `phone_number_id` (**unique global**, chave de resolução), credenciais Meta do tenant (**access token, app secret, verify token** — secretos), `ativo` |

- **Entrada:** `phone_number_id → CanalWhatsApp → tenant`. Lookup sob `rls_bypass()` (a borda ainda não
  tem contexto); o resto roda sob `tenant_context(tenant)`.
- **Isolamento:** cada tenant usa **seu** número/credenciais; a assinatura HMAC é validada com o **app
  secret daquele tenant**. Número desconhecido → descartar (não vaza existência).
- **Dev/single-tenant:** sem `CanalWhatsApp`, cai para um default de `settings` (`WHATSAPP_DEFAULT_*`) —
  andaime aposentado antes do go-live.

> **Por que pelo número receptor e não pelo remetente:** resolver pelo telefone do remetente exigiria
> varrer as pessoas de **todos** os tenants (o mesmo número pode existir em dois) — ambíguo e com cheiro
> de vazamento. O número receptor é determinístico e 1:1 com o tenant.

### 4.2 Identidade e autoria

Resolvido o tenant, o **remetente** identifica a pessoa **dentro daquele tenant** (o filtro
`/funcionarios/?telefone=` já existe e normaliza número); o papel (funcionário/cliente/fornecedor) decide
quais fluxos ele pode acionar. A **autoria** de qualquer registro vem daí (ex.: `EntradaDiario.autor`,
`origem='whatsapp'`). Remetente não encontrado → fluxo de **lead** (§5). Mudança de cadastro no meio da
conversa → estado descartado, sessão reinicia (comportamento já presente no Node; mantido).

### 4.3 Autenticação e o papel do JWT de serviço (Fase 10.8)

O webhook é **inbound e público**; autentica-se pela **assinatura HMAC da Meta** (`X-Hub-Signature-256`,
app secret do tenant), não por JWT de usuário.

- **Como escreve sem um usuário?** Rodando **in-process** (§3.2): autoria por telefone→pessoa, escrita sob
  `tenant_context()` — como a Fase B. **Sem token para chamar a si mesmo.**
- **Onde entra o JWT de serviço da 10.8?** Apenas se o canal for um processo **separado** falando com o
  backend por HTTP, ou se um fluxo precisar alcançar **outro** serviço (ex.: o drone). Disponível em
  [issue_service_token](../../iam/identity/tokens.py); não é necessário no caminho in-process.

> **Refinamento explícito** do [plano de reintegração](../arquitetura/diario-ia-reintegracao.md): a Fase C
> original dizia "o webhook chama o backend com o JWT de serviço". Depois que a Fase B firmou o padrão
> in-process, absorver o canal no backend e dispensar o round-trip de token é mais simples e correto. A
> 10.8 fica como plano B — ver §7, decisão D1.

### 4.4 Máquina de estados da conversa

Conversa multi-passo mantém estado em **Redis**, uma task por mensagem:

- **Chave:** `wa:state:<tenant_id>:<telefone>` (escopada por tenant — nunca cruza), **TTL** deslizante
  (~30 min) para higienizar sessões abandonadas.
- **Núcleo genérico:** o motor de passos e o roteador de comandos são do **canal**; cada fluxo declara
  seus passos (porte de [conversationSteps.js](../../backend/funcoeswhatsapp/bot/conversationSteps.js)).
- **Comandos globais:** `sair` limpa o estado; roteador inicia fluxos por palavra-chave, respeitando o
  papel do remetente.
- **Idempotência:** `message.id` da Meta guardado num `SET` Redis com TTL (a Meta reentrega em falha de
  ACK) → mensagem repetida é ignorada, evitando ação duplicada.

### 4.5 Cliente WhatsApp (saída)

`whatsapp_client.py` (httpx), porte de
[whatsappService.js](../../backend/funcoeswhatsapp/services/whatsappService.js), **credenciais por tenant**
(do `CanalWhatsApp`): `enviar_texto`, `enviar_botoes` (≤3), `enviar_lista` (≤10, paginação "mais opções"),
`baixar_midia`. Habilita também o **outbound proativo** (notificações — §5). Erros de envio são logados
(observabilidade 10.1) e não derrubam a task.

### 4.6 Segurança

- **Assinatura** `X-Hub-Signature-256` com `hmac.compare_digest` (tempo constante), app secret **do
  tenant** — porte fiel do
  [controller Node](../../backend/funcoeswhatsapp/controllers/whatsappController.js), já correto lá.
- **Handshake** `GET`: `hub.verify_token` conferido contra o verify token do canal.
- **Idempotência** por `message.id` (§4.4) contra reentrega.
- **Abuso de número desconhecido:** throttle do fluxo de lead por telefone (Redis).
- **Segredos:** tokens Meta são secretos → `_config` fail-fast fora de DEBUG, sem fallback público
  (padrão S7); em produção, gestão de segredos da Fase 10.3. Nunca logar payload cru com PII (manter o
  `sanitize_webhook_payload` do Node).
- **LGPD:** telefone é PII ([D6](../pendencias.md)); número que não vira pessoa fica só no lead, sob o
  mascaramento da Fase 9.C quando aplicável.

## 5. Fluxos (o canal é multi-fluxo)

Cada fluxo é um plugin do canal; a regra de negócio vive no módulo dono.

| Fluxo | Situação | Módulo dono | Escrita |
|---|---|---|---|
| **Diário de obra** | existe no Node; portar | `modulodiario` | via serviço `registrar_contribuicao` (§6) |
| **Pré-cadastro → lead** | existe no Node; portar | `modulocrm` | Lead (decisão D2) |

**Catálogo de fluxos futuros** (a visão de "canal de comunicação do SaaS" — sem compromisso de data):

- **Notificações outbound (proativas):** 2ª via de boleto/PIX, aviso de vencimento — usa o
  `whatsapp_client` + templates aprovados da Meta. (Backlog de monetização/portal do cliente.)
- **RH:** consulta de holerite (PDF), ponto eletrônico pelo chat.
- **Operações:** requisição de materiais/EPIs, tarefas do dia, apontamento de horas por atividade.
- **Segurança/qualidade:** reporte de incidentes/riscos, checklists (FVS, ferramentas/EPI), DDS digital.
- **Cliente/fornecedor:** consulta de status (boleto, andamento de obra); 2ª via.
- **Abstração multi-canal:** o motor de estados/roteador independe do transporte — um `TelegramChannel`
  ou SMS caberia atrás da mesma máquina (troca só a borda e o client de envio).

## 6. Reaproveitamento (refactor DRY)

Hoje a escrita do diário vive dentro da view `DiarioObraViewSet.contribuir`
([modulodiario/views.py](../../backend/modulodiario/views.py)), acoplada a `request.user`. Extrair
**`modulodiario/services.py::registrar_contribuicao(*, obra, funcionario, texto=None, arquivo=None,
eh_ocorrencia=False, clima=None, origem)`** (get-or-create do diário do dia + `EntradaDiario`/
`DocumentoDiario` + disparo da IA). Web e WhatsApp chamam a **mesma** função — um só lugar decide autoria,
tenant e disparo de IA (mesmo movimento do `modulocrm/services.py` da [Fase 11.2](../roadmap.md)). Cada
fluxo futuro segue o padrão: canal orquestra, módulo dono grava por um serviço reusável.

## 7. Plano de reescrita (fases)

Ordem incremental; cada fatia fecha com testes e é entregável isolada. Status por fase no
[roadmap](../roadmap.md).

- **C.0 — Fundação do canal:** app Django (Python), modelo `CanalWhatsApp` (+migration), view do webhook
  (`GET` verify + `POST` com HMAC → enfileira → `200`), `whatsapp_client.py`, resolução de tenant por
  `phone_number_id`, idempotência. **DoD:** handshake da Meta + validação de assinatura verdes.
- **C.1 — Núcleo de conversa:** identidade telefone→pessoa tenant-scoped; motor de estados no Redis
  (chave por tenant+telefone, TTL); comandos globais + roteador por papel; reset por mudança de perfil.
  **DoD:** testes de transição + identidade.
- **C.2 — Fluxo Diário:** extrair `modulodiario/services.py::registrar_contribuicao` (a view web passa a
  usá-lo); portar o fluxo. **Simplificado ao modelo novo de _um diário por obra por dia_:** a seleção de
  múltiplos diários do dia deixa de existir e o nível empreendimento→obra vira uma **lista de obras
  direta** (paginada, filtrada por equipe ∪ responsáveis técnicos — `pode_contribuir` garantido por
  construção), com atalho de **obra única**; coleta → `salvar` → serviço; mídia → `DocumentoDiario` → IA
  (Fase B). **DoD:** E2E do diário via webhook, escrita no tenant certo.
- **C.3 — Fluxo Lead:** portar o pré-cadastro → Lead no `modulocrm` (decisão D2). **DoD:** número
  desconhecido gera lead; teste do funil.
- **C.4 — Descomissionar o Node:** remover `backend/funcoeswhatsapp/*.js` e artefatos Node; garantir que
  nada referencia a URL/porta antiga; `.env.example` e compose limpos. **Fecha A2/D1 (WhatsApp).**
  **DoD:** `grep` sem resíduo Node; suíte + E2E verdes.
- **C.5+ — Novos fluxos:** o catálogo da §5, cada um como fatia independente sobre o núcleo pronto.

**Testes:** unidade (transições, identidade, assinatura HMAC, idempotência); DB-backed (Postgres, role
`erp_app`: escrita no tenant certo com `origem='whatsapp'` + disparo da IA mockada); E2E
`infra/gateway/phaseC_whatsapp_test.py` (simula webhook da Meta com assinatura → `200`; diário criado + IA
enfileirada; desconhecido → lead; assinatura inválida → `403`) — padrão dos `phaseN_*` em
[infra/gateway/](../../infra/gateway/).

## 8. Decisões a confirmar

| # | Decisão | Recomendação |
|---|---|---|
| **D1** | Canal **in-process** (app no backend) vs **processo separado** (usa JWT de serviço 10.8). | **In-process** — segue a Fase B, menos peças, sem round-trip de token. A 10.8 fica de plano B. |
| **D2** | Lead → `modulocrm.Lead` vs `nucleo.PreCadastro` (legado, [migration 0003](../../backend/nucleo/migrations/0003_precadastro.py)). | **`modulocrm.Lead`** — consolida com a absorção do `funcoeslead` (Fase 11.2); depreciar `nucleo.PreCadastro`. |
| **D3** | Número WhatsApp **por tenant** vs número **único** compartilhado. | **Por tenant** (`CanalWhatsApp`) — isolamento limpo; único só como andaime de dev. |
| **D4** | Armazenamento das credenciais Meta (secretas) por tenant. | Campo no modelo agora; **cofre de segredos** na Fase 10.3 antes do go-live. |

## 9. Mapa de paridade (Node → Python)

| Arquivo Node | Destino Python | Observação |
|---|---|---|
| `controllers/whatsappController.js` | `views.py` (webhook) | valida HMAC, enfileira, responde 200 |
| `bot/bot.js` | `tasks.py::processar_mensagem_whatsapp` | orquestração fora de request |
| `bot/commandRouter.js` | `bot/router.py` | roteamento de comando/fluxo por papel |
| `bot/conversationSteps.js` | `bot/steps.py` | passos por fluxo |
| `bot/flows/diarioObraFlow.js` | `flows/diario.py` | escreve via `modulodiario/services.py` |
| `bot/flows/preCadastroFlow.js` | `flows/lead.py` | cria Lead no `modulocrm` |
| `services/whatsappService.js` | `whatsapp_client.py` | envio/download (httpx), creds por tenant |
| `services/cacheService.js` | estado Redis nativo | chave por tenant+telefone |
| `services/api/*.js` | — | **eliminados**: ação in-process pelo ORM |
| `middleware/iamAuth.js` | — | **eliminado**: borda usa HMAC da Meta, não JWT |
| `config.js` | `settings`/`CanalWhatsApp` | creds por tenant + default de dev |
