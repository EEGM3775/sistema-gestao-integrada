import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { Card, Empty, Loading } from '@/components/malha'
import { CurvaSGrafico, GraficoEstilos } from '@/modules/orcamento/components/graficos'
import { mesBR } from '@/modules/orcamento/lib'
import { dateToBR } from '@/utils/dates'
import { usePdca } from '../contexto'
import { useAvancoFisicoFinanceiro } from '../hooks'
import type { AvancoFisicoFinanceiro, LinhaDoAvanco } from '../types'

const reais = (v: string | number | null | undefined) =>
  v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
const pct = (v: number | null | undefined) =>
  v == null ? '—' : `${v.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`

type Regua = 'plano' | 'orcamento'

/** **O avanço físico-financeiro** — quanto da obra foi executado, em % e em
 *  reais do orçado, contra duas réguas:
 *
 *  - o **previsto pelo plano** (as datas do CPM até hoje);
 *  - o **planejado no Orçamento** (o cronograma físico-financeiro etapa ×
 *    competência, pro rata no mês corrente).
 *
 *  *Decisão do dono, 10/10/2026:* o cronograma físico-financeiro é do
 *  Orçamento; o **avanço** é do PDCA, e tem de poder ser comparado com o
 *  planejado. O realizado é o apontado no campo — não o custo consumido, que o
 *  Controle do Orçamento acompanha. */
