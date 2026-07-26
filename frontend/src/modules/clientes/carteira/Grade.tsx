import {
  useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState,
  type CSSProperties, type PointerEvent as ReactPointerEvent,
} from 'react'
import { ChevronDown, ChevronRight, ArrowUp, ArrowDown, ChevronsUpDown, Lock } from 'lucide-react'
import type { ColunaDef } from './colunas'
import type { GrupoCarteira, LinhaCarteira } from './types'

export const ALTURA_LINHA = 44
const ALTURA_CABECALHO = 36
const JANELA_EXTRA = 8

/** Um nó da árvore de grupos: os níveis de cima somam os filhos. */
export interface NoGrupo {
  chaves: string[]
  rotulos: string[]
  filtros: string[]
  contagem: number
  valorAberto: number
  valorAtraso: number
  valorVenda: number
  folha: boolean
  filhos: NoGrupo[]
}

/** Monta a árvore a partir das combinações achatadas que o backend devolve. */
export function montarArvore(grupos: GrupoCarteira[], niveis: number): NoGrupo[] {
  const raiz: NoGrupo[] = []
  for (const g of grupos) {
    let nivelAtual = raiz
    for (let i = 0; i < g.chaves.length; i++) {
      const chaves = g.chaves.slice(0, i + 1)
      const id = chaves.join('␟')
      let no = nivelAtual.find(n => n.chaves.join('␟') === id)
      if (!no) {
        no = {
          chaves,
          rotulos: g.rotulos.slice(0, i + 1),
          filtros: g.filtros.slice(0, i + 1),
          contagem: 0, valorAberto: 0, valorAtraso: 0, valorVenda: 0,
          folha: i === niveis - 1,
          filhos: [],
        }
        nivelAtual.push(no)
      }
      no.contagem += g.contagem
      no.valorAberto += Number(g.valorAberto ?? 0)
      no.valorAtraso += Number(g.valorAtraso ?? 0)
      no.valorVenda += Number(g.valorVenda ?? 0)
      nivelAtual = no.filhos
    }
  }
  return raiz
}

export type ItemGrade =
  | { tipo: 'grupo'; no: NoGrupo; nivel: number; aberto: boolean }
  | { tipo: 'linha'; linha: LinhaCarteira; nivel: number }
  | { tipo: 'aviso'; texto: string; nivel: number }

const brl = (v: number) =>
  v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })

