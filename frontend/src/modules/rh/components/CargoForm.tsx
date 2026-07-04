import React, { useState, useEffect } from 'react'
import type { Cargo, CargoFormData } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'

interface Props {
  open: boolean
  onClose: () => void
  onSave: (fd: CargoFormData) => Promise<void>
  initial?: Cargo | null
}

const EMPTY: CargoFormData = { nome_cargo: '', descricao: '', departamento: '' }

const CargoForm: React.FC<Props> = ({ open, onClose, onSave, initial }) => {
  const [form, setForm] = useState<CargoFormData>(EMPTY)
  const [saving, setSaving] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    if (open) {
      setForm(initial
        ? { nome_cargo: initial.nome_cargo, descricao: initial.descricao, departamento: initial.departamento ?? '' }
        : EMPTY
      )
      setFieldErrors({})
    }
  }, [open, initial])

  const set = (k: keyof CargoFormData, v: string) => setForm(prev => ({ ...prev, [k]: v }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.nome_cargo.trim()) { setFieldErrors({ nome_cargo: 'Campo obrigatório.' }); return }
    setSaving(true)
    setFieldErrors({})
    try {
      await onSave(form)
      onClose()
    } catch (err) {
      setFieldErrors(parseApiErrors(err))
    } finally {
      setSaving(false)
    }
  }

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={onClose} />
      <div
        className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-2xl p-6 w-full max-w-md"
        style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}
      >
        <h2 className="text-lg font-bold mb-5" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
          {initial ? 'Editar Cargo' : 'Novo Cargo'}
        </h2>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Field label="Nome do Cargo *" error={fieldErrors.nome_cargo}>
            <input
              value={form.nome_cargo}
              onChange={e => set('nome_cargo', e.target.value)}
              placeholder="Ex: Engenheiro Civil"
              style={inputStyle}
            />
          </Field>

          <Field label="Departamento" error={fieldErrors.departamento}>
            <input
              value={form.departamento}
              onChange={e => set('departamento', e.target.value)}
              placeholder="Ex: Engenharia"
              style={inputStyle}
            />
          </Field>

          <Field label="Descrição" error={fieldErrors.descricao}>
            <textarea
              value={form.descricao}
              onChange={e => set('descricao', e.target.value)}
              rows={3}
              placeholder="Responsabilidades e atribuições..."
              style={{ ...inputStyle, resize: 'vertical' }}
            />
          </Field>

          <FormErrorBanner errors={fieldErrors} />

          <div className="flex justify-end gap-3 mt-2">
            <button type="button" onClick={onClose} style={cancelBtnStyle}>Cancelar</button>
            <button type="submit" disabled={saving} style={{ ...saveBtnStyle, opacity: saving ? 0.7 : 1 }}>
              {saving ? 'Salvando…' : 'Salvar'}
            </button>
          </div>
        </form>
      </div>
    </>
  )
}

const Field: React.FC<{ label: string; error?: string; children: React.ReactNode }> = ({ label, error, children }) => (
  <div className="flex flex-col gap-1">
    <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)',
      textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-body)' }}>
      {label}
    </label>
    {children}
    <FieldError msg={error} />
  </div>
)

const inputStyle: React.CSSProperties = {
  padding: '8px 12px', border: '1.5px solid #e2e8f0', borderRadius: '8px',
  fontSize: '0.875rem', fontFamily: 'var(--font-body)', color: 'var(--color-text)',
  background: '#FFFFFF', outline: 'none', width: '100%',
}

const cancelBtnStyle: React.CSSProperties = {
  padding: '8px 16px', borderRadius: '8px', border: '1.5px solid #e2e8f0',
  background: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)',
  fontSize: '0.875rem', color: 'var(--color-text-muted)',
}

const saveBtnStyle: React.CSSProperties = {
  padding: '8px 20px', borderRadius: '8px', border: 'none',
  background: 'var(--color-brand)', color: '#FFFFFF',
  cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: '0.875rem', fontWeight: 600,
}

export default CargoForm
