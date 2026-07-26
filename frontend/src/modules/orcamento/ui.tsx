// Kit Malha do Orçamento. Mais denso que o dos outros módulos de propósito: o
// orçamentista passa horas numa grade de centenas de linhas, e cada pixel de
// chrome é linha de planilha que sai da tela.
import { type ButtonHTMLAttributes, type CSSProperties, type HTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'
import { Inbox, Lock } from 'lucide-react'
import type { Kind } from './lib'

export const mono: CSSProperties = { fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }
export const CAPS: CSSProperties = {
  fontSize: 10.5, letterSpacing: '0.07em', textTransform: 'uppercase',
  color: 'var(--ink-3)', fontWeight: 700,
}
export const inp: CSSProperties = {
  width: '100%', padding: '7px 10px', fontSize: 13, color: 'var(--ink)',
  background: 'var(--surface-2)', border: '1px solid var(--line)',
  borderRadius: 'var(--r-sm)', outline: 'none', fontFamily: 'var(--sans)',
}
export const errBox: CSSProperties = {
  background: 'var(--danger-soft)', color: 'var(--danger-ink)', padding: '9px 12px',
  borderRadius: 'var(--r-sm)', fontSize: 12.5, marginBottom: 12,
}

export const KIND: Record<Kind, [string, string]> = {
  slate: ['var(--inset)', 'var(--ink-2)'],
  info: ['var(--info-soft)', 'var(--info-ink)'],
  amber: ['var(--accent-soft)', 'var(--accent-ink)'],
  good: ['var(--good-soft)', 'var(--good-ink)'],
  danger: ['var(--danger-soft)', 'var(--danger-ink)'],
  net: ['var(--net-soft)', 'var(--net-ink)'],
}

export function Pill({ kind = 'slate', pulse, children, title }: {
  kind?: Kind; pulse?: boolean; children: ReactNode; title?: string
}) {
  const [bg, fg] = KIND[kind]
  return (
    <span title={title} style={{
      display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 650,
      padding: '2px 8px', borderRadius: 999, whiteSpace: 'nowrap', lineHeight: 1.45,
      background: bg, color: fg,
    }}>
      {pulse && <span className="orc-dot" />}{children}
    </span>
  )
}

export function Card({ children, style, pad = true, ...rest }: {
  children: ReactNode; pad?: boolean
} & HTMLAttributes<HTMLDivElement>) {
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)',
      boxShadow: 'var(--shadow-sm)', padding: pad ? 18 : 0, ...style,
    }} {...rest}>{children}</div>
  )
}

export function Btn({ variant = 'ghost', tam = 'md', children, style, ...rest }: {
  variant?: 'primary' | 'ghost' | 'brand' | 'perigo'; tam?: 'sm' | 'md'
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  const v: Record<string, CSSProperties> = {
    primary: { background: 'var(--accent)', color: '#1A1204' },
    ghost: { background: 'var(--surface)', color: 'var(--ink-2)', border: '1px solid var(--line)' },
    brand: { background: 'var(--brand)', color: 'var(--brand-ink)' },
    perigo: { background: 'var(--danger-soft)', color: 'var(--danger-ink)', border: '1px solid var(--danger-soft)' },
  }
  const t: Record<string, CSSProperties> = {
    sm: { fontSize: 12, padding: '5px 10px', gap: 5 },
    md: { fontSize: 13, padding: '8px 14px', gap: 7 },
  }
  return (
    <button {...rest} style={{
      display: 'inline-flex', alignItems: 'center', fontWeight: 650, borderRadius: 'var(--r-sm)',
      cursor: rest.disabled ? 'not-allowed' : 'pointer', opacity: rest.disabled ? 0.5 : 1,
      border: '1px solid transparent', whiteSpace: 'nowrap', ...t[tam], ...v[variant], ...style,
    }}>{children}</button>
  )
}

/** Seletor horizontal — o nível 2 da navegação, dentro de cada página. */
export function Seletor<T extends string>({ valor, onChange, opcoes, compacto }: {
  valor: T
  onChange: (v: T) => void
  opcoes: { valor: T; rotulo: string; icone?: ReactNode; travado?: boolean; motivo?: string }[]
  compacto?: boolean
}) {
  return (
    <div style={{
      display: 'inline-flex', gap: 2, padding: 2, background: 'var(--inset)',
      border: '1px solid var(--line)', borderRadius: 999,
    }}>
      {opcoes.map(o => {
        const ativo = o.valor === valor
        return (
          <button
            key={o.valor}
            onClick={() => !o.travado && onChange(o.valor)}
            title={o.travado ? o.motivo : undefined}
            disabled={o.travado}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, border: 'none',
              padding: compacto ? '4px 11px' : '6px 14px', borderRadius: 999,
              fontSize: compacto ? 12 : 12.5, fontWeight: 650, whiteSpace: 'nowrap',
              cursor: o.travado ? 'not-allowed' : 'pointer',
              opacity: o.travado ? 0.5 : 1,
              background: ativo ? 'var(--surface)' : 'transparent',
              color: ativo ? 'var(--ink)' : 'var(--ink-3)',
              boxShadow: ativo ? 'var(--shadow-sm)' : 'none',
              transition: 'background .15s, color .15s',
            }}
          >
            {o.travado ? <Lock size={12} /> : o.icone}{o.rotulo}
          </button>
        )
      })}
    </div>
  )
}

