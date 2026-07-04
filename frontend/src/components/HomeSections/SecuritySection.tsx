import React from 'react'
import { ShieldCheck, Lock, CloudUpload, ScrollText } from 'lucide-react'

const badges = [
  { icon: <ShieldCheck size={22} />, label: 'Criptografia AES-256' },
  { icon: <Lock size={22} />, label: 'OWASP Top 10 Mitigado' },
  { icon: <CloudUpload size={22} />, label: 'Backups Diários' },
  { icon: <ScrollText size={22} />, label: 'Conformidade LGPD' },
]

const SecuritySection: React.FC = () => {
  return (
    <section id="seguranca" className="py-20 px-6" style={{ background: 'var(--color-bg-alt)' }}>
      <div className="max-w-6xl mx-auto flex flex-col lg:flex-row items-center gap-12">

        {/* Texto */}
        <div className="flex-1 text-center lg:text-left">
          <span
            className="inline-block text-xs font-semibold uppercase tracking-widest mb-4 px-3 py-1 rounded-full"
            style={{ background: '#e8f0fb', color: 'var(--color-brand)', fontFamily: 'var(--font-body)' }}
          >
            Segurança
          </span>
          <h3
            className="text-3xl lg:text-4xl font-bold mb-5"
            style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
          >
            Segurança em Nível Empresarial
          </h3>
          <p
            className="text-base leading-relaxed max-w-lg mx-auto lg:mx-0"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}
          >
            Seus dados são seu maior ativo. Protegemos suas informações com as mais rigorosas
            práticas de segurança do mercado, incluindo criptografia de ponta a ponta e
            conformidade total com a LGPD. Foco na sua obra, que da segurança cuidamos nós.
          </p>
        </div>

        {/* Badges */}
        <div className="flex-1 grid grid-cols-2 gap-4 w-full max-w-sm mx-auto lg:max-w-none">
          {badges.map((b) => (
            <div
              key={b.label}
              className="flex items-center gap-3 px-5 py-4 rounded-xl"
              style={{
                background: '#FFFFFF',
                boxShadow: 'var(--shadow-sm)',
                color: 'var(--color-brand)',
              }}
            >
              <span style={{ color: 'var(--color-brand)', flexShrink: 0 }}>{b.icon}</span>
              <span
                className="text-sm font-semibold leading-tight"
                style={{ fontFamily: 'var(--font-body)', color: 'var(--color-brand)' }}
              >
                {b.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default SecuritySection
