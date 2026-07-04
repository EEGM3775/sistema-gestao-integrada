# ERP Financeiro & Contábil (`moduloerp`) — plano do módulo carro-chefe

> **O coração do sistema.** Para o pequeno usuário é o que mais importa (contas a pagar/receber, boletos,
> nota fiscal, "quanto sobrou no fim do mês"); para o grande, é a espinha contábil-fiscal que sustenta
> auditoria e obrigações. Este documento é **a planta executiva** deste módulo: o que ele é hoje, a
> pesquisa do que um ERP completo precisa ter (pequenas **e** grandes empresas, com recorte de
> construção civil) e o **roadmap em sub-fases** para chegar lá.
>
> Decisão de escopo (07/06/2026): **ERP contábil completo** · cobrança/boleto via **Asaas (real)** ·
> incluir **financeiro por obra (centro de custo)**, **devoluções/estornos**, **folha do RH no caixa**,
> **conciliação + fluxo de caixa projetado**. Código atual: [backend/moduloerp/](../../backend/moduloerp/).
>
> ⚠️ Esta é a fase de **planejamento** — nenhum código novo foi escrito ainda. A implementação segue o
> roadmap da seção [§13](#13-roadmap-em-sub-fases-fase-d1x).

---

## 1. Visão

O `moduloerp` deixa de ser "o financeiro" e passa a ser o **núcleo de gestão financeira, contábil e
fiscal** da plataforma, organizado em camadas que escalam com o cliente:

| Perfil de cliente | O que ele usa | Profundidade |
|---|---|---|
| **Micro / pequeno** (construtor, prestador) | Contas a pagar/receber, boleto/PIX, NF de serviço, fluxo de caixa, "financeiro da obra" | Regime de **caixa**, sem contador |
| **Médio** | + centro de custo por obra, orçamento x realizado, conciliação bancária, DRE gerencial | Regime de **competência** |
| **Grande / incorporadora** | + contabilidade fiscal completa, SPED, apuração de tributos, patrimônio de afetação/RET, multi-CNPJ | Auditável, com contador/fiscal |

O mesmo módulo serve aos três
A construção civil é o domínio-âncora: orçamento de obra, medição, retenções e o regime
especial (RET) são cidadãos de primeira classe.

---

## 2. Estado atual (✅ o que já existe)

Backend maduro, **sem UI React** (é a Fase D.1 do frontend). Código: [backend/moduloerp/](../../backend/moduloerp/).

### Acesso
Entitlement **`erp_financeiro`** (camada 1) **+ papel `financeiro`** (camada 2): todo ViewSet declara
`required_module = "erp_financeiro"` e `required_role = "financeiro"` com
`[IsAuthenticated, RequireModule, RequireRole]`. Quem tem o módulo mas não o papel recebe **403**.
Isolado por tenant. Ver [../acesso-e-permissoes.md](../acesso-e-permissoes.md).

### Modelos atuais
| Modelo | Guarda |
|---|---|
| `ContaPagar` / `ContaReceber` | Título da empresa (fornecedor/cliente, empreendimento, descrição, valor, datas de emissão/vencimento/agendamento/pagamento-recebimento, **status granular** `ABERTO/PARCIAL/QUITADO/CANCELADO`, `valor_pago`/`juros`/`multa`/`desconto`, `total_devido`/`saldo_aberto` calculados); `ContaReceber` ainda liga `NotaFiscalServico`/`NotaFiscalProduto` (emissão de NF é ação do próprio recurso) |
| `CentroCusto` | Centro de custo/rateio, opcionalmente ligado a um `empreendimento` |
| `RateioContaPagar` / `RateioContaReceber` | Rateio do título por `CentroCusto` (1:N — soma livre, validada na UI) |
| `LoteRemessa` | Registro de lote de remessa bancária (status, valor_total, M2M com `ContaPagar`) — **só o registro**; geração do arquivo CNAB fica para sub-fase futura |
| `Transacao` | Entrada/saída gerada por `dar_baixa()`, ligada a `conta_pagar` **ou** `conta_receber` (CHECK garante só uma associação) e a obra/empreendimento/usuário |
| `RevisaoBaixa` | Fila de revisão do papel `financeiro`: registra (em vez de aplicar) uma baixa tentada num título já `QUITADO`/`CANCELADO` — ligada a `conta_pagar` **ou** `conta_receber` (mesmo CHECK xor); `status` `PENDENTE`/`APROVADA`/`REJEITADA`; `aprovar()` aplica a baixa represada (`forcar=True`), `rejeitar()` só arquiva |
| `NotaFiscalServico` / `NotaFiscalProduto` | NFS-e / NF-e: dados enviados à API externa + retorno (chave, número, PDF/XML, status) |
| `NotaFiscal` | NF **recebida** de fornecedor (XML/PDF) — `db_table = financeiro_notafiscal` |
| `CobrancaCliente` | Parcelas geradas ao cliente (forma de pagamento, status) |
| `Boleto` | Boleto ligado a uma `ContaReceber` **ou** `ContaPagar` (CHECK garante só uma associação) |

> O legado `Fatura` foi **removido** (07/06/2026): consolidado em `ContaPagar`/`ContaReceber` — único
> modelo de título da empresa, com `dar_baixa()` como caminho único de baixa (manual hoje, webhook
> Asaas amanhã) e `Transacao` repontada via CHECK constraint (`conta_pagar` xor `conta_receber`).

### Endpoints (`/api/erp/`)
`/contas-a-pagar/` (+ `dar-baixa`, `gerar-lote-remessa`) · `/contas-a-receber/` (+ `dar-baixa`,
`gerar-cobranca` ✅ D.1.2 — enfileira `funcoescobrancas.tasks.criar_cobranca`, gera `Boleto` via Asaas,
`emitir-nfse`, `emitir-nfe`, `emitir-lote-nfse`) · `/revisoes-baixa/` (somente leitura + `aprovar`,
`rejeitar` — fila do financeiro para baixas em títulos já quitados/cancelados) · `/centros-custo/` ·
`/lotes-remessa/` · `/transacoes/` · `/notas-fiscais-servico/` · `/notas-fiscais-produto/` ·
`/notas-fiscais/` · `/cobrancas-cliente/` · `/boletos/` · `/dashboard/` (aging + fluxo de caixa) ·
`/atualizar-status-nf/` · `/nf/<id>/consultar/`.

### Integração externa hoje
Emissão de NF chama o microsserviço Node [funcoesnf](funcoesnf.md) (NFE.io) em `localhost:3003`; em dev,
se o serviço não responde, a NF é criada em modo simulação (status `AGUARDANDO`) sem falhar.

### Dívidas técnicas conhecidas
- `unique=True` ainda **global** (ex.: `NotaFiscal.numero_nota`, `chave_acesso`) → vira `unique` por
  tenant na Fase 8 (risco de vazamento/colisão entre empresas).
- Mascaramento de campos sensíveis por papel é pendência (Fase 9).
- ~~`dar_baixa()` não impede baixa repetida em título já `QUITADO`/`CANCELADO`~~ **Corrigido
  (07/06/2026):** descoberto na validação do golden path de D.1.1 — chamar a ação novamente aceitava
  o pagamento, inflava `valor_pago` além de `total_devido` e deixava `saldo_aberto` negativo, além de
  duplicar `Transacao`. Decisão do usuário: em vez de bloquear ou aplicar, **detectar e encaminhar
  para revisão do papel `financeiro`** — `dar_baixa()` agora levanta `BaixaRequerRevisao` e cria um
  registro `RevisaoBaixa` (`PENDENTE`) com os dados da tentativa em vez de aplicar; a fila
  (`/api/erp/revisoes-baixa/`, ações `aprovar`/`rejeitar`) deixa o financeiro decidir caso a caso —
  aprovar aplica a baixa represada via `forcar=True` (bypassa o guard), rejeitar só arquiva.
  **Confirmado em produção cruzada (08/06/2026):** o webhook do Asaas ([D.1.2](funcoescobrancas.md))
  reaproveita o mesmo `dar_baixa(origem='asaas')` — pagamento duplicado em título `QUITADO` cai na
  mesma fila `RevisaoBaixa` em vez de processar sem moderação, validado e2e. Ver
  `RevisaoBaixa`/`BaixaRequerRevisao` em `backend/moduloerp/models.py`.

---

## 3. Pesquisa — anatomia de um ERP completo

Levantamento dos domínios que um ERP precisa cobrir para atender de micro a grande empresa, com o
recorte fiscal brasileiro e de construção civil. (Fontes ao final, [§16](#16-fontes).)

### 3.1 Mapa de domínios

| # | Domínio | Cobre | SGI hoje |
|---|---|---|---|
| A | **Financeiro / Tesouraria** | Contas a pagar/receber, caixa e bancos, conciliação, boleto/PIX/cartão, fluxo de caixa realizado e projetado | 🟡 parcial |
| B | **Contábil** | Plano de contas, partidas dobradas, razão/diário/balancete, DRE, balanço, encerramento | ❌ |
| C | **Fiscal / Tributário** | NF-e/NFS-e/NFC-e/CT-e, SPED (Fiscal/Contribuições/ECD/ECF), apuração de tributos, regimes, **Reforma Tributária (IBS/CBS/IS)** | 🟡 só emissão NF |
| D | **Faturamento / Billing** | Pedidos, contratos recorrentes, régua de cobrança, comissões | 🟡 `CobrancaCliente` |
| E | **Compras / Suprimentos** | Requisição → cotação → pedido → recebimento → NF entrada → contas a pagar | ❌ (NF entrada existe) |
| F | **Estoque / Almoxarifado** | Itens, saldos, movimentações, custo médio, requisição de obra | ❌ |
| G | **Patrimônio / Ativos** | Imobilizado, depreciação, equipamentos de obra | ❌ |
| H | **Custos / Controladoria** | Centro de custo, rateio, orçamento x realizado, margem por obra | ❌ |
| I | **Folha / RH** | Folha, encargos, provisões — já é o módulo [rh](rh.md); aqui entra a **consolidação no caixa** | 🟡 módulo rh existe |
| J | **Construção civil** | Orçamento de obra (SINAPI/curva ABC), medição, RET/patrimônio de afetação, retenções, incorporação/distrato | ❌ |
| K | **BI / Relatórios** | Dashboards, DRE gerencial, indicadores, exportações contábeis | 🟡 `/dashboard/` |

### 3.2 (A) Financeiro / Tesouraria — *o que o pequeno usa todo dia*
- **Contas a pagar (AP):** título, fornecedor, vencimento, rateio por centro de custo/obra, anexo de NF,
  agendamento, baixa parcial, juros/multa/desconto, pagamento em lote, remessa bancária.
- **Contas a receber (AR):** título, cliente, parcelas, **boleto/PIX/cartão**, baixa automática por
  webhook, régua de cobrança (lembrete/cobrança/negativação), inadimplência (aging).
- **Caixa e bancos:** múltiplas contas/carteiras, transferências entre contas, saldo consolidado.
- **Conciliação bancária:** importar extrato (OFX/CNAB/Open Finance) e casar com títulos; conciliação
  do Asaas via webhook.
- **Fluxo de caixa:** **realizado** (o que já entrou/saiu) e **projetado** (a partir de AP/AR futuros),
  com cenários e DRE de caixa.
- **Meios de pagamento:** boleto, PIX (estático/dinâmico), cartão, TED/DOC, dinheiro, cheque.

### 3.3 (B) Contábil — *o que o grande exige*
- **Plano de contas** (referencial + gerencial), centros de custo, partidas dobradas (débito/crédito).
- **Lançamentos contábeis** automáticos a partir dos eventos financeiros (motor de
  contabilização/"de-para" por evento) e manuais.
- **Livros:** Diário, Razão, Balancete; **DRE**, **Balanço Patrimonial**, fluxo de caixa (DFC).
- **Fechamento de período** (bloqueio de competência), conciliação contábil, rateios.
- Regime de **competência** vs **caixa** (o pequeno fica no caixa; o grande na competência).

### 3.4 (C) Fiscal / Tributário (Brasil)
- **Documentos fiscais eletrônicos:** NF-e (produto), NFS-e (serviço), NFC-e (consumidor), CT-e/MDF-e
  (transporte) — emissão, cancelamento, carta de correção, inutilização, manifestação do destinatário.
- **SPED:** EFD ICMS/IPI (Fiscal), EFD Contribuições (PIS/COFINS), ECD (contábil), ECF (IRPJ/CSLL),
  EFD-Reinf (retenções) + DCTFWeb.
- **Apuração de tributos:** ICMS, ISS, PIS, COFINS, IPI, IRPJ, CSLL, INSS; por **regime** (Simples
  Nacional, Lucro Presumido, Lucro Real).
- **Retenções:** IR, INSS, ISS, PIS/COFINS/CSLL na fonte (crítico em serviços e construção).
- 🆕 **Reforma Tributária (LC 214/2025 — transição 2026→2033):**
  - **CBS** (federal) substitui PIS/COFINS/IPI; **IBS** (estadual+municipal) substitui ICMS/ISS;
    **Imposto Seletivo (IS)** sobre itens nocivos. Modelo **IVA dual**.
  - **2026 = ano informativo/teste:** documentos fiscais já devem trazer os **campos de IBS/CBS**
    (CBS 0,9% / IBS 0,1% simbólicos, sem recolhimento se a obrigação acessória for cumprida).
  - **2027:** CBS cheia + IS entram em vigor; ICMS/ISS vão sendo reduzidos até 2033.
  - **Impacto no ERP:** cadastro de produto/serviço precisa de **tabelas auxiliares CBS/IBS** e o motor
    fiscal precisa de **apuração simultânea** (PIS/COFINS/ICMS/ISS para pagar + CBS/IBS para informar).
    → entra como sub-fase própria do roadmap fiscal.

### 3.5 (D) Faturamento / Billing
Pedido/proposta → contrato → faturamento (avulso ou **recorrente/assinatura**) → emissão de NF + cobrança.
Régua de cobrança, comissões de vendedor, vínculo a `clientes.ContratoCliente` (que já existe).

### 3.6 (E) Compras / Suprimentos
Fluxo **requisição → cotação (multi-fornecedor) → pedido de compra → recebimento → NF de entrada →
conta a pagar**. Aprovação por alçada. Vínculo a obra/centro de custo. Hoje só existe a `NotaFiscal`
de entrada — falta o ciclo completo.

### 3.7 (F) Estoque / Almoxarifado
Cadastro de itens/insumos, saldos por depósito/obra, movimentações (entrada/saída/transferência),
**custo médio**, requisição de material por obra, inventário. Integra com Compras e com o orçamento de obra.

### 3.8 (G) Patrimônio / Ativos
Imobilizado, **depreciação**, equipamentos de obra (locação x próprio), manutenção. Liga em Contábil
(depreciação) e em Custos (alocação à obra).

### 3.9 (H) Custos / Controladoria
**Centro de custo** (a obra é o centro de custo natural), rateio de despesas indiretas, **orçamento x
realizado**, margem/resultado por obra e por empreendimento, ponto de equilíbrio. É a camada que
transforma lançamento em **gestão**.

### 3.10 (I) Folha / RH — consolidação
A folha vive no módulo [rh](rh.md) (papéis `rh_financeiro`/`rh_medico`). O ERP **não recalcula folha**;
ele **consolida** os pagamentos de funcionários (salários, encargos, provisões de 13º/férias/FGTS/INSS)
no **fluxo de caixa** e na contabilidade, rateando por obra. eSocial/DCTFWeb ficam na fronteira RH↔fiscal.

### 3.11 (J) Construção civil — diferenciais
- **Orçamento de obra:** composições de custo (insumo + serviço), base **SINAPI/TCPO**, **curva ABC**
  (classifica itens por impacto no custo: poucos itens "A" concentram a maior parte do valor).
- **Medição / avanço físico-financeiro:** boletim de medição por etapa, liberação de pagamento por
  medição, retenção contratual (caução), aditivos.
- **Regime Especial Tributário (RET) + patrimônio de afetação:** recolhimento unificado de **4%** da
  receita (IRPJ+CSLL+PIS+COFINS) por empreendimento afetado — exige segregar receita/custo **por
  empreendimento** (já temos `Empreendimento`).
- **Retenções da construção:** **INSS 11%** sobre cessão de mão de obra/empreitada (elide
  responsabilidade solidária), **ISS** no local da obra, retenção de IR.
- **Incorporação imobiliária:** controle de unidades, comissões, **distrato** (Lei 13.786/2018),
  correção de parcelas (INCC), comissão de corretagem.

### 3.12 (K) BI / Relatórios
Dashboards por papel, DRE gerencial, fluxo de caixa, aging de inadimplência, margem por obra,
exportação para o contador (XML/SPED), agendamento de relatórios.

---

## 4. Gap analysis — SGI hoje × alvo

| Capacidade | Hoje | Alvo | Lacuna |
|---|---|---|---|
| AP / AR básico | ✅ | ✅ | baixa parcial, juros/multa, rateio, lote |
| Boleto/PIX/cartão real | 🟡 abstração | ✅ Asaas | integração + webhook de baixa |
| NF emissão (serviço/produto) | ✅ NFE.io | ✅ | cancelamento, CC-e, NFC-e |
| NF entrada (fornecedor) | ✅ modelo | ✅ | ciclo de compras |
| Fluxo de caixa | 🟡 realizado | ✅ + projetado | projeção + cenários |
| Conciliação bancária | ❌ | ✅ | OFX/Open Finance + webhook Asaas |
| Centro de custo / financeiro por obra | ❌ | ✅ | model + rateio + relatórios |
| Devoluções / estornos | ❌ | ✅ | model + refund Asaas + NF devolução |
| Folha do RH no caixa | ❌ | ✅ | consolidação rh→erp |
| Plano de contas / contábil | ❌ | ✅ | módulo contábil novo |
| SPED / apuração de tributos | ❌ | ✅ | motor fiscal |
| Reforma Tributária (IBS/CBS) | ❌ | ✅ | campos + apuração simultânea |
| Compras / Estoque / Patrimônio | ❌ | ✅ | módulos novos |
| Orçamento de obra / medição / RET | ❌ | ✅ | módulo construção |

---

## 5. Frontend do ERP — navegação e arquitetura

> O modelo de frontend atual do SGv02 (ver [../frontend.md](../frontend.md)) foi desenhado para **CRUD
> de cadastro** (dezenas de linhas, fetch manual, tabela client-side). O ERP é outra ordem de
> grandeza — milhares de lançamentos, baixa por webhook, dashboards, formulários com rateio e dinheiro.
> Esta seção define o **modelo de frontend específico do ERP**, que estende (não substitui) o do projeto.

### 5.1 Camadas de seleção (navegação / UX)

Atende o pedido: *"camadas de seleção para ver a parte financeira da obra, dos pagamentos e devoluções
de clientes, fornecedores, notas fiscais, funcionários"*. O ERP abre num **hub financeiro** e o usuário
**filtra/perfura** por entidade — o mesmo dado visto por ângulos diferentes:

```
/app/erp  (Dashboard financeiro — KPIs do tenant)
│
├── Por OBRA / EMPREENDIMENTO   → DRE da obra, orçado x realizado, AP/AR/medições da obra
├── Por CLIENTE                 → a receber, cobranças, boletos, devoluções, NF emitidas, contratos
├── Por FORNECEDOR              → a pagar, NF de entrada, devoluções, retenções
├── Por FUNCIONÁRIO (via RH)    → folha consolidada no caixa (somente papel autorizado)
├── NOTAS FISCAIS              → emitidas / recebidas / canceladas (emitir · cancelar · CC-e)
├── BOLETOS / COBRANÇAS        → emitir · cancelar · ver pagos/vencidos (baixa automática)
├── CAIXA & BANCOS             → contas, conciliação, transferências
├── FLUXO DE CAIXA             → realizado + projetado
└── CONTÁBIL / FISCAL          → plano de contas, DRE, apuração, SPED  (papel contador/fiscal)
```

**Padrão de filtro unificado:** todo listão financeiro aceita os mesmos filtros (período,
obra/empreendimento, cliente, fornecedor, status, centro de custo) — o "seletor de camada" é a barra de
filtros, não telas duplicadas. Drill-down: card de KPI → lista filtrada → detalhe do título → ações.
O estado do filtro vive na **URL** (`?obra=12&periodo=2026-06&status=vencido`) → deep-link, voltar/avançar
do navegador e compartilhamento funcionam.

### 5.2 Por que o modelo atual é simples demais

| Limite do modelo atual | Por que quebra no ERP |
|---|---|
| `services/*.ts` = funções axios cruas, sem cache | A mesma `ContaPagar`/`ContaReceber` é lida no dashboard, na obra e no cliente → N requisições duplicadas e dados divergentes entre telas |
| `hooks` com `useState`+`useEffect` (fetch on mount) | Sem **invalidação reativa**: baixa de boleto via webhook / cancelamento de NF não reflete sem refresh manual |
| Tabela **client-side** (carrega tudo e filtra no browser) | Milhares de lançamentos → travamento; precisa paginação/ordenação/filtro **server-side** + export |
| Formulário simples (campos planos) | Lançamento com **rateio** em N centros de custo, **parcelamento**, composição de custo = field arrays dinâmicos |
| Sem tratamento de moeda | `float` corrompe centavos; precisa entrada/exibição BRL com decimal seguro |
| Sem gráficos | DRE, fluxo de caixa, curva ABC, aging exigem biblioteca de charts |
| Só `hasModule` | ERP precisa de papéis finos (contador/fiscal/tesouraria) e **mascaramento de campo** |
| Bundle único | O ERP é o maior módulo → precisa **code-splitting** por sub-módulo |

### 5.3 Stack adicional (estende o do projeto)

| Camada | Biblioteca | Papel |
|---|---|---|
| **Estado de servidor** | **TanStack Query (React Query)** | cache, dedupe, refetch em background, **invalidação por chave**, optimistic update. O upgrade central. |
| **Data-grid** | **TanStack Table** (headless) + virtualização | tabela sobre dados server-driven: ordenação, colunas, paginação, seleção em massa |
| **Formulários** | **react-hook-form + zod** | forms complexos, **field arrays** (rateio/parcelas), validação por schema + assíncrona |
| **Gráficos** | **Recharts** (ou Tremor) | dashboards financeiros, DRE cascata, fluxo de caixa, curva ABC |
| **Dinheiro** | helpers próprios (centavos inteiros) + `Intl.NumberFormat('pt-BR')` | `MoneyInput`/`MoneyDisplay`; nunca `float` |
| **Tempo real** | SSE ou polling do React Query | refletir **baixa automática** do webhook Asaas |
| **PDF/XML** | viewer embutido + download autenticado (já existe `useFileUpload`) | documentos fiscais |

> Tudo compatível com a stack atual (React 19 · Vite · TS · Tailwind 4 · shadcn/ui). Nada de framework
> novo de runtime — são libs headless que convivem com o que já existe.

### 5.4 Camada de dados (o coração da mudança)

Substituir o par "service cru + hook manual" por **query keys + hooks de query/mutation**:

```
modules/erp/api/
├── erpClient.ts          ← axios já autenticado (reusa apiClient)
├── queryKeys.ts          ← fábrica de chaves: erpKeys.contasAPagar(filtros), erpKeys.dashboard.all...
└── endpoints/            ← contasAPagar.ts, contasAReceber.ts, boletos.ts, notas.ts, caixa.ts, ...
modules/erp/hooks/
├── useContasAPagar.ts    ← useQuery(erpKeys.contasAPagar(f), ...) + useDarBaixaContaAPagar (mutation)
├── useBaixarBoleto.ts    ← useMutation → invalida erpKeys.boletos + caixa + dashboard
└── ...
```

- **Invalidação em cascata:** uma mutação (pagar, cancelar, emitir NF) invalida as chaves afetadas →
  todas as telas que mostram aquele dado atualizam sozinhas. Resolve o problema do webhook/baixa.
- **Optimistic update** nas ações frequentes (baixa manual, marcar pago).
- **Prefetch** no hover do card de KPI → o drill-down já chega com dados quentes.

### 5.5 Arquétipos de página (layouts reutilizáveis)

Em vez de "List + Detail" genéricos, o ERP padroniza **6 arquétipos** reaproveitados por todos os
sub-módulos:

1. **Dashboard** — grade de `KpiCard` + charts (fluxo de caixa, aging, DRE resumida).
2. **Workspace de lista financeira** — `FilterBar` + `FinanceDataTable` (server-side) + ações em massa
   (pagar/emitir/cancelar em lote) + export (CSV/Excel/PDF) + `Sheet` de detalhe lateral.
3. **Detalhe de documento** — header + `StatusTimeline` + abas + ações + viewer PDF/XML (NF, boleto, título).
4. **Formulário de lançamento** — RHF+zod com `RateioField` (centro de custo), parcelamento, `MoneyInput`.
5. **Conciliação** — split view: extrato bancário ↔ títulos, casar/desfazer.
6. **Drill-down por entidade** — o arquétipo 2 com um filtro **fixado** (obra/cliente/fornecedor).

### 5.6 Estrutura de diretórios do módulo ERP

Mais rica que os módulos simples (`clientes/`, `rh/`), por causa do volume e das sub-áreas:

**Construído (D.1.0/D.1.1/D.1.2)** — base sólida para os próximos sub-módulos reaproveitarem:

```
modules/erp/
├── routes.tsx                    ← sub-rotas lazy/Suspense, irmãs de /app/erp (não aninhadas)
├── types.ts                      ← ContaPagar/ContaReceber/Boleto/EventoWebhookAsaas/Rateio/...
├── api/        erpClient · queryKeys (erpKeys.*) · endpoints/ (contasAPagar, contasAReceber,
│               centrosCusto, lotesRemessa, boletos, dashboard)
├── hooks/      useContasAPagar · useContasAReceber (useQuery + useCreate/useUpdate/useDarBaixa) ·
│               useCentrosCusto · useLotesRemessa · useEntityOptions · useErpDashboard ·
│               useBoletos (useBoletos · useGerarCobrancaContaAReceber · useEventosWebhookAsaas)
├── components/
│   ├── shared/   FilterBar · FinanceDataTable (TanStack Table server-side) · Sheet (slide-over) ·
│   │             MoneyInput · MoneyDisplay · KpiCard · StatusContaBadge (+ statusConta.ts) ·
│   │             StatusBoletoBadge (+ statusBoleto.ts)
│   ├── forms/    ContaPagarForm · ContaReceberForm · BaixaForm · RateioField · FormField ·
│   │             schemas.ts (zod) · formStyles.ts          ← RHF + zod, 1º uso no projeto
│   └── charts/   FluxoCaixaChart · AgingChart (Recharts)
└── pages/
    ├── ErpDashboardPage.tsx      ← hub /app/erp: KPIs + gráficos + cards de navegação aos workspaces
    ├── ContasAPagarPage.tsx      ← workspace: FilterBar+FinanceDataTable+Sheet (criar/editar/baixa/ver)
    ├── ContasAReceberPage.tsx    ← idem, espelhado para cliente/NF — + botão "Gerar cobrança (Asaas)"
    ├── BoletosListPage.tsx       ← D.1.2 ✅: workspace só-leitura das cobranças emitidas via Asaas
    └── BoletoDetailPage.tsx      ← D.1.2 ✅: dados do gateway + timeline de eventos do webhook
```

> Telas dedicadas de boletos (`/app/erp/boletos`, `/app/erp/boletos/:id`) — decisão do usuário de
> "telas dedicadas", não Sheet — ver [funcoescobrancas.md "UI dedicada"](funcoescobrancas.md#ui-dedicada--telas-de-boletos-entregue-08062026-)
> para o detalhe completo da entrega (08/06/2026).

**Planejado (sub-fases seguintes)** — entram conforme o roadmap em [§13](#13-roadmap-em-sub-fases-fase-d1x):

```
    ├── notas/    (NotasListPage [emitidas|recebidas|canceladas]) — D.1.3
    ├── obra/     (ObraFinanceiroPage — DRE da obra)             — D.1.4
    ├── caixa/    (CaixaPage, ConciliacaoPage)                   — D.1.6
    ├── fluxo/    (FluxoCaixaPage — realizado + projetado)       — D.1.7
    └── contabil/ · fiscal/   (papéis contador/fiscal)           — D.2/D.3
```

> `ErpFilterContext`/`ParcelasField`/`StatusTimeline`/`DocumentoFiscalViewer` seguem como arquétipos
> previstos em [§5.5](#55-arquétipos-de-página-layouts-reutilizáveis), a construir quando o
> sub-módulo que os usa entrar (notas/parcelamento). `boletos/` (D.1.2) já entrou e **não** precisou de
> arquétipo novo — reaproveitou "Workspace de lista financeira" + "Detalhe de documento" como tela
> dedicada (somente leitura).

### 5.7 Permissões e mascaramento na UI

- Guards de UI por papel: `useHasRole('contador')`, `<RequireRole role="financeiro">` escondendo
  ações/telas (espelha o backend `RequireRole`, ver [§11](#11-acesso--rbac-e-mascaramento)).
- `<Sensitive role="rh_financeiro">` redige valores (folha individual, margens) quando o papel não
  autoriza — alinhado ao mascaramento de campo da **Fase 9** (a UI nunca recebe o dado, não só o esconde).
- Sub-navegação da sidebar varia por papel: tesouraria vê Caixa/Conciliação; contador vê Contábil; etc.

### 5.8 Performance

Lazy-load por sub-módulo (`React.lazy` + `Suspense`), virtualização das tabelas grandes, `Skeleton` em
todo carregamento, suspense boundaries por área. O bundle do ERP nunca entra no carregamento inicial do app.

---

## 6. Boletos & cobrança — integração Asaas

> **✅ MVP entregue 08/06/2026** (D.1.2, backend + UI): emitir cobrança + baixa automática por webhook,
> golden path validado e2e (mock e ponta a ponta com o sandbox real via ngrok). Detalhe completo,
> validação e o que ficou de fora (slice 2): [funcoescobrancas.md](funcoescobrancas.md#fluxo-entregue-no-mvp).
> UI dedicada entregue (`BoletosListPage`/`BoletoDetailPage` + botão "Gerar cobrança" em
> `ContasAReceberPage` — ver [§5.6](#56-estrutura-de-diretórios-do-módulo-erp) e
> [funcoescobrancas.md "UI dedicada"](funcoescobrancas.md#ui-dedicada--telas-de-boletos-entregue-08062026-)).

Provedor escolhido: **Asaas** (boleto + PIX + cartão, com webhook de baixa). Substitui a abstração
genérica atual (`Boleto.gateway_id/url_pdf/linha_digitavel` já preveem isso — e que agora estão sendo
preenchidas de fato pelo `funcoescobrancas`).

### Capacidades a usar
| Recurso Asaas | Uso no SGI |
|---|---|
| `customers` | espelhar `clientes.Cliente` no Asaas (criar sob demanda, guardar `asaas_customer_id`) |
| `payments` (billingType BOLETO/PIX/CREDIT_CARD/UNDEFINED) | gerar a cobrança a partir de `ContaReceber`/`CobrancaCliente` |
| `installments` | parcelamento (parcelas de contrato) |
| `subscriptions` | cobrança **recorrente** (mensalidades/contratos) |
| webhook `PAYMENT_RECEIVED/CONFIRMED/OVERDUE/REFUNDED` | **baixa automática** ("quem já pagou"), inadimplência |
| `payments/{id}/refund` | **estorno/devolução** ao cliente |
| `DELETE payments/{id}` | **cancelar boleto** não pago |
| `identificationField` / `pixQrCode` | linha digitável e QR PIX |
| `transfers` | saques/transferências (tesouraria) |
| `invoices` | NFS-e via Asaas (usado pelo [funcoesnf](funcoesnf.md); NFE.io vira alternativo/legado) |

### Onde vive a integração: `funcoescobrancas` (Django app Python)
A cobrança fala com o Asaas por um **Django app Python** novo, **`funcoescobrancas`** — cliente HTTP +
**Celery tasks** + view de webhook, tudo in-process no Django. **Não** é microsserviço Node nem Java:
segue o **AD-8** ([arquitetura.md §6](../arquitetura.md#6-estratégia-de-stack-tecnológica)) — *"nova
integração externa → Celery task (Python)"*, *"novo webhook → Django view + Celery"*, e Java fica
restrito ao drone ("para o ERP, I/O-bound, essa limitação não existe"). O prefixo `funcoes*` não é de
Node: o [funcoesia](funcoesia.md) já é Python. A **lógica e os models continuam no
[moduloerp](moduloerp.md)** (`Boleto`, `ContaReceber`, `CobrancaCliente`); o app só adapta o protocolo
Asaas e recebe o webhook. O [funcoesnf](funcoesnf.md) também passa a usar o Asaas (`invoices`) para NFS-e
— **um só gateway** para nota e cobrança (reaproveita o mesmo `client.py`). Detalhe:
[funcoescobrancas.md](funcoescobrancas.md).

### Fluxo
1. ✅ Operador aciona `gerar-cobranca` em `ContaReceber` (action no `ContaReceberViewSet`).
2. ✅ O `moduloerp` enfileira a Celery task `criar_cobranca` de `funcoescobrancas`, que garante o
   `customer` no Asaas (espelha `Cliente.id_cliente_gateway`), cria o `payment` e grava `gateway_id`,
   `url_pdf`, `linha_digitavel` no `Boleto` (status `EMITIDO`). Idempotente.
3. ✅ Cliente paga → Asaas chama a **view de webhook** (`/api/erp/cobrancas/webhook/asaas/`) →
   `dar_baixa(origem='asaas')` dá a **baixa** (`Boleto`→`PAGO`, `ContaReceber`→`QUITADO`, lança
   `Transacao`); pagamento duplicado em título quitado cai no guard `RevisaoBaixa`.
4. ❌ **Fora do MVP (slice 2):** cancelar (`DELETE` no Asaas + `Boleto`→`CANCELADO`), estornar
   (`refund` + `Devolucao`), QR PIX, parcelamento — adiados por decisão do usuário para focar no golden
   path emitir+baixa primeiro.

### Decisões de implementação
- **Sandbox agora** (`https://api-sandbox.asaas.com/v3`); migra para o real
  (`https://api.asaas.com/v3`) trocando `ASAAS_BASE_URL` + `ASAAS_API_KEY`.
- **Credencial — decisão do MVP (07/06/2026):** **chave global** em `.env`, compartilhada por todos os
  tenants (mais simples para validar o fluxo agora). Migrar para credencial **por tenant**
  (`IntegracaoAsaas`, cada empresa com a própria conta Asaas, segredo cifrado) é pendência operacional
  da Fase 5 (gestão de segredos) — ver [§15](#15-questões-em-aberto-decidir-antes-da-sub-fase-relevante).
- Webhook **idempotente** (`EventoWebhookAsaas` trata `evento_id`, Asaas reenvia eventos não
  confirmados) + validação de token (`asaas-access-token` contra `ASAAS_WEBHOOK_TOKEN`) — **✅
  implementado e validado** (e2e com payloads simulados, 08/06/2026).
- Padrão: a integração é o Django app Python `funcoescobrancas` (Celery + webhook); a regra de negócio
  (inclusive a baixa) fica no `moduloerp`, reaproveitando o caminho único `dar_baixa()` do D.1.1 — o
  webhook não tem lógica de baixa própria, só resolve o `Boleto` e delega.

---

## 7. Notas fiscais — emitir · cancelar · ver

Cobre o pedido de *"ver notas fiscais, emitir e cancelar"* e *"ver quem já pagou"*.

- **Emitidas (saída):** `NotaFiscalServico` (NFS-e) e `NotaFiscalProduto` (NF-e) via NFE.io (hoje) —
  adicionar **cancelamento**, **carta de correção (CC-e)**, e avaliar **NFC-e** (consumidor) e Asaas
  como provedor alternativo de NFS-e.
- **Recebidas (entrada):** `NotaFiscal` de fornecedor (XML/PDF) → origina `ContaPagar`; futuro:
  **manifestação do destinatário** e importação automática por XML/chave.
- **Tela de NF:** abas Emitidas / Recebidas / Canceladas; filtros (período, cliente/fornecedor, status,
  obra); ações emitir (individual e **lote**, já existe `emitir-lote-nfse`), cancelar, baixar PDF/XML,
  consultar status (`/nf/<id>/consultar/`).
- **"Quem pagou":** cruzar NF emitida → `ContaReceber` → `Boleto`/`Transacao` (status de
  pagamento vem do webhook Asaas).

---

## 8. Devoluções / estornos

Modelo novo `Devolucao` (ou `notas de crédito/débito`) cobrindo os dois lados:
- **De cliente** (a empresa devolve): estorno de cobrança (refund Asaas), NF de devolução, baixa
  negativa no caixa, eventual nota de crédito.
- **De fornecedor** (devolução de compra): NF de devolução de entrada, ajuste de `ContaPagar`/estoque.
- Campos: origem (cliente/fornecedor), documento origem (NF/cobrança), valor, motivo, data, vínculo à
  `Transacao` de estorno e à NF de devolução. Reflete no fluxo de caixa e na apuração fiscal.

---

## 9. Consolidação — obra, RH e fluxo projetado

- **Financeiro por obra (centro de custo):** introduzir `CentroCusto` (e/ou usar `Obra` como CC),
  tornar **rateável** todo lançamento (AP/AR/Transacao) por obra/empreendimento. Saída: **DRE por obra**,
  **orçado x realizado**, margem.
- **Folha do RH no caixa:** job/serviço que lê os pagamentos de folha do módulo [rh](rh.md) e gera
  `ContaPagar`/`Transacao` de saída, rateando por obra (mão de obra direta). Respeita o mascaramento de
  PII por papel (Fase 9) — valores individuais só para papel autorizado.
- **Conciliação + fluxo projetado:** importar extrato (OFX/Open Finance) e webhook Asaas para conciliar
  o **realizado**; projetar caixa a partir de AP/AR futuros + medições previstas.

---

## 10. Modelo de dados proposto (alto nível)

> Tudo herda `TenantScopedModel`; `tenant` será **NOT NULL** e `unique` **por tenant** (Fase 8).

| Área | Models novos (propostos) | Observação |
|---|---|---|
| Tesouraria | `ContaBancaria`, `MovimentoBancario`, `Conciliacao` | múltiplas contas, extrato, casamento |
| Centro de custo | `CentroCusto`, `RateioLancamento` | obra como CC natural |
| Cobrança | reaproveitar `Boleto`/`CobrancaCliente` + `IntegracaoAsaas` (credencial/eventos), `WebhookEvento` | idempotência |
| Devolução | `Devolucao`, `NotaCredito` | cliente e fornecedor |
| Compras | `RequisicaoCompra`, `Cotacao`, `PedidoCompra`, `Recebimento` | ciclo → AP |
| Estoque | `Item`, `Deposito`, `SaldoEstoque`, `MovimentoEstoque` | custo médio |
| Patrimônio | `AtivoImobilizado`, `Depreciacao` | liga contábil |
| Contábil | `PlanoContas`, `LancamentoContabil`, `Partida`, `PeriodoContabil`, `RegraContabilizacao` | partidas dobradas |
| Fiscal | `RegimeTributario`, `ApuracaoImposto`, `Retencao`, `ConfigFiscalProduto` (CBS/IBS) | + geração SPED |
| Construção | `OrcamentoObra`, `ComposicaoCusto`, `Insumo`, `Medicao`, `Aditivo` | SINAPI/curva ABC |
| Incorporação | `UnidadeImobiliaria`, `Distrato`, `ReajusteParcela` | INCC, Lei 13.786 |

Os models atuais (`Transacao`, `ContaPagar/Receber`, `NotaFiscal*`, `Boleto`, `CobrancaCliente`,
`CentroCusto`/`Rateio*`, `RevisaoBaixa`) permanecem e ganham os hooks de contabilização.

---

## 11. Acesso / RBAC e mascaramento

Camada 1 (entitlement) `erp_financeiro` já existe. Refinar a camada 2 (papéis) — segregação de função é
requisito de controle interno e LGPD:

| Papel (proposto) | Vê / faz |
|---|---|
| `financeiro` (existe) | AP/AR, boletos, caixa, cobrança |
| `tesouraria` | bancos, conciliação, pagamentos/transferências |
| `contador` | plano de contas, lançamentos, DRE, fechamento, SPED |
| `fiscal` | NF, apuração de tributos, retenções, obrigações |
| `gestor_obra` | financeiro **da sua obra** (centro de custo restrito) |
| `auditor` | leitura ampla, sem escrita |

**Mascaramento (Fase 9):** valores de folha por funcionário, dados bancários e margens sensíveis
redigidos para quem não tem o papel — na serialização, não só bloqueando o endpoint. Trilha de
auditoria (`AuditLog`) em operações financeiras/fiscais.

---

## 12. Dependências de fundação (travam dados reais)

Antes de operar com **dinheiro real**, o módulo depende das fases de fundação (ver
[../roadmap.md](../roadmap.md)):

- **Fase 8** — Postgres real + `tenant` NOT NULL + `unique` **por tenant** + RLS. Crítico: hoje
  `NotaFiscal.numero_nota`/`chave_acesso` e afins são `unique` globais → risco de colisão/vazamento
  entre empresas. `CheckConstraint` (ex.: `Boleto`) e `ATOMIC_REQUESTS` só são reais no Postgres.
- **Fase 9** — RBAC de campo (mascaramento de PII), `AuditLog`, retenção/LGPD.
- **Fase 5 (operacional)** — gestão de segredos (chaves Asaas/NFE.io por tenant em Vault/Secrets
  Manager), observabilidade e DR.

> **Regra:** funcionalidade pode ser construída em dev sobre SQLite, mas o **cutover com dados reais**
> de cliente exige Fases 8 e 9 fechadas.

---

## 13. Roadmap em sub-fases (Fase D.1.x)

> Frontend = Fase **D.1** do [frontend.md](../frontend.md); backend complementar entra junto de cada
> sub-fase. Ordem por **valor para o pequeno usuário primeiro**, fiscal/contábil pesado depois.

| Sub-fase | Entrega | Backend | Frontend | DoD |
|---|---|---|---|---|
| **D.1.0** ✅ 07/06/2026 | **Fundação UI** do ERP ([§5](#5-frontend-do-erp--navegação-e-arquitetura)) | `_scope` (tenant) em todos os ViewSets financeiros; `ErpPageNumberPagination` (25/pág.) + `FilterSet`s + `SearchFilter`/`OrderingFilter` | camada de dados (`erpKeys` + `useErpDashboard` sobre TanStack Query), `FilterBar`+`FinanceDataTable` (TanStack Table, server-side, URL-friendly), `MoneyInput`/`MoneyDisplay` (centavos inteiros), `KpiCard` + `FluxoCaixaChart`/`AgingChart` (Recharts), `routes.tsx` com `lazy`/`Suspense` (code-splitting); shell `/app/erp` = `ErpDashboardPage` (hub com KPIs + gráficos) | ✅ dashboard abre em `/app/erp` com KPIs e gráficos reais do `/dashboard/` (aging a receber/pagar, fluxo de caixa mensal); cadeia de invalidação pronta para as mutações de D.1.1 |
| **D.1.1** ✅ 07/06/2026 | **Contas a pagar/receber** | `Fatura` **consolidada** em `ContaPagar`/`ContaReceber` (status granular, `valor_pago`/juros/multa/desconto, `data_emissao`/`agendamento`); `CentroCusto` + `RateioContaPagar/Receber`; `LoteRemessa`; `Transacao` repontada (CHECK `conta_pagar` xor `conta_receber`); `dar_baixa()` único caminho de baixa (gera `Transacao`, preparado para webhook Asaas D.1.2); `dar-baixa`/`gerar-lote-remessa` (AP) e `dar-baixa`/`emitir-nfse`/`emitir-nfe`/`emitir-lote-nfse` (AR) como actions; `ERPDashboardView` recalculado direto de AP/AR | `Sheet` (slide-over, 1º uso no projeto); `ContaPagarForm`/`ContaReceberForm`/`BaixaForm` (RHF+zod, 1º uso, com `RateioField` em field array); `ContasAPagarPage`/`ContasAReceberPage` (workspace: `FilterBar`+`FinanceDataTable`+`Sheet` p/ criar/editar/ver/baixa); cards de navegação no hub + breadcrumb de volta | ✅ CRUD completo, baixa parcial→total, rateio por centro de custo, lote de remessa e aging do dashboard validados via API/gateway (golden path, 07/06/2026; dados de teste limpos). **Achado corrigido no mesmo dia:** `dar_baixa()` aceitava baixa repetida em título já `QUITADO`/`CANCELADO` — agora detecta e encaminha para revisão do financeiro via `RevisaoBaixa`/`BaixaRequerRevisao` + fila `/api/erp/revisoes-baixa/` (`aprovar`/`rejeitar`); ver "Dívidas técnicas" |
| **D.1.2** ✅ MVP 08/06/2026 (backend) | **Boletos & Asaas** | Django app Python [funcoescobrancas](funcoescobrancas.md) — `AsaasClient` + `services`/`tasks` Celery + `WebhookAsaasView` idempotente + `EventoWebhookAsaas`; action `gerar-cobranca` em `ContaReceber`; baixa automática via `dar_baixa(origem='asaas')` (reaproveita o guard `RevisaoBaixa` do D.1.1) | ❌ telas de boletos (`BoletosListPage`/`BoletoDetailPage`) ainda não construídas | ✅ sandbox (mockado): emite, gera customer/payment, baixa automática por webhook, idempotência e guard `RevisaoBaixa` validados e2e (08/06/2026). Escopo MVP = golden path (emitir + baixa); cancelar/estornar/QR PIX/parcelamento ficam para slice 2; credencial **global** via `.env` (decisão do usuário) |
| **D.1.3** | **Notas fiscais** | cancelamento, CC-e, consulta | abas emitidas/recebidas/canceladas, lote | emitir + cancelar + baixar PDF/XML |
| **D.1.4** | **Financeiro por obra** | `CentroCusto`, rateio | DRE da obra, orçado x realizado | financeiro filtrado por obra |
| **D.1.5** | **Devoluções/estornos** | `Devolucao`, refund Asaas, NF devolução | tela de devoluções | estorno reflete no caixa |
| **D.1.6** | **Caixa, bancos & conciliação** | `ContaBancaria`, OFX/webhook | extrato + conciliação | extrato casa com títulos |
| **D.1.7** | **Fluxo de caixa projetado** | projeção AP/AR + medições | gráfico realizado+projetado | projeção bate com títulos |
| **D.1.8** | **Folha do RH no caixa** | consolidação rh→erp (rateio) | visão funcionários (mascarada) | folha aparece no caixa |
| **D.2.x** | **Contábil** | plano de contas, lançamentos, DRE, fechamento | livros + DRE + balancete | DRE fecha com o financeiro |
| **D.3.x** | **Fiscal/Tributário** | apuração, retenções, SPED, **IBS/CBS** | apuração + obrigações | SPED gera; campos IBS/CBS na NF |
| **D.4.x** | **Compras · Estoque · Patrimônio** | ciclo compras, estoque, imobilizado | telas dos ciclos | requisição→pedido→NF→AP |
| **D.5.x** | **Construção civil** | orçamento de obra, medição, RET | orçamento/curva ABC, boletim medição | orçado→medido→financeiro |

**Próximo passo aprovado pelo usuário:** *só o plano por enquanto* — implementação inicia em **D.1.0**
após revisão deste documento.

---

## 14. Decisões registradas
- **ERP contábil completo** (não só operacional) — alvo de longo prazo, entregue por camadas.
- **Asaas** como gateway de cobrança real (boleto/PIX/cartão + webhook).
- Incluir **financeiro por obra**, **devoluções/estornos**, **folha do RH no caixa**, **conciliação +
  fluxo projetado**.
- Tudo como **Django app(s)**, nunca microsserviço Node novo (CLAUDE.md).

## 15. Questões em aberto (decidir antes da sub-fase relevante)
- ~~NFS-e: manter NFE.io ou migrar para Asaas?~~ **Decidido (07/06/2026):** consolidar no **Asaas** —
  NFS-e via [funcoesnf](funcoesnf.md) (`invoices`) e cobrança via [funcoescobrancas](funcoescobrancas.md);
  NFE.io fica como provedor alternativo/legado. Ambos **sandbox agora, real depois**.
- ~~Conta Asaas: uma por tenant (cliente usa a própria) vs conta-mãe com split? (D.1.2)~~ **Decidido
  para o MVP (07/06/2026):** **chave global** em `.env`, compartilhada por todos os tenants — mais
  simples para validar o fluxo ponta a ponta agora; migrar para `IntegracaoAsaas` por tenant (conta
  própria de cada empresa, credencial cifrada) é pendência operacional da Fase 5 (gestão de segredos).
- Contábil: construir **motor próprio** ou integrar com contabilidade externa via SPED/exportação? (D.2)
- Multi-CNPJ por tenant (grupos econômicos / SPE por empreendimento) — modelar agora ou na Fase 8?
- Reforma Tributária: assumir os campos IBS/CBS já em 2026 (informativo) — priorizar D.3 antes?
- ~~Frontend: adotar TanStack Query/Table só no ERP ou promover para padrão do projeto? Recharts vs
  Tremor?~~ **Decidido na prática (D.1.0/D.1.1, 07/06/2026):** TanStack Query/Table + Recharts +
  RHF/zod ficaram restritos a `modules/erp/` por ora — retrofit dos módulos simples (`clientes`,
  `fornecedores`, `obras`, `rh`) é decisão separada, a avaliar quando o ERP estabilizar o padrão.
- ~~Regra de `dar_baixa()` para título já `QUITADO`/`CANCELADO` — bloquear toda baixa adicional, ou só
  capital, permitindo ajuste posterior de juros/multa/desconto?~~ **Decidido (07/06/2026):** nem
  bloquear nem aplicar — **detectar e encaminhar para revisão do financeiro** (`RevisaoBaixa` +
  `BaixaRequerRevisao`, fila `/api/erp/revisoes-baixa/`). Ver "Dívidas técnicas conhecidas" e
  `backend/moduloerp/models.py`.

## 16. Fontes
- Reforma Tributária / cronograma 2026–2033: [TOTVS – Espaço Legislação](https://espacolegislacao.totvs.com/reforma-tributaria/) · [Câmara dos Deputados](https://www.camara.leg.br/noticias/1237089-reforma-tributaria-comeca-fase-de-transicao-com-testes-de-novos-impostos-em-2026/) · [Jettax](https://www.jettax.com.br/blog/cronograma-e-fases-da-reforma-tributaria-de-2026-a-2033/) · [Tax Group – IVA/IBS/CBS/IS](https://www.taxgroup.com.br/intelligence/reforma-tributaria-guia-completo-sobre-iva-ibs-cbs-e-is/)
- Módulos de um ERP: [TOTVS](https://www.totvs.com/blog/erp/modulos-do-erp/) · [Sankhya](https://www.sankhya.com.br/gestao-de-negocios/modulos-do-erp/) · [Nomus](https://www.nomus.com.br/blog-industrial/modulos-de-um-erp/) · [ABC71 – Contábil/Fiscal](https://abc71.com.br/modulo-contabil-fiscal)
- Construção civil: [OSP – Guia tributário construtoras 2026](https://ospcontabilidade.com.br/blog/cnae-construcao-civil-engenharia-guia-tributario/) · [Curva ABC – OrçaFascio](https://www.orcafascio.com/papodeengenheiro/curva-abc) · [Retenção INSS – MLF](https://www.mlfconsultoria.com.br/blog-mlf/retencoes-tributarias-na-construcao-civil)