export function Select({ children, style, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} style={{
      padding: '6px 26px 6px 10px', fontSize: 12.5, fontWeight: 600, color: 'var(--ink)',
      background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
      outline: 'none', cursor: 'pointer', appearance: 'none',
      backgroundImage: 'linear-gradient(45deg,transparent 50%,currentColor 50%),linear-gradient(135deg,currentColor 50%,transparent 50%)',
      backgroundPosition: 'right 12px center,right 7px center',
      backgroundSize: '5px 5px,5px 5px', backgroundRepeat: 'no-repeat',
      maxWidth: 260, textOverflow: 'ellipsis', ...style,
    }}>{children}</select>
  )
}

export function Num({ children, forte, tom, tam = 13 }: {
  children: ReactNode; forte?: boolean; tom?: string; tam?: number
}) {
  return <span style={{ ...mono, fontSize: tam, fontWeight: forte ? 700 : 500, color: tom ?? 'inherit' }}>{children}</span>
}

export function Kpi({ rotulo, valor, apoio, tom, largura }: {
  rotulo: string; valor: ReactNode; apoio?: ReactNode; tom?: string; largura?: number
}) {
  return (
    <div style={{ minWidth: largura ?? 132 }}>
      <div style={{ ...CAPS, marginBottom: 4 }}>{rotulo}</div>
      <div style={{ ...mono, fontSize: 20, fontWeight: 700, color: tom ?? 'var(--ink)', lineHeight: 1.15 }}>{valor}</div>
      {apoio && <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 3 }}>{apoio}</div>}
    </div>
  )
}

export function SectHead({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '20px 0 11px' }}>
      <h2 style={{ ...CAPS, fontSize: 11.5, color: 'var(--ink-2)' }}>{children}</h2>
      <span style={{ flex: 1, height: 1, background: 'var(--line-2)' }} />
      {right}
    </div>
  )
}

export const Spinner = () => (
  <span style={{
    width: 24, height: 24, borderRadius: 999, border: '2.5px solid var(--line)',
    borderTopColor: 'var(--accent)', display: 'inline-block', animation: 'orcSpin .8s linear infinite',
  }} />
)
export const Loading = ({ texto }: { texto?: string }) => (
  <div style={{ display: 'grid', placeItems: 'center', gap: 12, padding: 56, color: 'var(--ink-3)', fontSize: 13 }}>
    <Spinner />{texto}
  </div>
)

export function Empty({ children, acao }: { children: ReactNode; acao?: ReactNode }) {
  return (
    <Card style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: 44, color: 'var(--ink-3)' }}>
      <Inbox size={30} style={{ opacity: 0.65 }} />
      <span style={{ fontSize: 13, textAlign: 'center', maxWidth: 460, lineHeight: 1.55 }}>{children}</span>
      {acao}
    </Card>
  )
}

export function Modal({ titulo, onClose, children, rodape, largura = 520 }: {
  titulo: ReactNode; onClose: () => void; children: ReactNode; rodape?: ReactNode; largura?: number
}) {
  return (
    <div
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 92, background: 'rgba(6,14,26,.5)', backdropFilter: 'blur(3px)',
        display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: '7vh 16px', overflowY: 'auto',
      }}
    >
      <div className="orc-modal" style={{
        width: '100%', maxWidth: largura, background: 'var(--surface)', border: '1px solid var(--line)',
        borderRadius: 'var(--r-lg)', boxShadow: 'var(--shadow-lg)',
      }}>
        <div style={{
          padding: '14px 19px', borderBottom: '1px solid var(--line)', fontFamily: 'var(--display)',
          fontSize: 15.5, fontWeight: 700, color: 'var(--ink)',
        }}>{titulo}</div>
        <div style={{ padding: 19 }}>{children}</div>
        {rodape && (
          <div style={{
            display: 'flex', justifyContent: 'flex-end', gap: 9, padding: '13px 19px',
            borderTop: '1px solid var(--line)',
          }}>{rodape}</div>
        )}
      </div>
    </div>
  )
}

