import React, { useEffect, useRef, useState } from 'react'
import { Search, X, ChevronDown } from 'lucide-react'
import type { EntityOption } from '../types'
import { inputBase } from './ui'

/**
 * Select de entidade com **busca server-side** (padrão Coupa/Ariba/Nimbi: não
 * carrega o catálogo inteiro no cliente — fecha o F2 para o SCM). Funciona hoje
 * e escala: a busca é paginada no backend e o componente só pede 20 por vez.
 */
interface Props {
  value: number | null
  onChange: (value: number | null, option: EntityOption | null) => void
  search: (q: string) => Promise<EntityOption[]>
  resolve?: (id: number) => Promise<EntityOption>
  placeholder?: string
  disabled?: boolean
  /** Rótulo já conhecido do valor pré-selecionado (evita um resolve). */
  initialOption?: EntityOption
}

export const AsyncEntitySelect: React.FC<Props> = ({ value, onChange, search, resolve, placeholder, disabled, initialOption }) => {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [options, setOptions] = useState<EntityOption[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<EntityOption | null>(initialOption ?? null)
  const boxRef = useRef<HTMLDivElement>(null)
  const reqId = useRef(0)

  // Resolve o rótulo de um valor pré-selecionado (edição).
  useEffect(() => {
    if (value == null) { setSelected(null); return }
    if (selected?.value === value) return
    if (initialOption?.value === value) { setSelected(initialOption); return }
    if (resolve) resolve(value).then(setSelected).catch(() => setSelected(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  // Busca com debounce enquanto aberto.
  useEffect(() => {
    if (!open) return
    const id = ++reqId.current
    setLoading(true)
    const t = setTimeout(() => {
      search(q).then(res => { if (id === reqId.current) { setOptions(res); setLoading(false) } })
        .catch(() => { if (id === reqId.current) { setOptions([]); setLoading(false) } })
    }, 220)
    return () => clearTimeout(t)
  }, [q, open, search])

  // Fecha ao clicar fora.
  useEffect(() => {
    const h = (e: MouseEvent) => { if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const pick = (opt: EntityOption) => { setSelected(opt); onChange(opt.value, opt); setOpen(false); setQ('') }
  const clear = () => { setSelected(null); onChange(null, null) }

  return (
    <div ref={boxRef} style={{ position: 'relative' }}>
      {selected && !open ? (
        <div style={{ ...inputBase, display: 'flex', alignItems: 'center', gap: 8, cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.6 : 1 }}
          onClick={() => { if (!disabled) setOpen(true) }}>
          <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {selected.label}
            {selected.hint && <span className="mono" style={{ color: 'var(--ink-3)', fontSize: 11.5, marginLeft: 7 }}>{selected.hint}</span>}
          </span>
          {!disabled && (
            <button type="button" onClick={e => { e.stopPropagation(); clear() }} aria-label="Limpar" style={{ color: 'var(--ink-3)', background: 'none', border: 'none', cursor: 'pointer', display: 'grid', placeItems: 'center' }}>
              <X size={15} />
            </button>
          )}
        </div>
      ) : (
        <div style={{ position: 'relative' }}>
          <Search size={15} style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-3)' }} />
          <input
            autoFocus={open}
            disabled={disabled}
            value={q}
            placeholder={placeholder ?? 'Buscar…'}
            onChange={e => setQ(e.target.value)}
            onFocus={() => setOpen(true)}
            style={{ ...inputBase, paddingLeft: 33, paddingRight: 28 }}
          />
          <ChevronDown size={15} style={{ position: 'absolute', right: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-3)', pointerEvents: 'none' }} />
        </div>
      )}

      {open && (
        <div style={{ position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0, zIndex: 30, background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', boxShadow: 'var(--shadow-lg)', maxHeight: 240, overflowY: 'auto' }}>
          {loading ? (
            <div style={{ padding: '11px 14px', fontSize: 12.5, color: 'var(--ink-3)' }}>Buscando…</div>
          ) : options.length === 0 ? (
            <div style={{ padding: '11px 14px', fontSize: 12.5, color: 'var(--ink-3)' }}>{q ? 'Nenhum resultado.' : 'Digite para buscar.'}</div>
          ) : (
            options.map(opt => (
              <button
                key={opt.value}
                type="button"
                onClick={() => pick(opt)}
                style={{ display: 'flex', width: '100%', alignItems: 'center', gap: 8, padding: '9px 14px', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', fontSize: 13, color: 'var(--ink-2)' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-2)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'none')}
              >
                <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{opt.label}</span>
                {opt.hint && <span className="mono" style={{ color: 'var(--ink-3)', fontSize: 11.5 }}>{opt.hint}</span>}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

export default AsyncEntitySelect
