import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  ChevronLeft, ChevronRight, ClipboardCheck, Gavel, LayoutGrid, Lock,
  RotateCcw, Save, TrendingUp,
} from 'lucide-react'
import { BotaoExportar, Btn, Card, Empty, Loading, Modal, Pill, SectionHead, WizardImportacao } from '@/components/malha'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/hooks/useAuth'
import { dateToBR } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import { usePdca } from '../contexto'
import { percentual } from '../formato'
import {
  useAbrirSemana, useAnotarSemana, useArrastarPendentes, useCandidatos,
  useCatalogoDeCausas, useComprometerSemana, useDevolverCompromisso,
  useEncerrarSemana, useGantt, useItensDaSemana, useJulgarSemana,
  usePlanoCorrente, usePuxarParaOQuadro, useRankingDeCausas, useReabrirSemana,
  useRestricoes, useSalvarCompromisso, useSemana, useSeriePpc,
} from '../hooks'
import { hojeIso, intervaloDaSemana, rotuloDaSemana, segundaDaSemana, somaDias } from '../semana'
import { DialogoDeEncerramento } from '../components/DialogoDeEncerramento'
import { EsteiraDeRestricoes } from '../components/EsteiraDeRestricoes'
import { QuadroDaSemana, type Julgamento } from '../components/QuadroDaSemana'
import { RankingDeCausas } from '../components/RankingDeCausas'
import { SerieDePpc } from '../components/SerieDePpc'
import type { JulgamentoDeItem, ProgramacaoSemanal } from '../types'

type Vista = 'quadro' | 'desempenho'

/** **O posto do Last Planner.** O quadro *é* o posto: o PPC não mora numa tela
 *  ao lado, ele é consequência de julgar estes cartões, aqui.
 *
 *  A semana vive no endereço (`?s=AAAA-MM-DD`) pela mesma razão que a obra vive
 *  na rota: quem compara a semana de duas obras precisa de um link colável, e a
 *  aba nova tem de abrir onde estava. */
