import React from 'react'
import { Network, Receipt, FileText, Boxes, Link2 } from 'lucide-react'
import type { Demanda, PedidoCompra, Recebimento, OfertaFornecedor, Proposta } from '../types'

/**
 * Chips de **seam** (rede / ERP / NF-e / estoque) — read-only. A planta pede
 * "não esconder" os ganchos da expansão sem deixá-los editáveis nesta fase
 * (docs/modulos/moduloscm.md §Comportamento; expansão §4/§6). Regra de UX: só
 * aparecem quando o campo está preenchido, então não poluem o uso pré-expansão;
 * quando a Esfera de Rede ligar, já há lugar para eles. Visual "linkado, não
 * editável": borda tracejada e tom mudo (o de rede usa `--net`, cor de rede/IA).
 */
export interface SeamDescriptor {
  key: string
  icon: React.ReactNode
  label: string
  title: string
  net?: boolean
}

export const SeamChip: React.FC<{ seam: SeamDescriptor }> = ({ seam }) => (
  <span
    title={seam.title}
    style={{
      display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 600,
      padding: '2px 8px', borderRadius: 999, whiteSpace: 'nowrap',
      border: `1px dashed ${seam.net ? 'var(--net)' : 'var(--line)'}`,
      background: seam.net ? 'var(--net-soft)' : 'transparent',
      color: seam.net ? 'var(--net-ink)' : 'var(--ink-3)',
    }}
  >
    <span style={{ display: 'grid', placeItems: 'center' }}>{React.cloneElement(seam.icon as React.ReactElement<{ size?: number }>, { size: 11 })}</span>
    {seam.label}
  </span>
)

export const SeamChips: React.FC<{ seams: SeamDescriptor[] }> = ({ seams }) =>
  seams.length === 0 ? null : (
    <span style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
      {seams.map(s => <SeamChip key={s.key} seam={s} />)}
    </span>
  )

const redeSeam = (visibilidade: string, refExterna?: string, origemTenant?: string | null): SeamDescriptor[] => {
  const out: SeamDescriptor[] = []
  if (visibilidade === 'rede') out.push({ key: 'rede', icon: <Network />, label: 'Rede', title: 'Publicado na rede (marketplace) — Esfera de Rede (H2)', net: true })
  if (origemTenant) out.push({ key: 'externo', icon: <Network />, label: 'Da rede', title: 'Origem em tenant externo (cópia espelhada)', net: true })
  else if (refExterna) out.push({ key: 'ref', icon: <Link2 />, label: 'Ref. rede', title: `Referência estável na rede: ${refExterna.slice(0, 8)}…` })
  return out
}

export const demandaSeams = (d: Demanda): SeamDescriptor[] => {
  const s = redeSeam(d.visibilidade, d.ref_externa, null)
  if (d.origem === 'estoque') s.push({ key: 'estoque', icon: <Boxes />, label: 'Estoque', title: 'Nasceu de falta no estoque (SIL — módulo futuro)' })
  return s
}

export const ofertaSeams = (o: OfertaFornecedor): SeamDescriptor[] =>
  redeSeam(o.visibilidade)

export const pedidoSeams = (p: PedidoCompra): SeamDescriptor[] => {
  const s = redeSeam('privada', p.ref_externa, p.origem_tenant)
  if (p.conta_pagar_ref) s.push({ key: 'erp', icon: <Receipt />, label: `ContaPagar #${p.conta_pagar_ref}`, title: 'Conta a pagar gerada no ERP (seam frouxo)' })
  return s
}

export const recebimentoSeams = (r: Recebimento): SeamDescriptor[] => {
  const s: SeamDescriptor[] = []
  if (r.nota_fiscal_ref) s.push({ key: 'nf', icon: <FileText />, label: 'NF-e', title: `NF-e conciliada: ${r.nota_fiscal_ref}` })
  if (r.local_entrega) s.push({ key: 'estoque', icon: <Boxes />, label: 'Estoque', title: `Entrada de estoque: ${r.local_entrega} (SIL — módulo futuro)` })
  return s
}

export const propostaSeams = (p: Proposta): SeamDescriptor[] =>
  p.origem_tenant ? [{ key: 'externo', icon: <Network />, label: 'Da rede', title: 'Proposta de fornecedor externo (cópia espelhada)', net: true }] : []