export function Drawer({ titulo, onClose, children, largura = 620 }: {
  titulo: ReactNode; onClose: () => void; children: ReactNode; largura?: number
}) {
  return (
    <div
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 90, background: 'rgba(6,14,26,.45)', backdropFilter: 'blur(2px)',
        display: 'flex', justifyContent: 'flex-end',
      }}
    >
      <div className="orc-drawer" style={{
        width: `min(${largura}px,95vw)`, height: '100%', background: 'var(--surface)',
        borderLeft: '1px solid var(--line)', boxShadow: 'var(--shadow-lg)', overflowY: 'auto',
      }}>
        <div style={{
          position: 'sticky', top: 0, background: 'var(--surface)', borderBottom: '1px solid var(--line)',
          padding: '14px 19px', display: 'flex', alignItems: 'center', gap: 10, zIndex: 2,
        }}>
          <div style={{ flex: 1, minWidth: 0, fontFamily: 'var(--display)', fontSize: 15.5, fontWeight: 700, color: 'var(--ink)' }}>
            {titulo}
          </div>
          <Btn tam="sm" onClick={onClose}>Fechar</Btn>
        </div>
        <div style={{ padding: 19 }}>{children}</div>
      </div>
    </div>
  )
}

export function Field({ label, children, dica }: { label: string; children: ReactNode; dica?: string }) {
  return (
    <label style={{ display: 'block', marginBottom: 13 }}>
      <span style={{ display: 'block', ...CAPS, marginBottom: 5 }}>{label}</span>
      {children}
      {dica && <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)', marginTop: 4 }}>{dica}</span>}
    </label>
  )
}

export function Info({ k, v, m }: { k: string; v: ReactNode; m?: boolean }) {
  return (
    <div>
      <div style={{ ...CAPS, marginBottom: 3 }}>{k}</div>
      <div style={{ fontSize: 13, color: 'var(--ink)', ...(m ? mono : {}) }}>{v}</div>
    </div>
  )
}

/** Aviso de dado que ainda não existe — nunca inventar número no lugar. */
export function EmBreve({ children }: { children: ReactNode }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: 'var(--ink-3)',
      background: 'var(--inset)', border: '1px dashed var(--line)', borderRadius: 'var(--r-sm)', padding: '3px 9px',
    }}>{children}</span>
  )
}

export function Aviso({ tom = 'info', children }: { tom?: 'info' | 'amber' | 'danger'; children: ReactNode }) {
  const cores: Record<string, [string, string]> = {
    info: ['var(--info-soft)', 'var(--info-ink)'],
    amber: ['var(--accent-soft)', 'var(--accent-ink)'],
    danger: ['var(--danger-soft)', 'var(--danger-ink)'],
  }
  const [bg, fg] = cores[tom]
  return (
    <div style={{
      background: bg, color: fg, padding: '10px 13px', borderRadius: 'var(--r-sm)',
      fontSize: 12.5, lineHeight: 1.55, display: 'flex', gap: 9, alignItems: 'flex-start',
    }}>{children}</div>
  )
}

export function OrcStyles() {
  return <style>{`
    @keyframes orcPulse{0%{transform:scale(.6);opacity:.5}100%{transform:scale(2.2);opacity:0}}
    @keyframes orcRise{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}
    @keyframes orcSpin{to{transform:rotate(360deg)}}
    @keyframes orcSlide{from{transform:translateX(22px);opacity:.4}to{transform:none;opacity:1}}
    @keyframes orcPop{from{opacity:0;transform:scale(.97)}to{opacity:1;transform:none}}
    @keyframes orcToast{from{opacity:0;transform:translate(-50%,14px)}to{opacity:1;transform:translate(-50%,0)}}
    .orc-tela{animation:orcRise .3s cubic-bezier(.2,.7,.2,1) both}
    .orc-drawer{animation:orcSlide .26s cubic-bezier(.2,.7,.2,1) both}
    .orc-modal{animation:orcPop .18s cubic-bezier(.2,.7,.2,1) both}
    .orc-dot{width:6px;height:6px;border-radius:999px;background:currentColor;position:relative;flex:none;display:inline-block}
    .orc-dot::after{content:"";position:absolute;inset:-3px;border-radius:999px;background:currentColor;opacity:.35;animation:orcPulse 2s ease-out infinite}
    .orc-lift{transition:transform .15s,box-shadow .15s,border-color .15s}
    .orc-lift:hover{transform:translateY(-2px);box-shadow:var(--shadow-md);border-color:color-mix(in srgb,var(--accent) 42%,var(--line))}
    .orc-linha:hover{background:var(--surface-2)}
    .orc-cel{outline:none}
    .orc-cel:focus-visible{box-shadow:inset 0 0 0 2px var(--accent);border-radius:3px}
    .orc-grade::-webkit-scrollbar{width:11px;height:11px}
    .orc-grade::-webkit-scrollbar-thumb{background:var(--line);border-radius:99px;border:3px solid var(--surface)}
    .orc-grade::-webkit-scrollbar-track{background:var(--surface)}
    @media(prefers-reduced-motion:reduce){.orc-dot::after,.orc-tela,.orc-drawer,.orc-modal,.orc-lift{animation:none;transition:none}}
  `}</style>
}
