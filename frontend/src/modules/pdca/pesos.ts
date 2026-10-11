/** O peso **em proporção** — quanto cada linha conta na etapa e na obra.
 *
 *  O peso informado é um número solto (5, 15, 120): sozinho ele não diz nada, e
 *  mudá-lo "não mexia na porcentagem" porque porcentagem nenhuma aparecia. O que
 *  importa é a parcela: 5 de um total de 60 é 8,3% da obra. A etapa vale a soma
 *  das filhas (o `peso` derivado do avanço), e a obra, a soma das etapas. */
import type { Atividade, AvancoDoCronograma } from './types'

export function pesoDe(avanco: AvancoDoCronograma, id: number): number | null {
  const v = avanco.por_atividade[String(id)]?.peso
  if (v == null) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

/** A soma das raízes — que é a soma de todas as folhas com peso. */
export function pesoDaObra(avanco: AvancoDoCronograma, atividades: Atividade[]): number {
  return atividades
    .filter((a) => a.pai == null)
    .reduce((s, a) => s + (pesoDe(avanco, a.atividade_id) ?? 0), 0)
}

export function parcela(peso: number | null, total: number | null | undefined): number | null {
  if (peso == null || !total) return null
  return (peso / total) * 100
}

/** Décimos de ponto percentual: 100% = 1000. É a casa que a tela mostra. */
const CEM_POR_CENTO = 1000

/** Reparte `unidades` entre os pesos **pelo maior resto**, para a soma fechar.
 *
 *  Arredondar cada parcela sozinha não fecha: três etapas iguais davam 33% +
 *  33% + 33% = 99%, e o dono viu o total não bater 100% (09/10/2026). O maior
 *  resto arredonda para baixo e dá o que sobrou a quem perdeu mais no corte.
 *  Peso nulo fica fora — não pondera nada, e nada recebe. */
export function rateioQueFecha(pesos: (number | null)[], unidades = CEM_POR_CENTO): (number | null)[] {
  const total = pesos.reduce<number>((s, p) => s + (p ?? 0), 0)
  if (total <= 0) return pesos.map(() => null)
  const brutos = pesos.map((p) => (p == null ? null : (p / total) * unidades))
  const pisos = brutos.map((b) => (b == null ? null : Math.floor(b)))
  let sobra = unidades - pisos.reduce<number>((s, p) => s + (p ?? 0), 0)
  const porResto = brutos
    .map((b, i) => ({ i, resto: b == null ? -1 : b - Math.floor(b) }))
    .filter((x) => x.resto >= 0)
    .sort((x, y) => y.resto - x.resto)
  for (const { i } of porResto) {
    if (sobra <= 0) break
    pisos[i] = (pisos[i] ?? 0) + 1
    sobra -= 1
  }
  return pisos
}

/** A parcela de cada linha **na obra**, em %, já arredondada para fechar.
 *
 *  Descendo pela árvore: as raízes repartem 100%, e cada etapa reparte entre as
 *  filhas exatamente o que recebeu — então as filhas somam a mãe, e as raízes
 *  somam 100,0%. Funciona com a árvore recolhida: a linha visível só depende
 *  das irmãs e dos ancestrais, e esses estão visíveis junto com ela. */
export function fatiasDaObra(avanco: AvancoDoCronograma, atividades: Atividade[]): Map<number, number> {
  const filhas = new Map<number | null, Atividade[]>()
  for (const a of atividades) {
    const lista = filhas.get(a.pai) ?? []
    lista.push(a)
    filhas.set(a.pai, lista)
  }
  const fatias = new Map<number, number>()
  const repartir = (pai: number | null, unidades: number) => {
    const grupo = filhas.get(pai) ?? []
    const partes = rateioQueFecha(grupo.map((a) => pesoDe(avanco, a.atividade_id)), unidades)
    grupo.forEach((a, i) => {
      const u = partes[i]
      if (u == null) return
      fatias.set(a.atividade_id, u / 10)
      repartir(a.atividade_id, u)
    })
  }
  repartir(null, CEM_POR_CENTO)
  return fatias
}

export function emPercentual(n: number | null | undefined): string {
  if (n == null) return '—'
  return `${n.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`
}
