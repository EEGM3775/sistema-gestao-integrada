// ─── Máscaras & Parsers ───────────────────────────────────────────────────────

/** Aplica máscara DD/MM/AAAA ao digitar */
export function maskDate(v: string): string {
  const d = v.replace(/\D/g, '').slice(0, 8)
  if (d.length <= 2) return d
  if (d.length <= 4) return `${d.slice(0, 2)}/${d.slice(2)}`
  return `${d.slice(0, 2)}/${d.slice(2, 4)}/${d.slice(4)}`
}

/** DD/MM/AAAA → Date, ou null se inválida */
export function parseDateBR(br: string): Date | null {
  const d = br.replace(/\D/g, '')
  if (d.length !== 8) return null
  const day = +d.slice(0, 2), month = +d.slice(2, 4) - 1, year = +d.slice(4)
  const date = new Date(year, month, day)
  if (date.getFullYear() !== year || date.getMonth() !== month || date.getDate() !== day) return null
  return date
}

/** DD/MM/AAAA → YYYY-MM-DD (retorna '' se inválida) */
export function dateFromBR(br: string): string {
  const d = br.replace(/\D/g, '')
  if (d.length !== 8) return ''
  return `${d.slice(4)}-${d.slice(2, 4)}-${d.slice(0, 2)}`
}

/** YYYY-MM-DD → DD/MM/AAAA */
export function dateToBR(iso: string): string {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}

const MESES_ABREV = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

/**
 * ISO de mês → rótulo pt-BR "jul/2026". Aceita tanto "2026-07-01" quanto o
 * datetime ISO cru que o `/api/erp/dashboard/` devolve (`TruncMonth` →
 * "2026-07-01T00:00:00Z"). Lê o prefixo YYYY-MM da string (sem `new Date()`),
 * evitando que o fuso empurre o mês para o anterior.
 */
export function mesToBR(iso: string): string {
  if (!iso) return ''
  const [y, m] = iso.slice(0, 7).split('-')
  const idx = Number(m) - 1
  if (!y || Number.isNaN(idx) || idx < 0 || idx > 11) return iso
  return `${MESES_ABREV[idx]}/${y}`
}

/**
 * `Date` → `YYYY-MM-DD` no fuso **local**.
 *
 * `toISOString()` converte para UTC antes de fatiar: no Brasil (UTC−3), das 21h
 * em diante ele já devolve o dia seguinte. Onde a data é um **dia de calendário**
 * do usuário (janela "hoje…+7", rótulo "Hoje"/"Amanhã"), tem de ser a data local.
 */
export function isoLocal(d: Date): string {
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

// ─── Helpers internos ─────────────────────────────────────────────────────────

function toISO(d: Date): string { return d.toISOString().slice(0, 10) }

function formatISO(iso: string): string {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return `${d}/${m}/${y}`
}

// ─── Constantes e funções ISO para atributos min/max de type="date" ──────────
// Constantes fixas (nunca mudam):

export const minNascISO = '1900-01-01'
export const minAdmiISO = '1940-01-01'

// Funções dinâmicas (recalculadas a cada chamada — dependem de "hoje"):

export function maxTodayISO(): string { return toISO(new Date()) }

export function maxAdmiISO(): string {
  const d = new Date(); d.setFullYear(d.getFullYear() + 2); return toISO(d)
}
export function minVigenciaISO(): string {
  const d = new Date(); d.setFullYear(d.getFullYear() - 10); return toISO(d)
}
export function maxVigenciaISO(): string {
  const d = new Date(); d.setFullYear(d.getFullYear() + 20); return toISO(d)
}
export function minPagamentoISO(): string {
  const d = new Date(); d.setFullYear(d.getFullYear() - 1); return toISO(d)
}
export function maxPagamentoISO(): string {
  const d = new Date(); d.setFullYear(d.getFullYear() + 5); return toISO(d)
}

// ─── Validadores para type="date" (YYYY-MM-DD) ────────────────────────────────

/** Valida intervalo de uma data ISO. Passa '' para sem limite. */
export function validateISO(value: string, min: string, max: string): string | null {
  if (!value) return null
  if (min && value < min) return `Data fora do intervalo permitido (mínimo: ${formatISO(min)}).`
  if (max && value > max) return `Data fora do intervalo permitido (máximo: ${formatISO(max)}).`
  return null
}

export function validateISO_Nasc(v: string): string | null {
  return validateISO(v, minNascISO, maxTodayISO())
}
export function validateISO_Vigencia(v: string): string | null {
  return validateISO(v, minVigenciaISO(), maxVigenciaISO())
}
export function validateISO_Pagamento(v: string): string | null {
  return validateISO(v, minPagamentoISO(), maxPagamentoISO())
}
export function validateISO_ExameASO(v: string): string | null {
  return validateISO(v, minVigenciaISO(), maxTodayISO())
}
export function validateISO_ValidadeASO(v: string): string | null {
  return validateISO(v, minVigenciaISO(), maxVigenciaISO())
}

// ─── Validadores para DD/MM/AAAA (text inputs com máscara) ───────────────────

const MIN_NASC_DATE = new Date(1900, 0, 1)
const MIN_ADMI_DATE = new Date(1940, 0, 1)

export function validateDataNasc(br: string): string | null {
  if (!br) return null
  const d = parseDateBR(br)
  if (!d) return 'Data inválida — use DD/MM/AAAA.'
  const today = new Date(); today.setHours(23, 59, 59, 999)
  if (d > today) return 'Data de nascimento não pode ser futura.'
  if (d < MIN_NASC_DATE) return 'Data inválida (mínimo: 01/01/1900).'
  return null
}

export function validateDataAdmissao(br: string): string | null {
  if (!br) return null
  const d = parseDateBR(br)
  if (!d) return 'Data inválida — use DD/MM/AAAA.'
  const maxFuture = new Date(); maxFuture.setFullYear(maxFuture.getFullYear() + 2)
  if (d > maxFuture) return 'Data muito distante (máximo: 2 anos no futuro).'
  if (d < MIN_ADMI_DATE) return 'Data inválida (mínimo: 01/01/1940).'
  return null
}

export function validateDataDemissao(br: string, admissaoBR: string): string | null {
  if (!br) return null
  const d = parseDateBR(br)
  if (!d) return 'Data inválida — use DD/MM/AAAA.'
  const admi = parseDateBR(admissaoBR)
  if (admi && d < admi) return 'Data de demissão deve ser posterior à admissão.'
  return null
}
