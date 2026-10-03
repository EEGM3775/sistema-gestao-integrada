import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { FileText, Loader2, ScrollText } from 'lucide-react'
import { erpKeys } from '../api/queryKeys'
import { fetchContaAReceber } from '../api/endpoints/contasAReceber'
import { useDarBaixaContaAReceber, useUpdateContaAReceber } from '../hooks/useContasAReceber'
import { useEstornarBaixa, useGerarCobranca } from '../hooks/useCobranca'
import { MoneyDisplay } from './shared/MoneyDisplay'
import { StatusContaBadge } from './shared/StatusContaBadge'
import { StatusBoletoBadge } from './shared/StatusBoletoBadge'
import { BotaoErroGateway } from './shared/GatewayErro'
import { ContaReceberForm } from './forms/ContaReceberForm'
import { BaixaForm } from './forms/BaixaForm'
import { buttonPrimaryStyle, buttonSecondaryStyle } from './forms/formStyles'
import { BoletoNaTela } from './BoletoNaTela'
import { GerarCobrancaDialog } from './GerarCobrancaDialog'
import { EstornarBaixaDialog } from './EstornarBaixaDialog'
import { EmitirNfseDialog } from './EmitirNfseDialog'
import { apiDecimalToCents } from '@/utils/money'
import { dateToBR, maxTodayISO } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import type { Boleto } from '../types'

const ATIVOS = ['EMITIDO', 'VENCIDO', 'AGUARDANDO']
/** Quanto tempo a tela espera o boleto aparecer antes de dizer para conferir depois. */
const ESPERA_DO_BOLETO_MS = 60_000

type Modo = 'ver' | 'editar' | 'baixa'

/**
 * A conta a receber no painel lateral — lida **ao vivo**, não a cópia da linha
 * clicada. Era a cópia que fazia o item 56 do dono: gerada a cobrança, a lista
 * se atualizava, mas o painel continuava mostrando a conta de antes (sem boleto,
 * botão ativo). Agora, pedida a cobrança, o painel acompanha até o boleto
 * chegar e o mostra aqui mesmo.
 */
