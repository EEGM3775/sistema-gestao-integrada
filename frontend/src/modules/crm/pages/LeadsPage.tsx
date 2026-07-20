import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Plus, Search, RefreshCw } from 'lucide-react'
import { useLeads, useCreateLead, useUpdateLead, useDeleteLead, useConvertLead } from '../hooks/useLeads'
import type { Lead, LeadFiltros, StatusLead, PaginatedResponse } from '../types'

const STATUS_OPTIONS: StatusLead[] = ['NOVO', 'CONTATADO', 'QUALIFICADO', 'CONVERTIDO', 'PERDIDO']

/**
 * Lista de Leads - /app/crm/leads
 */
export default function LeadsPage() {
  const [search, setSearch] = useState('')
  const [statusFiltro, setStatusFiltro] = useState<StatusLead | ''>('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingLead, setEditingLead] = useState<Lead | null>(null)

  const { data, isLoading, refetch } = useLeads({ search, status: statusFiltro || undefined })
  const createMutation = useCreateLead()
  const updateMutation = useUpdateLead()
  const deleteMutation = useDeleteLead()
  const convertMutation = useConvertLead()

  const handleCreate = async (payload: { first_name: string; last_name: string; email: string }) => {
    await createMutation.mutateAsync(payload)
    setFormOpen(false)
    refetch()
  }

  const handleUpdate = async (payload: { first_name: string; last_name: string; email: string }) => {
    if (editingLead) {
      await updateMutation.mutateAsync({ id: editingLead.id, payload })
      setEditingLead(null)
      refetch()
    }
  }

  const handleDelete = async (id: string) => {
    if (confirm('Tem certeza que deseja excluir este lead?')) {
      await deleteMutation.mutateAsync(id)
      refetch()
    }
  }

  const handleConvert = async (id: string) => {
    if (confirm('Converter este lead em Account + Contact + Opportunity?')) {
      await convertMutation.mutateAsync(id)
      refetch()
    }
  }

  return (
    <div className="px-6 py-8">
      {/* Cabeçalho */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#dcfce7', color: 'var(--color-brand)' }}>
            <Search size={22} />
          </div>
          <div>
            <h1 className="text-xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Leads
            </h1>
            <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {isLoading ? 'Carregando…' : `${data?.count ?? 0} lead${(data?.count ?? 0) !== 1 ? 's' : ''}`}
            </p>
          </div>
        </div>
        <button
          onClick={() => setFormOpen(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
          style={{ background: 'var(--color-brand)', color: '#FFFFFF', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
        >
          <Plus size={16} /> Novo Lead
        </button>
      </div>

      {/* Filtros */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-muted)' }} />
          <input
            type="text"
            placeholder="Buscar por nome ou e-mail…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm outline-none"
            style={{ border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)', color: 'var(--color-text)', background: '#FFFFFF' }}
          />
        </div>
        <select
          value={statusFiltro}
          onChange={e => setStatusFiltro(e.target.value as StatusLead | '')}
          className="px-4 py-2.5 rounded-lg text-sm outline-none"
          style={{ border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)', color: 'var(--color-text)', background: '#FFFFFF', cursor: 'pointer' }}
        >
          <option value="">Todos os status</option>
          {STATUS_OPTIONS.map(s => (
            <option key={s} value={s}>{s.charAt(0) + s.slice(1).toLowerCase()}</option>
          ))}
        </select>
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
            <Search size={40} style={{ color: '#cbd5e1' }} />
            <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {search || statusFiltro ? 'Nenhum resultado para os filtros aplicados.' : 'Nenhum lead cadastrado ainda.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full" style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-body)' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                  {['Nome', 'E-mail', 'Telefone', 'Empresa', 'Status', 'Score', 'Ações'].map(h => (
                    <th key={h} className="text-left text-xs font-semibold uppercase tracking-wide px-5 py-3"
                      style={{ color: 'var(--color-text-muted)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data?.results.map((lead: Lead, i: number) => (
                  <tr key={lead.id} className="transition-colors duration-100"
                    style={{ borderBottom: i < (data?.results.length ?? 0) - 1 ? '1px solid #f1f5f9' : 'none' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                    <td className="px-5 py-3.5">
                      <span className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>
                        {lead.first_name} {lead.last_name}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{lead.email}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{lead.phone || '—'}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{lead.company || '—'}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-xs px-2 py-1 rounded" style={{
                        background: lead.status === 'NOVO' ? '#dbeafe' :
                          lead.status === 'CONTATADO' ? '#e0e7ff' :
                          lead.status === 'QUALIFICADO' ? '#ede9fe' :
                          lead.status === 'CONVERTIDO' ? '#dcfce7' : '#fee2e2',
                        color: lead.status === 'NOVO' ? '#1d4ed8' :
                          lead.status === 'CONTATADO' ? '#4338ca' :
                          lead.status === 'QUALIFICADO' ? '#7c3aed' :
                          lead.status === 'CONVERTIDO' ? '#16a34a' : '#dc2626'
                      }}>
                        {lead.status.charAt(0) + lead.status.slice(1).toLowerCase()}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{lead.score}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <button onClick={() => setEditingLead(lead)} className="text-xs"
                          style={{ color: 'var(--color-brand)', background: 'none', border: 'none', cursor: 'pointer' }}>
                          Editar
                        </button>
                        {lead.status !== 'CONVERTIDO' && (
                          <button onClick={() => handleConvert(lead.id)} className="text-xs"
                            style={{ color: '#16a34a', background: 'none', border: 'none', cursor: 'pointer' }}>
                            Converter
                          </button>
                        )}
                        <button onClick={() => handleDelete(lead.id)} className="text-xs"
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
        <LeadForm
          onClose={() => setFormOpen(false)}
          onSave={handleCreate}
        />
      )}

      {editingLead && (
        <LeadForm
          lead={editingLead}
          onClose={() => setEditingLead(null)}
          onSave={handleUpdate}
        />
      )}
    </div>
  )
}

function LeadForm({ lead, onClose, onSave }: {
  lead?: Lead | null
  onClose: () => void
  onSave: (payload: { first_name: string; last_name: string; email: string }) => void
}) {
  const [first_name, setFirstName] = useState(lead?.first_name ?? '')
  const [last_name, setLastName] = useState(lead?.last_name ?? '')
  const [email, setEmail] = useState(lead?.email ?? '')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave({ first_name, last_name, email })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-full max-w-md" style={{ fontFamily: 'var(--font-body)' }}>
        <h2 className="text-lg font-bold mb-4" style={{ color: 'var(--color-brand)' }}>
          {lead ? 'Editar Lead' : 'Novo Lead'}
        </h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--color-text-muted)' }}>Nome</label>
            <input
              type="text"
              value={first_name}
              onChange={e => setFirstName(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1.5px solid #e2e8f0' }}
            />
          </div>
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--color-text-muted)' }}>Sobrenome</label>
            <input
              type="text"
              value={last_name}
              onChange={e => setLastName(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1.5px solid #e2e8f0' }}
            />
          </div>
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--color-text-muted)' }}>E-mail</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
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