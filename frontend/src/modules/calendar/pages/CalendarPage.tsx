import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import listPlugin from '@fullcalendar/list'
import interactionPlugin from '@fullcalendar/interaction'
import ptBrLocale from '@fullcalendar/core/locales/pt-br'
import type { DateSelectArg, EventClickArg, EventDropArg, DatesSetArg } from '@fullcalendar/core'
import type { EventResizeDoneArg } from '@fullcalendar/interaction'
import { Plus, RefreshCw, CalendarDays } from 'lucide-react'
import { SelectComBusca } from '@/components/malha'
import { calendarKeys } from '../api/queryKeys'
import { fetchEvent } from '../api/endpoints/events'
import { AgendasPanel, type ChaveAgenda } from '../components/AgendasPanel'
import { ConviteDialog } from '../components/ConviteDialog'
import { useCalendarEvents, useUpdateEvent } from '../hooks/useCalendarEvents'
import { useFeriadosStatus } from '../hooks/useLocalidades'
import { usePersistedState } from '../hooks/usePersistedState'
import { EventDialog } from '../components/EventDialog'
import { EventInfoDialog, type EventInfo } from '../components/EventInfoDialog'
import { LocalidadeSelector } from '../components/LocalidadeSelector'
import { SOURCE_STYLE, HOLIDAY_SCOPE_STYLE } from '../utils'
import type { CalendarRange, EventoAchado, EventSource, HolidayScope, LocalidadeSelecionada, OccurrenceRef } from '../types'

/** Variáveis de tema do FullCalendar alinhadas ao design navy do SGI. */
const fcTheme: CSSProperties = {
  fontFamily: 'var(--font-body)',
  ['--fc-border-color' as string]: '#eef1f6',
  ['--fc-today-bg-color' as string]: 'rgba(10, 42, 91, 0.045)',
  ['--fc-page-bg-color' as string]: '#FFFFFF',
  ['--fc-neutral-bg-color' as string]: '#f8fafc',
  ['--fc-list-event-hover-bg-color' as string]: '#f5f7fb',
  ['--fc-now-indicator-color' as string]: '#e11d48',
}

/**
 * Refinamentos visuais do FullCalendar (escopados por `.sgi-calendar`) — o v6
 * injeta o essencial por variáveis `--fc-*`, mas o polimento (botões-pílula,
 * eventos arredondados, cabeçalhos, "hoje" em destaque) precisa de classe.
 */
