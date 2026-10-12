import { useEffect, useRef, useState } from 'react'
// O MapLibre 6 deixou de ter export default: o namespace inteiro, e os tipos à parte.
import * as maplibregl from 'maplibre-gl'
import type { Map as MapLibreMap, StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
// O worker do MapLibre 6 é um ARQUIVO À PARTE, que ele procura ao lado do
// próprio módulo (`new URL('./maplibre-gl-worker.mjs', import.meta.url)`). O
// Vite não enxerga esse caminho montado em tempo de execução: no build o
// arquivo não ia para `assets/`, e no dev o pré-empacotamento o tirava do
// lugar — "Worker failed to load", e o mapa ficava sem nenhum pin, polígono ou
// rota (só os ladrilhos do fundo, que não passam pelo worker). `?worker&url`
// faz o Vite empacotar o worker (com o `maplibre-gl-shared` que ele importa) e
// devolve a URL certa nos dois modos.
import workerDoMapLibre from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { useTheme } from '@/hooks/useTheme'

/**
 * `<Mapa>` — a superfície espacial da Malha (MAP.1).
 *
 * Mora no kit COMPARTILHADO, não num quinto kit de módulo: obra, fornecedor,
 * almoxarifado e voo caem no mesmo mapa, e um mapa por módulo seria a dívida
 * dos kits paralelos multiplicada (docs/frontend.md §2).
 *
 * **MapLibre, e não Leaflet**, por dois motivos concretos: o mapa da empresa
 * desenha milhares de feições (vector/WebGL aguenta, DOM não) e o estilo é
 * JSON — claro e escuro saem do mesmo mecanismo de tema, sem trocar de
 * provedor de tile. O Leaflet fica no drone; são dois contextos, não uma
 * migração.
 *
 * **A precisão é desenhada, não escrita.** Cada pin ganha um halo cujo raio
 * cresce quando a coordenada é grossa: pin de porta é um ponto firme; centroide
 * de município é uma mancha larga. É a regra de ouro da planta §5 virada em
 * pixel — quem olha o mapa entende a incerteza sem ler legenda.
 *
 * **O mapa também é onde se edita** — pin arrastado à mão (`edicao`) e polígono
 * desenhado vértice a vértice (`desenho`). Sem isso, o pin "exata" que a
 * cascata tanto respeita só nascia pelo admin, e a área do voo só por GeoJSON
 * colado num POST.
 */

export interface PontoMapa {
  id: string | number
  lon: number
  lat: number
  nome: string
  /** `exata` | `endereco` | `cep` | `municipio` | `desconhecida` */
  precisao?: string
  tipo?: string
  detalhe?: string
}

export interface CamadaGeoJSON {
  id: string
  data: GeoJSON.FeatureCollection | GeoJSON.Feature | GeoJSON.Geometry
  cor?: string
  largura?: number
  preenchimento?: boolean
  /** Linha tracejada — o traçado que é estimativa, não rua. */
  tracejado?: boolean
}

export interface CamadaRaster {
  id: string
  /** URLs de tile com `{z}/{x}/{y}` — do backend, com gate (nunca o COG cru). */
  tiles: string[]
  opacidade?: number
}

type LonLat = [number, number]

interface Props {
  pontos?: PontoMapa[]
  camadas?: CamadaGeoJSON[]
  rasters?: CamadaRaster[]
  altura?: number | string
  centro?: [number, number]
  zoom?: number
  /**
   * Voa até um ponto quando ele muda — o "me mostra ONDE isto está".
   *
   * `centro` só vale na criação do mapa, de propósito (recriar o enquadramento a
   * cada render mataria o pan de quem está navegando). `null` não faz nada; o
   * `selo` existe para pedir a MESMA coordenada de novo e ainda assim voar.
   */
  foco?: { lon: number; lat: number; zoom?: number; selo?: number } | null
  /**
   * Enquadra tudo que foi passado — pins e, sem pins, as camadas (default: sim).
   *
   * Reenquadra só quando o CONJUNTO muda (outros ids), não quando um pin se
   * move: quem acabou de arrastar a obra para a porta certa não quer o mapa
   * fugindo para mostrar o Brasil inteiro de novo.
   */
  ajustar?: boolean
  /** O que manda no enquadramento quando há pins E camadas (default: pins). */
  enquadrar?: 'pontos' | 'camadas'
  satelite?: boolean
  /** Pin destacado (anel em volta) — a linha escolhida na lista ao lado. */
  selecionado?: string | number | null
  onSelecionar?: (id: string | number) => void
  onClicarMapa?: (lon: number, lat: number) => void
  /**
   * Modo "posicionar pin": um marcador arrastável; clicar no mapa o move.
   * `ponto: null` = ainda sem lugar — o primeiro clique o cria.
   */
  edicao?: { ponto: { lon: number; lat: number } | null; aoMover: (lon: number, lat: number) => void } | null
  /**
   * Modo "desenhar polígono": cada clique acrescenta um vértice; cada vértice
   * é um marcador arrastável (é assim que se EDITA uma área existente).
   */
  desenho?: { vertices: LonLat[]; aoMudar: (vertices: LonLat[]) => void; cor?: string } | null
}

import { COR_TIPO, HALO_PRECISAO as HALO } from './mapaCores'

maplibregl.setWorkerUrl(workerDoMapLibre)

// Centro do Brasil — enquadramento inicial de quem ainda não tem nenhum pin.
const BRASIL: [number, number] = [-51.9, -14.2]

/**
 * O estilo nasce com **todos** os fundos, e trocar de fundo é mudar
 * visibilidade — nunca `setStyle`.
 *
 * Antes era `setStyle` a cada troca, e a troca apagava o que o mapa tinha
 * desenhado: o `setStyle` descarta as camadas próprias, o redesenho esperava o
 * `styledata` e desistia se o estilo ainda não estivesse pronto — então clicar
 * em "Satélite" sumia com todos os pins (item 65). Com os fundos já no estilo,
 * pins, polígonos e rotas nunca saem do lugar.
 *
 * O satélite ganha os **rótulos de referência** por cima (ruas, bairros,
 * cidades): imagem aérea sem nome de rua é foto, não mapa.
 *
 * Provedores GRÁTIS por padrão (planta §9). O tile público do OSM fica de fora
 * de propósito: a política de uso dele restringe uso comercial pesado, e um
 * SaaS multi-tenant é exatamente isso. Pago entra como knob de payment/.
 */
function estilo(escuro: boolean, satelite: boolean): StyleSpecification {
  const esri = (servico: string) =>
    [`https://server.arcgisonline.com/ArcGIS/rest/services/${servico}/MapServer/tile/{z}/{y}/{x}`]
  const vis = (on: boolean) => ({ visibility: on ? 'visible' as const : 'none' as const })
  return {
    version: 8,
    sources: {
      claro: { type: 'raster', tileSize: 256, tiles: ['https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'], attribution: '© OpenStreetMap · © CARTO' },
      escuro: { type: 'raster', tileSize: 256, tiles: ['https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'], attribution: '© OpenStreetMap · © CARTO' },
      satelite: { type: 'raster', tileSize: 256, tiles: esri('World_Imagery'), attribution: 'Esri, Maxar, Earthstar Geographics' },
      ruas: { type: 'raster', tileSize: 256, tiles: esri('Reference/World_Transportation') },
      lugares: { type: 'raster', tileSize: 256, tiles: esri('Reference/World_Boundaries_and_Places') },
    },
    layers: [
      { id: 'fundo-claro', type: 'raster', source: 'claro', layout: vis(!satelite && !escuro) },
      { id: 'fundo-escuro', type: 'raster', source: 'escuro', layout: vis(!satelite && escuro) },
      { id: 'fundo-satelite', type: 'raster', source: 'satelite', layout: vis(satelite) },
      { id: 'rotulo-ruas', type: 'raster', source: 'ruas', layout: vis(satelite) },
      { id: 'rotulo-lugares', type: 'raster', source: 'lugares', layout: vis(satelite) },
    ],
  }
}

function aplicarFundo(m: MapLibreMap, escuro: boolean, satelite: boolean) {
  const vis: Record<string, boolean> = {
    'fundo-claro': !satelite && !escuro,
    'fundo-escuro': !satelite && escuro,
    'fundo-satelite': satelite,
    'rotulo-ruas': satelite,
    'rotulo-lugares': satelite,
  }
  Object.entries(vis).forEach(([id, on]) => {
    if (m.getLayer(id)) m.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none')
  })
  if (m.getLayer('pinos')) m.setPaintProperty('pinos', 'circle-stroke-color', escuro && !satelite ? '#0E1116' : '#FFFFFF')
}

function paraFeatures(pontos: PontoMapa[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: pontos.map((p) => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [p.lon, p.lat] },
      properties: {
        id: String(p.id),
        nome: p.nome,
        detalhe: p.detalhe ?? '',
        precisao: p.precisao ?? 'exata',
        halo: HALO[p.precisao ?? 'exata'] ?? 0,
        cor: COR_TIPO[p.tipo ?? 'avulso'] ?? COR_TIPO.avulso,
      },
    })),
  }
}

