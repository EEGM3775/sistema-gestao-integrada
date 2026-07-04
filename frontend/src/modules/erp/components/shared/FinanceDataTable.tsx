import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type OnChangeFn,
  type SortingState,
} from '@tanstack/react-table'
import { ChevronLeft, ChevronRight, ChevronsUpDown, ChevronUp, ChevronDown } from 'lucide-react'

/**
 * Tabela financeira server-side (docs/modulos/moduloerp.md §5.5 — arquétipo
 * "Workspace de lista financeira"): paginação e ordenação acontecem no
 * backend (`ErpPageNumberPagination` + `OrderingFilter`) — a tabela só
 * exibe a página corrente e dispara callbacks quando o usuário navega/ordena.
 * Headless (TanStack Table) para reaproveitar entre Contas a Pagar/Receber, Boletos, Lotes...
 */

interface FinanceDataTableProps<T> {
  data: T[]
  columns: ColumnDef<T, any>[]
  /** Linha única da resposta paginada do DRF — dispensa recalcular `pageCount` em cada tela. */
  count: number
  pageIndex: number
  pageSize: number
  onPageChange: (pageIndex: number) => void
  sorting: SortingState
  onSortingChange: OnChangeFn<SortingState>
  getRowId?: (row: T) => string
  isLoading?: boolean
  isFetching?: boolean
  emptyMessage?: string
  onRowClick?: (row: T) => void
}

export function FinanceDataTable<T>({
  data, columns, count, pageIndex, pageSize, onPageChange,
  sorting, onSortingChange, getRowId, isLoading, isFetching,
  emptyMessage = 'Nenhum registro encontrado.', onRowClick,
}: FinanceDataTableProps<T>) {
  const pageCount = Math.max(1, Math.ceil(count / pageSize))

  const table = useReactTable({
    data,
    columns,
    state: { sorting, pagination: { pageIndex, pageSize } },
    manualPagination: true,
    manualSorting: true,
    pageCount,
    onSortingChange,
    getRowId: getRowId as ((row: T) => string) | undefined,
    getCoreRowModel: getCoreRowModel(),
  })

  const rows = table.getRowModel().rows
  const from = count === 0 ? 0 : pageIndex * pageSize + 1
  const to = Math.min(count, (pageIndex + 1) * pageSize)

  return (
    <div className="rounded-xl overflow-hidden" style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF' }}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" style={{ fontFamily: 'var(--font-body)', borderCollapse: 'collapse' }}>
          <thead>
            {table.getHeaderGroups().map(headerGroup => (
              <tr key={headerGroup.id} style={{ borderBottom: '1.5px solid #e2e8f0', background: '#f8fafc' }}>
                {headerGroup.headers.map(header => {
                  const sortable = header.column.getCanSort()
                  const sorted = header.column.getIsSorted()
                  return (
                    <th
                      key={header.id}
                      onClick={sortable ? header.column.getToggleSortingHandler() : undefined}
                      className="text-left px-4 py-3 font-semibold"
                      style={{
                        color: 'var(--color-text-muted)', fontSize: '0.75rem',
                        textTransform: 'uppercase', letterSpacing: '0.05em',
                        cursor: sortable ? 'pointer' : 'default', userSelect: 'none', whiteSpace: 'nowrap',
                      }}
                    >
                      {header.isPlaceholder ? null : (
                        <span className="inline-flex items-center gap-1">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {sortable && (
                            sorted === 'asc' ? <ChevronUp size={13} /> :
                            sorted === 'desc' ? <ChevronDown size={13} /> :
                            <ChevronsUpDown size={13} style={{ opacity: 0.4 }} />
                          )}
                        </span>
                      )}
                    </th>
                  )
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={columns.length} className="px-4 py-10 text-center" style={{ color: 'var(--color-text-muted)' }}>Carregando…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={columns.length} className="px-4 py-10 text-center" style={{ color: 'var(--color-text-muted)' }}>{emptyMessage}</td></tr>
            ) : (
              rows.map(row => (
                <tr
                  key={row.id}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                  style={{ borderBottom: '1px solid #f1f5f9', cursor: onRowClick ? 'pointer' : 'default' }}
                  onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  {row.getVisibleCells().map(cell => (
                    <td key={cell.id} className="px-4 py-3" style={{ color: 'var(--color-text)' }}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between px-4 py-3 flex-wrap gap-2" style={{ borderTop: '1.5px solid #e2e8f0' }}>
        <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
          {count === 0 ? 'Sem registros' : `${from}–${to} de ${count}`}
          {isFetching && !isLoading && ' · atualizando…'}
        </span>
        <div className="flex items-center gap-2">
          <PageButton onClick={() => onPageChange(pageIndex - 1)} disabled={pageIndex <= 0}>
            <ChevronLeft size={16} />
          </PageButton>
          <span style={{ fontSize: '0.8rem', color: 'var(--color-text)', minWidth: '90px', textAlign: 'center' }}>
            Página {pageIndex + 1} de {pageCount}
          </span>
          <PageButton onClick={() => onPageChange(pageIndex + 1)} disabled={pageIndex + 1 >= pageCount}>
            <ChevronRight size={16} />
          </PageButton>
        </div>
      </div>
    </div>
  )
}

function PageButton({ onClick, disabled, children }: { onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="p-1.5 rounded-lg transition-colors duration-150"
      style={{
        border: '1.5px solid #e2e8f0', background: '#FFFFFF',
        color: disabled ? '#cbd5e1' : 'var(--color-text-muted)',
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
      onMouseEnter={e => { if (!disabled) e.currentTarget.style.borderColor = 'var(--color-brand)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = '#e2e8f0' }}
    >
      {children}
    </button>
  )
}
