import { useState } from 'react'
import { ArrowRight, CheckCircle2 } from 'lucide-react'
import { Btn, Modal, Num, Pill } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { percentual } from '../formato'
import { hojeIso, intervaloDaSemana } from '../semana'
import type { ItemProgramacao, ProgramacaoSemanal, ResumoDoPpc } from '../types'
import type { Julgamento } from './QuadroDaSemana'

/** **O ato do fim da semana.** Julgar o quadro inteiro numa transação, e só
 *  então encerrar — é a ordem que a reunião segue, e é a ordem em que o
 *  servidor aceita.
 *
 *  O diálogo não decide nada: ele mostra o que vai acontecer e relata o que o
 *  servidor respondeu. Quem recusa encerrar com item por julgar, quem exige a
 *  causa e quem cobra motivo na semana que ainda não acabou é o backend — a
 *  tela mostra a frase que ele devolveu, que é a mesma que a API devolveria por
 *  qualquer outra porta. */
export function DialogoDeEncerramento({
  programacao, itens, julgamentos, salvando, aoFechar, aoConfirmar,
}: {
  programacao: ProgramacaoSemanal
  itens: ItemProgramacao[]
  julgamentos: Record<number, Julgamento>
  salvando: boolean
  aoFechar: () => void
  aoConfirmar: (opcoes: { motivo: string; arrastar: boolean; aceitarSemCausa?: boolean }) => Promise<ResumoDoPpc>
}) {
  const [motivo, setMotivo] = useState('')
  const [arrastar, setArrastar] = useState(true)
  const [erros, setErros] = useState<FieldErrors>({})
  const [resumo, setResumo] = useState<ResumoDoPpc | null>(null)
  /** O aviso do servidor antes de bloquear: o que não saiu está sem causa. Quem
   *  tem a alçada (`pode`) decide seguir; quem não tem só vê o que falta. */
  const [semCausaAviso, setSemCausaAviso] = useState<
    { itens: { atividade: string; percentual: string }[]; pode: boolean } | null
  >(null)

  const decididos = itens.map((item) => ({
    item,
    cumprido: julgamentos[item.item_programacao_id]?.cumprido ?? item.cumprido,
    causa: julgamentos[item.item_programacao_id]?.causa ?? item.causa,
  }))
  const sairam = decididos.filter((d) => d.cumprido === true)
  const naoSairam = decididos.filter((d) => d.cumprido === false)
  const porJulgar = decididos.filter((d) => d.cumprido == null)
  const semCausa = naoSairam.filter((d) => d.causa == null)

  /** **Só decide se a frase de ajuda aparece, e nada mais.** Quem recusa o
   *  encerramento antecipado — e quem sabe se a permissão existe — é o
   *  servidor, na hora do POST. Repetir a regra aqui criaria duas versões dela,
   *  e a do navegador envelheceria primeiro. */
  const aindaNaoAcabou = programacao.semana_fim >= hojeIso()

  async function confirmar(aceitarSemCausa = false) {
    setErros({})
    try {
      setResumo(await aoConfirmar({ motivo, arrastar, aceitarSemCausa }))
      setSemCausaAviso(null)
    } catch (e) {
      const dados = (e as { response?: { data?: { codigo?: string; sem_causa?: { atividade: string; percentual: string }[]; pode_aceitar?: boolean } } })
        .response?.data
      if (dados?.codigo === 'sem_causa') {
        setSemCausaAviso({ itens: dados.sem_causa ?? [], pode: !!dados.pode_aceitar })
        return
      }
      setSemCausaAviso(null)
      setErros(parseApiErrors(e))
    }
  }

  if (resumo) return <ResultadoDoEncerramento resumo={resumo} aoFechar={aoFechar} />

  return (
    <Modal
      titulo="Encerrar a semana"
      onClose={aoFechar}
      largura={560}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Ainda não</Btn>
          {semCausaAviso?.pode && (
            <Btn onClick={() => void confirmar(true)} disabled={salvando}>
              Encerrar assim mesmo
            </Btn>
          )}
          <Btn variant="primary" onClick={() => void confirmar(false)} disabled={salvando}>
            {salvando ? 'Encerrando…' : 'Encerrar'}
          </Btn>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <FormErrorBanner errors={erros} />

        {semCausaAviso && (
          <Aviso tom="accent">
            <strong>
              {semCausaAviso.itens.length === 1
                ? 'Um compromisso que não saiu está sem causa.'
                : `${semCausaAviso.itens.length} compromissos que não saíram estão sem causa.`}
            </strong>{' '}
            A causa é de onde sai o ranking que muda a obra.{' '}
            {semCausaAviso.pode
              ? 'Você pode encerrar assim mesmo: eles entram no ranking como «Sem causa informada».'
              : 'Informe a causa de cada um para encerrar — ou peça a quem tem a alçada de encerrar sem causa.'}
            <Lista nomes={semCausaAviso.itens.map((i) => `${i.atividade} (${Number(i.percentual).toFixed(0)}%)`)} />
          </Aviso>
        )}

        <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
          Semana de{' '}
          <strong style={{ color: 'var(--ink-2)', fontWeight: 650 }}>
            {intervaloDaSemana(programacao.semana_inicio, programacao.semana_fim)}
          </strong>
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <Contador rotulo="saíram" valor={sairam.length} tom="var(--good-ink)" />
          <Contador rotulo="não saíram" valor={naoSairam.length} tom="var(--danger-ink)" />
          <Contador rotulo="por julgar" valor={porJulgar.length} tom="var(--ink-3)" />
        </div>

        {porJulgar.length > 0 && (
          <Aviso tom="danger">
            {porJulgar.length === 1
              ? 'Um compromisso ainda não foi julgado.'
              : `${porJulgar.length} compromissos ainda não foram julgados.`}
            {' '}Diga de cada um se saiu ou não — o índice sai desse julgamento,
            e um quadro meio julgado produz um número cujo divisor ninguém sabe.
            <Lista nomes={porJulgar.map((d) => d.item.atividade_nome)} />
          </Aviso>
        )}

        {semCausa.length > 0 && (
          <Aviso tom="danger">
            {semCausa.length === 1
              ? 'Um compromisso está marcado como não cumprido e ainda não tem causa.'
              : `${semCausa.length} compromissos não cumpridos ainda estão sem causa.`}
            {' '}É dessa resposta que sai o que mudar na obra.
            <Lista nomes={semCausa.map((d) => d.item.atividade_nome)} />
          </Aviso>
        )}

        {aindaNaoAcabou && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label
              style={{
                fontSize: 10.5, letterSpacing: '0.09em', textTransform: 'uppercase',
                color: 'var(--ink-3)', fontWeight: 700,
              }}
            >
              Por que encerrar antes do fim da semana
            </label>
            <textarea
              value={motivo}
              onChange={(e) => {
                setMotivo(e.target.value)
                setErros((p) => ({ ...p, motivo: '', detail: '' }))
              }}
              rows={2}
              placeholder="Ex.: obra para na quinta pelo feriado prolongado"
              style={{
                width: '100%', padding: '8px 10px', borderRadius: 8, fontSize: 13.5,
                border: '1px solid var(--line)', background: 'var(--surface)',
                color: 'var(--ink)', fontFamily: 'inherit', resize: 'vertical',
              }}
            />
            <span style={{ fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
              A semana termina em {dateToBR(programacao.semana_fim)}. Fechar
              antes marca o ponto na série como apurado mais cedo — é a frase que
              a próxima reunião lê para entender aquele número.
            </span>
            <FieldError msg={erros.motivo} />
          </div>
        )}

        <label
          style={{
            display: 'flex', alignItems: 'flex-start', gap: 9, cursor: 'pointer',
            padding: '10px 12px', background: 'var(--inset)',
            borderRadius: 'var(--r-sm)',
          }}
        >
          <input
            type="checkbox"
            checked={arrastar}
            onChange={(e) => setArrastar(e.target.checked)}
            style={{ marginTop: 2 }}
          />
          <span style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>
            <strong style={{ color: 'var(--ink)', fontWeight: 650 }}>
              Levar o que não saiu para a semana que vem
            </strong>
            <br />
            Os compromissos falhados nascem em rascunho no quadro seguinte, com o
            que ficou por fazer e o contador de semanas de pé — que é o que a
            reunião precisa ver antes do índice.
          </span>
        </label>
      </div>
    </Modal>
  )
}

function ResultadoDoEncerramento({
  resumo, aoFechar,
}: { resumo: ResumoDoPpc; aoFechar: () => void }) {
  const arrasto = resumo.arrasto
  const prometido = percentual(resumo.pontos_previstos)
  const feito = percentual(resumo.pontos_apontados)

  return (
    <Modal
      titulo="Semana encerrada"
      onClose={aoFechar}
      largura={500}
      rodape={
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Btn variant="primary" onClick={aoFechar}>Fechar</Btn>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 15 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {/* **O ícone diz que a semana fechou, não que ela foi boa.** Em verde
              ao lado de "0%" ele lia como parabéns por uma semana em que nada
              saiu — e o índice é o que julga o resultado, não a decoração. */}
          <CheckCircle2 size={30} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
          <div>
            <div
              className="num"
              style={{ fontSize: 30, fontWeight: 700, color: 'var(--ink)', lineHeight: 1 }}
            >
              {percentual(resumo.ppc) ?? '—'}
            </div>
            <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 3 }}>
              {resumo.cumpridos} de {resumo.comprometidos} compromissos cumpridos
            </div>
          </div>
        </div>

        {/* O denominador, dito em voz alta: quem lê o índice vê em cima de quê
            ele foi feito, e não precisa confiar no número sozinho. */}
        <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>
          {resumo.peso_bases.map((base) => (
            <Pill key={base} kind="slate" title="De onde saiu o peso de cada compromisso.">
              peso por {base}
            </Pill>
          ))}
          {resumo.sem_peso > 0 && (
            <Pill
              kind="info"
              title="Compromissos sem como ser pesados — marco, serviço sem duração nem vínculo. Contam no quadro e ficam fora da divisão."
            >
              {resumo.sem_peso} fora da divisão
            </Pill>
          )}
          {resumo.encerrada_antes_do_fim && (
            <Pill kind="accent">encerrada antes do fim</Pill>
          )}
        </div>

        {/* **Cada metade só aparece se existir.** Muito compromisso de LPS é
            binário ("concretar a laje do 4º") e não tem número de avanço — o
            travessão no meio da frase ("a equipe prometeu — de avanço") não é
            dado honesto, é dado faltando com aparência de dado. */}
        {(prometido || feito) && (
          <div
            style={{
              fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.6,
              padding: '10px 12px', background: 'var(--inset)',
              borderRadius: 'var(--r-sm)',
            }}
          >
            {prometido && feito && (
              <>
                A equipe prometeu <Num size={12.5}>{prometido}</Num> de avanço e o
                campo apontou <Num size={12.5}>{feito}</Num>.
              </>
            )}
            {prometido && !feito && (
              <>
                A equipe prometeu <Num size={12.5}>{prometido}</Num> de avanço, e
                ninguém apontou avanço nesta semana.
              </>
            )}
            {!prometido && feito && (
              <>
                O campo apontou <Num size={12.5}>{feito}</Num> de avanço nesta
                semana. Nenhum compromisso trazia número de quanto ia andar.
              </>
            )}
            <br />
            <span style={{ color: 'var(--ink-3)', fontSize: 11.5 }}>
              Estes números não entram no índice: ele pergunta se o compromisso
              saiu, e não o quanto andou.
            </span>
          </div>
        )}

        {arrasto && arrasto.arrastados > 0 && (
          <div
            style={{
              display: 'flex', alignItems: 'flex-start', gap: 9,
              fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55,
            }}
          >
            <ArrowRight size={15} style={{ color: 'var(--ink-3)', flexShrink: 0, marginTop: 2 }} />
            <span>
              {arrasto.arrastados} compromisso{arrasto.arrastados > 1 ? 's' : ''} que
              não saiu foi levado para a semana que vem, em rascunho.
            </span>
          </div>
        )}
        {arrasto?.destino_fechado && (
          <Aviso tom="accent">
            A semana seguinte já foi assumida, então nada foi levado para lá —
            acrescentar compromisso a um quadro já comprometido é escrever a
            aposta depois do resultado.
          </Aviso>
        )}
      </div>
    </Modal>
  )
}

