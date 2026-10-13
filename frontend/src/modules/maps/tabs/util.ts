import { parseApiErrors } from '@/utils/formErrors'

/** Constantes e funções que as abas do Maps compartilham (os componentes ficam em `comum.tsx`). */

export type Say = (mensagem: string) => void

export const selectEstilo: React.CSSProperties = {
  padding: '7px 11px', borderRadius: 8, border: '1px solid var(--line)',
  background: 'var(--surface)', color: 'var(--ink)', fontSize: 13,
}
export const inputEstilo: React.CSSProperties = { ...selectEstilo, width: '100%' }

/** A frase que o backend mandou — ou a de infraestrutura, quando não houve resposta. */
export function motivo(erro: unknown, padrao: string): string {
  const campos = parseApiErrors(erro)
  return campos._form || Object.values(campos)[0] || padrao
}

export const ROTULO_TIPO: Record<string, string> = {
  obra: 'Obras', empreendimento: 'Empreendimentos', fornecedor: 'Fornecedores',
  local_estoque: 'Almoxarifados', unidade: 'Unidades (lotes)', avulso: 'Pontos avulsos',
}
