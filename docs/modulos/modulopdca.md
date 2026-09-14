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
o MS Project; aqui elas caem de graça do versionamento que o projeto já pratica.

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

**`Risco`** — o terceiro modelo que a v01 tinha, ampliado: categoria, probabilidade, impacto,
severidade derivada, mitigação, dono (`rh.Funcionario`) e atividade opcional.

### 4.3 Execução e verificação

**`ApontamentoAvanco`** — quem, quando, onde, quanto. **Append-only**: erro se corrige por apontamento
de sinal contrário (`estorna`), não por edição — o avanço é a base de dinheiro que sai, e histórico
reescrito é dinheiro sem rastro. A trava mora no `save()` do model, e não só na API: a viewset não
expõe `PUT`/`PATCH`/`DELETE`, mas viewset é *uma* porta — o comando de bancada, a importação e a
fatia de WhatsApp entram por outras. Carrega `origem` (`web` / `whatsapp` / `app`) no mesmo idioma que
o diário já usa, e foto (pela porta única de arquivo da plataforma, que é por onde o teto de bytes já
é imposto).

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
entra na programação** — é a regra que separa o LPS de uma lista de tarefas.

**`ProgramacaoSemanal`** / **`ItemProgramacao`** — o que a equipe **se comprometeu** a fazer na semana.
No fim do ciclo cada item é cumprido ou não; o não-cumprido exige **causa**, escolhida de um catálogo
(`CausaNaoCumprimento`, de fábrica e extensível por tenant). O **PPC** é a razão entre os dois, e o
ranking de causas é o que alimenta o "Act".

### 4.4 Contrato, medição, aditivo

**`ContratoObra`** — obra, `fornecedor` (o cadastro único, que já é neutro quanto a ser de material ou
de serviço), objeto, **regime** (preço unitário, preço global, administração), vigência, garantia e a
cláusula de **retenção** (percentual, natureza e condição de liberação). Carrega **`regime_publico`**
e, quando ligado, o **limite legal de acréscimo** — *selecionado pelo usuário, não imposto pelo
sistema* (§11.3).

**`ItemContrato`** — com `item_orcado` **opcional**: contratado contra a régua do orçamento aprovado.
Quantidade contratada e preço unitário. A trava que o mercado ensina: **medição acumulada não pode
exceder contratado + aditivos**.

**`AditivoContrato`** / **`ItemAditivo`** — acréscimo, supressão, prazo ou reajuste, com motivo e
aprovação própria. Duas regras vindas da prática: a quantidade final de um item **não pode ficar
abaixo do que já foi medido**, e o item aditado fica **marcado** nas medições seguintes. O efeito no
custo já existe do outro lado — `RevisaoOrcamento` do tipo `aditivo` — e o PDCA amarra o documento, o
saldo e o prazo a ele.

**`Medicao`** / **`ItemMedicao`** — o boletim do período. **Nasce do avanço**, não ao lado dele
(§11.4): o sistema propõe a quantidade a partir dos apontamentos do período, o gestor confere, ajusta
e só então submete. Bruto → retenção → **líquido**, e o líquido vira `conta_pagar_ref` no ERP.

**`FluxoAprovacao`** / **`NivelAprovacao`** / **`Atesto`** — a aprovação em **mais de um nível**
(§11.5): engenheiro → gerente de contrato → fiscal, cada nível exigindo uma permissão e registrando
atesto com autor, data e observação. Aprovada no último nível, a medição **congela**; correção exige
medição **retificadora**, nunca edição.

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

**`DialogoSeguranca`** (DDS) com participantes de `rh.Funcionario`, **`Ocorrencia`** (quase-acidente /
incidente / acidente, com CAT e dias perdidos) e **`EntregaEPI`**, que aponta `catalogo.Item` — EPI já
é uma natureza do catálogo — e cujo movimento de estoque é do SIL. O PDCA registra a **entrega e a
validade**; quem baixa o saldo é quem sempre baixou.

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

### 5.2 Cinco instrumentos, cinco físicas de interação

