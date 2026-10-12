/* Ficha do item — "de onde veio, onde está registrado, loja e preço" (dono,
 * 11/10/2026). Uma chamada (`catalogo/itens/{id}/ficha/`); cada bloco diz o que
 * existe de verdade e "sem …" quando não há, nunca um número inventado. */
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Store, Warehouse, FileSpreadsheet, History, Tag } from 'lucide-react'
import { fichaItem } from '../api/scmApi'
import { brl, qty, dataBR } from '../lib'
import { Btn, Card, Info, Loading, Modal, Pill } from './ui'
import { CAPS, mono } from './estilo'
import type { FichaItem as Ficha } from '../types'

const ORIGEM_KIND: Record<string, 'info' | 'amber' | 'good' | 'slate'> = { base: 'info', orcamento: 'amber', compra: 'good', manual: 'slate' }

function Bloco({ icone, titulo, children }: { icone: ReactNode; titulo: string; children: ReactNode }) {
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, ...CAPS, fontSize: 10.5, marginBottom: 7 }}>{icone}{titulo}</div>
      {children}
    </div>
  )
}
const vazio = (t: string) => <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>{t}</div>
const th = { ...CAPS, fontSize: 10, textAlign: 'left' as const, padding: '7px 10px', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' }
const td = { padding: '8px 10px', borderBottom: '1px solid var(--line-2)', fontSize: 12.5 }

export function FichaItemModal({ item, onClose }: { item: number; onClose: () => void }) {
  const { data: f, isLoading } = useQuery({ queryKey: ['scm', 'ficha', item], queryFn: () => fichaItem(item) })
  return (
    <Modal title={f ? `${f.codigo_interno} · ${f.descricao}` : 'Ficha do item'} onClose={onClose} largura={760} footer={<Btn onClick={onClose}>Fechar</Btn>}>
      {isLoading || !f ? <Loading /> : <Conteudo f={f} />}
    </Modal>
  )
}

function Conteudo({ f }: { f: Ficha }) {
  return (
    <>
      <Card style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: 14 }}>
        <Info k="Unidade" v={f.unidade} />
        <Info k="Tipo" v={f.tipo_nome} />
        <Info k="Categoria" v={f.categoria || '—'} />
        <Info k="Estoque" v={f.estocavel ? `${qty(f.estoque_total)} ${f.unidade}` : 'não estocável'} mono />
        <Info k="Último preço" v={brl(f.preco_resumo.ultimo)} mono />
        <Info k="Faixa paga" v={f.preco_resumo.menor ? `${brl(f.preco_resumo.menor)} – ${brl(f.preco_resumo.maior)}` : 'sem compra'} mono />
      </Card>

      <Bloco icone={<Tag size={13} />} titulo="De onde veio">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', fontSize: 13 }}>
          <Pill kind={ORIGEM_KIND[f.origem.tipo] ?? 'slate'}>{f.origem.rotulo}</Pill>
          {f.origem.detalhe && <span style={{ color: 'var(--ink)' }}>{f.origem.detalhe}</span>}
          {f.origem.criado_em && <span style={{ ...mono, fontSize: 12, color: 'var(--ink-3)' }}>cadastrado em {dataBR(f.origem.criado_em)}</span>}
          {f.origem.fonte_nome && <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>· preço de referência: {f.origem.fonte_nome} {f.origem.codigo_referencia}</span>}
        </div>
      </Bloco>

      <Bloco icone={<Store size={13} />} titulo={`Lojas (${f.lojas.length})`}>
        {f.lojas.length === 0 ? vazio('Nenhum fornecedor vende este item ainda.') : (
          <div style={{ overflowX: 'auto', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 520 }}>
              <thead><tr><th style={th}>Fornecedor</th><th style={{ ...th, textAlign: 'right' }}>Preço de tabela</th><th style={{ ...th, textAlign: 'right' }}>Último pago</th><th style={th}>Última compra</th><th style={th}>Cód. na loja</th></tr></thead>
              <tbody>{f.lojas.map(l => (
                <tr key={l.fornecedor}>
                  <td style={{ ...td, color: 'var(--ink)', fontWeight: 600 }}>{l.fornecedor_nome}{l.compra_direta && <> <Pill kind="net">compra direta</Pill></>}</td>
                  <td style={{ ...td, ...mono, textAlign: 'right' }}>{l.preco_oferta ? brl(l.preco_oferta) : '—'}</td>
                  <td style={{ ...td, ...mono, textAlign: 'right', fontWeight: 650 }}>{l.ultimo_preco_pago ? brl(l.ultimo_preco_pago) : 'sem compra'}</td>
                  <td style={{ ...td, ...mono }}>{l.ultima_compra ? dataBR(l.ultima_compra) : '—'}</td>
                  <td style={{ ...td, ...mono, color: 'var(--ink-3)' }}>{l.codigo_no_fornecedor || '—'}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Bloco>

      <Bloco icone={<History size={13} />} titulo="Preços pagos">
        {f.historico_precos.length === 0 ? vazio('Sem compra registrada.') : (
          <div style={{ overflowX: 'auto', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', maxHeight: 220, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 460 }}>
              <thead><tr><th style={th}>Data</th><th style={th}>Pedido</th><th style={th}>Fornecedor</th><th style={{ ...th, textAlign: 'right' }}>Qtd.</th><th style={{ ...th, textAlign: 'right' }}>Preço</th></tr></thead>
              <tbody>{f.historico_precos.map((h, i) => (
                <tr key={i}>
                  <td style={{ ...td, ...mono }}>{dataBR(h.data)}</td>
                  <td style={{ ...td, ...mono }}>#{h.pedido}</td>
                  <td style={td}>{h.fornecedor_nome}</td>
                  <td style={{ ...td, ...mono, textAlign: 'right' }}>{qty(h.quantidade)} {h.unidade}</td>
                  <td style={{ ...td, ...mono, textAlign: 'right', fontWeight: 650 }}>{brl(h.preco_unitario)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Bloco>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))', gap: 16 }}>
        <Bloco icone={<Warehouse size={13} />} titulo="No estoque">
          {f.estoque.length === 0 ? vazio(f.estocavel ? 'Sem saldo em nenhum local.' : 'Item não estocável.') : f.estoque.map(s => (
            <div key={s.local} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--line-2)' }}>
              <span>{s.local_nome}</span><span style={mono}>{qty(s.quantidade)} {f.unidade}</span>
            </div>
          ))}
        </Bloco>
        <Bloco icone={<FileSpreadsheet size={13} />} titulo="Onde está registrado">
          <div style={{ fontSize: 13, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {f.orcamentos.length === 0 ? vazio('Em nenhum orçamento.') : f.orcamentos.map(o => (
              <div key={o.orcamento}>Orçamento <b>{o.descricao}</b> v{o.versao}{o.obra ? ` · ${o.obra}` : ''} <span style={{ ...mono, color: 'var(--ink-3)' }}>({o.linhas} linha{o.linhas > 1 ? 's' : ''})</span></div>
            ))}
            <div style={{ color: 'var(--ink-2)' }}>{f.uso.pedidos} pedido{f.uso.pedidos !== 1 ? 's' : ''} de compra · {f.uso.demandas} demanda{f.uso.demandas !== 1 ? 's' : ''}</div>
          </div>
        </Bloco>
      </div>
    </>
  )
}
