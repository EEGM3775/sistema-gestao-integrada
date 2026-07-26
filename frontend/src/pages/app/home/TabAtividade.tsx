import { Card, Empty, Pill } from '@/components/malha'
import type { FatoRecente } from './useHomeResumo'

/**
 * O feed de **fatos**, não de posts (régua §1.6.1) — o *recently changed items*
 * do Procore e o *Recent Items* do Autodesk Construction Cloud.
 *
 * Cada linha é um evento que de fato aconteceu no banco (um recebimento, uma
 * adjudicação, uma movimentação de estoque), carimbado com o módulo de origem.
 * Nada aqui é gerado no frontend.
 */
function quando(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const diff = Date.now() - d.getTime()
  const min = Math.round(diff / 60_000)
  if (min < 1) return 'agora'
  if (min < 60) return `há ${min} min`
  const h = Math.round(min / 60)
  if (h < 24) return `há ${h} h`
  const dias = Math.round(h / 24)
  if (dias < 30) return `há ${dias} d`
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })
}

export function TabAtividade({ fatos, temFonte }: { fatos: FatoRecente[]; temFonte: boolean }) {
  if (!temFonte)
    return (
      <Empty>
        O feed reúne fatos dos módulos operacionais (suprimentos e estoque). Nenhum deles está
        disponível para o seu usuário.
      </Empty>
    )

  if (fatos.length === 0)
    return <Empty>Nenhum movimento registrado ainda. Os fatos aparecem aqui assim que a operação começar.</Empty>

  return (
    <Card pad={false}>
      {fatos.map((f, i) => (
        <div
          key={f.id}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '12px 16px',
            borderTop: i === 0 ? 'none' : '1px solid var(--line-2)',
          }}
        >
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 550 }}>{f.titulo}</div>
            <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>{f.meta}</div>
          </div>
          <Pill kind="slate">{f.origem}</Pill>
          <span className="num" style={{ fontSize: 11.5, color: 'var(--ink-3)', width: 62, textAlign: 'right', flex: 'none' }}>
            {quando(f.quando)}
          </span>
        </div>
      ))}
    </Card>
  )
}
