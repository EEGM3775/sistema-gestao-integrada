// ─── Dinheiro — sempre em centavos inteiros (nunca float) ────────────────────
//
// O DRF serializa `DecimalField` como string decimal (ex.: "1234.56"). Para
// evitar que `0.1 + 0.2` corrompa centavos, todo valor monetário trafega no
// estado do formulário e nos componentes como **centavos inteiros** — só vira
// string decimal na borda da API (payload) e string formatada na exibição.

const BRL_FORMATTER = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })

/** Centavos inteiros → "R$ 1.234,56" (exibição). */
export function formatBRL(cents: number | string | null | undefined): string {
  if (cents == null || Number.isNaN(Number(cents))) return BRL_FORMATTER.format(0)
  const num = typeof cents === 'string' ? apiDecimalToCents(cents) : cents
  return BRL_FORMATTER.format(num / 100)
}

/** Dígitos digitados (qualquer formatação) → "1.234,56" (sem o "R$", para o `value=` do input). */
export function maskMoney(v: string): string {
  const digits = v.replace(/\D/g, '')
  const cents = digits === '' ? 0 : parseInt(digits, 10)
  return (cents / 100).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** Dígitos digitados → centavos inteiros (estado do formulário). */
export function digitsToCents(v: string): number {
  const digits = v.replace(/\D/g, '')
  return digits === '' ? 0 : parseInt(digits, 10)
}

/** Centavos inteiros → string decimal "1234.56" (payload para a API/DRF). */
export function centsToApiDecimal(cents: number | null | undefined): string {
  const safe = cents ?? 0
  return (safe / 100).toFixed(2)
}

/** String/numero decimal vindo da API ("1234.56" ou 1234.56) → centavos inteiros. */
export function apiDecimalToCents(value: string | number | null | undefined): number {
  if (value == null || value === '') return 0
  const n = typeof value === 'number' ? value : parseFloat(value)
  if (Number.isNaN(n)) return 0
  return Math.round(n * 100)
}