export function Grade({
  itens, colunas, larguras, ordenar, podeFinanceiro, podeDocumento, carregando,
  onOrdenar, onLargura, onReordenar, onAbrir, onAlternarGrupo, onFimDaLista,
}: {
  itens: ItemGrade[]
  colunas: ColunaDef[]
  larguras: Record<string, number>
  ordenar: string
  podeFinanceiro: boolean
  podeDocumento: boolean
  carregando: boolean
  onOrdenar: (chave: string, sentido: 'asc' | 'desc') => void
  onLargura: (chave: string, largura: number) => void
  onReordenar: (de: string, para: string) => void
  onAbrir: (linha: LinhaCarteira) => void
  onAlternarGrupo: (no: NoGrupo) => void
  onFimDaLista: () => void
}) {
  const refRolagem = useRef<HTMLDivElement>(null)
  const [scrollTop, setScrollTop] = useState(0)
  const [altura, setAltura] = useState(600)
  const [ativa, setAtiva] = useState<number>(-1)
  const [selecao, setSelecao] = useState<ReadonlySet<number>>(new Set())
  const [ancora, setAncora] = useState<number | null>(null)
  const [arrastando, setArrastando] = useState<string | null>(null)
  const [menu, setMenu] = useState<string | null>(null)

  const larguraDe = useCallback(
    (c: ColunaDef) => larguras[c.chave] ?? c.largura,
    [larguras],
  )
  const larguraTotal = useMemo(
    () => colunas.reduce((soma, c) => soma + larguraDe(c), 0),
    [colunas, larguraDe],
  )

  useLayoutEffect(() => {
    const el = refRolagem.current
    if (!el) return
    setAltura(el.clientHeight)
    const observador = new ResizeObserver(entradas => {
      for (const e of entradas) setAltura(e.contentRect.height)
    })
    observador.observe(el)
    return () => observador.disconnect()
  }, [])

  // Janela visível: com 5000 linhas, renderizar todas trava o navegador —
  // desenhamos só o que cabe na tela mais uma folga para a rolagem não piscar.
  const inicio = Math.max(0, Math.floor(scrollTop / ALTURA_LINHA) - JANELA_EXTRA)
  const fim = Math.min(itens.length, Math.ceil((scrollTop + altura) / ALTURA_LINHA) + JANELA_EXTRA)
  const visiveis = itens.slice(inicio, fim)

  const aoRolar = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    setScrollTop(el.scrollTop)
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 400) onFimDaLista()
  }

  const indicesDeLinha = useMemo(
    () => itens.map((it, i) => (it.tipo === 'linha' ? i : -1)).filter(i => i >= 0),
    [itens],
  )

  const selecionar = (indice: number, e: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean }) => {
    setAtiva(indice)
    if (e.shiftKey && ancora !== null) {
      const [de, para] = ancora < indice ? [ancora, indice] : [indice, ancora]
      setSelecao(new Set(indicesDeLinha.filter(i => i >= de && i <= para)))
      return
    }
    if (e.ctrlKey || e.metaKey) {
      const proxima = new Set(selecao)
      proxima.has(indice) ? proxima.delete(indice) : proxima.add(indice)
      setSelecao(proxima)
      setAncora(indice)
      return
    }
    setSelecao(new Set([indice]))
    setAncora(indice)
  }

  /** Ctrl+C copia o que está selecionado, nas colunas visíveis, em TSV —
   *  cola direto no Excel. O CPF sai como está na tela: mascarado continua
   *  mascarado, e coluna financeira que o usuário não recebe não existe aqui. */
  const copiar = useCallback(() => {
    const escolhidas = itens
      .map((it, i) => ({ it, i }))
      .filter(({ it, i }) => it.tipo === 'linha' && selecao.has(i))
    if (!escolhidas.length) return
    const cabecalho = colunas.map(c => c.titulo).join('\t')
    const corpo = escolhidas
      .map(({ it }) => colunas.map(c => c.valor((it as { linha: LinhaCarteira }).linha)).join('\t'))
      .join('\n')
    navigator.clipboard?.writeText(`${cabecalho}\n${corpo}`)
  }, [itens, selecao, colunas])

  const aoTeclar = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') {
      copiar()
      return
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const passo = e.key === 'ArrowDown' ? 1 : -1
      const proxima = Math.min(itens.length - 1, Math.max(0, (ativa < 0 ? 0 : ativa) + passo))
      selecionar(proxima, { shiftKey: e.shiftKey, ctrlKey: false, metaKey: false })
      refRolagem.current?.scrollTo({ top: Math.max(0, proxima * ALTURA_LINHA - altura / 2) })
      return
    }
    const item = itens[ativa]
    if (e.key === 'Enter' && item) {
      e.preventDefault()
      if (item.tipo === 'linha') onAbrir(item.linha)
      if (item.tipo === 'grupo') onAlternarGrupo(item.no)
    }
  }

  // Redimensionar coluna: arrasta a alça e a largura acompanha o ponteiro.
  const iniciarRedimensionamento = (c: ColunaDef) => (e: ReactPointerEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const xInicial = e.clientX
    const larguraInicial = larguraDe(c)
    const mover = (ev: PointerEvent) =>
      onLargura(c.chave, Math.max(60, larguraInicial + ev.clientX - xInicial))
    const soltar = () => {
      document.removeEventListener('pointermove', mover)
      document.removeEventListener('pointerup', soltar)
    }
    document.addEventListener('pointermove', mover)
    document.addEventListener('pointerup', soltar)
  }

  useEffect(() => {
    setSelecao(new Set())
    setAtiva(-1)
  }, [colunas])

  return (
    <div
      ref={refRolagem}
      onScroll={aoRolar}
      onKeyDown={aoTeclar}
      tabIndex={0}
      className="carteira-grade"
      style={{ flex: 1, overflow: 'auto', outline: 'none', background: 'var(--surface)' }}
    >
      <div style={{ width: Math.max(larguraTotal, 100), minWidth: '100%' }}>
        {/* Cabeçalho congelado — a régua da planilha não sai da tela. */}
        <div
          style={{
            display: 'flex', position: 'sticky', top: 0, zIndex: 3, height: ALTURA_CABECALHO,
            background: 'var(--surface-2)', borderBottom: '1px solid var(--line)',
          }}
        >
          {colunas.map((c, i) => {
            const ordenadaPor = ordenar.replace('-', '') === c.ordenar
            const descendente = ordenadaPor && ordenar.startsWith('-')
            const travada = Boolean(
              (c.documental && !podeDocumento) || (c.financeira && !podeFinanceiro),
            )
            return (
              <div
                key={c.chave}
                draggable
                onDragStart={() => setArrastando(c.chave)}
                onDragOver={e => e.preventDefault()}
                onDrop={() => {
                  if (arrastando && arrastando !== c.chave) onReordenar(arrastando, c.chave)
                  setArrastando(null)
                }}
                // Clicar alterna crescente/decrescente — o caminho rápido de quem
                // já sabe o que quer. O menu ao lado é o explícito.
                onClick={() => !travada && onOrdenar(c.ordenar, ordenadaPor && !descendente ? 'desc' : 'asc')}
                title={travada ? `${c.titulo} — ordenação exige permissão` : `Ordenar por ${c.titulo}`}
                style={{
                  width: larguraDe(c), flex: 'none', display: 'flex', alignItems: 'center', gap: 4,
                  padding: '0 10px', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: ordenadaPor ? 'var(--ink)' : 'var(--ink-3)',
                  cursor: travada ? 'default' : 'pointer',
                  justifyContent: c.alinhamento === 'right' ? 'flex-end' : 'flex-start',
                  // `relative` é o que ancora a alça de redimensionamento e o
                  // menu **nesta** coluna; na primeira, o sticky já posiciona.
                  position: i === 0 ? 'sticky' : 'relative',
                  left: i === 0 ? 0 : undefined,
                  zIndex: menu === c.chave ? 6 : i === 0 ? 2 : undefined,
                  background: i === 0 ? 'var(--surface-2)' : undefined,
                  borderRight: '1px solid var(--line-2)',
                  opacity: arrastando === c.chave ? 0.45 : 1,
                }}
              >
                <span className="truncate">{c.titulo}</span>
                {ordenadaPor && (descendente ? <ArrowDown size={11} /> : <ArrowUp size={11} />)}
                <button
                  aria-label={`Ordenar por ${c.titulo}`}
                  onClick={e => { e.stopPropagation(); setMenu(m => (m === c.chave ? null : c.chave)) }}
                  style={{
                    marginLeft: 'auto', display: 'grid', placeItems: 'center', width: 16, height: 16,
                    border: 'none', background: 'transparent', cursor: 'pointer', padding: 0,
                    color: ordenadaPor ? 'var(--accent-ink)' : 'var(--ink-3)',
                    opacity: menu === c.chave || ordenadaPor ? 1 : 0.55,
                  }}
                >
                  {travada ? <Lock size={10} /> : <ChevronsUpDown size={11} />}
                </button>
                {menu === c.chave && (
                  <MenuOrdenar
                    coluna={c}
                    ativa={ordenadaPor ? (descendente ? 'desc' : 'asc') : null}
                    travada={travada}
                    aDireita={i > colunas.length - 3}
                    onEscolher={sentido => { onOrdenar(c.ordenar, sentido); setMenu(null) }}
                    onFechar={() => setMenu(null)}
                  />
                )}
                <span
                  onPointerDown={iniciarRedimensionamento(c)}
                  onClick={e => e.stopPropagation()}
                  style={{
                    position: 'absolute', right: 0, top: 0, bottom: 0, width: 7,
                    cursor: 'col-resize', touchAction: 'none',
                  }}
                />
              </div>
            )
          })}
        </div>

        {/* Corpo virtualizado */}
        <div style={{ position: 'relative', height: itens.length * ALTURA_LINHA }}>
          {visiveis.map((item, i) => {
            const indice = inicio + i
            const topo = indice * ALTURA_LINHA
            if (item.tipo === 'grupo') {
              return (
                <LinhaGrupo
                  key={`g-${item.no.chaves.join('|')}`}
                  item={item} topo={topo} podeFinanceiro={podeFinanceiro}
                  onAlternar={() => onAlternarGrupo(item.no)}
                />
              )
            }
            if (item.tipo === 'aviso') {
              return (
                <div
                  key={`a-${indice}`}
                  style={{
                    position: 'absolute', top: topo, height: ALTURA_LINHA, left: 0, right: 0,
                    display: 'flex', alignItems: 'center', paddingLeft: 18 + item.nivel * 18,
                    fontSize: 12, color: 'var(--ink-3)',
                  }}
                >
                  {item.texto}
                </div>
              )
            }
            return (
              <LinhaCliente
                key={`l-${item.linha.tipo}-${item.linha.id}`}
                linha={item.linha} nivel={item.nivel} colunas={colunas} larguraDe={larguraDe}
                topo={topo} selecionada={selecao.has(indice)} ativa={ativa === indice}
                podeFinanceiro={podeFinanceiro}
                onSelecionar={e => selecionar(indice, e)}
                onAbrir={() => onAbrir(item.linha)}
              />
            )
          })}

          {carregando && (
            <div style={{ position: 'absolute', top: itens.length * ALTURA_LINHA, padding: 14, fontSize: 12, color: 'var(--ink-3)' }}>
              Carregando mais linhas…
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/** Os dois sentidos, ditos na língua do dado — "A → Z" não descreve dinheiro. */
const SENTIDOS: Record<NonNullable<ColunaDef['tipo']>, [string, string]> = {
  texto: ['A → Z', 'Z → A'],
  numero: ['Menor → maior', 'Maior → menor'],
  data: ['Mais antiga primeiro', 'Mais recente primeiro'],
  endereco: ['Do começo ao fim (2 antes de 10)', 'Do fim ao começo'],
}

/**
 * O "Ordenar por" de **cada** coluna.
 *
 * O clique no título já alterna o sentido; este menu existe para dizer, em
 * palavras, o que a seta faria — e para ser o lugar onde uma ordenação gateada
 * se explica em vez de simplesmente não acontecer.
 */
function MenuOrdenar({
  coluna, ativa, travada, aDireita, onEscolher, onFechar,
}: {
  coluna: ColunaDef
  ativa: 'asc' | 'desc' | null
  travada: boolean
  aDireita: boolean
  onEscolher: (sentido: 'asc' | 'desc') => void
  onFechar: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const fora = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onFechar()
    }
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape') onFechar() }
    document.addEventListener('mousedown', fora)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', fora)
      document.removeEventListener('keydown', escape)
    }
  }, [onFechar])

  const [crescente, decrescente] = SENTIDOS[coluna.tipo ?? 'texto']
  const motivo = coluna.documental
    ? 'Ordenar por documento exige a permissão que desmascara o CPF/CNPJ.'
    : 'Ordenar por valor exige a permissão de cobranças.'

  return (
    <div
      ref={ref}
      onClick={e => e.stopPropagation()}
      style={{
        position: 'absolute', top: '100%', zIndex: 8, minWidth: 216,
        [aDireita ? 'right' : 'left']: 0,
        background: 'var(--surface)', border: '1px solid var(--line)',
        borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-lg)', padding: 6,
        textTransform: 'none', letterSpacing: 'normal', fontWeight: 400,
      }}
    >
      <div style={{ padding: '4px 8px 6px', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)' }}>
        Ordenar por {coluna.titulo}
      </div>
      {coluna.chave === 'unidade' && (
        <div style={{ padding: '0 8px 7px', fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.45 }}>
          Quadra › Lote › Bloco/Torre › Andar › Apto
        </div>
      )}
      {travada ? (
        <div style={{ display: 'flex', gap: 7, padding: '6px 8px', fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.45 }}>
          <Lock size={13} style={{ flex: 'none', marginTop: 1 }} />
          {motivo}
        </div>
      ) : (
        ([['asc', crescente, ArrowUp], ['desc', decrescente, ArrowDown]] as const).map(([sentido, rotulo, Icone]) => (
          <button
            key={sentido}
            onClick={() => onEscolher(sentido)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'left',
              padding: '7px 8px', border: 'none', borderRadius: 'var(--r-sm)', cursor: 'pointer',
              fontSize: 12.5, fontFamily: 'var(--sans)',
              background: ativa === sentido ? 'var(--accent-soft)' : 'transparent',
              color: ativa === sentido ? 'var(--accent-ink)' : 'var(--ink-2)',
              fontWeight: ativa === sentido ? 650 : 400,
            }}
          >
            <Icone size={13} /> {rotulo}
          </button>
        ))
      )}
    </div>
  )
}

