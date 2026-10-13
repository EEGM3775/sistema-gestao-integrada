# SIL — Estoque & Logística interna (`modulosil`)

> **Planta do módulo.** Descreve o **desenho e o contrato de API** (sem status/datas — o
> status vive no [roadmap](../roadmap.md)). A **visão de expansão** (rede de estoque,
> benchmark de giro, RFQ automática, app móvel) está em
> [../expansão/modulos/modulosil.md](../expansão/modulos/modulosil.md).

## O que é

**Estoque + logística interna** da empresa: do **almoxarifado central** e dos **canteiros por obra**,
passando pelo **saldo valorado**, pelas **movimentações** (entrada/saída/ajuste/transferência),
pela **requisição de material da obra**, pela **rastreabilidade** (lote/validade) e pelas
**devoluções**, até o **inventário**. Fecha o laço do [SCM](moduloscm.md): *falta no estoque →
Demanda → Cotação/Pedido → Recebimento → repõe o estoque*. O **que** se estoca vem do
[catálogo-mestre](catalogo.md) (`catalogo.Item`, itens com flag `estocavel`).

**Construtora-native (v2).** Além do WMS-lite, o SIL cobre o que uma construtora precisa no
almoxarifado, apurado da pesquisa de mercado (Sienge/TOTVS):

- **EPI (NR-6):** ficha de entrega por colaborador com **CA + validade** e comprovante — a prova
  trabalhista. Alerta de CA vencido / troca prevista.
- **Ferramentaria (comodato):** ferramentas com patrimônio, **empréstimo→devolução** por colaborador,
  alerta de atraso e controle de **calibração/manutenção**.
- **Físico-financeiro (orçado × aplicado):** o consumo é apropriado a **obra E etapa**
  (`obras.EtapaObra`); a Gestão mostra o **aplicado** por etapa/insumo. O **orçado** vem do
  [módulo Orçamento](moduloorcamento.md) — orçamento aprovado vigente da obra, agregado na mesma
  chave `(obra, etapa)`, confrontando **custo direto** (material sai do estoque a custo; comparar
  com preço+BDI faria toda obra parecer economia). Sem régua aprovada ou sem o módulo assinado,
  `orcado` fica `null` em vez de zero.
- **Curva ABC** de materiais (A≈80% do valor) e **ruptura** para priorizar o controle.

A tela separa **Operação** (almoxarife: alta frequência) de **Gestão** (engenheiro: curva ABC, custo
por obra, ruptura) — dois públicos, uma página. O colaborador de EPI/ferramentaria integra ao
[RH](../modulos/README.md) (`rh.Funcionario`), com fallback de texto livre.

> **Dois "estoques" distintos, não confundir:** o `OfertaFornecedor.estoque_*` do SCM é o estoque
> **do fornecedor** (para venda/marketplace, inerte hoje); o `SaldoEstoque` do SIL é **o nosso**
> estoque interno. Donos diferentes, saldos diferentes.

## Acesso

Entitlement **`sil`** (`RequireModule("sil")`) + checagem por **permissão** (`RequirePermission`).
Todos os modelos herdam `TenantScopedModel` (RLS fail-closed). Persona de fábrica **`almoxarife`** =
`sil.*` + `cadastro.item.view` + `obra.obra.view` + `cadastro.fornecedor.view` + `rh.funcionario.view`
(picker de colaborador em EPI/ferramentaria).

## Modelos

