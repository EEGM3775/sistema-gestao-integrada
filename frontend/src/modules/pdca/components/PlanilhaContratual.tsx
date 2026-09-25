import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Link2Off, Lock, Plus } from 'lucide-react'
import {
  Btn, CampoDecimal, CampoMoeda, Card, Empty, Loading, Num, Pill, SectionHead,
  daApi, paraNumero,
} from '@/components/malha'
import { apiDecimalToCents, centsToApiDecimal, formatBRL } from '@/utils/money'
import type { ItemContrato, LinhaDeContrato } from '../types'

/** **A planilha contratual** — o que foi combinado, item a item.
 *
 *  Ela **fecha** quando alguém já mediu contra ela, e a trava vem do servidor
 *  (`planilha_editavel` + o motivo). A tela lê a resposta em vez de
 *  reimplementar a condição: uma prop de interface não protege o comando de
 *  bancada, a importação nem a aba antiga aberta no navegador — e foi assim
 *  que uma quantidade contratada foi de 53.150 para 631.500 enquanto a tela
 *  dizia que a planilha não se editava mais. */
export function PlanilhaContratual({
  contrato, itens, carregando, salvando, aoCriar, aoSalvar, aoRemover,
}: {
  contrato: LinhaDeContrato
  itens: ItemContrato[]
  carregando: boolean
  salvando?: boolean
  aoCriar?: (corpo: Partial<ItemContrato>) => void
  aoSalvar?: (id: number, corpo: Partial<ItemContrato>) => void
  aoRemover?: (id: number) => void
}) {
  const [novo, setNovo] = useState(false)
  const editavel = contrato.planilha_editavel && aoSalvar != null

  if (carregando) return <Loading o="a planilha do contrato" />

  return (
    <section>
      <SectionHead
        sub={
          itens.length > 0
            ? `${itens.length} ${itens.length === 1 ? 'item' : 'itens'} · ${formatBRL(apiDecimalToCents(contrato.saldo.valor_contratado))} contratados`
            : undefined
        }
        right={
          editavel && !novo ? (
            <Btn tam="sm" onClick={() => setNovo(true)}>
              <Plus size={13} />
              Novo item
            </Btn>
          ) : undefined
        }
      >
        Planilha contratual
      </SectionHead>

      {/* A trava, dita com a frase do servidor — a mesma que a API devolveria
          ao recusar a edição. Duas redações divergiriam na primeira mudança. */}
      {!contrato.planilha_editavel && (
        <div
          style={{
            display: 'flex', alignItems: 'flex-start', gap: 8,
            padding: '9px 12px', borderRadius: 'var(--r-sm)',
            background: 'var(--inset)', color: 'var(--ink-2)',
            fontSize: 12.5, lineHeight: 1.55, marginBottom: 10,
          }}
        >
          <Lock size={14} style={{ flexShrink: 0, marginTop: 2, color: 'var(--ink-3)' }} />
          <span>{contrato.planilha_fechada_porque.replace(/\*\*/g, '')}</span>
        </div>
      )}

      {novo && aoCriar && (
        <div style={{ marginBottom: 10 }}>
          <LinhaNova
            contratoId={contrato.contrato}
            salvando={salvando}
            aoCancelar={() => setNovo(false)}
            aoCriar={(corpo) => {
              aoCriar(corpo)
              setNovo(false)
            }}
          />
        </div>
      )}

      {itens.length === 0 && !novo ? (
        <Card>
          <Empty>
            <span style={{ lineHeight: 1.6 }}>
              Este contrato ainda não tem itens. Cadastre o que foi combinado —
              código, descrição, unidade, quantidade e preço — para poder medir.
            </span>
            {editavel && (
              <Btn variant="primary" onClick={() => setNovo(true)}>
                <Plus size={14} />
                Cadastrar o primeiro item
              </Btn>
            )}
          </Empty>
        </Card>
      ) : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
              <thead>
                <tr>
                  {[
                    { r: 'Item', a: 'left' },
                    { r: 'Descrição', a: 'left' },
                    { r: 'Un', a: 'left' },
                    { r: 'Contratado hoje', a: 'right' },
                    { r: 'Preço unitário', a: 'right' },
                    { r: 'Valor', a: 'right' },
                    { r: 'Serviço ligado', a: 'left' },
                    { r: '', a: 'right' },
                  ].map((coluna, i) => (
                    <th
                      key={coluna.r || `acao-${i}`}
                      style={{
                        textAlign: coluna.a as 'left' | 'right',
                        padding: '8px 10px', fontSize: 10.5, fontWeight: 700,
                        letterSpacing: '0.07em', textTransform: 'uppercase',
                        color: 'var(--ink-3)', whiteSpace: 'nowrap',
                        borderBottom: '1px solid var(--line)',
                        background: 'var(--surface-2)',
                      }}
                    >
                      {coluna.r}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {itens.map((item) => (
                  <LinhaDoItem
                    key={item.item_id}
                    item={item}
                    editavel={editavel}
                    salvando={salvando}
                    aoSalvar={aoSalvar}
                    aoRemover={aoRemover}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </section>
  )
}

function LinhaDoItem({
  item, editavel, salvando, aoSalvar, aoRemover,
}: {
  item: ItemContrato
  editavel: boolean
  salvando?: boolean
  aoSalvar?: (id: number, corpo: Partial<ItemContrato>) => void
  aoRemover?: (id: number) => void
}) {
  const [quantidade, setQuantidade] = useState(daApi(item.quantidade_contratada))
  const [preco, setPreco] = useState(apiDecimalToCents(item.preco_unitario))

  const mudou = quantidade !== daApi(item.quantidade_contratada)
    || preco !== apiDecimalToCents(item.preco_unitario)

  const aditivada = apiDecimalToCents(item.quantidade_aditivada) !== 0

  return (
    <tr style={{ borderBottom: '1px solid var(--line-2)' }}>
      <td style={{ padding: '7px 10px', fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink-2)' }}>
        {item.codigo}
      </td>
      <td style={{ padding: '7px 10px', fontSize: 12.5, color: 'var(--ink)', maxWidth: 280 }}>
        <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {item.descricao}
        </div>
      </td>
      <td style={{ padding: '7px 10px', fontSize: 12, color: 'var(--ink-3)' }}>
        {item.unidade}
      </td>

      <td style={{ padding: '5px 10px', textAlign: 'right', minWidth: 130 }}>
        {editavel ? (
          <CampoDecimal
            valor={quantidade}
            aoMudar={setQuantidade}
            aria-label={`Quantidade contratada de ${item.codigo}`}
          />
        ) : (
          <Num size={12.5} tone="var(--ink-2)">{daApi(item.quantidade_atual)}</Num>
        )}
        {/* O que vale hoje é original + aditivos: num contrato aditado a
            quantidade da assinatura já não governa nada. */}
        {aditivada && (
          <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 2 }}>
            {daApi(item.quantidade_contratada)} + {daApi(item.quantidade_aditivada)} de aditivo
          </div>
        )}
      </td>

      <td style={{ padding: '5px 10px', textAlign: 'right', minWidth: 140 }}>
        {editavel ? (
          <CampoMoeda
            centavos={preco}
            aoMudar={setPreco}
            aria-label={`Preço unitário de ${item.codigo}`}
          />
        ) : (
          <Num size={12.5} tone="var(--ink-2)">
            {formatBRL(apiDecimalToCents(item.preco_unitario))}
          </Num>
        )}
      </td>

      <td style={{ padding: '7px 10px', textAlign: 'right', whiteSpace: 'nowrap' }}>
        <Num size={12.5} tone="var(--ink)">
          {formatBRL(apiDecimalToCents(item.valor_contratado))}
        </Num>
      </td>

      {/* "Sem vínculo" é estado que o gestor precisa **ver aqui**, e não
          descobrir na hora de medir, quando a linha não recebe proposta. */}
      <td style={{ padding: '7px 10px', fontSize: 12, color: 'var(--ink-3)', maxWidth: 200 }}>
        {item.tem_vinculo_de_avanco ? (
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>
            {item.atividade_nome ?? item.item_orcado_descricao}
          </span>
        ) : (
          <Pill kind="info" title="Sem serviço ligado, a medição não consegue propor quantidade para este item">
            <Link2Off size={10} />
            sem vínculo
          </Pill>
        )}
      </td>

      <td style={{ padding: '5px 10px', textAlign: 'right', whiteSpace: 'nowrap' }}>
        {editavel && (
          <div style={{ display: 'inline-flex', gap: 6 }}>
            {mudou && (
              <Btn
                tam="sm"
                variant="primary"
                disabled={salvando}
                onClick={() =>
                  aoSalvar?.(item.item_id, {
                    quantidade_contratada: paraNumero(quantidade) ?? '0',
                    preco_unitario: centsToApiDecimal(preco),
                  })}
              >
                Gravar
              </Btn>
            )}
            {aoRemover && (
              <Btn tam="sm" disabled={salvando} onClick={() => aoRemover(item.item_id)}>
                Excluir
              </Btn>
            )}
          </div>
        )}
      </td>
    </tr>
  )
}

/** O item novo. Nasce sem vínculo de propósito — ligar ao cronograma é uma
 *  segunda decisão, e obrigá-la aqui impediria de cadastrar a planilha antes
 *  de o plano existir. */
function LinhaNova({
  contratoId, salvando, aoCriar, aoCancelar,
}: {
  contratoId: number
  salvando?: boolean
  aoCriar: (corpo: Partial<ItemContrato>) => void
  aoCancelar: () => void
}) {
  const [codigo, setCodigo] = useState('')
  const [descricao, setDescricao] = useState('')
  const [unidade, setUnidade] = useState('')
  const [quantidade, setQuantidade] = useState('')
  const [preco, setPreco] = useState(0)

  const completo = codigo.trim() && descricao.trim() && unidade.trim()
    && Number(paraNumero(quantidade) ?? '0') > 0

  const campo = {
    padding: '7px 10px', borderRadius: 8, fontSize: 12.5,
    border: '1px solid var(--line)', background: 'var(--surface)',
    color: 'var(--ink)',
  } as const

  return (
    <Card>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          value={codigo} onChange={(e) => setCodigo(e.target.value)}
          placeholder="Item" aria-label="Código do item" autoFocus
          style={{ ...campo, width: 90 }}
        />
        <input
          value={descricao} onChange={(e) => setDescricao(e.target.value)}
          placeholder="Descrição do serviço" aria-label="Descrição"
          style={{ ...campo, flex: 1, minWidth: 220 }}
        />
        <input
          value={unidade} onChange={(e) => setUnidade(e.target.value)}
          placeholder="un" aria-label="Unidade"
          style={{ ...campo, width: 70 }}
        />
        <div style={{ width: 130 }}>
          <CampoDecimal
            valor={quantidade} aoMudar={setQuantidade}
            aria-label="Quantidade contratada"
          />
        </div>
        <div style={{ width: 150 }}>
          <CampoMoeda centavos={preco} aoMudar={setPreco} aria-label="Preço unitário" />
        </div>
        <Btn tam="sm" onClick={aoCancelar}>Deixar para depois</Btn>
        <Btn
          tam="sm"
          variant="primary"
          disabled={!completo || salvando}
          onClick={() =>
            aoCriar({
              contrato: contratoId,
              codigo: codigo.trim(),
              descricao: descricao.trim(),
              unidade: unidade.trim(),
              quantidade_contratada: paraNumero(quantidade) ?? '0',
              preco_unitario: centsToApiDecimal(preco),
            })}
        >
          Incluir
        </Btn>
      </div>
      <p style={{ margin: '10px 0 0', fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
        O item nasce sem serviço ligado. Para a medição propor quantidade
        sozinha, ligue-o depois a uma atividade do plano —{' '}
        <Link to="../plano" style={{ color: 'var(--brand)', textDecoration: 'none' }}>
          abrir o plano
          <ArrowUpRight size={11} style={{ verticalAlign: '-1px' }} />
        </Link>
      </p>
    </Card>
  )
}