O erro seria forçar cinco necessidades diferentes no mesmo molde de página. Elas não têm o mesmo
usuário, nem o mesmo dispositivo, nem a mesma gramática de gesto.

**1 · Gantt — árvore + linha do tempo sincronizadas**
Não é tabela com barras coloridas. É um *split view*: a WBS à esquerda (árvore expansível,
**virtualizada** — cronograma real passa de mil linhas) e a linha do tempo à direita, com rolagem
vertical acoplada e horizontal independente. Os gestos que definem a ferramenta: **arrastar a barra**
para reprogramar, **ligar duas barras** para criar precedência, **destacar o caminho crítico**,
**sobrepor a linha de base** como fantasma atrás do plano vigente (é a leitura que responde *"atrasou
quanto desde que a gente combinou?"*) e **trocar a escala** de dia para semana, mês e trimestre.

**2 · Linha de balanço — o gesto é inverso ao do Gantt**
Eixo Y é **localização** (a `LocalObra` da §4.1), eixo X é tempo, e cada serviço é uma **reta
inclinada** cuja inclinação **é o ritmo**. No Gantt você arrasta uma barra pronta; aqui você **desenha
a linha**, clicando na localização de início e arrastando pela duração e pelas localizações — é assim
que o Vico Schedule Planner opera, e é o gesto que faz o planejador pensar em ritmo em vez de em
duração. Duas linhas que **se cruzam** são duas equipes no mesmo lugar: a tela precisa gritar isso,
porque é o conflito que a LOB existe para achar. (O ganho relatado do flowline sobre o Gantt é de pelo
menos 10% de prazo, sem consumir mais recurso.)

**3 · Quadro de programação — post-it, e de propósito**
O Last Planner nasceu numa parede com post-its, e o software que pegou (Touchplan) venceu justamente
por **parecer a parede**: cartões que se arrastam, uma área de rascunho de onde se puxam atividades, e
a **linha de compromisso** que o time arrasta sobre o plano convertendo as atividades em compromissos
da semana. É um **canvas de arrastar**, não um formulário — e é usado em reunião, em tela grande e
sensível ao toque, com várias pessoas em volta. Formulário mataria a reunião.

**4 · Grade de medição — planilha, com trava**
Contratado · acumulado anterior · **este período** · saldo, linha a linha, com edição na célula,
navegação por teclado (Tab/Enter, colar de planilha) e o bloqueio de exceder o contratado + aditivos
acontecendo **na hora da digitação**, não na submissão. Quem opera isso passa o dia aqui; cada clique
a mais é multiplicado por centenas de linhas. É a evolução natural do `FinanceDataTable` que o ERP já
tem.

**5 · Campo — o oposto de tudo acima**
Uma mão, luva, sol, e às vezes sem sinal. Alvos grandes, **uma pergunta por vez** em vez de formulário
denso, foto como cidadão de primeira classe (com data e coordenada carimbadas sozinhas, sem o
inspetor anotar nada), voz aceita como entrada. É o teste que a literatura de campo usa: *o inspetor
segurando o telefone com uma mão só, no canteiro, usa isto?* Grade e Gantt reprovam nesse teste, e é
por isso que o campo **não** pode ser a mesma tela reduzida.

### 5.3 Quem usa o quê

| Quem | Onde | Instrumento |
|---|---|---|
| Planejador | Escritório, tela grande | Gantt, linha de balanço, linha de base |
| Engenheiro de obra | Canteiro, tablet | Quadro de programação, apontamento, restrições |
| Encarregado / mestre | Canteiro, celular ou WhatsApp | Apontar avanço, abrir NC com foto |
| Gestor de contratos | Escritório | Grade de medição, saldo, aditivo |
| Técnico da qualidade | Canteiro | Verificação item a item, plano de ação |
| Fiscal / gerente | Onde estiver | Fila de atesto — decidir, com o que precisa para decidir junto |
| Diretor | Escritório | Carteira multi-obra: SPI/CPI, PPC, desvio |

### 5.4 O que une os instrumentos (já que não é o layout)

Não é o molde da página — é o **dado** e o **ato**:

- **a mesma atividade** aparece como barra no Gantt, reta na LOB, cartão no quadro e linha na medição;
  selecionar num lugar seleciona nos outros;
- **todo instrumento termina num ato que conclui** — atestar, comprometer, remover restrição, tratar,
  replanejar. Fila de decisão existe, mas ela **mora dentro do contexto da obra**, não num hub que
  soma o que não se soma;
- **dado honesto**: avanço sem apontamento aparece como *"sem apuração"*, nunca como 0% — e o número
  sempre diz se é apurado ou informado (§11.2). Fabricar avanço aqui é pior que em qualquer outro
  módulo: é o número que vai para o cliente e para o pagamento do empreiteiro.

### 5.5 As bibliotecas — e a fronteira de licença

O projeto entrega o frontend **ao navegador do cliente**, o que faz de qualquer biblioteca JS uma
distribuição. Copyleft aqui é o caso perigoso, não o teórico — a mesma disciplina que recusou o
PyMuPDF (AGPL) em favor do `pikepdf` está em [THIRD-PARTY-LICENSES.md](../../THIRD-PARTY-LICENSES.md).
**Só entra licença permissiva.**

| Instrumento | Caminho |
|---|---|
| **Gantt** | Biblioteca **MIT** (o campo tem opções reais: DHTMLX Community, SVAR React Gantt, `gantt-task-react`, Frappe Gantt). As comerciais — Bryntum (~US$ 940/dev) e DHTMLX PRO (~US$ 699) — ficam fora enquanto uma MIT der conta. **Nenhuma GPL**, mesmo "community" |
| **Linha de balanço** | **Não existe biblioteca.** É SVG próprio — e o projeto já faz SVG denso e interativo na [Prancheta](moduloprancheta.md) |
| **Quadro de programação** | Canvas de arrastar próprio; nada de biblioteca de kanban genérica, que traz um modelo de coluna que não é o do quadro semanal |
| **Grade de medição** | `@tanstack/react-table`, já no projeto, com edição em célula |
| **Curva S, EVM, PPC** | `recharts`, já no projeto |
| **Mapa da frente** | `maplibre-gl`, já no projeto |

O CPM **roda no servidor**, não no browser: é fonte de verdade para dinheiro e prazo, o teto de
tamanho é do dono ([`planos.py`](../../payment/planos.py)) e recalcular num laptop fraco daria
resultado diferente do recalculado no servidor.

### 5.6 O que da régua continua valendo

Identidade Malha (tokens, tema claro e escuro, tipografia), as [convenções
obrigatórias](../frontend-convencoes.md) — busca sem acento, dinheiro, datas, upload, omitir × trancar
—, **não-CRUD**, **dados honestos** e **integração visível entre módulos**. O que não vale é copiar a
forma: hub, lentes e nomenclatura são do domínio de cada módulo, e o deste pediu outra coisa.

### 5.7 O que a construção do Gantt fixou — e os limites declarados

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
  nem formulário por atividade: virou **planilha com trava**, no mesmo molde da grade de medição da
  §5.2 — a fila abre no que *deveria estar acontecendo hoje*, ordenada por crítica → vencida → vence
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
| [SIL](modulosil.md) | Aplicado de material por `(obra, etapa)` ao lado do avanço físico — consumo × produção |
| [SCM](moduloscm.md) | Restrição de material vira **demanda**; item de serviço contratado conversa com o pedido |
| [ERP](moduloerp.md) | Medição aprovada → **título líquido** → `ContaPagar`. O ERP decide quando sai do caixa |
| RH | Responsável, equipe, efetivo, DDS, EPI |
| [Diário](modulodiario.md) | Apontamento e NC podem **nascer no diário do dia**, inclusive por WhatsApp; e o diário passa a mostrar o que estava programado |
| [Prancheta](moduloprancheta.md) | NC ancorada no desenho (`Marcacao`), exportada em **BCF** com o resto |
| [Maps](modulomaps.md) | `LocalObra.maps_local` — a frente de serviço no mapa |
| Clientes | Avanço **apurado** no portal, no lugar do digitado; vistoria e chamado de garantia |
| [funcoesia](funcoesia.md) | Causa de não-cumprimento sugerida; foto de NC classificada — o módulo é **consumidor**, sem cliente de IA próprio |
| [funcoesimpexp](funcoesimpexp.md) | Importar cronograma de MS Project/P6 e exportar medição, verificação e curva S |

## 7. Fronteira do módulo (o que ele **não** faz)

- **Não** paga. Medição vira título; caixa é do [ERP](moduloerp.md).
- **Não** compra nem cota. Restrição vira demanda; compra é do [SCM](moduloscm.md).
- **Não** movimenta estoque. Consumo e EPI são do [SIL](modulosil.md).
- **Não** compõe custo. Composição, BDI e preço são do [Orçamento](moduloorcamento.md); aqui o custo
  entra pelo vínculo com `ItemOrcado`.
- **Não** extrai quantitativo de modelo BIM. É da Central BIM com a [Prancheta](moduloprancheta.md).
- **Não** guarda projeto (Prancheta) nem documento de gestão (`modulodms`).
- **Não** cadastra pessoa (RH) nem fornecedor (`fornecedores`) — usa os que existem.
- **Não** substitui o [Diário](modulodiario.md): escreve e lê nele.

## 8. Contrato de módulo

Entitlement `pdca` (já reservado). Grupo de permissões `pdca`, com a segregação que o ORC.6 provou
necessária — quem executa não aprova:

`pdca.local.*` · `pdca.cronograma.view|edit|publicar|replanejar` · `pdca.avanco.view|apontar` ·
`pdca.programacao.view|comprometer|encerrar` · `pdca.restricao.*` · `pdca.contrato.view|edit` ·
`pdca.medicao.view|apurar|atestar` · `pdca.aditivo.edit|aprovar` ·
`pdca.verificacao.modelo_edit|aplicar` · `pdca.nc.abrir|tratar|verificar_eficacia` · `pdca.ssma.*` ·
`pdca.apropriacao.*` · `pdca.risco.*` · `pdca.garantia.*`

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
`fiscal_de_obra`. As existentes (`orcamentista`, `almoxarife`, `suprimentos`) ganham só leitura do que
lhes diz respeito.

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
dele o servidor engrossa a granularidade e **declara** qual valeu). *Fotos e bytes por apontamento*
não viraram constante: o arquivo sobe pela porta única da plataforma, que já lê o teto do tenant —
declarar outro aqui criaria um segundo número para a mesma pergunta.

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
   `modulodms`.

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

