import React, { useState, useEffect } from 'react'
import apiClient from '@/api/apiClient'
import type { Funcionario, FuncionarioFormData, Cargo } from '@/types'
import { SeletorDeEmpreendimento } from '@/components/malha'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { maskCPF, validateCPF, maskPISPASEP, validatePISPASEP } from '@/utils/masks'
import {
  maskDate, dateFromBR, dateToBR,
  validateDataNasc, validateDataAdmissao, validateDataDemissao,
} from '@/utils/dates'

function maskPhone(v: string): string {
  const d = v.replace(/\D/g, '').slice(0, 11)
  if (!d.length) return ''
  if (d.length <= 2) return `(${d}`
  if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`
  if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`
}

// Máscara push-left (ex: "35000" → "350,00"; "3500000" → "35.000,00")
function maskSalary(v: string): string {
  const digits = v.replace(/\D/g, '')
  if (!digits) return ''
  const cents = parseInt(digits, 10)
  return (cents / 100).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// Carrega valor decimal da API ("3500.00") como BR ("3.500,00")
function salaryToBR(v: string): string {
  const n = parseFloat(v)
  return isNaN(n) ? '' : n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function parseSalary(v: string): number | null {
  const clean = v.trim()
  if (!clean) return null
  const n = clean.includes(',')
    ? parseFloat(clean.replace(/\./g, '').replace(',', '.'))
    : parseFloat(clean)
  return isNaN(n) || n < 0 ? null : n
}

// ─── Constantes de form ───────────────────────────────────────────────────────

const EMPTY: FuncionarioFormData = {
  nome_completo: '', cpf: '', rg: '', data_nascimento: '', genero: 'outro',
  estado_civil: '', telefone_pessoal: '', telefone_celular: '', email_pessoal: '',
  endereco_completo: '', cargo: '', empreendimento_vinculado: '',
  data_admissao: '', data_demissao: '', salario_base: '',
  status_contrato: 'ativo', numero_ctps: '', serie_ctps: '', pis_pasep: '',
}

function toFormData(f: Funcionario): FuncionarioFormData {
  return {
    nome_completo:            f.nome_completo,
    cpf:                      f.cpf.replace(/\D/g, ''),
    rg:                       f.rg ?? '',
    data_nascimento:          dateToBR(f.data_nascimento),
    genero:                   f.genero,
    estado_civil:             f.estado_civil ?? '',
    telefone_pessoal:         f.telefone_pessoal ? maskPhone(f.telefone_pessoal) : '',
    telefone_celular:         f.telefone_celular ? maskPhone(f.telefone_celular) : '',
    email_pessoal:            f.email_pessoal ?? '',
    endereco_completo:        f.endereco_completo,
    cargo:                    f.cargo ?? '',
    empreendimento_vinculado: f.empreendimento_vinculado ?? '',
    data_admissao:            dateToBR(f.data_admissao),
    data_demissao:            f.data_demissao ? dateToBR(f.data_demissao) : '',
    salario_base:             f.salario_base ? salaryToBR(f.salario_base) : '',
    status_contrato:          f.status_contrato,
    numero_ctps:              f.numero_ctps ?? '',
    serie_ctps:               f.serie_ctps ?? '',
    pis_pasep:                f.pis_pasep ?? '',
  }
}


// ─── Componente ───────────────────────────────────────────────────────────────

interface Props {
  open: boolean
  onClose: () => void
  onSave: (fd: FuncionarioFormData) => Promise<void>
  initial?: Funcionario | null
}

const FuncionarioForm: React.FC<Props> = ({ open, onClose, onSave, initial }) => {
  const [form, setForm]                       = useState<FuncionarioFormData>(EMPTY)
  const [cargos, setCargos]                   = useState<Cargo[]>([])
  const [saving, setSaving]                   = useState(false)
  const [fieldErrors, setFieldErrors]         = useState<FieldErrors>({})

  useEffect(() => {
    if (!open) return
    setForm(initial ? toFormData(initial) : { ...EMPTY })
    setFieldErrors({})
    apiClient.get('/cargos/')
      .then(c => setCargos(c.data.results ?? c.data))
      .catch(() => {})
  }, [open, initial])

  const set = <K extends keyof FuncionarioFormData>(k: K, v: FuncionarioFormData[K]) =>
    setForm(prev => ({ ...prev, [k]: v }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    // ── Campos obrigatórios ──
    if (!form.nome_completo.trim()) { setFieldErrors({ nome_completo: 'Campo obrigatório.' }); return }
    if (!form.cpf.trim())           { setFieldErrors({ cpf: 'Campo obrigatório.' }); return }
    const cpfErr = validateCPF(form.cpf)
    if (cpfErr)                     { setFieldErrors({ cpf: cpfErr }); return }
    if (!form.data_nascimento)      { setFieldErrors({ data_nascimento: 'Campo obrigatório.' }); return }
    if (!form.data_admissao)        { setFieldErrors({ data_admissao: 'Campo obrigatório.' }); return }

    // ── Validação de datas ──
    const nascErr = validateDataNasc(form.data_nascimento)
    if (nascErr) { setFieldErrors({ data_nascimento: nascErr }); return }

    const admiErr = validateDataAdmissao(form.data_admissao)
    if (admiErr) { setFieldErrors({ data_admissao: admiErr }); return }

    if (form.data_demissao) {
      const demErr = validateDataDemissao(form.data_demissao, form.data_admissao)
      if (demErr) { setFieldErrors({ data_demissao: demErr }); return }
    }

    // ── Montar payload para a API ──
    // data_demissao null (não '') — DRF rejeita string vazia em DateField
    const salarioNum = parseSalary(form.salario_base) ?? 0
    const apiData = {
      ...form,
      data_nascimento: dateFromBR(form.data_nascimento),
      data_admissao:   dateFromBR(form.data_admissao),
      data_demissao:   form.data_demissao ? dateFromBR(form.data_demissao) : null,
      salario_base:    salarioNum.toFixed(2),
    } as unknown as FuncionarioFormData

    setSaving(true); setFieldErrors({})
    try {
      await onSave(apiData)
      onClose()
    } catch (err: unknown) {
      const parsed = parseApiErrors(err)
      if (parsed.cpf && parsed.cpf.toLowerCase().includes('já existe')) {
        setFieldErrors({ cpf: 'Já existe um funcionário com este CPF.' })
      } else {
        setFieldErrors(parsed)
      }
    } finally {
      setSaving(false)
    }
  }

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.45)' }} onClick={onClose} />
      <aside
        className="fixed top-0 right-0 h-full z-50 flex flex-col"
        style={{ width: 'min(520px, 100vw)', background: '#FFFFFF', boxShadow: '-4px 0 30px rgba(0,0,0,0.15)' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 shrink-0"
          style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 className="text-lg font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            {initial ? 'Editar Funcionário' : 'Novo Funcionário'}
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', fontSize: '1.25rem' }}>✕</button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-5">

          <Section title="Identificação">
            <Row2>
              <Field label="Nome Completo *" error={fieldErrors.nome_completo}>
                <input value={form.nome_completo}
                  onChange={e => set('nome_completo', e.target.value)} style={inp} />
              </Field>
              <Field label="CPF *" error={fieldErrors.cpf}>
                <input value={maskCPF(form.cpf)} placeholder="000.000.000-00"
                  onChange={e => { setFieldErrors(prev => ({ ...prev, cpf: '' })); set('cpf', e.target.value.replace(/\D/g, '')) }}
                  onBlur={() => { const err = validateCPF(form.cpf); if (err) setFieldErrors(prev => ({ ...prev, cpf: err })) }}
                  maxLength={14} style={inp} />
              </Field>
            </Row2>
            <Row2>
              <Field label="RG" error={fieldErrors.rg}>
                <input value={form.rg} onChange={e => set('rg', e.target.value)} style={inp} />
              </Field>
              <Field label="Data de Nascimento *" error={fieldErrors.data_nascimento}>
                <input value={form.data_nascimento} placeholder="DD/MM/AAAA"
                  onChange={e => { setFieldErrors(prev => ({ ...prev, data_nascimento: '' })); set('data_nascimento', maskDate(e.target.value)) }}
                  onBlur={() => { const err = validateDataNasc(form.data_nascimento); if (err) setFieldErrors(prev => ({ ...prev, data_nascimento: err })) }}
                  maxLength={10} style={inp} />
              </Field>
            </Row2>
            <Row2>
              <Field label="Gênero" error={fieldErrors.genero}>
                <select value={form.genero}
                  onChange={e => set('genero', e.target.value as FuncionarioFormData['genero'])}
                  style={inp}>
                  <option value="outro">Outro</option>
                  <option value="masculino">Masculino</option>
                  <option value="feminino">Feminino</option>
                </select>
              </Field>
              <Field label="Estado Civil" error={fieldErrors.estado_civil}>
                <select value={form.estado_civil}
                  onChange={e => set('estado_civil', e.target.value as FuncionarioFormData['estado_civil'])}
                  style={inp}>
                  <option value="">Selecionar…</option>
                  <option value="solteiro">Solteiro(a)</option>
                  <option value="casado">Casado(a)</option>
                  <option value="divorciado">Divorciado(a)</option>
                  <option value="viuvo">Viúvo(a)</option>
                  <option value="uniao_estavel">União Estável</option>
                </select>
              </Field>
            </Row2>
          </Section>

          <Section title="Contato">
            <Row2>
              <Field label="E-mail Pessoal" error={fieldErrors.email_pessoal}>
                <input type="email" value={form.email_pessoal}
                  onChange={e => set('email_pessoal', e.target.value)} style={inp} />
              </Field>
              <Field label="Telefone Pessoal" error={fieldErrors.telefone_pessoal}>
                <input value={form.telefone_pessoal} placeholder="(XX) XXXX-XXXX"
                  onChange={e => set('telefone_pessoal', maskPhone(e.target.value))}
                  maxLength={15} style={inp} />
              </Field>
            </Row2>
            <Field label="Celular (WhatsApp)" error={fieldErrors.telefone_celular}>
              <input value={form.telefone_celular} placeholder="(XX) XXXXX-XXXX"
                onChange={e => set('telefone_celular', maskPhone(e.target.value))}
                maxLength={16} style={inp} />
            </Field>
          </Section>

          <Section title="Endereço">
            <Field label="Endereço Completo *" error={fieldErrors.endereco_completo}>
              <textarea value={form.endereco_completo}
                onChange={e => set('endereco_completo', e.target.value)}
                rows={2} style={{ ...inp, resize: 'vertical' }} />
            </Field>
          </Section>

          <Section title="Vínculo & Contrato">
            <Row2>
              <Field label="Cargo" error={fieldErrors.cargo}>
                <select value={form.cargo}
                  onChange={e => set('cargo', e.target.value === '' ? '' : Number(e.target.value))}
                  style={inp}>
                  <option value="">Sem cargo</option>
                  {cargos.map(c => <option key={c.cargo_id} value={c.cargo_id}>{c.nome_cargo}</option>)}
                </select>
              </Field>
              <Field label="Empreendimento Vinculado" error={fieldErrors.empreendimento_vinculado}>
                {/* Busca no servidor (F2); vazio = nenhum. */}
                <SeletorDeEmpreendimento
                  valor={form.empreendimento_vinculado === '' ? null : Number(form.empreendimento_vinculado)}
                  aoMudar={id => set('empreendimento_vinculado', id ?? '')}
                  permiteLimpar
                  placeholder="Nenhum — busque para escolher"
                  aria-label="Empreendimento vinculado"
                  style={inp}
                />
              </Field>
            </Row2>
            <Row2>
              <Field label="Data de Admissão *" error={fieldErrors.data_admissao}>
                <input value={form.data_admissao} placeholder="DD/MM/AAAA"
                  onChange={e => { setFieldErrors(prev => ({ ...prev, data_admissao: '' })); set('data_admissao', maskDate(e.target.value)) }}
                  onBlur={() => { const err = validateDataAdmissao(form.data_admissao); if (err) setFieldErrors(prev => ({ ...prev, data_admissao: err })) }}
                  maxLength={10} style={inp} />
              </Field>
              <Field label="Status do Contrato *" error={fieldErrors.status_contrato}>
                <select value={form.status_contrato}
                  onChange={e => set('status_contrato', e.target.value as FuncionarioFormData['status_contrato'])}
                  style={inp}>
                  <option value="ativo">Ativo</option>
                  <option value="inativo">Inativo</option>
                  <option value="ferias">Férias</option>
                  <option value="licenca">Licença</option>
                  <option value="desligado">Desligado</option>
                </select>
              </Field>
            </Row2>
            <Row2>
              <Field label="Salário Base (R$) *" error={fieldErrors.salario_base}>
                <input value={form.salario_base}
                  onChange={e => set('salario_base', maskSalary(e.target.value))}
                  placeholder="0,00" style={inp} />
              </Field>
              <Field label="Data de Demissão" error={fieldErrors.data_demissao}>
                <input value={form.data_demissao} placeholder="DD/MM/AAAA"
                  onChange={e => { setFieldErrors(prev => ({ ...prev, data_demissao: '' })); set('data_demissao', maskDate(e.target.value)) }}
                  onBlur={() => { const err = validateDataDemissao(form.data_demissao, form.data_admissao); if (err) setFieldErrors(prev => ({ ...prev, data_demissao: err })) }}
                  maxLength={10} style={inp} />
              </Field>
            </Row2>
          </Section>

          <Section title="Documentos Trabalhistas">
            <Row2>
              <Field label="PIS/PASEP" error={fieldErrors.pis_pasep}>
                <input value={maskPISPASEP(form.pis_pasep)} placeholder="000.00000.00-0"
                  onChange={e => { setFieldErrors(prev => ({ ...prev, pis_pasep: '' })); set('pis_pasep', e.target.value.replace(/\D/g, '')) }}
                  onBlur={() => { const err = validatePISPASEP(form.pis_pasep); if (err) setFieldErrors(prev => ({ ...prev, pis_pasep: err })) }}
                  maxLength={14} style={inp} />
              </Field>
              <Field label="Nº CTPS" error={fieldErrors.numero_ctps}>
                <input value={form.numero_ctps}
                  onChange={e => set('numero_ctps', e.target.value)} style={inp} />
              </Field>
            </Row2>
            <Field label="Série CTPS" error={fieldErrors.serie_ctps}>
              <input value={form.serie_ctps}
                onChange={e => set('serie_ctps', e.target.value)}
                style={{ ...inp, maxWidth: '160px' }} />
            </Field>
          </Section>

          <FormErrorBanner errors={fieldErrors} />
        </form>

        {/* Footer */}
        <div className="shrink-0 flex justify-end gap-3 px-6 py-4" style={{ borderTop: '1px solid #e2e8f0' }}>
          <button type="button" onClick={onClose} style={cancelBtn}>Cancelar</button>
          <button onClick={handleSubmit} disabled={saving}
            style={{ ...saveBtn, opacity: saving ? 0.7 : 1 }}>
            {saving ? 'Salvando…' : 'Salvar'}
          </button>
        </div>
      </aside>
    </>
  )
}

// ─── sub-componentes de layout ────────────────────────────────────────────────

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div>
    <p className="text-xs font-bold uppercase tracking-widest mb-3"
      style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
      {title}
    </p>
    <div className="flex flex-col gap-3">{children}</div>
  </div>
)

const Row2: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="grid grid-cols-2 gap-3">{children}</div>
)

const Field: React.FC<{ label: string; error?: string; children: React.ReactNode }> = ({ label, error, children }) => (
  <div className="flex flex-col gap-1">
    <label style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--color-text-muted)',
      textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-body)' }}>
      {label}
    </label>
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

export default FuncionarioForm
