import { useMemo, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, FileSpreadsheet, Plus, Trophy, ShoppingCart } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Card, Num, Pill } from '@/components/malha'
import { parseApiErrors, FormErrorBanner, type FieldErrors } from '@/utils/formErrors'
import {
  cotacoesHooks, demandasHooks, itensDemandaHooks, propostasHooks, itensPropostaHooks,
  useAdjudicar, useGerarDeCotacao,
} from '../hooks'
import { scmKeys } from '../api/queryKeys'
import { propostas as propostasApi, itensProposta as itensPropostaApi, searchFornecedores, resolveFornecedor } from '../api/scmApi'
import type { ItemDemanda, Proposta, ItemProposta } from '../types'
import { cotacaoEstado, propostaEstado, brl, qty } from '../lib'
import { PageHeader, Btn, Field, NumInput, Modal, EstadoPill, Spinner, EmptyState } from '../components/ui'
import { AsyncEntitySelect } from '../components/AsyncEntitySelect'
import { propostaSeams, SeamChips } from '../components/seams'

export default function CotacaoDetailPage() {
  const { id } = useParams()
  const cotacaoId = Number(id)
  const navigate = useNavigate()
  const { hasPermission } = useAuth()
  const podeAdjudicar = hasPermission('scm.cotacao.adjudicar')
  const podeRegistrar = hasPermission('scm.cotacao.edit')
  const podeGerar = hasPermission('scm.pedido.criar')

  const { data: cotacao, isLoading } = cotacoesHooks.useDetail(cotacaoId)
  const { data: demanda } = demandasHooks.useDetail(cotacao?.demanda)
  const { data: itens } = itensDemandaHooks.useAll({ demanda: cotacao?.demanda ?? 0 }, cotacao?.demanda != null)
  const { data: propostas } = propostasHooks.useAll({ cotacao: cotacaoId })
  const { data: itensProp } = itensPropostaHooks.useAll({ proposta__cotacao: cotacaoId })
  const adjudicar = useAdjudicar()
  const gerar = useGerarDeCotacao()
  const [registrar, setRegistrar] = useState(false)

  const lista = useMemo(() => (itens ?? []) as ItemDemanda[], [itens])
  const props = useMemo(() => (propostas ?? []) as Proposta[], [propostas])
  const cells = useMemo(() => {
    const m = new Map<string, string>()
    for (const ip of (itensProp ?? []) as ItemProposta[]) m.set(`${ip.proposta}:${ip.item_demanda}`, ip.preco_unitario)
    return m
  }, [itensProp])

  const recomendadaId = useMemo(() => {
    const validas = props.filter(p => p.status !== 'recusada' && p.valor_total != null)
    if (validas.length === 0) return null
    return validas.reduce((a, b) => (Number(a.valor_total) <= Number(b.valor_total) ? a : b)).proposta_id
  }, [props])

  if (isLoading || !cotacao) return <div style={{ display: 'grid', placeItems: 'center', padding: 80 }}><Spinner /></div>

  const adjudicada = cotacao.status === 'adjudicada'
  const vencedora = props.find(p => p.status === 'vencedora')

  return (
    <div style={{ padding: '28px 26px', maxWidth: 1180, margin: '0 auto' }}>
      <PageHeader
        icon={<FileSpreadsheet size={22} />}
        title={`Cotação #${cotacao.cotacao_id}`}
        backTo={
          <Link to={cotacao.demanda ? `/app/scm/demandas/${cotacao.demanda}` : '/app/scm/demandas'} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--ink-3)', marginBottom: 2 }}>
            <ArrowLeft size={13} /> Demanda #{cotacao.demanda}
          </Link>
        }
        subtitle={<EstadoPill estado={cotacaoEstado[cotacao.status]} />}
        actions={
          <>
            {podeRegistrar && !adjudicada && <Btn variant="ghost" onClick={() => setRegistrar(true)}><Plus size={14} /> Registrar proposta</Btn>}
            {podeGerar && adjudicada && (
              <Btn variant="primary" onClick={async () => { await gerar.mutateAsync(cotacaoId); navigate('/app/scm/pedidos') }} disabled={gerar.isPending}>
                <ShoppingCart size={14} /> Gerar pedido de compra
              </Btn>
            )}
          </>
        }
      />

      {adjudicada && vencedora && (
        <Card style={{ marginBottom: 18, display: 'flex', alignItems: 'center', gap: 12, borderColor: 'color-mix(in srgb, var(--good) 40%, var(--line))', background: 'var(--good-soft)' }}>
          <Trophy size={20} style={{ color: 'var(--good-ink)' }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 650, color: 'var(--ink)' }}>Adjudicada a {vencedora.fornecedor_label ?? 'fornecedor'}</div>
            <div style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>Valor <span className="mono">{brl(vencedora.valor_total)}</span>{vencedora.prazo_entrega_dias != null && <> · prazo {vencedora.prazo_entrega_dias} dias</>}</div>
          </div>
        </Card>
      )}

      {props.length === 0 ? (
        <EmptyState label="Nenhuma proposta registrada. Registre as respostas dos fornecedores para comparar." />
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <Card pad={false} style={{ overflow: 'hidden', minWidth: 520 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--line)' }}>
                  <th style={{ textAlign: 'left', padding: '12px 16px', fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700, background: 'var(--surface-2)', position: 'sticky', left: 0 }}>Item</th>
                  {props.map(p => {
                    const rec = p.proposta_id === recomendadaId && !adjudicada
                    const win = p.status === 'vencedora'
                    return (
                      <th key={p.proposta_id} style={{ padding: '10px 14px', minWidth: 168, textAlign: 'right', verticalAlign: 'top', background: win ? 'var(--good-soft)' : rec ? 'var(--accent-soft)' : 'var(--surface-2)', borderLeft: '1px solid var(--line-2)' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, alignItems: 'flex-end' }}>
                          <span style={{ fontSize: 12.5, fontWeight: 650, color: 'var(--ink)' }}>{p.fornecedor_label}</span>
                          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                            <EstadoPill estado={propostaEstado[p.status]} />
                            {rec && <Pill kind="amber">Recomendada</Pill>}
                            <SeamChips seams={propostaSeams(p)} />
                          </div>
                          {podeAdjudicar && !adjudicada && (
                            <Btn size="sm" variant="primary" onClick={() => adjudicar.mutate({ cotacao: cotacaoId, proposta: p.proposta_id })} disabled={adjudicar.isPending}>
                              <Trophy size={12} /> Adjudicar
                            </Btn>
                          )}
                        </div>
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {lista.map(it => (
                  <tr key={it.item_demanda_id} style={{ borderBottom: '1px solid var(--line-2)' }}>
                    <td style={{ padding: '10px 16px', fontSize: 13, color: 'var(--ink)', background: 'var(--surface)', position: 'sticky', left: 0 }}>
                      <div style={{ fontWeight: 500 }}>{it.produto_descricao ?? it.descricao_servico ?? `Item #${it.item_demanda_id}`}</div>
                      <span className="mono" style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{qty(it.quantidade)} {it.unidade || 'un'}</span>
                    </td>
                    {props.map(p => {
                      const preco = cells.get(`${p.proposta_id}:${it.item_demanda_id}`)
                      return <td key={p.proposta_id} style={{ padding: '10px 14px', textAlign: 'right', borderLeft: '1px solid var(--line-2)' }}><Num right style={{ color: preco ? 'var(--ink)' : 'var(--ink-3)' }}>{preco ? brl(preco) : '—'}</Num></td>
                    })}
                  </tr>
                ))}
                <tr style={{ borderTop: '2px solid var(--line)' }}>
                  <td style={{ padding: '12px 16px', fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--ink-3)', background: 'var(--surface-2)', position: 'sticky', left: 0 }}>Total</td>
                  {props.map(p => {
                    const rec = p.proposta_id === recomendadaId && !adjudicada
                    const win = p.status === 'vencedora'
                    return <td key={p.proposta_id} style={{ padding: '12px 14px', textAlign: 'right', borderLeft: '1px solid var(--line-2)', background: win ? 'var(--good-soft)' : rec ? 'var(--accent-soft)' : 'transparent' }}><Num right style={{ fontWeight: 750, fontSize: 15, color: 'var(--ink)' }}>{brl(p.valor_total)}</Num></td>
                  })}
                </tr>
                <tr>
                  <td style={{ padding: '9px 16px', fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 700, color: 'var(--ink-3)', background: 'var(--surface-2)', position: 'sticky', left: 0 }}>Prazo</td>
                  {props.map(p => (
                    <td key={p.proposta_id} style={{ padding: '9px 14px', textAlign: 'right', borderLeft: '1px solid var(--line-2)' }}>
                      <Num right style={{ color: 'var(--ink-2)' }}>{p.prazo_entrega_dias != null ? `${p.prazo_entrega_dias} d` : '—'}</Num>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </Card>
        </div>
      )}

      {registrar && demanda && (
        <RegistrarPropostaModal cotacaoId={cotacaoId} itens={lista} onClose={() => setRegistrar(false)} />
      )}
    </div>
  )
}

function RegistrarPropostaModal({ cotacaoId, itens, onClose }: { cotacaoId: number; itens: ItemDemanda[]; onClose: () => void }) {
  const qc = useQueryClient()
  const [errors, setErrors] = useState<FieldErrors>({})
  const [fornecedor, setFornecedor] = useState<number | null>(null)
  const [prazo, setPrazo] = useState('')
  const [precos, setPrecos] = useState<Record<number, string>>({})
  const [saving, setSaving] = useState(false)

  const total = itens.reduce((acc, it) => acc + (Number(precos[it.item_demanda_id] || 0) * Number(it.quantidade || 0)), 0)

  const salvar = async () => {
    setErrors({})
    if (fornecedor == null) return setErrors({ fornecedor: 'Selecione o fornecedor.' })
    setSaving(true)
    try {
      const proposta = await propostasApi.create({
        cotacao: cotacaoId, fornecedor,
        valor_total: total.toFixed(2),
        prazo_entrega_dias: prazo ? Number(prazo) : null,
      })
      for (const it of itens) {
        const preco = precos[it.item_demanda_id]
        if (preco) await itensPropostaApi.create({ proposta: proposta.proposta_id, item_demanda: it.item_demanda_id, preco_unitario: preco, quantidade: it.quantidade })
      }
      await qc.invalidateQueries({ queryKey: scmKeys.all })
      onClose()
    } catch (err) { setErrors(parseApiErrors(err)); setSaving(false) }
  }

  return (
    <Modal
      title="Registrar proposta"
      width={560}
      onClose={onClose}
      footer={<>
        <Btn variant="ghost" onClick={onClose}>Cancelar</Btn>
        <Btn variant="primary" onClick={salvar} disabled={saving}>{saving ? 'Salvando…' : 'Salvar proposta'}</Btn>
      </>}
    >
      <FormErrorBanner errors={errors} />
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 12 }}>
        <Field label="Fornecedor" required error={errors.fornecedor}>
          <AsyncEntitySelect value={fornecedor} onChange={setFornecedor} search={searchFornecedores} resolve={resolveFornecedor} placeholder="Buscar fornecedor…" />
        </Field>
        <Field label="Prazo (dias)">
          <NumInput value={prazo} onChange={setPrazo} step="1" min={0} placeholder="—" />
        </Field>
      </div>

      {itens.length > 0 && (
        <div style={{ marginTop: 4 }}>
          <div style={{ fontSize: 10.5, letterSpacing: '0.09em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700, marginBottom: 8 }}>Preço por item</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {itens.map(it => (
              <div key={it.item_demanda_id} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, color: 'var(--ink)' }}>{it.produto_descricao ?? it.descricao_servico ?? `Item #${it.item_demanda_id}`}</div>
                  <span className="mono" style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{qty(it.quantidade)} {it.unidade || 'un'}</span>
                </div>
                <div style={{ width: 130 }}>
                  <NumInput value={precos[it.item_demanda_id] ?? ''} onChange={v => setPrecos(p => ({ ...p, [it.item_demanda_id]: v }))} step="0.01" min={0} placeholder="Preço unit." />
                </div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--line)', alignItems: 'baseline' }}>
            <span style={{ fontSize: 12, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>Total</span>
            <Num style={{ fontSize: 18, fontWeight: 750, color: 'var(--ink)' }}>{brl(total.toFixed(2))}</Num>
          </div>
        </div>
      )}
    </Modal>
  )
}
