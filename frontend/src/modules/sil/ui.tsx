// Kit de UI Malha próprio do SIL (espelha o do SCM). Extraído para as abas
// (operação/gestão/pessoas) compartilharem sem duplicar.
import { type CSSProperties, type ReactNode, type HTMLAttributes, type ButtonHTMLAttributes } from 'react'
import { Inbox } from 'lucide-react'
import type { Kind, Estado } from './lib'

export type Say = (m: string) => void

export const mono: CSSProperties = { fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }
export const CAPS: CSSProperties = { fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }
export const inp: CSSProperties = { width: '100%', padding: '8px 11px', fontSize: 13.5, color: 'var(--ink)', background: 'var(--surface-2)', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', outline: 'none', fontFamily: 'var(--sans)' }
export const errBox: CSSProperties = { background: 'var(--danger-soft)', color: 'var(--danger-ink)', padding: '9px 12px', borderRadius: 'var(--r-sm)', fontSize: 12.5, marginBottom: 12 }

export const KIND: Record<Kind, [string, string]> = {
  slate: ['var(--inset)', 'var(--ink-2)'], info: ['var(--info-soft)', 'var(--info-ink)'], amber: ['var(--accent-soft)', 'var(--accent-ink)'],
  good: ['var(--good-soft)', 'var(--good-ink)'], danger: ['var(--danger-soft)', 'var(--danger-ink)'], net: ['var(--net-soft)', 'var(--net-ink)'],
}

export function Pill({ kind = 'slate', pulse, children }: { kind?: Kind; pulse?: boolean; children: ReactNode }) {
  const [bg, fg] = KIND[kind]
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11.5, fontWeight: 650, padding: '3px 9px', borderRadius: 999, whiteSpace: 'nowrap', lineHeight: 1.4, background: bg, color: fg }}>{pulse && <span className="sil-dot" />}{children}</span>
}
export const EstadoPill = ({ e }: { e: Estado }) => <Pill kind={e.kind} pulse={e.pulse}>{e.label}</Pill>

export function Card({ children, style, pad = true, ...rest }: { children: ReactNode; pad?: boolean } & HTMLAttributes<HTMLDivElement>) {
  return <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', boxShadow: 'var(--shadow-sm)', padding: pad ? 18 : 0, ...style }} {...rest}>{children}</div>
}

export function Btn({ variant = 'ghost', children, style, ...rest }: { variant?: 'primary' | 'ghost' | 'brand' } & ButtonHTMLAttributes<HTMLButtonElement>) {
  const v: Record<string, CSSProperties> = { primary: { background: 'var(--accent)', color: '#1A1204' }, ghost: { background: 'var(--surface)', color: 'var(--ink-2)', border: '1px solid var(--line)' }, brand: { background: 'var(--brand)', color: 'var(--brand-ink)' } }
  return <button {...rest} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 13.5, fontWeight: 650, padding: '9px 15px', borderRadius: 'var(--r-sm)', cursor: rest.disabled ? 'not-allowed' : 'pointer', opacity: rest.disabled ? 0.5 : 1, border: '1px solid transparent', whiteSpace: 'nowrap', ...v[variant], ...style }}>{children}</button>
}

export function SectHead({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '22px 0 12px' }}><h2 style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.02em', textTransform: 'uppercase', color: 'var(--ink-2)' }}>{children}</h2><span style={{ flex: 1, height: 1, background: 'var(--line-2)' }} />{right}</div>
}

export const Spinner = () => <span style={{ width: 26, height: 26, borderRadius: 999, border: '2.5px solid var(--line)', borderTopColor: 'var(--accent)', display: 'inline-block', animation: 'silSpin .8s linear infinite' }} />
export const Loading = () => <div style={{ display: 'grid', placeItems: 'center', padding: 60 }}><Spinner /></div>
export function Empty({ children }: { children: ReactNode }) { return <Card style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, padding: 44, color: 'var(--ink-3)' }}><Inbox size={32} style={{ opacity: 0.7 }} /><span style={{ fontSize: 13, textAlign: 'center' }}>{children}</span></Card> }

// `_h` (o rótulo) entra na assinatura porque `th` é usado como callback de map
// sobre a lista de cabeçalhos; o estilo só depende do índice.
export const th = (_h: string, i: number, right?: (n: number) => boolean): CSSProperties => ({ ...CAPS, fontSize: 10.5, textAlign: right?.(i) ? 'right' : 'left', padding: '11px 16px', borderBottom: '1px solid var(--line)', background: 'var(--surface-2)' })

