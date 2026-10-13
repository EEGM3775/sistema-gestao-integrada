import type { ReactNode } from 'react'

export type ChavePagina =
  | 'orcar' | 'encargos' | 'analisar' | 'cronograma' | 'bases' | 'incorporacao'

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
    chave: 'encargos',
    rota: '/app/orcamento/encargos',
    titulo: 'Encargos & BDI',
    verbo: 'Parametrizar o preço',
    resumo: 'Quadro de encargos por grupo A/B/C/D e composição do BDI. O reajuste é cláusula do contrato, no PDCA.',
    permissao: 'orcamento.orcamento.view',
    icone: 'percentual',
  },
  {
    chave: 'analisar',
    rota: '/app/orcamento/analisar',
    titulo: 'Analisar',
    verbo: 'Ler o orçado',
    resumo: 'Curva ABC de serviços e de insumos, relação de insumos para o Suprimentos e composição do custo.',
    permissao: 'orcamento.relatorio.view',
    icone: 'colunas',
  },
  {
    chave: 'cronograma',
    rota: '/app/orcamento/cronograma',
    titulo: 'Cronograma',
    verbo: 'Distribuir no tempo',
    resumo: 'Físico-financeiro por etapa: início, término e curva, Hh e equipe — a base do plano do PDCA.',
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
