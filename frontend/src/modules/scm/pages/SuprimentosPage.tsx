import { useMemo, useState, type CSSProperties, type ReactNode, type HTMLAttributes, type ButtonHTMLAttributes } from 'react'
import {
  LayoutDashboard, Tags, FileSpreadsheet, ShoppingCart, Network, ClipboardList,
  PackageCheck, ChevronRight, Coins, Gavel, Truck, Clock, Check, Sparkles, ArrowLeft,
  Package, Upload, LineChart, BadgeCheck, ArrowLeftRight, Store, AlertTriangle,
  Boxes, Star, Zap, Inbox, Lock,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useQueryClient } from '@tanstack/react-query'
import {
  useScmDashboard, cotacoesHooks, pedidosHooks, ofertasHooks, centrosCustoHooks,
  demandasHooks, itensDemandaHooks, propostasHooks, itensPropostaHooks, itensPedidoHooks,
  recebimentosHooks, avaliacoesHooks, useAdjudicar, useComprarDireto, useGerarDeCotacao,
} from '../hooks'
import { scmKeys } from '../api/queryKeys'
import { recebimentos as recebimentosApi, avaliacoes as avaliacoesApi } from '../api/scmApi'
import { brl, qty, dataBR, num, cotacaoEstado, pedidoEstado, propostaEstado, origemPedido, type Kind, type Estado } from '../lib'
import type {
  OfertaFornecedor, Cotacao, Proposta, ItemDemanda, ItemProposta,
  ItemPedido, Recebimento, AvaliacaoFornecedor, CentroCusto, TipoRecebimento,
} from '../types'

/* ─── primitivos ─── */
const mono: CSSProperties = { fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }
let toastTimer: number | undefined
const KIND: Record<Kind, [string, string]> = {
  slate: ['var(--inset)', 'var(--ink-2)'], info: ['var(--info-soft)', 'var(--info-ink)'], amber: ['var(--accent-soft)', 'var(--accent-ink)'],
  good: ['var(--good-soft)', 'var(--good-ink)'], danger: ['var(--danger-soft)', 'var(--danger-ink)'], net: ['var(--net-soft)', 'var(--net-ink)'],
}
function Pill({ kind = 'slate', pulse, children }: { kind?: Kind; pulse?: boolean; children: ReactNode }) {
  const [bg, fg] = KIND[kind]
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11.5, fontWeight: 650, padding: '3px 9px', borderRadius: 999, whiteSpace: 'nowrap', lineHeight: 1.4, background: bg, color: fg }}>{pulse && <span className="scm-dot" />}{children}</span>
}
const EstadoPill = ({ e }: { e: Estado }) => <Pill kind={e.kind} pulse={e.pulse}>{e.label}</Pill>
function Card({ children, style, pad = true, ...rest }: { children: ReactNode; pad?: boolean } & HTMLAttributes<HTMLDivElement>) {
  return <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', boxShadow: 'var(--shadow-sm)', padding: pad ? 18 : 0, ...style }} {...rest}>{children}</div>
}
const CONN = new Set(['de', 'do', 'da', 'dos', 'das', 'e'])
function iniciais(n: string) { const p = n.trim().split(/\s+/).filter(w => !CONN.has(w.toLowerCase())); const s = p.length ? p : n.trim().split(/\s+/); return ((s[0]?.[0] ?? '') + (s[1]?.[0] ?? '')).toUpperCase() }
const AV: [string, string][] = [['var(--info-soft)', 'var(--info-ink)'], ['var(--accent-soft)', 'var(--accent-ink)'], ['var(--good-soft)', 'var(--good-ink)'], ['var(--net-soft)', 'var(--net-ink)']]
function avColor(s: string) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return AV[h % AV.length] }
function Avatar({ name, size = 26 }: { name: string; size?: number }) { const [bg, fg] = avColor(name || '?'); return <span style={{ width: size, height: size, borderRadius: Math.round(size * 0.27), flex: 'none', display: 'grid', placeItems: 'center', background: bg, color: fg, fontFamily: 'var(--mono)', fontWeight: 700, fontSize: Math.round(size * 0.42) }}>{iniciais(name || '?')}</span> }
function Btn({ variant = 'ghost', children, style, ...rest }: { variant?: 'primary' | 'ghost' | 'brand' } & ButtonHTMLAttributes<HTMLButtonElement>) {
  const v: Record<string, CSSProperties> = { primary: { background: 'var(--accent)', color: '#1A1204' }, ghost: { background: 'var(--surface)', color: 'var(--ink-2)', border: '1px solid var(--line)' }, brand: { background: 'var(--brand)', color: 'var(--brand-ink)' } }
  return <button {...rest} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 13.5, fontWeight: 650, padding: '9px 15px', borderRadius: 'var(--r-sm)', cursor: rest.disabled ? 'not-allowed' : 'pointer', opacity: rest.disabled ? 0.5 : 1, border: '1px solid transparent', whiteSpace: 'nowrap', ...v[variant], ...style }}>{children}</button>
}
function SectHead({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '22px 0 12px' }}><h2 style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.02em', textTransform: 'uppercase', color: 'var(--ink-2)' }}>{children}</h2><span style={{ flex: 1, height: 1, background: 'var(--line-2)' }} />{right}</div>
}
const CAPS: CSSProperties = { fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }
const Spinner = () => <span style={{ width: 26, height: 26, borderRadius: 999, border: '2.5px solid var(--line)', borderTopColor: 'var(--accent)', display: 'inline-block', animation: 'scmSpin .8s linear infinite' }} />
const Loading = () => <div style={{ display: 'grid', placeItems: 'center', padding: 60 }}><Spinner /></div>
function Empty({ children }: { children: ReactNode }) { return <Card style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, padding: 44, color: 'var(--ink-3)' }}><Inbox size={32} style={{ opacity: 0.7 }} /><span style={{ fontSize: 13, textAlign: 'center' }}>{children}</span></Card> }
type Say = (m: string) => void

