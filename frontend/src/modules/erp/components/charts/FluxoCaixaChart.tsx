import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import type { FluxoCaixaMes } from '../../types'

const tickStyle = { fontSize: 12, fill: '#64748b' }
const tooltipStyle = { borderRadius: 8, border: '1px solid #e2e8f0', fontFamily: 'var(--font-body)', fontSize: '0.8rem' }

/** Receitas x despesas por mês — `fluxoDeCaixaMensal` do `/api/erp/dashboard/`. */
export function FluxoCaixaChart({ data }: { data: FluxoCaixaMes[] }) {
  const chartData = data.map(m => ({
    mes: m.mes,
    receitas: apiDecimalToCents(m.receitas) / 100,
    despesas: apiDecimalToCents(m.despesas) / 100,
  }))

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartData} barGap={4}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
        <XAxis dataKey="mes" tick={tickStyle} axisLine={{ stroke: '#e2e8f0' }} tickLine={false} />
        <YAxis tick={tickStyle} axisLine={false} tickLine={false} width={88}
          tickFormatter={v => formatBRL(Math.round(v * 100))} />
        <Tooltip formatter={value => formatBRL(Math.round(Number(value) * 100))} contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: '0.8rem', fontFamily: 'var(--font-body)' }} />
        <Bar dataKey="receitas" name="Receitas" fill="#22c55e" radius={[4, 4, 0, 0]} />
        <Bar dataKey="despesas" name="Despesas" fill="#ef4444" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
