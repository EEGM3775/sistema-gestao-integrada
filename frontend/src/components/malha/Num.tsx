import React from 'react'

/**
 * Leitura de instrumento (docs/identidade-visual.md §6): todo dado — preço,
 * quantidade, código, prazo, documento — em mono tabular. "Colunas como réguas"
 * é requisito, não estilo; por isso números em coluna alinham à direita.
 */
interface NumProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Alinha à direita (uso em células de tabela numérica). */
  right?: boolean
}

export const Num: React.FC<NumProps> = ({ right, style, children, ...rest }) => (
  <span
    className="num"
    style={{ ...(right ? { display: 'block', textAlign: 'right' } : null), ...style }}
    {...rest}
  >
    {children}
  </span>
)

export default Num