/* ─── página ─── */
type TabId = 'cockpit' | 'catalogo' | 'cotacao' | 'pedidos' | 'rede'
const TABS: { id: TabId; label: string; icon: ReactNode; locked?: boolean }[] = [
  { id: 'cockpit', label: 'Cockpit', icon: <LayoutDashboard size={15} /> }, { id: 'catalogo', label: 'Catálogo', icon: <Tags size={15} /> },
  { id: 'cotacao', label: 'Cotação', icon: <FileSpreadsheet size={15} /> }, { id: 'pedidos', label: 'Pedidos', icon: <ShoppingCart size={15} /> },
  { id: 'rede', label: 'Esfera de Rede', icon: <Network size={15} />, locked: true },
]

export default function SuprimentosPage() {
  const [tab, setTab] = useState<TabId>('cockpit')
  const [selCot, setSelCot] = useState<number | null>(null)
  const [selPed, setSelPed] = useState<number | null>(null)
  const [toast, setToast] = useState('')
  const say: Say = m => { setToast(m); window.clearTimeout(toastTimer); toastTimer = window.setTimeout(() => setToast(''), 2800) }
  const openCot = (id: number) => { setSelCot(id); setTab('cotacao') }
  const openPed = (id: number) => { setSelPed(id); setTab('pedidos') }

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
            <button key={t.id} onClick={() => setTab(t.id)} title={t.locked ? 'Bloqueado — disponível quando a Esfera de Rede for construída' : undefined} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '7px 13px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', border: 'none', color: on ? 'var(--ink)' : 'var(--ink-2)', background: on ? 'var(--surface)' : 'transparent', boxShadow: on ? 'var(--shadow-sm)' : 'none' }}>
              <span style={{ color: on ? 'var(--accent-strong)' : 'inherit', display: 'grid', placeItems: 'center' }}>{t.icon}</span>{t.label}{t.locked && <Lock size={12} style={{ color: 'var(--ink-3)', marginLeft: 1 }} />}
            </button>) })}
        </div>
      </div>

      <div className="scm-screen" key={tab + (selCot ?? '') + (selPed ?? '')}>
        {tab === 'cockpit' && <Cockpit go={setTab} openCot={openCot} />}
        {tab === 'catalogo' && <Catalogo say={say} onComprou={openPed} />}
        {tab === 'cotacao' && (selCot != null ? <CotacaoDetail id={selCot} onBack={() => setSelCot(null)} openPed={openPed} say={say} /> : <CotacaoList onOpen={setSelCot} />)}
        {tab === 'pedidos' && (selPed != null ? <PedidoDetail id={selPed} onBack={() => setSelPed(null)} say={say} /> : <PedidoList onOpen={setSelPed} say={say} onComprou={setSelPed} />)}
        {tab === 'rede' && <Rede />}
      </div>

      {toast && <div style={{ position: 'fixed', bottom: 24, left: '50%', background: 'var(--ink)', color: 'var(--surface)', padding: '12px 18px', borderRadius: 11, fontSize: 13.5, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 10, zIndex: 100, boxShadow: 'var(--shadow-lg)', animation: 'scmToast .28s cubic-bezier(.2,.7,.2,1) both' }}><Check size={17} style={{ color: 'var(--good)' }} />{toast}</div>}
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
function Cockpit({ go, openCot }: { go: (t: TabId) => void; openCot: (id: number) => void }) {
  const { data: d, isLoading } = useScmDashboard()
  const { data: cots } = cotacoesHooks.useList({ status: 'aberta' })
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
function Catalogo({ say, onComprou }: { say: Say; onComprou: (id: number) => void }) {
  const { hasPermission } = useAuth()
  const podeComprar = hasPermission('scm.pedido.criar')
  const [search, setSearch] = useState('')
  const [comprar, setComprar] = useState<OfertaFornecedor | null>(null)
  const { data, isLoading } = ofertasHooks.useList({ search, page_size: 24 })
  const rows = data?.results ?? []
  return (
    <>
      <SectHead right={<input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar produto…" style={{ fontSize: 13, padding: '7px 11px', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', background: 'var(--surface-2)', color: 'var(--ink)', minWidth: 220 }} />}>Catálogo de ofertas</SectHead>
      {isLoading ? <Loading /> : rows.length === 0 ? <Empty>Nenhuma oferta no catálogo{search ? ' para a busca' : ''}.</Empty> : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(268px,1fr))', gap: 14 }}>
          {rows.map(o => {
            const disp = num(o.estoque_disponivel) ?? 0, livre = num(o.estoque_livre) ?? disp, frac = disp > 0 ? Math.max(0, Math.min(1, livre / disp)) : 0
            return (
              <Card key={o.oferta_id} className="scm-lift" style={{ display: 'flex', flexDirection: 'column', gap: 12, opacity: o.ativo ? 1 : 0.6 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 'var(--r-md)', flex: 'none', display: 'grid', placeItems: 'center', background: 'var(--inset)', color: 'var(--ink-2)' }}><Package size={20} /></div>
                  <div style={{ flex: 1, minWidth: 0 }}><div style={{ fontWeight: 650, fontSize: 14, color: 'var(--ink)', lineHeight: 1.3 }}>{o.produto_descricao ?? `#${o.produto}`}</div><div style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>{o.produto_codigo ?? ''} · {o.fornecedor_nome ?? `#${o.fornecedor}`}</div></div>
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
function CotacaoList({ onOpen }: { onOpen: (id: number) => void }) {
  const { data, isLoading } = cotacoesHooks.useList({})
  const rows = data?.results ?? []
  if (isLoading) return <Loading />
  if (rows.length === 0) return <><SectHead>Cotações</SectHead><Empty>Nenhuma cotação. Elas nascem de uma demanda publicada.</Empty></>
  return (
    <>
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
  const adjudicar = useAdjudicar(), gerar = useGerarDeCotacao()

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
      </div>

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
      <SectHead right={podeComprar ? <Btn variant="primary" style={{ padding: '6px 12px', fontSize: 12.5 }} onClick={() => setComprar(true)}><Zap size={14} /> Compra direta</Btn> : undefined}>Pedidos de compra</SectHead>
      {isLoading ? <Loading /> : rows.length === 0 ? <Empty>Nenhum pedido. Compre direto no catálogo ou gere de uma cotação adjudicada.</Empty> : (
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
      {comprar && <ComprarModal onClose={() => setComprar(false)} onDone={id => { setComprar(false); say('Pedido gerado'); onComprou(id) }} />}
    </>
  )
}

function PedidoDetail({ id, onBack, say }: { id: number; onBack: () => void; say: Say }) {
  const { hasPermission } = useAuth()
  const podeReceber = hasPermission('scm.recebimento.edit'), podeAvaliar = hasPermission('scm.avaliacao.edit')
  const { data: p, isLoading } = pedidosHooks.useDetail(id)
  const { data: itens } = itensPedidoHooks.useAll({ pedido: id })
  const { data: recs } = recebimentosHooks.useAll({ pedido: id })
  const { data: avals } = avaliacoesHooks.useAll({ pedido: id })
  const [receber, setReceber] = useState(false), [avaliar, setAvaliar] = useState(false)
  if (isLoading || !p) return <Loading />
  const linhas = (itens ?? []) as ItemPedido[], recebs = (recs ?? []) as Recebimento[], avaliacoesL = (avals ?? []) as AvaliacaoFornecedor[]
  const finalizado = p.status === 'cancelado'
  return (
    <div style={{ maxWidth: 980 }}>
      <button onClick={onBack} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--ink-3)', background: 'none', border: 'none', cursor: 'pointer', marginBottom: 6 }}><ArrowLeft size={13} /> Todos os pedidos</button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 19, fontWeight: 750, letterSpacing: '-0.02em', color: 'var(--ink)' }}>Pedido #{p.pedido_id}</h2>
        <EstadoPill e={pedidoEstado[p.status]} /><Pill kind={origemPedido[p.origem].kind}>{origemPedido[p.origem].label}</Pill>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 9 }}>
          {podeAvaliar && <Btn onClick={() => setAvaliar(true)}><Star size={14} /> Avaliar fornecedor</Btn>}
          {podeReceber && !finalizado && <Btn variant="primary" onClick={() => setReceber(true)}><PackageCheck size={14} /> Registrar recebimento</Btn>}
        </div>
      </div>

      <div style={{ display: 'grid', gap: 18 }}>
        <Card><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 16 }}>
          <Info k="Fornecedor" v={p.fornecedor_nome ?? `#${p.fornecedor}`} />
          <Info k="Centro de custo" v={p.centro_custo_nome ?? '—'} />
          <Info k="Valor total" v={brl(p.valor_total)} mono />
          <Info k="Data do pedido" v={dataBR(p.data_pedido)} mono />
          {p.demanda && <Info k="Origem" v={`Demanda #${p.demanda}`} />}
          {p.oferta_origem && <Info k="Origem" v={`Oferta #${p.oferta_origem}`} />}
        </div></Card>

        <div>
          <SectHead>Itens</SectHead>
          {linhas.length === 0 ? <Empty>Sem itens.</Empty> : <Card pad={false} style={{ overflow: 'hidden' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead><tr>{['Item', 'Qtd.', 'Preço unit.', 'Subtotal'].map((h, i) => <th key={i} style={{ ...CAPS, fontSize: 10.5, textAlign: i ? 'right' : 'left', padding: '10px 16px', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' }}>{h}</th>)}</tr></thead>
            <tbody>{linhas.map((it, i) => (
              <tr key={it.item_pedido_id} style={{ borderBottom: i < linhas.length - 1 ? '1px solid var(--line-2)' : undefined }}>
                <td style={{ padding: '11px 16px' }}><div style={{ fontWeight: 500, color: 'var(--ink)' }}>{it.produto_descricao ?? it.descricao ?? '—'}</div>{it.produto_codigo && <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)' }}>{it.produto_codigo}</span>}</td>
                <td style={{ ...mono, padding: '11px 16px', textAlign: 'right' }}>{qty(it.quantidade)}</td>
                <td style={{ ...mono, padding: '11px 16px', textAlign: 'right' }}>{brl(it.preco_unitario)}</td>
                <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', fontWeight: 600, color: 'var(--ink)' }}>{brl((num(it.preco_unitario) ?? 0) * (num(it.quantidade) ?? 0))}</td>
              </tr>
            ))}</tbody>
          </table></Card>}
        </div>

        <div>
          <SectHead>Recebimentos</SectHead>
          {recebs.length === 0 ? <Empty>Nenhum recebimento registrado.</Empty> : <Card pad={false} style={{ overflow: 'hidden' }}>{recebs.map((r, i) => (
            <div key={r.recebimento_id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', borderBottom: i < recebs.length - 1 ? '1px solid var(--line-2)' : undefined }}><Pill kind={r.tipo === 'total' ? 'good' : 'amber'}>{r.tipo === 'total' ? 'Total' : 'Parcial'}</Pill><span style={{ ...mono, fontSize: 12.5, color: 'var(--ink-2)' }}>{dataBR(r.data)}</span>{r.nota_fiscal_ref && <span style={{ marginLeft: 'auto', ...mono, fontSize: 12, color: 'var(--net-ink)' }}>NF-e {r.nota_fiscal_ref}</span>}</div>
          ))}</Card>}
        </div>

        {avaliacoesL.length > 0 && <div>
          <SectHead>Avaliação do fornecedor</SectHead>
          {avaliacoesL.map(a => <Card key={a.avaliacao_id} style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center' }}><Nota k="Qualidade" v={a.nota_qualidade} /><Nota k="Pontualidade" v={a.nota_pontualidade} /><Nota k="Atendimento" v={a.nota_atendimento} />{a.comentario && <p style={{ flex: 1, minWidth: 200, fontSize: 13, color: 'var(--ink-2)' }}>{a.comentario}</p>}</Card>)}
        </div>}
      </div>

      {receber && <RecebimentoModal pedidoId={id} onClose={() => setReceber(false)} onDone={() => { setReceber(false); say('Recebimento registrado') }} />}
      {avaliar && <AvaliarModal pedidoId={id} fornecedor={p.fornecedor} onClose={() => setAvaliar(false)} onDone={() => { setAvaliar(false); say('Fornecedor avaliado') }} />}
    </div>
  )
}
function Info({ k, v, mono: m }: { k: string; v: string; mono?: boolean }) { return <div><div style={{ ...CAPS, fontSize: 10.5, marginBottom: 3 }}>{k}</div><div style={m ? mono : undefined}>{v}</div></div> }
function Nota({ k, v }: { k: string; v: number }) { return <div><div style={{ ...CAPS, fontSize: 10.5, marginBottom: 4 }}>{k}</div><div style={{ display: 'flex', gap: 2 }}>{[1, 2, 3, 4, 5].map(n => <Star key={n} size={15} style={{ color: n <= v ? 'var(--accent)' : 'var(--line)', fill: n <= v ? 'var(--accent)' : 'none' }} />)}</div></div> }

/* ═══ modais ═══ */
function Modal({ title, onClose, children, footer }: { title: string; onClose: () => void; children: ReactNode; footer: ReactNode }) {
  return <div onMouseDown={e => { if (e.target === e.currentTarget) onClose() }} style={{ position: 'fixed', inset: 0, zIndex: 90, background: 'rgba(6,14,26,.5)', backdropFilter: 'blur(3px)', display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: '8vh 16px' }}>
    <div style={{ width: '100%', maxWidth: 480, background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', boxShadow: 'var(--shadow-lg)' }}>
      <div style={{ padding: '15px 20px', borderBottom: '1px solid var(--line)', fontFamily: 'var(--display)', fontSize: 16, fontWeight: 700, color: 'var(--ink)' }}>{title}</div>
      <div style={{ padding: 20 }}>{children}</div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 9, padding: '14px 20px', borderTop: '1px solid var(--line)' }}>{footer}</div>
    </div>
  </div>
}
function Field({ label, children }: { label: string; children: ReactNode }) { return <label style={{ display: 'block', marginBottom: 14 }}><span style={{ display: 'block', ...CAPS, fontSize: 10.5, marginBottom: 5 }}>{label}</span>{children}</label> }
const inp: CSSProperties = { width: '100%', padding: '8px 11px', fontSize: 13.5, color: 'var(--ink)', background: 'var(--surface-2)', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', outline: 'none', fontFamily: 'var(--sans)' }

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
function RecebimentoModal({ pedidoId, onClose, onDone }: { pedidoId: number; onClose: () => void; onDone: () => void }) {
  const qc = useQueryClient()
  const [tipo, setTipo] = useState<TipoRecebimento>('total')
  const [data, setData] = useState(new Date().toISOString().slice(0, 10))
  const [nf, setNf] = useState(''), [saving, setSaving] = useState(false), [err, setErr] = useState('')
  const salvar = async () => {
    setSaving(true); setErr('')
    try { await recebimentosApi.create({ pedido: pedidoId, tipo, data, nota_fiscal_ref: nf }); await qc.invalidateQueries({ queryKey: scmKeys.all }); onDone() }
    catch { setErr('Falha ao registrar.'); setSaving(false) }
  }
  return <Modal title="Registrar recebimento" onClose={onClose} footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={saving}>{saving ? 'Salvando…' : 'Registrar'}</Btn></>}>
    {err && <div style={{ background: 'var(--danger-soft)', color: 'var(--danger-ink)', padding: '9px 12px', borderRadius: 'var(--r-sm)', fontSize: 12.5, marginBottom: 12 }}>{err}</div>}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Tipo"><select style={inp} value={tipo} onChange={e => setTipo(e.target.value as TipoRecebimento)}><option value="total">Total</option><option value="parcial">Parcial</option></select></Field>
      <Field label="Data"><input style={inp} type="date" value={data} onChange={e => setData(e.target.value)} /></Field>
    </div>
    <Field label="NF-e (chave/número)"><input style={inp} value={nf} onChange={e => setNf(e.target.value)} placeholder="Opcional — concilia com o ERP" /></Field>
  </Modal>
}
function AvaliarModal({ pedidoId, fornecedor, onClose, onDone }: { pedidoId: number; fornecedor: number; onClose: () => void; onDone: () => void }) {
  const qc = useQueryClient()
  const [q, setQ] = useState(5), [pt, setPt] = useState(5), [at, setAt] = useState(5), [c, setC] = useState(''), [saving, setSaving] = useState(false)
  const salvar = async () => { setSaving(true); try { await avaliacoesApi.create({ fornecedor, pedido: pedidoId, nota_qualidade: q, nota_pontualidade: pt, nota_atendimento: at, comentario: c }); await qc.invalidateQueries({ queryKey: scmKeys.all }); onDone() } catch { setSaving(false) } }
  return <Modal title="Avaliar fornecedor" onClose={onClose} footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={saving}>{saving ? 'Salvando…' : 'Salvar avaliação'}</Btn></>}>
    <StarsPick label="Qualidade" v={q} on={setQ} /><StarsPick label="Pontualidade" v={pt} on={setPt} /><StarsPick label="Atendimento" v={at} on={setAt} />
    <Field label="Comentário"><textarea style={{ ...inp, resize: 'vertical', minHeight: 60 }} value={c} onChange={e => setC(e.target.value)} placeholder="Opcional" /></Field>
  </Modal>
}
function StarsPick({ label, v, on }: { label: string; v: number; on: (n: number) => void }) {
  return <div style={{ marginBottom: 14 }}><div style={{ ...CAPS, fontSize: 10.5, marginBottom: 6 }}>{label}</div><div style={{ display: 'flex', gap: 4 }}>{[1, 2, 3, 4, 5].map(n => <button key={n} onClick={() => on(n)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2 }}><Star size={22} style={{ color: n <= v ? 'var(--accent)' : 'var(--line)', fill: n <= v ? 'var(--accent)' : 'none' }} /></button>)}</div></div>
}

/* ═══ ESFERA DE REDE (estático) ═══ */
function Rede() {
  return (
    <>
      <div style={{ padding: '30px 30px 28px', borderRadius: 'var(--r-xl)', position: 'relative', overflow: 'hidden', background: 'linear-gradient(125deg,var(--brand),#08203f 60%,#0a2c5e)', color: '#EAF1FC', border: '1px solid var(--brand-2)' }}>
        <div style={{ position: 'absolute', right: -60, top: -60, width: 260, height: 260, borderRadius: 999, background: 'radial-gradient(circle,rgba(15,138,147,.5),transparent 65%)' }} />
        <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#7FE0E6', background: 'rgba(15,138,147,.18)', border: '1px solid rgba(43,182,191,.35)', padding: '5px 12px', borderRadius: 999 }}><Lock size={12} /> Bloqueado · em construção — Horizonte H2–H3</span>
        <h2 style={{ position: 'relative', fontSize: 26, fontWeight: 750, letterSpacing: '-0.03em', margin: '16px 0 8px', maxWidth: 560, color: '#fff' }}>O mesmo mapa de cotação, aberto para o mercado inteiro.</h2>
        <p style={{ position: 'relative', color: '#B3C6E4', fontSize: 14, maxWidth: 600, lineHeight: 1.6 }}>Hoje você cota entre fornecedores conhecidos. Na <b style={{ color: '#EAF1FC' }}>Esfera de Rede</b>, publicar a demanda a envia como RFQ para as lojas da região — elas respondem na mesma fila de orçamentos, e cada loja de fora vira um convite de trial. O SCM já carrega os <i>seams</i>; esta aba mostra para onde a costura leva.</p>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 16, marginTop: 18 }}>
        <RoadCard icon={<Upload size={20} />} tag="H2" title="Publicar RFQ na rede" seam="visibilidade · ref_externa">Um clique projeta a demanda como cotação pública para lojas parceiras. Respostas voltam como Proposta — cópia com estado, sem FK cruzada.</RoadCard>
        <RoadCard icon={<LineChart size={20} />} tag="H3" title="Índice de preço regional" seam="fonte: Recebimento">Cada pedido concluído alimenta um benchmark k-anônimo por região e categoria. Você passa a saber se o preço praticado está caro.</RoadCard>
        <RoadCard icon={<BadgeCheck size={20} />} tag="H2" title="Reputação portátil" seam="fonte: AvaliacaoFornecedor">As avaliações que você já registra viram selo verificado na vitrine do fornecedor — reputação só sobre transação real, impossível de forjar.</RoadCard>
      </div>
      <SectHead>O documento espelhado — comprador ↔ vendedor</SectHead>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 44px 1fr', alignItems: 'stretch' }}>
        <MirrorSide color="var(--accent)" ink="var(--accent-ink)" title="Construtora · você (comprador)" items={['Demanda / RFQ publicada', 'PedidoCompra (origem: cotacao)', 'Recebimento + Avaliação']} />
        <div style={{ display: 'grid', placeItems: 'center', color: 'var(--net)' }}><ArrowLeftRight size={22} /></div>
        <MirrorSide color="var(--net)" ink="var(--net-ink)" title="Loja · Edição Loja (vendedor)" items={['RFQ na fila de orçamentos', 'Pedido de venda', 'NF-e + boleto (Asaas)']} icon={<Store size={13} />} />
      </div>
      <div style={{ display: 'flex', gap: 12, padding: '14px 16px', borderRadius: 'var(--r-md)', background: 'var(--accent-soft)', border: '1px solid color-mix(in srgb,var(--accent) 35%,var(--line))', fontSize: 12.5, color: 'var(--accent-ink)', lineHeight: 1.55, marginTop: 18 }}>
        <AlertTriangle size={18} style={{ flex: 'none', marginTop: 1 }} /><span><b>Fronteira honesta:</b> nada aqui está construído. O lado vendedor, a sincronização e o checkout graduam junto com a Esfera de Rede — o backend atual entrega só o lado comprador com os <i>seams</i> prontos.</span>
      </div>
    </>
  )
}
function RoadCard({ icon, tag, title, seam, children }: { icon: ReactNode; tag: string; title: string; seam: string; children: ReactNode }) {
  return <Card style={{ display: 'flex', flexDirection: 'column', gap: 12 }}><div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}><div style={{ width: 40, height: 40, borderRadius: 'var(--r-md)', background: 'var(--net-soft)', color: 'var(--net-ink)', display: 'grid', placeItems: 'center' }}>{icon}</div><Pill kind={tag === 'H2' ? 'net' : 'slate'}>{tag}</Pill></div><h3 style={{ fontFamily: 'var(--display)', fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>{title}</h3><p style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>{children}</p><div style={{ fontSize: 11.5, color: 'var(--ink-3)', display: 'flex', alignItems: 'center', gap: 7, paddingTop: 11, borderTop: '1px solid var(--line-2)' }}><BadgeCheck size={13} style={{ color: 'var(--net)' }} /><code style={{ ...mono, fontSize: 11, background: 'var(--inset)', padding: '1px 6px', borderRadius: 5, color: 'var(--net-ink)' }}>{seam}</code></div></Card>
}
function MirrorSide({ color, ink, title, items, icon }: { color: string; ink: string; title: string; items: string[]; icon?: ReactNode }) {
  return <div style={{ padding: 18, borderRadius: 'var(--r-md)', border: `1px solid color-mix(in srgb,${color} 35%,var(--line))` }}><b style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em', color: ink, fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 6 }}>{icon}{title}</b><ul style={{ listStyle: 'none', marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>{items.map(it => <li key={it} style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 13, color: 'var(--ink-2)' }}><span style={{ width: 7, height: 7, borderRadius: 2, flex: 'none', background: color }} />{it}</li>)}</ul></div>
}
