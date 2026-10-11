import { Navigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { portaDoPapel } from '../postos'

/** **Abrir a obra cai no posto do seu papel** (§3.3 da planta): o planejador
 *  no `PLANO`, o técnico de segurança na `SEGURANÇA`, quem assina no `HOJE`.
 *
 *  Só o endereço sem posto passa por aqui. O link colado, a fila e a paleta
 *  levam ao posto que nomeiam, e o rail continua com os seis — a porta escolhe
 *  onde se entra, não o que existe.
 *
 *  Quem tem só o papel de campo cai no `HOJE` da obra, e não na superfície de
 *  campo: ela é *a minha frente de hoje*, sem obra, e quem pediu esta obra no
 *  escritório estaria sendo tirado dela. A passagem para o campo fica na
 *  carteira, que é onde se chega antes de escolher obra. */
export function PortaDaObra() {
  const { roles, hasPermission } = useAuth()
  const porta = portaDoPapel(roles, hasPermission)
  return <Navigate to={porta === 'campo' ? 'controle' : porta} replace />
}
