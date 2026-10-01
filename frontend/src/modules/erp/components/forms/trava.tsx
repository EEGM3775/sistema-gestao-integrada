import type { ReactNode } from 'react'
import { Lock } from 'lucide-react'

/**
 * O que a baixa trava na conta (item 57) — a frase vem da API
 * (`travado_porque`), a mesma que ela devolveria se o campo fosse enviado.
 */
export function AvisoDeTrava({ motivo }: { motivo: string }) {
  if (!motivo) return null
  return (
    <div
      role="note"
      className="flex gap-2 text-sm"
      style={{
        padding: '10px 12px', borderRadius: 'var(--r-md)', background: 'var(--accent-soft)',
        color: 'var(--accent-ink)', lineHeight: 1.45,
      }}
    >
      <Lock size={15} style={{ flex: 'none', marginTop: 2 }} />
      <span>{motivo}</span>
    </div>
  )
}

/** Campo travado é texto, não caixa desabilitada (frontend-convencoes §10). */
export function TextoTravado({ children }: { children: ReactNode }) {
  return (
    <span className="flex items-center gap-2 text-sm" style={{ padding: '8px 0', color: 'var(--ink)', fontWeight: 600 }}>
      <Lock size={13} style={{ color: 'var(--ink-3)' }} /> {children}
    </span>
  )
}
