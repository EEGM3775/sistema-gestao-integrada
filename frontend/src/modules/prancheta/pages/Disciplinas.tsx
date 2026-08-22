import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, ChevronDown, Plus, Search, Tag, Trash2, X } from 'lucide-react'
import { Btn, Modal, Spinner } from '@/components/malha'
import { contemSemAcento } from '@/utils/texto'
import { useCriarDisciplina, useDisciplinas, useExcluirDisciplina } from '../hooks'
import type { DisciplinaCatalogo } from '../types'

/**
 * **Chip de disciplina** — a peça visual que se repete em toda a tela.
 *
 * Um chip, três estados (apagado · marcado · só leitura) e sempre a mesma
 * gramática: bolinha da cor + nome. É o que faz o filtro, o seletor do envio e o
 * cartão da prancha parecerem a mesma coisa em vez de três controles diferentes
 * para o mesmo conceito.
 *
 * Marcado, o chip **se pinta da própria cor** em vez de ganhar a moldura do
 * acento: com várias disciplinas juntas, a moldura única faria todas parecerem
 * iguais — e a cor é justamente o que a pessoa lê antes do nome.
 */
export function ChipDisciplina({
  nome, cor, marcado, onClick, tam = 'md',
}: {
  nome: string
  cor: string
  marcado?: boolean
  onClick?: () => void
  tam?: 'sm' | 'md'
}) {
  const pequeno = tam === 'sm'
  const conteudo = (
    <>
      <span
        aria-hidden
        style={{
          width: pequeno ? 10 : 13, height: pequeno ? 10 : 13, borderRadius: 4, flex: 'none',
          background: marcado ? 'transparent' : cor,
          border: marcado ? '2px solid currentColor' : '1px solid rgba(0,0,0,.25)',
        }}
      />
      {nome}
    </>
  )
  const estilo = {
    display: 'inline-flex', alignItems: 'center', gap: pequeno ? 5 : 7,
    minHeight: pequeno ? 30 : 40, padding: pequeno ? '0 9px' : '0 12px',
    borderRadius: 999, fontSize: pequeno ? 11.5 : 13, fontWeight: 700,
    // `color-mix` e não opacidade: sobre o fundo branco do modo sol a opacidade
    // lavaria o texto junto, e é o texto que precisa continuar legível ao sol.
    background: marcado ? `color-mix(in srgb, ${cor} 16%, var(--surface))` : 'var(--surface)',
    border: `2px solid ${marcado ? cor : 'var(--line)'}`,
    color: marcado ? cor : 'var(--ink-2)',
    cursor: onClick ? 'pointer' : 'default',
    whiteSpace: 'nowrap' as const,
  }

  if (!onClick) return <span style={estilo}>{conteudo}</span>
  return (
    <button type="button" onClick={onClick} aria-pressed={!!marcado} style={estilo}>
      {conteudo}
    </button>
  )
}

/**
 * Fileira de leitura — as disciplinas de uma prancha, sem interação.
 *
 * Existe separada do seletor porque o cartão da grade e o cabeçalho do
 * visualizador mostram o mesmo conjunto e **não** o editam; reaproveitar o
 * seletor ali daria alvos de toque que não fazem nada, no lugar onde o toque
 * abre a prancha.
 */
export function DisciplinasDaPrancha({
  itens, limite = 2,
}: {
  itens: { codigo: string; nome: string; cor: string }[]
  limite?: number
}) {
  if (!itens.length) return null
  const mostrados = itens.slice(0, limite)
  const resto = itens.length - mostrados.length
  return (
    <span style={{ display: 'inline-flex', gap: 5, flexWrap: 'wrap', alignItems: 'center' }}>
      {mostrados.map((d) => (
        <ChipDisciplina key={d.codigo} nome={d.nome} cor={d.cor} tam="sm" />
      ))}
      {resto > 0 && (
        <span
          title={itens.slice(limite).map((d) => d.nome).join(' · ')}
          style={{
            display: 'inline-flex', alignItems: 'center', minHeight: 30, padding: '0 8px',
            borderRadius: 999, border: '2px solid var(--line)', background: 'var(--surface)',
            fontSize: 11.5, fontWeight: 700, color: 'var(--ink-3)',
          }}
        >
          +{resto}
        </span>
      )}
    </span>
  )
}

