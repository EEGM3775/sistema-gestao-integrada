import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Lock } from 'lucide-react'

interface AccessNoticeProps {
  title: string
  message: string
  /** Ícone do topo (default: cadeado). */
  icon?: ReactNode
  /** Destino/rótulo do botão de volta (default: início). Passe `backTo=null` para omitir o botão. */
  backTo?: string | null
  backLabel?: string
}

/**
 * Tela amigável de acesso negado — usada quando o tenant não tem o módulo
 * contratado ou o usuário não tem a permissão exigida, no lugar de um 403 cru
 * da API (achado F4). Centralizada, discreta, com caminho de volta.
 */
export function AccessNotice({
  title,
  message,
  icon,
  backTo = '/app/dashboard',
  backLabel = 'Voltar ao início',
}: AccessNoticeProps) {
  return (
    <div className="flex flex-col items-center justify-center text-center px-6 py-20">
      <div
        className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
        style={{ background: '#f1f5f9', color: 'var(--color-text-muted)' }}
      >
        {icon ?? <Lock size={26} />}
      </div>
      <h1 className="text-lg font-bold mb-2" style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}>
        {title}
      </h1>
      <p
        className="text-sm mb-6"
        style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)', lineHeight: 1.5, maxWidth: '28rem' }}
      >
        {message}
      </p>
      {backTo && (
        <Link
          to={backTo}
          className="px-4 py-2 rounded-lg text-sm font-semibold"
          style={{ background: 'var(--color-brand)', color: '#FFFFFF', textDecoration: 'none', fontFamily: 'var(--font-body)' }}
        >
          {backLabel}
        </Link>
      )}
    </div>
  )
}

export default AccessNotice
