import type { ReactNode } from 'react'

/** Uma coluna da grade. `ordenar` é a chave que o backend aceita (`listao.py`). */
export interface ColunaGrade<T> {
  chave: string
  titulo: string
  largura: number
  ordenar?: string
  tipo?: 'texto' | 'numero' | 'data' | 'endereco'
  alinhamento?: 'left' | 'right' | 'center'
  mono?: boolean
  render: (linha: T) => ReactNode
  /** O texto que o Ctrl+C leva para a planilha. */
  texto: (linha: T) => string
}

export interface Somas {
  contagem: number
  valor: string
  saldo?: string
  vencido?: string
}

/** Uma combinação de níveis, como o backend devolve (achatada). */
export interface GrupoApi extends Somas {
  niveis: string[]
  filtros: string[]
  chaves: string[]
  rotulos: string[]
}

export interface Dimensao {
  chave: string
  rotulo: string
}

export interface RespostaGrupos {
  totais: Somas
  grupos: GrupoApi[]
  dimensoes: Dimensao[]
  teto_niveis: number
}

export interface PaginaGrade<T> {
  count: number
  next: string | null
  results: T[]
}

/** Um nó da árvore de grupos: os níveis de cima somam os filhos. */
export interface NoGrupo {
  chaves: string[]
  rotulos: string[]
  filtros: string[]
  contagem: number
  valor: number
  saldo: number
  vencido: number
  folha: boolean
  filhos: NoGrupo[]
}

export type ItemGrade<T> =
  | { tipo: 'grupo'; no: NoGrupo; nivel: number; aberto: boolean }
  | { tipo: 'linha'; linha: T; nivel: number }
  | { tipo: 'aviso'; texto: string; nivel: number; no?: NoGrupo }

export type Filtros = Record<string, string | number | undefined>
