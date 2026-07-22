import { useState } from 'react'
import { Tags, Plus, Pencil, Trash2, Layers } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { parseApiErrors, FormErrorBanner, type FieldErrors } from '@/utils/formErrors'
import { ofertasHooks, faixasHooks } from '../hooks'
import { searchProdutos, resolveProduto, searchFornecedores, resolveFornecedor } from '../api/scmApi'
import type { OfertaFornecedor, OfertaPayload, Visibilidade, EntityOption, FaixaPrecoOferta } from '../types'
import { brl, qty, visibilidadeEstado } from '../lib'
import {
  PageHeader, Toolbar, SearchInput, FilterSelect, DataTable, Pager, Btn,
  Drawer, Field, TextInput, TextArea, NumInput, NativeSelect, Checkbox, TagPill, EstadoPill, type Column,
} from '../components/ui'
import { AsyncEntitySelect } from '../components/AsyncEntitySelect'
import { SeamChips, ofertaSeams } from '../components/seams'
import { Num } from '@/components/malha'

const PAGE_SIZE = 25

export default function OfertasPage() {
  const { hasPermission } = useAuth()
  const podeEditar = hasPermission('scm.oferta.edit')
  const [search, setSearch] = useState('')
  const [via, setVia] = useState('')
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<OfertaFornecedor | null>(null)
  const [creating, setCreating] = useState(false)

  const { data, isLoading } = ofertasHooks.useList({
    search, page,
    compra_direta: via === 'direta' ? true : via === 'cotacao' ? false : '',
  })
  const total = data?.count ?? 0

  const columns: Column<OfertaFornecedor>[] = [
    { key: 'produto', header: 'Produto', render: o => (
      <div>
        <div style={{ color: 'var(--ink)', fontWeight: 500 }}>{o.produto_descricao ?? `#${o.produto}`}</div>
        <span className="mono" style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{o.produto_codigo}</span>
      </div>
    ) },
    { key: 'fornecedor', header: 'Fornecedor', render: o => o.fornecedor_nome ?? `#${o.fornecedor}` },
    { key: 'preco', header: 'Preço direto', align: 'right', render: o => <Num right style={{ color: 'var(--ink)' }}>{brl(o.preco_direto)}</Num> },
    { key: 'estoque', header: 'Estoque', align: 'right', render: o => <Num right>{qty(o.estoque_disponivel)}</Num> },
    { key: 'via', header: 'Vias', render: o => (
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        {o.compra_direta ? <TagPill kind="info">Compra direta</TagPill> : <TagPill>Só cotação</TagPill>}
        <EstadoPill estado={visibilidadeEstado[o.visibilidade]} />
        <SeamChips seams={ofertaSeams(o)} />
      </div>
    ) },
    { key: 'ativo', header: 'Situação', render: o => <TagPill kind={o.ativo ? 'good' : 'danger'}>{o.ativo ? 'Ativa' : 'Inativa'}</TagPill> },
    ...(podeEditar ? [{ key: 'acoes', header: '', align: 'right' as const, render: (o: OfertaFornecedor) => (
      <Btn size="sm" variant="subtle" onClick={() => setEditing(o)}><Pencil size={13} /> Editar</Btn>
    ) }] : []),
  ]

  return (
    <div style={{ padding: '28px 26px', maxWidth: 1180, margin: '0 auto' }}>
      <PageHeader
        icon={<Tags size={22} />}
        title="Ofertas de fornecedores"
        subtitle={isLoading ? 'Carregando…' : `${total} oferta${total !== 1 ? 's' : ''} — preço e estoque das duas vias`}
        actions={podeEditar && <Btn variant="primary" onClick={() => setCreating(true)}><Plus size={15} /> Nova oferta</Btn>}
      />
      <Toolbar>
        <SearchInput value={search} onChange={v => { setSearch(v); setPage(1) }} placeholder="Buscar por produto, código ou código no fornecedor…" />
        <FilterSelect value={via} onChange={v => { setVia(v); setPage(1) }} allLabel="Todas as vias"
          options={[{ value: 'direta', label: 'Compra direta' }, { value: 'cotacao', label: 'Só cotação' }]} />
      </Toolbar>
      <DataTable columns={columns} rows={data?.results ?? []} rowKey={o => o.oferta_id} loading={isLoading}
        emptyLabel={search || via ? 'Nenhuma oferta para os filtros.' : 'Nenhuma oferta cadastrada ainda.'} />
      <Pager page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />

      {(creating || editing) && (
        <OfertaDrawer oferta={editing} onClose={() => { setCreating(false); setEditing(null) }} />
      )}
    </div>
  )
}

