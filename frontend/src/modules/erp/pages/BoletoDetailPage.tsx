import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Copy, Check, ExternalLink, Ban, AlertTriangle } from 'lucide-react'
import {
  useBoleto, useEventosWebhookAsaas, useCancelarBoleto, useVerificarDocumentoBoleto,
} from '../hooks/useBoletos'
import { MoneyDisplay } from '../components/shared/MoneyDisplay'
import { StatusBoletoBadge } from '../components/shared/StatusBoletoBadge'
import { GatewayErroDialog } from '../components/shared/GatewayErro'
import { buttonSecondaryStyle } from '../components/forms/formStyles'
import { apiDecimalToCents } from '@/utils/money'
import { dateToBR } from '@/utils/dates'
import type { EventoWebhookAsaas } from '../types'

/** `recebido_em`/`processado_em` chegam como datetime ISO completo (não só data) — formata local pt-BR. */
function dateTimeToBR(iso: string | null): string {
  if (!iso) return '—'
  const data = new Date(iso)
  if (Number.isNaN(data.getTime())) return iso
  return data.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' })
}

/**
 * Detalhe dedicado de um Boleto (D.1.2, docs/modulos/moduloerp.md §6): dados
 * do gateway (linha digitável, link do PDF) + a timeline de eventos do
 * webhook Asaas que provam, evento a evento, como a baixa automática
 * aconteceu (`dar_baixa(origem='asaas')`/idempotência/`RevisaoBaixa`).
 *
 * Tela cheia (não Sheet) — escolha do usuário ("telas dedicadas de boletos"),
 * registrada sob `/app/erp/boletos/:id` (mesmo arquétipo de
 * `empreendimentos/:id`: rota-irmã com `useParams` + navegação própria de volta).
 */
