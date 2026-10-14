import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Crown, Plus, Trash2 } from 'lucide-react'
import apiClient from '@/api/apiClient'
import { Btn, Pill } from '@/components/malha'
import { formatCPFCNPJ } from '@/utils/masks'
import { parseApiErrors } from '@/utils/formErrors'
import { useEntidades, useExcluirParticipacao, useParticipacoes, useSalvarParticipacao } from '../api'

const campo = {
  padding: '7px 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--surface)',
  color: 'var(--ink)', fontSize: 13,
} as const

/**
 * Quem é o dono do empreendimento (docs/modulos/entidades.md §1–§3).
 *
 * - **Com entidade própria** (SPE, SCP, consórcio, afetação): os títulos dele são
 *   dela, e as participações são as sócias — a administradora vê a SPE inteira no
 *   ERP, as outras a veem pela cota na DRE.
 * - **De terceiro** (a entidade própria é externa): a empresa só executa; as obras
 *   e os títulos ficam com quem executa.
 * - **Sem entidade própria**: as participações são as co-donas, e o título de
 *   uma gera para as outras o intercompany da cota.
 */
export default function DonoECotas({ empreendimentoId, entidadePropria, podeEditar, onMudou }: {
  empreendimentoId: number
  entidadePropria: number | null
  podeEditar: boolean
  onMudou: () => void
}) {
  const entidades = useEntidades()
  const participacoes = useParticipacoes(empreendimentoId)
  const salvarPart = useSalvarParticipacao(empreendimentoId)
  const excluirPart = useExcluirParticipacao()
  const [dono, setDono] = useState<string>(entidadePropria ? String(entidadePropria) : '')
  const [salvandoDono, setSalvandoDono] = useState(false)
  const [erro, setErro] = useState('')
  const [nova, setNova] = useState({ entidade: '', cota: '', administradora: false })

  const todas = entidades.data ?? []
  const atual = todas.find(e => e.entidade_id === entidadePropria) ?? null
  const soma = (participacoes.data ?? []).reduce((s, p) => s + Number(p.cota), 0)
  const usadas = new Set((participacoes.data ?? []).map(p => p.entidade))

  async function salvarDono() {
    setSalvandoDono(true); setErro('')
    try {
      await apiClient.patch(`empreendimentos/${empreendimentoId}/`, { entidade_propria: dono ? Number(dono) : null })
      onMudou()
    } catch (e) {
      setErro(parseApiErrors(e)._form ?? parseApiErrors(e).entidade_propria ?? 'Não foi possível salvar.')
    } finally {
      setSalvandoDono(false)
    }
  }

  function adicionar() {
    setErro('')
    salvarPart.mutate(
      { dados: { entidade: Number(nova.entidade), cota: nova.cota.replace(',', '.'), administradora: nova.administradora } },
      {
        onSuccess: () => setNova({ entidade: '', cota: '', administradora: false }),
        onError: e => { const p = parseApiErrors(e); setErro(p.cota ?? p.administradora ?? p._form ?? 'Não foi possível salvar.') },
      },
    )
  }

  const situacao = !atual
    ? 'Sem entidade própria: lança no CNPJ/CPF das donas abaixo (ou da matriz, sem nenhuma).'
    : atual.externa
      ? `Empreendimento de terceiro: ${atual.nome} é dona. A empresa executa — obras e títulos ficam com quem executa.`
      : `Os títulos deste empreendimento são de ${atual.nome}.`

  return (
    <div className="flex flex-col gap-6" style={{ color: 'var(--ink-2)' }}>
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-bold" style={{ color: 'var(--ink)' }}>Entidade própria (dona)</h3>
        <p className="text-sm">{situacao}</p>
        {atual && (
          <p className="text-xs" style={{ color: 'var(--ink-3)' }}>
            {atual.papel_nome}{atual.documento ? ` · ${formatCPFCNPJ(atual.documento)}` : ''} ·{' '}
            <Link to="/app/entidades" style={{ color: 'var(--accent-ink)' }}>ver em Entidades</Link>
          </p>
        )}
        {podeEditar && (
          <div className="flex items-end gap-2 flex-wrap">
            <select value={dono} onChange={e => setDono(e.target.value)} style={{ ...campo, minWidth: 280 }}>
              <option value="">Sem entidade própria</option>
              <optgroup label="Do grupo (SPE, SCP, consórcio, afetação…)">
                {todas.filter(e => !e.externa && e.papel !== 'matriz' && e.papel !== 'filial').map(e => (
                  <option key={e.entidade_id} value={e.entidade_id}>{e.nome} — {e.papel_nome}</option>
                ))}
              </optgroup>
              <optgroup label="Externas (empreendimento de terceiro)">
                {todas.filter(e => e.externa).map(e => (
                  <option key={e.entidade_id} value={e.entidade_id}>{e.nome}</option>
                ))}
              </optgroup>
            </select>
            <Btn tam="sm" variant="primary" disabled={salvandoDono || dono === (entidadePropria ? String(entidadePropria) : '')}
              onClick={() => void salvarDono()}>
              {salvandoDono ? 'Salvando…' : 'Salvar dona'}
            </Btn>
            <Link to="/app/entidades" className="text-xs" style={{ color: 'var(--accent-ink)', paddingBottom: 8 }}>
              Cadastrar uma entidade nova
            </Link>
          </div>
        )}
        <p className="text-xs" style={{ color: 'var(--ink-3)' }}>
          A troca vale para os títulos lançados daqui em diante; os que já existem continuam com a entidade que têm.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-bold" style={{ color: 'var(--ink)' }}>
          {atual && !atual.externa ? `Sócias de ${atual.nome}` : 'Donas e cotas'}
        </h3>
        <p className="text-sm">
          {atual && !atual.externa
            ? 'Cada sócia vê o resultado da entidade própria pela cota, na DRE por entidade. A administradora vê o financeiro dela inteiro.'
            : 'Sem entidade própria, o título de uma dona gera para as outras o intercompany da cota delas.'}
        </p>
        {(participacoes.data ?? []).length === 0 && (
          <p className="text-sm" style={{ color: 'var(--ink-3)' }}>Nenhuma participação cadastrada.</p>
        )}
        {(participacoes.data ?? []).map(p => (
          <div key={p.participacao_id} className="flex items-center gap-2 text-sm">
            <strong style={{ color: 'var(--ink)' }}>{p.entidade_nome}</strong>
            <Pill kind="slate">{Number(p.cota).toLocaleString('pt-BR')}%</Pill>
            {p.administradora && <Pill kind="info"><Crown size={11} /> administradora</Pill>}
            {p.entidade_externa && <Pill kind="slate">externa</Pill>}
            {podeEditar && (
              <button type="button" title="Remover" onClick={() => excluirPart.mutate(p.participacao_id)}
                className="ml-auto" style={{ background: 'none', border: 'none', color: 'var(--danger-ink)', cursor: 'pointer' }}>
                <Trash2 size={14} />
              </button>
            )}
          </div>
        ))}
        {(participacoes.data ?? []).length > 0 && (
          <p className="text-xs" style={{ color: soma === 100 ? 'var(--ink-3)' : 'var(--accent-ink)' }}>
            Soma das cotas: {soma.toLocaleString('pt-BR')}%{soma !== 100 ? ' — o normal é fechar 100%.' : ''}
          </p>
        )}
        {podeEditar && (
          <div className="flex items-end gap-2 flex-wrap mt-2">
            <select value={nova.entidade} onChange={e => setNova(n => ({ ...n, entidade: e.target.value }))} style={{ ...campo, minWidth: 240 }}>
              <option value="">Entidade…</option>
              {todas.filter(e => !usadas.has(e.entidade_id) && e.entidade_id !== entidadePropria).map(e => (
                <option key={e.entidade_id} value={e.entidade_id}>{e.nome}{e.externa ? ' (externa)' : ''}</option>
              ))}
            </select>
            <input value={nova.cota} onChange={e => setNova(n => ({ ...n, cota: e.target.value.replace(/[^\d,]/g, '') }))}
              placeholder="Cota %" inputMode="decimal" style={{ ...campo, width: 90 }} />
            <label className="flex items-center gap-1.5 text-xs" style={{ paddingBottom: 8 }}>
              <input type="checkbox" checked={nova.administradora} onChange={e => setNova(n => ({ ...n, administradora: e.target.checked }))} />
              administradora
            </label>
            <Btn tam="sm" disabled={!nova.entidade || !nova.cota || salvarPart.isPending} onClick={adicionar}>
              <Plus size={14} /> Adicionar
            </Btn>
          </div>
        )}
        {erro && <p className="text-sm" style={{ color: 'var(--danger-ink)' }}>{erro}</p>}
      </section>
    </div>
  )
}
