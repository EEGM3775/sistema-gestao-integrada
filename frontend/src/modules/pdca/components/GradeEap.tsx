import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, Diamond } from 'lucide-react'
import { dateToBR } from '@/utils/dates'
import type { LinhaDaArvore } from '../arvore'
import type { AvancoDoCronograma, Atividade } from '../types'

export const ALTURA_LINHA = 28
export const LARGURA_GRADE = 468

interface Props {
  linhas: LinhaDaArvore[]
  avanco: AvancoDoCronograma
  selecionada: number | null
  editavel: boolean
  salvando: boolean
  aoSelecionar: (id: number) => void
  aoAlternar: (id: number) => void
  aoSalvar: (id: number, corpo: Partial<Atividade>) => void
}

/** A planilha da EAP. Em rascunho se digita; em plano vigente **número é
 *  texto** — `input` desabilitado tem borda e cursor, convida a clicar e não
 *  aceita nada. Quem manda é o `editavel` que o servidor devolve. */
export function GradeEap(
  { linhas, avanco, selecionada, editavel, salvando, aoSelecionar, aoAlternar, aoSalvar }: Props,
) {
  return (
    <div style={{ width: LARGURA_GRADE, flexShrink: 0, position: 'sticky', left: 0, zIndex: 3 }}>
      <div
        style={{
          display: 'flex', alignItems: 'center', height: 40,
          position: 'sticky', top: 0, zIndex: 4,
          background: 'var(--surface-2)', borderBottom: '1px solid var(--line)',
          borderRight: '1px solid var(--line)',
        }}
      >
        <Cabecalho largura={92} texto="Código" />
        <Cabecalho largura={196} texto="Atividade" />
        <Cabecalho largura={44} texto="Dur." alinhar="right" />
        <Cabecalho largura={68} texto="Início" alinhar="right" />
        <Cabecalho largura={68} texto="Término" alinhar="right" />
      </div>

      {linhas.map(({ atividade, nivel, temFilhos, aberta }) => {
        const ativa = atividade.atividade_id === selecionada
        const executado = avanco.por_atividade[String(atividade.atividade_id)]?.avanco
        return (
          <div
            key={atividade.atividade_id}
            onClick={() => aoSelecionar(atividade.atividade_id)}
            style={{
              display: 'flex', alignItems: 'center', height: ALTURA_LINHA,
              background: ativa ? 'var(--accent-soft)' : 'var(--surface)',
              borderBottom: '1px solid var(--line-2)',
              borderRight: '1px solid var(--line)',
              cursor: 'pointer',
            }}
          >
            <div style={{ width: 92, paddingLeft: 8 + nivel * 11, display: 'flex', alignItems: 'center', gap: 3, minWidth: 0 }}>
              {temFilhos ? (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); aoAlternar(atividade.atividade_id) }}
                  aria-label={aberta ? 'Recolher' : 'Expandir'}
                  style={{
                    background: 'transparent', border: 'none', cursor: 'pointer',
                    color: 'var(--ink-3)', display: 'flex', padding: 0, flexShrink: 0,
                  }}
                >
                  {aberta ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                </button>
              ) : (
                <span style={{ width: 12, flexShrink: 0 }} />
              )}
              <span
                style={{
                  fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-3)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}
              >
                {atividade.codigo}
              </span>
            </div>

            <div style={{ width: 196, paddingRight: 8, minWidth: 0, display: 'flex', alignItems: 'center', gap: 5 }}>
              {atividade.eh_marco && (
                <Diamond size={10} style={{ color: 'var(--info-ink)', flexShrink: 0 }} fill="currentColor" />
              )}
              <CampoTexto
                valor={atividade.nome}
                editavel={editavel}
                salvando={salvando}
                negrito={temFilhos}
                critica={atividade.critica}
                aoConfirmar={(v) => aoSalvar(atividade.atividade_id, { nome: v })}
              />
              {executado != null && executado > 0 && (
                <span
                  style={{
                    fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--good-ink)',
                    flexShrink: 0, fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {Math.round(executado)}%
                </span>
              )}
            </div>

            <CelulaNumero
              largura={44}
              valor={atividade.eh_marco ? null : atividade.duracao_dias}
              editavel={editavel && !atividade.eh_marco && !temFilhos}
              salvando={salvando}
              aoConfirmar={(n) => aoSalvar(atividade.atividade_id, { duracao_dias: n })}
            />
            <CelulaData largura={68} iso={atividade.inicio_cedo} />
            <CelulaData largura={68} iso={atividade.termino_cedo} />
          </div>
        )
      })}
    </div>
  )
}

