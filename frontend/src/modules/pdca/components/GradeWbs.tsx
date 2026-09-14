import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type RefObject } from 'react'
import { ChevronDown, ChevronRight, Diamond, Lock, MoreVertical } from 'lucide-react'
import { maskDate } from '@/utils/dates'
import { ALTURA_CABECALHO, ALTURA_LINHA } from '../medidas'
import { textoDePredecessoras, type LinhaDaArvore } from '../lib'
import { CATALOGO_COLUNAS } from '../colunas'
import { valorExibido, valorParaEdicao } from '../celulas'
import type {
  Atividade, CampoEditavel, ChaveColuna, ColunaGrade, EdicaoCelula, Precedencia,
} from '../types'

const EDITAVEIS = new Set<string>(CATALOGO_COLUNAS.filter(c => c.editavel).map(c => c.chave))

export interface Cursor { linha: number; coluna: number }
export type GestoDeEstrutura = 'indentar' | 'outdentar' | 'subir' | 'descer' | 'inserir' | 'excluir'

interface Props {
  linhas: LinhaDaArvore[]
  janela: { inicio: number; fim: number }
  colunas: ColunaGrade[]
  largura: number
  editavel: boolean
  precedencias: Precedencia[]
  porId: Map<number, Atividade>
  recolhidas: ReadonlySet<number>
  selecionadas: ReadonlySet<number>
  cursor: Cursor | null
  roloRef: RefObject<HTMLDivElement | null>
  onCursor: (cursor: Cursor) => void
  onSelecionar: (indice: number, modo: 'unica' | 'faixa' | 'alternar') => void
  onAlternarNo: (id: number) => void
  onEditar: (atividade: Atividade, campo: CampoEditavel, valor: string) => void
  onColar: (edicoes: EdicaoCelula[]) => void
  onMenu: (atividade: Atividade, ancora: DOMRect) => void
  onGesto: (gesto: GestoDeEstrutura, atividade: Atividade) => void
  onRedimensionar: (chave: ChaveColuna, largura: number) => void
}

