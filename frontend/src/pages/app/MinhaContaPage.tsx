import { useCallback, useEffect, useState } from 'react'
import { KeyRound, ShieldCheck, ShieldAlert, Timer } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Btn, Card, CampoInteiro, Loading, Modal, Pill, SectionHead } from '@/components/malha'
import { FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { dateToBR } from '@/utils/dates'
import { ChangePasswordModal } from '@/components/ChangePasswordModal'
import { PasswordField } from '@/components/PasswordField'
import { CadastroSegundoFator } from '@/components/seguranca/CadastroSegundoFator'
import { CampoCodigo } from '@/components/seguranca/CampoCodigo'
import { CodigosDeRecuperacao } from '@/components/seguranca/CodigosDeRecuperacao'
import {
  desativarSegundoFator, escolherJanela, iniciarTroca, lerSeguranca, trocarCodigos,
  type InicioCadastro, type MotivoSegundoFator, type SegurancaDaConta,
} from '@/api/segundoFator'

const POR_QUE: Record<MotivoSegundoFator, string> = {
  administrador: 'Sua conta administra a empresa: ela muda papéis, acessos e quem aprova pagamento. Para ela, o segundo fator é obrigatório.',
  alcada_financeira: 'Você aprova ou dá baixa em dinheiro. Uma senha vazada nesta conta vira pagamento indevido — é a conta que mais interessa a quem tenta invadir.',
  dado_de_saude: 'Você vê dados de saúde de outras pessoas. Um acesso indevido aqui expõe quem confiou esses dados à empresa.',
}

function ModalTrocarCodigos({ conta, aoFechar }: { conta: string; aoFechar: () => void }) {
  const [codigo, setCodigo] = useState('')
  const [novos, setNovos] = useState<string[] | null>(null)
  const [erros, setErros] = useState<FieldErrors>({})
  const [enviando, setEnviando] = useState(false)

  const gerar = async (e: React.FormEvent) => {
    e.preventDefault()
    setErros({})
    setEnviando(true)
    try {
      setNovos(await trocarCodigos(codigo))
    } catch (err) {
      setErros(parseApiErrors(err))
      setCodigo('')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal titulo="Gerar códigos de recuperação novos" onClose={aoFechar}>
      {novos ? (
        <CodigosDeRecuperacao codigos={novos} conta={conta} aoConcluir={aoFechar} rotuloConcluir="Fechar" />
      ) : (
        <form onSubmit={gerar} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <p style={{ fontSize: 13, color: 'var(--ink-2)', margin: 0, lineHeight: 1.5 }}>
            Os códigos antigos deixam de valer, inclusive os que você ainda não usou. Confirme com o
            código do app.
          </p>
          <FormErrorBanner errors={erros} />
          <CampoCodigo id="codigo-trocar-codigos" valor={codigo} aoMudar={setCodigo} />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Btn type="button" onClick={aoFechar}>Cancelar</Btn>
            <Btn type="submit" variant="brand" disabled={codigo.length !== 6 || enviando}>
              {enviando ? 'Gerando…' : 'Gerar códigos novos'}
            </Btn>
          </div>
        </form>
      )}
    </Modal>
  )
}

/** A senha e um código do celular atual (ou de recuperação) — o que desativar e
 *  trocar de celular pedem antes de mexer no segundo fator. */
function ProvaDosDoisFatores({ id, texto, rotulo, perigo, aoProvar, aoFechar }: {
  id: string
  texto: string
  rotulo: string
  perigo?: boolean
  aoProvar: (senha: string, codigo: string) => Promise<void>
  aoFechar: () => void
}) {
  const [senha, setSenha] = useState('')
  const [codigo, setCodigo] = useState('')
  const [recuperacao, setRecuperacao] = useState(false)
  const [erros, setErros] = useState<FieldErrors>({})
  const [enviando, setEnviando] = useState(false)

  const confirmar = async (e: React.FormEvent) => {
    e.preventDefault()
    setErros({})
    setEnviando(true)
    try {
      await aoProvar(senha, codigo)
    } catch (err) {
      setErros(parseApiErrors(err))
      setCodigo('')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form onSubmit={confirmar} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <p style={{ fontSize: 13, color: 'var(--ink-2)', margin: 0, lineHeight: 1.5 }}>{texto}</p>
      <FormErrorBanner errors={erros} />
      <PasswordField label="Sua senha" value={senha} onChange={setSenha} autoComplete="current-password" autoFocus />
      <CampoCodigo id={id} valor={codigo} aoMudar={setCodigo} recuperacao={recuperacao} focar={false} />
      <button
        type="button"
        onClick={() => { setRecuperacao(v => !v); setCodigo('') }}
        style={{ fontSize: 12, color: 'var(--brand)', background: 'none', border: 'none', cursor: 'pointer', alignSelf: 'flex-start' }}
      >
        {recuperacao ? 'Usar o código do app' : 'Estou sem o celular — usar um código de recuperação'}
      </button>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <Btn type="button" onClick={aoFechar}>Cancelar</Btn>
        <Btn type="submit" variant={perigo ? 'perigo' : 'brand'} disabled={!senha || !codigo || enviando}>
          {enviando ? 'Conferindo…' : rotulo}
        </Btn>
      </div>
    </form>
  )
}

/** Só para quem não é obrigado a ter segundo fator: o obrigado troca de celular (D241). */
function ModalDesativar({ aoFechar, aoDesativar }: { aoFechar: () => void; aoDesativar: () => void }) {
  return (
    <Modal titulo="Desativar o segundo fator" onClose={aoFechar}>
      <ProvaDosDoisFatores
        id="codigo-desativar"
        texto="Sem o segundo fator, quem descobrir sua senha entra na sua conta. Confirme com a senha e com o código do app — ou com um código de recuperação."
        rotulo="Desativar"
        perigo
        aoProvar={async (senha, codigo) => { await desativarSegundoFator(senha, codigo); aoDesativar() }}
        aoFechar={aoFechar}
      />
    </Modal>
  )
}

/** D241: o celular novo é lido e confirmado antes de o antigo sair — a conta
 *  nunca fica só com a senha. Fechar no meio não muda nada. */
function ModalTrocarCelular({ conta, aoFechar, aoTrocar }: {
  conta: string
  aoFechar: () => void
  aoTrocar: () => void
}) {
  const [inicio, setInicio] = useState<InicioCadastro | null>(null)

  return (
    <Modal titulo="Trocar de celular" onClose={aoFechar}>
      {inicio ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <p style={{ fontSize: 13, color: 'var(--ink-2)', margin: 0, lineHeight: 1.5 }}>
            Até você digitar o código do celular novo, o antigo continua valendo. Se fechar agora,
            nada muda.
          </p>
          <CadastroSegundoFator conta={conta} troca={inicio} aoConcluir={aoTrocar} aoCancelar={aoFechar} />
        </div>
      ) : (
        <ProvaDosDoisFatores
          id="codigo-trocar-celular"
          texto="Primeiro, confirme que é você: a senha e o código do celular atual — ou um código de recuperação, se você está sem ele. Em seguida, você lê um QR com o celular novo."
          rotulo="Continuar"
          aoProvar={async (senha, codigo) => setInicio(await iniciarTroca(senha, codigo))}
          aoFechar={aoFechar}
        />
      )}
    </Modal>
  )
}

function CartaoSegundoFator({ seguranca, conta, aoMudar }: {
  seguranca: SegurancaDaConta
  conta: string
  aoMudar: () => void
}) {
  const sf = seguranca.segundo_fator
  const [cadastrando, setCadastrando] = useState(false)
  const [trocandoCodigos, setTrocandoCodigos] = useState(false)
  const [trocandoCelular, setTrocandoCelular] = useState(false)
  const [desativando, setDesativando] = useState(false)

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        {sf.ativo
          ? <ShieldCheck size={20} style={{ color: 'var(--good-ink)' }} />
          : <ShieldAlert size={20} style={{ color: sf.obrigatorio ? 'var(--danger-ink)' : 'var(--ink-3)' }} />}
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>Segundo fator</h3>
        {sf.ativo
          ? <Pill kind="good">Ativo desde {sf.desde ? dateToBR(sf.desde.slice(0, 10)) : '—'}</Pill>
          : <Pill kind={sf.obrigatorio ? 'danger' : 'slate'}>{sf.obrigatorio ? 'Obrigatório — desligado' : 'Desligado'}</Pill>}
      </div>

      <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.55, margin: '0 0 12px' }}>
        Além da senha, a entrada passa a pedir um código de 6 dígitos que muda a cada 30 segundos no
        app autenticador do seu celular. Quem descobrir a senha, sozinha, não entra.
      </p>

      {!sf.ativo && sf.motivos.length > 0 && (
        <ul style={{ margin: '0 0 14px', paddingLeft: 18, fontSize: 13, color: 'var(--ink)', lineHeight: 1.55 }}>
          {sf.motivos.map(m => <li key={m}>{POR_QUE[m]}</li>)}
        </ul>
      )}

      {sf.bloqueado && (
        <p style={{ fontSize: 13, color: 'var(--danger-ink)', margin: '0 0 12px' }}>
          Muitos códigos errados seguidos: o segundo fator está travado por alguns minutos. Se não foi
          você, troque a senha agora.
        </p>
      )}

      {cadastrando ? (
        <div style={{ maxWidth: 420 }}>
          <CadastroSegundoFator
            conta={conta}
            aoConcluir={() => { setCadastrando(false); aoMudar() }}
            aoCancelar={() => setCadastrando(false)}
          />
        </div>
      ) : sf.ativo ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <p style={{ fontSize: 13, margin: 0, color: sf.codigos_restantes <= 3 ? 'var(--danger-ink)' : 'var(--ink-2)' }}>
            {sf.codigos_restantes === 0
              ? 'Você não tem mais códigos de recuperação. Gere novos antes de precisar deles.'
              : `Códigos de recuperação sem uso: ${sf.codigos_restantes}.`}
          </p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Btn onClick={() => setTrocandoCodigos(true)}>Gerar códigos novos</Btn>
            <Btn onClick={() => setTrocandoCelular(true)}>Trocar de celular</Btn>
            {!sf.obrigatorio && <Btn variant="perigo" onClick={() => setDesativando(true)}>Desativar</Btn>}
          </div>
        </div>
      ) : (
        <Btn variant="brand" onClick={() => setCadastrando(true)}>Ativar o segundo fator</Btn>
      )}

      {trocandoCodigos && (
        <ModalTrocarCodigos conta={conta} aoFechar={() => { setTrocandoCodigos(false); aoMudar() }} />
      )}
      {trocandoCelular && (
        <ModalTrocarCelular
          conta={conta}
          aoFechar={() => setTrocandoCelular(false)}
          aoTrocar={() => { setTrocandoCelular(false); aoMudar() }}
        />
      )}
      {desativando && (
        <ModalDesativar
          aoFechar={() => setDesativando(false)}
          aoDesativar={() => { setDesativando(false); aoMudar() }}
        />
      )}
    </Card>
  )
}

