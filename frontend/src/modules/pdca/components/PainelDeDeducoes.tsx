import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Btn, CampoMoeda, Num, Pill } from '@/components/malha'
import { apiDecimalToCents, centsToApiDecimal } from '@/utils/money'
import type { Deducao, LinhaDeDeducao, TipoDeducao, TotaisDaMedicao } from '../types'

/**
 * **O que sai do bruto além da retenção.**
 *
 * A diferença entre as duas não é contábil, é de destino: retenção é dinheiro
 * que a construtora **segura e devolve** quando a cláusula é cumprida; dedução
 * é dinheiro que **não volta** — imposto retido vai para a União, adiantamento
 * já foi pago antes, multa é penalidade.
 *
 * Sem isto, o título que saía para o ERP era o bruto menos a retenção, e o
 * empreiteiro recebia um boleto que não batia com a nota dele em nenhum
 * contrato com retenção legal — que é a maioria dos contratos de empreitada do
 * país. O gestor "resolvia" mexendo no percentual de retenção, e aí a
 * `LiberacaoRetencao` oferecia de volta imposto que nunca foi da construtora.
 */

const TIPOS: { valor: TipoDeducao; rotulo: string; dica: string }[] = [
  { valor: 'inss', rotulo: 'INSS', dica: 'Retenção previdenciária sobre a mão de obra' },
  { valor: 'iss', rotulo: 'ISS', dica: 'Imposto sobre serviços retido na fonte' },
  { valor: 'irrf', rotulo: 'IRRF', dica: 'Imposto de renda retido na fonte' },
  { valor: 'adiantamento', rotulo: 'Adiantamento', dica: 'Amortização de valor já pago antes' },
  { valor: 'material', rotulo: 'Material da contratante', dica: 'Material fornecido pela construtora' },
  { valor: 'multa', rotulo: 'Multa', dica: 'Penalidade contratual' },
  { valor: 'outros', rotulo: 'Outros', dica: 'Exige descrição' },
]

interface Rascunho {
  chave: string
  tipo: TipoDeducao
  descricao: string
  /** `true` = percentual sobre uma base; `false` = valor fechado. */
  porPercentual: boolean
  percentual: string
  baseCentavos: number
  valorCentavos: number
}

const dinheiro = (v: string | number) =>
  Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

export function paraApi(linhas: Rascunho[]): LinhaDeDeducao[] {
  return linhas.map(l => ({
    tipo: l.tipo,
    descricao: l.descricao,
    base_calculo: l.porPercentual && l.baseCentavos > 0
      ? centsToApiDecimal(l.baseCentavos) : null,
    percentual: l.porPercentual ? (l.percentual || '0').replace(',', '.') : null,
    valor: l.porPercentual ? null : centsToApiDecimal(l.valorCentavos),
  }))
}

export function useDeducoes(deducoes: Deducao[] | undefined) {
  const [linhas, setLinhas] = useState<Rascunho[]>([])
  const [base, setBase] = useState('')

  const vindas = useMemo<Rascunho[]>(
    () => (deducoes ?? []).map(d => ({
      chave: String(d.deducao_id),
      tipo: d.tipo,
      descricao: d.descricao,
      porPercentual: d.percentual != null,
      percentual: d.percentual ?? '',
      baseCentavos: apiDecimalToCents(d.base_calculo),
      valorCentavos: apiDecimalToCents(d.valor),
    })),
    [deducoes],
  )
  const assinaturaVinda = useMemo(
    () => vindas.map(l => `${l.tipo}:${l.percentual}:${l.baseCentavos}:${l.valorCentavos}:${l.descricao}`).join('|'),
    [vindas],
  )

  useEffect(() => {
    if (assinaturaVinda === base) return
    setLinhas(vindas)
    setBase(assinaturaVinda)
  }, [vindas, assinaturaVinda, base])

  const assinatura = useMemo(
    () => linhas.map(l => (
      `${l.tipo}:${l.porPercentual ? `${l.percentual}/${l.baseCentavos}` : l.valorCentavos}:${l.descricao}`
    )).join('|'),
    [linhas],
  )

  return { linhas, setLinhas, assinatura, paraEnviar: paraApi(linhas) }
}

