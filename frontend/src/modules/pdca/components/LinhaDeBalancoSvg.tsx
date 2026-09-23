import { useMemo, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Card, Empty, Pill } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { diasEntre, MESES, paraData, somarDias } from '../arvore'
import type { LinhaDeBalanco, PayloadBalanco } from '../types'

const ALTURA_LOCAL = 17
const MARGEM = { topo: 34, direita: 20, baixo: 26, esquerda: 168 }

/** A linha de balanço: eixo Y é lugar, X é tempo, e a **inclinação da faixa é o
 *  ritmo**. O que ela existe para mostrar é o cruzamento — duas equipes no
 *  mesmo lugar ao mesmo tempo.
 *
 *  **Cor aqui é significado, não identidade.** Com até 40 serviços no gráfico,
 *  pintar um hue por serviço produziria um arco-íris que ninguém decodifica e
 *  que quebra para quem não distingue cores. A identidade vem do **rótulo
 *  direto** em cada faixa; a cor fica reservada ao gargalo e ao conflito, que
 *  são as duas coisas sobre as quais se age. */
export function LinhaDeBalancoSvg({ dados }: { dados: PayloadBalanco }) {
  const [focado, setFocado] = useState<number | null>(null)

  const janela = useMemo(() => {
    const datas: Date[] = []
    for (const linha of dados.linhas) {
      for (const p of linha.pontos) {
        const i = paraData(p.inicio)
        const f = paraData(p.fim)
        if (i) datas.push(i)
        if (f) datas.push(f)
      }
    }
    if (datas.length === 0) return null
    const min = new Date(Math.min(...datas.map((d) => d.getTime())))
    const max = new Date(Math.max(...datas.map((d) => d.getTime())))
    const inicio = somarDias(min, -2)
    const fim = somarDias(max, 2)
    return { inicio, fim, dias: Math.max(1, diasEntre(inicio, fim) + 1) }
  }, [dados])

  if (dados.eixo.length === 0 || !janela) {
    return (
      <Card>
        <Empty>
          Nenhuma atividade deste plano está amarrada a um local da obra — e sem
          lugar não há linha de balanço. Vincule as atividades aos locais para
          ver o ritmo.
        </Empty>
      </Card>
    )
  }

  const alturaPlot = dados.eixo.length * ALTURA_LOCAL
  const larguraPlot = Math.max(520, Math.min(janela.dias * 4.2, 2400))
  const largura = MARGEM.esquerda + larguraPlot + MARGEM.direita
  const altura = MARGEM.topo + alturaPlot + MARGEM.baixo

  const x = (d: Date) => MARGEM.esquerda + (diasEntre(janela.inicio, d) / janela.dias) * larguraPlot
  /** Eixo crescendo para cima: o térreo embaixo, como a obra é. */
  const y = (indice: number) => MARGEM.topo + alturaPlot - (indice + 0.5) * ALTURA_LOCAL

  const hoje = new Date()
  hoje.setHours(0, 0, 0, 0)
  const xHoje = hoje >= janela.inicio && hoje <= janela.fim ? x(hoje) : null

  /** O servidor devolve o **id** do gargalo; o objeto vem de `linhas`. */
  const gargaloId = dados.gargalo
  const gargalo = dados.linhas.find((l) => l.servico === gargaloId) ?? null
  const locaisEmConflito = new Set(dados.conflitos.map((c) => c.local))

  const meses: { x: number; rotulo: string }[] = []
  let mesAtual = -1
  for (let d = 0; d < janela.dias; d++) {
    const data = somarDias(janela.inicio, d)
    if (data.getMonth() !== mesAtual) {
      mesAtual = data.getMonth()
      meses.push({
        x: x(data),
        rotulo: `${MESES[mesAtual]} ${String(data.getFullYear()).slice(2)}`,
      })
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Card pad={false}>
        <div style={{ overflowX: 'auto', padding: '4px 0 8px' }}>
          <svg width={largura} height={altura} style={{ display: 'block' }}>
            {dados.eixo.map((local) => {
              const emConflito = locaisEmConflito.has(local.local)
              return (
                <g key={local.local}>
                  <line
                    x1={MARGEM.esquerda} y1={y(local.y)} x2={MARGEM.esquerda + larguraPlot} y2={y(local.y)}
                    stroke={emConflito ? 'var(--danger-soft)' : 'var(--line-2)'}
                    strokeWidth={emConflito ? ALTURA_LOCAL - 2 : 1}
                    opacity={emConflito ? 0.5 : 1}
                  />
                  <text
                    x={MARGEM.esquerda - 8} y={y(local.y) + 3.5}
                    textAnchor="end" fontSize={9.5} fill="var(--ink-3)"
                    fontFamily="var(--mono)"
                  >
                    {local.nome.length > 24 ? `${local.nome.slice(0, 23)}…` : local.nome}
                  </text>
                </g>
              )
            })}

            {meses.map((m) => (
              <g key={m.x}>
                <line
                  x1={m.x} y1={MARGEM.topo} x2={m.x} y2={MARGEM.topo + alturaPlot}
                  stroke="var(--line)" strokeWidth={1}
                />
                <text x={m.x + 4} y={MARGEM.topo - 8} fontSize={10} fontWeight={700} fill="var(--ink-3)">
                  {m.rotulo}
                </text>
              </g>
            ))}

            {xHoje != null && (
              <line
                x1={xHoje} y1={MARGEM.topo - 4} x2={xHoje} y2={MARGEM.topo + alturaPlot}
                stroke="var(--danger)" strokeWidth={1.5} opacity={0.75}
              />
            )}

            {dados.linhas.map((linha) => (
              <Faixa
                key={linha.servico}
                linha={linha}
                x={x}
                y={y}
                gargalo={linha.servico === gargaloId}
                focado={focado === linha.servico}
                esmaecido={focado != null && focado !== linha.servico}
                aoFocar={setFocado}
              />
            ))}
          </svg>
        </div>
      </Card>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        {gargalo && (
          <Card>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5, minWidth: 210 }}>
              <span style={{ fontSize: 10, letterSpacing: '0.11em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }}>
                Gargalo — dita o ritmo de todos
              </span>
              <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>
                {gargalo.nome}
              </span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink-2)' }}>
                {gargalo.locais_por_semana ?? '—'} locais por semana
              </span>
              <span style={{ fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
                Acelerar qualquer outro serviço não adianta enquanto este não andar.
              </span>
            </div>
          </Card>
        )}

        {dados.conflitos.length > 0 && (
          <Card>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7, minWidth: 260, maxWidth: 420 }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10, letterSpacing: '0.11em', textTransform: 'uppercase', color: 'var(--danger-ink)', fontWeight: 700 }}>
                <AlertTriangle size={12} />
                Duas equipes no mesmo lugar
              </span>
              {dados.conflitos.slice(0, 6).map((c, i) => (
                <div key={i} style={{ fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.45 }}>
                  <strong style={{ color: 'var(--ink)' }}>{c.local_rotulo}</strong>
                  {' — '}
                  {c.servico_a} e {c.servico_b}, {c.dias} {c.dias === 1 ? 'dia' : 'dias'}
                  {' '}
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-3)' }}>
                    ({dateToBR(c.inicio)} → {dateToBR(c.fim)})
                  </span>
                </div>
              ))}
              {dados.conflitos.length > 6 && (
                <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                  e mais {dados.conflitos.length - 6}.
                </span>
              )}
            </div>
          </Card>
        )}

        {(dados.atividades_sem_local.length > 0
          || dados.locais_alem_do_teto > 0
          || (dados.servicos_alem_do_teto ?? 0) > 0) && (
          <Card>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 240, maxWidth: 380 }}>
              <span style={{ fontSize: 10, letterSpacing: '0.11em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }}>
                O que ficou fora do gráfico
              </span>
              {dados.atividades_sem_local.length > 0 && (
                <span style={{ fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.5 }}>
                  <Pill kind="slate">{dados.atividades_sem_local.length}</Pill>{' '}
                  {dados.atividades_sem_local.length === 1 ? 'atividade sem local' : 'atividades sem local'} —
                  sem lugar, não há onde desenhar.
                </span>
              )}
              {dados.locais_alem_do_teto > 0 && (
                <span style={{ fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.5 }}>
                  <Pill kind="slate">{dados.locais_alem_do_teto}</Pill> locais além do que o eixo comporta.
                </span>
              )}
              {(dados.servicos_alem_do_teto ?? 0) > 0 && (
                <span style={{ fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.5 }}>
                  <Pill kind="slate">{dados.servicos_alem_do_teto}</Pill> serviços além do que o gráfico comporta.
                </span>
              )}
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}

function Faixa(
  { linha, x, y, gargalo, focado, esmaecido, aoFocar }: {
    linha: LinhaDeBalanco
    x: (d: Date) => number
    y: (i: number) => number
    gargalo: boolean
    focado: boolean
    esmaecido: boolean
    aoFocar: (id: number | null) => void
  },
) {
  const pontos = linha.pontos
    .map((p) => ({ i: paraData(p.inicio), f: paraData(p.fim), y: p.y, p }))
    .filter((p): p is { i: Date; f: Date; y: number; p: typeof linha.pontos[number] } =>
      p.i != null && p.f != null)
  if (pontos.length === 0) return null

  const inicios = pontos.map((p) => `${x(p.i)},${y(p.y)}`)
  const fins = [...pontos].reverse().map((p) => `${x(somarDias(p.f, 1))},${y(p.y)}`)
  const area = `${inicios.join(' ')} ${fins.join(' ')}`

  const cor = gargalo ? 'var(--danger)' : 'var(--brand)'
  const opacidade = esmaecido ? 0.18 : 1
  const primeiro = pontos[0]

  return (
    <g
      onMouseEnter={() => aoFocar(linha.servico)}
      onMouseLeave={() => aoFocar(null)}
      style={{ cursor: 'default' }}
      opacity={opacidade}
    >
      <title>
        {`${linha.nome}\n${linha.locais_por_semana ?? '—'} locais por semana`
          + `${gargalo ? '\ngargalo do plano' : ''}`}
      </title>

      {pontos.length > 1 ? (
        <polygon
          points={area}
          fill={cor}
          opacity={focado ? 0.3 : 0.16}
          stroke={cor}
          strokeWidth={focado || gargalo ? 2 : 1.2}
          strokeLinejoin="round"
        />
      ) : (
        <line
          x1={x(primeiro.i)} y1={y(primeiro.y)}
          x2={x(somarDias(primeiro.f, 1))} y2={y(primeiro.y)}
          stroke={cor} strokeWidth={focado || gargalo ? 3.5 : 2.5} strokeLinecap="round"
        />
      )}

      <text
        x={x(primeiro.i) + 4}
        y={y(primeiro.y) - 5}
        fontSize={9.5}
        fontWeight={gargalo ? 700 : 600}
        fill={gargalo ? 'var(--danger-ink)' : 'var(--ink-2)'}
      >
        {linha.nome.length > 26 ? `${linha.nome.slice(0, 25)}…` : linha.nome}
        {gargalo ? ' · gargalo' : ''}
      </text>
    </g>
  )
}
