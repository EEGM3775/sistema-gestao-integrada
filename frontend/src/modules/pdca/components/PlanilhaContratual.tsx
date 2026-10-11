import { useMemo, useState } from 'react'
import { ClipboardPaste, GanttChartSquare, Calculator, Lock, Plus, X } from 'lucide-react'
import {
  Btn, CampoDecimal, CampoMoeda, Card, Empty, Loading, Num, SectionHead,
  daApi, paraNumero,
} from '@/components/malha'
import { apiDecimalToCents, centsToApiDecimal, formatBRL } from '@/utils/money'
import { contemSemAcento } from '@/utils/texto'
import { usePdca } from '../contexto'
import { useFontesDaPlanilha, useIncluirNaPlanilha } from '../hooks'
import { mensagemDe } from '../montagem'
import type { FontesDaPlanilha, ItemContrato, LinhaDeContrato, LinhaParaPlanilha } from '../types'

/** Ordem natural de código: 01, 02, 03… e 1.2 antes de 1.10 — e não a ordem
 *  em que as linhas foram criadas (o dono viu "01 04 03 02"). */
const porCodigo = (a: ItemContrato, b: ItemContrato) =>
  a.codigo.localeCompare(b.codigo, 'pt-BR', { numeric: true })

type Fonte = 'orcamento' | 'plano' | 'excel' | 'avulso'

