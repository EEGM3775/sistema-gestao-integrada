import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Ban, Building2, FileText } from 'lucide-react'
import { TelaDaGrade } from '../grade/TelaDaGrade'
import { BotaoExportar } from '@/components/malha'
import { estiloFiltro } from '../grade/estilos'
import { useGrade } from '../grade/useGrade'
import { filtrosDoGrupo } from '../grade/arvore'
import type { ColunaGrade, Filtros, NoGrupo } from '../grade/tipos'
import { MoneyDisplay } from '../components/shared/MoneyDisplay'
import { StatusBoletoBadge } from '../components/shared/StatusBoletoBadge'
import { BotaoErroGateway } from '../components/shared/GatewayErro'
import { LeitorDeBoleto } from '../components/BoletoNaTela'
import { useCancelarBoleto } from '../hooks/useBoletos'
import { useEmpreendimentoOptions } from '../hooks/useEntityOptions'
import { apiDecimalToCents } from '@/utils/money'
import { dateToBR } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import type { BoletoLista } from '../types'

type Aba = 'ativos' | 'pagos' | 'cancelados'
const ABAS: { id: Aba; rotulo: string; filtro: Filtros }[] = [
  { id: 'ativos', rotulo: 'Em aberto', filtro: { excluir_status: 'CANCELADO' } },
  { id: 'pagos', rotulo: 'Pagos', filtro: { status: 'PAGO' } },
  { id: 'cancelados', rotulo: 'Cancelados', filtro: { status: 'CANCELADO' } },
]

/**
 * Boletos (item 54 do dono): antes, a lista dizia "Conta a receber #172000" e
 * mais nada. Agora cada boleto diz de quem é, de qual parcela, de qual
 * empreendimento e lote, e por onde foi emitido (Asaas ou banco) — com a busca,
 * a ordem e o agrupamento da grade das contas.
 */
