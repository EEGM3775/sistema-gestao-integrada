import { useEffect } from 'react'
import { X, MapPin, Users, Check, XCircle, Repeat } from 'lucide-react'
import { useCalendarEvent } from '../hooks/useCalendarEvents'
import { useResponderConvite } from '../hooks/useAgendas'
import { SOURCE_STYLE } from '../utils'
import { describeRRule } from '../recurrence'
import { buttonPrimaryStyle, buttonSecondaryStyle } from '../formStyles'

interface Props {
  /** Evento (ou mestre da série) a mostrar; `null` fecha. */
  eventId: number | null
  /** Cor da agenda do evento, quando o feed a trouxe. */
  cor?: string | null
  onClose: () => void
}

function quando(inicio: string, fim: string, diaInteiro: boolean): string {
  const a = new Date(inicio)
  const b = new Date(fim)
  if (diaInteiro) return a.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })
  const dia = a.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' })
  const h = (d: Date) => d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  return `${dia} · ${h(a)}–${h(b)}`
}

/**
 * O evento visto por quem **não pode alterá-lo** (Fatia D): o convidado de uma
 * agenda que não é dele. Mostra o que ele precisa para decidir — quando, onde,
 * quem organiza e quem mais vai — e as duas respostas. Numa série, a resposta
 * vale para a série inteira.
 */
export function ConviteDialog({ eventId, cor, onClose }: Props) {
  const { data: ev, isLoading } = useCalendarEvent(eventId ?? undefined)
  const responder = useResponderConvite()

  useEffect(() => {
    if (eventId == null) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [eventId, onClose])

  if (eventId == null) return null
  const faixa = cor || SOURCE_STYLE.local.bg

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center px-4">
      <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onClick={onClose} aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-label="Convite" className="relative w-full flex flex-col rounded-xl"
        style={{ maxWidth: 440, background: '#FFFFFF', boxShadow: 'var(--shadow-lg)', border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)' }}>
        <div className="h-1.5 rounded-t-xl" style={{ background: faixa }} />
        <header className="flex items-start justify-between gap-3 px-5 pt-4">
          <span className="text-[0.7rem] font-semibold uppercase tracking-wide" style={{ color: 'var(--color-text-muted)' }}>
            {ev?.my_status ? 'Convite' : 'Evento'}{ev ? ` · organizado por ${ev.owner_name}` : ''}
          </span>
          <button type="button" onClick={onClose} aria-label="Fechar" className="p-1.5 rounded-lg"
            style={{ color: 'var(--color-text-muted)', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </header>

        {isLoading || !ev ? (
          <p className="px-5 pb-5 pt-2 text-sm" style={{ color: 'var(--color-text-muted)' }}>Carregando o evento…</p>
        ) : (
          <div className="px-5 pb-5 pt-2 flex flex-col gap-2.5">
            <h2 className="text-lg font-bold leading-snug break-words" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              {ev.title}
            </h2>
            <p className="text-sm capitalize" style={{ color: 'var(--color-text-muted)' }}>
              {quando(ev.start_time, ev.end_time, ev.all_day)}
            </p>
            {ev.recurrence_rule && (
              <p className="flex items-center gap-1.5 text-sm" style={{ color: 'var(--color-text)' }}>
                <Repeat size={14} /> {describeRRule(ev.recurrence_rule)}
              </p>
            )}
            {ev.location && (
              <p className="flex items-center gap-1.5 text-sm" style={{ color: 'var(--color-text)' }}>
                <MapPin size={14} /> {ev.location}
              </p>
            )}
            {ev.description && (
              <p className="text-sm whitespace-pre-wrap break-words px-3 py-2 rounded-lg" style={{ background: '#f8fafc', color: 'var(--color-text)' }}>
                {ev.description}
              </p>
            )}
            {ev.attendees.length > 0 && (
              <div className="text-sm" style={{ color: 'var(--color-text)' }}>
                <span className="flex items-center gap-1.5 font-semibold mb-1"><Users size={14} /> Convidados</span>
                <ul className="flex flex-col gap-0.5 pl-5">
                  {ev.attendees.map(a => (
                    <li key={a.user}>
                      {a.nome} <span style={{ color: 'var(--color-text-muted)' }}>
                        — {a.status === 'aceito' ? 'vai' : a.status === 'recusado' ? 'não vai' : 'aguardando'}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {ev.my_status && (
              <div className="flex items-center gap-2 pt-2 mt-1" style={{ borderTop: '1px dashed #e2e8f0' }}>
                <span className="text-sm mr-auto" style={{ color: 'var(--color-text-muted)' }}>Você vai?</span>
                <button type="button" disabled={responder.isPending || ev.my_status === 'recusado'}
                  onClick={() => responder.mutate({ eventId: ev.id, status: 'recusado' })}
                  style={{ ...buttonSecondaryStyle, display: 'flex', alignItems: 'center', gap: 6, opacity: ev.my_status === 'recusado' ? 0.55 : 1 }}>
                  <XCircle size={15} /> {ev.my_status === 'recusado' ? 'Recusado' : 'Recusar'}
                </button>
                <button type="button" disabled={responder.isPending || ev.my_status === 'aceito'}
                  onClick={() => responder.mutate({ eventId: ev.id, status: 'aceito' })}
                  style={{ ...buttonPrimaryStyle, display: 'flex', alignItems: 'center', gap: 6, opacity: ev.my_status === 'aceito' ? 0.55 : 1 }}>
                  <Check size={15} /> {ev.my_status === 'aceito' ? 'Aceito' : 'Aceitar'}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
