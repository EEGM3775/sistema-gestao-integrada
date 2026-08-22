import { baixarArquivo } from '@/lib/arquivo'
import type { Ponto } from '../types'

/**
 * O snap de medição — a mira que gruda no traço, como no CAD.
 *
 * **Por que existe um índice, e não uma leitura do desenho.** A prancha é
 * mostrada dentro de um `<img>`, e isso é decisão de segurança registrada no
 * `Vista2D.tsx`: o SVG que sai do conversor carrega texto vindo do arquivo do
 * cliente, e injetá-lo inline no DOM executaria qualquer `<script>` que
 * atravessasse o motor. Dentro de `<img>` o SVG é imagem — e imagem não tem
 * vértice que se possa consultar. Então a geometria chega por fora, num sidecar
 * binário que o backend produz na mesma passada que gera o SVG.
 *
 * **Clicar "por cima" da linha é o erro que isto existe para evitar.** Numa
 * folha onde 1 px vale 4 cm, dois cliques a três pixels do canto viram 8 cm de
 * erro numa cota que ninguém confere — e no canteiro isso vira parede no lugar
 * errado. Medir sem snap não é medir, é estimar com cara de medida.
 */

/** Os tipos, na ordem do byte que o backend grava (`motores/snap.py`). */
export const EXTREMIDADE = 0
export const MEIO = 1
export const CENTRO = 2
export const QUADRANTE = 3
export const NO = 4
export const INTERSECAO = 5

/**
 * "Próximo" — algum lugar sobre o traço, sem ser ponto notável.
 *
 * **Só existe no cliente**, e por isso é o único tipo fora do sidecar: ele não é
 * um ponto que o servidor possa listar (são infinitos), é o pé da perpendicular
 * calculado na hora contra o segmento sob o cursor. Numerá-lo depois dos que o
 * backend grava mantém o formato binário intacto.
 */
export const PROXIMO = 6

export type TipoDeSnap = 0 | 1 | 2 | 3 | 4 | 5 | 6

export const NOME_DO_TIPO: Record<number, string> = {
  [EXTREMIDADE]: 'extremidade',
  [MEIO]: 'meio',
  [CENTRO]: 'centro',
  [QUADRANTE]: 'quadrante',
  [NO]: 'nó',
  [INTERSECAO]: 'interseção',
  [PROXIMO]: 'próximo',
}

/**
 * Precedência quando dois candidatos empatam em distância.
 *
 * É a mesma ordem do CAD, e ela importa: num canto de parede coincidem
 * extremidade e interseção, e quem clicou ali quis o canto. Deixar o desempate
 * para a ordem do arquivo faria a mira escolher diferente em pranchas
 * visualmente idênticas.
 */
const PRECEDENCIA: Record<number, number> = {
  [EXTREMIDADE]: 0,
  [INTERSECAO]: 1,
  [CENTRO]: 2,
  [QUADRANTE]: 3,
  [NO]: 4,
  [MEIO]: 5,
  [PROXIMO]: 6,
}

/**
 * Faixa de prioridade — o que ganha de quem quando os dois estão ao alcance.
 *
 * **Distância pura escolhe errado, e é o defeito que se sente na mão.** Mirando
 * o canto de uma parede, o meio do segmento vizinho pode estar 3 px mais perto
 * do cursor que a própria extremidade; a mira agarra o meio e a medida sai do
 * lugar errado com a mira acesa, que é pior do que não ter mira. O CAD resolve
 * por faixa: canto e cruzamento primeiro, geometria de círculo depois, e "algum
 * lugar da linha" só quando não há mais nada.
 */
const FAIXA: Record<number, number> = {
  [EXTREMIDADE]: 0,
  [INTERSECAO]: 0,
  [CENTRO]: 1,
  [QUADRANTE]: 1,
  [NO]: 1,
  [MEIO]: 2,
  [PROXIMO]: 2,
}

/** Alcance da mira, em pixels de tela — a "abertura" do OSNAP. */
const ABERTURA_PX = 18

