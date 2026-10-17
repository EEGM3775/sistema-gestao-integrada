# modulopdca — a tela: postos de trabalho, não páginas

> **Natureza: planta.** O desenho do frontend do PDCA — como a pessoa entra, onde ela trabalha e por
> que a navegação tem a forma que tem. O domínio está em [modulopdca.md](modulopdca.md); a régua de
> módulo e o design system em [../frontend.md](../frontend.md); as regras obrigatórias de código em
> [../frontend-convencoes.md](../frontend-convencoes.md); a identidade em
> [../identidade-visual.md](../identidade-visual.md). Status e faseamento vivem no
> [../roadmap.md](../roadmap.md).

## 1. O problema que este desenho resolve

O backend do PDCA tem **45 models, 24 recursos REST, ~75 verbos**. Transformado em
tela pelo caminho óbvio — um item de menu por assunto que o backend tem — isso produz um depósito:
foi o que aconteceu, e a queixa do dono foi exata: *"simplesmente jogando várias coisas lá dentro"*.

O erro não foi de capricho: é o que acontece quando a **navegação espelha o banco**. Cada fatia nova
acrescentou uma página, nenhuma soube o que a anterior fazia, e o usuário passou a escolher entre
portas em vez de trabalhar.

**A regra que nasce daqui, e vale para os módulos grandes que vierem:** a navegação não se organiza
pelo que o sistema *guarda*, e sim pela **cadência com que a pessoa volta**. Assunto do banco vira
conteúdo dentro de um posto; nunca vira item de menu.

## 2. As referências — o que o mercado já provou

| Produto | O que ele prova | O que fazemos com isso |
|---|---|---|
| **Procore** | O mais adotado do setor, e a crítica recorrente é a mesma queixa do dono: o conjunto extenso de recursos produz interface poluída e navegação pouco intuitiva. Ele organiza por **ferramenta** — dezenas por projeto | É o padrão **a não repetir**. Confirma que completude sem eixo de navegação é dívida, não vantagem |
| **Touchplan** | O produto inteiro é *uma* parede e *um* gesto: a linha que a equipe arrasta sobre o plano converte atividade em compromisso da semana. Não existe "página de PPC" — o PPC é consequência do gesto | O instrumento **é** o posto. O indicador não ganha tela própria: aparece onde o ato que o produz acontece |
| **Fieldwire · Dalux** | No campo, a **planta é a home**. O defeito nasce como pino com coordenada, foto e responsável; o formulário vem *depois* do toque | A superfície de campo abre no lugar, não no cadastro. `NaoConformidade` já tem pino da Prancheta e `local` — o desenho usa os dois |
| **Prevision** (BR) | Linha de balanço e Gantt nativos, replanejamento com impacto visível na hora, e **medição pelo app com foto e motivo do atraso** no mesmo ato | O mais próximo do domínio. Confirma medição e avanço como atos de campo, não de escritório |
| **Autodesk Build · Procore Schedule** | O mesmo cronograma tem **leituras diferentes por papel** — o planejador lê caminho crítico, o superintendente lê os próximos sete dias | Mesma fonte, vistas distintas. Não são telas distintas, e o papel escolhe a vista inicial |

O espinho comum dos que acertam: **poucas superfícies, cada uma com física própria; o objeto é
compartilhado; a cadência ordena o menu; o papel decide a porta de entrada.**

## 3. As três decisões estruturais

### 3.1 A obra é o contexto permanente, e a cadência ordena o menu

Entra-se **numa obra**. Dentro dela, seis postos na ordem do tempo do trabalho — do que se olha todo
dia ao que se mexe uma vez por mês. Sair da obra é ato explícito (a carteira, §6).

```
┌──────────────────────────────────────────────────────────────┐
│ ⬛ Malha    ▾ Residencial Aurora            ⌘K        ◐  EG  │
├──────────┬───────────────────────────────────────────────────┤
│ ● HOJE   │                                                   │
│  SEMANA  │            o posto ocupa a tela inteira           │
│  PLANO   │            e tem a física do instrumento          │
│  MEDIÇÃO │                                                   │
│  QUALID. │                                    ┌──────────────┤
│  SEGURAN.│                                    │  inspetor    │
│ ──────── │                                    │  do que está │
│ ⌂ carteira                                    │  selecionado │
└──────────┴────────────────────────────────────┴──────────────┘
```

O rail é **fixo em seis** e não cresce com as fatias futuras: apropriação (PDCA.9) entra em `PLANO` e
`MEDIÇÃO`, riscos e marcos (PDCA.10) em `PLANO`, pós-obra (PDCA.11) em `QUALIDADE`. Um sétimo item só
se justificaria por uma **cadência nova** — e não há.

**O que o posto está mostrando mora no endereço, e não num `useState`.** A obra vem da rota
(`/app/pdca/o/:obraId/<posto>`) e o recorte de dentro vem da query string — no `MEDIÇÃO`, o contrato,
o boletim e a vista (`?contrato=&boletim=&v=`). É o que faz todo link colável e a aba nova cair onde
estava. Guardar isso na memória do componente quebra a promessa em silêncio: um link com `?boletim=`
abria noutra vista e o boletim pedido ficava invisível ([D201](../historico-correcoes.md)), que é a
forma de falha que não parece falha — a pessoa conclui que o documento não existe.

Vale para os cinco postos que têm documento: `?contrato=&boletim=` na medição, `?nc=`, `?ficha=` e
`?modelo=` na qualidade, `?ocorrencia=` e `?dds=` na segurança. **E quem aponta para um documento
leva a ele, e não ao posto**: a linha da fila do dia, a paleta ⌘K e os links de integração (a NC que
veio de uma ficha, a ocorrência que virou investigação) montam o endereço por uma função só,
`enderecoDoDocumento` (`postos.ts`) — mandar à porta do posto para procurar de novo é o que faz a
fila virar lembrete.

### 3.2 Duas superfícies de verdade, não uma que encolhe

O escritório e o canteiro não são o mesmo software em larguras diferentes. Têm identidade única e
**física oposta**:

| | Escritório | Campo |
|---|---|---|
| Entrada | A obra, no posto do seu papel | **A minha frente de hoje** |
| Densidade | Máxima — mono tabular, grade, várias decisões à vista | Mínima — **uma decisão por tela** |
| Alvo | Cursor, teclado, atalho | Dedo de luva, ≥ 48 px, alcance do polegar |
| Ato típico | Decidir sobre o que os outros fizeram | **Produzir o dado**: apontar, responder, fotografar |
| Condição | Sentado, monitor, rede boa | Sol, capacete, rede ruim |

O campo não é um recorte do escritório: quatro atos moram lá (§7), e são os atos que **produzem** o
número que todo indicador acima consome. Frontend de campo ruim é indicador inventado.

