import { useMemo, useState, type ReactNode } from 'react'
import {
  ClipboardList, ChevronRight, Check, AlertTriangle, Plus, Trash2, ArrowLeft,
  PackagePlus, PackageCheck, PackageMinus, ArrowLeftRight, RotateCcw, ClipboardCheck, Send,
  Coins, Boxes, Warehouse, HardHat, ShieldAlert, Wrench, Package, Truck,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useQueryClient } from '@tanstack/react-query'
import {
  useSilDashboard, saldosHooks, movimentacoesHooks, requisicoesHooks, itensRequisicaoHooks,
  transferenciasHooks, devolucoesHooks,
  inventariosHooks, itensInventarioHooks, locaisHooks, itensHooks, useObras, useFornecedores, useEtapas,
  useRegistrarMov, useDefinirMinimo, useGerarDemanda, useAprovarRequisicao, useAtenderRequisicao,
  useExecutarTransferencia, useExecutarDevolucao, useFecharInventario, useReabrirInventario,
} from '../hooks'
import {
  requisicoes as requisicoesApi, itensRequisicao as itensRequisicaoApi,
  transferencias as transferenciasApi, itensTransferencia as itensTransferenciaApi,
  devolucoes as devolucoesApi, itensDevolucao as itensDevolucaoApi,
  itensInventario as itensInventarioApi, inventarios as inventariosApi,
} from '../api/silApi'
import { silKeys } from '../api/queryKeys'
import { ConsumoApontado } from '../ConsumoApontado'
import {
  brl, qty, dataBR, num, movEstado, requisicaoEstado, transferenciaEstado, devolucaoEstado, inventarioEstado,
  type Kind,
} from '../lib'
import {
  mono, CAPS, inp, errBox, KIND, Pill, EstadoPill, Card, Btn, SectHead, Loading, Empty,
  Modal, Field, Drawer, Info, th, type Say,
} from '../ui'
import type {
  Item, LocalEstoque, SaldoEstoque, Requisicao, Transferencia, Devolucao, Inventario,
  ItemInventario, ItemRequisicao, MovimentacaoEstoque,
} from '../types'

/* ═══════════ COCKPIT (reenquadrado ao almoxarife) ═══════════ */
const ATIV: Record<string, { icon: ReactNode; kind: Kind }> = {
  entrada: { icon: <PackagePlus size={15} />, kind: 'good' }, saida: { icon: <PackageMinus size={15} />, kind: 'danger' },
  ajuste: { icon: <ClipboardCheck size={15} />, kind: 'amber' }, transf_saida: { icon: <ArrowLeftRight size={15} />, kind: 'info' },
  transf_entrada: { icon: <ArrowLeftRight size={15} />, kind: 'info' }, devolucao: { icon: <RotateCcw size={15} />, kind: 'net' },
}
export function Cockpit({ go, say }: { go: (t: string) => void; say: Say }) {
  const { hasPermission } = useAuth()
  const { data: d, isLoading } = useSilDashboard()
  const { data: baixo } = saldosHooks.useList({ abaixo_minimo: 1, page_size: 6 })
  const { data: reqPend } = requisicoesHooks.useList({ status: 'pendente', page_size: 5 })
  const { data: reqAprov } = requisicoesHooks.useList({ status: 'aprovada', page_size: 5 })
  const gerar = useGerarDemanda(), aprovar = useAprovarRequisicao(), atender = useAtenderRequisicao()
  const podeSaldo = hasPermission('sil.saldo.edit'), podeAprovar = hasPermission('sil.requisicao.aprovar'), podeAtender = hasPermission('sil.requisicao.atender')
  if (isLoading || !d) return <Loading />

  const rail = [
    { icon: <Coins size={18} />, k: 'Valor em estoque', v: brl(d.valorEstoque), meta: `${d.locais} local${d.locais !== 1 ? 'is' : ''}`, kind: 'good' as Kind, tab: 'almoxarifados', big: true },
    { icon: <Boxes size={18} />, k: 'Itens em estoque', v: String(d.itensEmEstoque), meta: 'com saldo', kind: 'info' as Kind, tab: 'almoxarifados' },
    { icon: <AlertTriangle size={18} />, k: 'Abaixo do mínimo', v: String(d.abaixoMinimo), meta: 'a repor', kind: 'amber' as Kind, pulse: d.abaixoMinimo > 0, tab: 'almoxarifados' },
    { icon: <ClipboardList size={18} />, k: 'Requisições', v: String(d.requisicoesPendentes), meta: 'a aprovar', kind: 'net' as Kind, pulse: d.requisicoesPendentes > 0, tab: 'requisicoes' },
  ]
  // Alertas operacionais construtora-native (2ª faixa).
  const alertas = [
    { icon: <Truck size={15} />, label: 'Recebimentos a conferir', v: d.recebimentosAConferir, kind: 'net' as Kind, tab: 'movimentacoes' },
    { icon: <ShieldAlert size={15} />, label: 'EPI vencendo / a trocar', v: d.epiVencendo, kind: 'danger' as Kind, tab: 'epi' },
    { icon: <Wrench size={15} />, label: 'Ferramenta em atraso', v: d.ferramentasAtrasadas, kind: 'amber' as Kind, tab: 'ferramentaria' },
    { icon: <ClipboardCheck size={15} />, label: 'Inventários abertos', v: d.inventariosAbertos, kind: 'info' as Kind, tab: 'inventario' },
  ]
  const saldosBaixo = (baixo?.results ?? []) as SaldoEstoque[]
  const reqs = (reqPend?.results ?? []) as Requisicao[]
  const reqsA = (reqAprov?.results ?? []) as Requisicao[]
  const semFila = saldosBaixo.length === 0 && reqs.length === 0 && reqsA.length === 0

  return (
    <>
      <Card pad={false} style={{ marginBottom: 12, overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)' }}>
          {rail.map((s, i) => (
            <button key={s.k} onClick={() => go(s.tab)} style={{ position: 'relative', padding: '18px 20px', textAlign: 'left', background: 'none', border: 'none', borderLeft: i ? '1px solid var(--line-2)' : undefined, cursor: 'pointer' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--ink-3)' }}><span style={{ display: 'grid', placeItems: 'center', width: 30, height: 30, borderRadius: 'var(--r-sm)', background: KIND[s.kind][0], color: KIND[s.kind][1] }}>{s.icon}</span><span style={CAPS}>{s.k}</span></div>
              <div style={{ ...mono, fontSize: s.big ? 25 : 30, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--ink)', marginTop: 8 }}>{s.v}</div>
              <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 5 }}>{s.pulse && <span className="sil-dot" style={{ color: 'var(--accent-ink)' }} />}{s.meta}</div>
            </button>
          ))}
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(210px,1fr))', gap: 12, marginBottom: 4 }}>
        {alertas.map(a => (
          <button key={a.label} onClick={() => go(a.tab)} style={{ textAlign: 'left', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 11, padding: '13px 15px', borderRadius: 'var(--r-md)', background: a.v > 0 ? KIND[a.kind][0] : 'var(--surface)', border: `1px solid ${a.v > 0 ? 'transparent' : 'var(--line)'}` }}>
            <span style={{ width: 32, height: 32, borderRadius: 9, flex: 'none', display: 'grid', placeItems: 'center', background: 'var(--surface)', color: KIND[a.kind][1] }}>{a.icon}</span>
            <div><div style={{ ...mono, fontSize: 20, fontWeight: 700, color: a.v > 0 ? KIND[a.kind][1] : 'var(--ink-3)' }}>{a.v}</div><div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{a.label}</div></div>
          </button>
        ))}
      </div>

      <ConsumoApontado aoRegistrar={() => go('movimentacoes')} />

      <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 18, marginTop: 14, alignItems: 'start' }}>
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 16px 11px' }}><h2 style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.02em', color: 'var(--ink-2)' }}>Requer sua decisão</h2><span style={{ flex: 1, height: 1, background: 'var(--line-2)' }} /><span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{d.lotesVencendo > 0 ? `${d.lotesVencendo} lote(s) vencendo` : ''}</span></div>
          {semFila ? <div style={{ padding: '8px 16px 22px', fontSize: 13, color: 'var(--ink-3)' }}>Nada aguardando decisão. Estoque saudável.</div> : (
            <div style={{ padding: '2px 8px 10px' }}>
              {saldosBaixo.map(s => (
                <Fila key={`b${s.saldo_id}`} kind="amber" icon={<AlertTriangle size={15} />}
                  titulo={`${s.item_descricao ?? `Item #${s.item}`} abaixo do mínimo`}
                  meta={`${qty(s.quantidade)}/${qty(s.ponto_reposicao)} ${s.item_unidade ?? ''} · ${s.local_nome ?? ''}`}
                  acao={podeSaldo ? <Btn variant="primary" style={{ padding: '6px 11px', fontSize: 12.5 }} disabled={gerar.isPending} onClick={async () => { await gerar.mutateAsync({ saldo: s.saldo_id }); say('Demanda de reposição gerada no SCM') }}><Send size={13} /> Gerar Demanda</Btn> : undefined} />
              ))}
              {reqs.map(r => (
                <Fila key={`rp${r.requisicao_id}`} kind="net" icon={<ClipboardList size={15} />}
                  titulo={`Requisição #${r.requisicao_id} pendente`}
                  meta={`${r.itens_count ?? 0} item(ns) · ${r.local_nome ?? ''}${r.obra_nome ? ` · ${r.obra_nome}` : ''}`}
                  acao={podeAprovar ? <Btn style={{ padding: '6px 11px', fontSize: 12.5 }} disabled={aprovar.isPending} onClick={async () => { await aprovar.mutateAsync(r.requisicao_id); say('Requisição aprovada (saldo reservado)') }}><Check size={13} /> Aprovar</Btn> : undefined} />
              ))}
              {reqsA.map(r => (
                <Fila key={`ra${r.requisicao_id}`} kind="info" icon={<PackageCheck size={15} />}
                  titulo={`Requisição #${r.requisicao_id} a atender`}
                  meta={`aprovada · ${r.local_nome ?? ''}${r.obra_nome ? ` · ${r.obra_nome}` : ''}`}
                  acao={podeAtender ? <Btn variant="primary" style={{ padding: '6px 11px', fontSize: 12.5 }} disabled={atender.isPending} onClick={async () => { await atender.mutateAsync(r.requisicao_id); say('Requisição atendida (saída do estoque)') }}><PackageCheck size={13} /> Atender</Btn> : undefined} />
              ))}
            </div>
          )}
        </Card>
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ padding: '14px 16px 8px' }}><h2 style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.02em', color: 'var(--ink-2)' }}>Movimentação recente</h2></div>
          <div style={{ padding: '2px 6px 8px' }}>
            {(d.atividade ?? []).length === 0 ? <div style={{ padding: '10px 12px', fontSize: 12.5, color: 'var(--ink-3)' }}>Sem movimentação ainda.</div> : d.atividade.map((a, i) => {
              const info = ATIV[a.tipo] ?? ATIV.entrada
              return (
                <div key={i} className="sil-row" style={{ display: 'flex', gap: 12, padding: '11px 12px', borderRadius: 10 }}>
                  <span style={{ width: 30, height: 30, borderRadius: 8, flex: 'none', display: 'grid', placeItems: 'center', background: KIND[info.kind][0], color: KIND[info.kind][1] }}>{info.icon}</span>
                  <div><div style={{ fontSize: 13, color: 'var(--ink)' }}>{a.titulo}</div><div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{a.meta}</div></div>
                </div>
              )
            })}
          </div>
        </Card>
      </div>
    </>
  )
}
function Fila({ kind, icon, titulo, meta, acao }: { kind: Kind; icon: ReactNode; titulo: string; meta: string; acao?: ReactNode }) {
  return (
    <div className="sil-row" style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 12px', borderRadius: 10 }}>
      <span style={{ width: 32, height: 32, borderRadius: 9, flex: 'none', display: 'grid', placeItems: 'center', background: KIND[kind][0], color: KIND[kind][1] }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}><div style={{ fontSize: 13.5, color: 'var(--ink)', fontWeight: 550 }}>{titulo}</div><div style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)' }}>{meta}</div></div>
      {acao}
    </div>
  )
}

