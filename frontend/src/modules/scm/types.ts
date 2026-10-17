// Tipos do domínio SCM — espelham os serializers (`fields="__all__"`) de
// backend/moduloscm/serializers.py. Decimais chegam como string; datas "YYYY-MM-DD".

export interface Paginated<T> { count: number; next: string | null; previous: string | null; results: T[] }

export type TipoItem = 'material' | 'servico'
export type Visibilidade = 'privada' | 'rede'

export interface Produto {
  produto_id: number; codigo_interno: string; descricao: string; unidade: string
  categoria: string; tipo_item: TipoItem; gtin: string; item_rede_id: string; ativo: boolean
}

export type TipoCentroCusto = 'obra' | 'empreendimento' | 'almoxarifado' | 'filial' | 'administrativo' | 'outro'
export interface CentroCusto {
  centro_custo_id: number; nome: string; codigo: string; tipo: TipoCentroCusto
  empreendimento: number | null; obra: number | null; local_estoque_ref: string; ativo: boolean
}

export interface OfertaFornecedor {
  oferta_id: number; produto: number; fornecedor: number; codigo_no_fornecedor: string
  preco_direto: string; estoque_disponivel: string; estoque_reservado: string
  prazo_entrega_dias: number | null; compra_direta: boolean; visibilidade: Visibilidade
  regiao_entrega: string; condicoes: string; vigencia_inicio: string | null; vigencia_fim: string | null; ativo: boolean
  produto_descricao?: string; produto_codigo?: string; produto_unidade?: string
  fornecedor_nome?: string; estoque_livre?: string
}

export type StatusDemanda = 'rascunho' | 'aberta' | 'em_cotacao' | 'atendida' | 'cancelada'
export type OrigemDemanda = 'manual' | 'estoque'
export interface Demanda {
  demanda_id: number; ref_externa: string; tipo: TipoItem; centro_custo: number | null
  solicitante: number | null; status: StatusDemanda; visibilidade: Visibilidade; origem: OrigemDemanda
  categoria: string; regiao: string; observacao: string; criado_em: string
  centro_custo_nome?: string | null; solicitante_nome?: string | null; itens_count?: number
}
export interface ItemDemanda {
  item_demanda_id: number; demanda: number; produto: number | null; descricao_servico: string
  quantidade: string; unidade: string; produto_descricao?: string | null; produto_codigo?: string | null
  /** Quanto ainda falta comprar desta linha (pedidos já gerados abatem). */
  saldo?: string
}

export type StatusCotacao = 'aberta' | 'encerrada' | 'adjudicada'
export interface Cotacao {
  cotacao_id: number; demanda: number; status: StatusCotacao; visibilidade: Visibilidade
  data_limite: string | null; observacao: string; criado_em: string; propostas_count?: number
}

export type StatusProposta = 'recebida' | 'vencedora' | 'recusada'
export interface Proposta {
  proposta_id: number; cotacao: number; fornecedor: number | null; origem_tenant: string | null
  fornecedor_nome: string; valor_total: string | null; prazo_entrega_dias: number | null
  status: StatusProposta; criado_em: string; fornecedor_label?: string
  /** Quando o preço chegou (o comprador digita dias depois). */
  recebida_em: string; observacao: string
  fornecedor_avaliacao_media?: string | null; fornecedor_avaliacao_count?: number
}
export interface ItemProposta {
  item_proposta_id: number; proposta: number; item_demanda: number; preco_unitario: string; quantidade: string
}

export type OrigemPedido = 'compra_direta' | 'cotacao' | 'manual'
export type StatusPedido = 'rascunho' | 'aprovado' | 'enviado' | 'recebido_parcial' | 'recebido_total' | 'cancelado'
export interface PedidoCompra {
  pedido_id: number; ref_externa: string; origem: OrigemPedido; demanda: number | null
  proposta_vencedora: number | null; oferta_origem: number | null; fornecedor: number
  centro_custo: number | null; status: StatusPedido; valor_total: string | null
  data_pedido: string; data_entrega_prevista: string | null; conta_pagar_ref: number | null
  origem_tenant: string | null; observacao: string; criado_em: string
  enviado_em?: string | null; revisao?: number
  fornecedor_nome?: string; centro_custo_nome?: string | null; itens_count?: number; recebimentos_count?: number
  /** Medição × compra de serviço: os contratos do PDCA que medem este pedido. */
  medicao_pdca?: { contrato: number; numero: string; obra: number; medido_aprovado: string }[]
}
export interface ItemPedido {
  item_pedido_id: number; pedido: number; produto: number | null; descricao: string; unidade?: string
  quantidade: string; preco_unitario: string; produto_descricao?: string | null; produto_codigo?: string | null
  produto_unidade?: string | null
}

export type TipoRecebimento = 'parcial' | 'total'
export interface Recebimento {
  recebimento_id: number; pedido: number; tipo: TipoRecebimento; data: string
  local_entrega: string; nota_fiscal_ref: string; observacao: string; criado_em: string
}
export interface AvaliacaoFornecedor {
  avaliacao_id: number; fornecedor: number; pedido: number | null
  nota_qualidade: number; nota_pontualidade: number; nota_atendimento: number
  comentario: string; data: string; fornecedor_nome?: string
}

