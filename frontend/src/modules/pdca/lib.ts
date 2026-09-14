import { isoLocal } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import type { Atividade, EstatisticasPlano, Precedencia, TipoPrecedencia } from './types'

/** Escalas do eixo do tempo. `px` é a largura de UM dia corrido em cada uma —
 *  é o único número que a geometria do Gantt precisa saber, porque toda posição
 *  é calculada a partir de dias corridos desde a origem do eixo. */
export const ESCALAS = {
  dia: { rotulo: 'Dia', px: 34 },
  semana: { rotulo: 'Semana', px: 11 },
  mes: { rotulo: 'Mês', px: 3.6 },
  trimestre: { rotulo: 'Trimestre', px: 1.3 },
} as const

export type ChaveEscala = keyof typeof ESCALAS

const MS_DIA = 86_400_000

/** ISO (AAAA-MM-DD) → Date **local**, sem o deslocamento de fuso que
 *  `new Date('2026-06-01')` introduz (ele lê como UTC e, a oeste de Greenwich,
 *  devolve 31/05). Num Gantt esse erro move toda barra um dia para a esquerda. */
export function daIso(iso: string): Date {
  const [a, m, d] = iso.split('-').map(Number)
  return new Date(a, (m ?? 1) - 1, d ?? 1)
}

export const paraIso = isoLocal

export function diasEntre(inicio: Date, fim: Date): number {
  return Math.round((fim.getTime() - inicio.getTime()) / MS_DIA)
}

export function somarDias(base: Date, dias: number): Date {
  const saida = new Date(base)
  saida.setDate(saida.getDate() + dias)
  return saida
}

export interface EixoDoTempo {
  origem: Date
  fim: Date
  pxPorDia: number
  largura: number
  x: (iso: string) => number
  data: (x: number) => Date
}

/** O eixo horizontal: origem, fim e as duas conversões entre data e pixel.
 *  A margem de 3 dias antes e 10 depois existe para a barra do primeiro dia não
 *  nascer colada na borda e para haver espaço de arrasto além do fim do plano. */
export function montarEixo(
  atividades: Atividade[], inicioPlano: string, escala: ChaveEscala, zoom = 1,
): EixoDoTempo {
  const datas: Date[] = [daIso(inicioPlano)]
  for (const a of atividades) {
    if (a.inicio_cedo) datas.push(daIso(a.inicio_cedo))
    if (a.termino_cedo) datas.push(daIso(a.termino_cedo))
  }
  const menor = new Date(Math.min(...datas.map(d => d.getTime())))
  const maior = new Date(Math.max(...datas.map(d => d.getTime())))
  const origem = somarDias(menor, -3)
  const fim = somarDias(maior, 10)
  const pxPorDia = pxDaEscala(escala, zoom)
  const largura = Math.max(diasEntre(origem, fim) * pxPorDia, 320)

  return {
    origem, fim, pxPorDia, largura,
    x: (iso: string) => diasEntre(origem, daIso(iso)) * pxPorDia,
    data: (x: number) => somarDias(origem, Math.round(x / pxPorDia)),
  }
}

export interface Marcacao { x: number; rotulo: string; forte: boolean }

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

/** As marcas do cabeçalho da linha do tempo. Cada escala tem a sua unidade —
 *  desenhar todos os dias numa escala trimestral produziria milhares de traços
 *  ilegíveis e travaria a rolagem. */
