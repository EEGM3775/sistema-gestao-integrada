import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowUpRight, HardHat } from 'lucide-react'
import { Card, Empty, Loading, Num, SectionHead } from '@/components/malha'
import { BotaoExportar } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { formatBRL, apiDecimalToCents } from '@/utils/money'
import { useDreObra, useFinanceiroObras } from '../hooks/useFinanceiroObra'
import type { DreObra } from '../types'

const reais = (v: string | null | undefined) => (v == null ? '—' : formatBRL(apiDecimalToCents(v)))
const tom = (v: string) => (Number(v) < 0 ? 'var(--danger-ink)' : 'var(--ink)')
const mesBR = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString('pt-BR', { month: 'short', year: 'numeric' })

/**
 * D.1.4 — financeiro por obra: a DRE gerencial de cada obra.
 *
 * A obra chega aqui pela própria conta (`obra`/`etapa`) ou pelo rateio a um
 * centro de custo com obra; a medição do PDCA já nasce com ela. Conta sem obra
 * não entra — a regra está em `backend/moduloerp/financeiro_obra.py`, e a tela
 * só a mostra. O orçado vem do Orçamento (aprovado vigente) para quem usa aquele
 * módulo; o resto vê o porquê, não um zero.
 */
export default function FinanceiroObraPage() {
  const { obraId } = useParams()
  const navigate = useNavigate()
  const lista = useFinanceiroObras()
  const escolhida = obraId ? Number(obraId) : lista.data?.[0]?.obra ?? null

  return (
    <div className="px-6 py-6 flex flex-col gap-5" style={{ color: 'var(--ink-2)' }}>
      <div>
        <Link to="/app/erp" className="inline-flex items-center gap-1.5 text-xs font-semibold mb-2" style={{ color: 'var(--ink-3)', textDecoration: 'none' }}>
          <ArrowLeft size={14} /> ERP / Financeiro
        </Link>
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-xl font-bold" style={{ color: 'var(--ink)' }}>Financeiro por obra</h1>
          <BotaoExportar tam="md" recurso="erp.financeiro_obras" />
        </div>
        <p className="text-xs" style={{ color: 'var(--ink-3)' }}>
          Receita, custo e resultado de cada obra — pela obra da conta ou pelo rateio ao centro de custo dela.
        </p>
      </div>

      {lista.isLoading && <Loading o="as obras" />}
      {lista.data && lista.data.length === 0 && (
        <Empty>
          <HardHat size={22} />
          Nenhuma conta tem obra ainda. Escolha a obra (e a etapa) ao lançar uma conta, ou rateie para um centro de
          custo ligado à obra — as medições do PDCA já chegam com ela.
        </Empty>
      )}

      {lista.data && lista.data.length > 0 && (
        <div className="grid gap-5" style={{ gridTemplateColumns: 'minmax(240px, 300px) 1fr', alignItems: 'start' }}>
          <Card pad={false}>
            {lista.data.map(l => (
              <button key={l.obra} type="button" onClick={() => navigate(`/app/erp/obras/${l.obra}`)}
                className="w-full text-left"
                style={{
                  padding: '10px 14px', borderBottom: '1px solid var(--line)', cursor: 'pointer',
                  background: l.obra === escolhida ? 'var(--surface-2)' : 'transparent',
                }}>
                <div className="text-sm font-semibold" style={{ color: 'var(--ink)' }}>{l.obra_nome}</div>
                <div className="flex justify-between text-xs mt-0.5" style={{ color: 'var(--ink-3)' }}>
                  <span>custo {reais(l.custo)}</span>
                  <span style={{ color: tom(l.resultado) }}>resultado {reais(l.resultado)}</span>
                </div>
              </button>
            ))}
          </Card>
          {escolhida != null && <Dre obraId={escolhida} />}
        </div>
      )}
    </div>
  )
}

