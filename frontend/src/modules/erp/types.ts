// Tipos do ERP financeiro (D.1.0/D.1.1 — fundação UI + Contas a Pagar/Receber).
//
// Valores monetários chegam da API como string decimal (`DecimalField` do DRF,
// ex.: "1234.56") — convertidos para centavos inteiros na borda (ver
// `api/endpoints/*` e `utils/money.ts`). Os tipos aqui refletem o *payload da
// API* (strings); os hooks expõem versões já normalizadas para a UI.

/** Espelha `StatusConta` (backend) — ABERTO/PARCIAL são "em aberto" para fins de aging. */
export type StatusConta = 'ABERTO' | 'PARCIAL' | 'QUITADO' | 'CANCELADO'

/** Espelha `LoteRemessa.StatusLote` (backend). */
export type StatusLote = 'GERADO' | 'ENVIADO' | 'PROCESSADO' | 'CANCELADO'

/** Item de rateio por centro de custo — mesmo formato em ContaPagar e ContaReceber. */
export interface Rateio {
  rateio_id: number
  centro_custo: number
  centro_custo_nome: string
  valor: string
}

/** Payload de escrita de um rateio — sem os campos somente leitura do `Rateio`. */
export interface RateioPayload {
  centro_custo: number
  valor: string
}

/** Espelha `Boleto.StatusBoleto` (backend). */
export type StatusBoleto = 'AGUARDANDO' | 'EMITIDO' | 'PAGO' | 'VENCIDO' | 'CANCELADO' | 'ERRO'

/** Boleto vinculado a uma conta — somente leitura aqui (gerado pelo gateway de cobrança, D.1.2). */
export interface Boleto {
  boleto_id: number
  status: StatusBoleto
  valor: string
  data_vencimento: string
  data_pagamento: string | null
  gateway_id: string | null
  url_pdf: string | null
  linha_digitavel: string | null
  conta_receber: number | null
  conta_pagar: number | null
}

/** Eixos de filtro do `BoletoFilter` (backend) — sem `search` (o model não tem campo de texto livre). */
export interface BoletoFiltros {
  status?: StatusBoleto
  conta_receber?: number
  conta_pagar?: number
  data_de?: string
  data_ate?: string
  page?: number
  page_size?: number
  ordering?: string
}

/**
 * Evento do webhook Asaas vinculado a um `Boleto` — alimenta a timeline da
 * `BoletoDetailPage` (D.1.2). Somente leitura: gerado pelo `WebhookAsaasView`,
 * nunca pela UI. `resultado` registra o desfecho do processamento (baixa
 * aplicada, idempotência, encaminhado para `RevisaoBaixa`...).
 */
export interface EventoWebhookAsaas {
  id: number
  evento_id: string
  tipo: string
  payload: Record<string, unknown>
  boleto: number | null
  recebido_em: string
  processado_em: string | null
  resultado: string
}

export interface ContaPagar {
  conta_pagar_id: number
  fornecedor: number | null
  empreendimento: number | null
  nota_fiscal: number | null
  descricao: string
  valor: string
  data_emissao: string | null
  data_vencimento: string
  data_agendamento: string | null
  status: StatusConta
  valor_pago: string
  juros: string
  multa: string
  desconto: string
  data_pagamento: string | null
  total_devido: string
  saldo_aberto: string
  rateios: Rateio[]
  boletos: Boleto[]
}

/**
 * Payload de escrita de uma `ContaPagar` — campos de baixa (status, valor_pago,
 * juros, multa, desconto, data_pagamento, total_devido, saldo_aberto, boletos)
 * são somente leitura no backend e nunca aparecem aqui (alterados só via `dar-baixa`).
 */
export interface ContaPagarPayload {
  fornecedor: number | null
  empreendimento: number | null
  nota_fiscal?: number | null
  descricao: string
  valor: string
  data_emissao?: string | null
  data_vencimento: string
  data_agendamento?: string | null
  rateios?: RateioPayload[]
}

