import type { ReactNode } from 'react'

export type ChavePagina = 'orcar' | 'controlar' | 'cronograma' | 'bases' | 'incorporacao'

export interface DefinicaoPagina {
  chave: ChavePagina
  rota: string
  titulo: string
  verbo: string
  resumo: string
  permissao: string
  icone: string
}

/** Catálogo único das páginas — o hub monta os cartões e a shell monta o menu
 *  a partir daqui, para não existirem duas listas que divergem. */
export const PAGINAS: DefinicaoPagina[] = [
  {
    chave: 'orcar',
    rota: '/app/orcamento/orcar',
    titulo: 'Orçar',
    verbo: 'Montar a planilha',
    resumo: 'Árvore EAP, composições analíticas, encargos e BDI. A grade onde o orçamento nasce.',
    permissao: 'orcamento.orcamento.view',
    icone: 'planilha',
  },
  {
    chave: 'controlar',
    rota: '/app/orcamento/controlar',
    titulo: 'Controlar',
    verbo: 'Acompanhar o custo',
    resumo: 'Orçado × comprometido × aplicado × realizado por obra, curva ABC e desvios.',
    permissao: 'orcamento.relatorio.view',
    icone: 'colunas',
  },
  {
    chave: 'cronograma',
    rota: '/app/orcamento/cronograma',
    titulo: 'Cronograma',
    verbo: 'Distribuir no tempo',
    resumo: 'Físico-financeiro por etapa e competência, com curva S de previsto × realizado.',
    permissao: 'orcamento.relatorio.view',
    icone: 'calendario',
  },
  {
    chave: 'bases',
    rota: '/app/orcamento/bases',
    titulo: 'Bases & bancos',
    verbo: 'Gerir preços de referência',
    resumo: 'Bases-mãe travadas (SINAPI, ORSE), bancos próprios da empresa e importações.',
    permissao: 'orcamento.base.view',
    icone: 'banco',
  },
  {
    chave: 'incorporacao',
    rota: '/app/orcamento/incorporacao',
    titulo: 'Incorporação',
    verbo: 'Estimar e registrar',
    resumo: 'Paramétrico por CUB na viabilidade e os quadros da NBR 12721 para o cartório.',
    permissao: 'orcamento.relatorio.view',
    icone: 'predio',
  },
]

export const PAGINA_POR_CHAVE = Object.fromEntries(PAGINAS.map(p => [p.chave, p])) as Record<ChavePagina, DefinicaoPagina>

export type ComIcone = { icone: ReactNode }
