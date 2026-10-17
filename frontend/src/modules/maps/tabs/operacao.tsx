import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, Building2, ChevronRight, Crosshair, HardHat, Layers, MapPin, MapPinPlus, Move,
  Navigation, Radar, RefreshCw, Search, Trash2, Truck, Warehouse, X,
} from 'lucide-react'
import { BotaoExportar, Btn, Card, Empty, KpiTile, Loading, Mapa, Num, Pill, SectionHead, WizardImportacao } from '@/components/malha'
import type { CamadaGeoJSON, PillKind, PontoMapa } from '@/components/malha'
import { COR_TIPO } from '@/components/malha/mapaCores'
import * as api from '../api'
import {
  mapsKeys, useExcluirLocal, useGeocodificar, useLocais, useMapa, useProximos, useSalvarLocal, useStatusMaps,
} from '../hooks'
import type { Destino, Ir, Local, LocalResumo, Precisao, UnidadeDetalhe } from '../types'
import { AvisoDeProvedores, FaixaDoMapa, LegendaDoMapa, MapaComPainel } from './comum'
import { ROTULO_TIPO, inputEstilo, motivo, selectEstilo, type Say } from './util'

export type { Say } from './util'

/** Como cada precisão se apresenta. O rótulo é sempre o que o backend mandou —
 *  aqui só se escolhe a cor, e a cor conta a mesma história do halo do mapa. */
const PRECISAO_KIND: Record<Precisao, PillKind> = {
  exata: 'good', endereco: 'info', cep: 'accent', municipio: 'danger', desconhecida: 'slate',
}
const ICONE_TIPO: Record<string, React.ReactNode> = {
  obra: <HardHat size={14} />, empreendimento: <Building2 size={14} />,
  fornecedor: <Truck size={14} />, local_estoque: <Warehouse size={14} />,
  unidade: <Building2 size={14} />, avulso: <MapPin size={14} />,
}

function paraPontos(locais: LocalResumo[]): PontoMapa[] {
  return locais
    .filter((l) => l.ponto)
    .map((l) => ({
      id: l.local_id,
      lon: l.ponto!.lon,
      lat: l.ponto!.lat,
      nome: l.nome,
      tipo: l.tipo,
      precisao: l.precisao,
      detalhe: [l.vinculo_rotulo, [l.cidade, l.uf].filter(Boolean).join(' - ')]
        .filter(Boolean).join(' · '),
    }))
}

const semAcento = (t: string) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

/**
 * Para onde cada pendência da fila leva — o que transforma o cartaz em fila.
 *
 * Desde que a tabela de locais virou o painel do mapa, todas as pendências de
 * cadastro levam ao MESMO lugar (o mapa), já com o recorte que isola o que a
 * pendência conta: "12 obras sem coordenada" abre o painel mostrando só as 12.
 */
const DESTINO_DA_PENDENCIA: Record<string, (alvo: string) => Destino | null> = {
  sem_coordenada: (alvo) => ({ tab: 'mapa', filtro: { tipo: alvo, precisao: 'desconhecida' } }),
  precisao_grosseira: () => ({ tab: 'mapa', filtro: { precisao: 'municipio' } }),
  rua_divergente: () => ({ tab: 'mapa', filtro: { tipo: 'unidade' } }),
  ortofoto_vencida: () => ({ tab: 'acervo' }),
  voo_sem_autorizacao: () => ({ tab: 'voos' }),
}

type Modo =
  | { tipo: 'posicionar'; local: Local; ponto: { lon: number; lat: number } | null }
  | { tipo: 'novo'; nome: string; ponto: { lon: number; lat: number } | null }

/** O que se pode sobrepor ao mapa da empresa quando o tenant assina Maps. */
const SOBREPOSICOES_FIXAS = [
  { id: 'planos', rotulo: 'Planos de voo', cor: '#1D9AA6' },
  { id: 'rotas', rotulo: 'Rotas', cor: '#3E9C6E' },
  { id: 'acervo', rotulo: 'Ortofotos (envelopes)', cor: '#8892A6' },
] as const

