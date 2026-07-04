import React, { useState, useEffect, useRef } from 'react'
import type { FolhaPagamento, FolhaPagamentoFormData } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { minPagamentoISO, maxPagamentoISO, validateISO_Pagamento } from '@/utils/dates'

interface Props {
  open: boolean
  onClose: () => void
  onSave: (fd: FolhaPagamentoFormData, holerite: File | null) => Promise<void>
  initial?: FolhaPagamento | null
  funcionarioId: number
}

const EMPTY = (fid: number): FolhaPagamentoFormData => ({
  funcionario: fid, mes_referencia: '', salario_bruto: '0.00',
  total_descontos: '0.00', total_proventos: '0.00',
  salario_liquido: '0.00', data_pagamento: '',
})

function toForm(f: FolhaPagamento): FolhaPagamentoFormData {
  return {
    funcionario: f.funcionario, mes_referencia: f.mes_referencia,
    salario_bruto: f.salario_bruto, total_descontos: f.total_descontos,
    total_proventos: f.total_proventos, salario_liquido: f.salario_liquido,
    data_pagamento: f.data_pagamento ?? '',
  }
}

const FolhaPagamentoForm: React.FC<Props> = ({ open, onClose, onSave, initial, funcionarioId }) => {
  const [form, setForm]         = useState<FolhaPagamentoFormData>(EMPTY(funcionarioId))
  const [holerite, setHolerite] = useState<File | null>(null)
  const [saving, setSaving]     = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const fileRef                 = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setForm(initial ? toForm(initial) : EMPTY(funcionarioId))
      setHolerite(null)
      setFieldErrors({})
    }
  }, [open, initial, funcionarioId])

  const set = <K extends keyof FolhaPagamentoFormData>(k: K, v: FolhaPagamentoFormData[K]) =>
    setForm(prev => ({ ...prev, [k]: v }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.mes_referencia) { setFieldErrors({ mes_referencia: 'Campo obrigatório.' }); return }
    setSaving(true); setFieldErrors({})
    try { await onSave(form, holerite); onClose() }
    catch (err) { setFieldErrors(parseApiErrors(err)) }
    finally { setSaving(false) }
  }

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.45)' }} onClick={onClose} />
      <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-2xl p-6 w-full max-w-md"
        style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
        <h2 className="text-lg font-bold mb-5" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
          {initial ? 'Editar Folha' : 'Nova Folha de Pagamento'}
        </h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Row2>
            <Field label="Mês de Referência *" error={fieldErrors.mes_referencia}>
              <input type="date" value={form.mes_referencia}
                min={minPagamentoISO()} max={maxPagamentoISO()}
                onChange={e => { set('mes_referencia', e.target.value); setFieldErrors(p => ({ ...p, mes_referencia: '' })) }}
                onBlur={e => { const err = validateISO_Pagamento(e.target.value); if (err) setFieldErrors(p => ({ ...p, mes_referencia: err })) }}
                style={inp} />
            </Field>
            <Field label="Data de Pagamento" error={fieldErrors.data_pagamento}>
              <input type="date" value={form.data_pagamento}
                min={minPagamentoISO()} max={maxPagamentoISO()}
                onChange={e => { set('data_pagamento', e.target.value); setFieldErrors(p => ({ ...p, data_pagamento: '' })) }}
                onBlur={e => { const err = validateISO_Pagamento(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_pagamento: err })) }}
                style={inp} />
            </Field>
          </Row2>
          <Row2>
            <Field label="Salário Bruto (R$)" error={fieldErrors.salario_bruto}>
              <input value={form.salario_bruto} onChange={e => set('salario_bruto', e.target.value)} style={inp} />
            </Field>
            <Field label="Total Descontos (R$)" error={fieldErrors.total_descontos}>
              <input value={form.total_descontos} onChange={e => set('total_descontos', e.target.value)} style={inp} />
            </Field>
          </Row2>
          <Row2>
            <Field label="Total Proventos (R$)" error={fieldErrors.total_proventos}>
              <input value={form.total_proventos} onChange={e => set('total_proventos', e.target.value)} style={inp} />
            </Field>
            <Field label="Salário Líquido (R$)" error={fieldErrors.salario_liquido}>
              <input value={form.salario_liquido} onChange={e => set('salario_liquido', e.target.value)} style={inp} />
            </Field>
          </Row2>

          <Field label="Holerite (PDF / imagem)" error={fieldErrors.holerite}>
            <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png"
              onChange={e => setHolerite(e.target.files?.[0] ?? null)}
              style={{ display: 'none' }} />
            <button type="button" onClick={() => fileRef.current?.click()}
              style={{ ...inp, textAlign: 'left', cursor: 'pointer',
                color: holerite ? 'var(--color-text)' : 'var(--color-text-muted)',
                background: '#f8fafc' }}>
              {holerite ? holerite.name : initial?.holerite ? '(substituir holerite atual)' : 'Escolher arquivo…'}
            </button>
            {initial?.holerite && !holerite && (
              <a href={initial.holerite} target="_blank" rel="noreferrer"
                className="text-xs mt-1 flex items-center gap-1"
                style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                Holerite atual ↗
              </a>
            )}
          </Field>

          <FormErrorBanner errors={fieldErrors} />

          <div className="flex justify-end gap-3 mt-2">
            <button type="button" onClick={onClose} style={cancelBtn}>Cancelar</button>
            <button type="submit" disabled={saving} style={{ ...saveBtn, opacity: saving ? 0.7 : 1 }}>
              {saving ? 'Salvando…' : 'Salvar'}
            </button>
          </div>
        </form>
      </div>
    </>
  )
}

const Row2: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="grid grid-cols-2 gap-3">{children}</div>
)
const Field: React.FC<{ label: string; error?: string; children: React.ReactNode }> = ({ label, error, children }) => (
  <div className="flex flex-col gap-1">
    <label style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--color-text-muted)',
      textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-body)' }}>{label}</label>
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

export default FolhaPagamentoForm