const CALENDAR_CSS = `
.sgi-calendar .fc { --fc-small-font-size: 0.78rem; }
.sgi-calendar .fc .fc-toolbar.fc-header-toolbar { margin-bottom: 1rem; gap: 0.75rem; flex-wrap: wrap; }
.sgi-calendar .fc .fc-toolbar-title {
  font-family: var(--font-heading); font-size: 1.15rem; font-weight: 700;
  color: var(--color-brand); text-transform: capitalize; letter-spacing: -0.01em;
}
/* Botões: pílula clara; ativo = navy */
.sgi-calendar .fc .fc-button {
  background: #FFFFFF; border: 1.5px solid #e6eaf1; color: var(--color-brand);
  font-family: var(--font-body); font-weight: 600; font-size: 0.8rem;
  text-transform: capitalize; padding: 0.42rem 0.85rem; border-radius: 9px;
  box-shadow: none; transition: background .15s, color .15s, border-color .15s;
}
.sgi-calendar .fc .fc-button:hover { background: #f1f4f9; border-color: #dde3ec; color: var(--color-brand-dark); }
.sgi-calendar .fc .fc-button:focus { box-shadow: 0 0 0 3px rgba(10,42,91,0.14); }
.sgi-calendar .fc .fc-button-primary:not(:disabled).fc-button-active,
.sgi-calendar .fc .fc-button-primary:not(:disabled):active {
  background: var(--color-brand); border-color: var(--color-brand); color: #FFFFFF;
}
.sgi-calendar .fc .fc-button-primary:disabled { background: #f1f4f9; border-color: #e6eaf1; color: #aab4c4; opacity: 1; }
.sgi-calendar .fc .fc-button-group > .fc-button { border-radius: 9px; }
.sgi-calendar .fc .fc-button-group > .fc-button:not(:last-child) { margin-right: 4px; }
.sgi-calendar .fc .fc-icon { font-size: 1.15em; }
/* Cabeçalho dos dias da semana */
.sgi-calendar .fc .fc-col-header-cell { background: #fbfcfe; }
.sgi-calendar .fc .fc-col-header-cell-cushion {
  text-transform: uppercase; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.05em;
  color: var(--color-text-muted); padding: 10px 6px;
}
/* Números dos dias */
.sgi-calendar .fc .fc-daygrid-day-number { font-size: 0.8rem; font-weight: 600; color: #64748b; padding: 6px 8px; }
.sgi-calendar .fc .fc-day-today .fc-daygrid-day-number {
  color: #FFFFFF; background: var(--color-brand); border-radius: 999px;
  min-width: 1.55rem; height: 1.55rem; display: inline-flex; align-items: center;
  justify-content: center; margin: 4px 4px 0 0; padding: 0;
}
.sgi-calendar .fc .fc-day-other .fc-daygrid-day-number { color: #cbd3df; }
/* Eventos: arredondados, sólidos, sem borda dura */
.sgi-calendar .fc .fc-daygrid-event {
  border-radius: 7px; padding: 2px 7px; font-weight: 600; font-size: 0.76rem;
  border: none; margin: 1px 3px; box-shadow: 0 1px 2px rgba(15,23,42,0.08);
}
.sgi-calendar .fc .fc-daygrid-event:hover { filter: brightness(0.94); }
/* Cursor de ponteiro (não o I-beam de texto) e texto não-selecionável nos eventos */
.sgi-calendar .fc .fc-event, .sgi-calendar .fc .fc-event .fc-event-main { cursor: pointer; }
.sgi-calendar .fc .fc-event .fc-event-main, .sgi-calendar .fc .fc-list-event { user-select: none; }
/* Título com reticências quando não cabe (mês/dia), em vez de cortar no meio */
.sgi-calendar .fc .fc-daygrid-event { overflow: hidden; }
.sgi-calendar .fc .fc-daygrid-event .fc-event-title {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0;
}
.sgi-calendar .fc .fc-h-event, .sgi-calendar .fc .fc-v-event { border: none; }
.sgi-calendar .fc .fc-timegrid-event { border-radius: 7px; border: none; box-shadow: 0 1px 2px rgba(15,23,42,0.1); }
.sgi-calendar .fc .fc-daygrid-more-link { font-weight: 600; color: var(--color-brand); font-size: 0.72rem; }
/* Bordas suaves da grade */
.sgi-calendar .fc .fc-scrollgrid { border-radius: 12px; overflow: hidden; }
.sgi-calendar .fc .fc-scrollgrid, .sgi-calendar .fc td, .sgi-calendar .fc th { border-color: #eef1f6; }
/* Lista/agenda */
.sgi-calendar .fc .fc-list { border-radius: 12px; overflow: hidden; }
.sgi-calendar .fc .fc-list-day-cushion { background: #f8fafc; }
.sgi-calendar .fc .fc-list-event td { font-size: 0.85rem; }
.sgi-calendar .fc .fc-list-event-dot { border-width: 5px; }
/* Convite ainda sem resposta: tracejado; recusado: apagado e riscado (Fatia D) */
.sgi-calendar .fc .sgi-convite-pendente { outline: 2px dashed rgba(255,255,255,0.85); outline-offset: -3px; }
.sgi-calendar .fc .sgi-convite-recusado { opacity: 0.45; }
.sgi-calendar .fc .sgi-convite-recusado .fc-event-title { text-decoration: line-through; }
`

/** Itens da legenda: origens dos eventos + escopos de feriado. */
const LEGEND_ITEMS: { bg: string; label: string }[] = [
  ...(['local', 'reuniao', 'tarefa', 'diario_obra'] as EventSource[]).map(s => ({
    bg: SOURCE_STYLE[s].bg, label: SOURCE_STYLE[s].label,
  })),
  ...(Object.keys(HOLIDAY_SCOPE_STYLE) as HolidayScope[]).map(s => ({
    bg: HOLIDAY_SCOPE_STYLE[s].bg, label: HOLIDAY_SCOPE_STYLE[s].label,
  })),
]

const novoEventoBtn: CSSProperties = {
  padding: '9px 16px', borderRadius: '10px', border: 'none',
  background: 'linear-gradient(135deg, var(--color-brand), var(--color-brand-surface))',
  color: '#FFFFFF', fontSize: '0.85rem', fontWeight: 600, fontFamily: 'var(--font-body)',
  cursor: 'pointer', boxShadow: '0 2px 10px rgba(10,42,91,0.28)',
}

