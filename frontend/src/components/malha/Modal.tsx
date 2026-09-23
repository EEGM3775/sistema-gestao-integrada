import { useEffect, useId } from 'react'
import type { ReactNode } from 'react'

interface ModalProps {
  titulo: ReactNode
  onClose: () => void
  children: ReactNode
  rodape?: ReactNode
  largura?: number
  /**
   * O diálogo ocupa a altura da janela e **entrega a sobra ao conteúdo**.
   *
   * Existe para o diálogo cujo miolo é uma lista longa — a conferência de
   * arquivos é o caso que o motivou. No modo normal o cartão cresce com o
   * conteúdo e quem rola é o fundo; aí cabeçalho, contadores e filtros empurram
   * a lista para fora da tela e sobra **uma fileira** para a coisa mais
   * importante do diálogo, que é justamente a lista.
   *
   * Com `alto`, o cartão vira coluna flex de altura fixa: cabeçalho e rodapé
   * ficam presos, o miolo recebe `flex: 1` e **quem rola é a lista**. O filho
   * precisa colaborar — ser uma coluna flex com `minHeight: 0` na parte que
   * rola —, e por isso isto é uma opção e não o padrão.
   */
  alto?: boolean
}

/**
 * Diálogo da Malha. Promovido junto do {@link Btn} para o IE.0c.
 *
 * Fecha no `Esc` e no clique fora — os dois gestos que o usuário tenta antes de
 * procurar o "X". `onMouseDown` (e não `onClick`) no fundo porque arrastar uma
 * seleção de dentro para fora terminaria o clique no backdrop e fecharia o
 * diálogo no meio de uma cópia de texto.
 */
export function Modal({
  titulo, onClose, children, rodape, largura = 520, alto = false,
}: ModalProps) {
  //: **O diálogo se anuncia como diálogo.** Sem `role`/`aria-modal`, um leitor
  //: de tela lê o cartão como mais um trecho da página: quem não enxerga não
  //: sabe que o resto ficou inerte, e o `Esc` não tem significado anunciado.
  //: O `aria-labelledby` aponta para o próprio cabeçalho, que é o título que a
  //: pessoa vidente lê — um `aria-label` paralelo seria um segundo nome, que
  //: envelhece separado do primeiro.
  const idDoTitulo = useId()

  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  }, [onClose])

  return (
    <div
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 92, background: 'rgba(6,14,26,.5)',
        backdropFilter: 'blur(3px)', display: 'flex', justifyContent: 'center',
        // No modo alto o cartão já cabe na janela, então o fundo não pode rolar:
        // se rolasse, a roda teria dois donos possíveis sobre a mesma área.
        ...(alto
          ? { alignItems: 'center', padding: '3vh 16px', overflow: 'hidden' }
          : { alignItems: 'flex-start', padding: '7vh 16px', overflowY: 'auto' }),
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={idDoTitulo}
        style={{
        width: '100%', maxWidth: largura, background: 'var(--surface)',
        border: '1px solid var(--line)', borderRadius: 'var(--r-lg)',
        boxShadow: 'var(--shadow-lg)',
        // **`minWidth: 0` é o que faz o `maxWidth` acima valer.** O cartão é
        // filho de um flex container, e filho de flex tem `min-width: auto` —
        // ou seja, ele não encolhe abaixo do conteúdo. Um `<select>` com uma
        // opção longa (o cabeçalho de uma planilha, no de-para da importação)
        // empurrava o cartão para além dos 620px declarados e o diálogo saía
        // pela lateral da tela, sem barra de rolagem para voltar.
        minWidth: 0,
        // `minHeight: 0` na coluna flex é o que permite ao miolo encolher abaixo
        // do tamanho natural do conteúdo — sem ele o `flex: 1` do filho não
        // limita nada e a lista volta a empurrar o rodapé para fora.
        ...(alto
          ? { height: '94vh', display: 'flex', flexDirection: 'column', minHeight: 0 }
          : null),
      }}>
        <div id={idDoTitulo} style={{
          padding: '14px 19px', borderBottom: '1px solid var(--line)',
          fontFamily: 'var(--display)', fontSize: 15.5, fontWeight: 700, color: 'var(--ink)',
          // Nome de arquivo não tem espaço para quebrar em: sem `anywhere`, um
          // `Relatorio_de_precos_consolidado_2026_revisao_final.xlsx` estica o
          // cabeçalho e leva o diálogo junto.
          overflowWrap: 'anywhere',
          ...(alto ? { flex: 'none' } : null),
        }}>{titulo}</div>
        <div style={{
          padding: 19, minWidth: 0,
          ...(alto ? { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' } : null),
        }}>{children}</div>
        {rodape && (
          <div style={{
            display: 'flex', justifyContent: 'flex-end', gap: 9, flexWrap: 'wrap',
            padding: '13px 19px', borderTop: '1px solid var(--line)',
            ...(alto ? { flex: 'none' } : null),
          }}>{rodape}</div>
        )}
      </div>
    </div>
  )
}
