import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, ShoppingCart, PackageCheck, Star } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Card, Num } from '@/components/malha'
import { parseApiErrors, FormErrorBanner, type FieldErrors } from '@/utils/formErrors'
import { pedidosHooks, itensPedidoHooks, recebimentosHooks, avaliacoesHooks } from '../hooks'
import type { ItemPedido, Recebimento, AvaliacaoFornecedor, TipoRecebimento } from '../types'
import { pedidoEstado, origemPedidoLabel, brl, qty, dataBR } from '../lib'
import { PageHeader, Btn, Field, TextInput, TextArea, NativeSelect, Modal, EstadoPill, TagPill, Spinner, EmptyState } from '../components/ui'
import { SeamChips, pedidoSeams, recebimentoSeams } from '../components/seams'

export default function PedidoDetailPage() {
  const { id } = useParams()
  const pedidoId = Number(id)
  const { hasPermission } = useAuth()
  const podeReceber = hasPermission('scm.recebimento.edit')
  const podeAvaliar = hasPermission('scm.avaliacao.edit')

  const { data: pedido, isLoading } = pedidosHooks.useDetail(pedidoId)
  const { data: itens } = itensPedidoHooks.useAll({ pedido: pedidoId })
  const { data: recebimentos } = recebimentosHooks.useAll({ pedido: pedidoId })
  const { data: avaliacoes } = avaliacoesHooks.useAll({ pedido: pedidoId })
  const [receber, setReceber] = useState(false)
  const [avaliar, setAvaliar] = useState(false)

  if (isLoading || !pedido) return <div style={{ display: 'grid', placeItems: 'center', padding: 80 }}><Spinner /></div>

  const linhas = (itens ?? []) as ItemPedido[]
  const recs = (recebimentos ?? []) as Recebimento[]
  const avals = (avaliacoes ?? []) as AvaliacaoFornecedor[]
  const finalizado = pedido.status === 'cancelado'

  return (
    <div style={{ padding: '28px 26px', maxWidth: 980, margin: '0 auto' }}>
      <PageHeader
        icon={<ShoppingCart size={22} />}
        title={`Pedido #${pedido.pedido_id}`}
        backTo={<Link to="/app/scm/pedidos" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--ink-3)', marginBottom: 2 }}><ArrowLeft size={13} /> Pedidos</Link>}
        subtitle={
          <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <EstadoPill estado={pedidoEstado[pedido.status]} />
            <TagPill kind={pedido.origem === 'compra_direta' ? 'info' : pedido.origem === 'cotacao' ? 'amber' : 'slate'}>{origemPedidoLabel[pedido.origem]}</TagPill>
            <SeamChips seams={pedidoSeams(pedido)} />
          </span>
        }
        actions={
          <>
            {podeAvaliar && <Btn variant="ghost" onClick={() => setAvaliar(true)}><Star size={14} /> Avaliar fornecedor</Btn>}
            {podeReceber && !finalizado && <Btn variant="primary" onClick={() => setReceber(true)}><PackageCheck size={14} /> Registrar recebimento</Btn>}
          </>
        }
      />

      <div style={{ display: 'grid', gap: 18 }}>
        <Card>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 16 }}>
            <Info label="Fornecedor" value={pedido.fornecedor_nome ?? `#${pedido.fornecedor}`} />
            <Info label="Centro de custo" value={pedido.centro_custo_nome ?? '—'} />
            <Info label="Valor total" value={brl(pedido.valor_total)} mono />
            <Info label="Data do pedido" value={dataBR(pedido.data_pedido)} mono />
            <Info label="Entrega prevista" value={dataBR(pedido.data_entrega_prevista)} mono />
            {pedido.demanda && <Info label="Origem" value={`Demanda #${pedido.demanda}`} />}
            {pedido.oferta_origem && <Info label="Origem" value={`Oferta #${pedido.oferta_origem}`} />}
          </div>
          {pedido.observacao && <p style={{ marginTop: 14, fontSize: 13, color: 'var(--ink-2)' }}>{pedido.observacao}</p>}
        </Card>

        <section>
          <SectionTitle>Itens</SectionTitle>
          {linhas.length === 0 ? <EmptyState label="Sem itens neste pedido." /> : (
            <Card pad={false} style={{ overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: 'var(--surface-2)', borderBottom: '1px solid var(--line)' }}>
                    {['Item', 'Qtd.', 'Preço unit.', 'Subtotal'].map((h, i) => (
                      <th key={h} style={{ textAlign: i === 0 ? 'left' : 'right', padding: '10px 16px', fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {linhas.map((it, i) => (
                    <tr key={it.item_pedido_id} style={{ borderBottom: i < linhas.length - 1 ? '1px solid var(--line-2)' : 'none' }}>
                      <td style={{ padding: '11px 16px', fontSize: 13, color: 'var(--ink)' }}>
                        <div style={{ fontWeight: 500 }}>{it.produto_descricao ?? it.descricao ?? '—'}</div>
                        {it.produto_codigo && <span className="mono" style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{it.produto_codigo}</span>}
                      </td>
                      <td style={{ padding: '11px 16px', textAlign: 'right' }}><Num right>{qty(it.quantidade)}</Num></td>
                      <td style={{ padding: '11px 16px', textAlign: 'right' }}><Num right>{brl(it.preco_unitario)}</Num></td>
                      <td style={{ padding: '11px 16px', textAlign: 'right' }}><Num right style={{ color: 'var(--ink)', fontWeight: 600 }}>{brl((Number(it.preco_unitario) * Number(it.quantidade)).toFixed(2))}</Num></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </section>

        <section>
          <SectionTitle>Recebimentos</SectionTitle>
          {recs.length === 0 ? <EmptyState label="Nenhum recebimento registrado." /> : (
            <Card pad={false} style={{ overflow: 'hidden' }}>
              {recs.map((r, i) => (
                <div key={r.recebimento_id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', borderBottom: i < recs.length - 1 ? '1px solid var(--line-2)' : 'none' }}>
                  <TagPill kind={r.tipo === 'total' ? 'good' : 'amber'}>{r.tipo === 'total' ? 'Total' : 'Parcial'}</TagPill>
                  <span className="mono" style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>{dataBR(r.data)}</span>
                  <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}><SeamChips seams={recebimentoSeams(r)} /></span>
                </div>
              ))}
            </Card>
          )}
        </section>

        {avals.length > 0 && (
          <section>
            <SectionTitle>Avaliação do fornecedor</SectionTitle>
            {avals.map(a => (
              <Card key={a.avaliacao_id} style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center' }}>
                <NotaView label="Qualidade" value={a.nota_qualidade} />
                <NotaView label="Pontualidade" value={a.nota_pontualidade} />
                <NotaView label="Atendimento" value={a.nota_atendimento} />
                {a.comentario && <p style={{ flex: 1, minWidth: 200, fontSize: 13, color: 'var(--ink-2)' }}>{a.comentario}</p>}
              </Card>
            ))}
          </section>
        )}
      </div>

      {receber && <RecebimentoModal pedidoId={pedidoId} onClose={() => setReceber(false)} />}
      {avaliar && <AvaliacaoModal pedidoId={pedidoId} fornecedor={pedido.fornecedor} onClose={() => setAvaliar(false)} />}
    </div>
  )
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700, marginBottom: 3 }}>{label}</div>
      <div className={mono ? 'mono' : undefined} style={{ fontSize: 13.5, color: 'var(--ink)' }}>{value}</div>
    </div>
  )
}
function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 style={{ fontFamily: 'var(--display)', fontSize: 15, fontWeight: 700, color: 'var(--ink)', marginBottom: 10 }}>{children}</h2>
}
function NotaView({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div style={{ fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700, marginBottom: 4 }}>{label}</div>
      <div style={{ display: 'flex', gap: 2 }}>
        {[1, 2, 3, 4, 5].map(n => <Star key={n} size={15} style={{ color: n <= value ? 'var(--accent)' : 'var(--line)', fill: n <= value ? 'var(--accent)' : 'none' }} />)}
      </div>
    </div>
  )
}

function RecebimentoModal({ pedidoId, onClose }: { pedidoId: number; onClose: () => void }) {
  const create = recebimentosHooks.useCreate()
  const [errors, setErrors] = useState<FieldErrors>({})
  const [tipo, setTipo] = useState<TipoRecebimento>('total')
  const [data, setData] = useState(new Date().toISOString().slice(0, 10))
  const [local, setLocal] = useState('')
  const [nf, setNf] = useState('')
  const [obs, setObs] = useState('')

  const salvar = async () => {
    setErrors({})
    try {
      await create.mutateAsync({ pedido: pedidoId, tipo, data, local_entrega: local, nota_fiscal_ref: nf, observacao: obs })
      onClose()
    } catch (err) { setErrors(parseApiErrors(err)) }
  }

  return (
    <Modal
      title="Registrar recebimento"
      onClose={onClose}
      footer={<><Btn variant="ghost" onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={create.isPending}>{create.isPending ? 'Salvando…' : 'Registrar'}</Btn></>}
    >
      <FormErrorBanner errors={errors} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Tipo" required>
          <NativeSelect value={tipo} onChange={v => setTipo(v as TipoRecebimento)}>
            <option value="total">Total</option>
            <option value="parcial">Parcial</option>
          </NativeSelect>
        </Field>
        <Field label="Data" required error={errors.data}>
          <TextInput type="date" value={data} onChange={e => setData(e.target.value)} />
        </Field>
      </div>
      <Field label="NF-e (chave/número)" hint="Conciliação com a nota fiscal — seam do ERP/NF-e." error={errors.nota_fiscal_ref}>
        <TextInput value={nf} onChange={e => setNf(e.target.value)} placeholder="Opcional" />
      </Field>
      <Field label="Local de entrega (estoque)" hint="Entrada de estoque — seam do módulo SIL (futuro)." error={errors.local_entrega}>
        <TextInput value={local} onChange={e => setLocal(e.target.value)} placeholder="Opcional" />
      </Field>
      <Field label="Observação" error={errors.observacao}>
        <TextArea value={obs} onChange={e => setObs(e.target.value)} placeholder="Opcional" />
      </Field>
    </Modal>
  )
}

function AvaliacaoModal({ pedidoId, fornecedor, onClose }: { pedidoId: number; fornecedor: number; onClose: () => void }) {
  const create = avaliacoesHooks.useCreate()
  const [errors, setErrors] = useState<FieldErrors>({})
  const [qualidade, setQualidade] = useState(5)
  const [pontualidade, setPontualidade] = useState(5)
  const [atendimento, setAtendimento] = useState(5)
  const [comentario, setComentario] = useState('')

  const salvar = async () => {
    setErrors({})
    try {
      await create.mutateAsync({ fornecedor, pedido: pedidoId, nota_qualidade: qualidade, nota_pontualidade: pontualidade, nota_atendimento: atendimento, comentario })
      onClose()
    } catch (err) { setErrors(parseApiErrors(err)) }
  }

  return (
    <Modal
      title="Avaliar fornecedor"
      onClose={onClose}
      footer={<><Btn variant="ghost" onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={create.isPending}>{create.isPending ? 'Salvando…' : 'Salvar avaliação'}</Btn></>}
    >
      <FormErrorBanner errors={errors} />
      <StarsPicker label="Qualidade" value={qualidade} onChange={setQualidade} />
      <StarsPicker label="Pontualidade" value={pontualidade} onChange={setPontualidade} />
      <StarsPicker label="Atendimento" value={atendimento} onChange={setAtendimento} />
      <Field label="Comentário" error={errors.comentario}>
        <TextArea value={comentario} onChange={e => setComentario(e.target.value)} placeholder="Opcional" />
      </Field>
    </Modal>
  )
}

function StarsPicker({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 10.5, letterSpacing: '0.09em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700, marginBottom: 6 }}>{label}</div>
      <div style={{ display: 'flex', gap: 4 }}>
        {[1, 2, 3, 4, 5].map(n => (
          <button key={n} onClick={() => onChange(n)} aria-label={`${n} estrela(s)`} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2 }}>
            <Star size={22} style={{ color: n <= value ? 'var(--accent)' : 'var(--line)', fill: n <= value ? 'var(--accent)' : 'none' }} />
          </button>
        ))}
      </div>
    </div>
  )
}
