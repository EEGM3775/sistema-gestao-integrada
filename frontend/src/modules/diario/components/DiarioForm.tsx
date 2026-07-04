import React, { useState, useEffect, useRef } from 'react'
import { X, Loader2, ImagePlus, AlertTriangle } from 'lucide-react'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import type { ContribuirData, Obra } from '@/types'

const makeEmpty = (obraId: number | null): ContribuirData => ({
  obra: obraId,
  texto: '',
  eh_ocorrencia: false,
  condicoes_climaticas: '',
  arquivo: null,
})

interface Props {
  open: boolean
  obras: Obra[]
  defaultObraId?: number | null
  onClose: () => void
  onSave: (data: ContribuirData) => Promise<void>
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '10px 12px', borderRadius: '8px',
  border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)',
  fontSize: '0.875rem', color: 'var(--color-text)', background: '#FFFFFF', outline: 'none',
}
const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: '0.8rem', fontWeight: 600,
  marginBottom: '4px', fontFamily: 'var(--font-body)', color: 'var(--color-brand)',
}

export const DiarioForm: React.FC<Props> = ({ open, obras, defaultObraId, onClose, onSave }) => {
  const [form, setForm]     = useState<ContribuirData>(makeEmpty(defaultObraId ?? null))
  const [saving, setSaving]           = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  const overlayRef         = useRef<HTMLDivElement>(null)
  const mousedownOnOverlay = useRef(false)

  useEffect(() => {
    if (!open) return
    setForm(makeEmpty(defaultObraId ?? null))
    setFieldErrors({})
  }, [open, defaultObraId])

  const set = <K extends keyof ContribuirData>(field: K, value: ContribuirData[K]) =>
    setForm(f => ({ ...f, [field]: value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.obra) { setFieldErrors({ obra: 'Selecione a obra.' }); return }
    if (!form.texto.trim() && !form.arquivo) { setFieldErrors({ texto: 'Envie ao menos um texto ou uma foto.' }); return }
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

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex justify-end"
      style={{ background: 'rgba(0,0,0,0.4)' }}
      onMouseDown={e => { mousedownOnOverlay.current = e.target === overlayRef.current }}
      onClick={() => { if (mousedownOnOverlay.current) onClose() }}
    >
      <div
        className="relative h-full w-full max-w-lg flex flex-col overflow-y-auto"
        style={{ background: '#FFFFFF', boxShadow: '-4px 0 24px rgba(0,0,0,0.15)' }}
        onMouseDown={e => e.stopPropagation()}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 shrink-0"
             style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 className="text-lg font-bold"
              style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            Registrar no diário do dia
          </h2>
          <button onClick={onClose}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-5 px-6 py-6 flex-1">
          <FormErrorBanner errors={fieldErrors} />

          <div>
            <label style={labelStyle}>Obra *</label>
            <select
              required
              style={{ ...inputStyle, cursor: 'pointer' }}
              value={form.obra ?? ''}
              onChange={e => set('obra', e.target.value ? parseInt(e.target.value, 10) : null)}
            >
              <option value="">Selecione…</option>
              {obras.map(o => (
                <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>
              ))}
            </select>
            <FieldError msg={fieldErrors.obra} />
            <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              Seu registro entra no diário de <strong>hoje</strong> dessa obra (um diário por obra/dia).
            </p>
          </div>

          <div>
            <label style={labelStyle}>O que registrar</label>
            <textarea rows={5} style={{ ...inputStyle, resize: 'vertical' }}
              value={form.texto}
              onChange={e => set('texto', e.target.value)}
              placeholder="Descreva a atividade, observação ou ocorrência…"
              onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
              onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
            <FieldError msg={fieldErrors.texto} />
          </div>

          <label className="flex items-center gap-2 text-sm cursor-pointer"
                 style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}>
            <input type="checkbox" checked={form.eh_ocorrencia}
                   onChange={e => set('eh_ocorrencia', e.target.checked)} />
            <AlertTriangle size={15} style={{ color: '#9a3412' }} />
            Marcar como problema/ocorrência
          </label>

          <div>
            <label style={labelStyle}>Foto (opcional — dispara a análise de IA)</label>
            <label
              className="flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer text-sm"
              style={{ border: '1.5px dashed #cbd5e1', color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}
            >
              <ImagePlus size={16} />
              {form.arquivo ? form.arquivo.name : 'Escolher imagem…'}
              <input type="file" accept="image/*" className="hidden"
                     onChange={e => set('arquivo', e.target.files?.[0] ?? null)} />
            </label>
            <FieldError msg={fieldErrors.arquivo} />
          </div>

          <div>
            <label style={labelStyle}>Condições climáticas do dia (opcional)</label>
            <input style={inputStyle} value={form.condicoes_climaticas}
              onChange={e => set('condicoes_climaticas', e.target.value)}
              placeholder="Ex: Ensolarado, chuva pela manhã…"
              onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
              onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
            <FieldError msg={fieldErrors.condicoes_climaticas} />
          </div>

          <div className="flex gap-3 mt-auto pt-4" style={{ borderTop: '1px solid #e2e8f0' }}>
            <button type="button" onClick={onClose}
              className="flex-1 py-2.5 rounded-lg text-sm font-semibold"
              style={{ background: 'transparent', border: '1.5px solid #e2e8f0',
                       color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', cursor: 'pointer' }}>
              Cancelar
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold"
              style={{ background: saving ? 'rgba(10,42,91,0.5)' : 'var(--color-brand)',
                       color: '#FFFFFF', border: 'none',
                       fontFamily: 'var(--font-body)', cursor: saving ? 'not-allowed' : 'pointer' }}>
              {saving ? <><Loader2 size={14} className="animate-spin" />Enviando…</> : 'Registrar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default DiarioForm
