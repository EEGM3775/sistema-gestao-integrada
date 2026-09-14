import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  Columns3, Crosshair, Diamond, ImageDown, Link2, Maximize2, Minus, Plus, Sheet, Trash2,
} from 'lucide-react'
import { contemSemAcento } from '@/utils/texto'
import { ALTURA_LINHA, FOLGA_VIRTUAL } from '../medidas'
import {
  ajustarAJanela, achatarArvore, baixarTexto, cadeiaDe, csvDaGrade, ESCALAS, hojeIso,
  montarEixo, pngDoSvg, pxDaEscala, textoDePredecessoras, ZOOM_MAX, ZOOM_MIN,
  type ChaveEscala, type LinhaDaArvore,
} from '../lib'
import type {
  Atividade, CampoEditavel, ChaveColuna, ColunaGrade, EdicaoCelula, Filtro, LinhaDaBase,
  PayloadGantt, TipoPrecedencia,
} from '../types'
import { CATALOGO_COLUNAS, COLUNAS_PADRAO } from '../colunas'
import { valorExibido } from '../celulas'
import GradeWbs, { type Cursor, type GestoDeEstrutura } from './GradeWbs'
import LinhaDoTempo from './LinhaDoTempo'
import BarraDeSelecao from './BarraDeSelecao'

/** A escolha de colunas e as larguras vivem no navegador de quem planeja.
 *  Não é preferência de conta: é o formato da bancada dele, e vai junto com a
 *  tela que ele usa — não com o login. */
const CHAVE_LOCAL = 'pdca:grade-wbs'

interface Preferencias {
  chaves: ChaveColuna[]
  larguras: Record<string, number>
  painel: number
}

function lerPreferencias(): Preferencias {
  const padrao: Preferencias = { chaves: COLUNAS_PADRAO, larguras: {}, painel: 520 }
  try {
    const bruto = localStorage.getItem(CHAVE_LOCAL)
    if (!bruto) return padrao
    const lido = JSON.parse(bruto) as Partial<Preferencias>
    const conhecidas = new Set(CATALOGO_COLUNAS.map(c => c.chave))
    return {
      // Filtra contra o catálogo: uma coluna removida do código não pode
      // ressuscitar de um localStorage antigo e quebrar a grade inteira.
      chaves: (lido.chaves ?? padrao.chaves).filter(c => conhecidas.has(c)),
      larguras: lido.larguras ?? {},
      painel: lido.painel ?? padrao.painel,
    }
  } catch {
    return padrao
  }
}

interface Props {
  dados: PayloadGantt
  editavel: boolean
  filtro: string
  filtros: ReadonlySet<Filtro>
  selecionadas: ReadonlySet<number>
  onSelecionar: (ids: number[]) => void
  onEditarCelula: (atividade: Atividade, campo: CampoEditavel, valor: string) => void
  onColar: (edicoes: EdicaoCelula[]) => void
  onGesto: (gesto: GestoDeEstrutura, atividade: Atividade) => void
  onMenu: (atividade: Atividade, ancora: DOMRect) => void
  onAbrirInspetor: (id: number) => void
  onReprogramar: (id: number, payload: { nao_comecar_antes_de?: string | null; duracao_dias?: number }) => void
  onLigar: (origem: number, destino: number, tipo: TipoPrecedencia) => void
  onExcluirPrecedencia: (id: number) => void
  onAviso: (texto: string) => void
  /** As ações que valem para o conjunto selecionado. `duracao` é a única com
   *  argumento, e por isso o parâmetro é opcional em vez de haver duas props. */
  onEmBloco: (acao: AcaoEmBloco, valor?: number) => void
}

export type AcaoEmBloco = 'indentar' | 'outdentar' | 'cadeia' | 'duracao' | 'excluir'

