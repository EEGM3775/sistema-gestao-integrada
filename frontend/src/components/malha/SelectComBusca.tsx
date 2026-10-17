import { useEffect, useId, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import { keepPreviousData, useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { Search, X } from 'lucide-react'
import apiClient from '@/api/apiClient'

/**
 * **Select com busca no servidor** — o cadastro grande escolhido pelo nome (F2).
 *
 * **Por que existe.** O `<select>` montado com "a lista inteira" pedia uma página
 * só: `/api/clientes/` serve no máximo 300 por página (`PAGINA_MAXIMA`), e o
 * cliente nº 301 sumia do formulário **em silêncio** — no demo, a lista parava em
 * "Carla Lima" e não se lançava título para quem vinha depois no alfabeto. Aqui
 * quem filtra é o servidor (`?search=`, o mesmo `BuscaSemAcento` da tela do
 * cadastro, que já sabe a regra do CPF).
 *
 * **Nenhum resultado fica de fora** *(decisão do dono, 15/10/2026)*. A lista
 * rola infinita: chegando ao fim, pede a próxima página, até o último resultado
 * da busca. Se há 21 "Maria Silva" e a pessoa quer a 21ª, rolar a encontra —
 * buscar refina, mas nunca é obrigatório para alcançar alguém.
 *
 * **O escolhido nunca some.** Fechado, o campo mostra o nome do item escolhido —
 * o que a tela já sabe (`rotuloAtual`, ex.: `cliente_nome` da conta) ou, sem
 * isso, o que o detalhe do recurso devolve. Editar uma conta antiga não depende
 * de o cliente dela cair na primeira página.
 *
 * Teclado: setas andam (e puxam a próxima página no fim), Enter escolhe sem
 * enviar o formulário, Esc fecha.
 */

/** Quantos itens cada ida ao servidor traz. É tela, não teto: o servidor corta
 *  pelo `PAGINA_MAXIMA` do `payment/planos.py` de qualquer jeito, e a rolagem
 *  busca o resto. */
const POR_PAGINA = 50
const ESPERA_MS = 250
/** Quanto antes do fim da lista a próxima página já é pedida (px). */
const FOLGA_PX = 60
/** O campo da Malha, para a tela que não passa `style` — sem isto o input saía
 *  cru, com a cara do navegador. */
const BASE: CSSProperties = {
  width: '100%', padding: '8px 11px', fontSize: 13.5, color: 'var(--ink)',
  background: 'var(--surface-2)', border: '1px solid var(--line)',
  borderRadius: 'var(--r-sm)', outline: 'none', fontFamily: 'var(--sans)',
}

interface Pagina<T> { count?: number; next?: string | null; results?: T[] }
interface Lote<T> { itens: T[]; total: number; temMais: boolean }

export interface SelectComBuscaProps<T> {
  /** Rota do recurso, com barra final: `/clientes/`. */
  recurso: string
  idDe: (item: T) => number
  rotuloDe: (item: T) => string
  /** Segunda linha da opção (cidade, CNPJ…), para distinguir homônimos. */
  detalheDe?: (item: T) => string | null | undefined
  valor: number | null | undefined
  /** O nome do escolhido, quando a tela já o tem — evita uma ida ao servidor. */
  rotuloAtual?: string | null
  aoMudar: (id: number | null, item?: T) => void
  ordenacao?: string
  placeholder?: string
  permiteLimpar?: boolean
  disabled?: boolean
  style?: CSSProperties
  'aria-label'?: string
  /** Mensagem da lista vazia sem busca (cadastro sem nenhum item). */
  vazio?: string
}

export function SelectComBusca<T>({
  recurso, idDe, rotuloDe, detalheDe, valor, rotuloAtual, aoMudar, ordenacao,
  placeholder = 'Digite para buscar…', permiteLimpar = false, disabled = false,
  style, vazio = 'Nenhum cadastro ainda.', ...aria
}: SelectComBuscaProps<T>) {
  const idLista = useId()
  const lista = useRef<HTMLUListElement>(null)
  const [aberto, setAberto] = useState(false)
  const [texto, setTexto] = useState('')
  const [termo, setTermo] = useState('')
  const [ativo, setAtivo] = useState(0)
  /** O nome do que foi escolhido nesta tela (antes de o pai devolver `valor`). */
  const [escolhido, setEscolhido] = useState<{ id: number; rotulo: string } | null>(null)

  useEffect(() => {
    const t = setTimeout(() => setTermo(texto.trim()), ESPERA_MS)
    return () => clearTimeout(t)
  }, [texto])

  const busca = useInfiniteQuery({
    queryKey: ['select-com-busca', recurso, termo, ordenacao ?? ''],
    initialPageParam: 1,
    queryFn: async ({ pageParam }): Promise<Lote<T>> => {
      const { data } = await apiClient.get<Pagina<T> | T[]>(recurso, {
        params: {
          search: termo || undefined, page: pageParam, page_size: POR_PAGINA, ordering: ordenacao,
        },
      })
      //: Recurso sem paginação devolve a lista inteira de uma vez: não há "mais".
      if (Array.isArray(data)) return { itens: data, total: data.length, temMais: false }
      const itens = data.results ?? []
      return { itens, total: data.count ?? itens.length, temMais: Boolean(data.next) }
    },
    getNextPageParam: (ultimo, todos) => (ultimo.temMais ? todos.length + 1 : undefined),
    enabled: aberto && !disabled,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = busca

  //: O nome do escolhido: o desta tela, o que o pai sabe, ou o detalhe.
  const rotuloConhecido = valor == null ? null
    : escolhido?.id === valor ? escolhido.rotulo
      : rotuloAtual || null
  const detalhe = useQuery({
    queryKey: ['select-com-busca', recurso, 'detalhe', valor],
    queryFn: async () => rotuloDe((await apiClient.get<T>(`${recurso}${valor}/`)).data),
    enabled: valor != null && !rotuloConhecido,
    staleTime: 60_000,
  })
  const rotuloFechado = valor == null ? ''
    : rotuloConhecido ?? detalhe.data ?? (detalhe.isLoading ? 'Carregando…' : `#${valor}`)

  //: Sem repetidos: se o servidor devolver o mesmo item em duas páginas (ordem
  //: sem desempate), ele aparece uma vez só. O desempate certo é da `ordenacao`.
  const vistos = new Set<number>()
  const itens = (busca.data?.pages.flatMap((p) => p.itens) ?? []).filter((item) => {
    const id = idDe(item)
    if (vistos.has(id)) return false
    vistos.add(id)
    return true
  })
  const total = busca.data?.pages[0]?.total ?? 0

  function puxarMais() {
    if (hasNextPage && !isFetchingNextPage) void fetchNextPage()
  }

  //: Página que não enche a caixa não tem rolagem — e sem rolagem o "fim" nunca
  //: chega. Nesse caso a próxima página é pedida sem esperar o dedo.
  useEffect(() => {
    const ul = lista.current
    if (!aberto || !ul) return
    if (ul.scrollHeight <= ul.clientHeight + FOLGA_PX && hasNextPage && !isFetchingNextPage) {
      void fetchNextPage()
    }
  }, [aberto, itens.length, hasNextPage, isFetchingNextPage, fetchNextPage])

  //: Pelo teclado, a opção ativa fica sempre à vista.
  useEffect(() => {
    if (!aberto) return
    document.getElementById(`${idLista}-${ativo}`)?.scrollIntoView({ block: 'nearest' })
  }, [aberto, ativo, idLista])

  function abrir() {
    if (disabled) return
    setAberto(true)
    setTexto('')
    setTermo('')
    setAtivo(0)
  }

  function fechar() {
    setAberto(false)
    setTexto('')
  }

  function escolher(item: T) {
    const id = idDe(item)
    setEscolhido({ id, rotulo: rotuloDe(item) })
    aoMudar(id, item)
    fechar()
  }

  function teclado(e: KeyboardEvent<HTMLInputElement>) {
    if (!aberto && (e.key === 'ArrowDown' || e.key === 'Enter')) {
      e.preventDefault()
      abrir()
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setAtivo((i) => Math.min(i + 1, Math.max(itens.length - 1, 0)))
      if (ativo >= itens.length - 3) puxarMais()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setAtivo((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      //: Enter escolhe — nunca envia o formulário em volta.
      e.preventDefault()
      if (itens[ativo]) escolher(itens[ativo])
    } else if (e.key === 'Escape') {
      e.preventDefault()
      fechar()
    }
  }

  const idAtivo = aberto && itens[ativo] ? `${idLista}-${ativo}` : undefined
  const totalBR = total.toLocaleString('pt-BR')

  return (
    <div style={{ position: 'relative' }}>
      <input
        type="text"
        role="combobox"
        aria-expanded={aberto}
        aria-controls={idLista}
        aria-autocomplete="list"
        aria-activedescendant={idAtivo}
        aria-label={aria['aria-label']}
        autoComplete="off"
        disabled={disabled}
        value={aberto ? texto : rotuloFechado}
        placeholder={aberto ? (rotuloFechado || placeholder) : placeholder}
        onFocus={abrir}
        onClick={() => { if (!aberto) abrir() }}
        onBlur={fechar}
        onChange={(e) => { setTexto(e.target.value); setAtivo(0); if (!aberto) setAberto(true) }}
        onKeyDown={teclado}
        //: A base vale quando a tela não manda estilo; a lupa reserva a esquerda.
        style={{
          ...BASE, ...style, paddingLeft: 32,
          paddingRight: permiteLimpar && valor != null ? 30 : style?.paddingRight ?? BASE.paddingRight,
        }}
      />
      <Search
        size={14}
        aria-hidden
        style={{
          position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)',
          color: 'var(--ink-3)', pointerEvents: 'none',
        }}
      />
      {permiteLimpar && valor != null && !disabled && (
        <button
          type="button"
          aria-label="Limpar"
          title="Limpar"
          //: `onMouseDown` + `preventDefault`: o clique não tira o foco antes de valer.
          onMouseDown={(e) => { e.preventDefault(); setEscolhido(null); aoMudar(null); fechar() }}
          style={{
            position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
            background: 'none', border: 'none', cursor: 'pointer', padding: 2,
            color: 'var(--ink-3)', display: 'flex',
          }}
        >
          <X size={14} />
        </button>
      )}

      {aberto && (
        <div
          style={{
            position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0, zIndex: 60,
            background: 'var(--surface)', border: '1px solid var(--line)',
            borderRadius: 8, boxShadow: 'var(--shadow-md)', overflow: 'hidden',
          }}
        >
          <ul
            ref={lista}
            id={idLista}
            role="listbox"
            //: A rolagem que importa é a da lista: perto do fim, a próxima página.
            onScroll={(e) => {
              const ul = e.currentTarget
              if (ul.scrollTop + ul.clientHeight >= ul.scrollHeight - FOLGA_PX) puxarMais()
            }}
            //: Rolar com a roda não pode tirar o foco do campo (fecharia a lista).
            onMouseDown={(e) => e.preventDefault()}
            style={{ listStyle: 'none', margin: 0, padding: 4, maxHeight: 280, overflowY: 'auto' }}
          >
            {itens.map((item, i) => {
              const id = idDe(item)
              const segunda = detalheDe?.(item)
              return (
                <li
                  key={id}
                  id={`${idLista}-${i}`}
                  role="option"
                  aria-selected={id === valor}
                  onMouseDown={(e) => { e.preventDefault(); escolher(item) }}
                  onMouseEnter={() => setAtivo(i)}
                  style={{
                    padding: '7px 9px', borderRadius: 6, cursor: 'pointer',
                    background: i === ativo ? 'var(--accent-soft)' : 'transparent',
                    color: 'var(--ink)', fontSize: 13.5, lineHeight: 1.35,
                    fontWeight: id === valor ? 650 : 400,
                  }}
                >
                  {rotuloDe(item)}
                  {segunda && (
                    <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)' }}>{segunda}</span>
                  )}
                </li>
              )
            })}
          </ul>
          <div
            role="status"
            style={{
              padding: '6px 11px', borderTop: itens.length ? '1px solid var(--line-2)' : 'none',
              fontSize: 11.5, color: 'var(--ink-3)',
            }}
          >
            {busca.isError ? 'Não foi possível buscar agora.'
              : busca.isLoading ? 'Buscando…'
                : itens.length === 0 ? (termo ? `Nada encontrado para “${termo}”.` : vazio)
                  : isFetchingNextPage ? `Carregando mais… ${itens.length} de ${totalBR}`
                    : hasNextPage
                      ? `${itens.length} de ${totalBR} — role para ver mais, ou digite para refinar.`
                      : `${totalBR} ${total === 1 ? 'resultado' : 'resultados'}.`}
          </div>
        </div>
      )}
    </div>
  )
}
