# SCM — Suprimentos (`moduloscm`)

> Cadeia de suprimentos: do **catálogo** de itens e ofertas de fornecedor, passando pela
> **necessidade** (demanda) e **cotação**, até o **pedido**, o **recebimento** e a **avaliação** do
> fornecedor. Módulo **vendável** (entitlement `scm`). Código: [backend/moduloscm/](../../backend/moduloscm/).
> Esta planta descreve o **desenho e o contrato de API** (sem status/datas — o status vive no
> [roadmap](../roadmap.md)). A **visão de expansão** (marketplace reverso, compra direta na rede, rede
> social, lado vendedor) está em [../expansão/modulos/moduloscm.md](../expansão/modulos/moduloscm.md) —
> **não é escopo do frontend da fase atual**, mas os *seams* já existem no modelo.

## Acesso

Entitlement **`scm`** (`RequireModule("scm")`) + checagem por **permissão** (`RequirePermission`,
camada 2). Todos os modelos herdam `TenantScopedModel` (isolamento por tenant + RLS fail-closed nas
migrations 0001–0003). Persona de fábrica **`suprimentos`** = `scm.*` + `cadastro.fornecedor.view`.

## As duas vias de aquisição (o conceito central)

O SCM tem **duas vias que convergem no mesmo `PedidoCompra`** (ver
[expansão/modulos/moduloscm.md §2](../expansão/modulos/moduloscm.md)):

1. **Compra direta (catálogo)** — comprar de uma `OfertaFornecedor` a preço fixo, **sem cotação**.
2. **Cotação/RFQ** — publicar uma `Demanda`, coletar `Proposta`s, **adjudicar** e gerar o pedido.

Fluxo interno completo (o que o frontend da fase atual cobre):

```
(falta no estoque/SIL, planilha do Orçamento ou manual) → Demanda → [publicar?] → Cotação → Propostas → adjudicar
                                                                                        ↓
Compra direta de uma Oferta ───────────────────────────────────────────────────→ PedidoCompra → Recebimento → (Avaliação)
```

**A compra que nasce da planilha** (`POST /api/scm/demandas/do-orcamento/`, permissão
`scm.demanda.edit`, motor em [`do_orcamento.py`](../../backend/moduloscm/do_orcamento.py)):
consome a relação consolidada de insumos do [Orçamento](moduloorcamento.md) e cria a `Demanda`
com a quantidade **da obra inteira** — o mesmo aço que aparece em nove serviços entra uma vez,
somado, apontando o mesmo `catalogo.Item` que foi orçado.

O arquivo mora **aqui**, e não no orçamento, porque quem sabe explodir composição é aquele
módulo e quem sabe o que é uma demanda é este. Três decisões do domínio: nasce **rascunho**
(planilha de mil linhas viraria RFQ com centenas de itens indo direto para cotação); **material
e serviço se separam** (mão de obra não vira compra — a RFQ pediria preço de "PEDREIRO (H)"); e
a **cobertura viaja junto** (se metade das composições não foi explodida, a lista de compra é
metade, e o comprador precisa saber antes de cotar).

## Modelos

