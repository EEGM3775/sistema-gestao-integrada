// Tipos do domínio SIL — espelham os serializers (`fields="__all__"`) de
// backend/modulosil/serializers.py. Decimais chegam como string; datas "YYYY-MM-DD".

export interface Paginated<T> { count: number; next: string | null; previous: string | null; results: T[] }

// Item do catálogo-mestre (backend/catalogo) — o "o que" se estoca.
export interface Item {
  item_id: number; codigo_interno: string; descricao: string; unidade: string
  categoria: string; tipo: string; compravel: boolean; estocavel: boolean
  vendavel: boolean; consumivel: boolean; rastreavel: boolean; gtin: string; ativo: boolean
}

export type TipoLocal = 'central' | 'canteiro' | 'fornecedor' | 'outro'
export interface LocalEstoque {
  local_id: number; nome: string; tipo: TipoLocal
  obra: number | null; empreendimento: number | null; fornecedor: number | null
  endereco: string; ativo: boolean; obra_nome?: string | null
}

export interface SaldoEstoque {
  saldo_id: number; item: number; local: number
  quantidade: string; custo_medio: string; reservado: string; ponto_reposicao: string
  item_descricao?: string; item_codigo?: string; item_unidade?: string; local_nome?: string
  disponivel?: string; valor_total?: string; abaixo_minimo?: boolean
}

export type TipoMov = 'entrada' | 'saida' | 'ajuste' | 'transf_saida' | 'transf_entrada' | 'devolucao'
export interface MovimentacaoEstoque {
  mov_id: number; item: number; local: number; tipo: TipoMov
  quantidade: string; custo_unitario: string; lote: number | null; obra: number | null
  recebimento_scm_ref: number | null; requisicao: number | null; transferencia: number | null
  devolucao: number | null; inventario: number | null; observacao: string; criado_em: string
  item_descricao?: string; item_codigo?: string; local_nome?: string; tipo_display?: string; usuario_nome?: string | null
}

export type StatusRequisicao = 'rascunho' | 'pendente' | 'aprovada' | 'atendida' | 'parcial' | 'cancelada'
export interface Requisicao {
  requisicao_id: number; local: number; obra: number | null; solicitante: number | null
  aprovador: number | null; status: StatusRequisicao; observacao: string; criado_em: string
  local_nome?: string; obra_nome?: string | null; solicitante_nome?: string | null; itens_count?: number
}
export interface ItemRequisicao {
  item_requisicao_id: number; requisicao: number; item: number; quantidade: string; quantidade_atendida: string
  item_descricao?: string; item_unidade?: string
}

export type StatusTransferencia = 'rascunho' | 'executada' | 'cancelada'
export interface Transferencia {
  transferencia_id: number; origem: number; destino: number; status: StatusTransferencia
  observacao: string; criado_em: string; origem_nome?: string; destino_nome?: string; itens_count?: number
}
export interface ItemTransferencia {
  item_transferencia_id: number; transferencia: number; item: number; quantidade: string; lote: number | null
  item_descricao?: string
}

export type TipoDevolucao = 'fornecedor' | 'estoque'
export type StatusDevolucao = 'rascunho' | 'executada' | 'cancelada'
export interface Devolucao {
  devolucao_id: number; tipo: TipoDevolucao; local: number; fornecedor: number | null
  pedido_scm_ref: number | null; status: StatusDevolucao; observacao: string; criado_em: string
  local_nome?: string; fornecedor_nome?: string | null; itens_count?: number
}
export interface ItemDevolucao {
  item_devolucao_id: number; devolucao: number; item: number; quantidade: string; lote: number | null
  item_descricao?: string
}

export type TipoInventario = 'geral' | 'ciclica'
export type StatusInventario = 'aberto' | 'fechado'
export interface Inventario {
  inventario_id: number; local: number; tipo: TipoInventario; status: StatusInventario
  criado_em: string; fechado_em: string | null; local_nome?: string; itens_count?: number
}
export interface ItemInventario {
  item_inventario_id: number; inventario: number; item: number; lote: number | null
  quantidade_sistema: string; quantidade_contada: string; item_descricao?: string; diferenca?: string
}