export default function PainelDeDeducoes({
  linhas, setLinhas, totais, somenteLeitura,
}: {
  linhas: Rascunho[]
  setLinhas: React.Dispatch<React.SetStateAction<Rascunho[]>>
  totais: TotaisDaMedicao | null
  somenteLeitura: boolean
}) {
  const mudar = (chave: string, mudanca: Partial<Rascunho>) =>
    setLinhas(antes => antes.map(l => (l.chave === chave ? { ...l, ...mudanca } : l)))

  const aplicado = (chave: string) =>
    totais?.deducoes.find(d => String(d.deducao_id) === chave)?.valor

  if (somenteLeitura && linhas.length === 0) {
    return (
      <p style={{ color: 'var(--ink-3)', fontSize: 13, margin: 0 }}>
        Esta medição não tem deduções — o líquido é o bruto menos a retenção.
      </p>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {linhas.map(l => (
          <div
            key={l.chave}
            style={{
              display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap',
              padding: '10px 12px', border: '1px solid var(--line)', borderRadius: 9,
            }}
          >
            <div style={{ minWidth: 150 }}>
              <Rotulo>Tipo</Rotulo>
              <select
                value={l.tipo}
                disabled={somenteLeitura}
                onChange={e => mudar(l.chave, { tipo: e.target.value as TipoDeducao })}
                style={campo}
              >
                {TIPOS.map(t => (
                  <option key={t.valor} value={t.valor} title={t.dica}>{t.rotulo}</option>
                ))}
              </select>
            </div>

            <div style={{ flex: 1, minWidth: 160 }}>
              <Rotulo>
                Descrição{l.tipo === 'outros' && <strong> (obrigatória)</strong>}
              </Rotulo>
              <input
                value={l.descricao}
                disabled={somenteLeitura}
                placeholder={l.tipo === 'outros' ? 'O que está sendo descontado' : 'opcional'}
                onChange={e => mudar(l.chave, { descricao: e.target.value })}
                style={campo}
              />
            </div>

            <div>
              <Rotulo>Como</Rotulo>
              <select
                value={l.porPercentual ? 'pct' : 'valor'}
                disabled={somenteLeitura}
                onChange={e => mudar(l.chave, { porPercentual: e.target.value === 'pct' })}
                style={{ ...campo, width: 118 }}
              >
                <option value="pct">Percentual</option>
                <option value="valor">Valor fixo</option>
              </select>
            </div>

            {l.porPercentual ? (
              <>
                <div style={{ width: 90 }}>
                  <Rotulo>%</Rotulo>
                  <input
                    value={l.percentual}
                    disabled={somenteLeitura}
                    inputMode="decimal"
                    onChange={e => mudar(l.chave, { percentual: e.target.value })}
                    style={{ ...campo, textAlign: 'right', fontFamily: 'var(--mono)' }}
                  />
                </div>
                <div style={{ width: 150 }}>
                  <Rotulo>
                    <span title="Vazio = sobre o bruto da medição. Preenchida = a parcela declarada (a mão de obra dentro do bruto, para o INSS).">
                      Base (opcional)
                    </span>
                  </Rotulo>
                  <CampoMoeda
                    centavos={l.baseCentavos}
                    aoMudar={v => mudar(l.chave, { baseCentavos: v })}
                    disabled={somenteLeitura}
                  />
                </div>
              </>
            ) : (
              <div style={{ width: 150 }}>
                <Rotulo>Valor</Rotulo>
                <CampoMoeda
                  centavos={l.valorCentavos}
                  aoMudar={v => mudar(l.chave, { valorCentavos: v })}
                  disabled={somenteLeitura}
                />
              </div>
            )}

            <div style={{ minWidth: 110, textAlign: 'right' }}>
              <Rotulo>Desconta</Rotulo>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 14, padding: '7px 0' }}>
                {aplicado(l.chave) != null ? (
                  <Num>− {dinheiro(aplicado(l.chave) as string)}</Num>
                ) : (
                  <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>ao salvar</span>
                )}
              </div>
            </div>

            {!somenteLeitura && (
              <Btn
                onClick={() => setLinhas(antes => antes.filter(x => x.chave !== l.chave))}
                title="Remover esta dedução"
              >
                <Trash2 size={14} />
              </Btn>
            )}
          </div>
        ))}
      </div>

      {!somenteLeitura && (
        <Btn
          style={{ marginTop: 10 }}
          onClick={() => setLinhas(antes => [...antes, {
            chave: `novo-${Date.now()}-${antes.length}`,
            tipo: 'inss',
            descricao: '',
            porPercentual: true,
            percentual: '11',
            baseCentavos: 0,
            valorCentavos: 0,
          }])}
        >
          <Plus size={14} /> Acrescentar dedução
        </Btn>
      )}

      {totais && Number(totais.total_deducoes) > 0 && (
        <p style={{
          margin: '12px 0 0', fontSize: 12.5, color: 'var(--ink-2)',
          display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap',
        }}>
          <Pill kind="slate">
            {dinheiro(totais.bruto)} − {dinheiro(totais.retencao)} de retenção
            {' '}− {dinheiro(totais.total_deducoes)} de deduções
          </Pill>
          <strong>= {dinheiro(totais.liquido)} de título</strong>
        </p>
      )}
    </div>
  )
}

function Rotulo({ children }: { children: React.ReactNode }) {
  return (
    <label style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)', marginBottom: 3 }}>
      {children}
    </label>
  )
}

const campo: React.CSSProperties = {
  width: '100%', padding: '7px 9px', borderRadius: 8,
  border: '1px solid var(--line)', background: 'var(--surface)',
  color: 'var(--ink)', fontSize: 13,
}
