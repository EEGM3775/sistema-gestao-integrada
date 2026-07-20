import React, { useEffect, useState } from 'react'
import { AlertTriangle, LogOut, RefreshCw } from 'lucide-react'

/**
 * Aviso de queda de sessão — ver docs/acesso-e-permissoes.md §5.2.
 *
 * Aparece `session_warn_seconds` antes de a sessão expirar. "Continuar conectado"
 * força uma rotação do refresh, que ESTENDE a janela deslizante — mas só enquanto o
 * teto absoluto não foi atingido. Batido o teto, nem a atividade renova (é o que
 * garante que uma sessão roubada morre sozinha) e o usuário precisa relogar; por
 * isso o botão pode falhar, e tratamos esse caso explicitamente em vez de deixar o
 * usuário clicando num botão que não resolve.
 */
export const SessionWarningDialog: React.FC<{
  expiraEm: number // época em SEGUNDOS
  onContinuar: () => Promise<boolean>
  onSair: () => void
}> = ({ expiraEm, onContinuar, onSair }) => {
  const [restanteMs, setRestanteMs] = useState(() => Math.max(0, expiraEm * 1000 - Date.now()))
  const [tentando, setTentando] = useState(false)
  const [tetoAtingido, setTetoAtingido] = useState(false)

  useEffect(() => {
    setRestanteMs(Math.max(0, expiraEm * 1000 - Date.now()))
    const id = setInterval(() => setRestanteMs(Math.max(0, expiraEm * 1000 - Date.now())), 1000)
    return () => clearInterval(id)
  }, [expiraEm])

  const mm = String(Math.floor(restanteMs / 60000)).padStart(2, '0')
  const ss = String(Math.floor((restanteMs % 60000) / 1000)).padStart(2, '0')
  const horaQueda = new Date(expiraEm * 1000).toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
  })

  const continuar = async () => {
    setTentando(true)
    const ok = await onContinuar()
    setTentando(false)
    if (!ok) setTetoAtingido(true)
  }

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.4)' }} />
      <div
        className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 rounded-2xl w-full max-w-md"
        style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="titulo-aviso-sessao"
      >
        <div className="p-6 pb-4 flex items-center gap-3" style={{ borderBottom: '1px solid #e2e8f0' }}>
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: '#fef3c7', color: '#b45309' }}
          >
            <AlertTriangle size={18} />
          </div>
          <div>
            <h2
              id="titulo-aviso-sessao"
              className="text-lg font-bold"
              style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
            >
              {tetoAtingido ? 'Sessão encerrada' : 'Sua sessão vai expirar'}
            </h2>
            <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              {tetoAtingido
                ? 'Tempo máximo de sessão atingido — é preciso entrar novamente.'
                : `Desconexão prevista para as ${horaQueda}.`}
            </p>
          </div>
        </div>

        <div className="p-6" style={{ fontFamily: 'var(--font-body)' }}>
          {tetoAtingido ? (
            <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
              Por segurança, toda sessão tem um tempo máximo, mesmo em uso. Salve o que
              for possível e entre novamente para continuar.
            </p>
          ) : (
            <>
              <div className="flex items-baseline justify-center gap-2 py-2">
                <span
                  className="text-4xl font-bold tabular-nums"
                  style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
                >
                  {mm}:{ss}
                </span>
              </div>
              <p className="text-sm text-center" style={{ color: 'var(--color-text-muted)' }}>
                Você será desconectado por inatividade. Salve o que estiver editando ou
                clique abaixo para continuar trabalhando.
              </p>
            </>
          )}
        </div>

        <div className="px-6 pb-6 flex gap-2 justify-end">
          <button
            type="button"
            onClick={onSair}
            className="px-4 py-2 rounded-xl text-sm font-semibold inline-flex items-center gap-2"
            style={{ background: '#f1f5f9', color: 'var(--color-text-muted)' }}
          >
            <LogOut size={16} />
            {tetoAtingido ? 'Ir para o login' : 'Sair agora'}
          </button>
          {!tetoAtingido && (
            <button
              type="button"
              onClick={() => void continuar()}
              disabled={tentando}
              className="px-4 py-2 rounded-xl text-sm font-semibold inline-flex items-center gap-2 disabled:opacity-60"
              style={{ background: 'var(--color-brand)', color: '#FFFFFF' }}
            >
              <RefreshCw size={16} className={tentando ? 'animate-spin' : undefined} />
              {tentando ? 'Renovando…' : 'Continuar conectado'}
            </button>
          )}
        </div>
      </div>
    </>
  )
}
