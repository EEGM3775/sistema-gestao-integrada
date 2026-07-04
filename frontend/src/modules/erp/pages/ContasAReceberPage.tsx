import { useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Plus } from 'lucide-react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { FilterBar, type FilterBarValue } from '../components/shared/FilterBar'
import { FinanceDataTable } from '../components/shared/FinanceDataTable'
import { Sheet } from '../components/shared/Sheet'
import { MoneyDisplay } from '../components/shared/MoneyDisplay'
import { StatusContaBadge } from '../components/shared/StatusContaBadge'
import { StatusBoletoBadge } from '../components/shared/StatusBoletoBadge'
import { STATUS_CONTA_OPTIONS } from '../components/shared/statusConta'
import { ContaReceberForm } from '../components/forms/ContaReceberForm'
import { BaixaForm } from '../components/forms/BaixaForm'
import { buttonPrimaryStyle, buttonSecondaryStyle } from '../components/forms/formStyles'
import {
  useContasAReceber, useCreateContaAReceber, useUpdateContaAReceber, useDarBaixaContaAReceber,
} from '../hooks/useContasAReceber'
import { useGerarCobrancaContaAReceber } from '../hooks/useBoletos'
import { useClienteOptions, useEmpreendimentoOptions } from '../hooks/useEntityOptions'
import { apiDecimalToCents } from '@/utils/money'
import { dateToBR } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import type { ContaReceber, ContaReceberFiltros, StatusConta } from '../types'

/** Feedback do fluxo assíncrono de "Gerar cobrança" — `ok` mostra confirmação, `erro` destaca o bloqueio. */
type GerarCobrancaFeedback = { tipo: 'ok' | 'erro'; mensagem: string } | null

const PAGE_SIZE = 20

type SheetState =
  | { mode: 'create' }
  | { mode: 'view' | 'edit' | 'baixa'; conta: ContaReceber }

/**
 * Workspace de Contas a Receber (D.1.1, docs/modulos/moduloerp.md §5.5):
 * listão paginado/filtrado no servidor + Sheet de lançamento/detalhe/baixa —
 * mesmo arquétipo de "Workspace de lista financeira" usado em Contas a Pagar.
 */
