import { useMemo, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Wallet, TrendingUp, TrendingDown, Scale, ArrowRight, ArrowDownCircle, ArrowUpCircle, FileText } from 'lucide-react'
import { useErpDashboard } from '../hooks/useErpDashboard'
import { KpiCard } from '../components/shared/KpiCard'
import { FluxoCaixaChart } from '../components/charts/FluxoCaixaChart'
import { AgingChart } from '../components/charts/AgingChart'
import { formatBRL, apiDecimalToCents } from '@/utils/money'
import { mesToBR } from '@/utils/dates'
import type { AgingFaixa } from '../types'

const sumCents = (faixas: AgingFaixa[]) => faixas.reduce((acc, f) => acc + apiDecimalToCents(f.total), 0)

/**
 * Hub financeiro do ERP — `/app/erp` (D.1.0, docs/modulos/moduloerp.md §5.1/§5.5).
 * KPIs e gráficos vêm de uma única chamada a `/api/erp/dashboard/`, cacheada
 * pelo React Query; mutações em contas a pagar/receber invalidam `erpKeys.dashboard.all`
 * e este hub se atualiza sozinho (sem refresh manual).
 */
export default function ErpDashboardPage() {
  const { data, isLoading, isError, error } = useErpDashboard()

  const kpis = useMemo(() => {
    if (!data) return null
    const aReceber = sumCents(data.agingContasAReceber)
    const aPagar = sumCents(data.agingContasAPagar)
    const ultimoMes = data.fluxoDeCaixaMensal.at(-1)
    const fluxoMes = ultimoMes
      ? apiDecimalToCents(ultimoMes.receitas) - apiDecimalToCents(ultimoMes.despesas)
      : 0
    return { aReceber, aPagar, saldoProjetado: aReceber - aPagar, fluxoMes, mesReferencia: ultimoMes ? mesToBR(ultimoMes.mes) : undefined }
  }, [data])

  return (
    <div className="px-6 py-8">
      {/* Cabeçalho */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#dcfce7', color: 'var(--color-brand)' }}>
          <Wallet size={22} />
        </div>
        <div>
          <h1 className="text-xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            ERP Financeiro
          </h1>
          <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
            Visão consolidada do caixa, contas e documentos fiscais do tenant
          </p>
        </div>
      </div>

      {/* Sub-rotas — workspaces de lançamento (D.1.1) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <WorkspaceLinkCard
          to="/app/erp/contas-a-pagar"
          label="Contas a pagar"
          description="Lançamentos, rateios por centro de custo e baixas de obrigações com fornecedores"
          icon={<ArrowUpCircle size={20} />}
          accentBg="#fee2e2" accentColor="#dc2626"
        />
        <WorkspaceLinkCard
          to="/app/erp/contas-a-receber"
          label="Contas a receber"
          description="Lançamentos, rateios, emissão de NF e recebimentos de clientes"
          icon={<ArrowDownCircle size={20} />}
          accentBg="#dcfce7" accentColor="#16a34a"
        />
        <WorkspaceLinkCard
          to="/app/erp/boletos"
          label="Boletos"
          description="Cobranças emitidas via Asaas (boleto/PIX): acompanhamento, linha digitável e timeline de pagamento"
          icon={<FileText size={20} />}
          accentBg="#e0f2fe" accentColor="#0369a1"
        />
      </div>

      {isError && (
        <div className="text-sm px-4 py-3 rounded-lg mb-4"
          style={{ background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030', fontFamily: 'var(--font-body)' }}>
          Não foi possível carregar os indicadores financeiros{error instanceof Error ? `: ${error.message}` : '.'}
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KpiCard
          label="A receber (aging)"
          value={isLoading || !kpis ? '—' : formatBRL(kpis.aReceber)}
          icon={<TrendingUp size={18} />}
          accentBg="#dcfce7" accentColor="#16a34a"
        />
        <KpiCard
          label="A pagar (aging)"
          value={isLoading || !kpis ? '—' : formatBRL(kpis.aPagar)}
          icon={<TrendingDown size={18} />}
          accentBg="#fee2e2" accentColor="#dc2626"
        />
        <KpiCard
          label="Saldo projetado"
          value={isLoading || !kpis ? '—' : formatBRL(kpis.saldoProjetado)}
          icon={<Scale size={18} />}
          accentBg="#dbeafe" accentColor="#2563eb"
          sub="A receber − a pagar"
        />
        <KpiCard
          label="Fluxo do mês"
          value={isLoading || !kpis ? '—' : formatBRL(kpis.fluxoMes)}
          icon={<Wallet size={18} />}
          accentBg="#fef3c7" accentColor="#d97706"
          sub={kpis?.mesReferencia ? `Referência: ${kpis.mesReferencia}` : undefined}
        />
      </div>

      {/* Gráficos */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Fluxo de caixa mensal">
          {isLoading ? <ChartPlaceholder /> : data && data.fluxoDeCaixaMensal.length > 0
            ? <FluxoCaixaChart data={data.fluxoDeCaixaMensal} />
            : <ChartEmpty />}
        </ChartCard>

        <div className="grid grid-cols-1 gap-4">
          <ChartCard title="Aging — contas a receber">
            {isLoading ? <ChartPlaceholder height={220} /> : data && data.agingContasAReceber.length > 0
              ? <AgingChart data={data.agingContasAReceber} color="#16a34a" />
              : <ChartEmpty />}
          </ChartCard>
          <ChartCard title="Aging — contas a pagar">
            {isLoading ? <ChartPlaceholder height={220} /> : data && data.agingContasAPagar.length > 0
              ? <AgingChart data={data.agingContasAPagar} color="#dc2626" />
              : <ChartEmpty />}
          </ChartCard>
        </div>
      </div>
    </div>
  )
}

interface WorkspaceLinkCardProps {
  to: string
  label: string
  description: string
  icon: ReactNode
  accentBg: string
  accentColor: string
}

function WorkspaceLinkCard({ to, label, description, icon, accentBg, accentColor }: WorkspaceLinkCardProps) {
  return (
    <Link
      to={to}
      className="rounded-xl p-4 flex items-center gap-4 transition-colors duration-150"
      style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF', textDecoration: 'none' }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = accentColor)}
      onMouseLeave={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
    >
      <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: accentBg, color: accentColor }}>
        {icon}
      </div>
      <div className="flex-1">
        <h2 className="text-sm font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-text)' }}>{label}</h2>
        <p className="text-xs mt-0.5" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>{description}</p>
      </div>
      <ArrowRight size={18} style={{ color: 'var(--color-text-muted)' }} />
    </Link>
  )
}

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl p-4" style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF' }}>
      <h2 className="text-sm font-semibold mb-3" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-text)' }}>
        {title}
      </h2>
      {children}
    </div>
  )
}

function ChartPlaceholder({ height = 280 }: { height?: number }) {
  return (
    <div className="rounded-lg animate-pulse" style={{ height, background: '#f1f5f9' }} />
  )
}

function ChartEmpty() {
  return (
    <div className="flex items-center justify-center" style={{ height: 160, color: 'var(--color-text-muted)', fontSize: '0.85rem', fontFamily: 'var(--font-body)' }}>
      Sem dados no período.
    </div>
  )
}
