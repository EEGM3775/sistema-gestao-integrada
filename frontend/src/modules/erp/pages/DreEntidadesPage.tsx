import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Building2, PieChart } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Card, Empty, Loading, Pill, SectionHead } from '@/components/malha'
import { BotaoExportar } from '@/components/malha'
import { formatBRL, apiDecimalToCents } from '@/utils/money'
import { formatCPFCNPJ } from '@/utils/masks'
import { erpClient } from '../api/erpClient'

const reais = (v: string | undefined) => (v == null ? '—' : formatBRL(apiDecimalToCents(v)))
const tom = (v: string | undefined) => (Number(v ?? 0) < 0 ? 'var(--danger-ink)' : 'var(--ink)')

type Regime = 'competencia' | 'caixa'

interface Lado {
  receita: string
  despesa: string
  resultado: string
  receita_terceiros: string
  despesa_terceiros: string
  despesa_repassada: string
  despesa_recebida: string
  receita_repassada: string
  receita_recebida: string
}

interface Cota {
  entidade: number
  nome: string
  empreendimento: string
  cota: string
  administradora: boolean
  competencia: string
  caixa: string
}

interface DreDaEntidade {
  entidade: number
  nome: string
  papel_nome: string
  documento: string
  competencia: Lado
  caixa: Lado
  cotas: Cota[]
  resultado_com_cotas: Record<Regime, string>
}

interface Dre {
  entidades: DreDaEntidade[]
  consolidado: {
    competencia: Partial<Lado>
    caixa: Partial<Lado>
    pelas_cotas: Record<Regime, string>
    resultado: Record<Regime, string>
  }
}

/**
 * DRE por entidade (docs/modulos/entidades.md §6). Cada CNPJ tem a sua: a
 * própria — com o intercompany pela natureza, para a despesa rateada ficar com
 * quem consumiu — e a parte pelas cotas das SPEs em que é sócia. O consolidado
 * soma o que a pessoa alcança e elimina o intercompany entre elas.
 */