export function marcacoes(eixo: EixoDoTempo, escala: ChaveEscala): Marcacao[] {
  const saida: Marcacao[] = []
  const total = diasEntre(eixo.origem, eixo.fim)

  if (escala === 'dia') {
    for (let i = 0; i <= total; i++) {
      const d = somarDias(eixo.origem, i)
      saida.push({
        x: i * eixo.pxPorDia,
        rotulo: String(d.getDate()),
        forte: d.getDay() === 1,
      })
    }
    return saida
  }
  if (escala === 'semana') {
    for (let i = 0; i <= total; i++) {
      const d = somarDias(eixo.origem, i)
      if (d.getDay() !== 1) continue
      saida.push({
        x: i * eixo.pxPorDia,
        rotulo: `${d.getDate()}/${MESES[d.getMonth()]}`,
        forte: d.getDate() <= 7,
      })
    }
    return saida
  }
  for (let i = 0; i <= total; i++) {
    const d = somarDias(eixo.origem, i)
    if (d.getDate() !== 1) continue
    const trimestral = escala === 'trimestre'
    if (trimestral && d.getMonth() % 3 !== 0) continue
    saida.push({
      x: i * eixo.pxPorDia,
      rotulo: trimestral
        ? `${MESES[d.getMonth()]}/${String(d.getFullYear()).slice(2)}`
        : MESES[d.getMonth()],
      forte: d.getMonth() === 0,
    })
  }
  return saida
}

/** Faixas de fim de semana, para o olho ler a semana sem contar quadradinho.
 *  Só na escala de dia e de semana: abaixo disso viram listras de moiré. */
export function fimDeSemana(eixo: EixoDoTempo, escala: ChaveEscala): { x: number; largura: number }[] {
  if (escala !== 'dia' && escala !== 'semana') return []
  const saida: { x: number; largura: number }[] = []
  const total = diasEntre(eixo.origem, eixo.fim)
  for (let i = 0; i <= total; i++) {
    const d = somarDias(eixo.origem, i)
    if (d.getDay() === 6) saida.push({ x: i * eixo.pxPorDia, largura: eixo.pxPorDia * 2 })
  }
  return saida
}

export interface LinhaDaArvore {
  atividade: Atividade
  nivel: number
  temFilhos: boolean
  aberta: boolean
}

/** A WBS achatada na ordem em que a tela desenha, respeitando o que está
 *  recolhido. É esta lista — e não a árvore — que a virtualização fatia. */
export function achatarArvore(
  atividades: Atividade[], recolhidas: ReadonlySet<number>,
): LinhaDaArvore[] {
  const porPai = new Map<number | null, Atividade[]>()
  for (const a of atividades) {
    const chave = a.pai ?? null
    const lista = porPai.get(chave) ?? []
    lista.push(a)
    porPai.set(chave, lista)
  }
  for (const lista of porPai.values()) {
    lista.sort((x, y) => x.ordem - y.ordem || x.codigo.localeCompare(y.codigo, 'pt-BR', { numeric: true }))
  }

  const saida: LinhaDaArvore[] = []
  const descer = (pai: number | null, nivel: number) => {
    for (const a of porPai.get(pai) ?? []) {
      const filhos = porPai.get(a.atividade_id) ?? []
      const aberta = !recolhidas.has(a.atividade_id)
      saida.push({ atividade: a, nivel, temFilhos: filhos.length > 0, aberta })
      if (filhos.length > 0 && aberta) descer(a.atividade_id, nivel + 1)
    }
  }
  descer(null, 0)
  return saida
}

export interface SetaDesenhada {
  precedencia: Precedencia
  caminho: string
  critica: boolean
  /** O ponto onde o rótulo do tipo e do atraso é escrito — o trecho horizontal
   *  do meio, que é o único que não corre risco de ficar embaixo de uma barra. */
  meio: { x: number; y: number }
}

/** As setas entre barras, em caminho SVG ortogonal (o traçado que P6 e MS
 *  Project usam: sai, contorna e chega). Curva livre atravessaria barras e
 *  faria o olho perder de onde a seta partiu. */
