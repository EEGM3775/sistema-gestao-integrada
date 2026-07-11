import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { crmKeys } from '../api/queryKeys'
import {
  fetchContacts,
  fetchContact,
  createContact,
  updateContact,
  deleteContact,
} from '../api/endpoints/contacts'
import type { ContactPayload } from '../types'

export function useContacts(params?: { search?: string }) {
  return useQuery({
    queryKey: crmKeys.contacts.list(params),
    queryFn: () => fetchContacts(params),
  })
}

export function useContact(id: string | undefined) {
  return useQuery({
    queryKey: crmKeys.contacts.detail(id ?? ''),
    queryFn: () => fetchContact(id as string),
    enabled: id != null,
  })
}

function useInvalidateContacts() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: crmKeys.contacts.all })
  }
}

export function useCreateContact() {
  const invalidate = useInvalidateContacts()
  return useMutation({
    mutationFn: (payload: ContactPayload) => createContact(payload),
    onSuccess: invalidate,
  })
}

export function useUpdateContact() {
  const invalidate = useInvalidateContacts()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ContactPayload }) => updateContact(id, payload),
    onSuccess: invalidate,
  })
}

export function useDeleteContact() {
  const invalidate = useInvalidateContacts()
  return useMutation({
    mutationFn: (id: string) => deleteContact(id),
    onSuccess: invalidate,
  })
}