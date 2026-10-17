import { useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Wallet, TrendingUp, TrendingDown, Scale, ArrowRight, ArrowDownCircle, ArrowUpCircle, FileText, ScrollText, Lock, Building2, Settings2, HardHat } from 'lucide-react'
import { useErpDashboard } from '../hooks/useErpDashboard'
import { KpiCard } from '../components/shared/KpiCard'
import { DivergenciasErpButton } from '../components/DivergenciasErpButton'
import { FluxoCaixaPainel } from '../components/charts/FluxoCaixaPainel'
import { periodoDoAtalho } from '../components/charts/fluxo'
import { AgingChart } from '../components/charts/AgingChart'
import { formatBRL, apiDecimalToCents } from '@/utils/money'
import { mesToBR } from '@/utils/dates'
import type { AgingFaixa, PeriodoFluxo } from '../types'

const sumCents = (faixas: AgingFaixa[]) => faixas.reduce((acc, f) => acc + apiDecimalToCents(f.total), 0)

/**
 * Hub financeiro do ERP — `/app/erp` (D.1.0, docs/modulos/moduloerp.md §5.1/§5.5).
 * KPIs e gráficos vêm de uma única chamada a `/api/erp/dashboard/`, cacheada
 * pelo React Query; mutações em contas a pagar/receber invalidam `erpKeys.dashboard.all`
 * e este hub se atualiza sozinho (sem refresh manual).
 */
export default function ErpDashboardPage() {
  const [periodo, setPeriodo] = useState<PeriodoFluxo>(() => periodoDoAtalho('12m'))
  const { data, isLoading, isError, error, isPlaceholderData } = useErpDashboard(undefined, periodo)

  // Tem o módulo ERP mas não a permissão `erp.relatorio.view` → 403 no hub.
  // Em vez do banner de erro cru, degrada amigavelmente: os atalhos de
  // workspace acima seguem, só os indicadores consolidados ficam velados (F4).
  const isForbidden = (error as { response?: { status?: number } } | null)?.response?.status === 403

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
      <div className="flex items-center justify-between gap-3 mb-6">
        <div className="flex items-center gap-3">
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
        <DivergenciasErpButton />
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
          description="Parcelas por cliente, empreendimento e lote; boletos em lote, segunda via e nota fiscal"
          icon={<ArrowDownCircle size={20} />}
          accentBg="#dcfce7" accentColor="#16a34a"
        />
        <WorkspaceLinkCard
          to="/app/erp/boletos"
          label="Boletos"
          description="Boletos pelo Asaas e pelo banco: de quem é, de qual parcela e lote, e quando foi pago"
          icon={<FileText size={20} />}
          accentBg="#e0f2fe" accentColor="#0369a1"
        />
        <WorkspaceLinkCard
          to="/app/erp/cobranca-bancaria"
          label="Cobrança bancária (CNAB)"
          description="Carteiras de cobrança, arquivos de remessa e de retorno dos bancos"
          icon={<Building2 size={20} />}
          accentBg="#fef3c7" accentColor="#b45309"
        />
        <WorkspaceLinkCard
          to="/app/erp/notas-fiscais"
          label="Notas fiscais"
          description="NFS-e emitidas (NFE.io), canceladas e notas recebidas de fornecedores: status, cancelamento e PDF/XML"
          icon={<ScrollText size={20} />}
          accentBg="#ede9fe" accentColor="#6d28d9"
        />
        <WorkspaceLinkCard
          to="/app/erp/obras"
          label="Financeiro por obra"
          description="DRE de cada obra: receita, custo por etapa contra o orçado e o caixa mês a mês"
          icon={<HardHat size={20} />}
          accentBg="#ffedd5" accentColor="#c2410c"
        />
        <WorkspaceLinkCard
          to="/app/erp/configuracoes"
          label="Configurações do financeiro"
          description="Quantos boletos e notas um lote emite, dentro do que o plano permite"
          icon={<Settings2 size={20} />}
          accentBg="#f1f5f9" accentColor="#475569"
        />
      </div>

      {isForbidden ? (
        <div className="rounded-xl px-5 py-6 flex items-start gap-3"
          style={{ border: '1.5px solid #fde68a', background: '#fffbeb', fontFamily: 'var(--font-body)' }}>
          <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" style={{ background: '#fef3c7', color: '#b45309' }}>
            <Lock size={18} />
          </div>
          <div>
            <h2 className="text-sm font-bold mb-1" style={{ fontFamily: 'var(--font-heading)', color: '#92400e' }}>
              Indicadores financeiros indisponíveis
            </h2>
            <p className="text-xs" style={{ color: '#92400e', lineHeight: 1.5 }}>
              Seu acesso não inclui a visão consolidada do caixa (permissão <span className="font-semibold">erp.relatorio.view</span>).
              Os atalhos acima seguem disponíveis conforme seu acesso — fale com o administrador do tenant para liberar os indicadores.
            </p>
          </div>
        </div>
      ) : (
        <>
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

      {/* Gráficos — o fluxo na largura toda; os dois agings, compactos, lado a lado */}
      <FluxoCaixaPainel
        data={data?.fluxoDeCaixaMensal}
        periodo={data?.fluxoPeriodo ?? periodo}
        onPeriodo={setPeriodo}
        carregando={isLoading}
        atualizando={isPlaceholderData}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
        {isLoading || !data ? (
          <>
            <div className="rounded-xl animate-pulse" style={{ height: 150, background: '#f1f5f9' }} />
            <div className="rounded-xl animate-pulse" style={{ height: 150, background: '#f1f5f9' }} />
          </>
        ) : (
          <>
            <AgingChart titulo="A receber — por vencimento" data={data.agingContasAReceber} to="/app/erp/contas-a-receber" cor="#16a34a" />
            <AgingChart titulo="A pagar — por vencimento" data={data.agingContasAPagar} to="/app/erp/contas-a-pagar" cor="#dc2626" />
          </>
        )}
      </div>
        </>
      )}
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

