import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, ClipboardList, Plus, Trash2, Send, FileSpreadsheet, ChevronRight } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Card, Num } from '@/components/malha'
import { demandasHooks, itensDemandaHooks, cotacoesHooks, usePublicarDemanda } from '../hooks'
import { searchProdutos, resolveProduto } from '../api/scmApi'
import type { ItemDemanda } from '../types'
import { demandaEstado, cotacaoEstado, tipoItemLabel, qty, dataHoraBR } from '../lib'
import { PageHeader, Btn, Field, TextInput, NumInput, EstadoPill, TagPill, Spinner, EmptyState } from '../components/ui'
import { AsyncEntitySelect } from '../components/AsyncEntitySelect'
import { SeamChips, demandaSeams } from '../components/seams'

export default function DemandaDetailPage() {
  const { id } = useParams()
  const demandaId = Number(id)
  const navigate = useNavigate()
  const { hasPermission } = useAuth()
  const podeEditar = hasPermission('scm.demanda.edit')
  const podePublicar = hasPermission('scm.demanda.publicar')
  const podeCotar = hasPermission('scm.cotacao.edit')

  const { data: demanda, isLoading } = demandasHooks.useDetail(demandaId)
  const { data: itens } = itensDemandaHooks.useAll({ demanda: demandaId })
  const { data: cotacoes } = cotacoesHooks.useAll({ demanda: demandaId })
  const publicar = usePublicarDemanda()
  const criarCotacao = cotacoesHooks.useCreate()

  if (isLoading || !demanda) return <div style={{ display: 'grid', placeItems: 'center', padding: 80 }}><Spinner /></div>

  const lista = (itens ?? []) as ItemDemanda[]
  const cots = cotacoes ?? []
  const podePublicarAgora = demanda.visibilidade === 'privada' && (demanda.status === 'rascunho' || demanda.status === 'aberta')

  const abrirCotacao = async () => {
    const nova = await criarCotacao.mutateAsync({ demanda: demandaId })
    navigate(`/app/scm/cotacoes/${nova.cotacao_id}`)
  }

  return (
    <div style={{ padding: '28px 26px', maxWidth: 980, margin: '0 auto' }}>
      <PageHeader
        icon={<ClipboardList size={22} />}
        title={`Demanda #${demanda.demanda_id}`}
        backTo={<Link to="/app/scm/demandas" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--ink-3)', marginBottom: 2 }}><ArrowLeft size={13} /> Demandas</Link>}
        subtitle={
          <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <EstadoPill estado={demandaEstado[demanda.status]} />
            <TagPill kind={demanda.tipo === 'servico' ? 'info' : 'slate'}>{tipoItemLabel[demanda.tipo]}</TagPill>
            <SeamChips seams={demandaSeams(demanda)} />
          </span>
        }
        actions={podePublicar && podePublicarAgora && (
          <Btn variant="ghost" onClick={() => publicar.mutate(demandaId)} disabled={publicar.isPending}>
            <Send size={14} /> Publicar na rede
          </Btn>
        )}
      />

      <div style={{ display: 'grid', gap: 18 }}>
        {/* Ficha */}
        <Card>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 16 }}>
            <Info label="Centro de custo" value={demanda.centro_custo_nome ?? '—'} />
            <Info label="Categoria" value={demanda.categoria || '—'} />
            <Info label="Região" value={demanda.regiao || '—'} />
            <Info label="Origem" value={demanda.origem === 'estoque' ? 'Falta no estoque' : 'Manual'} />
            <Info label="Solicitante" value={demanda.solicitante_nome ?? '—'} />
            <Info label="Criada" value={dataHoraBR(demanda.criado_em)} mono />
          </div>
          {demanda.observacao && <p style={{ marginTop: 14, fontSize: 13, color: 'var(--ink-2)' }}>{demanda.observacao}</p>}
        </Card>

        {/* Itens */}
        <section>
          <SectionTitle>Itens da demanda</SectionTitle>
          {lista.length === 0 ? (
            <EmptyState label="Nenhum item ainda — adicione o que precisa comprar." />
          ) : (
            <Card pad={false} style={{ overflow: 'hidden' }}>
              {lista.map((it, i) => (
                <div key={it.item_demanda_id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 16px', borderBottom: i < lista.length - 1 ? '1px solid var(--line-2)' : 'none' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: 'var(--ink)', fontWeight: 500 }}>{it.produto_descricao ?? it.descricao_servico ?? '—'}</div>
                    {it.produto_codigo && <span className="mono" style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{it.produto_codigo}</span>}
                  </div>
                  <Num style={{ color: 'var(--ink)' }}>{qty(it.quantidade)}</Num>
                  <span style={{ color: 'var(--ink-3)', fontSize: 12.5, minWidth: 34 }}>{it.unidade || 'un'}</span>
                  {podeEditar && <RemoveItem id={it.item_demanda_id} />}
                </div>
              ))}
            </Card>
          )}
          {podeEditar && <AddItem demandaId={demandaId} tipo={demanda.tipo} />}
        </section>

        {/* Cotações */}
        <section>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 10 }}>
            <SectionTitle noMargin>Cotações</SectionTitle>
            {podeCotar && (
              <Btn variant={cots.length === 0 ? 'primary' : 'subtle'} onClick={abrirCotacao} disabled={criarCotacao.isPending || lista.length === 0}>
                <FileSpreadsheet size={14} /> Abrir cotação
              </Btn>
            )}
          </div>
          {cots.length === 0 ? (
            <EmptyState label={lista.length === 0 ? 'Adicione itens para poder cotar.' : 'Nenhuma cotação aberta para esta demanda.'} />
          ) : (
            <Card pad={false} style={{ overflow: 'hidden' }}>
              {cots.map((c, i) => (
                <Link key={c.cotacao_id} to={`/app/scm/cotacoes/${c.cotacao_id}`}
                  style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', borderBottom: i < cots.length - 1 ? '1px solid var(--line-2)' : 'none' }}>
                  <span className="mono" style={{ color: 'var(--ink)', fontWeight: 600 }}>Cotação #{c.cotacao_id}</span>
                  <EstadoPill estado={cotacaoEstado[c.status]} />
                  <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>{c.propostas_count ?? 0} proposta(s)</span>
                  <span style={{ marginLeft: 'auto', color: 'var(--ink-3)' }}><ChevronRight size={16} /></span>
                </Link>
              ))}
            </Card>
          )}
        </section>
      </div>
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

