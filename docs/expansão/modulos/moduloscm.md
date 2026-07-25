# SCM — suprimentos, cotação e compra direta (design de expansão)

> **Natureza: 🧭 estratégia** ([README](README.md)). Estende, sem contradizer, a planta de
> [../03-mapa-de-modulos.md §3](../03-mapa-de-modulos.md), a mecânica de rede de
> [../04-rede-e-marketplaces.md](../04-rede-e-marketplaces.md) e as edições de
> [../09-verticais-por-participante.md](../09-verticais-por-participante.md). Separa **o que é
> construído agora** (backend do `moduloscm`, entra no [../../roadmap.md](../../roadmap.md) Fase 7)
> de **o que gradua depois** (Esfera de Rede, H2/H3).

## 1. O laço interno (fase atual — o que resolve hoje)

O SCM nasce servindo a obra da construtora, como a ponta de compra do laço com o estoque
(`modulosil`/SIL):

```
executor sinaliza falta no estoque (SIL)  →  Demanda (necessidade de material)
  →  financeiro cota (Cotação/RFQ entre fornecedores conhecidos)  →  Pedido de compra
  →  Recebimento (concilia com XML NF-e já lido no moduloerp.nfe_client)  →  repõe o estoque (SIL)
```

O mesmo módulo, sem mudança estrutural, serve **administradora de condomínio** (mesma necessidade
de material do setor) e, pela via genérica de **Demanda** (`tipo = material | serviço`), o
marketplace de **serviços** (corretor/prestador) — o motor `Demanda → Proposta` é um só.

## 2. As duas vias de aquisição (o que este design acrescenta)

Toda plataforma madura de procurement/marketplace tem **duas vias**, e elas **convergem no mesmo
`PedidoCompra`** (por isso `demanda` e `proposta_vencedora` são nuláveis nele):

| Via | Como funciona | Quando usar | Análogo de mercado |
|---|---|---|---|
| **Cotação / RFQ** (marketplace reverso) | Comprador publica a **Demanda**; fornecedores respondem **Proposta**; adjudica | Item sem preço fixo, volume, negociação | Alibaba RFQ; sourcing do Ariba |
| **Compra direta** (catálogo) | Fornecedor publica **oferta a preço fixo**; comprador compra na hora, sem cotar | Preço conhecido, reposição rápida | Amazon "comprar agora"; Nimbi Private; catálogo *hosted* do Ariba/Coupa |

A compra direta **já vale internamente** antes da rede: comprar de uma lista de preços de
fornecedor conhecido sem abrir cotação. A rede apenas a estende para fora (ver §4).

`PedidoCompra.origem = compra_direta | cotacao | manual`, com `oferta_origem?` apontando para a
oferta comprada na via direta.

## 3. Estoque como fonte única — a trava do Código de Defesa do Consumidor

**Decisão estruturante:** o item tem **um só objeto** (`OfertaFornecedor`), que é **fonte única de
preço E de estoque** para as duas vias. **Não pode existir um "anúncio de venda direta" separado da
"oferta de cotação"** — seriam dois saldos do mesmo item, e se o fornecedor vendesse todo o estoque
por uma via, a outra continuaria "vendável": **vender sem lastro fere o CDC**.

Consequências no desenho:

- **Saldo único com reserva.** Cotação adjudicada e compra direta **debitam/reservam o mesmo
  `estoque_disponivel`**. O ledger de reserva completo é da fase de rede; a **fonte única** é
  estabelecida já agora (um campo, um dono).
- **Preço por faixa (cotação) × preço direto (restritivo).** A cotação admite **desconto por
  quantidade** (faixas). A compra direta usa **preço fixo mais restritivo** (sem o desconto de
  volume) — é a diferença clássica *spot/negociado* × *catálogo*.
- **Publicação opt-in.** A oferta vira item navegável do marketplace só quando o fornecedor a
  publica (`visibilidade = privada | rede`, `compra_direta`, `regiao_entrega`, `condicoes`) —
  coerente com o princípio de [../04 §0](../04-rede-e-marketplaces.md) (rede nasce de publicação,
  nunca de leitura cruzada).