### 3.3 O papel escolhe a porta, e nunca esconde o resto

Sete personas ([modulopdca.md §5.3](modulopdca.md)) não viram sete produtos. O papel decide **onde
você cai** ao abrir a obra e **qual vista o posto abre primeiro** — não o que existe.

| Papel | Cai em | Vista inicial |
|---|---|---|
| Planejador | `PLANO` | Gantt, com caminho crítico |
| Engenheiro de obra | `SEMANA` | Quadro da semana corrente |
| Encarregado / mestre | **Campo** | Minha frente de hoje |
| Gestor de contratos | `MEDIÇÃO` | Fila de apuração e atesto |
| Técnico da qualidade | `QUALIDADE` | Fila do laço aberto |
| Técnico de segurança | `SEGURANÇA` | Fila da CAT (tem prazo legal) |
| Fiscal / gerente | `HOJE` | Fila de decisão |
| Diretor | **Carteira** | Obras lado a lado |

A chave é o **nome da persona de fábrica** (`roles` do `/auth/me/`; o engenheiro de obra é a
`engenharia`, o gerente é a `diretoria`) e a regra mora em `portaDoPapel` (`postos.ts`). Só o
endereço sem posto (`/app/pdca/o/:id`, e o nome da obra na carteira) passa pela porta; a fila, a
paleta e o link colado levam ao posto que nomeiam. Quem acumula papéis cai pelo de **quem assina**
(fiscal, diretoria → `HOJE`) e, depois, pela ordem de consequência da §4.5 (segurança, medição,
semana, qualidade, plano). A vista inicial de cada posto já é a do papel que mora nele; o Controle,
que serve a dois, abre em **Hoje** para quem assina e na **Semana** para o engenheiro de obra
(`entradaDoPapel`, `?aba=semana`). Papel renomeado ou montado à mão não casa com nada e cai em `HOJE`, e o
papel cujo posto está trancado para a pessoa passa a vez ao seguinte. **O campo não tira ninguém da
obra**: a superfície de campo não é de obra nenhuma, então o encarregado que abre uma obra no
escritório cai em `HOJE`; a porta dele é a **passagem para o campo** no topo da carteira.

## 4. A espinha — o que atravessa todos os postos

Sem isto, seis postos são seis depósitos menores.

### 4.1 O contexto de obra

Um seletor na topbar, presente em toda tela do módulo. Trocar de obra **mantém o posto** — quem está
comparando a semana de duas obras não quer voltar ao início. O contexto vive na rota
(`/app/pdca/o/:obraId/semana`) para que todo link seja colável e toda aba nova abra onde estava.

### 4.2 O objeto compartilhado

**A mesma atividade** é barra no Gantt, reta na linha de balanço, cartão no quadro da semana, linha
na planilha de medição e alvo da ficha de verificação. Selecionar num posto **mantém a seleção** ao
trocar de posto. É o que transforma seis instrumentos em um sistema — e é a diferença entre "tenho
seis telas" e "olho a mesma obra de seis ângulos".

### 4.3 O inspetor — detalhe sem trocar de rota

Selecionar qualquer coisa abre um painel à direita com o que ela é, o que falta nela e **os verbos
que você pode exercer**. Master-detail in-place já é regra Malha ([frontend.md §1.5](../frontend.md));
aqui é estrutural: é o inspetor que absorve os ~75 verbos do backend sem que nenhum vire uma página.

O inspetor é também onde a **integração aparece**: a atividade mostra o item orçado que a lastreia, a
etapa da obra, a NC aberta contra ela e a medição que a pagou — todos clicáveis, atravessando módulo
quando for o caso.

### 4.4 A paleta de comando (⌘K)

