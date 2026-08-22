# Visão — Plataforma Operacional do Mercado Imobiliário

> De onde partimos: um SaaS multi-tenant de gestão para construção/incorporação
> ([../arquitetura.md](../arquitetura.md)). Para onde vamos: o **sistema operacional do ciclo de
> vida do empreendimento**, onde todo participante do setor trabalha. Este doc é o Nível 2 do
> planejamento (domínio); o Nível 1 (arquitetura) está em
> [02-arquitetura-de-expansao.md](02-arquitetura-de-expansao.md).

## 1. A espinha dorsal: o ciclo de vida do empreendimento

Todo o mercado imobiliário orbita um único fluxo. A plataforma vence quando cobre o fluxo inteiro:

```
 terreno → viabilidade → incorporação → projeto → licenciamento → suprimentos → OBRA
    → venda → financiamento → entrega → pós-obra/assistência → operação/condomínio → revenda
```

| Etapa | Cobertura hoje | Expansão |
|---|---|---|
| Terreno / viabilidade / incorporação | ❌ | Banco de terrenos, estudo de viabilidade, GIS ([03](03-mapa-de-modulos.md) §7) |
| Projeto / licenciamento | ❌ | DMS, licenciamento, BIM ([03](03-mapa-de-modulos.md) §6) |
| Suprimentos | parcial (fornecedores, catálogo) | SCM completo + marketplace de cotações ([04](04-rede-e-marketplaces.md)) |
| **Obra** | ✅ forte (obras, diário, drone, IA) | Planejamento e qualidade (PDCA), **Prancheta** (projeto em campo), SST, equipamentos |
| Venda / financiamento | parcial (CRM, contratos, cobranças) | Espelho de vendas, Edição Imobiliária, rede de distribuição |
| Entrega / pós-obra | ❌ | Vistorias, assistência técnica, manual do proprietário |
| Operação / condomínio | ❌ | Facility, Edição Administradora de condomínio, portal do morador |

O **meio do fluxo (obra + financeiro) é a fortaleza atual** — é onde o produto já é profundo e
diferenciado (diário + IA + drone é combinação rara). A estratégia é expandir **das pontas do
fluxo para fora**, nunca abandonando a profundidade do meio.

## 2. Os participantes e como cada um entra

**Regra comercial:** todo participante que **tem operação empresarial vira tenant pagante da sua
própria edição** do sistema — a edição tem que resolver o dia a dia **dele**; a comunicação com os
demais participantes é o benefício, não a porta de entrada. Ninguém empresarial entra "de carona"
por convite da construtora. O foco é **vender o sistema para o máximo de empresas possível** —
cada vertical multiplica o mercado endereçável. Detalhe por edição em
[09-verticais-por-participante.md](09-verticais-por-participante.md).

| Participante | Hoje | Como entra |
|---|---|---|
| Construtora / incorporadora / loteadora | ✅ tenant pagante | 🏢 **Edição atual** — o cliente-âncora |
| Empreiteiro / prestador de serviços | parcial (fornecedor) | 🏢 **Edição Empreiteiro**: propostas, diário da frente, medições a faturar, NFS-e, receber |
| Fornecedor / loja de materiais | parcial (cadastro passivo) | 🏢 **Edição Loja**: orçamentos, catálogo, pedidos, estoque, NF-e, boletos — as RFQs dos parceiros caem na fila dele |
| Imobiliária / corretor | ❌ | 🏢 **Edição Imobiliária** (corretor = plano individual): CRM, carteira, visitas, comissões, locação |
| Arquiteto / engenheiro / projetista | parcial (funcionário/RT) | 🏢 **Edição Escritório de projeto**: propostas, DMS, timesheet, faturamento |
| Administradora de condomínio | ❌ | 🏢 **Edição Administradora** (H3): taxas, reservas, assembleias, chamados |
| Cliente final (comprador) | ✅ como registro | 👤 Persona gratuita — **portal do cliente** (não compra sistema de negócio; quem paga é o tenant) |
| Investidor | ❌ | 👤 Persona gratuita — portal do investidor (H3) |
| Morador / síndico | ❌ | 👤 Personas da Edição Administradora |
| Banco / seguradora | ❌ | 🔌 **Integração/parceria** (restrições institucionais impedem a venda direta): consomem relatórios/APIs; parceiros da fintech (H3) |
| Cartório / órgão público | ❌ | 🔌 **Integração** (legislação e burocracia inviabilizam a relação comercial): documentos/protocolos; API quando existir |

