/* O pedido de compra de ponta a ponta (D284, dono, 11/10/2026).
 *
 * Uma chamada (`pedidos/{id}/painel/`) traz tudo: linhas com o saldo, os
 * recebimentos, as NF-e, a cobrança com os títulos do ERP, o histórico e o que
 * está pendente. Quem decide se o pedido se edita livre, só no saldo ou nada é o
 * servidor (`regime`) — a tela lê e mostra, não reimplementa a regra. */
import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  ArrowLeft, PackageCheck, Star, FileText, Send, Pencil, XCircle, Receipt, CircleDollarSign,
  History, AlertTriangle, PlusCircle, Download, Paperclip, Mail, MessageCircle, Link2,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { parseApiErrors } from '@/utils/formErrors'
import { maskChaveNFe, validateChaveNFe, numeroDaChaveNFe } from '@/utils/masks'
import { minCalendarioISO, maxCalendarioISO } from '@/utils/dates'
import { baixarParaDisco } from '@/lib/arquivo'
import apiClient from '@/api/apiClient'
import {
  painelPedido, receberPedido, lancarNota, anexarDocumentoNota, corrigirNota, removerNota, definirCobranca, editarPedido,
  cancelarPedido, enviarPedido, pdfDoPedido, cadastrarItem, avaliacoes as avaliacoesApi, type MeioDigitado,
} from '../api/scmApi'
import { scmKeys } from '../api/queryKeys'
import { avaliacoesHooks, centrosCustoHooks } from '../hooks'
import { brl, dataBR, num, pedidoEstado, origemPedido } from '../lib'
import { Btn, Card, Empty, EstadoPill, Erro, Field, Info, Loading, Modal, Nota, Pill, SectHead } from './ui'
import { CAPS, inp, lerDecimal, mono, type Say } from './estilo'
import { FichaItemModal } from './FichaItem'
import type { AvaliacaoFornecedor, CentroCusto, LinhaSaldo, NotaFiscalCompra, PainelPedido } from '../types'

const erroDe = (e: unknown, padrao: string) => Object.values(parseApiErrors(e))[0] ?? padrao
const hojeISO = () => new Date().toISOString().slice(0, 10)
const maisDias = (iso: string, d: number) => { const x = new Date(iso + 'T12:00:00'); x.setDate(x.getDate() + d); return x.toISOString().slice(0, 10) }
const decBR = (s: string) => (num(s) ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 3 })

const SITUACAO_NOTA: Record<string, { label: string; kind: 'amber' | 'good' | 'danger' }> = {
  aguardando_documento: { label: 'Aguardando documento', kind: 'amber' },
  conferida: { label: 'Conferida', kind: 'good' },
  divergente: { label: 'Divergente', kind: 'danger' },
}
const STATUS_TITULO: Record<string, { label: string; kind: 'info' | 'amber' | 'good' | 'danger' }> = {
  ABERTO: { label: 'Em aberto', kind: 'info' }, PARCIAL: { label: 'Pago em parte', kind: 'amber' },
  QUITADO: { label: 'Pago', kind: 'good' }, CANCELADO: { label: 'Cancelado', kind: 'danger' },
}

type Abertura = null | 'receber' | 'nota' | 'cobranca' | 'editar' | 'enviar' | 'cancelar' | 'avaliar'