export default function GanttCronograma({
  dados, editavel, filtro, filtros, selecionadas, onSelecionar, onEditarCelula,
  onColar, onGesto, onMenu, onAbrirInspetor, onReprogramar, onLigar, onExcluirPrecedencia,
  onAviso, onEmBloco,
}: Props) {
  const [preferencias, setPreferencias] = useState<Preferencias>(lerPreferencias)
  const [escala, setEscala] = useState<ChaveEscala>('semana')
  const [zoom, setZoom] = useState(1)
  const [recolhidas, setRecolhidas] = useState<ReadonlySet<number>>(new Set())
  const [mostrarBase, setMostrarBase] = useState(true)
  const [mostrarFolga, setMostrarFolga] = useState(true)
  const [mostrarNomes, setMostrarNomes] = useState(false)
  const [realcarCadeia, setRealcarCadeia] = useState(false)
  const [escolhendoColunas, setEscolhendoColunas] = useState(false)
  const [cursor, setCursor] = useState<Cursor | null>(null)
  const [janela, setJanela] = useState({ inicio: 0, fim: 60 })

  const esquerdaRef = useRef<HTMLDivElement>(null)
  const direitaRef = useRef<HTMLDivElement>(null)
  //: Quem está mandando na rolagem agora. Sem esta trava, sincronizar A com B
  //: dispara o onScroll de B, que sincroniza A de volta — e a rolagem trava.
  const conduzindo = useRef<'esquerda' | 'direita' | null>(null)
  const ancoraDoPainel = useRef<{ x: number; largura: number } | null>(null)

  useEffect(() => {
    localStorage.setItem(CHAVE_LOCAL, JSON.stringify(preferencias))
  }, [preferencias])

  const colunas: ColunaGrade[] = useMemo(
    () => preferencias.chaves
      .map(chave => CATALOGO_COLUNAS.find(c => c.chave === chave))
      .filter((c): c is ColunaGrade => !!c)
      .map(c => ({ ...c, largura: preferencias.larguras[c.chave] ?? c.largura })),
    [preferencias],
  )

  const porId = useMemo(
    () => new Map(dados.atividades.map(a => [a.atividade_id, a])),
    [dados.atividades],
  )

  /** Quem está ligado a quem — só montado quando algum recorte precisa. */
  const ligadas = useMemo(() => {
    if (!filtros.has('sem_rede')) return null
    const ids = new Set<number>()
    for (const p of dados.precedencias) { ids.add(p.origem); ids.add(p.destino) }
    return ids
  }, [dados.precedencias, filtros])

  const situacaoNaBase = useMemo(() => {
    if (!filtros.has('atrasadas')) return null
    return new Map(dados.base.linhas.map(l => [l.codigo, l.situacao]))
  }, [dados.base.linhas, filtros])

  /** Com busca ou com recorte a árvore **não** é preservada: a linha que casa
   *  aparece sozinha, sem os pais. É a mesma escolha da grade do Orçamento, e
   *  pelo mesmo motivo — mostrar o galho inteiro para exibir uma folha
   *  esconderia o resultado no meio do que não casou.
   *
   *  Os recortes se **somam** (E, não OU): quem procura "crítica e sem peso"
   *  está atrás da interseção — a atividade que decide o prazo e não pondera
   *  avanço nenhum. Um OU devolveria as duas listas juntas e nenhuma pergunta
   *  respondida. */
  const linhas: LinhaDaArvore[] = useMemo(() => {
    if (!filtro && filtros.size === 0) return achatarArvore(dados.atividades, recolhidas)
    return achatarArvore(dados.atividades, new Set()).filter(l => {
      const a = l.atividade
      if (filtro && !(contemSemAcento(a.nome, filtro) || contemSemAcento(a.codigo, filtro))) return false
      if (filtros.has('criticas') && !a.critica) return false
      if (filtros.has('marcos') && !a.eh_marco) return false
      if (filtros.has('com_restricao') && !a.nao_comecar_antes_de) return false
      if (filtros.has('sem_peso') && (a.tem_filhos || a.peso != null)) return false
      if (filtros.has('sem_rede') && (a.tem_filhos || ligadas?.has(a.atividade_id))) return false
      if (filtros.has('atrasadas') && situacaoNaBase?.get(a.codigo) !== 'atrasada') return false
      return true
    })
  }, [dados.atividades, recolhidas, filtro, filtros, ligadas, situacaoNaBase])

  const linhaDe = useMemo(() => {
    const mapa = new Map<number, number>()
    linhas.forEach((l, i) => mapa.set(l.atividade.atividade_id, i))
    return mapa
  }, [linhas])

  const base = useMemo(() => {
    const mapa = new Map<string, LinhaDaBase>()
    for (const l of dados.base.linhas) if (l.base_inicio) mapa.set(l.codigo, l)
    return mapa
  }, [dados.base])

  const eixo = useMemo(
    () => montarEixo(dados.atividades, dados.cronograma.data_inicio, escala, zoom),
    [dados.atividades, dados.cronograma.data_inicio, escala, zoom],
  )

  /** A cadeia da atividade selecionada — ela, quem a empurra e quem ela empurra.
   *  Só com **uma** selecionada: com três, o realce cobriria metade do plano e
   *  não responderia mais à pergunta que ele existe para responder. */
  const cadeia = useMemo(() => {
    if (!realcarCadeia || selecionadas.size !== 1) return null
    const [id] = [...selecionadas]
    const { montante, jusante } = cadeiaDe(id, dados.precedencias)
    return new Set<number>([id, ...montante, ...jusante])
  }, [realcarCadeia, selecionadas, dados.precedencias])

  const larguraGrade = colunas.reduce((soma, c) => soma + c.largura, 0)

  /** O texto das predecessoras por atividade — a grade monta o seu para desenhar
   *  e o CSV precisa do mesmo, para o arquivo não divergir da tela. */
  const textoDePredecessorasPorId = useMemo(() => {
    const mapa = new Map<number, string>()
    for (const l of linhas) {
      mapa.set(l.atividade.atividade_id, textoDePredecessoras(l.atividade, dados.precedencias, porId))
    }
    return mapa
  }, [linhas, dados.precedencias, porId])

  // -------------------------------------------------------------------------
  // Rolagem: dois painéis, um movimento só
  // -------------------------------------------------------------------------

  const recalcularJanela = useCallback(() => {
    const rolo = direitaRef.current ?? esquerdaRef.current
    if (!rolo) return
    const topo = Math.floor(rolo.scrollTop / ALTURA_LINHA) - FOLGA_VIRTUAL
    const quantas = Math.ceil(rolo.clientHeight / ALTURA_LINHA) + FOLGA_VIRTUAL * 2
    const inicio = Math.max(topo, 0)
    setJanela({ inicio, fim: inicio + quantas })
  }, [])

  const sincronizar = (lado: 'esquerda' | 'direita') => {
    if (conduzindo.current && conduzindo.current !== lado) return
    conduzindo.current = lado
    const origem = lado === 'esquerda' ? esquerdaRef.current : direitaRef.current
    const destino = lado === 'esquerda' ? direitaRef.current : esquerdaRef.current
    if (origem && destino && destino.scrollTop !== origem.scrollTop) {
      destino.scrollTop = origem.scrollTop
    }
    recalcularJanela()
    requestAnimationFrame(() => { conduzindo.current = null })
  }

  useLayoutEffect(() => {
    recalcularJanela()
    const aoRedimensionar = () => recalcularJanela()
    window.addEventListener('resize', aoRedimensionar)
    return () => window.removeEventListener('resize', aoRedimensionar)
  }, [recalcularJanela, linhas.length])

  /** Arrastar a divisória. O painel guarda a largura em preferência, e não em
   *  estado de tela, porque quem trabalha com o Gantt aberto o dia inteiro
   *  ajusta isso uma vez. */
  useEffect(() => {
    const mover = (e: PointerEvent) => {
      const ancora = ancoraDoPainel.current
      if (!ancora) return
      const largura = Math.min(Math.max(ancora.largura + (e.clientX - ancora.x), 220), 1100)
      setPreferencias(p => ({ ...p, painel: largura }))
    }
    const soltar = () => { ancoraDoPainel.current = null }
    window.addEventListener('pointermove', mover)
    window.addEventListener('pointerup', soltar)
    return () => {
      window.removeEventListener('pointermove', mover)
      window.removeEventListener('pointerup', soltar)
    }
  }, [])

  // -------------------------------------------------------------------------
  // Levar o plano para fora
  // -------------------------------------------------------------------------

  /** Acima disto o PNG não cabe no canvas do navegador (o limite prático fica
   *  perto de 32.000 px de altura, e cada linha ocupa 30). Em vez de gerar uma
   *  imagem cortada em silêncio, exporta a janela visível e diz que fez isso. */
  const LIMITE_PNG = 1000

  const exportarCsv = () => {
    const texto = csvDaGrade(
      linhas,
      colunas.map(c => ({ chave: c.chave, rotulo: c.rotulo })),
      (a, chave) => valorExibido(a, chave as ChaveColuna, textoDePredecessorasPorId).texto,
    )
    baixarTexto(
      'cronograma-' + dados.cronograma.obra_nome.replace(/[^\w-]+/g, '-').toLowerCase()
        + '-v' + dados.cronograma.versao + '.csv',
      texto, 'text/csv;charset=utf-8',
    )
  }

  const exportarPng = async () => {
    const svg = direitaRef.current?.querySelector<SVGSVGElement>('svg[data-gantt]')
    if (!svg) return
    const inteiro = linhas.length <= LIMITE_PNG
    if (inteiro) setJanela({ inicio: 0, fim: linhas.length })
    // Dois quadros: um para o React desenhar as linhas que faltavam, outro para
    // o navegador aplicar o layout antes de a imagem ser lida.
    await new Promise(requestAnimationFrame)
    await new Promise(requestAnimationFrame)
    try {
      const fundo = getComputedStyle(document.body).backgroundColor || '#fff'
      const png = await pngDoSvg(svg, fundo)
      const url = URL.createObjectURL(png)
      const ancora = document.createElement('a')
      ancora.href = url
      ancora.download = 'gantt-' + dados.cronograma.obra_nome.replace(/[^\w-]+/g, '-').toLowerCase() + '.png'
      ancora.click()
      URL.revokeObjectURL(url)
      onAviso(inteiro
        ? 'Gantt exportado com as ' + linhas.length + ' linhas visíveis no recorte atual.'
        : 'O plano tem ' + linhas.length + ' linhas e o PNG comporta ' + LIMITE_PNG
          + ': foi exportado o trecho na tela. Use um recorte ou o CSV para levar tudo.')
    } catch (e) {
      onAviso(e instanceof Error ? e.message : 'Não foi possível gerar a imagem.')
    } finally {
      recalcularJanela()
    }
  }

  const irParaHoje = () => {
    const rolo = direitaRef.current
    if (!rolo) return
    rolo.scrollLeft = Math.max(eixo.x(hojeIso()) - rolo.clientWidth / 3, 0)
  }

  const ajustar = () => {
    const largura = direitaRef.current?.clientWidth ?? 900
    const alvo = ajustarAJanela(dados.atividades, dados.cronograma.data_inicio, largura)
    setEscala(alvo.escala)
    setZoom(alvo.zoom)
  }

  const alternarNo = (id: number) => {
    setRecolhidas(anterior => {
      const proxima = new Set(anterior)
      if (proxima.has(id)) proxima.delete(id)
      else proxima.add(id)
      return proxima
    })
  }

  /** Clique na grade: única, faixa (Shift) ou alternar (Ctrl). A faixa se apoia
   *  no cursor anterior, que é o que o usuário entende por "daqui até ali". */
  const selecionarPorIndice = (indice: number, modo: 'unica' | 'faixa' | 'alternar') => {
    const alvo = linhas[indice]?.atividade
    if (!alvo) return
    if (modo === 'faixa' && cursor) {
      const [de, ate] = [Math.min(cursor.linha, indice), Math.max(cursor.linha, indice)]
      onSelecionar(linhas.slice(de, ate + 1).map(l => l.atividade.atividade_id))
      return
    }
    if (modo === 'alternar') {
      const proxima = new Set(selecionadas)
      if (proxima.has(alvo.atividade_id)) proxima.delete(alvo.atividade_id)
      else proxima.add(alvo.atividade_id)
      onSelecionar([...proxima])
      setCursor({ linha: indice, coluna: cursor?.coluna ?? 0 })
      return
    }
    onSelecionar([alvo.atividade_id])
    setCursor({ linha: indice, coluna: cursor?.coluna ?? 0 })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <BarraDeFerramentas
        escala={escala} setEscala={setEscala}
        zoom={zoom} setZoom={setZoom}
        mostrarBase={mostrarBase} setMostrarBase={setMostrarBase}
        mostrarFolga={mostrarFolga} setMostrarFolga={setMostrarFolga}
        mostrarNomes={mostrarNomes} setMostrarNomes={setMostrarNomes}
        realcarCadeia={realcarCadeia} setRealcarCadeia={setRealcarCadeia}
        temBase={dados.base.tem_base}
        baseVersao={dados.base.base?.versao ?? null}
        calculado={!!dados.cronograma.calculado_em}
        onAjustar={ajustar}
        onHoje={irParaHoje}
        onColunas={() => setEscolhendoColunas(v => !v)}
        onCsv={exportarCsv}
        onPng={() => void exportarPng()}
      />

      {escolhendoColunas && (
        <SeletorDeColunas
          chaves={preferencias.chaves}
          onFechar={() => setEscolhendoColunas(false)}
          onMudar={chaves => setPreferencias(p => ({ ...p, chaves }))}
        />
      )}

      <div style={{
        flex: 1, minHeight: 0, display: 'flex', border: '1px solid var(--line)',
        borderRadius: 12, background: 'var(--surface)', overflow: 'hidden',
      }}>
        <div
          ref={esquerdaRef}
          onScroll={() => sincronizar('esquerda')}
          style={{
            width: preferencias.painel, flex: `0 0 ${preferencias.painel}px`,
            overflow: 'auto', scrollbarWidth: 'none', position: 'relative',
          }}
        >
          <div style={{ width: Math.max(larguraGrade, preferencias.painel) }}>
            <GradeWbs
              linhas={linhas} janela={janela} colunas={colunas} largura={larguraGrade}
              editavel={editavel} precedencias={dados.precedencias} porId={porId}
              recolhidas={recolhidas} selecionadas={selecionadas} cursor={cursor}
              roloRef={esquerdaRef}
              onCursor={setCursor}
              onSelecionar={selecionarPorIndice}
              onAlternarNo={alternarNo}
              onEditar={onEditarCelula}
              onColar={onColar}
              onMenu={onMenu}
              onGesto={onGesto}
              onRedimensionar={(chave, largura) =>
                setPreferencias(p => ({ ...p, larguras: { ...p.larguras, [chave]: largura } }))}
            />
          </div>
        </div>

        <div
          onPointerDown={e => {
            e.preventDefault()
            ancoraDoPainel.current = { x: e.clientX, largura: preferencias.painel }
          }}
          title="Arraste para dividir a grade e a linha do tempo"
          style={{
            flex: '0 0 5px', cursor: 'col-resize', background: 'var(--line)', touchAction: 'none',
          }}
        />

        <div
          ref={direitaRef}
          onScroll={() => sincronizar('direita')}
          style={{ flex: 1, minWidth: 0, overflow: 'auto', position: 'relative' }}
        >
          <LinhaDoTempo
            linhas={linhas} janela={janela} eixo={eixo} escala={escala}
            precedencias={dados.precedencias} porId={porId} linhaDe={linhaDe}
            base={base} avanco={dados.avanco.por_atividade}
            mostrarBase={mostrarBase} mostrarFolga={mostrarFolga}
            mostrarNomes={mostrarNomes} editavel={editavel}
            selecionadas={selecionadas} cadeia={cadeia}
            onSelecionar={(id, modo) => {
              const indice = linhaDe.get(id)
              if (indice != null) selecionarPorIndice(indice, modo)
            }}
            onAbrir={onAbrirInspetor}
            onReprogramar={onReprogramar}
            onLigar={onLigar}
            onExcluirPrecedencia={onExcluirPrecedencia}
          />
        </div>
      </div>

      <BarraDeSelecao
        selecionadas={linhas.filter(l => selecionadas.has(l.atividade.atividade_id)).map(l => l.atividade)}
        editavel={editavel}
        onIndentar={() => onEmBloco('indentar')}
        onPromover={() => onEmBloco('outdentar')}
        onLigarEmCadeia={() => onEmBloco('cadeia')}
        onDuracao={dias => onEmBloco('duracao', dias)}
        onExcluir={() => onEmBloco('excluir')}
        onLimpar={() => onSelecionar([])}
      />

      <Legenda editavel={editavel} />
    </div>
  )
}

