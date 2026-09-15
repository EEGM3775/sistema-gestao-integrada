import type { PillKind } from '@/components/malha'
import type { StatusAditivo, StatusMedicao } from '../types'

/**
 * A cor de cada estado de documento do contrato — **uma só definição**.
 *
 * Morava dentro da `ContratosPage`, e as outras telas a importavam de lá: uma
 * página virando biblioteca da vizinha. Estado de documento é vocabulário do
 * módulo, não detalhe de uma tela, e o boletim impresso precisa dele tanto
 * quanto a carteira.
 */
export const CORES_MEDICAO: Record<StatusMedicao, PillKind> = {
  rascunho: 'slate',
  em_aprovacao: 'info',
  aprovada: 'good',
  reprovada: 'danger',
  cancelada: 'slate',
}

export const CORES_ADITIVO: Record<StatusAditivo, PillKind> = {
  rascunho: 'slate',
  em_aprovacao: 'info',
  aprovado: 'good',
  reprovado: 'danger',
  cancelado: 'slate',
}