### 11.7 O frontend não segue a forma dos outros módulos

*(22/08/2026.)* Cada módulo tem necessidade própria de tela, e a do PDCA foi pesquisada e resolvida
por si — não herdada do SCM, do SIL ou do Maps. A régua do projeto continua valendo no que ela é
(profundidade, honestidade do dado, integração visível, identidade Malha); o que não se herda é a
**forma** — hub, lentes e nomenclatura.

Três consequências que vêm do domínio, e não caberiam no molde dos outros: a unidade de trabalho é a
**obra**, não o tenant (§5.1); os cinco instrumentos têm **gramáticas de gesto incompatíveis** entre
si (§5.2); e o frontend **nasce junto de cada fatia**, não como uma fatia final (§12).

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
| **PDCA.3** | `ContratoObra`, `ItemContrato`, `Medicao` nascendo do avanço, retenção, escada de atesto, título ao ERP |
| **PDCA.4** | `AditivoContrato` com as travas, saldo de contrato e o regime público opcional |
| **PDCA.5** | Last Planner: `Restricao`, `ProgramacaoSemanal`, PPC e catálogo de causas |
| **PDCA.6** | Linha de balanço sobre `LocalObra` — ritmo, sincronia de equipes, gargalo |
| **PDCA.7** | Verificação (FVS), `NaoConformidade` com pino da Prancheta, `PlanoAcao` 5W2H e verificação de eficácia |
| **PDCA.8** | SSMA: DDS, ocorrência, EPI |
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
