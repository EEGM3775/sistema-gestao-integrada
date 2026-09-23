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
| `BaseReferencial` | Uma **publicação**: fonte × UF × mês × regime de encargos × **variante** (ex.: "SINAPI SP 07/2026 desonerado"). A granularidade é a publicação, não a base, porque orçamento tem data-base e onerado/desonerado muda o custo de toda composição com mão de obra. A `variante` é o quinto eixo e fica **vazia em quase toda fonte** — existe porque a EMBASA publica, para o mesmo semestre e o mesmo regime, uma tabela por escopo × convenção coletiva, com os mesmos códigos e preços diferentes (§12.8) |
| `InsumoReferencia` | Linha da publicação — **insumo** (material/mão de obra/equipamento) ou **composição**, discriminados por `tipo`, como a própria SINAPI publica |
| `ComposicaoReferenciaItem` | Linha **analítica**: composição → filho + `coeficiente`. O filho pode ser outra composição (auxiliares aninhadas) |

**Escrita só pela mão do dono da plataforma**, por duas portas e um motor: `manage.py
importar_base_referencial` (ORC.0, o formato longo e as fontes sem leitor) e a **carga** da ORC.8
(o arquivo nacional, por botão ou agendamento — §12.7). As duas gravam pelas mesmas funções. O
comando aceita `.xlsx` e `.csv`,
**detecta o cabeçalho por sinônimos** (os arquivos oficiais mudam de layout entre publicações),
aceita mapeamento manual (`--colunas "codigo=1,…"`), é **idempotente** (reimportar atualiza preço
sem duplicar nem quebrar FK) e tem `--dry-run`. Duas armadilhas do dado brasileiro já tratadas:
número em `1.234,56` e delimitador `;` — o `csv.Sniffer` elege a **vírgula decimal** como separador
e parte a coluna de preço em duas, sem erro nenhum, então a preferência por `;` é fixa.

**API read-only** em `/api/orcamento/`: `bases/`, `referencias/` (busca server-side por código e
descrição, **paginada** — ninguém navega 80 mil linhas de uma vez, e o teto de página é
`PAGINA_MAXIMA["orcamento"]`), `referencias/{id}/composicao/` (analítica com a parcela de custo de
cada insumo = memória de cálculo), `bases-resumo/` e o verbo `referencias/{id}/adotar/`
(+ `adotar-lote/`). Paginada **não** quer dizer inalcançável: quem consome precisa oferecer o
percurso (rolagem infinita ou passa-página), porque orçamentista que não sabe o código de cor
navega pelo catálogo, não pela busca.

**Ordem é escolha de quem procura, não do arquivo.** `referencias/` aceita `ordering` por `codigo`,
`descricao` e `custo_unitario`; o padrão do model é `["base", "codigo"]`, e código de fonte oficial
não tem relação com assunto — procurar "aterro" pela numeração devolve os aterros espalhados no meio
da lista. A tela oferece as duas ordens, e a alfabética vai como `descricao,codigo`: descrição não é
única (a SINAPI publica dezenas de "CONSTRUÇÃO DE BASE E SUB-BASE…" que só diferem no fim do texto)
e, sem desempate, duas páginas do mesmo resultado podem repetir uma linha e engolir outra.

**Escolher publicação é em passos encadeados, não numa lista.** A identidade é
`fonte × UF × mês × regime`, e uma lista plana multiplica os quatro eixos: com a SINAPI de 01/2025 a
08/2026 são 27 UFs × 20 meses × 3 regimes = **1.460 opções** num `<select>`. O `SeletorDeBase`
encadeia — praça (fonte + UF) → mês → regime —, e cada caixa volta ao seu tamanho natural. Trocar de
praça preserva mês e regime quando existem na praça nova, para comparar o mesmo mês entre dois
estados sem reescolher a data. O regime é caixa própria e **não** pode ser deduzido: onerado ×
desonerado muda o custo de toda composição com mão de obra. Eixo que a fonte não publica fica
**cinza e travado**, não some — fonte de concessionária costuma ter preço único, e caixa que
desaparece muda o tamanho da linha e esconde que o eixo existe.

**A quarta caixa (`variante`) segue a mesma régua.** A EMBASA publica, para o mesmo semestre e o
mesmo regime, uma tabela por escopo (expansão · operação de água · de esgoto) × convenção coletiva,
todas com os mesmos 6.992 códigos e preços diferentes: sem ela, as seis chegariam ao fim do
encadeamento como seis linhas de nome igual. Ela mostra o rótulo que a **fonte** deu — escopo,
sindicato e a leis sociais do cabeçalho do arquivo — e fica cinza nas fontes que publicam uma
tabela só, que são todas as outras.

**`bases-resumo/` agrega por fora da lista, não com `annotate`.** Os números por publicação
(insumos, composições, quantos vieram classificados, quais classes a fonte usou) saem de duas
agregações chapadas casadas em memória por `base_id` — `Count` correlacionado na lista custaria uma
varredura da tabela de referências *por publicação*, e a base referencial cresce por mês × UF ×
regime. Servindo essas contas há o índice **parcial** `orcamento_ref_classe_idx` em
`(base, grupo) WHERE tipo='insumo'`: as perguntas de classificação só existem para insumo, e incluir
composição quadruplicaria o índice sem responder nada a mais. Tudo **derivado**, sem contador
gravado — a publicação pode ser reimportada e a tela não tem como falar de um estado que não existe
mais.

#### O arquivo oficial da SINAPI tem dois formatos, e eles não se parecem

Conhecimento caro, aprendido abrindo publicação de verdade — quem for mexer no importador precisa
dele antes de tocar em qualquer linha:

| | **Até 12/2024** | **A partir de 01/2025** |
|---|---|---|
| Distribuição | 1 ZIP **por UF × regime** (~27 × 2/mês, ~21 MB cada) | **1 ZIP nacional** por mês (~16 MB) |
| Arquivos | 3 XLSX: insumos, composições sintéticas, analítica | 1 XLSX de referência (+ mão de obra, famílias, manutenções) |
| Layout | **longo** — uma linha por item, uma coluna de preço | **largo** — abas `ISD`/`ICD`/`ISE` (insumos) e `CSD`/`CCD`/`CSE` (composições), com **as 27 UFs em colunas** |
| Regimes | no nome do arquivo (`NaoDesonerado`) | nas abas: `S`em desoneração · `C`om desoneração · `S`em `E`ncargos (este virou o regime `sem` na ORC.8 — é a base legítima do quadro analítico do ORC.7) |
| Analítica | por publicação | **nacional e única** (`Grupo · Código da Composição · Tipo Item · Código do Item · Descrição · Unidade · Coeficiente · Situação`) — coeficiente da SINAPI **não varia por UF**, só o preço |
| Classificação do insumo | ausente | coluna `Classificação`: MATERIAL, MÃO DE OBRA, EQUIPAMENTO (AQUISIÇÃO/LOCAÇÃO), ENCARGOS COMPLEMENTARES, SERVIÇOS, ESPECIAIS |

Duas regras que decorrem do formato largo e valem para qualquer leitor dele:

1. **Preço em branco numa UF significa ausência, não zero.** O próprio cabeçalho declara: *"Preço em
   branco para determinado estado significa que não houve pesquisa"*. Gravar `custo_unitario = 0`
   faria a planilha aceitar um insumo a R$ 0,00 sem ninguém perceber.
2. **`SD` = sem desoneração = regime `onerado`**; `CD` = com desoneração = `desonerado`. A dobra de
   nomenclatura é da fonte, e trocar os dois inverte o custo de toda composição com mão de obra.

A detecção de cabeçalho casa por **igualdade exata** com `ALIASES`; sinônimo que só vale para um
tipo de arquivo mora em `EXTRAS_POR_ARQUIVO` e entra **no fim** da lista do campo. O escopo não é
capricho: `CODIGO DA COMPOSICAO` é o `codigo` no sintético e o `codigo_composicao` na analítica, e
um alias global faria o campo certo ficar sem mapa num dos dois.