export function PedidoDetail({ id, onBack, say }: { id: number; onBack: () => void; say: Say }) {
  const { hasPermission } = useAuth()
  const qc = useQueryClient()
  const podeReceber = hasPermission('scm.recebimento.edit'), podeEditar = hasPermission('scm.pedido.edit')
  const podeAvaliar = hasPermission('scm.avaliacao.edit'), podeCadastrar = hasPermission('scm.pedido.criar')
  const { data: painel, isLoading } = useQuery({ queryKey: ['scm', 'pedidos', 'painel', id], queryFn: () => painelPedido(id) })
  const { data: avals } = avaliacoesHooks.useAll({ pedido: id })
  const [aberto, setAberto] = useState<Abertura>(null)
  const [anexarEm, setAnexarEm] = useState<NotaFiscalCompra | null>(null)
  const [corrigirEm, setCorrigirEm] = useState<NotaFiscalCompra | null>(null)
  const [removerEm, setRemoverEm] = useState<NotaFiscalCompra | null>(null)
  const [ficha, setFicha] = useState<number | null>(null)
  const [cadastrando, setCadastrando] = useState<number | null>(null)
  const atualizar = () => qc.invalidateQueries({ queryKey: scmKeys.all })

  if (isLoading || !painel) return <Loading />
  const p = painel.pedido
  const travado = painel.regime === 'travado'
  const falta = painel.linhas.some(l => (num(l.pendente) ?? 0) > 0)
  const avaliacoesL = (avals ?? []) as AvaliacaoFornecedor[]

  const cadastrar = async (l: LinhaSaldo) => {
    setCadastrando(l.item_pedido)
    try {
      const r = await cadastrarItem({ item_pedido: l.item_pedido })
      say(r.criado ? `Item cadastrado no catálogo: ${r.codigo_interno} — ${r.descricao}` : `Já estava no catálogo: ${r.codigo_interno} — ${r.descricao}`, 6000)
      await atualizar()
    } catch (e) { say(erroDe(e, 'Não foi possível cadastrar o item.'), 6000) }
    setCadastrando(null)
  }
  const baixarPdf = async () => {
    try {
      const blob = await pdfDoPedido(id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = `pedido-de-compra-${id}.pdf`; a.click()
      URL.revokeObjectURL(url)
    } catch (e) { say(erroDe(e, 'Não foi possível gerar o PDF.'), 5000) }
  }

  return (
    <div style={{ maxWidth: 1040 }}>
      <button onClick={onBack} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--ink-3)', background: 'none', border: 'none', cursor: 'pointer', marginBottom: 6 }}><ArrowLeft size={13} /> Todos os pedidos</button>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 19, fontWeight: 750, letterSpacing: '-0.02em', color: 'var(--ink)' }}>Pedido #{p.pedido_id}</h2>
        <EstadoPill e={pedidoEstado[p.status]} /><Pill kind={origemPedido[p.origem].kind}>{origemPedido[p.origem].label}</Pill>
        {!!p.revisao && <Pill>revisão {p.revisao}</Pill>}
        {p.enviado_em && <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>enviado em {dataBR(p.enviado_em)}</span>}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Btn onClick={baixarPdf}><FileText size={14} /> PDF</Btn>
          {podeEditar && !travado && <Btn onClick={() => setAberto('enviar')}><Send size={14} /> Enviar</Btn>}
          {podeEditar && !travado && <Btn onClick={() => setAberto('editar')}><Pencil size={14} /> Editar</Btn>}
          {podeAvaliar && <Btn onClick={() => setAberto('avaliar')}><Star size={14} /> Avaliar</Btn>}
          {podeReceber && !travado && falta && <Btn variant="primary" onClick={() => setAberto('receber')}><PackageCheck size={14} /> Registrar recebimento</Btn>}
        </div>
      </div>

      <Pendencias painel={painel} podeReceber={podeReceber} podeEditar={podeEditar}
        onNota={() => setAberto('nota')} onCobranca={() => setAberto('cobranca')} />

      <div style={{ display: 'grid', gap: 18 }}>
        <Card><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 16 }}>
          <Info k="Fornecedor" v={p.fornecedor_nome ?? `#${p.fornecedor}`} />
          <Info k="Centro de custo" v={p.centro_custo_nome ?? '—'} />
          <Info k="Valor total" v={brl(p.valor_total)} mono />
          <Info k="Data do pedido" v={dataBR(p.data_pedido)} mono />
          <Info k="Entrega prevista" v={dataBR(p.data_entrega_prevista)} mono />
          {p.demanda && <Info k="Origem" v={`Demanda #${p.demanda}`} />}
          {(p.medicao_pdca ?? []).map(m => <Info key={m.contrato} k={`Medido no PDCA · contrato ${m.numero}`} v={`${brl(m.medido_aprovado)} de ${brl(p.valor_total)}`} mono />)}
        </div>{p.observacao && <p style={{ marginTop: 12, fontSize: 13, color: 'var(--ink-2)', whiteSpace: 'pre-wrap' }}>{p.observacao}</p>}</Card>

        <div>
          <SectHead right={painel.regime === 'saldo' ? <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>já houve recebimento: só os saldos mudam</span> : undefined}>Itens</SectHead>
          <Card pad={false} style={{ overflow: 'hidden' }}><div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 680 }}>
            <thead><tr>{['Item', 'Pedido', 'Recebido', 'Falta', 'Preço unit.', 'Subtotal'].map((h, i) => <th key={i} style={{ ...CAPS, fontSize: 10.5, textAlign: i ? 'right' : 'left', padding: '10px 16px', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' }}>{h}</th>)}</tr></thead>
            <tbody>{painel.linhas.map((l, i) => {
              const enc = num(l.encerrado) ?? 0, exc = num(l.excedente) ?? 0, pend = num(l.pendente) ?? 0
              return (
                <tr key={l.item_pedido} style={{ borderBottom: i < painel.linhas.length - 1 ? '1px solid var(--line-2)' : undefined }}>
                  <td style={{ padding: '11px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {l.produto == null && podeCadastrar && !travado && (
                        <button type="button" title="Cadastrar este item no catálogo" aria-label="Cadastrar no catálogo" disabled={cadastrando === l.item_pedido}
                          onClick={() => cadastrar(l)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent-ink)', padding: 0, display: 'grid' }}><PlusCircle size={17} /></button>
                      )}
                      <div>
                        {l.produto != null
                          ? <button type="button" onClick={() => setFicha(l.produto)} style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', fontWeight: 500, color: 'var(--ink)', textAlign: 'left', textDecoration: 'underline dotted', textUnderlineOffset: 3 }}>{l.descricao}</button>
                          : <span style={{ fontWeight: 500, color: 'var(--ink)' }}>{l.descricao}</span>}
                        <div style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)' }}>{l.produto != null ? l.codigo : 'sem cadastro — não entra no estoque'}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ ...mono, padding: '11px 16px', textAlign: 'right' }}>{decBR(l.quantidade)} <span style={{ color: 'var(--ink-3)' }}>{l.unidade}</span></td>
                  <td style={{ ...mono, padding: '11px 16px', textAlign: 'right' }}>{decBR(l.recebido)}{exc > 0 && <div style={{ fontSize: 11, color: 'var(--accent-ink)' }}>+{decBR(l.excedente)} a mais</div>}</td>
                  <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', color: pend > 0 ? 'var(--ink)' : 'var(--ink-3)' }}>{pend > 0 ? decBR(l.pendente) : '—'}{enc > 0 && <div style={{ fontSize: 11, color: 'var(--danger-ink)' }}>{decBR(l.encerrado)} encerrado</div>}</td>
                  <td style={{ ...mono, padding: '11px 16px', textAlign: 'right' }}>{brl(l.preco_unitario)}</td>
                  <td style={{ ...mono, padding: '11px 16px', textAlign: 'right', fontWeight: 600, color: 'var(--ink)' }}>{brl(l.subtotal)}</td>
                </tr>
              )
            })}</tbody>
          </table></div></Card>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(380px,1fr))', gap: 18, alignItems: 'start' }}>
          <div>
            <SectHead right={podeReceber && !travado ? <Btn style={{ padding: '5px 11px', fontSize: 12.5 }} onClick={() => setAberto('nota')}><Receipt size={13} /> Lançar NF-e</Btn> : undefined}>Notas fiscais</SectHead>
            {painel.notas.length === 0 ? <Empty>Nenhuma NF-e lançada.</Empty> : painel.notas.map(n => (
              <NotaCard key={n.nota_id} n={n} podeAnexar={podeReceber} onAnexar={() => setAnexarEm(n)}
                onCorrigir={() => setCorrigirEm(n)} onRemover={() => setRemoverEm(n)} />
            ))}
          </div>
          <Cobranca painel={painel} podeEditar={podeEditar && !travado} onDefinir={() => setAberto('cobranca')} />
        </div>

        <div>
          <SectHead>Recebimentos</SectHead>
          {painel.recebimentos.length === 0 ? <Empty>Nenhum recebimento registrado.</Empty> : <Card pad={false} style={{ overflow: 'hidden' }}>{painel.recebimentos.map((r, i) => (
            <div key={r.recebimento_id} style={{ padding: '12px 16px', borderBottom: i < painel.recebimentos.length - 1 ? '1px solid var(--line-2)' : undefined }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <Pill kind={r.tipo === 'total' ? 'good' : 'amber'}>{r.tipo === 'total' ? 'Total' : 'Parcial'}</Pill>
                {r.encerrou_saldo && <Pill kind="danger">saldo encerrado</Pill>}
                <span style={{ ...mono, fontSize: 12.5, color: 'var(--ink-2)' }}>{dataBR(r.data)}</span>
                {r.recebido_por && <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>por {r.recebido_por}</span>}
                {r.nota_fiscal_ref ? <span style={{ marginLeft: 'auto', ...mono, fontSize: 12, color: 'var(--net-ink)' }}>NF-e {r.nota_fiscal_ref}</span> : <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--accent-ink)' }}>sem nota</span>}
              </div>
              {r.itens.length > 0 && <div style={{ fontSize: 12.5, color: 'var(--ink-2)', marginTop: 5 }}>{r.itens.map(it => `${it.descricao} ${decBR(it.quantidade)}`).join(' · ')}</div>}
            </div>
          ))}</Card>}
        </div>

        {avaliacoesL.length > 0 && <div>
          <SectHead>Avaliação do fornecedor</SectHead>
          {avaliacoesL.map(a => <Card key={a.avaliacao_id} style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center' }}><Nota k="Qualidade" v={a.nota_qualidade} /><Nota k="Pontualidade" v={a.nota_pontualidade} /><Nota k="Atendimento" v={a.nota_atendimento} />{a.comentario && <p style={{ flex: 1, minWidth: 200, fontSize: 13, color: 'var(--ink-2)' }}>{a.comentario}</p>}</Card>)}
        </div>}

        <div>
          <SectHead right={podeEditar && painel.regime === 'livre' ? <Btn variant="danger" style={{ padding: '5px 11px', fontSize: 12.5 }} onClick={() => setAberto('cancelar')}><XCircle size={13} /> Cancelar pedido</Btn> : undefined}>Histórico</SectHead>
          <Card pad={false}>{painel.eventos.length === 0 ? <div style={{ padding: 16, fontSize: 13, color: 'var(--ink-3)' }}>Sem histórico.</div> : painel.eventos.map((ev, i) => (
            <div key={ev.evento_id} style={{ display: 'flex', gap: 12, padding: '11px 16px', borderBottom: i < painel.eventos.length - 1 ? '1px solid var(--line-2)' : undefined }}>
              <History size={15} style={{ color: 'var(--ink-3)', flex: 'none', marginTop: 2 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, color: 'var(--ink)' }}>{ev.texto}</div>
                <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <span style={mono}>{new Date(ev.criado_em).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}</span>
                  {ev.autor_nome && <span>{ev.autor_nome}</span>}
                  {ev.vai_ao_erp && <Pill kind="net">anotado no financeiro</Pill>}
                </div>
              </div>
            </div>
          ))}</Card>
        </div>
      </div>

      {aberto === 'receber' && <ReceberModal painel={painel} onClose={() => setAberto(null)} onDone={async m => { setAberto(null); await atualizar(); say(m, 5000) }} />}
      {aberto === 'nota' && <NotaModal pedido={id} onClose={() => setAberto(null)} onDone={async m => { setAberto(null); await atualizar(); say(m, 5000) }} />}
      {anexarEm && <NotaModal pedido={id} nota={anexarEm} onClose={() => setAnexarEm(null)} onDone={async m => { setAnexarEm(null); await atualizar(); say(m, 5000) }} />}
      {corrigirEm && <CorrigirNotaModal nota={corrigirEm} onClose={() => setCorrigirEm(null)} onDone={async m => { setCorrigirEm(null); await atualizar(); say(m, 5000) }} />}
      {removerEm && <RemoverNotaModal nota={removerEm} onClose={() => setRemoverEm(null)} onDone={async m => { setRemoverEm(null); await atualizar(); say(m, 5000) }} />}
      {aberto === 'cobranca' && <CobrancaModal painel={painel} onClose={() => setAberto(null)} onDone={async m => { setAberto(null); await atualizar(); say(m, 5000) }} />}
      {aberto === 'editar' && <EditarModal painel={painel} onClose={() => setAberto(null)} onDone={async m => { setAberto(null); await atualizar(); say(m, 5000) }} />}
      {aberto === 'enviar' && <EnviarModal painel={painel} baixarPdf={baixarPdf} onClose={() => setAberto(null)} onDone={async m => { setAberto(null); await atualizar(); say(m, 5000) }} />}
      {aberto === 'cancelar' && <CancelarModal pedido={id} onClose={() => setAberto(null)} onDone={async m => { setAberto(null); await atualizar(); say(m, 5000) }} />}
      {aberto === 'avaliar' && <AvaliarModal pedidoId={id} fornecedor={p.fornecedor} onClose={() => setAberto(null)} onDone={async () => { setAberto(null); await atualizar(); say('Fornecedor avaliado') }} />}
      {ficha != null && <FichaItemModal item={ficha} onClose={() => setFicha(null)} />}
    </div>
  )
}

/* ─── o que está faltando, com o botão de cada coisa ─── */
function Pendencias({ painel, podeReceber, podeEditar, onNota, onCobranca }: { painel: PainelPedido; podeReceber: boolean; podeEditar: boolean; onNota: () => void; onCobranca: () => void }) {
  const itens: { texto: string; acao?: { rotulo: string; fazer: () => void } }[] = []
  const ps = new Set(painel.pendencias)
  if (ps.has('aguardando_nfe')) itens.push({ texto: 'Recebido sem nota fiscal — o financeiro está aguardando a NF-e.', acao: podeReceber ? { rotulo: 'Lançar NF-e', fazer: onNota } : undefined })
  if (ps.has('nfe_aguardando_documento')) itens.push({ texto: 'NF-e informada só pelo número — anexe o XML ou o PDF para conferir.' })
  if (ps.has('nfe_divergente')) itens.push({ texto: 'Há NF-e com divergência — confira abaixo o que não bate.' })
  if (ps.has('sem_cobranca')) itens.push({ texto: 'Sem cobrança: nada deste pedido foi para o contas a pagar.', acao: podeEditar ? { rotulo: 'Definir cobrança', fazer: onCobranca } : undefined })
  if (ps.has('cobranca_nao_confere')) itens.push({ texto: `A cobrança soma ${brl(painel.cobranca.soma)} e o pedido é ${brl(painel.cobranca.valor_pedido)} — redefina.`, acao: podeEditar ? { rotulo: 'Redefinir cobrança', fazer: onCobranca } : undefined })
  if (itens.length === 0) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
      {itens.map((it, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', borderRadius: 'var(--r-md)', background: 'var(--accent-soft)', border: '1px solid color-mix(in srgb,var(--accent) 35%,var(--line))', fontSize: 13, color: 'var(--accent-ink)' }}>
          <AlertTriangle size={16} style={{ flex: 'none' }} /><span style={{ flex: 1 }}>{it.texto}</span>
          {it.acao && <Btn style={{ padding: '5px 11px', fontSize: 12.5 }} onClick={it.acao.fazer}>{it.acao.rotulo}</Btn>}
        </div>
      ))}
    </div>
  )
}

/* ─── NF-e ─── */
function NotaCard({ n, podeAnexar, onAnexar, onCorrigir, onRemover }: { n: NotaFiscalCompra; podeAnexar: boolean; onAnexar: () => void; onCorrigir: () => void; onRemover: () => void }) {
  const s = SITUACAO_NOTA[n.situacao]
  return (
    <Card style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <b style={{ color: 'var(--ink)' }}>NF-e {n.numero}{n.serie ? ` · série ${n.serie}` : ''}</b>
        <Pill kind={s.kind}>{s.label}</Pill>
        {n.valor_total && <span style={{ ...mono, fontSize: 12.5, marginLeft: 'auto' }}>{brl(n.valor_total)}</span>}
      </div>
      {n.chave_acesso && <div style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', marginTop: 4, wordBreak: 'break-all' }}>{maskChaveNFe(n.chave_acesso)}</div>}
      {n.emitente_nome && <div style={{ fontSize: 12, color: 'var(--ink-2)', marginTop: 4 }}>Emitente: {n.emitente_nome}{n.data_emissao ? ` · emitida em ${dataBR(n.data_emissao)}` : ''}</div>}
      {n.divergencias.length > 0 && <ul style={{ margin: '8px 0 0', paddingLeft: 18, fontSize: 12.5, color: 'var(--danger-ink)' }}>{n.divergencias.map((d, i) => <li key={i}>{d}</li>)}</ul>}
      {n.duplicatas.length > 0 && <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 6 }}>Duplicatas: {n.duplicatas.map(d => `${dataBR(d.vencimento)} ${brl(d.valor)}`).join(' · ')}</div>}
      <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
        {n.url_xml && <Btn style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => baixarParaDisco(n.url_xml!, `nfe-${n.numero}.xml`)}><Download size={12} /> XML</Btn>}
        {n.url_pdf && <Btn style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => baixarParaDisco(n.url_pdf!, `nfe-${n.numero}.pdf`)}><Download size={12} /> DANFE</Btn>}
        {podeAnexar && !n.url_xml &&<Btn style={{ padding: '4px 10px', fontSize: 12 }} onClick={onAnexar}><Paperclip size={12} /> Anexar documento</Btn>}
        {podeAnexar && !n.url_xml && <Btn style={{ padding: '4px 10px', fontSize: 12 }} onClick={onCorrigir}><Pencil size={12} /> Corrigir</Btn>}
        {podeAnexar && <Btn variant="danger" style={{ padding: '4px 10px', fontSize: 12 }} onClick={onRemover}><XCircle size={12} /> Remover</Btn>}
      </div>
    </Card>
  )
}

