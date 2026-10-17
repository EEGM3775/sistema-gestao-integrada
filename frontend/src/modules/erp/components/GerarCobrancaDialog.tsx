import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CalendarClock, ChevronDown, ChevronRight, FileText, Loader2, X } from 'lucide-react'
import { formatBRL, apiDecimalToCents } from '@/utils/money'
import { dateToBR, maxCalendarioISO, maxTodayISO } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import { getDivergenciasAsaas, type DivergenciaAsaas } from '@/modules/clientes/services/clientesService'
import { DivergenciasAsaasPanel } from '@/modules/clientes/components/DivergenciasAsaasPanel'
import { usePreviaCobranca } from '../hooks/useCobranca'
import { buttonPrimaryStyle, buttonSecondaryStyle } from './forms/formStyles'

interface Props {
  open: boolean
  contaId: number
  onClose: () => void
  onConfirm: (vencimento?: string) => void
  pending: boolean
}

const reais = (v?: string) => formatBRL(apiDecimalToCents(v ?? '0'))

/**
 * Antes de emitir o boleto, a prévia do que ele vai ser (item 55 do dono).
 *
 * - A data do contrato e a do boleto, com o **porquê** quando diferem ("12/10
 *   é Nossa Senhora Aparecida"), e a ressalva quando a base de feriados nunca
 *   foi sincronizada — a mesma que a ficha do cliente mostra ao gerar o carnê.
 * - **Título vencido** não emite no passado: vem uma nova data sugerida, e o
 *   boleto soma a multa e os juros do contrato até ela. Mudar a data refaz a conta.
 * - O boleto antigo que será cancelado para dar lugar a este, dito antes.
 */
