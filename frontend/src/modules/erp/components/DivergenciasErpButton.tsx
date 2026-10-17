import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, WifiOff, X, RefreshCw } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { DivergenciasAsaasPanel } from '@/modules/clientes/components/DivergenciasAsaasPanel'
import { useDivergenciasErp } from '../hooks/useDivergenciasErp'
import { buttonSecondaryStyle } from './forms/formStyles'

/**
 * Alerta de divergências de cadastro do módulo ERP. Um único botão que:
 *  - fica **colorido como alerta** e mostra a contagem quando há divergências;
 *  - abre uma janela (modal) com os dados ao clicar.
 *
 * **Gate (LGPD + escopo):** é dado financeiro que carrega PII de cliente, então
 * exige as DUAS permissões de **usuário** — `erp.cobranca.view` (ver cobranças)
 * **e** `cadastro.cliente.view` (acesso aos clientes). Não basta `hasModule`: o
 * módulo é entitlement do **tenant**, não do usuário — um `operacional` num
 * tenant com ERP não deve ver isto. O documento (CPF/CNPJ) ainda vem mascarado
 * do backend para quem não tem `cadastro.cliente_doc.view` (regra da 9.C). O
 * mesmo par é reforçado no backend (`clientes/views.py::divergencias_asaas`).
 */
export function DivergenciasErpButton() {
  const { hasPermission } = useAuth()
  const [open, setOpen] = useState(false)

  // Gate de visibilidade (LGPD + escopo): permissão de cobrança + acesso aos
  // clientes. Sem isto o botão nem renderiza (e a query nem dispara).
  const podeVer = hasPermission('erp.cobranca.view') && hasPermission('cadastro.cliente.view')

  const { data, isLoading, isError, isFetching, refetch } = useDivergenciasErp(podeVer)

  const total = data?.total_divergencias ?? 0
  const temDivergencia = total > 0

  // Trava de rolagem + Esc enquanto o modal está aberto.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [open])

  if (!podeVer) return null

  // Estilo do botão conforme o estado. Alerta (âmbar) só quando há divergência.
  const estilo: React.CSSProperties = temDivergencia
    ? { background: '#fffbeb', border: '1.5px solid #fbbf24', color: '#92400e' }
    : isError
      ? { background: '#f8fafc', border: '1.5px solid #e2e8f0', color: 'var(--color-text-muted)' }
      : { background: '#f0fdf4', border: '1.5px solid #bbf7d0', color: '#166534' }

  const icone = isLoading
    ? <RefreshCw size={15} className="animate-spin" />
    : temDivergencia
      ? <AlertTriangle size={15} />
      : isError
        ? <WifiOff size={15} />
        : <CheckCircle2 size={15} />

  const rotulo = isLoading
    ? 'Verificando divergências…'
    : temDivergencia
      ? `${total} divergência${total !== 1 ? 's' : ''} de cadastro`
      : isError
        ? 'Divergências (indisponível)'
        : 'Sem divergências'

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-colors duration-150"
        style={{ ...estilo, fontFamily: 'var(--font-body)', cursor: 'pointer' }}
        title="Ver divergências de cadastro (ERP × Asaas)"
        aria-label={rotulo}
      >
        {icone}
        <span>{rotulo}</span>
        {temDivergencia && (
          <span
            className="inline-flex items-center justify-center rounded-full text-[0.65rem] font-bold"
            style={{ minWidth: 18, height: 18, padding: '0 5px', background: '#dc2626', color: '#FFFFFF' }}
          >
            {total}
          </span>
        )}
      </button>

      {open && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center px-4">
          <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onClick={() => setOpen(false)} aria-hidden="true" />

          <div
            role="dialog"
            aria-modal="true"
            aria-label="Divergências de cadastro do ERP"
            className="relative w-full flex flex-col rounded-xl"
            style={{ maxWidth: 520, maxHeight: '85vh', background: '#FFFFFF', boxShadow: 'var(--shadow-lg)', border: '1.5px solid #e2e8f0' }}
          >
            <header className="flex items-start justify-between gap-3 px-5 py-4" style={{ borderBottom: '1.5px solid #e2e8f0' }}>
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: temDivergencia ? '#fef3c7' : '#dcfce7', color: temDivergencia ? '#b45309' : '#166534' }}>
                  <AlertTriangle size={18} />
                </div>
                <div>
                  <h2 className="text-base font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
                    Divergências de cadastro
                  </h2>
                  <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                    Cadastros cujo estado impediria ou desviaria uma cobrança (banco × Asaas).
                  </p>
                </div>
              </div>
              <button type="button" onClick={() => setOpen(false)} aria-label="Fechar" className="p-1.5 rounded-lg shrink-0"
                style={{ color: 'var(--color-text-muted)', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </header>

            <div className="flex-1 overflow-y-auto px-5 py-4" style={{ fontFamily: 'var(--font-body)' }}>
              <DivergenciasAsaasPanel
                loading={isLoading}
                divergencias={data?.divergencias ?? []}
                error={isError ? 'Não foi possível verificar as divergências com a API agora.' : null}
              />
              {!isLoading && !isError && total === 0 && (
                <div className="px-4 py-3 rounded-lg text-xs" style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#166534' }}>
                  Nenhuma divergência — cadastro e Asaas estão alinhados.
                </div>
              )}
            </div>

            <footer className="flex items-center justify-end gap-2 px-5 py-3.5" style={{ borderTop: '1.5px solid #e2e8f0', background: '#f8fafc' }}>
              <button type="button" onClick={() => refetch()} disabled={isFetching}
                className="flex items-center gap-1.5"
                style={{ ...buttonSecondaryStyle, opacity: isFetching ? 0.6 : 1, cursor: isFetching ? 'wait' : 'pointer' }}>
                <RefreshCw size={14} className={isFetching ? 'animate-spin' : undefined} />
                Reverificar
              </button>
              <button type="button" onClick={() => setOpen(false)} style={buttonSecondaryStyle}>
                Fechar
              </button>
            </footer>
          </div>
        </div>
      )}
    </>
  )
}

export default DivergenciasErpButton
