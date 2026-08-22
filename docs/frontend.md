# Frontend — Projeto de Interiores

> **Planta** do shell React: visual identity, estrutura de shell, inventário de páginas, hierarquia
> de componentes, roteamento, fluxo de auth e camada de dados. Descreve o sistema **inteiro**
> (pronto e planejado), **sem status** — o status por módulo e o fluxo testável estão na
> [tabela de frontend do roadmap](roadmap.md#estado-dos-módulos--frontend-react-08062026); as
> **convenções de código** (obrigatórias para quem desenvolve) em
> [frontend-convencoes.md](frontend-convencoes.md)
> Stack: React 19 · Vite 7 · TypeScript 5.8 · Tailwind CSS 4 · React Router v7 · Axios ·
> TanStack Query/Table · RHF+zod · Recharts
> Infra: container `react` atrás do Nginx gateway em `:8090`; código em `frontend/src/`.


## 1. Design Language

> **Identidade visual — fonte única:** [identidade-visual.md](identidade-visual.md)
> (Sistema **Malha v1**, "Do terreno à cidade"): marco Quarteirão, cores por estágio do ciclo
> (a cor da edição é a do estágio que ela habita — o âmbar do produto atual é o estágio
> *Construir*), tipografia Archivo/Inter/JetBrains Mono, tema claro/escuro e voz.
> O **shell roda na Malha v1**: tokens de tema em [index.css](../frontend/src/index.css) (§1.2), fontes
> Archivo/Inter/JetBrains (§1.3), sidebar/topbar de marca (§3) e primitivos em
> [components/malha/](../frontend/src/components/malha/). Os **módulos legados** (ERP/RH/clientes…) usam
> **aliases de compatibilidade** (`--color-*`/`--font-*` → tokens Malha) e por isso já acompanham o tema
> sem reescrita — cada um migra para os tokens nativos na sua vez. O alvo visual é
> [identidade-visual-prototipo.html](identidade-visual-prototipo.html) (replicar, não reinterpretar); o
> padrão do **hub por edição** (módulos endereçados no ciclo + decisões + feed de fatos — alvo do
> dashboard F.1) está em [identidade-visual.md §9](identidade-visual.md).

### 1.1 Inspiração e contexto

O SGI atende incorporadoras e construtoras — ambiente de obra, engenharia, drone e IA.
Referências que norteiam as decisões visuais:

| Referência | O que tomar |
|---|---|
| **Procore** | Sidebar com project-switcher, data-density alta, orange accent |
| **Autodesk Construction Cloud** | Navy/slate primário, ícones de linha fina, mapas |
| **DroneDeploy** | Fundo escuro para visualizações, teal para telemetria/IA |
| **BIM 360** | Hierarquia clara: empreendimento → obra → etapa |
| **Linear** (SaaS moderno) | Sidebar collapsível elegante, keyboard-nav, atalhos |

### 1.2 Paleta de cores

**Fonte única: os tokens Malha em [index.css](../frontend/src/index.css)** — valores e semântica em
[identidade-visual.md §5](identidade-visual.md). O produto tem **tema claro e escuro** (custom
properties; `prefers-color-scheme` como default, o toggle do usuário carimba `data-theme` no `<html>` e
vence). Regras que a UI não reinterpreta:

- **Superfícies/tinta:** `--ground` (fundo da área), `--surface`/`--surface-2`/`--inset` (cartões —
  **nunca branco puro**), `--ink`/`--ink-2`/`--ink-3` (texto), `--line`/`--line-2` (bordas).
- **Marca/acento:** `--brand` (Navy Cívico), `--accent` (âmbar — estágio **Construir** da Edição
  Construtora); **um acento por tela** (o que "requer decisão / CTA primário").
- **Semânticos de UI** (nunca reutilizam cor de estágio como significado): `--good`/`--info`/`--danger`/
  `--net`, cada um com par `-soft`/`-ink`. Cores de estágio seguras para texto: `--st-orig/const/neg/oper`.
- **Compatibilidade v01:** `--color-*` continuam existindo como **aliases theme-aware** dos tokens
  Malha — os módulos legados acompanham o tema sem reescrita e migram para os nativos um a um.

### 1.3 Tipografia

**Archivo** (letreiro/display) · **Inter** (produto/corpo) · **JetBrains Mono** (dados/instrumento) —
carregadas em [index.html](../frontend/index.html); substituem Montserrat/Roboto da v01. Stacks em
`--display`/`--sans`/`--mono`.

- **Títulos** (`h1..h6`, `--display` Archivo): peso 700–800, tracking fechado (−0.02em).
- **Corpo** (`--sans` Inter): 400 body · 500 labels · 600 subtítulos.
- **Dados** (`--mono` JetBrains, classe `.num`/`.mono`): **todo** preço/quantidade/código/prazo em
  `tabular-nums`, alinhado à direita — "colunas como réguas" (§6). Componente [Num](../frontend/src/components/malha/Num.tsx).
- Aliases `--font-heading`/`--font-body` apontam para `--display`/`--sans` (compat v01).

### 1.4 Iconografia

- **Lucide React** (já na dep) — ícones de linha fina, 24px padrão
- Ícones de módulo específicos (Lucide):
  - Empreendimentos: `Building2`
  - Obras: `HardHat`
  - Clientes: `Users`
  - Fornecedores: `Truck`
  - ERP/Financeiro: `BarChart3`
  - RH: `UserCog`
  - CRM: `TrendingUp`
  - Drone: `Plane`
  - Diário/IA: `Brain`
  - Calendário: `CalendarDays`
  - Dashboard: `LayoutDashboard`

### 1.5 Princípios de UI

1. **Data-density controlada** — tabelas compactas com `text-sm`, espaçamento generoso apenas nos dashboards
2. **Hierarquia visual clara** — empreendimento > obra > etapa sempre visível no breadcrumb
3. **Entitlement invisível** — módulos não contratados simplesmente não aparecem, sem mensagem de bloqueio na sidebar
4. **Estado sempre legível** — badges coloridos para status de obra/etapa/financeiro, sem ícones ambíguos
5. **IA como feature diferencial** — análise de IA destacada visualmente (cor `blue-500`, ícone `Brain`)

---

## 1.6 A régua de módulo — grandioso e expansível (o SCM como referência)

> **O mandato que abre todo módulo.** A construção do frontend começou com um pedido explícito:
> *"faça um módulo grandioso, compatível com o escopo do projeto e expansível conforme a pasta
> [expansão](expansão/README.md)"*. O **SCM** ([§5.17](#517-scm--suprimentos-hasmodule-scm--✅-construído-s1s4-1º-módulo-malha))
> foi construído a essa régua. **Todo módulo de frontend — novo ou migrado — herda a mesma régua.**
> Não os mesmos KPIs, cards ou nomes (isso é do domínio de cada um), mas a mesma **profundidade,
> facilidade de uso e costura com a expansão**. E um **norte inegociável**: o próprio nome do projeto
> — ***sistema de gestão integrada*** — exige que os módulos que conversam no backend **conversem
> também na tela**; o fim do projeto é essa sensação de sistema único, não de N produtos ao lado.

### Capacidade × módulo — e por que a diferença é de tela

*(decisão do dono, 08/08/2026, tomada sobre a Prancheta e válida para todas as que vierem.)*

Nem tudo que se vende é um lugar. **Algumas compras são capacidades que atravessam o sistema**, e a
[Prancheta](modulos/moduloprancheta.md) é a primeira: quem a contrata não está comprando "um módulo de
projetos", está comprando **poder ver os próprios arquivos dentro do software**. Então quando o
Orçamento, o SIL ou o diário precisam mostrar um DWG, eles **puxam aquela visualização ali mesmo** —
não mandam o usuário para outro módulo, e não escondem a função.

A regra de tela que sai daí é a do farol (§3.2), aplicada a **função** e não só a menu:

- a capacidade aparece **onde o trabalho está**, embutida na tela em que a pessoa já estava;
- quem **não** a contratou vê o **cadeado com o motivo naquela mesma tela**, nunca um espaço vazio nem
  um redirecionamento para uma página de vendas de outro módulo;
- o que se vende é declarado **uma vez** e honrado em todo lugar — o cliente que comprou "abrir DWG"
  não descobre num segundo módulo que ali não vale.

Sinal de que você está tratando uma capacidade como silo: a mesma função aparece duas vezes com dois
gates, ou o usuário precisa **sair da tarefa** para usar o que já comprou.

### Não é CRUD — é o trabalho do usuário resolvido

Um módulo não é "listas + formulários". É um **workspace** que resolve o *job diário* de quem vive
naquele módulo, do começo ao fim do fluxo, e já **aponta para onde ele gradua na rede**. A tabela é
o piso, nunca o teto. Se a entrega é só um CRUD, ela não está pronta.

### As qualidades transferíveis (a régua é o espírito, não a forma)

1. **Cockpit de entrada** — o estado do módulo num relance, uma fila **"requer sua decisão"** (o que
   exige ação *agora*) e um feed de **fatos reais** (não posts). *(SCM: flow rail do fluxo, KPIs
   agregados, cotações a adjudicar, atividade de recebimentos/adjudicações/avaliações.)*
2. **O loop do domínio ponta a ponta** — o fluxo central inteiro com os **verbos de decisão**, não só
   o cadastro. *(SCM: demanda → cotação → pedido → recebimento → avaliação, com adjudicar / comprar
   direto / registrar recebimento / avaliar.)*
3. **Ferramenta de decisão onde há escolha** — comparar, priorizar, recomendar quando o domínio pede
   julgamento. *(SCM: mapa comparativo de propostas, menor por item, recomendação.)*
4. **Dados honestos** — agregados **reais** (computados no backend quando exigem *join*/soma);
   placeholder rotulado **"em breve"** onde ainda não há fonte; **nunca número fabricado**. *(SCM:
   economia/prazo médio vindos do `dashboard/`; assistente de IA inerte e rotulado.)*
5. **Arquitetado para graduar** — o módulo privado é **enxuto e direto** (resolve o job do tenant),
   mas **nasce com os *seams* de rede no modelo** (`visibilidade`/`ref_externa`/`origem_tenant` no
   SCM) e o loop desenhado para que o marketplace/portal seja só a **publicação** dele depois
   ([mapa §regra de ouro](expansão/03-mapa-de-modulos.md)). A vitrine/feed da rede é **da fase de
   expansão**, não uma aba dentro do módulo. *(SCM interno: UI enxuta, sem chips de rede; seams
   inertes no backend.)*
6. **Integração visível — um sistema, não silos** — quando dois módulos conversam no backend (FK,
   *seam*, evento), essa conversa **aparece para o usuário** no frontend, não fica só no banco:
   **referências clicáveis que atravessam o módulo** (do pedido → à ContaPagar do ERP → à NF-e; do
   centro de custo → à obra; do cliente → ao contrato → às cobranças), **contexto do outro módulo
   embutido** onde ajuda, o **breadcrumb do domínio** (empreendimento › obra › etapa) e **agregados
   que cruzam módulos** (ex.: DRE por obra puxa SCM + ERP + medições). É o que realiza o nome do
   projeto — *sistema de gestão **integrada***: o usuário navega **um** sistema, e cada módulo é uma
   porta para o resto, não um silo. *(SCM: o recebimento exibe a NF-e conciliada e o pedido mostra o
   centro de custo → obra e a origem — demanda/oferta; o vínculo clicável com a ContaPagar do ERP é o
   próximo passo natural dessa integração.)*
7. **Facilidade de uso Malha** — tema claro/escuro, **um acento por tela**, dado em **mono tabular**,
   **master-detail in-place** (sem trocar de rota para ver o detalhe), estados de **vazio/carregando**,
   ações **gateadas por permissão**, navegação por abas/atalhos. Ver [identidade-visual.md](identidade-visual.md).

### Como dar escopo a um módulo (as perguntas, não as telas)

Antes de desenhar qualquer tela, responder — é a versão operacional das
[seis perguntas de plataforma](expansão/README.md):

- Qual é a **decisão diária** de quem vive neste módulo? → vira o *"requer sua decisão"* do cockpit.
- Qual é o **loop** do domínio (o ciclo que se repete)? → vira o fluxo ponta a ponta com verbos.
- Onde há **julgamento/escolha**? → vira a ferramenta de comparação/priorização/recomendação.
- Que **fatos** o módulo produz? → viram o feed + os agregados do cockpit + (depois) o feed público da rede.
- Com que **outros módulos** este conversa (FK/*seam*/evento)? → essas conversas viram **referências
  clicáveis e contexto embutido** na tela (o pedido leva à conta a pagar; a obra puxa suprimentos,
  medições e financeiro) — o usuário nunca "sai do sistema" para ver o lado que se integra.
- Onde o módulo **gradua** para rede/portal ([04](expansão/04-rede-e-marketplaces.md) ·
  [05](expansão/05-portais-e-apps.md) · [09](expansão/09-verticais-por-participante.md))? → define os
  *seams* no modelo **desde já**; a vitrine/portal público é construído **depois**, na fase de
  expansão (o módulo privado fica enxuto).

### O job diário e a graduação de rede por módulo (direção, sem prescrever)

Fonte: [mapa de módulos](expansão/03-mapa-de-modulos.md) + [verticais](expansão/09-verticais-por-participante.md).
Não são telas a copiar — é **o que cada cockpit precisa resolver** e **onde ele gradua**:

| Módulo | Job diário que o cockpit/loop deve resolver | Gradua para (expansão) |
|---|---|---|
| **SCM** ✅ | necessidade → cotar → comparar → comprar → receber → avaliar | Marketplace de cotações · Edição Loja |
| **ERP/Financeiro** | o que vence/entra hoje, o que decidir (baixar, cobrar, emitir NF), saúde por obra (DRE) | Fintech: antecipação, conciliação, repasse ([07](expansão/07-monetizacao-da-expansao.md)) |
| **CRM** | a próxima ação do funil, leads que esfriam, forecast de VGV | Espelho de vendas → distribuição à Edição Imobiliária |
| **RH** | quem precisa de ação (ASO, contrato, ponto), folha do mês, PII protegida | Rede de profissionais · medições de empreiteiro |
| **Obras / Diário / Drone** | o dia da obra num relance, pendências, avanço × previsto, ortofoto | Página pública da obra + feed de marcos ([10](expansão/10-rede-social-do-setor.md)) |
| **Clientes** | a carteira e o que cada cliente precisa (2ª via, andamento) | **Portal do cliente** (H1) |
| **SIL — estoque** (`modulosil`) | saldo por local, mínimos, o que repor | Estoque mínimo → **RFQ automática** no SCM (E6) |
| **DMS** (`modulodms`) | o que vence/falta assinar, versões, documento por obra | Documento espelhado + assinatura por doc (receita medida) |
| **PDCA** (`modulopdca`) | cronograma vs. real, não-conformidades a tratar | IA de previsão de atraso / detecção em foto do diário |
| **Prancheta** (`moduloprancheta`) | o projeto da obra aberto em campo; revisão vigente × anterior | Marcação BCF devolvida ao projetista · modelo 4D/5D |
| **MAPS / Terrenos** (`modulomaps`) | terrenos por status, viabilidade, camadas GIS | Marketplace de terrenos · banco de terrenos |
| **Assistência / Condomínio** (pós-obra) | chamados por SLA, técnico em campo / taxas e reservas | Portal do proprietário/morador · **novo mercado** (H3) |

### Definition of done à régua SCM (checklist)

Um frontend de módulo só está "pronto" quando: **(1)** tem cockpit com fila de decisão + fatos reais;
**(2)** cobre o loop do domínio com os verbos, não só cadastro; **(3)** oferece a ferramenta de decisão
onde o domínio tem escolha; **(4)** não exibe **nenhum** dado fabricado (agregado real ou "em breve"
rotulado); **(5)** nasce com os *seams* de expansão no modelo e o loop pronto para graduar (a rede/portal é
publicação **posterior**, não aba do módulo); **(6)** **torna visíveis as integrações** com outros
módulos (FK/*seams*/eventos → referências clicáveis e contexto embutido; o usuário sente um sistema, não
silos); **(7)** segue a Malha (tema, acento único, mono, master-detail, vazio/carregando, permissões);
**(8)** typecheck limpo e um seed de demonstração que enche as telas.

---

## 2. Biblioteca de Componentes

### A camada compartilhada — `components/malha/`

Os primitivos da Malha vivem em [components/malha/](../frontend/src/components/malha/) e são a
**fonte única** dos módulos novos. Nenhum deles usa cor fixa: tudo sai dos tokens de
[index.css](../frontend/src/index.css), e por isso acompanham tema claro/escuro sem reescrita.

| Primitivo | Papel |
|---|---|
| `Card` | Superfície `--surface` (nunca branco puro), borda `--line`, raio `--r-md` |
| `Modal` | Diálogo: fecha no `Esc` e no clique fora. `largura` dimensiona; **`alto`** faz o cartão ocupar a janela e entregar a sobra ao conteúdo (ver §2.1) |
| `Pill` | Estado **nomeado** (§8) nos semânticos de UI + `accent`; cor sozinha nunca comunica |
| `Num` | Dado de instrumento: mono tabular, alinhado à direita — "colunas como réguas" (§6) |
| `KpiTile` | Mosaico de KPI: valor real **ou** o selo `EmBreve`; exige a base do número |
| `SectionHead` | Cabeçalho de seção, opcionalmente com a cor de estágio (`--st-*`) |
| `Spinner`/`Loading`/`Empty`/`EmBreve` | Estados; `Loading` sempre diz **o quê** carrega |
| `BotaoExportar`/`WizardImportacao`/`WizardArquivos` | As três portas de import/export de **todo** módulo ([impexp §10](modulos/funcoesimpexp.md)). Somem sozinhos quando `/api/impexp/recursos/` não lista o recurso para esta pessoa — nenhum recebe prop de permissão |

> **Dívida conhecida:** SCM e SIL nasceram antes deste diretório e têm cópias locais do kit
> (`modules/scm/pages/SuprimentosPage.tsx` e `modules/sil/ui.tsx` definem `Card`/`Pill`/`Btn`/
> `Modal` próprios). Cada um migra para `components/malha/` na sua vez. O ERP tem um terceiro kit,
> específico de finanças, em `modules/erp/components/shared/` (`FilterBar`, `FinanceDataTable`,
> `MoneyInput`, `Sheet`) — esse é legítimo, é de domínio, não de fundação.

**shadcn/ui não foi adotado** — a versão original desta seção planejava `src/components/ui/` gerado
por `npx shadcn add`, o que nunca aconteceu. Os primitivos são escritos no projeto (acima) e os
componentes herdados da v01 seguem em `components/common/` com CSS próprio, migrando por módulo.

### 2.1 Quem é o dono da roda — as três regras de rolagem

Telas de trabalho do sistema empilham áreas roláveis: página, lista, painel flutuante. Quando o
usuário gira a roda, **uma** dessas áreas tem de responder, e qual é ela não pode depender de acaso
de posicionamento. As três regras abaixo são o que garante isso, e cada uma existe porque a ausência
dela produziu um defeito relatado.

**1. Área rolável aninhada leva `overscroll-behavior: contain`.** Sem ele a roda *encadeia*: ao
chegar ao fim da lista interna, o resto do gesto passa ao container de trás e a tela salta. Com
`contain`, o ponteiro decide o dono — dentro rola o de dentro, fora rola o de fora.

**2. Painel flutuante (dropdown, popover, seletor) abre em `createPortal` no `body`, com coordenada
`fixed` medida do gatilho — nunca `position: absolute` dentro do fluxo.** Um painel absoluto dentro
de um ancestral com `overflow` custa três coisas de uma vez: é **cortado** na borda dele; **entra no
`scrollHeight`** do container, inventando uma barra de rolagem que o conteúdo não pediu; e obriga a
um véu de tela cheia para fechar no clique fora. O preço do portal é reposicionar ao rolar
(`window.addEventListener('scroll', …, true)` — captura, porque a rolagem que move o gatilho é a do
container interno e não borbulha até a `window`).

**3. Nada de véu `position: fixed; inset: 0` para fechar no clique fora — use `mousedown` no
documento.** O véu é o alvo do ponteiro em toda a tela enquanto o painel está aberto e, sendo fixo,
o encadeamento de rolagem dele vai para a **viewport**, não para o container que está atrás no DOM:
a roda deixa de funcionar em todo lugar. Fechar o painel na roda "resolve" e é pior — o usuário que
quis rolar o fundo perde a escolha que tinha aberto.

Referência das três: [`WizardArquivos.tsx`](../frontend/src/components/malha/impexp/WizardArquivos.tsx)
e [`prancheta/pages/Disciplinas.tsx`](../frontend/src/modules/prancheta/pages/Disciplinas.tsx).

**Um caso que a roda sozinha não resolve: a tabela larga.** Roda de mouse não rola na horizontal, e
uma lista de conferência com onze colunas tem para onde ir só para o lado. Quando o container
**não** tem rolagem vertical alguma e tem conteúdo à direita, a roda vertical é traduzida em
horizontal; havendo rolagem vertical, ela continua sendo da vertical. `Shift + roda` já é horizontal
pelo navegador e passa direto. O listener é nativo e não-passivo — em React o `onWheel` é passivo e
o `preventDefault()` não pega (mesma armadilha de [`Vista2D.tsx`](../frontend/src/modules/prancheta/visualizador/Vista2D.tsx)).

### 2.2 Diálogo cujo miolo é uma lista — o modo `alto` do `Modal`

No modo normal o cartão cresce com o conteúdo e quem rola é o fundo. Isso é certo para um aviso e
errado para um diálogo de trabalho: cabeçalho, contadores e filtros empurram a lista para fora da
tela e sobra **uma fileira** para aquilo que a pessoa veio ler.

Com `alto`, o cartão vira coluna flex de altura fixa: cabeçalho e rodapé ficam presos, o miolo
recebe `flex: 1` e **quem rola é a lista**. O filho tem de colaborar — ser coluna flex e usar
`flex: 1` + `minHeight: 0` na parte que rola, nunca `height: 100%` (altura percentual dentro de flex
depende de o pai ter altura resolvida e quebra em silêncio quando alguém insere um wrapper). Por
exigir essa colaboração, é opção e não padrão.

**Altura fixa em pixel na lista é sempre a altura errada:** no monitor grande desperdiça meia tela,
na tela baixa espreme a lista contra um cabeçalho que não encolhe.

### 2.3 Célula de tabela que precisa caber

`max-width` num `<td>` de tabela com `table-layout: auto` é **conselho, não regra** — o algoritmo
dimensiona a coluna pelo conteúdo e ignora o limite; com `white-space: nowrap` o `overflow: hidden`
nunca chega a ter o que cortar. O corte tem de ir num **filho de bloco** dentro da célula, com o
valor inteiro no `title` da célula.

Sem isso, uma coluna de identificador longo (um SHA-256 são 64 caracteres) abre sozinha centenas de
pixels e empurra as colunas úteis para fora da tela, espremendo justamente o nome do arquivo — que é
o que a pessoa lê para decidir.

### 2.4 Lista longa: marca em vez de rótulo, e a legenda que a explica

Numa lista de catálogo — milhares de linhas, descrição que passa de 130 caracteres — **texto de
estado no meio da linha custa duas coisas**: come a largura da descrição, que é o que a pessoa lê
para decidir; e, por só existir em algumas linhas, faz as colunas seguintes mudarem de lugar de
linha para linha, o que destrói a leitura em varredura vertical.

Uma pílula escrita `já no catálogo` e um botão de texto `ver analítica` eram os dois casos. Viraram
marcas de largura fixa, com o mesmo par sempre presente:

- **estado binário → bolinha cheia × vazada.** O estado negativo é **desenhado**, não omitido: é
  isso que dá largura constante à coluna. Omitir o negativo economiza um elemento e devolve o
  problema do alinhamento.
- **abrir/fechar detalhe → seta**, apontando para baixo quando aberta — a mesma convenção da árvore
  da planilha. Quando a linha não tem detalhe, entra um espaçador da largura da seta.
- **toda marca precisa de legenda.** Marca sem legenda é charada, e o usuário novo paga por ela toda
  vez. A legenda vive ao pé da lista, junto do contador.

**Descrição truncada leva `title` com o valor inteiro** — mesma regra da célula de tabela (§2.3),
mesma razão: escolher entre "…VERGALHÃO DE 5,0 MM" e "…DE 12,5 MM" não pode depender de adivinhar o
final. Vale para a linha da lista, para a coluna da grade e para o item recolhido de um painel.

**Cesta de seleção fica ao lado, não embaixo.** Numa seleção que atravessa páginas e buscas, o
rodapé com "5 item(ns) marcado(s)" é um número sem rosto: não diz *o que* foi marcado e não deixa
tirar um item errado sem reencontrá-lo na lista. O painel lateral resolve os dois — e é lateral
porque um painel abaixo sai de vista assim que a lista rola, e cesta que some não serve de
conferência. Ele mostra **só o identificador e o nome**: o resto já está na linha da lista.

**Painel lateral em linha flex precisa ser travado nas duas dimensões.** `flex: 0 0 <largura>` não
basta: item flex nasce com `min-width: auto` e conteúdo largo empurra a caixa, comendo a área da
lista. E se a **linha** não tiver altura própria, ela assume a do filho mais alto — cada item
marcado estica o painel, que estica a linha, que empurra a lista para fora da tela. O par é
`minWidth: 0` + `maxWidth` explícitos na lateral, e altura resolvida na linha (relativa à viewport,
nunca em pixel — §2.2), com cada coluna rolando por dentro.

### Componentes de domínio

```
src/components/
├── malha/                       ← primitivos da identidade (tabela acima)
├── brand/                       ← Quarteirao · BairroRecorte · EdicaoChip
├── layout/
│   ├── AppShell.tsx             ← AppSidebar + AppTopbar + <Outlet />
│   ├── AppSidebar.tsx           ← farol da edição, colapsível
│   └── AppTopbar.tsx            ← glass: breadcrumb + chip de estágio + tema
├── common/                      ← herdados da v01 (Button/Input/Modal/Table + CSS)
├── obra/                        ← blueprint · gantt · mapa · timeline · KPIs
├── clientes/ · notifications/
└── ModuleRoute · PrivateRoute · AccessNotice · ThemeToggle
```

---

## 3. AppShell — Estrutura Global

### 3.1 Layout

```
┌─────────────────────────────────────────────────────────────────┐
│                         TOPBAR (h-14)                           │
│  [≡ SGI]  Breadcrumb: Empreendimentos / Residencial Alfa / Obras│
│                                    [🔔] [Tenant: Alfa Ltda ▼]  │
├────────────┬────────────────────────────────────────────────────┤
│  SIDEBAR   │                                                    │
│  (w-56 /   │              CONTENT AREA                         │
│   w-14     │          <Outlet /> da rota ativa                 │
│  colapsada)│                                                    │
│            │                                                    │
│  Base:     │                                                    │
│  🏠 Home   │                                                    │
│  🏗 Empreen│                                                    │
│  🦺 Obras  │                                                    │
│  👥 Clientes                                                   │
│  🚛 Fornec.│                                                    │
│  ─────────│                                                    │
│  Módulos:  │                                                    │
│  💰 ERP    │                                                    │
│  👤 RH     │                                                    │
│  📈 CRM    │                                                    │
│  ─────────│                                                    │
│  Extras:   │                                                    │
│  ✈ Drone   │                                                    │
│  🧠 IA/Di. │                                                    │
│  📅 Agenda │                                                    │
│            │                                                    │
└────────────┴────────────────────────────────────────────────────┘
```

### 3.2 Sidebar — sidebar de marca (Malha)

[AppSidebar](../frontend/src/components/layout/AppSidebar.tsx) **acompanha o tema** (fundo `--surface`,
texto `--ink-*`, borda `--line`). De cima para baixo (identidade §9):

- **Lockup:** marco [Quarteirão](../frontend/src/components/brand/Quarteirao.tsx) (praça em `--ink`) +
  "SGI Plataforma / Do terreno à cidade" + **régua do ciclo** (filete com as 4 cores dos estágios).
- **Navegação por seções endereçadas** (Operação / Gestão / Administração / Ecossistema); item ativo =
  **quarteirão aceso** (ponto âmbar + fundo `--accent-soft`).
- **Farol da edição — mostra SEMPRE todos os itens, nunca esconde.** O que o usuário não pode acessar
  aparece **travado** (cadeado, sem interação), com o motivo no `title`: `Módulo não contratado`
  (item pago sem `hasModule`), `Somente administradores` (`adminOnly` sem `is_tenant_admin`) ou
  `Em breve`/`Em construção` (`implemented: false`). É `interativo = implemented && (sem module ||
  hasModule) && (não adminOnly || isTenantAdmin)`; falso → `<span>` travado, verdadeiro → `NavLink`.
  **O farol é por edição/tipo, não pela plataforma inteira:** cada edição (Construtora, Imobiliária,
  Loja, …) define **o seu próprio conjunto de itens** — a Construtora não lista os módulos exclusivos
  da Loja ou da Imobiliária, e vice-versa (§4/§9 da identidade: *cada edição tem o seu hub*). O farol
  revela o alcance **daquela** vertical, sem poluir com módulos de outra.
- **Rodapé:** recorte do Bairro ([BairroRecorte](../frontend/src/components/brand/BairroRecorte.tsx)) com o
  quarteirão-empresa (dia masterplan / noite janelas acesas, via `--city-*`) + avatar e usuário.
- **Colapsável** (`localStorage` `sgi_sidebar_collapsed`): expandida 236px / recolhida 60px (só ícones).
- **O que NÃO entra na sidebar: as lentes transversais.** Calendário, Mapas e **Prancheta** não são
  *lugares* do ciclo — são leituras sobre tudo o que já existe (a agenda de todos os módulos; o
  território de obra, fornecedor e almoxarifado; o projeto de qualquer obra aberto por cima da tela
  em que você está). Os três vivem como ícone na topbar (§3.3). A régua: se o item responde "onde eu
  estou no ciclo", é sidebar; se responde "o que está acontecendo agora, visto de outro eixo", é
  topbar. **As três estão na topbar** — a Prancheta entrou com a PRA.2
  ([modulos/moduloprancheta.md §9.1](modulos/moduloprancheta.md)).

### 3.3 Topbar — glass (Malha)

[AppTopbar](../frontend/src/components/layout/AppTopbar.tsx): faixa **glass** (`--glass` + `backdrop-filter`),
borda `--line`.

- **Breadcrumb** automático por rota (mapa de segmentos → rótulos; ignora ids numéricos).
- **Chip de estágio** ([EdicaoChip](../frontend/src/components/brand/EdicaoChip.tsx)) "Edição Construtora ·
  Construir" — toda tela declara seu endereço no ciclo.
- **Lentes transversais** (26/07/2026): ícone de **Mapas** (`/app/maps`) e de **Calendário**
  (`/app/calendario`), na mesma caixa de 34px do resto da fileira, ativo aceso em `--accent-soft`.
  Ficam ao lado do sino porque pertencem à mesma família — o que se consulta sem sair de onde se
  está. Ver a régua em §3.2.
- **[ThemeToggle](../frontend/src/components/ThemeToggle.tsx)** claro/escuro (o gesto de tema é movimento de
  marca §7); sino de notificações; avatar + dropdown (alterar senha, sair).
- **Sem command palette (⌘K)** por ora — volta quando houver busca cross-entidade real (ver **F2** em
  [pendencias.md](pendencias.md)); nenhuma navegação depende dela (a sidebar cobre tudo).

---

## 4. Roteamento

Utiliza `createBrowserRouter` com rotas aninhadas.

```
/                       → LandingPage (pública)
/login                  → LoginPage (pública)
/app                    → AppShell (PrivateRoute — exige token válido)
  /app/dashboard        → DashboardPage
  /app/empreendimentos  → EmpreendimentosListPage
  /app/empreendimentos/:eId
                        → EmpreendimentoDetailPage
  /app/empreendimentos/:eId/obras
                        → ObrasListPage (filtrado por empreendimento)
  /app/empreendimentos/:eId/obras/:obraId
                        → ObraDetailPage
  /app/obras            → ObrasListPage (todas as obras do tenant)
  /app/clientes         → ClientesListPage
  /app/clientes/:id     → ClienteDetailPage
  /app/fornecedores     → FornecedoresListPage
  /app/erp                    → ErpDashboardPage ✅      (hasModule: erp_financeiro — lazy/Suspense, hub D.1.0)
  /app/erp/contas-a-pagar     → ContasAPagarPage ✅      (rota-irmã, D.1.1 07/06/2026 — workspace: lançar/editar/ver/baixa)
  /app/erp/contas-a-receber   → ContasAReceberPage ✅    (idem, espelhado p/ cliente/NF — D.1.1 07/06/2026)
  /app/erp/boletos            → BoletosListPage ✅       (rota-irmã, D.1.2 08/06/2026 — telas dedicadas, somente leitura)
  /app/erp/boletos/:id        → BoletoDetailPage ✅      (gateway + timeline de eventos do webhook Asaas)
  /app/rh               → RHPage               (hasModule: rh)
  /app/rh/funcionarios  → FuncionariosListPage (hasModule: rh)
  /app/crm              → CrmDashboardPage     (hasModule: crm)
  /app/crm/leads        → LeadsPage            (hasModule: crm)
  /app/diario           → DiarioObraPage       (base)
  /app/drone            → DroneWrapperPage     (hasModule: drone)
  /app/calendario       → CalendarioPage       (base)
  /app/admin/papeis     → PersonasPage ✅       (adminOnly — Papéis e Acessos, Fase 9.A)
  /app/admin/usuarios   → UsuariosPage ✅       (adminOnly — Usuários e seus papéis, Fase 9.A)
  *                     → NotFoundPage
```

> **Guard de entitlement:** `<ModuleRoute module="erp_financeiro">` wrapping a rota
> redireciona para `/app/dashboard` com toast "Módulo não disponível no seu plano"
> se `!hasModule(module)`.

> **Área de Administração (Fase 9.A):** [modules/admin/](../frontend/src/modules/admin/) — `PersonasPage`
> (CRUD de papéis/personas com picker de permissões por módulo + clonar) e `UsuariosPage` (atribui
> papéis a usuários). Itens de menu só aparecem para `is_tenant_admin` (`AuthContext.isTenantAdmin`).
> Falam com a IAM pelo cliente `iamAdminClient` (baseURL `/iam`, roteado pelo gateway → IAM). Detalhe
> do modelo em [arquitetura/rbac-abac.md §9.1](arquitetura/rbac-abac.md).

---

## 5. Mapa de Páginas

### 5.1 LandingPage (`/`)

A porta de entrada do produto. A **estrutura e o copy já existem na v01** (`01sistema_gestao_integrada`)
e devem ser portados — não reinventados. Adaptar apenas para Tailwind + shadcn + nova paleta navy.

**Asset a reaproveitar:** `01sistema_gestao_integrada/frontend/src/components/HomeSections/dashboard-mockup.png`
→ copiar para `frontend/public/dashboard-mockup.png`.

#### Estrutura das seções (v01 → v02)

```
┌──────────────────────────────────────────────────────────────────┐
│  HEADER — fixo, bg branco, sombra                                │
│  [SGI Logo]    Funcionalidades  Módulos  Segurança   [Acessar →] │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  HERO — bg branco, duas colunas (desktop)                        │
│                                                                  │
│  TEXTO (esquerda)              │  IMAGEM (direita)               │
│  h1: "O Fim do Improviso       │  <dashboard-mockup.png>         │
│  na Sua Obra."                 │  rounded + sombra               │
│  "Inteligência, Gestão,        │                                 │
│  Controle e Lucro em um        │                                 │
│  só lugar."                    │                                 │
│                                │                                 │
│  p: "Nossa plataforma          │                                 │
│  integra todos os seus         │                                 │
│  processos, do canteiro de     │                                 │
│  obras ao financeiro..."       │                                 │
│                                │                                 │
│  [Solicitar Demonstração]      │                                 │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  MÓDULOS — bg #F0F2F5                                            │
│  h2: "Uma plataforma completa para cada desafio da sua           │
│        construtora"                                              │
│                                                                  │
│  Grid 3 colunas (desktop), 2 (tablet), 1 (mobile)               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │ 🔧 Gestão de │ │ 💰 Gestão    │ │ 📈 CRM de    │            │
│  │    Obras     │ │  Financeira  │ │    Vendas    │            │
│  │ Acompanhe    │ │ Controle     │ │ Gerencie     │            │
│  │ cronograma,  │ │ contas a     │ │ leads e      │            │
│  │ diário e     │ │ pagar,       │ │ clientes do  │            │
│  │ recursos     │ │ receber e    │ │ primeiro     │            │
│  │ em tempo     │ │ fluxo de     │ │ contato ao   │            │
│  │ real.        │ │ caixa.       │ │ contrato.    │            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │ 💬 Diário   │ │ 📂 Gestão de │ │ 🧠 Relatórios│            │
│  │  por        │ │  Documentos  │ │    com IA    │            │
│  │  WhatsApp   │ │              │ │              │            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  SOCIAL PROOF — bg branco                                        │
│  h2: "Construindo Relações de Confiança"                         │
│                                                                  │
│  Depoimento:                                                     │
│  "O sistema transformou nossa gestão. A visão integrada do       │
│  financeiro com o progresso das obras nos deu um poder de        │
│  decisão que não tínhamos antes."                                │
│  — João da Silva, Diretor na Construtora Exemplo                 │
│                                                                  │
│  Métricas (3 colunas):                                           │
│  [+30h economizadas/mês] [15% ↓ desperdício] [100% nos prazos]  │
│                                                                  │
│  Logos de clientes (placeholders → preencher com reais)          │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  SEGURANÇA — bg #F0F2F5, duas colunas (desktop)                  │
│                                                                  │
│  TEXTO                         │  BADGES                        │
│  h3: "Segurança em Nível       │  🛡 Criptografia AES-256       │
│        Empresarial"            │  🔒 OWASP Top 10 Mitigado      │
│  "Seus dados são seu maior     │  ☁ Backups Diários             │
│  ativo..."                     │  🛡 Conformidade LGPD          │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  FINAL CTA — bg #0A2A5B (navy), texto branco                     │
│  h2: "Pronto para revolucionar a gestão da sua construtora?"     │
│  p: "Veja na prática como nossa plataforma pode aumentar         │
│     sua eficiência e rentabilidade."                             │
│  [Solicitar Demonstração Gratuita]  ← botão branco/claro        │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  FOOTER — bg #495057, texto #aeb9c7                              │
│  © SGI 2026   Links: Política de Privacidade · Termos · Contato │
└──────────────────────────────────────────────────────────────────┘
```

#### Notas de implementação

- Header fixo (`sticky top-0 z-50`) com `backdrop-blur` e sombra sutil
- Hero: `pt-[140px]` para compensar o header fixo
- Módulos usam **Lucide React** no lugar do Phosphor Icons (v01 usava Phosphor — não instalar)
- Ícones dos 6 cards: `HardHat`, `BarChart3`, `TrendingUp`, `MessageCircle`, `FolderOpen`, `Brain`
- Métricas da SocialProof animadas com contagem (opcional — Fase B.2)
- FinalCTA ancora para `#solicitar-demo` (form de contato ou link WhatsApp)
- Responsivo: mobile-first, breakpoints `md:` (768px) e `lg:` (1024px)

### 5.2 LoginPage (`/login`) ✅ Construída

Layout **dois painéis** (desktop): painel navy à esquerda com feature bullets; painel branco à
direita com o formulário. Mobile: só o formulário com logo no topo.

```
┌──────────────────────────┬──────────────────────────────────────┐
│  PAINEL ESQUERDO (navy)  │  PAINEL DIREITO (branco)             │
│                          │                                      │
│  [SGI]  Gestão Integrada │  "Entrar na sua conta"               │
│                          │  "Acesse a plataforma com suas       │
│  "A plataforma completa  │   credenciais."                      │
│  para sua construtora."  │                                      │
│                          │  [Erro] ← aparece se login falhar    │
│  ✓ Obras e empreend.     │                                      │
│  ✓ Financeiro, RH e CRM  │  Usuário ________________           │
│  ✓ Análise de IA         │  Senha  ______________ 👁            │
│  ✓ LGPD e multi-tenant   │                                      │
│                          │  [⟳ Entrando… / → Entrar]           │
│  © 2026 SGI              │                                      │
│                          │  Esqueci minha senha                 │
│                          │  ← Voltar para o início              │
└──────────────────────────┴──────────────────────────────────────┘
```

- `POST /auth/login/` via `AuthContext.login()` → token em `localStorage` (cookie `HttpOnly` na Fase 10.6)
- Spinner e botão desabilitado durante submit; alerta vermelho inline em caso de erro
- Redireciona para `/app/dashboard` ou `location.state.from`

### 5.3 AppHomePage — Hub da Edição Construtora (`/app/dashboard`)

O **hub da edição** do §9 da identidade: faixa Meia-Noite com a malha viva (saudação + chip
"Edição Construtora · Construir" + números vivos clicáveis) e o conteúdo em **abas horizontais**,
com a aba na URL (`?aba=`) para ser linkável.

| Aba | O que resolve | Referência de mercado |
|---|---|---|
| **Visão geral** | KPIs compostos dos módulos + medidores de plano + prévia da fila | tiles dinâmicos do SAP Fiori Launchpad |
| **Requer decisão** | fila numerada, no acento, com o verbo e o destino | *Assigned to Me* (ACC) · *open items for review* (Procore) · *Assistant* (Salesforce) |
| **Agenda** | próximos 7 dias do feed agregado do calendário | *Today's Tasks/Events* (Salesforce) · *today's schedule* (Procore) |
| **Módulos** | **todos** os módulos, agrupados pelo endereço no ciclo | *App Launcher* (Salesforce) · *spaces/pages* (Fiori) |
| **Atividade** | feed de fatos reais, carimbado com o módulo de origem | *Recently changed* (Procore) · *Recent Items* (ACC) |

**Dados honestos — não há endpoint "dashboard da home".** O hub **compõe** os agregados que cada
módulo já calcula, cada chamada condicionada ao entitlement
([useHomeResumo](../frontend/src/pages/app/home/useHomeResumo.ts)): `/api/plano/` (uso real das
quotas, sempre), `/api/erp/dashboard/` (exige `erp.relatorio.view`), `/api/scm/dashboard/`,
`/api/sil/dashboard/` e `/api/calendar/events/`. Quem não assina um módulo **não vê um zero** —
não vê o KPI. Onde não há fonte (avanço físico → PDCA; DRE por obra → D.1.4), o mosaico diz
**"em breve"**. O hub de dois usuários da mesma empresa é legitimamente diferente.

**Catálogo** ([catalogo.ts](../frontend/src/pages/app/home/catalogo.ts)): os módulos são agrupados
por **estágio do ciclo** (Originar/Construir/Negociar/Operar + Plataforma transversal), não por
"base × pago", e incluem os **futuros com o horizonte** (H1/H2/H3) — o farol mostra a casa inteira,
inclusive os cômodos por construir. Nada é escondido: o inacessível aparece travado com o motivo
(`Módulo não contratado` · `Somente administradores` · `Backend pronto — tela em construção` ·
`Planejado`).

```
┌─ faixa Meia-Noite (malha viva) ──────────────────────────────┐
│  ▣  Bom dia, ana.                  [Edição Construtora ·     │
│     sexta, 25 de julho de 2026      Construir]               │
│                                                              │
│  7 decisões aguardando   12 compromissos em 7 dias   14 mód. │
├──────────────────────────────────────────────────────────────┤
│ [Visão geral] [Requer decisão ⑦] [Agenda] [Módulos] [Ativid.]│  ← abas (?aba=)
├──────────────────────────────────────────────────────────────┤
│  INDICADORES                                                 │
│  ┌────────┐┌────────┐┌────────┐┌────────┐┌──────────────┐    │
│  │ Obras  ││A receb.││ A pagar││Estoque ││ Avanço físico│    │
│  │  4     ││R$ 128k ││ R$ 96k ││R$ 61k  ││  [em breve]  │    │
│  │de 8 no ││ ERP    ││  ERP   ││  SIL   ││ depende do   │    │
│  │  plano ││        ││        ││        ││   PDCA       │    │
│  └────────┘└────────┘└────────┘└────────┘└──────────────┘    │
├───────────────────────────────────┬──────────────────────────┤
│  REQUER SUA DECISÃO               │  SEU PLANO               │
│  01 Requisições a aprovar   SIL → │  Essencial               │
│  02 Pagamentos vencidos     ERP → │  obras     ▓▓▓▓░░ 4/8    │
│  03 Cotações no prazo final SCM → │  clientes  ▓▓░░░░ 22/100 │
└───────────────────────────────────┴──────────────────────────┘
```

### 5.4 EmpreendimentosListPage

- Tabela com colunas: Nome, CNPJ, Status, Orçamento, Ações
- Filtro por status (`<Select>`)
- Botão "+ Novo Empreendimento" abre `<Sheet>` lateral com form
- Click na linha → `/app/empreendimentos/:eId`

### 5.5 EmpreendimentoDetailPage

```
Header: nome + status badge + [Editar]
Tabs: Visão Geral | Obras | Contas Bancárias | Custos | Unidades
─ Visão Geral: contagem de unidades (cadastradas · à venda · vendidas) + dados cadastrais
─ Unidades: o estoque à venda em linhas e colunas — ordenação server-side sobre o
  estoque inteiro, filtros (situação/quadra), busca, carregamento por página e CRUD.
  Ordem padrão é a do endereço (quadra › lote › bloco › andar › apto), numérica.
  É o cadastro que alimenta o seletor de unidade da venda (§5.8)
─ Obras: ObrasListPage filtrada por empreendimentoId
─ Financeiro: contas bancárias, custos, faturas vinculadas
─ Documentos: lista + upload
─ Custos: CustoEmpreendimento com fornecedores
```

### 5.6 ObrasListPage

- Seletor de empreendimento no topo (select ou breadcrumb)
- Tabela: ID, Nome, Endereço, Status badge, Início/Fim previsto
- Click → `/app/empreendimentos/:eId/obras/:obraId`

### 5.7 ObraDetailPage — página mais complexa

```
Breadcrumb: Empreendimentos / Residencial Alfa / Obras / Bloco A
Header: nome + status badge + [Editar]
KPI row: [Progresso geral] [Etapas concluídas/total] [Dias restantes] [Orçamento]

Layout duas colunas (lg:grid-cols-[320px_1fr]):

COLUNA ESQUERDA (320px fixo):
  ┌─────────────────────┐
  │ Localização         │
  │ MapaObra (Leaflet)  │
  ├─────────────────────┤
  │ Documentos          │
  │ lista + [Upload]    │
  ├─────────────────────┤
  │ Projeto 3D/Drone    │
  │ BluePrint / iframe  │
  └─────────────────────┘

COLUNA DIREITA (Tabs):
  [Visão Geral] [Cronograma] [Diário] [Financeiro] [Equipe]

  Visão Geral:
    datas previstas/reais, orçamento, descrição, responsáveis

  Cronograma:
    lista de EtapaObra com GanttBar inline por etapa
    status badge + % conclusão + datas + responsável

  Diário (ObraTimeline):
    linha do tempo de DiarioObra
    cada entrada: data + descrição + fotos com AnaliseStatus IA

  Financeiro (hasModule erp_financeiro):
    ContasPagar/Receber da obra
    gráfico de execução financeira vs orçado

  Equipe:
    M2M responsaveis_tecnicos + equipe (rh.Funcionario)
```

### 5.8 Clientes — a carteira (`/app/clientes`)

A lista de clientes é uma **grade tipo planilha**, não uma tabela: a carteira de
uma loteadora chega a milhares de linhas, e a tela precisa achar *um* lote entre
elas. Camada em [modules/clientes/carteira/](../frontend/src/modules/clientes/carteira/);
contrato do backend em [clientes/carteira.py](../backend/clientes/carteira.py).

**Duas coisas independentes**, como nos grids corporativos (AG Grid, Airtable,
relatórios do Salesforce) e nos Subtotais do Excel:

- **Visão** — o que é *uma linha*: `Clientes` (uma pessoa, com a última unidade e
  o contador das demais) ou `Unidades` (uma aquisição por linha, pessoa repetida).
  Sem isso, "unidade" e "adimplência por lote" não seriam colunas honestas.
  Cada visão é uma **planilha própria**, não a mesma com outro filtro: tem a sua
  **coluna-âncora** — a primeira, congelada, a que abre a ficha (`Cliente` numa,
  `Unidade` na outra) —, a sua **ordem padrão** (pessoas em ordem alfabética;
  unidades na ordem do endereço) e o seu próprio conjunto de colunas, larguras,
  agrupamento e ordenação. A âncora não se desliga nem se arrasta para o meio.
- **Agrupar por** — até **3 níveis** empilháveis (empreendimento, quadra,
  bloco/torre, cidade, UF, faixa de atraso, condição de pagamento, ano da compra,
  cliente). Cada grupo é um cabeçalho recolhível com contagem e subtotais
  calculados **no banco sobre a carteira inteira** (`GROUP BY`), não sobre a
  página carregada; abrir um grupo dispara a consulta das linhas dele.

**Ordenar** — **toda coluna ordena**, pelo clique no título (alterna o sentido) ou
pelo menu **"Ordenar por"** do cabeçalho, que diz em palavras o que a seta faz
("A → Z", "Menor → maior", "Mais recente primeiro"). A ordenação é **server-side**
sobre a carteira inteira, não sobre a página em mãos, e cada chave da tela tem
correspondente em `ORDENACOES` ([carteira.py](../backend/clientes/carteira.py)) —
menu sem item morto. Toda ordem carrega o desempate pela chave primária: sem ele
duas linhas de mesmo valor trocam de lugar entre páginas e a rolagem infinita
repete uma e come a outra.

Demais recursos de planilha: rolagem infinita virtualizada (só o visível é
renderizado), cabeçalho e primeira coluna congelados, colunas redimensionáveis e
reordenáveis por arrasto, seletor de colunas, seleção com Shift/Ctrl, **Ctrl+C**
copiando TSV (cola no Excel) e navegação por teclado. As preferências ficam
salvas por usuário **e por visão** (`localStorage`, chave
`sgi_carteira_clientes_v2`).

**Identificação da unidade** — `ClienteEmpreendimento` tem quadra, lote,
bloco/torre, andar e unidade **estruturados** (o `unidade_comprada` segue como
rótulo livre); o backend monta `rotulo_unidade` ("QD 12 · LT 05" ou
"Torre A · 3º · 302") para que grade, extrato e ficha nunca divirjam. Os cinco
níveis também são **colunas próprias** na visão de unidades, e juntos formam a
**ordem natural** dela — quadra › lote › bloco/torre › andar › apto —, que é a
ordem padrão e a que a coluna `Unidade` aplica. Natural e não alfabética: os
campos são texto (existe "Quadra A", "Lote 12-B"), e em ordem de texto o lote 10
vem antes do 2. A chave de ordenação preenche o valor com zeros à esquerda e
manda o nível vazio para o fim (`nulls_last`) — o apartamento sem quadra não se
mistura ao loteamento. Cidade/UF saem do **empreendimento** (campos próprios, não
do endereço em texto livre) — é a cidade do imóvel, que não se confunde com a do
cliente.

**Adimplência e LGPD.** A pílula *adimplente/inadimplente* aparece para quem
enxerga o cadastro; **parcelas, valores e dias de atraso** exigem
`erp.cobranca.view` além de `cadastro.cliente.view` (gate de duas pontas, o
mesmo das divergências Asaas) e nem saem do backend sem ela — a tela nunca
mostra "R$ 0,00" no lugar de "sem acesso". **Ordenar por um dado é lê-lo**, então
a ordenação segue o mesmo gate do valor: por dívida exige `erp.cobranca.view` e
por documento exige `cadastro.cliente_doc.view` — a ordem alfabética dos CPFs
reconstruiria, linha a linha, o que a máscara esconde. A resposta traz
`podeFinanceiro`/`podeDocumento` para o menu mostrar a opção **travada com o
motivo** em vez de aceitar o clique e não ordenar. CPF/CNPJ segue mascarado sem
`cadastro.cliente_doc.view`. A fonte é `ContaReceber` (a viva); "atrasado" é
derivado do vencimento, nas mesmas faixas do aging do ERP.

#### A venda de uma unidade (`AquisicaoForm`)

A identificação da unidade **não se digita mais na venda**: ela é cadastro do empreendimento (aba
**Unidades**), e o formulário de aquisição só escolhe uma das que estão à venda. Era daí que vinha o
conflito — o rótulo livre (`Unidade comprada`) e os cinco campos estruturados eram preenchidos lado a
lado, podiam divergir, e o mesmo lote podia ser vendido duas vezes por caminhos diferentes.

O preço parte do **valor de tabela** da unidade e o que o cliente paga sai de uma conta: desconto →
entrada (parcelável, **sem juros**) → saldo em N parcelas por **Price** (fixa) ou **SAC**
(decrescente) → **balões** anuais/semestrais. A conta roda no **backend** (`POST
/api/clientes-empreendimentos/simular/`, com folga de digitação), nunca no navegador: repetir a
fórmula na tela criaria duas matemáticas para o mesmo contrato, e a da tela seria a que o cliente vê.
O painel mostra o resumo (negociado, entrada, saldo, juros, total, parcela) e abre o carnê linha a
linha antes de salvar.

**Salvar registra a proposta; o carnê é outro ato.** As parcelas só viram `ContaReceber` pelo botão
**"Gerar parcelas"** na ficha, depois da conferência — e **sem boleto**: cobrar é decisão do ERP,
unitária ou por lote. O botão some quando o carnê existe (o backend recusa a segunda geração).

#### ClienteDetailPage — 6 abas

`Ficha` · `Aquisições` · `Documentos` · `Dados bancários` · **`Financeiro`** ·
**`Obra`**. As duas últimas são a integração entre módulos aparecendo na tela
(§1.6.6): **Financeiro** é o extrato parcela a parcela com o boleto de cada uma e
a unidade que ela paga (`GET /api/clientes/<id>/financeiro/`); **Obra** mostra o
andamento das obras do empreendimento comprado, com o percentual declarado como
*média das etapas* e link para o módulo de Obras — obra sem etapa cadastrada diz
"em breve", nunca 0% (`GET /api/clientes/<id>/obra/`).

### 5.9 FornecedoresListPage

- Lista: Nome, CNPJ, produtos/serviços, obras relacionadas

### 5.10 ERP (hasModule: erp_financeiro) ✅ Fundação UI + Contas a pagar/receber + Boletos 08/06/2026

> Fundação (D.1.0) e Contas a pagar/receber (D.1.1) construídas — modelo de frontend específico em
> [docs/modulos/moduloerp.md §5](modulos/moduloerp.md#5-frontend-do-erp--navegação-e-arquitetura)
> (estende, não substitui, o modelo geral deste documento: TanStack Query/Table, Recharts,
> RHF+zod, `MoneyInput`/centavos inteiros, code-splitting).

- **`ErpDashboardPage`** (`/app/erp`, hub) ✅ — `KpiCard` (a receber/a pagar/saldo projetado/fluxo do
  mês) + `FluxoCaixaChart` (receitas x despesas mensais) + `AgingChart` (aging a receber/a pagar),
  todos sobre `useErpDashboard()` → `GET /api/erp/dashboard/` (cacheado, React Query); cards
  `WorkspaceLinkCard` → `/app/erp/contas-a-{pagar,receber}`. No header, `DivergenciasErpButton` —
  botão-alerta (colorido + contagem quando há divergências banco × Asaas) que abre modal com o
  `DivergenciasAsaasPanel`; visível só com as permissões de usuário `erp.cobranca.view` + `cadastro.cliente.view`
  (gate LGPD+escopo — `hasModule` não basta, é do tenant; reforçado no backend), documento mascarado sem
  `cadastro.cliente_doc.view`. Sem `erp.relatorio.view`, os KPIs/gráficos degradam para um aviso amigável
  (403 velado, F4)
- **`ContasAPagarPage`/`ContasAReceberPage`** (`/app/erp/contas-a-{pagar,receber}`, rotas-irmãs) ✅ —
  arquétipo "Workspace de lista financeira" ([moduloerp.md §5.5](modulos/moduloerp.md#55-arquétipos-de-página-layouts-reutilizáveis)):
  `FilterBar`+`FinanceDataTable` (paginação/ordenação server-side) + `Sheet` lateral com 4 modos
  (`create`/`edit`/`view`/`baixa`) — lançar conta com `RateioField` (centro de custo), ver detalhe
  (rateios, boletos, ações), editar, dar baixa parcial ou total. Breadcrumb de volta ao hub.
- **`Sheet`** (slide-over) ✅ — **1º uso no projeto**; `open/onClose/title/description/footer/width`
- **Formulários RHF+zod** ✅ — **1ª adoção de `react-hook-form`+`zod` no projeto** (ver
  [moduloerp.md §5.3](modulos/moduloerp.md#53-stack-adicional-estende-o-do-projeto)):
  `ContaPagarForm`/`ContaReceberForm` (`useFieldArray` para `RateioField`, `setError`+
  `parseApiErrors`/`FormErrorBanner` para erros de API) e `BaixaForm` (compartilhado, espelha
  `dar_baixa()` do backend — juros/multa/desconto via `MoneyInput`+`Controller`)
- **Camada de dados** ✅ — `erpKeys` (fábrica de chaves) → `endpoints/{contasAPagar,contasAReceber,
  centrosCusto,lotesRemessa,dashboard}` → `hooks/{useContasAPagar,useContasAReceber,useCentrosCusto,
  useLotesRemessa,useEntityOptions,useErpDashboard}`; mutações (criar/editar/baixa) invalidam
  `erpKeys.contasA{Pagar,Receber}` + `erpKeys.dashboard.all` → hub e listas atualizam sozinhos
- **Componentes compartilhados** ✅ — `FilterBar` · `FinanceDataTable` (TanStack Table headless,
  server-side sobre `ErpPageNumberPagination`) · `MoneyInput`/`MoneyDisplay` (centavos inteiros) ·
  `KpiCard` · `StatusContaBadge` (`STATUS_CONTA_CONFIG`: ABERTO/PARCIAL/QUITADO/CANCELADO)
- **Code-splitting** ✅ — `modules/erp/routes.tsx` com `lazy`/`Suspense`, rotas-irmãs (mesmo padrão
  de `empreendimentos`/`empreendimentos/:id`, não aninhadas) — chunks `ErpDashboardPage`/
  `ContasAPagarPage`/`ContasAReceberPage`/`BaixaForm` separados do bundle principal
- **Validado (golden path, 07/06/2026)** ✅ — CRUD completo, baixa parcial→total, rateio por centro
  de custo, lote de remessa e aging do dashboard testados via API/gateway; dados de teste limpos.
  **Achado:** `dar_baixa()` aceita baixa repetida em título já `QUITADO` — ver
  [moduloerp.md "Dívidas técnicas"](modulos/moduloerp.md#dívidas-técnicas-conhecidas) (decidir regra
  antes de D.1.2/webhook Asaas)
- **`BoletosListPage`/`BoletoDetailPage`** (`/app/erp/boletos`, `/app/erp/boletos/:id`, rotas-irmãs)
  ✅ D.1.2 08/06/2026 — **telas dedicadas** (decisão do usuário, não Sheet/drill-down): a lista é um
  workspace só-leitura (`FilterBar`+`FinanceDataTable`, filtra por status/vencimento — o boleto nasce
  do gateway Asaas, não de lançamento manual); o detalhe mostra os dados do gateway (linha digitável,
  link do PDF) + **timeline de eventos do webhook** (`useEventosWebhookAsaas` →
  `GET /api/erp/cobrancas/eventos/?boleto={id}`), provando evento a evento como a baixa automática
  aconteceu. `StatusBoletoBadge`/`statusBoleto.ts` espelham `StatusContaBadge`. Botão
  **"Gerar cobrança (Asaas)"** no Sheet de detalhe de `ContaReceber` (`useGerarCobrancaContaAReceber`)
  enfileira a emissão real no Asaas sandbox. Detalhe completo:
  [funcoescobrancas.md "UI dedicada"](modulos/funcoescobrancas.md#ui-dedicada--telas-de-boletos-entregue-08062026-)
  e [moduloerp.md §6](modulos/moduloerp.md#6-boletos--cobrança--integração-asaas).
- **Próximas telas (❌ ainda não construídas)**: notas fiscais (abas emitidas/recebidas/canceladas,
  D.1.3), financeiro por obra (DRE, D.1.4) — ver roadmap em
  [docs/modulos/moduloerp.md §13](modulos/moduloerp.md#13-roadmap-em-sub-fases-fase-d1x)

### 5.11 RH (hasModule: rh) ✅ 06/06/2026

Módulo completo. Rotas: `/app/rh` · `/app/rh/cargos` · `/app/rh/:id`.

**FuncionariosListPage** (`/app/rh`):
- Tabela: Nome/email, CPF, Cargo, Status badge (ativo/férias/licença/inativo/desligado), Admissão, Salário
- Filtros client-side: busca (nome+CPF) + select de status
- Botão "Cargos" → CargosPage; botão "+ Novo Funcionário" → FuncionarioForm (Sheet)
- `useFuncionarios()` + `useCargos()` com `cargoMap` para join client-side

**CargosPage** (`/app/rh/cargos`):
- Tabela: Nome do Cargo, Departamento, Descrição (truncada)
- CRUD completo (criar, editar modal, excluir com confirmação)
- Back → FuncionariosListPage

**FuncionarioDetailPage** (`/app/rh/:id`):
- 4 abas:
  - **Dados Pessoais** — 4 cards: Identificação, Contato & Endereço, Contrato, Documentos Trabalhistas
  - **Documentos (N)** — upload de arquivo (tipo + nome + arquivo) + listagem com link externo + exclusão
  - **Saúde** — `DadoMedicoFuncionario` (1-to-1); mostra cadeado + mensagem se `rh_medico` negado (403)
  - **Financeiro** — 3 seções: Dados Bancários (lista+CRUD), Pagamentos (lista+CRUD), Folhas de Pagamento (lista+CRUD); mostra cadeado se `rh_financeiro` negado (403)
- `Promise.allSettled` para 6 fetches paralelos; 403 não quebra a página
- Editar funcionário (Sheet FuncionarioForm), excluir com modal de confirmação

### 5.12 CRM (hasModule: crm)

- **CrmDashboardPage**: funil de leads (Kanban ou funil visual)
- **LeadsPage**: tabela de leads + pipeline de conversão

### 5.13 DiarioObraPage (`/app/diario`)

- Seletor de obra no topo
- Timeline de entradas do diário
- Cada entrada: data, condições climáticas, descrição, fotos
- Fotos: badge de análise IA (pendente / concluída / falha)
- Click na foto → modal com `AnaliseCard` (resultado da IA)
- FAB "+" para novo diário (com form inline ou Sheet)

### 5.14 DroneWrapperPage (`/app/drone`) — hasModule: drone

- Topbar da rota injeta `empreendimento_id` e `obra_id` da URL
- `<iframe src="/drone/?token=JWT&empreendimento_id=X&obra_id=Y">`
- Spinner enquanto carrega
- Badge "Módulo Drone" no Topbar

### 5.15 CalendarioPage (`/app/calendario`)

- Grade mensal de `CalendarEvent`
- Eventos coloridos por tipo (obra, reunião, prazo financeiro)

### 5.16 Plano e quotas (D24) — 📋 planejado

O backend já **trava** a criação acima da quota do plano (402) e serve o medidor;
falta a camada visual. O desenho abaixo é o contrato do frontend com o que já existe.

**Princípio que organiza tudo:** o 402 tem de ser a **confirmação de algo já visível**, nunca a
primeira notícia. Descobrir o limite depois de preencher um cadastro inteiro faz o produto parecer
quebrado; descobrir antes faz o plano parecer pequeno — que é a leitura correta e a que vende
upgrade. Daí a ordem de prioridade: **medidor → botão desabilitado → diálogo de upgrade**. Se só uma
coisa for construída, que seja o medidor.

#### 5.16.1 O contrato vindo do backend

`GET /api/plano/` devolve plano vigente, medidores, próximo degrau e o catálogo inteiro:

```jsonc
{
  "plano": { "slug": "free", "nome": "Free", "preco_mensal": 0, "publico": "..." },
  "quotas": [
    { "recurso": "obras", "rotulo": "obras", "limite": 2, "uso": 1,
      "ilimitado": false, "restante": 1, "excedido": false, "fonte": "backend" },
    { "recurso": "seats", "rotulo": "seats", "limite": 1, "uso": null,
      "ilimitado": false, "restante": null, "excedido": false, "fonte": "iam" }
  ],
  "proximo_plano": { "slug": "essencial", "nome": "Essencial", "preco_mensal": 149 },
  "catalogo": [ { "slug": "...", "nome": "...", "preco_mensal": 149, "quotas": { ... } } ]
}
```

Três regras que não devem ser reinterpretadas na tela:

- **Preço nunca é escrito no frontend.** Sai de `catalogo`, que vem de `payment/planos.py` — a mesma
  tabela que a IAM usa para emitir os tetos. Um preço em código de frontend é um preço que vai
  divergir da cobrança, e quem descobre a divergência é o cliente, na fatura.
- **`limite: 0` ≠ `ilimitado`.** `0` significa "não incluído neste plano" (o `free` usa isso) e
  `ilimitado: true` significa sem teto. Tratar os dois como "sem limite" mostraria como disponível
  justamente o que o plano de entrada não vende.
- **`uso: null` não é zero.** É o caso de `seats`, cuja `fonte` é `"iam"`: o backend não conta
  usuários (o `Usuario` de lá é espelho JIT). A barra de seats se abastece de `GET /iam/usuarios/`,
  ou mostra só o limite. Desenhar `null` como `0` diria ao cliente que ele tem todos os seats livres.

#### 5.16.2 Tratamento global do 402

O 402 chega de **qualquer** criação — quatro recursos no backend e o cadastro de usuário na IAM — e
com **o mesmo corpo** nos dois serviços:

```jsonc
{ "detail": "…texto pronto para exibir…", "code": "quota_excedida",
  "quota": "obras", "limite": 2, "uso": 2, "plano": "free" }
```

Por isso o tratamento é **um interceptor de resposta**, irmão do que já trata 401 em
[`api/session.ts`](../frontend/src/api/session.ts) — e não um `catch` por formulário. Tratar por
formulário significa repetir a lógica em cinco telas e esquecer na sexta, que é exatamente a tela
nova que alguém vai escrever depois.

O interceptor reconhece `code === "quota_excedida"`, abre o `UpgradeDialog` e **não** deixa o erro
virar toast genérico. Ler `code`, nunca a string de `detail`: o texto muda, o código é contrato (é
por isso que o backend devolve os dois).

#### 5.16.3 Componentes

| Componente | Papel |
|---|---|
| `usePlano()` | Hook sobre `GET /api/plano/`. Invalidado após criar/excluir qualquer recurso contado — senão o medidor mente até o F5. |
| `QuotaMeter` | Barra uso/limite com rótulo. Estados: normal · atenção (≥80%) · esgotado. Trata `ilimitado` e `uso: null` sem inventar número. |
| `QuotaBanner` | Aviso discreto no topo da listagem quando o recurso daquela tela está ≥80%. É o que transforma o 402 em confirmação. |
| `UpgradeDialog` | Aberto pelo interceptor. Diz qual limite bateu, o uso atual, o plano vigente e o próximo com preço. Duas saídas: liberar espaço (link para a listagem) ou subir de plano. |
| `NovoButton` desabilitado | Nas listagens dos 4 recursos contados: com `excedido`, o botão fica inativo com tooltip explicando — padrão de botão inativo já definido em [frontend-convencoes.md](frontend-convencoes.md). Evita a pior sequência possível, que é preencher tudo e perder no submit. |

#### 5.16.4 Página `/app/admin/plano`

Ao lado de `/app/admin/papeis` e `/app/admin/usuarios`, sob o mesmo guard de `is_tenant_admin`:

- **Plano vigente** — nome, preço, público-alvo.
- **Medidores** — um `QuotaMeter` por quota, os esgotados primeiro.
- **Comparativo** — tabela do `catalogo`, plano atual destacado, quotas lado a lado.
- **CTA de upgrade.**

#### 5.16.5 O CTA enquanto não há checkout

O autoserviço (landing → checkout → Asaas → provisionamento) é o **item 3** do faseamento do
[monetizacao.md §10](arquitetura/monetizacao.md) e **não existe**. Até existir, o CTA abre um
formulário de contato ou um `mailto` — e deve dizer isso com todas as letras ("solicitar upgrade",
não "assinar agora"). Um botão que promete pagamento imediato e entrega um e-mail queima a conversão
uma vez por cliente, e é a impressão que fica.

Quando o checkout entrar, muda **só o destino do botão** — todo o resto desta seção continua valendo.

### 5.17 SCM — Suprimentos (`hasModule: scm`) — ✅ construído (S.1–S.4, 1º módulo Malha)

> Módulo **grande** e o primeiro porte v01→v02 completo no backend. O **contrato de API, o modelo e o
> escopo detalhado de UI (sub-fases S.1–S.4)** estão em
> [modulos/moduloscm.md](modulos/moduloscm.md#frontend-fase-atual--escopo-e-sub-fases) — esta seção é
> só o resumo para navegação. **Este frontend é o SCM interno da fase atual, não o da expansão**
> (marketplace/rede/lado vendedor ficam de fora; a UI apenas não esconde os campos-seam).

O conceito que a UI precisa acertar: **duas vias de aquisição que convergem no mesmo pedido** —
**compra direta** (de uma oferta a preço fixo, sem cotar) e **cotação/RFQ** (demanda → propostas →
adjudicar → pedido). Fluxo interno: `Demanda → Cotação → adjudicar → Pedido → Recebimento → Avaliação`,
ou `Oferta → comprar direto → Pedido → Recebimento`.

Telas por sub-fase (todas `hasModule('scm')` + gate por permissão `scm.*`):

- **S.1 Catálogo** — `ProdutosPage` (mestre), ofertas de fornecedor por produto (+ faixas de preço),
  `CentrosCustoPage` (o centro de custo é **próprio do SCM**, com `tipo`; obra é só um dos tipos).
- **S.2 Demanda & Cotação** — `DemandasPage` (com itens; botão **Publicar** → `scm.demanda.publicar`);
  `CotacaoDetailPage` com **mapa comparativo** de propostas + **Adjudicar** (`scm.cotacao.adjudicar`).
- **S.3 Pedido & Recebimento** — `PedidosPage` com os dois caminhos (**Comprar direto** de uma oferta
  `compra_direta` · **Gerar de cotação** — ambos `scm.pedido.criar`); `PedidoDetailPage` (itens, status,
  **registrar recebimento**); `AvaliacaoForm`.
- **S.4 Hub SCM** — `ScmDashboardPage` (KPIs: demandas abertas, cotações a adjudicar, pedidos por
  status) — substitui o `status/` placeholder.

Stack/padrões (como **construído**): TanStack Query com fábrica genérica de hooks CRUD
(`modules/scm/hooks.ts` sobre `scmApi`), code-splitting por `modules/scm/routes.tsx`. Por decisão de
projeto (21/07), **não** reaproveita os componentes legados do ERP (`FinanceDataTable`/`FilterBar`/
`Sheet`, que serão migrados): o SCM nasce sobre a **fundação Malha** com **kit de UI próprio** em
`modules/scm/components/ui.tsx` (`PageHeader`, `DataTable`, `Drawer`, `Modal`, inputs, `Pager`) +
`AsyncEntitySelect` (select com **busca server-side** — fecha o F2 no SCM) + `seams.tsx` (chips
read-only de rede/ERP/NF-e/estoque). Forms controlados com `@/utils/formErrors` (sem RHF/zod). É a
**referência do padrão Malha** para os próximos módulos. Endpoints em §7.3; contrato completo e rotas
em [moduloscm.md](modulos/moduloscm.md).

---

## 6. Auth & Entitlement

### 6.1 AuthContext (mantido e expandido)

```ts
interface AuthContextType {
  isAuthenticated: boolean
  user: User | null
  tenant: string | null        // ← novo: nome do tenant (para o Topbar)
  modules: string[]
  roles: string[]              // ← novo: claims de papéis do JWT
  loading: boolean
  token: string | null         // ← exposto explicitamente (corrige bug atual)
  login(username, password): Promise<void>
  logout(): void
  hasModule(code: string): boolean
  hasRole(role: string): boolean  // ← novo
}
```

- `GET /auth/me/` retorna `{ id, username, email, tenant, modules, roles }`
- `token` exposto diretamente (elimina o acesso via `localStorage` nos hooks)
- A migração para cookie `HttpOnly` (Fase 10.6) acontece sem mudar os consumers

### 6.2 Guards de rota

```tsx
// PrivateRoute — autentica
<Route element={<PrivateRoute />}>
  <Route path="/app" element={<AppShell />}>
    ...
  </Route>
</Route>

// ModuleRoute — entitlement
<ModuleRoute module="erp_financeiro">
  <Route path="erp" element={<ERPDashboardPage />} />
</ModuleRoute>
```

### 6.3 Sidebar entitlement-aware

```tsx
const navItems = [
  { label: 'Dashboard',      icon: LayoutDashboard, to: '/app/dashboard' },
  { label: 'Empreendimentos',icon: Building2,        to: '/app/empreendimentos' },
  { label: 'Obras',          icon: HardHat,          to: '/app/obras' },
  { label: 'Clientes',       icon: Users,            to: '/app/clientes' },
  { label: 'Fornecedores',   icon: Truck,            to: '/app/fornecedores' },
  // módulos pagos — só exibe se hasModule()
  { label: 'ERP',            icon: BarChart3,        to: '/app/erp',   module: 'erp_financeiro' },
  { label: 'RH',             icon: UserCog,          to: '/app/rh',    module: 'rh' },
  { label: 'CRM',            icon: TrendingUp,       to: '/app/crm',   module: 'crm' },
  // extras
  { label: 'Diário / IA',   icon: Brain,            to: '/app/diario' },
  { label: 'Drone',          icon: Plane,            to: '/app/drone', module: 'drone' },
  { label: 'Calendário',     icon: CalendarDays,     to: '/app/calendario' },
]
```

---

## 7. Camada de Dados

### 7.1 apiClient (mantido)

```ts
// src/api/apiClient.ts
const apiClient = axios.create({ baseURL: '/api' })
apiClient.interceptors.request.use(config => {
  const token = localStorage.getItem('token') // → cookie HttpOnly na Fase 10.6
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
```

### 7.2 Padrão de hooks por módulo

Cada módulo tem seus próprios hooks em `src/modules/<modulo>/hooks/`:

```ts
// src/modules/obras/hooks/useObras.ts
export function useObras(empreendimentoId?: number) { ... }

// src/modules/obras/hooks/useObra.ts
export function useObra(obraId: number) { ... }

// src/modules/obras/hooks/useEtapas.ts
export function useEtapas(obraId: number) { ... }

// src/modules/obras/hooks/useDocumentos.ts
export function useDocumentos(obraId: number) { ... }
```

Padrão interno de cada hook:

```ts
function useObra(obraId: number) {
  const { token } = useAuth()
  const [data, setData] = useState<Obra | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!obraId) return
    setLoading(true)
    apiClient.get(`/obras/${obraId}/`)
      .then(r => setData(r.data))
      .catch(() => setError('Erro ao carregar obra'))
      .finally(() => setLoading(false))
  }, [obraId, token])

  return { data, loading, error }
}
```

### 7.3 Endpoints consumidos por módulo

| Módulo | Endpoints |
|---|---|
| Auth | `POST /auth/login` · `GET /auth/me` · `POST /auth/logout` |
| Empreendimentos | `GET/POST /api/empreendimentos/` · `GET/PUT/DELETE /api/empreendimentos/:id/` |
| Obras | `GET/POST /api/obras/` · `GET/PUT /api/obras/:id/` |
| Etapas | `GET/POST /api/etapas-obras/` · `PUT /api/etapas-obras/:id/` |
| Documentos obra | `GET/POST /api/documentos-obras/` (multipart) |
| Clientes | `GET/POST /api/clientes/` · `GET/PUT /api/clientes/:id/` |
| Fornecedores | `GET /api/fornecedores/` |
| ERP | `GET /api/erp/dashboard/` · `GET/POST /api/erp/contas-a-pagar/` (+ `dar-baixa`, `gerar-lote-remessa`) · `GET/POST /api/erp/contas-a-receber/` (+ `dar-baixa`, `emitir-nfse`/`emitir-nfe`) · `GET/POST /api/erp/centros-custo/` · `GET /api/erp/lotes-remessa/` · etc. |
| RH | `GET /api/funcionarios/` |
| CRM | `GET /api/crm/leads/` · `GET /api/crm/oportunidades/` |
| SCM (`scm`) | Catálogo: `/api/scm/{produtos,ofertas,faixas-preco,centros-custo}/` · Cotação: `/api/scm/{demandas,itens-demanda,cotacoes,propostas,itens-proposta}/` (+ `POST demandas/:id/publicar/`, `POST cotacoes/:id/adjudicar/`) · Pedido: `/api/scm/{pedidos,itens-pedido,recebimentos,avaliacoes}/` (+ `POST pedidos/comprar_direto/`, `POST pedidos/gerar_de_cotacao/`). Contrato e permissões `scm.*` em [moduloscm.md](modulos/moduloscm.md) |
| Diário | `GET/POST /api/diario/diarios/` · `/api/diario/entradas/` · `/api/diario/documentos/` |
| IA | `GET /api/ia/analises/` · `GET /api/ia/analises/:id/` |
| Calendário | `GET/POST /api/calendar/events/` |
| Plano/quotas | `GET /api/plano/` (plano vigente + medidores + catálogo). O **402** `quota_excedida` pode voltar de qualquer criação de empreendimento/obra/cliente/fornecedor e de `POST /iam/usuarios/` — ver §5.16 |

---

## 8. Estrutura de arquivos (`src/`)

Legenda: ✅ existe · 📋 planejado

```
src/
├── main.tsx                          ✅ entry; wraps <AuthProvider>
├── App.tsx                           ✅ BrowserRouter + Routes (/ /login /app/*)
├── api/
│   └── apiClient.ts                  ✅ axios instance; interceptor Bearer
├── contexts/
│   ├── AuthContext.tsx               ✅ auth, modules, loading, login, logout, hasModule
│   └── ThemeContext.tsx              ✅ tema Malha: light/dark/system, data-theme, persistência (Malha v1)
├── hooks/
│   ├── useAuth.ts                    ✅ consumer do AuthContext
│   ├── useTheme.ts                   ✅ consumer do ThemeContext (preference/resolved/toggle)
│   └── useFileUpload.ts              ✅ upload c/ progresso + download autenticado + config da API
├── components/
│   ├── PrivateRoute.tsx              ✅ guard de autenticação
│   ├── ModuleRoute.tsx               ✅ guard de entitlement de módulo (hasModule) — tela amigável se não contratado
│   ├── AccessNotice.tsx              ✅ tela reutilizável de acesso negado (módulo/permissão)
│   ├── ThemeToggle.tsx               ✅ botão claro/escuro (gesto de marca)
│   ├── brand/                        ✅ marca Malha: Quarteirao (marco), BairroRecorte (motivo), EdicaoChip (estágio)
│   ├── malha/                        ✅ design system: Card, Pill (estado), Num (mono tabular), KpiCard + index (barrel)
│   ├── layout/
│   │   ├── LandingHeader.tsx         ✅ header fixo da landing (logo, nav, CTA)
│   │   ├── LandingFooter.tsx         ✅ footer da landing
│   │   ├── AppShell.tsx              ✅ sidebar + topbar + <Outlet />
│   │   ├── AppSidebar.tsx            ✅ sidebar de marca Malha (lockup+régua+Bairro, quarteirão aceso, colapsável)
│   │   └── AppTopbar.tsx             ✅ topbar glass: breadcrumb + chip de estágio + ThemeToggle + sino + user
│   ├── HomeSections/                 ✅ seções da landing page
│   │   ├── HeroSection.tsx
│   │   ├── ModulesSection.tsx
│   │   ├── SocialProofSection.tsx
│   │   ├── SecuritySection.tsx
│   │   └── FinalCTASection.tsx
│   ├── data/                         📋 DataTable, EmptyState, LoadingSkeleton
│   ├── obra/                         📋 StatusBadge, KpiCard, ObraCard, GanttBar, MapaObra
│   ├── ia/                           📋 AnaliseCard, AnaliseStatus
│   └── shared/                       📋 UploadZone, CurrencyDisplay
├── pages/
│   ├── LandingPage.tsx               ✅ / (pública) — 5 seções
│   ├── LoginPage.tsx                 ✅ /login — dois painéis navy+branco
│   └── app/
│       └── AppHomePage.tsx           ✅ /app/dashboard — hub de módulos com entitlement
├── modules/
│   ├── empreendimentos/              ✅ (04/06/2026)
│   │   ├── hooks/
│   │   │   ├── useEmpreendimentos.ts ← lista com filtro client-side (busca + status)
│   │   │   └── useEmpreendimento.ts  ← detalhe + contas + custos; create/update/delete
│   │   ├── components/
│   │   │   ├── EmpreendimentoStatusBadge.tsx
│   │   │   └── EmpreendimentoForm.tsx ← sheet c/ CNPJ (utils/masks), fone e moeda; fix close drag
│   │   └── pages/
│   │       ├── EmpreendimentosListPage.tsx  ← /app/empreendimentos
│   │       └── EmpreendimentoDetailPage.tsx ← /app/empreendimentos/:id (4 abas + modal excluir)
│   ├── obras/                        ✅ (04/06/2026)
│   │   ├── hooks/
│   │   │   ├── useObras.ts           ← lista; filtro servidor (empreendimento_id) + cliente (search, status)
│   │   │   └── useObra.ts            ← detalhe; fetch paralelo etapas+docs; CRUD obra/etapa
│   │   ├── components/
│   │   │   ├── ObraStatusBadge.tsx
│   │   │   ├── ObraForm.tsx          ← sheet; select empreendimento; máscara moeda
│   │   │   └── EtapaForm.tsx         ← sheet; slider % conclusão; ordem; máscara moeda
│   │   └── pages/
│   │       ├── ObrasListPage.tsx     ← /app/obras (3 filtros: busca, status, empreendimento)
│   │       └── ObraDetailPage.tsx    ← /app/obras/:id (KPIs + barra progresso + 3 abas)
│   ├── clientes/                     ✅ 04/06/2026
│   ├── fornecedores/                 ✅ 05/06/2026
│   ├── erp/                          ✅ Fundação UI (D.1.0) + Contas a pagar/receber (D.1.1) 07/06/2026 — modelo próprio, ver moduloerp.md §5
│   │   ├── routes.tsx                ← sub-rotas-irmãs lazy/Suspense (code-splitting; não aninhadas)
│   │   ├── types.ts                  ← payload da API (strings) + tipos normalizados p/ UI
│   │   ├── api/
│   │   │   ├── erpClient.ts · queryKeys.ts (fábrica `erpKeys`)
│   │   │   └── endpoints/            ← contasAPagar, contasAReceber, centrosCusto, lotesRemessa, dashboard
│   │   ├── hooks/                    ← useContasAPagar/useContasAReceber (query+mutations+useDarBaixa),
│   │   │                                useCentrosCusto, useLotesRemessa, useEntityOptions, useErpDashboard
│   │   ├── components/
│   │   │   ├── shared/               ← FilterBar, FinanceDataTable, Sheet (slide-over, 1º uso),
│   │   │   │                            MoneyInput, MoneyDisplay, KpiCard, StatusContaBadge
│   │   │   ├── forms/                ← ContaPagarForm/ContaReceberForm/BaixaForm/RateioField/FormField
│   │   │   │                            (RHF + zod, 1º uso no projeto) · schemas.ts · formStyles.ts
│   │   │   └── charts/               ← FluxoCaixaChart, AgingChart (Recharts)
│   │   └── pages/
│   │       ├── ErpDashboardPage.tsx  ← /app/erp (hub: KPIs + gráficos + cards p/ workspaces)
│   │       ├── ContasAPagarPage.tsx  ← /app/erp/contas-a-pagar   (workspace: listão + Sheet)
│   │       └── ContasAReceberPage.tsx← /app/erp/contas-a-receber (idem, espelhado)
│   ├── rh/                           ✅ 06/06/2026
│   │   ├── hooks/
│   │   │   ├── useCargos.ts          ← CRUD de Cargo
│   │   │   ├── useFuncionarios.ts    ← lista de Funcionario
│   │   │   └── useFuncionario.ts     ← detalhe + 7 sub-recursos (incl. asos); Promise.allSettled; 403 flags
│   │   ├── components/
│   │   │   ├── CargoForm.tsx         ← modal criar/editar Cargo
│   │   │   ├── FuncionarioForm.tsx   ← sheet criar/editar Funcionario (5 seções)
│   │   │   ├── DadoMedicoForm.tsx    ← sheet rh_medico (dados de saúde gerais, 1-para-1: emergência, tipo sanguíneo)
│   │   │   ├── ASOForm.tsx           ← sheet rh_medico (ASO — registro múltiplo, 1 por exame/ano; upload de arquivo)
│   │   │   ├── DadoBancarioRHForm.tsx← modal rh_financeiro (conta + PIX)
│   │   │   ├── PagamentoForm.tsx     ← modal rh_financeiro (descontos, adicionais, líquido)
│   │   │   └── FolhaPagamentoForm.tsx← modal rh_financeiro (folha mensal)
│   │   └── pages/
│   │       ├── FuncionariosListPage.tsx  ← /app/rh
│   │       ├── CargosPage.tsx            ← /app/rh/cargos
│   │       └── FuncionarioDetailPage.tsx ← /app/rh/:id (4 abas)
│   ├── crm/                          📋 Fase D.3
│   ├── diario/                       ✅ 06/06/2026
│   ├── drone/                        📋 Fase E.1
│   └── calendario/                   📋 Fase E.2
├── types/
│   └── index.ts                      ✅ Empreendimento, Obra, EtapaObra, DocumentoObra + domínio
├── utils/
│   ├── formErrors.ts                 ✅ parseApiErrors · FieldError · FormErrorBanner (erros inline por campo)
│   ├── masks.ts                      ✅ maskCPF/CNPJ/PIS · validateCPF/CNPJ/PIS · formatCPF/CNPJ/PIS
│   ├── dates.ts                      ✅ maskDate · parseDateBR · dateFromBR/ToBR · min/maxISO · validateISO_* · validateDataNasc/Admissao/Demissao
│   ├── fileUpload.ts                 ✅ validateFile · uploadFile · downloadFile · buildAcceptAttr · UploadConfig
│   └── money.ts                      ✅ 07/06/2026 — formatBRL · maskMoney · digitsToCents · centsToApiDecimal · apiDecimalToCents (centavos inteiros, D.1.0)
└── lib/
    ├── utils.ts                      ✅ cn() helper
    └── queryClient.ts                ✅ 07/06/2026 — instância TanStack Query (staleTime 60s, retry 1) — `QueryClientProvider` em `main.tsx`
```

---

## 9. Dependências do `package.json`

### Estado atual (07/06/2026)

```json
"dependencies": {
  "@hookform/resolvers": "^5.4.0",
  "@tanstack/react-query": "^5.101.0",
  "@tanstack/react-table": "^8.21.3",
  "axios": "^1.7.9",
  "class-variance-authority": "^0.7.1",
  "clsx": "^2.1.1",
  "date-fns": "^4.1.0",
  "lucide-react": "^0.460.0",
  "react": "^19.1.1",
  "react-dom": "^19.1.1",
  "react-hook-form": "^7.77.0",
  "react-is": "^19.2.7",
  "react-router-dom": "^7.1.1",
  "recharts": "^3.8.1",
  "tailwind-merge": "^2.6.0",
  "zod": "^4.4.3"
}
```

> **Adicionadas em 07/06/2026 (D.1.0/D.1.1 — fundação UI + Contas a pagar/receber do ERP,
> [§5.3](modulos/moduloerp.md#53-stack-adicional-estende-o-do-projeto)):**
> `@tanstack/react-query` (estado de servidor/cache/invalidação — o "upgrade central"),
> `@tanstack/react-table` (data-grid headless server-side), `recharts` (gráficos financeiros),
> `react-hook-form` + `zod` + `@hookform/resolvers` (**1º uso em D.1.1** — `ContaPagarForm`/
> `ContaReceberForm`/`BaixaForm` com `useFieldArray` para rateio por centro de custo).
> `react-is` foi adicionada à parte — é peer dependency (não declarada) do `recharts`; sem ela o
> `vite build` falha com `Rollup failed to resolve import "react-is"`.

### Removidas (eram bloqueadores)

```
leaflet / react-leaflet / @types/leaflet  → react-leaflet@4.x incompatível com react@19
frappe-gantt                              → Gantt será implementado com CSS/div (GanttBar)
react-hot-toast                           → removido; feedback via estado local por enquanto
```

### A adicionar quando necessário

```
react-leaflet@5 (ou maplibre-gl)  → quando MapaObra for implementado
@radix-ui/react-* (via shadcn)    → quando componentes shadcn específicos forem instalados
```

---

## 10. Fases de construção (A–F)

O rebuild acontece **módulo a módulo**, em fases nomeadas por letra. O **status vivo** de cada uma
está na [tabela de frontend do roadmap](roadmap.md#estado-dos-módulos--frontend-react-08062026) —
aqui só a definição do escopo:

| Fase | Escopo |
|---|---|
| A | Fundação — Tailwind, `AuthContext`, `AppShell`, roteamento |
| B | Landing + Login + Hub de módulos |
| C | Core — Dashboard de KPIs (C.1) · Empreendimentos (C.2) · Obras (C.3) · Clientes (C.4) · Fornecedores (C.5) · Diário+IA (C.6) |
| D | Módulos pagos — ERP `erp_financeiro` (D.1.x, sub-fases em [moduloerp.md §13](modulos/moduloerp.md#13-roadmap-em-sub-fases-fase-d1x)) · RH `rh` (D.2) · CRM `crm` (D.3) · **SCM `scm` (D.4 — backend ✅; sub-fases S.1–S.4 em [moduloscm.md](modulos/moduloscm.md#frontend-fase-atual--escopo-e-sub-fases))** |
| E | Extras — Drone wrapper iframe+SSO (E.1) · Calendário (E.2) · SIL/PDCA/DMS/Prancheta/Maps (E.3, aguarda backend) |
| F | Dashboard de KPIs real substitui o hub (F.1) |
| G | Paywall — medidores de quota, tratamento global do 402 e página de plano (§5.16). Independe de A–F: o backend já trava e já serve o medidor. |

---

## 11. Convenções de código

Vivem em [**frontend-convencoes.md**](frontend-convencoes.md) — leitura obrigatória antes de tocar o
frontend: convenções gerais, erros de formulário, máscaras CPF/CNPJ/PIS, datas, upload/download,
botões inativos e o procedimento para ativar um módulo concluído.
