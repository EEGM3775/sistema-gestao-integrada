import { useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import {
  AlertTriangle, Check, ChevronLeft, ChevronRight, Database, PackageSearch, Plus, Search,
  Sparkles, X,
} from 'lucide-react'
import {
  Aviso, BotaoAnalitica, Btn, CAPS, Field, inp, LegendaLista, Loading, MarcaCatalogo,
  Modal, mono, Pill, Select, Spinner,
} from '../ui'
import { brl, FONTE_ROTULO, num } from '../lib'
import * as api from '../api/orcamentoApi'
import { orcKeys } from '../api/queryKeys'
import { useBasesResumo, useComposicaoReferencia } from '../hooks'
import SeletorDeBase from './SeletorDeBase'
import type { CatalogoItem, InsumoReferencia } from '../types'

type Origem = 'base' | 'catalogo' | 'novo'

/** A cesta, **ao lado** da lista.
 *
 *  Antes o rodapé só dizia "5 item(ns) marcado(s)": um número sem rosto. Quem
 *  marca ao longo de várias páginas e buscas perde a conta do que já pegou, e
 *  tirar um errado exigia achá-lo de novo na lista — depois de trocar de
 *  filtro, uma caçada. Fica na lateral, e não embaixo, para continuar visível
 *  enquanto se rola a lista: uma cesta que sai de vista não serve de conferência.
 *
 *  Só **código e nome**: é o que identifica o item. Preço e unidade já estão na
 *  linha da lista, e repeti-los aqui só encolheria o nome.
 */
function CestaMarcados({ referencias, catalogo, onTirarReferencia, onTirarCatalogo, onLimpar }: {
  referencias: InsumoReferencia[]
  catalogo: CatalogoItem[]
  onTirarReferencia: (id: number) => void
  onTirarCatalogo: (id: number) => void
  onLimpar: () => void
}) {
  const total = referencias.length + catalogo.length
  return (
    <aside style={{
      // Constante nas duas dimensões. `flex: 0 0 246px` sozinho não segura: item
      // flex nasce com `min-width: auto`, e aí conteúdo largo (código comprido,
      // descrição sem espaço) empurra a caixa e come a área da lista. `minWidth`
      // e `maxWidth` explícitos tiram essa possibilidade — a cesta tem o mesmo
      // tamanho vazia ou com cinquenta itens.
      flex: '0 0 246px', width: 246, minWidth: 0, maxWidth: 246,
      display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden',
      border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', background: 'var(--inset)',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '7px 9px',
        borderBottom: '1px solid var(--line)',
      }}>
        <span style={{ ...CAPS, fontSize: 9 }}>Marcados ({total})</span>
        {total > 0 && (
          <button
            onClick={onLimpar}
            style={{
              marginLeft: 'auto', border: 'none', background: 'none', cursor: 'pointer',
              color: 'var(--ink-3)', fontSize: 11, fontWeight: 650, textDecoration: 'underline',
            }}
          >limpar</button>
        )}
      </div>

      {total === 0 ? (
        <p style={{
          padding: '14px 10px', fontSize: 11.5, color: 'var(--ink-3)', margin: 0,
          lineHeight: 1.5, overflowWrap: 'anywhere',
        }}>
          Nada marcado ainda. Clique numa linha da lista para trazer o item para cá.
        </p>
      ) : (
        <div style={{
          flex: 1, minHeight: 0, overflowY: 'auto', overscrollBehavior: 'contain',
          scrollbarGutter: 'stable', padding: 6, display: 'flex', flexDirection: 'column', gap: 4,
        }} className="orc-grade">
          {referencias.map(r => (
            <LinhaCesta key={`ref-${r.referencia_id}`} codigo={r.codigo} nome={r.descricao}
              onTirar={() => onTirarReferencia(r.referencia_id)} />
          ))}
          {catalogo.map(i => (
            <LinhaCesta key={`cat-${i.item_id}`} codigo={i.codigo_interno} nome={i.descricao} doCatalogo
              onTirar={() => onTirarCatalogo(i.item_id)} />
          ))}
        </div>
      )}
    </aside>
  )
}

function LinhaCesta({ codigo, nome, doCatalogo, onTirar }: {
  codigo: string; nome: string; doCatalogo?: boolean; onTirar: () => void
}) {
  return (
    <span
      title={`${codigo} — ${nome}`}
      style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '4px 4px 4px 7px',
        minWidth: 0, maxWidth: '100%', overflow: 'hidden',
        borderRadius: 'var(--r-sm)', background: 'var(--surface)', border: '1px solid var(--line-2)',
      }}
    >
      {/* O código também tem teto: um `PMSP-01.02.003` longo não pode espremer o
          nome até sumir, nem alargar a cesta. */}
      <span style={{
        ...mono, fontSize: 10.5, flex: '0 1 auto', maxWidth: 78,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        color: doCatalogo ? 'var(--net-ink)' : 'var(--ink-3)',
      }}>{codigo}</span>
      {/* `title` também no nome, e não só na linha: a descrição da SINAPI passa
          de 130 caracteres e o que se vê aqui é sempre um pedaço. */}
      <span title={nome} style={{
        flex: 1, minWidth: 0, fontSize: 11.5, color: 'var(--ink-2)',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'help',
      }}>{nome}</span>
      <button
        onClick={onTirar}
        title="Desmarcar"
        aria-label={`Desmarcar ${codigo}`}
        style={{
          flex: 'none', border: 'none', background: 'none', cursor: 'pointer', padding: 2,
          display: 'flex', color: 'var(--ink-3)', borderRadius: 999,
        }}
      ><X size={12} /></button>
    </span>
  )
}

