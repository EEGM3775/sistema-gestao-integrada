import { useRef, useState } from 'react'
import { Download, Pencil, Plus, Upload, Users, Building2, Lock } from 'lucide-react'
import { exportarIcs, type RecorteIcs } from '../api/endpoints/agendas'
import { useAgendas, useImportarIcs } from '../hooks/useAgendas'
import type { Agenda, AgendaScope } from '../types'
import { SOURCE_STYLE } from '../utils'
import { AgendaDialog } from './AgendaDialog'

/** Chave de visibilidade: a agenda pessoal implícita é `'meus'`. */
export type ChaveAgenda = number | 'meus'

const ICONE: Record<AgendaScope, typeof Lock> = { pessoal: Lock, equipe: Users, empresa: Building2 }

interface Props {
  ocultas: ChaveAgenda[]
  aoMudarOcultas: (ocultas: ChaveAgenda[]) => void
}

/**
 * As agendas que a pessoa vê (Fatia D), cada uma com a sua cor, mostrar/ocultar
 * no grid e — para a pessoa levar a agenda para outro calendário ou trazer a de
 * lá — exportar e importar `.ics` (Fatia E).
 */
export function AgendasPanel({ ocultas, aoMudarOcultas }: Props) {
  const { data: agendas = [], isLoading } = useAgendas()
  const [editando, setEditando] = useState<Agenda | null | undefined>(undefined)
  const [importarEm, setImportarEm] = useState<RecorteIcs | null>(null)
  const [aviso, setAviso] = useState<{ tipo: 'ok' | 'erro'; texto: string; erros?: string[] } | null>(null)
  const arquivo = useRef<HTMLInputElement>(null)
  const importar = useImportarIcs()

  const alternar = (chave: ChaveAgenda) =>
    aoMudarOcultas(ocultas.includes(chave) ? ocultas.filter(c => c !== chave) : [...ocultas, chave])

  const pedirArquivo = (recorte: RecorteIcs) => {
    setImportarEm(recorte)
    setAviso(null)
    arquivo.current?.click()
  }

  const aoEscolherArquivo = (f: File | undefined) => {
    if (!f || importarEm == null) return
    importar.mutate({ arquivo: f, recorte: importarEm }, {
      onSuccess: r => setAviso({ tipo: 'ok', texto: `${r.criados} evento(s) importado(s).` }),
      onError: (e: unknown) => {
        const corpo = (e as { response?: { data?: { detail?: string; erros?: string[]; arquivo?: string } } }).response?.data
        setAviso({
          tipo: 'erro',
          texto: corpo?.arquivo ?? corpo?.detail ?? 'Não foi possível importar o arquivo.',
          erros: corpo?.erros,
        })
      },
    })
    if (arquivo.current) arquivo.current.value = ''
  }

  const linha = (chave: ChaveAgenda, nome: string, cor: string, extra: React.ReactNode, Icone?: typeof Lock, sub?: string) => (
    <li key={String(chave)} className="group flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-slate-50">
      <input type="checkbox" checked={!ocultas.includes(chave)} onChange={() => alternar(chave)}
        aria-label={`Mostrar ${nome}`} style={{ accentColor: cor, cursor: 'pointer' }} />
      <span className="inline-block w-2.5 h-2.5 rounded-full shrink-0" style={{ background: cor }} />
      <span className="flex-1 min-w-0">
        <span className="flex items-center gap-1 text-sm truncate" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}>
          {nome} {Icone && <Icone size={11} style={{ color: 'var(--color-text-muted)' }} />}
        </span>
        {sub && <span className="block text-[0.68rem] truncate" style={{ color: 'var(--color-text-muted)' }}>{sub}</span>}
      </span>
      <span className="flex items-center gap-0.5 opacity-60 group-hover:opacity-100">{extra}</span>
    </li>
  )

  const botao = (titulo: string, onClick: () => void, Icone: typeof Lock) => (
    <button type="button" title={titulo} aria-label={titulo} onClick={onClick}
      className="p-1 rounded" style={{ color: 'var(--color-text-muted)', cursor: 'pointer' }}>
      <Icone size={13} />
    </button>
  )

  return (
    <aside className="flex flex-col gap-2 rounded-2xl bg-white p-3"
      style={{ boxShadow: 'var(--shadow-sm)', border: '1px solid #e9edf3', fontFamily: 'var(--font-body)' }}
      aria-label="Agendas">
      <div className="flex items-center justify-between px-1">
        <span className="text-[0.7rem] font-bold uppercase tracking-wide" style={{ color: 'var(--color-text-muted)' }}>Agendas</span>
        <button type="button" onClick={() => setEditando(null)}
          className="flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-lg"
          style={{ color: 'var(--color-brand)', background: '#eef2ff', cursor: 'pointer' }}>
          <Plus size={13} /> Nova agenda
        </button>
      </div>

      <ul className="flex flex-col">
        {linha('meus', 'Meus eventos', SOURCE_STYLE.local.bg, <>
          {botao('Exportar .ics', () => void exportarIcs('meus', 'meus-eventos'), Download)}
          {botao('Importar .ics', () => pedirArquivo('meus'), Upload)}
        </>, Lock)}
        {isLoading && <li className="px-2 py-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>Carregando agendas…</li>}
        {agendas.map(a => linha(a.id, a.name, a.color, <>
          {a.can_manage && botao('Editar agenda', () => setEditando(a), Pencil)}
          {botao('Exportar .ics', () => void exportarIcs(a.id, a.name), Download)}
          {botao('Importar .ics', () => pedirArquivo(a.id), Upload)}
        </>, ICONE[a.scope], a.can_manage ? (a.scope === 'equipe' ? `${a.members.length} membro(s)` : undefined) : `de ${a.owner_name}`))}
      </ul>

      <input ref={arquivo} type="file" accept=".ics,text/calendar" hidden
        onChange={e => aoEscolherArquivo(e.target.files?.[0])} />

      {importar.isPending && <p className="text-xs px-1" style={{ color: 'var(--color-text-muted)' }}>Importando…</p>}
      {aviso && (
        <div role="status" className="text-xs px-2.5 py-2 rounded-lg"
          style={aviso.tipo === 'ok'
            ? { background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#166534' }
            : { background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030' }}>
          {aviso.texto}
          {aviso.erros && (
            <ul className="mt-1 list-disc pl-4 max-h-32 overflow-y-auto">
              {aviso.erros.map(e => <li key={e}>{e}</li>)}
            </ul>
          )}
        </div>
      )}

      <AgendaDialog open={editando !== undefined} agenda={editando ?? null} onClose={() => setEditando(undefined)} />
    </aside>
  )
}
