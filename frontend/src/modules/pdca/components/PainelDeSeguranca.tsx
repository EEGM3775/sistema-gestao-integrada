import { Link } from 'react-router-dom'
import { ArrowUpRight, HardHat, Lock } from 'lucide-react'
import { Card, Empty, Num, SectionHead, Spinner } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { dateToBR } from '@/utils/dates'
import { emDias } from '../formato'
import { useEpiVencido } from '../hooks'
import type { FrenteInterditada, IndicadoresDeSsma } from '../types'

/** **Os números que o sistema sabe, e os dois que ele não sabe.**
 *
 *  Taxa de frequência e de gravidade dividem por homem-hora, que ainda não é
 *  apropriado: vêm nulas, e a tela escreve a frase do servidor no lugar do
 *  número. "0,00" numa tela de segurança diria que a obra é segura quando o
 *  que houve foi ninguém medir.
 *
 *  O que se entrega inteiro é o numerador e a pirâmide — quantos avisos para
 *  cada acidente diz se a obra registra o que avisa antes ou só o que sangra. */
export function PainelDeSeguranca({
  indicadores, interditadas, obraId,
}: {
  indicadores: IndicadoresDeSsma
  interditadas: FrenteInterditada[]
  obraId: number
}) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <SectionHead>Os números da obra</SectionHead>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10 }}>
        <Indicador rotulo="Acidentes" valor={indicadores.acidentes}
          nota={`${indicadores.com_afastamento} com afastamento · ${indicadores.obitos} óbito${indicadores.obitos === 1 ? '' : 's'}`} />
        <Indicador rotulo="Quase-acidentes" valor={indicadores.quase_acidentes}
          nota={indicadores.avisos_por_acidente != null
            ? `${indicadores.avisos_por_acidente.toLocaleString('pt-BR')} avisos por acidente`
            : 'sem acidente para comparar'} />
        <Indicador rotulo="Dias perdidos" valor={indicadores.dias_perdidos}
          nota={indicadores.dias_debitados ? `${indicadores.dias_debitados} debitados` : undefined} />
        <Indicador rotulo="Diálogos encerrados" valor={indicadores.dds_encerrados}
          nota="o que a obra faz antes" />
      </div>

      {indicadores.nao_classificadas > 0 && (
        <div style={{ fontSize: 12.5, color: 'var(--accent-ink)' }}>
          {indicadores.nao_classificadas}{' '}
          {indicadores.nao_classificadas === 1 ? 'ocorrência ainda não classificada fica' : 'ocorrências ainda não classificadas ficam'}{' '}
          fora da contagem de afastamento até alguém classificar.
        </div>
      )}

      <Card style={{ background: 'var(--inset)' }}>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          <TaxaSemApuracao rotulo="Taxa de frequência" />
          <TaxaSemApuracao rotulo="Taxa de gravidade" />
        </div>
        <p style={{ margin: '8px 0 0', fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.6 }}>
          {indicadores.taxas_indisponiveis_porque}
        </p>
      </Card>

      <FrentesInterditadas interditadas={interditadas} obraId={obraId} />
      <EpiVencido obraId={obraId} />
    </section>
  )
}

function Indicador({ rotulo, valor, nota }: { rotulo: string; valor: number; nota?: string }) {
  return (
    <Card>
      <div style={rotuloPequeno}>{rotulo}</div>
      <Num size={22} tone="var(--ink)" style={{ display: 'block', marginTop: 4 }}>{valor}</Num>
      {nota && <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>{nota}</div>}
    </Card>
  )
}

function TaxaSemApuracao({ rotulo }: { rotulo: string }) {
  return (
    <div>
      <div style={rotuloPequeno}>{rotulo}</div>
      <div style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 4, fontStyle: 'italic' }}>sem apuração</div>
    </div>
  )
}

const rotuloPequeno = {
  fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700,
} as const

/** A frente parada por uma ocorrência. Não é decisão desta tela — liberar é
 *  remover a restrição, na semana —, mas é o que impede encerrar a
 *  ocorrência que a abriu, e por isso aparece aqui. */
