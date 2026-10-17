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
  const [emTabela, setEmTabela] = useState(false)

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
        <button
          type="button"
          onClick={() => setEmTabela((v) => !v)}
          style={{
            background: 'none', border: '1px solid var(--line)', borderRadius: 6,
            padding: '3px 9px', fontSize: 11.5, fontWeight: 650, cursor: 'pointer',
            color: 'var(--ink-2)', fontFamily: 'inherit',
          }}
        >
          {emTabela ? 'Ver gráfico' : 'Ver tabela'}
        </button>
      </div>

      {emTabela ? (
        <TabelaDaSerie serie={serie} escolhida={escolhida} aoEscolher={aoEscolher} />
      ) : (
      <div style={{ display: 'flex', gap: 6 }}>
      {/* O eixo, escrito: sem ele a barra não se LÊ, só se estima (D295). Fora
          do SVG porque o `preserveAspectRatio="none"` esticaria o texto. */}
      <div
        aria-hidden
        style={{
          position: 'relative', width: 30, height: 92, flexShrink: 0,
          fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--ink-3)',
        }}
      >
        {[100, 50, 0].map((v) => (
          <span
            key={v}
            style={{
              position: 'absolute', right: 0, top: `${100 - v}%`,
              transform: 'translateY(-50%)', lineHeight: 1,
            }}
          >
            {v}%
          </span>
        ))}
      </div>
      <svg
        viewBox="0 0 100 34"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Cumprimento das últimas ${serie.length} semanas encerradas`}
        style={{ flex: 1, minWidth: 0, height: 92, display: 'block', overflow: 'visible' }}
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
              {/* A coluna é a semana INTEIRA — o que a equipe assumiu —, e a
                  barra é a parte que saiu. Sem o fundo, 50% vira um bloco solto
                  sem dizer contra o quê (D295). */}
              <rect x={cx} y="0" width={w} height="34" fill="var(--inset)" rx="0.4" />
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
      </div>
      )}

      <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginTop: 9, alignItems: 'center' }}>
        {/* As duas partes da coluna, nomeadas: a identidade não depende só da cor. */}
        <Amostra cor="var(--brand)" rotulo="saiu" />
        <Amostra cor="var(--inset)" rotulo="não saiu" />
        {escolhida && serie.some((p) => p.semana_inicio === escolhida) && (
          <Amostra cor="var(--accent)" rotulo="semana aberta no quadro" />
        )}
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

function Amostra({ cor, rotulo }: { cor: string; rotulo: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11.5, color: 'var(--ink-2)' }}>
      <span
        aria-hidden
        style={{
          width: 10, height: 10, borderRadius: 2, background: cor,
          border: '1px solid var(--line)', display: 'inline-block',
        }}
      />
      {rotulo}
    </span>
  )
}

/** **A tabela-gêmea** — obrigatória, não enfeite (D295). O acento da Malha fica
 *  abaixo de 3:1 contra a superfície clara, e a régua de dataviz só aceita isso
 *  com rótulo visível ou tabela: aqui nenhum valor fica só no gráfico, e o
 *  denominador tem coluna própria. */
function TabelaDaSerie({
  serie, escolhida, aoEscolher,
}: {
  serie: PontoDaSerie[]
  escolhida?: string
  aoEscolher?: (inicio: string) => void
}) {
  const celula: React.CSSProperties = { padding: '6px 9px', borderBottom: '1px solid var(--line-2)', textAlign: 'left' }
  const numero: React.CSSProperties = { ...celula, textAlign: 'right', fontFamily: 'var(--mono)' }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, color: 'var(--ink)' }}>
        <thead>
          <tr style={{ color: 'var(--ink-3)', fontSize: 11 }}>
            <th style={celula}>Semana</th>
            <th style={{ ...numero, fontFamily: 'inherit' }}>Cumprimento</th>
            <th style={{ ...numero, fontFamily: 'inherit' }}>Saíram</th>
            <th style={{ ...numero, fontFamily: 'inherit' }}>Assumidos</th>
            <th style={celula}>Observação</th>
          </tr>
        </thead>
        <tbody>
          {[...serie].reverse().map((p) => (
            <tr
              key={p.programacao}
              onClick={() => aoEscolher?.(p.semana_inicio)}
              style={{
                cursor: aoEscolher ? 'pointer' : 'default',
                background: escolhida === p.semana_inicio ? 'var(--accent-soft)' : 'transparent',
              }}
            >
              <td style={celula}>{intervaloDaSemana(p.semana_inicio, somaDias(p.semana_inicio, 6))}</td>
              <td style={numero}>{percentual(p.ppc)}</td>
              <td style={numero}>{p.cumpridos}</td>
              <td style={numero}>{p.comprometidos}</td>
              <td style={{ ...celula, color: 'var(--ink-3)' }}>
                {[
                  p.vezes_reaberta > 0 ? `reaberta ${p.vezes_reaberta}×` : '',
                  p.encerrada_antes_do_fim ? 'encerrada antes do fim' : '',
                ].filter(Boolean).join(' · ') || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
