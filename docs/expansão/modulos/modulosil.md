# SIL — estoque e logística interna (design de expansão)

> **Natureza: 🧭 estratégia** ([README](README.md)). Estende, sem contradizer, a planta de
> [../03-mapa-de-modulos.md §3](../03-mapa-de-modulos.md), a mecânica de rede de
> [../04-rede-e-marketplaces.md](../04-rede-e-marketplaces.md) e o backbone de eventos/automação
> [../02-arquitetura-de-expansao.md](../02-arquitetura-de-expansao.md) (E3/E6). Separa **o que é
> construído agora** (backend/frontend do `modulosil`, Fase 7 do [../../roadmap.md](../../roadmap.md))
> de **o que gradua depois** (rede de estoque, benchmark, app móvel).

## 1. O laço interno (fase atual — o que resolve hoje)

O SIL é a **outra ponta do laço do SCM** ([moduloscm.md §1](moduloscm.md)) — onde o material vive
entre comprar e consumir:

```
Recebimento (SCM) → ENTRADA no estoque (custo médio) → consumo na obra (requisição → SAÍDA)
   → saldo cai abaixo do mínimo → evento sil.estoque_minimo_atingido → Demanda (SCM) → fecha o laço
```

O **catálogo-mestre** ([../../modulos/catalogo.md](../../modulos/catalogo.md)) é o contrato: um só
`Item` para comprar (SCM), estocar (SIL) e, depois, vender/orçar (comercial/orçamento). Sem
duplicação de item nem de saldo.

## 2. As seis perguntas de plataforma ([README](../README.md))

1. **Efeito de rede** — estoque abaixo do mínimo vira **RFQ automática para lojas parceiras**
   (E6, o caso conector que inaugura a rede — [../04 §2.1](../04-rede-e-marketplaces.md)); estoque
   **ocioso** vira oferta de repasse entre obras/tenants (mesmo padrão de equipamentos).
2. **Valor do ecossistema** — captura o controle de material hoje feito em planilha/WhatsApp; o
   histórico de consumo alimenta previsão e benchmark.
3. **Nova receita** — SIL é módulo vendável (`sil`); premium: previsão de consumo por IA, múltiplos
   almoxarifados, rastreabilidade regulada; quota de SKUs/locais por plano.
4. **Produto independente** — controle de estoque/almoxarifado é um micro-SaaS por si só.
5. **Conexão** — casa com catálogo, SCM (compras), obras (canteiro/consumo), ERP (valorização/DRE),
   NF-e (conciliação de entrada) e a rede (RFQ/benchmark).
6. **Sistema operacional do ciclo de vida** — cobre a etapa **logística/almoxarifado** da obra.

## 3. O que é construído agora × o que gradua depois

| Agora (Fase 7 — `modulosil`) | Depois (H2/H3) |
|---|---|
| Multi-local (central + canteiros), saldo valorado (custo médio móvel), movimentações | Múltiplos armazéns com zonas/endereçamento; WMS pleno (picking/putaway) |
| Requisição da obra → reserva → baixa; transferências; devoluções | Aprovação em **2 níveis** (BPM leve, E6/H2); app móvel de requisição/contagem no canteiro |
| Rastreabilidade (lote/validade); inventário com ajuste | Série/nº patrimonial; controle de EPI por funcionário (casa com SST) |
| Ponto de reposição → evento `sil.estoque_minimo_atingido` → Demanda no SCM | **Automação E6:** mínimo → RFQ publicada na rede p/ lojas da região |
| Valorização de estoque (seam ERP) | Estoque como **ativo circulante** no balanço; consumo no **DRE por obra** |
| Consumo por obra/centro de custo | **Benchmark de giro** e custo de material por m² entre tenants (E4, anonimizado) |

## 4. Ganchos com o resto da plataforma

- **Catálogo** — fonte única do item; a flag `estocavel` decide o que tem saldo.
- **SCM** — Recebimento repõe; falta gera Demanda. O `CentroCusto` do SCM já traz `local_estoque_ref`.
- **ERP** — valorização de estoque + consumo apropriado ao DRE por obra ([moduloerp.md](../../modulos/moduloerp.md)).
- **Obras / Diário** — canteiro por obra; consumo registrado no diário pode baixar estoque (seam).
- **Rede social / marketplaces** — índice de preço de material e giro alimentam o feed do setor
  ([../10-rede-social-do-setor.md](../10-rede-social-do-setor.md)); RFQ automática abre a Edição Loja.

> **Regra de ouro do sequenciamento** ([../01-visao.md §3.2](../01-visao.md)): construir primeiro o
> módulo privado que gera o dado (o SIL interno); a RFQ na rede e o benchmark são a **publicação**
> dele — graduam com a Esfera de Rede, não antes.
