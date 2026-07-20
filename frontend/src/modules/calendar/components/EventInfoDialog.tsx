import { useEffect } from 'react'
import { X, Info } from 'lucide-react'
import { SOURCE_STYLE, HOLIDAY_SCOPE_STYLE } from '../utils'
import type { EventSource, HolidayScope } from '../types'

/** Dados de um evento somente-leitura para exibição (feriado, diário, CRM). */
export interface EventInfo {
  title: string
  type: EventSource
  scope?: HolidayScope
  start?: string
  end?: string
  allDay?: boolean
  description?: string
  notes?: string
}

interface Props {
  info: EventInfo | null
  onClose: () => void
}

/** Data por extenso; para eventos "dia inteiro" a string vem sem hora — parse
 * como data local (evita o off-by-one do `new Date('YYYY-MM-DD')` em UTC). */
function formatWhen(info: EventInfo): string {
  if (!info.start) return ''
  const d = new Date(info.start.length <= 10 ? `${info.start}T00:00` : info.start)
  if (Number.isNaN(d.getTime())) return ''
  if (info.allDay) {
    return d.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })
  }
  const dia = d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' })
  const hora = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  return `${dia} · ${hora}`
}

/**
 * Diálogo de LEITURA para eventos não-editáveis (feriados, diário de obra,
 * tarefas/reuniões do CRM). Existe porque o título é truncado com reticências no
 * grid — clicar mostra o nome inteiro e o contexto. Eventos próprios (`local`)
 * abrem o `EventDialog` de edição.
 */
export function EventInfoDialog({ info, onClose }: Props) {
  useEffect(() => {
    if (!info) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [info, onClose])

  if (!info) return null

  const style = info.type === 'holiday' && info.scope
    ? HOLIDAY_SCOPE_STYLE[info.scope]
    : SOURCE_STYLE[info.type] ?? SOURCE_STYLE.local
  const quando = formatWhen(info)

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center px-4">
      <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onClick={onClose} aria-hidden="true" />

      <div
        role="dialog"
        aria-modal="true"
        aria-label="Detalhes do evento"
        className="relative w-full flex flex-col rounded-xl"
        style={{ maxWidth: 420, background: '#FFFFFF', boxShadow: 'var(--shadow-lg)', border: '1.5px solid #e2e8f0' }}
      >
        {/* Faixa de cor por tipo/escopo */}
        <div className="h-1.5 rounded-t-xl" style={{ background: style.bg }} />

        <header className="flex items-start justify-between gap-3 px-5 pt-4">
          <span className="inline-flex items-center gap-1.5 rounded-full pl-2 pr-2.5 py-1"
            style={{ background: '#f6f8fb', border: '1px solid #edf1f6' }}>
            <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: style.bg }} />
            <span className="text-[0.7rem] font-semibold" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
              {style.label}
            </span>
          </span>
          <button type="button" onClick={onClose} aria-label="Fechar" className="p-1.5 rounded-lg shrink-0"
            style={{ color: 'var(--color-text-muted)', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </header>

        <div className="px-5 pb-5 pt-3 flex flex-col gap-2">
          {/* Título completo — quebra em várias linhas em vez de truncar */}
          <h2 className="text-lg font-bold leading-snug break-words"
            style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            {info.title}
          </h2>

          {quando && (
            <p className="text-sm capitalize" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {quando}
            </p>
          )}

          {(info.description || info.notes) && (
            <div className="flex items-start gap-2 mt-1 px-3 py-2.5 rounded-lg"
              style={{ background: '#f8fafc', border: '1px solid #eef1f6' }}>
              <Info size={15} className="shrink-0 mt-0.5" style={{ color: 'var(--color-text-muted)' }} />
              <p className="text-sm whitespace-pre-wrap break-words" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}>
                {info.description || info.notes}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