export function DetalheContaReceber({ contaId, modoInicial = 'ver', onTitulo }: {
  contaId: number
  modoInicial?: Modo
  onTitulo: (titulo: string, descricao?: string) => void
}) {
  const [modo, setModo] = useState<Modo>(modoInicial)
  const [aguardandoDesde, setAguardandoDesde] = useState<number | null>(null)
  const [boletosAntes, setBoletosAntes] = useState(0)
  const [cobrando, setCobrando] = useState(false)
  const [estornando, setEstornando] = useState(false)
  const [emitindoNota, setEmitindoNota] = useState(false)
  const [aviso, setAviso] = useState<{ tom: 'ok' | 'erro'; texto: string } | null>(null)

  const consulta = useQuery({
    queryKey: erpKeys.contasAReceber.detail(contaId),
    queryFn: () => fetchContaAReceber(contaId),
    refetchInterval: aguardandoDesde ? 2000 : false,
  })
  const conta = consulta.data
  const atualizar = useUpdateContaAReceber()
  const baixa = useDarBaixaContaAReceber()
  const cobrar = useGerarCobranca()
  const estornar = useEstornarBaixa('receber')

  useEffect(() => {
    if (conta) onTitulo(modo === 'editar' ? 'Editar conta a receber' : modo === 'baixa' ? 'Dar baixa' : conta.descricao, conta.cliente_nome)
  }, [conta, modo, onTitulo])

  // O boleto chegou (ou o relógio passou): para de consultar.
  useEffect(() => {
    if (!aguardandoDesde || !conta) return
    if (conta.boletos.length > boletosAntes) {
      setAguardandoDesde(null)
      const novo = conta.boletos[0]
      setAviso(novo?.status === 'ERRO'
        ? { tom: 'erro', texto: 'O Asaas recusou a cobrança. Veja o motivo no boleto abaixo.' }
        : { tom: 'ok', texto: 'Boleto emitido.' })
    } else if (Date.now() - aguardandoDesde > ESPERA_DO_BOLETO_MS) {
      setAguardandoDesde(null)
      setAviso({ tom: 'ok', texto: 'O Asaas ainda não respondeu. O boleto aparece aqui e em Boletos assim que chegar.' })
    }
  }, [conta, aguardandoDesde, boletosAntes])

  if (!conta) {
    return <p className="flex items-center gap-2 text-sm" style={{ color: 'var(--ink-3)' }}><Loader2 size={15} className="animate-spin" /> Carregando…</p>
  }

  if (modo === 'editar') {
    return <ContaReceberForm initial={conta} onCancel={() => setModo('ver')}
      onSubmit={async payload => {
        await atualizar.mutateAsync({ id: conta.conta_receber_id, payload })
        setModo('ver')
        // Valor ou vencimento mudou com boleto vivo: o boleto novo está a caminho.
        if (payload.atualizar_boleto) { setAviso(null); setBoletosAntes(conta.boletos.length); setAguardandoDesde(Date.now()) }
      }} />
  }
  if (modo === 'baixa') {
    return <BaixaForm saldoAberto={conta.saldo_aberto} onCancel={() => setModo('ver')}
      onSubmit={async payload => { await baixa.mutateAsync({ id: conta.conta_receber_id, payload }); setModo('ver') }} />
  }

  const aberta = conta.status === 'ABERTO' || conta.status === 'PARCIAL'
  const ativo = conta.boletos.find(b => ATIVOS.includes(b.status) && (b.gateway_id || b.canal === 'cnab'))
  const hoje = maxTodayISO()
  const ativoValido = ativo && ativo.data_vencimento >= hoje
  const vencida = conta.data_vencimento < hoje
  const outros = conta.boletos.filter(b => b !== ativo)

  const pedirCobranca = (vencimento?: string) => {
    setAviso(null)
    cobrar.mutate({ contaId: conta.conta_receber_id, vencimento }, {
      onSuccess: () => { setCobrando(false); setBoletosAntes(conta.boletos.length); setAguardandoDesde(Date.now()) },
      onError: e => { setCobrando(false); setAviso({ tom: 'erro', texto: parseApiErrors(e)._form ?? 'Não foi possível gerar o boleto.' }) },
    })
  }

  return (
    <div className="flex flex-col gap-5 text-sm" style={{ color: 'var(--ink-2)' }}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <StatusContaBadge status={conta.status} />
        <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>
          {conta.empreendimento_nome}{conta.unidade ? ` · ${conta.unidade}` : ''}
        </span>
      </div>

      {conta.cliente && (
        <Link to={`/app/clientes/${conta.cliente}`} className="font-semibold" style={{ color: 'var(--accent-ink)', textDecoration: 'none' }}>
          {conta.cliente_nome} — abrir a ficha do cliente →
        </Link>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Item rotulo="Valor" valor={<MoneyDisplay cents={apiDecimalToCents(conta.valor)} />} />
        <Item rotulo="Saldo em aberto" valor={<MoneyDisplay cents={apiDecimalToCents(conta.saldo_aberto)} />} />
        <Item rotulo="Vencimento" valor={<span style={{ color: vencida && aberta ? 'var(--danger-ink)' : undefined }}>{dateToBR(conta.data_vencimento)}{vencida && aberta ? ' · vencida' : ''}</span>} />
        <Item rotulo="Recebido em" valor={conta.data_recebimento ? dateToBR(conta.data_recebimento) : '—'} />
        {(Number(conta.multa) > 0 || Number(conta.juros) > 0) && (
          <Item rotulo="Multa e juros recebidos" valor={<MoneyDisplay cents={apiDecimalToCents(conta.multa) + apiDecimalToCents(conta.juros)} />} />
        )}
      </dl>

      {conta.rateios.length > 0 && (
        <Secao titulo="Rateio por centro de custo">
          <ul className="flex flex-col gap-1">
            {conta.rateios.map(r => (
              <li key={r.rateio_id} className="flex justify-between"><span>{r.centro_custo_nome}</span><MoneyDisplay cents={apiDecimalToCents(r.valor)} /></li>
            ))}
          </ul>
        </Secao>
      )}

      <Secao titulo="Boleto">
        {aguardandoDesde && (
          <p className="flex items-center gap-2" style={{ color: 'var(--ink-3)' }}><Loader2 size={15} className="animate-spin" /> Pedindo o boleto ao Asaas…</p>
        )}
        {ativo ? <BoletoNaTela boleto={ativo} desatualizado={conta.boleto_desatualizado} /> : !aguardandoDesde && (
          <p style={{ color: 'var(--ink-3)' }}>{aberta ? 'Nenhum boleto válido para esta conta.' : 'Conta encerrada.'}</p>
        )}
        {outros.length > 0 && <HistoricoDeBoletos boletos={outros} />}
      </Secao>

      {aviso && (
        <p role={aviso.tom === 'erro' ? 'alert' : 'status'}
          style={{ padding: '8px 12px', borderRadius: 'var(--r-md)', background: aviso.tom === 'erro' ? 'var(--danger-soft)' : 'var(--good-soft)', color: aviso.tom === 'erro' ? 'var(--danger-ink)' : 'var(--good-ink)' }}>
          {aviso.texto}
        </p>
      )}

      {conta.estorno_impedido_porque && Number(conta.valor_pago) > 0 && (
        <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>{conta.estorno_impedido_porque}</p>
      )}

      <div className="flex items-center justify-end gap-2 flex-wrap pt-1">
        {conta.pode_estornar && !conta.estorno_impedido_porque && (
          <button type="button" onClick={() => setEstornando(true)} style={buttonSecondaryStyle}>Estornar baixa</button>
        )}
        <button type="button" onClick={() => setModo('editar')} style={buttonSecondaryStyle}>Editar</button>
        <button type="button" onClick={() => setEmitindoNota(true)} className="flex items-center gap-1.5" style={buttonSecondaryStyle}>
          <ScrollText size={14} /> Nota fiscal
        </button>
        {aberta && (!ativoValido || conta.boleto_desatualizado) && (
          <button type="button" onClick={() => setCobrando(true)} disabled={cobrar.isPending || Boolean(aguardandoDesde)}
            className="flex items-center gap-1.5"
            style={{ ...buttonSecondaryStyle, opacity: cobrar.isPending || aguardandoDesde ? 0.6 : 1 }}>
            <FileText size={14} /> {conta.boleto_desatualizado ? 'Emitir boleto atualizado' : vencida ? 'Emitir segunda via' : 'Gerar boleto'}
          </button>
        )}
        {aberta && <button type="button" onClick={() => setModo('baixa')} style={buttonPrimaryStyle}>Dar baixa</button>}
      </div>

      <GerarCobrancaDialog open={cobrando} contaId={conta.conta_receber_id} pending={cobrar.isPending}
        onClose={() => setCobrando(false)} onConfirm={pedirCobranca} />
      {estornando && (
        <EstornarBaixaDialog valorPago={conta.valor_pago} pendente={estornar.isPending} onFechar={() => setEstornando(false)}
          onConfirmar={motivo => estornar.mutateAsync({ id: conta.conta_receber_id, motivo })} />
      )}
      <EmitirNfseDialog open={emitindoNota} contaInicial={conta.conta_receber_id} onClose={() => setEmitindoNota(false)}
        onEmitted={msg => { setEmitindoNota(false); setAviso({ tom: 'ok', texto: msg }) }} />
    </div>
  )
}

function HistoricoDeBoletos({ boletos }: { boletos: Boleto[] }) {
  return (
    <details className="mt-2">
      <summary style={{ cursor: 'pointer', fontSize: 12, color: 'var(--ink-3)' }}>Boletos anteriores ({boletos.length})</summary>
      <ul className="flex flex-col gap-1.5 mt-2">
        {boletos.map(b => (
          <li key={b.boleto_id} className="flex items-center justify-between gap-2">
            <Link to={`/app/erp/boletos/${b.boleto_id}`} style={{ color: 'var(--ink-2)' }}>{dateToBR(b.data_vencimento)}</Link>
            {b.status === 'ERRO' ? <BotaoErroGateway dados={b.dados_retorno_api} titulo="Erro na cobrança" /> : <StatusBoletoBadge status={b.status} />}
            <MoneyDisplay cents={apiDecimalToCents(b.valor)} />
          </li>
        ))}
      </ul>
    </details>
  )
}

function Secao({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: 'var(--ink-3)', letterSpacing: '0.06em' }}>{titulo}</h3>
      {children}
    </div>
  )
}

function Item({ rotulo, valor }: { rotulo: string; valor: ReactNode }) {
  return (
    <div>
      <dt className="text-xs" style={{ color: 'var(--ink-3)' }}>{rotulo}</dt>
      <dd className="font-medium" style={{ color: 'var(--ink)' }}>{valor}</dd>
    </div>
  )
}

