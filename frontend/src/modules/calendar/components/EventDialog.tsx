import { useEffect, useState } from 'react'
import { X, CalendarPlus, Trash2, Repeat, Bell, MapPin, Users } from 'lucide-react'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import {
  useCalendarEvent, useCreateEvent, useUpdateEvent, useDeleteEvent,
  useUpdateOccurrence, useDeleteOccurrence,
} from '../hooks/useCalendarEvents'
import { useAgendas } from '../hooks/useAgendas'
import { PessoasPicker, type PessoaEscolhida } from './PessoasPicker'
import type { CalendarEventPayload, EventType, OccurrenceRef, RecurrenceScope } from '../types'
import { EVENT_TYPE_LABEL, isoToLocalInput, isoToDateInput, localInputToIso, dateInputToIso } from '../utils'
import { RecurrenceEditor } from './RecurrenceEditor'
import { ScopeChooser } from './ScopeChooser'
import {
  inputStyle, selectStyle, labelStyle,
  buttonPrimaryStyle, buttonSecondaryStyle, buttonDangerStyle,
} from '../formStyles'

interface Props {
  open: boolean
  /** 'create' pré-preenche start/end; 'edit' carrega o evento por id. */
  mode: 'create' | 'edit'
  eventId?: number | string
  /** Presente quando se edita uma OCORRÊNCIA de série recorrente (Fatia B). */
  occurrence?: OccurrenceRef
  initialStart?: string
  initialEnd?: string
  initialAllDay?: boolean
  /** Agenda já escolhida ao criar (a única visível no painel, por exemplo). */
  initialCalendar?: number | null
  onClose: () => void
}

interface FormState {
  title: string
  event_type: EventType
  all_day: boolean
  start: string  // datetime-local (timed) ou date (all-day)
  end: string
  description: string
  recurrence_rule: string
  reminders: number[]  // offsets em minutos antes do início (Fatia C)
  calendar: number | null  // agenda (Fatia D); null = Meus eventos
  location: string  // Fatia E
  attendees: PessoaEscolhida[]  // convidados (Fatia D)
}

/** Opções de lembrete oferecidas no diálogo (offset em minutos → rótulo). */
const REMINDER_OPTIONS: { minutes: number; label: string }[] = [
  { minutes: 0, label: 'Na hora' },
  { minutes: 10, label: '10 min antes' },
  { minutes: 30, label: '30 min antes' },
  { minutes: 60, label: '1 hora antes' },
  { minutes: 1440, label: '1 dia antes' },
]

/** ISO do dia seguinte a 00:00 — fim exclusivo de um evento all-day (padrão FullCalendar). */
function allDayEndIso(dateStr: string): string {
  const d = new Date(`${dateStr}T00:00`)
  if (Number.isNaN(d.getTime())) return ''
  d.setDate(d.getDate() + 1)
  return d.toISOString()
}

function emptyForm(initialStart?: string, initialEnd?: string, initialAllDay?: boolean, initialCalendar?: number | null): FormState {
  const allDay = initialAllDay ?? false
  const now = new Date()
  const startIso = initialStart ?? now.toISOString()
  const endIso = initialEnd ?? new Date(now.getTime() + 60 * 60 * 1000).toISOString()
  return {
    title: '',
    event_type: 'tarefa',
    all_day: allDay,
    start: allDay ? isoToDateInput(startIso) : isoToLocalInput(startIso),
    end: allDay ? isoToDateInput(endIso) : isoToLocalInput(endIso),
    description: '',
    recurrence_rule: '',
    reminders: [],
    calendar: initialCalendar ?? null,
    location: '',
    attendees: [],
  }
}