// ---------------------------------------------------------------------------
// O seletor — uma linha, sempre
// ---------------------------------------------------------------------------

/**
 * **A caixa de seleção que substituiu a fileira de chips.**
 *
 * A fileira funcionava com dez disciplinas e quebrava com cem: mesmo com o
 * "mais N", expandir empurrava a grade de pranchas para o fim da página — o
 * controle roubava a tela de quem veio ver desenho. O `+ N` também não é
 * resposta quando o N é 180: ninguém procura numa lista de 180 chips.
 *
 * O seletor resolve os dois de uma vez: **ocupa uma linha, sempre**, e a busca
 * dentro dele é o que torna cem disciplinas navegáveis — digita-se "ele" e sobra
 * uma. A lista rola **dentro** do painel (altura fixa), nunca na página.
 *
 * Não é um `<select>` nativo de propósito: ele não mostra cor, não faz
 * multi-seleção sem Ctrl+clique e no celular abre uma lista cinza do sistema —
 * três coisas que este módulo usa para a pessoa reconhecer a disciplina sem ler.
 */
export function SeletorDisciplinas({
  valor,
  aoMudar,
  modo = 'varios',
  rotulo,
  contagens,
  rotuloVazio = 'Todas',
  compacto = false,
  permitirCriar = true,
}: {
  /** Códigos escolhidos, **principal primeiro** (a ordem de marcação é mantida). */
  valor: string[]
  aoMudar: (codigos: string[]) => void
  /** `unico` = filtro (marcar troca); `varios` = classificação (marcar acumula). */
  modo?: 'unico' | 'varios'
  rotulo?: string
  /** Quantas pranchas cada disciplina tem — some da lista quem tem zero. */
  contagens?: Record<string, number>
  rotuloVazio?: string
  compacto?: boolean
  permitirCriar?: boolean
}) {
  const { data: catalogo, isLoading } = useDisciplinas()
  const [aberto, setAberto] = useState(false)
  const [busca, setBusca] = useState('')
  const [criando, setCriando] = useState(false)
  const caixa = useRef<HTMLDivElement>(null)
  const painel = useRef<HTMLDivElement>(null)
  const [lugar, setLugar] = useState<{ top: number; left: number; width: number } | null>(null)

  const lista = useMemo(() => {
    const todas = catalogo ?? []
    // Com `contagens`, esconde o que não tem prancha: filtrar por uma disciplina
    // vazia dá tela vazia, e oferecer isso é oferecer um beco.
    return contagens ? todas.filter((d) => (contagens[d.codigo] ?? 0) > 0) : todas
  }, [catalogo, contagens])

  const escolhidas = useMemo(
    () => valor.map((c) => lista.find((d) => d.codigo === c)).filter((d): d is DisciplinaCatalogo => !!d),
    [valor, lista],
  )

  const filtradas = useMemo(() => {
    const termo = busca.trim()
    // Sem acento nos dois lados: "instalacao" acha "Instalações", que é o que
    // toda disciplina de fábrica tem (ver `utils/texto.ts`).
    const base = termo ? lista.filter((d) => contemSemAcento(d.nome, termo)) : lista
    // Marcadas no topo: com cem disciplinas, o que já se escolheu não pode estar
    // na posição 80 — e é o que deixa conferir a seleção sem rolar.
    const marcadas = base.filter((d) => valor.includes(d.codigo))
    return [...marcadas, ...base.filter((d) => !valor.includes(d.codigo))]
  }, [lista, busca, valor])

  /**
   * **O painel vai para um portal, e não é preciosismo.**
   *
   * Ele abre dentro de dois containers que rolam — a lista de arquivos do envio
   * (`overflow-y: auto`) e a gaveta de revisões —, e `position: absolute` dentro
   * de um ancestral com `overflow` é **cortado** na borda dele: a lista de
   * disciplinas apareceria pela metade justamente na linha de baixo. No `body`,
   * com coordenada `fixed` medida do gatilho, nada a corta.
   */
  const posicionar = useCallback(() => {
    const r = caixa.current?.getBoundingClientRect()
    if (!r) return
    const largura = Math.max(r.width, 260)
    const alturaEstimada = 360
    // Abre para cima quando não cabe embaixo — no celular deitado, o gatilho da
    // última linha fica a 80 px do fim da tela.
    const paraCima = r.bottom + alturaEstimada > window.innerHeight && r.top > alturaEstimada
    setLugar({
      top: paraCima ? Math.max(8, r.top - alturaEstimada - 6) : r.bottom + 6,
      left: Math.min(Math.max(8, r.left), Math.max(8, window.innerWidth - largura - 8)),
      width: largura,
    })
  }, [])

  useLayoutEffect(() => { if (aberto) posicionar() }, [aberto, posicionar])

  // Fecha ao clicar fora e no Esc; reposiciona ao rolar ou redimensionar. O
  // `true` no scroll é captura: a rolagem que importa é a do container interno,
  // que não borbulha até o `window`.
  useEffect(() => {
    if (!aberto) return
    const fora = (e: MouseEvent) => {
      const alvo = e.target as Node
      if (caixa.current?.contains(alvo) || painel.current?.contains(alvo)) return
      setAberto(false)
    }
    const tecla = (e: KeyboardEvent) => { if (e.key === 'Escape') setAberto(false) }
    document.addEventListener('mousedown', fora)
    document.addEventListener('keydown', tecla)
    window.addEventListener('scroll', posicionar, true)
    window.addEventListener('resize', posicionar)
    return () => {
      document.removeEventListener('mousedown', fora)
      document.removeEventListener('keydown', tecla)
      window.removeEventListener('scroll', posicionar, true)
      window.removeEventListener('resize', posicionar)
    }
  }, [aberto, posicionar])

  const alternar = (codigo: string) => {
    if (modo === 'unico') {
      aoMudar(valor.includes(codigo) ? [] : [codigo])
      setAberto(false)
      setBusca('')
      return
    }
    aoMudar(valor.includes(codigo) ? valor.filter((c) => c !== codigo) : [...valor, codigo])
  }

  const altura = compacto ? 36 : 44

  return (
    <div style={{ display: 'grid', gap: rotulo ? 6 : 0 }}>
      {rotulo && (
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-2)' }}>
          {rotulo}
          {modo === 'varios' && valor.length > 1 && (
            <span style={{ fontWeight: 500, color: 'var(--ink-3)' }}> · a primeira é a principal</span>
          )}
        </span>
      )}

      <div ref={caixa} style={{ position: 'relative' }}>
        {/* O gatilho mostra a seleção, e é ele que garante a linha única: os
            chips escolhidos vivem AQUI dentro, com corte em dois + "N". */}
        <button
          type="button"
          onClick={() => setAberto((a) => !a)}
          aria-expanded={aberto}
          aria-haspopup="listbox"
          disabled={isLoading}
          style={{
            display: 'flex', alignItems: 'center', gap: 8, width: '100%', minHeight: altura,
            padding: '0 10px', cursor: 'pointer', textAlign: 'left',
            borderRadius: 'var(--r-sm)', background: 'var(--surface)',
            border: `2px solid ${aberto ? 'var(--accent-strong)' : 'var(--line)'}`,
            color: 'var(--ink)', overflow: 'hidden',
          }}
        >
          {isLoading ? (
            <Spinner size={14} />
          ) : escolhidas.length ? (
            <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center', minWidth: 0, overflow: 'hidden' }}>
              {escolhidas.slice(0, 2).map((d) => (
                <ChipDisciplina key={d.codigo} nome={d.nome} cor={d.cor} tam="sm" />
              ))}
              {escolhidas.length > 2 && (
                <span
                  title={escolhidas.slice(2).map((d) => d.nome).join(' · ')}
                  style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--ink-3)' }}
                >
                  +{escolhidas.length - 2}
                </span>
              )}
            </span>
          ) : (
            <span style={{ fontSize: compacto ? 12.5 : 13.5, color: 'var(--ink-3)', fontWeight: 600 }}>
              {rotuloVazio}
            </span>
          )}

          <ChevronDown
            size={16}
            style={{
              marginLeft: 'auto', flex: 'none', color: 'var(--ink-3)',
              transform: aberto ? 'rotate(180deg)' : undefined, transition: 'transform .12s',
            }}
          />
        </button>

        {/* Limpar sem abrir o painel — o gesto mais comum depois de filtrar. */}
        {!!escolhidas.length && !aberto && (
          <button
            type="button"
            onClick={() => aoMudar([])}
            aria-label="Limpar disciplinas"
            style={{
              position: 'absolute', right: 30, top: '50%', transform: 'translateY(-50%)',
              width: 26, height: 26, display: 'grid', placeItems: 'center', cursor: 'pointer',
              background: 'transparent', border: 0, color: 'var(--ink-3)',
            }}
          >
            <X size={14} />
          </button>
        )}

        {aberto && lugar && createPortal(
          <div
            ref={painel}
            role="listbox"
            style={{
              position: 'fixed', top: lugar.top, left: lugar.left, width: lugar.width, zIndex: 120,
              display: 'grid', gap: 0, borderRadius: 'var(--r-md)', overflow: 'hidden',
              background: 'var(--surface)', border: '2px solid var(--line)',
              boxShadow: 'var(--shadow-lg)',
            }}
          >
            {/* A busca é o que torna cem disciplinas navegáveis. Só aparece
                quando há o que peneirar — com seis, ela seria ruído. */}
            {lista.length > 8 && (
              <div style={{ position: 'relative', borderBottom: '1px solid var(--line)' }}>
                <Search
                  size={15}
                  style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-3)' }}
                />
                <input
                  autoFocus
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                  placeholder="Buscar disciplina"
                  style={{
                    width: '100%', minHeight: 42, paddingLeft: 32, paddingRight: 10,
                    border: 0, background: 'var(--inset)', color: 'var(--ink)', fontSize: 13.5,
                  }}
                />
              </div>
            )}

            {/* Altura fixa: a lista rola AQUI, e a página não cresce.

                **`overscroll-behavior: contain` é o que separa as duas rolagens.**
                Sem ele a roda encadeia: chegando ao fim da lista o navegador passa
                o resto do gesto para a página atrás, e como o painel é `position:
                fixed` ele fica parado enquanto o fundo desliza — o efeito que se
                relatou na tela de enviar pasta, onde "não dá para mover nem a
                barra da tela nem a da caixa". `contain` corta o encadeamento: com
                o ponteiro dentro, rola a lista e só ela; fora, rola o que estiver
                fora. */}
            <div style={{
              maxHeight: 260, overflowY: 'auto', overscrollBehavior: 'contain',
              padding: 6, display: 'grid', gap: 3,
            }}>
              {!filtradas.length && (
                <span style={{ padding: '12px 10px', fontSize: 12.5, color: 'var(--ink-3)' }}>
                  {busca ? 'Nenhuma disciplina com esse nome.' : 'Nenhuma disciplina ainda.'}
                </span>
              )}
              {filtradas.map((d) => {
                const on = valor.includes(d.codigo)
                return (
                  <button
                    key={d.codigo}
                    type="button"
                    role="option"
                    aria-selected={on}
                    onClick={() => alternar(d.codigo)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 9, minHeight: 40, width: '100%',
                      padding: '0 10px', cursor: 'pointer', textAlign: 'left',
                      borderRadius: 'var(--r-sm)', border: 0,
                      background: on ? `color-mix(in srgb, ${d.cor} 14%, var(--surface))` : 'transparent',
                      color: 'var(--ink)', fontSize: 13.5, fontWeight: on ? 700 : 500,
                    }}
                  >
                    <span
                      aria-hidden
                      style={{
                        width: 14, height: 14, borderRadius: 4, flex: 'none',
                        background: d.cor, border: '1px solid rgba(0,0,0,.25)',
                      }}
                    />
                    <span className="truncate" style={{ flex: 1, minWidth: 0 }}>{d.nome}</span>
                    {contagens && (
                      <span className="num" style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                        {contagens[d.codigo]}
                      </span>
                    )}
                    {on && <Check size={15} style={{ flex: 'none', color: d.cor }} />}
                  </button>
                )
              })}
            </div>

            {permitirCriar && (
              <button
                type="button"
                onClick={() => { setCriando(true); setAberto(false) }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 7, minHeight: 42, padding: '0 12px',
                  cursor: 'pointer', border: 0, borderTop: '1px solid var(--line)',
                  background: 'var(--inset)', color: 'var(--accent-ink)',
                  fontSize: 12.5, fontWeight: 700,
                }}
              >
                <Plus size={14} /> Nova disciplina
              </button>
            )}
          </div>,
          document.body,
        )}
      </div>

      {criando && (
        <NovaDisciplina
          aoFechar={() => setCriando(false)}
          aoCriar={(d) => {
            aoMudar(modo === 'unico' ? [d.codigo] : [...valor, d.codigo])
            setCriando(false)
          }}
        />
      )}
    </div>
  )
}