export function tracarSetas(
  precedencias: Precedencia[],
  linhaDe: Map<number, number>,
  atividades: Map<number, Atividade>,
  eixo: EixoDoTempo,
  alturaLinha: number,
  alturaBarra: number,
): SetaDesenhada[] {
  const saida: SetaDesenhada[] = []
  const meio = (linha: number) => linha * alturaLinha + alturaLinha / 2

  for (const p of precedencias) {
    const linhaOrigem = linhaDe.get(p.origem)
    const linhaDestino = linhaDe.get(p.destino)
    const origem = atividades.get(p.origem)
    const destino = atividades.get(p.destino)
    if (linhaOrigem == null || linhaDestino == null || !origem || !destino) continue
    if (!origem.termino_cedo || !destino.inicio_cedo || !origem.inicio_cedo) continue

    const saiDoFim = p.tipo === 'FS' || p.tipo === 'FF'
    const chegaNoFim = p.tipo === 'FF' || p.tipo === 'SF'
    const x1 = saiDoFim
      ? eixo.x(origem.termino_cedo) + eixo.pxPorDia
      : eixo.x(origem.inicio_cedo)
    const x2 = chegaNoFim
      ? eixo.x(destino.termino_cedo ?? destino.inicio_cedo) + eixo.pxPorDia
      : eixo.x(destino.inicio_cedo)
    const y1 = meio(linhaOrigem)
    const y2 = meio(linhaDestino)

    const recuo = Math.max(eixo.pxPorDia * 0.6, 8)
    const meioY = y1 < y2 ? y1 + alturaBarra / 2 + 4 : y1 - alturaBarra / 2 - 4
    const caminho = [
      `M ${x1} ${y1}`,
      `L ${x1 + recuo} ${y1}`,
      `L ${x1 + recuo} ${meioY}`,
      `L ${x2 - recuo} ${meioY}`,
      `L ${x2 - recuo} ${y2}`,
      `L ${x2} ${y2}`,
    ].join(' ')

    saida.push({
      precedencia: p,
      caminho,
      critica: origem.critica && destino.critica,
      meio: { x: (x1 + recuo + x2 - recuo) / 2, y: meioY },
    })
  }
  return saida
}

export function rotuloFolga(atividade: Atividade): string {
  if (atividade.critica) return 'Caminho crítico'
  if (atividade.folga_total == null) return 'Sem cálculo'
  return `${atividade.folga_total} d de folga`
}

/** "Sem apuração" em vez de zero: a atividade sem régua de custo não tem peso,
 *  e mostrar 0 faria o avanço do pai parecer calculado quando não é. */
export function rotuloPeso(atividade: Atividade): string {
  if (atividade.peso == null) return 'sem apuração'
  const numero = Number(atividade.peso)
  if (atividade.peso_origem === 'orcado') {
    return numero.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
  }
  return numero.toLocaleString('pt-BR', { maximumFractionDigits: 2 })
}

// ---------------------------------------------------------------------------
// Zoom — a escala grossa, e o ajuste fino dentro dela
// ---------------------------------------------------------------------------

/** Fatores de zoom aceitos. O passo é multiplicativo (e não +10 px) porque a
 *  percepção de escala é logarítmica: somar 10 px num dia de 34 px quase não se
 *  vê, e num trimestre de 1,3 px muda tudo. */
export const ZOOM_MIN = 0.4
export const ZOOM_MAX = 4

export function pxDaEscala(escala: ChaveEscala, zoom: number): number {
  return ESCALAS[escala].px * Math.min(Math.max(zoom, ZOOM_MIN), ZOOM_MAX)
}

/** A escala cujo `px` mais aproxima o plano inteiro da largura disponível —
 *  o "ajustar à janela" do P6. Devolve a escala **e** o zoom que fecham a
 *  conta, porque só a escala erraria por até 3× para cada lado. */
export function ajustarAJanela(
  atividades: Atividade[], inicioPlano: string, larguraDisponivel: number,
): { escala: ChaveEscala; zoom: number } {
  const eixo = montarEixo(atividades, inicioPlano, 'dia', 1)
  const dias = Math.max(diasEntre(eixo.origem, eixo.fim), 1)
  const alvo = Math.max(larguraDisponivel - 24, 320) / dias
  let melhor: ChaveEscala = 'dia'
  for (const chave of Object.keys(ESCALAS) as ChaveEscala[]) {
    const zoom = alvo / ESCALAS[chave].px
    if (zoom >= ZOOM_MIN && zoom <= ZOOM_MAX) melhor = chave
  }
  return { escala: melhor, zoom: Math.min(Math.max(alvo / ESCALAS[melhor].px, ZOOM_MIN), ZOOM_MAX) }
}

