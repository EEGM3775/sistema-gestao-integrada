import { useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Files, Plus, ScrollText, X } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useQueryClient } from '@tanstack/react-query'
import { BotaoExportar, WizardImportacao } from '@/components/malha'
import { TelaDaGrade } from '../grade/TelaDaGrade'
import { estiloFiltro } from '../grade/estilos'
import { useGrade } from '../grade/useGrade'
import { filtrosDoGrupo } from '../grade/arvore'
import type { ColunaGrade, Filtros, NoGrupo } from '../grade/tipos'
import { Sheet } from '../components/shared/Sheet'
import { MoneyDisplay } from '../components/shared/MoneyDisplay'
import { StatusContaBadge } from '../components/shared/StatusContaBadge'
import { StatusBoletoBadge } from '../components/shared/StatusBoletoBadge'
import { ContaReceberForm } from '../components/forms/ContaReceberForm'
import { DetalheContaReceber } from '../components/DetalheContaReceber'
import { GerarBoletosLoteDialog } from '../components/GerarBoletosLoteDialog'
import { EmitirNotasLoteDialog } from '../components/EmitirNotasLoteDialog'
import { useCreateContaAReceber } from '../hooks/useContasAReceber'
import { useEmpreendimentoOptions } from '../hooks/useEntityOptions'
import { STATUS_CONTA_CONFIG } from '../components/shared/statusConta'
import { apiDecimalToCents } from '@/utils/money'
import { dateToBR, maxCalendarioISO, maxTodayISO, minCalendarioISO } from '@/utils/dates'
import type { ContaReceber } from '../types'

const SITUACOES = [
  { valor: '', rotulo: 'Todas' },
  { valor: 'a_vencer', rotulo: 'A vencer' },
  { valor: 'vencido', rotulo: 'Vencidas' },
  { valor: 'encerrado', rotulo: 'Quitadas e canceladas' },
]

/** Os filtros que um grupo "aberto sozinho" deixa — rótulo para o chip. */
const ROTULO_EXTRA: Record<string, string> = {
  cliente: 'Cliente', quadra: 'Quadra', mes: 'Mês', status: 'Status', faixa: 'Situação', empreendimento: 'Empreendimento',
}

const diasDeAtraso = (venc: string) => Math.floor((Date.parse(maxTodayISO()) - Date.parse(venc)) / 86_400_000)

/**
 * Contas a receber (itens 51, 53 e 54 do dono): a grade de rolagem infinita da
 * carteira de clientes, agora para os títulos. A busca responde enquanto se
 * digita e acha pelo cliente, pelo CPF, pelo empreendimento, pela quadra e pelo
 * lote; toda coluna ordena; "agrupar por" empilha empreendimento, cliente,
 * quadra, mês e situação com os subtotais do banco. Marcar linhas (ou "todas
 * do filtro") leva ao boleto em lote (item 52) e às notas fiscais em lote.
 */