function CampoChave({ valor, onChange, numero }: { valor: string; onChange: (v: string) => void; numero?: string }) {
  const aviso = validateChaveNFe(valor)
  const daChave = numeroDaChaveNFe(valor)
  const outroNumero = !aviso && numero && daChave && daChave !== String(Number(numero.replace(/\D/g, '')))
  return (
    <Field label="Chave de acesso (44 dígitos)">
      <input style={{ ...inp, ...mono, fontSize: 12.5 }} inputMode="numeric" placeholder="0000 0000 0000 …" value={maskChaveNFe(valor)} onChange={e => onChange(e.target.value.replace(/\D/g, '').slice(0, 44))} />
      {aviso && <div style={{ fontSize: 11.5, color: 'var(--accent-ink)', marginTop: 4 }}>⚠ {aviso} A nota pode ser lançada assim mesmo e fica marcada.</div>}
      {outroNumero && <div style={{ fontSize: 11.5, color: 'var(--accent-ink)', marginTop: 4 }}>⚠ A chave é da nota {daChave}, não da {numero}.</div>}
    </Field>
  )
}
function Arquivo({ label, accept, file, onChange }: { label: string; accept: string; file: File | null; onChange: (f: File | null) => void }) {
  return (
    <Field label={label}>
      <input type="file" accept={accept} style={{ ...inp, padding: 6 }} onChange={e => onChange(e.target.files?.[0] ?? null)} />
      {file && <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 3 }}>{file.name}</div>}
    </Field>
  )
}

