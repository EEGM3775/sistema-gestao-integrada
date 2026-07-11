import React, { useState, useMemo } from 'react'
import { Users, Search, Pencil, ShieldCheck } from 'lucide-react'
import { useUsuarios } from '../hooks/useUsuarios'
import type { UsuarioAdmin, Perfil } from '../types'

const PersonasEditor: React.FC<{
  usuario: UsuarioAdmin
  perfis: Perfil[]
  onClose: () => void
  onSave: (ids: number[]) => Promise<void>
}> = ({ usuario, perfis, onClose, onSave }) => {
  const [sel, setSel] = useState<Set<number>>(new Set(usuario.perfis))
  const [saving, setSaving] = useState(false)
  const toggle = (id: number) => setSel(prev => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n
  })
  const salvar = async () => { setSaving(true); try { await onSave([...sel]) } finally { setSaving(false) } }

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={onClose} />
      <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-2xl w-full max-w-lg flex flex-col"
        style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)', maxHeight: '86vh' }}>
        <div className="p-6 pb-4" style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 className="text-lg font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
            Papéis de {usuario.username}
          </h2>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
            As permissões efetivas são a união dos papéis marcados, limitada aos módulos contratados.
          </p>
        </div>
        <div className="px-6 py-3 overflow-y-auto flex flex-col gap-1">
          {usuario.is_tenant_admin && (
            <div className="flex items-start gap-2 rounded-lg p-3 mb-1" style={{ background: '#eef2ff' }}>
              <ShieldCheck size={16} style={{ color: 'var(--color-brand)', marginTop: 1 }} />
              <p className="text-xs" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>
                Admin do tenant — já tem acesso total, independente dos papéis abaixo.
              </p>
            </div>
          )}
          {perfis.map(p => (
            <label key={p.id} className="flex items-start gap-2 cursor-pointer py-1.5 px-2 rounded-lg"
              onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = '#f8fafc')}
              onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = 'transparent')}>
              <input type="checkbox" checked={sel.has(p.id)} onChange={() => toggle(p.id)}
                style={{ accentColor: 'var(--color-brand)', width: 15, height: 15, marginTop: 2 }} />
              <div className="min-w-0">
                <p className="text-sm font-semibold" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>{p.nome}</p>
                {p.descricao && <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>{p.descricao}</p>}
              </div>
            </label>
          ))}
        </div>
        <div className="flex justify-end gap-3 px-6 py-4" style={{ borderTop: '1px solid #e2e8f0' }}>
          <button onClick={onClose} style={cancelBtn}>Cancelar</button>
          <button onClick={salvar} disabled={saving} style={{ ...saveBtn, opacity: saving ? 0.7 : 1 }}>
            {saving ? 'Salvando…' : 'Salvar papéis'}
          </button>
        </div>
      </div>
    </>
  )
}

const UsuariosPage: React.FC = () => {
  const { usuarios, perfis, loading, error, setPerfisDoUsuario } = useUsuarios()
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<UsuarioAdmin | null>(null)

  const nomePorId = useMemo(() => new Map(perfis.map(p => [p.id, p.nome])), [perfis])
  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    if (!q) return usuarios
    return usuarios.filter(u => u.username.toLowerCase().includes(q) || u.email.toLowerCase().includes(q))
  }, [usuarios, search])

  return (
    <div className="px-6 py-8 max-w-4xl">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: '#dcfce7', color: 'var(--color-brand)' }}>
          <Users size={20} />
        </div>
        <h1 className="text-2xl font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>Usuários e Papéis</h1>
      </div>
      <p className="text-sm mb-6" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
        Atribua papéis (personas) a cada usuário do tenant. Os papéis são geridos em <b>Papéis e Acessos</b>.
      </p>

      <div className="relative max-w-xs mb-5">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-muted)' }} />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar usuário…"
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
                {['Usuário', 'Papéis', ''].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={3} style={{ padding: '32px', textAlign: 'center', color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', fontSize: '0.875rem' }}>Nenhum usuário.</td></tr>
              ) : filtered.map(u => (
                <tr key={u.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '12px 16px' }}>
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-semibold" style={{ color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>{u.username}</span>
                      {u.is_tenant_admin && (
                        <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: '#eef2ff', color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}>admin</span>
                      )}
                    </div>
                    <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>{u.email || '—'}</p>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div className="flex flex-wrap gap-1">
                      {u.perfis.length === 0 && <span className="text-sm" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>—</span>}
                      {u.perfis.map(pid => (
                        <span key={pid} className="text-xs px-2 py-0.5 rounded-full" style={{ background: '#f1f5f9', color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
                          {nomePorId.get(pid) ?? `#${pid}`}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', width: '60px' }}>
                    <button onClick={() => setEditing(u)} className="p-1.5 rounded" title="Editar papéis"
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                      <Pencil size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <PersonasEditor usuario={editing} perfis={perfis} onClose={() => setEditing(null)}
          onSave={async (ids) => { await setPerfisDoUsuario(editing.id, ids); setEditing(null) }} />
      )}
    </div>
  )
}

const cancelBtn: React.CSSProperties = {
  padding: '8px 16px', borderRadius: '8px', border: '1.5px solid #e2e8f0',
  background: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: '0.875rem', color: 'var(--color-text-muted)',
}
const saveBtn: React.CSSProperties = {
  padding: '8px 20px', borderRadius: '8px', border: 'none', background: 'var(--color-brand)', color: '#FFFFFF',
  cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: '0.875rem', fontWeight: 600,
}

export default UsuariosPage
