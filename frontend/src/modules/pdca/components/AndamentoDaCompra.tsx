import { Link } from 'react-router-dom'
import { ArrowUpRight, PackageCheck } from 'lucide-react'
import { dateToBR } from '@/utils/dates'
import type { CompraDaRestricao } from '../types'

const PASSOS: { chave: CompraDaRestricao['etapa'][]; rotulo: string }[] = [
  { chave: ['demanda'], rotulo: 'Demanda' },
  { chave: ['cotacao'], rotulo: 'Cotação' },
  { chave: ['pedido'], rotulo: 'Pedido' },
  { chave: ['recebido_parcial', 'recebido'], rotulo: 'Recebido' },
]

/** Em que pé está a compra que a trava abriu — demanda → cotação → pedido →
 *  recebido —, com o caminho para o Suprimentos. Quando tudo o que foi pedido
 *  chegou, oferece destravar com a nota já escrita; a pessoa confirma
 *  *(decisão do dono: o recebimento sugere, não destrava sozinho)*. */
export function AndamentoDaCompra(
  { compra, aoDestravar, ocupado = false }: {
    compra: CompraDaRestricao
    aoDestravar?: (nota: string) => void
    ocupado?: boolean
  },
) {
  const atual = PASSOS.findIndex((p) => p.chave.includes(compra.etapa))
  const pedido = compra.pedidos[compra.pedidos.length - 1]
  const detalhe = compra.etapa === 'recebido_parcial'
    ? 'recebido em parte'
    : pedido && compra.etapa === 'pedido'
      ? `pedido #${pedido.pedido} · ${pedido.status_rotulo.toLowerCase()}${pedido.entrega_prevista ? ` · entrega ${dateToBR(pedido.entrega_prevista)}` : ''}`
      : compra.etapa === 'cotacao' ? `cotação #${compra.cotacao}` : compra.etapa === 'demanda' ? `demanda #${compra.demanda} · ${compra.demanda_status}` : ''
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 3, flexWrap: 'wrap' }} aria-label={`Compra: ${PASSOS[atual]?.rotulo ?? ''}`}>
        {PASSOS.map((p, i) => (
          <span key={p.rotulo} style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
            <span
              style={{
                fontSize: 10.5, fontWeight: 650, padding: '1px 6px', borderRadius: 999,
                background: i < atual ? 'var(--good-soft)' : i === atual ? 'var(--accent-soft)' : 'var(--inset)',
                color: i < atual ? 'var(--good-ink)' : i === atual ? 'var(--accent-ink)' : 'var(--ink-3)',
              }}
            >
              {p.rotulo}
            </span>
            {i < PASSOS.length - 1 && <span style={{ color: 'var(--ink-3)', fontSize: 10 }}>›</span>}
          </span>
        ))}
        <Link to="/app/scm" title="Abrir no Suprimentos" style={{ color: 'var(--brand)', display: 'inline-flex', marginLeft: 2 }}>
          <ArrowUpRight size={12} />
        </Link>
      </div>
      {detalhe && <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{detalhe}</span>}
      {compra.sugerir_destravar && aoDestravar && (
        <button
          type="button"
          disabled={ocupado}
          onClick={() => aoDestravar(`Material recebido${pedido ? ` no pedido #${pedido.pedido}` : ''} (demanda #${compra.demanda}).`)}
          style={{
            alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 650,
            padding: '4px 10px', borderRadius: 'var(--r-sm)', border: '1px solid var(--good)', background: 'var(--good-soft)',
            color: 'var(--good-ink)', cursor: 'pointer',
          }}
        >
          <PackageCheck size={13} /> Material recebido — destravar
        </button>
      )}
    </div>
  )
}
