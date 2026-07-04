import React, { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Search, HardHat, RefreshCw } from 'lucide-react'
import { useObras } from '../hooks/useObras'
import { createObra } from '../hooks/useObra'
import { useEmpreendimentos } from '@/modules/empreendimentos/hooks/useEmpreendimentos'
import ObraStatusBadge from '../components/ObraStatusBadge'
import ObraForm from '../components/ObraForm'
import type { StatusObra, ObraFormData } from '@/types'

const STATUS_FILTER_OPTIONS: { value: StatusObra | ''; label: string }[] = [
  { value: '',             label: 'Todos os status'  },
  { value: 'planejamento', label: 'Planejamento'      },
  { value: 'em_execucao',  label: 'Em Execução'       },
  { value: 'concluida',    label: 'Concluída'         },
  { value: 'cancelada',    label: 'Cancelada'         },
]

function formatCurrency(value: string | null) {
  if (!value) return '—'
  return parseFloat(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function formatDate(value: string | null) {
  if (!value) return '—'
  const [y, m, d] = value.split('-')
  return `${d}/${m}/${y}`
}

const ObrasListPage: React.FC = () => {
  const navigate = useNavigate()
  const [search, setSearch]               = useState('')
  const [status, setStatus]               = useState<StatusObra | ''>('')
  const [empreendimentoId, setEmpId]      = useState<number | null>(null)
  const [formOpen, setFormOpen]           = useState(false)

  const { data, loading, error, refetch } = useObras({ search, status, empreendimentoId })
  const { data: empreendimentos }         = useEmpreendimentos()

  const empreendimentoMap = useMemo(
    () => Object.fromEntries(empreendimentos.map(e => [e.empreendimento_id, e.empreendimento])),
    [empreendimentos]
  )

  const handleCreate = async (formData: ObraFormData) => {
    await createObra(formData)
    refetch()
  }

  return (
    <div className="px-6 py-8">

      {/* Cabeçalho */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
               style={{ background: '#fef3c7', color: 'var(--color-brand)' }}>
            <HardHat size={22} />
          </div>
          <div>
            <h1 className="text-xl font-bold"
                style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Obras
            </h1>
            <p className="text-xs"
               style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {loading ? 'Carregando…' : `${data.length} registro${data.length !== 1 ? 's' : ''}`}
            </p>
          </div>
        </div>
        <button
          onClick={() => setFormOpen(true)}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold"
          style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
          onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand-dark)')}
          onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand)')}
        >
          <Plus size={16} /> Nova Obra
        </button>
      </div>

      {/* Filtros */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--color-text-muted)' }} />
          <input
            type="text"
            placeholder="Buscar por nome ou endereço…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm outline-none"
            style={{ border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)', color: 'var(--color-text)', background: '#FFFFFF' }}
            onFocus={e => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
            onBlur={e => (e.currentTarget.style.borderColor = '#e2e8f0')}
          />
        </div>
        <select
          value={status}
          onChange={e => setStatus(e.target.value as StatusObra | '')}
          className="px-4 py-2.5 rounded-lg text-sm outline-none"
          style={{ border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)', color: 'var(--color-text)', background: '#FFFFFF', cursor: 'pointer', minWidth: '160px' }}
        >
          {STATUS_FILTER_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select
          value={empreendimentoId ?? ''}
          onChange={e => setEmpId(e.target.value ? parseInt(e.target.value, 10) : null)}
          className="px-4 py-2.5 rounded-lg text-sm outline-none"
          style={{ border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)', color: 'var(--color-text)', background: '#FFFFFF', cursor: 'pointer', minWidth: '200px' }}
        >
          <option value="">Todos os empreendimentos</option>
          {empreendimentos.map(e => (
            <option key={e.empreendimento_id} value={e.empreendimento_id}>{e.empreendimento}</option>
          ))}
        </select>
        <button
          onClick={refetch}
          className="p-2.5 rounded-lg border"
          title="Atualizar"
          style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF', cursor: 'pointer', color: 'var(--color-text-muted)' }}
          onMouseEnter={e => ((e.currentTarget as HTMLElement).style.borderColor = 'var(--color-brand)')}
          onMouseLeave={e => ((e.currentTarget as HTMLElement).style.borderColor = '#e2e8f0')}
        >
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
            <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
                 style={{ borderColor: 'var(--color-brand)', borderTopColor: 'transparent' }} />
          </div>
        ) : data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <HardHat size={40} style={{ color: '#cbd5e1' }} />
            <p className="text-sm" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {search || status || empreendimentoId
                ? 'Nenhum resultado para os filtros aplicados.'
                : 'Nenhuma obra cadastrada ainda.'}
            </p>
            {!search && !status && !empreendimentoId && (
              <button
                onClick={() => setFormOpen(true)}
                className="text-sm font-semibold"
                style={{ color: 'var(--color-brand)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
              >
                + Criar primeira obra
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full" style={{ borderCollapse: 'collapse', fontFamily: 'var(--font-body)' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
                  {['Nome da Obra', 'Empreendimento', 'Status', 'Orçamento', 'Início', 'Fim'].map(h => (
                    <th key={h} className="text-left text-xs font-semibold uppercase tracking-wide px-5 py-3"
                        style={{ color: 'var(--color-text-muted)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((obra, i) => (
                  <tr
                    key={obra.obra_id}
                    onClick={() => navigate(`/app/obras/${obra.obra_id}`)}
                    className="transition-colors duration-100 cursor-pointer"
                    style={{ borderBottom: i < data.length - 1 ? '1px solid #f1f5f9' : 'none' }}
                    onMouseEnter={el => (el.currentTarget.style.background = '#f8fafc')}
                    onMouseLeave={el => (el.currentTarget.style.background = 'transparent')}
                  >
                    <td className="px-5 py-3.5">
                      <span className="text-sm font-semibold" style={{ color: 'var(--color-brand)' }}>
                        {obra.nome_obra}
                      </span>
                      {obra.endereco && (
                        <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
                          {obra.endereco}
                        </p>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text)' }}>
                        {obra.empreendimento ? (empreendimentoMap[obra.empreendimento] ?? '—') : '—'}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <ObraStatusBadge status={obra.status_obra} />
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text)' }}>
                        {formatCurrency(obra.orcamento_previsto)}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                        {formatDate(obra.data_inicio_prevista)}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                        {formatDate(obra.data_fim_prevista)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ObraForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSave={handleCreate}
      />
    </div>
  )
}

export default ObrasListPage
