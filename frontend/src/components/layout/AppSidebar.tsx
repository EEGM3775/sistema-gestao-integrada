import React, { useState, useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Building2, HardHat, Users, Truck,
  BarChart3, UserCog, TrendingUp, Brain, Plane, Package,
  PanelLeft, Lock, ShieldCheck, Warehouse, Calculator, DatabaseZap,
  GanttChartSquare, Trash2, FileSignature, Landmark, ScrollText,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Quarteirao } from '@/components/brand/Quarteirao'
import { BairroRecorte } from '@/components/brand/BairroRecorte'

type BadgeKind = 'amber' | 'soon'

interface NavItem {
  label: string
  icon: React.ReactNode
  to: string
  module?: string       // entitlement code — se definido, item some se não tiver o módulo
  adminOnly?: boolean    // só aparece para admin do tenant
  /** Permissão do catálogo da IAM que o item exige (D116, a lixeira).
   *
   *  Diferente de `platformOnly`: isto **tranca**, não omite. A régua do dono
   *  (22/08/2026) é a intenção — porta que existe para a pessoa aparece com
   *  cadeado, e esta existe: quem não tem o papel `gestor_lixo` pode pedi-lo ao
   *  admin da empresa, que é caminho real. O que se omite é o que não é dela de
   *  jeito nenhum, e a lixeira é da empresa. */
  permission?: string
  /** O que o cadeado diz a quem não tem a `permission`. */
  semPermissao?: string
  /** Só para o supervisor da plataforma — e **omitido**, não trancado.
   *
   *  A diferença com `adminOnly` é deliberada e é decisão do dono (22/08/2026):
   *  item de tenant que a pessoa não alcança aparece com cadeado, porque é um
   *  caminho que existe para ela e ela pode contratar. Já a operação de
   *  PLATAFORMA não é isso — ela não é vendável, não é contratável e não é dela.
   *  Mostrá-la trancada anunciaria uma porta que não é para ninguém do lado de
   *  cá, e convidaria a perguntar o que tem atrás. */
  platformOnly?: boolean
  implemented: boolean   // quando false: mostra o item mas não navega (cadeado)
  badge?: { text: string; kind: BadgeKind }
}

interface NavSection {
  label: string
  items: NavItem[]
}

