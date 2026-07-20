import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Plus, Search, RefreshCw, User } from 'lucide-react'
import { useContacts, useCreateContact, useUpdateContact, useDeleteContact } from '../hooks/useContacts'
import type { Contact, ContactPayload } from '../types'

/**
 * Lista de Contatos - /app/crm/contacts
 */
export default function ContactsPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingContact, setEditingContact] = useState<Contact | null>(null)

  const { data, isLoading, refetch } = useContacts({ search })
  const createMutation = useCreateContact()
  const updateMutation = useUpdateContact()
  const deleteMutation = useDeleteContact()

  const handleCreate = async (payload: ContactPayload) => {
    await createMutation.mutateAsync(payload)
    setFormOpen(false)
    refetch()
  }

  const handleUpdate = async (payload: ContactPayload) => {
    if (editingContact) {
      await updateMutation.mutateAsync({ id: editingContact.id, payload })
      setEditingContact(null)
      refetch()
    }
  }

  const handleDelete = async (id: string) => {
    if (confirm('Tem certeza que deseja excluir este contato?')) {
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
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#ede9fe', color: '#7c3aed' }}>
            <User size={22} />
          </div>
          <div>
            <h1 className="text-xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-text)' }}>
              Contatos
            </h1>
            <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {isLoading ? 'Carregando…' : `${data?.count ?? 0} contato${(data?.count ?? 0) !== 1 ? 's' : ''}`}
            </p>
          </div>
        </div>
        <button
          onClick={() => setFormOpen(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
          style={{ background: 'var(--color-brand)', color: '#FFFFFF', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
        >
          <Plus size={16} /> Novo Contato
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
            <User size={40} style={{ color: '#cbd5e1' }} />
            <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {search ? 'Nenhum resultado para os filtros aplicados.' : 'Nenhum contato cadastrado ainda.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full" style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-body)' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                  {['Nome', 'E-mail', 'Telefone', 'Cargo', 'Ações'].map(h => (
                    <th key={h} className="text-left text-xs font-semibold uppercase tracking-wide px-5 py-3"
                      style={{ color: 'var(--color-text-muted)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data?.results.map((contact: Contact, i: number) => (
                  <tr key={contact.id} className="transition-colors duration-100"
                    style={{ borderBottom: i < (data?.results.length ?? 0) - 1 ? '1px solid #f1f5f9' : 'none' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                    <td className="px-5 py-3.5">
                      <span className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>
                        {contact.first_name} {contact.last_name}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{contact.email || '—'}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{contact.phone || '—'}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{contact.title || '—'}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <button onClick={() => setEditingContact(contact)} className="text-xs"
                          style={{ color: 'var(--color-brand)', background: 'none', border: 'none', cursor: 'pointer' }}>
                          Editar
                        </button>
                        <button onClick={() => handleDelete(contact.id)} className="text-xs"
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
        <ContactForm
          onClose={() => setFormOpen(false)}
          onSave={handleCreate}
        />
      )}

      {editingContact && (
        <ContactForm
          contact={editingContact}
          onClose={() => setEditingContact(null)}
          onSave={handleUpdate}
        />
      )}
    </div>
  )
}

function ContactForm({ contact, onClose, onSave }: {
  contact?: Contact | null
  onClose: () => void
  onSave: (payload: ContactPayload) => void
}) {
  const [first_name, setFirstName] = useState(contact?.first_name ?? '')
  const [last_name, setLastName] = useState(contact?.last_name ?? '')
  const [email, setEmail] = useState(contact?.email ?? '')
  const [phone, setPhone] = useState(contact?.phone ?? '')
  const [title, setTitle] = useState(contact?.title ?? '')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave({ first_name, last_name, email, phone, title })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-full max-w-md" style={{ fontFamily: 'var(--font-body)' }}>
        <h2 className="text-lg font-bold mb-4" style={{ color: 'var(--color-brand)' }}>
          {contact ? 'Editar Contato' : 'Novo Contato'}
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
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--color-text-muted)' }}>Telefone</label>
            <input
              type="tel"
              value={phone}
              onChange={e => setPhone(e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1.5px solid #e2e8f0' }}
            />
          </div>
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--color-text-muted)' }}>Cargo</label>
            <input
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
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