export function EventDialog({ open, mode, eventId, occurrence, initialStart, initialEnd, initialAllDay, initialCalendar, onClose }: Props) {
  const [form, setForm] = useState<FormState>(() => emptyForm(initialStart, initialEnd, initialAllDay, initialCalendar))
  const { data: agendas = [] } = useAgendas()
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  // Quando editamos/excluímos uma ocorrência recorrente, guardamos a ação até
  // o usuário escolher o alcance (este/série/futuros).
  const [scopePrompt, setScopePrompt] = useState<'save' | 'delete' | null>(null)

  const isRecurringEdit = mode === 'edit' && occurrence != null
  // No modo "editar ocorrência", carregamos o MESTRE (título/tipo/regra vêm dele;
  // as datas vêm da ocorrência clicada). Nos demais, carregamos o próprio evento.
  const loadId = isRecurringEdit ? occurrence!.masterId : (mode === 'edit' ? eventId : undefined)
  const { data: loaded } = useCalendarEvent(loadId)

  const createMut = useCreateEvent()
  const updateMut = useUpdateEvent()
  const deleteMut = useDeleteEvent()
  const updateOccMut = useUpdateOccurrence()
  const deleteOccMut = useDeleteOccurrence()
  const pending = createMut.isPending || updateMut.isPending || deleteMut.isPending
    || updateOccMut.isPending || deleteOccMut.isPending

  // (Re)inicializa o formulário a cada abertura ou carga do registro editado.
  useEffect(() => {
    if (!open) return
    setFieldErrors({})
    setScopePrompt(null)
    if (mode === 'create') {
      setForm(emptyForm(initialStart, initialEnd, initialAllDay, initialCalendar))
    } else if (loaded) {
      const allDay = isRecurringEdit ? (initialAllDay ?? loaded.all_day) : loaded.all_day
      // Datas: da ocorrência (edição recorrente) ou do próprio evento.
      const startIso = isRecurringEdit && initialStart ? initialStart : loaded.start_time
      const endIso = isRecurringEdit && initialEnd ? initialEnd : loaded.end_time
      setForm({
        title: loaded.title,
        event_type: loaded.event_type,
        all_day: allDay,
        start: allDay ? isoToDateInput(startIso) : isoToLocalInput(startIso),
        end: allDay ? isoToDateInput(endIso) : isoToLocalInput(endIso),
        description: loaded.description ?? '',
        recurrence_rule: isRecurringEdit ? occurrence!.recurrenceRule : (loaded.recurrence_rule ?? ''),
        reminders: loaded.reminders ?? [],
        calendar: loaded.calendar ?? null,
        location: loaded.location ?? '',
        attendees: (loaded.attendees ?? []).map(a => ({ id: a.user, nome: a.nome, status: a.status })),
      })
    }
  }, [open, mode, loaded, isRecurringEdit, initialStart, initialEnd, initialAllDay, initialCalendar, occurrence])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !pending) onClose() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [open, onClose, pending])

  if (!open) return null

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm(prev => ({ ...prev, [key]: value }))
    setFieldErrors(prev => ({ ...prev, [String(key)]: '' }))
  }

  // Alterna all-day convertendo os valores entre date e datetime-local.
  const toggleAllDay = (allDay: boolean) => {
    setForm(prev => {
      const startIso = prev.all_day ? dateInputToIso(prev.start) : localInputToIso(prev.start)
      const endIso = prev.all_day ? dateInputToIso(prev.end) : localInputToIso(prev.end)
      return {
        ...prev,
        all_day: allDay,
        start: allDay ? isoToDateInput(startIso) : isoToLocalInput(startIso),
        end: allDay ? isoToDateInput(endIso) : isoToLocalInput(endIso),
      }
    })
  }

  const buildPayload = (): CalendarEventPayload | null => {
    const errs: FieldErrors = {}
    if (!form.title.trim()) errs.title = 'Informe um título.'
    if (!form.start) errs.start = 'Informe o início.'
    if (!form.end) errs.end = 'Informe o fim.'

    const start_time = form.all_day ? dateInputToIso(form.start) : localInputToIso(form.start)
    const end_time = form.all_day ? allDayEndIso(form.end) : localInputToIso(form.end)

    if (start_time && end_time && new Date(end_time) < new Date(start_time)) {
      errs.end = 'O fim não pode ser antes do início.'
    }
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs)
      return null
    }
    return {
      title: form.title.trim(),
      description: form.description.trim() || null,
      start_time,
      end_time,
      all_day: form.all_day,
      event_type: form.event_type,
      recurrence_rule: form.recurrence_rule,
      reminders: [...form.reminders].sort((a, b) => a - b),
      calendar: form.calendar,
      location: form.location.trim(),
      attendees: form.attendees.map(p => p.id),
    }
  }

  const toggleReminder = (minutes: number) => {
    setForm(prev => ({
      ...prev,
      reminders: prev.reminders.includes(minutes)
        ? prev.reminders.filter(m => m !== minutes)
        : [...prev.reminders, minutes],
    }))
  }

  const onError = (err: unknown) => setFieldErrors(parseApiErrors(err))

  const handleSave = () => {
    const payload = buildPayload()
    if (!payload) return
    if (mode === 'create') {
      createMut.mutate(payload, { onSuccess: onClose, onError })
    } else if (isRecurringEdit) {
      // Precisa do alcance antes de gravar.
      setScopePrompt('save')
    } else if (eventId != null) {
      updateMut.mutate({ id: eventId, payload }, { onSuccess: onClose, onError })
    }
  }

  const handleDelete = () => {
    if (isRecurringEdit) {
      setScopePrompt('delete')
    } else if (eventId != null) {
      deleteMut.mutate(eventId, { onSuccess: onClose, onError })
    }
  }

  // Aplica a ação recorrente com o alcance escolhido.
  const applyScope = (scope: RecurrenceScope) => {
    if (!occurrence) return
    if (scopePrompt === 'delete') {
      deleteOccMut.mutate(
        { masterId: occurrence.masterId, scope, occurrenceStart: occurrence.occurrenceStart },
        { onSuccess: onClose, onError },
      )
      return
    }
    const payload = buildPayload()
    if (!payload) { setScopePrompt(null); return }
    // Lembretes propagam pelo escopo escolhido (C1): 'todas' substitui os do
    // mestre; 'futuras' abastece o novo mestre; 'só esta', o override.
    // "Somente este" não altera a regra da série.
    if (scope === 'this') delete payload.recurrence_rule
    // Agenda e convidados são da série: só a edição de "todas" os muda (as
    // outras herdam os do mestre no backend).
    if (scope !== 'all') { delete payload.calendar; delete payload.attendees }
    updateOccMut.mutate(
      { masterId: occurrence.masterId, scope, occurrenceStart: occurrence.occurrenceStart, payload },
      { onSuccess: onClose, onError },
    )
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center px-4">
      <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onClick={() => !pending && onClose()} aria-hidden="true" />

      <div
        role="dialog"
        aria-modal="true"
        aria-label={mode === 'create' ? 'Novo evento' : 'Editar evento'}
        className="relative w-full flex flex-col rounded-xl"
        style={{ maxWidth: 480, maxHeight: '88vh', background: '#FFFFFF', boxShadow: 'var(--shadow-lg)', border: '1.5px solid #e2e8f0' }}
      >
        <header className="flex items-start justify-between gap-3 px-5 py-4" style={{ borderBottom: '1.5px solid #e2e8f0' }}>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: '#e0e7ff', color: '#1e40af' }}>
              <CalendarPlus size={18} />
            </div>
            <h2 className="text-base font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              {mode === 'create' ? 'Novo evento' : 'Editar evento'}
            </h2>
          </div>
          <button type="button" onClick={() => !pending && onClose()} aria-label="Fechar" className="p-1.5 rounded-lg shrink-0"
            style={{ color: 'var(--color-text-muted)', cursor: pending ? 'not-allowed' : 'pointer' }}>
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-3.5">
          <FormErrorBanner errors={fieldErrors} />

          <div>
            <label htmlFor="ev-title" style={labelStyle}>Título</label>
            <input id="ev-title" style={inputStyle} value={form.title} autoFocus
              onChange={e => set('title', e.target.value)} placeholder="Ex.: Reunião de obra" />
            <FieldError msg={fieldErrors.title} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="ev-type" style={labelStyle}>Tipo</label>
              <select id="ev-type" style={selectStyle} value={form.event_type}
                onChange={e => set('event_type', e.target.value as EventType)}>
                {(Object.keys(EVENT_TYPE_LABEL) as EventType[]).map(t => (
                  <option key={t} value={t}>{EVENT_TYPE_LABEL[t]}</option>
                ))}
              </select>
            </div>
            <div className="flex items-end pb-1.5">
              <label className="flex items-center gap-2 cursor-pointer" style={{ fontFamily: 'var(--font-body)', fontSize: '0.85rem', color: 'var(--color-text)' }}>
                <input type="checkbox" checked={form.all_day} onChange={e => toggleAllDay(e.target.checked)} />
                Dia inteiro
              </label>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="ev-start" style={labelStyle}>Início</label>
              <input id="ev-start" type={form.all_day ? 'date' : 'datetime-local'} style={inputStyle}
                value={form.start} onChange={e => set('start', e.target.value)} />
              <FieldError msg={fieldErrors.start || fieldErrors.start_time} />
            </div>
            <div>
              <label htmlFor="ev-end" style={labelStyle}>Fim</label>
              <input id="ev-end" type={form.all_day ? 'date' : 'datetime-local'} style={inputStyle}
                value={form.end} onChange={e => set('end', e.target.value)} />
              <FieldError msg={fieldErrors.end || fieldErrors.end_time} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="ev-agenda" style={labelStyle}>Agenda</label>
              <select id="ev-agenda" style={selectStyle} value={form.calendar ?? ''}
                onChange={e => set('calendar', e.target.value ? Number(e.target.value) : null)}>
                <option value="">Meus eventos</option>
                {agendas.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="ev-local" style={labelStyle}>
                <span className="inline-flex items-center gap-1"><MapPin size={12} /> Local</span>
              </label>
              <input id="ev-local" style={inputStyle} value={form.location} maxLength={255}
                onChange={e => set('location', e.target.value)} placeholder="Ex.: canteiro, sala 2" />
            </div>
          </div>

          <div className="pt-1" style={{ borderTop: '1px dashed #e2e8f0' }}>
            <div className="flex items-center gap-1.5 mt-3 mb-2" style={{ color: 'var(--color-brand)' }}>
              <Users size={14} />
              <span className="text-xs font-bold uppercase tracking-wide" style={{ fontFamily: 'var(--font-body)' }}>Convidados</span>
            </div>
            <PessoasPicker
              valor={form.attendees}
              aoMudar={pessoas => set('attendees', pessoas)}
              excluir={loaded ? [loaded.user] : []}
              aria-label="Convidar pessoa"
            />
            <p className="mt-1.5 text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              {isRecurringEdit
                ? 'Convidados e agenda valem para a série — mudam ao salvar "todos os eventos".'
                : 'Quem você convidar vê o evento na própria agenda e responde se vai.'}
            </p>
          </div>

          <div className="pt-1" style={{ borderTop: '1px dashed #e2e8f0' }}>
            <div className="flex items-center gap-1.5 mt-3 mb-2" style={{ color: 'var(--color-brand)' }}>
              <Repeat size={14} />
              <span className="text-xs font-bold uppercase tracking-wide" style={{ fontFamily: 'var(--font-body)' }}>Recorrência</span>
            </div>
            <RecurrenceEditor
              value={form.recurrence_rule}
              onChange={rule => set('recurrence_rule', rule)}
              anchorDate={form.start}
            />
          </div>

          {/* Lembretes (Fatia C) — geridos no CRUD do evento; para séries
              recorrentes, definidos na criação (a edição de ocorrência não os altera). */}
          {!isRecurringEdit && (
            <div className="pt-1" style={{ borderTop: '1px dashed #e2e8f0' }}>
              <div className="flex items-center gap-1.5 mt-3 mb-2" style={{ color: 'var(--color-brand)' }}>
                <Bell size={14} />
                <span className="text-xs font-bold uppercase tracking-wide" style={{ fontFamily: 'var(--font-body)' }}>Lembretes</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {REMINDER_OPTIONS.map(opt => {
                  const active = form.reminders.includes(opt.minutes)
                  return (
                    <button
                      key={opt.minutes}
                      type="button"
                      onClick={() => toggleReminder(opt.minutes)}
                      className="px-2.5 py-1 rounded-full text-xs font-medium transition-colors duration-150"
                      style={{
                        fontFamily: 'var(--font-body)',
                        cursor: 'pointer',
                        border: `1px solid ${active ? 'var(--color-brand-app)' : '#cbd5e1'}`,
                        background: active ? 'var(--color-brand-app)' : '#FFFFFF',
                        color: active ? '#FFFFFF' : 'var(--color-text-muted)',
                      }}
                    >
                      {opt.label}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          <div>
            <label htmlFor="ev-desc" style={labelStyle}>Descrição</label>
            <textarea id="ev-desc" style={{ ...inputStyle, minHeight: 72, resize: 'vertical' }}
              value={form.description} onChange={e => set('description', e.target.value)}
              placeholder="Detalhes (opcional)" />
          </div>
        </div>

        <footer className="flex items-center justify-between gap-2 px-5 py-3.5" style={{ borderTop: '1.5px solid #e2e8f0', background: '#f8fafc' }}>
          <div>
            {mode === 'edit' && (
              <button type="button" onClick={handleDelete} disabled={pending}
                style={{ ...buttonDangerStyle, opacity: pending ? 0.6 : 1, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Trash2 size={15} /> Excluir
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={onClose} disabled={pending} style={{ ...buttonSecondaryStyle, opacity: pending ? 0.6 : 1 }}>
              Cancelar
            </button>
            <button type="button" onClick={handleSave} disabled={pending}
              style={{ ...buttonPrimaryStyle, opacity: pending ? 0.6 : 1, cursor: pending ? 'wait' : 'pointer' }}>
              {pending ? 'Salvando…' : 'Salvar'}
            </button>
          </div>
        </footer>
      </div>

      {scopePrompt && (
        <ScopeChooser
          action={scopePrompt}
          pending={pending}
          onChoose={applyScope}
          onCancel={() => setScopePrompt(null)}
        />
      )}
    </div>
  )
}