| Modelo | Papel | Guarda-permissão |
|---|---|---|
| `LocalEstoque` | Local físico: almoxarifado **central** ou **canteiro** (vínculo opcional a `obra`/`empreendimento`; ou a `fornecedor` p/ consignação). `ativo` | `sil.local` |
| `SaldoEstoque` | Saldo de um `Item` num `LocalEstoque`: `quantidade`, **`custo_medio`** (ponderado móvel), `reservado`, `ponto_reposicao`. Único por (item, local). Tabela de consulta de saldo | `sil.saldo` (view) |
| `MovimentacaoEstoque` | **Ledger append-only**: `tipo` (entrada/saída/ajuste/transf_saída/transf_entrada/devolução), `item`, `local`, `quantidade`, `custo_unitario`, `usuario`, refs de origem (`recebimento_scm_ref`, `requisicao`, `obra`, `lote`), `observacao` | `sil.movimentacao` |
| `Requisicao` + `ItemRequisicao` | Pedido de material da **obra**: `status` (rascunho→pendente→aprovada→atendida/parcial→cancelada), `solicitante`, `aprovador`, `obra`/`centro_custo`. Aprovar **reserva**; atender **baixa** (SAÍDA) | `sil.requisicao` (+`.aprovar`/`.atender`) |
| `Transferencia` + itens | Movimento entre locais (transf_saída no origem + transf_entrada no destino, custo preservado) | `sil.transferencia` (+`.executar`) |
| `Devolucao` + itens | Ao **fornecedor** (SAÍDA, liga a `recebimento`/`pedido` do SCM) ou ao **estoque** (ENTRADA, estorno de requisição) | `sil.devolucao` |
| `Lote` + `SaldoEstoqueLote` | Rastreabilidade de itens com flag `rastreavel`: `numero_lote`, `validade`, `fornecedor`; saldo por lote. Alerta de vencimento | `sil.lote` |
| `Inventario` + `ItemInventario` | Contagem (geral/cíclica): contado × sistema → gera `MovimentacaoEstoque` de **ajuste** ao fechar | `sil.inventario` (+`.fechar`) |
| `EntregaEPI` | **EPI (NR-6):** `item`(EPI) × `colaborador`(`rh.Funcionario`, ou `colaborador_nome`), `ca_numero`/`ca_validade`, `data_prevista_troca`, `assinado`, `baixou_estoque`. Property `vencido`. Baixa opcional do estoque na entrega | `sil.epi` (+`.edit` p/ devolver) |
| `Ferramenta` | **Ferramentaria:** `nome`/`patrimonio` (único por-tenant), `estado` (disponível/emprestada/manutenção/baixada), `calibravel`, `proxima_calibracao`/`proxima_manutencao`, `valor`. Verbo `alterar_estado` | `sil.ferramenta` |
| `EmprestimoFerramenta` | **Comodato:** `ferramenta` × `colaborador`, `data_prevista_devolucao`, property `atrasada`. Emprestar marca a ferramenta EMPRESTADA; `devolver` a libera | `sil.ferramenta` (+`.edit`) |

> **Apropriação físico-financeira:** `MovimentacaoEstoque` e `Requisicao` ganharam `etapa`
> (FK `obras.EtapaObra`). Atender requisição / registrar saída propaga **obra + etapa** ao ledger —
> base do orçado×aplicado (ver [Orçamento](moduloorcamento.md)).

## Catálogo de permissões (`sil.*`)

`sil.local.{view,edit}` · `sil.saldo.{view,edit}` · `sil.movimentacao.{view,edit}` ·
`sil.requisicao.{view,edit,aprovar,atender}` · `sil.transferencia.{view,edit,executar}` ·
`sil.devolucao.{view,edit,executar}` · `sil.lote.{view,edit}` · `sil.inventario.{view,edit,fechar}` ·
`sil.epi.{view,edit}` · `sil.ferramenta.{view,edit}` · `sil.relatorio.view` (Gestão: curva ABC,
aplicado). **26 permissões `sil.*`.** Regra do `RequirePermission`: GET → `.view`, escrita → `.edit`;
verbos de domínio (aprovar, atender, executar, fechar, devolver) exigem a permissão dedicada (via
`action_permission_map`).

## Endpoints (`/api/sil/`)

CRUD REST isolado por tenant; **listas paginam** server-side e os viewsets de select aceitam
`?search=` (contrato dos selects assíncronos). Verbos de domínio abaixo.

