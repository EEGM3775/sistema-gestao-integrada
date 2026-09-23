import { useMemo, useState } from 'react'
import { AlertTriangle, Check, Lock, Plus, Repeat, X } from 'lucide-react'
import { Btn, Empty, Pill } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { contemSemAcento } from '@/utils/texto'
import { usePdca } from '../contexto'
import { percentual } from '../formato'
import type {
  CandidatoDaSemana, CausaNaoCumprimento, ItemProgramacao, ProgramacaoSemanal,
} from '../types'

/** O que está sendo arrastado. Vai no `dataTransfer` como JSON porque o
 *  navegador só transporta texto — e ler do estado em vez do evento quebraria
 *  o arrasto entre duas abas do mesmo quadro. */
type Carga =
  | { de: 'candidato'; atividade: number }
  | { de: 'quadro'; item: number }

/** O julgamento em edição, antes de ir ao servidor. */
export interface Julgamento {
  cumprido: boolean | null
  causa: number | null
  nota: string
}

/** A coluna de quem ninguém assumiu. É a **string vazia**, que é exatamente o
 *  que o servidor guarda em `responsavel` nesse caso — assim o sentinela da
 *  tela e o valor do banco são a mesma coisa, o `<option value="">` é HTML
 *  comum, e não existe um caractere de controle passeando pelo DOM. */
const SEM_DONO = ''

/** **O quadro da semana** — candidatos à esquerda, o que cada equipe assumiu à
 *  direita.
 *
 *  Canvas de arrastar próprio, e não biblioteca de kanban: o modelo de coluna
 *  daquelas é "estado do cartão", e aqui a coluna é **quem assume**. O cartão
 *  não anda por estágios; ele é puxado do plano, ganha dono, e no fim da semana
 *  é julgado no lugar onde está.
 *
 *  **O quadro é o posto, e o PPC é consequência do gesto** — não há uma tela de
 *  índice ao lado: o número sai de julgar estes cartões, aqui. */
