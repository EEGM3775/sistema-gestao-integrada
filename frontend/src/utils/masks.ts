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

// ─── Chave de acesso da NF-e — 44 dígitos em grupos de 4 ─────────────────────
// Testada como CPF e CNPJ (dono, 11/10/2026): o dígito verificador (módulo 11),
// e o que a chave carrega dentro — modelo, mês de emissão e o CNPJ/CPF do
// emitente, que tem os próprios dígitos. Espelha `moduloscm.notas.validar_chave`.
// **Avisa, não bloqueia**: a nota pode sair em nome de outra empresa, e a nota
// errada registrada e marcada vale mais que a nota recusada e esquecida.

export function maskChaveNFe(v: string): string {
  return v.replace(/\D/g, '').slice(0, 44).replace(/(\d{4})(?=\d)/g, '$1 ')
}

export function validateChaveNFe(digits: string): string | null {
  const d = digits.replace(/\D/g, '')
  if (!d) return null
  if (d.length !== 44) return `Chave incompleta — ${d.length} de 44 dígitos.`
  let soma = 0, peso = 2
  for (let i = 42; i >= 0; i--) { soma += +d[i] * peso; peso = peso === 9 ? 2 : peso + 1 }
  const resto = soma % 11
  if ((resto < 2 ? 0 : 11 - resto) !== +d[43]) return 'Chave de acesso inválida — confira a digitação.'
  const mes = +d.slice(4, 6)
  if (mes < 1 || mes > 12) return 'Chave de acesso inválida — o mês de emissão não existe.'
  const modelo = d.slice(20, 22)
  if (modelo !== '55' && modelo !== '65') return `A chave é de um documento modelo ${modelo}, não de NF-e.`
  const emitente = d.slice(6, 20)
  const cpfDoEmitente = emitente.startsWith('000') && validateCPF(emitente.slice(3)) === null
  if (validateCNPJ(emitente) !== null && !cpfDoEmitente) return 'Chave de acesso inválida — o CNPJ do emitente dentro dela não confere.'
  return null
}

/** O número da nota que a chave carrega (posições 26–34), sem zeros à esquerda. */
export function numeroDaChaveNFe(digits: string): string {
  const d = digits.replace(/\D/g, '')
  return d.length === 44 ? String(+d.slice(25, 34)) : ''
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
