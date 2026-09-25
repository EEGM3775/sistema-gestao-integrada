import { useState } from 'react'
import { Check, Plus, X } from 'lucide-react'
import {
  Btn, Card, Empty, Loading, Modal, Num, Pill, SectionHead,
} from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import { percentual } from '../formato'
import type { AditivoContrato, LinhaDeContrato, StatusAditivo } from '../types'

const TOM: Record<StatusAditivo, 'good' | 'accent' | 'info' | 'danger' | 'slate'> = {
  rascunho: 'info',
  em_aprovacao: 'accent',
  aprovado: 'good',
  reprovado: 'danger',
  cancelado: 'slate',
}

/** **O contrato mudando por escrito.**
 *
 *  O aditivo é painel do posto da medição, e não assunto à parte, porque só
 *  existe em função do contrato — e porque é ele que muda a quantidade contra
 *  a qual a próxima medição se confere. Um aditivo parado na escada é um
 *  boletim que vai medir contra o contratado velho. */
export function PainelDeAditivos({
  contrato, aditivos, carregando, ocupado, podeEditar, podeAprovar,
  aoAbrir, aoSubmeter, aoAtestar,
}: {
  contrato: LinhaDeContrato
  aditivos: AditivoContrato[]
  carregando: boolean
  ocupado?: boolean
  podeEditar: boolean
  podeAprovar: boolean
  aoAbrir: (corpo: {
    contrato: number; objeto: string; justificativa: string
  }) => void
  aoSubmeter: (id: number) => void
  aoAtestar: (id: number, aprovar: boolean, observacao: string) => void
}) {
  const [novo, setNovo] = useState(false)
  const [decidindo, setDecidindo] = useState<{ id: number; aprovar: boolean } | null>(null)

  if (carregando) return <Loading o="os aditivos do contrato" />

  return (
    <section>
      <SectionHead
        sub={
          apiDecimalToCents(contrato.saldo.valor_aditivado) !== 0
            ? `${formatBRL(apiDecimalToCents(contrato.saldo.valor_aditivado))} já acrescentados ao contratado original`
            : undefined
        }
        right={
          podeEditar && !novo ? (
            <Btn tam="sm" onClick={() => setNovo(true)}>
              <Plus size={13} />
              Novo aditivo
            </Btn>
          ) : undefined
        }
      >
        Aditivos
      </SectionHead>

      {/* O limite legal é do contrato, digitado por quem o cadastrou — o
          sistema confere contra o número declarado, não escolhe um. */}
      {contrato.regime_publico && (
        <p style={{ margin: '0 0 10px', fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          Contrato em regime público: os acréscimos são conferidos contra o
          limite declarado no cadastro deste contrato.
        </p>
      )}

      {aditivos.length === 0 ? (
        <Card>
          <Empty>
            <span style={{ lineHeight: 1.6 }}>
              Nenhum aditivo neste contrato. É por ele que quantidade, preço ou
              item novo entram depois da primeira medição — guardando o que
              mudou, o porquê e quem autorizou.
            </span>
            {podeEditar && (
              <Btn variant="primary" onClick={() => setNovo(true)}>
                <Plus size={14} />
                Abrir o primeiro aditivo
              </Btn>
            )}
          </Empty>
        </Card>
      ) : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          {aditivos.map((aditivo) => (
            <div
              key={aditivo.aditivo_id}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 10,
                padding: '11px 14px', borderBottom: '1px solid var(--line-2)',
              }}
            >
              <Num size={13} tone="var(--ink-3)" style={{ minWidth: 26 }}>
                {aditivo.numero}
              </Num>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>
                    {aditivo.objeto || 'Aditivo sem objeto declarado'}
                  </span>
                  <Pill kind={TOM[aditivo.status]}>{aditivo.status_rotulo}</Pill>
                  {aditivo.escada?.nivel && (
                    <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                      espera {aditivo.escada.nivel}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 3, lineHeight: 1.5 }}>
                  {aditivo.justificativa}
                </div>
                {aditivo.nova_data_fim && (
                  <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
                    prorroga o contrato até {dateToBR(aditivo.nova_data_fim)}
                  </div>
                )}
              </div>

              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <Num size={13} tone="var(--ink)">
                  {formatBRL(apiDecimalToCents(aditivo.valor_total))}
                </Num>
                {aditivo.percentual_sobre_original != null && (
                  <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2 }}>
                    {percentual(aditivo.percentual_sobre_original)} do original
                  </div>
                )}
                <div style={{ display: 'flex', gap: 6, marginTop: 7, justifyContent: 'flex-end' }}>
                  {aditivo.status === 'rascunho' && podeEditar && (
                    <Btn tam="sm" disabled={ocupado} onClick={() => aoSubmeter(aditivo.aditivo_id)}>
                      Enviar para aprovação
                    </Btn>
                  )}
                  {aditivo.status === 'em_aprovacao' && podeAprovar && (
                    <>
                      <Btn
                        tam="sm" variant="primary" disabled={ocupado}
                        onClick={() => setDecidindo({ id: aditivo.aditivo_id, aprovar: true })}
                      >
                        <Check size={13} />
                        Aprovar
                      </Btn>
                      <Btn
                        tam="sm" disabled={ocupado}
                        onClick={() => setDecidindo({ id: aditivo.aditivo_id, aprovar: false })}
                      >
                        <X size={13} />
                        Devolver
                      </Btn>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </Card>
      )}

      {novo && (
        <DialogoDeAditivo
          ocupado={ocupado}
          aoFechar={() => setNovo(false)}
          aoConfirmar={(objeto, justificativa) => {
            aoAbrir({ contrato: contrato.contrato, objeto, justificativa })
            setNovo(false)
          }}
        />
      )}

      {decidindo && (
        <DialogoDeDecisao
          aprovar={decidindo.aprovar}
          ocupado={ocupado}
          aoFechar={() => setDecidindo(null)}
          aoConfirmar={(observacao) => {
            aoAtestar(decidindo.id, decidindo.aprovar, observacao)
            setDecidindo(null)
          }}
        />
      )}
    </section>
  )
}

function DialogoDeAditivo({
  ocupado, aoFechar, aoConfirmar,
}: {
  ocupado?: boolean
  aoFechar: () => void
  aoConfirmar: (objeto: string, justificativa: string) => void
}) {
  const [objeto, setObjeto] = useState('')
  const [justificativa, setJustificativa] = useState('')
  const completo = objeto.trim() && justificativa.trim()

  const campo = {
    width: '100%', padding: '8px 10px', borderRadius: 8,
    border: '1px solid var(--line)', background: 'var(--surface)',
    color: 'var(--ink)', fontSize: 13, fontFamily: 'inherit',
  } as const

  return (
    <Modal
      titulo="Abrir um aditivo"
      onClose={aoFechar}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Voltar</Btn>
          <Btn
            variant="primary"
            disabled={!completo || ocupado}
            onClick={() => aoConfirmar(objeto.trim(), justificativa.trim())}
          >
            Abrir em rascunho
          </Btn>
        </div>
      }
    >
      <p style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6 }}>
        O aditivo nasce em rascunho e não move saldo nenhum ainda. As linhas —
        acréscimo, supressão ou item novo — entram depois, e só quando ele for
        aprovado o contratado muda.
      </p>
      <label style={{ display: 'block', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--ink-3)', fontWeight: 700, marginBottom: 6 }}>
        O que este aditivo acrescenta ou tira
      </label>
      <input value={objeto} onChange={(e) => setObjeto(e.target.value)} autoFocus style={campo} />
      <label style={{ display: 'block', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--ink-3)', fontWeight: 700, margin: '14px 0 6px' }}>
        Por que ele foi preciso
      </label>
      <textarea
        value={justificativa}
        onChange={(e) => setJustificativa(e.target.value)}
        rows={3}
        style={{ ...campo, resize: 'vertical' }}
      />
    </Modal>
  )
}

function DialogoDeDecisao({
  aprovar, ocupado, aoFechar, aoConfirmar,
}: {
  aprovar: boolean
  ocupado?: boolean
  aoFechar: () => void
  aoConfirmar: (observacao: string) => void
}) {
  const [texto, setTexto] = useState('')
  const falta = !aprovar && !texto.trim()

  return (
    <Modal
      titulo={aprovar ? 'Aprovar o aditivo' : 'Devolver o aditivo'}
      onClose={aoFechar}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Voltar</Btn>
          <Btn
            variant="primary"
            disabled={falta || ocupado}
            onClick={() => aoConfirmar(texto.trim())}
          >
            {aprovar ? 'Aprovar' : 'Devolver'}
          </Btn>
        </div>
      }
    >
      <p style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6 }}>
        {aprovar
          ? 'Aprovado o último degrau, as linhas do aditivo entram no contratado '
            + 'e passam a valer para a próxima medição.'
          : 'O aditivo volta para quem o montou. Diga o que precisa mudar — sem '
            + 'isso ele volta igual.'}
      </p>
      <textarea
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        rows={3}
        autoFocus
        placeholder={aprovar ? 'Observação da assinatura (opcional)' : 'O que precisa mudar'}
        style={{
          width: '100%', padding: '8px 10px', borderRadius: 8,
          border: '1px solid var(--line)', background: 'var(--surface)',
          color: 'var(--ink)', fontSize: 13, resize: 'vertical',
          fontFamily: 'inherit',
        }}
      />
    </Modal>
  )
}
