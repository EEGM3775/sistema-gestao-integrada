import { useState } from 'react'
import {
  ChevronDown, ChevronRight, Clock, FileSignature, Landmark, PenLine, Stamp,
} from 'lucide-react'
import { Card, Empty, Num, Pill, SectionHead } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import { emDias } from '../formato'
import { SemPermissaoAviso } from './SemPermissaoAviso'
import type { FilaDaMedicao, LinhaDaFila } from '../types'

/** O que cada bloco é, e **o verbo que o fecha**.
 *
 *  Fila que diz o que espera e não diz o que decidir é contagem com outro
 *  nome — a mesma régua da fila do dia, aplicada ao dinheiro. */
const BLOCOS: {
  chave: keyof FilaDaMedicao['totais']
  rotulo: string
  oQueDecidir: string
  icone: typeof PenLine
  pill: 'accent' | 'info' | 'slate'
}[] = [
  {
    chave: 'medicoes_a_atestar',
    rotulo: 'Boletim esperando atesto',
    oQueDecidir: 'Atestar ou devolver — o pagamento do empreiteiro sai daqui.',
    icone: Stamp,
    pill: 'accent',
  },
  {
    chave: 'medicoes_em_rascunho',
    rotulo: 'Boletim apurado e não enviado',
    oQueDecidir: 'Conferir a grade e enviar para atesto.',
    icone: PenLine,
    pill: 'info',
  },
  {
    chave: 'retencoes_a_liberar',
    rotulo: 'Retenção pedida de volta',
    oQueDecidir: 'Conferir a condição do contrato e decidir a devolução.',
    icone: Landmark,
    pill: 'info',
  },
  {
    chave: 'aditivos_a_decidir',
    rotulo: 'Aditivo sem decisão',
    oQueDecidir:
      'Decidir antes da próxima medição — é ele que muda a quantidade '
      + 'contra a qual se mede.',
    icone: FileSignature,
    pill: 'slate',
  },
]

/** **A fila do posto da medição** — o que espera alguém no caminho do dinheiro.
 *
 *  Diferente da fila do dia, esta **não navega**: clicar abre o documento no
 *  próprio posto, ao lado da grade que explica o número. Quem ateste está
 *  olhando a medição, e mandá-lo a outra tela para decidir separaria a decisão
 *  da evidência. */
export function FilaDoDinheiro({
  fila, aoEscolher, escolhida,
}: {
  fila: FilaDaMedicao
  /** O que fazer ao clicar numa linha. `contrato` sempre vem; `medicao` só nas
   *  duas faixas de boletim. */
  aoEscolher: (alvo: { contrato: number; medicao?: number }) => void
  escolhida?: number | null
}) {
  return (
    <section>
      <SectionHead
        sub={
          fila.total > 0
            ? `${fila.total} ${fila.total === 1 ? 'documento parado' : 'documentos parados'}`
            : undefined
        }
        right={fila.total > 0 ? <Pill kind="accent" pulse>{fila.total}</Pill> : undefined}
      >
        O que espera decisão
      </SectionHead>

      {fila.sem_permissao.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <SemPermissaoAviso itens={fila.sem_permissao} />
        </div>
      )}

      {fila.total === 0 ? (
        <Empty>
          <strong style={{ color: 'var(--ink-2)' }}>
            Nenhum documento parado nesta obra.
          </strong>
          <br />
          Nada esperando atesto, nenhum boletim apurado sem envio, nenhuma
          retenção pedida e nenhum aditivo sem decisão.
        </Empty>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {BLOCOS.map((bloco) => (
            <Bloco
              key={bloco.chave}
              bloco={bloco}
              linhas={fila[bloco.chave] as LinhaDaFila[]}
              total={fila.totais[bloco.chave]}
              aoEscolher={aoEscolher}
              escolhida={escolhida}
            />
          ))}
        </div>
      )}
    </section>
  )
}