function FrentesInterditadas({
  interditadas, obraId,
}: { interditadas: FrenteInterditada[]; obraId: number }) {
  if (interditadas.length === 0) return null
  return (
    <div>
      <div style={{ ...rotuloPequeno, marginBottom: 7, display: 'flex', gap: 6, alignItems: 'center' }}>
        <Lock size={12} /> Frentes interditadas
      </div>
      <Card pad={false} style={{ overflow: 'hidden' }}>
        {interditadas.map((f) => {
          const dias = f.desde ? Math.floor((Date.now() - new Date(`${f.desde}T12:00:00`).getTime()) / 86_400_000) : null
          return (
            <Link
              key={f.restricao}
              to={`/app/pdca/o/${obraId}/seguranca?ocorrencia=${f.ocorrencia}`}
              style={{
                display: 'flex', gap: 10, padding: '10px 13px', borderTop: '1px solid var(--line-2)',
                textDecoration: 'none', color: 'inherit', alignItems: 'flex-start',
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, color: 'var(--ink)' }}>
                  {f.atividade_nome || 'Serviço sem nome'}{f.local_rotulo && ` · ${f.local_rotulo}`}
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
                  {f.tipo_rotulo.split(' (')[0]} — {f.descricao}
                </div>
              </div>
              {dias != null && (
                <span style={{ fontSize: 11.5, color: 'var(--ink-3)', flexShrink: 0 }}>
                  {dias <= 0 ? 'desde hoje' : `há ${emDias(dias)}`}
                </span>
              )}
              <ArrowUpRight size={13} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
            </Link>
          )
        })}
      </Card>
      <p style={{ margin: '6px 2px 0', fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
        Quando o risco cessar, quem responde pela obra remove a restrição na
        Semana — é o que libera o serviço e deixa encerrar a ocorrência.
      </p>
    </div>
  )
}

/** **O EPI é do SIL**, e a leitura cobra a permissão de lá. Sem o módulo ou
 *  sem `sil.epi.view`, a indisponibilidade é dita — uma lista vazia se leria
 *  como "está tudo em dia". */
function EpiVencido({ obraId }: { obraId: number }) {
  const { hasPermission, hasModule } = useAuth()
  const temSil = hasModule('sil')
  const pode = temSil && hasPermission('sil.epi.view')
  const epi = useEpiVencido(obraId, pode)

  return (
    <div>
      <div style={{ ...rotuloPequeno, marginBottom: 7, display: 'flex', gap: 6, alignItems: 'center' }}>
        <HardHat size={12} /> EPI vencido nesta obra
      </div>
      {!temSil ? (
        <Empty>
          A ficha de EPI mora no módulo de Estoque, que a empresa não contratou.
          Sem ele, o sistema não sabe quem está com EPI vencido.
        </Empty>
      ) : !pode ? (
        <Empty>
          Ler a ficha de EPI exige a permissão do Estoque
          (<code style={{ fontFamily: 'var(--mono)', fontSize: 11.5 }}>sil.epi.view</code>).
          Quem libera é o administrador da empresa.
        </Empty>
      ) : epi.isLoading ? (
        <div style={{ padding: 12 }}><Spinner size={18} /></div>
      ) : epi.isError || !epi.data ? (
        <Empty>Não foi possível ler a ficha de EPI agora.</Empty>
      ) : !epi.data.disponivel ? (
        <Empty>{epi.data.motivo}</Empty>
      ) : epi.data.vencidos.length === 0 ? (
        <Empty>Ninguém com EPI vencido entre as entregas desta obra.</Empty>
      ) : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          {epi.data.vencidos.map((v) => (
            <div key={v.entrega} style={{ display: 'flex', gap: 10, padding: '9px 13px', borderTop: '1px solid var(--line-2)', fontSize: 12.5 }}>
              <span style={{ flex: 1, color: 'var(--ink)' }}>{v.colaborador}</span>
              <span style={{ flex: 1, color: 'var(--ink-2)' }}>{v.item}{v.ca_numero && ` · CA ${v.ca_numero}`}</span>
              <span style={{ color: 'var(--danger-ink)', flexShrink: 0 }}>
                {v.ca_validade && `CA vencido em ${dateToBR(v.ca_validade)}`}
                {v.ca_validade && v.troca_prevista && ' · '}
                {v.troca_prevista && `troca era ${dateToBR(v.troca_prevista)}`}
              </span>
            </div>
          ))}
        </Card>
      )}
    </div>
  )
}
