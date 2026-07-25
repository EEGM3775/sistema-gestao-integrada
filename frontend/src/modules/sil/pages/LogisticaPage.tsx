import { useState, type ReactNode } from 'react'
import {
  LayoutDashboard, Boxes, ArrowLeftRight, ClipboardList, ClipboardCheck, Network,
  Warehouse, RotateCcw, ShieldCheck, Hammer, Layers, TrendingUp, Activity, Check, Lock,
} from 'lucide-react'
import { SilStyles, type Say } from '../ui'
import { Cockpit, Almoxarifados, Movimentacoes, Requisicoes, Logistica, Inventario } from '../tabs/operacao'
import { EPI, Ferramentaria } from '../tabs/pessoas'
import { CurvaABC, CustoPorObra, GiroRuptura, Rede } from '../tabs/gestao'

type Modo = 'operacao' | 'gestao'
type TabId =
  | 'cockpit' | 'almoxarifados' | 'movimentacoes' | 'requisicoes' | 'logistica' | 'inventario' | 'epi' | 'ferramentaria'
  | 'abc' | 'custo' | 'giro' | 'rede'

interface TabDef { id: TabId; label: string; icon: ReactNode; locked?: boolean }
const TABS: Record<Modo, TabDef[]> = {
  operacao: [
    { id: 'cockpit', label: 'Cockpit', icon: <LayoutDashboard size={15} /> },
    { id: 'almoxarifados', label: 'Almoxarifados', icon: <Warehouse size={15} /> },
    { id: 'movimentacoes', label: 'Movimentações', icon: <ArrowLeftRight size={15} /> },
    { id: 'requisicoes', label: 'Requisições', icon: <ClipboardList size={15} /> },
    { id: 'logistica', label: 'Transf. & Devol.', icon: <RotateCcw size={15} /> },
    { id: 'inventario', label: 'Inventário', icon: <ClipboardCheck size={15} /> },
    { id: 'epi', label: 'EPI', icon: <ShieldCheck size={15} /> },
    { id: 'ferramentaria', label: 'Ferramentaria', icon: <Hammer size={15} /> },
  ],
  gestao: [
    { id: 'abc', label: 'Curva ABC', icon: <Layers size={15} /> },
    { id: 'custo', label: 'Custo por obra', icon: <TrendingUp size={15} /> },
    { id: 'giro', label: 'Giro & Ruptura', icon: <Activity size={15} /> },
    { id: 'rede', label: 'Esfera de Rede', icon: <Network size={15} />, locked: true },
  ],
}
const MODO_DE: Record<TabId, Modo> = {
  cockpit: 'operacao', almoxarifados: 'operacao', movimentacoes: 'operacao', requisicoes: 'operacao',
  logistica: 'operacao', inventario: 'operacao', epi: 'operacao', ferramentaria: 'operacao',
  abc: 'gestao', custo: 'gestao', giro: 'gestao', rede: 'gestao',
}

let toastTimer: number | undefined

export default function LogisticaPage() {
  const [modo, setModo] = useState<Modo>('operacao')
  const [tab, setTab] = useState<TabId>('cockpit')
  const [toast, setToast] = useState('')
  const say: Say = m => { setToast(m); window.clearTimeout(toastTimer); toastTimer = window.setTimeout(() => setToast(''), 2800) }
  // Navegação vinda do cockpit (pode trocar de modo).
  const go = (t: string) => { const id = t as TabId; setModo(MODO_DE[id] ?? 'operacao'); setTab(id) }
  const trocarModo = (m: Modo) => { setModo(m); setTab(TABS[m][0].id) }

  return (
    <div style={{ padding: '24px 26px 64px', maxWidth: 1240, margin: '0 auto' }}>
      <SilStyles />

      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 20, flexWrap: 'wrap', marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
          <div style={{ width: 42, height: 42, borderRadius: 'var(--r-md)', flex: 'none', display: 'grid', placeItems: 'center', background: 'var(--info-soft)', color: 'var(--info-ink)' }}><Warehouse size={22} /></div>
          <div>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 10.5, letterSpacing: '0.07em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--accent-ink)', background: 'var(--accent-soft)', borderRadius: 999, padding: '2px 9px', marginBottom: 5 }}><span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--accent)' }} /> Edição Construtora · Construir</span>
            <h1 style={{ fontFamily: 'var(--display)', fontSize: 23, fontWeight: 800, letterSpacing: '-0.025em', color: 'var(--ink)', lineHeight: 1.05 }}>Estoque &amp; Logística</h1>
          </div>
        </div>
        {/* Seletor Operação × Gestão — dois públicos, uma página. */}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 3, background: 'var(--surface-2)', border: '1px solid var(--line)', padding: 4, borderRadius: 12 }}>
          {([['operacao', 'Operação'], ['gestao', 'Gestão']] as const).map(([m, label]) => {
            const on = m === modo
            return <button key={m} onClick={() => trocarModo(m)} style={{ padding: '8px 18px', borderRadius: 9, fontSize: 13.5, fontWeight: 700, cursor: 'pointer', border: 'none', color: on ? 'var(--ink)' : 'var(--ink-3)', background: on ? 'var(--surface)' : 'transparent', boxShadow: on ? 'var(--shadow-sm)' : 'none', fontFamily: 'var(--display)' }}>{label}</button>
          })}
        </div>
      </div>

      {/* Barra de abas do modo atual */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, background: 'var(--surface-2)', border: '1px solid var(--line)', padding: 4, borderRadius: 12, marginBottom: 18 }}>
        {TABS[modo].map(t => {
          const on = t.id === tab
          return (
            <button key={t.id} onClick={() => setTab(t.id)} title={t.locked ? 'Bloqueado — disponível quando a Esfera de Rede for construída' : undefined} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '7px 13px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', border: 'none', color: on ? 'var(--ink)' : 'var(--ink-2)', background: on ? 'var(--surface)' : 'transparent', boxShadow: on ? 'var(--shadow-sm)' : 'none' }}>
              <span style={{ color: on ? 'var(--accent-strong)' : 'inherit', display: 'grid', placeItems: 'center' }}>{t.icon}</span>{t.label}{t.locked && <Lock size={12} style={{ color: 'var(--ink-3)', marginLeft: 1 }} />}
            </button>
          )
        })}
      </div>

      <div className="sil-screen" key={modo + tab}>
        {tab === 'cockpit' && <Cockpit go={go} say={say} />}
        {tab === 'almoxarifados' && <Almoxarifados say={say} />}
        {tab === 'movimentacoes' && <Movimentacoes say={say} />}
        {tab === 'requisicoes' && <Requisicoes say={say} />}
        {tab === 'logistica' && <Logistica say={say} />}
        {tab === 'inventario' && <Inventario say={say} />}
        {tab === 'epi' && <EPI say={say} />}
        {tab === 'ferramentaria' && <Ferramentaria say={say} />}
        {tab === 'abc' && <CurvaABC />}
        {tab === 'custo' && <CustoPorObra />}
        {tab === 'giro' && <GiroRuptura say={say} />}
        {tab === 'rede' && <Rede />}
      </div>

      {toast && <div style={{ position: 'fixed', bottom: 24, left: '50%', background: 'var(--ink)', color: 'var(--surface)', padding: '12px 18px', borderRadius: 11, fontSize: 13.5, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 10, zIndex: 100, boxShadow: 'var(--shadow-lg)', animation: 'silToast .28s cubic-bezier(.2,.7,.2,1) both' }}><Check size={17} style={{ color: 'var(--good)' }} />{toast}</div>}
    </div>
  )
}
