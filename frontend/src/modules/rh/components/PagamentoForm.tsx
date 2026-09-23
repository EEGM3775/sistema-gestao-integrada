import React, { useState, useEffect } from 'react'
import type { PagamentoFuncionario, PagamentoFormData } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { validateISO_Pagamento, minCalendarioISO, maxCalendarioISO } from '@/utils/dates'

interface Props {
  open: boolean
  onClose: () => void
  onSave: (fd: PagamentoFormData) => Promise<void>
  initial?: PagamentoFuncionario | null
  funcionarioId: number
}

const EMPTY = (fid: number): PagamentoFormData => ({
  funcionario: fid, data_pagamento: '', salario_base: '0.00',
  descontos: '0.00', adicionais: '0.00', extras: '0.00', bonus: '0.00',
  tipos_descontos: '', tipos_adicionais: '', tipos_extras: '', tipos_bonus: '',
  salario_liquido: '0.00', forma_pagamento: '', parcela: 1,
  referencia_pagamento: '', link_holerite: '', observacoes: '',
})

function toForm(p: PagamentoFuncionario): PagamentoFormData {
  return {
    funcionario: p.funcionario, data_pagamento: p.data_pagamento,
    salario_base: p.salario_base, descontos: p.descontos, adicionais: p.adicionais,
    extras: p.extras, bonus: p.bonus,
    tipos_descontos: p.tipos_descontos ?? '', tipos_adicionais: p.tipos_adicionais ?? '',
    tipos_extras: p.tipos_extras ?? '', tipos_bonus: p.tipos_bonus ?? '',
    salario_liquido: p.salario_liquido, forma_pagamento: p.forma_pagamento,
    parcela: p.parcela, referencia_pagamento: p.referencia_pagamento ?? '',
    link_holerite: p.link_holerite ?? '', observacoes: p.observacoes ?? '',
  }
}

const PagamentoForm: React.FC<Props> = ({ open, onClose, onSave, initial, funcionarioId }) => {
  const [form, setForm] = useState<PagamentoFormData>(EMPTY(funcionarioId))
  const [saving, setSaving] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    if (open) { setForm(initial ? toForm(initial) : EMPTY(funcionarioId)); setFieldErrors({}) }
  }, [open, initial, funcionarioId])

  const set = <K extends keyof PagamentoFormData>(k: K, v: PagamentoFormData[K]) =>
    setForm(prev => ({ ...prev, [k]: v }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.data_pagamento)  { setFieldErrors({ data_pagamento: 'Campo obrigatório.' }); return }
    if (!form.forma_pagamento) { setFieldErrors({ forma_pagamento: 'Campo obrigatório.' }); return }
    setSaving(true); setFieldErrors({})
    try { await onSave(form); onClose() }
    catch (err) { setFieldErrors(parseApiErrors(err)) }
    finally { setSaving(false) }
  }

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.45)' }} onClick={onClose} />
      <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-2xl p-6 w-full max-w-lg overflow-y-auto"
        style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)', maxHeight: '90vh' }}>
        <h2 className="text-lg font-bold mb-5" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
          {initial ? 'Editar Pagamento' : 'Novo Pagamento'}
        </h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Row2>
            <Field label="Data de Pagamento *" error={fieldErrors.data_pagamento}>
              <input type="date" min={minCalendarioISO} max={maxCalendarioISO} value={form.data_pagamento}
                onChange={e => { set('data_pagamento', e.target.value); setFieldErrors(p => ({ ...p, data_pagamento: '' })) }}
                onBlur={e => { const err = validateISO_Pagamento(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_pagamento: err })) }}
                style={inp} />
            </Field>
            <Field label="Forma de Pagamento *" error={fieldErrors.forma_pagamento}>
              <select value={form.forma_pagamento} onChange={e => set('forma_pagamento', e.target.value as PagamentoFormData['forma_pagamento'])} style={inp}>
                <option value="">Selecionar…</option>
                <option value="pix">PIX</option>
                <option value="transferencia">Transferência</option>
                <option value="deposito">Depósito</option>
                <option value="boleto">Boleto</option>
                <option value="dinheiro">Dinheiro</option>
                <option value="cheque">Cheque</option>
                <option value="cartao_credito">Cartão Crédito</option>
                <option value="cartao_debito">Cartão Débito</option>
                <option value="outro">Outro</option>
              </select>
            </Field>
          </Row2>
          <Row2>
            <Field label="Salário Base (R$)" error={fieldErrors.salario_base}>
              <input value={form.salario_base} onChange={e => set('salario_base', e.target.value)} style={inp} />
            </Field>
            <Field label="Descontos (R$)" error={fieldErrors.descontos}>
              <input value={form.descontos} onChange={e => set('descontos', e.target.value)} style={inp} />
            </Field>
          </Row2>
          <Row2>
            <Field label="Adicionais (R$)" error={fieldErrors.adicionais}>
              <input value={form.adicionais} onChange={e => set('adicionais', e.target.value)} style={inp} />
            </Field>
            <Field label="Extras (R$)" error={fieldErrors.extras}>
              <input value={form.extras} onChange={e => set('extras', e.target.value)} style={inp} />
            </Field>
          </Row2>
          <Row2>
            <Field label="Bônus (R$)" error={fieldErrors.bonus}>
              <input value={form.bonus} onChange={e => set('bonus', e.target.value)} style={inp} />
            </Field>
            <Field label="Salário Líquido (R$)" error={fieldErrors.salario_liquido}>
              <input value={form.salario_liquido} onChange={e => set('salario_liquido', e.target.value)} style={inp} />
            </Field>
          </Row2>
          <Row2>
            <Field label="Referência" error={fieldErrors.referencia_pagamento}>
              <input value={form.referencia_pagamento} onChange={e => set('referencia_pagamento', e.target.value)} placeholder="Ex: Maio/2025" style={inp} />
            </Field>
            <Field label="Parcela" error={fieldErrors.parcela}>
              <input type="number" min={1} value={form.parcela} onChange={e => set('parcela', Number(e.target.value))} style={inp} />
            </Field>
          </Row2>
          <Field label="Link do Holerite" error={fieldErrors.link_holerite}>
            <input type="url" value={form.link_holerite} onChange={e => set('link_holerite', e.target.value)} placeholder="https://…" style={inp} />
          </Field>
          <Field label="Observações" error={fieldErrors.observacoes}>
            <textarea value={form.observacoes} onChange={e => set('observacoes', e.target.value)} rows={2} style={{ ...inp, resize: 'vertical' }} />
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

export default PagamentoForm
