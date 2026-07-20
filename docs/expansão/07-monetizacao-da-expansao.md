# Monetização da expansão — além da assinatura

> **Estende** (não substitui) o modelo base de
> [../arquitetura/monetizacao.md](../arquitetura/monetizacao.md): planos híbridos + add-ons +
> quotas + trial, com Asaas como gateway. **A receita nº 1 é e continua sendo assinatura — e o
> caminho de crescimento dela é vender o sistema para o máximo de empresas possível**, via as
> edições verticais ([09-verticais-por-participante.md](09-verticais-por-participante.md)): cada
> edição repete o mesmo motor (planos+quotas) para um mercado novo. As demais fontes deste doc
> são o que **só existe quando a plataforma vira ecossistema** — critério da métrica-norte do H3
> (% de receita não-assinatura, [01-visao.md](01-visao.md) §5).

## 1. O mapa das fontes de receita

| # | Fonte | Mecânica | Depende de | Horizonte |
|---|---|---|---|---|
| 1 | **Assinatura + add-ons + excedentes** ✅ (planejado) | [monetizacao.md](../arquitetura/monetizacao.md) | Fases 7–11 | H0 — base de tudo |
| 2 | Módulos novos como add-ons | Cada módulo do [catálogo](03-mapa-de-modulos.md) = entitlement vendável (AD-4 já dá o mecanismo) | módulo pronto | H1 contínuo |
| 3 | Portais por unidade ativa | Portal do cliente/proprietário cobrado por unidade em carteira (R$/unidade/mês) — cresce com o sucesso do cliente | E2, portal | H1–H2 |
| 4 | **Assinaturas das edições verticais** | Loja, empreiteiro, imobiliária, escritório de projeto, administradora: cada um assina **a própria edição** (tabela de planos própria, mesmo motor de quotas) — multiplica o TAM a cada vertical; o loop de convite derruba o CAC ([09](09-verticais-por-participante.md) §3) | edição pronta ([09](09-verticais-por-participante.md) §6) | H2 — **a maior fonte nova** |
| 5 | Take rate / success fee | % ou fixo por transação intermediada (pedido de material, locação de equipamento, terreno) | marketplace líquido | H2–H3 |
| 6 | Lead fee / destaque | Fornecedor paga por lead qualificado ou posição de destaque — no marketplace **e no feed da rede social** (lançamento patrocinado, perfil em evidência regional — [10](10-rede-social-do-setor.md)); anúncio só de participante verificado, rotulado como patrocinado | marketplace · feed (H3) | H2–H3 |
| 7 | Serviços medidos de IA | Análises além da quota; chatbot RAG premium; previsão de atraso como add-on | Central de IA | H1–H2 |
| 8 | Assinatura digital | Por documento assinado (repasse certificadora + margem) | contratos & assinatura | H1–H2 |
| 9 | BI premium / data products | Add-on BI (warehouse); relatórios de benchmark vendidos por assinatura — inclusive a não-tenants (bancos, seguradoras) | E4 | H2–H3 |
| 10 | Fintech embutida | §5 | volume financeiro na plataforma | H3 |
| 11 | API pública metered | Chamadas de API como recurso de quota; parceiros de integração pagam tier | E5 | H2–H3 |
| 12 | Micro-SaaS destacáveis | §4 | caso a caso | H2–H3 |
| 13 | White-label / Enterprise | Plataforma com marca do cliente p/ grandes incorporadoras/administradoras; SLA + implantação | maturidade operacional (Fase 10 completa) | H3 |
| 14 | Implantação/onboarding assistido | One-time fee (já previsto no estudo base §2) | — | H0 |

## 2. Regra de ouro (herdada do estudo base)

Limite de **valor** → trava dura + upsell; limite de **COGS** (IA, drone, NF, boleto, SMS, API,
assinatura digital) → medidor com excedente cobrado. Toda fonte nova da tabela acima declara em
qual família cai **antes** de ser construída; o enforcement reusa `AssinaturaTenant.limites` + o
catálogo de planos em código ([monetizacao.md §9](../arquitetura/monetizacao.md)).

## 3. Quem paga o quê (princípio)

