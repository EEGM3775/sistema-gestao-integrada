import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * A cor da disciplina **saiu daqui na PRA.9b** — mora em
 * `backend/moduloprancheta/disciplinas.py`, e viaja pronta em `disciplina_cor`.
 *
 * Era um dicionário fixo neste arquivo, e funcionou enquanto as disciplinas eram
 * 13 fechadas no código. No instante em que o cliente pôde criar a sua, a tela
 * teria de inventar cor para o que não conhece — duas fontes para o mesmo
 * atributo, divergindo na primeira disciplina nova: uma cor no filtro, outra no
 * cartão. Agora o servidor responde a cor de todas, inclusive a derivada de quem
 * não escolheu, e a tela só pinta.
 *
 * Fica registrado aqui porque a tentação de "só um mapinha local" volta.
 */

/**
 * Ditado para a busca — o `SpeechRecognition` do navegador.
 *
 * **É acessibilidade, não enfeite.** O encarregado que não escreve
 * "hidrossanitário" consegue dizê-lo, e essa é a diferença entre achar a prancha e
 * desistir dela. Roda no Chrome do Android, que é o aparelho do canteiro; onde não
 * há suporte o botão **não aparece** — botão que não funciona é pior que botão
 * ausente, ainda mais para quem não vai ler a explicação.
 *
 * O reconhecimento para sozinho no fim da fala (`continuous: false`): manter o
 * microfone aberto no canteiro captaria a britadeira e gastaria bateria, e o gesto
 * que se quer é uma palavra, não uma conversa.
 */
interface EventoDeFala {
  results: ArrayLike<ArrayLike<{ transcript: string }>>
}
interface Reconhecedor {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  onresult: ((e: EventoDeFala) => void) | null
  onend: (() => void) | null
  onerror: ((e: { error?: string }) => void) | null
}
type FabricaDeReconhecedor = new () => Reconhecedor

function fabrica(): FabricaDeReconhecedor | null {
  if (typeof window === 'undefined') return null
  const janela = window as unknown as {
    SpeechRecognition?: FabricaDeReconhecedor
    webkitSpeechRecognition?: FabricaDeReconhecedor
  }
  return janela.SpeechRecognition ?? janela.webkitSpeechRecognition ?? null
}

export function useDitado(aoOuvir: (texto: string) => void, aoAvisar: (m: string) => void) {
  const [suportado] = useState(() => fabrica() !== null)
  const [ouvindo, setOuvindo] = useState(false)
  const reconhecedor = useRef<Reconhecedor | null>(null)

  // O callback vive numa ref porque o reconhecedor é criado uma vez e os
  // handlers ficariam presos ao primeiro `aoOuvir` — a busca receberia sempre o
  // `setBusca` do primeiro render, que ainda funciona, mas o `aoAvisar` não.
  const ouvir = useRef(aoOuvir)
  const avisar = useRef(aoAvisar)
  ouvir.current = aoOuvir
  avisar.current = aoAvisar

  useEffect(() => {
    const Fabrica = fabrica()
    if (!Fabrica) return
    const r = new Fabrica()
    r.lang = 'pt-BR'
    r.continuous = false
    r.interimResults = false
    r.onresult = (e) => {
      const texto = e.results?.[0]?.[0]?.transcript ?? ''
      if (texto) ouvir.current(texto.trim())
    }
    r.onend = () => setOuvindo(false)
    r.onerror = (e) => {
      setOuvindo(false)
      // `not-allowed` é a permissão do microfone negada — a única que a pessoa
      // resolve, e por isso a única com frase própria. As outras (rede, sem fala
      // captada) somem sozinhas na tentativa seguinte.
      if (e?.error === 'not-allowed') {
        avisar.current('Para buscar falando, libere o microfone para este site.')
      }
    }
    reconhecedor.current = r
    return () => { try { r.stop() } catch { /* já parado */ } }
  }, [])

  const alternar = useCallback(() => {
    const r = reconhecedor.current
    if (!r) return
    if (ouvindo) {
      r.stop()
      setOuvindo(false)
      return
    }
    try {
      r.start()
      setOuvindo(true)
    } catch {
      // `start()` numa sessão já ativa levanta — o estado local basta para
      // reconciliar, sem mostrar erro a quem só tocou duas vezes.
      setOuvindo(false)
    }
  }, [ouvindo])

  return { suportado, ouvindo, alternar }
}
