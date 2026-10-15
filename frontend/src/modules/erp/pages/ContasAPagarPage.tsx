import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Plus, X } from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BotaoExportar, WizardImportacao } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { TelaDaGrade } from '../grade/TelaDaGrade'
import { estiloFiltro } from '../grade/estilos'
import { useGrade } from '../grade/useGrade'
import { filtrosDoGrupo } from '../grade/arvore'
import type { ColunaGrade, Filtros, NoGrupo } from '../grade/tipos'
import { Sheet } from '../components/shared/Sheet'
import { MoneyDisplay } from '../components/shared/MoneyDisplay'
import { StatusContaBadge } from '../components/shared/StatusContaBadge'
import { STATUS_CONTA_CONFIG } from '../components/shared/statusConta'
import { ContaPagarForm } from '../components/forms/ContaPagarForm'
import { BaixaForm } from '../components/forms/BaixaForm'
import { AvisoDeTrava } from '../components/forms/trava'
import { buttonPrimaryStyle, buttonSecondaryStyle } from '../components/forms/formStyles'
import { EstornarBaixaDialog } from '../components/EstornarBaixaDialog'
import { erpKeys } from '../api/queryKeys'
import { anotarContaAPagar, fetchContaAPagar } from '../api/endpoints/contasAPagar'
import { useCreateContaAPagar, useDarBaixaContaAPagar, useUpdateContaAPagar } from '../hooks/useContasAPagar'
import { useEstornarBaixa } from '../hooks/useCobranca'
import { useEmpreendimentoOptions } from '../hooks/useEntityOptions'
import { apiDecimalToCents } from '@/utils/money'
import { dateToBR, maxCalendarioISO, maxTodayISO, minCalendarioISO } from '@/utils/dates'
import type { ContaPagar } from '../types'

const SITUACOES = [
  { valor: '', rotulo: 'Todas' },
  { valor: 'a_vencer', rotulo: 'A vencer' },
  { valor: 'vencido', rotulo: 'Vencidas' },
  { valor: 'encerrado', rotulo: 'Pagas e canceladas' },
]
const ROTULO_EXTRA: Record<string, string> = { fornecedor: 'Fornecedor', mes: 'Mês', status: 'Status', faixa: 'Situação', empreendimento: 'Empreendimento', obra: 'Obra' }

/**
 * Contas a pagar — a mesma grade de Contas a receber (itens 51/53): busca por
 * fornecedor, CNPJ, descrição, empreendimento e nota; toda coluna ordena;
 * agrupa por fornecedor, empreendimento, mês e situação. Conta paga continua
 * editável no que é descrição; o financeiro destrava pelo estorno (item 57).
 */
