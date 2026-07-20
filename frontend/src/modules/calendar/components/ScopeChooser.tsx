import type { RecurrenceScope } from '../types'
import { buttonSecondaryStyle } from '../formStyles'

interface Props {
  /** 'save' rotula como edição; 'delete' como exclusão. */
  action: 'save' | 'delete'
  onChoose: (scope: RecurrenceScope) => void
  onCancel: () => void
  pending?: boolean
}

const OPTIONS: { scope: RecurrenceScope; label: string }[] = [
  { scope: 'this', label: 'Somente este evento' },
  { scope: 'future', label: 'Este e os seguintes' },
  { scope: 'all', label: 'Todos os eventos da série' },
]

/**
 * Pergunta o alcance ao editar/excluir uma ocorrência de série recorrente
 * (padrão Google/Outlook): só esta, desta em diante, ou a série toda.
 */
export function ScopeChooser({ action, onChoose, onCancel, pending }: Props) {
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center px-4">
      <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onClick={() => !pending && onCancel()} aria-hidden="true" />
      <div
        role="dialog" aria-modal="true"
        aria-label={action === 'delete' ? 'Excluir evento recorrente' : 'Editar evento recorrente'}
        className="relative w-full rounded-xl"
        style={{ maxWidth: 380, background: '#FFFFFF', boxShadow: 'var(--shadow-lg)', border: '1.5px solid #e2e8f0' }}
      >
        <div className="px-5 py-4" style={{ borderBottom: '1.5px solid #e2e8f0' }}>
          <h3 className="text-base font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            {action === 'delete' ? 'Excluir evento recorrente' : 'Editar evento recorrente'}
          </h3>
        </div>
        <div className="px-5 py-4 flex flex-col gap-2">
          {OPTIONS.map(opt => (
            <button
              key={opt.scope} type="button" disabled={pending}
              onClick={() => onChoose(opt.scope)}
              className="w-full text-left px-4 py-2.5 rounded-lg text-sm font-semibold"
              style={{
                border: '1.5px solid #e2e8f0', background: '#f8fafc',
                color: 'var(--color-text)', fontFamily: 'var(--font-body)',
                cursor: pending ? 'wait' : 'pointer',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="px-5 py-3.5 flex justify-end" style={{ borderTop: '1.5px solid #e2e8f0', background: '#f8fafc' }}>
          <button type="button" onClick={onCancel} disabled={pending} style={{ ...buttonSecondaryStyle, opacity: pending ? 0.6 : 1 }}>
            Cancelar
          </button>
        </div>
      </div>
    </div>
  )
}
