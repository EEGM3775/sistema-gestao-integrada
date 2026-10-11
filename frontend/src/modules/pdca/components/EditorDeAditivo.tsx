import { useMemo, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Btn, CampoDecimal, Card, Loading, Num, SectionHead, daApi, paraNumero } from '@/components/malha'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import type {
  AcaoAditivo, AditivoContrato, ItemContrato, LinhaDeAditivoEntrada, LinhaDeContrato,
} from '../types'
import type { CabecalhoDoAditivo } from '../api/pdcaApi'

type AcaoNaLinha = 'nada' | Exclude<AcaoAditivo, 'inclusao'>

interface Mexida { acao: AcaoNaLinha; quantidade: string; preco: string; retencao: string }
interface ItemNovo { codigo: string; descricao: string; unidade: string; quantidade: string; preco: string; retencao: string }

const NADA: Mexida = { acao: 'nada', quantidade: '', preco: '', retencao: '' }
const num = (v: string) => Number(paraNumero(v) ?? '0')
const centavos = (reais: number) => Math.round(reais * 100)

/** **O aditivo montado como um contrato** *(decisão do dono, 11/10/2026)*.
 *
 *  "Aditivo não tem como fazer nada, deveria ser uma perna do criar contrato":
 *  o rascunho nascia só com objeto e justificativa e não havia tela para as
 *  linhas. Aqui ele se monta inteiro, dentro da aba de aditivos — o que muda
 *  no contrato (objeto, motivo, prazo, **retenção**), cada item existente
 *  (acréscimo, supressão, preço novo, retenção própria), os itens novos, e o
 *  antes → depois do contratado enquanto se digita. A conta da tela é só a
 *  prévia; o número que vale é o `resumo` do servidor, depois de gravar. */