export default function ContasAReceberPage() {
  const [filtros, setFiltros] = useState<FilterBarValue>({})
  const [pageIndex, setPageIndex] = useState(0)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'data_vencimento', desc: false }])
  const [sheet, setSheet] = useState<SheetState | null>(null)

  const ordering = sorting[0] ? `${sorting[0].desc ? '-' : ''}${sorting[0].id}` : undefined
  const queryFiltros: ContaReceberFiltros = useMemo(() => ({
    status: filtros.status as StatusConta | undefined,
    empreendimento: filtros.empreendimento,
    cliente: filtros.cliente,
    data_de: filtros.data_de,
    data_ate: filtros.data_ate,
    search: filtros.search,
    page: pageIndex + 1,
    page_size: PAGE_SIZE,
    ordering,
  }), [filtros, pageIndex, ordering])

  const { data, isLoading, isFetching } = useContasAReceber(queryFiltros)
  const clienteOptions = useClienteOptions(true)
  const empreendimentoOptions = useEmpreendimentoOptions(true)

  const labelCliente = (id: number | null) =>
    (id != null && clienteOptions.data?.find(o => o.id === id)?.label) || (id ? `Cliente #${id}` : '—')
  const labelEmpreendimento = (id: number | null) =>
    id == null ? '—' : (empreendimentoOptions.data?.find(o => o.id === id)?.label ?? `Obra #${id}`)

  const createMutation = useCreateContaAReceber()
  const updateMutation = useUpdateContaAReceber()
  const baixaMutation = useDarBaixaContaAReceber()
  const gerarCobrancaMutation = useGerarCobrancaContaAReceber()

  const columns = useMemo<ColumnDef<ContaReceber>[]>(() => [
    {
      accessorKey: 'descricao',
      header: 'Descrição',
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex flex-col">
          <span className="font-medium">{row.original.descricao}</span>
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {labelEmpreendimento(row.original.empreendimento)}
          </span>
        </div>
      ),
    },
    {
      accessorKey: 'cliente',
      header: 'Cliente',
      enableSorting: false,
      cell: ({ getValue }) => labelCliente(getValue<number | null>()),
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
      accessorKey: 'saldo_aberto',
      header: 'Saldo em aberto',
      enableSorting: false,
      cell: ({ getValue }) => <MoneyDisplay cents={apiDecimalToCents(getValue<string>())} />,
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => <StatusContaBadge status={getValue<StatusConta>()} />,
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [clienteOptions.data, empreendimentoOptions.data])

  const closeSheet = () => setSheet(null)

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

      <div className="flex items-center justify-between gap-3 mb-6 flex-wrap">
        <div>
          <h1 className="text-xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            Contas a receber
          </h1>
          <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
            Lançamentos, rateios e recebimentos de clientes
          </p>
        </div>
        <button
          type="button"
          onClick={() => setSheet({ mode: 'create' })}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-colors duration-150"
          style={{ background: 'var(--color-brand)', color: '#FFFFFF', fontFamily: 'var(--font-body)', cursor: 'pointer' }}
        >
          <Plus size={16} /> Nova conta
        </button>
      </div>

      <FilterBar
        value={filtros}
        onChange={next => { setFiltros(next); setPageIndex(0) }}
        fields={['search', 'periodo', 'empreendimento', 'cliente', 'status']}
        statusOptions={STATUS_CONTA_OPTIONS}
        searchPlaceholder="Buscar por descrição…"
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
        getRowId={row => String(row.conta_receber_id)}
        isLoading={isLoading}
        isFetching={isFetching}
        emptyMessage="Nenhuma conta a receber encontrada para os filtros atuais."
        onRowClick={conta => setSheet({ mode: 'view', conta })}
      />

      <Sheet
        open={sheet != null}
        onClose={closeSheet}
        width={560}
        title={
          sheet?.mode === 'create' ? 'Nova conta a receber'
          : sheet?.mode === 'edit' ? 'Editar conta a receber'
          : sheet?.mode === 'baixa' ? 'Dar baixa'
          : sheet?.mode === 'view' ? sheet.conta.descricao
          : ''
        }
        description={sheet && sheet.mode !== 'create' ? labelCliente(sheet.conta.cliente) : undefined}
      >
        {sheet?.mode === 'create' && (
          <ContaReceberForm
            onCancel={closeSheet}
            onSubmit={async payload => { await createMutation.mutateAsync(payload); closeSheet() }}
          />
        )}

        {sheet?.mode === 'edit' && (
          <ContaReceberForm
            initial={sheet.conta}
            onCancel={closeSheet}
            onSubmit={async payload => {
              await updateMutation.mutateAsync({ id: sheet.conta.conta_receber_id, payload })
              closeSheet()
            }}
          />
        )}

        {sheet?.mode === 'baixa' && (
          <BaixaForm
            saldoAberto={sheet.conta.saldo_aberto}
            onCancel={closeSheet}
            onSubmit={async payload => {
              await baixaMutation.mutateAsync({ id: sheet.conta.conta_receber_id, payload })
              closeSheet()
            }}
          />
        )}

        {sheet?.mode === 'view' && (
          <ContaReceberDetail
            conta={sheet.conta}
            labelEmpreendimento={labelEmpreendimento}
            onEditar={() => setSheet({ mode: 'edit', conta: sheet.conta })}
            onDarBaixa={() => setSheet({ mode: 'baixa', conta: sheet.conta })}
            onGerarCobranca={() => gerarCobrancaMutation.mutate(sheet.conta.conta_receber_id)}
            gerarCobrancaPending={gerarCobrancaMutation.isPending}
            gerarCobrancaFeedback={
              gerarCobrancaMutation.isSuccess
                ? { tipo: 'ok', mensagem: gerarCobrancaMutation.data?.detail ?? 'Cobrança iniciada.' }
                : gerarCobrancaMutation.isError
                ? { tipo: 'erro', mensagem: parseApiErrors(gerarCobrancaMutation.error)._form
                    ?? 'Não foi possível gerar a cobrança no Asaas — tente novamente.' }
                : null
            }
          />
        )}
      </Sheet>
    </div>
  )
}

