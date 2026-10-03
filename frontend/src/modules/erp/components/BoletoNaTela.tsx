import { useEffect, useState, type CSSProperties } from 'react'
import { AlertTriangle, CalendarClock, Check, Copy, Download, ExternalLink, FileText, Loader2, X } from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { usePdfBoleto, useMiniaturaBoleto } from '../hooks/useCobranca'
import { verificarDocumentoBoleto } from '../api/endpoints/boletos'
import { erpKeys } from '../api/queryKeys'
import { StatusBoletoBadge } from './shared/StatusBoletoBadge'
import { MoneyDisplay } from './shared/MoneyDisplay'
import { apiDecimalToCents } from '@/utils/money'
import { dateToBR } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import type { Boleto } from '../types'

/**
 * O boleto dentro da tela (item 56 do dono): a miniatura da primeira página, a
 * linha digitável para copiar e o PDF aberto num leitor aqui mesmo — antes, a
 * tela lateral só dizia que a cobrança "foi iniciada" e não mostrava nada.
 *
 * Revisão do dono (01/10/2026, item 55): o boleto do Asaas mostrava "Linha
 * digitável ainda não disponível" para sempre — ela mora num endpoint à parte,
 * que o SGI não chamava. Faltando, a tela pergunta ao Asaas na hora (e o
 * backend guarda). E o boleto diz por que vence noutro dia (feriado) e quando
 * deixou de ser o da conta (`desatualizado`, a frase vem da API).
 */
export function BoletoNaTela({ boleto, desatualizado }: { boleto: Boleto; desatualizado?: string }) {
  const [lendo, setLendo] = useState(false)
  const temDocumento = boleto.canal === 'cnab' ? Boolean(boleto.linha_digitavel) : Boolean(boleto.gateway_id)
  const miniatura = useMiniaturaBoleto(temDocumento ? boleto.boleto_id : undefined)
  const segundaVia = Number(boleto.valor_multa) > 0 || Number(boleto.valor_juros) > 0
  const aoVivo = useLinhaDoAsaas(boleto)
  const linha = boleto.linha_digitavel || aoVivo.linha
  const ajuste = ajusteDeVencimento(boleto)

  return (
    <>
    <div className="flex gap-3 min-w-0" style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', padding: 10, background: 'var(--surface)' }}>
      <button
        type="button"
        onClick={() => setLendo(true)}
        disabled={!temDocumento}
        aria-label="Ver o boleto"
        style={{
          width: 96, height: 124, flex: 'none', borderRadius: 'var(--r-sm)', overflow: 'hidden', padding: 0,
          border: '1px solid var(--line)', background: 'var(--surface-2)', cursor: temDocumento ? 'zoom-in' : 'default',
          display: 'grid', placeItems: 'center', color: 'var(--ink-3)',
        }}
      >
        {miniatura.url
          ? <img src={miniatura.url} alt="Miniatura do boleto" style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }} />
          : miniatura.carregando ? <Loader2 size={18} className="animate-spin" /> : <FileText size={22} />}
      </button>

      <div className="flex flex-col gap-1.5 min-w-0 flex-1 text-sm">
        <div className="flex items-center gap-2 flex-wrap">
          <StatusBoletoBadge status={boleto.status} />
          <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>
            {boleto.canal === 'cnab' ? 'Banco (CNAB)' : 'Asaas'} · vence {dateToBR(boleto.data_vencimento)}
          </span>
        </div>
        <div className="flex items-baseline gap-2">
          <strong><MoneyDisplay cents={apiDecimalToCents(boleto.valor)} /></strong>
          {segundaVia && (
            <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
              inclui multa <MoneyDisplay cents={apiDecimalToCents(boleto.valor_multa)} /> e juros <MoneyDisplay cents={apiDecimalToCents(boleto.valor_juros)} />
            </span>
          )}
        </div>
        {linha ? <LinhaParaCopiar linha={linha} /> : (
          <span className="flex items-center gap-1.5" style={{ fontSize: 12, color: 'var(--ink-3)' }}>
            {boleto.status === 'AGUARDANDO' ? 'Aguardando o registro no banco.'
              : aoVivo.buscando ? <><Loader2 size={12} className="animate-spin" /> Buscando a linha digitável no Asaas…</>
              : 'O Asaas não devolveu a linha digitável agora — ela está impressa no boleto (Ver boleto).'}
          </span>
        )}
        {ajuste && (
          <span className="flex items-start gap-1.5" style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
            <CalendarClock size={13} style={{ flex: 'none', marginTop: 1 }} />
            O contrato vence em {dateToBR(ajuste.contratual)}, {/^(sábado|domingo)$/.test(ajuste.motivo) ? `um ${ajuste.motivo}` : `feriado de ${ajuste.motivo}`}: o boleto vence no próximo dia útil.
          </span>
        )}
        {temDocumento && (
          <button type="button" onClick={() => setLendo(true)} className="self-start flex items-center gap-1.5"
            style={{ border: 'none', background: 'none', padding: 0, color: 'var(--accent-ink)', fontWeight: 600, fontSize: 12.5, cursor: 'pointer' }}>
            <FileText size={14} /> Ver boleto
          </button>
        )}
      </div>

      {lendo && <LeitorDeBoleto boleto={boleto} onFechar={() => setLendo(false)} />}
    </div>
    {desatualizado && (
      <p role="alert" className="flex gap-2 mt-2" style={{ fontSize: 12.5, padding: '8px 10px', borderRadius: 'var(--r-sm)', background: 'var(--danger-soft)', color: 'var(--danger-ink)' }}>
        <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
        <span>{desatualizado}</span>
      </p>
    )}
    </>
  )
}

