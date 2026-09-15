import { useMemo, useState } from 'react'
import { Link2Off, Pencil, Plus, Trash2 } from 'lucide-react'
import {
  Btn, CampoDecimal, CampoMoeda, Modal, Num, daApi, paraNumero,
} from '@/components/malha'
import { apiDecimalToCents, centsToApiDecimal } from '@/utils/money'
import { parseApiErrors } from '@/utils/formErrors'
import {
  useAtividadesDoContrato, useAtualizarItemDeContrato, useCriarItemDeContrato,
  useExcluirItemDeContrato,
} from '../hooks'
import type { ItemDeContrato } from '../types'

/**
 * **A planilha contratual — o que foi contratado, quanto e por qual preço.**
 *
 * *(Achado do dono, 15/09/2026, revisando o "+ novo contrato": ela não
 * existia.)* A API e os hooks estavam prontos desde a PDCA.3, e **nenhuma tela
 * os chamava** — então dava para criar o contrato, a grade de medição dizia
 * "cadastre os itens para poder medir", e não havia onde cadastrar. É a lição
 * da PRA.5c se repetindo: o botão não estava desabilitado, estava **ausente**,
 * e nenhum teste de API pegaria isso.
 *
 * **Por que aqui e não num modal de item por vez.** A planilha contratual chega
 * pronta do empreiteiro e se confere em bloco: a tabela mostra tudo, soma na
 * frente de quem lê, e o total confrontado com o valor global é o que denuncia
 * a divergência antes de a primeira medição existir — que é justamente a
 * validação que o backend faz no regime global.
 *
 * **A trava de edição é a do contrato, não a do item.** Contrato encerrado ou
 * cancelado não muda de planilha: medições já aprovadas foram calculadas sobre
 * ela. E item já medido não se exclui — a saída é o aditivo de supressão, que é
 * a PDCA.4.
 */

interface Props {
  contratoId: number
  obraId: number
  itens: ItemDeContrato[]
  /** Soma dos itens × valor fechado. Só o regime global exige que fechem. */
  regime: string
  valorGlobal: string | null
  editavel: boolean
  podeEditar: boolean
}

const dinheiro = (v: number) =>
  v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const quantidade = (v: string | number) =>
  Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 4 })

