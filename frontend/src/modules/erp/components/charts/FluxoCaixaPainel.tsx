import { useMemo, useState, type ReactNode } from 'react'
import { BarChart3, LineChart as LineChartIcon } from 'lucide-react'
import { formatBRL } from '@/utils/money'
import { mesToBR } from '@/utils/dates'
import type { FluxoCaixaMes, PeriodoFluxo } from '../../types'
import { FluxoCaixaChart } from './FluxoCaixaChart'
import { COR_FLUXO, periodoDoAtalho, serieDoPeriodo, type AtalhoPeriodo, type ModoFluxo } from './fluxo'

const ATALHOS: { id: AtalhoPeriodo; rotulo: string; titulo: string }[] = [
  { id: '3m', rotulo: '3M', titulo: 'Últimos 3 meses' },
  { id: '6m', rotulo: '6M', titulo: 'Últimos 6 meses' },
  { id: '12m', rotulo: '12M', titulo: 'Últimos 12 meses' },
  { id: 'ano', rotulo: 'Ano', titulo: 'Ano atual, de janeiro até este mês' },
  { id: 'personalizado', rotulo: 'Personalizado', titulo: 'Escolher mês inicial e final' },
]

interface Props {
  data?: FluxoCaixaMes[]
  /** O período efetivo que o backend devolveu. */
  periodo?: PeriodoFluxo
  onPeriodo: (periodo: PeriodoFluxo) => void
  carregando: boolean
  /** Buscando um período novo com o anterior ainda na tela. */
  atualizando: boolean
}

/**
 * Fluxo de caixa realizado do hub ERP: atalhos de período (3M · 6M · 12M · Ano)
 * ou um intervalo de meses, barras ou linha, e o total do período no topo — o
 * padrão de Xero/Qonto/Omie (passar o mouse mostra entradas, saídas e resultado).
 */
