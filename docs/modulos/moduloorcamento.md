# Orçamento — Planilha orçamentária e controle de custo da obra (`moduloorcamento`) 📋

> **Planta de desenho planejado.** App **ainda não implementado**; esta planta é o **alvo**, escrito
> a partir de pesquisa da prática do setor (§2) e da fundação que os módulos anteriores já
> deixaram pronta (§3). Nasce do SIL v2: a aba **Custo por obra (Orçado × Aplicado)** já entrega o
> lado **aplicado** e mostra o **orçado** como *"em breve"* — este módulo preenche esse lado. Sem
> status/datas (o status vive no [roadmap](../roadmap.md)); as **decisões de rumo abertas** estão em §12.

## 1. O que é

O **orçamento da obra**: a **planilha orçamentária** (EAP/etapas × serviços × insumos) com
quantidade e custo previstos, que vira a **régua** contra a qual o realizado é medido. Fecha o
triângulo do controle físico-financeiro da construção:

```
ORÇADO (moduloorcamento) → COMPROMETIDO (SCM) → ESTOCADO (SIL) → APLICADO (SIL) → REALIZADO (ERP)
  previsto na planilha      pedido colocado       saldo valorado    consumido na etapa   pago/liquidado
```

O SGI já tem quatro dos cinco elos. Falta o primeiro — a **referência**. Sem ele o sistema informa
quanto a obra gastou, mas não a única pergunta que o dono da obra faz: **estamos estourando?**

## 2. A prática do mercado (pesquisa)

### 2.1 O que os softwares de orçamento fazem (ORSE, OrçaFascio, Vigha, i9, AltoQi)

O núcleo é o mesmo em todos, e é **composição de custo**, não linha de planilha:

| Peça | O que é | Nota |
|---|---|---|
| **Bases referenciais** | SINAPI (Caixa+IBGE, mensal, gratuita, por estado, com composições **analíticas** e **sintéticas**), ORSE (Sergipe, ~9 mil insumos, alinhada ao manual SINAPI), SICRO (rodovias), SEINFRA, SEDOP, TCPO (privada) | OrçaFascio anuncia **+20 bases / 87 mil composições**; o insumo tem código da fonte |
| **Composição analítica** | serviço → insumos (material + mão de obra + equipamento) com **coeficiente** de consumo/produtividade; composições auxiliares aninhadas | é o que dá rastreabilidade: o preço tem *memória de cálculo* |
| **Encargos sociais** | percentual sobre mão de obra, por estado, **onerado × desonerado**, regime Sistema S | muda o custo unitário de toda composição com mão de obra |
| **BDI** | Benefícios e Despesas Indiretas — taxa sobre o custo direto que forma o **preço de venda** | administração central, risco, tributos, lucro |
| **Curva ABC** | ranking dos itens por peso no custo (A ≈ 80%) | onde vale negociar |
| **Cronograma físico-financeiro / Curva S** | distribuição do custo no tempo por etapa → desembolso mês a mês, acumulado em "S" | é a ponte com o financeiro |
| **Revisões** | etiquetas de revisão, versão do orçamento, **reorçamento** por mudança de escopo/método/mercado | licitação e aditivo exigem histórico |
| **Saídas** | 14+ relatórios, XLSX, proposta para pregão, memória de cálculo | |
| **IA** | sugestão de composição/insumo (a "Sofia" do OrçaFascio) | acelera a montagem, não decide |

### 2.2 O que as grandes construtoras fazem (Sienge — 80 das 100 maiores)

O software de orçamento *monta* o orçamento; o ERP da construtora **controla contra ele**. As peças
que aparecem no topo do mercado e que **não** existem num orçamentista puro:

- **Orçado × comprometido × realizado numa só tela**, para agir no desvio — `comprometido` é o
  pedido de compra já colocado, dinheiro que ainda não saiu mas já foi decidido. É a métrica que
  antecipa o estouro em vez de constatá-lo.
- **Orçamento vinculado ao planejamento**: o orçamento é importado pelo planejamento e cada custo
  amarra a um serviço do cronograma; **medições** de avanço físico atualizam o previsto × realizado.
- **Tipos por estágio de maturidade do projeto**: **paramétrico** (R$/m² via CUB do Sinduscon,
  margem de 10–20%, para viabilidade/estudo de massa, antes de haver projeto) → **estimado** →
  **executivo/meta** (discriminado, é o que se controla) → **reorçamento**.
