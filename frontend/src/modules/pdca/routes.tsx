import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route } from 'react-router-dom'
import ModuleRoute from '@/components/ModuleRoute'

const CarteiraPage = lazy(() => import('./pages/CarteiraPage'))
const CascaPdca = lazy(() => import('./components/CascaPdca'))
const HojePage = lazy(() => import('./pages/HojePage'))
const SemanaPage = lazy(() => import('./pages/SemanaPage'))
const PlanoPage = lazy(() => import('./pages/PlanoPage'))
const MedicaoPage = lazy(() => import('./pages/MedicaoPage'))
const QualidadePage = lazy(() => import('./pages/QualidadePage'))
const SegurancaPage = lazy(() => import('./pages/SegurancaPage'))
const CascaDeCampo = lazy(() => import('./campo/CascaDeCampo'))
const FrentePage = lazy(() => import('./campo/FrentePage'))
const ApontarPage = lazy(() => import('./campo/ApontarPage'))
const ResponderFichaPage = lazy(() => import('./campo/ResponderFichaPage'))
const NovoDefeitoPage = lazy(() => import('./campo/NovoDefeitoPage'))
const NovaOcorrenciaPage = lazy(() => import('./campo/NovaOcorrenciaPage'))
const DdsDeCampoPage = lazy(() => import('./campo/DdsDeCampoPage'))

function w(element: ReactNode) {
  return (
    <Suspense
      fallback={
        <div style={{ padding: '28px 26px', color: 'var(--ink-3)', fontSize: 14 }}>
          Carregando Planejamento…
        </div>
      }
    >
      {element}
    </Suspense>
  )
}

/** Rotas do PDCA, atrás do entitlement `pdca`.
 *
 *  **A obra vive no endereço** (`/app/pdca/o/:obraId/<posto>`): é o que torna
 *  todo link colável, faz a aba nova abrir onde estava e permite trocar de obra
 *  mantendo o posto. A carteira é a porta de fora. */
export const pdcaRoutes = (
  <Route element={<ModuleRoute module="pdca" />}>
    <Route path="pdca" element={w(<CarteiraPage />)} />
    <Route path="pdca/o/:obraId" element={w(<CascaPdca />)}>
      {/* **A obra abre em `HOJE`**, e não no plano: a pergunta do primeiro
          minuto do dia é o que exige decisão, não o que o cronograma diz.
          A porta por papel (o planejador em `PLANO`, o técnico de segurança
          em `SEGURANÇA` — §3.3 da planta) ainda não existe: com os seis
          postos no ar ela passou a ser construível, e está no roadmap. */}
      <Route index element={<Navigate to="hoje" replace />} />
      <Route path="hoje" element={w(<HojePage />)} />
      <Route path="semana" element={w(<SemanaPage />)} />
      <Route path="plano" element={w(<PlanoPage />)} />
      <Route path="medicao" element={w(<MedicaoPage />)} />
      <Route path="qualidade" element={w(<QualidadePage />)} />
      <Route path="seguranca" element={w(<SegurancaPage />)} />
      <Route path="*" element={<Navigate to="hoje" replace />} />
    </Route>
  </Route>
)

/** **A segunda superfície.** Rota própria, fora do `/app`, e casca própria:
 *  sem sidebar, sem rail, sem inspetor.
 *
 *  Não é o escritório encolhido. A entrada é *a minha frente de hoje* e não a
 *  obra, o alvo é dedo com luva e o ato é **produzir** o dado — apontar o que
 *  andou, dizer que a trava saiu. É esse dado que todo indicador do escritório
 *  consome, e por isso ele nasce junto do posto que o consome, e não numa fatia
 *  no fim. */
export const campoRoutes = (
  <Route element={<ModuleRoute module="pdca" />}>
    <Route path="campo" element={w(<CascaDeCampo />)}>
      <Route index element={w(<FrentePage />)} />
      <Route path="apontar/:atividadeId" element={w(<ApontarPage />)} />
      <Route path="ficha/:verificacaoId" element={w(<ResponderFichaPage />)} />
      <Route path="defeito" element={w(<NovoDefeitoPage />)} />
      <Route path="ocorrencia" element={w(<NovaOcorrenciaPage />)} />
      <Route path="dds" element={w(<DdsDeCampoPage />)} />
      <Route path="dds/:ddsId" element={w(<DdsDeCampoPage />)} />
      <Route path="*" element={<Navigate to="/campo" replace />} />
    </Route>
  </Route>
)
