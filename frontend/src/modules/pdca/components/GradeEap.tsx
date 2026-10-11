import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, ChevronDown, ChevronRight, Diamond, GripVertical, Pin, Plus, Trash2,
} from 'lucide-react'
import { dateToBR, maxCalendarioISO, minCalendarioISO } from '@/utils/dates'
import { paraData, type LinhaDaArvore } from '../arvore'
import type { FuncionarioCurto } from '../api/montagemApi'
import { diasUteisEntre } from '../importacao'
import type { Montagem } from '../montagem'
import { emPercentual, fatiasDaObra, pesoDe } from '../pesos'
import {
  ALTURA_CABECALHO_GRADE, ALTURA_LINHA, COLUNAS, LARGURA_ACOES, LARGURA_ALCA, larguraDaGrade,
  type ColunaId,
} from '../grade'
import type { AvancoDoCronograma, Atividade, LocalObra, Restricao } from '../types'

type Onde = 'antes' | 'depois' | 'dentro'

interface Props {
  linhas: LinhaDaArvore[]
  avanco: AvancoDoCronograma
  colunas: ColunaId[]
  selecionada: number | null
  editavel: boolean
  montagem: Montagem
  locais: LocalObra[]
  funcionarios: FuncionarioCurto[] | null
  restricoesPorAtividade: Map<number, Restricao[]>
  aoSelecionar: (id: number) => void
  aoAlternar: (id: number) => void
  aoColar: (texto: string) => void
  /** Pede a exclusão — a página confirma num diálogo e exclui. */
  aoExcluir: (lista: Atividade[]) => void
}

/** A planilha da EAP, no molde do MS Project: setas andam, Enter/F2 ou digitar
 *  edita, Enter grava e desce, Tab recua a linha, Shift+Tab avança, Insert cria
 *  logo abaixo, Alt+↑↓ muda a ordem, arrastar a alça leva a linha (com o que
 *  está dentro) para onde soltar. **Várias de vez**: Ctrl+clique marca e
 *  desmarca, Shift+clique e Shift+↑↓ marcam o intervalo, Ctrl+A marca todas,
 *  Esc desmarca — e Delete, Tab, Shift+Tab e arrastar valem para as marcadas.
 *  Em plano vigente **número é texto** — quem manda é o `editavel` do servidor. */
