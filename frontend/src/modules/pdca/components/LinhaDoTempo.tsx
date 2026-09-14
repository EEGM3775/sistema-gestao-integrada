import { useMemo, useState } from 'react'
import { ALTURA_BARRA, ALTURA_CABECALHO, ALTURA_LINHA } from '../medidas'
import {
  daIso, diasEntre, fimDeSemana, hojeIso, marcacoes, paraIso, rotuloFolga, somarDias, tracarSetas,
  type ChaveEscala, type EixoDoTempo, type LinhaDaArvore,
} from '../lib'
import type {
  Atividade, AvancoDaAtividade, LinhaDaBase, Precedencia, TipoPrecedencia,
} from '../types'

/** O gesto em curso. Um estado só, e não quatro booleanos, porque os quatro são
 *  mutuamente exclusivos: quem está esticando uma barra não está ligando outra,
 *  e a combinação impossível não deve nem ser representável. */
type Gesto =
  | { tipo: 'nenhum' }
  | { tipo: 'mover'; id: number; xInicial: number; dx: number }
  | { tipo: 'esticar'; id: number; xInicial: number; dx: number }
  | { tipo: 'ligar'; origem: number; x: number; y: number; alvo: number | null }

interface Props {
  linhas: LinhaDaArvore[]
  janela: { inicio: number; fim: number }
  eixo: EixoDoTempo
  escala: ChaveEscala
  precedencias: Precedencia[]
  porId: Map<number, Atividade>
  linhaDe: Map<number, number>
  base: Map<string, LinhaDaBase>
  /** PDCA.2 — quanto de cada atividade já foi apontado. É o preenchimento
   *  dentro da barra, no molde do "% concluído" do MS Project: a barra é o
   *  previsto, e o que está dentro dela é o que a obra respondeu. */
  avanco: Record<string, AvancoDaAtividade>
  mostrarBase: boolean
  mostrarFolga: boolean
  mostrarNomes: boolean
  editavel: boolean
  selecionadas: ReadonlySet<number>
  /** Quando existe, é a cadeia da atividade selecionada: o que está fora dela
   *  perde contraste. `null` = sem realce, tudo com o mesmo peso. */
  cadeia: ReadonlySet<number> | null
  onSelecionar: (id: number, modo: 'unica' | 'alternar') => void
  onAbrir: (id: number) => void
  onReprogramar: (id: number, payload: { nao_comecar_antes_de?: string | null; duracao_dias?: number }) => void
  onLigar: (origem: number, destino: number, tipo: TipoPrecedencia) => void
  onExcluirPrecedencia: (id: number) => void
}

