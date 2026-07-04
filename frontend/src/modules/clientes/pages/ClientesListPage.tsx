import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Search, Users, RefreshCw } from 'lucide-react'
import apiClient from '@/api/apiClient'
import { useClientes } from '../hooks/useClientes'
import { createCliente } from '../hooks/useCliente'
import { getDivergenciasAsaas, type DivergenciaAsaas } from '../services/clientesService'
import ClienteForm from '../components/ClienteForm'
import type { ClienteFormData, Empreendimento } from '@/types'
import { formatCPFCNPJ } from '@/utils/masks'

const ClientesListPage: React.FC = () => {
  const navigate   = useNavigate()
  const [search, setSearch]               = useState('')
  const [empFiltro, setEmpFiltro]         = useState<number | ''>('')
  const [empreendimentos, setEmp]         = useState<Empreendimento[]>([])
  const [formOpen, setFormOpen]           = useState(false)
  const [divergencias, setDivergencias]   = useState<DivergenciaAsaas[]>([])
  const [divergLoading, setDivergLoading] = useState(false)

  const { data, loading, error, refetch } = useClientes({ search, empreendimento: empFiltro })

  useEffect(() => {
    apiClient.get('/empreendimentos/')
      .then(r => setEmp(r.data.results ?? r.data))
      .catch(() => {})
  }, [])

  // Ao abrir "Novo Cliente", audita as divergências banco × Asaas para o
  // operador ver, antes de cadastrar, o que impediria/desviaria uma cobrança.
  const openCreate = () => {
    setFormOpen(true)
    setDivergLoading(true)
    setDivergencias([])
    getDivergenciasAsaas()
      .then(r => setDivergencias(r.data.divergencias))
      .catch(() => setDivergencias([]))
      .finally(() => setDivergLoading(false))
  }

  const handleCreate = async (formData: ClienteFormData) => {
    await createCliente(formData)
    refetch()
  }

  return (
    <div className="px-6 py-8">

      {/* Cabeçalho */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: '#dcfce7', color: 'var(--color-brand)' }}>
            <Users size={22} />
          </div>
          <div>
            <h1 className="text-xl font-bold"
              style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Clientes
            </h1>
            <p className="text-xs" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {loading ? 'Carregando…' : `${data.length} registro${data.length !== 1 ? 's' : ''}`}
            </p>
          </div>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold"
          style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
          onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand-dark)')}
          onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand)')}>
          <Plus size={16} /> Novo Cliente
        </button>
      </div>

      {/* Filtros */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--color-text-muted)' }} />
          <input
            type="text"
            placeholder="Buscar por nome, CPF/CNPJ ou e-mail…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm outline-none"
            style={{ border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)', color: 'var(--color-text)', background: '#FFFFFF' }}
            onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
            onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
          />
        </div>
        <select
          value={empFiltro}
          onChange={e => setEmpFiltro(e.target.value ? Number(e.target.value) : '')}
          className="px-4 py-2.5 rounded-lg text-sm outline-none"
          style={{ border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)', color: 'var(--color-text)', background: '#FFFFFF', cursor: 'pointer', minWidth: '200px' }}>
          <option value="">Todos os empreendimentos</option>
          {empreendimentos.map(emp => (
            <option key={emp.empreendimento_id} value={emp.empreendimento_id}>{emp.empreendimento}</option>
          ))}
        </select>
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
            <Users size={40} style={{ color: '#cbd5e1' }} />
            <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {search || empFiltro
                ? 'Nenhum resultado para os filtros aplicados.'
                : 'Nenhum cliente cadastrado ainda.'}
            </p>
            {!search && !empFiltro && (
              <button onClick={openCreate} className="text-sm font-semibold"
                style={{ color: 'var(--color-brand)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
                + Cadastrar primeiro cliente
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full" style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-body)' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                  {['Nome', 'CPF / CNPJ', 'E-mail', 'Telefone', 'Cidade / UF'].map(h => (
                    <th key={h} className="text-left text-xs font-semibold uppercase tracking-wide px-5 py-3"
                      style={{ color: 'var(--color-text-muted)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((c, i) => (
                  <tr
                    key={c.cliente_id}
                    onClick={() => navigate(`/app/clientes/${c.cliente_id}`)}
                    className="transition-colors duration-100 cursor-pointer"
                    style={{ borderBottom: i < data.length - 1 ? '1px solid #f1f5f9' : 'none' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                    <td className="px-5 py-3.5">
                      <span className="text-sm font-semibold" style={{ color: 'var(--color-brand)' }}>
                        {c.nome_completo}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                        {formatCPFCNPJ(c.cpf_cnpj)}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text)' }}>{c.email}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                        {c.telefone || '—'}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                        {c.cidade && c.estado ? `${c.cidade} / ${c.estado}` : c.cidade || c.estado || '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ClienteForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSave={handleCreate}
        divergencias={divergencias}
        divergLoading={divergLoading}
      />
    </div>
  )
}

export default ClientesListPage
