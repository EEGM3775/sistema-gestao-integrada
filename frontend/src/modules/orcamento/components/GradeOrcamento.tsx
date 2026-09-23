import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { AlertTriangle, ChevronDown, ChevronRight, CornerDownRight, GitBranch, Layers3, MoreVertical } from 'lucide-react'
import { CAPS, mono } from '../ui'
import { achatar, brl, FONTE_ROTULO, mesBR, montarArvore, num, paraDecimal, paraEdicao, peso, type NoEap } from '../lib'
import type { AnaliticaOrcamento, ItemOrcado, ItemOrcadoInsumo } from '../types'

import { contemSemAcento } from '@/utils/texto'

export type ColunaEditavel = 'descricao' | 'unidade' | 'quantidade' | 'custo_unitario'
const EDITAVEIS: ColunaEditavel[] = ['descricao', 'unidade', 'quantidade', 'custo_unitario']
const NUMERICAS = new Set<ColunaEditavel>(['quantidade', 'custo_unitario'])

const ALTURA_LINHA = 30
const JANELA_EXTRA = 12

const CATEGORIA_ROTULO: Record<string, string> = {
  material: 'Material',
  mao_de_obra: 'Mão de obra',
  equipamento: 'Equipamento',
  encargos_complementares: 'Enc. complementares',
  outro: 'Outro',
}

export interface Cursor { linha: number; coluna: ColunaEditavel }

interface Colunas { largura: number; alinhamento: CSSProperties['textAlign'] }
const LARGURAS: Record<string, Colunas> = {
  eap: { largura: 86, alinhamento: 'left' },
  fonte: { largura: 126, alinhamento: 'left' },
  descricao: { largura: 0, alinhamento: 'left' },
  unidade: { largura: 58, alinhamento: 'center' },
  quantidade: { largura: 108, alinhamento: 'right' },
  custo_unitario: { largura: 116, alinhamento: 'right' },
  // Fica **colada** no custo unitário de propósito: é a data daquele preço, não
  // um atributo solto da linha. Item aposentado pela fonte permanece na planilha
  // com o preço e a data que tinha — e é aqui que isso deixa de ser invisível.
  data_base: { largura: 92, alinhamento: 'center' },
  bdi: { largura: 62, alinhamento: 'right' },
  total: { largura: 128, alinhamento: 'right' },
  peso: { largura: 62, alinhamento: 'right' },
  menu: { largura: 34, alinhamento: 'center' },
}

export interface EdicaoCelula { item: ItemOrcado; coluna: ColunaEditavel; valor: string }

/** O que ocupa uma linha da grade.
 *
 *  Sintético e analítico são a **mesma planilha** vista com e sem a composição
 *  — a convenção da SINAPI, que publica o sintético (um serviço por linha, com
 *  o custo unitário fechado) e o analítico (o mesmo serviço aberto nos insumos
 *  que formam aquele custo). Não é um recorte da EAP: nenhum serviço some ao
 *  trocar de modo, senão a planilha deixaria de fechar com o total do rodapé.
 *
 *  Por isso a grade deixou de rolar uma lista de nós da EAP e passou a rolar
 *  uma lista de **linhas**, das quais o nó é só um dos tipos. Quem edita,
 *  navega com o teclado e cola do Excel continua andando apenas sobre as linhas
 *  de EAP — insumo é leitura, e o que o muda é a composição, não a célula.
 */
type Linha =
  | { tipo: 'eap'; no: NoEap }
  | { tipo: 'insumo'; pai: ItemOrcado; insumo: ItemOrcadoInsumo; nivel: number }
  | { tipo: 'sem-composicao'; pai: ItemOrcado; nivel: number }

const ehEap = (linha: Linha | undefined): linha is { tipo: 'eap'; no: NoEap } => linha?.tipo === 'eap'

