import { Link } from 'react-router-dom'
import { ArrowRight, CheckCircle2 } from 'lucide-react'
import { Card, Empty, Pill } from '@/components/malha'
import type { Decisao } from './useHomeResumo'

/**
 * A fila "requer sua decisão" — o item nº 1 da régua (frontend.md §1.6.1) e o
 * equivalente ao *Assigned to Me* do Autodesk Construction Cloud, ao *open items
 * for review* do Procore e ao *Assistant* do Salesforce.
 *
 * Duas regras: **só entra o que tem número real** (a fila é montada a partir dos
 * agregados dos módulos, nunca de um placeholder) e **todo item leva à tela onde
 * a decisão se toma** — é a integração visível do §1.6.6.
 *
 * Aqui mora o **acento da tela**: âmbar marca exclusivamente o que exige ação.
 */
export function ListaDecisoes({ decisoes, limite }: { decisoes: Decisao[]; limite?: number }) {
  const itens = limite ? decisoes.slice(0, limite) : decisoes

  if (itens.length === 0) {
    return (
      <Card style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 20 }}>
        <CheckCircle2 size={22} style={{ color: 'var(--good)', flex: 'none' }} />
        <div>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>Nada exige você agora.</div>
          <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 2 }}>
            A fila reúne vencimentos, aprovações e rupturas dos módulos que você acessa.
          </div>
        </div>
      </Card>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {itens.map((d, i) => (
        <Link key={d.id} to={d.rota} style={{ textDecoration: 'none' }}>
          <Card
            pad={false}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 14,
              padding: '13px 16px',
              borderLeft: `3px solid ${d.urgencia === 'alta' ? 'var(--accent)' : 'var(--line)'}`,
            }}
          >
            {/* Numerada, como manda o padrão de hub da identidade §9. */}
            <span
              className="num"
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: d.urgencia === 'alta' ? 'var(--accent-ink)' : 'var(--ink-3)',
                width: 18,
                flex: 'none',
              }}
            >
              {String(i + 1).padStart(2, '0')}
            </span>

            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>{d.titulo}</span>
                <span className="num" style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--ink-2)' }}>
                  {d.medida}
                </span>
                {d.urgencia === 'alta' && <Pill kind="accent">agora</Pill>}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 3 }}>{d.detalhe}</div>
            </div>

            <span
              style={{
                fontSize: 10,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                fontWeight: 700,
                color: 'var(--ink-3)',
                flex: 'none',
              }}
            >
              {d.origem}
            </span>
            <ArrowRight size={15} style={{ color: 'var(--ink-3)', flex: 'none' }} />
          </Card>
        </Link>
      ))}
    </div>
  )
}

export function TabDecisoes({ decisoes, temFonte }: { decisoes: Decisao[]; temFonte: boolean }) {
  if (!temFonte) {
    return (
      <Empty>
        A fila de decisão se alimenta dos módulos que você acessa (financeiro, suprimentos, estoque).
        Nenhum deles está disponível para o seu usuário — por isso não há o que listar aqui.
      </Empty>
    )
  }
  return <ListaDecisoes decisoes={decisoes} />
}
