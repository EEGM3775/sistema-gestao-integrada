import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, CalendarCheck, ClipboardCheck, HardHat, TrendingUp } from 'lucide-react'
import { Card, EmBreve, Pill } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { emDias, percentual } from '../formato'
import type { PulsoDaObra as Pulso } from '../types'
import { SemPermissaoAviso } from './SemPermissaoAviso'

/** **Quatro leituras honestas lado a lado** — e cada uma leva ao posto que a
 *  explica.
 *
 *  A régua é a do §5.1, e ela é dura: avanço sem apontamento é *sem apuração*,
 *  nunca 0%; PPC sem semana encerrada é *sem apuração*; e obra que nunca teve
 *  acidente com afastamento não mostra "0 dias" — mostra que não há série. Cada
 *  bloco carrega do servidor a frase do que falta, e é ela que aparece no lugar
 *  do número. */
export function PulsoDaObra({ pulso, obraId }: { pulso: Pulso; obraId: number }) {
  const { prazo, avanco, ppc, conformidade, seguranca } = pulso

  return (
    <section>
      {pulso.sem_permissao.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <SemPermissaoAviso itens={pulso.sem_permissao} />
        </div>
      )}

      <div
        style={{
          display: 'grid', gap: 12,
          gridTemplateColumns: 'repeat(auto-fit, minmax(212px, 1fr))',
        }}
      >
        <Leitura
          rotulo="Avanço físico"
          icone={<TrendingUp size={14} />}
          para={`/app/pdca/o/${obraId}/plano`}
          bloqueado={avanco == null}
          valor={percentual(avanco?.fisico)}
          faltando={avanco?.sem_apuracao_porque}
          base={
            avanco?.fisico != null
              ? `${avanco.folhas_apontadas} de ${avanco.folhas} serviços apontados`
              : undefined
          }
          extra={
            prazo?.desvio_dias != null ? (
              <Pill kind={prazo.desvio_dias > 0 ? 'danger' : 'good'}>
                {prazo.desvio_dias === 0
                  ? 'no prazo combinado'
                  : prazo.desvio_dias > 0
                    ? `${emDias(prazo.desvio_dias)} além do combinado`
                    : `${emDias(prazo.desvio_dias)} adiantado`}
              </Pill>
            ) : prazo?.termino ? (
              <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                Término previsto em {dateToBR(prazo.termino)}
              </span>
            ) : undefined
          }
        />

        <Leitura
          rotulo="Cumprimento da semana"
          icone={<CalendarCheck size={14} />}
          para={`/app/pdca/o/${obraId}/semana`}
          bloqueado={ppc == null}
          valor={percentual(ppc?.ppc)}
          faltando={ppc?.sem_apuracao_porque}
          base={
            ppc?.ppc != null
              ? `${ppc.cumpridos} de ${ppc.comprometidos} compromissos · semana de ${
                  ppc.semana_inicio ? dateToBR(ppc.semana_inicio) : ''
                }`
              : undefined
          }
          extra={<Tendencia serie={ppc?.serie ?? []} />}
        />

        <Leitura
          rotulo="Conformidade"
          icone={<ClipboardCheck size={14} />}
          para={`/app/pdca/o/${obraId}/qualidade`}
          bloqueado={conformidade == null}
          valor={percentual(conformidade?.conformidade, 2)}
          faltando={conformidade?.sem_apuracao_porque}
          base={
            conformidade?.conformidade != null
              ? `${conformidade.conformes} conformes de ${conformidade.julgados} itens julgados`
              : undefined
          }
        />

        <Leitura
          rotulo="Sem acidente com afastamento"
          icone={<HardHat size={14} />}
          para={`/app/pdca/o/${obraId}/seguranca`}
          bloqueado={seguranca == null}
          valor={
            seguranca?.dias_sem_afastamento != null
              ? emDias(seguranca.dias_sem_afastamento, 'hoje')
              : null
          }
          faltando={seguranca?.sem_apuracao_porque}
          base={
            seguranca?.ultimo_afastamento
              ? `Último em ${dateToBR(seguranca.ultimo_afastamento)}`
              : undefined
          }
          extra={
            seguranca ? (
              <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                {seguranca.ocorrencias_abertas > 0
                  ? `${seguranca.ocorrencias_abertas} ${
                      seguranca.ocorrencias_abertas === 1
                        ? 'ocorrência aberta'
                        : 'ocorrências abertas'
                    }`
                  : `${seguranca.ocorrencias_registradas} ${
                      seguranca.ocorrencias_registradas === 1
                        ? 'ocorrência registrada'
                        : 'ocorrências registradas'
                    }`}
              </span>
            ) : undefined
          }
        />
      </div>

      {seguranca && (
        <p
          style={{
            margin: '10px 2px 0', fontSize: 11.5, color: 'var(--ink-3)',
            lineHeight: 1.55, maxWidth: 780,
          }}
        >
          {seguranca.taxas_indisponiveis_porque}
        </p>
      )}
    </section>
  )
}

