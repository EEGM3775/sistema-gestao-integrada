import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, FileText, FileSearch, Ban } from 'lucide-react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { FilterBar, type FilterBarValue } from '../components/shared/FilterBar'
import { FinanceDataTable } from '../components/shared/FinanceDataTable'
import { MoneyDisplay } from '../components/shared/MoneyDisplay'
import { StatusBoletoBadge } from '../components/shared/StatusBoletoBadge'
import { BotaoErroGateway } from '../components/shared/GatewayErro'
import { useBoletos, useCancelarBoleto, useVerificarDocumentoBoleto } from '../hooks/useBoletos'
import { apiDecimalToCents } from '@/utils/money'
import { dateToBR } from '@/utils/dates'
import type { Boleto, BoletoFiltros } from '../types'

const PAGE_SIZE = 20

type Aba = 'ativos' | 'cancelados'

const ABAS: { id: Aba; label: string }[] = [
  { id: 'ativos', label: 'Ativos' },
  { id: 'cancelados', label: 'Cancelados' },
]

/**
 * Workspace dedicado de Boletos (D.1.2, docs/modulos/moduloerp.md §6):
 * listão paginado/filtrado no servidor das cobranças geradas via Asaas. Duas
 * abas — "Ativos" (exclui cancelados) e "Cancelados" — porque toda informação é
 * útil: um boleto cancelado não some, fica auditável na sua aba. O status "Erro"
 * é clicável (abre os códigos do Asaas), e o documento é aberto verificando o
 * gateway AO VIVO. O clique na linha navega para o detalhe (`/app/erp/boletos/:id`).
 */
export default function BoletosListPage() {
  const [aba, setAba] = useState<Aba>('ativos')

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
            Cobranças emitidas via Asaas (boleto/PIX) — geração, cancelamento e baixa automática (D.1.2)
          </p>
        </div>
      </div>

      {/* Abas */}
      <div className="flex items-center gap-1 mb-5 border-b" style={{ borderColor: '#e2e8f0' }}>
        {ABAS.map(({ id, label }) => {
          const ativa = aba === id
          return (
            <button
              key={id}
              type="button"
              onClick={() => setAba(id)}
              className="px-4 py-2.5 text-sm font-semibold transition-colors duration-150"
              style={{
                fontFamily: 'var(--font-body)',
                color: ativa ? 'var(--color-brand)' : 'var(--color-text-muted)',
                borderBottom: ativa ? '2px solid var(--color-brand)' : '2px solid transparent',
                marginBottom: '-1px',
                background: 'transparent',
                cursor: 'pointer',
              }}
            >
              {label}
            </button>
          )
        })}
      </div>

      <BoletosTab cancelados={aba === 'cancelados'} />
    </div>
  )
}

