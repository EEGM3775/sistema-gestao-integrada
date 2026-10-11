import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight } from 'lucide-react'
import { Card, Empty, Loading, Pill, SectionHead } from '@/components/malha'
import { controle } from '../api/controleApi'
import { pdcaKeys } from '../api/queryKeys'
import { PainelCusto } from './PainelCusto'

const reais = (v: string | number | null | undefined) =>
  v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
const indice = (v: string | null | undefined) => (v == null ? '—' : Number(v).toFixed(2).replace('.', ','))
const pct = (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(1).replace('.', ',')}%`)
const mono = { fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' as const }

/** Índice < 1 é ruim (gasto acima do que o avanço justifica, ou atraso);
 *  a cor só aparece quando há índice — nulo fica neutro. */
const tomDoIndice = (v: string | null | undefined) =>
  v == null ? 'var(--ink-3)' : Number(v) < 0.95 ? 'var(--danger-ink)' : Number(v) > 1.05 ? 'var(--good-ink)' : 'var(--ink)'

/** **O custo da obra contra o plano** — as colunas que não se somam, o valor
 *  agregado e para onde o custo final está indo. Os números de cada coluna
 *  levam ao módulo que é dono deles: o sistema conversa na tela como conversa
 *  no backend. */
export function PainelControleDeCusto({ obraId, cronogramaId }: { obraId: number; cronogramaId?: number }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: pdcaKeys.controle.custo(obraId),
    queryFn: () => controle.custo(obraId),
  })
  if (isLoading) return <Loading o="o custo da obra" />
  if (isError || !data) return <div style={{ padding: 22 }}><Card><Empty>Não foi possível apurar o custo da obra.</Empty></Card></div>

  const c = data.colunas
  const va = data.valor_agregado
  const colunas: { rotulo: string; valor: string | null; apoio: string; to?: string; tom?: string }[] = [
    { rotulo: 'Orçado', valor: c.orcado, apoio: data.orcamento ? `custo direto · v${data.orcamento_versao}` : 'sem orçamento aprovado',
      to: data.orcamento ? `/app/orcamento/orcar/orcamento/${data.orcamento}` : '/app/orcamento' },
    { rotulo: 'Comprometido', valor: c.comprometido, apoio: `pedidos ${reais(c.comprometido_pedidos)} · contratos ${reais(c.comprometido_contratos)}`,
      to: '/app/scm', tom: c.estourado ? 'var(--danger-ink)' : undefined },
    { rotulo: 'Aplicado', valor: c.aplicado, apoio: 'material que saiu do estoque', to: '/app/sil' },
    { rotulo: 'Medido', valor: c.medido, apoio: 'serviço de empreiteiro aprovado', to: `/app/pdca/o/${obraId}/medicao` },
    { rotulo: 'Realizado', valor: c.realizado, apoio: 'pago no financeiro', to: '/app/erp' },
    { rotulo: 'Saldo', valor: c.saldo, apoio: 'orçado − comprometido', tom: c.saldo != null && Number(c.saldo) < 0 ? 'var(--danger-ink)' : undefined },
  ]
  const celula = { padding: '7px 11px', borderBottom: '1px solid var(--line-2)', whiteSpace: 'nowrap' as const }
  const num = { ...celula, ...mono, textAlign: 'right' as const }
  const cab = { ...celula, fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase' as const, color: 'var(--ink-3)', background: 'var(--surface-2)' }

  return (
    <div style={{ padding: '18px 22px 40px', display: 'flex', flexDirection: 'column', gap: 22 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10 }}>
        {colunas.map((k) => {
          const corpo = (
            <Card style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-3)', display: 'flex', alignItems: 'center', gap: 4 }}>
                {k.rotulo}{k.to && <ArrowUpRight size={11} />}
              </span>
              <span style={{ ...mono, fontSize: 19, fontWeight: 700, color: k.tom ?? 'var(--ink)' }}>{reais(k.valor)}</span>
              <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{k.apoio}</span>
            </Card>
          )
          return k.to
            ? <Link key={k.rotulo} to={k.to} style={{ textDecoration: 'none', color: 'inherit' }}>{corpo}</Link>
            : <div key={k.rotulo}>{corpo}</div>
        })}
      </div>

      <div>
        <SectionHead sub="custo incorrido = material aplicado + serviço medido, contra o avanço físico do plano">
          Valor agregado — para onde o custo final está indo
        </SectionHead>
        <Card style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 16 }}>
          <Medida rotulo="Avanço previsto" valor={pct(va.previsto_pct)} />
          <Medida rotulo="Avanço realizado" valor={pct(va.realizado_pct)} />
          <Medida rotulo="Valor planejado (VP)" valor={reais(va.vp)} />
          <Medida rotulo="Valor agregado (VA)" valor={reais(va.va)} />
          <Medida rotulo="Custo incorrido (CR)" valor={reais(va.cr)} />
          <Medida rotulo="IDC (custo)" valor={indice(va.idc)} tom={tomDoIndice(va.idc)} dica="VA ÷ CR — abaixo de 1, gasta-se mais do que o avanço justifica" />
          <Medida rotulo="IDP (prazo)" valor={indice(va.idp)} tom={tomDoIndice(va.idp)} dica="VA ÷ VP — abaixo de 1, a obra está atrás do plano" />
          <Medida rotulo="Custo a incorrer" valor={reais(va.a_incorrer)} dica="(orçado − VA) ÷ IDC" />
          <Medida rotulo="Custo final projetado" valor={reais(va.ent)} forte />
          <Medida rotulo="Variação no término" valor={reais(va.vnt)} forte
            tom={va.vnt == null ? undefined : Number(va.vnt) < 0 ? 'var(--danger-ink)' : 'var(--good-ink)'}
            dica="orçado − custo final projetado; negativo = estouro previsto" />
        </Card>
        {va.idc == null && (
          <p style={{ fontSize: 11.5, color: 'var(--ink-3)', margin: '8px 2px 0' }}>
            Sem índice ainda: {data.plano == null ? 'a obra não tem plano no PDCA' : 'falta avanço apontado ou custo incorrido'} — o
            sistema não projeta custo final sem as duas pontas.
          </p>
        )}
      </div>

      {data.etapas.length > 0 && (
        <div>
          <SectionHead sub="o mesmo valor agregado, etapa a etapa">Por etapa</SectionHead>
          <Card pad={false} style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr>
                  {['Etapa', 'Orçado', 'Previsto', 'Feito', 'VP', 'VA', 'Incorrido', 'IDC', 'IDP', 'Custo final'].map((h, i) => (
                    <th key={h} style={{ ...cab, textAlign: i === 0 ? 'left' : 'right' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.etapas.map((e) => (
                  <tr key={e.etapa}>
                    <td style={{ ...celula, fontWeight: 600, color: 'var(--ink)' }}>{e.etapa_nome}</td>
                    <td style={num}>{reais(e.orcado)}</td>
                    <td style={num}>{pct(e.previsto_pct)}</td>
                    <td style={num}>{pct(e.realizado_pct)}</td>
                    <td style={num}>{reais(e.vp)}</td>
                    <td style={num}>{reais(e.va)}</td>
                    <td style={num} title={`aplicado ${reais(e.aplicado)} · medido ${reais(e.medido)}`}>{reais(e.cr)}</td>
                    <td style={{ ...num, color: tomDoIndice(e.idc), fontWeight: 650 }}>{indice(e.idc)}</td>
                    <td style={{ ...num, color: tomDoIndice(e.idp), fontWeight: 650 }}>{indice(e.idp)}</td>
                    <td style={{ ...num, fontWeight: 650, color: e.ent && Number(e.ent) > Number(e.orcado) ? 'var(--danger-ink)' : 'var(--ink)' }}>{reais(e.ent)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          {Number(data.sem_etapa) > 0 && (
            <p style={{ fontSize: 11.5, color: 'var(--ink-3)', margin: '8px 2px 0' }}>
              {reais(data.sem_etapa)} incorridos sem etapa (saída de estoque ou item medido sem etapa) entram no total da obra, não nas linhas.
            </p>
          )}
        </div>
      )}

      {data.contratos.length > 0 && (
        <div>
          <SectionHead sub="o que já se contratou com empreiteiros">Contratos no comprometido</SectionHead>
          <Card pad={false}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <tbody>
                {data.contratos.map((ct) => (
                  <tr key={ct.contrato}>
                    <td style={celula}>
                      <Link to={`/app/pdca/o/${obraId}/medicao?contrato=${ct.contrato}`} style={{ color: 'var(--ink)', fontWeight: 600, textDecoration: 'none' }}>
                        {ct.numero}
                      </Link>{' '}
                      <span style={{ color: 'var(--ink-3)' }}>{ct.fornecedor}</span>
                    </td>
                    <td style={{ ...celula, width: 1 }}><Pill kind={ct.status === 'vigente' ? 'good' : 'slate'}>{ct.status}</Pill></td>
                    <td style={{ ...num, width: 1 }}>{reais(ct.valor)}</td>
                    <td style={{ ...celula, width: 1, fontSize: 11.5, color: 'var(--ink-3)' }}>
                      {ct.conta ? 'conta no comprometido' : 'já no pedido de serviço'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}

      {cronogramaId != null && (
        <div>
          <SectionHead sub="pedido e recebido rateados pelo consumo de cada insumo">Por atividade do plano</SectionHead>
          <PainelCusto cronogramaId={cronogramaId} />
        </div>
      )}
      <p style={{ fontSize: 11.5, color: 'var(--ink-3)', margin: 0 }}>{data.nota}</p>
    </div>
  )
}

function Medida({ rotulo, valor, tom, dica, forte }: {
  rotulo: string; valor: string; tom?: string; dica?: string; forte?: boolean
}) {
  return (
    <div title={dica} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-3)' }}>{rotulo}</span>
      <span style={{ ...mono, fontSize: forte ? 18 : 15, fontWeight: forte ? 750 : 650, color: tom ?? 'var(--ink)' }}>{valor}</span>
    </div>
  )
}
