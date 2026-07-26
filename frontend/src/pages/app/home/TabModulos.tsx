import { Link } from 'react-router-dom'
import { ArrowRight, Lock } from 'lucide-react'
import { Card, Pill, SectionHead } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { acessoDoModulo, CATALOGO, ESTAGIOS, ORDEM_ESTAGIOS, type ModuloDef } from './catalogo'

/**
 * O lançador de módulos — equivalente ao *App Launcher* do Salesforce e às
 * *spaces/pages* do SAP Fiori Launchpad, mas agrupado pelo **endereço no ciclo**
 * (identidade §9) em vez de por "base × pago". O usuário vê a plataforma inteira
 * como uma cidade, e cada módulo declara em que estágio ele vive.
 *
 * **Nada é escondido** (farol da edição, §3.2): o que o usuário não pode abrir
 * aparece travado com o motivo. Esconder faria a plataforma parecer menor do que
 * é e transformaria "não contratado" em "não existe".
 */
function ModuloCard({ m }: { m: ModuloDef }) {
  const { hasModule, isTenantAdmin } = useAuth()
  const acesso = acessoDoModulo(m, hasModule, isTenantAdmin)
  const Icon = m.icon
  const cor = ESTAGIOS[m.estagio].cor

  const corpo = (
    <Card
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        height: '100%',
        opacity: acesso.pode ? 1 : 0.78,
      }}
      title={acesso.pode ? undefined : acesso.motivo}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <span
          style={{
            width: 34,
            height: 34,
            borderRadius: 'var(--r-sm)',
            display: 'grid',
            placeItems: 'center',
            flex: 'none',
            // Superfície tingida pelo estágio — a cor viva vale para superfície,
            // nunca para o texto (identidade §5.3).
            background: `color-mix(in srgb, ${cor} 14%, var(--surface-2))`,
            color: cor,
          }}
        >
          <Icon size={17} strokeWidth={1.9} />
        </span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 13.5, fontWeight: 650, color: 'var(--ink)', lineHeight: 1.25 }}>{m.label}</div>
          <div style={{ display: 'flex', gap: 5, marginTop: 5, flexWrap: 'wrap' }}>
            {!m.modulo && m.situacao === 'pronto' && <Pill kind="good">incluso</Pill>}
            {m.situacao === 'backend' && <Pill kind="info">tela em construção</Pill>}
            {m.situacao === 'planejado' && <Pill kind="slate">planejado</Pill>}
            {m.horizonte && <Pill kind="net">{m.horizonte}</Pill>}
            {m.adminOnly && <Pill kind="slate">admin</Pill>}
          </div>
        </div>
        {!acesso.pode && <Lock size={13} style={{ color: 'var(--ink-3)', flex: 'none' }} />}
      </div>

      <p style={{ fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.5, flex: 1 }}>{m.descricao}</p>

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11.5, fontWeight: 600 }}>
        {acesso.pode ? (
          <span style={{ color: 'var(--brand)', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            Abrir <ArrowRight size={13} />
          </span>
        ) : (
          <span style={{ color: 'var(--ink-3)' }}>{acesso.motivo}</span>
        )}
      </div>
    </Card>
  )

  if (!acesso.pode || !m.rota) return corpo
  return (
    <Link to={m.rota} style={{ textDecoration: 'none', display: 'block', height: '100%' }}>
      {corpo}
    </Link>
  )
}

export function TabModulos() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 26 }}>
      {ORDEM_ESTAGIOS.map((est) => {
        const mods = CATALOGO.filter((m) => m.estagio === est)
        if (mods.length === 0) return null
        const meta = ESTAGIOS[est]
        return (
          <section key={est}>
            <SectionHead estagio={meta.cor} sub={meta.sub}>
              {meta.label}
            </SectionHead>
            <div
              style={{
                display: 'grid',
                gap: 12,
                gridTemplateColumns: 'repeat(auto-fill, minmax(248px, 1fr))',
              }}
            >
              {mods.map((m) => (
                <ModuloCard key={m.id} m={m} />
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
