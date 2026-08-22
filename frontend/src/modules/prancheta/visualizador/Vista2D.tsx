import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { MouseEvent as EventoMouse, PointerEvent as EventoPonteiro, ReactNode } from 'react'
import { Maximize2, Minus, Plus } from 'lucide-react'
import type { Ponto } from '../types'
import { Coordenadas } from './Coordenadas'
import type { Mundo } from './Coordenadas'
import { degrauDeZoom, podeAfinar, prepararSvg, svgComEspessura } from './espessura'
import type { SvgPreparado } from './espessura'
import type { Achado } from './snap'

/**
 * Prancha 2D — SVG da derivada, imagem ou miniatura, com pan e zoom.
 *
 * **É um `<img>`, e isso é decisão de segurança, não de simplicidade.** O SVG
 * que sai do `ezdxf`/LibreDWG carrega texto vindo do arquivo do cliente;
 * injetá-lo inline no DOM (o caminho óbvio para dar zoom "vetorial de verdade")
 * executaria qualquer `<script>` que atravessasse o conversor, com a sessão de
 * quem abriu a prancha. Dentro de `<img>` o SVG é imagem: script não roda.
 *
 * **E o zoom só é vetorial se a CAIXA crescer — não o `scale()`.** Esta linha
 * antes afirmava que "o browser rasteriza no fator aplicado", e era falso: com
 * `transform: scale(z)` o navegador rasteriza o SVG UMA vez, no tamanho de
 * layout, e estica o bitmap. A 81× isso faz cada pixel do raster virar um bloco
 * de 38 px, e o traço aparece deslocado do lugar onde ele matematicamente está —
 * medido no Chromium: mediana 3,2 px e **até 17,9 px** fora. A mira, desenhada
 * na coordenada exata, ficava certa sobre um desenho pintado torto; era a
 * segunda metade do D90, a que sobrou depois de o backend estar correto.
 * Crescendo a caixa (`width`/`height` em px de tela) o vetor é re-rasterizado na
 * resolução final e o desvio some: **0,00 px de mediana, 100% em cima da linha**.
 * Custa o mesmo (33 ms por passo de zoom nos dois): o Chromium pinta o SVG por
 * tiles e só o que está visível.
 *
 * Os gestos são de **canteiro**: uma mão arrasta, duas dão pinça. Por isso tudo
 * é `PointerEvent` (mouse, caneta e dedo no mesmo caminho) e o container declara
 * `touch-action: none` — sem isso o browser do celular sequestra o arrasto para
 * rolar a página e a prancha nunca se move.
 *
 * **PRA.3 — a camada de marcação por cima.** A vista publica o *enquadramento*
 * (converter coordenada da folha em pixel de tela e vice-versa) por render prop,
 * em vez de a marcação recalcular a transformação por fora. Duas cópias da mesma
 * matriz divergiriam no primeiro ajuste de gesto, e o sintoma seria o pino a
 * dois dedos de onde alguém o colocou — o pior defeito possível numa ferramenta
 * cujo produto é apontar *onde*.
 */

/** A ponte entre a folha e a tela. `x` normalizado pela LARGURA do desenho. */
export interface Enquadramento {
  paraTela: (p: Ponto) => { x: number; y: number }
  paraDesenho: (px: { x: number; y: number }) => Ponto
  /** Pixels de tela por 1,0 de coordenada normalizada (= a largura na tela). */
  escala: number
  pronto: boolean
}

/** Uma região da folha, no mesmo normalizado de `Ponto` (os dois eixos pela largura). */
export interface Regiao {
  x: number
  y: number
  w: number
  h: number
}

/**
 * Limites de zoom, **relativos ao enquadramento inicial** e não absolutos.
 *
 * Eram `[0.02, 40]` fixos, e isso quebrava exatamente as pranchas que mais
 * precisam de zoom. Numa folha de aspecto 1:18 o `ajustar()` produz `z ≈
 * 0,000026`; o primeiro clique do scroll caía em `Math.max(0.02, …)` e **saltava
 * 766× de uma vez** — o desenho passava voando e o usuário concluía que não havia
 * desenho nenhum. Relativo ao ajuste, um clique é sempre um clique, em qualquer
 * prancha: é o "de pouco em pouco" do CAD, e girar o scroll rápido continua
 * acumulando porque cada evento multiplica.
 *
 * O teto de 20.000× não é generosidade: na prancha com dois levantamentos a 8,5
 * milhões de unidades, ler um deles exige **~7.865×** o enquadramento inicial.
 */