function Dre({ obraId }: { obraId: number }) {
  const dre = useDreObra(obraId)
  const { hasModule } = useAuth()
  if (dre.isLoading) return <Loading o="a DRE da obra" />
  if (!dre.data) return <Empty>Não foi possível carregar a DRE desta obra.</Empty>
  const d = dre.data

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-lg font-bold" style={{ color: 'var(--ink)' }}>{d.obra_nome}</h2>
        <div className="flex gap-3 text-xs font-semibold">
          <Link to={`/app/erp/contas-a-pagar?obra=${d.obra}&obra_nome=${encodeURIComponent(d.obra_nome)}`} style={{ color: 'var(--ink-3)' }}>Contas a pagar da obra</Link>
          {hasModule('pdca') && (
            <Link to={`/app/pdca/o/${d.obra}/controle?aba=custo`} className="inline-flex items-center gap-1" style={{ color: 'var(--ink-3)' }}>
              Custo da obra no Controle (PDCA) <ArrowUpRight size={12} />
            </Link>
          )}
        </div>
      </div>

      <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))' }}>
        <Bloco titulo="Receita" linhas={[['Faturado', d.receita.faturado], ['Recebido', d.receita.recebido], ['A receber', d.receita.a_receber]]} />
        <Bloco titulo="Custo" linhas={[['Apropriado', d.custo.apropriado], ['Pago', d.custo.pago], ['A pagar', d.custo.a_pagar]]} />
        <Bloco titulo="Resultado" linhas={[['Competência', d.resultado.competencia], ['Caixa', d.resultado.caixa]]}
          rodape={d.resultado.margem_pct != null ? `margem ${d.resultado.margem_pct}% do faturado` : 'sem receita lançada na obra'} />
        <Orcado d={d} />
      </div>

      <Card>
        <SectionHead sub="Custo apropriado contra o orçado de cada etapa">Por etapa</SectionHead>
        {d.por_etapa.length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--ink-3)' }}>Nenhuma etapa com custo ou orçado.</p>
        ) : (
          <table className="w-full text-sm mt-2">
            <thead>
              <tr style={{ color: 'var(--ink-3)', textAlign: 'right' }}>
                <th style={{ textAlign: 'left', fontWeight: 600 }}>Etapa</th>
                <th style={{ fontWeight: 600 }}>Orçado</th><th style={{ fontWeight: 600 }}>Apropriado</th>
                <th style={{ fontWeight: 600 }}>Pago</th><th style={{ fontWeight: 600 }}>Consumido</th>
              </tr>
            </thead>
            <tbody>
              {d.por_etapa.map(l => (
                <tr key={l.etapa ?? 'sem'} style={{ borderTop: '1px solid var(--line)', textAlign: 'right' }}>
                  <td style={{ textAlign: 'left', padding: '6px 0' }}>{l.etapa_nome}</td>
                  <td><Num>{reais(l.orcado)}</Num></td>
                  <td><Num>{reais(l.apropriado)}</Num></td>
                  <td><Num>{reais(l.pago)}</Num></td>
                  <td><Num tone={l.consumido_pct && Number(l.consumido_pct) > 100 ? 'var(--danger-ink)' : undefined}>
                    {l.consumido_pct != null ? `${l.consumido_pct}%` : '—'}
                  </Num></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card>
        <SectionHead sub="Entradas e saídas de caixa da obra, pelas baixas">Mês a mês</SectionHead>
        {d.mensal.length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--ink-3)' }}>Nenhuma baixa ainda.</p>
        ) : (
          <table className="w-full text-sm mt-2">
            <thead>
              <tr style={{ color: 'var(--ink-3)', textAlign: 'right' }}>
                <th style={{ textAlign: 'left', fontWeight: 600 }}>Mês</th>
                <th style={{ fontWeight: 600 }}>Entradas</th><th style={{ fontWeight: 600 }}>Saídas</th>
                <th style={{ fontWeight: 600 }}>Saldo acumulado</th>
              </tr>
            </thead>
            <tbody>
              {d.mensal.map(m => (
                <tr key={m.mes} style={{ borderTop: '1px solid var(--line)', textAlign: 'right' }}>
                  <td style={{ textAlign: 'left', padding: '6px 0' }}>{mesBR(m.mes)}</td>
                  <td><Num>{reais(m.entradas)}</Num></td>
                  <td><Num>{reais(m.saidas)}</Num></td>
                  <td><Num tone={tom(m.saldo_acumulado)}>{reais(m.saldo_acumulado)}</Num></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}

function Bloco({ titulo, linhas, rodape }: { titulo: string; linhas: [string, string][]; rodape?: string }) {
  return (
    <Card>
      <div className="text-xs font-semibold uppercase" style={{ color: 'var(--ink-3)', letterSpacing: '0.05em' }}>{titulo}</div>
      {linhas.map(([rotulo, valor]) => (
        <div key={rotulo} className="flex justify-between items-baseline mt-1.5">
          <span className="text-xs">{rotulo}</span>
          <Num size={rotulo === linhas[0][0] ? 16 : 13} weight={rotulo === linhas[0][0] ? 700 : 500} tone={tom(valor)}>{reais(valor)}</Num>
        </div>
      ))}
      {rodape && <p className="text-xs mt-2" style={{ color: 'var(--ink-3)' }}>{rodape}</p>}
    </Card>
  )
}

function Orcado({ d }: { d: DreObra }) {
  if (!d.orcado) {
    return (
      <Card>
        <div className="text-xs font-semibold uppercase" style={{ color: 'var(--ink-3)', letterSpacing: '0.05em' }}>Orçado</div>
        <p className="text-xs mt-2" style={{ color: 'var(--ink-3)', lineHeight: 1.5 }}>
          {d.orcado_disponivel
            ? 'Esta obra não tem orçamento aprovado no módulo Orçamento.'
            : 'O orçado vem do módulo Orçamento, que não está no seu acesso.'}
        </p>
      </Card>
    )
  }
  return (
    <Bloco titulo={`Orçado · v${d.orcado.versao}`}
      linhas={[['Custo direto', d.orcado.custo_direto], ['Com BDI', d.orcado.com_bdi]]}
      rodape="orçamento aprovado vigente" />
  )
}
