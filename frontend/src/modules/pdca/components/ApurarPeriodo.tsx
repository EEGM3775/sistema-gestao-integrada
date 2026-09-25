import { useEffect, useState } from 'react'
import { CalendarRange, Eye } from 'lucide-react'
import { Btn, Card, Loading, Num, Pill, SectionHead } from '@/components/malha'
import { dateToBR, maxCalendarioISO, minCalendarioISO } from '@/utils/dates'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import { GradeDeMedicao } from './GradeDeMedicao'
import type { LinhaDeContrato, PropostaDeMedicao } from '../types'

/** **Apurar** — a medição nasce do avanço apontado, não da digitação.
 *
 *  A prévia é **somente leitura por desenho**, e a tela diz isso: número é
 *  texto, não `input` desabilitado (convenções §10). Abrir o boletim é um
 *  segundo gesto, deliberado — ver a proposta abrindo uma medição encheria o
 *  contrato de rascunhos que alguém teria de apagar depois. */
export function ApurarPeriodo({
  contrato, previa, carregando, ocupado, podeApurar,
  aoVer, aoAbrirBoletim,
}: {
  contrato: LinhaDeContrato
  previa: PropostaDeMedicao | undefined
  carregando: boolean
  ocupado?: boolean
  podeApurar: boolean
  aoVer: (inicio: string, fim: string) => void
  aoAbrirBoletim: (inicio: string, fim: string) => void
}) {
  const sugerido = contrato.saldo.periodo_sugerido
  const [inicio, setInicio] = useState(sugerido.inicio)
  const [fim, setFim] = useState(sugerido.fim)

  /** Trocar de contrato reancora o período: manter as datas do anterior
   *  produziria uma prévia de um intervalo que não tem nada a ver com este. */
  useEffect(() => {
    setInicio(sugerido.inicio)
    setFim(sugerido.fim)
  }, [contrato.contrato, sugerido.inicio, sugerido.fim])

  const invertido = fim < inicio
  const bruto = previa
    ? previa.linhas.reduce(
      (soma, linha) =>
        soma + Math.round(
          apiDecimalToCents(linha.preco_unitario)
          * Number(linha.quantidade_proposta || '0'),
        ),
      0,
    )
    : 0

  return (
    <section>
      <SectionHead
        sub={
          sugerido.ultima_medicao
            ? `A última medição fechou em ${dateToBR(sugerido.ultima_medicao.periodo_fim)} — a corrente continua no dia seguinte.`
            : 'Ainda não houve medição neste contrato: o período começa na vigência.'
        }
      >
        Apurar um período
      </SectionHead>

      <Card>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <Data rotulo="De" valor={inicio} aoMudar={setInicio} />
          <Data rotulo="Até" valor={fim} aoMudar={setFim} />

          <Btn
            tam="sm"
            disabled={invertido || carregando}
            onClick={() => aoVer(inicio, fim)}
          >
            <Eye size={13} />
            {carregando ? 'Calculando…' : 'Ver a prévia'}
          </Btn>

          {podeApurar && (
            <Btn
              tam="sm"
              variant="primary"
              disabled={invertido || ocupado}
              onClick={() => aoAbrirBoletim(inicio, fim)}
            >
              Abrir o boletim deste período
            </Btn>
          )}

          <span style={{ flex: 1 }} />

          {sugerido.lacuna_dias > 0 && (
            <Pill
              kind="info"
              title="Dias entre o início da vigência e o começo deste período"
            >
              <CalendarRange size={11} />
              {sugerido.lacuna_dias} dias de vigência antes deste período
            </Pill>
          )}
        </div>

        {invertido && (
          <p style={{ margin: '10px 0 0', fontSize: 12.5, color: 'var(--danger-ink)' }}>
            A data final é anterior à inicial — inverta as duas para o período
            fazer sentido.
          </p>
        )}
      </Card>

      {carregando && (
        <div style={{ marginTop: 12 }}>
          <Loading o="a prévia do período" />
        </div>
      )}

      {previa && !carregando && (
        <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div
            style={{
              display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap',
              fontSize: 12.5, color: 'var(--ink-3)',
            }}
          >
            <strong style={{ color: 'var(--ink-2)' }}>
              Prévia de {dateToBR(previa.periodo.inicio)} a {dateToBR(previa.periodo.fim)}
            </strong>
            {/* **Prévia, e a soma é da prévia.** Não há boletim, logo não há
                retenção aplicada nem desconto lançado: o número é o bruto do
                que se mediria, e a tela diz isso em vez de chamá-lo de total. */}
            <span>
              somaria{' '}
              <Num size={12.5} tone="var(--ink)" style={{ display: 'inline-block' }}>
                {formatBRL(bruto)}
              </Num>{' '}
              de bruto, antes de retenção e descontos
            </span>
          </div>

          <GradeDeMedicao
            contexto={previa}
            somenteLeitura
            motivoDaLeitura={
              'é uma simulação do período, e não um boletim. Para lançar '
              + 'quantidade, abra o boletim deste período.'
            }
          />
        </div>
      )}
    </section>
  )
}

function Data({
  rotulo, valor, aoMudar,
}: { rotulo: string; valor: string; aoMudar: (v: string) => void }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span
        style={{
          fontSize: 10.5, letterSpacing: '0.07em', textTransform: 'uppercase',
          color: 'var(--ink-3)', fontWeight: 700,
        }}
      >
        {rotulo}
      </span>
      <input
        type="date"
        value={valor}
        /** A faixa do calendário é uma só na plataforma: 1900–2100. */
        min={minCalendarioISO}
        max={maxCalendarioISO}
        onChange={(e) => aoMudar(e.target.value)}
        style={{
          padding: '7px 9px', borderRadius: 8, fontSize: 12.5,
          border: '1px solid var(--line)', background: 'var(--surface)',
          color: 'var(--ink)', fontFamily: 'var(--mono)',
        }}
      />
    </label>
  )
}
