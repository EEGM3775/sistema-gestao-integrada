import { useEffect, useState, type ReactNode } from 'react'
import { X } from 'lucide-react'

/**
 * Painel deslizante (slide-over) lateral — primeiro uso no projeto
 * (docs/modulos/moduloerp.md §5.5, arquétipo "Workspace de lista financeira":
 * listão + filtro + Sheet de detalhe/edição, em vez de navegar para outra
 * página a cada clique numa linha).
 *
 * Sem libs de animação — `entered` liga a transição CSS um frame após montar,
 * o que dá o efeito de "deslizar" sem depender de `@keyframes` globais.
 */

interface SheetProps {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  /** Ações fixas no rodapé (ex.: "Cancelar" / "Salvar", "Confirmar baixa"). */
  footer?: ReactNode
  /** Largura do painel — telas com formulários maiores (lançamento + rateio) podem precisar de mais espaço. */
  width?: number | string
  children: ReactNode
}

export function Sheet({ open, onClose, title, description, footer, width = 480, children }: SheetProps) {
  const [entered, setEntered] = useState(false)

  useEffect(() => {
    if (!open) {
      setEntered(false)
      return
    }

    const frame = requestAnimationFrame(() => setEntered(true))
    const handleKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleKeyDown)

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      cancelAnimationFrame(frame)
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0 transition-opacity duration-200 ease-out"
        style={{ background: 'rgba(15, 23, 42, 0.45)', opacity: entered ? 1 : 0 }}
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative h-full flex flex-col transition-transform duration-200 ease-out"
        style={{
          width, maxWidth: '100vw', background: '#FFFFFF',
          borderLeft: '1.5px solid #e2e8f0', boxShadow: 'var(--shadow-lg)',
          transform: entered ? 'translateX(0)' : 'translateX(100%)',
        }}
      >
        <header className="flex items-start justify-between gap-3 px-6 py-5" style={{ borderBottom: '1.5px solid #e2e8f0' }}>
          <div>
            <h2 className="text-lg font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              {title}
            </h2>
            {description && (
              <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                {description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar painel"
            className="p-1.5 rounded-lg shrink-0 transition-colors duration-150"
            style={{ color: 'var(--color-text-muted)', cursor: 'pointer' }}
            onMouseEnter={e => (e.currentTarget.style.color = 'var(--color-brand)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--color-text-muted)')}
          >
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>

        {footer && (
          <footer className="flex items-center justify-end gap-2 px-6 py-4" style={{ borderTop: '1.5px solid #e2e8f0', background: '#f8fafc' }}>
            {footer}
          </footer>
        )}
      </div>
    </div>
  )
}
