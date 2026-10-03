import { useState } from 'react'
import { RotateCcw, X } from 'lucide-react'
import { formatBRL, apiDecimalToCents } from '@/utils/money'
import { parseApiErrors } from '@/utils/formErrors'
import { buttonSecondaryStyle } from './forms/formStyles'

/**
 * Estornar a baixa (item 57) — o "cancelar pagamento" do Omie e o
 * "cancelamento de baixa" do Protheus. A conta volta a "Aberto" e o caixa
 * ganha um lançamento de estorno; a baixa original continua no histórico.
 */
export function EstornarBaixaDialog({ valorPago, onConfirmar, onFechar, pendente }: {
  valorPago: string
  onConfirmar: (motivo: string) => Promise<unknown>
  onFechar: () => void
  pendente: boolean
}) {
  const [motivo, setMotivo] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const confirmar = async () => {
    setErro(null)
    try {
      await onConfirmar(motivo.trim())
      onFechar()
    } catch (e) {
      setErro(parseApiErrors(e)._form ?? 'Não foi possível estornar a baixa.')
    }
  }
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center px-4">
      <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onClick={() => !pendente && onFechar()} aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-label="Estornar baixa" className="relative w-full rounded-xl flex flex-col gap-3 p-5"
        style={{ maxWidth: 440, background: 'var(--surface)', boxShadow: 'var(--shadow-lg)', border: '1px solid var(--line)', color: 'var(--ink-2)' }}>
        <header className="flex items-center gap-2">
          <RotateCcw size={18} style={{ color: 'var(--danger-ink)' }} />
          <h2 className="text-base font-bold" style={{ color: 'var(--ink)' }}>Estornar baixa</h2>
          <button type="button" onClick={onFechar} aria-label="Fechar" style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)' }}><X size={18} /></button>
        </header>
        <p className="text-sm">
          A baixa de <strong>{formatBRL(apiDecimalToCents(valorPago))}</strong> é anulada e a conta volta para
          <strong> Aberto</strong>. O caixa recebe um lançamento de estorno — a baixa original continua no histórico.
          Depois disso, valor, vencimento e {`fornecedor/cliente`} podem ser corrigidos.
        </p>
        <label className="flex flex-col gap-1 text-sm">
          <span style={{ fontWeight: 600 }}>Motivo</span>
          <textarea value={motivo} onChange={e => setMotivo(e.target.value)} rows={3} autoFocus
            placeholder="Ex.: baixa lançada na conta errada"
            style={{ border: '1.5px solid var(--line)', borderRadius: 'var(--r-sm)', padding: 8, background: 'var(--surface)', color: 'var(--ink)', resize: 'vertical' }} />
        </label>
        {erro && <p className="text-sm" style={{ color: 'var(--danger-ink)' }}>⚠ {erro}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onFechar} disabled={pendente} style={buttonSecondaryStyle}>Cancelar</button>
          <button type="button" onClick={confirmar} disabled={pendente || motivo.trim().length < 5}
            style={{ ...buttonSecondaryStyle, background: 'var(--danger)', color: '#fff', borderColor: 'var(--danger)', opacity: pendente || motivo.trim().length < 5 ? 0.6 : 1 }}>
            {pendente ? 'Estornando…' : 'Estornar baixa'}
          </button>
        </div>
      </div>
    </div>
  )
}
