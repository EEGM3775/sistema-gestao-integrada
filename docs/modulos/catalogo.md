# Catálogo — item mestre de plataforma (`catalogo`)

> **Planta do módulo.** Descreve o **desenho e o contrato de API** (sem status/datas — o
> status vive no [roadmap](../roadmap.md)). Nasce da promoção do `Produto` do
> [moduloscm](moduloscm.md) a **cadastro-mestre compartilhado**.

## O que é (e por que é fundação, sem entitlement)

O **cadastro-mestre único** de tudo que a plataforma **compra, estoca, vende, orça ou consome** —
**bem ou serviço**. Fonte única de verdade (MDM/PIM) no molde consolidado dos grandes players:

- **SAP S/4HANA** — um **Product/Material Master central** liga compras, estoque, vendas, produção,
  qualidade, armazém e finanças; material × serviço é só um **discriminador de tipo** (*Product Type
  Group*: material vs. `DIEN`/`SERV`, não-estocável).
- **Oracle Fusion PIM** — um **Item Master** com **taxonomia (item class)** + **flags operacionais
  por aplicação** (`stockable`/`inventory item`…) que dizem como cada módulo trata o mesmo item.

Por isso `catalogo` é **app-fundação sem entitlement** — como `fornecedores`, `clientes`, `obras`:
infraestrutura de todos os módulos, não um produto vendável isolado. Quem **compra** o item é o SCM;
quem o **estoca/movimenta** é o SIL; quem o **vende/orça** é o comercial/orçamento (futuro) — todos
referenciam **o mesmo** `Item`. Não existe "produto do SCM" e "item do estoque" separados: seria a
duplicação de saldo/preço que a régua proíbe.

## Acesso

**Sem `RequireModule`** (fundação). Checagem por **permissão** (`RequirePermission`, camada 2):
`cadastro.item.{view,edit}` (molde de `cadastro.fornecedor.*`/`cadastro.cliente.*`). Todos os
modelos herdam `TenantScopedModel` (isolamento por tenant + RLS fail-closed). O **catálogo é
por-tenant** (cada empresa tem o seu); o seam `item_rede_id` prepara o catálogo **global** da rede.

## Modelos

| Modelo | Papel | Guarda-permissão |
|---|---|---|
| `Item` | **Item mestre**, supplier-agnostic. `codigo_interno` (SKU, único por-tenant), `descricao`, `unidade`, `categoria`, **`tipo`** (taxonomia abaixo), **flags por domínio** (abaixo), `ncm`, `gtin`, `codigo_referencia`+`fonte_referencia` (SINAPI/TCPO), `item_rede_id` (seam rede), `ativo` | `cadastro.item` |
| `ComponenteComposicao` | BOM de um `Item` do tipo **composição**: `item_pai` → `item_filho` + `coeficiente`. Base para explosão de insumos, curva ABC e orçado×realizado do módulo Orçamento (futuro) | `cadastro.item` |

### Taxonomia — `tipo` (rica desde já)

`material` (físico, estocável) · `servico` (não-estocável) · `equipamento` (ferramenta/máquina,
controlável) · `epi` (equipamento de proteção) · `ativo` (patrimônio) · `composicao` (item composto
por outros — SINAPI/TCPO). O `tipo` é o **discriminador SAP-like**; o comportamento fino vem das
flags.

### Flags por domínio (Oracle-like)

`compravel` (entra em Demanda/Pedido do SCM) · `estocavel` (tem saldo no SIL) · `vendavel` (entra no
comercial, futuro) · `consumivel` (baixa por consumo em obra) · `rastreavel` (exige lote/validade no
SIL). O **mesmo** item pode ser comprado, estocado, consumido e (depois) vendido — os flags evitam
tipos redundantes e deixam cada módulo ler só o que lhe importa.

## Migração `moduloscm.Produto` → `catalogo.Item`

O `Produto` já é o embrião do mestre (supplier-agnostic, `codigo_interno` único por-tenant,
`tipo_item` material|serviço, `gtin`/`item_rede_id`); só mora no lugar errado (dentro de um módulo
**vendável**). O porte o promove a fundação:

1. `catalogo.Item` (schema enriquecido) com migration + RLS fail-closed.
2. Data migration copiando os `Produto` existentes **preservando o PK** → as FKs continuam válidas
   por valor.
3. Repontar as **3 FKs** do SCM (`OfertaFornecedor.produto`, `ItemDemanda.produto`,
   `ItemPedido.produto`) para `catalogo.Item`; ajustar imports em views/serializers/tests do SCM.
4. Remover `moduloscm.Produto`; rodar `moduloscm/tests.py` (deve seguir verde) + re-seed.

Greenfield-safe (sem dado real de cliente — [migração v01→v02 §3](../arquitetura/migracao-v01.md)).

## Endpoints (`/api/catalogo/`)

CRUD REST isolado por tenant, **paginado** server-side e com `?search=` (contrato dos selects
assíncronos do frontend — não se carrega o catálogo inteiro no cliente).

| Rota | Recurso | Filtros úteis |
|---|---|---|
| `itens/` | `Item` | `tipo`, `categoria`, `ativo`, flags (`compravel`/`estocavel`/…) · busca `codigo_interno`/`descricao`/`gtin` |
| `componentes-composicao/` | `ComponenteComposicao` | `item_pai` |

## Quem consome (o contrato compartilhado)

| Módulo | Usa o `Item` como | Estado |
|---|---|---|
| [moduloscm](moduloscm.md) | item de `Oferta`/`Demanda`/`Pedido` | migra p/ cá na Fase 7 |
| [modulosil](modulosil.md) | item de `SaldoEstoque`/`Movimentação`/`Requisição` | consumidor nascente |
| Comercial / Orçamento / Projetos | item vendável / composição de custo | futuro (mapa de expansão) |

## Seams (prontos, inertes até graduarem)

- **`item_rede_id`** — id no **catálogo global da rede** (cotações comparáveis entre tenants) —
  [rede e marketplaces](../expansão/04-rede-e-marketplaces.md).
- **`codigo_referencia`/`fonte_referencia`** — vínculo a bases de composição (**SINAPI/TCPO**) para
  o módulo Orçamento ([mapa de módulos §2](../expansão/03-mapa-de-modulos.md)).

## Status / pendências

Status vivo no [roadmap](../roadmap.md).
