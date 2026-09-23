# modulopdca — a tela: postos de trabalho, não páginas

> **Natureza: planta.** O desenho do frontend do PDCA — como a pessoa entra, onde ela trabalha e por
> que a navegação tem a forma que tem. O domínio está em [modulopdca.md](modulopdca.md); a régua de
> módulo e o design system em [../frontend.md](../frontend.md); as regras obrigatórias de código em
> [../frontend-convencoes.md](../frontend-convencoes.md); a identidade em
> [../identidade-visual.md](../identidade-visual.md). Status e faseamento vivem no
> [../roadmap.md](../roadmap.md).

## 1. O problema que este desenho resolve

O backend do PDCA tem **45 models, 24 recursos REST, ~75 verbos e 40 permissões**. Transformado em
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
você cai** ao abrir a obra e **qual vista o posto abre primeiro** — não o que existe. Quem tem a
permissão vê o posto; quem não tem vê o cadeado com o motivo, pela régua omitir × trancar
([frontend-convencoes.md](../frontend-convencoes.md)).

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
  material gera demanda no SCM pelo verbo que já existe — e o vínculo fica visível.
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

A hierarquia de locais e a biblioteca de planos modelo moram **aqui dentro**, como painéis do posto
(§8), não como itens de menu.

### 5.4 MEDIÇÃO — o dinheiro

**Cadência:** mensal, fecha o mês. **Pergunta:** *quanto se deve, por que, e quem autoriza?*

É o posto de maior consequência: o número vai para o cliente e para o pagamento do empreiteiro.

- **Contratos da obra** com saldo, retenção acumulada e aditivos — a leitura de cima.
- **Planilha contratual** — a grade de itens, e ela **fecha** quando o contrato não permite mais
  editar. A trava vem do backend (`planilha_editavel`, `planilha_fechada_porque`) e a tela **lê a
  resposta**, nunca reimplementa a condição ([convenções §11](../frontend-convencoes.md)).
- **Apurar** — a medição nasce do avanço apontado, não da digitação. A proposta vem pronta do
  servidor e a grade mostra a **memória de cálculo** de cada linha: de onde veio o número.
- **Prévia** — somente leitura por desenho, e a tela **diz isso**: número é texto, não `input`
  desabilitado ([convenções §10](../frontend-convencoes.md)).
- **Escada de atesto** — submeter, atestar, cancelar; cada degrau com a sua permissão. Cancelar
  medição aprovada cancela o título no ERP, e o aviso sai do mesmo lugar da trava.
- **Aditivo** e **deduções** como painéis do posto, porque só existem em função do contrato.

### 5.5 QUALIDADE — o laço que fecha

**Cadência:** contínua, disparada por evento. **Pergunta:** *o que reprovou, quem está tratando, e
acabou mesmo?*

- **Fila do laço aberto** — NC sem plano (ninguém pegou), ação vencida (pegou e não fez), NC
  esperando eficácia (fez e ninguém conferiu), ficha parada no meio. O backend já devolve estas quatro.
- **Painel de conformidade** — o que mais reprova, cumulativo, cada linha partida em *em tratamento*,
  *sem NC aberta* e *já resolvida*.
- **A NC no lugar** — quando tem pino da Prancheta ou local, a tela mostra **onde**, não só o texto.
- **Plano de ação 5W2H** e **verificação de eficácia** no inspetor da NC, porque são passos do mesmo
  laço e não assuntos separados. Só a eficácia fecha a NC — a tela nunca oferece outro caminho.
- **Biblioteca de modelos de ficha** como painel do posto (§8).

### 5.6 SEGURANÇA — o prazo legal e o fato que ninguém queria

**Cadência:** diária (DDS, antes do turno) e por evento (ocorrência). **Pergunta:** *o que fazemos
para ninguém se machucar, e o que fazemos quando alguém se machuca?*

Posto separado da qualidade **de propósito**, e a razão não é organizacional: uma ocorrência tem
**prazo legal** (a CAT é devida no 1º dia útil, imediata na morte), tem **PII clínica** atrás de
permissão própria, e não pode entrar numa fila atrás de um defeito de pintura.

- **Fila da SSMA** com a CAT no topo e o prazo em contagem regressiva.
- **DDS** — a roda antes do turno: tema, lista de presença, encerramento que escreve no Diário.
- **Ocorrência** — do quase-acidente ao óbito. **Registrar é de baixo atrito e sem teto**; classificar
  é verbo à parte, porque quem é medido não classifica a própria medida.