// Seções endereçadas como no protótipo (docs/identidade-visual §9). A régua do
// ciclo no topo é a assinatura de plataforma; cada item ativo vira "quarteirão aceso".
//
// **Calendário e Mapas não estão aqui** (26/07/2026): os dois são *transversais* —
// não são um lugar do ciclo, são uma lente sobre tudo que já existe (a agenda de
// todos os módulos; o território de obra, fornecedor e almoxarifado). Ficam como
// ícone na topbar, ao lado das notificações, que é onde mora o que se consulta a
// qualquer momento sem sair de onde se está. A sidebar segue sendo o farol dos
// lugares da edição.
const NAV_SECTIONS: NavSection[] = [
  {
    label: 'Operação',
    items: [
      { label: 'Início',          icon: <LayoutDashboard />, to: '/app/dashboard',       implemented: true },
      { label: 'Empreendimentos', icon: <Building2 />,       to: '/app/empreendimentos', implemented: true },
      { label: 'Obras',           icon: <HardHat />,         to: '/app/obras',           implemented: true },
      { label: 'Clientes',        icon: <Users />,           to: '/app/clientes',        implemented: true },
      { label: 'Fornecedores',    icon: <Truck />,           to: '/app/fornecedores',    implemented: true },
      // Os CNPJs e CPFs da conta — matriz, filiais, SPEs e os donos externos dos
      // empreendimentos em que a empresa executa (docs/modulos/entidades.md).
      { label: 'Entidades',       icon: <Landmark />,        to: '/app/entidades',       permission: 'cadastro.entidade.view', semPermissao: 'Peça ao administrador o acesso ao cadastro de entidades', implemented: true },
      // **RH é Operação, não Gestão** *(decisão do dono, 15/09/2026)*. Ele
      // estava na seção de cima por parecer "área meio" junto com ERP e CRM, e
      // a régua da seção é outra: Operação é o **cadastro do que a obra tem** —
      // empreendimento, obra, cliente, fornecedor —, e a equipe é a primeira
      // coisa dessa lista. Quem procura um funcionário procura junto de onde
      // procurou a obra em que ele está.
      { label: 'RH',              icon: <UserCog />,         to: '/app/rh',    module: 'rh', implemented: true },
    ],
  },
  {
    label: 'Gestão',
    items: [
      { label: 'ERP / Financeiro', icon: <BarChart3 />,   to: '/app/erp',        module: 'erp_financeiro', implemented: true },
      { label: 'CRM',              icon: <TrendingUp />,  to: '/app/crm',        module: 'crm',            implemented: true },
      { label: 'Diário + IA',      icon: <Brain />,       to: '/app/diario',                               implemented: true },
      { label: 'Suprimentos',      icon: <Package />,     to: '/app/scm',        module: 'scm',            implemented: true },
      { label: 'Estoque & Logística', icon: <Warehouse />, to: '/app/sil',       module: 'sil',            implemented: true },
      { label: 'Orçamento',        icon: <Calculator />,  to: '/app/orcamento',  module: 'orcamento',      implemented: true },
      // **Um item só para o PDCA** *(decisão do dono, 15/09/2026: "medição tem
      // que ficar dentro de pdca")*. A PDCA.3 chegou a ter entrada própria aqui
      // — o argumento era que o gestor de contratos não abre o Gantt (§5.3) —,
      // e o dono decidiu o contrário: o módulo é um, e a medição é uma das
      // ferramentas dele. Ela é alcançada pela obra, dentro de `/app/pdca`, que
      // é a unidade de trabalho declarada do módulo (§5.1).
      { label: 'Planejamento & Execução (PDCA)', icon: <GanttChartSquare />, to: '/app/pdca',   module: 'pdca',           implemented: true },
      { label: 'Drone',            icon: <Plane />,       to: '/app/drone',      module: 'drone',          implemented: true },
    ],
  },
  {
    label: 'Administração',
    items: [
      { label: 'Papéis e Acessos', icon: <ShieldCheck />, to: '/app/admin/papeis',   adminOnly: true, implemented: true },
      { label: 'Usuários',         icon: <Users />,       to: '/app/admin/usuarios', adminOnly: true, implemented: true },
      // Quantas assinaturas o dinheiro atravessa. Mesma classe que "Papéis e
      // Acessos" — definir alçada é decidir quem manda no dinheiro, como
      // definir papel é decidir quem vê o quê (D130).
      { label: 'Aprovações',       icon: <FileSignature />, to: '/app/admin/aprovacoes', adminOnly: true, implemented: true },
      // D17 — a trilha do sistema e a das contas numa linha do tempo.
      { label: 'Auditoria',        icon: <ScrollText />,  to: '/app/auditoria',      permission: 'plataforma.auditoria.view', implemented: true },
      { label: 'Lixo',             icon: <Trash2 />,      to: '/app/lixo',           permission: 'plataforma.lixo.view', implemented: true },
    ],
  },
  {
    // A operação da PLATAFORMA, não a da empresa. A seção inteira desaparece
    // para quem não é supervisor — ver `platformOnly` e a filtragem no render.
    label: 'Sistema',
    items: [
      { label: 'Bases oficiais', icon: <DatabaseZap />, to: '/app/sistema/bases', platformOnly: true, implemented: true },
    ],
  },
]

const RAIL = 'linear-gradient(90deg,#3E9C6E 0 25%,#E79A22 25% 50%,#E4655F 50% 75%,#1D9AA6 75%)'

function iniciais(nome: string): string {
  const partes = nome.trim().split(/[\s._-]+/).filter(Boolean)
  if (partes.length >= 2) return (partes[0][0] + partes[1][0]).toUpperCase()
  return nome.slice(0, 2).toUpperCase()
}

