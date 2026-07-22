import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Landmark, Plus, Pencil, Trash2 } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { parseApiErrors, FormErrorBanner, type FieldErrors } from '@/utils/formErrors'
import { centrosCustoHooks } from '../hooks'
import { listObrasOpt, listEmpreendimentosOpt } from '../api/scmApi'
import type { CentroCusto, CentroCustoPayload, TipoCentroCusto } from '../types'
import { tipoCentroCustoLabel } from '../lib'
import {
  PageHeader, Toolbar, SearchInput, FilterSelect, DataTable, Pager, Btn,
  Drawer, Field, TextInput, NativeSelect, Checkbox, TagPill, type Column,
} from '../components/ui'

const PAGE_SIZE = 25
const TIPOS: TipoCentroCusto[] = ['obra', 'empreendimento', 'almoxarifado', 'filial', 'administrativo', 'outro']

export default function CentrosCustoPage() {
  const { hasPermission } = useAuth()
  const podeEditar = hasPermission('scm.centro_custo.edit')
  const [search, setSearch] = useState('')
  const [tipo, setTipo] = useState('')
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<CentroCusto | null>(null)
  const [creating, setCreating] = useState(false)

  const { data, isLoading } = centrosCustoHooks.useList({ search, tipo, page })
  const total = data?.count ?? 0

  const columns: Column<CentroCusto>[] = [
    { key: 'codigo', header: 'Código', render: c => <span className="mono" style={{ color: 'var(--ink)' }}>{c.codigo || '—'}</span> },
    { key: 'nome', header: 'Nome', render: c => <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{c.nome}</span> },
    { key: 'tipo', header: 'Tipo', render: c => <TagPill>{tipoCentroCustoLabel[c.tipo]}</TagPill> },
    { key: 'ativo', header: 'Situação', render: c => <TagPill kind={c.ativo ? 'good' : 'danger'}>{c.ativo ? 'Ativo' : 'Inativo'}</TagPill> },
    ...(podeEditar ? [{ key: 'acoes', header: '', align: 'right' as const, render: (c: CentroCusto) => (
      <Btn size="sm" variant="subtle" onClick={() => setEditing(c)}><Pencil size={13} /> Editar</Btn>
    ) }] : []),
  ]

  return (
    <div style={{ padding: '28px 26px', maxWidth: 1180, margin: '0 auto' }}>
      <PageHeader
        icon={<Landmark size={22} />}
        title="Centros de custo"
        subtitle={isLoading ? 'Carregando…' : `${total} centro${total !== 1 ? 's' : ''} de custo`}
        actions={podeEditar && <Btn variant="primary" onClick={() => setCreating(true)}><Plus size={15} /> Novo centro de custo</Btn>}
      />
      <Toolbar>
        <SearchInput value={search} onChange={v => { setSearch(v); setPage(1) }} placeholder="Buscar por nome ou código…" />
        <FilterSelect value={tipo} onChange={v => { setTipo(v); setPage(1) }} allLabel="Todos os tipos"
          options={TIPOS.map(t => ({ value: t, label: tipoCentroCustoLabel[t] }))} />
      </Toolbar>
      <DataTable columns={columns} rows={data?.results ?? []} rowKey={c => c.centro_custo_id} loading={isLoading}
        emptyLabel={search || tipo ? 'Nenhum centro de custo para os filtros.' : 'Nenhum centro de custo cadastrado ainda.'} />
      <Pager page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />

      {(creating || editing) && (
        <CentroCustoDrawer centro={editing} onClose={() => { setCreating(false); setEditing(null) }} />
      )}
    </div>
  )
}

