import { useState } from 'react'
import { Landmark } from 'lucide-react'
import {
  Btn, CampoMoeda, Card, Empty, Loading, Modal, Num, Pill, SectionHead,
} from '@/components/malha'
import { dateToBR, isoLocal } from '@/utils/dates'
import { apiDecimalToCents, centsToApiDecimal, formatBRL } from '@/utils/money'
import type { LiberacaoRetencao, LinhaDeContrato } from '../types'

/** **A caução** — o dinheiro do empreiteiro que a obra segurou.
 *
 *  As três parcelas aparecem juntas, e não só o saldo, porque a tela precisa
 *  poder explicar o número: "R$ 12.400 retidos, R$ 4.000 já devolvidos" é uma
 *  frase que o gestor confere contra o extrato; "saldo R$ 8.400" é um número
 *  que ele tem de aceitar.
 *
 *  Liberar é ato de quem ateste, e não de quem monta o contrato: a mesma
 *  pessoa não define o valor retido e o manda de volta. */
export function PainelDeRetencao({
  contrato, liberacoes, carregando, ocupado, podeLiberar, aoLiberar,
}: {
  contrato: LinhaDeContrato
  liberacoes: LiberacaoRetencao[]
  carregando: boolean
  ocupado?: boolean
  podeLiberar: boolean
  aoLiberar: (corpo: {
    valor: string; data: string; condicao_atendida: string
  }) => void
}) {
  const [pedindo, setPedindo] = useState(false)
  const retencao = contrato.saldo.retencao
  const disponivel = apiDecimalToCents(retencao.disponivel)

  if (carregando) return <Loading o="a retenção do contrato" />

  /** Contrato sem cláusula de retenção não tem painel para mostrar — e dizer
   *  "R$ 0,00 retidos" sugeriria que há caução onde não há. */
  if (
    apiDecimalToCents(retencao.retido) === 0
    && apiDecimalToCents(retencao.liberado) === 0
    && liberacoes.length === 0
  ) {
    return (
      <section>
        <SectionHead>Retenção</SectionHead>
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.6 }}>
          Este contrato não retém caução — nenhuma medição segurou valor, e não
          há nada a devolver ao empreiteiro.
        </p>
      </section>
    )
  }

  return (
    <section>
      <SectionHead
        right={
          podeLiberar && disponivel > 0 ? (
            <Btn tam="sm" onClick={() => setPedindo(true)}>
              <Landmark size={13} />
              Pedir devolução
            </Btn>
          ) : undefined
        }
      >
        Retenção
      </SectionHead>

      <Card>
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          {[
            { rotulo: 'Retido até aqui', valor: retencao.retido, tom: 'var(--ink-2)' },
            { rotulo: 'Já devolvido', valor: retencao.liberado, tom: 'var(--ink-3)' },
            { rotulo: 'Ainda em poder da obra', valor: retencao.disponivel, tom: 'var(--ink)' },
          ].map((parcela) => (
            <div key={parcela.rotulo}>
              <div
                style={{
                  fontSize: 10.5, letterSpacing: '0.07em', textTransform: 'uppercase',
                  color: 'var(--ink-3)', fontWeight: 700, marginBottom: 3,
                }}
              >
                {parcela.rotulo}
              </div>
              <Num size={15} tone={parcela.tom}>
                {formatBRL(apiDecimalToCents(parcela.valor))}
              </Num>
            </div>
          ))}
        </div>

        {/* A cláusula que diz **quando** a caução volta. É contra ela que quem
            pede a devolução declara o que foi cumprido. */}
        {retencao.condicao && (
          <p
            style={{
              margin: '14px 0 0', paddingTop: 12, fontSize: 12.5, lineHeight: 1.6,
              color: 'var(--ink-3)', borderTop: '1px solid var(--line-2)',
            }}
          >
            <strong style={{ color: 'var(--ink-2)' }}>Volta quando: </strong>
            {retencao.condicao}
          </p>
        )}
      </Card>

      {liberacoes.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <Card pad={false} style={{ overflow: 'hidden' }}>
            {liberacoes.map((liberacao) => (
              <div
                key={liberacao.liberacao_id}
                style={{
                  display: 'flex', alignItems: 'baseline', gap: 10,
                  padding: '9px 14px', borderBottom: '1px solid var(--line-2)',
                  fontSize: 12.5,
                }}
              >
                <Pill
                  kind={
                    liberacao.status === 'aprovada' ? 'good'
                      : liberacao.status === 'em_aprovacao' ? 'accent' : 'slate'
                  }
                >
                  {liberacao.status_rotulo}
                </Pill>
                <span style={{ flex: 1, color: 'var(--ink-2)', minWidth: 0 }}>
                  {liberacao.condicao_atendida}
                  {liberacao.escada?.nivel && (
                    <span style={{ color: 'var(--ink-3)' }}>
                      {' '}· espera {liberacao.escada.nivel}
                    </span>
                  )}
                </span>
                <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                  {dateToBR(liberacao.data)}
                </span>
                <Num size={12.5} tone="var(--ink)">
                  {formatBRL(apiDecimalToCents(liberacao.valor))}
                </Num>
              </div>
            ))}
          </Card>
        </div>
      )}

      {liberacoes.length === 0 && disponivel > 0 && (
        <div style={{ marginTop: 12 }}>
          <Empty>
            Nenhuma devolução pedida até aqui.
          </Empty>
        </div>
      )}

      {pedindo && (
        <DialogoDeLiberacao
          disponivel={disponivel}
          condicao={retencao.condicao}
          ocupado={ocupado}
          aoFechar={() => setPedindo(false)}
          aoConfirmar={(centavos, condicaoAtendida) => {
            aoLiberar({
              valor: centsToApiDecimal(centavos),
              data: isoLocal(new Date()),
              condicao_atendida: condicaoAtendida,
            })
            setPedindo(false)
          }}
        />
      )}
    </section>
  )
}