export function QuadroDaSemana({
  programacao, itens, candidatos, causas, julgamentos, carregandoCandidatos,
  podeMontar, podeJulgar, emJulgamento,
  aoPuxar, aoMover, aoDevolver, aoJulgar,
}: {
  programacao: ProgramacaoSemanal
  itens: ItemProgramacao[]
  candidatos: CandidatoDaSemana[]
  causas: CausaNaoCumprimento[]
  julgamentos: Record<number, Julgamento>
  carregandoCandidatos: boolean
  podeMontar: boolean
  podeJulgar: boolean
  emJulgamento: boolean
  aoPuxar: (atividade: number, responsavel: string) => void
  aoMover: (item: number, responsavel: string) => void
  aoDevolver: (item: number) => void
  aoJulgar: (item: number, julgamento: Julgamento) => void
}) {
  const [busca, setBusca] = useState('')
  const [equipesNovas, setEquipesNovas] = useState<string[]>([])
  const [batendo, setBatendo] = useState<string | null>(null)

  const montavel = podeMontar && programacao.status === 'rascunho'

  const equipes = useMemo(() => {
    const doQuadro = new Set<string>()
    for (const item of itens) {
      doQuadro.add(item.responsavel.trim() || SEM_DONO)
    }
    for (const nova of equipesNovas) doQuadro.add(nova)
    const nomeadas = [...doQuadro].filter((e) => e !== SEM_DONO).sort(
      (a, b) => a.localeCompare(b, 'pt-BR'),
    )
    //: A coluna sem dono fica **em primeiro**, e não escondida no fim: o cartão
    //: que ninguém assumiu é o que a reunião precisa resolver antes de acabar.
    return doQuadro.has(SEM_DONO) || nomeadas.length === 0
      ? [SEM_DONO, ...nomeadas]
      : nomeadas
  }, [itens, equipesNovas])

  const visiveis = useMemo(() => {
    const abertos = candidatos.filter((c) => !c.ja_no_quadro)
    if (!busca.trim()) return abertos
    return abertos.filter((c) => contemSemAcento(`${c.codigo} ${c.nome}`, busca))
  }, [candidatos, busca])

  function receber(evento: React.DragEvent, equipe: string) {
    evento.preventDefault()
    setBatendo(null)
    if (!montavel) return
    const carga = lerCarga(evento)
    if (!carga) return
    const dono = equipe === SEM_DONO ? '' : equipe
    if (carga.de === 'candidato') aoPuxar(carga.atividade, dono)
    else aoMover(carga.item, dono)
  }

  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 0, minWidth: 0 }}>
      {/* ---- a área de rascunho: o que o plano diz que é desta semana ---- */}
      <aside
        onDragOver={(e) => { if (montavel) { e.preventDefault(); setBatendo('rascunho') } }}
        onDragLeave={() => setBatendo(null)}
        onDrop={(e) => {
          e.preventDefault()
          setBatendo(null)
          const carga = lerCarga(e)
          if (montavel && carga?.de === 'quadro') aoDevolver(carga.item)
        }}
        style={{
          width: 268, flexShrink: 0, display: 'flex', flexDirection: 'column',
          borderRight: '1px solid var(--line)', background: 'var(--surface)',
          outline: batendo === 'rascunho' ? '2px dashed var(--accent)' : 'none',
          outlineOffset: -4,
        }}
      >
        <header
          style={{
            padding: '11px 13px', borderBottom: '1px solid var(--line-2)',
            flexShrink: 0,
          }}
        >
          <div
            style={{
              fontSize: 10.5, letterSpacing: '0.12em', textTransform: 'uppercase',
              color: 'var(--ink-3)', fontWeight: 700,
            }}
          >
            O plano sugere
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--ink-3)', margin: '2px 0 8px' }}>
            {carregandoCandidatos
              ? 'lendo o cronograma…'
              : `${visiveis.length} serviço${visiveis.length === 1 ? '' : 's'} atravessa${visiveis.length === 1 ? '' : 'm'} esta semana`}
          </div>
          <input
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Procurar serviço"
            style={{
              width: '100%', padding: '6px 9px', borderRadius: 7, fontSize: 12.5,
              border: '1px solid var(--line)', background: 'var(--ground)',
              color: 'var(--ink)', fontFamily: 'inherit',
            }}
          />
        </header>

        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: 9 }}>
          {!carregandoCandidatos && visiveis.length === 0 && (
            <p
              style={{
                fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.55,
                padding: '10px 4px', margin: 0,
              }}
            >
              {candidatos.length === 0
                ? 'O plano vigente desta obra não tem serviço nesta semana. A sugestão vem do cronograma — o quadro não depende dela, e qualquer frente pode ser assumida mesmo assim.'
                : 'Todos os serviços que o plano sugere já estão no quadro.'}
            </p>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {visiveis.map((candidato) => (
              <CartaoCandidato
                key={candidato.atividade}
                candidato={candidato}
                arrastavel={montavel}
                aoPuxar={() => aoPuxar(candidato.atividade, '')}
              />
            ))}
          </div>
        </div>

        {montavel && (
          <footer
            style={{
              padding: '8px 12px', borderTop: '1px solid var(--line-2)',
              fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.5, flexShrink: 0,
            }}
          >
            Arraste para a equipe que assume. Solte aqui para devolver um cartão
            ao plano.
          </footer>
        )}
      </aside>

      {/* ---- o quadro: uma coluna por equipe ---- */}
      <div
        style={{
          flex: 1, minWidth: 0, display: 'flex', gap: 10, overflowX: 'auto',
          padding: 12, alignItems: 'flex-start',
        }}
      >
        {itens.length === 0 && equipes.length <= 1 && !montavel ? (
          <div style={{ padding: 24, maxWidth: 520 }}>
            <Empty>
              <span style={{ lineHeight: 1.6 }}>
                Esta semana está {programacao.status_rotulo.toLowerCase()} e não
                tem nenhum compromisso no quadro.
              </span>
            </Empty>
          </div>
        ) : (
          equipes.map((equipe) => (
            <ColunaDaEquipe
              key={equipe || 'sem-dono'}
              equipe={equipe}
              equipes={equipes}
              itens={itens.filter(
                (i) => (i.responsavel.trim() || SEM_DONO) === equipe,
              )}
              causas={causas}
              julgamentos={julgamentos}
              montavel={montavel}
              podeJulgar={podeJulgar}
              emJulgamento={emJulgamento}
              batendo={batendo === equipe}
              aoEntrar={() => montavel && setBatendo(equipe)}
              aoSair={() => setBatendo(null)}
              aoSoltar={(e) => receber(e, equipe)}
              aoDevolver={aoDevolver}
              aoMover={aoMover}
              aoJulgar={aoJulgar}
            />
          ))
        )}

        {montavel && (
          <BotaoDeEquipe
            aoCriar={(nome) => setEquipesNovas((atual) => [...atual, nome])}
            existentes={equipes}
          />
        )}
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */

function CartaoCandidato({
  candidato, arrastavel, aoPuxar,
}: {
  candidato: CandidatoDaSemana
  arrastavel: boolean
  aoPuxar: () => void
}) {
  const { selecionar } = usePdca()
  const travado = candidato.restricoes_abertas > 0

  return (
    <div
      draggable={arrastavel && !travado}
      onDragStart={(e) => escreverCarga(e, { de: 'candidato', atividade: candidato.atividade })}
      onClick={() => selecionar({ tipo: 'atividade', id: candidato.atividade })}
      title={travado
        ? `Este serviço tem ${candidato.restricoes_abertas} trava(s) aberta(s) e não entra no quadro. Destrave primeiro, na esteira à esquerda.`
        : undefined}
      style={{
        background: travado ? 'var(--inset)' : 'var(--ground)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-sm)',
        padding: '8px 10px',
        cursor: travado ? 'not-allowed' : arrastavel ? 'grab' : 'pointer',
        opacity: travado ? 0.72 : 1,
      }}
    >
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--ink-3)',
        }}
      >
        {candidato.codigo}
        {candidato.critica && <Pill kind="danger">crítico</Pill>}
        <span style={{ flex: 1 }} />
        {/* **Arrastar não pode ser o único caminho.** Quem usa teclado não
            arrasta, e numa reunião com o quadro num tablet arrastar entre
            colunas é pior do que escolher. O botão puxa sem dono; a coluna se
            decide no próprio cartão, logo abaixo. */}
        {arrastavel && !travado && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); aoPuxar() }}
            title="Puxar para o quadro desta semana"
            aria-label={`Puxar ${candidato.nome} para o quadro`}
            style={{
              display: 'grid', placeItems: 'center', width: 22, height: 22,
              borderRadius: 6, cursor: 'pointer', flexShrink: 0,
              background: 'var(--surface)', border: '1px solid var(--line)',
              color: 'var(--ink-2)',
            }}
          >
            <Plus size={13} />
          </button>
        )}
      </div>
      <div
        style={{
          fontSize: 12.5, color: 'var(--ink)', lineHeight: 1.4, marginTop: 3,
          fontWeight: 600,
        }}
      >
        {candidato.nome}
      </div>
      {(candidato.inicio_previsto || candidato.fim_previsto) && (
        <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 3 }}>
          {candidato.inicio_previsto ? dateToBR(candidato.inicio_previsto) : '—'}
          {' → '}
          {candidato.fim_previsto ? dateToBR(candidato.fim_previsto) : '—'}
        </div>
      )}
      {(travado || candidato.ncs_abertas > 0) && (
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 6 }}>
          {travado && (
            <Pill kind="danger">
              <Lock size={10} />
              {candidato.restricoes_abertas} trava{candidato.restricoes_abertas > 1 ? 's' : ''}
            </Pill>
          )}
          {candidato.ncs_abertas > 0 && (
            <Pill kind="accent">
              {candidato.ncs_abertas} defeito{candidato.ncs_abertas > 1 ? 's' : ''}
            </Pill>
          )}
        </div>
      )}
    </div>
  )
}

