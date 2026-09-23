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
