import { useMemo, useRef, useState } from 'react'
import { dateToBR } from '@/utils/dates'
import {
  diasEntre, janelaDoPlano, MESES, paraData, somarDias,
  type LinhaDaArvore,
} from '../arvore'
import { diasUteisEntre } from '../importacao'
import { contarDiasUteis, expedientesDoGantt, type Expediente } from '../expediente'
import { ALTURA_CABECALHO_GRADE, ALTURA_LINHA, ZOOM_MAX, ZOOM_MIN, type Zoom } from '../grade'
import type {
  ComparacaoComBase, AvancoDoCronograma, ExpedientesDoPlano, Precedencia, Restricao, TipoPrecedencia,
} from '../types'

const ALTURA_CABECALHO = ALTURA_CABECALHO_GRADE

interface Props {
  linhas: LinhaDaArvore[]
  precedencias: Precedencia[]
  base: ComparacaoComBase
  avanco: AvancoDoCronograma
  zoom: Zoom
  /** Fim de semana, feriado e recesso de cada expediente: a barra se corta neles. */
  expedientes?: ExpedientesDoPlano
  mostrarBase: boolean
  selecionada: number | null
  editavel: boolean
  restricoesPorAtividade: Map<number, Restricao[]>
  ligacaoSelecionada: number | null
  /** Linhas marcadas na grade para agir em lote — realçadas aqui também. */
  marcadas?: ReadonlySet<number>
  aoSelecionar: (id: number) => void
  /** Arrastar a barra fixa o "não começar antes de"; esticar a ponta muda a duração. */
  aoReprogramar: (id: number, corpo: { nao_comecar_antes_de?: string; duracao_dias?: number }) => void
  aoLigar: (origem: number, destino: number, tipo: TipoPrecedencia) => void
  aoClicarLigacao: (p: Precedencia, ponto: { x: number; y: number }) => void
}

type Arrasto =
  | { modo: 'mover' | 'esticar'; id: number; x0: number; dx: number }
  | { modo: 'ligar'; id: number; lado: 'inicio' | 'fim'; x0: number; y0: number; x: number; y: number }

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** O Gantt. SVG próprio: o split view com a grade, a linha de base sobreposta à
 *  barra e o executado dentro dela — e, em rascunho, a física do Project:
 *  **arrastar** a barra para mudar a data, **esticar** a ponta para mudar a
 *  duração, **puxar** do pino de uma barra até outra para ligar, e clicar na
 *  seta para mudar o tipo ou desligar. Nada se move sem o servidor: soltar a
 *  barra grava a restrição de data e o CPM decide onde ela fica. */
