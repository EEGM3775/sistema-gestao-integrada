import { useCallback, useRef, useState } from 'react'

/** A pilha de desfazer da planilha — ORC.10d.
 *
 *  **Por que é do cliente, e não do servidor.** Um log de operações no banco
 *  daria desfazer entre sessões, mas custaria uma tabela nova, um verbo de
 *  compensação por operação e a pergunta de quem pode desfazer o que — e o
 *  gesto que se quer é o do Excel: `Ctrl+Z` logo depois do engano, na mesma
 *  tela, por quem errou. A pilha vive enquanto a planilha está aberta, que é
 *  exatamente a janela em que alguém se lembra do que fez.
 *
 *  **Como cada operação vira reversível.** Quem empilha declara o par: o que
 *  refazer e o que desfazer, ambos como funções que já capturaram o estado
 *  necessário. Edição de célula guarda o valor anterior; mover guarda o pai e a
 *  posição de origem; duplicar desfaz excluindo as cópias; e exclusão só é
 *  reversível porque o servidor devolve o material para recriar as linhas
 *  (`excluir-lote` → `restaurar`). O preço disso é que os **ids mudam** ao
 *  desfazer uma exclusão — o banco não reaproveita chave primária, e fingir
 *  que reaproveita seria mentir para quem tivesse guardado o id antigo.
 *
 *  **O que não entra.** Localizar-e-substituir sobre a planilha inteira e a
 *  reprecificação ficam de fora de propósito: a primeira pode tocar mil linhas
 *  (a pilha guardaria mil valores para um gesto), e a segunda já tem o seu
 *  próprio desfazer, com lote, histórico e trilha — dois mecanismos de desfazer
 *  sobre a mesma coisa é a receita para um deles estar errado.
 */
export interface Passo {
  /** O que aparece no aviso: "desfeito: mover 3 linhas". */
  rotulo: string
  desfazer: () => Promise<void>
  refazer: () => Promise<void>
}

/** Quantos passos a pilha guarda.
 *
 *  **O número é do dono**, e mora em `payment/planos.py`
 *  (`ORCAMENTO_TETO_PASSOS_DESFAZER`): ele diz até onde o cliente volta atrás,
 *  que é a definição de teto na régua do projeto. Está espelhado aqui porque o
 *  frontend não importa Python e a API ainda não serve este valor — a mesma
 *  costura que o modal de inserir item faz com o `PAGINA_MAXIMA`. Mudar de lado
 *  exige mudar dos dois. */
const TETO = 50

export function useHistorico() {
  // `useRef` para as pilhas e `useState` só para os contadores: o componente
  // precisa re-renderizar quando o botão muda de habilitado para desabilitado,
  // mas guardar as funções em estado faria cada `push` clonar dois arrays.
  const desfazerPilha = useRef<Passo[]>([])
  const refazerPilha = useRef<Passo[]>([])
  const [versao, setVersao] = useState(0)
  const [ocupado, setOcupado] = useState(false)

  const sincronizar = useCallback(() => setVersao(v => v + 1), [])

  const registrar = useCallback((passo: Passo) => {
    desfazerPilha.current = [...desfazerPilha.current.slice(-(TETO - 1)), passo]
    // Fazer algo novo depois de desfazer corta o futuro — é o contrato de
    // qualquer editor, e manter a pilha de refazer aqui levaria a refazer por
    // cima de um estado que não é mais o que ela esperava.
    refazerPilha.current = []
    sincronizar()
  }, [sincronizar])

  const executar = useCallback(async (
    de: React.RefObject<Passo[]>, para: React.RefObject<Passo[]>, metodo: 'desfazer' | 'refazer',
  ) => {
    const passo = de.current[de.current.length - 1]
    if (!passo) return null
    setOcupado(true)
    try {
      await passo[metodo]()
      de.current = de.current.slice(0, -1)
      para.current = [...para.current, passo]
      sincronizar()
      return passo.rotulo
    } catch {
      // Falhou: o passo **fica** na pilha. Tirá-lo daria a impressão de que o
      // desfazer aconteceu, e a próxima tentativa pularia a operação errada.
      return null
    } finally {
      setOcupado(false)
    }
  }, [sincronizar])

  const desfazer = useCallback(
    () => executar(desfazerPilha, refazerPilha, 'desfazer'), [executar],
  )
  const refazer = useCallback(
    () => executar(refazerPilha, desfazerPilha, 'refazer'), [executar],
  )

  const limpar = useCallback(() => {
    desfazerPilha.current = []
    refazerPilha.current = []
    sincronizar()
  }, [sincronizar])

  return {
    registrar,
    desfazer,
    refazer,
    limpar,
    ocupado,
    // `versao` entra na dependência de quem lê estes dois para o botão
    // reavaliar — as pilhas são refs e não disparam render sozinhas.
    podeDesfazer: desfazerPilha.current.length > 0 && versao >= 0,
    podeRefazer: refazerPilha.current.length > 0 && versao >= 0,
    proximoDesfazer: desfazerPilha.current[desfazerPilha.current.length - 1]?.rotulo,
    proximoRefazer: refazerPilha.current[refazerPilha.current.length - 1]?.rotulo,
  }
}
