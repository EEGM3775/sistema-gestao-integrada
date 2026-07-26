import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ExternalLink, FileText } from 'lucide-react'
import { Card, Empty, Loading, Pill } from '@/components/malha'
import { buscarFinanceiroCliente } from './api'
import type { ParcelaCliente } from './types'

const brl = (v: string | number) =>
  Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const data = (v?: string | null) => (v ? v.slice(0, 10).split('-').reverse().join('/') : '—')

const STATUS: Record<string, { rotulo: string; kind: 'good' | 'info' | 'danger' | 'slate' }> = {
  QUITADO: { rotulo: 'Quitado', kind: 'good' },
  PARCIAL: { rotulo: 'Parcial', kind: 'info' },
  ABERTO: { rotulo: 'Em aberto', kind: 'slate' },
  CANCELADO: { rotulo: 'Cancelado', kind: 'slate' },
}

/**
 * Histórico de pagamento do cliente — parcela a parcela, com o boleto de cada
 * uma e a unidade que ela paga.
 *
 * O 403 aqui não é erro de tela: é a permissão de cobranças faltando
 * (`erp.cobranca.view`). A aba diz isso em português em vez de mostrar um vazio
 * que pareceria "cliente sem parcelas".
 */
export function AbaFinanceiro({ clienteId }: { clienteId: number }) {
  const consulta = useQuery({
    queryKey: ['clientes', 'financeiro', clienteId],
    queryFn: () => buscarFinanceiroCliente(clienteId),
    retry: false,
  })

  if (consulta.isLoading) return <Loading o="o histórico de pagamento" />

  if (consulta.isError) {
    const status = (consulta.error as { response?: { status?: number } })?.response?.status
    return (
      <Empty>
        {status === 403
          ? 'Ver parcelas e valores exige a permissão de cobranças (erp.cobranca.view). Peça ao administrador da sua empresa.'
          : 'Não foi possível carregar o histórico de pagamento agora.'}
      </Empty>
    )
  }

  const { resumo, parcelas } = consulta.data!

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
        <Indicador rotulo="Situação" valor={resumo.adimplente ? 'Adimplente' : 'Inadimplente'}
          tom={resumo.adimplente ? 'var(--good-ink)' : 'var(--danger-ink)'} />
        <Indicador rotulo="Em aberto" valor={brl(resumo.valorAberto)} />
        <Indicador rotulo="Em atraso" valor={brl(resumo.valorAtraso)}
          tom={Number(resumo.valorAtraso) > 0 ? 'var(--danger-ink)' : undefined}
          apoio={`${resumo.parcelasAtraso} de ${resumo.parcelasTotal} parcelas`} />
        <Indicador rotulo="Já pago" valor={brl(resumo.valorPago)} />
      </div>

      {parcelas.length === 0 ? (
        <Empty>Este cliente ainda não tem parcelas lançadas no financeiro.</Empty>
      ) : (
        <Card pad={false}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr style={{ background: 'var(--surface-2)', borderBottom: '1px solid var(--line)' }}>
                  {['Vencimento', 'Descrição', 'Unidade', 'Valor', 'Pago', 'Saldo', 'Situação', 'Boleto'].map(h => (
                    <th key={h} style={{
                      textAlign: h === 'Valor' || h === 'Pago' || h === 'Saldo' ? 'right' : 'left',
                      padding: '9px 12px', fontSize: 10.5, letterSpacing: '0.06em',
                      textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700,
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {parcelas.map(p => <LinhaParcela key={p.id} p={p} />)}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}

function LinhaParcela({ p }: { p: ParcelaCliente }) {
  const st = STATUS[p.status] ?? { rotulo: p.status, kind: 'slate' as const }
  const atrasada = p.diasAtraso > 0
  return (
    <tr style={{ borderBottom: '1px solid var(--line-2)' }}>
      <td className="num" style={{ padding: '9px 12px', color: atrasada ? 'var(--danger-ink)' : 'var(--ink-2)' }}>
        {data(p.vencimento)}
        {atrasada && (
          <span title={`${p.diasAtraso} dias em atraso`} style={{ marginLeft: 6, display: 'inline-flex', verticalAlign: 'middle' }}>
            <AlertTriangle size={12} />
          </span>
        )}
      </td>
      <td style={{ padding: '9px 12px', color: 'var(--ink)' }}>{p.descricao}</td>
      <td className="num" style={{ padding: '9px 12px', color: 'var(--ink-3)' }}>
        {p.unidade ?? '—'}
      </td>
      <td className="num" style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--ink)' }}>{brl(p.valor)}</td>
      <td className="num" style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--ink-3)' }}>{brl(p.pago)}</td>
      <td className="num" style={{ padding: '9px 12px', textAlign: 'right', fontWeight: 700, color: Number(p.saldo) > 0 ? 'var(--ink)' : 'var(--ink-3)' }}>
        {brl(p.saldo)}
      </td>
      <td style={{ padding: '9px 12px' }}><Pill kind={st.kind}>{st.rotulo}</Pill></td>
      <td style={{ padding: '9px 12px' }}>
        {p.boleto ? (
          p.boleto.urlPdf ? (
            <a
              href={p.boleto.urlPdf} target="_blank" rel="noopener noreferrer"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: 'var(--brand)', fontWeight: 600 }}
              title={p.boleto.linhaDigitavel ?? undefined}
            >
              <FileText size={13} /> {p.boleto.status} <ExternalLink size={11} />
            </a>
          ) : (
            <span style={{ color: 'var(--ink-3)' }}>{p.boleto.status}</span>
          )
        ) : (
          <span style={{ color: 'var(--ink-3)' }}>—</span>
        )}
      </td>
    </tr>
  )
}

function Indicador({ rotulo, valor, apoio, tom }: { rotulo: string; valor: string; apoio?: string; tom?: string }) {
  return (
    <Card style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <span style={{ fontSize: 10.5, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }}>
        {rotulo}
      </span>
      <span className="num" style={{ fontSize: 19, fontWeight: 700, color: tom ?? 'var(--ink)' }}>{valor}</span>
      {apoio && <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{apoio}</span>}
    </Card>
  )
}