export default function BoletosListPage() {
  const navigate = useNavigate()
  const [aba, setAba] = useState<Aba>('ativos')
  const [busca, setBusca] = useState('')
  const [empreendimento, setEmpreendimento] = useState('')
  const [lendo, setLendo] = useState<BoletoLista | null>(null)
  const [aviso, setAviso] = useState<{ tom: 'ok' | 'erro'; texto: string } | null>(null)
  const [grupoAberto, setGrupoAberto] = useState<Filtros>({})
  const cancelar = useCancelarBoleto()
  const empreendimentos = useEmpreendimentoOptions(true)

  const filtros: Filtros = useMemo(() => ({
    ...ABAS.find(a => a.id === aba)!.filtro, search: busca, empreendimento, ...grupoAberto,
  }), [aba, busca, empreendimento, grupoAberto])
  const grade = useGrade<BoletoLista>({ recurso: 'boletos', filtros, ordenarPadrao: '-vencimento' })

  const aoCancelar = (b: BoletoLista) => {
    if (!window.confirm(`Cancelar o boleto de ${b.pessoa_nome} (${dateToBR(b.data_vencimento)})? O cancelamento na API não se desfaz.`)) return
    cancelar.mutate(b.boleto_id, {
      onSuccess: r => setAviso({ tom: 'ok', texto: r.detail }),
      onError: e => setAviso({ tom: 'erro', texto: parseApiErrors(e)._form ?? 'Não foi possível cancelar o boleto agora.' }),
    })
  }

  const colunas = useMemo<ColunaGrade<BoletoLista>[]>(() => [
    {
      chave: 'cliente', titulo: 'Pagador', largura: 220, ordenar: 'cliente',
      render: b => b.cliente_id
        ? <Link to={`/app/clientes/${b.cliente_id}`} onClick={e => e.stopPropagation()} className="truncate font-semibold" style={{ color: 'var(--ink)', textDecoration: 'none' }}>{b.pessoa_nome}</Link>
        : <span className="truncate font-semibold" style={{ color: 'var(--ink)' }}>{b.pessoa_nome || '—'}</span>,
      texto: b => b.pessoa_nome,
    },
    { chave: 'parcela', titulo: 'Parcela', largura: 210, render: b => <span className="truncate" title={b.conta_descricao}>{b.conta_descricao || '—'}</span>, texto: b => b.conta_descricao },
    { chave: 'empreendimento', titulo: 'Empreendimento', largura: 180, ordenar: 'empreendimento', render: b => <span className="truncate">{b.empreendimento_nome || '—'}</span>, texto: b => b.empreendimento_nome },
    { chave: 'unidade', titulo: 'Unidade', largura: 110, ordenar: 'unidade', tipo: 'endereco', render: b => b.unidade || '—', texto: b => b.unidade },
    { chave: 'vencimento', titulo: 'Vencimento', largura: 110, ordenar: 'vencimento', tipo: 'data', render: b => dateToBR(b.data_vencimento), texto: b => dateToBR(b.data_vencimento) },
    { chave: 'valor', titulo: 'Valor', largura: 120, ordenar: 'valor', tipo: 'numero', alinhamento: 'right', render: b => <MoneyDisplay cents={apiDecimalToCents(b.valor)} />, texto: b => b.valor },
    { chave: 'canal', titulo: 'Emitido por', largura: 110, render: b => (b.canal === 'cnab' ? 'Banco (CNAB)' : 'Asaas'), texto: b => b.canal },
    {
      chave: 'status', titulo: 'Situação', largura: 130, ordenar: 'status',
      render: b => (b.status === 'ERRO'
        ? <span onClick={e => e.stopPropagation()}><BotaoErroGateway dados={b.dados_retorno_api} titulo="Erro na cobrança" /></span>
        : <StatusBoletoBadge status={b.status} />),
      texto: b => b.status,
    },
    {
      chave: 'acoes', titulo: '', largura: 96,
      render: b => (
        <span className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
          <button type="button" title="Ver o boleto" aria-label="Ver o boleto" onClick={() => setLendo(b)}
            disabled={!(b.gateway_id || b.linha_digitavel)} style={botaoIcone}><FileText size={14} /></button>
          {b.canal === 'asaas' && ['EMITIDO', 'VENCIDO', 'AGUARDANDO'].includes(b.status) && (
            <button type="button" title="Cancelar no Asaas" aria-label="Cancelar no Asaas" onClick={() => aoCancelar(b)}
              style={{ ...botaoIcone, color: 'var(--danger-ink)' }}><Ban size={14} /></button>
          )}
        </span>
      ),
      texto: () => '',
    },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [])

  const abrirSoOGrupo = (no: NoGrupo) => { setGrupoAberto(g => ({ ...g, ...filtrosDoGrupo({}, no) })); grade.setNiveis([]) }

  return (
    <>
      <TelaDaGrade<BoletoLista>
        titulo="Boletos"
        subtitulo="Cobranças emitidas pelo Asaas e pelo banco — de quem é, de qual parcela e de qual lote"
        acoes={
          <>
          {/* Boleto é emissão no Asaas/banco: só exporta (dono, 15/10/2026). */}
          <BotaoExportar tam="md" recurso="erp.boleto" recorte={filtros} />
          <Link to="/app/erp/cobranca-bancaria" className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
            style={{ border: '1.5px solid var(--line)', color: 'var(--ink-2)', textDecoration: 'none' }}>
            <Building2 size={16} /> Cobrança bancária (CNAB)
          </Link>
          </>
        }
        abas={
          <div className="flex items-center gap-1 mb-3" style={{ borderBottom: '1px solid var(--line)' }}>
            {ABAS.map(a => (
              <button key={a.id} type="button" onClick={() => { setAba(a.id); setGrupoAberto({}) }}
                style={{
                  padding: '8px 14px', fontSize: 13, fontWeight: 600, background: 'none', border: 'none', cursor: 'pointer',
                  color: aba === a.id ? 'var(--ink)' : 'var(--ink-3)', borderBottom: `2px solid ${aba === a.id ? 'var(--accent)' : 'transparent'}`, marginBottom: -1,
                }}>
                {a.rotulo}
              </button>
            ))}
          </div>
        }
        busca={busca}
        onBuscar={setBusca}
        placeholderBusca="Buscar por cliente, CPF, parcela, lote ou linha digitável"
        filtros={
          <>
            <select aria-label="Empreendimento" value={empreendimento} style={estiloFiltro} onChange={e => setEmpreendimento(e.target.value)}>
              <option value="">Todos os empreendimentos</option>
              {(empreendimentos.data ?? []).map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
            {Object.keys(grupoAberto).length > 0 && (
              <button type="button" onClick={() => setGrupoAberto({})} style={{ border: 'none', background: 'none', color: 'var(--ink-3)', fontSize: 12.5, cursor: 'pointer' }}>
                Voltar a todos os grupos
              </button>
            )}
          </>
        }
        extraTotais={aviso && (
          <span style={{ color: aviso.tom === 'erro' ? 'var(--danger-ink)' : 'var(--good-ink)' }}>{aviso.texto}</span>
        )}
        grade={grade}
        colunas={colunas}
        onAbrir={b => navigate(`/app/erp/boletos/${b.boleto_id}`)}
        onAbrirSoOGrupo={abrirSoOGrupo}
        substantivo={['boleto', 'boletos']}
        mostrarSaldo={false}
        vazio={busca ? 'Nenhum boleto para esta busca.' : 'Nenhum boleto aqui. Gere boletos a partir de Contas a receber.'}
      />
      {lendo && <LeitorDeBoleto boleto={lendo} onFechar={() => setLendo(null)} />}
    </>
  )
}

const botaoIcone = {
  border: '1px solid var(--line)', background: 'var(--surface)', borderRadius: 'var(--r-sm)', padding: 5,
  cursor: 'pointer', color: 'var(--ink-3)', display: 'flex',
} as const
