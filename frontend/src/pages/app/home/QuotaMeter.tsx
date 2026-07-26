import { Num, Pill } from '@/components/malha'
import type { QuotaMedidor } from './useHomeResumo'

/**
 * Medidor de quota (docs/frontend.md §5.16.3). O princípio: o 402 do backend tem
 * de ser a **confirmação de algo já visível**, nunca a primeira notícia.
 *
 * Três regras que a barra não reinterpreta:
 * - `limite: 0` ≠ ilimitado — é "não incluído neste plano".
 * - `uso: null` ≠ zero — é quota de fonte externa (seats vêm da IAM); mostra só o teto.
 * - `ilimitado` não desenha barra: não há proporção de infinito.
 */
export function QuotaMeter({ q }: { q: QuotaMedidor }) {
  const semContagem = q.uso == null

  const pct =
    q.ilimitado || semContagem || !q.limite ? 0 : Math.min(100, Math.round((q.uso! / q.limite) * 100))

  const tom = q.excedido ? 'var(--danger)' : pct >= 80 ? 'var(--accent)' : 'var(--good)'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 12.5, color: 'var(--ink-2)', fontWeight: 500, textTransform: 'capitalize' }}>
          {q.rotulo}
        </span>
        <span style={{ marginLeft: 'auto' }}>
          {q.ilimitado ? (
            <Pill kind="info">sem limite</Pill>
          ) : semContagem ? (
            <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
              teto de <Num size={11.5}>{q.limite}</Num> · contagem na IAM
            </span>
          ) : (
            <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
              <Num size={12.5} tone={q.excedido ? 'var(--danger-ink)' : 'var(--ink)'}>
                {q.uso}
              </Num>
              {' / '}
              <Num size={11.5} tone="var(--ink-3)">
                {q.limite}
              </Num>
            </span>
          )}
        </span>
      </div>

      {!q.ilimitado && !semContagem && (
        <div style={{ height: 5, borderRadius: 999, background: 'var(--inset)', overflow: 'hidden' }}>
          <div style={{ width: `${pct}%`, height: '100%', background: tom, borderRadius: 999, transition: 'width .3s' }} />
        </div>
      )}

      {q.excedido && (
        <span style={{ fontSize: 11, color: 'var(--danger-ink)' }}>
          Limite atingido — novos cadastros ficam bloqueados.
        </span>
      )}
    </div>
  )
}
