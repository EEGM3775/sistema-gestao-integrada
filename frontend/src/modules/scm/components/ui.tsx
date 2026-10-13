/* Primitivos Malha do Suprimentos — os da página, num lugar só, para a página e
 * os componentes do pedido (PedidoDetalhe, FichaItem) falarem a mesma língua. */
import type { CSSProperties, ReactNode, HTMLAttributes, ButtonHTMLAttributes } from 'react'
import { Inbox, Star } from 'lucide-react'
import type { Kind, Estado } from '../lib'
import { CAPS, KIND, mono } from './estilo'

export function Pill({ kind = 'slate', pulse, children }: { kind?: Kind; pulse?: boolean; children: ReactNode }) {
  const [bg, fg] = KIND[kind]
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11.5, fontWeight: 650, padding: '3px 9px', borderRadius: 999, whiteSpace: 'nowrap', lineHeight: 1.4, background: bg, color: fg }}>{pulse && <span className="scm-dot" />}{children}</span>
}
export const EstadoPill = ({ e }: { e: Estado }) => <Pill kind={e.kind} pulse={e.pulse}>{e.label}</Pill>
export function Card({ children, style, pad = true, ...rest }: { children: ReactNode; pad?: boolean } & HTMLAttributes<HTMLDivElement>) {
  return <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', boxShadow: 'var(--shadow-sm)', padding: pad ? 18 : 0, ...style }} {...rest}>{children}</div>
}
const CONN = new Set(['de', 'do', 'da', 'dos', 'das', 'e'])
function iniciais(n: string) { const p = n.trim().split(/\s+/).filter(w => !CONN.has(w.toLowerCase())); const s = p.length ? p : n.trim().split(/\s+/); return ((s[0]?.[0] ?? '') + (s[1]?.[0] ?? '')).toUpperCase() }
const AV: [string, string][] = [['var(--info-soft)', 'var(--info-ink)'], ['var(--accent-soft)', 'var(--accent-ink)'], ['var(--good-soft)', 'var(--good-ink)'], ['var(--net-soft)', 'var(--net-ink)']]
function avColor(s: string) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return AV[h % AV.length] }
export function Avatar({ name, size = 26 }: { name: string; size?: number }) { const [bg, fg] = avColor(name || '?'); return <span style={{ width: size, height: size, borderRadius: Math.round(size * 0.27), flex: 'none', display: 'grid', placeItems: 'center', background: bg, color: fg, fontFamily: 'var(--mono)', fontWeight: 700, fontSize: Math.round(size * 0.42) }}>{iniciais(name || '?')}</span> }
export function Btn({ variant = 'ghost', children, style, ...rest }: { variant?: 'primary' | 'ghost' | 'brand' | 'danger' } & ButtonHTMLAttributes<HTMLButtonElement>) {
  const v: Record<string, CSSProperties> = { primary: { background: 'var(--accent)', color: '#1A1204' }, ghost: { background: 'var(--surface)', color: 'var(--ink-2)', border: '1px solid var(--line)' }, brand: { background: 'var(--brand)', color: 'var(--brand-ink)' }, danger: { background: 'var(--surface)', color: 'var(--danger-ink)', border: '1px solid color-mix(in srgb,var(--danger) 40%,var(--line))' } }
  return <button {...rest} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 13.5, fontWeight: 650, padding: '9px 15px', borderRadius: 'var(--r-sm)', cursor: rest.disabled ? 'not-allowed' : 'pointer', opacity: rest.disabled ? 0.5 : 1, border: '1px solid transparent', whiteSpace: 'nowrap', ...v[variant], ...style }}>{children}</button>
}
export function SectHead({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '22px 0 12px' }}><h2 style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.02em', textTransform: 'uppercase', color: 'var(--ink-2)' }}>{children}</h2><span style={{ flex: 1, height: 1, background: 'var(--line-2)' }} />{right}</div>
}
const Spinner = () => <span style={{ width: 26, height: 26, borderRadius: 999, border: '2.5px solid var(--line)', borderTopColor: 'var(--accent)', display: 'inline-block', animation: 'scmSpin .8s linear infinite' }} />
export const Loading = () => <div style={{ display: 'grid', placeItems: 'center', padding: 60 }}><Spinner /></div>
export function Empty({ children }: { children: ReactNode }) { return <Card style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, padding: 44, color: 'var(--ink-3)' }}><Inbox size={32} style={{ opacity: 0.7 }} /><span style={{ fontSize: 13, textAlign: 'center' }}>{children}</span></Card> }

export function Modal({ title, onClose, children, footer, largura = 480 }: { title: string; onClose: () => void; children: ReactNode; footer: ReactNode; largura?: number }) {
  return <div onMouseDown={e => { if (e.target === e.currentTarget) onClose() }} style={{ position: 'fixed', inset: 0, zIndex: 90, background: 'rgba(6,14,26,.5)', backdropFilter: 'blur(3px)', display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '3vh 16px' }}>
    {/* A janela manda: o modal cresce até `largura`, nunca passa da tela, e o miolo rola com título e botões sempre à vista. */}
    <div style={{ width: '100%', maxWidth: largura, maxHeight: '94vh', display: 'flex', flexDirection: 'column', background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', boxShadow: 'var(--shadow-lg)' }}>
      <div style={{ flex: 'none', padding: '15px 20px', borderBottom: '1px solid var(--line)', fontFamily: 'var(--display)', fontSize: 16, fontWeight: 700, color: 'var(--ink)' }}>{title}</div>
      <div style={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', padding: 20 }}>{children}</div>
      <div style={{ flex: 'none', display: 'flex', justifyContent: 'flex-end', gap: 9, padding: '14px 20px', borderTop: '1px solid var(--line)', flexWrap: 'wrap' }}>{footer}</div>
    </div>
  </div>
}
export function Field({ label, children }: { label: string; children: ReactNode }) { return <label style={{ display: 'block', marginBottom: 14 }}><span style={{ display: 'block', ...CAPS, fontSize: 10.5, marginBottom: 5 }}>{label}</span>{children}</label> }
export function Info({ k, v, mono: m }: { k: string; v: ReactNode; mono?: boolean }) { return <div><div style={{ ...CAPS, fontSize: 10.5, marginBottom: 3 }}>{k}</div><div style={m ? mono : undefined}>{v}</div></div> }
export function Nota({ k, v }: { k: string; v: number }) { return <div><div style={{ ...CAPS, fontSize: 10.5, marginBottom: 4 }}>{k}</div><div style={{ display: 'flex', gap: 2 }}>{[1, 2, 3, 4, 5].map(n => <Star key={n} size={15} style={{ color: n <= v ? 'var(--accent)' : 'var(--line)', fill: n <= v ? 'var(--accent)' : 'none' }} />)}</div></div> }
export function Erro({ msg }: { msg: string }) {
  return msg ? <div role="alert" style={{ background: 'var(--danger-soft)', color: 'var(--danger-ink)', padding: '9px 12px', borderRadius: 'var(--r-sm)', fontSize: 12.5, marginBottom: 12 }}>{msg}</div> : null
}

