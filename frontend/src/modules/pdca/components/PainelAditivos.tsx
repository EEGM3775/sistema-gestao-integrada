import { useMemo, useState } from 'react'
import {
  CheckCircle2, FilePlus2, Pencil, Plus, Send, Trash2,
} from 'lucide-react'
import { Btn, Modal, Num, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { parseApiErrors } from '@/utils/formErrors'
import {
  useAbrirAditivo, useAditivos, useAtestarAditivo, useCancelarAditivo,
  useSalvarItensDoAditivo, useSubmeterAditivo,
} from '../hooks'
import { CORES_ADITIVO } from './cores'
import type { AcaoAditivo, Aditivo, ItemDeContrato, LinhaDeAditivo } from '../types'

/**
 * **O contrato mudando por escrito.**
 *
 * Antes disto, mudar uma quantidade contratada era editar o `ItemContrato`: o
 * número mudava, o saldo mudava junto, e ninguém conseguia mais dizer *o que
 * foi combinado no dia da assinatura* nem *quem autorizou a diferença*. É o
 * primeiro achado de qualquer auditoria de contrato de obra, e era a razão de
 * a planilha contratual ser editável em contrato vigente.
 *
 * O documento tem escada própria (`pdca.aditivo.aprovar`), e ela não é a da
 * medição: quem confere serviço executado não é quem autoriza a empresa a
 * gastar acima do contratado. Enquanto não é aprovado, **não move saldo
 * nenhum** — é intenção, como o rascunho de medição.
 */

const dinheiro = (v: string | number | null | undefined) =>
  v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const quantidade = (v: string | number) =>
  Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 4 })