/**
 * Alcance de "sobre o traço", menor de propósito.
 *
 * Ele existe para o caso sem vértice (medir até o meio de um vão), e não para
 * competir com o canto. Igualando as duas aberturas, todo traço perto do cursor
 * produziria um candidato — e como há traço em toda parte numa prancha, o pé da
 * perpendicular venceria o vértice sempre que este estivesse um fio mais longe.
 */
const ABERTURA_TRACO_PX = 8

export interface Achado {
  ponto: Ponto
  tipo: TipoDeSnap
  /** Distância em pixels de tela — é o que a UI usa para decidir se mostra. */
  pixels: number
}

/**
 * O índice carregado, com busca espacial.
 *
 * A busca é em grade uniforme e não em k-d tree de propósito: o alvo é achar o
 * ponto mais próximo do cursor **a cada movimento do mouse**, com orçamento de
 * um quadro (~16 ms). A grade responde em tempo constante para a densidade real
 * de uma prancha, não realoca durante o pan e é construída numa passada linear —
 * o que importa quando o índice tem 470 mil pontos e a aba não pode congelar
 * enquanto ele entra.
 */
export class IndiceDeSnap {
  readonly pontos: number
  readonly truncado: boolean

  private readonly x: Float64Array
  private readonly y: Float64Array
  private readonly tipo: Uint8Array
  private readonly segmentos: Float64Array
  private readonly grade: Map<number, number[]>
  private readonly lado: number

  private constructor(
    x: Float64Array, y: Float64Array, tipo: Uint8Array,
    segmentos: Float64Array, truncado: boolean,
  ) {
    this.x = x
    this.y = y
    this.tipo = tipo
    this.segmentos = segmentos
    this.truncado = truncado
    this.pontos = tipo.length

    // Célula alvo: ~64 pontos por célula na prancha mediana. Grade fina demais
    // gasta memória em Map; grossa demais faz cada consulta varrer uma multidão.
    this.lado = 1 / Math.max(16, Math.min(1024, Math.round(Math.sqrt(this.pontos / 4))))
    this.grade = new Map()
    for (let i = 0; i < this.pontos; i += 1) {
      const chave = this.chave(x[i], y[i])
      const balde = this.grade.get(chave)
      if (balde) balde.push(i)
      else this.grade.set(chave, [i])
    }
  }

  /**
   * Lê o sidecar binário, nas duas versões do formato.
   *
   * Formato (`motores/snap.py::empacotar`): `SNAP1`/`SNAP2` · uint32 n · uint32
   * m · uint8 truncado · f[n] x · f[n] y · uint8[n] tipo · f[4m] segmentos —
   * com `f` valendo **float32 no `SNAP1` e float64 no `SNAP2`**.
   *
   * **Os dois, porque a precisão de um arquivo não se reescreve na leitura.** O
   * `SNAP1` guarda 32 bits, e 32 bits em coordenada normalizada dão degrau de
   * 6×10⁻⁸ — numa folha A1, 0,00005 unidade de desenho, mais grosso que a
   * quinta casa decimal que o sistema promete. Sidecar antigo continua abrindo
   * com a precisão que tem; quem quer as cinco casas reprocessa a folha. Fingir
   * precisão que o arquivo não carrega seria pior que não abrir.
   *
   * **As tipadas são cópias, e é de propósito.** O `buffer` do `fetch` não
   * garante alinhamento no offset onde o X começa (14, que não é múltiplo de 4
   * nem de 8), e `new Float64Array(buffer, 14, n)` lança `RangeError` em todo
   * navegador. A cópia custa uma passada e evita um erro que só apareceria em
   * produção, com o arquivo do cliente.
   */
  static ler(dados: ArrayBuffer): IndiceDeSnap | null {
    if (dados.byteLength < 14) return null
    const cabecalho = new DataView(dados)
    const marca = String.fromCharCode(...new Uint8Array(dados, 0, 5))
    if (marca !== 'SNAP1' && marca !== 'SNAP2') return null
    const largo = marca === 'SNAP2'
    const bytes = largo ? 8 : 4

    const n = cabecalho.getUint32(5, true)
    const m = cabecalho.getUint32(9, true)
    const truncado = cabecalho.getUint8(13) === 1

    const esperado = 14 + n * bytes * 2 + n + m * bytes * 4
    if (dados.byteLength < esperado) return null

    // Tudo vira `Float64Array` mesmo vindo de 32 bits: um tipo só adiante evita
    // que a busca tenha dois caminhos, e o 32→64 é exato (não inventa dígito,
    // só deixa de truncar os que já existem).
    const ler = (inicio: number, quantos: number) => {
      const fatia = dados.slice(inicio, inicio + quantos * bytes)
      return largo ? new Float64Array(fatia) : Float64Array.from(new Float32Array(fatia))
    }

    let posicao = 14
    const x = ler(posicao, n)
    posicao += n * bytes
    const y = ler(posicao, n)
    posicao += n * bytes
    const tipo = new Uint8Array(dados.slice(posicao, posicao + n))
    posicao += n
    const segmentos = ler(posicao, m * 4)

    return new IndiceDeSnap(x, y, tipo, segmentos, truncado)
  }

