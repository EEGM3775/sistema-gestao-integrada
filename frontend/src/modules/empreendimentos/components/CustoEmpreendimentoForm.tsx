import React, { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import type { CustoEmpreendimento, CustoEmpreendimentoFormData, TipoCusto } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { minPagamentoISO, maxPagamentoISO, validateISO_Pagamento } from '@/utils/dates'

interface Props {
  open: boolean
  empreendimentoId: number
  onClose: () => void
  onSave: (data: CustoEmpreendimentoFormData) => Promise<void>
  initial?: CustoEmpreendimento | null
}

const TIPO_OPTIONS: { value: TipoCusto; label: string }[] = [
  { value: 'materiais',         label: 'Materiais' },
  { value: 'servicos',          label: 'Serviços' },
  { value: 'servicos_terceiros',label: 'Serviços de Terceiros' },
  { value: 'funcionarios',      label: 'Funcionários' },
  { value: 'equipamentos',      label: 'Equipamentos' },
  { value: 'imovel',            label: 'Imóvel' },
  { value: 'fixo',              label: 'Fixo' },
  { value: 'variavel',          label: 'Variável' },
  { value: 'impostos',          label: 'Impostos' },
  { value: 'taxas',             label: 'Taxas' },
  { value: 'seguros',           label: 'Seguros' },
  { value: 'manutencao',        label: 'Manutenção' },
  { value: 'transporte',        label: 'Transporte' },
  { value: 'automovel',         label: 'Automóvel' },
  { value: 'mobiliario',        label: 'Mobiliário' },
  { value: 'publicidade',       label: 'Publicidade' },
  { value: 'imprevisto',        label: 'Imprevisto' },
  { value: 'extra',             label: 'Extra' },
  { value: 'outros',            label: 'Outros' },
]

const EMPTY = (empreendimentoId: number): CustoEmpreendimentoFormData => ({
  empreendimento: empreendimentoId,
  tipo_custo: 'materiais',
  descricao: '',
  valor: '',
  quantidade: '1',
  data_custo: new Date().toISOString().split('T')[0],
  nota_fiscal: '',
})

function toForm(c: CustoEmpreendimento, empId: number): CustoEmpreendimentoFormData {
  return {
    empreendimento: empId,
    tipo_custo: c.tipo_custo,
    descricao: c.descricao ?? '',
    valor: c.valor,
    quantidade: c.quantidade,
    data_custo: c.data_custo,
    nota_fiscal: c.nota_fiscal ?? '',
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

const CustoEmpreendimentoForm: React.FC<Props> = ({ open, empreendimentoId, onClose, onSave, initial }) => {
  const [form, setForm]   = useState<CustoEmpreendimentoFormData>(EMPTY(empreendimentoId))
  const [saving, setSaving] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    if (!open) return
    setForm(initial ? toForm(initial, empreendimentoId) : EMPTY(empreendimentoId))
    setFieldErrors({})
  }, [initial, open, empreendimentoId])

  if (!open) return null

  const set = <K extends keyof CustoEmpreendimentoFormData>(
    field: K, value: CustoEmpreendimentoFormData[K]
  ) => setForm(prev => ({ ...prev, [field]: value }))

  const valor  = parseFloat(form.valor.replace(',', '.')) || 0
  const qtd    = parseFloat(form.quantidade.replace(',', '.')) || 0
  const total  = valor * qtd

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
            {initial ? 'Editar Custo' : 'Registrar Custo'}
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        <form id="custo-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4">
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label style={labelCls}>Tipo de Custo *</label>
              <select required style={{ ...inputCls, cursor: 'pointer' }}
                value={form.tipo_custo}
                onChange={e => set('tipo_custo', e.target.value as TipoCusto)}>
                {TIPO_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <FieldError msg={fieldErrors.tipo_custo} />
            </div>
            <div>
              <label style={labelCls}>Data *</label>
              <input required type="date" style={inputCls} value={form.data_custo}
                min={minPagamentoISO()} max={maxPagamentoISO()}
                onChange={e => { set('data_custo', e.target.value); setFieldErrors(p => ({ ...p, data_custo: '' })) }}
                onBlur={e => { const err = validateISO_Pagamento(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_custo: err })) }} />
              <FieldError msg={fieldErrors.data_custo} />
            </div>
          </div>

          <div className="mb-3">
            <label style={labelCls}>Descrição</label>
            <textarea style={{ ...inputCls, resize: 'vertical', minHeight: '72px' }}
              value={form.descricao}
              onChange={e => set('descricao', e.target.value)} />
            <FieldError msg={fieldErrors.descricao} />
          </div>

          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label style={labelCls}>Valor Unitário (R$) *</label>
              <input required type="number" step="0.01" min="0" style={inputCls}
                placeholder="0,00"
                value={form.valor}
                onChange={e => set('valor', e.target.value)} />
              <FieldError msg={fieldErrors.valor} />
            </div>
            <div>
              <label style={labelCls}>Quantidade *</label>
              <input required type="number" step="0.001" min="0.001" style={inputCls}
                placeholder="1"
                value={form.quantidade}
                onChange={e => set('quantidade', e.target.value)} />
              <FieldError msg={fieldErrors.quantidade} />
            </div>
          </div>

          {/* Preview do total */}
          {total > 0 && (
            <div className="mb-4 px-4 py-3 rounded-lg flex items-center justify-between"
              style={{ background: '#f0fdf4', border: '1px solid #bbf7d0' }}>
              <span style={{ fontSize: '0.8rem', color: '#166534', fontFamily: 'var(--font-body)' }}>Total calculado</span>
              <span style={{ fontSize: '0.95rem', fontWeight: 700, color: '#166534', fontFamily: 'var(--font-heading)' }}>
                {total.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
              </span>
            </div>
          )}

          <div className="mb-3">
            <label style={labelCls}>Nota Fiscal / NF-e</label>
            <input style={inputCls} placeholder="Número ou referência da nota"
              value={form.nota_fiscal}
              onChange={e => set('nota_fiscal', e.target.value)} />
            <FieldError msg={fieldErrors.nota_fiscal} />
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
          <button form="custo-form" type="submit" disabled={saving}
            className="px-5 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none',
              cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1,
              fontFamily: 'var(--font-body)' }}>
            {saving ? 'Salvando…' : initial ? 'Salvar alterações' : 'Registrar custo'}
          </button>
        </div>
      </div>
    </>
  )
}

export default CustoEmpreendimentoForm