function CartaoJanela({ seguranca, aoSalvar }: {
  seguranca: SegurancaDaConta
  aoSalvar: (s: SegurancaDaConta) => void
}) {
  const j = seguranca.janela_confirmacao
  const [minutos, setMinutos] = useState(j.minutos)
  const [erros, setErros] = useState<FieldErrors>({})
  const [salvando, setSalvando] = useState(false)
  const [salvo, setSalvo] = useState(false)
  const foraDaFaixa = minutos < j.minimo || minutos > j.maximo

  const salvar = async () => {
    setErros({})
    setSalvando(true)
    try {
      aoSalvar(await escolherJanela(minutos))
      setSalvo(true)
    } catch (err) {
      setErros(parseApiErrors(err))
    } finally {
      setSalvando(false)
    }
  }

  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <Timer size={20} style={{ color: 'var(--ink-3)' }} />
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>Confirmação de atos graves</h3>
        <Pill kind="info">em breve</Pill>
      </div>
      <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.55, margin: '0 0 12px' }}>
        Atestar pagamento, mudar o papel de alguém e exportar dados pessoais vão pedir que você prove
        de novo quem é quando fizer mais de alguns minutos desde a última confirmação. Escolha esse
        tempo aqui; a escolha já fica guardada para quando a confirmação entrar no sistema.
      </p>
      <FormErrorBanner errors={erros} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <label htmlFor="janela-confirmacao" style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 600 }}>
          Confirmar de novo depois de
        </label>
        <CampoInteiro
          id="janela-confirmacao"
          valor={minutos}
          aoMudar={v => { setMinutos(v); setSalvo(false) }}
          max={j.maximo}
          style={{ width: 80 }}
        />
        <span style={{ fontSize: 13, color: 'var(--ink-2)' }}>minutos</span>
        <Btn variant="brand" tam="sm" disabled={foraDaFaixa || salvando || minutos === j.minutos} onClick={salvar}>
          {salvando ? 'Salvando…' : 'Salvar'}
        </Btn>
        {salvo && minutos === j.minutos && <span style={{ fontSize: 12, color: 'var(--good-ink)' }}>Salvo.</span>}
      </div>
      <p style={{ fontSize: 12, color: 'var(--ink-3)', margin: '8px 0 0' }}>
        De {j.minimo} a {j.maximo} minutos. O padrão é {j.padrao}.
      </p>
      {minutos > j.padrao && !foraDaFaixa && (
        <p style={{ fontSize: 13, color: 'var(--danger-ink)', margin: '8px 0 0' }}>
          Com {minutos} minutos, se você deixar a sessão aberta num computador, quem sentar nele pode
          aprovar sem confirmar nada durante esse tempo.
        </p>
      )}
      {!seguranca.segundo_fator.ativo && (
        <p style={{ fontSize: 12, color: 'var(--ink-3)', margin: '8px 0 0' }}>
          Sem o segundo fator, a confirmação é feita digitando a senha de novo. Isso protege do
          computador esquecido aberto, mas não de uma senha descoberta — o segundo fator protege dos dois.
        </p>
      )}
    </Card>
  )
}

