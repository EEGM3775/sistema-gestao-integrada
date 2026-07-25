import { useState, useMemo, type ReactNode } from 'react'
import {
  Layers, Coins, AlertTriangle, Send, TrendingUp, Lock, Upload, LineChart,
  Store, BadgeCheck, ArrowLeftRight, Warehouse, Boxes, Building2,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useCurvaABC, useAplicado, useObras, saldosHooks, useSilDashboard, useGerarDemanda } from '../hooks'
import { brl, qty, num, abcKind } from '../lib'
import { mono, CAPS, inp, KIND, Pill, Card, Btn, SectHead, Loading, Empty, th, type Say } from '../ui'
import type { CurvaABCItem, AplicadoLinha, SaldoEstoque } from '../types'

/* ═══════════ CURVA ABC ═══════════ */
export function CurvaABC() {
  const { data, isLoading } = useCurvaABC()
  if (isLoading || !data) return <Loading />
  const total = num(data.total) ?? 0
  const cards = (['A', 'B', 'C'] as const).map(c => ({ classe: c, ...data.resumo[c], pct: total > 0 ? ((num(data.resumo[c].valor) ?? 0) / total * 100) : 0 }))
  const rows = data.itens as CurvaABCItem[]
  return (
    <>
      <div style={{ display: 'flex', gap: 12, padding: '13px 16px', borderRadius: 'var(--r-md)', background: 'var(--surface-2)', border: '1px solid var(--line)', marginBottom: 4 }}>
        <Layers size={20} style={{ color: 'var(--ink-2)', flex: 'none' }} />
        <span style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.5 }}>A <b>curva ABC</b> classifica os itens pelo peso no valor em estoque. A <b>Classe A</b> concentra ~80% do custo em poucos itens — é onde o controle rende mais. Priorize contagem, ponto de reposição e negociação nesses itens.</span>
      </div>
      <SectHead right={<span style={{ ...mono, fontSize: 13, color: 'var(--ink-2)' }}>total {brl(data.total)}</span>}>Classificação por valor</SectHead>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14, marginBottom: 4 }}>
        {cards.map(c => (
          <Card key={c.classe} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <span style={{ width: 30, height: 30, borderRadius: 8, display: 'grid', placeItems: 'center', fontWeight: 800, fontFamily: 'var(--display)', background: KIND[abcKind[c.classe]][0], color: KIND[abcKind[c.classe]][1] }}>{c.classe}</span>
              <span style={{ ...CAPS, fontSize: 11 }}>Classe {c.classe}</span>
              <span style={{ marginLeft: 'auto', ...mono, fontSize: 13, fontWeight: 700, color: 'var(--ink)' }}>{c.pct.toFixed(0)}%</span>
            </div>
            <div style={{ ...mono, fontSize: 22, fontWeight: 750, letterSpacing: '-0.02em', color: 'var(--ink)' }}>{brl(c.valor)}</div>
            <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>{c.itens} item(ns)</div>
            <div style={{ height: 6, borderRadius: 999, background: 'var(--inset)', overflow: 'hidden', marginTop: 2 }}><span style={{ display: 'block', height: '100%', width: `${c.pct}%`, background: KIND[abcKind[c.classe]][1] }} /></div>
          </Card>
        ))}
      </div>
      {rows.length === 0 ? <Empty>Sem itens em estoque para classificar.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden', marginTop: 14 }}>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 760 }}>
            <thead><tr>{['Classe', 'Item', 'Qtd.', 'Valor', '% do total', '% acumulado'].map((h, i) => <th key={i} style={th(h, i, n => n >= 2)}>{h}</th>)}</tr></thead>
            <tbody>{rows.map((it, i) => (
              <tr key={it.item} style={{ borderBottom: i < rows.length - 1 ? '1px solid var(--line-2)' : undefined }}>
                <td style={{ padding: '10px 16px' }}><span style={{ display: 'inline-grid', placeItems: 'center', width: 24, height: 24, borderRadius: 6, fontWeight: 800, fontSize: 12, fontFamily: 'var(--display)', background: KIND[abcKind[it.classe]][0], color: KIND[abcKind[it.classe]][1] }}>{it.classe}</span></td>
                <td style={{ padding: '10px 16px' }}><div style={{ color: 'var(--ink)' }}>{it.descricao}</div><span style={{ ...mono, fontSize: 11, color: 'var(--ink-3)' }}>{it.codigo}</span></td>
                <td style={{ ...mono, padding: '10px 16px', textAlign: 'right', color: 'var(--ink-2)' }}>{qty(it.quantidade)} <small style={{ color: 'var(--ink-3)' }}>{it.unidade}</small></td>
                <td style={{ ...mono, padding: '10px 16px', textAlign: 'right', fontWeight: 700, color: 'var(--ink)' }}>{brl(it.valor)}</td>
                <td style={{ ...mono, padding: '10px 16px', textAlign: 'right', color: 'var(--ink-2)' }}>{Number(it.pct).toFixed(1)}%</td>
                <td style={{ ...mono, padding: '10px 16px', textAlign: 'right', color: 'var(--ink-3)' }}>{Number(it.pct_acumulado).toFixed(1)}%</td>
              </tr>
            ))}</tbody>
          </table></div>
        </Card>
      )}
    </>
  )
}