| Modelo | Papel | Guarda-permissão (view/edit) |
|---|---|---|
| `CentroCusto` | Destino de custo **próprio do SCM** (mapeia p/ o rateio do ERP). `tipo` (obra/empreendimento/almoxarifado/filial/administrativo/outro) + vínculo opcional a `obra`/`empreendimento` + `local_estoque_ref` (seam SIL). Vertical-agnóstico | `scm.centro_custo` |
| `catalogo.Item` ⤴ | **Item mestre — extraído para o app-fundação [`catalogo`](catalogo.md)** (Fase 7, sub-fatia SIL.0): o antigo `Produto` do SCM virou o **cadastro-mestre compartilhado** (bem/serviço/equip./ativo/composição). O SCM passa a **referenciar** `catalogo.Item`, não a possuí-lo. Gerido por `cadastro.item.{view,edit}` | `cadastro.item` |
| `OfertaFornecedor` | Oferta de um fornecedor p/ um `catalogo.Item` — **fonte única de preço e estoque (do fornecedor)** das duas vias. `preco_direto` (compra direta), `estoque_disponivel`/`estoque_reservado` (`estoque_reservado` read-only), `compra_direta` (habilita a via direta), `visibilidade` (privada\|rede). Não confundir com o `SaldoEstoque` do [SIL](modulosil.md) (nosso estoque interno) | `scm.oferta` |
| `FaixaPrecoOferta` | Desconto por quantidade da oferta — só na **cotação** (`quantidade_min` → `preco_unitario`) | `scm.oferta` |
| `Demanda` | **Pivô publicável**. `tipo` material\|serviço, `status` (rascunho→aberta→em_cotacao→atendida/cancelada), `visibilidade` (privada\|rede, read-only — muda por `publicar`), `origem` (manual\|estoque), `centro_custo`, `solicitante`, `ref_externa` (UUID auto = id do gêmeo na rede) | `scm.demanda` |
| `ItemDemanda` | Linha da demanda. `produto` **ou** `descricao_servico` (serviço/item livre) + `quantidade`/`unidade` | `scm.demanda` |
| `Cotacao` | RFQ de uma `Demanda`. `status` (aberta→encerrada→adjudicada, read-only), `visibilidade`, `data_limite` | `scm.cotacao` |
| `Proposta` | Resposta de fornecedor. Interna → `fornecedor` (FK); da rede → `origem_tenant` (cópia, **sem FK cruzada**) + `fornecedor_nome`. `valor_total`, `prazo`, `status` (recebida→vencedora/recusada, read-only) | `scm.cotacao` |
| `ItemProposta` | Preço proposto p/ um `ItemDemanda` (único por proposta+item) | `scm.cotacao` |
| `PedidoCompra` | **Convergência das duas vias** (`origem` compra_direta\|cotacao\|manual). Rastros opcionais: `oferta_origem` (direta), `proposta_vencedora`+`demanda` (cotação). `status` (rascunho→aprovado→enviado→recebido_parcial/total→cancelado), `fornecedor`, `centro_custo`, `valor_total`, `conta_pagar_ref` (seam ERP, read-only), `ref_externa`/`origem_tenant` (seam rede) | `scm.pedido` |
| `ItemPedido` | Linha do pedido (`produto` ou `descricao` + `quantidade`/`preco_unitario`) | `scm.pedido` |
| `Recebimento` | Entrega (`tipo` parcial\|total) — conciliação com NF-e (`nota_fiscal_ref`, seam) + origem da entrada de estoque (`local_entrega`, seam SIL). Criar recebimento **propaga o status ao pedido** | `scm.recebimento` |
| `ItemRecebimento` | Quantidade recebida por item do pedido | `scm.recebimento` |
| `AvaliacaoFornecedor` | Notas 1–5 (qualidade/pontualidade/atendimento) + comentário, opcionalmente ligada a um pedido | `scm.avaliacao` |

## Catálogo de permissões (`scm.*`, 17)

`scm.oferta.{view,edit}` · `scm.centro_custo.{view,edit}` ·
`scm.demanda.{view,edit,publicar}` · `scm.cotacao.{view,edit,adjudicar}` ·
`scm.pedido.{view,edit,criar}` · `scm.recebimento.{view,edit}` · `scm.avaliacao.{view,edit}`.

> **Nota (SIL.0):** os antigos `scm.produto.{view,edit}` **saíram** — a gestão do item mestre passou
> para o app-fundação [`catalogo`](catalogo.md) sob `cadastro.item.{view,edit}` (disponível a todos os
> tenants, não só aos que assinam `scm`). A persona `suprimentos` ganha `cadastro.item.view`.

Regra do `RequirePermission`: **GET → `.view`**, **escrita (POST/PUT/PATCH/DELETE) → `.edit`**; os
verbos de domínio abaixo exigem a permissão dedicada (via `action_permission_map`).

## Endpoints (`/api/scm/`)

CRUD REST em cada recurso (list/create/retrieve/update/partial_update/destroy), isolado por tenant.
As **listas paginam** server-side (`ScmPageNumberPagination`: `page`/`page_size`, `count`/`results`) e
os viewsets de select aceitam `?search=` — é o contrato dos selects assíncronos do frontend (não se
carrega o catálogo inteiro no cliente). As tabelas-filhas (`itens-*`, `faixas-preco`) **não** paginam
(lidas por pai). Vários serializers expõem **rótulos denormalizados read-only** para as listas
(ex.: `produto_descricao`/`fornecedor_nome` na oferta; `fornecedor_label` na proposta;
`centro_custo_nome`/`itens_count` no pedido). `itens-proposta` aceita `?proposta__cotacao=` (monta o
mapa comparativo itens × propostas numa chamada).