interface DialogState {
  open: boolean
  mode: 'create' | 'edit'
  eventId?: string
  occurrence?: OccurrenceRef
  initialStart?: string
  initialEnd?: string
  initialAllDay?: boolean
}

const CLOSED: DialogState = { open: false, mode: 'create' }

const CalendarPage: React.FC = () => {
  const [janela, setJanela] = useState<{ start: string; end: string } | null>(null)
  const [localidade, setLocalidade] = usePersistedState<LocalidadeSelecionada>(
    'sgi_calendar_localidade', { uf: '', ibge: '' },
  )
  const [dialog, setDialog] = useState<DialogState>(CLOSED)
  const [info, setInfo] = useState<EventInfo | null>(null)
  // Fatia D: o evento que a pessoa vê mas não altera (convite) e as agendas ocultas.
  const [convite, setConvite] = useState<{ id: number; cor?: string | null } | null>(null)
  const [ocultas, setOcultas] = usePersistedState<ChaveAgenda[]>('sgi_calendar_ocultas', [])
  const calendarRef = useRef<FullCalendar>(null)
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()

  /** Abre um evento pelo id (busca, ou o link `?evento=` do sino): leva o grid
   *  até a data e abre a edição — ou a leitura, se a pessoa não pode alterá-lo
   *  ou se é uma série (que se edita pela ocorrência, no grid). */
  const abrirEvento = useCallback(async (id: number) => {
    try {
      const ev = await queryClient.fetchQuery({
        queryKey: calendarKeys.events.detail(id), queryFn: () => fetchEvent(id),
      })
      calendarRef.current?.getApi().gotoDate(ev.start_time)
      if (ev.can_edit && !ev.recurrence_rule) setDialog({ open: true, mode: 'edit', eventId: String(id) })
      else setConvite({ id })
    } catch {
      /* evento apagado ou fora do alcance: o grid fica onde está */
    }
  }, [queryClient])

  // `?evento=<id>` — o aviso de convite no sino leva direto ao evento.
  useEffect(() => {
    const alvo = Number(params.get('evento'))
    if (!alvo) return
    void abrirEvento(alvo)
    const resto = new URLSearchParams(params)
    resto.delete('evento')
    setParams(resto, { replace: true })
  }, [params, setParams, abrirEvento])

  // Janela do FullCalendar + localidade escolhida = consulta ao feed.
  const range: CalendarRange | null = janela
    ? { ...janela, uf: localidade.uf, ibge: localidade.ibge }
    : null

  const { data, isError } = useCalendarEvents(range)
  const { data: feriadosStatus } = useFeriadosStatus()  // null p/ não-superuser (403)
  const updateMut = useUpdateEvent()

  const fcEvents = useMemo(
    () =>
      (data ?? []).filter(e => {
        // Agenda oculta no painel: some do grid. Convite numa agenda que não é
        // da pessoa não tem chave no painel e sempre aparece.
        if (e.extendedProps.type !== 'local') return true
        const p = e.extendedProps
        const chave: ChaveAgenda | null = p.calendarId != null ? (p.calendarId as number)
          : p.ownerName ? null : 'meus'
        return chave == null || !ocultas.includes(chave)
      }).map((e, i) => {
        // Feriados: cor por escopo (nacional/estadual/municipal); demais: por origem.
        const scope = e.extendedProps.scope as HolidayScope | undefined
        const style = e.extendedProps.type === 'holiday' && scope && HOLIDAY_SCOPE_STYLE[scope]
          ? HOLIDAY_SCOPE_STYLE[scope]
          : SOURCE_STYLE[e.extendedProps.type] ?? SOURCE_STYLE.local
        const isRecurring = e.extendedProps.isRecurring === true
        // Ocorrências virtuais de série não arrastam (o mover exige escolher o
        // alcance no diálogo); únicos e overrides concretos seguem editáveis.
        const p = e.extendedProps
        const editable = p.type === 'local' && !isRecurring && p.canEdit !== false
        const corAgenda = p.type === 'local' && typeof p.color === 'string' ? p.color : null
        return {
          id: e.id != null ? String(e.id) : `${e.extendedProps.type}-${i}`,
          title: e.title,
          start: e.start,
          end: e.end,
          allDay: e.allDay,
          backgroundColor: corAgenda ?? style.bg,
          borderColor: corAgenda ?? style.border,
          textColor: style.text,
          editable,
          classNames: p.myStatus === 'pendente' ? ['sgi-convite-pendente']
            : p.myStatus === 'recusado' ? ['sgi-convite-recusado'] : [],
          extendedProps: e.extendedProps,
        }
      }),
    [data, ocultas],
  )

  const handleDatesSet = (arg: DatesSetArg) => {
    setJanela({ start: arg.startStr, end: arg.endStr })
  }

  const handleSelect = (arg: DateSelectArg) => {
    setDialog({ open: true, mode: 'create', initialStart: arg.startStr, initialEnd: arg.endStr, initialAllDay: arg.allDay })
  }

  const handleEventClick = (arg: EventClickArg) => {
    const p = arg.event.extendedProps
    if (p.type !== 'local') {
      // Eventos somente-leitura (feriado, diário, tarefa/reunião do CRM): o
      // título é truncado no grid, então clicar abre a leitura com o nome inteiro.
      setInfo({
        title: arg.event.title,
        type: p.type as EventSource,
        scope: p.scope as HolidayScope | undefined,
        start: arg.event.allDay ? arg.event.startStr : (arg.event.start?.toISOString() ?? arg.event.startStr),
        end: (arg.event.end ?? arg.event.start)?.toISOString(),
        allDay: arg.event.allDay,
        description: p.description as string | undefined,
        notes: p.notes as string | undefined,
      })
      return
    }
    if (p.canEdit === false) {
      // Convite numa agenda que a pessoa não vê: ela lê e responde (Fatia D).
      setConvite({ id: (p.masterId as number | undefined) ?? Number(arg.event.id), cor: p.color as string | null })
      return
    }
    if (p.isRecurring) {
      // Ocorrência virtual de uma série: edita via mestre + data da ocorrência.
      setDialog({
        open: true, mode: 'edit',
        occurrence: {
          masterId: p.masterId as number,
          occurrenceStart: p.occurrenceStart as string,
          recurrenceRule: (p.recurrenceRule as string) ?? '',
        },
        initialStart: arg.event.start?.toISOString(),
        initialEnd: (arg.event.end ?? arg.event.start)?.toISOString(),
        initialAllDay: arg.event.allDay,
      })
    } else {
      // Evento único ou override concreto (id numérico próprio).
      setDialog({ open: true, mode: 'edit', eventId: arg.event.id })
    }
  }

  // Persiste arrastar/redimensionar de eventos próprios; reverte no erro.
  const persistMove = (arg: EventDropArg | EventResizeDoneArg) => {
    const { event } = arg
    if (event.extendedProps.type !== 'local' || event.extendedProps.canEdit === false || !event.start) {
      arg.revert()
      return
    }
    const end = event.end ?? event.start
    updateMut.mutate(
      {
        id: event.id,
        payload: { start_time: event.start.toISOString(), end_time: end.toISOString(), all_day: event.allDay },
      },
      { onError: () => arg.revert() },
    )
  }

  return (
    <div className="flex flex-col h-full px-4 sm:px-6 py-5 gap-4">
      <style>{CALENDAR_CSS}</style>

      {/* Cabeçalho */}
      <header className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: 'linear-gradient(135deg, var(--color-brand), var(--color-brand-surface))', color: '#FFFFFF', boxShadow: 'var(--shadow-sm)' }}>
            <CalendarDays size={22} />
          </div>
          <div>
            <h1 className="text-2xl font-bold leading-tight" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Calendário
            </h1>
            <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              Eventos, tarefas e reuniões, diários de obra e feriados num só lugar.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Busca de eventos no servidor (Fatia E): título, descrição ou local. */}
          <div style={{ width: 260 }}>
            <SelectComBusca<EventoAchado>
              recurso="calendar/events/busca/"
              idDe={ev => ev.id}
              rotuloDe={ev => ev.title}
              detalheDe={ev => [
                new Date(ev.start_time).toLocaleDateString('pt-BR'),
                ev.location, ev.calendar_name, ev.recurrence_rule ? 'repete' : null,
              ].filter(Boolean).join(' · ')}
              valor={null}
              aoMudar={id => { if (id != null) void abrirEvento(id) }}
              placeholder="Buscar evento…"
              vazio="Nenhum evento ainda."
              aria-label="Buscar evento"
              style={{ width: '100%', padding: '8px 12px', borderRadius: 10, border: '1.5px solid #e2e8f0', fontSize: '0.85rem', fontFamily: 'var(--font-body)' }}
            />
          </div>
          {/* Seletor de localidade dos feriados (obra → estado → município) */}
          <LocalidadeSelector value={localidade} onChange={setLocalidade} />
          <button
            type="button"
            onClick={() => setDialog({ open: true, mode: 'create' })}
            className="flex items-center gap-1.5 shrink-0 transition-transform hover:-translate-y-px"
            style={novoEventoBtn}
          >
            <Plus size={16} /> Novo evento
          </button>
        </div>
      </header>

      {/* Mensagem ao superuser: quando os feriados foram atualizados */}
      {feriadosStatus && (
        <div className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs w-fit"
          style={{ background: '#f0f9ff', border: '1px solid #bae6fd', color: '#075985', fontFamily: 'var(--font-body)' }}>
          <RefreshCw size={13} />
          {feriadosStatus.atualizado_em
            ? `Feriados atualizados em ${new Date(feriadosStatus.atualizado_em).toLocaleString('pt-BR')} — ${feriadosStatus.total} registros (${feriadosStatus.anos}).`
            : 'Feriados ainda não sincronizados — rode “manage.py sincronizar_feriados”.'}
        </div>
      )}

      <div className="flex flex-col lg:flex-row flex-1 min-h-0 gap-4">
      {/* Agendas (Fatia D): mostrar/ocultar, cor, compartilhar, .ics (Fatia E) */}
      <div className="lg:w-64 shrink-0">
        <AgendasPanel ocultas={ocultas} aoMudarOcultas={setOcultas} />
      </div>

      {/* Card do calendário */}
      <div className="flex flex-col flex-1 min-h-0 min-w-0 rounded-2xl bg-white overflow-hidden"
        style={{ boxShadow: 'var(--shadow-md)', border: '1px solid #e9edf3' }}>

        {/* Legenda em pills */}
        <div className="flex flex-wrap items-center gap-2 px-4 sm:px-5 py-3" style={{ borderBottom: '1px solid #eef1f6' }}>
          <span className="text-[0.7rem] font-bold uppercase tracking-wide mr-1" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
            Legenda
          </span>
          {LEGEND_ITEMS.map(item => (
            <span key={item.label} className="inline-flex items-center gap-1.5 rounded-full pl-1.5 pr-2.5 py-1"
              style={{ background: '#f6f8fb', border: '1px solid #edf1f6' }}>
              <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: item.bg }} />
              <span className="text-[0.7rem] font-medium" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>{item.label}</span>
            </span>
          ))}
        </div>

        {isError && (
          <div className="mx-4 mt-3 px-4 py-2.5 rounded-lg text-sm" style={{ background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030', fontFamily: 'var(--font-body)' }}>
            Não foi possível carregar os eventos agora.
          </div>
        )}

        {/* Calendário */}
        <div className="flex-1 min-h-0 p-3 sm:p-4 sgi-calendar" style={fcTheme}>
          <FullCalendar
            ref={calendarRef}
            plugins={[dayGridPlugin, timeGridPlugin, listPlugin, interactionPlugin]}
            initialView="dayGridMonth"
            locale={ptBrLocale}
            headerToolbar={{
              left: 'prev,next today',
              center: 'title',
              right: 'dayGridMonth,timeGridWeek,timeGridDay,listWeek',
            }}
            buttonText={{ today: 'Hoje', month: 'Mês', week: 'Semana', day: 'Dia', list: 'Agenda' }}
            height="100%"
            nowIndicator
            selectable
            selectMirror
            editable
            dayMaxEvents
            fixedWeekCount={false}
            events={fcEvents}
            datesSet={handleDatesSet}
            select={handleSelect}
            eventClick={handleEventClick}
            eventDrop={persistMove}
            eventResize={persistMove}
          />
        </div>
      </div>

      </div>

      <EventDialog
        open={dialog.open}
        mode={dialog.mode}
        eventId={dialog.eventId}
        occurrence={dialog.occurrence}
        initialStart={dialog.initialStart}
        initialEnd={dialog.initialEnd}
        initialAllDay={dialog.initialAllDay}
        onClose={() => setDialog(CLOSED)}
      />

      <EventInfoDialog info={info} onClose={() => setInfo(null)} />
      <ConviteDialog eventId={convite?.id ?? null} cor={convite?.cor} onClose={() => setConvite(null)} />
    </div>
  )
}

export default CalendarPage
