# Orçamento — Planilha orçamentária de insumos (`moduloorcamento`) 📋

> **Planta de desenho planejado.** App **ainda não implementado**; esta planta é o
> **alvo**. Nasce do SIL v2: a aba **Custo por obra (Orçado × Aplicado)** já entrega o
> lado **aplicado** (consumo real por obra/etapa, valorizado por custo médio) e mostra o
> **orçado** como *"em breve"* — este módulo é quem preenche esse lado. Sem status/datas
> (o status vive no [roadmap](../roadmap.md)).

## O que é

O **orçamento de insumos** da obra: a **planilha orçamentária** (EAP/etapas × insumos) com
**quantidade e custo previstos** por item, que vira a régua contra a qual o realizado é medido.
Fecha o triângulo do controle físico-financeiro da construção:

```
ORÇADO (moduloorcamento)  →  COMPRADO (SCM)  →  ESTOCADO (SIL)  →  APLICADO (SIL)
   previsto na planilha        pedido/recebido     saldo valorado    consumido na etapa
```

Hoje o SIL já dá **estocado** e **aplicado** (por obra/etapa/insumo), e o SCM dá **comprado**.
Falta o **orçado** — a referência. Com ele, a obra sabe se está **estourando** material.

## Modelos (alvo)

| Modelo | Papel |
|---|---|
| `Orcamento` | Orçamento de uma **obra** (versão/revisão, status rascunho→aprovado→revisado, moeda-base, data-base) |
| `ItemOrcado` | Linha da planilha: `etapa` (`obras.EtapaObra`), `item` (`catalogo.Item`), **quantidade orçada**, **custo unitário orçado**, fonte (SINAPI/SICRO/própria) |
| `ComposicaoCusto` | (opcional) composição de serviço → insumos (mão de obra, material, equipamento), % de perda por insumo |

O **que** se orça vem do [catálogo-mestre](catalogo.md) (`catalogo.Item`) — o mesmo item que o
SCM compra e o SIL estoca. A **etapa** é a de [obras](obras.md) (`EtapaObra`) — a mesma dimensão
que o SIL usa na apropriação do consumo. Assim **orçado e aplicado casam por (obra, etapa, item)**
sem tradução.

## Integrações (o "tudo se conecta")

| Conecta com | Como |
|---|---|
| [SIL](modulosil.md) | **orçado × aplicado** por obra/etapa/insumo — a aba Custo por obra do SIL passa a mostrar o orçado real (hoje `None`); alerta de estouro (aplicado > orçado) |
| [SCM](moduloscm.md) | **orçado × comprado** — a compra nasce da planilha (demanda por insumo orçado); comprometido vs. saldo orçamentário |
| [moduloerp](moduloerp.md) | curva **físico-financeira** (previsto × realizado por etapa) alimenta a DRE por obra |
| [obras](obras.md) | a planilha é por obra e etapa (EAP); o cronograma físico-financeiro amarra à data-base |

## Costura já pronta no SIL

O SIL v2 foi construído **antecipando** este módulo:

- `MovimentacaoEstoque.etapa` e `Requisicao.etapa` (FK `obras.EtapaObra`) — o consumo já é
  apropriado à etapa.
- Endpoint `GET /api/sil/aplicado/` devolve `{obra, etapa, item, aplicado, orcado: null}` — o
  campo `orcado` é o **seam** que este módulo preenche.
- Aba **Custo por obra (Orçado × Aplicado)** no frontend do SIL já renderiza a coluna "Orçado"
  como *em breve*; quando o módulo existir, ela lê o valor real e calcula o saldo/estouro.

## Status / pendências

Planejado. Fase a definir. Ver [roadmap](../roadmap.md).