Três categorias, três mecânicas: 🏢 **tenant com edição própria** (assinatura — a regra) ·
👤 **persona externa gratuita** (só quem não compra sistema de negócio —
[02](02-arquitetura-de-expansao.md) §E2) · 🔌 **integração sem licença** (só quem não pode).

## 3. A tese de plataforma

1. **Single-player primeiro — para cada edição.** O SaaS tem que ser excelente para um tenant
   sozinho: a Edição Loja tem que valer a assinatura mesmo que nenhuma construtora a convide.
   Ferramenta ruim com rede não retém ninguém.
2. **A rede nasce de dados que já existem.** Cotação de material, unidade à venda, terreno,
   catálogo de fornecedor — tudo já é (ou será) registro privado de algum tenant. O marketplace é
   a **publicação opt-in** desses registros, não um produto paralelo a alimentar do zero.
3. **Cada participante compra pela dor própria; fica pela rede.** A loja assina para tocar
   orçamentos, estoque e NF-e; a imobiliária para tocar funil e comissões; o empreiteiro para
   faturar medições. A comunicação entre eles — RFQ que vira orçamento, medição que vira fatura,
   espelho que vira reserva — é o benefício que nenhum sistema isolado oferece.
4. **Efeito de rede = fosso.** Módulos são copiáveis; milhares de empresas de todas as pontas do
   setor transacionando no mesmo grafo de dados, não.
5. **Cada tenant traz os próximos.** Toda transação com uma empresa de fora é um convite para ela
   virar cliente da edição dela — o loop viral de
   [09-verticais-por-participante.md](09-verticais-por-participante.md) §3.
6. **A rede só se autossustenta se for visível.** O estágio final é a **rede social do setor**
   ([10-rede-social-do-setor.md](10-rede-social-do-setor.md)): a atividade real vira conteúdo
   público curado — o lojista vê quem está construindo, o cliente vê as novas obras, a construtora
   vê os melhores corretores e o preço real dos materiais. Quem está fora vê o mercado
   acontecendo lá dentro e entra; entrando, gera mais atividade visível — o flywheel que faz a
   plataforma crescer sozinha.
7. **Cada central pode virar produto.** O drone (funcoesODM) já prova o modelo de produto
   destacável (AD-7). Diário de obra, assistência técnica e cotações têm o mesmo potencial
   ([07-monetizacao-da-expansao.md](07-monetizacao-da-expansao.md) §4).

## 4. Princípios invioláveis (herdados das plantas)

| Princípio | Origem |
|---|---|
| O tenant é soberano: isolamento por RLS fail-closed; rede só por publicação explícita | AD-3, Fase 8 |
| Identidade única na IAM — nenhum portal/produto reimplementa auth | AD-2, AD-5 |
| Módulos à la carte, entitlement por módulo (edição = bundle de módulos) | AD-4 |
| Novo módulo de negócio = Django app; integração = Celery; UI = React | AD-8 |
| Produto destacável tem stack e banco próprios quando se paga (modelo drone) | AD-1, AD-7 |
| PII mascarada por permissão; LGPD de primeira classe | AD-9, Fase 9 |

## 5. Métricas-norte (por estágio)

| Estágio | Métrica-norte | Por quê |
|---|---|---|
| SaaS (H0–H1) | MRR + retenção líquida de tenants | Valor single-player |
| Profundidade (H1) | módulos ativos por tenant (attach rate) | ARPU cresce com o attach |
| Verticais (H2) | **empresas ativas por edição** + % de contrapartes convertidas em tenant | O foco: máximo de empresas na plataforma |
| Rede (H2) | transações cross-tenant/mês (cotações respondidas, medições espelhadas, reservas) | Valor multi-player real, não vanity |
| Ecossistema (H3) | % da receita não-assinatura (take rate, fintech, dados, API) | Plataforma, não ferramenta |
| Autossustentação (H3) | % de tenants novos que chegam **sem venda ativa** (feed, SEO, convite, widget — [10](10-rede-social-do-setor.md) §6) | O flywheel girando sozinho |

Horizontes e gates em [08-roadmap-estrategico.md](08-roadmap-estrategico.md).
