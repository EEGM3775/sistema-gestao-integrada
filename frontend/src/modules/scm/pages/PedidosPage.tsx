import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ShoppingCart, Zap } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Num } from '@/components/malha'
import { parseApiErrors, FormErrorBanner, type FieldErrors } from '@/utils/formErrors'
import { pedidosHooks, useComprarDireto } from '../hooks'
import { ofertas as ofertasApi, searchOfertasDiretas, searchCentrosCusto, resolveCentroCusto } from '../api/scmApi'
import type { PedidoCompra, OrigemPedido, StatusPedido } from '../types'
import { pedidoEstado, origemPedidoLabel, brl, qty, dataBR } from '../lib'
import {
  PageHeader, Toolbar, FilterSelect, DataTable, Pager, Btn,
  Modal, Field, NumInput, EstadoPill, TagPill, type Column,
} from '../components/ui'
import { AsyncEntitySelect } from '../components/AsyncEntitySelect'
import { SeamChips, pedidoSeams } from '../components/seams'

const PAGE_SIZE = 25
const STATUS: StatusPedido[] = ['rascunho', 'aprovado', 'enviado', 'recebido_parcial', 'recebido_total', 'cancelado']
const ORIGENS: OrigemPedido[] = ['compra_direta', 'cotacao', 'manual']