export default function DreEntidadesPage() {
  const [regime, setRegime] = useState<Regime>('competencia')
  const [de, setDe] = useState('')
  const [ate, setAte] = useState('')
  const { data, isLoading } = useQuery({
    queryKey: ['erp', 'dre-entidades', de, ate],
    queryFn: async () => (await erpClient.get<Dre>('erp/entidades/dre/', {
      params: { ...(de ? { data_de: de } : {}), ...(ate ? { data_ate: ate } : {}) },
    })).data,
  })

  return (
    <div className="px-6 py-6 flex flex-col gap-5" style={{ color: 'var(--ink-2)' }}>
      <div className="flex items-end gap-4 flex-wrap">
        <div className="flex-1" style={{ minWidth: 260 }}>
          <Link to="/app/erp" className="inline-flex items-center gap-1.5 text-xs font-semibold mb-2" style={{ color: 'var(--ink-3)', textDecoration: 'none' }}>
            <ArrowLeft size={14} /> ERP / Financeiro
          </Link>
          <h1 className="text-xl font-bold" style={{ color: 'var(--ink)' }}>DRE por entidade</h1>
          <p className="text-xs" style={{ color: 'var(--ink-3)' }}>
            O resultado de cada CNPJ, com a parte nas SPEs pela cota — e o consolidado do grupo.
          </p>
        </div>
        <div className="flex items-end gap-2 flex-wrap text-xs">
          {/* Relatório: só exporta, no período da tela (R7). */}
          <BotaoExportar tam="md" recurso="erp.dre_entidades" recorte={{ data_de: de || undefined, data_ate: ate || undefined }} />
          <label className="flex flex-col gap-1">Vencimento de
            <input type="date" value={de} onChange={e => setDe(e.target.value)} style={campo} />
          </label>
          <label className="flex flex-col gap-1">até
            <input type="date" value={ate} onChange={e => setAte(e.target.value)} style={campo} />
          </label>
          <div className="flex" role="group" aria-label="Regime">
            {(['competencia', 'caixa'] as Regime[]).map(r => (
              <button key={r} type="button" onClick={() => setRegime(r)} aria-pressed={regime === r}
                style={{
                  ...campo, cursor: 'pointer', fontWeight: 600,
                  background: regime === r ? 'var(--accent-soft)' : 'var(--surface)',
                  color: regime === r ? 'var(--accent-ink)' : 'var(--ink-2)',
                }}>
                {r === 'competencia' ? 'Competência' : 'Caixa'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isLoading && <Loading o="a DRE das entidades" />}
      {data && data.entidades.length === 0 && (
        <Empty><Building2 size={22} /> Você ainda não tem acesso ao financeiro de nenhuma entidade.</Empty>
      )}

      {data && data.entidades.length > 1 && (
        <Card>
          <SectionHead sub="Soma das entidades que você alcança, sem o intercompany entre elas">Consolidado</SectionHead>
          <Linhas lado={data.consolidado[regime]} />
          {apiDecimalToCents(data.consolidado.pelas_cotas[regime]) !== 0 && (
            <Linha rotulo="Pelas cotas (SPEs fora do seu acesso)" valor={data.consolidado.pelas_cotas[regime]} />
          )}
          <Linha rotulo="Resultado" valor={data.consolidado.resultado[regime]} forte />
        </Card>
      )}

      <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
        {data?.entidades.map(e => (
          <Card key={e.entidade}>
            <SectionHead
              sub={`${e.papel_nome}${e.documento ? ` · ${formatCPFCNPJ(e.documento)}` : ' · sem CPF/CNPJ'}`}
            >
              {e.nome}
            </SectionHead>
            <Linhas lado={e[regime]} />
            {e.cotas.length > 0 && (
              <div className="mt-3 pt-3" style={{ borderTop: '1px dashed var(--line)' }}>
                <div className="text-xs font-semibold mb-1 flex items-center gap-1.5" style={{ color: 'var(--ink-3)' }}>
                  <PieChart size={13} /> Pelas cotas
                </div>
                {e.cotas.map(c => (
                  <Linha
                    key={c.entidade}
                    rotulo={<>{c.cota}% de {c.nome} {c.administradora && <Pill kind="info">administradora</Pill>}</>}
                    valor={c[regime]}
                  />
                ))}
                <Linha rotulo="Resultado com as cotas" valor={e.resultado_com_cotas[regime]} forte />
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  )
}

const campo = {
  padding: '6px 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink)',
  fontSize: 12.5,
} as const

function Linhas({ lado }: { lado: Partial<Lado> }) {
  const repasse = (a?: string, b?: string) => apiDecimalToCents(a) !== 0 || apiDecimalToCents(b) !== 0
  return (
    <div className="flex flex-col">
      <Linha rotulo="Receita" valor={lado.receita} />
      {repasse(lado.receita_recebida, lado.receita_repassada) && (
        <Linha rotulo="  da qual intercompany (recebida − repassada)" valor={String(
          (apiDecimalToCents(lado.receita_recebida) - apiDecimalToCents(lado.receita_repassada)) / 100,
        )} sutil />
      )}
      <Linha rotulo="Despesa" valor={lado.despesa} />
      {repasse(lado.despesa_recebida, lado.despesa_repassada) && (
        <Linha rotulo="  da qual intercompany (recebida − repassada)" valor={String(
          (apiDecimalToCents(lado.despesa_recebida) - apiDecimalToCents(lado.despesa_repassada)) / 100,
        )} sutil />
      )}
      <Linha rotulo="Resultado" valor={lado.resultado} forte />
    </div>
  )
}

function Linha({ rotulo, valor, forte, sutil }: { rotulo: ReactNode; valor?: string; forte?: boolean; sutil?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm" style={{
      padding: '5px 0', borderTop: forte ? '1px solid var(--line)' : undefined,
      fontSize: sutil ? 12 : undefined, color: sutil ? 'var(--ink-3)' : undefined,
    }}>
      <span style={{ whiteSpace: 'pre' }}>{rotulo}</span>
      <span style={{ fontWeight: forte ? 700 : 600, color: sutil ? 'var(--ink-3)' : tom(valor), fontVariantNumeric: 'tabular-nums' }}>
        {reais(valor)}
      </span>
    </div>
  )
}