/**
 * O filtro da grade — seleção única, numa linha, ao lado do botão de gerir.
 *
 * Era uma fileira de chips que quebrava linha, e com centenas de disciplinas ela
 * empurrava as pranchas para o fim da página. Agora é o seletor: **altura fixa**,
 * busca dentro, e a lista rolando no painel em vez de na tela.
 */
export function FiltroDeDisciplina({
  grupos, escolhida, aoEscolher, podeGerir,
}: {
  grupos: { disciplina: string; rotulo: string; cor: string; total: number }[]
  escolhida: string
  aoEscolher: (codigo: string) => void
  podeGerir: boolean
}) {
  const { data: catalogo } = useDisciplinas()
  const [gerindo, setGerindo] = useState(false)
  const contagens = useMemo(
    () => Object.fromEntries(grupos.map((g) => [g.disciplina, g.total])),
    [grupos],
  )

  if (grupos.length < 2 && !podeGerir) return null

  return (
    <>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 220px', maxWidth: 340 }}>
          <SeletorDisciplinas
            valor={escolhida ? [escolhida] : []}
            aoMudar={(codigos) => aoEscolher(codigos[0] ?? '')}
            modo="unico"
            contagens={contagens}
            rotuloVazio={`Todas as disciplinas (${grupos.length})`}
            permitirCriar={false}
          />
        </div>

        {podeGerir && (
          <Btn onClick={() => setGerindo(true)} title="Criar ou apagar disciplinas" style={{ minHeight: 44 }}>
            <Tag size={15} /> <span className="hidden sm:inline">Disciplinas</span>
          </Btn>
        )}
      </div>

      {gerindo && <GerirDisciplinas catalogo={catalogo ?? []} aoFechar={() => setGerindo(false)} />}
    </>
  )
}