// ---------------------------------------------------------------------------

function BarraDeFerramentas({
  escala, setEscala, zoom, setZoom, mostrarBase, setMostrarBase, mostrarFolga,
  setMostrarFolga, mostrarNomes, setMostrarNomes, realcarCadeia, setRealcarCadeia,
  temBase, baseVersao, calculado, onAjustar, onHoje, onColunas, onCsv, onPng,
}: {
  escala: ChaveEscala; setEscala: (e: ChaveEscala) => void
  zoom: number; setZoom: (z: number) => void
  mostrarBase: boolean; setMostrarBase: (v: boolean) => void
  mostrarFolga: boolean; setMostrarFolga: (v: boolean) => void
  mostrarNomes: boolean; setMostrarNomes: (v: boolean) => void
  realcarCadeia: boolean; setRealcarCadeia: (v: boolean) => void
  temBase: boolean; baseVersao: number | null; calculado: boolean
  onAjustar: () => void; onHoje: () => void; onColunas: () => void
  onCsv: () => void; onPng: () => void
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '0 2px 10px', flexWrap: 'wrap' }}>
      <div style={{ display: 'flex', gap: 2, background: 'var(--inset)', padding: 3, borderRadius: 9 }}>
        {(Object.keys(ESCALAS) as ChaveEscala[]).map(chave => (
          <button
            key={chave} type="button" onClick={() => { setEscala(chave); setZoom(1) }}
            style={{
              border: 'none', borderRadius: 6, padding: '5px 11px', fontSize: 12, cursor: 'pointer',
              background: escala === chave ? 'var(--surface)' : 'transparent',
              color: escala === chave ? 'var(--ink)' : 'var(--ink-3)',
              fontWeight: escala === chave ? 600 : 400,
            }}
          >{ESCALAS[chave].rotulo}</button>
        ))}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <IconeBotao rotulo="Menos zoom" onClick={() => setZoom(Math.max(zoom / 1.35, ZOOM_MIN))}><Minus size={14} /></IconeBotao>
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)', width: 62, textAlign: 'center' }}>
          {pxDaEscala(escala, zoom).toFixed(1)} px/dia
        </span>
        <IconeBotao rotulo="Mais zoom" onClick={() => setZoom(Math.min(zoom * 1.35, ZOOM_MAX))}><Plus size={14} /></IconeBotao>
        <IconeBotao rotulo="Ajustar o plano à janela" onClick={onAjustar}><Maximize2 size={14} /></IconeBotao>
        <IconeBotao rotulo="Ir para hoje" onClick={onHoje}><Crosshair size={14} /></IconeBotao>
        <IconeBotao rotulo="Escolher colunas" onClick={onColunas}><Columns3 size={14} /></IconeBotao>
        <IconeBotao rotulo="Exportar a grade em CSV (abre no Excel)" onClick={onCsv}><Sheet size={14} /></IconeBotao>
        <IconeBotao rotulo="Exportar o Gantt em PNG" onClick={onPng}><ImageDown size={14} /></IconeBotao>
      </div>

      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center' }}>
        {temBase ? (
          <Alternador ligado={mostrarBase} onMudar={setMostrarBase}>
            Linha de base {baseVersao != null && <span style={{ color: 'var(--ink-3)' }}>(v{baseVersao})</span>}
          </Alternador>
        ) : (
          <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Sem linha de base — esta é a primeira versão</span>
        )}
        <Alternador ligado={mostrarFolga} onMudar={setMostrarFolga}>Folga</Alternador>
        <Alternador ligado={mostrarNomes} onMudar={setMostrarNomes}>Nomes na barra</Alternador>
        <Alternador ligado={realcarCadeia} onMudar={setRealcarCadeia}>Realçar a cadeia</Alternador>
      </div>

      {!calculado && (
        <span style={{
          fontSize: 12, color: 'var(--danger-ink)', background: 'var(--danger-soft)',
          padding: '4px 10px', borderRadius: 999,
        }}>
          Datas ainda não calculadas — rode o CPM
        </span>
      )}
    </div>
  )
}

