import React, { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import type { DadoBancarioCliente, DadoBancarioClienteFormData } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { maskCPFCNPJ, validateCPFCNPJ } from '@/utils/masks'

interface Props {
  open: boolean
  clienteId: number
  onClose: () => void
  onSave: (data: DadoBancarioClienteFormData) => Promise<void>
  initial?: DadoBancarioCliente | null
}

const TIPO_CONTA_OPTIONS = [
  { value: 'corrente',     label: 'Conta Corrente' },
  { value: 'poupanca',     label: 'Conta Poupança' },
  { value: 'investimento', label: 'Conta de Investimento' },
  { value: 'salario',      label: 'Conta Salário' },
  { value: 'outros',       label: 'Outros' },
]

const EMPTY = (clienteId: number): DadoBancarioClienteFormData => ({
  cliente: clienteId, codigo_banco: '', agencia: '', agencia_dv: '',
  conta: '', conta_dv: '', tipo_conta: 'corrente', titular_nome: '',
  titular_cpf_cnpj: '', chave_pix: '', codigo_cedente: '', carteira: '', observacoes: '',
})

const inputCls: React.CSSProperties = {
  width: '100%', padding: '8px 12px', borderRadius: '8px',
  border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)',
  fontSize: '0.875rem', color: 'var(--color-text)', background: '#FFFFFF',
  outline: 'none', boxSizing: 'border-box',
}
const labelCls: React.CSSProperties = {
  display: 'block', fontSize: '0.75rem', fontWeight: 600,
  marginBottom: '4px', color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)',
}

