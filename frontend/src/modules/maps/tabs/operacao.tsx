import { useMemo, useState } from 'react'
import {
  AlertTriangle, ChevronRight, Crosshair, Eye, MapPin, Navigation, Radar, RefreshCw,
  Building2, HardHat, Truck, Warehouse,
} from 'lucide-react'
import { Btn, Card, Empty, KpiTile, Loading, Mapa, Num, Pill, SectionHead } from '@/components/malha'
import type { PillKind, PontoMapa } from '@/components/malha'
import { useGeocodificar, useLocais, useMapa, useProximos } from '../hooks'
import type { Destino, Ir, Local, LocalResumo, Precisao, UnidadeDetalhe } from '../types'

export type Say = (mensagem: string) => void

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

const selectEstilo: React.CSSProperties = {
  padding: '7px 11px', borderRadius: 8, border: '1px solid var(--line)',
  background: 'var(--surface)', color: 'var(--ink)', fontSize: 13,
}

/**
 * Para onde cada pendência da fila leva — o que transforma o cartaz em fila.
 *
 * Cada `tipo` que o backend emite em `requer_decisao` tem aqui o seu destino, e
 * o destino é **o lugar onde a pendência se resolve**, já filtrado: "12 obras
 * sem coordenada" abre a tabela de locais mostrando só as 12, não a lista
 * inteira para a pessoa refazer o filtro na mão. O que não tiver destino
 * declarado continua legível e simplesmente não clica — é melhor que um clique
 * que leva ao lugar errado.
 */
const DESTINO_DA_PENDENCIA: Record<string, (alvo: string) => Destino | null> = {
  sem_coordenada: (alvo) => ({ tab: 'locais', filtro: { tipo: alvo, precisao: 'desconhecida' } }),
  precisao_grosseira: () => ({ tab: 'locais', filtro: { precisao: 'municipio' } }),
  rua_divergente: () => ({ tab: 'locais', filtro: { tipo: 'unidade' } }),
  ortofoto_vencida: () => ({ tab: 'acervo' }),
  voo_sem_autorizacao: () => ({ tab: 'voos' }),
}

/* ═══════════ Mapa da empresa + fila de decisão ═══════════ */
export function MapaDaEmpresa({ say, ir, foco = null }: {
  say: Say; ir: Ir; foco?: { lon: number; lat: number } | null
}) {
  const { data, isLoading } = useMapa()
  const [satelite, setSatelite] = useState(false)
  const geocodificar = useGeocodificar()

  const pontos = useMemo(() => paraPontos(data?.locais ?? []), [data])
  if (isLoading) return <Loading o="o mapa da empresa" />
  if (!data) return <Empty>Não foi possível carregar o mapa.</Empty>

  const { resumo, requer_decisao } = data
  const semCoordenada = resumo.total - resumo.com_coordenada

  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(190px,1fr))', gap: 12, marginBottom: 18 }}>
        <KpiTile label="Locais no território" valor={<Num>{resumo.total}</Num>} base="obras, fornecedores, almoxarifados" />
        <KpiTile label="Com coordenada" valor={<Num>{resumo.com_coordenada}</Num>}
          base={semCoordenada ? `${semCoordenada} ainda sem` : 'todos localizados'} />
        <KpiTile label="Precisão de porta" valor={<Num>{resumo.por_precisao.exata ?? 0}</Num>} base="pin à mão ou EXIF" />
        <KpiTile label="Só no centro da cidade" valor={<Num>{resumo.por_precisao.municipio ?? 0}</Num>}
          base="precisão de município" />
      </div>

      {requer_decisao.length > 0 && (
        <Card style={{ marginBottom: 18 }}>
          <SectionHead right={<Pill kind="accent">{requer_decisao.length}</Pill>}>Requer decisão</SectionHead>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
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

      <Card>
        <SectionHead
          sub="O halo cresce com a incerteza — pin firme é porta, mancha larga é cidade."
          right={<Btn onClick={() => setSatelite((s) => !s)}>{satelite ? 'Mapa' : 'Satélite'}</Btn>}
        >
          Mapa da empresa
        </SectionHead>
        {pontos.length === 0 ? (
          <Empty>
            Nenhum local com coordenada ainda. Rode o georreferenciamento dos cadastros
            (obras, fornecedores, almoxarifados) ou posicione o primeiro pin à mão.
          </Empty>
        ) : (
          <>
            <Mapa pontos={pontos} altura={470} satelite={satelite} foco={foco}
              onSelecionar={(id) => {
                const local = data.locais.find((l) => String(l.local_id) === String(id))
                if (local) say(`${local.nome} — ${local.precisao_rotulo}`)
              }} />
            <Legenda />
          </>
        )}
      </Card>

      {semCoordenada > 0 && (
        <Card style={{ marginTop: 16 }}>
          <SectionHead sub="A cascata tenta endereço → CEP → município. Se nenhum degrau resolver, o pin fica com você.">
            Sem coordenada
          </SectionHead>
          <ListaDeLocais
            filtro={{ precisao: 'desconhecida' }}
            aoGeocodificar={(id, forcar) =>
              geocodificar.mutate({ id, forcar }, {
                onSuccess: (r) => say(r.geocodificado ? `Localizado: ${r.local.precisao_rotulo}` : r.motivo),
                onError: () => say('Não deu para localizar agora — tente de novo em instantes.'),
              })
            }
          />
        </Card>
      )}
    </>
  )
}