function ColunaDaEquipe({
  equipe, equipes, itens, causas, julgamentos, montavel, podeJulgar, emJulgamento,
  batendo, aoEntrar, aoSair, aoSoltar, aoDevolver, aoMover, aoJulgar,
}: {
  equipe: string
  equipes: string[]
  itens: ItemProgramacao[]
  causas: CausaNaoCumprimento[]
  julgamentos: Record<number, Julgamento>
  montavel: boolean
  podeJulgar: boolean
  emJulgamento: boolean
  batendo: boolean
  aoEntrar: () => void
  aoSair: () => void
  aoSoltar: (e: React.DragEvent) => void
  aoDevolver: (item: number) => void
  aoMover: (item: number, responsavel: string) => void
  aoJulgar: (item: number, julgamento: Julgamento) => void
}) {
  const semDono = equipe === SEM_DONO
  const porJulgar = itens.filter(
    (i) => (julgamentos[i.item_programacao_id]?.cumprido ?? i.cumprido) == null,
  ).length

  return (
    <section
      onDragOver={(e) => { if (montavel) { e.preventDefault(); aoEntrar() } }}
      onDragLeave={aoSair}
      onDrop={aoSoltar}
      style={{
        width: 262, flexShrink: 0, background: 'var(--surface)',
        border: `1px solid ${batendo ? 'var(--accent)' : 'var(--line)'}`,
        borderRadius: 'var(--r-md)', display: 'flex', flexDirection: 'column',
        maxHeight: '100%', boxShadow: batendo ? 'var(--shadow-sm)' : 'none',
      }}
    >
      <header
        style={{
          padding: '9px 11px', borderBottom: '1px solid var(--line-2)',
          flexShrink: 0,
        }}
      >
        <div
          style={{
            fontSize: 12.5, fontWeight: 700,
            color: semDono ? 'var(--ink-3)' : 'var(--ink)',
            fontStyle: semDono ? 'italic' : 'normal',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
        >
          {semDono ? 'Sem dono ainda' : equipe}
        </div>
        <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2 }}>
          {itens.length} compromisso{itens.length === 1 ? '' : 's'}
          {emJulgamento && porJulgar > 0 && ` · ${porJulgar} por julgar`}
        </div>
      </header>

      <div
        style={{
          flex: 1, minHeight: 60, overflowY: 'auto', padding: 8,
          display: 'flex', flexDirection: 'column', gap: 7,
        }}
      >
        {itens.length === 0 && (
          <p
            style={{
              fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5,
              margin: 0, padding: '8px 4px',
            }}
          >
            {semDono
              ? 'Nenhum cartão sem dono — é assim que a semana deve sair da reunião.'
              : montavel
                ? 'Arraste para cá o que esta equipe assume.'
                : 'Nada assumido por esta equipe.'}
          </p>
        )}
        {itens.map((item) => (
          <CartaoDeCompromisso
            key={item.item_programacao_id}
            item={item}
            causas={causas}
            equipes={equipes}
            julgamento={julgamentos[item.item_programacao_id]}
            montavel={montavel}
            podeJulgar={podeJulgar}
            emJulgamento={emJulgamento}
            aoDevolver={() => aoDevolver(item.item_programacao_id)}
            aoMover={(dono) => aoMover(item.item_programacao_id, dono)}
            aoJulgar={(j) => aoJulgar(item.item_programacao_id, j)}
          />
        ))}
      </div>
    </section>
  )
}

