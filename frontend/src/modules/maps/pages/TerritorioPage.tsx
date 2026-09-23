import { useState, type ReactNode } from 'react'
import { Layers, Lock, MapPin, Map as MapIcon, Plane, Radar, Route as RouteIcon, Table } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Locais, MapaDaEmpresa, Vizinhanca, type Say } from '../tabs/operacao'
import { Acervo, Camadas, Rotas, TerritorioBloqueado, Voos } from '../tabs/territorio'
import type { Destino, Ir, TabMaps } from '../types'

/**
 * Maps — **Operação × Território**, dois públicos numa página só (a régua do SIL).
 *
 * O corte não é estético: ele é o mesmo do backend. *Operação* é a metade
 * **fundação** (`Local`) e responde para todo tenant — quem não assina Maps
 * ainda precisa saber onde ficam obra e almoxarifado, senão SIL e SCM perdem a
 * dimensão espacial de quem não pagou por um módulo que não usa. *Território* é
 * a metade vendável: acervo, voo, rota e cerca ficam atrás do entitlement e,
 * sem ele, a aba mostra o cadeado com o que existe do outro lado — nunca some
 * (docs/identidade-visual §3.2).
 */

type Modo = 'operacao' | 'territorio'
type TabId = TabMaps

/**
 * A fila de decisão listava pendências e não ia a lugar nenhum — cada linha era
 * um `<div>` sem `onClick`. Fila que não abre a decisão é cartaz. `ir()` é a
 * porta: o item diz a aba e, quando cabe, o filtro que isola exatamente os
 * locais de que ele fala, para a pessoa não ter de reconstruí-lo à mão.
 */
const MODO_DA_TAB: Record<TabId, Modo> = {
  mapa: 'operacao', locais: 'operacao', vizinhanca: 'operacao',
  camadas: 'territorio', acervo: 'territorio', voos: 'territorio', rotas: 'territorio',
}

interface TabDef { id: TabId; label: string; icon: ReactNode }
const TABS: Record<Modo, TabDef[]> = {
  operacao: [
    { id: 'mapa', label: 'Mapa da empresa', icon: <MapIcon size={15} /> },
    { id: 'locais', label: 'Locais', icon: <Table size={15} /> },
    { id: 'vizinhanca', label: 'Vizinhança', icon: <Radar size={15} /> },
  ],
  territorio: [
    { id: 'camadas', label: 'Camadas', icon: <Layers size={15} /> },
    { id: 'acervo', label: 'Acervo de voos', icon: <MapPin size={15} /> },
    { id: 'voos', label: 'Planos de voo', icon: <Plane size={15} /> },
    { id: 'rotas', label: 'Rotas', icon: <RouteIcon size={15} /> },
  ],
}
let toastTimer: number | undefined

