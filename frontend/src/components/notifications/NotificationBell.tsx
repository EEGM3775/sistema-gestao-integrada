import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, CheckCheck } from 'lucide-react'
import { useNotificacoes, useUnreadCount, useMarcarLida, useMarcarTodasLidas } from './useNotificacoes'
import type { Notificacao } from './types'

/** "há 5 min" / "há 2 h" / "há 3 dias" a partir de um ISO. */
function tempoRelativo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return 'agora'
  if (min < 60) return `há ${min} min`
  const h = Math.floor(min / 60)
  if (h < 24) return `há ${h} h`
  const d = Math.floor(h / 24)
  return `há ${d} dia${d > 1 ? 's' : ''}`
}

const COR_DO_NIVEL: Record<number, string> = {
  1: 'var(--color-text-muted)',
  2: 'var(--color-warning, #d97706)',
  3: 'var(--color-danger)',
}

export const NotificationBell: React.FC = () => {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const { data: unread = 0 } = useUnreadCount()
  const { data: notificacoes = [], isLoading } = useNotificacoes(open)
  const marcarLida = useMarcarLida()
  const marcarTodas = useMarcarTodasLidas()

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const onClickItem = (n: Notificacao) => {
    if (!n.lida) marcarLida.mutate(n.id)
    if (n.url) { setOpen(false); navigate(n.url) }
  }

  const badge = unread > 99 ? '99+' : String(unread)
  // "Agir já" fica no topo: é o que não pode esperar (funcoesnotificacoes §2).
  const ordenadas = [...notificacoes].sort(
    (a, b) => Number(b.nivel === 3 && !b.lida) - Number(a.nivel === 3 && !a.lida),
  )

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label={`Notificações${unread > 0 ? ` (${unread} não lidas)` : ''}`}
        className="relative flex items-center justify-center w-9 h-9 rounded-lg transition-colors duration-150"
        style={{ background: open ? 'rgba(255,255,255,0.12)' : 'rgba(255,255,255,0.08)', border: 'none', cursor: 'pointer' }}
        onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.12)')}
        onMouseLeave={(e) => { if (!open) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.08)' }}
      >
        <Bell size={17} style={{ color: '#FFFFFF' }} />
        {unread > 0 && (
          <span
            className="absolute -top-1 -right-1 min-w-[17px] h-[17px] px-1 rounded-full flex items-center justify-center text-[10px] font-bold"
            style={{ background: 'var(--color-danger)', color: '#FFFFFF', fontFamily: 'var(--font-body)' }}
          >
            {badge}
          </span>
        )}
      </button>

      {open && (
        <div
          className="absolute right-0 top-full mt-2 w-80 rounded-xl z-50 flex flex-col overflow-hidden"
          style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-lg)', border: '1px solid #e2e8f0', maxHeight: '70vh' }}
        >
          <div className="flex items-center justify-between px-4 py-2.5 border-b" style={{ borderColor: '#e2e8f0' }}>
            <p className="text-sm font-bold" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-heading)' }}>
              Notificações
            </p>
            {unread > 0 && (
              <button
                onClick={() => marcarTodas.mutate()}
                disabled={marcarTodas.isPending}
                className="flex items-center gap-1 text-xs font-medium"
                style={{ color: 'var(--color-brand-app)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
              >
                <CheckCheck size={13} /> Marcar todas
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto">
            {isLoading ? (
              <p className="px-4 py-6 text-sm text-center" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                Carregando…
              </p>
            ) : notificacoes.length === 0 ? (
              <div className="px-4 py-8 flex flex-col items-center gap-2" style={{ color: 'var(--color-text-muted)' }}>
                <Bell size={22} style={{ opacity: 0.4 }} />
                <p className="text-sm" style={{ fontFamily: 'var(--font-body)' }}>Nenhuma notificação</p>
              </div>
            ) : (
              ordenadas.map((n) => (
                <button
                  key={n.id}
                  onClick={() => onClickItem(n)}
                  className="w-full text-left px-4 py-3 border-b transition-colors duration-150 flex gap-2.5"
                  style={{ borderColor: '#f1f5f9', background: n.lida ? '#FFFFFF' : '#f5f8ff', cursor: 'pointer' }}
                  onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = '#f8fafc')}
                  onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = n.lida ? '#FFFFFF' : '#f5f8ff')}
                >
                  {!n.lida && (
                    <span
                      className="mt-1.5 w-2 h-2 rounded-full shrink-0"
                      style={{ background: COR_DO_NIVEL[n.nivel] ?? COR_DO_NIVEL[1] }}
                    />
                  )}
                  <span className={`flex-1 min-w-0 ${n.lida ? 'pl-[18px]' : ''}`}>
                    {n.nivel === 3 && (
                      <span className="block text-[10px] font-bold uppercase tracking-wide" style={{ color: COR_DO_NIVEL[3] }}>
                        Agir já
                      </span>
                    )}
                    <span className="block text-sm font-semibold truncate" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                      {n.titulo}
                    </span>
                    {n.mensagem && (
                      <span className="block text-xs mt-0.5" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                        {n.mensagem}
                      </span>
                    )}
                    <span className="block text-[11px] mt-1" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                      {tempoRelativo(n.criado_em)}
                    </span>
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default NotificationBell
