import { useMemo, useState } from 'react'
import {
  Calculator, CalendarClock, Download, Layers, Plane, Route as RouteIcon, ShieldAlert, Timer,
} from 'lucide-react'
import { Btn, Card, Empty, KpiTile, Loading, Mapa, Num, Pill, SectionHead } from '@/components/malha'
import type { CamadaGeoJSON, CamadaRaster } from '@/components/malha'
import { exportarPlano, tilesDaOrtofoto } from '../api'
import {
  useCalcularPlano, useCamadas, useFeicoes, useOrtofotos, useOtimizarRota, usePlanos, useRotas,
} from '../hooks'
import type { MemoriaDoVoo, ViolacaoDeJanela } from '../types'
import type { Say } from './operacao'

const selectEstilo: React.CSSProperties = {
  padding: '7px 11px', borderRadius: 8, border: '1px solid var(--line)',
  background: 'var(--surface)', color: 'var(--ink)', fontSize: 13,
}
const dataBR = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString('pt-BR')

/* ═══════════ Camadas & feições — o antes/depois ═══════════ */
export function Camadas() {
  const { data: camadas, isLoading } = useCamadas()
  const [ate, setAte] = useState('')
  const { data: feicoes } = useFeicoes(ate ? { ate, page_size: 500 } : { page_size: 500 })

  const geo: CamadaGeoJSON[] = useMemo(() => {
    const linhas = feicoes?.results ?? []
    return linhas.map((f) => ({
      id: `feicao-${f.feicao_id}`,
      data: f.geom,
      cor: f.camada_cor,
    }))
  }, [feicoes])

  const pontos = useMemo(
    () => (feicoes?.results ?? [])
      .filter((f) => f.geom.type === 'Point')
      .map((f) => {
        const [lon, lat] = (f.geom as GeoJSON.Point).coordinates
        return { id: f.feicao_id, lon, lat, nome: f.nome, detalhe: `${f.camada_nome} · ${dataBR(f.data_referencia)}` }
      }),
    [feicoes],
  )

  if (isLoading) return <Loading o="as camadas" />

  return (
    <>
      <Card style={{ marginBottom: 16 }}>
        <SectionHead
          sub="A data de referência é o que permite o antes/depois: o mapa de uma data mostra o que existia naquela data."
          right={
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--ink-2)' }}>
              <CalendarClock size={15} style={{ color: 'var(--ink-3)' }} />
              até
              <input type="date" value={ate} onChange={(e) => setAte(e.target.value)} style={selectEstilo} />
            </label>
          }
        >
          Camadas do território
        </SectionHead>

        {(camadas?.results ?? []).length === 0 ? (
          <Empty>Nenhuma camada criada. Camadas agrupam feições por assunto: progresso de obra, sondagens, interferências, marcos.</Empty>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {(camadas?.results ?? []).map((c) => (
              <span key={c.camada_id}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 11px', borderRadius: 999, border: '1px solid var(--line)', background: 'var(--surface-2)', fontSize: 13 }}>
                <span style={{ width: 9, height: 9, borderRadius: 3, background: c.cor, flex: 'none' }} />
                <span style={{ color: 'var(--ink)' }}>{c.nome}</span>
                <Num size={12} tone="var(--ink-3)">{c.total_feicoes ?? 0}</Num>
              </span>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <SectionHead right={<Pill kind="slate">{`${feicoes?.count ?? 0} feições`}</Pill>}>Feições no mapa</SectionHead>
        {pontos.length === 0 && geo.length === 0
          ? <Empty>Nada desenhado neste recorte.</Empty>
          : <Mapa pontos={pontos} camadas={geo} altura={460} />}
      </Card>
    </>
  )
}

/* ═══════════ Acervo de ortofotos ═══════════ */
export function Acervo({ say }: { say: Say }) {
  const { data, isLoading } = useOrtofotos()
  const [ativa, setAtiva] = useState<number | null>(null)

  if (isLoading) return <Loading o="o acervo de ortofotos" />
  const linhas = data?.results ?? []

  const escolhida = linhas.find((o) => o.ortofoto_id === ativa)
  const rasters: CamadaRaster[] = escolhida
    ? [{ id: `orto-${escolhida.ortofoto_id}`, tiles: [tilesDaOrtofoto(escolhida.ortofoto_id)] }]
    : []
  const camadas: CamadaGeoJSON[] = escolhida
    ? [{ id: `bbox-${escolhida.ortofoto_id}`, data: escolhida.bbox, cor: '#E79A22', preenchimento: false }]
    : linhas.map((o) => ({ id: `bbox-${o.ortofoto_id}`, data: o.bbox, cor: '#8892A6', preenchimento: false }))

  return (
    <>
      <Card style={{ marginBottom: 16 }}>
        <SectionHead sub="O pixel continua no drone. Aqui ficam o envelope e a data — é o que responde “o que voamos nesta área, e quando?”.">
          Acervo de voos
        </SectionHead>
        {linhas.length === 0 ? (
          <Empty>Nenhuma ortofoto indexada. O índice nasce quando um voo processado é registrado com o envelope (bbox) e a data.</Empty>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {linhas.map((o) => {
              const vencida = o.dias_desde_voo > 90
              return (
                <div key={o.ortofoto_id}
                  onClick={() => setAtiva(ativa === o.ortofoto_id ? null : o.ortofoto_id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 11, padding: '10px 12px', borderRadius: 9,
                    cursor: 'pointer', border: '1px solid var(--line)',
                    background: ativa === o.ortofoto_id ? 'var(--accent-soft)' : 'var(--surface-2)',
                  }}>
                  <Layers size={15} style={{ color: 'var(--ink-3)', flex: 'none' }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13.5, color: 'var(--ink)' }}>{o.titulo}</div>
                    <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                      {dataBR(o.data_voo)}{o.obra_nome ? ` · ${o.obra_nome}` : ''}
                      {o.gsd_cm ? ` · ${o.gsd_cm} cm/px` : ''}
                    </div>
                  </div>
                  <Pill kind={vencida ? 'danger' : 'good'}>
                    {vencida ? `${o.dias_desde_voo} dias` : 'recente'}
                  </Pill>
                  {!o.url_cog && <Pill kind="slate">sem COG</Pill>}
                </div>
              )
            })}
          </div>
        )}
      </Card>

      {linhas.length > 0 && (
        <Card>
          <SectionHead
            sub={escolhida ? 'Tile servido pelo backend, com entitlement — o COG do drone não é exposto direto.' : 'Selecione um voo para sobrepor a imagem.'}
            right={escolhida ? <Btn onClick={() => { setAtiva(null); say('Sobreposição removida') }}>Remover</Btn> : undefined}
          >
            {escolhida ? escolhida.titulo : 'Envelopes do acervo'}
          </SectionHead>
          <Mapa camadas={camadas} rasters={rasters} altura={440} satelite />
        </Card>
      )}
    </>
  )
}

/* ═══════════ Planos de voo ═══════════ */
export function Voos({ say }: { say: Say }) {
  const { data, isLoading } = usePlanos()
  const calcular = useCalcularPlano()
  const [memoria, setMemoria] = useState<Record<number, MemoriaDoVoo>>({})

  if (isLoading) return <Loading o="os planos de voo" />
  const linhas = data?.results ?? []
  if (!linhas.length) {
    return (
      <Empty>
        Nenhum plano de voo. Um plano nasce da área da obra + o GSD desejado — a altura
        é calculada pela geometria da câmera, nunca digitada solta.
      </Empty>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {linhas.map((plano) => {
        const mem = memoria[plano.plano_id]
        const semAutorizacao = !plano.autorizacao_protocolo
        return (
          <Card key={plano.plano_id}>
            <SectionHead
              sub={`${plano.tipo_rotulo} · GSD alvo ${plano.gsd_alvo_cm} cm/px · ${plano.camera_nome}`}
              right={
                <div style={{ display: 'flex', gap: 7, alignItems: 'center' }}>
                  {semAutorizacao && (
                    <Pill kind="danger"><ShieldAlert size={12} /> sem autorização</Pill>
                  )}
                  <Btn variant="primary" tam="sm"
                    onClick={() => calcular.mutate(plano.plano_id, {
                      onSuccess: (r) => {
                        setMemoria((m) => ({ ...m, [plano.plano_id]: r.memoria }))
                        say(`Altura ${r.memoria.altura_m} m · ${r.memoria.waypoints} waypoints`)
                      },
                      onError: () => say('Área pequena demais para o espaçamento — aumente o GSD alvo.'),
                    })}>
                    <Calculator size={13} /> Calcular
                  </Btn>
                </div>
              }
            >
              {plano.nome}
            </SectionHead>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 12, marginBottom: 14 }}>
              <KpiTile label="Altura de voo" valor={plano.altura_m ? <Num>{`${plano.altura_m} m`}</Num> : null}
                pendente={!plano.altura_m} base={`GSD ${plano.gsd_alvo_cm} cm/px`} />
              <KpiTile label="Distância" valor={plano.distancia_m ? <Num>{`${(Number(plano.distancia_m) / 1000).toFixed(2)} km`}</Num> : null}
                pendente={!plano.distancia_m} base="linhas de voo" />
              <KpiTile label="Duração estimada" valor={plano.duracao_min ? <Num>{`${plano.duracao_min} min`}</Num> : null}
                pendente={!plano.duracao_min} base="+25% de folga" />
              <KpiTile label="Fotos" valor={plano.fotos_estimadas != null ? <Num>{plano.fotos_estimadas}</Num> : null}
                pendente={plano.fotos_estimadas == null}
                base={`sobrep. ${plano.sobreposicao_frontal_pct}/${plano.sobreposicao_lateral_pct}%`} />
            </div>

            {mem && (
              <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginBottom: 12, padding: '9px 12px', borderRadius: 8, background: 'var(--surface-2)', border: '1px solid var(--line)' }}>
                <b style={{ color: 'var(--ink-2)' }}>Memória de cálculo:</b> altura {mem.altura_m} m ·
                espaçamento entre faixas {mem.espacamento_m} m · foto a cada {mem.intervalo_foto_m} m ·
                {' '}{mem.waypoints} waypoints
              </div>
            )}

            <Mapa
              camadas={[
                { id: `area-${plano.plano_id}`, data: plano.area, cor: '#1D9AA6' },
                ...(plano.linha ? [{ id: `linha-${plano.plano_id}`, data: plano.linha, cor: '#E79A22', largura: 2 }] : []),
              ]}
              altura={330}
              satelite
            />

            {plano.waypoints?.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12, alignItems: 'center' }}>
                <span style={{ fontSize: 12, color: 'var(--ink-3)', marginRight: 4 }}>
                  <Download size={13} style={{ verticalAlign: -2 }} /> Levar para o campo:
                </span>
                {([['kml', 'KML'], ['plan', 'MAVLink .plan'], ['litchi', 'Litchi CSV'], ['wpml', 'DJI WPML']] as const)
                  .map(([formato, rotulo]) => (
                    <Btn key={formato} tam="sm"
                      onClick={() => exportarPlano(plano.plano_id, formato, plano.nome).then(() => say(`${rotulo} baixado`))}>
                      {rotulo}
                    </Btn>
                  ))}
              </div>
            )}
          </Card>
        )
      })}
    </div>
  )
}

