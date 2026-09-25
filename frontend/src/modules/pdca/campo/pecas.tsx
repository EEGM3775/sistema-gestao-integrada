import { useEffect, useMemo, type CSSProperties, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Camera, Check, ChevronLeft, X } from 'lucide-react'
import { useObras } from '../hooks'
import { campoGrande } from '../estilos'

/** As peças da superfície de campo — **alvo de dedo com luva**: nada menor
 *  que 48 px, fonte de 16 px nos campos (abaixo disso o celular dá zoom ao
 *  focar), e uma decisão por tela. */


export function VoltarParaFrente({ rotulo = 'Minha frente', para = '/campo' }: { rotulo?: string; para?: string }) {
  const navigate = useNavigate()
  return (
    <button
      type="button"
      onClick={() => navigate(para)}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 5, alignSelf: 'flex-start',
        minHeight: 44, padding: '0 4px', background: 'none', border: 'none',
        cursor: 'pointer', color: 'var(--ink-3)', fontSize: 13.5, fontFamily: 'inherit',
      }}
    >
      <ChevronLeft size={17} />
      {rotulo}
    </button>
  )
}

export function Titulo({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <header>
      <h1 style={{ fontSize: 20, fontWeight: 750, color: 'var(--ink)', lineHeight: 1.3, margin: 0 }}>
        {children}
      </h1>
      {sub && <div style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 4 }}>{sub}</div>}
    </header>
  )
}

export function Aviso({ tom, children }: { tom: 'danger' | 'good' | 'accent'; children: ReactNode }) {
  if (!children) return null
  return (
    <div
      role={tom === 'danger' ? 'alert' : 'status'}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 9, padding: '13px 14px',
        borderRadius: 'var(--r-md)', background: `var(--${tom}-soft)`,
        color: `var(--${tom}-ink)`, fontSize: 14, lineHeight: 1.55,
      }}
    >
      {tom === 'good' && <Check size={19} style={{ flexShrink: 0 }} />}
      <span>{children}</span>
    </div>
  )
}

export function Cartao({ children }: { children: ReactNode }) {
  return (
    <section
      style={{
        background: 'var(--surface)', border: '1px solid var(--line)',
        borderRadius: 'var(--r-md)', padding: 16,
        display: 'flex', flexDirection: 'column', gap: 14,
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      {children}
    </section>
  )
}

export function Rotulado({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 14, fontWeight: 650, color: 'var(--ink)' }}>{rotulo}</span>
      {children}
    </label>
  )
}

/** Um grupo de botões de escolha — `fieldset`, e não `label`: tocar no texto
 *  de um `label` aciona o primeiro controle dentro dele, e aqui isso escolheria
 *  a primeira opção sem a pessoa pedir. */
export function Conjunto({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <fieldset style={{ border: 'none', padding: 0, margin: 0, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <legend style={{ fontSize: 14, fontWeight: 650, color: 'var(--ink)', padding: 0, marginBottom: 6 }}>
        {rotulo}
      </legend>
      {children}
    </fieldset>
  )
}

export function BotaoGrande({
  children, onClick, disabled, tom = 'accent',
}: {
  children: ReactNode
  onClick: () => void
  disabled?: boolean
  tom?: 'accent' | 'danger' | 'neutro'
}) {
  const cores: Record<string, CSSProperties> = {
    accent: { background: 'var(--accent)', color: '#1A1204', border: 'none' },
    danger: { background: 'var(--danger-soft)', color: 'var(--danger-ink)', border: '1px solid var(--danger-ink)' },
    neutro: { background: 'var(--surface-2)', color: 'var(--ink-2)', border: '1px solid var(--line)' },
  }
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        width: '100%', minHeight: 56, borderRadius: 12,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
        fontSize: 17, fontWeight: 750, fontFamily: 'inherit',
        cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.55 : 1,
        ...cores[tom],
      }}
    >
      {children}
    </button>
  )
}

/** A câmera de trás, direto — no canteiro o que se quer é fotografar o
 *  serviço, e não escolher um arquivo. */
export function BotaoDaCamera({
  foto, aoMudar, rotulo = 'Tirar foto', grande,
}: {
  foto: File | null
  aoMudar: (f: File | null) => void
  rotulo?: string
  grande?: boolean
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
      <label
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          gap: 8, minHeight: grande ? 120 : 48, padding: '0 16px', borderRadius: grande ? 14 : 10,
          border: grande ? '2px dashed var(--line)' : '1px solid var(--line)',
          background: 'var(--surface-2)', color: 'var(--ink-2)',
          fontSize: grande ? 17 : 14.5, fontWeight: 650, cursor: 'pointer',
          flex: grande ? '1 1 100%' : '0 0 auto',
        }}
      >
        <Camera size={grande ? 26 : 18} />
        {foto ? 'Trocar foto' : rotulo}
        <input
          type="file"
          accept="image/*"
          capture="environment"
          onChange={(e) => aoMudar(e.target.files?.[0] ?? null)}
          style={{ display: 'none' }}
        />
      </label>
      {foto && (
        <button
          type="button"
          onClick={() => aoMudar(null)}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 5, minHeight: 44,
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--ink-3)', fontSize: 13, fontFamily: 'inherit', minWidth: 0,
          }}
        >
          <X size={15} />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 200 }}>
            {foto.name}
          </span>
        </button>
      )}
    </div>
  )
}

/** Em qual obra. O campo não vive dentro de uma obra — o mestre que cobre duas
 *  escolhe —, mas quem só tem uma não deveria ver a pergunta. */
export function EscolhaDeObra({
  valor, aoMudar,
}: { valor: number | null; aoMudar: (id: number | null) => void }) {
  const obras = useObras()
  const lista = useMemo(() => obras.data ?? [], [obras.data])

  useEffect(() => {
    if (valor == null && lista.length === 1) aoMudar(lista[0].obra_id)
  }, [valor, lista, aoMudar])

  if (lista.length === 1 && valor === lista[0].obra_id) return null

  return (
    <Rotulado rotulo="Em qual obra">
      <select
        value={valor ?? ''}
        onChange={(e) => aoMudar(e.target.value ? Number(e.target.value) : null)}
        style={campoGrande}
        disabled={obras.isLoading}
      >
        <option value="">{obras.isLoading ? 'Carregando…' : 'Escolha a obra'}</option>
        {lista.map((o) => (
          <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>
        ))}
      </select>
    </Rotulado>
  )
}