export interface ContaReceber {
  conta_receber_id: number
  cliente: number | null
  empreendimento: number | null
  nota_fiscal_recebida: number | null
  nota_fiscal_servico: number | null
  nota_fiscal_produto: number | null
  descricao: string
  valor: string
  data_emissao: string | null
  data_vencimento: string
  data_agendamento: string | null
  status: StatusConta
  valor_pago: string
  juros: string
  multa: string
  desconto: string
  data_recebimento: string | null
  total_devido: string
  saldo_aberto: string
  rateios: Rateio[]
  boletos: Boleto[]
}

/** Payload de escrita de uma `ContaReceber` — mesma regra do `ContaPagarPayload`. */
export interface ContaReceberPayload {
  cliente: number | null
  empreendimento: number | null
  nota_fiscal_recebida?: number | null
  nota_fiscal_servico?: number | null
  nota_fiscal_produto?: number | null
  descricao: string
  valor: string
  data_emissao?: string | null
  data_vencimento: string
  data_agendamento?: string | null
  rateios?: RateioPayload[]
}

/** Payload de `emitir-nfse`/`emitir-nfe` — campos opcionais (defaults vêm da conta/configuração do tenant). */
export interface EmitirNfPayload {
  descricao?: string
  city_service_code?: string
}

export interface CentroCusto {
  centro_custo_id: number
  nome: string
  codigo: string
  empreendimento: number | null
  ativo: boolean
}

/** Resumo de conta dentro de um lote — formato de `LoteRemessaSerializer.get_contas_resumo`. */
export interface LoteRemessaResumoConta {
  id: number
  descricao: string
  fornecedor: string | null
  valor: string
}

/** Registro do lote de remessa bancária — geração do arquivo CNAB fica fora do escopo (ver models.LoteRemessa). */
export interface LoteRemessa {
  lote_id: number
  status: StatusLote
  banco: string
  data_geracao: string
  data_envio: string | null
  valor_total: string
  observacoes: string
  contas_pagar: number[]
  contas_resumo: LoteRemessaResumoConta[]
}

/** Payload da ação `gerar-lote-remessa` (registro do lote — sem geração de arquivo CNAB). */
export interface GerarLoteRemessaPayload {
  conta_pagar_ids: number[]
  banco?: string
  observacoes?: string
}

/**
 * Payload da ação `dar-baixa` — usado tanto pela baixa manual (UI) quanto,
 * futuramente, pelo handler de webhook do Asaas (D.1.2): os dois caminhos
 * convergem no mesmo `model.dar_baixa()` com os mesmos tipos/regras.
 */
export interface BaixaPayload {
  valor: string
  data: string
  juros?: string
  multa?: string
  desconto?: string
  meio_pagamento?: string
}

/** Resposta paginada padrão do DRF (`ErpPageNumberPagination`). */
export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

/** Eixos comuns do filtro unificado (docs/modulos/moduloerp.md §5.1) — espelha `ContaPagarFilter`/`ContaReceberFilter`. */
export interface ContaFiltrosBase {
  status?: StatusConta
  empreendimento?: number
  data_de?: string
  data_ate?: string
  search?: string
  page?: number
  page_size?: number
  ordering?: string
}

export interface ContaPagarFiltros extends ContaFiltrosBase {
  fornecedor?: number
}

export interface ContaReceberFiltros extends ContaFiltrosBase {
  cliente?: number
}

export interface AgingFaixa {
  categoria: string
  total: string
}

export interface FluxoCaixaMes {
  mes: string
  receitas: string
  despesas: string
}

/** Payload de `/api/erp/dashboard/` (chaves em camelCase no backend). */
export interface ErpDashboardData {
  agingContasAReceber: AgingFaixa[]
  agingContasAPagar: AgingFaixa[]
  fluxoDeCaixaMensal: FluxoCaixaMes[]
}
