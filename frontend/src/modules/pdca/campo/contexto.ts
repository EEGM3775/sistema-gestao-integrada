import { createContext, useContext } from 'react'

export interface ContextoDoCampo {
  /** O nome escolhido pela pessoa, quando o do cadastro não é o que o quadro
   *  usa. Vazio significa "use o do cadastro", e é o caso normal. */
  como: string
  /** O nome contra o qual o servidor **de fato** procurou.
   *
   *  Vem da resposta, e não do cadastro que a tela conhece: o navegador só sabe
   *  o `username`, e quem casa o trabalho é o nome completo. Mostrar o que a
   *  tela acha produziria a pior confusão possível — a pessoa lendo um nome e o
   *  sistema procurando outro. */
  nomeDoServidor: string
  definirNomeDoServidor: (nome: string) => void
  trocarNome: () => void
}

export const ContextoDeCampo = createContext<ContextoDoCampo | null>(null)

export function useCampo(): ContextoDoCampo {
  const contexto = useContext(ContextoDeCampo)
  if (!contexto) throw new Error('useCampo fora da CascaDeCampo')
  return contexto
}
