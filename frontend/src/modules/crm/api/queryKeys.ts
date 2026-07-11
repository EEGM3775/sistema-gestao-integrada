import type { LeadFiltros, OpportunityFiltros, InteractionFiltros } from '../types'

/**
 * Fábrica de chaves do TanStack Query para o módulo CRM.
 */
export const crmKeys = {
  all: ['crm'] as const,

  leads: {
    all: ['crm', 'leads'] as const,
    list: (filtros: LeadFiltros = {}) => ['crm', 'leads', 'list', filtros] as const,
    detail: (id: string) => ['crm', 'leads', 'detail', id] as const,
  },

  accounts: {
    all: ['crm', 'accounts'] as const,
    list: (params?: { search?: string }) => ['crm', 'accounts', 'list', params] as const,
    detail: (id: string) => ['crm', 'accounts', 'detail', id] as const,
  },

  contacts: {
    all: ['crm', 'contacts'] as const,
    list: (params?: { search?: string }) => ['crm', 'contacts', 'list', params] as const,
    detail: (id: string) => ['crm', 'contacts', 'detail', id] as const,
  },

  opportunities: {
    all: ['crm', 'opportunities'] as const,
    list: (filtros: OpportunityFiltros = {}) => ['crm', 'opportunities', 'list', filtros] as const,
    detail: (id: string) => ['crm', 'opportunities', 'detail', id] as const,
  },

  interactions: {
    all: ['crm', 'interactions'] as const,
    list: (filtros: InteractionFiltros = {}) => ['crm', 'interactions', 'list', filtros] as const,
    detail: (id: string) => ['crm', 'interactions', 'detail', id] as const,
  },
}