import { Empty, Num } from '@/components/malha'
import { percentual } from '../formato'
import type { RankingDeCausas as Ranking } from '../types'

/** **O "Act"** — por que os compromissos desta obra não saem.
 *
 *  O PPC diz *quanto* falhou; só isto diz *o quê* mudar, e é a razão de a causa
 *  vir de catálogo fechado: com texto livre, "chuva", "choveu" e "clima" viram
 *  três linhas com um terço do peso cada, e a causa que lidera não aparece.
 *
 *  **É cumulativo de propósito** — um ranking que descartasse a causa já
 *  resolvida zeraria toda vez que a obra funcionasse, e passaria a medir o que
 *  está acontecendo agora em vez do que é difícil nesta obra. */
export function RankingDeCausas({ ranking }: { ranking: Ranking }) {
  if (ranking.total_falhas === 0) {
    return (
      <Empty>
        <span style={{ lineHeight: 1.6 }}>
          Nenhum compromisso desta obra deixou de sair nas semanas já encerradas.
          Quando um deixar, a causa registrada na reunião aparece aqui — é dela
          que sai o que mudar, e não do índice.
        </span>
      </Empty>
    )
  }

  const maior = Math.max(...ranking.causas.map((c) => c.ocorrencias), 1)

  return (
    <div
      style={{
        display: 'grid', gridTemplateColumns: 'minmax(0, 3fr) minmax(0, 2fr)',
        gap: 22,
      }}
    >
      <div>
        <Legenda>
          {/* "saiu" não pluraliza colando um sufixo — vira "saiuram". As duas
              formas ficam escritas por extenso, que é o único jeito de uma
              flexão irregular não sair errada em tela. */}
          {ranking.total_falhas === 1
            ? 'O que mais atrapalha — 1 compromisso que não saiu, acumulado'
            : `O que mais atrapalha — ${ranking.total_falhas} compromissos que não saíram, acumulado`}
        </Legenda>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {ranking.causas.map((causa) => (
            <div
              key={causa.causa ?? causa.codigo}
              style={{ display: 'flex', alignItems: 'center', gap: 10 }}
            >
              <span
                style={{
                  flex: 1, minWidth: 0, fontSize: 12.5, color: 'var(--ink-2)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}
                title={`${causa.codigo} · ${causa.nome}`}
              >
                {causa.nome || causa.codigo}
              </span>
              <div
                style={{
                  width: 150, height: 9, background: 'var(--inset)',
                  borderRadius: 999, overflow: 'hidden', flexShrink: 0,
                }}
              >
                <div
                  style={{
                    width: `${(causa.ocorrencias / maior) * 100}%`, height: '100%',
                    background: 'var(--brand)', borderRadius: 999,
                  }}
                />
              </div>
              <Num size={12.5} tone="var(--ink)" style={{ minWidth: 26 }}>
                {causa.ocorrencias}
              </Num>
              <Num size={11.5} tone="var(--ink-3)" style={{ minWidth: 46 }}>
                {percentual(causa.percentual)}
              </Num>
            </div>
          ))}
        </div>
      </div>

      <div>
        <Legenda>Com quem é a conversa</Legenda>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {ranking.categorias.map((categoria) => (
            <div
              key={categoria.categoria}
              style={{ display: 'flex', alignItems: 'center', gap: 10 }}
            >
              <span
                style={{
                  flex: 1, minWidth: 0, fontSize: 12.5, color: 'var(--ink-2)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}
              >
                {categoria.rotulo}
              </span>
              <div
                style={{
                  width: 84, height: 9, background: 'var(--inset)',
                  borderRadius: 999, overflow: 'hidden', flexShrink: 0,
                }}
              >
                <div
                  style={{
                    width: `${Number(categoria.percentual)}%`, height: '100%',
                    background: 'var(--ink-3)', borderRadius: 999,
                  }}
                />
              </div>
              <Num size={11.5} tone="var(--ink-3)" style={{ minWidth: 46 }}>
                {percentual(categoria.percentual)}
              </Num>
            </div>
          ))}
        </div>
        <p
          style={{
            fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.55,
            marginTop: 10, marginBottom: 0,
          }}
        >
          Saber qual causa lidera é meia informação. Saber para onde a maioria
          aponta — a equipe, o fornecedor, o projeto, o cliente — é o que decide
          se a próxima conversa é no canteiro ou na mesa da contratante.
        </p>
      </div>
    </div>
  )
}

function Legenda({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase',
        color: 'var(--ink-3)', fontWeight: 700, marginBottom: 9,
      }}
    >
      {children}
    </div>
  )
}