/* ═══════════ ALMOXARIFADOS (locais clicáveis + kardex do item) ═══════════ */
export function Almoxarifados({ say }: { say: Say }) {
  const { hasPermission } = useAuth()
  const podeSaldo = hasPermission('sil.saldo.edit'), podeLocal = hasPermission('sil.local.edit')
  const podeMover = hasPermission('sil.movimentacao.edit')
  const [saida, setSaida] = useState<{ item: number; local: number } | null>(null)
  const [soBaixo, setSoBaixo] = useState(false)
  const [search, setSearch] = useState('')
  const [minimo, setMinimo] = useState<SaldoEstoque | null>(null)
  const [localSel, setLocalSel] = useState<LocalEstoque | null>(null)
  const [itemSel, setItemSel] = useState<number | null>(null)
  const [novoLocal, setNovoLocal] = useState(false)
  const { data: locaisData } = locaisHooks.useAll({ ativo: true })
  const { data: saldosAll } = saldosHooks.useAll({})
  const { data, isLoading } = saldosHooks.useList({ ...(soBaixo ? { abaixo_minimo: 1 } : {}), search, page_size: 50 })
  const gerar = useGerarDemanda()
  const locais = (locaisData ?? []) as LocalEstoque[]
  const todosSaldos = (saldosAll ?? []) as SaldoEstoque[]
  const rows = (data?.results ?? []) as SaldoEstoque[]
  // valor + nº de itens por local (agregado no cliente).
  const porLocal = useMemo(() => {
    const m = new Map<number, { valor: number; itens: number }>()
    for (const s of todosSaldos) {
      const cur = m.get(s.local) ?? { valor: 0, itens: 0 }
      cur.valor += num(s.valor_total) ?? 0
      if ((num(s.quantidade) ?? 0) > 0) cur.itens += 1
      m.set(s.local, cur)
    }
    return m
  }, [todosSaldos])

  return (
    <>
      <SectHead right={podeLocal ? <Btn variant="primary" style={{ padding: '6px 12px', fontSize: 12.5 }} onClick={() => setNovoLocal(true)}><Plus size={14} /> Novo local</Btn> : undefined}>Almoxarifados &amp; canteiros</SectHead>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(230px,1fr))', gap: 12 }}>
        {locais.map(l => { const agg = porLocal.get(l.local_id) ?? { valor: 0, itens: 0 }; return (
          <Card key={l.local_id} className="sil-lift" style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 8 }} onClick={() => setLocalSel(l)}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ width: 36, height: 36, borderRadius: 'var(--r-md)', flex: 'none', display: 'grid', placeItems: 'center', background: l.tipo === 'central' ? 'var(--info-soft)' : 'var(--accent-soft)', color: l.tipo === 'central' ? 'var(--info-ink)' : 'var(--accent-ink)' }}>{l.tipo === 'canteiro' ? <HardHat size={18} /> : <Warehouse size={18} />}</span>
              <div style={{ flex: 1, minWidth: 0 }}><div style={{ fontWeight: 650, fontSize: 14, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.nome}</div><div style={{ fontSize: 11.5, color: 'var(--ink-3)', textTransform: 'capitalize' }}>{l.tipo}{l.obra_nome ? ` · ${l.obra_nome}` : ''}</div></div>
              <ChevronRight size={16} style={{ color: 'var(--ink-3)' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 8, borderTop: '1px solid var(--line-2)' }}>
              <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{agg.itens} item(ns)</span>
              <span style={{ ...mono, fontWeight: 700, fontSize: 14, color: 'var(--ink)' }}>{brl(agg.valor.toFixed(2))}</span>
            </div>
          </Card>
        ) })}
      </div>

      <SectHead right={
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--ink-2)', cursor: 'pointer' }}><input type="checkbox" checked={soBaixo} onChange={e => setSoBaixo(e.target.checked)} /> abaixo do mínimo</label>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar item…" style={{ ...inp, width: 190, padding: '7px 11px' }} />
        </div>}>Saldos valorados</SectHead>
      {isLoading ? <Loading /> : rows.length === 0 ? <Empty>Nenhum saldo{soBaixo ? ' abaixo do mínimo' : ''}.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 780 }}>
            <thead><tr>{['Item', 'Local', 'Qtd.', 'Disponível', 'Custo médio', 'Valor total', ''].map((h, i) => <th key={i} style={th(h, i, n => n >= 2 && n <= 5)}>{h}</th>)}</tr></thead>
            <tbody>{rows.map((s, i) => (
              <tr key={s.saldo_id} className="sil-row" style={{ borderBottom: i < rows.length - 1 ? '1px solid var(--line-2)' : undefined, background: s.abaixo_minimo ? 'var(--accent-soft)' : undefined }}>
                <td style={{ padding: '11px 16px' }}><button onClick={() => setItemSel(s.item)} style={{ background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', padding: 0 }}><div style={{ fontWeight: 550, color: 'var(--net-ink)' }}>{s.item_descricao ?? `#${s.item}`}</div><span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)' }}>{s.item_codigo ?? ''}</span></button></td>
                <td style={{ padding: '11px 16px', color: 'var(--ink-2)', fontSize: 12.5 }}>{s.local_nome ?? `#${s.local}`}</td>
                <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', fontWeight: 600, color: 'var(--ink)' }}>{qty(s.quantidade)} <small style={{ color: 'var(--ink-3)' }}>{s.item_unidade}</small>{s.abaixo_minimo && <div><Pill kind="amber">mín {qty(s.ponto_reposicao)}</Pill></div>}</td>
                <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', color: 'var(--ink-2)' }}>{qty(s.disponivel)}</td>
                <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', color: 'var(--ink-2)' }}>{brl(s.custo_medio)}</td>
                <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', fontWeight: 700, color: 'var(--ink)' }}>{brl(s.valor_total)}</td>
                <td style={{ padding: '11px 16px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                  {podeMover && (num(s.disponivel) ?? 0) > 0 && <Btn style={{ padding: '5px 10px', fontSize: 12 }} onClick={() => setSaida({ item: s.item, local: s.local })}><PackageMinus size={12} /> Saída</Btn>}
                  {podeSaldo && <>
                    {s.abaixo_minimo && <Btn variant="primary" style={{ padding: '5px 10px', fontSize: 12 }} disabled={gerar.isPending} onClick={async () => { await gerar.mutateAsync({ saldo: s.saldo_id }); say('Demanda gerada no SCM') }}><Send size={12} /> Demanda</Btn>}
                    <Btn style={{ padding: '5px 10px', fontSize: 12, marginLeft: 6 }} onClick={() => setMinimo(s)}>Mínimo</Btn>
                  </>}
                </td>
              </tr>
            ))}</tbody>
          </table></div>
        </Card>
      )}
      {minimo && <DefinirMinimoModal saldo={minimo} onClose={() => setMinimo(null)} onDone={() => { setMinimo(null); say('Ponto de reposição atualizado') }} />}
      {localSel && <LocalDrawer local={localSel} saldos={todosSaldos.filter(s => s.local === localSel.local_id)} onItem={id => { setLocalSel(null); setItemSel(id) }} onClose={() => setLocalSel(null)} />}
      {itemSel != null && <ItemDrawer itemId={itemSel} onClose={() => setItemSel(null)} onSaida={podeMover ? local => setSaida({ item: itemSel, local }) : undefined} />}
      {saida && <RegistrarMovModal inicial={{ ...saida, tipo: 'saida' }} onClose={() => setSaida(null)} onDone={() => { setSaida(null); say('Saída registrada') }} />}
      {novoLocal && <NovoLocalModal onClose={() => setNovoLocal(false)} onDone={() => { setNovoLocal(false); say('Local criado') }} />}
    </>
  )
}
function LocalDrawer({ local, saldos, onItem, onClose }: { local: LocalEstoque; saldos: SaldoEstoque[]; onItem: (id: number) => void; onClose: () => void }) {
  const { data: movs } = movimentacoesHooks.useList({ local: local.local_id, page_size: 8 })
  const linhas = (movs?.results ?? []) as MovimentacaoEstoque[]
  const valor = saldos.reduce((a, s) => a + (num(s.valor_total) ?? 0), 0)
  return (
    <Drawer title={<span style={{ display: 'flex', alignItems: 'center', gap: 9 }}>{local.tipo === 'canteiro' ? <HardHat size={18} /> : <Warehouse size={18} />}{local.nome}</span>} onClose={onClose}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12, marginBottom: 16 }}>
        <Info k="Tipo" v={<span style={{ textTransform: 'capitalize' }}>{local.tipo}</span>} />
        <Info k="Itens" v={String(saldos.filter(s => (num(s.quantidade) ?? 0) > 0).length)} mono />
        <Info k="Valor" v={brl(valor.toFixed(2))} mono />
      </div>
      <SectHead>No estoque</SectHead>
      {saldos.length === 0 ? <Empty>Local vazio.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead><tr>{['Item', 'Qtd.', 'Valor'].map((h, i) => <th key={i} style={th(h, i, n => n >= 1)}>{h}</th>)}</tr></thead>
          <tbody>{saldos.map((s, i) => (
            <tr key={s.saldo_id} className="sil-row" style={{ borderBottom: i < saldos.length - 1 ? '1px solid var(--line-2)' : undefined, cursor: 'pointer' }} onClick={() => onItem(s.item)}>
              <td style={{ padding: '10px 14px', color: 'var(--net-ink)' }}>{s.item_descricao ?? `#${s.item}`}</td>
              <td style={{ ...mono, padding: '10px 14px', textAlign: 'right' }}>{qty(s.quantidade)} <small style={{ color: 'var(--ink-3)' }}>{s.item_unidade}</small></td>
              <td style={{ ...mono, padding: '10px 14px', textAlign: 'right', fontWeight: 600 }}>{brl(s.valor_total)}</td>
            </tr>
          ))}</tbody>
        </table></Card>
      )}
      <SectHead>Movimentos recentes</SectHead>
      {linhas.length === 0 ? <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Sem movimentos.</div> : linhas.map(m => (
        <div key={m.mov_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--line-2)' }}>
          <EstadoPill e={movEstado[m.tipo]} /><span style={{ flex: 1, fontSize: 12.5, color: 'var(--ink-2)' }}>{m.item_descricao}</span>
          <span style={{ ...mono, fontSize: 12, color: 'var(--ink-3)' }}>{qty(m.quantidade)} · {dataBR(m.criado_em)}</span>
        </div>
      ))}
    </Drawer>
  )
}
function ItemDrawer({ itemId, onClose, onSaida }: { itemId: number; onClose: () => void; onSaida?: (local: number) => void }) {
  const { data: saldosData } = saldosHooks.useAll({ item: itemId })
  const { data: movs } = movimentacoesHooks.useList({ item: itemId, page_size: 20 })
  const saldos = (saldosData ?? []) as SaldoEstoque[]
  const linhas = (movs?.results ?? []) as MovimentacaoEstoque[]
  const primeiro = saldos[0]
  const totalQtd = saldos.reduce((a, s) => a + (num(s.quantidade) ?? 0), 0)
  const totalVal = saldos.reduce((a, s) => a + (num(s.valor_total) ?? 0), 0)
  return (
    <Drawer title={<span style={{ display: 'flex', alignItems: 'center', gap: 9 }}><Package size={18} />{primeiro?.item_descricao ?? `Item #${itemId}`}</span>} onClose={onClose}>
      <div style={{ ...mono, fontSize: 12, color: 'var(--ink-3)', marginTop: -8, marginBottom: 14 }}>{primeiro?.item_codigo ?? ''}</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12, marginBottom: 16 }}>
        <Info k="Saldo total" v={<>{qty(totalQtd)} <small style={{ color: 'var(--ink-3)' }}>{primeiro?.item_unidade}</small></>} mono />
        <Info k="Custo médio" v={brl(primeiro?.custo_medio)} mono />
        <Info k="Valor total" v={brl(totalVal.toFixed(2))} mono />
      </div>
      <SectHead>Saldo por local</SectHead>
      <Card pad={false} style={{ overflow: 'hidden' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead><tr>{['Local', 'Qtd.', 'Reservado', 'Custo médio', ''].map((h, i) => <th key={i} style={th(h, i, n => n >= 1 && n <= 3)}>{h}</th>)}</tr></thead>
        <tbody>{saldos.map((s, i) => (
          <tr key={s.saldo_id} style={{ borderBottom: i < saldos.length - 1 ? '1px solid var(--line-2)' : undefined, background: s.abaixo_minimo ? 'var(--accent-soft)' : undefined }}>
            <td style={{ padding: '10px 14px', color: 'var(--ink)' }}>{s.local_nome}</td>
            <td style={{ ...mono, padding: '10px 14px', textAlign: 'right', fontWeight: 600 }}>{qty(s.quantidade)}</td>
            <td style={{ ...mono, padding: '10px 14px', textAlign: 'right', color: 'var(--ink-3)' }}>{qty(s.reservado)}</td>
            <td style={{ ...mono, padding: '10px 14px', textAlign: 'right' }}>{brl(s.custo_medio)}</td>
            <td style={{ padding: '10px 14px', textAlign: 'right' }}>{onSaida && (num(s.disponivel) ?? 0) > 0 && <Btn style={{ padding: '4px 9px', fontSize: 12 }} onClick={() => onSaida(s.local)}><PackageMinus size={12} /> Saída</Btn>}</td>
          </tr>
        ))}</tbody>
      </table></Card>
      <SectHead>Kardex (movimentações)</SectHead>
      {linhas.length === 0 ? <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Sem movimentações.</div> : (
        <Card pad={false} style={{ overflow: 'hidden' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead><tr>{['Data', 'Tipo', 'Qtd.', 'Custo un.', 'Obra/etapa'].map((h, i) => <th key={i} style={th(h, i, n => n === 2 || n === 3)}>{h}</th>)}</tr></thead>
          <tbody>{linhas.map((m, i) => (
            <tr key={m.mov_id} style={{ borderBottom: i < linhas.length - 1 ? '1px solid var(--line-2)' : undefined }}>
              <td style={{ ...mono, padding: '9px 14px', color: 'var(--ink-3)', fontSize: 11.5 }}>{dataBR(m.criado_em)}</td>
              <td style={{ padding: '9px 14px' }}><EstadoPill e={movEstado[m.tipo]} /></td>
              <td style={{ ...mono, padding: '9px 14px', textAlign: 'right', fontWeight: 600 }}>{qty(m.quantidade)}</td>
              <td style={{ ...mono, padding: '9px 14px', textAlign: 'right', color: 'var(--ink-2)' }}>{brl(m.custo_unitario)}</td>
              <td style={{ padding: '9px 14px', fontSize: 11.5, color: 'var(--ink-3)' }}>{m.obra_nome ?? '—'}{m.etapa_nome ? ` · ${m.etapa_nome}` : ''}</td>
            </tr>
          ))}</tbody>
        </table></Card>
      )}
    </Drawer>
  )
}
function DefinirMinimoModal({ saldo, onClose, onDone }: { saldo: SaldoEstoque; onClose: () => void; onDone: () => void }) {
  const def = useDefinirMinimo()
  const [ponto, setPonto] = useState(saldo.ponto_reposicao ?? '0')
  return <Modal title="Ponto de reposição" onClose={onClose} footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={async () => { await def.mutateAsync({ saldo: saldo.saldo_id, ponto }); onDone() }} disabled={def.isPending}>Salvar</Btn></>}>
    <div style={{ padding: '10px 12px', background: 'var(--surface-2)', borderRadius: 'var(--r-sm)', marginBottom: 14 }}><div style={{ fontWeight: 600, color: 'var(--ink)' }}>{saldo.item_descricao}</div><div style={{ fontSize: 12, color: 'var(--ink-3)' }}>{saldo.local_nome} · saldo {qty(saldo.quantidade)} {saldo.item_unidade}</div></div>
    <Field label="Quantidade mínima (dispara reposição)"><input style={{ ...inp, ...mono }} type="number" min={0} step="0.001" value={ponto} onChange={e => setPonto(e.target.value)} /></Field>
  </Modal>
}
function NovoLocalModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const create = locaisHooks.useCreate()
  const { data: obras } = useObras()
  const [nome, setNome] = useState(''), [tipo, setTipo] = useState('central'), [obra, setObra] = useState(''), [err, setErr] = useState('')
  const salvar = async () => {
    if (!nome.trim()) return setErr('Informe o nome.')
    try { await create.mutateAsync({ nome, tipo, obra: obra ? Number(obra) : null }); onDone() }
    catch { setErr('Falha ao criar (nome duplicado?).') }
  }
  return <Modal title="Novo local de estoque" onClose={onClose} footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={create.isPending}>Criar</Btn></>}>
    {err && <div style={errBox}>{err}</div>}
    <Field label="Nome"><input style={inp} value={nome} onChange={e => setNome(e.target.value)} placeholder="Ex.: Canteiro — Torre B" /></Field>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Tipo"><select style={inp} value={tipo} onChange={e => setTipo(e.target.value)}><option value="central">Almoxarifado central</option><option value="canteiro">Canteiro de obra</option><option value="outro">Outro</option></select></Field>
      <Field label="Obra (canteiro)"><select style={inp} value={obra} onChange={e => setObra(e.target.value)}><option value="">— nenhuma —</option>{(obras ?? []).map(o => <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>)}</select></Field>
    </div>
  </Modal>
}