function OfertaDrawer({ oferta, onClose }: { oferta: OfertaFornecedor | null; onClose: () => void }) {
  const create = ofertasHooks.useCreate()
  const update = ofertasHooks.useUpdate()
  const remove = ofertasHooks.useRemove()
  const [errors, setErrors] = useState<FieldErrors>({})

  const [produto, setProduto] = useState<number | null>(oferta?.produto ?? null)
  const [fornecedor, setFornecedor] = useState<number | null>(oferta?.fornecedor ?? null)
  const [codigoForn, setCodigoForn] = useState(oferta?.codigo_no_fornecedor ?? '')
  const [preco, setPreco] = useState(oferta?.preco_direto ?? '')
  const [estoque, setEstoque] = useState(oferta?.estoque_disponivel ?? '0')
  const [prazo, setPrazo] = useState(oferta?.prazo_entrega_dias != null ? String(oferta.prazo_entrega_dias) : '')
  const [compraDireta, setCompraDireta] = useState(oferta?.compra_direta ?? false)
  const [visibilidade, setVisibilidade] = useState<Visibilidade>(oferta?.visibilidade ?? 'privada')
  const [regiao, setRegiao] = useState(oferta?.regiao_entrega ?? '')
  const [condicoes, setCondicoes] = useState(oferta?.condicoes ?? '')
  const [ativo, setAtivo] = useState(oferta?.ativo ?? true)

  const produtoOpt: EntityOption | undefined = oferta?.produto_descricao ? { value: oferta.produto, label: oferta.produto_descricao, hint: oferta.produto_codigo } : undefined
  const fornOpt: EntityOption | undefined = oferta?.fornecedor_nome ? { value: oferta.fornecedor, label: oferta.fornecedor_nome } : undefined

  const salvar = async () => {
    setErrors({})
    if (produto == null) return setErrors({ produto: 'Selecione o produto.' })
    if (fornecedor == null) return setErrors({ fornecedor: 'Selecione o fornecedor.' })
    if (!preco) return setErrors({ preco_direto: 'Informe o preço de compra direta.' })
    const payload: OfertaPayload = {
      produto, fornecedor, codigo_no_fornecedor: codigoForn, preco_direto: preco,
      estoque_disponivel: estoque || '0', prazo_entrega_dias: prazo ? Number(prazo) : null,
      compra_direta: compraDireta, visibilidade, regiao_entrega: regiao, condicoes, ativo,
    }
    try {
      if (oferta) await update.mutateAsync({ id: oferta.oferta_id, payload })
      else await create.mutateAsync(payload)
      onClose()
    } catch (err) { setErrors(parseApiErrors(err)) }
  }
  const excluir = async () => {
    if (!oferta || !confirm('Excluir esta oferta?')) return
    try { await remove.mutateAsync(oferta.oferta_id); onClose() } catch (err) { setErrors(parseApiErrors(err)) }
  }
  const saving = create.isPending || update.isPending

  return (
    <Drawer
      title={oferta ? 'Editar oferta' : 'Nova oferta'}
      width={520}
      onClose={onClose}
      footer={
        <>
          {oferta && <Btn variant="danger" onClick={excluir} style={{ marginRight: 'auto' }}><Trash2 size={14} /> Excluir</Btn>}
          <Btn variant="ghost" onClick={onClose}>Cancelar</Btn>
          <Btn variant="primary" onClick={salvar} disabled={saving}>{saving ? 'Salvando…' : 'Salvar'}</Btn>
        </>
      }
    >
      <FormErrorBanner errors={errors} />
      <Field label="Produto" required error={errors.produto}>
        <AsyncEntitySelect value={produto} onChange={setProduto} search={searchProdutos} resolve={resolveProduto} initialOption={produtoOpt} placeholder="Buscar produto…" />
      </Field>
      <Field label="Fornecedor" required error={errors.fornecedor}>
        <AsyncEntitySelect value={fornecedor} onChange={setFornecedor} search={searchFornecedores} resolve={resolveFornecedor} initialOption={fornOpt} placeholder="Buscar fornecedor…" />
      </Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Preço de compra direta (R$)" required error={errors.preco_direto}>
          <NumInput value={preco} onChange={setPreco} step="0.01" min={0} placeholder="0,00" />
        </Field>
        <Field label="Código no fornecedor" error={errors.codigo_no_fornecedor}>
          <TextInput value={codigoForn} onChange={e => setCodigoForn(e.target.value)} placeholder="Opcional" />
        </Field>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Estoque disponível" error={errors.estoque_disponivel}>
          <NumInput value={estoque} onChange={setEstoque} step="0.001" min={0} placeholder="0" />
        </Field>
        <Field label="Prazo de entrega (dias)" error={errors.prazo_entrega_dias}>
          <NumInput value={prazo} onChange={setPrazo} step="1" min={0} placeholder="—" />
        </Field>
      </div>

      <Checkbox checked={compraDireta} onChange={setCompraDireta} label="Disponível para compra direta (preço fixo, sem cotação)" />

      <Field label="Visibilidade" hint="'Rede' publica a oferta no marketplace (Esfera de Rede, H2). Fica privada por padrão.">
        <NativeSelect value={visibilidade} onChange={v => setVisibilidade(v as Visibilidade)}>
          <option value="privada">Privada</option>
          <option value="rede">Publicada na rede</option>
        </NativeSelect>
      </Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 12 }}>
        <Field label="Região de entrega" error={errors.regiao_entrega}>
          <TextInput value={regiao} onChange={e => setRegiao(e.target.value)} placeholder="Opcional" />
        </Field>
        <Field label="Condições" error={errors.condicoes}>
          <TextArea value={condicoes} onChange={e => setCondicoes(e.target.value)} placeholder="Condições comerciais (opcional)" />
        </Field>
      </div>
      <Checkbox checked={ativo} onChange={setAtivo} label="Oferta ativa" />

      {oferta && <FaixasEditor oferta={oferta} />}
    </Drawer>
  )
}

