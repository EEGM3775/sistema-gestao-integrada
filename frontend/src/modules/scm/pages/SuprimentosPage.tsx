import { useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  LayoutDashboard, Tags, FileSpreadsheet, ShoppingCart, ClipboardList,
  PackageCheck, ChevronRight, Coins, Gavel, Truck, Clock, Check, Sparkles, ArrowLeft,
  Package,
  Boxes, Star, Zap, Lock, PlusCircle, Trash2,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useQuery } from '@tanstack/react-query'
import {
  useScmDashboard, cotacoesHooks, pedidosHooks, ofertasHooks, centrosCustoHooks,
  demandasHooks, itensDemandaHooks, propostasHooks, itensPropostaHooks,
  useAdjudicar, useComprarDireto, useGerarDeCotacao, useCompraAvulsa,
} from '../hooks'
import { CompraPeloCronograma } from '../components/CompraPeloCronograma'
import { PedidoDetail } from '../components/PedidoDetalhe'
import { FichaItemModal } from '../components/FichaItem'
import { cadastrarItem, cotarItens, abrirCotacaoDaDemanda } from '../api/scmApi'
import { brl, qty, dataBR, num, cotacaoEstado, demandaEstado, pedidoEstado, propostaEstado, origemPedido, type Kind } from '../lib'
import { minCalendarioISO, maxCalendarioISO } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import type { OfertaFornecedor, Cotacao, Demanda, Proposta, ItemDemanda, ItemProposta, CentroCusto } from '../types'
import apiClient from '@/api/apiClient'
import { Pill, EstadoPill, Card, Avatar, Btn, SectHead, Loading, Empty, Modal, Field } from '../components/ui'
import { mono, KIND, CAPS, inp, lerDecimal, type Say } from '../components/estilo'

let toastTimer: number | undefined

/* ─── página ─── */
type TabId = 'cockpit' | 'catalogo' | 'cotacao' | 'pedidos'
const TABS: { id: TabId; label: string; icon: ReactNode; locked?: boolean }[] = [
  { id: 'cockpit', label: 'Painel', icon: <LayoutDashboard size={15} /> }, { id: 'catalogo', label: 'Catálogo', icon: <Tags size={15} /> },
  { id: 'cotacao', label: 'Cotação', icon: <FileSpreadsheet size={15} /> }, { id: 'pedidos', label: 'Pedidos', icon: <ShoppingCart size={15} /> },
]

export default function SuprimentosPage() {
  // O título do ERP abre o pedido de origem (`?pedido=`, D284).
  const [params] = useSearchParams()
  const pedidoDoLink = Number(params.get('pedido')) || null
  const [tab, setTab] = useState<TabId>(pedidoDoLink ? 'pedidos' : 'cockpit')
  const [selCot, setSelCot] = useState<number | null>(null)
  const [selPed, setSelPed] = useState<number | null>(pedidoDoLink)
  const [toast, setToast] = useState('')
  const say: Say = (m, ms = 2800) => { setToast(m); window.clearTimeout(toastTimer); toastTimer = window.setTimeout(() => setToast(''), ms) }
  const openCot = (id: number) => { setSelCot(id); setTab('cotacao') }
  const openPed = (id: number) => { setSelPed(id); setTab('pedidos') }
  // Clicar na aba leva à lista dela, não ao último registro aberto (dono, 11/10/2026).
  const irParaAba = (t: TabId) => { setSelCot(null); setSelPed(null); setTab(t) }

  return (
    <div style={{ padding: '24px 26px 64px', maxWidth: 1240, margin: '0 auto' }}>
      <style>{`
        @keyframes scmPulse{0%{transform:scale(.6);opacity:.5}100%{transform:scale(2.2);opacity:0}}
        @keyframes scmRise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
        @keyframes scmToast{from{opacity:0;transform:translate(-50%,16px)}to{opacity:1;transform:translate(-50%,0)}}
        @keyframes scmSpin{to{transform:rotate(360deg)}}
        .scm-screen{animation:scmRise .34s cubic-bezier(.2,.7,.2,1) both}
        .scm-dot{width:6px;height:6px;border-radius:999px;background:currentColor;position:relative;flex:none;display:inline-block}
        .scm-dot::after{content:"";position:absolute;inset:-3px;border-radius:999px;background:currentColor;opacity:.35;animation:scmPulse 2s ease-out infinite}
        .scm-row:hover{background:var(--surface-2)}
        .scm-lift{transition:transform .15s,box-shadow .15s,border-color .15s}
        .scm-lift:hover{transform:translateY(-2px);box-shadow:var(--shadow-md);border-color:color-mix(in srgb,var(--accent) 40%,var(--line))}
        @media(prefers-reduced-motion:reduce){.scm-dot::after,.scm-screen,.scm-lift{animation:none;transition:none}}
      `}</style>

      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 20, flexWrap: 'wrap', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
          <div style={{ width: 42, height: 42, borderRadius: 'var(--r-md)', flex: 'none', display: 'grid', placeItems: 'center', background: 'var(--accent-soft)', color: 'var(--accent-ink)' }}><Boxes size={22} /></div>
          <div>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 10.5, letterSpacing: '0.07em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--accent-ink)', background: 'var(--accent-soft)', borderRadius: 999, padding: '2px 9px', marginBottom: 5 }}><span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--accent)' }} /> Edição Construtora · Construir</span>
            <h1 style={{ fontFamily: 'var(--display)', fontSize: 23, fontWeight: 800, letterSpacing: '-0.025em', color: 'var(--ink)', lineHeight: 1.05 }}>Suprimentos</h1>
          </div>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', flexWrap: 'wrap', gap: 3, background: 'var(--surface-2)', border: '1px solid var(--line)', padding: 4, borderRadius: 12 }}>
          {TABS.map(t => { const on = t.id === tab; return (
            <button key={t.id} onClick={() => irParaAba(t.id)} title={t.locked ? 'Bloqueado — disponível quando a Esfera de Rede for construída' : undefined} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '7px 13px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', border: 'none', color: on ? 'var(--ink)' : 'var(--ink-2)', background: on ? 'var(--surface)' : 'transparent', boxShadow: on ? 'var(--shadow-sm)' : 'none' }}>
              <span style={{ color: on ? 'var(--accent-strong)' : 'inherit', display: 'grid', placeItems: 'center' }}>{t.icon}</span>{t.label}{t.locked && <Lock size={12} style={{ color: 'var(--ink-3)', marginLeft: 1 }} />}
            </button>) })}
        </div>
      </div>

      <div className="scm-screen" key={tab + (selCot ?? '') + (selPed ?? '')}>
        {tab === 'cockpit' && <Cockpit go={irParaAba} openCot={openCot} openPed={openPed} say={say} />}
        {tab === 'catalogo' && <Catalogo say={say} onComprou={openPed} onCotou={openCot} />}
        {tab === 'cotacao' && (selCot != null ? <CotacaoDetail id={selCot} onBack={() => setSelCot(null)} openPed={openPed} say={say} /> : <CotacaoList onOpen={setSelCot} say={say} onComprou={openPed} />)}
        {tab === 'pedidos' && (selPed != null ? <PedidoDetail id={selPed} onBack={() => setSelPed(null)} say={say} /> : <PedidoList onOpen={setSelPed} say={say} onComprou={setSelPed} />)}
      </div>

      {toast && <div role="status" style={{ position: 'fixed', bottom: 24, left: '50%', maxWidth: 'min(640px, calc(100vw - 32px))', background: 'var(--ink)', color: 'var(--surface)', padding: '12px 18px', borderRadius: 11, fontSize: 13.5, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 10, zIndex: 100, boxShadow: 'var(--shadow-lg)', animation: 'scmToast .28s cubic-bezier(.2,.7,.2,1) both' }}><Check size={17} style={{ color: 'var(--good)' }} />{toast}</div>}
    </div>
  )
}

