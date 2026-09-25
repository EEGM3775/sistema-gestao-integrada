import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import {
  AlertTriangle, ChevronDown, ChevronRight, CopyIcon, CornerDownRight, FileSpreadsheet, GitBranch,
  Layers3, Lock, Plus, Ruler, Trash2, Wrench, X,
} from 'lucide-react'
import { CAPS, mono } from '../ui'
import { achatar, brl, FONTE_ROTULO, mesBR, montarArvore, num, paraDecimal, paraEdicao, peso, type NoEap } from '../lib'
import type { AnaliticaOrcamento, ItemOrcado, ItemOrcadoInsumo } from '../types'

import { contemSemAcento } from '@/utils/texto'

/** As colunas que se digitam direto na linha da EAP.
 *
 *  `codigo_eap` entra desde a ORC.10e. Ele é derivado da árvore por padrão — e
 *  isso continua certo —, mas digitar por cima é o gesto que assume o código à
 *  mão: o `onEditar` manda `eap_manual: true` junto, porque separar as duas
 *  coisas em dois atos faria o primeiro parecer quebrado (digita, some).
 */
export type ColunaEditavel = 'codigo_eap' | 'descricao' | 'unidade' | 'quantidade' | 'custo_unitario'
const EDITAVEIS: ColunaEditavel[] = ['codigo_eap', 'descricao', 'unidade', 'quantidade', 'custo_unitario']
const NUMERICAS = new Set<ColunaEditavel>(['quantidade', 'custo_unitario'])

/** As colunas da composição que se digitam — ORC.10c. */
export type ColunaInsumo = 'descricao' | 'unidade' | 'coeficiente' | 'custo_unitario'
const NUMERICAS_INSUMO = new Set<ColunaInsumo>(['coeficiente', 'custo_unitario'])

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

/** Onde a linha arrastada vai pousar em relação à linha sob o cursor. */
export type Zona = 'antes' | 'dentro' | 'depois'
export interface Alvo { id: number; zona: Zona }

export type OperacaoDeBloco = 'indentar' | 'desindentar' | 'cima' | 'baixo'

/** Os verbos que ficam **na linha**, a um clique — ORC.10h.
 *
 *  **Por que eles saíram do menu.** Tudo morava atrás de um `⋮`: um ícone que
 *  não diz nada (o dono perguntou para que servia) e que cobrava **dois
 *  cliques** para qualquer coisa — um para abrir, outro para escolher. Os
 *  quatro verbos que se usam o dia inteiro passaram a ser ícone próprio na
 *  própria linha: aí o desenho já diz o que faz (régua é medida, lixeira é
 *  excluir) e o clique é um só.
 *
 *  **Por que quatro, e não dez.** A linha tem 30px de altura e a planilha tem
 *  mil delas; dez ícones seriam uma barra de ferramentas por linha, e a coluna
 *  comeria a descrição — que é o que se lê. O resto continua acessível pelo
 *  botão de **mais ações** e pelo botão direito do mouse, que não custa pixel
 *  nenhum. */
export type AcaoRapida = 'memoria' | 'quantitativo' | 'duplicar' | 'excluir'

/** O que a grade pede quando alguém solta um bloco arrastado. */
export interface PedidoDeMover { itens: number[]; pai: number | null; posicao: number | null }

