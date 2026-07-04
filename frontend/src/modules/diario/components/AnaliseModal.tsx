import React, { useState, useEffect } from 'react'
import { X, RefreshCw, Loader2, ImageOff } from 'lucide-react'
import { getAnaliseDetalhes, reprocessarAnalise } from '../hooks/useAnalisesIA'
import { extractApiError } from '../hooks/useDiario'
import AnaliseStatusBadge from './AnaliseStatusBadge'
import { mediaUrl } from '@/lib/utils'
import type { AnaliseDocumentoDetalhes } from '@/types'

interface Props {
  documentoId: number
  fallbackImage?: string | null
  onClose: () => void
}

function ResultadoView({ resultado }: { resultado: unknown }) {
  if (resultado == null) {
    return (
      <p className="text-sm" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
        Nenhum resultado disponível ainda.
      </p>
    )
  }

  let parsed: unknown = resultado
  if (typeof resultado === 'string') {
    try { parsed = JSON.parse(resultado) } catch { /* mantém string */ }
  }

  if (typeof parsed === 'string') {
    return (
      <p className="text-sm whitespace-pre-wrap leading-relaxed"
         style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
        {parsed}
      </p>
    )
  }

  if (parsed && typeof parsed === 'object') {
    const entries = Object.entries(parsed as Record<string, unknown>)
    return (
      <div className="flex flex-col gap-3">
        {entries.map(([key, value]) => (
          <div key={key}>
            <p className="text-xs font-semibold uppercase tracking-wide mb-1"
               style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              {key.replace(/_/g, ' ')}
            </p>
            <p className="text-sm whitespace-pre-wrap leading-relaxed"
               style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
              {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
            </p>
          </div>
        ))}
      </div>
    )
  }

  return null
}

export const AnaliseModal: React.FC<Props> = ({ documentoId, fallbackImage, onClose }) => {
  const [data, setData]               = useState<AnaliseDocumentoDetalhes | null>(null)
  const [loading, setLoading]         = useState(true)
  const [imgError, setImgError]       = useState(false)
  const [reprocessing, setReprocess]  = useState(false)
  const [notice, setNotice]           = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setNotice(null)
    getAnaliseDetalhes(documentoId)
      .then(d => { if (active) setData(d) })
      .catch(err => {
        if (active) setNotice(extractApiError(err, 'Este documento ainda não possui análise concluída.'))
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [documentoId])

  const handleReprocess = async () => {
    setReprocess(true)
    setNotice(null)
    try {
      await reprocessarAnalise(documentoId)
      setNotice('Reprocessamento iniciado. Atualize em instantes para ver o novo resultado.')
    } catch (err) {
      setNotice(extractApiError(err, 'Erro ao reprocessar a análise.'))
    } finally {
      setReprocess(false)
    }
  }

  const imageSrc = mediaUrl(data?.url_imagem ?? fallbackImage)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
         style={{ background: 'rgba(0,0,0,0.55)' }}
         onClick={onClose}>
      <div
        className="relative w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden rounded-2xl"
        style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.35)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 shrink-0"
             style={{ borderBottom: '1px solid #e2e8f0' }}>
          <div className="flex items-center gap-3 min-w-0">
            <h2 className="text-base font-bold truncate"
                style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              {data?.nome_original || data?.nome || 'Análise de IA'}
            </h2>
            {data && <AnaliseStatusBadge status={data.status_analise} />}
          </div>
          <button onClick={onClose}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        {/* Conteúdo */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={28} className="animate-spin" style={{ color: 'var(--color-brand)' }} />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 overflow-y-auto">
            {/* Imagem */}
            <div className="flex items-center justify-center p-4" style={{ background: '#0f1f3d' }}>
              {imageSrc && !imgError ? (
                <img src={imageSrc} alt={data?.nome ?? 'Imagem'}
                     className="max-h-[60vh] w-auto rounded-lg object-contain"
                     onError={() => setImgError(true)} />
              ) : (
                <div className="flex flex-col items-center gap-2 py-16" style={{ color: 'rgba(255,255,255,0.5)' }}>
                  <ImageOff size={40} />
                  <span className="text-xs" style={{ fontFamily: 'var(--font-body)' }}>Imagem indisponível</span>
                </div>
              )}
            </div>

            {/* Resultado */}
            <div className="p-6 flex flex-col gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide mb-1"
                   style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                  Obra
                </p>
                <p className="text-sm" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                  {data?.obra_nome || '—'}
                </p>
              </div>

              <div className="rounded-xl p-4" style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
                <ResultadoView resultado={data?.resultado ?? data?.resultado_analise} />
              </div>

              {notice && (
                <div className="text-xs px-3 py-2 rounded-lg"
                     style={{ background: '#e0f2fe', color: '#0369a1', fontFamily: 'var(--font-body)' }}>
                  {notice}
                </div>
              )}

              <button
                onClick={handleReprocess}
                disabled={reprocessing}
                className="flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold mt-auto"
                style={{ background: 'transparent', border: '1.5px solid var(--color-brand)',
                         color: 'var(--color-brand)', fontFamily: 'var(--font-body)',
                         cursor: reprocessing ? 'not-allowed' : 'pointer' }}
              >
                {reprocessing
                  ? <><Loader2 size={14} className="animate-spin" />Enviando…</>
                  : <><RefreshCw size={14} />Reprocessar análise</>}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default AnaliseModal
