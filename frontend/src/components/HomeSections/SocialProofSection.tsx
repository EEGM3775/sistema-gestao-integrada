import React from 'react'
import { Quote } from 'lucide-react'

const metrics = [
  { value: '+30', unit: 'horas', label: 'economizadas por mês' },
  { value: '15%', unit: '', label: 'Redução no desperdício de materiais' },
  { value: '100%', unit: '', label: 'De conformidade nos prazos' },
]

const SocialProofSection: React.FC = () => {
  return (
    <section className="py-20 px-6" style={{ background: 'var(--color-bg)' }}>
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <h2
            className="text-3xl lg:text-4xl font-bold"
            style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
          >
            Construindo Relações de Confiança
          </h2>
        </div>

        {/* Depoimento */}
        <div
          className="max-w-2xl mx-auto rounded-2xl p-8 mb-14"
          style={{
            background: 'var(--color-bg-alt)',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <Quote size={32} style={{ color: 'var(--color-brand)', marginBottom: '1rem', opacity: 0.5 }} />
          <blockquote
            className="text-lg italic mb-4 leading-relaxed"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}
          >
            "O sistema transformou nossa gestão. A visão integrada do financeiro com o progresso das
            obras nos deu um poder de decisão que não tínhamos antes."
          </blockquote>
          <cite
            className="text-sm font-bold not-italic"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--color-brand)' }}
          >
            João da Silva, Diretor na Construtora Exemplo.
          </cite>
        </div>

        {/* Métricas */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-16">
          {metrics.map((m) => (
            <div key={m.label} className="text-center">
              <div
                className="text-5xl font-extrabold mb-1"
                style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
              >
                {m.value}
                {m.unit && (
                  <span className="text-2xl ml-1">{m.unit}</span>
                )}
              </div>
              <div
                className="text-sm"
                style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}
              >
                {m.label}
              </div>
            </div>
          ))}
        </div>

        {/* Logos clientes */}
        <div className="text-center">
          <h4
            className="text-sm font-semibold uppercase tracking-widest mb-8"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}
          >
            Empresas que confiam em nossa tecnologia
          </h4>
          <div className="flex flex-wrap justify-center gap-6">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="w-28 h-12 rounded-lg flex items-center justify-center text-xs font-semibold"
                style={{
                  background: 'var(--color-bg-alt)',
                  color: 'var(--color-text-muted)',
                  border: '1px dashed #ced4da',
                  fontFamily: 'var(--font-body)',
                }}
              >
                LOGO
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

export default SocialProofSection
