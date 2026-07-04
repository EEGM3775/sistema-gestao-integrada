import React, { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import apiClient from '@/api/apiClient'
import type { ClienteEmpreendimento, ClienteEmpreendimentoFormData, CondicoesPagamento, Empreendimento } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { minPagamentoISO, maxPagamentoISO, validateISO_Pagamento } from '@/utils/dates'

interface Props {
  open: boolean
  clienteId: number
  onClose: () => void
  onSave: (data: ClienteEmpreendimentoFormData) => Promise<void>
  initial?: ClienteEmpreendimento | null
}

const CONDICOES: { value: CondicoesPagamento | ''; label: string }[] = [
  { value: '',                      label: 'Selecione…' },
  { value: 'a_vista',               label: 'À Vista' },
  { value: 'financiamento_bancario',label: 'Financiamento Bancário' },
  { value: 'financiamento_direto',  label: 'Financiamento Direto' },
  { value: 'permuta',               label: 'Permuta' },
  { value: 'cartao',                label: 'Cartão de Crédito/Débito' },
  { value: 'outro',                 label: 'Outro' },
]

function maskCurrency(v: string) {
  const digits = v.replace(/\D/g, '')
  if (!digits) return ''
  const n = parseInt(digits, 10) / 100
  return n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function currencyToDecimal(v: string) {
  return v.replace(/\./g, '').replace(',', '.')
}

const EMPTY: ClienteEmpreendimentoFormData = {
  cliente: 0, empreendimento: '', unidade_comprada: '',
  endereco_unidade: '', data_compra: '', valor_compra: '',
  condicoes_pagamento: '', observacoes_compra: '',
}

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

const AquisicaoForm: React.FC<Props> = ({ open, clienteId, onClose, onSave, initial }) => {
  const [form, setForm]               = useState<ClienteEmpreendimentoFormData>(EMPTY)
  const [empreendimentos, setEmp]     = useState<Empreendimento[]>([])
  const [displayValor, setDisplay]    = useState('')
  const [saving, setSaving]           = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    apiClient.get('/empreendimentos/').then(r => setEmp(r.data.results ?? r.data)).catch(() => {})
  }, [])

  useEffect(() => {
    if (initial) {
      setForm({ ...initial, empreendimento: initial.empreendimento, condicoes_pagamento: initial.condicoes_pagamento })
      setDisplay(parseFloat(initial.valor_compra).toLocaleString('pt-BR', { minimumFractionDigits: 2 }))
    } else {
      setForm({ ...EMPTY, cliente: clienteId })
      setDisplay('')
    }
    setFieldErrors({})
  }, [initial, open, clienteId])

  if (!open) return null

  const set = (field: keyof ClienteEmpreendimentoFormData, value: string | number) =>
    setForm(prev => ({ ...prev, [field]: value }))

  const handleValor = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value.replace(/\D/g, '')
    setDisplay(maskCurrency(raw))
    set('valor_compra', currencyToDecimal(maskCurrency(raw)))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setFieldErrors({})
    try {
      await onSave({ ...form, cliente: clienteId })
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
        style={{ width: '440px', background: '#FFFFFF', boxShadow: '-4px 0 24px rgba(0,0,0,0.12)', overflow: 'hidden' }}>

        <div className="flex items-center justify-between px-6 py-4 shrink-0"
          style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: '1rem', color: 'var(--color-brand)' }}>
            {initial ? 'Editar Aquisição' : 'Nova Aquisição'}
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        <form id="aquisicao-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-3">
          <FormErrorBanner errors={fieldErrors} />

          <div>
            <label style={labelCls}>Empreendimento *</label>
            <select required style={inputCls} value={form.empreendimento}
              onChange={e => set('empreendimento', Number(e.target.value))}>
              <option value="">Selecione…</option>
              {empreendimentos.map(emp => (
                <option key={emp.empreendimento_id} value={emp.empreendimento_id}>{emp.empreendimento}</option>
              ))}
            </select>
            <FieldError msg={fieldErrors.empreendimento} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={labelCls}>Unidade comprada *</label>
              <input required style={inputCls} value={form.unidade_comprada} placeholder="Ex: Apto 101"
                onChange={e => set('unidade_comprada', e.target.value)} />
              <FieldError msg={fieldErrors.unidade_comprada} />
            </div>
            <div>
              <label style={labelCls}>Data da compra *</label>
              <input required type="date" style={inputCls} value={form.data_compra}
                min={minPagamentoISO()} max={maxPagamentoISO()}
                onChange={e => { set('data_compra', e.target.value); setFieldErrors(p => ({ ...p, data_compra: '' })) }}
                onBlur={e => { const err = validateISO_Pagamento(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_compra: err })) }} />
              <FieldError msg={fieldErrors.data_compra} />
            </div>
          </div>

          <div>
            <label style={labelCls}>Endereço da unidade *</label>
            <input required style={inputCls} value={form.endereco_unidade}
              onChange={e => set('endereco_unidade', e.target.value)} />
            <FieldError msg={fieldErrors.endereco_unidade} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={labelCls}>Valor da compra (R$) *</label>
              <input required style={inputCls} value={displayValor} placeholder="0,00"
                onChange={handleValor} />
              <FieldError msg={fieldErrors.valor_compra} />
            </div>
            <div>
              <label style={labelCls}>Condições de pagamento *</label>
              <select required style={inputCls} value={form.condicoes_pagamento}
                onChange={e => set('condicoes_pagamento', e.target.value)}>
                {CONDICOES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <FieldError msg={fieldErrors.condicoes_pagamento} />
            </div>
          </div>

          <div>
            <label style={labelCls}>Observações</label>
            <textarea style={{ ...inputCls, minHeight: '72px', resize: 'vertical' }}
              value={form.observacoes_compra}
              onChange={e => set('observacoes_compra', e.target.value)} />
            <FieldError msg={fieldErrors.observacoes_compra} />
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
          <button form="aquisicao-form" type="submit" disabled={saving}
            className="px-5 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none',
              cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1,
              fontFamily: 'var(--font-body)' }}>
            {saving ? 'Salvando…' : initial ? 'Salvar' : 'Registrar aquisição'}
          </button>
        </div>
      </div>
    </>
  )
}

export default AquisicaoForm
