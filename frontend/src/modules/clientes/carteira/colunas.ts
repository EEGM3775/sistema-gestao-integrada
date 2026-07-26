import type { LinhaCarteira, Visao } from './types'

/**
 * As colunas da carteira.
 *
 * **Toda coluna ordena.** `ordenar` é a chave que o backend aceita
 * (`clientes/carteira.py::ORDENACOES`) e existe em todas — o menu "Ordenar por"
 * do cabeçalho não tem item morto.
 *
 * Duas ordenações são gateadas, porque ordenar por um dado é lê-lo:
 * `financeira` exige `erp.cobranca.view` (a coluna nem chega do backend sem ela)
 * e `documental` exige `cadastro.cliente_doc.view` — a coluna aparece com o
 * CPF mascarado, mas a **ordem alfabética dos documentos** reconstruiria o que a
 * máscara esconde, então o item do menu vem travado com o motivo.
 *
 * `tipo` só decide o texto do menu ("A → Z" vs. "Menor → maior").
 */
export interface ColunaDef {
  chave: string
  titulo: string
  largura: number
  alinhamento?: 'left' | 'right' | 'center'
  /** Dado de instrumento → mono tabular (identidade §6). */
  mono?: boolean
  tipo?: 'texto' | 'numero' | 'data' | 'endereco'
  ordenar: string
  financeira?: boolean
  documental?: boolean
  valor: (l: LinhaCarteira) => string
}

const dinheiro = (v?: string | null) =>
  v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const data = (v?: string | null) =>
  v ? v.slice(0, 10).split('-').reverse().join('/') : '—'

/** A coluna que dá nome à linha: fica **sempre em primeiro**, congelada, e é a
 *  que abre a ficha. Cliente na visão de pessoas, unidade na de aquisições —
 *  é o que a visão promete e o que a ordem padrão acompanha. */
export const COLUNA_ANCORA: Record<Visao, string> = {
  clientes: 'nome',
  unidades: 'unidade',
}

const CLIENTE: ColunaDef = {
  chave: 'nome', titulo: 'Cliente', largura: 260, ordenar: 'nome', tipo: 'texto',
  valor: l => l.nome,
}

const IDENTIFICACAO: ColunaDef[] = [
  {
    chave: 'documento', titulo: 'CPF / CNPJ', largura: 150, mono: true,
    ordenar: 'documento', documental: true, tipo: 'texto', valor: l => l.documento || '—',
  },
  { chave: 'email', titulo: 'E-mail', largura: 220, ordenar: 'email', tipo: 'texto', valor: l => l.email || '—' },
  { chave: 'telefone', titulo: 'Telefone', largura: 140, mono: true, ordenar: 'telefone', tipo: 'texto', valor: l => l.telefone || '—' },
]

const FINANCEIRAS: ColunaDef[] = [
  {
    chave: 'valorAberto', titulo: 'Em aberto', largura: 130, alinhamento: 'right', mono: true,
    ordenar: 'valor_aberto', financeira: true, tipo: 'numero', valor: l => dinheiro(l.valorAberto),
  },
  {
    chave: 'valorAtraso', titulo: 'Em atraso', largura: 130, alinhamento: 'right', mono: true,
    ordenar: 'valor_atraso', financeira: true, tipo: 'numero', valor: l => dinheiro(l.valorAtraso),
  },
  {
    chave: 'parcelasAtraso', titulo: 'Parcelas atr.', largura: 110, alinhamento: 'right', mono: true,
    ordenar: 'parcelas_atraso', financeira: true, tipo: 'numero', valor: l => String(l.parcelasAtraso ?? '—'),
  },
  {
    chave: 'diasAtraso', titulo: 'Dias atr.', largura: 95, alinhamento: 'right', mono: true,
    ordenar: 'atraso', financeira: true, tipo: 'numero', valor: l => (l.diasAtraso ? String(l.diasAtraso) : '—'),
  },
  {
    chave: 'valorVenda', titulo: 'Valor de venda', largura: 145, alinhamento: 'right', mono: true,
    ordenar: 'valor_venda', financeira: true, tipo: 'numero', valor: l => dinheiro(l.valorVenda),
  },
]