/** Faixas de desconto por quantidade — só na via de cotação (§3 da expansão). */
function FaixasEditor({ oferta }: { oferta: OfertaFornecedor }) {
  const { hasPermission } = useAuth()
  const podeEditar = hasPermission('scm.oferta.edit')
  const { data: faixas } = faixasHooks.useAll({ oferta: oferta.oferta_id })
  const create = faixasHooks.useCreate()
  const remove = faixasHooks.useRemove()
  const [qtd, setQtd] = useState('')
  const [preco, setPreco] = useState('')

  const add = async () => {
    if (!qtd || !preco) return
    await create.mutateAsync({ oferta: oferta.oferta_id, quantidade_min: qtd, preco_unitario: preco })
    setQtd(''); setPreco('')
  }

  const lista = (faixas ?? []) as FaixaPrecoOferta[]
  return (
    <div style={{ marginTop: 8, paddingTop: 16, borderTop: '1px solid var(--line)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <Layers size={15} style={{ color: 'var(--ink-3)' }} />
        <span style={{ fontFamily: 'var(--display)', fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>Faixas de preço (cotação)</span>
      </div>
      <p style={{ fontSize: 11.5, color: 'var(--ink-3)', marginBottom: 12 }}>Desconto por quantidade — vale na cotação, não na compra direta (preço fixo).</p>

      {lista.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
          {lista.map(f => (
            <div key={f.faixa_id} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12.5, background: 'var(--surface-2)', borderRadius: 'var(--r-sm)', padding: '7px 11px' }}>
              <span className="mono" style={{ color: 'var(--ink-2)' }}>≥ {qty(f.quantidade_min)}</span>
              <span style={{ color: 'var(--ink-3)' }}>→</span>
              <span className="mono" style={{ color: 'var(--ink)', fontWeight: 600 }}>{brl(f.preco_unitario)}</span>
              {podeEditar && (
                <button onClick={() => remove.mutate(f.faixa_id)} aria-label="Remover faixa" style={{ marginLeft: 'auto', color: 'var(--danger)', background: 'none', border: 'none', cursor: 'pointer', display: 'grid', placeItems: 'center' }}>
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {podeEditar && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 8, alignItems: 'end' }}>
          <Field label="Qtd. mínima"><NumInput value={qtd} onChange={setQtd} step="0.001" min={0} placeholder="0" /></Field>
          <Field label="Preço unit. (R$)"><NumInput value={preco} onChange={setPreco} step="0.01" min={0} placeholder="0,00" /></Field>
          <Btn variant="subtle" onClick={add} disabled={create.isPending} style={{ marginBottom: 14 }}><Plus size={14} /> Adicionar</Btn>
        </div>
      )}
    </div>
  )
}
