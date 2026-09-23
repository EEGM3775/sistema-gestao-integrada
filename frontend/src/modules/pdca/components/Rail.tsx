import { NavLink } from 'react-router-dom'
import { Lock } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { POSTOS, type Posto } from '../postos'


export function Rail({ obraId }: { obraId: number }) {
  const { hasPermission } = useAuth()

  return (
    <nav
      aria-label="Postos de trabalho da obra"
      style={{
        width: 148,
        flexShrink: 0,
        borderRight: '1px solid var(--line)',
        background: 'var(--surface)',
        padding: '10px 8px',
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      {POSTOS.map((posto) => {
        const liberado = hasPermission(posto.permissao)
        return liberado
          ? <ItemDoRail key={posto.codigo} posto={posto} obraId={obraId} />
          : <ItemTrancado key={posto.codigo} posto={posto} />
      })}
    </nav>
  )
}

function ItemDoRail({ posto, obraId }: { posto: Posto; obraId: number }) {
  return (
    <NavLink
      to={`/app/pdca/o/${obraId}/${posto.codigo}`}
      style={({ isActive }) => ({
        textDecoration: 'none',
        display: 'block',
        padding: '9px 10px',
        borderRadius: 'var(--r-sm)',
        background: isActive ? 'var(--accent-soft)' : 'transparent',
        borderLeft: `2px solid ${isActive ? 'var(--accent)' : 'transparent'}`,
      })}
    >
      {({ isActive }) => (
        <>
          <div
            style={{
              fontSize: 11.5,
              fontWeight: 750,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: isActive ? 'var(--accent-ink)' : 'var(--ink-2)',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            {posto.rotulo}
            {!posto.noAr && (
              <span
                title="Ainda não está no ar"
                style={{
                  width: 5, height: 5, borderRadius: 999,
                  background: 'var(--ink-3)', opacity: 0.6, flexShrink: 0,
                }}
              />
            )}
          </div>
          <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 2 }}>
            {posto.cadencia}
          </div>
        </>
      )}
    </NavLink>
  )
}

function ItemTrancado({ posto }: { posto: Posto }) {
  return (
    <div
      title={`Requer a permissão “${posto.permissao}”. Peça ao administrador da empresa.`}
      style={{
        padding: '9px 10px',
        borderRadius: 'var(--r-sm)',
        borderLeft: '2px solid transparent',
        opacity: 0.55,
        cursor: 'not-allowed',
      }}
    >
      <div
        style={{
          fontSize: 11.5,
          fontWeight: 750,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: 'var(--ink-3)',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        {posto.rotulo}
        <Lock size={11} strokeWidth={2.4} />
      </div>
      <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 2 }}>
        sem acesso
      </div>
    </div>
  )
}
