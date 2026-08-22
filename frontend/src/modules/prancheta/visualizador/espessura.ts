/**
 * Espessura de traço constante na tela — o fio de cabelo do CAD.
 *
 * **O problema.** A prancha é um `<img>` escalado por `transform`, então o traço
 * amplia junto com o desenho: a 20× o que era um fio vira uma tarja, e o detalhe
 * que a pessoa ampliou para conferir fica coberto pela própria linha que queria
 * ver. É o oposto do CAD, onde ampliar aumenta o desenho e **não** o traço.
 *
 * **Por que dá para consertar sem abrir mão do `<img>`.** O `ezdxf` emite a
 * espessura em **classes CSS no cabeçalho** — `.C1 { stroke-width: 4167 }` —, uma
 * por combinação de cor e espessura, e não em cada `<path>`. São algumas centenas
 * de bytes no começo do arquivo, qualquer que seja o tamanho do desenho. Dá para
 * reescrever só esse pedaço e remontar o blob; o corpo do SVG, que pode ter 10 MB,
 * nunca é tocado nem copiado — o `Blob` aceita as partes em lista.
 *
 * **A hierarquia sobrevive onde ela existe.** As larguras são renormalizadas
 * mantendo a razão entre elas: a mais fina vira ~1 px e as outras acompanham, com
 * teto. No desenho penado por cor (3 de 4 do acervo medido, onde toda camada é
 * `DEFAULT`) existe uma largura só, e o resultado é fio de cabelo uniforme — que é
 * exatamente o que o AutoCAD mostra no modelspace com exibição de espessura
 * desligada. No desenho que declara espessura de verdade, parede continua mais
 * grossa que cota.
 */

/** Espessura, em pixels de tela, da linha mais FINA do desenho. */
const PX_MAIS_FINA = 1.1

/**
 * Teto da mais grossa, em pixels de tela.
 *
 * Sem teto, um desenho que declare 2,11 mm ao lado de 0,05 mm renderizaria a
 * razão de 42× — uma tarja de 46 px que engole o desenho. O CAD faz o mesmo
 * corte: espessura é dica de hierarquia, não escala física da tela.
 */
const PX_MAIS_GROSSA = 4

/** Onde os estilos moram no SVG do `ezdxf` — do primeiro `<style>` ao último. */
const ESTILO = /<style>[\s\S]*<\/style>/

export interface SvgPreparado {
  /** Tudo antes do bloco de estilos — vazio quando só a geometria foi lida. */
  antes: string
  /** Tudo depois — o corpo do desenho, que nunca é reescrito. Idem. */
  depois: string
  /**
   * As regras originais, na ordem em que apareciam.
   *
   * `largura` é `null` nas que **não se reescreve** — o `ezdxf` emite
   * `stroke-width: none` nas classes de preenchimento (hachura, sólido), e elas
   * têm de sair **verbatim**. Descartá-las foi o primeiro erro desta fatia: a
   * classe sumia do SVG remontado, o preenchimento caía no preto padrão e a
   * prancha ganhava tarjas pretas por cima do desenho — a mesma família de
   * defeito do D46, onde a folha abre, parece pronta e esconde o que importa.
   */
  regras: { classe: string; largura: number | null; corpo: string }[]
  /** Largura do `viewBox`, para converter pixel de tela em unidade do SVG. */
  viewBox: number
  /**
   * Altura do `viewBox`, na mesma unidade.
   *
   * Só o leitor de coordenadas usa — mas usa por um motivo: o `ezdxf` emite
   * **sempre** `viewBox="0 0 1000000 H"` com o H **arredondado a inteiro**,
   * enquanto o `width`/`height` em mm carrega uma casa decimal. Os dois aspectos
   * não são o mesmo número, e saber qual deles a tela está usando é a diferença
   * entre um desvio explicado e um desvio que se persegue no escuro.
   */
  viewBoxAltura: number
  /**
   * `viewBoxLargura / viewBoxAltura` — o aspecto EXATO do desenho.
   *
   * **É o que impede a mira de cair fora do traço.** O `<img>` reporta
   * `naturalWidth`/`naturalHeight` arredondados para inteiro (o SVG mede
   * 2715,21 × 1272,19 px e vira 2715 × 1272), então a caixa fica com um aspecto
   * levemente diferente do `viewBox`. Com o `preserveAspectRatio` padrão o
   * conteúdo é **centralizado** nessa caixa, sobrando uma letterbox de 0,044 px
   * — invisível no enquadramento e **multiplicada pelo zoom**: 4,4 px a 100×,
   * 44 px a 1000×. O pino não denuncia isso porque nasce de um clique e o erro
   * se cancela na ida e volta; o ponto de snap vem do servidor e não cancela.
   *
   * Dando à caixa o aspecto exato, a letterbox some e as duas normalizações — a
   * do backend (pelo `viewBox`) e a da tela (pela largura da imagem) — voltam a
   * ser a mesma conta.
   */
  aspecto: number
  /**
   * O papel que o SVG declara, em milímetros — `null` se não vier em mm.
   *
   * É o que transforma o leitor de coordenadas em régua: sem ele a barra mostra
   * fração de folha, que é exata mas não é a linguagem de quem projeta. Com ele,
   * a mesma posição sai em milímetros de papel, que é o que se confere contra a
   * prancha impressa.
   */
  papelMm: { largura: number; altura: number } | null
}

