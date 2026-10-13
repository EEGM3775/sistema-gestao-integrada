import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, CalendarClock, ChevronDown, ChevronRight } from 'lucide-react'
import apiClient from '@/api/apiClient'
import { useAuth } from '@/hooks/useAuth'
import { scmKeys } from '../api/queryKeys'
import { dataBR, num, qty } from '../lib'

interface ObraNaFila {
  obra: number
  obra_nome: string
  cronograma: number
  versao: number
  insumos_a_comprar: number
  primeira_falta: string | null
  valor_a_comprar: string
  antecedencia_padrao: number | null
  cobertura: { folhas_fora_da_conta: number; tem_orcamento_vigente: boolean }
}

interface InsumoNaFila {
  insumo: string
  item: number | null
  descricao: string
  unidade: string
  tipo_demanda: 'material' | 'servico'
  a_comprar: string
  valor_a_comprar: string
  primeira_falta: string | null
  obras: { obra: number; obra_nome: string; cronograma: number; a_comprar: string; primeira_falta: string | null }[]
}

interface Fila { obras: ObraNaFila[]; por_insumo: InsumoNaFila[] }

const CAPS = { fontSize: 10.5, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 } as const
const mono = { fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' } as const
const reais = (v: string) => (num(v) ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

function quandoPedir(iso: string | null): { texto: string; cor: string } {
  if (!iso) return { texto: '—', cor: 'var(--ink-3)' }
  const hoje = new Date(); hoje.setHours(0, 0, 0, 0)
  const dias = Math.round((new Date(`${iso}T00:00:00`).getTime() - hoje.getTime()) / 86400000)
  if (dias < 0) return { texto: `${dataBR(iso)} · atrasado`, cor: 'var(--danger-ink)' }
  if (dias <= 7) return { texto: `${dataBR(iso)} · em ${dias} d`, cor: 'var(--accent-ink)' }
  return { texto: dataBR(iso), cor: 'var(--ink-2)' }
}

/** **A mesma fila do posto Plano do PDCA**, vista pelo comprador: o que o
 *  cronograma de cada obra pede, por insumo, já descontado o estoque da obra,
 *  os pedidos em aberto e as demandas. O aço das três obras aparece numa linha
 *  só, com a obra e a data de cada pedaço — e vira demanda daqui. */
export function CompraPeloCronograma() {
  const { hasPermission } = useAuth()
  const podeGerar = hasPermission('scm.demanda.edit')
  const qc = useQueryClient()
  const { data, isLoading, isError } = useQuery({
    queryKey: [...scmKeys.all, 'do-cronograma'],
    queryFn: async () => (await apiClient.get<Fila>('scm/demandas/do-cronograma/')).data,
    staleTime: 60_000,
  })
  const gerar = useMutation({
    mutationFn: async (corpo: { cronograma: number; insumos?: string[] }) =>
      (await apiClient.post<{ demandas: { demanda: number; itens: number }[] }>('scm/demandas/do-cronograma/gerar/', corpo)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: scmKeys.all })
      qc.invalidateQueries({ queryKey: ['pdca'] })
    },
  })
  const [abertos, setAbertos] = useState<Set<string>>(new Set())
  const [aviso, setAviso] = useState<string | null>(null)

  async function demandar(cronograma: number, obraNome: string, insumos?: string[]) {
    setAviso(null)
    try {
      const r = await gerar.mutateAsync({ cronograma, insumos })
      setAviso(`${obraNome}: ${r.demandas.map((d) => `demanda #${d.demanda} (${d.itens} ${d.itens === 1 ? 'item' : 'itens'})`).join(', ')} em rascunho — confira e publique na Cotação.`)
    } catch (e) {
      const corpo = (e as { response?: { data?: { detail?: string } } }).response?.data
      setAviso(corpo?.detail ?? 'Não foi possível gerar a demanda.')
    }
  }

  if (isError) return null
  const obras = data?.obras ?? []
  const insumos = data?.por_insumo ?? []

  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', boxShadow: 'var(--shadow-sm)', marginTop: 22, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 16px 6px', flexWrap: 'wrap' }}>
        <CalendarClock size={16} style={{ color: 'var(--accent-ink)' }} />
        <h2 style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.02em', color: 'var(--ink-2)' }}>Comprar pelo cronograma</h2>
        <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>o que o plano de cada obra pede, já descontado estoque, pedido e demanda</span>
      </div>

      {isLoading && <div style={{ padding: '10px 16px 18px', fontSize: 12.5, color: 'var(--ink-3)' }}>Lendo os cronogramas das obras…</div>}
      {!isLoading && obras.length === 0 && (
        <div style={{ padding: '10px 16px 18px', fontSize: 12.5, color: 'var(--ink-3)' }}>
          Nenhuma obra tem plano publicado no PDCA. Quando tiver, o que ele pede de material aparece aqui com a data de compra.
        </div>
      )}

      {aviso && <div style={{ margin: '4px 16px 8px', fontSize: 12.5, padding: '8px 12px', borderRadius: 'var(--r-sm)', background: 'var(--accent-soft)', color: 'var(--accent-ink)' }}>{aviso}</div>}

      {obras.length > 0 && (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', padding: '6px 16px 12px' }}>
          {obras.map((o) => {
            const q = quandoPedir(o.primeira_falta)
            return (
              <div key={o.obra} style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', padding: '9px 11px', minWidth: 220, display: 'flex', flexDirection: 'column', gap: 4 }}>
                <Link to={`/app/pdca/o/${o.obra}/plano?vista=suprimentos`} style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                  {o.obra_nome} <ArrowUpRight size={12} style={{ color: 'var(--ink-3)' }} />
                </Link>
                <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                  plano v{o.versao} · {o.insumos_a_comprar} {o.insumos_a_comprar === 1 ? 'insumo' : 'insumos'} a comprar · {reais(o.valor_a_comprar)}
                </span>
                {o.insumos_a_comprar > 0 && <span style={{ fontSize: 11.5, color: q.cor }}>pedir a partir de {q.texto}</span>}
                {o.cobertura.folhas_fora_da_conta > 0 && (
                  <span style={{ fontSize: 11, color: 'var(--accent-ink)' }}>{o.cobertura.folhas_fora_da_conta} atividades sem orçamento ligado (fora da conta)</span>
                )}
                {podeGerar && o.insumos_a_comprar > 0 && (
                  <button
                    type="button"
                    disabled={gerar.isPending}
                    onClick={() => void demandar(o.cronograma, o.obra_nome)}
                    style={{ alignSelf: 'flex-start', marginTop: 2, fontSize: 12, fontWeight: 650, padding: '4px 10px', borderRadius: 'var(--r-sm)', border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink-2)', cursor: 'pointer' }}
                  >
                    Gerar demanda da obra
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}

      {insumos.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 560 }}>
            <thead>
              <tr>
                {['Insumo', 'A comprar', 'Valor (orçado)', 'Pedir até', 'Obras'].map((h, i) => (
                  <th key={h} style={{ ...CAPS, textAlign: i === 1 || i === 2 ? 'right' : 'left', padding: '8px 14px', borderTop: '1px solid var(--line-2)', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {insumos.map((g) => {
                const aberto = abertos.has(g.insumo)
                const q = quandoPedir(g.primeira_falta)
                return (
                  <FragmentoDoInsumo
                    key={g.insumo}
                    g={g}
                    aberto={aberto}
                    quando={q}
                    podeGerar={podeGerar && !gerar.isPending}
                    aoAlternar={() => setAbertos((s) => { const n = new Set(s); if (n.has(g.insumo)) n.delete(g.insumo); else n.add(g.insumo); return n })}
                    aoGerar={(cronograma, obraNome) => void demandar(cronograma, obraNome, [g.insumo])}
                  />
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function FragmentoDoInsumo(
  { g, aberto, quando, podeGerar, aoAlternar, aoGerar }: {
    g: InsumoNaFila; aberto: boolean; quando: { texto: string; cor: string }; podeGerar: boolean
    aoAlternar: () => void; aoGerar: (cronograma: number, obraNome: string) => void
  },
) {
  const celula = { padding: '9px 14px', borderBottom: '1px solid var(--line-2)' }
  return (
    <>
      <tr className="scm-row">
        <td style={celula}>
          <button type="button" onClick={aoAlternar} style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 5, color: 'var(--ink)', fontWeight: 600, fontSize: 13, textAlign: 'left' }}>
            {aberto ? <ChevronDown size={13} /> : <ChevronRight size={13} />}{g.descricao}
          </button>
          <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}> · {g.unidade || 'un'}{g.tipo_demanda === 'servico' ? ' · locação' : ''}</span>
        </td>
        <td style={{ ...celula, ...mono, textAlign: 'right', fontWeight: 700 }}>{qty(g.a_comprar)}</td>
        <td style={{ ...celula, ...mono, textAlign: 'right', color: 'var(--ink-2)' }}>{reais(g.valor_a_comprar)}</td>
        <td style={{ ...celula, ...mono, color: quando.cor, whiteSpace: 'nowrap' }}>{quando.texto}</td>
        <td style={{ ...celula, fontSize: 12, color: 'var(--ink-2)' }}>{g.obras.map((o) => o.obra_nome).join(', ')}</td>
      </tr>
      {aberto && g.obras.map((o) => (
        <tr key={o.obra} style={{ background: 'var(--surface-2)' }}>
          <td style={{ ...celula, paddingLeft: 34, fontSize: 12.5 }}>{o.obra_nome}</td>
          <td style={{ ...celula, ...mono, textAlign: 'right', fontSize: 12.5 }}>{qty(o.a_comprar)}</td>
          <td style={celula} />
          <td style={{ ...celula, ...mono, fontSize: 12.5, color: quandoPedir(o.primeira_falta).cor }}>{quandoPedir(o.primeira_falta).texto}</td>
          <td style={celula}>
            {podeGerar && (
              <button type="button" onClick={() => aoGerar(o.cronograma, o.obra_nome)} style={{ fontSize: 12, fontWeight: 650, padding: '3px 9px', borderRadius: 'var(--r-sm)', border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink-2)', cursor: 'pointer' }}>
                Demandar
              </button>
            )}
          </td>
        </tr>
      ))}
    </>
  )
}
