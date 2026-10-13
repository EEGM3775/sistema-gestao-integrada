/** "Este dia é útil?" no cliente — com a mesma precedência do `eh_dia_util`
 *  do servidor: **exceção** do dia > **feriado** > regra da semana. Serve ao
 *  Gantt para cortar a barra nos dias parados e para a ponta esticada contar a
 *  duração em dias úteis de verdade (com feriado), e não só de segunda a sexta. */
import type { Atividade, ExpedienteDoGantt, ExpedientesDoPlano } from './types'

export interface Expediente {
  nome: string
  ehUtil: (d: Date) => boolean
  /** Por que o dia está parado — o nome do feriado, o motivo da exceção. */
  porque: (d: Date) => string | null
  /** O dia é parado por data avulsa (feriado/exceção), e não pela semana? */
  avulso: (d: Date) => boolean
}

const DIAS = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado']

function chave(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function montarExpediente(cal: ExpedienteDoGantt | undefined): Expediente | null {
  if (!cal) return null
  const feriados = new Map(cal.feriados.map((f) => [f.data, f.nome]))
  const excecoes = new Map(cal.excecoes.map((e) => [e.data, e]))
  // getDay(): 0 = domingo; o servidor manda segunda primeiro (0 = segunda).
  const semana = (d: Date) => cal.dias_da_semana[(d.getDay() + 6) % 7] ?? true
  return {
    nome: cal.nome,
    ehUtil(d) {
      const k = chave(d)
      const exc = excecoes.get(k)
      if (exc) return exc.trabalha
      if (feriados.has(k)) return false
      return semana(d)
    },
    porque(d) {
      const k = chave(d)
      const exc = excecoes.get(k)
      if (exc) return exc.trabalha ? null : (exc.motivo || 'exceção do expediente')
      const feriado = feriados.get(k)
      if (feriado) return `feriado: ${feriado}`
      return semana(d) ? null : `${DIAS[d.getDay()]} sem expediente`
    },
    avulso(d) {
      const k = chave(d)
      const exc = excecoes.get(k)
      return exc ? !exc.trabalha : feriados.has(k)
    },
  }
}

/** O expediente de cada atividade (o próprio, ou o do plano que ela herda). */
export function expedientesDoGantt(blocos: ExpedientesDoPlano | undefined) {
  const porId = new Map<number, Expediente>()
  for (const [id, cal] of Object.entries(blocos?.calendarios ?? {})) {
    const e = montarExpediente(cal)
    if (e) porId.set(Number(id), e)
  }
  const doPlano = blocos?.calendario_do_plano != null ? porId.get(blocos.calendario_do_plano) ?? null : null
  return {
    doPlano,
    daAtividade: (a: Atividade): Expediente | null =>
      (a.calendario != null ? porId.get(a.calendario) : undefined) ?? doPlano,
  }
}

/** Dias úteis entre duas datas, **incluindo as duas pontas**. */
export function contarDiasUteis(exp: Expediente, inicio: Date, fim: Date): number {
  let n = 0
  const d = new Date(inicio)
  while (d <= fim) {
    if (exp.ehUtil(d)) n++
    d.setDate(d.getDate() + 1)
  }
  return Math.max(1, n)
}
