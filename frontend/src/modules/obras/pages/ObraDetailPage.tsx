import React, { useState, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  Pencil, Trash2, ChevronRight, HardHat, Loader2,
  ListChecks, FileText, Plus,
} from 'lucide-react'
import { useObra, updateObra, deleteObra, createEtapa, updateEtapa, deleteEtapa } from '../hooks/useObra'
import ObraStatusBadge from '../components/ObraStatusBadge'
import ObraForm from '../components/ObraForm'
import EtapaForm from '../components/EtapaForm'
import { baixarParaDisco } from '@/lib/arquivo'
import { AvisoDaLixeira } from '@/components/AvisoDaLixeira'
import type { ObraFormData, EtapaObra, EtapaObraFormData } from '@/types'

// ─── Utilitários ─────────────────────────────────────────────────────────────

function formatCurrency(value: string | null) {
  if (!value || value === '0' || value === '0.00') return '—'
  return parseFloat(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}
function formatDate(value: string | null) {
  if (!value) return '—'
  const [y, m, d] = value.split('-')
  return `${d}/${m}/${y}`
}

const TIPO_DOC_LABEL: Record<string, string> = {
  projeto: 'Projeto', relatorio: 'Relatório', memorial_descritivo: 'Memorial Desc.',
  alvara: 'Alvará', contrato: 'Contrato', licenca: 'Licença',
  viabilidade: 'Viabilidade', outros: 'Outros',
}
const STATUS_DOC_CONFIG: Record<string, { label: string; bg: string; color: string }> = {
  rascunho:    { label: 'Rascunho',       bg: '#f3f4f6', color: '#374151' },
  em_revisao:  { label: 'Em Revisão',     bg: '#e0f2fe', color: '#0369a1' },
  aprovacao:   { label: 'Em Aprovação',   bg: '#fef9c3', color: '#854d0e' },
  correcoes:   { label: 'Correções',      bg: '#ffedd5', color: '#9a3412' },
  aprovado:    { label: 'Aprovado',       bg: '#dcfce7', color: '#166534' },
  rejeitado:   { label: 'Rejeitado',      bg: '#fee2e2', color: '#991b1b' },
  publicado:   { label: 'Publicado',      bg: '#ede9fe', color: '#6d28d9' },
  cancelado:   { label: 'Cancelado',      bg: '#f3f4f6', color: '#6b7280' },
}

// ─── Barra de progresso inline ────────────────────────────────────────────────

const ProgressBar: React.FC<{ value: number }> = ({ value }) => (
  <div className="flex items-center gap-3">
    <div className="flex-1 rounded-full overflow-hidden" style={{ background: '#f1f5f9', height: '6px' }}>
      <div style={{
        width: `${Math.min(100, Math.max(0, value))}%`,
        height: '100%',
        borderRadius: '9999px',
        background: value >= 100 ? '#166534' : value >= 50 ? 'var(--color-brand)' : '#f59e0b',
        transition: 'width 0.3s ease',
      }} />
    </div>
    <span className="text-xs font-semibold tabular-nums"
          style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', minWidth: '30px' }}>
      {Math.round(value)}%
    </span>
  </div>
)

// ─── Tipos de aba ─────────────────────────────────────────────────────────────

type Tab = 'visao' | 'etapas' | 'documentos'
const TABS: { key: Tab; label: string; icon: React.ReactNode }[] = [
  { key: 'visao',      label: 'Visão Geral', icon: <HardHat size={15} /> },
  { key: 'etapas',    label: 'Etapas',       icon: <ListChecks size={15} /> },
  { key: 'documentos',label: 'Documentos',   icon: <FileText size={15} /> },
]

// ─── Página principal ─────────────────────────────────────────────────────────

const ObraDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const numId = id ? parseInt(id, 10) : null

  const { data, etapas, documentos, loading, error, refetch } = useObra(numId)

  const [activeTab, setActiveTab]       = useState<Tab>('visao')
  const [editOpen, setEditOpen]         = useState(false)
  const [deleteModal, setDeleteModal]   = useState(false)
  const [deleting, setDeleting]         = useState(false)

  // Etapa form state
  const [etapaFormOpen, setEtapaFormOpen]     = useState(false)
  const [editingEtapa, setEditingEtapa]       = useState<EtapaObra | null>(null)
  const [deletingEtapaId, setDeletingEtapaId] = useState<number | null>(null)
  const [etapaDelModal, setEtapaDelModal]     = useState(false)

  const nextOrdem = useMemo(
    () => etapas.length > 0 ? Math.max(...etapas.map(e => e.ordem)) + 1 : 1,
    [etapas]
  )
  const progressGeral = useMemo(() => {
    if (etapas.length === 0) return null
    return etapas.reduce((acc, e) => acc + parseFloat(e.percentual_conclusao || '0'), 0) / etapas.length
  }, [etapas])

  // ── Handlers obra ────────────────────────────────────────────────────────────

  const handleUpdate = async (formData: ObraFormData) => {
    if (!numId) return
    await updateObra(numId, formData)
    refetch()
  }

  const handleDelete = async () => {
    if (!numId) return
    setDeleting(true)
    try {
      await deleteObra(numId)
      navigate('/app/obras', { replace: true })
    } catch {
      setDeleting(false)
      setDeleteModal(false)
    }
  }

  // ── Handlers etapa ───────────────────────────────────────────────────────────

  const handleSaveEtapa = async (formData: EtapaObraFormData) => {
    if (editingEtapa) {
      await updateEtapa(editingEtapa.etapa_id, formData)
    } else {
      await createEtapa(formData)
    }
    refetch()
  }

  const openDeleteEtapa = (etapaId: number) => {
    setDeletingEtapaId(etapaId)
    setEtapaDelModal(true)
  }

  const handleDeleteEtapa = async () => {
    if (!deletingEtapaId) return
    try {
      await deleteEtapa(deletingEtapaId)
      setEtapaDelModal(false)
      setDeletingEtapaId(null)
      refetch()
    } catch {
      setEtapaDelModal(false)
    }
  }

  // ── Loading / erro ───────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
             style={{ borderColor: 'var(--color-brand)', borderTopColor: 'transparent' }} />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="px-6 py-8">
        <div className="text-sm px-4 py-3 rounded-lg"
             style={{ background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030', fontFamily: 'var(--font-body)' }}>
          {error ?? 'Obra não encontrada.'}
        </div>
      </div>
    )
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="px-6 py-8 max-w-5xl">

      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-xs mb-6"
           style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
        <Link to="/app/obras" className="hover:underline" style={{ color: 'var(--color-brand)' }}>
          Obras
        </Link>
        <ChevronRight size={12} />
        <span>{data.nome_obra}</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-8">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
               style={{ background: '#fef3c7', color: 'var(--color-brand)' }}>
            <HardHat size={24} />
          </div>
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-2xl font-bold"
                  style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
                {data.nome_obra}
              </h1>
              <ObraStatusBadge status={data.status_obra} />
            </div>
            <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {data.endereco || 'Sem endereço'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setEditOpen(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold"
            style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF', color: 'var(--color-brand)', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
          >
            <Pencil size={14} /> Editar
          </button>
          <button
            onClick={() => setDeleteModal(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold"
            style={{ border: '1.5px solid #fed7d7', background: '#fff5f5', color: '#c53030', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {[
          { label: 'Orçamento Previsto', value: formatCurrency(data.orcamento_previsto) },
          {
            label: 'Progresso Geral',
            value: progressGeral !== null ? `${Math.round(progressGeral)}%` : '—',
            sub: etapas.length > 0 ? `${etapas.length} etapa${etapas.length !== 1 ? 's' : ''}` : 'Sem etapas',
          },
          { label: 'Início Previsto',   value: formatDate(data.data_inicio_prevista) },
          { label: 'Fim Previsto',      value: formatDate(data.data_fim_prevista) },
        ].map(kpi => (
          <div key={kpi.label} className="rounded-xl p-4" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)' }}>
            <p className="text-xs font-semibold uppercase tracking-wide mb-1"
               style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {kpi.label}
            </p>
            <p className="text-lg font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              {kpi.value}
            </p>
            {'sub' in kpi && kpi.sub && (
              <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                {kpi.sub}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Barra de progresso geral */}
      {progressGeral !== null && (
        <div className="mb-8 px-4 py-3 rounded-xl" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)' }}>
          <p className="text-xs font-semibold uppercase tracking-wide mb-2"
             style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
            Progresso geral
          </p>
          <ProgressBar value={progressGeral} />
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-6 p-1 rounded-xl w-fit" style={{ background: '#f1f5f9' }}>
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold transition-all duration-150"
            style={{
              fontFamily: 'var(--font-body)', border: 'none', cursor: 'pointer',
              background: activeTab === t.key ? '#FFFFFF' : 'transparent',
              color: activeTab === t.key ? 'var(--color-brand)' : 'var(--color-text-muted)',
              boxShadow: activeTab === t.key ? 'var(--shadow-sm)' : 'none',
            }}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="rounded-xl p-6" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)' }}>

        {/* ── Visão Geral ── */}
        {activeTab === 'visao' && (
          <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
            {[
              { label: 'Endereço',     value: data.endereco || '—' },
              { label: 'Início real',  value: formatDate(data.data_inicio_real) },
              { label: 'Fim real',     value: formatDate(data.data_fim_real) },
              { label: 'Cadastro',     value: new Date(data.data_cadastro).toLocaleDateString('pt-BR') },
              { label: 'Atualização',  value: new Date(data.data_atualizacao).toLocaleDateString('pt-BR') },
            ].map(item => (
              <div key={item.label}>
                <dt className="text-xs font-semibold uppercase tracking-wide mb-0.5"
                    style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                  {item.label}
                </dt>
                <dd className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}>
                  {item.value}
                </dd>
              </div>
            ))}
            {data.descricao && (
              <div className="md:col-span-2">
                <dt className="text-xs font-semibold uppercase tracking-wide mb-0.5"
                    style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                  Descrição
                </dt>
                <dd className="text-sm leading-relaxed" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}>
                  {data.descricao}
                </dd>
              </div>
            )}
          </dl>
        )}

        {/* ── Etapas ── */}
        {activeTab === 'etapas' && (
          <div>
            <div className="flex items-center justify-between mb-5">
              <p className="text-sm font-semibold"
                 style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                {etapas.length} etapa{etapas.length !== 1 ? 's' : ''}
              </p>
              <button
                onClick={() => { setEditingEtapa(null); setEtapaFormOpen(true) }}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold"
                style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
                onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand-dark)')}
                onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand)')}
              >
                <Plus size={14} /> Nova Etapa
              </button>
            </div>

            {etapas.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 gap-3">
                <ListChecks size={36} style={{ color: '#cbd5e1' }} />
                <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                  Nenhuma etapa cadastrada. Adicione etapas para acompanhar o cronograma.
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {etapas.map(etapa => (
                  <div
                    key={etapa.etapa_id}
                    className="rounded-xl p-4"
                    style={{ border: '1px solid #e2e8f0', background: '#f8fafc' }}
                  >
                    <div className="flex items-start justify-between gap-4 mb-3">
                      <div className="flex items-center gap-3">
                        {/* Badge de ordem */}
                        <span className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                              style={{ background: 'var(--color-brand)', color: '#FFFFFF', fontFamily: 'var(--font-body)' }}>
                          {etapa.ordem}
                        </span>
                        <div>
                          <p className="text-sm font-semibold"
                             style={{ fontFamily: 'var(--font-body)', color: 'var(--color-brand)' }}>
                            {etapa.nome_etapa}
                          </p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <ObraStatusBadge status={etapa.status_etapa} />
                            {(etapa.data_inicio_prevista || etapa.data_fim_prevista) && (
                              <span className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                                {formatDate(etapa.data_inicio_prevista)} → {formatDate(etapa.data_fim_prevista)}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={() => { setEditingEtapa(etapa); setEtapaFormOpen(true) }}
                          className="p-1.5 rounded-lg"
                          title="Editar etapa"
                          style={{ background: '#FFFFFF', border: '1px solid #e2e8f0', cursor: 'pointer', color: 'var(--color-brand)' }}
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={() => openDeleteEtapa(etapa.etapa_id)}
                          className="p-1.5 rounded-lg"
                          title="Excluir etapa"
                          style={{ background: '#fff5f5', border: '1px solid #fed7d7', cursor: 'pointer', color: '#c53030' }}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                    <ProgressBar value={parseFloat(etapa.percentual_conclusao || '0')} />
                    {etapa.descricao && (
                      <p className="text-xs mt-2 leading-relaxed"
                         style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                        {etapa.descricao}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Documentos ── */}
        {activeTab === 'documentos' && (
          <div>
            {documentos.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 gap-3">
                <FileText size={36} style={{ color: '#cbd5e1' }} />
                <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                  Nenhum documento cadastrado para esta obra.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full" style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-body)' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                      {['Nome', 'Tipo', 'Versão', 'Status', 'Data Emissão', ''].map(h => (
                        <th key={h} className="text-left text-xs font-semibold uppercase tracking-wide px-4 py-3"
                            style={{ color: 'var(--color-text-muted)' }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {documentos.map((doc, i) => {
                      const statusCfg = STATUS_DOC_CONFIG[doc.status_documento] ?? { label: doc.status_documento, bg: '#f3f4f6', color: '#374151' }
                      return (
                        <tr key={doc.documento_id}
                            style={{ borderBottom: i < documentos.length - 1 ? '1px solid #f1f5f9' : 'none' }}>
                          <td className="px-4 py-3">
                            <span className="text-sm font-semibold" style={{ color: 'var(--color-brand)' }}>
                              {doc.nome_documento}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
                                  style={{ background: '#f1f5f9', color: 'var(--color-text)' }}>
                              {TIPO_DOC_LABEL[doc.tipo_documento] ?? doc.tipo_documento}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm" style={{ color: 'var(--color-text-muted)' }}>
                            {doc.versao || '—'}
                          </td>
                          <td className="px-4 py-3">
                            <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
                                  style={{ background: statusCfg.bg, color: statusCfg.color }}>
                              {statusCfg.label}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm" style={{ color: 'var(--color-text-muted)' }}>
                            {formatDate(doc.data_emissao)}
                          </td>
                          <td className="px-4 py-3">
                            {/* D70 — o documento da obra saiu de `/media/`; baixar
                                é XHR autenticado, e o nome vem do que a tela sabe. */}
                            {doc.arquivo && (
                              <button onClick={() => baixarParaDisco(doc.arquivo, doc.nome_documento)}
                                 className="text-xs font-semibold"
                                 style={{ color: 'var(--color-brand)', textDecoration: 'none',
                                   background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                                Download
                              </button>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

      </div>

      {/* ── Sheet de editar obra ── */}
      <ObraForm
        open={editOpen}
        onClose={() => setEditOpen(false)}
        onSave={handleUpdate}
        initial={data}
      />

      {/* ── Sheet de etapa ── */}
      {numId && (
        <EtapaForm
          open={etapaFormOpen}
          obraId={numId}
          nextOrdem={nextOrdem}
          onClose={() => { setEtapaFormOpen(false); setEditingEtapa(null) }}
          onSave={handleSaveEtapa}
          initial={editingEtapa}
        />
      )}

      {/* ── Modal excluir obra ── */}
      {deleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
             style={{ background: 'rgba(0,0,0,0.5)' }}>
          <div className="w-full max-w-md rounded-2xl p-6 flex flex-col gap-5"
               style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-lg)' }}>
            <div className="flex items-start gap-4">
              <div className="w-11 h-11 rounded-full flex items-center justify-center shrink-0"
                   style={{ background: '#fee2e2' }}>
                <Trash2 size={20} style={{ color: '#c53030' }} />
              </div>
              <div>
                <h3 className="text-base font-bold mb-1"
                    style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
                  Excluir obra?
                </h3>
                <p className="text-sm leading-relaxed"
                   style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}>
                  A obra <strong>"{data.nome_obra}"</strong> sai das listagens.{' '}
                  <AvisoDaLixeira oQue="Ela" />
                </p>
              </div>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setDeleteModal(false)} disabled={deleting}
                className="flex-1 py-2.5 rounded-lg text-sm font-semibold"
                style={{ border: '1.5px solid #e2e8f0', background: 'transparent', color: 'var(--color-text-muted)', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
                Cancelar
              </button>
              <button onClick={handleDelete} disabled={deleting}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold"
                style={{ background: deleting ? '#fca5a5' : '#dc2626', border: 'none', color: '#FFFFFF', cursor: deleting ? 'not-allowed' : 'pointer', fontFamily: 'var(--font-body)' }}>
                {deleting ? <><Loader2 size={14} className="animate-spin" />Excluindo…</> : <><Trash2 size={14} />Excluir</>}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal excluir etapa ── */}
      {etapaDelModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4"
             style={{ background: 'rgba(0,0,0,0.5)' }}>
          <div className="w-full max-w-sm rounded-2xl p-6 flex flex-col gap-5"
               style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-lg)' }}>
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-full flex items-center justify-center shrink-0"
                   style={{ background: '#fee2e2' }}>
                <Trash2 size={18} style={{ color: '#c53030' }} />
              </div>
              <div>
                <h3 className="text-sm font-bold mb-1"
                    style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
                  Excluir etapa?
                </h3>
                <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}>
                  <AvisoDaLixeira oQue="A etapa" />
                </p>
              </div>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setEtapaDelModal(false)}
                className="flex-1 py-2 rounded-lg text-sm font-semibold"
                style={{ border: '1.5px solid #e2e8f0', background: 'transparent', color: 'var(--color-text-muted)', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
                Cancelar
              </button>
              <button onClick={handleDeleteEtapa}
                className="flex-1 py-2 rounded-lg text-sm font-semibold"
                style={{ background: '#dc2626', border: 'none', color: '#FFFFFF', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
                Excluir
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}

export default ObraDetailPage