export default function SemanaPage() {
  const { obraId } = usePdca()
  const { hasPermission } = useAuth()
  const [params, setParams] = useSearchParams()
  const [vista, setVista] = useState<Vista>('quadro')
  const [emJulgamento, setEmJulgamento] = useState(false)
  const [julgamentos, setJulgamentos] = useState<Record<number, Julgamento>>({})
  const [encerrando, setEncerrando] = useState(false)
  const [reabrindo, setReabrindo] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string[] | null>(null)

  const inicio = segundaDaSemana(params.get('s') || hojeIso())
  const fim = somaDias(inicio, 6)

  const semana = useSemana(obraId, inicio)
  const programacao = semana.data
  const itens = useItensDaSemana(programacao?.programacao_id)
  const candidatos = useCandidatos(
    programacao?.programacao_id, programacao?.status === 'rascunho',
  )
  const causas = useCatalogoDeCausas()
  const restricoes = useRestricoes(obraId)
  const { plano } = usePlanoCorrente(obraId)
  const gantt = useGantt(plano?.cronograma_id)

  const abrir = useAbrirSemana(obraId)
  const puxar = usePuxarParaOQuadro(obraId)
  const salvar = useSalvarCompromisso(obraId)
  const devolver = useDevolverCompromisso(obraId)
  const comprometer = useComprometerSemana(obraId)
  const julgar = useJulgarSemana(obraId)
  const encerrar = useEncerrarSemana(obraId)
  const reabrir = useReabrirSemana(obraId)
  const arrastar = useArrastarPendentes(obraId)

  const podeMontar = hasPermission('pdca.programacao.comprometer')
  const qcPlanilha = useQueryClient()
  const podeJulgar = hasPermission('pdca.programacao.encerrar')

  const linhas = useMemo(() => itens.data ?? [], [itens.data])

  /** Trocar de semana descarta o julgamento em edição — ele é daquele quadro, e
   *  carregá-lo para outro gravaria o julgamento na semana errada. */
  useEffect(() => {
    setJulgamentos({})
    setEmJulgamento(false)
  }, [programacao?.programacao_id])

  /** A semana comprometida abre já em modo de julgamento quando **todo** o
   *  quadro está por julgar e ela já acabou: é a reunião de segunda olhando a
   *  semana passada, e pedir um clique a mais só atrasaria o gesto. */
  useEffect(() => {
    if (programacao?.status === 'comprometida' && fim < hojeIso() && podeJulgar) {
      setEmJulgamento(true)
    }
  }, [programacao?.programacao_id, programacao?.status, fim, podeJulgar])

  const pendentesDeGravacao = useMemo(
    () => Object.entries(julgamentos).filter(([id, j]) => {
      const item = linhas.find((l) => l.item_programacao_id === Number(id))
      if (!item) return false
      return j.cumprido !== item.cumprido || j.causa !== item.causa || j.nota !== item.nota
        || (j.percentual_concluido ?? null) !== (item.percentual_concluido ?? null)
    }),
    [julgamentos, linhas],
  )

  function irPara(novoInicio: string) {
    const proximos = new URLSearchParams(params)
    proximos.set('s', novoInicio)
    setParams(proximos, { replace: true })
  }

  async function executar(acao: () => Promise<unknown>) {
    setErro(null)
    setAviso(null)
    try {
      await acao()
    } catch (e) {
      const erros = parseApiErrors(e)
      setErro(erros._form ?? erros.detail ?? Object.values(erros)[0] ?? 'Não foi possível concluir.')
    }
  }

  function payloadDoJulgamento(): JulgamentoDeItem[] {
    return pendentesDeGravacao.map(([id, j]) => ({
      item: Number(id),
      cumprido: j.cumprido,
      causa: j.causa,
      nota: j.nota,
      percentual_concluido: j.percentual_concluido ?? null,
    }))
  }

  async function gravarJulgamento() {
    if (!programacao || pendentesDeGravacao.length === 0) return
    await executar(async () => {
      const r = await julgar.mutateAsync({
        id: programacao.programacao_id, julgamentos: payloadDoJulgamento(),
      }) as { avisos?: string[] } | undefined
      setJulgamentos({})
      // Salvou. O que ficou sem causa vira aviso — só trava na hora de encerrar.
      setAviso(r?.avisos?.length ? r.avisos : null)
    })
  }

  if (semana.isLoading && !programacao) return <Loading o="a semana da obra" />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <header
        style={{
          display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
          padding: '10px 16px', borderBottom: '1px solid var(--line)',
          background: 'var(--surface)', flexShrink: 0,
        }}
      >
        <span style={{ fontSize: 15, fontWeight: 750, color: 'var(--ink)' }}>Semana</span>

        <Navegador inicio={inicio} fim={fim} aoIr={irPara} />

        {programacao && <SeloDaSemana programacao={programacao} />}

        <span style={{ flex: 1 }} />

        {/* Planilha da semana: sai o quadro; entram cartões enquanto ele é rascunho
            (as mesmas travas do "puxar para o quadro"). */}
        {programacao && (
          <>
            <BotaoExportar recurso="pdca.programacao" recorte={{ programacao: programacao.programacao_id }} />
            {podeMontar && programacao.status === 'rascunho' && (
              <WizardImportacao recurso="pdca.programacao" contexto={{ programacao: programacao.programacao_id }}
                onConcluida={() => qcPlanilha.invalidateQueries({ queryKey: ['pdca'] })} />
            )}
          </>
        )}

        <div
          style={{
            display: 'flex', gap: 2, background: 'var(--inset)',
            borderRadius: 'var(--r-sm)', padding: 2,
          }}
        >
          {([
            { chave: 'quadro' as const, rotulo: 'Quadro', icone: LayoutGrid },
            { chave: 'desempenho' as const, rotulo: 'Desempenho', icone: TrendingUp },
          ]).map(({ chave, rotulo, icone: Icone }) => (
            <button
              key={chave}
              type="button"
              onClick={() => setVista(chave)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: vista === chave ? 'var(--surface)' : 'transparent',
                border: 'none', borderRadius: 5, cursor: 'pointer',
                padding: '5px 10px', fontSize: 12, fontWeight: 650,
                fontFamily: 'inherit',
                color: vista === chave ? 'var(--ink)' : 'var(--ink-3)',
                boxShadow: vista === chave ? 'var(--shadow-sm)' : 'none',
              }}
            >
              <Icone size={13} />
              {rotulo}
            </button>
          ))}
        </div>

        {vista === 'quadro' && programacao && (
          <Verbos
            programacao={programacao}
            temCartao={linhas.length > 0}
            podeMontar={podeMontar}
            podeJulgar={podeJulgar}
            emJulgamento={emJulgamento}
            pendentes={pendentesDeGravacao.length}
            ocupado={
              comprometer.isPending || julgar.isPending || arrastar.isPending
            }
            aoAlternarJulgamento={() => setEmJulgamento((v) => !v)}
            aoGravar={gravarJulgamento}
            aoComprometer={() => executar(() =>
              comprometer.mutateAsync(programacao.programacao_id))}
            aoEncerrar={() => setEncerrando(true)}
            aoReabrir={() => setReabrindo(true)}
            aoArrastar={() => executar(() =>
              arrastar.mutateAsync(programacao.programacao_id))}
          />
        )}
      </header>

      {erro && (
        <div
          style={{
            padding: '9px 16px', background: 'var(--danger-soft)',
            color: 'var(--danger-ink)', fontSize: 12.5, lineHeight: 1.5,
            borderBottom: '1px solid var(--line)', flexShrink: 0,
          }}
          role="alert"
        >
          {erro}
        </div>
      )}

      {aviso && (
        <div
          role="status"
          style={{
            padding: '9px 16px', background: 'var(--accent-soft)',
            color: 'var(--accent-ink)', fontSize: 12.5, lineHeight: 1.5,
            borderBottom: '1px solid var(--line)', flexShrink: 0,
            display: 'flex', gap: 10, alignItems: 'flex-start',
          }}
        >
          <span style={{ flex: 1 }}>
            <strong>Salvo, com {aviso.length === 1 ? 'um aviso' : `${aviso.length} avisos`}:</strong>
            {aviso.map((a) => <span key={a} style={{ display: 'block' }}>⚠ {a}</span>)}
          </span>
          <button type="button" aria-label="Fechar aviso" onClick={() => setAviso(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}>×</button>
        </div>
      )}

      {!programacao ? (
        <SemanaPorAbrir
          inicio={inicio}
          fim={fim}
          podeMontar={podeMontar}
          abrindo={abrir.isPending}
          aoAbrir={() => executar(() => abrir.mutateAsync(inicio))}
        />
      ) : vista === 'desempenho' ? (
        <Desempenho
          obraId={obraId}
          inicio={inicio}
          programacao={programacao}
          aoEscolherSemana={irPara}
        />
      ) : (
        <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
          <EsteiraDeRestricoes
            restricoes={restricoes.data ?? []}
            atividades={gantt.data?.atividades ?? []}
            carregando={restricoes.isLoading}
          />
          <QuadroDaSemana
            programacao={programacao}
            itens={linhas}
            candidatos={candidatos.data ?? []}
            causas={causas.data ?? []}
            julgamentos={julgamentos}
            carregandoCandidatos={candidatos.isLoading}
            podeMontar={podeMontar}
            podeJulgar={podeJulgar}
            emJulgamento={emJulgamento}
            aoPuxar={(atividade, responsavel) => executar(() => puxar.mutateAsync({
              programacao: programacao.programacao_id, atividade, responsavel,
            }))}
            aoMover={(item, responsavel) => executar(() =>
              salvar.mutateAsync({ id: item, corpo: { responsavel } }))}
            aoDevolver={(item) => executar(() => devolver.mutateAsync(item))}
            aoJulgar={(item, julgamento) =>
              setJulgamentos((atual) => ({ ...atual, [item]: julgamento }))}
          />
        </div>
      )}

      {encerrando && programacao && (
        <DialogoDeEncerramento
          programacao={programacao}
          itens={linhas}
          julgamentos={julgamentos}
          salvando={julgar.isPending || encerrar.isPending}
          aoFechar={() => setEncerrando(false)}
          aoConfirmar={async ({ motivo, arrastar: levar, aceitarSemCausa }) => {
            //: Julgar **antes** de encerrar, e em duas chamadas, porque são dois
            //: atos: o julgamento pode ser salvo e revisto; o encerramento é o
            //: que faz o índice existir. O servidor recusa encerrar com item por
            //: julgar, então a ordem também é a que ele aceita.
            if (pendentesDeGravacao.length > 0) {
              await julgar.mutateAsync({
                id: programacao.programacao_id,
                julgamentos: payloadDoJulgamento(),
              })
              setJulgamentos({})
            }
            const resumo = await encerrar.mutateAsync({
              id: programacao.programacao_id, motivo, arrastar: levar, aceitarSemCausa,
            })
            setEmJulgamento(false)
            return resumo
          }}
        />
      )}

      {reabrindo && programacao && (
        <DialogoDeReabertura
          programacao={programacao}
          salvando={reabrir.isPending}
          aoFechar={() => setReabrindo(false)}
          aoConfirmar={async (motivo) => {
            await reabrir.mutateAsync({ id: programacao.programacao_id, motivo })
            setReabrindo(false)
          }}
        />
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */

function Navegador({
  inicio, fim, aoIr,
}: { inicio: string; fim: string; aoIr: (iso: string) => void }) {
  const rotulo = rotuloDaSemana(inicio)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <BotaoDeSeta titulo="Semana anterior" onClick={() => aoIr(somaDias(inicio, -7))}>
        <ChevronLeft size={15} />
      </BotaoDeSeta>
      <button
        type="button"
        onClick={() => aoIr(segundaDaSemana(hojeIso()))}
        title="Voltar à semana de hoje"
        style={{
          background: 'none', border: 'none', cursor: 'pointer', padding: '2px 4px',
          textAlign: 'left', color: 'inherit', fontFamily: 'inherit',
        }}
      >
        <div
          style={{
            fontSize: 13, fontWeight: 650, color: 'var(--ink)',
            fontFamily: 'var(--mono)',
          }}
        >
          {intervaloDaSemana(inicio, fim)}
        </div>
        <div style={{ fontSize: 10.5, color: 'var(--ink-3)' }}>{rotulo}</div>
      </button>
      <BotaoDeSeta titulo="Próxima semana" onClick={() => aoIr(somaDias(inicio, 7))}>
        <ChevronRight size={15} />
      </BotaoDeSeta>
    </div>
  )
}

function BotaoDeSeta({
  titulo, onClick, children,
}: { titulo: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={titulo}
      aria-label={titulo}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        width: 26, height: 26, borderRadius: 'var(--r-sm)', cursor: 'pointer',
        background: 'var(--surface-2)', border: '1px solid var(--line)',
        color: 'var(--ink-2)',
      }}
    >
      {children}
    </button>
  )
}

