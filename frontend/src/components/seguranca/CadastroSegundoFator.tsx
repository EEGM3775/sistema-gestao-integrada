import { useEffect, useRef, useState } from 'react'
import { Loader2, Smartphone } from 'lucide-react'
import { Btn } from '@/components/malha'
import { FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import {
  confirmarCadastro, iniciarCadastro, type InicioCadastro, type SessaoComCodigos,
} from '@/api/segundoFator'
import { CampoCodigo } from './CampoCodigo'
import { CodigosDeRecuperacao } from './CodigosDeRecuperacao'

interface CadastroSegundoFatorProps {
  conta: string
  /** Vindo do login do administrador; sem ele, o cadastro é da sessão aberta. */
  desafio?: string
  aoConcluir: (sessao: SessaoComCodigos) => void
  aoCancelar?: () => void
  /** O login recomeça quando o passe da senha vence. */
  aoVencer?: () => void
}

type Passo = 'carregando' | 'ler' | 'codigos'

export function CadastroSegundoFator({ conta, desafio, aoConcluir, aoCancelar, aoVencer }: CadastroSegundoFatorProps) {
  const [passo, setPasso] = useState<Passo>('carregando')
  const [inicio, setInicio] = useState<InicioCadastro | null>(null)
  const [codigo, setCodigo] = useState('')
  const [sessao, setSessao] = useState<SessaoComCodigos | null>(null)
  const [erros, setErros] = useState<FieldErrors>({})
  const [enviando, setEnviando] = useState(false)
  const [mostrarChave, setMostrarChave] = useState(false)
  const venceu = useRef(aoVencer)
  venceu.current = aoVencer

  useEffect(() => {
    let vivo = true
    iniciarCadastro(desafio)
      .then(r => { if (vivo) { setInicio(r); setPasso('ler') } })
      .catch(err => {
        if (!vivo) return
        if ((err as { response?: { status?: number } })?.response?.status === 401 && venceu.current) venceu.current()
        else setErros(parseApiErrors(err))
      })
    return () => { vivo = false }
  }, [desafio])

  const confirmar = async (e: React.FormEvent) => {
    e.preventDefault()
    if (codigo.length !== 6 || enviando) return
    setErros({})
    setEnviando(true)
    try {
      const r = await confirmarCadastro(codigo, desafio)
      setSessao(r)
      setPasso('codigos')
    } catch (err) {
      if ((err as { response?: { status?: number } })?.response?.status === 401 && aoVencer) aoVencer()
      else setErros(parseApiErrors(err))
      setCodigo('')
    } finally {
      setEnviando(false)
    }
  }

  if (passo === 'codigos' && sessao) {
    return (
      <CodigosDeRecuperacao
        codigos={sessao.codigos ?? []}
        conta={conta}
        aoConcluir={() => aoConcluir(sessao)}
        rotuloConcluir={desafio ? 'Entrar' : 'Concluir'}
      />
    )
  }

  return (
    <form onSubmit={confirmar} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <FormErrorBanner errors={erros} />
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
        <Smartphone size={18} style={{ color: 'var(--brand)', flex: 'none', marginTop: 2 }} />
        <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.5, margin: 0 }}>
          Abra um app autenticador no celular (Google Authenticator, Microsoft Authenticator, Authy ou
          o do seu gerenciador de senhas), toque em <b>adicionar conta</b> e aponte a câmera para o
          código abaixo.
        </p>
      </div>

      {passo === 'carregando' && !erros._form && (
        <div style={{ display: 'grid', placeItems: 'center', height: 180 }}>
          <Loader2 size={22} className="animate-spin" style={{ color: 'var(--ink-3)' }} />
        </div>
      )}

      {inicio && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
          <img
            src={inicio.qr}
            alt="QR para cadastrar a conta no app autenticador"
            width={200}
            height={200}
            style={{ background: '#fff', padding: 6, borderRadius: 'var(--r-sm)', border: '1px solid var(--line)' }}
          />
          {mostrarChave ? (
            <code
              data-chave-segundo-fator
              style={{ fontSize: 13, letterSpacing: '0.08em', color: 'var(--ink)', wordBreak: 'break-all', textAlign: 'center' }}
            >
              {inicio.segredo.replace(/(.{4})/g, '$1 ').trim()}
            </code>
          ) : (
            <button
              type="button"
              onClick={() => setMostrarChave(true)}
              style={{ fontSize: 12, color: 'var(--brand)', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              Não consigo ler o QR — mostrar a chave para digitar
            </button>
          )}
        </div>
      )}

      <CampoCodigo
        id="codigo-cadastro-segundo-fator"
        valor={codigo}
        aoMudar={setCodigo}
        focar={!!inicio}
        rotulo="Digite o código que o app mostrar"
      />

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        {aoCancelar && <Btn type="button" onClick={aoCancelar}>Cancelar</Btn>}
        <Btn type="submit" variant="brand" disabled={codigo.length !== 6 || enviando || !inicio}>
          {enviando ? 'Conferindo…' : 'Ativar'}
        </Btn>
      </div>
    </form>
  )
}
