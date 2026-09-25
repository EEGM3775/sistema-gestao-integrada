import type { CSSProperties } from 'react'

/** O campo de formulário do escritório. */
export const entrada: CSSProperties = {
  width: '100%', padding: '8px 10px', borderRadius: 8,
  border: '1px solid var(--line)', background: 'var(--surface)',
  color: 'var(--ink)', fontSize: 13, fontFamily: 'inherit',
}

/** O campo do canteiro — 48 px e fonte de 16 px (abaixo disso o celular dá
 *  zoom ao focar). */
export const campoGrande: CSSProperties = {
  width: '100%', minHeight: 48, padding: '12px 13px', borderRadius: 10,
  border: '1px solid var(--line)', background: 'var(--surface)',
  color: 'var(--ink)', fontSize: 16, fontFamily: 'inherit',
}
