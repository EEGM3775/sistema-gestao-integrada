import { useState, type ReactNode } from 'react'
import { Lock, Map as MapIcon, Plane, Radar, Route as RouteIcon, Layers } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { MapaDaEmpresa, Vizinhanca, type Say } from '../tabs/operacao'
import { Acervo, Rotas, TerritorioBloqueado, Voos } from '../tabs/territorio'
import type { Destino, Ir, TabMaps } from '../types'

/**
 * Maps — **uma página, uma fileira de abas** (item 63 do dono).
 *
 * Antes havia dois níveis: um seletor Operação × Território e, dentro de cada
 * um, as suas abas. O corte era o do backend (fundação × produto pago) e
 * ninguém precisava dele na tela — quem abria via "Território" sem saber o que
 * era, e a metade com as camadas parecia vazia. O corte continua valendo onde
 * importa: as abas do módulo pago ganham um cadeado quando o tenant não o
 * assina, e abrem o cartão que explica o que existe do outro lado (nunca
 * somem — docs/identidade-visual §3.2).
 *
 * As antigas abas **Locais** e **Camadas** viraram partes do Mapa da empresa:
 * a lista de locais é o painel ao lado do mapa (item 67) e as camadas são o
 * que se liga e desliga por cima dele (item 68).
 */

interface TabDef { id: TabMaps; label: string; icon: ReactNode; pago: boolean }
const TABS: TabDef[] = [
  { id: 'mapa', label: 'Mapa da empresa', icon: <MapIcon size={15} />, pago: false },
  { id: 'vizinhanca', label: 'Vizinhança', icon: <Radar size={15} />, pago: false },
  { id: 'voos', label: 'Planos de voo', icon: <Plane size={15} />, pago: true },
  { id: 'acervo', label: 'Acervo de voos', icon: <Layers size={15} />, pago: true },
  { id: 'rotas', label: 'Rotas', icon: <RouteIcon size={15} />, pago: true },
]
const PAGA = new Set(TABS.filter((t) => t.pago).map((t) => t.id))
let toastTimer: number | undefined

export default function TerritorioPage() {
  const { hasModule } = useAuth()
  const temMaps = hasModule('maps')
  const [tab, setTab] = useState<TabMaps>('mapa')
  const [toast, setToast] = useState('')
  /** O filtro que a fila de decisão pediu, consumido pela aba de destino. */
  const [destino, setDestino] = useState<Destino | null>(null)

  const say: Say = (m) => {
    setToast(m)
    window.clearTimeout(toastTimer)
    toastTimer = window.setTimeout(() => setToast(''), 3200)
  }

  /**
   * A porta da fila de decisão: o item diz a aba e, quando cabe, o filtro que
   * isola exatamente os locais de que ele fala.
   */
  const ir: Ir = (d) => {
    // Aba paga sem entitlement mostra o cadeado; mandar para lá seria trocar
    // uma pendência acionável por uma parede. O item fica onde está e avisa.
    if (PAGA.has(d.tab) && !temMaps) {
      say('Pendência do módulo Maps, que não está contratado.')
      return
    }
    setTab(d.tab)
    setDestino({ ...d, selo: Date.now() })
  }
  const bloqueada = PAGA.has(tab) && !temMaps

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
      </div>

      <div role="tablist" style={{ display: 'flex', flexWrap: 'wrap', gap: 3, background: 'var(--surface-2)', border: '1px solid var(--line)', padding: 4, borderRadius: 12, marginBottom: 18 }}>
        {TABS.map((t) => {
          const on = t.id === tab
          const travada = t.pago && !temMaps
          return (
            <button key={t.id} role="tab" aria-selected={on} onClick={() => { setTab(t.id); setDestino(null) }}
              title={travada ? 'Módulo Maps não contratado' : undefined}
              style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '7px 13px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', border: 'none', color: on ? 'var(--ink)' : 'var(--ink-2)', background: on ? 'var(--surface)' : 'transparent', boxShadow: on ? 'var(--shadow-sm)' : 'none' }}>
              <span style={{ color: on ? 'var(--accent-strong)' : 'inherit', display: 'grid', placeItems: 'center' }}>{t.icon}</span>
              {t.label}
              {travada && <Lock size={12} style={{ color: 'var(--ink-3)' }} />}
            </button>
          )
        })}
      </div>

      <div key={`${tab}${destino?.selo ?? ''}`}>
        {bloqueada ? (
          <TerritorioBloqueado />
        ) : (
          <>
            {tab === 'mapa' && (
              <MapaDaEmpresa say={say} ir={ir} temMaps={temMaps} foco={destino?.foco ?? null} filtroInicial={destino?.filtro} />
            )}
            {tab === 'vizinhanca' && <Vizinhanca say={say} />}
            {tab === 'voos' && <Voos say={say} />}
            {tab === 'acervo' && <Acervo say={say} />}
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
