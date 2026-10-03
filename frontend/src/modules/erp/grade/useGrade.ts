import { useCallback, useEffect, useMemo, useState } from 'react'
import { achatar, idDoNo, montarArvore } from './arvore'
import { useGradeInfinita, useGruposDaGrade, useLinhasDosGrupos } from './hooks'
import type { Filtros, ItemGrade, NoGrupo } from './tipos'

interface Preferencias { ordenar: string; niveis: string[] }

function lerPreferencias(chave: string, padrao: Preferencias): Preferencias {
  try {
    const bruto = window.localStorage.getItem(chave)
    if (!bruto) return padrao
    const lido = JSON.parse(bruto) as Partial<Preferencias>
    return {
      ordenar: typeof lido.ordenar === 'string' && lido.ordenar ? lido.ordenar : padrao.ordenar,
      niveis: Array.isArray(lido.niveis) ? lido.niveis.filter(n => typeof n === 'string') : padrao.niveis,
    }
  } catch {
    return padrao
  }
}

function gravarPreferencias(chave: string, p: Preferencias) {
  try { window.localStorage.setItem(chave, JSON.stringify(p)) } catch { /* navegador sem armazenamento: só não lembra */ }
}

/**
 * Tudo o que uma tela de títulos precisa da grade: a lista (plana ou agrupada),
 * os totais, a ordem e o agrupamento — os dois últimos lembrados por pessoa e
 * por tela, como a carteira de clientes faz.
 */
export function useGrade<T>({ recurso, filtros, ordenarPadrao }: {
  recurso: string
  filtros: Filtros
  ordenarPadrao: string
}) {
  const chavePref = `sgi_grade_erp_${recurso}_v1`
  const [pref, setPref] = useState<Preferencias>(() => lerPreferencias(chavePref, { ordenar: ordenarPadrao, niveis: [] }))
  const [abertos, setAbertos] = useState<ReadonlySet<string>>(new Set())

  useEffect(() => { gravarPreferencias(chavePref, pref) }, [chavePref, pref])

  const agrupada = pref.niveis.length > 0
  const lista = useGradeInfinita<T>(recurso, filtros, pref.ordenar, !agrupada)
  const grupos = useGruposDaGrade(recurso, filtros, pref.niveis)

  // Grupos que o filtro mudou deixam de existir: fecha tudo ao trocar o recorte.
  const assinatura = JSON.stringify([filtros, pref.niveis])
  useEffect(() => { setAbertos(new Set()) }, [assinatura])

  const arvore = useMemo(
    () => (agrupada ? montarArvore(grupos.grupos, pref.niveis.length) : []),
    [agrupada, grupos.grupos, pref.niveis.length],
  )

  const folhasAbertas = useMemo(() => {
    const saida: NoGrupo[] = []
    const visitar = (nos: NoGrupo[]) => {
      for (const no of nos) {
        if (!abertos.has(idDoNo(no))) continue
        if (no.folha) saida.push(no)
        else visitar(no.filhos)
      }
    }
    visitar(arvore)
    return saida
  }, [arvore, abertos])

  const linhasDosGrupos = useLinhasDosGrupos<T>(recurso, filtros, pref.ordenar, folhasAbertas)

  const itens: ItemGrade<T>[] = useMemo(() => {
    if (!agrupada) return lista.linhas.map(linha => ({ tipo: 'linha' as const, linha, nivel: 0 }))
    return achatar<T>(arvore, abertos, no => linhasDosGrupos.get(idDoNo(no)))
  }, [agrupada, lista.linhas, arvore, abertos, linhasDosGrupos])

  const alternarGrupo = useCallback((no: NoGrupo) => {
    setAbertos(atual => {
      const prox = new Set(atual)
      const id = idDoNo(no)
      if (prox.has(id)) prox.delete(id)
      else prox.add(id)
      return prox
    })
  }, [])

  return {
    itens,
    agrupada,
    ordenar: pref.ordenar,
    setOrdenar: (ordenar: string) => setPref(p => ({ ...p, ordenar })),
    niveis: pref.niveis,
    setNiveis: (niveis: string[]) => setPref(p => ({ ...p, niveis })),
    totais: grupos.totais,
    dimensoes: grupos.dimensoes,
    tetoNiveis: grupos.tetoNiveis,
    carregando: agrupada ? grupos.carregando : lista.carregando || lista.buscandoMais,
    atualizando: lista.atualizando,
    alternarGrupo,
    fimDaLista: () => { if (!agrupada) lista.proximaPagina() },
  }
}