function Contador({ rotulo, valor, tom }: { rotulo: string; valor: number; tom: string }) {
  return (
    <div
      style={{
        flex: 1, padding: '10px 12px', background: 'var(--inset)',
        borderRadius: 'var(--r-sm)',
      }}
    >
      <div className="num" style={{ fontSize: 21, fontWeight: 700, color: tom, lineHeight: 1 }}>
        {valor}
      </div>
      <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 3 }}>{rotulo}</div>
    </div>
  )
}

function Aviso({ tom, children }: { tom: 'danger' | 'accent'; children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: 12.5, lineHeight: 1.55, padding: '10px 12px',
        borderRadius: 'var(--r-sm)', background: `var(--${tom}-soft)`,
        color: `var(--${tom}-ink)`,
      }}
    >
      {children}
    </div>
  )
}

/** Os nomes do que falta, e não só a contagem: "3 por julgar" manda procurar;
 *  os três nomes mandam ir até eles. */
function Lista({ nomes }: { nomes: string[] }) {
  const mostrados = nomes.slice(0, 4)
  return (
    <span style={{ display: 'block', marginTop: 5, fontSize: 11.5, opacity: 0.9 }}>
      {mostrados.join(' · ')}
      {nomes.length > mostrados.length && ` · e mais ${nomes.length - mostrados.length}`}
    </span>
  )
}