export const AppSidebar: React.FC = () => {
  const { hasModule, hasPermission, isTenantAdmin, isPlatformAdmin, user } = useAuth()
  const [collapsed, setCollapsed] = useState(() =>
    localStorage.getItem('sgi_sidebar_collapsed') === 'true'
  )

  useEffect(() => {
    localStorage.setItem('sgi_sidebar_collapsed', String(collapsed))
  }, [collapsed])

  // A sidebar mostra SEMPRE todos os itens (farol da plataforma — docs/identidade
  // §3.2). O que o usuário não pode acessar aparece sem interação (cadeado): item
  // não construído, módulo não contratado (`module` sem entitlement) ou item de
  // admin para não-admin. `interativo` decide NavLink × <span> travado.
  const acesso = (it: NavItem): { interativo: boolean; motivo?: string } => {
    if (!it.implemented) return { interativo: false, motivo: it.badge?.kind === 'soon' ? 'Em breve' : 'Em construção' }
    if (it.module && !hasModule(it.module)) return { interativo: false, motivo: 'Módulo não contratado' }
    if (it.adminOnly && !isTenantAdmin) return { interativo: false, motivo: 'Somente administradores' }
    if (it.permission && !hasPermission(it.permission)) return { interativo: false, motivo: it.semPermissao ?? 'Somente o gestor da lixeira' }
    return { interativo: true }
  }

  // `platformOnly` some da árvore — não vira cadeado. E a seção que ficar vazia
  // some junto, senão sobraria um título "Sistema" sem nada embaixo, que é a
  // mesma pergunta que o cadeado levantaria.
  const secoesVisiveis = NAV_SECTIONS
    .map(sec => ({ ...sec, items: sec.items.filter(it => !it.platformOnly || isPlatformAdmin) }))
    .filter(sec => sec.items.length > 0)

  const nome = user?.username ?? 'usuário'

  return (
    <aside
      className="flex flex-col shrink-0 h-full relative overflow-hidden transition-all duration-200"
      style={{
        width: collapsed ? '60px' : '236px',
        background: 'var(--surface)',
        color: 'var(--ink-2)',
        borderRight: '1px solid var(--line)',
      }}
    >
      {/* Motivo gráfico "o Bairro" — recorte do quarteirão-empresa, fade no topo */}
      {!collapsed && <BairroRecorte />}

      {/* ── Marca: marco + lockup ── */}
      <div
        className="flex items-center gap-3 relative"
        style={{ padding: collapsed ? '18px 0 12px' : '20px 20px 14px', zIndex: 1, justifyContent: collapsed ? 'center' : 'flex-start' }}
      >
        <Quarteirao size={collapsed ? 30 : 34} />
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <div style={{ fontFamily: 'var(--display)', fontWeight: 700, fontSize: 15, color: 'var(--ink)', letterSpacing: '-0.02em', lineHeight: 1.1 }}>
              SGI Plataforma
            </div>
            <div style={{ fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 600 }}>
              Do terreno à cidade
            </div>
          </div>
        )}
        {!collapsed && (
          <button
            onClick={() => setCollapsed(true)}
            aria-label="Recolher menu"
            style={{ color: 'var(--ink-3)', padding: 4, borderRadius: 6 }}
            onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--ink)')}
            onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--ink-3)')}
          >
            <PanelLeft size={17} />
          </button>
        )}
      </div>

      {/* ── Régua do ciclo: assinatura de plataforma ── */}
      <div
        title="Originar · Construir · Negociar · Operar"
        style={{ height: 3, margin: collapsed ? '0 12px 6px' : '0 20px 6px', borderRadius: 999, flex: 'none', background: RAIL, position: 'relative', zIndex: 1 }}
      />

      {collapsed && (
        <button
          onClick={() => setCollapsed(false)}
          aria-label="Expandir menu"
          className="flex items-center justify-center"
          style={{ margin: '2px auto 6px', color: 'var(--ink-3)', padding: 6, borderRadius: 6, position: 'relative', zIndex: 1 }}
          onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--ink)')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--ink-3)')}
        >
          <PanelLeft size={17} style={{ transform: 'scaleX(-1)' }} />
        </button>
      )}

      {/* ── Navegação ── */}
      <nav className="flex-1 overflow-y-auto relative" style={{ padding: '6px 12px', zIndex: 1 }}>
        {secoesVisiveis.map((sec) => (
          <div key={sec.label}>
            {!collapsed
              ? <div style={{ fontSize: 10, letterSpacing: '0.13em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700, padding: '14px 10px 6px' }}>{sec.label}</div>
              : <div style={{ height: 1, background: 'var(--line-2)', margin: '10px 8px' }} />}
            <div className="flex flex-col gap-0.5">
              {sec.items.map((item) => {
                const { interativo, motivo } = acesso(item)
                return <SidebarItem key={item.label} item={item} collapsed={collapsed} interativo={interativo} motivo={motivo} />
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* ── Rodapé: usuário ── */}
      <div
        className="flex items-center gap-2.5 relative"
        style={{ padding: 12, borderTop: '1px solid var(--line-2)', zIndex: 1, justifyContent: collapsed ? 'center' : 'flex-start' }}
      >
        <div style={{ width: 30, height: 30, borderRadius: 8, flex: 'none', background: 'linear-gradient(135deg,#274D8C,#12305F)', display: 'grid', placeItems: 'center', color: '#fff', fontWeight: 700, fontSize: 12 }}>
          {iniciais(nome)}
        </div>
        {!collapsed && (
          <div style={{ fontSize: 12, lineHeight: 1.25, minWidth: 0 }}>
            <b style={{ color: 'var(--ink)', fontWeight: 600, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{nome}</b>
            <span style={{ color: 'var(--ink-3)', fontSize: 11 }}>{isTenantAdmin ? 'Administrador' : 'Operação'}</span>
          </div>
        )}
      </div>
    </aside>
  )
}

const Badge: React.FC<{ badge: NavItem['badge'] }> = ({ badge }) => {
  if (!badge) return null
  const amber = badge.kind === 'amber'
  return (
    <span
      className="mono"
      style={{
        marginLeft: 'auto',
        fontWeight: 700,
        borderRadius: 999,
        ...(amber
          ? { fontSize: 10.5, padding: '1px 7px', background: 'var(--accent)', color: '#1A1204' }
          : { fontSize: 9, padding: '2px 6px', background: 'var(--net-soft)', color: 'var(--net-ink)', letterSpacing: '0.03em', textTransform: 'uppercase' as const }),
      }}
    >
      {badge.text}
    </span>
  )
}

const SidebarItem: React.FC<{ item: NavItem; collapsed: boolean; interativo: boolean; motivo?: string }> = ({ item, collapsed, interativo, motivo }) => {
  const base: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 11,
    padding: collapsed ? '8px' : '8px 11px',
    borderRadius: 8,
    fontSize: 13.5,
    fontWeight: 500,
    position: 'relative',
    textDecoration: 'none',
    justifyContent: collapsed ? 'center' : 'flex-start',
    transition: 'background .14s, color .14s',
  }

  const icon = (
    <span style={{ display: 'grid', placeItems: 'center', flex: 'none', width: 17, height: 17 }}>
      {React.cloneElement(
        item.icon as React.ReactElement<{ size?: number; strokeWidth?: number }>,
        { size: 17, strokeWidth: 1.9 },
      )}
    </span>
  )

  const label = !collapsed && <span className="truncate" style={{ flex: 1 }}>{item.label}</span>

  // Item sem acesso (não construído, módulo não contratado ou só-admin):
  // cadeado + opacidade, visível mas sem navegar.
  if (!interativo) {
    return (
      <span
        style={{ ...base, color: 'var(--ink-3)', opacity: 0.72, cursor: 'default' }}
        title={collapsed ? item.label : (motivo ?? item.label)}
      >
        {icon}
        {label}
        {!collapsed && (item.badge ? <Badge badge={item.badge} /> : <Lock size={12} style={{ color: 'var(--ink-3)', flexShrink: 0, marginLeft: 'auto' }} />)}
      </span>
    )
  }

  return (
    <NavLink to={item.to} title={collapsed ? item.label : undefined} style={{ textDecoration: 'none', display: 'block', borderRadius: 8 }}>
      {({ isActive }) => (
        <span
          style={{
            ...base,
            width: '100%',
            background: isActive ? 'var(--accent-soft)' : 'transparent',
            color: isActive ? 'var(--accent-ink)' : 'var(--ink-2)',
            fontWeight: isActive ? 650 : 500,
          }}
          onMouseEnter={(e) => { if (!isActive) { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.color = 'var(--ink)' } }}
          onMouseLeave={(e) => { if (!isActive) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--ink-2)' } }}
        >
          {/* quarteirão aceso: ponto âmbar à esquerda do item ativo */}
          {isActive && !collapsed && (
            <span style={{ position: 'absolute', left: -9, top: '50%', transform: 'translateY(-50%)', width: 8, height: 8, borderRadius: 2.5, background: 'var(--accent)', boxShadow: '0 0 0 3px color-mix(in srgb, var(--accent) 25%, transparent)' }} />
          )}
          {icon}
          {label}
          {item.badge && !collapsed && <Badge badge={item.badge} />}
        </span>
      )}
    </NavLink>
  )
}

export default AppSidebar
