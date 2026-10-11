# modulopdca — PDCA: planejar, executar, verificar, agir

> **Planta do módulo.** Descreve o desenho, não o status: o que existe, o que ele não faz e por quê.
> Status e faseamento em [../roadmap.md](../roadmap.md); achados abertos em
> [../pendencias.md](../pendencias.md).

## 1. O que é

O `modulopdca` é o **laço** da obra: planeja o que será executado, registra o que foi, mede o que foi
feito contra o que foi planejado e trata o desvio.

O nome não é decorativo. A ISO 9001:2015 cita o ciclo de Deming na cláusula 0.3.2 como a estrutura da
própria norma — **cláusulas 4–6 = Plan, 7–8 = Do, 9 = Check, 10 = Act** — e é essa a forma do módulo.
Mais do que isso: é a forma do **SGI inteiro**, que hoje tem o laço aberto.

| Letra | O que a plataforma já tem | O que falta |
|---|---|---|
| **Plan** | [`moduloorcamento`](moduloorcamento.md) é o plano de **custo**: EAP, composição, BDI, curva S | O plano de **tempo e execução** — atividade, precedência, ritmo, contrato |
| **Do** | [`modulosil`](modulosil.md) e [`moduloscm`](moduloscm.md) movem **recurso**; [`modulodiario`](modulodiario.md) registra o **dia** | O que foi **executado** — avanço da atividade, medição do contrato |
| **Check** | — | **Nada.** O avanço da obra é `EtapaObra.percentual_conclusao`, digitado à mão |
| **Act** | — | **Nada.** Não-conformidade, ação corretiva, replanejamento e aditivo não existem |

O módulo fecha as duas colunas vazias. Não é um produto de planejamento ao lado do sistema: é a
metade que faltava do sistema.

## 2. A prática do mercado (pesquisa)

### 2.1 As quatro escolas

| Escola | Referência | O que faz de essencial |
|---|---|---|
| **ERP de construtora** | Sienge | Contrato de empreiteiro → medição por item → aditivo. O aditivo **não deixa a quantidade final cair abaixo do já medido**, e o item aditado fica marcado nas medições. Notável: o Sienge **tirou o planejamento do ERP** e o pôs num produto separado (Prevision), integrando medição física ↔ financeira |
| **Planejamento puro** | Primavera P6, MS Project | CPM, precedências, calendários múltiplos, **linhas de base** (P6 ilimitadas, MSP uma só), nivelamento de recursos e EVM. O P6 mede valor agregado em **homem-hora e em custo separadamente**; o MSP só em custo — porque uma obra pode gastar dentro do previsto e estar perdendo em produtividade de equipe |
| **Lean / Last Planner** | LPS, linha de balanço | **PPC** (percentual da programação concluída — média ~54% em obra convencional, 80–85% com LPS bem aplicado), remoção de **restrições** antes de programar (*make-ready*) e a **causa do não-cumprido** realimentando o ciclo. A LOB planeja por **localização e ritmo**, não por duração |
| **Qualidade e campo** | Procore, Autodesk CC, SAP QM | Observações **tipificadas** (não-conformidade, segurança, boa prática, pré-punch), punch list, RFI. No SAP, a notificação de qualidade **não fecha** enquanto as ações corretivas não forem executadas *e* aprovadas (8D/CAPA) |

### 2.2 O que é obrigatório no Brasil

O **PBQP-H / SiAC** exige, para certificar: **FVS** (Ficha de Verificação de Serviço) — o checklist do
serviço, com possibilidade de **reprovar item** e registrar pendência — e o tratamento da
não-conformidade com **duas** respostas, ação corretiva imediata e ação preventiva. O nível A exige o
sistema de gestão da qualidade implantado; o B é a porta de entrada.

Isso não é diferencial: é requisito de quem quer vender para incorporadora certificada ou disputar
obra pública. Um módulo de obra sem FVS não atende a construtora que já é certificada.

### 2.3 O que o SGI tem e um software de planejamento puro não tem

O MS Project não sabe quanto custa a atividade. O P6 não sabe se o material chegou. O Prevision
precisa de integração para saber o que foi contratado. Aqui, **a régua, o recurso e o contrato moram
na mesma plataforma**:

- o **orçado por etapa** já sai pronto de [`planilha.orcado_por_etapa`](../../backend/moduloorcamento/planilha.py),
  na mesma chave `(obra, etapa)` que o SIL usa para o aplicado;
- o **aplicado** de material vem do SIL sem integração;
- o **comprometido** vem do SCM;
- o canteiro **já fala com a plataforma por WhatsApp** ([`modulodiario`](modulodiario.md));
- a **não-conformidade pode virar pino sobre o desenho**, porque a [Prancheta](moduloprancheta.md) já
  tem acervo, visualizador, marcação com âncora e exportação BCF.

Nenhum concorrente tem os cinco no mesmo lugar. É esse o argumento do módulo.

## 3. Fundação já pronta (o módulo não começa do zero)

| O que o PDCA precisa | Onde já existe |
|---|---|
| Régua de custo por etapa | `planilha.orcado_por_etapa` — orçamento **aprovado** é congelado |
| Insumo explodido e coeficiente da composição | `ItemOrcadoInsumo` — a base da produtividade prevista |
| Distribuição de custo no tempo | `ParcelaEtapa` + curva S |
| Aplicado de material por `(obra, etapa)` | [`modulosil`](modulosil.md) |
| Comprometido | [`moduloscm`](moduloscm.md) |
| Cadastro único de empreiteiro | `fornecedores.Fornecedor` — **sem campo de tipo**; a tipagem vive em `ProdutoServicoFornecedor`, N por fornecedor |
| Título a pagar | `moduloerp.ContaPagar`, no molde de `PedidoCompra.conta_pagar_ref` |
| Pessoa, cargo, equipe | `rh` |
| Feriado federal/estadual/municipal e recorrência RRULE | `modulocalendar` |
| Canal do canteiro | `modulodiario` (`origem = web` ou `whatsapp`), com IA lendo texto e foto |
| Marcação sobre o desenho, BCF | [`moduloprancheta`](moduloprancheta.md) |
| Âncora geográfica | `modulomaps.Local` (fundação sem entitlement) |
| Item de catálogo, inclusive EPI | `catalogo.Item` |
| Importação/exportação tabular | [`funcoesimpexp`](funcoesimpexp.md) |
| Fila de trabalho pesado | `nucleo.frota` |
| Entitlement `pdca` | já reservado em `backend/modulopdca/` (view de status com `RequireModule`) |

## 4. Modelos

Todo modelo herda `TenantScopedModel`, com **RLS fail-closed**. A convenção de linha sintética ×
analítica repete a do `ItemOrcado`, que já provou funcionar em árvore grande.

### 4.1 Estrutura — onde e quando

**`LocalObra`** — a hierarquia **construtiva**, recursiva: empreendimento → torre → pavimento →
unidade → ambiente; e, em obra linear, frente → trecho → estaca. A raiz da árvore é a **obra** (é
dela que pende o teto de locais); o nível é lista fechada, porque a linha de balanço ordena por ele.
Dois vínculos **opcionais**:

- `maps_local` → `modulomaps.Local` — a torre tem coordenada, o ambiente não precisa;
- `unidade` → `empreendimentos.Unidade` — o apartamento 101 **já existe** como unidade *vendável*, e
  o `LocalObra` é o mesmo apartamento visto pela obra. Ligar os dois é o que faz o avanço apurado
  chegar ao portal do cliente sem digitação (§6); não ligar é legítimo — obra linear, reforma e área
  comum não têm unidade vendável nenhuma.

É o eixo vertical da linha de balanço e o endereço da não-conformidade.

Nasce com **gerador em lote** por padrão repetitivo (torre A, pavimentos 1–20, quatro unidades por
andar) — criar 1.600 locais à mão é o que faz o recurso não ser usado. A receita tem duas formas por
nível, **faixa** (`de`/`ate` com formato `{n}`) e **lista** (`itens`), e é **idempotente** por
`(pai, código)`. Roda em modo **simulação**: a mesma conta, sem escrever — porque o teto tem de ser
conhecido antes de o cliente descobrir que pediu 16.000 locais.

**`CalendarioTrabalho`** — jornada e dias trabalhados, por obra ou por frente, **consumindo** os
feriados que o `modulocalendar` já tem. O calendário de feriado existe; o de trabalho não — e sem ele
a duração em dias úteis é chute. Escopo em dois níveis: sem obra é o **padrão da empresa** (um por
tenant), com obra é o dela.

**`ExcecaoCalendario`** — o dia que foge da regra: recesso, parada por chuva, mutirão de sábado. A
precedência é **exceção > feriado > regra da semana** — o registro mais específico sobre aquele dia
vence. Sem ela, parar a obra uma semana exigiria editar o calendário inteiro, e o cronograma de
janeiro passaria a recontar dezembro.

> **A base de feriados é global e nasce vazia** (quem a enche é `sincronizar_feriados`). Todo cálculo
> de dia útil declara se ela está sincronizada: um calendário que promete considerar feriados e
> responde sem eles daria número errado com cara de certo.

### 4.2 Planejamento — a WBS própria

**`Cronograma`** — o plano da obra, **versionado** no mesmo padrão do orçamento: rascunho → vigente, e
replanejar cria a versão seguinte com motivo obrigatório, rebaixando a anterior. Toda versão anterior
continua legível: é a **linha de base**. O P6 vende "linhas de base ilimitadas" como diferencial sobre
o MS Project; aqui elas caem de graça do versionamento que o projeto já pratica. **Um rascunho por
vez**: replanejar com um rascunho aberto é recusado (continue nele, ou descarte-o — `DELETE` vale para
rascunho, nunca para o vigente). Ao **publicar**, as restrições **abertas** do vigente que sai passam à
atividade gêmea (mesmo código EAP) da versão que entra — o mesmo pareamento do avanço; a resolvida fica
na versão em que nasceu. O `gantt/` leva o bloco `expedientes`: a regra da semana, os feriados da
localidade e as exceções de cada expediente em uso, numa janela em volta do plano — é com ele que o
Gantt corta a barra nos dias parados. **Os feriados são os do lugar da obra**, os mesmos da Agenda
(`localidade_dos_feriados` + `modulocalendar.dias_uteis.feriados_da_localidade`): o UF/IBGE digitado no
expediente vence; sem ele, vale o endereço da obra (do expediente, ou do plano que usa o expediente da
empresa), resolvido pelo `nucleo.geo`; a lei é calculada quando a tabela não tem o ano, e o municipal
vem do dataset ou da projeção.

**`Atividade`** — a WBS **própria do PDCA**, recursiva (sintético × analítico), com dois vínculos
**opcionais** que são o coração da integração:

- **`etapa` → `obras.EtapaObra`** — o mapeamento com a macro-fase que a obra já cadastrou. Opcional
  porque o cronograma real tem granularidade que a etapa não tem, e obrigatório seria forçar a
  construtora a redesenhar o cadastro dela para poder planejar.
- **`item_orcado` → `moduloorcamento.ItemOrcado`** — a régua de custo. Vinculada, a atividade sabe
  quanto vale o que executa, e o avanço vira dinheiro sem digitação.

Carrega ainda `local` (opcional), duração, datas previstas, calendário, `eh_marco` — o `Marco` da v01
é atividade de duração zero, não uma segunda tabela — e o **peso** com que pondera o pai: derivado do
orçado quando houver vínculo, informado quando não.

**`Precedencia`** — origem, destino, tipo (`FS`/`SS`/`FF`/`SF`) e *lag*. O CPM roda sobre isso e
devolve datas cedo/tarde, folga total e livre, e o **caminho crítico**.

**Ligação de fase** *(decisão do dono, 09/10/2026: "dependências de fases")*: origem ou destino pode
ser uma **sintética** (a etapa). O CPM continua só com folhas — `services.ligacoes_das_folhas` expande a
seta de fase com a semântica de tarefa-resumo do MS Project: sai do término (FS/FF) de **todas** as
folhas da origem, sai do início (SS/SF) das folhas que **abrem** a etapa; chega no início (FS/SS) de
**todas** as folhas do destino, no término (FF/SF) das que a **fecham**. O ciclo é conferido no grafo
expandido (`verificar_rede`), e uma etapa não se liga ao que ela contém. O número de setas expandidas
tem teto do dono (`PDCA_TETO_LIGACOES_EXPANDIDAS`). *Limite declarado:* "abre" e "fecha" se leem pela
rede gravada, não pelas datas.

**A montagem é por verbos de árvore**, todos em rascunho e todos terminando numa `renumerar_eap` (o
código é posição na árvore, e nenhum gesto o calcula à mão):

| Rota | O que faz |
|---|---|
| `cronogramas/{id}/inserir-atividade/` | cria a linha **na posição** (abaixo de `depois_de`, ou no fim de `pai`) |
| `atividades/{id}/mover/` | leva a linha com a subárvore para `pai`/`posicao` — arrastar, recuar, avançar, subir |
| `cronogramas/{id}/importar-linhas/` | muitas linhas com nível, duração, marco, data mínima, peso e predecessoras (por código ou pelo Id da linha do Project), numa transação |
| `cronogramas/{id}/orcamentos/` · `gerar-do-orcamento/` | a EAP nasce da planilha orçamentária da obra, folhas ligadas ao item; corte de profundidade; `simular` |
| `cronogramas/{id}/anexar-modelo/` | traz um modelo para o **fim** de um rascunho que já existe (`aplicar-modelo/` cria o primeiro plano) |
| `cronogramas/{id}/restaurar-linhas/` | o desfazer da exclusão: recria a subárvore fotografada pela tela, no mesmo lugar e com as ligações, e devolve o mapa de ids antigos → novos; vínculo que não é desta obra volta vazio; restrições e apontamentos não voltam |

