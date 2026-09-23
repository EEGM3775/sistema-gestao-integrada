import { useEffect, useState } from 'react'
import { Search, X } from 'lucide-react'
import { useEmpreendimentoOptions, useClienteOptions, useFornecedorOptions } from '../../hooks/useEntityOptions'

import { minCalendarioISO, maxCalendarioISO } from '@/utils/dates'

/**
 * Barra de filtro unificada do ERP (docs/modulos/moduloerp.md §5.1).
 *
 * Todo "listão financeiro" (contas a pagar/receber, boletos, lotes de remessa, NF...)
 * compartilha os mesmos eixos — período, obra/empreendimento, cliente,
 * fornecedor, status, busca — em vez de telas de filtro duplicadas. O estado
 * vive fora deste componente (controlado): a página dona sincroniza `value`
 * com a URL para permitir deep-link/voltar/compartilhar.
 */

export interface FilterBarValue {
  data_de?: string
  data_ate?: string
  empreendimento?: number
  cliente?: number
  fornecedor?: number
  status?: string
  search?: string
}

export type FilterBarField = 'periodo' | 'empreendimento' | 'cliente' | 'fornecedor' | 'status' | 'search'

export interface FilterBarStatusOption {
  value: string
  label: string
}

interface FilterBarProps {
  value: FilterBarValue
  onChange: (next: FilterBarValue) => void
  /** Quais eixos exibir — cada tela usa apenas os que fazem sentido para sua entidade. */
  fields: FilterBarField[]
  /** Necessário quando `fields` inclui `'status'` — os valores variam por entidade (ContaPagar, ContaReceber, Boleto...). */
  statusOptions?: FilterBarStatusOption[]
  searchPlaceholder?: string
}

const selectStyle: React.CSSProperties = {
  border: '1.5px solid #e2e8f0', borderRadius: '8px', padding: '8px 12px',
  fontSize: '0.875rem', fontFamily: 'var(--font-body)', color: 'var(--color-text)',
  background: '#FFFFFF', outline: 'none', cursor: 'pointer', minWidth: '170px',
}

const dateStyle: React.CSSProperties = {
  ...selectStyle, cursor: 'text', minWidth: '150px',
}

export function FilterBar({ value, onChange, fields, statusOptions, searchPlaceholder }: FilterBarProps) {
  const has = (f: FilterBarField) => fields.includes(f)

  // Hooks sempre chamados (regra dos hooks) — `enabled` evita buscar listas que esta tela não usa.
  const empreendimentoOptions = useEmpreendimentoOptions(has('empreendimento'))
  const clienteOptions = useClienteOptions(has('cliente'))
  const fornecedorOptions = useFornecedorOptions(has('fornecedor'))

  const set = <K extends keyof FilterBarValue>(key: K, raw: string) => {
    const next = { ...value }
    if (key === 'empreendimento' || key === 'cliente' || key === 'fornecedor') {
      if (raw === '') delete next[key]
      else (next[key] as number) = Number(raw)
    } else if (raw === '') {
      delete next[key]
    } else {
      ;(next[key] as string) = raw
    }
    onChange(next)
  }

  const hasActiveFilters = Object.keys(value).length > 0

  return (
    <div className="flex flex-wrap items-center gap-3 mb-4">
      {has('search') && (
        <SearchField
          value={value.search ?? ''}
          placeholder={searchPlaceholder ?? 'Buscar…'}
          onChange={v => set('search', v)}
        />
      )}

      {has('periodo') && (
        <>
          <input
            type="date" min={minCalendarioISO} max={maxCalendarioISO}
            value={value.data_de ?? ''}
            onChange={e => set('data_de', e.target.value)}
            title="Vencimento de"
            style={dateStyle}
          />
          <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8rem' }}>até</span>
          <input
            type="date" min={minCalendarioISO} max={maxCalendarioISO}
            value={value.data_ate ?? ''}
            onChange={e => set('data_ate', e.target.value)}
            title="Vencimento até"
            style={dateStyle}
          />
        </>
      )}

      {has('empreendimento') && (
        <EntitySelect
          placeholder="Todas as obras"
          value={value.empreendimento}
          onChange={v => set('empreendimento', v)}
          query={empreendimentoOptions}
        />
      )}

      {has('cliente') && (
        <EntitySelect
          placeholder="Todos os clientes"
          value={value.cliente}
          onChange={v => set('cliente', v)}
          query={clienteOptions}
        />
      )}

      {has('fornecedor') && (
        <EntitySelect
          placeholder="Todos os fornecedores"
          value={value.fornecedor}
          onChange={v => set('fornecedor', v)}
          query={fornecedorOptions}
        />
      )}

      {has('status') && statusOptions && (
        <select value={value.status ?? ''} onChange={e => set('status', e.target.value)} style={selectStyle}>
          <option value="">Todos os status</option>
          {statusOptions.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      )}

      {hasActiveFilters && (
        <button
          type="button"
          onClick={() => onChange({})}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm transition-colors duration-150"
          style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', cursor: 'pointer' }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--color-brand)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--color-text-muted)')}
        >
          <X size={14} /> Limpar filtros
        </button>
      )}
    </div>
  )
}

/** Busca com debounce — evita disparar uma requisição por tecla digitada. */
function SearchField({ value, placeholder, onChange }: { value: string; placeholder: string; onChange: (v: string) => void }) {
  const [draft, setDraft] = useState(value)

  useEffect(() => setDraft(value), [value])

  useEffect(() => {
    const id = setTimeout(() => { if (draft !== value) onChange(draft) }, 400)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  return (
    <div className="relative" style={{ minWidth: '220px', flex: '1 1 220px' }}>
      <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-muted)' }} />
      <input
        type="text"
        value={draft}
        onChange={e => setDraft(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-9 pr-3 py-2 rounded-lg text-sm outline-none"
        style={{ border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)', color: 'var(--color-text)', background: '#FFFFFF' }}
        onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
        onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
      />
    </div>
  )
}

function EntitySelect({ value, placeholder, onChange, query }: {
  value?: number
  placeholder: string
  onChange: (v: string) => void
  query: { data?: { id: number; label: string }[]; isLoading: boolean }
}) {
  return (
    <select value={value ?? ''} onChange={e => onChange(e.target.value)} style={selectStyle} disabled={query.isLoading}>
      <option value="">{placeholder}</option>
      {(query.data ?? []).map(opt => (
        <option key={opt.id} value={opt.id}>{opt.label}</option>
      ))}
    </select>
  )
}
