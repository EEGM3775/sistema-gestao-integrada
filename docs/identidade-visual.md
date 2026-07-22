# Identidade visual — Sistema Malha v1

> **Planta** da identidade da plataforma: conceito, marco, wordmark, arquitetura de marca, cor,
> tipografia, motivo gráfico, voz e aplicações. Vale para **todas as superfícies** — app, landing,
> portais, e-mails, selo público e materiais de venda. O princípio que a organiza:
> **a identidade nasce completa no lançamento** — ela é dimensionada pela visão de expansão
> ([expansão/01-visao.md](expansão/01-visao.md)), não pelo estado atual do produto; cada edição
> vertical e cada módulo futuro **já têm endereço** no sistema, e lançar uma vertical nova
> **nunca exige rebrand**. Protótipo navegável de referência:
> [identidade-visual-prototipo.html](identidade-visual-prototipo.html) (abrir no browser; **uma
> tela só, de propósito**: o sistema da identidade, demonstrado dentro do shell que já veste a
> linguagem — sidebar de marca, topbar, temas claro/escuro. Telas de produto não vivem aqui:
> **cada edição terá o seu hub** e os seus módulos, todos formados sobre este corpo).

## 1. O conceito — "Do terreno à cidade"

A marca **não** é a de um sistema de gestão de obra. É a da **plataforma onde o mercado imobiliário
inteiro opera**: construtoras, lojas, imobiliárias, empreiteiros, escritórios de projeto e
administradoras trabalhando no mesmo grafo ([expansão/README.md](expansão/README.md)).

- **Imagem-mãe:** a **cidade viva, vista de cima** — a malha urbana à noite, onde **cada luz é uma
  empresa trabalhando**. É o efeito de rede transformado em imagem: o produto final do setor é a
  cidade, e a plataforma é onde ela acontece. (A vista zenital também herda, sem dependência, o
  diferencial do drone.)
- **Tagline oficial:** **"Do terreno à cidade."** — resume o ciclo de vida coberto
  (terreno → viabilidade → obra → venda → operação) e a ambição da plataforma numa linha.
- **Por que não uma identidade "de canteiro":** amarrar a marca à obra limitaria as edições que não
  constroem (imobiliária, administradora, escritório). A cidade contém todas.

## 2. O marco — o Quarteirão

Quatro avenidas girando ao redor de uma praça central. **Três leituras no mesmo desenho:**

1. Um **quarteirão de cidade planejada** (a vista de cima da imagem-mãe);
2. O **flywheel** da autossustentação do ecossistema
   ([expansão/10-rede-social-do-setor.md §4](expansão/10-rede-social-do-setor.md));
3. Os **quatro estágios do ciclo de vida** do empreendimento, sempre em sentido horário:
   **Originar → Construir → Negociar → Operar**. A praça central é a **plataforma**.

### 2.1 Geometria (fonte única)

SVG em `viewBox="0 0 96 96"`; braços de espessura 16, folga de 4 entre braços, praça 14×14:

```svg
<svg viewBox="0 0 96 96">
  <rect x="12" y="12" width="16" height="50" fill="#3E9C6E"/>  <!-- Originar  (esquerda) -->
  <rect x="32" y="12" width="52" height="16" fill="#E79A22"/>  <!-- Construir (topo)     -->
  <rect x="68" y="32" width="16" height="52" fill="#E4655F"/>  <!-- Negociar  (direita)  -->
  <rect x="12" y="68" width="52" height="16" fill="#1D9AA6"/>  <!-- Operar    (base)     -->
  <rect x="41" y="41" width="14" height="14" fill="#0A1626"/>  <!-- praça = a plataforma -->
</svg>
```

A praça usa **Meia-Noite** sobre fundo claro e **Papel de Planta** sobre fundo escuro
(no app, `var(--ink)` acompanha o tema).

### 2.2 Variantes

| Variante | Composição | Uso |
|---|---|---|
| **Plataforma** (padrão) | 4 cores do ciclo + praça | Marca-mãe, landing, materiais da plataforma |
| **Institucional** | Tudo em Navy Cívico `#0A2A5B` | Documentos, carimbo, contextos monocromáticos |
| **Noturna** | Avenidas em Papel `#F5F7FA`, praça âmbar, sobre Meia-Noite | Fotografia, heros escuros, selo público |
| **De edição** | Só a avenida da edição acesa; demais em cinza-planta `#C3CBD6`; praça na cor de tinta | Sub-marcas, ícones de app por edição |
| **Micro** (≤ 20px) | Sem praça, braços engrossados (x/y 6, espessura 20, comprimento 58) | Favicon, badges pequenos |