/**
 * Lê a geometria da folha e, quando dá, quebra o SVG em cabeçalho reescrevível e
 * corpo intocado.
 *
 * **O `viewBox` sobrevive mesmo quando a espessura não pode ser reescrita**, e
 * isso é conserto, não detalhe. Antes esta função devolvia `null` sempre que não
 * achasse regra de espessura numérica — e junto com o `null` a vista perdia o
 * `aspecto`, que é o que dá o tamanho exato à caixa do `<img>`. Sem caixa exata
 * o desenho volta a ser pintado com `preserveAspectRatio` sobre um retângulo de
 * lados **arredondados a inteiro** pelo próprio navegador: o conteúdo passa a
 * escalar por `naturalHeight/viewBoxAltura` em vez da razão exata, e sobra um
 * erro **relativo** de ~2×10⁻⁴, ancorado no topo da folha. Ele é invisível no
 * enquadramento, cresce proporcional à distância do topo e **é multiplicado pelo
 * zoom** — a assinatura exata do que se relatou: mira colada no traço em cima da
 * prancha, e um quadrado inteiro fora dela embaixo, em zoom alto.
 *
 * Ou seja: afinar traço é conforto e pode falhar; saber o aspecto é correção e
 * não pode. Amarrar os dois no mesmo `null` fazia a falha do conforto derrubar a
 * correção — e sem aviso nenhum, porque a prancha continuava abrindo.
 *
 * Devolve `null` só quando não há `viewBox` legível: aí não há o que dimensionar,
 * e a vista segue com o blob original.
 */
export function prepararSvg(texto: string): SvgPreparado | null {
  const caixa = texto.match(/viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)/)
  const viewBox = Number(caixa?.[1])
  const altura = Number(caixa?.[2])
  if (!viewBox || !Number.isFinite(viewBox)) return null
  if (!altura || !Number.isFinite(altura)) return null

  // O papel declarado. Só a tag `<svg …>` é varrida: o corpo pode ter 10 MB de
  // `<path>`, e um `match` global sobre ele custaria mais que tudo o que esta
  // função faz junto. **A partir do `<svg`, não do começo do arquivo** — o
  // `ezdxf` abre com `<?xml version='1.0' encoding='utf-8'?>`, e recortar até o
  // primeiro `>` pegava só o prólogo, deixando o papel sempre vazio.
  const abertura = Math.max(texto.indexOf('<svg'), 0)
  const cabecalho = texto.slice(abertura, texto.indexOf('>', abertura) + 1)
  const emMm = (atributo: string) => {
    const v = Number(cabecalho.match(new RegExp(`${atributo}="([\\d.]+)mm"`))?.[1])
    return Number.isFinite(v) && v > 0 ? v : null
  }
  const larguraMm = emMm('width')
  const alturaMm = emMm('height')

  const geometria = {
    viewBox,
    viewBoxAltura: altura,
    aspecto: viewBox / altura,
    papelMm: larguraMm && alturaMm ? { largura: larguraMm, altura: alturaMm } : null,
  }

  const bloco = texto.match(ESTILO)
  const regras: SvgPreparado['regras'] = []
  if (bloco) {
    const porRegra = /\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}/g
    let achado: RegExpExecArray | null
    while ((achado = porRegra.exec(bloco[0])) !== null) {
      const corpo = achado[2]
      const medida = Number(corpo.match(/stroke-width:\s*([\d.]+)/)?.[1])
      regras.push({
        classe: achado[1],
        // Toda regra entra, tenha ou não espessura numérica. As que não têm são
        // reemitidas exatamente como vieram — ver o comentário em `regras`.
        largura: Number.isFinite(medida) ? medida : null,
        corpo,
      })
    }
  }
  // Sem espessura numérica não há o que renormalizar: o SVG fica como veio e só
  // a geometria segue adiante. `antes`/`depois` ficam vazios de propósito — quem
  // chama `svgComEspessura` tem de checar `regras` (ver `podeAfinar`).
  if (!bloco || !regras.some((r) => r.largura !== null)) {
    return { antes: '', depois: '', regras: [], ...geometria }
  }

  const inicio = bloco.index ?? 0
  return {
    antes: texto.slice(0, inicio),
    depois: texto.slice(inicio + bloco[0].length),
    regras,
    ...geometria,
  }
}

