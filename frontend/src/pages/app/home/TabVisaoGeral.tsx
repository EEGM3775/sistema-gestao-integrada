import { Link } from 'react-router-dom'
import { ArrowRight, Gauge } from 'lucide-react'
import { Card, Empty, KpiTile, Loading, SectionHead } from '@/components/malha'
import { ListaDecisoes } from './TabDecisoes'
import { QuotaMeter } from './QuotaMeter'
import type { useHomeResumo } from './useHomeResumo'

type Resumo = ReturnType<typeof useHomeResumo>

/**
 * A visão geral do hub: o estado do negócio num relance.
 *
 * Os KPIs são **compostos** a partir dos agregados que cada módulo já calcula no
 * backend — o hub não soma nada por conta própria e não exibe zero por um módulo
 * que o usuário não acessa. Onde ainda não existe fonte (avanço físico depende
 * do PDCA; DRE por obra é a sub-fase D.1.4 do ERP), o mosaico diz **"em breve"**
 * em vez de inventar — é a regra de dados honestos da régua (§1.6.4).
 */
export function TabVisaoGeral({ r }: { r: Resumo }) {
  const { kpis, decisoes, quotas, plano, carregando, fontes } = r
  const semFonteAlguma = kpis.length === 0 && !carregando

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 26 }}>
      {/* ── Indicadores ─────────────────────────────────────────────────── */}
      <section>
        <SectionHead sub="Agregados calculados no backend de cada módulo — só aparece o que você acessa">
          Indicadores
        </SectionHead>

        {carregando && kpis.length === 0 ? (
          <Loading o="os indicadores" />
        ) : semFonteAlguma ? (
          <Empty>
            Seu usuário ainda não acessa nenhum módulo com agregado próprio. Assim que o financeiro,
            suprimentos ou estoque estiverem disponíveis, os números aparecem aqui.
          </Empty>
        ) : (
          <div
            style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(212px, 1fr))' }}
          >
            {kpis.map((k) => (
              <KpiTile key={k.id} label={k.label} valor={k.valor} base={k.base} origem={k.origem} to={k.rota} />
            ))}

            {/* Lacunas assumidas: o número não existe, e a tela diz isso. */}
            <KpiTile
              label="Avanço físico × previsto"
              valor={null}
              pendente
              base="depende do módulo de planejamento (PDCA)"
            />
            <KpiTile
              label="DRE por obra"
              valor={null}
              pendente
              base="sub-fase D.1.4 do ERP — cruza SCM, SIL e medições"
            />
          </div>
        )}
      </section>

      {/* ── Decisão + plano ─────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gap: 20, gridTemplateColumns: 'minmax(0, 1.7fr) minmax(260px, 1fr)' }}>
        <section style={{ minWidth: 0 }}>
          <SectionHead
            sub="Vencimentos, aprovações e rupturas que já passaram do ponto de esperar"
            right={
              decisoes.length > 5 ? (
                <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                  mostrando 5 de {decisoes.length}
                </span>
              ) : undefined
            }
          >
            Requer sua decisão
          </SectionHead>
          <ListaDecisoes decisoes={decisoes} limite={5} />
        </section>

        <section style={{ minWidth: 0 }}>
          <SectionHead sub="O limite aparece antes de travar o cadastro, não depois">Seu plano</SectionHead>
          <Card style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Gauge size={16} style={{ color: 'var(--ink-3)' }} />
              <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>
                {plano.data?.plano.nome ?? '—'}
              </span>
            </div>

            {quotas.length === 0 ? (
              <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Sem medidores para exibir.</span>
            ) : (
              quotas.map((q) => <QuotaMeter key={q.recurso} q={q} />)
            )}

            {plano.data?.proximo_plano && (
              <div style={{ borderTop: '1px solid var(--line-2)', paddingTop: 12, fontSize: 12, color: 'var(--ink-3)' }}>
                Próximo degrau: <b style={{ color: 'var(--ink-2)' }}>{plano.data.proximo_plano.nome}</b>
              </div>
            )}
          </Card>
        </section>
      </div>

      {/* ── Procedência ─────────────────────────────────────────────────── */}
      <Card style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: 13 }}>
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
          Números vindos de: <b style={{ color: 'var(--ink-2)' }}>plano</b>
          {fontes.erp && <>, <b style={{ color: 'var(--ink-2)' }}>ERP</b></>}
          {fontes.scm && <>, <b style={{ color: 'var(--ink-2)' }}>SCM</b></>}
          {fontes.sil && <>, <b style={{ color: 'var(--ink-2)' }}>SIL</b></>}
          . Cada módulo calcula o seu agregado no backend.
        </span>
        <Link
          to="/app/dashboard?aba=modulos"
          style={{ marginLeft: 'auto', fontSize: 11.5, fontWeight: 600, color: 'var(--brand)', display: 'inline-flex', alignItems: 'center', gap: 4 }}
        >
          Ver todos os módulos <ArrowRight size={12} />
        </Link>
      </Card>
    </div>
  )
}
