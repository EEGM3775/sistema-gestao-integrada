import { useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { BotaoExportar, Btn, Card, Empty, Loading, Pill } from '@/components/malha'
import { contemSemAcento } from '@/utils/texto'
import { emDias } from '../formato'
import { useNcs } from '../hooks'
import { entrada } from '../estilos'
import { Escolhas } from './Formulario'
import { TOM_DA_GRAVIDADE, TOM_DO_STATUS_DA_NC } from '../vocabulario'

type Recorte = 'abertas' | 'encerrada' | 'cancelada' | 'todas'

const RECORTES: { valor: Recorte; rotulo: string }[] = [
  { valor: 'abertas', rotulo: 'Em aberto' },
  { valor: 'encerrada', rotulo: 'Encerradas' },
  { valor: 'cancelada', rotulo: 'Canceladas' },
  { valor: 'todas', rotulo: 'Todas' },
]

/** Todos os defeitos da obra. A fila mostra o que está **parado**; esta lista
 *  mostra o que **existe** — é por ela que se acha o defeito de ontem que já
 *  tem plano e por isso saiu da fila. */
export function ListaDeNcs({
  obraId, aoAbrir, aoRegistrar,
}: {
  obraId: number
  aoAbrir: (id: number) => void
  aoRegistrar?: () => void
}) {
  const [recorte, setRecorte] = useState<Recorte>('abertas')
  const [termo, setTermo] = useState('')
  const status = recorte === 'abertas' || recorte === 'todas' ? '' : recorte
  const consulta = useNcs(obraId, status)

  const visiveis = useMemo(() => {
    const todas = consulta.data ?? []
    return todas
      .filter((nc) => recorte !== 'abertas' || nc.status === 'aberta' || nc.status === 'em_tratamento')
      .filter((nc) => !termo.trim() || contemSemAcento(
        `${nc.descricao} ${nc.local_rotulo ?? ''} ${nc.atividade_nome ?? ''} ${nc.aberta_por}`, termo,
      ))
  }, [consulta.data, recorte, termo])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <Escolhas valor={recorte} aoEscolher={setRecorte} opcoes={RECORTES} />
        <div style={{ position: 'relative', flex: '1 1 220px', maxWidth: 340 }}>
          <Search size={14} style={{ position: 'absolute', left: 9, top: 10, color: 'var(--ink-3)' }} />
          <input
            value={termo}
            onChange={(e) => setTermo(e.target.value)}
            placeholder="Procurar pelo defeito, local ou serviço"
            aria-label="Procurar defeito"
            style={{ ...entrada, paddingLeft: 28 }}
          />
        </div>
        <span style={{ flex: 1 }} />
        <BotaoExportar tam="md" recurso="pdca.nc" recorte={{ obra: obraId }} />
        {aoRegistrar && <Btn variant="primary" onClick={aoRegistrar}>Registrar defeito</Btn>}
      </div>

      {consulta.isLoading ? (
        <Loading o="os defeitos da obra" />
      ) : visiveis.length === 0 ? (
        <Empty>
          {termo.trim()
            ? 'Nenhum defeito com esse texto neste recorte.'
            : recorte === 'abertas'
              ? 'Nenhum defeito em aberto nesta obra.'
              : 'Nenhum defeito neste recorte.'}
        </Empty>
      ) : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          {visiveis.map((nc) => {
            const dias = Math.floor((Date.now() - new Date(nc.aberta_em).getTime()) / 86_400_000)
            const aberta = nc.status === 'aberta' || nc.status === 'em_tratamento'
            return (
              <button
                key={nc.nc_id}
                type="button"
                onClick={() => aoAbrir(nc.nc_id)}
                style={{
                  display: 'flex', alignItems: 'flex-start', gap: 12, width: '100%',
                  padding: '11px 14px', borderTop: '1px solid var(--line-2)',
                  background: 'transparent', border: 'none', borderTopStyle: 'solid',
                  cursor: 'pointer', textAlign: 'left', color: 'inherit', font: 'inherit',
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    <Pill kind={TOM_DA_GRAVIDADE[nc.gravidade]}>
                      {nc.gravidade_rotulo.split(' — ')[0]}
                    </Pill>
                    <Pill kind={TOM_DO_STATUS_DA_NC[nc.status]}>{nc.status_rotulo}</Pill>
                  </div>
                  <div
                    style={{
                      fontSize: 13, color: 'var(--ink)', marginTop: 5, lineHeight: 1.4,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}
                  >
                    {nc.descricao}
                  </div>
                  <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
                    {[nc.local_rotulo, nc.atividade_nome].filter(Boolean).join(' · ') || 'sem local'}
                    {aberta && nc.estado.falta && <> · falta {nc.estado.falta}</>}
                  </div>
                </div>
                <span style={{ fontSize: 11.5, color: 'var(--ink-3)', flexShrink: 0 }}>
                  {dias <= 0 ? 'hoje' : `há ${emDias(dias)}`}
                </span>
              </button>
            )
          })}
        </Card>
      )}
    </div>
  )
}