/** Hoje em ISO local — a linha vertical que dá sentido a "atrasou". */
export function hojeIso(): string {
  return paraIso(new Date())
}

// ---------------------------------------------------------------------------
// A cadeia — o que empurra e o que é empurrado por uma atividade
// ---------------------------------------------------------------------------

/** Tudo que leva a `id` (montante) e tudo que ele leva (jusante), atravessando
 *  a rede inteira. É a leitura que responde *"se esta atrasar, quem atrasa?"* —
 *  e no Gantt ela vira o realce que apaga o resto do plano. */
export function cadeiaDe(id: number, precedencias: Precedencia[]): {
  montante: Set<number>
  jusante: Set<number>
} {
  const paraTras = new Map<number, number[]>()
  const paraFrente = new Map<number, number[]>()
  for (const p of precedencias) {
    paraTras.set(p.destino, [...(paraTras.get(p.destino) ?? []), p.origem])
    paraFrente.set(p.origem, [...(paraFrente.get(p.origem) ?? []), p.destino])
  }
  const caminhar = (mapa: Map<number, number[]>) => {
    const vistos = new Set<number>()
    const pilha = [...(mapa.get(id) ?? [])]
    while (pilha.length) {
      const no = pilha.pop() as number
      if (vistos.has(no)) continue
      vistos.add(no)
      pilha.push(...(mapa.get(no) ?? []))
    }
    return vistos
  }
  return { montante: caminhar(paraTras), jusante: caminhar(paraFrente) }
}

// ---------------------------------------------------------------------------
// A curva S **não** mora mais aqui (PDCA.2)
// ---------------------------------------------------------------------------
//
// Até a PDCA.1b, `curvaSPrevista()` desenhava o previsto neste arquivo,
// distribuindo o peso linearmente nos **dias corridos** de cada barra — uma
// aproximação declarada, porque o calendário mora no servidor.
//
// A PDCA.2 a levou para lá inteira (`GET /api/pdca/cronogramas/{id}/curva-s/`),
// e não por organização: a curva **realizada** cruza apontamento com peso, e o
// peso vem do orçamento — duas tabelas que o navegador não tem. Com as duas
// linhas no mesmo gráfico, uma calculada por dias corridos e outra por data de
// apontamento, o desvio entre elas carregaria o erro de fim de semana da
// aproximação: o número que a reunião de obra lê é justamente esse desvio.
// Agora o previsto é distribuído nos dias úteis do calendário de cada atividade,
// que é a régua com que o CPM produziu as datas.

// ---------------------------------------------------------------------------
// Estatísticas — o que um planejador olha antes de assinar embaixo
// ---------------------------------------------------------------------------

export function estatisticasDoPlano(
  atividades: Atividade[], precedencias: Precedencia[],
): EstatisticasPlano {
  const folhas = atividades.filter(a => !a.tem_filhos)
  const ligadas = new Set<number>()
  for (const p of precedencias) { ligadas.add(p.origem); ligadas.add(p.destino) }

  const inicios = atividades.map(a => a.inicio_cedo).filter(Boolean) as string[]
  const terminos = atividades.map(a => a.termino_cedo).filter(Boolean) as string[]
  const inicio = inicios.length ? inicios.reduce((a, b) => (a < b ? a : b)) : null
  const termino = terminos.length ? terminos.reduce((a, b) => (a > b ? a : b)) : null

  const naoCriticas = folhas.filter(a => !a.critica && a.folga_total != null)
  const folgaMedia = naoCriticas.length
    ? naoCriticas.reduce((s, a) => s + (a.folga_total as number), 0) / naoCriticas.length
    : null

  return {
    atividades: atividades.length,
    folhas: folhas.length,
    sinteticas: atividades.length - folhas.length,
    marcos: atividades.filter(a => a.eh_marco).length,
    criticas: atividades.filter(a => a.critica).length,
    precedencias: precedencias.length,
    densidade: folhas.length ? Number((precedencias.length / folhas.length).toFixed(2)) : null,
    folhasSemLigacao: folhas.filter(a => !ligadas.has(a.atividade_id)).length,
    inicio,
    termino,
    duracaoDiasCorridos: inicio && termino ? diasEntre(daIso(inicio), daIso(termino)) + 1 : null,
    folgaMedia: folgaMedia == null ? null : Number(folgaMedia.toFixed(1)),
    comRestricaoDeData: atividades.filter(a => a.nao_comecar_antes_de).length,
  }
}

