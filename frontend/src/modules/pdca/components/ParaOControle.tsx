import { Navigate, useLocation } from 'react-router-dom'

/** `hoje` e `semana` viraram abas do Controle (decisão do dono, 10/10/2026).
 *  O link antigo continua abrindo no mesmo lugar, com a query que trazia. */
export function ParaOControle({ aba }: { aba: 'hoje' | 'semana' }) {
  const { search } = useLocation()
  const params = new URLSearchParams(search)
  if (aba === 'semana') params.set('aba', 'semana')
  const query = params.toString()
  return <Navigate to={`../controle${query ? `?${query}` : ''}`} replace />
}