### 2.3 Regras de uso

- O giro é **sempre horário** — o sentido do ciclo de vida. Nunca rotacionar, espelhar ou inverter.
- A **praça nunca recebe cor de edição** — ela é a plataforma, não uma vertical.
- Cada edição **acende a sua avenida**; as demais ficam em cinza-planta. Nunca duas acesas.
- Sobre fotografia: variante noturna sobre véu Meia-Noite (nunca o marco pleno direto na foto).
- Área de proteção: 1 braço de espessura (16/96 do lado) livre em todo o perímetro.

## 3. Wordmark

**"SGI" desenhado como avenidas de um mapa** — strokes grossos com terminais redondos — com
**nós de luz** nas quatro cores do ciclo nos extremos/cruzamentos (os participantes que a rede
conecta). Fonte única em `viewBox="0 0 300 112"`, `stroke-width="15"`, `stroke-linecap="round"`:

```svg
<path d="M80 28 H48 Q28 28 28 46 Q28 62 48 62 H62 Q84 62 84 80 Q84 96 62 96 H30"/>  <!-- S -->
<path d="M186 34 Q176 24 156 24 Q124 24 124 60 Q124 96 156 96 Q182 96 184 74 V66 H158"/> <!-- G -->
<path d="M224 24 V96"/>                                                                <!-- I -->
<circle cx="80"  cy="28" r="6.5" fill="#E79A22"/>  <circle cx="30"  cy="96" r="6.5" fill="#3E9C6E"/>
<circle cx="158" cy="66" r="6.5" fill="#E4655F"/>  <circle cx="224" cy="24" r="6.5" fill="#1D9AA6"/>
```

- Traço em Papel `#F5F7FA` sobre Meia-Noite (uso primário) ou Navy Cívico sobre claro.
- Os **nós de luz não mudam de cor nem de posição** — são parte do desenho, não decoração.
- Em corpo de texto e UI, "SGI" se escreve em texto normal; o wordmark é peça de marca (landing,
  hero, materiais), não substituto tipográfico.

## 4. Arquitetura de marca — plataforma e edições

**Cor é endereço, não decoração.** A plataforma é Meia-Noite + Papel; **cada edição usa a cor do
estágio do ciclo que habita**. É esta regra que elimina o rebrand futuro: a cor de cada vertical
está reservada antes de a vertical existir.

| Estágio | Cor | Edições/módulos com este endereço |
|---|---|---|
| **Originar** | Verde Terreno `#3E9C6E` | Edição Escritório de Projeto; banco de terrenos, viabilidade, licenciamento |
| **Construir** | Âmbar Obra `#E79A22` | **Edição Construtora (o produto atual)**, Edição Empreiteiro, Edição Loja; obra, SCM, diário, drone |
| **Negociar** | Coral Lançamento `#E4655F` | Edição Imobiliária/corretor; espelho de vendas, reservas, comissões |
| **Operar** | Teal Operação `#1D9AA6` | Edição Administradora; assistência técnica, condomínio, facility |
| — praça — | tinta do tema | **Portais do consumidor** (comprador, investidor, morador): quem não compra sistema entra pelo espaço público da plataforma |

- **Sub-marca de edição (lockup):** marco na variante de edição + "SGI" + nome da edição com o nome
  na cor do estágio (ex.: "SGI **Imobiliária**" em coral). Ver protótipo, aba Identidade →
  Aplicações.
- Consequência prática já vigente: **o produto atual usa âmbar como acento porque a Edição
  Construtora vive no estágio Construir** — não porque "âmbar é a cor do SGI".
- As 4 cores juntas (**a régua do ciclo**) só aparecem em contexto de **plataforma** — marca, rede,
  feed, landing. Dentro de uma edição, vale a cor dela. Como elemento gráfico, a régua é um filete
  de `3px` com o gradiente dos 4 estágios (25% cada, na ordem do ciclo) — usada sob o lockup da
  marca no sidebar; é a assinatura de plataforma dentro do produto.

## 5. Cor

### 5.1 Paleta da marca

| Nome | Hex | Papel |
|---|---|---|
| **Meia-Noite** | `#0A1626` | O céu da cidade. Fundo da marca, heros, superfícies de rede. Evolução profunda do navy da v01 |
| **Papel de Planta** | `#F5F7FA` | O papel do trabalho diário. Neutros sempre com viés de azul — nunca cinza puro |
| **Navy Cívico** | `#0A2A5B` | Herança v01 — a cor institucional dentro do produto (sidebar, CTAs institucionais, documentos) |
| **Verde Terreno** | `#3E9C6E` | Estágio Originar |
| **Âmbar Obra** | `#E79A22` | Estágio Construir (acento do produto atual) |
| **Coral Lançamento** | `#E4655F` | Estágio Negociar |
| **Teal Operação** | `#1D9AA6` | Estágio Operar |
| Cinza-planta | `#C3CBD6` | Avenidas apagadas na variante de edição |