// ---------------------------------------------------------------------------
// A coluna de predecessoras — o gesto que vem do MS Project no dedo de quem usa
// ---------------------------------------------------------------------------
//
// Ninguém que planeja obra grande liga 800 setas com o mouse. No MS Project a
// rede é digitada numa coluna de texto — `12FS+3` — e é esse gesto que esta
// coluna reproduz, com uma diferença deliberada: aqui a referência é o **código
// da EAP**, não o número da linha. Número de linha muda quando alguém insere
// uma atividade acima; código não muda, e é o mesmo identificador por onde a
// importação de MS Project/P6 vai reencontrar a atividade depois.

/** `1.2FS+3d; 1.4SS` — o que a célula mostra. FS sem atraso aparece só como o
 *  código, que é a forma curta que o planejador espera ver. */
export function textoDePredecessoras(
  atividade: Atividade, precedencias: Precedencia[], porId: Map<number, Atividade>,
): string {
  return precedencias
    .filter(p => p.destino === atividade.atividade_id)
    .map(p => {
      const codigo = porId.get(p.origem)?.codigo ?? p.origem_codigo ?? String(p.origem)
      const tipo = p.tipo === 'FS' ? '' : p.tipo
      const atraso = p.atraso_dias ? `${p.atraso_dias > 0 ? '+' : ''}${p.atraso_dias}d` : ''
      return `${codigo}${tipo}${atraso}`
    })
    .join('; ')
}

export interface PredecessoraLida {
  origem: number
  tipo: TipoPrecedencia
  atraso_dias: number
}

const TIPOS: TipoPrecedencia[] = ['FS', 'SS', 'FF', 'SF']

/** Lê o que foi digitado na célula. Devolve **erro com o texto ofensor**, nunca
 *  uma lista parcial: aplicar metade de uma rede digitada deixaria o plano num
 *  estado que ninguém pediu e que é difícil de desfazer no olho. */
export function interpretarPredecessoras(
  texto: string, porCodigo: Map<string, Atividade>, destino: Atividade,
): { ok: true; itens: PredecessoraLida[] } | { ok: false; erro: string } {
  const itens: PredecessoraLida[] = []
  const vistos = new Set<number>()

  for (const bruto of texto.split(/[;,]/)) {
    const token = bruto.replace(/\s+/g, '')
    if (!token) continue

    let resto = token
    let atraso = 0
    const casaAtraso = resto.match(/([+-]\d+)(?:d|dias?)?$/i)
    if (casaAtraso) {
      atraso = Number(casaAtraso[1])
      resto = resto.slice(0, -casaAtraso[0].length)
    }

    // O sufixo de tipo só é cortado quando o texto inteiro NÃO é um código
    // conhecido: uma atividade batizada de "1.FS" existe, e decapitá-la em
    // silêncio ligaria a seta na atividade errada.
    let tipo: TipoPrecedencia = 'FS'
    const sufixo = resto.slice(-2).toUpperCase() as TipoPrecedencia
    if (TIPOS.includes(sufixo) && !porCodigo.has(resto)) {
      tipo = sufixo
      resto = resto.slice(0, -2)
    }

    const origem = porCodigo.get(resto)
    if (!origem) return { ok: false, erro: `Não existe atividade com o código "${resto}".` }
    if (origem.atividade_id === destino.atividade_id) {
      return { ok: false, erro: 'Uma atividade não precede a si mesma.' }
    }
    if (origem.tem_filhos) {
      return {
        ok: false,
        erro: `"${origem.codigo}" é sintética (tem filhas). A precedência liga as folhas.`,
      }
    }
    if (vistos.has(origem.atividade_id)) {
      return { ok: false, erro: `"${origem.codigo}" aparece duas vezes.` }
    }
    vistos.add(origem.atividade_id)
    itens.push({ origem: origem.atividade_id, tipo, atraso_dias: atraso })
  }
  return { ok: true, itens }
}