### 4.2 Orçamento do tenant (tenant-scoped, RLS fail-closed)

| Modelo | Papel |
|---|---|
| `Orcamento` | Orçamento de uma **obra**, **versionado**: `versao` + `orcamento_origem`, `status` (rascunho→aprovado→superado/cancelado), data-base, base referencial, regime de encargos, encargos (%), **BDI** (%), totais desnormalizados |
| `ItemOrcado` | Linha da planilha, nó da **árvore EAP** (`pai`, `codigo_eap`, `tipo_linha` sintético×analítico): `etapa` (`obras.EtapaObra`), `item` (`catalogo.Item`) e o **snapshot** (descrição, unidade, quantidade, custo unitário, fonte, código na fonte, data-base) |
| `RevisaoOrcamento` | Trilha da revisão: tipo (aditivo/supressão/reequilíbrio/atualização/correção), motivo, valores das duas pontas — o histórico que licitação e contrato exigem |
| `ComposicaoBDI` | BDI **analítico** (Acórdão 2622/2013-TCU): AC, seguro, risco, garantia, despesas financeiras, lucro e tributos (PIS/COFINS/ISS/CPRB) → percentual derivado. Um por orçamento como `padrao`, outros p/ **BDI diferenciado** por linha |
| `ItemOrcadoInsumo` | **Memória de cálculo**: a composição explodida em folhas, com coeficiente acumulado, `categoria` (material/mão de obra/equipamento) e custo no serviço |
| `ParcelaEtapa` | Célula do cronograma: etapa × mês × percentual → valor previsto, curva S e desembolso |
| `ComposicaoEncargos` · `RubricaEncargos` | O **quadro de encargos analítico**: grupos A (obrigações sobre a folha), B (recebem a incidência de A), C (indenizatórios) e D (**reincidências, derivadas** — `A×B/100` e `FGTS×aviso/100`). Unicidade por `(orçamento, tipo, regime)`: horista e mensalista convivem, e a explosão escolhe pela unidade do insumo. No desonerado a rubrica A1 **sai** do quadro (a CPP virou CPRB, que é tributo e vive no BDI) |
| `LinhaMedicao` | A **memória do quantitativo**: parciais `n × a × b × c` com sinal, ou `formula` livre. Dimensão nula é ausência, não zero. A linha com parciais tem quantidade **derivada** |
| `FormulaReajuste` · `ParcelaFormulaReajuste` | A **fórmula paramétrica do contrato** — `R = V × [a + Σpᵢ × (Iᵢ,t/Iᵢ,0)]`, cesta de índices com pesos. Reajustar ≠ reprecificar (§12.5) |
| `Reprecificacao` · `LinhaReprecificacao` | O **lote de troca de data-base**, com o preço anterior linha a linha — é o que torna o desfazer possível sem inventar versão. `descontinuado` marca a linha cujo código **sumiu da publicação de destino**: ela entra no lote para *aparecer*, com `custo_depois == custo_antes`, `selecionada=False` e nunca aplicável, nem que venha marcada no pedido. `linhas_afetadas` conta preço trocado; `linhas_descontinuadas` conta à parte, porque não são a mesma coisa |
| `ParametroObra` | Orçamento **paramétrico**: `projeto_padrao` (R-1…GI), CUB da data-base, áreas real e equivalente, adicionais que o CUB não cobre |
| `PavimentoObra` · `UnidadeAutonoma` · `MemorialNBR` | Base dos quadros da **NBR 12721** — áreas por pavimento, unidades autônomas (coeficiente de proporcionalidade **e** fração ideal, que não são a mesma coisa) e os memoriais descritivos dos quadros V–VIII |