/**
 * Escolher **as** disciplinas de algo — o mesmo seletor, em modo múltiplo.
 *
 * Usado por linha de arquivo no envio e pela reclassificação dentro da prancha.
 * Com trinta arquivos na tela, cada linha ocupa **uma** altura fixa: era isso que
 * a fileira de chips não conseguia dar.
 */
export function EscolhaDeDisciplinas({
  valor, aoMudar, rotulo = 'Disciplinas', compacto = false,
}: {
  valor: string[]
  aoMudar: (codigos: string[]) => void
  rotulo?: string
  compacto?: boolean
}) {
  return (
    <SeletorDisciplinas
      valor={valor}
      aoMudar={aoMudar}
      modo="varios"
      rotulo={rotulo || undefined}
      rotuloVazio="Escolher disciplina"
      compacto={compacto}
    />
  )
}

/** Doze matizes bem separados — os mesmos que o servidor deriva para quem não escolhe. */
const PALETA = [
  '#B45309', '#1D4ED8', '#047857', '#A21CAF', '#B91C1C', '#0E7490',
  '#4D7C0F', '#7C2D12', '#6D28D9', '#0F766E', '#9D174D', '#374151',
]

function NovaDisciplina({
  aoFechar, aoCriar,
}: {
  aoFechar: () => void
  aoCriar: (d: DisciplinaCatalogo) => void
}) {
  const criar = useCriarDisciplina()
  const [nome, setNome] = useState('')
  const [cor, setCor] = useState(PALETA[0])
  const [erro, setErro] = useState('')

  const salvar = () => {
    setErro('')
    criar.mutate({ nome: nome.trim(), cor }, {
      onSuccess: aoCriar,
      onError: (e: unknown) => {
        const r = (e as { response?: { data?: Record<string, string[] | string> } })?.response?.data
        const primeiro = r && Object.values(r)[0]
        setErro(
          Array.isArray(primeiro) ? primeiro[0]
            : typeof primeiro === 'string' ? primeiro
            : 'Não foi possível criar. Talvez já exista uma com este nome.',
        )
      },
    })
  }

  return (
    <Modal
      titulo="Nova disciplina"
      onClose={aoFechar}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Cancelar</Btn>
          <Btn variant="primary" disabled={!nome.trim() || criar.isPending} onClick={salvar}>
            {criar.isPending ? <Spinner /> : <Check size={14} />} Criar
          </Btn>
        </div>
      }
    >
      <div style={{ display: 'grid', gap: 14 }}>
        <label style={{ display: 'grid', gap: 5 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-2)' }}>Nome</span>
          <input
            autoFocus
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && nome.trim()) salvar() }}
            placeholder="Impermeabilização"
            maxLength={60}
            style={{
              minHeight: 44, padding: '8px 10px', fontSize: 15, color: 'var(--ink)',
              background: 'var(--surface)', border: '2px solid var(--line)', borderRadius: 'var(--r-sm)',
            }}
          />
          <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
            O código sai do nome — você não precisa escolher um.
          </span>
        </label>

        <div style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-2)' }}>Cor</span>
          <span style={{ fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.5 }}>
            É por ela que se reconhece a disciplina antes de ler o nome — escolha uma que não se
            confunda com as que você já usa.
          </span>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 2 }}>
            {PALETA.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setCor(c)}
                aria-label={`Cor ${c}`}
                aria-pressed={c === cor}
                style={{
                  width: 40, height: 40, borderRadius: 10, cursor: 'pointer', background: c,
                  border: c === cor ? '3px solid var(--ink)' : '1px solid rgba(0,0,0,.25)',
                }}
              />
            ))}
          </div>
        </div>

        {erro && <span style={{ fontSize: 12.5, color: 'var(--danger-ink)' }}>{erro}</span>}
      </div>
    </Modal>
  )
}