function Legenda() {
  const escala: Array<[Precisao, string, number]> = [
    ['exata', 'Porta (pin/EXIF)', 8],
    ['endereco', 'Endereço', 12],
    ['cep', 'CEP', 16],
    ['municipio', 'Centro da cidade', 21],
  ]
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 14, marginTop: 12, fontSize: 11.5, color: 'var(--ink-3)' }}>
      <span style={{ fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' }}>Precisão</span>
      {escala.map(([chave, rotulo, tamanho]) => (
        <span key={chave} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            width: tamanho, height: tamanho, borderRadius: '50%', background: 'var(--ink-3)',
            opacity: chave === 'exata' ? 0.85 : 0.25, flex: 'none',
          }} />
          {rotulo}
        </span>
      ))}
    </div>
  )
}

/* ═══════════ Locais (tabela) ═══════════ */
export function Locais({ say, ir, filtroInicial }: {
  say: Say; ir: Ir; filtroInicial?: Record<string, string>
}) {
  // O tipo nasce do que a fila de decisão pediu: chegar aqui por "12 obras sem
  // coordenada" e encontrar o seletor em "Todos os tipos" obrigaria a pessoa a
  // refazer à mão o filtro que ela acabou de clicar.
  const [tipo, setTipo] = useState(filtroInicial?.tipo ?? '')
  const [precisao, setPrecisao] = useState(filtroInicial?.precisao ?? '')
  const geocodificar = useGeocodificar()

  const filtro = { ...(tipo ? { tipo } : {}), ...(precisao ? { precisao } : {}) }
  const filtrando = !!(tipo || precisao)

  return (
    <Card>
      <SectionHead
        sub={filtrando ? 'Recorte pedido pela fila de decisão.' : undefined}
        right={
          <div style={{ display: 'flex', gap: 7, alignItems: 'center', flexWrap: 'wrap' }}>
            <select value={tipo} onChange={(e) => setTipo(e.target.value)} style={selectEstilo}>
              <option value="">Todos os tipos</option>
              <option value="obra">Obras</option>
              <option value="empreendimento">Empreendimentos</option>
              <option value="fornecedor">Fornecedores</option>
              <option value="local_estoque">Almoxarifados</option>
              {/* Faltava: os lotes e apartamentos entram no mapa como `unidade`,
                  mas o seletor não os oferecia — o filtro que a fila de decisão
                  pede ao clicar em "rua divergente" não existia na tela. */}
              <option value="unidade">Unidades (lotes)</option>
              <option value="avulso">Avulsos</option>
            </select>
            <select value={precisao} onChange={(e) => setPrecisao(e.target.value)} style={selectEstilo}>
              <option value="">Qualquer precisão</option>
              <option value="exata">Porta (pin/EXIF)</option>
              <option value="endereco">Endereço</option>
              <option value="cep">CEP</option>
              <option value="municipio">Centro da cidade</option>
              <option value="desconhecida">Sem coordenada</option>
            </select>
            {filtrando && (
              <Btn tam="sm" onClick={() => { setTipo(''); setPrecisao('') }}>Limpar</Btn>
            )}
          </div>
        }
      >
        Locais
      </SectionHead>
      <ListaDeLocais
        filtro={filtro}
        aoVerNoMapa={(local) =>
          ir({ tab: 'mapa', foco: { lon: local.ponto!.lon, lat: local.ponto!.lat } })
        }
        aoGeocodificar={(id, forcar) =>
          geocodificar.mutate({ id, forcar }, {
            onSuccess: (r) => say(r.geocodificado ? `Localizado: ${r.local.precisao_rotulo}` : r.motivo),
            // Sem isto, um 403/500 no `geocodificar/` era silêncio absoluto —
            // o clique não mudava a tabela nem dizia nada, e o botão parecia
            // morto. Falha que não fala é indistinguível de botão quebrado.
            onError: () => say('Não deu para localizar agora — tente de novo em instantes.'),
          })
        }
      />
    </Card>
  )
}