/**
 * **As camadas do território, no mapa da empresa** (item 68).
 *
 * A antiga aba "Camadas" era uma lista de etiquetas e um mapa vazio: nenhuma
 * camada existia, e mesmo existindo ela ficava num mapa à parte, longe das
 * obras. Aqui camada é o que o nome diz — algo que se liga e desliga POR CIMA
 * do mapa da empresa: os planos de voo, as rotas, os envelopes do acervo e as
 * camadas temáticas (sondagens, marcos, interferências). É também onde os
 * módulos se encontram na tela: a obra do cadastro, o voo e a entrega no mesmo
 * enquadramento.
 */
function useSobreposicoes(temMaps: boolean, ativas: Set<string>) {
  const { data: camadas } = useQuery({ queryKey: mapsKeys.camadas, queryFn: api.listarCamadas, enabled: temMaps })
  const algumaTematica = [...ativas].some((a) => a.startsWith('camada-'))
  const { data: feicoes } = useQuery({
    queryKey: mapsKeys.feicoes({ page_size: 500 }),
    queryFn: () => api.listarFeicoes({ page_size: 500 }),
    enabled: temMaps && algumaTematica,
  })
  const { data: planos } = useQuery({ queryKey: mapsKeys.planos, queryFn: api.listarPlanos, enabled: temMaps })
  const { data: rotas } = useQuery({ queryKey: mapsKeys.rotas, queryFn: api.listarRotas, enabled: temMaps })
  const { data: ortofotos } = useQuery({ queryKey: mapsKeys.ortofotos, queryFn: () => api.listarOrtofotos(), enabled: temMaps })

  const desenho = useMemo<CamadaGeoJSON[]>(() => {
    const saida: CamadaGeoJSON[] = []
    if (ativas.has('planos')) {
      ;(planos?.results ?? []).forEach((p) => saida.push({ id: `plano-${p.plano_id}`, data: p.area, cor: '#1D9AA6' }))
    }
    if (ativas.has('rotas')) {
      ;(rotas?.results ?? []).filter((r) => r.linha).forEach((r) => saida.push({
        id: `rota-${r.rota_id}`, data: r.linha!, cor: '#3E9C6E', largura: 3, tracejado: r.procedencia !== 'osrm',
      }))
    }
    if (ativas.has('acervo')) {
      ;(ortofotos?.results ?? []).forEach((o) => saida.push({ id: `orto-${o.ortofoto_id}`, data: o.bbox, cor: '#8892A6', preenchimento: false }))
    }
    ;(camadas?.results ?? []).forEach((c) => {
      if (!ativas.has(`camada-${c.camada_id}`)) return
      const doCamada = (feicoes?.results ?? []).filter((f) => f.camada === c.camada_id)
      if (!doCamada.length) return
      saida.push({
        id: `camada-${c.camada_id}`, cor: c.cor,
        data: { type: 'FeatureCollection', features: doCamada.map((f) => ({ type: 'Feature', geometry: f.geom, properties: { nome: f.nome } })) },
      })
    })
    return saida
  }, [ativas, planos, rotas, ortofotos, camadas, feicoes])

  const contagem: Record<string, number> = {
    planos: planos?.count ?? 0, rotas: rotas?.count ?? 0, acervo: ortofotos?.count ?? 0,
  }
  return { desenho, camadas: camadas?.results ?? [], contagem }
}

