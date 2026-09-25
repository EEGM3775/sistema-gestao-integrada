import React, { useCallback, useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { Eye, EyeOff, LogIn, HardHat, BarChart3, Brain, ArrowLeft, Loader2 } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import type { DesafioSegundoFator, SessaoComCodigos } from '@/api/segundoFator'
import { EntrarComCodigo } from '@/components/seguranca/EntrarComCodigo'
import { CadastroSegundoFator } from '@/components/seguranca/CadastroSegundoFator'

const features = [
  { icon: <HardHat size={18} />,    text: 'Obras e empreendimentos integrados' },
  { icon: <BarChart3 size={18} />,  text: 'Financeiro, RH e CRM em um lugar' },
  { icon: <Brain size={18} />,      text: 'Análise de IA para fotos de obra' },
]

const LoginPage: React.FC = () => {
  const { login, concluirLogin } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [username, setUsername]     = useState('')
  const [password, setPassword]     = useState('')
  const [showPass, setShowPass]     = useState(false)
  const [remember, setRemember]     = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [desafio, setDesafio]       = useState<DesafioSegundoFator | null>(null)

  const from = (location.state as { from?: { pathname?: string } })?.from?.pathname || '/app/dashboard'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      const segundaEtapa = await login(username, password, remember)
      if (segundaEtapa) {
        setDesafio(segundaEtapa)
        return
      }
      navigate(from, { replace: true })
    } catch {
      setError('Usuário ou senha incorretos. Verifique seus dados e tente novamente.')
    } finally {
      setSubmitting(false)
    }
  }

  const entrar = async (sessao: SessaoComCodigos, destino?: string) => {
    await concluirLogin(sessao)
    navigate(destino ?? from, { replace: true })
  }

  const recomecar = useCallback(() => {
    setDesafio(null)
    setPassword('')
    setError('O tempo para confirmar passou. Entre com a senha de novo.')
  }, [])

  return (
    <div className="min-h-screen flex">

      {/* ── Painel esquerdo (navy) ── visível só em desktop */}
      <div
        className="hidden lg:flex flex-col justify-between w-[480px] shrink-0 p-12"
        style={{ background: 'var(--color-brand)' }}
      >
        {/* Logo */}
        <div>
          <Link to="/" className="flex items-center gap-3 mb-16">
            <span
              className="text-3xl font-extrabold tracking-tight"
              style={{ fontFamily: 'var(--font-heading)', color: '#FFFFFF' }}
            >
              SGI
            </span>
            <span className="text-sm font-medium" style={{ color: 'rgba(255,255,255,0.65)' }}>
              Gestão Integrada
            </span>
          </Link>

          <h2
            className="text-3xl font-bold leading-snug mb-4"
            style={{ fontFamily: 'var(--font-heading)', color: '#FFFFFF' }}
          >
            A plataforma completa para sua construtora.
          </h2>
          <p className="text-sm leading-relaxed mb-10" style={{ color: 'rgba(255,255,255,0.7)' }}>
            Gestão de obras, empreendimentos, financeiro e drone com inteligência artificial —
            tudo em um único lugar.
          </p>

          <ul className="flex flex-col gap-4">
            {features.map((f) => (
              <li key={f.text} className="flex items-center gap-3">
                <span
                  className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: 'rgba(255,255,255,0.12)', color: '#FFFFFF' }}
                >
                  {f.icon}
                </span>
                <span className="text-sm" style={{ color: 'rgba(255,255,255,0.85)', fontFamily: 'var(--font-body)' }}>
                  {f.text}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {/* Rodapé do painel */}
        <p className="text-xs" style={{ color: 'rgba(255,255,255,0.4)', fontFamily: 'var(--font-body)' }}>
          © {new Date().getFullYear()} SGI — Sistema de Gestão Integrada
        </p>
      </div>

      {/* ── Painel direito (formulário) ── */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-12"
           style={{ background: '#FFFFFF' }}>

        {/* Logo mobile */}
        <div className="lg:hidden mb-10 text-center">
          <Link to="/">
            <span
              className="text-3xl font-extrabold"
              style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
            >
              SGI
            </span>
          </Link>
        </div>

        {desafio ? (
          <div className="w-full max-w-sm">
            <h1
              className="text-2xl font-bold mb-1"
              style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
            >
              {desafio.segundo_fator === 'codigo' ? 'Confirme que é você' : 'Ative o segundo fator'}
            </h1>
            <p className="text-sm mb-6" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
              {desafio.segundo_fator === 'codigo'
                ? <>A senha de <b>{username}</b> está certa. Falta o código do celular.</>
                : <>A conta <b>{username}</b> administra a empresa, e por isso só entra com senha e
                  com um código do celular. A ativação leva um minuto e é feita uma vez só.</>}
            </p>
            {desafio.segundo_fator === 'codigo' ? (
              <EntrarComCodigo desafio={desafio.desafio} aoEntrar={entrar} aoVencer={recomecar} />
            ) : (
              <CadastroSegundoFator
                conta={username}
                desafio={desafio.desafio}
                aoConcluir={sessao => { void entrar(sessao) }}
                aoVencer={recomecar}
              />
            )}
            <button
              type="button"
              onClick={() => { setDesafio(null); setPassword('') }}
              className="mt-6 flex items-center gap-1.5 text-sm"
              style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              <ArrowLeft size={14} /> Entrar com outra conta
            </button>
          </div>
        ) : (
        <div className="w-full max-w-sm">
          <h1
            className="text-2xl font-bold mb-1"
            style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
          >
            Entrar na sua conta
          </h1>
          <p className="text-sm mb-8" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}>
            Acesse a plataforma com suas credenciais.
          </p>

          {/* Erro */}
          {error && (
            <div
              className="flex items-start gap-2 text-sm px-4 py-3 rounded-lg mb-6"
              style={{
                background: '#fff5f5',
                border: '1px solid #fed7d7',
                color: '#c53030',
                fontFamily: 'var(--font-body)',
              }}
            >
              <span className="mt-0.5 shrink-0">⚠</span>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col gap-5">

            {/* Campo usuário */}
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="username"
                className="text-sm font-medium"
                style={{ fontFamily: 'var(--font-body)', color: 'var(--color-brand)' }}
              >
                Usuário
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="seu.usuario"
                className="w-full px-4 py-3 rounded-lg text-sm outline-none transition-all duration-150"
                style={{
                  fontFamily: 'var(--font-body)',
                  border: '1.5px solid #e2e8f0',
                  color: 'var(--color-text)',
                  background: '#FFFFFF',
                }}
                onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                onBlur={(e) => (e.currentTarget.style.borderColor = '#e2e8f0')}
              />
            </div>

            {/* Campo senha */}
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="password"
                className="text-sm font-medium"
                style={{ fontFamily: 'var(--font-body)', color: 'var(--color-brand)' }}
              >
                Senha
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPass ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-4 py-3 pr-11 rounded-lg text-sm outline-none transition-all duration-150"
                  style={{
                    fontFamily: 'var(--font-body)',
                    border: '1.5px solid #e2e8f0',
                    color: 'var(--color-text)',
                    background: '#FFFFFF',
                  }}
                  onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
                  onBlur={(e) => (e.currentTarget.style.borderColor = '#e2e8f0')}
                />
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => setShowPass((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded"
                  style={{ color: 'var(--color-text-muted)', background: 'none', border: 'none', cursor: 'pointer' }}
                  aria-label={showPass ? 'Ocultar senha' : 'Mostrar senha'}
                >
                  {showPass ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            {/* Lembrar de mim + recuperação (D11) */}
            <div className="flex items-center justify-between gap-3 -mt-1">
              <label
                className="flex items-center gap-2 text-sm select-none cursor-pointer"
                style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}
              >
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                  style={{ width: 16, height: 16, accentColor: 'var(--color-brand)', cursor: 'pointer' }}
                />
                Manter conectado
              </label>

              <Link
                to="/esqueci-senha"
                className="text-sm font-medium shrink-0"
                style={{ fontFamily: 'var(--font-body)', color: 'var(--color-brand)', textDecoration: 'none' }}
              >
                Esqueci minha senha
              </Link>
            </div>

            {/* Botão entrar */}
            <button
              type="submit"
              disabled={submitting}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-lg text-sm font-bold transition-all duration-200 mt-1"
              style={{
                background: submitting ? 'rgba(10,42,91,0.6)' : 'var(--color-brand)',
                color: '#FFFFFF',
                fontFamily: 'var(--font-body)',
                border: 'none',
                cursor: submitting ? 'not-allowed' : 'pointer',
              }}
              onMouseEnter={(e) => {
                if (!submitting) (e.currentTarget as HTMLElement).style.background = 'var(--color-brand-dark)'
              }}
              onMouseLeave={(e) => {
                if (!submitting) (e.currentTarget as HTMLElement).style.background = 'var(--color-brand)'
              }}
            >
              {submitting
                ? <><Loader2 size={16} className="animate-spin" /> Entrando…</>
                : <><LogIn size={16} /> Entrar</>
              }
            </button>

          </form>

          {/* Links auxiliares */}
          {/* Havia aqui um `<a href="#">Esqueci minha senha</a>` — placeholder da
              época em que não existia recuperação. Removido com o D11: o link de
              verdade fica junto do "Manter conectado", acima. Dois links com o
              mesmo texto, um deles morto, é pior que nenhum. */}
          <div className="mt-6 flex flex-col items-center gap-3">
            <Link
              to="/"
              className="flex items-center gap-1.5 text-sm transition-colors duration-150"
              style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-muted)' }}
              onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.color = 'var(--color-brand)')}
              onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.color = 'var(--color-text-muted)')}
            >
              <ArrowLeft size={14} /> Voltar para o início
            </Link>
          </div>
        </div>
        )}
      </div>

    </div>
  )
}

export default LoginPage
