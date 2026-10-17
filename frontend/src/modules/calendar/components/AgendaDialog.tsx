import { useEffect, useState } from 'react'
import { X, CalendarRange, Trash2 } from 'lucide-react'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { useApagarAgenda, useSalvarAgenda } from '../hooks/useAgendas'
import type { Agenda, AgendaScope } from '../types'
import { PessoasPicker, type PessoaEscolhida } from './PessoasPicker'
import {
  inputStyle, labelStyle, buttonPrimaryStyle, buttonSecondaryStyle, buttonDangerStyle,
} from '../formStyles'

/** Cores oferecidas — as mesmas famílias da legenda, para a agenda não sumir no grid. */
const CORES = ['#1e40af', '#0e7490', '#15803d', '#b45309', '#7c3aed', '#be123c', '#334155']

const ESCOPOS: { valor: AgendaScope; rotulo: string; ajuda: string }[] = [
  { valor: 'pessoal', rotulo: 'Só eu', ajuda: 'Ninguém mais vê os eventos desta agenda.' },
  { valor: 'equipe', rotulo: 'Equipe', ajuda: 'Você e os membros escolhidos veem e lançam eventos.' },
  { valor: 'empresa', rotulo: 'Empresa', ajuda: 'Todos da empresa veem e lançam eventos.' },
]

interface Props {
  open: boolean
  /** Ausente = nova agenda. */
  agenda?: Agenda | null
  onClose: () => void
}

export function AgendaDialog({ open, agenda, onClose }: Props) {
  const [name, setName] = useState('')
  const [color, setColor] = useState(CORES[0])
  const [scope, setScope] = useState<AgendaScope>('pessoal')
  const [membros, setMembros] = useState<PessoaEscolhida[]>([])
  const [erros, setErros] = useState<FieldErrors>({})
  const [confirmarApagar, setConfirmarApagar] = useState(false)
  const salvar = useSalvarAgenda()
  const apagar = useApagarAgenda()
  const pending = salvar.isPending || apagar.isPending

  useEffect(() => {
    if (!open) return
    setErros({})
    setConfirmarApagar(false)
    setName(agenda?.name ?? '')
    setColor(agenda?.color ?? CORES[0])
    setScope(agenda?.scope ?? 'pessoal')
    setMembros(agenda?.members.map(m => ({ id: m.id, nome: m.nome })) ?? [])
  }, [open, agenda])

  if (!open) return null

  const handleSalvar = () => {
    if (!name.trim()) { setErros({ name: 'Dê um nome à agenda.' }); return }
    salvar.mutate(
      { id: agenda?.id, payload: { name: name.trim(), color, scope, members: scope === 'equipe' ? membros.map(m => m.id) : [] } },
      { onSuccess: onClose, onError: e => setErros(parseApiErrors(e)) },
    )
  }

  const handleApagar = () => {
    if (!agenda) return
    if (!confirmarApagar) { setConfirmarApagar(true); return }
    apagar.mutate(agenda.id, { onSuccess: onClose, onError: e => setErros(parseApiErrors(e)) })
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center px-4">
      <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onClick={() => !pending && onClose()} aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-label={agenda ? 'Editar agenda' : 'Nova agenda'}
        className="relative w-full flex flex-col rounded-xl"
        style={{ maxWidth: 460, maxHeight: '88vh', background: '#FFFFFF', boxShadow: 'var(--shadow-lg)', border: '1.5px solid #e2e8f0' }}>
        <header className="flex items-center justify-between gap-3 px-5 py-4" style={{ borderBottom: '1.5px solid #e2e8f0' }}>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: '#e0e7ff', color: '#1e40af' }}>
              <CalendarRange size={18} />
            </div>
            <h2 className="text-base font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              {agenda ? 'Editar agenda' : 'Nova agenda'}
            </h2>
          </div>
          <button type="button" onClick={() => !pending && onClose()} aria-label="Fechar" className="p-1.5 rounded-lg"
            style={{ color: 'var(--color-text-muted)', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-3.5">
          <FormErrorBanner errors={erros} />
          <div>
            <label htmlFor="ag-nome" style={labelStyle}>Nome</label>
            <input id="ag-nome" style={inputStyle} value={name} autoFocus
              onChange={e => setName(e.target.value)} placeholder="Ex.: Obra Residencial Centro" />
            <FieldError msg={erros.name} />
          </div>

          <div>
            <span style={labelStyle}>Cor</span>
            <div className="flex gap-2" role="radiogroup" aria-label="Cor da agenda">
              {CORES.map(c => (
                <button key={c} type="button" role="radio" aria-checked={color === c} aria-label={c}
                  onClick={() => setColor(c)}
                  className="w-7 h-7 rounded-full"
                  style={{ background: c, cursor: 'pointer', outline: color === c ? '3px solid rgba(10,42,91,0.35)' : 'none', outlineOffset: 2 }} />
              ))}
            </div>
          </div>

          <div>
            <span style={labelStyle}>Quem vê</span>
            <div className="flex flex-col gap-1.5" role="radiogroup" aria-label="Quem vê">
              {ESCOPOS.map(op => (
                <label key={op.valor} className="flex items-start gap-2 cursor-pointer px-3 py-2 rounded-lg"
                  style={{ border: `1.5px solid ${scope === op.valor ? 'var(--color-brand-app)' : '#e2e8f0'}`, fontFamily: 'var(--font-body)' }}>
                  <input type="radio" name="ag-escopo" checked={scope === op.valor} onChange={() => setScope(op.valor)} className="mt-1" />
                  <span>
                    <span className="block text-sm font-semibold" style={{ color: 'var(--color-text)' }}>{op.rotulo}</span>
                    <span className="block text-xs" style={{ color: 'var(--color-text-muted)' }}>{op.ajuda}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>

          {scope === 'equipe' && (
            <div>
              <span style={labelStyle}>Membros</span>
              <PessoasPicker valor={membros} aoMudar={setMembros}
                excluir={agenda ? [agenda.owner] : []} aria-label="Adicionar membro" />
              <FieldError msg={erros.members} />
            </div>
          )}
        </div>

        <footer className="flex items-center justify-between gap-2 px-5 py-3.5" style={{ borderTop: '1.5px solid #e2e8f0', background: '#f8fafc' }}>
          <div>
            {agenda && (
              <button type="button" onClick={handleApagar} disabled={pending}
                style={{ ...buttonDangerStyle, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Trash2 size={15} /> {confirmarApagar ? 'Apagar agenda e eventos?' : 'Apagar'}
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={onClose} disabled={pending} style={buttonSecondaryStyle}>Cancelar</button>
            <button type="button" onClick={handleSalvar} disabled={pending}
              style={{ ...buttonPrimaryStyle, opacity: pending ? 0.6 : 1 }}>
              {pending ? 'Salvando…' : 'Salvar'}
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}
