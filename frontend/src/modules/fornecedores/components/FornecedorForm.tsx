import React, { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import type { Fornecedor, FornecedorFormData } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { maskCPFCNPJ, validateCPFCNPJ } from '@/utils/masks'

interface Props {
  open: boolean
  onClose: () => void
  onSave: (data: FornecedorFormData) => Promise<void>
  initial?: Fornecedor | null
}

// ─── máscaras ─────────────────────────────────────────────────────────────────

function maskPhone(v: string) {
  const d = v.replace(/\D/g, '').slice(0, 11)
  if (d.length <= 10)
    return d.replace(/(\d{0,2})(\d{0,4})(\d{0,4})/, (_, a, b, c) =>
      c ? `(${a}) ${b}-${c}` : b ? `(${a}) ${b}` : a ? `(${a}` : '')
  return d.replace(/(\d{0,2})(\d{0,5})(\d{0,4})/, (_, a, b, c) =>
    c ? `(${a}) ${b}-${c}` : b ? `(${a}) ${b}` : a ? `(${a}` : '')
}

// ─── helpers de form ──────────────────────────────────────────────────────────

const EMPTY: FornecedorFormData = {
  razao_social: '', cnpj: '', contato: '', email: '', emails_adicionais: [], telefone: '',
}

function toForm(f: Fornecedor): FornecedorFormData {
  return {
    razao_social: f.razao_social,
    cnpj: f.cnpj ?? '',
    contato: f.contato,
    email: f.email,
    emails_adicionais: f.emails_adicionais ?? [],
    telefone: f.telefone,
  }
}

// ─── estilos ──────────────────────────────────────────────────────────────────

const inputCls: React.CSSProperties = {
  width: '100%', padding: '8px 12px', borderRadius: '8px',
  border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)',
  fontSize: '0.875rem', color: 'var(--color-text)', background: '#FFFFFF', outline: 'none',
  boxSizing: 'border-box',
}

const labelCls: React.CSSProperties = {
  display: 'block', fontSize: '0.75rem', fontWeight: 600,
  marginBottom: '4px', color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)',
}

const SectionTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p style={{
    fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em',
    textTransform: 'uppercase', color: 'var(--color-brand)',
    fontFamily: 'var(--font-body)', marginBottom: '12px', marginTop: '20px',
  }}>
    {children}
  </p>
)

// ─── componente ───────────────────────────────────────────────────────────────

