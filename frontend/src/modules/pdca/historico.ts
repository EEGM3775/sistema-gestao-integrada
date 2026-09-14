import { useCallback, useRef, useState } from 'react'
import type { Comando } from './types'

/**
 * A pilha de desfazer/refazer do planejamento.
 *
 * **Por que ela não é uma cópia do estado.** O padrão fácil — guardar snapshots
 * do plano e restaurar o anterior — não serve aqui: o dono do cronograma é o
 * servidor, que recalcula o CPM a cada gesto e devolve datas que a tela não
 * teria como recompor sozinha. Restaurar um snapshot local mostraria o plano de
 * antes **sem** o backend concordar, e o próximo recálculo desfaria o desfazer.
 *
 * Então a pilha guarda **gestos inversos**, não estados: cada passo sabe a
 * chamada que o aplica e a chamada que o volta. Desfazer é uma escrita como
 * qualquer outra — passa pelas mesmas validações, e o CPM roda de novo.
 *
 * **O que não entra aqui:** publicar e replanejar. Os dois viram compromisso da
 * obra (um congela a versão, o outro abre a seguinte), e "desfazer" um
 * compromisso pelas costas de quem o assumiu seria pior que não ter desfazer. A
 * tela limpa a pilha quando eles acontecem, em vez de fingir que dá para voltar.
 */
export function useHistorico(limite = 60) {
  const [pilha, setPilha] = useState<Comando[]>([])
  const [cursor, setCursor] = useState(0)
  const [ocupado, setOcupado] = useState(false)
  const [erro, setErro] = useState('')
  //: A pilha é lida dentro de callbacks assíncronos; o ref evita a leitura de
  //: um estado velho quando dois gestos chegam quase juntos.
  const atual = useRef({ pilha, cursor })
  atual.current = { pilha, cursor }

  const registrar = useCallback((comando: Comando) => {
    setPilha(anterior => {
      const cortada = anterior.slice(0, atual.current.cursor)
      const nova = [...cortada, comando]
      const excedente = Math.max(nova.length - limite, 0)
      setCursor(nova.length - excedente)
      return excedente ? nova.slice(excedente) : nova
    })
  }, [limite])

  /** Executa e registra. Falhou, **não** entra na pilha: desfazer um gesto que
   *  nunca aconteceu removeria algo que o usuário não fez. */
  const executar = useCallback(async (comando: Comando) => {
    setOcupado(true)
    setErro('')
    try {
      await comando.fazer()
      registrar(comando)
      return true
    } catch (e) {
      setErro(mensagem(e))
      return false
    } finally {
      setOcupado(false)
    }
  }, [registrar])

  const andar = useCallback(async (direcao: -1 | 1) => {
    const { pilha: p, cursor: c } = atual.current
    const indice = direcao === -1 ? c - 1 : c
    const comando = p[indice]
    if (!comando) return
    setOcupado(true)
    setErro('')
    try {
      await (direcao === -1 ? comando.desfazer() : comando.fazer())
      setCursor(c + direcao)
    } catch (e) {
      setErro(mensagem(e))
    } finally {
      setOcupado(false)
    }
  }, [])

  const limpar = useCallback(() => {
    setPilha([])
    setCursor(0)
    setErro('')
  }, [])

  return {
    executar,
    registrar,
    desfazer: () => andar(-1),
    refazer: () => andar(1),
    limpar,
    ocupado,
    erro,
    limparErro: () => setErro(''),
    podeDesfazer: cursor > 0,
    podeRefazer: cursor < pilha.length,
    rotuloDesfazer: cursor > 0 ? pilha[cursor - 1].rotulo : '',
    rotuloRefazer: cursor < pilha.length ? pilha[cursor].rotulo : '',
  }
}

function mensagem(e: unknown): string {
  const resposta = (e as { response?: { data?: unknown } })?.response?.data
  if (typeof resposta === 'string') return resposta
  if (resposta && typeof resposta === 'object') {
    const primeiro = Object.values(resposta as Record<string, unknown>)[0]
    if (Array.isArray(primeiro)) return String(primeiro[0])
    if (typeof primeiro === 'string') return primeiro
  }
  return e instanceof Error ? e.message : 'Não foi possível concluir o passo.'
}
