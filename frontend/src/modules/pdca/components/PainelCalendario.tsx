import { Card, Empty, Loading, Pill } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { useCalendarios } from '../hooks'
import type { CalendarioTrabalho } from '../types'

const DIAS: { campo: keyof CalendarioTrabalho; sigla: string }[] = [
  { campo: 'trabalha_segunda', sigla: 'S' },
  { campo: 'trabalha_terca', sigla: 'T' },
  { campo: 'trabalha_quarta', sigla: 'Q' },
  { campo: 'trabalha_quinta', sigla: 'Q' },
  { campo: 'trabalha_sexta', sigla: 'S' },
  { campo: 'trabalha_sabado', sigla: 'S' },
  { campo: 'trabalha_domingo', sigla: 'D' },
]

/** O expediente é o que converte duração em data. Mora dentro do posto que o
 *  consome — configuração com item de menu próprio vira assunto, e assunto
 *  vira porta. */
export function PainelCalendario({ obraId }: { obraId: number }) {
  const { data, isLoading, isError } = useCalendarios(obraId)

  if (isLoading) return <Loading o="os expedientes" />
  if (isError) {
    return (
      <Card>
        <Empty>Não foi possível carregar os expedientes. Tente de novo.</Empty>
      </Card>
    )
  }
  if (!data || data.length === 0) {
    return (
      <Card>
        <Empty>
          Esta empresa ainda não cadastrou expediente. Sem ele o plano não calcula
          prazo — é o expediente que diz quando se trabalha.
        </Empty>
      </Card>
    )
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
      {data.map((cal) => (
        <Card key={cal.calendario_id}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
              <span style={{ flex: 1, fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>
                {cal.nome}
              </span>
              <Pill kind={cal.obra ? 'accent' : 'slate'}>
                {cal.obra ? 'desta obra' : 'da empresa'}
              </Pill>
            </div>

            <div style={{ display: 'flex', gap: 4 }}>
              {DIAS.map((d, i) => {
                const trabalha = Boolean(cal[d.campo])
                return (
                  <span
                    key={i}
                    title={trabalha ? 'Dia trabalhado' : 'Não se trabalha'}
                    style={{
                      width: 24, height: 24, borderRadius: 5,
                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 10.5, fontWeight: 700, fontFamily: 'var(--mono)',
                      background: trabalha ? 'var(--accent-soft)' : 'var(--inset)',
                      color: trabalha ? 'var(--accent-ink)' : 'var(--ink-3)',
                    }}
                  >
                    {d.sigla}
                  </span>
                )
              })}
            </div>

            <div style={{ display: 'flex', gap: 14, fontSize: 12, color: 'var(--ink-2)' }}>
              <span>
                <span style={{ color: 'var(--ink-3)' }}>Jornada </span>
                <span style={{ fontFamily: 'var(--mono)' }}>{cal.horas_por_dia} h</span>
              </span>
              <span style={{ color: cal.considera_feriados ? 'var(--ink-2)' : 'var(--ink-3)' }}>
                {cal.considera_feriados ? 'Respeita feriados' : 'Ignora feriados'}
              </span>
            </div>

            {cal.excecoes.length > 0 && (
              <div style={{ borderTop: '1px solid var(--line-2)', paddingTop: 9 }}>
                <div
                  style={{
                    fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase',
                    color: 'var(--ink-3)', fontWeight: 700, marginBottom: 6,
                  }}
                >
                  Exceções ({cal.excecoes.length})
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {cal.excecoes.slice(0, 5).map((e) => (
                    <div key={e.excecao_id} style={{ display: 'flex', gap: 8, fontSize: 11.5 }}>
                      <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>
                        {dateToBR(e.data)}
                      </span>
                      <span style={{ color: e.trabalha ? 'var(--good-ink)' : 'var(--danger-ink)' }}>
                        {e.trabalha ? 'trabalha' : 'para'}
                      </span>
                      <span style={{ color: 'var(--ink-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {e.descricao}
                      </span>
                    </div>
                  ))}
                  {cal.excecoes.length > 5 && (
                    <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
                      e mais {cal.excecoes.length - 5}.
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </Card>
      ))}
    </div>
  )
}
