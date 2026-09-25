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
`cadastro.item.{view,edit}` (molde de `cadastro.fornecedor.*`/`cadastro.cliente.*`) e
`cadastro.tipo_item.{view,edit}` para os **tipos próprios**. São recursos separados de propósito:
cadastrar item é trabalho diário de quem compra e de quem orça, mas **definir um tipo** muda como o
sistema calcula todos os itens que o usam — encargo social, entrada na relação de compra, saldo em
estoque. É a mesma classe de ato que criar e excluir cliente, e por isso o admin do tenant entrega a
quem responde pelo cadastro-mestre. Todos os
modelos herdam `TenantScopedModel` (isolamento por tenant + RLS fail-closed). O **catálogo é
por-tenant** (cada empresa tem o seu); o seam `item_rede_id` prepara o catálogo **global** da rede.

## Modelos

| Modelo | Papel | Guarda-permissão |
|---|---|---|
| `Item` | **Item mestre**, supplier-agnostic. `codigo_interno` (SKU, único por-tenant), `descricao`, `unidade`, `categoria`, **`tipo`** (taxonomia abaixo), **flags por domínio** (abaixo), `ncm`, `gtin`, `codigo_referencia`+`fonte_referencia`+`publicacao_referencia` (SINAPI/TCPO), `item_rede_id` (seam rede), `ativo` | `cadastro.item` |
| `ComponenteComposicao` | BOM de um `Item` do tipo **composição**: `item_pai` → `item_filho` + `coeficiente`. Base para explosão de insumos, curva ABC e orçado×realizado do módulo Orçamento (futuro) | `cadastro.item` |
| `TipoItemProprio` | O tipo **que a empresa cria** por cima das naturezas fechadas: `codigo`, `nome`, `natureza` (uma das do `tipo`) e as flags de domínio. `Item.tipo_proprio` aponta para ele e o `save()` do `Item` **reescreve o `tipo` pela natureza declarada** — não existe item com rótulo de uma coisa e cálculo de outra. `clean()` recusa encargo social fora de mão de obra e composição comprável/estocável | `cadastro.tipo_item` |

### Taxonomia — `tipo` (rica desde já)

`material` (físico, estocável) · `mao_de_obra` (gente da empresa — **é quem leva encargo social**)
· `encargos_complementares` (EPI, exame, alimentação, transporte: acompanham a hora de mão de obra e
**não** recebem encargo por cima) · `servico` (de terceiro; o preço do subcontratado já vem com o
encargo dele dentro) · `equipamento` (ferramenta/máquina,
controlável) · `epi` (equipamento de proteção) · `ativo` (patrimônio) · `composicao` (item composto
por outros — SINAPI/TCPO). O `tipo` é o **discriminador SAP-like**; o comportamento fino vem das
flags.

**A natureza é fechada; o nome, não.** As oito naturezas acima são a classificação da SINAPI — é
delas que sai o cálculo, e por isso não se criam pela tela. O que o tenant cria é o **nome que ele
usa** ("Andaime locado", "Verba de mobilização") dizendo de qual natureza aquilo é e como as flags se
comportam (`TipoItemProprio`). Os padrões de cada natureza vêm de `TipoItemProprio.padroes_da_natureza`
e são servidos pela API — o formulário pergunta a natureza primeiro e preenche o resto, para quem não
conhece as flags sair com um tipo coerente sem tocar em nenhuma.

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
4. Remover `moduloscm.Produto`; rodar `testes/backend/moduloscm/tests.py` (deve seguir verde) + re-seed.

Greenfield-safe (sem dado real de cliente — [migração v01→v02 §3](../arquitetura/migracao-v01.md)).

## Endpoints (`/api/catalogo/`)

CRUD REST isolado por tenant, **paginado** server-side e com `?search=` (contrato dos selects
assíncronos do frontend — não se carrega o catálogo inteiro no cliente).

| Rota | Recurso | Filtros úteis |
|---|---|---|
| `itens/` | `Item` | `tipo`, `tipo_proprio`, `categoria`, `ativo`, flags (`compravel`/`estocavel`/…) · busca `codigo_interno`/`descricao`/`gtin` |
| `componentes-composicao/` | `ComponenteComposicao` | `item_pai` |
| `tipos-item/` | `TipoItemProprio` (sem paginação — dezenas, não milhares; traz `itens_com_este_tipo`) | `natureza`, `ativo` · busca `codigo`/`nome` |
| `tipos-item/naturezas/` | as naturezas **com o padrão de flag de cada uma** | — |

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
- **`publicacao_referencia`** — de qual **edição** o item foi adotado ("SINAPI BA 10/2024
  desonerada", ou o nome do banco próprio). Rótulo durável e não FK: o catálogo é do tenant, a
  publicação é global, e apagar uma publicação não pode apagar a procedência do item. Sem ele o par
  `(fonte, código)` seria toda a procedência guardada, e não haveria como saber de onde saiu a
  descrição gravada — que é o que a adoção confere antes de sobrescrever
  ([moduloorcamento](moduloorcamento.md)).

## Status / pendências

Status vivo no [roadmap](../roadmap.md).
