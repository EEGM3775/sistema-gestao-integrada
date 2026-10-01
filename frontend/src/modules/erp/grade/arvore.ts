import type { GrupoApi, ItemGrade, NoGrupo } from './tipos'

const SEP = '␟'

export const idDoNo = (no: { chaves: string[] }) => no.chaves.join(SEP)

/** Monta a árvore a partir das combinações achatadas que o backend devolve. */
export function montarArvore(grupos: GrupoApi[], niveis: number): NoGrupo[] {
  const raiz: NoGrupo[] = []
  for (const g of grupos) {
    let nivelAtual = raiz
    for (let i = 0; i < g.chaves.length; i++) {
      const chaves = g.chaves.slice(0, i + 1)
      const id = chaves.join(SEP)
      let no = nivelAtual.find(n => idDoNo(n) === id)
      if (!no) {
        no = {
          chaves,
          rotulos: g.rotulos.slice(0, i + 1),
          filtros: g.filtros.slice(0, i + 1),
          contagem: 0, valor: 0, saldo: 0, vencido: 0,
          folha: i === niveis - 1,
          filhos: [],
        }
        nivelAtual.push(no)
      }
      no.contagem += g.contagem
      no.valor += Number(g.valor ?? 0)
      no.saldo += Number(g.saldo ?? 0)
      no.vencido += Number(g.vencido ?? 0)
      nivelAtual = no.filhos
    }
  }
  return raiz
}

/**
 * A árvore aberta vira a lista que a grade virtualiza: cabeçalho de grupo,
 * as linhas do grupo aberto e, quando ele tem mais do que veio, um aviso que
 * leva a abrir só aquele grupo (onde a rolagem infinita continua).
 */
export function achatar<T>(
  nos: NoGrupo[],
  abertos: ReadonlySet<string>,
  linhasDe: (no: NoGrupo) => { linhas: T[]; total: number; carregando: boolean } | undefined,
  nivel = 0,
): ItemGrade<T>[] {
  const saida: ItemGrade<T>[] = []
  for (const no of nos) {
    const aberto = abertos.has(idDoNo(no))
    saida.push({ tipo: 'grupo', no, nivel, aberto })
    if (!aberto) continue
    if (!no.folha) {
      saida.push(...achatar(no.filhos, abertos, linhasDe, nivel + 1))
      continue
    }
    const dados = linhasDe(no)
    if (!dados || dados.carregando) {
      saida.push({ tipo: 'aviso', texto: 'Carregando…', nivel: nivel + 1 })
      continue
    }
    for (const linha of dados.linhas) saida.push({ tipo: 'linha', linha, nivel: nivel + 1 })
    if (dados.total > dados.linhas.length) {
      saida.push({
        tipo: 'aviso', nivel: nivel + 1, no,
        texto: `Mostrando ${dados.linhas.length} de ${dados.total.toLocaleString('pt-BR')} — abrir só este grupo para rolar todas`,
      })
    }
  }
  return saida
}

/** Os filtros que pedem as linhas de um grupo: os da tela mais as chaves dele. */
export function filtrosDoGrupo(
  base: Record<string, string | number | undefined>, no: { chaves: string[]; filtros: string[] },
): Record<string, string | number | undefined> {
  const saida = { ...base }
  no.filtros.forEach((campo, i) => { saida[campo] = no.chaves[i] })
  return saida
}
