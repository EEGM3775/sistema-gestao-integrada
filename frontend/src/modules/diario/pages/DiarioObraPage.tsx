import React, { useState, useMemo } from 'react'
import {
  Brain, Plus, Search, RefreshCw, CalendarDays, CloudSun,
  AlertTriangle, NotebookPen, Images, Trash2, MessageSquare, Smartphone, Globe,
} from 'lucide-react'
import { useObras } from '@/modules/obras/hooks/useObras'
import { useDiarios } from '../hooks/useDiarios'
import { contribuir, deleteEntrada, deleteDocumento } from '../hooks/useDiario'
import { useAnalisesIA } from '../hooks/useAnalisesIA'
import DiarioForm from '../components/DiarioForm'
import AnaliseModal from '../components/AnaliseModal'
import AnaliseStatusBadge from '../components/AnaliseStatusBadge'
import ImagemDoArquivo from '@/components/ImagemDoArquivo'
import type { ContribuirData, DocumentoDiario, EntradaDiario, DiarioObra } from '@/types'

function formatDate(value: string | null) {
  if (!value) return '—'
  const [y, m, d] = value.split('-')
  if (!d) return value
  return `${d}/${m}/${y}`
}
function formatTime(value: string) {
  return new Date(value).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}
function isImage(name: string) {
  return /\.(jpe?g|png|gif|bmp|webp)$/i.test(name)
}

type Tab = 'registros' | 'galeria'
const TABS: { key: Tab; label: string; icon: React.ReactNode }[] = [
  { key: 'registros', label: 'Registros', icon: <NotebookPen size={15} /> },
  { key: 'galeria',   label: 'Galeria IA', icon: <Images size={15} /> },
]

interface SelectedDoc { id: number; image: string | null }

const OrigemIcon: React.FC<{ origem: string }> = ({ origem }) => (
  origem === 'whatsapp'
    ? <Smartphone size={11} style={{ color: '#16a34a' }} />
    : <Globe size={11} style={{ color: '#64748b' }} />
)

const Thumb: React.FC<{ doc: DocumentoDiario; canModerate: boolean; onOpen: () => void; onDelete: () => void }> =
({ doc, canModerate, onOpen, onDelete }) => {
  // D70 — `doc.arquivo` deixou de ser um caminho de `/media/` e virou a URL da
  // porta única, que exige token. A miniatura é baixada por XHR e vira object
  // URL; e como a URL gateada não carrega mais o nome do arquivo, quem responde
  // "isto é imagem?" passou a ser `arquivo_nome`, publicado à parte pela API.
  const src = isImage(doc.arquivo_nome) ? doc.arquivo : null
  return (
    <div className="relative group">
      <button
        onClick={onOpen}
        className="relative w-16 h-16 rounded-lg overflow-hidden shrink-0 block"
        style={{ border: '1px solid #e2e8f0', background: '#f1f5f9', cursor: 'pointer' }}
        title={doc.autor_nome ? `Foto de ${doc.autor_nome}` : 'Ver análise de IA'}
      >
        <ImagemDoArquivo url={src} alt={doc.descricao ?? ''} tamanhoDoVazio={18} />
        {doc.analise_ia && (
          <span className="absolute bottom-0 inset-x-0 text-center text-[9px] py-0.5"
                style={{ background: 'rgba(15,31,61,0.8)', color: '#fff' }}>
            IA
          </span>
        )}
      </button>
      {canModerate && (
        <button
          onClick={onDelete}
          className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full items-center justify-center hidden group-hover:flex"
          style={{ background: '#ef4444', color: '#fff', border: 'none', cursor: 'pointer' }}
          title="Excluir foto"
        >
          <Trash2 size={11} />
        </button>
      )}
    </div>
  )
}