export function GradeEap(props: Props) {
  const {
    linhas, avanco, colunas, selecionada, editavel, montagem, locais, funcionarios,
    restricoesPorAtividade, aoSelecionar, aoAlternar, aoColar, aoExcluir,
  } = props
  const visiveis = useMemo(() => COLUNAS.filter((c) => colunas.includes(c.id)), [colunas])
  const [ativa, setAtiva] = useState<{ linha: number; coluna: ColunaId } | null>(null)
  const [editando, setEditando] = useState(false)
  const [rascunho, setRascunho] = useState('')
  const [arrastando, setArrastando] = useState<number | null>(null)
  const [alvo, setAlvo] = useState<{ id: number; onde: Onde } | null>(null)
  const [editarAoSurgir, setEditarAoSurgir] = useState<number | null>(null)
  /** De onde o Shift estende o intervalo. */
  const [ancora, setAncora] = useState<number | null>(null)
  const grade = useRef<HTMLDivElement>(null)
  const marcadas = useMemo(() => new Set(montagem.marcadas), [montagem.marcadas])
  const fatias = useMemo(() => fatiasDaObra(avanco, linhas.map((l) => l.atividade)), [avanco, linhas])

  // A seleção que veio de fora (Gantt, paleta, Inspetor) move o cursor da grade.
  useEffect(() => {
    if (selecionada == null) return
    const i = linhas.findIndex((l) => l.atividade.atividade_id === selecionada)
    if (i >= 0 && ativa?.linha !== i) setAtiva((a) => ({ linha: i, coluna: a?.coluna ?? 'nome' }))
  }, [selecionada, linhas]) // eslint-disable-line react-hooks/exhaustive-deps

  // A linha recém-criada abre já com o nome em edição.
  useEffect(() => {
    if (editarAoSurgir == null) return
    const i = linhas.findIndex((l) => l.atividade.atividade_id === editarAoSurgir)
    if (i < 0) return
    setAtiva({ linha: i, coluna: 'nome' })
    setRascunho(linhas[i].atividade.nome)
    setEditando(true)
    setEditarAoSurgir(null)
  }, [linhas, editarAoSurgir])

  const atual = ativa ? linhas[ativa.linha]?.atividade : undefined

  function podeEditar(l: LinhaDaArvore, col: ColunaId): boolean {
    if (!editavel) return false
    const a = l.atividade
    switch (col) {
      case 'nome': case 'predecessoras': case 'local': return true
      case 'duracao': case 'inicio': return !l.temFilhos
      case 'responsavel': return funcionarios != null
      case 'peso': return !l.temFilhos && a.peso_origem !== 'orcado'
      default: return false
    }
  }

  function valorParaEditar(a: Atividade, col: ColunaId): string {
    switch (col) {
      case 'nome': return a.nome
      case 'duracao': return a.eh_marco ? '0' : String(a.duracao_dias ?? '')
      case 'predecessoras': return montagem.textoDasPredecessoras(a)
      case 'inicio': return a.nao_comecar_antes_de ?? a.inicio_cedo ?? ''
      case 'local': return a.local != null ? String(a.local) : ''
      case 'responsavel': return a.responsavel != null ? String(a.responsavel) : ''
      case 'peso': return a.peso_informado ?? ''
      default: return ''
    }
  }

  async function gravar(a: Atividade, col: ColunaId, valor: string) {
    const v = valor.trim()
    switch (col) {
      case 'nome':
        if (v && v !== a.nome) await montagem.salvar(a, { nome: v }, 'renomear')
        break
      case 'duracao': {
        const n = Math.round(Number(v.replace(',', '.')))
        if (!Number.isFinite(n) || n < 0 || v === '') break
        if (n === 0 && !a.eh_marco) await montagem.salvar(a, { eh_marco: true, duracao_dias: null }, 'virar marco')
        else if (n > 0 && a.eh_marco) await montagem.salvar(a, { eh_marco: false, duracao_dias: n }, 'duração')
        else if (n > 0 && n !== a.duracao_dias) await montagem.salvar(a, { duracao_dias: n }, 'duração')
        break
      }
      case 'predecessoras':
        if (v !== montagem.textoDasPredecessoras(a)) await montagem.definirPredecessoras(a, v)
        break
      case 'inicio': {
        const novo = v || null
        if (novo !== (a.nao_comecar_antes_de ?? null) && !(novo === a.inicio_cedo && !a.nao_comecar_antes_de)) {
          await montagem.salvar(a, { nao_comecar_antes_de: novo }, 'data de início')
        }
        break
      }
      case 'local':
        if ((v ? Number(v) : null) !== a.local) await montagem.salvar(a, { local: v ? Number(v) : null }, 'local')
        break
      case 'responsavel':
        if ((v ? Number(v) : null) !== a.responsavel) {
          await montagem.salvar(a, { responsavel: v ? Number(v) : null }, 'responsável')
        }
        break
      case 'peso':
        if (v !== (a.peso_informado ?? '')) {
          await montagem.salvar(a, { peso_informado: v ? v.replace(',', '.') : null }, 'peso')
        }
        break
    }
  }

  /** Anda o cursor. Sem Shift, desmarca o lote; com Shift, marca da âncora até aqui. */
  function irPara(linha: number, coluna: ColunaId, estender = false) {
    const i = Math.max(0, Math.min(linhas.length - 1, linha))
    if (estender) marcarIntervalo(ancora ?? ativa?.linha ?? i, i)
    else { montagem.limparMarcas(); setAncora(i) }
    setAtiva({ linha: i, coluna })
    const a = linhas[i]?.atividade
    if (a) aoSelecionar(a.atividade_id)
  }

  function marcarIntervalo(de: number, ate: number) {
    if (ancora == null) setAncora(de)
    const [x, y] = de <= ate ? [de, ate] : [ate, de]
    montagem.marcar(linhas.slice(x, y + 1).map((l) => l.atividade.atividade_id))
  }

  /** O que a ação de teclado alcança: as marcadas, ou a linha do cursor. */
  function alvoDaAcao(): Atividade[] {
    if (montagem.linhasMarcadas.length > 1) return montagem.linhasMarcadas
    return atual ? [atual] : []
  }

  function clicarNaLinha(e: React.MouseEvent, indice: number, coluna: ColunaId) {
    const id = linhas[indice].atividade.atividade_id
    if (e.shiftKey) {
      marcarIntervalo(ancora ?? ativa?.linha ?? indice, indice)
    } else if (e.ctrlKey || e.metaKey) {
      const base = montagem.marcadas.length ? montagem.marcadas : (atual ? [atual.atividade_id] : [])
      montagem.marcar(base.includes(id) ? base.filter((x) => x !== id) : [...base, id])
      setAncora(indice)
    } else {
      montagem.limparMarcas()
      setAncora(indice)
    }
    setAtiva({ linha: indice, coluna })
    aoSelecionar(id)
  }

  function colunaVizinha(col: ColunaId, delta: number): ColunaId {
    const i = visiveis.findIndex((c) => c.id === col)
    return visiveis[Math.max(0, Math.min(visiveis.length - 1, i + delta))]?.id ?? col
  }

  function abrirEdicao(inicial?: string) {
    if (!ativa || !atual) return
    const l = linhas[ativa.linha]
    if (!podeEditar(l, ativa.coluna)) return
    setRascunho(inicial ?? valorParaEditar(atual, ativa.coluna))
    setEditando(true)
  }

  /** Fecha a célula em edição. O foco volta à grade **na hora** e só quando o
   *  fechamento veio do teclado: devolvê-lo num quadro seguinte fechava o
   *  editor que a próxima tecla tinha acabado de abrir, e devolvê-lo no blur
   *  roubava o clique que a pessoa deu no Inspetor. */
  function fecharEdicao(gravando: boolean, mover?: { linha: number; coluna: number }, focar = false) {
    if (!ativa || !atual) { setEditando(false); return }
    const col = ativa.coluna
    const a = atual
    const valor = rascunho
    setEditando(false)
    if (gravando) void gravar(a, col, valor)
    if (mover) irPara(ativa.linha + mover.linha, colunaVizinha(col, mover.coluna))
    if (focar) grade.current?.focus({ preventScroll: true })
  }

  async function inserirAbaixo(dentro = false) {
    if (!editavel) return
    const nova = !atual
      ? await montagem.inserir({ pai: null })
      : dentro
        ? (atual.eh_marco ? undefined : await montagem.inserir({ pai: atual }))
        : await montagem.inserir({
          pai: atual.pai != null ? linhas.find((l) => l.atividade.atividade_id === atual.pai)?.atividade ?? null : null,
          depoisDe: atual,
        })
    if (nova) {
      if (dentro && atual) {
        // Abre o pai para a filha aparecer.
        const l = linhas.find((x) => x.atividade.atividade_id === atual.atividade_id)
        if (l && l.temFilhos && !l.aberta) aoAlternar(atual.atividade_id)
      }
      aoSelecionar(nova.atividade_id)
      setEditarAoSurgir(nova.atividade_id)
    }
  }

  function aoTeclar(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.target !== grade.current) return
    if (editando) {
      // A tecla que chegou antes de o campo pegar o foco ainda é do rascunho.
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault()
        setRascunho((r) => r + e.key)
      }
      return
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault(); void montagem.desfazer(); return
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
      e.preventDefault(); montagem.marcar(linhas.map((x) => x.atividade.atividade_id)); return
    }
    if (e.key === 'Escape' && montagem.marcadas.length) {
      e.preventDefault(); montagem.limparMarcas(); return
    }
    if (!ativa) {
      if (['ArrowDown', 'ArrowUp', 'Enter'].includes(e.key) && linhas.length) { e.preventDefault(); irPara(0, 'nome') }
      return
    }
    const l = linhas[ativa.linha]
    const a = l?.atividade
    if (!a) return

    if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault()
      if (editavel) void montagem.deslocar(a, e.key === 'ArrowUp' ? -1 : 1)
      return
    }
    switch (e.key) {
      case 'ArrowDown': e.preventDefault(); irPara(ativa.linha + 1, ativa.coluna, e.shiftKey); return
      case 'ArrowUp': e.preventDefault(); irPara(ativa.linha - 1, ativa.coluna, e.shiftKey); return
      case 'ArrowLeft':
        e.preventDefault()
        if (ativa.coluna === visiveis[0]?.id && l.temFilhos && l.aberta) aoAlternar(a.atividade_id)
        else setAtiva({ ...ativa, coluna: colunaVizinha(ativa.coluna, -1) })
        return
      case 'ArrowRight': e.preventDefault(); setAtiva({ ...ativa, coluna: colunaVizinha(ativa.coluna, 1) }); return
      case 'Home': e.preventDefault(); irPara(0, ativa.coluna); return
      case 'End': e.preventDefault(); irPara(linhas.length - 1, ativa.coluna); return
      case 'F2': e.preventDefault(); abrirEdicao(); return
      case 'Enter':
        e.preventDefault()
        if (e.shiftKey) void inserirAbaixo()
        else if (e.ctrlKey || e.metaKey) void inserirAbaixo(true)
        else abrirEdicao()
        return
      case 'Insert': e.preventDefault(); void inserirAbaixo(); return
      case 'Tab':
        e.preventDefault()
        if (editavel) void (e.shiftKey ? montagem.avancarVarias(alvoDaAcao()) : montagem.recuarVarias(alvoDaAcao()))
        return
      case 'Delete':
        e.preventDefault()
        if (editavel) aoExcluir(alvoDaAcao())
        return
      case ' ':
        if (l.temFilhos) { e.preventDefault(); aoAlternar(a.atividade_id) }
        return
    }
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const tipoTexto = ['nome', 'duracao', 'predecessoras', 'peso'].includes(ativa.coluna)
      if (tipoTexto && podeEditar(l, ativa.coluna)) { e.preventDefault(); abrirEdicao(e.key) }
    }
  }

  function aoColarNaGrade(e: React.ClipboardEvent<HTMLDivElement>) {
    if (editando || !editavel) return
    const texto = e.clipboardData.getData('text')
    if (!texto) return
    e.preventDefault()
    if (/[\n\t]/.test(texto.trim()) || !ativa || !atual) { aoColar(texto); return }
    // Um valor só cai na célula, como numa planilha.
    if (podeEditar(linhas[ativa.linha], ativa.coluna)) void gravar(atual, ativa.coluna, texto)
  }

  function zonaDe(e: React.DragEvent<HTMLDivElement>, alvoA: Atividade): Onde {
    const caixa = e.currentTarget.getBoundingClientRect()
    const y = (e.clientY - caixa.top) / caixa.height
    if (y < 0.28) return 'antes'
    if (y > 0.72 || alvoA.eh_marco) return 'depois'
    return 'dentro'
  }

  async function inserirNoFim() {
    const ultimaRaiz = [...linhas].reverse().find((l) => l.atividade.pai == null)?.atividade ?? null
    const nova = await montagem.inserir({ pai: null, depoisDe: ultimaRaiz })
    if (nova) { aoSelecionar(nova.atividade_id); setEditarAoSurgir(nova.atividade_id) }
  }

  const largura = larguraDaGrade(colunas)

  return (
    <div
      ref={grade}
      tabIndex={0}
      role="grid"
      aria-label="Estrutura do plano"
      onKeyDown={aoTeclar}
      onPaste={aoColarNaGrade}
      style={{ width: largura, flexShrink: 0, position: 'sticky', left: 0, zIndex: 3, outline: 'none' }}
    >
      <div
        role="row"
        style={{
          display: 'flex', alignItems: 'center', height: ALTURA_CABECALHO_GRADE,
          position: 'sticky', top: 0, zIndex: 4,
          background: 'var(--surface-2)', borderBottom: '1px solid var(--line)',
          borderRight: '1px solid var(--line)',
        }}
      >
        <span style={{ width: LARGURA_ALCA }} />
        {visiveis.map((c) => (
          <div
            key={c.id}
            role="columnheader"
            style={{
              width: c.largura, flexShrink: 0, padding: '0 8px', textAlign: c.direita ? 'right' : 'left',
              fontSize: 9.5, letterSpacing: '0.1em', textTransform: 'uppercase',
              color: 'var(--ink-3)', fontWeight: 700,
            }}
          >
            {c.rotulo}
          </div>
        ))}
        <span style={{ width: LARGURA_ACOES }} />
      </div>

      {linhas.map((l, indice) => {
        const a = l.atividade
        const selecionadaAqui = a.atividade_id === selecionada || marcadas.has(a.atividade_id)
        const executado = avanco.por_atividade[String(a.atividade_id)]?.avanco
        const restricoes = restricoesPorAtividade.get(a.atividade_id) ?? []
        const ehAlvo = alvo?.id === a.atividade_id && arrastando !== a.atividade_id
        return (
          <div
            key={a.atividade_id}
            role="row"
            aria-selected={selecionadaAqui}
            onDragOver={(e) => {
              if (arrastando == null) return
              e.preventDefault()
              const onde = zonaDe(e, a)
              if (alvo?.id !== a.atividade_id || alvo.onde !== onde) setAlvo({ id: a.atividade_id, onde })
            }}
            onDragLeave={() => { if (alvo?.id === a.atividade_id) setAlvo(null) }}
            onDrop={(e) => {
              e.preventDefault()
              const arrastada = linhas.find((x) => x.atividade.atividade_id === arrastando)?.atividade
              // Arrastar uma das marcadas leva o lote inteiro.
              const lote = arrastada && marcadas.has(arrastada.atividade_id) && montagem.linhasMarcadas.length > 1
                ? montagem.linhasMarcadas
                : arrastada ? [arrastada] : []
              if (lote.length && alvo) void montagem.soltar(lote, a, alvo.onde)
              setArrastando(null); setAlvo(null)
            }}
            style={{
              display: 'flex', alignItems: 'center', height: ALTURA_LINHA,
              background: ehAlvo && alvo?.onde === 'dentro'
                ? 'var(--accent-soft)'
                : selecionadaAqui ? 'var(--accent-soft)' : 'var(--surface)',
              borderBottom: '1px solid var(--line-2)', borderRight: '1px solid var(--line)',
              boxShadow: ehAlvo && alvo?.onde === 'antes'
                ? 'inset 0 2px 0 var(--accent)'
                : ehAlvo && alvo?.onde === 'depois' ? 'inset 0 -2px 0 var(--accent)' : undefined,
              opacity: arrastando === a.atividade_id
                || (arrastando != null && marcadas.has(arrastando) && marcadas.has(a.atividade_id)) ? 0.45 : 1,
            }}
          >
            <span
              draggable={editavel}
              onDragStart={(e) => {
                e.dataTransfer.effectAllowed = 'move'
                e.dataTransfer.setData('text/plain', String(a.atividade_id))
                setArrastando(a.atividade_id)
              }}
              onDragEnd={() => { setArrastando(null); setAlvo(null) }}
              title={editavel ? 'Arraste para mover (solte no meio de uma linha para pôr dentro dela)' : undefined}
              style={{
                width: LARGURA_ALCA, display: 'flex', justifyContent: 'center', flexShrink: 0,
                color: 'var(--ink-3)', cursor: editavel ? 'grab' : 'default', opacity: editavel ? 0.7 : 0,
              }}
            >
              <GripVertical size={12} />
            </span>

            {visiveis.map((c) => {
              const ehAtiva = ativa?.linha === indice && ativa.coluna === c.id
              const emEdicao = ehAtiva && editando
              const editavelAqui = podeEditar(l, c.id)
              return (
                <div
                  key={c.id}
                  role="gridcell"
                  aria-selected={ehAtiva}
                  onMouseDown={(e) => {
                    if (emEdicao) return
                    // O foco vai para a grade agora, e não pelo padrão do navegador:
                    // a primeira tecla depois do clique já tem de chegar nela.
                    e.preventDefault()
                    if (editando) fecharEdicao(true)
                    clicarNaLinha(e, indice, c.id)
                    grade.current?.focus({ preventScroll: true })
                  }}
                  onDoubleClick={() => { setAtiva({ linha: indice, coluna: c.id }); if (editavelAqui) { setRascunho(valorParaEditar(a, c.id)); setEditando(true) } }}
                  style={{
                    width: c.largura, flexShrink: 0, height: '100%', display: 'flex', alignItems: 'center',
                    justifyContent: c.direita ? 'flex-end' : 'flex-start', minWidth: 0,
                    padding: c.id === 'nome' ? `0 6px 0 ${4 + l.nivel * 13}px` : '0 8px',
                    outline: ehAtiva && !emEdicao ? '2px solid var(--accent)' : 'none', outlineOffset: -2,
                    cursor: editavelAqui ? 'cell' : 'default',
                  }}
                >
                  {emEdicao ? (
                    <Editor
                      coluna={c.id}
                      valor={rascunho}
                      aoMudar={setRascunho}
                      locais={locais}
                      funcionarios={funcionarios ?? []}
                      aoFechar={fecharEdicao}
                      aoEscolher={(v) => { setEditando(false); void gravar(a, c.id, v); grade.current?.focus({ preventScroll: true }) }}
                    />
                  ) : (
                    <Celula
                      coluna={c.id}
                      linha={l}
                      executado={executado}
                      peso={pesoDe(avanco, a.atividade_id)}
                      fatia={fatias.get(a.atividade_id) ?? null}
                      restricoes={restricoes}
                      montagem={montagem}
                      locais={locais}
                      aoAlternar={aoAlternar}
                    />
                  )}
                </div>
              )
            })}

            <div style={{ width: LARGURA_ACOES, display: 'flex', justifyContent: 'center', gap: 2, flexShrink: 0 }}>
              {editavel && (
                <>
                  {!a.eh_marco && (
                    <BotaoDeLinha
                      titulo="Adicionar atividade dentro desta (Ctrl+Enter)"
                      desabilitado={montagem.ocupado}
                      aoClicar={async () => {
                        const nova = await montagem.inserir({ pai: a })
                        if (nova) {
                          if (l.temFilhos && !l.aberta) aoAlternar(a.atividade_id)
                          aoSelecionar(nova.atividade_id)
                          setEditarAoSurgir(nova.atividade_id)
                        }
                      }}
                    >
                      <Plus size={12} />
                    </BotaoDeLinha>
                  )}
                  <BotaoDeLinha
                    titulo="Excluir, com o que estiver dentro (Delete)"
                    desabilitado={montagem.ocupado}
                    aoClicar={() => aoExcluir(marcadas.has(a.atividade_id) && montagem.linhasMarcadas.length > 1 ? montagem.linhasMarcadas : [a])}
                  >
                    <Trash2 size={12} />
                  </BotaoDeLinha>
                </>
              )}
            </div>
          </div>
        )
      })}

      {editavel && (
        <button
          type="button"
          onClick={() => { void inserirNoFim() }}
          disabled={montagem.ocupado}
          style={{
            display: 'flex', alignItems: 'center', gap: 6, width: '100%', height: ALTURA_LINHA,
            padding: `0 0 0 ${LARGURA_ALCA + 8}px`, background: 'var(--surface)', border: 'none',
            borderBottom: '1px dashed var(--line-2)', borderRight: '1px solid var(--line)',
            color: 'var(--ink-3)', fontSize: 12, cursor: 'pointer', textAlign: 'left',
          }}
        >
          <Plus size={12} /> Nova linha no fim (ou Insert sobre uma linha)
        </button>
      )}
    </div>
  )
}