function ContaReceberDetail({
  conta, labelEmpreendimento, onEditar, onDarBaixa,
  onGerarCobranca, gerarCobrancaPending, gerarCobrancaFeedback,
}: {
  conta: ContaReceber
  labelEmpreendimento: (id: number | null) => string
  onEditar: () => void
  onDarBaixa: () => void
  onGerarCobranca: () => void
  gerarCobrancaPending: boolean
  gerarCobrancaFeedback: GerarCobrancaFeedback
}) {
  const podeBaixar = conta.status === 'ABERTO' || conta.status === 'PARCIAL'
  const podeGerarCobranca = conta.status === 'ABERTO' || conta.status === 'PARCIAL'
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <StatusContaBadge status={conta.status} />
        <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{labelEmpreendimento(conta.empreendimento)}</span>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm" style={{ fontFamily: 'var(--font-body)' }}>
        <DetailItem label="Valor" value={<MoneyDisplay cents={apiDecimalToCents(conta.valor)} />} />
        <DetailItem label="Saldo em aberto" value={<MoneyDisplay cents={apiDecimalToCents(conta.saldo_aberto)} />} />
        <DetailItem label="Emissão" value={conta.data_emissao ? dateToBR(conta.data_emissao) : '—'} />
        <DetailItem label="Vencimento" value={dateToBR(conta.data_vencimento)} />
        <DetailItem label="Agendamento" value={conta.data_agendamento ? dateToBR(conta.data_agendamento) : '—'} />
        <DetailItem label="Recebimento" value={conta.data_recebimento ? dateToBR(conta.data_recebimento) : '—'} />
      </dl>

      {conta.rateios.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: 'var(--color-brand)' }}>
            Rateio por centro de custo
          </h3>
          <ul className="flex flex-col gap-1 text-sm">
            {conta.rateios.map(r => (
              <li key={r.rateio_id} className="flex items-center justify-between">
                <span>{r.centro_custo_nome}</span>
                <MoneyDisplay cents={apiDecimalToCents(r.valor)} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {conta.boletos.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: 'var(--color-brand)' }}>Boletos</h3>
          <ul className="flex flex-col gap-1.5 text-sm">
            {conta.boletos.map(b => (
              <li key={b.boleto_id} className="flex items-center justify-between">
                <Link
                  to={`/app/erp/boletos/${b.boleto_id}`}
                  className="flex items-center gap-2"
                  style={{ color: 'var(--color-text)', textDecoration: 'none' }}
                  onMouseEnter={e => (e.currentTarget.style.color = 'var(--color-brand)')}
                  onMouseLeave={e => (e.currentTarget.style.color = 'var(--color-text)')}
                >
                  <span>{dateToBR(b.data_vencimento)}</span>
                  <StatusBoletoBadge status={b.status} />
                </Link>
                <MoneyDisplay cents={apiDecimalToCents(b.valor)} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {gerarCobrancaFeedback && (
        gerarCobrancaFeedback.tipo === 'erro' ? (
          <div
            role="alert"
            className="text-sm"
            style={{
              padding: '10px 14px', borderRadius: '8px',
              background: '#fff5f5', border: '1px solid #fed7d7',
              color: '#c53030', fontFamily: 'var(--font-body)', lineHeight: 1.4,
            }}
          >
            ⚠ {gerarCobrancaFeedback.mensagem}
          </div>
        ) : (
          <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
            {gerarCobrancaFeedback.mensagem}
          </p>
        )
      )}

      <div className="flex items-center justify-end gap-2 pt-2">
        <button type="button" onClick={onEditar} style={buttonSecondaryStyle}>Editar</button>
        {podeGerarCobranca && (
          <button type="button" onClick={onGerarCobranca} disabled={gerarCobrancaPending} style={{ ...buttonSecondaryStyle, opacity: gerarCobrancaPending ? 0.6 : 1, cursor: gerarCobrancaPending ? 'wait' : 'pointer' }}>
            {gerarCobrancaPending ? 'Gerando…' : 'Gerar cobrança (Asaas)'}
          </button>
        )}
        {podeBaixar && <button type="button" onClick={onDarBaixa} style={buttonPrimaryStyle}>Dar baixa</button>}
      </div>
    </div>
  )
}

function DetailItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{label}</dt>
      <dd className="font-medium" style={{ color: 'var(--color-text)' }}>{value}</dd>
    </div>
  )
}
