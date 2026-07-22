import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ClipboardList, Plus } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { parseApiErrors, FormErrorBanner, type FieldErrors } from '@/utils/formErrors'
import { demandasHooks } from '../hooks'
import { searchCentrosCusto, resolveCentroCusto } from '../api/scmApi'
import type { Demanda, DemandaPayload, TipoItem, StatusDemanda } from '../types'
import { demandaEstado, tipoItemLabel, dataHoraBR } from '../lib'
import {
  PageHeader, Toolbar, SearchInput, FilterSelect, DataTable, Pager, Btn,
  Drawer, Field, TextInput, TextArea, NativeSelect, EstadoPill, TagPill, type Column,
} from '../components/ui'
import { AsyncEntitySelect } from '../components/AsyncEntitySelect'
import { SeamChips, demandaSeams } from '../components/seams'
import { Num } from '@/components/malha'

const PAGE_SIZE = 25
const STATUS: StatusDemanda[] = ['rascunho', 'aberta', 'em_cotacao', 'atendida', 'cancelada']

export default function DemandasPage() {
  const navigate = useNavigate()
  const { hasPermission } = useAuth()
  const podeCriar = hasPermission('scm.demanda.edit')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [tipo, setTipo] = useState('')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)

  const { data, isLoading } = demandasHooks.useList({ search, status, tipo, page })
  const total = data?.count ?? 0

  const columns: Column<Demanda>[] = [
    { key: 'id', header: 'Demanda', render: d => <span className="mono" style={{ color: 'var(--ink)', fontWeight: 600 }}>#{d.demanda_id}</span> },
    { key: 'tipo', header: 'Tipo', render: d => <TagPill kind={d.tipo === 'servico' ? 'info' : 'slate'}>{tipoItemLabel[d.tipo]}</TagPill> },
    { key: 'status', header: 'Estado', render: d => <EstadoPill estado={demandaEstado[d.status]} /> },
    { key: 'cc', header: 'Centro de custo', render: d => d.centro_custo_nome ?? '—' },
    { key: 'itens', header: 'Itens', align: 'right', render: d => <Num right>{d.itens_count ?? 0}</Num> },
    { key: 'seams', header: 'Rede', render: d => <SeamChips seams={demandaSeams(d)} /> },
    { key: 'criado', header: 'Criada', render: d => <span className="mono" style={{ fontSize: 12, color: 'var(--ink-3)' }}>{dataHoraBR(d.criado_em)}</span> },
  ]

  return (
    <div style={{ padding: '28px 26px', maxWidth: 1180, margin: '0 auto' }}>
      <PageHeader
        icon={<ClipboardList size={22} />}
        title="Demandas"
        subtitle={isLoading ? 'Carregando…' : `${total} demanda${total !== 1 ? 's' : ''} de compra`}
        actions={podeCriar && <Btn variant="primary" onClick={() => setCreating(true)}><Plus size={15} /> Nova demanda</Btn>}
      />
      <Toolbar>
        <SearchInput value={search} onChange={v => { setSearch(v); setPage(1) }} placeholder="Buscar por categoria, região ou observação…" />
        <FilterSelect value={status} onChange={v => { setStatus(v); setPage(1) }} allLabel="Todos os estados"
          options={STATUS.map(s => ({ value: s, label: demandaEstado[s].label }))} />
        <FilterSelect value={tipo} onChange={v => { setTipo(v); setPage(1) }} allLabel="Todos os tipos"
          options={[{ value: 'material', label: 'Material' }, { value: 'servico', label: 'Serviço' }]} />
      </Toolbar>
      <DataTable columns={columns} rows={data?.results ?? []} rowKey={d => d.demanda_id} loading={isLoading}
        onRowClick={d => navigate(`/app/scm/demandas/${d.demanda_id}`)}
        emptyLabel={search || status || tipo ? 'Nenhuma demanda para os filtros.' : 'Nenhuma demanda cadastrada ainda.'} />
      <Pager page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />

      {creating && <DemandaDrawer onClose={() => setCreating(false)} onCreated={id => navigate(`/app/scm/demandas/${id}`)} />}
    </div>
  )
}

function DemandaDrawer({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const create = demandasHooks.useCreate()
  const [errors, setErrors] = useState<FieldErrors>({})
  const [tipo, setTipo] = useState<TipoItem>('material')
  const [centroCusto, setCentroCusto] = useState<number | null>(null)
  const [categoria, setCategoria] = useState('')
  const [regiao, setRegiao] = useState('')
  const [observacao, setObservacao] = useState('')

  const salvar = async () => {
    setErrors({})
    const payload: DemandaPayload = { tipo, centro_custo: centroCusto, categoria, regiao, observacao }
    try {
      const nova = await create.mutateAsync(payload)
      onCreated(nova.demanda_id)
    } catch (err) { setErrors(parseApiErrors(err)) }
  }

  return (
    <Drawer
      title="Nova demanda"
      onClose={onClose}
      footer={<>
        <Btn variant="ghost" onClick={onClose}>Cancelar</Btn>
        <Btn variant="primary" onClick={salvar} disabled={create.isPending}>{create.isPending ? 'Criando…' : 'Criar demanda'}</Btn>
      </>}
    >
      <FormErrorBanner errors={errors} />
      <Field label="Tipo" required error={errors.tipo}>
        <NativeSelect value={tipo} onChange={v => setTipo(v as TipoItem)}>
          <option value="material">Material</option>
          <option value="servico">Serviço</option>
        </NativeSelect>
      </Field>
      <Field label="Centro de custo" error={errors.centro_custo}>
        <AsyncEntitySelect value={centroCusto} onChange={setCentroCusto} search={searchCentrosCusto} resolve={resolveCentroCusto} placeholder="Buscar centro de custo…" />
      </Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Categoria" error={errors.categoria}>
          <TextInput value={categoria} onChange={e => setCategoria(e.target.value)} placeholder="Opcional" />
        </Field>
        <Field label="Região" error={errors.regiao}>
          <TextInput value={regiao} onChange={e => setRegiao(e.target.value)} placeholder="Opcional" />
        </Field>
      </div>
      <Field label="Observação" error={errors.observacao}>
        <TextArea value={observacao} onChange={e => setObservacao(e.target.value)} placeholder="Detalhes da necessidade (opcional)" />
      </Field>
      <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Os itens da demanda são adicionados na tela seguinte.</p>
    </Drawer>
  )
}