/** Este SVG dá para afinar? Falso quando só a geometria foi aproveitada. */
export function podeAfinar(svg: SvgPreparado): boolean {
  return svg.regras.some((r) => r.largura !== null)
}

/**
 * Monta o SVG com as espessuras que rendem largura constante na tela.
 *
 * `larguraNaTela` é quantos pixels a folha inteira ocupa agora (o `escala` do
 * `Enquadramento`). Como o `viewBox` cobre essa mesma folha, a conversão é
 * direta: um pixel de tela vale `viewBox / larguraNaTela` unidades do SVG.
 */
export function svgComEspessura(
  svg: SvgPreparado, larguraNaTela: number, larguraNoAjuste: number,
): Blob {
  const unidadesPorPixel = svg.viewBox / Math.max(larguraNaTela, 1)

  /**
   * **Constante ao AMPLIAR, proporcional ao REDUZIR.**
   *
   * Segurar 1,1 px também na saída faz a prancha reduzida virar um borrão: a
   * 20% do enquadramento, uma planta densa tem mais traço que pixel, e todo
   * traço com largura de pixel inteiro se funde num bloco preto. Reduzir é
   * justamente o gesto de "ver o conjunto", e ele precisa de traço sub-pixel
   * para o conjunto aparecer.
   *
   * Acima do enquadramento o fator satura em 1 e vale o fio de cabelo do CAD.
   */
  const fator = larguraNoAjuste > 0
    ? Math.min(1, larguraNaTela / larguraNoAjuste)
    : 1
  const medidas = svg.regras
    .map((r) => r.largura)
    .filter((w): w is number => w !== null && w > 0)
  const fina = medidas.length ? Math.min(...medidas) : 1

  const estilos = svg.regras.map((r) => {
    if (r.largura === null || r.largura <= 0) {
      // Preenchimento e afins saem intactos: aqui não há traço para afinar, e
      // reescrever o corpo custaria a cor de uma hachura para não ganhar nada.
      return `<style>.${r.classe} {${r.corpo}}</style>`
    }
    // Razão preservada, teto aplicado: mantém a hierarquia sem deixar a linha
    // mais grossa virar tarja num desenho de espessuras muito espalhadas.
    const px = Math.min(PX_MAIS_FINA * (r.largura / fina), PX_MAIS_GROSSA) * fator
    // **Sem piso de uma unidade de SVG.** Era `Math.max(…, 1)`, e em zoom alto
    // uma unidade de SVG vale vários pixels — o piso passava a mandar e a linha
    // voltava a engrossar junto com o zoom, exatamente o defeito que esta
    // função existe para consertar. Aparecia na dezena de milhar por cento, que
    // é onde `unidadesPorPixel` cai abaixo de 1. Fração é válida em
    // `stroke-width`, então o único piso necessário é não ser zero.
    const largura = Math.max(px * unidadesPorPixel, 1e-6)
    const semLargura = r.corpo.replace(/stroke-width:\s*[\d.]+;?\s*/, '')
    // 6 casas: em zoom muito alto a largura cai para centésimos de unidade, e
    // `toFixed(2)` a arredondaria para 0,00 — traço nenhum na tela.
    return `<style>.${r.classe} {${semLargura}stroke-width: ${largura.toFixed(6)};}</style>`
  })

  // As partes vão em LISTA, sem concatenar: `depois` pode ter 10 MB, e juntá-lo
  // numa string nova a cada passo de zoom alocaria isso repetidamente.
  return new Blob([svg.antes, ...estilos, svg.depois], { type: 'image/svg+xml' })
}

/**
 * O degrau de zoom em que vale reescrever o SVG.
 *
 * Reescrever a cada pixel de movimento da roda seria criar e revogar um blob
 * dezenas de vezes por segundo. Como a espessura só precisa **parecer**
 * constante, degraus de ~2^(1/3) (≈26%) são imperceptíveis e cortam o trabalho
 * a um punhado de reconstruções em toda uma sessão de zoom.
 */
export function degrauDeZoom(larguraNaTela: number): number {
  if (!(larguraNaTela > 0)) return 0
  return Math.round(Math.log2(larguraNaTela) * 3)
}
