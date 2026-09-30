import React, { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { ShieldCheck } from 'lucide-react'
import {
  confirmarIdentidade, lerEstadoConfirmacao, registrarConfirmador, type EstadoConfirmacao,
} from '@/api/confirmacao'

type Resolver = (confirmado: boolean) => void

function mensagemDeErro(erro: unknown, metodo: EstadoConfirmacao['metodo']): string {
  if (axios.isAxiosError(erro)) {
    const status = erro.response?.status
    if (status === 429) {
      return 'Muitas tentativas erradas seguidas. Por segurança, espere alguns minutos e tente de novo.'
    }
    if (status === 400) {
      return metodo === 'codigo' ? 'Código incorreto ou já usado. Use o código que o app mostra agora.' : 'Senha incorreta.'
    }
    if (status === 401) return 'Sua sessão terminou. Entre de novo para continuar.'
    if (!erro.response) return 'Sem conexão com o servidor. Nada foi feito; tente de novo.'
  }
  return 'Não foi possível confirmar agora. Nada foi feito; tente de novo em instantes.'
}

export const ConfirmacaoDialog: React.FC = () => {
  const [aberto, setAberto] = useState(false)
  const [estado, setEstado] = useState<EstadoConfirmacao | null>(null)
  const [valor, setValor] = useState('')
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)
  const resolver = useRef<Resolver | null>(null)

  useEffect(() => {
    registrarConfirmador(
      () =>
        new Promise<boolean>((resolve) => {
          resolver.current = resolve
          setValor('')
          setErro('')
          setEstado(null)
          setAberto(true)
          lerEstadoConfirmacao()
            .then(setEstado)
            .catch(() => setEstado({ metodo: 'senha', janela_s: 0, valida_ate: null }))
        }),
    )
    return () => registrarConfirmador(null)
  }, [])

  const fechar = (confirmado: boolean) => {
    setAberto(false)
    resolver.current?.(confirmado)
    resolver.current = null
  }

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!estado || !valor.trim()) return
    setEnviando(true)
    setErro('')
    try {
      await confirmarIdentidade(estado.metodo === 'codigo' ? { codigo: valor.trim() } : { senha: valor })
      fechar(true)
    } catch (err) {
      setErro(mensagemDeErro(err, estado.metodo))
    } finally {
      setEnviando(false)
    }
  }

  if (!aberto) return null
  const porCodigo = estado?.metodo === 'codigo'
  const minutos = estado ? Math.round(estado.janela_s / 60) : 0

  return (
    <>
      <div className="fixed inset-0 z-[60]" style={{ background: 'rgba(0,0,0,0.4)' }} />
      <form
        onSubmit={(e) => void enviar(e)}
        className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[70] rounded-2xl w-full max-w-md"
        style={{ background: '#FFFFFF', boxShadow: '0 20px 60px rgba(0,0,0,0.2)' }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="titulo-confirmacao"
      >
        <div className="p-6 pb-4 flex items-center gap-3" style={{ borderBottom: '1px solid #e2e8f0' }}>
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: '#e0f2fe', color: '#0369a1' }}
          >
            <ShieldCheck size={18} />
          </div>
          <div>
            <h2
              id="titulo-confirmacao"
              className="text-lg font-bold"
              style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-brand)' }}
            >
              Confirme que é você
            </h2>
            <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
              Esta ação mexe com dinheiro, acesso ou dado pessoal.
            </p>
          </div>
        </div>

        <div className="p-6 space-y-3" style={{ fontFamily: 'var(--font-body)' }}>
          <label className="block text-sm font-semibold" htmlFor="prova-confirmacao" style={{ color: 'var(--color-brand)' }}>
            {porCodigo ? 'Código do app autenticador' : 'Sua senha'}
          </label>
          <input
            id="prova-confirmacao"
            type={porCodigo ? 'text' : 'password'}
            inputMode={porCodigo ? 'numeric' : undefined}
            autoComplete={porCodigo ? 'one-time-code' : 'current-password'}
            maxLength={porCodigo ? 6 : undefined}
            autoFocus
            disabled={!estado}
            value={valor}
            onChange={(e) => setValor(porCodigo ? e.target.value.replace(/\D/g, '') : e.target.value)}
            className="w-full px-3 py-2 rounded-xl border text-sm"
            style={{ borderColor: '#cbd5e1' }}
          />
          {erro && (
            <p className="text-sm" role="alert" style={{ color: '#b91c1c' }}>
              ⚠ {erro}
            </p>
          )}
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {minutos > 0 && `Depois de confirmar, você não precisa confirmar de novo por ${minutos} min. `}
            {!porCodigo && estado && (
              <>
                Com o segundo fator ligado, a confirmação passa a ser pelo código do celular — mais seguro
                que a senha. <a href="/app/conta" onClick={() => fechar(false)} className="underline">Ativar em Minha conta</a>
              </>
            )}
          </p>
        </div>

        <div className="px-6 pb-6 flex gap-2 justify-end">
          <button
            type="button"
            onClick={() => fechar(false)}
            className="px-4 py-2 rounded-xl text-sm font-semibold"
            style={{ background: '#f1f5f9', color: 'var(--color-text-muted)' }}
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={!estado || enviando || !valor.trim()}
            className="px-4 py-2 rounded-xl text-sm font-semibold inline-flex items-center gap-2 disabled:opacity-60"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF' }}
          >
            <ShieldCheck size={16} />
            {enviando ? 'Confirmando…' : 'Confirmar e continuar'}
          </button>
        </div>
      </form>
    </>
  )
}