export default function GradeWbs({
  linhas, janela, colunas, largura, editavel, precedencias, porId, recolhidas,
  selecionadas, cursor, roloRef, onCursor, onSelecionar, onAlternarNo, onEditar,
  onColar, onMenu, onGesto, onRedimensionar,
}: Props) {
  const [editando, setEditando] = useState('')
  const [emEdicao, setEmEdicao] = useState(false)
  const entradaRef = useRef<HTMLInputElement>(null)

  /** Predecessoras é a única coluna cujo texto não está na atividade: ele nasce
   *  da rede inteira, e remontá-lo por célula desenhada passaria milhares de
   *  vezes pela mesma lista de setas a cada rolagem. */
  const textoPredecessoras = useMemo(() => {
    const mapa = new Map<number, string>()
    if (!colunas.some(c => c.chave === 'predecessoras')) return mapa
    for (const linha of linhas) {
      mapa.set(linha.atividade.atividade_id, textoDePredecessoras(linha.atividade, precedencias, porId))
    }
    return mapa
  }, [linhas, precedencias, porId, colunas])

  useLayoutEffect(() => {
    if (emEdicao) entradaRef.current?.focus()
  }, [emEdicao, cursor])

  /** O cursor puxa a rolagem — quem desce com a seta não pode sair da tela. */
  useEffect(() => {
    const rolo = roloRef.current
    if (!cursor || !rolo) return
    const topo = cursor.linha * ALTURA_LINHA
    const util = rolo.clientHeight - ALTURA_CABECALHO
    if (topo < rolo.scrollTop) rolo.scrollTop = topo
    else if (topo + ALTURA_LINHA > rolo.scrollTop + util) rolo.scrollTop = topo + ALTURA_LINHA - util
  }, [cursor, roloRef])

  /** Por que a recusa carrega motivo: a célula que não aceita edição é a regra
   *  do domínio aparecendo (sintética não tem duração própria, atividade
   *  vinculada vale o orçado). Sem o motivo no `title`, ela parece defeito. */
  const permissaoDaCelula = (a: Atividade, chave: ChaveColuna): { pode: boolean; motivo: string } => {
    if (!EDITAVEIS.has(chave)) return { pode: false, motivo: '' }
    if (!editavel) return { pode: false, motivo: 'O plano vigente não se edita — replaneje para abrir a próxima versão.' }
    if (chave === 'duracao_dias') {
      if (a.tem_filhos) return { pode: false, motivo: 'A sintética é o intervalo das filhas.' }
      if (a.eh_marco) return { pode: false, motivo: 'Marco é um instante: não tem duração.' }
    }
    if (chave === 'predecessoras' && a.tem_filhos) {
      return { pode: false, motivo: 'A precedência liga as folhas — a sintética é o intervalo delas.' }
    }
    if (chave === 'peso_informado' && a.item_orcado) {
      return { pode: false, motivo: 'Vinculada ao orçamento: o peso é o valor orçado do item.' }
    }
    return { pode: true, motivo: '' }
  }

  const iniciarEdicao = (a: Atividade, chave: ChaveColuna) => {
    if (!permissaoDaCelula(a, chave).pode) return
    setEditando(valorParaEdicao(a, chave, textoPredecessoras))
    setEmEdicao(true)
  }

  const confirmar = (a: Atividade, chave: ChaveColuna) => {
    setEmEdicao(false)
    const original = valorParaEdicao(a, chave, textoPredecessoras)
    const valor = editando.trim()
    if (valor === original.trim()) return
    onEditar(a, chave as CampoEditavel, valor)
  }

  const mover = (dLinha: number, dColuna: number) => {
    if (!cursor) return
    let { linha, coluna } = cursor
    if (dColuna) {
      coluna += dColuna
      if (coluna < 0) { coluna = colunas.length - 1; linha -= 1 }
      else if (coluna >= colunas.length) { coluna = 0; linha += 1 }
    }
    onCursor({ linha: Math.max(0, Math.min(linhas.length - 1, linha + dLinha)), coluna })
  }

  const aoTeclar = (e: KeyboardEvent<HTMLDivElement>, a: Atividade, chave: ChaveColuna, temFilhos: boolean) => {
    if (emEdicao) {
      if (e.key === 'Escape') { e.preventDefault(); setEmEdicao(false) }
      else if (e.key === 'Enter') { e.preventDefault(); confirmar(a, chave); mover(1, 0) }
      else if (e.key === 'Tab') { e.preventDefault(); confirmar(a, chave); mover(0, e.shiftKey ? -1 : 1) }
      return
    }
    // Alt + setas é a gramática de estrutura do MS Project, e quem planeja a traz
    // decorada: indentar, promover e reordenar sem tirar a mão do teclado.
    if (e.altKey) {
      const gestos = { ArrowRight: 'indentar', ArrowLeft: 'outdentar', ArrowUp: 'subir', ArrowDown: 'descer' } as const
      const gesto = gestos[e.key as keyof typeof gestos]
      if (gesto) { e.preventDefault(); onGesto(gesto, a); return }
    }
    if (e.key === 'Enter' || e.key === 'F2') { e.preventDefault(); iniciarEdicao(a, chave) }
    else if (e.key === 'Tab') { e.preventDefault(); mover(0, e.shiftKey ? -1 : 1) }
    else if (e.key === 'ArrowDown') { e.preventDefault(); mover(1, 0) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); mover(-1, 0) }
    else if (e.key === 'ArrowRight') { e.preventDefault(); mover(0, 1) }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); mover(0, -1) }
    else if (e.key === 'Insert') { e.preventDefault(); onGesto('inserir', a) }
    else if (e.key === 'Delete' && e.ctrlKey) { e.preventDefault(); onGesto('excluir', a) }
    else if (e.key === ' ' && temFilhos) { e.preventDefault(); onAlternarNo(a.atividade_id) }
    else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && permissaoDaCelula(a, chave).pode) {
      setEditando(e.key)
      setEmEdicao(true)
    }
  }

  /** Colar bloco de planilha. Ancora na célula do cursor, desce pelas linhas e
   *  **pula a célula que aquela linha não aceita** — duração de sintética, peso
   *  de atividade vinculada — em vez de recusar o bloco inteiro: quem cola 300
   *  linhas não quer descobrir na primeira que uma delas era um agrupador. */
  const aoColar = (e: React.ClipboardEvent, indice: number, coluna: number) => {
    const texto = e.clipboardData.getData('text/plain')
    if (!texto.includes('\t') && !texto.includes('\n')) return
    e.preventDefault()
    if (!editavel) return
    const bloco = texto.replace(/\r/g, '').split('\n').filter(l => l !== '').map(l => l.split('\t'))
    const edicoes: EdicaoCelula[] = []
    bloco.forEach((celulas, dl) => {
      const alvo = linhas[indice + dl]
      if (!alvo) return
      celulas.forEach((bruto, dc) => {
        const col = colunas[coluna + dc]
        if (!col || !permissaoDaCelula(alvo.atividade, col.chave).pode) return
        edicoes.push({ atividade: alvo.atividade, campo: col.chave as CampoEditavel, valor: bruto.trim() })
      })
    })
    if (edicoes.length) onColar(edicoes)
  }

  /** Onde a árvore mora. É a coluna do **nome**, e não a primeira da esquerda:
   *  recuar a EAP afundaria o próprio código que dá o nível, e numa WBS de 12
   *  degraus a coluna de 104 px sumiria embaixo do recuo. Sem a coluna de nome
   *  ligada, a árvore cai na primeira que houver. */
  const colunaArvore = Math.max(colunas.findIndex(c => c.chave === 'nome'), 0)

  const visiveis = linhas.slice(janela.inicio, janela.fim + 1)

  return (
    <div style={{ width: largura, flex: `0 0 ${largura}px` }}>
      <Cabecalho colunas={colunas} onRedimensionar={onRedimensionar} />

      <div style={{ height: linhas.length * ALTURA_LINHA, position: 'relative' }}>
        {visiveis.map((linha, i) => {
          const indice = janela.inicio + i
          const a = linha.atividade
          const selecionada = selecionadas.has(a.atividade_id)
          return (
            <div
              key={a.atividade_id}
              onMouseDown={e => onSelecionar(indice, e.shiftKey ? 'faixa' : (e.ctrlKey || e.metaKey) ? 'alternar' : 'unica')}
              style={{
                position: 'absolute', top: indice * ALTURA_LINHA, left: 0, width: '100%',
                height: ALTURA_LINHA, display: 'flex', alignItems: 'stretch',
                background: selecionada ? 'var(--inset)' : 'transparent',
                borderBottom: '1px solid var(--line)',
              }}
            >
              {colunas.map((col, ci) => (
                <Celula
                  key={col.chave}
                  atividade={a} coluna={col} linha={linha}
                  arvore={ci === colunaArvore}
                  foco={cursor?.linha === indice && cursor?.coluna === ci}
                  emEdicao={emEdicao} editando={editando} entradaRef={entradaRef}
                  editavel={editavel}
                  permissao={permissaoDaCelula(a, col.chave)}
                  conteudo={valorExibido(a, col.chave, textoPredecessoras)}
                  recolhida={recolhidas.has(a.atividade_id)}
                  onEditando={setEditando}
                  onCursor={() => onCursor({ linha: indice, coluna: ci })}
                  onIniciar={() => iniciarEdicao(a, col.chave)}
                  onConfirmar={() => confirmar(a, col.chave)}
                  onTeclar={e => aoTeclar(e, a, col.chave, linha.temFilhos)}
                  onColar={e => aoColar(e, indice, ci)}
                  onAlternarNo={() => onAlternarNo(a.atividade_id)}
                  onMenu={ancora => onMenu(a, ancora)}
                />
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// A célula
// ---------------------------------------------------------------------------
//
// Componente próprio, e não JSX embutido no laço, porque ela é desenhada
// (colunas × linhas visíveis) dezenas de vezes por rolagem: manter o corpo aqui
// deixa o laço da grade legível e o custo de cada célula visível em um lugar só.

interface CelulaProps {
  atividade: Atividade
  coluna: ColunaGrade
  linha: LinhaDaArvore
  /** Esta é a célula que desenha o recuo, a seta e o menu da linha. */
  arvore: boolean
  foco: boolean
  emEdicao: boolean
  editando: string
  editavel: boolean
  entradaRef: RefObject<HTMLInputElement | null>
  permissao: { pode: boolean; motivo: string }
  conteudo: { texto: string; esmaecido?: boolean }
  recolhida: boolean
  onEditando: (v: string) => void
  onCursor: () => void
  onIniciar: () => void
  onConfirmar: () => void
  onTeclar: (e: KeyboardEvent<HTMLDivElement>) => void
  onColar: (e: React.ClipboardEvent) => void
  onAlternarNo: () => void
  onMenu: (ancora: DOMRect) => void
}

function Celula({
  atividade, coluna, linha, arvore, foco, emEdicao, editando, editavel, entradaRef,
  permissao, conteudo, recolhida, onEditando, onCursor, onIniciar, onConfirmar,
  onTeclar, onColar, onAlternarNo, onMenu,
}: CelulaProps) {
  const primeira = arvore
  // O recuo satura em 8 degraus: além disso ele come a coluna inteira, e a
  // profundidade continua legível pela seta e pelo código da EAP.
  const recuo = 8 + Math.min(linha.nivel, 8) * 15
  const derivadaVazia = coluna.derivada && !atividade.inicio_cedo

  return (
    <div
      tabIndex={foco ? 0 : -1}
      ref={el => { if (foco && !emEdicao) el?.focus({ preventScroll: true }) }}
      onClick={onCursor}
      onDoubleClick={onIniciar}
      onKeyDown={onTeclar}
      onPaste={onColar}
      title={permissao.motivo || undefined}
      style={{
        width: coluna.largura, flex: `0 0 ${coluna.largura}px`,
        display: 'flex', alignItems: 'center', gap: 5,
        padding: primeira ? `0 4px 0 ${recuo}px` : '0 8px',
        justifyContent: alinhar(coluna.alinhamento),
        fontSize: 12.5, color: 'var(--ink)', outline: 'none',
        fontWeight: linha.temFilhos ? 650 : 400,
        borderRight: '1px solid var(--line)',
        boxShadow: foco ? 'inset 0 0 0 2px var(--accent)' : undefined,
        cursor: permissao.pode ? 'text' : 'default',
        opacity: derivadaVazia ? 0.45 : 1,
      }}
    >
      {primeira && (
        <button
          onClick={e => { e.stopPropagation(); if (linha.temFilhos) onAlternarNo() }}
          aria-label={linha.temFilhos ? (recolhida ? 'Expandir' : 'Recolher') : undefined}
          style={{
            background: 'none', border: 'none', padding: 0, display: 'flex', width: 14,
            color: 'var(--ink-3)', cursor: linha.temFilhos ? 'pointer' : 'default', flex: '0 0 14px',
          }}
        >
          {linha.temFilhos
            ? (recolhida ? <ChevronRight size={13} /> : <ChevronDown size={13} />)
            : atividade.eh_marco ? <Diamond size={11} /> : null}
        </button>
      )}

      {foco && emEdicao ? (
        <input
          ref={entradaRef}
          value={editando}
          onChange={e => onEditando(
            coluna.chave === 'nao_comecar_antes_de' ? maskDate(e.target.value) : e.target.value,
          )}
          onBlur={onConfirmar}
          onKeyDown={onTeclar}
          onClick={e => e.stopPropagation()}
          style={{
            width: '100%', minWidth: 0, border: 'none', outline: 'none',
            background: 'var(--surface)', font: 'inherit', color: 'var(--ink)',
            textAlign: coluna.alinhamento === 'right' ? 'right' : 'left',
          }}
        />
      ) : (
        <span style={{
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0,
          color: conteudo.esmaecido ? 'var(--ink-3)' : undefined,
          fontStyle: conteudo.esmaecido ? 'italic' : undefined,
        }}>
          {conteudo.texto}
        </span>
      )}

      {primeira && !editavel && <Lock size={11} style={{ color: 'var(--ink-3)', flex: '0 0 auto' }} />}
      {primeira && (
        <button
          onClick={e => { e.stopPropagation(); onMenu(e.currentTarget.getBoundingClientRect()) }}
          aria-label="Ações da atividade"
          style={{
            marginLeft: 'auto', background: 'none', border: 'none', padding: 0, display: 'flex',
            color: 'var(--ink-3)', cursor: 'pointer', flex: '0 0 auto',
          }}
        >
          <MoreVertical size={13} />
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// O cabeçalho, com a alça de largura
// ---------------------------------------------------------------------------

function Cabecalho({ colunas, onRedimensionar }: {
  colunas: ColunaGrade[]
  onRedimensionar: (chave: ChaveColuna, largura: number) => void
}) {
  const arrasto = useRef<{ chave: ChaveColuna; x: number; largura: number } | null>(null)

  // Os dois ouvintes ficam na janela, e não na alça: quem arrasta uma coluna
  // estreita passa o ponteiro por fora dela em meio pixel, e o arrasto preso ao
  // elemento morreria no meio do gesto.
  useEffect(() => {
    const mover = (e: PointerEvent) => {
      const atual = arrasto.current
      if (!atual) return
      onRedimensionar(atual.chave, Math.max(atual.largura + (e.clientX - atual.x), 52))
    }
    const soltar = () => { arrasto.current = null }
    window.addEventListener('pointermove', mover)
    window.addEventListener('pointerup', soltar)
    return () => {
      window.removeEventListener('pointermove', mover)
      window.removeEventListener('pointerup', soltar)
    }
  }, [onRedimensionar])

  return (
    <div style={{
      position: 'sticky', top: 0, zIndex: 3, display: 'flex', height: ALTURA_CABECALHO,
      alignItems: 'center', background: 'var(--inset)', borderBottom: '1px solid var(--line)',
      fontSize: 11, fontWeight: 700, letterSpacing: '.04em', textTransform: 'uppercase',
      color: 'var(--ink-3)',
    }}>
      {colunas.map(col => (
        <div
          key={col.chave}
          title={col.rotulo}
          style={{
            width: col.largura, flex: `0 0 ${col.largura}px`, padding: '0 8px', position: 'relative',
            display: 'flex', alignItems: 'center', justifyContent: alinhar(col.alinhamento),
          }}
        >
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {col.curto ?? col.rotulo}
          </span>
          <span
            onPointerDown={e => {
              e.preventDefault()
              arrasto.current = { chave: col.chave, x: e.clientX, largura: col.largura }
            }}
            style={{ position: 'absolute', right: -3, top: 0, bottom: 0, width: 7, cursor: 'col-resize', touchAction: 'none' }}
          />
        </div>
      ))}
    </div>
  )
}

const alinhar = (a: ColunaGrade['alinhamento']) =>
  a === 'right' ? 'flex-end' : a === 'center' ? 'center' : 'flex-start'
