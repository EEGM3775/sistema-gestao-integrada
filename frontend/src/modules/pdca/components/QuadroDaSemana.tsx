import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Building2, Check, Lock, Package, Plus, Repeat, User, X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Btn, Empty, Pill } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { contemSemAcento } from '@/utils/texto'
import { usePdca } from '../contexto'
import { useAuth } from '@/hooks/useAuth'
import { percentual } from '../formato'
import { useCriarEquipe, useEquipesDaObra, usePedirMaterialDaSemana } from '../hooks'
import { buscarFornecedores, buscarFuncionarios } from '../api/montagemApi'
import { mensagemDe } from '../montagem'
import { SeloDoMaterial } from './SeloDoMaterial'
import type {
  CandidatoDaSemana, CausaNaoCumprimento, EquipeObra, ItemProgramacao, ProgramacaoSemanal,
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
  /** O % concluído da atividade — quando há, o "saiu" é derivado dele. */
  percentual_concluido?: string | null
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
  const [batendo, setBatendo] = useState<string | null>(null)
  //: As colunas são as **equipes da obra** — composições de funcionários e
  //: fornecedores (decisão do dono, 09/10/2026) — mais os nomes soltos de
  //: cartões antigos, que continuam aparecendo onde estavam.
  const equipesDaObra = useEquipesDaObra(programacao.obra)
  const composicoes = useMemo(
    () => new Map((equipesDaObra.data ?? []).map((e) => [e.nome, e])),
    [equipesDaObra.data],
  )

  const montavel = podeMontar && programacao.status === 'rascunho'

  const equipes = useMemo(() => {
    const doQuadro = new Set<string>()
    for (const item of itens) {
      doQuadro.add(item.responsavel.trim() || SEM_DONO)
    }
    for (const nome of composicoes.keys()) doQuadro.add(nome)
    const nomeadas = [...doQuadro].filter((e) => e !== SEM_DONO).sort(
      (a, b) => a.localeCompare(b, 'pt-BR'),
    )
    //: A coluna sem dono fica **em primeiro**, e não escondida no fim: o cartão
    //: que ninguém assumiu é o que a reunião precisa resolver antes de acabar.
    return doQuadro.has(SEM_DONO) || nomeadas.length === 0
      ? [SEM_DONO, ...nomeadas]
      : nomeadas
  }, [itens, composicoes])

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
              composicao={composicoes.get(equipe)}
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
            obraId={programacao.obra}
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
      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 6 }}>
        <SeloDoMaterial atividade={candidato.atividade} />
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
    </div>
  )
}

function ColunaDaEquipe({
  equipe, composicao, equipes, itens, causas, julgamentos, montavel, podeJulgar, emJulgamento,
  batendo, aoEntrar, aoSair, aoSoltar, aoDevolver, aoMover, aoJulgar,
}: {
  equipe: string
  /** A composição, quando a coluna é uma equipe da obra (e não um nome solto). */
  composicao?: EquipeObra
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
        {/* Quem é a equipe — a composição, e não só o nome que alguém deu. */}
        {composicao && composicao.membros.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
            {composicao.membros.map((m) => (
              <span
                key={`${m.tipo}-${m.id}`}
                title={m.tipo === 'fornecedor' ? 'Fornecedor' : 'Funcionário'}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 3, maxWidth: '100%',
                  padding: '1px 6px', borderRadius: 999, fontSize: 10.5,
                  background: m.tipo === 'fornecedor' ? 'var(--info-soft)' : 'var(--inset)',
                  color: m.tipo === 'fornecedor' ? 'var(--info-ink)' : 'var(--ink-2)',
                }}
              >
                {m.tipo === 'fornecedor' ? <Building2 size={9} /> : <User size={9} />}
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.nome}</span>
              </span>
            ))}
          </div>
        )}
        {!semDono && !composicao && (
          <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 4, fontStyle: 'italic' }}>
            nome solto, sem composição
          </div>
        )}
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

