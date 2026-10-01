import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, Loader2, ScrollText, X } from 'lucide-react'
import { formatBRL, apiDecimalToCents } from '@/utils/money'
import { parseApiErrors } from '@/utils/formErrors'
import { useEmitirLoteNfse, usePreviaLoteNfse } from '../hooks/useCobranca'
import type { EscolhaDoLote } from '../api/endpoints/cobranca'
import type { PreviaLoteNfse, ResultadoLoteNfse } from '../types'
import { buttonPrimaryStyle, buttonSecondaryStyle } from './forms/formStyles'

/**
 * NFS-e em lote (pedido do dono, 01/10/2026): "emitir a nota geral — não só
 * da cobrança". A mesma escolha da grade que gera os boletos — linhas marcadas,
 * ou todas do filtro menos as desmarcadas — vira uma prévia (quantas notas
 * saem, quantas contas já têm nota, de quem falta cadastro) e a emissão.
 */
export function EmitirNotasLoteDialog({ escolha, quantidade, onFechar }: {
  escolha: EscolhaDoLote
  quantidade: number
  /** `emitiu`: a seleção só se desfaz quando as notas saíram — olhar a prévia não a perde. */
  onFechar: (emitiu: boolean) => void
}) {
  const previa = usePreviaLoteNfse()
  const emitir = useEmitirLoteNfse()
  const refazer = previa.mutate
  const chave = JSON.stringify(escolha)
  useEffect(() => { refazer(JSON.parse(chave) as EscolhaDoLote) }, [chave, refazer])

  const p = previa.data
  const erro = previa.error ? parseApiErrors(previa.error)._form : emitir.error ? parseApiErrors(emitir.error)._form : null
  const podeEmitir = p && p.emitir > 0 && !emitir.isPending && !emitir.data
  const fechar = () => onFechar(Boolean(emitir.data))

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center px-4">
      <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onClick={() => !emitir.isPending && fechar()} aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-label="Emitir notas fiscais em lote" className="relative w-full flex flex-col rounded-xl"
        style={{ maxWidth: 540, maxHeight: '90vh', background: 'var(--surface)', boxShadow: 'var(--shadow-lg)', border: '1px solid var(--line)' }}>
        <header className="flex items-center gap-2.5 px-5 py-4" style={{ borderBottom: '1px solid var(--line)' }}>
          <ScrollText size={18} style={{ color: 'var(--accent-ink)' }} />
          <h2 className="text-base font-bold" style={{ color: 'var(--ink)' }}>
            Emitir notas fiscais — {quantidade.toLocaleString('pt-BR')} conta{quantidade !== 1 ? 's' : ''}
          </h2>
          <button type="button" onClick={fechar} aria-label="Fechar" style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)' }}><X size={18} /></button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-4 text-sm" style={{ color: 'var(--ink-2)' }}>
          {emitir.data ? <ResultadoNotas resultado={emitir.data} /> : (
            <>
              {!p && previa.isPending && <p className="flex items-center gap-2"><Loader2 size={15} className="animate-spin" /> Conferindo as contas e os cadastros…</p>}
              {p && <ResumoNotas previa={p} />}
            </>
          )}
          {erro && <p style={{ color: 'var(--danger-ink)' }}>⚠ {erro}</p>}
        </div>

        <footer className="flex items-center justify-end gap-2 px-5 py-3.5" style={{ borderTop: '1px solid var(--line)', background: 'var(--surface-2)' }}>
          {emitir.data ? (
            <button type="button" onClick={fechar} style={buttonPrimaryStyle}>Fechar</button>
          ) : (
            <>
              <button type="button" onClick={fechar} style={buttonSecondaryStyle}>Cancelar</button>
              <button type="button" disabled={!podeEmitir} onClick={() => emitir.mutate(escolha)}
                style={{ ...buttonPrimaryStyle, opacity: podeEmitir ? 1 : 0.6, cursor: emitir.isPending ? 'wait' : 'pointer' }}>
                {emitir.isPending ? 'Enviando…' : `Emitir ${p?.emitir ?? ''} nota${p?.emitir === 1 ? '' : 's'}`}
              </button>
            </>
          )}
        </footer>
      </div>
    </div>
  )
}

