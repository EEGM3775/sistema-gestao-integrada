import { crmClient, CRM_BASE } from '../crmClient'
import type {
  Account,
  AccountPayload,
  PaginatedResponse,
} from '../../types'

export async function fetchAccounts(params?: { search?: string }): Promise<PaginatedResponse<Account>> {
  const { data } = await crmClient.get<PaginatedResponse<Account>>(`${CRM_BASE}accounts/`, {
    params: params?.search ? { search: params.search } : undefined,
  })
  return data
}

export async function fetchAccount(id: string): Promise<Account> {
  const { data } = await crmClient.get<Account>(`${CRM_BASE}accounts/${id}/`)
  return data
}

export async function createAccount(payload: AccountPayload): Promise<Account> {
  const { data } = await crmClient.post<Account>(`${CRM_BASE}accounts/`, payload)
  return data
}

export async function updateAccount(id: string, payload: AccountPayload): Promise<Account> {
  const { data } = await crmClient.put<Account>(`${CRM_BASE}accounts/${id}/`, payload)
  return data
}

export async function deleteAccount(id: string): Promise<void> {
  await crmClient.delete(`${CRM_BASE}accounts/${id}/`)
}