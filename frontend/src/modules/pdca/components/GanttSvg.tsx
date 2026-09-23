import { useMemo } from 'react'
import { dateToBR } from '@/utils/dates'
import {
  diasEntre, janelaDoPlano, MESES, paraData, somarDias,
  type LinhaDaArvore,
} from '../arvore'
import { ALTURA_LINHA } from './GradeEap'
import type { ComparacaoComBase, AvancoDoCronograma, Precedencia } from '../types'

export type Zoom = 'dia' | 'semana' | 'mes'

const PX_POR_DIA: Record<Zoom, number> = { dia: 22, semana: 7, mes: 2.6 }
const ALTURA_CABECALHO = 40

interface Props {
  linhas: LinhaDaArvore[]
  precedencias: Precedencia[]
  base: ComparacaoComBase
  avanco: AvancoDoCronograma
  zoom: Zoom
  mostrarBase: boolean
  selecionada: number | null
  aoSelecionar: (id: number) => void
}

/** O Gantt. SVG próprio, e não biblioteca: o split view com a grade, a linha de
 *  base sobreposta à barra e o executado dentro dela são o que o planejador
 *  compara com o Project — nenhuma biblioteca permissiva entrega os três. */
export function GanttSvg(
  { linhas, precedencias, base, avanco, zoom, mostrarBase, selecionada, aoSelecionar }: Props,
) {
  const px = PX_POR_DIA[zoom]

  const janela = useMemo(
    () => janelaDoPlano(
      linhas.map((l) => l.atividade),
      mostrarBase ? base.linhas.flatMap((l) => [l.base_inicio, l.base_termino]) : [],
    ),
    [linhas, base, mostrarBase],
  )

  const porBase = useMemo(
    () => new Map(base.linhas.map((l) => [l.codigo, l])),
    [base],
  )

  const indicePorId = useMemo(() => {
    const m = new Map<number, number>()
    linhas.forEach((l, i) => m.set(l.atividade.atividade_id, i))
    return m
  }, [linhas])

  if (!janela) {
    return (
      <div
        style={{
          flex: 1, minWidth: 420, display: 'flex', alignItems: 'center',
          justifyContent: 'center', padding: 40, color: 'var(--ink-3)',
          fontSize: 13, textAlign: 'center', lineHeight: 1.6,
        }}
      >
        Nenhuma atividade tem data ainda.
        <br />
        Calcule o plano para ver as barras.
      </div>
    )
  }

  const largura = Math.max(560, Math.ceil(janela.dias * px))
  const altura = linhas.length * ALTURA_LINHA
  const x = (d: Date) => diasEntre(janela.inicio, d) * px
  const hoje = new Date()
  hoje.setHours(0, 0, 0, 0)
  const xHoje = hoje >= janela.inicio && hoje <= janela.fim ? x(hoje) : null

  const marcas = escalaDeTempo(janela.inicio, janela.dias, px, zoom)

  return (
    <div style={{ flex: 1, minWidth: largura }}>
      <div
        style={{
          height: ALTURA_CABECALHO, position: 'sticky', top: 0, zIndex: 2,
          background: 'var(--surface-2)', borderBottom: '1px solid var(--line)',
        }}
      >
        <svg width={largura} height={ALTURA_CABECALHO} role="presentation">
          {marcas.meses.map((m) => (
            <g key={`m${m.x}`}>
              <line x1={m.x} y1={0} x2={m.x} y2={ALTURA_CABECALHO} stroke="var(--line)" strokeWidth={1} />
              <text
                x={m.x + 5} y={15}
                fontSize={10.5} fontWeight={700} fill="var(--ink-2)"
                fontFamily="var(--sans)" letterSpacing="0.04em"
              >
                {m.rotulo}
              </text>
            </g>
          ))}
          {marcas.menores.map((t) => (
            <g key={`t${t.x}`}>
              <line
                x1={t.x} y1={ALTURA_CABECALHO - 14} x2={t.x} y2={ALTURA_CABECALHO}
                stroke="var(--line-2)" strokeWidth={1}
              />
              {t.rotulo && (
                <text
                  x={t.x + 3} y={ALTURA_CABECALHO - 4}
                  fontSize={9} fill="var(--ink-3)" fontFamily="var(--mono)"
                >
                  {t.rotulo}
                </text>
              )}
            </g>
          ))}
        </svg>
      </div>

      <svg width={largura} height={Math.max(altura, 1)} style={{ display: 'block' }}>
        <defs>
          <marker
            id="pdca-seta" viewBox="0 0 8 8" refX="7" refY="4"
            markerWidth="5" markerHeight="5" orient="auto-start-reverse"
          >
            <path d="M 0 1 L 7 4 L 0 7 z" fill="var(--ink-3)" />
          </marker>
        </defs>

        {marcas.meses.map((m) => (
          <line key={`gm${m.x}`} x1={m.x} y1={0} x2={m.x} y2={altura} stroke="var(--line)" strokeWidth={1} />
        ))}
        {marcas.menores.map((t) => (
          <line key={`gt${t.x}`} x1={t.x} y1={0} x2={t.x} y2={altura} stroke="var(--line-2)" strokeWidth={1} />
        ))}

        {linhas.map((l, i) => (
          <rect
            key={`f${l.atividade.atividade_id}`}
            x={0} y={i * ALTURA_LINHA} width={largura} height={ALTURA_LINHA}
            fill={l.atividade.atividade_id === selecionada ? 'var(--accent-soft)' : 'transparent'}
          />
        ))}
        {linhas.map((l, i) => (
          <line
            key={`h${l.atividade.atividade_id}`}
            x1={0} y1={(i + 1) * ALTURA_LINHA - 0.5}
            x2={largura} y2={(i + 1) * ALTURA_LINHA - 0.5}
            stroke="var(--line-2)" strokeWidth={1}
          />
        ))}

        {xHoje != null && (
          <line x1={xHoje} y1={0} x2={xHoje} y2={altura} stroke="var(--danger)" strokeWidth={1.5} opacity={0.75} />
        )}

        <Setas
          precedencias={precedencias}
          indicePorId={indicePorId}
          linhas={linhas}
          x={x}
          px={px}
        />

        {linhas.map((l, i) => (
          <Barra
            key={l.atividade.atividade_id}
            linha={l}
            i={i}
            x={x}
            px={px}
            executado={avanco.por_atividade[String(l.atividade.atividade_id)]?.avanco ?? null}
            naBase={mostrarBase ? porBase.get(l.atividade.codigo) : undefined}
            selecionada={l.atividade.atividade_id === selecionada}
            aoSelecionar={aoSelecionar}
          />
        ))}
      </svg>
    </div>
  )
}