export function GanttSvg(props: Props) {
  const {
    linhas, precedencias, base, avanco, zoom, expedientes, mostrarBase, selecionada, editavel,
    restricoesPorAtividade, ligacaoSelecionada, marcadas, aoSelecionar, aoReprogramar, aoLigar, aoClicarLigacao,
  } = props
  const px = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom))
  const [arrasto, setArrasto] = useState<Arrasto | null>(null)
  const [sobre, setSobre] = useState<number | null>(null)
  const svg = useRef<SVGSVGElement>(null)
  const exps = useMemo(() => expedientesDoGantt(expedientes), [expedientes])

  const janela = useMemo(
    () => janelaDoPlano(
      linhas.map((l) => l.atividade),
      mostrarBase ? base.linhas.flatMap((l) => [l.base_inicio, l.base_termino]) : [],
    ),
    [linhas, base, mostrarBase],
  )
  const porBase = useMemo(() => new Map(base.linhas.map((l) => [l.codigo, l])), [base])
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
        As barras aparecem quando o plano tiver data.
        <br />
        Confira o início e o expediente do plano no topo.
      </div>
    )
  }

  const largura = Math.max(560, Math.ceil(janela.dias * px) + 40)
  const altura = linhas.length * ALTURA_LINHA
  const x = (d: Date) => diasEntre(janela.inicio, d) * px
  const hoje = new Date()
  hoje.setHours(0, 0, 0, 0)
  const xHoje = hoje >= janela.inicio && hoje <= janela.fim ? x(hoje) : null
  const marcas = escalaDeTempo(janela.inicio, janela.dias, px)
  const paradas = diasParados(janela.inicio, janela.dias, exps.doPlano, px)

  function ponto(e: React.PointerEvent) {
    const caixa = svg.current!.getBoundingClientRect()
    return { x: e.clientX - caixa.left, y: e.clientY - caixa.top }
  }

  function iniciar(e: React.PointerEvent, novo: Arrasto) {
    if (!editavel) return
    e.stopPropagation()
    e.preventDefault()
    svg.current?.setPointerCapture(e.pointerId)
    setArrasto(novo)
  }

  function aoMover(e: React.PointerEvent) {
    if (!arrasto) return
    const p = ponto(e)
    if (arrasto.modo === 'ligar') setArrasto({ ...arrasto, x: p.x, y: p.y })
    else setArrasto({ ...arrasto, dx: p.x - arrasto.x0 })
  }

  function aoSoltar(e: React.PointerEvent) {
    if (!arrasto) return
    svg.current?.releasePointerCapture(e.pointerId)
    const atual = arrasto
    setArrasto(null)
    const linha = linhas[indicePorId.get(atual.id) ?? -1]
    if (!linha) return
    const a = linha.atividade

    if (atual.modo === 'ligar') {
      const p = ponto(e)
      const destino = linhas[Math.floor(p.y / ALTURA_LINHA)]?.atividade
      if (!destino || destino.atividade_id === a.atividade_id) return
      const di = paraData(destino.inicio_cedo)
      const dt = paraData(destino.termino_cedo)
      // Soltar perto do começo da barra-alvo liga ao início; perto do fim, ao término.
      const pertoDoInicio = !di || !dt || Math.abs(p.x - x(di)) <= Math.abs(p.x - x(somarDias(dt, 1)))
      const tipo: TipoPrecedencia = atual.lado === 'fim'
        ? (pertoDoInicio ? 'FS' : 'FF')
        : (pertoDoInicio ? 'SS' : 'SF')
      aoLigar(a.atividade_id, destino.atividade_id, tipo)
      return
    }

    const dias = Math.round(atual.dx / px)
    if (dias === 0) { aoSelecionar(a.atividade_id); return }
    const inicio = paraData(a.inicio_cedo)
    const termino = paraData(a.termino_cedo)
    if (!inicio || !termino) return
    if (atual.modo === 'mover') {
      aoReprogramar(a.atividade_id, { nao_comecar_antes_de: iso(somarDias(inicio, dias)) })
    } else {
      const novoFim = somarDias(termino, dias)
      if (novoFim < inicio) return
      // A duração é em dias úteis **do expediente da atividade** — com o
      // feriado e o recesso, não só de segunda a sexta.
      const exp = exps.daAtividade(a)
      aoReprogramar(a.atividade_id, {
        duracao_dias: exp ? contarDiasUteis(exp, inicio, novoFim) : diasUteisEntre(inicio, novoFim),
      })
    }
  }

  return (
    <div style={{ flex: 1, minWidth: largura }}>
      <div
        style={{
          height: ALTURA_CABECALHO, position: 'sticky', top: 0, zIndex: 2,
          background: 'var(--surface-2)', borderBottom: '1px solid var(--line)',
        }}
      >
        <svg width={largura} height={ALTURA_CABECALHO} role="presentation">
          {paradas.filter((p) => p.avulso).map((p) => (
            <rect
              key={`hf${p.x}`} x={p.x} y={ALTURA_CABECALHO - 14} width={Math.max(2, p.w)} height={14}
              fill="var(--danger)" opacity={0.28}
            >
              <title>{p.porque}</title>
            </rect>
          ))}
          {marcas.meses.map((m) => (
            <g key={`m${m.x}`}>
              <line x1={m.x} y1={0} x2={m.x} y2={ALTURA_CABECALHO} stroke="var(--line)" strokeWidth={1} />
              <text x={m.x + 5} y={15} fontSize={10.5} fontWeight={700} fill="var(--ink-2)" fontFamily="var(--sans)" letterSpacing="0.04em">
                {m.rotulo}
              </text>
            </g>
          ))}
          {marcas.menores.map((t) => (
            <g key={`t${t.x}`}>
              <line x1={t.x} y1={ALTURA_CABECALHO - 14} x2={t.x} y2={ALTURA_CABECALHO} stroke="var(--line-2)" strokeWidth={1} />
              {t.rotulo && (
                <text x={t.x + 3} y={ALTURA_CABECALHO - 4} fontSize={9} fill="var(--ink-3)" fontFamily="var(--mono)">
                  {t.rotulo}
                </text>
              )}
            </g>
          ))}
        </svg>
      </div>

      <svg
        ref={svg}
        width={largura}
        height={Math.max(altura, 1)}
        style={{ display: 'block', touchAction: 'none', userSelect: 'none' }}
        onPointerMove={aoMover}
        onPointerUp={aoSoltar}
        onPointerCancel={() => setArrasto(null)}
      >
        <defs>
          <marker id="pdca-seta" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 1 L 7 4 L 0 7 z" fill="var(--ink-3)" />
          </marker>
          <marker id="pdca-seta-ativa" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 1 L 7 4 L 0 7 z" fill="var(--accent)" />
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
            fill={l.atividade.atividade_id === selecionada || marcadas?.has(l.atividade.atividade_id) ? 'var(--accent-soft)' : 'transparent'}
            onPointerEnter={() => setSobre(l.atividade.atividade_id)}
            onClick={() => aoSelecionar(l.atividade.atividade_id)}
          />
        ))}
        {linhas.map((l, i) => (
          <line
            key={`h${l.atividade.atividade_id}`}
            x1={0} y1={(i + 1) * ALTURA_LINHA - 0.5} x2={largura} y2={(i + 1) * ALTURA_LINHA - 0.5}
            stroke="var(--line-2)" strokeWidth={1} pointerEvents="none"
          />
        ))}

        {/* Os dias parados do expediente do plano: fim de semana em cinza,
            feriado e recesso num tom mais quente. Por cima das linhas e por
            baixo das barras — que se cortam por conta própria (ver Barra). */}
        {paradas.map((p) => (
          <rect
            key={`p${p.x}`} x={p.x} y={0} width={p.w} height={altura}
            fill={p.avulso ? 'var(--danger)' : 'var(--ink-3)'} opacity={p.avulso ? 0.09 : 0.07}
            pointerEvents="none"
          />
        ))}

        {xHoje != null && (
          <line x1={xHoje} y1={0} x2={xHoje} y2={altura} stroke="var(--danger)" strokeWidth={1.5} opacity={0.75} pointerEvents="none" />
        )}

        <Setas
          precedencias={precedencias}
          indicePorId={indicePorId}
          linhas={linhas}
          x={x}
          px={px}
          selecionada={ligacaoSelecionada}
          aoClicar={(p, e) => aoClicarLigacao(p, { x: e.clientX, y: e.clientY })}
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
            mostrarPinos={editavel && (sobre === l.atividade.atividade_id || selecionada === l.atividade.atividade_id)}
            deslocamento={arrasto && arrasto.modo !== 'ligar' && arrasto.id === l.atividade.atividade_id ? arrasto : null}
            restricoes={restricoesPorAtividade.get(l.atividade.atividade_id) ?? []}
            expediente={exps.daAtividade(l.atividade)}
            editavel={editavel}
            aoEntrar={() => setSobre(l.atividade.atividade_id)}
            aoIniciar={(e, modo, lado) => {
              const p = ponto(e)
              if (modo === 'ligar') {
                iniciar(e, { modo, id: l.atividade.atividade_id, lado: lado ?? 'fim', x0: p.x, y0: p.y, x: p.x, y: p.y })
              } else {
                iniciar(e, { modo, id: l.atividade.atividade_id, x0: p.x, dx: 0 })
              }
            }}
            aoSelecionar={aoSelecionar}
          />
        ))}

        {arrasto?.modo === 'ligar' && (
          <line
            x1={arrasto.x0} y1={arrasto.y0} x2={arrasto.x} y2={arrasto.y}
            stroke="var(--accent)" strokeWidth={1.6} strokeDasharray="4 3"
            markerEnd="url(#pdca-seta-ativa)" pointerEvents="none"
          />
        )}
      </svg>
    </div>
  )
}

