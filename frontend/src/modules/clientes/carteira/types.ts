/**
 * Contratos da carteira de clientes (backend: `clientes/carteira.py`).
 *
 * Os campos financeiros são **opcionais de propósito**: sem `erp.cobranca.view`
 * o backend não os envia (LGPD — gate de duas pontas). `podeFinanceiro` na
 * resposta diz qual dos dois mundos a tela está vendo, para ela nunca exibir
 * "R$ 0,00" no lugar de "você não tem acesso a este número".
 */

export type Visao = 'clientes' | 'unidades'

export type FaixaChave = 'em_dia' | 'd1_30' | 'd31_60' | 'd61_90' | 'd90_mais'

export interface LinhaCarteira {
  tipo: 'cliente' | 'unidade'
  id: number
  clienteId: number
  nome: string
  documento: string
  email: string
  telefone: string
  empreendimento: string
  cidade: string
  estado: string
  /** O rótulo montado: "QD 12 · LT 05" ou "Torre A · 3º · 302". */
  unidade: string
  /** Os níveis do endereço, soltos — são as colunas e a ordem natural da visão
   *  de unidades. Na visão de clientes descrevem a **última** aquisição. */
  quadra: string
  lote: string
  blocoTorre?: string
  andar?: string
  apto?: string
  cidadeCliente?: string
  estadoCliente?: string
  dataCompra?: string | null
  condicaoPagamento?: string
  unidadesTotal: number
  valorVenda: string | null
  /** Situação — sempre presente, é a pílula que todos veem. */
  adimplente: boolean
  faixa: FaixaChave
  /** Números — só com `erp.cobranca.view`. */
  parcelasAtraso?: number
  valorAtraso?: string
  valorAberto?: string
  diasAtraso?: number
}

export interface PaginaCarteira {
  visao: Visao
  count: number
  page: number
  pageSize: number
  temMais: boolean
  podeFinanceiro: boolean
  /** `cadastro.cliente_doc.view` — libera **ordenar** por CPF/CNPJ, não só lê-lo. */
  podeDocumento: boolean
  results: LinhaCarteira[]
}

export interface GrupoCarteira {
  niveis: string[]
  /** O parâmetro de filtro de cada nível — é como a tela "entra" no grupo. */
  filtros: string[]
  chaves: string[]
  rotulos: string[]
  contagem: number
  valorAberto?: string
  valorAtraso?: string
  valorVenda?: string
}

export interface RespostaGrupos {
  visao: Visao
  niveis: string[]
  podeFinanceiro: boolean
  podeDocumento: boolean
  /**
   * Quantas linhas a carteira tem neste recorte — **não** a soma dos grupos.
   *
   * As duas divergem de propósito ao agrupar pessoas por uma dimensão de
   * muitos: quem comprou em dois empreendimentos é um cliente e aparece em dois
   * cabeçalhos. Somar os cabeçalhos dava 5.312 numa carteira de 5.000, e o
   * contador da barra mudava só porque alguém agrupou.
   */
  count: number
  /** A soma dos cabeçalhos — só para explicar a diferença, nunca para exibir
   *  como total. */
  somaDosGrupos: number
  grupos: GrupoCarteira[]
}

export interface OpcoesCarteira {
  empreendimentos: { id: number; nome: string }[]
  quadras: string[]
  cidades: string[]
  estados: string[]
  anos: number[]
  faixas: { chave: FaixaChave; rotulo: string }[]
  dimensoes: Record<Visao, { chave: string; rotulo: string }[]>
  podeFinanceiro: boolean
}

/** Filtros ativos da tela — viram query params sem tradução. */
export interface FiltrosCarteira {
  busca?: string
  empreendimento?: string
  quadra?: string
  cidade?: string
  estado?: string
  faixa?: string
  ano_compra?: string
  condicao_pagamento?: string
  bloco_torre?: string
  profissao?: string
  estado_civil?: string
  cliente?: string
}

/** Extrato do cliente (aba Financeiro da ficha). */
export interface ParcelaCliente {
  id: number
  descricao: string
  vencimento: string
  valor: string
  pago: string
  saldo: string
  status: string
  diasAtraso: number
  recebimento: string | null
  unidade: string | null
  empreendimento: string | null
  boleto: {
    id: number
    status: string
    linhaDigitavel: string | null
    urlPdf: string | null
    vencimento: string
  } | null
}

export interface FinanceiroCliente {
  resumo: {
    valorAberto: string
    valorAtraso: string
    valorPago: string
    parcelasAtraso: number
    parcelasTotal: number
    adimplente: boolean
  }
  parcelas: ParcelaCliente[]
}

/** Andamento da obra (aba Obra da ficha). */
export interface ObraDoCliente {
  id: number
  nome: string
  status: string
  empreendimento: string | null
  empreendimentoId: number | null
  inicioPrevisto: string | null
  fimPrevisto: string | null
  fimReal: string | null
  /** `null` = obra sem etapa cadastrada. Não é zero — é ausência de fonte. */
  percentual: number | null
  etapasTotal: number
  etapas: {
    id: number
    nome: string
    status: string
    percentual: number
    fimPrevisto: string | null
  }[]
}

export interface ObraResposta {
  unidades: { id: number; unidade: string; empreendimento: string; empreendimentoId: number }[]
  obras: ObraDoCliente[]
}