/* ═══ COCKPIT ═══ */
const ATIV: Record<string, { icon: ReactNode; kind: Kind }> = {
  recebimento: { icon: <PackageCheck size={15} />, kind: 'good' },
  adjudicacao: { icon: <Gavel size={15} />, kind: 'amber' },
  compra_direta: { icon: <ShoppingCart size={15} />, kind: 'net' },
  avaliacao: { icon: <Star size={15} />, kind: 'info' },
}
function Cockpit({ go, openCot, openPed, say }: { go: (t: TabId) => void; openCot: (id: number) => void; openPed: (id: number) => void; say: Say }) {
  const { data: d, isLoading } = useScmDashboard()
  const { data: cots } = cotacoesHooks.useList({ status: 'aberta' })
  const { hasPermission } = useAuth()
  const [novaCompra, setNovaCompra] = useState(false)
  if (isLoading || !d) return <Loading />
  const aDecidir = (cots?.results ?? []).slice(0, 6)
  const rail = [
    { icon: <ClipboardList size={18} />, k: 'Demandas', v: d.demandasAbertas, meta: 'abertas', kind: 'info' as Kind, tab: 'cotacao' as TabId },
    { icon: <FileSpreadsheet size={18} />, k: 'Em cotação', v: d.cotacoesAbertas, meta: 'a adjudicar', kind: 'amber' as Kind, pulse: d.cotacoesAbertas > 0, tab: 'cotacao' as TabId },
    { icon: <ShoppingCart size={18} />, k: 'Pedidos', v: d.pedidosAprovados, meta: 'aprovados', kind: 'net' as Kind, tab: 'pedidos' as TabId },
    { icon: <PackageCheck size={18} />, k: 'Recebendo', v: d.pedidosEnviados + d.pedidosRecebidosParcial, meta: 'a caminho / parcial', kind: 'good' as Kind, tab: 'pedidos' as TabId },
  ]
  return (
    <>
      {hasPermission('scm.pedido.criar') && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 10 }}>
          <Btn variant="primary" onClick={() => setNovaCompra(true)}><ShoppingCart size={14} /> Nova compra</Btn>
        </div>
      )}
      {novaCompra && <NovaCompraModal say={say} onClose={() => setNovaCompra(false)} onDone={id => { setNovaCompra(false); say('Pedido gerado'); openPed(id) }} />}
      <Card pad={false} style={{ marginBottom: 14, overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)' }}>
          {rail.map((s, i) => (
            <button key={s.k} onClick={() => go(s.tab)} style={{ position: 'relative', padding: '18px 20px', textAlign: 'left', background: 'none', border: 'none', borderLeft: i ? '1px solid var(--line-2)' : undefined, cursor: 'pointer' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--ink-3)' }}><span style={{ display: 'grid', placeItems: 'center', width: 30, height: 30, borderRadius: 'var(--r-sm)', background: KIND[s.kind][0], color: KIND[s.kind][1] }}>{s.icon}</span><span style={CAPS}>{s.k}</span></div>
              <div style={{ ...mono, fontSize: 30, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--ink)', marginTop: 8 }}>{s.v}</div>
              <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 5 }}>{s.pulse && <span className="scm-dot" style={{ color: 'var(--accent-ink)' }} />}{s.meta}</div>
              {i < 3 && <span style={{ position: 'absolute', right: -9, top: '50%', transform: 'translateY(-50%)', zIndex: 2, width: 18, height: 18, borderRadius: 999, background: 'var(--surface)', border: '1px solid var(--line)', display: 'grid', placeItems: 'center', color: 'var(--ink-3)' }}><ChevronRight size={11} /></span>}
            </button>
          ))}
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(210px,1fr))', gap: 14 }}>
        <Kpi accent icon={<Coins size={14} />} label="Economia em cotações" value={brl(d.economiaAdjudicadas)}
          foot={<span style={{ fontSize: 11.5, color: 'var(--ink-3)', fontWeight: 600 }}>{d.cotacoesAdjudicadas > 0 ? `em ${d.cotacoesAdjudicadas} cotação${d.cotacoesAdjudicadas > 1 ? 'ões' : ''} adjudicada${d.cotacoesAdjudicadas > 1 ? 's' : ''}` : 'sem cotações adjudicadas'}</span>} />
        <Kpi icon={<Gavel size={14} />} label="Cotações a adjudicar" value={d.cotacoesAbertas}
          foot={d.cotacoesVencemHoje > 0 ? <Pill kind="amber">{d.cotacoesVencemHoje} vence{d.cotacoesVencemHoje > 1 ? 'm' : ''} hoje</Pill> : <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>nenhuma vence hoje</span>} />
        <Kpi icon={<Truck size={14} />} label="Pedidos em trânsito" value={brl(d.pedidosTransitoValor)}
          foot={<span style={{ fontSize: 12, color: 'var(--ink-3)' }}>{d.pedidosTransitoCount} pedido{d.pedidosTransitoCount !== 1 ? 's' : ''} · {d.pedidosTransitoFornecedores} fornecedor{d.pedidosTransitoFornecedores !== 1 ? 'es' : ''}</span>} />
        <Kpi icon={<Clock size={14} />} label="Prazo médio de entrega" value={d.prazoMedioEntregaDias != null ? <>{d.prazoMedioEntregaDias.toLocaleString('pt-BR')} <small style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink-3)' }}>dias</small></> : '—'}
          foot={<span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{d.prazoMedioEntregaDias != null ? 'do pedido ao recebimento total' : 'sem recebimentos ainda'}</span>} />
      </div>

      <CompraPeloCronograma />

      <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 18, marginTop: 22, alignItems: 'start' }}>
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 16px 11px' }}><h2 style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.02em', color: 'var(--ink-2)' }}>Requer sua decisão</h2><span style={{ flex: 1, height: 1, background: 'var(--line-2)' }} /><button onClick={() => go('cotacao')} style={{ fontSize: 12.5, color: 'var(--net-ink)', fontWeight: 600, background: 'none', border: 'none', cursor: 'pointer' }}>Ver cotações →</button></div>
          {aDecidir.length === 0 ? <div style={{ padding: '8px 16px 20px', fontSize: 13, color: 'var(--ink-3)' }}>Nenhuma cotação aberta aguardando decisão.</div> : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 520 }}>
                <thead><tr>{['Demanda', 'Centro de custo', 'Prop.', 'Melhor total', 'Prazo', ''].map((h, i) => <th key={i} style={{ ...CAPS, fontSize: 10, textAlign: i >= 2 && i <= 4 ? 'right' : 'left', padding: '9px 14px', borderTop: '1px solid var(--line-2)', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' }}>{h}</th>)}</tr></thead>
                <tbody>{aDecidir.map((c, i) => <DecisaoRow key={c.cotacao_id} cot={c} openCot={openCot} last={i === aDecidir.length - 1} />)}</tbody>
              </table>
            </div>
          )}
        </Card>
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ padding: '14px 16px 8px' }}><h2 style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.02em', color: 'var(--ink-2)' }}>Atividade recente</h2></div>
          <div style={{ padding: '2px 6px 8px' }}>
            {(d.atividade ?? []).length === 0 ? <div style={{ padding: '10px 12px', fontSize: 12.5, color: 'var(--ink-3)' }}>Sem atividade ainda.</div> : d.atividade.map((a, i) => {
              const info = ATIV[a.tipo] ?? ATIV.recebimento
              return (
                <div key={i} className="scm-row" style={{ display: 'flex', gap: 12, padding: '11px 12px', borderRadius: 10 }}>
                  <span style={{ width: 30, height: 30, borderRadius: 8, flex: 'none', display: 'grid', placeItems: 'center', background: KIND[info.kind][0], color: KIND[info.kind][1] }}>{info.icon}</span>
                  <div><div style={{ fontSize: 13, color: 'var(--ink)' }}>{a.titulo}</div><div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{a.meta}</div></div>
                </div>
              )
            })}
          </div>
        </Card>
      </div>
    </>
  )
}
function Kpi({ icon, label, value, foot, accent }: { icon: ReactNode; label: string; value: ReactNode; foot?: ReactNode; accent?: boolean }) {
  return (
    <Card pad={false} style={{ padding: '16px 18px', ...(accent ? { background: 'linear-gradient(135deg,var(--accent-soft),var(--surface))', borderColor: 'color-mix(in srgb,var(--accent) 40%,var(--line))' } : {}) }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: 'var(--ink-3)', fontWeight: 600 }}>{icon} {label}</div>
      <div style={{ ...mono, fontSize: 27, fontWeight: 750, letterSpacing: '-0.03em', marginTop: 8, color: 'var(--ink)' }}>{value}</div>
      {foot && <div style={{ marginTop: 6 }}>{foot}</div>}
    </Card>
  )
}
function urgencia(dl: string | null): { label: string; kind: Kind; pulse?: boolean } | null {
  if (!dl) return null
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const diff = Math.round((new Date(dl + 'T00:00:00').getTime() - today.getTime()) / 86400000)
  if (diff < 0) return { label: 'vencida', kind: 'danger', pulse: true }
  if (diff === 0) return { label: 'vence hoje', kind: 'amber', pulse: true }
  if (diff === 1) return { label: 'vence amanhã', kind: 'amber' }
  return { label: `${diff} d restantes`, kind: 'info' }
}
// Linha da fila de decisão: puxa a demanda (título + centro de custo) e as
// propostas (melhor total + prazo) da própria cotação — dados reais por linha.
function DecisaoRow({ cot, openCot, last }: { cot: Cotacao; openCot: (id: number) => void; last: boolean }) {
  const { data: dem } = demandasHooks.useDetail(cot.demanda)
  const { data: propsData } = propostasHooks.useAll({ cotacao: cot.cotacao_id })
  const validas = ((propsData ?? []) as Proposta[]).filter(p => p.status !== 'recusada' && p.valor_total != null)
  const melhor = validas.length ? validas.reduce((a, b) => (Number(a.valor_total) <= Number(b.valor_total) ? a : b)) : null
  const urg = urgencia(cot.data_limite)
  const titulo = dem?.categoria || (dem?.observacao ? dem.observacao.slice(0, 30) : `Demanda #${cot.demanda}`)
  return (
    <tr className="scm-row" onClick={() => openCot(cot.cotacao_id)} style={{ cursor: 'pointer', borderBottom: last ? undefined : '1px solid var(--line-2)' }}>
      <td style={{ padding: '11px 14px' }}><div style={{ fontWeight: 600, color: 'var(--ink)' }}>#{cot.demanda} · {titulo}</div><div style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)' }}>Cotação #{cot.cotacao_id}</div></td>
      <td style={{ padding: '11px 14px', color: 'var(--ink-2)', fontSize: 12.5 }}>{dem?.centro_custo_nome ?? '—'}</td>
      <td style={{ ...mono, padding: '11px 14px', textAlign: 'right', color: 'var(--ink-2)' }}>{cot.propostas_count ?? validas.length}</td>
      <td style={{ ...mono, padding: '11px 14px', textAlign: 'right', fontWeight: 700, color: 'var(--ink)' }}>{brl(melhor?.valor_total)}</td>
      <td style={{ ...mono, padding: '11px 14px', textAlign: 'right', color: 'var(--ink-2)' }}>{melhor?.prazo_entrega_dias != null ? `${melhor.prazo_entrega_dias} d` : '—'}</td>
      <td style={{ padding: '11px 14px', textAlign: 'right' }}>{urg && <Pill kind={urg.kind} pulse={urg.pulse}>{urg.label}</Pill>}</td>
    </tr>
  )
}