- **Incorporação**: os **8 quadros da NBR 12721** (áreas reais/equivalentes, custo global via CUB,
  fração ideal) são condição de registro do memorial de incorporação em cartório.

### 2.3 O que o SGI tem e um orçamentista puro não tem

É daqui que sai o diferencial do módulo — não de reimplementar o OrçaFascio:

| Vantagem | De onde vem |
|---|---|
| **Preço real praticado**, não preço de tabela | `Proposta`/`ItemProposta` e `PedidoCompra` do [SCM](moduloscm.md) — o que os fornecedores *daquela* construtora realmente cobraram |
| **Custo médio ponderado móvel** do insumo em estoque | [SIL](modulosil.md) — valoração real, não referencial |
| **Aplicado por obra e etapa** | SIL (`MovimentacaoEstoque.etapa`, `Requisicao.etapa`) — o consumo já é apropriado |
| **Realizado financeiro** | `ContaPagar`/`Transacao` do [ERP](moduloerp.md), com centro de custo e rateio |
| **Avanço físico** | `EtapaObra.percentual_conclusao` — a curva S real sem depender de módulo novo |
| **Benchmark entre empresas** (depois) | custo/m² anônimo da rede — [expansão E4](../expansão/06-dados-ia-automacao.md) |

> **Consequência de desenho:** o orçamento do SGI nasce **calibrável pelo histórico da própria
> empresa**. A base oficial (SINAPI/ORSE) é o ponto de partida de quem não tem histórico; o preço
> real do SCM é o que torna o orçamento honesto no segundo ano de uso. Nenhum orçamentista puro
> consegue isso, porque não vê as compras.

## 3. Fundação já pronta (o módulo não começa do zero)

| Já existe | Onde | Serve para |
|---|---|---|
| `catalogo.Item` com `tipo` (material/serviço/equipamento/composição) | [catalogo.md](catalogo.md) | o **que** se orça é o mesmo item que o SCM compra e o SIL estoca — zero tradução |
| `Item.codigo_referencia` + `Item.fonte_referencia` (`sinapi`/`tcpo`/`propria`) | `catalogo/models.py` | amarrar o item à base oficial (seam criado **para** este módulo) |
| `catalogo.ComponenteComposicao` (`item_pai`, `item_filho`, `coeficiente`) | `catalogo/models.py` | **a composição analítica já é modelada** — explosão de insumos e curva ABC herdam |
| `obras.EtapaObra` (`ordem`, `percentual_conclusao`) | `obras/models.py` | a EAP e o avanço físico para a curva S |
| `GET /api/sil/aplicado/` devolvendo `{obra, etapa, item, aplicado, orcado: null}` | `modulosil/views.py` | o **seam** que este módulo preenche |
| Aba **Custo por obra** do SIL renderizando "Orçado — em breve" | `modules/sil/tabs/` | a primeira tela que ganha valor no dia 1 |

**Armadilha registrada:** `EtapaObra.orcamento_previsto` (Decimal solto, hoje preenchido à mão) é um
"orçado por etapa" ingênuo que **antecede** este módulo. Ao implementar, decidir explicitamente:
vira **derivado** (somatório do `Orcamento` aprovado, read-only) ou é aposentado. Deixar os dois
caminhos gravando o mesmo número é garantia de divergência.

## 4. Modelos

### 4.1 Base referencial de plataforma (globais, sem tenant)

| Modelo | Papel |
|---|---|
| `BaseReferencial` | Uma **publicação**: fonte × UF × mês × regime de encargos (ex.: "SINAPI SP 07/2026 desonerado"). A granularidade é a publicação, não a base, porque orçamento tem data-base e onerado/desonerado muda o custo de toda composição com mão de obra |
| `InsumoReferencia` | Linha da publicação — **insumo** (material/mão de obra/equipamento) ou **composição**, discriminados por `tipo`, como a própria SINAPI publica |
| `ComposicaoReferenciaItem` | Linha **analítica**: composição → filho + `coeficiente`. O filho pode ser outra composição (auxiliares aninhadas) |

