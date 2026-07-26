import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronDown, LayoutGrid } from 'lucide-react'
import { OrcStyles } from '../ui'
import { PAGINAS, PAGINA_POR_CHAVE, type ChavePagina } from '../paginas'

/** Moldura das páginas do módulo: uma faixa fina no topo com a volta ao hub, o
 *  troca-página e o seletor da própria página; o resto da tela é conteúdo. */
export default function PaginaShell({ pagina, seletor, acoes, children, semRolagem }: {
  pagina: ChavePagina
  seletor?: ReactNode
  acoes?: ReactNode
  children: ReactNode
  semRolagem?: boolean
}) {
  const def = PAGINA_POR_CHAVE[pagina]
  const [menuAberto, setMenuAberto] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (!menuAberto) return
    const fechar = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuAberto(false)
    }
    document.addEventListener('mousedown', fechar)
    return () => document.removeEventListener('mousedown', fechar)
  }, [menuAberto])

  return (
    <div
      className="orc-tela"
      style={{
        display: 'flex', flexDirection: 'column',
        height: semRolagem ? 'calc(100vh - var(--topbar-h, 56px))' : undefined,
        minHeight: semRolagem ? undefined : 'calc(100vh - var(--topbar-h, 56px))',
        background: 'var(--ground)',
      }}
    >
      <OrcStyles />
      <header style={{
        display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
        padding: '0 18px', minHeight: 46, flex: 'none',
        background: 'var(--surface)', borderBottom: '1px solid var(--line)',
        position: 'sticky', top: 0, zIndex: 20,
      }}>
        <Link
          to="/app/orcamento"
          title="Voltar ao hub do Orçamento"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--ink-3)',
            fontSize: 12.5, fontWeight: 650, textDecoration: 'none',
          }}
        >
          <LayoutGrid size={14} />Orçamento
        </Link>

        <div ref={menuRef} style={{ position: 'relative' }}>
          <button
            onClick={() => setMenuAberto(v => !v)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, border: '1px solid var(--line)',
              background: 'var(--surface-2)', borderRadius: 'var(--r-sm)', padding: '5px 9px 5px 11px',
              fontFamily: 'var(--display)', fontSize: 14, fontWeight: 700, color: 'var(--ink)', cursor: 'pointer',
            }}
          >
            {def.titulo}<ChevronDown size={14} style={{ color: 'var(--ink-3)' }} />
          </button>
          {menuAberto && (
            <div className="orc-modal" style={{
              position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 40, minWidth: 268,
              background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-md)',
              boxShadow: 'var(--shadow-lg)', padding: 5,
            }}>
              {PAGINAS.map(p => (
                <button
                  key={p.chave}
                  onClick={() => { setMenuAberto(false); navigate(p.rota) }}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left', border: 'none', cursor: 'pointer',
                    padding: '8px 10px', borderRadius: 'var(--r-sm)', background: p.chave === pagina ? 'var(--inset)' : 'transparent',
                  }}
                >
                  <span style={{ display: 'block', fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>{p.titulo}</span>
                  <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)' }}>{p.verbo}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {seletor}
        <div style={{ flex: 1 }} />
        {acoes}
      </header>

      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>{children}</div>
    </div>
  )
}
