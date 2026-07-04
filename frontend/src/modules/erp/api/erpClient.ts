import apiClient from '@/api/apiClient'

/** Reexporta o `apiClient` autenticado — todo endpoint do ERP cai sob `/erp/`. */
export const erpClient = apiClient
export const ERP_BASE = 'erp/'
