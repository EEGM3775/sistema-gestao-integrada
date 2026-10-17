import React, { useState, useEffect } from 'react'
import { Lock } from 'lucide-react'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import type { PerfilFormData, CatalogoResposta } from '../types'

interface Props {
  open: boolean
  onClose: () => void
  onSave: (fd: PerfilFormData) => Promise<void>
  initialData?: PerfilFormData | null   // valores para preencher (editar OU clonar)
  heading: string                        // título do modal
  catalogo: CatalogoResposta
}

const MODULO_LABEL: Record<string, string> = {
  rh: 'Recursos Humanos',
  erp_financeiro: 'ERP Financeiro',
  crm: 'CRM',
  drone: 'Drone',
  base: 'Base — obras, cadastros, agenda, IA',
  plataforma: 'Plataforma & Governança',
}

const EMPTY: PerfilFormData = { nome: '', descricao: '', permissoes: [] }

const PersonaForm: React.FC<Props> = ({ open, onClose, onSave, initialData, heading, catalogo }) => {
  const [form, setForm] = useState<PerfilFormData>(EMPTY)
  const [saving, setSaving] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    if (open) {
      setForm(initialData
        ? { nome: initialData.nome, descricao: initialData.descricao ?? '', permissoes: [...initialData.permissoes] }
        : EMPTY)
      setFieldErrors({})
    }
  }, [open, initialData])

  const toggle = (id: number) =>
    setForm(prev => ({
      ...prev,
      permissoes: prev.permissoes.includes(id)
        ? prev.permissoes.filter(x => x !== id)
        : [...prev.permissoes, id],
    }))

  const toggleModulo = (ids: number[], allOn: boolean) =>
    setForm(prev => ({
      ...prev,
      permissoes: allOn
        ? prev.permissoes.filter(x => !ids.includes(x))
        : [...new Set([...prev.permissoes, ...ids])],
    }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.nome.trim()) { setFieldErrors({ nome: 'Campo obrigatório.' }); return }
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

  if (!open) return null
  const selected = new Set(form.permissoes)

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={onClose} />
      <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-2xl w-full max-w-2xl flex flex-col"
        style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)', maxHeight: '88vh' }}>

        <div className="p-6 pb-4" style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 className="text-lg font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            {heading}
          </h2>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
            Componha as permissões deste papel. Módulos não contratados ficam bloqueados.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col min-h-0 flex-1">
          <div className="px-6 py-4 overflow-y-auto flex flex-col gap-4">
            <Field label="Nome do papel *" error={fieldErrors.nome}>
              <input value={form.nome} onChange={e => setForm(p => ({ ...p, nome: e.target.value }))}
                placeholder="Ex: Analista Financeiro" style={inputStyle} />
            </Field>
            <Field label="Descrição" error={fieldErrors.descricao}>
              <input value={form.descricao} onChange={e => setForm(p => ({ ...p, descricao: e.target.value }))}
                placeholder="Para que serve este papel" style={inputStyle} />
            </Field>

            <div className="flex flex-col gap-3 mt-1">
              {catalogo.modulos.map(mod => {
                const ids = mod.permissoes.map(p => p.id)
                const marcadas = ids.filter(id => selected.has(id)).length
                const todas = marcadas === ids.length && ids.length > 0
                const bloqueado = !mod.atribuivel
                return (
                  <div key={mod.modulo} className="rounded-xl overflow-hidden"
                    style={{ border: '1px solid #e2e8f0', opacity: bloqueado ? 0.55 : 1 }}>
                    <div className="flex items-center justify-between px-3 py-2"
                      style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                      <span className="text-sm font-bold flex items-center gap-1.5"
                        style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                        {bloqueado && <Lock size={13} />}
                        {MODULO_LABEL[mod.modulo] ?? mod.modulo}
                        <span style={{ fontWeight: 500, color: 'var(--color-text-muted)' }}>
                          ({marcadas}/{ids.length})
                        </span>
                      </span>
                      {!bloqueado && (
                        <button type="button" onClick={() => toggleModulo(ids, todas)}
                          className="text-xs font-semibold" style={linkBtn}>
                          {todas ? 'Limpar' : 'Marcar todas'}
                        </button>
                      )}
                    </div>
                    {bloqueado ? (
                      <p className="text-xs px-3 py-2" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                        Módulo não contratado por este tenant.
                      </p>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 p-3">
                        {mod.permissoes.map(perm => (
                          <label key={perm.id} className="flex items-center gap-2 cursor-pointer py-0.5"
                            title={perm.nome}>
                            <input type="checkbox" checked={selected.has(perm.id)}
                              onChange={() => toggle(perm.id)}
                              style={{ accentColor: 'var(--color-brand)', width: 15, height: 15 }} />
                            <span className="text-sm truncate" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                              {perm.nome}
                            </span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            <FormErrorBanner errors={fieldErrors} />
          </div>

          <div className="flex items-center justify-between gap-3 px-6 py-4" style={{ borderTop: '1px solid #e2e8f0' }}>
            <span className="text-sm" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              {form.permissoes.length} permiss{form.permissoes.length === 1 ? 'ão' : 'ões'} selecionada{form.permissoes.length === 1 ? '' : 's'}
            </span>
            <div className="flex gap-3">
              <button type="button" onClick={onClose} style={cancelBtnStyle}>Cancelar</button>
              <button type="submit" disabled={saving} style={{ ...saveBtnStyle, opacity: saving ? 0.7 : 1 }}>
                {saving ? 'Salvando…' : 'Salvar papel'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </>
  )
}

const Field: React.FC<{ label: string; error?: string; children: React.ReactNode }> = ({ label, error, children }) => (
  <div className="flex flex-col gap-1">
    <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)',
      textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'var(--font-body)' }}>
      {label}
    </label>
    {children}
    <FieldError msg={error} />
  </div>
)

const inputStyle: React.CSSProperties = {
  padding: '8px 12px', border: '1.5px solid #e2e8f0', borderRadius: '8px',
  fontSize: '0.875rem', fontFamily: 'var(--font-body)', color: 'var(--color-text)',
  background: '#FFFFFF', outline: 'none', width: '100%',
}
const cancelBtnStyle: React.CSSProperties = {
  padding: '8px 16px', borderRadius: '8px', border: '1.5px solid #e2e8f0',
  background: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)',
  fontSize: '0.875rem', color: 'var(--color-text-muted)',
}
const saveBtnStyle: React.CSSProperties = {
  padding: '8px 20px', borderRadius: '8px', border: 'none',
  background: 'var(--color-brand)', color: '#FFFFFF',
  cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: '0.875rem', fontWeight: 600,
}
const linkBtn: React.CSSProperties = {
  background: 'none', border: 'none', cursor: 'pointer',
  color: 'var(--color-brand)', fontFamily: 'var(--font-body)',
}

export default PersonaForm
