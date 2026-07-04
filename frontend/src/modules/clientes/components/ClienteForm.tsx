import React, { useState, useEffect } from 'react'
import { X, AlertTriangle } from 'lucide-react'
import type { Cliente, ClienteFormData, EstadoCivil } from '@/types'
import type { DivergenciaAsaas } from '../services/clientesService'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { maskCPFCNPJ, validateCPFCNPJ, formatCPFCNPJ } from '@/utils/masks'
import { minNascISO, maxTodayISO, validateISO_Nasc } from '@/utils/dates'

interface Props {
  open: boolean
  onClose: () => void
  onSave: (data: ClienteFormData) => Promise<void>
  initial?: Cliente | null
  /** Divergências banco × Asaas (auditadas ao abrir "Novo Cliente") — só no cadastro. */
  divergencias?: DivergenciaAsaas[]
  divergLoading?: boolean
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


// Teto de linhas efetivamente renderizadas no painel. Sem isso, um tenant com
// milhares de divergências geraria milhares de <li> e o aviso "tomaria" toda a
// gaveta, enterrando os campos do formulário. O total real continua no cabeçalho.
const MAX_DIVERGENCIAS_VISIVEIS = 50

const DivergenciasAsaasPanel: React.FC<{ loading: boolean; divergencias: DivergenciaAsaas[] }> = ({ loading, divergencias }) => {
  if (loading) {
    return (
      <div className="mb-4 px-4 py-3 rounded-lg text-xs" style={{
        background: '#f8fafc', border: '1px solid #e2e8f0',
        color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)',
      }}>
        Verificando divergências com o gateway de cobrança (Asaas)…
      </div>
    )
  }
  if (divergencias.length === 0) return null

  const total = divergencias.length
  const visiveis = divergencias.slice(0, MAX_DIVERGENCIAS_VISIVEIS)
  const ocultas = total - visiveis.length

  return (
    <div className="mb-4 px-4 py-3 rounded-lg" style={{
      background: '#fffbeb', border: '1px solid #fde68a', fontFamily: 'var(--font-body)',
    }}>
      <div className="flex items-center gap-2 mb-2" style={{ color: '#92400e' }}>
        <AlertTriangle size={15} />
        <span className="text-xs font-bold uppercase tracking-wide">
          {total} divergência{total !== 1 ? 's' : ''} entre cadastro e Asaas
        </span>
      </div>
      <p className="text-xs mb-2" style={{ color: '#92400e' }}>
        Clientes cujo cadastro impediria ou desviaria uma cobrança. Corrija antes de emitir boletos:
      </p>
      {/* Lista com altura limitada e rolagem própria: o painel nunca cresce além
          disso, independentemente do número de divergências. */}
      <ul className="flex flex-col gap-1.5" style={{ maxHeight: '220px', overflowY: 'auto' }}>
        {visiveis.map(d => (
          <li key={d.cliente_id} className="text-xs" style={{ color: '#78350f', lineHeight: 1.4 }}>
            <span className="font-semibold">{d.nome}</span>
            {d.documento ? ` (${formatCPFCNPJ(d.documento)})` : ''}
            {d.nome_gateway ? <> — no Asaas: <span className="font-semibold">“{d.nome_gateway}”</span></> : ''}
            <br />
            <span style={{ opacity: 0.85 }}>{d.detalhe}</span>
          </li>
        ))}
      </ul>
      {ocultas > 0 && (
        <p className="text-xs mt-2 font-semibold" style={{ color: '#92400e' }}>
          + {ocultas} outr{ocultas !== 1 ? 'as' : 'a'} divergência{ocultas !== 1 ? 's' : ''} não listada{ocultas !== 1 ? 's' : ''} aqui.
          Corrija estas e reabra para ver as demais.
        </p>
      )}
    </div>
  )
}

const ClienteForm: React.FC<Props> = ({ open, onClose, onSave, initial, divergencias = [], divergLoading = false }) => {
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

          {!initial && <DivergenciasAsaasPanel loading={divergLoading} divergencias={divergencias} />}

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
              <input required type="date" style={inputCls} value={form.data_nascimento}
                min={minNascISO} max={maxTodayISO()}
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
            <label style={labelCls}>E-mail *</label>
            <input required type="email" style={inputCls} value={form.email}
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