function Barra(
  {
    linha, i, x, px, executado, naBase, selecionada, mostrarPinos, deslocamento,
    restricoes, expediente, editavel, aoEntrar, aoIniciar, aoSelecionar,
  }: {
    linha: LinhaDaArvore
    i: number
    x: (d: Date) => number
    px: number
    executado: number | null
    naBase: { base_inicio: string | null; base_termino: string | null } | undefined
    selecionada: boolean
    mostrarPinos: boolean
    deslocamento: { modo: 'mover' | 'esticar'; dx: number } | null
    restricoes: Restricao[]
    expediente: Expediente | null
    editavel: boolean
    aoEntrar: () => void
    aoIniciar: (e: React.PointerEvent, modo: 'mover' | 'esticar' | 'ligar', lado?: 'inicio' | 'fim') => void
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
  const dxMover = deslocamento?.modo === 'mover' ? deslocamento.dx : 0
  const dxEsticar = deslocamento?.modo === 'esticar' ? deslocamento.dx : 0
  const x0 = x(inicio) + dxMover
  const larguraBarra = Math.max(px, x(somarDias(termino, 1)) - x(inicio) + dxEsticar)
  const cy = yBase + ALTURA_LINHA / 2

  const dica = [
    `${a.codigo} · ${a.nome}`,
    `${dateToBR(a.inicio_cedo ?? '')} → ${dateToBR(a.termino_cedo ?? '')}`,
    a.eh_marco ? 'marco' : linha.temFilhos ? 'etapa' : `${a.duracao_dias} dias úteis`,
    executado == null ? null : `${executado.toFixed(1).replace('.', ',')}% executado`,
    a.critica ? 'caminho crítico' : null,
    editavel && !linha.temFilhos ? 'arraste para mudar a data · puxe a ponta para mudar a duração' : null,
    editavel ? 'puxe um pino até outra barra para ligar' : null,
  ].filter(Boolean).join('\n')

  const cor = a.critica ? 'var(--danger)' : 'var(--brand)'
  const podeMover = editavel && !linha.temFilhos

  // A barra se **corta** nos dias em que o expediente dela não trabalha (fim
  // de semana, feriado, recesso): o CPM já os pulava, agora a tela mostra.
  // Durante o arrasto não — os dias parados mudam com a posição, e o corte
  // velho por cima da barra em movimento mente.
  const cortes: { x: number; w: number }[] = []
  if (expediente && !linha.temFilhos && !a.eh_marco && !deslocamento) {
    let aberto: { x: number; w: number } | null = null
    for (let d = new Date(inicio); d <= termino; d = somarDias(d, 1)) {
      if (expediente.ehUtil(d)) { aberto = null; continue }
      if (aberto) aberto.w += px
      else { aberto = { x: x(d), w: px }; cortes.push(aberto) }
    }
  }
  const desenhoDosCortes = cortes.map((c) => (
    <g key={`c${c.x}`} pointerEvents="none">
      <rect x={c.x} y={y - 1} width={c.w} height={alturaBarra + 2} fill="var(--surface)" opacity={0.82} />
      <line x1={c.x} y1={cy} x2={c.x + c.w} y2={cy} stroke={cor} strokeWidth={1} strokeDasharray="2 2" opacity={0.7} />
    </g>
  ))

  const pinos = mostrarPinos && (
    <>
      <circle
        cx={x0 - 5} cy={cy} r={4} fill="var(--surface)" stroke="var(--accent)" strokeWidth={1.4}
        style={{ cursor: 'crosshair' }}
        onPointerDown={(e) => aoIniciar(e, 'ligar', 'inicio')}
      >
        <title>Puxe até outra barra: ligar pelo início (SS/SF)</title>
      </circle>
      <circle
        cx={x0 + (a.eh_marco ? 12 : larguraBarra) + 5} cy={cy} r={4} fill="var(--surface)" stroke="var(--accent)" strokeWidth={1.4}
        style={{ cursor: 'crosshair' }}
        onPointerDown={(e) => aoIniciar(e, 'ligar', 'fim')}
      >
        <title>Puxe até outra barra: o que vem depois (FS/FF)</title>
      </circle>
    </>
  )

  const marcasDeRestricao = restricoes.filter((r) => r.prazo).map((r) => {
    const d = paraData(r.prazo)
    if (!d) return null
    const xr = x(d)
    const segura = d >= inicio
    return (
      <path
        key={r.restricao_id}
        d={`M ${xr} ${yBase + 2} l 4 6 h -8 z`}
        fill={segura ? 'var(--danger)' : 'var(--accent)'}
        pointerEvents="visiblePainted"
      >
        <title>
          {`${r.tipo_rotulo}: ${r.descricao} — até ${dateToBR(r.prazo ?? '')}`}
          {segura ? '\nChega depois do início previsto: a atividade fica travada.' : ''}
        </title>
      </path>
    )
  })

  if (a.eh_marco) {
    const cx = x0 + 6
    return (
      <g onPointerEnter={aoEntrar}>
        <g
          onPointerDown={(e) => (podeMover ? aoIniciar(e, 'mover') : undefined)}
          onClick={() => !podeMover && aoSelecionar(a.atividade_id)}
          style={{ cursor: podeMover ? 'grab' : 'pointer' }}
        >
          <title>{dica}</title>
          <path
            d={`M ${cx} ${cy - 7} L ${cx + 7} ${cy} L ${cx} ${cy + 7} L ${cx - 7} ${cy} Z`}
            fill={a.critica ? 'var(--danger)' : 'var(--info)'}
            stroke={selecionada ? 'var(--accent)' : 'none'} strokeWidth={1.5}
          />
        </g>
        {marcasDeRestricao}
        {pinos}
      </g>
    )
  }

  return (
    <g onPointerEnter={aoEntrar}>
      <g
        onPointerDown={(e) => (podeMover ? aoIniciar(e, 'mover') : undefined)}
        onClick={() => !podeMover && aoSelecionar(a.atividade_id)}
        style={{ cursor: podeMover ? 'grab' : 'pointer' }}
      >
        <title>{dica}</title>
        {linha.temFilhos ? (
          <path
            d={`M ${x0} ${y} H ${x0 + larguraBarra} V ${y + alturaBarra}
                L ${x0 + larguraBarra - 5} ${y + alturaBarra - 4}
                H ${x0 + 5} L ${x0} ${y + alturaBarra} Z`}
            fill="var(--ink-2)" opacity={0.85}
            stroke={selecionada ? 'var(--accent)' : 'none'} strokeWidth={1.5}
          />
        ) : (
          <>
            <rect x={x0} y={y} width={larguraBarra} height={alturaBarra} rx={3} fill={cor} opacity={0.24} />
            {executado != null && executado > 0 && (
              <rect
                x={x0} y={y} width={Math.max(1.5, larguraBarra * Math.min(executado, 100) / 100)}
                height={alturaBarra} rx={3} fill="var(--good)"
              />
            )}
            <rect
              x={x0} y={y} width={larguraBarra} height={alturaBarra} rx={3} fill="none"
              stroke={selecionada ? 'var(--accent)' : cor} strokeWidth={selecionada ? 2 : 1.25}
            />
          </>
        )}
        {desenhoDosCortes}
      </g>

      {podeMover && (
        <rect
          x={x0 + larguraBarra - 4} y={y - 1} width={8} height={alturaBarra + 2}
          fill="transparent" style={{ cursor: 'ew-resize' }}
          onPointerDown={(e) => aoIniciar(e, 'esticar')}
        >
          <title>Puxe para mudar a duração</title>
        </rect>
      )}

      {naBase?.base_inicio && naBase.base_termino && (() => {
        const bi = paraData(naBase.base_inicio)
        const bt = paraData(naBase.base_termino)
        if (!bi || !bt) return null
        const bx = x(bi)
        const bw = Math.max(px, x(somarDias(bt, 1)) - bx)
        return <rect x={bx} y={y + alturaBarra + 1.5} width={bw} height={3.5} rx={1.5} fill="var(--ink-3)" opacity={0.55} pointerEvents="none" />
      })()}

      {marcasDeRestricao}
      {pinos}
    </g>
  )
}

function Setas(
  { precedencias, indicePorId, linhas, x, px, selecionada, aoClicar }: {
    precedencias: Precedencia[]
    indicePorId: Map<number, number>
    linhas: LinhaDaArvore[]
    x: (d: Date) => number
    px: number
    selecionada: number | null
    aoClicar: (p: Precedencia, e: React.MouseEvent) => void
  },
) {
  const caminhos: { p: Precedencia; d: string }[] = []

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
    caminhos.push({ p, d: rotaDaSeta(xo, yo, xd, yd, saiNoFim, chegaNoInicio, Math.max(7, px * 0.6)) })
  }

  return (
    <g>
      {caminhos.map(({ p, d }) => {
        const ativa = p.precedencia_id === selecionada
        return (
          <g key={p.precedencia_id} style={{ cursor: 'pointer' }} onClick={(e) => aoClicar(p, e)}>
            <title>{`${p.tipo}${p.atraso_dias ? ` ${p.atraso_dias > 0 ? '+' : ''}${p.atraso_dias}d` : ''} — clique para mudar ou desligar`}</title>
            <path d={d} fill="none" stroke="transparent" strokeWidth={9} />
            <path
              d={d} fill="none"
              stroke={ativa ? 'var(--accent)' : 'var(--ink-3)'}
              strokeWidth={ativa ? 1.8 : 1}
              opacity={ativa ? 1 : 0.55}
              markerEnd={ativa ? 'url(#pdca-seta-ativa)' : 'url(#pdca-seta)'}
            />
          </g>
        )
      })}
    </g>
  )
}

