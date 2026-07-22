import React from 'react'
import { X, Search, Inbox } from 'lucide-react'
import { Card, Pill } from '@/components/malha'
import type { PillKind } from '@/components/malha'
import { FieldError } from '@/utils/formErrors'
import type { Estado } from '../lib'

// Kit de UI Malha do SCM (docs/identidade-visual.md). Primeiro módulo nascido
// sobre a fundação; serve de referência para os próximos. Estilo por tokens
// (acompanha claro/escuro), tipografia Archivo/Inter/JetBrains, um acento por tela.

// ─── Cabeçalho de página / módulo (§9 cabeçalho de módulo) ────────────────────

export const PageHeader: React.FC<{
  icon?: React.ReactNode
  title: string
  subtitle?: React.ReactNode
  actions?: React.ReactNode
  backTo?: React.ReactNode
}> = ({ icon, title, subtitle, actions, backTo }) => (
  <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 22 }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 13, minWidth: 0 }}>
      {icon && (
        <div style={{ width: 42, height: 42, borderRadius: 'var(--r-md)', flex: 'none', display: 'grid', placeItems: 'center', background: 'var(--accent-soft)', color: 'var(--accent-ink)' }}>
          {icon}
        </div>
      )}
      <div style={{ minWidth: 0 }}>
        {backTo}
        <h1 style={{ fontFamily: 'var(--display)', fontSize: 21, fontWeight: 750, color: 'var(--ink)', letterSpacing: '-0.02em', lineHeight: 1.15 }}>{title}</h1>
        {subtitle && <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 2 }}>{subtitle}</div>}
      </div>
    </div>
    {actions && <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>{actions}</div>}
  </div>
)

// ─── Botões ───────────────────────────────────────────────────────────────────

type BtnVariant = 'primary' | 'brand' | 'ghost' | 'danger' | 'subtle'
const BTN: Record<BtnVariant, React.CSSProperties> = {
  primary: { background: 'var(--accent)', color: '#1A1204', border: '1px solid transparent' },
  brand: { background: 'var(--brand)', color: 'var(--brand-ink)', border: '1px solid transparent' },
  ghost: { background: 'transparent', color: 'var(--ink-2)', border: '1px solid var(--line)' },
  danger: { background: 'var(--danger-soft)', color: 'var(--danger-ink)', border: '1px solid transparent' },
  subtle: { background: 'var(--surface-2)', color: 'var(--ink-2)', border: '1px solid var(--line)' },
}

export const Btn: React.FC<
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: 'sm' | 'md' }
> = ({ variant = 'ghost', size = 'md', style, children, disabled, ...rest }) => (
  <button
    disabled={disabled}
    style={{
      display: 'inline-flex', alignItems: 'center', gap: 7, whiteSpace: 'nowrap',
      fontFamily: 'var(--sans)', fontWeight: 600,
      fontSize: size === 'sm' ? 12.5 : 13.5,
      padding: size === 'sm' ? '5px 11px' : '8px 15px',
      borderRadius: 'var(--r-sm)',
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.5 : 1,
      transition: 'filter .14s, background .14s',
      ...BTN[variant], ...style,
    }}
    onMouseEnter={e => { if (!disabled) e.currentTarget.style.filter = 'brightness(0.96)' }}
    onMouseLeave={e => { e.currentTarget.style.filter = 'none' }}
    {...rest}
  >
    {children}
  </button>
)

// ─── Barra de ferramentas (busca + filtros) ───────────────────────────────────

export const Toolbar: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap', alignItems: 'center', marginBottom: 16 }}>{children}</div>
)

export const SearchInput: React.FC<{ value: string; onChange: (v: string) => void; placeholder?: string }> = ({ value, onChange, placeholder }) => (
  <div style={{ position: 'relative', flex: '1 1 240px', minWidth: 200 }}>
    <Search size={15} style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-3)' }} />
    <input
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder ?? 'Buscar…'}
      style={{ ...inputBase, paddingLeft: 33 }}
    />
  </div>
)

export const FilterSelect: React.FC<{
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  allLabel?: string
}> = ({ value, onChange, options, allLabel }) => (
  <select value={value} onChange={e => onChange(e.target.value)} style={{ ...inputBase, width: 'auto', minWidth: 150, cursor: 'pointer' }}>
    {allLabel !== undefined && <option value="">{allLabel}</option>}
    {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
  </select>
)

// ─── Tabela genérica (colunas como réguas — §6) ───────────────────────────────

export interface Column<T> {
  key: string
  header: string
  render: (row: T) => React.ReactNode
  align?: 'left' | 'right'
  width?: number | string
}

interface DataTableProps<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => React.Key
  onRowClick?: (row: T) => void
  loading?: boolean
  emptyLabel?: string
}