export default function ContasAPagarPage() {
  const [busca, setBusca] = useState('')
  const [situacao, setSituacao] = useState('')
  const [empreendimento, setEmpreendimento] = useState('')
  const [periodo, setPeriodo] = useState({ de: '', ate: '' })
  // A DRE da obra abre esta grade já filtrada (`?obra=&obra_nome=`, D.1.4).
  const [params] = useSearchParams()
  const [extras, setExtras] = useState<{ chave: string; valor: string; rotulo: string }[]>(() => {
    const obra = params.get('obra')
    return obra ? [{ chave: 'obra', valor: obra, rotulo: `Obra: ${params.get('obra_nome') || `#${obra}`}` }] : []
  })
  // O pedido de compra do Suprimentos abre o título direto (`?conta=`, D284).
  const [aberta, setAberta] = useState<number | null>(() => Number(params.get('conta')) || null)
  const [criando, setCriando] = useState(false)
  const [titulo, setTitulo] = useState<{ titulo: string; descricao?: string }>({ titulo: '' })

  const filtros: Filtros = useMemo(() => ({
    search: busca, faixa: situacao, empreendimento, data_de: periodo.de, data_ate: periodo.ate,
    ...Object.fromEntries(extras.map(e => [e.chave, e.valor])),
  }), [busca, situacao, empreendimento, periodo, extras])
  const grade = useGrade<ContaPagar>({ recurso: 'contas-a-pagar', filtros, ordenarPadrao: 'vencimento' })
  const empreendimentos = useEmpreendimentoOptions(true)
  const criar = useCreateContaAPagar()
  const qc = useQueryClient()

  const abrirSoOGrupo = (no: NoGrupo) => {
    const f = filtrosDoGrupo({}, no)
    setExtras(atual => [
      ...atual.filter(e => !(e.chave in f)),
      ...no.filtros.map((chave, i) => ({ chave, valor: no.chaves[i], rotulo: `${ROTULO_EXTRA[chave] ?? chave}: ${no.rotulos[i]}` })),
    ])
    grade.setNiveis([])
  }

  const colunas = useMemo<ColunaGrade<ContaPagar>[]>(() => [
    { chave: 'fornecedor', titulo: 'Fornecedor', largura: 230, ordenar: 'fornecedor', render: c => <span className="truncate font-semibold" style={{ color: 'var(--ink)' }}>{c.fornecedor_nome || '—'}</span>, texto: c => c.fornecedor_nome },
    { chave: 'descricao', titulo: 'Descrição', largura: 240, ordenar: 'descricao', render: c => <span className="truncate" title={c.descricao}>{c.descricao}</span>, texto: c => c.descricao },
    { chave: 'empreendimento', titulo: 'Empreendimento', largura: 180, ordenar: 'empreendimento', render: c => <span className="truncate">{c.empreendimento_nome || '—'}</span>, texto: c => c.empreendimento_nome },
    { chave: 'obra', titulo: 'Obra', largura: 170, ordenar: 'obra', render: c => <span className="truncate" title={c.etapa_nome ? `${c.obra_nome} · ${c.etapa_nome}` : c.obra_nome}>{c.obra_nome || '—'}</span>, texto: c => c.obra_nome },
    { chave: 'vencimento', titulo: 'Vencimento', largura: 120, ordenar: 'vencimento', tipo: 'data', render: c => dateToBR(c.data_vencimento), texto: c => dateToBR(c.data_vencimento) },
    { chave: 'valor', titulo: 'Valor', largura: 120, ordenar: 'valor', tipo: 'numero', alinhamento: 'right', render: c => <MoneyDisplay cents={apiDecimalToCents(c.valor)} />, texto: c => c.valor },
    { chave: 'saldo', titulo: 'Em aberto', largura: 120, ordenar: 'saldo', tipo: 'numero', alinhamento: 'right', render: c => <MoneyDisplay cents={apiDecimalToCents(c.saldo_aberto)} />, texto: c => c.saldo_aberto },
    { chave: 'pagamento', titulo: 'Pago em', largura: 110, ordenar: 'pagamento', tipo: 'data', render: c => (c.data_pagamento ? dateToBR(c.data_pagamento) : '—'), texto: c => c.data_pagamento ?? '' },
    { chave: 'status', titulo: 'Situação', largura: 120, ordenar: 'status', render: c => <StatusContaBadge status={c.status} />, texto: c => STATUS_CONTA_CONFIG[c.status]?.label ?? c.status },
  ], [])

  const temFiltro = Boolean(busca || situacao || empreendimento || periodo.de || periodo.ate || extras.length)
  const fechar = useCallback(() => { setAberta(null); setCriando(false) }, [])
  const definirTitulo = useCallback((t: string, d?: string) => setTitulo({ titulo: t, descricao: d }), [])

  return (
    <>
      <TelaDaGrade<ContaPagar>
        titulo="Contas a pagar"
        subtitulo="Fornecedores, notas e pagamentos — busque por fornecedor, CNPJ, descrição, obra ou número da nota"
        acoes={
          <>
          {/* Planilha: sai o recorte da grade (R7); entra só título novo, em aberto. */}
          <BotaoExportar tam="md" recurso="erp.conta_pagar" recorte={filtros} />
          <WizardImportacao tam="md" recurso="erp.conta_pagar" onConcluida={() => qc.invalidateQueries({ queryKey: ['erp'] })} />
          <button type="button" onClick={() => setCriando(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--brand)', color: '#fff', border: 'none', cursor: 'pointer' }}>
            <Plus size={16} /> Nova conta
          </button>
          </>
        }
        busca={busca}
        onBuscar={setBusca}
        placeholderBusca="Buscar por fornecedor, CNPJ, descrição, obra ou nota"
        situacoes={SITUACOES}
        situacao={situacao}
        onSituacao={setSituacao}
        filtros={
          <>
            <select aria-label="Empreendimento" value={empreendimento} style={estiloFiltro} onChange={e => setEmpreendimento(e.target.value)}>
              <option value="">Todas as obras</option>
              {(empreendimentos.data ?? []).map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
            <span className="flex items-center gap-1.5" style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
              Vencimento
              <input type="date" aria-label="Vencimento de" min={minCalendarioISO} max={maxCalendarioISO} value={periodo.de} style={estiloFiltro} onChange={e => setPeriodo(p => ({ ...p, de: e.target.value }))} />
              até
              <input type="date" aria-label="Vencimento até" min={minCalendarioISO} max={maxCalendarioISO} value={periodo.ate} style={estiloFiltro} onChange={e => setPeriodo(p => ({ ...p, ate: e.target.value }))} />
            </span>
            {extras.map(e => (
              <span key={e.chave} className="flex items-center gap-1" style={{ padding: '3px 6px 3px 10px', borderRadius: 999, background: 'var(--surface-2)', fontSize: 12, fontWeight: 600, color: 'var(--ink-2)' }}>
                {e.rotulo}
                <button type="button" aria-label={`Tirar o filtro ${e.rotulo}`} onClick={() => setExtras(x => x.filter(y => y.chave !== e.chave))}
                  style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'inherit', display: 'flex', padding: 0 }}><X size={13} /></button>
              </span>
            ))}
            {temFiltro && (
              <button type="button" onClick={() => { setBusca(''); setSituacao(''); setEmpreendimento(''); setPeriodo({ de: '', ate: '' }); setExtras([]) }}
                style={{ border: 'none', background: 'none', color: 'var(--ink-3)', fontSize: 12.5, cursor: 'pointer' }}>Limpar filtros</button>
            )}
          </>
        }
        grade={grade}
        colunas={colunas}
        onAbrir={c => setAberta(c.conta_pagar_id)}
        onAbrirSoOGrupo={abrirSoOGrupo}
        substantivo={['conta', 'contas']}
        mostrarSaldo
        vazio={temFiltro ? 'Nenhuma conta para esta busca.' : 'Nenhuma conta a pagar lançada.'}
      />

      <Sheet open={aberta != null || criando} onClose={fechar} width={560}
        title={criando ? 'Nova conta a pagar' : titulo.titulo} description={criando ? undefined : titulo.descricao}>
        {criando && <ContaPagarForm onCancel={fechar} onSubmit={async p => { await criar.mutateAsync(p); fechar() }} />}
        {aberta != null && <DetalheContaPagar key={aberta} contaId={aberta} onTitulo={definirTitulo} />}
      </Sheet>
    </>
  )
}

function DetalheContaPagar({ contaId, onTitulo }: { contaId: number; onTitulo: (t: string, d?: string) => void }) {
  const [modo, setModo] = useState<'ver' | 'editar' | 'baixa'>('ver')
  const [estornando, setEstornando] = useState(false)
  const { data: conta } = useQuery({ queryKey: erpKeys.contasAPagar.detail(contaId), queryFn: () => fetchContaAPagar(contaId) })
  const atualizar = useUpdateContaAPagar()
  const baixa = useDarBaixaContaAPagar()
  const estornar = useEstornarBaixa('pagar')

  useEffect(() => {
    if (conta) onTitulo(modo === 'editar' ? 'Editar conta a pagar' : modo === 'baixa' ? 'Dar baixa' : conta.descricao, conta.fornecedor_nome)
  }, [conta, modo, onTitulo])

  if (!conta) return <p className="text-sm" style={{ color: 'var(--ink-3)' }}>Carregando…</p>
  if (modo === 'editar') {
    return <ContaPagarForm initial={conta} onCancel={() => setModo('ver')}
      onSubmit={async p => { await atualizar.mutateAsync({ id: conta.conta_pagar_id, payload: p }); setModo('ver') }} />
  }
  if (modo === 'baixa') {
    return <BaixaForm saldoAberto={conta.saldo_aberto} onCancel={() => setModo('ver')}
      onSubmit={async p => { await baixa.mutateAsync({ id: conta.conta_pagar_id, payload: p }); setModo('ver') }} />
  }
  const aberta = conta.status === 'ABERTO' || conta.status === 'PARCIAL'
  const vencida = aberta && conta.data_vencimento < maxTodayISO()

  return (
    <div className="flex flex-col gap-5 text-sm" style={{ color: 'var(--ink-2)' }}>
      <div className="flex items-center justify-between">
        <StatusContaBadge status={conta.status} />
        <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>{conta.empreendimento_nome || 'Sem obra'}</span>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Item r="Valor" v={<MoneyDisplay cents={apiDecimalToCents(conta.valor)} />} />
        <Item r="Em aberto" v={<MoneyDisplay cents={apiDecimalToCents(conta.saldo_aberto)} />} />
        <Item r="Vencimento" v={<span style={{ color: vencida ? 'var(--danger-ink)' : undefined }}>{dateToBR(conta.data_vencimento)}{vencida ? ' · vencida' : ''}</span>} />
        <Item r="Pago em" v={conta.data_pagamento ? dateToBR(conta.data_pagamento) : '—'} />
        <Item r="Emissão" v={conta.data_emissao ? dateToBR(conta.data_emissao) : '—'} />
        <Item r="Agendamento" v={conta.data_agendamento ? dateToBR(conta.data_agendamento) : '—'} />
      </dl>
      {conta.rateios.length > 0 && (
        <ul className="flex flex-col gap-1">
          {conta.rateios.map(r => <li key={r.rateio_id} className="flex justify-between"><span>{r.centro_custo_nome}</span><MoneyDisplay cents={apiDecimalToCents(r.valor)} /></li>)}
        </ul>
      )}
      {conta.pedido_compra_ref != null && <CompraDoTitulo conta={conta} />}
      <AvisoDeTrava motivo={conta.travado_porque} />
      {conta.estorno_impedido_porque && <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>{conta.estorno_impedido_porque}</p>}
      <div className="flex items-center justify-end gap-2 flex-wrap">
        {conta.pode_estornar && !conta.estorno_impedido_porque && (
          <button type="button" onClick={() => setEstornando(true)} style={buttonSecondaryStyle}>Estornar baixa</button>
        )}
        <button type="button" onClick={() => setModo('editar')} style={buttonSecondaryStyle}>Editar</button>
        {aberta && <button type="button" onClick={() => setModo('baixa')} style={buttonPrimaryStyle}>Dar baixa</button>}
      </div>
      {estornando && (
        <EstornarBaixaDialog valorPago={conta.valor_pago} pendente={estornar.isPending} onFechar={() => setEstornando(false)}
          onConfirmar={motivo => estornar.mutateAsync({ id: conta.conta_pagar_id, motivo })} />
      )}
    </div>
  )
}

const NFE_COR: Record<string, [string, string]> = {
  aguardando_nota: ['var(--accent-soft)', 'var(--accent-ink)'],
  aguardando_documento: ['var(--accent-soft)', 'var(--accent-ink)'],
  conferida: ['var(--good-soft)', 'var(--good-ink)'],
  divergente: ['var(--danger-soft)', 'var(--danger-ink)'],
}

/** O título que nasceu de um pedido de compra: a nota e a trilha do que mudou
 *  no pedido depois (edição, entrega a mais ou a menos, nota divergente). */
function CompraDoTitulo({ conta }: { conta: ContaPagar }) {
  const qc = useQueryClient()
  const { hasPermission } = useAuth()
  const [texto, setTexto] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [cor, tinta] = NFE_COR[conta.nfe_situacao ?? ''] ?? ['var(--surface-2)', 'var(--ink-2)']
  const anotar = async () => {
    if (!texto.trim()) return
    setSalvando(true)
    try {
      await anotarContaAPagar(conta.conta_pagar_id, texto.trim())
      setTexto('')
      await qc.invalidateQueries({ queryKey: erpKeys.contasAPagar.detail(conta.conta_pagar_id) })
    } finally { setSalvando(false) }
  }
  return (
    <div className="flex flex-col gap-2" style={{ borderTop: '1px solid var(--line)', paddingTop: 12 }}>
      <div className="flex items-center gap-2 flex-wrap">
        <Link to={`/app/scm?pedido=${conta.pedido_compra_ref}`} style={{ fontWeight: 600, color: 'var(--net-ink)' }}>Pedido de compra #{conta.pedido_compra_ref}</Link>
        <span style={{ fontSize: 11.5, fontWeight: 650, padding: '2px 9px', borderRadius: 999, background: cor, color: tinta }}>
          {conta.nfe_situacao_nome}{conta.nfe_numero ? ` · ${conta.nfe_numero}` : ''}
        </span>
      </div>
      {(conta.anotacoes ?? []).length > 0 && (
        <ul className="flex flex-col gap-2" style={{ fontSize: 12.5 }}>
          {(conta.anotacoes ?? []).map(a => (
            <li key={a.anotacao_id} style={{ padding: '7px 10px', borderRadius: 8, background: a.tipo === 'divergencia' ? 'var(--danger-soft)' : 'var(--surface-2)' }}>
              <div style={{ color: 'var(--ink)' }}>{a.texto}</div>
              <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 2 }}>
                {a.tipo_nome} · {new Date(a.criado_em).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}{a.autor_nome ? ` · ${a.autor_nome}` : ''}
                {a.valor ? <> · <MoneyDisplay cents={apiDecimalToCents(a.valor)} /></> : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      {hasPermission('erp.conta_pagar.edit') && (
        <div className="flex gap-2">
          <input value={texto} onChange={e => setTexto(e.target.value)} placeholder="Anotar neste título…" aria-label="Anotação"
            style={{ flex: 1, fontSize: 12.5, padding: '6px 10px', border: '1px solid var(--line)', borderRadius: 8, background: 'var(--surface-2)', color: 'var(--ink)' }} />
          <button type="button" onClick={anotar} disabled={salvando || !texto.trim()} style={buttonSecondaryStyle}>Anotar</button>
        </div>
      )}
    </div>
  )
}

function Item({ r, v }: { r: string; v: ReactNode }) {
  return (
    <div>
      <dt className="text-xs" style={{ color: 'var(--ink-3)' }}>{r}</dt>
      <dd className="font-medium" style={{ color: 'var(--ink)' }}>{v}</dd>
    </div>
  )
}