- **Bloco clínico** (lesão, CID, atestado) sob `pdca.ocorrencia.dado_medico`, com porta de mídia
  própria — a foto da cena e o atestado não saem pelo mesmo gate.
- **EPI vencido** lido do SIL sob `sil.epi.view`; sem o módulo contratado, a indisponibilidade é
  **declarada**, não escondida.

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
cartão como mais um trecho da página, e quem não enxerga não sabe que o resto ficou inerte. Junto deles nasceu o `SemPermissaoAviso` — a faixa que diz **o que a leitura deixou de
fora e a quem pedir**, e que é o par obrigatório de todo agregado com recorte por bloco (§10.1).

**Percentual passa pelo `formato.ts` do módulo.** O avanço atravessa como `float` e o PPC e a
conformidade como string (é assim que o DRF serializa `Decimal`, e é assim que centavo não vira
dízima): renderizados crus, a mesma linha da carteira mostrava `77,6%` ao lado de `21.7%`. Régua da
identidade §6 — colunas são réguas, e régua com duas marcações não mede nada.

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
una. Cinco dos sete já existem; os dois que faltam nascem com a fatia que os consome.

| # | O que | Para quê | Onde |
|---|---|---|---|
| B1 | Agregado **multi-obra** (`GET carteira/`) | §6 e o diretor | `services.carteira` |
| B2 | **Fila unificada** da obra juntando qualidade, SSMA, medição a atestar, restrição a vencer e semana a encerrar | §4.5, §5.1 | `services.fila_do_dia`, em `GET hoje/` |
| B3 | **Fila de medição** — as que esperam apuração e atesto, com o que é preciso para decidir | §5.4 | ❌ nasce com a F.4 |
| B4 | **Busca única** (`GET busca/?q=`) sobre atividade, local, contrato, medição, ficha, NC e ocorrência | §4.4 | `services.busca_unica` |
| B5 | **Minhas frentes** — o que está atribuído a quem pede, na semana corrente | §7 | `services.minhas_frentes`, em `GET minhas-frentes/` |
| B6 | **Pulso da obra** — avanço × base, PPC, conformidade e segurança num só retorno | §5.1 | `services.pulso_da_obra`, em `GET hoje/` |
| B7 | Agregados de **obra** (não de cronograma) para ritmo e curva S | §5.1, §5.3 | ❌ a obra com mais de um cronograma não soma |

### 10.1 As três regras que as leituras que atravessam seguem

Valem para B3, B5 e B7 quando nascerem, e para qualquer agregado novo que cruze assunto ou obra.

**Nenhuma delas calcula nada de novo.** Cada número vem da função que já o produzia
(`avanco_do_cronograma`, `serie_ppc`, `fila_da_qualidade`, `fila_da_ssma`). Uma segunda
implementação da mesma média ponderada é o D138 em escala de carteira: o cockpit diria 62%, o posto
diria 64%, e ninguém saberia qual acreditar. Quando a leitura precisa de um número **por obra** e
chamar a função N vezes seria caro, a agregação é em SQL — e o teste cobra que os dois caminhos
dão o mesmo.

**A permissão é por bloco, e a leitura nunca devolve 403 inteira.** Uma leitura que junta cinco
assuntos não tem um dono: exigir `pdca.nc.view` para abrir a carteira recusaria a página ao técnico
de segurança, e exigir o menor denominador não recusaria nada. As portas declaram só
`RequireModule`; o recorte acontece no serviço, por uma função `pode(codigo) -> bool` que o
chamador monta das claims. O bloco que a pessoa não pode ver vem **nulo**, e a permissão que falta
vem nomeada em `sem_permissao` — é a régua omitir × trancar aplicada a um agregado, e a alternativa
(omitir em silêncio) faria a fila parecer vazia, que é a pior das três saídas porque não parece
falha.

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
8. **Omitir × trancar** aplicado: cadeado com motivo onde a pessoa pode destravar;
9. **O objeto atravessa** — selecionar aqui mantém selecionado no posto vizinho;
10. **Campo, quando o posto produz dado de campo**, entregue junto e não depois.

## 13. Limites declarados

- **Offline não existe** enquanto o PWA for fase de plataforma. O campo declara a dependência de rede
  em vez de fingir fila local — perder um apontamento silenciosamente é pior que recusá-lo.
- **A carteira é leitura**, não um posto de trabalho: dali se entra na obra, não se decide sobre
  várias de uma vez.
- **O rail não cresce por fatia.** Capacidade nova entra num posto existente; cadência nova — e só
  ela — justificaria um sétimo.
- **WhatsApp e web responsiva** entram dentro das fatias que produzem dado de campo; não são posto.
