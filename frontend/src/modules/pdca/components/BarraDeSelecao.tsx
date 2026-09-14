import { useState } from 'react'
import { ArrowLeftToLine, ArrowRightToLine, Link2, Timer, Trash2, X } from 'lucide-react'
import { Btn } from '@/components/malha'
import type { Atividade } from '../types'

/**
 * O que se faz com **muitas** linhas de uma vez.
 *
 * Quem monta cronograma seleciona um bloco e age sobre ele — indenta os doze
 * serviços de um pavimento, liga a sequência inteira em cadeia, dá a mesma
 * duração a todas as fôrmas. Sem isso, a seleção múltipla só serve para pintar
 * linhas de outra cor, que é o que ela fazia até aqui.
 *
 * A barra aparece só com **duas ou mais** selecionadas: com uma, os mesmos
 * gestos já estão no menu da linha e no teclado, e uma barra flutuante em cima
 * do plano seria ruído permanente.
 */
export default function BarraDeSelecao({
  selecionadas, editavel, onIndentar, onPromover, onLigarEmCadeia, onDuracao, onExcluir, onLimpar,
}: {
  selecionadas: Atividade[]
  editavel: boolean
  onIndentar: () => void
  onPromover: () => void
  onLigarEmCadeia: () => void
  onDuracao: (dias: number) => void
  onExcluir: () => void
  onLimpar: () => void
}) {
  const [duracao, setDuracao] = useState('')
  if (selecionadas.length < 2) return null

  const folhas = selecionadas.filter(a => !a.tem_filhos && !a.eh_marco)

  return (
    <div style={{
      position: 'sticky', bottom: 12, zIndex: 5, alignSelf: 'center',
      display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
      background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 999,
      boxShadow: 'var(--shadow-md)', padding: '7px 8px 7px 16px', marginTop: -44,
    }}>
      <strong style={{ fontSize: 12.5 }}>{selecionadas.length} selecionadas</strong>

      {editavel && (
        <>
          <Btn tam="sm" onClick={onIndentar} title="Indentar todas (Alt+→)">
            <ArrowRightToLine size={14} /> Indentar
          </Btn>
          <Btn tam="sm" onClick={onPromover} title="Promover todas (Alt+←)">
            <ArrowLeftToLine size={14} /> Promover
          </Btn>
          <Btn
            tam="sm" onClick={onLigarEmCadeia} disabled={folhas.length < 2}
            title={folhas.length < 2
              ? 'A cadeia liga folhas — sintéticas e marcos ficam de fora'
              : 'Ligar em cadeia: cada uma termina, a seguinte começa (' + folhas.length + ' folhas)'}
          >
            <Link2 size={14} /> Ligar em cadeia
          </Btn>

          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <Timer size={14} style={{ color: 'var(--ink-3)' }} />
            <input
              type="number" min={1} value={duracao} placeholder="dias"
              onChange={e => setDuracao(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && Number(duracao) >= 1) {
                  onDuracao(Number(duracao))
                  setDuracao('')
                }
              }}
              style={{
                width: 62, fontSize: 12.5, padding: '4px 7px', borderRadius: 7,
                border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink)',
              }}
              title={'Aplicar a mesma duração às ' + folhas.length + ' folhas selecionadas (Enter)'}
            />
          </span>

          <Btn tam="sm" variant="perigo" onClick={onExcluir} title="Excluir as selecionadas">
            <Trash2 size={14} /> Excluir
          </Btn>
        </>
      )}

      <button
        onClick={onLimpar} aria-label="Limpar a seleção"
        style={{ border: 'none', background: 'none', color: 'var(--ink-3)', cursor: 'pointer', display: 'flex', padding: 4 }}
      >
        <X size={15} />
      </button>
    </div>
  )
}
