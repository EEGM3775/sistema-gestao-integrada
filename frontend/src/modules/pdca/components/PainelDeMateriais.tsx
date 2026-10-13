import { useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Card, Empty, Loading, Pill, SectionHead } from '@/components/malha'
import { controle } from '../api/controleApi'
import { pdcaKeys } from '../api/queryKeys'

const reais = (v: string | number | null | undefined) =>
  v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
const qtd = (v: string | null | undefined) =>
  v == null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 2 })
const mono = { fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' as const }

type Filtro = 'todos' | 'acima' | 'fora'

/** **Materiais gastos** — cada insumo: o que o orçamento previa, o que já saiu
 *  do estoque para a obra e, com o avanço físico, o que **deveria** ter saído
 *  até aqui. Desperdício (ou desvio de material) aparece no meio da obra, e não
 *  na última nota. */
export function PainelDeMateriais({ obraId }: { obraId: number }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: pdcaKeys.controle.materiais(obraId),
    queryFn: () => controle.materiais(obraId),
  })
  const [filtro, setFiltro] = useState<Filtro>('todos')
  const linhas = useMemo(() => {
    const todas = data?.insumos ?? []
    if (filtro === 'acima') return todas.filter((l) => l.desvio_pct != null && Number(l.desvio_pct) > 5)
    if (filtro === 'fora') return todas.filter((l) => l.fora_do_orcamento)
    return todas
  }, [data, filtro])

  if (isLoading) return <Loading o="os materiais da obra" />
  if (isError || !data) return <div style={{ padding: 22 }}><Card><Empty>Não foi possível apurar os materiais da obra.</Empty></Card></div>
  if (!data.insumos.length) {
    return (
      <div style={{ padding: 22 }}>
        <Card><Empty>
          Nenhum material orçado nem aplicado ainda. O orçado vem das composições abertas do orçamento aprovado;
          o aplicado, das saídas do estoque para a obra.
        </Empty></Card>
      </div>
    )
  }

  const acima = data.insumos.filter((l) => l.desvio_pct != null && Number(l.desvio_pct) > 5).length
  const fora = data.insumos.filter((l) => l.fora_do_orcamento).length
  const celula = { padding: '7px 11px', borderBottom: '1px solid var(--line-2)', whiteSpace: 'nowrap' as const }
  const num = { ...celula, ...mono, textAlign: 'right' as const }
  const cab = { ...celula, fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase' as const, color: 'var(--ink-3)', background: 'var(--surface-2)' }
  const botao = (f: Filtro, rotulo: string) => (
    <button type="button" onClick={() => setFiltro(f)} style={{
      fontSize: 12, padding: '4px 10px', borderRadius: 999, cursor: 'pointer',
      border: '1px solid var(--line)', background: filtro === f ? 'var(--ink)' : 'var(--surface)',
      color: filtro === f ? 'var(--surface)' : 'var(--ink-2)',
    }}>{rotulo}</button>
  )

  return (
    <div style={{ padding: '18px 22px 40px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
        <Bloco rotulo="Material orçado" valor={reais(data.totais.orcado)} apoio={
          data.orcamento ? <Link to={`/app/orcamento/analisar?obra=${data.obra}`} style={{ color: 'inherit' }}>relação de insumos ↗</Link> : 'sem orçamento aprovado'} />
        <Bloco rotulo="Material aplicado" valor={reais(data.totais.aplicado)} apoio={<Link to="/app/sil" style={{ color: 'inherit' }}>saídas do estoque ↗</Link>} />
        <Bloco rotulo="Avanço físico" valor={data.realizado_pct == null ? '—' : `${data.realizado_pct.toFixed(1).replace('.', ',')}%`}
          apoio="a régua do esperado" />
        <Bloco rotulo="Acima do avanço" valor={String(acima)} apoio="insumos >5% sobre o esperado" tom={acima ? 'var(--danger-ink)' : undefined} />
        <Bloco rotulo="Fora do orçamento" valor={String(fora)} apoio="aplicados sem previsão" tom={fora ? 'var(--accent-ink)' : undefined} />
      </Card>

      <SectionHead right={<div style={{ display: 'flex', gap: 6 }}>{botao('todos', 'Todos')}{botao('acima', 'Acima do avanço')}{botao('fora', 'Fora do orçamento')}</div>}>
        Orçado × aplicado × esperado
      </SectionHead>
      <Card pad={false} style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead>
            <tr>
              {['Insumo', 'Und', 'Orçado', 'Aplicado', 'Consumido', 'Esperado', 'Desvio', 'R$ orçado', 'R$ aplicado'].map((h, i) => (
                <th key={h} style={{ ...cab, textAlign: i <= 1 ? 'left' : 'right' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {linhas.map((l, i) => {
              const desvio = l.desvio_pct == null ? null : Number(l.desvio_pct)
              return (
                <tr key={`${l.item ?? l.descricao}-${i}`}>
                  <td style={{ ...celula, color: 'var(--ink)', fontWeight: 550, whiteSpace: 'normal' }}>
                    {l.descricao} {l.fora_do_orcamento && <Pill kind="accent">fora do orçamento</Pill>}
                  </td>
                  <td style={{ ...celula, color: 'var(--ink-3)' }}>{l.unidade}</td>
                  <td style={num}>{qtd(l.orcado_qtd)}</td>
                  <td style={num}>{qtd(l.aplicado_qtd)}</td>
                  <td style={num}>{l.consumido_pct == null ? '—' : `${l.consumido_pct.replace('.', ',')}%`}</td>
                  <td style={num}>{qtd(l.esperado_qtd)}</td>
                  <td style={{ ...num, fontWeight: 650, color: desvio == null ? 'var(--ink-3)' : desvio > 5 ? 'var(--danger-ink)' : desvio < -5 ? 'var(--info-ink)' : 'var(--ink)' }}>
                    {desvio == null ? '—' : `${desvio > 0 ? '+' : ''}${String(l.desvio_pct).replace('.', ',')}%`}
                  </td>
                  <td style={num}>{reais(l.orcado_valor)}</td>
                  <td style={num}>{reais(l.aplicado_valor)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </Card>
      <p style={{ fontSize: 11.5, color: 'var(--ink-3)', margin: 0 }}>
        Esperado = orçado × avanço físico realizado da obra. Desvio positivo é material saindo adiante do serviço feito
        (perda, estoque de frente ou desvio); negativo, material ainda por aplicar. Mão de obra fica de fora — é Hh, não estoque.
      </p>
    </div>
  )
}

function Bloco({ rotulo, valor, apoio, tom }: { rotulo: string; valor: string; apoio: ReactNode; tom?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span style={{ fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-3)' }}>{rotulo}</span>
      <span style={{ ...mono, fontSize: 19, fontWeight: 700, color: tom ?? 'var(--ink)' }}>{valor}</span>
      <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{apoio}</span>
    </div>
  )
}