function Celula(
  { coluna, linha, executado, peso, fatia, restricoes, montagem, locais, aoAlternar }: {
    coluna: ColunaId
    linha: LinhaDaArvore
    executado: number | null | undefined
    /** O peso efetivo (o da folha, ou a soma das filhas na etapa). */
    peso: number | null
    /** A parcela na obra, já repartida para as raízes fecharem 100%. */
    fatia: number | null
    restricoes: Restricao[]
    montagem: Montagem
    locais: LocalObra[]
    aoAlternar: (id: number) => void
  },
) {
  const a = linha.atividade
  const mono = {
    fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums', fontSize: 11.5,
    color: 'var(--ink-2)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
  } as const
  switch (coluna) {
    case 'codigo':
      return <span style={{ ...mono, fontSize: 11, color: 'var(--ink-3)' }}>{a.codigo}</span>
    case 'nome':
      return (
        <span style={{ display: 'flex', alignItems: 'center', gap: 4, minWidth: 0, flex: 1 }}>
          {linha.temFilhos ? (
            <button
              type="button"
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => { e.stopPropagation(); aoAlternar(a.atividade_id) }}
              aria-label={linha.aberta ? 'Recolher' : 'Expandir'}
              style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--ink-3)', display: 'flex', padding: 0, flexShrink: 0 }}
            >
              {linha.aberta ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
          ) : <span style={{ width: 12, flexShrink: 0 }} />}
          {a.eh_marco && <Diamond size={10} style={{ color: 'var(--info-ink)', flexShrink: 0 }} fill="currentColor" />}
          <span
            title={a.nome}
            style={{
              fontSize: 12.5, fontWeight: linha.temFilhos ? 700 : 450,
              color: a.critica ? 'var(--danger-ink)' : 'var(--ink)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, minWidth: 0,
            }}
          >
            {a.nome}
          </span>
          {restricoes.length > 0 && (
            <span
              title={restricoes.map((r) => `${r.tipo_rotulo}: ${r.descricao}${r.prazo ? ` (até ${dateToBR(r.prazo)})` : ''}`).join('\n')}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 2, color: 'var(--accent-ink)', fontSize: 10, flexShrink: 0 }}
            >
              <AlertTriangle size={11} />{restricoes.length}
            </span>
          )}
          {executado != null && executado > 0 && (
            <span style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--good-ink)', flexShrink: 0 }}>
              {Math.round(executado)}%
            </span>
          )}
        </span>
      )
    case 'duracao':
      if (linha.temFilhos) return <span style={{ ...mono, color: 'var(--ink-3)' }}>{diasDoIntervalo(a)}</span>
      return <span style={mono}>{a.eh_marco ? '◆' : `${a.duracao_dias}d`}</span>
    case 'predecessoras':
      return <span style={mono} title={montagem.textoDasPredecessoras(a)}>{montagem.textoDasPredecessoras(a)}</span>
    case 'inicio':
      return (
        <span style={{ ...mono, display: 'inline-flex', alignItems: 'center', gap: 3 }}>
          {a.nao_comecar_antes_de && (
            <span title={`Não começa antes de ${dateToBR(a.nao_comecar_antes_de)}`} style={{ display: 'flex', color: 'var(--info-ink)' }}>
              <Pin size={10} />
            </span>
          )}
          {dataCurta(a.inicio_cedo)}
        </span>
      )
    case 'termino':
      return <span style={mono}>{dataCurta(a.termino_cedo)}</span>
    case 'folga':
      return (
        <span style={{ ...mono, color: a.folga_total === 0 ? 'var(--danger-ink)' : 'var(--ink-2)' }}>
          {a.folga_total == null ? '—' : `${a.folga_total}d`}
        </span>
      )
    case 'local':
      return <span style={{ ...mono, fontFamily: 'inherit', fontSize: 12 }}>{a.local_rotulo || (a.local ? locais.find((x) => x.local_id === a.local)?.nome : '') || ''}</span>
    case 'responsavel':
      return <span style={{ ...mono, fontFamily: 'inherit', fontSize: 12 }}>{a.responsavel_nome ?? ''}</span>
    case 'peso': {
      // O número e a parcela da obra: 5 de 60 é 8,3% — é a parcela que muda o
      // avanço físico quando o campo aponta. Na etapa, a soma das filhas.
      const dica = [
        a.peso_origem === 'orcado' ? 'Vem do orçamento (item ligado)' : linha.temFilhos ? 'Soma das filhas' : null,
        fatia != null ? `${emPercentual(fatia)} do avanço físico da obra` : null,
      ].filter(Boolean).join(' · ')
      return (
        <span style={{ ...mono, color: linha.temFilhos ? 'var(--ink-3)' : mono.color }} title={dica || undefined}>
          {peso == null ? '' : peso.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}
          {fatia != null && <span style={{ fontSize: 9.5, color: 'var(--ink-3)' }}> {emPercentual(fatia)}</span>}
        </span>
      )
    }
  }
}

