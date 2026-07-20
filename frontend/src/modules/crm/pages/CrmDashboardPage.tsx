import { TrendingUp, UserPlus, Building2 } from 'lucide-react'
import { useLeads } from '../hooks/useLeads'
import { useOpportunities } from '../hooks/useOpportunities'
import { formatBRL } from '@/utils/money'
import type { StatusLead, StageOportunidade, Lead, Opportunity } from '../types'

/**
 * Dashboard do CRM - /app/crm
 * Funil visual de leads e oportunidades.
 */
export default function CrmDashboardPage() {
  const { data: leadsData, isLoading: leadsLoading } = useLeads()
  const { data: oppsData, isLoading: oppsLoading } = useOpportunities()

  // Contagem por status
  const leadsByStatus = (leadsData?.results ?? []).reduce((acc: Record<StatusLead, number>, lead: Lead) => {
    acc[lead.status] = (acc[lead.status] || 0) + 1
    return acc
  }, {} as Record<StatusLead, number>)

  // Contagem por stage
  const oppsByStage = (oppsData?.results ?? []).reduce((acc: Record<StageOportunidade, number>, opp: Opportunity) => {
    acc[opp.stage] = (acc[opp.stage] || 0) + 1
    return acc
  }, {} as Record<StageOportunidade, number>)

  const totalLeads = leadsData?.count ?? 0
  const totalOpportunities = oppsData?.count ?? 0
  const totalValue = (oppsData?.results ?? []).reduce((sum: number, opp: Opportunity) => sum + Number(opp.amount || 0), 0)

  return (
    <div className="px-6 py-8">
      {/* Cabeçalho */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#dcfce7', color: 'var(--color-brand)' }}>
          <TrendingUp size={22} />
        </div>
        <div>
          <h1 className="text-xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            CRM
          </h1>
          <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
            Gestão de leads, contas e oportunidades
          </p>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <KpiCard
          label="Total de Leads"
          value={leadsLoading ? '—' : String(totalLeads)}
          icon={<UserPlus size={18} />}
          accentBg="#dcfce7"
          accentColor="#16a34a"
        />
        <KpiCard
          label="Oportunidades"
          value={oppsLoading ? '—' : String(totalOpportunities)}
          icon={<Building2 size={18} />}
          accentBg="#dbeafe"
          accentColor="#2563eb"
        />
        <KpiCard
          label="Valor total"
          value={oppsLoading ? '—' : formatBRL(totalValue)}
          icon={<TrendingUp size={18} />}
          accentBg="#fef3c7"
          accentColor="#d97706"
        />
      </div>

      {/* Funil de Leads */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <FunnelCard
          title="Funil de Leads"
          items={[
            { label: 'Novo', count: leadsByStatus['NOVO'] || 0, color: '#3b82f6' },
            { label: 'Contatado', count: leadsByStatus['CONTATADO'] || 0, color: '#6366f1' },
            { label: 'Qualificado', count: leadsByStatus['QUALIFICADO'] || 0, color: '#8b5cf6' },
            { label: 'Convertido', count: leadsByStatus['CONVERTIDO'] || 0, color: '#10b981' },
            { label: 'Perdido', count: leadsByStatus['PERDIDO'] || 0, color: '#ef4444' },
          ]}
          isLoading={leadsLoading}
        />

        <FunnelCard
          title="Oportunidades por Etapa"
          items={[
            { label: 'Qualificação', count: oppsByStage['QUALIFICACAO'] || 0, color: '#3b82f6' },
            { label: 'Proposta', count: oppsByStage['PROPOSTA'] || 0, color: '#6366f1' },
            { label: 'Negociação', count: oppsByStage['NEGOCIACAO'] || 0, color: '#f59e0b' },
            { label: 'Ganho', count: oppsByStage['GANHO'] || 0, color: '#10b981' },
            { label: 'Perdido', count: oppsByStage['PERDIDO'] || 0, color: '#ef4444' },
          ]}
          isLoading={oppsLoading}
        />
      </div>
    </div>
  )
}

interface KpiCardProps {
  label: string
  value: string
  icon: React.ReactNode
  accentBg: string
  accentColor: string
}

function KpiCard({ label, value, icon, accentBg, accentColor }: KpiCardProps) {
  return (
    <div className="rounded-xl p-4" style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF' }}>
      <div className="flex items-center gap-3 mb-2">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: accentBg, color: accentColor }}>
          {icon}
        </div>
        <span className="text-xs font-semibold" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
          {label}
        </span>
      </div>
      <div className="text-2xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-text)' }}>
        {value}
      </div>
    </div>
  )
}

interface FunnelItem {
  label: string
  count: number
  color: string
}

function FunnelCard({ title, items, isLoading }: { title: string; items: FunnelItem[]; isLoading: boolean }) {
  const maxCount = Math.max(...items.map(i => i.count), 1)

  return (
    <div className="rounded-xl p-4" style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF' }}>
      <h2 className="text-sm font-semibold mb-3" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-text)' }}>
        {title}
      </h2>
      {isLoading ? (
        <div className="space-y-2">
          {items.map((_, i) => (
            <div key={i} className="h-8 rounded bg-gray-200 animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {items.map(item => (
            <div key={item.label} className="flex items-center gap-2">
              <div className="w-20 text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                {item.label}
              </div>
              <div className="flex-1 h-8 rounded-md relative overflow-hidden" style={{ background: '#f1f5f9' }}>
                <div
                  className="h-full rounded-md transition-all duration-300"
                  style={{
                    width: `${(item.count / maxCount) * 100}%`,
                    background: item.color,
                  }}
                />
                <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs font-semibold" style={{ color: '#FFFFFF' }}>
                  {item.count}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}