import React, { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import type { Cliente, ClienteFormData, EstadoCivil } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { maskCPFCNPJ, validateCPFCNPJ } from '@/utils/masks'
import { validateISO_Nasc, minCalendarioISO, maxCalendarioISO } from '@/utils/dates'

interface Props {
  open: boolean
  onClose: () => void
  onSave: (data: ClienteFormData) => Promise<void>
  initial?: Cliente | null
}

const ESTADO_CIVIL_OPTIONS: { value: EstadoCivil | ''; label: string }[] = [
  { value: '',               label: 'Não informado' },
  { value: 'solteiro',      label: 'Solteiro(a)' },
  { value: 'casado',        label: 'Casado(a)' },
  { value: 'divorciado',    label: 'Divorciado(a)' },
  { value: 'viuvo',         label: 'Viúvo(a)' },
  { value: 'uniao_estavel', label: 'União Estável' },
]

function maskCEP(v: string) {
  const d = v.replace(/\D/g, '').slice(0, 8)
  return d.replace(/(\d{5})(\d{0,3})/, (_, a, b) => b ? `${a}-${b}` : a)
}

const EMPTY: ClienteFormData = {
  nome_completo: '', cpf_cnpj: '', email: '', telefone: '',
  data_nascimento: '', estado_civil: '', profissao: '',
  endereco: '', numero_endereco: '', complemento_endereco: '',
  bairro: '', cidade: '', estado: '', cep: '',
}

function toForm(c: Cliente): ClienteFormData {
  return {
    nome_completo: c.nome_completo,
    cpf_cnpj: c.cpf_cnpj,
    email: c.email,
    telefone: c.telefone,
    data_nascimento: c.data_nascimento,
    estado_civil: c.estado_civil ?? '',
    profissao: c.profissao ?? '',
    endereco: c.endereco,
    numero_endereco: c.numero_endereco,
    complemento_endereco: c.complemento_endereco,
    bairro: c.bairro,
    cidade: c.cidade,
    estado: c.estado,
    cep: c.cep,
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


const ClienteForm: React.FC<Props> = ({ open, onClose, onSave, initial }) => {
  const [form, setForm]         = useState<ClienteFormData>(EMPTY)
  const [saving, setSaving]         = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    setForm(initial ? toForm(initial) : EMPTY)
    setFieldErrors({})
  }, [initial, open])

  if (!open) return null

  const set = (field: keyof ClienteFormData, value: string) =>
    setForm(prev => ({ ...prev, [field]: value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const cpfValidation = validateCPFCNPJ(form.cpf_cnpj)
    if (cpfValidation) { setFieldErrors({ cpf_cnpj: cpfValidation }); return }
    setSaving(true)
    setFieldErrors({})
    try {
      await onSave({
        ...form,
        cpf_cnpj: form.cpf_cnpj.replace(/\D/g, ''),
        cep: form.cep.replace(/\D/g, ''),
        estado_civil: form.estado_civil || null as unknown as '',
      })
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

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 shrink-0"
          style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: '1rem', color: 'var(--color-brand)' }}>
            {initial ? 'Editar Cliente' : 'Novo Cliente'}
          </h2>
          <button onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <form id="cliente-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4">

          <SectionTitle>Dados Pessoais</SectionTitle>

          <div className="mb-3">
            <label style={labelCls}>Nome completo *</label>
            <input required style={inputCls} value={form.nome_completo}
              onChange={e => set('nome_completo', e.target.value)} />
            <FieldError msg={fieldErrors.nome_completo} />
          </div>

          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label style={labelCls}>CPF / CNPJ *</label>
              <input required style={inputCls}
                placeholder="000.000.000-00" maxLength={18}
                value={maskCPFCNPJ(form.cpf_cnpj)}
                onChange={e => { setFieldErrors(prev => ({ ...prev, cpf_cnpj: '' })); set('cpf_cnpj', e.target.value.replace(/\D/g, '')) }}
                onBlur={() => { const v = validateCPFCNPJ(form.cpf_cnpj); if (v) setFieldErrors(prev => ({ ...prev, cpf_cnpj: v })) }} />
              <FieldError msg={fieldErrors.cpf_cnpj} />
            </div>
            <div>
              <label style={labelCls}>Data de nascimento *</label>
              <input required type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputCls} value={form.data_nascimento}
                onChange={e => { set('data_nascimento', e.target.value); setFieldErrors(p => ({ ...p, data_nascimento: '' })) }}
                onBlur={e => { const err = validateISO_Nasc(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_nascimento: err })) }} />
              <FieldError msg={fieldErrors.data_nascimento} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label style={labelCls}>Estado civil</label>
              <select style={inputCls} value={form.estado_civil}
                onChange={e => set('estado_civil', e.target.value)}>
                {ESTADO_CIVIL_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <FieldError msg={fieldErrors.estado_civil} />
            </div>
            <div>
              <label style={labelCls}>Profissão</label>
              <input style={inputCls} value={form.profissao}
                onChange={e => set('profissao', e.target.value)} />
              <FieldError msg={fieldErrors.profissao} />
            </div>
          </div>

          <SectionTitle>Contato</SectionTitle>

          <div className="mb-3">
            <label style={labelCls}>E-mail</label>
            <input type="email" style={inputCls} value={form.email}
              onChange={e => set('email', e.target.value)} />
            <FieldError msg={fieldErrors.email} />
          </div>

          <div className="mb-3">
            <label style={labelCls}>Telefone</label>
            <input style={inputCls} value={form.telefone} placeholder="(00) 00000-0000"
              onChange={e => set('telefone', e.target.value)} />
            <FieldError msg={fieldErrors.telefone} />
          </div>

          <SectionTitle>Endereço</SectionTitle>

          <div className="grid grid-cols-3 gap-3 mb-3">
            <div className="col-span-2">
              <label style={labelCls}>Logradouro</label>
              <input style={inputCls} value={form.endereco}
                onChange={e => set('endereco', e.target.value)} />
              <FieldError msg={fieldErrors.endereco} />
            </div>
            <div>
              <label style={labelCls}>Número</label>
              <input style={inputCls} value={form.numero_endereco}
                onChange={e => set('numero_endereco', e.target.value)} />
              <FieldError msg={fieldErrors.numero_endereco} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label style={labelCls}>Complemento</label>
              <input style={inputCls} value={form.complemento_endereco}
                onChange={e => set('complemento_endereco', e.target.value)} />
              <FieldError msg={fieldErrors.complemento_endereco} />
            </div>
            <div>
              <label style={labelCls}>Bairro</label>
              <input style={inputCls} value={form.bairro}
                onChange={e => set('bairro', e.target.value)} />
              <FieldError msg={fieldErrors.bairro} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-3">
            <div>
              <label style={labelCls}>CEP</label>
              <input style={inputCls} placeholder="00000-000" maxLength={9}
                value={maskCEP(form.cep)}
                onChange={e => set('cep', e.target.value.replace(/\D/g, ''))} />
              <FieldError msg={fieldErrors.cep} />
            </div>
            <div>
              <label style={labelCls}>Cidade</label>
              <input style={inputCls} value={form.cidade}
                onChange={e => set('cidade', e.target.value)} />
              <FieldError msg={fieldErrors.cidade} />
            </div>
            <div>
              <label style={labelCls}>UF</label>
              <input style={inputCls} value={form.estado} maxLength={2} placeholder="SP"
                onChange={e => set('estado', e.target.value.toUpperCase())} />
              <FieldError msg={fieldErrors.estado} />
            </div>
          </div>

          <FormErrorBanner errors={fieldErrors} />
        </form>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 shrink-0"
          style={{ borderTop: '1px solid #e2e8f0' }}>
          <button type="button" onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'none', border: '1.5px solid #e2e8f0', cursor: 'pointer',
              color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
            Cancelar
          </button>
          <button form="cliente-form" type="submit" disabled={saving}
            className="px-5 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none',
              cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1,
              fontFamily: 'var(--font-body)' }}>
            {saving ? 'Salvando…' : initial ? 'Salvar alterações' : 'Criar cliente'}
          </button>
        </div>
      </div>
    </>
  )
}

export default ClienteForm