| Rota | Recurso | Filtros úteis |
|---|---|---|
| `centros-custo/` | `CentroCusto` | `tipo`, `ativo`, `empreendimento`, `obra` · busca `nome`/`codigo` |
| ~~`produtos/`~~ → **`/api/catalogo/itens/`** | `catalogo.Item` (movido p/ o app catálogo — SIL.0) | `tipo`, `categoria`, `ativo` · busca `codigo_interno`/`descricao`/`gtin` |
| `ofertas/` | `OfertaFornecedor` | `produto`, `fornecedor`, `compra_direta`, `visibilidade`, `ativo` |
| `faixas-preco/` | `FaixaPrecoOferta` | `oferta` |
| `demandas/` | `Demanda` | `tipo`, `status`, `visibilidade`, `origem`, `centro_custo` |
| `itens-demanda/` | `ItemDemanda` | `demanda`, `produto` |
| `cotacoes/` | `Cotacao` | `demanda`, `status`, `visibilidade` |
| `propostas/` | `Proposta` | `cotacao`, `fornecedor`, `status` |
| `itens-proposta/` | `ItemProposta` | `proposta`, `item_demanda` |
| `pedidos/` | `PedidoCompra` | `origem`, `status`, `fornecedor`, `centro_custo`, `demanda` |
| `itens-pedido/` | `ItemPedido` | `pedido`, `produto` |
| `recebimentos/` | `Recebimento` | `pedido`, `tipo` |
| `itens-recebimento/` | `ItemRecebimento` | `recebimento`, `item_pedido` |
| `avaliacoes/` | `AvaliacaoFornecedor` | `fornecedor`, `pedido` |

**Verbos de domínio** (POST, exigem permissão dedicada):

| Endpoint | Corpo | Efeito | Permissão |
|---|---|---|---|
| `POST demandas/{id}/publicar/` | — | `visibilidade=rede`; rascunho→aberta | `scm.demanda.publicar` |
| `POST cotacoes/{id}/adjudicar/` | `{ proposta_id }` | marca a vencedora, recusa as demais, cotação→adjudicada | `scm.cotacao.adjudicar` |
| `POST pedidos/comprar_direto/` | `{ oferta, quantidade, centro_custo? }` | via **direta**: pedido `aprovado` (origem=compra_direta) + item a `preco_direto`. Recusa oferta sem `compra_direta` (400) | `scm.pedido.criar` |
| `POST pedidos/gerar_de_cotacao/` | `{ cotacao }` | via **cotação**: pedido da proposta vencedora (copia itens) + demanda→atendida. Sem vencedora → 400 | `scm.pedido.criar` |

`GET status/` — health do módulo (só exige `scm`).

## Comportamento e regras

- **Estoque = fonte única (CDC):** não há anúncio de venda direta separado da oferta de cotação — um
  saldo, um preço. A **reserva/anti-oversell é do lado vendedor** (rede) e **não** é aplicada no lado
  comprador atual, de propósito (ver [expansão/modulos/moduloscm.md §3](../expansão/modulos/moduloscm.md)).
- **Recebimento propaga status:** criar um recebimento `total`/`parcial` põe o pedido em
  `recebido_total`/`recebido_parcial`.
- **`Demanda.solicitante`** default = usuário do request quando não enviado.
- **Seams (frontend NÃO implementa agora, mas o modelo já carrega):** `origem=estoque` (gatilho do
  SIL), `local_entrega`/`nota_fiscal_ref` (SIL/NF-e), `conta_pagar_ref` (ERP), `visibilidade`/
  `ref_externa`/`origem_tenant` (rede/marketplace).

## Frontend (fase atual) — escopo e sub-fases

> **Este frontend não é o da expansão.** Cobre o SCM **interno** de um tenant (a construtora compra
> para a obra; financeiro cota e compra). É **enxuto e direto**: ver o orçamento comparado e comprar.
> Rede/marketplace, lado vendedor e vitrine pública ficam para a Esfera de Rede: **sem feature nem
> dado de rede dentro do módulo** — nada de "publicar na rede", visibilidade ou chips de rede em
> registros. Existe só uma aba **"Esfera de Rede" bloqueada (cadeado)** — teaser de visão, que
> destrava quando construída. Os campos-seam de rede seguem no backend, inertes. Os **seams internos**
> (NF-e no recebimento; ContaPagar/estoque quando integrados) são integrações reais. Convenções gerais
> no [frontend.md](../frontend.md).
> **O frontend do SCM é a referência da régua de módulo** ([frontend.md §1.6](../frontend.md)): a
> profundidade, a facilidade de uso e o *arquitetado-para-graduar* que todo módulo de frontend herda
> — cockpit com fila de decisão, loop ponta a ponta com verbos, dados honestos e seams de rede
> prontos no modelo (sem UI de rede aqui). Página única com abas em
> [frontend/src/modules/scm/pages/SuprimentosPage.tsx](../../frontend/src/modules/scm/pages/SuprimentosPage.tsx).

Sub-fases sugeridas (uma fatia de UI por vez, `hasModule('scm')` + gate por permissão):

