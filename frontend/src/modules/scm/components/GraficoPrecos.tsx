/* Preço do item por fornecedor ao longo do tempo (dono, 16/10/2026) — dentro da
 * ficha do item. Cada compra paga é um ponto cheio ligado aos outros do mesmo
 * fornecedor; cada preço cotado é um ponto vazado da mesma cor. Sem média: o
 * ponto diz de qual pedido ou cotação veio.
 *
 * A tabela de lojas É a legenda: cor, checkbox para pôr ou tirar o fornecedor do
 * gráfico, preço de tabela e último pago — com rolagem, porque um item comum tem
 * muitas lojas. As compras uma a uma ficam recolhidas embaixo. */
import { useMemo, useState } from 'react'
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import { brl, dataBR, qty } from '../lib'
import { CAPS, mono } from './estilo'
import { Pill } from './ui'
import type { FichaItem } from '../types'

type Janela = '6m' | '12m' | 'tudo'

/** Paleta categórica em hex — atributo SVG não resolve `var(--...)` de forma confiável. */
const CORES = ['#2563eb', '#ea580c', '#16a34a', '#9333ea', '#0891b2', '#ca8a04', '#db2777', '#475569', '#65a30d', '#be123c']
const STATUS_COTACAO = { recebida: 'cotado', vencedora: 'cotado · vencedor', recusada: 'cotado · recusado' } as const

interface Ponto { t: number; preco: number; data: string; fornecedor: string; quantidade: string; origem: string }
interface Loja {
  k: string; nome: string; cor: string
  tabela: string | null; ultimoPago: string | null; ultimaCompra: string | null
  ultimoCotado: string | null; compraDireta: boolean; codigo: string
  pagos: Ponto[]; cotados: Ponto[]
}