function Barra(
  { linha, i, x, px, executado, naBase, selecionada, aoSelecionar }: {
    linha: LinhaDaArvore
    i: number
    x: (d: Date) => number
    px: number
    executado: number | null
    naBase: { base_inicio: string | null; base_termino: string | null } | undefined
    selecionada: boolean
    aoSelecionar: (id: number) => void
  },
) {
  const a = linha.atividade
  const inicio = paraData(a.inicio_cedo)
  const termino = paraData(a.termino_cedo)
  if (!inicio || !termino) return null

  const yBase = i * ALTURA_LINHA
  const alturaBarra = linha.temFilhos ? 8 : 13
  const y = yBase + (ALTURA_LINHA - alturaBarra) / 2 - (naBase ? 2 : 0)
  const x0 = x(inicio)
  const larguraBarra = Math.max(px, x(somarDias(termino, 1)) - x0)

  const dica = [
    `${a.codigo} · ${a.nome}`,
    `${dateToBR(a.inicio_cedo ?? '')} → ${dateToBR(a.termino_cedo ?? '')}`,
    a.eh_marco ? 'marco' : `${a.duracao_dias} dias`,
    executado == null ? 'sem apuração de avanço' : `${executado.toFixed(1).replace('.', ',')}% executado`,
    a.critica ? 'caminho crítico' : null,
  ].filter(Boolean).join('\n')

  const cor = a.critica ? 'var(--danger)' : 'var(--brand)'

  if (a.eh_marco) {
    const cx = x0 + 6
    const cy = yBase + ALTURA_LINHA / 2
    return (
      <g onClick={() => aoSelecionar(a.atividade_id)} style={{ cursor: 'pointer' }}>
        <title>{dica}</title>
        <path
          d={`M ${cx} ${cy - 7} L ${cx + 7} ${cy} L ${cx} ${cy + 7} L ${cx - 7} ${cy} Z`}
          fill={a.critica ? 'var(--danger)' : 'var(--info)'}
          stroke={selecionada ? 'var(--accent)' : 'none'}
          strokeWidth={1.5}
        />
      </g>
    )
  }

  return (
    <g onClick={() => aoSelecionar(a.atividade_id)} style={{ cursor: 'pointer' }}>
      <title>{dica}</title>

      {linha.temFilhos ? (
        <path
          d={`M ${x0} ${y} H ${x0 + larguraBarra} V ${y + alturaBarra}
              L ${x0 + larguraBarra - 5} ${y + alturaBarra - 4}
              H ${x0 + 5} L ${x0} ${y + alturaBarra} Z`}
          fill="var(--ink-2)"
          opacity={0.85}
        />
      ) : (
        <>
          <rect
            x={x0} y={y} width={larguraBarra} height={alturaBarra}
            rx={3} fill={cor} opacity={0.24}
          />
          {executado != null && executado > 0 && (
            <rect
              x={x0} y={y}
              width={Math.max(1.5, larguraBarra * Math.min(executado, 100) / 100)}
              height={alturaBarra} rx={3}
              fill="var(--good)"
            />
          )}
          <rect
            x={x0} y={y} width={larguraBarra} height={alturaBarra} rx={3}
            fill="none"
            stroke={selecionada ? 'var(--accent)' : cor}
            strokeWidth={selecionada ? 2 : 1.25}
          />
        </>
      )}

      {naBase?.base_inicio && naBase.base_termino && (() => {
        const bi = paraData(naBase.base_inicio)
        const bt = paraData(naBase.base_termino)
        if (!bi || !bt) return null
        const bx = x(bi)
        const bw = Math.max(px, x(somarDias(bt, 1)) - bx)
        return (
          <rect
            x={bx} y={y + alturaBarra + 1.5} width={bw} height={3.5} rx={1.5}
            fill="var(--ink-3)" opacity={0.55}
          />
        )
      })()}
    </g>
  )
}

