import React, { useState } from 'react'
import { KeyRound, CheckCircle2 } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { PasswordField } from '@/components/PasswordField'

/**
 * Troca da própria senha (self-service). Ao concluir, o backend encerra as OUTRAS
 * sessões do usuário e mantém a atual — por isso avisamos o usuário disso.
 */
export const ChangePasswordModal: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const { changePassword, user } = useAuth()
  const [atual, setAtual] = useState('')
  const [nova, setNova] = useState('')
  const [conf, setConf] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (nova.length < 8) { setError('A nova senha deve ter ao menos 8 caracteres.'); return }
    if (nova !== conf) { setError('A confirmação não confere com a nova senha.'); return }
    if (nova === atual) { setError('A nova senha deve ser diferente da atual.'); return }
    setSaving(true)
    try {
      await changePassword(atual, nova)
      setOk(true)
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Não foi possível alterar a senha.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={onClose} />
      <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-2xl w-full max-w-md"
        style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}>
        <div className="p-6 pb-4 flex items-center gap-3" style={{ borderBottom: '1px solid #e2e8f0' }}>
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: '#dcfce7', color: 'var(--color-brand)' }}>
            <KeyRound size={18} />
          </div>
          <div>
            <h2 className="text-lg font-bold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
              Alterar senha
            </h2>
            <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              Você está alterando a senha da sua conta (<b>{user?.username}</b>).
            </p>
          </div>
        </div>

        {ok ? (
          <div className="p-6 flex flex-col items-center text-center gap-3">
            <CheckCircle2 size={40} style={{ color: 'var(--color-brand)' }} />
            <p className="text-sm" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-body)' }}>
              Senha alterada com sucesso. Por segurança, <b>as suas outras sessões foram encerradas</b> —
              este dispositivo continua conectado.
            </p>
            <button onClick={onClose} style={saveBtn}>Fechar</button>
          </div>
        ) : (
          <form onSubmit={submit} className="p-6 flex flex-col gap-4">
            {error && (
              <div className="text-sm px-4 py-2.5 rounded-lg" style={{ background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030', fontFamily: 'var(--font-body)' }}>
                {error}
              </div>
            )}
            <PasswordField label="Senha atual" value={atual} onChange={setAtual} autoFocus autoComplete="current-password" />
            <PasswordField label="Nova senha" value={nova} onChange={setNova} hint="Mínimo 8 caracteres." autoComplete="new-password" />
            <PasswordField label="Confirmar nova senha" value={conf} onChange={setConf} autoComplete="new-password" />
            <div className="flex justify-end gap-3 pt-1">
              <button type="button" onClick={onClose} style={cancelBtn}>Cancelar</button>
              <button type="submit" disabled={saving} style={{ ...saveBtn, opacity: saving ? 0.7 : 1 }}>
                {saving ? 'Alterando…' : 'Alterar senha'}
              </button>
            </div>
          </form>
        )}
      </div>
    </>
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

export default ChangePasswordModal
