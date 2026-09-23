import { isoLocal } from '@/utils/dates'

/** A segunda-feira da semana de `iso`, em `YYYY-MM-DD`.
 *
 *  **A âncora é a mesma do servidor** (`services.segunda_da_semana`): a semana
 *  do Last Planner começa na segunda por convenção do método, e é isso que faz
 *  de `semana_inicio` uma chave natural em vez de um intervalo qualquer.
 *
 *  A conta é feita em `Date` **local** e volta por `isoLocal` de propósito.
 *  `new Date('2026-09-21')` é lido como meia-noite UTC, e quem está a oeste de
 *  Greenwich recebe o domingo anterior — a tela abriria uma semana antes da
 *  que o servidor abriria, e as duas nunca se encontrariam. */
export function segundaDaSemana(iso: string): string {
  const base = deIso(iso)
  const diaDaSemana = (base.getDay() + 6) % 7
  base.setDate(base.getDate() - diaDaSemana)
  return isoLocal(base)
}

/** `iso` deslocado em `dias` — o navegador da semana anda de sete em sete. */
export function somaDias(iso: string, dias: number): string {
  const base = deIso(iso)
  base.setDate(base.getDate() + dias)
  return isoLocal(base)
}

export function hojeIso(): string {
  return isoLocal(new Date())
}

/** "22/09 a 28/09" — o intervalo como a reunião o chama. O ano só aparece
 *  quando a semana atravessa a virada, que é quando ele deixa de ser óbvio. */
export function intervaloDaSemana(inicio: string, fim: string): string {
  const [ai, mi, di] = partes(inicio)
  const [af, mf, df] = partes(fim)
  if (ai !== af) return `${di}/${mi}/${ai} a ${df}/${mf}/${af}`
  return `${di}/${mi} a ${df}/${mf}`
}

/** Quantas semanas `iso` está à frente da semana corrente. Negativo é passado,
 *  zero é a semana em que se está. */
export function distanciaEmSemanas(inicio: string): number {
  const atual = deIso(segundaDaSemana(hojeIso())).getTime()
  const alvo = deIso(inicio).getTime()
  return Math.round((alvo - atual) / (7 * 24 * 60 * 60 * 1000))
}

/** "esta semana" · "semana que vem" · "há 3 semanas" — o rótulo que quem está
 *  na reunião usa. Fora da vizinhança imediata, o número é mais honesto que um
 *  advérbio: "há 7 semanas" diz o tamanho do atraso; "semanas atrás" não. */
export function rotuloDaSemana(inicio: string): string {
  const distancia = distanciaEmSemanas(inicio)
  if (distancia === 0) return 'esta semana'
  if (distancia === 1) return 'semana que vem'
  if (distancia === -1) return 'semana passada'
  return distancia > 0 ? `daqui a ${distancia} semanas` : `há ${-distancia} semanas`
}

/** Os sete dias da semana, para o cabeçalho do quadro. */
export function diasDaSemana(inicio: string): { iso: string; sigla: string; dia: string }[] {
  const siglas = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom']
  return siglas.map((sigla, i) => {
    const iso = somaDias(inicio, i)
    return { iso, sigla, dia: partes(iso)[2] }
  })
}

function partes(iso: string): [string, string, string] {
  const [ano, mes, dia] = (iso || '').split('-')
  return [ano ?? '', mes ?? '', dia ?? '']
}

/** `YYYY-MM-DD` → `Date` **local**, sem passar pelo parser de UTC. */
function deIso(iso: string): Date {
  const [ano, mes, dia] = (iso || '').split('-').map(Number)
  return new Date(ano || 1970, (mes || 1) - 1, dia || 1)
}