export interface Escolha { itemCatalogoId: number; descricao: string }

/** As três origens que todo software de orçamento oferece no "inserir item":
 *  a base oficial, o catálogo da própria empresa e a criação de um item novo. */
export default function InserirItemModal({ onFechar, onInserir, inserindo, baseDoOrcamento }: {
  onFechar: () => void
  onInserir: (escolhas: Escolha[]) => Promise<void> | void
  inserindo: boolean
  /** A publicação **do orçamento** — que não é a mesma coisa que a publicação
   *  navegada aqui, e é a diferença que fazia a linha nascer zerada sem aviso.
   *  Ver o aviso montado abaixo. */
  baseDoOrcamento: number | null
}) {
  const [origem, setOrigem] = useState<Origem>('base')
  const { data: bases } = useBasesResumo()
  const [baseId, setBaseId] = useState<number | ''>('')
  const [busca, setBusca] = useState('')
  const [tipo, setTipo] = useState<'' | 'insumo' | 'composicao'>('')
  // A base oficial vem numerada por código, e código da SINAPI não tem relação
  // com assunto: procurar "aterro" pelo código devolve os aterros espalhados no
  // meio da lista, entre coisas que nada têm a ver. Quem percorre catálogo
  // procura por nome.
  const [ordem, setOrdem] = useState<'codigo' | 'descricao'>('codigo')
  const [marcados, setMarcados] = useState<Map<number, InsumoReferencia>>(new Map())
  const [marcadosCatalogo, setMarcadosCatalogo] = useState<Map<number, CatalogoItem>>(new Map())
  const [espiando, setEspiando] = useState<number | null>(null)
  const [erro, setErro] = useState('')

  // Abre na publicação **do orçamento**, não na mais recente do banco: é dela
  // que sai o preço da linha. Abrir em outra era oferecer o catálogo certo com
  // o preço errado — o item entrava a zero porque o código não existia na base
  // do orçamento, e nada na tela dizia por quê. Cai na primeira da lista só
  // quando o orçamento não tem base (e aí o aviso âmbar explica o zero).
  useEffect(() => {
    if (baseId !== '' || !bases || bases.length === 0) return
    const doOrcamento = bases.find(b => b.base_id === baseDoOrcamento)
    setBaseId(doOrcamento?.base_id ?? bases[0].base_id)
  }, [bases, baseId, baseDoOrcamento])

  // 100 é o teto do servidor (`PAGINA_MAXIMA["orcamento"]` em planos.py), então
  // "a lista toda" não cabe numa requisição: 12,5 mil linhas viriam em 126. O que
  // dá para oferecer é o controle — quantos por vez e ir e voltar de página —
  // sem obrigar ninguém a saber o código de cor para achar o que quer.
  const POR_PAGINA = [25, 50, 100]
  const [porPagina, setPorPagina] = useState(50)
  const [pagina, setPagina] = useState(1)
  const listaRef = useRef<HTMLDivElement>(null)

  // Filtro que muda invalida a página em que se estava: manter `pagina=7` depois
  // de digitar uma busca de 3 resultados devolveria uma lista vazia.
  useEffect(() => { setPagina(1) }, [baseId, busca, tipo, porPagina, ordem])

  const paramsRef = useMemo(
    () => ({
      base: baseId || undefined, search: busca || undefined, tipo: tipo || undefined,
      // O desempate por `codigo` não é detalhe: descrição não é única — a SINAPI
      // publica dezenas de "CONSTRUÇÃO DE BASE E SUB-BASE..." que só diferem no
      // fim do texto. Sem critério estável, duas páginas do mesmo resultado
      // podem repetir uma linha e engolir outra, porque o banco não garante
      // ordem entre empates.
      ordering: ordem === 'descricao' ? 'descricao,codigo' : 'codigo',
      page_size: porPagina, page: pagina,
    }),
    [baseId, busca, tipo, ordem, porPagina, pagina],
  )
  const referencias = useQuery({
    queryKey: orcKeys.referencias.list(paramsRef),
    queryFn: () => api.referencias.listar(paramsRef),
    enabled: origem === 'base' && baseId !== '',
    placeholderData: keepPreviousData,
  })
  const total = referencias.data?.count ?? 0
  const totalPaginas = Math.max(1, Math.ceil(total / porPagina))

  const irPara = (n: number) => {
    setPagina(Math.min(Math.max(1, n), totalPaginas))
    // Sem isto a página nova começa na altura de rolagem da anterior, e parece
    // que nada aconteceu.
    listaRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }
  const catalogo = useQuery({
    queryKey: orcKeys.catalogo(busca),
    queryFn: () => api.buscarNoCatalogo(busca),
    enabled: origem === 'catalogo',
  })
  const composicao = useComposicaoReferencia(espiando ?? undefined)

  const [novo, setNovo] = useState({ codigo_interno: '', descricao: '', unidade: '', categoria: '', tipo: 'material' })

  const totalMarcado = marcados.size + marcadosCatalogo.size

  async function confirmar() {
    setErro('')
    try {
      const escolhas: Escolha[] = []
      if (marcados.size) {
        // `adotados` é a contagem; os ids vêm em `itens` — e com a descrição já
        // do catálogo, então não há pareamento por índice para sair errado.
        const resultado = await api.adotarLote([...marcados.keys()])
        for (const item of resultado.itens ?? []) {
          escolhas.push({ itemCatalogoId: item.item_id, descricao: item.descricao })
        }
        // D110 — o que não conferiu não foi adotado, e portanto não vai virar
        // linha. Sair daqui em silêncio faria o orçamentista marcar cinco itens,
        // ver quatro na planilha e não saber do quinto; a marca do quinto é o
        // aviso, não a ausência dele.
        const divergentes = resultado.divergentes ?? []
        if (divergentes.length) {
          setErro(
            `${divergentes.length} item(ns) não foram adotados: o código já existe no seu `
            + 'catálogo descrevendo outro insumo ('
            + divergentes.map(d => `${d.codigo} — "${d.descricao_catalogo}" × "${d.descricao_publicacao}"`).join('; ')
            + '). Confira em Bases & bancos antes de inserir.',
          )
          if (!escolhas.length && !marcadosCatalogo.size) return
        }
      }
      for (const item of marcadosCatalogo.values()) {
        escolhas.push({ itemCatalogoId: item.item_id, descricao: item.descricao })
      }
      if (!escolhas.length) { setErro('Marque ao menos um item.'); return }
      await onInserir(escolhas)
    } catch {
      setErro('Não foi possível inserir. Verifique se você tem permissão de adoção no catálogo.')
    }
  }

  async function criarEInserir() {
    setErro('')
    if (!novo.descricao.trim() || !novo.unidade.trim()) { setErro('Descrição e unidade são obrigatórias.'); return }
    try {
      const criado = await api.criarItemNoCatalogo({
        codigo_interno: novo.codigo_interno.trim() || novo.descricao.trim().slice(0, 40).toUpperCase().replace(/\s+/g, '-'),
        descricao: novo.descricao.trim(),
        unidade: novo.unidade.trim(),
        categoria: novo.categoria.trim(),
        tipo: novo.tipo,
      })
      await onInserir([{ itemCatalogoId: criado.item_id, descricao: criado.descricao }])
    } catch {
      setErro('Não foi possível criar o item. Código interno duplicado ou permissão `cadastro.item.edit` ausente.')
    }
  }

  const abas: { chave: Origem; rotulo: string; icone: React.ReactNode }[] = [
    { chave: 'base', rotulo: 'Base de preço', icone: <Database size={13} /> },
    { chave: 'catalogo', rotulo: 'Catálogo da empresa', icone: <PackageSearch size={13} /> },
    { chave: 'novo', rotulo: 'Criar novo', icone: <Plus size={13} /> },
  ]

  return (
    <Modal
      titulo="Inserir item na planilha"
      onClose={onFechar}
      // 880 apertava: a lista tem 6 colunas e a cesta ocupa 246 fixos. Em
      // 1240 a descrição da composição — que passa de 130 caracteres — cabe
      // muito mais antes das reticências. O `maxWidth` do Modal continua
      // convivendo com `width: 100%`, então em tela estreita ele encolhe.
      largura={1240}
      rodape={
        <>
          <span style={{ marginRight: 'auto', fontSize: 12, color: 'var(--ink-3)' }}>
            {origem === 'novo'
              ? 'O item novo entra no catálogo da empresa e fica disponível para o SCM comprar e o SIL estocar.'
              : `${totalMarcado} item(ns) marcado(s) — a quantidade se digita direto na grade depois.`}
          </span>
          <Btn onClick={onFechar}>Cancelar</Btn>
          {origem === 'novo'
            ? <Btn variant="primary" onClick={criarEInserir} disabled={inserindo}>Criar e inserir</Btn>
            : <Btn variant="primary" onClick={confirmar} disabled={inserindo || totalMarcado === 0}>
                <Check size={14} />Inserir {totalMarcado > 0 ? `(${totalMarcado})` : ''}
              </Btn>}
        </>
      }
    >
      <div style={{ display: 'flex', gap: 3, marginBottom: 14, borderBottom: '1px solid var(--line)' }}>
        {abas.map(a => (
          <button
            key={a.chave}
            onClick={() => setOrigem(a.chave)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, border: 'none', background: 'none',
              padding: '8px 13px', fontSize: 13, fontWeight: 650, cursor: 'pointer',
              color: origem === a.chave ? 'var(--ink)' : 'var(--ink-3)',
              borderBottom: `2px solid ${origem === a.chave ? 'var(--accent)' : 'transparent'}`,
              marginBottom: -1,
            }}
          >{a.icone}{a.rotulo}</button>
        ))}
      </div>

      {erro && <Aviso tom="danger">{erro}</Aviso>}

      {origem === 'base' && (
        <>
          {!bases || bases.length === 0 ? (
            <Aviso tom="amber">
              <Database size={15} style={{ flex: 'none', marginTop: 1 }} />
              Nenhuma base de preço importada ainda. Enquanto não houver SINAPI, ORSE ou um banco
              próprio, use o catálogo da empresa ou crie o item na terceira aba.
            </Aviso>
          ) : (
            <>
              {/* **Duas "bases" diferentes, e só uma estava à vista.** A caixa
                  ao lado escolhe onde PROCURAR o item; o preço que a linha
                  recebe vem da publicação DO ORÇAMENTO, definida lá atrás na
                  criação — onde a primeira opção é "Sem base — preço digitado à
                  mão". Quem não reparou inseria tudo a custo zero e só
                  descobria na grade, sem nada na tela ligando uma coisa à
                  outra. O aviso não muda a regra de preço (a data-base do
                  orçamento é que manda, e misturar publicações quebraria isso):
                  ele só para de esconder a consequência. */}
              {baseDoOrcamento === null ? (
                <Aviso tom="amber">
                  <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
                  <span>
                    Este orçamento está <b>sem base de preço</b>, então as linhas vão entrar com
                    <b> custo zero</b> — escolher a publicação aqui só define onde procurar o item.
                    Defina a base do orçamento (ou use <b>Reprecificar</b> depois) para os preços virem juntos.
                  </span>
                </Aviso>
              ) : baseId !== '' && baseId !== baseDoOrcamento ? (
                <Aviso tom="amber">
                  <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
                  <span>
                    Você está navegando uma publicação <b>diferente</b> da do orçamento. O preço da
                    linha vem sempre da publicação do orçamento — e fica <b>zero</b> se o código não
                    existir lá.
                  </span>
                </Aviso>
              ) : null}
              <div style={{ display: 'flex', gap: 8, marginBottom: 11, marginTop: 11, flexWrap: 'wrap' }}>
                <SeletorDeBase bases={bases} valor={baseId} onChange={setBaseId} />
                <Select value={tipo} onChange={e => setTipo(e.target.value as '' | 'insumo' | 'composicao')}>
                  <option value="">Insumos e composições</option>
                  <option value="composicao">Só composições (serviços)</option>
                  <option value="insumo">Só insumos</option>
                </Select>
                <Select
                  value={ordem}
                  onChange={e => setOrdem(e.target.value as 'codigo' | 'descricao')}
                  title="Ordem da lista"
                >
                  <option value="codigo">Ordem por código</option>
                  <option value="descricao">Ordem alfabética</option>
                </Select>
                <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
                  <Search size={14} style={{ position: 'absolute', left: 10, top: 9, color: 'var(--ink-3)' }} />
                  <input
                    autoFocus
                    value={busca}
                    onChange={e => setBusca(e.target.value)}
                    placeholder="Código ou descrição — ex.: 87879, chapisco, alvenaria"
                    style={{ ...inp, paddingLeft: 30 }}
                  />
                </div>
              </div>

              {/* `height` fixa, não `maxHeight`: sem altura própria, a linha flex
                  assume a do filho mais alto — a cesta crescia a cada item marcado
                  e empurrava a lista para fora da tela. Com altura constante, o
                  bloco não muda de tamanho, marcado ou vazio, e cada coluna rola
                  por dentro. */}
              <div style={{
                display: 'flex', gap: 10, alignItems: 'stretch',
                height: 'min(62vh, 660px)', minHeight: 0,
              }}>
              <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
              <div
                ref={listaRef}
                className="orc-grade"
                style={{
                  flex: 1, minHeight: 0,
                  overflowY: 'auto',
                  // O que fazia o scroll "pegar": ao chegar no fim da lista a
                  // rolagem vazava para a página atrás do modal (scroll chaining).
                  overscrollBehavior: 'contain',
                  // Sem isto a lista salta lateralmente quando a barra aparece.
                  scrollbarGutter: 'stable',
                  border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
                }}
              >
                {referencias.isLoading ? <Loading /> : (referencias.data?.results.length ?? 0) === 0 ? (
                  <div style={{ padding: 26, textAlign: 'center', fontSize: 13, color: 'var(--ink-3)' }}>
                    Nada encontrado nesta publicação.
                  </div>
                ) : referencias.data?.results.map(r => {
                  const marcado = marcados.has(r.referencia_id)
                  return (
                    <div key={r.referencia_id}>
                      <div
                        onClick={() => setMarcados(m => {
                          const p = new Map(m)
                          if (p.has(r.referencia_id)) p.delete(r.referencia_id)
                          else p.set(r.referencia_id, r)
                          return p
                        })}
                        className="orc-linha"
                        style={{
                          display: 'flex', alignItems: 'center', gap: 10, padding: '8px 11px',
                          borderBottom: '1px solid var(--line-2)', cursor: 'pointer',
                          background: marcado ? 'var(--accent-soft)' : undefined,
                        }}
                      >
                        <input type="checkbox" checked={marcado} readOnly style={{ accentColor: 'var(--accent)' }} />
                        <span style={{ ...CAPS, fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'var(--inset)', color: 'var(--ink-3)', flex: 'none' }}>
                          {FONTE_ROTULO[r.base_fonte]}
                        </span>
                        <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 74px' }}>{r.codigo}</span>
                        <span title={r.descricao} style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {r.descricao}
                        </span>
                        {/* Espaço reservado mesmo quando é insumo: sem isso as
                            colunas seguintes mudam de lugar a cada linha. */}
                        {r.tipo === 'composicao' ? (
                          <BotaoAnalitica
                            aberto={espiando === r.referencia_id}
                            onClick={e => { e.stopPropagation(); setEspiando(espiando === r.referencia_id ? null : r.referencia_id) }}
                          />
                        ) : <span style={{ flex: '0 0 18px' }} />}
                        <MarcaCatalogo adotado={!!r.adotado_item_id} />
                        <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 38px', textAlign: 'center' }}>{r.unidade}</span>
                        <span style={{ ...mono, fontSize: 12.5, color: 'var(--ink)', flex: '0 0 104px', textAlign: 'right' }}>{brl(r.custo_unitario)}</span>
                      </div>

                      {espiando === r.referencia_id && (
                        <div style={{ background: 'var(--inset)', padding: '9px 14px 12px 42px', borderBottom: '1px solid var(--line-2)' }}>
                          <div style={{ ...CAPS, marginBottom: 6 }}>Composição analítica — memória de cálculo</div>
                          {composicao.isLoading ? <Loading /> : (composicao.data ?? []).length === 0 ? (
                            <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Esta publicação não trouxe a analítica desta composição.</span>
                          ) : (
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
                              <thead>
                                <tr>
                                  {['Código', 'Insumo', 'Und', 'Coeficiente', 'Custo unit.', 'Parcela'].map((h, i) => (
                                    <th key={h} style={{ ...CAPS, fontSize: 9, textAlign: i >= 3 ? 'right' : 'left', padding: '3px 6px' }}>{h}</th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {composicao.data?.map(c => (
                                  <tr key={c.componente_id}>
                                    <td style={{ ...mono, padding: '3px 6px', color: 'var(--ink-3)' }}>{c.filho_codigo}</td>
                                    <td style={{ padding: '3px 6px', color: 'var(--ink-2)' }}>{c.filho_descricao}</td>
                                    <td style={{ padding: '3px 6px', color: 'var(--ink-3)' }}>{c.filho_unidade}</td>
                                    <td style={{ ...mono, padding: '3px 6px', textAlign: 'right' }}>{num(c.coeficiente)}</td>
                                    <td style={{ ...mono, padding: '3px 6px', textAlign: 'right' }}>{brl(c.filho_custo_unitario)}</td>
                                    <td style={{ ...mono, padding: '3px 6px', textAlign: 'right', color: 'var(--ink)' }}>{brl(c.custo_no_item)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
              {total > 0 && (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
                  marginTop: 9, fontSize: 11.5, color: 'var(--ink-3)',
                }}>
                  <span>
                    <b style={{ color: 'var(--ink-2)' }}>{total.toLocaleString('pt-BR')}</b> itens
                    {' · '}página {pagina.toLocaleString('pt-BR')} de {totalPaginas.toLocaleString('pt-BR')}
                  </span>
                  <LegendaLista />

                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, marginLeft: 'auto' }}>
                    <span>Por página</span>
                    <Select
                      value={porPagina}
                      onChange={e => setPorPagina(Number(e.target.value))}
                      style={{ width: 74, padding: '4px 6px', fontSize: 11.5 }}
                    >
                      {POR_PAGINA.map(n => <option key={n} value={n}>{n}</option>)}
                    </Select>
                  </span>

                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    <Btn variant="ghost" tam="sm" onClick={() => irPara(1)}
                      disabled={pagina <= 1} title="Primeira página">«</Btn>
                    <Btn variant="ghost" tam="sm" onClick={() => irPara(pagina - 1)}
                      disabled={pagina <= 1} title="Página anterior">
                      <ChevronLeft size={13} />
                    </Btn>
                    <Btn variant="ghost" tam="sm" onClick={() => irPara(pagina + 1)}
                      disabled={pagina >= totalPaginas} title="Próxima página">
                      <ChevronRight size={13} />
                    </Btn>
                    <Btn variant="ghost" tam="sm" onClick={() => irPara(totalPaginas)}
                      disabled={pagina >= totalPaginas} title="Última página">»</Btn>
                    {referencias.isFetching && <Spinner />}
                  </span>
                </div>
              )}
              </div>
              <CestaMarcados
                referencias={[...marcados.values()]}
                catalogo={[...marcadosCatalogo.values()]}
                onTirarReferencia={id => setMarcados(m => { const p = new Map(m); p.delete(id); return p })}
                onTirarCatalogo={id => setMarcadosCatalogo(m => { const p = new Map(m); p.delete(id); return p })}
                onLimpar={() => { setMarcados(new Map()); setMarcadosCatalogo(new Map()) }}
              />
              </div>
              <p style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 9, display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                <Sparkles size={13} style={{ flex: 'none', marginTop: 1 }} />
                Inserir da base <b>adota</b> o item no catálogo da empresa (cópia editável) — a base
                oficial permanece intocada, e é o mesmo item que o Suprimentos compra e o Estoque guarda.
              </p>
            </>
          )}
        </>
      )}

      {origem === 'catalogo' && (
        <>
          <div style={{ position: 'relative', marginBottom: 11 }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: 9, color: 'var(--ink-3)' }} />
            <input
              autoFocus
              value={busca}
              onChange={e => setBusca(e.target.value)}
              placeholder="Buscar no catálogo da empresa"
              style={{ ...inp, paddingLeft: 30 }}
            />
          </div>
          <div style={{
            display: 'flex', gap: 10, alignItems: 'stretch',
            height: 'min(62vh, 660px)', minHeight: 0,
          }}>
          <div
            className="orc-grade"
            style={{
              flex: 1, minWidth: 0, overflowY: 'auto',
              overscrollBehavior: 'contain', scrollbarGutter: 'stable',
              border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
            }}
          >
            {catalogo.isLoading ? <Loading /> : (catalogo.data ?? []).length === 0 ? (
              <div style={{ padding: 26, textAlign: 'center', fontSize: 13, color: 'var(--ink-3)' }}>
                Nenhum item no catálogo com esse termo.
              </div>
            ) : catalogo.data?.map(item => {
              const marcado = marcadosCatalogo.has(item.item_id)
              return (
                <div
                  key={item.item_id}
                  className="orc-linha"
                  onClick={() => setMarcadosCatalogo(m => {
                    const p = new Map(m)
                    if (p.has(item.item_id)) p.delete(item.item_id)
                    else p.set(item.item_id, item)
                    return p
                  })}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 11px',
                    borderBottom: '1px solid var(--line-2)', cursor: 'pointer',
                    background: marcado ? 'var(--accent-soft)' : undefined,
                  }}
                >
                  <input type="checkbox" checked={marcado} readOnly style={{ accentColor: 'var(--accent)' }} />
                  <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 96px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {item.codigo_interno}
                  </span>
                  <span title={item.descricao} style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.descricao}
                  </span>
                  {item.fonte_referencia && <Pill kind="slate">{FONTE_ROTULO[item.fonte_referencia]} {item.codigo_referencia}</Pill>}
                  <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 38px', textAlign: 'center' }}>{item.unidade}</span>
                </div>
              )
            })}
          </div>
          <CestaMarcados
            referencias={[...marcados.values()]}
            catalogo={[...marcadosCatalogo.values()]}
            onTirarReferencia={id => setMarcados(m => { const p = new Map(m); p.delete(id); return p })}
            onTirarCatalogo={id => setMarcadosCatalogo(m => { const p = new Map(m); p.delete(id); return p })}
            onLimpar={() => { setMarcados(new Map()); setMarcadosCatalogo(new Map()) }}
          />
          </div>
        </>
      )}

      {origem === 'novo' && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 14px' }}>
            <div style={{ gridColumn: '1 / -1' }}>
              <Field label="Descrição">
                <input autoFocus value={novo.descricao} onChange={e => setNovo(n => ({ ...n, descricao: e.target.value }))} style={inp} />
              </Field>
            </div>
            <Field label="Unidade"><input value={novo.unidade} onChange={e => setNovo(n => ({ ...n, unidade: e.target.value }))} placeholder="m², m³, un, vb" style={inp} /></Field>
            <Field label="Código interno" dica="Em branco, é derivado da descrição.">
              <input value={novo.codigo_interno} onChange={e => setNovo(n => ({ ...n, codigo_interno: e.target.value }))} style={inp} />
            </Field>
            <Field label="Tipo">
              <Select value={novo.tipo} onChange={e => setNovo(n => ({ ...n, tipo: e.target.value }))} style={{ width: '100%', maxWidth: 'none' }}>
                <option value="material">Material</option>
                <option value="mao_de_obra">Mão de obra</option>
                <option value="equipamento">Equipamento / Ferramenta</option>
                <option value="encargos_complementares">Encargos complementares</option>
                <option value="servico">Serviço de terceiro</option>
                <option value="composicao">Composição</option>
                <option value="epi">EPI</option>
              </Select>
            </Field>
            <Field label="Categoria"><input value={novo.categoria} onChange={e => setNovo(n => ({ ...n, categoria: e.target.value }))} style={inp} /></Field>
          </div>
          <Aviso>
            <Plus size={15} style={{ flex: 'none', marginTop: 1 }} />
            O item nasce com fonte <b>PRÓPRIA</b> e preço zerado — digite o custo unitário na grade.
            Para virar composição com insumos e coeficientes, use o banco próprio em Bases &amp; bancos.
          </Aviso>
        </>
      )}

    </Modal>
  )
}