function IconeBotao({ rotulo, onClick, children }: { rotulo: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button" onClick={onClick} title={rotulo} aria-label={rotulo}
      style={{
        display: 'grid', placeItems: 'center', width: 27, height: 27, borderRadius: 7,
        border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink-2)',
        cursor: 'pointer',
      }}
    >{children}</button>
  )
}

function Alternador({ ligado, onMudar, children }: {
  ligado: boolean; onMudar: (v: boolean) => void; children: React.ReactNode
}) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--ink-2)', cursor: 'pointer' }}>
      <input type="checkbox" checked={ligado} onChange={e => onMudar(e.target.checked)} />
      {children}
    </label>
  )
}

/** O seletor de colunas. Ordem também se muda aqui: arrastar cabeçalho seria
 *  mais bonito e brigaria com a alça de largura, que ocupa a mesma borda. */
function SeletorDeColunas({ chaves, onMudar, onFechar }: {
  chaves: ChaveColuna[]
  onMudar: (chaves: ChaveColuna[]) => void
  onFechar: () => void
}) {
  const ligadas = new Set(chaves)
  const alternar = (chave: ChaveColuna) => {
    if (ligadas.has(chave)) {
      if (chaves.length <= 1) return
      onMudar(chaves.filter(c => c !== chave))
    } else {
      onMudar([...chaves, chave])
    }
  }
  const mover = (chave: ChaveColuna, direcao: -1 | 1) => {
    const i = chaves.indexOf(chave)
    const j = i + direcao
    if (i < 0 || j < 0 || j >= chaves.length) return
    const copia = [...chaves]
    copia[i] = copia[j]
    copia[j] = chave
    onMudar(copia)
  }

  return (
    <div style={{
      border: '1px solid var(--line)', borderRadius: 10, background: 'var(--surface)',
      padding: 12, marginBottom: 10, display: 'flex', flexWrap: 'wrap', gap: 8,
    }}>
      {CATALOGO_COLUNAS.map(col => {
        const ligada = ligadas.has(col.chave)
        return (
          <span
            key={col.chave}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12,
              border: '1px solid var(--line)', borderRadius: 999, padding: '3px 4px 3px 10px',
              background: ligada ? 'var(--inset)' : 'transparent',
              color: ligada ? 'var(--ink)' : 'var(--ink-3)',
            }}
          >
            <button
              type="button" onClick={() => alternar(col.chave)}
              style={{ border: 'none', background: 'none', padding: 0, cursor: 'pointer', color: 'inherit', font: 'inherit' }}
            >
              {col.rotulo}
            </button>
            {ligada && (
              <>
                <button type="button" onClick={() => mover(col.chave, -1)} aria-label="Mover para a esquerda" style={setinha}>{'‹'}</button>
                <button type="button" onClick={() => mover(col.chave, 1)} aria-label="Mover para a direita" style={setinha}>{'›'}</button>
              </>
            )}
          </span>
        )
      })}
      <button
        type="button" onClick={onFechar}
        style={{
          marginLeft: 'auto', border: 'none', background: 'none', color: 'var(--ink-3)',
          fontSize: 12, cursor: 'pointer',
        }}
      >Fechar</button>
    </div>
  )
}

