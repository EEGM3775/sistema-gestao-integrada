import React, { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import type { SituacaoUnidade, TipoUnidade, Unidade, UnidadeFormData } from '@/types'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'

/**
 * Cadastro da unidade — o que se vende, com preço de tabela.
 *
 * A identificação (quadra/lote/bloco/andar/apto) mora aqui e **só aqui**: a
 * aquisição do cliente passou a escolher uma unidade já cadastrada, em vez de
 * digitar de novo um rótulo livre que podia divergir. Loteamento preenche
 * quadra/lote; vertical preenche bloco/andar/apto; ao menos um é obrigatório.
 */
interface Props {
  open: boolean
  empreendimentoId: number
  onClose: () => void
  onSave: (data: UnidadeFormData) => Promise<void>
  initial?: Unidade | null
}

const TIPOS: { value: TipoUnidade; label: string }[] = [
  { value: 'lote', label: 'Lote' },
  { value: 'apartamento', label: 'Apartamento' },
  { value: 'casa', label: 'Casa' },
  { value: 'sala', label: 'Sala comercial' },
  { value: 'outro', label: 'Outro' },
]

const SITUACOES: { value: SituacaoUnidade; label: string }[] = [
  { value: 'disponivel', label: 'Disponível' },
  { value: 'reservada', label: 'Reservada' },
  { value: 'indisponivel', label: 'Indisponível' },
]

/** Os quatro lados na ordem do memorial descritivo. A frente vem primeiro
 *  porque é a rua — é dela que sai o endereço e é ela que o comprador
 *  reconhece quando visita o lote. */
const LADOS: { medida: keyof UnidadeFormData; confrontante: keyof UnidadeFormData; rotulo: string }[] = [
  { medida: 'medida_frente',           confrontante: 'confrontante_frente',           rotulo: 'Frente' },
  { medida: 'medida_fundo',            confrontante: 'confrontante_fundo',            rotulo: 'Fundo' },
  { medida: 'medida_lateral_direita',  confrontante: 'confrontante_lateral_direita',  rotulo: 'Lateral direita' },
  { medida: 'medida_lateral_esquerda', confrontante: 'confrontante_lateral_esquerda', rotulo: 'Lateral esquerda' },
]

const EMPTY = (empreendimentoId: number): UnidadeFormData => ({
  empreendimento: empreendimentoId,
  quadra: '', lote: '', bloco_torre: '', andar: '', apto: '',
  tipo: 'lote', situacao: 'disponivel',
  valor_base: '', area_privativa: '', area_total: '', endereco: '',
  medida_frente: '', medida_fundo: '', medida_lateral_direita: '', medida_lateral_esquerda: '',
  confrontante_frente: '', confrontante_fundo: '',
  confrontante_lateral_direita: '', confrontante_lateral_esquerda: '',
  observacoes: '',
})

function toForm(u: Unidade): UnidadeFormData {
  return {
    empreendimento: u.empreendimento,
    quadra: u.quadra, lote: u.lote, bloco_torre: u.bloco_torre,
    andar: u.andar, apto: u.apto,
    tipo: u.tipo, situacao: u.situacao,
    valor_base: u.valor_base,
    area_privativa: u.area_privativa ?? '',
    area_total: u.area_total ?? '',
    endereco: u.endereco,
    medida_frente: u.medida_frente ?? '',
    medida_fundo: u.medida_fundo ?? '',
    medida_lateral_direita: u.medida_lateral_direita ?? '',
    medida_lateral_esquerda: u.medida_lateral_esquerda ?? '',
    confrontante_frente: u.confrontante_frente,
    confrontante_fundo: u.confrontante_fundo,
    confrontante_lateral_direita: u.confrontante_lateral_direita,
    confrontante_lateral_esquerda: u.confrontante_lateral_esquerda,
    observacoes: u.observacoes,
  }
}

function maskCurrency(v: string) {
  const digits = v.replace(/\D/g, '')
  if (!digits) return ''
  return (parseInt(digits, 10) / 100).toLocaleString('pt-BR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })
}

const currencyToDecimal = (v: string) => v.replace(/\./g, '').replace(',', '.')

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
    textTransform: 'uppercase', color: 'var(--color-text-muted)',
    marginTop: '8px', marginBottom: '2px', fontFamily: 'var(--font-body)',
  }}>{children}</p>
)

