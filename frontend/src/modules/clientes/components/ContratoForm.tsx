import React, { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import apiClient from '@/api/apiClient'
import type {
  ContratoCliente, ContratoClienteFormData, StatusContrato,
  Empreendimento, ClienteEmpreendimento,
} from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { minVigenciaISO, maxVigenciaISO, validateISO_Vigencia } from '@/utils/dates'

interface Props {
  open: boolean
  clienteId: number
  aquisicoes: ClienteEmpreendimento[]
  onClose: () => void
  onSave: (data: ContratoClienteFormData) => Promise<void>
  initial?: ContratoCliente | null
}

const STATUS_OPTIONS: { value: StatusContrato; label: string }[] = [
  { value: 'ativo',      label: 'Ativo' },
  { value: 'inativo',    label: 'Inativo' },
  { value: 'cancelado',  label: 'Cancelado' },
  { value: 'concluido',  label: 'Concluído' },
]

const EMPTY: ContratoClienteFormData = {
  cliente: 0, empreendimento: '', cliente_empreendimento: '',
  numero_contrato: '', data_assinatura: '', objeto_contrato: '',
  arquivo_contrato: '', status_contrato: 'ativo', responsavel: '', vendedor: '',
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

const ContratoForm: React.FC<Props> = ({ open, clienteId, aquisicoes, onClose, onSave, initial }) => {
  const [form, setForm]           = useState<ContratoClienteFormData>(EMPTY)
  const [empreendimentos, setEmp] = useState<Empreendimento[]>([])
  const [saving, setSaving]       = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    apiClient.get('/empreendimentos/').then(r => setEmp(r.data.results ?? r.data)).catch(() => {})
  }, [])

  useEffect(() => {
    if (initial) {
      setForm({
        cliente: clienteId,
        empreendimento: initial.empreendimento,
        cliente_empreendimento: initial.cliente_empreendimento ?? '',
        numero_contrato: initial.numero_contrato,
        data_assinatura: initial.data_assinatura ?? '',
        objeto_contrato: initial.objeto_contrato,
        arquivo_contrato: initial.arquivo_contrato ?? '',
        status_contrato: initial.status_contrato,
        responsavel: initial.responsavel ?? '',
        vendedor: initial.vendedor ?? '',
      })
    } else {
      setForm({ ...EMPTY, cliente: clienteId })
    }
    setFieldErrors({})
  }, [initial, open, clienteId])

  if (!open) return null

  const set = (field: keyof ContratoClienteFormData, value: string | number) =>
    setForm(prev => ({ ...prev, [field]: value }))

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
            {initial ? 'Editar Contrato' : 'Novo Contrato'}
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        <form id="contrato-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-3">
          <FormErrorBanner errors={fieldErrors} />

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={labelCls}>Número do contrato *</label>
              <input required style={inputCls} value={form.numero_contrato}
                onChange={e => set('numero_contrato', e.target.value)} />
              <FieldError msg={fieldErrors.numero_contrato} />
            </div>
            <div>
              <label style={labelCls}>Status</label>
              <select style={inputCls} value={form.status_contrato}
                onChange={e => set('status_contrato', e.target.value)}>
                {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <FieldError msg={fieldErrors.status_contrato} />
            </div>
          </div>

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

          {aquisicoes.length > 0 && (
            <div>
              <label style={labelCls}>Aquisição vinculada</label>
              <select style={inputCls} value={form.cliente_empreendimento}
                onChange={e => set('cliente_empreendimento', e.target.value ? Number(e.target.value) : '')}>
                <option value="">Nenhuma</option>
                {aquisicoes.map(a => (
                  <option key={a.cliente_empreendimento_id} value={a.cliente_empreendimento_id}>
                    {a.empreendimento_nome} — {a.rotulo_unidade}
                  </option>
                ))}
              </select>
              <FieldError msg={fieldErrors.cliente_empreendimento} />
            </div>
          )}

          <div>
            <label style={labelCls}>Data de assinatura</label>
            <input type="date" style={inputCls} value={form.data_assinatura}
              min={minVigenciaISO()} max={maxVigenciaISO()}
              onChange={e => { set('data_assinatura', e.target.value); setFieldErrors(p => ({ ...p, data_assinatura: '' })) }}
              onBlur={e => { const err = validateISO_Vigencia(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_assinatura: err })) }} />
            <FieldError msg={fieldErrors.data_assinatura} />
          </div>

          <div>
            <label style={labelCls}>Objeto do contrato *</label>
            <textarea required style={{ ...inputCls, minHeight: '80px', resize: 'vertical' }}
              value={form.objeto_contrato}
              onChange={e => set('objeto_contrato', e.target.value)} />
            <FieldError msg={fieldErrors.objeto_contrato} />
          </div>

          <div>
            <label style={labelCls}>URL do arquivo</label>
            <input type="url" style={inputCls} value={form.arquivo_contrato} placeholder="https://…"
              onChange={e => set('arquivo_contrato', e.target.value)} />
            <FieldError msg={fieldErrors.arquivo_contrato} />
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
          <button form="contrato-form" type="submit" disabled={saving}
            className="px-5 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none',
              cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1,
              fontFamily: 'var(--font-body)' }}>
            {saving ? 'Salvando…' : initial ? 'Salvar' : 'Criar contrato'}
          </button>
        </div>
      </div>
    </>
  )
}

export default ContratoForm
