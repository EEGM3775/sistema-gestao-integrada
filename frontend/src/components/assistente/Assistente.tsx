import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ChevronLeft, ChevronRight, HelpCircle, Keyboard, Lightbulb, X } from 'lucide-react'
import {
  AssistenteCtx, guardarPreferencia, lerPreferencia, useAssistente,
  type AjudaDaTela, type ContextoDoAssistente,
} from './contexto'

/** O provider do assistente — estado, preferência e a tecla `?`. */
export function AssistenteProvider({ children }: { children: ReactNode }) {
  const [ativo, setAtivo] = useState(lerPreferencia)
  const [ajuda, setAjuda] = useState<AjudaDaTela | null>(null)
  const [painelAberto, setPainelAberto] = useState(false)

  const alternar = useCallback(() => {
    setAtivo(atual => {
      const proximo = !atual
      guardarPreferencia(proximo)
      return proximo
    })
  }, [])

  const publicar = useCallback((nova: AjudaDaTela | null) => setAjuda(nova), [])
  const abrirPainel = useCallback(() => setPainelAberto(true), [])
  const fecharPainel = useCallback(() => setPainelAberto(false), [])

  // A tecla `?` abre a referência de onde quer que se esteja — menos dentro de
  // um campo de texto, onde `?` é só um caractere que a pessoa está digitando.
  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key !== '?' || e.ctrlKey || e.metaKey || e.altKey) return
      const alvo = e.target as HTMLElement | null
      if (alvo && (/^(INPUT|TEXTAREA|SELECT)$/.test(alvo.tagName) || alvo.isContentEditable)) return
      e.preventDefault()
      setPainelAberto(a => !a)
    }
    document.addEventListener('keydown', aoTeclar)
    return () => document.removeEventListener('keydown', aoTeclar)
  }, [])

  const valor = useMemo<ContextoDoAssistente>(
    () => ({ ativo, alternar, ajuda, publicar, painelAberto, abrirPainel, fecharPainel }),
    [ativo, alternar, ajuda, publicar, painelAberto, abrirPainel, fecharPainel],
  )

  return <AssistenteCtx.Provider value={valor}>{children}</AssistenteCtx.Provider>
}

/** O cartão do assistente e o painel de referência (`?`).
 *
 *  Os dois lados do mesmo problema: o cartão **ensina sem ser pedido** (é o que
 *  o dono pediu ao citar o assistente do Office — aparece, ajuda, e se desliga
 *  quando incomoda), e o painel **responde quando é pedido**, com a lista
 *  inteira de gestos e atalhos da tela aberta.
 *
 *  O cartão nunca é modal e nunca rouba o foco: quem está digitando quantidade
 *  não pode ser interrompido por uma caixa que pede clique. Ele fica no canto,
 *  mostra uma dica por vez com setas para percorrer, e some inteiro no botão da
 *  barra de cima.
 */
export default function Assistente() {
  const { ativo, ajuda, painelAberto, abrirPainel, alternar } = useAssistente()
  const [indice, setIndice] = useState(0)
  const [recolhido, setRecolhido] = useState(false)

  // Trocar de tela recomeça as dicas: a terceira dica da tela anterior não diz
  // nada sobre esta.
  useEffect(() => { setIndice(0); setRecolhido(false) }, [ajuda?.tela])

  const dicas = ajuda?.dicas ?? []
  const mostrarCartao = ativo && dicas.length > 0 && !painelAberto

  return (
    <>
      {mostrarCartao && (
        <aside
          // `aria-live` educado: o leitor de tela anuncia a dica quando ela
          // muda, sem cortar o que a pessoa está fazendo.
          aria-live="polite"
          style={{
            position: 'fixed', right: 18, zIndex: 70,
            // **Acima da faixa de baixo**, e não colado nela. O rodapé da tela é
            // território das barras da própria página — totais, seleção em lote,
            // aviso — e o cartão pousado em `bottom: 18` cobria os botões delas.
            // Quem descobriu foi o roteiro de navegador, tentando clicar em
            // "Limpar seleção" e batendo no assistente: ajuda que tapa o comando
            // que ela está ensinando a usar é pior que ajuda nenhuma.
            bottom: 96,
            width: recolhido ? undefined : 320,
            maxWidth: 'calc(100vw - 36px)',
            background: 'var(--surface)', border: '1px solid var(--line)',
            borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-lg)',
            overflow: 'hidden',
          }}
        >
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px',
            background: 'var(--accent-soft)', borderBottom: recolhido ? 'none' : '1px solid var(--line)',
          }}>
            <Lightbulb size={14} style={{ color: 'var(--accent-ink)', flex: 'none' }} />
            <span style={{
              fontSize: 11, fontWeight: 700, letterSpacing: '0.06em',
              textTransform: 'uppercase', color: 'var(--accent-ink)', flex: 1,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {recolhido ? 'Assistente' : ajuda?.tela}
            </span>
            <button
              onClick={() => setRecolhido(r => !r)}
              title={recolhido ? 'Mostrar a dica' : 'Encolher'}
              aria-label={recolhido ? 'Mostrar a dica' : 'Encolher o assistente'}
              style={botaoDaBarra}
            >{recolhido ? <ChevronLeft size={13} /> : <ChevronRight size={13} />}</button>
            <button
              onClick={alternar}
              // Desligar daqui **desliga de vez** (a chave é a mesma da barra de
              // cima), e o texto diz isso: um X que só fecha desta vez faria a
              // pessoa fechar o mesmo cartão todo dia.
              title="Desligar o assistente — dá para religar na barra de cima"
              aria-label="Desligar o assistente"
              style={botaoDaBarra}
            ><X size={13} /></button>
          </div>

          {!recolhido && (
            <div style={{ padding: '11px 12px 9px' }}>
              <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5, color: 'var(--ink-2)' }}>
                {dicas[Math.min(indice, dicas.length - 1)]}
              </p>

              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 11 }}>
                {dicas.length > 1 && (
                  <>
                    <button
                      onClick={() => setIndice(i => (i - 1 + dicas.length) % dicas.length)}
                      title="Dica anterior"
                      aria-label="Dica anterior"
                      style={botaoPequeno}
                    ><ChevronLeft size={13} /></button>
                    <span style={{ fontSize: 11, color: 'var(--ink-3)', minWidth: 34, textAlign: 'center' }}>
                      {Math.min(indice, dicas.length - 1) + 1}/{dicas.length}
                    </span>
                    <button
                      onClick={() => setIndice(i => (i + 1) % dicas.length)}
                      title="Próxima dica"
                      aria-label="Próxima dica"
                      style={botaoPequeno}
                    ><ChevronRight size={13} /></button>
                  </>
                )}
                <div style={{ flex: 1 }} />
                <button
                  onClick={abrirPainel}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5, border: 'none',
                    background: 'none', cursor: 'pointer', padding: 0,
                    color: 'var(--net-ink)', fontSize: 11.5, fontWeight: 650,
                  }}
                ><Keyboard size={12} />ver tudo</button>
              </div>
            </div>
          )}
        </aside>
      )}

      {painelAberto && <PainelDeAjuda />}
    </>
  )
}

