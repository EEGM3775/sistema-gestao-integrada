import React from 'react'
import { AlertTriangle, WifiOff } from 'lucide-react'
import { formatCPFCNPJ } from '@/utils/masks'
import type { DivergenciaAsaas } from '../services/clientesService'

// Teto de linhas efetivamente renderizadas. Sem isso, um tenant com milhares de
// divergências geraria milhares de <li> e enterraria o resto da tela. O total
// real continua no cabeçalho.
const MAX_DIVERGENCIAS_VISIVEIS = 50

/** O backend mascara o documento (••••NN) para quem não tem `cadastro.cliente_doc.view`
 *  (LGPD). Só formata como CPF/CNPJ quando vier em dígitos crus. */
function renderDocumento(documento: string): string {
  if (!documento) return ''
  return /[•*]/.test(documento) ? documento : formatCPFCNPJ(documento)
}

interface Props {
  loading: boolean
  divergencias: DivergenciaAsaas[]
  /** Mensagem quando a auditoria não pôde rodar (Asaas fora, sem permissão) —
   *  evita a falsa sensação de "tudo certo" de um painel vazio (D3). */
  error?: string | null
  /** Classe do root — só é aplicada quando algo renderiza (o estado vazio
   *  devolve `null`, sem margem órfã no consumidor). */
  className?: string
}

/**
 * Painel de divergências de identidade banco × Asaas — cadastros cujo estado
 * impediria ou desviaria uma cobrança. Compartilhado entre o cadastro de cliente
 * ("Novo Cliente") e o fluxo de gerar cobrança do ERP (D3), para as duas telas
 * mostrarem a MESMA informação, da mesma forma.
 */
export const DivergenciasAsaasPanel: React.FC<Props> = ({ loading, divergencias, error, className = '' }) => {
  if (loading) {
    return (
      <div className={`${className} px-4 py-3 rounded-lg text-xs`} style={{
        background: '#f8fafc', border: '1px solid #e2e8f0',
        color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)',
      }}>
        Verificando divergências com o gateway de cobrança (Asaas)…
      </div>
    )
  }

  if (error) {
    return (
      <div className={`${className} px-4 py-3 rounded-lg`} style={{
        background: '#f8fafc', border: '1px solid #e2e8f0', fontFamily: 'var(--font-body)',
      }}>
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          <WifiOff size={14} />
          <span>{error}</span>
        </div>
      </div>
    )
  }

  if (divergencias.length === 0) return null

  const total = divergencias.length
  const visiveis = divergencias.slice(0, MAX_DIVERGENCIAS_VISIVEIS)
  const ocultas = total - visiveis.length

  return (
    <div className={`${className} px-4 py-3 rounded-lg`} style={{
      background: '#fffbeb', border: '1px solid #fde68a', fontFamily: 'var(--font-body)',
    }}>
      <div className="flex items-center gap-2 mb-2" style={{ color: '#92400e' }}>
        <AlertTriangle size={15} />
        <span className="text-xs font-bold uppercase tracking-wide">
          {total} divergência{total !== 1 ? 's' : ''} entre cadastro e Asaas
        </span>
      </div>
      <p className="text-xs mb-2" style={{ color: '#92400e' }}>
        Clientes cujo cadastro impediria ou desviaria uma cobrança. Corrija antes de emitir boletos:
      </p>
      {/* Lista com altura limitada e rolagem própria: o painel nunca cresce além
          disso, independentemente do número de divergências. */}
      <ul className="flex flex-col gap-1.5" style={{ maxHeight: '220px', overflowY: 'auto' }}>
        {visiveis.map(d => (
          <li key={d.cliente_id} className="text-xs" style={{ color: '#78350f', lineHeight: 1.4 }}>
            <span className="font-semibold">{d.nome}</span>
            {d.documento ? ` (${renderDocumento(d.documento)})` : ''}
            {d.nome_gateway ? <> — no Asaas: <span className="font-semibold">“{d.nome_gateway}”</span></> : ''}
            <br />
            <span style={{ opacity: 0.85 }}>{d.detalhe}</span>
          </li>
        ))}
      </ul>
      {ocultas > 0 && (
        <p className="text-xs mt-2 font-semibold" style={{ color: '#92400e' }}>
          + {ocultas} outr{ocultas !== 1 ? 'as' : 'a'} divergência{ocultas !== 1 ? 's' : ''} não listada{ocultas !== 1 ? 's' : ''} aqui.
          Corrija estas e reabra para ver as demais.
        </p>
      )}
    </div>
  )
}
