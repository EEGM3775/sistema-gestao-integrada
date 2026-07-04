import React from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Building2, HardHat, Users, Truck, Brain, CalendarDays,
  BarChart3, UserCog, TrendingUp, Plane,
  Package, FileText, ClipboardList, Boxes, Map, Wrench,
  Lock, Construction,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'

// ─── Tipos ────────────────────────────────────────────────────────────────────

interface ModuleDef {
  code?: string          // entitlement code (undefined = módulo base)
  label: string
  description: string
  icon: React.ReactNode
  color: string          // cor de fundo do ícone
  implemented: boolean
  route?: string         // rota de navegação (quando implemented = true)
  comingSoon?: boolean
}

// ─── Catálogo de módulos ──────────────────────────────────────────────────────

const BASE_MODULES: ModuleDef[] = [
  {
    label: 'Empreendimentos',
    icon: <Building2 size={28} />,
    color: '#dbeafe',
    description: 'Cadastro e acompanhamento de empreendimentos com orçamento, contas bancárias e custos.',
    implemented: true,
    route: '/app/empreendimentos',
  },
  {
    label: 'Obras',
    icon: <HardHat size={28} />,
    color: '#fef3c7',
    description: 'Gestão de obras: etapas, cronograma, documentos, equipe e KPIs em tempo real.',
    implemented: true,
    route: '/app/obras',
  },
  {
    label: 'Clientes',
    icon: <Users size={28} />,
    color: '#dcfce7',
    description: 'Cadastro de compradores, contratos, cobranças e histórico de relacionamento.',
    implemented: true,
    route: '/app/clientes',
  },
  {
    label: 'Fornecedores',
    icon: <Truck size={28} />,
    color: '#ede9fe',
    description: 'Catálogo de fornecedores e produtos/serviços vinculados às obras e empreendimentos.',
    implemented: true,
    route: '/app/fornecedores',
  },
  {
    label: 'Diário de Obra',
    icon: <Brain size={28} />,
    color: '#e0f2fe',
    description: 'Registro diário de obra por WhatsApp com análise automática de fotos via IA.',
    implemented: true,
    route: '/app/diario',
  },
  {
    label: 'Calendário',
    icon: <CalendarDays size={28} />,
    color: '#fce7f3',
    description: 'Agenda integrada com eventos de obra, vencimentos e reuniões de toda a equipe.',
    implemented: false,
  },
]

const PAID_MODULES: ModuleDef[] = [
  {
    code: 'erp_financeiro',
    label: 'ERP Financeiro',
    icon: <BarChart3 size={28} />,
    color: '#d1fae5',
    description: 'Contas a pagar e receber, fluxo de caixa, NF-e/NFS-e e boletos integrados.',
    implemented: true,
    route: '/app/erp',
  },
  {
    code: 'rh',
    label: 'Recursos Humanos',
    icon: <UserCog size={28} />,
    color: '#fef3c7',
    description: 'Funcionários, cargos, folha de pagamento e documentos com conformidade LGPD.',
    implemented: true,
    route: '/app/rh',
  },
  {
    code: 'crm',
    label: 'CRM de Vendas',
    icon: <TrendingUp size={28} />,
    color: '#ede9fe',
    description: 'Pipeline de leads, oportunidades e contas. Do primeiro contato ao contrato assinado.',
    implemented: false,
  },
  {
    code: 'drone',
    label: 'Drone & Mapeamento',
    icon: <Plane size={28} />,
    color: '#dbeafe',
    description: 'Levantamento aéreo e modelagem 3D com NodeODM. Projetos vinculados à obra.',
    implemented: false,
  },
]

