import type { ReactNode } from 'react'
import React, { createContext, useCallback, useEffect, useState } from 'react'

/**
 * Tema da identidade Malha v1 (docs/identidade-visual.md §5.3): claro e escuro
 * desde o desenho. `'system'` segue o `prefers-color-scheme`; `'light'`/`'dark'`
 * carimbam `data-theme` no <html> e vencem o sinal do SO. A escolha persiste em
 * localStorage (`sgi_theme`); o script anti-flash em index.html a aplica antes
 * do primeiro paint.
 */
export type ThemePreference = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'sgi_theme'

interface ThemeContextType {
  /** Preferência escolhida pelo usuário (pode ser 'system'). */
  preference: ThemePreference
  /** Tema efetivamente aplicado agora ('light' | 'dark'). */
  resolved: ResolvedTheme
  setPreference: (pref: ThemePreference) => void
  /** Alterna claro↔escuro a partir do que está aplicado (deixa de ser 'system'). */
  toggle: () => void
}

export const ThemeContext = createContext<ThemeContextType>({} as ThemeContextType)

function readStored(): ThemePreference {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'light' || v === 'dark') return v
  } catch {
    /* localStorage indisponível — cai em 'system' */
  }
  return 'system'
}

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-color-scheme: dark)').matches === true
}

function resolve(pref: ThemePreference): ResolvedTheme {
  if (pref === 'system') return systemPrefersDark() ? 'dark' : 'light'
  return pref
}

export const ThemeProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [preference, setPreferenceState] = useState<ThemePreference>(readStored)
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolve(readStored()))

  // Aplica a preferência ao <html> e persiste. 'system' remove o atributo para
  // devolver o controle ao prefers-color-scheme.
  useEffect(() => {
    const root = document.documentElement
    if (preference === 'system') {
      root.removeAttribute('data-theme')
      try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }
    } else {
      root.setAttribute('data-theme', preference)
      try { localStorage.setItem(STORAGE_KEY, preference) } catch { /* ignore */ }
    }
    setResolved(resolve(preference))
  }, [preference])

  // Enquanto em 'system', acompanha a troca de tema do SO em tempo real.
  useEffect(() => {
    if (preference !== 'system' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => setResolved(mq.matches ? 'dark' : 'light')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [preference])

  const setPreference = useCallback((pref: ThemePreference) => setPreferenceState(pref), [])
  const toggle = useCallback(
    () => setPreferenceState(resolve(readStored()) === 'dark' ? 'light' : 'dark'),
    [],
  )

  return (
    <ThemeContext.Provider value={{ preference, resolved, setPreference, toggle }}>
      {children}
    </ThemeContext.Provider>
  )
}
