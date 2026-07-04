import React from 'react'
import { Link } from 'react-router-dom'

const LandingFooter: React.FC = () => {
  return (
    <footer style={{ background: '#495057', color: '#aeb9c7' }}>
      <div className="max-w-6xl mx-auto px-6 py-8 flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <span
            className="text-lg font-bold"
            style={{ fontFamily: 'var(--font-heading)', color: '#FFFFFF' }}
          >
            SGI
          </span>
          <span className="text-sm">© {new Date().getFullYear()} Todos os direitos reservados.</span>
        </div>

        <nav className="flex flex-wrap justify-center gap-6 text-sm">
          {[
            { label: 'Política de Privacidade', href: '#' },
            { label: 'Termos de Uso', href: '#' },
            { label: 'Contato', href: '#solicitar-demo' },
          ].map((item) => (
            <a
              key={item.label}
              href={item.href}
              className="transition-colors duration-150 hover:text-white"
            >
              {item.label}
            </a>
          ))}
          <Link to="/login" className="transition-colors duration-150 hover:text-white">
            Acessar plataforma
          </Link>
        </nav>
      </div>
    </footer>
  )
}

export default LandingFooter
