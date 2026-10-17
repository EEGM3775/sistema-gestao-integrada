/* A cotação alimentada por quem compra (dono, 16/10/2026): "cotação também pode
 * ser alimentada pelo usuário, tanto com importação quanto digitando — a rede
 * ainda não está no ar". O preço chega por telefone, e-mail ou WhatsApp e entra
 * aqui; ou o fornecedor devolve a planilha da cotação preenchida. E o mapa
 * comparativo sai em PDF/XLSX, uma ou várias cotações. */
import { useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Download, FileSpreadsheet, FileText, Pencil, Trash2 } from 'lucide-react'
import { BotaoExportar, SeletorDeFornecedor, WizardImportacao } from '@/components/malha'
import { parseApiErrors } from '@/utils/formErrors'
import { alterarProposta, apagarProposta, mapaDeCotacoes, registrarProposta } from '../api/scmApi'
import { scmKeys } from '../api/queryKeys'
import { brl, qty, num } from '../lib'
import { Btn, Erro, Field, Modal } from './ui'
import { CAPS, inp, lerDecimal, mono, type Say } from './estilo'
import type { ItemDemanda, Proposta } from '../types'

const hoje = () => new Date().toLocaleDateString('sv-SE')
const descricao = (it: ItemDemanda) => it.produto_descricao ?? it.descricao_servico ?? `Item #${it.item_demanda_id}`
const erroDe = (e: unknown, padrao: string) => Object.values(parseApiErrors(e))[0] ?? padrao

/** Digitar (ou corrigir) a proposta de um fornecedor. Item sem preço = não cotado. */
export function PropostaModal({ cotacao, itens, proposta, precosAtuais, onClose, say }: {
  cotacao: number
  itens: ItemDemanda[]
  /** Com ela, edita; sem, registra uma nova. */
  proposta?: Proposta
  /** `item_demanda → preço` da proposta em edição. */
  precosAtuais?: Map<number, string>
  onClose: () => void
  say: Say
}) {
  const qc = useQueryClient()
  const [fornecedor, setFornecedor] = useState<number | null>(proposta?.fornecedor ?? null)
  const [recebida, setRecebida] = useState(proposta?.recebida_em ?? hoje())
  const [prazo, setPrazo] = useState(proposta?.prazo_entrega_dias != null ? String(proposta.prazo_entrega_dias) : '')
  const [observacao, setObservacao] = useState(proposta?.observacao ?? '')
  const [precos, setPrecos] = useState<Record<number, string>>(() => Object.fromEntries(
    itens.map(it => [it.item_demanda_id, precosAtuais?.get(it.item_demanda_id)?.replace('.', ',') ?? '']),
  ))
  const [erro, setErro] = useState('')
  const [salvando, setSalvando] = useState(false)

  const total = itens.reduce((s, it) => s + (lerDecimal(precos[it.item_demanda_id] ?? '') ?? 0) * (num(it.quantidade) ?? 0), 0)
  const cotados = itens.filter(it => lerDecimal(precos[it.item_demanda_id] ?? '') != null).length

  async function salvar() {
    if (fornecedor == null) { setErro('Escolha o fornecedor.'); return }
    if (cotados === 0) { setErro('Informe o preço de pelo menos um item.'); return }
    const corpo = {
      fornecedor, recebida_em: recebida, observacao,
      prazo_entrega_dias: prazo.trim() ? Number(prazo) : null,
      itens: itens.map(it => ({ item_demanda: it.item_demanda_id, preco_unitario: String(lerDecimal(precos[it.item_demanda_id] ?? '') ?? '') })),
    }
    setSalvando(true); setErro('')
    try {
      if (proposta) await alterarProposta(cotacao, proposta.proposta_id, corpo)
      else await registrarProposta(cotacao, corpo)
      await qc.invalidateQueries({ queryKey: scmKeys.all })
      say(proposta ? 'Proposta corrigida' : 'Proposta registrada')
      onClose()
    } catch (e) {
      setErro(erroDe(e, 'Não foi possível salvar a proposta.'))
      setSalvando(false)
    }
  }

  return (
    <Modal title={proposta ? 'Corrigir proposta' : 'Registrar proposta'} onClose={onClose} largura={720}
      footer={<>
        <span style={{ marginRight: 'auto', alignSelf: 'center', fontSize: 12.5, color: 'var(--ink-2)' }}>
          {cotados} de {itens.length} itens · total <b style={mono}>{brl(total)}</b>
        </span>
        <Btn onClick={onClose}>Cancelar</Btn>
        <Btn variant="primary" onClick={salvar} disabled={salvando}>{salvando ? 'Salvando…' : 'Salvar proposta'}</Btn>
      </>}>
      <Erro msg={erro} />
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,2fr) minmax(0,1fr) minmax(0,1fr)', gap: 12 }}>
        <Field label="Fornecedor">
          <SeletorDeFornecedor valor={fornecedor} aoMudar={id => setFornecedor(id)} />
        </Field>
        <Field label="Recebida em">
          <input type="date" value={recebida} max={hoje()} onChange={e => setRecebida(e.target.value)} style={inp} />
        </Field>
        <Field label="Prazo de entrega (dias)">
          <input inputMode="numeric" value={prazo} onChange={e => setPrazo(e.target.value.replace(/\D/g, ''))} placeholder="—" style={{ ...inp, ...mono }} />
        </Field>
      </div>
      <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', overflow: 'hidden', marginBottom: 14 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead><tr>
            {['Item', 'Qtd.', 'Preço unitário', 'Subtotal'].map((h, i) => (
              <th key={h} style={{ ...CAPS, fontSize: 10, padding: '8px 10px', textAlign: i === 0 ? 'left' : 'right', background: 'var(--surface-2)', borderBottom: '1px solid var(--line)' }}>{h}</th>
            ))}
          </tr></thead>
          <tbody>{itens.map(it => {
            const v = lerDecimal(precos[it.item_demanda_id] ?? '')
            return (
              <tr key={it.item_demanda_id} style={{ borderBottom: '1px solid var(--line-2)' }}>
                <td style={{ padding: '7px 10px', color: 'var(--ink)' }}>{descricao(it)}</td>
                <td style={{ padding: '7px 10px', textAlign: 'right', ...mono, color: 'var(--ink-2)', whiteSpace: 'nowrap' }}>{qty(it.quantidade)} {it.unidade || 'un'}</td>
                <td style={{ padding: '5px 10px', width: 150 }}>
                  <input inputMode="decimal" value={precos[it.item_demanda_id] ?? ''} placeholder="não cotou"
                    onChange={e => setPrecos(p => ({ ...p, [it.item_demanda_id]: e.target.value }))}
                    style={{ ...inp, ...mono, textAlign: 'right', padding: '6px 9px' }} />
                </td>
                <td style={{ padding: '7px 10px', textAlign: 'right', ...mono, color: v == null ? 'var(--ink-3)' : 'var(--ink)' }}>
                  {v == null ? '—' : brl(v * (num(it.quantidade) ?? 0))}
                </td>
              </tr>
            )
          })}</tbody>
        </table>
      </div>
      <Field label="Observação (frete, condição de pagamento, validade…)">
        <textarea value={observacao} onChange={e => setObservacao(e.target.value)} rows={2} style={{ ...inp, resize: 'vertical' }} />
      </Field>
    </Modal>
  )
}

