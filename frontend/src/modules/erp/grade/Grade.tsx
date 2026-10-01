import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, ChevronsUpDown } from 'lucide-react'
import { formatBRL } from '@/utils/money'
import type { ColunaGrade, ItemGrade, NoGrupo } from './tipos'

export const ALTURA_LINHA = 46
const ALTURA_CABECALHO = 36
const FOLGA = 10
const LARGURA_MARCA = 38

const reais = (v: number) => formatBRL(Math.round(v * 100))

/** Os dois sentidos, ditos na língua do dado — "A → Z" não descreve dinheiro. */
const SENTIDOS: Record<NonNullable<ColunaGrade<unknown>['tipo']>, [string, string]> = {
  texto: ['A → Z', 'Z → A'],
  numero: ['Menor → maior', 'Maior → menor'],
  data: ['Mais antiga primeiro', 'Mais recente primeiro'],
  endereco: ['Quadra e lote em ordem (2 antes de 10)', 'Do fim ao começo'],
}

/**
 * Quem está marcado é uma pergunta, não um conjunto: em "todas do filtro" a
 * página não tem os ids das milhares de linhas que não carregou, e a linha
 * precisa aparecer marcada mesmo assim (item 51: "marca, mas o quadrado fica
 * vazio").
 */
export interface SelecaoGrade<T> {
  marcada: (linha: T) => boolean
  alternar: (linha: T) => void
  podeMarcar?: (linha: T) => boolean
  /** A caixa do cabeçalho: marca ou desmarca todas as linhas do filtro. */
  todas?: {
    estado: 'nenhuma' | 'algumas' | 'todas'
    habilitada: boolean
    dica: string
    alternar: () => void
  }
}

function CaixaDeTodas({ todas }: { todas: NonNullable<SelecaoGrade<unknown>['todas']> }) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => { if (ref.current) ref.current.indeterminate = todas.estado === 'algumas' }, [todas.estado])
  return (
    <input
      ref={ref}
      type="checkbox"
      aria-label="Marcar todas as linhas do filtro"
      title={todas.dica}
      checked={todas.estado === 'todas'}
      disabled={!todas.habilitada}
      onChange={todas.alternar}
      style={{ cursor: todas.habilitada ? 'pointer' : 'not-allowed', accentColor: 'var(--accent)' }}
    />
  )
}

/**
 * A grade dos títulos: rolagem infinita virtualizada, cabeçalho congelado,
 * primeira coluna congelada, toda coluna ordena e os grupos mostram os
 * subtotais do banco. O molde é a carteira de clientes (frontend.md §5.8):
 * com dezenas de milhares de linhas, desenhar todas trava o navegador — só o
 * que cabe na tela é renderizado.
 */
