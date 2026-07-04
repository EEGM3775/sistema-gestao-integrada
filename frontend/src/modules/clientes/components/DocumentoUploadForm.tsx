import React, { useState, useRef, useEffect } from 'react'
import { X, UploadCloud } from 'lucide-react'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'

const TIPO_DOCUMENTO_OPTIONS = [
  { value: 'rg',                     label: 'RG' },
  { value: 'cpf',                    label: 'CPF' },
  { value: 'cnh',                    label: 'CNH' },
  { value: 'comprovante_residencia', label: 'Comprovante de Residência' },
  { value: 'certidao_casamento',     label: 'Certidão de Casamento' },
  { value: 'outros',                 label: 'Outros' },
]

interface Props {
  open: boolean
  clienteId: number
  onClose: () => void
  onSave: (form: FormData) => Promise<void>
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

const DocumentoUploadForm: React.FC<Props> = ({ open, clienteId, onClose, onSave }) => {
  const [tipo, setTipo]         = useState('outros')
  const [nome, setNome]         = useState('')
  const [file, setFile]         = useState<File | null>(null)
  const [saving, setSaving]     = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const fileRef                 = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setTipo('outros'); setNome(''); setFile(null); setFieldErrors({})
  }, [open])

  if (!open) return null

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null
    setFile(f)
    if (f && !nome) setNome(f.name)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) { setFieldErrors({ arquivo: 'Selecione um arquivo.' }); return }
    setSaving(true)
    setFieldErrors({})
    try {
      const fd = new FormData()
      fd.append('cliente', String(clienteId))
      fd.append('tipo_documento', tipo)
      fd.append('nome_documento', nome || file.name)
      fd.append('arquivo', file)
      await onSave(fd)
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
        style={{ width: '400px', background: '#FFFFFF', boxShadow: '-4px 0 24px rgba(0,0,0,0.12)', overflow: 'hidden' }}>

        <div className="flex items-center justify-between px-6 py-4 shrink-0"
          style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: '1rem', color: 'var(--color-brand)' }}>
            Anexar Documento
          </h2>
          <button onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        <form id="doc-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-4">
          <FormErrorBanner errors={fieldErrors} />

          <div>
            <label style={labelCls}>Tipo de documento *</label>
            <select style={inputCls} value={tipo} onChange={e => setTipo(e.target.value)}>
              {TIPO_DOCUMENTO_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <FieldError msg={fieldErrors.tipo_documento} />
          </div>

          <div>
            <label style={labelCls}>Nome / descrição *</label>
            <input required style={inputCls} value={nome}
              placeholder="Ex: RG - João Silva"
              onChange={e => setNome(e.target.value)} />
            <FieldError msg={fieldErrors.nome_documento} />
          </div>

          {/* Drop zone */}
          <div>
            <label style={labelCls}>Arquivo *</label>
            <div
              className="flex flex-col items-center justify-center gap-2 rounded-xl cursor-pointer transition-colors"
              style={{
                border: '2px dashed #e2e8f0', padding: '24px 16px',
                background: file ? '#f0fdf4' : '#f8fafc',
                borderColor: file ? '#86efac' : '#e2e8f0',
              }}
              onClick={() => fileRef.current?.click()}
            >
              <UploadCloud size={28} style={{ color: file ? '#16a34a' : '#94a3b8' }} />
              {file ? (
                <p className="text-sm font-medium text-center" style={{ color: '#16a34a', fontFamily: 'var(--font-body)' }}>
                  {file.name}
                </p>
              ) : (
                <>
                  <p className="text-sm font-medium" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                    Clique para selecionar
                  </p>
                  <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                    PDF, JPG, PNG, DOCX até 10 MB
                  </p>
                </>
              )}
            </div>
            <input ref={fileRef} type="file" className="hidden"
              accept=".pdf,.jpg,.jpeg,.png,.docx,.doc"
              onChange={handleFile} />
            <FieldError msg={fieldErrors.arquivo} />
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
          <button form="doc-form" type="submit" disabled={saving || !file}
            className="px-5 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none',
              cursor: (saving || !file) ? 'not-allowed' : 'pointer',
              opacity: (saving || !file) ? 0.6 : 1,
              fontFamily: 'var(--font-body)' }}>
            {saving ? 'Enviando…' : 'Anexar documento'}
          </button>
        </div>
      </div>
    </>
  )
}

export default DocumentoUploadForm
