import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, MailCheck, Loader2, KeyRound } from 'lucide-react'
import { solicitarRecuperacao, mensagemDeErro } from '@/api/recuperacaoSenha'
import { AuthShell, campoStyle, botaoPrimario } from '@/components/AuthShell'

/**
 * "Esqueci minha senha" (D11) — porta de entrada da recuperação.
 *
 * A tela de sucesso é deliberadamente idêntica para conta existente e
 * inexistente: o servidor responde igual nos dois casos (para não virar oráculo
 * de enumeração de usuários) e a UI não pode desfazer isso mostrando "usuário
 * não encontrado". Por isso o texto fala em "se a conta existir".
 */
const EsqueciSenhaPage: React.FC = () => {
  const [identificador, setIdentificador] = useState('')
  const [enviado, setEnviado] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (enviando) return
    setErro(null)
    setEnviando(true)
    try {
      await solicitarRecuperacao(identificador.trim())
      setEnviado(true)
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível processar o pedido. Tente novamente.'))
    } finally {
      setEnviando(false)
    }
  }

  if (enviado) {
    return (
      <AuthShell
        icone={<MailCheck size={22} />}
        titulo="Verifique seu e-mail"
        subtitulo="Se a conta existir e tiver e-mail cadastrado, enviamos um link de redefinição."
      >
        <div
          className="text-sm leading-relaxed px-4 py-3 rounded-lg mb-6"
          style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#166534', fontFamily: 'var(--font-body)' }}
        >
          O link vale por <b>30 minutos</b> e só pode ser usado uma vez. Não esqueça de olhar a
          caixa de spam.
        </div>
        <p className="text-sm mb-6" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
          O administrador da sua empresa é avisado de que houve este pedido — por segurança, ele
          recebe apenas o aviso, nunca o link.
        </p>
        <Link to="/login" style={{ ...botaoPrimario, display: 'block', textAlign: 'center', textDecoration: 'none' }}>
          Voltar para o login
        </Link>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      icone={<KeyRound size={22} />}
      titulo="Recuperar acesso"
      subtitulo="Informe seu usuário ou e-mail. Enviaremos um link para você criar uma nova senha."
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

      <form onSubmit={submit} className="flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="identificador"
            className="text-sm font-medium"
            style={{ fontFamily: 'var(--font-body)', color: 'var(--color-brand)' }}
          >
            Usuário ou e-mail
          </label>
          <input
            id="identificador"
            type="text"
            autoComplete="username"
            required
            autoFocus
            value={identificador}
            onChange={(e) => setIdentificador(e.target.value)}
            placeholder="seu.usuario ou voce@empresa.com"
            style={campoStyle}
            onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--color-brand)')}
            onBlur={(e) => (e.currentTarget.style.borderColor = '#e2e8f0')}
          />
        </div>

        <button type="submit" disabled={enviando} style={{ ...botaoPrimario, opacity: enviando ? 0.7 : 1 }}>
          {enviando ? (
            <span className="inline-flex items-center gap-2">
              <Loader2 size={16} className="animate-spin" /> Enviando…
            </span>
          ) : (
            'Enviar link de recuperação'
          )}
        </button>
      </form>

      <Link
        to="/login"
        className="inline-flex items-center gap-1.5 text-sm mt-6"
        style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)', textDecoration: 'none' }}
      >
        <ArrowLeft size={15} /> Voltar para o login
      </Link>
    </AuthShell>
  )
}

export default EsqueciSenhaPage