const setinha: React.CSSProperties = {
  border: 'none', background: 'var(--surface)', borderRadius: 5, width: 18, height: 18,
  cursor: 'pointer', color: 'var(--ink-3)', lineHeight: 1, padding: 0,
}

function Legenda({ editavel }: { editavel: boolean }) {
  return (
    <div style={{
      display: 'flex', gap: 18, flexWrap: 'wrap', alignItems: 'center',
      padding: '10px 2px 0', fontSize: 11.5, color: 'var(--ink-3)',
    }}>
      <Amostra cor="var(--danger)" rotulo="Caminho crítico" />
      <Amostra cor="var(--brand)" rotulo="Com folga" />
      <Amostra cor="var(--ink-3)" rotulo="Linha de base" opacidade={0.35} />
      <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <Diamond size={11} style={{ color: 'var(--accent)' }} /> Marco
      </span>
      {editavel && (
        <>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <Link2 size={12} /> Arraste o ponto da barra até outra para ligar
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <Trash2 size={12} /> Clique na seta para remover
          </span>
        </>
      )}
    </div>
  )
}

function Amostra({ cor, rotulo, opacidade = 1 }: { cor: string; rotulo: string; opacidade?: number }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <span style={{ width: 16, height: 7, borderRadius: 2, background: cor, opacity: opacidade }} />
      {rotulo}
    </span>
  )
}