/* ═══════════ MOVIMENTAÇÕES ═══════════ */
const SEAM: { key: keyof MovimentacaoEstoque; label: (v: number) => string; kind: Kind }[] = [
  { key: 'recebimento_scm_ref', label: v => `Receb. SCM #${v}`, kind: 'net' },
  { key: 'requisicao', label: v => `Requisição #${v}`, kind: 'info' },
  { key: 'transferencia', label: v => `Transf. #${v}`, kind: 'info' },
  { key: 'devolucao', label: v => `Devolução #${v}`, kind: 'net' },
  { key: 'inventario', label: v => `Inventário #${v}`, kind: 'amber' },
]
export function Movimentacoes({ say }: { say: Say }) {
  const { hasPermission } = useAuth()
  const podeMover = hasPermission('sil.movimentacao.edit')
  const [tipo, setTipo] = useState('')
  const [registrar, setRegistrar] = useState(false)
  const { data, isLoading } = movimentacoesHooks.useList({ ...(tipo ? { tipo } : {}), page_size: 50 })
  const rows = (data?.results ?? []) as MovimentacaoEstoque[]
  return (
    <>
      <SectHead right={
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select value={tipo} onChange={e => setTipo(e.target.value)} style={{ ...inp, width: 'auto', padding: '7px 10px' }}>
            <option value="">Todos os tipos</option><option value="entrada">Entrada</option><option value="saida">Saída</option><option value="ajuste">Ajuste</option>
            <option value="transf_saida">Transf. saída</option><option value="transf_entrada">Transf. entrada</option><option value="devolucao">Devolução</option>
          </select>
          {podeMover && <Btn variant="primary" style={{ padding: '6px 12px', fontSize: 12.5 }} onClick={() => setRegistrar(true)}><PackagePlus size={14} /> Registrar</Btn>}
        </div>}>Ledger de movimentações</SectHead>
      {isLoading ? <Loading /> : rows.length === 0 ? <Empty>Nenhuma movimentação{tipo ? ' desse tipo' : ''}. O recebimento do SCM entra aqui automaticamente.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 900 }}>
            <thead><tr>{['Data', 'Tipo', 'Item', 'Local', 'Qtd.', 'Custo un.', 'Obra/etapa', 'Origem'].map((h, i) => <th key={i} style={th(h, i, n => n === 4 || n === 5)}>{h}</th>)}</tr></thead>
            <tbody>{rows.map((m, i) => {
              const seam = SEAM.find(s => m[s.key] != null)
              return (
                <tr key={m.mov_id} className="sil-row" style={{ borderBottom: i < rows.length - 1 ? '1px solid var(--line-2)' : undefined }}>
                  <td style={{ ...mono, padding: '11px 16px', fontSize: 12, color: 'var(--ink-3)' }}>{dataBR(m.criado_em)}</td>
                  <td style={{ padding: '11px 16px' }}><EstadoPill e={movEstado[m.tipo]} /></td>
                  <td style={{ padding: '11px 16px' }}><div style={{ color: 'var(--ink)' }}>{m.item_descricao ?? `#${m.item}`}</div><span style={{ ...mono, fontSize: 11, color: 'var(--ink-3)' }}>{m.item_codigo ?? ''}</span></td>
                  <td style={{ padding: '11px 16px', color: 'var(--ink-2)', fontSize: 12.5 }}>{m.local_nome ?? `#${m.local}`}</td>
                  <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', fontWeight: 600, color: 'var(--ink)' }}>{qty(m.quantidade)}</td>
                  <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', color: 'var(--ink-2)' }}>{brl(m.custo_unitario)}</td>
                  <td style={{ padding: '11px 16px', fontSize: 11.5, color: 'var(--ink-3)' }}>{m.obra_nome ?? '—'}{m.etapa_nome ? <div style={{ color: 'var(--accent-ink)' }}>{m.etapa_nome}</div> : ''}</td>
                  <td style={{ padding: '11px 16px' }}>{seam ? <Pill kind={seam.kind}>{seam.label(m[seam.key] as number)}</Pill> : <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>manual</span>}</td>
                </tr>
              )
            })}</tbody>
          </table></div>
        </Card>
      )}
      {registrar && <RegistrarMovModal onClose={() => setRegistrar(false)} onDone={() => { setRegistrar(false); say('Movimentação registrada') }} />}
    </>
  )
}
function RegistrarMovModal({ inicial, onClose, onDone }: { inicial?: { item: number; local: number; tipo: string }; onClose: () => void; onDone: () => void }) {
  const registrar = useRegistrarMov()
  const { data: itens } = itensHooks.useAll({ estocavel: true })
  const { data: locais } = locaisHooks.useAll({ ativo: true })
  const { data: obras } = useObras()
  const [item, setItem] = useState(inicial ? String(inicial.item) : ''), [local, setLocal] = useState(inicial ? String(inicial.local) : ''), [tipo, setTipo] = useState(inicial?.tipo ?? 'entrada')
  const [quantidade, setQuantidade] = useState(''), [custo, setCusto] = useState(''), [obra, setObra] = useState(''), [etapa, setEtapa] = useState('')
  const { data: etapas } = useEtapas(obra ? Number(obra) : undefined)
  const [err, setErr] = useState('')
  const opItens = (itens ?? []) as Item[], opLocais = (locais ?? []) as LocalEstoque[]
  const salvar = async () => {
    setErr('')
    if (!item || !local) return setErr('Escolha item e local.')
    if ((num(quantidade) ?? 0) <= 0 && tipo !== 'ajuste') return setErr('Informe uma quantidade positiva.')
    try {
      await registrar.mutateAsync({ item: Number(item), local: Number(local), tipo, quantidade: quantidade || '0', obra: obra ? Number(obra) : null, etapa: etapa ? Number(etapa) : null, ...(tipo !== 'saida' && custo ? { custo_unitario: custo } : {}) })
      onDone()
    } catch (e) { const ax = e as { response?: { data?: { detail?: string } } }; setErr(ax.response?.data?.detail ?? 'Falha ao registrar.') }
  }
  return <Modal title="Registrar movimentação" onClose={onClose} wide footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={registrar.isPending}>{registrar.isPending ? 'Registrando…' : 'Registrar'}</Btn></>}>
    {err && <div style={errBox}>{err}</div>}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Tipo"><select style={inp} value={tipo} onChange={e => setTipo(e.target.value)}><option value="entrada">Entrada</option><option value="saida">Saída (consumo)</option><option value="ajuste">Ajuste (contagem)</option></select></Field>
      <Field label="Local"><select style={inp} value={local} onChange={e => setLocal(e.target.value)}><option value="">— selecione —</option>{opLocais.map(l => <option key={l.local_id} value={l.local_id}>{l.nome}</option>)}</select></Field>
    </div>
    <Field label="Item"><select style={inp} value={item} onChange={e => setItem(e.target.value)}><option value="">— selecione —</option>{opItens.map(i => <option key={i.item_id} value={i.item_id}>{i.codigo_interno} · {i.descricao}</option>)}</select></Field>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label={tipo === 'ajuste' ? 'Quantidade contada' : 'Quantidade'}><input style={{ ...inp, ...mono }} type="number" min={0} step="0.001" value={quantidade} onChange={e => setQuantidade(e.target.value)} placeholder="0" /></Field>
      {tipo !== 'saida' && <Field label="Custo unitário"><input style={{ ...inp, ...mono }} type="number" min={0} step="0.0001" value={custo} onChange={e => setCusto(e.target.value)} placeholder="0,00" /></Field>}
    </div>
    {tipo === 'saida' && <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Obra (apropriação)"><select style={inp} value={obra} onChange={e => { setObra(e.target.value); setEtapa('') }}><option value="">— nenhuma —</option>{(obras ?? []).map(o => <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>)}</select></Field>
      <Field label="Etapa"><select style={inp} value={etapa} onChange={e => setEtapa(e.target.value)} disabled={!obra}><option value="">— nenhuma —</option>{(etapas ?? []).map(et => <option key={et.etapa_id} value={et.etapa_id}>{et.nome_etapa}</option>)}</select></Field>
    </div>}
    <p style={{ fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>{tipo === 'entrada' ? 'A entrada recalcula o custo médio ponderado móvel.' : tipo === 'saida' ? 'A saída valoriza pelo custo médio e apropria o consumo à obra/etapa (físico-financeiro).' : 'O ajuste leva o saldo à quantidade contada.'}</p>
  </Modal>
}

/* ═══════════ REQUISIÇÕES ═══════════ */
export function Requisicoes({ say }: { say: Say }) {
  const { hasPermission } = useAuth()
  const podeCriar = hasPermission('sil.requisicao.edit'), podeAprovar = hasPermission('sil.requisicao.aprovar'), podeAtender = hasPermission('sil.requisicao.atender')
  const [nova, setNova] = useState(false)
  const [detalhe, setDetalhe] = useState<Requisicao | null>(null)
  const { data, isLoading } = requisicoesHooks.useList({ page_size: 50 })
  const aprovar = useAprovarRequisicao(), atender = useAtenderRequisicao()
  const rows = (data?.results ?? []) as Requisicao[]
  return (
    <>
      <SectHead right={podeCriar ? <Btn variant="primary" style={{ padding: '6px 12px', fontSize: 12.5 }} onClick={() => setNova(true)}><Plus size={14} /> Nova requisição</Btn> : undefined}>Requisições de material</SectHead>
      {isLoading ? <Loading /> : rows.length === 0 ? <Empty>Nenhuma requisição. A obra pede material do almoxarifado por aqui.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 820 }}>
            <thead><tr>{['Requisição', 'Local', 'Obra / etapa', 'Itens', 'Estado', ''].map((h, i) => <th key={i} style={th(h, i, n => n === 3)}>{h}</th>)}</tr></thead>
            <tbody>{rows.map((r, i) => (
              <tr key={r.requisicao_id} className="sil-row" style={{ borderBottom: i < rows.length - 1 ? '1px solid var(--line-2)' : undefined }}>
                <td style={{ padding: '12px 16px' }}><button onClick={() => setDetalhe(r)} style={{ background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', padding: 0 }}><span style={{ ...mono, fontWeight: 700, color: 'var(--net-ink)' }}>#{r.requisicao_id}</span><div style={{ fontSize: 11, color: 'var(--ink-3)' }}>{r.solicitante_nome ?? ''}</div></button></td>
                <td style={{ padding: '12px 16px', color: 'var(--ink-2)', fontSize: 12.5 }}>{r.local_nome ?? `#${r.local}`}</td>
                <td style={{ padding: '12px 16px', color: 'var(--ink-2)', fontSize: 12.5 }}>{r.obra_nome ?? '—'}{r.etapa_nome ? <div style={{ color: 'var(--accent-ink)', fontSize: 11.5 }}>{r.etapa_nome}</div> : ''}</td>
                <td style={{ ...mono, padding: '12px 16px', textAlign: 'right', color: 'var(--ink-2)' }}>{r.itens_count ?? 0}</td>
                <td style={{ padding: '12px 16px' }}><EstadoPill e={requisicaoEstado[r.status]} /></td>
                <td style={{ padding: '12px 16px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                  {podeAprovar && (r.status === 'pendente' || r.status === 'rascunho') && <Btn style={{ padding: '5px 10px', fontSize: 12 }} disabled={aprovar.isPending} onClick={async () => { await aprovar.mutateAsync(r.requisicao_id); say('Requisição aprovada (saldo reservado)') }}><Check size={12} /> Aprovar</Btn>}
                  {podeAtender && (r.status === 'aprovada' || r.status === 'parcial') && <Btn variant="primary" style={{ padding: '5px 10px', fontSize: 12 }} disabled={atender.isPending} onClick={async () => { await atender.mutateAsync(r.requisicao_id); say('Requisição atendida (saída do estoque)') }}><PackageCheck size={12} /> Atender</Btn>}
                </td>
              </tr>
            ))}</tbody>
          </table></div>
        </Card>
      )}
      {nova && <NovaRequisicaoModal onClose={() => setNova(false)} onDone={() => { setNova(false); say('Requisição criada') }} />}
      {detalhe && <RequisicaoDrawer req={detalhe} onClose={() => setDetalhe(null)} />}
    </>
  )
}
function RequisicaoDrawer({ req, onClose }: { req: Requisicao; onClose: () => void }) {
  const { data: itens } = itensRequisicaoHooks.useAll({ requisicao: req.requisicao_id })
  const linhas = (itens ?? []) as ItemRequisicao[]
  return (
    <Drawer title={`Requisição #${req.requisicao_id}`} onClose={onClose}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}><EstadoPill e={requisicaoEstado[req.status]} />{req.obra_nome && <Pill kind="slate">{req.obra_nome}</Pill>}{req.etapa_nome && <Pill kind="amber">{req.etapa_nome}</Pill>}</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 12, marginBottom: 16 }}>
        <Info k="Local (de onde sai)" v={req.local_nome ?? '—'} />
        <Info k="Solicitante" v={req.solicitante_nome ?? '—'} />
      </div>
      {req.observacao && <p style={{ fontSize: 13, color: 'var(--ink-2)', marginBottom: 14 }}>{req.observacao}</p>}
      <SectHead>Itens</SectHead>
      {linhas.length === 0 ? <Empty>Sem itens.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead><tr>{['Item', 'Solicitado', 'Atendido'].map((h, i) => <th key={i} style={th(h, i, n => n >= 1)}>{h}</th>)}</tr></thead>
          <tbody>{linhas.map((l, i) => (
            <tr key={l.item_requisicao_id} style={{ borderBottom: i < linhas.length - 1 ? '1px solid var(--line-2)' : undefined }}>
              <td style={{ padding: '10px 14px', color: 'var(--ink)' }}>{l.item_descricao ?? `#${l.item}`}</td>
              <td style={{ ...mono, padding: '10px 14px', textAlign: 'right' }}>{qty(l.quantidade)} <small style={{ color: 'var(--ink-3)' }}>{l.item_unidade}</small></td>
              <td style={{ ...mono, padding: '10px 14px', textAlign: 'right', fontWeight: 600, color: num(l.quantidade_atendida) ? 'var(--good-ink)' : 'var(--ink-3)' }}>{qty(l.quantidade_atendida)}</td>
            </tr>
          ))}</tbody>
        </table></Card>
      )}
    </Drawer>
  )
}
function NovaRequisicaoModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const qc = useQueryClient()
  const { data: locais } = locaisHooks.useAll({ ativo: true })
  const { data: itens } = itensHooks.useAll({ estocavel: true })
  const { data: obras } = useObras()
  const [local, setLocal] = useState(''), [obra, setObra] = useState(''), [etapa, setEtapa] = useState(''), [observacao, setObservacao] = useState('')
  const { data: etapas } = useEtapas(obra ? Number(obra) : undefined)
  const [linhas, setLinhas] = useState<Linha[]>([{ item: '', quantidade: '', key: Date.now() }])
  const [saving, setSaving] = useState(false), [err, setErr] = useState('')
  const opLocais = (locais ?? []) as LocalEstoque[], opItens = (itens ?? []) as Item[]
  const salvar = async () => {
    setErr('')
    const validas = linhas.filter(l => l.item && (num(l.quantidade) ?? 0) > 0)
    if (!local) return setErr('Escolha o local de onde o material sai.')
    if (validas.length === 0) return setErr('Adicione ao menos um item com quantidade.')
    setSaving(true)
    try {
      const req = await requisicoesApi.create({ local: Number(local), obra: obra ? Number(obra) : null, etapa: etapa ? Number(etapa) : null, observacao })
      const rid = (req as Requisicao).requisicao_id
      for (const l of validas) await itensRequisicaoApi.create({ requisicao: rid, item: Number(l.item), quantidade: l.quantidade })
      await qc.invalidateQueries({ queryKey: silKeys.all }); onDone()
    } catch { setErr('Falha ao criar requisição.'); setSaving(false) }
  }
  return <Modal title="Nova requisição" onClose={onClose} wide footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={saving}>{saving ? 'Salvando…' : 'Criar requisição'}</Btn></>}>
    {err && <div style={errBox}>{err}</div>}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
      <Field label="Local (de onde sai)"><select style={inp} value={local} onChange={e => setLocal(e.target.value)}><option value="">— selecione —</option>{opLocais.map(l => <option key={l.local_id} value={l.local_id}>{l.nome}</option>)}</select></Field>
      <Field label="Obra"><select style={inp} value={obra} onChange={e => { setObra(e.target.value); setEtapa('') }}><option value="">— nenhuma —</option>{(obras ?? []).map(o => <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>)}</select></Field>
      <Field label="Etapa"><select style={inp} value={etapa} onChange={e => setEtapa(e.target.value)} disabled={!obra}><option value="">— nenhuma —</option>{(etapas ?? []).map(et => <option key={et.etapa_id} value={et.etapa_id}>{et.nome_etapa}</option>)}</select></Field>
    </div>
    <ItemLines linhas={linhas} setLinhas={setLinhas} itens={opItens} />
    <Field label="Observação"><textarea style={{ ...inp, resize: 'vertical', minHeight: 48 }} value={observacao} onChange={e => setObservacao(e.target.value)} placeholder="Opcional" /></Field>
  </Modal>
}