interface LeituraProps {
  rotulo: string
  icone: ReactNode
  para: string
  valor: string | null
  /** A frase do servidor sobre o que falta medir. Aparece **no lugar** do
   *  número, nunca embaixo de um zero. */
  faltando?: string
  base?: string
  extra?: ReactNode
  /** Sem a permissão do bloco: o cadeado, não um número vazio. */
  bloqueado?: boolean
}

function Leitura({ rotulo, icone, para, valor, faltando, base, extra, bloqueado }: LeituraProps) {
  const corpo = (
    <Card
      style={{
        display: 'flex', flexDirection: 'column', gap: 9, height: '100%',
        opacity: bloqueado ? 0.6 : 1,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        <span style={{ color: 'var(--ink-3)', display: 'grid', placeItems: 'center' }}>
          {icone}
        </span>
        <span
          style={{
            fontSize: 10.5, letterSpacing: '0.07em', textTransform: 'uppercase',
            color: 'var(--ink-3)', fontWeight: 700, lineHeight: 1.3,
          }}
        >
          {rotulo}
        </span>
        {!bloqueado && (
          <ArrowUpRight
            size={13}
            style={{ marginLeft: 'auto', color: 'var(--ink-3)', flexShrink: 0 }}
          />
        )}
      </div>

      {bloqueado ? (
        <EmBreve>sem acesso</EmBreve>
      ) : valor != null ? (
        <span
          className="num"
          style={{
            fontSize: 26, fontWeight: 700, color: 'var(--ink)',
            letterSpacing: '-0.02em', lineHeight: 1.05,
          }}
        >
          {valor}
        </span>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <EmBreve>sem apuração</EmBreve>
          {faltando && (
            <span style={{ fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
              {faltando}
            </span>
          )}
        </div>
      )}

      {base && (
        <span style={{ fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.4 }}>{base}</span>
      )}
      {extra && <div style={{ marginTop: 'auto', paddingTop: 2 }}>{extra}</div>}
    </Card>
  )

  if (bloqueado) return corpo
  return (
    <Link to={para} style={{ textDecoration: 'none', display: 'block', height: '100%' }}>
      {corpo}
    </Link>
  )
}

/** A série do PPC em barras minúsculas.
 *
 *  **Um PPC isolado não diz nada**: 68% subindo de 40% e 68% caindo de 90% são
 *  duas obras diferentes. Por isso a tendência viaja ao lado do número, e não
 *  numa página de gráfico. */
function Tendencia({ serie }: { serie: { semana_inicio: string; ppc: string }[] }) {
  if (serie.length < 2) return null
  const valores = serie.map((p) => Number(p.ppc))
  const teto = Math.max(100, ...valores)

  return (
    <div
      title={serie
        .map((p) => `${dateToBR(p.semana_inicio)}: ${percentual(p.ppc)}`)
        .join(' · ')}
      style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 22 }}
    >
      {valores.map((valor, i) => (
        <span
          key={serie[i].semana_inicio}
          style={{
            flex: 1,
            height: `${Math.max(8, (valor / teto) * 100)}%`,
            background: i === valores.length - 1 ? 'var(--accent)' : 'var(--line)',
            borderRadius: 1.5,
          }}
        />
      ))}
    </div>
  )
}
