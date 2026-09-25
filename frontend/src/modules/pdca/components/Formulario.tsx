import type { CSSProperties, ReactNode } from 'react'

/** As peças de formulário do módulo.
 *
 *  Nasceram copiadas dentro do formulário de contrato e da esteira de
 *  restrições; a F.5 seria a terceira cópia, e é aí que se promove. **O
 *  rótulo envolve o campo** (`<label>` e não `<div>`): sem a associação, o
 *  leitor de tela anuncia "caixa de texto" sem dizer qual, e o roteiro de
 *  navegador não acha o campo pelo nome que a pessoa lê. */

export function Linha({ children }: { children: ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-start' }}>
      {children}
    </div>
  )
}

const rotuloDoCampo: CSSProperties = {
  display: 'block', fontSize: 10.5, letterSpacing: '0.07em',
  textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700,
  marginBottom: 5,
}

export function Campo({
  rotulo, larga, children,
}: { rotulo: string; larga?: boolean; children: ReactNode }) {
  return (
    <label style={{ display: 'block', flex: larga ? 2 : 1, minWidth: 160 }}>
      <span style={rotuloDoCampo}>{rotulo}</span>
      {children}
    </label>
  )
}

/** Um grupo de escolhas (rádios, botões) — `fieldset`, porque um `label` em
 *  volta de vários controles associaria o rótulo só ao primeiro. */
export function Grupo({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <fieldset style={{ border: 'none', padding: 0, margin: 0, minWidth: 0 }}>
      <legend style={{ ...rotuloDoCampo, padding: 0 }}>{rotulo}</legend>
      {children}
    </fieldset>
  )
}

export function Ajuda({ children }: { children: ReactNode }) {
  return (
    <span
      style={{
        display: 'block', margin: '5px 0 0', fontSize: 11.5,
        color: 'var(--ink-3)', lineHeight: 1.5, textTransform: 'none',
        letterSpacing: 0, fontWeight: 400,
      }}
    >
      {children}
    </span>
  )
}

/** O erro do gesto que falhou, dentro do diálogo que o fez — a frase já vem
 *  traduzida pelo `parseApiErrors` (D187). */
export function FaixaDeErro({ children }: { children: ReactNode }) {
  if (!children) return null
  return (
    <div
      role="alert"
      style={{
        padding: '9px 11px', borderRadius: 'var(--r-sm)',
        background: 'var(--danger-soft)', color: 'var(--danger-ink)',
        fontSize: 12.5, lineHeight: 1.5,
      }}
    >
      {children}
    </div>
  )
}

/** Botões de escolha única, grandes o bastante para o dedo — o `select` de
 *  quatro opções esconde três delas atrás de um toque a mais. */
export function Escolhas<T extends string>({
  opcoes, valor, aoEscolher, tamanho = 'md', rotulo,
}: {
  opcoes: { valor: T; rotulo: string; tom?: 'good' | 'danger' | 'accent' | 'slate' }[]
  valor: T | null
  aoEscolher: (v: T) => void
  tamanho?: 'md' | 'lg'
  /** Nome do grupo, quando há vários na mesma tela — "resposta da pergunta 3"
   *  é o que o leitor de tela anuncia, em vez de quatro botões soltos. */
  rotulo?: string
}) {
  return (
    <div role={rotulo ? 'group' : undefined} aria-label={rotulo} style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {opcoes.map((o) => {
        const ativo = valor === o.valor
        const tom = o.tom ?? 'accent'
        return (
          <button
            key={o.valor}
            type="button"
            aria-pressed={ativo}
            onClick={() => aoEscolher(o.valor)}
            style={{
              flex: tamanho === 'lg' ? '1 1 140px' : undefined,
              minHeight: tamanho === 'lg' ? 56 : 34,
              padding: tamanho === 'lg' ? '12px 14px' : '6px 11px',
              borderRadius: tamanho === 'lg' ? 12 : 'var(--r-sm)',
              border: `1px solid ${ativo ? `var(--${tom === 'slate' ? 'ink-3' : `${tom}-ink`})` : 'var(--line)'}`,
              background: ativo
                ? (tom === 'slate' ? 'var(--surface-2)' : `var(--${tom}-soft)`)
                : 'var(--surface)',
              color: ativo
                ? (tom === 'slate' ? 'var(--ink)' : `var(--${tom}-ink)`)
                : 'var(--ink-2)',
              fontSize: tamanho === 'lg' ? 16 : 12.5,
              fontWeight: 650, cursor: 'pointer', fontFamily: 'inherit',
              textAlign: 'center',
            }}
          >
            {o.rotulo}
          </button>
        )
      })}
    </div>
  )
}