/* ═══════════ Rotas de entrega ═══════════ */
export function Rotas({ say }: { say: Say }) {
  const { data, isLoading } = useRotas()
  const otimizar = useOtimizarRota()
  const [violacoes, setViolacoes] = useState<Record<number, ViolacaoDeJanela[]>>({})

  if (isLoading) return <Loading o="as rotas" />
  const linhas = data?.results ?? []
  if (!linhas.length) {
    return (
      <Empty>
        Nenhuma rota planejada. Uma rota sai de um almoxarifado e passa pelos canteiros —
        a ordem é calculada por tempo de viagem, e as janelas de horário são conferidas.
      </Empty>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {linhas.map((rota) => {
        const furos = violacoes[rota.rota_id] ?? []
        return (
          <Card key={rota.rota_id}>
            <SectionHead
              sub={`Sai de ${rota.origem_nome} · ${rota.paradas.length} paradas`}
              right={
                <div style={{ display: 'flex', gap: 7, alignItems: 'center' }}>
                  {rota.procedencia && (
                    <Pill kind={rota.procedencia === 'osrm' ? 'good' : 'slate'}>{rota.procedencia_rotulo}</Pill>
                  )}
                  <Btn variant="primary" tam="sm"
                    onClick={() => otimizar.mutate(rota.rota_id, {
                      onSuccess: (r) => {
                        setViolacoes((v) => ({ ...v, [rota.rota_id]: r.violacoes_de_janela }))
                        say(r.violacoes_de_janela.length
                          ? `Ordem otimizada — ${r.violacoes_de_janela.length} janela(s) em conflito`
                          : 'Ordem otimizada')
                      },
                      onError: () => say('Alguma parada está sem coordenada — geocodifique antes.'),
                    })}>
                    <RouteIcon size={13} /> Otimizar
                  </Btn>
                </div>
              }
            >
              {rota.nome}
            </SectionHead>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 12, marginBottom: 14 }}>
              <KpiTile label="Distância" valor={rota.distancia_km != null ? <Num>{`${rota.distancia_km} km`}</Num> : null}
                pendente={rota.distancia_km == null} base={rota.procedencia_rotulo || 'não traçada'} />
              <KpiTile label="Duração" valor={rota.duracao_s ? <Num>{`${Math.round(rota.duracao_s / 60)} min`}</Num> : null}
                pendente={!rota.duracao_s} base="tempo de viagem" />
              <KpiTile label="Paradas" valor={<Num>{rota.paradas.length}</Num>} base="na ordem atual" />
            </div>

            {furos.length > 0 && (
              <div style={{ marginBottom: 12, padding: '10px 12px', borderRadius: 9, background: 'var(--danger-soft)', border: '1px solid var(--danger-soft)' }}>
                <b style={{ fontSize: 12.5, color: 'var(--danger-ink)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Timer size={14} /> A ordem mais curta fura janelas de entrega
                </b>
                {furos.map((v) => (
                  <div key={v.parada} style={{ fontSize: 12.5, color: 'var(--danger-ink)', marginTop: 4 }}>
                    Chega às {v.chegada.slice(0, 5)} — {v.motivo}
                  </div>
                ))}
              </div>
            )}

            <Mapa
              pontos={rota.paradas
                .filter((p) => p.local_ponto)
                .map((p) => ({
                  id: p.parada_id, lon: p.local_ponto!.lon, lat: p.local_ponto!.lat,
                  nome: `${p.ordem}. ${p.local_nome}`,
                  detalhe: p.chegada_estimada_s != null ? `chegada ~${Math.round(p.chegada_estimada_s / 60)} min` : undefined,
                }))}
              camadas={rota.linha ? [{ id: `rota-${rota.rota_id}`, data: rota.linha, cor: '#3E9C6E', largura: 3 }] : []}
              altura={330}
            />
          </Card>
        )
      })}
    </div>
  )
}

/** Cartão do módulo não contratado — cadeado com teaser, no padrão do farol. */
export function TerritorioBloqueado() {
  return (
    <Card style={{ textAlign: 'center', padding: 40 }}>
      <Plane size={30} style={{ color: 'var(--ink-3)', marginBottom: 12 }} />
      <h3 style={{ fontFamily: 'var(--display)', fontSize: 18, fontWeight: 700, color: 'var(--ink)', marginBottom: 8 }}>
        Território é do módulo Maps
      </h3>
      <p style={{ fontSize: 13.5, color: 'var(--ink-3)', maxWidth: 520, margin: '0 auto' }}>
        Georreferenciar obra, fornecedor e almoxarifado continua incluso — é cadastro.
        Acervo de ortofotos, plano de voo, roteirização e cercas de canteiro têm custo
        próprio (storage raster, motor de rota) e vêm com o módulo <b>Maps</b>.
      </p>
    </Card>
  )
}
