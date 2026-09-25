import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * **Grava sozinho, e diz que gravou.**
 *
 * Existe por um defeito de verdade: a tela da medição tinha "Salvar grade" e
 * "Submeter" como dois botões independentes, e submeter mandava só o id. Quem
 * digitasse 200 linhas e clicasse direto em Submeter via o documento ser
 * aprovado **com os números antigos** — sem erro, sem aviso, e com um título a
 * pagar no fim. Não havia nem estado de "não salvo" na tela.
 *
 * O desenho é o de qualquer editor moderno, e os três detalhes que importam:
 *
 * 1. **Debounce, não a cada tecla.** Quem opera planilha digita em rajada; uma
 *    chamada por tecla entregaria 200 requisições e um servidor lento passaria
 *    a comer dígitos.
 * 2. **A assinatura nasce do que veio do servidor.** Sem isso, a montagem do
 *    componente contaria como mudança e toda abertura de documento gravaria —
 *    reescrevendo `origem` de linhas que ninguém tocou.
 * 3. **`salvarAgora` para o gesto que não pode esperar.** Submeter, sair da
 *    página, trocar de aba: o atraso é conveniência, e nenhuma conveniência
 *    pode ficar entre o gestor e o que ele acabou de digitar.
 */
export type EstadoDoSalvamento = 'limpo' | 'pendente' | 'salvando' | 'salvo' | 'erro'

interface Opcoes<T> {
  /** O que salvar. Comparado por `assinatura`, não por identidade. */
  valor: T
  /** A forma estável do valor — duas chamadas com a mesma string não gravam. */
  assinatura: string
  salvar: (valor: T) => Promise<unknown>
  /** `false` congela tudo: documento congelado, sem permissão, ainda carregando. */
  ativo: boolean
  atrasoMs?: number
}

export interface Autosave {
  estado: EstadoDoSalvamento
  erro: string | null
  /** Grava agora o que estiver pendente. Devolve `true` se o documento está
   *  gravado ao fim da chamada — é o que o botão de submeter espera. */
  salvarAgora: () => Promise<boolean>
  ultimoEm: Date | null
}

export function useAutosave<T>({
  valor, assinatura, salvar, ativo, atrasoMs = 1500,
}: Opcoes<T>): Autosave {
  const [estado, setEstado] = useState<EstadoDoSalvamento>('limpo')
  const [erro, setErro] = useState<string | null>(null)
  const [ultimoEm, setUltimoEm] = useState<Date | null>(null)

  const salvo = useRef<string | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Refs porque o efeito abaixo não pode depender do valor sem reagendar a cada
  // tecla — o que anularia o debounce.
  const atual = useRef({ valor, assinatura, salvar })
  atual.current = { valor, assinatura, salvar }

  const gravar = useCallback(async (): Promise<boolean> => {
    const { valor: v, assinatura: a, salvar: f } = atual.current
    if (salvo.current === a) return true
    setEstado('salvando')
    setErro(null)
    try {
      await f(v)
      salvo.current = a
      setUltimoEm(new Date())
      // Só volta a "salvo" se nada novo foi digitado enquanto a chamada corria —
      // senão a tela diria "salvo" com uma tecla ainda pendente.
      setEstado(atual.current.assinatura === a ? 'salvo' : 'pendente')
      return atual.current.assinatura === a
    } catch (e) {
      setEstado('erro')
      setErro(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || 'Não deu para gravar. A digitação continua aqui — tente de novo.',
      )
      return false
    }
  }, [])

  useEffect(() => {
    if (!ativo) return
    // A primeira assinatura é a do servidor: ela é o marco zero, não uma edição.
    if (salvo.current === null) { salvo.current = assinatura; return }
    if (salvo.current === assinatura) return

    setEstado('pendente')
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => { void gravar() }, atrasoMs)
    return () => { if (timer.current) clearTimeout(timer.current) }
  }, [assinatura, ativo, atrasoMs, gravar])

  /** O documento trocou (outra medição, ou recarregou do servidor): o marco
   *  zero muda junto, senão a próxima digitação compararia contra o anterior. */
  const trocou = useRef(ativo)
  useEffect(() => {
    if (trocou.current !== ativo) {
      trocou.current = ativo
      salvo.current = ativo ? assinatura : null
      setEstado('limpo')
    }
  }, [ativo, assinatura])

  // Aviso do navegador ao fechar a aba com gravação pendente. É a última rede:
  // o `beforeunload` não consegue esperar uma requisição, mas consegue impedir
  // que a pessoa saia sem saber.
  useEffect(() => {
    if (estado !== 'pendente' && estado !== 'erro') return
    const avisar = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', avisar)
    return () => window.removeEventListener('beforeunload', avisar)
  }, [estado])

  const salvarAgora = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current)
    return gravar()
  }, [gravar])

  return { estado, erro, salvarAgora, ultimoEm }
}

/** O selo que a tela mostra. Texto curto, e **sempre** presente: uma tela que
 *  só avisa quando falha deixa a pessoa sem saber se o silêncio é bom. */
export function rotuloDoSalvamento(a: Autosave): string {
  switch (a.estado) {
    case 'salvando': return 'salvando…'
    case 'pendente': return 'não salvo'
    case 'erro': return a.erro ?? 'falhou'
    case 'salvo':
      return a.ultimoEm
        ? `salvo às ${a.ultimoEm.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`
        : 'salvo'
    default: return 'sem alterações'
  }
}