/** Por que a data do boleto não é a do contrato — gravado na emissão. */
function ajusteDeVencimento(boleto: Boleto): { contratual: string; motivo: string } | null {
  const a = boleto.dados_retorno_api?.ajuste_de_vencimento as { contratual?: string; motivo?: string } | undefined
  return a?.contratual && a.motivo ? { contratual: a.contratual, motivo: a.motivo } : null
}

/**
 * Boleto do Asaas sem linha digitável: pergunta uma vez ao Asaas (a
 * verificação ao vivo grava o que vier) e atualiza a conta e a lista.
 */
function useLinhaDoAsaas(boleto: Boleto) {
  const qc = useQueryClient()
  const falta = boleto.canal === 'asaas' && !boleto.linha_digitavel && Boolean(boleto.gateway_id)
    && (boleto.status === 'EMITIDO' || boleto.status === 'VENCIDO')
  const consulta = useQuery({
    queryKey: ['erp', 'cobranca', 'linha', boleto.boleto_id],
    queryFn: () => verificarDocumentoBoleto(boleto.boleto_id),
    enabled: falta,
    staleTime: Infinity,
    retry: false,
  })
  const linha = consulta.data?.linha_digitavel || ''
  useEffect(() => {
    if (!linha) return
    qc.invalidateQueries({ queryKey: erpKeys.contasAReceber.all })
    qc.invalidateQueries({ queryKey: erpKeys.boletos.all })
  }, [linha, qc])
  return { linha, buscando: falta && consulta.isLoading }
}

function LinhaParaCopiar({ linha }: { linha: string }) {
  const [copiado, setCopiado] = useState(false)
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(linha.replace(/\D/g, ''))
      setCopiado(true)
      setTimeout(() => setCopiado(false), 2000)
    } catch {
      setCopiado(false)
    }
  }
  return (
    <div className="flex items-start gap-2 min-w-0">
      <code style={{ fontSize: 11.5, fontFamily: 'var(--mono)', color: 'var(--ink-2)', overflowWrap: 'anywhere', lineHeight: 1.5 }}>
        {formatarLinha(linha)}
      </code>
      <button type="button" onClick={copiar} aria-label="Copiar linha digitável"
        style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', background: 'var(--surface)', padding: '2px 6px', cursor: 'pointer', color: copiado ? 'var(--good-ink)' : 'var(--ink-3)', display: 'flex' }}>
        {copiado ? <Check size={13} /> : <Copy size={13} />}
      </button>
    </div>
  )
}

/**
 * `46191.11000 00000.000000 13431.604019 3 27740000210080` — o formato do
 * boleto impresso. O Asaas devolve os 47 dígitos colados; o CNAB já vem assim.
 */
function formatarLinha(linha: string): string {
  const d = linha.replace(/\D/g, '')
  if (d.length !== 47) return linha
  return `${d.slice(0, 5)}.${d.slice(5, 10)} ${d.slice(10, 15)}.${d.slice(15, 21)} ${d.slice(21, 26)}.${d.slice(26, 32)} ${d[32]} ${d.slice(33)}`
}

/** O PDF num leitor dentro do SGI, com baixar e abrir em nova aba. */
export function LeitorDeBoleto({ boleto, onFechar }: { boleto: Boleto; onFechar: () => void }) {
  const pdf = usePdfBoleto(boleto.boleto_id)

  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onFechar() }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [onFechar])

  const erro = pdf.erro ? parseApiErrors(pdf.erro)._form : null
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.55)' }} onClick={onFechar} aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-label="Boleto"
        className="relative flex flex-col w-full"
        style={{ maxWidth: 860, height: '90vh', background: 'var(--surface)', borderRadius: 'var(--r-lg)', overflow: 'hidden', boxShadow: 'var(--shadow-lg)' }}>
        <header className="flex items-center gap-2 px-4 py-3" style={{ borderBottom: '1px solid var(--line)' }}>
          <FileText size={17} style={{ color: 'var(--ink-3)' }} />
          <strong style={{ fontSize: 14 }}>Boleto — vence {dateToBR(boleto.data_vencimento)}</strong>
          <span className="flex items-center gap-2" style={{ marginLeft: 'auto' }}>
            {pdf.url && (
              <>
                <a href={pdf.url} download={`boleto-${boleto.boleto_id}.pdf`} className="flex items-center gap-1.5" style={acao}><Download size={14} /> Baixar</a>
                <a href={pdf.url} target="_blank" rel="noreferrer" className="flex items-center gap-1.5" style={acao}><ExternalLink size={14} /> Nova aba</a>
              </>
            )}
            <button type="button" onClick={onFechar} aria-label="Fechar" style={{ ...acao, cursor: 'pointer' }}><X size={16} /></button>
          </span>
        </header>
        <div className="flex-1" style={{ background: 'var(--inset)' }}>
          {pdf.url && <iframe title="Boleto em PDF" src={pdf.url} style={{ width: '100%', height: '100%', border: 'none' }} />}
          {pdf.carregando && <p className="flex items-center gap-2 p-6 text-sm" style={{ color: 'var(--ink-3)' }}><Loader2 size={16} className="animate-spin" /> Buscando o boleto…</p>}
          {erro && <p className="p-6 text-sm" style={{ color: 'var(--danger-ink)' }}>{erro}</p>}
        </div>
      </div>
    </div>
  )
}

const acao: CSSProperties = {
  border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', background: 'var(--surface)', padding: '5px 9px',
  fontSize: 12.5, color: 'var(--ink-2)', textDecoration: 'none', display: 'flex', alignItems: 'center',
}
