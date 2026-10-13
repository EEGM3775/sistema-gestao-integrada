import type { LinhaImportada } from './api/montagemApi'

/** O que a tela leu de uma colagem ou de um arquivo — as linhas, e de onde
 *  saiu cada coluna, para a pré-visualização dizer o que entendeu antes de
 *  escrever qualquer coisa. */
export interface Leitura {
  linhas: LinhaImportada[]
  colunas: string[]
  /** `linha` quando as predecessoras apontam para o Id da linha (MS Project). */
  referencia: 'codigo' | 'linha'
  avisos: string[]
}

const CABECALHOS: [keyof LinhaImportada | 'id', RegExp][] = [
  ['id', /^(id|n[ºo°]?|#)$/i],
  ['codigo', /^(c[oó]d(igo)?|edt|eap|wbs|item)$/i],
  ['nivel', /^(n[ií]vel|n[ií]vel da estrutura.*|outline.*)$/i],
  ['nome', /^(nome( da tarefa)?|tarefa|atividade|servi[cç]o|descri[cç][aã]o|task name|name)$/i],
  ['duracao_dias', /^(dura[cç][aã]o|dur\.?|duration|dias)$/i],
  ['predecessoras', /^(predecessoras?|predecessors?|depende de)$/i],
  ['nao_comecar_antes_de', /^(in[ií]cio|start|come[cç]a)$/i],
  ['peso', /^(peso|weight)$/i],
]

const CODIGO = /^\d+(\.\d+)*\.?$/

/** "10 dias", "10d", "10,5", "0 dias" → "10", "10", "10.5", "0". */
function lerDuracao(texto: string): string | null {
  const limpo = texto.trim().toLowerCase().replace(',', '.')
  if (!limpo) return null
  const n = limpo.match(/^-?\d+(\.\d+)?/)
  if (!n) return null
  let valor = Number(n[0])
  if (/\b(sem|semanas?|w|wk)\b/.test(limpo)) valor *= 5
  else if (/\b(m[eê]s|meses|mo)\b/.test(limpo)) valor *= 20
  else if (/\b(h|horas?|hrs?)\b/.test(limpo)) valor /= 8
  return String(Math.round(valor))
}

/** "05/01/2027" ou "2027-01-05" → "2027-01-05". */
function lerData(texto: string): string | null {
  const t = texto.trim()
  const br = t.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/)
  if (br) {
    const ano = br[3].length === 2 ? `20${br[3]}` : br[3]
    return `${ano}-${br[2].padStart(2, '0')}-${br[1].padStart(2, '0')}`
  }
  const iso = t.match(/^(\d{4})-(\d{2})-(\d{2})/)
  return iso ? `${iso[1]}-${iso[2]}-${iso[3]}` : null
}

/** A colagem do Excel (ou de qualquer planilha): linhas por quebra, células
 *  por tabulação. Com cabeçalho, as colunas se acham pelo nome; sem ele, a
 *  ordem que o planejador mais usa — código, nome, duração, predecessoras.
 *  Recuo do nome (espaços à esquerda) vira nível, como o MS Project cola. */
export function lerColagem(texto: string): Leitura {
  const brutas = texto.replace(/\r/g, '').split('\n').filter((l) => l.trim() !== '')
  const avisos: string[] = []
  if (brutas.length === 0) return { linhas: [], colunas: [], referencia: 'codigo', avisos }
  const celulas = brutas.map((l) => l.split('\t'))

  let mapa: (keyof LinhaImportada | 'id' | null)[] = []
  let corpo = celulas
  const primeira = celulas[0]
  const reconhecidas = primeira.map((c) => CABECALHOS.find(([, re]) => re.test(c.trim()))?.[0] ?? null)
  if (reconhecidas.filter(Boolean).length >= 1 && reconhecidas.includes('nome')) {
    mapa = reconhecidas
    corpo = celulas.slice(1)
  } else {
    const largura = Math.max(...celulas.map((c) => c.length))
    const temCodigo = celulas.every((c) => c.length > 1 && CODIGO.test(c[0].trim()))
    if (largura === 1) mapa = ['nome']
    else if (temCodigo) mapa = ['codigo', 'nome', 'duracao_dias', 'predecessoras', 'nao_comecar_antes_de']
    else mapa = ['nome', 'duracao_dias', 'predecessoras', 'nao_comecar_antes_de']
  }

  const recuos = corpo.map((c) => {
    const i = mapa.indexOf('nome')
    const nome = i >= 0 ? c[i] ?? '' : ''
    return nome.length - nome.trimStart().length
  })
  const passo = Math.min(...recuos.filter((r) => r > 0), Infinity)
  const temNivel = mapa.includes('nivel') || mapa.includes('codigo')

  const linhas: LinhaImportada[] = corpo.map((c, indice) => {
    const linha: LinhaImportada = { nome: '' }
    mapa.forEach((campo, i) => {
      const valor = (c[i] ?? '').trim()
      if (!campo || !valor) return
      if (campo === 'nome') linha.nome = valor
      else if (campo === 'codigo') linha.codigo = valor.replace(/\.$/, '')
      else if (campo === 'nivel') linha.nivel = Number(valor) || null
      else if (campo === 'duracao_dias') {
        linha.duracao_dias = lerDuracao(valor)
        if (linha.duracao_dias === '0') linha.eh_marco = true
      } else if (campo === 'predecessoras') linha.predecessoras = valor
      else if (campo === 'nao_comecar_antes_de') linha.nao_comecar_antes_de = lerData(valor)
      else if (campo === 'peso') linha.peso = valor
    })
    if (!temNivel && Number.isFinite(passo)) {
      linha.nivel = 1 + Math.round(recuos[indice] / passo)
    }
    return linha
  })

  // Sem coluna de código, as predecessoras do Project apontam para o Id da linha.
  const referencia: 'codigo' | 'linha' = mapa.includes('codigo') ? 'codigo' : 'linha'
  const semNome = linhas.filter((l) => !l.nome).length
  if (semNome) avisos.push(`${semNome} linha(s) sem nome serão ignoradas.`)
  return {
    linhas: linhas.filter((l) => l.nome),
    colunas: mapa.filter((c): c is keyof LinhaImportada => !!c && c !== 'id').map(String),
    referencia,
    avisos,
  }
}

/** "PT80H0M0S" → horas. */
function horasDe(iso: string | null | undefined): number {
  if (!iso) return 0
  const m = iso.match(/P(?:(\d+)D)?T?(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?/)
  if (!m) return 0
  return Number(m[1] ?? 0) * 24 + Number(m[2] ?? 0) + Number(m[3] ?? 0) / 60
}

const TIPO_DO_PROJECT: Record<string, string> = { 0: 'FF', 1: 'FS', 2: 'SF', 3: 'SS' }

/** O XML do MS Project (Arquivo › Salvar como › XML). O `.mpp` é binário
 *  fechado e não se lê no navegador — a tela pede o XML, que todo Project
 *  exporta e que o ProjectLibre e o GanttProject também gravam. */
export function lerXmlDoProject(texto: string): Leitura {
  const avisos: string[] = []
  const doc = new DOMParser().parseFromString(texto, 'application/xml')
  if (doc.getElementsByTagName('parsererror').length) {
    return { linhas: [], colunas: [], referencia: 'codigo', avisos: ['O arquivo não é um XML válido.'] }
  }
  const filho = (el: Element, nome: string) => el.getElementsByTagName(nome)[0]?.textContent ?? null
  const minutosPorDia = Number(doc.getElementsByTagName('MinutesPerDay')[0]?.textContent ?? 480) || 480
  const horasPorDia = minutosPorDia / 60

  const tarefas = Array.from(doc.getElementsByTagName('Task')).filter((t) => {
    const nivel = Number(filho(t, 'OutlineLevel') ?? 1)
    return nivel >= 1 && (filho(t, 'Name') ?? '').trim() !== ''
  })
  if (tarefas.length === 0) avisos.push('Nenhuma tarefa encontrada no arquivo.')

  const codigoPorUid = new Map<string, string>()
  for (const t of tarefas) {
    const uid = filho(t, 'UID') ?? ''
    codigoPorUid.set(uid, filho(t, 'OutlineNumber') ?? filho(t, 'WBS') ?? uid)
  }

  const linhas: LinhaImportada[] = tarefas.map((t) => {
    const marco = filho(t, 'Milestone') === '1'
    const resumo = filho(t, 'Summary') === '1'
    const horas = horasDe(filho(t, 'Duration'))
    const ligacoes = Array.from(t.getElementsByTagName('PredecessorLink')).map((l) => {
      const ref = codigoPorUid.get(filho(l, 'PredecessorUID') ?? '')
      if (!ref) return null
      const tipo = TIPO_DO_PROJECT[filho(l, 'Type') ?? '1'] ?? 'FS'
      // LinkLag vem em décimos de minuto.
      const lag = Math.round(Number(filho(l, 'LinkLag') ?? 0) / 10 / minutosPorDia)
      return `${ref}${tipo}${lag ? (lag > 0 ? `+${lag}` : lag) : ''}`
    }).filter(Boolean)
    const restricao = filho(t, 'ConstraintType')
    const dataRestricao = filho(t, 'ConstraintDate')
    return {
      nome: (filho(t, 'Name') ?? '').trim(),
      codigo: filho(t, 'OutlineNumber') ?? undefined,
      nivel: Number(filho(t, 'OutlineLevel') ?? 1),
      duracao_dias: resumo ? null : String(Math.round(horas / horasPorDia)),
      eh_marco: marco,
      predecessoras: ligacoes.join('; '),
      // 4 = "Não iniciar antes de" no Project.
      nao_comecar_antes_de: restricao === '4' && dataRestricao ? dataRestricao.slice(0, 10) : null,
    }
  })
  return {
    linhas,
    colunas: ['codigo', 'nome', 'duracao_dias', 'predecessoras', 'nao_comecar_antes_de'],
    referencia: 'codigo',
    avisos,
  }
}

/** Texto de predecessoras como a coluna mostra: `1.2`, `1.3SS+2`, `4FF-1`. */
export function rotuloDaLigacao(codigo: string, tipo: string, atraso: number): string {
  return `${codigo}${tipo === 'FS' ? '' : tipo}${atraso ? (atraso > 0 ? `+${atraso}` : atraso) : ''}`
}

/** A mesma gramática que o servidor lê (`services.ler_predecessoras`). */
export function lerPredecessoras(texto: string): { ref: string; tipo: string; atraso: number }[] | string {
  const saida: { ref: string; tipo: string; atraso: number }[] = []
  const pt: Record<string, string> = { TI: 'FS', II: 'SS', TT: 'FF', IT: 'SF' }
  for (const pedaco of texto.split(/[;,]/)) {
    if (!pedaco.trim()) continue
    const m = pedaco.match(
      /^\s*([^\s;,+]+?)\s*(FS|SS|FF|SF|TI|II|TT|IT)?\s*(?:([+-]\s*\d+)\s*(?:d|du|dias?)?)?\s*$/i,
    )
    if (!m) return `Não entendi "${pedaco.trim()}". Use, por exemplo, 1.2 ou 1.2FS+3 ou 1.4SS.`
    const tipo = (m[2] ?? 'FS').toUpperCase()
    saida.push({ ref: m[1], tipo: pt[tipo] ?? tipo, atraso: m[3] ? Number(m[3].replace(/\s/g, '')) : 0 })
  }
  return saida
}

/** Dias úteis (seg–sex) entre duas datas, contando as duas pontas. É a conta do
 *  gesto de esticar a barra; o servidor refaz pelo calendário de verdade. */
export function diasUteisEntre(inicio: Date, fim: Date): number {
  let n = 0
  const d = new Date(inicio)
  while (d <= fim) {
    const dia = d.getDay()
    if (dia !== 0 && dia !== 6) n++
    d.setDate(d.getDate() + 1)
  }
  return Math.max(1, n)
}