function Cabecalho(
  { largura, texto, alinhar = 'left' }:
  { largura: number; texto: string; alinhar?: 'left' | 'right' },
) {
  return (
    <div
      style={{
        width: largura, paddingLeft: alinhar === 'left' ? 8 : 0, paddingRight: alinhar === 'right' ? 8 : 0,
        textAlign: alinhar, fontSize: 9.5, letterSpacing: '0.1em', textTransform: 'uppercase',
        color: 'var(--ink-3)', fontWeight: 700,
      }}
    >
      {texto}
    </div>
  )
}

function CampoTexto(
  { valor, editavel, salvando, negrito, critica, aoConfirmar }:
  {
    valor: string; editavel: boolean; salvando: boolean
    negrito: boolean; critica: boolean; aoConfirmar: (v: string) => void
  },
) {
  const [editando, setEditando] = useState(false)
  const [rascunho, setRascunho] = useState(valor)
  const campo = useRef<HTMLInputElement>(null)

  useEffect(() => { if (!editando) setRascunho(valor) }, [valor, editando])
  useEffect(() => { if (editando) campo.current?.select() }, [editando])

  const estilo = {
    fontSize: 12.5,
    color: critica ? 'var(--danger-ink)' : 'var(--ink)',
    fontWeight: negrito ? 700 : 450,
  } as const

  if (!editavel || !editando) {
    return (
      <span
        onDoubleClick={() => editavel && setEditando(true)}
        title={editavel ? 'Toque duas vezes para renomear' : valor}
        style={{
          ...estilo, flex: 1, minWidth: 0,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}
      >
        {valor}
      </span>
    )
  }

  function confirmar() {
    setEditando(false)
    const limpo = rascunho.trim()
    if (limpo && limpo !== valor) aoConfirmar(limpo)
    else setRascunho(valor)
  }

  return (
    <input
      ref={campo}
      value={rascunho}
      disabled={salvando}
      onChange={(e) => setRascunho(e.target.value)}
      onBlur={confirmar}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === 'Enter') confirmar()
        if (e.key === 'Escape') { setRascunho(valor); setEditando(false) }
      }}
      style={{
        ...estilo, flex: 1, minWidth: 0, background: 'var(--surface)',
        border: '1px solid var(--accent)', borderRadius: 3, padding: '1px 4px', outline: 'none',
      }}
    />
  )
}

function CelulaNumero(
  { largura, valor, editavel, salvando, aoConfirmar }:
  {
    largura: number; valor: number | null; editavel: boolean
    salvando: boolean; aoConfirmar: (n: number) => void
  },
) {
  const [editando, setEditando] = useState(false)
  const [rascunho, setRascunho] = useState(String(valor ?? ''))

  useEffect(() => { if (!editando) setRascunho(String(valor ?? '')) }, [valor, editando])

  const base = {
    width: largura, paddingRight: 8, textAlign: 'right',
    fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
    fontSize: 11.5, color: 'var(--ink-2)',
  } as const

  if (!editavel || !editando) {
    return (
      <span
        onDoubleClick={() => editavel && setEditando(true)}
        style={{ ...base, cursor: editavel ? 'text' : 'default' }}
      >
        {valor == null ? '—' : valor}
      </span>
    )
  }

  function confirmar() {
    setEditando(false)
    const n = Number(rascunho.replace(',', '.'))
    if (Number.isFinite(n) && n >= 0 && n !== valor) aoConfirmar(Math.round(n))
    else setRascunho(String(valor ?? ''))
  }

  return (
    <input
      autoFocus
      inputMode="numeric"
      value={rascunho}
      disabled={salvando}
      onChange={(e) => setRascunho(e.target.value)}
      onBlur={confirmar}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === 'Enter') confirmar()
        if (e.key === 'Escape') { setRascunho(String(valor ?? '')); setEditando(false) }
      }}
      style={{
        ...base, background: 'var(--surface)', border: '1px solid var(--accent)',
        borderRadius: 3, padding: '1px 4px', outline: 'none',
      }}
    />
  )
}

function CelulaData({ largura, iso }: { largura: number; iso: string | null }) {
  return (
    <span
      title={iso ? undefined : 'O plano ainda não foi calculado'}
      style={{
        width: largura, paddingRight: 8, textAlign: 'right',
        fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
        fontSize: 11, color: iso ? 'var(--ink-2)' : 'var(--ink-3)',
        overflow: 'hidden', whiteSpace: 'nowrap',
      }}
    >
      {iso ? dateToBR(iso).slice(0, 10) : '—'}
    </span>
  )
}
