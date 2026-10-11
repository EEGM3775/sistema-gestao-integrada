import { Navigate, useLocation } from 'react-router-dom'

/** `controlar` virou `analisar` (decisão do dono, 10/10/2026): o controle da
 *  execução foi para o PDCA. O link antigo abre a análise da mesma obra. */
export function ParaAnalisar() {
  const { search } = useLocation()
  return <Navigate to={`/app/orcamento/analisar${search}`} replace />
}
