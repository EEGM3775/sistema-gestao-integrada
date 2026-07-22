import { Link } from 'react-router-dom'
import {
  Package, ClipboardList, ShoppingCart, Tags, Landmark, FileSpreadsheet,
  Gavel, PackageCheck, ChevronRight,
} from 'lucide-react'
import { Card, KpiCard, Num } from '@/components/malha'
import { useScmDashboard } from '../hooks'
import { Spinner } from '../components/ui'

const ATALHOS = [
  { to: '/app/scm/demandas', icon: <ClipboardList size={20} />, label: 'Demandas', desc: 'Necessidades de compra e cotações' },
  { to: '/app/scm/pedidos', icon: <ShoppingCart size={20} />, label: 'Pedidos de compra', desc: 'Compra direta e cotação convergem aqui' },
  { to: '/app/scm/produtos', icon: <Package size={20} />, label: 'Produtos', desc: 'Catálogo mestre de itens' },
  { to: '/app/scm/ofertas', icon: <Tags size={20} />, label: 'Ofertas', desc: 'Preço e estoque por fornecedor' },
  { to: '/app/scm/centros-custo', icon: <Landmark size={20} />, label: 'Centros de custo', desc: 'Destino de custo das compras' },
]

export default function ScmDashboardPage() {
  const { data, isLoading } = useScmDashboard()

  return (
    <div style={{ padding: '28px 26px', maxWidth: 1180, margin: '0 auto' }}>
      {/* Faixa de abertura do hub (§9) — endereço no ciclo: Construir (âmbar). */}
      <div style={{ borderRadius: 'var(--r-xl)', padding: '26px 28px', marginBottom: 24, background: 'linear-gradient(120deg, var(--brand) 0%, #0A1626 100%)', color: '#EDF2F9', position: 'relative', overflow: 'hidden' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 700, color: '#F2AC46', marginBottom: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: 2, background: '#E79A22' }} /> Edição Construtora · Construir
        </div>
        <h1 style={{ fontFamily: 'var(--display)', fontSize: 25, fontWeight: 780, letterSpacing: '-0.02em', color: '#fff' }}>Suprimentos</h1>
        <p style={{ fontSize: 13.5, color: '#B7C3D6', marginTop: 4, maxWidth: 560 }}>
          Do catálogo à cotação, do pedido ao recebimento. Duas vias de compra — direta e cotação — convergindo num só pedido.
        </p>
      </div>

      {isLoading || !data ? (
        <div style={{ display: 'grid', placeItems: 'center', padding: 60 }}><Spinner /></div>
      ) : (
        <>
          {/* KPIs — o acento (âmbar) marca o que requer decisão: cotações a adjudicar. */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 14, marginBottom: 14 }}>
            <KpiCard label="Cotações a adjudicar" icon={<Gavel />} value={<Num>{data.cotacoesAbertas}</Num>} accent />
            <KpiCard label="Demandas abertas" icon={<ClipboardList />} value={<Num>{data.demandasAbertas}</Num>} />
            <KpiCard label="Em cotação" icon={<FileSpreadsheet />} value={<Num>{data.demandasEmCotacao}</Num>} />
            <KpiCard label="Pedidos aprovados" icon={<ShoppingCart />} value={<Num>{data.pedidosAprovados}</Num>} />
            <KpiCard label="A receber (parcial)" icon={<PackageCheck />} value={<Num>{data.pedidosRecebidosParcial + data.pedidosEnviados}</Num>} />
            <KpiCard label="Produtos ativos" icon={<Package />} value={<Num>{data.produtosAtivos}</Num>} />
            <KpiCard label="Ofertas p/ compra direta" icon={<Tags />} value={<Num>{data.ofertasDiretas}</Num>} />
          </div>

          {/* Atalhos */}
          <h2 style={{ fontFamily: 'var(--display)', fontSize: 15, fontWeight: 700, color: 'var(--ink)', margin: '22px 0 10px' }}>Atalhos</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14 }}>
            {ATALHOS.map(a => (
              <Link key={a.to} to={a.to}>
                <Card style={{ display: 'flex', alignItems: 'center', gap: 14, transition: 'box-shadow .15s, border-color .15s' }}
                  onMouseEnter={e => { e.currentTarget.style.boxShadow = 'var(--shadow-md)'; e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--accent) 40%, var(--line))' }}
                  onMouseLeave={e => { e.currentTarget.style.boxShadow = 'var(--shadow-sm)'; e.currentTarget.style.borderColor = 'var(--line)' }}>
                  <div style={{ width: 40, height: 40, borderRadius: 'var(--r-md)', flex: 'none', display: 'grid', placeItems: 'center', background: 'var(--accent-soft)', color: 'var(--accent-ink)' }}>{a.icon}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 650, color: 'var(--ink)', fontSize: 14 }}>{a.label}</div>
                    <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>{a.desc}</div>
                  </div>
                  <ChevronRight size={17} style={{ color: 'var(--ink-3)' }} />
                </Card>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