export default function BoletoDetailPage() {
  const { id } = useParams<{ id: string }>()
  const boletoId = id ? Number(id) : undefined

  const { data: boleto, isLoading, isError } = useBoleto(boletoId)
  const { data: eventos, isLoading: isLoadingEventos } = useEventosWebhookAsaas(boletoId)
  const cancelar = useCancelarBoleto()
  const verificarDoc = useVerificarDocumentoBoleto()
  const [mensagem, setMensagem] = useState<{ tom: 'ok' | 'erro'; texto: string } | null>(null)
  const [erroAberto, setErroAberto] = useState(false)

  /** Abre o PDF verificando o Asaas AO VIVO (aba aberta no clique p/ não bloquear popup). */
  function aoAbrirDocumento() {
    if (!boletoId) return
    const win = window.open('', '_blank')
    verificarDoc.mutate(boletoId, {
      onSuccess: doc => {
        if (doc.url_pdf && win) win.location.href = doc.url_pdf
        else if (win) win.close()
        if (!doc.gateway_online) setMensagem({ tom: 'erro', texto: doc.mensagem })
        else if (!doc.url_pdf) setMensagem({ tom: 'erro', texto: 'Documento ainda indisponível no Asaas.' })
      },
      onError: () => { if (win) win.close(); setMensagem({ tom: 'erro', texto: 'Não foi possível verificar o documento no Asaas.' }) },
    })
  }

  function aoCancelar() {
    if (!boletoId || !window.confirm(`Cancelar o boleto #${boletoId} no Asaas? A ação não pode ser desfeita.`)) return
    cancelar.mutate(boletoId, {
      onSuccess: r => setMensagem({ tom: 'ok', texto: r.detail }),
      onError: () => setMensagem({ tom: 'erro', texto: 'Não foi possível cancelar o boleto agora.' }),
    })
  }

  const cancelavel = boleto ? ['EMITIDO', 'VENCIDO', 'AGUARDANDO'].includes(boleto.status) : false

  return (
    <div className="px-6 py-8">
      <Link
        to="/app/erp/boletos"
        className="inline-flex items-center gap-1.5 text-xs font-semibold mb-3 transition-colors duration-150"
        style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', textDecoration: 'none' }}
        onMouseEnter={e => (e.currentTarget.style.color = 'var(--color-brand)')}
        onMouseLeave={e => (e.currentTarget.style.color = 'var(--color-text-muted)')}
      >
        <ArrowLeft size={14} /> Boletos
      </Link>

      {isLoading && (
        <p className="text-sm" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>Carregando boleto…</p>
      )}

      {isError && (
        <div className="text-sm px-4 py-3 rounded-lg mb-4"
          style={{ background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030', fontFamily: 'var(--font-body)' }}>
          Não foi possível carregar este boleto.
        </div>
      )}

      {boleto && (
        <>
          <div className="flex items-center justify-between gap-3 mb-6 flex-wrap">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
                  Boleto #{boleto.boleto_id}
                </h1>
                <StatusBoletoBadge status={boleto.status} />
              </div>
              <p className="text-xs mt-1" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
                {boleto.conta_receber != null
                  ? `Vinculado à conta a receber #${boleto.conta_receber}`
                  : boleto.conta_pagar != null
                  ? `Vinculado à conta a pagar #${boleto.conta_pagar}`
                  : 'Sem conta vinculada'}
              </p>
            </div>
            {cancelavel && (
              <button
                type="button"
                onClick={aoCancelar}
                disabled={cancelar.isPending}
                className="inline-flex items-center gap-1.5 rounded-lg font-semibold px-4 py-2 text-sm transition-opacity duration-150"
                style={{ background: '#fee2e2', color: '#991b1b', border: 'none', cursor: cancelar.isPending ? 'wait' : 'pointer', fontFamily: 'var(--font-body)', opacity: cancelar.isPending ? 0.6 : 1 }}
              >
                <Ban size={15} /> {cancelar.isPending ? 'Cancelando…' : 'Cancelar boleto'}
              </button>
            )}
          </div>

          {mensagem && (
            <div className="text-sm px-4 py-3 rounded-lg mb-4"
              style={mensagem.tom === 'ok'
                ? { background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#166534', fontFamily: 'var(--font-body)' }
                : { background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030', fontFamily: 'var(--font-body)' }}>
              {mensagem.texto}
            </div>
          )}

          {boleto.status === 'ERRO' && (
            <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-lg mb-6"
              style={{ background: '#fff5f5', border: '1px solid #fed7d7', fontFamily: 'var(--font-body)' }}>
              <span className="text-sm flex items-center gap-2" style={{ color: '#991b1b' }}>
                <AlertTriangle size={16} /> A cobrança foi recusada pelo Asaas.
              </span>
              <button type="button" onClick={() => setErroAberto(true)}
                className="text-xs font-semibold px-3 py-1.5 rounded-lg"
                style={{ background: '#991b1b', color: '#FFFFFF', border: 'none', cursor: 'pointer' }}>
                Ver detalhes do erro
              </button>
            </div>
          )}

          {erroAberto && (
            <GatewayErroDialog
              dados={boleto.dados_retorno_api}
              titulo="Erro na cobrança (Asaas)"
              onClose={() => setErroAberto(false)}
            />
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <section className="rounded-xl p-5" style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF' }}>
              <h2 className="text-xs font-semibold uppercase tracking-wide mb-4" style={{ color: 'var(--color-brand)' }}>
                Dados do boleto
              </h2>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm" style={{ fontFamily: 'var(--font-body)' }}>
                <DetailItem label="Valor" value={<MoneyDisplay cents={apiDecimalToCents(boleto.valor)} />} />
                <DetailItem label="Vencimento" value={dateToBR(boleto.data_vencimento)} />
                <DetailItem label="Pagamento" value={boleto.data_pagamento ? dateToBR(boleto.data_pagamento) : '—'} />
                {boleto.data_cancelamento && (
                  <DetailItem label="Cancelamento" value={dateToBR(boleto.data_cancelamento)} />
                )}
                <DetailItem label="ID no gateway (Asaas)" value={boleto.gateway_id ?? '—'} />
              </dl>

              <div className="mt-5 pt-5 flex flex-col gap-3" style={{ borderTop: '1px solid #f1f5f9' }}>
                <h3 className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--color-brand)' }}>
                  Cobrança (gateway)
                </h3>
                <LinhaDigitavel valor={boleto.linha_digitavel} />
                {boleto.gateway_id ? (
                  <button
                    type="button"
                    onClick={aoAbrirDocumento}
                    disabled={verificarDoc.isPending}
                    className="inline-flex items-center gap-2 self-start"
                    style={{ ...buttonSecondaryStyle, cursor: verificarDoc.isPending ? 'wait' : 'pointer', opacity: verificarDoc.isPending ? 0.6 : 1 }}
                  >
                    <ExternalLink size={14} /> {verificarDoc.isPending ? 'Verificando no Asaas…' : 'Abrir PDF (verifica no Asaas)'}
                  </button>
                ) : (
                  <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>PDF ainda não disponível — aguardando confirmação do gateway.</p>
                )}
              </div>
            </section>

            <section className="rounded-xl p-5" style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF' }}>
              <h2 className="text-xs font-semibold uppercase tracking-wide mb-4" style={{ color: 'var(--color-brand)' }}>
                Timeline de eventos do webhook (Asaas)
              </h2>
              <p className="text-xs mb-4" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                Cada evento recebido em <code>/api/erp/cobrancas/webhook/asaas/</code> e o resultado do
                processamento — é assim que o ERP sabe, automaticamente, quando este boleto foi pago.
              </p>

              {isLoadingEventos && (
                <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>Carregando eventos…</p>
              )}

              {!isLoadingEventos && (eventos?.length ?? 0) === 0 && (
                <p className="text-sm" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                  Nenhum evento de webhook recebido para este boleto ainda.
                </p>
              )}

              {!isLoadingEventos && eventos && eventos.length > 0 && (
                <ol className="flex flex-col gap-3">
                  {eventos.map(evento => <EventoTimelineItem key={evento.id} evento={evento} />)}
                </ol>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  )
}

function DetailItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{label}</dt>
      <dd className="font-medium break-all" style={{ color: 'var(--color-text)' }}>{value}</dd>
    </div>
  )
}

function LinhaDigitavel({ valor }: { valor: string | null }) {
  const [copiado, setCopiado] = useState(false)

  if (!valor) {
    return <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Linha digitável ainda não disponível.</p>
  }

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(valor)
      setCopiado(true)
      setTimeout(() => setCopiado(false), 2000)
    } catch {
      // Clipboard indisponível (ex.: contexto não-seguro) — falha silenciosa, o valor já está visível para copiar manualmente.
    }
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <code className="text-xs px-2.5 py-1.5 rounded-md break-all" style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
        {valor}
      </code>
      <button
        type="button"
        onClick={copiar}
        className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1.5 rounded-md transition-colors duration-150"
        style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF', color: copiado ? '#166534' : 'var(--color-text-muted)', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
      >
        {copiado ? <><Check size={13} /> Copiado</> : <><Copy size={13} /> Copiar linha digitável</>}
      </button>
    </div>
  )
}

const TIPO_EVENTO_LABELS: Record<string, string> = {
  PAYMENT_CREATED: 'Cobrança criada',
  PAYMENT_RECEIVED: 'Pagamento recebido',
  PAYMENT_CONFIRMED: 'Pagamento confirmado',
  PAYMENT_OVERDUE: 'Cobrança vencida',
  PAYMENT_REFUNDED: 'Pagamento estornado',
}

function EventoTimelineItem({ evento }: { evento: EventoWebhookAsaas }) {
  const label = TIPO_EVENTO_LABELS[evento.tipo] ?? evento.tipo
  return (
    <li className="flex gap-3">
      <div className="flex flex-col items-center pt-1">
        <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: 'var(--color-brand)' }} />
        <span className="w-px flex-1" style={{ background: '#e2e8f0' }} />
      </div>
      <div className="flex flex-col gap-0.5 pb-2 text-sm" style={{ fontFamily: 'var(--font-body)' }}>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold" style={{ color: 'var(--color-text)' }}>{label}</span>
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{dateTimeToBR(evento.recebido_em)}</span>
        </div>
        {evento.resultado && (
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{evento.resultado}</span>
        )}
        <span className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
          evento {evento.evento_id} · processado em {dateTimeToBR(evento.processado_em)}
        </span>
      </div>
    </li>
  )
}