**Escrita só por comando** — `manage.py importar_base_referencial`, que aceita `.xlsx` e `.csv`,
**detecta o cabeçalho por sinônimos** (os arquivos oficiais mudam de layout entre publicações),
aceita mapeamento manual (`--colunas "codigo=1,…"`), é **idempotente** (reimportar atualiza preço
sem duplicar nem quebrar FK) e tem `--dry-run`. Duas armadilhas do dado brasileiro já tratadas:
número em `1.234,56` e delimitador `;` — o `csv.Sniffer` elege a **vírgula decimal** como separador
e parte a coluna de preço em duas, sem erro nenhum, então a preferência por `;` é fixa.

**API read-only** em `/api/orcamento/`: `bases/`, `referencias/` (busca server-side por código e
descrição — ninguém navega 80 mil linhas), `referencias/{id}/composicao/` (analítica com a parcela
de custo de cada insumo = memória de cálculo), `bases-resumo/` e o verbo `referencias/{id}/adotar/`
(+ `adotar-lote/`).

### 4.2 Orçamento do tenant (tenant-scoped, RLS fail-closed)

| Modelo | Papel |
|---|---|
| `Orcamento` | Orçamento de uma **obra**, **versionado**: `versao` + `orcamento_origem`, `status` (rascunho→aprovado→superado/cancelado), data-base, base referencial, regime de encargos, encargos (%), **BDI** (%), totais desnormalizados |
| `ItemOrcado` | Linha da planilha, nó da **árvore EAP** (`pai`, `codigo_eap`, `tipo_linha` sintético×analítico): `etapa` (`obras.EtapaObra`), `item` (`catalogo.Item`) e o **snapshot** (descrição, unidade, quantidade, custo unitário, fonte, código na fonte, data-base) |
| `RevisaoOrcamento` | Trilha da revisão: tipo (aditivo/supressão/reequilíbrio/atualização/correção), motivo, valores das duas pontas — o histórico que licitação e contrato exigem |
| `ComposicaoBDI` | BDI **analítico** (Acórdão 2622/2013-TCU): AC, seguro, risco, garantia, despesas financeiras, lucro e tributos (PIS/COFINS/ISS/CPRB) → percentual derivado. Um por orçamento como `padrao`, outros p/ **BDI diferenciado** por linha |
| `ItemOrcadoInsumo` | **Memória de cálculo**: a composição explodida em folhas, com coeficiente acumulado, `categoria` (material/mão de obra/equipamento) e custo no serviço |
| `ParcelaEtapa` | Célula do cronograma: etapa × mês × percentual → valor previsto, curva S e desembolso |
| `ParametroObra` | Orçamento **paramétrico**: `projeto_padrao` (R-1…GI), CUB da data-base, áreas real e equivalente, adicionais que o CUB não cobre |
| `PavimentoObra` · `UnidadeAutonoma` · `MemorialNBR` | Base dos quadros da **NBR 12721** — áreas por pavimento, unidades autônomas (coeficiente de proporcionalidade **e** fração ideal, que não são a mesma coisa) e os memoriais descritivos dos quadros V–VIII |

**A versão é numerada pelo servidor, nunca pelo cliente.** `versao` é read-only na API e a unicidade
é `(obra, versao)`; os três caminhos que criam orçamento — POST, `revisar_orcamento` e
`duplicar_orcamento` — pedem o próximo número a `planilha.proxima_versao(obra_id)`. Logo a segunda
planilha de uma obra nasce **v2**: é o **reorçamento** (escopo/método/mercado mudaram e se orça do
zero), irmão da revisão, que copia a planilha aprovada e exige motivo.

Verbos de decisão (não CRUD): **aprovar** orçamento (congela a régua), **revisar** (nova versão com
trilha), **explodir composição** (serviço → insumos, usando `ComponenteComposicao`), **precificar
pelo histórico** (puxa o preço real do SCM/custo médio do SIL no lugar do referencial),
**distribuir no cronograma**, **calcular coeficientes** e **ratear** (NBR 12721).
Falta: **gerar demanda de compra** (linha orçada → `Demanda` do SCM) — ver §7.

### 4.3 Organização dos serviços

O módulo tem lógica demais para um `services.py` só. Os módulos são achatados na raiz do app
(não é pacote), separados por **concern**, não por tamanho:

