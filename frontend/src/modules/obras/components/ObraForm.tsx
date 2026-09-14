import React, { useState, useEffect, useRef } from 'react'
import { X, Loader2 } from 'lucide-react'
import apiClient from '@/api/apiClient'
import type { Obra, ObraFormData, StatusObra, Empreendimento } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { minVigenciaISO, maxVigenciaISO, validateISO_Vigencia } from '@/utils/dates'

/**
 * O 400 de nome repetido (decisão do dono, 13/09/2026).
 *
 * A regra de unicidade **continua valendo** — o que mudou é que a recusa deixou
 * de ser uma parede: ela diz *qual* obra conflita, para a pessoa reconhecer se é
 * a mesma que ela já tem, e traz um nome livre pronto.
 */
interface ConflitoDeNome {
  conflito: {
    obra_id: number
    nome_obra: string
    status_obra: string
    data_inicio_prevista: string | null
    data_fim_prevista: string | null
    etapas: number
    /** O número que separa a obra de verdade da casca cadastrada e abandonada. */
    atividades: number
  }
  sugestao_nome: string
}

function extrairConflito(err: unknown): ConflitoDeNome | null {
  const data = (err as { response?: { data?: unknown } })?.response?.data as
    | Partial<ConflitoDeNome>
    | undefined
  if (!data?.conflito) return null
  return { conflito: data.conflito, sugestao_nome: data.sugestao_nome ?? '' }
}

function dataBR(iso: string | null) {
  if (!iso) return '—'
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}

