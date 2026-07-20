import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchNotificacoes, fetchUnreadCount, marcarLida, marcarTodasLidas } from './api'

const keys = {
  all: ['notificacoes'] as const,
  list: ['notificacoes', 'list'] as const,
  unread: ['notificacoes', 'unread-count'] as const,
}

/** Contador de não-lidas para o badge — revalida a cada 60s (polling). */
export function useUnreadCount() {
  return useQuery({
    queryKey: keys.unread,
    queryFn: fetchUnreadCount,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  })
}

/** Lista de notificações — só busca quando o painel do sino está aberto. */
export function useNotificacoes(enabled: boolean) {
  return useQuery({
    queryKey: keys.list,
    queryFn: fetchNotificacoes,
    enabled,
  })
}

export function useMarcarLida() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => marcarLida(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.all }),
  })
}

export function useMarcarTodasLidas() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => marcarTodasLidas(),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.all }),
  })
}
