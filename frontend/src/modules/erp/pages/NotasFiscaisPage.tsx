import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, FileText, RefreshCw, Ban, FileDown, FileCode2, Plus, FileSearch } from 'lucide-react'
import type { ColumnDef } from '@tanstack/react-table'
import { FinanceDataTable } from '../components/shared/FinanceDataTable'
import { MoneyDisplay } from '../components/shared/MoneyDisplay'
import { StatusNfeBadge } from '../components/shared/StatusNfeBadge'
import { BotaoErroGateway } from '../components/shared/GatewayErro'
import { EmitirNfseDialog } from '../components/EmitirNfseDialog'
import {
  useNotasFiscaisServico, useNotasFiscaisRecebidas,
  useConsultarStatusNfse, useCancelarNfse, useVerificarDocumentoNfse,
} from '../hooks/useNotasFiscais'
import { baixarArquivo, baixarParaDisco } from '@/lib/arquivo'
import { apiDecimalToCents } from '@/utils/money'
import { dateToBR } from '@/utils/dates'
import type { NotaFiscalRecebida, NotaFiscalServico } from '../types'

const PAGE_SIZE = 20

type Aba = 'emitidas' | 'canceladas' | 'recebidas'

const ABAS: { id: Aba; label: string }[] = [
  { id: 'emitidas', label: 'Emitidas (serviço)' },
  { id: 'canceladas', label: 'Canceladas' },
  { id: 'recebidas', label: 'Recebidas (fornecedor)' },
]

/**
 * Workspace de Notas Fiscais (D.1.3, docs/modulos/moduloerp.md §13). Três abas:
 * NFS-e **emitidas** (exclui canceladas), **canceladas** e NF **recebidas** de
 * fornecedor. Nas emitidas o financeiro reconsulta o status na NFE.io, cancela
 * uma nota emitida e baixa PDF/XML — a emissão nasce de uma conta a receber
 * (`emitir-nfse`), então aqui é acompanhamento/pós-emissão, não lançamento.
 */
export default function NotasFiscaisPage() {
  const [aba, setAba] = useState<Aba>('emitidas')
  const [emitirOpen, setEmitirOpen] = useState(false)
  const [avisoEmissao, setAvisoEmissao] = useState<string | null>(null)

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

      <div className="flex items-start justify-between gap-3 mb-6 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#ede9fe', color: '#6d28d9' }}>
            <FileText size={20} />
          </div>
          <div>
            <h1 className="text-xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Notas Fiscais
            </h1>
            <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              NFS-e emitidas (NFE.io), canceladas e notas recebidas de fornecedores (D.1.3)
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setEmitirOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-lg font-semibold transition-opacity duration-150"
          style={{ padding: '9px 16px', background: 'var(--color-brand)', color: '#FFFFFF', fontSize: '0.875rem', fontFamily: 'var(--font-body)', border: 'none', cursor: 'pointer' }}
        >
          <Plus size={16} /> Emitir NFS-e
        </button>
      </div>

      {avisoEmissao && (
        <div className="text-sm px-4 py-3 rounded-lg mb-4"
          style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#166534', fontFamily: 'var(--font-body)' }}>
          {avisoEmissao}
        </div>
      )}

      <EmitirNfseDialog
        open={emitirOpen}
        onClose={() => setEmitirOpen(false)}
        onEmitted={msg => { setEmitirOpen(false); setAvisoEmissao(msg); setAba('emitidas') }}
      />

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

      {aba === 'recebidas'
        ? <NotasRecebidasTab />
        : <NotasServicoTab canceladas={aba === 'canceladas'} />}
    </div>
  )
}

