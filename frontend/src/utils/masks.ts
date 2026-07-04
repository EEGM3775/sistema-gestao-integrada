// ─── Máscaras (aplicadas na digitação) ───────────────────────────────────────

export function maskCPF(v: string): string {
  const d = v.replace(/\D/g, '').slice(0, 11)
  return d.replace(/(\d{0,3})(\d{0,3})(\d{0,3})(\d{0,2})/, (_, a, b, c, e) => {
    if (e) return `${a}.${b}.${c}-${e}`
    if (c) return `${a}.${b}.${c}`
    if (b) return `${a}.${b}`
    return a
  })
}

export function maskCNPJ(v: string): string {
  const d = v.replace(/\D/g, '').slice(0, 14)
  return d.replace(/(\d{0,2})(\d{0,3})(\d{0,3})(\d{0,4})(\d{0,2})/, (_, a, b, c, dd, e) => {
    if (e)  return `${a}.${b}.${c}/${dd}-${e}`
    if (dd) return `${a}.${b}.${c}/${dd}`
    if (c)  return `${a}.${b}.${c}`
    if (b)  return `${a}.${b}`
    return a
  })
}

// Adapta automaticamente: ≤11 dígitos → CPF, 12-14 dígitos → CNPJ
export function maskCPFCNPJ(v: string): string {
  const d = v.replace(/\D/g, '').slice(0, 14)
  return d.length <= 11 ? maskCPF(d) : maskCNPJ(d)
}

// ─── Validação de dígitos verificadores ──────────────────────────────────────

export function validateCPF(digits: string): string | null {
  const d = digits.replace(/\D/g, '')
  if (d.length !== 11 || /^(\d)\1+$/.test(d)) return 'CPF inválido.'
  let sum = 0
  for (let i = 0; i < 9; i++) sum += +d[i] * (10 - i)
  let r = (sum * 10) % 11; if (r === 10 || r === 11) r = 0
  if (r !== +d[9]) return 'CPF inválido.'
  sum = 0
  for (let i = 0; i < 10; i++) sum += +d[i] * (11 - i)
  r = (sum * 10) % 11; if (r === 10 || r === 11) r = 0
  return r !== +d[10] ? 'CPF inválido.' : null
}

export function validateCNPJ(digits: string): string | null {
  const d = digits.replace(/\D/g, '')
  if (d.length !== 14 || /^(\d)\1+$/.test(d)) return 'CNPJ inválido.'
  const calc = (len: number) => {
    let s = 0, pos = len - 7
    for (let i = len; i >= 1; i--) { s += +d[len - i] * pos--; if (pos < 2) pos = 9 }
    return s % 11 < 2 ? 0 : 11 - (s % 11)
  }
  return calc(12) !== +d[12] || calc(13) !== +d[13] ? 'CNPJ inválido.' : null
}

export function validateCPFCNPJ(digits: string): string | null {
  const d = digits.replace(/\D/g, '')
  if (!d) return null
  if (d.length < 11)  return 'CPF incompleto — precisa de 11 dígitos.'
  if (d.length === 11) return validateCPF(d)
  if (d.length < 14)  return 'CNPJ incompleto — precisa de 14 dígitos.'
  return validateCNPJ(d)
}

// ─── Formatadores para exibição somente-leitura ───────────────────────────────

export function formatCPF(v: string | null | undefined): string {
  if (!v) return ''
  const d = v.replace(/\D/g, '')
  if (d.length !== 11) return v
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`
}

export function formatCNPJ(v: string | null | undefined): string {
  if (!v) return ''
  const d = v.replace(/\D/g, '')
  if (d.length !== 14) return v
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`
}

export function formatCPFCNPJ(v: string | null | undefined): string {
  if (!v) return ''
  const d = v.replace(/\D/g, '')
  if (d.length === 11) return formatCPF(d)
  if (d.length === 14) return formatCNPJ(d)
  return v
}

// ─── PIS/PASEP (NIT) — formato 000.00000.00-0 (11 dígitos) ───────────────────

export function maskPISPASEP(v: string): string {
  const d = v.replace(/\D/g, '').slice(0, 11)
  return d.replace(/(\d{0,3})(\d{0,5})(\d{0,2})(\d{0,1})/, (_, a, b, c, e) => {
    if (e) return `${a}.${b}.${c}-${e}`
    if (c) return `${a}.${b}.${c}`
    if (b) return `${a}.${b}`
    return a
  })
}

export function formatPISPASEP(v: string | null | undefined): string {
  if (!v) return ''
  const d = v.replace(/\D/g, '')
  if (d.length !== 11) return v
  return `${d.slice(0, 3)}.${d.slice(3, 8)}.${d.slice(8, 10)}-${d.slice(10)}`
}

export function validatePISPASEP(digits: string): string | null {
  const d = digits.replace(/\D/g, '')
  if (!d) return null
  if (d.length !== 11) return 'PIS/PASEP inválido — precisa de 11 dígitos.'
  if (/^(\d)\1+$/.test(d)) return 'PIS/PASEP inválido.'
  const weights = [3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
  let sum = 0
  for (let i = 0; i < 10; i++) sum += +d[i] * weights[i]
  const rem = sum % 11
  const check = rem < 2 ? 0 : 11 - rem
  return check !== +d[10] ? 'PIS/PASEP inválido.' : null
}