### 5.2 Semânticos de UI (separados da marca)

Estados de interface **nunca** reutilizam as cores de estágio como significado e sempre vêm com
rótulo (nunca cor sozinha):

| Papel | Light | Dark |
|---|---|---|
| Aprovado/concluído (`--good`) | `#1F9D74` | `#37C293` |
| Em andamento/informativo (`--info`) | `#3B7DD8` | `#5C97E6` |
| Erro/cancelado (`--danger`) | `#D8434B` | `#EF6169` |
| Rede/IA (`--net`) | `#0F8A93` | `#2BB6BF` |

### 5.3 Tokens de interface (linguagem premium do produto)

O produto tem **tema claro e escuro** desde o desenho (custom properties; o toggle do usuário
sobrepõe o `prefers-color-scheme`). Principais tokens (valores completos no protótipo):

| Token | Light | Dark | Papel |
|---|---|---|---|
| `--ground` | `#E6EAF1` | `#0A1626` | Fundo da área de conteúdo (papel suave / Meia-Noite) |
| `--surface` | `#F5F7FA` | `#13233C` | Cartões e superfícies — **sem branco puro** (conforto ocular; o Papel de Planta é o teto de claridade) |
| `--surface-2` / `--inset` | `#ECF0F6` / `#E2E7F0` | `#1B2F4E` / `#0E1C30` | Superfícies secundárias/rebaixadas |
| `--ink` / `--ink-2` / `--ink-3` | `#0C1A30` / `#3C4B64` / `#5D6B80` | `#EDF2F9` / `#B7C3D6` / `#8797AE` | Texto: primário/secundário/mudo |
| `--line` / `--line-2` | `#DEE4EC` / `#EAEEF4` | `#2C4265` / `#213551` | Bordas e divisores |
| `--brand` | `#0A2A5B` | `#2E5EAE` | Navy Cívico (clareia no escuro p/ contraste) |
| `--accent` / `--accent-strong` | `#E79A22` / `#A85F0D` | `#F2AC46` | Acento do estágio da edição ativa; o `strong` é a variante **texto** |
| `--st-orig` / `--st-const` / `--st-neg` / `--st-oper` | `#25714B` / `#9A5E0B` / `#BE4038` / `#0F7280` | `#6BCB9C` / `#F2AC46` / `#F0918B` / `#54C6D1` | Cores de estágio **seguras para texto** (rótulos, nomes de edição) |

**Regra de contraste:** a cor viva do estágio (§5.1) vale para **superfícies, bordas e pontos**;
texto em cor de estágio usa sempre os tokens `--st-*` (escurecidos no claro, clareados no escuro).
Deltas e variações (▲/▼) usam os `--*-ink` semânticos, nunca a cor viva. Texto mudo (`--ink-3`)
mira ≥ 4.5:1 sobre `--surface` nos dois temas.

Regras de aplicação no produto:

- **Um acento por tela** — o acento (âmbar na Edição Construtora) marca exclusivamente
  "requer sua decisão / recomendado / CTA primário". Tela sem acento = nada exige o usuário.
- Raio de borda: 7/11/16/22px (`--r-sm/md/lg/xl`); sombras discretas em 3 níveis; glass
  (blur + transparência) só na topbar.

## 6. Tipografia — letreiro e instrumento

| Papel | Face | Uso |
|---|---|---|
| **Display — o letreiro** | **Archivo** (Expanded em peças de marca) | Títulos de marca e de página; peso 750–800, tracking fechado (−0.02em). A letra dos letreiros urbanos |
| **Texto — o produto** | **Inter** | Corpo, formulários, tabelas. Uma família só, do portal do comprador ao ERP |
| **Dados — o instrumento** | **JetBrains Mono** | **Todo dado**: preço, quantidade, código, prazo, documento — sempre com `font-variant-numeric: tabular-nums` |

- Archivo/Inter/JetBrains Mono **substituem Montserrat/Roboto** (herdadas da v01) no lançamento da
  identidade; [frontend.md §1](frontend.md) aponta para cá como fonte única.
- Rótulos de campo/eixo: caps, 10–11px, tracking largo (+0.10em), peso 650–700, sempre **acima**
  do valor.
- Números em coluna alinham à direita, em mono tabular — "colunas como réguas" é requisito, não
  estilo.
