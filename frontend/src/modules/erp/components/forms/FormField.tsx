import type { ReactNode } from 'react'
import { FieldError } from '@/utils/formErrors'
import { labelStyle } from './formStyles'

interface FieldProps {
  label: string
  error?: string
  children: ReactNode
}

/** Wrapper label + campo + erro, padronizando o espaçamento dos formulários de lançamento (D.1.1). */
export function Field({ label, error, children }: FieldProps) {
  return (
    <label className="block">
      <span style={labelStyle}>{label}</span>
      {children}
      <FieldError msg={error} />
    </label>
  )
}
