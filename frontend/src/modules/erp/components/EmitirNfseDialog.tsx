import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { X, ScrollText } from 'lucide-react'
import { formatBRL, apiDecimalToCents } from '@/utils/money'
import { dateToBR } from '@/utils/dates'
import { useContaAReceber, useContasAReceber } from '../hooks/useContasAReceber'
import { useEmitirNfse } from '../hooks/useNotasFiscais'
import { CaixaDeBusca } from '../grade/BarraDaGrade'
import { buttonPrimaryStyle, buttonSecondaryStyle, inputStyle, selectStyle, labelStyle } from './forms/formStyles'

interface Props {
  open: boolean
  onClose: () => void
  /** Chamado quando a emissão foi enfileirada (202) — a página exibe o aviso e vai para "Emitidas". */
  onEmitted: (message: string) => void
  /** A conta já escolhida — quando o diálogo abre a partir do detalhe dela. */
  contaInicial?: number
}

interface ApiErr { response?: { status?: number; data?: { message?: string; detail?: string; error?: string; cliente_id?: number } } }

/** A frase do erro e, quando falta dado do tomador, o cliente a completar (item 58). */
function mensagemDeErro(e: unknown): { texto: string; clienteId?: number } {
  const err = e as ApiErr
  const d = err.response?.data
  if (d?.message || d?.detail || d?.error) return { texto: (d.message || d.detail || d.error) as string, clienteId: d.cliente_id }
  if (err.response?.status === 403) return { texto: 'Seu acesso não permite emitir nota fiscal.' }
  return { texto: 'Não foi possível emitir a NFS-e agora.' }
}

/**
 * Emissão de NFS-e a partir de uma conta a receber (D.1.3). A NF é sempre
 * derivada de um título a receber — tomador e valor vêm dele —, então o diálogo
 * lista as contas a receber ainda **sem** NFS-e e deixa o usuário ajustar o
 * código de serviço municipal e a descrição antes de emitir. A emissão é
 * assíncrona (enfileira na NFE.io): a nota aparece como "Processando" na aba
 * Emitidas e vira "Emitida"/"Erro" quando a NFE.io responder.
 */