/* ═══════════ Mapa da empresa — mapa + painel de locais + camadas ═══════════ */
export function MapaDaEmpresa({ say, ir, temMaps, foco = null, filtroInicial }: {
  say: Say; ir: Ir; temMaps: boolean
  foco?: { lon: number; lat: number } | null
  filtroInicial?: Record<string, string>
}) {
  const { data, isLoading } = useMapa()
  const { data: status } = useStatusMaps(temMaps)
  const [satelite, setSatelite] = useState(false)
  // O recorte nasce do que a fila de decisão pediu: chegar por "12 obras sem
  // coordenada" e encontrar o seletor em "Todos" obrigaria a refazer o filtro.
  const [tipo, setTipo] = useState(filtroInicial?.tipo ?? '')
  const [precisao, setPrecisao] = useState(filtroInicial?.precisao ?? '')
  const [busca, setBusca] = useState('')
  const qcPlanilha = useQueryClient()
  const [selecionado, setSelecionado] = useState<number | null>(null)
  const [focoAtual, setFocoAtual] = useState<{ lon: number; lat: number; selo?: number } | null>(foco)
  const [modo, setModo] = useState<Modo | null>(null)
  const [ativas, setAtivas] = useState<Set<string>>(() => new Set(['planos', 'rotas']))
  const sobre = useSobreposicoes(temMaps, ativas)
  const salvar = useSalvarLocal()

  const pontos = useMemo(() => {
    const termo = semAcento(busca.trim())
    return paraPontos((data?.locais ?? []).filter((l) =>
      (!tipo || l.tipo === tipo)
      && (!precisao || l.precisao === precisao)
      && (!termo || semAcento(`${l.nome} ${l.cidade} ${l.vinculo_rotulo}`).includes(termo)),
    ))
  }, [data, tipo, precisao, busca])
  // Recorte sem nenhum pin (ex.: "sem coordenada" vindo da fila de decisão) não tem o que
  // mostrar no mapa: abre sem restrição, em vez de um mapa vazio no meio do Brasil.
  const todosPontos = useMemo(() => paraPontos(data?.locais ?? []), [data])
  const pontosNoMapa = pontos.length > 0 ? pontos : todosPontos

  if (isLoading) return <Loading o="o mapa da empresa" />
  if (!data) return <Empty>Não foi possível carregar o mapa.</Empty>

  const { resumo, requer_decisao } = data
  const semCoordenada = resumo.total - resumo.com_coordenada

  const selecionar = (id: number, ponto: { lon: number; lat: number } | null) => {
    setSelecionado(id)
    if (ponto) setFocoAtual({ ...ponto, selo: Date.now() })
  }

  const salvarModo = () => {
    if (!modo?.ponto) return
    if (modo.tipo === 'posicionar') {
      salvar.mutate({ local_id: modo.local.local_id, ponto: modo.ponto }, {
        onSuccess: () => { say(`Pin de ${modo.local.nome} salvo (posição manual).`); setModo(null) },
        onError: (e) => say(motivo(e, 'Não foi possível salvar o pin.')),
      })
    } else {
      salvar.mutate({ nome: modo.nome.trim(), tipo: 'avulso', ponto: modo.ponto }, {
        onSuccess: (novo) => { say(`Ponto "${novo.nome}" criado.`); setModo(null); setSelecionado(novo.local_id) },
        onError: (e) => say(motivo(e, 'Não foi possível criar o ponto.')),
      })
    }
  }

  const mapa = (
    <>
      <Mapa
        pontos={modo?.tipo === 'posicionar' ? pontosNoMapa.filter((p) => p.id !== modo.local.local_id) : pontosNoMapa}
        camadas={sobre.desenho}
        altura={600} satelite={satelite} foco={focoAtual} selecionado={selecionado}
        onSelecionar={(id) => {
          const local = data.locais.find((l) => String(l.local_id) === String(id))
          if (local) selecionar(local.local_id, null)
        }}
        edicao={modo ? { ponto: modo.ponto, aoMover: (lon, lat) => setModo({ ...modo, ponto: { lon, lat } }) } : null}
      />
      {modo ? (
        <FaixaDoMapa>
          <Move size={15} style={{ color: 'var(--accent-ink)' }} />
          <span style={{ flex: 1, minWidth: 180 }}>
            {modo.tipo === 'posicionar'
              ? <>Clique no mapa ou arraste o pin para posicionar <b>{modo.local.nome}</b>.</>
              : <>Clique no mapa onde fica o novo ponto{modo.nome ? <> <b>{modo.nome}</b></> : ''}.</>}
          </span>
          <Btn tam="sm" onClick={() => setModo(null)}>Cancelar</Btn>
          <Btn tam="sm" variant="primary" onClick={salvarModo}
            disabled={!modo.ponto || salvar.isPending || (modo.tipo === 'novo' && !modo.nome.trim())}>
            Salvar pin
          </Btn>
        </FaixaDoMapa>
      ) : (
        <div style={{ position: 'absolute', top: 10, left: 10, zIndex: 2 }}>
          <Btn tam="sm" onClick={() => setSatelite((s) => !s)}
            style={{ boxShadow: 'var(--shadow-sm)' }}>
            {satelite ? 'Mapa' : 'Satélite'}
          </Btn>
        </div>
      )}
    </>
  )

  const legendaDeCamadas = temMaps ? (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
      <span style={{ fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', fontSize: 10.5, color: 'var(--ink-3)', minWidth: 64, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        <Layers size={12} /> Camadas
      </span>
      {[...SOBREPOSICOES_FIXAS.map((s) => ({ ...s, n: sobre.contagem[s.id] ?? 0 })),
        ...sobre.camadas.map((c) => ({ id: `camada-${c.camada_id}`, rotulo: c.nome, cor: c.cor, n: c.total_feicoes ?? 0 }))]
        .map((s) => {
          const on = ativas.has(s.id)
          return (
            <label key={s.id} style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 9px', borderRadius: 999, fontSize: 12,
              cursor: 'pointer', color: on ? 'var(--ink)' : 'var(--ink-3)', border: '1px solid var(--line)',
              background: on ? 'var(--surface-2)' : 'transparent',
            }}>
              <input type="checkbox" checked={on} style={{ margin: 0 }}
                onChange={() => setAtivas((a) => { const n = new Set(a); if (on) n.delete(s.id); else n.add(s.id); return n })} />
              <span style={{ width: 12, height: 4, borderRadius: 2, background: s.cor, flex: 'none' }} />
              {s.rotulo}
              <span style={{ color: 'var(--ink-3)', fontVariantNumeric: 'tabular-nums' }}>{s.n}</span>
            </label>
          )
        })}
      {sobre.camadas.length === 0 && (
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
          Camadas temáticas (sondagens, marcos, interferências) chegam pela Prancheta — em breve.
        </span>
      )}
    </div>
  ) : null

  return (
    <>
      <AvisoDeProvedores status={status} quais={['geocodificacao_endereco']} />

      {/* Planilha de endereços: sai no tipo escolhido; entra só local novo (a cascata geocodifica). */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginBottom: 10 }}>
        <BotaoExportar recurso="maps.local" recorte={{ tipo: tipo || undefined }} />
        <WizardImportacao recurso="maps.local" onConcluida={() => qcPlanilha.invalidateQueries({ queryKey: ['maps', 'locais'] })} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(190px,1fr))', gap: 12, marginBottom: 14 }}>
        <KpiTile label="Locais no território" valor={<Num>{resumo.total}</Num>} base="obras, fornecedores, almoxarifados" />
        <KpiTile label="Com coordenada" valor={<Num>{resumo.com_coordenada}</Num>}
          base={semCoordenada ? `${semCoordenada} ainda sem` : 'todos localizados'} />
        <KpiTile label="Precisão de porta" valor={<Num>{resumo.por_precisao.exata ?? 0}</Num>} base="pin à mão ou EXIF" />
        <KpiTile label="Só no centro da cidade" valor={<Num>{resumo.por_precisao.municipio ?? 0}</Num>}
          base="precisão de município" />
      </div>

      {requer_decisao.length > 0 && (
        <Card style={{ marginBottom: 14 }}>
          <SectionHead right={<Pill kind="accent">{requer_decisao.length}</Pill>}>Requer decisão</SectionHead>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 8 }}>
            {requer_decisao.map((item) => {
              const destino = DESTINO_DA_PENDENCIA[item.tipo]?.(item.alvo) ?? null
              return (
                <button
                  key={`${item.tipo}-${item.alvo}`}
                  type="button"
                  disabled={!destino}
                  onClick={() => destino && ir(destino)}
                  title={destino ? 'Abrir o que falta resolver' : undefined}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px',
                    borderRadius: 9, background: 'var(--surface-2)', border: '1px solid var(--line)',
                    width: '100%', textAlign: 'left', font: 'inherit',
                    cursor: destino ? 'pointer' : 'default',
                  }}
                >
                  <AlertTriangle size={15} style={{ color: 'var(--accent-ink)', flex: 'none' }} />
                  <span style={{ fontSize: 13.5, color: 'var(--ink)', flex: 1 }}>{item.titulo}</span>
                  <Pill kind={item.tipo === 'sem_coordenada' ? 'danger' : 'accent'}>{item.quantidade}</Pill>
                  {destino && <ChevronRight size={15} style={{ color: 'var(--ink-3)', flex: 'none' }} />}
                </button>
              )
            })}
          </div>
        </Card>
      )}

      <MapaComPainel
        mapa={mapa}
        painel={
          <PainelDeLocais
            tipo={tipo} setTipo={setTipo} precisao={precisao} setPrecisao={setPrecisao}
            busca={busca} setBusca={setBusca}
            selecionado={selecionado}
            aoSelecionar={(l) => selecionar(l.local_id, l.ponto)}
            modo={modo} setModo={setModo}
            say={say}
          />
        }
        rodape={
          <LegendaDoMapa porTipo={resumo.por_tipo} tipoAtivo={tipo} aoEscolherTipo={setTipo} extra={legendaDeCamadas} />
        }
      />
    </>
  )
}