/* ═══════════ TRANSFERÊNCIAS & DEVOLUÇÕES ═══════════ */
export function Logistica({ say }: { say: Say }) {
  const { hasPermission } = useAuth()
  const podeTransf = hasPermission('sil.transferencia.edit'), podeExecT = hasPermission('sil.transferencia.executar')
  const podeDev = hasPermission('sil.devolucao.edit'), podeExecD = hasPermission('sil.devolucao.executar')
  const [novaT, setNovaT] = useState(false), [novaD, setNovaD] = useState(false)
  const { data: transf } = transferenciasHooks.useList({ page_size: 30 })
  const { data: dev } = devolucoesHooks.useList({ page_size: 30 })
  const execT = useExecutarTransferencia(), execD = useExecutarDevolucao()
  const ts = (transf?.results ?? []) as Transferencia[], ds = (dev?.results ?? []) as Devolucao[]
  return (
    <>
      <SectHead right={podeTransf ? <Btn variant="primary" style={{ padding: '6px 12px', fontSize: 12.5 }} onClick={() => setNovaT(true)}><ArrowLeftRight size={14} /> Nova transferência</Btn> : undefined}>Transferências entre locais</SectHead>
      {ts.length === 0 ? <Empty>Nenhuma transferência. Mova material entre almoxarifado e canteiros.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 680 }}>
            <thead><tr>{['Transf.', 'Origem', 'Destino', 'Itens', 'Estado', ''].map((h, i) => <th key={i} style={th(h, i, n => n === 3)}>{h}</th>)}</tr></thead>
            <tbody>{ts.map((t, i) => (
              <tr key={t.transferencia_id} style={{ borderBottom: i < ts.length - 1 ? '1px solid var(--line-2)' : undefined }}>
                <td style={{ ...mono, padding: '12px 16px', fontWeight: 700, color: 'var(--ink)' }}>#{t.transferencia_id}</td>
                <td style={{ padding: '12px 16px', color: 'var(--ink-2)', fontSize: 12.5 }}>{t.origem_nome ?? `#${t.origem}`}</td>
                <td style={{ padding: '12px 16px', color: 'var(--ink-2)', fontSize: 12.5 }}>{t.destino_nome ?? `#${t.destino}`}</td>
                <td style={{ ...mono, padding: '12px 16px', textAlign: 'right', color: 'var(--ink-2)' }}>{t.itens_count ?? 0}</td>
                <td style={{ padding: '12px 16px' }}><EstadoPill e={transferenciaEstado[t.status]} /></td>
                <td style={{ padding: '12px 16px', textAlign: 'right' }}>{podeExecT && t.status === 'rascunho' && <Btn variant="primary" style={{ padding: '5px 10px', fontSize: 12 }} disabled={execT.isPending} onClick={async () => { try { await execT.mutateAsync(t.transferencia_id); say('Transferência executada') } catch { say('Saldo insuficiente na origem') } }}><Check size={12} /> Executar</Btn>}</td>
              </tr>
            ))}</tbody>
          </table></div>
        </Card>
      )}
      <SectHead right={podeDev ? <Btn variant="primary" style={{ padding: '6px 12px', fontSize: 12.5 }} onClick={() => setNovaD(true)}><RotateCcw size={14} /> Nova devolução</Btn> : undefined}>Devoluções</SectHead>
      {ds.length === 0 ? <Empty>Nenhuma devolução. Devolva ao fornecedor (saída) ou estorne ao estoque (entrada).</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 680 }}>
            <thead><tr>{['Devolução', 'Tipo', 'Local', 'Fornecedor', 'Estado', ''].map((h, i) => <th key={i} style={th(h, i)}>{h}</th>)}</tr></thead>
            <tbody>{ds.map((dv, i) => (
              <tr key={dv.devolucao_id} style={{ borderBottom: i < ds.length - 1 ? '1px solid var(--line-2)' : undefined }}>
                <td style={{ ...mono, padding: '12px 16px', fontWeight: 700, color: 'var(--ink)' }}>#{dv.devolucao_id}</td>
                <td style={{ padding: '12px 16px' }}><Pill kind={dv.tipo === 'fornecedor' ? 'net' : 'info'}>{dv.tipo === 'fornecedor' ? 'Ao fornecedor' : 'Ao estoque'}</Pill></td>
                <td style={{ padding: '12px 16px', color: 'var(--ink-2)', fontSize: 12.5 }}>{dv.local_nome ?? `#${dv.local}`}</td>
                <td style={{ padding: '12px 16px', color: 'var(--ink-2)', fontSize: 12.5 }}>{dv.fornecedor_nome ?? '—'}</td>
                <td style={{ padding: '12px 16px' }}><EstadoPill e={devolucaoEstado[dv.status]} /></td>
                <td style={{ padding: '12px 16px', textAlign: 'right' }}>{podeExecD && dv.status === 'rascunho' && <Btn variant="primary" style={{ padding: '5px 10px', fontSize: 12 }} disabled={execD.isPending} onClick={async () => { try { await execD.mutateAsync(dv.devolucao_id); say('Devolução executada') } catch { say('Saldo insuficiente') } }}><Check size={12} /> Executar</Btn>}</td>
              </tr>
            ))}</tbody>
          </table></div>
        </Card>
      )}
      {novaT && <NovaTransferenciaModal onClose={() => setNovaT(false)} onDone={() => { setNovaT(false); say('Transferência criada (rascunho)') }} />}
      {novaD && <NovaDevolucaoModal onClose={() => setNovaD(false)} onDone={() => { setNovaD(false); say('Devolução criada (rascunho)') }} />}
    </>
  )
}
function NovaTransferenciaModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const qc = useQueryClient()
  const { data: locais } = locaisHooks.useAll({ ativo: true })
  const { data: itens } = itensHooks.useAll({ estocavel: true })
  const [origem, setOrigem] = useState(''), [destino, setDestino] = useState('')
  const [linhas, setLinhas] = useState<Linha[]>([{ item: '', quantidade: '', key: Date.now() }])
  const [saving, setSaving] = useState(false), [err, setErr] = useState('')
  const opLocais = (locais ?? []) as LocalEstoque[], opItens = (itens ?? []) as Item[]
  const salvar = async () => {
    setErr('')
    const validas = linhas.filter(l => l.item && (num(l.quantidade) ?? 0) > 0)
    if (!origem || !destino) return setErr('Escolha origem e destino.')
    if (origem === destino) return setErr('Origem e destino devem ser diferentes.')
    if (validas.length === 0) return setErr('Adicione ao menos um item.')
    setSaving(true)
    try {
      const t = await transferenciasApi.create({ origem: Number(origem), destino: Number(destino) })
      const tid = (t as Transferencia).transferencia_id
      for (const l of validas) await itensTransferenciaApi.create({ transferencia: tid, item: Number(l.item), quantidade: l.quantidade })
      await qc.invalidateQueries({ queryKey: silKeys.all }); onDone()
    } catch { setErr('Falha ao criar transferência.'); setSaving(false) }
  }
  return <Modal title="Nova transferência" onClose={onClose} wide footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={saving}>{saving ? 'Salvando…' : 'Criar (rascunho)'}</Btn></>}>
    {err && <div style={errBox}>{err}</div>}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Origem"><select style={inp} value={origem} onChange={e => setOrigem(e.target.value)}><option value="">— selecione —</option>{opLocais.map(l => <option key={l.local_id} value={l.local_id}>{l.nome}</option>)}</select></Field>
      <Field label="Destino"><select style={inp} value={destino} onChange={e => setDestino(e.target.value)}><option value="">— selecione —</option>{opLocais.map(l => <option key={l.local_id} value={l.local_id}>{l.nome}</option>)}</select></Field>
    </div>
    <ItemLines linhas={linhas} setLinhas={setLinhas} itens={opItens} />
    <p style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>Criada em rascunho; o custo médio é preservado ao executar.</p>
  </Modal>
}
function NovaDevolucaoModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const qc = useQueryClient()
  const { data: locais } = locaisHooks.useAll({ ativo: true })
  const { data: itens } = itensHooks.useAll({ estocavel: true })
  const { data: fornecedores } = useFornecedores()
  const [tipo, setTipo] = useState('fornecedor'), [local, setLocal] = useState(''), [fornecedor, setFornecedor] = useState('')
  const [linhas, setLinhas] = useState<Linha[]>([{ item: '', quantidade: '', key: Date.now() }])
  const [saving, setSaving] = useState(false), [err, setErr] = useState('')
  const opLocais = (locais ?? []) as LocalEstoque[], opItens = (itens ?? []) as Item[]
  const salvar = async () => {
    setErr('')
    const validas = linhas.filter(l => l.item && (num(l.quantidade) ?? 0) > 0)
    if (!local) return setErr('Escolha o local.')
    if (validas.length === 0) return setErr('Adicione ao menos um item.')
    setSaving(true)
    try {
      const dv = await devolucoesApi.create({ tipo, local: Number(local), fornecedor: fornecedor ? Number(fornecedor) : null })
      const did = (dv as Devolucao).devolucao_id
      for (const l of validas) await itensDevolucaoApi.create({ devolucao: did, item: Number(l.item), quantidade: l.quantidade })
      await qc.invalidateQueries({ queryKey: silKeys.all }); onDone()
    } catch { setErr('Falha ao criar devolução.'); setSaving(false) }
  }
  return <Modal title="Nova devolução" onClose={onClose} wide footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={saving}>{saving ? 'Salvando…' : 'Criar (rascunho)'}</Btn></>}>
    {err && <div style={errBox}>{err}</div>}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Tipo"><select style={inp} value={tipo} onChange={e => setTipo(e.target.value)}><option value="fornecedor">Ao fornecedor (saída)</option><option value="estoque">Ao estoque (entrada)</option></select></Field>
      <Field label="Local"><select style={inp} value={local} onChange={e => setLocal(e.target.value)}><option value="">— selecione —</option>{opLocais.map(l => <option key={l.local_id} value={l.local_id}>{l.nome}</option>)}</select></Field>
    </div>
    {tipo === 'fornecedor' && <Field label="Fornecedor"><select style={inp} value={fornecedor} onChange={e => setFornecedor(e.target.value)}><option value="">— nenhum —</option>{(fornecedores ?? []).map(f => <option key={f.fornecedor_id} value={f.fornecedor_id}>{f.razao_social}</option>)}</select></Field>}
    <ItemLines linhas={linhas} setLinhas={setLinhas} itens={opItens} />
  </Modal>
}