export function DataTable<T>({ columns, rows, rowKey, onRowClick, loading, emptyLabel }: DataTableProps<T>) {
  if (loading) return <Card style={{ display: 'grid', placeItems: 'center', padding: 48 }}><Spinner /></Card>
  if (rows.length === 0) return <EmptyState label={emptyLabel ?? 'Nada por aqui ainda.'} />
  return (
    <Card pad={false} style={{ overflow: 'hidden' }}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: 'var(--surface-2)', borderBottom: '1px solid var(--line)' }}>
              {columns.map(c => (
                <th key={c.key} style={{ textAlign: c.align ?? 'left', padding: '10px 16px', width: c.width, fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700, whiteSpace: 'nowrap' }}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                style={{ borderBottom: i < rows.length - 1 ? '1px solid var(--line-2)' : 'none', cursor: onRowClick ? 'pointer' : 'default' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-2)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                {columns.map(c => (
                  <td key={c.key} style={{ textAlign: c.align ?? 'left', padding: '11px 16px', fontSize: 13, color: 'var(--ink-2)', verticalAlign: 'middle' }}>
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export const EmptyState: React.FC<{ label: string; icon?: React.ReactNode }> = ({ label, icon }) => (
  <Card style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, padding: 44, color: 'var(--ink-3)' }}>
    <span style={{ color: 'var(--ink-3)', opacity: 0.7 }}>{icon ?? <Inbox size={34} />}</span>
    <span style={{ fontSize: 13 }}>{label}</span>
  </Card>
)

export const Spinner: React.FC = () => (
  <span className="animate-spin" style={{ width: 26, height: 26, borderRadius: 999, border: '2.5px solid var(--line)', borderTopColor: 'var(--accent)', display: 'inline-block' }} />
)

// ─── Overlays: Drawer (formulários) e Modal (confirmação/detalhe) ─────────────

const Backdrop: React.FC<{ onClose: () => void; children: React.ReactNode; align: 'right' | 'center' }> = ({ onClose, children, align }) => (
  <div
    onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
    style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(6,14,26,0.5)', backdropFilter: 'blur(2px)', display: 'flex', justifyContent: align === 'right' ? 'flex-end' : 'center', alignItems: align === 'right' ? 'stretch' : 'flex-start', padding: align === 'center' ? '6vh 16px' : 0 }}
  >
    {children}
  </div>
)

export const Drawer: React.FC<{
  title: string
  onClose: () => void
  children: React.ReactNode
  footer?: React.ReactNode
  width?: number
}> = ({ title, onClose, children, footer, width = 460 }) => (
  <Backdrop onClose={onClose} align="right">
    <div style={{ width: '100%', maxWidth: width, background: 'var(--ground)', borderLeft: '1px solid var(--line)', display: 'flex', flexDirection: 'column', boxShadow: 'var(--shadow-lg)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid var(--line)', background: 'var(--surface)' }}>
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 16, fontWeight: 700, color: 'var(--ink)' }}>{title}</h2>
        <button onClick={onClose} aria-label="Fechar" style={{ color: 'var(--ink-3)', padding: 4, borderRadius: 6, cursor: 'pointer', background: 'none', border: 'none' }}>
          <X size={18} />
        </button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>{children}</div>
      {footer && <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 9, padding: '14px 20px', borderTop: '1px solid var(--line)', background: 'var(--surface)' }}>{footer}</div>}
    </div>
  </Backdrop>
)

export const Modal: React.FC<{
  title: string
  onClose: () => void
  children: React.ReactNode
  footer?: React.ReactNode
  width?: number
}> = ({ title, onClose, children, footer, width = 460 }) => (
  <Backdrop onClose={onClose} align="center">
    <div style={{ width: '100%', maxWidth: width, background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', boxShadow: 'var(--shadow-lg)', display: 'flex', flexDirection: 'column', maxHeight: '88vh' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '15px 20px', borderBottom: '1px solid var(--line)' }}>
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 16, fontWeight: 700, color: 'var(--ink)' }}>{title}</h2>
        <button onClick={onClose} aria-label="Fechar" style={{ color: 'var(--ink-3)', padding: 4, borderRadius: 6, cursor: 'pointer', background: 'none', border: 'none' }}>
          <X size={18} />
        </button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>{children}</div>
      {footer && <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 9, padding: '14px 20px', borderTop: '1px solid var(--line)' }}>{footer}</div>}
    </div>
  </Backdrop>
)