/* ═══ CATÁLOGO ═══ */
interface ItemDoCatalogo { item_id: number; codigo_interno: string; descricao: string; unidade: string; tipo_nome: string; categoria: string; origem: string; origem_detalhe: string }
const ORIGEM: Record<string, { label: string; kind: Kind }> = {
  manual: { label: 'Cadastro', kind: 'slate' }, base: { label: 'Base de referência', kind: 'info' },
  orcamento: { label: 'Orçamento', kind: 'amber' }, compra: { label: 'Compra', kind: 'good' },
}
/** Os itens do catálogo, com a ficha (de onde veio, lojas, preços, estoque) no clique. */
function ItensDoCatalogo({ onFicha, onComprar, onCotar, marcados, onMarcar }: {
  onFicha: (id: number) => void; onComprar?: (its: ItemDoCatalogo[]) => void; onCotar?: (its: ItemDoCatalogo[]) => void
  marcados: Map<number, ItemDoCatalogo>; onMarcar: (its: ItemDoCatalogo[], marcar: boolean) => void
}) {
  const [busca, setBusca] = useState('')
  const [pagina, setPagina] = useState(1)
  const { data, isLoading } = useQuery({
    queryKey: ['scm', 'catalogo-itens', busca, pagina],
    queryFn: async () => (await apiClient.get<{ count: number; results: ItemDoCatalogo[] }>('catalogo/itens/', { params: { search: busca, page: pagina, page_size: 15, ordering: 'descricao' } })).data,
    placeholderData: prev => prev,
  })
  const itens = data?.results ?? [], total = data?.count ?? 0
  return (
    <>
      <SectHead right={<input value={busca} onChange={e => { setBusca(e.target.value); setPagina(1) }} placeholder="Buscar item (nome, código)…" style={{ fontSize: 13, padding: '7px 11px', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', background: 'var(--surface-2)', color: 'var(--ink)', minWidth: 240 }} />}>Itens do catálogo{total ? ` (${total.toLocaleString('pt-BR')})` : ''}</SectHead>
      {marcados.size > 0 && (
        <div style={{ position: 'sticky', top: 8, zIndex: 4, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '9px 14px', marginBottom: 10, borderRadius: 'var(--r-md)', background: 'var(--accent-soft)', border: '1px solid color-mix(in srgb,var(--accent) 35%,var(--line))', color: 'var(--accent-ink)', fontSize: 13, fontWeight: 600 }}>
          <span>{marcados.size} {marcados.size === 1 ? 'item selecionado' : 'itens selecionados'}</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <Btn style={{ padding: '5px 11px', fontSize: 12.5 }} onClick={() => onMarcar([...marcados.values()], false)}>Limpar</Btn>
            {onCotar && <Btn style={{ padding: '5px 11px', fontSize: 12.5 }} onClick={() => onCotar([...marcados.values()])}><FileSpreadsheet size={13} /> Cotar selecionados</Btn>}
            {onComprar && <Btn variant="primary" style={{ padding: '5px 11px', fontSize: 12.5 }} onClick={() => onComprar([...marcados.values()])}><ShoppingCart size={13} /> Comprar selecionados</Btn>}
          </div>
        </div>
      )}
      {isLoading ? <Loading /> : itens.length === 0 ? <Empty>Nenhum item{busca ? ' para a busca' : ' no catálogo ainda'}.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden', marginBottom: 6 }}>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 620 }}>
            <thead><tr>{['', 'Código', 'Item', 'Un.', 'Tipo', 'De onde veio', ''].map((h, i) => i === 0 && (onComprar || onCotar)
              ? <th key={i} style={{ width: 36, padding: '10px 0 10px 16px', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' }}>
                  <input type="checkbox" aria-label="Marcar todos desta página" checked={itens.length > 0 && itens.every(x => marcados.has(x.item_id))}
                    onChange={e => onMarcar(itens, e.target.checked)} />
                </th>
              : <th key={i} style={{ ...CAPS, fontSize: 10.5, textAlign: 'left', padding: '10px 16px', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' }}>{h}</th>)}</tr></thead>
            <tbody>{itens.map((it, i) => (
              <tr key={it.item_id} className="scm-row" style={{ cursor: 'pointer', borderBottom: i < itens.length - 1 ? '1px solid var(--line-2)' : undefined }} onClick={() => onFicha(it.item_id)}>
                {(onComprar || onCotar) ? <td style={{ width: 36, padding: '10px 0 10px 16px' }} onClick={e => e.stopPropagation()}>
                  <input type="checkbox" aria-label={`Marcar ${it.descricao}`} checked={marcados.has(it.item_id)} onChange={e => onMarcar([it], e.target.checked)} />
                </td> : <td />}
                <td style={{ ...mono, padding: '10px 16px', color: 'var(--ink-3)', fontSize: 12 }}>{it.codigo_interno}</td>
                <td style={{ padding: '10px 16px', color: 'var(--ink)', fontWeight: 500 }}>{it.descricao}{it.categoria && <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}> · {it.categoria}</span>}</td>
                <td style={{ padding: '10px 16px', color: 'var(--ink-2)' }}>{it.unidade}</td>
                <td style={{ padding: '10px 16px', color: 'var(--ink-2)', fontSize: 12.5 }}>{it.tipo_nome}</td>
                <td style={{ padding: '10px 16px' }}><Pill kind={ORIGEM[it.origem]?.kind ?? 'slate'}>{ORIGEM[it.origem]?.label ?? it.origem}</Pill>{it.origem_detalhe && <span style={{ fontSize: 11.5, color: 'var(--ink-3)', marginLeft: 6 }}>{it.origem_detalhe}</span>}</td>
                <td style={{ padding: '10px 16px', textAlign: 'right', whiteSpace: 'nowrap' }} onClick={e => e.stopPropagation()}>
                  {onCotar && <Btn style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => onCotar([it])}><FileSpreadsheet size={12} /> Cotar</Btn>}
                  {onComprar && <Btn variant="primary" style={{ padding: '4px 10px', fontSize: 12, marginLeft: 6 }} onClick={() => onComprar([it])}><ShoppingCart size={12} /> Comprar</Btn>}
                </td>
              </tr>
            ))}</tbody>
          </table></div>
        </Card>
      )}
      {total > 15 && <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--ink-3)' }}>
        <Btn style={{ padding: '4px 10px', fontSize: 12 }} disabled={pagina <= 1} onClick={() => setPagina(p => p - 1)}>Anterior</Btn>
        página {pagina} de {Math.ceil(total / 15)}
        <Btn style={{ padding: '4px 10px', fontSize: 12 }} disabled={pagina >= Math.ceil(total / 15)} onClick={() => setPagina(p => p + 1)}>Próxima</Btn>
      </div>}
    </>
  )
}

function Catalogo({ say, onComprou, onCotou }: { say: Say; onComprou: (id: number) => void; onCotou: (id: number) => void }) {
  const { hasPermission } = useAuth()
  const podeComprar = hasPermission('scm.pedido.criar'), podeCotar = hasPermission('scm.demanda.edit')
  const [compraDe, setCompraDe] = useState<ItemDoCatalogo[] | null>(null)
  const [cotacaoDe, setCotacaoDe] = useState<ItemDoCatalogo[] | null>(null)
  // A seleção sobrevive à troca de página e à busca: marca-se aqui e ali, compra-se junto.
  const [marcados, setMarcados] = useState<Map<number, ItemDoCatalogo>>(new Map())
  const marcar = (its: ItemDoCatalogo[], on: boolean) => setMarcados(prev => {
    const novo = new Map(prev)
    for (const it of its) on ? novo.set(it.item_id, it) : novo.delete(it.item_id)
    return novo
  })
  const [search, setSearch] = useState('')
  const [comprar, setComprar] = useState<OfertaFornecedor | null>(null)
  const [ficha, setFicha] = useState<number | null>(null)
  const { data, isLoading } = ofertasHooks.useList({ search, page_size: 24 })
  const rows = data?.results ?? []
  return (
    <>
      <ItensDoCatalogo onFicha={setFicha} onComprar={podeComprar ? setCompraDe : undefined} onCotar={podeCotar ? setCotacaoDe : undefined} marcados={marcados} onMarcar={marcar} />
      {ficha != null && <FichaItemModal item={ficha} onClose={() => setFicha(null)} />}
      {compraDe && <NovaCompraModal say={say} iniciais={compraDe.map(it => ({ produto: it.item_id, descricao: it.descricao, unidade: it.unidade }))} onClose={() => setCompraDe(null)} onDone={id => { setCompraDe(null); setMarcados(new Map()); say('Pedido gerado'); onComprou(id) }} />}
      {cotacaoDe && <CotarModal itens={cotacaoDe} onClose={() => setCotacaoDe(null)} onDone={id => { setCotacaoDe(null); setMarcados(new Map()); say('Cotação aberta'); onCotou(id) }} />}
      <SectHead right={<input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar oferta…" style={{ fontSize: 13, padding: '7px 11px', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', background: 'var(--surface-2)', color: 'var(--ink)', minWidth: 220 }} />}>Ofertas das lojas</SectHead>
      {isLoading ? <Loading /> : rows.length === 0 ? <Empty>Nenhuma oferta no catálogo{search ? ' para a busca' : ''}.</Empty> : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(268px,1fr))', gap: 14 }}>
          {rows.map(o => {
            const disp = num(o.estoque_disponivel) ?? 0, livre = num(o.estoque_livre) ?? disp, frac = disp > 0 ? Math.max(0, Math.min(1, livre / disp)) : 0
            return (
              <Card key={o.oferta_id} className="scm-lift" style={{ display: 'flex', flexDirection: 'column', gap: 12, opacity: o.ativo ? 1 : 0.6 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 'var(--r-md)', flex: 'none', display: 'grid', placeItems: 'center', background: 'var(--inset)', color: 'var(--ink-2)' }}><Package size={20} /></div>
                  <div style={{ flex: 1, minWidth: 0 }}><button type="button" onClick={() => setFicha(o.produto)} style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left', fontWeight: 650, fontSize: 14, color: 'var(--ink)', lineHeight: 1.3 }}>{o.produto_descricao ?? `#${o.produto}`}</button><div style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>{o.produto_codigo ?? ''} · {o.fornecedor_nome ?? `#${o.fornecedor}`}</div></div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', paddingTop: 10, borderTop: '1px solid var(--line-2)' }}><span style={{ fontSize: 11, color: 'var(--ink-3)', fontWeight: 600 }}>Preço direto</span><span style={{ ...mono, fontWeight: 700, fontSize: 16, color: 'var(--ink)' }}>{brl(o.preco_direto)}</span></div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ flex: 1, height: 6, borderRadius: 999, background: 'var(--inset)', overflow: 'hidden' }}><span style={{ display: 'block', height: '100%', width: `${frac * 100}%`, background: frac > 0.15 ? 'var(--good)' : 'var(--danger)' }} /></span><span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>{qty(livre)} {o.produto_unidade ?? ''}</span></div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>{o.compra_direta ? <Pill kind="net">Compra direta</Pill> : <Pill>Só cotação</Pill>}{podeComprar && o.compra_direta && o.ativo && <Btn variant="primary" style={{ marginLeft: 'auto', padding: '6px 12px', fontSize: 12.5 }} onClick={() => setComprar(o)}><ShoppingCart size={13} /> Comprar</Btn>}</div>
              </Card>
            )
          })}
        </div>
      )}
      {comprar && <ComprarModal oferta={comprar} onClose={() => setComprar(null)} onDone={id => { setComprar(null); say('Pedido gerado por compra direta'); onComprou(id) }} />}
    </>
  )
}

