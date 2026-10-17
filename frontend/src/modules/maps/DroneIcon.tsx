import type { CSSProperties } from 'react'

/** Quadricóptero — o `lucide-react` só tem avião, e plano de voo aqui é de drone.
 *  Mesma assinatura dos ícones do lucide (`size`, `style`) para trocar sem mexer no resto. */
export function DroneIcon({ size = 16, style }: { size?: number; style?: CSSProperties }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden style={style}
    >
      <rect x="9" y="9" width="6" height="6" rx="1.5" />
      <path d="M9.5 9.5 6 6M14.5 9.5 18 6M9.5 14.5 6 18M14.5 14.5 18 18" />
      <circle cx="5" cy="5" r="2.2" />
      <circle cx="19" cy="5" r="2.2" />
      <circle cx="5" cy="19" r="2.2" />
      <circle cx="19" cy="19" r="2.2" />
    </svg>
  )
}