function SeloDaSemana({ programacao }: { programacao: ProgramacaoSemanal }) {
  const ppc = percentual(programacao.ppc)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <Pill
        kind={
          programacao.status === 'encerrada' ? 'good'
            : programacao.status === 'comprometida' ? 'info' : 'slate'
        }
      >
        {programacao.status_rotulo}
      </Pill>
      {ppc ? (
        <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
          cumprimento{' '}
          <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink)', fontWeight: 650 }}>
            {ppc}
          </span>
        </span>
      ) : (
        <span
          style={{ fontSize: 12, color: 'var(--ink-3)', fontStyle: 'italic' }}
          title="O índice só existe depois que a semana é encerrada e cada compromisso é julgado."
        >
          sem apuração
        </span>
      )}
      {programacao.vezes_reaberta > 0 && (
        <Pill kind="accent" title={programacao.motivo_reabertura}>
          reaberta {programacao.vezes_reaberta}×
        </Pill>
      )}
      {programacao.encerrada_antes_do_fim && (
        <Pill kind="accent" title={programacao.motivo_encerramento_antecipado}>
          encerrada antes do fim
        </Pill>
      )}
    </div>
  )
}

function Verbos({
  programacao, temCartao, podeMontar, podeJulgar, emJulgamento, pendentes,
  ocupado, aoAlternarJulgamento, aoGravar, aoComprometer, aoEncerrar, aoReabrir,
  aoArrastar,
}: {
  programacao: ProgramacaoSemanal
  temCartao: boolean
  podeMontar: boolean
  podeJulgar: boolean
  emJulgamento: boolean
  pendentes: number
  ocupado: boolean
  aoAlternarJulgamento: () => void
  aoGravar: () => void
  aoComprometer: () => void
  aoEncerrar: () => void
  aoReabrir: () => void
  aoArrastar: () => void
}) {
  if (programacao.status === 'rascunho') {
    if (!podeMontar) {
      return <SemVerbo o="assumir a semana" permissao="pdca.programacao.comprometer" />
    }
    return (
      <Btn
        tam="sm"
        variant="primary"
        onClick={aoComprometer}
        disabled={ocupado || !temCartao}
        title={temCartao
          ? 'Fecha a lista: depois disto o quadro não recebe cartão novo.'
          : 'Puxe pelo menos um serviço do plano para o quadro.'}
      >
        <ClipboardCheck size={13} />
        A equipe assume
      </Btn>
    )
  }

  if (programacao.status === 'comprometida') {
    if (!podeJulgar) {
      return <SemVerbo o="encerrar a semana" permissao="pdca.programacao.encerrar" />
    }
    return (
      <div style={{ display: 'flex', gap: 6 }}>
        <Btn tam="sm" onClick={aoAlternarJulgamento}>
          <Gavel size={13} />
          {emJulgamento ? 'Sair do julgamento' : 'Julgar o quadro'}
        </Btn>
        {pendentes > 0 && (
          <Btn tam="sm" onClick={aoGravar} disabled={ocupado}>
            <Save size={13} />
            Salvar {pendentes}
          </Btn>
        )}
        <Btn tam="sm" variant="primary" onClick={aoEncerrar} disabled={ocupado}>
          Encerrar a semana
        </Btn>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', gap: 6 }}>
      <Btn
        tam="sm"
        onClick={aoArrastar}
        disabled={ocupado}
        title="Leva o que não saiu para o quadro da semana seguinte, em rascunho. Rodar duas vezes não duplica cartão."
      >
        Levar pendências adiante
      </Btn>
      {podeJulgar && (
        <Btn tam="sm" onClick={aoReabrir} disabled={ocupado}>
          <RotateCcw size={13} />
          Reabrir
        </Btn>
      )}
    </div>
  )
}

function SemVerbo({ o, permissao }: { o: string; permissao: string }) {
  return (
    <span
      title={`Requer a permissão “${permissao}”. Peça ao administrador da empresa.`}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        fontSize: 12, color: 'var(--ink-3)', cursor: 'not-allowed',
      }}
    >
      <Lock size={12} />
      Você não pode {o}
    </span>
  )
}