const UnidadeForm: React.FC<Props> = ({ open, empreendimentoId, onClose, onSave, initial }) => {
  const [form, setForm] = useState<UnidadeFormData>(EMPTY(empreendimentoId))
  const [displayValor, setDisplayValor] = useState('')
  const [saving, setSaving] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  useEffect(() => {
    if (initial) {
      setForm(toForm(initial))
      setDisplayValor(
        parseFloat(initial.valor_base).toLocaleString('pt-BR', { minimumFractionDigits: 2 }),
      )
    } else {
      setForm(EMPTY(empreendimentoId))
      setDisplayValor('')
    }
    setFieldErrors({})
  }, [initial, open, empreendimentoId])

  if (!open) return null

  const set = (campo: keyof UnidadeFormData, valor: string | number) =>
    setForm(anterior => ({ ...anterior, [campo]: valor }))

  const identificada = ['quadra', 'lote', 'bloco_torre', 'andar', 'apto']
    .some(campo => String(form[campo as keyof UnidadeFormData] || '').trim())

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!identificada) {
      setFieldErrors({ quadra: 'Preencha ao menos um nível da identificação.' })
      return
    }
    setSaving(true)
    setFieldErrors({})
    try {
      // Medida em branco é "não medido", não zero — o DecimalField é nulável e
      // string vazia não é decimal válido para o DRF.
      const medidas = Object.fromEntries(
        LADOS.map(l => [l.medida, String(form[l.medida] || '').trim() || null]),
      )
      await onSave({ ...form, ...medidas, empreendimento: empreendimentoId } as UnidadeFormData)
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
        style={{ width: '440px', background: '#FFFFFF', boxShadow: '-4px 0 24px rgba(0,0,0,0.12)', overflow: 'hidden' }}>

        <div className="flex items-center justify-between px-6 py-4 shrink-0"
          style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: '1rem', color: 'var(--color-brand)' }}>
            {initial ? 'Editar Unidade' : 'Nova Unidade'}
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        <form id="unidade-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-3">
          <FormErrorBanner errors={fieldErrors} />

          <SectionTitle>Identificação</SectionTitle>
          <p style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: -6 }}>
            Loteamento usa quadra e lote; prédio usa bloco, andar e apto. Ao menos um.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={labelCls}>Quadra</label>
              <input style={inputCls} value={form.quadra} onChange={e => set('quadra', e.target.value)} />
              <FieldError msg={fieldErrors.quadra} />
            </div>
            <div>
              <label style={labelCls}>Lote</label>
              <input style={inputCls} value={form.lote} onChange={e => set('lote', e.target.value)} />
              <FieldError msg={fieldErrors.lote} />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label style={labelCls}>Bloco/Torre</label>
              <input style={inputCls} value={form.bloco_torre} onChange={e => set('bloco_torre', e.target.value)} />
              <FieldError msg={fieldErrors.bloco_torre} />
            </div>
            <div>
              <label style={labelCls}>Andar</label>
              <input style={inputCls} value={form.andar} onChange={e => set('andar', e.target.value)} />
              <FieldError msg={fieldErrors.andar} />
            </div>
            <div>
              <label style={labelCls}>Apto/Nº</label>
              <input style={inputCls} value={form.apto} onChange={e => set('apto', e.target.value)} />
              <FieldError msg={fieldErrors.apto} />
            </div>
          </div>

          <SectionTitle>Comercial</SectionTitle>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={labelCls}>Valor de tabela (R$) *</label>
              <input required style={inputCls} value={displayValor} placeholder="0,00"
                onChange={e => {
                  const mascarado = maskCurrency(e.target.value)
                  setDisplayValor(mascarado)
                  set('valor_base', currencyToDecimal(mascarado))
                }} />
              <FieldError msg={fieldErrors.valor_base} />
            </div>
            <div>
              <label style={labelCls}>Tipo</label>
              <select style={inputCls} value={form.tipo} onChange={e => set('tipo', e.target.value)}>
                {TIPOS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label style={labelCls}>Situação</label>
              {/* "Vendida" não é escolha: sai da existência de uma aquisição. */}
              <select style={inputCls} value={form.situacao}
                disabled={initial?.situacao === 'vendida'}
                onChange={e => set('situacao', e.target.value)}>
                {initial?.situacao === 'vendida'
                  ? <option value="vendida">Vendida</option>
                  : SITUACOES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
            <div>
              <label style={labelCls}>Área privativa (m²)</label>
              <input style={inputCls} value={form.area_privativa} inputMode="decimal"
                onChange={e => set('area_privativa', e.target.value.replace(',', '.'))} />
              <FieldError msg={fieldErrors.area_privativa} />
            </div>
            <div>
              <label style={labelCls}>Área total (m²)</label>
              <input style={inputCls} value={form.area_total} inputMode="decimal"
                onChange={e => set('area_total', e.target.value.replace(',', '.'))} />
              <FieldError msg={fieldErrors.area_total} />
            </div>
          </div>

          {initial?.situacao === 'vendida' && initial.cliente_nome && (
            <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
              Vendida para <strong>{initial.cliente_nome}</strong>. Para liberar a unidade,
              cancele a aquisição na ficha do cliente.
            </p>
          )}

          <SectionTitle>Localização</SectionTitle>
          <div>
            <label style={labelCls}>Endereço da unidade</label>
            <input style={inputCls} value={form.endereco} onChange={e => set('endereco', e.target.value)} />
            <FieldError msg={fieldErrors.endereco} />
          </div>

          <SectionTitle>Medidas e confrontações</SectionTitle>
          <p style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: -6 }}>
            O que vai ao contrato e à matrícula: quanto mede cada lado e com quem divide.
            A frente é, em geral, a rua. Lote irregular descreve o excedente em observações.
          </p>
          {LADOS.map(lado => (
            <div key={lado.medida} className="grid gap-3" style={{ gridTemplateColumns: '110px 1fr' }}>
              <div>
                <label style={labelCls}>{lado.rotulo} (m)</label>
                <input style={inputCls} inputMode="decimal" placeholder="0,00"
                  value={String(form[lado.medida] ?? '')}
                  onChange={e => set(lado.medida, e.target.value.replace(',', '.'))} />
                <FieldError msg={fieldErrors[lado.medida]} />
              </div>
              <div>
                <label style={labelCls}>Confronta com</label>
                <input style={inputCls}
                  placeholder={lado.medida === 'medida_frente' ? 'Rua, avenida…' : 'Lote, área comum, terceiro…'}
                  value={String(form[lado.confrontante] ?? '')}
                  onChange={e => set(lado.confrontante, e.target.value)} />
                <FieldError msg={fieldErrors[lado.confrontante]} />
              </div>
            </div>
          ))}
          {initial?.descricao_confrontacoes && (
            <p style={{
              fontSize: '0.72rem', color: 'var(--color-text-muted)', lineHeight: 1.5,
              background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '8px 10px',
            }}>
              <strong style={{ display: 'block', marginBottom: 2 }}>Memorial</strong>
              {initial.descricao_confrontacoes}
            </p>
          )}
          <div>
            <label style={labelCls}>Observações</label>
            <textarea style={{ ...inputCls, minHeight: '64px', resize: 'vertical' }}
              value={form.observacoes} onChange={e => set('observacoes', e.target.value)} />
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
          <button form="unidade-form" type="submit" disabled={saving}
            className="px-5 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none',
              cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1,
              fontFamily: 'var(--font-body)' }}>
            {saving ? 'Salvando…' : initial ? 'Salvar' : 'Cadastrar unidade'}
          </button>
        </div>
      </div>
    </>
  )
}

export default UnidadeForm
