import React, { useState, useMemo } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { UserCog, Plus, Search, ChevronRight, Briefcase } from 'lucide-react'
import { useFuncionarios, createFuncionario } from '../hooks/useFuncionarios'
import { useCargos } from '../hooks/useCargos'
import FuncionarioForm from '../components/FuncionarioForm'
import type { FuncionarioFormData, StatusContratoFuncionario } from '@/types'
import { formatCPF } from '@/utils/masks'

import { contemSemAcento } from '@/utils/texto'

// ─── helpers ──────────────────────────────────────────────────────────────────

function formatDate(v: string | null) {
  if (!v) return '—'
  const [y, m, d] = v.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}

function formatCurrency(v: string | null) {
  if (!v) return '—'
  return parseFloat(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

const STATUS_LABEL: Record<StatusContratoFuncionario, string> = {
  ativo: 'Ativo', inativo: 'Inativo', ferias: 'Férias', licenca: 'Licença', desligado: 'Desligado',
}

const STATUS_COLORS: Record<StatusContratoFuncionario, { bg: string; color: string }> = {
  ativo:     { bg: '#dcfce7', color: '#166534' },
  ferias:    { bg: '#dbeafe', color: '#1d4ed8' },
  licenca:   { bg: '#fef9c3', color: '#854d0e' },
  inativo:   { bg: '#f1f5f9', color: '#475569' },
  desligado: { bg: '#fee2e2', color: '#991b1b' },
}

// ─── página ───────────────────────────────────────────────────────────────────

const FuncionariosListPage: React.FC = () => {
  const navigate = useNavigate()
  const { funcionarios, loading, error, refetch } = useFuncionarios()
  const { cargos } = useCargos()
  const [search, setSearch]           = useState('')
  const [filterStatus, setFilterStatus] = useState<string>('')
  const [formOpen, setFormOpen]       = useState(false)
  const [creating, setCreating]       = useState(false)

  const cargoMap = useMemo(() =>
    Object.fromEntries(cargos.map(c => [c.cargo_id, c])),
    [cargos]
  )

  const filtered = useMemo(() => {
    const q = search.trim()
    return funcionarios.filter(f => {
      const matchStatus = !filterStatus || f.status_contrato === filterStatus
      const matchSearch = !q || contemSemAcento(f.nome_completo, q) || f.cpf.includes(q)
      return matchStatus && matchSearch
    })
  }, [funcionarios, search, filterStatus])

  const handleCreate = async (fd: FuncionarioFormData) => {
    setCreating(true)
    try {
      await createFuncionario(fd)
      await refetch()
      setFormOpen(false)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="px-6 py-8 max-w-6xl">

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: '#fef9c3', color: 'var(--color-brand)' }}>
            <UserCog size={22} />
          </div>
          <h1 className="text-2xl font-bold"
            style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            Funcionários
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/app/rh/cargos"
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold"
            style={{ border: '1.5px solid #e2e8f0', background: '#FFFFFF',
              color: 'var(--color-text)', textDecoration: 'none', fontFamily: 'var(--font-body)' }}>
            <Briefcase size={15} /> Cargos
          </Link>
          <button
            onClick={() => setFormOpen(true)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none',
              cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
            <Plus size={16} /> Novo Funcionário
          </button>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex gap-3 mb-5">
        <div className="relative flex-1 max-w-xs">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--color-text-muted)' }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por nome, CPF…"
            style={{
              paddingLeft: '34px', padding: '8px 12px 8px 34px',
              border: '1.5px solid #e2e8f0', borderRadius: '8px',
              fontSize: '0.875rem', fontFamily: 'var(--font-body)',
              color: 'var(--color-text)', background: '#FFFFFF', width: '100%', outline: 'none',
            }}
          />
        </div>
        <select
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}
          style={{
            padding: '8px 12px', border: '1.5px solid #e2e8f0', borderRadius: '8px',
            fontSize: '0.875rem', fontFamily: 'var(--font-body)', color: 'var(--color-text)',
            background: '#FFFFFF', outline: 'none', cursor: 'pointer',
          }}
        >
          <option value="">Todos os status</option>
          <option value="ativo">Ativo</option>
          <option value="ferias">Férias</option>
          <option value="licenca">Licença</option>
          <option value="inativo">Inativo</option>
          <option value="desligado">Desligado</option>
        </select>
      </div>

      {/* Estado de carregamento */}
      {loading && (
        <div className="flex items-center justify-center py-24">
          <div className="w-8 h-8 rounded-full border-2 animate-spin"
            style={{ borderColor: 'var(--color-brand)', borderTopColor: 'transparent' }} />
        </div>
      )}

      {error && (
        <p className="text-sm py-8" style={{ color: '#c53030', fontFamily: 'var(--font-body)' }}>{error}</p>
      )}

      {!loading && !error && (
        <div className="rounded-xl overflow-hidden" style={{ border: '1px solid #e2e8f0', background: '#FFFFFF' }}>
          <table className="w-full" style={{ borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                {['Nome', 'CPF', 'Cargo', 'Status', 'Admissão', 'Salário', ''].map(h => (
                  <th key={h} style={{
                    padding: '10px 16px', textAlign: 'left', fontSize: '0.7rem',
                    fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em',
                    color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)',
                  }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ padding: '32px', textAlign: 'center',
                    color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', fontSize: '0.875rem' }}>
                    {search || filterStatus ? 'Nenhum funcionário encontrado para os filtros aplicados.' : 'Nenhum funcionário cadastrado.'}
                  </td>
                </tr>
              ) : (
                filtered.map(f => {
                  const cargo = f.cargo ? cargoMap[f.cargo] : null
                  const sc = STATUS_COLORS[f.status_contrato]
                  return (
                    <tr
                      key={f.funcionario_id}
                      onClick={() => navigate(`/app/rh/${f.funcionario_id}`)}
                      className="cursor-pointer transition-colors duration-100"
                      style={{ borderBottom: '1px solid #f1f5f9' }}
                      onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = '#f8fafc'}
                      onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = 'transparent'}
                    >
                      <td style={{ padding: '12px 16px' }}>
                        <div>
                          <p className="text-sm font-semibold" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                            {f.nome_completo}
                          </p>
                          {f.email_pessoal && (
                            <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                              {f.email_pessoal}
                            </p>
                          )}
                        </div>
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <span className="text-sm" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                          {formatCPF(f.cpf)}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        {cargo ? (
                          <div>
                            <p className="text-sm" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                              {cargo.nome_cargo}
                            </p>
                            {cargo.departamento && (
                              <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                                {cargo.departamento}
                              </p>
                            )}
                          </div>
                        ) : (
                          <span className="text-sm" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>—</span>
                        )}
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <span className="text-xs font-semibold px-2 py-1 rounded-full"
                          style={{ background: sc.bg, color: sc.color, fontFamily: 'var(--font-body)' }}>
                          {STATUS_LABEL[f.status_contrato]}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <span className="text-sm" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                          {formatDate(f.data_admissao)}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <span className="text-sm" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                          {formatCurrency(f.salario_base)}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px', width: '40px' }}>
                        <ChevronRight size={16} style={{ color: 'var(--color-text-muted)' }} />
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>

          {/* Footer count */}
          {filtered.length > 0 && (
            <div style={{ padding: '10px 16px', borderTop: '1px solid #f1f5f9', background: '#f8fafc' }}>
              <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                {filtered.length} funcionário{filtered.length !== 1 ? 's' : ''}
                {(search || filterStatus) && ` (de ${funcionarios.length} total)`}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Form */}
      <FuncionarioForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSave={handleCreate}
        initial={null}
      />
      {creating && null}
    </div>
  )
}

export default FuncionariosListPage
