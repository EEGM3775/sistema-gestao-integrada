import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Card, Empty, Loading } from '@/components/malha'
import { usePdca } from '../contexto'
import { useCustoDoPlano } from '../hooks'
import type { CustoDaEtapa } from '../api/suprimentosApi'

const reais = (v: string | number) => Number(v ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })

const COLUNAS = [
  { chave: 'orcado', rotulo: 'Orçado', dica: 'Custo direto do orçamento vigente, na fração de cada atividade' },
  { chave: 'comprometido', rotulo: 'Comprometido', dica: 'Pedidos de compra da obra (aprovados em diante), rateados por insumo' },
  { chave: 'recebido', rotulo: 'Recebido', dica: 'O que já chegou dos pedidos, ao preço do pedido' },
  { chave: 'aplicado', rotulo: 'Aplicado', dica: 'O que saiu do estoque para a obra e a etapa (só por etapa)' },
  { chave: 'medido', rotulo: 'Medido', dica: 'O que as medições aprovadas pagaram aos empreiteiros' },
] as const

/** **O custo dentro do plano** — o mesmo serviço visto pelo orçamento, pelas
 *  compras, pelo estoque e pela medição, lado a lado. É a pergunta da reunião
 *  de obra: *o que orçamos, o que já comprometemos, o que chegou, o que saiu
 *  para a frente e o que pagamos aos empreiteiros?* Pedido e recebido não sabem
 *  para qual serviço compraram — vêm rateados pelo consumo de cada insumo no
 *  orçamento, e a tela diz isso. */
export function PainelCusto({ cronogramaId }: { cronogramaId: number }) {
  const { selecionar } = usePdca()
  const { data, isLoading, isError } = useCustoDoPlano(cronogramaId)
  const [abertas, setAbertas] = useState<Set<string>>(new Set())
  if (isLoading) return <Loading o="o custo do plano" />
  if (isError || !data) return <Card><Empty>Não foi possível montar o custo do plano.</Empty></Card>
  const naoAlocado = Object.values(data.nao_alocado).some((v) => Number(v) !== 0)
  const celula = { padding: '8px 12px', borderBottom: '1px solid var(--line-2)', whiteSpace: 'nowrap' as const }
  const numero = { ...celula, textAlign: 'right' as const, fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' as const }

  function linhaDaEtapa(e: CustoDaEtapa) {
    const chave = String(e.etapa)
    const aberta = abertas.has(chave)
    const estourou = Number(e.orcado) > 0 && Math.max(Number(e.comprometido), Number(e.aplicado) + Number(e.medido)) > Number(e.orcado)
    return (
      <tbody key={chave}>
        <tr>
          <td style={celula}>
            <button
              type="button"
              onClick={() => setAbertas((s) => { const n = new Set(s); if (n.has(chave)) n.delete(chave); else n.add(chave); return n })}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 5, fontWeight: 650, color: 'var(--ink)', fontSize: 12.5 }}
            >
              {aberta ? <ChevronDown size={13} /> : <ChevronRight size={13} />}{e.etapa_nome}
            </button>
            {estourou && <span style={{ marginLeft: 6, fontSize: 10.5, color: 'var(--danger-ink)', fontWeight: 650 }}>acima do orçado</span>}
          </td>
          {COLUNAS.map((c) => <td key={c.chave} style={{ ...numero, fontWeight: 650 }}>{reais(e[c.chave])}</td>)}
        </tr>
        {aberta && e.atividades.map((a) => (
          <tr key={a.atividade} style={{ background: 'var(--inset)' }}>
            <td style={{ ...celula, paddingLeft: 32, fontSize: 12 }}>
              <button type="button" onClick={() => selecionar({ tipo: 'atividade', id: a.atividade })} style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--ink-2)', fontSize: 12, textAlign: 'left' }}>
                <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-3)' }}>{a.codigo}</span> {a.nome}
              </button>
            </td>
            <td style={{ ...numero, fontSize: 12 }}>{reais(a.orcado)}</td>
            <td style={{ ...numero, fontSize: 12 }}>{reais(a.comprometido)}</td>
            <td style={{ ...numero, fontSize: 12 }}>{reais(a.recebido)}</td>
            <td style={{ ...numero, fontSize: 12, color: 'var(--ink-3)' }}>—</td>
            <td style={{ ...numero, fontSize: 12 }}>{reais(a.medido)}</td>
          </tr>
        ))}
      </tbody>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 1100 }}>
      <div style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>
        <strong>O custo dentro do plano.</strong> Cada etapa com o dinheiro do orçamento, das compras, do estoque e da
        medição lado a lado. Comprometido e recebido vêm <em>rateados</em> pelo consumo de cada insumo no orçamento — o
        pedido não diz para qual serviço comprou. O aplicado é por etapa, que é como o estoque apropria a saída.
      </div>
      <Card pad={false}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr>
                <th style={{ ...celula, textAlign: 'left', fontSize: 10.5, color: 'var(--ink-3)', background: 'var(--surface-2)' }}>Etapa</th>
                {COLUNAS.map((c) => (
                  <th key={c.chave} title={c.dica} style={{ ...celula, textAlign: 'right', fontSize: 10.5, color: 'var(--ink-3)', background: 'var(--surface-2)', cursor: 'help' }}>{c.rotulo}</th>
                ))}
              </tr>
            </thead>
            {data.etapas.length === 0 ? (
              <tbody><tr><td colSpan={6} style={{ padding: 18, textAlign: 'center', color: 'var(--ink-3)' }}>Nenhuma atividade ligada ao orçamento ainda — o custo aparece quando o plano conversa com o orçamento.</td></tr></tbody>
            ) : data.etapas.map(linhaDaEtapa)}
            <tbody>
              {naoAlocado && (
                <tr>
                  <td style={{ ...celula, color: 'var(--ink-3)', fontStyle: 'italic' }} title="Pedido de insumo que nenhuma atividade consome, saída sem etapa, medição sem atividade nem item orçado">Sem atividade nem etapa</td>
                  <td style={numero}>—</td>
                  <td style={{ ...numero, color: 'var(--ink-3)' }}>{reais(data.nao_alocado.comprometido)}</td>
                  <td style={{ ...numero, color: 'var(--ink-3)' }}>{reais(data.nao_alocado.recebido)}</td>
                  <td style={{ ...numero, color: 'var(--ink-3)' }}>{reais(data.nao_alocado.aplicado)}</td>
                  <td style={{ ...numero, color: 'var(--ink-3)' }}>{reais(data.nao_alocado.medido)}</td>
                </tr>
              )}
              <tr>
                <td style={{ ...celula, fontWeight: 750 }}>Total da obra</td>
                {COLUNAS.map((c) => <td key={c.chave} style={{ ...numero, fontWeight: 750 }}>{reais(data.total[c.chave])}</td>)}
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
