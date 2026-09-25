import { useEffect, useRef } from 'react'

interface CampoCodigoProps {
  id: string
  valor: string
  aoMudar: (v: string) => void
  /** Aceita também o código de recuperação (letras e hífen), e não só 6 dígitos. */
  recuperacao?: boolean
  focar?: boolean
  rotulo?: string
}

/**
 * O código do app autenticador. `one-time-code` deixa o celular sugerir o
 * código sozinho, e `numeric` abre o teclado de números no campo.
 */
export function CampoCodigo({ id, valor, aoMudar, recuperacao = false, focar = true, rotulo }: CampoCodigoProps) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => { if (focar) ref.current?.focus() }, [focar, recuperacao])
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label htmlFor={id} style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)' }}>
        {rotulo ?? (recuperacao ? 'Código de recuperação' : 'Código de 6 dígitos do app')}
      </label>
      <input
        ref={ref}
        id={id}
        value={valor}
        onChange={e => aoMudar(recuperacao
          ? e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 11)
          : e.target.value.replace(/\D/g, '').slice(0, 6))}
        inputMode={recuperacao ? 'text' : 'numeric'}
        autoComplete="one-time-code"
        placeholder={recuperacao ? 'xxxxx-xxxxx' : '000000'}
        style={{
          fontFamily: 'var(--font-mono, monospace)', fontSize: 22, letterSpacing: recuperacao ? '0.08em' : '0.4em',
          padding: '10px 14px', borderRadius: 'var(--r-sm)', border: '1.5px solid var(--line)',
          background: 'var(--surface)', color: 'var(--ink)', outline: 'none', width: '100%',
        }}
      />
    </div>
  )
}