export default function TerritorioPage() {
  const { hasModule } = useAuth()
  const temMaps = hasModule('maps')
  const [modo, setModo] = useState<Modo>('operacao')
  const [tab, setTab] = useState<TabId>('mapa')
  const [toast, setToast] = useState('')
  /** O filtro que a fila de decisão pediu, consumido pela aba de destino. */
  const [destino, setDestino] = useState<Destino | null>(null)

  const say: Say = (m) => {
    setToast(m)
    window.clearTimeout(toastTimer)
    toastTimer = window.setTimeout(() => setToast(''), 2800)
  }
  const trocarModo = (m: Modo) => { setModo(m); setTab(TABS[m][0].id); setDestino(null) }

  const ir: Ir = (d) => {
    const alvo = MODO_DA_TAB[d.tab]
    // Território sem entitlement mostra o cadeado; mandar para lá seria trocar
    // uma pendência acionável por uma parede. O item fica onde está e avisa.
    if (alvo === 'territorio' && !temMaps) {
      say('Essa pendência é do módulo Maps, que não está contratado.')
      return
    }
    setModo(alvo)
    setTab(d.tab)
    setDestino({ ...d, selo: Date.now() })
  }

  return (
    <div style={{ padding: '24px 26px 64px', maxWidth: 1240, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 20, flexWrap: 'wrap', marginBottom: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
          <div style={{ width: 42, height: 42, borderRadius: 'var(--r-md)', flex: 'none', display: 'grid', placeItems: 'center', background: 'var(--net-soft)', color: 'var(--net-ink)' }}>
            <MapIcon size={22} />
          </div>
          <div>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 10.5, letterSpacing: '0.07em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--accent-ink)', background: 'var(--accent-soft)', borderRadius: 999, padding: '2px 9px', marginBottom: 5 }}>
              <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--accent)' }} />
              Edição Construtora · Construir
            </span>
            <h1 style={{ fontFamily: 'var(--display)', fontSize: 23, fontWeight: 800, letterSpacing: '-0.025em', color: 'var(--ink)', lineHeight: 1.05 }}>
              Mapas &amp; Território
            </h1>
          </div>
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 3, background: 'var(--surface-2)', border: '1px solid var(--line)', padding: 4, borderRadius: 12 }}>
          {([['operacao', 'Operação'], ['territorio', 'Território']] as const).map(([m, label]) => {
            const on = m === modo
            return (
              <button key={m} onClick={() => trocarModo(m)}
                title={m === 'territorio' && !temMaps ? 'Módulo Maps não contratado' : undefined}
                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 18px', borderRadius: 9, fontSize: 13.5, fontWeight: 700, cursor: 'pointer', border: 'none', color: on ? 'var(--ink)' : 'var(--ink-3)', background: on ? 'var(--surface)' : 'transparent', boxShadow: on ? 'var(--shadow-sm)' : 'none', fontFamily: 'var(--display)' }}>
                {label}
                {m === 'territorio' && !temMaps && <Lock size={12} style={{ color: 'var(--ink-3)' }} />}
              </button>
            )
          })}
        </div>
      </div>

      {(modo === 'operacao' || temMaps) && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, background: 'var(--surface-2)', border: '1px solid var(--line)', padding: 4, borderRadius: 12, marginBottom: 18 }}>
          {TABS[modo].map((t) => {
            const on = t.id === tab
            return (
              <button key={t.id} onClick={() => { setTab(t.id); setDestino(null) }}
                style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '7px 13px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', border: 'none', color: on ? 'var(--ink)' : 'var(--ink-2)', background: on ? 'var(--surface)' : 'transparent', boxShadow: on ? 'var(--shadow-sm)' : 'none' }}>
                <span style={{ color: on ? 'var(--accent-strong)' : 'inherit', display: 'grid', placeItems: 'center' }}>{t.icon}</span>
                {t.label}
              </button>
            )
          })}
        </div>
      )}

      <div key={`${modo}${tab}${destino?.selo ?? ''}`}>
        {modo === 'territorio' && !temMaps ? (
          <TerritorioBloqueado />
        ) : (
          <>
            {tab === 'mapa' && <MapaDaEmpresa say={say} ir={ir} foco={destino?.foco ?? null} />}
            {tab === 'locais' && <Locais say={say} ir={ir} filtroInicial={destino?.filtro} />}
            {tab === 'vizinhanca' && <Vizinhanca say={say} />}
            {tab === 'camadas' && <Camadas />}
            {tab === 'acervo' && <Acervo say={say} />}
            {tab === 'voos' && <Voos say={say} />}
            {tab === 'rotas' && <Rotas say={say} />}
          </>
        )}
      </div>

      {toast && (
        <div role="status"
          style={{ position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)', zIndex: 60, padding: '11px 18px', borderRadius: 10, background: 'var(--surface)', border: '1px solid var(--line)', boxShadow: 'var(--shadow-lg)', fontSize: 13.5, color: 'var(--ink)' }}>
          {toast}
        </div>
      )}
    </div>
  )
}