export function PainelAvanco({ cronogramaId, obraId }: { cronogramaId: number; obraId: number }) {
  const { selecionar } = usePdca()
  const { data, isLoading, isError } = useAvancoFisicoFinanceiro(cronogramaId)
  const [regua, setRegua] = useState<Regua>('plano')
  const serie = useMemo(() => (data ? serieDaCurva(data, regua) : []), [data, regua])

  if (isLoading) return <Loading o="o avanço físico-financeiro" />
  if (isError || !data) return <Card><Empty>Não foi possível montar o avanço físico-financeiro.</Empty></Card>

  const comPlanejado = data.tem_dinheiro && data.planejado != null
  const celula = { padding: '8px 12px', borderBottom: '1px solid var(--line-2)', whiteSpace: 'nowrap' as const }
  const numero = { ...celula, textAlign: 'right' as const, fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' as const }
  const cabeca = { ...celula, fontSize: 10.5, color: 'var(--ink-3)', background: 'var(--surface-2)' }
  const tom = (v: number | string | null | undefined) =>
    v == null || Number(v) === 0 ? 'var(--ink-2)' : Number(v) < 0 ? 'var(--danger-ink)' : 'var(--good-ink)'
  const sinal = (v: number | string | null | undefined) => (v != null && Number(v) > 0 ? '+' : '')
  const linkDoOrcamento = `/app/orcamento/cronograma${data.planejado ? `?orcamento=${data.planejado.orcamento}` : ''}`

  function linha(l: LinhaDoAvanco & { codigo?: string; nome?: string; atividade?: number }, total = false) {
    const peso = total ? 750 : 400
    return (
      <tr key={l.atividade ?? 'obra'}>
        <td style={{ ...celula, fontWeight: total ? 750 : 650 }}>
          {total ? 'Obra' : (
            <button
              type="button"
              onClick={() => l.atividade != null && selecionar({ tipo: 'atividade', id: l.atividade })}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--ink)', fontSize: 12.5, fontWeight: 650, textAlign: 'left' }}
            >
              <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-3)' }}>{l.codigo}</span> {l.nome}
            </button>
          )}
        </td>
        <td style={{ ...numero, fontWeight: peso }}>{pct(l.previsto_pct)}</td>
        <td style={{ ...numero, fontWeight: peso }}>{pct(l.realizado_pct)}</td>
        <td style={{ ...numero, fontWeight: peso, color: tom(l.desvio_pct) }}>{sinal(l.desvio_pct)}{pct(l.desvio_pct)}</td>
        {data!.tem_dinheiro && (
          <>
            <td style={{ ...numero, fontWeight: peso }}>{reais(l.valor_orcado)}</td>
            <td style={{ ...numero, fontWeight: peso }}>{reais(l.valor_realizado)}</td>
            <td style={{ ...numero, fontWeight: peso }}>{reais(l.valor_previsto)}</td>
            <td style={{ ...numero, fontWeight: peso, color: tom(l.valor_desvio) }}>{sinal(l.valor_desvio)}{reais(l.valor_desvio)}</td>
          </>
        )}
        {comPlanejado && (
          <>
            <td style={{ ...numero, fontWeight: peso }}>{reais(l.valor_planejado)}</td>
            <td style={{ ...numero, fontWeight: peso, color: tom(l.valor_desvio_planejado) }}>
              {sinal(l.valor_desvio_planejado)}{reais(l.valor_desvio_planejado)}
            </td>
          </>
        )}
      </tr>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 1240 }}>
      <GraficoEstilos />
      <div style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>
        <strong>O avanço físico-financeiro em {dateToBR(data.hoje)}.</strong> Realizado é o que o campo apontou; em
        reais, o valor orçado de cada atividade vezes o avanço dela. A régua é dupla: o <em>previsto</em> pelas datas
        do plano e o <em>planejado</em> no{' '}
        <Link to={linkDoOrcamento} style={{ color: 'var(--brand)', textDecoration: 'none' }}>
          cronograma físico-financeiro do Orçamento <ArrowUpRight size={11} style={{ verticalAlign: '-1px' }} />
        </Link>
        . O custo consumido fica na aba{' '}
        <Link to={`/app/pdca/o/${obraId}/controle?aba=custo`} style={{ color: 'var(--brand)', textDecoration: 'none' }}>
          Custo <ArrowUpRight size={11} style={{ verticalAlign: '-1px' }} />
        </Link>.
      </div>

      {data.tem_dinheiro && data.planejado == null && (
        <div style={{ padding: '9px 12px', borderRadius: 'var(--r-sm)', background: 'var(--accent-soft)', color: 'var(--accent-ink)', fontSize: 12.5 }}>
          O orçamento ainda não tem cronograma físico-financeiro, então não há planejado para comparar.{' '}
          <Link to={linkDoOrcamento} style={{ color: 'inherit', fontWeight: 650 }}>Montar no Orçamento</Link>.
        </div>
      )}

      <Card pad={false}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr>
                <th style={{ ...cabeca, textAlign: 'left' }} rowSpan={2}>Etapa</th>
                <th style={{ ...cabeca, textAlign: 'center', borderLeft: '1px solid var(--line-2)' }} colSpan={3}>Físico</th>
                {data.tem_dinheiro && (
                  <th style={{ ...cabeca, textAlign: 'center', borderLeft: '1px solid var(--line-2)' }} colSpan={4}>R$ contra o plano</th>
                )}
                {comPlanejado && (
                  <th style={{ ...cabeca, textAlign: 'center', borderLeft: '1px solid var(--line-2)' }} colSpan={2}>R$ contra o planejado</th>
                )}
              </tr>
              <tr>
                <th style={{ ...cabeca, textAlign: 'right' }} title="Físico previsto até hoje pelas datas do plano">Previsto</th>
                <th style={{ ...cabeca, textAlign: 'right' }} title="Físico apontado no campo">Realizado</th>
                <th style={{ ...cabeca, textAlign: 'right' }}>Desvio</th>
                {data.tem_dinheiro && (
                  <>
                    <th style={{ ...cabeca, textAlign: 'right' }} title="Valor orçado das atividades ligadas ao orçamento">Orçado</th>
                    <th style={{ ...cabeca, textAlign: 'right' }}>Realizado</th>
                    <th style={{ ...cabeca, textAlign: 'right' }} title="O que as datas do plano previam até hoje">Previsto</th>
                    <th style={{ ...cabeca, textAlign: 'right' }}>Desvio</th>
                  </>
                )}
                {comPlanejado && (
                  <>
                    <th style={{ ...cabeca, textAlign: 'right' }} title="Cronograma físico-financeiro do Orçamento até hoje (o mês corrente, pro rata)">Planejado</th>
                    <th style={{ ...cabeca, textAlign: 'right' }}>Desvio</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {data.linhas.length === 0 ? (
                <tr><td colSpan={11} style={{ padding: 18, textAlign: 'center', color: 'var(--ink-3)' }}>
                  Nenhuma atividade com peso ainda — sem item orçado nem peso informado não há o que medir.
                </td></tr>
              ) : data.linhas.map((l) => linha(l))}
              {data.linhas.length > 0 && linha(data.obra, true)}
            </tbody>
          </table>
        </div>
      </Card>

      {(data.folhas_sem_orcamento > 0 || data.folhas_sem_peso > 0 || data.folhas_sem_data > 0) && (
        <div style={{ fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          {data.folhas_sem_orcamento > 0 && <>{data.folhas_sem_orcamento} atividade(s) sem item orçado pesam no físico e ficam fora do R$. </>}
          {data.folhas_sem_peso > 0 && <>{data.folhas_sem_peso} sem peso, fora da conta. </>}
          {data.folhas_sem_data > 0 && <>{data.folhas_sem_data} sem data (plano não calculado) contam previsto zero.</>}
        </div>
      )}

      {serie.length > 1 && (
        <Card>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
            <div style={{ fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700, flex: 1 }}>
              Curva S — {regua === 'plano' ? 'previsto pelo plano × realizado (físico)' : 'planejado no Orçamento × realizado (R$)'}
            </div>
            <div role="radiogroup" aria-label="Comparar com" style={{ display: 'flex', gap: 2, background: 'var(--inset)', borderRadius: 'var(--r-sm)', padding: 2 }}>
              {([['plano', 'Datas do plano'], ['orcamento', 'Planejado no Orçamento']] as const).map(([chave, rotulo]) => (
                <button
                  key={chave}
                  type="button"
                  role="radio"
                  aria-checked={regua === chave}
                  disabled={chave === 'orcamento' && !comPlanejado}
                  title={chave === 'orcamento' && !comPlanejado ? 'O orçamento não tem cronograma físico-financeiro' : undefined}
                  onClick={() => setRegua(chave)}
                  style={{
                    border: 'none', borderRadius: 5, padding: '4px 9px', fontSize: 11.5, fontWeight: 650,
                    cursor: chave === 'orcamento' && !comPlanejado ? 'not-allowed' : 'pointer',
                    background: regua === chave ? 'var(--surface)' : 'transparent',
                    color: regua === chave ? 'var(--ink)' : 'var(--ink-3)',
                    boxShadow: regua === chave ? 'var(--shadow-sm)' : 'none',
                  }}
                >
                  {rotulo}
                </button>
              ))}
            </div>
          </div>
          <CurvaSGrafico serie={serie} />
          <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 6 }}>
            {data.curva?.ultimo_apontamento
              ? <>Último apontamento em {dateToBR(data.curva.ultimo_apontamento)} — dali em diante a linha do realizado só repete o último valor.</>
              : 'Nada apontado ainda: a linha do realizado fica em zero.'}
          </div>
        </Card>
      )}
    </div>
  )
}

