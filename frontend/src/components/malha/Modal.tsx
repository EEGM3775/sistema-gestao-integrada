import { useEffect } from 'react'
import type { ReactNode } from 'react'

interface ModalProps {
  titulo: ReactNode
  onClose: () => void
  children: ReactNode
  rodape?: ReactNode
  largura?: number
}

/**
 * Diálogo da Malha. Promovido junto do {@link Btn} para o IE.0c.
 *
 * Fecha no `Esc` e no clique fora — os dois gestos que o usuário tenta antes de
 * procurar o "X". `onMouseDown` (e não `onClick`) no fundo porque arrastar uma
 * seleção de dentro para fora terminaria o clique no backdrop e fecharia o
 * diálogo no meio de uma cópia de texto.
 */
export function Modal({ titulo, onClose, children, rodape, largura = 520 }: ModalProps) {
  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  }, [onClose])

  return (
    <div
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 92, background: 'rgba(6,14,26,.5)',
        backdropFilter: 'blur(3px)', display: 'flex', justifyContent: 'center',
        alignItems: 'flex-start', padding: '7vh 16px', overflowY: 'auto',
      }}
    >
      <div style={{
        width: '100%', maxWidth: largura, background: 'var(--surface)',
        border: '1px solid var(--line)', borderRadius: 'var(--r-lg)',
        boxShadow: 'var(--shadow-lg)',
      }}>
        <div style={{
          padding: '14px 19px', borderBottom: '1px solid var(--line)',
          fontFamily: 'var(--display)', fontSize: 15.5, fontWeight: 700, color: 'var(--ink)',
        }}>{titulo}</div>
        <div style={{ padding: 19 }}>{children}</div>
        {rodape && (
          <div style={{
            display: 'flex', justifyContent: 'flex-end', gap: 9, flexWrap: 'wrap',
            padding: '13px 19px', borderTop: '1px solid var(--line)',
          }}>{rodape}</div>
        )}
      </div>
    </div>
  )
}