/* ═══════════ CUSTO POR OBRA — ORÇADO × APLICADO ═══════════ */
export function CustoPorObra() {
  const { data: obras } = useObras()
  const [obra, setObra] = useState('')
  const { data, isLoading } = useAplicado(obra ? Number(obra) : undefined)
  const linhas = (data ?? []) as AplicadoLinha[]
  // Agrupa por obra → etapas.
  const grupos = useMemo(() => {
    const m = new Map<string, { obra: string; total: number; etapas: AplicadoLinha[] }>()
    for (const l of linhas) {
      const key = l.obra_nome ?? '— sem obra —'
      const g = m.get(key) ?? { obra: key, total: 0, etapas: [] }
      g.total += num(l.aplicado) ?? 0
      g.etapas.push(l)
      m.set(key, g)
    }
    return [...m.values()]
  }, [linhas])

  return (
    <>
      <div style={{ display: 'flex', gap: 12, padding: '14px 16px', borderRadius: 'var(--r-md)', background: 'linear-gradient(120deg,var(--accent-soft),var(--surface) 80%)', border: '1px solid color-mix(in srgb,var(--accent) 30%,var(--line))', marginBottom: 4 }}>
        <TrendingUp size={20} style={{ color: 'var(--accent-ink)', flex: 'none' }} />
        <span style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>O <b>físico-financeiro</b> da obra: quanto de material foi <b>aplicado</b> (consumido, valorizado pelo custo médio) por obra e etapa. O <b>orçado</b> — o outro lado da comparação — vem do <b>módulo Orçamento</b> (planejado); aqui aparece como <i>em breve</i>. É a base do "a obra está estourando o material?".</span>
      </div>
      <SectHead right={<select value={obra} onChange={e => setObra(e.target.value)} style={{ ...inp, width: 'auto', padding: '7px 10px' }}><option value="">Todas as obras</option>{(obras ?? []).map(o => <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>)}</select>}>Aplicado por obra e etapa</SectHead>
      {isLoading ? <Loading /> : grupos.length === 0 ? <Empty>Nenhum consumo apropriado a obra ainda. Atenda uma requisição ou registre uma saída com obra/etapa.</Empty> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {grupos.map(g => (
            <Card key={g.obra} pad={false} style={{ overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '13px 16px', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' }}>
                <Building2 size={16} style={{ color: 'var(--ink-2)' }} />
                <b style={{ fontSize: 14, color: 'var(--ink)' }}>{g.obra}</b>
                <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 14 }}>
                  <span style={{ ...CAPS, fontSize: 10 }}>Aplicado</span>
                  <span style={{ ...mono, fontSize: 18, fontWeight: 750, color: 'var(--ink)' }}>{brl(g.total)}</span>
                </span>
              </div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead><tr>{['Etapa', 'Aplicado', 'Orçado', 'Saldo'].map((h, i) => <th key={i} style={th(h, i, n => n >= 1)}>{h}</th>)}</tr></thead>
                <tbody>{g.etapas.map((e, i) => (
                  <tr key={i} style={{ borderBottom: i < g.etapas.length - 1 ? '1px solid var(--line-2)' : undefined }}>
                    <td style={{ padding: '10px 16px', color: 'var(--ink)' }}>{e.etapa_nome}</td>
                    <td style={{ ...mono, padding: '10px 16px', textAlign: 'right', fontWeight: 600, color: 'var(--ink)' }}>{brl(e.aplicado)}</td>
                    <td style={{ padding: '10px 16px', textAlign: 'right' }}><Pill kind="net">em breve · Orçamento</Pill></td>
                    <td style={{ ...mono, padding: '10px 16px', textAlign: 'right', color: 'var(--ink-3)' }}>—</td>
                  </tr>
                ))}</tbody>
              </table>
            </Card>
          ))}
        </div>
      )}
    </>
  )
}