- Fallback stacks: `Archivo, ui-sans-serif, system-ui, sans-serif` ·
  `Inter, ui-sans-serif, system-ui, sans-serif` ·
  `"JetBrains Mono", ui-monospace, "Cascadia Code", Menlo, Consolas, monospace`.

## 7. Motivo gráfico — o Bairro (dia e noite)

O motivo de marca é **um tecido urbano desenhado como os urbanistas desenham cidade**: o mapa
**figure-ground** (Nolli) — quarteirões cheios (*poché*), **ruas como vazios**. Referências do
método: a identidade do Porto (Studio Eduardo Aires — sistema geométrico composto numa grelha
contínua) e a tradição figure-ground do desenho urbano. **Não é gerado nem foto: é uma composição
única, desenhada à mão** — a mesma geometria em todas as superfícies.

**A regra-mestra: uma geometria, duas vidas.** O Bairro acompanha o tema do sistema:

| | ☀️ Dia (tema claro) | 🌙 Noite (tema escuro) |
|---|---|---|
| Leitura | O **mapa de zoneamento** sobre papel | A mesma cidade **anoitecendo** |
| Quarteirões | Tons de planta (`--city-block/-2`) | Massas escuras sobre Meia-Noite |
| **Distritos do ciclo** | **Pastel de zoneamento** (tintas suaves das 4 cores) | **Acesos nas cores vivas do marco** |
| Sombras | **Sombra de sol** dura (`drop-shadow 5×7px`, sem blur) caindo nas ruas | — |
| Janelas | Invisíveis (`--city-window: 0`) | **Acesas** em âmbar (`0.92`) |
| Ruas | Vazios de papel, recebem as sombras | Ganham **brilho âmbar** (`--city-glow`) |
| Distrito Construir | Pastel âmbar no plano | Âmbar vivo **com halo** (glow) |

O dia **não é a noite clareada**: cada turno tem elemento próprio (sombra ↔ luz).

- **Anatomia da composição** (SVG `#cityFabric`, 560×380, definido uma vez e recortado por
  `<use>` + `viewBox`): malha **irregular com ruas generosas** — locais de **16px**, quarteirões
  de 56 a 128px em dois tons alternados e **de formas variadas** (retângulos chanfrados, lotes em
  "L", trapézios e pentágonos — nenhum idêntico ao vizinho; a irregularidade é o que dá leitura de
  cadastro urbano real, não de grade), **interseções em T** (os eixos de cada fileira não se
  alinham; é o que separa tecido urbano de grade de jogo); **boulevard horizontal de 34px com
  canteiro central verde tracejado**; no **centro exato**, a **praça-rotatória verde** (gramado
  r=44 com **miolo em `--ink`** — a plataforma), que **nada sobrepõe**: os quarteirões centrais
  encurtam para lhe dar adro. Ao redor dela, **os 4 distritos nas cores do ciclo em giro horário**
  (verde no alto-esquerdo → âmbar no alto-direito → coral embaixo-direito → teal
  embaixo-esquerdo) — **o cata-vento do marco na escala da cidade**. À noite acendem as guias do
  boulevard e o **anel da rotatória**; nada de cortes mascarados — toda via é desenhada, não
  recortada.
- **Tokens** (por tema): `--city-block`, `--city-block2`, `--city-park`, `--city-tree`,
  `--city-zorig/zconst/zneg/zoper` (distritos), `--city-window` (janelas), `--city-glow`
  (brilho de rua/halo), `--city-shadowf` (filtro de sombra de sol — `none` à noite).
- **Usos:** hero da identidade (recorte grande à direita, máscara de fade sob o texto), sidebar
  (recorte do quadrante da empresa, ancorado no rodapé, fade no topo), login e capas.
- **Proibições:** nunca redesenhar o tecido por superfície (é sempre recorte do mesmo
  `#cityFabric`); **um** quarteirão-empresa por composição; nunca sob tabela ou formulário denso;
  sem animação (o "movimento" da marca é o próprio anoitecer via tema).

Leitura do motivo: *o mercado inteiro no mesmo tecido — cada edição é um distrito, a praça é a
plataforma* — e o alternador de tema vira gesto de marca: **a cidade amanhece e anoitece com o
usuário**; de dia se planeja (zoneamento e sombras), à noite se vê quem está aceso.

## 8. Voz — fato, não adorno

A plataforma escreve como quem registra fato verificável (a tese do feed de fatos):

| Regra | ✓ Faça | ✗ Não faça |
|---|---|---|
| **Número com unidade e origem** | "R$ 47.320 economizados em 12 cotações — julho" | "Economia incrível este mês!" |
| **Botão diz a ação** | "Adjudicar" → toast "Cotação #142 adjudicada" | "OK" · "Confirmar?" · "Deseja prosseguir?" |
| **Estado nomeado e medido** | "recebido parcial · 60 de 120 kg conferidos" | "pendente…" |