const STATUS_DA_REQUISICAO: Record<string, string> = {
  rascunho: 'rascunho', pendente: 'aguardando aprovação', aprovada: 'aprovada (reservado)',
  atendida: 'atendida', parcial: 'atendida em parte', cancelada: 'cancelada',
}

/** "Pedir material" do compromisso — requisição em rascunho no Estoque, e o
 *  cartão mostra em que pé ela está *(decisão do dono: botão por compromisso)*. */
function PedidoDeMaterial({ item }: { item: ItemProgramacao }) {
  const { obraId } = usePdca()
  const { hasPermission } = useAuth()
  const pedir = usePedirMaterialDaSemana(obraId)
  const [erro, setErro] = useState<string | null>(null)
  const pedido = item.requisicao_sil && item.requisicao_sil_status !== 'cancelada'
  if (pedido) {
    return (
      <Link
        to="/app/sil"
        onClick={(e) => e.stopPropagation()}
        title="Abrir a requisição no Estoque"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 6, fontSize: 11, color: 'var(--brand)', textDecoration: 'none' }}
      >
        <Package size={11} /> material pedido · req. #{item.requisicao_sil} · {STATUS_DA_REQUISICAO[item.requisicao_sil_status ?? ''] ?? item.requisicao_sil_status}
      </Link>
    )
  }
  if (!hasPermission('sil.requisicao.edit')) return null
  return (
    <div style={{ marginTop: 6 }}>
      <button
        type="button"
        disabled={pedir.isPending}
        onClick={async (e) => {
          e.stopPropagation()
          setErro(null)
          try { await pedir.mutateAsync(item.item_programacao_id) } catch (err) { setErro(mensagemDe(err)) }
        }}
        title="Cria a requisição do material da semana ao almoxarifado (em rascunho)"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, fontWeight: 650, padding: '2px 8px', borderRadius: 'var(--r-sm)', border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink-2)', cursor: 'pointer' }}
      >
        <Package size={11} /> {pedir.isPending ? 'Pedindo…' : 'Pedir material'}
      </button>
      {erro && <div style={{ fontSize: 10.5, color: 'var(--danger-ink)', marginTop: 3 }}>{erro}</div>}
    </div>
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

  //: O julgamento é pelo **% concluído** da atividade (decisão do dono,
  //: 09/10/2026); o "saiu" do PPC é derivado: bateu a meta da semana ou não.
  //: A conta final é do servidor — esta é a mesma, para a causa ser pedida
  //: na hora e não no fim da reunião.
  const concluido = julgamento?.percentual_concluido !== undefined
    ? julgamento.percentual_concluido
    : item.percentual_concluido ?? null
  const meta = item.meta_da_semana != null ? Number(item.meta_da_semana) : 100
  const atual = item.avanco_atual != null ? Number(item.avanco_atual) : 0
  const valorConcluido = concluido != null && concluido !== '' ? Number(concluido) : null
  const abaixoDoApontado = valorConcluido != null && valorConcluido < atual

  function definirConcluido(texto: string) {
    const limpo = texto.replace(/[^\d,.]/g, '').replace(',', '.')
    if (!limpo) {
      aoJulgar({ cumprido: null, causa, nota, percentual_concluido: null })
      return
    }
    const n = Number(limpo)
    if (!Number.isFinite(n) || n > 100) return
    const saiu = n >= meta
    //: Bater a meta **limpa a causa**: o servidor recusa cumprido com causa.
    aoJulgar({ cumprido: saiu, causa: saiu ? null : causa, nota, percentual_concluido: limpo })
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

      <PedidoDeMaterial item={item} />
      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 6 }}>
        <SeloDoMaterial atividade={item.atividade} />
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

      {emJulgamento && podeJulgar && (
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--line-2)',
            display: 'flex', flexDirection: 'column', gap: 6,
          }}
        >
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: 'var(--ink-3)' }}>
            <span style={{ flex: 1 }}>Concluído</span>
            <span style={{ position: 'relative', width: 78 }}>
              <input
                inputMode="decimal"
                value={concluido == null ? '' : String(concluido).replace('.', ',')}
                placeholder={String(atual).replace('.', ',')}
                onChange={(e) => definirConcluido(e.target.value)}
                aria-label={`Quanto de ${item.atividade_nome} está concluído`}
                style={{
                  width: '100%', padding: '4px 20px 4px 7px', borderRadius: 6, fontSize: 12.5,
                  textAlign: 'right', fontFamily: 'var(--mono)',
                  border: `1px solid ${abaixoDoApontado ? 'var(--danger-ink)' : 'var(--line)'}`,
                  background: 'var(--surface)', color: 'var(--ink)',
                }}
              />
              <span style={{ position: 'absolute', right: 7, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}>%</span>
            </span>
          </label>
          <div style={{ fontSize: 10.5, color: 'var(--ink-3)', lineHeight: 1.45 }}>
            {abaixoDoApontado
              ? <span style={{ color: 'var(--danger-ink)' }}>O campo já apontou {percentual(atual)} — o concluído não fica abaixo disso.</span>
              : <>
                  meta da semana <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>{percentual(meta)}</span>
                  {' · '}hoje em <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>{percentual(atual)}</span>
                  {valorConcluido != null && valorConcluido > atual && <> · lança +{percentual(valorConcluido - atual)} de avanço</>}
                </>}
          </div>
          {cumprido != null && !abaixoDoApontado && (
            <Pill kind={cumprido ? 'good' : 'danger'}>
              {cumprido ? <Check size={10} /> : <X size={10} />}
              {cumprido ? 'bateu a meta · saiu' : 'abaixo da meta · não saiu'}
            </Pill>
          )}

          {cumprido === false && !abaixoDoApontado && (
            <>
              <select
                value={causa ?? ''}
                onChange={(e) => aoJulgar({
                  cumprido: false,
                  causa: e.target.value ? Number(e.target.value) : null,
                  nota,
                  percentual_concluido: concluido,
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
                onChange={(e) => aoJulgar({ cumprido: false, causa, nota: e.target.value, percentual_concluido: concluido })}
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
            {item.percentual_concluido != null && `${percentual(item.percentual_concluido)} · `}
            {cumprido ? 'saiu' : `não saiu${item.causa_nome ? ` · ${item.causa_nome}` : ''}`}
          </Pill>
        </div>
      )}
    </div>
  )
}

/** **Compor** a equipe — funcionários do RH e fornecedores (as empreiteiras),
 *  não escrever um nome (decisão do dono, 09/10/2026). O nome é opcional: vazio,
 *  nasce dos membros. A equipe é da obra e volta nas semanas seguintes. */
function BotaoDeEquipe({ obraId, existentes }: { obraId: number; existentes: string[] }) {
  const [abrindo, setAbrindo] = useState(false)
  const [nome, setNome] = useState('')
  const [filtro, setFiltro] = useState('')
  const [funcionarios, setFuncionarios] = useState<number[]>([])
  const [fornecedores, setFornecedores] = useState<number[]>([])
  const [erro, setErro] = useState<string | null>(null)
  const criar = useCriarEquipe(obraId)
  const pessoas = useQuery({
    queryKey: ['pdca', 'funcionarios'], queryFn: buscarFuncionarios, enabled: abrindo,
  })
  const empresas = useQuery({
    queryKey: ['pdca', 'fornecedores'], queryFn: buscarFornecedores, enabled: abrindo,
  })

  function fechar() {
    setAbrindo(false)
    setNome('')
    setFiltro('')
    setFuncionarios([])
    setFornecedores([])
    setErro(null)
  }

  async function confirmar() {
    const limpo = nome.trim()
    if (limpo && existentes.some((e) => e.toLocaleLowerCase('pt-BR') === limpo.toLocaleLowerCase('pt-BR'))) {
      setErro('Já há uma coluna com esse nome nesta semana.')
      return
    }
    setErro(null)
    try {
      await criar.mutateAsync({ obra: obraId, nome: limpo, funcionarios, fornecedores })
      fechar()
    } catch (e) {
      setErro(mensagemDe(e))
    }
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

  const casa = (texto: string) => !filtro.trim() || contemSemAcento(texto, filtro)
  const alternar = (lista: number[], id: number) =>
    lista.includes(id) ? lista.filter((x) => x !== id) : [...lista, id]
  const campo = {
    width: '100%', padding: '6px 9px', borderRadius: 7, fontSize: 12.5,
    border: '1px solid var(--line)', background: 'var(--ground)',
    color: 'var(--ink)', fontFamily: 'inherit',
  } as const
  const rotuloDaLista = {
    fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 700,
    color: 'var(--ink-3)', display: 'flex', alignItems: 'center', gap: 4,
  } as const
  const escolhidos = funcionarios.length + fornecedores.length

  return (
    <div
      style={{
        width: 280, flexShrink: 0, padding: 10, border: '1px solid var(--line)',
        borderRadius: 'var(--r-md)', background: 'var(--surface)',
        display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '100%',
      }}
    >
      <input
        autoFocus
        value={nome}
        onChange={(e) => setNome(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Escape') fechar() }}
        placeholder="Nome da equipe (opcional)"
        aria-label="Nome da equipe"
        style={campo}
      />
      <input
        value={filtro}
        onChange={(e) => setFiltro(e.target.value)}
        placeholder="Procurar funcionário ou fornecedor"
        aria-label="Procurar membros"
        style={campo}
      />
      <div style={{ flex: 1, minHeight: 80, maxHeight: 300, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 3 }}>
        <span style={rotuloDaLista}><User size={10} /> Funcionários</span>
        {pessoas.isLoading && <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>Carregando…</span>}
        {pessoas.isError && <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>Sem acesso ao RH.</span>}
        {(pessoas.data ?? []).filter((p) => casa(p.nome_completo)).map((p) => (
          <label key={`f-${p.funcionario_id}`} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, color: 'var(--ink-2)', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={funcionarios.includes(p.funcionario_id)}
              onChange={() => setFuncionarios((l) => alternar(l, p.funcionario_id))}
            />
            {p.nome_completo}
          </label>
        ))}
        <span style={{ ...rotuloDaLista, marginTop: 6 }}><Building2 size={10} /> Fornecedores</span>
        {empresas.isLoading && <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>Carregando…</span>}
        {empresas.isError && <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>Sem acesso a fornecedores.</span>}
        {(empresas.data ?? []).filter((f) => casa(f.razao_social)).map((f) => (
          <label key={`e-${f.fornecedor_id}`} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, color: 'var(--ink-2)', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={fornecedores.includes(f.fornecedor_id)}
              onChange={() => setFornecedores((l) => alternar(l, f.fornecedor_id))}
            />
            {f.razao_social}
          </label>
        ))}
      </div>
      <span style={{ fontSize: 10.5, color: 'var(--ink-3)', lineHeight: 1.45 }}>
        {escolhidos === 0
          ? 'Escolha quem forma a equipe. Sem nome, ela se chama pelos membros.'
          : `${escolhidos} na equipe. A equipe é da obra e volta nas próximas semanas.`}
      </span>
      {erro && <span style={{ fontSize: 11.5, color: 'var(--danger-ink)' }}>{erro}</span>}
      <div style={{ display: 'flex', gap: 6 }}>
        <Btn tam="sm" variant="primary" disabled={escolhidos === 0 || criar.isPending} onClick={() => void confirmar()}>
          {criar.isPending ? 'Criando…' : 'Criar'}
        </Btn>
        <Btn tam="sm" onClick={fechar}>Cancelar</Btn>
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