export function GerarCobrancaDialog({ open, contaId, onClose, onConfirm, pending }: Props) {
  const [vencimento, setVencimento] = useState<string | undefined>(undefined)
  const previa = usePreviaCobranca(contaId, vencimento, open)
  const p = previa.data

  // A data volta à sugerida só ao abrir — não a cada fim de "gerando…" nem a
  // cada render do pai (o mesmo defeito que apagava o erro da NFS-e).
  useEffect(() => { if (open) setVencimento(undefined) }, [open])
  const ocupado = useRef(pending)
  ocupado.current = pending
  const fechar = useRef(onClose)
  fechar.current = onClose
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !ocupado.current) fechar.current() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  if (!open) return null

  const erroPrevia = previa.error ? parseApiErrors(previa.error)._form : null
  const temEncargos = p && (Number(p.multa) > 0 || Number(p.juros) > 0)

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center px-4">
      <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onClick={() => !pending && onClose()} aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-label="Gerar boleto"
        className="relative w-full flex flex-col rounded-xl"
        style={{ maxWidth: 500, maxHeight: '88vh', background: 'var(--surface)', boxShadow: 'var(--shadow-lg)', border: '1px solid var(--line)' }}>
        <header className="flex items-center justify-between gap-3 px-5 py-4" style={{ borderBottom: '1px solid var(--line)' }}>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: 'var(--accent-soft)', color: 'var(--accent-ink)' }}>
              <FileText size={18} />
            </div>
            <h2 className="text-base font-bold" style={{ color: 'var(--ink)' }}>
              {p?.vencida ? 'Emitir segunda via' : 'Gerar boleto'}
            </h2>
          </div>
          <button type="button" onClick={() => !pending && onClose()} aria-label="Fechar" className="p-1.5 rounded-lg"
            style={{ color: 'var(--ink-3)', cursor: pending ? 'not-allowed' : 'pointer', background: 'none', border: 'none' }}>
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-3 text-sm" style={{ color: 'var(--ink-2)' }}>
          {!p && previa.isLoading && (
            <p className="flex items-center gap-2"><Loader2 size={15} className="animate-spin" /> Calculando o boleto…</p>
          )}
          {erroPrevia && <p style={{ color: 'var(--danger-ink)' }}>{erroPrevia}</p>}

          {p && (
            <>
              {p.vencida && (
                <div className="flex gap-2" style={{ padding: '10px 12px', borderRadius: 'var(--r-md)', background: 'var(--danger-soft)', color: 'var(--danger-ink)' }}>
                  <AlertTriangle size={16} style={{ flex: 'none', marginTop: 2 }} />
                  <span>
                    Esta parcela venceu em <strong>{dateToBR(p.vencimento_contratual)}</strong> ({p.dias_atraso} dia{p.dias_atraso !== 1 ? 's' : ''}).
                    O boleto sai com uma nova data e soma a multa e os juros do contrato até ela.
                  </span>
                </div>
              )}

              {p.vencida && (
                <label className="flex flex-col gap-1">
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-3)' }}>Nova data de vencimento</span>
                  <input
                    type="date" min={maxTodayISO()} max={maxCalendarioISO}
                    value={vencimento ?? p.vencimento_escolhido}
                    onChange={e => e.target.value && setVencimento(e.target.value)}
                    style={{ border: '1.5px solid var(--line)', borderRadius: 'var(--r-sm)', padding: '7px 10px', background: 'var(--surface)', color: 'var(--ink)', maxWidth: 200 }}
                  />
                  <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>Sugerida: {dateToBR(p.vencimento_sugerido)}. Os encargos são recalculados para a data escolhida.</span>
                </label>
              )}

              <dl className="grid grid-cols-2 gap-x-4 gap-y-2" style={{ background: 'var(--surface-2)', borderRadius: 'var(--r-md)', padding: '10px 12px' }}>
                <dt>Vencimento do contrato</dt><dd className="text-right">{dateToBR(p.vencimento_contratual)}</dd>
                <dt className="font-semibold" style={{ color: 'var(--ink)' }}>Vencimento do boleto</dt>
                <dd className="text-right font-semibold" style={{ color: 'var(--ink)' }}>{dateToBR(p.vencimento_bancario)}</dd>
                <dt>Saldo da parcela</dt><dd className="text-right">{reais(p.saldo)}</dd>
                {temEncargos && (
                  <>
                    <dt>Multa ({Number(p.multa_percentual).toLocaleString('pt-BR')}%)</dt><dd className="text-right">{reais(p.multa)}</dd>
                    <dt>Juros ({Number(p.juros_mes_percentual).toLocaleString('pt-BR')}% ao mês · {p.dias_encargos} dias)</dt><dd className="text-right">{reais(p.juros)}</dd>
                  </>
                )}
                <dt className="font-bold" style={{ color: 'var(--ink)' }}>Valor do boleto</dt>
                <dd className="text-right font-bold" style={{ color: 'var(--ink)' }}>{reais(p.total)}</dd>
              </dl>

              {p.motivo_ajuste && (
                <p className="flex gap-2" style={{ fontSize: 12.5 }}>
                  <CalendarClock size={15} style={{ flex: 'none', marginTop: 1, color: 'var(--ink-3)' }} />
                  <span>
                    {dateToBR(p.vencimento_escolhido)} cai {/^(sábado|domingo)$/.test(p.motivo_ajuste) ? `num ${p.motivo_ajuste}` : `no feriado de ${p.motivo_ajuste}`}:
                    o boleto vence no próximo dia útil ({p.calendario.uf ? `feriados de ${p.calendario.uf}` : 'feriados nacionais'}{p.calendario.municipio ? ' e do município do imóvel' : ''}).
                    {p.calendario.municipal_projetado && ' O feriado da cidade foi estimado pela data dos anos já publicados.'}
                  </span>
                </p>
              )}
              {!p.calendario.feriados_carregados && (
                <p style={{ fontSize: 12, color: 'var(--accent-ink)' }}>
                  A base de feriados ainda não foi sincronizada: o vencimento desvia de sábado e domingo, mas <strong>não</strong> de feriado.
                </p>
              )}

              {p.boleto_substituido && (
                <p style={{ fontSize: 12.5, padding: '8px 10px', borderRadius: 'var(--r-sm)', background: 'var(--accent-soft)', color: 'var(--accent-ink)' }}>
                  O boleto de {dateToBR(p.boleto_substituido.vencimento)} ({reais(p.boleto_substituido.valor)}) será
                  <strong> cancelado na API</strong> e substituído por este. O cancelamento não se desfaz.
                </p>
              )}

              <Divergencias />
            </>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 px-5 py-3.5" style={{ borderTop: '1px solid var(--line)', background: 'var(--surface-2)' }}>
          <button type="button" onClick={onClose} disabled={pending} style={{ ...buttonSecondaryStyle, opacity: pending ? 0.6 : 1 }}>Cancelar</button>
          <button
            type="button"
            onClick={() => onConfirm(p?.vencida ? p.vencimento_escolhido : undefined)}
            disabled={pending || !p || previa.isFetching}
            style={{ ...buttonPrimaryStyle, opacity: pending || !p ? 0.6 : 1, cursor: pending ? 'wait' : 'pointer' }}
          >
            {pending ? 'Gerando…' : p?.vencida ? `Emitir segunda via · ${reais(p.total)}` : `Gerar boleto · ${reais(p?.total)}`}
          </button>
        </footer>
      </div>
    </div>
  )
}

/** As divergências de cadastro com o Asaas, sob demanda (minimização de PII — D3). */
function Divergencias() {
  const [aberto, setAberto] = useState(false)
  const [estado, setEstado] = useState<{ carregando: boolean; itens: DivergenciaAsaas[]; erro: string | null; ok: boolean }>(
    { carregando: false, itens: [], erro: null, ok: false },
  )
  const alternar = () => {
    const prox = !aberto
    setAberto(prox)
    if (prox && !estado.ok) {
      setEstado(e => ({ ...e, carregando: true, erro: null }))
      getDivergenciasAsaas()
        .then(r => setEstado({ carregando: false, itens: r.data.divergencias, erro: null, ok: true }))
        .catch(() => setEstado({ carregando: false, itens: [], erro: 'Não foi possível verificar as divergências com a API agora.', ok: false }))
    }
  }
  return (
    <div>
      <button type="button" onClick={alternar} className="flex items-center gap-1.5 text-xs font-semibold"
        style={{ color: 'var(--accent-ink)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
        {aberto ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Ver divergências de cadastro (Asaas)
      </button>
      {aberto && (
        <div className="mt-2">
          <DivergenciasAsaasPanel loading={estado.carregando} divergencias={estado.itens} error={estado.erro} />
          {estado.ok && !estado.itens.length && (
            <div className="px-3 py-2 rounded-lg text-xs" style={{ background: 'var(--good-soft)', color: 'var(--good-ink)' }}>
              Nenhuma divergência — cadastro e Asaas estão alinhados.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