/** O que mudou entre o que está gravado e o que foi digitado. Três listas, e é
 *  isso que evita apagar e recriar a rede inteira a cada Enter. */
export function diferencaDePredecessoras(
  atuais: Precedencia[], lidas: PredecessoraLida[],
): {
  criar: PredecessoraLida[]
  atualizar: { id: number; payload: Partial<Precedencia> }[]
  excluir: number[]
} {
  const porOrigem = new Map(atuais.map(p => [p.origem, p]))
  const desejadas = new Set(lidas.map(l => l.origem))
  const criar: PredecessoraLida[] = []
  const atualizar: { id: number; payload: Partial<Precedencia> }[] = []

  for (const lida of lidas) {
    const atual = porOrigem.get(lida.origem)
    if (!atual) { criar.push(lida); continue }
    if (atual.tipo !== lida.tipo || atual.atraso_dias !== lida.atraso_dias) {
      atualizar.push({
        id: atual.precedencia_id,
        payload: { tipo: lida.tipo, atraso_dias: lida.atraso_dias },
      })
    }
  }
  const excluir = atuais.filter(p => !desejadas.has(p.origem)).map(p => p.precedencia_id)
  return { criar, atualizar, excluir }
}

// ---------------------------------------------------------------------------
// Códigos da EAP
// ---------------------------------------------------------------------------

/** O código que a linha nova recebe: o do pai mais o próximo número livre entre
 *  os irmãos. Sugestão, não imposição — o campo continua editável, porque obra
 *  pública costuma trazer a numeração do edital. */
export function proximoCodigo(pai: Atividade | null, irmaos: Atividade[]): string {
  const prefixo = pai ? `${pai.codigo}.` : ''
  let maior = 0
  for (const irmao of irmaos) {
    const cauda = pai ? irmao.codigo.slice(prefixo.length) : irmao.codigo
    const numero = Number(cauda.split('.')[0])
    if (Number.isFinite(numero) && numero > maior) maior = numero
  }
  return `${prefixo}${maior + 1}`
}

/* A renumeração da EAP **não** mora aqui: ela é do servidor
 * (`POST /api/pdca/cronogramas/{id}/renumerar-eap/`). O motivo é a trava de
 * unicidade do código — trocar `1.2` por `1.1` exige levar todos os que mudam
 * para um nome temporário antes de assentar qualquer definitivo, e as duas
 * passadas têm de caber na mesma transação. Calcular aqui e mandar em blocos,
 * que é o que o teto por chamada obrigaria, faria um código do segundo bloco
 * colidir com o primeiro. */

// ---------------------------------------------------------------------------
// Levar o plano para fora — a reunião e a planilha
// ---------------------------------------------------------------------------

/** A grade como CSV, com **as colunas que estão na tela**.
 *
 *  Separador `;` e decimal com vírgula: é o que o Excel em português abre com
 *  duplo clique. Vírgula e ponto obrigariam o assistente de importação, e
 *  ninguém faz isso duas vezes. BOM na frente pelo mesmo motivo — sem ele,
 *  "Fundação" vira "FundaÃ§Ã£o" na abertura padrão. */
