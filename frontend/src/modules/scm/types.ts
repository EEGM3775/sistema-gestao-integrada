// Tipos do domínio SCM (suprimentos). Espelham os serializers `fields="__all__"`
// de backend/moduloscm/serializers.py — Decimais chegam como string do DRF;
// datas como "YYYY-MM-DD"; FKs como o pk inteiro do alvo.
// Planta: docs/modulos/moduloscm.md · expansão: docs/expansão/modulos/moduloscm.md

export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export type TipoItem = 'material' | 'servico'
export type Visibilidade = 'privada' | 'rede'

// ─── Catálogo ────────────────────────────────────────────────────────────────

export interface Produto {
  produto_id: number
  codigo_interno: string
  descricao: string
  unidade: string
  categoria: string
  tipo_item: TipoItem
  gtin: string
  item_rede_id: string
  ativo: boolean
}

export type ProdutoPayload = Omit<Produto, 'produto_id'>

export type TipoCentroCusto =
  | 'obra' | 'empreendimento' | 'almoxarifado' | 'filial' | 'administrativo' | 'outro'

export interface CentroCusto {
  centro_custo_id: number
  nome: string
  codigo: string
  tipo: TipoCentroCusto
  empreendimento: number | null
  obra: number | null
  local_estoque_ref: string
  ativo: boolean
}

export type CentroCustoPayload = Omit<CentroCusto, 'centro_custo_id'>

export interface OfertaFornecedor {
  oferta_id: number
  produto: number
  fornecedor: number
  codigo_no_fornecedor: string
  preco_direto: string
  estoque_disponivel: string
  estoque_reservado: string
  prazo_entrega_dias: number | null
  compra_direta: boolean
  visibilidade: Visibilidade
  regiao_entrega: string
  condicoes: string
  vigencia_inicio: string | null
  vigencia_fim: string | null
  ativo: boolean
  // Rótulos denormalizados (read-only) da API.
  produto_descricao?: string
  produto_codigo?: string
  produto_unidade?: string
  fornecedor_nome?: string
  estoque_livre?: string
}

export interface OfertaPayload {
  produto: number
  fornecedor: number
  codigo_no_fornecedor?: string
  preco_direto: string
  estoque_disponivel?: string
  prazo_entrega_dias?: number | null
  compra_direta?: boolean
  visibilidade?: Visibilidade
  regiao_entrega?: string
  condicoes?: string
  vigencia_inicio?: string | null
  vigencia_fim?: string | null
  ativo?: boolean
}

export interface FaixaPrecoOferta {
  faixa_id: number
  oferta: number
  quantidade_min: string
  preco_unitario: string
}

export type FaixaPayload = Omit<FaixaPrecoOferta, 'faixa_id'>

// ─── Demanda & Cotação ───────────────────────────────────────────────────────

export type StatusDemanda = 'rascunho' | 'aberta' | 'em_cotacao' | 'atendida' | 'cancelada'
export type OrigemDemanda = 'manual' | 'estoque'

export interface Demanda {
  demanda_id: number
  ref_externa: string
  tipo: TipoItem
  centro_custo: number | null
  solicitante: string | null
  status: StatusDemanda
  visibilidade: Visibilidade
  origem: OrigemDemanda
  categoria: string
  regiao: string
  observacao: string
  criado_em: string
  centro_custo_nome?: string | null
  solicitante_nome?: string | null
  itens_count?: number
}

export interface DemandaPayload {
  tipo: TipoItem
  centro_custo?: number | null
  categoria?: string
  regiao?: string
  observacao?: string
  origem?: OrigemDemanda
}

export interface ItemDemanda {
  item_demanda_id: number
  demanda: number
  produto: number | null
  descricao_servico: string
  quantidade: string
  unidade: string
  produto_descricao?: string | null
  produto_codigo?: string | null
}

export interface ItemDemandaPayload {
  demanda: number
  produto?: number | null
  descricao_servico?: string
  quantidade: string
  unidade?: string
}

export type StatusCotacao = 'aberta' | 'encerrada' | 'adjudicada'

