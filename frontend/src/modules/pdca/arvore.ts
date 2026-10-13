import type { Atividade } from './types'

export interface LinhaDaArvore {
  atividade: Atividade
  nivel: number
  temFilhos: boolean
  aberta: boolean
}

/** A ordem da EAP: irmãos por `ordem`, depois por código, e cada galho logo
 *  abaixo do pai. É a mesma lista que a grade e o Gantt desenham — passar duas
 *  ordens diferentes para os dois é como as linhas desalinham. */
export function linhasVisiveis(
  atividades: Atividade[],
  fechados: ReadonlySet<number>,
): LinhaDaArvore[] {
  const filhosDe = new Map<number | null, Atividade[]>()
  for (const a of atividades) {
    const chave = a.pai ?? null
    const grupo = filhosDe.get(chave)
    if (grupo) grupo.push(a)
    else filhosDe.set(chave, [a])
  }
  for (const grupo of filhosDe.values()) {
    grupo.sort((x, y) => (x.ordem - y.ordem) || x.codigo.localeCompare(y.codigo, 'pt-BR'))
  }

  const saida: LinhaDaArvore[] = []
  /** Toda atividade alcançada a partir da raiz — mostrada **ou escondida**
   *  dentro de uma etapa recolhida. Contar só as mostradas fazia os filhos
   *  recolhidos passarem por órfãos e irem parar no fim do plano. */
  const alcancados = new Set<number>()
  function descer(pai: number | null, nivel: number, visivel: boolean) {
    for (const a of filhosDe.get(pai) ?? []) {
      alcancados.add(a.atividade_id)
      const filhos = filhosDe.get(a.atividade_id) ?? []
      const aberta = !fechados.has(a.atividade_id)
      if (visivel) saida.push({ atividade: a, nivel, temFilhos: filhos.length > 0, aberta })
      if (filhos.length > 0) descer(a.atividade_id, nivel + 1, visivel && aberta)
    }
  }
  descer(null, 0, true)

  /** Atividade cujo pai não está na lista ficaria invisível sem isto — e sumir
   *  em silêncio num plano é o defeito que ninguém encontra. */
  for (const a of atividades) {
    if (!alcancados.has(a.atividade_id)) {
      saida.push({ atividade: a, nivel: 0, temFilhos: false, aberta: true })
    }
  }
  return saida
}

export function todosOsPais(atividades: Atividade[]): number[] {
  const pais = new Set<number>()
  for (const a of atividades) if (a.pai != null) pais.add(a.pai)
  return [...pais]
}

const DIA_MS = 86_400_000

export function paraData(iso: string | null): Date | null {
  if (!iso) return null
  const [ano, mes, dia] = iso.slice(0, 10).split('-').map(Number)
  if (!ano || !mes || !dia) return null
  return new Date(ano, mes - 1, dia)
}

export function diasEntre(de: Date, ate: Date): number {
  return Math.round((ate.getTime() - de.getTime()) / DIA_MS)
}

export function somarDias(d: Date, dias: number): Date {
  const saida = new Date(d)
  saida.setDate(saida.getDate() + dias)
  return saida
}

export interface Janela {
  inicio: Date
  fim: Date
  dias: number
}

/** A janela que o Gantt desenha: do primeiro início ao último término, com
 *  folga nas pontas para a barra não encostar na borda. */
export function janelaDoPlano(atividades: Atividade[], base: (string | null)[] = []): Janela | null {
  const datas: Date[] = []
  for (const a of atividades) {
    const i = paraData(a.inicio_cedo)
    const t = paraData(a.termino_cedo)
    if (i) datas.push(i)
    if (t) datas.push(t)
  }
  for (const iso of base) {
    const d = paraData(iso)
    if (d) datas.push(d)
  }
  if (datas.length === 0) return null

  const min = new Date(Math.min(...datas.map((d) => d.getTime())))
  const max = new Date(Math.max(...datas.map((d) => d.getTime())))
  const inicio = somarDias(min, -3)
  const fim = somarDias(max, 3)
  return { inicio, fim, dias: Math.max(1, diasEntre(inicio, fim) + 1) }
}

export const MESES = [
  'jan', 'fev', 'mar', 'abr', 'mai', 'jun',
  'jul', 'ago', 'set', 'out', 'nov', 'dez',
]