export default function PlanilhaContratual({
  contratoId, obraId, itens, regime, valorGlobal, editavel, podeEditar,
}: Props) {
  const [editando, setEditando] = useState<ItemDeContrato | null>(null)
  const [criando, setCriando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const excluir = useExcluirItemDeContrato(contratoId)

  const total = useMemo(
    () => itens.reduce(
      (s, i) => s + Number(i.quantidade_contratada) * Number(i.preco_unitario), 0,
    ),
    [itens],
  )
  const fechado = valorGlobal != null ? Number(valorGlobal) : null
  // No global a soma **tem** de fechar (o backend recusa a medição se não
  // fechar). Mostrar a diferença aqui é o que evita descobrir isso só na hora
  // de medir, que é semanas depois e com o empreiteiro esperando.
  const diverge = regime === 'global' && fechado != null
    && Math.abs(total - fechado) > 0.005

  async function comErro(acao: () => Promise<unknown>) {
    setErro(null)
    try { await acao() } catch (e) {
      const campos = parseApiErrors(e)
      setErro(Object.values(campos).join(' · ') || 'Não deu para concluir.')
    }
  }

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between',
        gap: 14, flexWrap: 'wrap', marginBottom: 12,
      }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 16 }}>Planilha contratual</h2>
          <p style={{ margin: '4px 0 0', color: 'var(--ink-3)', fontSize: 12.5, maxWidth: 560 }}>
            O que foi contratado, em que quantidade e por qual preço. É contra
            ela que a medição é conferida — e é o vínculo de cada linha com uma
            frente do cronograma que faz a medição nascer do avanço.
          </p>
        </div>
        {podeEditar && editavel && (
          <Btn variant="brand" onClick={() => setCriando(true)}>
            <Plus size={15} /> Novo item
          </Btn>
        )}
      </div>

      {erro && (
        <div style={{
          padding: '9px 11px', borderRadius: 8, fontSize: 12.5, marginBottom: 10,
          background: 'var(--danger-soft)', color: 'var(--danger-ink)',
        }}>{erro}</div>
      )}

      {itens.length === 0 ? (
        <p style={{
          color: 'var(--ink-2)', fontSize: 13, padding: '14px 12px',
          background: 'var(--surface-2)', borderRadius: 8, margin: 0,
        }}>
          Nenhum item ainda. <strong>Sem planilha não há o que medir</strong> — o
          contrato existe, mas a medição não tem linhas para propor.
          {podeEditar && editavel
            ? ' Comece pelo botão "Novo item".'
            : ' Quem cadastra é quem tem a permissão de editar contrato.'}
        </p>
      ) : (
        <div style={{ overflowX: 'auto', border: '1px solid var(--line)', borderRadius: 10 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 720 }}>
            <thead>
              <tr style={{ background: 'var(--surface-2)', textAlign: 'left' }}>
                <Th style={{ width: 78 }}>Item</Th>
                <Th>Descrição</Th>
                <Th style={{ width: 52 }}>Un.</Th>
                <Th n>Quantidade</Th>
                <Th n>Preço unit.</Th>
                <Th n>Valor</Th>
                {podeEditar && editavel && <Th style={{ width: 80 }} />}
              </tr>
            </thead>
            <tbody>
              {itens.map(item => (
                <tr key={item.item_contrato_id} style={{ borderTop: '1px solid var(--line)' }}>
                  <Td mono>{item.codigo}</Td>
                  <Td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span>{item.descricao}</span>
                      {/* O estado que o gestor precisa ver **no cadastro**, e não
                          descobrir na hora de medir: sem vínculo, o sistema não
                          consegue propor quantidade para esta linha. */}
                      {!item.tem_vinculo_de_avanco && (
                        <span
                          title="Sem atividade nem item orçado ligados — a medição não conseguirá propor quantidade para esta linha."
                          style={{ display: 'inline-flex', color: 'var(--accent-ink)' }}
                        >
                          <Link2Off size={13} />
                        </span>
                      )}
                      {item.atividade_nome && (
                        <span style={{ color: 'var(--ink-3)', fontSize: 11.5 }}>
                          · {item.atividade_nome}
                        </span>
                      )}
                    </div>
                  </Td>
                  <Td>{item.unidade}</Td>
                  <Td n><Num>{quantidade(item.quantidade_contratada)}</Num></Td>
                  <Td n><Num>{dinheiro(Number(item.preco_unitario))}</Num></Td>
                  <Td n><Num>{dinheiro(Number(item.valor_contratado))}</Num></Td>
                  {podeEditar && editavel && (
                    <Td n style={{ whiteSpace: 'nowrap' }}>
                      <Btn tam="sm" onClick={() => setEditando(item)}>
                        <Pencil size={13} />
                      </Btn>{' '}
                      <Btn
                        tam="sm" variant="perigo"
                        onClick={() => comErro(() => excluir.mutateAsync(item.item_contrato_id))}
                      >
                        <Trash2 size={13} />
                      </Btn>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ borderTop: '2px solid var(--line)', background: 'var(--surface-2)' }}>
                <Td colSpan={5} style={{ fontWeight: 600 }}>
                  {itens.length} {itens.length === 1 ? 'item' : 'itens'}
                </Td>
                <Td n style={{ fontWeight: 600 }}><Num>{dinheiro(total)}</Num></Td>
                {podeEditar && editavel && <Td />}
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {diverge && (
        <p style={{
          marginTop: 10, fontSize: 12.5, color: 'var(--danger-ink)',
          display: 'flex', gap: 6, alignItems: 'flex-start',
        }}>
          <span>
            <strong>A soma dos itens ({dinheiro(total)}) não fecha com o valor
            global do contrato ({dinheiro(fechado as number)}).</strong> No regime
            de preço global a planilha é o cronograma físico-financeiro, e a
            medição será recusada enquanto os dois não baterem — a diferença é de{' '}
            {dinheiro(Math.abs(total - (fechado as number)))}.
          </span>
        </p>
      )}

      {(criando || editando) && (
        <ModalItem
          contratoId={contratoId}
          obraId={obraId}
          item={editando ?? undefined}
          onClose={() => { setCriando(false); setEditando(null) }}
          proximoCodigo={String(itens.length + 1)}
        />
      )}
    </div>
  )
}

function ModalItem({ contratoId, obraId, item, onClose, proximoCodigo }: {
  contratoId: number
  obraId: number
  item?: ItemDeContrato
  onClose: () => void
  proximoCodigo: string
}) {
  const editando = item != null
  const criar = useCriarItemDeContrato(contratoId)
  const atualizar = useAtualizarItemDeContrato(contratoId)
  const atividades = useAtividadesDoContrato(obraId)
  const [erros, setErros] = useState<Record<string, string>>({})

  const [f, setF] = useState({
    codigo: item?.codigo ?? proximoCodigo,
    descricao: item?.descricao ?? '',
    unidade: item?.unidade ?? '',
    quantidade_contratada: daApi(item?.quantidade_contratada) || '',
    preco_unitario: apiDecimalToCents(item?.preco_unitario),
    atividade: item?.atividade ?? 0,
  })
  const set = <K extends keyof typeof f>(c: K, v: (typeof f)[K]) =>
    setF(a => ({ ...a, [c]: v }))

  const qtd = Number(paraNumero(f.quantidade_contratada) ?? 0)
  const total = qtd * (f.preco_unitario / 100)

  // **A mesma regra do banco, dita antes de sair da tela.** O backend recusa
  // quantidade zero (e agora com mensagem, [D133]); barrar aqui poupa a ida e
  // diz o porquê ao lado do campo, que é onde quem preenche está olhando.
  const faltando =
    !f.codigo.trim() ? 'Informe o número do item.'
      : !f.descricao.trim() ? 'Descreva o que este item contrata.'
        : qtd <= 0 ? 'A quantidade precisa ser maior que zero.'
          : null

  async function salvar() {
    setErros({})
    const payload = {
      contrato: contratoId,
      codigo: f.codigo.trim(),
      descricao: f.descricao.trim(),
      unidade: f.unidade.trim(),
      quantidade_contratada: paraNumero(f.quantidade_contratada) ?? '0',
      preco_unitario: centsToApiDecimal(f.preco_unitario),
      atividade: f.atividade || null,
    }
    try {
      if (editando) {
        await atualizar.mutateAsync({ id: item.item_contrato_id, payload })
      } else {
        await criar.mutateAsync(payload)
      }
      onClose()
    } catch (e) {
      setErros(parseApiErrors(e))
    }
  }

  const salvando = criar.isPending || atualizar.isPending

  return (
    <Modal
      titulo={editando ? `Item ${item.codigo}` : 'Novo item do contrato'}
      onClose={onClose}
      largura={560}
      rodape={
        <>
          {/* O motivo fica **ao lado do botão desabilitado**. Um botão apagado
              sem explicação faz a pessoa procurar o erro no campo errado. */}
          {faltando && (
            <span style={{ fontSize: 12.5, color: 'var(--ink-3)', marginRight: 'auto' }}>
              {faltando}
            </span>
          )}
          <Btn onClick={onClose}>Cancelar</Btn>
          <Btn
            variant="brand"
            disabled={salvando || faltando != null}
            onClick={salvar}
          >
            {salvando ? 'Salvando…' : 'Salvar'}
          </Btn>
        </>
      }
    >
      {Object.keys(erros).length > 0 && (
        <div style={{
          padding: '9px 11px', borderRadius: 8, fontSize: 12.5, marginBottom: 12,
          background: 'var(--danger-soft)', color: 'var(--danger-ink)',
        }}>
          {Object.entries(erros).map(([campo, msg]) => (
            <div key={campo}>{msg}</div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ width: 110 }}>
            <Rotulo>Item</Rotulo>
            <input
              value={f.codigo}
              onChange={e => set('codigo', e.target.value)}
              placeholder="1.1"
              style={entrada}
            />
          </div>
          <div style={{ flex: 1 }}>
            <Rotulo>Descrição</Rotulo>
            <input
              value={f.descricao}
              onChange={e => set('descricao', e.target.value)}
              placeholder="Alvenaria de blocos de concreto"
              style={entrada}
            />
          </div>
        </div>

        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ width: 90 }}>
            <Rotulo>Unidade</Rotulo>
            <input
              value={f.unidade}
              onChange={e => set('unidade', e.target.value)}
              placeholder="m2"
              style={entrada}
            />
          </div>
          <div style={{ flex: 1 }}>
            <Rotulo>Quantidade</Rotulo>
            <CampoDecimal
              valor={f.quantidade_contratada}
              aoMudar={v => set('quantidade_contratada', v)}
            />
          </div>
          <div style={{ flex: 1 }}>
            <Rotulo>Preço unitário</Rotulo>
            <CampoMoeda
              centavos={f.preco_unitario}
              aoMudar={v => set('preco_unitario', v)}
            />
          </div>
        </div>

        {/* O total aparece **enquanto se digita**, e não depois de salvar: é
            ele que denuncia a vírgula no lugar errado antes de a linha existir. */}
        <div style={{
          display: 'flex', justifyContent: 'flex-end', gap: 8, alignItems: 'baseline',
          padding: '8px 10px', background: 'var(--surface-2)', borderRadius: 8,
        }}>
          <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Valor desta linha</span>
          <Num size={16}>{dinheiro(total)}</Num>
        </div>

        <div>
          <Rotulo>Frente do cronograma que executa este item</Rotulo>
          <select
            value={f.atividade}
            onChange={e => set('atividade', Number(e.target.value))}
            style={entrada}
          >
            <option value={0}>Sem vínculo — a medição não proporá quantidade</option>
            {(atividades.data ?? []).map(a => (
              <option key={a.atividade_id} value={a.atividade_id}>
                {a.codigo} · {a.nome}
              </option>
            ))}
          </select>
          {/* A consequência dita **antes** da escolha, e não depois. */}
          <p style={ajuda}>
            {atividades.isLoading ? 'Carregando as frentes do plano…'
              : (atividades.data ?? []).length === 0
                ? 'Esta obra ainda não tem plano publicado com atividades. Sem o vínculo '
                  + 'a linha continua válida — só terá de ser medida à mão, digitando a '
                  + 'quantidade em vez de recebê-la do avanço apontado.'
                : 'É por este vínculo que o avanço apontado no canteiro vira quantidade '
                  + 'medida. Sem ele a linha é digitada à mão a cada medição.'}
          </p>
        </div>
      </div>
    </Modal>
  )
}

const entrada: React.CSSProperties = {
  width: '100%', padding: '8px 10px', borderRadius: 8,
  border: '1px solid var(--line)', background: 'var(--surface)',
  color: 'var(--ink)', fontSize: 13.5,
}
const ajuda: React.CSSProperties = {
  margin: '5px 0 0', fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.45,
}

function Rotulo({ children }: { children: React.ReactNode }) {
  return (
    <label style={{ display: 'block', fontSize: 12.5, color: 'var(--ink-2)', marginBottom: 4 }}>
      {children}
    </label>
  )
}

function Th({ children, n, style }: {
  children?: React.ReactNode; n?: boolean; style?: React.CSSProperties
}) {
  return (
    <th style={{
      padding: '9px 10px', fontWeight: 600, fontSize: 11.5, color: 'var(--ink-2)',
      textTransform: 'uppercase', letterSpacing: '.04em',
      textAlign: n ? 'right' : 'left', whiteSpace: 'nowrap', ...style,
    }}>{children}</th>
  )
}

function Td({ children, n, mono, style, colSpan }: {
  children?: React.ReactNode; n?: boolean; mono?: boolean
  style?: React.CSSProperties; colSpan?: number
}) {
  return (
    <td colSpan={colSpan} style={{
      padding: '7px 10px', textAlign: n ? 'right' : 'left',
      fontFamily: mono ? 'var(--mono)' : undefined, verticalAlign: 'middle', ...style,
    }}>{children}</td>
  )
}