const ZOOM_MIN_REL = 0.2
const ZOOM_MAX_REL = 50_000

/**
 * O passo do scroll, e por que ele **acelera**.
 *
 * Um passo fixo obriga a escolher entre percorrer 7.865× de dez em dez por
 * cento (inviável) ou saltar tanto que o desenho passa voando. O CAD resolve
 * isso do jeito que a mão já sabe: gira devagar para ajustar, gira rápido para
 * atravessar. Aqui é o intervalo entre dois eventos de roda que decide — abaixo
 * de `JANELA_RAPIDA` o expoente cresce, até `ACELERACAO_MAX` cliques num.
 */
const PASSO_RODA = 1.12
const JANELA_RAPIDA = 120
const ACELERACAO_MAX = 3

/**
 * **`Ctrl` + roda = passo fino** — o conserto do D97, e ele existe porque a
 * aceleração acima estava certa e mesmo assim atrapalhava.
 *
 * O relato do dono: *"se eu coloco um pouco mais de zoom ele já aproxima muito e
 * não tem como eu achar nada porque levaria muito tempo arrastando"*. A causa
 * está medida: `JANELA_RAPIDA` são 120 ms, e **um mouse girado com naturalidade
 * dispara eventos a cada 50–80 ms** — ou seja, o giro normal quase nunca pega o
 * passo de 1,12; pega o de até 1,40. Três cliques viravam 2,7×.
 *
 * Remover a aceleração troca um defeito por outro: atravessar os ~7.865× que ler
 * uma poligonal exige, de 12% em 12%, é inviável. Então ela fica — e ganha um
 * **modificador**. Com `Ctrl` preso o passo é fixo e pequeno, sem aceleração
 * nenhuma: é o "de pouco em pouco" para procurar, e a roda solta continua sendo
 * o "atravessar" para viajar. Os dois gestos que o CAD sempre teve, agora
 * separados.
 *
 * 1,03 e não 1,01: a 1% o gesto vira moer o dedo, e a folha mediana pede ~20
 * cliques para dobrar de tamanho — que é o que se quer ao conferir uma cota.
 */
const PASSO_FINO = 1.03

/**
 * Teto da caixa do `<img>`, em pixels de tela.
 *
 * **Medido, não estimado** (Chromium 131, `ferramentas/medicao/`): a caixa é pintada
 * corretamente até 3×10⁷ px de largura e o navegador **desiste** em 10⁸ — e
 * "desiste" aqui é a prancha sumir da tela, que é muito pior que a mira torta
 * que este mecanismo existe para consertar.
 *
 * O teto de zoom da vista é 50.000× o enquadramento, e numa folha A1 isso pediria
 * 7,6×10⁷ px. Passando daqui, o `scale()` volta a cobrir a diferença: o desenho
 * fica com a pintura em bloco de novo, mas **aparece**. E o patamar em que isso
 * começa — ~19.600× o enquadramento — está muito acima de qualquer zoom em que
 * alguém esteja medindo: os 7.865× que a prancha mais extrema do acervo exige
 * continuam exatos.
 */
const LARGURA_MAXIMA_DE_CAIXA = 30_000_000