| Arquivo | Responsabilidade |
|---|---|
| `services.py` | as duas travessias de catálogo: base referencial → `catalogo.Item` (adoção) e `catalogo.Item` → linha da planilha (snapshot) |
| `planilha.py` | recálculo bottom-up, numeração EAP, aprovação, revisão, orçado por etapa (o seam do SIL) |
| `precificacao.py` | BDI do TCU, explosão da composição, encargos, curva ABC, preço real do SCM/SIL |
| `controle.py` | quatro colunas, cronograma, curva S |
| `nbr12721.py` | paramétrico por CUB e os oito quadros |

## 5. A tela que justifica o módulo — as quatro colunas

Por obra, etapa e item, numa só tela (o que o topo do mercado vende):

| Coluna | Pergunta que responde | Fonte |
|---|---|---|
| **Orçado** | quanto eu planejei gastar? | `Orcamento` aprovado vigente da obra |
| **Comprometido** | quanto eu já me obriguei a pagar? | `PedidoCompra` do SCM, obra via centro de custo |
| **Aplicado** | quanto já virou obra de fato? | `MovimentacaoEstoque` de saída por obra+etapa, a custo (SIL) |
| **Realizado** | quanto já saiu do caixa? | `ContaPagar` alcançada pelo `conta_pagar_ref` do pedido (ERP) |

As quatro **não se somam** — são quatro ângulos sobre o mesmo dinheiro, e é a distância entre elas
que informa: comprometido acima do orçado é estouro contratado antes de acontecer; aplicado muito
acima do realizado é passivo a pagar; realizado acima do aplicado é adiantamento a fornecedor.

Derivados: **saldo orçamentário** (orçado − comprometido, porque o que já foi pedido não está mais
disponível), **% consumido** e **alerta de estouro**. O confronto por etapa (orçado × aplicado) vive
no `aplicado/` do SIL, que apropria movimentação na mesma dimensão.

Ao lado delas, `orcamentos/{id}/por-categoria/` responde **de que natureza é o custo** (material × mão
de obra × equipamento) somando `ItemOrcadoInsumo` × quantidade da linha-pai. Como só enxerga linha
**explodida**, a resposta declara `cobertura_pct`: um orçamento com 10% das linhas abertas mostraria
um gráfico convincente e errado se ela não estivesse lá.

> **Limite da coluna "realizado".** O `moduloerp` amarra despesa a **empreendimento**, não a obra
> (`ContaPagar.empreendimento`, `CentroCusto` do ERP idem). O único vínculo preciso com a obra é
> pelo SCM (`PedidoCompra.conta_pagar_ref`), então *realizado* cobre **o que passou por pedido de
> compra**; lançamento feito direto no ERP não é rateado por aproximação. A resposta declara isso em
> `realizado_cobertura`/`nota_realizado`. Fechar a lacuna é a fatia **D.1.4** do ERP.

## 6. Integrações (o "tudo se conecta")

| Conecta com | Como |
|---|---|
| [SIL](modulosil.md) | `orcado`/`saldo`/`estourado` no `GET /api/sil/aplicado/`, do orçamento aprovado vigente, confrontando **custo direto** (material sai a custo; comparar com preço+BDI faria toda obra parecer economia). Import tardio e tolerante: sem o módulo assinado, `orcado` segue `None`. Curva ABC do orçado usa a mesma convenção de classe do ABC do consumo |
| [SCM](moduloscm.md) | **comprometido** por obra (pedido → centro de custo → obra); e o caminho de volta: `preco-real/` traz o preço médio pago e `aplicar-preco-real/` o adota no lugar do referencial. Falta: compra nascer da planilha (linha orçada → `Demanda`) |
| [moduloerp](moduloerp.md) | **realizado** pela `ContaPagar` alcançada do pedido (ver o limite em §5); a curva S e o desembolso previsto alimentam a **DRE por obra** (D.1.4) e o fluxo de caixa projetado |
| [obras](obras.md) | planilha por obra/etapa (EAP); `percentual_conclusao` pondera o avanço físico da curva S |
| [empreendimentos](empreendimentos.md) | custo global do empreendimento; paramétrico na viabilidade; NBR 12721 (se entrar no escopo) |
| [catalogo](catalogo.md) | item e composição; `fonte_referencia` precisa ganhar ORSE/SICRO/SEINFRA se as bases entrarem |
| APS (📦 futuro) | o cronograma financeiro daqui é a semente do cronograma físico do APS — o Gantt/linha de balanço e o avanço medido são **de lá**, não daqui |

## 7. Fronteira do módulo (o que ele **não** faz)

