import { useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowUpRight, CheckCircle2, ChevronDown, ChevronRight, Clock } from 'lucide-react'
import { Card, Empty, Num, Pill, SectionHead } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import { emDias } from '../formato'
import { DEGRAUS, POSTO_DA_ORIGEM, enderecoDoDocumento } from '../postos'
import { SemPermissaoAviso } from './SemPermissaoAviso'
import type { Consequencia, FaixaDaFila, FilaDoDia, LinhaDaFila } from '../types'

/** **A fila de decisão da obra** — o que espera alguém, agora.
 *
 *  Não é contagem: cada linha diz o que é, há quanto tempo espera e o botão vai
 *  ao posto que a resolve. E **não soma o que não se soma** — as faixas ficam
 *  agrupadas por degrau de consequência, na ordem em que doem, em vez de virar
 *  um "12 pendências" que mistura uma comunicação com prazo em lei e um defeito
 *  de pintura. */
export function FilaDeDecisao({
  fila, obraId, titulo = 'O que exige a sua decisão', vazio, noPosto, emAberto,
}: {
  fila: FilaDoDia
  obraId: number
  titulo?: string
  /** O estado vazio do posto nomeia as filas **dele**; o do dia, as onze. */
  vazio?: ReactNode
  /** Dentro do posto a faixa não tem "Resolver": ela já está onde se resolve,
   *  e a linha abre o documento. */
  noPosto?: boolean
  /** O que o posto tem **em aberto** e que já saiu da fila por ter dono (a
   *  ocorrência em investigação, o defeito com plano). Aparece dentro da caixa
   *  da fila e, havendo, toma o lugar do "nada parado" — achado do dono,
   *  17/10/2026: a frase fazia a ocorrência aberta parecer inexistente. */
  emAberto?: ReactNode
}) {
  const porDegrau = useMemo(() => {
    return DEGRAUS
      .map((degrau) => ({
        degrau,
        faixas: fila.faixas.filter((f) => f.consequencia === degrau.codigo),
      }))
      .filter((grupo) => grupo.faixas.length > 0)
  }, [fila.faixas])

  return (
    <section>
      <SectionHead
        sub={
          fila.total > 0
            ? `${fila.total} ${fila.total === 1 ? 'coisa espera' : 'coisas esperam'} uma decisão`
            : undefined
        }
        right={
          fila.total > 0 ? (
            <Pill kind="accent" pulse>
              {fila.total} na fila
            </Pill>
          ) : undefined
        }
      >
        {titulo}
      </SectionHead>

      {fila.sem_permissao.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <SemPermissaoAviso itens={fila.sem_permissao} />
        </div>
      )}

      {fila.total === 0 && emAberto ? null : fila.total === 0 ? (
        <Empty>
          {vazio ?? (
            <>
              <strong style={{ color: 'var(--ink-2)' }}>Nada esperando você nesta obra.</strong>
              <br />
              Nenhuma das {fila.faixas_varridas} filas — comunicação de acidente,
              medição, semana, restrição, defeito e ficha — tem alguém parado.
            </>
          )}
        </Empty>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {porDegrau.map(({ degrau, faixas }) => (
            <div key={degrau.codigo}>
              <div
                style={{
                  display: 'flex', alignItems: 'baseline', gap: 9,
                  marginBottom: 7, paddingLeft: 2,
                }}
              >
                <Pill kind={degrau.pill}>{degrau.rotulo}</Pill>
                <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                  {degrau.explica}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {faixas.map((faixa) => (
                  <Faixa
                    key={faixa.codigo}
                    faixa={faixa}
                    obraId={obraId}
                    tom={degrau.codigo}
                    noPosto={noPosto}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {emAberto && <div style={{ marginTop: fila.total > 0 ? 16 : 0 }}>{emAberto}</div>}
    </section>
  )
}

function Faixa({
  faixa, obraId, tom, noPosto,
}: { faixa: FaixaDaFila; obraId: number; tom: Consequencia; noPosto?: boolean }) {
  const [aberta, setAberta] = useState(
    noPosto || tom === 'prazo_legal' || tom === 'dinheiro',
  )
  const navigate = useNavigate()
  const destino = `/app/pdca/o/${obraId}/${POSTO_DA_ORIGEM[faixa.origem]}`

  return (
    <Card pad={false} style={{ overflow: 'hidden' }}>
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '11px 14px',
        }}
      >
        <button
          type="button"
          onClick={() => setAberta((v) => !v)}
          aria-expanded={aberta}
          style={{
            display: 'flex', alignItems: 'center', gap: 9, flex: 1, minWidth: 0,
            background: 'none', border: 'none', padding: 0, cursor: 'pointer',
            textAlign: 'left', color: 'inherit',
          }}
        >
          {aberta
            ? <ChevronDown size={15} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
            : <ChevronRight size={15} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />}
          <Num size={15} tone="var(--ink)" align="center" style={{ minWidth: 22 }}>
            {faixa.total}
          </Num>
          <span style={{ minWidth: 0 }}>
            <span
              style={{
                display: 'block', fontSize: 13.5, fontWeight: 650,
                color: 'var(--ink)', lineHeight: 1.35,
              }}
            >
              {faixa.rotulo}
            </span>
            <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)' }}>
              {faixa.o_que_decidir}
            </span>
          </span>
        </button>

        {!noPosto && <button
          type="button"
          onClick={() => navigate(destino)}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 5, flexShrink: 0,
            background: 'var(--surface-2)', border: '1px solid var(--line)',
            borderRadius: 'var(--r-sm)', padding: '5px 10px', cursor: 'pointer',
            fontSize: 12, fontWeight: 650, color: 'var(--ink-2)',
          }}
        >
          Resolver
          <ArrowUpRight size={13} />
        </button>}
      </div>

      {aberta && (
        <div style={{ borderTop: '1px solid var(--line-2)' }}>
          {faixa.linhas.map((linha) => (
            <Linha key={linha.chave} linha={linha} obraId={obraId} />
          ))}
          {faixa.truncada && (
            <div
              style={{
                padding: '9px 14px', fontSize: 11.5, color: 'var(--ink-3)',
                borderTop: '1px solid var(--line-2)', background: 'var(--inset)',
              }}
            >
              Mostrando as {faixa.linhas.length} mais antigas de {faixa.total}.
              As demais estão no posto que trata deste assunto.
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

/** A linha **abre o documento**, e não só o posto: quem clicou numa NC quer
 *  aquela NC, e mandá-lo à porta do posto para procurá-la de novo é o que faz
 *  a fila virar só um lembrete. */
function Linha({ linha, obraId }: { linha: LinhaDaFila; obraId: number }) {
  const prazo = linha.prazo
  /** **O valor aparece na fila da medição, e não só lá dentro.** Quem vai
   *  atestar decide pelo tamanho do que está assinando — uma fila de dinheiro
   *  sem o dinheiro obriga a abrir cada uma para saber qual olhar primeiro. */
  const liquido = typeof linha.liquido === 'string' ? linha.liquido : null

  return (
    <Link
      to={enderecoDoDocumento(obraId, linha.tipo, linha.id, {
        nc: linha.nc, contrato: linha.contrato,
      })}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 11,
        padding: '9px 14px 9px 46px', borderTop: '1px solid var(--line-2)',
        textDecoration: 'none', color: 'inherit',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 12.5, color: 'var(--ink)', lineHeight: 1.4,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}
        >
          {linha.titulo}
        </div>
        {(linha.detalhe || linha.onde) && (
          <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
            {linha.onde && <span>{linha.onde}</span>}
            {linha.onde && linha.detalhe && <span> · </span>}
            {linha.detalhe}
          </div>
        )}
      </div>

      {liquido && (
        <Num size={12.5} tone="var(--ink-2)" style={{ flexShrink: 0 }}>
          {formatBRL(apiDecimalToCents(liquido))}
        </Num>
      )}

      {prazo && <SeloDePrazo prazo={prazo} />}

      {linha.dias != null && (
        <span
          title={linha.desde ? `Desde ${dateToBR(linha.desde)}` : undefined}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            fontSize: 11.5, color: 'var(--ink-3)', flexShrink: 0,
            minWidth: 74, justifyContent: 'flex-end',
          }}
        >
          <Clock size={11} />
          {linha.dias === 0 ? 'hoje' : `há ${emDias(linha.dias)}`}
        </span>
      )}
    </Link>
  )
}

/** O prazo que corre contra a linha.
 *
 *  Só existe onde o servidor devolve um — a comunicação de acidente, a
 *  restrição, a ação do plano. A frase diz **quantos dias**, porque "vencido"
 *  sozinho não distingue um atraso de ontem de um de dois meses. */
function SeloDePrazo({ prazo }: { prazo: NonNullable<LinhaDaFila['prazo']> }) {
  const dias = prazo.dias_restantes
  const texto = prazo.imediata && !prazo.vencido
    ? 'imediata'
    : prazo.vencido
      ? `${emDias(dias)} em atraso`
      : dias === 0
        ? 'vence hoje'
        : `faltam ${emDias(dias)}`

  return (
    <span style={{ flexShrink: 0 }}>
      <Pill
        kind={prazo.vencido ? 'danger' : dias <= 1 ? 'accent' : 'slate'}
        title={prazo.base_legal || undefined}
      >
        {prazo.vencido ? <Clock size={11} /> : <CheckCircle2 size={11} />}
        {texto}
      </Pill>
    </span>
  )
}