function DialogoDeLiberacao({
  disponivel, condicao, ocupado, aoFechar, aoConfirmar,
}: {
  disponivel: number
  condicao: string
  ocupado?: boolean
  aoFechar: () => void
  aoConfirmar: (centavos: number, condicaoAtendida: string) => void
}) {
  const [centavos, setCentavos] = useState(disponivel)
  const [texto, setTexto] = useState('')

  const acimaDoSaldo = centavos > disponivel
  const completo = centavos > 0 && !acimaDoSaldo && texto.trim()

  return (
    <Modal
      titulo="Pedir a devolução da retenção"
      onClose={aoFechar}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Voltar</Btn>
          <Btn
            variant="primary"
            disabled={!completo || ocupado}
            onClick={() => aoConfirmar(centavos, texto.trim())}
          >
            Pedir
          </Btn>
        </div>
      }
    >
      <p style={{ margin: '0 0 14px', fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6 }}>
        Há {formatBRL(disponivel)} em poder da obra. O pedido vai para a escada
        de aprovação da caução, que é separada da de medição: quem ateste
        medição confere serviço executado; quem libera caução confere condição
        de contrato cumprida.
      </p>

      <label style={{ display: 'block', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--ink-3)', fontWeight: 700, marginBottom: 6 }}>
        Quanto devolver
      </label>
      <CampoMoeda centavos={centavos} aoMudar={setCentavos} aria-label="Valor a devolver" />
      {acimaDoSaldo && (
        <p style={{ margin: '6px 0 0', fontSize: 12, color: 'var(--danger-ink)' }}>
          Só há {formatBRL(disponivel)} disponíveis para devolução.
        </p>
      )}

      <label style={{ display: 'block', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--ink-3)', fontWeight: 700, margin: '14px 0 6px' }}>
        Que condição do contrato foi cumprida
      </label>
      {condicao && (
        <p style={{ margin: '0 0 6px', fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          A cláusula deste contrato diz: {condicao}
        </p>
      )}
      <textarea
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        rows={3}
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
