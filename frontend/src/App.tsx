import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import AppShell from './components/layout/AppShell'
import AppHomePage from './pages/app/AppHomePage'
import PrivateRoute from './components/PrivateRoute'
import EmpreendimentosListPage from './modules/empreendimentos/pages/EmpreendimentosListPage'
import EmpreendimentoDetailPage from './modules/empreendimentos/pages/EmpreendimentoDetailPage'
import ObrasListPage from './modules/obras/pages/ObrasListPage'
import ObraDetailPage from './modules/obras/pages/ObraDetailPage'
import ClientesListPage from './modules/clientes/pages/ClientesListPage'
import ClienteDetailPage from './modules/clientes/pages/ClienteDetailPage'
import FornecedoresListPage from './modules/fornecedores/pages/FornecedoresListPage'
import FornecedorDetailPage from './modules/fornecedores/pages/FornecedorDetailPage'
import DiarioObraPage from './modules/diario/pages/DiarioObraPage'
import FuncionariosListPage from './modules/rh/pages/FuncionariosListPage'
import FuncionarioDetailPage from './modules/rh/pages/FuncionarioDetailPage'
import CargosPage from './modules/rh/pages/CargosPage'
import { erpRoutes } from './modules/erp/routes'

function App() {
  return (
    <Router>
      <Routes>
        {/* ── Públicas ── */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />

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

          {/* ── RH ── */}
          <Route path="rh" element={<FuncionariosListPage />} />
          <Route path="rh/cargos" element={<CargosPage />} />
          <Route path="rh/:id" element={<FuncionarioDetailPage />} />

          {/* ── ERP Financeiro (sub-rotas lazy — code-splitting, docs/modulos/moduloerp.md §5.6) ── */}
          {erpRoutes}

          {/* Fallback interno — caminho absoluto evita loop de append no splat (/app/x → /app/x/dashboard → …) */}
          <Route path="*" element={<Navigate to="/app/dashboard" replace />} />
        </Route>

        {/* ── Fallback global ── */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  )
}

export default App