function SectionTitle({ children, noMargin }: { children: React.ReactNode; noMargin?: boolean }) {
  return <h2 style={{ fontFamily: 'var(--display)', fontSize: 15, fontWeight: 700, color: 'var(--ink)', marginBottom: noMargin ? 0 : 10 }}>{children}</h2>
}

function RemoveItem({ id }: { id: number }) {
  const remove = itensDemandaHooks.useRemove()
  return (
    <button onClick={() => remove.mutate(id)} aria-label="Remover item" style={{ color: 'var(--danger)', background: 'none', border: 'none', cursor: 'pointer', display: 'grid', placeItems: 'center' }}>
      <Trash2 size={15} />
    </button>
  )
}

function AddItem({ demandaId, tipo }: { demandaId: number; tipo: 'material' | 'servico' }) {
  const create = itensDemandaHooks.useCreate()
  const [produto, setProduto] = useState<number | null>(null)
  const [descricao, setDescricao] = useState('')
  const [quantidade, setQuantidade] = useState('')
  const [unidade, setUnidade] = useState('')

  const add = async () => {
    if (!quantidade) return
    if (tipo === 'material' && produto == null && !descricao) return
    await create.mutateAsync({
      demanda: demandaId,
      produto: tipo === 'material' ? produto : null,
      descricao_servico: descricao,
      quantidade,
      unidade,
    })
    setProduto(null); setDescricao(''); setQuantidade(''); setUnidade('')
  }

  return (
    <Card style={{ marginTop: 12, background: 'var(--surface-2)' }}>
      <div style={{ display: 'grid', gridTemplateColumns: tipo === 'material' ? '2fr 1fr 0.8fr auto' : '2fr 1fr 0.8fr auto', gap: 10, alignItems: 'end' }}>
        {tipo === 'material' ? (
          <Field label="Produto">
            <AsyncEntitySelect value={produto} onChange={setProduto} search={searchProdutos} resolve={resolveProduto} placeholder="Buscar produto…" />
          </Field>
        ) : (
          <Field label="Serviço / item">
            <TextInput value={descricao} onChange={e => setDescricao(e.target.value)} placeholder="Descrição do serviço" />
          </Field>
        )}
        <Field label="Quantidade"><NumInput value={quantidade} onChange={setQuantidade} step="0.001" min={0} placeholder="0" /></Field>
        <Field label="Unidade"><TextInput value={unidade} onChange={e => setUnidade(e.target.value)} placeholder="un" /></Field>
        <Btn variant="subtle" onClick={add} disabled={create.isPending} style={{ marginBottom: 14 }}><Plus size={14} /> Item</Btn>
      </div>
    </Card>
  )
}