function LinhaGrupo({
  item, topo, podeFinanceiro, onAlternar,
}: {
  item: Extract<ItemGrade, { tipo: 'grupo' }>
  topo: number
  podeFinanceiro: boolean
  onAlternar: () => void
}) {
  const { no, nivel, aberto } = item
  return (
    <div
      onClick={onAlternar}
      className="carteira-grupo"
      style={{
        position: 'absolute', top: topo, left: 0, right: 0, height: ALTURA_LINHA,
        display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer',
        paddingLeft: 10 + nivel * 18, paddingRight: 14,
        background: nivel === 0 ? 'var(--inset)' : 'var(--surface-2)',
        borderBottom: '1px solid var(--line)',
        fontWeight: 650, fontSize: 13, color: 'var(--ink)',
      }}
    >
      {aberto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      <span className="truncate" style={{ maxWidth: 380 }}>{no.rotulos[no.rotulos.length - 1]}</span>
      <span className="num" style={{ fontSize: 11.5, color: 'var(--ink-3)', fontWeight: 600 }}>
        {no.contagem}
      </span>
      {podeFinanceiro && (
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 18, alignItems: 'center' }}>
          {no.valorAtraso > 0 && (
            <span className="num" style={{ fontSize: 12, color: 'var(--danger-ink)', fontWeight: 700 }}>
              {brl(no.valorAtraso)} em atraso
            </span>
          )}
          <span className="num" style={{ fontSize: 12, color: 'var(--ink-2)' }}>
            {brl(no.valorAberto)} em aberto
          </span>
        </span>
      )}
    </div>
  )
}