- **Não** é planejamento: Gantt, linha de balanço, caminho crítico e rede de precedências são do
  **APS**. Aqui a dimensão tempo existe só como **distribuição de custo no tempo** (curva S).
- **Não** é medição de empreiteiro: boletim de medição, retenção e liberação de pagamento são do
  módulo **Medições & empreiteiros** ([mapa §2](../expansão/03-mapa-de-modulos.md)).
- **Não** é levantamento de quantitativos por projeto: extração de quantidade de modelo BIM é da
  **Central BIM** (5D, H3). Aqui a quantidade é digitada/importada, com memória de cálculo.

## 8. Frontend — a régua de módulo na identidade Malha

Segue a [régua §1.6](../frontend.md) (cockpit + loop + ferramenta de decisão + dados honestos +
integração visível + seams), na linguagem [Malha](../identidade-visual.md): **Edição Construtora →
estágio Construir → acento Âmbar Obra `#E79A22`**, um acento por tela, número em **mono tabular**
(`Num`/`KpiCard`), master-detail in-place, claro+escuro, ações gateadas por permissão.

**Hub + páginas** (o módulo é grande demais para caber numa página só, ao contrário do SIL): a raiz
`/app/orcamento` é um **hub-dashboard** com a fila de decisão e a seleção das páginas; cada página tem
um **seletor horizontal** próprio no topo. Catálogo único das páginas em
[`paginas.ts`](../../frontend/src/modules/orcamento/paginas.ts) — hub e moldura leem de lá.

| Rota | Página | Quem | O que resolve |
|---|---|---|---|
| `/app/orcamento` | **Hub** | todos | fila "requer sua decisão" (estouro, obra sem régua, rascunho parado), KPIs das quatro colunas, bases disponíveis |
| `…/orcar` | **Orçar** | orçamentista/engenheiro | a **grade**: árvore EAP → etapa → serviço → insumos, explosão de composição, precificar (referencial × histórico real), encargos/BDI, memória de cálculo. Sub-seletor sintético × analítico |
| `…/controlar` | **Controlar** | dono da obra / diretoria | as **quatro colunas** com drill-down, curva ABC, composição por natureza do insumo, curva S. Sub-seletor: colunas · ABC · composição |
| `…/cronograma` | **Cronograma** | planejador | grade etapa × competência com percentual editável, distribuição linear de partida, desembolso previsto, curva S |
| `…/bases` | **Bases & bancos** | orçamentista | bases-mãe travadas (exploração + adoção em lote), bancos próprios do tenant, importações |
| `…/incorporacao` | **Incorporação** | incorporador | paramétrico por CUB e os quadros da NBR 12721 |

**A grade é o módulo.** O padrão do setor (OrçaFascio, Volare, Sienge) é **edição na célula**, não
formulário por linha: Tab/Enter/setas/F2, digitar-para-começar, **colar bloco do Excel** e inserir item
por uma janela com **três origens** (base oficial · catálogo da empresa · criar novo). Digitar 400
quantidades num drawer é inviável, e é isso que o orçamentista faz o dia inteiro. A grade usa janela
virtual — a planilha analítica passa de mil linhas com facilidade.

**Gráficos.** As cores da Malha reprovaram na validação de paleta categórica (croma baixa: teal e verde
lidos como cinza; vermelho × âmbar indistinguíveis sob deuteranopia). Em vez de matizes fora da marca,
as **formas** mudaram: magnitude vira barra de um matiz, ABC vira rampa ordinal do acento, curva S vira
referência tracejada + acento. As três séries que restaram (comprometido/aplicado/realizado) passam nos
dois temas. Tokens em [`graficos.tsx`](../../frontend/src/modules/orcamento/components/graficos.tsx).

**Fila "requer sua decisão"** do cockpit: etapas com comprometido acima do orçado, itens sem preço,
orçamento em rascunho sem aprovação, revisão pendente, item orçado cujo preço real do SCM divergiu
acima do limite. **Integração visível:** cada linha orçada leva ao `Pedido` do SCM, ao consumo do SIL
e à `ContaPagar` do ERP — referência clicável, não número solto.

## 9. Seams de expansão (inertes no lançamento)

- **Benchmark de custo/m² e de preço de insumo** entre tenants (anônimo, opt-in) — [E4](../expansão/06-dados-ia-automacao.md);
  exige `ParametroObra` (área equivalente + padrão) desde já para o número ser comparável.