function Bloco({
  bloco, linhas, total, aoEscolher, escolhida,
}: {
  bloco: (typeof BLOCOS)[number]
  linhas: LinhaDaFila[]
  total: number
  aoEscolher: (alvo: { contrato: number; medicao?: number }) => void
  escolhida?: number | null
}) {
  /** Abre por padrão o que tem gente esperando — um bloco vazio recolhido não
   *  esconde nada, e um cheio fechado esconde tudo. */
  const [aberto, setAberto] = useState(total > 0)
  const Icone = bloco.icone

  if (total === 0) return null

  return (
    <Card pad={false} style={{ overflow: 'hidden' }}>
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
        style={{
          display: 'flex', alignItems: 'center', gap: 10, width: '100%',
          padding: '11px 14px', background: 'none', border: 'none',
          cursor: 'pointer', textAlign: 'left', color: 'inherit',
        }}
      >
        {aberto
          ? <ChevronDown size={15} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
          : <ChevronRight size={15} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />}
        <Icone size={15} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
        <Num size={15} tone="var(--ink)" align="center" style={{ minWidth: 22 }}>
          {total}
        </Num>
        <span style={{ minWidth: 0, flex: 1 }}>
          <span
            style={{
              display: 'block', fontSize: 13.5, fontWeight: 650,
              color: 'var(--ink)', lineHeight: 1.35,
            }}
          >
            {bloco.rotulo}
          </span>
          <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)' }}>
            {bloco.oQueDecidir}
          </span>
        </span>
        <Pill kind={bloco.pill}>{total}</Pill>
      </button>

      {aberto && (
        <div style={{ borderTop: '1px solid var(--line-2)' }}>
          {linhas.map((linha) => (
            <Linha
              key={linha.chave}
              linha={linha}
              selecionada={
                linha.tipo === 'medicao' && escolhida === linha.id
              }
              aoEscolher={aoEscolher}
            />
          ))}
          {total > linhas.length && (
            <div
              style={{
                padding: '9px 14px', fontSize: 11.5, color: 'var(--ink-3)',
                borderTop: '1px solid var(--line-2)', background: 'var(--inset)',
              }}
            >
              Mostrando os {linhas.length} mais antigos de {total}. Os demais
              aparecem à medida que estes saírem da fila.
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

function Linha({
  linha, selecionada, aoEscolher,
}: {
  linha: LinhaDaFila
  selecionada: boolean
  aoEscolher: (alvo: { contrato: number; medicao?: number }) => void
}) {
  const contrato = typeof linha.contrato === 'number' ? linha.contrato : null
  const liquido = typeof linha.liquido === 'string' ? linha.liquido : null
  const degrau = typeof linha.degrau === 'string' ? linha.degrau : ''
  /** O boletim aberto **sem uma linha sequer** não é o mesmo problema do que
   *  está pronto e parado: um pede para ser preenchido, o outro conferido. */
  const vazio = linha.linhas === 0

  return (
    <button
      type="button"
      disabled={contrato == null}
      onClick={() => {
        if (contrato == null) return
        aoEscolher({
          contrato,
          medicao: linha.tipo === 'medicao' ? linha.id : undefined,
        })
      }}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 11, width: '100%',
        padding: '9px 14px 9px 46px', borderTop: '1px solid var(--line-2)',
        background: selecionada ? 'var(--inset)' : 'transparent',
        border: 'none', borderTopStyle: 'solid', cursor: contrato == null ? 'default' : 'pointer',
        textAlign: 'left', color: 'inherit', font: 'inherit',
      }}
    >
      <span style={{ flex: 1, minWidth: 0 }}>
        <span
          style={{
            display: 'block', fontSize: 12.5, color: 'var(--ink)',
            lineHeight: 1.4, overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {linha.titulo}
        </span>
        <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
          {linha.onde && <span>{linha.onde}</span>}
          {linha.onde && linha.detalhe && <span> · </span>}
          {linha.detalhe}
          {degrau && <span> · espera {degrau}</span>}
          {vazio && <span> · sem linhas preenchidas</span>}
        </span>
      </span>

      {liquido && (
        <Num size={12.5} tone="var(--ink-2)" style={{ flexShrink: 0 }}>
          {formatBRL(apiDecimalToCents(liquido))}
        </Num>
      )}

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
    </button>
  )
}