/** `dd/mm/aa` — a coluna é estreita, e o ano inteiro cortava a data. */
function dataCurta(iso: string | null): string {
  if (!iso) return '—'
  const br = dateToBR(iso)
  return `${br.slice(0, 6)}${br.slice(8, 10)}`
}

/** A agrupadora não tem duração própria: mostra o intervalo dos filhos, em
 *  dias de segunda a sexta (o calendário de verdade está nas folhas). */
function diasDoIntervalo(a: Atividade): string {
  const i = paraData(a.inicio_cedo)
  const t = paraData(a.termino_cedo)
  if (!i || !t) return '—'
  return `${diasUteisEntre(i, t)}d`
}

function Editor(
  { coluna, valor, aoMudar, locais, funcionarios, aoFechar, aoEscolher }: {
    coluna: ColunaId
    valor: string
    aoMudar: (v: string) => void
    locais: LocalObra[]
    funcionarios: FuncionarioCurto[]
    aoFechar: (gravando: boolean, mover?: { linha: number; coluna: number }, focar?: boolean) => void
    aoEscolher: (v: string) => void
  },
) {
  const campoTexto = useRef<HTMLInputElement>(null)
  const campoLista = useRef<HTMLSelectElement>(null)
  // Foco antes da pintura: quem digita rápido não pode perder a segunda tecla.
  useLayoutEffect(() => {
    campoLista.current?.focus()
    const el = campoTexto.current
    if (!el) return
    el.focus()
    if (el.type === 'text') {
      try { el.setSelectionRange(el.value.length, el.value.length) } catch { /* campo sem seleção */ }
    }
  }, [])
  const estilo = {
    width: '100%', fontSize: 12, padding: '1px 4px', background: 'var(--surface)', color: 'var(--ink)',
    border: '1px solid var(--accent)', borderRadius: 3, outline: 'none', minWidth: 0,
  } as const
  const teclas = (e: React.KeyboardEvent) => {
    e.stopPropagation()
    if (e.key === 'Enter') { e.preventDefault(); aoFechar(true, { linha: 1, coluna: 0 }, true) }
    if (e.key === 'Tab') { e.preventDefault(); aoFechar(true, { linha: 0, coluna: e.shiftKey ? -1 : 1 }, true) }
    if (e.key === 'Escape') { e.preventDefault(); aoFechar(false, undefined, true) }
  }

  if (coluna === 'local' || coluna === 'responsavel') {
    return (
      <select
        ref={campoLista}
        value={valor}
        onChange={(e) => aoEscolher(e.target.value)}
        onBlur={() => aoFechar(false)}
        onKeyDown={teclas}
        style={estilo}
      >
        <option value="">—</option>
        {coluna === 'local'
          ? locais.map((l) => (
            <option key={l.local_id} value={l.local_id}>
              {'  '.repeat(Math.max(0, l.profundidade - 1))}{l.nome}
            </option>
          ))
          : funcionarios.map((f) => (
            <option key={f.funcionario_id} value={f.funcionario_id}>{f.nome_completo}</option>
          ))}
      </select>
    )
  }
  if (coluna === 'inicio') {
    return (
      <input
        ref={campoTexto}
        type="date"
        min={minCalendarioISO}
        max={maxCalendarioISO}
        value={valor}
        onChange={(e) => aoMudar(e.target.value)}
        onBlur={() => aoFechar(true)}
        onKeyDown={teclas}
        style={estilo}
      />
    )
  }
  return (
    <input
      ref={campoTexto}
      type="text"
      inputMode={coluna === 'duracao' || coluna === 'peso' ? 'decimal' : undefined}
      value={valor}
      placeholder={coluna === 'predecessoras' ? '1.2; 1.3SS+2' : undefined}
      onChange={(e) => aoMudar(e.target.value)}
      onBlur={() => aoFechar(true)}
      onKeyDown={teclas}
      style={{ ...estilo, textAlign: coluna === 'duracao' || coluna === 'peso' ? 'right' : 'left' }}
    />
  )
}

function BotaoDeLinha(
  { titulo, desabilitado, aoClicar, children }:
  { titulo: string; desabilitado: boolean; aoClicar: () => void; children: React.ReactNode },
) {
  return (
    <button
      type="button"
      title={titulo}
      aria-label={titulo}
      disabled={desabilitado}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => { e.stopPropagation(); aoClicar() }}
      style={{
        background: 'transparent', border: 'none', padding: 3, display: 'flex',
        cursor: desabilitado ? 'not-allowed' : 'pointer', color: 'var(--ink-3)',
      }}
    >
      {children}
    </button>
  )
}
