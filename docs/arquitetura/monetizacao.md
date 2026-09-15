# Monetização, planos e limites

> **Prancha de desenho — proposta v1, a validar.** Estuda o **paywall / auto-serviço**: como o
> cliente descobre, paga, ativa e é limitado conforme o que pagou. Números em BRL são **proposta de
> partida** (ajustar com dados reais de custo e mercado).
> Camada de acesso *dentro* do tenant: [rbac-abac.md](rbac-abac.md).
>
> **Deixou de ser só planejamento em 19/07/2026.** O checkout continua sendo fase futura
> ([D24](../historico-correcoes.md)), mas o **modelo de planos existe em código** e uma quota já é aplicada de
> verdade — ver [§11](#11-onde-o-modelo-de-planos-vive-em-código-paywall-e-catálogo). Isso foi feito
> antes do paywall de propósito: sem os planos declarados, o teto de requisições do **D23** não teria
> de onde tirar o tamanho de cada empresa.

## 1. Visão — o módulo tem duas faces

O "nucleo de acesso" é a **chave financeira** do projeto: o que impede usar o software sem pagar.

| Face | O que faz | Onde vive |
|---|---|---|
| **A. Paywall / auto-serviço** (externo) | landing → checkout → cadastro → pagamento → código de ativação → usa o que pagou; planos com **quotas** | novo fluxo público + IAM (`Tenant`/`AssinaturaTenant`) + Asaas |
| **B. Acesso intra-tenant** (interno) | o **admin** (1º usuário, quem pagou) libera cada usuário a empreendimentos/recursos | [rbac-abac.md](rbac-abac.md) + ABAC por objeto |

**O admin é a ponte:** o pagamento cria o `Tenant`, a assinatura (com limites) e o **1º usuário = admin**;
esse admin acessa tudo e distribui acesso aos demais (deny-by-default, por recurso, direto + equipes).

**Reaproveita o que já existe:** `AssinaturaTenant.limites` (JSONField — gancho de quota pronto),
`funcoescobrancas`/**Asaas** (PIX/boleto/cartão já integrados), provisionamento na IAM, `PreCadastro`.

### 1.1 Usuário ↔ Funcionário (vínculo de identidade)

Todo **usuário de login é vinculado a um Funcionário** (`rh.Funcionario`). Regras do vínculo:

- **Cardinalidade 1:1, opcional pelo lado do funcionário:** um funcionário **pode** ter um usuário de
  login (nem todo funcionário usa o sistema — ex.: um pedreiro não loga); um usuário **sempre**
  corresponde a um funcionário (é a pessoa que acessa). O 1º admin também é um funcionário (o dono).
- **Implicação de billing (seat):** o limite de "usuários" do plano conta **funcionários** — funcionário consome seat. Criar/ativar um login checa a quota de usuários.
- **Implicação de acesso:** o usuário **herda o Cargo** do funcionário (e o cargo pode sugerir o
  **papel de acesso** — a ponte Cargo→Persona de [rbac-abac.md §9.1](rbac-abac.md)). PII do funcionário
  é do RH; credenciais/identidade são da IAM.
- **Provisionamento:** na ficha do funcionário (RH), um botão **"criar acesso"** gera o `Usuario`
  vinculado (define username/e-mail), conta o seat e permite atribuir papéis. Desligar o acesso
  **libera o seat** sem apagar o funcionário.
- **Desenho cruza serviços (decisão a registrar):** `Funcionario` vive no **backend** (`TenantScopedModel`)
  e `Usuario` na **IAM** (autoridade de identidade). O vínculo precisa de uma **referência estável** —
  proposta: `Funcionario.usuario_ref` guarda o `sub`/UUID do usuário da IAM (a IAM continua dona da
  identidade; o backend só referencia). O provisionamento JIT já cria o `nucleo.Usuario` espelho a partir
  do JWT — o vínculo se dá por esse `sub`.

---

## 2. Modelo de cobrança — estudo e recomendação

**Recomendado: assinatura recorrente (mensal + anual), + taxa de implantação opcional.** SaaS com
custo de infra contínuo (processamento de drone, IA, armazenamento) **não se sustenta em licença
única** — a licença única cobra uma vez e paga infra para sempre. O "código de ativação" que você
descreveu vira a **confirmação do 1º pagamento**, não uma licença perpétua.

Como lidar com cada situação:

| Situação | Como tratar |
|---|---|
| **Mensal** | Porta de entrada, menor barreira. Cartão (recorrência automática) ou PIX/boleto (renovação manual com lembrete). |
| **Anual** | Desconto de **2 meses** (paga 10, usa 12 = ~17% off). Melhora caixa e **reduz churn**. |
| **Licença única** | Não para o core. Só como **taxa de implantação/onboarding assistido** (one-time) — receita extra sem canibalizar a recorrência. |
| **Upgrade de plano** | Imediato, com **cobrança pró-rata** do período restante. |
| **Downgrade** | Vale no **fim do ciclo** (evita reembolso e abuso). Bloqueia se o uso atual excede o plano menor. |
| **Falha de pagamento (dunning)** | 3 tentativas em 7 dias (lembrete PIX/boleto); depois **suspende** (read-only); cancela após 15–30 dias. |
| **Cancelamento** | Fim do ciclo pago; dados em **read-only** por 30 dias e depois arquivados (janela de reativação). |

---

## 3. Gateway de pagamento + ativação — estudo (mais barato e confiável)

| Opção | Custo (BR, ordem de grandeza) | Prós | Contras |
|---|---|---|---|
| **Asaas** ✅ (já integrado) | PIX ~R$0,99 (ou %), boleto ~R$1,99, cartão ~2,99–4,99% + fixo | PIX instantâneo e barato; boleto; **recorrência de cartão**; webhook **já implementado** | menos "global" que Stripe |
| Stripe | cartão ~3,99% + R$0,39 | ótimo p/ cartão internacional, DX | boleto/PIX fracos; trocaria o Asaas existente |
| PagarMe/outros | similar ao Asaas | BR-first | nova integração |

**Recomendação: Asaas** — mais barato no meio BR (PIX), confiável, e **já está no projeto**. Cartão
para a recorrência automática; PIX para quem quer ativar na hora; boleto como opção.

**Entrega do código de ativação: e-mail (grátis) como padrão.** Com **PIX**, o pagamento confirma em
segundos → ativação quase imediata. **SMS fica como add-on** (custa ~R$0,08–0,19/msg via Zenvia/Twilio;
liga só se a conversão justificar). Confiabilidade: e-mail transacional dedicado (evita spam) + reenvio.

---

## 3.1 Módulo × capacidade — nem tudo que se vende é um lugar

*(decisão do dono, 08/08/2026, tomada sobre a Prancheta.)*

A unidade de venda padrão é o **módulo**, e ele é um lugar: o cliente contrata o SCM e passa a ter as
telas do SCM. Mas parte do catálogo não tem essa forma. **A [Prancheta](../modulos/moduloprancheta.md)
não vende um lugar, vende uma capacidade** — *ver os próprios arquivos e projetos dentro do software*
—, e essa capacidade é consumida de dentro de outros módulos: o Orçamento que precisa mostrar a
prancha de uma composição, o SIL que mostra a planta do almoxarifado, o diário que abre o detalhe
citado no apontamento.

Três consequências comerciais, e as três já valem em código:

1. **O formato é vendido uma vez.** `formatos_prancheta` deixou de significar "o que a Prancheta
   abre" e passou a significar **"o que esta empresa abre no sistema"**. Quem aplica a parede é o
   motor de import/export na porta única, não cada módulo — um 402 só, com o mesmo corpo, em qualquer
   tela ([funcoesimpexp §2, R17](../modulos/funcoesimpexp.md)).
2. **A capacidade e o acabamento são duas vendas, porque são dois custos.** Abrir DWG é a capacidade;
   abrir com alta fidelidade é o motor premium (`motores_prancheta`), que é COGS por tradução — cai
   na família §4.2, não na §4.1.
3. **Não contratar nunca vira função invisível.** O usuário vê o cadeado com o motivo **na tela onde
   estava**, o que é upsell no momento da necessidade — o oposto de descobrir a ausência procurando
   um menu que não existe ([frontend.md §1.6](../frontend.md)).

Ao desenhar um item novo do catálogo, a pergunta é: *isto é um lugar aonde a pessoa vai, ou algo que
ela passa a poder fazer em todo lugar?* A segunda resposta muda onde o gate mora e onde o cadeado
aparece.

## 4. Catálogo de limites — o estudo central (não só os 5 citados)

Nem todo limite pesa igual. Separo em **duas famílias**, porque a estratégia de cada uma difere:

### 4.1 Limites de valor/segmentação (baratos de servir → travam por plano)
Servem para diferenciar planos e capturar disposição a pagar; custo marginal ~zero.

- **Usuários (logins/funcionários)** — principal alavanca de preço (per-seat percebido).
- **Empreendimentos**, **Obras**, **Clientes**, **Fornecedores** — porte da operação.
- **Leads/Contatos (CRM)**, **Entradas de diário/mês** — intensidade de uso.
- **Retenção de histórico** (meses) e **usuários com acesso "vê todos"**.

### 4.2 Limites de consumo com CUSTO REAL (COGS → medir e/ou cobrar excedente)
Estes geram desembolso a cada uso; são o que protege a **margem**.

| Recurso | Por que custa | Unidade de limite |
|---|---|---|
| **Processamento de drone (ODM)** | CPU/tempo alto por job — **o maior custo** | processamentos/mês |
| **Tamanho/qtd de imagem de drone** | storage + tempo de processamento | MP e MB por imagem; nº de imagens/processamento |
| **Armazenamento** | ortofotos, nuvens de pontos, documentos | GB totais |
| **Análises de IA (Gemini/LLM)** | custo por chamada (ou compute local) | análises/mês |
| **NF-e/NFS-e** (NFE.io) | custo por nota emitida | NF/mês |
| **Cobranças/boletos (Asaas)** | custo por boleto/PIX emitido | cobranças/mês |
| **E-mail / SMS** | SMS tem custo por envio | envios/mês |

> **Regra de ouro:** limite de valor → **trava dura + upsell**; limite de COGS → **medidor com
> excedente cobrado** (não trava o cliente no meio da operação e ainda protege a margem).

---

## 5. Planos (híbrido) — proposta v1

Preços mensais; **anual = 10× o mensal** (2 meses grátis). Valores a calibrar com custo real + mercado
(referências BR de gestão de obra: faixa ~R$150–1.500/mês).

> **Plano `free` (decidido 19/07/2026), anterior ao Essencial.** É o degrau de aquisição *e* o
> default de quem não tem assinatura: 1 usuário, 1 empreendimento, 2 obras, 20 clientes, 1 GB, sem
> ERP/CRM/IA/drone. Restritivo em **objeto**, honesto em **experiência** — os módulos base funcionam
> de verdade, porque quota apertada demais na experiência não converte, desinstala. Serve o caso "1
> engenheiro validando o produto" e é o default **seguro**: tenant provisionado com erro cai no plano
> menor, nunca em "sem limite".

| Recurso | **Essencial** R$149/mês | **Profissional** R$449/mês | **Empresarial** R$1.199/mês |
|---|---|---|---|
| **Módulos** | Base (obras, empreend., clientes, fornecedores, diário), RH básico, Calendário | + **ERP Financeiro**, **CRM**, Diário **IA** | **Tudo** + **Drone** |
| Usuários | 3 | 12 | 40 |
| Empreendimentos | 2 | 10 | 50 |
| Obras | 8 | 40 | 200 |
| Clientes / Fornecedores | 100 | 1.000 | 10.000 |
| Armazenamento | 5 GB | 100 GB | 500 GB |
| Análises de IA/mês | 30 | 300 | 1.500 |
| NF-e/mês | — | 100 | 500 |
| Cobranças Asaas/mês | — | 200 | 1.000 |
| Processamentos de drone/mês | — | *add-on* | 25 |
| Imagem de drone | — | *add-on* | até 60 MP / 40 MB; 500 imgs/proc |

**Racional de posicionamento:** *Essencial* atrai o pequeno construtor (entra fácil, barato, quase sem
COGS); *Profissional* é o **sweet spot** de margem (financeiro + CRM, custo baixo, preço médio);
*Empresarial* captura o **drone** (alto valor percebido, alto COGS, preço premium). *Sob Medida
(Enterprise)* para grandes: preço negociado, limites altos, SLA.

### 5.1 Add-ons (upsell contínuo — o "híbrido")

| Add-on | Preço sugerido |
|---|---|
| Usuário extra | R$29/usuário/mês |
| Empreendimento extra | R$19/mês · pacote 10 obras: R$49/mês |
| **Módulo Drone** (sobre Essencial/Profissional) | R$349/mês (inclui 10 processamentos + 100 GB) |
| Processamento de drone extra | R$25 cada · pacote 10: R$199 |
| Armazenamento +100 GB | R$79/mês |
| Pacote IA +500 análises/mês | R$99/mês |
| NF-e excedente | R$0,60/NF · Boleto excedente: repasse Asaas + R$0,50 |
| Ativação/notificação por SMS | R$0,19/envio |

---

## 6. Trial — 28 dias, com limitações

- **28 dias, sem cartão** (cria o `Tenant` na hora). Libera os módulos do **Profissional** com **caps
  de trial**: 3 usuários, 1 empreendimento, 3 obras, 20 clientes, 2 GB, **3 processamentos de drone**
  (imagens até 20 MP, máx 30/proc), 30 análises de IA, **NF-e em sandbox** (não vale fiscalmente), 5
  cobranças de teste.
- **Fim do trial:** converte (escolhe plano) → migra dados; senão **read-only por 15 dias** → arquiva.
- Anti-abuso: 1 trial por CNPJ/e-mail; verificação no cadastro.

---

## 7. Comportamento ao atingir o limite

- **Seats e objetos** (usuários, empreendimentos, obras, clientes): **bloqueia a criação** com CTA de
  upgrade ("seu plano permite N; faça upgrade para adicionar"). Previsível e sem surpresa na fatura.
- **Consumo com COGS** (drone, IA, NF, boleto, storage): **alerta em 80%/100%** e permite continuar
  como **excedente cobrado** (ou exige comprar pacote), para não travar a operação.
- **Assinatura suspensa/vencida:** tudo em **read-only**, exceto a tela de pagamento.

---

## 8. Fluxo de auto-serviço (onboarding) — mapeado no que já existe

```
Landing "Planos" → Checkout público → PreCadastro (dados + plano escolhido)
   → Pagamento Asaas (PIX/cartão)  →  webhook confirma
   → cria Tenant + AssinaturaTenant(limites=plano) + 1º Usuario(admin)
   → gera código de ativação → e-mail (PIX: quase instantâneo)
   → admin ativa (define senha) → usa o que pagou
Trial: cria Tenant trial (sem pagamento) com limites de trial + expira_em
```

- **Quotas** vivem em `AssinaturaTenant.limites` (JSON por módulo) — o campo **já existe**.
- **Provisionamento** reusa a IAM (`Tenant`, `Usuario`, `AssinaturaTenant`, `AcessoUsuarioModulo`).
- **Pagamento** reusa `funcoescobrancas`/Asaas (webhook já implementado).

---

## 9. Enforcement — desenho (implementação é fase futura)

- **Quota de seats/objetos:** um `QuotaEnforcedMixin` no `nucleo` intercepta o `perform_create` do
  ViewSet, conta uso vs. `limites`, e **bloqueia (402/403) com mensagem de upgrade**.
- **Quota de consumo:** contador mensal de uso (por tenant/recurso) checado no ponto de disparo
  (processar drone, emitir NF, gerar boleto, chamar IA); excedente → cobra ou exige pacote.
- **Estado da assinatura:** entitlement já barra módulo não contratado; **suspensa** → middleware
  força read-only exceto billing.
- **Fonte de verdade da quota:** o plano define os `limites`; um **catálogo de planos em código**
  (espelho do que fizemos no catálogo de permissões) evita "planos mágicos" no banco.

---

## 10. Faseamento sugerido (quando implementar)

1. **Catálogo de planos + quotas** (em código) e leitura de `AssinaturaTenant.limites`.
2. **Enforcement de seats/objetos** (mixin) — trava dura + upsell.
3. **Checkout público + Asaas + provisionamento automático** (landing → paga → cria tenant/admin).
4. **Ativação por e-mail** + código; trial de 28 dias com expiração.
5. **Medidores de consumo** (drone/IA/NF/boleto/storage) + excedente.
6. **Portal de billing** (upgrade/downgrade/2ª via, dunning) e SMS opcional.

---

## 11. Onde o modelo de planos vive em código (paywall e catálogo)

Implementado em **19/07/2026** (junto do D23; consolidado no D24). **Todo o modelo comercial vive na
pasta [`payment/`](../../payment/README.md)** — decisão explícita do dono do software, para quem faz
manutenção abrir uma pasta só. Dentro dela, uma fronteira por arquivo:

| Arquivo | O quê | Quem mexe |
|---|---|---|
| **`payment/planos.py`** | **valores**: planos, quotas, preços, parâmetros do teto e **quais quotas travam** (§4) | o **dono do software**, sem revisão de código |
| **`payment/addons.py`** | **valores** dos add-ons | o **dono do software**, sem revisão de código |
| **`payment/regras.py`** | **regras**: como o teto deriva dos seats, precedência, o que vale sem plano | engenharia |

`payment/` é pacote na raiz pelo mesmo motivo do [`funcoesemail/`](../../funcoesemail/README.md): é
importado pelos dois serviços e não é módulo de negócio de nenhum. É **Python puro (sem Django)**, e é
isso que permite IAM e backend importarem sem hop de rede nem tabela de planos duplicada.

**O enforcement fica nos serviços, por necessidade física, não escolha:** `iam/identity/quotas.py`
(trava de seats) e `backend/nucleo/quotas.py` (trava de objetos) precisam do framework (a exceção HTTP)
e precisam **contar linhas no banco de cada serviço** — são dois bancos, e o pacote compartilhado não
alcança nenhum. A contagem roda onde o dado está, mas pergunta **todo limite** a `payment/regras.py`.
Não há decisão comercial nesses dois arquivos; o dono não os edita.

### 11.1 O que já é aplicado, e o que está declarado e inerte

**Aplicado hoje:** só `requisicoes_hora`. A IAM calcula o teto do tenant e o emite como claim
`rate_hora` do access token; o backend o usa como teto do eixo por tenant do throttle (D23). A IAM é
quem calcula porque **só ela sabe quantos seats a empresa contratou** — o `Usuario` do backend é
espelho JIT (só existe quem já logou), então contar lá daria um número menor que o contratado e
crescente durante a implantação do cliente.

**Declarado e inerte:** todas as demais quotas do §5 (obras, clientes, storage, IA, NF, boletos,
processamentos de drone). Existem para serem lidas, exibidas e versionadas; nada as bloqueia até o
**D24**. Declará-las antes de cobrá-las é o que permitiu testar o modelo de planos em **dev e staging
sem checkout**, que foi o motivo de fazer isto agora.

### 11.2 Como o teto de requisições deriva do plano

```
teto = min(RATE_BASE_HORA + seats × RATE_POR_SEAT_HORA, RATE_TETO_INFRA_HORA)
```

Precedência, do mais forte ao mais fraco: **`AssinaturaTenant.limites`** (o contratado de fato, onde o
*Sob Medida* grava o negociado) → **o plano** (`Tenant.plano`) → **`free`** (o padrão).

Três decisões que valem registro:

- **Deriva de seats CONTRATADOS, não de usuários ativos.** O cliente recebe o que comprou mesmo antes
  de cadastrar todo mundo, e o teto não muda sozinho durante a implantação. Consequência boa:
  **comprar o add-on de usuário extra aumenta o teto automaticamente** — o limite acompanha a receita
  em vez de brigar com ela. É o que Shopify faz por tier e o GitHub pelo tamanho da organização.
- **Teto fixo não existe.** Um número só não serve para 1 e para 1000 funcionários: alto o bastante
  para o cliente grande não protege contra o médio abusando; baixo o bastante para proteger inutiliza
  o grande. Foi exatamente o defeito da primeira versão do D23.
- **`RATE_TETO_INFRA_HORA` não é número comercial, é de capacidade.** Fica acima de qualquer plano,
  inclusive do *Sob Medida* — "ilimitado" no contrato não pode virar ilimitado no eixo de requisições,
  senão um tenant sozinho consome a capacidade dos outros. Todo grande mantém esse limite absoluto por
  cima da fórmula (o GitHub para em 12.500/h) para ela não virar cheque em branco. Contrato que
  precise de mais exige **projeto de capacidade** (réplicas), não cláusula.

### 11.3 Propagação

Mudar plano ou quota vale no **próximo refresh** do token (≤ TTL do access), igual à mudança de
permissão — o refresh recalcula as claims. Não há migration: `Tenant.plano` guarda só o slug.

### 11.4 Manual do dono — o que muda só em `payment/` e o que precisa de engenheiro

A régua de bolso: **mexer nos números do modelo que já existe → só `payment/`. Criar uma capacidade
nova de cobrança → o número é seu, o encanamento é do engenheiro (uma vez).**

**Só `payment/`, sem revisão de código** (vale no próximo refresh do token, ≤ 5 min; sem migration,
sem deploy de lógica):

| O que você quer fazer | Arquivo | Onde exatamente |
|---|---|---|
| Mudar um **preço** | `payment/planos.py` | `PLANOS[<plano>]["preco_mensal"]` |
| Mudar uma **quota** (ex.: `free` com 3 obras) | `payment/planos.py` | `PLANOS[<plano>]["obras"]` |
| **Criar / remover um plano** inteiro | `payment/planos.py` | entrada em `PLANOS` **+** o slug em `ORDEM_PLANOS` (a régua de upgrade) |
| **Criar / remover um add-on** | `payment/addons.py` | `ADDONS` |
| Mudar o **preço de excedente** (COGS) | `payment/addons.py` | `EXCEDENTES` |
| Afrouxar/apertar o **teto de requisições** | `payment/planos.py` | `RATE_BASE_HORA` · `RATE_POR_SEAT_HORA` · `RATE_TETO_INFRA_HORA` |
| **Ligar/desligar** a trava de um recurso **que já é contado** | `payment/planos.py` | `QUOTAS_APLICADAS` / `QUOTAS_DE_OBJETO` (§4) |

> **Recursos que já são contados hoje** (dá para ligar/desligar a trava sozinho): `seats`,
> `empreendimentos`, `obras`, `clientes`, `fornecedores`. Só esses.

**Precisa de um engenheiro** (o **número** ainda vai em `payment/`, mas o encanamento é código):

| O que você quer fazer | Por que não é só `payment/` |
|---|---|
| **Travar um recurso novo** (ex.: "limitar entradas de diário/mês") | O código não sabe *qual tabela contar* até um engenheiro registrar o recurso em `backend/nucleo/quotas.py` (`RECURSOS_CONTADOS`). Se você puser o nome em `QUOTAS_APLICADAS` sem esse contador, **o teste de CI falha de propósito** — é a rede que impede cobrar por algo que ninguém sabe medir. |
| **Cobrar excedente** de IA / NF / boleto / drone | Hoje esses limites estão **declarados e inertes**. Virar medição + fatura é uma *feature* (item 5 do §10), não uma edição de valor. |
| **Checkout / auto-serviço** (landing → Asaas → provisionamento) | Não existe ainda (item 3 do §10). |
| **UI do paywall** (medidor, aviso, tela de upgrade) | É a **fase G** do frontend ([frontend.md §5.16](../frontend.md)); o backend já serve os dados. |

**Nem é código:** *colocar o cliente X no plano Empresarial* não toca `payment/`. O plano de cada
empresa é **dado** (`Tenant.plano`), definido no provisionamento / admin da IAM. `payment/` define o
que **cada plano é**; **quem está em qual plano** é banco. O negociado do "Sob Medida" mora em
`AssinaturaTenant.limites` (também dado), que tem precedência sobre o plano.

### 11.5 Mapa de arquivos — onde encontrar cada coisa

Quatro camadas. O dono só edita a primeira; as outras três são engenharia e existem para **executar** a
primeira.

**1. Decisão comercial — `payment/` (o dono edita):**

| Arquivo | Conteúdo |
|---|---|
| [`payment/planos.py`](../../payment/planos.py) | planos e suas quotas (`PLANOS`), régua de venda (`ORDEM_PLANOS`), plano padrão (`PLANO_PADRAO`), parâmetros do teto (`RATE_*`) e **quais quotas travam** (`QUOTAS_APLICADAS`/`QUOTAS_DE_OBJETO`/`QUOTA_SEATS`, §4) |
| [`payment/addons.py`](../../payment/addons.py) | add-ons (`ADDONS`) e excedentes de COGS (`EXCEDENTES`) |
| [`payment/regras.py`](../../payment/regras.py) | *engenharia dentro de `payment/`*: como o teto deriva dos seats, precedência do contrato, fallback (`teto_requisicoes_hora`, `quota_efetiva`, `quotas_efetivas`, `proximo_plano`, `plano_valido`) |
| [`payment/README.md`](../../payment/README.md) | o guia do dono — a versão curta deste §11 |

**2. Emissão — a IAM põe o plano no token (engenharia):**

| Arquivo | Papel |
|---|---|
| [`iam/identity/tokens.py`](../../iam/identity/tokens.py) | `build_claims` emite as claims `plano`, `rate_hora` e `quotas` no access token, chamando `payment/regras.py` |
| [`iam/identity/models.py`](../../iam/identity/models.py) | `Tenant.plano` (o slug contratado) e `Tenant.limites_contratados()` (funde `AssinaturaTenant.limites` das assinaturas ativas) |

**3. Enforcement — cada serviço aplica, no seu banco (engenharia; o dono não toca):**

| Arquivo | Trava o quê |
|---|---|
| [`iam/identity/quotas.py`](../../iam/identity/quotas.py) | **seats** — conta usuário ativo no banco da IAM (`checar_seats`); 402 ao criar/reativar acima do teto |
| [`backend/nucleo/quotas.py`](../../backend/nucleo/quotas.py) | **objetos** — `QuotaEnforcedMixin` + `RECURSOS_CONTADOS` (qual tabela contar) + `checar_quota`; 402 na criação acima do teto |
| [`backend/nucleo/authentication.py`](../../backend/nucleo/authentication.py) | lê as claims do token para `user.iam_plano` / `iam_quotas` / `iam_rate_hora` |
| [`backend/nucleo/throttling.py`](../../backend/nucleo/throttling.py) | aplica `rate_hora` como teto do eixo por tenant (D23) |

**4. Apresentação e provas:**

| Arquivo | Papel |
|---|---|
| [`backend/nucleo/plano_views.py`](../../backend/nucleo/plano_views.py) | `GET /api/plano/` — plano vigente, medidores (uso × limite), **janelas** (limites de TEMPO, como `lixo_retencao_dias`: vêm separados porque janela não tem uso a contar e viraria medidor quebrado), próximo degrau e o catálogo com preços (tudo lido de `payment/`, nada hardcoded no front) |
| [`backend/nucleo/test_quotas.py`](../../backend/nucleo/test_quotas.py) | testes da trava de objeto + **a rede que barra divergência** entre `QUOTAS_APLICADAS` e `RECURSOS_CONTADOS` |
| [`iam/identity/test_quotas.py`](../../iam/identity/test_quotas.py) · [`test_planos.py`](../../iam/identity/test_planos.py) | testes da trava de seats e das regras/claim |
| [frontend.md §5.16](../frontend.md) | a UI do paywall — planejada (**fase G**), ainda não construída |

---

## 12. Decisões em aberto (para você confirmar)

- **Preços/limites** da tabela §5 — calibrar com seu **custo real** (quanto custa 1 processamento de
  drone? 1 GB/mês? 1 análise de IA?) e com o preço que o mercado-alvo topa.
- **Faixa do público-alvo:** micro/pequena construtora (preço baixo, volume) vs. média/grande (preço
  alto, menos clientes)? Isso desloca toda a tabela.
- **Anual obrigatório em algum plano?** (ex.: Empresarial só anual, para caixa e menos churn).
- **Excedente cobrado vs. só bloqueio** nos recursos de COGS — apetite a cobrança variável.
- **Taxa de implantação** (onboarding assistido) — cobrar? quanto?
- **Drone no trial** — liberar 3 processamentos reais custa CPU; manter ou trocar por vídeo-demo?
