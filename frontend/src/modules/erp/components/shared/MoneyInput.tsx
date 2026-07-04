import React from 'react'
import { maskMoney, digitsToCents } from '@/utils/money'

interface MoneyInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type'> {
  /** Valor em centavos inteiros (nunca float — ver utils/money.ts). */
  valueCents: number
  onChangeCents: (cents: number) => void
}

/**
 * Input monetário em BRL. O estado do formulário guarda **centavos inteiros**;
 * a máscara formata "1.234,56" no `value=` e o prefixo "R$" é só visual.
 */
export const MoneyInput: React.FC<MoneyInputProps> = ({ valueCents, onChangeCents, style, ...props }) => {
  return (
    <div style={{ position: 'relative' }}>
      <span style={{
        position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)',
        fontSize: '0.875rem', color: 'var(--color-text-muted)', pointerEvents: 'none',
      }}>
        R$
      </span>
      <input
        {...props}
        type="text"
        inputMode="decimal"
        value={maskMoney(String(valueCents))}
        onChange={e => onChangeCents(digitsToCents(e.target.value))}
        style={{
          padding: '8px 12px 8px 36px', border: '1.5px solid #e2e8f0', borderRadius: '8px',
          fontSize: '0.875rem', fontFamily: 'var(--font-body)', color: 'var(--color-text)',
          background: '#FFFFFF', outline: 'none', width: '100%', textAlign: 'right',
          ...style,
        }}
      />
    </div>
  )
}
