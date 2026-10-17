import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import type { AgingFaixa } from '../../types'

/**
 * Faixas na ordem do tempo, do que ainda vai vencer ao mais atrasado. A cor é a
 * gravidade do atraso — a mesma rampa nos dois lados (receber e pagar), para
 * que "vermelho" queira dizer a mesma coisa nos dois cards.
 */
const FAIXAS: { casa: (c: string) => boolean; rotulo: string; cor: string }[] = [
  { casa: c => c === 'A Vencer', rotulo: 'A vencer', cor: '#94a3b8' },
  { casa: c => c === 'Vence Hoje', rotulo: 'Vence hoje', cor: '#eab308' },
  { casa: c => c.startsWith('1-30'), rotulo: '1–30 dias', cor: '#f59e0b' },
  { casa: c => c.startsWith('31-60'), rotulo: '31–60 dias', cor: '#f97316' },
  { casa: c => c.startsWith('61-90'), rotulo: '61–90 dias', cor: '#ef4444' },
  { casa: c => c.startsWith('>'), rotulo: '> 90 dias', cor: '#991b1b' },
]

interface Props {
  titulo: string
  data: AgingFaixa[]
  /** Lista de origem dos títulos — o card leva até ela. */
  to: string
  /** Cor de destaque do total (verde a receber, vermelho a pagar). */
  cor: string
}

/**
 * Aging de contas em uma barra empilhada fina + a lista das faixas com valor e
 * participação — `agingContasA{Receber,Pagar}` do `/api/erp/dashboard/`. Ocupa
 * um terço da altura do antigo gráfico de barras e mostra o número exato.
 */
export function AgingChart({ titulo, data, to, cor }: Props) {
  const faixas = FAIXAS
    .map(f => ({ ...f, centavos: data.filter(d => f.casa(d.categoria)).reduce((s, d) => s + apiDecimalToCents(d.total), 0) }))
    .filter(f => f.centavos > 0)
  const total = faixas.reduce((s, f) => s + f.centavos, 0)
  const vencido = faixas.filter(f => f.rotulo !== 'A vencer' && f.rotulo !== 'Vence hoje').reduce((s, f) => s + f.centavos, 0)

  return (
    <div className="rounded-xl p-4 flex flex-col" style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF' }}>
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <h2 className="text-sm font-semibold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-text)' }}>{titulo}</h2>
          <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
            {total > 0 ? `${formatBRL(vencido)} vencido (${pct(vencido, total)})` : 'Saldo em aberto por faixa de vencimento'}
          </p>
        </div>
        <div className="text-right">
          <div className="text-lg font-bold" style={{ fontFamily: 'var(--font-heading)', color: cor, fontVariantNumeric: 'tabular-nums' }}>
            {formatBRL(total)}
          </div>
          <Link to={to} className="inline-flex items-center gap-1 text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
            Ver títulos <ArrowRight size={12} />
          </Link>
        </div>
      </div>

      {total === 0 ? (
        <p className="text-xs py-3" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>Nenhum título em aberto.</p>
      ) : (
        <>
          <div className="flex w-full overflow-hidden rounded-full mb-3" style={{ height: 10, background: '#f1f5f9' }}
            role="img" aria-label={faixas.map(f => `${f.rotulo}: ${formatBRL(f.centavos)}`).join('; ')}>
            {faixas.map(f => (
              <div key={f.rotulo} title={`${f.rotulo}: ${formatBRL(f.centavos)}`}
                style={{ width: `${(f.centavos / total) * 100}%`, background: f.cor, minWidth: 3 }} />
            ))}
          </div>
          <ul className="grid gap-x-4 gap-y-1 sm:grid-cols-2" style={{ fontFamily: 'var(--font-body)', fontSize: '0.78rem' }}>
            {faixas.map(f => (
              <li key={f.rotulo} className="flex items-center gap-2">
                <span style={{ width: 8, height: 8, borderRadius: 2, background: f.cor, flexShrink: 0 }} />
                <span className="flex-1" style={{ color: 'var(--color-text-muted)' }}>{f.rotulo}</span>
                <span style={{ color: 'var(--color-text)', fontVariantNumeric: 'tabular-nums', fontWeight: 500 }}>{formatBRL(f.centavos)}</span>
                <span style={{ color: 'var(--color-text-muted)', fontVariantNumeric: 'tabular-nums', width: 36, textAlign: 'right' }}>{pct(f.centavos, total)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

function pct(parte: number, total: number) {
  return `${Math.round((parte / total) * 100)}%`
}