export default function ContasAReceberPage() {
  const [busca, setBusca] = useState('')
  const [situacao, setSituacao] = useState('')
  const [empreendimento, setEmpreendimento] = useState('')
  const [periodo, setPeriodo] = useState({ de: '', ate: '' })
  const [extras, setExtras] = useState<{ chave: string; valor: string; rotulo: string }[]>([])
  const [marcados, setMarcados] = useState<ReadonlySet<number>>(new Set())
  const [todosDoFiltro, setTodosDoFiltro] = useState(false)
  // Em "todas do filtro", as que a pessoa desmarcou uma a uma depois.
  const [excluidos, setExcluidos] = useState<ReadonlySet<number>>(new Set())
  const [aberta, setAberta] = useState<number | null>(null)
  const [criando, setCriando] = useState(false)
  const [loteAberto, setLoteAberto] = useState(false)
  const [notasAbertas, setNotasAbertas] = useState(false)
  const { hasPermission } = useAuth()
  const [tituloSheet, setTituloSheet] = useState<{ titulo: string; descricao?: string }>({ titulo: '' })

  const filtros: Filtros = useMemo(() => ({
    search: busca, faixa: situacao, empreendimento, data_de: periodo.de, data_ate: periodo.ate,
    ...Object.fromEntries(extras.map(e => [e.chave, e.valor])),
  }), [busca, situacao, empreendimento, periodo, extras])

  const grade = useGrade<ContaReceber>({ recurso: 'contas-a-receber', filtros, ordenarPadrao: 'vencimento' })
  const empreendimentos = useEmpreendimentoOptions(true)
  const qc = useQueryClient()
  const criar = useCreateContaAReceber()

  const desmarcarTudo = () => { setMarcados(new Set()); setTodosDoFiltro(false); setExcluidos(new Set()) }
  const mudarFiltro = (f: () => void) => { f(); desmarcarTudo() }

  const abrirSoOGrupo = (no: NoGrupo) => {
    const f = filtrosDoGrupo({}, no)
    mudarFiltro(() => {
      setExtras(atual => [
        ...atual.filter(e => !(e.chave in f)),
        ...no.filtros.map((chave, i) => ({ chave, valor: no.chaves[i], rotulo: `${ROTULO_EXTRA[chave] ?? chave}: ${no.rotulos[i]}` })),
      ])
      grade.setNiveis([])
    })
  }

  const trocar = (id: number) => (atual: ReadonlySet<number>) => {
    const prox = new Set(atual)
    if (prox.has(id)) prox.delete(id)
    else prox.add(id)
    return prox
  }
  const podeMarcar = (c: ContaReceber) => c.status === 'ABERTO' || c.status === 'PARCIAL'
  const alternar = (c: ContaReceber) => {
    if (todosDoFiltro) setExcluidos(trocar(c.conta_receber_id))
    else setMarcados(trocar(c.conta_receber_id))
  }
  const marcada = (c: ContaReceber) => (todosDoFiltro
    ? podeMarcar(c) && !excluidos.has(c.conta_receber_id)
    : marcados.has(c.conta_receber_id))
  const marcarTodasDoFiltro = () => { setMarcados(new Set()); setExcluidos(new Set()); setTodosDoFiltro(true) }

  const colunas = useMemo<ColunaGrade<ContaReceber>[]>(() => [
    {
      chave: 'cliente', titulo: 'Cliente', largura: 230, ordenar: 'cliente',
      render: c => (
        <span className="flex flex-col min-w-0">
          <Link to={`/app/clientes/${c.cliente}`} onClick={e => e.stopPropagation()} className="truncate font-semibold"
            style={{ color: 'var(--ink)', textDecoration: 'none' }} title="Abrir a ficha do cliente">
            {c.cliente_nome}
          </Link>
        </span>
      ),
      texto: c => c.cliente_nome,
    },
    { chave: 'descricao', titulo: 'Parcela', largura: 210, ordenar: 'descricao', render: c => <span className="truncate" title={c.descricao}>{c.descricao}</span>, texto: c => c.descricao },
    { chave: 'empreendimento', titulo: 'Empreendimento', largura: 190, ordenar: 'empreendimento', render: c => <span className="truncate">{c.empreendimento_nome || '—'}</span>, texto: c => c.empreendimento_nome },
    { chave: 'unidade', titulo: 'Unidade', largura: 120, ordenar: 'unidade', tipo: 'endereco', render: c => c.unidade || '—', texto: c => c.unidade },
    {
      chave: 'vencimento', titulo: 'Vencimento', largura: 150, ordenar: 'vencimento', tipo: 'data',
      render: c => {
        const atraso = (c.status === 'ABERTO' || c.status === 'PARCIAL') ? diasDeAtraso(c.data_vencimento) : 0
        return (
          <span className="flex flex-col">
            <span>{dateToBR(c.data_vencimento)}</span>
            {atraso > 0 && <span style={{ fontSize: 11, color: 'var(--danger-ink)', fontWeight: 600 }}>{atraso} dia{atraso !== 1 ? 's' : ''} de atraso</span>}
          </span>
        )
      },
      texto: c => dateToBR(c.data_vencimento),
    },
    { chave: 'valor', titulo: 'Valor', largura: 120, ordenar: 'valor', tipo: 'numero', alinhamento: 'right', render: c => <MoneyDisplay cents={apiDecimalToCents(c.valor)} />, texto: c => c.valor },
    { chave: 'saldo', titulo: 'Em aberto', largura: 120, ordenar: 'saldo', tipo: 'numero', alinhamento: 'right', render: c => <MoneyDisplay cents={apiDecimalToCents(c.saldo_aberto)} />, texto: c => c.saldo_aberto },
    {
      chave: 'status', titulo: 'Situação', largura: 170, ordenar: 'status',
      render: c => {
        const b = c.boletos.find(x => ['EMITIDO', 'VENCIDO', 'AGUARDANDO', 'ERRO'].includes(x.status))
        return (
          <span className="flex items-center gap-1.5">
            <StatusContaBadge status={c.status} />
            {b && <StatusBoletoBadge status={b.status} />}
          </span>
        )
      },
      texto: c => STATUS_CONTA_CONFIG[c.status]?.label ?? c.status,
    },
  ], [])

  const doFiltro = grade.totais?.contagem ?? 0
  const selecionadas = todosDoFiltro ? Math.max(0, doFiltro - excluidos.size) : marcados.size
  const temFiltroAtivo = Boolean(busca || situacao || empreendimento || periodo.de || periodo.ate || extras.length)
  const estadoTodas = todosDoFiltro
    ? (excluidos.size ? 'algumas' : 'todas')
    : (marcados.size ? 'algumas' : 'nenhuma')
  const fecharSheet = useCallback(() => { setAberta(null); setCriando(false) }, [])
  const definirTitulo = useCallback((titulo: string, descricao?: string) => setTituloSheet({ titulo, descricao }), [])

  return (
    <>
      <TelaDaGrade<ContaReceber>
        titulo="Contas a receber"
        subtitulo="Parcelas, boletos e recebimentos — busque por cliente, CPF, empreendimento, quadra, lote ou parcela"
        acoes={
          <>
            {/* Planilha: sai o recorte da grade (R7); entra só título novo, em aberto. */}
            <BotaoExportar tam="md" recurso="erp.conta_receber" recorte={filtros} />
            <WizardImportacao tam="md" recurso="erp.conta_receber" onConcluida={() => qc.invalidateQueries({ queryKey: ['erp'] })} />
            {selecionadas > 0 && (
              <button type="button" onClick={() => setLoteAberto(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
                style={{ background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer' }}>
                <Files size={16} /> Gerar boletos ({selecionadas.toLocaleString('pt-BR')})
              </button>
            )}
            {selecionadas > 0 && hasPermission('erp.nf.emitir') && (
              <button type="button" onClick={() => setNotasAbertas(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
                style={{ background: 'var(--surface)', color: 'var(--accent-ink)', border: '1.5px solid var(--accent)', cursor: 'pointer' }}>
                <ScrollText size={16} /> Emitir notas ({selecionadas.toLocaleString('pt-BR')})
              </button>
            )}
            <button type="button" onClick={() => setCriando(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
              style={{ background: 'var(--brand)', color: '#fff', border: 'none', cursor: 'pointer' }}>
              <Plus size={16} /> Nova conta
            </button>
          </>
        }
        busca={busca}
        onBuscar={t => mudarFiltro(() => setBusca(t))}
        placeholderBusca="Buscar por cliente, CPF, empreendimento, quadra, lote ou parcela"
        situacoes={SITUACOES}
        situacao={situacao}
        onSituacao={v => mudarFiltro(() => setSituacao(v))}
        filtros={
          <>
            <select aria-label="Empreendimento" value={empreendimento} style={estiloFiltro}
              onChange={e => mudarFiltro(() => setEmpreendimento(e.target.value))}>
              <option value="">Todos os empreendimentos</option>
              {(empreendimentos.data ?? []).map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
            <span className="flex items-center gap-1.5" style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
              Vencimento
              <input type="date" aria-label="Vencimento de" min={minCalendarioISO} max={maxCalendarioISO} value={periodo.de} style={estiloFiltro}
                onChange={e => mudarFiltro(() => setPeriodo(p => ({ ...p, de: e.target.value })))} />
              até
              <input type="date" aria-label="Vencimento até" min={minCalendarioISO} max={maxCalendarioISO} value={periodo.ate} style={estiloFiltro}
                onChange={e => mudarFiltro(() => setPeriodo(p => ({ ...p, ate: e.target.value })))} />
            </span>
            {extras.map(e => (
              <span key={e.chave} className="flex items-center gap-1" style={{ padding: '3px 6px 3px 10px', borderRadius: 999, background: 'var(--surface-2)', fontSize: 12, fontWeight: 600, color: 'var(--ink-2)' }}>
                {e.rotulo}
                <button type="button" aria-label={`Tirar o filtro ${e.rotulo}`} onClick={() => mudarFiltro(() => setExtras(x => x.filter(y => y.chave !== e.chave)))}
                  style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'inherit', display: 'flex', padding: 0 }}><X size={13} /></button>
              </span>
            ))}
            {temFiltroAtivo && (
              <button type="button" onClick={() => mudarFiltro(() => { setBusca(''); setSituacao(''); setEmpreendimento(''); setPeriodo({ de: '', ate: '' }); setExtras([]) })}
                style={{ border: 'none', background: 'none', color: 'var(--ink-3)', fontSize: 12.5, cursor: 'pointer' }}>
                Limpar filtros
              </button>
            )}
          </>
        }
        grade={grade}
        colunas={colunas}
        onAbrir={c => setAberta(c.conta_receber_id)}
        onAbrirSoOGrupo={abrirSoOGrupo}
        selecao={{
          marcada, alternar, podeMarcar,
          todas: {
            estado: estadoTodas,
            habilitada: estadoTodas !== 'nenhuma' || (doFiltro > 0 && temFiltroAtivo),
            dica: estadoTodas !== 'nenhuma'
              ? 'Desmarcar todas'
              : temFiltroAtivo
                ? `Marcar todas as ${doFiltro.toLocaleString('pt-BR')} contas do filtro`
                : 'Filtre a lista (busca, situação, empreendimento ou período) para marcar todas de uma vez',
            alternar: () => (estadoTodas === 'nenhuma' ? marcarTodasDoFiltro() : desmarcarTudo()),
          },
        }}
        extraTotais={
          <span className="flex items-center gap-2" style={{ fontSize: 12.5 }}>
            {marcados.size > 0 && !todosDoFiltro && <span>{marcados.size} marcada{marcados.size !== 1 ? 's' : ''}</span>}
            {todosDoFiltro && (
              <span>
                Todas as {doFiltro.toLocaleString('pt-BR')} do filtro marcadas
                {excluidos.size > 0 && `, menos ${excluidos.size}`}
              </span>
            )}
            {!todosDoFiltro && doFiltro > 0 && temFiltroAtivo && (
              <button type="button" onClick={marcarTodasDoFiltro}
                style={{ border: 'none', background: 'none', color: 'var(--accent-ink)', fontWeight: 600, cursor: 'pointer', fontSize: 12.5 }}>
                Marcar todas do filtro
              </button>
            )}
            {(marcados.size > 0 || todosDoFiltro) && (
              <button type="button" onClick={desmarcarTudo}
                style={{ border: 'none', background: 'none', color: 'var(--ink-3)', cursor: 'pointer', fontSize: 12.5 }}>
                Desmarcar
              </button>
            )}
          </span>
        }
        substantivo={['conta', 'contas']}
        mostrarSaldo
        vazio={temFiltroAtivo ? 'Nenhuma conta para esta busca. Tente outra palavra ou limpe os filtros.' : 'Nenhuma conta a receber lançada.'}
      />

      <Sheet open={aberta != null || criando} onClose={fecharSheet} width={580}
        title={criando ? 'Nova conta a receber' : tituloSheet.titulo} description={criando ? undefined : tituloSheet.descricao}>
        {criando && (
          <ContaReceberForm onCancel={fecharSheet}
            onSubmit={async payload => { await criar.mutateAsync(payload); fecharSheet() }} />
        )}
        {aberta != null && <DetalheContaReceber key={aberta} contaId={aberta} onTitulo={definirTitulo} />}
      </Sheet>

      {loteAberto && (
        <GerarBoletosLoteDialog
          quantidade={selecionadas}
          escolha={todosDoFiltro
            ? { todos_do_filtro: true, filtros, excluir_ids: [...excluidos] }
            : { ids: [...marcados] }}
          onFechar={() => { setLoteAberto(false); desmarcarTudo() }}
        />
      )}
      {notasAbertas && (
        <EmitirNotasLoteDialog
          quantidade={selecionadas}
          escolha={todosDoFiltro
            ? { todos_do_filtro: true, filtros, excluir_ids: [...excluidos] }
            : { ids: [...marcados] }}
          onFechar={emitiu => { setNotasAbertas(false); if (emitiu) desmarcarTudo() }}
        />
      )}
    </>
  )
}