/** A série do gráfico na régua escolhida.
 *
 *  - **plano**: o % físico acumulado previsto pelas datas × o realizado;
 *  - **orçamento**: o R$ acumulado planejado (parcelas) × o R$ realizado, os
 *    dois em % do total planejado — a mesma moeda dos dois lados. */
function serieDaCurva(data: AvancoFisicoFinanceiro, regua: Regua) {
  const pontos = data.curva?.pontos ?? []
  if (regua === 'plano' || !data.planejado) {
    // Depois do último apontamento o servidor manda o realizado nulo; o gráfico
    // repete o último valor (e a legenda diz a data), em vez de cair a zero.
    let ultimo = 0
    let ultimoReais = 0
    return pontos.map((p) => {
      if (p.realizado != null) ultimo = p.realizado
      if (p.realizado_reais != null) ultimoReais = Number(p.realizado_reais)
      return {
        competencia: p.rotulo,
        previstoPct: p.previsto,
        realizadoPct: ultimo,
        previsto: Number(p.previsto_reais ?? 0),
        realizado: ultimoReais,
      }
    })
  }
  const total = Number(data.planejado.total) || 0
  const realizadoPorMes = new Map(pontos.map((p) => [p.iso.slice(0, 7), p.realizado_reais]))
  const planejadoPorMes = new Map(data.planejado.mensal.map((m) => [m.mes.slice(0, 7), m]))
  const meses = [...new Set([...planejadoPorMes.keys(), ...realizadoPorMes.keys()])].sort()
  let planejado = 0
  let realizado = 0
  return meses.map((mes) => {
    const m = planejadoPorMes.get(mes)
    if (m) planejado = Number(m.acumulado)
    const r = realizadoPorMes.get(mes)
    if (r != null) realizado = Number(r)
    return {
      competencia: mesBR(`${mes}-01`),
      previstoPct: total > 0 ? (planejado / total) * 100 : 0,
      realizadoPct: total > 0 ? (realizado / total) * 100 : 0,
      previsto: planejado,
      realizado,
    }
  })
}
