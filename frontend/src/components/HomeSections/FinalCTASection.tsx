import React from 'react'

const FinalCTASection: React.FC = () => {
  return (
    <section
      id="solicitar-demo"
      className="py-24 px-6 text-center"
      style={{ background: 'var(--color-brand)' }}
    >
      <div className="max-w-2xl mx-auto">
        <h2
          className="text-3xl lg:text-4xl font-bold mb-4"
          style={{ fontFamily: 'var(--font-heading)', color: '#FFFFFF' }}
        >
          Pronto para revolucionar a gestão da sua construtora?
        </h2>
        <p
          className="text-base mb-10"
          style={{ fontFamily: 'var(--font-body)', color: 'rgba(255,255,255,0.8)' }}
        >
          Veja na prática como nossa plataforma pode aumentar sua eficiência e rentabilidade.
        </p>

        {/* Formulário simples */}
        <form
          className="flex flex-col sm:flex-row gap-3 justify-center max-w-lg mx-auto"
          onSubmit={(e) => e.preventDefault()}
        >
          <input
            type="email"
            placeholder="Seu melhor e-mail"
            required
            className="flex-1 px-4 py-3 rounded-lg text-sm outline-none"
            style={{
              fontFamily: 'var(--font-body)',
              color: 'var(--color-text)',
              border: 'none',
              minWidth: 0,
            }}
          />
          <button
            type="submit"
            className="shrink-0 px-7 py-3 rounded-lg text-sm font-bold transition-all duration-200"
            style={{
              background: '#FFFFFF',
              color: 'var(--color-brand)',
              fontFamily: 'var(--font-body)',
              border: 'none',
              cursor: 'pointer',
            }}
            onMouseEnter={(e) =>
              ((e.currentTarget as HTMLElement).style.background = 'var(--color-bg-alt)')
            }
            onMouseLeave={(e) =>
              ((e.currentTarget as HTMLElement).style.background = '#FFFFFF')
            }
          >
            Solicitar Demo Gratuita
          </button>
        </form>

        <p
          className="text-xs mt-5"
          style={{ fontFamily: 'var(--font-body)', color: 'rgba(255,255,255,0.55)' }}
        >
          Sem compromisso. Nossa equipe entrará em contato em até 24h.
        </p>
      </div>
    </section>
  )
}

export default FinalCTASection