const chave = (id: number | null, nome: string) => (id != null ? `f${id}` : `n${nome}`)
const tempo = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00`).getTime()
const mesAno = (t: number) => new Date(t).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' })
const th = { ...CAPS, fontSize: 10, textAlign: 'left' as const, padding: '7px 10px', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)', position: 'sticky' as const, top: 0, zIndex: 1 }
const td = { padding: '7px 10px', borderBottom: '1px solid var(--line-2)', fontSize: 12.5 }

export function PrecoPorFornecedor({ f }: { f: FichaItem }) {
  const [janela, setJanela] = useState<Janela>('tudo')
  const [ocultos, setOcultos] = useState<Set<string>>(new Set())
  const unidade = f.unidade

  const lojas = useMemo<Loja[]>(() => {
    const mapa = new Map<string, Omit<Loja, 'cor'>>()
    const loja = (k: string, nome: string) => {
      if (!mapa.has(k)) mapa.set(k, { k, nome, tabela: null, ultimoPago: null, ultimaCompra: null, ultimoCotado: null, compraDireta: false, codigo: '', pagos: [], cotados: [] })
      return mapa.get(k)!
    }
    for (const l of f.lojas) {
      Object.assign(loja(chave(l.fornecedor, l.fornecedor_nome), l.fornecedor_nome), {
        tabela: l.preco_oferta, ultimoPago: l.ultimo_preco_pago, ultimaCompra: l.ultima_compra,
        compraDireta: l.compra_direta, codigo: l.codigo_no_fornecedor,
      })
    }
    for (const p of f.grafico_precos.pagos) {
      loja(chave(p.fornecedor, p.fornecedor_nome), p.fornecedor_nome).pagos.push({
        t: tempo(p.data), preco: Number(p.preco_unitario), data: p.data, fornecedor: p.fornecedor_nome, quantidade: p.quantidade, origem: `Pedido #${p.pedido} · pago`,
      })
    }
    for (const c of f.grafico_precos.cotados) {
      const l = loja(chave(c.fornecedor, c.fornecedor_nome), c.fornecedor_nome)
      l.cotados.push({
        t: tempo(c.data), preco: Number(c.preco_unitario), data: c.data, fornecedor: c.fornecedor_nome, quantidade: c.quantidade, origem: `Cotação #${c.cotacao} · ${STATUS_COTACAO[c.status]}`,
      })
      l.ultimoCotado = c.preco_unitario  // a série vem em ordem cronológica: o último fica
    }
    return [...mapa.values()].map((l, i) => ({ ...l, cor: CORES[i % CORES.length] }))
  }, [f])

  const corte = janela === 'tudo' ? -Infinity : Date.now() - (janela === '6m' ? 183 : 365) * 86_400_000
  const visiveis = lojas
    .filter(l => !ocultos.has(l.k))
    .map(l => ({ ...l, pagos: l.pagos.filter(p => p.t >= corte), cotados: l.cotados.filter(p => p.t >= corte) }))
  const pontos = visiveis.flatMap(l => [...l.pagos, ...l.cotados])
  const pagos = visiveis.flatMap(l => l.pagos).sort((a, b) => a.t - b.t)
  const resumo = pagos.length > 0 ? {
    menor: Math.min(...pagos.map(p => p.preco)),
    maior: Math.max(...pagos.map(p => p.preco)),
    variacao: pagos.length > 1 ? (pagos.at(-1)!.preco - pagos[0].preco) / pagos[0].preco : null,
  } : null

  const alternar = (k: string) => setOcultos(o => { const n = new Set(o); if (n.has(k)) n.delete(k); else n.add(k); return n })
  const todos = ocultos.size === 0

  if (lojas.length === 0) {
    return <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Nenhum fornecedor vende este item ainda — sem compra nem cotação registrada.</div>
  }

  return (
    <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', background: 'var(--surface)' }}>
      <div style={{ padding: '10px 12px 4px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', marginBottom: 4 }}>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 12, color: 'var(--ink-2)' }}>
            {resumo ? (
              <>
                <span>menor pago <b style={mono}>{brl(resumo.menor)}</b></span>
                <span>maior pago <b style={mono}>{brl(resumo.maior)}</b></span>
                {resumo.variacao != null && (
                  <span title="Da primeira à última compra paga no período, nos fornecedores marcados">
                    variação <b style={{ ...mono, color: resumo.variacao > 0 ? 'var(--danger-ink)' : resumo.variacao < 0 ? 'var(--good-ink)' : 'var(--ink)' }}>
                      {resumo.variacao > 0 ? '+' : ''}{(resumo.variacao * 100).toFixed(1).replace('.', ',')}%
                    </b>
                  </span>
                )}
              </>
            ) : <span style={{ color: 'var(--ink-3)' }}>sem compra paga no período</span>}
          </div>
          <div role="group" aria-label="Período" style={{ display: 'inline-flex', background: 'var(--inset)', borderRadius: 7, padding: 2 }}>
            {(['6m', '12m', 'tudo'] as const).map(j => (
              <button key={j} type="button" aria-pressed={janela === j} onClick={() => setJanela(j)}
                style={{
                  border: 0, cursor: 'pointer', padding: '3px 9px', borderRadius: 5, fontSize: 11.5, fontWeight: 600,
                  background: janela === j ? 'var(--surface)' : 'transparent', color: janela === j ? 'var(--ink)' : 'var(--ink-3)',
                  boxShadow: janela === j ? 'var(--shadow-sm)' : 'none',
                }}>
                {j === 'tudo' ? 'Tudo' : j.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {pontos.length === 0 ? (
          <div style={{ fontSize: 12.5, color: 'var(--ink-3)', padding: '28px 0', textAlign: 'center' }}>
            {todos ? 'Nada neste período.' : 'Nenhum preço dos fornecedores marcados neste período.'}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <ScatterChart margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#94a3b833" vertical={false} />
              <XAxis type="number" dataKey="t" scale="time" domain={['dataMin', 'dataMax']} padding={{ left: 14, right: 14 }}
                tickFormatter={mesAno} tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={{ stroke: '#94a3b855' }} />
              <YAxis type="number" dataKey="preco" domain={['auto', 'auto']} width={70} tickFormatter={v => brl(v)}
                tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                content={({ active, payload }) => {
                  const p = active ? payload?.[0]?.payload as Ponto | undefined : undefined
                  if (!p) return null
                  return (
                    <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 8, padding: '7px 10px', fontSize: 12, boxShadow: 'var(--shadow-md)' }}>
                      <div style={{ fontWeight: 650, color: 'var(--ink)' }}>{p.fornecedor}</div>
                      <div style={{ color: 'var(--ink-3)' }}>{dataBR(p.data)} · {p.origem}</div>
                      <div style={{ ...mono, marginTop: 3, color: 'var(--ink)' }}>
                        <b>{brl(p.preco)}</b> / {unidade} <span style={{ color: 'var(--ink-3)' }}>· {qty(p.quantidade)} {unidade}</span>
                      </div>
                    </div>
                  )
                }}
              />
              {/* Scatter com `line` liga as compras do fornecedor e mantém o tooltip
                  por ponto — cada série tem datas próprias, sem eixo compartilhado. */}
              {visiveis.map(l => l.pagos.length > 0 && (
                <Scatter key={`${l.k}-pago`} data={l.pagos} name={l.nome} fill={l.cor}
                  line={{ stroke: l.cor, strokeWidth: 2 }} isAnimationActive={false} />
              ))}
              {visiveis.map(l => l.cotados.length > 0 && (
                <Scatter key={`${l.k}-cotado`} data={l.cotados} name={`${l.nome} (cotado)`}
                  fill="#ffffff" stroke={l.cor} strokeWidth={1.75} isAnimationActive={false} />
              ))}
            </ScatterChart>
          </ResponsiveContainer>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, fontSize: 11, color: 'var(--ink-3)', margin: '2px 0 6px' }}>
          <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 8, background: 'var(--ink-3)' }} /> pago</span>
          <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 8, border: '1.5px solid var(--ink-3)' }} /> cotado</span>
        </div>
      </div>

      {/* A legenda: rola quando há muitas lojas, e o cabeçalho fica à vista. */}
      <div style={{ maxHeight: 216, overflow: 'auto', borderTop: '1px solid var(--line)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 540 }}>
          <thead><tr>
            <th style={{ ...th, width: 34 }}>
              <input type="checkbox" aria-label="Mostrar todos os fornecedores" checked={todos}
                onChange={() => setOcultos(todos ? new Set(lojas.map(l => l.k)) : new Set())} />
            </th>
            <th style={th}>Fornecedor ({lojas.length})</th>
            <th style={{ ...th, textAlign: 'right' }}>Tabela</th>
            <th style={{ ...th, textAlign: 'right' }}>Último pago</th>
            <th style={th}>Última compra</th>
            <th style={{ ...th, textAlign: 'right' }}>Último cotado</th>
          </tr></thead>
          <tbody>{lojas.map(l => {
            const marcado = !ocultos.has(l.k)
            return (
              <tr key={l.k} onClick={() => alternar(l.k)} style={{ cursor: 'pointer', opacity: marcado ? 1 : 0.55 }}>
                <td style={td}><input type="checkbox" checked={marcado} onChange={() => alternar(l.k)} onClick={e => e.stopPropagation()} aria-label={`Mostrar ${l.nome} no gráfico`} /></td>
                <td style={{ ...td, color: 'var(--ink)', fontWeight: 600 }} title={l.codigo ? `Código na loja: ${l.codigo}` : undefined}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7 }}>
                    <span style={{ width: 10, height: 10, borderRadius: 10, background: l.cor, flex: 'none' }} />
                    {l.nome}
                    {l.compraDireta && <Pill kind="net">compra direta</Pill>}
                  </span>
                </td>
                <td style={{ ...td, ...mono, textAlign: 'right' }}>{l.tabela ? brl(l.tabela) : '—'}</td>
                <td style={{ ...td, ...mono, textAlign: 'right', fontWeight: 650 }}>{l.ultimoPago ? brl(l.ultimoPago) : <span style={{ color: 'var(--ink-3)', fontWeight: 400 }}>sem compra</span>}</td>
                <td style={{ ...td, ...mono }}>{l.ultimaCompra ? dataBR(l.ultimaCompra) : '—'}</td>
                <td style={{ ...td, ...mono, textAlign: 'right' }}>{l.ultimoCotado ? brl(l.ultimoCotado) : '—'}</td>
              </tr>
            )
          })}</tbody>
        </table>
      </div>

      {f.historico_precos.length > 0 && (
        <details style={{ borderTop: '1px solid var(--line)' }}>
          <summary style={{ cursor: 'pointer', padding: '8px 12px', fontSize: 12.5, fontWeight: 600, color: 'var(--ink-2)' }}>
            Ver as {f.historico_precos.length} compra{f.historico_precos.length > 1 ? 's' : ''}
          </summary>
          <div style={{ maxHeight: 220, overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 460 }}>
              <thead><tr><th style={th}>Data</th><th style={th}>Pedido</th><th style={th}>Fornecedor</th><th style={{ ...th, textAlign: 'right' }}>Qtd.</th><th style={{ ...th, textAlign: 'right' }}>Preço</th></tr></thead>
              <tbody>{f.historico_precos.map((h, i) => (
                <tr key={i}>
                  <td style={{ ...td, ...mono }}>{dataBR(h.data)}</td>
                  <td style={{ ...td, ...mono }}>#{h.pedido}</td>
                  <td style={td}>{h.fornecedor_nome}</td>
                  <td style={{ ...td, ...mono, textAlign: 'right' }}>{qty(h.quantidade)} {h.unidade}</td>
                  <td style={{ ...td, ...mono, textAlign: 'right', fontWeight: 650 }}>{brl(h.preco_unitario)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  )
}
