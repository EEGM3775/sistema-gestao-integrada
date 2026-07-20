# `payment/` — os botões comerciais do produto

> **Este é o arquivo que o dono do software mexe.** Preço, quota, tamanho de plano e teto de
> requisições moram aqui, fora do código de negócio. Mudar um número aqui não exige entender Django,
> IAM ou throttle — e não deveria exigir tocar em mais nenhum arquivo.

## Por que um pacote na raiz

Mesmo motivo do [`funcoesemail/`](../funcoesemail/README.md): é importado pelos **dois serviços** (IAM
e backend) e não é módulo de negócio de nenhum deles. As imagens de IAM e backend buildam com contexto
na raiz, então o import funciona sem hop de rede e sem duplicar a tabela de planos — que é como ela
ficaria desatualizada em um dos lados.

## Tudo que trata de plano/pagamento mora nesta pasta

Foi decisão explícita: quem faz manutenção do modelo comercial abre **só `payment/`**. Dentro dela há
uma fronteira que vale respeitar — os **valores** (o que você edita à vontade) e as **regras** (a
engenharia que lê esses valores):

| Arquivo | O quê | Quem mexe |
|---|---|---|
| **`planos.py`** | planos, quotas, teto de requisições e **quais quotas travam** (§4) | **você**, sem revisão de código |
| **`addons.py`** | preços dos add-ons (usuário extra, pacote de IA, drone avulso…) | **você**, sem revisão de código |
| **`regras.py`** | como o teto deriva dos seats, precedência do contrato, o que vale sem plano | engenharia — **não** edite para "ajustar um preço" |

### E o enforcement? Fica nos serviços, e você não toca nele

Duas coisas ficam **fora** de `payment/`, e não por escolha de organização — é impossível trazê-las:

- `iam/identity/quotas.py` — trava de **seats** (conta usuário no banco **da IAM**);
- `backend/nucleo/quotas.py` — trava de **objetos** (conta obra/cliente no banco **do backend**).

`payment/` é Python puro, sem Django, e é o que permite os dois serviços importarem ele. O enforcement
precisa do framework (a exceção HTTP) e precisa contar linhas **no banco de cada serviço** — são dois
bancos diferentes, e um pacote compartilhado não alcança nenhum deles. Então a contagem roda onde o
dado está, mas **toda decisão** (o limite, o que trava) ela pergunta para `payment/`. Você não edita
esses arquivos para mexer no modelo comercial; eles só executam o que está aqui.

### A §4 do `planos.py` é um botão comercial, não configuração técnica

Declarar uma quota na tabela de planos **não a faz valer**. Ela só barra o cliente se o nome dela
estiver em `QUOTAS_APLICADAS`. Essa lista mora aqui — e não no código de engenharia — porque mexer
nela mexe no faturamento, e nos dois sentidos:

| Mudança | Efeito |
|---|---|
| **Tirar** um nome da lista | o limite deixa de morder. O cliente do `free` cadastra sem parar e nunca vê motivo para pagar. **Vazamento de receita, e silencioso** — nada quebra, nada aparece no log. |
| **Pôr** um nome sem contador do outro lado | o cliente é barrado por um limite que ninguém sabe medir. |
| **Mover** uma quota de COGS para a lista | troca "cobrar excedente" por "barrar o cliente" — ver a regra de ouro em [monetizacao.md §4](../docs/arquitetura/monetizacao.md). |

O segundo e o terceiro casos não passam despercebidos: `backend/nucleo/test_quotas.py` **falha** se a
lista comercial e os contadores divergirem, e o CI barra o merge. O primeiro caso é decisão sua, e é
por isso que a lista está à vista neste arquivo.

## O que já está ligado e o que ainda não

| Quota | Estado |
|---|---|
| `requisicoes_hora` | ✅ aplicada — teto do eixo por tenant do throttle (**D23**) |
| `seats` | ✅ aplicada na **IAM** — criar/reativar usuário acima do teto dá **402** |
| `empreendimentos`, `obras`, `clientes`, `fornecedores` | ✅ aplicadas no **backend** — criar acima do teto dá **402** |
| `armazenamento_gb`, `analises_ia_mes`, `notas_fiscais_mes`, `cobrancas_mes`, `processamentos_drone_mes` | ⏸️ declaradas e **inertes** |

A linha de baixo é **inerte por desenho, não por atraso**: é a família de COGS, e a regra de ouro do
[monetizacao.md §4](../docs/arquitetura/monetizacao.md) manda **medir e cobrar o excedente** dela, não
travar. Parar o cliente no meio de um fechamento fiscal para vender um pacote custa mais caro que o
excedente que se evitaria. Quando os medidores existirem (D24 item 5), o efeito será fatura, não 402.

Declarar as quotas antes de cobrá-las é o que permite testar o modelo de planos em dev e staging **sem
checkout** — que foi o que motivou este pacote.

## Como mudar um plano

1. Edite o valor em `planos.py`.
2. Reinicie a IAM (o catálogo é lido no import; não há cache além do processo).
3. Os usuários recebem o teto novo no **próximo refresh** do token (≤ 5 min) — mesma propagação de
   permissão, ver [acesso-e-permissoes.md](../docs/acesso-e-permissoes.md).

Nenhuma migration é necessária: `Tenant.plano` guarda só o **slug** do plano, e as quotas vivem aqui.

## O que você muda aqui sozinho, e o que precisa de um engenheiro

**Só nesta pasta, sem revisão de código:**

| Objetivo | Arquivo · onde |
|---|---|
| Mudar um **preço** | `planos.py` · `PLANOS[<plano>]["preco_mensal"]` |
| Mudar uma **quota** | `planos.py` · `PLANOS[<plano>]["obras"]` etc. |
| **Criar/remover um plano** | `planos.py` · entrada em `PLANOS` **+** o slug em `ORDEM_PLANOS` |
| **Criar/remover um add-on** ou mexer no **excedente** | `addons.py` · `ADDONS` / `EXCEDENTES` |
| Afrouxar/apertar o **teto de requisições** | `planos.py` · `RATE_BASE_HORA` · `RATE_POR_SEAT_HORA` · `RATE_TETO_INFRA_HORA` |
| **Ligar/desligar** a trava de um recurso **que já é contado** | `planos.py` · `QUOTAS_APLICADAS` (§4) — só `seats`, `empreendimentos`, `obras`, `clientes`, `fornecedores` são contados hoje |

**Precisa de um engenheiro** (o **número** ainda é seu, aqui; o encanamento é código):

- **travar um recurso novo** que ninguém conta ainda → registrar o contador em
  `backend/nucleo/quotas.py` (senão o CI barra, de propósito);
- **cobrar excedente** de IA/NF/boleto/drone (hoje inertes) → é feature, não valor;
- **checkout / auto-serviço** e a **UI do paywall** → itens de roadmap, ainda não existem.

**Nem é código:** *colocar o cliente X no plano Empresarial* é **dado** (`Tenant.plano`), definido no
provisionamento/admin da IAM — não se edita aqui. Esta pasta define o que **cada plano é**; **quem está
em qual plano** é banco.

> **`plano` vazio = `free`** (1 seat, 2 obras). É o default seguro, mas **todo tenant real precisa de
> `plano` gravado** antes do go-live, senão a trava o capa em 1 usuário. Os seeds de dev já gravam.

Guia completo (mapa de todos os arquivos, inclusive os de engenharia) e racional de preço:
[monetizacao.md §11](../docs/arquitetura/monetizacao.md) — em especial **§11.4** (este playbook) e
**§11.5** (mapa de arquivos por camada).
