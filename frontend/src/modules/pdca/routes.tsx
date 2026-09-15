import { lazy, Suspense, type ReactNode } from 'react'
import { Route } from 'react-router-dom'
import ModuleRoute from '@/components/ModuleRoute'

const ObrasPage = lazy(() => import('./pages/ObrasPage'))
const CronogramaPage = lazy(() => import('./pages/CronogramaPage'))
const ExpedientePage = lazy(() => import('./pages/ExpedientePage'))
const ContratosPage = lazy(() => import('./pages/ContratosPage'))
const ContratoPage = lazy(() => import('./pages/ContratoPage'))
const PreviaDeMedicaoPage = lazy(() => import('./pages/PreviaDeMedicaoPage'))
const MedicaoPage = lazy(() => import('./pages/MedicaoPage'))

function w(element: ReactNode) {
  return (
    <Suspense fallback={<div style={{ padding: '28px 26px', color: 'var(--ink-3)', fontSize: 14 }}>Carregando o Planejamento…</div>}>
      {element}
    </Suspense>
  )
}

/**
 * Rotas do PDCA sob `/app/pdca`, atrás do entitlement `pdca`.
 *
 * O endereço carrega a **obra** e o **cronograma**, nesta ordem, porque a
 * unidade de trabalho deste módulo é a obra (planta §5.1): o link colado no
 * grupo da obra abre o plano daquela obra, e não uma tela que pede para
 * escolher de novo. A atividade viaja em `?atividade=` — ela é um recorte
 * dentro do plano, não um lugar.
 */
export const pdcaRoutes = (
  <Route element={<ModuleRoute module="pdca" />}>
    <Route path="pdca" element={w(<ObrasPage />)} />
    <Route path="pdca/obra/:obraId/cronograma/:cronogramaId" element={w(<CronogramaPage />)} />
    {/* O expediente é da **empresa**, não de uma obra — por isso fica fora do
        endereço com obra. Um calendário de obra é caso particular dele. */}
    <Route path="pdca/expediente" element={w(<ExpedientePage />)} />
    {/* PDCA.3 — o contrato mora **sob a obra**, como o cronograma.
        *(Decisão do dono, 15/09/2026: "medição tem que ficar dentro de pdca".)*
        A primeira escrita desta rota era `/app/pdca/contratos`, cross-obra, com
        entrada própria na barra lateral; o argumento era que a pergunta do
        gestor de contratos atravessa obras ("o que a Alfa tem em aberto
        comigo?"). O dono decidiu pela unidade do módulo — e ela é a **obra**
        (§5.1), como já era para tudo o mais aqui. A pergunta cross-obra que
        sobra é a que realmente não pertence a uma obra — *de quem se espera
        decisão agora* —, e ela ficou na raiz do módulo, na `ObrasPage`. */}
    <Route path="pdca/obra/:obraId/contratos" element={w(<ContratosPage />)} />
    <Route path="pdca/obra/:obraId/contratos/:contratoId" element={w(<ContratoPage />)} />
    {/* **A medição tem endereço próprio, e isso é o conserto de um defeito.**
        Ela era um `?medicao=14` que reconfigurava um card no meio da tela do
        contrato: o link era compartilhável mas abria uma tela diferente da que
        o gestor tinha visto (a página calculava saldo a partir de uma prévia
        que só existia quando se chegava pelo outro caminho). Rota própria
        significa que o documento é o mesmo por qualquer porta — e o endereço
        antigo continua funcionando, redirecionado pela `ContratoPage`.

        A **prévia** também é rota, e somente leitura: só se digita dentro de um
        documento, nunca em duas superfícies para o mesmo número. */}
    <Route path="pdca/obra/:obraId/contratos/:contratoId/previa" element={w(<PreviaDeMedicaoPage />)} />
    <Route path="pdca/obra/:obraId/contratos/:contratoId/medicoes/:medicaoId" element={w(<MedicaoPage />)} />
  </Route>
)
