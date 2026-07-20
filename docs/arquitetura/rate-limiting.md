# Rate limiting, cotas e proteção de fornecedor

> **Prancha de desenho.** Registra o modelo de limitação de tráfego da plataforma: o que limita
> **entrada** (proteger a nossa API), o que limita **saída** (proteger cota e dinheiro em serviços de
> terceiro) e o que limita **consumo comercial** (cota de plano). O **status por camada** fica em
> [../roadmap.md](../roadmap.md); achados abertos, em [../pendencias.md](../pendencias.md).

## 1. Por que existem três camadas, e não uma

A confusão mais cara nesta área é tratar "rate limiting" como um assunto só. São três problemas
distintos, com donos, algoritmos e consequências diferentes:

| | **Camada 1 — Entrada** | **Camada 2 — Saída** | **Camada 3 — Cota comercial** |
|---|---|---|---|
| Protege | nossa infraestrutura | cota do fornecedor e **dinheiro** | receita / plano contratado |
| Contra | abuso, varredura, laço acidental | estourar limite de terceiro, emissão indevida | uso além do contratado |
| Onde roda | borda (nginx) + DRF | **worker**, no cliente HTTP | serviço de assinatura |
| Excedeu → | `429` ao chamador | task **espera e repete** | bloqueio comercial / upsell |
| Algoritmo | janela deslizante | **token bucket** | contador por período |

Confundi-las produz controles que parecem funcionar e não funcionam. O exemplo real, deste projeto:
limitar `emitir-nfse` na **entrada** por usuário não protege a NFE.io, porque (a) o endpoint de lote
recebe uma **lista** e emite N notas numa requisição só, (b) a chamada ao fornecedor acontece depois,
no **worker**, e (c) o `max_retries=3` multiplica cada ação por até 4. O contador de entrada marca 1.

## 2. Camada 1 — Entrada (proteger a plataforma)

### 2.1 Dimensões

Um SaaS multi-tenant precisa limitar em mais de um eixo ao mesmo tempo, porque cada eixo responde a
uma ameaça diferente:

- **Por IP** — anônimo. Varredura, enumeração, força bruta. É o único eixo disponível antes de saber
  quem é o requisitante.
- **Por usuário** — laço acidental no front, script de um funcionário, credencial vazada.
- **Por tenant (empresa)** — o eixo que define um SaaS. Sem ele, uma empresa com 50 funcionários
  consome 50× o que uma de 3 consome e pode degradar a experiência das outras — o problema conhecido
  como **noisy neighbor**. O limite de usuário é uma **fração** do limite da empresa
  (`THROTTLE_TENANT` × `THROTTLE_USER_FRACAO`), não um valor independente: solto, ele mente nas duas
  pontas — multiplica silenciosamente o teto real da empresa pelo número de funcionários, e pune a
  empresa pequena com um teto efetivo menor que o da grande.
- **Por endpoint** — operações caras (relatório consolidado) ou sensíveis (recuperação de senha)
  precisam de teto próprio, muito menor que o geral.

### 2.2 A cadeia de identidade (de onde vem o "quem")

Ponto de erro frequente e já cometido aqui. O gateway usa `$proxy_add_x_forwarded_for`, que
**acrescenta** o IP real ao `X-Forwarded-For` **enviado pelo cliente** — não o reescreve. Portanto:

- o **primeiro** elemento da cadeia é texto arbitrário de quem chama;
- o endereço confiável é o **último acrescentado pelo proxy mais próximo**.

Usar o primeiro elemento (ou a cadeia inteira) como identidade permite **furar o teto** trocando o
valor a cada requisição, e **poluir a trilha de auditoria** com IP falso. O número de camadas
confiáveis é configuração (`NUM_PROXIES`) e **tem de bater com a topologia real** — ao pôr CDN ou
balanceador na frente, ele muda.

### 2.3 Ordem de avaliação (limite conhecido)

No DRF, a permissão é resolvida **antes** do throttle: requisição sem token a endpoint protegido
recebe `401` e **não é contada**. Consequência prática: o teto anônimo protege as rotas `AllowAny`
(webhooks, recuperação de senha), **não** a inundação anônima de `/api/*`. Essa é responsabilidade da
borda: o gateway aplica `limit_req` por IP no login (apertado, anti brute-force) e em `/api/` (folgado,
anti-inundação — um escritório inteiro pode compartilhar um IP via NAT, e o limite fino é o da
aplicação).

### 2.5 Falha da cache

**Fail-open, mas ruidoso**, pelo mesmo trade-off da camada 2 (§3.4) e com um agravante próprio: o
`SimpleRateThrottle` do DRF assume que a cache devolve uma lista, e `django_redis` com
`IGNORE_EXCEPTIONS` devolve `None` numa queda — o que transformaria indisponibilidade do Redis em
**500 em toda requisição**. Um teto que derruba o produto que existe para proteger é pior que teto
nenhum. Todos os eixos, inclusive os de escopo nomeado, passam por um mixin que libera e registra erro.