function CartaoDeCompromisso({
  item, causas, equipes, julgamento, montavel, podeJulgar, emJulgamento,
  aoDevolver, aoMover, aoJulgar,
}: {
  item: ItemProgramacao
  causas: CausaNaoCumprimento[]
  equipes: string[]
  julgamento: Julgamento | undefined
  montavel: boolean
  podeJulgar: boolean
  emJulgamento: boolean
  aoDevolver: () => void
  aoMover: (responsavel: string) => void
  aoJulgar: (julgamento: Julgamento) => void
}) {
  const { selecao, selecionar } = usePdca()
  const escolhido = selecao?.tipo === 'atividade' && selecao.id === item.atividade

  const cumprido = julgamento?.cumprido ?? item.cumprido
  const causa = julgamento?.causa ?? item.causa
  const nota = julgamento?.nota ?? item.nota

  const previsto = percentual(item.percentual_previsto)
  const apontado = percentual(item.percentual_apontado)

  function julgar(valor: boolean) {
    //: Marcar "saiu" **limpa a causa**: o servidor recusa cumprido com causa, e
    //: deixar o campo pendurado faria a recusa chegar no fim da reunião.
    aoJulgar({
      cumprido: cumprido === valor ? null : valor,
      causa: valor ? null : causa,
      nota,
    })
  }

  return (
    <div
      draggable={montavel}
      onDragStart={(e) => escreverCarga(e, { de: 'quadro', item: item.item_programacao_id })}
      onClick={() => selecionar({ tipo: 'atividade', id: item.atividade })}
      style={{
        background: 'var(--ground)',
        border: `1px solid ${escolhido ? 'var(--accent)' : 'var(--line)'}`,
        borderLeft: `3px solid ${
          cumprido === true ? 'var(--good-ink)'
            : cumprido === false ? 'var(--danger-ink)'
              : 'var(--line)'
        }`,
        borderRadius: 'var(--r-sm)', padding: '8px 10px',
        cursor: montavel ? 'grab' : 'pointer',
      }}
    >
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--ink-3)',
        }}
      >
        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {item.atividade_codigo}
        </span>
        {montavel && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); aoDevolver() }}
            title="Devolver ao plano"
            style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: 0,
              color: 'var(--ink-3)', display: 'flex',
            }}
          >
            <X size={12} />
          </button>
        )}
      </div>

      <div
        style={{
          fontSize: 12.5, color: 'var(--ink)', lineHeight: 1.4, marginTop: 3,
          fontWeight: 600,
        }}
      >
        {item.atividade_nome}
      </div>
      {item.local_rotulo && (
        <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2 }}>
          {item.local_rotulo}
        </div>
      )}

      {/* Prometido e feito lado a lado, e **nunca somados**: um é o que a
          equipe assumiu, o outro é o que o campo apontou. */}
      {(previsto || apontado) && (
        <div
          style={{
            display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 6,
            fontSize: 11, color: 'var(--ink-3)',
          }}
        >
          {previsto && (
            <span>
              prometeu{' '}
              <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>
                {previsto}
              </span>
            </span>
          )}
          {previsto && apontado && <span>·</span>}
          {apontado ? (
            <span>
              apontou{' '}
              <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>
                {apontado}
              </span>
            </span>
          ) : (
            <span style={{ fontStyle: 'italic' }} title="O campo não apontou nada nesta semana — o que é diferente de ter apontado zero.">
              ninguém apontou
            </span>
          )}
        </div>
      )}

      {/* O par acessível do arrasto entre colunas — ver o botão de puxar. */}
      {montavel && (
        <select
          value={item.responsavel.trim() || SEM_DONO}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => aoMover(e.target.value === SEM_DONO ? '' : e.target.value)}
          aria-label={`Quem assume ${item.atividade_nome}`}
          style={{
            width: '100%', marginTop: 7, padding: '4px 6px', borderRadius: 6,
            fontSize: 11.5, border: '1px solid var(--line)',
            background: 'var(--surface)', color: 'var(--ink-2)',
            fontFamily: 'inherit',
          }}
        >
          {equipes.map((nome) => (
            <option key={nome || 'sem-dono'} value={nome}>
              {nome === SEM_DONO ? 'Sem dono ainda' : nome}
            </option>
          ))}
        </select>
      )}

      {(item.restricoes_abertas > 0 || item.ncs_abertas > 0 || item.vezes_arrastado > 0) && (
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 6 }}>
          {item.restricoes_abertas > 0 && (
            <Pill kind="danger">
              <AlertTriangle size={10} />
              {item.restricoes_abertas} trava{item.restricoes_abertas > 1 ? 's' : ''}
            </Pill>
          )}
          {item.ncs_abertas > 0 && (
            <Pill kind="accent">
              {item.ncs_abertas} defeito{item.ncs_abertas > 1 ? 's' : ''}
            </Pill>
          )}
          {item.vezes_arrastado > 0 && (
            <Pill
              kind="info"
              title="Este compromisso não saiu em semanas anteriores e continua de pé."
            >
              <Repeat size={10} />
              {item.vezes_arrastado + 1}ª semana
            </Pill>
          )}
        </div>
      )}

      {emJulgamento && podeJulgar && (
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--line-2)',
            display: 'flex', flexDirection: 'column', gap: 6,
          }}
        >
          <div style={{ display: 'flex', gap: 5 }}>
            <BotaoDeJulgamento
              ativo={cumprido === true}
              tom="good"
              onClick={() => julgar(true)}
            >
              <Check size={12} />
              Saiu
            </BotaoDeJulgamento>
            <BotaoDeJulgamento
              ativo={cumprido === false}
              tom="danger"
              onClick={() => julgar(false)}
            >
              <X size={12} />
              Não saiu
            </BotaoDeJulgamento>
          </div>

          {cumprido === false && (
            <>
              <select
                value={causa ?? ''}
                onChange={(e) => aoJulgar({
                  cumprido: false,
                  causa: e.target.value ? Number(e.target.value) : null,
                  nota,
                })}
                style={{
                  width: '100%', padding: '5px 7px', borderRadius: 6, fontSize: 12,
                  border: `1px solid ${causa ? 'var(--line)' : 'var(--danger-ink)'}`,
                  background: 'var(--surface)', color: 'var(--ink)',
                  fontFamily: 'inherit',
                }}
              >
                <option value="">Por que não saiu?</option>
                {causas.map((c) => (
                  <option key={c.causa_id} value={c.causa_id}>
                    {c.codigo} · {c.nome}
                  </option>
                ))}
              </select>
              <input
                value={nota}
                onChange={(e) => aoJulgar({ cumprido: false, causa, nota: e.target.value })}
                placeholder="Qual material? Que projeto?"
                style={{
                  width: '100%', padding: '5px 7px', borderRadius: 6, fontSize: 12,
                  border: '1px solid var(--line)', background: 'var(--surface)',
                  color: 'var(--ink)', fontFamily: 'inherit',
                }}
              />
            </>
          )}
        </div>
      )}

      {!emJulgamento && cumprido != null && (
        <div style={{ marginTop: 7 }}>
          <Pill kind={cumprido ? 'good' : 'danger'}>
            {cumprido ? 'saiu' : `não saiu${item.causa_nome ? ` · ${item.causa_nome}` : ''}`}
          </Pill>
        </div>
      )}
    </div>
  )
}

