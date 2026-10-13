import { useMemo, useState } from 'react'
import {
  Calculator, Download, Layers, MapPin, PenLine, Plane, Plus, Route as RouteIcon, Search, ShieldAlert,
  Spline, Timer, Trash2, Undo2, X,
} from 'lucide-react'
import { Btn, Card, Empty, KpiTile, Loading, Mapa, Num, Pill, SectionHead } from '@/components/malha'
import type { CamadaGeoJSON, CamadaRaster, PontoMapa } from '@/components/malha'
import { exportarPlano, tilesDaOrtofoto } from '../api'
import {
  useCalcularPlano, useCriarPlanoDoLocal, useExcluirPlano, useExcluirRota, useLocais, useMapa, useOrtofotos,
  useOtimizarRota, usePlanos, useRotas, useSalvarPlano, useSalvarRota, useStatusMaps, useTracarRota,
} from '../hooks'
import type { MemoriaDoVoo, PlanoVoo, Rota, ViolacaoDeJanela } from '../types'
import { AvisoDeProvedores, FaixaDoMapa, MapaComPainel } from './comum'
import { ROTULO_TIPO, inputEstilo, motivo, type Say } from './util'

const dataBR = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString('pt-BR')
type LonLat = [number, number]

/** Pins de contexto (obras, empreendimentos): é perto deles que se voa e se entrega. */
function useLocaisDeContexto(): PontoMapa[] {
  const { data } = useMapa()
  return useMemo(() => (data?.locais ?? [])
    .filter((l) => l.ponto)
    .map((l) => ({
      id: l.local_id, lon: l.ponto!.lon, lat: l.ponto!.lat, nome: l.nome, tipo: l.tipo,
      precisao: l.precisao, detalhe: l.vinculo_rotulo,
    })), [data])
}

