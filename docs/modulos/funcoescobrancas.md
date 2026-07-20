# Integração de Cobranças (`funcoescobrancas`)

> **Status: ✅ MVP entregue 08/06/2026** (`backend/funcoescobrancas/`). **Django app Python**
> (não microsserviço Node) que adapta o gateway de cobrança **Asaas** (boleto · PIX · cartão). Acionado
> pelo [moduloerp](moduloerp.md). Plano financeiro em
> [moduloerp.md §6](moduloerp.md#6-boletos--cobrança--integração-asaas).
>
> **Escopo do MVP (decisão do usuário, 07/06/2026):** golden path apenas — **emitir cobrança** e
> **baixa automática via webhook**. Cancelamento, estorno/refund, QR PIX e parcelamento ficam para uma
> slice 2 futura (não fazem parte desta entrega). Credencial **global** via `.env`
> (`ASAAS_API_KEY`/`ASAAS_BASE_URL`/`ASAAS_WEBHOOK_TOKEN`, compartilhada por todos os tenants nesta
> fase) — ver "Ambiente" abaixo; `IntegracaoAsaas` por tenant fica para quando a gestão de segredos da
> Fase 5 estiver pronta.

## Por que Python (e não Node nem Java)

Decisão de 07/06/2026, conforme o **AD-8** da [arquitetura.md](../arquitetura.md#6-estratégia-de-stack-tecnológica):

- A regra é explícita: **nova integração externa → Celery task (Python)**; **novo webhook → Django view
  + Celery (Python)**; e *"nunca criar um novo microsserviço Node.js ou um novo serviço Java para lógica
  que o Django cobre"*.
- **Java** está congelado ao produto de drone (`funcoesODM`) por concorrência CPU-bound / WebSocket /
  NodeODM — "fica e não cresce". Uma integração de pagamento é **I/O-bound** (HTTP + webhook), sem nada
  disso.
- O prefixo `funcoes*` **não** é exclusivo de Node: o [funcoesia](funcoesia.md) já é um app Django
  Python rodando em Celery. `funcoescobrancas` segue o mesmo padrão.

## Ambiente: Asaas sandbox → real

- **Agora:** **sandbox** (`https://api-sandbox.asaas.com/v3`) — cobranças de teste, sem dinheiro real,
  para construir e validar o fluxo ponta a ponta.
- **Depois:** **real** (`https://api.asaas.com/v3`) — troca-se `ASAAS_BASE_URL` + `ASAAS_API_KEY`.
- **Credencial — decisão do MVP (07/06/2026):** **chave global** em `.env`
  (`ASAAS_API_KEY`/`ASAAS_BASE_URL`/`ASAAS_WEBHOOK_TOKEN`), compartilhada por todos os tenants. Migrar
  para credencial **por tenant** (`IntegracaoAsaas`, cada empresa com a própria conta Asaas, segredo
  cifrado) é pendência operacional da [Fase 5](../roadmap.md#fase-5--endurecimento-rs256jwks--borda) —
  ver também a questão em aberto em [moduloerp.md §15](moduloerp.md#15-questões-em-aberto-decidir-antes-da-sub-fase-relevante).

## Arquitetura

Os **models de negócio continuam no [moduloerp](moduloerp.md)** (`Boleto`, `ContaReceber`,
`CobrancaCliente`). Este app é o **adaptador**: cliente HTTP do Asaas + orquestração + tarefas Celery +
a view de webhook — tudo in-process no Django (sem novo runtime/HTTP interno). A única tabela própria é
`EventoWebhookAsaas` (idempotência do webhook — ver "Modelo" abaixo).

```
backend/funcoescobrancas/
├── client.py        ← AsaasClient: cliente HTTP do Asaas (customers/payments, sandbox/real por env)
├── services.py      ← orquestra: garante customer, gera cobrança, processa evento de webhook
├── tasks.py         ← Celery: criar_cobranca · processar_evento_webhook (wrappers finos sobre services)
├── views.py         ← WebhookAsaasView (DRF APIView pública, valida token, idempotente)
├── urls.py          ← registra POST /webhook/asaas/
├── models.py        ← EventoWebhookAsaas (idempotência; plain Model, não TenantScopedModel)
└── admin.py         ← EventoWebhookAsaasAdmin
```

> **Por que `EventoWebhookAsaas` não é `TenantScopedModel`:** o tenant só é conhecível depois de
> resolver o `Boleto` vinculado ao `payment.id` do evento — e a credencial do gateway é global nesta
> fase. Ver docstring do model para o raciocínio completo.

### Fluxo (entregue no MVP)
1. **Criar cobrança:** o operador aciona `POST /api/erp/contas-a-receber/{id}/gerar-cobranca/` (action
   no `ContaReceberViewSet`). Antes de enfileirar, a view roda a **trava de identidade** síncrona
   `services.validar_cliente_para_cobranca` (só leituras no Asaas) — ver "Trava de identidade" abaixo;
   se bloquear, devolve `409` com mensagem pronta para o usuário e **não** enfileira nada. Passando, a
   view enfileira `tasks.criar_cobranca.delay(conta_receber_id)`. A task chama
   `services.gerar_cobranca_asaas`, que garante o `customer` no Asaas (espelha em
   `Cliente.id_cliente_gateway`, resolvendo a identidade sempre por CPF/CNPJ + nome), cria o `payment` e
   grava `gateway_id`, `url_pdf`, `linha_digitavel` no `Boleto` (status `EMITIDO`). Idempotente: uma 2ª
   chamada reaproveita o `Boleto`/`customer` existentes sem chamar o gateway de novo.

#### Trava de identidade — NUNCA emitir para cadastro divergente

Um boleto errado sai no CPF de outra pessoa/empresa e é caro de estornar. Por isso a emissão exige que
**nome _e_ CPF/CNPJ** do `Cliente` do sistema batam com o customer do Asaas antes de criar o `payment`:

- **Sem CPF/CNPJ válido** (11 ou 14 dígitos) → bloqueia. Corrige o bug em que `id_cliente_gateway` era
  resolvido com documento vazio: `GET /customers?cpfCnpj=` fazia o Asaas devolver a **conta inteira** e
  o código adotava o primeiro customer (`dados[0]`) — foi assim que uma cobrança saiu no cadastro errado
  ("EEGM"). `client.buscar_customer_por_cpf_cnpj` agora retorna `None` sem documento e confere o
  `cpfCnpj` do candidato.
- **CPF/CNPJ já existe no Asaas com nome diferente** → bloqueia (não adota o cadastro alheio). CPF igual
  + nome diferente é tratado como **provável erro de digitação**, não como "mesma pessoa" — a comparação
  (`_normalizar_nome`) tolera acento/caixa/espaço, mas é sensível ao conteúdo (`EDISON GOES` == `Edison
  Góes`, mas `EEGM` ≠ `Edison Goes`).
- **CPF/CNPJ igual e nome batendo** → reusa o customer existente. **Não existe / nome novo** → cria.
- **Fonte da verdade é sempre o CPF/CNPJ**, não o `id_cliente_gateway` salvo — que já foi contaminado no
  passado por adoção de cadastro alheio; agora se autocorrige e a mesma trava vale para o caminho
  assíncrono (`garantir_customer_asaas` repete a validação; `tasks.criar_cobranca` trata
  `CobrancaBloqueada` como falha **permanente** — sem retry — e a registra na DLQ).

O usuário vê o motivo exato no Sheet de detalhe da `ContaReceber` (mensagem em destaque de alerta),
podendo corrigir o cadastro antes de tentar de novo.

#### Auditoria de divergências (banco × Asaas)

A mesma trava roda em modo **relatório** (só leitura, não corrige nada) para antecipar problemas antes
mesmo da emissão — `services.analisar_divergencias_asaas(clientes)`. Faz **uma varredura paginada** da
conta Asaas (`AsaasClient.iterar_todos_customers`, dict por CPF/CNPJ) em vez de um GET por cliente, e
classifica cada cliente do tenant em: `sem_documento` (CPF/CNPJ inválido), `nome_divergente` (mesmo
documento com nome diferente no gateway — o caso "EEGM") ou `vinculo_divergente` (`id_cliente_gateway`
salvo aponta para outro cadastro). Dois consumidores:

- **Comando de operação/cron:** `python manage.py analisar_divergencias_asaas [--tenant <slug>]`
  (`clientes/management/commands/`) — imprime o relatório; sem `--tenant`, varre todos.
- **Painel ao criar cliente:** ao clicar em **"Novo Cliente"**, o frontend chama
  `GET /api/clientes/divergencias-asaas/` (action `ClienteViewSet.divergencias_asaas`, tenant-scoped) e
  mostra no topo do formulário as divergências existentes — o operador vê o que já está desalinhado
  **antes** de cadastrar mais um. Gateway fora do ar → `502` (o painel apenas não aparece; não bloqueia
  o cadastro).
2. **Baixa automática (webhook):** o Asaas faz `POST /api/erp/cobrancas/webhook/asaas/`
   (`PAYMENT_RECEIVED`/`CONFIRMED`/...); a view valida o header `asaas-access-token` contra
   `ASAAS_WEBHOOK_TOKEN`, grava/recupera o `EventoWebhookAsaas` por `evento_id` (idempotência — Asaas
   reenvia eventos não confirmados) e despacha `tasks.processar_evento_webhook`. A task chama
   `services.processar_evento_webhook`, que localiza o `Boleto` pelo `gateway_id` e aplica
   **`dar_baixa(origem='asaas')`** — o MESMO caminho único de baixa do D.1.1 (`Boleto`→`PAGO`,
   `ContaReceber`→`QUITADO`, lança `Transacao`). Pagamento repetido em título já quitado cai no guard
   `RevisaoBaixa`/`BaixaRequerRevisao` (fila do financeiro), exatamente como previsto no D.1.1. É assim
   que o backend sabe **quem já pagou**, sem moderação manual no caminho feliz.
3. **Cancelamento:** `services.cancelar_cobranca_asaas(boleto)` faz `DELETE /payments/{id}` no Asaas,
   marca `Boleto.CANCELADO` + `data_cancelamento` e guarda a resposta em `dados_retorno_api`
   (acionado por `BoletoViewSet.cancelar`, síncrono). O webhook também reflete cancelamentos nascidos
   fora do SGI: `EVENTOS_DE_CANCELAMENTO` (`PAYMENT_DELETED`) marca o boleto local como `CANCELADO`.
4. **Erro visível:** se o Asaas recusa a emissão (4xx — ex.: CPF inválido), `gerar_cobranca_asaas`
   persiste um `Boleto` status `ERRO` com o payload cru (códigos/mensagens) e levanta `CobrancaRejeitada`
   (subclasse de `CobrancaBloqueada` → sem retry); 5xx/rede continua transitório (retry). O erro deixa de
   morrer só na DLQ e aparece clicável na UI (lista de Boletos + na Conta a Receber).
5. **Verificação ao vivo:** `services.verificar_cobranca_asaas(boleto)` (`GET /payments/{id}`) devolve o
   estado atual do gateway ao abrir o documento — online = verdade do Asaas (status/URL atualizados);
   offline = última versão local + `gateway_online=False` (a UI abre o guardado e avisa).

### Fora do escopo do MVP (slice 2 futura)
`tasks.estornar` (`refund` → lança `Devolucao`), QR PIX e parcelamento (`installments`) — adiados por
decisão do usuário (07/06/2026) para manter o MVP no golden path emitir+baixa. Cancelamento de boleto:
**entregue 18/07/2026** (botão na UI + webhook `PAYMENT_DELETED`).

### UI dedicada — telas de boletos (entregue 08/06/2026) ✅

Por decisão do usuário ("telas dedicadas de boletos", não Sheet/drill-down), o frontend ganhou um
sub-módulo próprio em `modules/erp/` (rotas-irmãs, mesmo padrão de `empreendimentos/:id`):

- **`BoletosListPage`** (`/app/erp/boletos`) — workspace só-leitura: `FilterBar` + `FinanceDataTable`
  paginado/filtrado no servidor (status/vencimento), reaproveitando o arquétipo "Workspace de lista
  financeira" do ERP (ver [moduloerp.md §5.5](moduloerp.md#55-arquétipos-de-página-layouts-reutilizáveis)).
- **`BoletoDetailPage`** (`/app/erp/boletos/:id`) — dados do gateway (linha digitável, link do PDF) +
  **timeline de eventos do webhook Asaas** (consome `GET /api/erp/cobrancas/eventos/?boleto={id}`),
  provando evento a evento como a baixa automática aconteceu (`recebido_em`/`processado_em`/`resultado`).
- **`StatusBoletoBadge`/`statusBoleto.ts`** — badge de status (`EMITIDO`/`PAGO`/`VENCIDO`/`CANCELADO`),
  espelhando `StatusContaBadge`.
- **Botão "Gerar cobrança (Asaas)"** no Sheet de detalhe da `ContaReceber` (`ContasAReceberPage`) —
  aciona `useGerarCobrancaContaAReceber` → `POST .../gerar-cobranca/`.
- Card de navegação no hub (`ErpDashboardPage`) → `/app/erp/boletos`.

Camada de dados: `endpoints/boletos.ts` + `hooks/useBoletos.ts` (`useBoletos`,
`useGerarCobrancaContaAReceber`, `useEventosWebhookAsaas`) sobre `erpKeys`. Detalhe completo (arquétipos,
code-splitting, invalidação de cache): [moduloerp.md §6](moduloerp.md#6-boletos--cobrança--integração-asaas)
e `frontend.md` §5.10 (ERP).

### Bugs corrigidos durante a validação real (08/06/2026)

A validação ponta a ponta via API (golden path completo: gerar cobrança → boleto real no sandbox)
revelou três problemas que bloqueavam o fluxo — nenhum específico do `funcoescobrancas`, mas só
apareceram ao rodar o caminho completo pela primeira vez. Todos corrigidos no mesmo turno:

1. **`nucleo/signals.py` gravava `alvo_id=task_id`** em `LogAtividadeUsuario.alvo_id`
   (`PositiveIntegerField`), mas o `task_id` do Celery é um UUID (string) — disparar **qualquer** tarefa
   assíncrona (não só `criar_cobranca`) levantava `ValueError` dentro de uma transação atômica e poluía
   as queries seguintes (`502 "An error occurred in the current transaction… 'atomic' block"`). Bug
   **pré-existente e sistêmico** — corrigido removendo `alvo_id=task_id` das duas chamadas a
   `LogAtividadeUsuario.objects.create(...)` (`log_task_start` e o fallback de `log_task_end`); o
   `task_id` permanece em `detalhes["task_id"]`.
2. **`ASAAS_API_KEY`/`ASAAS_BASE_URL`/`ASAAS_WEBHOOK_TOKEN` nunca chegavam ao container `sgi-erp`** — o
   `docker-compose.yml` não referenciava essas variáveis no serviço `erp` (só existiam em
   `backend/.env`, que o Compose não lê). Resultado: `502 "Asaas respondeu 401: … 'access_token' é
   obrigatório"`. Corrigido adicionando `${ASAAS_BASE_URL}`/`${ASAAS_API_KEY}`/`${ASAAS_WEBHOOK_TOKEN}`
   ao `environment:` do serviço `erp` em `docker-compose.yml` e replicando os valores no `.env` da raiz
   (o que o Compose efetivamente lê).
3. **`sgi-erp` é imagem buildada**, não monta `./backend` como volume (igual ao `sgi-react`) — qualquer
   alteração de código exige `docker compose build erp && docker compose up -d erp` para entrar em
   vigor. As views/serializers/urls novas do `funcoescobrancas` davam `404` em
   `/api/erp/cobrancas/eventos/` até o rebuild da imagem.

> ⚠️ **Cuidado ao editar `ASAAS_API_KEY` no `.env`:** o valor (formato `aact_...`) costuma trazer um
> `$` literal — o Compose tenta interpolá-lo como variável e, se não escapado como `$` (dólar
> duplicado), **imprime avisos no terminal contendo boa parte da chave real**. Foi o que aconteceu
> nesta sessão; a chave deve ser tratada como potencialmente comprometida e regenerada no painel do
> Asaas assim que possível.

## Endpoint público (webhook)

| Método | Rota | Função |
|---|---|---|
| `POST` | `/api/erp/cobrancas/webhook/asaas/` | Recebe os eventos do Asaas; **idempotente** (trata `event.id`), valida `ASAAS_WEBHOOK_TOKEN`, despacha a baixa via Celery |

> As demais operações (criar/cancelar/estornar) **não** são HTTP — são chamadas in-process pelo
> `moduloerp` via Celery, não um serviço à parte.

## Configuração (Django settings, por env)

```
ASAAS_BASE_URL=https://api-sandbox.asaas.com/v3   # real: https://api.asaas.com/v3
ASAAS_API_KEY=SUA_CHAVE_SANDBOX_AQUI               # GLOBAL nesta fase (todos os tenants); ver "Ambiente"
ASAAS_WEBHOOK_TOKEN=TOKEN_DE_VALIDACAO_DO_WEBHOOK  # confere o header asaas-access-token do Asaas
```

## Validação do MVP (08/06/2026)

Validado e2e com `AsaasClient` mockado (`unittest.mock.patch.object`, sem rede/credenciais reais —
script descartável, executado via `manage.py shell` e removido após confirmar). Cenários cobertos, todos
✅:
- `gerar_cobranca_asaas`: cria `customer`+`payment`, espelha `id_cliente_gateway`, grava `Boleto`
  `EMITIDO` com `gateway_id`/`url_pdf`/`linha_digitavel`; 2ª chamada reaproveita sem chamar o gateway.
- Webhook `PAYMENT_CONFIRMED` → `dar_baixa(origem='asaas')` aplicada (`ContaReceber`→`QUITADO`,
  `Boleto`→`PAGO`, `Transacao` lançada).
- Reenvio do mesmo `evento_id` → idempotente (não duplica `EventoWebhookAsaas`/`Transacao`/baixa).
- 2º pagamento no mesmo título já `QUITADO` → guard aciona `RevisaoBaixa(origem='asaas')`, não altera
  `valor_pago` (prova que o mecanismo do D.1.1 cobre o caminho do Asaas, como previsto).
- View HTTP (`django.test.Client`): sem token → 401, token errado → 401, token correto + payload válido
  → 200 e baixa aplicada ponta a ponta via HTTP.

### Reforço: teste com túnel real (ngrok) e sandbox Asaas de verdade — 08/06/2026 ✅

> **Nota (andaime de dev):** o túnel **ngrok** + o proxy dedicado abaixo são de **desenvolvimento**,
> não de produção. Em produção, o ingress público dos webhooks passa a ser uma solução profissional
> (recomendado **Cloudflare Tunnel**) — ver [arquitetura/deploy-e-seguranca.md §3.1](../arquitetura/deploy-e-seguranca.md)
> e a Fase **10.3.2** do [roadmap](../roadmap.md).

A instalação automatizada do ngrok (via `snap`, e depois via download direto do binário) não foi
possível durante a sessão — a primeira pediu senha sudo interativa e a segunda foi corretamente
bloqueada pelas guardas de segurança do agente (fonte de download não autorizada pelo usuário). Em
seguida o usuário instalou o ngrok manualmente (`apt` com sua própria credencial sudo) e configurou o
authtoken — então fizemos o teste real:

1. Subimos `manage.py runserver` + túnel `ngrok http 8000` (URL pública temporária
   `https://<id>.ngrok-free.app`, com `ALLOWED_HOSTS` incluindo `.ngrok-free.app`).
2. Registramos a URL pública + `ASAAS_WEBHOOK_TOKEN` (gerado para o teste) como webhook via
   **API do Asaas** (`POST /webhooks` — descoberto que o v3 expõe esse endpoint; eventos
   `PAYMENT_CREATED/RECEIVED/CONFIRMED/OVERDUE/REFUNDED`).
3. Geramos uma cobrança **de verdade** no sandbox via `gerar_cobranca_asaas` (sem mock — `customer` e
   `payment` reais criados na conta sandbox) e simulamos o pagamento via `POST
   /payments/{id}/receiveInCash`.
4. **Resultado: dois eventos chegaram pela internet de verdade** (`PAYMENT_CREATED` e
   `PAYMENT_RECEIVED`, em ~2s) — o `WebhookAsaasView` validou o token, gravou `EventoWebhookAsaas` e
   aplicou `dar_baixa(origem='asaas')` de ponta a ponta: `ContaReceber`→`QUITADO`, `Boleto`→`PAGO`,
   `Transacao` lançada — tudo via HTTP real, sem mock em nenhuma camada.
5. Limpeza: removemos o webhook do Asaas (`DELETE /webhooks/{id}`) e os dados locais de teste; a
   cobrança/cliente de teste seguem no sandbox (sem custo, é ambiente de testes).

Conclusão: o golden path está confirmado **duas vezes** — localmente com payloads simulados e
ponta a ponta pela internet com o gateway real. Nada pendente quanto a **este teste pontual**
(túnel/webhook removidos ao final) — ver a seguir a configuração **persistente** que o substituiu.

### Túnel ngrok persistente para testes contínuos (08/06/2026)

Diferente do teste acima (túnel temporário, registrado e depois removido), o usuário optou por manter
um **túnel ngrok ativo de forma contínua**, com a URL pública registrada como webhook no Asaas —
assim, eventos de pagamentos simulados no sandbox chegam automaticamente "do lado de fora" sem
precisar reabrir o túnel/registrar o webhook a cada sessão de teste.

> **Plano inicial vs. configuração final:** a primeira ideia era simplesmente apontar `ngrok http 8090`
> para o gateway inteiro, com `ALLOWED_HOSTS` ganhando o curinga `.ngrok-free.app`. Avaliando os riscos
> disso (ver aviso de segurança logo abaixo), o usuário pediu uma pesquisa sobre como reduzir a chance
> de o túnel virar porta de vazamento — o resultado foi o **proxy dedicado descrito na subseção
> seguinte**, que é a forma **recomendada e efetivamente usada**. A configuração final ficou assim:

- O ngrok aponta para o **proxy dedicado** (`ngrok http 8091`, **não** `8090` — ver subseção
  seguinte), que só repassa adiante o endpoint do webhook.
- `ALLOWED_HOSTS` **permanece `localhost,127.0.0.1`**, sem curinga `.ngrok-free.app` — o proxy refaz a
  chamada para `http://localhost:8090/...`, então o Django sempre enxerga `Host: localhost:8090`
  (já confiável), nunca o domínio do ngrok. O curinga do plano inicial deixou de ser necessário
  (detalhe completo no aviso de segurança).
- O webhook é registrado uma vez no Asaas via `POST /webhooks` apontando para a URL pública do túnel
  — `https://<id-do-túnel>.ngrok-free.app/api/erp/cobrancas/webhook/asaas/` —, com o
  `ASAAS_WEBHOOK_TOKEN` do `.env` (a view já valida esse token — ver "Boas práticas" abaixo).

#### Redução da superfície: proxy dedicado ao webhook (08/06/2026) ✅

Pesquisa feita após o aviso acima (ver opções de proteção do túnel — `ngrok --basic-auth`, `--allow-cidrs`,
OAuth via Traffic Policy): **autenticação genérica no túnel inteiro quebraria o próprio webhook**, porque
o disparador do Asaas só envia `POST` + JSON + o header `asaas-access-token` — não faz login interativo
nem Basic Auth/OAuth. Qualquer proteção precisa ser **ciente do caminho** (proteger tudo, exceto o
endpoint do webhook) ou, melhor ainda, **reduzir o que o túnel alcança**.

**Decisão (08/06/2026):** em vez de apontar `ngrok http 8090` para o gateway inteiro, criamos
`infra/ngrok-webhook-proxy/proxy.py` — um proxy mínimo (só biblioteca padrão do Python, sem
dependências) que:

1. **Só repassa `POST /api/erp/cobrancas/webhook/asaas/`** — qualquer outro caminho/método recebe
   `404` puro. Mesmo que a URL do túnel vaze, **nada além desse único endpoint fica alcançável** —
   nem login, nem APIs do backend/IAM, nada.
2. **Chamadas com o `asaas-access-token` correto passam direto** — é o tráfego real do Asaas,
   sem fricção nenhuma (mesmo guard que a view Django já valida — dupla checagem, mesma fonte de
   verdade `ASAAS_WEBHOOK_TOKEN`).
3. **Chamadas sem o token correto caem num desafio HTTP Basic Auth genérico** (`401` +
   `WWW-Authenticate: Basic`, sem corpo, sem `Server: ... Django`) — um "muro de obscuridade": quem
   ficar sondando essa URL (scanners de internet) não recebe nenhuma pista de que há um Django/DRF/backend
   por trás, só um 401 anônimo idêntico ao de qualquer servidor genérico.

Aponte o ngrok para o proxy em vez do gateway: `ngrok http 8091` (em vez de `ngrok http 8090`) — o
proxy escuta em `127.0.0.1:8091` e repassa para `http://localhost:8090/api/erp/cobrancas/webhook/asaas/`.
Variáveis em `.env` da raiz (não versionadas): `WEBHOOK_PROXY_PORT`, `WEBHOOK_UPSTREAM_URL`,
`WEBHOOK_PROXY_BASIC_USER`/`WEBHOOK_PROXY_BASIC_PASS` (credenciais do muro — geradas aleatoriamente,
só para descartar sondagens; **não** são enviadas pelo Asaas, então nunca bloqueiam o webhook real).
Rodar: `python3 infra/ngrok-webhook-proxy/proxy.py` (lê as variáveis do ambiente — exporte o `.env`
antes). Testado e2e (sem o gateway no ar): caminho aleatório → `404`; sem token/sem auth → `401 Basic`
genérico; Basic Auth certo sem token → repassa (502 só porque o gateway estava fora do ar no teste);
Basic Auth errado → `401`; token do Asaas certo sem Basic Auth → repassa direto.

> Por que não colocar o Basic Auth diretamente no próprio webhook (ex.: embutido na URL registrada no
> Asaas, `https://user:pass@<túnel>/...`)? Não há garantia de que o disparador do Asaas envie
> `Authorization` a partir do "userinfo" da URL — se não enviar, o webhook real quebra silenciosamente.
> O proxy evita esse risco: o token do Asaas sempre destrava o caminho, e o Basic Auth só entra como
> filtro para quem **não** manda o token (ou seja, nunca para o Asaas de verdade).

> ## ⚠️ AVISO DE SEGURANÇA — leia antes de deixar o túnel ligado
>
> **Este aviso descreve o risco do *plano inicial* (`ngrok http 8090` direto no gateway +
> `ALLOWED_HOSTS` com curinga `.ngrok-free.app`) e como a arquitetura final — proxy dedicado
> (`ngrok http 8091`) + `ALLOWED_HOSTS` sem curinga — fecha quase tudo isso. Ele continua aqui
> porque registra o trade-off que foi avaliado e a decisão do usuário, e porque **o risco volta
> integralmente se alguém apontar o ngrok direto para a porta 8090 de novo.**
>
> ### O que o plano inicial exporia (e por que foi descartado)
>
> Apontar o túnel direto para o gateway (`localhost:8090`) exporia **o gateway de desenvolvimento
> inteiro na internet pública** — não só o endpoint do webhook:
>
> - **Login e todas as APIs do backend/IAM/CRM/diário/etc.** — qualquer pessoa com a URL
>   `*.ngrok-free.app` poderia tentar autenticar e navegar pelas rotas, igual a um usuário acessando
>   de fora.
> - **Credenciais reais do Asaas sandbox** (`ASAAS_API_KEY`/`ASAAS_WEBHOOK_TOKEN`) ficariam ao alcance
>   de quem comprometesse o login — embora seja ambiente de testes (sem dinheiro real), ainda é uma
>   conta vinculada ao usuário no Asaas.
> - O `ALLOWED_HOSTS` precisaria do curinga `.ngrok-free.app` (porque o domínio do túnel muda a cada
>   reinício no plano grátis), o que aceitaria *qualquer* subdomínio `*.ngrok-free.app` — não só o
>   túnel deste projeto.
>
> ### Como a arquitetura final fecha esses pontos
>
> Com o **proxy dedicado** (`infra/ngrok-webhook-proxy/proxy.py`, `ngrok http 8091`) no lugar:
>
> - **Só um endpoint fica alcançável** — `POST /api/erp/cobrancas/webhook/asaas/`; login, demais APIs
>   do backend/IAM/CRM/diário e tudo mais respondem `404` antes mesmo de chegar ao gateway. Mesmo que a
>   URL do túnel vaze, não há rota de navegação nem de autenticação por ali.
> - **`ALLOWED_HOSTS` voltou a `localhost,127.0.0.1`, sem curinga** — o proxy refaz a chamada para
>   `http://localhost:8090/...`, então o Django só enxerga `Host: localhost:8090` (já confiável em
>   qualquer cenário, túnel ligado ou não). Não existe mais brecha de "qualquer subdomínio
>   `.ngrok-free.app` é aceito" porque essa entrada foi removida — não apenas mitigada.
> - **Quem não manda o `asaas-access-token` correto esbarra num muro de Basic Auth genérico**
>   (credenciais aleatórias só para essa finalidade, geradas com `secrets` e guardadas no `.env`
>   gitignored) — sem nenhuma pista de que há Django/DRF por trás, reduzindo o valor de sondagens de
>   scanners de internet.
>
> Ou seja: a superfície real exposta pelo túnel hoje é **um único endpoint, sem navegação, sem login,
> sem APIs de negócio** — o cenário descrito acima (login/APIs/credenciais ao alcance) não se aplica
> mais à configuração em uso.
>
> **Decisão registrada (usuário, 08/06/2026):** manter o túnel ligado de forma contínua, com a
> ressalva *"Mantenha assim, mas coloque na documentação um aviso"* — o que motivou tanto este aviso
> quanto a pesquisa que resultou no proxy dedicado. O trade-off foi avaliado e o risco residual,
> aceito conscientemente.
>
> **Recomendações que continuam valendo:**
> - **Nunca apontar o ngrok direto para `8090`** — sempre `ngrok http 8091` (o proxy). Apontar para
>   `8090` reabre integralmente o cenário descrito em "o que o plano inicial exporia".
> - Encerrar o túnel (`Ctrl+C` no `ngrok http 8091`) quando não estiver testando ativamente — ele não
>   precisa ficar ligado 24/7, só durante as sessões de teste do golden path de cobrança.
> - Não reutilizar as credenciais sandbox em produção; ao migrar para o Asaas real
>   (`ASAAS_BASE_URL`/`ASAAS_API_KEY` de produção), a borda passa a ser o gateway de produção com TLS
>   próprio (Fase 5+) — este túnel/proxy é só para o ambiente de desenvolvimento.
> - Trocar o usuário/senha do muro de Basic Auth (`WEBHOOK_PROXY_BASIC_USER`/`_PASS` no `.env`) se
>   notar atividade não reconhecida nos logs do proxy ou em `LogAtividadeUsuario`.

## Boas práticas obrigatórias
- **Webhook idempotente:** o Asaas reenvia eventos; trata-se `evento_id` via `EventoWebhookAsaas` para
  não dar baixa em dobro — **implementado e validado**.
- **Validar a origem** do webhook (`asaas-access-token` contra `ASAAS_WEBHOOK_TOKEN`) antes de
  processar — **implementado e validado** (401 em token ausente/incorreto).
- **Nunca guardar dado de cartão** — usar tokenização do Asaas (não se aplica ao MVP: só
  boleto/PIX no golden path; cartão fica para a slice 2).
- Reaproveitar o `client.py` para a **NFS-e via Asaas** do [funcoesnf](funcoesnf.md) (um só gateway) —
  ainda não feito (fora do escopo do MVP de cobrança).

## Referências
- Plano financeiro e capacidades Asaas usadas: [moduloerp.md §6](moduloerp.md#6-boletos--cobrança--integração-asaas).
- Regra de stack: [arquitetura.md §6 (AD-8)](../arquitetura.md#6-estratégia-de-stack-tecnológica).
- Emissão de NF (também migrando para Asaas): [funcoesnf.md](funcoesnf.md).
