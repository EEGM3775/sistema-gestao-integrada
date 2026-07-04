import React from 'react'

const HeroSection: React.FC = () => {
  return (
    <section
      className="pt-[140px] pb-20 px-6"
      style={{ background: 'var(--color-bg)' }}
    >
      <div className="max-w-6xl mx-auto flex flex-col lg:flex-row items-center gap-12">

        {/* Texto */}
        <div className="flex-1 text-center lg:text-left">
          <span
            className="inline-block text-xs font-semibold uppercase tracking-widest mb-4 px-3 py-1 rounded-full"
            style={{
              background: '#e8f0fb',
              color: 'var(--color-brand)',
              fontFamily: 'var(--font-body)',
            }}
          >
            Plataforma SaaS para Construção Civil
          </span>

          <h1
            className="text-4xl lg:text-5xl font-extrabold leading-tight mb-6"
            style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
          >
            O Fim do Improviso <br className="hidden lg:block" />
            na Sua Obra.
          </h1>

          <p
            className="text-xl font-semibold mb-3"
            style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
          >
            Inteligência, Gestão, Controle e Lucro em um só lugar.
          </p>

          <p
            className="text-base mb-8 max-w-lg mx-auto lg:mx-0"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)', lineHeight: 1.7 }}
          >
            Nossa plataforma integra todos os seus processos, do canteiro de obras ao financeiro,
            transformando dados em decisões inteligentes e previsíveis. Tenha o controle total
            dos seus empreendimentos.
          </p>

          <div className="flex flex-col sm:flex-row gap-3 justify-center lg:justify-start">
            <a
              href="#solicitar-demo"
              className="inline-block text-sm font-bold px-8 py-4 rounded-lg transition-all duration-200"
              style={{
                background: 'var(--color-brand)',
                color: '#FFFFFF',
                fontFamily: 'var(--font-body)',
                boxShadow: '0 4px 14px rgba(10,42,91,0.35)',
              }}
              onMouseEnter={(e) =>
                ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand-dark)')
              }
              onMouseLeave={(e) =>
                ((e.currentTarget as HTMLElement).style.background = 'var(--color-brand)')
              }
            >
              Solicitar Demonstração
            </a>
            <a
              href="#modulos"
              className="inline-block text-sm font-bold px-8 py-4 rounded-lg border-2 transition-all duration-200"
              style={{
                borderColor: 'var(--color-brand)',
                color: 'var(--color-brand)',
                fontFamily: 'var(--font-body)',
              }}
              onMouseEnter={(e) => {
                const el = e.currentTarget as HTMLElement
                el.style.background = 'var(--color-brand)'
                el.style.color = '#FFFFFF'
              }}
              onMouseLeave={(e) => {
                const el = e.currentTarget as HTMLElement
                el.style.background = 'transparent'
                el.style.color = 'var(--color-brand)'
              }}
            >
              Ver módulos
            </a>
          </div>

          {/* Métricas rápidas */}
          <div className="mt-10 flex flex-wrap gap-6 justify-center lg:justify-start">
            {[
              { value: '+30h', label: 'economizadas/mês' },
              { value: '15%', label: 'menos desperdício' },
              { value: '100%', label: 'conformidade nos prazos' },
            ].map((m) => (
              <div key={m.label} className="text-center lg:text-left">
                <div
                  className="text-2xl font-extrabold"
                  style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
                >
                  {m.value}
                </div>
                <div
                  className="text-xs mt-0.5"
                  style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}
                >
                  {m.label}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Imagem mockup */}
        <div className="flex-1 w-full max-w-xl lg:max-w-none">
          <div
            className="rounded-2xl overflow-hidden"
            style={{ boxShadow: 'var(--shadow-lg)' }}
          >
            <img
              src="/dashboard-mockup.png"
              alt="Dashboard do Sistema de Gestão Integrada"
              className="w-full h-auto"
              onError={(e) => {
                // fallback enquanto a imagem não existir
                const el = e.currentTarget
                el.style.display = 'none'
                const parent = el.parentElement
                if (parent) {
                  parent.style.background = 'var(--color-bg-alt)'
                  parent.style.minHeight = '320px'
                  parent.style.display = 'flex'
                  parent.style.alignItems = 'center'
                  parent.style.justifyContent = 'center'
                  parent.innerHTML =
                    '<span style="color:var(--color-text-muted);font-family:var(--font-body);font-size:0.875rem">Dashboard mockup</span>'
                }
              }}
            />
          </div>
        </div>
      </div>
    </section>
  )
}

export default HeroSection