function NotaModal({ pedido, nota, onClose, onDone }: { pedido: number; nota?: NotaFiscalCompra; onClose: () => void; onDone: (m: string) => void }) {
  const [numero, setNumero] = useState(''), [serie, setSerie] = useState(''), [chave, setChave] = useState(nota?.chave_acesso ?? '')
  const [xml, setXml] = useState<File | null>(null), [pdf, setPdf] = useState<File | null>(null)
  const [err, setErr] = useState(''), [salvando, setSalvando] = useState(false)
  const salvar = async () => {
    setErr(''); setSalvando(true)
    try {
      const r = nota
        ? await anexarDocumentoNota(nota.nota_id, { chave: chave !== nota.chave_acesso ? chave : '', xml, pdf })
        : await lancarNota(pedido, { numero: numero || numeroDaChaveNFe(chave), serie, chave, xml, pdf })
      onDone(r.situacao === 'divergente' ? `NF-e ${r.numero} registrada com divergência — confira.` : r.situacao === 'conferida' ? `NF-e ${r.numero} conferida.` : `NF-e ${r.numero} lançada — aguardando o documento.`)
    } catch (e) { setErr(erroDe(e, 'Não foi possível lançar a nota.')); setSalvando(false) }
  }
  return (
    <Modal title={nota ? `Documento da NF-e ${nota.numero}` : 'Lançar NF-e'} onClose={onClose} largura={560}
      footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={salvando}>{salvando ? 'Salvando…' : nota ? 'Anexar e conferir' : 'Lançar'}</Btn></>}>
      <Erro msg={err} />
      <p style={{ fontSize: 12.5, color: 'var(--ink-3)', marginBottom: 12 }}>Só com o número, a nota vai ao financeiro aguardando o documento. Com o XML (ou o PDF com a chave), ela é conferida com o pedido.</p>
      {!nota && <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px', gap: 10 }}>
        <Field label="Número da nota"><input style={{ ...inp, ...mono }} inputMode="numeric" value={numero} onChange={e => setNumero(e.target.value.replace(/\D/g, '').slice(0, 9))} placeholder={numeroDaChaveNFe(chave) || 'ex.: 529'} /></Field>
        <Field label="Série"><input style={{ ...inp, ...mono }} inputMode="numeric" value={serie} onChange={e => setSerie(e.target.value.replace(/\D/g, '').slice(0, 3))} /></Field>
      </div>}
      <CampoChave valor={chave} onChange={setChave} numero={nota ? nota.numero : numero} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <Arquivo label="XML da NF-e" accept=".xml,application/xml,text/xml" file={xml} onChange={setXml} />
        <Arquivo label="PDF (DANFE)" accept=".pdf,application/pdf" file={pdf} onChange={setPdf} />
      </div>
    </Modal>
  )
}

function CorrigirNotaModal({ nota, onClose, onDone }: { nota: NotaFiscalCompra; onClose: () => void; onDone: (m: string) => void }) {
  const [numero, setNumero] = useState(nota.numero), [serie, setSerie] = useState(nota.serie ?? ''), [chave, setChave] = useState(nota.chave_acesso ?? '')
  const [err, setErr] = useState(''), [salvando, setSalvando] = useState(false)
  const salvar = async () => {
    setErr(''); setSalvando(true)
    try {
      const r = await corrigirNota(nota.nota_id, { numero: numero || numeroDaChaveNFe(chave), serie, chave })
      onDone(r.situacao === 'divergente' ? `NF-e ${r.numero} corrigida, com divergência — confira.` : `NF-e ${r.numero} corrigida.`)
    } catch (e) { setErr(erroDe(e, 'Não foi possível corrigir a nota.')); setSalvando(false) }
  }
  return (
    <Modal title={`Corrigir a NF-e ${nota.numero}`} onClose={onClose} largura={520}
      footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={salvando}>{salvando ? 'Salvando…' : 'Corrigir'}</Btn></>}>
      <Erro msg={err} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px', gap: 10 }}>
        <Field label="Número da nota"><input style={{ ...inp, ...mono }} inputMode="numeric" value={numero} onChange={e => setNumero(e.target.value.replace(/\D/g, '').slice(0, 9))} /></Field>
        <Field label="Série"><input style={{ ...inp, ...mono }} inputMode="numeric" value={serie} onChange={e => setSerie(e.target.value.replace(/\D/g, '').slice(0, 3))} /></Field>
      </div>
      <CampoChave valor={chave} onChange={setChave} numero={numero} />
    </Modal>
  )
}

function RemoverNotaModal({ nota, onClose, onDone }: { nota: NotaFiscalCompra; onClose: () => void; onDone: (m: string) => void }) {
  const [motivo, setMotivo] = useState(''), [err, setErr] = useState(''), [salvando, setSalvando] = useState(false)
  const remover = async () => {
    setErr(''); setSalvando(true)
    try { await removerNota(nota.nota_id, motivo); onDone(`NF-e ${nota.numero} removida do pedido.`) }
    catch (e) { setErr(erroDe(e, 'Não foi possível remover a nota.')); setSalvando(false) }
  }
  return (
    <Modal title={`Remover a NF-e ${nota.numero}`} onClose={onClose} largura={480}
      footer={<><Btn onClick={onClose}>Voltar</Btn><Btn variant="danger" onClick={remover} disabled={salvando}>{salvando ? 'Removendo…' : 'Remover nota'}</Btn></>}>
      <Erro msg={err} />
      <p style={{ fontSize: 12.5, color: 'var(--ink-3)', marginBottom: 12 }}>A nota sai do pedido e o arquivo anexado é apagado. O financeiro é avisado nos títulos, e o histórico guarda a remoção.</p>
      <Field label="Motivo (opcional)"><input style={inp} value={motivo} onChange={e => setMotivo(e.target.value)} placeholder="ex.: a nota é de outro pedido" /></Field>
    </Modal>
  )
}

