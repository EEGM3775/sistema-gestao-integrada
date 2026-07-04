import React, { useState, useEffect } from 'react'
import type { DadoMedicoFuncionario, DadoMedicoFormData } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'

interface Props {
  open: boolean
  onClose: () => void
  onSave: (fd: DadoMedicoFormData) => Promise<void>
  initial?: DadoMedicoFuncionario | null
  funcionarioId: number
}

const EMPTY = (fid: number): DadoMedicoFormData => ({
  funcionario: fid,
  numero_cartao_sus: '', tipo_sanguineo: '', alergias: '', medicamentos: '',
  historico_doencas: '', contato_emergencia_nome: '', contato_emergencia_telefone: '',
  observacoes_medicas: '',
})

function toForm(d: DadoMedicoFuncionario): DadoMedicoFormData {
  return {
    funcionario: d.funcionario,
    numero_cartao_sus: d.numero_cartao_sus ?? '',
    tipo_sanguineo: d.tipo_sanguineo ?? '',
    alergias: d.alergias ?? '',
    medicamentos: d.medicamentos ?? '',
    historico_doencas: d.historico_doencas ?? '',
    contato_emergencia_nome: d.contato_emergencia_nome ?? '',
    contato_emergencia_telefone: d.contato_emergencia_telefone ?? '',
    observacoes_medicas: d.observacoes_medicas ?? '',
  }
}

const DadoMedicoForm: React.FC<Props> = ({ open, onClose, onSave, initial, funcionarioId }) => {
  const [form, setForm] = useState<DadoMedicoFormData>(EMPTY(funcionarioId))
  const [saving, setSaving] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    if (open) { setForm(initial ? toForm(initial) : EMPTY(funcionarioId)); setFieldErrors({}) }
  }, [open, initial, funcionarioId])

  const set = <K extends keyof DadoMedicoFormData>(k: K, v: DadoMedicoFormData[K]) =>
    setForm(prev => ({ ...prev, [k]: v }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true); setFieldErrors({})
    try { await onSave(form); onClose() }
    catch (err) { setFieldErrors(parseApiErrors(err)) }
    finally { setSaving(false) }
  }

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.45)' }} onClick={onClose} />
      <aside className="fixed top-0 right-0 h-full z-50 flex flex-col"
        style={{ width: 'min(480px, 100vw)', background: '#FFFFFF', boxShadow: '-4px 0 30px rgba(0,0,0,0.15)' }}>
        <div className="flex items-center justify-between px-6 py-5 shrink-0" style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 className="text-lg font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            Dados de Saúde
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', fontSize: '1.25rem' }}>✕</button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-4">
          <Row2>
            <Field label="Nº Cartão SUS" error={fieldErrors.numero_cartao_sus}>
              <input value={form.numero_cartao_sus} onChange={e => set('numero_cartao_sus', e.target.value)} style={inp} />
            </Field>
            <Field label="Tipo Sanguíneo" error={fieldErrors.tipo_sanguineo}>
              <input value={form.tipo_sanguineo} onChange={e => set('tipo_sanguineo', e.target.value)} placeholder="Ex: O+" style={inp} />
            </Field>
          </Row2>

          <Field label="Alergias" error={fieldErrors.alergias}>
            <textarea value={form.alergias} onChange={e => set('alergias', e.target.value)} rows={2} style={{ ...inp, resize: 'vertical' }} />
          </Field>

          <Field label="Medicamentos em Uso" error={fieldErrors.medicamentos}>
            <textarea value={form.medicamentos} onChange={e => set('medicamentos', e.target.value)} rows={2} style={{ ...inp, resize: 'vertical' }} />
          </Field>

          <Field label="Histórico de Doenças" error={fieldErrors.historico_doencas}>
            <textarea value={form.historico_doencas} onChange={e => set('historico_doencas', e.target.value)} rows={2} style={{ ...inp, resize: 'vertical' }} />
          </Field>

          <p className="text-xs font-bold uppercase tracking-widest mt-1"
            style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
            Contato de Emergência
          </p>
          <Row2>
            <Field label="Nome" error={fieldErrors.contato_emergencia_nome}>
              <input value={form.contato_emergencia_nome} onChange={e => set('contato_emergencia_nome', e.target.value)} style={inp} />
            </Field>
            <Field label="Telefone" error={fieldErrors.contato_emergencia_telefone}>
              <input value={form.contato_emergencia_telefone} onChange={e => set('contato_emergencia_telefone', e.target.value)} style={inp} />
            </Field>
          </Row2>

          <Field label="Observações Médicas" error={fieldErrors.observacoes_medicas}>
            <textarea value={form.observacoes_medicas} onChange={e => set('observacoes_medicas', e.target.value)} rows={2} style={{ ...inp, resize: 'vertical' }} />
          </Field>

          <FormErrorBanner errors={fieldErrors} />
        </form>

        <div className="shrink-0 flex justify-end gap-3 px-6 py-4" style={{ borderTop: '1px solid #e2e8f0' }}>
          <button type="button" onClick={onClose} style={cancelBtn}>Cancelar</button>
          <button onClick={handleSubmit} disabled={saving} style={{ ...saveBtn, opacity: saving ? 0.7 : 1 }}>
            {saving ? 'Salvando…' : 'Salvar Dados de Saúde'}
          </button>
        </div>
      </aside>
    </>
  )
}

const Row2: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="grid grid-cols-2 gap-3">{children}</div>
)

const Field: React.FC<{ label: string; error?: string; children: React.ReactNode }> = ({ label, error, children }) => (
  <div className="flex flex-col gap-1">
    <label style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--color-text-muted)',
      textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-body)' }}>
      {label}
    </label>
    {children}
    <FieldError msg={error} />
  </div>
)

const inp: React.CSSProperties = {
  padding: '7px 10px', border: '1.5px solid #e2e8f0', borderRadius: '7px',
  fontSize: '0.875rem', fontFamily: 'var(--font-body)', color: 'var(--color-text)',
  background: '#FFFFFF', outline: 'none', width: '100%',
}
const cancelBtn: React.CSSProperties = {
  padding: '8px 16px', borderRadius: '8px', border: '1.5px solid #e2e8f0',
  background: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)',
  fontSize: '0.875rem', color: 'var(--color-text-muted)',
}
const saveBtn: React.CSSProperties = {
  padding: '8px 20px', borderRadius: '8px', border: 'none',
  background: 'var(--color-brand)', color: '#FFFFFF',
  cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: '0.875rem', fontWeight: 600,
}

export default DadoMedicoForm
