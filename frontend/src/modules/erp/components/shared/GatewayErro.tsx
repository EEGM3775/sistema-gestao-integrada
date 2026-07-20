import { useEffect, useState } from 'react'
import { X, AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react'

/**
 * Exibição unificada dos erros do gateway (Asaas p/ boleto, NFE.io p/ NFS-e).
 *
 * O status "Erro" deixa de ser só um rótulo: vira um BOTÃO que abre um popup
 * com TODOS os códigos e mensagens que o gateway devolveu (`dados_retorno_api`),
 * mais o JSON cru para o financeiro/suporte. É o "método de o usuário saber o
 * que aconteceu" — em vez de um erro genérico e invisível.
 */

interface ErroItem {
  codigo?: string
  descricao: string
}

/**
 * Normaliza os vários formatos de erro num par (código, descrição):
 *  - Asaas: `{erro, status_code, detalhes: {errors: [{code, description}]}}`
 *  - NFE.io: `{erro, detalhes: {message, errors: [...]}}` ou `{erro, detalhes: [...]}`
 *  - Validação local: `{erro: "mensagem", detalhes: null}`
 */
export function extrairErrosGateway(dados: Record<string, unknown> | null | undefined): {
  mensagem: string
  itens: ErroItem[]
} {
  if (!dados || typeof dados !== 'object') return { mensagem: '', itens: [] }

  const mensagem = typeof dados.erro === 'string' ? dados.erro : ''
  const itens: ErroItem[] = []

  const push = (v: unknown) => {
    if (!v) return
    if (typeof v === 'string') { itens.push({ descricao: v }); return }
    if (typeof v === 'object') {
      const o = v as Record<string, unknown>
      const descricao = (o.description ?? o.message ?? o.detail ?? o.msg) as string | undefined
      const codigo = (o.code ?? o.codigo ?? o.status) as string | number | undefined
      if (descricao) itens.push({ codigo: codigo != null ? String(codigo) : undefined, descricao: String(descricao) })
      else itens.push({ descricao: JSON.stringify(o) })
    }
  }

  const detalhes = dados.detalhes as unknown
  if (Array.isArray(detalhes)) {
    detalhes.forEach(push)
  } else if (detalhes && typeof detalhes === 'object') {
    const d = detalhes as Record<string, unknown>
    if (Array.isArray(d.errors)) d.errors.forEach(push)
    else if (typeof d.message === 'string') push(d.message)
    else if (Object.keys(d).length) push(d)
  }

  const statusCode = dados.status_code
  const cabecalho = mensagem || (itens[0]?.descricao ?? 'Erro reportado pelo gateway.')
  return {
    mensagem: statusCode ? `${cabecalho}` : cabecalho,
    itens: itens.filter(i => i.descricao),
  }
}

/**
 * Badge "Erro" clicável: mostra a pílula vermelha e, ao clicar, abre o popup
 * com os detalhes. `titulo` nomeia a origem no cabeçalho do popup.
 */
export function BotaoErroGateway({
  dados,
  titulo = 'Detalhes do erro',
  label = 'Erro',
}: {
  dados: Record<string, unknown> | null | undefined
  titulo?: string
  label?: string
}) {
  const [aberto, setAberto] = useState(false)
  return (
    <>
      <button
        type="button"
        onClick={e => { e.stopPropagation(); setAberto(true) }}
        title="Ver detalhes do erro"
        className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full whitespace-nowrap transition-opacity duration-150"
        style={{ background: '#fee2e2', color: '#991b1b', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
      >
        <AlertTriangle size={12} /> {label}
      </button>
      {aberto && <GatewayErroDialog dados={dados} titulo={titulo} onClose={() => setAberto(false)} />}
    </>
  )
}

/** Popup com a lista de códigos/mensagens + o JSON cru (expansível). */
export function GatewayErroDialog({
  dados,
  titulo,
  onClose,
}: {
  dados: Record<string, unknown> | null | undefined
  titulo: string
  onClose: () => void
}) {
  const [verJson, setVerJson] = useState(false)
  const { mensagem, itens } = extrairErrosGateway(dados)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [onClose])

  const statusCode = dados && typeof dados === 'object' ? (dados as Record<string, unknown>).status_code : undefined

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center px-4" onClick={e => e.stopPropagation()}>
      <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        className="relative w-full flex flex-col rounded-xl"
        style={{ maxWidth: 560, maxHeight: '85vh', background: '#FFFFFF', boxShadow: 'var(--shadow-lg)', border: '1.5px solid #e2e8f0' }}
      >
        <header className="flex items-start justify-between gap-3 px-5 py-4" style={{ borderBottom: '1.5px solid #e2e8f0' }}>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: '#fee2e2', color: '#991b1b' }}>
              <AlertTriangle size={18} />
            </div>
            <div>
              <h2 className="text-base font-bold" style={{ fontFamily: 'var(--font-heading)', color: '#991b1b' }}>{titulo}</h2>
              {statusCode != null && (
                <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                  HTTP {String(statusCode)}
                </p>
              )}
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Fechar" className="p-1.5 rounded-lg shrink-0"
            style={{ color: 'var(--color-text-muted)', cursor: 'pointer', background: 'none', border: 'none' }}>
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4" style={{ fontFamily: 'var(--font-body)' }}>
          {mensagem && (
            <p className="text-sm mb-3" style={{ color: 'var(--color-text)', lineHeight: 1.5 }}>{mensagem}</p>
          )}

          {itens.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {itens.map((item, i) => (
                <li key={i} className="px-3 py-2 rounded-lg text-sm"
                  style={{ background: '#fff5f5', border: '1px solid #fed7d7', color: '#7f1d1d' }}>
                  {item.codigo && (
                    <span className="font-mono text-xs font-semibold mr-2 px-1.5 py-0.5 rounded"
                      style={{ background: '#fee2e2', color: '#991b1b' }}>{item.codigo}</span>
                  )}
                  {item.descricao}
                </li>
              ))}
            </ul>
          ) : (
            !mensagem && <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>Nenhum detalhe adicional foi retornado pelo gateway.</p>
          )}

          <button
            type="button"
            onClick={() => setVerJson(v => !v)}
            className="flex items-center gap-1.5 mt-4 text-xs font-semibold"
            style={{ color: 'var(--color-brand)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          >
            {verJson ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            Ver retorno técnico completo (JSON)
          </button>
          {verJson && (
            <pre className="mt-2 text-xs p-3 rounded-lg overflow-x-auto"
              style={{ background: '#0f172a', color: '#e2e8f0', fontFamily: 'monospace', maxHeight: 300 }}>
              {JSON.stringify(dados, null, 2)}
            </pre>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 px-5 py-3.5" style={{ borderTop: '1.5px solid #e2e8f0', background: '#f8fafc' }}>
          <button type="button" onClick={onClose}
            className="text-sm font-semibold px-4 py-2 rounded-lg"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
            Fechar
          </button>
        </footer>
      </div>
    </div>
  )
}
