// Gráficos do módulo. Paleta validada com scripts/validate_palette.js nos dois
// temas (categórica de 3 e rampa ordinal ABC) — os hexadecimais abaixo não são
// escolha de gosto, passaram nas checagens de banda de luminosidade, croma,
// separação sob daltonismo e contraste contra a superfície.
//
// Formas escolhidas pela pergunta, não pelo enfeite:
// - magnitude por categoria  → barra horizontal de um matiz (não pizza)
// - peso acumulado (ABC)     → Pareto: barras + linha acumulada
// - quatro colunas           → trilho do orçado com marcas sobrepostas
// - previsto × realizado     → duas linhas, uma delas referência tracejada
import { useId, useState, type ReactNode } from 'react'
import { CAPS, mono } from '../ui'
import { brl, brlCurto, pct } from '../lib'

export function GraficoEstilos() {
  return <style>{`
    :root{
      --g-serie-1:#A85F0D; --g-serie-2:#1F62D0; --g-serie-3:#0E8A5F;
      --g-abc-a:#6E4404; --g-abc-b:#A85F0D; --g-abc-c:#E79A22;
      --g-grade:var(--line-2); --g-eixo:var(--ink-3);
    }
    @media (prefers-color-scheme: dark){
      :root{
        --g-serie-1:#C48024; --g-serie-2:#5B90E0; --g-serie-3:#12A374;
        --g-abc-a:#F7C879; --g-abc-b:#F2AC46; --g-abc-c:#B87B25;
      }
    }
    :root[data-theme="light"]{
      --g-serie-1:#A85F0D; --g-serie-2:#1F62D0; --g-serie-3:#0E8A5F;
      --g-abc-a:#6E4404; --g-abc-b:#A85F0D; --g-abc-c:#E79A22;
    }
    :root[data-theme="dark"]{
      --g-serie-1:#C48024; --g-serie-2:#5B90E0; --g-serie-3:#12A374;
      --g-abc-a:#F7C879; --g-abc-b:#F2AC46; --g-abc-c:#B87B25;
    }
    .g-alvo{transition:opacity .12s}
    .g-alvo:hover{opacity:.82}
  `}</style>
}

export const COR_SERIE = ['var(--g-serie-1)', 'var(--g-serie-2)', 'var(--g-serie-3)']
export const COR_ABC: Record<'A' | 'B' | 'C', string> = {
  A: 'var(--g-abc-a)', B: 'var(--g-abc-b)', C: 'var(--g-abc-c)',
}

export function Legenda({ itens }: { itens: { cor: string; rotulo: string; tracejada?: boolean }[] }) {
  return (
    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
      {itens.map(i => (
        <span key={i.rotulo} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: 'var(--ink-3)' }}>
          {i.tracejada
            ? <svg width="16" height="8" aria-hidden><line x1="0" y1="4" x2="16" y2="4" stroke={i.cor} strokeWidth="2" strokeDasharray="4 3" /></svg>
            : <span style={{ width: 10, height: 10, borderRadius: 3, background: i.cor, display: 'inline-block' }} />}
          {i.rotulo}
        </span>
      ))}
    </div>
  )
}

function Dica({ x, y, children }: { x: number; y: number; children: ReactNode }) {
  return (
    <div style={{
      position: 'fixed', left: x + 12, top: y - 8, zIndex: 70, pointerEvents: 'none',
      background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
      boxShadow: 'var(--shadow-md)', padding: '7px 10px', fontSize: 12, color: 'var(--ink)',
      maxWidth: 280, lineHeight: 1.5,
    }}>{children}</div>
  )
}

