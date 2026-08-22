import type { Marcacao, Ponto, SituacaoMarcacao } from '../types'
import type { PillKind } from '@/components/malha'

/**
 * A lógica da marcação e da medição, fora dos componentes.
 *
 * Está aqui — e não dentro do JSX — porque estas funções decidem **números que
 * o servidor recalcula**: a distância que a tela desenha enquanto o dedo se move
 * tem de bater com a que o backend grava. Mantê-las isoladas é o que permite lê-
 * las lado a lado com `serializers.medir()` e ver que são a mesma conta.
 *
 * O que a tela NÃO faz é gravar o número que calculou: quem grava é o servidor,
 * a partir dos vértices. Esta cópia existe só para o traço ter rótulo enquanto
 * se mede — é a mesma separação do simulador de plano de pagamento (F19), onde
 * a tela mostra e o motor decide.
 */

export type Modo = 'navegar' | 'marcar' | 'distancia' | 'area' | 'calibrar'

/** Quantos vértices o modo precisa antes de poder concluir. */
export const MINIMO_DE_PONTOS: Record<Modo, number> = {
  navegar: 0,
  marcar: 1,
  distancia: 2,
  area: 3,
  calibrar: 2,
}

/** Comprimento da polilinha em unidades normalizadas (pela largura da folha). */
export function comprimento(pontos: Ponto[]): number {
  let soma = 0
  for (let i = 1; i < pontos.length; i += 1) {
    soma += Math.hypot(pontos[i].x - pontos[i - 1].x, pontos[i].y - pontos[i - 1].y)
  }
  return soma
}

/** Área do polígono (shoelace), fechando o último com o primeiro. */
export function area(pontos: Ponto[]): number {
  let soma = 0
  for (let i = 0; i < pontos.length; i += 1) {
    const a = pontos[i]
    const b = pontos[(i + 1) % pontos.length]
    soma += a.x * b.y - b.x * a.y
  }
  return Math.abs(soma) / 2
}

/**
 * O rótulo do traço enquanto se mede.
 *
 * **Sem escala não se escreve metro.** O valor sai em fração da largura da folha
 * e a tela diz isso — no canteiro, um número com unidade errada vira parede no
 * lugar errado, e é mais caro que não ter número nenhum.
 *
 * Área multiplica pelo QUADRADO do fator linear; usar o fator direto entregaria
 * um cômodo de 3 m².
 */
export function rotuloDaMedida(
  pontos: Ponto[],
  modo: Modo,
  escala: number | null,
  unidade: string,
): string {
  if (pontos.length < MINIMO_DE_PONTOS[modo]) return ''
  const ehArea = modo === 'area'
  const bruto = ehArea ? area(pontos) : comprimento(pontos)

  if (!escala) {
    return `${bruto.toFixed(3)} da largura${ehArea ? '²' : ''} · sem escala`
  }
  const valor = ehArea ? bruto * escala * escala : bruto * escala
  const casas = valor < 10 ? 2 : 1
  return `${valor.toFixed(casas).replace('.', ',')} ${unidade}${ehArea ? '²' : ''}`
}

/** A cor da situação. Aberta é decisão pendente (accent), fechada é conclusão. */
export function corDaSituacao(situacao: SituacaoMarcacao): PillKind {
  if (situacao === 'Open') return 'accent'
  if (situacao === 'In Progress') return 'info'
  if (situacao === 'Resolved') return 'good'
  return 'slate'
}

/** Marcação com âncora na folha — só essas viram pino sobre o desenho. */
export function temAncora(m: Marcacao): m is Marcacao & { ancora: Ponto } {
  const a = m.ancora as Partial<Ponto>
  return typeof a?.x === 'number' && typeof a?.y === 'number'
}

/**
 * Recorta um pedaço do desenho em volta da âncora e devolve um PNG.
 *
 * É o que carrega a marcação 2D para fora: o BCF não tem onde guardar um ponto
 * numa folha (é um formato centrado em modelo 3D), então o que o projetista
 * recebe é a **imagem do trecho** mais o tópico. Sem isto, a marcação chegaria
 * ao escritório dizendo "está errado" sem dizer onde.
 *
 * **Devolve `null` em vez de lançar**, e é decisão de produto: a captura roda no
 * navegador (`drawImage` de um SVG pode marcar o canvas como contaminado em
 * browser antigo) e falha com mais frequência do que se gostaria. Um ponto de
 * vista sem imagem ainda é válido no BCF — perder o apontamento inteiro para
 * salvar a foto seria trocar o essencial pelo acessório.
 */
export async function capturarRecorte(
  img: HTMLImageElement | null,
  ancora: Ponto,
): Promise<Blob | null> {
  if (!img?.naturalWidth) return null
  try {
    // 40% da largura em volta do ponto: perto o bastante para se reconhecer o
    // detalhe, largo o bastante para não virar um recorte sem contexto.
    const lado = Math.round(img.naturalWidth * 0.4)
    const cx = ancora.x * img.naturalWidth
    const cy = ancora.y * img.naturalWidth
    const sx = Math.max(0, Math.min(img.naturalWidth - lado, cx - lado / 2))
    const sy = Math.max(0, Math.min(img.naturalHeight - lado, cy - lado / 2))

    const canvas = document.createElement('canvas')
    canvas.width = 800
    canvas.height = 800
    const ctx = canvas.getContext('2d')
    if (!ctx) return null
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, 800, 800)
    ctx.drawImage(img, sx, sy, lado, Math.min(lado, img.naturalHeight), 0, 0, 800, 800)

    // A cruz que diz ONDE — sem ela o recorte é só um pedaço de planta.
    ctx.strokeStyle = '#E5484D'
    ctx.lineWidth = 4
    const px = ((cx - sx) / lado) * 800
    const py = ((cy - sy) / lado) * 800
    ctx.beginPath()
    ctx.arc(px, py, 26, 0, Math.PI * 2)
    ctx.moveTo(px - 40, py)
    ctx.lineTo(px + 40, py)
    ctx.moveTo(px, py - 40)
    ctx.lineTo(px, py + 40)
    ctx.stroke()

    return await new Promise((resolve) => canvas.toBlob((b) => resolve(b), 'image/png'))
  } catch {
    return null
  }
}
