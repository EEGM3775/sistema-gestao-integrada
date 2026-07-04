import React, { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import type { ProdutoServicoFornecedor, ProdutoServicoFormData } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'

interface Props {
  open: boolean
  fornecedorId: number
  onClose: () => void
  onSave: (data: ProdutoServicoFormData) => Promise<void>
  initial?: ProdutoServicoFornecedor | null
}

const TIPO_OPTIONS = [
  { value: 'aluguel',                      label: 'Aluguel' },
  { value: 'aluguel_equipamento',          label: 'Aluguel de Equipamento' },
  { value: 'aluguel_maquinario',           label: 'Aluguel de Maquinário' },
  { value: 'assinatura',                   label: 'Assinatura' },
  { value: 'comissao',                     label: 'Comissão' },
  { value: 'consultoria',                  label: 'Consultoria' },
  { value: 'equipamento_obra',             label: 'Equipamento de Obra' },
  { value: 'equipamento_pessoal',          label: 'Equipamento Pessoal' },
  { value: 'ferramenta',                   label: 'Ferramenta' },
  { value: 'frete',                        label: 'Frete' },
  { value: 'hardware',                     label: 'Hardware' },
  { value: 'imposto',                      label: 'Imposto' },
  { value: 'licenca',                      label: 'Licença' },
  { value: 'maquina',                      label: 'Máquina' },
  { value: 'manutencao',                   label: 'Manutenção' },
  { value: 'material_acabamento',          label: 'Material de Acabamento' },
  { value: 'material_construcao',          label: 'Material de Construção' },
  { value: 'material_electrico',           label: 'Material Elétrico' },
  { value: 'material_escritorio',          label: 'Material de Escritório' },
  { value: 'material_hidraulico',          label: 'Material Hidráulico' },
  { value: 'material_jardinagem',          label: 'Material de Jardinagem' },
  { value: 'material_limpeza',             label: 'Material de Limpeza' },
  { value: 'material_manutencao',          label: 'Material de Manutenção' },
  { value: 'material_pavimentacao',        label: 'Material de Pavimentação' },
  { value: 'obra',                         label: 'Obra' },
  { value: 'produto',                      label: 'Produto' },
  { value: 'projeto',                      label: 'Projeto' },
  { value: 'servico',                      label: 'Serviço' },
  { value: 'servico_administrativo',       label: 'Serviço Administrativo' },
  { value: 'servico_almoxarifado',         label: 'Serviço de Almoxarifado' },
  { value: 'servico_construcao',           label: 'Serviço de Construção' },
  { value: 'servico_construcao_civil',     label: 'Serviço de Construção Civil' },
  { value: 'servico_contabil',             label: 'Serviço Contábil' },
  { value: 'servico_consultoria',          label: 'Serviço de Consultoria' },
  { value: 'servico_eletrica',             label: 'Serviço Elétrico' },
  { value: 'servico_engenharia_arquitetura', label: 'Serviço de Engenharia e Arquitetura' },
  { value: 'servico_estoque',              label: 'Serviço de Estoque' },
  { value: 'servico_financeiro',           label: 'Serviço Financeiro' },
  { value: 'servico_gerenciamento',        label: 'Serviço de Gerenciamento' },
  { value: 'servico_hidraulica',           label: 'Serviço Hidráulico' },
  { value: 'servico_instalacao',           label: 'Serviço de Instalação' },
  { value: 'servico_juridico',             label: 'Serviço Jurídico' },
  { value: 'servico_logistica',            label: 'Serviço de Logística' },
  { value: 'servico_manutencao',           label: 'Serviço de Manutenção' },
  { value: 'servico_marketing',            label: 'Serviço de Marketing' },
  { value: 'servico_pintura',              label: 'Serviço de Pintura' },
  { value: 'servico_reforma',              label: 'Serviço de Reforma' },
  { value: 'servico_tecnico',              label: 'Serviço Técnico' },
  { value: 'servico_terceirizado',         label: 'Serviço Terceirizado' },
  { value: 'servico_terraplenagem',        label: 'Serviço de Terraplenagem' },
  { value: 'servico_transporte',           label: 'Serviço de Transporte' },
  { value: 'servico_vendas',               label: 'Serviço de Vendas' },
  { value: 'software',                     label: 'Software' },
  { value: 'suporte',                      label: 'Suporte' },
  { value: 'taxa',                         label: 'Taxa' },
  { value: 'treinamento',                  label: 'Treinamento' },
  { value: 'veiculo',                      label: 'Veículo' },
  { value: 'outro',                        label: 'Outro' },
]

const EMPTY = (fornecedorId: number): ProdutoServicoFormData => ({
  fornecedor: fornecedorId,
  nome_produto_servico: '', descricao: '', unidade_medida: '',
  preco_unitario: '', tipo_produto_servico: '',
})

function toForm(ps: ProdutoServicoFornecedor, fornecedorId: number): ProdutoServicoFormData {
  return {
    fornecedor: fornecedorId,
    nome_produto_servico: ps.nome_produto_servico,
    descricao: ps.descricao ?? '',
    unidade_medida: ps.unidade_medida,
    preco_unitario: ps.preco_unitario,
    tipo_produto_servico: ps.tipo_produto_servico,
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

const ProdutoServicoForm: React.FC<Props> = ({ open, fornecedorId, onClose, onSave, initial }) => {
  const [form, setForm]     = useState<ProdutoServicoFormData>(EMPTY(fornecedorId))
  const [saving, setSaving]           = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    setForm(initial ? toForm(initial, fornecedorId) : EMPTY(fornecedorId))
    setFieldErrors({})
  }, [initial, open, fornecedorId])

  if (!open) return null

  const set = (field: keyof ProdutoServicoFormData, value: string | number | null) =>
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
            {initial ? 'Editar Produto / Serviço' : 'Novo Produto / Serviço'}
          </h2>
          <button onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        <form id="produto-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4">
          <FormErrorBanner errors={fieldErrors} />

          <div className="mb-3">
            <label style={labelCls}>Nome do Produto / Serviço *</label>
            <input required style={inputCls} value={form.nome_produto_servico}
              onChange={e => set('nome_produto_servico', e.target.value)} />
            <FieldError msg={fieldErrors.nome_produto_servico} />
          </div>

          <div className="mb-3">
            <label style={labelCls}>Tipo *</label>
            <select required style={inputCls} value={form.tipo_produto_servico}
              onChange={e => set('tipo_produto_servico', e.target.value)}>
              <option value="">Selecione…</option>
              {TIPO_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <FieldError msg={fieldErrors.tipo_produto_servico} />
          </div>

          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label style={labelCls}>Unidade de Medida *</label>
              <input required style={inputCls} placeholder="un, m², m³, kg, h…"
                value={form.unidade_medida}
                onChange={e => set('unidade_medida', e.target.value)} />
              <FieldError msg={fieldErrors.unidade_medida} />
            </div>
            <div>
              <label style={labelCls}>Preço Unitário (R$) *</label>
              <input required type="number" min="0" step="0.01" style={inputCls}
                value={form.preco_unitario}
                onChange={e => set('preco_unitario', e.target.value)} />
              <FieldError msg={fieldErrors.preco_unitario} />
            </div>
          </div>

          <div className="mb-3">
            <label style={labelCls}>Descrição</label>
            <textarea rows={3} style={{ ...inputCls, resize: 'vertical' }} value={form.descricao}
              onChange={e => set('descricao', e.target.value)} />
            <FieldError msg={fieldErrors.descricao} />
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
          <button form="produto-form" type="submit" disabled={saving}
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

export default ProdutoServicoForm