export function Modal({ title, onClose, children, footer, wide }: { title: string; onClose: () => void; children: ReactNode; footer: ReactNode; wide?: boolean }) {
  return <div onMouseDown={e => { if (e.target === e.currentTarget) onClose() }} style={{ position: 'fixed', inset: 0, zIndex: 90, background: 'rgba(6,14,26,.5)', backdropFilter: 'blur(3px)', display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: '8vh 16px', overflowY: 'auto' }}>
    <div style={{ width: '100%', maxWidth: wide ? 560 : 480, background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', boxShadow: 'var(--shadow-lg)' }}>
      <div style={{ padding: '15px 20px', borderBottom: '1px solid var(--line)', fontFamily: 'var(--display)', fontSize: 16, fontWeight: 700, color: 'var(--ink)' }}>{title}</div>
      <div style={{ padding: 20 }}>{children}</div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 9, padding: '14px 20px', borderTop: '1px solid var(--line)' }}>{footer}</div>
    </div>
  </div>
}
export function Field({ label, children }: { label: string; children: ReactNode }) { return <label style={{ display: 'block', marginBottom: 14 }}><span style={{ display: 'block', ...CAPS, fontSize: 10.5, marginBottom: 5 }}>{label}</span>{children}</label> }

// Drawer lateral para as fichas (item/almoxarifado) — drill-down sem sair da aba.
export function Drawer({ title, onClose, children }: { title: ReactNode; onClose: () => void; children: ReactNode }) {
  return <div onMouseDown={e => { if (e.target === e.currentTarget) onClose() }} style={{ position: 'fixed', inset: 0, zIndex: 88, background: 'rgba(6,14,26,.45)', backdropFilter: 'blur(2px)', display: 'flex', justifyContent: 'flex-end' }}>
    <div className="sil-drawer" style={{ width: 'min(560px,94vw)', height: '100%', background: 'var(--surface)', borderLeft: '1px solid var(--line)', boxShadow: 'var(--shadow-lg)', overflowY: 'auto' }}>
      <div style={{ position: 'sticky', top: 0, background: 'var(--surface)', borderBottom: '1px solid var(--line)', padding: '15px 20px', display: 'flex', alignItems: 'center', gap: 10, zIndex: 2 }}>
        <div style={{ flex: 1, minWidth: 0, fontFamily: 'var(--display)', fontSize: 16, fontWeight: 700, color: 'var(--ink)' }}>{title}</div>
        <button onClick={onClose} style={{ background: 'var(--surface-2)', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', color: 'var(--ink-2)', cursor: 'pointer', padding: '5px 9px', fontSize: 13 }}>Fechar</button>
      </div>
      <div style={{ padding: 20 }}>{children}</div>
    </div>
  </div>
}

export function Info({ k, v, mono: m }: { k: string; v: ReactNode; mono?: boolean }) {
  return <div><div style={{ ...CAPS, fontSize: 10.5, marginBottom: 3 }}>{k}</div><div style={m ? mono : undefined}>{v}</div></div>
}

// Estilos/animações injetados uma vez pela página.
export function SilStyles() {
  return <style>{`
    @keyframes silPulse{0%{transform:scale(.6);opacity:.5}100%{transform:scale(2.2);opacity:0}}
    @keyframes silRise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
    @keyframes silToast{from{opacity:0;transform:translate(-50%,16px)}to{opacity:1;transform:translate(-50%,0)}}
    @keyframes silSpin{to{transform:rotate(360deg)}}
    @keyframes silSlide{from{transform:translateX(24px);opacity:.4}to{transform:none;opacity:1}}
    .sil-screen{animation:silRise .34s cubic-bezier(.2,.7,.2,1) both}
    .sil-drawer{animation:silSlide .28s cubic-bezier(.2,.7,.2,1) both}
    .sil-dot{width:6px;height:6px;border-radius:999px;background:currentColor;position:relative;flex:none;display:inline-block}
    .sil-dot::after{content:"";position:absolute;inset:-3px;border-radius:999px;background:currentColor;opacity:.35;animation:silPulse 2s ease-out infinite}
    .sil-row:hover{background:var(--surface-2)}
    .sil-lift{transition:transform .15s,box-shadow .15s,border-color .15s}
    .sil-lift:hover{transform:translateY(-2px);box-shadow:var(--shadow-md);border-color:color-mix(in srgb,var(--accent) 40%,var(--line))}
    @media(prefers-reduced-motion:reduce){.sil-dot::after,.sil-screen,.sil-drawer,.sil-lift{animation:none;transition:none}}
  `}</style>
}
