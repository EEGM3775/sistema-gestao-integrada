import { useMemo, useState } from 'react'
import { Pill } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { percentual } from '../formato'
import { intervaloDaSemana, somaDias } from '../semana'
import type { PontoDaSerie } from '../api/pdcaApi'

/** **A série de PPC** — porque um PPC isolado não diz nada.
 *
 *  SVG próprio, e não `recharts`, pela razão que a série tem e um gráfico de
 *  barras genérico não: **dois tipos de ponto precisam se desenhar diferente**.
 *  O ponto de uma semana reaberta é um número que já foi lido e depois mudou, e
 *  o de uma semana encerrada antes do domingo foi apurado com prazo pela frente
 *  — os dois entram na série e nenhum dos dois é comparável aos vizinhos sem
 *  aviso. É a mesma decisão do Gantt e da linha de balanço deste módulo: cor só
 *  por token, para o tema escuro não exigir reescrita. */
export function SerieDePpc({
  serie, aoEscolher, escolhida,
}: {
  serie: PontoDaSerie[]
  aoEscolher?: (inicio: string) => void
  escolhida?: string
}) {
  const [sobre, setSobre] = useState<PontoDaSerie | null>(null)

  const ultimo = serie[serie.length - 1]
  const media = useMemo(() => {
    if (serie.length === 0) return null
    const soma = serie.reduce((acc, p) => acc + Number(p.ppc), 0)
    return soma / serie.length
  }, [serie])

  if (serie.length === 0) {
    return (
      <div style={{ fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.6 }}>
        Nenhuma semana desta obra foi encerrada ainda. O índice aparece quando a
        primeira reunião julgar o quadro — até lá não há o que comparar.
      </div>
    )
  }

  const largura = 100 / serie.length
  const foco = sobre ?? ultimo

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 9 }}>
        <span
          className="num"
          style={{ fontSize: 24, fontWeight: 700, color: 'var(--ink)', lineHeight: 1 }}
        >
          {percentual(foco.ppc)}
        </span>
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.4 }}>
          {intervaloDaSemana(foco.semana_inicio, somaDias(foco.semana_inicio, 6))}
          {' · '}
          {foco.cumpridos} de {foco.comprometidos} compromissos
          {foco.peso_bases.length > 0 && ` · peso por ${foco.peso_bases.join(' e ')}`}
        </span>
        <span style={{ flex: 1 }} />
        {media != null && serie.length > 1 && (
          <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
            média de {serie.length} semanas:{' '}
            <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>
              {percentual(media)}
            </span>
          </span>
        )}
      </div>

      <svg
        viewBox="0 0 100 34"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Cumprimento das últimas ${serie.length} semanas encerradas`}
        style={{ width: '100%', height: 92, display: 'block', overflow: 'visible' }}
      >
        {/* As linhas de 50% e 100% — a régua sem a qual a barra não mede nada */}
        {[0, 17, 34].map((y) => (
          <line
            key={y}
            x1="0" x2="100" y1={y} y2={y}
            stroke="var(--line-2)" strokeWidth="0.25" vectorEffect="non-scaling-stroke"
          />
        ))}

        {serie.map((ponto, i) => {
          const valor = Math.max(0, Math.min(100, Number(ponto.ppc)))
          const altura = (valor / 100) * 34
          const x = i * largura
          const w = Math.max(largura - largura * 0.28, 0.6)
          const cx = x + (largura - w) / 2
          const marcada = escolhida === ponto.semana_inicio
          return (
            <g key={ponto.programacao}>
              <rect
                x={cx} y={34 - altura} width={w} height={Math.max(altura, 0.4)}
                fill={marcada ? 'var(--accent)' : 'var(--brand)'}
                opacity={ponto.encerrada_antes_do_fim ? 0.45 : 1}
                rx="0.4"
              />
              {/* Semana reaberta: o número já foi lido por alguém e mudou. O
                  traço no topo é o que impede o ponto corrigido de passar por
                  ponto virgem. */}
              {ponto.vezes_reaberta > 0 && (
                <rect
                  x={cx} y={Math.max(34 - altura - 1.4, 0)} width={w} height="1.1"
                  fill="var(--accent-ink)"
                />
              )}
              {/* A área inteira é o alvo do mouse: barra baixa não se acerta. */}
              <rect
                x={x} y="0" width={largura} height="34"
                fill="transparent"
                style={{ cursor: aoEscolher ? 'pointer' : 'default' }}
                onMouseEnter={() => setSobre(ponto)}
                onMouseLeave={() => setSobre(null)}
                onClick={() => aoEscolher?.(ponto.semana_inicio)}
              >
                <title>
                  {`${dateToBR(ponto.semana_inicio)} · ${percentual(ponto.ppc)}`}
                  {ponto.vezes_reaberta > 0 ? ' · reaberta' : ''}
                  {ponto.encerrada_antes_do_fim ? ' · encerrada antes do fim' : ''}
                </title>
              </rect>
            </g>
          )
        })}
      </svg>

      <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginTop: 9 }}>
        {serie.some((p) => p.vezes_reaberta > 0) && (
          <Pill kind="accent" title="Semanas cujo julgamento foi refeito depois de alguém já ter lido o índice.">
            traço no topo = semana reaberta
          </Pill>
        )}
        {serie.some((p) => p.encerrada_antes_do_fim) && (
          <Pill kind="slate" title="Apuradas antes do domingo, com prazo ainda pela frente.">
            barra clara = encerrada antes do fim
          </Pill>
        )}
      </div>
    </div>
  )
}
