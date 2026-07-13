import { useEffect, useState } from 'react'
import { X, FileText, ChevronDown, ChevronRight } from 'lucide-react'
import { formatBRL } from '@/utils/money'
import { getDivergenciasAsaas, type DivergenciaAsaas } from '@/modules/clientes/services/clientesService'
import { DivergenciasAsaasPanel } from '@/modules/clientes/components/DivergenciasAsaasPanel'
import { buttonPrimaryStyle, buttonSecondaryStyle } from './forms/formStyles'

interface Props {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  pending: boolean
  /** Saldo em aberto da conta (centavos) — o valor que será cobrado. */
  valorCents: number
}

/**
 * Confirmação da geração de cobrança no Asaas (D3). Espelha o padrão de sistemas
 * de cobrança conceituados: antes de emitir, um passo de confirmação que resume o
 * que será feito e dá acesso, **sob demanda**, às divergências de cadastro
 * (banco × Asaas) — os mesmos dados do painel de "Novo Cliente", agora também
 * aqui, na hora que mais importam. As divergências são carregadas só quando o
 * usuário pede (minimização de PII/LGPD) e o documento vem mascarado do backend
 * para quem não tem `cadastro.cliente_doc.view`.
 */
export function GerarCobrancaDialog({ open, onClose, onConfirm, pending, valorCents }: Props) {
  const [verDiverg, setVerDiverg] = useState(false)
  const [loading, setLoading] = useState(false)
  const [divergencias, setDivergencias] = useState<DivergenciaAsaas[]>([])
  const [error, setError] = useState<string | null>(null)
  const [carregado, setCarregado] = useState(false)

  // Reset ao (re)abrir: cada abertura parte do estado neutro.
  useEffect(() => {
    if (!open) return
    setVerDiverg(false)
    setDivergencias([])
    setError(null)
    setCarregado(false)
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !pending) onClose() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [open, onClose, pending])

  if (!open) return null

  const toggleDiverg = () => {
    const next = !verDiverg
    setVerDiverg(next)
    if (next && !carregado) {
      setLoading(true)
      setError(null)
      getDivergenciasAsaas()
        .then(r => { setDivergencias(r.data.divergencias); setCarregado(true) })
        // Falha silenciosa não: avisa que a auditoria não pôde rodar (D3).
        .catch(() => setError('Não foi possível verificar as divergências com o Asaas agora.'))
        .finally(() => setLoading(false))
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center px-4">
      <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onClick={() => !pending && onClose()} aria-hidden="true" />

      <div
        role="dialog"
        aria-modal="true"
        aria-label="Gerar cobrança no Asaas"
        className="relative w-full flex flex-col rounded-xl"
        style={{ maxWidth: 460, maxHeight: '85vh', background: '#FFFFFF', boxShadow: 'var(--shadow-lg)', border: '1.5px solid #e2e8f0' }}
      >
        <header className="flex items-start justify-between gap-3 px-5 py-4" style={{ borderBottom: '1.5px solid #e2e8f0' }}>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: '#e0f2fe', color: '#0369a1' }}>
              <FileText size={18} />
            </div>
            <h2 className="text-base font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Gerar cobrança no Asaas
            </h2>
          </div>
          <button type="button" onClick={() => !pending && onClose()} aria-label="Fechar" className="p-1.5 rounded-lg shrink-0"
            style={{ color: 'var(--color-text-muted)', cursor: pending ? 'not-allowed' : 'pointer' }}>
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4" style={{ fontFamily: 'var(--font-body)' }}>
          <p className="text-sm" style={{ color: 'var(--color-text)', lineHeight: 1.5 }}>
            Será emitida uma cobrança (boleto/PIX) no valor de{' '}
            <span className="font-bold">{formatBRL(valorCents)}</span>. O boleto aparece em “Boletos”
            assim que o gateway confirmar.
          </p>

          <button
            type="button"
            onClick={toggleDiverg}
            className="flex items-center gap-1.5 mt-4 text-xs font-semibold"
            style={{ color: 'var(--color-brand)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          >
            {verDiverg ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            Ver divergências de cadastro (Asaas)
          </button>
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
            Cadastros cujo estado impediria ou desviaria o boleto — confira antes de emitir.
          </p>

          {verDiverg && (
            <div className="mt-3">
              <DivergenciasAsaasPanel loading={loading} divergencias={divergencias} error={error} />
              {!loading && !error && divergencias.length === 0 && carregado && (
                <div className="px-4 py-3 rounded-lg text-xs" style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#166534' }}>
                  Nenhuma divergência — cadastro e Asaas estão alinhados.
                </div>
              )}
            </div>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 px-5 py-3.5" style={{ borderTop: '1.5px solid #e2e8f0', background: '#f8fafc' }}>
          <button type="button" onClick={onClose} disabled={pending} style={{ ...buttonSecondaryStyle, opacity: pending ? 0.6 : 1 }}>
            Cancelar
          </button>
          <button type="button" onClick={onConfirm} disabled={pending}
            style={{ ...buttonPrimaryStyle, opacity: pending ? 0.6 : 1, cursor: pending ? 'wait' : 'pointer' }}>
            {pending ? 'Gerando…' : 'Confirmar geração'}
          </button>
        </footer>
      </div>
    </div>
  )
}