A válvula que permite manter o rail em seis. Busca **uma só** sobre obra, atividade (por código de
EAP), local, contrato, medição, ficha, NC e ocorrência — e executa verbo direto (*"atestar medição
07"*, *"abrir NC"*). Sem acento, pela régua ([frontend-convencoes.md §6](../frontend-convencoes.md)).
Quem usa o módulo todo dia para de navegar por menu na primeira semana.

**A divisão do trabalho é por onde o dado já está.** Postos e obras são a navegação da própria
casca, já estão em memória e se filtram na tela — ir ao servidor para achar "Plano" seria latência
sem ganho. As sete espécies de registro vêm do `busca/`, agrupadas por espécie e cortadas **por
espécie**: quarenta atividades chamadas "alvenaria" não podem esconder o contrato que também se
chama assim. Um alternador limita à obra corrente ou abre para a carteira inteira.

**O piso de duas letras precisa aparecer mesmo havendo resultados.** Abaixo dele o servidor não
varre, e como postos e obras casam com quase qualquer letra, quem digita `a` procurando "alvenaria"
veria uma lista cheia e concluiria que a alvenaria não existe. A tela diz o piso em vez de deixar
a pessoa adivinhar.

### 4.5 A fila de decisão é uma, e mora na obra

O backend já tinha o padrão certo — `ncs/fila` e `ocorrencias/fila` devolvem *o que espera alguém,
agora*, não uma contagem. O desenho **unifica** as filas dos seis postos numa só, em `HOJE`, com a
mesma linha: o que é, há quanto tempo espera, **o que decidir** e o botão que decide.

Nunca um hub que soma o que não se soma: uma NC sem plano e uma medição sem atesto não viram "12
pendências". Ficam em **onze faixas nomeadas**, agrupadas em cinco degraus de consequência, e a
ordem dos degraus não é negociável:

| Degrau | Por que vem antes | Faixas |
|---|---|---|
| **prazo legal** | Tem prazo em lei e multa, e não se recupera depois | CAT por comunicar |
| **segurança** | Pode estar escondendo uma comunicação devida | ocorrência por classificar · ocorrência sem tratamento aberto |
| **dinheiro** | O pagamento do empreiteiro depende da decisão | medição esperando atesto |
| **compromisso** | A equipe assumiu e a semana precisa fechar | semana por encerrar · restrição vencida · restrição vencendo |
| **retrabalho** | Custa serviço refeito se ficar parado | defeito sem plano · ação vencida · conserto por conferir · ficha parada |

O servidor devolve a **origem** de cada faixa (o assunto), e não a rota: navegação é da tela, e uma
rota na resposta faria renomear um posto virar mudança de API. Faixa sem ninguém esperando **não
entra** na resposta — aviso que aparece sempre e não pede ação ensina a ignorar a tela —, e a
resposta diz quantas foram varridas para o estado vazio poder ser uma frase em vez de uma página em
branco.

## 5. Os seis postos

### 5.1 HOJE — o pulso e a fila

**Cadência:** todo dia, primeiro minuto. **Pergunta:** *o que exige a minha decisão, e como a obra
está indo?*

- **Fila de decisão unificada** (§4.5) — a faixa de cima, sempre.
- **Pulso da obra** — quatro leituras honestas lado a lado: avanço físico × linha de base, PPC da
  última semana encerrada (com a série ao lado, porque um PPC isolado não diz nada), conformidade do
  período e dias sem ocorrência com afastamento. Cada uma clicável para o posto que a explica.
- **O que mudou desde ontem** — fatos, não posts: medição atestada, semana encerrada, NC aberta,
  cronograma replanejado, ocorrência classificada. Cada linha é um ato com carimbo de quem o
  praticou, lido do campo que o registrou — **não há tabela de evento**, e não deveria haver: um log
  paralelo divergiria do fato na primeira vez que alguém gravasse por outro caminho.

**Os três blocos vêm numa chamada só** (`GET hoje/`). Em chamadas separadas a tela esperava três
vezes e — pior — cada número chegava com um recorte de período diferente do vizinho.

**Dado honesto, e aqui é obrigatório:** avanço sem apontamento é *"sem apuração"*, nunca 0%. Taxa de
frequência e de gravidade voltam `null` do backend porque dependem de homem-hora, que ainda não é
apurado — a tela **diz o que falta**, e não desenha zero. Zero diria que a obra é segura quando o que
houve foi ninguém medir. Cada bloco traz do servidor a frase do que falta (`sem_apuracao_porque`), e
é ela que aparece **no lugar** do número — nunca embaixo de um zero.

**Onde o zero vira nulo, e por que não na conta.** `avanco_do_cronograma` devolve `0.0` para o plano
em que ninguém apontou, e está certo: a média ponderada de atividades com peso e sem apontamento é
zero, e é isso que a barra de cada linha do Gantt desenha. No cockpit a mesma resposta mente —
"avanço 0%" ao lado de "PPC 68%" lê-se como *a obra não andou*. A conversão acontece no consumidor,
que é o que evita mexer no número de que o posto `PLANO` depende.

### 5.2 SEMANA — o Last Planner

**Cadência:** semanal, com hora marcada. **Pergunta:** *o que a equipe assume, e por que o que não
saiu não saiu?*

Um **canvas** de arrastar próprio — nada de biblioteca de kanban genérica, cujo modelo de coluna não
é o do quadro semanal: lá a coluna é o *estágio do cartão*, aqui ela é **quem assume**. A lição do
Touchplan: o quadro **é** o posto, e o PPC é consequência do gesto, não uma tela ao lado.

**Arrastar nunca é o único caminho.** Quem usa teclado não arrasta, e numa reunião com o quadro
projetado — ou num tablet — arrastar entre colunas é pior do que escolher. Todo gesto do quadro tem
o par clicável: o candidato traz o verbo de puxar e o cartão traz o seletor de dono. É a régua de
acessibilidade da busca sem acento ([§6 das convenções](../frontend-convencoes.md)) aplicada ao
gesto em vez do texto.

- **Esteira de restrições** à esquerda: o que trava, quem resolve, quando vence. Restrição de
  material, equipamento ou mão de obra gera demanda no SCM pelo verbo que já existe — e o vínculo fica
  visível — com o andamento da compra e o "destravar" quando o material chega. As **destravadas
  continuam embaixo**, riscadas, com quem destravou e como, e reabrem.
- Cada cartão leva o **selo do material** (no estoque · a caminho · falta) lido da fila de suprimentos, e
  o compromisso tem **"Pedir material"** (requisição em rascunho no Estoque, com o estado no cartão).
- **Quadro da semana** ao centro: candidatos → comprometidos, por equipe e por dia. Atividade com
  restrição aberta **não entra**, e o quadro diz por quê ao tentar.
- **Encerramento** como ato: julgar item a item **no próprio cartão** — a pergunta "saiu?" mora
  onde o serviço está, e não numa lista paralela —, causa obrigatória no não cumprido, e o PPC
  calculado na hora, devolvido **com a base do peso** e com quantos cartões ficaram fora da
  divisão. O que não saiu **arrasta** para a semana seguinte em rascunho, com o contador de semanas
  de pé. Encerrar antes do fim da semana é verbo à parte, com motivo escrito, e marca o ponto na
  série. A semana que **já acabou** abre julgando: é a reunião de segunda olhando a semana passada,
  e pedir um clique a mais só atrasaria o gesto.
- **Ranking de causas** no rodapé, cumulativo, em três partes que somam o total.

**As colunas são as equipes da obra** (`EquipeObra`): "Nova equipe" **compõe** — funcionários do RH e
fornecedores, nome opcional (nasce dos membros) — e o cabeçalho mostra quem é a equipe. Nome solto de
cartão antigo aparece como "sem composição". **Julgar é dizer o % concluído** da atividade: o cartão
mostra a meta da semana e onde ela está hoje, diz se bateu a meta (o "saiu" é derivado) e pede a causa
quando não bateu; o servidor lança a diferença como avanço.

### 5.3 PLANO — o cronograma e o ritmo

**Cadência:** por evento (montar, publicar, replanejar). **Pergunta:** *quando cada coisa acontece, e
o que segura o quê?*

Quatro vistas sobre **o mesmo cronograma**, trocáveis sem trocar de rota:

| Vista | Física | Para quem |
|---|---|---|
| **Grade EAP** | Planilha: digitar duração, predecessora (`1.2FS+3d`), peso. Escrita em lote | Planejador montando |
| **Gantt** | Barras, caminho crítico, linha de base sobreposta | Planejador, gerente |
| **Linha de balanço** | SVG próprio — retas local × tempo, ritmo, sincronia, gargalo | Planejador de obra repetitiva |
| **Calendário** | Dias úteis, exceções, expediente | Quem define jornada |

**Rascunho × vigente é a espinha do posto**, não um detalhe: o rascunho se edita à vontade, o vigente
não se toca, e replanejar abre a versão seguinte com motivo. A tela deixa claro **em qual você está**
o tempo inteiro — a barra de contexto muda e o verbo de publicar fica à vista.

- **O posto abre o rascunho em montagem** (`usePlanoEmEdicao`), não o vigente: se há rascunho mais novo
  que o vigente, é nele que se trabalha. A Semana e o Hoje seguem no vigente (`usePlanoCorrente`).
- **Uma versão em rascunho por vez** — replanejar com um rascunho aberto é recusado no servidor.
- **Seletor de versão** no topo (v4 · em montagem, v1 · o combinado, sobras de rascunho), com faixa
  dizendo o que a versão é: rascunho (ver o vigente · descartar), vigente com rascunho aberto (abrir o
  rascunho), vigente sem rascunho (replanejar), substituída (só leitura). Replanejar leva a tela à
  versão nova. A escolha mora no contexto do PDCA (`planoEscolhido`), e o Inspetor lê dela.
- **Restrição é do plano em execução.** No rascunho, a linha mostra as restrições da gêmea vigente
  (mesmo código EAP); ao publicar, as abertas passam para a versão nova ([modulopdca.md](modulopdca.md)).

**O plano se monta aqui dentro, sem sair do posto** — e por qualquer porta. *(Decisão do dono,
09/10/2026: "hoje só consigo criar tarefa e mais nada. Quero fazer tudo.")*

- **Obra sem plano abre o assistente** (`AssistenteDoPlano`): início e **expediente** (cadastrado ali
  mesmo, se a empresa não tem — sem expediente o CPM não dá data) → **ponto de partida** → etapas e
  atividades com duração (sugestões de fase clicáveis) → sequência (fase depois de fase; atividade
  depois de atividade) → criar. Os quatro pontos de partida: **digitar**, **do orçamento**, **de um
  modelo**, **colar do Excel / XML do MS Project**. Orçamento e colar criam o plano e abrem o diálogo
  respectivo; o modelo aplica direto. Plano já criado e vazio mostra as mesmas quatro portas.
- **A grade é planilha de verdade** (`GradeEap`), no molde do MS Project: setas andam entre células;
  Enter/F2 ou digitar edita; Enter grava e desce; Tab (editando) grava e vai à direita; **Insert** ou
  Shift+Enter cria a linha abaixo já com o nome em edição; Ctrl+Enter cria dentro; **Tab recua**
  (entra na irmã de cima) e **Shift+Tab avança**; Alt+↑↓ muda a ordem; Delete exclui; Ctrl+V cola;
  Ctrl+Z desfaz. A alça da linha **arrasta** para antes, depois ou **dentro** de outra (o terço do
  meio da linha-alvo). Colunas escolhidas pela pessoa (EAP, atividade, duração, **predecessoras**,
  início, término, folga, local, responsável, peso), guardadas no `localStorage`. Duração 0 vira marco.
  A coluna Predecessoras se digita na grafia do Project (`1.2; 1.3SS+2; 4FF-1`, também TI/II/TT/IT).
- **O Gantt é instrumento, não desenho**: arrastar a barra grava "não começar antes de" (e o CPM decide
  onde ela fica); puxar a ponta muda a duração; os **pinos** nas pontas da barra selecionada ligam a
  outra barra — do fim, FS ou FF; do início, SS ou SF, conforme se solta perto do começo ou do fim da
  alvo; clicar na seta abre o editor (tipo, defasagem, desligar). Restrição com prazo aparece como
  marca na linha, vermelha quando chega depois do início previsto.
- **A seta chega pelo lado certo**: por trás no início (FS, SS), pela frente no término (FF, SF); sem
  espaço entre as barras, desvia pela fronteira entre as linhas em vez de voltar por cima da barra.
- **A barra se corta nos dias parados** do expediente dela (fim de semana, feriado, recesso), e o fundo
  do Gantt sombreia os do plano — feriado e exceção num tom próprio, com o nome no cabeçalho. Vem do
  bloco `expedientes` do `gantt/`: os feriados são os do lugar da obra, os mesmos da Agenda.
- **Escala contínua**: atalhos dia · semana · mês · trimestre, deslizante (logarítmico), −/+ e
  "caber" (o plano inteiro na largura). A régua de tempo se adapta à densidade; a escala fica guardada.
- **O Inspetor edita tudo** da atividade: nome, marco, duração, data mínima, expediente próprio (vazio =
  herda o do plano, e o rótulo diz qual), rede inteira para trás (**Depende de**) e para frente
  (**Libera**) com tipo e defasagem — com cabeçalho das colunas e legenda dos tipos —, **restrições**
  (material, projeto, licença…) com prazo, "pedir compra" (material) ou "pedir contratação" (equipamento,
  mão de obra) no SCM com link à demanda, e a opção de segurar a atividade até o prazo; a **resolvida
  fica na lista**, riscada, com a nota, e pode ser **reaberta**. Peso informado (o bloco explica que o
  peso pondera o avanço físico da etapa e da obra), local, etapa da obra, **item orçado** (busca no
  orçamento da obra), responsável (RH) e observação. Data digitada só grava inteira (`CampoData`).
  Na **etapa**, o bloco de peso é a **composição**: cada filha com o peso (digitável ali mesmo) e a parcela
  na etapa, e o peso da etapa (soma das filhas) com a parcela na obra; na folha, a participação (% da etapa
  · % da obra). A coluna Peso da grade mostra o número e a parcela da obra (`pesos.ts`). As listas de
  dependência seguem a ordem da árvore, não a do código. Sem locais, o seletor de local explica o que é e
  leva ao cadastro.
- **Etapa liga com etapa** — a ligação de fase ("a alvenaria começa quando a estrutura termina") é uma
  seta na tela e o CPM a expande nas folhas ([modulopdca.md §4.2](modulopdca.md)). Uma etapa não se liga
  ao que ela contém.
- **Menu Montar**: nova etapa, atividade (abaixo da selecionada, ou dentro se ela é etapa), marco, colar
  / abrir MS Project, trazer do orçamento, modelos (trazer para o fim deste plano, ou salvar este como
  modelo), encadear as etapas. Abre por cima de tudo, dentro da janela, mesmo com o botão quebrado.
- **Várias de vez**: Ctrl+clique marca e desmarca, Shift+clique e Shift+↑↓ marcam o intervalo, Ctrl+A
  marca todas, Esc desmarca. Delete, Tab, Shift+Tab e arrastar valem para o lote, e o Inspetor vira o
  **painel do lote**: encadear em sequência, desligar entre elas, recuar, avançar, excluir e aplicar a
  todas duração, data mínima, local, responsável e expediente — cada ação é **um** passo no desfazer.
- **Desfazer e recálculo** moram no store `montagem.ts`, compartilhado pela grade, pelo Gantt e pelo
  Inspetor. *(Decisão do dono, 09/10/2026: o Ctrl+Z vale "enquanto estou na tela ou até eu finalizar o
  plano".)* A pilha é **dado, não função**: operações inversas serializáveis, guardadas por plano no
  navegador — sobrevivem a recarregar e a trocar de posto, e zeram ao publicar ou replanejar (até 100
  passos). Ligações são lembradas pelo par (origem, destino). **Excluir também volta**: a tela fotografa
  a subárvore antes de apagar e o inverso é `restaurar-linhas/`, cujo mapa de ids corrige o resto da
  pilha. O Ctrl+Z vale com o foco em qualquer lugar do posto, menos num campo de texto em digitação.
  Cada gesto dispara o CPM; o motivo de não ter calculado vira faixa no posto.
- **Excluir pergunta num diálogo do sistema** (quantas linhas vão junto, quantas ligações saem, que
  dá para desfazer, e quais restrições não voltam), e a linha **some na hora** — o servidor apaga,
  recalcula e confirma por trás.
- **Recolher é estado da pessoa**: a etapa recolhida esconde as filhas e continua recolhida ao
  recarregar (por plano, no navegador).
- O topo do posto mostra e edita o **início** e o **expediente** do plano, e o término calculado.

A **etapa do plano (raiz) é a etapa da obra**: criar uma etapa cria a etapa da obra e liga as duas, e
renomear uma renomeia a outra (salvo se outra atividade usa a mesma etapa). No plano vigente, o único
verbo de escrita é **Replanejar**, com motivo; as restrições continuam registráveis (são do make-ready).

*Limites declarados:* o `.mpp` é binário fechado — a tela pede o XML do Project. O esticar da barra
conta os dias úteis pelo expediente da atividade (com feriado e exceção), e o servidor refaz pelo CPM.

**Vista Suprimentos** — a fila "comprar até": por insumo, necessário × estoque × pedido × demanda × a
comprar, a data de pedir (atrasada em vermelho), expandindo para as atividades (chegar até, de onde vem a
antecedência); antecedência padrão da obra e exceção por insumo editáveis ali; marcar e **gerar demanda**;
avisos de cobertura (atividade fora da conta, sem orçamento aprovado, revisão do orçamento com "religar")
e da sobra em outro almoxarifado. **Vista Custo** — por etapa (expande para atividades): orçado ×
comprometido × recebido × aplicado × medido, com "acima do orçado" e a linha do que não tem dono. No
Inspetor, o bloco **Material** da atividade (insumos, situação, chegar até, antecedência própria) e o
custo dela. A restrição mostra o **andamento da compra** e oferece "Material recebido — destravar".

**Vista Avanço R$** — o avanço físico-financeiro: por etapa e da obra, previsto pelas datas × realizado
apontado (% e R$ do orçado), e contra o **planejado no cronograma do Orçamento**; a curva S troca a régua
(datas do plano ou planejado no Orçamento). O cronograma físico-financeiro se monta no Orçamento, que
linka de volta para esta vista. **Faixa do expediente** — feriado/parada lançado depois do cálculo que cai
dentro de barras: cita os dias e as atividades; no rascunho recalcula, na versão congelada manda
replanejar. Excluir uma etapa avisa que ela sai também das etapas da obra (ou, no rascunho do
replanejamento, que sai ao publicar). As parcelas de peso em % somam 100% (maior resto).

A hierarquia de locais e a biblioteca de planos modelo moram **aqui dentro**, como painéis do posto
(§8), não como itens de menu. O painel **Locais** explica o que é um local e cadastra ali mesmo — no
topo ou dentro de outro, um por vez ou em série ("Trecho" × 12 → Trecho 1…12, código seguido do pai) — e
exclui. A vista do posto mora na URL (`?vista=locais`), para o Inspetor levar direto a ela.

### 5.4 MEDIÇÃO — o dinheiro

**Cadência:** mensal, fecha o mês. **Pergunta:** *quanto se deve, por que, e quem autoriza?*

É o posto de maior consequência: o número vai para o cliente e para o pagamento do empreiteiro.

**A porta é a fila, e a fila é documento parado.** Quatro blocos, na ordem do caminho que o dinheiro
percorre: boletim apurado e não enviado · boletim esperando atesto (com o degrau e de quem se
espera) · retenção pedida de volta · aditivo sem decisão. Cada um traz o verbo que o fecha, e clicar
abre o documento **no próprio posto**, ao lado da grade que explica o número — quem ateste está
olhando a medição, e mandá-lo a outra tela separaria a decisão da evidência.

**Não existe faixa de "contrato sem medir há N dias", e a ausência é desenho.** De quanto em quanto
tempo se mede é cláusula combinada com cada empreiteiro; o contrato não guarda esse campo, e
qualquer corte seria número inventado em código — acenderia todo dia para todo contrato vigente, que
é o aviso que ensina a ignorar a fila. O período que a próxima medição cobriria viaja **no
contrato**, como informação ao lado dele.

- **Contratos da obra** com saldo, retenção acumulada e aditivos — a leitura de cima. O contrato
  também **nasce aqui**: sem isso o estado vazio pediria uma ação sem caminho. O formulário só
  aparece para quem tem `pdca.contrato.edit` — a diretoria ateste e não monta contrato, e o verbo
  some em vez de aparecer e recusar.
- **Dentro do contrato, um mapa — não abas** (pedido do dono: "igual um jogo com ótimo design de
  mapas: sempre deixa saber o caminho, sem ficar avisando"). O caminho é uma linha só: **Contrato →
  Vigente → Medir → Aprovação → Executado**, derivado do saldo (`trilha.ts`). O feito fica marcado,
  a próxima parada brilha, a aberta tem o anel de "você está aqui"; clicar leva até ela. Aditivos e
  Retenção são desvios ao lado da estrada. Sem vista no endereço, o contrato abre na próxima parada.
  Nenhuma faixa de aviso: o mapa mostra.
- **Contrato** (`FichaDoContrato`, `?v=planilha`) — o contrato inteiro: o dinheiro do contratado ao
  pago no ERP, o cadastro, a linha do tempo (medição retificada riscada, apontando para a que a
  substituiu), os itens com medido e saldo, e a planilha contratual embaixo, editável até a primeira
  medição.
- **Vigente** — o resumo do contrato e o botão **Tornar vigente** (`ativar/`): unitário precisa de
  planilha, global/administração do valor fechado.
- **Planilha contratual** — em ordem natural de código, toda linha editável inteira (código,
  descrição, unidade, quantidade, preço) e com o **vínculo escolhido na linha** (atividade do plano
  ou item do orçamento; sem vínculo = digita-se na medição). Entra de quatro jeitos: **do orçamento**,
  **do plano**, **colando do Excel** e item avulso (`fontes-da-planilha/` + `incluir-na-planilha/`,
  tudo ou nada). Ela **fecha** quando o contrato não permite mais editar. A trava vem do backend
  (`planilha_editavel`, `planilha_fechada_porque`) e a tela **lê a resposta**, nunca reimplementa a
  condição ([convenções §11](../frontend-convencoes.md)).
- **Medir** juntou Apurar e Boletins: o período e a prévia em cima, os boletins embaixo. Na grade,
  item ligado vem proposto pelo avanço e item sem vínculo se digita — os dois na mesma grade.
- **Apurar** — a medição nasce do avanço apontado, não da digitação. A proposta vem pronta do
  servidor e a grade mostra a **memória de cálculo** de cada linha: de onde veio o número.
- **Prévia** — somente leitura por desenho, e a tela **diz isso**: número é texto, não `input`
  desabilitado ([convenções §10](../frontend-convencoes.md)). A mesma grade desenha a prévia e o
  boletim aberto; duas grades para as mesmas dez colunas divergiriam na primeira coluna nova.
- **A grade grava sozinha, e não tem botão de salvar.** Selo permanente de estado, aviso do
  navegador ao fechar a aba com gravação pendente, e **enviar grava antes de enviar** — desistindo
  do envio se a gravação falhar. Botão de salvar separado do enviar é o D137, e a F.4 o reconstruiu
  sem querer ([D202](../historico-correcoes.md)): o servidor congela o que está *gravado*, não o que
  está na tela. Passar do saldo acende a trava **na linha, na digitação**, com o saldo do servidor
  ao lado.
- **Escada de atesto** — submeter, atestar, cancelar; Cancelar
  medição aprovada cancela o título no ERP, e o aviso sai do mesmo lugar da trava.
- **Aditivo** e **deduções** como painéis do posto, porque só existem em função do contrato. O
  aditivo se monta no `EditorDeAditivo`, como um contrato: termo (objeto, motivo, prorrogação, nova
  retenção), cada item existente (acréscimo, supressão, preço novo, retenção própria), itens novos e o
  antes → depois do contratado; o rascunho se edita, exclui ou envia, e o que está na escada se retira.
- **Retificadora** — a grade vira o quadro original | corrigido | diferença, e o boletim ganha a
  conciliação (líquido antes, corrigido, diferença; o efeito no saldo e no ERP).

### 5.5 QUALIDADE — o laço que fecha

**Cadência:** contínua, disparada por evento. **Pergunta:** *o que reprovou, quem está tratando, e
acabou mesmo?*

- **Fila do laço aberto** — NC sem plano (ninguém pegou), ação vencida (pegou e não fez), NC
  esperando eficácia (fez e ninguém conferiu), ficha parada no meio. O backend já devolve estas quatro.
- **Painel de conformidade** — o que mais reprova, cumulativo, cada linha partida em *em tratamento*,
  *sem NC aberta* e *já resolvida*.
- **A NC no lugar** — quando tem pino da Prancheta ou local, a tela mostra **onde**, não só o texto.
- **Plano de ação 5W2H** e **verificação de eficácia** no documento da NC, um embaixo do outro,
  porque são passos do mesmo laço e não assuntos separados. Só a eficácia fecha a NC — a tela nunca
  oferece outro caminho, e diz que quem montou o plano não assina que ele funcionou. O documento é
  página do posto, e não o inspetor lateral: são quatro blocos com formulário, e o inspetor é para
  ver o que algo é sem trocar de rota.
- **A ficha no escritório** é a mesma do campo em lista: cada resposta grava sozinha, e a conclusão
  mostra os reprovados **com o peso que cada um recebeu** antes de abrir os defeitos de uma vez.
- **Biblioteca de modelos de ficha** como vista do posto (§8), gravando campo a campo.

Quatro vistas, e o endereço decide qual: **o laço aberto** (a fila do posto ao lado do painel),
**defeitos**, **fichas** e **modelos de ficha**. A fila é a do degrau de retrabalho da fila do dia,
recortada (B8) — as duas não podem discordar sobre o mesmo defeito.

### 5.6 SEGURANÇA — o prazo legal e o fato que ninguém queria

**Cadência:** diária (DDS, antes do turno) e por evento (ocorrência). **Pergunta:** *o que fazemos
para ninguém se machucar, e o que fazemos quando alguém se machuca?*

Posto separado da qualidade **de propósito**, e a razão não é organizacional: uma ocorrência tem
**prazo legal** (a CAT é devida no 1º dia útil, imediata na morte), tem **dado clínico sensível**,
e não pode entrar numa fila atrás de um defeito de pintura.

- **Fila da SSMA** com a CAT no topo e o prazo em contagem regressiva.
- **DDS** — a roda antes do turno: tema, lista de presença, encerramento que escreve no Diário.
- **Ocorrência** — do quase-acidente ao óbito. **Registrar é de baixo atrito e sem teto**; classificar
  é verbo à parte, porque quem é medido não classifica a própria medida.
- **Bloco clínico** (lesão, CID, atestado) sob `pdca.ocorrencia.dado_medico`, com porta de mídia
  própria — a foto da cena e o atestado não saem pelo mesmo gate.
- **EPI vencido** lido do SIL sob `sil.epi.view`; sem o módulo contratado, a indisponibilidade é
  **declarada**, não escondida.
- **Taxa de frequência e de gravidade** aparecem como *sem apuração*, com a frase do servidor —
  dividem por homem-hora, que o sistema não apropria.
- **Frentes interditadas** à parte, e não como faixa: liberar é remover a restrição, na semana; aqui
  elas são o que impede encerrar a ocorrência que as abriu.

Três vistas: **o que pede ação** (a fila, com a CAT no topo, ao lado dos números), **ocorrências** e
**diálogos de segurança**. A fila é a das faixas de prazo legal e segurança da fila do dia (B9).

## 6. A carteira — fora da obra

A porta de fora, e a casa da diretoria: as obras lado a lado com avanço físico, desvio de prazo
contra a linha de base, PPC, conformidade e dias sem afastamento. Uma linha por obra, ordenável
pelo que dói. Clicar entra na obra, no posto que explica o número clicado.

Não é um painel de vaidade: é **fila de decisão em escala de carteira** — qual obra precisa de você
esta semana. E por isso ela **não soma o que não se soma**: cada linha traz as pendências
discriminadas (*"CAT por comunicar · 1"*, *"Defeito em aberto · 3"*) e nomeia a **pior** pela ordem
de consequência da §4.5, que é o critério da ordenação padrão.

**A carteira conta, a fila lista — e os dois têm de bater.** A contagem sai de sete consultas
agregadas para todas as obras; listar quarenta obras custaria quarenta varreduras com prefetch e
quarenta cálculos de prazo de CAT, e a carteira não mostra linha nenhuma. Os fatos contados são os
mesmos da fila, e há teste cobrando isso: se divergissem, a diretoria decidiria por um número e a
obra trabalharia por outro.

**SPI e CPI ficam de fora, e a ausência é decisão.** As duas são de valor agregado e o CPI precisa
de custo real, que mora no ERP; desenhá-las a partir do que o módulo tem hoje seria índice com nome
de norma e conta inventada. Entram quando a apropriação existir.

**O teto é de leitura, e o caro é o avanço**: cada linha custa o rollup do cronograma vigente
daquela obra. Acima dele a resposta vem cortada **dizendo quantas ficaram de fora** — carteira
truncada em silêncio é a diretoria decidindo sobre quarenta obras achando que viu todas.

## 7. A segunda superfície — Campo

Rota própria e casca própria: sem rail, sem inspetor, sem grade. Instalável, e a ausência de offline
é **declarada** enquanto o PWA for fase de plataforma.

**Home = minha frente de hoje**: o que eu assumi nesta semana no quadro (§5.2), o que está atribuído
a mim e o que vence hoje. Nada mais.

**"Meu" é um nome, e a tela deixa trocá-lo.** `responsavel`, `quem` e `inspetor` são rótulo durável
em todo o módulo, e não FK de usuário — a razão é do domínio ([modulopdca.md](modulopdca.md)): quem
assume a frente é com frequência o encarregado da empreiteira, e quem destrava é o projetista ou o
fiscal da prefeitura, que não têm login. A leitura casa por nome **sem acento e sem caixa**, devolve
contra qual nome procurou, e a casca oferece escolher outro. Sem essa saída, a pessoa que o
escritório registrou como "Mestre Antônio" e que entra como `antonio.silva` veria a frente vazia
para sempre — e frente vazia é a pior forma de falha, porque não parece falha.

Quatro atos, e cada um cabe num polegar:

| Ato | Abre em | Regra |
|---|---|---|
| **Apontar avanço** | A minha atividade, com o quanto já foi apontado | Número grande, teclado numérico, foto opcional; estornar o próprio erro é um toque |
| **Responder ficha** | O item, um por tela | Conforme / não conforme / N.A. / pendente; **gravidade é perguntada no item** quando reprova, e só aí |
| **Abrir NC com foto** | **A câmera**, não o formulário | Local pré-preenchido pela frente; o texto vem depois da foto |
| **DDS e ocorrência** | Lista de presença · o fato | Registrar sem atrito; classificar não é do campo |

A lição do Fieldwire/Dalux aplicada ao que já existe no backend: `NaoConformidade` tem `local` e pino
da Prancheta — o campo abre **no lugar**, e o formulário é consequência do toque.

**As rotas.** A home ganha um bloco *Registrar* com os três atos que nascem no canteiro:
`/campo/defeito` (abre pela câmera), `/campo/ocorrencia` e
`/campo/dds` → `/campo/dds/:id` (a roda, um nome por vez, e o encerramento que escreve no diário).
Obra, local e serviço chegam preenchidos pela query string quando se vem da frente. A ficha
pendente no nome da pessoa vira link para `/campo/ficha/:id` — uma pergunta por tela, *conforme*
grava no toque, o desvio pede o texto e o peso antes de gravar, e a foto sobe na mesma requisição da
resposta. No fim, concluir e abrir o defeito do que reprovou, dali mesmo.

Grupo de botões de escolha é `fieldset`, nunca `label`: tocar no texto de um rótulo aciona o
primeiro controle dentro dele, e aqui isso escolheria a primeira opção sem a pessoa pedir.

## 8. Onde mora a configuração — e por que ela não tem menu

Locais da obra, calendário de trabalho, planos modelo, modelos de ficha e catálogo de causas são
**setup**, não cadência. Cada um vive como painel dentro do posto que o consome:

| Configuração | Mora em |
|---|---|
| Hierarquia de locais · calendário · exceções | `PLANO` |
| Biblioteca de planos modelo | `PLANO` |
| Modelos de verificação | `QUALIDADE` |
| Catálogo de causas | `SEMANA` |

**A regra:** configuração que ganha item de menu vira assunto; assunto vira porta; porta vira
depósito. Foi assim que o depósito nasceu da primeira vez.

## 9. Componentes e bibliotecas

Tudo sai de `components/malha/` e dos tokens de `index.css` — nada de cor fixa, nada de kit paralelo.

**Novos primitivos que este módulo promove à camada compartilhada** (porque outros módulos vão pedir):
`ContextoDeObra` (o seletor da topbar), `PaletaDeComando` (⌘K), `Inspetor` (painel lateral com verbos),
`FilaDeDecisao` (a linha que diz o que decidir e traz o botão) e `CascaDeCampo` (a casca da segunda
superfície). E uma correção no `Modal` da Malha, que vale para todos os módulos: ele se anuncia como
`role="dialog"`, com `aria-modal` e o próprio cabeçalho como rótulo — sem isso um leitor de tela lê o
cartão como mais um trecho da página, e quem não enxerga não sabe que o resto ficou inerte.

**Percentual passa pelo `formato.ts` do módulo.** O avanço atravessa como `float` e o PPC e a
conformidade como string (é assim que o DRF serializa `Decimal`, e é assim que centavo não vira
dízima): renderizados crus, a mesma linha da carteira mostrava `77,6%` ao lado de `21.7%`. Régua da
identidade §6 — colunas são réguas, e régua com duas marcações não mede nada.

**As peças do módulo que a F.5 promoveu**, porque os dois postos novos e o campo as repetiriam:
`Formulario.tsx` (`Campo` — o rótulo **envolve** o campo, senão o leitor de tela não diz qual é —,
`Grupo`, `Escolhas`, `FaixaDeErro`), `VistasDoPosto` (cabeçalho com abas `role="tab"`),
`FotoProtegida` (a foto pela porta única, nunca por `<img src>` cru, que chegaria sem token) e
`SeletorDeLugar` (local e serviço, só as folhas do plano). Constantes de domínio moram em
`vocabulario.ts` e estilos em `estilos.ts`: arquivo de componente só exporta componente, senão o
fast refresh do Vite deixa de funcionar.

Bibliotecas — **só licença permissiva**, pela mesma disciplina do
[THIRD-PARTY-LICENSES.md](../../THIRD-PARTY-LICENSES.md):

| Instrumento | Caminho |
|---|---|
| Gantt | Biblioteca MIT (o campo tem opções reais). As comerciais ficam fora enquanto uma MIT der conta |
| Linha de balanço | **SVG próprio** — não existe biblioteca, e o projeto já faz SVG denso na Prancheta |
| Quadro da semana | Canvas de arrastar próprio |
| Grade de medição | `@tanstack/react-table`, já no projeto |
| Curva S, EVM | `recharts`, já no projeto |
| Série de PPC | **SVG próprio** — dois tipos de ponto precisam se desenhar diferente (a semana reaberta e a encerrada antes do fim), e a cor sai só de token, para o tema escuro não exigir reescrita |
| Mapa da frente | `maplibre-gl`, já no projeto |

O CPM **roda no servidor**: é fonte de verdade para prazo e dinheiro, e recalcular num laptop fraco
daria outro resultado.

## 10. O que este desenho cobra do backend

Levantado contra o código: **todo agregado exigia `obra_id`** e as filas eram duas, sem nada que as
una. Oito dos nove existem; o que falta nasce com a fatia que o consome. B8 e B9 não calculam nada:
montam as faixas pelas mesmas funções da fila do dia (`faixas_da_qualidade`,
`faixas_da_seguranca`), e há teste cobrando que as duas leituras dão o mesmo.

| # | O que | Para quê | Onde |
|---|---|---|---|
| B1 | Agregado **multi-obra** (`GET carteira/`) | §6 e o diretor | `services.carteira` |
| B2 | **Fila unificada** da obra juntando qualidade, SSMA, medição a atestar, restrição a vencer e semana a encerrar | §4.5, §5.1 | `services.fila_do_dia`, em `GET hoje/` |
| B3 | **Fila de medição** — os documentos parados no caminho do dinheiro, com o que é preciso para decidir | §5.4 | `services.fila_da_medicao` + `services.carteira_de_contratos`, em `GET medicao/` |
| B4 | **Busca única** (`GET busca/?q=`) sobre atividade, local, contrato, medição, ficha, NC e ocorrência | §4.4 | `services.busca_unica` |
| B5 | **Minhas frentes** — o que está atribuído a quem pede, na semana corrente | §7 | `services.minhas_frentes`, em `GET minhas-frentes/` |
| B6 | **Pulso da obra** — avanço × base, PPC, conformidade e segurança num só retorno | §5.1 | `services.pulso_da_obra`, em `GET hoje/` |
| B7 | Agregados de **obra** (não de cronograma) para ritmo e curva S | §5.1, §5.3 | ❌ a obra com mais de um cronograma não soma |
| B8 | **Posto da qualidade** — a fila do laço (as faixas de retrabalho da fila do dia) e o painel de conformidade | §5.5 | `services.posto_da_qualidade`, em `GET qualidade/` |
| B9 | **Posto da segurança** — as faixas de prazo legal e segurança, os indicadores e as frentes interditadas | §5.6 | `services.posto_da_seguranca`, em `GET seguranca/` |

### 10.1 As duas regras que as leituras que atravessam seguem

Valem para o B7 quando nascer, e para qualquer agregado novo que cruze assunto ou obra.

**Nenhuma delas calcula nada de novo.** Cada número vem da função que já o produzia
(`avanco_do_cronograma`, `serie_ppc`, `fila_da_qualidade`, `fila_da_ssma`). Uma segunda
implementação da mesma média ponderada é o D138 em escala de carteira: o cockpit diria 62%, o posto
diria 64%, e ninguém saberia qual acreditar. Quando a leitura precisa de um número **por obra** e
chamar a função N vezes seria caro, a agregação é em SQL — e o teste cobra que os dois caminhos
dão o mesmo.

**São `APIView` pura, então a tenancy é explícita.** Todo o resto do módulo é `ModelViewSet` e
herda a RLS do `TenantScopedViewSetMixin`; uma `APIView` não arma nada, e foi exatamente o achado
S1. A carteira cruza obras **de propósito** — sem o `TenantScopedAPIViewMixin` ela seria a
repetição literal daquele defeito.

Trabalho de backend nasce no [../roadmap.md](../roadmap.md), e é lá que os três restantes estão
faseados.

## 11. Faseamento proposto

O frontend **não é uma fatia no fim**, e o campo **não é a última**: o ato de campo nasce junto do
posto que o consome, porque é ele que produz o dado do posto.

| Fatia | Entrega |
|---|---|
| **F.0** | A espinha do escritório: casca obra-first, rail, contexto de obra na rota, inspetor, ⌘K, camada de dados, primitivos novos. **Zero domínio** — sem isto, tudo o mais volta a ser depósito |
| **F.0c** | A casca do campo: autenticação, alvo grande, câmera, a ausência de offline declarada |
| **F.1** | `HOJE` + carteira · **cobra B1, B2, B4, B6** — os quatro entregues junto, porque a fatia não é construível sem eles |
| **F.2** | `SEMANA` (quadro, restrições, encerramento, PPC, causas) + campo: apontar e registrar o que assumi · **cobra B5**. Os outros três atos de campo (responder ficha, abrir NC com foto, DDS e ocorrência) nascem com a F.5, que é a fatia que os consome |
| **F.3** | `PLANO` (grade EAP, Gantt, linha de balanço, calendário, locais, modelos) · **cobra B7** |
| **F.4** | `MEDIÇÃO` (contrato, planilha, apurar, prévia, atesto, aditivo, deduções, retenção) · **cobra B3** |
| **F.5** | `QUALIDADE` e `SEGURANÇA` + campo: ficha, NC com foto, DDS, ocorrência |
| **F.6** | Os seams das fatias futuras, inertes: apropriação e EVM em `PLANO`/`MEDIÇÃO`, riscos e marcos em `PLANO`, pós-obra em `QUALIDADE` |

## 12. Régua de pronto

Um posto está pronto quando:

1. **Tem fila de decisão** — não uma contagem, mas o que espera, há quanto tempo, e o botão que decide;
2. **O loop fecha na tela** — o verbo que conclui está onde o trabalho está, não noutra página;
3. **Nenhum número é fabricado** — agregado real do backend, ou *"sem apuração"* dizendo o que falta;
4. **A integração aparece** — o que conversa no backend é clicável na tela, atravessando módulo;
5. **A trava vem do backend** — a tela lê `pode_x` / `x_porque`, nunca reimplementa a condição;
6. **O texto é de quem opera** — sem número de fatia, sem referência a documento interno, sem o
   software se defendendo;
7. **Estado vazio que pede ação traz o botão** que leva até ela;
8. **O objeto atravessa** — selecionar aqui mantém selecionado no posto vizinho;
9. **Campo, quando o posto produz dado de campo**, entregue junto e não depois.

## 13. Limites declarados

- **Offline não existe** enquanto o PWA for fase de plataforma. O campo declara a dependência de rede
  em vez de fingir fila local — perder um apontamento silenciosamente é pior que recusá-lo.
- **A carteira é leitura**, não um posto de trabalho: dali se entra na obra, não se decide sobre
  várias de uma vez.
- **O rail não cresce por fatia.** Capacidade nova entra num posto existente; cadência nova — e só
  ela — justificaria um sétimo.
- **WhatsApp e web responsiva** entram dentro das fatias que produzem dado de campo; não são posto.


## Mudança de desenho — o posto Controle (decisão do dono, 10/10/2026)

O **Hoje** e a **Semana** deixam de ser postos: viram abas do posto **Controle**
(`/app/pdca/o/:obraId/controle?aba=hoje|semana|avanco|custo|materiais`). `hoje` e `semana` na URL
redirecionam; `?vista=avanco|custo` do Plano também. O Plano fica com Cronograma, Suprimentos, Ritmo,
Locais e Expediente. O diálogo "Trazer do orçamento" traz as etapas do cronograma do Orçamento, e uma
faixa no topo do Plano avisa quando esse cronograma mudou. O formulário de contrato escolhe o lado
(empreiteiro/contratante) e a fórmula de reajuste.