export function Vista2D({
  src,
  titulo,
  desenhando = false,
  alvo,
  mira,
  ancora,
  mundo,
  aoApontar,
  aoPairar,
  aoCarregarImagem,
  children,
}: {
  src: string
  titulo: string
  /** Em modo de desenho o toque de UM dedo marca ponto em vez de arrastar.
   *  Dois dedos continuam dando pinça — no tablet do canteiro, perder o zoom
   *  enquanto se mede tornaria a medida imprecisa justamente onde ela importa. */
  desenhando?: boolean
  /** Região a enquadrar (os atalhos "ir para o desenho N" do D46).
   *  `seq` existe para clicar duas vezes no mesmo desenho voltar a enquadrá-lo —
   *  sem ele, um `useEffect` sobre a região não dispararia na segunda vez. */
  alvo?: { regiao: Regiao; seq: number } | null
  /** O ponto que o snap escolheu — só para o leitor de coordenadas exibir.
   *  Quem DESENHA a mira continua sendo a `Camada`, por `children`; aqui ele
   *  entra como número, ao lado do zoom, para o desvio poder ser lido e não
   *  estimado. */
  mira?: Achado | null
  /** O último vértice já plantado do gesto em curso — o leitor mostra distância
   *  e rumo até ele, que é a entrada dinâmica do CAD. */
  ancora?: Ponto | null
  /** A coordenada de desenho desta folha, medida na conversão — o leitor abre
   *  por ela, que é a única régua que existia antes da conversão. */
  mundo?: Mundo | null
  aoApontar?: (p: Ponto) => void
  /** Onde o cursor está sobre a folha, para o snap procurar o traço mais perto.
   *
   *  Sai daqui e não de quem consome porque a **escala de tela** é desta vista:
   *  o snap tem raio em pixels (12 px, como no CAD), e converter isso para
   *  coordenada de folha exige o zoom corrente. Recalculá-lo por fora seria a
   *  segunda cópia da matriz que o `Enquadramento` existe para evitar.
   *
   *  `null` quando o ponteiro sai da folha — sem isso a mira ficaria acesa no
   *  último lugar onde passou. */
  aoPairar?: (p: Ponto | null, escalaDaTela: number) => void
  /** Entrega o `<img>` para quem precisa capturar o recorte (o snapshot BCF). */
  aoCarregarImagem?: (img: HTMLImageElement | null) => void
  children?: (enq: Enquadramento) => ReactNode
}) {
  const caixaRef = useRef<HTMLDivElement>(null)
  const imgRef = useRef<HTMLImageElement>(null)
  const [t, setT] = useState({ x: 0, y: 0, z: 1 })
  const [largura, setLargura] = useState(0)
  // O zoom do "ajustar à tela". É a referência de TODO o resto: os limites e o
  // percentual são relativos a ele, e não a números absolutos que só fazem
  // sentido numa prancha de tamanho comum.
  const [zAjuste, setZAjuste] = useState(1)
  const ponteiros = useRef(new Map<number, { x: number; y: number }>())
  const pinca = useRef<{ dist: number; meio: { x: number; y: number } } | null>(null)
  // Distância percorrida desde o toque: separa "tocar para marcar" de "arrastar
  // para mover". Sem isso, todo arrasto terminaria plantando um ponto.
  const percorrido = useRef(0)
  const ultimoGiro = useRef(0)
  const [laco, setLaco] = useState<{ a: Ponto; b: Ponto } | null>(null)
  /** O escritor do leitor de coordenadas — ver `Coordenadas.tsx`: ele se atualiza
   *  por fora do React porque o ponteiro emite dezenas de eventos por segundo. */
  const leitor = useRef<((p: Ponto | null) => void) | null>(null)

  // --- espessura constante na tela (item 20) --------------------------------
  // O SVG é reemitido com outra espessura a cada degrau de zoom. O texto é lido
  // uma vez do próprio blob (é local, não vai à rede) e quebrado em cabeçalho
  // reescrevível + corpo intocado — ver `espessura.ts`.
  const preparado = useRef<SvgPreparado | null>(null)
  const [fonteAjustada, setFonteAjustada] = useState<string | null>(null)
  const degrauAtual = useRef<number | null>(null)
  /**
   * A geometria declarada pela folha: `viewBox`, aspecto exato e papel em mm.
   *
   * O aspecto é o que tira a letterbox de sub-pixel que fazia a mira do snap
   * cair fora do traço (ver `SvgPreparado.aspecto`); o resto vai para o leitor
   * de coordenadas, que precisa dizer *em que régua* está lendo.
   */
  const [papel, setPapel] = useState<{
    viewBox: number
    viewBoxAltura: number
    aspecto: number
    mm: { largura: number; altura: number } | null
  } | null>(null)
  const aspecto = papel?.aspecto ?? null

  useEffect(() => {
    preparado.current = null
    degrauAtual.current = null
    setFonteAjustada(null)
    // **Zerar a largura é o que faz a folha nova ser enquadrada.** O `onLoad`
    // agora só chama `ajustar()` quando `largura` é 0 — senão, cada troca de
    // espessura jogaria a pessoa de volta ao "caber na tela" no meio do zoom.
    // Sem este zero, o efeito colateral seria o inverso e pior: trocar de
    // desenho abriria a folha nova no enquadramento da anterior.
    setLargura(0)
    setPapel(null)
    if (!src) return

    let vivo = true
    void fetch(src)
      .then((r) => r.text())
      .then((texto) => {
        if (!vivo) return
        const svg = prepararSvg(texto)
        preparado.current = svg
        if (svg) {
          setPapel({
            viewBox: svg.viewBox,
            viewBoxAltura: svg.viewBoxAltura,
            aspecto: svg.aspecto,
            mm: svg.papelMm,
          })
        }
      })
      .catch(() => { /* não é SVG, ou não tem a forma esperada: segue o original */ })
    return () => { vivo = false }
  }, [src])

  const naTela = largura * t.z
  useEffect(() => {
    const svg = preparado.current
    // `podeAfinar` e não só `svg`: agora o preparador devolve a geometria mesmo
    // quando não há espessura a renormalizar (é o conserto descrito lá), e
    // remontar o blob sem regras produziria um SVG sem o cabeçalho de estilos —
    // desenho sem cor nenhuma.
    if (!svg || !podeAfinar(svg) || !naTela) return
    const degrau = degrauDeZoom(naTela)
    if (degrau === degrauAtual.current) return
    degrauAtual.current = degrau

    const url = URL.createObjectURL(svgComEspessura(svg, naTela, largura * zAjuste))
    setFonteAjustada((anterior) => {
      // Revogar o anterior é obrigatório: numa sessão de zoom são dezenas de
      // blobs de vários MB, e sem isto eles ficam vivos até a aba fechar.
      if (anterior) URL.revokeObjectURL(anterior)
      return url
    })
  }, [naTela, largura, zAjuste])

  // Revoga o último ao desmontar — o efeito acima só revoga ao TROCAR.
  useEffect(() => () => { if (fonteAjustada) URL.revokeObjectURL(fonteAjustada) },
    [fonteAjustada])

  /** Encaixa a prancha inteira na caixa — o estado inicial e o botão "ajustar". */
  const ajustar = useCallback(() => {
    const caixa = caixaRef.current
    const img = imgRef.current
    if (!caixa || !img || !img.naturalWidth) return
    const r = caixa.getBoundingClientRect()
    const escala = Math.min(r.width / img.naturalWidth, r.height / img.naturalHeight) * 0.94
    setLargura(img.naturalWidth)
    setZAjuste(escala)
    setT({
      z: escala,
      x: (r.width - img.naturalWidth * escala) / 2,
      y: (r.height - img.naturalHeight * escala) / 2,
    })
  }, [])

  useEffect(() => {
    const caixa = caixaRef.current
    if (!caixa) return
    const observador = new ResizeObserver(() => ajustar())
    observador.observe(caixa)
    return () => observador.disconnect()
  }, [ajustar])

  /** Zoom ancorado num ponto: o que está sob o dedo continua sob o dedo. */
  const ampliar = useCallback((fator: number, ancora: { x: number; y: number }) => {
    setT((atual) => {
      const z = Math.min(
        zAjuste * ZOOM_MAX_REL,
        Math.max(zAjuste * ZOOM_MIN_REL, atual.z * fator),
      )
      const real = z / atual.z
      return { z, x: ancora.x - (ancora.x - atual.x) * real, y: ancora.y - (ancora.y - atual.y) * real }
    })
  }, [zAjuste])

  /**
   * Enquadra uma região da folha — o motor dos atalhos e do zoom por laço.
   *
   * Recebe a região no mesmo normalizado de `Ponto` (os dois eixos pela largura),
   * que é como o backend a publica em `conversao.aviso.desenhos`. Nada de
   * geometria de página é recalculado aqui.
   */
  const enquadrarRegiao = useCallback((r: Regiao) => {
    const caixa = caixaRef.current
    if (!caixa || !largura || r.w <= 0 || r.h <= 0) return
    const box = caixa.getBoundingClientRect()
    const [px, py] = [r.x * largura, r.y * largura]
    const [pw, ph] = [r.w * largura, r.h * largura]
    // 0,82 = a folga que faz o desenho não encostar na borda; ver um pedaço do
    // vazio em volta é o que diz "cheguei no desenho certo".
    const z = Math.min(box.width / pw, box.height / ph) * 0.82
    setT({
      z,
      x: box.width / 2 - (px + pw / 2) * z,
      y: box.height / 2 - (py + ph / 2) * z,
    })
  }, [largura])

  // Os atalhos do D46: o pai troca `alvo.seq` e a vista voa até lá.
  useEffect(() => {
    if (alvo) enquadrarRegiao(alvo.regiao)
  }, [alvo, enquadrarRegiao])

  const local = (e: { clientX: number; clientY: number }) => {
    const r = caixaRef.current?.getBoundingClientRect()
    return { x: e.clientX - (r?.left ?? 0), y: e.clientY - (r?.top ?? 0) }
  }

  const aoDescer = (e: EventoPonteiro) => {
    ;(e.target as Element).setPointerCapture?.(e.pointerId)
    ponteiros.current.set(e.pointerId, local(e))
    pinca.current = null
    percorrido.current = 0
    // Shift + arrasto = **zoom por laço**, o "zoom window" do CAD. Fica atrás do
    // Shift de propósito: o arrasto simples é mover, e no canteiro mover é o
    // gesto de todo minuto. Sem modificador, um seria a versão frustrada do outro.
    if (e.shiftKey && !desenhando && largura) {
      const p = paraDesenho(local(e))
      setLaco({ a: p, b: p })
    }
  }

  const aoMover = (e: EventoPonteiro) => {
    // **Antes do teste de captura, de propósito.** O mouse pairando não tem
    // botão pressionado e por isso não está em `ponteiros`; se a mira só
    // acendesse com o botão apertado, no desktop ela só apareceria depois do
    // clique — tarde demais, porque o clique é justamente o que ela deveria
    // guiar. No toque o efeito é o oposto e igualmente correto: o dedo já
    // encostado alimenta a mira enquanto arrasta, antes de soltar.
    // `largura * t.z` e não `largura`: o segundo é a largura NATURAL do SVG, que
    // não sabe de zoom. A tolerância do snap é de 12 px de TELA — com a natural,
    // ela ficaria constante em coordenada de folha e a mira passaria a agarrar
    // ponto a metros de distância justamente quando alguém amplia para ser
    // preciso. É o mesmo `escala` que o `Enquadramento` publica logo abaixo.
    if (desenhando && largura) aoPairar?.(paraDesenho(local(e)), largura * t.z)
    // O leitor acompanha SEMPRE, medindo ou navegando — é barra de status, como
    // no CAD, e serve tanto para conferir onde se está quanto para flagrar a
    // tela discordando do desenho antes de alguém gravar medida errada.
    if (largura) leitor.current?.(paraDesenho(local(e)))

    if (!ponteiros.current.has(e.pointerId)) return
    const antes = ponteiros.current.get(e.pointerId)!
    const agora = local(e)
    ponteiros.current.set(e.pointerId, agora)

    if (laco) {
      setLaco((atual) => (atual ? { ...atual, b: paraDesenho(agora) } : null))
      return
    }

    const ativos = [...ponteiros.current.values()]
    if (ativos.length === 1) {
      percorrido.current += Math.hypot(agora.x - antes.x, agora.y - antes.y)
      // Em modo de desenho, um dedo NÃO arrasta: o gesto está reservado para
      // apontar. O deslocamento continua sendo somado para o `pointerup` saber
      // distinguir toque de tremor.
      if (desenhando) return
      setT((atual) => ({ ...atual, x: atual.x + (agora.x - antes.x), y: atual.y + (agora.y - antes.y) }))
      return
    }
    if (ativos.length >= 2) {
      const [a, b] = ativos
      const dist = Math.hypot(a.x - b.x, a.y - b.y)
      const meio = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
      if (pinca.current) {
        // Arrastar as duas juntas move; afastá-las amplia. Tratar os dois no
        // mesmo gesto é o que faz a pinça parecer natural em vez de travada.
        const desloc = { x: meio.x - pinca.current.meio.x, y: meio.y - pinca.current.meio.y }
        setT((atual) => ({ ...atual, x: atual.x + desloc.x, y: atual.y + desloc.y }))
        if (pinca.current.dist > 0) ampliar(dist / pinca.current.dist, meio)
      }
      pinca.current = { dist, meio }
    }
  }

  const aoSubir = (e: EventoPonteiro) => {
    const era = ponteiros.current.get(e.pointerId)
    const sozinho = ponteiros.current.size === 1
    ponteiros.current.delete(e.pointerId)
    if (ponteiros.current.size < 2) pinca.current = null

    if (laco) {
      const r = retanguloDoLaco(laco)
      setLaco(null)
      // Laço de 3 px é clique com o Shift preso, não pedido de zoom. Enquadrar
      // aquilo jogaria a pessoa a milhares de por cento de onde ela estava.
      if (r.w * largura > 12 && r.h * largura > 12) enquadrarRegiao(r)
      return
    }

    // 6 px de tolerância: dedo com luva nunca fica parado, e exigir imobilidade
    // absoluta faria metade dos toques do canteiro não registrarem nada.
    if (desenhando && sozinho && era && percorrido.current < 6 && largura) {
      aoApontar?.(paraDesenho(era))
    }
  }

  /** Duplo clique aproxima onde se clicou — o atalho que dispensa mirar no botão.
   *  Com Shift, afasta: é o par que evita ter de voltar ao canto da tela. */
  const aoDuplicar = (e: EventoMouse) => {
    if (desenhando) return
    ampliar(e.shiftKey ? 1 / 2.2 : 2.2, local(e))
  }

  useEffect(() => {
    const caixa = caixaRef.current
    if (!caixa) return
    // `wheel` como listener nativo não-passivo: em React o `onWheel` é passivo e
    // o `preventDefault()` não pega, então a roda daria zoom E rolaria a página.
    const aoRodar = (e: WheelEvent) => {
      e.preventDefault()
      const r = caixa.getBoundingClientRect()
      const local = { x: e.clientX - r.left, y: e.clientY - r.top }

      // **`Ctrl` preso: passo fino, sem aceleração** (D97). O relógio nem é
      // consultado — a aceleração existe para atravessar, e quem segura o `Ctrl`
      // está procurando, não viajando. Zerar `ultimoGiro` ao sair do modo fino
      // seria supérfluo: o próximo giro solto recalcula o intervalo sozinho.
      if (e.ctrlKey || e.metaKey) {
        ampliar(e.deltaY < 0 ? PASSO_FINO : 1 / PASSO_FINO, local)
        return
      }

      // Giro rápido = passo maior, como no CAD. O relógio é a única fonte:
      // usar a magnitude de `deltaY` faria trackpad e mouse de roda andarem em
      // velocidades diferentes pelo mesmo gesto.
      const agora = e.timeStamp
      const intervalo = agora - ultimoGiro.current
      ultimoGiro.current = agora
      const aceleracao = intervalo < JANELA_RAPIDA
        ? 1 + Math.min(ACELERACAO_MAX - 1, (JANELA_RAPIDA - intervalo) / 45)
        : 1
      const fator = Math.pow(PASSO_RODA, aceleracao)
      ampliar(e.deltaY < 0 ? fator : 1 / fator, local)
    }
    caixa.addEventListener('wheel', aoRodar, { passive: false })
    return () => caixa.removeEventListener('wheel', aoRodar)
  }, [ampliar])

  // Teclado: `+`/`-` para aproximar sem tirar a mão do lugar e `0` para voltar ao
  // ajuste — o vocabulário que quem usa CAD já tem no dedo.
  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      const alvoTecla = e.target as HTMLElement | null
      if (alvoTecla && /^(INPUT|TEXTAREA)$/.test(alvoTecla.tagName)) return
      if (e.key === '+' || e.key === '=') ampliar(1.3, centro())
      else if (e.key === '-' || e.key === '_') ampliar(1 / 1.3, centro())
      else if (e.key === '0') ajustar()
    }
    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  })

  const centro = () => {
    const r = caixaRef.current?.getBoundingClientRect()
    return { x: (r?.width ?? 0) / 2, y: (r?.height ?? 0) / 2 }
  }

  // As duas conversões, derivadas de UMA fonte (a transformação corrente).
  // `largura` é a natural da imagem: normalizar pela largura nos dois eixos é o
  // que preserva o aspecto (ver o contrato de `Ponto` em types.ts).
  const paraTela = (p: Ponto) => ({
    x: t.x + p.x * largura * t.z,
    y: t.y + p.y * largura * t.z,
  })
  const paraDesenho = (px: { x: number; y: number }) => ({
    x: (px.x - t.x) / (t.z * largura),
    y: (px.y - t.y) / (t.z * largura),
  })

  /**
   * O zoom sai do `scale()` e vai para a CAIXA — o conserto do desvio visual.
   *
   * `zCaixa` é o quanto o `<img>` cresce de verdade (e portanto em que resolução
   * o navegador re-rasteriza o vetor); `restoDaEscala` é só o que não coube no
   * teto, e vale 1 em todo zoom praticável. A geometria na tela é idêntica à de
   * antes — `transformOrigin: 0 0` faz escalar a caixa e escalar o conteúdo
   * darem no mesmo lugar —, então `paraTela` acima não muda uma vírgula, e nem
   * a marcação já anotada no canteiro.
   *
   * Sem `aspecto` (SVG que não é do nosso motor) não há caixa a dimensionar, e
   * aí é o `scale()` de antes: pior pintura, mas a prancha abre.
   */
  const zCaixa = aspecto && largura
    ? Math.min(t.z, LARGURA_MAXIMA_DE_CAIXA / largura)
    : 0
  const restoDaEscala = zCaixa > 0 ? t.z / zCaixa : t.z
  const caixaPedida = zCaixa > 0
    ? { largura: largura * zCaixa, altura: (largura / (aspecto as number)) * zCaixa }
    : null

  /**
   * A caixa que o navegador **de fato** deu — a única linha do leitor que não
   * vem de conta nossa.
   *
   * Pedir uma largura não é receber uma largura: o mecanismo de layout tem teto
   * próprio, e quando ele corta, o desenho passa a ser pintado numa escala
   * diferente daquela que `paraTela` usa para posicionar a mira. Isso é erro
   * **relativo**, invisível no enquadramento e multiplicado pelo zoom — a forma
   * exata do defeito que se relatou. Medir em vez de confiar é o que transforma
   * essa suspeita em resposta.
   *
   * `useLayoutEffect` e não `useEffect`: tem de ler depois do DOM mudar e antes
   * de pintar, senão a leitura é sempre a do zoom anterior. Divide-se pelo
   * `scale()` porque o rect já vem transformado.
   */
  const [caixaReal, setCaixaReal] = useState<{ largura: number; altura: number } | null>(null)
  useLayoutEffect(() => {
    const img = imgRef.current
    if (!img || !caixaPedida) { setCaixaReal(null); return }
    const r = img.getBoundingClientRect()
    const k = restoDaEscala || 1
    setCaixaReal({ largura: r.width / k, altura: r.height / k })
  }, [caixaPedida?.largura, caixaPedida?.altura, restoDaEscala, fonteAjustada])

  const registrarLeitor = useCallback(
    (fn: ((p: Ponto | null) => void) | null) => { leitor.current = fn },
    [],
  )

  return (
    <div
      ref={caixaRef}
      onPointerDown={aoDescer}
      onPointerMove={aoMover}
      onPointerUp={aoSubir}
      onPointerCancel={aoSubir}
      onPointerLeave={() => { aoPairar?.(null, largura); leitor.current?.(null) }}
      onDoubleClick={aoDuplicar}
      style={{
        position: 'relative', width: '100%', height: '100%', overflow: 'hidden',
        background: 'var(--inset)', touchAction: 'none',
        cursor: desenhando ? 'crosshair' : 'grab',
      }}
    >
      <img
        ref={imgRef}
        // O ajustado quando existe; o original enquanto ele não chegou (e para
        // sempre, quando o arquivo não é SVG do nosso motor). A troca não
        // repisca a prancha: mesmo desenho, mesmas dimensões, só a espessura.
        src={fonteAjustada ?? src}
        alt={titulo}
        draggable={false}
        onLoad={() => {
          // `ajustar()` só na PRIMEIRA carga: reenquadrar a cada troca de
          // espessura jogaria a pessoa de volta ao "caber na tela" no meio do
          // zoom, que é o oposto do que ela pediu ao ampliar.
          if (!largura) ajustar()
          aoCarregarImagem?.(imgRef.current)
        }}
        style={{
          position: 'absolute', top: 0, left: 0, transformOrigin: '0 0',
          // O `scale()` só entra pelo que passou do teto da caixa — em zoom
          // praticável `restoDaEscala` é 1 e isto é uma translação pura.
          transform: `translate(${t.x}px, ${t.y}px)`
            + (restoDaEscala === 1 ? '' : ` scale(${restoDaEscala})`),
          // **A caixa cresce com o zoom, e é ela que manda o navegador
          // re-rasterizar o vetor** (ver o cabeçalho: é o conserto do desvio
          // visual do D90). A ALTURA sai do `viewBox` e não do `naturalHeight`:
          // os dois diferem por arredondamento a inteiro, e a diferença vira
          // letterbox que o zoom multiplica — ver `SvgPreparado.aspecto`.
          ...(zCaixa > 0
            ? {
              width: `${largura * zCaixa}px`,
              height: `${(largura / (aspecto as number)) * zCaixa}px`,
            }
            : null),
          // A prancha é linha fina: suavizar destrói o traço no zoom alto.
          imageRendering: 'crisp-edges', userSelect: 'none', maxWidth: 'none',
        }}
      />

      {/* A camada de marcação. `pointerEvents: none` no container para o gesto
          continuar chegando à prancha; cada pino religa o seu. */}
      {children && largura > 0 && (
        <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
          {children({ paraTela, paraDesenho, escala: largura * t.z, pronto: true })}
        </div>
      )}

      {/* O laço, enquanto se arrasta com Shift. */}
      {laco && largura > 0 && (() => {
        const r = retanguloDoLaco(laco)
        const canto = paraTela({ x: r.x, y: r.y })
        return (
          <div
            style={{
              position: 'absolute', pointerEvents: 'none',
              left: canto.x, top: canto.y,
              width: r.w * largura * t.z, height: r.h * largura * t.z,
              border: '1.5px dashed var(--accent)',
              background: 'color-mix(in srgb,var(--accent) 12%,transparent)',
            }}
          />
        )
      })()}

      <div style={{ position: 'absolute', right: 12, bottom: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <BotaoZoom rotulo="Aproximar (+ ou duplo clique)" onClick={() => ampliar(1.3, centro())}><Plus size={16} /></BotaoZoom>
        <BotaoZoom rotulo="Afastar (−)" onClick={() => ampliar(1 / 1.3, centro())}><Minus size={16} /></BotaoZoom>
        <BotaoZoom rotulo="Ajustar à tela (0)" onClick={ajustar}><Maximize2 size={15} /></BotaoZoom>
      </div>

      {/* O rodapé de instrumentos: o zoom e, ao lado, o leitor de coordenadas —
          juntos porque respondem à mesma pergunta ("onde eu estou?") e porque
          separá-los faria procurar em dois cantos da tela. */}
      <div style={{
        position: 'absolute', left: 12, bottom: 12,
        display: 'flex', alignItems: 'flex-end', gap: 6,
      }}>
        <span
          className="num"
          title="100% = prancha ajustada à tela. Shift + arrastar enquadra uma área; girar o scroll rápido aproxima mais depressa."
          style={{
            fontSize: 11, fontWeight: 600,
            color: 'var(--ink-3)', background: 'var(--glass)', border: '1px solid var(--line)',
            borderRadius: 999, padding: '3px 9px',
          }}
        >
          {/* Relativo ao ajuste, e não ao tamanho natural do SVG. Absoluto, uma
              prancha de aspecto 1:18 abria marcando **0%** — um número que não
              informa nada e que fazia a tela parecer quebrada antes mesmo de o
              usuário tentar mover. */}
          {formatarZoom(t.z / (zAjuste || 1))}
        </span>

        {largura > 0 && (
          <Coordenadas
            mira={mira}
            ancora={ancora}
            registrar={registrarLeitor}
            instrumento={{
              mundo: mundo ?? null,
              escala: largura * t.z,
              zoom: t.z / (zAjuste || 1),
              viewBox: papel ? { largura: papel.viewBox, altura: papel.viewBoxAltura } : null,
              papelMm: papel?.mm ?? null,
              pedida: caixaPedida,
              real: caixaReal,
              resto: restoDaEscala,
            }}
          />
        )}
      </div>
    </div>
  )
}

/** Canto superior-esquerdo + tamanho de um laço traçado em qualquer direção. */
function retanguloDoLaco(laco: { a: Ponto; b: Ponto }): Regiao {
  return {
    x: Math.min(laco.a.x, laco.b.x),
    y: Math.min(laco.a.y, laco.b.y),
    w: Math.abs(laco.b.x - laco.a.x),
    h: Math.abs(laco.b.y - laco.a.y),
  }
}

/** `7865x` lê melhor que `786500%` — e é a grandeza que o CAD usa nesse patamar. */
function formatarZoom(relativo: number): string {
  if (relativo >= 20) return `${Math.round(relativo).toLocaleString('pt-BR')}×`
  return `${Math.round(relativo * 100)}%`
}

function BotaoZoom({ children, rotulo, onClick }: { children: ReactNode; rotulo: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label={rotulo}
      title={rotulo}
      style={{
        width: 34, height: 34, display: 'grid', placeItems: 'center', cursor: 'pointer',
        background: 'var(--surface)', color: 'var(--ink-2)', border: '1px solid var(--line)',
        borderRadius: 'var(--r-sm)', boxShadow: 'var(--shadow-sm)',
      }}
    >
      {children}
    </button>
  )
}
