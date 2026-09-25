import { createContext, useContext, useEffect } from 'react'

/** O contrato do assistente da plataforma — o que se liga e desliga na barra
 *  de cima.
 *
 *  **Por que ele existe.** A grade do Orçamento ganhou seleção múltipla,
 *  arrastar, Alt+setas, Ctrl+Z, menu de contexto e um painel de banco — e nada
 *  disso se anunciava. O dono do sistema perguntou para que servia o botão de
 *  três pontos no fim da linha; se ele não sabia, ninguém saberia. Poder sem
 *  pista de que existe não é recurso, é dívida.
 *
 *  **Por que ligado e desligado, e não sempre.** Dica permanente vira ruído
 *  para quem já aprendeu, e o orçamentista passa o dia nesta tela. A régua é a
 *  do velho assistente do Office, que o dono citou pelo nome: aparece quando se
 *  quer, some quando não se quer, e a chave mora onde se vê — ao lado da
 *  Prancheta e do Calendário, que são as outras lentes que acompanham a pessoa
 *  por todo o sistema.
 *
 *  **Como uma tela participa.** Ela publica o que sabe com `useAjudaDaTela`:
 *  `dicas` (as poucas frases que o cartão mostra) e `grupos` (a referência
 *  inteira, que o painel do `?` abre). Tela que não publica nada simplesmente
 *  não tem assistente, e o painel diz isso em vez de abrir vazio.
 *
 *  Arquivo sem JSX de propósito: o provider é componente e mora em
 *  `Assistente.tsx`. Misturar componente e hook no mesmo arquivo quebra o
 *  *fast refresh* do Vite — a regra `react-refresh/only-export-components`.
 */

export interface Atalho {
  /** Como se faz: `Ctrl+Z`, `Alt+→`, `clique com Shift`, `botão direito`. */
  gesto: string
  /** O que acontece. */
  faz: string
}

export interface GrupoDeAtalhos {
  titulo: string
  itens: Atalho[]
}

export interface AjudaDaTela {
  /** O nome da tela, para o painel dizer de onde a ajuda é. */
  tela: string
  /** As frases curtas que o cartão mostra, na ordem de importância. */
  dicas: string[]
  /** A referência completa, agrupada, que o `?` abre. */
  grupos: GrupoDeAtalhos[]
}

export interface ContextoDoAssistente {
  /** O assistente está ligado? Vive no navegador de quem usa. */
  ativo: boolean
  alternar: () => void
  /** A ajuda publicada pela tela aberta agora — `null` quando não há. */
  ajuda: AjudaDaTela | null
  publicar: (ajuda: AjudaDaTela | null) => void
  /** O painel do `?` está aberto? */
  painelAberto: boolean
  abrirPainel: () => void
  fecharPainel: () => void
}

export const AssistenteCtx = createContext<ContextoDoAssistente | null>(null)

export const CHAVE_DO_ASSISTENTE = 'sgi.assistente.ativo'

/** Nasce **ligado**: quem nunca viu a tela é exatamente quem precisa da dica, e
 *  desligar é um clique. O contrário — nascer desligado — deixaria o recurso
 *  invisível pelo mesmo motivo que ele existe para corrigir.
 *
 *  O `try` não é zelo exagerado: em janela anônima ou com dados de site
 *  bloqueados o acesso **lança**, e uma exceção aqui derrubaria o shell inteiro
 *  por causa de uma preferência. Sem memória, o assistente funciona igual — só
 *  não lembra da escolha entre sessões. */
export function lerPreferencia(): boolean {
  try {
    const guardado = localStorage.getItem(CHAVE_DO_ASSISTENTE)
    return guardado === null ? true : guardado === '1'
  } catch {
    return true
  }
}

export function guardarPreferencia(ativo: boolean): void {
  try {
    localStorage.setItem(CHAVE_DO_ASSISTENTE, ativo ? '1' : '0')
  } catch {
    // Sem memória, tudo bem: a escolha vale por esta sessão.
  }
}

export function useAssistente(): ContextoDoAssistente {
  const ctx = useContext(AssistenteCtx)
  if (!ctx) {
    throw new Error('useAssistente precisa estar dentro do <AssistenteProvider>.')
  }
  return ctx
}

/** A tela publica a sua ajuda enquanto estiver montada, e a retira ao sair.
 *
 *  `ajuda` tem de ser **estável** — constante de módulo ou `useMemo` no
 *  chamador. Recriada a cada render, a publicação entraria em laço. */
export function useAjudaDaTela(ajuda: AjudaDaTela | null): void {
  const { publicar } = useAssistente()
  useEffect(() => {
    publicar(ajuda)
    return () => publicar(null)
  }, [ajuda, publicar])
}