/** A referência inteira da tela — o que a tecla `?` abre. */
function PainelDeAjuda() {
  const { ajuda, fecharPainel } = useAssistente()

  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => { if (e.key === 'Escape') fecharPainel() }
    document.addEventListener('keydown', aoTeclar)
    return () => document.removeEventListener('keydown', aoTeclar)
  }, [fecharPainel])

  return (
    <div
      onClick={fecharPainel}
      style={{
        position: 'fixed', inset: 0, zIndex: 95, background: 'rgba(15,18,24,0.42)',
        display: 'grid', placeItems: 'center', padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-label="Ajuda desta tela"
        style={{
          width: 'min(760px, 100%)', maxHeight: '86vh', display: 'flex', flexDirection: 'column',
          background: 'var(--surface)', border: '1px solid var(--line)',
          borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-lg)', overflow: 'hidden',
        }}
      >
        <div style={{
          display: 'flex', alignItems: 'center', gap: 9, padding: '12px 16px',
          borderBottom: '1px solid var(--line)', flex: 'none',
        }}>
          <HelpCircle size={16} style={{ color: 'var(--accent-ink)' }} />
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)', flex: 1 }}>
            {ajuda ? `O que dá para fazer — ${ajuda.tela}` : 'Ajuda'}
          </span>
          <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
            abre e fecha com <b>?</b>
          </span>
          <button onClick={fecharPainel} aria-label="Fechar" style={botaoDaBarra}><X size={15} /></button>
        </div>

        <div style={{ overflowY: 'auto', padding: '4px 0 12px' }}>
          {!ajuda || ajuda.grupos.length === 0 ? (
            <p style={{ padding: '22px 16px', margin: 0, fontSize: 13, color: 'var(--ink-3)' }}>
              Esta tela ainda não publicou a ajuda dela. O assistente aparece nas telas que
              publicaram — por enquanto, a planilha do Orçamento.
            </p>
          ) : ajuda.grupos.map(grupo => (
            <section key={grupo.titulo} style={{ padding: '12px 16px 4px' }}>
              <h3 style={{
                margin: '0 0 8px', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.07em',
                textTransform: 'uppercase', color: 'var(--ink-3)',
              }}>{grupo.titulo}</h3>
              <div style={{ display: 'grid', gap: 1 }}>
                {grupo.itens.map(item => (
                  <div
                    key={`${grupo.titulo}-${item.gesto}-${item.faz}`}
                    style={{
                      display: 'flex', alignItems: 'baseline', gap: 12, padding: '5px 0',
                      borderBottom: '1px solid var(--line-2)', fontSize: 12.5,
                    }}
                  >
                    <kbd style={{
                      flex: 'none', minWidth: 132, fontFamily: 'var(--mono)', fontSize: 11.5,
                      color: 'var(--ink)', background: 'var(--inset)', borderRadius: 4,
                      padding: '2px 7px', border: '1px solid var(--line)',
                    }}>{item.gesto}</kbd>
                    <span style={{ color: 'var(--ink-2)', lineHeight: 1.45 }}>{item.faz}</span>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}

const botaoDaBarra: React.CSSProperties = {
  border: 'none', background: 'none', cursor: 'pointer', color: 'var(--ink-3)',
  padding: 2, display: 'flex', flex: 'none', borderRadius: 4,
}

const botaoPequeno: React.CSSProperties = {
  ...botaoDaBarra, border: '1px solid var(--line)', padding: '2px 5px',
}