## 4. Documentos espelhados: comprador ↔ vendedor

Uma compra na rede (direta ou por cotação) é um **par espelhado** de registros privados, um em cada
tenant — nunca FK cruzada, sempre cópia com estado sincronizada por eventos (E1 transacional,
[../02 §E1](../02-arquitetura-de-expansao.md)):

| Lado comprador (este módulo) | Lado vendedor (Edição Loja) |
|---|---|
| Demanda / RFQ publicada | RFQ na fila de orçamentos |
| `PedidoCompra` | Pedido de venda |

**O que é construído agora:** apenas o **lado comprador** — `PedidoCompra` com os *seams* de rede
prontos (`ref_externa` UUID estável, `origem_tenant` como cópia). **O que gradua depois:** o
**Pedido de venda** do vendedor, a **sincronização** e a navegação/checkout do marketplace entram
**junto com a Esfera de Rede** ([../04](../04-rede-e-marketplaces.md)), não antes.

## 5. O que é construído agora × o que gradua depois

| Agora (Fase 7 — backend `moduloscm`) | Depois (Esfera de Rede, H2/H3) |
|---|---|
| Catálogo **compartilhado da plataforma** (`catalogo.Item`, extraído do SCM na Fase 7/SIL.0) + `OfertaFornecedor` do SCM, com *seam* de catálogo global (`item_rede_id`, categoria, GTIN) | Catálogo global compartilhado da rede; navegação/busca por categoria+região |
| Demanda genérica (material\|serviço) + Cotação + Proposta — **lado comprador** | Publicação da Demanda como RFQ na rede; propostas de tenants externos |
| `OfertaFornecedor` como fonte única de preço/estoque, com *flags* de publicação | Vitrine do marketplace de compra direta; **Pedido de venda** espelhado |
| `PedidoCompra` (origem `compra_direta`/`cotacao`/`manual`) + Recebimento, **seams** para SIL, ERP e NF-e | Carrinho/checkout, pagamento online (trilhos Asaas), *take rate* no pedido ([../07](../07-monetizacao-da-expansao.md)) |
| Centro de custo próprio do SCM (mapeia p/ ERP ao virar `ContaPagar`) | — |
| Avaliação de fornecedor (privada) | Reputação portátil na rede ([../04 §2.3](../04-rede-e-marketplaces.md)) |

## 6. Ganchos com o resto da plataforma

- **SIL / estoque** — a Demanda pode nascer da falta no estoque (`origem = estoque`); o Recebimento
  repõe o saldo. Fonte única de estoque (§3) é o contrato entre os dois.
- **ERP** (`moduloerp`) — o Pedido/Recebimento vira `ContaPagar`; o centro de custo do SCM mapeia
  para o rateio/DRE do ERP.
- **NF-e** (`moduloerp.nfe_client`) — o Recebimento concilia com o XML já lido.
- **Marketplace de cotações e rede social** — [../04 §2.1](../04-rede-e-marketplaces.md) e
  [../10-rede-social-do-setor.md](../10-rede-social-do-setor.md): cadastrar-se já gera descoberta;
  lojistas veem a demanda e propõem (RFQ) ou publicam ofertas navegáveis (compra direta).

## 7. As seis perguntas de plataforma ([README](../README.md))

1. **Efeito de rede** — cada RFQ/compra com empresa de fora é um lead de trial da Edição Loja.
2. **Valor do ecossistema** — captura o fluxo hoje feito em telefone/WhatsApp/planilha.
3. **Nova receita** — assinatura da loja + *take rate* opcional no pedido + destaque de oferta.
4. **Produto independente** — o par cotação+compra-direta é um micro-SaaS de compras por si só.
5. **Conexão** — casa com SIL (estoque), ERP (financeiro), NF-e, fornecedores e a rede social.
6. **Sistema operacional do ciclo de vida** — cobre a etapa **suprimentos** do empreendimento.