const COMING_SOON: ModuleDef[] = [
  {
    code: 'scm',
    label: 'Supply Chain',
    icon: <Boxes size={24} />,
    color: '#f3f4f6',
    description: 'Gestão de suprimentos e logística de materiais.',
    implemented: false,
    comingSoon: true,
  },
  {
    code: 'dms',
    label: 'Gestão de Documentos',
    icon: <FileText size={24} />,
    color: '#f3f4f6',
    description: 'Repositório central de projetos, licenças e contratos.',
    implemented: false,
    comingSoon: true,
  },
  {
    code: 'pdca',
    label: 'PDCA / Qualidade',
    icon: <ClipboardList size={24} />,
    color: '#f3f4f6',
    description: 'Ciclo de melhoria contínua e controle de qualidade.',
    implemented: false,
    comingSoon: true,
  },
  {
    code: 'aps',
    label: 'Planejamento (APS)',
    icon: <Wrench size={24} />,
    color: '#f3f4f6',
    description: 'Planejamento avançado de produção e recursos.',
    implemented: false,
    comingSoon: true,
  },
  {
    code: 'sil',
    label: 'Sinalização / SIL',
    icon: <Package size={24} />,
    color: '#f3f4f6',
    description: 'Gestão de sinalização e conformidade de canteiro.',
    implemented: false,
    comingSoon: true,
  },
  {
    code: 'maps',
    label: 'Mapas & GIS',
    icon: <Map size={24} />,
    color: '#f3f4f6',
    description: 'Visualização georreferenciada de obras e empreendimentos.',
    implemented: false,
    comingSoon: true,
  },
]

// ─── Componente de card ───────────────────────────────────────────────────────

interface ModuleCardProps {
  mod: ModuleDef
  acquired: boolean
}

