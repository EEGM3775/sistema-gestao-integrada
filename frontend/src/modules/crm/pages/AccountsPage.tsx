import { useTextoDaLixeira } from '@/hooks/useRetencaoDoLixo'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Plus, Search, RefreshCw, Building2 } from 'lucide-react'
import { BotaoExportar, WizardImportacao } from '@/components/malha'
import { useAccounts, useCreateAccount, useUpdateAccount, useDeleteAccount } from '../hooks/useAccounts'
import type { Account, AccountPayload } from '../types'

/**
 * Lista de Contas - /app/crm/accounts
 */
export default function AccountsPage() {
  const textoLixeira = useTextoDaLixeira()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingAccount, setEditingAccount] = useState<Account | null>(null)

  const { data, isLoading, refetch } = useAccounts({ search })
  const createMutation = useCreateAccount()
  const updateMutation = useUpdateAccount()
  const deleteMutation = useDeleteAccount()

  const handleCreate = async (payload: AccountPayload) => {
    await createMutation.mutateAsync(payload)
    setFormOpen(false)
    refetch()
  }

  const handleUpdate = async (payload: AccountPayload) => {
    if (editingAccount) {
      await updateMutation.mutateAsync({ id: editingAccount.id, payload })
      setEditingAccount(null)
      refetch()
    }
  }

  const handleDelete = async (id: string) => {
    if (confirm(textoLixeira('esta conta'))) {
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
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#dbeafe', color: '#2563eb' }}>
            <Building2 size={22} />
          </div>
          <div>
            <h1 className="text-xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-text)' }}>
              Contas
            </h1>
            <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {isLoading ? 'Carregando…' : `${data?.count ?? 0} conta${(data?.count ?? 0) !== 1 ? 's' : ''}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
        {/* Planilha: sai a busca da tela (R7) e entra só conta nova. */}
        <BotaoExportar tam="md" recurso="crm.conta" recorte={{ search }} />
        <WizardImportacao tam="md" recurso="crm.conta" onConcluida={() => refetch()} />
        <button
          onClick={() => setFormOpen(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
          style={{ background: 'var(--color-brand)', color: '#FFFFFF', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
        >
          <Plus size={16} /> Nova Conta
        </button>
        </div>
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
            <Building2 size={40} style={{ color: '#cbd5e1' }} />
            <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {search ? 'Nenhum resultado para os filtros aplicados.' : 'Nenhuma conta cadastrada ainda.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full" style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-body)' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                  {['Nome', 'E-mail', 'Telefone', 'Website', 'Indústria', 'Ações'].map(h => (
                    <th key={h} className="text-left text-xs font-semibold uppercase tracking-wide px-5 py-3"
                      style={{ color: 'var(--color-text-muted)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data?.results.map((account: Account, i: number) => (
                  <tr key={account.id} className="transition-colors duration-100"
                    style={{ borderBottom: i < (data?.results.length ?? 0) - 1 ? '1px solid #f1f5f9' : 'none' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                    <td className="px-5 py-3.5">
                      <span className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>
                        {account.name}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{account.email || '—'}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{account.phone || '—'}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                        {account.website ? <a href={account.website} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-brand)' }}>{account.website}</a> : '—'}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{account.industry || '—'}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <button onClick={() => setEditingAccount(account)} className="text-xs"
                          style={{ color: 'var(--color-brand)', background: 'none', border: 'none', cursor: 'pointer' }}>
                          Editar
                        </button>
                        <button onClick={() => handleDelete(account.id)} className="text-xs"
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
        <AccountForm
          onClose={() => setFormOpen(false)}
          onSave={handleCreate}
        />
      )}

      {editingAccount && (
        <AccountForm
          account={editingAccount}
          onClose={() => setEditingAccount(null)}
          onSave={handleUpdate}
        />
      )}
    </div>
  )
}

function AccountForm({ account, onClose, onSave }: {
  account?: Account | null
  onClose: () => void
  onSave: (payload: AccountPayload) => void
}) {
  const [name, setName] = useState(account?.name ?? '')
  const [email, setEmail] = useState(account?.email ?? '')
  const [phone, setPhone] = useState(account?.phone ?? '')
  const [website, setWebsite] = useState(account?.website ?? '')
  const [industry, setIndustry] = useState(account?.industry ?? '')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave({ name, email, phone, website, industry })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-full max-w-md" style={{ fontFamily: 'var(--font-body)' }}>
        <h2 className="text-lg font-bold mb-4" style={{ color: 'var(--color-brand)' }}>
          {account ? 'Editar Conta' : 'Nova Conta'}
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
            <label className="text-xs block mb-1" style={{ color: 'var(--color-text-muted)' }}>E-mail</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
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
            <label className="text-xs block mb-1" style={{ color: 'var(--color-text-muted)' }}>Website</label>
            <input
              type="url"
              value={website}
              onChange={e => setWebsite(e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1.5px solid #e2e8f0' }}
            />
          </div>
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--color-text-muted)' }}>Indústria</label>
            <input
              type="text"
              value={industry}
              onChange={e => setIndustry(e.target.value)}
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