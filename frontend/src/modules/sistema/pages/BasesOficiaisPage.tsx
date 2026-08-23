/** Sistema → Bases oficiais — a carga da base-mãe (ORC.8).
 *
 *  **Por que isto NÃO mora dentro do Orçamento** *(decisão do dono, 22/08/2026)*:
 *  a base-mãe não é dado da empresa, é dado da **plataforma** — vale para todos
 *  os tenants ao mesmo tempo e nenhum deles a edita. Enquanto o painel morava na
 *  tela de Bases & bancos do módulo, ele era uma operação de plataforma
 *  escondida dentro de um produto vendido, e alcançá-la exigia ter o entitlement
 *  `orcamento` — que o supervisor pode não ter e que, de todo modo, é a régua
 *  errada para decidir quem carrega a SINAPI.
 *
 *  **E não aparece trancado para ninguém.** Item de tenant que a pessoa não
 *  alcança mostra cadeado, porque é caminho que existe para ela e ela pode
 *  contratar. Isto aqui não é vendável nem contratável: mostrar trancado
 *  anunciaria uma porta que não é para o lado de cá. A seção inteira some da
 *  sidebar (`platformOnly` em AppSidebar) e a rota tem guarda própria.
 */
import PainelCargaOficial from '@/modules/orcamento/components/PainelCargaOficial'
import { OrcStyles } from '@/modules/orcamento/ui'

export default function BasesOficiaisPage() {
  return (
    <div style={{ height: '100%', overflowY: 'auto' }}>
      <OrcStyles />
      <div style={{ padding: '22px 26px 40px', maxWidth: 1100 }}>
        <div style={{ marginBottom: 18 }}>
          <h1 style={{ fontSize: 20, fontWeight: 680, color: 'var(--ink)', margin: 0 }}>
            Bases oficiais
          </h1>
          <p style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 5, maxWidth: 760 }}>
            SINAPI, ORSE e as demais tabelas públicas de custo. O que entra aqui{' '}
            <b>todos os tenants enxergam</b>, e nenhum deles edita — é a referência que
            sustenta orçamento de licitação. Carga, agendamento e histórico das corridas.
          </p>
        </div>
        <PainelCargaOficial />
      </div>
    </div>
  )
}
