import React, { useState } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { CheckCircle2, Loader2, ShieldCheck, AlertTriangle } from 'lucide-react'
import { redefinirComToken, mensagemDeErro } from '@/api/recuperacaoSenha'
import { PasswordField } from '@/components/PasswordField'
import { AuthShell, botaoPrimario } from '@/components/AuthShell'

/**
 * Define a senha nova a partir do token do e-mail (D11).
 *
 * Note que não há campo de "senha atual": é justamente o ponto do fluxo — quem
 * chega aqui esqueceu a senha. O que autoriza é a posse do token de uso único
 * entregue na caixa da pessoa, e ele vive por minutos.
 */
const RedefinirSenhaPage: React.FC = () => {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const token = params.get('token') ?? ''

  const [nova, setNova] = useState('')
  const [conf, setConf] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [salvando, setSalvando] = useState(false)
  const [pronto, setPronto] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (salvando) return
    setErro(null)
    if (nova.length < 8) {
      setErro('A nova senha deve ter ao menos 8 caracteres.')
      return
    }
    if (nova !== conf) {
      setErro('A confirmação não confere com a nova senha.')
      return
    }
    setSalvando(true)
    try {
      await redefinirComToken(token, nova)
      setPronto(true)
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível redefinir a senha.'))
    } finally {
      setSalvando(false)
    }
  }

  // Link aberto sem token (copiado pela metade, ou acesso direto à URL).
  if (!token) {
    return (
      <AuthShell
        icone={<AlertTriangle size={22} />}
        titulo="Link inválido"
        subtitulo="Este endereço precisa do link completo que enviamos por e-mail."
      >
        <Link to="/esqueci-senha" style={{ ...botaoPrimario, display: 'block', textAlign: 'center', textDecoration: 'none' }}>
          Pedir um novo link
        </Link>
      </AuthShell>
    )
  }

  if (pronto) {
    return (
      <AuthShell
        icone={<CheckCircle2 size={22} />}
        titulo="Senha redefinida"
        subtitulo="Sua senha foi alterada e todas as sessões anteriores foram encerradas."
      >
        <p className="text-sm leading-relaxed mb-6" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
          Se você não reconhece esta alteração, avise o administrador da sua empresa imediatamente.
        </p>
        <button onClick={() => navigate('/login')} style={botaoPrimario}>
          Entrar com a nova senha
        </button>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      icone={<ShieldCheck size={22} />}
      titulo="Criar nova senha"
      subtitulo="Escolha uma senha que você não use em outros serviços."
    >
      {erro && (
        <div
          className="flex items-start gap-2 text-sm px-4 py-3 rounded-lg mb-6"
          style={{ background: '#fff5f5', border: '1px solid #fed7d7', color: '#c53030', fontFamily: 'var(--font-body)' }}
        >
          <span className="mt-0.5 shrink-0">⚠</span>
          <span>{erro}</span>
        </div>
      )}

      <form onSubmit={submit} className="flex flex-col gap-4">
        <PasswordField label="Nova senha" value={nova} onChange={setNova} hint="Mínimo 8 caracteres." autoFocus autoComplete="new-password" />
        <PasswordField label="Confirmar nova senha" value={conf} onChange={setConf} autoComplete="new-password" />
        <button type="submit" disabled={salvando} style={{ ...botaoPrimario, opacity: salvando ? 0.7 : 1, marginTop: 4 }}>
          {salvando ? (
            <span className="inline-flex items-center gap-2">
              <Loader2 size={16} className="animate-spin" /> Salvando…
            </span>
          ) : (
            'Redefinir senha'
          )}
        </button>
      </form>
    </AuthShell>
  )
}

export default RedefinirSenhaPage
