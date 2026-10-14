import React, { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Briefcase, ArrowLeft, Plus, Pencil, Trash2, Search } from 'lucide-react'
import { useCargos } from '../hooks/useCargos'
import CargoForm from '../components/CargoForm'
import type { Cargo, CargoFormData } from '@/types'

import { contemSemAcento } from '@/utils/texto'
import { BotaoExportar, WizardImportacao } from '@/components/malha'

const CargosPage: React.FC = () => {
  const navigate = useNavigate()
  const { cargos, loading, error, createCargo, updateCargo, deleteCargo, refetch } = useCargos()
  const [search, setSearch]         = useState('')
  const [form, setForm]             = useState<{ open: boolean; editing: Cargo | null }>({ open: false, editing: null })
  const [confirmId, setConfirmId]   = useState<number | null>(null)
  const [deleting, setDeleting]     = useState(false)

  const filtered = useMemo(() => {
    const q = search.trim()
    if (!q) return cargos
    return cargos.filter(c =>
      contemSemAcento(c.nome_cargo, q) ||
      contemSemAcento(c.departamento ?? '', q)
    )
  }, [cargos, search])

  const handleSave = async (fd: CargoFormData) => {
    if (form.editing) await updateCargo(form.editing.cargo_id, fd)
    else await createCargo(fd)
    setForm({ open: false, editing: null })
  }

  const handleDelete = async () => {
    if (!confirmId) return
    setDeleting(true)
    try { await deleteCargo(confirmId) }
    finally { setDeleting(false); setConfirmId(null) }
  }

  return (
    <div className="px-6 py-8 max-w-4xl">

      {/* Volta */}
      <button onClick={() => navigate('/app/rh')}
        className="flex items-center gap-2 text-sm mb-5"
        style={{ color: 'var(--color-text-muted)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
        <ArrowLeft size={15} /> Funcionários
      </button>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: '#fef9c3', color: 'var(--color-brand)' }}>
            <Briefcase size={20} />
          </div>
          <h1 className="text-2xl font-bold"
            style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            Cargos
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <BotaoExportar tam="md" recurso="rh.cargo" recorte={{ search: search.trim() }} />
          <WizardImportacao tam="md" recurso="rh.cargo" onConcluida={() => refetch()} />
          <button onClick={() => setForm({ open: true, editing: null })}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}>
            <Plus size={16} /> Novo Cargo
          </button>
        </div>
      </div>

      {/* Busca */}
      <div className="relative max-w-xs mb-5">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2"
          style={{ color: 'var(--color-text-muted)' }} />
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Buscar por nome, departamento…"
          style={{
            paddingLeft: '34px', padding: '8px 12px 8px 34px',
            border: '1.5px solid #e2e8f0', borderRadius: '8px',
            fontSize: '0.875rem', fontFamily: 'var(--font-body)',
            color: 'var(--color-text)', background: '#FFFFFF', width: '100%', outline: 'none',
          }} />
      </div>

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
                {['Nome do Cargo', 'Departamento', 'Descrição', ''].map(h => (
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
                  <td colSpan={4} style={{ padding: '32px', textAlign: 'center',
                    color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', fontSize: '0.875rem' }}>
                    {search ? 'Nenhum cargo encontrado.' : 'Nenhum cargo cadastrado.'}
                  </td>
                </tr>
              ) : (
                filtered.map(cargo => (
                  <tr key={cargo.cargo_id}
                    style={{ borderBottom: '1px solid #f1f5f9' }}
                    onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = '#f8fafc'}
                    onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = 'transparent'}>
                    <td style={{ padding: '12px 16px' }}>
                      <p className="text-sm font-semibold"
                        style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                        {cargo.nome_cargo}
                      </p>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <span className="text-sm" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                        {cargo.departamento ?? '—'}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', maxWidth: '320px' }}>
                      <p className="text-sm" style={{
                        color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {cargo.descricao || '—'}
                      </p>
                    </td>
                    <td style={{ padding: '12px 16px', width: '80px' }}>
                      <div className="flex items-center gap-1 justify-end">
                        <button onClick={() => setForm({ open: true, editing: cargo })}
                          className="p-1.5 rounded"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}
                          title="Editar">
                          <Pencil size={14} />
                        </button>
                        <button onClick={() => setConfirmId(cargo.cargo_id)}
                          className="p-1.5 rounded"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626' }}
                          title="Excluir">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>

          {filtered.length > 0 && (
            <div style={{ padding: '10px 16px', borderTop: '1px solid #f1f5f9', background: '#f8fafc' }}>
              <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
                {filtered.length} cargo{filtered.length !== 1 ? 's' : ''}
                {search && ` (de ${cargos.length} total)`}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Confirm delete */}
      {confirmId !== null && (
        <>
          <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={() => setConfirmId(null)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-2xl p-6 w-72"
            style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
            <h3 className="text-base font-bold mb-2"
              style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Excluir cargo?
            </h3>
            <p className="text-sm mb-5" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              Funcionários vinculados a este cargo perderão o vínculo.
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmId(null)} style={cancelBtn}>Cancelar</button>
              <button onClick={handleDelete} disabled={deleting}
                style={{ ...deleteBtn, opacity: deleting ? 0.7 : 1 }}>
                {deleting ? 'Excluindo…' : 'Excluir'}
              </button>
            </div>
          </div>
        </>
      )}

      {/* Form */}
      <CargoForm
        open={form.open}
        onClose={() => setForm({ open: false, editing: null })}
        onSave={handleSave}
        initial={form.editing}
      />
    </div>
  )
}

const cancelBtn: React.CSSProperties = {
  padding: '7px 14px', borderRadius: '7px', border: '1.5px solid #e2e8f0',
  background: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)',
  fontSize: '0.8125rem', color: 'var(--color-text-muted)',
}
const deleteBtn: React.CSSProperties = {
  padding: '7px 16px', borderRadius: '7px', border: 'none',
  background: '#dc2626', color: '#FFFFFF',
  cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: '0.8125rem', fontWeight: 600,
}

export default CargosPage
