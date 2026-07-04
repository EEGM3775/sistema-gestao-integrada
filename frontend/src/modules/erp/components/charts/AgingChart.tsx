import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import type { AgingFaixa } from '../../types'

const tickStyle = { fontSize: 12, fill: '#64748b' }
const tooltipStyle = { borderRadius: 8, border: '1px solid #e2e8f0', fontFamily: 'var(--font-body)', fontSize: '0.8rem' }

interface Props {
  data: AgingFaixa[]
  /** Cor das barras — hex literal (atributo SVG `fill` não resolve `var(--...)` de forma confiável). */
  color?: string
}

/** Aging de contas (faixas de atraso/vencimento) — `agingContasA{Receber,Pagar}` do `/api/erp/dashboard/`. */
export function AgingChart({ data, color = '#0A2A5B' }: Props) {
  const chartData = data.map(f => ({ categoria: f.categoria, total: apiDecimalToCents(f.total) / 100 }))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
        <XAxis type="number" tick={tickStyle} axisLine={false} tickLine={false}
          tickFormatter={v => formatBRL(Math.round(v * 100))} />
        <YAxis type="category" dataKey="categoria" tick={{ ...tickStyle, fill: '#1e293b' }} axisLine={false} tickLine={false} width={104} />
        <Tooltip formatter={value => formatBRL(Math.round(Number(value) * 100))} contentStyle={tooltipStyle} />
        <Bar dataKey="total" radius={[0, 4, 4, 0]} fill={color} barSize={22} />
      </BarChart>
    </ResponsiveContainer>
  )
}
