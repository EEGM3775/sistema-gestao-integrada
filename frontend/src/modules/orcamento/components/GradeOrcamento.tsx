import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { ChevronDown, ChevronRight, Layers3, MoreVertical } from 'lucide-react'
import { CAPS, mono } from '../ui'
import { achatar, brl, FONTE_ROTULO, montarArvore, num, paraDecimal, paraEdicao, peso, type NoEap } from '../lib'
import type { ItemOrcado } from '../types'

export type ColunaEditavel = 'descricao' | 'unidade' | 'quantidade' | 'custo_unitario'
const EDITAVEIS: ColunaEditavel[] = ['descricao', 'unidade', 'quantidade', 'custo_unitario']
const NUMERICAS = new Set<ColunaEditavel>(['quantidade', 'custo_unitario'])

const ALTURA_LINHA = 30
const JANELA_EXTRA = 12

export interface Cursor { linha: number; coluna: ColunaEditavel }

interface Colunas { largura: number; alinhamento: CSSProperties['textAlign'] }
const LARGURAS: Record<string, Colunas> = {
  eap: { largura: 86, alinhamento: 'left' },
  fonte: { largura: 126, alinhamento: 'left' },
  descricao: { largura: 0, alinhamento: 'left' },
  unidade: { largura: 58, alinhamento: 'center' },
  quantidade: { largura: 108, alinhamento: 'right' },
  custo_unitario: { largura: 116, alinhamento: 'right' },
  bdi: { largura: 62, alinhamento: 'right' },
  total: { largura: 128, alinhamento: 'right' },
  peso: { largura: 62, alinhamento: 'right' },
  menu: { largura: 34, alinhamento: 'center' },
}

export interface EdicaoCelula { item: ItemOrcado; coluna: ColunaEditavel; valor: string }