/** Corrigir / apagar a proposta, no pé da coluna do mapa — só com a cotação aberta. */
export function AcoesDaProposta({ cotacao, proposta, itens, precos, say }: {
  cotacao: number; proposta: Proposta; itens: ItemDemanda[]; precos: Map<number, string>; say: Say
}) {
  const qc = useQueryClient()
  const [editar, setEditar] = useState(false)
  async function apagar() {
    if (!window.confirm(`Apagar a proposta de ${proposta.fornecedor_label ?? proposta.fornecedor_nome}?`)) return
    try {
      await apagarProposta(cotacao, proposta.proposta_id)
      await qc.invalidateQueries({ queryKey: scmKeys.all })
      say('Proposta apagada')
    } catch (e) { say(erroDe(e, 'Não foi possível apagar a proposta.')) }
  }
  return (
    <span style={{ display: 'flex', gap: 4 }}>
      <Btn style={{ padding: '5px 8px' }} title="Corrigir a proposta" onClick={() => setEditar(true)}><Pencil size={13} /></Btn>
      <Btn style={{ padding: '5px 8px' }} title="Apagar a proposta" onClick={apagar}><Trash2 size={13} /></Btn>
      {editar && <PropostaModal cotacao={cotacao} itens={itens} proposta={proposta} precosAtuais={precos} onClose={() => setEditar(false)} say={say} />}
    </span>
  )
}

