import { useState } from 'react'
import { Check, ChevronDown, ChevronRight, Pencil, Plus, Trash2, X } from 'lucide-react'
import {
  Btn, Card, Empty, Loading, Modal, Num, Pill, SectionHead,
} from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import { percentual } from '../formato'
import type {
  AditivoContrato, ItemContrato, LinhaDeAditivoEntrada, LinhaDeContrato, StatusAditivo,
} from '../types'
import type { CabecalhoDoAditivo } from '../api/pdcaApi'
import { EditorDeAditivo } from './EditorDeAditivo'

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
  contrato, aditivos, carregando, itens, carregandoItens, ocupado, erro,
  podeEditar, podeAprovar, aoSalvar, aoSubmeter, aoAtestar, aoExcluir, aoRetirar,
}: {
  contrato: LinhaDeContrato
  aditivos: AditivoContrato[]
  carregando: boolean
  /** Os itens do contrato — o editor monta o aditivo sobre eles. */
  itens: ItemContrato[]
  carregandoItens: boolean
  ocupado?: boolean
  erro?: string | null
  podeEditar: boolean
  podeAprovar: boolean
  /** Grava o aditivo inteiro (abre ou reescreve). Devolve `true` se gravou. */
  aoSalvar: (corpo: {
    id: number | null; cabecalho: CabecalhoDoAditivo; itens: LinhaDeAditivoEntrada[]; enviar: boolean
  }) => Promise<boolean>
  aoSubmeter: (id: number) => void
  aoAtestar: (id: number, aprovar: boolean, observacao: string) => void
  aoExcluir: (id: number) => void
  aoRetirar: (id: number, motivo: string) => void
}) {
  /** `null` = lista; `'novo'` = aditivo novo; ou o rascunho em edição. */
  const [editando, setEditando] = useState<'novo' | AditivoContrato | null>(null)
  const [decidindo, setDecidindo] = useState<{ id: number; aprovar: boolean } | null>(null)
  const [abertos, setAbertos] = useState<Set<number>>(new Set())
  const setNovo = (sim: boolean) => setEditando(sim ? 'novo' : null)

  if (carregando) return <Loading o="os aditivos do contrato" />

  if (editando) {
    const rascunho = editando === 'novo' ? null : editando
    return (
      <EditorDeAditivo
        contrato={contrato}
        itens={itens}
        carregandoItens={carregandoItens}
        aditivo={rascunho}
        ocupado={ocupado}
        erro={erro}
        aoFechar={() => setEditando(null)}
        aoSalvar={async (corpo) => {
          const gravou = await aoSalvar({ id: rascunho?.aditivo_id ?? null, ...corpo })
          if (gravou) setEditando(null)
        }}
      />
    )
  }

  return (
    <section>
      <SectionHead
        sub={
          apiDecimalToCents(contrato.saldo.valor_aditivado) !== 0
            ? `${formatBRL(apiDecimalToCents(contrato.saldo.valor_aditivado))} já acrescentados ao contratado original`
            : undefined
        }
        right={
          podeEditar ? (
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
            <div key={aditivo.aditivo_id} style={{ borderBottom: '1px solid var(--line-2)' }}>
            <div
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 10,
                padding: '11px 14px',
              }}
            >
              <button
                type="button"
                aria-expanded={abertos.has(aditivo.aditivo_id)}
                aria-label="Ver as linhas do aditivo"
                onClick={() => setAbertos((a) => {
                  const n = new Set(a)
                  if (n.has(aditivo.aditivo_id)) n.delete(aditivo.aditivo_id)
                  else n.add(aditivo.aditivo_id)
                  return n
                })}
                style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--ink-3)', display: 'inline-flex', alignItems: 'center', gap: 4 }}
              >
                {abertos.has(aditivo.aditivo_id) ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                <Num size={13} tone="var(--ink-3)" style={{ minWidth: 20 }}>
                  {aditivo.numero}
                </Num>
              </button>
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
                {aditivo.retencao_percentual_nova != null && (
                  <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
                    retenção do contrato passa a {percentual(aditivo.retencao_percentual_nova)}
                  </div>
                )}
                <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
                  {aditivo.resumo.itens} {aditivo.resumo.itens === 1 ? 'linha' : 'linhas'}
                  {apiDecimalToCents(aditivo.resumo.acrescimo) !== 0 && <> · acréscimo {formatBRL(apiDecimalToCents(aditivo.resumo.acrescimo))}</>}
                  {apiDecimalToCents(aditivo.resumo.supressao) !== 0 && <> · supressão {formatBRL(Math.abs(apiDecimalToCents(aditivo.resumo.supressao)))}</>}
                  {apiDecimalToCents(aditivo.resumo.revisao_de_preco) !== 0 && <> · preço {formatBRL(apiDecimalToCents(aditivo.resumo.revisao_de_preco))}</>}
                </div>
              </div>

              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <Num size={13} tone="var(--ink)">
                  {apiDecimalToCents(aditivo.resumo.liquido) > 0 ? '+ ' : ''}
                  {formatBRL(apiDecimalToCents(aditivo.resumo.liquido))}
                </Num>
                {aditivo.resumo.percentual_sobre_original != null && (
                  <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 2 }}>
                    {percentual(aditivo.resumo.percentual_sobre_original)} do original
                  </div>
                )}
                <div style={{ display: 'flex', gap: 6, marginTop: 7, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                  {aditivo.status === 'rascunho' && podeEditar && (
                    <>
                      <Btn tam="sm" disabled={ocupado} onClick={() => setEditando(aditivo)}>
                        <Pencil size={12} /> Editar
                      </Btn>
                      <Btn tam="sm" disabled={ocupado} onClick={() => aoSubmeter(aditivo.aditivo_id)}>
                        Enviar para aprovação
                      </Btn>
                      <Btn tam="sm" disabled={ocupado} title="Rascunho vai para a lixeira"
                        onClick={() => aoExcluir(aditivo.aditivo_id)}>
                        <Trash2 size={12} />
                      </Btn>
                    </>
                  )}
                  {aditivo.status === 'em_aprovacao' && podeEditar && (
                    <Btn tam="sm" disabled={ocupado}
                      onClick={() => aoRetirar(aditivo.aditivo_id, 'Retirado da aprovação por quem o montou.')}>
                      Retirar
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
            {abertos.has(aditivo.aditivo_id) && <LinhasDoAditivo aditivo={aditivo} />}
            </div>
          ))}
        </Card>
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

/** As linhas do aditivo, abertas na lista — o que ele faz com cada item. */
function LinhasDoAditivo({ aditivo }: { aditivo: AditivoContrato }) {
  const linhas = aditivo.itens ?? []
  if (linhas.length === 0) {
    return (
      <p style={{ margin: 0, padding: '0 14px 12px 44px', fontSize: 12, color: 'var(--ink-3)' }}>
        Sem linhas — o aditivo mexe só no prazo ou na retenção.
      </p>
    )
  }
  return (
    <div style={{ padding: '0 14px 12px 44px' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <tbody>
          {linhas.map((l) => (
            <tr key={l.item_aditivo_id} style={{ borderTop: '1px solid var(--line-2)' }}>
              <td style={{ padding: '5px 6px', fontFamily: 'var(--mono)', color: 'var(--ink-2)', width: 70 }}>{l.codigo}</td>
              <td style={{ padding: '5px 6px', color: 'var(--ink)' }}>{l.descricao}</td>
              <td style={{ padding: '5px 6px', color: 'var(--ink-3)' }}>{l.acao_rotulo}</td>
              <td style={{ padding: '5px 6px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                {l.acao === 'preco'
                  ? <>{formatBRL(apiDecimalToCents(l.preco_unitario_anterior ?? '0'))} → {formatBRL(apiDecimalToCents(l.preco_unitario ?? '0'))}</>
                  : <>{Number(l.quantidade_delta) > 0 ? '+' : ''}{Number(l.quantidade_delta).toLocaleString('pt-BR')} {l.unidade}</>}
              </td>
              <td style={{ padding: '5px 6px', textAlign: 'right', color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>
                {l.retencao_percentual != null ? `retém ${percentual(l.retencao_percentual)}` : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
          : 'O aditivo volta para quem o montou. Informe o que precisa mudar.'}
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
