import React, { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AtSign, CheckCircle2, XCircle, Loader2, AlertTriangle } from 'lucide-react'
import { resolverTrocaEmail, mensagemDeErro } from '@/api/recuperacaoSenha'
import { AuthShell, botaoPrimario, botaoSecundario } from '@/components/AuthShell'

/**
 * Confirma — ou recusa — uma troca de e-mail (D11).
 *
 * Este link chega no endereço **ANTIGO**. É o ponto onde o dono da conta tem a
 * palavra final: enquanto ele não confirmar, o e-mail não muda. Por isso o botão
 * de recusar tem o mesmo peso visual do de confirmar, e o texto explica por que
 * uma troca que a pessoa não pediu é sinal de tentativa de tomar a conta —
 * quem controla o e-mail controla a recuperação de senha.
 */
const ConfirmarEmailPage: React.FC = () => {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''

  const [resultado, setResultado] = useState<'confirmado' | 'cancelado' | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [processando, setProcessando] = useState<'confirmar' | 'cancelar' | null>(null)

  const agir = async (cancelar: boolean) => {
    if (processando) return
    setErro(null)
    setProcessando(cancelar ? 'cancelar' : 'confirmar')
    try {
      await resolverTrocaEmail(token, cancelar)
      setResultado(cancelar ? 'cancelado' : 'confirmado')
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível processar o link.'))
    } finally {
      setProcessando(null)
    }
  }

  if (!token) {
    return (
      <AuthShell
        icone={<AlertTriangle size={22} />}
        titulo="Link inválido"
        subtitulo="Este endereço precisa do link completo que enviamos por e-mail."
      >
        <Link to="/login" style={{ ...botaoPrimario, display: 'block', textAlign: 'center', textDecoration: 'none' }}>
          Ir para o login
        </Link>
      </AuthShell>
    )
  }

  if (resultado === 'confirmado') {
    return (
      <AuthShell icone={<CheckCircle2 size={22} />} titulo="E-mail atualizado" subtitulo="A troca foi confirmada com sucesso.">
        <p className="text-sm leading-relaxed mb-6" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
          Por segurança, a recuperação de senha desta conta fica indisponível por 24 horas após uma
          troca de e-mail.
        </p>
        <Link to="/login" style={{ ...botaoPrimario, display: 'block', textAlign: 'center', textDecoration: 'none' }}>
          Ir para o login
        </Link>
      </AuthShell>
    )
  }

  if (resultado === 'cancelado') {
    return (
      <AuthShell icone={<XCircle size={22} />} titulo="Troca cancelada" subtitulo="Seu e-mail continua o mesmo.">
        <div
          className="text-sm leading-relaxed px-4 py-3 rounded-lg mb-6"
          style={{ background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e', fontFamily: 'var(--font-body)' }}
        >
          Se você não pediu esta troca, <b>avise o administrador da sua empresa</b>. O registro da
          tentativa ficou na trilha de segurança.
        </div>
        <Link to="/login" style={{ ...botaoPrimario, display: 'block', textAlign: 'center', textDecoration: 'none' }}>
          Ir para o login
        </Link>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      icone={<AtSign size={22} />}
      titulo="Confirmar troca de e-mail"
      subtitulo="Foi solicitada a troca do e-mail da sua conta. A mudança só vale se você confirmar aqui."
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

      <div
        className="text-sm leading-relaxed px-4 py-3 rounded-lg mb-6"
        style={{ background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e', fontFamily: 'var(--font-body)' }}
      >
        <b>Não foi você quem pediu?</b> Recuse abaixo. Quem controla o e-mail de uma conta consegue
        pedir a recuperação de senha dela — por isso a troca precisa passar por você.
      </div>

      <div className="flex flex-col gap-3">
        <button onClick={() => agir(false)} disabled={processando !== null} style={{ ...botaoPrimario, opacity: processando ? 0.7 : 1 }}>
          {processando === 'confirmar' ? (
            <span className="inline-flex items-center gap-2">
              <Loader2 size={16} className="animate-spin" /> Confirmando…
            </span>
          ) : (
            'Confirmar a troca'
          )}
        </button>
        <button onClick={() => agir(true)} disabled={processando !== null} style={{ ...botaoSecundario, opacity: processando ? 0.7 : 1 }}>
          {processando === 'cancelar' ? 'Cancelando…' : 'Não fui eu — recusar'}
        </button>
      </div>
    </AuthShell>
  )
}

export default ConfirmarEmailPage
