import type { LucideIcon } from 'lucide-react'

export interface VistaDoPosto<T extends string> {
  chave: T
  rotulo: string
  icone: LucideIcon
}

/** O cabeçalho do posto: o nome, a cadência e as vistas sobre o mesmo
 *  assunto. As abas são `tab` de verdade — quem navega por teclado ou leitor
 *  de tela ouve "aba 2 de 4, selecionada", e não quatro botões soltos. */
export function VistasDoPosto<T extends string>({
  titulo, sub, vistas, atual, aoEscolher, contagem = {},
}: {
  titulo: string
  sub: string
  vistas: VistaDoPosto<T>[]
  atual: T
  aoEscolher: (v: T) => void
  contagem?: Partial<Record<T, number | undefined>>
}) {
  return (
    <div style={{ flexShrink: 0, background: 'var(--surface)', borderBottom: '1px solid var(--line)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, padding: '14px 20px 8px' }}>
        <span style={{ fontSize: 17, fontWeight: 750, color: 'var(--ink)' }}>{titulo}</span>
        <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>{sub}</span>
      </div>
      <div role="tablist" aria-label={titulo} style={{ display: 'flex', gap: 2, padding: '0 16px 7px', flexWrap: 'wrap' }}>
        {vistas.map(({ chave, rotulo, icone: Icone }) => {
          const ativa = chave === atual
          const n = contagem[chave]
          return (
            <button
              key={chave}
              type="button"
              role="tab"
              aria-selected={ativa}
              onClick={() => aoEscolher(chave)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: ativa ? 'var(--surface-2)' : 'transparent',
                border: `1px solid ${ativa ? 'var(--line)' : 'transparent'}`,
                borderRadius: 5, cursor: 'pointer', padding: '5px 10px',
                fontSize: 12, fontWeight: 650,
                color: ativa ? 'var(--ink)' : 'var(--ink-3)',
              }}
            >
              <Icone size={13} />
              {rotulo}
              {n ? (
                <span
                  style={{
                    fontFamily: 'var(--mono)', fontSize: 10.5, padding: '0 5px',
                    borderRadius: 999, background: 'var(--accent-soft)', color: 'var(--accent-ink)',
                  }}
                >
                  {n}
                </span>
              ) : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}
