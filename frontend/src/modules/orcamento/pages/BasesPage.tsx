import { useMemo, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle, Check, Copy, Database, FileDown, FileUp, FolderPlus, LayoutGrid, Lock, LockOpen,
  Plus, ShieldCheck, Sparkles, Trash2, Undo2, Upload,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
// IE.1 — importar/exportar vêm do kit compartilhado; o módulo não tem mais os seus.
import {
  BotaoExportar, RetomarImportacao, WizardImportacao, podeRetomar,
} from '@/components/malha'
import { useDesfazerImportacao, useHistorico, useRecurso } from '@/components/malha/impexp/hooks'
import PaginaShell from '../components/PaginaShell'
import PainelTiposItem from '../components/PainelTiposItem'
import SeletorDeBase from '../components/SeletorDeBase'
import {
  Aviso, BotaoAnalitica, Btn, CampoBusca, Card, CAPS, Empty, Field, inp, LegendaLista, Loading,
  MarcaCatalogo, Modal, mono, Pill, SectHead, Select, Seletor,
} from '../ui'
import { brl, dataBR, FONTE_ROTULO, mesBR, num } from '../lib'
import type { BaseResumo, DivergenciaAdocao } from '../types'
import {
  useAdotarLote, useAdotarDoBanco, useBancos, useBasesResumo, useComposicaoBanco,
  useComposicaoReferencia, useCopiarDaBasePublica, useCriarBanco, useDestravarBanco,
  useItensBanco, useReferenciasInfinitas, useRemoverBanco, useTravarBanco,
} from '../hooks'

type Aba = 'oficiais' | 'meus' | 'importacoes' | 'tipos'

/** Altura da faixa do `PaginaShell`, que é `sticky` no topo do `<main>`. As
 *  barras de filtro desta página grudam logo abaixo dela. */
const TOPO_FIXO = 46

/** Devolve a rolagem ao começo da página.
 *
 *  Quem rola é o `<main>` do `AppShell` (`flex-1 overflow-y-auto` dentro de um
 *  `h-screen overflow-hidden`), não a janela — `window.scrollTo` daqui não mexe
 *  em nada. */
function rolarAoTopo(el: HTMLElement | null) {
  el?.closest('main')?.scrollTo({ top: 0 })
}

/** A publicação (ou o banco) **já escolhido**, como uma faixa de uma linha.
 *
 *  Toma o lugar da grade de cartões depois da escolha: diz o que está aberto,
 *  carrega as ações daquele item e devolve à lista de preços a altura de tela
 *  que dezenas de cartões ocupavam. O botão de trocar reabre a grade — a escolha
 *  nunca fica presa. */
function FaixaEscolhida({ etiquetas, titulo, meta, alerta, acoes }: {
  etiquetas?: ReactNode
  titulo: ReactNode
  meta?: ReactNode
  alerta?: ReactNode
  acoes?: ReactNode
}) {
  return (
    <Card style={{
      display: 'flex', alignItems: 'center', gap: 13, flexWrap: 'wrap', padding: '11px 14px',
      borderColor: 'var(--accent)', background: 'var(--accent-soft)',
    }}>
      <div style={{ flex: 1, minWidth: 230 }}>
        {etiquetas && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4, flexWrap: 'wrap' }}>
            {etiquetas}
          </div>
        )}
        <div style={{ fontSize: 14.5, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.3 }}>{titulo}</div>
        {meta && <div style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', marginTop: 3 }}>{meta}</div>}
        {alerta}
      </div>
      {acoes && <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>{acoes}</div>}
    </Card>
  )
}

/** "Esta publicação não classifica insumo" — no cartão e na faixa, com o mesmo
 *  texto, porque é a mesma informação nos dois lugares em que a escolha é feita. */
function AvisoClassificacao({ base }: { base: BaseResumo }) {
  return (
    <div style={{ fontSize: 11.5, color: 'var(--danger-ink)', marginTop: 4, display: 'flex', gap: 5, alignItems: 'flex-start' }}>
      <AlertTriangle size={12} style={{ flex: 'none', marginTop: 2 }} />
      <span>
        {base.classes_desconhecidas?.length ? (
          <>classes que o sistema não sabe ler: <b>{base.classes_desconhecidas.join(' · ')}</b> — esses insumos caem na unidade</>
        ) : (
          <>não classifica insumo — tudo que não é hora/mês é adotado como material</>
        )}
      </span>
    </div>
  )
}

/** A barra de filtros da lista de preços, grudada abaixo da faixa do módulo.
 *
 *  É `sticky` porque a lista tem 12 mil linhas: a busca, o recorte por tipo e o
 *  botão de adotar precisam continuar ao alcance na linha 300 — antes eles
 *  ficavam no começo da página e sumiam ao primeiro rolar. */
function BarraDaLista({ children }: { children: ReactNode }) {
  return (
    <div style={{
      position: 'sticky', top: TOPO_FIXO, zIndex: 10, display: 'flex', gap: 8,
      alignItems: 'center', flexWrap: 'wrap', margin: '13px -22px 11px', padding: '9px 22px',
      background: 'var(--ground)', borderBottom: '1px solid var(--line-2)',
    }}>{children}</div>
  )
}

