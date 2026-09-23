import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Check, ChevronDown, Search } from 'lucide-react'
import { contemSemAcento } from '@/utils/texto'
import { useObras } from '../hooks'

/** Troca de obra **mantendo o posto** — quem compara a semana de duas obras não
 *  quer voltar ao início. O posto vem da própria rota. */
export function SeletorDeObra({ obraId, nome }: { obraId: number; nome: string }) {
  const [aberto, setAberto] = useState(false)
  const [busca, setBusca] = useState('')
  const caixa = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { data: obras = [], isLoading } = useObras()

  /** O posto é o último segmento da rota — trocar de obra o preserva. */
  const posto = pathname.split('/').filter(Boolean).pop() ?? 'plano'

  useEffect(() => {
    if (!aberto) return
    function fora(e: MouseEvent) {
      if (caixa.current && !caixa.current.contains(e.target as Node)) setAberto(false)
    }
    document.addEventListener('mousedown', fora)
    return () => document.removeEventListener('mousedown', fora)
  }, [aberto])

  const visiveis = busca.trim()
    ? obras.filter((o) => contemSemAcento(o.nome_obra, busca))
    : obras

  return (
    <div ref={caixa} style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={() => { setAberto((v) => !v); setBusca('') }}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 8,
          background: 'transparent', border: '1px solid var(--line)',
          borderRadius: 'var(--r-sm)', padding: '6px 10px', cursor: 'pointer',
          color: 'var(--ink)', fontSize: 13.5, fontWeight: 650, maxWidth: 380,
        }}
      >
        <span
          style={{
            width: 7, height: 7, borderRadius: 2,
            background: 'var(--accent)', flexShrink: 0,
          }}
        />
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {nome}
        </span>
        <ChevronDown size={14} style={{ flexShrink: 0, color: 'var(--ink-3)' }} />
      </button>

      {aberto && (
        <div
          style={{
            position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 40,
            width: 340, background: 'var(--surface)',
            border: '1px solid var(--line)', borderRadius: 'var(--r-md)',
            boxShadow: 'var(--shadow-lg)', overflow: 'hidden',
          }}
        >
          <div
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '9px 12px', borderBottom: '1px solid var(--line-2)',
            }}
          >
            <Search size={14} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
            <input
              autoFocus
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar obra"
              style={{
                border: 'none', outline: 'none', background: 'transparent',
                color: 'var(--ink)', fontSize: 13, width: '100%',
              }}
            />
          </div>

          <div style={{ maxHeight: 320, overflowY: 'auto' }}>
            {isLoading && (
              <div style={{ padding: '14px 12px', fontSize: 12.5, color: 'var(--ink-3)' }}>
                Carregando obras…
              </div>
            )}
            {!isLoading && visiveis.length === 0 && (
              <div style={{ padding: '14px 12px', fontSize: 12.5, color: 'var(--ink-3)' }}>
                Nenhuma obra com esse nome.
              </div>
            )}
            {visiveis.map((o) => (
              <button
                key={o.obra_id}
                type="button"
                onClick={() => {
                  setAberto(false)
                  navigate(`/app/pdca/o/${o.obra_id}/${posto}`)
                }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                  background: o.obra_id === obraId ? 'var(--surface-2)' : 'transparent',
                  border: 'none', textAlign: 'left', cursor: 'pointer',
                  padding: '9px 12px', color: 'var(--ink)', fontSize: 13,
                }}
              >
                <Check
                  size={13}
                  style={{
                    flexShrink: 0,
                    color: 'var(--accent-ink)',
                    visibility: o.obra_id === obraId ? 'visible' : 'hidden',
                  }}
                />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {o.nome_obra}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