/** O caminho de uma seta, no molde do MS Project.
 *
 *  A seta **chega por trás** quando liga ao começo (FS, SS: entra pela
 *  esquerda, apontando para a direita) e **pela frente** quando liga ao término
 *  (FF, SF: entra pela direita). Sai pelo lado da origem que o tipo diz — o
 *  fim (FS, FF) para a direita, o começo (SS, SF) para a esquerda.
 *
 *  Quando não há espaço horizontal entre a saída e a chegada — o FS sem folga,
 *  em que a sucessora começa logo depois de a antecessora terminar —, a rota
 *  antiga voltava por cima da barra e a ponta chegava ao contrário. Aqui ela
 *  desce até a fronteira entre as linhas, cruza por ali e entra pelo lado
 *  certo: um "S" em vez de um gancho. */
function rotaDaSeta(
  xo: number, yo: number, xd: number, yd: number,
  saiNoFim: boolean, chegaNoInicio: boolean, recuo: number,
): string {
  const xs = saiNoFim ? xo + recuo : xo - recuo // o toco de saída
  const xe = chegaNoInicio ? xd - recuo : xd + recuo // o ponto de aproximação
  // Dá para descer numa vertical só? Saindo para a direita, a vertical tem de
  // ficar à direita do toco; chegando por trás, à esquerda da aproximação.
  const lo = saiNoFim ? xs : -Infinity
  const hi = saiNoFim ? Infinity : xs
  const alvoLo = chegaNoInicio ? -Infinity : xe
  const alvoHi = chegaNoInicio ? xe : Infinity
  const de = Math.max(lo, alvoLo)
  const ate = Math.min(hi, alvoHi)
  if (de <= ate) {
    const xv = Number.isFinite(de) ? de : ate
    return `M ${xo} ${yo} H ${xv} V ${yd} H ${xd}`
  }
  // Sem vertical única: atravessa pela fronteira entre as linhas da chegada.
  const yMeio = yd + (yd > yo ? -ALTURA_LINHA / 2 : ALTURA_LINHA / 2)
  return `M ${xo} ${yo} H ${xs} V ${yMeio} H ${xe} V ${yd} H ${xd}`
}