export default function BasesPage() {
  const { hasPermission } = useAuth()
  const [aba, setAba] = useState<Aba>('oficiais')
  const [baseId, setBaseId] = useState<number | ''>('')
  const [busca, setBusca] = useState('')
  const [tipo, setTipo] = useState<'' | 'insumo' | 'composicao'>('')
  const [marcados, setMarcados] = useState<Set<number>>(new Set())
  const [espiando, setEspiando] = useState<number | null>(null)
  const [recado, setRecado] = useState('')
  // D110 — os itens que a adoção NÃO sobrescreveu porque o código aponta para
  // outro insumo. Não é toast: some antes de ser lido, e cada linha aqui pede
  // uma conferência à mão. Fica na tela até o usuário fechar.
  const [divergentes, setDivergentes] = useState<DivergenciaAdocao[]>([])
  // O mural de publicações — a grade de cartões — e o texto que o filtra.
  // Fechado por padrão: com a SINAPI carregada são centenas de cartões de 250px,
  // e o que a pessoa vem fazer aqui é *abrir uma* publicação, não admirar todas.
  const [mural, setMural] = useState(false)
  const [filtroMural, setFiltroMural] = useState('')
  const topo = useRef<HTMLDivElement>(null)

  const { data: bases, isLoading: carregandoBases } = useBasesResumo()
  const adotarLote = useAdotarLote()
  const podeAdotar = hasPermission('orcamento.base.adotar')
  const base = bases?.find(b => b.base_id === baseId)

  const params = useMemo(
    // 100 é o teto (`PAGINA_MAXIMA["orcamento"]`) — pedir o máximo por vez reduz
    // pela metade as idas ao servidor para percorrer uma publicação de 12,5 mil.
    () => ({ base: baseId || undefined, search: busca || undefined, tipo: tipo || undefined, page_size: 100 }),
    [baseId, busca, tipo],
  )
  const referencias = useReferenciasInfinitas(params, aba === 'oficiais' && baseId !== '')
  const linhas = useMemo(
    () => referencias.data?.pages.flatMap(p => p.results) ?? [],
    [referencias.data],
  )
  const totalDaBase = referencias.data?.pages[0]?.count ?? 0
  const composicao = useComposicaoReferencia(espiando ?? undefined)

  // O filtro do mural procura no que está escrito no cartão — rótulo, fonte e
  // UF —, para que digitar "BA 08/2026" ache a publicação da Bahia daquele mês.
  const muralFiltrado = useMemo(() => {
    const alvo = filtroMural.trim().toLowerCase()
    if (!alvo || !bases) return bases ?? []
    const termos = alvo.split(/\s+/)
    return bases.filter(b => {
      const texto = `${b.rotulo} ${FONTE_ROTULO[b.fonte] ?? b.fonte} ${b.uf} ${mesBR(b.mes_referencia)} ${b.regime_encargos}`.toLowerCase()
      return termos.every(t => texto.includes(t))
    })
  }, [bases, filtroMural])

  /** Abrir uma publicação **fecha o mural** e devolve a rolagem ao topo.
   *
   *  Era este o defeito da tela: a grade de cartões continuava inteira acima, e
   *  a lista de preços nascia abaixo dela — meia tela de rolagem entre o clique
   *  e o primeiro valor, toda vez. O mural é o passo de escolher; depois de
   *  escolhido, quem manda na tela é a publicação aberta. */
  function escolherBase(id: number | '') {
    setBaseId(id)
    setMarcados(new Set())
    setEspiando(null)
    // As divergências são de uma adoção **daquela** publicação: mantidas na
    // troca, virariam códigos que não existem na tabela que está aberta.
    setDivergentes([])
    if (id !== '') setMural(false)
    rolarAoTopo(topo.current)
  }

  const seletor = (
    <Seletor
      compacto
      valor={aba}
      onChange={setAba}
      opcoes={[
        { valor: 'oficiais' as Aba, rotulo: 'Bases oficiais' },
        { valor: 'meus' as Aba, rotulo: 'Meus bancos' },
        { valor: 'importacoes' as Aba, rotulo: 'Importações' },
        // Tipo de item mora aqui, e não no cadastro de item, porque é da mesma
        // mão: quem monta a régua de preço da casa é quem define o vocabulário
        // com que ela classifica o que compra e o que paga.
        { valor: 'tipos' as Aba, rotulo: 'Tipos de item' },
      ]}
    />
  )

  return (
    <PaginaShell pagina="bases" seletor={seletor}>
      <div ref={topo} style={{ padding: '18px 22px 40px' }}>
        {aba === 'tipos' && <PainelTiposItem />}

        {aba === 'oficiais' && (
          <>
            {/* A carga da base-mãe **não mora aqui** desde 22/08/2026: ela é
                operação de plataforma, não de tenant, e mudou-se para
                Sistema → Bases oficiais. Dentro deste módulo ela dependia do
                entitlement `orcamento` — régua errada para decidir quem carrega
                a SINAPI — e aparecia num produto vendido a quem ela não pertence. */}
            <SectHead right={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {bases && bases.length > 0 && (
                  <span style={{ ...CAPS, fontSize: 9.5 }}>{bases.length.toLocaleString('pt-BR')} publicações</span>
                )}
                <Pill kind="slate"><Lock size={11} />somente leitura</Pill>
              </div>
            }>
              Publicações disponíveis
            </SectHead>

            {carregandoBases ? <Loading /> : !bases || bases.length === 0 ? (
              <Empty>
                Nenhuma base-mãe importada nesta instalação. As bases oficiais (SINAPI, ORSE, SICRO…)
                são carregadas pelo <b>dono da plataforma</b> e valem para todas as empresas —
                nenhum tenant edita, por isso elas são confiáveis como referência de licitação.
              </Empty>
            ) : (
              <>
                {/* **Escolher não é rolar um mural.** A identidade de uma
                    publicação é `fonte × UF × mês × regime`: com a SINAPI
                    carregada inteira são centenas de cartões de 250px, e achar
                    "SINAPI BA 08/2026 desonerado" vira caça ao tesouro. As
                    quatro caixas encadeadas são as mesmas da tela de orçar —
                    cada eixo no seu tamanho natural, ~27 praças e ~20 meses. */}
                <Card style={{ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap', padding: '11px 13px' }}>
                  <SeletorDeBase
                    bases={bases}
                    valor={baseId}
                    onChange={escolherBase}
                    rotuloVazio="Escolha a publicação…"
                    style={{ flex: 1 }}
                  />
                  <Btn tam="sm" onClick={() => setMural(m => !m)}>
                    <LayoutGrid size={13} />{mural ? 'Fechar os cartões' : 'Ver em cartões'}
                  </Btn>
                </Card>

                {/* O mural continua existindo, porque é por ele que se
                    **descobre** o que a instalação tem — e porque ele mostra o
                    que não cabe numa caixa de seleção: quanto já foi adotado e
                    se a publicação classifica insumo. Só não é mais o caminho
                    obrigatório para abrir uma tabela, nem fica empilhado por
                    cima da lista de preços depois que a escolha foi feita. */}
                {mural && (
                  <div style={{ marginTop: 11 }}>
                    <CampoBusca
                      autoFocus
                      valor={filtroMural}
                      onChange={setFiltroMural}
                      placeholder="Filtrar por fonte, estado ou data-base"
                      style={{ marginBottom: 11 }}
                    />
                    {muralFiltrado.length === 0 ? (
                      <Card style={{ padding: 22, textAlign: 'center', fontSize: 13, color: 'var(--ink-3)' }}>
                        Nenhuma publicação com esse texto.
                      </Card>
                    ) : (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(250px,1fr))', gap: 11 }}>
                        {muralFiltrado.map(b => {
                          const ativa = baseId === b.base_id
                          return (
                            <Card
                              key={b.base_id}
                              className="orc-lift"
                              onClick={() => escolherBase(ativa ? '' : b.base_id)}
                              style={{
                                cursor: 'pointer', padding: '13px 15px',
                                borderColor: ativa ? 'var(--accent)' : 'var(--line)',
                                background: ativa ? 'var(--accent-soft)' : 'var(--surface)',
                              }}
                            >
                              <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
                                <span style={{ ...CAPS, fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'var(--inset)', color: 'var(--ink-3)' }}>
                                  {FONTE_ROTULO[b.fonte]}
                                </span>
                                {b.uf && <span style={{ ...CAPS, fontSize: 9 }}>{b.uf}</span>}
                                <Lock size={11} style={{ color: 'var(--ink-3)', marginLeft: 'auto' }} />
                              </div>
                              <div style={{ fontSize: 13.5, fontWeight: 650, color: 'var(--ink)' }}>{b.rotulo}</div>
                              <div style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', marginTop: 4 }}>
                                {b.insumos} insumos · {b.composicoes} composições
                              </div>
                              <div style={{ fontSize: 11.5, color: 'var(--accent-ink)', marginTop: 3 }}>
                                {b.adotados_no_catalogo} adotado(s) no seu catálogo
                              </div>
                              {/* A classificação não chega até a natureza — ou a coluna não
                                  existe (publicação anterior a 01/2025, D111) ou o vocabulário
                                  é de outra base e não sabemos ler. Nos dois casos a adoção cai
                                  no plano B da unidade, e o usuário precisa saber disso AQUI, ao
                                  escolher a base, e não estranhando a analítica depois. */}
                              {!b.classifica_insumo && <AvisoClassificacao base={b} />}
                              <div style={{ ...CAPS, fontSize: 9, marginTop: 5 }}>data-base {mesBR(b.mes_referencia)} · {b.regime_encargos}</div>
                            </Card>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )}

                {/* A publicação aberta, em uma linha: o que os cartões diziam,
                    sem a tela que eles ocupavam. */}
                {base && (
                  <div style={{ marginTop: 11 }}>
                    <FaixaEscolhida
                      etiquetas={
                        <>
                          <span style={{ ...CAPS, fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'var(--surface)', color: 'var(--ink-3)' }}>
                            {FONTE_ROTULO[base.fonte]}
                          </span>
                          {base.uf && <span style={{ ...CAPS, fontSize: 9 }}>{base.uf}</span>}
                          <Pill
                            kind="slate"
                            title="Base-mãe é travada por desenho. Para ajustar coeficiente ou preço, adote o item: ele vira uma cópia editável no catálogo da empresa e a base oficial fica intocada."
                          >
                            <Lock size={10} />somente leitura
                          </Pill>
                        </>
                      }
                      titulo={base.rotulo}
                      meta={
                        <>
                          {base.insumos} insumos · {base.composicoes} composições · data-base{' '}
                          {mesBR(base.mes_referencia)} · {base.regime_encargos} ·{' '}
                          <span style={{ color: 'var(--accent-ink)' }}>
                            {base.adotados_no_catalogo} adotado(s) no seu catálogo
                          </span>
                        </>
                      }
                      alerta={!base.classifica_insumo && <AvisoClassificacao base={base} />}
                      acoes={
                        <Btn tam="sm" onClick={() => { escolherBase(''); setMural(true) }}>
                          <LayoutGrid size={13} />Trocar publicação
                        </Btn>
                      }
                    />
                  </div>
                )}

                {/* A lição de base-mãe travada é do momento de escolher. Depois
                    que uma publicação está aberta, quem a repete é a pílula
                    `somente leitura` da faixa — e o que a tela deve à pessoa
                    naquele instante é altura para a lista de preços. */}
                {!base && (
                  <div style={{ marginTop: 11 }}>
                    <Aviso tom="info">
                      <ShieldCheck size={15} style={{ flex: 'none', marginTop: 1 }} />
                      <span>
                        Base-mãe é <b>travada por desenho</b> — ninguém no seu tenant consegue editar um preço
                        da SINAPI, nem por engano. Para ajustar coeficiente ou preço, <b>adote</b> o item: ele
                        vira uma cópia no catálogo da empresa, editável, e a base oficial fica intocada.
                      </span>
                    </Aviso>
                  </div>
                )}

                {divergentes.length > 0 && (
                  <div style={{ marginTop: 9 }}>
                    <Aviso tom="danger">
                      <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
                      <div style={{ flex: 1 }}>
                        <b>{divergentes.length} item(ns) não foram adotados</b> — o código existe no seu
                        catálogo, mas descrevendo outro insumo. A fonte reaproveitou o número entre
                        edições; sobrescrever trocaria o item por baixo das composições e das planilhas
                        que já o usam. Confira e, se for mesmo o mesmo item, adote um a um.
                        <ul style={{ margin: '7px 0 0', paddingLeft: 17 }}>
                          {divergentes.map(d => (
                            <li key={d.codigo} style={{ marginBottom: 3 }}>
                              <span style={{ ...mono }}>{d.codigo}</span> — {d.motivo}:{' '}
                              no catálogo <b>{d.descricao_catalogo}</b> ({d.unidade_catalogo}) ·{' '}
                              na publicação <b>{d.descricao_publicacao}</b> ({d.unidade_publicacao})
                            </li>
                          ))}
                        </ul>
                        <Btn tam="sm" onClick={() => setDivergentes([])} style={{ marginTop: 8 }}>
                          Entendi
                        </Btn>
                      </div>
                    </Aviso>
                  </div>
                )}

                {baseId !== '' && (
                  <>
                    {/* Filtro, contagem e adoção numa barra só, grudada no topo:
                        são as três coisas que a pessoa quer **enquanto** rola a
                        lista, e não antes dela. O total vem primeiro de propósito
                        — sem ele, uma lista que acaba na centésima linha parece
                        um catálogo pequeno. */}
                    <BarraDaLista>
                      <Select value={tipo} onChange={e => setTipo(e.target.value as '' | 'insumo' | 'composicao')}>
                        <option value="">Insumos e composições</option>
                        <option value="composicao">Só composições</option>
                        <option value="insumo">Só insumos</option>
                      </Select>
                      <CampoBusca
                        valor={busca}
                        onChange={setBusca}
                        placeholder="Código ou descrição"
                        style={{ minWidth: 240 }}
                      />
                      {totalDaBase > 0 && (
                        <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>
                          {linhas.length.toLocaleString('pt-BR')} de{' '}
                          <b style={{ color: 'var(--ink-2)' }}>{totalDaBase.toLocaleString('pt-BR')}</b>
                        </span>
                      )}
                      {podeAdotar && marcados.size > 0 && (
                        <Btn tam="sm" variant="primary" disabled={adotarLote.isPending} onClick={async () => {
                          const r = await adotarLote.mutateAsync([...marcados])
                          setMarcados(new Set())
                          setDivergentes(r.divergentes ?? [])
                          setRecado(`${r.adotados ?? marcados.size} item(ns) adotado(s) no catálogo da empresa.`)
                        }}>
                          <Check size={13} />Adotar {marcados.size} no catálogo
                        </Btn>
                      )}
                    </BarraDaLista>

                    <Card pad={false} style={{ overflow: 'hidden' }}>
                      {referencias.isLoading ? <Loading /> : linhas.length === 0 ? (
                        <div style={{ padding: 26, textAlign: 'center', fontSize: 13, color: 'var(--ink-3)' }}>Nada encontrado.</div>
                      ) : linhas.map(r => {
                        const marcado = marcados.has(r.referencia_id)
                        return (
                          <div key={r.referencia_id}>
                            <div
                              className="orc-linha"
                              onClick={() => podeAdotar && setMarcados(m => {
                                const p = new Set(m)
                                if (p.has(r.referencia_id)) p.delete(r.referencia_id)
                                else p.add(r.referencia_id)
                                return p
                              })}
                              style={{
                                display: 'flex', alignItems: 'center', gap: 10, padding: '8px 13px',
                                borderBottom: '1px solid var(--line-2)', cursor: podeAdotar ? 'pointer' : 'default',
                                background: marcado ? 'var(--accent-soft)' : undefined,
                              }}
                            >
                              {podeAdotar && <input type="checkbox" checked={marcado} readOnly style={{ accentColor: 'var(--accent)' }} />}
                              <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 78px' }}>{r.codigo}</span>
                              <span title={r.descricao} style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {r.descricao}
                              </span>
                              {r.tipo === 'composicao' ? (
                                <BotaoAnalitica
                                  aberto={espiando === r.referencia_id}
                                  onClick={e => { e.stopPropagation(); setEspiando(espiando === r.referencia_id ? null : r.referencia_id) }}
                                />
                              ) : <span style={{ flex: '0 0 18px' }} />}
                              <MarcaCatalogo adotado={!!r.adotado_item_id} />
                              <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 40px', textAlign: 'center' }}>{r.unidade}</span>
                              <span style={{ ...mono, fontSize: 12.5, color: 'var(--ink)', flex: '0 0 108px', textAlign: 'right' }}>{brl(r.custo_unitario)}</span>
                            </div>
                            {espiando === r.referencia_id && (
                              <div style={{ background: 'var(--inset)', padding: '9px 14px 12px 44px', borderBottom: '1px solid var(--line-2)' }}>
                                {composicao.isLoading ? <Loading /> : (composicao.data ?? []).length === 0 ? (
                                  <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Sem analítica nesta publicação.</span>
                                ) : (
                                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
                                    <tbody>
                                      {composicao.data?.map(c => (
                                        <tr key={c.componente_id}>
                                          <td style={{ ...mono, padding: '3px 6px', color: 'var(--ink-3)', width: 78 }}>{c.filho_codigo}</td>
                                          <td style={{ padding: '3px 6px', color: 'var(--ink-2)' }}>{c.filho_descricao}</td>
                                          <td style={{ padding: '3px 6px', color: 'var(--ink-3)', width: 40 }}>{c.filho_unidade}</td>
                                          <td style={{ ...mono, padding: '3px 6px', textAlign: 'right', width: 90 }}>{num(c.coeficiente)}</td>
                                          <td style={{ ...mono, padding: '3px 6px', textAlign: 'right', width: 100, color: 'var(--ink)' }}>{brl(c.custo_no_item)}</td>
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
                      {referencias.hasNextPage && (
                        <div style={{ padding: 10, textAlign: 'center', borderTop: '1px solid var(--line-2)' }}>
                          <Btn
                            variant="ghost"
                            tam="sm"
                            onClick={() => referencias.fetchNextPage()}
                            disabled={referencias.isFetchingNextPage}
                          >
                            {referencias.isFetchingNextPage
                              ? 'Carregando…'
                              : `Carregar mais (${(totalDaBase - linhas.length).toLocaleString('pt-BR')} restantes)`}
                          </Btn>
                        </div>
                      )}
                    </Card>
                    {/* A contagem subiu para a barra fixa; aqui embaixo ela só
                        seria lida por quem já rolou os 12 mil itens. */}
                    <LegendaLista style={{ marginTop: 8 }} />
                  </>
                )}
              </>
            )}
          </>
        )}

        {aba === 'meus' && (
          <PainelMeusBancos
            marcadosDaBase={[...marcados]}
            onRecado={setRecado}
            onLimparMarcados={() => setMarcados(new Set())}
          />
        )}

        {aba === 'importacoes' && <PainelImportacoes onRecado={setRecado} />}
      </div>

      {recado && (
        <div style={{
          position: 'fixed', bottom: 22, left: '50%', zIndex: 95, animation: 'orcToast .22s ease both',
          background: 'var(--brand)', color: 'var(--brand-ink)', padding: '9px 17px',
          borderRadius: 999, fontSize: 12.5, fontWeight: 650, boxShadow: 'var(--shadow-lg)',
        }}>{recado}</div>
      )}
    </PaginaShell>
  )
}

/** Bancos da empresa: criar, travar, navegar os itens e receber cópia da base pública. */
function PainelMeusBancos({ marcadosDaBase, onRecado, onLimparMarcados }: {
  marcadosDaBase: number[]
  onRecado: (m: string) => void
  onLimparMarcados: () => void
}) {
  const { hasPermission } = useAuth()
  const [bancoId, setBancoId] = useState<number | ''>('')
  const [busca, setBusca] = useState('')
  const [criando, setCriando] = useState(false)
  const [espiando, setEspiando] = useState<number | null>(null)
  const [marcados, setMarcados] = useState<Set<number>>(new Set())
  const [filtroBancos, setFiltroBancos] = useState('')
  const raiz = useRef<HTMLDivElement>(null)

  const { data: bancos, isLoading } = useBancos()
  const criar = useCriarBanco()
  const travar = useTravarBanco()
  const destravar = useDestravarBanco()
  const remover = useRemoverBanco()
  const adotar = useAdotarDoBanco()
  const copiarDaBase = useCopiarDaBasePublica()
  const composicao = useComposicaoBanco(espiando ?? undefined)

  const podeEditar = hasPermission('orcamento.orcamento.edit')
  const podeAdotar = hasPermission('orcamento.base.adotar')
  const banco = bancos?.find(b => b.banco_id === bancoId)

  const params = useMemo(
    () => ({ banco: bancoId || undefined, search: busca || undefined, page_size: 50 }),
    [bancoId, busca],
  )
  const itens = useItensBanco(params, bancoId !== '')

  const bancosFiltrados = useMemo(() => {
    const alvo = filtroBancos.trim().toLowerCase()
    if (!alvo || !bancos) return bancos ?? []
    return bancos.filter(b => `${b.nome} ${b.descricao} ${b.uf} ${b.obra_nome ?? ''}`.toLowerCase().includes(alvo))
  }, [bancos, filtroBancos])

  /** Mesma regra da aba das oficiais: abrir um banco recolhe a grade e sobe a
   *  rolagem, para que os itens dele comecem onde os olhos já estão. */
  function escolherBanco(id: number | '') {
    setBancoId(id)
    setMarcados(new Set())
    setEspiando(null)
    rolarAoTopo(raiz.current)
  }

  return (
    <div ref={raiz}>
      <SectHead right={podeEditar
        ? <Btn tam="sm" variant="primary" onClick={() => setCriando(true)}><Plus size={13} />Novo banco</Btn>
        : undefined}>
        Bancos de preço da empresa
      </SectHead>

      {isLoading ? <Loading /> : !bancos || bancos.length === 0 ? (
        <Empty acao={podeEditar
          ? <Btn variant="primary" onClick={() => setCriando(true)}><Plus size={14} />Criar o primeiro banco</Btn>
          : undefined}>
          Nenhum banco próprio ainda. É aqui que entram a <b>tabela da prefeitura</b>, o banco
          histórico da empresa e as composições calibradas pelo preço que você realmente pagou —
          isolados do seu tenant, sem tocar nas bases oficiais.
        </Empty>
      ) : banco ? (
        /* Banco aberto: uma faixa com o que o cartão dizia e as ações dele,
           no lugar da grade inteira. Trocar de banco reabre a grade. */
        <FaixaEscolhida
          etiquetas={
            <>
              <span style={{ ...CAPS, fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'var(--surface)', color: 'var(--ink-3)' }}>
                {FONTE_ROTULO[banco.fonte]}
              </span>
              {banco.uf && <span style={{ ...CAPS, fontSize: 9 }}>{banco.uf}</span>}
              {banco.travado
                ? <Pill kind="slate" title={`Travado por ${banco.travado_por_nome} em ${dataBR(banco.travado_em)}`}><Lock size={10} />travado</Pill>
                : <Pill kind="good">editável</Pill>}
            </>
          }
          titulo={banco.nome}
          meta={
            <>
              {banco.total_itens} itens · {banco.total_pastas} pasta(s) ·{' '}
              {banco.mes_referencia ? `data-base ${mesBR(banco.mes_referencia)}` : 'sem data-base'}
              {banco.obra_nome ? ` · ${banco.obra_nome}` : ''}
            </>
          }
          acoes={
            <>
              <Btn tam="sm" onClick={() => escolherBanco('')}>
                <LayoutGrid size={13} />Trocar banco
              </Btn>
              {podeEditar && (banco.travado ? (
                <Btn tam="sm" disabled={destravar.isPending} onClick={async () => {
                  await destravar.mutateAsync(banco.banco_id)
                  onRecado('Banco destravado — a alteração fica registrada.')
                }}><LockOpen size={13} />Destravar</Btn>
              ) : (
                <Btn tam="sm" disabled={travar.isPending} onClick={async () => {
                  await travar.mutateAsync(banco.banco_id)
                  onRecado('Banco travado. Ninguém edita o preço sem destravar antes.')
                }}><Lock size={13} />Travar</Btn>
              ))}
              {podeEditar && !banco.travado && (
                <Btn tam="sm" variant="perigo" disabled={remover.isPending} onClick={async () => {
                  await remover.mutateAsync(banco.banco_id)
                  setBancoId('')
                  onRecado('Banco excluído.')
                }}><Trash2 size={13} />Excluir</Btn>
              )}
            </>
          }
        />
      ) : (
        <>
          <CampoBusca
            valor={filtroBancos}
            onChange={setFiltroBancos}
            placeholder="Filtrar por nome, estado ou obra"
            style={{ marginBottom: 11 }}
          />
          {bancosFiltrados.length === 0 ? (
            <Card style={{ padding: 22, textAlign: 'center', fontSize: 13, color: 'var(--ink-3)' }}>
              Nenhum banco com esse texto.
            </Card>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(262px,1fr))', gap: 11 }}>
              {bancosFiltrados.map(b => (
                <Card
                  key={b.banco_id}
                  className="orc-lift"
                  onClick={() => escolherBanco(b.banco_id)}
                  style={{ cursor: 'pointer', padding: '13px 15px' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
                    <span style={{ ...CAPS, fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'var(--inset)', color: 'var(--ink-3)' }}>
                      {FONTE_ROTULO[b.fonte]}
                    </span>
                    {b.uf && <span style={{ ...CAPS, fontSize: 9 }}>{b.uf}</span>}
                    <span style={{ marginLeft: 'auto' }}>
                      {b.travado
                        ? <Pill kind="slate" title={`Travado por ${b.travado_por_nome} em ${dataBR(b.travado_em)}`}><Lock size={10} />travado</Pill>
                        : <Pill kind="good">editável</Pill>}
                    </span>
                  </div>
                  <div style={{ fontSize: 13.5, fontWeight: 650, color: 'var(--ink)' }}>{b.nome}</div>
                  <div style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', marginTop: 4 }}>
                    {b.total_itens} itens · {b.total_pastas} pasta(s)
                  </div>
                  <div style={{ ...CAPS, fontSize: 9, marginTop: 5 }}>
                    {b.mes_referencia ? `data-base ${mesBR(b.mes_referencia)}` : 'sem data-base'}
                    {b.obra_nome ? ` · ${b.obra_nome}` : ''}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}

      {marcadosDaBase.length > 0 && bancos && bancos.length > 0 && podeEditar && (
        <>
          <div style={{ height: 14 }} />
          <Aviso tom="amber">
            <Copy size={15} style={{ flex: 'none', marginTop: 1 }} />
            <span style={{ flex: 1 }}>
              Você marcou <b>{marcadosDaBase.length} item(ns)</b> na aba de bases oficiais. Copie
              para um banco seu e edite coeficiente e preço lá — a base oficial não é tocada.
            </span>
            <Select
              value={bancoId}
              onChange={e => setBancoId(e.target.value ? Number(e.target.value) : '')}
              style={{ maxWidth: 200 }}
            >
              <option value="">Escolha o banco</option>
              {bancos.filter(b => !b.travado).map(b => (
                <option key={b.banco_id} value={b.banco_id}>{b.nome}</option>
              ))}
            </Select>
            <Btn tam="sm" variant="primary" disabled={!bancoId || copiarDaBase.isPending} onClick={async () => {
              const r = await copiarDaBase.mutateAsync({ banco: Number(bancoId), referencias: marcadosDaBase })
              onLimparMarcados()
              onRecado(`${r.criados} item(ns) copiados — agora editáveis no seu banco.`)
            }}>Copiar</Btn>
          </Aviso>
        </>
      )}

      {banco && (
        <>
          {/* Travar, destravar e excluir subiram para a faixa do banco: são
              ações **do banco**, e repeti-las num cabeçalho logo abaixo do nome
              dele era uma segunda linha de cromo entre a escolha e os preços. */}
          {banco.travado && (
            <div style={{ marginTop: 11 }}>
              <Aviso tom="info">
                <ShieldCheck size={15} style={{ flex: 'none', marginTop: 1 }} />
                <span>
                  Banco travado em {dataBR(banco.travado_em)} por <b>{banco.travado_por_nome || '—'}</b>.
                  Item, coeficiente e pasta ficam somente leitura — a trava vale para o conteúdo, não
                  só para o nome.
                </span>
              </Aviso>
            </div>
          )}

          <BarraDaLista>
            <CampoBusca valor={busca} onChange={setBusca} placeholder="Buscar neste banco" style={{ minWidth: 240 }} />
            {(itens.data?.count ?? 0) > 0 && (
              <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>
                {(itens.data?.results.length ?? 0).toLocaleString('pt-BR')} de{' '}
                <b style={{ color: 'var(--ink-2)' }}>{(itens.data?.count ?? 0).toLocaleString('pt-BR')}</b>
              </span>
            )}
            {podeAdotar && marcados.size > 0 && (
              <Btn tam="sm" variant="primary" disabled={adotar.isPending} onClick={async () => {
                const r = await adotar.mutateAsync({ banco: banco.banco_id, itens: [...marcados] })
                setMarcados(new Set())
                // D110: o que não conferiu ficou de fora, e o número sozinho
                // não conta essa parte da história.
                const fora = r.divergentes?.length ?? 0
                onRecado(
                  `${r.criados} item(ns) adotados no catálogo da empresa.`
                  + (fora ? ` ${fora} não conferem com o que já está no catálogo e ficaram de fora.` : ''),
                )
              }}>
                <Check size={13} />Adotar {marcados.size}
              </Btn>
            )}
          </BarraDaLista>

          <Card pad={false} style={{ overflow: 'hidden' }}>
            {itens.isLoading ? <Loading /> : (itens.data?.results.length ?? 0) === 0 ? (
              <div style={{ padding: 26, textAlign: 'center', fontSize: 13, color: 'var(--ink-3)' }}>
                Banco vazio. Importe uma planilha ou copie itens de uma base oficial.
              </div>
            ) : itens.data?.results.map(item => {
              const marcado = marcados.has(item.item_banco_id)
              return (
                <div key={item.item_banco_id}>
                  <div
                    className="orc-linha"
                    onClick={() => podeAdotar && setMarcados(m => {
                      const p = new Set(m)
                      if (p.has(item.item_banco_id)) p.delete(item.item_banco_id)
                      else p.add(item.item_banco_id)
                      return p
                    })}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 13px',
                      borderBottom: '1px solid var(--line-2)', cursor: podeAdotar ? 'pointer' : 'default',
                      background: marcado ? 'var(--accent-soft)' : undefined,
                    }}
                  >
                    {podeAdotar && <input type="checkbox" checked={marcado} readOnly style={{ accentColor: 'var(--accent)' }} />}
                    <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 120px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.codigo}
                    </span>
                    <span title={item.descricao} style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.descricao}
                    </span>
                    {item.tipo === 'composicao' ? (
                      <BotaoAnalitica
                        aberto={espiando === item.item_banco_id}
                        onClick={e => { e.stopPropagation(); setEspiando(espiando === item.item_banco_id ? null : item.item_banco_id) }}
                      />
                    ) : <span style={{ flex: '0 0 18px' }} />}
                    <MarcaCatalogo adotado={!!item.adotado_item_id} />
                    <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', flex: '0 0 40px', textAlign: 'center' }}>{item.unidade}</span>
                    <span style={{ ...mono, fontSize: 12.5, color: 'var(--ink)', flex: '0 0 108px', textAlign: 'right' }}>{brl(item.custo_unitario)}</span>
                  </div>
                  {espiando === item.item_banco_id && (
                    <div style={{ background: 'var(--inset)', padding: '9px 14px 12px 44px', borderBottom: '1px solid var(--line-2)' }}>
                      {composicao.isLoading ? <Loading /> : (composicao.data ?? []).length === 0 ? (
                        <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Sem componentes cadastrados.</span>
                      ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
                          <tbody>
                            {composicao.data?.map(c => (
                              <tr key={c.componente_id}>
                                <td style={{ ...mono, padding: '3px 6px', color: 'var(--ink-3)', width: 120 }}>{c.filho_codigo}</td>
                                <td style={{ padding: '3px 6px', color: 'var(--ink-2)' }}>{c.filho_descricao}</td>
                                <td style={{ padding: '3px 6px', color: 'var(--ink-3)', width: 40 }}>{c.filho_unidade}</td>
                                <td style={{ ...mono, padding: '3px 6px', textAlign: 'right', width: 90 }}>{num(c.coeficiente)}</td>
                                <td style={{ ...mono, padding: '3px 6px', textAlign: 'right', width: 100, color: 'var(--ink)' }}>{brl(c.custo_no_item)}</td>
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
          </Card>
        </>
      )}

      {criando && (
        <Modal
          titulo="Novo banco de preço"
          onClose={() => setCriando(false)}
          rodape={<Btn onClick={() => setCriando(false)}>Fechar</Btn>}
        >
          <FormNovoBanco
            salvando={criar.isPending}
            onCriar={async dados => {
              const novo = await criar.mutateAsync(dados)
              setCriando(false)
              escolherBanco(novo.banco_id)
              onRecado('Banco criado. Importe uma planilha ou copie itens de uma base oficial.')
            }}
          />
        </Modal>
      )}
    </div>
  )
}

function FormNovoBanco({ salvando, onCriar }: {
  salvando: boolean
  onCriar: (dados: Record<string, unknown>) => void
}) {
  const [form, setForm] = useState({ nome: '', descricao: '', uf: '', mes: '' })
  const [erro, setErro] = useState('')
  return (
    <>
      {erro && <Aviso tom="danger">{erro}</Aviso>}
      <Field label="Nome" dica="Ex.: Prefeitura de Aracaju 03/2026, Banco histórico da empresa">
        <input autoFocus value={form.nome} onChange={e => setForm(f => ({ ...f, nome: e.target.value }))} style={inp} />
      </Field>
      <Field label="Descrição">
        <input value={form.descricao} onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))} style={inp} />
      </Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Field label="UF"><input value={form.uf} maxLength={2} onChange={e => setForm(f => ({ ...f, uf: e.target.value.toUpperCase() }))} style={inp} /></Field>
        <Field label="Data-base"><input type="month" value={form.mes} onChange={e => setForm(f => ({ ...f, mes: e.target.value }))} style={{ ...inp, ...mono }} /></Field>
      </div>
      <Aviso>
        <Database size={15} style={{ flex: 'none', marginTop: 1 }} />
        O banco é <b>da empresa</b>, não de uma obra — a tabela de uma prefeitura serve todas as
        obras daquela cidade.
      </Aviso>
      <div style={{ height: 14 }} />
      <Btn variant="primary" disabled={salvando} onClick={() => {
        if (!form.nome.trim()) { setErro('O nome é obrigatório.'); return }
        onCriar({
          nome: form.nome.trim(),
          descricao: form.descricao.trim(),
          uf: form.uf.trim(),
          mes_referencia: form.mes ? `${form.mes}-01` : null,
        })
      }}>Criar banco</Btn>
    </>
  )
}

/** Importações: o motor de plataforma, com o banco escolhido como destino.
 *
 *  Depois do **IE.1** esta tela não tem mais leitor, conferência nem histórico
 *  próprios: `<WizardImportacao>` é o mesmo componente que qualquer módulo usa
 *  ([funcoesimpexp §10](../../../../../docs/modulos/funcoesimpexp.md)). O que
 *  sobrou aqui é o que **é** do Orçamento: escolher para qual banco vai. */
function PainelImportacoes({ onRecado }: { onRecado: (m: string) => void }) {
  const [bancoDestino, setBancoDestino] = useState<number | ''>('')
  /** O lote que a pessoa clicou para retomar — a janela abre nele. */
  const [retomando, setRetomando] = useState<number | null>(null)
  const { data: bancos } = useBancos()
  const { recurso } = useRecurso('orcamento.banco_preco')
  const { data: historico, isLoading, refetch } = useHistorico('orcamento.banco_preco')

  const bancosEditaveis = (bancos ?? []).filter(b => !b.travado)
  const desfazer = useDesfazerImportacao()
  // Os lotes que ainda dependem de uma decisão. Ficam num cartaz acima da
  // tabela porque essa é a informação que a pessoa veio buscar — descobri-la
  // lendo a coluna "Status" de um histórico de oito linhas é sorte, não tela.
  const pendentes = (historico ?? []).filter(i => podeRetomar(i.status))

  return (
    <>
      <SectHead>Trazer preços para dentro</SectHead>

      {!recurso ? (
        <Empty>
          Importar tabela de preço exige <b>acesso total</b> ao recurso — as permissões
          {' '}<code style={{ ...mono }}>orcamento.base.view</code> e
          {' '}<code style={{ ...mono }}>orcamento.base.adotar</code>. Meia permissão bloqueia:
          arquivo sai inteiro ou não sai.
        </Empty>
      ) : bancosEditaveis.length === 0 ? (
        <Aviso tom="amber">
          <FolderPlus size={15} style={{ flex: 'none', marginTop: 1 }} />
          Você precisa de um banco destravado para receber a importação. Crie um em <b>Meus bancos</b>
          {' '}(ou destrave o existente).
        </Aviso>
      ) : (
        <Card style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <FileUp size={20} style={{ color: 'var(--accent-ink)' }} />
          <div style={{ flex: 1, minWidth: 220 }}>
            <div style={{ fontSize: 13.5, fontWeight: 650, color: 'var(--ink)' }}>Subir planilha ou PDF</div>
            <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
              XLSX, CSV ou PDF. O sistema lê, classifica e <b>para na conferência</b> — nada é gravado antes de você decidir.
            </div>
          </div>
          <Select value={bancoDestino} onChange={e => setBancoDestino(e.target.value ? Number(e.target.value) : '')} style={{ maxWidth: 220 }}>
            <option value="">Banco de destino</option>
            {bancosEditaveis.map(b => <option key={b.banco_id} value={b.banco_id}>{b.nome}</option>)}
          </Select>
          {bancoDestino ? (
            <WizardImportacao
              tam="md"
              recurso="orcamento.banco_preco"
              contexto={{ banco: Number(bancoDestino) }}
              rotulo="Escolher arquivo"
              onConcluida={resumo => {
                refetch()
                onRecado(
                  resumo.status === 'descartada'
                    ? 'Importação descartada — nada foi gravado.'
                    : `${resumo.aplicadas} linha(s) gravadas no banco.`,
                )
              }}
            />
          ) : (
            <Btn variant="primary" disabled title="Escolha o banco de destino primeiro">
              <Upload size={14} />Escolher arquivo
            </Btn>
          )}
          <BotaoExportar
            tam="md"
            recurso="orcamento.banco_preco"
            recorte={{ banco: Number(bancoDestino) }}
          />
        </Card>
      )}

      <SectHead>Histórico</SectHead>
      {pendentes.length > 0 && (
        <Aviso tom="amber">
          <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
          <span style={{ flex: 1 }}>
            <b>{pendentes.length} importação(ões) esperando você.</b> Nada foi gravado — o
            arquivo está guardado no servidor e a decisão continua de pé. Clique na linha
            para conferir as linhas, responder o de-para ou ver o que impediu a leitura.
          </span>
          <Btn tam="sm" variant="primary" onClick={() => setRetomando(pendentes[0].importacao_id)}>
            Retomar a mais recente
          </Btn>
        </Aviso>
      )}
      {isLoading ? <Loading /> : !historico || historico.length === 0 ? (
        <Empty>Nenhuma importação ainda.</Empty>
      ) : (
        <Card pad={false} style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr>
                {['Quando', 'Arquivo', 'Por', 'Status', 'Lidas', 'Aplicadas', ''].map((h, i) => (
                  <th key={h || i} style={{
                    ...CAPS, padding: '9px 12px', textAlign: i >= 4 ? 'right' : 'left',
                    borderBottom: '1px solid var(--line)', background: 'var(--surface-2)',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {historico.map(imp => {
                /* Um lote em `lendo`/`conferindo`/`erro` ainda espera uma
                   decisão humana — e antes não havia onde tomá-la: a linha ficava
                   parada no histórico dizendo "Conferência", sem nada clicável, e
                   o único caminho era subir a planilha de novo. A linha inteira é
                   a porta, com o botão explícito ao lado para quem procura um. */
                const retomavel = podeRetomar(imp.status)
                const abrir = () => retomavel && setRetomando(imp.importacao_id)
                return (
                <tr
                  key={imp.importacao_id}
                  className="orc-linha"
                  onClick={abrir}
                  title={retomavel ? 'Abrir esta importação e decidir o que entra' : undefined}
                  style={{ cursor: retomavel ? 'pointer' : 'default' }}
                >
                  <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', color: 'var(--ink-3)' }}>{dataBR(imp.criada_em)}</td>
                  <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', color: 'var(--ink)', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={imp.arquivo || undefined}>{imp.arquivo || '—'}</td>
                  <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', color: 'var(--ink-3)' }}>{imp.usuario_nome || '—'}</td>
                  <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)' }}>
                    <Pill kind={
                      imp.status === 'aplicada' ? 'good'
                        : imp.status === 'conferindo' || imp.status === 'lendo' ? 'amber'
                          : imp.status === 'erro' ? 'danger' : 'slate'
                    }>{imp.status_nome}</Pill>
                  </td>
                  <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono }}>{imp.total}</td>
                  <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono }}>{imp.aplicadas}</td>
                  <td
                    style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right' }}
                    onClick={e => e.stopPropagation()}
                  >
                    {retomavel && (
                      <Btn
                        tam="sm"
                        variant="primary"
                        title={
                          imp.status === 'erro'
                            ? 'Ver o que impediu a leitura e tentar de novo'
                            : 'Continuar: conferir as linhas e decidir o que entra'
                        }
                        onClick={abrir}
                      >
                        <FileUp size={13} />Retomar
                      </Btn>
                    )}
                    {imp.pode_desfazer && (
                      <Btn
                        tam="sm"
                        disabled={desfazer.isPending}
                        title="Restaura o preço e a procedência de cada linha deste lote"
                        onClick={async () => {
                          await desfazer.mutateAsync(imp.importacao_id)
                          refetch()
                          onRecado('Lote desfeito — os preços anteriores voltaram.')
                        }}
                      >
                        <Undo2 size={13} />Desfazer
                      </Btn>
                    )}
                  </td>
                </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}

      <Aviso tom="info">
        <Sparkles size={15} style={{ flex: 'none', marginTop: 1 }} />
        <span>
          <b>Quem importa o quê:</b> o dono da plataforma importa <b>bases-mãe</b>, que valem para
          todas as empresas. Você importa para os <b>seus bancos</b>, que não saem do seu tenant. Os
          dois caminhos usam esta mesma conferência, e o seu tem teto do plano — por linhas em cada
          importação e por linhas acumuladas na empresa.
        </span>
      </Aviso>

      <SectHead>Exportar</SectHead>
      <Card style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <FileDown size={17} style={{ color: 'var(--ink-3)' }} />
        <span style={{ flex: 1, minWidth: 240, fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.55 }}>
          Planilha sintética e analítica em XLSX e PDF, curva ABC e cronograma em XLSX — a entrega
          para licitação, cliente e cartório. Fica no botão <b>Exportar</b> da página Orçar, sobre o
          orçamento aberto.
        </span>
        <Link to="/app/orcamento/orcar" style={{ textDecoration: 'none' }}>
          <Btn tam="sm">Ir para Orçar</Btn>
        </Link>
      </Card>

      {retomando !== null && (
        <RetomarImportacao
          recurso="orcamento.banco_preco"
          importacaoId={retomando}
          onFechar={() => { setRetomando(null); refetch() }}
          onConcluida={resumo => {
            refetch()
            onRecado(
              resumo.status === 'descartada'
                ? 'Importação descartada — nada foi gravado.'
                : `${resumo.aplicadas} linha(s) gravadas no banco.`,
            )
          }}
        />
      )}
    </>
  )
}