export default function LinhaDoTempo({
  linhas, janela, eixo, escala, precedencias, porId, linhaDe, base, avanco, mostrarBase,
  mostrarFolga, mostrarNomes, editavel, selecionadas, cadeia, onSelecionar, onAbrir,
  onReprogramar, onLigar, onExcluirPrecedencia,
}: Props) {
  const [gesto, setGesto] = useState<Gesto>({ tipo: 'nenhum' })

  const alturaTotal = linhas.length * ALTURA_LINHA
  const setas = useMemo(
    () => tracarSetas(precedencias, linhaDe, porId, eixo, ALTURA_LINHA, ALTURA_BARRA),
    [precedencias, linhaDe, porId, eixo],
  )
  const faixas = useMemo(() => fimDeSemana(eixo, escala), [eixo, escala])
  const marcas = useMemo(() => marcacoes(eixo, escala), [eixo, escala])
  const xHoje = useMemo(() => {
    const hoje = hojeIso()
    return hoje >= paraIso(eixo.origem) && hoje <= paraIso(eixo.fim) ? eixo.x(hoje) : null
  }, [eixo])

  /**
   * A coordenada do ponteiro **no espaço do SVG**, e não no do elemento clicado.
   *
   * Os gestos começam em elementos próprios — a barra, a alça de esticar, o
   * ponto de ligação — e terminam no `onPointerMove` do SVG inteiro. Medir cada
   * um contra a caixa do seu elemento daria um zero diferente para o início e
   * para o fim do mesmo gesto, e o arrasto sairia deslocado pela distância da
   * barra até a origem do plano: quanto mais tarde a atividade, maior o erro.
   */
  const posicao = (evento: React.PointerEvent<Element>) => {
    const alvo = evento.currentTarget as SVGElement
    const svg = (alvo as SVGGraphicsElement).ownerSVGElement ?? (alvo as SVGSVGElement)
    const caixa = svg.getBoundingClientRect()
    return { x: evento.clientX - caixa.left, y: evento.clientY - caixa.top }
  }

  const aoMover = (evento: React.PointerEvent<SVGSVGElement>) => {
    if (gesto.tipo === 'nenhum') return
    const { x, y } = posicao(evento)
    if (gesto.tipo === 'mover' || gesto.tipo === 'esticar') {
      setGesto({ ...gesto, dx: x - gesto.xInicial })
      return
    }
    const linha = linhas[Math.floor(y / ALTURA_LINHA)]
    const alvo = linha && !linha.temFilhos && linha.atividade.atividade_id !== gesto.origem
      ? linha.atividade.atividade_id
      : null
    setGesto({ ...gesto, x, y, alvo })
  }

  /** Soltar não move a barra: manda o **pedido** e deixa o CPM decidir. A barra
   *  pode voltar para trás porque uma predecessora não permite — e ver isso
   *  acontecer é a diferença entre um cronograma e uma tela de desenho. */
  const aoSoltar = () => {
    if (gesto.tipo === 'mover') {
      const a = porId.get(gesto.id)
      const passos = Math.round(gesto.dx / eixo.pxPorDia)
      if (a?.inicio_cedo && passos !== 0) {
        onReprogramar(gesto.id, { nao_comecar_antes_de: paraIso(somarDias(daIso(a.inicio_cedo), passos)) })
      }
    } else if (gesto.tipo === 'esticar') {
      const a = porId.get(gesto.id)
      const passos = Math.round(gesto.dx / eixo.pxPorDia)
      if (a && !a.eh_marco && passos !== 0) {
        onReprogramar(gesto.id, { duracao_dias: Math.max((a.duracao_dias ?? 1) + passos, 1) })
      }
    } else if (gesto.tipo === 'ligar' && gesto.alvo != null) {
      onLigar(gesto.origem, gesto.alvo, 'FS')
    }
    setGesto({ tipo: 'nenhum' })
  }

  const geometria = (a: Atividade) => {
    if (!a.inicio_cedo) return null
    const inicio = eixo.x(a.inicio_cedo)
    const fim = a.termino_cedo ?? a.inicio_cedo
    const largura = a.eh_marco
      ? eixo.pxPorDia
      : Math.max((diasEntre(daIso(a.inicio_cedo), daIso(fim)) + 1) * eixo.pxPorDia, 3)
    let deslocamento = 0
    let extra = 0
    if (gesto.tipo === 'mover' && gesto.id === a.atividade_id) deslocamento = gesto.dx
    if (gesto.tipo === 'esticar' && gesto.id === a.atividade_id) extra = gesto.dx
    return { x: inicio + deslocamento, largura: Math.max(largura + extra, 3) }
  }

  const cor = (a: Atividade) =>
    a.tem_filhos ? 'var(--ink-3)' : a.critica ? 'var(--danger)' : 'var(--brand)'

  /** Fora da cadeia realçada a barra continua desenhada, só que apagada: sumir
   *  com ela faria a rolagem parecer quebrada, e o planejador precisa ver o
   *  contexto de onde a corrente passa. */
  const opacidadeDe = (a: Atividade) =>
    !cadeia || cadeia.has(a.atividade_id) ? 1 : 0.2

  const visiveis = linhas.slice(janela.inicio, janela.fim + 1)

  return (
    <div style={{ width: eixo.largura, position: 'relative' }}>
      <div style={{
        height: ALTURA_CABECALHO, position: 'sticky', top: 0, zIndex: 2,
        background: 'var(--inset)', borderBottom: '1px solid var(--line)',
      }}>
        <svg width={eixo.largura} height={ALTURA_CABECALHO} style={{ display: 'block' }}>
          {faixas.map((f, i) => (
            <rect key={i} x={f.x} y={0} width={f.largura} height={ALTURA_CABECALHO} fill="var(--surface-2)" />
          ))}
          {marcas.map((m, i) => (
            <g key={i}>
              <line x1={m.x} y1={ALTURA_CABECALHO - 10} x2={m.x} y2={ALTURA_CABECALHO}
                stroke="var(--line)" strokeWidth={m.forte ? 1.4 : 0.6} />
              <text x={m.x + 3} y={ALTURA_CABECALHO - 14} fontSize={10}
                fill={m.forte ? 'var(--ink-2)' : 'var(--ink-3)'} fontWeight={m.forte ? 600 : 400}>
                {m.rotulo}
              </text>
            </g>
          ))}
          {xHoje != null && (
            <g>
              <line x1={xHoje} y1={0} x2={xHoje} y2={ALTURA_CABECALHO} stroke="var(--accent)" strokeWidth={1.5} />
              <text x={xHoje + 4} y={12} fontSize={9.5} fontWeight={700} fill="var(--accent)">HOJE</text>
            </g>
          )}
        </svg>
      </div>

      <svg
        width={eixo.largura}
        height={alturaTotal}
        data-gantt="linha-do-tempo"
        style={{ display: 'block', touchAction: 'none' }}
        onPointerMove={aoMover}
        onPointerUp={aoSoltar}
        onPointerLeave={() => gesto.tipo !== 'nenhum' && setGesto({ tipo: 'nenhum' })}
      >
        <defs>
          <marker id="pdca-seta" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <path d="M0,0 L7,3.5 L0,7 Z" fill="var(--ink-3)" />
          </marker>
          <marker id="pdca-seta-critica" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <path d="M0,0 L7,3.5 L0,7 Z" fill="var(--danger)" />
          </marker>
          <pattern id="pdca-folga" width="5" height="5" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
            <line x1="0" y1="0" x2="0" y2="5" stroke="var(--ink-3)" strokeWidth="1.4" opacity="0.5" />
          </pattern>
        </defs>

        {faixas.map((f, i) => (
          <rect key={i} x={f.x} y={0} width={f.largura} height={alturaTotal} fill="var(--inset)" opacity={0.55} />
        ))}
        {marcas.filter(m => m.forte).map((m, i) => (
          <line key={i} x1={m.x} y1={0} x2={m.x} y2={alturaTotal} stroke="var(--line)" strokeWidth={1} />
        ))}
        {xHoje != null && (
          <line x1={xHoje} y1={0} x2={xHoje} y2={alturaTotal} stroke="var(--accent)" strokeWidth={1.5} opacity={0.75} />
        )}

        {setas.map(s => {
          const l1 = linhaDe.get(s.precedencia.origem) ?? 0
          const l2 = linhaDe.get(s.precedencia.destino) ?? 0
          if (Math.max(l1, l2) < janela.inicio - 40 || Math.min(l1, l2) > janela.fim + 40) return null
          const naCadeia = !cadeia || (cadeia.has(s.precedencia.origem) && cadeia.has(s.precedencia.destino))
          const atraso = s.precedencia.atraso_dias
          return (
            <g key={s.precedencia.precedencia_id} opacity={naCadeia ? 1 : 0.15}>
              <path
                d={s.caminho} fill="none"
                stroke={s.critica ? 'var(--danger)' : 'var(--ink-3)'}
                strokeWidth={s.critica ? 1.6 : 1}
                opacity={s.critica ? 0.9 : 0.55}
                markerEnd={s.critica ? 'url(#pdca-seta-critica)' : 'url(#pdca-seta)'}
                style={{ cursor: editavel ? 'pointer' : 'default' }}
                onClick={() => editavel && onExcluirPrecedencia(s.precedencia.precedencia_id)}
              >
                <title>
                  {`${s.precedencia.origem_codigo} → ${s.precedencia.destino_codigo} · ${s.precedencia.tipo_rotulo}`
                    + (atraso ? ` · ${atraso > 0 ? '+' : ''}${atraso} d` : '')
                    + (editavel ? ' — clique para remover' : '')}
                </title>
              </path>
              {/* O tipo e o atraso desenhados na seta: sem eles, um FS e um SS
                  com 5 dias de defasagem são o mesmo traço na tela. */}
              {(s.precedencia.tipo !== 'FS' || atraso !== 0) && eixo.pxPorDia > 4 && (
                <text
                  x={s.meio.x} y={s.meio.y - 3} fontSize={9} textAnchor="middle"
                  fill={s.critica ? 'var(--danger)' : 'var(--ink-3)'} fontWeight={600}
                  pointerEvents="none"
                >
                  {s.precedencia.tipo !== 'FS' ? s.precedencia.tipo : ''}
                  {atraso ? `${atraso > 0 ? '+' : ''}${atraso}d` : ''}
                </text>
              )}
            </g>
          )
        })}

        {visiveis.map((linha, i) => {
          const indice = janela.inicio + i
          const a = linha.atividade
          const geo = geometria(a)
          if (!geo) return null
          const y = indice * ALTURA_LINHA + (ALTURA_LINHA - ALTURA_BARRA) / 2
          const daBase = mostrarBase ? base.get(a.codigo) : undefined
          const arrastavel = editavel && !linha.temFilhos
          const arrastando = gesto.tipo !== 'nenhum' && 'id' in gesto && gesto.id === a.atividade_id

          return (
            <g key={a.atividade_id} opacity={opacidadeDe(a)}>
              {selecionadas.has(a.atividade_id) && (
                <rect x={0} y={indice * ALTURA_LINHA} width={eixo.largura} height={ALTURA_LINHA}
                  fill="var(--brand)" opacity={0.07} />
              )}

              {/* A folga total como faixa hachurada depois da barra: é o quanto a
                  atividade escorrega sem empurrar o fim da obra, e sem ela a
                  leitura "esta é crítica" fica sem contraponto visível. */}
              {mostrarFolga && !linha.temFilhos && !a.critica && (a.folga_total ?? 0) > 0 && (
                <rect
                  x={geo.x + geo.largura} y={y + ALTURA_BARRA / 2 - 3}
                  width={Math.max((a.folga_total as number) * eixo.pxPorDia, 2)} height={6} rx={2}
                  fill="url(#pdca-folga)"
                >
                  <title>{(a.folga_total as number) + ' dias de folga total'}</title>
                </rect>
              )}

              {daBase?.base_inicio && (
                <rect
                  x={eixo.x(daBase.base_inicio)}
                  y={y + ALTURA_BARRA - 3}
                  width={Math.max(
                    (diasEntre(daIso(daBase.base_inicio), daIso(daBase.base_termino ?? daBase.base_inicio)) + 1) * eixo.pxPorDia, 3,
                  )}
                  height={5} rx={2} fill="var(--ink-3)" opacity={0.35}
                >
                  <title>{'Linha de base: ' + curta(daBase.base_inicio) + ' a ' + curta(daBase.base_termino)}</title>
                </rect>
              )}

              {a.eh_marco ? (
                <polygon
                  points={losango(geo.x + eixo.pxPorDia / 2, y + ALTURA_BARRA / 2, ALTURA_BARRA / 1.5)}
                  fill={a.critica ? 'var(--danger)' : 'var(--accent)'}
                  stroke="var(--surface)" strokeWidth={1}
                  style={{ cursor: arrastavel ? 'grab' : 'pointer' }}
                  onDoubleClick={() => onAbrir(a.atividade_id)}
                  onPointerDown={e => {
                    onSelecionar(a.atividade_id, e.ctrlKey || e.metaKey ? 'alternar' : 'unica')
                    if (!arrastavel) return
                    e.currentTarget.ownerSVGElement?.setPointerCapture(e.pointerId)
                    setGesto({ tipo: 'mover', id: a.atividade_id, xInicial: posicao(e).x, dx: 0 })
                  }}
                >
                  <title>{a.codigo + ' ' + a.nome + ' - marco em ' + curta(a.inicio_cedo)}</title>
                </polygon>
              ) : linha.temFilhos ? (
                <g onClick={() => onSelecionar(a.atividade_id, 'unica')} style={{ cursor: 'pointer' }}>
                  <rect x={geo.x} y={y + 3} width={geo.largura} height={5} rx={1} fill={cor(a)} opacity={0.8} />
                  {!!avanco[String(a.atividade_id)]?.avanco && (
                    <rect
                      x={geo.x} y={y + 3}
                      width={geo.largura * Math.min(avanco[String(a.atividade_id)]?.avanco ?? 0, 100) / 100}
                      height={5} rx={1} fill="var(--ink)" opacity={0.42}
                    />
                  )}
                  <polygon points={colchete(geo.x, y, 'esquerda')} fill={cor(a)} />
                  <polygon points={colchete(geo.x + geo.largura, y, 'direita')} fill={cor(a)} />
                  <title>{a.codigo + ' ' + a.nome + ' - ' + curta(a.inicio_cedo) + ' a ' + curta(a.termino_cedo)}</title>
                </g>
              ) : (
                <g>
                  <rect
                    x={geo.x} y={y} width={geo.largura} height={ALTURA_BARRA} rx={3}
                    fill={cor(a)} opacity={arrastando ? 0.65 : 1}
                    style={{ cursor: arrastavel ? 'grab' : 'pointer' }}
                    onDoubleClick={() => onAbrir(a.atividade_id)}
                    onPointerDown={e => {
                      onSelecionar(a.atividade_id, e.ctrlKey || e.metaKey ? 'alternar' : 'unica')
                      if (!arrastavel) return
                      e.currentTarget.ownerSVGElement?.setPointerCapture(e.pointerId)
                      setGesto({ tipo: 'mover', id: a.atividade_id, xInicial: posicao(e).x, dx: 0 })
                    }}
                  >
                    <title>{a.codigo + ' ' + a.nome + '\n' + curta(a.inicio_cedo) + ' a ' + curta(a.termino_cedo) + ' - ' + rotuloFolga(a)}</title>
                  </rect>

                  {/* O executado, dentro do previsto — o "% concluído" do MS
                      Project. Por cima da barra e mais escuro, nunca como uma
                      segunda barra ao lado: o avanço é uma fração DESTA
                      atividade, e duas barras lado a lado seriam lidas como dois
                      períodos. `pointerEvents: none` para não roubar o arrasto
                      da barra que ele cobre. */}
                  {!!avanco[String(a.atividade_id)]?.avanco && (
                    <rect
                      x={geo.x} y={y + 3}
                      width={geo.largura * Math.min(avanco[String(a.atividade_id)]?.avanco ?? 0, 100) / 100}
                      height={ALTURA_BARRA - 6} rx={2}
                      fill="var(--ink)" opacity={0.42} style={{ pointerEvents: 'none' }}
                    />
                  )}

                  {/* A âncora da restrição de data. Sem ela, "esta barra não anda
                      para trás" é um mistério que só o inspetor explica. */}
                  {a.nao_comecar_antes_de && (
                    <polygon points={ancora(eixo.x(a.nao_comecar_antes_de), y)} fill="var(--accent)">
                      <title>{'Não começar antes de ' + curta(a.nao_comecar_antes_de)}</title>
                    </polygon>
                  )}

                  {arrastavel && (
                    <>
                      <rect
                        x={geo.x + geo.largura - 5} y={y} width={5} height={ALTURA_BARRA}
                        fill="transparent" style={{ cursor: 'ew-resize' }}
                        onPointerDown={e => {
                          e.stopPropagation()
                          e.currentTarget.ownerSVGElement?.setPointerCapture(e.pointerId)
                          setGesto({ tipo: 'esticar', id: a.atividade_id, xInicial: posicao(e).x, dx: 0 })
                        }}
                      />
                      <circle
                        cx={geo.x + geo.largura + 7} cy={y + ALTURA_BARRA / 2} r={4.5}
                        fill="var(--surface)" stroke="var(--brand)" strokeWidth={1.4}
                        opacity={selecionadas.has(a.atividade_id) ? 1 : 0.28}
                        style={{ cursor: 'crosshair' }}
                        onPointerDown={e => {
                          e.stopPropagation()
                          const p = posicao(e)
                          e.currentTarget.ownerSVGElement?.setPointerCapture(e.pointerId)
                          setGesto({ tipo: 'ligar', origem: a.atividade_id, x: p.x, y: p.y, alvo: null })
                        }}
                      >
                        <title>Arraste até outra barra para criar a precedência</title>
                      </circle>
                    </>
                  )}
                </g>
              )}

              {mostrarNomes && !linha.temFilhos && (
                <text
                  x={geo.x + geo.largura + (arrastavel ? 16 : 6)} y={y + ALTURA_BARRA - 3}
                  fontSize={10.5} fill="var(--ink-3)" pointerEvents="none"
                >
                  {a.nome}
                </text>
              )}

              {/* Enquanto arrasta, a data (ou a duração) que vai ser pedida:
                  arrastar às cegas e conferir depois no CPM é o que faz errar
                  por um dia. */}
              {arrastando && (
                <text x={geo.x} y={y - 4} fontSize={10} fontWeight={700} fill="var(--accent)" pointerEvents="none">
                  {gesto.tipo === 'esticar'
                    ? Math.max((a.duracao_dias ?? 1) + Math.round(gesto.dx / eixo.pxPorDia), 1) + ' d'
                    : curta(paraIso(somarDias(daIso(a.inicio_cedo as string), Math.round(gesto.dx / eixo.pxPorDia))))}
                </text>
              )}
            </g>
          )
        })}

        {gesto.tipo === 'ligar' && (() => {
          const origem = porId.get(gesto.origem)
          const linhaOrigem = linhaDe.get(gesto.origem)
          if (!origem?.inicio_cedo || linhaOrigem == null) return null
          const geo = geometria(origem)
          if (!geo) return null
          return (
            <g pointerEvents="none">
              <line
                x1={geo.x + geo.largura + 7} y1={linhaOrigem * ALTURA_LINHA + ALTURA_LINHA / 2}
                x2={gesto.x} y2={gesto.y}
                stroke={gesto.alvo ? 'var(--good)' : 'var(--brand)'} strokeWidth={1.8} strokeDasharray="4 3"
              />
              {gesto.alvo != null && (
                <rect
                  x={0} y={(linhaDe.get(gesto.alvo) ?? 0) * ALTURA_LINHA}
                  width={eixo.largura} height={ALTURA_LINHA} fill="var(--good)" opacity={0.12}
                />
              )}
            </g>
          )
        })()}
      </svg>
    </div>
  )
}

const losango = (cx: number, cy: number, r: number) =>
  [cx + ',' + (cy - r), (cx + r) + ',' + cy, cx + ',' + (cy + r), (cx - r) + ',' + cy].join(' ')

/** As pontas da barra sintética — o colchete que P6 e MS Project desenham para
 *  dizer "isto é o intervalo das filhas", não uma atividade que alguém executa. */
const colchete = (x: number, y: number, lado: 'esquerda' | 'direita') => {
  const sinal = lado === 'esquerda' ? 1 : -1
  return [x + ',' + (y + 3), (x + sinal * 5) + ',' + (y + 3), x + ',' + (y + 12)].join(' ')
}

const ancora = (x: number, y: number) =>
  [x + ',' + (y - 2), (x + 5) + ',' + (y - 6), (x - 5) + ',' + (y - 6)].join(' ')

function curta(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [, m, d] = iso.split('-')
  return d + '/' + m
}