/** **A planilha contratual** — o que foi combinado, item a item.
 *
 *  Monta-se de quatro jeitos, porque é assim que contrato de empreitada nasce
 *  (decisão do dono, 10/10/2026): **do orçamento** (descrição, unidade,
 *  quantidade e preço já vêm, ligados ao item orçado), **do plano** (ligado à
 *  atividade, a medição propõe pelo avanço dela), **colando do Excel** ou
 *  digitando. Toda linha se edita inteira e escolhe o seu vínculo na própria
 *  linha.
 *
 *  Ela **fecha** quando alguém já mediu contra ela, e a trava vem do servidor
 *  (`planilha_editavel` + o motivo); daí em diante muda-se por aditivo. */
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
  const { obraId } = usePdca()
  const editavel = contrato.planilha_editavel && aoSalvar != null
  const [fonte, setFonte] = useState<Fonte | null>(null)
  const fontes = useFontesDaPlanilha(contrato.contrato, editavel)
  const ordenados = useMemo(() => [...itens].sort(porCodigo), [itens])

  if (carregando) return <Loading o="a planilha do contrato" />

  const soma = itens.reduce((t, i) => t + apiDecimalToCents(i.valor_contratado), 0)
  const fechado = apiDecimalToCents(contrato.saldo.valor_contratado)

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <SectionHead
        sub={itens.length > 0
          ? `${itens.length} ${itens.length === 1 ? 'item' : 'itens'} · ${formatBRL(soma)}`
            + (contrato.regime !== 'unitario' && soma !== fechado
              ? ` · o contrato vale o fechado de ${formatBRL(fechado)} (${contrato.regime_rotulo.toLowerCase()})`
              : '')
          : undefined}
        right={editavel ? (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <Btn tam="sm" onClick={() => setFonte('orcamento')}><Calculator size={13} /> Do orçamento</Btn>
            <Btn tam="sm" onClick={() => setFonte('plano')}><GanttChartSquare size={13} /> Do plano</Btn>
            <Btn tam="sm" onClick={() => setFonte('excel')}><ClipboardPaste size={13} /> Colar do Excel</Btn>
            <Btn tam="sm" onClick={() => setFonte('avulso')}><Plus size={13} /> Item</Btn>
          </div>
        ) : undefined}
      >
        Planilha contratual
      </SectionHead>

      {!contrato.planilha_editavel && (
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.55 }}>
          <Lock size={14} style={{ flexShrink: 0, marginTop: 2 }} />
          <span>{contrato.planilha_fechada_porque.replace(/\*\*/g, '')}</span>
        </div>
      )}

      {fonte && editavel && (
        <Card>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
            <span style={{ flex: 1, fontSize: 13, fontWeight: 700, color: 'var(--ink)' }}>
              {{ orcamento: 'Trazer do orçamento', plano: 'Trazer do plano', excel: 'Colar do Excel', avulso: 'Novo item' }[fonte]}
            </span>
            <button type="button" aria-label="Fechar" onClick={() => setFonte(null)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)', display: 'flex' }}>
              <X size={15} />
            </button>
          </div>
          {fonte === 'avulso' && aoCriar && (
            <LinhaNova
              contratoId={contrato.contrato}
              salvando={salvando}
              aoCancelar={() => setFonte(null)}
              aoCriar={(corpo) => { aoCriar(corpo); setFonte(null) }}
            />
          )}
          {fonte !== 'avulso' && (
            <Importador
              fonte={fonte}
              contratoId={contrato.contrato}
              obraId={obraId}
              fontes={fontes.data}
              carregando={fontes.isLoading}
              aoConcluir={() => setFonte(null)}
            />
          )}
        </Card>
      )}

      {itens.length === 0 && !fonte ? (
        <Card>
          <Empty>
            <span style={{ lineHeight: 1.6 }}>
              O que foi combinado com o empreiteiro, item a item. Traga do orçamento ou do plano,
              cole a planilha do contrato, ou digite.
            </span>
            {editavel && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'center' }}>
                <Btn variant="primary" onClick={() => setFonte('orcamento')}><Calculator size={14} /> Do orçamento</Btn>
                <Btn onClick={() => setFonte('plano')}><GanttChartSquare size={14} /> Do plano</Btn>
                <Btn onClick={() => setFonte('excel')}><ClipboardPaste size={14} /> Colar do Excel</Btn>
              </div>
            )}
          </Empty>
        </Card>
      ) : itens.length > 0 && (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1040 }}>
              <thead>
                <tr>
                  {[
                    { r: 'Item', a: 'left' }, { r: 'Descrição', a: 'left' }, { r: 'Un', a: 'left' },
                    { r: 'Quantidade', a: 'right' }, { r: 'Preço unitário', a: 'right' },
                    { r: 'Valor', a: 'right' }, { r: 'Ligado a', a: 'left' }, { r: '', a: 'right' },
                  ].map((coluna, i) => (
                    <th key={coluna.r || `acao-${i}`} style={{
                      textAlign: coluna.a as 'left' | 'right', padding: '8px 10px', fontSize: 10.5,
                      fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase',
                      color: 'var(--ink-3)', whiteSpace: 'nowrap', borderBottom: '1px solid var(--line)',
                      background: 'var(--surface-2)',
                    }}>
                      {coluna.r}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ordenados.map((item) => (
                  <LinhaDoItem
                    key={item.item_contrato_id}
                    item={item}
                    fontes={fontes.data}
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

const CAMPO = {
  padding: '6px 8px', borderRadius: 7, fontSize: 12.5, width: '100%',
  border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink)',
} as const

/** O vínculo como valor de um `<select>`: `a:12` atividade, `o:34` item orçado. */
function vinculoDe(item: Pick<ItemContrato, 'atividade' | 'item_orcado'>): string {
  if (item.atividade != null) return `a:${item.atividade}`
  if (item.item_orcado != null) return `o:${item.item_orcado}`
  return ''
}

function SeletorDeVinculo({ valor, fontes, aoMudar, rotulo }: {
  valor: string
  fontes: FontesDaPlanilha | undefined
  aoMudar: (v: string) => void
  rotulo: string
}) {
  return (
    <select value={valor} onChange={(e) => aoMudar(e.target.value)} aria-label={rotulo} style={{ ...CAMPO, minWidth: 180 }}>
      <option value="">— sem vínculo (digita na medição)</option>
      {(fontes?.atividades.length ?? 0) > 0 && (
        <optgroup label="Atividade do plano (propõe pelo avanço)">
          {fontes!.atividades.map((a) => <option key={`a${a.atividade}`} value={`a:${a.atividade}`}>{a.codigo} · {a.nome}</option>)}
        </optgroup>
      )}
      {(fontes?.itens_orcados.length ?? 0) > 0 && (
        <optgroup label="Item do orçamento">
          {fontes!.itens_orcados.map((o) => <option key={`o${o.item_orcado}`} value={`o:${o.item_orcado}`}>{o.codigo} · {o.descricao}</option>)}
        </optgroup>
      )}
    </select>
  )
}

function LinhaDoItem({
  item, fontes, editavel, salvando, aoSalvar, aoRemover,
}: {
  item: ItemContrato
  fontes: FontesDaPlanilha | undefined
  editavel: boolean
  salvando?: boolean
  aoSalvar?: (id: number, corpo: Partial<ItemContrato>) => void
  aoRemover?: (id: number) => void
}) {
  const [codigo, setCodigo] = useState(item.codigo)
  const [descricao, setDescricao] = useState(item.descricao)
  const [unidade, setUnidade] = useState(item.unidade)
  const [quantidade, setQuantidade] = useState(daApi(item.quantidade_contratada))
  const [preco, setPreco] = useState(apiDecimalToCents(item.preco_unitario))
  const [vinculo, setVinculo] = useState(vinculoDe(item))

  const mudou = codigo !== item.codigo || descricao !== item.descricao || unidade !== item.unidade
    || quantidade !== daApi(item.quantidade_contratada) || preco !== apiDecimalToCents(item.preco_unitario)
    || vinculo !== vinculoDe(item)
  const aditivada = apiDecimalToCents(item.quantidade_aditivada) !== 0
  const td = { padding: '5px 8px', verticalAlign: 'middle' as const }

  function gravar() {
    aoSalvar?.(item.item_contrato_id, {
      codigo: codigo.trim(), descricao: descricao.trim(), unidade: unidade.trim(),
      quantidade_contratada: paraNumero(quantidade) ?? '0',
      preco_unitario: centsToApiDecimal(preco),
      atividade: vinculo.startsWith('a:') ? Number(vinculo.slice(2)) : null,
      item_orcado: vinculo.startsWith('o:') ? Number(vinculo.slice(2)) : null,
    })
  }

  if (!editavel) {
    return (
      <tr style={{ borderBottom: '1px solid var(--line-2)' }}>
        <td style={{ ...td, fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink-2)' }}>{item.codigo}</td>
        <td style={{ ...td, fontSize: 12.5, color: 'var(--ink)' }}>{item.descricao}</td>
        <td style={{ ...td, fontSize: 12, color: 'var(--ink-3)' }}>{item.unidade}</td>
        <td style={{ ...td, textAlign: 'right' }}>
          <Num size={12.5} tone="var(--ink-2)">{daApi(item.quantidade_atual)}</Num>
          {aditivada && <div style={{ fontSize: 10, color: 'var(--ink-3)' }}>{daApi(item.quantidade_contratada)} + {daApi(item.quantidade_aditivada)} de aditivo</div>}
        </td>
        <td style={{ ...td, textAlign: 'right' }}><Num size={12.5} tone="var(--ink-2)">{formatBRL(apiDecimalToCents(item.preco_unitario))}</Num></td>
        <td style={{ ...td, textAlign: 'right' }}><Num size={12.5} tone="var(--ink)">{formatBRL(apiDecimalToCents(item.valor_contratado))}</Num></td>
        <td style={{ ...td, fontSize: 12, color: 'var(--ink-3)' }}>{item.atividade_nome ?? item.item_orcado_descricao ?? '—'}</td>
        <td />
      </tr>
    )
  }

  return (
    <tr style={{ borderBottom: '1px solid var(--line-2)' }}>
      <td style={{ ...td, width: 84 }}>
        <input value={codigo} onChange={(e) => setCodigo(e.target.value)} aria-label="Código do item" style={{ ...CAMPO, fontFamily: 'var(--mono)' }} />
      </td>
      <td style={{ ...td, minWidth: 220 }}>
        <input value={descricao} onChange={(e) => setDescricao(e.target.value)} aria-label={`Descrição de ${item.codigo}`} style={CAMPO} />
      </td>
      <td style={{ ...td, width: 64 }}>
        <input value={unidade} onChange={(e) => setUnidade(e.target.value)} aria-label={`Unidade de ${item.codigo}`} style={CAMPO} />
      </td>
      <td style={{ ...td, width: 120 }}>
        <CampoDecimal valor={quantidade} aoMudar={setQuantidade} aria-label={`Quantidade contratada de ${item.codigo}`} />
      </td>
      <td style={{ ...td, width: 140 }}>
        <CampoMoeda centavos={preco} aoMudar={setPreco} aria-label={`Preço unitário de ${item.codigo}`} />
      </td>
      <td style={{ ...td, textAlign: 'right', whiteSpace: 'nowrap' }}>
        <Num size={12.5} tone="var(--ink)">{formatBRL(apiDecimalToCents(item.valor_contratado))}</Num>
      </td>
      <td style={td}>
        <SeletorDeVinculo valor={vinculo} fontes={fontes} aoMudar={setVinculo} rotulo={`Vínculo de ${item.codigo}`} />
      </td>
      <td style={{ ...td, textAlign: 'right', whiteSpace: 'nowrap' }}>
        <div style={{ display: 'inline-flex', gap: 6 }}>
          {mudou && <Btn tam="sm" variant="primary" disabled={salvando} onClick={gravar}>Gravar</Btn>}
          {aoRemover && <Btn tam="sm" disabled={salvando} onClick={() => aoRemover(item.item_contrato_id)}>Excluir</Btn>}
        </div>
      </td>
    </tr>
  )
}

/** O item avulso, digitado. Nasce com o vínculo escolhido ali mesmo. */
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

  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
      <input value={codigo} onChange={(e) => setCodigo(e.target.value)} placeholder="Item" aria-label="Código do item" autoFocus style={{ ...CAMPO, width: 90 }} />
      <input value={descricao} onChange={(e) => setDescricao(e.target.value)} placeholder="Descrição do serviço" aria-label="Descrição" style={{ ...CAMPO, flex: 1, minWidth: 220, width: 'auto' }} />
      <input value={unidade} onChange={(e) => setUnidade(e.target.value)} placeholder="un" aria-label="Unidade" style={{ ...CAMPO, width: 70 }} />
      <div style={{ width: 130 }}><CampoDecimal valor={quantidade} aoMudar={setQuantidade} aria-label="Quantidade contratada" /></div>
      <div style={{ width: 150 }}><CampoMoeda centavos={preco} aoMudar={setPreco} aria-label="Preço unitário" /></div>
      <Btn tam="sm" onClick={aoCancelar}>Cancelar</Btn>
      <Btn
        tam="sm" variant="primary" disabled={!completo || salvando}
        onClick={() => aoCriar({
          contrato: contratoId, codigo: codigo.trim(), descricao: descricao.trim(),
          unidade: unidade.trim(), quantidade_contratada: paraNumero(quantidade) ?? '0',
          preco_unitario: centsToApiDecimal(preco),
        })}
      >
        Incluir
      </Btn>
    </div>
  )
}

/** Lê o que veio do Excel: código, descrição, unidade, quantidade, preço —
 *  separado por tabulação (o copiar do Excel) ou ponto e vírgula. */
function lerColagem(texto: string): LinhaParaPlanilha[] {
  const numero = (v: string) => (v || '').replace(/[R$\s]/g, '').replace(/\.(?=\d{3}(\D|$))/g, '').replace(',', '.')
  return texto.split(/\r?\n/).map((l) => l.trim()).filter(Boolean).map((l) => {
    const c = l.split(l.includes('\t') ? '\t' : ';').map((x) => x.trim())
    return {
      codigo: c[0] ?? '', descricao: c[1] ?? '', unidade: c[2] ?? '',
      quantidade_contratada: numero(c[3] ?? ''), preco_unitario: numero(c[4] ?? '0') || '0',
    }
  }).filter((l) => !(l.codigo.toLowerCase() === 'item' || l.descricao.toLowerCase() === 'descrição'))
}

function Importador({ fonte, contratoId, obraId, fontes, carregando, aoConcluir }: {
  fonte: 'orcamento' | 'plano' | 'excel'
  contratoId: number
  obraId: number | undefined
  fontes: FontesDaPlanilha | undefined
  carregando: boolean
  aoConcluir: () => void
}) {
  const incluir = useIncluirNaPlanilha(obraId)
  const [marcados, setMarcados] = useState<Set<number>>(new Set())
  const [busca, setBusca] = useState('')
  const [texto, setTexto] = useState('')
  const [erro, setErro] = useState<string | null>(null)

  const colagem = useMemo(() => (fonte === 'excel' ? lerColagem(texto) : []), [fonte, texto])
  if (carregando && fonte !== 'excel') return <Loading o="as fontes da planilha" />

  const opcoes = fonte === 'orcamento'
    ? (fontes?.itens_orcados ?? []).map((o) => ({ id: o.item_orcado, codigo: o.codigo, texto: o.descricao, extra: `${daApi(o.quantidade)} ${o.unidade} · ${formatBRL(apiDecimalToCents(o.preco_unitario))}`, ja: o.ja_no_contrato }))
    : fonte === 'plano'
      ? (fontes?.atividades ?? []).map((a) => ({ id: a.atividade, codigo: a.codigo, texto: a.nome, extra: '', ja: a.ja_no_contrato }))
      : []
  const visiveis = opcoes.filter((o) => !busca.trim() || contemSemAcento(`${o.codigo} ${o.texto}`, busca))

  function linhas(): LinhaParaPlanilha[] {
    if (fonte === 'excel') return colagem
    if (fonte === 'orcamento') {
      return (fontes?.itens_orcados ?? []).filter((o) => marcados.has(o.item_orcado)).map((o) => ({
        codigo: o.codigo || String(o.item_orcado), descricao: o.descricao, unidade: o.unidade,
        quantidade_contratada: o.quantidade, preco_unitario: o.preco_unitario, item_orcado: o.item_orcado,
      }))
    }
    return (fontes?.atividades ?? []).filter((a) => marcados.has(a.atividade)).map((a) => ({
      codigo: a.codigo, descricao: a.nome, unidade: 'vb', quantidade_contratada: '1',
      preco_unitario: '0', atividade: a.atividade,
    }))
  }

  async function confirmar() {
    setErro(null)
    try {
      await incluir.mutateAsync({ id: contratoId, linhas: linhas() })
      aoConcluir()
    } catch (e) {
      setErro(mensagemDe(e))
    }
  }

  const quantas = fonte === 'excel' ? colagem.length : marcados.size
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {fonte === 'excel' ? (
        <>
          <textarea
            value={texto} onChange={(e) => setTexto(e.target.value)} rows={8} autoFocus
            placeholder={'Item\tDescrição\tUn\tQuantidade\tPreço unitário\n01\tAssentar manilhas\tm\t75\t2.500,00'}
            aria-label="Linhas coladas do Excel"
            style={{ ...CAMPO, fontFamily: 'var(--mono)', fontSize: 12, resize: 'vertical' }}
          />
          <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
            Cinco colunas, nesta ordem: item, descrição, unidade, quantidade e preço unitário.
            {colagem.length > 0 && ` ${colagem.length} linha(s) lidas.`}
          </span>
        </>
      ) : opcoes.length === 0 ? (
        <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
          {fonte === 'orcamento' ? 'A obra não tem orçamento aprovado com itens.' : 'O plano da obra ainda não tem atividades.'}
        </span>
      ) : (
        <>
          <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Procurar" aria-label="Procurar" style={CAMPO} />
          <div style={{ maxHeight: 320, overflowY: 'auto', border: '1px solid var(--line-2)', borderRadius: 'var(--r-sm)' }}>
            {visiveis.map((o) => (
              <label key={o.id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '6px 10px', borderBottom: '1px solid var(--line-2)', fontSize: 12.5, color: o.ja ? 'var(--ink-3)' : 'var(--ink)', cursor: o.ja ? 'default' : 'pointer' }}>
                <input
                  type="checkbox" disabled={o.ja} checked={marcados.has(o.id)}
                  onChange={() => setMarcados((s) => { const n = new Set(s); if (n.has(o.id)) n.delete(o.id); else n.add(o.id); return n })}
                />
                <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-3)', minWidth: 54 }}>{o.codigo}</span>
                <span style={{ flex: 1 }}>{o.texto}</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--ink-3)' }}>{o.ja ? 'já na planilha' : o.extra}</span>
              </label>
            ))}
          </div>
          {fonte === 'plano' && (
            <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
              Cada atividade entra como 1 vb ligada a ela; ajuste quantidade e preço na planilha.
            </span>
          )}
        </>
      )}
      {erro && <span style={{ fontSize: 12, color: 'var(--danger-ink)', whiteSpace: 'pre-line' }}>{erro}</span>}
      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
        <Btn tam="sm" onClick={aoConcluir}>Cancelar</Btn>
        <Btn tam="sm" variant="primary" disabled={quantas === 0 || incluir.isPending} onClick={() => void confirmar()}>
          {incluir.isPending ? 'Incluindo…' : `Incluir ${quantas || ''} ${quantas === 1 ? 'item' : 'itens'}`}
        </Btn>
      </div>
    </div>
  )
}
