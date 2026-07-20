import apiClient from '@/api/apiClient'

/** Reexporta o `apiClient` autenticado — todo endpoint do CRM cai sob `/crm/`. */
export const crmClient = apiClient
export const CRM_BASE = 'crm/'