export interface Lote {
  lote_id: number; item: number; numero_lote: string; validade: string | null
  fornecedor: number | null; criado_em: string; item_descricao?: string
}

export interface SilAtividade { tipo: TipoMov; titulo: string; meta: string; quando: string }
export interface SilDashboard {
  valorEstoque: string; locais: number; itensEmEstoque: number; abaixoMinimo: number
  requisicoesPendentes: number; requisicoesAprovadas: number; inventariosAbertos: number
  lotesVencendo: number; epiVencendo: number; ferramentasAtrasadas: number
  ferramentasManutencao: number; recebimentosAConferir: number; atividade: SilAtividade[]
}

// EPI (NR-6) — a prova trabalhista de entrega.
export type StatusEPI = 'entregue' | 'devolvido' | 'substituido' | 'danificado'
export interface EntregaEPI {
  entrega_epi_id: number; item: number; colaborador: number | null; colaborador_nome: string
  local: number | null; obra: number | null; quantidade: string; ca_numero: string
  ca_validade: string | null; data_entrega: string; data_prevista_troca: string | null
  data_devolucao: string | null; status: StatusEPI; baixou_estoque: boolean; assinado: boolean
  observacao: string; item_descricao?: string; item_codigo?: string; colaborador_label?: string | null
  obra_nome?: string | null; local_nome?: string | null; vencido?: boolean
}

// Ferramentaria (comodato interno).
export type EstadoFerramenta = 'disponivel' | 'emprestada' | 'manutencao' | 'baixada'
export interface Ferramenta {
  ferramenta_id: number; item: number | null; nome: string; patrimonio: string
  local: number | null; estado: EstadoFerramenta; calibravel: boolean
  proxima_calibracao: string | null; proxima_manutencao: string | null; valor: string | null
  observacao: string; item_descricao?: string | null; local_nome?: string | null
  estado_display?: string; manutencao_vencendo?: boolean
  emprestimo_ativo?: { emprestimo_id: number; colaborador: string | null; atrasada: boolean } | null
}
export type StatusEmprestimo = 'emprestada' | 'devolvida'
export interface EmprestimoFerramenta {
  emprestimo_id: number; ferramenta: number; colaborador: number | null; colaborador_nome: string
  obra: number | null; data_emprestimo: string; data_prevista_devolucao: string | null
  data_devolucao: string | null; status: StatusEmprestimo; observacao: string
  ferramenta_nome?: string; ferramenta_patrimonio?: string | null; colaborador_label?: string | null
  obra_nome?: string | null; atrasada?: boolean
}

// Analíticos de gestão.
export interface CurvaABCItem {
  item: number; descricao: string; codigo: string; unidade: string
  quantidade: string; valor: string; pct: string; pct_acumulado: string; classe: 'A' | 'B' | 'C'
}
export interface CurvaABC {
  total: string
  resumo: Record<'A' | 'B' | 'C', { itens: number; valor: string }>
  itens: CurvaABCItem[]
}
export interface AplicadoLinha {
  obra: number | null; obra_nome: string | null; etapa: number | null; etapa_nome: string
  aplicado: string
  // Vêm do módulo Orçamento (orçamento aprovado vigente da obra). Nulos quando
  // a obra não tem régua aprovada ou o tenant não assina `orcamento`.
  orcado: string | null; saldo: string | null; estourado: boolean
}

// Opções leves para selects (cadastros-base + RH).
export interface ObraOpt { obra_id: number; nome_obra: string }
export interface FornecedorOpt { fornecedor_id: number; razao_social: string }
export interface FuncionarioOpt { funcionario_id: number; nome_completo: string }
export interface EtapaOpt { etapa_id: number; nome_etapa: string; obra: number }
