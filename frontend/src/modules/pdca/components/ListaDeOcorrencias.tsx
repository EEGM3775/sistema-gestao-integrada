import { useMemo, useState } from 'react'
import { Btn, Card, Empty, Loading, Pill } from '@/components/malha'
import { contemSemAcento } from '@/utils/texto'
import { useOcorrencias } from '../hooks'
import { entrada } from '../estilos'
import { Escolhas } from './Formulario'
import { dataHora } from '../formato'
import { TOM_DO_STATUS_DA_OCORRENCIA } from '../vocabulario'

type Recorte = 'abertas' | 'encerradas' | 'todas'

/** Todas as ocorrências da obra — do quase-acidente ao acidente. A fila
 *  mostra o que pede decisão; esta lista mostra o que aconteceu. */
export function ListaDeOcorrencias({
  obraId, aoAbrir, aoRegistrar,
}: {
  obraId: number
  aoAbrir: (id: number) => void
  aoRegistrar?: () => void
}) {
  const consulta = useOcorrencias(obraId)
  const [recorte, setRecorte] = useState<Recorte>('abertas')
  const [termo, setTermo] = useState('')

  const visiveis = useMemo(() => (consulta.data ?? [])
    .filter((o) => recorte === 'todas'
      || (recorte === 'abertas'
        ? o.status === 'aberta' || o.status === 'em_investigacao'
        : o.status === 'encerrada' || o.status === 'cancelada'))
    .filter((o) => !termo.trim() || contemSemAcento(`${o.descricao} ${o.local_rotulo ?? ''} ${o.tipo_rotulo}`, termo)),
  [consulta.data, recorte, termo])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <Escolhas
          valor={recorte} aoEscolher={setRecorte}
          opcoes={[
            { valor: 'abertas', rotulo: 'Em aberto' },
            { valor: 'encerradas', rotulo: 'Encerradas' },
            { valor: 'todas', rotulo: 'Todas' },
          ]}
        />
        <input
          value={termo} onChange={(e) => setTermo(e.target.value)}
          placeholder="Procurar pelo que aconteceu ou onde"
          aria-label="Procurar ocorrência"
          style={{ ...entrada, maxWidth: 320 }}
        />
        <span style={{ flex: 1 }} />
        {aoRegistrar && <Btn variant="primary" onClick={aoRegistrar}>Registrar ocorrência</Btn>}
      </div>

      {consulta.isLoading ? (
        <Loading o="as ocorrências da obra" />
      ) : visiveis.length === 0 ? (
        <Empty>
          {termo.trim() ? 'Nenhuma ocorrência com esse texto.' : recorte === 'abertas'
            ? 'Nenhuma ocorrência em aberto nesta obra.'
            : 'Nenhuma ocorrência neste recorte.'}
        </Empty>
      ) : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          {visiveis.map((o) => (
            <button
              key={o.ocorrencia_id}
              type="button"
              onClick={() => aoAbrir(o.ocorrencia_id)}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 12, width: '100%',
                padding: '11px 14px', borderTop: '1px solid var(--line-2)',
                background: 'transparent', border: 'none', borderTopStyle: 'solid',
                cursor: 'pointer', textAlign: 'left', color: 'inherit', font: 'inherit',
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Pill kind={o.exige_cat ? 'danger' : 'slate'}>{o.tipo_rotulo.split(' (')[0]}</Pill>
                  <Pill kind={TOM_DO_STATUS_DA_OCORRENCIA[o.status]}>
                    {o.status === 'em_investigacao' ? 'Em investigação' : o.status === 'aberta' ? 'Aberta' : o.status === 'encerrada' ? 'Encerrada' : 'Cancelada'}
                  </Pill>
                  {o.classificacao === 'pendente' && <Pill kind="accent">sem classificação</Pill>}
                  {o.exige_cat && !o.cat_emitida_em && <Pill kind="danger">CAT pendente</Pill>}
                  {o.restricao && <Pill kind="slate">frente interditada</Pill>}
                </div>
                <div style={{ fontSize: 13, color: 'var(--ink)', marginTop: 5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {o.descricao}
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
                  {dataHora(o.ocorrido_em)}{o.local_rotulo && ` · ${o.local_rotulo}`}
                </div>
              </div>
            </button>
          ))}
        </Card>
      )}
    </div>
  )
}
