import { createContext, useContext } from 'react'
import type { Obra } from '@/types'
import type { Selecao } from './types'

export interface ContextoPdca {
  obraId: number
  obra: Obra | undefined
  /** O objeto selecionado atravessa os postos: a mesma atividade escolhida na
   *  grade continua escolhida no Gantt e na linha de balanço. É o que faz de
   *  seis instrumentos um sistema, e não seis telas. */
  selecao: Selecao
  selecionar: (s: Selecao) => void
  paletaAberta: boolean
  abrirPaleta: () => void
  fecharPaleta: () => void
}

export const Contexto = createContext<ContextoPdca | null>(null)

export function usePdca(): ContextoPdca {
  const ctx = useContext(Contexto)
  if (!ctx) throw new Error('usePdca fora do ProvedorPdca')
  return ctx
}