// ─── D284: o pedido inteiro (painel), a NF-e da compra, a cobrança, a ficha ───
export type Regime = 'livre' | 'saldo' | 'travado'
export type Pendencia = 'aguardando_nfe' | 'nfe_aguardando_documento' | 'nfe_divergente' | 'sem_cobranca' | 'cobranca_nao_confere'
export interface LinhaSaldo {
  item_pedido: number; produto: number | null; descricao: string; codigo: string; unidade: string; estocavel: boolean
  quantidade: string; recebido: string; encerrado: string; pendente: string; excedente: string
  preco_unitario: string; subtotal: string
}
export type SituacaoNota = 'aguardando_documento' | 'conferida' | 'divergente'
export interface NotaFiscalCompra {
  nota_id: number; pedido: number; recebimento: number | null; numero: string; serie: string
  chave_acesso: string; data_emissao: string | null; valor_total: string | null
  emitente_cnpj: string; emitente_nome: string; situacao: SituacaoNota; situacao_nome: string
  divergencias: string[]; duplicatas: { numero: string; vencimento: string; valor: string }[]
  conferida_em: string | null; criado_em: string
  /** A entrega autenticada (`/api/impexp/scm.nota_compra/arquivo/…`), ou `null` sem o documento. */
  url_xml: string | null; url_pdf: string | null
}
export interface ParcelaCobranca {
  numero: number; vencimento: string; valor: string; conta_pagar_ref: number | null
  titulo_status: string | null; titulo_valor_pago: string | null
}
export interface MeioCobranca {
  meio_id: number; tipo: string; tipo_nome: string; valor: string; parcelas: number
  primeiro_vencimento: string; intervalo_dias: number; descricao: string; parcelas_geradas: ParcelaCobranca[]
}
export interface CobrancaResumo {
  meios: MeioCobranca[]; soma: string; valor_pedido: string; confere: boolean
  tipos: { valor: string; rotulo: string }[]
}
export interface EventoPedido {
  evento_id: number; tipo: string; tipo_nome: string; texto: string; valor: string | null
  vai_ao_erp: boolean; autor_nome: string; criado_em: string
}
export interface RecebimentoPainel {
  recebimento_id: number; data: string; tipo: TipoRecebimento; encerrou_saldo: boolean
  local_entrega: string; observacao: string; nota_fiscal_ref: string; recebido_por: string
  itens: { item_pedido: number; descricao: string; quantidade: string }[]; notas: number[]
}
export interface TituloPedido {
  conta_pagar_id: number; descricao: string; valor: string; valor_pago: string
  status: string; data_vencimento: string; nfe_situacao: string
}
export interface PainelPedido {
  pedido: PedidoCompra; regime: Regime; linhas: LinhaSaldo[]; recebimentos: RecebimentoPainel[]
  notas: NotaFiscalCompra[]; cobranca: CobrancaResumo; titulos: TituloPedido[]; eventos: EventoPedido[]
  pendencias: Pendencia[]; fornecedor_contato: { email: string; telefone: string }
}
export interface FichaItem {
  item: number; codigo_interno: string; descricao: string; unidade: string; tipo: string; tipo_nome: string
  categoria: string; ncm: string; gtin: string; estocavel: boolean; ativo: boolean
  origem: {
    tipo: string; rotulo: string; detalhe: string; criado_em: string | null; fonte_referencia: string
    fonte_nome: string; codigo_referencia: string; publicacao_referencia: string
  }
  lojas: {
    fornecedor: number; fornecedor_nome: string; oferta: number | null; codigo_no_fornecedor: string
    preco_oferta: string | null; compra_direta: boolean; prazo_entrega_dias: number | null; ativo: boolean
    ultimo_preco_pago: string | null; ultima_compra: string | null
  }[]
  historico_precos: { pedido: number; data: string; fornecedor: number; fornecedor_nome: string; quantidade: string; unidade: string; preco_unitario: string }[]
  /** Pontos do gráfico "preço por fornecedor ao longo do tempo", em ordem cronológica. */
  grafico_precos: {
    pagos: { data: string; fornecedor: number; fornecedor_nome: string; pedido: number; quantidade: string; preco_unitario: string }[]
    /** `fornecedor` nulo = proposta da rede (só o rótulo). */
    cotados: { data: string; fornecedor: number | null; fornecedor_nome: string; cotacao: number; status: 'recebida' | 'vencedora' | 'recusada'; quantidade: string; preco_unitario: string }[]
  }
  preco_resumo: { ultimo: string | null; menor: string | null; maior: string | null; compras: number }
  orcamentos: { orcamento: number; descricao: string; versao: number; obra: string; linhas: number; quantidade: string | null }[]
  estoque: { local: number; local_nome: string; quantidade: string; reservado: string; custo_medio: string }[]
  estoque_total: string
  uso: { demandas: number; pedidos: number }
}
export interface ItemCadastrado { item_id: number; codigo_interno: string; descricao: string; unidade: string; criado: boolean; oferta: number | null }

export interface AtividadeItem {
  tipo: 'recebimento' | 'adjudicacao' | 'compra_direta' | 'avaliacao'
  titulo: string; meta: string; quando: string
}
export interface ScmDashboard {
  demandasAbertas: number; demandasEmCotacao: number; cotacoesAbertas: number
  pedidosAprovados: number; pedidosEnviados: number; pedidosRecebidosParcial: number
  produtosAtivos: number; ofertasDiretas: number; mesReferencia: string
  valorCompradoMes: string; valorCompradoMesAnterior: string; fornecedoresAvaliados: number
  economiaAdjudicadas: string; cotacoesAdjudicadas: number; cotacoesVencemHoje: number
  pedidosTransitoValor: string; pedidosTransitoCount: number; pedidosTransitoFornecedores: number
  prazoMedioEntregaDias: number | null; atividade: AtividadeItem[]
}