interface Marca { x: number; rotulo?: string }

/** As marcas da régua de tempo, pela densidade (pixels por dia) — e não por
 *  três modos fixos: cada dia rotulado quando cabe o número, as segundas quando
 *  cabe a semana, o dia 15 quando só cabe o mês; e o rótulo do mês some para o
 *  trimestre quando o mês fica estreito demais para "jan 26". */
function escalaDeTempo(inicio: Date, dias: number, px: number) {
  const meses: Marca[] = []
  const menores: Marca[] = []
  let mesAtual = -1
  const mesCabeRotulo = px * 30 >= 38
  for (let d = 0; d < dias; d++) {
    const data = somarDias(inicio, d)
    if (data.getMonth() !== mesAtual) {
      mesAtual = data.getMonth()
      const rotulo = mesCabeRotulo || mesAtual % 3 === 0
        ? `${MESES[mesAtual]} ${String(data.getFullYear()).slice(2)}`
        : undefined
      meses.push({ x: d * px, rotulo })
    }
    if (px >= 16) {
      menores.push({ x: d * px, rotulo: String(data.getDate()) })
    } else if (px >= 9) {
      menores.push({ x: d * px, rotulo: data.getDay() === 1 ? String(data.getDate()) : undefined })
    } else if (px >= 2.4) {
      if (data.getDay() === 1) menores.push({ x: d * px, rotulo: px * 7 >= 20 ? String(data.getDate()) : undefined })
    } else if (data.getDate() === 15) {
      menores.push({ x: d * px })
    }
  }
  return { meses, menores }
}

/** Os dias parados do expediente do plano na janela, emendados em faixas. Com
 *  a escala apertada (menos de 3 px por dia) o fim de semana vira textura e sai
 *  do desenho; feriado e recesso ficam sempre. */
function diasParados(inicio: Date, dias: number, exp: Expediente | null, px: number) {
  const faixas: { x: number; w: number; avulso: boolean; porque: string }[] = []
  if (!exp) return faixas
  let aberta: (typeof faixas)[number] | null = null
  for (let d = 0; d < dias; d++) {
    const data = somarDias(inicio, d)
    const avulso = exp.avulso(data)
    const parado = !exp.ehUtil(data) && (avulso || px >= 3)
    if (!parado) { aberta = null; continue }
    const porque = exp.porque(data) ?? ''
    if (aberta && !avulso && !aberta.avulso) {
      aberta.w += px
    } else {
      aberta = { x: d * px, w: px, avulso, porque: `${dateToBR(iso(data))} · ${porque}` }
      faixas.push(aberta)
    }
  }
  return faixas
}