export function EmitirNfseDialog({ open, onClose, onEmitted, contaInicial }: Props) {
  const [contaId, setContaId] = useState<number | ''>('')
  const [cityCode, setCityCode] = useState('010701')
  const [descricao, setDescricao] = useState('')
  const [erro, setErro] = useState<{ texto: string; clienteId?: number } | null>(null)
  const [busca, setBusca] = useState('')

  const emitir = useEmitirNfse()
  // A busca vai ao servidor (cliente, lote, descrição): com dezenas de milhares
  // de contas, uma lista das cem mais recentes não achava quem se procura. Conta
  // com nota recusada continua na lista — o backend deixa reemitir (item 58) e
  // recusa, com frase, quem já tem nota válida.
  const { data, isLoading } = useContasAReceber({ page_size: 50, ordering: '-vencimento', search: busca || undefined })
  const inicial = useContaAReceber(contaInicial).data
  const contas = useMemo(() => {
    const lista = (data?.results ?? []).filter(c => c.status !== 'CANCELADO')
    return inicial && !lista.some(c => c.conta_receber_id === inicial.conta_receber_id) ? [inicial, ...lista] : lista
  }, [data, inicial])

  // Zera o formulário **só ao abrir**. Antes o mesmo efeito dependia de
  // `emitir.isPending` e de `onClose` (uma função nova a cada render do pai):
  // quando a API recusava, o fim do "emitindo…" rodava o efeito de novo e apagava
  // a mensagem de erro no mesmo instante — "clico em emitir e nada acontece".
  useEffect(() => {
    if (!open) return
    setContaId(contaInicial ?? '')
    setBusca('')
    setCityCode('010701')
    setDescricao('')
    setErro(null)
  }, [open, contaInicial])

  const ocupado = useRef(false)
  ocupado.current = emitir.isPending
  const fechar = useRef(onClose)
  fechar.current = onClose
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !ocupado.current) fechar.current() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [open])

  if (!open) return null

  function emitirAgora() {
    if (contaId === '') { setErro({ texto: 'Selecione a conta a receber que dará origem à nota.' }); return }
    setErro(null)
    emitir.mutate(
      { contaId: contaId as number, payload: { city_service_code: cityCode || undefined, descricao: descricao || undefined } },
      {
        onSuccess: () => onEmitted('Emissão de NFS-e iniciada. A nota aparece como "Processando" na aba Emitidas e é atualizada quando a API responder.'),
        onError: e => setErro(mensagemDeErro(e)),
      },
    )
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center px-4">
      <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onClick={() => !emitir.isPending && onClose()} aria-hidden="true" />

      <div
        role="dialog"
        aria-modal="true"
        aria-label="Emitir NFS-e"
        className="relative w-full flex flex-col rounded-xl"
        style={{ maxWidth: 480, maxHeight: '85vh', background: '#FFFFFF', boxShadow: 'var(--shadow-lg)', border: '1.5px solid #e2e8f0' }}
      >
        <header className="flex items-start justify-between gap-3 px-5 py-4" style={{ borderBottom: '1.5px solid #e2e8f0' }}>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: '#ede9fe', color: '#6d28d9' }}>
              <ScrollText size={18} />
            </div>
            <h2 className="text-base font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Emitir NFS-e
            </h2>
          </div>
          <button type="button" onClick={() => !emitir.isPending && onClose()} aria-label="Fechar" className="p-1.5 rounded-lg shrink-0"
            style={{ color: 'var(--color-text-muted)', cursor: emitir.isPending ? 'not-allowed' : 'pointer' }}>
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4" style={{ fontFamily: 'var(--font-body)' }}>
          <p className="text-sm mb-4" style={{ color: 'var(--color-text-muted)', lineHeight: 1.5 }}>
            A nota é emitida a partir de uma conta a receber — o tomador e o valor vêm do título.
          </p>

          {!contaInicial && (
            <div className="mb-2">
              <CaixaDeBusca valor={busca} onBuscar={setBusca} buscando={false} placeholder="Buscar conta por cliente, lote ou descrição" />
            </div>
          )}
          <div className="mb-3.5">
            <label style={labelStyle} htmlFor="nfse-conta">Conta a receber</label>
            <select id="nfse-conta" style={selectStyle} value={contaId}
              onChange={e => setContaId(e.target.value ? Number(e.target.value) : '')} disabled={emitir.isPending}>
              <option value="">{isLoading ? 'Carregando…' : 'Selecione…'}</option>
              {contas.map(c => (
                <option key={c.conta_receber_id} value={c.conta_receber_id}>
                  {c.cliente_nome} · {c.descricao} · {formatBRL(apiDecimalToCents(c.valor))} · venc {dateToBR(c.data_vencimento)}
                </option>
              ))}
            </select>
            {!isLoading && contas.length === 0 && (
              <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
                Nenhuma conta encontrada. Mude a busca ou crie a conta em “Contas a receber”.
              </p>
            )}
          </div>

          <div className="mb-3.5">
            <label style={labelStyle} htmlFor="nfse-code">Código de serviço municipal</label>
            <input id="nfse-code" style={inputStyle} value={cityCode} onChange={e => setCityCode(e.target.value)}
              disabled={emitir.isPending} placeholder="010701" />
            <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
              Código do serviço no município do emitente (confira o válido no cadastro da NFE.io).
            </p>
          </div>

          <div className="mb-1">
            <label style={labelStyle} htmlFor="nfse-desc">Descrição do serviço (opcional)</label>
            <textarea id="nfse-desc" style={{ ...inputStyle, minHeight: 64, resize: 'vertical' }} value={descricao}
              onChange={e => setDescricao(e.target.value)} disabled={emitir.isPending}
              placeholder="Se vazio, usa a descrição da conta a receber." />
          </div>

          {erro && (
            <div className="text-sm px-4 py-3 rounded-lg mt-3"
              style={{ background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030' }}>
              {erro.texto}
              {erro.clienteId && (
                <Link to={`/app/clientes/${erro.clienteId}`} className="block mt-1 font-semibold" style={{ color: '#c53030' }}>
                  Abrir o cadastro do cliente →
                </Link>
              )}
            </div>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 px-5 py-3.5" style={{ borderTop: '1.5px solid #e2e8f0', background: '#f8fafc' }}>
          <button type="button" onClick={onClose} disabled={emitir.isPending} style={{ ...buttonSecondaryStyle, opacity: emitir.isPending ? 0.6 : 1 }}>
            Cancelar
          </button>
          <button type="button" onClick={emitirAgora} disabled={emitir.isPending || contaId === ''}
            style={{ ...buttonPrimaryStyle, opacity: emitir.isPending || contaId === '' ? 0.6 : 1, cursor: emitir.isPending ? 'wait' : 'pointer' }}>
            {emitir.isPending ? 'Emitindo…' : 'Emitir NFS-e'}
          </button>
        </footer>
      </div>
    </div>
  )
}
