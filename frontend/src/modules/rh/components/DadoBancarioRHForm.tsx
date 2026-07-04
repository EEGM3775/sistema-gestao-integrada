import React, { useState, useEffect } from 'react'
import type { DadoBancarioFuncionario, DadoBancarioFuncionarioFormData } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { maskCPFCNPJ, validateCPFCNPJ } from '@/utils/masks'

interface Props {
  open: boolean
  onClose: () => void
  onSave: (fd: DadoBancarioFuncionarioFormData) => Promise<void>
  initial?: DadoBancarioFuncionario | null
  funcionarioId: number
}

const EMPTY = (fid: number): DadoBancarioFuncionarioFormData => ({
  funcionario: fid, codigo_banco: '', agencia: '', agencia_dv: '', conta: '', conta_dv: '',
  codigo_cedente: '', carteira: '', tipo_conta: '', chave_pix: '',
  titular_nome: '', titular_cpf_cnpj: '', observacoes: '',
})

function toForm(d: DadoBancarioFuncionario): DadoBancarioFuncionarioFormData {
  return {
    funcionario: d.funcionario, codigo_banco: d.codigo_banco, agencia: d.agencia,
    agencia_dv: d.agencia_dv ?? '', conta: d.conta, conta_dv: d.conta_dv ?? '',
    codigo_cedente: d.codigo_cedente ?? '', carteira: d.carteira ?? '',
    tipo_conta: d.tipo_conta, chave_pix: d.chave_pix ?? '',
    titular_nome: d.titular_nome, titular_cpf_cnpj: (d.titular_cpf_cnpj ?? '').replace(/\D/g, ''),
    observacoes: d.observacoes ?? '',
  }
}

const DadoBancarioRHForm: React.FC<Props> = ({ open, onClose, onSave, initial, funcionarioId }) => {
  const [form, setForm] = useState<DadoBancarioFuncionarioFormData>(EMPTY(funcionarioId))
  const [saving, setSaving] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    if (open) { setForm(initial ? toForm(initial) : EMPTY(funcionarioId)); setFieldErrors({}) }
  }, [open, initial, funcionarioId])

  const set = <K extends keyof DadoBancarioFuncionarioFormData>(k: K, v: DadoBancarioFuncionarioFormData[K]) =>
    setForm(prev => ({ ...prev, [k]: v }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.tipo_conta)     { setFieldErrors({ tipo_conta: 'Campo obrigatório.' }); return }
    if (!form.titular_nome)   { setFieldErrors({ titular_nome: 'Campo obrigatório.' }); return }
    if (form.titular_cpf_cnpj) {
      const cpfErr = validateCPFCNPJ(form.titular_cpf_cnpj)
      if (cpfErr) { setFieldErrors({ titular_cpf_cnpj: cpfErr }); return }
    }
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
          {initial ? 'Editar Conta Bancária' : 'Nova Conta Bancária'}
        </h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Row2>
            <Field label="Titular *" error={fieldErrors.titular_nome}>
              <input value={form.titular_nome} onChange={e => set('titular_nome', e.target.value)} style={inp} />
            </Field>
            <Field label="CPF/CNPJ do Titular" error={fieldErrors.titular_cpf_cnpj}>
              <input value={maskCPFCNPJ(form.titular_cpf_cnpj)} placeholder="000.000.000-00"
                maxLength={18}
                onChange={e => { setFieldErrors(prev => ({ ...prev, titular_cpf_cnpj: '' })); set('titular_cpf_cnpj', e.target.value.replace(/\D/g, '')) }}
                onBlur={e => { const err = validateCPFCNPJ(e.target.value.replace(/\D/g, '')); if (err) setFieldErrors(prev => ({ ...prev, titular_cpf_cnpj: err })) }}
                style={inp} />
            </Field>
          </Row2>
          <Row2>
            <Field label="Tipo de Conta *" error={fieldErrors.tipo_conta}>
              <select value={form.tipo_conta} onChange={e => set('tipo_conta', e.target.value as DadoBancarioFuncionarioFormData['tipo_conta'])} style={inp}>
                <option value="">Selecionar…</option>
                <option value="corrente">Corrente</option>
                <option value="poupanca">Poupança</option>
                <option value="salario">Salário</option>
                <option value="investimento">Investimento</option>
                <option value="conta_conjunta">Conjunta</option>
                <option value="conta_empresarial">Empresarial</option>
                <option value="outro">Outro</option>
              </select>
            </Field>
            <Field label="Código do Banco" error={fieldErrors.codigo_banco}>
              <input value={form.codigo_banco} onChange={e => set('codigo_banco', e.target.value)} placeholder="Ex: 001" style={inp} />
            </Field>
          </Row2>
          <Row2>
            <Field label="Agência" error={fieldErrors.agencia}>
              <input value={form.agencia} onChange={e => set('agencia', e.target.value)} style={inp} />
            </Field>
            <Field label="DV Agência" error={fieldErrors.agencia_dv}>
              <input value={form.agencia_dv} onChange={e => set('agencia_dv', e.target.value)} maxLength={1} style={{ ...inp, maxWidth: '80px' }} />
            </Field>
          </Row2>
          <Row2>
            <Field label="Conta" error={fieldErrors.conta}>
              <input value={form.conta} onChange={e => set('conta', e.target.value)} style={inp} />
            </Field>
            <Field label="DV Conta" error={fieldErrors.conta_dv}>
              <input value={form.conta_dv} onChange={e => set('conta_dv', e.target.value)} maxLength={1} style={{ ...inp, maxWidth: '80px' }} />
            </Field>
          </Row2>
          <Field label="Chave PIX" error={fieldErrors.chave_pix}>
            <input value={form.chave_pix} onChange={e => set('chave_pix', e.target.value)} style={inp} />
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

export default DadoBancarioRHForm