  private chave(px: number, py: number): number {
    // Deslocado por 2^19 para a célula negativa não invadir os bits vizinhos —
    // o mesmo cuidado do `_celula()` do backend, e pela mesma razão: a borda do
    // recorte produz coordenada um fio fora de [0, 1].
    const cx = Math.floor(px / this.lado) + 0x80000
    const cy = Math.floor(py / this.lado) + 0x80000
    return cx * 0x100000 + cy
  }

  /**
   * O ponto notável mais próximo do cursor, ou `null` se nenhum está perto.
   *
   * `toleranciaPx` é raio de tela, não de folha: a mira tem de grudar quando o
   * traço está a 12 px do cursor, independente do zoom — é assim no CAD e é o
   * que faz o gesto ser previsível. Converter para o espaço da folha aqui, com a
   * escala corrente, é o que mantém isso verdade em 1× e em 20.000×.
   */
  maisProximo(
    alvo: Ponto,
    escalaDaTela: number,
    toleranciaPx = ABERTURA_PX,
    tipos?: ReadonlySet<number>,
  ): Achado | null {
    if (!this.pontos || escalaDaTela <= 0) return null
    const raio = toleranciaPx / escalaDaTela
    const raio2 = raio * raio

    let melhor: Achado | null = null
    let melhorD2 = 0
    let melhorFaixa = Infinity
    const alcance = Math.ceil(raio / this.lado)

    const cx = Math.floor(alvo.x / this.lado)
    const cy = Math.floor(alvo.y / this.lado)
    for (let dx = -alcance; dx <= alcance; dx += 1) {
      for (let dy = -alcance; dy <= alcance; dy += 1) {
        const balde = this.grade.get(
          (cx + dx + 0x80000) * 0x100000 + (cy + dy + 0x80000),
        )
        if (!balde) continue
        for (const i of balde) {
          const tipo = this.tipo[i]
          if (tipos && !tipos.has(tipo)) continue
          const ex = this.x[i] - alvo.x
          const ey = this.y[i] - alvo.y
          const d2 = ex * ex + ey * ey
          if (d2 > raio2) continue

          // **Faixa primeiro, distância depois.** Dentro da abertura, o canto
          // ganha do meio mesmo estando um pouco mais longe — é o que faz mirar
          // um vértice funcionar. Só dentro da MESMA faixa a distância decide,
          // e o `PRECEDENCIA` desempata quem cai no mesmo lugar.
          const faixa = FAIXA[tipo]
          if (melhor) {
            if (faixa > melhorFaixa) continue
            if (faixa === melhorFaixa) {
              if (d2 > melhorD2) continue
              if (Math.abs(d2 - melhorD2) < 1e-18
                  && PRECEDENCIA[tipo] >= PRECEDENCIA[melhor.tipo]) continue
            }
          }
          melhorFaixa = faixa
          melhorD2 = d2
          melhor = {
            ponto: { x: this.x[i], y: this.y[i] },
            tipo: tipo as TipoDeSnap,
            pixels: Math.sqrt(d2) * escalaDaTela,
          }
        }
      }
    }
    return melhor
  }

