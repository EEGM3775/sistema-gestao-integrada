import { Btn, Card, Pill } from '@/components/malha'
import { useOcorrencias } from '../hooks'
import { dataHora } from '../formato'
import { TOM_DO_STATUS_DA_OCORRENCIA } from '../vocabulario'

const ROTULO = { aberta: 'Aberta', em_investigacao: 'Em investigação', encerrada: 'Encerrada', cancelada: 'Cancelada' } as const

/** O que aconteceu por último na obra, na porta do posto: a fila mostra o que
 *  pede decisão, mas a ocorrência já tratada também precisa estar à vista. */
export function OcorrenciasRecentes({
  obraId, aoAbrir, aoVerTodas, limite = 5,
}: {
  obraId: number
  aoAbrir: (id: number) => void
  aoVerTodas: () => void
  limite?: number
}) {
  const consulta = useOcorrencias(obraId)
  if (consulta.isLoading || consulta.isError) return null
  const lista = [...(consulta.data ?? [])]
    .sort((a, b) => (b.ocorrido_em ?? '').localeCompare(a.ocorrido_em ?? ''))
    .slice(0, limite)

  return (
    <Card pad={false} style={{ overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px' }}>
        <strong style={{ fontSize: 13, color: 'var(--ink-2)', flex: 1 }}>Ocorrências recentes</strong>
        <Btn onClick={aoVerTodas}>Ver todas</Btn>
      </div>
      {lista.length === 0 ? (
        <div style={{ padding: '12px 14px 16px', fontSize: 13, color: 'var(--ink-3)', borderTop: '1px solid var(--line-2)' }}>
          Nenhuma ocorrência registrada nesta obra.
        </div>
      ) : lista.map((o) => (
        <button
          key={o.ocorrencia_id}
          type="button"
          onClick={() => aoAbrir(o.ocorrencia_id)}
          style={{
            display: 'block', width: '100%', padding: '10px 14px', border: 'none',
            borderTop: '1px solid var(--line-2)', background: 'transparent',
            cursor: 'pointer', textAlign: 'left', color: 'inherit', font: 'inherit',
          }}
        >
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            <Pill kind={o.exige_cat ? 'danger' : 'slate'}>{o.tipo_rotulo.split(' (')[0]}</Pill>
            <Pill kind={TOM_DO_STATUS_DA_OCORRENCIA[o.status]}>{ROTULO[o.status]}</Pill>
            {o.exige_cat && !o.cat_emitida_em && <Pill kind="danger">CAT pendente</Pill>}
          </div>
          <div style={{ fontSize: 13, color: 'var(--ink)', marginTop: 5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {o.descricao}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
            {dataHora(o.ocorrido_em)}{o.local_rotulo && ` · ${o.local_rotulo}`}
          </div>
        </button>
      ))}
    </Card>
  )
}