**A base de preço é escolhível depois, e trocar a publicação arrasta a data-base junto.**
`base_referencial` é editável no cabeçalho (`PATCH` no orçamento, e o campo fica na tela "Base, BDI e
encargos") — a escolha não morre na criação, onde o padrão é *"Sem base — preço digitado à mão"*.
Quando a publicação **muda**, `OrcamentoSerializer.update` copia `data_base` e `regime_encargos`
dela, como o `create` já fazia: sem isso o cabeçalho ficaria dizendo um mês e apoiado no preço de
outro, e data-base errada não avisa, só mente. Duas exceções deliberadas: `data_base` informada na
mesma requisição **vence** (data de edital ≠ mês da publicação é caso real), e **tirar** a base não
apaga a data-base — ela sobrevive à publicação, porque o preço já congelado continua sendo de algum
mês.

Trocar a base **não reprecifica** o que já está na planilha. As linhas são fotografias, e mexer nelas
é o trabalho da `Reprecificacao`, que tem prévia, histórico e desfazer; repreçar calado num campo de
formulário passaria por cima dessa trilha. A troca muda de onde vêm os **próximos** itens, e a tela
diz isso no momento em que a escolha é feita.

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

#### A planilha não pode mentir a data-base que anuncia

A fonte **aposenta item todo mês**. Se a reprecificação pula em silêncio o código que não existe mais
no destino, a linha fica com o preço velho enquanto o cabeçalho passa a anunciar a data-base nova: a
peça que vai para a licitação diz "julho" carregando junho por dentro, **com aparência de correta** —
que é o que a torna perigosa numa auditoria. O defeito não é o número, é o silêncio.

O aviso existe em dois tempos, de propósito:

- **no lote**, enquanto se decide (a linha descontinuada aparece na prévia, marcada e não aplicável);
- **no orçamento**, depois que o lote passou — `GET /api/orcamento/orcamentos/{id}/avisos/`, as
  linhas cujo `data_base_preco` é anterior à `data_base` do cabeçalho. Fica no orçamento, e não no
  lote, porque é a **planilha** que vai para a licitação: quem a abrir meses depois não vai atrás do
  histórico de lotes.

O aviso do orçamento é **derivado, nunca gravado**. Um campo "esta linha está desatualizada" seria
uma terceira verdade a manter sincronizada com o preço e com a data-base, e dessincronizaria na
primeira reprecificação parcial. Por ser derivado ele também pega mais do que o item aposentado:
pega a linha que o operador **desmarcou** na prévia — e isso é desejado, porque para a auditoria as
duas são o mesmo defeito. Na tela, a coluna **Data-base** da grade do Orçar mostra o mesmo fato linha
a linha.

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
| `encargos.py` | o quadro A/B/C/D, o modelo de partida e o `ResolvedorEncargos` que a explosão consulta |
| `quantitativos.py` | parciais de medição e o avaliador de fórmula por **AST restrita** (sem nó de nome nem de chamada) |
| `insumos.py` | o orçamento visto **por insumo**: relação consolidada, curva ABC de insumos, composição separada nas três naturezas |
| `reajuste.py` | fator paramétrico, prévia e aplicação (em aprovado, via revisão de reequilíbrio) |
| `tasks.py` | varredura diária de base e índice atrasados — o calcanhar do módulo é dado fresco, não cálculo |

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
| [SCM](moduloscm.md) | **comprometido** por obra (pedido → centro de custo → obra); o caminho de volta: `preco-real/` traz o preço médio pago e `aplicar-preco-real/` o adota no lugar do referencial; e, desde o ORC.7, **a compra nasce da planilha** — `relacao-insumos/` daqui vira `Demanda` em rascunho pelo `POST /api/scm/demandas/do-orcamento/`, que mora **no SCM** |
| [moduloerp](moduloerp.md) | **realizado** pela `ContaPagar` alcançada do pedido (ver o limite em §5); a curva S e o desembolso previsto alimentam a **DRE por obra** (D.1.4) e o fluxo de caixa projetado |
| [obras](obras.md) | planilha por obra/etapa (EAP); `percentual_conclusao` pondera o avanço físico da curva S |
| [empreendimentos](empreendimentos.md) | custo global do empreendimento; paramétrico na viabilidade; NBR 12721 (se entrar no escopo) |
| [catalogo](catalogo.md) | item e composição; `fonte_referencia` precisa ganhar ORSE/SICRO/SEINFRA se as bases entrarem |
| PDCA (📦 futuro) | o cronograma financeiro daqui é a semente do cronograma físico do PDCA — o Gantt/linha de balanço e o avanço medido são **de lá**, não daqui |

## 7. Fronteira do módulo (o que ele **não** faz)

- **Não** é planejamento: Gantt, linha de balanço, caminho crítico e rede de precedências são do
  **PDCA**. Aqui a dimensão tempo existe só como **distribuição de custo no tempo** (curva S).
- **Não** é medição de empreiteiro: boletim de medição, retenção e liberação por avanço são do
  **PDCA** — são atos do **contrato de obra**, e o ERP é de recursos empresariais. Ele recebe o
  título líquido e paga, no mesmo molde do `PedidoCompra.conta_pagar_ref` do SCM (§13.1).
  *Decisão do dono, 17/08/2026:* **não existirá um `modulomedicao`** — o ciclo
  `orçado → medido → pago` se fecha entre módulos que já têm dono, e não num quarto.
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
| `…/orcar` | **Orçar — obras** | orçamentista/engenheiro | as obras, com quantos orçamentos cada uma tem e o valor da versão que vale |
| `…/orcar/obra/{obra}` | **Orçar — versões da obra** | orçamentista/engenheiro | as versões daquela obra (descrição, v, status, data-base, total) — onde se escolhe qual planilha abrir |
| `…/orcar/orcamento/{id}` | **Orçar — a planilha** | orçamentista/engenheiro | a **grade**: árvore EAP → etapa → serviço → insumos, explosão de composição, precificar (referencial × histórico real), encargos/BDI, memória de cálculo. Sub-seletor sintético × analítico |
| `…/encargos` | **Encargos & reajuste** | orçamentista | o **quadro A/B/C/D** (grupo D bloqueado, com a conta ao lado), a composição do BDI e a **cesta de índices** do reajuste com prévia do fator. Sub-seletor: encargos · reajuste |
| `…/controlar` | **Controlar** | dono da obra / diretoria | as **quatro colunas** com drill-down, curva ABC, **insumos** (relação + ABC de insumos + gerar demanda no SCM), composição por natureza, curva S. Sub-seletor: colunas · ABC · insumos · composição |
| `…/cronograma` | **Cronograma** | planejador | grade etapa × competência com percentual editável, distribuição linear de partida, desembolso previsto, curva S, **desembolso por insumo**. Sub-seletor: grade · curva S · insumos |
| `…/bases` | **Bases & bancos** | orçamentista / curador de preços | bases-mãe travadas (exploração + adoção em lote), bancos próprios do tenant, importações e os **tipos de item da empresa** (natureza + flags, com o padrão de cada natureza preenchido) |
| `…/incorporacao` | **Incorporação** | incorporador | paramétrico por CUB e os quadros da NBR 12721 |

**A natureza do insumo é a classificação da SINAPI, não uma adivinhação.** A publicação traz desde
01/2025 a coluna `Classificação` (MATERIAL · MÃO DE OBRA · EQUIPAMENTO · ENCARGOS COMPLEMENTARES ·
SERVIÇOS · ESPECIAIS) e é ela que a adoção lê; a unidade (`H`/`MES` → mão de obra) só decide quando a
fonte não classifica, e "ESPECIAIS"/capítulo de composição não classificam nada. O que isso conserta:
até a ORC.9 o catálogo não tinha `mao_de_obra`, o pedreiro entrava como `servico` e a precificação
lia **todo** serviço como mão de obra — logo serviço **terceirizado** levava encargo social sobre um
preço que já vem com encargo dentro. Quem corrige o que já foi adotado é
`manage.py reclassificar_itens_catalogo` (`--dry-run` mostra o de-para; sem o flag corrige o catálogo
e refaz **só os rascunhos** — planilha aprovada é régua de medição e não se mexe).

**Publicação que não classifica, e o de-para da empresa.** A coluna `Classificação` não existe nas
publicações anteriores a 01/2025: nelas todo insumo cai no plano B da unidade, e o que não é hora nem
mês é adotado como material. O sistema **declara** isso em vez de disfarçar — `bases-resumo/` devolve
`classifica_insumo` e `insumos_classificados`, o card da publicação em Bases & bancos marca a
publicação que não classifica, e o comando conta o mesmo no relatório. Para resolver sem esperar uma
publicação nova, `reclassificar_itens_catalogo --de-para arquivo.csv` aceita a classificação que a
empresa declara (`codigo;natureza[;fonte]`, rótulo publicado ou chave interna), que **vence** a da
fonte — e a discordância entre as duas sai no relatório. O que o comando **não** faz, por decisão:
deduzir natureza do texto da descrição. O de-para da SINAPI BA 10/2024 é versionado em
[`dados/`](../../backend/moduloorcamento/dados/classificacao-sinapi-ba-2024-10.csv) e um teste o
carrega, para erro de digitação não esperar o dia do uso.

**Classe que a fonte publica e o sistema não sabe ler.** A tradução classe → natureza é um de-para
por prefixo (`services.PREFIXOS_DE_CLASSE`) escrito à mão, e base de vocabulário próprio (ORSE,
SICRO, tabela de prefeitura) usa palavras que não estão nele. Antes isso era **indistinguível de
campo vazio**: os dois devolviam `None`, caíam no plano B da unidade sem uma palavra, e — pior — o
indicador `classifica_insumo` acendia **verde**, porque media só "a coluna veio preenchida". Um
insumo em `H` sob classe ilegível vira mão de obra e **leva encargo social**, que é o D109 renascido
em outra fonte.

Agora as três causas são separadas por `services.classificacao_desconhecida`: campo vazio (D111),
classe que declara não ser natureza (`ESPECIAIS`, `TAXAS` — reconhecidas, e a resposta delas é "não
classifico") e **vocabulário desconhecido**, que é o único reportável. Ele aparece três vezes: no
`importar_base_referencial`, no momento em que o operador está olhando; no relatório do
`reclassificar_itens_catalogo`, com quantos itens do catálogo dependem de cada classe; e em
`bases-resumo/` (`classes_desconhecidas`), que é o que fecha o indicador e escreve as palavras no
card. A conferência é só de insumo: em composição o campo traz o capítulo, que não é natureza.

**Classe sem tradução interrompe a importação** *(decisão do dono, 21/08/2026)*, e a assimetria com
a coluna ausente é de propósito — a diferença é **quem tem a resposta**. Base-mãe é global e
read-only: só o superuser importa, e o que ele importa todos os tenants enxergam, então traduzir uma
classe errado é alavanca de preço para a plataforma inteira de uma vez. O comando não escolhe
sozinho: para **antes de gravar** (publicação meio importada parece completa, e é pior que nenhuma),
lista o que não soube fazer com a contagem por classe, e devolve a pergunta com as duas saídas —
declarar a tradução ou `--aceitar-sem-classe`. Coluna **ausente** não interrompe: ali não há pergunta
a fazer a ninguém, a fonte não respondeu, e a publicação segue útil como era antes da ORC.9.

A tradução declarada mora em [`dados/classes/<fonte>.csv`](../../backend/moduloorcamento/dados/classes/)
(`classe;natureza`), lida por `services.classes_declaradas` e **vencendo** o de-para embutido. É por
fonte e não por publicação, então a resposta dada uma vez vale para os meses seguintes — senão a
mesma pergunta voltaria toda virada de mês. Em arquivo e não em tabela porque quem decide é o
superuser, uma vez por fonte: assim a decisão entra no diff e é revisável, em vez de alguém mudar a
natureza de uma classe inteira sem deixar rastro. O casamento ali é **exato** (e não por prefixo como
o embutido), que é também o escape para o caso em que o prefixo erra — capítulo que começa com
palavra de natureza, como "Serviços preliminares" batendo com `servico`.

**Mesmo código não é mesmo insumo.** A adoção acha o item do catálogo pelo par `(fonte, código)`, mas
isso diz **onde** escrever, não *o quê*: fonte que reaproveita número entre edições (tabela de
prefeitura) faria o item do tenant virar outro insumo carregando o histórico do anterior, com as
composições e as linhas orçadas ainda apontando para ele. Antes de sobrescrever, descrição e unidade
são conferidas ([`identidade.py`](../../backend/moduloorcamento/identidade.py) — unidade por
igualdade normalizada, descrição por semelhança de conjunto de palavras). Divergiu: a adoção **não
grava** e responde **409** com os dois lados (`{"forcar": true}` é a decisão humana de que é o mesmo
item); em lote, o divergente fica de fora e volta listado em `divergentes`; a reclassificação deixa o
item fora do lote e o reporta como "não confere" ou "ambíguo". `catalogo.Item.publicacao_referencia`
guarda de qual **edição** o item foi adotado — sem ela o par `(fonte, código)` era toda a procedência.

**Tipo próprio da empresa.** Por cima dessas naturezas, o tenant cria o nome que usa ("Andaime
locado", "Verba de mobilização") declarando de qual natureza aquilo é e como as flags de domínio se
comportam — `catalogo.TipoItemProprio`, com os padrões de cada natureza servidos por
`GET /api/catalogo/tipos-item/naturezas/` (o de-para vive no model; a tela que o repetisse divergiria
dele). O `save()` do `Item` reescreve o `tipo` pela natureza do tipo próprio, então não existe item
com rótulo de uma coisa e cálculo de outra; e encargo social ligado fora de mão de obra é recusado no
`clean()` e na API, porque essa combinação sai como preço errado, não como tela feia.

**Quem manda no banco de preço e nos tipos.** A ORC.9 cumpriu a condição que o §12.1 tinha deixado
escrita: `orcamento.banco.view`/`.edit` para o banco de preço da empresa (ler e manter deixaram de
ser `orcamento.base.view` + `orcamento.orcamento.edit`) e `cadastro.tipo_item.view`/`.edit` para os
tipos, no grupo **base** — definir tipo é ato de cadastro-mestre, da mesma classe de criar e excluir
cliente. A persona `orcamentista` nasce com as quatro; separar o curador de preços de quem orça é
tirar as linhas do papel de fábrica em `/app/admin/papeis`. Permissão nova exige rebuild da imagem da
IAM + `sync_authz`.

**Obra primeiro, planilha depois.** Orçar tem três níveis e **cada um é um endereço** — obras →
versões da obra → planilha. É o desenho do setor (Sienge e OrçaFácil entram pela obra, não por um
filtro), e é o que faz existirem trilha, link colável e botão voltar. Um `?orcamento=` grudado numa
tela de lista não dá nenhum dos três: filtro não é lugar nenhum, e por isso "voltar para todas as
obras" não tinha como funcionar.

**Sintético × analítico é a convenção da SINAPI, não um zoom na EAP.** As duas peças mostram a
planilha **inteira**, um serviço por linha; a analítica abre embaixo de cada serviço os insumos que
formam aquele custo — natureza, consumo (coeficiente × quantidade), preço e a parcela de cada um,
que **soma** o custo direto do serviço. Linha de insumo não repete BDI nem peso do orçamento (ela já
está contida no serviço acima) e não se edita: o que a muda é a composição. Serviço sem composição
gravada diz isso na cara — *composição não explodida* com o atalho para explodir, ou *preço digitado*
—, em vez de aparecer como serviço sem insumo. A grade lê tudo de uma vez em
`GET /api/orcamento/orcamentos/{id}/analitica/`, resposta separada da `arvore/` para trocar de modo
não jogar fora a planilha já carregada. Mesma régua na exportação XLSX/PDF.

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

Entitlement próprio **`orcamento`** (`RequireModule("orcamento")`) e **11 permissões** no catálogo da
IAM ([acesso-e-permissoes.md §7](../acesso-e-permissoes.md)): `orcamento.base.view`/`.adotar`,
`orcamento.banco.view`/`.edit` (ORC.9), `orcamento.orcamento.view`/`.edit`/`.aprovar`/`.revisar`,
`orcamento.item.view`/`.edit` e `orcamento.relatorio.view`. O módulo também **consome** duas de
fundação, criadas junto na ORC.9: `cadastro.tipo_item.view`/`.edit`, que vivem no grupo `base`
porque tipo de item é cadastro-mestre e serve SCM e SIL do mesmo jeito. Todo model **do tenant**
herda `TenantScopedModel` com **RLS fail-closed** (a base referencial é a exceção documentada em
§11.1).

Três separações deliberadas de permissão:

- **adotar ≠ editar a base.** A base não é editável por ninguém, então não existe
  `orcamento.base.edit`; adotar escreve no catálogo do **tenant** e tem permissão própria. Por isso
  os viewsets da base declaram `required_permission` fixa em vez de `required_resource` — o atalho do
  recurso derivaria um `.edit` fantasma e devolveria **403 mentiroso** onde o certo é **405**.
- **aprovar ≠ editar o orçamento.** Congelar a régua de custo é decisão de quem responde pela obra,
  não de quem digita a planilha — a persona `orcamentista` edita mas não aprova.
- **manter a régua ≠ usar a régua** *(ORC.9)*. O banco de preço da empresa saiu de
  `orcamento.orcamento.edit` e ganhou `orcamento.banco.*`; consultar a SINAPI (`base.view`) deixou
  de dar acesso à tabela que a casa negociou, que é **dado comercial**. Detalhe e motivo em §12.1.

Persona de fábrica **`orcamentista`**: orçamento (inclusive `banco.*`) + `cadastro.item.*` +
`cadastro.tipo_item.*` + leitura de obra/empreendimento e do que dá **custo real**
(`scm.oferta.view`, `scm.pedido.view`, `sil.saldo.view`, `sil.relatorio.view`). As duas famílias
novas ficam aí por padrão **para serem destacadas**: separar o curador de preços de quem orça é
tirá-las do papel de fábrica, não pedir código. Como o catálogo da IAM vive na imagem, o módulo exige rebuild de `sgi-iam` +
re-seed.

## 11. Decisões de rumo (tomadas pelo dono do produto)

1. **Bases referenciais entram desde o início** — SINAPI e ORSE importadas por comando, não só banco
   próprio. Consequências de desenho em §11.1.
2. **Composição analítica, faseada** — a planilha nasce em etapa × item; explosão de composição,
   encargos (onerado/desonerado) e BDI vêm na fatia seguinte, reusando `catalogo.ComponenteComposicao`.
3. **Curva S financeira nasce aqui** — distribuição do custo no tempo e desembolso previsto, ponderados
   por `EtapaObra.percentual_conclusao`. Gantt, precedências e avanço medido seguem sendo do PDCA.
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

### 11.2 Excluir orçamento: a trava protege a empresa, não tutela o usuário

> **Decisão do dono, 13/09/2026:** *"Quero que a trava seja o limite para não atrapalhar o usuário em
> sua empresa, mas também não pode limitar o usuário: um orçamento que não pode ser usado também não
> pode atrapalhar o usuário de ter outro orçamento, já que a paywall limita quantidades."*

| Status | Exclui? | Por quê |
|---|---|---|
| **Rascunho** | ✅ | tentativa em andamento, não rege nada |
| **Cancelado** | ✅ | morto por definição |
| **Superado** | ✅ | foi trocado por revisão; não rege nada |
| **Aprovado** | ❌ **409** | é a base contratual contra a qual medições foram feitas |

**O aprovado não é beco sem saída** — e é isso que separa trava de tutela: cancelar já existe, é um
clique, e abre o caminho. A recusa **diz isso** em vez de só negar. Nunca há estado do qual não se
saia.

**O defeito que isto corrigiu não era falta de trava — era a régua errada.** O `perform_destroy`
chamava `_exigir_editavel`, que é a regra da **escrita** (só rascunho). O aprovado estava protegido,
sim; o efeito colateral é que **cancelado e superado também não saíam**, e o usuário ficava com
documento morto que o sistema se recusava a deixá-lo limpar — exatamente a armadilha que a decisão
acima veio fechar.

> **Editar e excluir são réguas diferentes.** Um superado não aceita escrita (é história de revisão)
> mas aceita exclusão (não rege nada). Reusar a régua da escrita para a exclusão foi o que criou o
> problema — e é um erro fácil de repetir em qualquer módulo com máquina de estados.

**Vai para a lixeira** ([D116](../arquitetura/lixo.md)): o `Orcamento` herda `Excluivel`, então
excluir marca a lápide e a planilha inteira — com as sete tabelas filhas — volta intacta dentro do
prazo do plano. A tela só mostra o botão onde o servidor deixa sair; o aprovado não ganha botão
trancado, porque oferecer a porta para depois recusar é pior que não oferecer.

**O número da versão nunca é reciclado.** `proxima_versao` lê por `Orcamento.todos`, incluindo o que
está na lixeira: versão é **identidade** numa cadeia de revisão, não rótulo. Se o número voltasse a
ser oferecido, restaurar colidiria com o orçamento que nasceu no lugar do excluído — e "v3" passaria
a significar duas planilhas diferentes no histórico da obra. É o oposto do que se faz com **nome**,
que a lixeira libera de imediato ([obras.md](obras.md)): nome é rótulo e se reusa; número de versão,
não.

**A quantidade de orçamentos por plano continua indefinida** — não há quota sobre a planilha hoje.
Registrado em [D124](../pendencias.md).

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
| **ORC.6** | E2E vivo pelo gateway + sincronização de docs — [orc6_orcamento_test.py](../../testes/e2e/orc6_orcamento_test.py), 17 blocos / 55 checks |
| **ORC.7** | **Paridade de licitação:** encargos analíticos (A/B/C/D), memória do quantitativo (`LinhaMedicao`), relação consolidada + curva ABC **de insumos**, desembolso por insumo, reajuste por fórmula paramétrica, quatro peças de documento novas, `importar_indices`, tasks de varredura. Seam novo no SCM (compra nasce da planilha) e 6ª página no frontend |
| **ORC.8** | **A carga da base oficial num clique:** `FonteOficial` (template de URL editável), `CargaBase` (histórico, inclusive das falhas), `AnaliticaNacional`, leitor do formato largo da Caixa, botão + upload + agendamento — tudo do `is_platform_admin`, na tela **Sistema → Bases oficiais** |
| **ORC.8b** | **A EMBASA, a fonte que publica em PDF:** leitor do *Relatório de Serviços* e do *Relatório de Insumos Genéricos*, `BaseReferencial.variante` (o quinto eixo da chave), menu de documentos da fonte (`documentos-disponiveis`), de-para de classes da EMBASA e a quarta caixa do seletor de base |

### 12.5 ORC.7 — as três assimetrias que sobravam

O ORC.6 fechou o módulo como orçamentista completo; a comparação com OrçaFascio,
Arquimedes/CYPE e Sienge apontou três coisas que **não quebravam quando erravam**, que é a
pior classe de defeito numa peça de licitação:

1. **Encargo era um percentual digitado.** Calculava certo e reprovava em análise, que pede o
   quadro. O grupo D é a razão de o quadro existir: `A×B/100` e `FGTS×aviso/100` ninguém digita
   à mão sem errar, e o erro some dentro de um total plausível. Aqui ele é **derivado**, e a tela
   mostra o campo bloqueado com a conta ao lado.
2. **A quantidade não tinha memória.** O preço abria em insumos e respondia "por que este m³
   custa R$ 412,80?"; a quantidade era um Decimal e não respondia a nada — sendo que numa
   conferência é ela que se questiona primeiro (o preço vem de tabela pública, a quantidade vem
   do projeto de quem orçou). É o núcleo do Arquimedes, e a assimetria mais visível que o módulo
   tinha.
3. **Reprecificar ≠ reajustar.** Trocar a data-base de uma publicação muda a *composição* do
   custo; reajustar multiplica tudo por um fator contratual sem tocar em composição. Só a
   primeira existia. O fator é **razão entre dois números-índice**, não soma de variações —
   encadear variações acumula erro de arredondamento que vira centavo no aditivo, e centavo no
   aditivo é apontamento.

**Fronteira mantida.** Medição de empreiteiro e aditivo continuam fora (§7): o ciclo
orçado→medido→pago se fecha com o **PDCA** (planejamento) e o **moduloerp** (financeiro),
não aqui. Takeoff de modelo BIM segue da Central BIM — `LinhaMedicao` já é o lugar onde o
quantitativo extraído vai pousar quando ela existir.

**O que é de outro módulo mora lá.** A relação de insumos é publicada aqui; quem a transforma
em `Demanda` é o [SCM](moduloscm.md) (`moduloscm/do_orcamento.py`), porque quem sabe explodir
composição é este módulo e quem sabe o que é uma compra é aquele.

### 12.7 ORC.8 — a carga da base num clique

O calcanhar do módulo nunca foi cálculo: é **dado fresco**. Manter 27 UFs × 3 regimes × 12 meses à
mão não escala, e a `tasks.py` só sabe **avisar** que a publicação envelheceu. O ORC.8 fecha isso
como operação do **dono da plataforma** (`is_platform_admin` — o mesmo gate que já guarda a base-mãe
em `impexp.py`; não é o `is_superuser` do Django).

Decisões de rumo tomadas pelo dono, e o porquê de cada uma:

| Decisão | Por quê |
|---|---|
| **ZIP oficial + parser próprio**, não API de terceiro | Não existe biblioteca madura para SINAPI: o único ETL open source é alpha, de um autor, e GPLv3; as APIs comerciais cobram e o plano gratuito não carrega base em massa. O artefato da Caixa é autoritativo, gratuito e estável há anos. A API comercial fica como caminho **futuro**, quando o produto amadurecer — daí a leitura ficar atrás de uma fronteira trocável |
| **Um download por mês**, não 54 | Desde 2025 a Caixa publica **um ZIP nacional** (§4.1). O que parecia 54 downloads é um |
| **Template de URL editável + `url_origem` gravado** | A URL da Caixa **já mudou uma vez** (o padrão por UF morre em 12/2024). Template numa caixa de texto conserta em 30 segundos, sem deploy; `url_origem` na publicação registra de onde cada preço veio, que é o que a auditoria pede |
| **Download pausado, com backoff** | O WAF da Caixa (Azion) **limita por taxa**: rajada derruba tudo para `429`, inclusive URL boa. Também exige sessão aquecida + `Referer` — hit frio no `/Downloads/` é recusado |
| **Upload como plano B** | Mês em que a Caixa muda layout ou aperta o WAF não pode parar a carga |
| **Botão sempre clicável + agendamento que o superuser define** | O botão resolve *hoje*; o agendamento evita que "alguém esqueceu" vire orçamento nascendo com preço vencido |
| **Histórico guardado, nada apagado** | Publicação **é** data-base, e orçamento tem data-base. Apagar mês antigo é perder reprecificação e a justificativa de preço em auditoria |
| **Analítica normalizada** | O coeficiente é **nacional** e não varia por UF/regime (§4.1). Amarrado a cada publicação, ele seria replicado 54× — ~3,6 milhões de linhas/mês, ~69 milhões nos 19 meses desde 01/2025. Guardado uma vez por fonte+mês, são ~67 mil/mês |
| **ISE/CSE (sem encargos) importado** | É a base legítima para o **quadro de encargos analítico** que o ORC.7 já entregou: aplicar quadro próprio sobre preço que já embute encargo é contar duas vezes |

**Resumo antes de gravar**, não conferência linha a linha: a importação é idempotente, e uma
conferência de 800 mil linhas seria teatro. O resumo diz quantos insumos, composições e linhas
analíticas entram — e é aí que se percebe o arquivo errado.

**A classificação do insumo** (MATERIAL / MÃO DE OBRA / EQUIPAMENTO / …) só existe no formato novo;
enquanto a publicação carregada for do formato antigo, filtro por ela devolve vazio. Ver §4.1.

#### Onde a ORC.8 mora no código

| Peça | Arquivo |
|---|---|
| A busca: sessão aquecida, `Referer`, backoff e teto de bytes no stream | [oficial.py](../../backend/moduloorcamento/oficial.py) |
| O motor: ZIP → abas largas → publicações; resumo; escrita compartilhada | [carga.py](../../backend/moduloorcamento/carga.py) |
| Onde a fonte mora e o que já foi tentado | `FonteOficial` e `CargaBase` em [models.py](../../backend/moduloorcamento/models.py) |
| A analítica guardada uma vez por fonte + mês | `AnaliticaNacional` em [models.py](../../backend/moduloorcamento/models.py) |
| A leitura única das duas analíticas | `services.componentes_da_composicao` |
| O botão, o plano B e o histórico | `FonteOficialViewSet` / `CargaBaseViewSet` em [views.py](../../backend/moduloorcamento/views.py) |
| A varredura que busca (e as quatro recusas dela) | `agendar_cargas_do_mes` em [tasks.py](../../backend/moduloorcamento/tasks.py) |
| A mesma porta pela bancada | [carregar_base_oficial](../../backend/moduloorcamento/management/commands/carregar_base_oficial.py) |
| O painel, só para `is_platform_admin` | [PainelCargaOficial.tsx](../../frontend/src/modules/orcamento/components/PainelCargaOficial.tsx) |
| A tela onde ele mora — **fora deste módulo** | [sistema/pages/BasesOficiaisPage.tsx](../../frontend/src/modules/sistema/pages/BasesOficiaisPage.tsx) (`/app/sistema/bases`) |
| Os tetos do caminho (bytes, relógio, memória, tentativas, esperas) | [payment/planos.py](../../payment/planos.py) §5.5b |

**A carga NÃO mora dentro do módulo** *(decisão do dono, 22/08/2026)*. Ela
nasceu na tela de Bases & bancos e mudou-se para **Sistema → Bases oficiais**,
porque a base-mãe não é dado da empresa: vale para todos os tenants ao mesmo
tempo e nenhum deles a edita. Dentro do Orçamento ela dependia do entitlement
`orcamento` — régua errada para decidir quem carrega a SINAPI — e aparecia num
produto vendido a quem ela não pertence. O painel (`PainelCargaOficial`) continua
morando no módulo como componente; quem o hospeda é a tela de plataforma. Regra
de visibilidade em [acesso-e-permissoes.md](../acesso-e-permissoes.md).

**Quem escreve na base-mãe são duas portas e um motor.** O comando da ORC.0 continua sendo o
caminho do formato longo e das fontes sem leitor; a carga é o caminho do arquivo nacional. As duas
gravam pelas **mesmas** funções (`carga.gravar_itens`, `carga.gravar_analitica`) — duas cópias do
que "reimportar" significa divergiriam na primeira publicação com layout novo, e a divergência
apareceria como preço errado, não como erro.

**A analítica tem dois armazenamentos e uma leitura.** `ComposicaoReferenciaItem` guarda a analítica
**da publicação** (formato longo, conferida por quem importou aquele arquivo) e `AnaliticaNacional`
guarda a **nacional**, uma vez por fonte + mês. Todo consumidor — adoção, cópia para banco de preço,
endpoint de composição — passa por `services.componentes_da_composicao`, e a da publicação vence
quando existe. Componente cujo filho não tem preço naquela UF fica de fora: a regra 1 do §4.1 vale
até o fim, e uma composição exibida com insumo a R$ 0,00 mentiria sobre o próprio custo.

**Carregar reativa a publicação.** `ativa=False` some do seletor
(`bases-resumo` só lista ativas), e uma carga que grava os preços deixando a
publicação escondida termina com sucesso sem resultado visível. Carregar é ato
afirmativo — diz "este mês agora está aqui".

**O botão não é o único caminho, de propósito.** Três saídas para o mesmo mês, na ordem em que a
operação as usa: o botão (baixa e grava), *só conferir* (lê e conta, não grava) e *enviar o arquivo*
(o plano B, para o mês em que a Caixa muda o layout ou o WAF aperta). O agendamento por fonte
(`dia_do_mes`) é a quarta, e existe para que "alguém esqueceu" não vire orçamento nascendo com preço
vencido.

**O que o motor ainda não lê:** o formato largo da Caixa e o PDF da EMBASA (§12.8), e mais nada.
`carga.fontes_conhecidas()` declara isso, a tela diz na cara e o agendamento se recusa a tentar uma
fonte sem leitor — nada finge funcionar. É o que sobrou do [A14](../pendencias.md), com outro
conteúdo.

### 12.8 ORC.8b — a EMBASA, a fonte que publica em PDF

A EMBASA (Empresa Baiana de Águas e Saneamento) é a tabela de preços de saneamento da Bahia, e é a
primeira fonte do sistema que **não entrega planilha nenhuma**. Não é descuido de quem publica: o
artefato é gerado do Excel deles com moldura de relatório e serve para licitação impressa. Quem
precisa do dado é quem o lê.

Três fatos desta fonte, e a decisão que cada um forçou:

| O que a fonte faz | O que isso exigiu |
|---|---|
| **Publica por semestre, numa página com nome próprio** (`/2026.11`), não um arquivo por mês | O `template_url` da `FonteOficial` guarda a **página**, e a carga lista os documentos dela. `cargas/documentos-disponiveis/` é esse menu; `carga.exige_escolha_de_documento` tira a fonte da varredura mensal, porque um agendamento que escolhe por alguém escolhe o preço de uma região para quem orça em outra |
| **65 tabelas carregáveis por semestre**, e nenhuma é "a do mês" — escopo (expansão · operação de água · de esgoto, produção × unidade fixa) × regime × convenção coletiva | `BaseReferencial.variante` entrou na chave da publicação. Sem ela, as seis tabelas de um mesmo escopo+regime colidiriam e a última carga sobrescreveria as cinco anteriores **em silêncio** — são os mesmos 6.992 códigos com preços diferentes (6.093 dos 6.992 divergem entre a 1.1 e a 1.2) |
| **O documento declara a própria identidade** na quinta linha: `DESONERADO - EXPANSÃO - SINTRACOM`, com `LS H:` e `LS M:` no cabeçalho | A identidade é lida do **PDF**, não do nome do arquivo: o nome traz `h-158-56`, não traz o sindicato, e é o sindicato que separa duas publicações que de outro modo colidiriam. O rótulo da publicação sai daí |
| **E nem toda tabela tem convenção.** As quatro de manutenção industrial da operação de água terminam em `- MANUT IND`, que é fim de escopo e não sindicato — elas são uma só por regime | A convenção é o **último pedaço, quando vem sozinho**: sigla de sindicato é uma palavra, `MANUT IND` são duas. Sem ela o escopo vai inteiro e `sindicato` fica vazio, em vez de guardar o que não é sindicato. Lista fixa de siglas quebraria no primeiro acordo novo |

Quatro regras do dado da EMBASA, e por que cada uma é o **inverso** de uma regra da SINAPI:

1. **`TRADICIONAL` é o `onerado` do sistema.** A dobra de nomenclatura é da fonte, e "tradicional"
   soa como "o normal" — trocar os dois inverte o custo de toda a tabela, calado.
2. **`0,00` é valor publicado, não ausência.** Na SINAPI, célula em branco significa "não houve
   pesquisa" e a linha fica fora (§4.1). Aqui a célula vem **preenchida** com `0,00` para o que a
   fonte não precifica (mobilização, fiscalização — verba do contrato). A linha entra, e o resumo
   conta quantas são.
3. **Insumo é custo puro, serviço não é.** O *Relatório de Insumos Genéricos* traz o salário-hora
   sem leis sociais (ajudante de armador a R$ 7,84/h) e entra no regime **`sem encargos`**; o
   *Relatório de Serviços* traz o preço **já com** a LS do cabeçalho dentro e entra como
   `desonerado`/`onerado`. Trocar os dois aplicaria encargo sobre preço que já o tem — o D109
   renascido nesta fonte.
4. **A data-base é a do artefato, não a que foi pedida.** A corrida nasce com uma competência
   calculada por defasagem em meses; a EMBASA publica por semestre, então pedir agosto e receber
   junho é o normal. Vale a do PDF, e o aviso registra a diferença.

**Não há analítica.** A EMBASA publica o preço sintético do serviço, não a composição dele — as
composições entram com custo e sem memória de cálculo, pelo mesmo aviso que a SINAPI dá quando a
aba analítica falta.

**Os PDFs de Encargos Sociais ficam de fora, de propósito.** `1.7`, `2.7`, `1.8`… são a memória de
cálculo da LS (grupos A, B, C e D em quatro colunas), e o lugar deles é o quadro de encargos do
ORC.7, não a base de preço. Eles aparecem na lista de documentos — é o que a página publica — mas
não são carregáveis, e a leitura recusa um deles dizendo por quê. Os dois números que a base precisa
(LS horista e mensalista) já vêm no cabeçalho de **toda** tabela de serviços, e ficam no rótulo da
publicação e no resumo da corrida. Eles não viram campo porque o preço de serviço da EMBASA já os
embute: ninguém os aplica de novo, e o que se precisa deles é saber qual tabela se está usando.

**A URL do documento é amarrada ao host cadastrado.** O endpoint manda o worker buscar um endereço —
sem a amarra, é SSRF com convite. A liberdade que a fonte exige (escolher entre 65 documentos do
mesmo site) cabe inteira dentro do host que já está em `FonteOficial`.

#### Onde a ORC.8b mora no código

| Peça | Arquivo |
|---|---|
| O leitor: identidade do cabeçalho, PDF → publicação, lista de documentos | [embasa.py](../../backend/moduloorcamento/embasa.py) |
| O despacho por fonte e o menu de artefatos | `ler_pacote` / `documentos_disponiveis` em [carga.py](../../backend/moduloorcamento/carga.py) |
| O quinto eixo da chave | `BaseReferencial.variante` em [models.py](../../backend/moduloorcamento/models.py) |
| O de-para das seis classes da fonte | [dados/classes/embasa.csv](../../backend/moduloorcamento/dados/classes/embasa.csv) |
| O endereço já cadastrado | `cadastrar_embasa` em [0014_orc8b_embasa_pdf.py](../../backend/moduloorcamento/migrations/0014_orc8b_embasa_pdf.py) |
| A escolha do documento, sem abrir SSRF | `CargaBaseViewSet._documento` em [views.py](../../backend/moduloorcamento/views.py) |
| `--listar`, `--documento` e `--todas` | [carregar_base_oficial](../../backend/moduloorcamento/management/commands/carregar_base_oficial.py) |
| A quarta caixa do seletor | [SeletorDeBase.tsx](../../frontend/src/modules/orcamento/components/SeletorDeBase.tsx) |
| A caixa "Tabela" no painel de carga | [PainelCargaOficial.tsx](../../frontend/src/modules/orcamento/components/PainelCargaOficial.tsx) |

### 12.6 Onde o ORC.7 mora no código

| Peça | Arquivo |
|---|---|
| Quadro de encargos e o resolvedor da explosão | [encargos.py](../../backend/moduloorcamento/encargos.py) |
| Parciais de medição e o avaliador de fórmula | [quantitativos.py](../../backend/moduloorcamento/quantitativos.py) |
| Relação de insumos, ABC de insumos, composição por natureza | [insumos.py](../../backend/moduloorcamento/insumos.py) |
| Reajuste contratual | [reajuste.py](../../backend/moduloorcamento/reajuste.py) |
| Desembolso por insumo | `desembolso_por_insumo` em [controle.py](../../backend/moduloorcamento/controle.py) |
| Peças de documento (BDI, encargos, relação, ABC de insumos, carta) | [exportacao.py](../../backend/moduloorcamento/exportacao.py) + [carta_proposta.html](../../backend/moduloorcamento/templates/moduloorcamento/carta_proposta.html) |
| Varredura de base/índice atrasados | [tasks.py](../../backend/moduloorcamento/tasks.py) (beat em `config/settings.py`) |
| Série de índices por comando | [importar_indices.py](../../backend/moduloorcamento/management/commands/importar_indices.py) |
| Seam da compra | [moduloscm/do_orcamento.py](../../backend/moduloscm/do_orcamento.py) |
| Testes da fatia | [test_orc7.py](../../backend/moduloorcamento/test_orc7.py) |

**Tetos no `payment/`:** `ORCAMENTO_TETO_LINHAS_MEDICAO_POR_ITEM` e
`ORCAMENTO_PROFUNDIDADE_MAXIMA_FORMULA`, cobrados por `nucleo/test_tetos_no_payment.py`.

### 12.3 Onde o ORC.5b mora no código

| Peça | Arquivo |
|---|---|
| Bancos da empresa: adoção, trava, cópia da base pública | [bancos.py](../../backend/moduloorcamento/bancos.py) |
| **Importação/exportação tabular: a declaração** | [impexp.py](../../backend/moduloorcamento/impexp.py) — o motor é o [funcoesimpexp](funcoesimpexp.md) |
| Cabeçalho da analítica, só para o comando | [leitura.py](../../backend/moduloorcamento/leitura.py) |
| Reprecificação: prévia, aplicar, desfazer | [reprecificacao.py](../../backend/moduloorcamento/reprecificacao.py) |
| Duplicar orçamento e copiar linhas | [duplicacao.py](../../backend/moduloorcamento/duplicacao.py) |
| Exportação de **documento** (XLSX/PDF) | [exportacao.py](../../backend/moduloorcamento/exportacao.py) + [planilha.html](../../backend/moduloorcamento/templates/moduloorcamento/planilha.html). O PDF é emitido pelo `html_para_pdf` do [funcoesimpexp §6.1b](funcoesimpexp.md) — aqui fica o HTML, não o `write_pdf()` |
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

### 12.1 Permissões: as 9 do catálogo bastaram até a ORC.9 (que criou mais 4)

ORC.1–ORC.4 **não criaram permissão nova**. Cronograma e NBR 12721 reusam as existentes
(`orcamento.orcamento.edit` para mexer no cronograma, `orcamento.item.edit` para áreas/unidades,
`orcamento.relatorio.view` para os quadros, curva ABC, curva S e as quatro colunas). O motivo é de
operação, não de modelagem: permissão nova exige **rebuild da imagem `sgi-iam` + re-seed**, e o
recorte destas fatias não pediu granularidade que as 9 não dessem. Se o frontend (ORC.5) mostrar que
"quem monta a planilha" e "quem planeja o cronograma" são papéis distintos na prática, aí sim vale
`orcamento.cronograma.*` e `orcamento.nbr.*`.

**O banco de preço saiu dessa regra na ORC.9 — a condição que estava escrita aqui se cumpriu.** Até
então, manter banco de preço usava `orcamento.orcamento.edit` e ler usava `orcamento.base.view`, com
a ressalva de que "se na operação real quem cuida do banco de preço for pessoa diferente de quem
orça, vale criar `orcamento.banco.*`". Virou, por decisão do dono (20/08/2026): a régua de preço da
casa é função específica. Foram criadas **quatro** permissões, e a conta da parada de imagem foi paga
de uma vez:

| Permissão | Grupo | O que abre |
|---|---|---|
| `orcamento.banco.view` | `orcamento` | ver os bancos de preço próprios (dado comercial — separado de consultar a SINAPI) |
| `orcamento.banco.edit` | `orcamento` | manter banco próprio: item, pasta, coeficiente, trava e a importação de tabela |
| `cadastro.tipo_item.view` | `base` | ver os tipos próprios de item |
| `cadastro.tipo_item.edit` | `base` | criar/editar tipo próprio (natureza + flags) |

Trazer preço **para dentro do catálogo** continua em `orcamento.base.adotar`: é escrita no
cadastro-mestre, não no banco, e quem pode uma coisa não precisa poder a outra. A persona
`orcamentista` nasce com as quatro (o módulo continua utilizável no dia seguinte ao deploy) e
separar o curador de preços de quem orça é tirar as linhas do papel de fábrica em
`/app/admin/papeis`. `cadastro.tipo_item.view` também foi para `suprimentos` e `almoxarife`, que
listam item e mostrariam rótulo vazio sem ela.

## 13. O que ficou de fora — e o endereço de cada coisa

A comparação com OrçaFascio, Arquimedes/CYPE e Sienge (§2) levantou mais do que o ORC.7 entregou.
O que sobrou **não está esquecido: está endereçado**. A régua para decidir o endereço é a da §7 —
o módulo faz *composição de custo e a régua contra a qual se mede*; quem faz outra coisa mora
onde essa coisa é assunto principal.

Esta tabela é o contrato entre os módulos. Enquanto a coluna "Onde mora" não for construída, a
capacidade **não existe no SGI** — e é isso que ela declara, em vez de deixar cada leitor supor.

| Capacidade que falta | Quem no mercado tem | Onde mora | Situação |
|---|---|---|---|
| **Boletim de medição de empreiteiro**, retenção contratual, liberação por avanço medido | Sienge; Arquimedes (*autos de medição*) | **`modulopdca`** — inteiro. Medir, aplicar a retenção e liberar são atos do **contrato de obra**; o ERP recebe o título líquido e paga (§13.2). **Não existe `modulomedicao`** e não deve existir | ❌ Fase do PDCA |
| **Gantt, caminho crítico, precedências, linha de balanço** | Sienge; MS Project ao lado do orçamentista | **`modulopdca`** — [modulos-planejados.md](modulos-planejados.md) | ❌ Fase do PDCA |
| **Aditivo contratual de obra** (o documento, o saldo do contrato, o limite legal de acréscimo) | Sienge | **`modulopdca`** — é contrato de obra, não recurso empresarial. Aqui já existe o **efeito no custo**: `RevisaoOrcamento` tipo `aditivo` registra a mudança da régua e o par de valores; o PDCA amarra isso ao contrato e ao prazo | 🚧 metade feita |
| **Takeoff de quantitativo a partir do modelo BIM** (Revit/IFC), medição sobre DWG/DXF | Arquimedes/CYPE — é o núcleo do produto deles | **Central BIM** (5D, H3) + **[moduloprancheta](moduloprancheta.md)**, que já tem o acervo e o visualizador. **O ponto de pouso já existe aqui:** `LinhaMedicao` é onde a parcial extraída do modelo entra, com `referencia_projeto` apontando o elemento — não precisará de model novo | ❌ Fase da Central BIM |
| **IA que sugere composição/CPU e insumo faltante** | OrçaFascio (*OF IA*) | **[funcoesia](funcoesia.md)** — é a casa de toda chamada de modelo na plataforma (AD-8: integração externa → task Celery). O orçamento entra como *consumidor*: expõe a composição e recebe a sugestão, sem cliente de IA próprio | ❌ [expansão 06](../expansão/06-dados-ia-automacao.md) |
| **Previsão de estouro** (orçado × realizado × preços da rede) | ninguém, de forma consolidada | **funcoesia** + os dados daqui e do SCM | ❌ [expansão 06](../expansão/06-dados-ia-automacao.md) |
| **Benchmark de custo/m² e de preço de insumo entre empresas** | ninguém (nenhum concorrente vê a rede) | **Esfera de Rede** — [expansão E4](../expansão/06-dados-ia-automacao.md). `ParametroObra` (área equivalente + padrão) já existe **para** isso | ❌ E4 |
| **Banco de composições publicável na rede** | — | **Esfera de Rede**, no mesmo padrão `ref_externa`/`origem_tenant` do SCM | ❌ E4 |
| **Download automático das bases** (SINAPI/ORSE mensal, 27 UFs) | OrçaFascio e Vigha vendem "sempre atualizadas" como *feature* | **Plataforma** — a varredura diária já existe em [`tasks.py`](../../backend/moduloorcamento/tasks.py) e **avisa**; falta a busca, que exige fonte declarada por publicação. Achado **A13** em [pendencias.md](../pendencias.md) | 🔴 aberto |
| **SICRO, SEINFRA, SEDOP carregadas** | OrçaFascio: 20+ bases | **Operação de dado**, não código: `Fonte` aceita as quatro desde o ORC.0 e o importador é genérico. Achado **A14** em [pendencias.md](../pendencias.md) | 🔴 aberto |
| **Realizado financeiro completo por obra** (despesa lançada direto no ERP, sem passar por pedido) | Sienge | **[moduloerp](moduloerp.md) D.1.4** — dimensão de obra na `ContaPagar`. O limite já é declarado na resposta (§5, `realizado_cobertura`) em vez de rateado por aproximação | ❌ Fase D.1.4 |

### 13.1 A linha entre PDCA e ERP — obra × recursos empresariais

*Decisão do dono, 17/08/2026*, corrigindo a primeira versão desta seção, que jogava retenção e
aditivo no ERP: **o ERP é de recursos empresariais; o PDCA é de obra.** Contrato de empreiteiro,
medição, retenção e aditivo de escopo são do canteiro — o ERP não tem por que conhecer o
percentual de avanço de uma etapa para pagar uma parcela.

A fronteira exata já tem precedente vivo no SGI, e é o mesmo do SCM: **`PedidoCompra.conta_pagar_ref`.**
O SCM decide a compra inteira (fornecedor, preço, condição) e entrega ao ERP um **título**; o ERP
não sabe nada de cotação. O PDCA segue esse molde:

```
PDCA                                                      │  moduloerp
apura o avanço → aplica a retenção do contrato →          │  recebe o título
libera a parcela                            ─────────────▶│  → ContaPagar → paga
(quanto é devido, e por quê)                              │  (quando sai do caixa)
```

Ou seja: **quem decide o valor é o PDCA; quem move o dinheiro é o ERP.** A retenção não é um
desconto financeiro, é uma cláusula do contrato de obra — quem a calcula precisa saber o que foi
medido, e isso o ERP não sabe. O que ele recebe é o líquido, com o vínculo de volta, como já
acontece com o pedido de compra.

Consequência para este módulo: nada muda. O Orçamento entrega a **régua** (orçamento aprovado,
`orcado_por_etapa` na mesma dimensão que o SIL usa) e o **desembolso previsto** (curva S e, desde
o ORC.7, por insumo). Quem consome é o PDCA de um lado e o fluxo de caixa projetado do ERP
(D.1.7) do outro.

### 13.2 Por que nada disso virou "só mais um arquivo aqui"

Seria mais rápido pôr medição, Gantt e takeoff dentro do `moduloorcamento` — o dado está todo à
mão. O custo apareceria depois, e em dois lugares:

- **O módulo deixaria de ter uma pergunta.** Hoje ele responde *"quanto deveria custar, e estamos
  dentro?"*. Um módulo que também mede avanço, também agenda tarefa e também lê modelo BIM não
  responde nada — vira o lugar onde tudo que toca obra acaba caindo, que é como um sistema de
  gestão integrada vira um monolito com telas.
- **A segunda casa nasceria vazia.** Quando o PDCA for construído, o cronograma físico teria de
  ser extraído daqui, com as medições já feitas apontando para o lugar errado. É mais barato o
  endereço ficar reservado e vazio do que ocupado pelo módulo errado.

O que **é** deste módulo e ficou reservado para uma fatia futura está em §9 (seams inertes): o
`ItemOrcado` preparado para receber id de elemento BIM e o `ParametroObra` que o benchmark exige.

## 14. Status

Ver [roadmap](../roadmap.md).
