import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'

/**
 * `useState` que espelha o valor em `localStorage` — sobrevive a F5 e à troca de
 * tela (o componente desmonta, mas a escolha volta). Tolerante a modo privado/
 * quota (cai no valor inicial sem quebrar). Prefixo `sgi_` como no resto do app.
 */
export function usePersistedState<T>(key: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw != null ? (JSON.parse(raw) as T) : initial
    } catch {
      return initial
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch {
      /* localStorage indisponível (modo privado/quota) — segue em memória */
    }
  }, [key, value])

  return [value, setValue]
}