- **Previsão de estouro por IA** (orçado × realizado × preços da rede) — [06](../expansão/06-dados-ia-automacao.md) §Orçamento+SCM.
- **Banco de composições da rede**: composição própria publicável (`ref_externa`/`origem_tenant`,
  mesmo padrão do SCM) → repositório compartilhado de composições calibradas por preço real.
- **BIM 5D**: `ItemOrcado` preparado para receber `id` de elemento do modelo (quantitativo automático).
- **Edição Empreiteiro**: orçamento vira **proposta** ao construtor — o mesmo motor com o BDI do
  empreiteiro; a graduação é publicação, não módulo novo.

## 10. Contrato de módulo

Entitlement próprio **`orcamento`** (`RequireModule("orcamento")`) e **9 permissões** no catálogo da
IAM ([acesso-e-permissoes.md §7](../acesso-e-permissoes.md)): `orcamento.base.view`/`.adotar`,
`orcamento.orcamento.view`/`.edit`/`.aprovar`/`.revisar`, `orcamento.item.view`/`.edit` e
`orcamento.relatorio.view`. Todo model **do tenant** herda `TenantScopedModel` com **RLS
fail-closed** (a base referencial é a exceção documentada em §11.1).

Duas separações deliberadas de permissão:

- **adotar ≠ editar a base.** A base não é editável por ninguém, então não existe
  `orcamento.base.edit`; adotar escreve no catálogo do **tenant** e tem permissão própria. Por isso
  os viewsets da base declaram `required_permission` fixa em vez de `required_resource` — o atalho do
  recurso derivaria um `.edit` fantasma e devolveria **403 mentiroso** onde o certo é **405**.
- **aprovar ≠ editar o orçamento.** Congelar a régua de custo é decisão de quem responde pela obra,
  não de quem digita a planilha — a persona `orcamentista` edita mas não aprova.

Persona de fábrica **`orcamentista`**: orçamento + `cadastro.item.*` + leitura de obra/empreendimento
e do que dá **custo real** (`scm.oferta.view`, `scm.pedido.view`, `sil.saldo.view`,
`sil.relatorio.view`). Como o catálogo da IAM vive na imagem, o módulo exige rebuild de `sgi-iam` +
re-seed.

## 11. Decisões de rumo (tomadas pelo dono do produto)

1. **Bases referenciais entram desde o início** — SINAPI e ORSE importadas por comando, não só banco
   próprio. Consequências de desenho em §11.1.
2. **Composição analítica, faseada** — a planilha nasce em etapa × item; explosão de composição,
   encargos (onerado/desonerado) e BDI vêm na fatia seguinte, reusando `catalogo.ComponenteComposicao`.
3. **Curva S financeira nasce aqui** — distribuição do custo no tempo e desembolso previsto, ponderados
   por `EtapaObra.percentual_conclusao`. Gantt, precedências e avanço medido seguem sendo do APS.
4. **Incorporação entra completa** — orçamento **paramétrico** (CUB, R$/m², área equivalente) *e* os
   **8 quadros da NBR 12721** (condição de registro do memorial em cartório).

### 11.1 A base referencial é de PLATAFORMA, não do tenant

Decisão que decorre de (1): SINAPI publica **~87 mil composições por estado, mês a mês**. Replicar isso
dentro de `catalogo.Item` (que é `TenantScopedModel`) significaria dezenas de milhares de linhas por
empresa, de dado que **não é da empresa** — é dado público do governo. Então:

- **Tabelas globais, sem tenant e sem RLS** (`BaseReferencial`, `InsumoReferencia`,
  `ComposicaoReferenciaItem`): catálogo público, versionado por **fonte × UF × mês × onerado/desonerado**,
  gravado só por comando de importação e **read-only** na API. Não são dados de cliente, então a RLS
  fail-closed não se aplica — e é a única exceção consciente à regra de que todo model de negócio é
  tenant-scoped (a leitura segue gateada pelo entitlement `orcamento`).
- **Adoção sob demanda:** usar um item da base no orçamento **adota** aquele item no catálogo do
  tenant — cria o `catalogo.Item` com `codigo_referencia` + `fonte_referencia` preenchidos (o seam que
  o catálogo já traz) e, quando for composição, os `ComponenteComposicao`. Assim entra no catálogo da
  empresa **só o que ela usa**, e o item orçado é o mesmo que o SCM compra e o SIL estoca.
