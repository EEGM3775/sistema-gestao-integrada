import React, { useState, useEffect, useRef } from 'react'
import { Paperclip, ExternalLink } from 'lucide-react'
import type { ASOFuncionario, ASOFuncionarioFormData, TipoExameASO, StatusASO } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { minVigenciaISO, maxTodayISO, maxVigenciaISO, validateISO_ExameASO, validateISO_ValidadeASO } from '@/utils/dates'

interface Props {
  open: boolean
  onClose: () => void
  onSave: (fd: ASOFuncionarioFormData, arquivo: File | null) => Promise<void>
  initial?: ASOFuncionario | null
  funcionarioId: number
}

const EMPTY = (fid: number): ASOFuncionarioFormData => ({
  funcionario: fid,
  tipo_exame: '',
  status: 'ativo',
  data_exame: '',
  data_validade: '',
  observacoes: '',
})

function toForm(a: ASOFuncionario): ASOFuncionarioFormData {
  return {
    funcionario: a.funcionario,
    tipo_exame: a.tipo_exame,
    status: a.status,
    data_exame: a.data_exame,
    data_validade: a.data_validade ?? '',
    observacoes: a.observacoes ?? '',
  }
}

const ASOForm: React.FC<Props> = ({ open, onClose, onSave, initial, funcionarioId }) => {
  const [form, setForm]               = useState<ASOFuncionarioFormData>(EMPTY(funcionarioId))
  const [arquivo, setArquivo]         = useState<File | null>(null)
  const [saving, setSaving]           = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const fileInputRef                  = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setForm(initial ? toForm(initial) : EMPTY(funcionarioId))
      setArquivo(null)
      setFieldErrors({})
    }
  }, [open, initial, funcionarioId])

  const set = <K extends keyof ASOFuncionarioFormData>(k: K, v: ASOFuncionarioFormData[K]) =>
    setForm(prev => ({ ...prev, [k]: v }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true); setFieldErrors({})
    try { await onSave(form, arquivo); onClose() }
    catch (err) { setFieldErrors(parseApiErrors(err)) }
    finally { setSaving(false) }
  }

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.45)' }} onClick={onClose} />
      <aside className="fixed top-0 right-0 h-full z-50 flex flex-col"
        style={{ width: 'min(480px, 100vw)', background: '#FFFFFF', boxShadow: '-4px 0 30px rgba(0,0,0,0.15)' }}>
        <div className="flex items-center justify-between px-6 py-5 shrink-0" style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 className="text-lg font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            {initial ? 'Editar ASO' : 'Novo ASO'}
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', fontSize: '1.25rem' }}>✕</button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-4">
          <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
            Cada exame ocupacional (admissional, periódico ou demissional) é registrado individualmente —
            mantenha um histórico completo cadastrando um novo ASO a cada exame realizado.
          </p>

          <Row2>
            <Field label="Tipo de Exame *" error={fieldErrors.tipo_exame}>
              <select required value={form.tipo_exame}
                onChange={e => set('tipo_exame', e.target.value as TipoExameASO | '')} style={inp}>
                <option value="">Selecione…</option>
                <option value="admissional">Admissional</option>
                <option value="periodico">Periódico</option>
                <option value="demissional">Demissional</option>
              </select>
            </Field>
            <Field label="Status" error={fieldErrors.status}>
              <select value={form.status} onChange={e => set('status', e.target.value as StatusASO)} style={inp}>
                <option value="ativo">Ativo</option>
                <option value="pendente">Pendente</option>
                <option value="inativo">Inativo</option>
                <option value="cancelado">Cancelado</option>
              </select>
            </Field>
          </Row2>

          <Row2>
            <Field label="Data do Exame *" error={fieldErrors.data_exame}>
              <input required type="date" value={form.data_exame}
                min={minVigenciaISO()} max={maxTodayISO()}
                onChange={e => { set('data_exame', e.target.value); setFieldErrors(p => ({ ...p, data_exame: '' })) }}
                onBlur={e => { const err = validateISO_ExameASO(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_exame: err })) }}
                style={inp} />
            </Field>
            <Field label="Validade" error={fieldErrors.data_validade}>
              <input type="date" value={form.data_validade}
                min={minVigenciaISO()} max={maxVigenciaISO()}
                onChange={e => { set('data_validade', e.target.value); setFieldErrors(p => ({ ...p, data_validade: '' })) }}
                onBlur={e => { const err = validateISO_ValidadeASO(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_validade: err })) }}
                style={inp} />
            </Field>
          </Row2>

          <Field label="Documento ASO" error={fieldErrors.arquivo}>
            <input ref={fileInputRef} type="file" accept=".pdf,image/*"
              onChange={e => setArquivo(e.target.files?.[0] ?? null)}
              style={{ display: 'none' }} />
            <button type="button" onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-2"
              style={{ ...inp, cursor: 'pointer', textAlign: 'left',
                color: arquivo ? 'var(--color-text)' : 'var(--color-text-muted)', background: '#f8fafc' }}>
              <Paperclip size={14} style={{ flexShrink: 0 }} />
              {arquivo ? arquivo.name : (initial?.arquivo ? 'Substituir arquivo…' : 'Escolher arquivo (PDF ou imagem)…')}
            </button>
            {initial?.arquivo && !arquivo && (
              <a href={initial.arquivo} target="_blank" rel="noreferrer"
                className="flex items-center gap-1 text-xs mt-1"
                style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                <ExternalLink size={12} /> Ver documento atual
              </a>
            )}
          </Field>

          <Field label="Observações" error={fieldErrors.observacoes}>
            <textarea value={form.observacoes} onChange={e => set('observacoes', e.target.value)} rows={3} style={{ ...inp, resize: 'vertical' }} />
          </Field>

          <FormErrorBanner errors={fieldErrors} />
        </form>

        <div className="shrink-0 flex justify-end gap-3 px-6 py-4" style={{ borderTop: '1px solid #e2e8f0' }}>
          <button type="button" onClick={onClose} style={cancelBtn}>Cancelar</button>
          <button onClick={handleSubmit} disabled={saving} style={{ ...saveBtn, opacity: saving ? 0.7 : 1 }}>
            {saving ? 'Salvando…' : initial ? 'Salvar ASO' : 'Registrar ASO'}
          </button>
        </div>
      </aside>
    </>
  )
}

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

export default ASOForm
