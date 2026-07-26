import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, HardHat } from 'lucide-react'
import { Card, EmBreve, Empty, Loading, Pill, SectionHead } from '@/components/malha'
import { buscarObraCliente } from './api'
import type { ObraDoCliente } from './types'

const data = (v?: string | null) => (v ? v.slice(0, 10).split('-').reverse().join('/') : '—')

const STATUS_OBRA: Record<string, { rotulo: string; kind: 'good' | 'info' | 'slate' | 'danger' }> = {
  planejamento: { rotulo: 'Planejamento', kind: 'slate' },
  em_execucao: { rotulo: 'Em execução', kind: 'info' },
  concluida: { rotulo: 'Concluída', kind: 'good' },
  paralisada: { rotulo: 'Paralisada', kind: 'danger' },
  cancelada: { rotulo: 'Cancelada', kind: 'slate' },
}

/**
 * O que o cliente comprou está sendo construído — e ele acompanha daqui.
 *
 * É a integração entre módulos aparecendo na tela (frontend.md §1.6.6): a
 * aquisição leva ao empreendimento, que leva à obra e às suas etapas, com link
 * clicável para o módulo de Obras. O percentual é **média das etapas** e vem
 * declarado assim; obra sem etapa cadastrada mostra "em breve" em vez de 0%,
 * que faria uma obra tocada parecer parada.
 */
export function AbaObra({ clienteId }: { clienteId: number }) {
  const consulta = useQuery({
    queryKey: ['clientes', 'obra', clienteId],
    queryFn: () => buscarObraCliente(clienteId),
  })

  if (consulta.isLoading) return <Loading o="o andamento das obras" />
  if (consulta.isError) return <Empty>Não foi possível carregar o andamento das obras agora.</Empty>

  const { unidades, obras } = consulta.data!

  if (unidades.length === 0) {
    return <Empty>Este cliente ainda não tem aquisição registrada — sem unidade, não há obra para acompanhar.</Empty>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <section>
        <SectionHead sub="O que este cliente comprou">Unidades</SectionHead>
        <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))' }}>
          {unidades.map(u => (
            <Card key={u.id} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span className="num" style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>{u.unidade}</span>
              <Link
                to={`/app/empreendimentos/${u.empreendimentoId}`}
                style={{ fontSize: 12, color: 'var(--brand)', display: 'inline-flex', alignItems: 'center', gap: 4 }}
              >
                {u.empreendimento} <ArrowUpRight size={12} />
              </Link>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <SectionHead sub="Média das etapas cadastradas em cada obra">Andamento</SectionHead>
        {obras.length === 0 ? (
          <Empty>Ainda não há obra cadastrada nos empreendimentos deste cliente.</Empty>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {obras.map(o => <CartaoObra key={o.id} obra={o} />)}
          </div>
        )}
      </section>
    </div>
  )
}

function CartaoObra({ obra }: { obra: ObraDoCliente }) {
  const st = STATUS_OBRA[obra.status] ?? { rotulo: obra.status, kind: 'slate' as const }
  return (
    <Card style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <HardHat size={16} style={{ color: 'var(--ink-3)' }} />
        <Link to={`/app/obras/${obra.id}`} style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>
          {obra.nome}
        </Link>
        <Pill kind={st.kind}>{st.rotulo}</Pill>
        <span style={{ marginLeft: 'auto', fontSize: 11.5, color: 'var(--ink-3)' }}>
          Previsão: {data(obra.fimPrevisto)}
        </span>
      </div>

      {obra.percentual === null ? (
        <EmBreve>sem etapas cadastradas — avanço indisponível</EmBreve>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ flex: 1, height: 8, borderRadius: 999, background: 'var(--inset)', overflow: 'hidden' }}>
            <div style={{ width: `${obra.percentual}%`, height: '100%', background: 'var(--accent)', borderRadius: 999 }} />
          </div>
          <span className="num" style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>
            {obra.percentual}%
          </span>
          <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
            média de {obra.etapasTotal} {obra.etapasTotal === 1 ? 'etapa' : 'etapas'}
          </span>
        </div>
      )}

      {obra.etapas.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {obra.etapas.map(e => (
            <div key={e.id} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12 }}>
              <span className="truncate" style={{ minWidth: 0, flex: 1, color: 'var(--ink-2)' }}>{e.nome}</span>
              <div style={{ width: 120, height: 5, borderRadius: 999, background: 'var(--inset)', overflow: 'hidden', flex: 'none' }}>
                <div style={{ width: `${e.percentual}%`, height: '100%', background: 'var(--st-const)' }} />
              </div>
              <span className="num" style={{ width: 46, textAlign: 'right', color: 'var(--ink-3)' }}>{e.percentual}%</span>
              <span className="num" style={{ width: 78, textAlign: 'right', color: 'var(--ink-3)' }}>{data(e.fimPrevisto)}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
