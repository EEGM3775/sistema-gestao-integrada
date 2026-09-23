import React, { useState, useEffect, useRef } from 'react'
import { X, Loader2 } from 'lucide-react'
import type { EtapaObra, EtapaObraFormData, StatusObra } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { validateISO_Vigencia, minCalendarioISO, maxCalendarioISO } from '@/utils/dates'

function maskCurrency(v: string): string {
  const digits = v.replace(/\D/g, '').slice(0, 15)
  if (!digits) return ''
  const num = parseInt(digits, 10)
  return (num / 100).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function currencyToDecimal(v: string): string {
  return v.replace(/\./g, '').replace(',', '.')
}

const STATUS_OPTIONS: { value: StatusObra; label: string }[] = [
  { value: 'planejamento', label: 'Planejamento' },
  { value: 'em_execucao',  label: 'Em Execução'  },
  { value: 'concluida',    label: 'Concluída'    },
  { value: 'cancelada',    label: 'Cancelada'    },
]

interface Props {
  open: boolean
  obraId: number
  nextOrdem: number
  onClose: () => void
  onSave: (data: EtapaObraFormData) => Promise<void>
  initial?: EtapaObra | null
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '10px 12px', borderRadius: '8px',
  border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)',
  fontSize: '0.875rem', color: 'var(--color-text)', background: '#FFFFFF', outline: 'none',
}
const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: '0.8rem', fontWeight: 600,
  marginBottom: '4px', fontFamily: 'var(--font-body)', color: 'var(--color-brand)',
}

