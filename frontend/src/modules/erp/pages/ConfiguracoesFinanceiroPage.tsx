import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Files, Loader2, Lock, ScrollText } from 'lucide-react'
import { buttonPrimaryStyle, inputStyle } from '../components/forms/formStyles'
import { useLimitesLote, useSalvarLimitesLote } from '../hooks/useCobranca'
import { dataHoraBR } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import type { LimiteDeLote, LimitesLote } from '../types'

const milhar = (n: number) => n.toLocaleString('pt-BR')

/**
 * Configurações do financeiro — hoje, quantos boletos e notas um lote emite
 * (pedido do dono, 01/10/2026; `payment/planos.py` §5.5u).
 *
 * O plano dá o teto (é o paywall); a empresa escolhe um número menor, como
 * freio contra o lote grande por engano. Quem muda é o administrador ou quem
 * tem a permissão especial `erp.lote.configurar` — que nenhum papel padrão
 * recebe: o admin a concede em Papéis e Acessos. Os outros veem o número e
 * quem pode mudá-lo. A regra e as frases vêm da API (frontend-convencoes §11).
 */
export default function ConfiguracoesFinanceiroPage() {
  const limites = useLimitesLote()
  const d = limites.data

  return (
    <div className="px-6 py-6 flex flex-col gap-6" style={{ color: 'var(--ink-2)', maxWidth: 820 }}>
      <div>
        <Link to="/app/erp" className="inline-flex items-center gap-1.5 text-xs font-semibold mb-2" style={{ color: 'var(--ink-3)', textDecoration: 'none' }}>
          <ArrowLeft size={14} /> ERP / Financeiro
        </Link>
        <h1 className="text-xl font-bold" style={{ color: 'var(--ink)' }}>Configurações do financeiro</h1>
        <p className="text-xs" style={{ color: 'var(--ink-3)' }}>O que a empresa decide para o próprio financeiro, dentro do que o plano permite.</p>
      </div>

      {limites.isLoading && <p className="flex items-center gap-2 text-sm"><Loader2 size={15} className="animate-spin" /> Carregando…</p>}
      {limites.error && <p className="text-sm" style={{ color: 'var(--danger-ink)' }}>{parseApiErrors(limites.error)._form ?? 'Não foi possível carregar a configuração.'}</p>}
      {d && <LimitesDosLotes dados={d} />}
    </div>
  )
}

function LimitesDosLotes({ dados }: { dados: LimitesLote }) {
  const salvar = useSalvarLimitesLote()
  const [boletos, setBoletos] = useState('')
  const [notas, setNotas] = useState('')
  const [salvo, setSalvo] = useState(false)
  useEffect(() => {
    setBoletos(dados.boletos_por_lote.escolhido?.toString() ?? '')
    setNotas(dados.notas_por_lote.escolhido?.toString() ?? '')
  }, [dados])

  const erros = salvar.error ? parseApiErrors(salvar.error) : {}
  const enviar = () => {
    setSalvo(false)
    salvar.mutate(
      { boletos_por_lote: boletos === '' ? null : Number(boletos), notas_por_lote: notas === '' ? null : Number(notas) },
      { onSuccess: () => setSalvo(true) },
    )
  }

  return (
    <section style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', background: 'var(--surface)', padding: 20 }}>
      <h2 className="text-base font-bold" style={{ color: 'var(--ink)' }}>Limite dos lotes</h2>
      <p className="text-sm mt-1" style={{ lineHeight: 1.5 }}>
        Quantas contas um clique de "Gerar boletos" ou "Emitir notas" alcança. O plano{' '}
        <strong>{dados.plano || 'contratado'}</strong> dá o teto; abaixo dele, a empresa escolhe o seu —
        um freio contra o lote grande por engano. Em branco, vale o máximo do plano.
      </p>

      <div className="grid gap-4 mt-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
        <CampoDeLimite rotulo="Boletos por lote" icone={<Files size={16} />} limite={dados.boletos_por_lote}
          valor={boletos} onValor={setBoletos} podeEditar={dados.pode_editar} erro={erros.boletos_por_lote} />
        <CampoDeLimite rotulo="Notas fiscais por lote" icone={<ScrollText size={16} />} limite={dados.notas_por_lote}
          valor={notas} onValor={setNotas} podeEditar={dados.pode_editar} erro={erros.notas_por_lote} />
      </div>

      {dados.pode_editar ? (
        <div className="flex items-center justify-end gap-3 mt-4">
          {salvo && <span className="text-sm" style={{ color: 'var(--good-ink)' }}>Salvo.</span>}
          {erros._form && <span className="text-sm" style={{ color: 'var(--danger-ink)' }}>{erros._form}</span>}
          <button type="button" onClick={enviar} disabled={salvar.isPending} style={{ ...buttonPrimaryStyle, opacity: salvar.isPending ? 0.7 : 1 }}>
            {salvar.isPending ? 'Salvando…' : 'Salvar limites'}
          </button>
        </div>
      ) : (
        <p className="flex items-start gap-2 text-sm mt-4" style={{ padding: '10px 12px', borderRadius: 'var(--r-md)', background: 'var(--surface-2)', color: 'var(--ink-3)' }}>
          <Lock size={15} style={{ flex: 'none', marginTop: 2 }} />
          Quem muda este limite é o administrador da empresa, ou quem recebeu dele a permissão
          "Definir quantos boletos e notas um lote emite" em Papéis e Acessos.
        </p>
      )}
      {dados.atualizado_em && (
        <p className="text-xs mt-3" style={{ color: 'var(--ink-3)' }}>
          Alterado em {dataHoraBR(dados.atualizado_em)}{dados.atualizado_por ? ` por ${dados.atualizado_por}` : ''}.
        </p>
      )}
    </section>
  )
}

function CampoDeLimite({ rotulo, icone, limite, valor, onValor, podeEditar, erro }: {
  rotulo: string
  icone: ReactNode
  limite: LimiteDeLote
  valor: string
  onValor: (v: string) => void
  podeEditar: boolean
  erro?: string
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="flex items-center gap-2 text-sm font-semibold" style={{ color: 'var(--ink)' }}>{icone} {rotulo}</span>
      {podeEditar ? (
        <input type="number" min={1} max={limite.teto_plano} inputMode="numeric" value={valor}
          placeholder={`Máximo do plano (${milhar(limite.teto_plano)})`}
          onChange={e => onValor(e.target.value.replace(/\D/g, ''))}
          style={{ ...inputStyle, borderColor: erro ? 'var(--danger)' : undefined }} />
      ) : (
        <span className="text-lg font-bold" style={{ color: 'var(--ink)' }}>{milhar(limite.valor)}</span>
      )}
      <span className="text-xs" style={{ color: erro ? 'var(--danger-ink)' : 'var(--ink-3)' }}>
        {erro ?? (limite.escolhido
          ? `Vale ${milhar(limite.valor)} — o plano permite até ${milhar(limite.teto_plano)}.`
          : `Vale o máximo do plano: ${milhar(limite.teto_plano)}.`)}
      </span>
    </label>
  )
}
