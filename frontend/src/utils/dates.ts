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

/**
 * Instante ISO do servidor (`2026-10-01T00:33:31Z`) → `30/09/2026 21:33` no fuso
 * **local**. Fatiar o texto (`iso.slice(0, 10)`) dá o dia em UTC: o arquivo
 * gerado às 21h aparecia como do dia seguinte.
 */
export function dataHoraBR(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${formatISO(isoLocal(d))} ${hh}:${mi}`
}

// ─── Helpers internos ─────────────────────────────────────────────────────────

function toISO(d: Date): string { return d.toISOString().slice(0, 10) }

function formatISO(iso: string): string {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return `${d}/${m}/${y}`
}

// ─── A faixa do calendário — uma só, para toda a plataforma ──────────────────
//
// **1900–2100 em todo campo de data, sem exceção** *(decisão do dono,
// 15/09/2026)*. Antes cada família de campo tinha a sua janela — vigência era
// `hoje−10 … hoje+20`, pagamento era `hoje−1 … hoje+5` — e o sintoma apareceu no
// Expediente do PDCA: o campo de exceção do calendário abria em **2016–2046** e
// não havia como cadastrar o feriado de 2047.
//
// Janela que anda com o relógio é pior do que janela estreita: a mesma tela
// aceita hoje o que vai recusar no ano que vem, e ninguém consegue explicar o
// porquê para quem está do outro lado.
//
// **O `min`/`max` do input não é o lugar da regra de negócio.** O que é absurdo
// — nascimento no futuro, exame que ainda não aconteceu — continua recusado,
// mas pelos **validadores** abaixo, que têm frase. `min`/`max` de um
// `type="date"` apagam o dia do calendário do navegador sem dizer nada: a
// pessoa clica, não acontece nada, e a conclusão dela é que o sistema travou.

/** O primeiro dia que qualquer campo de data da plataforma aceita. */
export const minCalendarioISO = '1900-01-01'
/** E o último. Duzentos anos é mais do que qualquer documento de obra alcança, e
 *  o bastante para esta faixa nunca mais ser o motivo de uma recusa. */
export const maxCalendarioISO = '2100-12-31'

// ─── Constantes e funções ISO para atributos min/max de type="date" ──────────
//
// Mantidas como **apelidos** da faixa única: o nome diz em que campo o valor
// está sendo usado e continua legível no JSX, e mudar a faixa de todos é mudar
// as duas constantes acima. Nenhum deles anda com o relógio.

export const minNascISO = minCalendarioISO
export const minAdmiISO = minCalendarioISO

/** Hoje, em ISO. **Não é mais `max` de input nenhum** — é o que os validadores
 *  de "não pode ser futura" comparam, e o que a tela usa como valor padrão. */
export function maxTodayISO(): string { return toISO(new Date()) }

export function maxAdmiISO(): string { return maxCalendarioISO }
export function minVigenciaISO(): string { return minCalendarioISO }
export function maxVigenciaISO(): string { return maxCalendarioISO }
export function minPagamentoISO(): string { return minCalendarioISO }
export function maxPagamentoISO(): string { return maxCalendarioISO }

// ─── Validadores para type="date" (YYYY-MM-DD) ────────────────────────────────

/** Valida intervalo de uma data ISO. Passa '' para sem limite. */
export function validateISO(value: string, min: string, max: string): string | null {
  if (!value) return null
  if (min && value < min) return `Data fora do intervalo permitido (mínimo: ${formatISO(min)}).`
  if (max && value > max) return `Data fora do intervalo permitido (máximo: ${formatISO(max)}).`
  return null
}

/** A faixa do calendário e nada mais — para o campo cuja única regra é ser uma
 *  data: vigência de contrato, início de plano, exceção de calendário, prazo. */
export function validateISO_Calendario(v: string): string | null {
  return validateISO(v, minCalendarioISO, maxCalendarioISO)
}

/** Nascimento: a faixa, **mais** a regra de que ninguém nasceu amanhã. */
export function validateISO_Nasc(v: string): string | null {
  return (
    validateISO_Calendario(v)
    ?? (v > maxTodayISO() ? 'Data de nascimento não pode ser futura.' : null)
  )
}
export function validateISO_Vigencia(v: string): string | null {
  return validateISO_Calendario(v)
}
export function validateISO_Pagamento(v: string): string | null {
  return validateISO_Calendario(v)
}
/** O exame já foi feito. Data de exame no futuro é erro de digitação — e o ASO
 *  que sai dela vence numa data que nunca começou a valer. */
export function validateISO_ExameASO(v: string): string | null {
  return (
    validateISO_Calendario(v)
    ?? (v > maxTodayISO() ? 'A data do exame não pode ser futura.' : null)
  )
}
export function validateISO_ValidadeASO(v: string): string | null {
  return validateISO_Calendario(v)
}

// ─── Validadores para DD/MM/AAAA (text inputs com máscara) ───────────────────

const MIN_DATE = new Date(1900, 0, 1)
const MAX_DATE = new Date(2100, 11, 31)

export function validateDataNasc(br: string): string | null {
  if (!br) return null
  const d = parseDateBR(br)
  if (!d) return 'Data inválida — use DD/MM/AAAA.'
  const today = new Date(); today.setHours(23, 59, 59, 999)
  if (d > today) return 'Data de nascimento não pode ser futura.'
  if (d < MIN_DATE) return 'Data inválida (mínimo: 01/01/1900).'
  return null
}

export function validateDataAdmissao(br: string): string | null {
  if (!br) return null
  const d = parseDateBR(br)
  if (!d) return 'Data inválida — use DD/MM/AAAA.'
  if (d > MAX_DATE) return 'Data inválida (máximo: 31/12/2100).'
  if (d < MIN_DATE) return 'Data inválida (mínimo: 01/01/1900).'
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