export default function GradeOrcamento({
  itens, totalOrcamento, bdiPadrao, editavel, modo, filtro, dataBaseOrcamento,
  insumos, carregandoInsumos, onEditar, onColar, onAbrirLinha, onMenu, onExplodir,
}: {
  itens: ItemOrcado[]
  totalOrcamento: string
  bdiPadrao: string
  /** Data-base do cabeçalho. A linha cujo preço é anterior a ela está atrasada:
   *  a planilha se anuncia por um mês e carrega preço de outro. */
  dataBaseOrcamento?: string | null
  editavel: boolean
  modo: 'sintetico' | 'analitico'
  filtro: string
  /** A composição de cada linha, indexada pelo id. Só chega em analítico. */
  insumos?: AnaliticaOrcamento
  carregandoInsumos?: boolean
  onEditar: (item: ItemOrcado, coluna: ColunaEditavel, valor: string) => void
  onColar: (edicoes: EdicaoCelula[]) => void
  onAbrirLinha: (item: ItemOrcado) => void
  onMenu: (item: ItemOrcado, ancora: DOMRect) => void
  onExplodir?: (item: ItemOrcado) => void
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

  const visiveis = useMemo<Linha[]>(() => {
    const busca = filtro.trim()
    if (busca) {
      // Com filtro a hierarquia já está quebrada (a linha que casa aparece sem
      // o pai): abrir composição em cima disso viraria ruído.
      const casa = (n: NoEap) =>
        contemSemAcento(n.item.descricao, busca) ||
        contemSemAcento(n.item.codigo_referencia, busca) ||
        contemSemAcento(n.item.codigo_eap, busca)
      return achatar(arvore, new Set()).filter(casa).map(no => ({ tipo: 'eap', no }) as Linha)
    }

    const linhas: Linha[] = []
    for (const no of achatar(arvore, recolhidos)) {
      linhas.push({ tipo: 'eap', no })
      if (modo !== 'analitico') continue
      const item = no.item
      // Agrupador não tem composição: o custo dele é a soma dos filhos, e
      // pendurar insumo embaixo de etapa contaria o mesmo insumo duas vezes.
      if (item.tipo_linha === 'sintetico') continue
      if (recolhidos.has(item.item_orcado_id)) continue
      const composicao = insumos?.[String(item.item_orcado_id)] ?? []
      if (composicao.length) {
        for (const insumo of composicao) {
          linhas.push({ tipo: 'insumo', pai: item, insumo, nivel: no.nivel + 1 })
        }
      } else if (!carregandoInsumos) {
        // Dado honesto: a linha sem composição gravada diz isso, em vez de
        // parecer serviço que "não tem insumo". São dois casos diferentes — o
        // que veio do catálogo e nunca foi explodido, e o de preço digitado.
        linhas.push({ tipo: 'sem-composicao', pai: item, nivel: no.nivel + 1 })
      }
    }
    return linhas
  }, [arvore, recolhidos, modo, filtro, insumos, carregandoInsumos])

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

  /** Próxima linha **de EAP** na direção pedida. As linhas de insumo ficam de
   *  fora da navegação: o cursor da grade é o cursor da planilha, e parar numa
   *  linha que não se edita quebraria a descida contínua de quem digita
   *  quantidade atrás de quantidade. */
  const pularParaEap = useCallback((partida: number, direcao: number) => {
    const passo = direcao >= 0 ? 1 : -1
    for (let i = partida; i >= 0 && i < visiveis.length; i += passo) {
      if (ehEap(visiveis[i])) return i
    }
    for (let i = partida; i >= 0 && i < visiveis.length; i -= passo) {
      if (ehEap(visiveis[i])) return i
    }
    return -1
  }, [visiveis])

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
      const bruta = Math.max(0, Math.min(visiveis.length - 1, linha + dLinha))
      const destino = pularParaEap(bruta, dLinha || dColuna || 1)
      return destino < 0 ? atual : { linha: destino, coluna }
    })
  }, [visiveis.length, pularParaEap])

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

  const aoTeclar = (e: KeyboardEvent<HTMLDivElement>, no: NoEap, coluna: ColunaEditavel, temComposicao: boolean) => {
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
    else if (e.key === ' ' && (no.filhos.length || temComposicao)) { e.preventDefault(); alternar(no.item.item_orcado_id) }
    else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && editavel) {
      setEditando(e.key)
      setEmEdicao(true)
    }
  }

  /** Colar bloco do Excel: a área colada se ancora na célula com foco e desce
   *  pelas linhas visíveis — **saltando as de insumo**, que não se editam.
   *  Fora da grade, o orçamentista faria isso à mão. */
  const aoColar = (e: React.ClipboardEvent, indice: number, coluna: ColunaEditavel) => {
    const texto = e.clipboardData.getData('text/plain')
    if (!texto.includes('\t') && !texto.includes('\n')) return
    e.preventDefault()
    if (!editavel) return
    const bloco = texto.replace(/\r/g, '').split('\n').filter(l => l !== '').map(l => l.split('\t'))
    const colunaInicial = EDITAVEIS.indexOf(coluna)
    const edicoes: EdicaoCelula[] = []
    let atual = indice
    for (const linha of bloco) {
      while (atual < visiveis.length && !ehEap(visiveis[atual])) atual += 1
      const alvo = visiveis[atual]
      if (!ehEap(alvo)) break
      linha.forEach((bruto, dc) => {
        const col = EDITAVEIS[colunaInicial + dc]
        if (!col) return
        if (alvo.no.item.tipo_linha === 'sintetico' && col !== 'descricao') return
        edicoes.push({ item: alvo.no.item, coluna: col, valor: NUMERICAS.has(col) ? paraDecimal(bruto) : bruto.trim() })
      })
      atual += 1
    }
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
        {cel('fonte', modo === 'analitico' ? 'Fonte / natureza' : 'Fonte / código')}
        {cel('descricao', 'Descrição')}
        {cel('unidade', 'Und')}
        {cel('quantidade', 'Quantidade')}
        {cel('custo_unitario', 'Custo unit.')}
        {cel('data_base', 'Data-base')}
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
            {fatia.map((linha, iFatia) => {
              const indice = primeira + iFatia

              // --- linha de insumo: a composição do serviço logo acima -------
              if (linha.tipo === 'insumo') {
                const { insumo, pai } = linha
                const quantidadeServico = Number(pai.quantidade) || 0
                const consumo = Number(insumo.coeficiente) * quantidadeServico
                const parcela = Number(insumo.custo_no_item) * quantidadeServico
                const maoDeObra = insumo.categoria === 'mao_de_obra'
                return (
                  <div
                    key={`ins-${insumo.insumo_id}`}
                    style={{
                      display: 'flex', alignItems: 'stretch', height: ALTURA_LINHA,
                      borderBottom: '1px solid var(--line-2)', fontSize: 11.5,
                      background: 'var(--inset)', color: 'var(--ink-3)',
                    }}
                  >
                    {cel('eap', (
                      <span style={{ display: 'flex', alignItems: 'center', paddingLeft: linha.nivel * 11 + 13 }}>
                        <CornerDownRight size={11} style={{ color: 'var(--ink-3)' }} />
                      </span>
                    ))}
                    {cel('fonte', (
                      <span
                        title={maoDeObra
                          ? 'Mão de obra — a parcela já inclui os encargos sociais do regime do orçamento.'
                          : `Natureza do insumo: ${CATEGORIA_ROTULO[insumo.categoria] ?? insumo.categoria}.`}
                        style={{
                          ...CAPS, fontSize: 9, padding: '1px 5px', borderRadius: 3, cursor: 'help',
                          background: maoDeObra ? 'var(--accent-soft)' : 'var(--surface-2)',
                          color: maoDeObra ? 'var(--accent-ink)' : 'var(--ink-3)',
                        }}
                      >
                        {CATEGORIA_ROTULO[insumo.categoria] ?? insumo.categoria}
                      </span>
                    ))}
                    {cel('descricao', (
                      <span title={insumo.descricao} style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {insumo.descricao}
                      </span>
                    ))}
                    {cel('unidade', insumo.unidade)}
                    {cel('quantidade', (
                      <span
                        style={{ ...mono }}
                        title={`Coeficiente ${num(insumo.coeficiente)} por ${pai.unidade || 'unidade'} `
                          + `× ${num(pai.quantidade)} = consumo do insumo neste serviço.`}
                      >{num(consumo)}</span>
                    ))}
                    {cel('custo_unitario', <span style={{ ...mono }}>{num(insumo.custo_unitario)}</span>)}
                    {cel('data_base', '')}
                    {cel('bdi', '')}
                    {cel('total', (
                      <span
                        style={{ ...mono }}
                        title="Parcela do insumo no custo direto do serviço — sem BDI, que já está na linha do serviço."
                      >{brl(parcela)}</span>
                    ))}
                    {cel('peso', (
                      <span
                        style={{ ...mono, fontSize: 10.5 }}
                        title="Peso do insumo dentro da composição deste serviço (não do orçamento)."
                      >{Number(insumo.peso_pct).toFixed(1)}</span>
                    ))}
                    {cel('menu', '')}
                  </div>
                )
              }

              // --- linha sem composição gravada -----------------------------
              if (linha.tipo === 'sem-composicao') {
                const { pai } = linha
                const doCatalogo = pai.item !== null
                return (
                  <div
                    key={`vazio-${pai.item_orcado_id}`}
                    style={{
                      display: 'flex', alignItems: 'center', height: ALTURA_LINHA, gap: 7,
                      borderBottom: '1px solid var(--line-2)', fontSize: 11.5,
                      background: 'var(--inset)', color: 'var(--ink-3)',
                      paddingLeft: linha.nivel * 11 + 108,
                    }}
                  >
                    <CornerDownRight size={11} />
                    {doCatalogo ? (
                      <>
                        <span>composição não explodida — o preço veio fechado da base.</span>
                        {onExplodir && (
                          <button
                            onClick={() => onExplodir(pai)}
                            style={{
                              display: 'inline-flex', alignItems: 'center', gap: 4, border: 'none',
                              background: 'none', cursor: 'pointer', padding: 0,
                              color: 'var(--net-ink)', fontSize: 11.5, fontWeight: 650,
                            }}
                          ><GitBranch size={11} />explodir</button>
                        )}
                      </>
                    ) : (
                      <span>preço digitado — esta linha não tem composição para abrir.</span>
                    )}
                  </div>
                )
              }

              // --- linha da EAP ---------------------------------------------
              const no = linha.no
              const item = no.item
              const sintetico = item.tipo_linha === 'sintetico'
              const temComposicao = modo === 'analitico' && !sintetico
                && (insumos?.[String(item.item_orcado_id)]?.length ?? 0) > 0
              const temFilhos = no.filhos.length > 0 || temComposicao
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
                        onKeyDown={e => aoTeclar(e, no, coluna, temComposicao)}
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
                            onKeyDown={e => aoTeclar(e, no, coluna, temComposicao)}
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

                  {cel('data_base', sintetico ? '' : (() => {
                    // Sintético não tem preço próprio (é soma dos filhos), logo
                    // não tem data-base — inventar uma aqui seria dado fabricado.
                    const atrasada = Boolean(
                      item.data_base_preco && dataBaseOrcamento
                      && item.data_base_preco < dataBaseOrcamento,
                    )
                    return (
                      <span
                        title={atrasada
                          ? `Preço de ${mesBR(item.data_base_preco)}, anterior à data-base `
                            + `${mesBR(dataBaseOrcamento)} da planilha — item aposentado pela fonte `
                            + 'ou não reprecificado. O total não reflete a data-base anunciada.'
                          : item.data_base_preco
                            ? `Preço da publicação de ${mesBR(item.data_base_preco)}.`
                            // Sem afirmar a causa: a linha pode ter sido digitada,
                            // ou vinda do catálogo sem a data ter sido registrada.
                            : 'Sem data-base registrada neste preço.'}
                        style={{
                          ...mono, fontSize: 11,
                          display: 'inline-flex', alignItems: 'center', gap: 4,
                          padding: atrasada ? '1px 5px' : 0,
                          borderRadius: 3,
                          // `danger`, e não um tom ameno: linha fora da data-base
                          // anunciada é defeito da peça que vai para a licitação,
                          // não enfeite. O módulo não tem par `warn`.
                          background: atrasada ? 'var(--danger-soft)' : undefined,
                          color: atrasada ? 'var(--danger-ink)' : 'var(--ink-3)',
                          fontWeight: atrasada ? 600 : 400,
                          cursor: 'help',
                        }}
                      >
                        {atrasada && <AlertTriangle size={11} />}
                        {mesBR(item.data_base_preco)}
                      </span>
                    )
                  })())}

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