export const COLUNAS: Record<Visao, ColunaDef[]> = {
  // Pessoas: o cliente abre a linha e a ordem padrão é alfabética.
  clientes: [
    CLIENTE,
    ...IDENTIFICACAO,
    { chave: 'cidade', titulo: 'Cidade da aquisição', largura: 170, ordenar: 'cidade', tipo: 'texto', valor: l => l.cidade || '—' },
    {
      chave: 'unidade', titulo: 'Unidade', largura: 190, mono: true, ordenar: 'unidade', tipo: 'endereco',
      valor: l => (l.unidade || '—') + (l.unidadesTotal > 1 ? `  +${l.unidadesTotal - 1}` : ''),
    },
    { chave: 'empreendimento', titulo: 'Empreendimento', largura: 200, ordenar: 'empreendimento', tipo: 'texto', valor: l => l.empreendimento || '—' },
    { chave: 'estado', titulo: 'UF', largura: 60, alinhamento: 'center', ordenar: 'estado', tipo: 'texto', valor: l => l.estado || '—' },
    { chave: 'unidadesTotal', titulo: 'Unidades', largura: 95, alinhamento: 'right', mono: true, ordenar: 'unidades_total', tipo: 'numero', valor: l => String(l.unidadesTotal) },
    { chave: 'cidadeCliente', titulo: 'Cidade do cliente', largura: 165, ordenar: 'cidade_cliente', tipo: 'texto', valor: l => l.cidadeCliente || '—' },
    { chave: 'estadoCliente', titulo: 'UF do cliente', largura: 100, alinhamento: 'center', ordenar: 'estado_cliente', tipo: 'texto', valor: l => l.estadoCliente || '—' },
    ...FINANCEIRAS,
  ],
  // Aquisições: a unidade abre a linha e a ordem padrão é a do endereço
  // (quadra › lote › bloco/torre › andar › apto), numérica, não alfabética.
  unidades: [
    {
      chave: 'unidade', titulo: 'Unidade', largura: 200, mono: true, ordenar: 'unidade',
      tipo: 'endereco', valor: l => l.unidade || '—',
    },
    CLIENTE,
    { chave: 'empreendimento', titulo: 'Empreendimento', largura: 200, ordenar: 'empreendimento', tipo: 'texto', valor: l => l.empreendimento || '—' },
    { chave: 'quadra', titulo: 'Quadra', largura: 85, alinhamento: 'right', mono: true, ordenar: 'quadra', tipo: 'endereco', valor: l => l.quadra || '—' },
    { chave: 'lote', titulo: 'Lote', largura: 75, alinhamento: 'right', mono: true, ordenar: 'lote', tipo: 'endereco', valor: l => l.lote || '—' },
    { chave: 'blocoTorre', titulo: 'Bloco / Torre', largura: 120, mono: true, ordenar: 'bloco_torre', tipo: 'endereco', valor: l => l.blocoTorre || '—' },
    { chave: 'andar', titulo: 'Andar', largura: 80, alinhamento: 'right', mono: true, ordenar: 'andar', tipo: 'endereco', valor: l => l.andar || '—' },
    { chave: 'apto', titulo: 'Apto / Un.', largura: 100, alinhamento: 'right', mono: true, ordenar: 'apto', tipo: 'endereco', valor: l => l.apto || '—' },
    ...IDENTIFICACAO,
    { chave: 'cidade', titulo: 'Cidade da aquisição', largura: 170, ordenar: 'cidade', tipo: 'texto', valor: l => l.cidade || '—' },
    { chave: 'estado', titulo: 'UF', largura: 60, alinhamento: 'center', ordenar: 'estado', tipo: 'texto', valor: l => l.estado || '—' },
    { chave: 'dataCompra', titulo: 'Compra', largura: 110, mono: true, ordenar: 'compra', tipo: 'data', valor: l => data(l.dataCompra) },
    { chave: 'condicaoPagamento', titulo: 'Condição', largura: 175, ordenar: 'condicao_pagamento', tipo: 'texto', valor: l => l.condicaoPagamento || '—' },
    ...FINANCEIRAS,
  ],
}

/** O que aparece antes de o usuário mexer em nada — a âncora sempre à frente. */
export const COLUNAS_PADRAO: Record<Visao, string[]> = {
  clientes: ['nome', 'documento', 'email', 'telefone', 'cidade', 'unidade'],
  unidades: ['unidade', 'nome', 'empreendimento', 'quadra', 'lote', 'cidade'],
}

/** A ordem com que cada visão nasce — e para a qual o backend cai sozinho se a
 *  chave pedida não valer naquela visão (trocar de visão não herda a ordem da
 *  outra: "unidade" não ordena pessoas do mesmo jeito que ordena lotes). */
export const ORDEM_PADRAO: Record<Visao, string> = {
  clientes: 'nome',
  unidades: 'unidade',
}

export function colunasDisponiveis(visao: Visao, podeFinanceiro: boolean): ColunaDef[] {
  return COLUNAS[visao].filter(c => podeFinanceiro || !c.financeira)
}

/** As escolhidas, sempre com a âncora da visão em primeiro lugar. */
export function colunasVisiveis(
  visao: Visao, escolhidas: string[], podeFinanceiro: boolean,
): ColunaDef[] {
  const disponiveis = colunasDisponiveis(visao, podeFinanceiro)
  const ancora = COLUNA_ANCORA[visao]
  const chaves = [ancora, ...escolhidas.filter(c => c !== ancora)]
  const saida = chaves
    .map(chave => disponiveis.find(c => c.chave === chave))
    .filter((c): c is ColunaDef => Boolean(c))
  return saida.length ? saida : disponiveis.slice(0, 4)
}
