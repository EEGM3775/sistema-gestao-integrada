import React from 'react'

/**
 * Chip de edição/estágio (docs/identidade-visual.md §9) — "toda tela declara seu
 * endereço no ciclo". O produto atual é a Edição Construtora, que habita o estágio
 * Construir (âmbar). Cor é endereço, não decoração: a Construtora usa âmbar porque
 * vive em Construir — não porque "âmbar é a cor do SGI".
 *
 * Reutilizável: quando nascerem outras edições, muda o par (nome, estágio, cor).
 */
interface EdicaoChipProps {
  edicao?: string
  estagio?: string
  className?: string
}

export const EdicaoChip: React.FC<EdicaoChipProps> = ({
  edicao = 'Edição Construtora',
  estagio = 'Construir',
  className,
}) => (
  <span
    className={className}
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 7,
      padding: '3px 10px',
      borderRadius: 999,
      background: 'var(--accent-soft)',
      color: 'var(--accent-ink)',
      fontSize: 11.5,
      fontWeight: 600,
      whiteSpace: 'nowrap',
    }}
  >
    {/* a avenida "Construir" do marco, na escala do chip */}
    <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--accent)', flex: 'none' }} />
    {edicao}
    <span style={{ opacity: 0.5 }}>·</span>
    {estagio}
  </span>
)

export default EdicaoChip
