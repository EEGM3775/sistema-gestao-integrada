/** Notificação in-app (centro de notificações / sino do topbar). */
export interface Notificacao {
  id: number
  titulo: string
  mensagem: string
  tipo: 'lembrete' | 'sistema'
  /** Os três níveis de `docs/modulos/funcoesnotificacoes.md`:
   *  1 Saber (cinza) · 2 Decidir (âmbar) · 3 Agir já (vermelho). */
  nivel: 1 | 2 | 3
  url: string
  lida: boolean
  lida_em: string | null
  criado_em: string
}