const ModuleCard: React.FC<ModuleCardProps> = ({ mod, acquired }) => {
  const navigate = useNavigate()
  const isPaid = !!mod.code
  const locked = isPaid && !acquired
  const canAccess = mod.implemented && (!isPaid || acquired)

  return (
    <div
      className="relative flex flex-col gap-4 rounded-2xl p-6 transition-shadow duration-200"
      style={{
        background: '#FFFFFF',
        boxShadow: 'var(--shadow-sm)',
        opacity: mod.comingSoon ? 0.55 : 1,
      }}
    >
      {/* Lock badge (módulos pagos não contratados) */}
      {locked && (
        <span
          className="absolute top-4 right-4 flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full"
          style={{ background: '#fef9c3', color: '#854d0e', fontFamily: 'var(--font-body)' }}
        >
          <Lock size={10} /> Adicional
        </span>
      )}

      {/* Coming soon badge */}
      {mod.comingSoon && (
        <span
          className="absolute top-4 right-4 flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full"
          style={{ background: '#f3f4f6', color: '#6b7280', fontFamily: 'var(--font-body)' }}
        >
          <Construction size={10} /> Em breve
        </span>
      )}

      {/* Ícone */}
      <div
        className="w-14 h-14 rounded-xl flex items-center justify-center"
        style={{ background: mod.color, color: 'var(--color-brand)' }}
      >
        {mod.icon}
      </div>

      {/* Texto */}
      <div className="flex-1">
        <h3
          className="text-base font-bold mb-1.5"
          style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
        >
          {mod.label}
        </h3>
        <p
          className="text-sm leading-relaxed"
          style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}
        >
          {mod.description}
        </p>
      </div>

      {/* Botão */}
      {!mod.comingSoon && (
        <button
          disabled={!canAccess}
          onClick={() => canAccess && mod.route && navigate(mod.route)}
          className="w-full py-2.5 rounded-lg text-sm font-semibold transition-all duration-150"
          style={{
            fontFamily: 'var(--font-body)',
            cursor: canAccess ? 'pointer' : 'not-allowed',
            ...(locked
              ? { background: 'transparent', border: '1.5px solid #e2e8f0', color: '#94a3b8' }
              : canAccess
                ? { background: 'var(--color-brand)', border: 'none', color: '#FFFFFF' }
                : { background: 'var(--color-brand)', border: 'none', color: '#FFFFFF', opacity: 0.4 }
            ),
          }}
          onMouseEnter={e => {
            if (canAccess) (e.currentTarget as HTMLElement).style.background = 'var(--color-brand-dark)'
          }}
          onMouseLeave={e => {
            if (canAccess) (e.currentTarget as HTMLElement).style.background = 'var(--color-brand)'
          }}
        >
          {locked ? 'Contratar módulo' : 'Acessar'}
        </button>
      )}
    </div>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────

const AppHomePage: React.FC = () => {
  const { user, modules } = useAuth()

  const now = new Date()
  const dateStr = now.toLocaleDateString('pt-BR', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  })
  const hour = now.getHours()
  const greeting = hour < 12 ? 'Bom dia' : hour < 18 ? 'Boa tarde' : 'Boa noite'

  return (
    <div className="px-6 py-8 max-w-6xl mx-auto">

      {/* ── Cabeçalho ─────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-2 mb-10">
        <div>
          <h1
            className="text-2xl font-bold"
            style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
          >
            {greeting}, {user?.username}!
          </h1>
          <p className="text-sm mt-0.5 capitalize"
             style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
            {dateStr}
          </p>
        </div>
        <span
          className="text-xs font-semibold px-3 py-1.5 rounded-full self-start sm:self-auto"
          style={{ background: '#e8f0fb', color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}
        >
          {modules.length > 0
            ? `${modules.length} módulo${modules.length > 1 ? 's' : ''} contratado${modules.length > 1 ? 's' : ''}`
            : 'Plano base'}
        </span>
      </div>

      {/* ── Módulos base ──────────────────────────────────── */}
      <section className="mb-12">
        <div className="flex items-center gap-3 mb-5">
          <h2
            className="text-sm font-semibold uppercase tracking-widest"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}
          >
            Módulos base
          </h2>
          <span
            className="text-xs px-2 py-0.5 rounded-full font-medium"
            style={{ background: '#dcfce7', color: '#166534', fontFamily: 'var(--font-body)' }}
          >
            Inclusos
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {BASE_MODULES.map((mod) => (
            <ModuleCard key={mod.label} mod={mod} acquired={true} />
          ))}
        </div>
      </section>

      {/* ── Módulos adicionais ────────────────────────────── */}
      <section className="mb-12">
        <div className="flex items-center gap-3 mb-5">
          <h2
            className="text-sm font-semibold uppercase tracking-widest"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}
          >
            Módulos adicionais
          </h2>
          <span
            className="text-xs px-2 py-0.5 rounded-full font-medium"
            style={{ background: '#fef9c3', color: '#854d0e', fontFamily: 'var(--font-body)' }}
          >
            À la carte
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {PAID_MODULES.map((mod) => (
            <ModuleCard
              key={mod.label}
              mod={mod}
              acquired={!!mod.code && modules.includes(mod.code)}
            />
          ))}
        </div>
      </section>

      {/* ── Em desenvolvimento ────────────────────────────── */}
      <section>
        <div className="flex items-center gap-3 mb-5">
          <h2
            className="text-sm font-semibold uppercase tracking-widest"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}
          >
            Em desenvolvimento
          </h2>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          {COMING_SOON.map((mod) => (
            <div
              key={mod.label}
              className="flex flex-col items-center gap-2 p-4 rounded-xl text-center"
              style={{
                background: '#FFFFFF',
                boxShadow: 'var(--shadow-sm)',
                opacity: 0.5,
              }}
            >
              <div
                className="w-10 h-10 rounded-lg flex items-center justify-center"
                style={{ background: '#f1f5f9', color: '#94a3b8' }}
              >
                {mod.icon}
              </div>
              <span
                className="text-xs font-semibold leading-tight"
                style={{ fontFamily: 'var(--font-body)', color: '#64748b' }}
              >
                {mod.label}
              </span>
            </div>
          ))}
        </div>
      </section>

    </div>
  )
}

export default AppHomePage
