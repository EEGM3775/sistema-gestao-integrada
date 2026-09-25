import { parseApiErrors } from '@/utils/formErrors'

/** Percentual em português, venha `number` do JSON ou `string` do `Decimal`.
 *
 *  **Existe porque a mesma linha mostrava as duas coisas.** O avanço atravessa
 *  como `float` e virava `77,6%`; o PPC e a conformidade atravessam como
 *  string (é assim que o DRF serializa `Decimal`, e é assim que centavo não
 *  vira dízima) e saíam cruas — `21.7%` e `75.00%`, com ponto, coladas ao
 *  `77,6%` com vírgula. Régua da identidade §6: colunas são réguas, e régua com
 *  duas marcações não mede nada.
 *
 *  `null` continua `null`, e quem chama decide a frase — aqui ninguém inventa
 *  "0%" para o que não foi apurado. */
export function percentual(
  valor: string | number | null | undefined,
  casas = 1,
): string | null {
  if (valor === null || valor === undefined || valor === '') return null
  const numero = typeof valor === 'number' ? valor : Number(valor)
  if (!Number.isFinite(numero)) return null
  return `${numero.toLocaleString('pt-BR', { maximumFractionDigits: casas })}%`
}

/** "3 dias" / "1 dia" / "hoje" — a contagem que a fila e o pulso repetem. */
export function emDias(quantos: number, zero = 'hoje'): string {
  if (quantos === 0) return zero
  const n = Math.abs(quantos)
  return `${n} ${n === 1 ? 'dia' : 'dias'}`
}

/** O "agora" no formato do `<input type="datetime-local">` — hora local, sem
 *  fuso, porque é assim que o campo o lê. */
export function agoraLocal(): string {
  const d = new Date()
  const doisDigitos = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${doisDigitos(d.getMonth() + 1)}-${doisDigitos(d.getDate())}`
    + `T${doisDigitos(d.getHours())}:${doisDigitos(d.getMinutes())}`
}

/** Data e hora do servidor, legíveis: "24/09/2026 às 14:32". */
export function dataHora(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.toLocaleDateString('pt-BR')} às ${d.toLocaleTimeString('pt-BR', {
    hour: '2-digit', minute: '2-digit',
  })}`
}

/** A frase que o diálogo mostra quando o gesto falha — a do servidor quando
 *  ele disse uma, e a tradução do `parseApiErrors` quando não (D187). */
export function primeiraFrase(e: unknown): string {
  const erros = parseApiErrors(e)
  return erros._form ?? erros.detail ?? Object.values(erros)[0] ?? 'Não foi possível concluir.'
}
