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
(falta no estoque/SIL ou manual) → Demanda → [publicar?] → Cotação → Propostas → adjudicar
                                                                          ↓
Compra direta de uma Oferta ─────────────────────────────────────→ PedidoCompra → Recebimento → (Avaliação)
```

## Modelos

| Modelo | Papel | Guarda-permissão (view/edit) |
|---|---|---|
| `CentroCusto` | Destino de custo **próprio do SCM** (mapeia p/ o rateio do ERP). `tipo` (obra/empreendimento/almoxarifado/filial/administrativo/outro) + vínculo opcional a `obra`/`empreendimento` + `local_estoque_ref` (seam SIL). Vertical-agnóstico | `scm.centro_custo` |
| `Produto` | Item mestre do catálogo, **supplier-agnostic** (`codigo_interno` único por-tenant, `unidade`, `categoria`, `tipo_item` material\|serviço, `gtin`/`item_rede_id` = seam do catálogo global) | `scm.produto` |
| `OfertaFornecedor` | Oferta de um fornecedor p/ um `Produto` — **fonte única de preço e estoque** das duas vias. `preco_direto` (compra direta), `estoque_disponivel`/`estoque_reservado` (`estoque_reservado` read-only), `compra_direta` (habilita a via direta), `visibilidade` (privada\|rede) | `scm.oferta` |
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

## Catálogo de permissões (`scm.*`, 19)

`scm.produto.{view,edit}` · `scm.oferta.{view,edit}` · `scm.centro_custo.{view,edit}` ·
`scm.demanda.{view,edit,publicar}` · `scm.cotacao.{view,edit,adjudicar}` ·
`scm.pedido.{view,edit,criar}` · `scm.recebimento.{view,edit}` · `scm.avaliacao.{view,edit}`.

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
| `produtos/` | `Produto` | `tipo_item`, `categoria`, `ativo` · busca `codigo_interno`/`descricao`/`gtin` |
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
> para a obra; financeiro cota e compra). A rede/marketplace, o lado vendedor e a compra na vitrine
> pública ficam para a Esfera de Rede — a UI só **não esconde** os campos-seam quando fizer sentido.
> Convenções gerais no [frontend.md](../frontend.md); este roteiro estende, não substitui.

Sub-fases sugeridas (uma fatia de UI por vez, `hasModule('scm')` + gate por permissão):

| Sub-fase | Telas | Consome |
|---|---|---|
| **S.1 Catálogo** | `ProdutosPage` (lista+form), `OfertasPage`/aba de ofertas por produto (com `FaixaPrecoOferta`), `CentrosCustoPage` | `produtos/`, `ofertas/`, `faixas-preco/`, `centros-custo/` |
| **S.2 Demanda & Cotação** | `DemandasPage` (lista+form+itens), botão **Publicar**; `CotacaoDetail` (propostas lado a lado + **Adjudicar**) | `demandas/`(+`publicar`), `itens-demanda/`, `cotacoes/`(+`adjudicar`), `propostas/`, `itens-proposta/` |
| **S.3 Pedido & Recebimento** | `PedidosPage` com as **duas vias**: "Comprar direto" (de uma oferta com `compra_direta`) e "Gerar de cotação"; `PedidoDetail` (itens, status, **registrar recebimento**); `AvaliacaoForm` | `pedidos/`(+`comprar_direto`/`gerar_de_cotacao`), `itens-pedido/`, `recebimentos/`, `avaliacoes/` |
| **S.4 Hub SCM** | `ScmDashboardPage` (KPIs: demandas abertas, cotações a adjudicar, pedidos por status; atalhos) | agregação das listas |

UX-chave a acertar: **as duas vias de compra** (catálogo × cotação) num só `PedidoCompra`; o
**mapa comparativo** de propostas na adjudicação; e deixar visível (sem editar) o que é *seam* de
rede/estoque/ERP para não surpreender quando a expansão ligar.

### Rotas do frontend (React — `modules/scm/`)

Primeiro módulo sobre a **fundação Malha** ([identidade-visual.md](../identidade-visual.md) §10). Kit de
UI próprio do módulo em `modules/scm/components/` (`ui.tsx`: PageHeader/DataTable/Drawer/Modal/inputs/
Pager; `AsyncEntitySelect` = select com busca server-side; `seams.tsx` = chips read-only). Sob
`ModuleRoute module="scm"`:

| Rota | Tela | Sub-fase |
|---|---|---|
| `/app/scm` | `ScmDashboardPage` (hub de KPIs + atalhos) | S.4 |
| `/app/scm/produtos` | `ProdutosPage` | S.1 |
| `/app/scm/ofertas` | `OfertasPage` (+ editor de `FaixaPrecoOferta`) | S.1 |
| `/app/scm/centros-custo` | `CentrosCustoPage` | S.1 |
| `/app/scm/demandas` | `DemandasPage` | S.2 |
| `/app/scm/demandas/:id` | `DemandaDetailPage` (itens + **Publicar** + abrir cotação) | S.2 |
| `/app/scm/cotacoes/:id` | `CotacaoDetailPage` (mapa comparativo + **Adjudicar** + gerar pedido) | S.2/S.3 |
| `/app/scm/pedidos` | `PedidosPage` (**Comprar direto**) | S.3 |
| `/app/scm/pedidos/:id` | `PedidoDetailPage` (itens + recebimento + avaliação) | S.3 |

**Seams na UI (read-only):** chips que só aparecem quando o campo está preenchido — `Rede`
(`visibilidade=rede`), `ContaPagar #n` (`conta_pagar_ref`), `NF-e` (`nota_fiscal_ref`), `Estoque`
(`local_entrega`/`origem=estoque`), `Da rede` (`origem_tenant`) — para não poluir o uso pré-expansão.
Gate por **permissão de usuário** (`hasPermission('scm.*')`), não só entitlement do tenant.

## Status / pendências

Backend **completo (fatias 1–3)** e testado (`moduloscm/tests.py`, 29/29 sobre Postgres). **Frontend
S.1–S.4 implementado** (rotas acima) sobre a fundação Malha. Status vivo no
[roadmap](../roadmap.md#estado-dos-módulos--backend-07062026).