**`Risco`** — o terceiro modelo que a v01 tinha, ampliado: categoria, probabilidade, impacto,
severidade derivada, mitigação, dono (`rh.Funcionario`) e atividade opcional.

### 4.3 Execução e verificação

**`ApontamentoAvanco`** — quem, quando, onde, quanto. **Append-only**: erro se corrige por apontamento
de sinal contrário (`estorna`), não por edição — o avanço é a base de dinheiro que sai, e histórico
reescrito é dinheiro sem rastro. A trava mora no `save()` do model, e não só na API: a viewset não
expõe `PUT`/`PATCH`/`DELETE`, mas viewset é *uma* porta — o comando de bancada, a importação e a
fatia de WhatsApp entram por outras. Carrega `origem` (`web` / `whatsapp` / `app`) no mesmo idioma que
o diário já usa, e foto — **pela porta única da plataforma nos dois sentidos**. Na subida é o
`UploadValidationMixin`, que é por onde o teto de bytes e a lista de tipos do tenant já são impostos;
na descida é o recurso `pdca.avanco_foto` do `funcoesimpexp`
(`GET /api/impexp/pdca.avanco_foto/arquivo/foto/<apontamento>/`), e nunca `/media/` — que o gateway
não serve e que, num dev com `DEBUG=True`, entregaria o binário fora de auth, de entitlement e da
RLS. O JSON publica esse endereço no próprio campo `foto`, e `null` quando não há foto.

**A entrega é gateada por `pdca.avanco.view`, e não pelo par de escrita.** Apontar e ver são pessoas
diferentes (§8): exigir `pdca.avanco.apontar` para abrir a foto tiraria do planejador a evidência do
avanço que ele está conferindo — seria fechar com a régua da escrita um ato que é de leitura.

**O percentual é um delta, não um acumulado.** 30% na segunda e 25% na quinta deixam a atividade em
55%; a leitura acumulada é derivada, nunca gravada. Guardar o acumulado em coluna obrigaria a
reescrever a linha anterior a cada apontamento, que é exatamente o que o append-only proíbe.

O avanço da atividade é **derivado** dos apontamentos; o do pai, ponderado pelos filhos — e o peso da
sintética é a soma dos pesos dos filhos que têm peso, o que faz a conta da raiz ser idêntica à média
ponderada de todas as folhas, qualquer que seja o formato da árvore. **Folha sem peso não entra na
média**: ela é contada à parte, e a resposta da API declara o denominador, na mesma régua do
`realizado_cobertura` do Orçamento.

**O avanço atravessa o replanejamento pelo código da EAP**, no mesmo contrato de `comparar_com_base`.
Replanejar copia a árvore e gera ids novos: sem o pareamento, publicar a v2 de uma obra 40% executada
a mostraria em zero. O que atravessa é a **leitura**; o registro continua preso, para sempre, à
atividade da versão em que foi feito.

**Quatro recusas, antes da escrita:** sintética não recebe apontamento (o avanço dela é dos filhos);
só o cronograma **vigente** recebe (rascunho é plano que ninguém assumiu, substituído é história);
marco é 100 ou -100 (acontece ou não acontece, não fica em 40%); e o acumulado não sai de 0–100 — nem
pelo apontamento, nem pelo estorno. A escrita trava a linha da atividade: dois apontamentos
simultâneos da mesma frente leriam o mesmo acumulado e os dois passariam na conferência dos 100%.

**`Restricao`** — o *make-ready* do Last Planner: tipo (projeto, material, mão de obra, equipamento,
área, licença, decisão, clima), responsável, prazo e status. **Atividade com restrição aberta não
entra na programação** — é a regra que separa o LPS de uma lista de tarefas. A removida (resolvida)
**volta** por `reabrir/` (`pdca.restricao.remover`): carimbada (`reaberta_em/por`, `vezes_reaberta`),
com a nota da remoção preservada e o teto de abertas conferido. Viram compra no SCM as que se destravam
comprando (`TIPOS_QUE_VIRAM_COMPRA`): material → demanda de material; equipamento (locação) e mão de
obra (empreitada) → demanda de serviço.

**`ProgramacaoSemanal`** / **`ItemProgramacao`** — o que a equipe **se comprometeu** a fazer na semana.
No fim do ciclo cada item é cumprido ou não; o não-cumprido exige **causa**, escolhida de um catálogo
(`CausaNaoCumprimento`, de fábrica e extensível por tenant — a frente interditada por risco tem causa
própria, `SEG-INTERD`, em **planejamento**: liberar a frente com segurança é make-ready, e o ranking
não pode mandá-la para "externo", ao lado da chuva). O **PPC** é a razão entre os dois,
**ponderada pelo peso do compromisso** (§11.11), e o ranking de causas é o que alimenta o "Act".

Três colunas do cartão sustentam a §11.11: `peso`/`peso_origem` (quanto ele vale no índice e de onde
o número saiu, congelados quando o cartão entra no quadro) e `arrastado_de`/`vezes_arrastado` (de qual
cartão da semana anterior ele veio, e há quantas semanas está de pé). Na semana, `encerrada_antes_do_fim`
e `motivo_encerramento_antecipado` marcam o ponto apurado antes do prazo.

### 4.4 Contrato, medição, aditivo