function Setas(
  { precedencias, indicePorId, linhas, x, px }: {
    precedencias: Precedencia[]
    indicePorId: Map<number, number>
    linhas: LinhaDaArvore[]
    x: (d: Date) => number
    px: number
  },
) {
  const caminhos: string[] = []

  for (const p of precedencias) {
    const io = indicePorId.get(p.origem)
    const id = indicePorId.get(p.destino)
    if (io == null || id == null) continue

    const ao = linhas[io].atividade
    const ad = linhas[id].atividade
    const oi = paraData(ao.inicio_cedo)
    const ot = paraData(ao.termino_cedo)
    const di = paraData(ad.inicio_cedo)
    const dt = paraData(ad.termino_cedo)
    if (!oi || !ot || !di || !dt) continue

    const saiNoFim = p.tipo === 'FS' || p.tipo === 'FF'
    const chegaNoInicio = p.tipo === 'FS' || p.tipo === 'SS'

    const xo = saiNoFim ? x(somarDias(ot, 1)) : x(oi)
    const xd = chegaNoInicio ? x(di) : x(somarDias(dt, 1))
    const yo = io * ALTURA_LINHA + ALTURA_LINHA / 2
    const yd = id * ALTURA_LINHA + ALTURA_LINHA / 2

    const recuo = Math.max(6, px * 0.6)
    const meio = chegaNoInicio ? xd - recuo : xd + recuo
    caminhos.push(
      `M ${xo} ${yo} H ${saiNoFim ? Math.max(xo + recuo, meio) : Math.min(xo - recuo, meio)} V ${yd} H ${xd}`,
    )
  }

  return (
    <g>
      {caminhos.map((d, i) => (
        <path
          key={i}
          d={d}
          fill="none"
          stroke="var(--ink-3)"
          strokeWidth={1}
          opacity={0.5}
          markerEnd="url(#pdca-seta)"
        />
      ))}
    </g>
  )
}

interface Marca { x: number; rotulo?: string }

function escalaDeTempo(inicio: Date, dias: number, px: number, zoom: Zoom) {
  const meses: Marca[] = []
  const menores: Marca[] = []

  let mesAtual = -1
  for (let d = 0; d < dias; d++) {
    const data = somarDias(inicio, d)
    if (data.getMonth() !== mesAtual) {
      mesAtual = data.getMonth()
      meses.push({ x: d * px, rotulo: `${MESES[mesAtual]} ${String(data.getFullYear()).slice(2)}` })
    }
    if (zoom === 'dia') {
      if (data.getDay() === 1) menores.push({ x: d * px, rotulo: String(data.getDate()) })
    } else if (zoom === 'semana') {
      if (data.getDay() === 1) menores.push({ x: d * px })
    } else if (data.getDate() === 15) {
      menores.push({ x: d * px })
    }
  }
  return { meses, menores }
}
