import React from 'react'
import { formatBRL } from '@/utils/money'

interface MoneyDisplayProps {
  /** Valor em centavos inteiros (nunca float — ver utils/money.ts). */
  cents: number | null | undefined
  /** Pinta verde/vermelho conforme o sinal — útil em fluxo de caixa. */
  signed?: boolean
  className?: string
}

export const MoneyDisplay: React.FC<MoneyDisplayProps> = ({ cents, signed, className }) => {
  const value = cents ?? 0
  const color = signed ? (value > 0 ? '#16a34a' : value < 0 ? '#dc2626' : 'var(--color-text)') : 'var(--color-text)'
  return (
    <span className={className} style={{ fontVariantNumeric: 'tabular-nums', color, fontWeight: signed ? 600 : 400 }}>
      {formatBRL(value)}
    </span>
  )
}
