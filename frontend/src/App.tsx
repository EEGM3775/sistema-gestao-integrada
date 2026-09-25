import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import EsqueciSenhaPage from './pages/EsqueciSenhaPage'
import RedefinirSenhaPage from './pages/RedefinirSenhaPage'
import ConfirmarEmailPage from './pages/ConfirmarEmailPage'
import AppShell from './components/layout/AppShell'
import AppHomePage from './pages/app/AppHomePage'
import MinhaContaPage from './pages/app/MinhaContaPage'
import PrivateRoute from './components/PrivateRoute'
import ModuleRoute from './components/ModuleRoute'
import AdminRoute from './components/AdminRoute'
import EmpreendimentosListPage from './modules/empreendimentos/pages/EmpreendimentosListPage'
import EmpreendimentoDetailPage from './modules/empreendimentos/pages/EmpreendimentoDetailPage'
import ObrasListPage from './modules/obras/pages/ObrasListPage'
import ObraDetailPage from './modules/obras/pages/ObraDetailPage'
import ClientesListPage from './modules/clientes/pages/ClientesListPage'
import ClienteDetailPage from './modules/clientes/pages/ClienteDetailPage'
import FornecedoresListPage from './modules/fornecedores/pages/FornecedoresListPage'
import FornecedorDetailPage from './modules/fornecedores/pages/FornecedorDetailPage'
import DiarioObraPage from './modules/diario/pages/DiarioObraPage'
import CalendarPage from './modules/calendar/pages/CalendarPage'
import FuncionariosListPage from './modules/rh/pages/FuncionariosListPage'
import FuncionarioDetailPage from './modules/rh/pages/FuncionarioDetailPage'
import CargosPage from './modules/rh/pages/CargosPage'
import PlatformRoute from './components/PlatformRoute'
import LixoPage from './modules/lixo/pages/LixoPage'
import BasesOficiaisPage from './modules/sistema/pages/BasesOficiaisPage'
import PersonasPage from './modules/admin/pages/PersonasPage'
import UsuariosPage from './modules/admin/pages/UsuariosPage'
import AprovacoesPage from './modules/admin/pages/AprovacoesPage'
import { erpRoutes } from './modules/erp/routes'
import { crmRoutes } from './modules/crm/routes'
import { scmRoutes } from './modules/scm/routes'
import { silRoutes } from './modules/sil/routes'
import { orcamentoRoutes } from './modules/orcamento/routes'
import { mapsRoutes } from './modules/maps/routes'
import { pranchetaRoutes } from './modules/prancheta/routes'
import { campoRoutes, pdcaRoutes } from './modules/pdca/routes'