| Sub-fase | Telas | Consome |
|---|---|---|
| **S.1 Catálogo** | `ProdutosPage` (lista+form, lê o item mestre); `OfertasPage` em **cards** (preço direto + barra de estoque + **Comprar direto**) ou tabela, com editor de `FaixaPrecoOferta`; `CentrosCustoPage` | `catalogo/itens/`, `ofertas/`, `faixas-preco/`, `centros-custo/` |
| **S.2 Demanda & Cotação** | `DemandasPage` (lista+form+itens); `CotacaoDetail` = **mapa comparativo** (itens × propostas, **estrelas** do fornecedor, marcador **menor** por item, **delta** vs. menor total, moldura da coluna recomendada/vencedora, barra de **IA inerte**) + **Adjudicar** | `demandas/`, `itens-demanda/`, `cotacoes/`(+`adjudicar`), `propostas/`, `itens-proposta/` |
| **S.3 Pedido & Recebimento** | `PedidosPage` com as **duas vias**: "Comprar direto" (de uma oferta com `compra_direta`) e "Gerar de cotação"; `PedidoDetail` (itens, status, **registrar recebimento**); `AvaliacaoForm` | `pedidos/`(+`comprar_direto`/`gerar_de_cotacao`), `itens-pedido/`, `recebimentos/`, `avaliacoes/` |
| **S.4 Hub SCM** | `ScmDashboardPage`: **trilho de fluxo** (Demanda→Cotação→Pedido→Recebimento com contagens), KPI **Compras no mês** (valor real + delta vs. mês anterior, mês selecionável), cotações a adjudicar, fornecedores avaliados; atalhos | `dashboard/` (agregado) |

UX-chave: **as duas vias de compra** (catálogo × cotação) num só `PedidoCompra`; o **mapa
comparativo** como coração da adjudicação (estrelas/menor/delta/moldura); a **barra de IA inerte**
("em breve", sem dados fabricados) reservando o lugar do assistente; e mostrar só os *seams*
**internos** (ERP/NF-e/estoque). A **reputação** (estrelas) vem de `AvaliacaoFornecedor` agregada no
`PropostaSerializer` (`fornecedor_avaliacao_media`/`_count`); sem avaliação → "sem avaliação".

### Rotas e estrutura do frontend (React — `modules/scm/`)

Primeiro módulo sobre a **fundação Malha** ([identidade-visual.md](../identidade-visual.md) §10).
**Página única com abas**, self-contained (primitivos Malha embutidos: `Pill`/`Card`/`Kpi`/`Avatar`/
modais), sob `ModuleRoute module="scm"`. As sub-fases S.1–S.4 viram **abas de uma só tela**; os
drill-downs (cotação, pedido) e os verbos (adjudicar, comprar direto, gerar de cotação, receber,
avaliar) abrem em detalhe/modal na própria aba.

| Rota | Tela | Abas |
|---|---|---|
| `/app/scm` | `SuprimentosPage` | **Cockpit** (S.4: trilho de fluxo + KPIs + fila de decisão + atividade), **Catálogo** (S.1: ofertas em cards + Comprar direto), **Cotação** (S.2: lista + mapa comparativo + Adjudicar + gerar pedido), **Pedidos** (S.3: duas vias + recebimento + avaliação), **Esfera de Rede** (bloqueada 🔒) |

**Aba Esfera de Rede — bloqueada (cadeado):** teaser de visão (RFQ na rede, índice de preço regional,
reputação portátil, documento espelhado comprador↔vendedor). **Sem feature nem dado de rede** — os
campos-seam seguem inertes no backend. Marca o lugar; destrava quando a Esfera de Rede for construída.

**Seams na UI:** só os **internos** — a NF-e (`nota_fiscal_ref`) é capturada no recebimento;
ContaPagar (`conta_pagar_ref`) e estoque (`local_entrega`) aparecem quando as integrações graduarem.
Os *seams de rede* (`visibilidade`, `origem_tenant`, `ref_externa`) **não têm UI** de feature. Gate por
**permissão de usuário** (`hasPermission('scm.*')`), não só entitlement do tenant.

## Status / pendências

Backend **completo (fatias 1–3)** + agregação de reputação e endpoint `dashboard/`, testado
(`moduloscm/tests.py`, 34/34 sobre Postgres). **Mudança planejada (Fase 7, SIL.0):** o `Produto` do
SCM é **extraído** para o app-fundação [`catalogo`](catalogo.md) (`catalogo.Item`) — o SCM passa a
referenciá-lo; ver a migração em [catalogo.md](catalogo.md#migração-moduloscmproduto--catalogoitem).
**Frontend S.1–S.4 reconstruído sobre o protótipo Malha**
(página única com abas: mapa comparativo, catálogo em cards, hub com trilho de fluxo, IA inerte; aba
Esfera de Rede bloqueada — cadeado, teaser de visão, sem feature de rede). Status vivo
no [roadmap](../roadmap.md#estado-dos-módulos--backend-07062026).
