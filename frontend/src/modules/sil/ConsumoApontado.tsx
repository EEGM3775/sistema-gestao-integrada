import { useQuery } from '@tanstack/react-query'
import { HardHat } from 'lucide-react'
import apiClient from '@/api/apiClient'
import { useAuth } from '@/hooks/useAuth'

interface LinhaDeConsumo {
  obra: number
  obra_nome: string
  etapa: number | null
  etapa_nome: string
  item: number
  descricao: string
  unidade: string
  teorico: string
  aplicado: string
  a_baixar: string
}

const n = (v: string) => Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 3 })

/** **O campo apontou, o estoque ainda não baixou.** O avanço lançado no PDCA
 *  não mexe no estoque *(decisão do dono)* — ele avisa: o consumo teórico do
 *  serviço (avanço × composição do orçamento) contra o que já saiu para a obra
 *  e a etapa. A diferença é a saída a registrar, ou o desperdício a explicar. */
export function ConsumoApontado({ aoRegistrar }: { aoRegistrar: () => void }) {
  const { hasPermission } = useAuth()
  const { data } = useQuery({
    queryKey: ['sil', 'consumo-a-baixar'],
    queryFn: async () => (await apiClient.get<{ linhas: LinhaDeConsumo[]; disponivel: boolean }>('sil/consumo-a-baixar/')).data,
    enabled: hasPermission('sil.relatorio.view'),
    staleTime: 60_000,
  })
  const linhas = data?.linhas ?? []
  if (linhas.length === 0) return null
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', boxShadow: 'var(--shadow-sm)', marginTop: 14, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 16px 8px', flexWrap: 'wrap' }}>
        <HardHat size={16} style={{ color: 'var(--accent-ink)' }} />
        <h2 style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.02em', color: 'var(--ink-2)' }}>Consumo apontado no campo, sem baixa</h2>
        <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>avanço do PDCA × composição do orçamento, contra o que já saiu para a obra</span>
        <span style={{ flex: 1 }} />
        {hasPermission('sil.movimentacao.edit') && (
          <button type="button" onClick={aoRegistrar} style={{ fontSize: 12.5, fontWeight: 650, padding: '5px 11px', borderRadius: 'var(--r-sm)', border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink-2)', cursor: 'pointer' }}>
            Registrar saída
          </button>
        )}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 560 }}>
          <thead>
            <tr>
              {['Obra · etapa', 'Insumo', 'Apontado (teórico)', 'Já baixado', 'A baixar'].map((h, i) => (
                <th key={h} style={{ fontSize: 10.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700, textAlign: i >= 2 ? 'right' : 'left', padding: '8px 14px', borderTop: '1px solid var(--line-2)', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {linhas.map((l) => (
              <tr key={`${l.obra}-${l.etapa}-${l.item}`}>
                <td style={{ padding: '8px 14px', borderBottom: '1px solid var(--line-2)' }}>{l.obra_nome} <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>· {l.etapa_nome}</span></td>
                <td style={{ padding: '8px 14px', borderBottom: '1px solid var(--line-2)' }}>{l.descricao} <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>{l.unidade}</span></td>
                <td style={{ padding: '8px 14px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', fontFamily: 'var(--mono)' }}>{n(l.teorico)}</td>
                <td style={{ padding: '8px 14px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', fontFamily: 'var(--mono)', color: 'var(--ink-3)' }}>{n(l.aplicado)}</td>
                <td style={{ padding: '8px 14px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', fontFamily: 'var(--mono)', fontWeight: 700, color: 'var(--accent-ink)' }}>{n(l.a_baixar)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