/* ═══════════ INVENTÁRIO ═══════════ */
export function Inventario({ say }: { say: Say }) {
  const [sel, setSel] = useState<number | null>(null)
  return sel != null ? <InventarioDetail id={sel} onBack={() => setSel(null)} say={say} /> : <InventarioList onOpen={setSel} say={say} />
}
function InventarioList({ onOpen, say }: { onOpen: (id: number) => void; say: Say }) {
  const { hasPermission } = useAuth()
  const podeInv = hasPermission('sil.inventario.edit')
  const [novo, setNovo] = useState(false)
  const { data, isLoading } = inventariosHooks.useList({ page_size: 40 })
  const rows = (data?.results ?? []) as Inventario[]
  return (
    <>
      <SectHead right={podeInv ? <Btn variant="primary" style={{ padding: '6px 12px', fontSize: 12.5 }} onClick={() => setNovo(true)}><Plus size={14} /> Novo inventário</Btn> : undefined}>Inventários</SectHead>
      {isLoading ? <Loading /> : rows.length === 0 ? <Empty>Nenhum inventário. Conte o estoque e feche para gerar os ajustes.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 640 }}>
            <thead><tr>{['Inventário', 'Local', 'Tipo', 'Itens', 'Estado', ''].map((h, i) => <th key={i} style={th(h, i, n => n === 3)}>{h}</th>)}</tr></thead>
            <tbody>{rows.map((iv, i) => (
              <tr key={iv.inventario_id} className="sil-row" style={{ cursor: 'pointer', borderBottom: i < rows.length - 1 ? '1px solid var(--line-2)' : undefined }} onClick={() => onOpen(iv.inventario_id)}>
                <td style={{ ...mono, padding: '12px 16px', fontWeight: 700, color: 'var(--ink)' }}>#{iv.inventario_id}</td>
                <td style={{ padding: '12px 16px', color: 'var(--ink-2)', fontSize: 12.5 }}>{iv.local_nome ?? `#${iv.local}`}</td>
                <td style={{ padding: '12px 16px', color: 'var(--ink-2)', fontSize: 12.5, textTransform: 'capitalize' }}>{iv.tipo}</td>
                <td style={{ ...mono, padding: '12px 16px', textAlign: 'right', color: 'var(--ink-2)' }}>{iv.itens_count ?? 0}</td>
                <td style={{ padding: '12px 16px' }}><EstadoPill e={inventarioEstado[iv.status]} /></td>
                <td style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--ink-3)' }}><ChevronRight size={15} /></td>
              </tr>
            ))}</tbody>
          </table></div>
        </Card>
      )}
      {novo && <NovoInventarioModal onClose={() => setNovo(false)} onDone={id => { setNovo(false); say('Inventário aberto'); onOpen(id) }} />}
    </>
  )
}
function NovoInventarioModal({ onClose, onDone }: { onClose: () => void; onDone: (id: number) => void }) {
  const create = inventariosHooks.useCreate()
  const { data: locais } = locaisHooks.useAll({ ativo: true })
  const [local, setLocal] = useState(''), [tipo, setTipo] = useState('ciclica'), [err, setErr] = useState('')
  const opLocais = (locais ?? []) as LocalEstoque[]
  const salvar = async () => {
    if (!local) return setErr('Escolha o local.')
    try { const iv = await create.mutateAsync({ local: Number(local), tipo }); onDone((iv as Inventario).inventario_id) }
    catch { setErr('Falha ao abrir inventário.') }
  }
  return <Modal title="Novo inventário" onClose={onClose} footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={create.isPending}>Abrir contagem</Btn></>}>
    {err && <div style={errBox}>{err}</div>}
    <Field label="Local"><select style={inp} value={local} onChange={e => setLocal(e.target.value)}><option value="">— selecione —</option>{opLocais.map(l => <option key={l.local_id} value={l.local_id}>{l.nome}</option>)}</select></Field>
    <Field label="Tipo"><select style={inp} value={tipo} onChange={e => setTipo(e.target.value)}><option value="ciclica">Cíclica</option><option value="geral">Geral</option></select></Field>
  </Modal>
}
function InventarioDetail({ id, onBack, say }: { id: number; onBack: () => void; say: Say }) {
  const { hasPermission } = useAuth()
  const qc = useQueryClient()
  const podeInv = hasPermission('sil.inventario.edit'), podeFechar = hasPermission('sil.inventario.fechar')
  const { data: inv, isLoading } = inventariosHooks.useDetail(id)
  const { data: linhas } = itensInventarioHooks.useAll({ inventario: id })
  const { data: itens } = itensHooks.useAll({ estocavel: true })
  const fechar = useFecharInventario()
  const reabrir = useReabrirInventario()
  const [add, setAdd] = useState(false)
  const [erro, setErro] = useState('')
  if (isLoading || !inv) return <Loading />
  const linhasL = (linhas ?? []) as ItemInventario[]
  const aberto = inv.status === 'aberto'
  const detalhe = (e: unknown) =>
    (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Não foi possível concluir.'
  async function agir(acao: () => Promise<unknown>, recado: string) {
    setErro('')
    try { await acao(); say(recado) } catch (e) { setErro(detalhe(e)) }
  }
  async function excluirContagem() {
    if (!window.confirm(`Excluir o inventário #${inv!.inventario_id} e as ${linhasL.length} linha(s) contadas?`)) return
    await agir(async () => { await inventariosApi.remove(inv!.inventario_id); await qc.invalidateQueries({ queryKey: silKeys.all }); onBack() }, 'Inventário excluído')
  }
  async function tirarLinha(id: number) {
    await agir(async () => { await itensInventarioApi.remove(id); await qc.invalidateQueries({ queryKey: silKeys.all }) }, 'Linha removida da contagem')
  }
  return (
    <div style={{ maxWidth: 900 }}>
      <button onClick={onBack} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--ink-3)', background: 'none', border: 'none', cursor: 'pointer', marginBottom: 6 }}><ArrowLeft size={13} /> Todos os inventários</button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 19, fontWeight: 750, letterSpacing: '-0.02em', color: 'var(--ink)' }}>Inventário #{inv.inventario_id}</h2>
        <EstadoPill e={inventarioEstado[inv.status]} /><span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>{inv.local_nome}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 9 }}>
          {aberto && podeInv && <Btn onClick={() => setAdd(true)}><ClipboardCheck size={14} /> Adicionar contagem</Btn>}
          {aberto && podeInv && <Btn onClick={() => void excluirContagem()}><Trash2 size={14} /> Excluir</Btn>}
          {aberto && podeFechar && linhasL.length > 0 && <Btn variant="primary" disabled={fechar.isPending} onClick={() => void agir(() => fechar.mutateAsync(inv.inventario_id), 'Inventário fechado (ajustes gerados)')}><Check size={14} /> Fechar (gera ajustes)</Btn>}
          {!aberto && podeFechar && <Btn disabled={reabrir.isPending} onClick={() => void agir(() => reabrir.mutateAsync(inv.inventario_id), 'Inventário reaberto (ajustes estornados)')}><RotateCcw size={14} /> Reabrir</Btn>}
        </div>
      </div>
      {erro && <div style={{ ...errBox, marginBottom: 12 }}>{erro}</div>}
      {linhasL.length === 0 ? <Empty>Nenhuma linha contada. Adicione itens à contagem.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead><tr>{['Item', 'Sistema', 'Contado', 'Diferença', ''].map((h, i) => <th key={i} style={th(h, i, n => n >= 1)}>{h}</th>)}</tr></thead>
          <tbody>{linhasL.map((l, i) => { const dif = num(l.diferenca) ?? 0; return (
            <tr key={l.item_inventario_id} style={{ borderBottom: i < linhasL.length - 1 ? '1px solid var(--line-2)' : undefined }}>
              <td style={{ padding: '11px 16px', color: 'var(--ink)' }}>{l.item_descricao ?? `#${l.item}`}</td>
              <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', color: 'var(--ink-2)' }}>{qty(l.quantidade_sistema)}</td>
              <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', fontWeight: 600, color: 'var(--ink)' }}>{qty(l.quantidade_contada)}</td>
              <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', fontWeight: 600, color: dif === 0 ? 'var(--ink-3)' : dif > 0 ? 'var(--good-ink)' : 'var(--danger-ink)' }}>{dif > 0 ? '+' : ''}{qty(l.diferenca)}</td>
              <td style={{ padding: '6px 12px', textAlign: 'right', width: 40 }}>{aberto && podeInv && <button type="button" title="Tirar da contagem" aria-label={`Tirar ${l.item_descricao ?? l.item} da contagem`} onClick={() => void tirarLinha(l.item_inventario_id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)', display: 'inline-flex' }}><Trash2 size={14} /></button>}</td>
            </tr>
          ) })}</tbody>
        </table></Card>
      )}
      {add && <AddContagemModal inventarioId={id} itens={(itens ?? []) as Item[]} onClose={() => setAdd(false)} onDone={async () => { setAdd(false); await qc.invalidateQueries({ queryKey: silKeys.all }); say('Contagem adicionada') }} />}
    </div>
  )
}
function AddContagemModal({ inventarioId, itens, onClose, onDone }: { inventarioId: number; itens: Item[]; onClose: () => void; onDone: () => void }) {
  const [item, setItem] = useState(''), [sistema, setSistema] = useState('0'), [contada, setContada] = useState('')
  const [saving, setSaving] = useState(false), [err, setErr] = useState('')
  const salvar = async () => {
    if (!item) return setErr('Escolha o item.')
    setSaving(true)
    try { await itensInventarioApi.create({ inventario: inventarioId, item: Number(item), quantidade_sistema: sistema, quantidade_contada: contada || '0' }); onDone() }
    catch { setErr('Falha ao adicionar.'); setSaving(false) }
  }
  return <Modal title="Adicionar contagem" onClose={onClose} footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={saving}>Adicionar</Btn></>}>
    {err && <div style={errBox}>{err}</div>}
    <Field label="Item"><select style={inp} value={item} onChange={e => setItem(e.target.value)}><option value="">— selecione —</option>{itens.map(i => <option key={i.item_id} value={i.item_id}>{i.codigo_interno} · {i.descricao}</option>)}</select></Field>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <Field label="Qtd. no sistema"><input style={{ ...inp, ...mono }} type="number" step="0.001" value={sistema} onChange={e => setSistema(e.target.value)} /></Field>
      <Field label="Qtd. contada"><input style={{ ...inp, ...mono }} type="number" step="0.001" value={contada} onChange={e => setContada(e.target.value)} placeholder="0" /></Field>
    </div>
  </Modal>
}

