import {
  ResponsiveContainer, ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine,
} from 'recharts'
import { formatBRL } from '@/utils/money'
import { mesToBR } from '@/utils/dates'
import { COR_FLUXO, type ModoFluxo, type PontoFluxo } from './fluxo'

const tickStyle = { fontSize: 11, fill: '#64748b' }
const compacto = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', notation: 'compact', maximumFractionDigits: 1 })

/** Receitas × despesas × resultado por mês — `fluxoDeCaixaMensal` do `/api/erp/dashboard/`. */
export function FluxoCaixaChart({ pontos, modo }: { pontos: PontoFluxo[]; modo: ModoFluxo }) {
  // Recharts plota em reais; o tooltip lê os centavos originais do ponto.
  const chartData = pontos.map(p => ({
    ...p,
    rotulo: mesToBR(p.mes),
    vReceitas: p.receitas / 100,
    vDespesas: p.despesas / 100,
    vResultado: p.resultado / 100,
  }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={chartData} barGap={3} barCategoryGap="24%" margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
        <XAxis dataKey="rotulo" tick={tickStyle} axisLine={{ stroke: '#e2e8f0' }} tickLine={false} interval="preserveStartEnd" minTickGap={8} />
        <YAxis tick={tickStyle} axisLine={false} tickLine={false} width={72} tickFormatter={v => compacto.format(v)} />
        <ReferenceLine y={0} stroke="#cbd5e1" />
        <Tooltip
          cursor={{ fill: 'rgba(148,163,184,.12)' }}
          content={({ active, payload }) => {
            const p = active && payload?.[0]?.payload as (PontoFluxo & { rotulo: string }) | undefined
            if (!p) return null
            return (
              <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, padding: '8px 10px', fontFamily: 'var(--font-body)', fontSize: '0.78rem', boxShadow: '0 4px 12px rgba(12,26,48,.08)' }}>
                <div style={{ fontWeight: 600, marginBottom: 4, color: '#0f172a' }}>{p.rotulo}</div>
                <LinhaTooltip cor={COR_FLUXO.receitas} rotulo="Receitas" centavos={p.receitas} />
                <LinhaTooltip cor={COR_FLUXO.despesas} rotulo="Despesas" centavos={p.despesas} />
                <div style={{ borderTop: '1px solid #f1f5f9', marginTop: 4, paddingTop: 4 }}>
                  <LinhaTooltip cor={COR_FLUXO.resultado} rotulo="Resultado" centavos={p.resultado} destaque />
                </div>
              </div>
            )
          }}
        />
        <Legend iconSize={10} wrapperStyle={{ fontSize: '0.75rem', fontFamily: 'var(--font-body)' }} />
        {modo === 'barras' ? (
          <>
            <Bar dataKey="vReceitas" name="Receitas" fill={COR_FLUXO.receitas} radius={[3, 3, 0, 0]} maxBarSize={28} />
            <Bar dataKey="vDespesas" name="Despesas" fill={COR_FLUXO.despesas} radius={[3, 3, 0, 0]} maxBarSize={28} />
          </>
        ) : (
          <>
            <Line type="monotone" dataKey="vReceitas" name="Receitas" stroke={COR_FLUXO.receitas} strokeWidth={2} dot={{ r: 2.5 }} activeDot={{ r: 4 }} />
            <Line type="monotone" dataKey="vDespesas" name="Despesas" stroke={COR_FLUXO.despesas} strokeWidth={2} dot={{ r: 2.5 }} activeDot={{ r: 4 }} />
            <Line type="monotone" dataKey="vResultado" name="Resultado" stroke={COR_FLUXO.resultado} strokeWidth={2} strokeDasharray="5 4" dot={{ r: 2.5 }} activeDot={{ r: 4 }} />
          </>
        )}
      </ComposedChart>
    </ResponsiveContainer>
  )
}

function LinhaTooltip({ cor, rotulo, centavos, destaque }: { cor: string; rotulo: string; centavos: number; destaque?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, lineHeight: 1.6 }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: cor }} />
      <span style={{ color: '#475569', flex: 1 }}>{rotulo}</span>
      <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: destaque ? 600 : 500, color: destaque && centavos < 0 ? COR_FLUXO.despesas : '#0f172a', marginLeft: 12 }}>
        {formatBRL(centavos)}
      </span>
    </div>
  )
}