| Rota | Recurso | Filtros úteis |
|---|---|---|
| `locais/` | `LocalEstoque` | `tipo`, `ativo`, `obra`, `empreendimento` |
| `saldos/` | `SaldoEstoque` | `item`, `local`, `abaixo_minimo` |
| `movimentacoes/` | `MovimentacaoEstoque` | `item`, `local`, `tipo`, `obra`, período |
| `requisicoes/` · `itens-requisicao/` | `Requisicao` | `status`, `obra`, `solicitante` |
| `transferencias/` | `Transferencia` | `origem`, `destino`, `status` |
| `devolucoes/` | `Devolucao` | `fornecedor`, `pedido` |
| `lotes/` | `Lote` | `item`, `vencendo` |
| `inventarios/` · `itens-inventario/` | `Inventario` | `local`, `status` |
| `entregas-epi/` | `EntregaEPI` | `item`, `colaborador`, `status`, `obra` |
| `ferramentas/` | `Ferramenta` | `estado`, `local`, `calibravel` |
| `emprestimos/` | `EmprestimoFerramenta` | `ferramenta`, `colaborador`, `status` |
| `dashboard/` | agregado do cockpit (inclui EPI vencendo, ferramenta atrasada/manutenção, recebimentos a conferir) | — |
| `curva-abc/` | classificação A/B/C por valor em estoque (Gestão) | — |
| `aplicado/` | consumo aplicado por **obra/etapa/insumo** (físico-financeiro) + `orcado`/`saldo`/`estourado` do [Orçamento](moduloorcamento.md) aprovado (`null` sem régua ou sem o módulo) | `obra` |

**Verbos de domínio** (POST, permissão dedicada): `requisicoes/{id}/aprovar/` · `.../atender/` ·
`transferencias/{id}/executar/` · `devolucoes/{id}/executar/` · `inventarios/{id}/fechar/` ·
`saldos/{id}/gerar_demanda/` (cria `Demanda(origem=estoque)` no SCM) · `saldos/{id}/definir_minimo/` ·
`entregas-epi/{id}/devolver/` · `ferramentas/{id}/alterar_estado/` · `emprestimos/{id}/devolver/`.

## Comportamento e regras

- **Custo médio ponderado móvel:** toda ENTRADA recalcula `SaldoEstoque.custo_medio`; SAÍDA valoriza
  pelo custo médio vigente (norma brasileira; base da valorização de estoque no ERP/DRE por obra).
- **Reserva:** aprovar requisição **reserva** (não baixa); atender baixa. `reservado` protege o saldo
  comprometido.
- **Ponto de reposição:** saldo abaixo de `ponto_reposicao` alimenta a **fila de decisão** do
  cockpit e emite o evento `sil.estoque_minimo_atingido` (nome reservado no backbone
  [E3](../expansão/02-arquitetura-de-expansao.md)); o botão **"Gerar Demanda"** cria a `Demanda`
  no SCM (`origem=estoque`).
- **Recebimento → entrada:** criar `Recebimento` no SCM gera `MovimentacaoEstoque` ENTRADA (ativa o
  seam `local_entrega`); concilia com o XML NF-e já lido (`nota_fiscal_ref`).
- **Inventário:** fechar a contagem gera ajustes automáticos e trava reedição. Cada linha guarda o
  ajuste aplicado, com sinal (`ajuste_aplicado`), e **reabrir** (`reabrir/`, mesma permissão de fechar)
  o estorna sobre o saldo de hoje — recusando se deixaria saldo negativo. Contagem e linha só se
  excluem com o inventário aberto.

## Integrações (o "tudo se conecta")

| Conecta com | Como | Estado na Fase 7 |
|---|---|---|
| [catalogo](catalogo.md) | fonte única do **que** se estoca (`Item` com `estocavel`) | **vivo** |
| [moduloscm](moduloscm.md) | Recebimento → ENTRADA; item < mínimo → **Demanda** (`origem=estoque`) | **vivo** (as duas pontas) |
| [obras](obras.md) | canteiro vinculado à obra; consumo (requisição) apropriado à obra | **vivo** |
| [modulopdca](modulopdca.md) | o compromisso da semana pede o material (requisição em rascunho do canteiro, obra + etapa); o apontamento **avisa** a baixa que falta (`GET consumo-a-baixar/`, card no cockpit: teórico do avanço × saídas) — não baixa nada | **vivo** |
| [moduloerp](moduloerp.md) | consumo → custo por centro de custo/obra (DRE); valorização de estoque | **vivo (leve) + seam** |
| NF-e (`moduloerp.nfe_client`) | entrada concilia com o XML já lido | **seam pronto** |
| Eventos (E3) / Automação (E6) | `sil.estoque_minimo_atingido`, `sil.material_vencendo` → notificação/RFQ | **evento vivo; RFQ = rede** |
| IA / app móvel / rede | previsão de consumo, contagem mobile, marketplace de estoque ocioso | **seam (aba Rede 🔒)** |

