import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, FileText } from 'lucide-react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { FilterBar, type FilterBarValue } from '../components/shared/FilterBar'
import { FinanceDataTable } from '../components/shared/FinanceDataTable'
import { MoneyDisplay } from '../components/shared/MoneyDisplay'
import { StatusBoletoBadge } from '../components/shared/StatusBoletoBadge'
import { STATUS_BOLETO_OPTIONS } from '../components/shared/statusBoleto'
import { useBoletos } from '../hooks/useBoletos'
import { apiDecimalToCents } from '@/utils/money'
import { dateToBR } from '@/utils/dates'
import type { Boleto, BoletoFiltros, StatusBoleto } from '../types'

const PAGE_SIZE = 20

/**
 * Workspace dedicado de Boletos (D.1.2, docs/modulos/moduloerp.md §6):
 * listão paginado/filtrado no servidor das cobranças geradas via Asaas —
 * mesmo arquétipo de "Workspace de lista financeira" de Contas a Pagar/Receber,
 * mas somente leitura (o boleto nasce do gateway, não de um lançamento manual).
 * O clique na linha navega para a tela dedicada de detalhe (`/app/erp/boletos/:id`),
 * onde fica a timeline de eventos do webhook.
 */
export default function BoletosListPage() {
  const navigate = useNavigate()
  const [filtros, setFiltros] = useState<FilterBarValue>({})
  const [pageIndex, setPageIndex] = useState(0)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'data_vencimento', desc: false }])

  const ordering = sorting[0] ? `${sorting[0].desc ? '-' : ''}${sorting[0].id}` : undefined
  const queryFiltros: BoletoFiltros = useMemo(() => ({
    status: filtros.status as StatusBoleto | undefined,
    data_de: filtros.data_de,
    data_ate: filtros.data_ate,
    page: pageIndex + 1,
    page_size: PAGE_SIZE,
    ordering,
  }), [filtros, pageIndex, ordering])

  const { data, isLoading, isFetching } = useBoletos(queryFiltros)

  const columns = useMemo<ColumnDef<Boleto>[]>(() => [
    {
      accessorKey: 'boleto_id',
      header: 'Boleto',
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex flex-col">
          <span className="font-medium">#{row.original.boleto_id}</span>
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {row.original.conta_receber != null
              ? `Conta a receber #${row.original.conta_receber}`
              : row.original.conta_pagar != null
              ? `Conta a pagar #${row.original.conta_pagar}`
              : '—'}
          </span>
        </div>
      ),
    },
    {
      accessorKey: 'linha_digitavel',
      header: 'Linha digitável',
      enableSorting: false,
      cell: ({ getValue }) => {
        const linha = getValue<string | null>()
        return linha ? <span className="font-mono text-xs">{linha}</span> : <span style={{ color: 'var(--color-text-muted)' }}>—</span>
      },
    },
    {
      accessorKey: 'data_vencimento',
      header: 'Vencimento',
      cell: ({ getValue }) => dateToBR(getValue<string>()),
    },
    {
      accessorKey: 'valor',
      header: 'Valor',
      cell: ({ getValue }) => <MoneyDisplay cents={apiDecimalToCents(getValue<string>())} />,
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => <StatusBoletoBadge status={getValue<StatusBoleto>()} />,
    },
  ], [])

  return (
    <div className="px-6 py-8">
      <Link
        to="/app/erp"
        className="inline-flex items-center gap-1.5 text-xs font-semibold mb-3 transition-colors duration-150"
        style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', textDecoration: 'none' }}
        onMouseEnter={e => (e.currentTarget.style.color = 'var(--color-brand)')}
        onMouseLeave={e => (e.currentTarget.style.color = 'var(--color-text-muted)')}
      >
        <ArrowLeft size={14} /> ERP Financeiro
      </Link>

      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#e0f2fe', color: '#0369a1' }}>
          <FileText size={20} />
        </div>
        <div>
          <h1 className="text-xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            Boletos
          </h1>
          <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
            Cobranças emitidas via Asaas (boleto/PIX) — geração e baixa automática (D.1.2)
          </p>
        </div>
      </div>

      <FilterBar
        value={filtros}
        onChange={next => { setFiltros(next); setPageIndex(0) }}
        fields={['periodo', 'status']}
        statusOptions={STATUS_BOLETO_OPTIONS}
      />

      <FinanceDataTable
        data={data?.results ?? []}
        columns={columns}
        count={data?.count ?? 0}
        pageIndex={pageIndex}
        pageSize={PAGE_SIZE}
        onPageChange={setPageIndex}
        sorting={sorting}
        onSortingChange={setSorting}
        getRowId={row => String(row.boleto_id)}
        isLoading={isLoading}
        isFetching={isFetching}
        emptyMessage="Nenhum boleto encontrado para os filtros atuais. Gere uma cobrança a partir de uma conta a receber."
        onRowClick={boleto => navigate(`/app/erp/boletos/${boleto.boleto_id}`)}
      />
    </div>
  )
}