export interface Cotacao {
  cotacao_id: number
  demanda: number
  status: StatusCotacao
  visibilidade: Visibilidade
  data_limite: string | null
  observacao: string
  criado_em: string
  propostas_count?: number
}

export interface CotacaoPayload {
  demanda: number
  visibilidade?: Visibilidade
  data_limite?: string | null
  observacao?: string
}

export type StatusProposta = 'recebida' | 'vencedora' | 'recusada'

export interface Proposta {
  proposta_id: number
  cotacao: number
  fornecedor: number | null
  origem_tenant: string | null
  fornecedor_nome: string
  valor_total: string | null
  prazo_entrega_dias: number | null
  status: StatusProposta
  criado_em: string
  fornecedor_label?: string
}

export interface PropostaPayload {
  cotacao: number
  fornecedor?: number | null
  fornecedor_nome?: string
  valor_total?: string | null
  prazo_entrega_dias?: number | null
}

export interface ItemProposta {
  item_proposta_id: number
  proposta: number
  item_demanda: number
  preco_unitario: string
  quantidade: string
}

export type ItemPropostaPayload = Omit<ItemProposta, 'item_proposta_id'>

// ─── Pedido, Recebimento & Avaliação ─────────────────────────────────────────

export type OrigemPedido = 'compra_direta' | 'cotacao' | 'manual'
export type StatusPedido =
  | 'rascunho' | 'aprovado' | 'enviado' | 'recebido_parcial' | 'recebido_total' | 'cancelado'

export interface PedidoCompra {
  pedido_id: number
  ref_externa: string
  origem: OrigemPedido
  demanda: number | null
  proposta_vencedora: number | null
  oferta_origem: number | null
  fornecedor: number
  centro_custo: number | null
  status: StatusPedido
  valor_total: string | null
  data_pedido: string
  data_entrega_prevista: string | null
  conta_pagar_ref: number | null
  origem_tenant: string | null
  observacao: string
  criado_em: string
  fornecedor_nome?: string
  centro_custo_nome?: string | null
  itens_count?: number
  recebimentos_count?: number
}

export interface PedidoPayload {
  fornecedor: number
  centro_custo?: number | null
  data_pedido?: string
  data_entrega_prevista?: string | null
  observacao?: string
  status?: StatusPedido
}

export interface ItemPedido {
  item_pedido_id: number
  pedido: number
  produto: number | null
  descricao: string
  quantidade: string
  preco_unitario: string
  produto_descricao?: string | null
  produto_codigo?: string | null
}

export interface ItemPedidoPayload {
  pedido: number
  produto?: number | null
  descricao?: string
  quantidade: string
  preco_unitario: string
}

export type TipoRecebimento = 'parcial' | 'total'

export interface Recebimento {
  recebimento_id: number
  pedido: number
  tipo: TipoRecebimento
  data: string
  local_entrega: string
  nota_fiscal_ref: string
  observacao: string
  criado_em: string
}

export interface RecebimentoPayload {
  pedido: number
  tipo: TipoRecebimento
  data?: string
  local_entrega?: string
  nota_fiscal_ref?: string
  observacao?: string
}

export interface AvaliacaoFornecedor {
  avaliacao_id: number
  fornecedor: number
  pedido: number | null
  nota_qualidade: number
  nota_pontualidade: number
  nota_atendimento: number
  comentario: string
  data: string
  fornecedor_nome?: string
}

export interface AvaliacaoPayload {
  fornecedor: number
  pedido?: number | null
  nota_qualidade: number
  nota_pontualidade: number
  nota_atendimento: number
  comentario?: string
}

// ─── Entidades externas (selects) ────────────────────────────────────────────

export interface FornecedorLite {
  fornecedor_id: number
  razao_social: string
  cnpj?: string
}

export interface ObraLite {
  obra_id: number
  nome_obra: string
}

export interface EmpreendimentoLite {
  empreendimento_id: number
  empreendimento: string
}

// Opção genérica de um select de entidade (value = pk, label = rótulo legível).
export interface EntityOption {
  value: number
  label: string
  hint?: string
}
