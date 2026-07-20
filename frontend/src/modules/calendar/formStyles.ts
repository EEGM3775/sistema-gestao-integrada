/** Estilos de formulário do Calendário — em módulo à parte (react-refresh/only-export-components). */

export const inputStyle: React.CSSProperties = {
  width: '100%', padding: '8px 12px', borderRadius: '8px',
  border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)',
  fontSize: '0.875rem', color: 'var(--color-text)', background: '#FFFFFF', outline: 'none',
}

export const selectStyle: React.CSSProperties = { ...inputStyle, cursor: 'pointer' }

export const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: '0.8rem', fontWeight: 600,
  marginBottom: '4px', fontFamily: 'var(--font-body)', color: 'var(--color-brand)',
}

export const buttonPrimaryStyle: React.CSSProperties = {
  padding: '9px 18px', borderRadius: '8px', border: 'none',
  background: 'var(--color-brand)', color: '#FFFFFF',
  fontSize: '0.875rem', fontWeight: 600, fontFamily: 'var(--font-body)', cursor: 'pointer',
}

export const buttonSecondaryStyle: React.CSSProperties = {
  padding: '9px 18px', borderRadius: '8px', border: '1.5px solid #e2e8f0',
  background: '#FFFFFF', color: 'var(--color-text-muted)',
  fontSize: '0.875rem', fontWeight: 600, fontFamily: 'var(--font-body)', cursor: 'pointer',
}

export const buttonDangerStyle: React.CSSProperties = {
  padding: '9px 18px', borderRadius: '8px', border: '1.5px solid #fecaca',
  background: '#FFFFFF', color: '#dc2626',
  fontSize: '0.875rem', fontWeight: 600, fontFamily: 'var(--font-body)', cursor: 'pointer',
}