### 2.4 O que o chamador recebe

`429` com `Retry-After`. A mensagem exibida deve deixar claro **qual eixo** foi atingido — bloqueio da
*conexão* é diferente de bloqueio da *conta*; sem isso o usuário conclui que a conta foi suspensa.
E o texto **nunca** pode revelar se uma conta existe: nos fluxos de recuperação de senha, o teto por
conta é silencioso de propósito (ver [acesso-e-permissoes.md](../acesso-e-permissoes.md)).

## 3. Camada 2 — Saída (proteger cota de terceiro e dinheiro)

### 3.1 Por que no worker, e por fornecedor

Toda integração de escrita deste sistema é **assíncrona**: a view enfileira, o worker executa. Logo o
único ponto onde se conhece o número real de chamadas ao fornecedor é o **cliente HTTP dentro do
worker**. Limitar na view é limitar intenção, não consumo.

O balde é **por fornecedor**, não por endpoint nem por usuário, porque a cota que se está protegendo é
do fornecedor: a NFE.io não distingue se a nota veio do lote ou da tela. Um balde por fornecedor
significa que qualquer caminho novo que fale com aquele serviço herda o limite **de graça** — inclusive
os que ainda não existem (módulo de pagamento, novos serviços).

### 3.2 Por que token bucket

É o algoritmo que tolera **rajada** mantendo a média — exatamente o padrão de uso deste produto, onde
o trabalho chega em lotes (remessa, emissão em massa, fechamento de mês) e não em fluxo constante.
Janela fixa quebraria o lote legítimo; token bucket o absorve até o tamanho do balde e depois impõe o
ritmo médio.

- **`rate`** — reposição sustentada (o que o fornecedor tolera continuamente).
- **`burst`** — tamanho do balde (quanto de lote absorve de uma vez).

### 3.3 O que acontece quando não há token

A task **não bloqueia o worker** — ela é reagendada (`retry`) com espera. Bloquear seria pior que o
problema: um worker parado esperando token deixa de processar todo o resto da fila, inclusive tarefas
de outros tenants.

Isso também muda a natureza do retry: em vez de multiplicar a pressão sobre um fornecedor já saturado,
o retry **consome do mesmo balde** e se espaça naturalmente.

### 3.4 Falha do Redis

**Fail-open, mas ruidoso.** Se o contador estiver indisponível, a chamada passa — porque estourar o
limite do fornecedor gera `429` dele (que o retry já trata), enquanto travar tudo pararia a emissão de
notas e boletos do sistema inteiro. Mas a falha é registrada em nível de erro e conta métrica: um
protetor fail-open que perde a dependência fica **indistinguível de um protetor funcionando**, e essa
foi a origem de um incidente real neste projeto (ver `D21` em [../pendencias.md](../pendencias.md)).

### 3.5 Escopo do balde e credencial por tenant

Enquanto a credencial do fornecedor é **global** (uma conta para todos os tenants), o balde é global —
é a cota real sendo disputada. Quando a credencial passar a ser **por tenant** (previsto para o Asaas),
a chave do balde precisa incluir o tenant: cada empresa passa a ter a própria cota no fornecedor, e um
balde global limitaria empresas que não têm relação entre si.

## 4. Camada 3 — Cota comercial (plano)

Diferente das duas anteriores: não é proteção técnica, é **produto**. Quantas notas, boletos, análises
de IA ou mensagens o plano contratado inclui por mês. Excedente vira bloqueio ou upsell, não `429`.

Depende do modelo de assinatura (ver [monetizacao.md](monetizacao.md)) e por isso caminha junto do
paywall, não antes dele. O contador é por tenant e por período de faturamento — e deve ser **auditável**,
porque vira fatura.

## 5. Como isto se relaciona com o resto

- **Entitlement de módulo** (`RequireModule`) responde "esta empresa contratou o módulo?" — é binário e
  anterior a qualquer limite. Rate limit responde "quanto pode usar agora".
- **Permissão** (`RequirePermission`) responde "este usuário pode esta ação?". Um usuário autorizado
  ainda está sujeito aos tetos.
- **DLQ** — chamada que esgota retries por limite de fornecedor termina na fila de falhas como qualquer
  outra falha permanente, e é sinal operacional de que o `rate` está mal calibrado (ou de que o plano
  contratado no fornecedor ficou pequeno).

## 6. Calibração

Regra: o `rate` sai do **contrato com o fornecedor**, não de estimativa de uso. Se o fornecedor publica
limite, use uma fração dele (folga para picos e para outros consumidores da mesma conta). O `burst` sai
do **maior lote legítimo** esperado — se o maior fechamento emite 200 notas de uma vez, um balde menor
que isso transforma operação normal em fila.

Sinais de má calibração: DLQ com falhas de limite (apertado demais) ou `429` vindo do próprio
fornecedor (folgado demais).