function App() {
  return (
    <Router>
      <Routes>
        {/* ── Públicas ── */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        {/* D11 — recuperação de conta. Públicas por necessidade: quem esqueceu a
            senha não consegue se autenticar. Os caminhos batem com os links que
            a IAM monta nos e-mails (FRONTEND_BASE_URL + estes paths). */}
        <Route path="/esqueci-senha" element={<EsqueciSenhaPage />} />
        <Route path="/redefinir-senha" element={<RedefinirSenhaPage />} />
        <Route path="/confirmar-email" element={<ConfirmarEmailPage />} />

        {/* ── Área protegida (AppShell = sidebar + topbar + Outlet) ── */}
        <Route
          path="/app"
          element={
            <PrivateRoute>
              <AppShell />
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="/app/dashboard" replace />} />
          <Route path="dashboard" element={<AppHomePage />} />
          <Route path="conta" element={<MinhaContaPage />} />

          {/* ── Empreendimentos ── */}
          <Route path="empreendimentos" element={<EmpreendimentosListPage />} />
          <Route path="empreendimentos/:id" element={<EmpreendimentoDetailPage />} />

          {/* ── Obras ── */}
          <Route path="obras" element={<ObrasListPage />} />
          <Route path="obras/:id" element={<ObraDetailPage />} />

          {/* ── Clientes ── */}
          <Route path="clientes" element={<ClientesListPage />} />
          <Route path="clientes/:id" element={<ClienteDetailPage />} />

          {/* ── Fornecedores ── */}
          <Route path="fornecedores" element={<FornecedoresListPage />} />
          <Route path="fornecedores/:id" element={<FornecedorDetailPage />} />

          {/* ── Diário de Obra & IA ── */}
          <Route path="diario" element={<DiarioObraPage />} />

          {/* ── Calendário (módulo base — sem entitlement) ── */}
          <Route path="calendario" element={<CalendarPage />} />

          {/* ── RH (entitlement `rh` — guard de módulo, F4) ── */}
          <Route element={<ModuleRoute module="rh" />}>
            <Route path="rh" element={<FuncionariosListPage />} />
            <Route path="rh/cargos" element={<CargosPage />} />
            <Route path="rh/:id" element={<FuncionarioDetailPage />} />
          </Route>

          {/* ── Administração do tenant (papéis/personas + usuários) — guard de
               is_tenant_admin, F7. Antes só a sidebar travava o link. ── */}
          <Route element={<AdminRoute />}>
            <Route path="admin/papeis" element={<PersonasPage />} />
            <Route path="admin/usuarios" element={<UsuariosPage />} />
            {/* Definir alçada é da mesma classe que definir papel: decidir quem
                manda no dinheiro × quem vê o quê. Daí morar aqui, atrás do
                mesmo guard, e não dentro do módulo que a escada aprova. */}
            <Route path="admin/aprovacoes" element={<AprovacoesPage />} />

          {/* ── LIXO — a exclusão reversível da plataforma (D116). Não é módulo
               (não tem entitlement) nem é só do admin: quem alcança é o papel
               `gestor_lixo`, pela permissão `plataforma.lixo.view`. A rota fica
               solta aqui, ao lado da administração, porque a página atravessa
               todos os módulos — obra, cliente, fornecedor, conta e lead saem
               da mesma lista. ── */}
          <Route path="lixo" element={<LixoPage />} />
          </Route>

          {/* ── SISTEMA — operação da PLATAFORMA, não da empresa. Guarda por
               `is_platform_admin`, e a recusa é um redirect silencioso: para
               quem não é supervisor a rota não existe. ── */}
          <Route element={<PlatformRoute />}>
            <Route path="sistema/bases" element={<BasesOficiaisPage />} />
          </Route>

          {/* ── ERP Financeiro (sub-rotas lazy — code-splitting, docs/modulos/moduloerp.md §5.6) ── */}
          {erpRoutes}

          {/* ── CRM (sub-rotas lazy — code-splitting) ── */}
          {crmRoutes}

          {/* ── SCM / Suprimentos (sub-rotas lazy — primeiro módulo Malha) ── */}
          {scmRoutes}

          {/* ── SIL / Estoque & Logística (sub-rotas lazy) ── */}
          {silRoutes}

          {/* ── Orçamento (hub + páginas, sub-rotas lazy) ── */}
          {orcamentoRoutes}

          {/* ── Maps / Território (metade fundação sem entitlement; a aba
               Território é que trava sem o módulo `maps`) ── */}
          {mapsRoutes}

          {/* ── Prancheta / projeto em campo (rota aberta; a página é que decide
               entre o acervo e a tela que explica o módulo — como o Maps) ── */}
          {pranchetaRoutes}

          {/* ── PDCA / Planejamento e qualidade (entitlement `pdca`; a unidade de
               trabalho é a obra — docs/modulos/modulopdca.md §5.1) ── */}
          {pdcaRoutes}

          {/* Fallback interno — caminho absoluto evita loop de append no splat (/app/x → /app/x/dashboard → …) */}
          <Route path="*" element={<Navigate to="/app/dashboard" replace />} />
        </Route>

        {/* ── Campo (segunda superfície do PDCA) ──
             Fora do `/app` **de propósito**: o canteiro não é o escritório
             encolhido. Sem sidebar e sem topbar, porque quem está de capacete
             tem uma frente, não um menu — a casca é a do módulo.

             A rota de layout é **sem `path`**: ela só exige a sessão. O
             endereço vem de dentro do `campoRoutes`, e dar um `path="/campo"`
             aqui empilharia com o `path="campo"` de lá e a tela viveria em
             `/campo/campo` — que foi o que aconteceu na primeira escrita. */}
        <Route
          element={
            <PrivateRoute>
              <Outlet />
            </PrivateRoute>
          }
        >
          {campoRoutes}
        </Route>

        {/* ── Fallback global ── */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  )
}

export default App