function SemanaPorAbrir({
  inicio, fim, podeMontar, abrindo, aoAbrir,
}: {
  inicio: string
  fim: string
  podeMontar: boolean
  abrindo: boolean
  aoAbrir: () => void
}) {
  return (
    <div style={{ padding: '26px 26px', maxWidth: 620 }}>
      <Empty>
        <span style={{ lineHeight: 1.65 }}>
          A semana de{' '}
          <strong style={{ color: 'var(--ink-2)' }}>{intervaloDaSemana(inicio, fim)}</strong>
          {' '}ainda não tem quadro. Abrir cria a folha em branco — o time puxa do
          plano o que assume, e só depois assina embaixo.
        </span>
        {podeMontar ? (
          <Btn variant="primary" onClick={aoAbrir} disabled={abrindo}>
            {abrindo ? 'Abrindo…' : 'Abrir o quadro desta semana'}
          </Btn>
        ) : (
          <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
            Quem abre o quadro é quem monta a semana — exige a permissão
            “pdca.programacao.comprometer”.
          </span>
        )}
      </Empty>
    </div>
  )
}

function Desempenho({
  obraId, inicio, programacao, aoEscolherSemana,
}: {
  obraId: number
  inicio: string
  programacao: ProgramacaoSemanal
  aoEscolherSemana: (iso: string) => void
}) {
  const serie = useSeriePpc(obraId)
  const ranking = useRankingDeCausas(obraId)

  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '20px 24px' }}>
      <div
        style={{
          display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 1080,
        }}
      >
        <section>
          <SectionHead sub="Quanto do que a equipe assumiu saiu, semana a semana">
            Cumprimento da programação
          </SectionHead>
          <Card>
            {serie.isLoading ? (
              <p style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Carregando a série…</p>
            ) : (
              <SerieDePpc
                serie={serie.data?.serie ?? []}
                escolhida={inicio}
                aoEscolher={aoEscolherSemana}
              />
            )}
          </Card>
        </section>

        <section>
          <SectionHead sub="Cumulativo — o que é difícil nesta obra, e não o que está atrasado hoje">
            Por que os compromissos não saem
          </SectionHead>
          <Card>
            {ranking.isLoading ? (
              <p style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Carregando as causas…</p>
            ) : ranking.data ? (
              <RankingDeCausas ranking={ranking.data} />
            ) : null}
          </Card>
        </section>

        <AtaDaReuniao obraId={obraId} programacao={programacao} />
      </div>
    </div>
  )
}