- **Empresa paga a própria edição** (fonte #4). Loja, empreiteiro, imobiliária, escritório e
  administradora assinam porque o sistema resolve o dia a dia **deles** — a rede é benefício, não
  o produto. Nunca vender acesso "de carona" pago pela construtora: isso mata o incentivo de
  adoção real e o TAM da vertical.
- **Consumidor não paga** (comprador, investidor, morador — personas E2, sem seat). Quem paga o
  portal é o tenant (por unidade ativa, fonte #3), porque o valor — menos suporte, mais vendas —
  é dele.
- **Responder ao parceiro é grátis; operar é pago.** A contraparte convidada responde a RFQ/aceita
  o boletim no trial sem pagar; a assinatura entra quando a edição vira a ferramenta dela
  ([09](09-verticais-por-participante.md) §3). Nunca cobrar dos dois lados da mesma transação no
  início — escolher o lado com maior disposição e subsidiar o outro até a liquidez.
- **Quem não pode comprar não paga licença** (banco, seguradora, cartório, órgão público):
  entram por integração/parceria — a receita deles é indireta (fintech #10, data products #9,
  API #11).

## 4. Micro-SaaS destacáveis (o modelo funcoesODM)

O drone prova o padrão: produto com entitlement próprio, vendável sozinho, banco próprio (AD-7).
Candidatos, em ordem de plausibilidade:

| Candidato | Por que se sustenta sozinho | Mercado standalone |
|---|---|---|
| **Assistência técnica pós-obra** | Dor legal (garantia NBR/CDC) mesmo p/ quem tem outro ERP | Construtoras não-clientes; administradoras |
| **Diário de obra + IA** (web+WhatsApp ✅) | Já funciona quase isolado; onboarding trivial | Pequenas construtoras, engenheiros autônomos, fiscalização de obra pública |
| **Cotações (mini-SCM + rede)** | Valor imediato dos dois lados sem exigir o ERP | Qualquer construtora + lojas |
| **Drone/ODM** ✅ | Já é destacável | Topografia, agro, mineração |
| **Condomínio** | Mercado próprio inteiro (administradoras) | Migra o comprador→morador da base |

Estratégia: micro-SaaS é **porta de entrada** — preço baixo, upsell natural para a plataforma
inteira ("seu diário já está aqui; ative o financeiro"). Cada um mantém o contrato de módulo
(IAM, entitlement), então "destacar" é decisão comercial, não reescrita.

Não confundir com edição vertical: **micro-SaaS** = uma fatia da plataforma vendida isolada para
o *mesmo* tipo de cliente (construtora que só quer o diário); **edição** = bundle completo para um
*outro* participante do mercado ([09](09-verticais-por-participante.md) §1). Os dois usam o mesmo
mecanismo (AD-4: bundle de entitlements).

## 5. Fintech embutida (H3 — o teto de receita do setor)

O fluxo financeiro do setor **já passa pela plataforma** (cobranças Asaas, contas a pagar,
medições). Com volume e histórico:

- **Antecipação de recebíveis** da carteira de parcelas (parceria FIDC/banco; a plataforma tem o
  dado de inadimplência real → melhor pricing de risco; comissão sobre o volume).
- **Escrow/conta garantia** de medição de empreiteiro (libera contra medição aprovada).
- **Seguros embutidos**: garantia de entrega, seguro obra, garantia locatícia — comissão de
  corretagem via parceiro segurador.
- **Crédito para lojas/fornecedores** ancorado no fluxo de pedidos do marketplace.

Pré-condições inegociáveis: volume auditável (trilha ✅ Fase 9.E), compliance/regulatório com
parceiro licenciado (a plataforma **não** vira instituição financeira no início), e o funil
de dados do E4.

## 6. Sequência de ativação de receita

```
H0: assinatura da edição construtora (planos+quotas) ── 100% da receita
H1: + módulos novos, portal por unidade, IA medida, assinatura digital
H2: + EDIÇÕES VERTICAIS (novas assinaturas: loja, empreiteiro, imobiliária…),
     lead fee, BI premium, API
H3: + take rate, data products, fintech, white-label  ── meta: 25–40% não-assinatura
```

Disciplina: **nenhuma fonte nova antes da sua dependência estar líquida** (ex.: take rate antes de
marketplace com transação recorrente só gera atrito e afasta os primeiros participantes).
