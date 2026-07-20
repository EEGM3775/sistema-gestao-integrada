import apiClient from '@/api/apiClient'
import type { Notificacao } from './types'

const BASE = 'notificacoes/'

/** Notificações recentes do usuário (as não-lidas primeiro por ordenação do backend). */
export async function fetchNotificacoes(): Promise<Notificacao[]> {
  const { data } = await apiClient.get<Notificacao[]>(BASE)
  return data
}

/** Contador de não-lidas para o badge do sino (polling barato). */
export async function fetchUnreadCount(): Promise<number> {
  const { data } = await apiClient.get<{ count: number }>(`${BASE}unread-count/`)
  return data.count
}

export async function marcarLida(id: number): Promise<void> {
  await apiClient.post(`${BASE}${id}/marcar-lida/`)
}

export async function marcarTodasLidas(): Promise<void> {
  await apiClient.post(`${BASE}marcar-todas-lidas/`)
}