/* ═══════════ editor de linhas de item (compartilhado) ═══════════ */
export interface Linha { item: number | string; quantidade: string; key: number }
export function ItemLines({ linhas, setLinhas, itens }: { linhas: Linha[]; setLinhas: (l: Linha[]) => void; itens: Item[] }) {
  const set = (key: number, patch: Partial<Linha>) => setLinhas(linhas.map(l => l.key === key ? { ...l, ...patch } : l))
  const add = () => setLinhas([...linhas, { item: '', quantidade: '', key: Date.now() + Math.random() }])
  const rm = (key: number) => setLinhas(linhas.length > 1 ? linhas.filter(l => l.key !== key) : linhas)
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ ...CAPS, fontSize: 10.5, marginBottom: 6 }}>Itens</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {linhas.map(l => (
          <div key={l.key} style={{ display: 'grid', gridTemplateColumns: '1fr 110px 34px', gap: 8 }}>
            <select style={inp} value={l.item} onChange={e => set(l.key, { item: e.target.value })}><option value="">— item —</option>{itens.map(i => <option key={i.item_id} value={i.item_id}>{i.codigo_interno} · {i.descricao}</option>)}</select>
            <input style={{ ...inp, ...mono }} type="number" min={0} step="0.001" value={l.quantidade} onChange={e => set(l.key, { quantidade: e.target.value })} placeholder="Qtd." />
            <button onClick={() => rm(l.key)} style={{ background: 'var(--surface-2)', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', color: 'var(--ink-3)', cursor: 'pointer', display: 'grid', placeItems: 'center' }}><Trash2 size={14} /></button>
          </div>
        ))}
      </div>
      <button onClick={add} style={{ marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, fontWeight: 600, color: 'var(--net-ink)', background: 'none', border: 'none', cursor: 'pointer' }}><Plus size={14} /> adicionar item</button>
    </div>
  )
}