const CORES_FAIXA: Record<string, [string, string]> = {
  em_dia: ['var(--good-soft)', 'var(--good-ink)'],
  d1_30: ['var(--accent-soft)', 'var(--accent-ink)'],
  d31_60: ['var(--accent-soft)', 'var(--accent-ink)'],
  d61_90: ['var(--danger-soft)', 'var(--danger-ink)'],
  d90_mais: ['var(--danger-soft)', 'var(--danger-ink)'],
}

function LinhaCliente({
  linha, nivel, colunas, larguraDe, topo, selecionada, ativa, podeFinanceiro, onSelecionar, onAbrir,
}: {
  linha: LinhaCarteira
  nivel: number
  colunas: ColunaDef[]
  larguraDe: (c: ColunaDef) => number
  topo: number
  selecionada: boolean
  ativa: boolean
  podeFinanceiro: boolean
  onSelecionar: (e: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean }) => void
  onAbrir: () => void
}) {
  const fundo = selecionada ? 'var(--accent-soft)' : 'var(--surface)'
  const celulaBase: CSSProperties = {
    flex: 'none', display: 'flex', alignItems: 'center', padding: '0 10px',
    fontSize: 12.5, color: 'var(--ink-2)', height: '100%',
    borderRight: '1px solid var(--line-2)', overflow: 'hidden',
  }

  return (
    <div
      onClick={e => onSelecionar(e)}
      onDoubleClick={onAbrir}
      className="carteira-linha"
      style={{
        position: 'absolute', top: topo, left: 0, height: ALTURA_LINHA, display: 'flex',
        background: fundo, borderBottom: '1px solid var(--line-2)', cursor: 'default',
        boxShadow: ativa ? 'inset 0 0 0 2px var(--accent)' : undefined,
      }}
    >
      {colunas.map((c, i) => {
        const conteudo = c.valor(linha)
        const primeira = i === 0
        return (
          <div
            key={c.chave}
            style={{
              ...celulaBase,
              width: larguraDe(c),
              justifyContent: c.alinhamento === 'right' ? 'flex-end' : c.alinhamento === 'center' ? 'center' : 'flex-start',
              fontFamily: c.mono ? 'var(--mono)' : 'var(--sans)',
              fontVariantNumeric: c.mono ? 'tabular-nums' : undefined,
              position: primeira ? 'sticky' : undefined,
              left: primeira ? 0 : undefined,
              zIndex: primeira ? 1 : undefined,
              background: primeira ? fundo : undefined,
              paddingLeft: primeira ? 10 + nivel * 18 : 10,
            }}
          >
            {primeira ? (
              <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                <button
                  onClick={e => { e.stopPropagation(); onAbrir() }}
                  className="truncate"
                  style={{
                    background: 'none', border: 'none', padding: 0, textAlign: 'left', cursor: 'pointer',
                    fontSize: 13, fontWeight: 600, color: 'var(--ink)', fontFamily: 'var(--sans)',
                  }}
                >
                  {conteudo}
                </button>
                <PilulaSituacao linha={linha} podeFinanceiro={podeFinanceiro} />
              </span>
            ) : (
              <span className="truncate">{conteudo}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

/**
 * A situação de todos; os números, só de quem pode.
 *
 * A pílula aparece para qualquer um que enxergue o cadastro; parcelas e valor
 * do atraso ficam no `title` (aparecem ao passar o mouse) e só existem quando o
 * backend os enviou — ou seja, com `erp.cobranca.view`.
 */
function PilulaSituacao({ linha, podeFinanceiro }: { linha: LinhaCarteira; podeFinanceiro: boolean }) {
  const [fundo, cor] = CORES_FAIXA[linha.faixa] ?? CORES_FAIXA.em_dia
  const detalhe = podeFinanceiro && !linha.adimplente
    ? `${linha.parcelasAtraso} parcela(s) em atraso · ${Number(linha.valorAtraso ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })} · ${linha.diasAtraso} dias`
    : podeFinanceiro
      ? 'Sem parcelas vencidas'
      : 'Valores exigem permissão de cobranças'

  return (
    <span
      title={detalhe}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 4, alignSelf: 'flex-start',
        background: fundo, color: cor, borderRadius: 999, padding: '0 7px',
        fontSize: 10, fontWeight: 700, lineHeight: '15px', whiteSpace: 'nowrap',
      }}
    >
      {linha.adimplente ? 'Adimplente' : 'Inadimplente'}
    </span>
  )
}