/* ═══════════ GIRO & RUPTURA ═══════════ */
export function GiroRuptura({ say }: { say: Say }) {
  const { hasPermission } = useAuth()
  const podeSaldo = hasPermission('sil.saldo.edit')
  const { data: d } = useSilDashboard()
  const { data: baixoData, isLoading } = saldosHooks.useList({ abaixo_minimo: 1, page_size: 100 })
  const gerar = useGerarDemanda()
  const rupturas = (baixoData?.results ?? []) as SaldoEstoque[]
  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: 14, marginBottom: 4 }}>
        <Kpi icon={<Coins size={14} />} label="Valor imobilizado" value={brl(d?.valorEstoque)} foot={`${d?.itensEmEstoque ?? 0} itens em estoque`} />
        <Kpi icon={<AlertTriangle size={14} />} label="Itens em ruptura" value={String(d?.abaixoMinimo ?? 0)} foot="abaixo do ponto de reposição" accent={(d?.abaixoMinimo ?? 0) > 0} />
        <Kpi icon={<Layers size={14} />} label="Locais ativos" value={String(d?.locais ?? 0)} foot="almoxarifados e canteiros" />
      </div>
      <SectHead right={<span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>giro histórico e benchmark → Esfera de Rede</span>}>Ruptura de estoque</SectHead>
      {isLoading ? <Loading /> : rupturas.length === 0 ? <Empty>Nenhum item em ruptura. Estoque coberto.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 640 }}>
            <thead><tr>{['Item', 'Local', 'Saldo', 'Mínimo', ''].map((h, i) => <th key={i} style={th(h, i, n => n === 2 || n === 3)}>{h}</th>)}</tr></thead>
            <tbody>{rupturas.map((s, i) => (
              <tr key={s.saldo_id} style={{ borderBottom: i < rupturas.length - 1 ? '1px solid var(--line-2)' : undefined, background: 'var(--accent-soft)' }}>
                <td style={{ padding: '11px 16px' }}><div style={{ fontWeight: 550, color: 'var(--ink)' }}>{s.item_descricao ?? `#${s.item}`}</div><span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)' }}>{s.item_codigo ?? ''}</span></td>
                <td style={{ padding: '11px 16px', color: 'var(--ink-2)', fontSize: 12.5 }}>{s.local_nome}</td>
                <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', fontWeight: 700, color: 'var(--danger-ink)' }}>{qty(s.quantidade)}</td>
                <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', color: 'var(--ink-2)' }}>{qty(s.ponto_reposicao)}</td>
                <td style={{ padding: '11px 16px', textAlign: 'right' }}>{podeSaldo && <Btn variant="primary" style={{ padding: '5px 10px', fontSize: 12 }} disabled={gerar.isPending} onClick={async () => { await gerar.mutateAsync({ saldo: s.saldo_id }); say('Demanda gerada no SCM') }}><Send size={12} /> Repor</Btn>}</td>
              </tr>
            ))}</tbody>
          </table></div>
        </Card>
      )}
    </>
  )
}
function Kpi({ icon, label, value, foot, accent }: { icon: ReactNode; label: string; value: ReactNode; foot?: ReactNode; accent?: boolean }) {
  return (
    <Card pad={false} style={{ padding: '16px 18px', ...(accent ? { background: 'linear-gradient(135deg,var(--accent-soft),var(--surface))', borderColor: 'color-mix(in srgb,var(--accent) 40%,var(--line))' } : {}) }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: 'var(--ink-3)', fontWeight: 600 }}>{icon} {label}</div>
      <div style={{ ...mono, fontSize: 26, fontWeight: 750, letterSpacing: '-0.03em', marginTop: 8, color: 'var(--ink)' }}>{value}</div>
      {foot && <div style={{ marginTop: 6, fontSize: 11.5, color: 'var(--ink-3)' }}>{foot}</div>}
    </Card>
  )
}