// ─── Campos de formulário (rótulo caps acima do valor — §6) ───────────────────

export const inputBase: React.CSSProperties = {
  width: '100%', padding: '8px 11px', fontSize: 13.5, fontFamily: 'var(--sans)',
  color: 'var(--ink)', background: 'var(--surface-2)', border: '1px solid var(--line)',
  borderRadius: 'var(--r-sm)', outline: 'none',
}
const inputMono: React.CSSProperties = { ...inputBase, fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' as const }

export const Field: React.FC<{ label: string; hint?: string; error?: string; required?: boolean; children: React.ReactNode }> = ({ label, hint, error, required, children }) => (
  <label style={{ display: 'block', marginBottom: 14 }}>
    <span style={{ display: 'block', fontSize: 10.5, letterSpacing: '0.09em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700, marginBottom: 5 }}>
      {label}{required && <span style={{ color: 'var(--danger)' }}> *</span>}
    </span>
    {children}
    {hint && !error && <span style={{ display: 'block', fontSize: 11, color: 'var(--ink-3)', marginTop: 4 }}>{hint}</span>}
    <FieldError msg={error} />
  </label>
)

export const TextInput: React.FC<React.InputHTMLAttributes<HTMLInputElement>> = ({ style, ...rest }) => (
  <input style={{ ...inputBase, ...style }} {...rest} />
)

export const TextArea: React.FC<React.TextareaHTMLAttributes<HTMLTextAreaElement>> = ({ style, ...rest }) => (
  <textarea rows={3} style={{ ...inputBase, resize: 'vertical', ...style }} {...rest} />
)

/** Entrada numérica (mono tabular). `decimals` controla o step; valor é string. */
export const NumInput: React.FC<
  { value: string; onChange: (v: string) => void; placeholder?: string; step?: string; min?: number } & { disabled?: boolean }
> = ({ value, onChange, placeholder, step = 'any', min, disabled }) => (
  <input
    type="number" inputMode="decimal" step={step} min={min} disabled={disabled}
    value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
    style={inputMono}
  />
)

export const NativeSelect: React.FC<
  { value: string; onChange: (v: string) => void; children: React.ReactNode } & { disabled?: boolean }
> = ({ value, onChange, children, disabled }) => (
  <select value={value} disabled={disabled} onChange={e => onChange(e.target.value)} style={{ ...inputBase, cursor: 'pointer' }}>
    {children}
  </select>
)

export const Checkbox: React.FC<{ checked: boolean; onChange: (v: boolean) => void; label: string }> = ({ checked, onChange, label }) => (
  <label style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 14, cursor: 'pointer', fontSize: 13, color: 'var(--ink-2)' }}>
    <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} style={{ width: 16, height: 16, accentColor: 'var(--accent)' }} />
    {label}
  </label>
)

// ─── Pílula de estado a partir do mapa de lib.ts ──────────────────────────────

export const EstadoPill: React.FC<{ estado: Estado }> = ({ estado }) => (
  <Pill kind={estado.kind} pulse={estado.pulse}>{estado.label}</Pill>
)

export const TagPill: React.FC<{ kind?: PillKind; children: React.ReactNode }> = ({ kind = 'slate', children }) => (
  <Pill kind={kind}>{children}</Pill>
)

// ─── Paginação server-side ────────────────────────────────────────────────────

export const Pager: React.FC<{ page: number; pageSize: number; total: number; onPage: (p: number) => void }> = ({ page, pageSize, total, onPage }) => {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (total <= pageSize) return null
  const de = (page - 1) * pageSize + 1
  const ate = Math.min(page * pageSize, total)
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginTop: 14, fontSize: 12.5, color: 'var(--ink-3)' }}>
      <span className="mono">{de}–{ate} de {total}</span>
      <div style={{ display: 'flex', gap: 7 }}>
        <Btn size="sm" variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>Anterior</Btn>
        <Btn size="sm" variant="ghost" disabled={page >= pages} onClick={() => onPage(page + 1)}>Próxima</Btn>
      </div>
    </div>
  )
}
