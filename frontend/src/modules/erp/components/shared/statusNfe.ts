import type { StatusNFE } from '../../types'

/** Rótulos e cores de `StatusNFE` — compartilhado entre `StatusNfeBadge` e a tela de Notas Fiscais (D.1.3). */

export const STATUS_NFE_CONFIG: Record<StatusNFE, { label: string; bg: string; color: string }> = {
  AGUARDANDO:  { label: 'Aguardando emissão', bg: '#f3f4f6', color: '#374151' },
  PROCESSANDO: { label: 'Processando',        bg: '#e0f2fe', color: '#0369a1' },
  EMITIDA:     { label: 'Emitida',            bg: '#dcfce7', color: '#166534' },
  ERRO:        { label: 'Erro',               bg: '#fee2e2', color: '#991b1b' },
  CANCELADA:   { label: 'Cancelada',          bg: '#fef3c7', color: '#92400e' },
}