/** Magnitude por categoria — barras horizontais de um matiz, rotuladas direto. */
export function BarrasHorizontais({ dados, total, cor = 'var(--accent)' }: {
  dados: { rotulo: string; valor: number; apoio?: string }[]
  total: number
  cor?: string
}) {
  const [dica, setDica] = useState<{ x: number; y: number; conteudo: ReactNode } | null>(null)
  const maior = Math.max(...dados.map(d => d.valor), 1)

  return (
    <div style={{ display: 'grid', gap: 9 }}>
      {dados.map(d => {
        const proporcao = (d.valor / maior) * 100
        const share = total > 0 ? (d.valor / total) * 100 : 0
        return (
          <div key={d.rotulo} style={{ display: 'grid', gridTemplateColumns: '124px 1fr 118px', gap: 11, alignItems: 'center' }}>
            <span style={{ fontSize: 12.5, color: 'var(--ink-2)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {d.rotulo}
            </span>
            <div
              className="g-alvo"
              onMouseMove={e => setDica({
                x: e.clientX, y: e.clientY,
                conteudo: <><b>{d.rotulo}</b><br />{brl(d.valor)} · {pct(share, 1)} do total{d.apoio ? <><br />{d.apoio}</> : null}</>,
              })}
              onMouseLeave={() => setDica(null)}
              style={{ height: 18, background: 'var(--inset)', borderRadius: 4, overflow: 'hidden' }}
            >
              <div style={{ width: `${proporcao}%`, height: '100%', background: cor, borderRadius: '0 4px 4px 0' }} />
            </div>
            <span style={{ ...mono, fontSize: 12, color: 'var(--ink)', textAlign: 'right' }}>
              {brlCurto(d.valor)} <span style={{ color: 'var(--ink-3)', fontSize: 11 }}>{pct(share, 0)}</span>
            </span>
          </div>
        )
      })}
      {dica && <Dica x={dica.x} y={dica.y}>{dica.conteudo}</Dica>}
    </div>
  )
}

/** Pareto da curva ABC: barra por item (cor = classe) + linha do acumulado. */
export function Pareto({ itens, altura = 190 }: {
  itens: { rotulo: string; valor: number; acumuladoPct: number; classe: 'A' | 'B' | 'C' }[]
  altura?: number
}) {
  const [dica, setDica] = useState<{ x: number; y: number; conteudo: ReactNode } | null>(null)
  const id = useId()
  if (itens.length === 0) return null

  const maior = Math.max(...itens.map(i => i.valor), 1)
  const largura = 100 / itens.length
  const pontos = itens
    .map((i, n) => `${(n + 0.5) * largura},${100 - i.acumuladoPct}`)
    .join(' ')

  return (
    <div>
      <div style={{ position: 'relative', height: altura }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ width: '100%', height: '100%', display: 'block' }} aria-labelledby={id}>
          <title id={id}>Curva ABC: peso financeiro por item e percentual acumulado</title>
          {[20, 40, 60, 80].map(y => (
            <line key={y} x1="0" y1={y} x2="100" y2={y} stroke="var(--g-grade)" strokeWidth="0.3" vectorEffect="non-scaling-stroke" />
          ))}
          <line x1="0" y1="20" x2="100" y2="20" stroke="var(--ink-3)" strokeWidth="0.6" strokeDasharray="3 2" vectorEffect="non-scaling-stroke" opacity="0.7" />
          {itens.map((i, n) => {
            const h = (i.valor / maior) * 92
            return (
              <rect
                key={n}
                x={n * largura + largura * 0.14}
                y={100 - h}
                width={largura * 0.72}
                height={h}
                fill={COR_ABC[i.classe]}
                rx="0.6"
                className="g-alvo"
                onMouseMove={e => setDica({
                  x: e.clientX, y: e.clientY,
                  conteudo: <><b>{i.rotulo}</b><br />{brl(i.valor)} · classe {i.classe}<br />acumulado {pct(i.acumuladoPct, 1)}</>,
                })}
                onMouseLeave={() => setDica(null)}
              />
            )
          })}
          <polyline points={pontos} fill="none" stroke="var(--ink-2)" strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        </svg>
        <span style={{ position: 'absolute', top: `${20}%`, right: 4, transform: 'translateY(-130%)', ...CAPS, fontSize: 9 }}>80%</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
        <Legenda itens={[
          { cor: COR_ABC.A, rotulo: 'Classe A' },
          { cor: COR_ABC.B, rotulo: 'Classe B' },
          { cor: COR_ABC.C, rotulo: 'Classe C' },
          { cor: 'var(--ink-2)', rotulo: '% acumulado' },
        ]} />
      </div>
      {dica && <Dica x={dica.x} y={dica.y}>{dica.conteudo}</Dica>}
    </div>
  )
}

/** Trilho das quatro colunas: o orçado é a pista, o resto são marcas sobre ela. */
export function TrilhoQuatroColunas({ orcado, comprometido, aplicado, realizado }: {
  orcado: number | null; comprometido: number; aplicado: number; realizado: number
}) {
  const [dica, setDica] = useState<{ x: number; y: number; conteudo: ReactNode } | null>(null)
  const teto = Math.max(orcado ?? 0, comprometido, aplicado, realizado, 1)
  const largura = (v: number) => `${Math.min((v / teto) * 100, 100)}%`
  const estourou = orcado !== null && comprometido > orcado

  const marca = (valor: number, cor: string, rotulo: string, indice: number) => (
    <div
      className="g-alvo"
      onMouseMove={e => setDica({
        x: e.clientX, y: e.clientY,
        conteudo: <><b>{rotulo}</b><br />{brl(valor)}{orcado ? <><br />{pct((valor / orcado) * 100, 1)} do orçado</> : null}</>,
      })}
      onMouseLeave={() => setDica(null)}
      style={{
        position: 'absolute', left: 0, top: 3 + indice * 8, height: 6,
        width: largura(valor), background: cor, borderRadius: '0 3px 3px 0',
        boxShadow: '0 0 0 1.5px var(--surface)',
      }}
    />
  )

  return (
    <div style={{ minWidth: 190 }}>
      <div style={{
        position: 'relative', height: 28, background: 'var(--inset)', borderRadius: 4,
        border: estourou ? '1px solid var(--danger)' : '1px solid transparent',
      }}>
        {marca(comprometido, COR_SERIE[0], 'Comprometido (pedidos do SCM)', 0)}
        {marca(aplicado, COR_SERIE[1], 'Aplicado (consumo do SIL)', 1)}
        {marca(realizado, COR_SERIE[2], 'Realizado (pago no ERP)', 2)}
        {orcado !== null && (
          <span
            title={`Orçado: ${brl(orcado)}`}
            style={{
              position: 'absolute', left: largura(orcado), top: -2, bottom: -2, width: 2,
              background: 'var(--ink)', borderRadius: 1,
            }}
          />
        )}
      </div>
      {dica && <Dica x={dica.x} y={dica.y}>{dica.conteudo}</Dica>}
    </div>
  )
}

/** Curva S: previsto acumulado (referência tracejada) × realizado acumulado. */
export function CurvaSGrafico({ serie, altura = 220 }: {
  serie: { competencia: string; previstoPct: number; realizadoPct: number; previsto: number; realizado: number }[]
  altura?: number
}) {
  const [dica, setDica] = useState<{ x: number; y: number; conteudo: ReactNode } | null>(null)
  const [foco, setFoco] = useState<number | null>(null)
  const id = useId()
  if (serie.length === 0) return null

  const passo = serie.length > 1 ? 100 / (serie.length - 1) : 100
  const caminho = (chave: 'previstoPct' | 'realizadoPct') =>
    serie.map((p, n) => `${n === 0 ? 'M' : 'L'}${n * passo},${100 - p[chave]}`).join(' ')

  return (
    <div>
      <div style={{ position: 'relative', height: altura }}>
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          style={{ width: '100%', height: '100%', display: 'block' }}
          aria-labelledby={id}
          onMouseLeave={() => { setFoco(null); setDica(null) }}
          onMouseMove={e => {
            const caixa = e.currentTarget.getBoundingClientRect()
            const razao = (e.clientX - caixa.left) / caixa.width
            const n = Math.max(0, Math.min(serie.length - 1, Math.round(razao * (serie.length - 1))))
            setFoco(n)
            const p = serie[n]
            setDica({
              x: e.clientX, y: e.clientY,
              conteudo: (
                <>
                  <b>{p.competencia}</b><br />
                  previsto {pct(p.previstoPct, 1)} · {brl(p.previsto)}<br />
                  realizado {pct(p.realizadoPct, 1)} · {brl(p.realizado)}
                </>
              ),
            })
          }}
        >
          <title id={id}>Curva S: percentual acumulado previsto contra realizado</title>
          {[25, 50, 75].map(y => (
            <line key={y} x1="0" y1={y} x2="100" y2={y} stroke="var(--g-grade)" strokeWidth="0.3" vectorEffect="non-scaling-stroke" />
          ))}
          <path d={caminho('previstoPct')} fill="none" stroke="var(--ink-3)" strokeWidth="2" strokeDasharray="5 4" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          <path d={caminho('realizadoPct')} fill="none" stroke="var(--accent)" strokeWidth="2.5" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          {foco !== null && (
            <line x1={foco * passo} y1="0" x2={foco * passo} y2="100" stroke="var(--ink-3)" strokeWidth="1" vectorEffect="non-scaling-stroke" opacity="0.55" />
          )}
        </svg>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5, ...CAPS, fontSize: 9.5 }}>
        <span>{serie[0]?.competencia}</span>
        <span>{serie[serie.length - 1]?.competencia}</span>
      </div>
      <div style={{ marginTop: 8 }}>
        <Legenda itens={[
          { cor: 'var(--ink-3)', rotulo: 'Previsto acumulado', tracejada: true },
          { cor: 'var(--accent)', rotulo: 'Realizado acumulado' },
        ]} />
      </div>
      {dica && <Dica x={dica.x} y={dica.y}>{dica.conteudo}</Dica>}
    </div>
  )
}