export default function GradeOrcamento({
  itens, totalOrcamento, bdiPadrao, editavel, modo, filtro, onEditar, onColar, onAbrirLinha, onMenu,
}: {
  itens: ItemOrcado[]
  totalOrcamento: string
  bdiPadrao: string
  editavel: boolean
  modo: 'sintetico' | 'analitico'
  filtro: string
  onEditar: (item: ItemOrcado, coluna: ColunaEditavel, valor: string) => void
  onColar: (edicoes: EdicaoCelula[]) => void
  onAbrirLinha: (item: ItemOrcado) => void
  onMenu: (item: ItemOrcado, ancora: DOMRect) => void
}) {
  const [recolhidos, setRecolhidos] = useState<ReadonlySet<number>>(new Set())
  const [cursor, setCursor] = useState<Cursor | null>(null)
  const [editando, setEditando] = useState<string>('')
  const [emEdicao, setEmEdicao] = useState(false)
  const [scrollTop, setScrollTop] = useState(0)
  const [altura, setAltura] = useState(600)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    setAltura(el.clientHeight)
    const observador = new ResizeObserver(entradas => {
      for (const entrada of entradas) setAltura(entrada.contentRect.height)
    })
    observador.observe(el)
    return () => observador.disconnect()
  }, [])

  const arvore = useMemo(() => montarArvore(itens), [itens])

  const visiveis = useMemo(() => {
    const busca = filtro.trim().toLowerCase()
    let linhas = achatar(arvore, recolhidos)
    if (modo === 'sintetico') {
      // Sintético esconde a folha analítica cujo pai já resume o custo — é a
      // mesma planilha, outro nível de leitura (a convenção da SINAPI).
      linhas = linhas.filter(n => n.item.tipo_linha === 'sintetico' || n.nivel <= 1)
    }
    if (busca) {
      const casa = (n: NoEap) =>
        n.item.descricao.toLowerCase().includes(busca) ||
        n.item.codigo_referencia.toLowerCase().includes(busca) ||
        n.item.codigo_eap.toLowerCase().includes(busca)
      linhas = achatar(arvore, new Set()).filter(casa)
    }
    return linhas
  }, [arvore, recolhidos, modo, filtro])

  const alternar = useCallback((id: number) => {
    setRecolhidos(atual => {
      const proximo = new Set(atual)
      if (proximo.has(id)) proximo.delete(id)
      else proximo.add(id)
      return proximo
    })
  }, [])

  const iniciarEdicao = useCallback((no: NoEap, coluna: ColunaEditavel) => {
    if (!editavel) return
    if (no.item.tipo_linha === 'sintetico' && coluna !== 'descricao') return
    const bruto = no.item[coluna]
    setEditando(NUMERICAS.has(coluna) ? paraEdicao(bruto) : String(bruto ?? ''))
    setEmEdicao(true)
  }, [editavel])

  const confirmar = useCallback((no: NoEap, coluna: ColunaEditavel) => {
    const original = String(no.item[coluna] ?? '')
    const valor = NUMERICAS.has(coluna) ? paraDecimal(editando) : editando.trim()
    setEmEdicao(false)
    if (valor === original) return
    if (NUMERICAS.has(coluna) && Number(valor) === Number(original)) return
    onEditar(no.item, coluna, valor)
  }, [editando, onEditar])

  const mover = useCallback((dLinha: number, dColuna: number) => {
    setCursor(atual => {
      if (!atual) return atual
      let { linha, coluna } = atual
      if (dColuna) {
        const i = EDITAVEIS.indexOf(coluna) + dColuna
        if (i < 0) { coluna = EDITAVEIS[EDITAVEIS.length - 1]; linha -= 1 }
        else if (i >= EDITAVEIS.length) { coluna = EDITAVEIS[0]; linha += 1 }
        else coluna = EDITAVEIS[i]
      }
      linha = Math.max(0, Math.min(visiveis.length - 1, linha + dLinha))
      return { linha, coluna }
    })
  }, [visiveis.length])

  useLayoutEffect(() => {
    if (emEdicao) inputRef.current?.focus()
  }, [emEdicao, cursor])

  useEffect(() => {
    if (!cursor || !containerRef.current) return
    const topo = cursor.linha * ALTURA_LINHA
    const el = containerRef.current
    if (topo < el.scrollTop) el.scrollTop = topo
    else if (topo + ALTURA_LINHA > el.scrollTop + el.clientHeight) el.scrollTop = topo + ALTURA_LINHA - el.clientHeight
  }, [cursor])

  const aoTeclar = (e: KeyboardEvent<HTMLDivElement>, no: NoEap, coluna: ColunaEditavel) => {
    if (emEdicao) {
      if (e.key === 'Escape') { e.preventDefault(); setEmEdicao(false) }
      else if (e.key === 'Enter') { e.preventDefault(); confirmar(no, coluna); mover(1, 0) }
      else if (e.key === 'Tab') { e.preventDefault(); confirmar(no, coluna); mover(0, e.shiftKey ? -1 : 1) }
      return
    }
    if (e.key === 'Enter' || e.key === 'F2') { e.preventDefault(); iniciarEdicao(no, coluna) }
    else if (e.key === 'Tab') { e.preventDefault(); mover(0, e.shiftKey ? -1 : 1) }
    else if (e.key === 'ArrowDown') { e.preventDefault(); mover(1, 0) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); mover(-1, 0) }
    else if (e.key === 'ArrowRight' && !e.ctrlKey) { e.preventDefault(); mover(0, 1) }
    else if (e.key === 'ArrowLeft' && !e.ctrlKey) { e.preventDefault(); mover(0, -1) }
    else if (e.key === ' ' && no.filhos.length) { e.preventDefault(); alternar(no.item.item_orcado_id) }
    else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && editavel) {
      setEditando(e.key)
      setEmEdicao(true)
    }
  }

  /** Colar bloco do Excel: a área colada se ancora na célula com foco e desce
   *  pelas linhas visíveis. Fora da grade, o orçamentista faria isso à mão. */
  const aoColar = (e: React.ClipboardEvent, indice: number, coluna: ColunaEditavel) => {
    const texto = e.clipboardData.getData('text/plain')
    if (!texto.includes('\t') && !texto.includes('\n')) return
    e.preventDefault()
    if (!editavel) return
    const bloco = texto.replace(/\r/g, '').split('\n').filter(l => l !== '').map(l => l.split('\t'))
    const colunaInicial = EDITAVEIS.indexOf(coluna)
    const edicoes: EdicaoCelula[] = []
    bloco.forEach((linha, dl) => {
      const alvo = visiveis[indice + dl]
      if (!alvo) return
      linha.forEach((bruto, dc) => {
        const col = EDITAVEIS[colunaInicial + dc]
        if (!col) return
        if (alvo.item.tipo_linha === 'sintetico' && col !== 'descricao') return
        edicoes.push({ item: alvo.item, coluna: col, valor: NUMERICAS.has(col) ? paraDecimal(bruto) : bruto.trim() })
      })
    })
    if (edicoes.length) onColar(edicoes)
  }

  const primeira = Math.max(0, Math.floor(scrollTop / ALTURA_LINHA) - JANELA_EXTRA)
  const quantas = Math.ceil(altura / ALTURA_LINHA) + JANELA_EXTRA * 2
  const fatia = visiveis.slice(primeira, primeira + quantas)

  const cel = (chave: keyof typeof LARGURAS, conteudo: React.ReactNode, extra?: CSSProperties) => (
    <div style={{
      width: LARGURAS[chave].largura || undefined,
      flex: LARGURAS[chave].largura ? 'none' : 1,
      minWidth: LARGURAS[chave].largura ? undefined : 200,
      textAlign: LARGURAS[chave].alinhamento,
      padding: '0 9px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      display: 'flex', alignItems: 'center',
      justifyContent: LARGURAS[chave].alinhamento === 'right' ? 'flex-end' : LARGURAS[chave].alinhamento === 'center' ? 'center' : 'flex-start',
      ...extra,
    }}>{conteudo}</div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, background: 'var(--surface)' }}>
      <div style={{
        display: 'flex', alignItems: 'stretch', height: 32, flex: 'none',
        background: 'var(--surface-2)', borderBottom: '1px solid var(--line)', ...CAPS, fontSize: 10,
      }}>
        {cel('eap', 'Item')}
        {cel('fonte', 'Fonte / código')}
        {cel('descricao', 'Descrição')}
        {cel('unidade', 'Und')}
        {cel('quantidade', 'Quantidade')}
        {cel('custo_unitario', 'Custo unit.')}
        {cel('bdi', 'BDI')}
        {cel('total', 'Total c/ BDI')}
        {cel('peso', 'Peso')}
        {cel('menu', '')}
      </div>

      <div
        ref={containerRef}
        className="orc-grade"
        onScroll={e => setScrollTop(e.currentTarget.scrollTop)}
        style={{ flex: 1, minHeight: 0, overflow: 'auto', position: 'relative' }}
      >
        <div style={{ height: visiveis.length * ALTURA_LINHA, position: 'relative' }}>
          <div style={{ position: 'absolute', top: primeira * ALTURA_LINHA, left: 0, right: 0 }}>
            {fatia.map((no, iFatia) => {
              const indice = primeira + iFatia
              const item = no.item
              const sintetico = item.tipo_linha === 'sintetico'
              const temFilhos = no.filhos.length > 0
              const recolhido = recolhidos.has(item.item_orcado_id)
              const p = peso(item.total_com_bdi, totalOrcamento)

              return (
                <div
                  key={item.item_orcado_id}
                  className="orc-linha"
                  style={{
                    display: 'flex', alignItems: 'stretch', height: ALTURA_LINHA,
                    borderBottom: '1px solid var(--line-2)', fontSize: 12.5,
                    background: sintetico ? 'var(--surface-2)' : undefined,
                    fontWeight: sintetico ? 700 : 400,
                    color: sintetico ? 'var(--ink)' : 'var(--ink-2)',
                  }}
                >
                  {cel('eap', (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 2, paddingLeft: no.nivel * 11 }}>
                      {temFilhos ? (
                        <button
                          onClick={() => alternar(item.item_orcado_id)}
                          style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--ink-3)', padding: 0, display: 'flex' }}
                          title={recolhido ? 'Expandir' : 'Recolher'}
                        >
                          {recolhido ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                        </button>
                      ) : <span style={{ width: 13 }} />}
                      <span style={{ ...mono, fontSize: 11.5, color: sintetico ? 'var(--ink)' : 'var(--ink-3)' }}>{item.codigo_eap}</span>
                    </span>
                  ))}

                  {cel('fonte', item.codigo_referencia ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, minWidth: 0 }}>
                      <span style={{
                        ...CAPS, fontSize: 9, padding: '1px 5px', borderRadius: 3,
                        background: item.fonte_referencia === 'propria' ? 'var(--net-soft)' : 'var(--inset)',
                        color: item.fonte_referencia === 'propria' ? 'var(--net-ink)' : 'var(--ink-3)',
                      }}>
                        {item.fonte_referencia ? FONTE_ROTULO[item.fonte_referencia] : '—'}
                      </span>
                      <span style={{ ...mono, fontSize: 11, color: 'var(--ink-3)', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {item.codigo_referencia}
                      </span>
                    </span>
                  ) : sintetico ? <Layers3 size={12} style={{ color: 'var(--ink-3)' }} /> : null)}

                  {EDITAVEIS.map(coluna => {
                    const ativa = cursor?.linha === indice && cursor.coluna === coluna
                    const bloqueada = sintetico && coluna !== 'descricao'
                    const chaveCol = coluna
                    const exibicao =
                      coluna === 'quantidade' ? (bloqueada ? '' : num(item.quantidade))
                        : coluna === 'custo_unitario' ? (bloqueada ? '' : num(item.custo_unitario))
                          : String(item[coluna] ?? '')

                    return (
                      <div
                        key={coluna}
                        className="orc-cel"
                        tabIndex={0}
                        onFocus={() => setCursor({ linha: indice, coluna })}
                        onClick={() => setCursor({ linha: indice, coluna })}
                        onDoubleClick={() => iniciarEdicao(no, coluna)}
                        onKeyDown={e => aoTeclar(e, no, coluna)}
                        onPaste={e => aoColar(e, indice, coluna)}
                        style={{
                          width: LARGURAS[chaveCol].largura || undefined,
                          flex: LARGURAS[chaveCol].largura ? 'none' : 1,
                          minWidth: LARGURAS[chaveCol].largura ? undefined : 200,
                          padding: emEdicao && ativa ? 0 : '0 9px',
                          display: 'flex', alignItems: 'center',
                          justifyContent: LARGURAS[chaveCol].alinhamento === 'right' ? 'flex-end' : LARGURAS[chaveCol].alinhamento === 'center' ? 'center' : 'flex-start',
                          overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis',
                          background: ativa && !emEdicao ? 'var(--accent-soft)' : undefined,
                          cursor: editavel && !bloqueada ? 'cell' : 'default',
                          ...(NUMERICAS.has(coluna) ? mono : {}),
                        }}
                      >
                        {emEdicao && ativa ? (
                          <input
                            ref={inputRef}
                            value={editando}
                            onChange={e => setEditando(e.target.value)}
                            onBlur={() => confirmar(no, coluna)}
                            onKeyDown={e => aoTeclar(e, no, coluna)}
                            style={{
                              width: '100%', height: '100%', border: '2px solid var(--accent)', outline: 'none',
                              background: 'var(--surface)', color: 'var(--ink)', padding: '0 7px', fontSize: 12.5,
                              textAlign: NUMERICAS.has(coluna) ? 'right' : 'left',
                              ...(NUMERICAS.has(coluna) ? mono : { fontFamily: 'var(--sans)' }),
                            }}
                          />
                        ) : exibicao}
                      </div>
                    )
                  })}

                  {cel('bdi', sintetico ? '' : (
                    <span style={{ ...mono, fontSize: 11.5, color: item.bdi ? 'var(--accent-ink)' : 'var(--ink-3)' }}>
                      {item.bdi ? 'próprio' : `${Number(bdiPadrao).toFixed(1)}%`}
                    </span>
                  ))}

                  {cel('total', <span style={{ ...mono, fontWeight: sintetico ? 700 : 500, color: 'var(--ink)' }}>{brl(item.total_com_bdi)}</span>)}

                  {cel('peso', p > 0 ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ width: 22, height: 4, borderRadius: 99, background: 'var(--inset)', overflow: 'hidden', display: 'inline-block' }}>
                        <span style={{ display: 'block', width: `${Math.min(p, 100)}%`, height: '100%', background: p >= 10 ? 'var(--accent)' : 'var(--ink-3)' }} />
                      </span>
                      <span style={{ ...mono, fontSize: 10.5, color: 'var(--ink-3)' }}>{p.toFixed(1)}</span>
                    </span>
                  ) : null)}

                  {cel('menu', (
                    <button
                      onClick={e => onMenu(item, e.currentTarget.getBoundingClientRect())}
                      onDoubleClick={() => onAbrirLinha(item)}
                      title="Ações da linha"
                      style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--ink-3)', padding: 2, display: 'flex' }}
                    >
                      <MoreVertical size={14} />
                    </button>
                  ))}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