function ListaDeLocais({
  filtro, aoGeocodificar, aoVerNoMapa,
}: {
  filtro?: Record<string, unknown>
  aoGeocodificar: (id: number, forcar?: boolean) => void
  aoVerNoMapa?: (local: Local) => void
}) {
  const { data, isLoading } = useLocais({ page_size: 100, ...(filtro ?? {}) })
  if (isLoading) return <Loading o="os locais" />
  const linhas = data?.results ?? []
  if (!linhas.length) return <Empty>Nada por aqui.</Empty>

  const th: React.CSSProperties = {
    padding: '8px 10px', textAlign: 'left', color: 'var(--ink-3)', fontSize: 11,
    textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700,
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
        <thead>
          <tr>
            <th style={th}>Local</th>
            <th style={th}>Cidade</th>
            <th style={th}>Precisão</th>
            <th style={th}>Procedência</th>
            <th style={th} />
          </tr>
        </thead>
        <tbody>
          {linhas.map((local) => (
            <tr key={local.local_id} style={{ borderTop: '1px solid var(--line-2)' }}>
              <td style={{ padding: '9px 10px' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, color: 'var(--ink)' }}>
                  <span style={{ color: 'var(--ink-3)', display: 'grid', placeItems: 'center' }}>
                    {ICONE_TIPO[local.tipo] ?? ICONE_TIPO.avulso}
                  </span>
                  {local.nome}
                </span>
                {local.vinculo_rotulo && (
                  <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginLeft: 21 }}>{local.vinculo_rotulo}</div>
                )}
                {local.unidade_detalhe && <DetalheDaUnidade u={local.unidade_detalhe} />}
              </td>
              <td style={{ padding: '9px 10px', color: 'var(--ink-2)' }}>
                {[local.cidade, local.uf].filter(Boolean).join(' - ') || '—'}
              </td>
              <td style={{ padding: '9px 10px' }}>
                <Pill kind={PRECISAO_KIND[local.precisao]}>{local.precisao_rotulo}</Pill>
              </td>
              <td style={{ padding: '9px 10px', color: 'var(--ink-3)', fontSize: 12.5 }}>
                {local.fonte_rotulo || '—'}
              </td>
              {/**
                * **O que "Localizar" faz depende do estado do local, e antes não
                * dependia.** O botão era um só e chamava sempre a cascata; num
                * local que já tinha coordenada o backend respondia, corretamente,
                * "já tem coordenada — use ?forcar=1", e a tela mostrava um aviso
                * que não mudava nada. Para quem clicou querendo VER onde o local
                * está, isso é um botão que não faz nada.
                *
                * São dois gestos diferentes e agora são dois botões:
                * **Ver** enquadra o pin no mapa (sempre funciona, e é o que a
                * palavra "localizar" sugeria), e **Localizar/Refazer** roda a
                * cascata — só aparece onde ela tem o que fazer. Pin `exata` não
                * ganha o segundo: é verdade de campo, e nenhum provedor a desfaz.
                */}
              <td style={{ padding: '9px 10px', textAlign: 'right' }}>
                <div style={{ display: 'inline-flex', gap: 6, justifyContent: 'flex-end' }}>
                  {local.ponto && aoVerNoMapa && (
                    <Btn tam="sm" onClick={() => aoVerNoMapa(local)} title="Enquadrar no mapa da empresa">
                      <Eye size={13} /> Ver
                    </Btn>
                  )}
                  {!local.ponto && (
                    <Btn tam="sm" onClick={() => aoGeocodificar(local.local_id)}>
                      <Crosshair size={13} /> Localizar
                    </Btn>
                  )}
                  {local.ponto && local.precisao !== 'exata' && (
                    <Btn tam="sm" onClick={() => aoGeocodificar(local.local_id, true)}
                      title="Rodar a cascata de novo — pode refinar a precisão">
                      <RefreshCw size={13} /> Refazer
                    </Btn>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * O que um lote é, no mapa: medidas, divisas e a rua da frente.
 *
 * **O que faltava:** a unidade chegava aqui com área e mais nada. Área não
 * descreve terreno — o que vai ao contrato, à matrícula e à conversa com o
 * vizinho é *quanto mede cada lado* e *com quem cada lado divide*, e o lado da
 * frente é a rua, de onde sai o endereço. O cadastro já guardava tudo isso
 * (`empreendimentos.Unidade`); o mapa é que não mostrava.
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
    <div style={{ marginLeft: 21, marginTop: 4, display: 'grid', gap: 3 }}>
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
                borderRadius: 999, border: '1px solid var(--line)', background: 'var(--surface-2)',
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
