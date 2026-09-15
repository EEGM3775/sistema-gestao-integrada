import type { CSSProperties, FocusEvent, InputHTMLAttributes } from 'react'
import { digitsToCents, maskMoney } from '@/utils/money'

/**
 * Campos de entrada numérica da Malha — dinheiro, inteiro e decimal.
 *
 * **Por que existem, se o ERP já tinha um `MoneyInput`.** O do ERP é de um kit
 * local anterior à Malha e pinta cor fixa (`#e2e8f0`, `#FFFFFF`): no tema
 * escuro ele fica branco no escuro. Estes saem só de token, como o resto da
 * Malha, e por isso acompanham o tema sem reescrita — é a migração que a
 * [frontend.md §1.2](../../../../docs/frontend.md) prevê, feita na vez do PDCA.
 *
 * **O que os três compartilham, e que um `<input type="number">` não dá:**
 *
 * - **o valor se apresenta como a pessoa o escreve.** Real é `1.234,56`, não
 *   `1234.56`; e `500000` digitado num campo de valor é meio milhão, não
 *   quinhentos mil centavos perdidos numa conversão implícita;
 * - **zero à esquerda não sobrevive.** O `type="number"` controlado pelo React
 *   guarda `12` no estado e deixa `012` na caixa — o DOM e o estado divergem, e
 *   quem digitou vê um número que o sistema não tem;
 * - **a roda do mouse não muda o valor.** O `type="number"` altera o número
 *   quando alguém rola a página com o cursor sobre ele, e num formulário de
 *   contrato isso troca um prazo de pagamento sem ninguém perceber.
 */

const base: CSSProperties = {
  width: '100%', padding: '8px 10px', borderRadius: 8,
  border: '1px solid var(--line)', background: 'var(--surface)',
  color: 'var(--ink)', fontSize: 13.5,
}

/**
 * **Selecionar ao focar**, nos três campos.
 *
 * Campo numérico nunca está vazio — ele mostra `0,00` ou `0`, que é o valor
 * neutro, não um espaço em branco. Sem a seleção, clicar e digitar **acrescenta**
 * ao zero: quem digita `8000` num campo de preço recebe `R$ 80.000,00` em vez de
 * `R$ 80,00`, e o número errado parece plausível o bastante para ser salvo. Foi
 * exatamente assim que o teste de formulário da PDCA.3 tropeçou — o que ele
 * fez é o que uma pessoa faz.
 *
 * A `GradeDeMedicao` já tinha essa proteção na célula; aqui ela vira propriedade
 * do kit, e não lembrança de quem escreve o próximo formulário.
 */
const selecionaAoFocar = (e: FocusEvent<HTMLInputElement>) => e.target.select()

type Comuns = Omit<
  InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type'
>

interface MoedaProps extends Comuns {
  /** **Centavos inteiros**, nunca float — a convenção de `utils/money.ts`. */
  centavos: number
  aoMudar: (centavos: number) => void
}

/** Real brasileiro. O estado guarda centavos; a caixa mostra `1.234,56`. */
export function CampoMoeda({ centavos, aoMudar, style, ...resto }: MoedaProps) {
  return (
    <div style={{ position: 'relative' }}>
      <span style={{
        position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)',
        fontSize: 13, color: 'var(--ink-3)', pointerEvents: 'none',
      }}>
        R$
      </span>
      <input
        {...resto}
        type="text"
        inputMode="decimal"
        value={maskMoney(String(centavos))}
        onChange={e => aoMudar(digitsToCents(e.target.value))}
        onFocus={selecionaAoFocar}
        style={{
          ...base, paddingLeft: 34, textAlign: 'right',
          fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
          ...style,
        }}
      />
    </div>
  )
}

interface InteiroProps extends Comuns {
  valor: number
  aoMudar: (valor: number) => void
  min?: number
  max?: number
}

