import { Loading } from '@/components/malha'
import { usePdca } from '../contexto'
import { useHoje } from '../hooks'
import { FilaDeDecisao } from '../components/FilaDeDecisao'
import { MudancasRecentes } from '../components/MudancasRecentes'
import { PulsoDaObra } from '../components/PulsoDaObra'

/** **HOJE** — o primeiro minuto do dia.
 *
 *  Três faixas, nesta ordem: o que exige a sua decisão (a fila unificada dos
 *  seis postos), como a obra está indo (quatro leituras clicáveis) e o que
 *  mudou desde que você saiu.
 *
 *  **Uma chamada só.** O servidor monta as três juntas, e é o que impede o
 *  defeito que este posto teria por construção: em chamadas separadas cada
 *  número chegaria com um recorte de período diferente do vizinho, e a fila
 *  seria ordenada no navegador — que não sabe que a comunicação de acidente
 *  tem prazo em lei. */
export default function HojePage() {
  const { obraId, obra } = usePdca()
  const { data, isLoading, isError, error } = useHoje(obraId)

  if (isLoading) return <Loading o="o dia desta obra" />

  if (isError || !data) {
    return (
      <div style={{ padding: '24px 26px', maxWidth: 620 }}>
        <p style={{ fontSize: 14, color: 'var(--ink-2)', lineHeight: 1.6, margin: 0 }}>
          Não foi possível carregar o dia desta obra. Verifique a conexão e tente
          de novo — nada do que estava aqui se perdeu.
        </p>
        {error instanceof Error && (
          <p style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 8 }}>
            {error.message}
          </p>
        )}
      </div>
    )
  }

  return (
    <div
      style={{
        padding: '22px 26px 40px',
        display: 'flex', flexDirection: 'column', gap: 26,
        maxWidth: 1180,
      }}
    >
      <header>
        <h1
          style={{
            margin: 0, fontSize: 20, fontWeight: 700, color: 'var(--ink)',
            letterSpacing: '-0.01em',
          }}
        >
          {obra?.nome_obra ?? data.obra_nome}
        </h1>
        <p style={{ margin: '3px 0 0', fontSize: 12.5, color: 'var(--ink-3)' }}>
          {new Date(`${data.fila.hoje}T12:00:00`).toLocaleDateString('pt-BR', {
            weekday: 'long', day: '2-digit', month: 'long',
          })}
        </p>
      </header>

      <FilaDeDecisao fila={data.fila} obraId={obraId} />
      <PulsoDaObra pulso={data.pulso} obraId={obraId} />
      {data.mudancas && (
        <MudancasRecentes mudancas={data.mudancas} obraId={obraId} />
      )}
    </div>
  )
}