  /**
   * O pé da perpendicular do cursor sobre o traço mais próximo.
   *
   * Complementa o ponto notável em vez de competir com ele: medir de uma parede
   * até o MEIO de um vão não tem vértice onde grudar, e sem isto a pessoa volta
   * a clicar no olho. Só entra quando nenhum ponto notável está no alcance —
   * extremidade sempre ganha do "algum lugar da linha".
   */
  sobreOTraco(alvo: Ponto, escalaDaTela: number, toleranciaPx = ABERTURA_TRACO_PX): Achado | null {
    const total = this.segmentos.length / 4
    if (!total || escalaDaTela <= 0) return null
    const raio = toleranciaPx / escalaDaTela
    let melhor: Achado | null = null
    let melhorD2 = raio * raio

    for (let s = 0; s < total; s += 1) {
      const p = 4 * s
      const x1 = this.segmentos[p]
      const y1 = this.segmentos[p + 1]
      const dx = this.segmentos[p + 2] - x1
      const dy = this.segmentos[p + 3] - y1
      const comprimento2 = dx * dx + dy * dy
      if (!comprimento2) continue
      // Descarte barato antes da conta cara: se a caixa do segmento está longe,
      // a projeção também está. É o que mantém isto viável a cada movimento.
      if (Math.abs(x1 - alvo.x) - Math.abs(dx) > raio) continue
      if (Math.abs(y1 - alvo.y) - Math.abs(dy) > raio) continue

      let t = ((alvo.x - x1) * dx + (alvo.y - y1) * dy) / comprimento2
      t = t < 0 ? 0 : t > 1 ? 1 : t
      const px = x1 + t * dx
      const py = y1 + t * dy
      const ex = px - alvo.x
      const ey = py - alvo.y
      const d2 = ex * ex + ey * ey
      if (d2 < melhorD2) {
        melhorD2 = d2
        melhor = {
          ponto: { x: px, y: py },
          tipo: PROXIMO,
          pixels: Math.sqrt(d2) * escalaDaTela,
        }
      }
    }
    return melhor
  }

  /**
   * O que a mira deve mostrar para este cursor.
   *
   * A ordem é a do CAD: ponto notável primeiro, traço só quando não há nenhum.
   * Inverter isso faria a mira preferir "qualquer lugar da linha" ao canto que
   * está a dois pixels — e o canto é o que se quis clicar.
   */
  procurar(alvo: Ponto, escalaDaTela: number, tipos?: ReadonlySet<number>): Achado | null {
    return this.maisProximo(alvo, escalaDaTela, 12, tipos)
      ?? this.sobreOTraco(alvo, escalaDaTela)
  }
}

/**
 * Busca o sidecar e o interpreta.
 *
 * Devolve `null` em vez de lançar quando não dá: sem snap a medição continua
 * funcionando à mão, e derrubar o visualizador inteiro porque um extra não
 * carregou seria trocar o essencial pelo acessório — a mesma decisão que o
 * `capturarRecorte` já toma no `marcar.ts`.
 */
export async function carregarSnap(url: string): Promise<IndiceDeSnap | null> {
  try {
    // **Pelo `apiClient`, nunca por `fetch` cru.** O access token vive em
    // memória (F1) e só é anexado pelo interceptor do axios; um `fetch` direto
    // chega sem `Authorization` e leva 401 — e como esta função engole a falha
    // por desenho, o sintoma não é erro na tela, é **o snap simplesmente não
    // existir**, sem nada dizendo por quê. Foi exatamente isso que aconteceu, e
    // o cabeçalho de `lib/arquivo.ts` já avisava.
    const blob = await baixarArquivo(url)
    return IndiceDeSnap.ler(await blob.arrayBuffer())
  } catch {
    return null
  }
}