export const EtapaForm: React.FC<Props> = ({ open, obraId, nextOrdem, onClose, onSave, initial }) => {
  const makeEmpty = (): EtapaObraFormData => ({
    obra: obraId,
    nome_etapa: '',
    ordem: nextOrdem,
    percentual_conclusao: '0',
    status_etapa: 'planejamento',
    descricao: '',
    data_inicio_prevista: '',
    data_fim_prevista: '',
    orcamento_previsto: '',
  })

  const [form, setForm]     = useState<EtapaObraFormData>(makeEmpty)
  const [saving, setSaving] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  const overlayRef         = useRef<HTMLDivElement>(null)
  const mousedownOnOverlay = useRef(false)

  useEffect(() => {
    if (!open) return
    if (initial) {
      setForm({
        obra:                  initial.obra,
        nome_etapa:            initial.nome_etapa,
        ordem:                 initial.ordem,
        percentual_conclusao:  String(parseFloat(initial.percentual_conclusao || '0')),
        status_etapa:          initial.status_etapa,
        descricao:             initial.descricao ?? '',
        data_inicio_prevista:  initial.data_inicio_prevista ?? '',
        data_fim_prevista:     initial.data_fim_prevista ?? '',
        orcamento_previsto:    initial.orcamento_previsto
          ? maskCurrency(String(Math.round(parseFloat(initial.orcamento_previsto) * 100)))
          : '',
      })
    } else {
      setForm(makeEmpty())
    }
    setFieldErrors({})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial, open, obraId, nextOrdem])

  const set = (field: keyof EtapaObraFormData, value: string | number) =>
    setForm(f => ({ ...f, [field]: value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const pct = parseFloat(form.percentual_conclusao)
    if (isNaN(pct) || pct < 0 || pct > 100) {
      setFieldErrors({ percentual_conclusao: 'Percentual deve ser um número entre 0 e 100.' })
      return
    }
    if (form.data_inicio_prevista && form.data_fim_prevista && form.data_fim_prevista < form.data_inicio_prevista) {
      setFieldErrors({ data_fim_prevista: 'Data de término deve ser posterior ao início.' }); return
    }
    setSaving(true)
    setFieldErrors({})
    try {
      const payload: EtapaObraFormData = {
        ...form,
        orcamento_previsto: form.orcamento_previsto ? currencyToDecimal(form.orcamento_previsto) : '',
        percentual_conclusao: String(pct),
      }
      await onSave(payload)
      onClose()
    } catch (err) {
      setFieldErrors(parseApiErrors(err))
    } finally {
      setSaving(false)
    }
  }

  if (!open) return null

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex justify-end"
      style={{ background: 'rgba(0,0,0,0.4)' }}
      onMouseDown={e => { mousedownOnOverlay.current = e.target === overlayRef.current }}
      onClick={() => { if (mousedownOnOverlay.current) onClose() }}
    >
      <div
        className="relative h-full w-full max-w-lg flex flex-col overflow-y-auto"
        style={{ background: '#FFFFFF', boxShadow: '-4px 0 24px rgba(0,0,0,0.15)' }}
        onMouseDown={e => e.stopPropagation()}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 shrink-0"
             style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 className="text-lg font-bold"
              style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            {initial ? 'Editar Etapa' : 'Nova Etapa'}
          </h2>
          <button onClick={onClose}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-5 px-6 py-6 flex-1">
          <div>
            <label style={labelStyle}>Nome da etapa *</label>
            <input required style={inputStyle} value={form.nome_etapa}
              onChange={e => set('nome_etapa', e.target.value)}
              placeholder="Ex: Fundação, Estrutura, Acabamento"
              onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
              onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
            <FieldError msg={fieldErrors.nome_etapa} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label style={labelStyle}>Ordem</label>
              <input type="number" min={1} style={inputStyle} value={form.ordem}
                onChange={e => set('ordem', parseInt(e.target.value, 10) || 1)}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
              <FieldError msg={fieldErrors.ordem} />
            </div>
            <div>
              <label style={labelStyle}>Status</label>
              <select style={{ ...inputStyle, cursor: 'pointer' }}
                      value={form.status_etapa}
                      onChange={e => set('status_etapa', e.target.value)}>
                {STATUS_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <FieldError msg={fieldErrors.status_etapa} />
            </div>
          </div>

          <div>
            <label style={labelStyle}>
              Percentual concluído: <strong>{form.percentual_conclusao}%</strong>
            </label>
            <input
              type="range" min={0} max={100} step={1}
              value={form.percentual_conclusao}
              onChange={e => set('percentual_conclusao', e.target.value)}
              style={{ width: '100%', accentColor: 'var(--color-brand)', cursor: 'pointer' }}
            />
            <div className="flex justify-between text-xs mt-1"
                 style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              <span>0%</span><span>50%</span><span>100%</span>
            </div>
            <FieldError msg={fieldErrors.percentual_conclusao} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label style={labelStyle}>Início previsto</label>
              <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputStyle} value={form.data_inicio_prevista}
                onChange={e => { set('data_inicio_prevista', e.target.value); setFieldErrors(p => ({ ...p, data_inicio_prevista: '' })) }}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => { e.currentTarget.style.borderColor = '#e2e8f0'; const err = validateISO_Vigencia(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_inicio_prevista: err })) }} />
              <FieldError msg={fieldErrors.data_inicio_prevista} />
            </div>
            <div>
              <label style={labelStyle}>Fim previsto</label>
              <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputStyle} value={form.data_fim_prevista}
                onChange={e => { set('data_fim_prevista', e.target.value); setFieldErrors(p => ({ ...p, data_fim_prevista: '' })) }}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => { e.currentTarget.style.borderColor = '#e2e8f0'; const err = validateISO_Vigencia(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_fim_prevista: err })) }} />
              <FieldError msg={fieldErrors.data_fim_prevista} />
            </div>
          </div>

          <div>
            <label style={labelStyle}>Orçamento previsto</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm select-none"
                    style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                R$
              </span>
              <input
                style={{ ...inputStyle, paddingLeft: '36px' }}
                value={form.orcamento_previsto}
                onChange={e => set('orcamento_previsto', maskCurrency(e.target.value))}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                placeholder="0,00"
                inputMode="numeric"
              />
            </div>
            <FieldError msg={fieldErrors.orcamento_previsto} />
          </div>

          <div>
            <label style={labelStyle}>Descrição</label>
            <textarea rows={3} style={{ ...inputStyle, resize: 'vertical' }}
              value={form.descricao}
              onChange={e => set('descricao', e.target.value)}
              placeholder="Descrição da etapa..."
              onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
              onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
            <FieldError msg={fieldErrors.descricao} />
          </div>

          <FormErrorBanner errors={fieldErrors} />

          <div className="flex gap-3 mt-auto pt-4" style={{ borderTop: '1px solid #e2e8f0' }}>
            <button type="button" onClick={onClose}
              className="flex-1 py-2.5 rounded-lg text-sm font-semibold"
              style={{ background: 'transparent', border: '1.5px solid #e2e8f0',
                       color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', cursor: 'pointer' }}>
              Cancelar
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold"
              style={{ background: saving ? 'rgba(10,42,91,0.5)' : 'var(--color-brand)',
                       color: '#FFFFFF', border: 'none',
                       fontFamily: 'var(--font-body)', cursor: saving ? 'not-allowed' : 'pointer' }}>
              {saving ? <><Loader2 size={14} className="animate-spin" />Salvando…</> : 'Salvar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default EtapaForm
