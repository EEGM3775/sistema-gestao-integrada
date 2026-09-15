import { Link } from 'react-router-dom'
import { ArrowRight, Sigma } from 'lucide-react'
import { Modal, Num, Pill } from '@/components/malha'
import type { LinhaDaGrade } from '../types'

/**
 * **De onde saiu este número.**
 *
 * A proposta automática nasce do avanço apontado no cronograma, e até aqui a
 * tela mostrava só o resultado. Quando o gestor perguntava *"por que 95?"*, a
 * resposta existia no servidor — as atividades, o avanço de cada uma no
 * período, o peso que cada uma teve — e era descartada na serialização.
 *
 * Uma proposta que ninguém consegue auditar é uma caixa preta, e caixa preta
 * que vira título a pagar é exatamente o que a §11.4 da planta manda evitar. É
 * também a **integração visível** que a régua do frontend pede: daqui se vai
 * para a atividade do cronograma que gerou a linha, com um clique.
 */
export default function MemoriaDeCalculo({
  linha, obraId, cronogramaId, onClose, observacao, onObservacao,
}: {
  linha: LinhaDaGrade
  obraId: number | undefined
  cronogramaId: number | undefined
  onClose: () => void
  /** A nota da pessoa sobre esta linha. `undefined` em documento congelado. */
  observacao?: string
  onObservacao?: (texto: string) => void
}) {
  const contratado = Number(linha.quantidade_contratada)
  const percentual = linha.percentual_avanco_periodo == null
    ? null : Number(linha.percentual_avanco_periodo)
  const proposto = Number(linha.quantidade_proposta)

  return (
    <Modal titulo={`Memória de cálculo · item ${linha.codigo}`} onClose={onClose}>
      <p style={{ fontSize: 13.5, color: 'var(--ink-2)', marginTop: 0 }}>
        {linha.descricao}
      </p>

      {linha.criterio === 'sem_vinculo' ? (
        <div style={{
          padding: '10px 12px', borderRadius: 8, fontSize: 13,
          background: 'var(--accent-soft)', color: 'var(--accent-ink)',
        }}>
          Esta linha <strong>não tem atividade nem item orçado ligados</strong>, então
          o sistema não consegue propor quantidade para ela — o que a grade mostra
          é zero por falta de vínculo, não por falta de avanço. Ligue o item a uma
          frente do cronograma na planilha contratual, ou digite a quantidade à
          mão sabendo que ela não é conferida contra nada.
        </div>
      ) : (
        <>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
            padding: '12px 14px', borderRadius: 10, background: 'var(--surface-2)',
            fontFamily: 'var(--mono)', fontSize: 14, marginBottom: 14,
          }}>
            <Sigma size={15} style={{ color: 'var(--ink-3)' }} />
            <span><Num>{contratado.toLocaleString('pt-BR')}</Num> contratado</span>
            <span style={{ color: 'var(--ink-3)' }}>×</span>
            <span><Num>{percentual ?? 0}%</Num> no período</span>
            <ArrowRight size={14} style={{ color: 'var(--ink-3)' }} />
            <strong style={{ color: 'var(--brand)' }}>
              <Num>{proposto.toLocaleString('pt-BR')}</Num> {linha.unidade}
            </strong>
          </div>

          {linha.limitada_pelo_saldo && (
            <p style={{
              fontSize: 12.5, color: 'var(--accent-ink)', background: 'var(--accent-soft)',
              padding: '8px 10px', borderRadius: 8, margin: '0 0 14px',
            }}>
              O avanço apontado daria <strong>mais que o saldo</strong> — a proposta
              foi cortada no que resta do contratado ({Number(linha.saldo)} {linha.unidade}).
              Medir acima disso é aditivo, não medição.
            </p>
          )}

          <h3 style={{ margin: '0 0 8px', fontSize: 13 }}>
            {linha.memoria.length === 1
              ? 'A frente que alimenta esta linha'
              : `As ${linha.memoria.length} frentes que alimentam esta linha`}
            {linha.criterio === 'ponderado' && ' · média ponderada pelo peso'}
            {linha.criterio === 'media_simples' && ' · média simples (nenhuma tem peso)'}
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {linha.memoria.map(m => (
              <div
                key={m.atividade_id}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5,
                  padding: '8px 10px', border: '1px solid var(--line)', borderRadius: 8,
                }}
              >
                <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-3)' }}>
                  {m.codigo}
                </span>
                <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {cronogramaId && obraId ? (
                    <Link
                      to={`/app/pdca/obra/${obraId}/cronograma/${cronogramaId}?atividade=${m.atividade_id}`}
                      style={{ color: 'var(--ink)', textDecoration: 'none' }}
                      title="Abrir esta frente no cronograma"
                    >
                      {m.nome}
                    </Link>
                  ) : m.nome}
                </span>
                {m.peso != null && (
                  <Pill kind="slate">
                    peso {Number(m.peso).toLocaleString('pt-BR')}
                    {m.origem_do_peso ? ` · ${m.origem_do_peso}` : ''}
                  </Pill>
                )}
                <Num>{Number(m.percentual).toLocaleString('pt-BR')}%</Num>
              </div>
            ))}
          </div>

          <p style={{ margin: '12px 0 0', fontSize: 12, color: 'var(--ink-3)' }}>
            O avanço do período é a <strong>soma dos apontamentos</strong> com data
            dentro da janela, estornos incluídos — eles são negativos e se cancelam
            sozinhos. Nada é calculado subtraindo acumulados de duas datas.
          </p>
        </>
      )}

      {/* A outra metade da memória: a do **sistema** está acima; esta é a de
          quem mediu. Ela viaja para o boletim, que é onde alguém a lê dois
          anos depois perguntando por que a linha pagou o que pagou. */}
      {(onObservacao || observacao) && (
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--line)' }}>
          <label style={{ display: 'block', fontSize: 12.5, color: 'var(--ink-2)', marginBottom: 5 }}>
            Sua nota sobre esta linha
          </label>
          {onObservacao ? (
            <textarea
              value={observacao ?? ''}
              onChange={e => onObservacao(e.target.value)}
              rows={3}
              placeholder="Ex.: conferido em campo com o fiscal em 12/08, croqui na pasta da obra."
              style={{
                width: '100%', padding: '8px 10px', borderRadius: 8,
                border: '1px solid var(--line)', background: 'var(--surface)',
                color: 'var(--ink)', fontSize: 13.5, resize: 'vertical',
              }}
            />
          ) : (
            <p style={{ fontSize: 13, margin: 0, whiteSpace: 'pre-wrap' }}>{observacao}</p>
          )}
          <p style={{ margin: '5px 0 0', fontSize: 11.5, color: 'var(--ink-3)' }}>
            Sai impressa no boletim, ao lado da linha.
          </p>
        </div>
      )}
    </Modal>
  )
}