## Frontend (fase atual) — escopo e sub-fatias

**Segue a régua do SCM** ([frontend.md §1.6](../frontend.md)) no padrão Malha, mas com um seletor de
topo **Operação | Gestão** (dois públicos, uma página) — [LogisticaPage](../../frontend/src/modules/sil/pages/LogisticaPage.tsx).
Rota `/app/sil` sob `ModuleRoute module="sil"`; cada verbo gateado por **permissão de usuário**
(`hasPermission('sil.*')`), não só entitlement. Kit próprio em [ui.tsx](../../frontend/src/modules/sil/ui.tsx);
abas em [tabs/](../../frontend/src/modules/sil/tabs/) (`operacao`/`pessoas`/`gestao`). **Drill-down
clicável** (drawer): ficha do **almoxarifado** (o que há dentro) e **kardex do item** (saldo por local +
ledger), dentro das abas — sem abas soltas.

**Operação** (almoxarife, alta frequência):

| Aba | Cobre |
|---|---|
| **Cockpit** | fila de decisão (abaixo do mínimo → **Gerar Demanda** · requisições a aprovar/atender · inventários) + alertas construtora (recebimentos a conferir, **EPI vencendo**, **ferramenta em atraso**) + atividade recente |
| **Almoxarifados** | locais em cards (valor + nº itens) → **clique** abre a ficha do local; saldos valorados com **clique no item** → kardex; Gerar Demanda / definir mínimo; novo local |
| **Movimentações** | ledger com seams de origem; registrar entrada/saída/ajuste (saída apropria **obra + etapa**) |
| **Requisições** | criar (com obra/etapa + linhas) · aprovar (reserva) · atender (saída) · **detalhe** com linhas |
| **Transf. & Devoluções** | entre locais; ao fornecedor/estoque — criar + executar |
| **Inventário** | abrir contagem → conferir → fechar (gera ajustes) |
| **EPI** | ficha de entrega por colaborador (CA + validade), baixa do estoque, devolver; alerta de vencido |
| **Ferramentaria** | cadastro (patrimônio/estado/calibração), **emprestar→devolver** por colaborador, atraso, manutenção |

**Gestão** (engenheiro/gestor, supervisão):

| Aba | Cobre |
|---|---|
| **Curva ABC** | classifica itens A/B/C por valor (Pareto), resumo por classe, tabela com % acumulado |
| **Custo por obra** | **Orçado × Aplicado** por obra/etapa, ambos reais — o orçado vem do orçamento aprovado vigente ([Orçamento](moduloorcamento.md)), com saldo e marca de estouro |
| **Giro & Ruptura** | valor imobilizado, itens em ruptura (com Repor→Demanda); giro histórico → Esfera de Rede |
| **Esfera de Rede** | 🔒 teaser (RFQ automática, benchmark de giro, marketplace de ocioso) — sem feature de rede |

### Sub-fatias (histórico)

| Sub-fatia | Entrega |
|---|---|
| **SIL.0** | app [catalogo](catalogo.md) + `Item`/composição + migração do `Produto` + repontar o SCM |
| **SIL.1–3** | núcleo de estoque + logística (requisição/transferência/devolução/lote/inventário) + integrações vivas |
| **SIL.4** | frontend `LogisticaPage` (Malha, página única) |
| **SIL.5** | IAM (`sil` + persona `almoxarife`) · rebuild imagens · re-seed |
| **SIL.6 (v2)** | construtora-native: **EPI/NR-6**, **ferramentaria** (comodato+calibração), **apropriação por etapa**, **curva ABC**, **orçado×aplicado**, reestruturação **Operação×Gestão** + drill-downs |

## Status / pendências

Status vivo no [roadmap](../roadmap.md).