export default function MinhaContaPage() {
  const { user } = useAuth()
  const [seguranca, setSeguranca] = useState<SegurancaDaConta | null>(null)
  const [erro, setErro] = useState<FieldErrors>({})
  const [trocandoSenha, setTrocandoSenha] = useState(false)

  const carregar = useCallback(() => {
    lerSeguranca().then(setSeguranca).catch(err => setErro(parseApiErrors(err)))
  }, [])
  useEffect(() => { carregar() }, [carregar])

  return (
    <div style={{ padding: '28px 26px', maxWidth: 760, display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 750, color: 'var(--ink)' }}>Minha conta</h1>
        <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--ink-3)' }}>
          {user?.username} · {user?.email}
        </p>
      </div>

      <SectionHead sub="Como a sua conta prova que é você">Segurança</SectionHead>
      <FormErrorBanner errors={erro} />
      {!seguranca && !erro._form && <Loading o="a segurança da conta" />}
      {seguranca && (
        <>
          <CartaoSegundoFator seguranca={seguranca} conta={user?.username ?? ''} aoMudar={carregar} />
          <CartaoJanela seguranca={seguranca} aoSalvar={setSeguranca} />
        </>
      )}
      <Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <KeyRound size={20} style={{ color: 'var(--ink-3)' }} />
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: 'var(--ink)', flex: 1 }}>Senha</h3>
          <Btn onClick={() => setTrocandoSenha(true)}>Alterar senha</Btn>
        </div>
      </Card>
      {trocandoSenha && <ChangePasswordModal onClose={() => setTrocandoSenha(false)} />}
    </div>
  )
}