> **De onde vem a régua desta fatia** *(levantamento de 15/09/2026, pedido pelo dono: "pesquise como
> grandes sistemas fazem e analise o melhor jeito")*. Três sistemas foram olhados, e cada um decidiu
> uma coisa aqui:
>
> - **AIA G702/G703** — o formulário de medição que o mercado americano usa há décadas. Dele vêm as
>   **colunas e a ordem delas**, que é a ordem em que a conferência acontece: contratado original →
>   aditivos → contratado atual → acumulado anterior → este período → **material estocado** →
>   acumulado → % → saldo. Faltavam quatro dessas colunas, e o *material presently stored* trouxe
>   junto a regra de que ele é **saldo, não delta**.
> - **Procore** — a fatura/medição é **documento de primeira classe**, com tela própria, rascunho que
>   se salva para continuar depois e workflow de aprovação roteado. Daí a decisão de dar endereço
>   próprio à medição e separar *apurar* de *boletim*. O rascunho negociado antes de virar documento
>   oficial tem nome lá (*pencil copy*) — é a nossa prévia, com a diferença declarada: a prévia é
>   **leitura**, porque duas superfícies editáveis para o mesmo número foi exatamente o defeito que a
>   primeira escrita desta tela teve.
> - **Sienge** — o vocabulário e o fluxo brasileiros: contrato → medição → **boletim** (relatório
>   próprio) → liberação para pagamento → aditivo. E a lembrança de que o boletim soma mais do que
>   bruto menos retenção: *"totais retidos como sinal, permuta ou imposto, descontos, faturamento
>   direto"* — que virou a `DeducaoMedicao` tipada.
>
> O que **não** se copiou: o medir por %, por quantidade ou por valor do Sienge. Aqui a entrada é
> **quantidade**, com o percentual espelhado e não editável *(decisão do dono, 15/09/2026)* — três
> caminhos para o mesmo número dão três arredondamentos para a mesma linha.

**`ContratoObra`** — obra, `fornecedor` (o cadastro único, que já é neutro quanto a ser de material ou
de serviço), objeto, **regime** (preço unitário, preço global, administração), vigência, garantia e a
cláusula de **retenção** (percentual, natureza e condição de liberação). Carrega **`regime_publico`**
e, quando ligado, o **limite legal de acréscimo** — *selecionado pelo usuário, não imposto pelo
sistema* (§11.3).

**`ItemContrato`** — com `item_orcado` **opcional**: contratado contra a régua do orçamento aprovado.
Quantidade contratada e preço unitário. A trava que o mercado ensina: **medição acumulada não pode
exceder contratado + aditivos**.

> **Quando a planilha fecha para edição direta: quando alguém já mediu contra ela.** Não é o status
> do contrato — é o uso. Antes da primeira medição em voo não há nada a preservar: nenhum número foi
> calculado sobre a planilha e nenhum título saiu, então corrigir uma quantidade é corrigir um
> cadastro. Depois, mudá-la reescreveria o denominador de um documento assinado, e o caminho é o
> **aditivo**. Medição cancelada ou reprovada não fecha nada, pela mesma régua do `_EM_VOO` que
> governa o acumulado.
>
> A regra é **uma função** (`services.planilha_editavel`) que a view aplica e o serializer publica
> (`planilha_editavel`, `planilha_fechada_porque`). As duas coisas importam: fechar só na tela deixa
> a API, o comando de bancada e a aba velha passando por fora; e deixar a tela reimplementar a regra
> foi o que produziu, em 15/09/2026, uma tela dizendo *"não se edita mais aqui"* enquanto a API
> aceitava a edição ([D142](../historico-correcoes.md)).

**`AditivoContrato`** / **`ItemAditivo`** — acréscimo, supressão, revisão de preço, inclusão de item
e prorrogação, com objeto, **justificativa** e escada de aprovação própria
(`pdca.aditivo.edit|aprovar` — montar e autorizar são de pessoas diferentes, como apurar e atestar).
O efeito no custo já existe do outro lado — `RevisaoOrcamento` do tipo `aditivo` — e o PDCA amarra o
documento, o saldo e o prazo a ele.

> **O contratado original nunca é reescrito.** `ItemContrato.quantidade_contratada` é o do dia da
> assinatura, e o que vale hoje é **derivado**: `atual = original + Σ deltas de aditivos aprovados`
> (§4.9 — derivar, não guardar a segunda verdade). Toda trava do módulo confere contra o *atual*;
> nenhuma confere contra o campo. A consequência é que a linha **nascida de aditivo** tem quantidade
> original zero e a quantidade inteira no `ItemAditivo` — é o que faz a regra valer sem exceção em
> nenhuma linha, e é a única razão de a `CheckConstraint` de quantidade positiva ter a ressalva do
> `aditivo_origem`.
>
> **O preço é a exceção declarada**: ele é reescrito na linha do contrato, porque o `ItemMedicao`
> congela o preço do dia e nenhuma medição passada é afetada — e o `ItemAditivo` guarda o anterior,
> senão "revisou o preço" não diz de quanto para quanto.
>
> **As três travas** (`services.validar_aditivo`): a quantidade final de um item **nunca** cai abaixo
> do que já foi medido e estocado; no regime público o acréscimo acumulado é conferido contra o
> contratado **original** e o limite **digitado** no contrato (25% + 25% são 56% do assinado, não
> 50% — conferir contra o valor já aditado é o erro que a lei existe para impedir); e aditivo em
> rascunho ou na escada **não move saldo nenhum**, como o rascunho de medição.
>
> **O aditivo se monta como um contrato.** O rascunho tem cabeçalho editável (`cabecalho/`: objeto,
> justificativa, assinatura, prorrogação e **nova retenção do contrato**) e linhas reescritas de uma vez
> (`itens/`). A retenção anda em dois níveis: `retencao_percentual_nova` muda a cláusula do contrato na
> aprovação; `ItemAditivo.retencao_percentual` dá **retenção própria** ao item que a linha traz ou mexe
> (`ItemContrato.retencao_percentual`). A medição copia a do item para a linha no dia em que nasce
> (`ItemMedicao.retencao_percentual`), e a retenção do boletim é `base × geral + Σ valor da linha ×
> (própria − geral)`. Aditivo só de retenção é aditivo válido.

**`DeducaoMedicao`** — o que sai do bruto **além** da retenção contratual, tipado (INSS, ISS, IRRF,
amortização de adiantamento, material fornecido pela contratante, multa, outros). A diferença entre
dedução e retenção não é contábil, é de destino: retenção é dinheiro que a construtora **segura e
devolve** quando a cláusula é cumprida; dedução é dinheiro que **não volta**. Somar as duas num
percentual só faria a `LiberacaoRetencao` oferecer de volta imposto que nunca foi da construtora.
Percentual **ou** valor, nunca os dois (constraint no banco), com a base declarada quando o
percentual não incide sobre o bruto inteiro.

**`Medicao`** / **`ItemMedicao`** — o boletim do período. **Nasce do avanço**, não ao lado dele
(§11.4): o sistema propõe a quantidade a partir dos apontamentos do período, o gestor confere, ajusta
e só então submete. Bruto → retenção → **deduções** → **líquido**, e o líquido vira `conta_pagar_ref`
no ERP.

> **Material estocado é saldo, não delta.** `ItemMedicao.quantidade_estocada` é a coluna E da G703
> (*materials presently stored*): material posto na obra, pago e ainda não aplicado. Cada medição
> declara o estoque que existe **naquele momento**, e o que se paga de material nela é a **diferença**
> contra o que a anterior declarava — fosse delta, um estoque parado dois meses apareceria como zero
> e ninguém veria que há material pago sem aplicar. Quando o material é aplicado, o estoque cai e a
> quantidade executada sobe: as duas diferenças se cancelam, e por isso **ninguém paga duas vezes**
> pela mesma unidade. O acumulado que trava soma executado **mais** estocado, porque os dois ocupam
> contrato.
>
> **Os períodos são uma corrente.** A próxima medição começa no dia seguinte ao fim da anterior
> (`/contratos/{id}/periodo-sugerido/`), e período que **se sobrepõe** ao de outra medição em voo é
> recusado: dois períodos que se cruzam pagam o mesmo avanço duas vezes, e a trava do acumulado só
> perceberia quando a soma estourasse o contratado — que pode ser muitos meses depois. A
> retificadora é a exceção declarada: ela repete o período de propósito, porque está corrigindo
> aquele período.

> **Como a proposta encontra o avanço.** O `ItemContrato` tem **dois** vínculos opcionais, e eles não
> são redundantes: `item_orcado` é a *régua de custo* (contratado contra o orçamento aprovado) e
> `atividade` é a *ponte do avanço*. Na obra com orçamento os dois se encontram sozinhos — a
> `Atividade` já carrega `item_orcado` desde a PDCA.1 —; o vínculo direto existe para a obra que **não
> tem orçamento**, que senão não conseguiria medir a partir do avanço. Havendo mais de uma atividade
> na mesma linha, a média é **ponderada pelo peso** (o mesmo `peso_de` da árvore do avanço) e a
> resposta **declara o critério**: sem peso em nenhuma, cai para média simples e diz isso.
>
> **O que congela, e o que continua derivado.** O `ItemMedicao` guarda a quantidade **e o preço
> unitário do dia**, do jeito que uma nota fiscal guarda — não é agregado, é o *insumo* congelado, e
> sem ele corrigir um preço de contrato em 2027 reescreveria o valor de uma medição paga em 2026.
> Bruto, retenção, líquido, saldo e acumulado continuam somados na leitura (§4.9).
>
> **Três somas diferentes de "já medido", e confundi-las é o erro caro.** O acumulado que **trava**
> conta as medições aprovadas *e* as que estão na escada — contar só as aprovadas deixaria duas
> medições subirem em paralelo, cada uma passando sozinha e as duas juntas estourando o contratado. O
> **retido disponível** conta só as aprovadas, porque retenção que ainda não foi descontada de nada
> não é dinheiro retido. E o **rascunho não ocupa saldo**: ele é intenção, e somá-lo faria o saldo
> encolher quando o gestor abre uma medição só para estudar.

**`LiberacaoRetencao`** — o dinheiro retido voltando ao empreiteiro *(decisão do dono, 14/09/2026: a
liberação entra na PDCA.3, e não numa fatia posterior — reter sem poder liberar deixa o ciclo do
dinheiro pela metade)*. Tem **escada própria**, e não herda a da medição: quem ateste medição confere
*serviço executado*; quem libera caução confere *condição contratual cumprida* — perguntas diferentes,
em momentos diferentes, muitas vezes por pessoas diferentes. O teto é o saldo **derivado** (retido nas
aprovadas − já liberado), e o título que ela gera é **próprio**, nunca uma baixa na conta da medição
que reteve: aquela conta pode já estar quitada, e a retenção costuma voltar meses depois com
vencimento seu.

**O regime de administração mede custo, e o custo é declarado** — *e a tela do módulo segue isso até
o fim*: a prévia e a medição de um contrato por administração mostram o **custo**, não a grade de
itens, porque ali os itens não entram na conta. Mostrá-los era oferecer um instrumento que não vale
no regime ([D143](../historico-correcoes.md)). A planilha contratual continua valendo como
referência de custo, e o cockpit diz isso onde o gestor procuraria a grade. `Medicao.custo_reembolsavel` não sai
do avanço nem de nenhum lançamento que o sistema tenha hoje — quem o conhece é a folha, a nota do
material e o aplicado do SIL. Enquanto a PDCA.9 e o seam do SIL não chegam, ele é **digitado**, e o
campo `custo_origem` viaja junto dizendo *"informado pelo gestor"*. *(Decisão do dono, 14/09/2026: o
regime entra com custo manual. A régua de dado honesto é cumprida **declarando a origem**, não
escondendo o número: no dia em que a apropriação existir, `apropriado` entra sem migração de dado e
sem reinterpretar o passado.)*

**`FluxoAprovacao`** / **`NivelAprovacao`** / **`Atesto`** — a aprovação em **mais de um nível**
(§11.5): engenheiro → gerente de contrato → fiscal, cada nível exigindo uma permissão e registrando
atesto com autor, data e observação. Aprovada no último nível, a medição **congela**; correção exige
medição **retificadora**, nunca edição.

> **A retificadora substitui a original, não soma a ela.** Nasce como cópia inteira da aprovada
> (linhas, estoque, descontos, retenção e taxa do dia) e guarda a medição **corrigida inteira**.
> Aprovada, a original vira `retificada` — legível, fora de toda soma — e só uma medição vale por
> período. Enquanto a retificadora sobe a escada, a original sai do acumulado (`_fora_da_conta`) para o
> período não contar duas vezes; para o estoque de material, a retificadora ocupa o lugar da original
> na corrente (`posicao_da_medicao`). **O título acompanha** (`_fechar_retificacao`): título da original
> em aberto → cancelado, e nasce o do líquido inteiro da corrigida; título já pago (inteiro ou em
> parte) → nasce o **título da diferença** (complemento a pagar; ou, se a corrigida é menor, o saldo em
> aberto do título cai primeiro e o resto vira devolução contra a mesma contraparte, achada pelo
> CNPJ/CPF do outro lado do cadastro) e o ERP recebe aviso de **nível 3** ([funcoesnotificacoes](funcoesnotificacoes.md)).
> Retificadora retirada antes de valer é **apagada** (não fica "cancelada" no contrato); a aprovada não
> se cancela — corrige-se retificando de novo. A tela mostra o quadro original | corrigido | diferença
> e a conciliação do líquido, com o efeito no saldo do contrato e no ERP.

> **Onde essa máquina mora.** Fluxo de aprovação não é assunto de obra — é da plataforma, e o ERP e o
> SCM vão pedi-lo. Nasce em **`nucleo`**, com o PDCA como **primeiro cliente**, pelo mesmo raciocínio
> que pôs a gerência de frota em `nucleo` e não na Prancheta: *a Prancheta é a primeira cliente, não a
> dona*.
>
> **Como ela ficou (PDCA.0).** Rota `/api/aprovacao/`; o alvo é um `ContentType`, e não o par de FKs
> nuláveis do `modulomaps.Local`, porque aqui o conjunto de alvos é aberto por desenho — o `nucleo` é
> importado por todos e não pode importar nenhum de volta. Quem for alvo declara uma `GenericRelation`
> e o pedido morre junto com o objeto. Quatro regras que a tela não redecide: **quem solicitou não
> ateste** (salvo `permite_autoatesto`, escolha escrita do cliente para a obra pequena); a permissão é
> a **do degrau atual**; **reprovar encerra** em qualquer degrau; e **uma escada por objeto**,
> garantida por constraint parcial no banco. Terminada a escada, o `nucleo` emite o sinal
> `aprovacao_concluida` — congelar a medição e gerar o título é do módulo dono do alvo. Falha de um
> receptor **não** desfaz o atesto: a decisão de quem tem alçada é verdade independente de o efeito
> colateral ter dado certo.
>
> **Configurar a escada é do administrador do tenant** (`plataforma.fluxo_aprovacao.edit`). Criar um
> degrau que exige a permissão X é decidir quem tem alçada sobre o dinheiro — mesma classe de ato que
> `plataforma.papel.gerir`. Uma persona de fábrica com esse verbo poderia rebaixar a escada que a
> controla.

### 4.5 Qualidade, segurança e entrega — uma máquina, quatro domínios

FVS, checklist de segurança, vistoria de entrega e inspeção ambiental são **a mesma coisa**: um modelo
de verificação aplicado a um objeto, item a item, com resultado e evidência. Três cópias divergiriam
na primeira mudança de requisito.

**`ModeloVerificacao`** / **`ItemModeloVerificacao`** — o template, com `dominio` (`qualidade` ·
`seguranca` · `ambiental` · `entrega`).

**`Verificacao`** / **`ItemVerificacao`** — a ficha aplicada: obra, local, atividade opcional,
inspetor, data; cada item conforme / não conforme / não aplicável, com observação e foto. Reprovação
**parcial** é o caso normal, não a exceção.

**`NaoConformidade`** — nasce de um item reprovado ou avulsa. Obra, local, atividade opcional,
gravidade, foto — e **`marcacao_prancheta` opcional**, que a ancora ao pino sobre o desenho e a exporta
em BCF junto com o resto.

**`PlanoAcao`** (5W2H) — o quê, por quê, onde, quando, quem, como, quanto; tipo **corretiva** ou
**preventiva**, as duas que o PBQP-H exige. **`VerificacaoEficacia`** fecha o laço: a não-conformidade
**não encerra** enquanto a eficácia não for verificada e registrada. É o padrão do SAP QM, e é o que
separa tratar de arquivar.

### 4.6 SSMA

**`DialogoSeguranca`** (DDS) + **`ParticipanteDDS`** — a roda antes do turno e a **lista de presença**,
que é a única parte do DDS que prova alguma coisa. Encerrar fecha a lista (nome acrescentado três dias
depois não é presença) e **escreve no Diário de Obra**: o diálogo faz parte do que aconteceu na obra
naquele dia. O DDS **não é obrigatório por nome em norma nenhuma** — "diálogo" aparece uma vez nas NRs,
na NR-1 item 1.4.4.1 —, e é o principal **indicador proativo** que a construtora tem.

**`Ocorrencia`** + **`AnexoOcorrencia`** — do quase-acidente ao óbito, com os campos da CAT que **só a
obra conhece** (hora, agente causador, situação geradora, parte do corpo e lado, último dia trabalhado,
horas trabalhadas antes, registro policial) e o bloco clínico atrás de verbo próprio, que é a **primeira
PII do grupo `pdca`**. `registrar` e `classificar` são verbos separados: quem é medido não classifica a
própria medida. A CAT é **devida mesmo sem afastamento**; o sistema avisa o prazo (1º dia útil; imediato
na morte) e guarda o protocolo — **a transmissão do evento eSocial S-2210 é da folha**, e uma segunda
porta para um ato com prazo legal criaria duas verdades sobre se a CAT foi comunicada.

**O EPI não tem modelo aqui** *(decisão do dono, 20/09/2026)*. `EntregaEPI` vive em
[`modulosil`](modulosil.md) desde 25/07/2026, completo — item do catálogo, colaborador do RH, CA e
validade, troca, devolução, baixa de estoque. Recriá-lo produziria duas verdades sobre o mesmo capacete
(o saldo podendo baixar sem a ficha existir, e a ficha existindo sem o saldo baixar) e contradiria a §7
desta planta, que diz que o PDCA **não** movimenta estoque. A SSMA **lê**, sob `sil.epi.view`, com a
indisponibilidade declarada quando o tenant não contrata o SIL. O grão é a **obra**, e não a frente:
dizer quem está com EPI vencido *numa frente* exige saber quem está em qual frente, e isso é `Efetivo`,
da PDCA.9.

*(A versão anterior desta seção mandava a fatia criar `EntregaEPI`, em contradição com a §7. O desenho
mudou, e é por isso que o texto mudou.)*

### 4.7 Apropriação e produtividade

**`Equipe`**, **`Efetivo`** (quantos, onde, quando) e **`ApropriacaoHH`** (horas por atividade). Com o
coeficiente da composição do orçamento, isso produz **produtividade real × prevista** e permite o EVM
em **homem-hora** ao lado do EVM em custo — as duas curvas que o P6 mostra e o MS Project não.

### 4.8 Pós-obra

**`Vistoria`** de entrega sobre a `LocalObra` (a unidade), gerando **punch list**; **`Garantia`** por
sistema construtivo com prazo contado da entrega; **`ChamadoGarantia`** ligado ao cliente. É o "Act" do
empreendimento inteiro, e reaproveita a mesma máquina de verificação da §4.5.

### 4.9 O que é derivado, e não tem tabela

Curva S física, curva S financeira, PV/EV/AC, SPI/CPI, PPC, produtividade, saldo de contrato e caminho
crítico são **calculados**. Guardá-los criaria a segunda verdade que diverge da primeira — o erro que
o `services.componentes_da_composicao` do Orçamento já corrigiu ao virar leitura única.

## 5. A tela — o que o PDCA precisa, não o que os outros módulos fizeram

*(Decisão do dono, 22/08/2026: **o frontend do PDCA não segue a forma dos outros módulos.** Cada
módulo tem necessidade própria, e a desta é pesquisada e resolvida aqui.)*

A [régua §1.6](../frontend.md) já dizia isso — *"a régua é o espírito, não a forma"*: mesma
profundidade, facilidade e costura com a expansão; **não** os mesmos cards, lentes e nomes. O seletor
"Operação × Território" do Maps e o "Campo × Acervo" da Prancheta resolvem o problema **daqueles**
domínios. Copiá-los aqui seria repetir forma sem herdar razão.

### 5.1 A diferença estrutural: a unidade de trabalho é a OBRA

Este é o primeiro módulo do SGI cuja unidade de trabalho **não é o tenant**. O SCM compra para a
empresa, o SIL move estoque da empresa, o ERP é a empresa inteira — todos são transversais, e por isso
abrem num hub que soma tudo. **Nada no PDCA existe fora de uma obra:** cronograma é de uma obra,
contrato é de uma obra, PPC é de uma obra, FVS é de uma obra.

Consequência de tela, e é a primeira decisão de desenho: a entrada do módulo é a **escolha da obra**,
e ela **persiste** como contexto de trabalho enquanto a pessoa estiver ali — não é um filtro que se
reaplica em cada página. Um hub que somasse cronogramas de sete obras produziria um número que não
serve para decidir nada.

Acima do contexto existe **uma** leitura multi-obra, e ela é para quem dirige, não para quem planeja:
o painel de carteira — SPI/CPI, PPC e desvio de prazo por obra, lado a lado, com a obra em pior estado
na frente.

### 5.2 O desenho da tela mora em documento próprio

A primeira escrita desta seção descrevia cinco instrumentos e virou, na construção, um conjunto de
páginas soltas no menu — um assunto do banco por porta. O desenho foi refeito do zero sobre o eixo
que o mercado provou (cadência, não assunto), e vive agora em
**[modulopdca-frontend.md](modulopdca-frontend.md)**: os seis postos de trabalho, a espinha que os
atravessa, a superfície de campo, o que o desenho cobra do backend e o faseamento.

O que continua valendo daqui: a **unidade de trabalho é a obra** (§5.1), **quem usa o quê** (§5.3) e
os limites que a construção do Gantt fixou (§5.4).

#### As cinco rotas que não são recurso de router

A API do módulo é um `DefaultRouter` sobre 24 recursos, mais `status/` e **cinco leituras que
atravessam** — registradas à mão em `urls.py` porque não têm dono:

| Rota | O que devolve | Permissão |
|---|---|---|
| `GET /api/pdca/carteira/` | As obras lado a lado, com as pendências discriminadas. `?obras=1,2` recorta | só o módulo; cada coluna cobra a sua |
| `GET /api/pdca/hoje/?obra=N` | **Fila + pulso + o que mudou**, numa leitura. `?mudancas=0` e `?dias=` ajustam a terceira | idem |
| `GET /api/pdca/busca/?q=` | As sete espécies do módulo, sem acento, cortadas por espécie. `?obra=N` restringe | idem |
| `GET /api/pdca/minhas-frentes/` | **O que está no nome de quem pede**, na semana corrente: compromisso, trava, conserto e ficha. `?obra=N` recorta; `?como=` troca o nome procurado | idem |
| `GET /api/pdca/medicao/?obra=N` | **Os contratos com saldo + a fila do dinheiro**, numa leitura (B3): boletim parado em rascunho, boletim esperando atesto, retenção pedida e aditivo sem decisão | idem |
| `GET /api/pdca/contratos/{id}/ficha/` | **A ficha do contrato**: os títulos do ERP (emitido, pago, em aberto — um título contado uma vez), os itens com medido e saldo, e a linha do tempo (medições, inclusive a retificada, aditivos e liberações) | `pdca.contrato.view` |
| `GET /api/pdca/qualidade/?obra=N` | **O laço aberto + o painel de conformidade** (B8). A fila é a das quatro faixas de retrabalho da fila do dia (`faixas_da_qualidade`); o painel vem nulo, com a permissão nomeada, para quem não vê NC. `?desde=&ate=` recortam o painel | idem |
| `GET /api/pdca/seguranca/?obra=N` | **A fila da SSMA + os indicadores + as frentes interditadas** (B9). A fila é a das três faixas de prazo legal e segurança (`faixas_da_seguranca`); as taxas de frequência e de gravidade voltam nulas com a frase. O EPI vencido **não** vem aqui — exige a permissão do SIL, e fica em `ocorrencias/epi-vencido/` | idem |

As cinco declaram **só `RequireModule`**, e o recorte por permissão acontece dentro do serviço —
uma leitura que junta cinco assuntos não tem um recurso dono, e exigir um recusaria a página a
quem trabalha nos outros quatro. O desenho e as três regras que elas seguem estão na
[§10.1 do documento da tela](modulopdca-frontend.md).

**A do posto da medição atravessa assunto, e não obra**, e é o caso que mostra por que a régua não é
formalidade: ela junta contrato e medição, que têm permissões diferentes. Exigir `pdca.contrato.view`
no portão recusaria o posto inteiro a quem só ateste — que é justamente quem mais o usa. E ela
existe como leitura única porque a alternativa é a tela pedir `contratos/` e depois `saldo/` **uma
vez por contrato**: numa obra com doze empreiteiros, treze idas ao servidor para desenhar doze
linhas, cada resposta de um instante diferente. O saldo de cada linha é o mesmo
`saldo_do_contrato` que `GET contratos/{id}/saldo/` devolve — não há segunda soma, e o E2E cobra a
igualdade campo a campo.

**A frente do canteiro casa por nome, e não por FK**, porque `responsavel`, `quem` e `inspetor` são
rótulo durável em todo o módulo — a decisão é anterior a esta leitura e está nos próprios modelos:
quem assume a frente é com frequência o encarregado da empreiteira, e quem destrava é o projetista
ou o fiscal da prefeitura. O casamento é sem acento e sem caixa, e a resposta diz **contra qual
nome** procurou; `?como=` existe para quem o escritório registrou com outro rótulo.

### 5.3 Quem usa o quê

| Quem | Onde | Instrumento |
|---|---|---|
| Planejador | Escritório, tela grande | Gantt, linha de balanço, linha de base |
| Engenheiro de obra | Canteiro, tablet | Quadro de programação, apontamento, restrições |
| Encarregado / mestre | Canteiro, celular ou WhatsApp | Apontar avanço, abrir NC com foto |
| Gestor de contratos | Escritório | Grade de medição, saldo, aditivo |
| Técnico da qualidade | Canteiro | Verificação item a item, plano de ação |
| Fiscal / gerente | Onde estiver | Fila de atesto — decidir, com o que precisa para decidir junto |
| Diretor | Escritório | Carteira multi-obra: avanço × linha de base, PPC, conformidade, segurança |

> **SPI e CPI saíram desta linha, e a saída é decisão.** As duas são de valor agregado: o SPI exige
> valor planejado por período e o CPI exige **custo real**, que mora no ERP e ainda não é apropriado
> por atividade (é a PDCA.9). Prometer as siglas e calculá-las com o que há hoje daria índice com
> nome de norma e conta inventada — a mesma recusa que as taxas de frequência e gravidade da §4.6
> já fazem. A carteira entrega as quatro leituras que o módulo **mede**, e cada uma diz em cima de
> quantos serviços foi feita.

### 5.4 O que a construção do Gantt fixou — e os limites declarados

O desenho acima é a intenção; abaixo estão as decisões que só aparecem quando a ferramenta existe, e
os limites que ela assume de olhos abertos.

- **A rede se digita.** A coluna **Predecessoras** aceita `1.2FS+3d; 1.4SS` e é a via principal de
  montar a rede — ninguém liga 800 setas com o mouse. A referência é o **código da EAP**, não o
  número da linha (que muda quando alguém insere uma atividade acima). *Limite:* um código que
  contenha `+` ou `-` não é endereçável nessa coluna; a ligação dele se faz pelo inspetor.
- **Desfazer é o gesto inverso, não um retrato do plano.** O dono do cronograma é o servidor, que
  recalcula o CPM a cada escrita: restaurar um retrato local mostraria um plano com que o backend
  não concorda. *Limites:* **publicar e replanejar zeram a pilha** (viram compromisso da obra, e
  desfazer compromisso pelas costas de quem o assumiu é pior que não ter desfazer); e **excluir uma
  sintética não é desfazível** — a cascata leva a subárvore, e prometer recompô-la seria prometer o
  que a tela não guardou. A folha, essa volta inteira, com as setas que chegavam nela.
- **Renumerar a EAP é um ato explícito, em duas passadas.** O código é único por cronograma, então
  renomear `1.2` para `1.1` enquanto `1.1` existe bate na trava do banco: a primeira passada leva
  todos para um código temporário, a segunda assenta o definitivo. Custa o dobro de escritas — e é
  por isso que a renumeração **não** acontece sozinha a cada indentação.
- **A curva S tem duas linhas, e as duas vêm do servidor.** O previsto é o peso distribuído nos
  **dias úteis do calendário de cada atividade** — a mesma régua com que o CPM produziu as datas —, e
  o realizado nasce do apontamento. Ela era calculada no cliente até a PDCA.1b, por dias corridos e
  com a aproximação declarada; com as duas linhas no mesmo gráfico isso deixou de servir, porque o
  número que a reunião lê é o **desvio entre elas**, e ele carregaria o erro de fim de semana da
  aproximação. A realizada **para no último apontamento**: continuar reta até o fim do plano seria
  lida como "em dia" onde ninguém apontou. *Limite declarado:* a curva financeira cobre só as folhas
  vinculadas ao orçamento, e a tela diz quantas ficaram de fora.
- **O plano vira padrão, e o padrão vira obra nova.** *(Decisão do dono, 23/08/2026.)* Marcar um
  cronograma como **modelo** o põe na biblioteca da empresa, com nome único; aplicá-lo cria o
  **primeiro** plano de uma obra que ainda não tem. O que se repete é a **estrutura** — WBS, durações
  e rede —, nunca as datas: elas nascem do calendário e da âncora da obra nova. E os vínculos com
  local, etapa e item orçado **ficam para trás de propósito**: eles são da obra de origem, e um plano
  ponderando avanço pelo orçamento de outra obra é um erro que não aparece na tela e sai no boletim
  de medição. *Limites:* o modelo é uma marca no cronograma, e não uma tabela à parte — um modelo
  **é** um cronograma, e duplicar a estrutura numa segunda tabela faria a biblioteca divergir do que
  ela produz; a quota (`planos_modelo`) é de plano, porque o que se vende não é guardar cronograma,
  é ter biblioteca de padrão para replicar.
- **Colar é uma requisição; renumerar é outra.** A escrita em lote (`lote/`) aplica até
  `PDCA_TETO_LINHAS_POR_LOTE` células numa transação — e o passo inteiro entra no desfazer como
  **um** só —, e a tela fatia pelo número que o `status/` declara, não por uma cópia envelhecendo no
  bundle. O mesmo endpoint é o seam por onde a importação de MS Project/P6
  ([funcoesimpexp](funcoesimpexp.md)) vai entrar. A **renumeração da EAP não passa por ali**: o
  código é único por cronograma, então todos os que mudam precisam ir para um nome temporário antes
  de qualquer definitivo, e as duas passadas têm de caber na mesma transação. Fatiar em blocos faria
  um código do segundo bloco colidir com o primeiro — por isso ela tem endpoint próprio, limitado
  pelo teto da **árvore**, com prévia antes de mexer em dezenas de códigos de uma vez.
- **A grade da semana é a física 4 aplicada ao avanço.** O apontamento na web não ganhou tela própria
  nem formulário por atividade: virou **planilha com trava**, no mesmo molde da grade de medição
  ([o desenho](modulopdca-frontend.md)) — a fila abre no que *deveria estar acontecendo hoje*, ordenada por crítica → vencida → vence
  antes (não pela EAP), com o previsto e o acumulado ao lado do campo de digitar, e o envio inteiro
  numa transação. **O que se digita é o delta**, e não o acumulado: "andou 15% esta semana" é a
  pergunta que alguém no canteiro responde olhando o serviço; "está em 65%" é uma conta que ele faria
  errado. O caminho do celular e do WhatsApp (§9) continua sendo outro, e a coluna `origem` do
  apontamento já existe para quando ele chegar.
- **O estorno aparece como linha, não como sumiço.** A tela risca o lançamento corrigido e mostra a
  correção ao lado, com o motivo — quem confere a medição daqui a dois anos precisa ver o que foi
  apontado, o que foi corrigido e por quê. *Limite:* estorno não se estorna; quem errou a correção
  aponta o avanço de novo.
- **O executado mora dentro da barra prevista.** No Gantt o avanço é o preenchimento escuro dentro da
  barra, no molde do "% concluído" do MS Project, e nunca uma segunda barra ao lado — duas barras
  seriam lidas como dois períodos, e o avanço é uma fração *desta* atividade.
- **O calendário que a tela oferece é o que o cálculo usaria.** `?para_obra=` devolve **o da obra
  mais os da empresa** (os de `obra` nula, que existem para valer em todas), com o específico antes
  do geral — a mesma ordem de precedência de `services.calendario_da_obra`. Perguntar pelo filtro
  exato `?obra=` escondia os da empresa e deixava o select vazio numa empresa que tinha expediente
  ([D118](historico-correcoes.md)). *Limite declarado:* plano **sem** calendário continua podendo
  nascer — nulo é a resposta honesta "a empresa ainda não disse quando trabalha" —, mas o CPM recusa
  calcular, e a tela diz isso na hora de escolher em vez de deixar descobrir depois.
- **A bancada é de quem planeja.** Colunas visíveis, ordem, larguras e a divisória do split view
  vivem no `localStorage` — é o formato da mesa de trabalho, não preferência de conta.

## 6. Integrações — o que conversa no backend conversa na tela

| Com quem | O que atravessa |
|---|---|
| [Orçamento](moduloorcamento.md) | Régua orçada por etapa/atividade; a **curva S financeira passa a derivar do cronograma físico**, em vez de a distribuição por competência ser digitada; aditivo ↔ `RevisaoOrcamento` |
| [SIL](modulosil.md) | Aplicado de material por `(obra, etapa)` ao lado do avanço físico — consumo × produção; o compromisso da semana pede o material (requisição) e o apontamento avisa a baixa que falta (§6.1) |
| [SCM](moduloscm.md) | Restrição de material, equipamento ou mão de obra vira **demanda** (✅ PDCA.5 — `Demanda.origem = restricao`, uma por restrição; equipamento e mão de obra como serviço) e acompanha o pedido; o cronograma puxa a compra (`origem = plano`); o contrato de empreitada mede o pedido de serviço (§6.1) |
| [ERP](moduloerp.md) | Medição aprovada → **título líquido** → `ContaPagar`. O ERP decide quando sai do caixa. **E a fronteira anda nos dois sentidos**: cancelar a medição aprovada cancela o título junto, na mesma transação — a menos que ele já tenha recebido baixa, e aí a recusa manda retificar (§11.12) |
| RH | Responsável, equipe, efetivo, DDS, EPI |
| [Diário](modulodiario.md) | Apontamento e NC podem **nascer no diário do dia**, inclusive por WhatsApp; e o diário passa a mostrar o que estava programado |
| [Prancheta](moduloprancheta.md) | NC ancorada no desenho (`Marcacao`), exportada em **BCF** com o resto |
| [Maps](modulomaps.md) | `LocalObra.maps_local` — a frente de serviço no mapa |
| Clientes | Avanço **apurado** no portal, no lugar do digitado; vistoria e chamado de garantia |
| [funcoesia](funcoesia.md) | Causa de não-cumprimento sugerida; foto de NC classificada — o módulo é **consumidor**, sem cliente de IA próprio |
| [funcoesimpexp](funcoesimpexp.md) | Importar cronograma de MS Project/P6 e exportar medição, verificação e curva S |

### 6.1 PDCA × Orçamento × Suprimentos × Estoque — o cronograma puxa a compra

*(Decisão do dono, 09/10/2026: "quero que o PDCA, o orçamento, os pedidos e o estoque se conversem".)*
O motor mora em [`modulopdca/suprimentos.py`](../../backend/modulopdca/suprimentos.py) e importa os
outros três tarde (o plano carrega sem eles).

- **Quem consome quanto** (`consumo_do_plano`, a regra única): atividade ligada a item orçado → a linha
  dividida entre as atividades que a citam, pela duração; sem vínculo, os itens do orçamento vigente da
  **etapa** que nenhuma atividade cita caem na atividade da etapa que começa primeiro. Atividade ligada a
  item de **revisão anterior** é lida pelo item de mesmo código EAP na vigente (`religar-orcamento/`
  grava o vínculo — só rascunho — e o peso do avanço acompanha). O executado sai da conta (`1 − avanço`).
- **Quando**: chegar até = início − antecedência; antecedência da **atividade**
  (`Atividade.antecedencia_compra_dias`) > do **insumo** > **padrão da obra** (`AntecedenciaDeCompra`,
  por obra, item nulo = padrão) > zero. *Pedir até* desconta o menor prazo de entrega das ofertas.
- **Quanto falta**: por insumo e na ordem das datas, abate o saldo livre do canteiro da obra, o que os
  pedidos em aberto do centro de custo da obra ainda devem e o que as demandas sem pedido pedem. Saldo em
  outro almoxarifado (central, outra obra) **não abate** — vira o aviso "transfira antes de comprar".
- **A fila** (`GET cronogramas/{id}/suprimentos/`; o Suprimentos lê a mesma por insumo juntando as obras
  vigentes) vira **demanda em rascunho** (`suprimentos/gerar-demanda/`, exige `scm.demanda.edit`;
  `Demanda.origem = plano`; centro de custo da obra criado se faltar). Gerar duas vezes não compra duas.
- **Restrição acompanha a compra**: o serializer traz `compra` (demanda → cotação → pedido → recebido) e
  `sugerir_destravar` quando tudo o que foi pedido chegou; destravar segue da pessoa.
- **Semana → almoxarifado**: `itens-programacao/{id}/pedir-material/` (exige `sil.requisicao.edit`)
  cria a requisição em rascunho do canteiro, apropriada à obra e à etapa, com a quantidade da semana
  (total × % previsto, sem passar do que falta); `ItemProgramacao.requisicao_sil` guarda o vínculo.
- **Apontamento avisa o estoque**: não baixa nada; `consumo_a_baixar` (teórico = avanço × material,
  contra as saídas da obra/etapa) alimenta a fila do almoxarife no SIL.
- **Custo no plano** (`GET cronogramas/{id}/custo/`): por etapa e atividade, orçado × comprometido
  (pedidos) × recebido × aplicado (saídas, só por etapa) × medido (medições aprovadas). Pedido e recebido
  são **rateados** por insumo (declarado); pedido de serviço ligado a contrato rateia pelas atividades do
  contrato; o que não acha dono vai para `nao_alocado`.
- **Medição × compra de serviço**: `ContratoObra.pedido_scm` liga a empreitada ao pedido de serviço do
  Suprimentos — o contrato mostra pedido × medido × saldo, e o pedido mostra o medido no PDCA.

### 6.2 Etapas da obra, equipe, julgamento por % e avanço físico-financeiro

- **As etapas da obra são as raízes do plano em vigor** (`modulopdca/etapas.py`). Governa o vigente; sem
  ele, o rascunho. Raiz nova → `EtapaObra` (ou a de mesmo nome, ligada); renomear, reordenar e as datas
  previstas seguem a raiz; raiz excluída → etapa na **lixeira** (volta com o desfazer). O rascunho do
  replanejamento não mexe na obra até publicar. Roda no `on_commit` dos sinais de `Atividade` (raiz) e
  `Cronograma`, e no fim do CPM — uma vez por obra por transação. Do lado da Obra: etapa cadastrada entra
  como raiz do plano em montagem; excluir uma etapa que o plano tem é recusado com o caminho (pelo PDCA).
- **`EquipeObra`** — a equipe é uma **composição** de funcionários (RH) e fornecedores (empreiteiras), da
  obra e não da semana (`/api/pdca/equipes/`, `pdca.programacao.view|comprometer`). Nome vazio nasce dos
  membros. O cartão (`ItemProgramacao.equipe`) liga-se a ela pelo nome, e o `responsavel` continua sendo o
  rótulo que o campo procura. RLS fail-closed na tabela.
- **Julgamento por %** — `julgar/` aceita `percentual_concluido` (acumulado da atividade). O servidor lança
  a diferença como `ApontamentoAvanco` (menor que o apontado é recusado: corrigir é estorno) e deriva o
  `cumprido` contra a meta da semana (`andamento_dos_itens`: início + prometido, ou 100% sem promessa). A
  causa segue obrigatória abaixo da meta; o PPC continua binário. A linha sem % segue o caminho antigo.
- **Avanço físico-financeiro** — `cronogramas/{id}/avanco-fisico-financeiro/`: por etapa (raiz) e da obra,
  previsto até hoje pelas datas do CPM × realizado apontado, em % do físico e em R$ (valor orçado ×
  avanço), e contra o **planejado** do Orçamento (as `ParcelaEtapa` até hoje, mês corrente pro rata), mais
  a curva S mensal. O **cronograma** físico-financeiro (o planejado por competência) continua sendo do
  Orçamento; o PDCA só o lê.
- **Feriado depois do cálculo** — o `gantt/` traz `fora_do_expediente`: as folhas cujos dias úteis entre
  início e término já não batem com a duração, e os feriados/exceções que caem nelas.
- **Material sem orçamento** — `MaterialDaAtividade` (`/api/pdca/materiais-atividade/`): o planejador
  informa na atividade o que ela consome (item do catálogo ou texto, quantidade). A necessidade de
  compra (`suprimentos.py`) trata a linha como a do orçamento (`origem="informado"`): data pelo início,
  executado fora da conta, abatida por estoque e pedido. Vai junto no replanejamento e no modelo.
- **Contrato de medição** — `contratos/{id}/ativar/` (rascunho → vigente), `fontes-da-planilha/`
  (itens analíticos do orçamento vigente e atividades folha do plano em vigor, marcando o que já
  está no contrato) e `incluir-na-planilha/` (várias linhas, tudo ou nada, recusa citando a linha).

### 6.3 O Orçamento planeja, o PDCA executa e controla

O **cronograma físico-financeiro por etapa** nasce no [Orçamento](moduloorcamento.md) (`PlanoEtapa`).
`gerar-do-orcamento` traz **só etapas** para o plano: cada uma vira atividade com `nao_comecar_antes_de`
(início), duração em dias úteis do expediente do plano, `peso_informado` = valor da etapa
(`peso_do_orcamento`, conta como orçado no avanço financeiro) e o Hh orçado na observação. O plano
guarda `orcamento_origem` e `cronograma_orcamento_em`; `situacao-do-orcamento` avisa quando há versão
nova ou cronograma editado, e `atualizar-do-orcamento` traz a mudança (etapa que saiu do orçamento não
é apagada — pode ter avanço).

O posto **Controle** (`controle.py`, `GET /api/pdca/controle/custo|materiais/`) absorve o Hoje e a Semana
e lê a execução: orçado × comprometido (pedidos + contratos de empreiteiro sem pedido de serviço) ×
aplicado (menos devoluções) × medido × realizado; **valor agregado** (`VA = % físico × orçado`,
`IDC = VA ÷ CR`, `IDP = VA ÷ VP`, custo a incorrer `(ONT − VA) ÷ IDC`, custo final projetado
`CR + a incorrer`; nulo sem avanço ou sem custo incorrido) e o material orçado × aplicado × esperado
pelo avanço.

### 6.4 Contrato dos dois lados e reajuste

`ContratoObra.lado`: **custo** (empreiteiro → `ContaPagar`) ou **receita** (contratante, `cliente` →
`ContaReceber`); o mesmo documento, itens, aditivos, medição e retenção. A fórmula paramétrica
(`reajuste_data_base`, periodicidade, parcela fixa, `ParcelaReajusteContrato` com peso e índice da série
única `nucleo`) é aplicada por `recalcular_reajuste` sobre o bruto do período: vale só depois do
aniversário (período que o atravessa divide pelos dias), com número-índice ou variações compostas, fator
**truncado**, índice não publicado → **provisório** (marcado). O reajuste fica **gravado** na medição
(`valor_reajuste`, `reajuste_memoria`) e soma ao bruto antes de retenção e deduções.

## 7. Fronteira do módulo (o que ele **não** faz)

- **Não** paga. Medição vira título; caixa é do [ERP](moduloerp.md).
- **Não** compra nem cota. Restrição vira demanda; compra é do [SCM](moduloscm.md).
- **Não** movimenta estoque. Consumo e EPI são do [SIL](modulosil.md).
- **Não** compõe custo. Composição, BDI e preço são do [Orçamento](moduloorcamento.md); aqui o custo
  entra pelo vínculo com `ItemOrcado` ou pelo valor da **etapa** que veio do cronograma do orçamento.
- **Não** extrai quantitativo de modelo BIM. É da Central BIM com a [Prancheta](moduloprancheta.md).
- **Não** guarda projeto (Prancheta) nem documento de gestão (o DMS, [funcoesimpexp](funcoesimpexp.md) §13).
- **Não** cadastra pessoa (RH) nem fornecedor (`fornecedores`) — usa os que existem.
- **Não** substitui o [Diário](modulodiario.md): escreve e lê nele.

## 8. Contrato de módulo

Entitlement `pdca` (já reservado). Grupo de permissões `pdca`, com a segregação que o ORC.6 provou
necessária — quem executa não aprova:

`pdca.local.*` · `pdca.cronograma.view|edit|publicar|replanejar` · `pdca.avanco.view|apontar` ·
`pdca.programacao.view|comprometer|encerrar` (✅ PDCA.5) · `pdca.restricao.view|edit|remover`
(✅ PDCA.5) · `pdca.contrato.view|edit` ·
`pdca.medicao.view|apurar|atestar` · `pdca.aditivo.edit|aprovar` (✅ PDCA.4) ·
`pdca.verificacao.view|modelo_edit|aplicar` · `pdca.nc.view|abrir|tratar|verificar_eficacia`
(✅ PDCA.7) · `pdca.dds.view|registrar` ·
`pdca.ocorrencia.view|registrar|classificar|emitir_cat|dado_medico` (✅ PDCA.8) ·
`pdca.apropriacao.*` · `pdca.risco.*` · `pdca.garantia.*`

> **O `pdca.ssma.*` que esta lista reservava não era realizável, e virou dois recursos.** O catálogo
> cobra código com **exatamente dois pontos** (`modulo.recurso.acao`, conferido em
> `testes/iam/identity/tests.py`), então `pdca.ssma.dds.registrar` quebraria a suíte — e um recurso `ssma`
> único empilharia num só nome coisas com donos diferentes. A PDCA.8 fez o que a PDCA.7 fez com
> `verificacao` e `nc`: dois recursos, porque são dois objetos com ciclos de vida distintos.
>
> **A segregação da fatia é `registrar` × `classificar`**, e ela é nova nesta casa. As anteriores
> separavam quem faz de quem aprova (`apurar` × `atestar`, `tratar` × `verificar_eficacia`); esta
> separa **quem é medido de quem classifica a própria medida**. Registrar tem de ser de baixo atrito
> — o quase-acidente é o dado mais valioso da segurança e o mais fácil de não anotar —, mas dizer
> *"foi com afastamento, nove dias"* muda o indicador pelo qual a frente é cobrada.
>
> **`emitir_cat` não vai para a persona de segurança.** Quem protocola CAT no INSS é o RH, e duas
> portas para um ato com prazo legal e multa criariam duas verdades sobre se ela foi comunicada.
> **`dado_medico`** abre lesão, CID e atestado: é a primeira PII do grupo `pdca` (LGPD art. 11), e
> para classificar o acidente ninguém precisa do diagnóstico.

> **Os dois `view` da PDCA.7 não estavam nesta lista, e entraram.** A linha
> acima enumerava só os verbos de escrita da verificação; todo recurso desta
> casa tem um `view`, e sem eles as duas telas de leitura da fatia — a fila de
> decisão e o painel de conformidade — não teriam porta.

O nível de aprovação da medição **não** cria permissões numeradas: cada `NivelAprovacao` declara
**qual permissão** ele exige, e o tenant compõe a escada com os papéis que já tem.

Uma permissão nasce **fora** deste grupo, no grupo `base`: **`obra.etapa.percentual_manual`** (§11.2)
— com o prefixo `obra.`, que é o do grupo, e não `obras.` do nome do app.

> **Por que `avanco` tem dois verbos e nenhum deles é `edit`.** Ler o percentual da obra é do gestor e
> de quem recebe relatório; *apontar* é o ato de canteiro que vira dinheiro na medição — são pessoas
> diferentes, e o par `view`/`edit` de CRUD as trataria como uma só. E o verbo de escrita não se chama
> `edit` porque nada aqui se edita: o lançamento nasce e não muda mais, e um interruptor chamado
> "editar" prometeria na tela de papéis um poder que a API não tem.

Personas de fábrica: `planejador`, `engenheiro_de_obra`, `gestor_contratos`, `tecnico_qualidade`,
`fiscal_de_obra`, `tecnico_seguranca`. As existentes (`orcamentista`, `almoxarife`, `suprimentos`)
ganham só leitura do que lhes diz respeito.

> **A PDCA.8 estreou a `tecnico_seguranca`, que a lista acima não previa** — é o TST do SESMT (NR-4),
> o cargo que a obra acima de certo porte é obrigada a ter. Ela passa no teste da gêmea, e por pouco:
> divide com o `tecnico_qualidade` o miolo da verificação (aplicar ficha, abrir e tratar NC, travar a
> frente), porque inspeção de segurança **é** a máquina da §4.5 com outro domínio. O que as separa são
> os dois extremos — ela tem `dds.*` e `ocorrencia.*`, que nenhuma outra persona de obra tem, e **não**
> tem `verificacao.modelo_edit`, que é o verbo exclusivo do técnico de qualidade. É por isso que os
> verbos de SSMA **não** foram dados ao técnico de qualidade: dar-lhe os dois tornaria as personas a
> mesma lista.
>
> Ela leva também `sil.epi.view` — é o que faz o seam do EPI funcionar sem duplicar a entrega (§4.6) —
> e **não** leva `emitir_cat` nem `dado_medico`.

> **A PDCA.3 estreou a `gestor_contratos`, e ela é nova de verdade** — não é gêmea de ninguém, que é o
> teste que a nota abaixo impõe. A `engenharia` responde pela execução (aponta avanço, assina diário),
> o `financeiro` paga o título depois de pronto, e entre os dois havia um vazio: quem fecha o contrato
> com o empreiteiro, confere a medição do período e a leva à assinatura. Ela **apura e não ateste** —
> leva `pdca.medicao.apurar`, nunca `atestar`.
>
> **Quem ateste é a `diretoria`**, que já existe e é o "gerente" da §5.3. Ela recebeu da PDCA.3 o
> **único verbo de escrita que tem em todo o catálogo**, e ele é uma assinatura, não uma edição:
> `pdca.medicao.atestar`. Dar o atesto a quem já lê contrato e medição é o que torna a escada montável
> no primeiro dia, sem o tenant precisar desenhar uma persona antes de emitir a primeira medição.

> **O nome do fiscal.** `fiscal` já é a persona de **nota fiscal** no catálogo da IAM, e são pessoas
> diferentes em empresas diferentes — daí `fiscal_de_obra`.
>
> **Cada persona entra com a fatia que lhe dá verbo.** A PDCA.0 estreia a `planejador` (desenha a
> árvore e o calendário, que é o que existe para fazer) e enxerta `pdca.local.*` na `engenharia` —
> quem responde pela obra desenha o esqueleto dela. As outras chegam na PDCA.3, .5 e .7; criá-las
> antes produziria papéis indistinguíveis entre si, que é a lição do D28 pelo avesso — permissão sem
> persona não se exerce, persona sem permissão não se explica.
>
> **A PDCA.2 não criou a `engenheiro_de_obra`, e a decisão é a mesma lição.** Esta casa já tem a
> `engenharia` — quem responde pela obra, assina o diário e desenha a árvore de locais —, e uma
> persona nova ao lado dela seria a gêmea que o parágrafo acima proíbe. O que a fatia fez foi dar-lhe
> o **verbo**: `pdca.avanco.*` e `obra.etapa.percentual_manual`. A `campo` ganhou
> `pdca.avanco.apontar` (apontar quanto a frente andou é o gesto do canteiro, e é a razão de a fatia
> existir) sem poder editar o plano; `planejador` e `diretoria` ganharam só `pdca.avanco.view` — o
> planejador que apontasse o próprio avanço estaria conferindo o próprio dever de casa.
>
> **A PDCA.5 confirmou a decisão em vez de revê-la.** Era a fatia que mais teria pretexto para criar
> a `engenheiro_de_obra` — a §5.3 põe esse cargo no quadro de programação, no apontamento e nas
> restrições —, e criá-la produziria exatamente a gêmea da `engenharia`: os dois papéis teriam a
> mesma lista. A `engenharia` levou os cinco verbos do ciclo (`pdca.restricao.*`,
> `pdca.programacao.*`), porque ele é dela de ponta a ponta: registra a trava, declara que ela saiu,
> monta o quadro, assume e julga.
>
> **A `campo` ganhou `pdca.restricao.edit`, e o argumento é o mesmo do apontamento**: quem descobre
> que o material não chegou e que a frente anterior não liberou a área é quem está no canteiro, e
> obrigá-lo a telefonar para alguém registrar isso é o que faz o log de restrição nascer
> desatualizado. O que ela **não** tem é `remover` — declarar que a trava saiu libera o serviço para
> ser assumido, e esse é ato de quem responde pela obra. `planejador` e `diretoria` ficaram na
> leitura: o PPC é indicador de direção, e o planejador que julgasse o próprio plano cumprido
> estaria, de novo, conferindo o próprio dever de casa. A `suprimentos` ganhou
> `pdca.restricao.view` — é o outro lado do seam, e quem compra precisa ver o que a demanda está
> segurando na obra.
>
> **Por que `remover` é verbo, e não um `edit` mais forte.** A §5.4 põe "remover restrição" ao lado
> de atestar e comprometer — é **ato que conclui**: ele libera a atividade para entrar na
> programação, e carrega a nota que a reunião seguinte lê. Quem abre a pendência não é
> necessariamente quem pode declarar que ela acabou.
>
> **A PDCA.7 estreou as duas últimas personas previstas — e as duas passam no teste da gêmea.**
> O **`tecnico_qualidade`** é o único cargo desta casa cujo trabalho *é* a máquina de verificação:
> ele leva o `verificacao.modelo_edit`, que nenhuma outra persona tem (escrever o método da empresa
> muda o que **toda** obra confere), aplica a ficha e monta o plano de ação — e não toca em
> cronograma, contrato nem medição, que é o que o separa da `engenharia`. O **`fiscal_de_obra`** é o
> outro lado: **não executa nada** e assina os dois atos que encerram, a medição e a
> não-conformidade. Nenhum dos dois repete a lista de alguém que já existe.
>
> **A segregação desta fatia é `tratar` × `verificar_eficacia`**, e ela é a forma que a medição já
> tem entre `apurar` e `atestar`: quem montou o conserto não assina que o conserto funcionou. Por
> isso `tecnico_qualidade`, `engenharia` e `campo` **não** têm `verificar_eficacia`, e `diretoria` e
> `fiscal_de_obra` o têm sem ter `tratar`. Não vira beco de D130: `fiscal_de_obra` nasce de fábrica e
> o admin de tenant atravessa, então a primeira NC de um tenant de uma pessoa só encerra no dia um.
>
> **`modelo_edit` é separado de `aplicar` pelo mesmo raciocínio, com um detalhe que decide.** Um
> `edit` único daria a quem está na frente o poder de afrouxar o critério da FVS **no momento exato
> em que ela reprovasse** — que é quando alguém quer. A `campo` ganhou `verificacao.aplicar` e
> `nc.abrir` (responder a ficha e fotografar o defeito são o gesto do canteiro, e é a razão de a
> fatia existir) sem `tratar`: decidir o que a obra vai fazer a respeito é de quem responde por ela.
> A `suprimentos` não ganhou nada aqui — NC não vira compra.

**Tetos em [`payment/planos.py`](../../payment/planos.py)**, como todo limite do sistema: atividades por
cronograma, profundidade da WBS, locais por obra e profundidade da hierarquia, itens por contrato,
linhas por medição, níveis de aprovação, fotos e bytes por apontamento, relógio do recálculo de CPM e o
corte síncrono × job, retenção de linhas de base. Nenhum deles em código de engenharia nem no
`settings.py`.

Cada teto entra junto da fatia que o **aplica**: número que nenhum código lê não é régua, é intenção —
e o teste do `nucleo` prende constante a consumidor. A §5.5c do `planos.py` traz os quatro da PDCA.0
(locais por obra, profundidade da hierarquia, locais por geração — que é o corte síncrono × job desta
fatia — e níveis de aprovação); a §5.5d os cinco do cronograma; a §5.5e o do lote de células; e a
**§5.5f os dois da PDCA.2** — apontamentos por lote (a grade da semana) e pontos da curva S (acima
dele o servidor engrossa a granularidade e **declara** qual valeu); e a **§5.5h os dois da PDCA.3** —
itens por contrato e linhas por medição, que são o mesmo número de propósito (a primeira medição de
uma empreitada por preço unitário toca legitimamente **todos** os itens). *Fotos e bytes por
apontamento* não viraram constante: o arquivo sobe pela porta única da plataforma, que já lê o teto do
tenant — declarar outro aqui criaria um segundo número para a mesma pergunta. A **§5.5j traz os
quatro da PDCA.5** — cartões por programação (o quadro é parede de reunião: acima disso ninguém o lê
inteiro), restrições abertas por obra (o *constraint log* é para zerar, não para acumular), causas
por tenant (a causa só serve se for escolhida da mesma lista toda semana) e semanas na série de PPC,
que é o irmão do teto de pontos da curva S.

> **O PPC não tem teto, e não tem meta.** É a tentação óbvia desta fatia: a literatura registra ~54%
> em obra convencional e 80–85% com LPS maduro (§2.1), e seria fácil cravar 85 como "meta do plano".
> O número é **resultado medido**, não limite de uso — a fronteira da §5.6 —, e meta de desempenho é
> acordo entre o cliente e a equipe dele, da mesma classe do percentual de retenção que a §5.5h
> recusou. O sistema mede e mostra; quem cobra é gente.

> **O que da PDCA.3 NÃO virou teto, e por quê.** A **retenção** (percentual, natureza, condição) é
> cláusula que o cliente negocia com o fornecedor dele — mesma classe do prazo de pagamento e do
> limite legal de acréscimo do regime público; a §5.6 do `planos.py` já traça essa fronteira. E o
> **valor da medição** não tem teto: pareceria prudência e seria a pior espécie de trava, porque a
> obra grande é justamente a que paga o plano caro. Quem protege a empresa contra o número errado é a
> escada de atesto, que é gente conferindo — não uma constante.

## 9. O campo — três caminhos, em fases declaradas

*(Decisão do dono, 22/08/2026.)*

1. **WhatsApp** — a porta que **já existe e está em produção**: `modulodiario.origem = whatsapp`, com a
   IA lendo texto e foto. Apontar avanço, abrir NC com foto e responder verificação por conversa. O
   mestre de obras não instala nada.
2. **Web responsiva** — as telas do módulo funcionando no navegador do celular, para o que exige forma
   (ficha de verificação item a item, medição linha a linha).
3. **PWA com offline de verdade** — manifest, service worker, fila de sincronização e resolução de
   conflito. **É fatia de plataforma, não do PDCA**, e o endereço fica reservado aqui para ninguém a
   implementar avulsa dentro deste módulo — o mesmo cuidado que a capacidade de PDF recebeu no
   DMS ([funcoesimpexp](funcoesimpexp.md) §13).

## 10. Seams de expansão (inertes no desenho)

Importação de cronograma de MS Project/P6 · nivelamento de recursos · simulação Monte Carlo de prazo ·
4D (cronograma × modelo, sobre a Prancheta) · benchmark de produtividade entre empresas (Esfera de
Rede) · previsão de atraso por IA sobre PPC e causas.

## 11. Decisões de rumo (tomadas pelo dono do produto)

### 11.1 A WBS é própria, e o vínculo com a etapa é opcional

*(22/08/2026.)* O cronograma tem sua própria árvore, com liberdade total para Gantt e linha de balanço,
e **pode** se vincular a uma `EtapaObra` para mapeamento. Ampliar a `EtapaObra` seria pôr planejamento
dentro de um app de cadastro que é fundação de vários módulos, e uma tabela que a obra usa como
macro-fase não comporta a granularidade de um cronograma real.

**Consequência:** a tradução entre a WBS e a dimensão `(obra, etapa)` — que Orçamento e SIL já
compartilham — é **explícita**, feita pelo vínculo, e a cobertura dela é declarada na resposta da API,
no molde do `realizado_cobertura` do Orçamento. Vínculo que não existe não é inventado.

### 11.2 O percentual digitado continua existindo, sob permissão

*(22/08/2026.)* `EtapaObra.percentual_conclusao` hoje é digitado à mão e pondera quatro leituras
(resumo da obra, serializer, portal do cliente, curva S real). Havendo vínculo direto com uma atividade
do PDCA, ele passa a ser **apurado** — e a edição manual continua **possível**, liberada ou bloqueada
por **`obra.etapa.percentual_manual`**, do usuário ou do admin.

A tela **sempre diz de onde veio o número** — apurado ou informado. Duas fontes silenciosas para o
mesmo número é como se perde a confiança nas duas.

**Como ficou (PDCA.2).** O módulo **escreve o espelho** na coluna a cada apontamento, em vez de a
coluna ser calculada na leitura: aquelas quatro leituras não conhecem o PDCA, e calcular só na tela
deste módulo as deixaria mostrando o número digitado meses atrás. É escrita derivada de um gesto, no
molde do `calculado_em` do CPM — **uma passada pela árvore por gesto**: o lote sincroniza uma vez no
fim da transação, e o apontamento avulso, uma vez só. *Limite declarado:* essa passada é proporcional
ao tamanho do plano (teto de 5.000 atividades), então um apontamento avulso num cronograma no teto lê
a árvore inteira para escrever uma etapa. É barato hoje e tem saída óbvia se deixar de ser — a mesma
da fatia do CPM assíncrono —, mas o custo fica escrito em vez de descoberto.
A etapa ligada ao **pai e também a uma filha** conta uma vez só (entram apenas as mais altas de cada
ramo), senão a filha seria contada dentro do peso do pai e outra vez por fora. Do lado do `obras`, o
serializer expõe `percentual_origem` (`apurado` / `informado`) e recusa a digitação sem a permissão —
dizendo, na mesma mensagem, que o valor digitado **vale até o próximo apontamento**, que é o que
evita a descoberta pelo susto. A dependência é de mão única: `obras` é fundação sem entitlement e não
importa módulo pago; quem oferece a leitura é o `pdca`, e a ausência dele devolve a etapa ao que ela
sempre foi.

### 11.3 Obra pública é opção do usuário, não regime do sistema

*(22/08/2026.)* O módulo atende contrato privado e público. As **regras duras** — limite legal de
acréscimo, atesto de fiscal — ficam **atrás de uma opção que o usuário liga no contrato**. Nem toda
obra com dinheiro público segue o mesmo estatuto, e sistema que impõe a regra pela origem do dinheiro
erra na exceção.

**O limite legal não vai para `payment/planos.py`.** Ele é regra de domínio, não teto comercial — a
mesma natureza da fórmula do Acórdão 2622/2013-TCU, que mora no código do Orçamento. A §5.6 do
`planos.py` já traça essa fronteira.

### 11.4 Avanço e medição são duas coisas, e a medição nasce do avanço

*(22/08/2026.)* O **avanço** é da atividade e existe sempre — inclusive em serviço executado por equipe
própria, que não tem contrato. A **medição** é do contrato e só existe onde há empreiteiro, e é
**proposta a partir do avanço do período**, para o gestor conferir e ajustar antes de submeter.

Unificar os dois obrigaria toda atividade a ter contrato para ter avanço. Separá-los sem derivação
produziria dois números divergindo sem ninguém notar.

### 11.5 Medição aprovada congela, com escada de atesto

*(22/08/2026.)* Aprovação em **mais de um nível**, com atesto registrado em cada um; no último, a
medição congela e só uma retificadora a corrige. É dinheiro saindo: o mesmo rigor do orçamento
aprovado. A máquina de fluxo nasce em `nucleo` (§4.4).

### 11.6 Uma máquina de verificação, quatro domínios

*(22/08/2026.)* FVS, inspeção de segurança, vistoria de entrega e checagem ambiental compartilham
modelo, aplicação, evidência e tratamento. Ver §4.5.

### 11.11 A ficha guarda a pergunta que respondeu

*(PDCA.7.)* `ItemVerificacao.texto` e `.criterio` são **cópia do modelo, não referência** — a decisão
que transforma a ficha em prova.

O modelo é vivo, e tem de ser: a empresa aperta o critério de prumo de 3 mm para 2 mm no ano
seguinte, e faz bem. Se a ficha lesse o texto pelo FK, toda inspeção do ano anterior passaria a
**afirmar que conferiu 2 mm** — e a auditoria do PBQP-H encontraria um sistema que reescreve o
passado sozinho, sem ninguém ter mentido em campo algum. É a mesma razão que congela preço no
`ItemMedicao`: o documento guarda o que foi respondido, não o que se pergunta hoje.

A consequência prática é que **editar o modelo pelo `/admin` é seguro** — e é por isso que o
`ModeloVerificacao` é o único desta fatia que não é somente leitura lá.

E é o congelamento que obriga o ranking do §4.5 a agrupar por `item_modelo`, e não pelo texto: o
texto é cópia por resposta, e agrupar por ele contaria a mesma pergunta N vezes. A resposta órfã —
item acrescentado em campo, ou modelo apagado — fica fora do ranking e é **declarada** na leitura,
em vez de sumir na conta.

### 11.12 "Ação concluída" não encerra a não-conformidade

*(PDCA.7.)* É a regra que separa tratar de arquivar, e sem ela a fatia não valeria a pena existir.

O caminho fácil seria encerrar a NC quando o último `PlanoAcao` fosse marcado como concluído. Isso
é **quem consertou dizendo que consertou** — e é exatamente como a maior parte dos sistemas de
qualidade, de papel e de software, perde o valor inteiro do ciclo: ninguém volta à frente. O que
encerra é a `VerificacaoEficacia`, que é alguém olhando de novo e registrando o que viu.

Três consequências que vêm daí:

- **`eficaz=False` é o resultado mais útil dos dois.** Não encerra nada: devolve a NC para
  tratamento, porque o plano anterior comprovadamente não resolveu, e o que vem a seguir é um plano
  novo. A sequência de verificações fica inteira (o modelo é append-only na prática) e é a história
  honesta de quantas tentativas o conserto levou — a régua do estorno do `ApontamentoAvanco`.
- **Vale a última, não a primeira.** Uma NC verificada como eficaz em março e reaberta em maio por
  ter voltado a falhar não encerra pela leitura de março.
- **A trava mora no `services`, e não numa `CheckConstraint`**, por uma razão física: ela olha
  **outra tabela**, e check de banco não atravessa tabela. O que o banco protege é o que cabe numa
  linha — e ali ele protege o que importa: desvio sem observação é recusado pelo banco também,
  porque o "não aplicável" em tudo é a porta pela qual uma ficha inteira passa sem ninguém verificar
  nada.

### 11.13 A gravidade da NC tem dente: ela para o serviço de verdade

*(PDCA.7.)* `NaoConformidade.restricao` é o seam **vivo** com o Last Planner, e existe para que
"crítica — para o serviço" não seja adjetivo.

Sem o elo, o sistema diria que o serviço está parado e a equipe se comprometeria com ele na
segunda-feira seguinte — porque o quadro da PDCA.5 só olha `Restricao`. Com ele, `gerar-restricao/`
abre uma trava de tipo `AREA` na atividade, e ela deixa de poder entrar na programação até alguém
declarar que a trava saiu.

**`AREA`, e não um nono tipo.** A oitava família da PDCA.5 é *"a frente anterior não liberou o
local"*, e é literalmente o que uma NC aberta faz: o serviço está lá, executado errado, e a frente
seguinte não entra. Um tipo `qualidade` partiria o ranking de restrição em dois vocabulários para o
mesmo impedimento físico.

**Exige a atividade, e a recusa diz isso.** Restrição sem alvo não bloqueia nada (regra da PDCA.5), e
a NC do canteiro nem sempre tem uma — a trinca vista a caminho do almoxarifado não sabe de que
serviço veio. E exige **duas** permissões: `pdca.nc.tratar` mais `pdca.restricao.edit`, na régua do
`gerar-demanda` da restrição — parar a frente é ato do quadro da semana, e deixar que só a permissão
de tratar o fizesse criaria uma porta lateral para ele.

**O caminho de volta é o da PDCA.5, não um novo:** quem destrava é quem remove a restrição, com a
nota de como. A NC encerra pelo seu próprio laço, e as duas coisas são independentes de propósito —
liberar a frente para trabalhar e declarar o defeito tratado não são o mesmo ato.

### 11.15 A gravidade é perguntada no item, não no fim da ficha

*(Decisão do dono, 16/09/2026, olhando o painel de gravidade da primeira obra
verificada: "essa pergunta deveria ser feita em cada item e não no final, porque
aí fica parecendo que um desalinhamento na porta é grave igual a falta de uma
maçaneta".)*

A primeira escrita da PDCA.7 perguntava a gravidade **uma vez**, no diálogo de
conclusão da ficha, e carimbava o mesmo rótulo em todos os itens reprovados. O
painel então somava *"3 maiores"* sobre três coisas de tamanhos diferentes — e
um ranking que agrupa o que não é do mesmo tamanho não ranqueia nada. É o mesmo
mecanismo que faria o ranking de causas da PDCA.5 parar de funcionar se a causa
fosse escolhida **por semana** em vez de por compromisso.

**A gravidade é propriedade do defeito**, então mora em `ItemVerificacao`
(`gravidade`, nula fora do reprovado) e não no gesto que abre as NCs.

**E é perguntada no item porque é lá que dá para responder.** Quem conclui a
ficha pode não ser quem a respondeu — o `campo` responde, qualquer um com
`aplicar` conclui — e pode nem ter estado na frente. Quem acabou de olhar o
defeito sabe se ele se corrige na hora ou se para o serviço; quem lê uma lista
depois, não.

Três consequências:

- **obrigatória no reprovado, recusada nos outros três resultados**, com trava na
  aplicação e no banco. O segundo lado é o menos óbvio e importa igual: um item
  que ficou *conforme* com uma gravidade pendurada (porque alguém marcou "não
  conforme", pesou e depois corrigiu) contaria no painel um defeito que não
  existe;
- **`abrir-ncs/` não recebe corpo.** Cada NC nasce com o peso do seu item. O
  serializer de entrada foi removido, e a ausência está declarada no arquivo para
  que ninguém o reintroduza achando que faltou;
- **o diálogo de conclusão mostra, não pergunta.** Ele lista o que vai abrir com
  o peso de cada um; mudar um peso é voltar à pergunta, antes de concluir.

Os rótulos dizem **o que cada degrau autoriza** — *corrige-se na frente*, *o
serviço não é aceito assim*, *para o serviço* — e não "baixa/média/alta". É a
diferença entre classificar e decidir, e é o que faz o técnico escolher certo com
uma mão no celular.

### 11.14 A biblioteca de fichas nasce vazia

*(PDCA.7.)* O catálogo de causas da PDCA.5 nasce semeado; a biblioteca de modelos de verificação,
**não** — e a assimetria é a decisão, não um esquecimento.

Rótulo de falha é vocabulário comum a todo canteiro, e um catálogo vazio faria a primeira reunião
inventar texto livre, que é o que o modelo existe para impedir. FVS não é isso: ela é o **método
desta empresa** escrito — o que ela aprendeu a conferir, com o critério numérico que ela adota —, e é
contra ela que o organismo certificador audita. Uma ficha de fábrica seria aplicada sem ser lida, e a
empresa se certificaria contra o nosso chute.

O que a fatia oferece no lugar é o **`duplicar`**, que é o gesto real: quem tem quarenta FVS tem
quarenta variações de três linhas, e digitar a segunda inteira é onde o critério de uma diverge do da
outra por descuido.

### 11.7 O frontend não segue a forma dos outros módulos

*(22/08/2026.)* Cada módulo tem necessidade própria de tela, e a do PDCA foi pesquisada e resolvida
por si — não herdada do SCM, do SIL ou do Maps. A régua do projeto continua valendo no que ela é
(profundidade, honestidade do dado, integração visível, identidade Malha); o que não se herda é a
**forma** — hub, lentes e nomenclatura.

Três consequências que vêm do domínio, e não caberiam no molde dos outros: a unidade de trabalho é a
**obra**, não o tenant (§5.1); os instrumentos têm **gramáticas de gesto incompatíveis** entre
si ([o desenho](modulopdca-frontend.md)); e o frontend **nasce junto de cada fatia**, não como uma
fatia final (§12).

### 11.10 O PPC é binário, e a execução parcial fica ao lado dele

*(decisão de desenho, 15/09/2026, respondendo a "existe a possibilidade de a obra ter sido executada
parcialmente".)*

A observação é certa e o remédio óbvio é errado. Um compromisso de 200 m² de alvenaria pode sair em
150 m², e marcar isso como "não saiu" parece injusto com quem trabalhou. A tentação é dar crédito
parcial: 150/200 = 0,75 no lugar de 0.

**Não.** O PPC é `compromissos cumpridos ÷ compromissos assumidos`, **binário por definição**, e a
dureza é o mecanismo. Com crédito parcial o time aprende a prometer demais e a entregar uma fração:
o índice estabiliza em uns 70% para sempre e deixa de medir a **confiabilidade do plano**, que é a
única coisa que ele mede. A binariedade é o que força o compromisso a ser dimensionado para caber na
semana — e dimensionar direito é o que o Last Planner ensina.

**Mas o número existe e não pode ser jogado fora.** A obra que assumiu 20 pontos e entregou 12 fez
12, e um cartão que só diz "não saiu" faz o sistema parecer dizer que ela não fez nada. Duas
consequências, as duas ruins: a equipe desconfia do índice, e **quem julga julga de memória**.

A saída é a régua de integração do projeto — *o que conversa no backend conversa na tela*: o avanço
já está apurado no [`ApontamentoAvanco`](#43-execução-e-verificação) da PDCA.2, lançado pelo campo no
dia. O cartão passa a mostrá-lo **ao lado** do compromisso:

> `prometeu 20 pts · campo apontou 12 pts`

Nada é digitado de novo, e é por isso que o número é confiável. Ele serve para **julgar com a prova
na frente**, e as causas de fábrica para o caso já existem: `PLAN-MAL-DIM` (serviço mal dimensionado
no plano) e `MO-PRODUT` (produtividade abaixo da prevista).

**E ele nunca entra no PPC.** Na semana encerrada a leitura aparece com nome próprio e a etiqueta
*"não entra no PPC"*, porque as duas coisas são verdade ao mesmo tempo: o plano não foi confiável (é
o que o índice mede) e a equipe trabalhou (é o que isto mostra). Somar as duas num número só
destruiria a primeira.

**`null` não é zero.** Cartão sem apontamento diz *"sem apontamento do campo nesta semana"*, não
"0 pts": pode ser que ninguém tenha apontado, não que nada tenha andado — e fabricar o zero acusaria
a equipe de uma parada que talvez não tenha havido.

> **Isto continua valendo depois do peso da §11.11, e as duas coisas não se confundem.** O
> **cumprimento** é binário — saiu ou não saiu, e 150 de 200 m² é "não saiu". O **peso** decide quanto
> cada "saiu" vale no índice. Dar crédito de 0,75 pela execução parcial é o que esta seção recusa;
> dizer que a concretagem da laje pesa mais que a limpeza do canteiro é outra pergunta, e a §11.11
> responde sim a ela. O que o arrasto (§11.11) acrescentou é que o pedaço que ficou por fazer vira o
> previsto do cartão da semana seguinte — em vez de virar crédito parcial nesta.

### 11.11 O PPC pesa, a semana futura não fecha, e o que não saiu continua

*(três decisões do dono, 15/09/2026, na mesma leva de relatos sobre o quadro da semana.)*

**a) O índice é ponderado, e o peso sai do planejamento.** Contar cartões dizia que assumir a
concretagem da laje e assumir a limpeza do canteiro valem o mesmo: a semana que entrega a laje e perde
a limpeza marcava os mesmos 50% da que entrega a limpeza e perde a laje. O dono decidiu que o peso
*"sai do planejamento — o planejamento pega o peso pelo orçamento (orçamento tem o físico-financeiro)
ou pelo tempo que o usuário colocou"*, e que o ponderado **substitui** o clássico.

A escada é a do `peso_de` do avanço, com um degrau a mais no fim (`services.peso_do_compromisso`):

| origem | de onde vem | quando vale |
| --- | --- | --- |
| `orcado` | `ItemOrcado.total_com_bdi` da atividade vinculada | há vínculo com o orçamento |
| `informado` | `Atividade.peso_informado` | o planejador digitou um peso |
| `duracao` | `Atividade.duracao_dias` | há duração no cronograma |
| `igual` | 1 por cartão | **nenhum** cartão do quadro tem régua — é o PPC clássico |

O degrau da duração existe **só aqui**: o avanço do cronograma pergunta *quanto da obra está feito*, e
ali duração seria régua errada (semana de cura de concreto não é obra feita); o PPC pergunta *quanto do
que se assumiu saiu*, e duração é a régua de esforço que toda obra tem mesmo sem orçamento vinculado.

**O peso é congelado quando o cartão entra no quadro**, na régua do `retencao_percentual_aplicado` da
medição: reprecificar o orçamento em dezembro não pode reescrever o PPC de agosto. Cartão sem régua
(marco, atividade sem duração nem vínculo) fica **fora da divisão** e é contado em `sem_peso` ao lado
do índice — a régua do `folhas_sem_peso` do avanço. E **a base viaja com o número** (`peso_bases`), na
leitura da semana, em cada ponto da série, no tooltip, na tabela e na legenda: 70% pesado por dinheiro
e 70% contando cartões são duas frases diferentes.

> **Continua sem teto e sem meta** (§5.5j do `planos.py`). Peso é a unidade do índice; meta seria um
> valor a atingir, e essa continua sendo conversa entre a empresa e a equipe dela.

**b) A semana que ainda não acabou não se encerra sem alçada e sem motivo.** `encerrar` conferia o
status e os julgamentos pendentes, nunca o calendário: na segunda de manhã dava para fechar a semana
que ia até domingo. Não virou porta trancada — existe a obra que para na quinta de um feriado
prolongado, e recusar faria o time julgar de memória na segunda seguinte. Virou **porta com chave e
assinatura**: `pdca.programacao.encerrar_antecipado` + motivo por escrito, e a semana fica marcada na
série com símbolo próprio (losango no eixo, distinto da bolinha da semana reaberta — ela pode ser as
duas coisas).

**c) O compromisso que não saiu continua de pé.** A semana encerrada era um fim de linha: o cartão
"não saiu" ficava no quadro de trás e a seguinte nascia vazia. O que se perdia não era o clique de
puxar de novo — era **o fato de aquele compromisso estar na segunda semana seguida**, que é o que faz a
reunião perguntar o que está travando em vez de perguntar por que o índice caiu.

`services.arrastar_pendentes` roda no fim de `encerrar` (e tem porta própria, `arrastar/`, para a
semana reaberta e rejulgada). O cartão novo leva **o que ficou por fazer** — previsto menos apontado,
que é o item parcialmente concluído da §11.10 —, o responsável, o local e o contador; **não** leva a
nota nem a causa, que são o julgamento da semana que passou. Três recusas deliberadas: não arrasta
para semana já comprometida, respeita o teto de cartões e **arrasta mesmo o que está travado** — a
restrição volta com o cartão, `comprometer` recusa a semana enquanto ela estiver lá, e a trava aparece
no quadro da reunião em vez de o serviço sumir.

### 11.12 Cancelar a medição cancela o título — e o título pago tranca o cancelamento

*(decisão do dono, 15/09/2026: "quando cancelo medição em PDCA não cancela o pagamento em ERP… também
tem a questão de já estar quitado".)*

A §7 diz que o PDCA **não paga**, e isso continua verdade: ele não dá baixa, não escolhe data de
pagamento, não conversa com o banco. Mas ele **gera** o título, e o que gera tem de saber desfazer —
senão a `ContaPagar` fica aberta no financeiro apontando para um boletim que não existe mais, e a
conciliação descobre no fim do mês.

`services.cancelar_medicao` é o caminho único, com três portas:

| estado da medição | o que acontece |
| --- | --- |
| rascunho · em aprovação | retira o documento. Não há título, e não pede motivo — não houve efeito |
| aprovada, título `ABERTO` | cancela os dois **na mesma transação**; motivo obrigatório; auditoria dos dois lados |
| aprovada, título com baixa (parcial **ou** quitado) | **recusa**, dizendo quanto já foi pago, e manda retificar |

**A régua do quitado é a mesma que já governa esta casa:** o que virou dinheiro se corrige por
documento novo, não apagando o antigo. Existe uma `Transacao` lançada, e um título cancelado com baixa
em cima é um buraco que a conciliação não fecha nunca. A verificação olha `valor_pago > 0` **antes** do
status, porque o caso traiçoeiro é a baixa parcial — o título ainda é `PARCIAL`, parece vivo, e já saiu
dinheiro.

**O aviso e a trava saem do mesmo lugar** (`services.estado_do_titulo`, servido no
`MedicaoSerializer.titulo_erp`): o diálogo da tela mostra o título, o valor e o vencimento antes do
clique, e com baixa em cima o botão de confirmar nem arma. Dois lugares para a mesma regra divergiriam
na primeira mudança dela. O campo fica **fora** do `MedicaoResumoSerializer` — é uma consulta por
linha, e a lista desenha o status do boletim, não o do título (a lição do D136).

**A permissão é a de atestar, não a de apurar:** derrubar um título a pagar é alçada de quem autorizou
o dinheiro a sair.

### 11.9 A semana errada tem volta, e a volta é registrada

*(decisão de desenho, 15/09/2026, respondendo a "e se o usuário tiver errado na semana?".)*

O ciclo do Last Planner é de mão única — rascunho → comprometida → encerrada —, e ele **precisa** ser,
senão o PPC deixa de medir compromisso e passa a medir quem soube editar a lista a tempo. Mas mão
única não pode virar beco: julgamento é feito em reunião, com gente cansada no fim da semana, e erro
ali é normal. Sem volta, uma causa lançada errada fica para sempre — e o estrago não é do índice, é do
**ranking**, que é o que decide o que a empresa muda. Uma causa errada contada durante um ano manda a
obra consertar o problema que ela não tem.

**Por que reabrir, e não retificar.** A medição da PDCA.3 congela e se corrige por um documento novo,
porque ela virou dinheiro: existe um título no ERP que não pode ser reescrito. Aqui não há documento a
reconciliar — o PPC é **derivado, nunca gravado** (§4.9) —, então reabrir e rejulgar simplesmente
recalcula. A régua aplicável é a do `ApontamentoAvanco` (§4.3): o erro se corrige **com motivo
declarado**, não se apaga.

**Um degrau por vez**, e o custo de cada um é diferente:

| De → para | O julgamento | De quem é o ato |
|---|---|---|
| `encerrada` → `comprometida` | **fica** — corrige-se só o que está errado | quem julga (`programacao.encerrar`) |
| `comprometida` → `rascunho` | **é apagado** — semana não assumida não tem julgamento | quem assume (`programacao.comprometer`) |

Descer dois degraus custa duas reaberturas, cada uma com a sua frase — porque é exatamente o gesto que
merece dois registros. E a permissão muda com o degrau de propósito: um código só para os dois daria a
quem julga o poder de desmontar o quadro que a equipe assumiu, ou — pior — daria a quem monta a parede
o poder de apagar o índice que ela produziu.

**Enquanto reaberta, a semana sai da série de PPC e do ranking de causas.** Ela deixou de ser apurada,
e contá-la com o julgamento velho seria publicar um número que o próprio sistema declarou em revisão.

**Sem prazo, e o que protege o histórico é a correção aparecer.** A tentação seria só deixar reabrir a
semana recente; mas erro achado tarde é o mais caro de não poder consertar, e a retificadora da
medição — que mexe em dinheiro — também não tem prazo. O que impede a reescrita silenciosa da história
é o selo: quem lê a série vê quais semanas foram reabertas, quantas vezes e por quê, e a reunião que
discutiu o número antigo não é contrariada em silêncio.

### 11.8 O commit é do dono, e vem no fim do módulo

*(decisão do dono, 23/08/2026.)* Gravar história no repositório é **ato do dono** — nenhum agente
commita por ele. E a gravação do PDCA não acompanha a fatia: o commit vem **ao final do módulo**,
não a cada sub-fatia da §12.

A consequência prática é que as fatias **PDCA.0–PDCA.13 se acumulam na árvore de trabalho** até lá.
Isso muda o que a árvore suja significa neste módulo — ela é o estado normal do trabalho em curso, e
não um resto por commitar.

O que **não** muda é o critério de pronto de cada fatia: continua sendo *inteira e testada* (§12) —
a suíte verde, as migrations aplicadas sem divergência de modelo e os documentos de status
sincronizados no mesmo turno. Fatia pronta é fatia que passa, não fatia gravada.

## 12. Sub-fatias (proposta de faseamento)

O desenho é completo; a execução segue o padrão do projeto — fatias que entram inteiras e testadas.
O **commit não acompanha a fatia**: ele é do dono e vem ao final do módulo (§11.8).

| Fatia | O que entrega |
|---|---|
| **PDCA.0** | Fundação: `LocalObra` + gerador em lote, `CalendarioTrabalho`, permissões, personas, RLS fail-closed, contrato de módulo — e a **máquina de fluxo de aprovação em `nucleo`** |
| **PDCA.1** | Cronograma versionado, `Atividade` (WBS), `Precedencia`, CPM, linha de base, vínculos opcionais com `EtapaObra` e `ItemOrcado` |
| **PDCA.1b** | Plano modelo (biblioteca de padrões da empresa, com quota de plano), escrita em lote, renumeração da EAP, tela de expediente, filtros de trabalho, ações em bloco e exportação (PNG/CSV) |
| **PDCA.2** | `ApontamentoAvanco`, avanço ponderado, curva S física × financeira, e a tomada do `percentual_conclusao` com a permissão de override |
| **PDCA.3** | `ContratoObra`, `ItemContrato`, `Medicao` nascendo do avanço, retenção **e sua liberação**, escada de atesto, título ao ERP |
| **PDCA.4** | `AditivoContrato`/`ItemAditivo` com as três travas, `DeducaoMedicao` tipada, material estocado (coluna E da G703), período encadeado, e a medição como **documento com endereço próprio** (apurar × boletim) |
| **PDCA.5** | Last Planner: `Restricao`, `ProgramacaoSemanal`, PPC e catálogo de causas |
| **PDCA.6** | Linha de balanço sobre `LocalObra` — ritmo, sincronia de equipes, gargalo |
| **PDCA.7** ✅ | Verificação (FVS), `NaoConformidade` com pino da Prancheta, `PlanoAcao` 5W2H e verificação de eficácia |
| **PDCA.8** ✅ | SSMA: DDS com lista de presença, ocorrência com os campos da CAT e o bloco clínico sob PII. **O EPI é lido do SIL, não recriado** (§4.6) |
| **PDCA.9** | Apropriação, produtividade e EVM em homem-hora |
| **PDCA.10** | Riscos e marcos |
| **PDCA.11** | Pós-obra: vistoria, punch list, garantia, chamado |
| **PDCA.13** | E2E vivo pelo gateway, no padrão de `orc6_orcamento_test.py` e `pra8_prancheta_test.py` |

**O frontend não é uma fatia no fim.** Cada instrumento da §5.2 tem física própria e nasce **junto**
da fatia de backend que o alimenta — Gantt com a PDCA.1, grade de medição com a PDCA.3, quadro de
programação com a PDCA.5, LOB com a PDCA.6, campo com a PDCA.7. Concentrar tudo numa PDCA.12
produziria cinco ferramentas desenhadas sem quem as usa ter tocado em nenhuma. O que sobra para o fim
é só o **contexto de obra** e a **carteira multi-obra** (§5.1), que dependem de tudo já existir.

O canal WhatsApp e a web responsiva entram **dentro** das fatias que produzem dado de campo (2, 5, 7,
8); o PWA offline é fatia de plataforma, fora desta conta (§9).

## 13. O que ficou de fora — e o endereço de cada coisa

| Capacidade | Onde mora |
|---|---|
| Nivelamento de recursos e Monte Carlo de prazo | Aqui, em fatia posterior — depende do CPM estar maduro |
| Importação de MS Project/P6 | [`funcoesimpexp`](funcoesimpexp.md), como recurso declarado |
| 4D — cronograma sobre o modelo | Central BIM + [Prancheta](moduloprancheta.md) |
| Previsão de atraso e de estouro | [`funcoesia`](funcoesia.md), com os dados daqui |
| Benchmark de produtividade entre empresas | Esfera de Rede |
| App de campo offline | Plataforma (§9) |
| Realizado financeiro completo por obra | [`moduloerp`](moduloerp.md) D.1.4 |

## 14. Status

Ver [../roadmap.md](../roadmap.md).