function CentroCustoDrawer({ centro, onClose }: { centro: CentroCusto | null; onClose: () => void }) {
  const create = centrosCustoHooks.useCreate()
  const update = centrosCustoHooks.useUpdate()
  const remove = centrosCustoHooks.useRemove()
  const [errors, setErrors] = useState<FieldErrors>({})
  const [form, setForm] = useState<CentroCustoPayload>({
    nome: centro?.nome ?? '',
    codigo: centro?.codigo ?? '',
    tipo: centro?.tipo ?? 'obra',
    empreendimento: centro?.empreendimento ?? null,
    obra: centro?.obra ?? null,
    local_estoque_ref: centro?.local_estoque_ref ?? '',
    ativo: centro?.ativo ?? true,
  })
  const set = <K extends keyof CentroCustoPayload>(k: K, v: CentroCustoPayload[K]) => { setForm(f => ({ ...f, [k]: v })); setErrors(e => ({ ...e, [k]: '' })) }

  const obras = useQuery({ queryKey: ['scm', 'opts', 'obras'], queryFn: listObrasOpt, enabled: form.tipo === 'obra' })
  const empreends = useQuery({ queryKey: ['scm', 'opts', 'empreendimentos'], queryFn: listEmpreendimentosOpt, enabled: form.tipo === 'empreendimento' })

  const salvar = async () => {
    setErrors({})
    // Vínculo polimórfico: só o campo do tipo escolhido viaja.
    const payload: CentroCustoPayload = {
      ...form,
      obra: form.tipo === 'obra' ? form.obra : null,
      empreendimento: form.tipo === 'empreendimento' ? form.empreendimento : null,
    }
    try {
      if (centro) await update.mutateAsync({ id: centro.centro_custo_id, payload })
      else await create.mutateAsync(payload)
      onClose()
    } catch (err) { setErrors(parseApiErrors(err)) }
  }
  const excluir = async () => {
    if (!centro || !confirm(`Excluir o centro de custo "${centro.nome}"?`)) return
    try { await remove.mutateAsync(centro.centro_custo_id); onClose() } catch (err) { setErrors(parseApiErrors(err)) }
  }
  const saving = create.isPending || update.isPending

  return (
    <Drawer
      title={centro ? 'Editar centro de custo' : 'Novo centro de custo'}
      onClose={onClose}
      footer={
        <>
          {centro && <Btn variant="danger" onClick={excluir} style={{ marginRight: 'auto' }}><Trash2 size={14} /> Excluir</Btn>}
          <Btn variant="ghost" onClick={onClose}>Cancelar</Btn>
          <Btn variant="primary" onClick={salvar} disabled={saving}>{saving ? 'Salvando…' : 'Salvar'}</Btn>
        </>
      }
    >
      <FormErrorBanner errors={errors} />
      <Field label="Nome" required error={errors.nome}>
        <TextInput value={form.nome} onChange={e => set('nome', e.target.value)} placeholder="Ex.: Obra Residencial Aurora" />
      </Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Código" error={errors.codigo}>
          <TextInput value={form.codigo} onChange={e => set('codigo', e.target.value)} placeholder="Opcional" />
        </Field>
        <Field label="Tipo" required error={errors.tipo}>
          <NativeSelect value={form.tipo} onChange={v => set('tipo', v as TipoCentroCusto)}>
            {TIPOS.map(t => <option key={t} value={t}>{tipoCentroCustoLabel[t]}</option>)}
          </NativeSelect>
        </Field>
      </div>

      {form.tipo === 'obra' && (
        <Field label="Obra vinculada" error={errors.obra}>
          <NativeSelect value={form.obra != null ? String(form.obra) : ''} onChange={v => set('obra', v ? Number(v) : null)}>
            <option value="">— Selecione —</option>
            {obras.data?.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </NativeSelect>
        </Field>
      )}
      {form.tipo === 'empreendimento' && (
        <Field label="Empreendimento vinculado" error={errors.empreendimento}>
          <NativeSelect value={form.empreendimento != null ? String(form.empreendimento) : ''} onChange={v => set('empreendimento', v ? Number(v) : null)}>
            <option value="">— Selecione —</option>
            {empreends.data?.map(e => <option key={e.value} value={e.value}>{e.label}</option>)}
          </NativeSelect>
        </Field>
      )}

      <Field label="Local de estoque (referência)" hint="Seam para o módulo de estoque (SIL), que ainda não existe — opcional." error={errors.local_estoque_ref}>
        <TextInput value={form.local_estoque_ref} onChange={e => set('local_estoque_ref', e.target.value)} placeholder="Ex.: ALM-CENTRAL" />
      </Field>
      <Checkbox checked={form.ativo} onChange={v => set('ativo', v)} label="Ativo" />
    </Drawer>
  )
}