Erros dizem o que aconteceu e como resolver, sem desculpas nem vagueza. Editorial é permitido em
peças de marketing, mas **rotulado** — nunca misturado a dado operacional.

## 9. Aplicações

| Peça | Especificação |
|---|---|
| **Ícone do app / PWA** | Marco pleno (4 cores, praça em Papel) sobre tile Meia-Noite→`#122340`, raio ~24%. Apps de edição: variante de edição no mesmo tile |
| **Favicon** | Variante micro |
| **Selo público "Obra ao vivo no SGI"** | Chip Meia-Noite: marco de edição (avenida âmbar acesa) + "OBRA AO VIVO NO SGI" + linha mono com obra/percentual. É o widget do flywheel — a construtora embute no site dela |
| **Sidebar do app** | **Acompanha o tema** (fundo `--surface`, textos `--ink-*`, divisores `--line`); no rodapé, **recorte do Bairro** (§7) com o quarteirão-empresa âmbar — de dia masterplan, de noite janelas acesas — com fade no topo; marco 34px (praça em `--ink`) + lockup + **régua do ciclo**; item ativo = **quarteirão aceso** (bloco âmbar 8px com anel suave, fundo `--accent-soft`) |
| **Cabeçalho de módulo** | Título + **chip da edição/estágio** (ex.: "Edição Construtora · Construir" em âmbar-soft) — toda tela declara seu endereço no ciclo |
| **Hub da edição (padrão de página)** | **Cada edição tem o seu hub** — este é o padrão que todos seguem: faixa Meia-Noite com malha viva (saudação + badge da edição + números vivos); módulos agrupados **pelo endereço no ciclo**, com os futuros já exibindo casa e horizonte (H2/H3); lista "requer sua decisão" numerada no acento da edição; feed de **fatos verificados**. O primeiro a construir é o da Edição Construtora (dashboard F.1 do [roadmap](roadmap.md)) |
| **Sub-marca de edição** | Lockup: marco de edição + "SGI" + nome da edição na cor do estágio (texto usa `--st-*`, §5.3) |
| **E-mail** ([funcoesemail/](../funcoesemail/)) | Cabeçalho Meia-Noite com marco noturno; corpo claro; dados em mono |

## 10. Aplicação no produto (transição)

- **O shell React já roda na Malha v1** ([frontend.md §1](frontend.md), §3): tokens de tema claro/escuro,
  fontes Archivo/Inter/JetBrains, sidebar de marca (marco + régua + Bairro), topbar glass (breadcrumb +
  chip de estágio + toggle de tema) e os primitivos-base em `components/malha/` (`Card`, `Pill` de estado,
  `Num` de instrumento, `KpiCard`). O ⌘K/command palette ficou **fora por ora** (sem busca cross-entidade —
  ver **F2**); o flow rail nasce com o SCM. Os **módulos legados** acompanham o tema por aliases de
  compatibilidade e migram para os tokens nativos **um a um**; **módulos novos nascem na Malha v1** — o
  primeiro é o frontend do **SCM** (fase D.4/S.1 do [roadmap](roadmap.md)), sobre esta fundação.
- O [protótipo](identidade-visual-prototipo.html) é o **alvo visual**: a implementação React replica o que
  está lá, não reinterpreta. As telas de produto (hubs por edição, cabeçalho de módulo com chip, módulos)
  seguem as especificações do §9 ao nascer.
- O acento âmbar já usado no produto é **coerente por construção** (estágio Construir) — a migração
  não muda a cor do dia a dia da Edição Construtora, muda a fundação (tokens, tipografia, tema
  escuro, componentes).
- Convenções de código do frontend continuam em
  [frontend-convencoes.md](frontend-convencoes.md); esta planta define **o que** a UI expressa,
  não **como** se escreve React.

## 11. Anti-padrões (o que a marca nunca faz)

- As 4 cores do ciclo juntas dentro de uma edição (régua completa = só contexto de plataforma).
- Cor de estágio usada como semântica de UI (verde de "Originar" ≠ verde de "aprovado").
- Marco girado, espelhado, com praça colorida de edição ou com duas avenidas acesas.
- Gradientes fora do céu Meia-Noite; foto de banco de imagem como fundo de marca.
- Número sem unidade; percentual sem base; "carregando…" sem dizer o quê.
- Cinza puro (neutros sempre com viés de azul); acento repetido em mais de uma ação por tela.