/**
 * Gerir o vocabulário: o que dá para apagar, e o que não dá.
 *
 * As 13 embutidas não são apagáveis — são o piso de onde a taxonomia do lote
 * adivinha a pasta, e sumir com "Arquitetura" quebraria a classificação
 * automática de todo acervo organizado. As próprias somem, e **nenhuma prancha
 * vai junto**: o documento guarda o código como texto, então ele volta a se
 * exibir pelo próprio slug até alguém reclassificá-lo.
 */
function GerirDisciplinas({
  catalogo, aoFechar,
}: {
  catalogo: DisciplinaCatalogo[]
  aoFechar: () => void
}) {
  const excluir = useExcluirDisciplina()
  const [criando, setCriando] = useState(false)
  const [busca, setBusca] = useState('')
  const proprias = catalogo.filter((d) => d.disciplina_id && !d.padrao)
  const embutidas = catalogo.filter((d) => !d.disciplina_id || d.padrao)

  const termo = busca.trim()
  const visiveis = termo
    ? proprias.filter((d) => contemSemAcento(d.nome, termo))
    : proprias

  return (
    <Modal
      titulo="Disciplinas do acervo"
      onClose={aoFechar}
      largura={560}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between', width: '100%' }}>
          <Btn variant="primary" onClick={() => setCriando(true)}><Plus size={14} /> Nova disciplina</Btn>
          <Btn onClick={aoFechar}>Fechar</Btn>
        </div>
      }
    >
      <div style={{ display: 'grid', gap: 16 }}>
        <section style={{ display: 'grid', gap: 8 }}>
          <strong style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
            Suas disciplinas {proprias.length > 0 && <span style={{ color: 'var(--ink-3)', fontWeight: 500 }}>({proprias.length})</span>}
          </strong>

          {/* Busca também aqui: com centenas, rolar a lista para achar a que se
              quer apagar é o mesmo problema do filtro, no modal. */}
          {proprias.length > 8 && (
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar nas suas disciplinas"
              style={{
                minHeight: 40, padding: '8px 10px', fontSize: 13, color: 'var(--ink)',
                background: 'var(--inset)', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
              }}
            />
          )}

          {!proprias.length && (
            <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
              Nenhuma ainda — crie uma quando as de fábrica não descreverem o seu projeto.
            </span>
          )}

          {/* Lista dentro do modal, que por sua vez rola: mesma regra de dono do
              gesto que o seletor (ver o painel acima). */}
          <div style={{
            display: 'grid', gap: 6, maxHeight: 300, overflowY: 'auto',
            overscrollBehavior: 'contain',
          }}>
            {visiveis.map((d) => (
              <div key={d.codigo} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 'var(--r-sm)', border: '1px solid var(--line)' }}>
                <span style={{ width: 16, height: 16, borderRadius: 5, background: d.cor, flex: 'none', border: '1px solid rgba(0,0,0,.25)' }} />
                <strong style={{ fontSize: 13.5, color: 'var(--ink)' }}>{d.nome}</strong>
                <code style={{ fontSize: 11, color: 'var(--ink-3)' }}>{d.codigo}</code>
                <Btn
                  tam="sm"
                  style={{ marginLeft: 'auto' }}
                  disabled={excluir.isPending}
                  onClick={() => excluir.mutate(d.disciplina_id as number)}
                >
                  <Trash2 size={13} /> Apagar
                </Btn>
              </div>
            ))}
          </div>

          <span style={{ fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.5 }}>
            Apagar uma disciplina <strong>não apaga prancha nenhuma</strong> — as que estavam nela
            passam a se exibir pelo próprio código até alguém reclassificá-las.
          </span>
        </section>

        <section style={{ display: 'grid', gap: 8 }}>
          <strong style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>De fábrica</strong>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {embutidas.map((d) => (
              <span
                key={d.codigo}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 10px',
                  borderRadius: 999, border: '1px solid var(--line)', fontSize: 12, color: 'var(--ink-2)',
                }}
              >
                <span style={{ width: 12, height: 12, borderRadius: 4, background: d.cor, border: '1px solid rgba(0,0,0,.25)' }} />
                {d.nome}
              </span>
            ))}
          </div>
          <span style={{ fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.5 }}>
            Não são apagáveis: é delas que a plataforma adivinha a disciplina pelo nome da pasta
            quando você envia um acervo inteiro.
          </span>
        </section>
      </div>

      {criando && (
        <NovaDisciplina aoFechar={() => setCriando(false)} aoCriar={() => setCriando(false)} />
      )}
    </Modal>
  )
}
