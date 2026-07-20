import { crmClient, CRM_BASE } from '../crmClient'
import type {
  Contact,
  ContactPayload,
  PaginatedResponse,
} from '../../types'

export async function fetchContacts(params?: { search?: string }): Promise<PaginatedResponse<Contact>> {
  const { data } = await crmClient.get<PaginatedResponse<Contact>>(`${CRM_BASE}contacts/`, {
    params: params?.search ? { search: params.search } : undefined,
  })
  return data
}

export async function fetchContact(id: string): Promise<Contact> {
  const { data } = await crmClient.get<Contact>(`${CRM_BASE}contacts/${id}/`)
  return data
}

export async function createContact(payload: ContactPayload): Promise<Contact> {
  const { data } = await crmClient.post<Contact>(`${CRM_BASE}contacts/`, payload)
  return data
}

export async function updateContact(id: string, payload: ContactPayload): Promise<Contact> {
  const { data } = await crmClient.put<Contact>(`${CRM_BASE}contacts/${id}/`, payload)
  return data
}

export async function deleteContact(id: string): Promise<void> {
  await crmClient.delete(`${CRM_BASE}contacts/${id}/`)
}