/* ─── Recebimento por linha ─── */
function ReceberModal({ painel, onClose, onDone }: { painel: PainelPedido; onClose: () => void; onDone: (m: string) => void }) {
  const linhas = painel.linhas
  const [qtd, setQtd] = useState<Record<number, string>>(() => Object.fromEntries(linhas.map(l => [l.item_pedido, (num(l.pendente) ?? 0) > 0 ? decBR(l.pendente) : ''])))
  const [data, setData] = useState(hojeISO())
  const [encerrar, setEncerrar] = useState(false)
  const [obs, setObs] = useState('')
  const [nfNumero, setNfNumero] = useState(''), [nfSerie, setNfSerie] = useState(''), [nfChave, setNfChave] = useState('')
  const [xml, setXml] = useState<File | null>(null), [pdf, setPdf] = useState<File | null>(null)
  const [err, setErr] = useState(''), [salvando, setSalvando] = useState(false)

  const analise = useMemo(() => {
    const aMais: string[] = [], aMenos: string[] = []
    for (const l of linhas) {
      const q = lerDecimal(qtd[l.item_pedido] ?? '') ?? 0, pend = num(l.pendente) ?? 0
      if (q > pend) aMais.push(`${l.descricao} +${(q - pend).toLocaleString('pt-BR')}`)
      else if (q < pend) aMenos.push(`${l.descricao} −${(pend - q).toLocaleString('pt-BR')}`)
    }
    return { aMais, aMenos }
  }, [linhas, qtd])

  const salvar = async () => {
    setErr('')
    const itens = linhas.map(l => ({ item_pedido: l.item_pedido, quantidade: String(lerDecimal(qtd[l.item_pedido] ?? '') ?? 0) })).filter(i => Number(i.quantidade) > 0)
    if (itens.length === 0 && !encerrar) return setErr('Informe a quantidade que chegou.')
    setSalvando(true)
    try {
      const r = await receberPedido(painel.pedido.pedido_id, { itens, data, encerrar, observacao: obs, nf_numero: nfNumero || numeroDaChaveNFe(nfChave), nf_serie: nfSerie, nf_chave: nfChave, nf_xml: xml, nf_pdf: pdf })
      const partes = ['Recebimento registrado — o estoque foi atualizado.']
      if (r.a_mais.length) partes.push('Chegou a mais: anotado no financeiro.')
      if (r.encerrados.length) partes.push('Saldo encerrado: anotado no financeiro.')
      if (r.aguardando_nfe) partes.push('Aguardando a NF-e.')
      onDone(partes.join(' '))
    } catch (e) { setErr(erroDe(e, 'Não foi possível registrar o recebimento.')); setSalvando(false) }
  }

  return (
    <Modal title="Registrar recebimento" onClose={onClose} largura={720}
      footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={salvando}><PackageCheck size={14} /> {salvando ? 'Registrando…' : 'Registrar'}</Btn></>}>
      <Erro msg={err} />
      <div style={{ display: 'grid', gridTemplateColumns: '170px 1fr', gap: 12 }}>
        <Field label="Data"><input style={inp} type="date" min={minCalendarioISO} max={maxCalendarioISO} value={data} onChange={e => setData(e.target.value)} /></Field>
        <Field label="Observação"><input style={inp} value={obs} onChange={e => setObs(e.target.value)} placeholder="Opcional" /></Field>
      </div>
      <div style={{ ...CAPS, fontSize: 10.5, marginBottom: 6 }}>O que chegou</div>
      <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', overflow: 'hidden', marginBottom: 14 }}>
        {linhas.map((l, i) => {
          const pend = num(l.pendente) ?? 0
          return (
            <div key={l.item_pedido} style={{ display: 'grid', gridTemplateColumns: '1fr 120px 120px', gap: 10, alignItems: 'center', padding: '8px 12px', borderBottom: i < linhas.length - 1 ? '1px solid var(--line-2)' : undefined, opacity: pend <= 0 ? 0.6 : 1 }}>
              <div><div style={{ fontSize: 13, color: 'var(--ink)' }}>{l.descricao}</div>{!l.estocavel && <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>não entra no estoque</div>}</div>
              <div style={{ ...mono, fontSize: 12, color: 'var(--ink-3)', textAlign: 'right' }}>{pend > 0 ? `faltam ${decBR(l.pendente)} ${l.unidade}` : 'completo'}</div>
              <input style={{ ...inp, ...mono, textAlign: 'right' }} inputMode="decimal" placeholder="0" aria-label={`Quantidade recebida de ${l.descricao}`}
                value={qtd[l.item_pedido] ?? ''} onChange={e => setQtd(q => ({ ...q, [l.item_pedido]: e.target.value }))} />
            </div>
          )
        })}
      </div>
      {analise.aMais.length > 0 && <div style={{ fontSize: 12.5, color: 'var(--accent-ink)', marginBottom: 8 }}>⚠ Chegou a mais: {analise.aMais.join('; ')}. O estoque recebe o que chegou e o financeiro é avisado.</div>}
      <label style={{ display: 'flex', gap: 9, alignItems: 'flex-start', fontSize: 13, color: 'var(--ink)', padding: '10px 12px', borderRadius: 'var(--r-sm)', background: encerrar ? 'var(--danger-soft)' : 'var(--surface-2)', cursor: 'pointer', marginBottom: 14 }}>
        <input type="checkbox" checked={encerrar} onChange={e => setEncerrar(e.target.checked)} style={{ marginTop: 2 }} />
        <span><b>Finalizar o recebimento</b> — o que faltar não vem mais.{encerrar && analise.aMenos.length > 0 && <span style={{ display: 'block', color: 'var(--danger-ink)', marginTop: 3 }}>Vai ao financeiro como divergência: {analise.aMenos.join('; ')}.</span>}{!encerrar && analise.aMenos.length > 0 && <span style={{ display: 'block', color: 'var(--ink-3)', marginTop: 3 }}>Sem marcar, o pedido fica parcial esperando o resto.</span>}</span>
      </label>
      <div style={{ ...CAPS, fontSize: 10.5, marginBottom: 6 }}>Nota fiscal que veio com a entrega <span style={{ textTransform: 'none', letterSpacing: 0, fontWeight: 500 }}>(opcional — sem ela, fica aguardando)</span></div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px', gap: 10 }}>
        <Field label="Número"><input style={{ ...inp, ...mono }} inputMode="numeric" value={nfNumero} onChange={e => setNfNumero(e.target.value.replace(/\D/g, '').slice(0, 9))} placeholder={numeroDaChaveNFe(nfChave)} /></Field>
        <Field label="Série"><input style={{ ...inp, ...mono }} inputMode="numeric" value={nfSerie} onChange={e => setNfSerie(e.target.value.replace(/\D/g, '').slice(0, 3))} /></Field>
      </div>
      <CampoChave valor={nfChave} onChange={setNfChave} numero={nfNumero} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <Arquivo label="XML da NF-e" accept=".xml,application/xml,text/xml" file={xml} onChange={setXml} />
        <Arquivo label="PDF (DANFE)" accept=".pdf,application/pdf" file={pdf} onChange={setPdf} />
      </div>
    </Modal>
  )
}

