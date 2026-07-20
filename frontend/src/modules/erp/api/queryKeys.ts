import type {
  BoletoFiltros, ContaPagarFiltros, ContaReceberFiltros,
  NotaFiscalRecebidaFiltros, NotaFiscalServicoFiltros,
} from '../types'

/**
 * Fábrica de chaves do TanStack Query (D.1.0/D.1.1 — camada de dados).
 *
 * Toda mutação que afeta uma `ContaPagar`/`ContaReceber` (baixa, rateio,
 * emissão de NF, lote de remessa) invalida `erpKeys.contasAPagar.all` /
 * `erpKeys.contasAReceber.all` + `erpKeys.dashboard.all` — isso é o que
 * resolve, de forma genérica, o "mesmo dado visto de ângulos diferentes"
 * (dashboard, obra, cliente/fornecedor) sem refresh manual (docs/modulos/moduloerp.md §5.4).
 */
export const erpKeys = {
  all: ['erp'] as const,

  contasAPagar: {
    all: ['erp', 'contas-a-pagar'] as const,
    list: (filtros: ContaPagarFiltros = {}) => ['erp', 'contas-a-pagar', 'list', filtros] as const,
    detail: (id: number) => ['erp', 'contas-a-pagar', 'detail', id] as const,
  },

  contasAReceber: {
    all: ['erp', 'contas-a-receber'] as const,
    list: (filtros: ContaReceberFiltros = {}) => ['erp', 'contas-a-receber', 'list', filtros] as const,
    detail: (id: number) => ['erp', 'contas-a-receber', 'detail', id] as const,
  },

  boletos: {
    all: ['erp', 'boletos'] as const,
    list: (filtros: BoletoFiltros = {}) => ['erp', 'boletos', 'list', filtros] as const,
    detail: (id: number) => ['erp', 'boletos', 'detail', id] as const,
  },

  eventosWebhookAsaas: {
    all: ['erp', 'eventos-webhook-asaas'] as const,
    porBoleto: (boletoId: number) => ['erp', 'eventos-webhook-asaas', 'boleto', boletoId] as const,
  },

  centrosCusto: {
    all: ['erp', 'centros-custo'] as const,
    list: () => ['erp', 'centros-custo', 'list'] as const,
  },

  lotesRemessa: {
    all: ['erp', 'lotes-remessa'] as const,
    list: () => ['erp', 'lotes-remessa', 'list'] as const,
    detail: (id: number) => ['erp', 'lotes-remessa', 'detail', id] as const,
  },

  notasFiscaisServico: {
    all: ['erp', 'notas-fiscais-servico'] as const,
    list: (filtros: NotaFiscalServicoFiltros = {}) => ['erp', 'notas-fiscais-servico', 'list', filtros] as const,
  },

  notasFiscaisRecebidas: {
    all: ['erp', 'notas-fiscais'] as const,
    list: (filtros: NotaFiscalRecebidaFiltros = {}) => ['erp', 'notas-fiscais', 'list', filtros] as const,
  },

  dashboard: {
    all: ['erp', 'dashboard'] as const,
    summary: (empreendimentoId?: number) => ['erp', 'dashboard', 'summary', empreendimentoId ?? null] as const,
  },
}
