import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { crmKeys } from '../api/queryKeys'
import {
  fetchAccounts,
  fetchAccount,
  createAccount,
  updateAccount,
  deleteAccount,
} from '../api/endpoints/accounts'
import type { AccountPayload } from '../types'

export function useAccounts(params?: { search?: string }) {
  return useQuery({
    queryKey: crmKeys.accounts.list(params),
    queryFn: () => fetchAccounts(params),
  })
}

export function useAccount(id: string | undefined) {
  return useQuery({
    queryKey: crmKeys.accounts.detail(id ?? ''),
    queryFn: () => fetchAccount(id as string),
    enabled: id != null,
  })
}

function useInvalidateAccounts() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: crmKeys.accounts.all })
  }
}

export function useCreateAccount() {
  const invalidate = useInvalidateAccounts()
  return useMutation({
    mutationFn: (payload: AccountPayload) => createAccount(payload),
    onSuccess: invalidate,
  })
}

export function useUpdateAccount() {
  const invalidate = useInvalidateAccounts()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: AccountPayload }) => updateAccount(id, payload),
    onSuccess: invalidate,
  })
}

export function useDeleteAccount() {
  const invalidate = useInvalidateAccounts()
  return useMutation({
    mutationFn: (id: string) => deleteAccount(id),
    onSuccess: invalidate,
  })
}