/* ─── Cobrança ─── */
function Cobranca({ painel, podeEditar, onDefinir }: { painel: PainelPedido; podeEditar: boolean; onDefinir: () => void }) {
  const c = painel.cobranca
  return (
    <div>
      <SectHead right={podeEditar ? <Btn style={{ padding: '5px 11px', fontSize: 12.5 }} onClick={onDefinir}><CircleDollarSign size={13} /> {c.meios.length ? 'Redefinir' : 'Definir cobrança'}</Btn> : undefined}>Cobrança e contas a pagar</SectHead>
      {c.meios.length === 0 ? <Empty>Sem cobrança — defina como o fornecedor vai cobrar para o pedido ir ao contas a pagar.</Empty> : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          {c.meios.map((m, i) => (
            <div key={m.meio_id} style={{ padding: '11px 16px', borderBottom: i < c.meios.length - 1 ? '1px solid var(--line-2)' : undefined }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <b style={{ color: 'var(--ink)', fontSize: 13 }}>{m.tipo_nome}{m.parcelas > 1 ? ` em ${m.parcelas}x` : ''}</b>
                {m.descricao && <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>{m.descricao}</span>}
                <span style={{ ...mono, marginLeft: 'auto', fontWeight: 650 }}>{brl(m.valor)}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginTop: 6 }}>
                {m.parcelas_geradas.map(pa => {
                  const st = pa.titulo_status ? STATUS_TITULO[pa.titulo_status] : null
                  return (
                    <div key={pa.numero} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}>
                      <span style={{ ...mono, color: 'var(--ink-3)', width: 34 }}>{pa.numero}/{m.parcelas}</span>
                      <span style={mono}>{dataBR(pa.vencimento)}</span>
                      <span style={{ ...mono, marginLeft: 'auto' }}>{brl(pa.valor)}</span>
                      {st ? <Pill kind={st.kind}>{st.label}</Pill> : <Pill>sem título</Pill>}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 16px', background: 'var(--surface-2)', fontSize: 12.5 }}>
            {c.confere ? <span style={{ color: 'var(--good-ink)' }}>Fecha com o pedido ({brl(c.soma)}).</span> : <span style={{ color: 'var(--danger-ink)' }}>Soma {brl(c.soma)} · pedido {brl(c.valor_pedido)}</span>}
            <Link to={painel.titulos.length ? `/app/erp/contas-a-pagar?conta=${painel.titulos.find(t => t.status !== 'CANCELADO')?.conta_pagar_id ?? painel.titulos[0].conta_pagar_id}` : '/app/erp/contas-a-pagar'}
              style={{ marginLeft: 'auto', color: 'var(--net-ink)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 4 }}><Link2 size={12} /> Ver no contas a pagar</Link>
          </div>
        </Card>
      )}
    </div>
  )
}

interface MeioForm extends Omit<MeioDigitado, 'parcelas' | 'intervalo_dias'> { chave: number; parcelas: string; intervalo_dias: string }
function parcelasDe(m: MeioForm): { n: number; venc: string; valor: number }[] {
  const valor = Math.round((lerDecimal(m.valor) ?? 0) * 100), n = Math.max(1, Math.min(60, parseInt(m.parcelas) || 1))
  const intervalo = parseInt(m.intervalo_dias) || 30
  if (!valor || !m.primeiro_vencimento) return []
  const base = Math.floor(valor / n), resto = valor - base * n
  return Array.from({ length: n }, (_, i) => ({ n: i + 1, venc: maisDias(m.primeiro_vencimento, intervalo * i), valor: (base + (i === 0 ? resto : 0)) / 100 }))
}

function CobrancaModal({ painel, onClose, onDone }: { painel: PainelPedido; onClose: () => void; onDone: (m: string) => void }) {
  const c = painel.cobranca
  const total = num(painel.pedido.valor_total) ?? 0
  const [meios, setMeios] = useState<MeioForm[]>(() => c.meios.length
    ? c.meios.map((m, i) => ({ chave: i + 1, tipo: m.tipo, valor: decBR(m.valor), parcelas: String(m.parcelas), primeiro_vencimento: m.primeiro_vencimento, intervalo_dias: String(m.intervalo_dias), descricao: m.descricao }))
    : [{ chave: 1, tipo: 'boleto', valor: total.toLocaleString('pt-BR', { minimumFractionDigits: 2 }), parcelas: '1', primeiro_vencimento: maisDias(hojeISO(), 30), intervalo_dias: '30', descricao: '' }])
  const [err, setErr] = useState(''), [salvando, setSalvando] = useState(false)
  const soma = meios.reduce((s, m) => s + Math.round((lerDecimal(m.valor) ?? 0) * 100), 0) / 100
  const diferenca = Math.round((total - soma) * 100) / 100
  const mudar = (chave: number, patch: Partial<MeioForm>) => setMeios(ms => ms.map(m => m.chave === chave ? { ...m, ...patch } : m))
  const pagos = c.meios.some(m => m.parcelas_geradas.some(p => (num(p.titulo_valor_pago) ?? 0) > 0))

  const salvar = async () => {
    setErr(''); setSalvando(true)
    try {
      const r = await definirCobranca(painel.pedido.pedido_id, meios.map(m => ({
        tipo: m.tipo, valor: String(lerDecimal(m.valor) ?? 0), parcelas: parseInt(m.parcelas) || 1,
        primeiro_vencimento: m.primeiro_vencimento, intervalo_dias: parseInt(m.intervalo_dias) || 30, descricao: m.descricao,
      })))
      onDone(`${r.titulos.length} título${r.titulos.length > 1 ? 's' : ''} lançado${r.titulos.length > 1 ? 's' : ''} no contas a pagar, aguardando a NF-e.`)
    } catch (e) { setErr(erroDe(e, 'Não foi possível definir a cobrança.')); setSalvando(false) }
  }
  return (
    <Modal title={c.meios.length ? 'Redefinir cobrança' : 'Cobrança do pedido'} onClose={onClose} largura={760}
      footer={<>
        <span style={{ marginRight: 'auto', alignSelf: 'center', ...mono, fontSize: 13, color: diferenca === 0 ? 'var(--good-ink)' : 'var(--danger-ink)' }}>
          {brl(soma)} de {brl(total)}{diferenca > 0 ? ` · faltam ${brl(diferenca)}` : diferenca < 0 ? ` · sobram ${brl(-diferenca)}` : ' · fecha'}
        </span>
        <Btn onClick={onClose}>Cancelar</Btn>
        <Btn variant="primary" onClick={salvar} disabled={salvando || diferenca !== 0 || pagos}>{salvando ? 'Lançando…' : 'Lançar no contas a pagar'}</Btn>
      </>}>
      <Erro msg={err} />
      {pagos && <Erro msg="Um título deste pedido já tem pagamento no financeiro. Para mudar a cobrança, o financeiro precisa estornar a baixa antes." />}
      {c.meios.length > 0 && !pagos && <p style={{ fontSize: 12.5, color: 'var(--ink-3)', marginBottom: 12 }}>Os títulos atuais (sem pagamento) serão cancelados e os novos lançados.</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {meios.map(m => {
          const prev = parcelasDe(m)
          return (
            <div key={m.chave} style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', padding: 12 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr 70px 1fr 80px 28px', gap: 8, alignItems: 'end' }}>
                <Field label="Forma"><select style={inp} value={m.tipo} onChange={e => mudar(m.chave, { tipo: e.target.value })}>{c.tipos.map(t => <option key={t.valor} value={t.valor}>{t.rotulo}</option>)}</select></Field>
                <Field label="Valor (R$)"><input style={{ ...inp, ...mono, textAlign: 'right' }} inputMode="decimal" value={m.valor} onChange={e => mudar(m.chave, { valor: e.target.value })} /></Field>
                <Field label="Vezes"><input style={{ ...inp, ...mono }} inputMode="numeric" value={m.parcelas} onChange={e => mudar(m.chave, { parcelas: e.target.value.replace(/\D/g, '').slice(0, 2) })} /></Field>
                <Field label="1º vencimento"><input style={inp} type="date" min={minCalendarioISO} max={maxCalendarioISO} value={m.primeiro_vencimento} onChange={e => mudar(m.chave, { primeiro_vencimento: e.target.value })} /></Field>
                <Field label="Dias entre"><input style={{ ...inp, ...mono }} inputMode="numeric" value={m.intervalo_dias} disabled={(parseInt(m.parcelas) || 1) <= 1} onChange={e => mudar(m.chave, { intervalo_dias: e.target.value.replace(/\D/g, '').slice(0, 3) })} /></Field>
                <button type="button" aria-label="Tirar meio" disabled={meios.length === 1} onClick={() => setMeios(ms => ms.filter(x => x.chave !== m.chave))} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)', marginBottom: 22 }}>×</button>
              </div>
              <input style={{ ...inp, fontSize: 12.5 }} value={m.descricao} onChange={e => mudar(m.chave, { descricao: e.target.value })}
                placeholder={m.tipo === 'cheque' ? 'Banco e números dos cheques' : m.tipo.startsWith('cartao') ? 'Bandeira / final do cartão' : m.tipo === 'outro' ? 'Descreva o meio (obrigatório)' : 'Observação (opcional)'} />
              {prev.length > 0 && <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 12px', marginTop: 8, fontSize: 11.5, color: 'var(--ink-3)', ...mono }}>
                {prev.slice(0, 12).map(p => <span key={p.n}>{p.n}ª {dataBR(p.venc)} {brl(p.valor)}</span>)}{prev.length > 12 && <span>… +{prev.length - 12}</span>}
              </div>}
            </div>
          )
        })}
      </div>
      <Btn style={{ marginTop: 10 }} onClick={() => setMeios(ms => [...ms, { chave: Date.now(), tipo: 'pix', valor: diferenca > 0 ? diferenca.toLocaleString('pt-BR', { minimumFractionDigits: 2 }) : '', parcelas: '1', primeiro_vencimento: hojeISO(), intervalo_dias: '30', descricao: '' }])}>+ Outro meio</Btn>
    </Modal>
  )
}

/* ─── Edição ─── */
interface LinhaEdicao { chave: number; item_pedido?: number; descricao: string; unidade: string; quantidade: string; preco: string; recebido: number }
function EditarModal({ painel, onClose, onDone }: { painel: PainelPedido; onClose: () => void; onDone: (m: string) => void }) {
  const p = painel.pedido
  const livre = painel.regime === 'livre'
  const { data: cc } = centrosCustoHooks.useAll({ ativo: true })
  const centros = (cc ?? []) as CentroCusto[]
  const { data: fornecedores = [] } = useQuery({
    queryKey: ['scm', 'fornecedores-da-compra'],
    queryFn: async () => {
      const { data } = await apiClient.get<{ results?: { fornecedor_id: number; razao_social: string }[] } | { fornecedor_id: number; razao_social: string }[]>('/fornecedores/', { params: { page_size: 500 } })
      return Array.isArray(data) ? data : (data.results ?? [])
    },
    enabled: livre,
  })
  const [fornecedor, setFornecedor] = useState(String(p.fornecedor))
  const [centro, setCentro] = useState(p.centro_custo ? String(p.centro_custo) : '')
  const [entrega, setEntrega] = useState(p.data_entrega_prevista ?? '')
  const [obs, setObs] = useState(p.observacao ?? '')
  const [motivo, setMotivo] = useState('')
  const [linhas, setLinhas] = useState<LinhaEdicao[]>(() => painel.linhas.map(l => ({
    chave: l.item_pedido, item_pedido: l.item_pedido, descricao: l.descricao, unidade: l.unidade,
    quantidade: decBR(l.quantidade), preco: decBR(l.preco_unitario), recebido: num(l.recebido) ?? 0,
  })))
  const [err, setErr] = useState(''), [salvando, setSalvando] = useState(false)
  const mudar = (chave: number, patch: Partial<LinhaEdicao>) => setLinhas(ls => ls.map(l => l.chave === chave ? { ...l, ...patch } : l))
  const total = linhas.reduce((t, l) => t + (lerDecimal(l.quantidade) ?? 0) * (lerDecimal(l.preco) ?? 0), 0)

  const salvar = async () => {
    setErr('')
    const abaixo = linhas.find(l => (lerDecimal(l.quantidade) ?? 0) < l.recebido)
    if (abaixo) return setErr(`${abaixo.descricao}: já chegaram ${abaixo.recebido.toLocaleString('pt-BR')}; a quantidade não pode ficar abaixo disso.`)
    setSalvando(true)
    const corpo: Record<string, unknown> = {
      data_entrega_prevista: entrega || null, observacao: obs, motivo,
      itens: linhas.map(l => ({
        ...(l.item_pedido ? { item_pedido: l.item_pedido } : { descricao: l.descricao, unidade: l.unidade }),
        quantidade: String(lerDecimal(l.quantidade) ?? 0),
        ...(livre ? { preco_unitario: String(lerDecimal(l.preco) ?? 0) } : {}),
      })),
    }
    if (livre) { corpo.fornecedor = Number(fornecedor); corpo.centro_custo = centro ? Number(centro) : null }
    try {
      const r = await editarPedido(p.pedido_id, corpo)
      onDone(r.mudancas.length ? `Pedido editado (${r.mudancas.length} mudança${r.mudancas.length > 1 ? 's' : ''}) — anotado no financeiro.` : 'Nada mudou.')
    } catch (e) { setErr(erroDe(e, 'Não foi possível editar o pedido.')); setSalvando(false) }
  }

  return (
    <Modal title={`Editar pedido #${p.pedido_id}`} onClose={onClose} largura={760}
      footer={<><span style={{ marginRight: 'auto', alignSelf: 'center', ...mono, fontSize: 13 }}>Novo total: <b>{brl(total.toFixed(2))}</b></span><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={salvando}>{salvando ? 'Salvando…' : 'Salvar'}</Btn></>}>
      <Erro msg={err} />
      {!livre && <div style={{ fontSize: 12.5, color: 'var(--accent-ink)', background: 'var(--accent-soft)', padding: '9px 12px', borderRadius: 'var(--r-sm)', marginBottom: 12 }}>Este pedido já teve recebimento: só as quantidades (saldos) mudam, nunca abaixo do que já chegou. Preço e fornecedor ficam como estão.</div>}
      {livre && <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Fornecedor"><select style={inp} value={fornecedor} onChange={e => setFornecedor(e.target.value)}>{fornecedores.map(f => <option key={f.fornecedor_id} value={f.fornecedor_id}>{f.razao_social}</option>)}{!fornecedores.length && <option value={p.fornecedor}>{p.fornecedor_nome}</option>}</select></Field>
        <Field label="Centro de custo"><select style={inp} value={centro} onChange={e => setCentro(e.target.value)}><option value="">— nenhum —</option>{centros.map(c => <option key={c.centro_custo_id} value={c.centro_custo_id}>{c.nome}</option>)}</select></Field>
      </div>}
      <div style={{ display: 'grid', gridTemplateColumns: '170px 1fr', gap: 12 }}>
        <Field label="Entrega prevista"><input style={inp} type="date" min={minCalendarioISO} max={maxCalendarioISO} value={entrega} onChange={e => setEntrega(e.target.value)} /></Field>
        <Field label="Observação"><input style={inp} value={obs} onChange={e => setObs(e.target.value)} /></Field>
      </div>
      <div style={{ ...CAPS, fontSize: 10.5, marginBottom: 6 }}>Itens</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 8 }}>
        {linhas.map(l => (
          <div key={l.chave} style={{ display: 'grid', gridTemplateColumns: livre ? '1fr 60px 100px 110px 28px' : '1fr 60px 110px', gap: 6, alignItems: 'center' }}>
            {l.item_pedido ? <div style={{ fontSize: 13 }}>{l.descricao}{l.recebido > 0 && <span style={{ fontSize: 11, color: 'var(--ink-3)' }}> · chegaram {l.recebido.toLocaleString('pt-BR')}</span>}</div>
              : <input style={inp} value={l.descricao} placeholder="O que comprar" onChange={e => mudar(l.chave, { descricao: e.target.value })} />}
            {l.item_pedido ? <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>{l.unidade}</span>
              : <input style={inp} value={l.unidade} placeholder="Un." maxLength={20} onChange={e => mudar(l.chave, { unidade: e.target.value })} />}
            {livre && <input style={{ ...inp, ...mono, textAlign: 'right' }} inputMode="decimal" aria-label="Preço unitário" value={l.preco} onChange={e => mudar(l.chave, { preco: e.target.value })} />}
            <input style={{ ...inp, ...mono, textAlign: 'right' }} inputMode="decimal" aria-label="Quantidade" value={l.quantidade} onChange={e => mudar(l.chave, { quantidade: e.target.value })} />
            {livre && <button type="button" aria-label="Tirar item" disabled={linhas.length === 1} onClick={() => setLinhas(ls => ls.filter(x => x.chave !== l.chave))} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)' }}>×</button>}
          </div>
        ))}
      </div>
      {livre && <Btn onClick={() => setLinhas(ls => [...ls, { chave: Date.now(), descricao: '', unidade: '', quantidade: '', preco: '', recebido: 0 }])}>+ Outro item</Btn>}
      <Field label="Motivo da mudança (vai ao financeiro)"><input style={{ ...inp, marginTop: 10 }} value={motivo} onChange={e => setMotivo(e.target.value)} placeholder="Opcional" /></Field>
    </Modal>
  )
}

/* ─── Envio ao fornecedor ─── */
function EnviarModal({ painel, baixarPdf, onClose, onDone }: { painel: PainelPedido; baixarPdf: () => void; onClose: () => void; onDone: (m: string) => void }) {
  const p = painel.pedido
  const [email, setEmail] = useState(painel.fornecedor_contato.email)
  const [err, setErr] = useState(''), [enviando, setEnviando] = useState(false)
  const texto = `Pedido de compra nº ${p.pedido_id}${p.revisao ? ` (revisão ${p.revisao})` : ''} — ${brl(p.valor_total)}. Entrega prevista: ${dataBR(p.data_entrega_prevista)}. Por favor, cite o número do pedido na NF-e.`

  const porEmail = async () => {
    setErr(''); setEnviando(true)
    try { await enviarPedido(p.pedido_id, 'email', email); onDone(`Pedido enviado por e-mail para ${email}.`) }
    catch (e) { setErr(erroDe(e, 'Não foi possível enviar o e-mail.')); setEnviando(false) }
  }
  const porWhatsapp = async () => {
    setErr(''); setEnviando(true)
    try {
      const blob = await pdfDoPedido(p.pedido_id)
      const arquivo = new File([blob], `pedido-de-compra-${p.pedido_id}.pdf`, { type: 'application/pdf' })
      const nav = navigator as Navigator & { canShare?: (d: { files: File[] }) => boolean }
      if (nav.canShare?.({ files: [arquivo] })) {
        await navigator.share({ files: [arquivo], text: texto, title: `Pedido de compra ${p.pedido_id}` })
      } else {
        baixarPdf()
        const fone = painel.fornecedor_contato.telefone.replace(/\D/g, '')
        const destino = fone ? `https://wa.me/${fone.length <= 11 ? '55' + fone : fone}` : 'https://wa.me/'
        window.open(`${destino}?text=${encodeURIComponent(texto + ' (PDF em anexo)')}`, '_blank', 'noopener')
      }
      await enviarPedido(p.pedido_id, 'whatsapp')
      onDone('Pedido marcado como enviado por WhatsApp.')
    } catch (e) {
      if ((e as { name?: string }).name === 'AbortError') { setEnviando(false); return }
      setErr(erroDe(e, 'Não foi possível compartilhar.')); setEnviando(false)
    }
  }
  return (
    <Modal title={`Enviar pedido #${p.pedido_id} ao fornecedor`} onClose={onClose} largura={520} footer={<Btn onClick={onClose}>Fechar</Btn>}>
      <Erro msg={err} />
      <p style={{ fontSize: 12.5, color: 'var(--ink-3)', marginBottom: 14 }}>{p.fornecedor_nome} recebe o PDF do pedido. Depois de enviado, o pedido passa a “Enviado”.</p>
      <Field label="E-mail do fornecedor"><input style={inp} type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="vendas@fornecedor.com.br" /></Field>
      <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap' }}>
        <Btn variant="primary" disabled={enviando || !email.includes('@')} onClick={porEmail}><Mail size={14} /> Enviar por e-mail</Btn>
        <Btn disabled={enviando} onClick={porWhatsapp}><MessageCircle size={14} /> WhatsApp</Btn>
        <Btn disabled={enviando} onClick={baixarPdf}><Download size={14} /> Baixar PDF</Btn>
      </div>
    </Modal>
  )
}

function CancelarModal({ pedido, onClose, onDone }: { pedido: number; onClose: () => void; onDone: (m: string) => void }) {
  const [motivo, setMotivo] = useState(''), [err, setErr] = useState(''), [salvando, setSalvando] = useState(false)
  const salvar = async () => {
    setErr(''); setSalvando(true)
    try {
      const r = await cancelarPedido(pedido, motivo) as { titulos_cancelados: number[]; titulos_com_pagamento: number[] }
      onDone(`Pedido cancelado.${r.titulos_cancelados.length ? ` ${r.titulos_cancelados.length} título(s) cancelado(s) no financeiro.` : ''}${r.titulos_com_pagamento.length ? ' Há título com pagamento: o financeiro foi avisado.' : ''}`)
    } catch (e) { setErr(erroDe(e, 'Não foi possível cancelar.')); setSalvando(false) }
  }
  return (
    <Modal title={`Cancelar pedido #${pedido}`} onClose={onClose} footer={<><Btn onClick={onClose}>Voltar</Btn><Btn variant="danger" onClick={salvar} disabled={salvando}>{salvando ? 'Cancelando…' : 'Cancelar pedido'}</Btn></>}>
      <Erro msg={err} />
      <p style={{ fontSize: 13, color: 'var(--ink-2)', marginBottom: 12 }}>Os títulos do pedido que ainda não foram pagos são cancelados no contas a pagar.</p>
      <Field label="Motivo"><input style={inp} value={motivo} onChange={e => setMotivo(e.target.value)} placeholder="Opcional — vai ao financeiro" /></Field>
    </Modal>
  )
}

function AvaliarModal({ pedidoId, fornecedor, onClose, onDone }: { pedidoId: number; fornecedor: number; onClose: () => void; onDone: () => void }) {
  const [q, setQ] = useState(5), [pt, setPt] = useState(5), [at, setAt] = useState(5), [c, setC] = useState(''), [saving, setSaving] = useState(false)
  const salvar = async () => { setSaving(true); try { await avaliacoesApi.create({ fornecedor, pedido: pedidoId, nota_qualidade: q, nota_pontualidade: pt, nota_atendimento: at, comentario: c }); onDone() } catch { setSaving(false) } }
  return <Modal title="Avaliar fornecedor" onClose={onClose} footer={<><Btn onClick={onClose}>Cancelar</Btn><Btn variant="primary" onClick={salvar} disabled={saving}>{saving ? 'Salvando…' : 'Salvar avaliação'}</Btn></>}>
    <StarsPick label="Qualidade" v={q} on={setQ} /><StarsPick label="Pontualidade" v={pt} on={setPt} /><StarsPick label="Atendimento" v={at} on={setAt} />
    <Field label="Comentário"><textarea style={{ ...inp, resize: 'vertical', minHeight: 60 }} value={c} onChange={e => setC(e.target.value)} placeholder="Opcional" /></Field>
  </Modal>
}
function StarsPick({ label, v, on }: { label: string; v: number; on: (n: number) => void }) {
  return <div style={{ marginBottom: 14 }}><div style={{ ...CAPS, fontSize: 10.5, marginBottom: 6 }}>{label}</div><div style={{ display: 'flex', gap: 4 }}>{[1, 2, 3, 4, 5].map(n => <button key={n} onClick={() => on(n)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2 }}><Star size={22} style={{ color: n <= v ? 'var(--accent)' : 'var(--line)', fill: n <= v ? 'var(--accent)' : 'none' }} /></button>)}</div></div>
}
