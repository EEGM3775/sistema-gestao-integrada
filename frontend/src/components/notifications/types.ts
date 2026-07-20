/** Notificação in-app (centro de notificações / sino do topbar). */
export interface Notificacao {
  id: number
  titulo: string
  mensagem: string
  tipo: 'lembrete' | 'sistema'
  url: string
  lida: boolean
  lida_em: string | null
  criado_em: string
}