- **`Item.Fonte` precisa crescer:** hoje só `sinapi`/`tcpo`/`propria`; ganha `orse`, `sicro`,
  `seinfra`, `sedop` (migration no `catalogo`).
- **`ItemOrcado` guarda snapshot** (descrição, unidade, custo unitário e data-base usados): orçamento
  aprovado é régua histórica — não muda porque a base do mês seguinte mudou ou porque alguém editou o
  item no catálogo.

## 12. Sub-fatias

| Fatia | Escopo |
|---|---|
| **ORC.0** | **Fundação:** entitlement `orcamento` + permissões + persona `orcamentista` na IAM; base referencial de plataforma (`BaseReferencial`/`InsumoReferencia`/`ComposicaoReferenciaItem`), comando `importar_base_referencial` (SINAPI/ORSE), `Item.Fonte` ampliado e verbo **adotar no catálogo** |
| **ORC.1** | `Orcamento` + `ItemOrcado` (com snapshot) + `RevisaoOrcamento`, RLS fail-closed, verbos aprovar/revisar; **fecha o seam do SIL** (`orcado` real no `aplicado/`, alerta de estouro) |
| **ORC.2** | Composição analítica (explosão), encargos onerado/desonerado, **BDI**, curva ABC do orçado, memória de cálculo, precificar pelo histórico real do SCM/SIL |
| **ORC.3** | **Quatro colunas** (orçado × comprometido × aplicado × realizado) + cronograma financeiro e **curva S** (`ParcelaEtapa`) |
| **ORC.4** | **Paramétrico** (`ParametroObra`, CUB, R$/m²) + **quadros da NBR 12721** (I–IV calculados; V–VIII descritivos) |
| **ORC.5** | Frontend Malha (hub + 5 páginas) com integração clicável SCM/SIL/ERP |
| **ORC.5b** | Bancos próprios do tenant, importação com conferência, duplicar/copiar, reprecificação e exportação |
| **ORC.6** | E2E vivo pelo gateway + sincronização de docs |

### 12.3 Onde o ORC.5b mora no código

| Peça | Arquivo |
|---|---|
| Bancos da empresa: adoção, trava, cópia da base pública | [bancos.py](../../backend/moduloorcamento/bancos.py) |
| **Importação/exportação tabular: a declaração** | [impexp.py](../../backend/moduloorcamento/impexp.py) — o motor é o [funcoesimpexp](funcoesimpexp.md) |
| Cabeçalho da analítica, só para o comando | [leitura.py](../../backend/moduloorcamento/leitura.py) |
| Reprecificação: prévia, aplicar, desfazer | [reprecificacao.py](../../backend/moduloorcamento/reprecificacao.py) |
| Duplicar orçamento e copiar linhas | [duplicacao.py](../../backend/moduloorcamento/duplicacao.py) |
| Exportação de **documento** (XLSX/PDF) | [exportacao.py](../../backend/moduloorcamento/exportacao.py) + [planilha.html](../../backend/moduloorcamento/templates/moduloorcamento/planilha.html) |
| Testes da fatia | [test_orc5b.py](../../backend/moduloorcamento/test_orc5b.py) |
| Dado de demonstração | `seed_orcamento` em [seed_demo_data.py](../../backend/seed_demo_data.py) |

### 12.4 A importação saiu do módulo (IE.1)

O ORC.5b resolveu importação de preço com conferência linha a linha, teto de plano em duas grandezas,
base-mãe do dono da plataforma e lote desfazível — tudo dentro de `moduloorcamento/`. **Isso agora
mora no motor de plataforma**, e o módulo só declara.

| Antes (ORC.5b) | Depois (IE.1) |
|---|---|
| `moduloorcamento/importacao.py` | a declaração em [impexp.py](../../backend/moduloorcamento/impexp.py) |
| `ImportacaoPreco` / `LinhaImportacao` | `funcoesimpexp.Importacao` / `LinhaImportacao` |
| `/api/orcamento/importacoes/**` | `/api/impexp/orcamento.banco_preco/**` |
| `ConferenciaImportacao.tsx` do módulo | `<WizardImportacao>` do kit Malha |
| aliases de preço em `leitura.py` | `aliases` das colunas declaradas (a fonte única da R2) |

