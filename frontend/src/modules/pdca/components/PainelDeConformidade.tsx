import { Card, Empty, Num, Pill, SectionHead } from '@/components/malha'
import { percentual } from '../formato'
import type { GravidadeNc, PainelDeConformidade as Painel } from '../types'

const TOM_DA_GRAVIDADE: Record<GravidadeNc, 'slate' | 'accent' | 'danger'> = {
  menor: 'slate',
  maior: 'accent',
  critica: 'danger',
}

/** **O "Act" da qualidade** — o que mais reprova, e em que situação está hoje.
 *
 *  O índice diz *quanto* falhou; só o ranking diz *o quê* mudar. E o ranking é
 *  cumulativo de propósito — o processo que mais dá trabalho é o que reprova
 *  de novo depois de consertado —, por isso cada linha vem partida em *em
 *  tratamento*, *sem ninguém tratando* e *resolvida*: sem a partição, uma
 *  reprova encerrada semana passada se lê como problema de agora. */
export function PainelDeConformidade({ painel }: { painel: Painel }) {
  const laco = painel.ncs_abertas + painel.ncs_encerradas

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <SectionHead
        sub={
          painel.fichas_concluidas > 0
            ? `sobre ${painel.fichas_concluidas} ${painel.fichas_concluidas === 1 ? 'ficha concluída' : 'fichas concluídas'}`
            : undefined
        }
      >
        O que mais reprova
      </SectionHead>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10 }}>
        {painel.por_dominio.length === 0 ? (
          <Card>
            <Rotulo>Conformidade</Rotulo>
            <div style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 6, lineHeight: 1.5 }}>
              sem apuração — nenhuma ficha concluída com item julgado
            </div>
          </Card>
        ) : painel.por_dominio.map((d) => (
          <Card key={d.dominio}>
            <Rotulo>{d.rotulo}</Rotulo>
            <Num size={22} tone="var(--ink)" style={{ display: 'block', marginTop: 4 }}>
              {percentual(d.conformidade)}
            </Num>
            <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
              {d.conformes} {d.conformes === 1 ? 'conforme' : 'conformes'} ·{' '}
              {d.nao_conformes} {d.nao_conformes === 1 ? 'reprovado' : 'reprovados'}
            </div>
          </Card>
        ))}

        <Card>
          <Rotulo>O laço fechou</Rotulo>
          {laco === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 6 }}>
              nenhum defeito registrado nesta obra
            </div>
          ) : (
            <>
              <Num size={22} tone="var(--ink)" style={{ display: 'block', marginTop: 4 }}>
                {painel.ncs_encerradas}
                <span style={{ fontSize: 13, color: 'var(--ink-3)' }}> de {laco}</span>
              </Num>
              <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
                defeitos encerrados com a eficácia conferida
              </div>
            </>
          )}
        </Card>
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {painel.ncs_por_gravidade.map((g) => (
          <Pill key={g.gravidade} kind={g.abertas > 0 ? TOM_DA_GRAVIDADE[g.gravidade] : 'slate'}>
            {g.rotulo.split(' — ')[0]}: {g.abertas} {g.abertas === 1 ? 'aberta' : 'abertas'}
          </Pill>
        ))}
      </div>

      {painel.itens_que_mais_reprovam.length === 0 ? (
        <Empty>
          Nenhuma pergunta reprovou ainda. O ranking aparece quando uma ficha
          concluída tiver item não conforme.
        </Empty>
      ) : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr style={{ background: 'var(--surface-2)', color: 'var(--ink-3)', textAlign: 'left' }}>
                <th style={th}>Pergunta</th>
                <th style={{ ...th, textAlign: 'right' }}>Reprovas</th>
                <th style={{ ...th, textAlign: 'right' }}>Em tratamento</th>
                <th style={{ ...th, textAlign: 'right' }}>Sem ninguém tratando</th>
                <th style={{ ...th, textAlign: 'right' }}>Resolvidas</th>
              </tr>
            </thead>
            <tbody>
              {painel.itens_que_mais_reprovam.map((linha) => (
                <tr key={linha.item_modelo} style={{ borderTop: '1px solid var(--line-2)' }}>
                  <td style={td}>
                    <div style={{ color: 'var(--ink)' }}>{linha.texto}</div>
                    <div style={{ fontSize: 11, color: 'var(--ink-3)', fontFamily: 'var(--mono)' }}>
                      {linha.modelo_codigo} · {percentual(linha.percentual)} das reprovas
                    </div>
                  </td>
                  <td style={{ ...td, textAlign: 'right' }}><Num size={13}>{linha.reprovas}</Num></td>
                  <td style={{ ...td, textAlign: 'right' }}><Num size={13}>{linha.em_aberto}</Num></td>
                  <td style={{ ...td, textAlign: 'right' }}>
                    <Num size={13} tone={linha.sem_nc > 0 ? 'var(--danger-ink)' : undefined}>
                      {linha.sem_nc}
                    </Num>
                  </td>
                  <td style={{ ...td, textAlign: 'right' }}>
                    <Num size={13} tone="var(--good-ink)">{linha.encerradas}</Num>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {painel.reprovas_sem_modelo > 0 && (
            <div
              style={{
                padding: '8px 12px', fontSize: 11.5, color: 'var(--ink-3)',
                borderTop: '1px solid var(--line-2)', background: 'var(--inset)',
              }}
            >
              Mais {painel.reprovas_sem_modelo}{' '}
              {painel.reprovas_sem_modelo === 1 ? 'reprova' : 'reprovas'} de perguntas
              que não estão mais em nenhum modelo — contadas no total, fora do ranking.
            </div>
          )}
        </Card>
      )}
    </section>
  )
}

const th = { padding: '8px 12px', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase' } as const
const td = { padding: '9px 12px', verticalAlign: 'top' } as const

function Rotulo({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase',
        color: 'var(--ink-3)', fontWeight: 700,
      }}
    >
      {children}
    </div>
  )
}
