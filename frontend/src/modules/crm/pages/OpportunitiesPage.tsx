import { useTextoDaLixeira } from '@/hooks/useRetencaoDoLixo'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Plus, Search, RefreshCw, BarChart3 } from 'lucide-react'
import { useOpportunities, useCreateOpportunity, useUpdateOpportunity, useDeleteOpportunity } from '../hooks/useOpportunities'
import { formatBRL } from '@/utils/money'
import type { Opportunity, OpportunityPayload } from '../types'

/**
 * Lista de Oportunidades - /app/crm/opportunities
 */
export default function OpportunitiesPage() {
  const textoLixeira = useTextoDaLixeira()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingOpportunity, setEditingOpportunity] = useState<Opportunity | null>(null)

  const { data, isLoading, refetch } = useOpportunities({ search })
  const createMutation = useCreateOpportunity()
  const updateMutation = useUpdateOpportunity()
  const deleteMutation = useDeleteOpportunity()

  const handleCreate = async (payload: OpportunityPayload) => {
    await createMutation.mutateAsync(payload)
    setFormOpen(false)
    refetch()
  }

  const handleUpdate = async (payload: OpportunityPayload) => {
    if (editingOpportunity) {
      await updateMutation.mutateAsync({ id: editingOpportunity.id, payload })
      setEditingOpportunity(null)
      refetch()
    }
  }

  const handleDelete = async (id: string) => {
    if (confirm(textoLixeira('esta oportunidade'))) {
      await deleteMutation.mutateAsync(id)
      refetch()
    }
  }

  return (
    <div className="px-6 py-8">
      {/* Cabeçalho */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/app/crm')} className="p-2 rounded-lg hover:bg-gray-100" style={{ color: 'var(--color-text-muted)', background: 'none', border: 'none', cursor: 'pointer' }}>
            <ArrowLeft size={20} />
          </button>
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#fef3c7', color: '#d97706' }}>
            <BarChart3 size={22} />
          </div>
          <div>
            <h1 className="text-xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-text)' }}>
              Oportunidades
            </h1>
            <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {isLoading ? 'Carregando…' : `${data?.count ?? 0} oportunidade${(data?.count ?? 0) !== 1 ? 's' : ''}`}
            </p>
          </div>
        </div>
        <button
          onClick={() => setFormOpen(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
          style={{ background: 'var(--color-brand)', color: '#FFFFFF', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
        >
          <Plus size={16} /> Nova Oportunidade
        </button>
      </div>

      {/* Filtros */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-muted)' }} />
          <input
            type="text"
            placeholder="Buscar por nome…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm outline-none"
            style={{ border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)', color: 'var(--color-text)', background: '#FFFFFF' }}
          />
        </div>
        <button onClick={() => refetch()} className="p-2.5 rounded-lg border" title="Atualizar"
          style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Tabela */}
      <div className="rounded-xl overflow-hidden" style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-8 h-8 rounded-full border-2 animate-spin" style={{ borderColor: 'var(--color-brand)', borderTopColor: 'transparent' }} />
          </div>
        ) : (data?.results?.length ?? 0) === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <BarChart3 size={40} style={{ color: '#cbd5e1' }} />
            <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {search ? 'Nenhum resultado para os filtros aplicados.' : 'Nenhuma oportunidade cadastrada ainda.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full" style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-body)' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                  {['Nome', 'Conta', 'Stage', 'Valor', 'Probabilidade', 'Ações'].map(h => (
                    <th key={h} className="text-left text-xs font-semibold uppercase tracking-wide px-5 py-3"
                      style={{ color: 'var(--color-text-muted)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data?.results.map((opp: Opportunity, i: number) => (
                  <tr key={opp.id} className="transition-colors duration-100"
                    style={{ borderBottom: i < (data?.results.length ?? 0) - 1 ? '1px solid #f1f5f9' : 'none' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                    <td className="px-5 py-3.5">
                      <span className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>
                        {opp.name}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{opp.account || '—'}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-xs px-2 py-1 rounded" style={{
                        background: opp.stage === 'QUALIFICACAO' ? '#dbeafe' :
                          opp.stage === 'PROPOSTA' ? '#e0e7ff' :
                          opp.stage === 'NEGOCIACAO' ? '#fef3c7' :
                          opp.stage === 'GANHO' ? '#dcfce7' : '#fee2e2',
                        color: opp.stage === 'QUALIFICACAO' ? '#1d4ed8' :
                          opp.stage === 'PROPOSTA' ? '#4338ca' :
                          opp.stage === 'NEGOCIACAO' ? '#d97706' :
                          opp.stage === 'GANHO' ? '#16a34a' : '#dc2626'
                      }}>
                        {opp.stage.charAt(0) + opp.stage.slice(1).toLowerCase()}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{formatBRL(opp.amount)}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{opp.probability}%</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <button onClick={() => setEditingOpportunity(opp)} className="text-xs"
                          style={{ color: 'var(--color-brand)', background: 'none', border: 'none', cursor: 'pointer' }}>
                          Editar
                        </button>
                        <button onClick={() => handleDelete(opp.id)} className="text-xs"
                          style={{ color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}>
                          Excluir
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Formulário */}
      {formOpen && (
        <OpportunityForm
          onClose={() => setFormOpen(false)}
          onSave={handleCreate}
        />
      )}

      {editingOpportunity && (
        <OpportunityForm
          opportunity={editingOpportunity}
          onClose={() => setEditingOpportunity(null)}
          onSave={handleUpdate}
        />
      )}
    </div>
  )
}

function OpportunityForm({ opportunity, onClose, onSave }: {
  opportunity?: Opportunity | null
  onClose: () => void
  onSave: (payload: OpportunityPayload) => void
}) {
  const [name, setName] = useState(opportunity?.name ?? '')
  const [closeDate, setCloseDate] = useState(opportunity?.close_date?.split('T')[0] ?? '')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave({ name, close_date: closeDate })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-full max-w-md" style={{ fontFamily: 'var(--font-body)' }}>
        <h2 className="text-lg font-bold mb-4" style={{ color: 'var(--color-brand)' }}>
          {opportunity ? 'Editar Oportunidade' : 'Nova Oportunidade'}
        </h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--color-text-muted)' }}>Nome</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1.5px solid #e2e8f0' }}
            />
          </div>
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--color-text-muted)' }}>Data de Fechamento</label>
            <input
              type="date"
              value={closeDate}
              onChange={e => setCloseDate(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1.5px solid #e2e8f0' }}
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg text-sm"
              style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF', cursor: 'pointer' }}>
              Cancelar
            </button>
            <button type="submit" className="px-4 py-2 rounded-lg text-sm"
              style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none', cursor: 'pointer' }}>
              Salvar
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}