function maskCurrency(v: string): string {
  const digits = v.replace(/\D/g, '').slice(0, 15)
  if (!digits) return ''
  const num = parseInt(digits, 10)
  return (num / 100).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function currencyToDecimal(v: string): string {
  return v.replace(/\./g, '').replace(',', '.')
}

const STATUS_OPTIONS: { value: StatusObra; label: string }[] = [
  { value: 'planejamento', label: 'Planejamento' },
  { value: 'em_execucao',  label: 'Em Execução'  },
  { value: 'concluida',    label: 'Concluída'    },
  { value: 'cancelada',    label: 'Cancelada'    },
]

const EMPTY: ObraFormData = {
  nome_obra: '',
  empreendimento: null,
  endereco: '',
  status_obra: 'planejamento',
  descricao: '',
  data_inicio_prevista: '',
  data_fim_prevista: '',
  orcamento_previsto: '',
}

interface Props {
  open: boolean
  onClose: () => void
  onSave: (data: ObraFormData) => Promise<void>
  initial?: Obra | null
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

export const ObraForm: React.FC<Props> = ({ open, onClose, onSave, initial }) => {
  const [form, setForm]             = useState<ObraFormData>(EMPTY)
  const [saving, setSaving]         = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  /** O 400 de nome repetido, quando o servidor manda o conflito e a sugestão. */
  const [conflito, setConflito] = useState<ConflitoDeNome | null>(null)
  const [empreendimentos, setEmpreendimentos] = useState<Empreendimento[]>([])

  const overlayRef         = useRef<HTMLDivElement>(null)
  const mousedownOnOverlay = useRef(false)

  // Carrega empreendimentos para o select
  useEffect(() => {
    if (!open) return
    apiClient.get('/empreendimentos/')
      .then(r => setEmpreendimentos(r.data.results ?? r.data))
      .catch(() => {})
  }, [open])

  useEffect(() => {
    if (!open) return
    if (initial) {
      setForm({
        nome_obra:             initial.nome_obra,
        empreendimento:        initial.empreendimento,
        endereco:              initial.endereco,
        status_obra:           initial.status_obra,
        descricao:             initial.descricao ?? '',
        data_inicio_prevista:  initial.data_inicio_prevista ?? '',
        data_fim_prevista:     initial.data_fim_prevista ?? '',
        orcamento_previsto:    initial.orcamento_previsto
          ? maskCurrency(String(Math.round(parseFloat(initial.orcamento_previsto) * 100)))
          : '',
      })
    } else {
      setForm(EMPTY)
    }
    setFieldErrors({})
  }, [initial, open])

  const set = (field: keyof ObraFormData, value: string | number | null) => {
    // Trocar o nome ou o empreendimento muda o escopo da unicidade — o aviso
    // anterior deixa de valer, e mantê-lo na tela acusaria um conflito que já
    // não existe.
    if (field === 'nome_obra' || field === 'empreendimento') setConflito(null)
    setForm(f => ({ ...f, [field]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (form.data_inicio_prevista && form.data_fim_prevista && form.data_fim_prevista < form.data_inicio_prevista) {
      setFieldErrors({ data_fim_prevista: 'Data de término deve ser posterior ao início.' }); return
    }
    setSaving(true)
    setFieldErrors({})
    try {
      const payload: ObraFormData = {
        ...form,
        orcamento_previsto: form.orcamento_previsto ? currencyToDecimal(form.orcamento_previsto) : '',
      }
      await onSave(payload)
      onClose()
    } catch (err) {
      setFieldErrors(parseApiErrors(err))
      setConflito(extrairConflito(err))
    } finally {
      setSaving(false)
    }
  }

  /** Aceita o nome que o servidor propôs — um clique, sem redigitar. */
  const aceitarSugestao = () => {
    if (!conflito?.sugestao_nome) return
    setForm(f => ({ ...f, nome_obra: conflito.sugestao_nome }))
    setConflito(null)
    setFieldErrors({})
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
            {initial ? 'Editar Obra' : 'Nova Obra'}
          </h2>
          <button onClick={onClose}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-5 px-6 py-6 flex-1">
          <div>
            <label style={labelStyle}>Nome da obra *</label>
            <input required style={inputStyle} value={form.nome_obra}
              onChange={e => set('nome_obra', e.target.value)}
              placeholder="Ex: Bloco A — Torre Leste"
              onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
              onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
            <FieldError msg={fieldErrors.nome_obra} />

            {conflito && (
              <div
                style={{
                  marginTop: 8, padding: '10px 12px', borderRadius: 8,
                  border: '1px solid #f0c36d', background: '#fdf6e3',
                  fontSize: 12.5, color: '#6b4d09',
                }}
              >
                <div style={{ fontWeight: 650, marginBottom: 6 }}>
                  Já existe uma obra com este nome neste empreendimento
                </div>

                {/* O cartão da obra que conflita. Sem ele a pessoa não consegue
                    decidir o que importa: é a mesma obra (e ela deveria usar a
                    que já existe) ou é outra de verdade? */}
                <div style={{ marginBottom: 8, lineHeight: 1.6 }}>
                  <div><b>{conflito.conflito.nome_obra}</b></div>
                  <div>
                    início {dataBR(conflito.conflito.data_inicio_prevista)} ·{' '}
                    {conflito.conflito.status_obra.replace('_', ' ')} ·{' '}
                    {conflito.conflito.atividades > 0
                      ? `${conflito.conflito.atividades} atividades no plano`
                      : 'sem plano montado'}
                  </div>
                </div>

                {conflito.sugestao_nome ? (
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span>É outra obra? Sugerimos:</span>
                    <code
                      style={{
                        background: '#fff', border: '1px solid #e8d9a8',
                        borderRadius: 5, padding: '2px 6px',
                      }}
                    >
                      {conflito.sugestao_nome}
                    </code>
                    <button
                      type="button"
                      onClick={aceitarSugestao}
                      style={{
                        border: '1px solid #d9a441', background: '#fff',
                        borderRadius: 6, padding: '3px 10px', cursor: 'pointer',
                        fontSize: 12, fontWeight: 600, color: '#6b4d09',
                      }}
                    >
                      Usar este nome
                    </button>
                  </div>
                ) : (
                  // O gerador desistiu (muitas homônimas). Avisar sem propor é
                  // melhor que propor um nome que o banco vai recusar.
                  <div>É outra obra? Escolha um nome que as separe.</div>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label style={labelStyle}>Empreendimento</label>
              <select
                style={{ ...inputStyle, cursor: 'pointer' }}
                value={form.empreendimento ?? ''}
                onChange={e => set('empreendimento', e.target.value ? parseInt(e.target.value, 10) : null)}
              >
                <option value="">Nenhum (obra avulsa)</option>
                {empreendimentos.map(emp => (
                  <option key={emp.empreendimento_id} value={emp.empreendimento_id}>
                    {emp.empreendimento}
                  </option>
                ))}
              </select>
              <FieldError msg={fieldErrors.empreendimento} />
            </div>
            <div>
              <label style={labelStyle}>Status</label>
              <select style={{ ...inputStyle, cursor: 'pointer' }}
                      value={form.status_obra}
                      onChange={e => set('status_obra', e.target.value)}>
                {STATUS_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <FieldError msg={fieldErrors.status_obra} />
            </div>
          </div>

          <div>
            <label style={labelStyle}>Endereço</label>
            <input style={inputStyle} value={form.endereco}
              onChange={e => set('endereco', e.target.value)}
              placeholder="Rua, nº, Bairro, Cidade - UF"
              onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
              onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
            <FieldError msg={fieldErrors.endereco} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label style={labelStyle}>Início previsto</label>
              <input type="date" style={inputStyle} value={form.data_inicio_prevista}
                min={minVigenciaISO()} max={maxVigenciaISO()}
                onChange={e => { set('data_inicio_prevista', e.target.value); setFieldErrors(p => ({ ...p, data_inicio_prevista: '' })) }}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => { e.currentTarget.style.borderColor = '#e2e8f0'; const err = validateISO_Vigencia(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_inicio_prevista: err })) }} />
              <FieldError msg={fieldErrors.data_inicio_prevista} />
            </div>
            <div>
              <label style={labelStyle}>Fim previsto</label>
              <input type="date" style={inputStyle} value={form.data_fim_prevista}
                min={minVigenciaISO()} max={maxVigenciaISO()}
                onChange={e => { set('data_fim_prevista', e.target.value); setFieldErrors(p => ({ ...p, data_fim_prevista: '' })) }}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => { e.currentTarget.style.borderColor = '#e2e8f0'; const err = validateISO_Vigencia(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_fim_prevista: err })) }} />
              <FieldError msg={fieldErrors.data_fim_prevista} />
            </div>
          </div>

          <div>
            <label style={labelStyle}>Orçamento previsto</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm select-none"
                    style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                R$
              </span>
              <input
                style={{ ...inputStyle, paddingLeft: '36px' }}
                value={form.orcamento_previsto}
                onChange={e => set('orcamento_previsto', maskCurrency(e.target.value))}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
                placeholder="0,00"
                inputMode="numeric"
              />
            </div>
            <FieldError msg={fieldErrors.orcamento_previsto} />
          </div>

          <div>
            <label style={labelStyle}>Descrição</label>
            <textarea rows={4} style={{ ...inputStyle, resize: 'vertical' }}
              value={form.descricao}
              onChange={e => set('descricao', e.target.value)}
              placeholder="Descrição da obra..."
              onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
              onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')} />
            <FieldError msg={fieldErrors.descricao} />
          </div>

          <FormErrorBanner errors={fieldErrors} />

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
              {saving ? <><Loader2 size={14} className="animate-spin" />Salvando…</> : 'Salvar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default ObraForm