export default function PainelAditivos({ contratoId, itens, contratoEditavel }: {
  contratoId: number
  itens: ItemDeContrato[]
  contratoEditavel: boolean
}) {
  const { hasPermission } = useAuth()
  const podeEditar = hasPermission('pdca.aditivo.edit')
  const podeAprovar = hasPermission('pdca.aditivo.aprovar')

  const aditivos = useAditivos({ contrato: contratoId })
  const [editando, setEditando] = useState<Aditivo | 'novo' | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  const submeter = useSubmeterAditivo(contratoId)
  const atestar = useAtestarAditivo(contratoId)
  const cancelar = useCancelarAditivo(contratoId)

  const lista = aditivos.data?.results ?? []

  async function comErro<T>(acao: () => Promise<T>) {
    setErro(null)
    try { return await acao() } catch (e) {
      setErro(Object.values(parseApiErrors(e)).join(' · ') || 'Não deu para concluir.')
      return undefined
    }
  }

  return (
    <div>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        gap: 12, flexWrap: 'wrap', marginBottom: 10,
      }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 15 }}>Aditivos</h2>
          <p style={{ margin: '3px 0 0', fontSize: 12.5, color: 'var(--ink-3)', maxWidth: 520 }}>
            Quantidade, preço, item novo ou prazo. O contratado original nunca é
            reescrito — o que vale hoje é ele <strong>mais</strong> os aditivos
            aprovados.
          </p>
        </div>
        {podeEditar && contratoEditavel && (
          <Btn onClick={() => setEditando('novo')}>
            <FilePlus2 size={14} /> Novo aditivo
          </Btn>
        )}
      </div>

      {erro && (
        <div style={{
          padding: '9px 11px', borderRadius: 8, fontSize: 13, marginBottom: 10,
          background: 'var(--danger-soft)', color: 'var(--danger-ink)',
        }}>
          {erro}
        </div>
      )}

      {lista.length === 0 ? (
        <p style={{ color: 'var(--ink-3)', fontSize: 13, margin: 0 }}>
          Nenhum aditivo. O contrato vale como foi assinado.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {lista.map(a => (
            <div
              key={a.aditivo_id}
              style={{
                border: '1px solid var(--line)', borderRadius: 9, padding: '10px 12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 600, fontFamily: 'var(--mono)' }}>
                  #{a.numero}
                </span>
                <Pill kind={CORES_ADITIVO[a.status]}>{a.status_rotulo}</Pill>
                {a.escada?.nivel && <Pill kind="info">parado em {a.escada.nivel}</Pill>}
                <span style={{ flex: 1, minWidth: 140, fontSize: 13 }}>{a.objeto}</span>
                <Num>{dinheiro(a.resumo.liquido)}</Num>
                {a.resumo.percentual_sobre_original != null && (
                  <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
                    ({Number(a.resumo.percentual_sobre_original) > 0 ? '+' : ''}
                    {Number(a.resumo.percentual_sobre_original).toFixed(2)}% do original)
                  </span>
                )}
              </div>

              <div style={{
                display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 6,
                fontSize: 12, color: 'var(--ink-3)',
              }}>
                <span>{a.resumo.itens} {a.resumo.itens === 1 ? 'linha' : 'linhas'}</span>
                {Number(a.resumo.acrescimo) !== 0 && (
                  <span>acréscimo {dinheiro(a.resumo.acrescimo)}</span>
                )}
                {Number(a.resumo.supressao) !== 0 && (
                  <span>supressão {dinheiro(a.resumo.supressao)}</span>
                )}
                {Number(a.resumo.revisao_de_preco) !== 0 && (
                  <span>revisão de preço {dinheiro(a.resumo.revisao_de_preco)}</span>
                )}
                {a.nova_data_fim && (
                  <span>novo fim {a.nova_data_fim.split('-').reverse().join('/')}</span>
                )}
              </div>

              <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                {a.status === 'rascunho' && podeEditar && (
                  <>
                    <Btn tam="sm" onClick={() => setEditando(a)}>
                      <Pencil size={13} /> Editar
                    </Btn>
                    <Btn
                      tam="sm"
                      variant="brand"
                      onClick={() => comErro(() => submeter.mutateAsync(a.aditivo_id))}
                    >
                      <Send size={13} /> Submeter
                    </Btn>
                  </>
                )}
                {a.status === 'em_aprovacao' && podeAprovar && (
                  <>
                    <Btn
                      tam="sm"
                      variant="brand"
                      onClick={() => comErro(() => atestar.mutateAsync({
                        id: a.aditivo_id, aprovar: true,
                      }))}
                    >
                      <CheckCircle2 size={13} /> Aprovar
                    </Btn>
                    <BotaoReprovar
                      onConfirmar={motivo => comErro(() => atestar.mutateAsync({
                        id: a.aditivo_id, aprovar: false, observacao: motivo,
                      }))}
                    />
                  </>
                )}
                {(a.status === 'rascunho' || a.status === 'em_aprovacao') && podeEditar && (
                  <Btn
                    tam="sm"
                    onClick={() => comErro(() => cancelar.mutateAsync({ id: a.aditivo_id }))}
                  >
                    Cancelar
                  </Btn>
                )}
              </div>

              {a.status === 'aprovado' && a.itens.length > 0 && (
                <details style={{ marginTop: 8 }}>
                  <summary style={{ fontSize: 12, color: 'var(--ink-3)', cursor: 'pointer' }}>
                    O que ele mudou
                  </summary>
                  <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 3 }}>
                    {a.itens.map(i => (
                      <div key={i.item_aditivo_id} style={{ fontSize: 12, display: 'flex', gap: 8 }}>
                        <span style={{ fontFamily: 'var(--mono)' }}>{i.codigo}</span>
                        <span style={{ flex: 1, minWidth: 0 }}>{i.descricao}</span>
                        <span>{i.acao_rotulo}</span>
                        {Number(i.quantidade_delta) !== 0 && (
                          <Num>
                            {Number(i.quantidade_delta) > 0 ? '+' : ''}
                            {quantidade(i.quantidade_delta)} {i.unidade}
                          </Num>
                        )}
                        {i.preco_unitario_anterior && (
                          <Num>
                            {dinheiro(i.preco_unitario_anterior)} → {dinheiro(i.preco_unitario)}
                          </Num>
                        )}
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          ))}
        </div>
      )}

      {editando && (
        <ModalAditivo
          contratoId={contratoId}
          itens={itens}
          aditivo={editando === 'novo' ? null : editando}
          onClose={() => setEditando(null)}
        />
      )}
    </div>
  )
}

function BotaoReprovar({ onConfirmar }: { onConfirmar: (motivo: string) => void }) {
  const [aberto, setAberto] = useState(false)
  const [motivo, setMotivo] = useState('')
  return (
    <>
      <Btn tam="sm" variant="perigo" onClick={() => setAberto(true)}>Reprovar</Btn>
      {aberto && (
        <Modal
          titulo="Reprovar aditivo"
          onClose={() => setAberto(false)}
          rodape={
            <>
              <Btn onClick={() => setAberto(false)}>Voltar</Btn>
              <Btn
                variant="perigo"
                disabled={!motivo.trim()}
                onClick={() => { onConfirmar(motivo); setAberto(false) }}
              >
                Reprovar
              </Btn>
            </>
          }
        >
          <p style={{ fontSize: 13, color: 'var(--ink-2)', marginTop: 0 }}>
            Diga por quê. Quem montou o aditivo precisa saber o que corrigir —
            sem isso, a próxima versão volta com o mesmo problema.
          </p>
          <textarea
            value={motivo}
            onChange={e => setMotivo(e.target.value)}
            rows={3}
            style={campoTexto}
            placeholder="Ex.: o acréscimo do item 2.3 não tem projeto aprovado."
          />
        </Modal>
      )}
    </>
  )
}

interface Rascunho extends LinhaDeAditivo {
  chave: string
}

function ModalAditivo({ contratoId, itens, aditivo, onClose }: {
  contratoId: number
  itens: ItemDeContrato[]
  aditivo: Aditivo | null
  onClose: () => void
}) {
  const abrir = useAbrirAditivo(contratoId)
  const salvarItens = useSalvarItensDoAditivo(contratoId)

  const [objeto, setObjeto] = useState(aditivo?.objeto ?? '')
  const [justificativa, setJustificativa] = useState(aditivo?.justificativa ?? '')
  const [assinatura, setAssinatura] = useState(aditivo?.data_assinatura ?? '')
  const [novoFim, setNovoFim] = useState(aditivo?.nova_data_fim ?? '')
  const [erro, setErro] = useState<string | null>(null)
  const [linhas, setLinhas] = useState<Rascunho[]>(
    () => (aditivo?.itens ?? []).map((i, n) => ({
      chave: `e${i.item_aditivo_id}-${n}`,
      acao: i.acao,
      item_contrato_id: i.item_contrato,
      quantidade_delta: i.quantidade_delta,
      preco_unitario: i.preco_unitario,
      codigo_novo: i.item_contrato ? '' : i.codigo,
      descricao_nova: i.item_contrato ? '' : i.descricao,
      unidade_nova: i.item_contrato ? '' : i.unidade,
    })),
  )

  const porItem = useMemo(
    () => new Map(itens.map(i => [i.item_contrato_id, i])), [itens],
  )

  const mudar = (chave: string, mudanca: Partial<Rascunho>) =>
    setLinhas(antes => antes.map(l => (l.chave === chave ? { ...l, ...mudanca } : l)))

  const gravar = async () => {
    setErro(null)
    const payload: LinhaDeAditivo[] = linhas.map(({ chave: _c, ...l }) => ({
      ...l,
      quantidade_delta: l.quantidade_delta || '0',
      preco_unitario: l.preco_unitario || null,
    }))
    try {
      if (aditivo) {
        await salvarItens.mutateAsync({ id: aditivo.aditivo_id, itens: payload })
      } else {
        await abrir.mutateAsync({
          contrato: contratoId,
          objeto,
          justificativa,
          data_assinatura: assinatura || null,
          nova_data_fim: novoFim || null,
          itens: payload,
        })
      }
      onClose()
    } catch (e) {
      const campos = parseApiErrors(e)
      setErro(Object.values(campos).join(' · ') || 'Não deu para gravar o aditivo.')
    }
  }

  return (
    <Modal
      titulo={aditivo ? `Aditivo ${aditivo.numero}` : 'Novo aditivo'}
      onClose={onClose}
      rodape={
        <>
          <Btn onClick={onClose}>Cancelar</Btn>
          <Btn
            variant="brand"
            disabled={!objeto.trim() || !justificativa.trim()}
            onClick={gravar}
          >
            {aditivo ? 'Salvar linhas' : 'Abrir aditivo'}
          </Btn>
        </>
      }
    >
      {erro && (
        <div style={{
          padding: '9px 11px', borderRadius: 8, fontSize: 13, marginBottom: 12,
          background: 'var(--danger-soft)', color: 'var(--danger-ink)',
          whiteSpace: 'pre-wrap',
        }}>
          {erro}
        </div>
      )}

      <div style={{ display: 'grid', gap: 10, gridTemplateColumns: '1fr 1fr', marginBottom: 12 }}>
        <div style={{ gridColumn: '1 / -1' }}>
          <Rotulo>Objeto</Rotulo>
          <input
            value={objeto}
            disabled={Boolean(aditivo)}
            onChange={e => setObjeto(e.target.value)}
            placeholder="Ex.: acréscimo de 320 m² de alvenaria no bloco B"
            style={campo}
          />
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <Rotulo>Justificativa</Rotulo>
          <textarea
            value={justificativa}
            disabled={Boolean(aditivo)}
            onChange={e => setJustificativa(e.target.value)}
            rows={2}
            placeholder="O porquê. É o campo que a auditoria lê primeiro."
            style={campoTexto}
          />
        </div>
        <div>
          <Rotulo>Data de assinatura</Rotulo>
          <input
            type="date"
            value={assinatura}
            disabled={Boolean(aditivo)}
            onChange={e => setAssinatura(e.target.value)}
            style={campo}
          />
        </div>
        <div>
          <Rotulo>Nova data de fim (prorrogação)</Rotulo>
          <input
            type="date"
            value={novoFim}
            disabled={Boolean(aditivo)}
            onChange={e => setNovoFim(e.target.value)}
            style={campo}
          />
        </div>
      </div>

      <h3 style={{ margin: '0 0 8px', fontSize: 13 }}>Linhas</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {linhas.map(l => {
          const item = l.item_contrato_id ? porItem.get(l.item_contrato_id) : undefined
          const inclusao = l.acao === 'inclusao'
          return (
            <div
              key={l.chave}
              style={{
                border: '1px solid var(--line)', borderRadius: 9, padding: '10px 12px',
                display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end',
              }}
            >
              <div style={{ width: 150 }}>
                <Rotulo>Ação</Rotulo>
                <select
                  value={l.acao}
                  onChange={e => mudar(l.chave, { acao: e.target.value as AcaoAditivo })}
                  style={campo}
                >
                  <option value="acrescimo">Acréscimo</option>
                  <option value="supressao">Supressão</option>
                  <option value="preco">Revisão de preço</option>
                  <option value="inclusao">Item novo</option>
                </select>
              </div>

              {inclusao ? (
                <>
                  <div style={{ width: 110 }}>
                    <Rotulo>Código</Rotulo>
                    <input
                      value={l.codigo_novo ?? ''}
                      onChange={e => mudar(l.chave, { codigo_novo: e.target.value })}
                      style={campo}
                    />
                  </div>
                  <div style={{ flex: 1, minWidth: 160 }}>
                    <Rotulo>Descrição</Rotulo>
                    <input
                      value={l.descricao_nova ?? ''}
                      onChange={e => mudar(l.chave, { descricao_nova: e.target.value })}
                      style={campo}
                    />
                  </div>
                  <div style={{ width: 70 }}>
                    <Rotulo>Un.</Rotulo>
                    <input
                      value={l.unidade_nova ?? ''}
                      onChange={e => mudar(l.chave, { unidade_nova: e.target.value })}
                      style={campo}
                    />
                  </div>
                </>
              ) : (
                <div style={{ flex: 1, minWidth: 220 }}>
                  <Rotulo>Item do contrato</Rotulo>
                  <select
                    value={l.item_contrato_id ?? ''}
                    onChange={e => mudar(l.chave, {
                      item_contrato_id: e.target.value ? Number(e.target.value) : null,
                    })}
                    style={campo}
                  >
                    <option value="">escolha…</option>
                    {itens.map(i => (
                      <option key={i.item_contrato_id} value={i.item_contrato_id}>
                        {i.codigo} · {i.descricao}
                      </option>
                    ))}
                  </select>
                  {item && (
                    <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 3 }}>
                      hoje: {quantidade(item.quantidade_atual ?? item.quantidade_contratada)}
                      {' '}{item.unidade} × {dinheiro(item.preco_unitario)}
                    </div>
                  )}
                </div>
              )}

              {l.acao !== 'preco' && (
                <div style={{ width: 120 }}>
                  <Rotulo>
                    {l.acao === 'supressao' ? 'Δ (negativo)' : 'Quantidade'}
                  </Rotulo>
                  <input
                    value={l.quantidade_delta ?? ''}
                    inputMode="decimal"
                    onChange={e => mudar(l.chave, { quantidade_delta: e.target.value })}
                    style={{ ...campo, textAlign: 'right', fontFamily: 'var(--mono)' }}
                  />
                </div>
              )}

              {(l.acao === 'preco' || inclusao) && (
                <div style={{ width: 130 }}>
                  <Rotulo>Preço unitário</Rotulo>
                  <input
                    value={l.preco_unitario ?? ''}
                    inputMode="decimal"
                    onChange={e => mudar(l.chave, { preco_unitario: e.target.value })}
                    style={{ ...campo, textAlign: 'right', fontFamily: 'var(--mono)' }}
                  />
                </div>
              )}

              <Btn onClick={() => setLinhas(a => a.filter(x => x.chave !== l.chave))}>
                <Trash2 size={14} />
              </Btn>
            </div>
          )
        })}
      </div>

      <Btn
        style={{ marginTop: 10 }}
        onClick={() => setLinhas(a => [...a, {
          chave: `n${Date.now()}-${a.length}`,
          acao: 'acrescimo',
          item_contrato_id: null,
          quantidade_delta: '',
          preco_unitario: null,
        }])}
      >
        <Plus size={14} /> Acrescentar linha
      </Btn>

      <p style={{ margin: '12px 0 0', fontSize: 12, color: 'var(--ink-3)' }}>
        Nada aqui muda o contrato até o aditivo ser <strong>aprovado</strong>. A
        supressão não pode deixar a quantidade abaixo do que já foi medido, e no
        regime público os acréscimos são conferidos contra o limite declarado no
        contrato.
      </p>
    </Modal>
  )
}

function Rotulo({ children }: { children: React.ReactNode }) {
  return (
    <label style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)', marginBottom: 3 }}>
      {children}
    </label>
  )
}

const campo: React.CSSProperties = {
  width: '100%', padding: '7px 9px', borderRadius: 8,
  border: '1px solid var(--line)', background: 'var(--surface)',
  color: 'var(--ink)', fontSize: 13,
}
const campoTexto: React.CSSProperties = { ...campo, resize: 'vertical' }