function BoletosTab({ cancelados }: { cancelados: boolean }) {
  const navigate = useNavigate()
  const [filtros, setFiltros] = useState<FilterBarValue>({})
  const [pageIndex, setPageIndex] = useState(0)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'data_vencimento', desc: false }])
  const [mensagem, setMensagem] = useState<{ tom: 'ok' | 'erro'; texto: string } | null>(null)

  const cancelar = useCancelarBoleto()
  const verificarDoc = useVerificarDocumentoBoleto()
  const acaoOcupada = cancelar.isPending || verificarDoc.isPending

  const ordering = sorting[0] ? `${sorting[0].desc ? '-' : ''}${sorting[0].id}` : undefined
  const queryFiltros: BoletoFiltros = useMemo(() => ({
    ...(cancelados ? { status: 'CANCELADO' as const } : { excluir_status: 'CANCELADO' as const }),
    data_de: filtros.data_de,
    data_ate: filtros.data_ate,
    page: pageIndex + 1,
    page_size: PAGE_SIZE,
    ordering,
  }), [cancelados, filtros, pageIndex, ordering])

  const { data, isLoading, isFetching } = useBoletos(queryFiltros)

  /** Abre o documento verificando o Asaas AO VIVO (aba aberta no clique p/ não bloquear popup). */
  function aoVerDocumento(boleto: Boleto) {
    const win = window.open('', '_blank')
    verificarDoc.mutate(boleto.boleto_id, {
      onSuccess: doc => {
        if (doc.url_pdf && win) win.location.href = doc.url_pdf
        else if (win) win.close()
        if (!doc.gateway_online) setMensagem({ tom: 'erro', texto: doc.mensagem })
        else if (!doc.url_pdf) setMensagem({ tom: 'erro', texto: 'Documento ainda indisponível no Asaas.' })
      },
      onError: () => { if (win) win.close(); setMensagem({ tom: 'erro', texto: 'Não foi possível verificar o documento no Asaas.' }) },
    })
  }

  function aoCancelar(boleto: Boleto) {
    if (!window.confirm(`Cancelar o boleto #${boleto.boleto_id} no Asaas? A ação não pode ser desfeita.`)) return
    cancelar.mutate(boleto.boleto_id, {
      onSuccess: r => setMensagem({ tom: 'ok', texto: r.detail }),
      onError: () => setMensagem({ tom: 'erro', texto: 'Não foi possível cancelar o boleto agora.' }),
    })
  }

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
    ...(cancelados ? [{
      accessorKey: 'data_cancelamento',
      header: 'Cancelado em',
      enableSorting: false,
      cell: ({ getValue }: { getValue: () => string | null }) => {
        const v = getValue()
        return v ? dateToBR(v) : <span style={{ color: 'var(--color-text-muted)' }}>—</span>
      },
    } as ColumnDef<Boleto>] : []),
    {
      accessorKey: 'valor',
      header: 'Valor',
      cell: ({ getValue }) => <MoneyDisplay cents={apiDecimalToCents(getValue<string>())} />,
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const b = row.original
        // "Erro" vira botão → popup com todos os códigos/mensagens do Asaas.
        return b.status === 'ERRO'
          ? <BotaoErroGateway dados={b.dados_retorno_api} titulo="Erro na cobrança (Asaas)" />
          : <StatusBoletoBadge status={b.status} />
      },
    },
    {
      id: 'acoes',
      header: 'Ações',
      enableSorting: false,
      cell: ({ row }) => {
        const b = row.original
        const cancelavel = ['EMITIDO', 'VENCIDO', 'AGUARDANDO'].includes(b.status)
        return (
          <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
            <AcaoBoletoButton
              titulo="Abrir documento (verifica no Asaas)"
              onClick={() => aoVerDocumento(b)}
              disabled={acaoOcupada || !b.gateway_id}
              icon={<FileSearch size={14} />}
            />
            <AcaoBoletoButton
              titulo="Cancelar boleto no Asaas"
              onClick={() => aoCancelar(b)}
              disabled={acaoOcupada || !cancelavel}
              icon={<Ban size={14} />}
              perigo
            />
          </div>
        )
      },
    },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [cancelados, acaoOcupada])

  return (
    <>
      {mensagem && (
        <div
          className="text-sm px-4 py-3 rounded-lg mb-4"
          style={mensagem.tom === 'ok'
            ? { background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#166534', fontFamily: 'var(--font-body)' }
            : { background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030', fontFamily: 'var(--font-body)' }}
        >
          {mensagem.texto}
        </div>
      )}

      <FilterBar
        value={filtros}
        onChange={next => { setFiltros(next); setPageIndex(0) }}
        fields={['periodo']}
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
        emptyMessage={cancelados
          ? 'Nenhum boleto cancelado.'
          : 'Nenhum boleto encontrado. Gere uma cobrança a partir de uma conta a receber.'}
        onRowClick={boleto => navigate(`/app/erp/boletos/${boleto.boleto_id}`)}
      />
    </>
  )
}

function AcaoBoletoButton({ titulo, onClick, disabled, icon, perigo }: {
  titulo: string; onClick: () => void; disabled?: boolean; icon: React.ReactNode; perigo?: boolean
}) {
  const cor = perigo ? '#b91c1c' : 'var(--color-text-muted)'
  return (
    <button
      type="button"
      title={titulo}
      aria-label={titulo}
      onClick={onClick}
      disabled={disabled}
      className="p-1.5 rounded-lg transition-colors duration-150"
      style={{
        border: '1.5px solid #e2e8f0', background: '#FFFFFF',
        color: disabled ? '#cbd5e1' : cor,
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
      onMouseEnter={e => { if (!disabled) e.currentTarget.style.borderColor = perigo ? '#b91c1c' : 'var(--color-brand)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = '#e2e8f0' }}
    >
      {icon}
    </button>
  )
}