/** **A ata da reunião** — o que foi combinado e não cabe em cartão nenhum.
 *
 *  Fica aqui, ao lado do índice e das causas, porque é aqui que a reunião
 *  termina: olha-se o número, discute-se a causa, e escreve-se o que ficou
 *  decidido. É o único campo do documento da semana que muda por `PATCH`; todo
 *  o resto muda por verbo. */
function AtaDaReuniao({
  obraId, programacao,
}: { obraId: number; programacao: ProgramacaoSemanal }) {
  const anotar = useAnotarSemana(obraId)
  const [texto, setTexto] = useState(programacao.nota)
  const [erro, setErro] = useState<string | null>(null)

  //: A nota é do documento, e trocar de semana tem de trocar o texto — sem
  //: isto, a ata da semana passada apareceria na tela da semana seguinte e
  //: seria gravada nela ao primeiro clique.
  useEffect(() => {
    setTexto(programacao.nota)
    setErro(null)
  }, [programacao.programacao_id, programacao.nota])

  const sujo = texto !== programacao.nota

  async function salvar() {
    setErro(null)
    try {
      await anotar.mutateAsync({ id: programacao.programacao_id, nota: texto })
    } catch (e) {
      const erros = parseApiErrors(e)
      setErro(erros.nota ?? erros._form ?? erros.detail ?? 'Não foi possível gravar a ata.')
    }
  }

  return (
    <section>
      <SectionHead sub="O que ficou combinado e não cabe em cartão nenhum">
        Ata da reunião
      </SectionHead>
      <Card>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {erro && (
            <div
              role="alert"
              style={{
                fontSize: 12.5, padding: '9px 11px', borderRadius: 'var(--r-sm)',
                background: 'var(--danger-soft)', color: 'var(--danger-ink)',
                lineHeight: 1.5,
              }}
            >
              {erro}
            </div>
          )}
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={4}
            placeholder="Ex.: o fornecedor confirmou a entrega para quarta; a equipe da laje passa para a torre B na semana que vem"
            style={{
              width: '100%', padding: '10px 12px', borderRadius: 8, fontSize: 13.5,
              border: '1px solid var(--line)', background: 'var(--surface)',
              color: 'var(--ink)', fontFamily: 'inherit', resize: 'vertical',
            }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Btn
              tam="sm"
              variant={sujo ? 'primary' : 'ghost'}
              onClick={salvar}
              disabled={!sujo || anotar.isPending}
            >
              {anotar.isPending ? 'Gravando…' : 'Gravar a ata'}
            </Btn>
            <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
              {sujo
                ? 'Há mudanças não gravadas.'
                : programacao.nota
                  ? 'Gravada.'
                  : 'Nada escrito ainda.'}
            </span>
          </div>
        </div>
      </Card>
    </section>
  )
}

function DialogoDeReabertura({
  programacao, salvando, aoFechar, aoConfirmar,
}: {
  programacao: ProgramacaoSemanal
  salvando: boolean
  aoFechar: () => void
  aoConfirmar: (motivo: string) => Promise<void>
}) {
  const [motivo, setMotivo] = useState('')
  const [erro, setErro] = useState<string | null>(null)

  async function confirmar() {
    setErro(null)
    try {
      await aoConfirmar(motivo)
    } catch (e) {
      const erros = parseApiErrors(e)
      setErro(erros._form ?? erros.motivo ?? erros.detail ?? 'Não foi possível reabrir.')
    }
  }

  return (
    <Modal
      titulo="Reabrir a semana"
      onClose={aoFechar}
      largura={470}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Cancelar</Btn>
          <Btn variant="primary" onClick={confirmar} disabled={salvando}>
            {salvando ? 'Reabrindo…' : 'Reabrir'}
          </Btn>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {erro && (
          <div
            style={{
              fontSize: 12.5, padding: '9px 11px', borderRadius: 'var(--r-sm)',
              background: 'var(--danger-soft)', color: 'var(--danger-ink)',
              lineHeight: 1.5,
            }}
            role="alert"
          >
            {erro}
          </div>
        )}

        <p style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.6, margin: 0 }}>
          A semana volta a aceitar julgamento, e o cumprimento de{' '}
          <strong>{percentual(programacao.ppc) ?? 'sem apuração'}</strong> deixa
          de valer até ela ser encerrada de novo. O índice já foi lido por
          alguém — a reabertura fica marcada na série para quem lembrar do número
          antigo saber o que houve.
        </p>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span
            style={{
              fontSize: 10.5, letterSpacing: '0.09em', textTransform: 'uppercase',
              color: 'var(--ink-3)', fontWeight: 700,
            }}
          >
            Por que está sendo reaberta
          </span>
          <textarea
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            rows={3}
            autoFocus
            placeholder="Ex.: a laje do 3º foi concretada na sexta e ninguém avisou na reunião"
            style={{
              width: '100%', padding: '8px 10px', borderRadius: 8, fontSize: 13.5,
              border: '1px solid var(--line)', background: 'var(--surface)',
              color: 'var(--ink)', fontFamily: 'inherit', resize: 'vertical',
            }}
          />
        </label>

        <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
          Encerrada em {programacao.encerrada_em ? dateToBR(programacao.encerrada_em.slice(0, 10)) : '—'}
          {programacao.encerrada_por && ` por ${programacao.encerrada_por}`}.
        </span>
      </div>
    </Modal>
  )
}
