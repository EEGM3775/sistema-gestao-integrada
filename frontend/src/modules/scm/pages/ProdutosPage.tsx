import { useState } from 'react'
import { Package, Plus, Pencil, Trash2 } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { parseApiErrors, FormErrorBanner, type FieldErrors } from '@/utils/formErrors'
import { produtosHooks } from '../hooks'
import type { Produto, ProdutoPayload, TipoItem } from '../types'
import { tipoItemLabel } from '../lib'
import {
  PageHeader, Toolbar, SearchInput, FilterSelect, DataTable, Pager, Btn,
  Drawer, Field, TextInput, NativeSelect, Checkbox, TagPill, type Column,
} from '../components/ui'

const PAGE_SIZE = 25

export default function ProdutosPage() {
  const { hasPermission } = useAuth()
  const podeEditar = hasPermission('scm.produto.edit')
  const [search, setSearch] = useState('')
  const [tipo, setTipo] = useState('')
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<Produto | null>(null)
  const [creating, setCreating] = useState(false)

  const { data, isLoading } = produtosHooks.useList({ search, tipo_item: tipo, page })
  const total = data?.count ?? 0

  const columns: Column<Produto>[] = [
    { key: 'codigo', header: 'Código', render: p => <span className="mono" style={{ color: 'var(--ink)' }}>{p.codigo_interno}</span> },
    { key: 'descricao', header: 'Descrição', render: p => <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{p.descricao}</span> },
    { key: 'unidade', header: 'Unidade', render: p => <span className="mono">{p.unidade}</span> },
    { key: 'categoria', header: 'Categoria', render: p => p.categoria || '—' },
    { key: 'tipo', header: 'Tipo', render: p => <TagPill kind={p.tipo_item === 'servico' ? 'info' : 'slate'}>{tipoItemLabel[p.tipo_item]}</TagPill> },
    { key: 'ativo', header: 'Situação', render: p => <TagPill kind={p.ativo ? 'good' : 'danger'}>{p.ativo ? 'Ativo' : 'Inativo'}</TagPill> },
    ...(podeEditar ? [{ key: 'acoes', header: '', align: 'right' as const, render: (p: Produto) => (
      <Btn size="sm" variant="subtle" onClick={() => setEditing(p)}><Pencil size={13} /> Editar</Btn>
    ) }] : []),
  ]

  return (
    <div style={{ padding: '28px 26px', maxWidth: 1180, margin: '0 auto' }}>
      <PageHeader
        icon={<Package size={22} />}
        title="Produtos"
        subtitle={isLoading ? 'Carregando…' : `${total} item${total !== 1 ? 'ns' : ''} no catálogo`}
        actions={podeEditar && <Btn variant="primary" onClick={() => setCreating(true)}><Plus size={15} /> Novo produto</Btn>}
      />

      <Toolbar>
        <SearchInput value={search} onChange={v => { setSearch(v); setPage(1) }} placeholder="Buscar por código, descrição, categoria ou GTIN…" />
        <FilterSelect value={tipo} onChange={v => { setTipo(v); setPage(1) }} allLabel="Todos os tipos"
          options={[{ value: 'material', label: 'Material' }, { value: 'servico', label: 'Serviço' }]} />
      </Toolbar>

      <DataTable columns={columns} rows={data?.results ?? []} rowKey={p => p.produto_id} loading={isLoading}
        emptyLabel={search || tipo ? 'Nenhum produto para os filtros.' : 'Nenhum produto cadastrado ainda.'} />
      <Pager page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />

      {(creating || editing) && (
        <ProdutoDrawer produto={editing} onClose={() => { setCreating(false); setEditing(null) }} />
      )}
    </div>
  )
}

function ProdutoDrawer({ produto, onClose }: { produto: Produto | null; onClose: () => void }) {
  const create = produtosHooks.useCreate()
  const update = produtosHooks.useUpdate()
  const remove = produtosHooks.useRemove()
  const [errors, setErrors] = useState<FieldErrors>({})
  const [form, setForm] = useState<ProdutoPayload>({
    codigo_interno: produto?.codigo_interno ?? '',
    descricao: produto?.descricao ?? '',
    unidade: produto?.unidade ?? '',
    categoria: produto?.categoria ?? '',
    tipo_item: produto?.tipo_item ?? 'material',
    gtin: produto?.gtin ?? '',
    item_rede_id: produto?.item_rede_id ?? '',
    ativo: produto?.ativo ?? true,
  })
  const set = <K extends keyof ProdutoPayload>(k: K, v: ProdutoPayload[K]) => { setForm(f => ({ ...f, [k]: v })); setErrors(e => ({ ...e, [k]: '' })) }

  const salvar = async () => {
    setErrors({})
    try {
      if (produto) await update.mutateAsync({ id: produto.produto_id, payload: form })
      else await create.mutateAsync(form)
      onClose()
    } catch (err) { setErrors(parseApiErrors(err)) }
  }

  const excluir = async () => {
    if (!produto || !confirm(`Excluir o produto "${produto.descricao}"?`)) return
    try { await remove.mutateAsync(produto.produto_id); onClose() } catch (err) { setErrors(parseApiErrors(err)) }
  }

  const saving = create.isPending || update.isPending
  return (
    <Drawer
      title={produto ? 'Editar produto' : 'Novo produto'}
      onClose={onClose}
      footer={
        <>
          {produto && <Btn variant="danger" onClick={excluir} style={{ marginRight: 'auto' }}><Trash2 size={14} /> Excluir</Btn>}
          <Btn variant="ghost" onClick={onClose}>Cancelar</Btn>
          <Btn variant="primary" onClick={salvar} disabled={saving}>{saving ? 'Salvando…' : 'Salvar'}</Btn>
        </>
      }
    >
      <FormErrorBanner errors={errors} />
      <Field label="Código interno (SKU)" required error={errors.codigo_interno}>
        <TextInput value={form.codigo_interno} onChange={e => set('codigo_interno', e.target.value)} placeholder="Ex.: CIM-50" />
      </Field>
      <Field label="Descrição" required error={errors.descricao}>
        <TextInput value={form.descricao} onChange={e => set('descricao', e.target.value)} placeholder="Ex.: Cimento CPII 50kg" />
      </Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Unidade" required error={errors.unidade}>
          <TextInput value={form.unidade} onChange={e => set('unidade', e.target.value)} placeholder="un, kg, m³…" />
        </Field>
        <Field label="Tipo" error={errors.tipo_item}>
          <NativeSelect value={form.tipo_item} onChange={v => set('tipo_item', v as TipoItem)}>
            <option value="material">Material</option>
            <option value="servico">Serviço</option>
          </NativeSelect>
        </Field>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Categoria" error={errors.categoria}>
          <TextInput value={form.categoria} onChange={e => set('categoria', e.target.value)} placeholder="Ex.: Aglomerantes" />
        </Field>
        <Field label="GTIN / EAN" error={errors.gtin}>
          <TextInput value={form.gtin} onChange={e => set('gtin', e.target.value)} placeholder="Opcional" />
        </Field>
      </div>
      <Checkbox checked={form.ativo} onChange={v => set('ativo', v)} label="Ativo no catálogo" />
    </Drawer>
  )
}
