import type { FieldErrors } from '@/utils/formErrors'

/**
 * Espalha o erro da API pelos campos do formulário e devolve o que sobrou
 * para a faixa de aviso.
 *
 * Antes, erro de um campo que o formulário não tem (um `non_field_errors`,
 * um campo de outro nível) era descartado: o botão voltava ao normal e a
 * pessoa não via nada — "clico em salvar e nada acontece" (item 57).
 */
export function distribuirErros(
  parsed: FieldErrors,
  camposDoForm: readonly string[],
  marcar: (campo: string, msg: string) => void,
): string | null {
  const { _form, ...campo } = parsed
  const sobras: string[] = []
  for (const [nome, msg] of Object.entries(campo)) {
    const alvo = nome === 'valor' ? 'valorCents' : nome
    if (camposDoForm.includes(alvo)) marcar(alvo, msg)
    else sobras.push(msg)
  }
  if (_form) sobras.unshift(_form)
  if (sobras.length) return sobras.join(' ')
  return Object.keys(campo).length ? null : 'Não foi possível salvar a conta.'
}

/** Campos que o formulário não mostra com mensagem própria. */
const SEM_MENSAGEM_NA_TELA = new Set(['empreendimento', 'fornecedor', 'cliente', 'valorCents', 'data_vencimento'])

/**
 * A validação do navegador também não reprova em silêncio (item 57).
 *
 * Com o campo travado virando texto, os que ele protege não têm mais onde
 * mostrar erro — e o `empreendimento` nunca teve. Qualquer reprovação que caia
 * nesses campos vai para a faixa de aviso, com o nome do campo.
 */
export function errosSemLugar(erros: Record<string, { message?: string } | undefined>): string | null {
  const frases = Object.entries(erros)
    .filter(([campo, e]) => e && SEM_MENSAGEM_NA_TELA.has(campo))
    .map(([campo, e]) => `${ROTULOS[campo] ?? campo}: ${e?.message ?? 'valor inválido'}`)
  return frases.length ? `Confira — ${frases.join(' · ')}` : null
}

const ROTULOS: Record<string, string> = {
  empreendimento: 'Obra/empreendimento', fornecedor: 'Fornecedor', cliente: 'Cliente',
  valorCents: 'Valor', data_vencimento: 'Vencimento',
}
