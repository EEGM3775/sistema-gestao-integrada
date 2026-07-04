import React, { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import type { DadoBancarioFornecedor, DadoBancarioFornecedorFormData, TipoContaFornecedor } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'

interface Props {
  open: boolean
  fornecedorId: number
  onClose: () => void
  onSave: (data: DadoBancarioFornecedorFormData) => Promise<void>
  initial?: DadoBancarioFornecedor | null
}

const TIPO_CONTA_OPTIONS: { value: TipoContaFornecedor; label: string }[] = [
  { value: 'corrente', label: 'Conta Corrente' },
  { value: 'poupanca', label: 'Conta Poupança' },
  { value: 'outro',    label: 'Outro' },
]

const EMPTY = (fornecedorId: number): DadoBancarioFornecedorFormData => ({
  fornecedor: fornecedorId,
  codigo_banco: '', agencia: '', agencia_dv: '', conta: '', conta_dv: '',
  codigo_cedente: '', carteira: '', chave_pix: '', tipo_conta: '', observacoes: '',
})

function toForm(db: DadoBancarioFornecedor, fornecedorId: number): DadoBancarioFornecedorFormData {
  return {
    fornecedor: fornecedorId,
    codigo_banco: db.codigo_banco,
    agencia: db.agencia,
    agencia_dv: db.agencia_dv ?? '',
    conta: db.conta,
    conta_dv: db.conta_dv ?? '',
    codigo_cedente: db.codigo_cedente ?? '',
    carteira: db.carteira ?? '',
    chave_pix: db.chave_pix ?? '',
    tipo_conta: db.tipo_conta,
    observacoes: db.observacoes ?? '',
  }
}

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

const DadoBancarioFornecedorForm: React.FC<Props> = ({ open, fornecedorId, onClose, onSave, initial }) => {
  const [form, setForm]     = useState<DadoBancarioFornecedorFormData>(EMPTY(fornecedorId))
  const [saving, setSaving]           = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    setForm(initial ? toForm(initial, fornecedorId) : EMPTY(fornecedorId))
    setFieldErrors({})
  }, [initial, open, fornecedorId])

  if (!open) return null

  const set = (field: keyof DadoBancarioFornecedorFormData, value: string) =>
    setForm(prev => ({ ...prev, [field]: value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setFieldErrors({})
    try {
      await onSave(form)
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
        style={{ width: '460px', background: '#FFFFFF', boxShadow: '-4px 0 24px rgba(0,0,0,0.12)', overflow: 'hidden' }}>

        <div className="flex items-center justify-between px-6 py-4 shrink-0"
          style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: '1rem', color: 'var(--color-brand)' }}>
            {initial ? 'Editar Dados Bancários' : 'Adicionar Conta Bancária'}
          </h2>
          <button onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        <form id="banco-forn-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4">
          <FormErrorBanner errors={fieldErrors} />

          <div className="mb-3">
            <label style={labelCls}>Tipo de Conta *</label>
            <select required style={inputCls} value={form.tipo_conta}
              onChange={e => set('tipo_conta', e.target.value)}>
              <option value="">Selecione…</option>
              {TIPO_CONTA_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <FieldError msg={fieldErrors.tipo_conta} />
          </div>

          <div className="mb-3">
            <label style={labelCls}>Código do Banco *</label>
            <input required style={inputCls} placeholder="ex: 001, 341, 237"
              value={form.codigo_banco}
              onChange={e => set('codigo_banco', e.target.value)} />
            <FieldError msg={fieldErrors.codigo_banco} />
          </div>

          <div className="grid grid-cols-3 gap-3 mb-3">
            <div className="col-span-2">
              <label style={labelCls}>Agência *</label>
              <input required style={inputCls} value={form.agencia}
                onChange={e => set('agencia', e.target.value)} />
              <FieldError msg={fieldErrors.agencia} />
            </div>
            <div>
              <label style={labelCls}>DV</label>
              <input style={inputCls} maxLength={1} value={form.agencia_dv}
                onChange={e => set('agencia_dv', e.target.value)} />
              <FieldError msg={fieldErrors.agencia_dv} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-3">
            <div className="col-span-2">
              <label style={labelCls}>Conta *</label>
              <input required style={inputCls} value={form.conta}
                onChange={e => set('conta', e.target.value)} />
              <FieldError msg={fieldErrors.conta} />
            </div>
            <div>
              <label style={labelCls}>DV</label>
              <input style={inputCls} maxLength={1} value={form.conta_dv}
                onChange={e => set('conta_dv', e.target.value)} />
              <FieldError msg={fieldErrors.conta_dv} />
            </div>
          </div>

          <div className="mb-3">
            <label style={labelCls}>Chave PIX</label>
            <input style={inputCls} placeholder="CPF, CNPJ, e-mail, telefone ou aleatória"
              value={form.chave_pix}
              onChange={e => set('chave_pix', e.target.value)} />
            <FieldError msg={fieldErrors.chave_pix} />
          </div>

          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label style={labelCls}>Código Cedente</label>
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

          <div className="mb-3">
            <label style={labelCls}>Observações</label>
            <textarea rows={2} style={{ ...inputCls, resize: 'vertical' }} value={form.observacoes}
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
          <button form="banco-forn-form" type="submit" disabled={saving}
            className="px-5 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none',
              cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1,
              fontFamily: 'var(--font-body)' }}>
            {saving ? 'Salvando…' : initial ? 'Salvar alterações' : 'Adicionar conta'}
          </button>
        </div>
      </div>
    </>
  )
}

export default DadoBancarioFornecedorForm