/**
 * O painel ao lado do mapa — a antiga aba "Locais", agora onde ela faz sentido.
 *
 * Mesmos filtros do mapa (o que a lista mostra é o que o mapa mostra), linha
 * clicável que enquadra o pin, e as ações do local escolhido: **posicionar o
 * pin à mão** (item 66), rodar a cascata, excluir o ponto avulso.
 */
function PainelDeLocais({
  tipo, setTipo, precisao, setPrecisao, busca, setBusca, selecionado, aoSelecionar, modo, setModo, say,
}: {
  tipo: string; setTipo: (v: string) => void
  precisao: string; setPrecisao: (v: string) => void
  busca: string; setBusca: (v: string) => void
  selecionado: number | null
  aoSelecionar: (l: Local) => void
  modo: Modo | null; setModo: (m: Modo | null) => void
  say: Say
}) {
  const [buscaDebounce, setBuscaDebounce] = useState(busca)
  useEffect(() => {
    const t = window.setTimeout(() => setBuscaDebounce(busca), 300)
    return () => window.clearTimeout(t)
  }, [busca])
  const params = {
    page_size: 200,
    ...(tipo ? { tipo } : {}), ...(precisao ? { precisao } : {}), ...(buscaDebounce.trim() ? { search: buscaDebounce.trim() } : {}),
  }
  const { data, isLoading } = useLocais(params)
  const geocodificar = useGeocodificar()
  const excluir = useExcluirLocal()
  const linhas = data?.results ?? []
  const filtrando = !!(tipo || precisao || busca)

  // O pin clicado no mapa traz a linha dele para a vista — senão, com centenas
  // de locais, a seleção acontecia lá embaixo e ninguém via.
  const refs = useRef<Record<number, HTMLDivElement | null>>({})
  useEffect(() => {
    if (selecionado != null) refs.current[selecionado]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selecionado, linhas.length])

  const rodarCascata = (local: Local, forcar = false) =>
    geocodificar.mutate({ id: local.local_id, forcar }, {
      onSuccess: (r) => say(r.geocodificado ? `Localizado: ${r.local.precisao_rotulo}` : r.motivo),
      onError: (e) => say(motivo(e, 'Não foi possível localizar agora. Tente de novo.')),
    })

  return (
    <>
      <div style={{ padding: 10, borderBottom: '1px solid var(--line)', display: 'grid', gap: 7 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <b style={{ fontFamily: 'var(--display)', fontSize: 14.5, color: 'var(--ink)', flex: 1 }}>
            Locais <span style={{ color: 'var(--ink-3)', fontWeight: 600, fontSize: 12.5 }}>{data ? data.count : ''}</span>
          </b>
          <Btn tam="sm" variant="primary" disabled={!!modo}
            onClick={() => setModo({ tipo: 'novo', nome: '', ponto: null })}
            title="Criar um ponto avulso clicando no mapa">
            <MapPinPlus size={13} /> Novo ponto
          </Btn>
        </div>
        <label style={{ position: 'relative', display: 'block' }}>
          <Search size={14} style={{ position: 'absolute', left: 9, top: 9, color: 'var(--ink-3)' }} />
          <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por nome, cidade…"
            style={{ ...inputEstilo, paddingLeft: 29 }} />
        </label>
        <div style={{ display: 'flex', gap: 6 }}>
          <select value={tipo} onChange={(e) => setTipo(e.target.value)} style={{ ...selectEstilo, flex: 1, minWidth: 0 }}>
            <option value="">Todos os tipos</option>
            {Object.entries(ROTULO_TIPO).map(([v, r]) => <option key={v} value={v}>{r}</option>)}
          </select>
          <select value={precisao} onChange={(e) => setPrecisao(e.target.value)} style={{ ...selectEstilo, flex: 1, minWidth: 0 }}>
            <option value="">Qualquer precisão</option>
            <option value="exata">Porta (pin/EXIF)</option>
            <option value="endereco">Endereço</option>
            <option value="cep">CEP</option>
            <option value="municipio">Centro da cidade</option>
            <option value="desconhecida">Sem coordenada</option>
          </select>
          {filtrando && (
            <Btn tam="sm" title="Limpar filtros" onClick={() => { setTipo(''); setPrecisao(''); setBusca('') }}><X size={13} /></Btn>
          )}
        </div>
        {modo?.tipo === 'novo' && (
          <div style={{ display: 'grid', gap: 6, padding: 9, borderRadius: 8, background: 'var(--accent-soft)' }}>
            <span style={{ fontSize: 12, color: 'var(--ink-2)' }}>Nome do novo ponto — depois clique no mapa onde ele fica.</span>
            <input autoFocus value={modo.nome} onChange={(e) => setModo({ ...modo, nome: e.target.value })}
              placeholder="Ex.: Portão de descarga, Jazida de areia" style={inputEstilo} maxLength={180} />
          </div>
        )}
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {isLoading ? <Loading o="os locais" /> : linhas.length === 0 ? (
          <div style={{ padding: 16 }}><Empty>Nada neste recorte.</Empty></div>
        ) : linhas.map((local) => {
          const on = local.local_id === selecionado
          return (
            <div key={local.local_id} ref={(el) => { refs.current[local.local_id] = el }}
              style={{ borderBottom: '1px solid var(--line-2)', background: on ? 'var(--surface-2)' : 'transparent' }}>
              <button type="button" onClick={() => aoSelecionar(local)}
                style={{ display: 'flex', alignItems: 'flex-start', gap: 9, width: '100%', padding: '9px 11px', textAlign: 'left', font: 'inherit', background: 'none', border: 'none', cursor: 'pointer' }}>
                <span style={{ width: 10, height: 10, borderRadius: '50%', background: COR_TIPO[local.tipo] ?? COR_TIPO.avulso, flex: 'none', marginTop: 4 }} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 13.5, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{local.nome}</span>
                  <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {[local.vinculo_rotulo, [local.cidade, local.uf].filter(Boolean).join(' - ')].filter(Boolean).join(' · ') || ROTULO_TIPO[local.tipo]}
                  </span>
                </span>
                <Pill kind={PRECISAO_KIND[local.precisao]}>{local.ponto ? local.precisao_rotulo.split(' (')[0] : 'sem pin'}</Pill>
              </button>

              {on && (
                <div style={{ padding: '0 11px 11px 30px', display: 'grid', gap: 7 }}>
                  <div style={{ fontSize: 12, color: 'var(--ink-3)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ color: 'var(--ink-3)', display: 'grid', placeItems: 'center' }}>{ICONE_TIPO[local.tipo] ?? ICONE_TIPO.avulso}</span>
                    {local.endereco_completo || 'Sem endereço cadastrado'}
                  </div>
                  <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                    {local.precisao_rotulo}{local.fonte_rotulo ? ` · ${local.fonte_rotulo}` : ''}
                  </div>
                  {local.unidade_detalhe && <DetalheDaUnidade u={local.unidade_detalhe} />}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    <Btn tam="sm" variant="primary" disabled={!!modo}
                      onClick={() => setModo({ tipo: 'posicionar', local, ponto: local.ponto })}
                      title="Arrastar o pin para o lugar certo — vira precisão exata">
                      <Move size={13} /> {local.ponto ? 'Mover pin' : 'Posicionar pin'}
                    </Btn>
                    {/* **Localizar ≠ posicionar.** Localizar roda a cascata (endereço →
                        CEP → município); só aparece onde ela tem o que fazer. Pin
                        `exata` não ganha "Refazer": é verdade de campo. */}
                    {!local.ponto && (
                      <Btn tam="sm" onClick={() => rodarCascata(local)}><Crosshair size={13} /> Localizar pelo endereço</Btn>
                    )}
                    {local.ponto && local.precisao !== 'exata' && (
                      <Btn tam="sm" onClick={() => rodarCascata(local, true)} title="Rodar a cascata de novo — pode refinar a precisão">
                        <RefreshCw size={13} /> Refazer
                      </Btn>
                    )}
                    {local.tipo === 'avulso' && (
                      <Btn tam="sm" title="Excluir este ponto avulso"
                        onClick={() => {
                          if (!window.confirm(`Excluir o ponto "${local.nome}"?`)) return
                          excluir.mutate(local.local_id, {
                            onSuccess: () => say(`Ponto "${local.nome}" excluído.`),
                            onError: (e) => say(motivo(e, 'Não foi possível excluir.')),
                          })
                        }}>
                        <Trash2 size={13} />
                      </Btn>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </>
  )
}

/**
 * O que um lote é, no mapa: medidas, divisas e a rua da frente.
 *
 * Área não descreve terreno — o que vai ao contrato, à matrícula e à conversa
 * com o vizinho é *quanto mede cada lado* e *com quem cada lado divide*, e o
 * lado da frente é a rua, de onde sai o endereço.
 *
 * A pílula da rua tem três estados, e o terceiro é o que evita o alarme falso:
 * bate, **não bate**, e "não dá para dizer" — este último quando falta o
 * confrontante ou falta o endereço. Cadastro incompleto não é cadastro errado.
 */
function DetalheDaUnidade({ u }: { u: UnidadeDetalhe }) {
  const areas = [
    u.area_privativa && `${Number(u.area_privativa).toLocaleString('pt-BR')} m² privativos`,
    u.area_total && `${Number(u.area_total).toLocaleString('pt-BR')} m² totais`,
  ].filter(Boolean).join(' · ')

  return (
    <div style={{ display: 'grid', gap: 3 }}>
      {areas && <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{areas}</div>}

      {u.confrontacoes.length === 0 ? (
        <div style={{ fontSize: 11.5, color: 'var(--ink-3)', fontStyle: 'italic' }}>
          Sem medidas nem confrontações — o memorial descritivo desta unidade ainda
          não existe no cadastro.
        </div>
      ) : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {u.confrontacoes.map((c) => (
            <span
              key={c.lado}
              title={`${c.rotulo}${c.medida ? ` — ${Number(c.medida).toLocaleString('pt-BR')} m` : ''}`
                + `${c.confrontante ? `, com ${c.confrontante}` : ''}`}
              style={{
                display: 'inline-flex', alignItems: 'baseline', gap: 5, padding: '2px 8px',
                borderRadius: 999, border: '1px solid var(--line)', background: 'var(--surface)',
                fontSize: 11, color: 'var(--ink-2)', maxWidth: 260,
              }}
            >
              <b style={{ color: 'var(--ink-3)', fontWeight: 700 }}>{c.rotulo}</b>
              {c.medida && (
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {Number(c.medida).toLocaleString('pt-BR')} m
                </span>
              )}
              {c.confrontante && (
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {c.confrontante}
                </span>
              )}
            </span>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
          Frente: {u.rua || '— sem rua cadastrada —'}
        </span>
        {u.rua_confere === true && <Pill kind="good">rua confere com o endereço</Pill>}
        {u.rua_confere === false && (
          <Pill kind="danger" title={`Endereço cadastrado: ${u.endereco || '(vazio)'}`}>
            rua diferente do endereço
          </Pill>
        )}
        {u.rua_confere === null && <Pill kind="slate">sem como conferir a rua</Pill>}
      </div>
    </div>
  )
}

/* ═══════════ Vizinhança — "o que está perto de quê" ═══════════ */
export function Vizinhanca({ say }: { say: Say }) {
  const { data: lista } = useLocais({ page_size: 200 })
  const [origem, setOrigem] = useState<number | null>(null)
  const [raio, setRaio] = useState(50)
  const [tipo, setTipo] = useState('fornecedor')
  const { data, isFetching } = useProximos(origem, raio, tipo || undefined)

  const comCoordenada = (lista?.results ?? []).filter((l) => l.ponto)
  const pontos = useMemo(() => (data ? paraPontos([data.origem, ...data.resultados]) : []), [data])

  return (
    <Card>
      <SectionHead sub="Enquanto o endereço era texto livre, isto era impossível. Com coordenada, o SCM decide por preço, reputação e distância.">
        Vizinhança
      </SectionHead>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14, alignItems: 'center' }}>
        <select value={origem ?? ''} onChange={(e) => setOrigem(Number(e.target.value) || null)}
          style={{ ...selectEstilo, minWidth: 220 }}>
          <option value="">A partir de…</option>
          {comCoordenada.map((l) => <option key={l.local_id} value={l.local_id}>{l.nome}</option>)}
        </select>
        <select value={tipo} onChange={(e) => setTipo(e.target.value)} style={selectEstilo}>
          <option value="">Qualquer tipo</option>
          <option value="fornecedor">Fornecedores</option>
          <option value="local_estoque">Almoxarifados</option>
          <option value="obra">Obras</option>
        </select>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 9, fontSize: 13, color: 'var(--ink-2)' }}>
          <Radar size={15} style={{ color: 'var(--ink-3)' }} />
          <input type="range" min={5} max={300} step={5} value={raio}
            onChange={(e) => setRaio(Number(e.target.value))} style={{ width: 150 }} />
          <Num size={13}>{`${raio} km`}</Num>
        </label>
      </div>

      {!origem ? (
        <Empty>Escolha um ponto de partida — a vizinhança é sempre relativa a um local com coordenada.</Empty>
      ) : isFetching ? (
        <Loading o="a vizinhança" />
      ) : (
        <>
          <Mapa pontos={pontos} altura={380} />
          <div style={{ marginTop: 12 }}>
            {(data?.resultados ?? []).length === 0 ? (
              <Empty>{`Nada num raio de ${raio} km.`}</Empty>
            ) : (
              (data?.resultados ?? []).map((r) => (
                <div key={r.local_id}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 4px', borderTop: '1px solid var(--line-2)' }}>
                  <span style={{ color: 'var(--ink-3)', display: 'grid', placeItems: 'center' }}>
                    {ICONE_TIPO[r.tipo] ?? ICONE_TIPO.avulso}
                  </span>
                  <span style={{ fontSize: 13.5, color: 'var(--ink)', flex: 1 }}>{r.nome}</span>
                  <Pill kind={PRECISAO_KIND[r.precisao]}>{r.precisao_rotulo}</Pill>
                  <Num size={13} tone="var(--accent-ink)" style={{ minWidth: 74 }}>
                    {r.distancia_km != null ? `${r.distancia_km} km` : '—'}
                  </Num>
                  <Btn tam="sm" onClick={() => say(`${r.nome} — ${r.distancia_km} km de ${data?.origem.nome}`)}>
                    <Navigation size={13} />
                  </Btn>
                </div>
              ))
            )}
          </div>
        </>
      )}
    </Card>
  )
}
