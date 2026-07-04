import React from 'react'
import {
  HardHat,
  BarChart3,
  TrendingUp,
  MessageCircle,
  FolderOpen,
  Brain,
} from 'lucide-react'

const modules = [
  {
    icon: <HardHat size={40} />,
    title: 'Gestão de Obras',
    text: 'Acompanhe o cronograma, diário de obras e alocação de recursos em tempo real.',
    badge: 'Base',
  },
  {
    icon: <BarChart3 size={40} />,
    title: 'Gestão Financeira',
    text: 'Controle contas a pagar, receber e o fluxo de caixa com precisão total.',
    badge: 'Módulo adicional',
  },
  {
    icon: <TrendingUp size={40} />,
    title: 'CRM de Vendas',
    text: 'Gerencie seus leads e clientes, do primeiro contato ao fechamento do contrato.',
    badge: 'Módulo adicional',
  },
  {
    icon: <MessageCircle size={40} />,
    title: 'Diário por WhatsApp',
    text: 'Receba atualizações do campo com fotos e textos, direto na plataforma, sem apps adicionais.',
    badge: 'Base',
  },
  {
    icon: <FolderOpen size={40} />,
    title: 'Gestão de Documentos',
    text: 'Centralize projetos, licenças e NFs em um repositório seguro e rastreável.',
    badge: 'Base',
  },
  {
    icon: <Brain size={40} />,
    title: 'Relatórios com IA',
    text: 'Nossa IA analisa seus dados para gerar insights sobre custos, prazos e riscos.',
    badge: 'Base',
  },
]

const ModulesSection: React.FC = () => {
  return (
    <section id="modulos" className="py-20 px-6" style={{ background: 'var(--color-bg-alt)' }}>
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <h2
            className="text-3xl lg:text-4xl font-bold mb-4"
            style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
          >
            Uma plataforma completa para cada desafio da sua construtora
          </h2>
          <p
            className="text-base max-w-xl mx-auto"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}
          >
            Módulos base inclusos. Expanda com funcionalidades adicionais conforme sua operação crescer.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {modules.map((mod) => (
            <div
              key={mod.title}
              className="rounded-xl p-7 flex flex-col gap-4 transition-shadow duration-200"
              style={{
                background: '#FFFFFF',
                boxShadow: 'var(--shadow-sm)',
              }}
              onMouseEnter={(e) =>
                ((e.currentTarget as HTMLElement).style.boxShadow = 'var(--shadow-md)')
              }
              onMouseLeave={(e) =>
                ((e.currentTarget as HTMLElement).style.boxShadow = 'var(--shadow-sm)')
              }
            >
              <div
                className="w-14 h-14 rounded-xl flex items-center justify-center"
                style={{ background: '#e8f0fb', color: 'var(--color-brand)' }}
              >
                {mod.icon}
              </div>

              <div className="flex items-start justify-between gap-2">
                <h3
                  className="text-lg font-bold"
                  style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
                >
                  {mod.title}
                </h3>
                <span
                  className="shrink-0 text-xs font-semibold px-2 py-1 rounded-full"
                  style={
                    mod.badge === 'Base'
                      ? { background: '#d4edda', color: '#155724' }
                      : { background: '#fff3cd', color: '#856404' }
                  }
                >
                  {mod.badge}
                </span>
              </div>

              <p
                className="text-sm leading-relaxed"
                style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text)' }}
              >
                {mod.text}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default ModulesSection