/* ═══ COTAÇÃO ═══ */
/** As demandas que esperam decisão: cada uma vira cotação ou vai direto à compra. */
function DemandasAbertas({ onCotou, onComprou, say }: { onCotou: (cotacao: number) => void; onComprou: (pedido: number) => void; say: Say }) {
  const { hasPermission } = useAuth()
  const podeCotar = hasPermission('scm.demanda.edit'), podeComprar = hasPermission('scm.pedido.criar')
  const { data, isLoading } = demandasHooks.useList({ page_size: 50 })
  const [ocupada, setOcupada] = useState<number | null>(null)
  const [compra, setCompra] = useState<{ demanda: Demanda; linhas: LinhaInicial[] } | null>(null)
  const [erro, setErro] = useState('')
  const [marcadas, setMarcadas] = useState<Set<number>>(new Set())
  const remover = demandasHooks.useRemove()
  const rows = (data?.results ?? []).filter(d => d.status === 'rascunho' || d.status === 'aberta' || d.status === 'em_cotacao')
  if (isLoading || rows.length === 0) return null
  const alternar = (ids: number[], on: boolean) => setMarcadas(prev => { const n = new Set(prev); for (const id of ids) on ? n.add(id) : n.delete(id); return n })
  /** Apaga uma a uma; as que já têm pedido ou proposta o servidor recusa e o motivo aparece. */
  const excluir = async (ids: number[]) => {
    if (!window.confirm(ids.length === 1 ? `Apagar a demanda #${ids[0]}? Isso não pode ser desfeito.` : `Apagar ${ids.length} demandas? Isso não pode ser desfeito.`)) return
    setErro('')
    const falhas: string[] = []
    let apagadas = 0
    for (const id of ids) {
      try { await remover.mutateAsync(id); apagadas++ }
      catch (e) { falhas.push(Object.values(parseApiErrors(e))[0] ?? `Não foi possível apagar a #${id}.`) }
    }
    setMarcadas(new Set())
    if (apagadas) say(apagadas === 1 ? 'Demanda apagada' : `${apagadas} demandas apagadas`)
    if (falhas.length) setErro(falhas.join(' '))
  }
  const cotar = async (d: Demanda) => {
    setErro(''); setOcupada(d.demanda_id)
    try { const r = await abrirCotacaoDaDemanda(d.demanda_id); say('Cotação aberta'); onCotou(r.cotacao_id) }
    catch (e) { setErro(Object.values(parseApiErrors(e))[0] ?? 'Não foi possível abrir a cotação.') }
    setOcupada(null)
  }
  const comprar = async (d: Demanda) => {
    setErro(''); setOcupada(d.demanda_id)
    try {
      const { data: itens } = await apiClient.get<ItemDemanda[]>('scm/itens-demanda/', { params: { demanda: d.demanda_id } })
      const faltam = itens.filter(i => (num(i.saldo ?? i.quantidade) ?? 0) > 0)
      if (faltam.length === 0) setErro('A demanda não tem itens a comprar.')
      else setCompra({
        demanda: d,
        linhas: faltam.map(i => ({ produto: i.produto, descricao: i.produto ? (i.produto_descricao ?? '') : i.descricao_servico, unidade: i.unidade, quantidade: i.saldo ?? i.quantidade })),
      })
    } catch (e) { setErro(Object.values(parseApiErrors(e))[0] ?? 'Não foi possível ler os itens da demanda.') }
    setOcupada(null)
  }
  return (
    <>
      <SectHead right={podeCotar && marcadas.size > 0
        ? <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--ink-2)' }}>
            {marcadas.size} selecionada{marcadas.size > 1 ? 's' : ''}
            <Btn style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => setMarcadas(new Set())}>Limpar</Btn>
            <Btn variant="danger" style={{ padding: '4px 10px', fontSize: 12 }} disabled={remover.isPending} onClick={() => excluir([...marcadas])}><Trash2 size={12} /> Apagar selecionadas</Btn>
          </div> : undefined}>Demandas para decidir ({rows.length})</SectHead>
      {erro &&<div style={{ background: 'var(--danger-soft)', color: 'var(--danger-ink)', padding: '9px 12px', borderRadius: 'var(--r-sm)', fontSize: 12.5, marginBottom: 10 }}>{erro}</div>}
      <Card pad={false} style={{ overflow: 'hidden', marginBottom: 18 }}>
        <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5, minWidth: 620 }}>
          <thead><tr>{['', 'Demanda', 'Origem', 'Centro de custo', 'Itens', 'Estado', ''].map((h, i) => i === 0
            ? <th key={i} style={{ width: 36, padding: '11px 0 11px 16px', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' }}>
                {podeCotar && <input type="checkbox" aria-label="Marcar todas" checked={rows.every(d => marcadas.has(d.demanda_id))} onChange={e => alternar(rows.map(d => d.demanda_id), e.target.checked)} />}
              </th>
            : <th key={i} style={{ ...CAPS, fontSize: 10.5, textAlign: i === 4 ? 'right' : 'left', padding: '11px 16px', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' }}>{h}</th>)}</tr></thead>
          <tbody>{rows.map((d, i) => (
            <tr key={d.demanda_id} style={{ borderBottom: i < rows.length - 1 ? '1px solid var(--line-2)' : undefined }}>
              <td style={{ width: 36, padding: '12px 0 12px 16px' }}>{podeCotar && <input type="checkbox" aria-label={`Marcar demanda #${d.demanda_id}`} checked={marcadas.has(d.demanda_id)} onChange={e => alternar([d.demanda_id], e.target.checked)} />}</td>
              <td style={{ ...mono, padding: '12px 16px', fontWeight: 700, color: 'var(--ink)' }}>#{d.demanda_id}{d.observacao && <div style={{ fontFamily: 'var(--sans)', fontWeight: 400, fontSize: 11.5, color: 'var(--ink-3)', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.observacao}</div>}</td>
              <td style={{ padding: '12px 16px', color: 'var(--ink-2)', fontSize: 12.5, textTransform: 'capitalize' }}>{d.origem}</td>
              <td style={{ padding: '12px 16px', color: 'var(--ink-3)', fontSize: 12.5 }}>{d.centro_custo_nome ?? '—'}</td>
              <td style={{ ...mono, padding: '12px 16px', textAlign: 'right', color: 'var(--ink-2)' }}>{d.itens_count ?? 0}</td>
              <td style={{ padding: '12px 16px' }}><EstadoPill e={demandaEstado[d.status]} /></td>
              <td style={{ padding: '12px 16px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                {podeCotar && <Btn style={{ padding: '4px 10px', fontSize: 12 }} disabled={ocupada === d.demanda_id} onClick={() => cotar(d)}><FileSpreadsheet size={12} /> Abrir cotação</Btn>}
                {podeComprar && <Btn variant="primary" style={{ padding: '4px 10px', fontSize: 12, marginLeft: 6 }} disabled={ocupada === d.demanda_id} onClick={() => comprar(d)}><ShoppingCart size={12} /> Comprar</Btn>}
                {podeCotar && <Btn variant="danger" style={{ padding: '4px 8px', fontSize: 12, marginLeft: 6 }} title="Apagar demanda" aria-label={`Apagar demanda #${d.demanda_id}`} disabled={remover.isPending} onClick={() => excluir([d.demanda_id])}><Trash2 size={12} /></Btn>}
              </td>
            </tr>
          ))}</tbody>
        </table></div>
      </Card>
      {compra && <NovaCompraModal say={say} iniciais={compra.linhas} demanda={{ id: compra.demanda.demanda_id, centro_custo: compra.demanda.centro_custo }}
        onClose={() => setCompra(null)} onDone={id => { setCompra(null); say('Pedido gerado da demanda'); onComprou(id) }} />}
    </>
  )
}

function CotacaoList({ onOpen, say, onComprou }: { onOpen: (id: number) => void; say: Say; onComprou: (id: number) => void }) {
  const { data, isLoading } = cotacoesHooks.useList({})
  const rows = data?.results ?? []
  if (isLoading) return <Loading />
  if (rows.length === 0) return <><DemandasAbertas onCotou={onOpen} onComprou={onComprou} say={say} /><SectHead>Cotações</SectHead><Empty>Nenhuma cotação ainda. Abra uma pela demanda acima, ou cote direto do Catálogo.</Empty></>
  return (
    <>
      <DemandasAbertas onCotou={onOpen} onComprou={onComprou} say={say} />
      <SectHead>Cotações</SectHead>
      <Card pad={false} style={{ overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5, minWidth: 560 }}>
          <thead><tr>{['Cotação', 'Demanda', 'Estado', 'Propostas', 'Encerra'].map((h, i) => <th key={i} style={{ ...CAPS, fontSize: 10.5, textAlign: i === 3 ? 'right' : 'left', padding: '11px 16px', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' }}>{h}</th>)}</tr></thead>
          <tbody>{rows.map((c, i) => (
            <tr key={c.cotacao_id} className="scm-row" style={{ cursor: 'pointer', borderBottom: i < rows.length - 1 ? '1px solid var(--line-2)' : undefined }} onClick={() => onOpen(c.cotacao_id)}>
              <td style={{ ...mono, padding: '13px 16px', fontWeight: 700, color: 'var(--ink)' }}>#{c.cotacao_id}</td>
              <td style={{ ...mono, padding: '13px 16px', color: 'var(--ink-3)' }}>#{c.demanda}</td>
              <td style={{ padding: '13px 16px' }}><EstadoPill e={cotacaoEstado[c.status]} /></td>
              <td style={{ ...mono, padding: '13px 16px', textAlign: 'right', color: 'var(--ink-2)' }}>{c.propostas_count ?? 0}</td>
              <td style={{ ...mono, padding: '13px 16px', fontSize: 12, color: 'var(--ink-3)' }}>{dataBR(c.data_limite)}</td>
            </tr>
          ))}</tbody>
        </table></div>
      </Card>
    </>
  )
}

const H = { head: 122, cell: 66, total: 80, act: 70 }
function CotacaoDetail({ id, onBack, openPed, say }: { id: number; onBack: () => void; openPed: (id: number) => void; say: Say }) {
  const { hasPermission } = useAuth()
  const podeAdjudicar = hasPermission('scm.cotacao.adjudicar'), podeGerar = hasPermission('scm.pedido.criar')
  const { data: cot, isLoading } = cotacoesHooks.useDetail(id)
  const { data: itens } = itensDemandaHooks.useAll({ demanda: cot?.demanda ?? 0 }, cot?.demanda != null)
  const { data: propostas } = propostasHooks.useAll({ cotacao: id })
  const { data: itensProp } = itensPropostaHooks.useAll({ proposta__cotacao: id })
  const { data: demanda } = demandasHooks.useDetail(cot?.demanda)
  const adjudicar = useAdjudicar(), gerar = useGerarDeCotacao()
  const [direto, setDireto] = useState(false)

  const lista = useMemo(() => (itens ?? []) as ItemDemanda[], [itens])
  const props = useMemo(() => (propostas ?? []) as Proposta[], [propostas])
  const cells = useMemo(() => { const m = new Map<string, string>(); for (const ip of (itensProp ?? []) as ItemProposta[]) m.set(`${ip.proposta}:${ip.item_demanda}`, ip.preco_unitario); return m }, [itensProp])
  const menorItem = useMemo(() => { const mn = new Map<number, number>(); for (const it of lista) { let m: number | null = null; for (const p of props) { const v = num(cells.get(`${p.proposta_id}:${it.item_demanda_id}`)); if (v != null && (m == null || v < m)) m = v } if (m != null) mn.set(it.item_demanda_id, m) } return mn }, [lista, props, cells])
  const totais = props.filter(p => p.status !== 'recusada').map(p => num(p.valor_total)).filter((v): v is number => v != null)
  const menorTotal = totais.length ? Math.min(...totais) : null
  const recomendada = useMemo(() => { const val = props.filter(p => p.status !== 'recusada' && p.valor_total != null); return val.length ? val.reduce((a, b) => (Number(a.valor_total) <= Number(b.valor_total) ? a : b)) : null }, [props])

  if (isLoading || !cot) return <Loading />
  const adjudicada = cot.status === 'adjudicada'

  return (
    <>
      <button onClick={onBack} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--ink-3)', background: 'none', border: 'none', cursor: 'pointer', marginBottom: 6 }}><ArrowLeft size={13} /> Todas as cotações</button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 4 }}>
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 19, fontWeight: 750, letterSpacing: '-0.02em', color: 'var(--ink)' }}>Cotação #{cot.cotacao_id}</h2>
        <EstadoPill e={cotacaoEstado[cot.status]} />
        {cot.data_limite && <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>encerra <b className="mono">{dataBR(cot.data_limite)}</b></span>}
        {adjudicada && podeGerar && <Btn variant="primary" style={{ marginLeft: 'auto' }} onClick={async () => { const p = await gerar.mutateAsync(id); say('Pedido gerado da cotação'); openPed(p.pedido_id) }} disabled={gerar.isPending}><ShoppingCart size={14} /> Gerar pedido</Btn>}
        {cot.status === 'aberta' && podeGerar && lista.some(i => (num(i.saldo ?? i.quantidade) ?? 0) > 0) && <Btn variant="primary" style={{ marginLeft: 'auto' }} title="Compra os itens da demanda sem esperar proposta: escolha o fornecedor e os preços" onClick={() => setDireto(true)}><ShoppingCart size={14} /> Gerar pedido</Btn>}
      </div>
      {direto && cot.demanda != null && <NovaCompraModal say={say}
        iniciais={lista.filter(i => (num(i.saldo ?? i.quantidade) ?? 0) > 0).map(i => ({ produto: i.produto, descricao: i.produto ? (i.produto_descricao ?? '') : i.descricao_servico, unidade: i.unidade, quantidade: i.saldo ?? i.quantidade }))}
        demanda={{ id: cot.demanda, centro_custo: demanda?.centro_custo ?? null }}
        onClose={() => setDireto(false)} onDone={id => { setDireto(false); say('Pedido gerado da cotação'); openPed(id) }} />}

      {props.length === 0 ? <Empty>Nenhuma proposta registrada nesta cotação ainda.</Empty> : (
        <>
          <SectHead right={<span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>menor por linha em verde</span>}>Mapa comparativo de propostas</SectHead>
          <div style={{ overflowX: 'auto' }}>
            <div style={{ display: 'grid', gridTemplateColumns: `220px repeat(${props.length},minmax(190px,1fr))`, border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden', background: 'var(--surface)', minWidth: 560 }}>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <div style={{ height: H.head, padding: 16, background: 'var(--surface-2)', borderBottom: '1px solid var(--line)', display: 'flex', alignItems: 'flex-end' }}><span style={CAPS}>Item da demanda</span></div>
                {lista.map(it => <div key={it.item_demanda_id} style={{ height: H.cell, padding: 16, borderBottom: '1px solid var(--line-2)', background: 'var(--surface-2)', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}><b style={{ fontSize: 13.5, fontWeight: 650, color: 'var(--ink)' }}>{it.produto_descricao ?? it.descricao_servico ?? `Item #${it.item_demanda_id}`}</b><span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{qty(it.quantidade)} {it.unidade || 'un'}</span></div>)}
                <div style={{ height: H.total, padding: 16, borderTop: '2px solid var(--line)', background: 'var(--surface-2)', display: 'flex', alignItems: 'center' }}><span style={CAPS}>Total da proposta</span></div>
                <div style={{ height: H.act, borderTop: '1px solid var(--line-2)', background: 'var(--surface-2)' }} />
              </div>
              {props.map(p => {
                const rec = recomendada?.proposta_id === p.proposta_id && !adjudicada, win = p.status === 'vencedora'
                const val = num(p.valor_total), dl = val != null && menorTotal != null && menorTotal > 0 && val !== menorTotal ? ((val - menorTotal) / menorTotal) * 100 : null
                return (
                  <div key={p.proposta_id} style={{ display: 'flex', flexDirection: 'column', borderLeft: '1px solid var(--line-2)', ...(win ? { boxShadow: 'inset 0 0 0 2px var(--good)', background: 'linear-gradient(180deg,var(--good-soft),transparent 32%)' } : rec ? { boxShadow: 'inset 0 0 0 2px var(--accent)', background: 'linear-gradient(180deg,var(--accent-soft),transparent 32%)' } : {}) }}>
                    <div style={{ height: H.head, padding: '14px 16px', borderBottom: '1px solid var(--line)', display: 'flex', flexDirection: 'column', gap: 7 }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Avatar name={p.fornecedor_label ?? p.fornecedor_nome ?? '?'} size={24} /><b style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>{p.fornecedor_label ?? p.fornecedor_nome}</b></span>
                      <StarsMini media={p.fornecedor_avaliacao_media} count={p.fornecedor_avaliacao_count} prazo={p.prazo_entrega_dias} />
                      <span>{win ? <Pill kind="good"><Check size={12} /> Vencedora</Pill> : rec ? <Pill kind="amber"><Sparkles size={12} /> Menor total</Pill> : <EstadoPill e={propostaEstado[p.status]} />}</span>
                    </div>
                    {lista.map(it => {
                      const pr = cells.get(`${p.proposta_id}:${it.item_demanda_id}`), v = num(pr)
                      const cmp = props.reduce((n, q) => n + (num(cells.get(`${q.proposta_id}:${it.item_demanda_id}`)) != null ? 1 : 0), 0)
                      const best = cmp >= 2 && v != null && v === menorItem.get(it.item_demanda_id)
                      return (
                        <div key={it.item_demanda_id} style={{ height: H.cell, padding: '10px 16px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 1, background: best ? 'var(--good-soft)' : undefined }}>
                          <span style={{ ...mono, fontSize: 14, fontWeight: best ? 700 : 500, color: best ? 'var(--good-ink)' : v != null ? 'var(--ink)' : 'var(--ink-3)' }}>{pr ? brl(pr) : '—'}</span>
                          {v != null && <span style={{ ...mono, fontSize: 10.5, color: 'var(--ink-3)' }}>= {brl(v * (num(it.quantidade) ?? 0))}</span>}
                          {best && <span style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--good-ink)' }}>menor</span>}
                        </div>
                      )
                    })}
                    <div style={{ height: H.total, padding: '12px 16px', borderTop: '2px solid var(--line)', textAlign: 'right', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                      <span style={{ ...mono, fontSize: 19, fontWeight: 750, color: 'var(--ink)' }}>{brl(p.valor_total)}</span>
                      {p.status !== 'recusada' && <span style={{ fontSize: 11, fontWeight: 600, color: val === menorTotal ? 'var(--good-ink)' : 'var(--ink-3)' }}>{val === menorTotal ? 'menor total' : dl != null ? `+${dl.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%` : ''}</span>}
                    </div>
                    <div style={{ height: H.act, padding: '14px 16px', borderTop: '1px solid var(--line-2)', display: 'flex', alignItems: 'center' }}>
                      {!adjudicada && podeAdjudicar && p.status !== 'recusada' && <Btn variant={rec ? 'primary' : 'ghost'} style={{ width: '100%', justifyContent: 'center', padding: '7px' }} onClick={() => { adjudicar.mutate({ cotacao: id, proposta: p.proposta_id }); say(`Cotação adjudicada a ${p.fornecedor_label ?? p.fornecedor_nome}`) }} disabled={adjudicar.isPending}><Check size={14} /> Adjudicar</Btn>}
                      {win && <Pill kind="good"><Check size={12} /> Adjudicada</Pill>}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 15, padding: '18px 20px', borderRadius: 'var(--r-lg)', marginTop: 18, background: 'linear-gradient(120deg,var(--net-soft),var(--surface) 78%)', border: '1px solid color-mix(in srgb,var(--net) 32%,var(--line))' }}>
            <div style={{ width: 40, height: 40, borderRadius: 'var(--r-md)', flex: 'none', display: 'grid', placeItems: 'center', background: 'var(--net)', color: '#fff', boxShadow: '0 4px 14px color-mix(in srgb,var(--net) 45%,transparent)' }}><Sparkles size={20} /></div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9, fontFamily: 'var(--display)', fontWeight: 700, fontSize: 14, color: 'var(--ink)', marginBottom: 5 }}>Assistente de compras <Pill kind="net">IA · em breve</Pill></div>
              <div style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.55 }}>{recomendada ? <>Menor total agora: <b style={{ color: 'var(--ink)' }}>{recomendada.fornecedor_label ?? recomendada.fornecedor_nome}</b> ({brl(recomendada.valor_total)}). A recomendação automática vai ponderar <b>preço</b>, <b>prazo</b> e a <b>reputação</b> do fornecedor — por ora, o verde marca o menor por item e a moldura, o menor total.</> : 'Registre propostas para o comparativo.'}</div>
            </div>
          </div>
        </>
      )}
    </>
  )
}
function StarsMini({ media, count, prazo }: { media?: string | null; count?: number; prazo?: number | null }) {
  const m = media == null || media === '' ? null : Number(media)
  return <span style={{ fontSize: 11, color: 'var(--ink-3)', display: 'inline-flex', alignItems: 'center', gap: 5 }}>{m == null ? <span>sem avaliação</span> : <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}><Star size={11} style={{ color: 'var(--accent)', fill: 'var(--accent)' }} /><b className="mono" style={{ color: 'var(--ink-2)' }}>{m.toFixed(1)}</b>{count ? ` (${count})` : ''}</span>}{prazo != null && <span>· {prazo} d</span>}</span>
}

/* ═══ PEDIDOS ═══ */
function PedidoList({ onOpen, say, onComprou }: { onOpen: (id: number) => void; say: Say; onComprou: (id: number) => void }) {
  const { hasPermission } = useAuth()
  const podeComprar = hasPermission('scm.pedido.criar')
  const { data, isLoading } = pedidosHooks.useList({})
  const [comprar, setComprar] = useState(false)
  const rows = data?.results ?? []
  return (
    <>
      <SectHead right={podeComprar ? <Btn variant="primary" style={{ padding: '6px 12px', fontSize: 12.5 }} onClick={() => setComprar(true)}><Zap size={14} /> Nova compra</Btn> : undefined}>Pedidos de compra</SectHead>
      {isLoading ? <Loading /> : rows.length === 0 ? <Empty>Nenhum pedido ainda.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5, minWidth: 720 }}>
            <thead><tr>{['Pedido', 'Via', 'Fornecedor', 'Centro de custo', 'Valor', 'Data', 'Estado'].map((h, i) => <th key={i} style={{ ...CAPS, fontSize: 10.5, textAlign: i === 4 ? 'right' : 'left', padding: '11px 16px', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' }}>{h}</th>)}</tr></thead>
            <tbody>{rows.map((p, i) => (
              <tr key={p.pedido_id} className="scm-row" style={{ cursor: 'pointer', borderBottom: i < rows.length - 1 ? '1px solid var(--line-2)' : undefined }} onClick={() => onOpen(p.pedido_id)}>
                <td style={{ ...mono, padding: '13px 16px', fontWeight: 700, color: 'var(--ink)' }}>#{p.pedido_id}</td>
                <td style={{ padding: '13px 16px' }}><Pill kind={origemPedido[p.origem].kind}>{origemPedido[p.origem].label}</Pill></td>
                <td style={{ padding: '13px 16px' }}><span style={{ display: 'flex', alignItems: 'center', gap: 9 }}><Avatar name={p.fornecedor_nome ?? '?'} size={24} /><span style={{ color: 'var(--ink)' }}>{p.fornecedor_nome ?? `#${p.fornecedor}`}</span></span></td>
                <td style={{ ...mono, padding: '13px 16px', fontSize: 12, color: 'var(--ink-3)' }}>{p.centro_custo_nome ?? '—'}</td>
                <td style={{ ...mono, padding: '13px 16px', textAlign: 'right', fontWeight: 700, color: 'var(--ink)' }}>{brl(p.valor_total)}</td>
                <td style={{ ...mono, padding: '13px 16px', fontSize: 12, color: 'var(--ink-3)' }}>{dataBR(p.data_pedido)}</td>
                <td style={{ padding: '13px 16px' }}><EstadoPill e={pedidoEstado[p.status]} /></td>
              </tr>
            ))}</tbody>
          </table></div>
        </Card>
      )}
      {comprar && <NovaCompraModal say={say} onClose={() => setComprar(false)} onDone={id => { setComprar(false); say('Pedido gerado'); onComprou(id) }} />}
    </>
  )
}

/* ═══ modais ═══ */

function ComprarModal({ oferta, onClose, onDone }: { oferta?: OfertaFornecedor; onClose: () => void; onDone: (id: number) => void }) {
  const comprar = useComprarDireto()
  const { data: cc } = centrosCustoHooks.useAll({ ativo: true })
  const centros = (cc ?? []) as CentroCusto[]
  const [ofertaId] = useState<number | undefined>(oferta?.oferta_id)
  const [qtd, setQtd] = useState('')
  const [centro, setCentro] = useState<string>('')
  const [err, setErr] = useState('')
  const preco = num(oferta?.preco_direto) ?? 0
  const total = preco * (num(qtd) ?? 0)
  const salvar = async () => {
    if (ofertaId == null) return setErr('Sem oferta.')
    if ((num(qtd) ?? 0) <= 0) return setErr('Informe uma quantidade positiva.')
    try { const p = await comprar.mutateAsync({ oferta: ofertaId, quantidade: qtd, centro_custo: centro ? Number(centro) : null }); onDone(p.pedido_id) }
    catch (e) { const ax = e as { response?: { data?: { detail?: string } } }; setErr(ax.response?.data?.detail ?? 'Falha ao comprar.') }
  }
  return <Modal title="Comprar direto" onClose={onClose} footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={comprar.isPending}>{comprar.isPending ? 'Comprando…' : 'Gerar pedido'}</Btn></>}>
    {err && <div style={{ background: 'var(--danger-soft)', color: 'var(--danger-ink)', padding: '9px 12px', borderRadius: 'var(--r-sm)', fontSize: 12.5, marginBottom: 12 }}>{err}</div>}
    {oferta && <div style={{ padding: '10px 12px', background: 'var(--surface-2)', borderRadius: 'var(--r-sm)', marginBottom: 14 }}><div style={{ fontWeight: 600, color: 'var(--ink)' }}>{oferta.produto_descricao}</div><div style={{ fontSize: 12, color: 'var(--ink-3)' }}>{oferta.fornecedor_nome} · {brl(oferta.preco_direto)} / {oferta.produto_unidade ?? 'un'}</div></div>}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Quantidade"><input style={{ ...inp, ...mono }} type="number" min={0} step="0.001" value={qtd} onChange={e => setQtd(e.target.value)} placeholder="0" /></Field>
      <Field label="Total estimado"><div style={{ ...inp, ...mono, fontWeight: 700 }}>{brl(total.toFixed(2))}</div></Field>
    </div>
    <Field label="Centro de custo"><select style={inp} value={centro} onChange={e => setCentro(e.target.value)}><option value="">— nenhum —</option>{centros.map(c => <option key={c.centro_custo_id} value={c.centro_custo_id}>{c.nome}</option>)}</select></Field>
  </Modal>
}
/** **Cotar** um item do catálogo: quantidade, centro de custo e prazo → demanda + cotação abertas. */
function CotarModal({ itens, onClose, onDone }: { itens: ItemDoCatalogo[]; onClose: () => void; onDone: (cotacao: number) => void }) {
  const { data: cc } = centrosCustoHooks.useAll({ ativo: true })
  const centros = (cc ?? []) as CentroCusto[]
  const [qtds, setQtds] = useState<Record<number, string>>({}), [centro, setCentro] = useState(''), [limite, setLimite] = useState('')
  const [err, setErr] = useState(''), [salvando, setSalvando] = useState(false)
  const salvar = async () => {
    setErr('')
    const linhas = itens.map(it => ({ produto: it.item_id, q: lerDecimal(qtds[it.item_id] ?? '') ?? 0, nome: it.descricao }))
    const sem = linhas.find(l => l.q <= 0)
    if (sem) return setErr(`Informe a quantidade de "${sem.nome}".`)
    setSalvando(true)
    try {
      const r = await cotarItens({ itens: linhas.map(l => ({ produto: l.produto, quantidade: String(l.q) })), centro_custo: centro ? Number(centro) : null, data_limite: limite || null })
      onDone(r.cotacao_id)
    } catch (e) { setErr(Object.values(parseApiErrors(e))[0] ?? 'Não foi possível abrir a cotação.'); setSalvando(false) }
  }
  return <Modal title={itens.length === 1 ? 'Cotar item' : `Cotar ${itens.length} itens`} largura={560} onClose={onClose} footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={salvando}>{salvando ? 'Abrindo…' : 'Abrir cotação'}</Btn></>}>
    {err && <div style={{ background: 'var(--danger-soft)', color: 'var(--danger-ink)', padding: '9px 12px', borderRadius: 'var(--r-sm)', fontSize: 12.5, marginBottom: 12 }}>{err}</div>}
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14, maxHeight: 280, overflowY: 'auto' }}>
      {itens.map(it => (
        <div key={it.item_id} style={{ display: 'grid', gridTemplateColumns: '1fr 110px', gap: 10, alignItems: 'center', padding: '8px 12px', background: 'var(--surface-2)', borderRadius: 'var(--r-sm)' }}>
          <div style={{ minWidth: 0 }}><div style={{ fontWeight: 600, color: 'var(--ink)', fontSize: 13 }}>{it.descricao}</div><div style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)' }}>{it.codigo_interno} · {it.unidade}</div></div>
          <input style={{ ...inp, ...mono }} inputMode="decimal" aria-label={`Quantidade de ${it.descricao}`} placeholder={`Qtd (${it.unidade || 'un'})`} value={qtds[it.item_id] ?? ''} onChange={e => setQtds(q => ({ ...q, [it.item_id]: e.target.value }))} />
        </div>
      ))}
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Responder até"><input style={inp} type="date" min={minCalendarioISO} max={maxCalendarioISO} value={limite} onChange={e => setLimite(e.target.value)} /></Field>
    </div>
    <Field label="Centro de custo"><select style={inp} value={centro} onChange={e => setCentro(e.target.value)}><option value="">— nenhum —</option>{centros.map(c => <option key={c.centro_custo_id} value={c.centro_custo_id}>{c.nome}</option>)}</select></Field>
  </Modal>
}
interface ItemCatalogo { item_id: number; codigo_interno: string; descricao: string; unidade: string }
interface LinhaDeCompra { chave: number; produto: number | null; descricao: string; unidade: string; quantidade: string; preco: string }


/** **Nova compra** — fornecedor, o que se compra, quantidade e preço. Sem
 *  oferta no catálogo e sem cotação: é a compra do depósito da esquina, que a
 *  obra faz todo dia (achado do dono, 10/10/2026: "continuo sem poder
 *  comprar"). Item do catálogo é procurado pelo nome; o que não está no
 *  catálogo vai como texto. Nasce pedido aprovado e segue igual aos outros. */
interface LinhaInicial { produto: number | null; descricao: string; unidade: string; quantidade?: string }
function NovaCompraModal({ onClose, onDone, say, iniciais, demanda }: {
  onClose: () => void; onDone: (id: number) => void; say: Say
  iniciais?: LinhaInicial[]; demanda?: { id: number; centro_custo: number | null }
}) {
  const comprar = useCompraAvulsa()
  const { data: cc } = centrosCustoHooks.useAll({ ativo: true })
  const centros = (cc ?? []) as CentroCusto[]
  const { data: fornecedores = [] } = useQuery({
    queryKey: ['scm', 'fornecedores-da-compra'],
    queryFn: async () => {
      const { data } = await apiClient.get<{ results?: { fornecedor_id: number; razao_social: string }[] } | { fornecedor_id: number; razao_social: string }[]>('/fornecedores/', { params: { page_size: 500 } })
      return Array.isArray(data) ? data : (data.results ?? [])
    },
  })
  const [fornecedor, setFornecedor] = useState('')
  const [centro, setCentro] = useState(demanda?.centro_custo != null ? String(demanda.centro_custo) : '')
  const [entrega, setEntrega] = useState('')
  const [linhas, setLinhas] = useState<LinhaDeCompra[]>(iniciais?.length
    ? iniciais.map((it, i) => ({ chave: i + 1, produto: it.produto, descricao: it.descricao, unidade: it.unidade, quantidade: it.quantidade ?? '', preco: '' }))
    : [{ chave: 1, produto: null, descricao: '', unidade: '', quantidade: '', preco: '' }])
  const [busca, setBusca] = useState<{ chave: number; termo: string } | null>(null)
  const sugestoes = useQuery({
    queryKey: ['scm', 'produtos-busca', busca?.termo ?? ''],
    queryFn: async () => (await apiClient.get<{ results?: ItemCatalogo[] } | ItemCatalogo[]>('catalogo/itens/', { params: { search: busca!.termo, page_size: 10 } })).data,
    enabled: (busca?.termo.trim().length ?? 0) >= 2,
  })
  const listaSugestoes = Array.isArray(sugestoes.data) ? sugestoes.data : (sugestoes.data?.results ?? [])
  const [err, setErr] = useState('')
  const mudar = (chave: number, patch: Partial<LinhaDeCompra>) => setLinhas(ls => ls.map(l => l.chave === chave ? { ...l, ...patch } : l))
  const subtotal = (l: LinhaDeCompra) => (lerDecimal(l.quantidade) ?? 0) * (lerDecimal(l.preco) ?? 0)
  const total = linhas.reduce((t, l) => t + subtotal(l), 0)
  const [cadastrando, setCadastrando] = useState<number | null>(null)

  /** O item que é só texto vira item do catálogo (e a loja dele, com o preço
   *  digitado). O código gerado aparece no aviso embaixo (dono, 11/10/2026). */
  const cadastrar = async (l: LinhaDeCompra) => {
    if (!l.descricao.trim()) return setErr('Escreva o item antes de cadastrar.')
    setErr(''); setCadastrando(l.chave)
    try {
      const r = await cadastrarItem({
        descricao: l.descricao.trim(), unidade: l.unidade.trim(),
        fornecedor: fornecedor ? Number(fornecedor) : null,
        preco: lerDecimal(l.preco) != null ? String(lerDecimal(l.preco)) : undefined,
      })
      mudar(l.chave, { produto: r.item_id, descricao: r.descricao, unidade: r.unidade })
      say(r.criado ? `Item cadastrado no catálogo: ${r.codigo_interno} — ${r.descricao} (${r.unidade})` : `Já estava no catálogo: ${r.codigo_interno} — ${r.descricao}`, 6000)
    } catch (e) { setErr(Object.values(parseApiErrors(e))[0] ?? 'Não foi possível cadastrar o item.') }
    setCadastrando(null)
  }

  const salvar = async () => {
    setErr('')
    if (!fornecedor) return setErr('Escolha o fornecedor.')
    const itens = linhas.filter(l => l.descricao.trim() || l.produto).map(l => ({
      produto: l.produto, descricao: l.produto ? '' : l.descricao.trim(), unidade: l.unidade.trim(),
      quantidade: String(lerDecimal(l.quantidade) ?? 0), preco_unitario: String(lerDecimal(l.preco) ?? 0),
    }))
    if (itens.length === 0) return setErr('Inclua ao menos um item.')
    try {
      const p = await comprar.mutateAsync({
        fornecedor: Number(fornecedor), centro_custo: centro ? Number(centro) : null,
        data_entrega_prevista: entrega || null, demanda: demanda?.id ?? null, itens,
      })
      onDone(p.pedido_id)
    } catch (e) {
      const ax = e as { response?: { data?: { detail?: string } } }
      setErr(ax.response?.data?.detail ?? 'Falha ao gerar o pedido.')
    }
  }

  return <Modal title="Nova compra" largura={920} onClose={onClose} footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={comprar.isPending}>{comprar.isPending ? 'Gerando…' : `Gerar pedido · ${brl(total.toFixed(2))}`}</Btn></>}>
    {err && <div style={{ background: 'var(--danger-soft)', color: 'var(--danger-ink)', padding: '9px 12px', borderRadius: 'var(--r-sm)', fontSize: 12.5, marginBottom: 12 }}>{err}</div>}
    <Field label="Fornecedor">
      <select style={inp} value={fornecedor} onChange={e => setFornecedor(e.target.value)}>
        <option value="">— escolha —</option>
        {fornecedores.map(f => <option key={f.fornecedor_id} value={f.fornecedor_id}>{f.razao_social}</option>)}
      </select>
    </Field>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Centro de custo"><select style={inp} value={centro} onChange={e => setCentro(e.target.value)}><option value="">— nenhum —</option>{centros.map(c => <option key={c.centro_custo_id} value={c.centro_custo_id}>{c.nome}</option>)}</select></Field>
      <Field label="Entrega prevista"><input style={inp} type="date" min={minCalendarioISO} max={maxCalendarioISO} value={entrega} onChange={e => setEntrega(e.target.value)} /></Field>
    </div>
    <div style={{ ...CAPS, fontSize: 10.5, marginBottom: 6 }}>Itens</div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 8 }}>
      {linhas.map(l => (
        <div key={l.chave} style={{ display: 'grid', gridTemplateColumns: '24px 1fr 80px 70px 120px 28px', gap: 6, alignItems: 'start' }}>
          {/* Só texto → botão à esquerda cadastra no catálogo (dono, 11/10/2026). */}
          {l.produto == null && l.descricao.trim().length >= 2
            ? <button type="button" title="Cadastrar este item no catálogo" aria-label="Cadastrar no catálogo" disabled={cadastrando === l.chave}
                onClick={() => cadastrar(l)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent-ink)', paddingTop: 8, display: 'grid', placeItems: 'center' }}><PlusCircle size={18} /></button>
            : <span />}
          <div style={{ position: 'relative' }}>
            <input
              style={inp} value={l.descricao} placeholder="O que comprar (procura no catálogo)"
              onChange={e => { mudar(l.chave, { descricao: e.target.value, produto: null }); setBusca({ chave: l.chave, termo: e.target.value }) }}
            />
            {busca?.chave === l.chave && l.produto == null && listaSugestoes.length > 0 && (
              <div style={{ position: 'absolute', zIndex: 5, top: '100%', left: 0, right: 0, background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', boxShadow: 'var(--shadow-md)', maxHeight: 180, overflowY: 'auto' }}>
                {listaSugestoes.map(p => (
                  <button key={p.item_id} type="button"
                    onClick={() => { mudar(l.chave, { produto: p.item_id, descricao: p.descricao, unidade: p.unidade }); setBusca(null) }}
                    style={{ display: 'block', width: '100%', textAlign: 'left', padding: '6px 9px', fontSize: 12.5, background: 'none', border: 'none', borderBottom: '1px solid var(--line-2)', cursor: 'pointer', color: 'var(--ink)' }}>
                    <span style={{ ...mono, color: 'var(--ink-3)' }}>{p.codigo_interno}</span> {p.descricao} · {p.unidade}
                  </button>
                ))}
              </div>
            )}
            {l.produto != null
              ? <div style={{ fontSize: 10.5, color: 'var(--good-ink)', marginTop: 2 }}>do catálogo</div>
              : l.descricao.trim().length >= 2 && <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2 }}>fora do catálogo — não entra no estoque; use o + para cadastrar</div>}
          </div>
          <input style={{ ...inp, ...mono }} inputMode="decimal" placeholder="Qtd" value={l.quantidade} onChange={e => mudar(l.chave, { quantidade: e.target.value })} />
          {/* Item do catálogo traz a unidade do cadastro; item livre diz a sua. */}
          <input style={{ ...inp, ...(l.produto != null ? { color: 'var(--ink-3)' } : {}) }} placeholder="Un." maxLength={20}
            title={l.produto != null ? 'Unidade do cadastro do catálogo' : 'Unidade: un, m, m², m³, kg, sc, vb…'}
            value={l.unidade} readOnly={l.produto != null} onChange={e => mudar(l.chave, { unidade: e.target.value })} />
          <div style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', left: 10, top: 9, fontSize: 12.5, color: 'var(--ink-3)', pointerEvents: 'none' }}>R$</span>
            <input style={{ ...inp, ...mono, paddingLeft: 32, textAlign: 'right' }} inputMode="decimal" placeholder="0,00"
              aria-label="Preço unitário em reais" title={l.unidade ? `Preço por ${l.unidade}` : 'Preço unitário'}
              value={l.preco} onChange={e => mudar(l.chave, { preco: e.target.value })} />
            {subtotal(l) > 0 && <div style={{ ...mono, fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2, textAlign: 'right' }}>= {brl(subtotal(l).toFixed(2))}</div>}
          </div>
          <button type="button" aria-label="Tirar item" disabled={linhas.length === 1} onClick={() => setLinhas(ls => ls.filter(x => x.chave !== l.chave))}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)', paddingTop: 8 }}>×</button>
        </div>
      ))}
    </div>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
      <Btn onClick={() => setLinhas(ls => [...ls, { chave: Date.now(), produto: null, descricao: '', unidade: '', quantidade: '', preco: '' }])}>+ Outro item</Btn>
      <div style={{ textAlign: 'right' }}>
        <div style={{ ...CAPS, fontSize: 10.5 }}>Total do pedido</div>
        <div style={{ ...mono, fontSize: 18, fontWeight: 650, color: 'var(--ink)' }}>{brl(total.toFixed(2))}</div>
      </div>
    </div>
  </Modal>
}
