# Monetização, planos e limites — estudo do consultor (PLANEJAMENTO, sem código)

> **Prancha de desenho — proposta v1, a validar.** Estuda o **paywall / auto-serviço**: como o
> cliente descobre, paga, ativa e é limitado conforme o que pagou. Números em BRL são **proposta de
> partida** (ajustar com dados reais de custo e mercado). Não há código aqui; a implementação é uma
> fase futura do [roadmap](../roadmap.md). Camada de acesso *dentro* do tenant: [rbac-abac.md](rbac-abac.md).

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
- **Desenho cruza serviços (decisão a registrar):** `Funcionario` vive no **ERP** (`TenantScopedModel`)
  e `Usuario` na **IAM** (autoridade de identidade). O vínculo precisa de uma **referência estável** —
  proposta: `Funcionario.usuario_ref` guarda o `sub`/UUID do usuário da IAM (a IAM continua dona da
  identidade; o ERP só referencia). O provisionamento JIT já cria o `nucleo.Usuario` espelho a partir
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

## 11. Decisões em aberto (para você confirmar)

- **Preços/limites** da tabela §5 — calibrar com seu **custo real** (quanto custa 1 processamento de
  drone? 1 GB/mês? 1 análise de IA?) e com o preço que o mercado-alvo topa.
- **Faixa do público-alvo:** micro/pequena construtora (preço baixo, volume) vs. média/grande (preço
  alto, menos clientes)? Isso desloca toda a tabela.
- **Anual obrigatório em algum plano?** (ex.: Empresarial só anual, para caixa e menos churn).
- **Excedente cobrado vs. só bloqueio** nos recursos de COGS — apetite a cobrança variável.
- **Taxa de implantação** (onboarding assistido) — cobrar? quanto?
- **Drone no trial** — liberar 3 processamentos reais custa CPU; manter ou trocar por vídeo-demo?