/** A planilha que vai ao fornecedor e a que volta preenchida. */
export function PlanilhaDaCotacao({ cotacao, say }: { cotacao: number; say: Say }) {
  const qc = useQueryClient()
  const [importar, setImportar] = useState(false)
  const [fornecedor, setFornecedor] = useState<number | null>(null)
  const [recebida, setRecebida] = useState(hoje())
  const [prazo, setPrazo] = useState('')
  return (
    <>
      <BotaoExportar recurso="scm.proposta" recorte={{ cotacao }} rotulo="Planilha para cotação" />
      <Btn style={{ padding: '6px 12px', fontSize: 12.5 }} onClick={() => setImportar(true)} title="Sobe a planilha que o fornecedor devolveu com os preços">
        <FileSpreadsheet size={14} /> Importar proposta
      </Btn>
      {importar && (
        <Modal title="Importar a proposta de um fornecedor" onClose={() => setImportar(false)} largura={560}
          footer={<Btn onClick={() => setImportar(false)}>Fechar</Btn>}>
          <p style={{ fontSize: 12.5, color: 'var(--ink-2)', marginBottom: 14, lineHeight: 1.5 }}>
            Use a <b>planilha para cotação</b>: ele preenche a coluna de preço e devolve.
            Linha sem preço é item que ele não cotou. A planilha vira a proposta dele de uma vez — ou nada entra.
          </p>
          <Field label="De qual fornecedor é a planilha">
            <SeletorDeFornecedor valor={fornecedor} aoMudar={id => setFornecedor(id)} />
          </Field>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Field label="Recebida em"><input type="date" value={recebida} max={hoje()} onChange={e => setRecebida(e.target.value)} style={inp} /></Field>
            <Field label="Prazo de entrega (dias)"><input inputMode="numeric" value={prazo} onChange={e => setPrazo(e.target.value.replace(/\D/g, ''))} placeholder="—" style={{ ...inp, ...mono }} /></Field>
          </div>
          {fornecedor == null
            ? <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Escolha o fornecedor para subir a planilha.</div>
            : <WizardImportacao recurso="scm.proposta" rotulo="Escolher a planilha" tam="md"
                contexto={{ cotacao, fornecedor, recebida_em: recebida, prazo_entrega_dias: prazo || null }}
                onConcluida={() => { qc.invalidateQueries({ queryKey: scmKeys.all }); setImportar(false); say('Proposta importada') }} />}
        </Modal>
      )}
    </>
  )
}

/** "Exportar mapa" — PDF para projetar/imprimir ou XLSX para mexer nos números. */
export function BotaoMapa({ ids, rotulo = 'Exportar mapa', say }: { ids: number[]; rotulo?: string; say: Say }) {
  const [aberto, setAberto] = useState(false)
  const [baixando, setBaixando] = useState(false)
  async function baixar(formato: 'pdf' | 'xlsx') {
    setBaixando(true); setAberto(false)
    try {
      const blob = await mapaDeCotacoes(ids, formato)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = ids.length === 1 ? `mapa-cotacao-${ids[0]}.${formato}` : `mapas-de-cotacao.${formato}`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      say(erroDe(e, 'Não foi possível gerar o mapa.'))
    } finally {
      setBaixando(false)
    }
  }
  return (
    <span style={{ position: 'relative', display: 'inline-flex' }}>
      <Btn style={{ padding: '6px 12px', fontSize: 12.5 }} disabled={baixando || ids.length === 0} onClick={() => setAberto(a => !a)}>
        <Download size={14} /> {baixando ? 'Gerando…' : rotulo}
      </Btn>
      {aberto && (
        <span role="menu" style={{ position: 'absolute', right: 0, top: 'calc(100% + 4px)', zIndex: 20, minWidth: 140, background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', boxShadow: 'var(--shadow-md)', padding: 4 }}>
          <ItemMenu onClick={() => baixar('pdf')} icone={<FileText size={14} />} titulo="PDF" />
          <ItemMenu onClick={() => baixar('xlsx')} icone={<FileSpreadsheet size={14} />} titulo="Excel" />
        </span>
      )}
    </span>
  )
}

function ItemMenu({ onClick, icone, titulo }: { onClick: () => void; icone: ReactNode; titulo: string }) {
  return (
    <button type="button" role="menuitem" onClick={onClick}
      style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%', textAlign: 'left', padding: '8px 10px', border: 0, background: 'transparent', borderRadius: 6, cursor: 'pointer', color: 'var(--ink)' }}
      onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-2)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
      <span style={{ color: 'var(--ink-3)', display: 'flex' }}>{icone}</span>
      <span style={{ fontSize: 13, fontWeight: 600 }}>{titulo}</span>
    </button>
  )
}
