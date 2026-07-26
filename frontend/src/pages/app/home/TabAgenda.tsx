import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { CalendarDays } from 'lucide-react'
import { Card, Empty, Loading, Pill } from '@/components/malha'
import type { PillKind } from '@/components/malha'
import type { CalendarFeedEvent, EventSource } from '@/modules/calendar/types'
import { isoLocal } from '@/utils/dates'

/**
 * A agenda dos próximos 7 dias — o *Today's Tasks/Events* do Salesforce e o
 * *tasks on today's schedule* do Procore. O backend já entrega o feed
 * **agregado** (eventos próprios + diário de obra + feriados + compromissos do
 * CRM), então a home não junta nada: exibe o que o módulo calculou.
 */

const ORIGEM: Record<EventSource, { label: string; kind: PillKind }> = {
  local: { label: 'Agenda', kind: 'info' },
  diario_obra: { label: 'Diário', kind: 'net' },
  holiday: { label: 'Feriado', kind: 'slate' },
  tarefa: { label: 'Tarefa', kind: 'accent' },
  reuniao: { label: 'Reunião', kind: 'info' },
}

const diaISO = (iso: string) => iso.slice(0, 10)

function rotuloDoDia(iso: string): string {
  const hoje = new Date()
  const amanha = new Date(hoje)
  amanha.setDate(amanha.getDate() + 1)
  if (iso === isoLocal(hoje)) return 'Hoje'
  if (iso === isoLocal(amanha)) return 'Amanhã'
  // Meio-dia evita que o fuso empurre o rótulo para o dia anterior.
  const d = new Date(`${iso}T12:00:00`)
  return d.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })
}

function hora(ev: CalendarFeedEvent): string | null {
  if (ev.allDay) return null
  const d = new Date(ev.start)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

export function TabAgenda({
  eventos,
  carregando,
  erro,
}: {
  eventos: CalendarFeedEvent[] | undefined
  carregando: boolean
  erro: boolean
}) {
  const porDia = useMemo(() => {
    const mapa = new Map<string, CalendarFeedEvent[]>()
    for (const ev of eventos ?? []) {
      const k = diaISO(ev.start)
      const lista = mapa.get(k)
      if (lista) lista.push(ev)
      else mapa.set(k, [ev])
    }
    return [...mapa.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1))
  }, [eventos])

  if (carregando) return <Loading o="a agenda" />
  if (erro) return <Empty>Não foi possível carregar a agenda agora.</Empty>
  if (porDia.length === 0)
    return (
      <Empty>
        Nada agendado para os próximos 7 dias. O que aparece aqui vem do{' '}
        <Link to="/app/calendario" style={{ color: 'var(--brand)', fontWeight: 600 }}>
          calendário
        </Link>{' '}
        — eventos próprios, diário de obra, feriados e compromissos do CRM.
      </Empty>
    )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {porDia.map(([dia, evs]) => (
        <section key={dia}>
          <div
            style={{
              fontSize: 11,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              fontWeight: 700,
              color: 'var(--ink-3)',
              marginBottom: 8,
            }}
          >
            {rotuloDoDia(dia)}
          </div>
          <Card pad={false}>
            {evs.map((ev, i) => {
              const org = ORIGEM[ev.extendedProps.type] ?? { label: ev.extendedProps.type, kind: 'slate' as PillKind }
              const h = hora(ev)
              return (
                <div
                  key={`${dia}-${i}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '11px 16px',
                    borderTop: i === 0 ? 'none' : '1px solid var(--line-2)',
                  }}
                >
                  <span
                    className="num"
                    style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-3)', width: 46, flex: 'none' }}
                  >
                    {h ?? 'dia'}
                  </span>
                  <span style={{ fontSize: 13, color: 'var(--ink)', flex: 1, minWidth: 0 }}>{ev.title}</span>
                  <Pill kind={org.kind}>{org.label}</Pill>
                </div>
              )
            })}
          </Card>
        </section>
      ))}

      <Link
        to="/app/calendario"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 12.5,
          fontWeight: 600,
          color: 'var(--brand)',
        }}
      >
        <CalendarDays size={14} /> Abrir o calendário completo
      </Link>
    </div>
  )
}
