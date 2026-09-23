import { Lock } from 'lucide-react'
import type { SemPermissao } from '../types'

/** O que a leitura **deixou de fora**, e a quem pedir.
 *
 *  As leituras do cockpit nunca recusam a página inteira por falta de uma
 *  permissão: o bloco vem nulo e a razão vem numa lista. Esta faixa é a outra
 *  metade da régua omitir × trancar — sem ela a fila pareceria vazia, e fila
 *  vazia por falta de acesso é a pior forma de falha, porque não parece falha. */
export function SemPermissaoAviso({ itens }: { itens: SemPermissao[] }) {
  if (itens.length === 0) return null

  return (
    <div
      style={{
        display: 'flex', gap: 10, alignItems: 'flex-start',
        padding: '10px 13px', borderRadius: 'var(--r-sm)',
        background: 'var(--inset)', border: '1px dashed var(--line)',
      }}
    >
      <Lock size={14} style={{ color: 'var(--ink-3)', flexShrink: 0, marginTop: 2 }} />
      <div style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>
        Esta tela está incompleta para o seu acesso.{' '}
        {itens.length === 1 ? 'Falta ver' : 'Faltam ver'}{' '}
        {itens.map((item, i) => (
          <span key={item.permissao}>
            {i > 0 && (i === itens.length - 1 ? ' e ' : ', ')}
            <strong style={{ fontWeight: 650, color: 'var(--ink)' }}>{item.o_que}</strong>
            <code
              style={{
                fontFamily: 'var(--mono)', fontSize: 11, marginLeft: 5,
                color: 'var(--ink-3)',
              }}
            >
              {item.permissao}
            </code>
          </span>
        ))}
        . Quem libera é o administrador da empresa.
      </div>
    </div>
  )
}