interface Colunas { largura: number; alinhamento: CSSProperties['textAlign'] }
const LARGURAS: Record<string, Colunas> = {
  marca: { largura: 26, alinhamento: 'center' },
  codigo_eap: { largura: 92, alinhamento: 'left' },
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
  // De 34 para 132: cabe os quatro verbos frequentes mais o de "mais ações".
  // O espaço é **reservado sempre**, mesmo com os ícones apagados — apareceram
  // no hover empurrando a linha, a planilha inteira tremeria ao passar o mouse.
  menu: { largura: 132, alinhamento: 'right' },
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
 *  uma lista de **linhas**, das quais o nó é só um dos tipos. Quem navega com o
 *  cursor e cola do Excel continua andando apenas sobre as linhas de EAP; a de
 *  insumo tem edição própria (ORC.10c), com o seu próprio foco.
 */
type Linha =
  | { tipo: 'eap'; no: NoEap }
  | { tipo: 'insumo'; pai: ItemOrcado; insumo: ItemOrcadoInsumo; nivel: number }
  | { tipo: 'novo-insumo'; pai: ItemOrcado; nivel: number }
  | { tipo: 'sem-composicao'; pai: ItemOrcado; nivel: number }

const ehEap = (linha: Linha | undefined): linha is { tipo: 'eap'; no: NoEap } => linha?.tipo === 'eap'

/** Um verbo da linha: ícone, dica e um clique.
 *
 *  `title` **e** `aria-label`, e os dois dizendo coisas diferentes de propósito:
 *  o primeiro explica o verbo a quem vê o desenho e não o entende; o segundo
 *  nomeia a linha, porque quem usa leitor de tela precisa saber *de qual* linha
 *  é aquele botão num rol de mil. */
function BotaoDaLinha({ titulo, rotulo, desligado, perigo, onClick, onDoubleClick, children }: {
  titulo: string
  rotulo: string
  desligado?: boolean
  perigo?: boolean
  onClick: (e: React.MouseEvent<HTMLButtonElement>) => void
  onDoubleClick?: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      disabled={desligado}
      onClick={e => { e.stopPropagation(); onClick(e) }}
      onDoubleClick={onDoubleClick}
      title={desligado ? undefined : titulo}
      aria-label={rotulo}
      style={{
        border: 'none', background: 'none', display: 'flex', padding: 3, borderRadius: 4,
        cursor: desligado ? 'default' : 'pointer',
        color: perigo ? 'var(--danger-ink)' : 'var(--ink-3)',
        opacity: desligado ? 0.25 : 1,
      }}
    >{children}</button>
  )
}

export default function GradeOrcamento({
  itens, totalOrcamento, bdiPadrao, editavel, modo, filtro, dataBaseOrcamento,
  insumos, carregandoInsumos, selecao, onSelecionar, onEditar, onColar, onAbrirLinha, onMenu,
  onExplodir, onMover, onOperacao, onEditarInsumo, onNovoInsumo, onRemoverInsumo,
  arrastandoDeFora, onSoltarDeFora, afetados, onExcluirSelecao, onAcaoRapida,
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
  /** ORC.10d — a seleção mora na página, porque a barra de lote age sobre ela. */
  selecao: ReadonlySet<number>
  onSelecionar: (ids: number[], modo: 'trocar' | 'alternar' | 'faixa' | 'somar-faixa') => void
  /** Quem **vai junto** sem estar marcado: os descendentes da seleção.
   *
   *  Vem pronto da página porque ela também precisa do número (a barra de lote
   *  conta, o diálogo de excluir nomeia). Calcular dos dois lados daria duas
   *  respostas para a mesma pergunta na mesma tela, que é como se produz a
   *  divergência que ninguém entende depois. */
  afetados: ReadonlySet<number>
  /** `Delete` sobre a seleção. A grade **não** exclui: ela pede. Quem sabe
   *  quantas linhas e quanto dinheiro saem — e portanto quem pode perguntar de
   *  forma honesta — é a página. */
  onExcluirSelecao?: () => void
  /** Os quatro verbos de um clique na própria linha (ORC.10h). Ausente, a linha
   *  volta a ter só o botão de mais ações. */
  onAcaoRapida?: (item: ItemOrcado, acao: AcaoRapida) => void
  onEditar: (item: ItemOrcado, coluna: ColunaEditavel, valor: string) => void
  onColar: (edicoes: EdicaoCelula[]) => void
  onAbrirLinha: (item: ItemOrcado) => void
  onMenu: (item: ItemOrcado, ancora: DOMRect) => void
  onExplodir?: (item: ItemOrcado) => void
  /** ORC.10b — arrastar e soltar. Ausente, a grade não fica arrastável. */
  onMover?: (pedido: PedidoDeMover) => void
  /** ORC.10b — os atalhos de teclado (Alt + setas). */
  onOperacao?: (operacao: OperacaoDeBloco, itens: number[]) => void
  /** ORC.10c — a composição vira escrita. Ausentes, ela segue só de leitura. */
  onEditarInsumo?: (insumo: ItemOrcadoInsumo, coluna: ColunaInsumo, valor: string) => void
  onNovoInsumo?: (pai: ItemOrcado) => void
  onRemoverInsumo?: (insumo: ItemOrcadoInsumo) => void
  /** ORC.10f — há algo vindo do painel do banco no ar. A grade acende as mesmas
   *  zonas de pouso do arrasto interno: quem arrasta não deveria ter de aprender
   *  dois alvos diferentes para o mesmo gesto. */
  arrastandoDeFora?: boolean
  onSoltarDeFora?: (alvo: Alvo) => void
}) {
  const [recolhidos, setRecolhidos] = useState<ReadonlySet<number>>(new Set())
  const [cursor, setCursor] = useState<Cursor | null>(null)
  const [editando, setEditando] = useState<string>('')
  const [emEdicao, setEmEdicao] = useState(false)
  const [celulaInsumo, setCelulaInsumo] = useState<{ id: number; coluna: ColunaInsumo } | null>(null)
  const [arrastando, setArrastando] = useState<number[] | null>(null)
  const [alvo, setAlvo] = useState<Alvo | null>(null)
  const [scrollTop, setScrollTop] = useState(0)
  const [altura, setAltura] = useState(600)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const inputInsumoRef = useRef<HTMLInputElement>(null)
  /** Última linha clicada — a âncora do Shift+clique. */
  const ancora = useRef<number | null>(null)

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
  const porId = useMemo(
    () => new Map(itens.map(i => [i.item_orcado_id, i])), [itens],
  )

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
        // A linha de "somar insumo" fecha a composição — é o gesto do
        // Arquimedes, e sem ela acrescentar um item exigiria sair da grade.
        if (editavel && onNovoInsumo) {
          linhas.push({ tipo: 'novo-insumo', pai: item, nivel: no.nivel + 1 })
        }
      } else if (!carregandoInsumos) {
        // Dado honesto: a linha sem composição gravada diz isso, em vez de
        // parecer serviço que "não tem insumo". São dois casos diferentes — o
        // que veio do catálogo e nunca foi explodido, e o de preço digitado.
        linhas.push({ tipo: 'sem-composicao', pai: item, nivel: no.nivel + 1 })
      }
    }
    return linhas
  }, [arvore, recolhidos, modo, filtro, insumos, carregandoInsumos, editavel, onNovoInsumo])

  /** Os ids de EAP na ordem em que a tela os mostra.
   *
   *  É a régua do Shift e a do `Delete`: seleção de faixa que ignorasse o
   *  recolhimento ou o filtro marcaria o que não está à vista, e a primeira vez
   *  que isso acontece com o botão Excluir ao lado é a última vez que alguém
   *  confia na seleção. */
  const idsVisiveis = useMemo(
    () => visiveis.filter(ehEap).map(l => l.no.item.item_orcado_id), [visiveis],
  )

  const alternar = useCallback((id: number) => {
    setRecolhidos(atual => {
      const proximo = new Set(atual)
      if (proximo.has(id)) proximo.delete(id)
      else proximo.add(id)
      return proximo
    })
  }, [])

  // --- seleção (ORC.10d) ---------------------------------------------------

  /** Clique numa linha: troca, alterna (Ctrl), estende (Shift) ou soma a faixa
   *  (Ctrl+Shift).
   *
   *  `Shift` sozinho **substitui** pela faixa e `Ctrl+Shift` **soma** — a
   *  convenção de toda grade, e a diferença importa em planilha grande: pegar
   *  três trechos separados da EAP para aplicar um percentual é o caso normal,
   *  e sem a faixa somada isso eram trinta cliques com Ctrl.
   *
   *  A **âncora não se move** numa extensão: é o que deixa arrastar o Shift
   *  para cima e para baixo sobre o mesmo ponto de partida. E quando ela aponta
   *  para uma linha que não está mais à vista — excluída, recolhida, escondida
   *  pelo filtro —, o Shift não vira clique simples em silêncio: a âncora é
   *  refeita na linha clicada, que é onde a pessoa acabou de dizer que está. */
  const clicarNaLinha = useCallback((id: number, e: { ctrlKey: boolean; metaKey: boolean; shiftKey: boolean }) => {
    const comando = e.ctrlKey || e.metaKey
    if (e.shiftKey && ancora.current != null) {
      const de = idsVisiveis.indexOf(ancora.current)
      const ate = idsVisiveis.indexOf(id)
      if (de >= 0 && ate >= 0) {
        const [a, b] = de <= ate ? [de, ate] : [ate, de]
        onSelecionar(idsVisiveis.slice(a, b + 1), comando ? 'somar-faixa' : 'faixa')
        return
      }
    }
    ancora.current = id
    onSelecionar([id], comando ? 'alternar' : 'trocar')
  }, [idsVisiveis, onSelecionar])

  /** Marcar tudo pelo cabeçalho — e "tudo" é **o que está à vista**.
   *
   *  Com filtro ativo, é o resultado do filtro; sem filtro, a planilha inteira.
   *  A alternativa (marcar sempre tudo) é o defeito que o `Ctrl+A` tinha: quem
   *  filtra por "alvenaria", vê três linhas e manda marcar tudo, marca
   *  quatrocentas — e o botão ao lado é o de excluir. */
  const todasMarcadas = idsVisiveis.length > 0 && idsVisiveis.every(id => selecao.has(id))
  const algumaMarcada = !todasMarcadas && idsVisiveis.some(id => selecao.has(id))

  /** Sobre quem o gesto age: a seleção, se a linha do cursor estiver nela; a
   *  linha sozinha, caso contrário. É a regra de qualquer grade — agir sobre a
   *  seleção quando se está dentro dela, e sobre a linha quando se está fora. */
  const alvoDoGesto = useCallback((id: number) => (
    selecao.has(id) ? [...selecao] : [id]
  ), [selecao])

  // --- edição de célula ----------------------------------------------------

  const iniciarEdicao = useCallback((no: NoEap, coluna: ColunaEditavel) => {
    if (!editavel) return
    if (no.item.tipo_linha === 'sintetico' && coluna !== 'descricao' && coluna !== 'codigo_eap') return
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
   *  linha de composição quebraria a descida contínua de quem digita
   *  quantidade atrás de quantidade — a composição tem o foco dela. */
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

  useLayoutEffect(() => {
    if (celulaInsumo) inputInsumoRef.current?.focus()
  }, [celulaInsumo])

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

    // ORC.10b — os atalhos de estrutura. `Alt` e não `Tab`: Tab já é a
    // navegação entre células desde a ORC.5, e é o que o orçamentista usa o dia
    // inteiro. Roubá-lo para indentar (como faz um editor de texto) tiraria o
    // gesto mais frequente para dar lugar ao mais raro. Alt+setas é o que
    // Project, Notion e os editores de árvore usam, e não colide com nada.
    if (e.altKey && onOperacao) {
      const bloco = alvoDoGesto(no.item.item_orcado_id)
      const mapa: Record<string, OperacaoDeBloco> = {
        ArrowRight: 'indentar', ArrowLeft: 'desindentar',
        ArrowUp: 'cima', ArrowDown: 'baixo',
      }
      const operacao = mapa[e.key]
      if (operacao) { e.preventDefault(); onOperacao(operacao, bloco); return }
    }

    // Seleção pelo teclado: quem digita quantidade atrás de quantidade não tira
    // a mão para pegar o mouse, e marcar seis linhas seguidas eram seis cliques.
    if (e.shiftKey && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault()
      const onde = idsVisiveis.indexOf(no.item.item_orcado_id)
      const destino = onde + (e.key === 'ArrowDown' ? 1 : -1)
      if (onde >= 0 && destino >= 0 && destino < idsVisiveis.length) {
        if (ancora.current == null || idsVisiveis.indexOf(ancora.current) < 0) {
          ancora.current = no.item.item_orcado_id
        }
        const de = idsVisiveis.indexOf(ancora.current)
        const [a, b] = de <= destino ? [de, destino] : [destino, de]
        onSelecionar(idsVisiveis.slice(a, b + 1), 'faixa')
        mover(e.key === 'ArrowDown' ? 1 : -1, 0)
      }
      return
    }
    if (e.key === 'Escape' && selecao.size) {
      e.preventDefault()
      onSelecionar([], 'trocar')
      return
    }
    // `Delete` não exclui daqui: pede à página, que é quem sabe dizer quanto sai.
    if ((e.key === 'Delete' || e.key === 'Backspace') && selecao.size && onExcluirSelecao) {
      e.preventDefault()
      onExcluirSelecao()
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
   *  pelas linhas visíveis — **saltando as de insumo**, que têm edição própria.
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
      const alvoLinha = visiveis[atual]
      if (!ehEap(alvoLinha)) break
      linha.forEach((bruto, dc) => {
        const col = EDITAVEIS[colunaInicial + dc]
        if (!col) return
        const sintetico = alvoLinha.no.item.tipo_linha === 'sintetico'
        if (sintetico && col !== 'descricao' && col !== 'codigo_eap') return
        edicoes.push({ item: alvoLinha.no.item, coluna: col, valor: NUMERICAS.has(col) ? paraDecimal(bruto) : bruto.trim() })
      })
      atual += 1
    }
    if (edicoes.length) onColar(edicoes)
  }

  // --- arrastar e soltar (ORC.10b) -----------------------------------------

  const podeArrastar = Boolean(editavel && onMover && !filtro.trim())

  /** Traduz "soltei nesta linha, nesta zona" em pai + posição.
   *
   *  A posição é contada sobre os irmãos do destino **sem** o que está sendo
   *  movido, que é exatamente a régua do servidor — as duas pontas medem a
   *  mesma coisa, então arrastar para baixo dentro do próprio grupo não
   *  escorrega uma posição. */
  const resolverDestino = useCallback((movidos: number[], alvoLinha: Alvo): PedidoDeMover | null => {
    const destino = porId.get(alvoLinha.id)
    if (!destino) return null
    const emMovimento = new Set(movidos)
    if (emMovimento.has(destino.item_orcado_id) && alvoLinha.zona === 'dentro') return null

    if (alvoLinha.zona === 'dentro') {
      return { itens: movidos, pai: destino.item_orcado_id, posicao: null }
    }
    const irmaos = itens
      .filter(i => i.pai === destino.pai && !emMovimento.has(i.item_orcado_id))
      .sort((a, b) => a.ordem - b.ordem || a.item_orcado_id - b.item_orcado_id)
    const indice = irmaos.findIndex(i => i.item_orcado_id === destino.item_orcado_id)
    if (indice < 0) return { itens: movidos, pai: destino.pai, posicao: null }
    return {
      itens: movidos,
      pai: destino.pai,
      posicao: alvoLinha.zona === 'antes' ? indice : indice + 1,
    }
  }, [itens, porId])

  const zonaDoEvento = (e: React.DragEvent, sintetico: boolean): Zona => {
    const caixa = e.currentTarget.getBoundingClientRect()
    const relativo = (e.clientY - caixa.top) / caixa.height
    // Faixa de "dentro" maior no sintético: é nele que se solta para agrupar, e
    // um alvo de 50% no meio de 30px é fácil de errar. No analítico a faixa é
    // menor porque pendurar item sob item é o gesto menos comum.
    const margem = sintetico ? 0.28 : 0.4
    if (relativo < margem) return 'antes'
    if (relativo > 1 - margem) return 'depois'
    return 'dentro'
  }

  const primeira = Math.max(0, Math.floor(scrollTop / ALTURA_LINHA) - JANELA_EXTRA)
  const quantas = Math.ceil(altura / ALTURA_LINHA) + JANELA_EXTRA * 2
  const fatia = visiveis.slice(primeira, primeira + quantas)

  const cel = (
    chave: keyof typeof LARGURAS, conteudo: React.ReactNode, extra?: CSSProperties,
    aoClicar?: (e: React.MouseEvent) => void,
  ) => (
    <div onClick={aoClicar} style={{
      cursor: aoClicar ? 'pointer' : undefined,
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

  /** A célula editável da composição — mesma mecânica da célula da EAP, com
   *  estado próprio porque o cursor da planilha não desce até aqui. */
  const celInsumo = (
    insumo: ItemOrcadoInsumo, coluna: ColunaInsumo, chave: keyof typeof LARGURAS,
    exibicao: React.ReactNode, extra?: CSSProperties,
  ) => {
    const podeMexer = Boolean(editavel && onEditarInsumo)
    const ativa = celulaInsumo?.id === insumo.insumo_id && celulaInsumo.coluna === coluna
    const largura = LARGURAS[chave]
    return (
      <div
        onDoubleClick={() => {
          if (!podeMexer) return
          const bruto = insumo[coluna]
          setEditando(NUMERICAS_INSUMO.has(coluna) ? paraEdicao(bruto) : String(bruto ?? ''))
          setCelulaInsumo({ id: insumo.insumo_id, coluna })
        }}
        title={podeMexer ? 'Duplo clique para editar' : undefined}
        style={{
          width: largura.largura || undefined,
          flex: largura.largura ? 'none' : 1,
          minWidth: largura.largura ? undefined : 200,
          padding: ativa ? 0 : '0 9px',
          display: 'flex', alignItems: 'center',
          justifyContent: largura.alinhamento === 'right' ? 'flex-end' : largura.alinhamento === 'center' ? 'center' : 'flex-start',
          overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis',
          cursor: podeMexer ? 'cell' : 'default',
          ...extra,
        }}
      >
        {ativa ? (
          <input
            ref={inputInsumoRef}
            value={editando}
            onChange={e => setEditando(e.target.value)}
            onBlur={() => {
              setCelulaInsumo(null)
              const original = String(insumo[coluna] ?? '')
              const valor = NUMERICAS_INSUMO.has(coluna) ? paraDecimal(editando) : editando.trim()
              if (valor === original) return
              if (NUMERICAS_INSUMO.has(coluna) && Number(valor) === Number(original)) return
              onEditarInsumo?.(insumo, coluna, valor)
            }}
            onKeyDown={e => {
              if (e.key === 'Escape') { e.preventDefault(); setCelulaInsumo(null) }
              else if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur() }
            }}
            style={{
              width: '100%', height: '100%', border: '2px solid var(--accent)', outline: 'none',
              background: 'var(--surface)', color: 'var(--ink)', padding: '0 7px', fontSize: 11.5,
              textAlign: NUMERICAS_INSUMO.has(coluna) ? 'right' : 'left',
              ...(NUMERICAS_INSUMO.has(coluna) ? mono : { fontFamily: 'var(--sans)' }),
            }}
          />
        ) : exibicao}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, background: 'var(--surface)' }}>
      <div style={{
        display: 'flex', alignItems: 'stretch', height: 32, flex: 'none',
        background: 'var(--surface-2)', borderBottom: '1px solid var(--line)', ...CAPS, fontSize: 10,
      }}>
        {cel('marca', idsVisiveis.length > 0 ? (
          <input
            type="checkbox"
            checked={todasMarcadas}
            // `indeterminate` não existe como atributo em JSX — é propriedade do
            // nó. Sem ele, seleção parcial mostraria a caixa vazia, e clicar
            // pareceria "marcar tudo" quando na verdade é "marcar o resto".
            ref={el => { if (el) el.indeterminate = algumaMarcada }}
            onChange={() => onSelecionar(todasMarcadas ? [] : idsVisiveis, 'trocar')}
            title={todasMarcadas
              ? 'Desmarcar tudo'
              : filtro.trim()
                ? `Marcar as ${idsVisiveis.length} linhas deste filtro`
                : 'Marcar a planilha inteira'}
            aria-label="Marcar tudo o que está à vista"
            style={{ cursor: 'pointer', accentColor: 'var(--accent)' }}
          />
        ) : '')}
        {cel('codigo_eap', 'Item')}
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
        onDragLeave={e => { if (e.currentTarget === e.target) setAlvo(null) }}
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
                    className="orc-linha-insumo"
                    style={{
                      display: 'flex', alignItems: 'stretch', height: ALTURA_LINHA,
                      borderBottom: '1px solid var(--line-2)', fontSize: 11.5,
                      background: 'var(--inset)', color: 'var(--ink-3)',
                    }}
                  >
                    {cel('marca', '')}
                    {cel('codigo_eap', (
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
                    {celInsumo(insumo, 'descricao', 'descricao', (
                      <span title={insumo.descricao} style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {insumo.descricao}
                      </span>
                    ))}
                    {celInsumo(insumo, 'unidade', 'unidade', insumo.unidade)}
                    {/* A coluna mostra o **consumo** (coeficiente × quantidade do
                        serviço), que é o que se confere; a edição é do
                        **coeficiente**, que é o que a composição guarda. O
                        `title` diz a conta inteira para os dois não se
                        confundirem na hora de digitar. */}
                    {celInsumo(insumo, 'coeficiente', 'quantidade', (
                      <span
                        style={{ ...mono }}
                        title={`Coeficiente ${num(insumo.coeficiente)} por ${pai.unidade || 'unidade'} `
                          + `× ${num(pai.quantidade)} = ${num(consumo)}. Editar aqui muda o coeficiente.`}
                      >{num(consumo)}</span>
                    ), mono)}
                    {celInsumo(insumo, 'custo_unitario', 'custo_unitario', (
                      <span style={{ ...mono }}>{num(insumo.custo_unitario)}</span>
                    ), mono)}
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
                    {cel('menu', editavel && onRemoverInsumo ? (
                      <button
                        onClick={() => onRemoverInsumo(insumo)}
                        title="Tirar este insumo da composição"
                        aria-label={`Tirar ${insumo.descricao} da composição`}
                        style={{
                          border: 'none', background: 'none', cursor: 'pointer',
                          color: 'var(--ink-3)', padding: 2, display: 'flex',
                        }}
                      ><X size={12} /></button>
                    ) : null)}
                  </div>
                )
              }

              // --- linha de somar insumo ------------------------------------
              if (linha.tipo === 'novo-insumo') {
                return (
                  <div
                    key={`novo-${linha.pai.item_orcado_id}`}
                    style={{
                      display: 'flex', alignItems: 'center', height: ALTURA_LINHA, gap: 6,
                      borderBottom: '1px solid var(--line-2)', fontSize: 11.5,
                      background: 'var(--inset)', paddingLeft: linha.nivel * 11 + 134,
                    }}
                  >
                    <button
                      onClick={() => onNovoInsumo?.(linha.pai)}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4, border: 'none',
                        background: 'none', cursor: 'pointer', padding: 0,
                        color: 'var(--net-ink)', fontSize: 11.5, fontWeight: 650,
                      }}
                    ><Plus size={11} />somar insumo</button>
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
                      paddingLeft: linha.nivel * 11 + 134,
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
                      <span>preço digitado — esta linha não tem composição gravada.</span>
                    )}
                    {editavel && onNovoInsumo && (
                      <button
                        onClick={() => onNovoInsumo(pai)}
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 4, border: 'none',
                          background: 'none', cursor: 'pointer', padding: 0,
                          color: 'var(--net-ink)', fontSize: 11.5, fontWeight: 650,
                        }}
                      ><Plus size={11} />montar do zero</button>
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
              const marcada = selecao.has(item.item_orcado_id)
              const vaiJunto = !marcada && afetados.has(item.item_orcado_id)
              const emArrasto = arrastando?.includes(item.item_orcado_id) ?? false
              const alvoAqui = alvo?.id === item.item_orcado_id ? alvo.zona : null

              return (
                <div
                  key={item.item_orcado_id}
                  className="orc-linha"
                  draggable={podeArrastar}
                  onDragStart={e => {
                    const bloco = alvoDoGesto(item.item_orcado_id)
                    setArrastando(bloco)
                    e.dataTransfer.effectAllowed = 'move'
                    // Alguns navegadores cancelam o arrasto sem payload.
                    e.dataTransfer.setData('text/plain', String(item.item_orcado_id))
                  }}
                  onDragEnd={() => { setArrastando(null); setAlvo(null) }}
                  onContextMenu={e => {
                    // O botão direito abre o mesmo menu dos `⋮`. Um ícone de três
                    // pontos na ponta de uma linha de 30px não se anuncia — e o
                    // que está atrás dele não é secundário: é a memória de
                    // cálculo, a do quantitativo, o preço real, explodir,
                    // duplicar, travar preço e excluir. O menu de contexto é onde
                    // as pessoas procuram primeiro, e agora os dois levam ao
                    // mesmo lugar.
                    e.preventDefault()
                    if (!selecao.has(item.item_orcado_id)) {
                      ancora.current = item.item_orcado_id
                      onSelecionar([item.item_orcado_id], 'trocar')
                    }
                    onMenu(item, new DOMRect(e.clientX + 214, e.clientY, 0, 0))
                  }}
                  onClick={e => {
                    // Com modificador, o clique pega em **qualquer** ponto da
                    // linha, inclusive sobre célula editável: quem segura Ctrl ou
                    // Shift está selecionando, não navegando.
                    if (e.ctrlKey || e.metaKey || e.shiftKey) {
                      e.preventDefault()
                      clicarNaLinha(item.item_orcado_id, e)
                    }
                  }}
                  onDragOver={e => {
                    if (!arrastando && !arrastandoDeFora) return
                    e.preventDefault()
                    e.dataTransfer.dropEffect = arrastando ? 'move' : 'copy'
                    setAlvo({ id: item.item_orcado_id, zona: zonaDoEvento(e, sintetico) })
                  }}
                  onDrop={e => {
                    e.preventDefault()
                    const bloco = arrastando
                    const onde = alvo
                    setArrastando(null)
                    setAlvo(null)
                    if (!onde) return
                    if (!bloco) {
                      // Veio do painel do banco: a grade não sabe adotar item nem
                      // criar linha — só sabe **onde** foi solto, que é a única
                      // coisa que ela pode responder. Quem insere é a página.
                      if (arrastandoDeFora) onSoltarDeFora?.(onde)
                      return
                    }
                    const pedido = resolverDestino(bloco, onde)
                    if (pedido) onMover?.(pedido)
                  }}
                  style={{
                    display: 'flex', alignItems: 'stretch', height: ALTURA_LINHA,
                    borderBottom: '1px solid var(--line-2)', fontSize: 12.5,
                    background: marcada
                      ? 'var(--accent-soft)'
                      // Quem vai junto ganha marca **mais fraca** que a da
                      // seleção: ele não foi escolhido, foi arrastado pela
                      // escolha, e as duas coisas não podem parecer a mesma.
                      : vaiJunto ? 'var(--inset)'
                        : sintetico ? 'var(--surface-2)' : undefined,
                    fontWeight: sintetico ? 700 : 400,
                    color: sintetico ? 'var(--ink)' : 'var(--ink-2)',
                    opacity: emArrasto ? 0.4 : 1,
                    // As três zonas se anunciam por onde a marca aparece: risco
                    // em cima, risco embaixo, moldura em volta. Um indicador só
                    // (a moldura) faria "dentro" e "depois" parecerem o mesmo
                    // gesto, e soltar no lugar errado reorganiza a planilha.
                    //
                    // A moldura do arrasto **ganha** do risco de "vai junto": a
                    // pergunta do momento é onde isto vai pousar, e duas marcas
                    // disputando a mesma borda não respondem nenhuma das duas.
                    boxShadow: alvoAqui === 'dentro'
                      ? 'inset 0 0 0 2px var(--accent)'
                      : vaiJunto ? 'inset 3px 0 0 var(--accent)' : undefined,
                    borderTop: alvoAqui === 'antes' ? '2px solid var(--accent)' : undefined,
                    borderBottomColor: alvoAqui === 'depois' ? 'var(--accent)' : undefined,
                    borderBottomWidth: alvoAqui === 'depois' ? 2 : 1,
                    cursor: podeArrastar ? 'grab' : undefined,
                  }}
                >
                  {cel('marca', (
                    <input
                      type="checkbox"
                      checked={marcada}
                      onChange={() => {}}
                      onClick={e => { e.stopPropagation(); clicarNaLinha(item.item_orcado_id, e) }}
                      title={vaiJunto
                        ? 'Esta linha já vai junto — ela pende de uma linha marcada.'
                        : 'Selecionar · Shift marca a faixa · Ctrl soma uma linha'}
                      aria-label={`Selecionar ${item.descricao}`}
                      style={{ cursor: 'pointer', accentColor: 'var(--accent)' }}
                    />
                  ))}

                  {/* O código EAP é célula editável desde a ORC.10e, mas o
                      cabeçalho dela (o chevron de recolher e o recuo do nível)
                      continua aqui — é o que dá a forma de árvore à coluna. */}
                  <div
                    className="orc-cel"
                    tabIndex={0}
                    onFocus={() => setCursor({ linha: indice, coluna: 'codigo_eap' })}
                    onClick={e => { setCursor({ linha: indice, coluna: 'codigo_eap' }); clicarNaLinha(item.item_orcado_id, e) }}
                    onDoubleClick={() => iniciarEdicao(no, 'codigo_eap')}
                    onKeyDown={e => aoTeclar(e, no, 'codigo_eap', temComposicao)}
                    onPaste={e => aoColar(e, indice, 'codigo_eap')}
                    style={{
                      width: LARGURAS.codigo_eap.largura, flex: 'none',
                      display: 'flex', alignItems: 'center', gap: 2,
                      padding: emEdicao && cursor?.linha === indice && cursor.coluna === 'codigo_eap' ? 0 : '0 9px',
                      paddingLeft: emEdicao && cursor?.linha === indice && cursor.coluna === 'codigo_eap'
                        ? 0 : no.nivel * 9 + 4,
                      overflow: 'hidden', whiteSpace: 'nowrap',
                      background: cursor?.linha === indice && cursor.coluna === 'codigo_eap' && !emEdicao && !marcada
                        ? 'var(--accent-soft)' : undefined,
                      cursor: editavel ? 'cell' : 'default',
                    }}
                  >
                    {emEdicao && cursor?.linha === indice && cursor.coluna === 'codigo_eap' ? (
                      <input
                        ref={inputRef}
                        value={editando}
                        onChange={e => setEditando(e.target.value)}
                        onBlur={() => confirmar(no, 'codigo_eap')}
                        onKeyDown={e => aoTeclar(e, no, 'codigo_eap', temComposicao)}
                        style={{
                          width: '100%', height: '100%', border: '2px solid var(--accent)', outline: 'none',
                          background: 'var(--surface)', color: 'var(--ink)', padding: '0 7px',
                          fontSize: 11.5, ...mono,
                        }}
                      />
                    ) : (
                      <>
                        {temFilhos ? (
                          <button
                            onClick={e => { e.stopPropagation(); alternar(item.item_orcado_id) }}
                            style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--ink-3)', padding: 0, display: 'flex' }}
                            title={recolhido ? 'Expandir' : 'Recolher'}
                          >
                            {recolhido ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                          </button>
                        ) : <span style={{ width: 13, flex: 'none' }} />}
                        <span style={{
                          ...mono, fontSize: 11.5, overflow: 'hidden', textOverflow: 'ellipsis',
                          color: sintetico ? 'var(--ink)' : 'var(--ink-3)',
                        }}>{item.codigo_eap}</span>
                        {item.eap_manual && (
                          <Lock
                            size={9}
                            style={{ flex: 'none', color: 'var(--accent-ink)' }}
                          />
                        )}
                      </>
                    )}
                  </div>

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

                  {EDITAVEIS.filter(c => c !== 'codigo_eap').map(coluna => {
                    const ativa = cursor?.linha === indice && cursor.coluna === coluna
                    const bloqueada = sintetico && coluna !== 'descricao'
                    const travada = coluna === 'custo_unitario' && item.preco_travado
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
                        // A descrição da SINAPI passa de 130 caracteres e a
                        // coluna corta com reticências — e na linha da planilha
                        // **não havia como ler o resto**, nem passando o mouse
                        // (a linha de composição tinha `title`, a da EAP não).
                        // O sistema escondia metade do nome do serviço e não
                        // oferecia caminho nenhum até ele.
                        title={travada
                          ? 'Preço travado: reprecificação e lote não encostam nesta linha.'
                          : coluna === 'descricao' ? item.descricao : undefined}
                        style={{
                          width: LARGURAS[coluna].largura || undefined,
                          flex: LARGURAS[coluna].largura ? 'none' : 1,
                          minWidth: LARGURAS[coluna].largura ? undefined : 200,
                          padding: emEdicao && ativa ? 0 : '0 9px',
                          display: 'flex', alignItems: 'center', gap: 4,
                          justifyContent: LARGURAS[coluna].alinhamento === 'right' ? 'flex-end' : LARGURAS[coluna].alinhamento === 'center' ? 'center' : 'flex-start',
                          overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis',
                          background: ativa && !emEdicao && !marcada ? 'var(--accent-soft)' : undefined,
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
                        ) : (
                          <>
                            {travada && <Lock size={10} style={{ flex: 'none', color: 'var(--accent-ink)' }} />}
                            {exibicao}
                          </>
                        )}
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

                  {cel(
                    'total',
                    <span style={{ ...mono, fontWeight: sintetico ? 700 : 500, color: 'var(--ink)' }}>{brl(item.total_com_bdi)}</span>,
                    undefined,
                    // Coluna larga e de leitura pura: era espaço morto, e agora é
                    // área de pegada. Clicar num número para marcar a linha é o
                    // que qualquer um tenta antes de achar a caixinha.
                    e => clicarNaLinha(item.item_orcado_id, e),
                  )}

                  {cel('peso', p > 0 ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ width: 22, height: 4, borderRadius: 99, background: 'var(--inset)', overflow: 'hidden', display: 'inline-block' }}>
                        <span style={{ display: 'block', width: `${Math.min(p, 100)}%`, height: '100%', background: p >= 10 ? 'var(--accent)' : 'var(--ink-3)' }} />
                      </span>
                      <span style={{ ...mono, fontSize: 10.5, color: 'var(--ink-3)' }}>{p.toFixed(1)}</span>
                    </span>
                  ) : null)}

                  {cel('menu', (
                    // `orc-acoes` some quando a linha não está sob o cursor, para
                    // a planilha não virar um mural de ícones — e fica **fixa** na
                    // linha marcada, que é aquela sobre a qual a pessoa vai agir.
                    <span
                      className={`orc-acoes${marcada ? ' orc-acoes-fixas' : ''}`}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 1 }}
                    >
                      {onAcaoRapida && (
                        <>
                          <BotaoDaLinha
                            titulo="Memória de cálculo — de que insumos este preço é feito"
                            rotulo={`Memória de cálculo de ${item.descricao}`}
                            onClick={() => onAcaoRapida(item, 'memoria')}
                          ><FileSpreadsheet size={13} /></BotaoDaLinha>
                          <BotaoDaLinha
                            titulo="Memória do quantitativo — de onde veio esta quantidade"
                            rotulo={`Memória do quantitativo de ${item.descricao}`}
                            desligado={sintetico}
                            onClick={() => onAcaoRapida(item, 'quantitativo')}
                          ><Ruler size={13} /></BotaoDaLinha>
                          <BotaoDaLinha
                            titulo="Duplicar esta linha (com o que pende dela)"
                            rotulo={`Duplicar ${item.descricao}`}
                            desligado={!editavel}
                            onClick={() => onAcaoRapida(item, 'duplicar')}
                          ><CopyIcon size={13} /></BotaoDaLinha>
                          <BotaoDaLinha
                            titulo="Excluir esta linha"
                            rotulo={`Excluir ${item.descricao}`}
                            desligado={!editavel}
                            perigo
                            onClick={() => onAcaoRapida(item, 'excluir')}
                          ><Trash2 size={13} /></BotaoDaLinha>
                        </>
                      )}
                      <BotaoDaLinha
                        // **Chave inglesa, e não três pontos.** O `⋮` é o ícone que
                        // não diz nada: serve para qualquer coisa e por isso não
                        // anuncia nenhuma. Ferramenta diz "dá para mexer nesta
                        // linha", que é exatamente o que há atrás dele.
                        titulo={'Mais ações desta linha: preço real, explodir composição, '
                          + 'sub-item, travar preço, descrição detalhada e salvar a composição '
                          + 'no banco. O botão direito do mouse abre o mesmo menu.'}
                        rotulo={`Mais ações da linha ${item.codigo_eap} — ${item.descricao}`}
                        onClick={e => {
                          if (!selecao.has(item.item_orcado_id)) {
                            ancora.current = item.item_orcado_id
                            onSelecionar([item.item_orcado_id], 'trocar')
                          }
                          onMenu(item, e.currentTarget.getBoundingClientRect())
                        }}
                        onDoubleClick={() => onAbrirLinha(item)}
                      ><Wrench size={13} /></BotaoDaLinha>
                    </span>
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