/** Centro do envelope de um polígono — para voar até o plano escolhido. */
function centroDe(area: GeoJSON.Polygon): { lon: number; lat: number } {
  const anel = area.coordinates[0] ?? []
  const lons = anel.map((c) => c[0])
  const lats = anel.map((c) => c[1])
  return { lon: (Math.min(...lons) + Math.max(...lons)) / 2, lat: (Math.min(...lats) + Math.max(...lats)) / 2 }
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
          Acervo de voos realizados
        </SectionHead>
        {linhas.length === 0 ? (
          <Empty>
            Nenhuma ortofoto indexada ainda. O acervo é dos voos JÁ FEITOS e processados no Drone — cada
            ortofoto entra aqui com o envelope e a data. Para planejar um voo novo, use a aba Planos de voo.
          </Empty>
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

/* ═══════════ Planos de voo — ver, desenhar, editar, excluir ═══════════ */

type Edicao = {
  plano_id?: number
  nome: string
  tipo: string
  gsd_alvo_cm: string
  vertices: LonLat[]
}

const TIPOS_DE_VOO: Array<[string, string]> = [
  ['grid', 'Grid (linhas paralelas)'], ['duplo_grid', 'Duplo grid (cruzado)'],
  ['perimetro', 'Perímetro'], ['orbital', 'Orbital / POI'], ['corredor', 'Corredor'],
]

/**
 * **Os voos no mapa, e o mapa como prancheta do voo** (item 69).
 *
 * "Não consigo ver os voos": cada plano tinha o seu mapinha, que nascia
 * enquadrado no Brasil inteiro — o polígono de 150 m existia, mas ficava do
 * tamanho de um pixel. Agora há UM mapa com todos os planos, enquadrado neles,
 * e o plano escolhido mostra as linhas de voo por cima.
 *
 * E o polígono se desenha aqui: clique marca um canto, arrasto ajusta, botão
 * direito remove. É o mesmo gesto para criar e para EDITAR a área de um plano
 * existente; mudar a área apaga o cálculo antigo no backend, e o plano é
 * recalculado na hora — exportar para o drone um voo sobre a área anterior
 * seria pior do que não exportar.
 */
export function Voos({ say }: { say: Say }) {
  const { data, isLoading } = usePlanos()
  const contexto = useLocaisDeContexto()
  const calcular = useCalcularPlano()
  const salvar = useSalvarPlano()
  const excluir = useExcluirPlano()
  const [selecionado, setSelecionado] = useState<number | null>(null)
  const [edicao, setEdicao] = useState<Edicao | null>(null)
  const [deLocal, setDeLocal] = useState(false)
  const [foco, setFoco] = useState<{ lon: number; lat: number; zoom?: number; selo?: number } | null>(null)
  const [memoria, setMemoria] = useState<Record<number, MemoriaDoVoo>>({})
  const [satelite, setSatelite] = useState(true)

  const planos = useMemo(() => data?.results ?? [], [data])
  const escolhido = planos.find((p) => p.plano_id === selecionado) ?? null

  const camadas: CamadaGeoJSON[] = useMemo(() => {
    const saida: CamadaGeoJSON[] = []
    planos.forEach((p) => {
      if (edicao?.plano_id === p.plano_id) return
      saida.push({ id: `area-${p.plano_id}`, data: p.area, cor: p.plano_id === selecionado ? '#E79A22' : '#1D9AA6' })
    })
    if (escolhido?.linha && edicao?.plano_id !== escolhido.plano_id) {
      saida.push({ id: `linha-${escolhido.plano_id}`, data: escolhido.linha, cor: '#F2C14E', largura: 2, preenchimento: false })
    }
    return saida
  }, [planos, selecionado, escolhido, edicao])

  if (isLoading) return <Loading o="os planos de voo" />

  const rodarCalculo = (plano_id: number) =>
    calcular.mutate(plano_id, {
      onSuccess: (r) => {
        setMemoria((m) => ({ ...m, [plano_id]: r.memoria }))
        say(`Calculado: altura ${r.memoria.altura_m} m · ${r.memoria.waypoints} waypoints`)
      },
      onError: (e) => say(motivo(e, 'Área pequena demais para o espaçamento — aumente o GSD alvo.')),
    })

  const salvarEdicao = () => {
    if (!edicao || edicao.vertices.length < 3) return
    const anel = [...edicao.vertices, edicao.vertices[0]]
    salvar.mutate({
      plano_id: edicao.plano_id,
      nome: edicao.nome.trim() || 'Plano de voo',
      tipo: edicao.tipo,
      gsd_alvo_cm: edicao.gsd_alvo_cm,
      area: { type: 'Polygon', coordinates: [anel] },
    }, {
      onSuccess: (plano) => {
        setEdicao(null)
        setSelecionado(plano.plano_id)
        say(edicao.plano_id ? 'Área atualizada — recalculando o voo…' : 'Plano criado — calculando o voo…')
        rodarCalculo(plano.plano_id)
      },
      onError: (e) => say(motivo(e, 'Não deu para salvar o plano.')),
    })
  }

  const editarArea = (p: PlanoVoo) => {
    const anel = p.area.coordinates[0] ?? []
    // O anel GeoJSON repete o primeiro ponto no fim; no desenho, cada vértice é um marcador.
    const vertices = anel.slice(0, anel.length > 1 ? -1 : undefined).map((c) => [c[0], c[1]] as LonLat)
    setEdicao({ plano_id: p.plano_id, nome: p.nome, tipo: p.tipo, gsd_alvo_cm: p.gsd_alvo_cm, vertices })
    setFoco({ ...centroDe(p.area), zoom: 16, selo: Date.now() })
  }

  const mapa = (
    <>
      <Mapa
        pontos={contexto} camadas={camadas} enquadrar="camadas" altura={600} satelite={satelite} foco={foco}
        desenho={edicao ? { vertices: edicao.vertices, aoMudar: (v) => setEdicao({ ...edicao, vertices: v }) } : null}
      />
      {edicao ? (
        <FaixaDoMapa>
          <PenLine size={15} style={{ color: 'var(--accent-ink)' }} />
          <span style={{ flex: 1, minWidth: 200 }}>
            Clique no mapa para marcar os cantos da área · arraste um canto para ajustar · botão direito remove.
            <b> {edicao.vertices.length} {edicao.vertices.length === 1 ? 'canto' : 'cantos'}</b>
            {edicao.vertices.length < 3 && ' (mínimo 3)'}
          </span>
          <Btn tam="sm" title="Desfazer o último canto" disabled={!edicao.vertices.length}
            onClick={() => setEdicao({ ...edicao, vertices: edicao.vertices.slice(0, -1) })}>
            <Undo2 size={13} />
          </Btn>
          <Btn tam="sm" onClick={() => setSatelite((s) => !s)}>{satelite ? 'Mapa' : 'Satélite'}</Btn>
        </FaixaDoMapa>
      ) : (
        <div style={{ position: 'absolute', top: 10, left: 10, zIndex: 2 }}>
          <Btn tam="sm" onClick={() => setSatelite((s) => !s)} style={{ boxShadow: 'var(--shadow-sm)' }}>
            {satelite ? 'Mapa' : 'Satélite'}
          </Btn>
        </div>
      )}
    </>
  )

  const painel = edicao ? (
    <div style={{ padding: 12, display: 'grid', gap: 9, alignContent: 'start', overflowY: 'auto' }}>
      <b style={{ fontFamily: 'var(--display)', fontSize: 14.5, color: 'var(--ink)' }}>
        {edicao.plano_id ? 'Editar área do plano' : 'Novo plano — desenhe a área'}
      </b>
      <label style={{ display: 'grid', gap: 4, fontSize: 12, color: 'var(--ink-3)' }}>
        Nome
        <input value={edicao.nome} onChange={(e) => setEdicao({ ...edicao, nome: e.target.value })}
          placeholder="Ex.: Levantamento do terreno — Aurora" style={inputEstilo} maxLength={180} />
      </label>
      <label style={{ display: 'grid', gap: 4, fontSize: 12, color: 'var(--ink-3)' }}>
        Tipo de voo
        <select value={edicao.tipo} onChange={(e) => setEdicao({ ...edicao, tipo: e.target.value })} style={inputEstilo}>
          {TIPOS_DE_VOO.map(([v, r]) => <option key={v} value={v}>{r}</option>)}
        </select>
      </label>
      <label style={{ display: 'grid', gap: 4, fontSize: 12, color: 'var(--ink-3)' }}>
        GSD alvo (cm/px) — a altura sai daqui, não se digita
        <input type="number" min={0.5} max={20} step={0.1} value={edicao.gsd_alvo_cm}
          onChange={(e) => setEdicao({ ...edicao, gsd_alvo_cm: e.target.value })} style={inputEstilo} />
      </label>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
        <Btn variant="primary" tam="sm" disabled={edicao.vertices.length < 3 || salvar.isPending} onClick={salvarEdicao}>
          {edicao.plano_id ? 'Salvar área e recalcular' : 'Criar e calcular'}
        </Btn>
        <Btn tam="sm" disabled={!edicao.vertices.length} onClick={() => setEdicao({ ...edicao, vertices: [] })}>Limpar</Btn>
        <Btn tam="sm" onClick={() => setEdicao(null)}>Cancelar</Btn>
      </div>
    </div>
  ) : (
    <>
      <div style={{ padding: 10, borderBottom: '1px solid var(--line)', display: 'grid', gap: 7 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <b style={{ fontFamily: 'var(--display)', fontSize: 14.5, color: 'var(--ink)', flex: 1 }}>
            Planos de voo <span style={{ color: 'var(--ink-3)', fontWeight: 600, fontSize: 12.5 }}>{planos.length}</span>
          </b>
          <Btn tam="sm" variant="primary" title="Desenhar a área do voo no mapa"
            onClick={() => { setDeLocal(false); setSelecionado(null); setEdicao({ nome: '', tipo: 'grid', gsd_alvo_cm: '2', vertices: [] }) }}>
            <PenLine size={13} /> Desenhar
          </Btn>
          <Btn tam="sm" title="Criar a partir de um local cadastrado" onClick={() => setDeLocal((v) => !v)}>
            <MapPin size={13} /> De um local
          </Btn>
        </div>
        {deLocal && <NovoPlanoDoLocal say={say} aoCriar={(p) => { setDeLocal(false); setSelecionado(p.plano_id); setFoco({ ...centroDe(p.area), zoom: 16, selo: Date.now() }) }} />}
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {planos.length === 0 ? (
          <div style={{ padding: 16 }}>
            <Empty>
              Nenhum plano de voo ainda. Clique em <b>Desenhar</b> e marque os cantos da área no mapa —
              a altura sai do GSD desejado e da câmera, nunca digitada solta.
            </Empty>
          </div>
        ) : planos.map((p) => (
          <CartaoDoPlano key={p.plano_id} plano={p} aberto={p.plano_id === selecionado} memoria={memoria[p.plano_id]}
            aoAbrir={() => { setSelecionado(p.plano_id); setFoco({ ...centroDe(p.area), zoom: 16, selo: Date.now() }) }}
            aoCalcular={() => rodarCalculo(p.plano_id)}
            calculando={calcular.isPending}
            aoEditar={() => editarArea(p)}
            aoExcluir={() => {
              if (!window.confirm(`Excluir o plano "${p.nome}"? Isto não pode ser desfeito.`)) return
              excluir.mutate(p.plano_id, {
                onSuccess: () => { say(`Plano "${p.nome}" excluído.`); if (selecionado === p.plano_id) setSelecionado(null) },
                onError: (e) => say(motivo(e, 'Não deu para excluir o plano.')),
              })
            }}
            say={say}
          />
        ))}
      </div>
    </>
  )

  return <MapaComPainel mapa={mapa} painel={painel} />
}

function CartaoDoPlano({ plano, aberto, memoria, aoAbrir, aoCalcular, calculando, aoEditar, aoExcluir, say }: {
  plano: PlanoVoo; aberto: boolean; memoria?: MemoriaDoVoo
  aoAbrir: () => void; aoCalcular: () => void; calculando: boolean; aoEditar: () => void; aoExcluir: () => void
  say: Say
}) {
  const semAutorizacao = !plano.autorizacao_protocolo
  return (
    <div style={{ borderBottom: '1px solid var(--line-2)', background: aberto ? 'var(--surface-2)' : 'transparent' }}>
      <button type="button" onClick={aoAbrir}
        style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%', padding: '10px 11px', textAlign: 'left', font: 'inherit', background: 'none', border: 'none', cursor: 'pointer' }}>
        <Plane size={15} style={{ color: aberto ? 'var(--accent-ink)' : 'var(--ink-3)', flex: 'none' }} />
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: 'block', fontSize: 13.5, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{plano.nome}</span>
          <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)' }}>
            {plano.tipo_rotulo} · GSD {plano.gsd_alvo_cm} cm/px{plano.obra_nome ? ` · ${plano.obra_nome}` : ''}
          </span>
        </span>
        {plano.calculado_em ? <Pill kind="good">calculado</Pill> : <Pill kind="slate">a calcular</Pill>}
      </button>

      {aberto && (
        <div style={{ padding: '0 11px 12px', display: 'grid', gap: 9 }}>
          {semAutorizacao && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--danger-ink)' }}>
              <ShieldAlert size={13} /> Sem protocolo de autorização (DECEA/SARPAS) registrado.
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <KpiTile label="Altura" valor={plano.altura_m ? <Num>{`${plano.altura_m} m`}</Num> : null} pendente={!plano.altura_m} base="do GSD" />
            <KpiTile label="Distância" valor={plano.distancia_m ? <Num>{`${(Number(plano.distancia_m) / 1000).toFixed(2)} km`}</Num> : null} pendente={!plano.distancia_m} base="linhas de voo" />
            <KpiTile label="Duração" valor={plano.duracao_min ? <Num>{`${plano.duracao_min} min`}</Num> : null} pendente={!plano.duracao_min} base="+25% de folga" />
            <KpiTile label="Fotos" valor={plano.fotos_estimadas != null ? <Num>{plano.fotos_estimadas}</Num> : null} pendente={plano.fotos_estimadas == null} base={`sobrep. ${plano.sobreposicao_frontal_pct}/${plano.sobreposicao_lateral_pct}%`} />
          </div>
          {memoria && (
            <div style={{ fontSize: 12, color: 'var(--ink-3)', padding: '8px 10px', borderRadius: 8, background: 'var(--surface)', border: '1px solid var(--line)' }}>
              <b style={{ color: 'var(--ink-2)' }}>Memória de cálculo:</b> altura {memoria.altura_m} m ·
              faixas a cada {memoria.espacamento_m} m · foto a cada {memoria.intervalo_foto_m} m · {memoria.waypoints} waypoints
            </div>
          )}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            <Btn variant="primary" tam="sm" disabled={calculando} onClick={aoCalcular}><Calculator size={13} /> Calcular</Btn>
            <Btn tam="sm" onClick={aoEditar}><PenLine size={13} /> Editar área</Btn>
            <Btn tam="sm" onClick={aoExcluir} title="Excluir este plano"><Trash2 size={13} /> Excluir</Btn>
          </div>
          {plano.waypoints?.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
              <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}><Download size={12} style={{ verticalAlign: -2 }} /> Levar para o campo:</span>
              {([['kml', 'KML'], ['plan', '.plan'], ['litchi', 'Litchi'], ['wpml', 'DJI WPML']] as const).map(([formato, rotulo]) => (
                <Btn key={formato} tam="sm"
                  onClick={() => exportarPlano(plano.plano_id, formato, plano.nome)
                    .then(() => say(`${rotulo} baixado`))
                    .catch((e) => say(motivo(e, 'Não deu para exportar.')))}>
                  {rotulo}
                </Btn>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * O plano a partir de um local já cadastrado — perímetro desenhado se houver,
 * círculo de raio se não. A resposta diz qual dos dois valeu, porque voar
 * sobre um círculo em volta do pin não é voar sobre o canteiro. Para a área
 * exata, há o desenho.
 */
function NovoPlanoDoLocal({ say, aoCriar }: { say: Say; aoCriar: (p: PlanoVoo) => void }) {
  const { data: locais } = useLocais({ page_size: 200 })
  const criar = useCriarPlanoDoLocal()
  const [local, setLocal] = useState<number | null>(null)
  const [raio, setRaio] = useState(150)

  const comCoordenada = (locais?.results ?? []).filter((l) => l.ponto)
  const escolhido = comCoordenada.find((l) => l.local_id === local)
  const temPerimetro = !!escolhido?.area

  if (comCoordenada.length === 0) {
    return <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Nenhum local com coordenada — posicione o pin no Mapa da empresa, ou desenhe a área.</span>
  }
  return (
    <div style={{ display: 'grid', gap: 7, padding: 9, borderRadius: 8, background: 'var(--surface-2)' }}>
      <select value={local ?? ''} onChange={(e) => setLocal(Number(e.target.value) || null)} style={inputEstilo}>
        <option value="">Onde voar…</option>
        {comCoordenada.map((l) => (
          <option key={l.local_id} value={l.local_id}>{l.nome}{l.area ? ' (tem perímetro)' : ''}</option>
        ))}
      </select>
      {local != null && !temPerimetro && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 12.5, color: 'var(--ink-2)' }}>
          raio
          <input type="range" min={50} max={1000} step={25} value={raio} onChange={(e) => setRaio(Number(e.target.value))} style={{ flex: 1 }} />
          <Num size={12.5}>{`${raio} m`}</Num>
        </label>
      )}
      <Btn variant="primary" tam="sm" disabled={local == null || criar.isPending}
        onClick={() => local != null && criar.mutate(
          { local, ...(temPerimetro ? {} : { raio_m: raio }) },
          {
            onSuccess: (r) => {
              say(r.origem_da_area === 'perimetro'
                ? `Plano criado sobre o perímetro de ${escolhido?.nome}. Agora calcule.`
                : `Plano criado num círculo de ${r.raio_m} m em volta de ${escolhido?.nome}. Ajuste a área em "Editar área" e calcule.`)
              aoCriar(r.plano)
            },
            onError: (e) => say(motivo(e, 'Não deu para criar o plano — confira se o local tem coordenada.')),
          },
        )}>
        <Plus size={13} /> Criar plano
      </Btn>
    </div>
  )
}

/* ═══════════ Rotas de entrega ═══════════ */

/**
 * **Rotas pelas ruas, montadas na tela** (item 70).
 *
 * O traçado de rua vem do OSRM (`OSRM_URL`); sem ele, a rota é a reta entre
 * paradas e sai carimbada "estimativa" — e a linha aparece TRACEJADA, para não
 * se passar por rua. E a aba só sabia listar: rota nascia pelo admin. Agora
 * nasce aqui (origem + paradas), é traçada na hora e pode ser excluída.
 */
export function Rotas({ say }: { say: Say }) {
  const { data, isLoading } = useRotas()
  const { data: status } = useStatusMaps(true)
  const otimizar = useOtimizarRota()
  const tracar = useTracarRota()
  const excluir = useExcluirRota()
  const [selecionada, setSelecionada] = useState<number | null>(null)
  const [criando, setCriando] = useState(false)
  const [violacoes, setViolacoes] = useState<Record<number, ViolacaoDeJanela[]>>({})

  const rotas = useMemo(() => data?.results ?? [], [data])
  const rota = rotas.find((r) => r.rota_id === selecionada) ?? rotas[0] ?? null

  const contexto = useLocaisDeContexto()
  const pontos: PontoMapa[] = useMemo(() => {
    if (!rota) return []
    const saida = contexto.find((l) => String(l.id) === String(rota.origem))
    return [
      ...(saida ? [{ ...saida, id: `origem-${rota.origem}`, nome: `Saída: ${rota.origem_nome}`, tipo: 'local_estoque' }] : []),
      ...rota.paradas
        .filter((p) => p.local_ponto)
        .map((p) => ({
          id: p.parada_id, lon: p.local_ponto!.lon, lat: p.local_ponto!.lat, tipo: 'obra',
          nome: `${p.ordem}. ${p.local_nome}`,
          detalhe: p.chegada_estimada_s != null ? `chegada ~${Math.round(p.chegada_estimada_s / 60)} min` : undefined,
        })),
    ]
  }, [rota, contexto])
  const camadas: CamadaGeoJSON[] = useMemo(() => (rota?.linha
    ? [{ id: `rota-${rota.rota_id}`, data: rota.linha, cor: '#3E9C6E', largura: 4, tracejado: rota.procedencia !== 'osrm' }]
    : []), [rota])

  if (isLoading) return <Loading o="as rotas" />

  const aoTracar = (r: Rota) => tracar.mutate(r.rota_id, {
    onSuccess: (x) => say(x.procedencia === 'osrm'
      ? `Traçado pelas ruas — ${x.distancia_km} km`
      : `Traçado em linha reta (sem motor de rota) — ${x.distancia_km} km`),
    onError: (e) => say(motivo(e, 'Alguma parada está sem coordenada — posicione o pin antes.')),
  })

  const painel = criando ? (
    <NovaRota say={say} aoCancelar={() => setCriando(false)}
      aoCriar={(r) => { setCriando(false); setSelecionada(r.rota_id); aoTracar(r) }} />
  ) : (
    <>
      <div style={{ padding: 10, borderBottom: '1px solid var(--line)', display: 'flex', alignItems: 'center', gap: 6 }}>
        <b style={{ fontFamily: 'var(--display)', fontSize: 14.5, color: 'var(--ink)', flex: 1 }}>
          Rotas <span style={{ color: 'var(--ink-3)', fontWeight: 600, fontSize: 12.5 }}>{rotas.length}</span>
        </b>
        <Btn tam="sm" variant="primary" onClick={() => setCriando(true)}><Plus size={13} /> Nova rota</Btn>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {rotas.length === 0 ? (
          <div style={{ padding: 16 }}>
            <Empty>
              Nenhuma rota ainda. Uma rota sai de um almoxarifado e passa pelos canteiros — a ordem é
              calculada por tempo de viagem, e as janelas de horário são conferidas.
            </Empty>
          </div>
        ) : rotas.map((r) => {
          const aberta = r.rota_id === rota?.rota_id
          const furos = violacoes[r.rota_id] ?? []
          return (
            <div key={r.rota_id} style={{ borderBottom: '1px solid var(--line-2)', background: aberta ? 'var(--surface-2)' : 'transparent' }}>
              <button type="button" onClick={() => setSelecionada(r.rota_id)}
                style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%', padding: '10px 11px', textAlign: 'left', font: 'inherit', background: 'none', border: 'none', cursor: 'pointer' }}>
                <RouteIcon size={15} style={{ color: aberta ? 'var(--accent-ink)' : 'var(--ink-3)', flex: 'none' }} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 13.5, color: 'var(--ink)' }}>{r.nome}</span>
                  <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)' }}>
                    Sai de {r.origem_nome} · {r.paradas.length} paradas{r.distancia_km != null ? ` · ${r.distancia_km} km` : ''}
                  </span>
                </span>
                {r.procedencia
                  ? <Pill kind={r.procedencia === 'osrm' ? 'good' : 'slate'}>{r.procedencia === 'osrm' ? 'pelas ruas' : 'linha reta'}</Pill>
                  : <Pill kind="slate">não traçada</Pill>}
              </button>
              {aberta && (
                <div style={{ padding: '0 11px 12px', display: 'grid', gap: 9 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                    <KpiTile label="Distância" valor={r.distancia_km != null ? <Num>{`${r.distancia_km} km`}</Num> : null}
                      pendente={r.distancia_km == null} base={r.procedencia_rotulo || 'não traçada'} />
                    <KpiTile label="Duração" valor={r.duracao_s ? <Num>{`${Math.round(r.duracao_s / 60)} min`}</Num> : null}
                      pendente={!r.duracao_s} base="tempo de viagem" />
                  </div>
                  {furos.length > 0 && (
                    <div style={{ padding: '9px 11px', borderRadius: 8, background: 'var(--danger-soft)' }}>
                      <b style={{ fontSize: 12, color: 'var(--danger-ink)', display: 'flex', alignItems: 'center', gap: 6 }}>
                        <Timer size={13} /> A ordem mais curta fura janelas de entrega
                      </b>
                      {furos.map((v) => (
                        <div key={v.parada} style={{ fontSize: 12, color: 'var(--danger-ink)', marginTop: 3 }}>
                          Chega às {v.chegada.slice(0, 5)} — {v.motivo}
                        </div>
                      ))}
                    </div>
                  )}
                  <ol style={{ margin: 0, paddingLeft: 18, listStyle: 'decimal', fontSize: 12.5, color: 'var(--ink-2)', display: 'grid', gap: 2 }}>
                    {r.paradas.map((p) => (
                      <li key={p.parada_id}>
                        {p.local_nome}
                        {!p.local_ponto && <span style={{ color: 'var(--danger-ink)' }}> — sem pin</span>}
                        {p.chegada_estimada_s != null && <span style={{ color: 'var(--ink-3)' }}> · ~{Math.round(p.chegada_estimada_s / 60)} min</span>}
                      </li>
                    ))}
                  </ol>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {/* Traçar ≠ otimizar: traçar desenha na ordem que está;
                        otimizar reordena as paradas e então traça. */}
                    <Btn tam="sm" disabled={tracar.isPending} onClick={() => aoTracar(r)}><Spline size={13} /> Traçar</Btn>
                    <Btn variant="primary" tam="sm" disabled={otimizar.isPending || r.paradas.length < 2}
                      title={r.paradas.length < 2 ? 'Otimizar exige ao menos duas paradas' : 'Reordenar as paradas pelo menor tempo'}
                      onClick={() => otimizar.mutate(r.rota_id, {
                        onSuccess: (x) => {
                          setViolacoes((v) => ({ ...v, [r.rota_id]: x.violacoes_de_janela }))
                          say(x.violacoes_de_janela.length
                            ? `Ordem otimizada — ${x.violacoes_de_janela.length} janela(s) em conflito`
                            : 'Ordem otimizada')
                        },
                        onError: (e) => say(motivo(e, 'Alguma parada está sem coordenada — posicione o pin antes.')),
                      })}>
                      <RouteIcon size={13} /> Otimizar
                    </Btn>
                    <Btn tam="sm" title="Excluir esta rota"
                      onClick={() => {
                        if (!window.confirm(`Excluir a rota "${r.nome}"?`)) return
                        excluir.mutate(r.rota_id, {
                          onSuccess: () => { say(`Rota "${r.nome}" excluída.`); setSelecionada(null) },
                          onError: (e) => say(motivo(e, 'Não deu para excluir a rota.')),
                        })
                      }}>
                      <Trash2 size={13} />
                    </Btn>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </>
  )

  return (
    <>
      <AvisoDeProvedores status={status} quais={['motor_rota']} />
      <MapaComPainel
        mapa={<Mapa pontos={pontos} camadas={camadas} enquadrar="camadas" altura={560} />}
        painel={painel}
        altura={560}
        rodape={rota && (
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 12, color: 'var(--ink-3)', alignItems: 'center' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 22, height: 4, borderRadius: 2, background: '#3E9C6E' }} /> traçado pelas ruas (OSRM)
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 22, height: 0, borderTop: '3px dashed #3E9C6E' }} /> linha reta — estimativa, não é rua
            </span>
            <span>Pin verde = saída; laranja = paradas (o número no nome é a ordem).</span>
          </div>
        )}
      />
    </>
  )
}

/** Montar a rota: nome, de onde sai e por onde passa — na ordem marcada. */
function NovaRota({ say, aoCancelar, aoCriar }: { say: Say; aoCancelar: () => void; aoCriar: (r: Rota) => void }) {
  const { data } = useLocais({ page_size: 200 })
  const salvar = useSalvarRota()
  const [nome, setNome] = useState('')
  const [origem, setOrigem] = useState<number | null>(null)
  const [paradas, setParadas] = useState<number[]>([])
  const [busca, setBusca] = useState('')

  const locais = (data?.results ?? []).filter((l) => l.ponto)
  const termo = busca.trim().toLowerCase()
  const visiveis = locais.filter((l) => l.local_id !== origem && (!termo || l.nome.toLowerCase().includes(termo)))
  const nomeDe = (id: number) => locais.find((l) => l.local_id === id)?.nome ?? `#${id}`

  // Almoxarifado primeiro: é de onde a entrega costuma sair.
  const origens = [...locais].sort((a, b) => Number(b.tipo === 'local_estoque') - Number(a.tipo === 'local_estoque'))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, height: '100%' }}>
      <div style={{ padding: 12, display: 'grid', gap: 8, borderBottom: '1px solid var(--line)' }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <b style={{ fontFamily: 'var(--display)', fontSize: 14.5, color: 'var(--ink)', flex: 1 }}>Nova rota</b>
          <Btn tam="sm" onClick={aoCancelar} title="Cancelar"><X size={13} /></Btn>
        </div>
        <input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Nome (ex.: Entrega de segunda)" style={inputEstilo} maxLength={180} />
        <select value={origem ?? ''} onChange={(e) => { const v = Number(e.target.value) || null; setOrigem(v); setParadas((p) => p.filter((x) => x !== v)) }} style={inputEstilo}>
          <option value="">Sai de…</option>
          {origens.map((l) => <option key={l.local_id} value={l.local_id}>{l.nome} — {ROTULO_TIPO[l.tipo] ?? l.tipo}</option>)}
        </select>
        {paradas.length > 0 && (
          <div style={{ fontSize: 12, color: 'var(--ink-2)' }}>
            <b>Paradas na ordem:</b> {paradas.map((id, i) => `${i + 1}. ${nomeDe(id)}`).join(' → ')}
          </div>
        )}
        <label style={{ position: 'relative', display: 'block' }}>
          <Search size={14} style={{ position: 'absolute', left: 9, top: 9, color: 'var(--ink-3)' }} />
          <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar parada…" style={{ ...inputEstilo, paddingLeft: 29 }} />
        </label>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '4px 0' }}>
        {locais.length === 0 ? (
          <div style={{ padding: 14, fontSize: 12.5, color: 'var(--ink-3)' }}>Nenhum local com pin — posicione-os no Mapa da empresa.</div>
        ) : visiveis.map((l) => {
          const marcada = paradas.includes(l.local_id)
          return (
            <label key={l.local_id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px', fontSize: 13, color: 'var(--ink)', cursor: 'pointer' }}>
              <input type="checkbox" checked={marcada}
                onChange={() => setParadas((p) => (marcada ? p.filter((x) => x !== l.local_id) : [...p, l.local_id]))} />
              <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.nome}</span>
              <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{ROTULO_TIPO[l.tipo] ?? l.tipo}</span>
              {marcada && <Pill kind="accent">{paradas.indexOf(l.local_id) + 1}</Pill>}
            </label>
          )
        })}
      </div>
      <div style={{ padding: 10, borderTop: '1px solid var(--line)', display: 'flex', gap: 6 }}>
        <Btn variant="primary" tam="sm" disabled={!origem || !paradas.length || salvar.isPending}
          onClick={() => origem && salvar.mutate(
            { nome: nome.trim() || `Rota — ${nomeDe(origem)}`, origem, paradas_locais: paradas },
            {
              onSuccess: (r) => { say(`Rota "${r.nome}" criada — traçando…`); aoCriar(r) },
              onError: (e) => say(motivo(e, 'Não deu para criar a rota.')),
            },
          )}>
          Criar e traçar
        </Btn>
        <Btn tam="sm" onClick={aoCancelar}>Cancelar</Btn>
      </div>
    </div>
  )
}

/** Cartão do módulo não contratado — cadeado com teaser, no padrão do farol. */
export function TerritorioBloqueado() {
  return (
    <Card style={{ textAlign: 'center', padding: 40 }}>
      <Plane size={30} style={{ color: 'var(--ink-3)', marginBottom: 12 }} />
      <h3 style={{ fontFamily: 'var(--display)', fontSize: 18, fontWeight: 700, color: 'var(--ink)', marginBottom: 8 }}>
        Esta aba é do módulo Maps
      </h3>
      <p style={{ fontSize: 13.5, color: 'var(--ink-3)', maxWidth: 520, margin: '0 auto' }}>
        Georreferenciar obra, fornecedor e almoxarifado continua incluso — é cadastro, e está no
        Mapa da empresa. Acervo de ortofotos, plano de voo, roteirização e cercas de canteiro têm
        custo próprio (storage raster, motor de rota) e vêm com o módulo <b>Maps</b>.
      </p>
    </Card>
  )
}