function BotaoDeJulgamento({
  ativo, tom, onClick, children,
}: {
  ativo: boolean
  tom: 'good' | 'danger'
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        flex: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        gap: 4, padding: '5px 8px', borderRadius: 6, cursor: 'pointer',
        fontSize: 11.5, fontWeight: 650, fontFamily: 'inherit',
        background: ativo ? `var(--${tom}-soft)` : 'var(--surface)',
        color: ativo ? `var(--${tom}-ink)` : 'var(--ink-3)',
        border: `1px solid ${ativo ? `var(--${tom}-soft)` : 'var(--line)'}`,
      }}
    >
      {children}
    </button>
  )
}

function BotaoDeEquipe({
  aoCriar, existentes,
}: { aoCriar: (nome: string) => void; existentes: string[] }) {
  const [abrindo, setAbrindo] = useState(false)
  const [nome, setNome] = useState('')

  function confirmar() {
    const limpo = nome.trim()
    if (!limpo || existentes.includes(limpo)) {
      setAbrindo(false)
      setNome('')
      return
    }
    aoCriar(limpo)
    setNome('')
    setAbrindo(false)
  }

  if (!abrindo) {
    return (
      <button
        type="button"
        onClick={() => setAbrindo(true)}
        style={{
          width: 190, flexShrink: 0, padding: '14px 12px', cursor: 'pointer',
          border: '1px dashed var(--line)', borderRadius: 'var(--r-md)',
          background: 'transparent', color: 'var(--ink-3)', fontSize: 12.5,
          fontWeight: 650, fontFamily: 'inherit',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
        }}
      >
        <Plus size={14} />
        Nova equipe
      </button>
    )
  }

  return (
    <div
      style={{
        width: 224, flexShrink: 0, padding: 10, border: '1px solid var(--line)',
        borderRadius: 'var(--r-md)', background: 'var(--surface)',
        display: 'flex', flexDirection: 'column', gap: 8,
      }}
    >
      <input
        autoFocus
        value={nome}
        onChange={(e) => setNome(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') confirmar()
          if (e.key === 'Escape') { setAbrindo(false); setNome('') }
        }}
        placeholder="Nome da equipe ou do encarregado"
        style={{
          width: '100%', padding: '6px 9px', borderRadius: 7, fontSize: 12.5,
          border: '1px solid var(--line)', background: 'var(--ground)',
          color: 'var(--ink)', fontFamily: 'inherit',
        }}
      />
      <span style={{ fontSize: 10.5, color: 'var(--ink-3)', lineHeight: 1.45 }}>
        É este nome que o encarregado vai procurar no celular dele. Escreva como
        a obra o chama.
      </span>
      <div style={{ display: 'flex', gap: 6 }}>
        <Btn tam="sm" variant="primary" onClick={confirmar}>Criar</Btn>
        <Btn tam="sm" onClick={() => { setAbrindo(false); setNome('') }}>Cancelar</Btn>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */

function escreverCarga(evento: React.DragEvent, carga: Carga) {
  evento.dataTransfer.setData('text/plain', JSON.stringify(carga))
  evento.dataTransfer.effectAllowed = 'move'
}

function lerCarga(evento: React.DragEvent): Carga | null {
  try {
    const bruto = evento.dataTransfer.getData('text/plain')
    if (!bruto) return null
    const carga = JSON.parse(bruto) as Carga
    return carga?.de === 'candidato' || carga?.de === 'quadro' ? carga : null
  } catch {
    //: Arrastar texto de fora da página cai aqui, e não é erro: o quadro
    //: simplesmente não recebe o que não é cartão dele.
    return null
  }
}