export function Grade<T>({
  itens, colunas, ordenar, carregando, mostrarSaldo, selecao, vazio,
  onOrdenar, onAbrir, onAlternarGrupo, onAbrirSoOGrupo, onFimDaLista,
}: {
  itens: ItemGrade<T>[]
  colunas: ColunaGrade<T>[]
  ordenar: string
  carregando: boolean
  mostrarSaldo: boolean
  selecao?: SelecaoGrade<T>
  vazio: string
  onOrdenar: (chave: string) => void
  onAbrir: (linha: T) => void
  onAlternarGrupo: (no: NoGrupo) => void
  onAbrirSoOGrupo: (no: NoGrupo) => void
  onFimDaLista: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [topo, setTopo] = useState(0)
  const [altura, setAltura] = useState(600)
  const [ativa, setAtiva] = useState(-1)
  const [menu, setMenu] = useState<string | null>(null)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    setAltura(el.clientHeight)
    const obs = new ResizeObserver(e => { for (const x of e) setAltura(x.contentRect.height) })
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  // Outra busca ou outra ordem: volta ao topo, senão a tela mostra o meio de
  // uma lista que não é a que a pessoa acabou de pedir.
  const assinatura = `${ordenar}|${colunas.length}`
  useEffect(() => { ref.current?.scrollTo({ top: 0 }); setAtiva(-1) }, [assinatura])

  const larguraTotal = useMemo(
    () => colunas.reduce((s, c) => s + c.largura, 0) + (selecao ? LARGURA_MARCA : 0),
    [colunas, selecao],
  )

  const inicio = Math.max(0, Math.floor(topo / ALTURA_LINHA) - FOLGA)
  const fim = Math.min(itens.length, Math.ceil((topo + altura) / ALTURA_LINHA) + FOLGA)

  const aoRolar = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    setTopo(el.scrollTop)
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 600) onFimDaLista()
  }

  const copiar = useCallback(() => {
    const item = itens[ativa]
    if (!item || item.tipo !== 'linha') return
    const cab = colunas.map(c => c.titulo).join('\t')
    const corpo = colunas.map(c => c.texto(item.linha)).join('\t')
    navigator.clipboard?.writeText(`${cab}\n${corpo}`)
  }, [itens, ativa, colunas])

  const aoTeclar = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') { copiar(); return }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const prox = Math.min(itens.length - 1, Math.max(0, (ativa < 0 ? -1 : ativa) + (e.key === 'ArrowDown' ? 1 : -1)))
      setAtiva(prox)
      const el = ref.current
      if (el) {
        const y = prox * ALTURA_LINHA
        if (y < el.scrollTop) el.scrollTo({ top: y })
        else if (y + ALTURA_LINHA + ALTURA_CABECALHO > el.scrollTop + el.clientHeight) {
          el.scrollTo({ top: y + ALTURA_LINHA + ALTURA_CABECALHO - el.clientHeight })
        }
      }
      return
    }
    const item = itens[ativa]
    if (e.key === 'Enter' && item) {
      e.preventDefault()
      if (item.tipo === 'linha') onAbrir(item.linha)
      if (item.tipo === 'grupo') onAlternarGrupo(item.no)
    }
    if (e.key === ' ' && item?.tipo === 'linha' && selecao) {
      e.preventDefault()
      selecao.alternar(item.linha)
    }
  }

  return (
    <div
      ref={ref}
      onScroll={aoRolar}
      onKeyDown={aoTeclar}
      tabIndex={0}
      role="grid"
      aria-rowcount={itens.length}
      style={{
        flex: 1, overflow: 'auto', outline: 'none', background: 'var(--surface)',
        border: '1px solid var(--line)', borderRadius: 'var(--r-md)', minHeight: 320,
      }}
    >
      <div style={{ width: Math.max(larguraTotal, 100), minWidth: '100%' }}>
        <div
          role="row"
          style={{
            display: 'flex', position: 'sticky', top: 0, zIndex: 3, height: ALTURA_CABECALHO,
            background: 'var(--surface-2)', borderBottom: '1px solid var(--line)',
          }}
        >
          {selecao && (
            <div style={{
              width: LARGURA_MARCA, flex: 'none', position: 'sticky', left: 0, zIndex: 2, background: 'var(--surface-2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {selecao.todas && <CaixaDeTodas todas={selecao.todas} />}
            </div>
          )}
          {colunas.map((c, i) => {
            const ordenada = Boolean(c.ordenar) && ordenar.replace('-', '') === c.ordenar
            const desc = ordenada && ordenar.startsWith('-')
            const primeira = i === 0
            return (
              <div
                key={c.chave}
                role="columnheader"
                aria-sort={ordenada ? (desc ? 'descending' : 'ascending') : 'none'}
                onClick={() => c.ordenar && onOrdenar(ordenada && !desc ? `-${c.ordenar}` : c.ordenar)}
                title={c.ordenar ? `Ordenar por ${c.titulo}` : c.titulo}
                style={{
                  width: c.largura, flex: 'none', display: 'flex', alignItems: 'center', gap: 4,
                  padding: '0 10px', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em',
                  textTransform: 'uppercase', color: ordenada ? 'var(--ink)' : 'var(--ink-3)',
                  cursor: c.ordenar ? 'pointer' : 'default',
                  justifyContent: c.alinhamento === 'right' ? 'flex-end' : 'flex-start',
                  position: primeira ? 'sticky' : 'relative', left: primeira ? (selecao ? LARGURA_MARCA : 0) : undefined,
                  zIndex: menu === c.chave ? 6 : primeira ? 2 : undefined,
                  background: primeira ? 'var(--surface-2)' : undefined,
                  borderRight: '1px solid var(--line-2)',
                }}
              >
                <span className="truncate">{c.titulo}</span>
                {ordenada && (desc ? <ArrowDown size={11} /> : <ArrowUp size={11} />)}
                {c.ordenar && (
                  <button
                    type="button"
                    aria-label={`Opções de ordenação de ${c.titulo}`}
                    onClick={e => { e.stopPropagation(); setMenu(m => (m === c.chave ? null : c.chave)) }}
                    style={{
                      marginLeft: c.alinhamento === 'right' ? 0 : 'auto', display: 'grid', placeItems: 'center',
                      width: 16, height: 16, border: 'none', background: 'transparent', cursor: 'pointer', padding: 0,
                      color: ordenada ? 'var(--accent-ink)' : 'var(--ink-3)', opacity: ordenada || menu === c.chave ? 1 : 0.55,
                    }}
                  >
                    <ChevronsUpDown size={11} />
                  </button>
                )}
                {menu === c.chave && c.ordenar && (
                  <MenuOrdenar
                    titulo={c.titulo}
                    sentidos={SENTIDOS[c.tipo ?? 'texto']}
                    ativa={ordenada ? (desc ? 'desc' : 'asc') : null}
                    aDireita={i > colunas.length - 3}
                    onEscolher={s => { onOrdenar(s === 'desc' ? `-${c.ordenar}` : c.ordenar!); setMenu(null) }}
                    onFechar={() => setMenu(null)}
                  />
                )}
              </div>
            )
          })}
        </div>

        <div style={{ position: 'relative', height: Math.max(itens.length, 1) * ALTURA_LINHA }}>
          {!carregando && itens.length === 0 && (
            <div style={{ padding: '28px 18px', fontSize: 13, color: 'var(--ink-3)' }}>{vazio}</div>
          )}
          {itens.slice(inicio, fim).map((item, i) => {
            const indice = inicio + i
            const y = indice * ALTURA_LINHA
            if (item.tipo === 'grupo') {
              return (
                <LinhaGrupo
                  key={`g-${item.no.chaves.join('|')}`}
                  no={item.no} nivel={item.nivel} aberto={item.aberto} topo={y}
                  ativa={ativa === indice} mostrarSaldo={mostrarSaldo}
                  onAlternar={() => { setAtiva(indice); onAlternarGrupo(item.no) }}
                />
              )
            }
            if (item.tipo === 'aviso') {
              return (
                <div
                  key={`a-${indice}`}
                  style={{
                    position: 'absolute', top: y, height: ALTURA_LINHA, left: 0, right: 0, display: 'flex',
                    alignItems: 'center', paddingLeft: 18 + item.nivel * 18, fontSize: 12, color: 'var(--ink-3)',
                  }}
                >
                  {item.no ? (
                    <button
                      type="button"
                      onClick={() => onAbrirSoOGrupo(item.no!)}
                      style={{ background: 'none', border: 'none', padding: 0, color: 'var(--accent-ink)', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
                    >
                      {item.texto}
                    </button>
                  ) : item.texto}
                </div>
              )
            }
            return (
              <LinhaDados
                key={`l-${indice}`}
                linha={item.linha} nivel={item.nivel} colunas={colunas} topo={y}
                ativa={ativa === indice} selecao={selecao}
                onFocar={() => setAtiva(indice)}
                onAbrir={() => onAbrir(item.linha)}
              />
            )
          })}
          {carregando && (
            <div style={{ position: 'absolute', top: itens.length * ALTURA_LINHA, padding: 14, fontSize: 12, color: 'var(--ink-3)' }}>
              Carregando…
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function MenuOrdenar({ titulo, sentidos, ativa, aDireita, onEscolher, onFechar }: {
  titulo: string
  sentidos: [string, string]
  ativa: 'asc' | 'desc' | null
  aDireita: boolean
  onEscolher: (s: 'asc' | 'desc') => void
  onFechar: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const fora = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onFechar() }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onFechar() }
    document.addEventListener('mousedown', fora)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', fora); document.removeEventListener('keydown', esc) }
  }, [onFechar])

  return (
    <div
      ref={ref}
      role="menu"
      onClick={e => e.stopPropagation()}
      style={{
        position: 'absolute', top: '100%', zIndex: 8, minWidth: 220, [aDireita ? 'right' : 'left']: 0,
        background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-md)',
        boxShadow: 'var(--shadow-lg)', padding: 6, textTransform: 'none', letterSpacing: 'normal', fontWeight: 400,
      }}
    >
      <div style={{ padding: '4px 8px 6px', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)' }}>
        Ordenar por {titulo}
      </div>
      {([['asc', sentidos[0], ArrowUp], ['desc', sentidos[1], ArrowDown]] as const).map(([s, rotulo, Icone]) => (
        <button
          key={s}
          type="button"
          role="menuitem"
          onClick={() => onEscolher(s)}
          style={{
            display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'left', padding: '7px 8px',
            border: 'none', borderRadius: 'var(--r-sm)', cursor: 'pointer', fontSize: 12.5, fontFamily: 'var(--sans)',
            background: ativa === s ? 'var(--accent-soft)' : 'transparent',
            color: ativa === s ? 'var(--accent-ink)' : 'var(--ink-2)', fontWeight: ativa === s ? 650 : 400,
          }}
        >
          <Icone size={13} /> {rotulo}
        </button>
      ))}
    </div>
  )
}

function LinhaGrupo({ no, nivel, aberto, topo, ativa, mostrarSaldo, onAlternar }: {
  no: NoGrupo; nivel: number; aberto: boolean; topo: number; ativa: boolean; mostrarSaldo: boolean
  onAlternar: () => void
}) {
  return (
    <div
      role="row"
      aria-expanded={aberto}
      onClick={onAlternar}
      style={{
        position: 'absolute', top: topo, left: 0, right: 0, height: ALTURA_LINHA, display: 'flex',
        alignItems: 'center', gap: 8, cursor: 'pointer', paddingLeft: 10 + nivel * 18, paddingRight: 14,
        background: nivel === 0 ? 'var(--inset)' : 'var(--surface-2)', borderBottom: '1px solid var(--line)',
        fontWeight: 650, fontSize: 13, color: 'var(--ink)',
        boxShadow: ativa ? 'inset 0 0 0 2px var(--accent)' : undefined,
      }}
    >
      {aberto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      <span className="truncate" style={{ maxWidth: 420 }}>{no.rotulos[no.rotulos.length - 1]}</span>
      <span style={{ fontSize: 11.5, color: 'var(--ink-3)', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
        {no.contagem.toLocaleString('pt-BR')}
      </span>
      <span style={{ marginLeft: 'auto', display: 'flex', gap: 18, alignItems: 'center', fontVariantNumeric: 'tabular-nums' }}>
        {mostrarSaldo && no.vencido > 0 && (
          <span style={{ fontSize: 12, color: 'var(--danger-ink)', fontWeight: 700 }}>{reais(no.vencido)} vencido</span>
        )}
        {mostrarSaldo ? (
          <span style={{ fontSize: 12, color: 'var(--ink-2)' }}>{reais(no.saldo)} em aberto</span>
        ) : (
          <span style={{ fontSize: 12, color: 'var(--ink-2)' }}>{reais(no.valor)}</span>
        )}
      </span>
    </div>
  )
}

function LinhaDados<T>({ linha, nivel, colunas, topo, ativa, selecao, onFocar, onAbrir }: {
  linha: T; nivel: number; colunas: ColunaGrade<T>[]; topo: number; ativa: boolean
  selecao?: SelecaoGrade<T>; onFocar: () => void; onAbrir: () => void
}) {
  const marcada = selecao ? selecao.marcada(linha) : false
  const fundo = marcada ? 'var(--accent-soft)' : 'var(--surface)'
  const celula: CSSProperties = {
    flex: 'none', display: 'flex', alignItems: 'center', padding: '0 10px', fontSize: 12.5,
    color: 'var(--ink-2)', height: '100%', borderRight: '1px solid var(--line-2)', overflow: 'hidden',
  }
  const podeMarcar = selecao ? (selecao.podeMarcar?.(linha) ?? true) : false

  return (
    <div
      role="row"
      aria-selected={marcada}
      onClick={() => { onFocar(); onAbrir() }}
      style={{
        position: 'absolute', top: topo, left: 0, height: ALTURA_LINHA, display: 'flex', background: fundo,
        borderBottom: '1px solid var(--line-2)', cursor: 'pointer',
        boxShadow: ativa ? 'inset 0 0 0 2px var(--accent)' : undefined,
      }}
    >
      {selecao && (
        <div
          onClick={e => e.stopPropagation()}
          style={{ ...celula, width: LARGURA_MARCA, justifyContent: 'center', position: 'sticky', left: 0, zIndex: 1, background: fundo, padding: 0 }}
        >
          <input
            type="checkbox"
            aria-label="Selecionar linha"
            checked={marcada}
            disabled={!podeMarcar}
            onChange={() => selecao.alternar(linha)}
            style={{ cursor: podeMarcar ? 'pointer' : 'not-allowed', accentColor: 'var(--accent)' }}
          />
        </div>
      )}
      {colunas.map((c, i) => {
        const primeira = i === 0
        return (
          <div
            key={c.chave}
            role="gridcell"
            style={{
              ...celula, width: c.largura,
              justifyContent: c.alinhamento === 'right' ? 'flex-end' : c.alinhamento === 'center' ? 'center' : 'flex-start',
              fontFamily: c.mono ? 'var(--mono)' : 'var(--sans)', fontVariantNumeric: c.mono || c.tipo === 'numero' ? 'tabular-nums' : undefined,
              position: primeira ? 'sticky' : undefined, left: primeira ? (selecao ? LARGURA_MARCA : 0) : undefined,
              zIndex: primeira ? 1 : undefined, background: primeira ? fundo : undefined,
              paddingLeft: primeira ? 10 + nivel * 18 : 10,
            }}
          >
            {c.render(linha)}
          </div>
        )
      })}
    </div>
  )
}