/** Contagem — dias, meses, unidades. Só dígitos, sem zero à esquerda. */
export function CampoInteiro({
  valor, aoMudar, min = 0, max, style, ...resto
}: InteiroProps) {
  return (
    <input
      {...resto}
      type="text"
      inputMode="numeric"
      value={String(valor)}
      onChange={e => {
        // Só dígitos, e o zero à esquerda morre na entrada — não no `blur`.
        // Corrigir só no `blur` deixaria a caixa mostrando `012` enquanto a
        // pessoa digita, que é exatamente a divergência que se quer evitar.
        const limpo = e.target.value.replace(/\D/g, '').replace(/^0+(?=\d)/, '')
        const n = limpo === '' ? 0 : parseInt(limpo, 10)
        aoMudar(max != null ? Math.min(n, max) : Math.max(n, min))
      }}
      onFocus={selecionaAoFocar}
      style={{
        ...base, textAlign: 'right',
        fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
        ...style,
      }}
    />
  )
}

interface DecimalProps extends Comuns {
  /** Texto, e não `number`: o campo precisa aceitar estados intermediários —
   *  `"1,"`, `"0,0"`, vazio — que um `number` não representa. A conversão
   *  acontece na borda da API, onde `paraNumero` é a leitura única. */
  valor: string
  aoMudar: (valor: string) => void
  /** Sufixo visual (`%`, `m²`). Não entra no valor. */
  sufixo?: string
  casas?: number
}

/** Percentual, quantidade, coeficiente — decimal com vírgula brasileira. */
export function CampoDecimal({
  valor, aoMudar, sufixo, casas = 4, style, ...resto
}: DecimalProps) {
  return (
    <div style={{ position: 'relative' }}>
      <input
        {...resto}
        type="text"
        inputMode="decimal"
        value={valor}
        onChange={e => {
          // Aceita vírgula **e** ponto (quem cola de planilha traz ponto), um
          // separador só, e corta as casas excedentes em vez de recusar a tecla
          // — recusar em silêncio faz a pessoa achar que o teclado falhou.
          let t = e.target.value.replace(/[^\d.,]/g, '').replace(/\./g, ',')
          const partes = t.split(',')
          if (partes.length > 2) t = partes[0] + ',' + partes.slice(1).join('')
          const [inteira, decimal] = t.split(',')
          t = decimal != null
            ? `${inteira.replace(/^0+(?=\d)/, '')},${decimal.slice(0, casas)}`
            : inteira.replace(/^0+(?=\d)/, '')
          aoMudar(t)
        }}
        onFocus={selecionaAoFocar}
        style={{
          ...base, textAlign: 'right', paddingRight: sufixo ? 30 : 10,
          fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
          ...style,
        }}
      />
      {sufixo && (
        <span style={{
          position: 'absolute', right: 11, top: '50%', transform: 'translateY(-50%)',
          fontSize: 12.5, color: 'var(--ink-3)', pointerEvents: 'none',
        }}>
          {sufixo}
        </span>
      )}
    </div>
  )
}

/** `"12,5"` → `"12.5"` — a leitura única na borda da API. Vazio vira `null`,
 *  e **`null` não é zero**: "não informado" e "zero por cento" são respostas
 *  diferentes, e o backend distingue as duas. */
export function paraNumero(valor: string): string | null {
  const limpo = (valor ?? '').trim().replace(',', '.')
  if (limpo === '' || limpo === '.') return null
  const n = Number(limpo)
  return Number.isFinite(n) ? String(n) : null
}

/** `"12.50"` (API) → `"12,5"` (caixa). Tira zeros decimais inúteis: ninguém
 *  digita `5,0000`, e mostrar isso sugere uma precisão que não foi escolhida. */
export function daApi(valor: string | number | null | undefined): string {
  if (valor == null || valor === '') return ''
  const n = Number(valor)
  if (!Number.isFinite(n)) return ''
  return String(n).replace('.', ',')
}