/** A prévia: quantas saem, quantas ficam de fora e por quê. */
export function ResumoNotas({ previa: p }: { previa: PreviaLoteNfse }) {
  return (
    <>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5" style={{ background: 'var(--surface-2)', borderRadius: 'var(--r-md)', padding: '10px 12px' }}>
        <dt>Notas a emitir</dt><dd className="text-right font-semibold">{p.emitir}</dd>
        <dt>Já têm nota emitida ou em emissão — ficam de fora</dt><dd className="text-right">{p.com_nota}</dd>
        {p.sem_cadastro > 0 && <><dt>Cadastro do tomador incompleto — ficam de fora</dt><dd className="text-right">{p.sem_cadastro}</dd></>}
        {p.canceladas > 0 && <><dt>Contas canceladas — ficam de fora</dt><dd className="text-right">{p.canceladas}</dd></>}
        <dt className="font-bold" style={{ color: 'var(--ink)' }}>Valor dos serviços</dt>
        <dd className="text-right font-bold" style={{ color: 'var(--ink)' }}>{formatBRL(apiDecimalToCents(p.valor_total))}</dd>
      </dl>
      {p.cadastro_incompleto_total > 0 && (
        <div style={{ padding: '10px 12px', borderRadius: 'var(--r-md)', background: 'var(--accent-soft)', color: 'var(--accent-ink)', fontSize: 12.5 }}>
          <p className="font-semibold">A prefeitura só aceita a nota com CPF/CNPJ, CEP e município do tomador.</p>
          <p className="mt-1">Complete o cadastro (abre em outra aba) e emita de novo as que ficaram de fora.</p>
          <ul className="flex flex-col gap-0.5 mt-2">
            {p.cadastro_incompleto.map(c => (
              <li key={c.cliente_id}>
                <Link to={`/app/clientes/${c.cliente_id}`} target="_blank" rel="noreferrer" style={{ color: 'inherit', fontWeight: 600 }}>{c.cliente_nome}</Link>
                {' '}— falta {c.falta.join(', ')}
              </li>
            ))}
            {p.cadastro_incompleto_total > p.cadastro_incompleto.length && (
              <li>e mais {p.cadastro_incompleto_total - p.cadastro_incompleto.length}.</li>
            )}
          </ul>
        </div>
      )}
    </>
  )
}

/** O desfecho: quantas foram para a NFE.io e quem ficou de fora, com o motivo. */
export function ResultadoNotas({ resultado: r }: { resultado: ResultadoLoteNfse }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="flex items-center gap-2 font-semibold" style={{ color: 'var(--ink)' }}>
        <CheckCircle2 size={16} style={{ color: 'var(--good-ink)' }} />
        {r.enviadas} nota{r.enviadas !== 1 ? 's' : ''} enviada{r.enviadas !== 1 ? 's' : ''} à prefeitura
      </p>
      <p style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
        A prefeitura devolve cada nota em segundos ou minutos; o SGI acompanha sozinho.{' '}
        <Link to="/app/erp/notas-fiscais" style={{ color: 'var(--accent-ink)', fontWeight: 600 }}>Ver as notas</Link>
      </p>
      {r.recusadas_total > 0 && (
        <div>
          <p className="font-semibold" style={{ color: 'var(--danger-ink)' }}>{r.recusadas_total} conta{r.recusadas_total !== 1 ? 's' : ''} ficaram sem nota:</p>
          <ul className="flex flex-col gap-1 mt-1" style={{ fontSize: 12.5 }}>
            {r.recusadas.map(f => (
              <li key={f.conta_receber_id}>
                <Link to={`/app/clientes/${f.cliente_id}`} target="_blank" rel="noreferrer" style={{ color: 'inherit', fontWeight: 600 }}>{f.cliente_nome}</Link>
                {' '}· {f.descricao} — {f.mensagem}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