/** Todas as coordenadas de uma geometria/feature — para enquadrar camadas. */
function coordenadas(dado: CamadaGeoJSON['data'], saida: LonLat[] = []): LonLat[] {
  if (!dado) return saida
  if (dado.type === 'FeatureCollection') { dado.features.forEach((f) => coordenadas(f, saida)); return saida }
  if (dado.type === 'Feature') return dado.geometry ? coordenadas(dado.geometry, saida) : saida
  if (dado.type === 'GeometryCollection') { dado.geometries.forEach((g) => coordenadas(g, saida)); return saida }
  const varrer = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === 'number') saida.push([c[0] as number, c[1] as number])
    else if (Array.isArray(c)) c.forEach(varrer)
  }
  varrer((dado as { coordinates: unknown }).coordinates)
  return saida
}

export function Mapa({
  pontos = [], camadas = [], rasters = [], altura = 460,
  centro, zoom = 4, foco = null, ajustar = true, enquadrar = 'pontos', satelite = false, selecionado = null,
  onSelecionar, onClicarMapa, edicao = null, desenho = null,
}: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapa = useRef<MapLibreMap | null>(null)
  const [pronto, setPronto] = useState(false)
  const { resolved } = useTheme()
  const escuro = resolved === 'dark'

  // Os handlers mudam a cada render (closures da tela); o mapa registra UM
  // ouvinte por evento e lê o handler atual daqui. Registrar o callback direto
  // na criação congelava a primeira versão dele — e um clique de "posicionar
  // pin" chamaria o estado de quando o mapa nasceu.
  const handlers = useRef({ onSelecionar, onClicarMapa, edicao, desenho })
  handlers.current = { onSelecionar, onClicarMapa, edicao, desenho }

  // ── criação (uma vez) ────────────────────────────────────────────────────
  useEffect(() => {
    if (!container.current || mapa.current) return
    const m = new maplibregl.Map({
      container: container.current,
      style: estilo(escuro, satelite),
      center: centro ?? BRASIL,
      zoom: centro ? zoom : 3.4,
      attributionControl: { compact: true },
      // Duplo clique fecha o polígono no modo desenho; o zoom por duplo clique
      // brigaria com isso e acrescentaria dois vértices fantasmas.
      doubleClickZoom: false,
    })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.addControl(new maplibregl.ScaleControl({ maxWidth: 90, unit: 'metric' }))
    m.on('load', () => setPronto(true))

    m.on('click', (e) => {
      const h = handlers.current
      const { lng, lat } = e.lngLat
      if (h.desenho) { h.desenho.aoMudar([...h.desenho.vertices, [lng, lat]]); return }
      if (h.edicao) { h.edicao.aoMover(lng, lat); return }
      const alvo = m.getLayer('pinos') ? m.queryRenderedFeatures(e.point, { layers: ['pinos'] })[0] : undefined
      const id = alvo?.properties?.id
      if (id != null) { h.onSelecionar?.(id as string); return }
      h.onClicarMapa?.(lng, lat)
    })
    m.on('mousemove', (e) => {
      const h = handlers.current
      if (h.desenho || h.edicao) { m.getCanvas().style.cursor = 'crosshair'; return }
      const sobre = m.getLayer('pinos') && m.queryRenderedFeatures(e.point, { layers: ['pinos'] }).length > 0
      m.getCanvas().style.cursor = sobre && h.onSelecionar ? 'pointer' : ''
    })

    mapa.current = m
    return () => { m.remove(); mapa.current = null }
    // Recriar o mapa a cada mudança de prop mataria o estado de navegação do
    // usuário (zoom, pan). Fundo, dados e tema são atualizados nos efeitos
    // abaixo, sobre a MESMA instância.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── tema e fundo — visibilidade, nunca `setStyle` ────────────────────────
  useEffect(() => {
    if (!mapa.current || !pronto) return
    aplicarFundo(mapa.current, escuro, satelite)
  }, [escuro, satelite, pronto])

  // ── dados ────────────────────────────────────────────────────────────────
  const desenhadas = useRef<{ camadas: Set<string>; rasters: Set<string> }>({ camadas: new Set(), rasters: new Set() })
  useEffect(() => {
    if (!mapa.current || !pronto) return
    desenhar(mapa.current, pontos, camadas, rasters, escuro && !satelite, desenhadas.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pontos, camadas, rasters, pronto])

  // ── seleção ──────────────────────────────────────────────────────────────
  useEffect(() => {
    const m = mapa.current
    if (!m || !pronto || !m.getLayer('selecao')) return
    m.setFilter('selecao', ['==', ['get', 'id'], selecionado == null ? '' : String(selecionado)])
  }, [selecionado, pronto, pontos])

  // ── enquadramento ────────────────────────────────────────────────────────
  const pelosPontos = enquadrar === 'pontos' ? pontos.length > 0 : camadas.length === 0
  const chaveDoConjunto = pelosPontos
    ? `p:${pontos.map((p) => p.id).join('|')}`
    : `c:${camadas.map((c) => c.id).join('|')}`
  useEffect(() => {
    if (!mapa.current || !pronto || !ajustar) return
    const coords: LonLat[] = pelosPontos
      ? pontos.map((p) => [p.lon, p.lat])
      : camadas.flatMap((c) => coordenadas(c.data))
    if (!coords.length) return
    const limites = new maplibregl.LngLatBounds()
    coords.forEach((c) => limites.extend(c))
    mapa.current.fitBounds(limites, { padding: 64, maxZoom: pelosPontos ? 14 : 17, duration: 420 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chaveDoConjunto, ajustar, pronto])

  // ── foco ─────────────────────────────────────────────────────────────────
  // Declarado DEPOIS do enquadramento de propósito: quando os dois mudam na
  // mesma renderização, quem tem de vencer é o pedido explícito.
  useEffect(() => {
    if (!mapa.current || !pronto || !foco) return
    mapa.current.flyTo({ center: [foco.lon, foco.lat], zoom: foco.zoom ?? 15, duration: 700 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [foco?.lon, foco?.lat, foco?.zoom, foco?.selo, pronto])

  // ── edição de pin: um marcador arrastável ────────────────────────────────
  const marcador = useRef<maplibregl.Marker | null>(null)
  const pontoEditado = edicao?.ponto ?? null
  useEffect(() => {
    const m = mapa.current
    if (!m || !pronto) return
    if (!edicao || !pontoEditado) {
      marcador.current?.remove()
      marcador.current = null
      return
    }
    if (!marcador.current) {
      marcador.current = new maplibregl.Marker({ draggable: true, color: '#E79A22' })
        .setLngLat([pontoEditado.lon, pontoEditado.lat])
        .addTo(m)
      marcador.current.on('dragend', () => {
        const p = marcador.current?.getLngLat()
        if (p) handlers.current.edicao?.aoMover(p.lng, p.lat)
      })
    } else {
      marcador.current.setLngLat([pontoEditado.lon, pontoEditado.lat])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!edicao, pontoEditado?.lon, pontoEditado?.lat, pronto])

  // ── desenho de polígono: vértices arrastáveis + o polígono provisório ────
  const vertices = desenho?.vertices ?? null
  const marcadoresVertice = useRef<maplibregl.Marker[]>([])
  useEffect(() => {
    const m = mapa.current
    if (!m || !pronto) return
    marcadoresVertice.current.forEach((mk) => mk.remove())
    marcadoresVertice.current = []
    const cor = desenho?.cor ?? '#E79A22'
    const fechado: LonLat[] = vertices && vertices.length >= 3 ? [...vertices, vertices[0]] : []
    const dados: GeoJSON.FeatureCollection = {
      type: 'FeatureCollection',
      features: !vertices ? [] : [
        ...(fechado.length
          ? [{ type: 'Feature' as const, properties: {}, geometry: { type: 'Polygon' as const, coordinates: [fechado] } }]
          : vertices.length === 2
            ? [{ type: 'Feature' as const, properties: {}, geometry: { type: 'LineString' as const, coordinates: vertices } }]
            : []),
      ],
    }
    const fonte = m.getSource('desenho') as maplibregl.GeoJSONSource | undefined
    if (fonte) fonte.setData(dados)
    else {
      m.addSource('desenho', { type: 'geojson', data: dados })
      m.addLayer({ id: 'desenho-fill', type: 'fill', source: 'desenho', paint: { 'fill-color': cor, 'fill-opacity': 0.22 }, filter: ['==', ['geometry-type'], 'Polygon'] })
      m.addLayer({ id: 'desenho-line', type: 'line', source: 'desenho', paint: { 'line-color': cor, 'line-width': 2.5, 'line-dasharray': [2, 1] } })
    }
    if (!vertices) return
    vertices.forEach(([lon, lat], i) => {
      const el = document.createElement('div')
      el.style.cssText = `width:12px;height:12px;border-radius:50%;background:#fff;border:2.5px solid ${cor};box-shadow:0 1px 3px rgba(0,0,0,.4);cursor:grab`
      el.title = 'Arraste para mover · clique com o botão direito para remover'
      el.addEventListener('contextmenu', (ev) => {
        ev.preventDefault()
        ev.stopPropagation()
        const d = handlers.current.desenho
        if (d) d.aoMudar(d.vertices.filter((_, j) => j !== i))
      })
      // O clique no vértice não pode virar "acrescentar vértice" no mapa embaixo.
      el.addEventListener('click', (ev) => ev.stopPropagation())
      const mk = new maplibregl.Marker({ element: el, draggable: true }).setLngLat([lon, lat]).addTo(m)
      mk.on('dragend', () => {
        const d = handlers.current.desenho
        const p = mk.getLngLat()
        if (d) d.aoMudar(d.vertices.map((v, j) => (j === i ? [p.lng, p.lat] as LonLat : v)))
      })
      marcadoresVertice.current.push(mk)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vertices, pronto])

  return (
    <div
      ref={container}
      style={{
        height: typeof altura === 'number' ? `${altura}px` : altura,
        width: '100%',
        borderRadius: 'var(--r-md)',
        overflow: 'hidden',
        border: '1px solid var(--line)',
        background: 'var(--surface-2)',
      }}
    />
  )
}

/**
 * (Re)desenha as camadas próprias sobre o estilo atual.
 *
 * Remove o que saiu da lista: camada desligada na legenda e plano excluído têm
 * de sumir do mapa — antes, uma vez desenhada, a camada ficava para sempre.
 */
function desenhar(
  m: MapLibreMap,
  pontos: PontoMapa[],
  camadas: CamadaGeoJSON[],
  rasters: CamadaRaster[],
  escuro: boolean,
  desenhadas: { camadas: Set<string>; rasters: Set<string> },
) {
  const antesDosPinos = m.getLayer('halos') ? 'halos' : undefined
  // Imagem (ortofoto) vai por BAIXO de todo desenho vetorial: o envelope e a
  // área do voo precisam continuar visíveis por cima da foto.
  const antesDosVetores = m.getStyle().layers
    .find((l) => l.id.startsWith('geo-') || l.id === 'halos' || l.id.startsWith('desenho'))?.id

  const rastersAgora = new Set(rasters.map((r) => `raster-${r.id}`))
  desenhadas.rasters.forEach((id) => {
    if (rastersAgora.has(id)) return
    if (m.getLayer(id)) m.removeLayer(id)
    if (m.getSource(id)) m.removeSource(id)
    desenhadas.rasters.delete(id)
  })
  rasters.forEach((r) => {
    const id = `raster-${r.id}`
    if (m.getSource(id)) return
    m.addSource(id, { type: 'raster', tiles: r.tiles, tileSize: 256 })
    m.addLayer({ id, type: 'raster', source: id, paint: { 'raster-opacity': r.opacidade ?? 0.85 } }, antesDosVetores)
    desenhadas.rasters.add(id)
  })

  const camadasAgora = new Set(camadas.map((c) => `geo-${c.id}`))
  desenhadas.camadas.forEach((id) => {
    if (camadasAgora.has(id)) return
    ;[`${id}-fill`, `${id}-line`, `${id}-ponto`].forEach((l) => { if (m.getLayer(l)) m.removeLayer(l) })
    if (m.getSource(id)) m.removeSource(id)
    desenhadas.camadas.delete(id)
  })
  camadas.forEach((c) => {
    const id = `geo-${c.id}`
    const cor = c.cor ?? '#E79A22'
    const dados = (c.data.type === 'FeatureCollection' || c.data.type === 'Feature'
      ? c.data
      : { type: 'Feature' as const, geometry: c.data, properties: {} }) as GeoJSON.FeatureCollection | GeoJSON.Feature
    const fonte = m.getSource(id) as maplibregl.GeoJSONSource | undefined
    if (fonte) {
      fonte.setData(dados)
      if (m.getLayer(`${id}-line`)) m.setPaintProperty(`${id}-line`, 'line-color', cor)
      if (m.getLayer(`${id}-fill`)) m.setPaintProperty(`${id}-fill`, 'fill-color', cor)
      return
    }
    m.addSource(id, { type: 'geojson', data: dados })
    if (c.preenchimento !== false) {
      m.addLayer({ id: `${id}-fill`, type: 'fill', source: id, paint: { 'fill-color': cor, 'fill-opacity': 0.18 }, filter: ['==', ['geometry-type'], 'Polygon'] }, antesDosPinos)
    }
    m.addLayer({
      id: `${id}-line`, type: 'line', source: id,
      paint: { 'line-color': cor, 'line-width': c.largura ?? 2.5, ...(c.tracejado ? { 'line-dasharray': [2, 1.5] } : {}) },
      filter: ['!=', ['geometry-type'], 'Point'],
    }, antesDosPinos)
    // Feição pontual de camada (marco, sondagem) — sem isto ela não aparecia.
    m.addLayer({
      id: `${id}-ponto`, type: 'circle', source: id,
      paint: { 'circle-radius': 4.5, 'circle-color': cor, 'circle-stroke-width': 1.5, 'circle-stroke-color': '#FFFFFF' },
      filter: ['==', ['geometry-type'], 'Point'],
    }, antesDosPinos)
    desenhadas.camadas.add(id)
  })

  const dados = paraFeatures(pontos)
  const fonte = m.getSource('locais') as maplibregl.GeoJSONSource | undefined
  if (fonte) { fonte.setData(dados); return }

  m.addSource('locais', { type: 'geojson', data: dados })
  // Halo da incerteza — desenhado ANTES do pino para ficar por baixo.
  m.addLayer({
    id: 'halos',
    type: 'circle',
    source: 'locais',
    filter: ['>', ['get', 'halo'], 0],
    paint: {
      'circle-radius': ['get', 'halo'],
      'circle-color': ['get', 'cor'],
      'circle-opacity': 0.16,
      'circle-stroke-width': 1,
      'circle-stroke-color': ['get', 'cor'],
      'circle-stroke-opacity': 0.4,
    },
  })
  m.addLayer({
    id: 'selecao',
    type: 'circle',
    source: 'locais',
    filter: ['==', ['get', 'id'], ''],
    paint: {
      'circle-radius': 12,
      'circle-color': 'transparent',
      'circle-stroke-width': 3,
      'circle-stroke-color': '#E79A22',
    },
  })
  m.addLayer({
    id: 'pinos',
    type: 'circle',
    source: 'locais',
    paint: {
      'circle-radius': 6,
      'circle-color': ['get', 'cor'],
      'circle-stroke-width': 2,
      'circle-stroke-color': escuro ? '#0E1116' : '#FFFFFF',
    },
  })

  const balao = new maplibregl.Popup({ closeButton: false, offset: 12 })
  m.on('mouseenter', 'pinos', (e) => {
    const f = e.features?.[0]
    if (!f) return
    const p = f.properties as Record<string, string>
    const coords = (f.geometry as GeoJSON.Point).coordinates as [number, number]
    balao
      .setLngLat(coords)
      .setHTML(
        `<div style="font-family:system-ui;font-size:12.5px;line-height:1.35;color:#1b1f27">
           <b>${escapar(p.nome)}</b>
           ${p.detalhe ? `<br><span style="opacity:.75">${escapar(p.detalhe)}</span>` : ''}
           <br><span style="opacity:.6;font-size:11px">Precisão: ${escapar(p.precisao)}</span>
         </div>`,
      )
      .addTo(m)
  })
  m.on('mouseleave', 'pinos', () => balao.remove())
}

function escapar(texto: string): string {
  return String(texto ?? '').replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] ?? c))
}

export default Mapa
