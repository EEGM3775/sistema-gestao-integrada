import { useAuth } from '@/hooks/useAuth'
import { Gauge } from 'lucide-react'
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
 *
 * **Plano e quota não aparecem para o supervisor da plataforma**
 * *(decisão do dono, 22/08/2026)*. Eles descrevem o que uma **empresa** contratou:
 * quanto ela pode cadastrar, quando trava, qual o próximo degrau de venda. O
 * supervisor não é cliente — mostrar "Seu plano: Profissional" e "limite de
 * clientes atingido" para ele é oferecer um upsell a quem vende o produto, e
 * transformar um número de fixture num alarme que ele não tem por que resolver.
 */
export function TabVisaoGeral({ r }: { r: Resumo }) {
  const { kpis, decisoes, quotas, plano, carregando, fontes } = r
  const { isPlatformAdmin } = useAuth()
  const semFonteAlguma = kpis.length === 0 && !carregando
  // Sem o painel de plano, a linha volta a ser de uma coluna só — senão
  // sobraria um vão do tamanho do card que não está lá.
  const colunas = isPlatformAdmin
    ? 'minmax(0, 1fr)'
    : 'minmax(0, 1.7fr) minmax(260px, 1fr)'

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
          </div>
        )}
      </section>

      {/* ── Decisão + plano ─────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gap: 20, gridTemplateColumns: colunas }}>
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

        {!isPlatformAdmin && (
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
        )}
      </div>

      {/* ── Procedência ─────────────────────────────────────────────────── */}
      <Card style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: 13 }}>
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
          Números vindos de:{' '}
          {!isPlatformAdmin && <b style={{ color: 'var(--ink-2)' }}>plano</b>}
          {!isPlatformAdmin && fontes.erp && ', '}
          {fontes.erp && <b style={{ color: 'var(--ink-2)' }}>ERP</b>}
          {fontes.scm && <>, <b style={{ color: 'var(--ink-2)' }}>SCM</b></>}
          {fontes.sil && <>, <b style={{ color: 'var(--ink-2)' }}>SIL</b></>}
          {fontes.pdca && <>, <b style={{ color: 'var(--ink-2)' }}>PDCA</b></>}
          . Cada módulo calcula o seu agregado no backend.
        </span>
      </Card>
    </div>
  )
}