const EntradaRow: React.FC<{ entrada: EntradaDiario; canModerate: boolean; onDelete: () => void }> =
({ entrada, canModerate, onDelete }) => (
  <div className="flex items-start gap-2 py-2 group"
       style={{ borderTop: '1px solid #f1f5f9' }}>
    <div className="mt-0.5">
      {entrada.eh_ocorrencia
        ? <AlertTriangle size={14} style={{ color: '#9a3412' }} />
        : <MessageSquare size={14} style={{ color: '#94a3b8' }} />}
    </div>
    <div className="flex-1 min-w-0">
      <p className="text-sm whitespace-pre-wrap leading-relaxed"
         style={{ color: entrada.eh_ocorrencia ? '#9a3412' : 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
        {entrada.texto}
      </p>
      <div className="flex items-center gap-1.5 mt-0.5 text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
        <OrigemIcon origem={entrada.origem} />
        <span>{entrada.autor_nome ?? '—'}</span>
        <span>·</span>
        <span>{formatTime(entrada.data_criacao)}</span>
      </div>
    </div>
    {canModerate && (
      <button onClick={onDelete}
        className="opacity-0 group-hover:opacity-100 p-1 rounded"
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444' }}
        title="Excluir entrada">
        <Trash2 size={14} />
      </button>
    )}
  </div>
)

const DiaCard: React.FC<{
  diario: DiarioObra
  showObra: boolean
  onOpenDoc: (d: SelectedDoc) => void
  onChanged: () => void
}> = ({ diario, showObra, onOpenDoc, onChanged }) => {
  const canModerate = diario.pode_moderar
  const docs = diario.documentos ?? []
  const entradas = diario.entradas ?? []

  const handleDeleteEntrada = async (id: number) => {
    if (!window.confirm('Excluir esta entrada do diário?')) return
    try { await deleteEntrada(id); onChanged() } catch { /* noop */ }
  }
  const handleDeleteDoc = async (id: number) => {
    if (!window.confirm('Excluir esta foto do diário?')) return
    try { await deleteDocumento(id); onChanged() } catch { /* noop */ }
  }

  return (
    <div className="rounded-xl p-5"
         style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <CalendarDays size={16} style={{ color: 'var(--color-brand)' }} />
          <span className="text-sm font-bold" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-heading)' }}>
            {formatDate(diario.data)}
          </span>
          {showObra && (
            <span className="text-xs px-2 py-0.5 rounded-full"
                  style={{ background: '#f1f5f9', color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              {diario.obra_nome ?? `Obra #${diario.obra}`}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
          {diario.condicoes_climaticas && (
            <span className="flex items-center gap-1"><CloudSun size={14} /> {diario.condicoes_climaticas}</span>
          )}
          <span>{entradas.length} entrada{entradas.length !== 1 ? 's' : ''} · {docs.length} foto{docs.length !== 1 ? 's' : ''}</span>
        </div>
      </div>

      {entradas.length > 0 && (
        <div className="mb-2">
          {entradas.map(e => (
            <EntradaRow key={e.entrada_id} entrada={e} canModerate={canModerate}
                        onDelete={() => handleDeleteEntrada(e.entrada_id)} />
          ))}
        </div>
      )}

      {docs.length > 0 && (
        <div className="flex flex-wrap gap-2 pt-3" style={{ borderTop: '1px solid #f1f5f9' }}>
          {docs.map(doc => (
            <Thumb key={doc.documento_diario_id} doc={doc} canModerate={canModerate}
                   onOpen={() => onOpenDoc({ id: doc.documento_diario_id, image: doc.arquivo })}
                   onDelete={() => handleDeleteDoc(doc.documento_diario_id)} />
          ))}
        </div>
      )}

      {entradas.length === 0 && docs.length === 0 && (
        <p className="text-sm" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
          Diário aberto, sem conteúdo ainda.
        </p>
      )}
    </div>
  )
}

const DiarioObraPage: React.FC = () => {
  const [obraId, setObraId]     = useState<number | null>(null)
  const [search, setSearch]     = useState('')
  const [tab, setTab]           = useState<Tab>('registros')
  const [formOpen, setFormOpen] = useState(false)
  const [selected, setSelected] = useState<SelectedDoc | null>(null)

  const { data: obras } = useObras()
  const { data: diarios, loading, error, refetch } = useDiarios({ obraId, search })
  const {
    data: analises, total, loading: loadingIA, error: errorIA, refetch: refetchIA,
  } = useAnalisesIA({ obraId })

  const refreshAll = () => { refetch(); refetchIA() }

  const handleContribuir = async (data: ContribuirData) => {
    await contribuir(data)
    refreshAll()
  }

  const totalEntradas = useMemo(
    () => diarios.reduce((acc, d) => acc + (d.entradas?.length ?? 0), 0),
    [diarios]
  )

  return (
    <div className="px-6 py-8">

      {/* Cabeçalho */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
               style={{ background: '#e0f2fe', color: 'var(--color-brand)' }}>
            <Brain size={22} />
          </div>
          <div>
            <h1 className="text-xl font-bold"
                style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Diário de Obra & IA
            </h1>
            <p className="text-xs"
               style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {tab === 'registros'
                ? (loading ? 'Carregando…' : `${diarios.length} dia${diarios.length !== 1 ? 's' : ''} · ${totalEntradas} entrada${totalEntradas !== 1 ? 's' : ''}`)
                : (loadingIA ? 'Carregando…' : `${total} imagem${total !== 1 ? 'ns' : ''} analisada${total !== 1 ? 's' : ''}`)}
            </p>
          </div>
        </div>
        <button
          onClick={() => setFormOpen(true)}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold"
          style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
          onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand-dark)')}
          onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand)')}
        >
          <Plus size={16} /> Novo registro
        </button>
      </div>

      {/* Filtros */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        {tab === 'registros' && (
          <div className="relative flex-1">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2"
                    style={{ color: 'var(--color-text-muted)' }} />
            <input
              type="text"
              placeholder="Buscar no conteúdo dos registros…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm outline-none"
              style={{ border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)', color: 'var(--color-text)', background: '#FFFFFF' }}
              onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
              onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
            />
          </div>
        )}
        <select
          value={obraId ?? ''}
          onChange={e => setObraId(e.target.value ? parseInt(e.target.value, 10) : null)}
          className="px-4 py-2.5 rounded-lg text-sm outline-none"
          style={{ border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)', color: 'var(--color-text)', background: '#FFFFFF', cursor: 'pointer', minWidth: '220px', flex: tab === 'galeria' ? 1 : undefined }}
        >
          <option value="">Todas as obras</option>
          {obras.map(o => (
            <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>
          ))}
        </select>
        <button
          onClick={refreshAll}
          className="p-2.5 rounded-lg border"
          title="Atualizar"
          style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF', cursor: 'pointer', color: 'var(--color-text-muted)' }}
          onMouseEnter={e => ((e.currentTarget as HTMLElement).style.borderColor = 'var(--color-brand)')}
          onMouseLeave={e => ((e.currentTarget as HTMLElement).style.borderColor = '#e2e8f0')}
        >
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Abas */}
      <div className="flex gap-1 mb-6" style={{ borderBottom: '1px solid #e2e8f0' }}>
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className="flex items-center gap-2 px-4 py-2.5 text-sm font-semibold"
            style={{
              background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)',
              color: tab === t.key ? 'var(--color-brand)' : 'var(--color-text-muted)',
              borderBottom: tab === t.key ? '2px solid var(--color-brand)' : '2px solid transparent',
              marginBottom: '-1px',
            }}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* ── Aba Registros ── */}
      {tab === 'registros' && (
        <>
          {error && (
            <div className="text-sm px-4 py-3 rounded-lg mb-4"
                 style={{ background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030', fontFamily: 'var(--font-body)' }}>
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
                   style={{ borderColor: 'var(--color-brand)', borderTopColor: 'transparent' }} />
            </div>
          ) : diarios.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 rounded-xl"
                 style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
              <NotebookPen size={40} style={{ color: '#cbd5e1' }} />
              <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                {search || obraId ? 'Nenhum registro para os filtros aplicados.' : 'Nenhum diário registrado ainda.'}
              </p>
              {!search && !obraId && (
                <button onClick={() => setFormOpen(true)} className="text-sm font-semibold"
                        style={{ color: 'var(--color-brand)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
                  + Fazer o primeiro registro
                </button>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {diarios.map(d => (
                <DiaCard key={d.diario_obra_id} diario={d} showObra={!obraId}
                         onOpenDoc={setSelected} onChanged={refreshAll} />
              ))}
            </div>
          )}
        </>
      )}

      {/* ── Aba Galeria IA ── */}
      {tab === 'galeria' && (
        <>
          {errorIA && (
            <div className="text-sm px-4 py-3 rounded-lg mb-4"
                 style={{ background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030', fontFamily: 'var(--font-body)' }}>
              {errorIA}
            </div>
          )}

          {loadingIA ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
                   style={{ borderColor: 'var(--color-brand)', borderTopColor: 'transparent' }} />
            </div>
          ) : analises.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 rounded-xl"
                 style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
              <Images size={40} style={{ color: '#cbd5e1' }} />
              <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                {obraId ? 'Nenhuma imagem analisada para esta obra.' : 'Nenhuma imagem com análise de IA ainda.'}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
              {analises.map(a => (
                <button
                  key={a.id}
                  onClick={() => setSelected({ id: a.id, image: a.url_imagem })}
                  className="flex flex-col rounded-xl overflow-hidden text-left"
                  style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0', cursor: 'pointer' }}
                >
                  <div className="w-full h-32 flex items-center justify-center" style={{ background: '#0f1f3d' }}>
                    {/* D70 — `url_imagem` também virou URL gateada (a galeria é
                        payload montado à mão nas views do diário). */}
                    <ImagemDoArquivo url={a.url_imagem} alt={a.nome}
                                     corDoVazio="rgba(255,255,255,0.4)" tamanhoDoVazio={28} />
                  </div>
                  <div className="p-3 flex flex-col gap-2">
                    <span className="text-xs font-semibold truncate" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                      {a.nome_original || a.nome}
                    </span>
                    <span className="text-xs truncate" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                      {a.obra_nome ?? '—'}{a.autor_nome ? ` · ${a.autor_nome}` : ''}
                    </span>
                    <AnaliseStatusBadge status={a.status_analise} />
                  </div>
                </button>
              ))}
            </div>
          )}
        </>
      )}

      <DiarioForm
        open={formOpen}
        obras={obras}
        defaultObraId={obraId}
        onClose={() => setFormOpen(false)}
        onSave={handleContribuir}
      />

      {selected && (
        <AnaliseModal
          documentoId={selected.id}
          fallbackImage={selected.image}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}

export default DiarioObraPage