/* ═══════════ ESFERA DE REDE (teaser) ═══════════ */
export function Rede() {
  return (
    <>
      <div style={{ padding: '30px 30px 28px', borderRadius: 'var(--r-xl)', position: 'relative', overflow: 'hidden', background: 'linear-gradient(125deg,var(--brand),#08203f 60%,#0a2c5e)', color: '#EAF1FC', border: '1px solid var(--brand-2)' }}>
        <div style={{ position: 'absolute', right: -60, top: -60, width: 260, height: 260, borderRadius: 999, background: 'radial-gradient(circle,rgba(15,138,147,.5),transparent 65%)' }} />
        <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#7FE0E6', background: 'rgba(15,138,147,.18)', border: '1px solid rgba(43,182,191,.35)', padding: '5px 12px', borderRadius: 999 }}><Lock size={12} /> Bloqueado · em construção — Horizonte H2–H3</span>
        <h2 style={{ position: 'relative', fontSize: 26, fontWeight: 750, letterSpacing: '-0.03em', margin: '16px 0 8px', maxWidth: 560, color: '#fff' }}>Do estoque parado ao giro da rede inteira.</h2>
        <p style={{ position: 'relative', color: '#B3C6E4', fontSize: 14, maxWidth: 600, lineHeight: 1.6 }}>Hoje o estoque abaixo do mínimo já vira <b style={{ color: '#EAF1FC' }}>Demanda</b> no seu SCM. Na <b style={{ color: '#EAF1FC' }}>Esfera de Rede</b>, essa reposição sai como RFQ automática para as lojas da região, o giro dos seus itens vira benchmark k-anônimo e o estoque ocioso de um canteiro encontra comprador em outro. O SIL já carrega os <i>seams</i>; esta aba mostra para onde a costura leva.</p>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 16, marginTop: 18 }}>
        <RoadCard icon={<Upload size={20} />} tag="H2" title="RFQ automática de reposição" seam="fonte: sil.estoque_minimo_atingido">O evento de item abaixo do mínimo dispara a cotação na rede sozinho — a reposição deixa de depender de alguém lembrar.</RoadCard>
        <RoadCard icon={<LineChart size={20} />} tag="H3" title="Benchmark de giro" seam="fonte: MovimentacaoEstoque">Cada saída alimenta um índice de giro por categoria e região. Você passa a saber qual item encalha e qual falta sempre.</RoadCard>
        <RoadCard icon={<Store size={20} />} tag="H3" title="Marketplace de ocioso" seam="fonte: SaldoEstoque">Saldo parado num canteiro vira oferta interna (ou pública) para outro — o ativo imobilizado volta a circular.</RoadCard>
      </div>
      <SectHead>O laço que já existe — SIL ↔ SCM</SectHead>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 44px 1fr', alignItems: 'stretch' }}>
        <MirrorSide color="var(--info)" ink="var(--info-ink)" title="SIL · estoque (você)" items={['Saldo abaixo do mínimo', 'Recebimento → ENTRADA automática', 'Consumo apropriado à obra/etapa (DRE)']} icon={<Warehouse size={13} />} />
        <div style={{ display: 'grid', placeItems: 'center', color: 'var(--net)' }}><ArrowLeftRight size={22} /></div>
        <MirrorSide color="var(--accent)" ink="var(--accent-ink)" title="SCM · suprimentos" items={['Demanda (origem: estoque)', 'Cotação / Pedido', 'Recebimento fecha o laço']} icon={<Boxes size={13} />} />
      </div>
      <div style={{ display: 'flex', gap: 12, padding: '14px 16px', borderRadius: 'var(--r-md)', background: 'var(--accent-soft)', border: '1px solid color-mix(in srgb,var(--accent) 35%,var(--line))', fontSize: 12.5, color: 'var(--accent-ink)', lineHeight: 1.55, marginTop: 18 }}>
        <AlertTriangle size={18} style={{ flex: 'none', marginTop: 1 }} /><span><b>Fronteira honesta:</b> a RFQ automática, o benchmark e o marketplace não estão construídos. O que já é real é o laço SIL↔SCM (recebimento vira entrada; falta vira demanda) — o resto gradua junto com a Esfera de Rede.</span>
      </div>
    </>
  )
}
function RoadCard({ icon, tag, title, seam, children }: { icon: ReactNode; tag: string; title: string; seam: string; children: ReactNode }) {
  return <Card style={{ display: 'flex', flexDirection: 'column', gap: 12 }}><div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}><div style={{ width: 40, height: 40, borderRadius: 'var(--r-md)', background: 'var(--net-soft)', color: 'var(--net-ink)', display: 'grid', placeItems: 'center' }}>{icon}</div><Pill kind={tag === 'H2' ? 'net' : 'slate'}>{tag}</Pill></div><h3 style={{ fontFamily: 'var(--display)', fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>{title}</h3><p style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>{children}</p><div style={{ fontSize: 11.5, color: 'var(--ink-3)', display: 'flex', alignItems: 'center', gap: 7, paddingTop: 11, borderTop: '1px solid var(--line-2)' }}><BadgeCheck size={13} style={{ color: 'var(--net)' }} /><code style={{ ...mono, fontSize: 11, background: 'var(--inset)', padding: '1px 6px', borderRadius: 5, color: 'var(--net-ink)' }}>{seam}</code></div></Card>
}
function MirrorSide({ color, ink, title, items, icon }: { color: string; ink: string; title: string; items: string[]; icon?: ReactNode }) {
  return <div style={{ padding: 18, borderRadius: 'var(--r-md)', border: `1px solid color-mix(in srgb,${color} 35%,var(--line))` }}><b style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em', color: ink, fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 6 }}>{icon}{title}</b><ul style={{ listStyle: 'none', marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>{items.map(it => <li key={it} style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 13, color: 'var(--ink-2)' }}><span style={{ width: 7, height: 7, borderRadius: 2, flex: 'none', background: color }} />{it}</li>)}</ul></div>
}