export default function PedidosPage() {
  const navigate = useNavigate()
  const { hasPermission } = useAuth()
  const podeComprar = hasPermission('scm.pedido.criar')
  const [status, setStatus] = useState('')
  const [origem, setOrigem] = useState('')
  const [page, setPage] = useState(1)
  const [comprando, setComprando] = useState(false)

  const { data, isLoading } = pedidosHooks.useList({ status, origem, page })
  const total = data?.count ?? 0

  const columns: Column<PedidoCompra>[] = [
    { key: 'id', header: 'Pedido', render: p => <span className="mono" style={{ color: 'var(--ink)', fontWeight: 600 }}>#{p.pedido_id}</span> },
    { key: 'origem', header: 'Origem', render: p => <TagPill kind={p.origem === 'compra_direta' ? 'info' : p.origem === 'cotacao' ? 'amber' : 'slate'}>{origemPedidoLabel[p.origem]}</TagPill> },
    { key: 'fornecedor', header: 'Fornecedor', render: p => p.fornecedor_nome ?? `#${p.fornecedor}` },
    { key: 'cc', header: 'Centro de custo', render: p => p.centro_custo_nome ?? '—' },
    { key: 'valor', header: 'Valor', align: 'right', render: p => <Num right style={{ color: 'var(--ink)' }}>{brl(p.valor_total)}</Num> },
    { key: 'status', header: 'Estado', render: p => <EstadoPill estado={pedidoEstado[p.status]} /> },
    { key: 'seams', header: 'Vínculos', render: p => <SeamChips seams={pedidoSeams(p)} /> },
    { key: 'data', header: 'Data', render: p => <span className="mono" style={{ fontSize: 12, color: 'var(--ink-3)' }}>{dataBR(p.data_pedido)}</span> },
  ]

  return (
    <div style={{ padding: '28px 26px', maxWidth: 1180, margin: '0 auto' }}>
      <PageHeader
        icon={<ShoppingCart size={22} />}
        title="Pedidos de compra"
        subtitle={isLoading ? 'Carregando…' : `${total} pedido${total !== 1 ? 's' : ''} — compra direta e cotação convergem aqui`}
        actions={podeComprar && <Btn variant="primary" onClick={() => setComprando(true)}><Zap size={15} /> Comprar direto</Btn>}
      />
      <Toolbar>
        <FilterSelect value={origem} onChange={v => { setOrigem(v); setPage(1) }} allLabel="Todas as origens"
          options={ORIGENS.map(o => ({ value: o, label: origemPedidoLabel[o] }))} />
        <FilterSelect value={status} onChange={v => { setStatus(v); setPage(1) }} allLabel="Todos os estados"
          options={STATUS.map(s => ({ value: s, label: pedidoEstado[s].label }))} />
      </Toolbar>
      <DataTable columns={columns} rows={data?.results ?? []} rowKey={p => p.pedido_id} loading={isLoading}
        onRowClick={p => navigate(`/app/scm/pedidos/${p.pedido_id}`)}
        emptyLabel={status || origem ? 'Nenhum pedido para os filtros.' : 'Nenhum pedido ainda. Compre direto ou gere de uma cotação adjudicada.'} />
      <Pager page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />

      {comprando && <ComprarDiretoModal onClose={() => setComprando(false)} onCreated={id => navigate(`/app/scm/pedidos/${id}`)} />}
    </div>
  )
}

function ComprarDiretoModal({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const comprar = useComprarDireto()
  const [errors, setErrors] = useState<FieldErrors>({})
  const [oferta, setOferta] = useState<number | null>(null)
  const [quantidade, setQuantidade] = useState('')
  const [centroCusto, setCentroCusto] = useState<number | null>(null)

  const ofertaDet = useQuery({ queryKey: ['scm', 'oferta', oferta], queryFn: () => ofertasApi.get(oferta as number), enabled: oferta != null })
  const preco = ofertaDet.data ? Number(ofertaDet.data.preco_direto) : 0
  const totalPrevisto = preco * Number(quantidade || 0)

  const salvar = async () => {
    setErrors({})
    if (oferta == null) return setErrors({ oferta: 'Selecione uma oferta.' })
    if (!quantidade || Number(quantidade) <= 0) return setErrors({ quantidade: 'Informe uma quantidade positiva.' })
    try {
      const pedido = await comprar.mutateAsync({ oferta, quantidade, centro_custo: centroCusto })
      onCreated(pedido.pedido_id)
    } catch (err) {
      const parsed = parseApiErrors(err)
      // O backend responde `detail` (400) — mostra no banner geral.
      setErrors(parsed.detail ? { _form: parsed.detail } : parsed)
    }
  }

  return (
    <Modal
      title="Comprar direto"
      width={520}
      onClose={onClose}
      footer={<>
        <Btn variant="ghost" onClick={onClose}>Cancelar</Btn>
        <Btn variant="primary" onClick={salvar} disabled={comprar.isPending}>{comprar.isPending ? 'Comprando…' : 'Gerar pedido'}</Btn>
      </>}
    >
      <FormErrorBanner errors={errors} />
      <p style={{ fontSize: 12.5, color: 'var(--ink-3)', marginBottom: 14 }}>Compra a preço fixo de uma oferta publicada para compra direta — sem cotação. Gera um pedido já aprovado.</p>
      <Field label="Oferta" required error={errors.oferta}>
        <AsyncEntitySelect value={oferta} onChange={setOferta} search={searchOfertasDiretas} placeholder="Buscar oferta (compra direta)…" />
      </Field>
      {ofertaDet.data && (
        <div style={{ display: 'flex', gap: 18, marginBottom: 14, fontSize: 12.5, color: 'var(--ink-2)' }}>
          <span>Preço unit.: <span className="mono" style={{ color: 'var(--ink)' }}>{brl(ofertaDet.data.preco_direto)}</span></span>
          <span>Estoque: <span className="mono">{qty(ofertaDet.data.estoque_disponivel)}</span></span>
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: 12 }}>
        <Field label="Quantidade" required error={errors.quantidade}>
          <NumInput value={quantidade} onChange={setQuantidade} step="0.001" min={0} placeholder="0" />
        </Field>
        <Field label="Centro de custo">
          <AsyncEntitySelect value={centroCusto} onChange={setCentroCusto} search={searchCentrosCusto} resolve={resolveCentroCusto} placeholder="Opcional…" />
        </Field>
      </div>
      {quantidade && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, alignItems: 'baseline', paddingTop: 8, borderTop: '1px solid var(--line)' }}>
          <span style={{ fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }}>Total previsto</span>
          <Num style={{ fontSize: 18, fontWeight: 750, color: 'var(--ink)' }}>{brl(totalPrevisto.toFixed(2))}</Num>
        </div>
      )}
    </Modal>
  )
}
