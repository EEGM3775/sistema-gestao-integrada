import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Search, Truck, RefreshCw } from 'lucide-react'
import { useFornecedores } from '../hooks/useFornecedores'
import { createFornecedor } from '../hooks/useFornecedor'
import FornecedorForm from '../components/FornecedorForm'
import type { FornecedorFormData } from '@/types'
import { formatCNPJ } from '@/utils/masks'
import { BotaoExportar, WizardImportacao } from '@/components/malha'

function formatPhone(v: string) {
  const d = v.replace(/\D/g, '')
  if (d.length === 11) return d.replace(/(\d{2})(\d{5})(\d{4})/, '($1) $2-$3')
  if (d.length === 10) return d.replace(/(\d{2})(\d{4})(\d{4})/, '($1) $2-$3')
  return v
}

const FornecedoresListPage: React.FC = () => {
  const navigate = useNavigate()
  const [search, setSearch]   = useState('')
  const [formOpen, setFormOpen] = useState(false)

  const { data, loading, error, refetch } = useFornecedores({ search })

  const handleCreate = async (formData: FornecedorFormData) => {
    await createFornecedor(formData)
    refetch()
  }

  return (
    <div className="px-6 py-8">

      {/* Cabeçalho */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: '#fef3c7', color: 'var(--color-brand)' }}>
            <Truck size={22} />
          </div>
          <div>
            <h1 className="text-xl font-bold"
              style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Fornecedores
            </h1>
            <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {loading ? 'Carregando…' : `${data.length} registro${data.length !== 1 ? 's' : ''}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
        {/* Planilha: sai a busca da tela (R7) e entra só fornecedor novo. */}
        <BotaoExportar tam="md" recurso="cadastro.fornecedor" recorte={{ search }} />
        <WizardImportacao tam="md" recurso="cadastro.fornecedor" onConcluida={() => refetch()} />
        <button
          onClick={() => setFormOpen(true)}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold"
          style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
          onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand-dark)')}
          onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand)')}>
          <Plus size={16} /> Novo Fornecedor
        </button>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex gap-3 mb-6">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--color-text-muted)' }} />
          <input
            type="text"
            placeholder="Buscar por razão social, CNPJ, e-mail ou contato…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm outline-none"
            style={{ border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)', color: 'var(--color-text)', background: '#FFFFFF' }}
            onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
            onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
          />
        </div>
        <button onClick={refetch}
          className="p-2.5 rounded-lg border transition-colors duration-150" title="Atualizar"
          style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF', cursor: 'pointer', color: 'var(--color-text-muted)' }}
          onMouseEnter={e => ((e.currentTarget as HTMLElement).style.borderColor = 'var(--color-brand)')}
          onMouseLeave={e => ((e.currentTarget as HTMLElement).style.borderColor = '#e2e8f0')}>
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Erro */}
      {error && (
        <div className="text-sm px-4 py-3 rounded-lg mb-4"
          style={{ background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030', fontFamily: 'var(--font-body)' }}>
          {error}
        </div>
      )}

      {/* Tabela */}
      <div className="rounded-xl overflow-hidden"
        style={{ background: '#FFFFFF', boxShadow: 'var(--shadow-sm)', border: '1px solid #e2e8f0' }}>
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-8 h-8 rounded-full border-2 animate-spin"
              style={{ borderColor: 'var(--color-brand)', borderTopColor: 'transparent' }} />
          </div>
        ) : data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <Truck size={40} style={{ color: '#cbd5e1' }} />
            <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {search ? 'Nenhum resultado para os filtros aplicados.' : 'Nenhum fornecedor cadastrado ainda.'}
            </p>
            {!search && (
              <button onClick={() => setFormOpen(true)} className="text-sm font-semibold"
                style={{ color: 'var(--color-brand)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
                + Cadastrar primeiro fornecedor
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full" style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-body)' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                  {['Razão Social', 'CNPJ', 'E-mail', 'Telefone', 'Contato'].map(h => (
                    <th key={h} className="text-left text-xs font-semibold uppercase tracking-wide px-5 py-3"
                      style={{ color: 'var(--color-text-muted)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((f, i) => (
                  <tr
                    key={f.fornecedor_id}
                    onClick={() => navigate(`/app/fornecedores/${f.fornecedor_id}`)}
                    className="transition-colors duration-100 cursor-pointer"
                    style={{ borderBottom: i < data.length - 1 ? '1px solid #f1f5f9' : 'none' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                    <td className="px-5 py-3.5">
                      <span className="text-sm font-semibold" style={{ color: 'var(--color-brand)' }}>
                        {f.razao_social}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                        {f.cnpj ? formatCNPJ(f.cnpj) : '—'}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text)' }}>{f.email}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                        {f.telefone ? formatPhone(f.telefone) : '—'}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                        {f.contato || '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <FornecedorForm open={formOpen} onClose={() => setFormOpen(false)} onSave={handleCreate} />
    </div>
  )
}

export default FornecedoresListPage