export function EditorDeAditivo({
  contrato, itens, carregandoItens, aditivo, ocupado, erro, aoSalvar, aoFechar,
}: {
  contrato: LinhaDeContrato
  itens: ItemContrato[]
  carregandoItens: boolean
  /** O rascunho em edição; `null` = aditivo novo. */
  aditivo: AditivoContrato | null
  ocupado?: boolean
  erro?: string | null
  aoSalvar: (corpo: { cabecalho: CabecalhoDoAditivo; itens: LinhaDeAditivoEntrada[]; enviar: boolean }) => void
  aoFechar: () => void
}) {
  const [objeto, setObjeto] = useState(aditivo?.objeto ?? '')
  const [justificativa, setJustificativa] = useState(aditivo?.justificativa ?? '')
  const [assinatura, setAssinatura] = useState(aditivo?.data_assinatura ?? '')
  const [novoFim, setNovoFim] = useState(aditivo?.nova_data_fim ?? '')
  const [mudaRetencao, setMudaRetencao] = useState(aditivo?.retencao_percentual_nova != null)
  const [retencao, setRetencao] = useState(daApi(aditivo?.retencao_percentual_nova ?? ''))

  const [mexidas, setMexidas] = useState<Map<number, Mexida>>(() => {
    const m = new Map<number, Mexida>()
    for (const l of aditivo?.itens ?? []) {
      if (l.acao === 'inclusao' || l.item_contrato == null) continue
      m.set(l.item_contrato, {
        acao: l.acao,
        quantidade: daApi(Math.abs(Number(l.quantidade_delta))),
        preco: daApi(l.preco_unitario ?? ''),
        retencao: daApi(l.retencao_percentual ?? ''),
      })
    }
    return m
  })
  const [novos, setNovos] = useState<ItemNovo[]>(() =>
    (aditivo?.itens ?? []).filter((l) => l.acao === 'inclusao').map((l) => ({
      codigo: l.codigo_novo, descricao: l.descricao_nova, unidade: l.unidade_nova,
      quantidade: daApi(l.quantidade_delta), preco: daApi(l.preco_unitario ?? ''),
      retencao: daApi(l.retencao_percentual ?? ''),
    })),
  )

  function mexer(id: number, campo: keyof Mexida, valor: string) {
    setMexidas((antes) => {
      const m = new Map(antes)
      m.set(id, { ...(m.get(id) ?? NADA), [campo]: valor })
      return m
    })
  }
  function mudarNovo(i: number, campo: keyof ItemNovo, valor: string) {
    setNovos((antes) => antes.map((n, j) => (j === i ? { ...n, [campo]: valor } : n)))
  }

  /** A prévia do antes → depois, linha a linha (só para ver enquanto digita). */
  const previa = useMemo(() => {
    let delta = 0
    const porItem = new Map<number, { depois: number; valorDepois: number; dif: number }>()
    for (const item of itens) {
      const m = mexidas.get(item.item_contrato_id)
      const atual = Number(item.quantidade_atual)
      const preco = Number(item.preco_unitario)
      let depois = atual
      let precoDepois = preco
      if (m?.acao === 'acrescimo') depois = atual + num(m.quantidade)
      if (m?.acao === 'supressao') depois = atual - num(m.quantidade)
      if (m?.acao === 'preco' && paraNumero(m.preco) != null) precoDepois = num(m.preco)
      const dif = centavos(depois * precoDepois) - centavos(atual * preco)
      delta += dif
      porItem.set(item.item_contrato_id, { depois, valorDepois: centavos(depois * precoDepois), dif })
    }
    for (const n of novos) delta += centavos(num(n.quantidade) * num(n.preco))
    return { delta, porItem }
  }, [itens, mexidas, novos])

  const atual = apiDecimalToCents(contrato.saldo.valor_contratado)
  const original = apiDecimalToCents(contrato.saldo.valor_original)
  const acumulado = apiDecimalToCents(contrato.saldo.valor_aditivado) + previa.delta
  const completo = objeto.trim() !== '' && justificativa.trim() !== ''

  function montar(enviar: boolean) {
    const linhas: LinhaDeAditivoEntrada[] = []
    for (const [id, m] of mexidas) {
      if (m.acao === 'nada') continue
      const ret = paraNumero(m.retencao)
      linhas.push({
        acao: m.acao,
        item_contrato_id: id,
        quantidade_delta: m.acao === 'preco' ? '0'
          : String((m.acao === 'supressao' ? -1 : 1) * num(m.quantidade)),
        preco_unitario: m.acao === 'preco' ? paraNumero(m.preco) : null,
        retencao_percentual: ret,
      })
    }
    for (const n of novos) {
      linhas.push({
        acao: 'inclusao',
        codigo_novo: n.codigo.trim(),
        descricao_nova: n.descricao.trim(),
        unidade_nova: n.unidade.trim(),
        quantidade_delta: paraNumero(n.quantidade) ?? '0',
        preco_unitario: paraNumero(n.preco),
        retencao_percentual: paraNumero(n.retencao),
      })
    }
    aoSalvar({
      enviar,
      itens: linhas,
      cabecalho: {
        objeto: objeto.trim(),
        justificativa: justificativa.trim(),
        data_assinatura: assinatura || null,
        nova_data_fim: novoFim || null,
        retencao_percentual_nova: mudaRetencao ? paraNumero(retencao) : null,
      },
    })
  }

  const campo = {
    width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid var(--line)',
    background: 'var(--surface)', color: 'var(--ink)', fontSize: 13, fontFamily: 'inherit',
  } as const
  const rotulo = {
    display: 'block', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.07em',
    color: 'var(--ink-3)', fontWeight: 700, marginBottom: 5,
  } as const
  const th = (a: 'left' | 'right' = 'left') => ({
    textAlign: a, padding: '8px 8px', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.07em',
    textTransform: 'uppercase' as const, color: 'var(--ink-3)', whiteSpace: 'nowrap' as const,
    borderBottom: '1px solid var(--line)', background: 'var(--surface-2)',
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <SectionHead
        sub={aditivo ? `rascunho do aditivo ${aditivo.numero} · nada muda no contrato até a aprovação` : 'nasce em rascunho · nada muda no contrato até a aprovação'}
        right={<Btn tam="sm" onClick={aoFechar}>Voltar aos aditivos</Btn>}
      >
        {aditivo ? `Aditivo ${aditivo.numero}` : 'Novo aditivo'} · contrato {contrato.numero}
      </SectionHead>

      {erro && (
        <div style={{ padding: '9px 12px', borderRadius: 'var(--r-sm)', background: 'var(--danger-soft)', color: 'var(--danger-ink)', fontSize: 12.5, lineHeight: 1.5 }}>
          {erro}
        </div>
      )}

      {/* --- 1. o termo -------------------------------------------------- */}
      <Card>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14 }}>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={rotulo}>Objeto — o que este aditivo muda</label>
            <input value={objeto} onChange={(e) => setObjeto(e.target.value)} style={campo} autoFocus={!aditivo} />
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={rotulo}>Justificativa — por que foi preciso</label>
            <textarea value={justificativa} onChange={(e) => setJustificativa(e.target.value)} rows={2} style={{ ...campo, resize: 'vertical' }} />
          </div>
          <div>
            <label style={rotulo}>Data da assinatura</label>
            <input type="date" value={assinatura} onChange={(e) => setAssinatura(e.target.value)} style={campo} />
          </div>
          <div>
            <label style={rotulo}>Prorrogar o fim para</label>
            <input type="date" value={novoFim} onChange={(e) => setNovoFim(e.target.value)} style={campo} />
            <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
              hoje: {contrato.data_fim ? contrato.data_fim.split('-').reverse().join('/') : 'sem fim'}
            </span>
          </div>
          <div>
            <label style={rotulo}>Retenção do contrato</label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--ink-2)', marginBottom: 6 }}>
              <input type="checkbox" checked={mudaRetencao} onChange={(e) => setMudaRetencao(e.target.checked)} />
              este aditivo muda a retenção
            </label>
            {mudaRetencao && (
              <CampoDecimal valor={retencao} aoMudar={setRetencao} sufixo="%" casas={2} aria-label="Nova retenção do contrato" />
            )}
            <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
              vale para as medições abertas depois da aprovação
            </span>
          </div>
        </div>
      </Card>

      {/* --- 2. os itens que já existem --------------------------------- */}
      <section>
        <SectionHead sub="acréscimo, supressão ou preço novo — e, se quiser, uma retenção própria para o item">
          Itens do contrato
        </SectionHead>
        {carregandoItens ? <Loading o="os itens do contrato" /> : (
          <Card pad={false} style={{ overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980, fontSize: 12.5 }}>
                <thead>
                  <tr>
                    <th style={th()}>Item</th>
                    <th style={th()}>Descrição</th>
                    <th style={th('right')}>Hoje</th>
                    <th style={th()}>O que muda</th>
                    <th style={th('right')}>Quantidade / preço</th>
                    <th style={th('right')}>Retenção própria</th>
                    <th style={th('right')}>Depois</th>
                    <th style={th('right')}>Δ R$</th>
                  </tr>
                </thead>
                <tbody>
                  {itens.map((item) => {
                    const m = mexidas.get(item.item_contrato_id) ?? NADA
                    const p = previa.porItem.get(item.item_contrato_id)
                    return (
                      <tr key={item.item_contrato_id} style={{ borderBottom: '1px solid var(--line-2)', background: m.acao !== 'nada' ? 'var(--accent-soft)' : undefined }}>
                        <td style={{ padding: '6px 8px', fontFamily: 'var(--mono)', fontSize: 12 }}>{item.codigo}</td>
                        <td style={{ padding: '6px 8px', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.descricao}</td>
                        <td style={{ padding: '6px 8px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                          <Num size={12} tone="var(--ink-2)">{daApi(item.quantidade_atual)} {item.unidade}</Num>
                          <div style={{ fontSize: 10, color: 'var(--ink-3)' }}>{formatBRL(apiDecimalToCents(item.preco_unitario))}/{item.unidade}</div>
                        </td>
                        <td style={{ padding: '4px 8px' }}>
                          <select
                            value={m.acao}
                            onChange={(e) => mexer(item.item_contrato_id, 'acao', e.target.value)}
                            aria-label={`O que muda em ${item.codigo}`}
                            style={{ ...campo, padding: '5px 6px', fontSize: 12 }}
                          >
                            <option value="nada">— não muda</option>
                            <option value="acrescimo">Acréscimo</option>
                            <option value="supressao">Supressão</option>
                            <option value="preco">Preço novo</option>
                          </select>
                        </td>
                        <td style={{ padding: '4px 8px', minWidth: 120 }}>
                          {m.acao === 'acrescimo' || m.acao === 'supressao' ? (
                            <CampoDecimal valor={m.quantidade} aoMudar={(v) => mexer(item.item_contrato_id, 'quantidade', v)}
                              sufixo={item.unidade} aria-label={`Quantidade de ${item.codigo}`} />
                          ) : m.acao === 'preco' ? (
                            <CampoDecimal valor={m.preco} aoMudar={(v) => mexer(item.item_contrato_id, 'preco', v)}
                              sufixo="R$" aria-label={`Preço novo de ${item.codigo}`} />
                          ) : null}
                        </td>
                        <td style={{ padding: '4px 8px', minWidth: 96 }}>
                          {m.acao !== 'nada' && (
                            <CampoDecimal valor={m.retencao} aoMudar={(v) => mexer(item.item_contrato_id, 'retencao', v)}
                              sufixo="%" casas={2} placeholder={item.retencao_percentual ? daApi(item.retencao_percentual) : 'do contrato'}
                              aria-label={`Retenção própria de ${item.codigo}`} />
                          )}
                        </td>
                        <td style={{ padding: '6px 8px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                          {p && m.acao !== 'nada' ? (
                            <>
                              <Num size={12} tone="var(--ink)">{daApi(Math.round(p.depois * 10000) / 10000)} {item.unidade}</Num>
                              <div style={{ fontSize: 10, color: 'var(--ink-3)' }}>{formatBRL(p.valorDepois)}</div>
                            </>
                          ) : <span style={{ color: 'var(--ink-3)' }}>—</span>}
                        </td>
                        <td style={{ padding: '6px 8px', textAlign: 'right' }}>
                          {p && p.dif !== 0 ? (
                            <Num size={12} tone={p.dif < 0 ? 'var(--danger-ink)' : 'var(--good-ink)'}>
                              {p.dif > 0 ? '+' : '−'} {formatBRL(Math.abs(p.dif))}
                            </Num>
                          ) : <span style={{ color: 'var(--ink-3)' }}>—</span>}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </section>

      {/* --- 3. os itens novos -------------------------------------------- */}
      <section>
        <SectionHead
          sub="o serviço que não estava no contrato — com retenção própria, se for o caso"
          right={(
            <Btn tam="sm" onClick={() => setNovos((n) => [...n, { codigo: '', descricao: '', unidade: '', quantidade: '', preco: '', retencao: '' }])}>
              <Plus size={13} /> Item novo
            </Btn>
          )}
        >
          Itens novos
        </SectionHead>
        {novos.length === 0 ? (
          <p style={{ margin: 0, fontSize: 12, color: 'var(--ink-3)' }}>Nenhum item novo neste aditivo.</p>
        ) : (
          <Card pad={false} style={{ overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900, fontSize: 12.5 }}>
                <thead>
                  <tr>
                    <th style={th()}>Código</th>
                    <th style={th()}>Descrição</th>
                    <th style={th()}>Un</th>
                    <th style={th('right')}>Quantidade</th>
                    <th style={th('right')}>Preço unitário</th>
                    <th style={th('right')}>Retenção própria</th>
                    <th style={th('right')}>Valor</th>
                    <th style={th()} />
                  </tr>
                </thead>
                <tbody>
                  {novos.map((n, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--line-2)' }}>
                      <td style={{ padding: '4px 8px', width: 90 }}><input value={n.codigo} onChange={(e) => mudarNovo(i, 'codigo', e.target.value)} style={{ ...campo, padding: '5px 6px' }} aria-label="Código do item novo" /></td>
                      <td style={{ padding: '4px 8px' }}><input value={n.descricao} onChange={(e) => mudarNovo(i, 'descricao', e.target.value)} style={{ ...campo, padding: '5px 6px' }} aria-label="Descrição do item novo" /></td>
                      <td style={{ padding: '4px 8px', width: 70 }}><input value={n.unidade} onChange={(e) => mudarNovo(i, 'unidade', e.target.value)} style={{ ...campo, padding: '5px 6px' }} aria-label="Unidade do item novo" /></td>
                      <td style={{ padding: '4px 8px', width: 120 }}><CampoDecimal valor={n.quantidade} aoMudar={(v) => mudarNovo(i, 'quantidade', v)} aria-label="Quantidade do item novo" /></td>
                      <td style={{ padding: '4px 8px', width: 130 }}><CampoDecimal valor={n.preco} aoMudar={(v) => mudarNovo(i, 'preco', v)} sufixo="R$" aria-label="Preço do item novo" /></td>
                      <td style={{ padding: '4px 8px', width: 100 }}><CampoDecimal valor={n.retencao} aoMudar={(v) => mudarNovo(i, 'retencao', v)} sufixo="%" casas={2} placeholder="do contrato" aria-label="Retenção própria do item novo" /></td>
                      <td style={{ padding: '6px 8px', textAlign: 'right' }}><Num size={12}>{formatBRL(centavos(num(n.quantidade) * num(n.preco)))}</Num></td>
                      <td style={{ padding: '4px 8px', width: 36 }}>
                        <button type="button" onClick={() => setNovos((v) => v.filter((_, j) => j !== i))} aria-label="Tirar o item novo"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)' }}>
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </section>

      {/* --- 4. antes → depois, e os gestos -------------------------------- */}
      <Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: 22, flexWrap: 'wrap' }}>
          <div>
            <div style={rotulo}>Contratado hoje</div>
            <Num size={15} tone="var(--ink-2)" align="left">{formatBRL(atual)}</Num>
          </div>
          <div>
            <div style={rotulo}>Este aditivo</div>
            <Num size={15} align="left" tone={previa.delta < 0 ? 'var(--danger-ink)' : previa.delta > 0 ? 'var(--good-ink)' : 'var(--ink-3)'}>
              {previa.delta === 0 ? '—' : `${previa.delta > 0 ? '+' : '−'} ${formatBRL(Math.abs(previa.delta))}`}
            </Num>
          </div>
          <div>
            <div style={rotulo}>Contratado depois</div>
            <Num size={17} weight={750} align="left">{formatBRL(atual + previa.delta)}</Num>
          </div>
          {original > 0 && (
            <div>
              <div style={rotulo}>Aditivos sobre o original</div>
              <Num size={15} align="left" tone="var(--ink-2)">
                {((acumulado / original) * 100).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%
              </Num>
            </div>
          )}
          <span style={{ flex: 1 }} />
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Btn onClick={aoFechar}>Descartar mudanças</Btn>
            <Btn disabled={!completo || ocupado} onClick={() => montar(false)}>
              {ocupado ? 'Gravando…' : 'Salvar rascunho'}
            </Btn>
            <Btn variant="primary" disabled={!completo || ocupado} onClick={() => montar(true)}>
              Salvar e enviar para aprovação
            </Btn>
          </div>
        </div>
        {!completo && (
          <p style={{ margin: '10px 0 0', fontSize: 11.5, color: 'var(--ink-3)' }}>
            Objeto e justificativa são obrigatórios — é o que a auditoria lê primeiro.
          </p>
        )}
      </Card>
    </div>
  )
}
