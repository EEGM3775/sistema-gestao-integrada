import React, { useState, useMemo } from 'react'
import { ShieldCheck, Plus, Pencil, Trash2, Search, Star, Copy } from 'lucide-react'
import { usePersonas } from '../hooks/usePersonas'
import PersonaForm from '../components/PersonaForm'
import type { Perfil, PerfilFormData } from '../types'

import { contemSemAcento } from '@/utils/texto'

interface FormState {
  open: boolean
  editing: Perfil | null                 // se != null, salva com PATCH; senão POST (novo/clone)
  initialData: PerfilFormData | null
  heading: string
}
const CLOSED: FormState = { open: false, editing: null, initialData: null, heading: '' }
const toFormData = (p: Perfil): PerfilFormData => ({ nome: p.nome, descricao: p.descricao ?? '', permissoes: [...p.permissoes] })

const PersonasPage: React.FC = () => {
  const { perfis, catalogo, loading, error, createPerfil, updatePerfil, deletePerfil } = usePersonas()
  const [search, setSearch] = useState('')
  const [form, setForm] = useState<FormState>(CLOSED)
  const [confirmId, setConfirmId] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)

  const templates = useMemo(() => new Set(catalogo?.templates ?? []), [catalogo])

  const abrirNovo   = () => setForm({ open: true, editing: null, initialData: null, heading: 'Novo papel de acesso' })
  const abrirEditar = (p: Perfil) => setForm({ open: true, editing: p, initialData: toFormData(p), heading: `Editar papel: ${p.nome}` })
  const abrirClonar = (p: Perfil) => setForm({ open: true, editing: null, heading: `Clonar de: ${p.nome}`,
    initialData: { ...toFormData(p), nome: `${p.nome} (cópia)`, descricao: p.descricao ?? '' } })

  const filtered = useMemo(() => {
    const q = search.trim()
    if (!q) return perfis
    return perfis.filter(p => contemSemAcento(p.nome, q) || contemSemAcento(p.descricao ?? '', q))
  }, [perfis, search])

  const handleSave = async (fd: PerfilFormData) => {
    if (form.editing) await updatePerfil(form.editing.id, fd)
    else await createPerfil(fd)
    setForm(CLOSED)
  }

  const handleDelete = async () => {
    if (confirmId === null) return
    setDeleting(true)
    try { await deletePerfil(confirmId) }
    finally { setDeleting(false); setConfirmId(null) }
  }

  return (
    <div className="px-6 py-8 max-w-4xl">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#e0e7ff', color: 'var(--color-brand)' }}>
            <ShieldCheck size={20} />
          </div>
          <h1 className="text-2xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            Papéis e Permissões
          </h1>
        </div>
        <button onClick={abrirNovo} disabled={!catalogo}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold"
          style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none', cursor: catalogo ? 'pointer' : 'not-allowed', opacity: catalogo ? 1 : 0.6, fontFamily: 'var(--font-body)' }}>
          <Plus size={16} /> Novo papel
        </button>
      </div>
      <p className="text-sm mb-6" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
        Personas de acesso do seu tenant. Papéis de fábrica <Star size={11} className="inline" style={{ color: '#eab308' }} /> podem ser clonados e ajustados; você também cria os seus.
      </p>

      <div className="relative max-w-xs mb-5">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-muted)' }} />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar papel…"
          style={{ padding: '8px 12px 8px 34px', border: '1.5px solid #e2e8f0', borderRadius: '8px', fontSize: '0.875rem', fontFamily: 'var(--font-body)', color: 'var(--color-text)', background: '#FFFFFF', width: '100%', outline: 'none' }} />
      </div>

      {loading && (
        <div className="flex items-center justify-center py-24">
          <div className="w-8 h-8 rounded-full border-2 animate-spin" style={{ borderColor: 'var(--color-brand)', borderTopColor: 'transparent' }} />
        </div>
      )}
      {error && <p className="text-sm py-8" style={{ color: '#c53030', fontFamily: 'var(--font-body)' }}>{error}</p>}

      {!loading && !error && (
        <div className="rounded-xl overflow-hidden" style={{ border: '1px solid #e2e8f0', background: '#FFFFFF' }}>
          <table className="w-full" style={{ borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                {['Papel', 'Descrição', 'Permissões', ''].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={4} style={{ padding: '32px', textAlign: 'center', color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', fontSize: '0.875rem' }}>
                  {search ? 'Nenhum papel encontrado.' : 'Nenhum papel cadastrado.'}
                </td></tr>
              ) : filtered.map(p => (
                <tr key={p.id} style={{ borderBottom: '1px solid #f1f5f9' }}
                  onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = '#f8fafc')}
                  onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = 'transparent')}>
                  <td style={{ padding: '12px 16px' }}>
                    <span className="text-sm font-semibold flex items-center gap-1.5" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                      {templates.has(p.nome) && <Star size={12} style={{ color: '#eab308' }} />}
                      {p.nome}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', maxWidth: '320px' }}>
                    <p className="text-sm" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.descricao || '—'}
                    </p>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span className="text-sm" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>{p.permissoes.length}</span>
                  </td>
                  <td style={{ padding: '12px 16px', width: '80px' }}>
                    <div className="flex items-center gap-1 justify-end">
                      <button onClick={() => abrirClonar(p)} className="p-1.5 rounded" title="Clonar"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                        <Copy size={14} />
                      </button>
                      <button onClick={() => abrirEditar(p)} className="p-1.5 rounded" title="Editar"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => setConfirmId(p.id)} className="p-1.5 rounded" title="Excluir"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626' }}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {confirmId !== null && (
        <>
          <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={() => setConfirmId(null)} />
          <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-2xl p-6 w-80"
            style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
            <h3 className="text-base font-bold mb-2" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>Excluir papel?</h3>
            <p className="text-sm mb-5" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              Usuários com este papel perdem as permissões que só ele concedia.
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmId(null)} style={cancelBtn}>Cancelar</button>
              <button onClick={handleDelete} disabled={deleting} style={{ ...deleteBtn, opacity: deleting ? 0.7 : 1 }}>
                {deleting ? 'Excluindo…' : 'Excluir'}
              </button>
            </div>
          </div>
        </>
      )}

      {catalogo && (
        <PersonaForm open={form.open} onClose={() => setForm(CLOSED)}
          onSave={handleSave} initialData={form.initialData} heading={form.heading} catalogo={catalogo} />
      )}
    </div>
  )
}

const cancelBtn: React.CSSProperties = {
  padding: '7px 14px', borderRadius: '7px', border: '1.5px solid #e2e8f0',
  background: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: '0.8125rem', color: 'var(--color-text-muted)',
}
const deleteBtn: React.CSSProperties = {
  padding: '7px 16px', borderRadius: '7px', border: 'none', background: '#dc2626', color: '#FFFFFF',
  cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: '0.8125rem', fontWeight: 600,
}

export default PersonasPage