const FornecedorForm: React.FC<Props> = ({ open, onClose, onSave, initial }) => {
  const [form, setForm]         = useState<FornecedorFormData>(EMPTY)
  const [semDoc, setSemDoc]         = useState(false)
  const [saving, setSaving]         = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    if (!open) return
    const base = initial ? toForm(initial) : EMPTY
    setForm(base)
    setSemDoc(initial ? initial.cnpj === null : false)
    setFieldErrors({})
  }, [initial, open])

  if (!open) return null

  const set = (field: keyof FornecedorFormData, value: string) =>
    setForm(prev => ({ ...prev, [field]: value }))

  const cnpjDigits = typeof form.cnpj === 'string' ? form.cnpj.replace(/\D/g, '') : ''

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!semDoc) {
      const err = validateCPFCNPJ(cnpjDigits)
      if (err) { setFieldErrors({ cnpj: err }); return }
    }
    setSaving(true)
    setFieldErrors({})
    try {
      await onSave({
        ...form,
        cnpj: semDoc ? null : cnpjDigits,
        emails_adicionais: form.emails_adicionais.map(e => e.trim()).filter(Boolean),
      })
      onClose()
    } catch (err: unknown) {
      setFieldErrors(parseApiErrors(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.3)' }} onClick={onClose} />
      <div className="fixed top-0 right-0 h-full z-50 flex flex-col"
        style={{ width: '480px', background: '#FFFFFF', boxShadow: '-4px 0 24px rgba(0,0,0,0.12)', overflow: 'hidden' }}>

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 shrink-0"
          style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: '1rem', color: 'var(--color-brand)' }}>
            {initial ? 'Editar Fornecedor' : 'Novo Fornecedor'}
          </h2>
          <button onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <form id="fornecedor-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4">

          <FormErrorBanner errors={fieldErrors} />

          <SectionTitle>Dados da Empresa</SectionTitle>

          <div className="mb-3">
            <label style={labelCls}>Razão Social *</label>
            <input required style={inputCls} value={form.razao_social}
              onChange={e => set('razao_social', e.target.value)} />
            <FieldError msg={fieldErrors.razao_social} />
          </div>

          {/* CPF / CNPJ */}
          <div className="mb-3">
            <div className="flex items-center justify-between mb-1">
              <label style={{ ...labelCls, marginBottom: 0 }}>
                CPF / CNPJ {!semDoc && '*'}
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer select-none"
                style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                <input
                  type="checkbox"
                  checked={semDoc}
                  onChange={e => {
                    setSemDoc(e.target.checked)
                    if (e.target.checked) {
                      setForm(prev => ({ ...prev, cnpj: '' }))
                      setFieldErrors(prev => ({ ...prev, cnpj: '' }))
                    }
                  }}
                  style={{ width: '14px', height: '14px', accentColor: 'var(--color-brand)', cursor: 'pointer' }}
                />
                Não informar
              </label>
            </div>
            <input
              disabled={semDoc}
              required={!semDoc}
              style={{
                ...inputCls,
                borderColor: fieldErrors.cnpj ? '#ef4444' : '#e2e8f0',
                background: semDoc ? '#f8fafc' : '#FFFFFF',
                color: semDoc ? 'var(--color-text-muted)' : 'var(--color-text)',
              }}
              placeholder={semDoc ? '—' : 'CPF (000.000.000-00) ou CNPJ (00.000.000/0000-00)'}
              maxLength={18}
              value={semDoc ? '' : maskCPFCNPJ(cnpjDigits)}
              onChange={e => {
                setFieldErrors(prev => ({ ...prev, cnpj: '' }))
                set('cnpj', e.target.value.replace(/\D/g, ''))
              }}
              onBlur={() => {
                if (!semDoc) {
                  const err = validateCPFCNPJ(cnpjDigits)
                  setFieldErrors(prev => ({ ...prev, cnpj: err ?? '' }))
                }
              }}
            />
            <FieldError msg={fieldErrors.cnpj} />
          </div>

          <div className="mb-3">
            <label style={labelCls}>Contato (nome da pessoa)</label>
            <input style={inputCls} value={form.contato}
              onChange={e => set('contato', e.target.value)} />
            <FieldError msg={fieldErrors.contato} />
          </div>

          <SectionTitle>Contato</SectionTitle>

          <div className="mb-3">
            <label style={labelCls}>E-mail</label>
            <input type="email" style={inputCls} value={form.email}
              onChange={e => set('email', e.target.value)} />
            <FieldError msg={fieldErrors.email} />
          </div>

          <div className="mb-3">
            <label style={labelCls}>Outros e-mails</label>
            {form.emails_adicionais.map((em, i) => (
              <div key={i} className="flex items-center gap-2 mb-2">
                <input type="email" style={inputCls} value={em}
                  onChange={e => setForm(prev => ({
                    ...prev,
                    emails_adicionais: prev.emails_adicionais.map((x, j) => j === i ? e.target.value : x),
                  }))} />
                <button type="button" aria-label="Remover e-mail"
                  onClick={() => setForm(prev => ({
                    ...prev,
                    emails_adicionais: prev.emails_adicionais.filter((_, j) => j !== i),
                  }))}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                  <X size={16} />
                </button>
              </div>
            ))}
            <button type="button"
              onClick={() => setForm(prev => ({ ...prev, emails_adicionais: [...prev.emails_adicionais, ''] }))}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
              + Adicionar e-mail
            </button>
            <FieldError msg={fieldErrors.emails_adicionais} />
          </div>

          <div className="mb-3">
            <label style={labelCls}>Telefone</label>
            <input style={inputCls} placeholder="(00) 00000-0000" maxLength={15}
              value={maskPhone(form.telefone)}
              onChange={e => set('telefone', e.target.value.replace(/\D/g, ''))} />
            <FieldError msg={fieldErrors.telefone} />
          </div>
        </form>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 shrink-0"
          style={{ borderTop: '1px solid #e2e8f0' }}>
          <button type="button" onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'none', border: '1.5px solid #e2e8f0', cursor: 'pointer',
              color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
            Cancelar
          </button>
          <button form="fornecedor-form" type="submit" disabled={saving}
            className="px-5 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none',
              cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1,
              fontFamily: 'var(--font-body)' }}>
            {saving ? 'Salvando…' : initial ? 'Salvar alterações' : 'Criar fornecedor'}
          </button>
        </div>
      </div>
    </>
  )
}

export default FornecedorForm
