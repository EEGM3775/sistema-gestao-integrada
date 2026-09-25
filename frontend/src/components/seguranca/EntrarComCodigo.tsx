import { useState } from 'react'
import { Btn } from '@/components/malha'
import { FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { entrarComCodigo, type SessaoComCodigos } from '@/api/segundoFator'
import { CampoCodigo } from './CampoCodigo'

interface EntrarComCodigoProps {
  desafio: string
  aoEntrar: (sessao: SessaoComCodigos, destino?: string) => void
  aoVencer: () => void
}

export function EntrarComCodigo({ desafio, aoEntrar, aoVencer }: EntrarComCodigoProps) {
  const [recuperacao, setRecuperacao] = useState(false)
  const [codigo, setCodigo] = useState('')
  const [erros, setErros] = useState<FieldErrors>({})
  const [enviando, setEnviando] = useState(false)
  const [depoisDaRecuperacao, setDepoisDaRecuperacao] = useState<SessaoComCodigos | null>(null)

  const completo = recuperacao ? codigo.replace(/-/g, '').length === 10 : codigo.length === 6

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!completo || enviando) return
    setErros({})
    setEnviando(true)
    try {
      const sessao = await entrarComCodigo(desafio, codigo)
      if (sessao.codigos_restantes !== undefined) setDepoisDaRecuperacao(sessao)
      else aoEntrar(sessao)
    } catch (err) {
      if ((err as { response?: { status?: number } })?.response?.status === 401) {
        aoVencer()
        return
      }
      setErros(parseApiErrors(err))
      setCodigo('')
    } finally {
      setEnviando(false)
    }
  }

  if (depoisDaRecuperacao) {
    const restantes = depoisDaRecuperacao.codigos_restantes ?? 0
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <p style={{ fontSize: 14, color: 'var(--ink)', lineHeight: 1.5, margin: 0 }}>
          Você entrou com um código de recuperação.{' '}
          {restantes > 0
            ? <>Restam <b>{restantes}</b>.</>
            : <b>Não resta nenhum.</b>}{' '}
          Se o celular foi perdido, cadastre o app de novo em <b>Minha conta › Segurança</b> e gere
          códigos novos.
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn type="button" variant="brand" onClick={() => aoEntrar(depoisDaRecuperacao, '/app/conta')}>
            Ir para Minha conta
          </Btn>
          <Btn type="button" onClick={() => aoEntrar(depoisDaRecuperacao)}>Continuar</Btn>
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={enviar} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.5, margin: 0 }}>
        {recuperacao
          ? 'Digite um dos códigos de recuperação que você guardou ao ativar o segundo fator. Cada um vale uma vez.'
          : 'Abra o app autenticador do celular e digite o código de 6 dígitos desta conta.'}
      </p>
      <FormErrorBanner errors={erros} />
      <CampoCodigo id="codigo-segundo-fator" valor={codigo} aoMudar={setCodigo} recuperacao={recuperacao} />
      <Btn type="submit" variant="brand" disabled={!completo || enviando} style={{ justifyContent: 'center', padding: '11px 14px' }}>
        {enviando ? 'Conferindo…' : 'Entrar'}
      </Btn>
      <button
        type="button"
        onClick={() => { setRecuperacao(v => !v); setCodigo(''); setErros({}) }}
        style={{ fontSize: 13, color: 'var(--brand)', background: 'none', border: 'none', cursor: 'pointer', alignSelf: 'center' }}
      >
        {recuperacao ? 'Usar o código do app' : 'Perdi o celular — usar um código de recuperação'}
      </button>
    </form>
  )
}