const DadoBancarioForm: React.FC<Props> = ({ open, clienteId, onClose, onSave, initial }) => {
  const [form, setForm]         = useState<DadoBancarioClienteFormData>(EMPTY(clienteId))
  const [saving, setSaving]           = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    if (initial) {
      setForm({
        cliente: clienteId, codigo_banco: initial.codigo_banco, agencia: initial.agencia,
        agencia_dv: initial.agencia_dv ?? '', conta: initial.conta, conta_dv: initial.conta_dv ?? '',
        tipo_conta: initial.tipo_conta, titular_nome: initial.titular_nome,
        titular_cpf_cnpj: initial.titular_cpf_cnpj, chave_pix: initial.chave_pix ?? '',
        codigo_cedente: initial.codigo_cedente, carteira: initial.carteira,
        observacoes: initial.observacoes ?? '',
      })
    } else {
      setForm(EMPTY(clienteId))
    }
    setFieldErrors({})
  }, [open, clienteId, initial])

  if (!open) return null

  const set = (field: keyof DadoBancarioClienteFormData, value: string) =>
    setForm(prev => ({ ...prev, [field]: value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const cpfVal = validateCPFCNPJ(form.titular_cpf_cnpj)
    if (cpfVal) { setFieldErrors({ titular_cpf_cnpj: cpfVal }); return }
    setSaving(true)
    setFieldErrors({})
    try {
      await onSave({ ...form, cliente: clienteId })
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
        style={{ width: '440px', background: '#FFFFFF', boxShadow: '-4px 0 24px rgba(0,0,0,0.12)', overflow: 'hidden' }}>

        <div className="flex items-center justify-between px-6 py-4 shrink-0"
          style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: '1rem', color: 'var(--color-brand)' }}>
            {initial ? 'Editar Dado Bancário' : 'Novo Dado Bancário'}
          </h2>
          <button onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        <form id="banco-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-3">
          <FormErrorBanner errors={fieldErrors} />

          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-1">
              <label style={labelCls}>Código banco *</label>
              <input required style={inputCls} value={form.codigo_banco} placeholder="001"
                onChange={e => set('codigo_banco', e.target.value)} />
              <FieldError msg={fieldErrors.codigo_banco} />
            </div>
            <div>
              <label style={labelCls}>Tipo de conta *</label>
              <select required style={inputCls} value={form.tipo_conta}
                onChange={e => set('tipo_conta', e.target.value)}>
                {TIPO_CONTA_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <FieldError msg={fieldErrors.tipo_conta} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label style={labelCls}>Agência *</label>
              <input required style={inputCls} value={form.agencia}
                onChange={e => set('agencia', e.target.value)} />
              <FieldError msg={fieldErrors.agencia} />
            </div>
            <div>
              <label style={labelCls}>Dígito</label>
              <input style={inputCls} value={form.agencia_dv} maxLength={1}
                onChange={e => set('agencia_dv', e.target.value)} />
              <FieldError msg={fieldErrors.agencia_dv} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label style={labelCls}>Conta *</label>
              <input required style={inputCls} value={form.conta}
                onChange={e => set('conta', e.target.value)} />
              <FieldError msg={fieldErrors.conta} />
            </div>
            <div>
              <label style={labelCls}>Dígito</label>
              <input style={inputCls} value={form.conta_dv} maxLength={1}
                onChange={e => set('conta_dv', e.target.value)} />
              <FieldError msg={fieldErrors.conta_dv} />
            </div>
          </div>

          <div>
            <label style={labelCls}>Nome do titular *</label>
            <input required style={inputCls} value={form.titular_nome}
              onChange={e => set('titular_nome', e.target.value)} />
            <FieldError msg={fieldErrors.titular_nome} />
          </div>

          <div>
            <label style={labelCls}>CPF/CNPJ do titular *</label>
            <input required style={{ ...inputCls, borderColor: fieldErrors.titular_cpf_cnpj ? '#ef4444' : '#e2e8f0' }}
              placeholder="000.000.000-00" maxLength={18}
              value={maskCPFCNPJ(form.titular_cpf_cnpj)}
              onChange={e => {
                setFieldErrors(prev => ({ ...prev, titular_cpf_cnpj: '' }))
                set('titular_cpf_cnpj', e.target.value.replace(/\D/g, ''))
              }}
              onBlur={() => {
                const err = validateCPFCNPJ(form.titular_cpf_cnpj)
                setFieldErrors(prev => ({ ...prev, titular_cpf_cnpj: err ?? '' }))
              }} />
            <FieldError msg={fieldErrors.titular_cpf_cnpj} />
          </div>

          <div>
            <label style={labelCls}>Chave PIX</label>
            <input style={inputCls} value={form.chave_pix}
              onChange={e => set('chave_pix', e.target.value)} />
            <FieldError msg={fieldErrors.chave_pix} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={labelCls}>Código cedente</label>
              <input style={inputCls} value={form.codigo_cedente}
                onChange={e => set('codigo_cedente', e.target.value)} />
              <FieldError msg={fieldErrors.codigo_cedente} />
            </div>
            <div>
              <label style={labelCls}>Carteira</label>
              <input style={inputCls} value={form.carteira}
                onChange={e => set('carteira', e.target.value)} />
              <FieldError msg={fieldErrors.carteira} />
            </div>
          </div>

          <div>
            <label style={labelCls}>Observações</label>
            <textarea style={{ ...inputCls, minHeight: '60px', resize: 'vertical' }}
              value={form.observacoes}
              onChange={e => set('observacoes', e.target.value)} />
            <FieldError msg={fieldErrors.observacoes} />
          </div>
        </form>

        <div className="flex items-center justify-end gap-3 px-6 py-4 shrink-0"
          style={{ borderTop: '1px solid #e2e8f0' }}>
          <button type="button" onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'none', border: '1.5px solid #e2e8f0', cursor: 'pointer',
              color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
            Cancelar
          </button>
          <button form="banco-form" type="submit" disabled={saving}
            className="px-5 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none',
              cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1,
              fontFamily: 'var(--font-body)' }}>
            {saving ? 'Salvando…' : initial ? 'Salvar alterações' : 'Adicionar'}
          </button>
        </div>
      </div>
    </>
  )
}

export default DadoBancarioForm