export function csvDaGrade(
  linhas: LinhaDaArvore[],
  colunas: { chave: string; rotulo: string }[],
  celula: (a: Atividade, chave: string) => string,
): string {
  const escapar = (texto: string) =>
    /[;"\n]/.test(texto) ? '"' + texto.replace(/"/g, '""') + '"' : texto

  const cabecalho = ['Nível', ...colunas.map(c => c.rotulo)].map(escapar).join(';')
  const corpo = linhas.map(l => [
    String(l.nivel + 1),
    ...colunas.map(c => escapar(celula(l.atividade, c.chave))),
  ].join(';'))
  return '﻿' + [cabecalho, ...corpo].join('\r\n')
}

/** Dispara o download de um texto gerado na própria máquina de quem clicou. */
export function baixarTexto(nome: string, conteudo: string, tipo: string) {
  const url = URL.createObjectURL(new Blob([conteudo], { type: tipo }))
  const ancora = document.createElement('a')
  ancora.href = url
  ancora.download = nome
  ancora.click()
  URL.revokeObjectURL(url)
}

/** O Gantt como PNG, desenhado pelo próprio navegador.
 *
 *  Sem servidor e sem biblioteca: o SVG vira uma imagem por `data:` URI e é
 *  pintado num canvas. **Os estilos precisam viajar embutidos** — o SVG dentro
 *  de uma `<img>` não enxerga o CSS da página, e o que sai sem isso é um
 *  desenho preto sobre transparente. Por isso as cores são resolvidas antes,
 *  token por token, contra o elemento vivo.
 */
export async function pngDoSvg(svg: SVGSVGElement, fundo: string): Promise<Blob> {
  const copia = svg.cloneNode(true) as SVGSVGElement
  const largura = svg.width.baseVal.value || svg.getBoundingClientRect().width
  const altura = svg.height.baseVal.value || svg.getBoundingClientRect().height

  // `var(--x)` não resolve dentro da imagem: troca cada um pelo valor computado.
  const estilo = getComputedStyle(svg)
  const resolver = (no: Element) => {
    for (const atributo of ['fill', 'stroke']) {
      const valor = no.getAttribute(atributo)
      const casa = valor?.match(/^var\((--[\w-]+)\)$/)
      if (casa) no.setAttribute(atributo, estilo.getPropertyValue(casa[1]).trim() || '#888')
    }
    for (const filho of Array.from(no.children)) resolver(filho)
  }
  resolver(copia)
  copia.setAttribute('xmlns', 'http://www.w3.org/2000/svg')

  const fonte = new XMLSerializer().serializeToString(copia)
  const imagem = new Image()
  imagem.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(fonte)
  await new Promise((ok, erro) => { imagem.onload = ok; imagem.onerror = erro })

  const escala = Math.min(window.devicePixelRatio || 1, 2)
  const tela = document.createElement('canvas')
  tela.width = Math.ceil(largura * escala)
  tela.height = Math.ceil(altura * escala)
  const pincel = tela.getContext('2d')
  if (!pincel) throw new Error('O navegador não permitiu desenhar a imagem.')
  pincel.scale(escala, escala)
  pincel.fillStyle = fundo
  pincel.fillRect(0, 0, largura, altura)
  pincel.drawImage(imagem, 0, 0, largura, altura)

  return await new Promise<Blob>((ok, erro) =>
    tela.toBlob(b => (b ? ok(b) : erro(new Error('Não foi possível gerar o PNG.'))), 'image/png'),
  )
}

// ---------------------------------------------------------------------------
// Erro de API em uma frase
// ---------------------------------------------------------------------------

/** A primeira mensagem que o servidor devolveu, ou uma frase genérica.
 *
 *  Mora aqui porque as recusas deste módulo são **texto de domínio** — "a
 *  atividade 1.2 é sintética", "o acumulado passaria de 100%" —, e engoli-las
 *  por um "erro ao salvar" apagaria exatamente a parte útil. */
export function primeiraMensagem(e: unknown): string {
  const erros = parseApiErrors(e)
  const primeiro = Object.values(erros)[0]
  return primeiro || 'Não foi possível concluir a operação.'
}