**Três recursos declarados:** `orcamento.banco_preco` (banco da empresa), `orcamento.base_referencial`
(publicação pública, só o dono da plataforma) e `orcamento.planilha` (as linhas da EAP).

**O que não migrou, e por quê.** A planilha orçamentária formatada (XLSX com árvore EAP indentada e
totais, PDF para assinar), a curva ABC e o cronograma continuam em
[exportacao.py](../../backend/moduloorcamento/exportacao.py). Aquilo não é exportação tabular — é
**peça de documento**, com hierarquia, subtotal e cabeçalho técnico. Espremer no escritor genérico de
colunas perderia função, e a régua do IE.1 é migrar *sem perder função*.

O gate mudou de forma junto: onde havia uma permissão de ação (`orcamento.base.adotar`), agora vale a
regra §3 do motor — **acesso total ou nada**. Quem tem só `orcamento.base.view` não vê o botão.

**Armadilha registrada.** `RequirePermission` aceita `permission_map` com as chaves **`view`/`write`**,
não nomes de método HTTP. Um `{"GET": …}` é dicionário truthy cujo `.get("view")` devolve `None`, e
`has_permission` trata exigência `None` como "não exige" — ou seja, **desliga o gate em silêncio**. Foi o
que aconteceu na 1ª versão dos cinco ViewSets do ORC.5b e a suíte ficou verde, porque nenhum teste exercia
o caminho negado. A classe do defeito é a do **D5**; a regressão vive em
`test_orc5b.py::GateDeApiTests`.

### 12.2 ORC.5b — o que o rumo do dono definiu (25/07/2026)

- **Banco próprio = tabela separada do tenant.** A `BaseReferencial` pública fica como está (global,
  sem tenant, sem RLS — §11.1 intocada) e nasce um `BancoPreco` `TenantScopedModel` com RLS
  fail-closed padrão. **Duas tabelas, mesmo Postgres** — sem exceção nova à política de isolamento.
  O banco é **da empresa, com obra opcional** (a tabela da prefeitura serve várias obras), tem
  data-base própria e **trava** de edição. Pastas de composição organizam por obra/tipo dentro dele.
- **Uma busca só.** O seletor de base da planilha lista as duas origens juntas, com cadeado no que é
  base-mãe: origem é atributo, não lugar.
- **Importação** por planilha XLSX/CSV, API de sincronização e PDF — os três com **conferência linha a
  linha** (confirmar tudo · confirmar seleção · negar tudo) antes de gravar. Superuser importa
  base-mãe (vale para todos os tenants); usuário comum importa para os bancos do próprio tenant.
  **Teto do plano** em duas grandezas: linhas por importação e linhas acumuladas no tenant — knobs em
  [payment/](../../payment/README.md), não no código de engenharia.
- **Reprecificar ≠ versionar.** Trocar a data-base é operação com **prévia item a item** (preço velho →
  novo, Δ, efeito no total, seleção por linha) sobre **qualquer publicação**, para frente ou para trás
  — o edital manda na data-base e ela costuma ser passada. Em **rascunho** grava um lote desfazível
  (histórico com "desfazer" que restaura os preços anteriores); em **aprovado** obriga a revisão,
  porque `exigir_editavel` já impede escrita em régua congelada. Versão continua significando
  **aditivo contratual**, não troca de tabela de preço.
- **Importar/exportar** tem os pontos de entrada na tela desde já, em estado "em construção" — o
  backend vem depois, como função separada.

### 12.1 Permissões: as 9 do catálogo bastam até aqui

ORC.1–ORC.4 **não criaram permissão nova**. Cronograma e NBR 12721 reusam as existentes
(`orcamento.orcamento.edit` para mexer no cronograma, `orcamento.item.edit` para áreas/unidades,
`orcamento.relatorio.view` para os quadros, curva ABC, curva S e as quatro colunas). O motivo é de
operação, não de modelagem: permissão nova exige **rebuild da imagem `sgi-iam` + re-seed**, e o
recorte destas fatias não pediu granularidade que as 9 não dessem. Se o frontend (ORC.5) mostrar que
"quem monta a planilha" e "quem planeja o cronograma" são papéis distintos na prática, aí sim vale
`orcamento.cronograma.*` e `orcamento.nbr.*`.

## 13. Status

Ver [roadmap](../roadmap.md).
