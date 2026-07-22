import React from 'react'
import { Moon, Sun } from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'

/**
 * Botão de alternância claro↔escuro. O "movimento" da marca é o próprio anoitecer
 * (docs/identidade-visual.md §7) — o gesto de trocar tema é gesto de marca.
 */
export const ThemeToggle: React.FC<{ className?: string }> = ({ className }) => {
  const { resolved, toggle } = useTheme()
  const isDark = resolved === 'dark'
  return (
    <button
      type="button"
      onClick={toggle}
      className={className}
      aria-label={isDark ? 'Mudar para tema claro' : 'Mudar para tema escuro'}
      title={isDark ? 'Tema claro' : 'Tema escuro'}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 34,
        height: 34,
        borderRadius: 'var(--r-sm)',
        color: 'var(--ink-2)',
        transition: 'background .15s, color .15s',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.color = 'var(--ink)' }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--ink-2)' }}
    >
      {isDark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  )
}
