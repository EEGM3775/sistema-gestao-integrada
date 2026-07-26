import React, { useState, useEffect, useRef } from 'react'
import { X, Loader2 } from 'lucide-react'
import type { Empreendimento, EmpreendimentoFormData, StatusEmpreendimento } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { maskCNPJ, validateCNPJ } from '@/utils/masks'
import { minVigenciaISO, maxVigenciaISO, validateISO_Vigencia } from '@/utils/dates'

// ─── Máscaras ────────────────────────────────────────────────────────────────

function maskPhone(v: string) {
  const d = v.replace(/\D/g, '').slice(0, 11)
  if (d.length <= 10)
    return d.replace(/^(\d{2})(\d)/, '($1) $2').replace(/(\d{4})(\d)/, '$1-$2')
  return d.replace(/^(\d{2})(\d)/, '($1) $2').replace(/(\d{5})(\d)/, '$1-$2')
}

// Formata em tempo real: extrai só dígitos, divide por 100, exibe como BRL
// "1" → "0,01"  "123" → "1,23"  "1234567" → "12.345,67"
function maskCurrency(v: string): string {
  const digits = v.replace(/\D/g, '').slice(0, 15)
  if (!digits) return ''
  const num = parseInt(digits, 10)
  return (num / 100).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function currencyToDecimal(v: string): string {
  // '12.345,67' → '12345.67'
  return v.replace(/\./g, '').replace(',', '.')
}

// ─── Constantes ──────────────────────────────────────────────────────────────

const STATUS_OPTIONS: { value: StatusEmpreendimento; label: string }[] = [
  { value: 'planejamento', label: 'Planejamento' },
  { value: 'em_execucao',  label: 'Em Execução'  },
  { value: 'concluido',    label: 'Concluído'    },
  { value: 'cancelado',    label: 'Cancelado'    },
]

const EMPTY: EmpreendimentoFormData = {
  empreendimento: '',
  razao_social: '',
  cnpj: '',
  telefone: '',
  endereco: '',
  cidade: '',
  estado: '',
  data_inicio_prevista: '',
  data_fim_prevista: '',
  orcamento_total: '',
  status_empreendimento: 'planejamento',
  descricao: '',
}

interface Props {
  open: boolean
  onClose: () => void
  onSave: (data: EmpreendimentoFormData) => Promise<void>
  initial?: Empreendimento | null
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

// ─── Componente ──────────────────────────────────────────────────────────────

export const EmpreendimentoForm: React.FC<Props> = ({ open, onClose, onSave, initial }) => {
  const [form, setForm]     = useState<EmpreendimentoFormData>(EMPTY)
  const [saving, setSaving] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  // Controle de fechamento por click fora (sem fechar ao arrastar texto)
  const overlayRef          = useRef<HTMLDivElement>(null)
  const mousedownOnOverlay  = useRef(false)

  useEffect(() => {
    if (!open) return
    if (initial) {
      setForm({
        empreendimento:        initial.empreendimento,
        razao_social:          initial.razao_social,
        cnpj:                  initial.cnpj.replace(/\D/g, ''),
        telefone:              initial.telefone,
        endereco:              initial.endereco,
        cidade:                initial.cidade ?? '',
        estado:                initial.estado ?? '',
        data_inicio_prevista:  initial.data_inicio_prevista ?? '',
        data_fim_prevista:     initial.data_fim_prevista ?? '',
        orcamento_total:       initial.orcamento_total
                                 ? maskCurrency(
                                     // backend retorna '12345.67' → converte para dígitos → mask
                                     String(Math.round(parseFloat(initial.orcamento_total) * 100))
                                   )
                                 : '',
        status_empreendimento: initial.status_empreendimento,
        descricao:             initial.descricao ?? '',
      })
    } else {
      setForm(EMPTY)
    }
    setFieldErrors({})
  }, [initial, open])

  const set = (field: keyof EmpreendimentoFormData, value: string) =>
    setForm(f => ({ ...f, [field]: value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (form.cnpj) {
      const cnpjErr = validateCNPJ(form.cnpj)
      if (cnpjErr) { setFieldErrors({ cnpj: cnpjErr }); return }
    }
    if (form.data_inicio_prevista && form.data_fim_prevista && form.data_fim_prevista < form.data_inicio_prevista) {
      setFieldErrors({ data_fim_prevista: 'Data de término deve ser posterior ao início.' }); return
    }
    setSaving(true)
    setFieldErrors({})
    try {
      const payload: EmpreendimentoFormData = {
        ...form,
        orcamento_total: currencyToDecimal(form.orcamento_total),
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
      onMouseDown={e => {
        // Só fecha se o mousedown começou DIRETAMENTE no overlay (não dentro do painel)
        mousedownOnOverlay.current = e.target === overlayRef.current
      }}
      onClick={() => {
        if (mousedownOnOverlay.current) onClose()
      }}
    >
      <div
        className="relative h-full w-full max-w-lg flex flex-col overflow-y-auto"
        style={{ background: '#FFFFFF', boxShadow: '-4px 0 24px rgba(0,0,0,0.15)' }}
        onMouseDown={e => e.stopPropagation()}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 shrink-0"
             style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 className="text-lg font-bold"
              style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            {initial ? 'Editar Empreendimento' : 'Novo Empreendimento'}
          </h2>
          <button onClick={onClose}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-5 px-6 py-6 flex-1">
          <div>
            <label style={labelStyle}>Nome do empreendimento *</label>
            <input required style={inputStyle} value={form.empreendimento}
              onChange={e => set('empreendimento', e.target.value)}
              placeholder="Ex: Residencial Alfa"
              onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
              onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
            <FieldError msg={fieldErrors.empreendimento} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label style={labelStyle}>Razão social *</label>
              <input required style={inputStyle} value={form.razao_social}
                onChange={e => set('razao_social', e.target.value)}
                placeholder="Nome Ltda."
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
              <FieldError msg={fieldErrors.razao_social} />
            </div>
            <div>
              <label style={labelStyle}>CNPJ *</label>
              <input required style={inputStyle} value={maskCNPJ(form.cnpj)}
                onChange={e => { setFieldErrors(prev => ({ ...prev, cnpj: '' })); set('cnpj', e.target.value.replace(/\D/g, '')) }}
                placeholder="00.000.000/0001-00" maxLength={18}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => {
                  e.currentTarget.style.borderColor = '#e2e8f0'
                  const err = validateCNPJ(e.target.value.replace(/\D/g, ''))
                  if (err) setFieldErrors(prev => ({ ...prev, cnpj: err }))
                }} />
              <FieldError msg={fieldErrors.cnpj} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label style={labelStyle}>Telefone</label>
              <input style={inputStyle} value={form.telefone}
                onChange={e => set('telefone', maskPhone(e.target.value))}
                placeholder="(11) 99999-9999" maxLength={15}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
              <FieldError msg={fieldErrors.telefone} />
            </div>
            <div>
              <label style={labelStyle}>Status</label>
              <select style={{ ...inputStyle, cursor: 'pointer' }}
                      value={form.status_empreendimento}
                      onChange={e => set('status_empreendimento', e.target.value)}>
                {STATUS_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <FieldError msg={fieldErrors.status_empreendimento} />
            </div>
          </div>

          <div>
            <label style={labelStyle}>Endereço</label>
            <input style={inputStyle} value={form.endereco}
              onChange={e => set('endereco', e.target.value)}
              placeholder="Rua, nº, Bairro"
              onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
              onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
            <FieldError msg={fieldErrors.endereco} />
          </div>

          {/* Cidade/UF separados do endereço: é por eles que a carteira de
              clientes filtra e agrupa ("clientes por cidade"), o que texto
              livre não permite. */}
          <div className="grid grid-cols-[1fr_100px] gap-4">
            <div>
              <label style={labelStyle}>Cidade do empreendimento</label>
              <input style={inputStyle} value={form.cidade}
                onChange={e => set('cidade', e.target.value)}
                placeholder="Palhoça"
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
              <FieldError msg={fieldErrors.cidade} />
            </div>
            <div>
              <label style={labelStyle}>UF</label>
              <input style={inputStyle} value={form.estado} maxLength={2}
                onChange={e => set('estado', e.target.value.toUpperCase())}
                placeholder="SC"
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
              <FieldError msg={fieldErrors.estado} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label style={labelStyle}>Início previsto</label>
              <input type="date" style={inputStyle} value={form.data_inicio_prevista}
                min={minVigenciaISO()} max={maxVigenciaISO()}
                onChange={e => { set('data_inicio_prevista', e.target.value); setFieldErrors(p => ({ ...p, data_inicio_prevista: '' })) }}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => { e.currentTarget.style.borderColor = '#e2e8f0'; const err = validateISO_Vigencia(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_inicio_prevista: err })) }} />
              <FieldError msg={fieldErrors.data_inicio_prevista} />
            </div>
            <div>
              <label style={labelStyle}>Fim previsto</label>
              <input type="date" style={inputStyle} value={form.data_fim_prevista}
                min={minVigenciaISO()} max={maxVigenciaISO()}
                onChange={e => { set('data_fim_prevista', e.target.value); setFieldErrors(p => ({ ...p, data_fim_prevista: '' })) }}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => { e.currentTarget.style.borderColor = '#e2e8f0'; const err = validateISO_Vigencia(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_fim_prevista: err })) }} />
              <FieldError msg={fieldErrors.data_fim_prevista} />
            </div>
          </div>

          <div>
            <label style={labelStyle}>Orçamento total</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm select-none"
                    style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                R$
              </span>
              <input
                style={{ ...inputStyle, paddingLeft: '36px' }}
                value={form.orcamento_total}
                onChange={e => set('orcamento_total', maskCurrency(e.target.value))}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                placeholder="0,00"
                inputMode="numeric"
              />
            </div>
            <FieldError msg={fieldErrors.orcamento_total} />
          </div>

          <div>
            <label style={labelStyle}>Descrição</label>
            <textarea rows={4} style={{ ...inputStyle, resize: 'vertical' }}
              value={form.descricao}
              onChange={e => set('descricao', e.target.value)}
              placeholder="Descrição do empreendimento..."
              onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
              onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
            <FieldError msg={fieldErrors.descricao} />
          </div>

          <FormErrorBanner errors={fieldErrors} />

          {/* Footer */}
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

export default EmpreendimentoForm