/** Aba de NFS-e emitidas ou canceladas (mesma tabela, filtro por status invertido). */
function NotasServicoTab({ canceladas }: { canceladas: boolean }) {
  const [pageIndex, setPageIndex] = useState(0)
  const [mensagem, setMensagem] = useState<{ tom: 'ok' | 'erro'; texto: string } | null>(null)

  const filtros = useMemo(() => ({
    ...(canceladas ? { status: 'CANCELADA' as const } : { excluir_status: 'CANCELADA' as const }),
    page: pageIndex + 1,
    page_size: PAGE_SIZE,
  }), [canceladas, pageIndex])

  const { data, isLoading, isFetching } = useNotasFiscaisServico(filtros)
  const consultar = useConsultarStatusNfse()
  const cancelar = useCancelarNfse()
  const verificarDoc = useVerificarDocumentoNfse()

  const acaoOcupada = consultar.isPending || cancelar.isPending || verificarDoc.isPending

  function aoConsultar(nf: NotaFiscalServico) {
    consultar.mutate(nf.id, {
      onSuccess: r => setMensagem({ tom: 'ok', texto: r.message }),
      onError: () => setMensagem({ tom: 'erro', texto: 'Não foi possível consultar o status agora.' }),
    })
  }

  /**
   * Abre o documento verificando a NFE.io AO VIVO: no ar → abre a versão atual
   * (a CANCELADA quando cancelada); fora do ar → abre a última versão local e
   * avisa. A aba do navegador é aberta já no clique (evita bloqueio de popup) e
   * só então recebe a URL resolvida.
   */
  function aoVerDocumento(nf: NotaFiscalServico) {
    const win = window.open('', '_blank')
    verificarDoc.mutate(nf.id, {
      onSuccess: doc => {
        // A resposta traz OU o link assinado da NFE.io (externo, navega direto)
        // OU a nossa cópia local, que desde o D70 é a porta única e exige token:
        // apontar a janela para ela daria 401. Por isso a distinção pela origem.
        if (doc.url_pdf && win) {
          if (doc.url_pdf.startsWith('/')) {
            baixarArquivo(doc.url_pdf)
              .then(blob => { win.location.href = URL.createObjectURL(blob) })
              .catch(() => { win.close(); setMensagem({ tom: 'erro', texto: 'Não foi possível abrir a cópia local da nota.' }) })
          } else {
            win.location.href = doc.url_pdf
          }
        }
        else if (win) win.close()
        if (!doc.gateway_online) setMensagem({ tom: 'erro', texto: doc.mensagem })
        else if (!doc.url_pdf) setMensagem({ tom: 'erro', texto: 'Documento ainda indisponível na NFE.io.' })
      },
      onError: () => { if (win) win.close(); setMensagem({ tom: 'erro', texto: 'Não foi possível verificar o documento na NFE.io.' }) },
    })
  }

  function aoCancelar(nf: NotaFiscalServico) {
    if (!window.confirm(`Cancelar a NFS-e ${nf.numero ? `nº ${nf.numero}` : `#${nf.id}`} na NFE.io? A ação não pode ser desfeita.`)) return
    cancelar.mutate(nf.id, {
      onSuccess: r => setMensagem({ tom: 'ok', texto: r.message }),
      onError: () => setMensagem({ tom: 'erro', texto: 'Não foi possível cancelar a nota agora.' }),
    })
  }

  const columns = useMemo<ColumnDef<NotaFiscalServico>[]>(() => [
    {
      accessorKey: 'numero',
      header: 'Número',
      enableSorting: false,
      cell: ({ row }) => (
        <div className="flex flex-col">
          <span className="font-medium">{row.original.numero ? `nº ${row.original.numero}` : `#${row.original.id}`}</span>
          {row.original.nfe_io_id && (
            <span className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>{row.original.nfe_io_id}</span>
          )}
        </div>
      ),
    },
    {
      id: 'tomador',
      header: 'Tomador',
      enableSorting: false,
      cell: ({ row }) => {
        const b = row.original.borrower_data ?? {}
        const nome = b.nome_completo || b.razao_social
        return nome ? <span>{nome}</span> : <span style={{ color: 'var(--color-text-muted)' }}>—</span>
      },
    },
    {
      accessorKey: 'services_amount',
      header: 'Valor',
      enableSorting: false,
      cell: ({ getValue }) => <MoneyDisplay cents={apiDecimalToCents(getValue<string>())} />,
    },
    {
      accessorKey: 'data_emissao',
      header: 'Emissão',
      enableSorting: false,
      cell: ({ getValue }) => {
        const v = getValue<string | null>()
        return v ? dateToBR(v) : <span style={{ color: 'var(--color-text-muted)' }}>—</span>
      },
    },
    {
      accessorKey: 'status',
      header: 'Status',
      enableSorting: false,
      cell: ({ row }) => {
        const nf = row.original
        // "Erro" vira botão → popup com todos os códigos/mensagens da NFE.io.
        return nf.status === 'ERRO'
          ? <BotaoErroGateway dados={nf.dados_retorno_api} titulo="Erro na emissão da NFS-e (NFE.io)" />
          : <StatusNfeBadge status={nf.status} />
      },
    },
    {
      id: 'arquivos',
      header: 'Arquivos',
      enableSorting: false,
      cell: ({ row }) => (
        <ArquivosCell pdf={row.original.arquivo_pdf} xml={row.original.arquivo_xml}
                      nome={row.original.numero} />
      ),
    },
    {
      id: 'acoes',
      header: 'Ações',
      enableSorting: false,
      cell: ({ row }) => {
        const nf = row.original
        return (
          <div className="flex items-center gap-1.5">
            <AcaoButton
              titulo="Abrir documento (verifica na NFE.io)"
              onClick={() => aoVerDocumento(nf)}
              disabled={acaoOcupada || !nf.nfe_io_id}
              icon={<FileSearch size={14} />}
            />
            <AcaoButton
              titulo="Reconsultar status na NFE.io"
              onClick={() => aoConsultar(nf)}
              disabled={acaoOcupada || !nf.nfe_io_id}
              icon={<RefreshCw size={14} />}
            />
            <AcaoButton
              titulo="Cancelar NFS-e"
              onClick={() => aoCancelar(nf)}
              disabled={acaoOcupada || nf.status !== 'EMITIDA'}
              icon={<Ban size={14} />}
              perigo
            />
          </div>
        )
      },
    },
  ], [acaoOcupada])

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

      <FinanceDataTable
        data={data?.results ?? []}
        columns={columns}
        count={data?.count ?? 0}
        pageIndex={pageIndex}
        pageSize={PAGE_SIZE}
        onPageChange={setPageIndex}
        sorting={[]}
        onSortingChange={() => {}}
        getRowId={row => String(row.id)}
        isLoading={isLoading}
        isFetching={isFetching}
        emptyMessage={canceladas
          ? 'Nenhuma NFS-e cancelada.'
          : 'Nenhuma NFS-e emitida. Emita uma a partir de uma conta a receber.'}
      />
    </>
  )
}

/** Aba de NF recebidas de fornecedor (upload/lançamento de entrada — só leitura + download). */
function NotasRecebidasTab() {
  const [pageIndex, setPageIndex] = useState(0)
  const filtros = useMemo(() => ({ page: pageIndex + 1, page_size: PAGE_SIZE }), [pageIndex])
  const { data, isLoading, isFetching } = useNotasFiscaisRecebidas(filtros)

  const columns = useMemo<ColumnDef<NotaFiscalRecebida>[]>(() => [
    {
      accessorKey: 'numero_nota',
      header: 'Número',
      enableSorting: false,
      cell: ({ getValue }) => <span className="font-medium">{getValue<string>()}</span>,
    },
    {
      accessorKey: 'chave_acesso',
      header: 'Chave de acesso',
      enableSorting: false,
      cell: ({ getValue }) => {
        const v = getValue<string>()
        return v ? <span className="font-mono text-xs">{v}</span> : <span style={{ color: 'var(--color-text-muted)' }}>—</span>
      },
    },
    {
      accessorKey: 'valor_total',
      header: 'Valor',
      enableSorting: false,
      cell: ({ getValue }) => <MoneyDisplay cents={apiDecimalToCents(getValue<string>())} />,
    },
    {
      accessorKey: 'data_emissao',
      header: 'Emissão',
      enableSorting: false,
      cell: ({ getValue }) => {
        const v = getValue<string | null>()
        return v ? dateToBR(v) : <span style={{ color: 'var(--color-text-muted)' }}>—</span>
      },
    },
    {
      id: 'arquivos',
      header: 'Arquivos',
      enableSorting: false,
      cell: ({ row }) => (
        <ArquivosCell pdf={row.original.arquivo_pdf} xml={row.original.arquivo_xml}
                      nome={row.original.numero_nota} />
      ),
    },
  ], [])

  return (
    <FinanceDataTable
      data={data?.results ?? []}
      columns={columns}
      count={data?.count ?? 0}
      pageIndex={pageIndex}
      pageSize={PAGE_SIZE}
      onPageChange={setPageIndex}
      sorting={[]}
      onSortingChange={() => {}}
      getRowId={row => String(row.nota_fiscal_id)}
      isLoading={isLoading}
      isFetching={isFetching}
      emptyMessage="Nenhuma nota fiscal recebida lançada."
    />
  )
}

/** Links de download de PDF/XML — só aparecem quando o arquivo existe na NF. */
/**
 * PDF e XML da nota.
 *
 * **D70:** os dois deixaram de ser caminhos de `/media/` e passaram a ser a URL
 * da porta única, que exige token — `<a href>` chegaria sem `Authorization`.
 * Baixar por XHR também dá o nome certo ao arquivo salvo: a URL gateada termina
 * em `/nfse_pdf/12/`, e sem `download` o browser salvaria "12".
 */
function ArquivosCell({ pdf, xml, nome }: { pdf: string | null; xml: string | null; nome?: string | null }) {
  if (!pdf && !xml) return <span style={{ color: 'var(--color-text-muted)' }}>—</span>
  const base = nome ? `nota-${nome}` : 'nota-fiscal'
  return (
    <div className="flex items-center gap-2">
      {pdf && (
        <button type="button" onClick={() => baixarParaDisco(pdf, `${base}.pdf`)}
          className="inline-flex items-center gap-1 text-xs font-semibold"
          style={{ color: '#b91c1c', textDecoration: 'none', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
          <FileDown size={14} /> PDF
        </button>
      )}
      {xml && (
        <button type="button" onClick={() => baixarParaDisco(xml, `${base}.xml`)}
          className="inline-flex items-center gap-1 text-xs font-semibold"
          style={{ color: '#0369a1', textDecoration: 'none', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
          <FileCode2 size={14} /> XML
        </button>
      )}
    </div>
  )
}

function AcaoButton({ titulo, onClick, disabled, icon, perigo }: {
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
