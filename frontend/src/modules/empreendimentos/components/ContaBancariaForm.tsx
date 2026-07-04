import React, { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import type { ContaBancariaEmpreendimento, ContaBancariaEmpreendimentoFormData } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'

interface Props {
  open: boolean
  empreendimentoId: number
  onClose: () => void
  onSave: (data: ContaBancariaEmpreendimentoFormData) => Promise<void>
  initial?: ContaBancariaEmpreendimento | null
}

const EMPTY = (empreendimentoId: number): ContaBancariaEmpreendimentoFormData => ({
  empreendimento: empreendimentoId,
  tipo_conta: 'corrente',
  codigo_banco: '',
  agencia: '',
  agencia_dv: '',
  conta: '',
  conta_dv: '',
  codigo_cedente: '',
  carteira: '',
  codigo_pix: '',
  is_principal: 1,
  observacoes: '',
})

function toForm(c: ContaBancariaEmpreendimento, empId: number): ContaBancariaEmpreendimentoFormData {
  return {
    empreendimento: empId,
    tipo_conta: c.tipo_conta,
    codigo_banco: c.codigo_banco,
    agencia: c.agencia,
    agencia_dv: c.agencia_dv ?? '',
    conta: c.conta,
    conta_dv: c.conta_dv ?? '',
    codigo_cedente: c.codigo_cedente ?? '',
    carteira: c.carteira ?? '',
    codigo_pix: c.codigo_pix ?? '',
    is_principal: c.is_principal,
    observacoes: c.observacoes ?? '',
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

const SectionTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p style={{
    fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em',
    textTransform: 'uppercase', color: 'var(--color-brand)',
    fontFamily: 'var(--font-body)', marginBottom: '12px', marginTop: '20px',
  }}>
    {children}
  </p>
)

const ContaBancariaForm: React.FC<Props> = ({ open, empreendimentoId, onClose, onSave, initial }) => {
  const [form, setForm]   = useState<ContaBancariaEmpreendimentoFormData>(EMPTY(empreendimentoId))
  const [saving, setSaving] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    if (!open) return
    setForm(initial ? toForm(initial, empreendimentoId) : EMPTY(empreendimentoId))
    setFieldErrors({})
  }, [initial, open, empreendimentoId])

  if (!open) return null

  const set = <K extends keyof ContaBancariaEmpreendimentoFormData>(
    field: K, value: ContaBancariaEmpreendimentoFormData[K]
  ) => setForm(prev => ({ ...prev, [field]: value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
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

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.3)' }} onClick={onClose} />
      <div className="fixed top-0 right-0 h-full z-50 flex flex-col"
        style={{ width: '480px', background: '#FFFFFF', boxShadow: '-4px 0 24px rgba(0,0,0,0.12)', overflow: 'hidden' }}>

        <div className="flex items-center justify-between px-6 py-4 shrink-0"
          style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: '1rem', color: 'var(--color-brand)' }}>
            {initial ? 'Editar Conta Bancária' : 'Nova Conta Bancária'}
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        <form id="conta-bancaria-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4">
          <SectionTitle>Dados do Banco</SectionTitle>

          <div className="grid grid-cols-3 gap-3 mb-3">
            <div className="col-span-2">
              <label style={labelCls}>Código do Banco *</label>
              <input required style={inputCls} placeholder="001" maxLength={10}
                value={form.codigo_banco}
                onChange={e => set('codigo_banco', e.target.value)} />
              <FieldError msg={fieldErrors.codigo_banco} />
            </div>
            <div>
              <label style={labelCls}>Tipo *</label>
              <select required style={{ ...inputCls, cursor: 'pointer' }}
                value={form.tipo_conta}
                onChange={e => set('tipo_conta', e.target.value as ContaBancariaEmpreendimentoFormData['tipo_conta'])}>
                <option value="corrente">Corrente</option>
                <option value="poupanca">Poupança</option>
                <option value="investimento">Investimento</option>
              </select>
              <FieldError msg={fieldErrors.tipo_conta} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-3">
            <div className="col-span-2">
              <label style={labelCls}>Agência *</label>
              <input required style={inputCls} placeholder="0001" maxLength={20}
                value={form.agencia}
                onChange={e => set('agencia', e.target.value)} />
              <FieldError msg={fieldErrors.agencia} />
            </div>
            <div>
              <label style={labelCls}>DV</label>
              <input style={inputCls} placeholder="X" maxLength={1}
                value={form.agencia_dv}
                onChange={e => set('agencia_dv', e.target.value)} />
              <FieldError msg={fieldErrors.agencia_dv} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-3">
            <div className="col-span-2">
              <label style={labelCls}>Conta *</label>
              <input required style={inputCls} placeholder="12345-6" maxLength={20}
                value={form.conta}
                onChange={e => set('conta', e.target.value)} />
              <FieldError msg={fieldErrors.conta} />
            </div>
            <div>
              <label style={labelCls}>DV</label>
              <input style={inputCls} placeholder="X" maxLength={1}
                value={form.conta_dv}
                onChange={e => set('conta_dv', e.target.value)} />
              <FieldError msg={fieldErrors.conta_dv} />
            </div>
          </div>

          <SectionTitle>Dados Complementares</SectionTitle>

          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label style={labelCls}>Código Cedente</label>
              <input style={inputCls} maxLength={25}
                value={form.codigo_cedente}
                onChange={e => set('codigo_cedente', e.target.value)} />
              <FieldError msg={fieldErrors.codigo_cedente} />
            </div>
            <div>
              <label style={labelCls}>Carteira</label>
              <input style={inputCls} maxLength={25}
                value={form.carteira}
                onChange={e => set('carteira', e.target.value)} />
              <FieldError msg={fieldErrors.carteira} />
            </div>
          </div>

          <div className="mb-3">
            <label style={labelCls}>Chave PIX</label>
            <input style={inputCls} placeholder="CPF, e-mail, telefone ou chave aleatória"
              value={form.codigo_pix}
              onChange={e => set('codigo_pix', e.target.value)} />
            <FieldError msg={fieldErrors.codigo_pix} />
          </div>

          <div className="mb-3">
            <label style={labelCls}>Conta Principal</label>
            <select style={{ ...inputCls, cursor: 'pointer' }}
              value={form.is_principal}
              onChange={e => set('is_principal', Number(e.target.value) as 1 | 0)}>
              <option value={1}>Sim</option>
              <option value={0}>Não</option>
            </select>
          </div>

          <div className="mb-3">
            <label style={labelCls}>Observações</label>
            <textarea style={{ ...inputCls, resize: 'vertical', minHeight: '80px' }}
              value={form.observacoes}
              onChange={e => set('observacoes', e.target.value)} />
            <FieldError msg={fieldErrors.observacoes} />
          </div>

          <FormErrorBanner errors={fieldErrors} />
        </form>

        <div className="flex items-center justify-end gap-3 px-6 py-4 shrink-0"
          style={{ borderTop: '1px solid #e2e8f0' }}>
          <button type="button" onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'none', border: '1.5px solid #e2e8f0', cursor: 'pointer',
              color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
            Cancelar
          </button>
          <button form="conta-bancaria-form" type="submit" disabled={saving}
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

export default ContaBancariaForm