export function FluxoCaixaPainel({ data, periodo, onPeriodo, carregando, atualizando }: Props) {
  const [atalho, setAtalho] = useState<AtalhoPeriodo>('12m')
  const [modo, setModo] = useState<ModoFluxo>('barras')
  const [rascunho, setRascunho] = useState<PeriodoFluxo>(() => periodoDoAtalho('12m'))

  const pontos = useMemo(() => (data && periodo ? serieDoPeriodo(data, periodo) : []), [data, periodo])
  const totais = useMemo(() => pontos.reduce(
    (acc, p) => ({ receitas: acc.receitas + p.receitas, despesas: acc.despesas + p.despesas }),
    { receitas: 0, despesas: 0 },
  ), [pontos])
  const temMovimento = pontos.some(p => p.receitas !== 0 || p.despesas !== 0)

  function escolherAtalho(id: AtalhoPeriodo) {
    setAtalho(id)
    if (id === 'personalizado') {
      if (periodo) setRascunho(periodo)
      return
    }
    onPeriodo(periodoDoAtalho(id))
  }

  function mudarRascunho(campo: keyof PeriodoFluxo, valor: string) {
    if (!valor) return
    const novo = { ...rascunho, [campo]: valor }
    setRascunho(novo)
    if (novo.inicio <= novo.fim) onPeriodo(novo)
  }

  return (
    <div className="rounded-xl p-4" style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF' }}>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div>
          <h2 className="text-sm font-semibold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-text)' }}>
            Fluxo de caixa realizado
          </h2>
          <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
            {periodo ? `${mesToBR(periodo.inicio)} a ${mesToBR(periodo.fim)}` : '—'}
            {atualizando && ' · atualizando…'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Segmentado rotulo="Período">
            {ATALHOS.map(a => (
              <BotaoSegmento key={a.id} ativo={atalho === a.id} titulo={a.titulo} onClick={() => escolherAtalho(a.id)}>
                {a.rotulo}
              </BotaoSegmento>
            ))}
          </Segmentado>
          <Segmentado rotulo="Tipo de gráfico">
            <BotaoSegmento ativo={modo === 'barras'} titulo="Barras" onClick={() => setModo('barras')}><BarChart3 size={14} /></BotaoSegmento>
            <BotaoSegmento ativo={modo === 'linha'} titulo="Linha, com o resultado do mês" onClick={() => setModo('linha')}><LineChartIcon size={14} /></BotaoSegmento>
          </Segmentado>
        </div>
      </div>

      {atalho === 'personalizado' && (
        <div className="flex flex-wrap items-center gap-2 mb-3 text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
          <label className="flex items-center gap-1.5">
            De
            <input type="month" value={rascunho.inicio} max={rascunho.fim} onChange={e => mudarRascunho('inicio', e.target.value)}
              className="rounded-md px-2 py-1" style={{ border: '1px solid #e2e8f0', color: 'var(--color-text)' }} />
          </label>
          <label className="flex items-center gap-1.5">
            até
            <input type="month" value={rascunho.fim} min={rascunho.inicio} onChange={e => mudarRascunho('fim', e.target.value)}
              className="rounded-md px-2 py-1" style={{ border: '1px solid #e2e8f0', color: 'var(--color-text)' }} />
          </label>
          {rascunho.inicio > rascunho.fim && <span style={{ color: '#dc2626' }}>O mês inicial precisa vir antes do final.</span>}
        </div>
      )}

      {carregando ? (
        <div className="rounded-lg animate-pulse" style={{ height: 300, background: '#f1f5f9' }} />
      ) : !temMovimento ? (
        <div className="flex items-center justify-center" style={{ height: 160, color: 'var(--color-text-muted)', fontSize: '0.85rem', fontFamily: 'var(--font-body)' }}>
          Sem movimento de caixa no período.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3 mb-2">
            <Total rotulo="Receitas" cor={COR_FLUXO.receitas} centavos={totais.receitas} />
            <Total rotulo="Despesas" cor={COR_FLUXO.despesas} centavos={totais.despesas} />
            <Total rotulo="Resultado" cor={COR_FLUXO.resultado} centavos={totais.receitas - totais.despesas} sinal />
          </div>
          <div style={{ opacity: atualizando ? 0.55 : 1, transition: 'opacity .15s' }}>
            <FluxoCaixaChart pontos={pontos} modo={modo} />
          </div>
        </>
      )}
    </div>
  )
}

function Segmentado({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={rotulo} className="inline-flex rounded-lg p-0.5" style={{ background: '#f1f5f9' }}>
      {children}
    </div>
  )
}

function BotaoSegmento({ ativo, titulo, onClick, children }: { ativo: boolean; titulo: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button" title={titulo} aria-pressed={ativo} onClick={onClick}
      className="px-2.5 py-1 rounded-md text-xs font-medium flex items-center transition-colors"
      style={{
        fontFamily: 'var(--font-body)',
        background: ativo ? '#FFFFFF' : 'transparent',
        color: ativo ? 'var(--color-brand)' : 'var(--color-text-muted)',
        boxShadow: ativo ? '0 1px 2px rgba(12,26,48,.08)' : 'none',
      }}
    >
      {children}
    </button>
  )
}

function Total({ rotulo, cor, centavos, sinal }: { rotulo: string; cor: string; centavos: number; sinal?: boolean }) {
  return (
    <div className="rounded-lg px-3 py-2" style={{ background: '#f8fafc' }}>
      <div className="flex items-center gap-1.5 text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
        <span style={{ width: 8, height: 8, borderRadius: 2, background: cor }} />
        {rotulo}
      </div>
      <div className="text-sm font-semibold" style={{
        fontFamily: 'var(--font-body)', fontVariantNumeric: 'tabular-nums',
        color: sinal && centavos < 0 ? COR_FLUXO.despesas : 'var(--color-text)',
      }}>
        {formatBRL(centavos)}
      </div>
    </div>
  )
}
