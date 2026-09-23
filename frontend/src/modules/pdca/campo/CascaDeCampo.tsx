import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet } from 'react-router-dom'
import { Monitor, UserCog, WifiOff } from 'lucide-react'
import { Btn, Modal } from '@/components/malha'
import { ContextoDeCampo, type ContextoDoCampo } from './contexto'

const CHAVE_DO_NOME = 'pdca.campo.como'

/** **A casca da segunda superfície.** Sem rail, sem inspetor, sem grade.
 *
 *  O escritório e o canteiro não são o mesmo software em larguras diferentes: a
 *  física é oposta. Lá a densidade é máxima e o ato típico é decidir sobre o que
 *  os outros fizeram; aqui é **uma decisão por tela**, alvo de dedo com luva, e
 *  o ato é produzir o número que todo indicador acima consome.
 *
 *  **A ausência de trabalho sem rede é declarada**, e não disfarçada: enquanto
 *  o aplicativo instalável for fase de plataforma, nada fica guardado no
 *  celular. Recusar um apontamento é ruim; perdê-lo em silêncio é pior. */
export default function CascaDeCampo() {
  const [trocandoNome, setTrocandoNome] = useState(false)
  const [nomeDoServidor, setNomeDoServidor] = useState('')
  const [como, setComo] = useState<string>(() => {
    try {
      return localStorage.getItem(CHAVE_DO_NOME) ?? ''
    } catch {
      //: Navegador com armazenamento bloqueado continua funcionando — a escolha
      //: simplesmente não sobrevive a fechar a aba.
      return ''
    }
  })
  const [semRede, setSemRede] = useState(() => !navigator.onLine)

  useEffect(() => {
    const online = () => setSemRede(false)
    const offline = () => setSemRede(true)
    window.addEventListener('online', online)
    window.addEventListener('offline', offline)
    return () => {
      window.removeEventListener('online', online)
      window.removeEventListener('offline', offline)
    }
  }, [])

  const definirNomeDoServidor = useCallback((nome: string) => {
    setNomeDoServidor((atual) => (atual === nome ? atual : nome))
  }, [])

  function guardar(nome: string) {
    const limpo = nome.trim()
    setComo(limpo)
    try {
      if (limpo) localStorage.setItem(CHAVE_DO_NOME, limpo)
      else localStorage.removeItem(CHAVE_DO_NOME)
    } catch {
      // ver o comentário do estado inicial
    }
    setTrocandoNome(false)
  }

  const contexto = useMemo<ContextoDoCampo>(() => ({
    como,
    nomeDoServidor,
    definirNomeDoServidor,
    trocarNome: () => setTrocandoNome(true),
  }), [como, nomeDoServidor, definirNomeDoServidor])

  const exibido = como || nomeDoServidor

  return (
    <ContextoDeCampo.Provider value={contexto}>
      <div
        style={{
          minHeight: '100dvh', display: 'flex', flexDirection: 'column',
          background: 'var(--ground)',
        }}
      >
        <header
          style={{
            display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
            padding: '12px 14px', background: 'var(--surface)',
            borderBottom: '1px solid var(--line)',
            position: 'sticky', top: 0, zIndex: 20,
          }}
        >
          <div style={{ minWidth: 0, flex: 1 }}>
            <div
              style={{
                fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase',
                color: 'var(--ink-3)', fontWeight: 700,
              }}
            >
              Minha frente
            </div>
            <button
              type="button"
              onClick={() => setTrocandoNome(true)}
              title="Não é você? Escolha o nome com que o escritório o registrou no quadro."
              style={{
                display: 'flex', alignItems: 'center', gap: 6, padding: 0,
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--ink)', fontSize: 16, fontWeight: 700,
                fontFamily: 'inherit', maxWidth: '100%',
              }}
            >
              <span
                style={{
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}
              >
                {exibido || 'Quem é você?'}
              </span>
              <UserCog size={15} style={{ color: 'var(--ink-3)', flexShrink: 0 }} />
            </button>
          </div>

          <Link
            to="/app/pdca"
            title="Abrir a versão de escritório"
            aria-label="Abrir a versão de escritório"
            style={{
              display: 'grid', placeItems: 'center', width: 48, height: 48,
              borderRadius: 'var(--r-sm)', flexShrink: 0,
              background: 'var(--surface-2)', border: '1px solid var(--line)',
              color: 'var(--ink-2)', textDecoration: 'none',
            }}
          >
            <Monitor size={19} />
          </Link>
        </header>

        {semRede && (
          <div
            role="alert"
            style={{
              display: 'flex', alignItems: 'flex-start', gap: 9, flexShrink: 0,
              padding: '11px 14px', background: 'var(--danger-soft)',
              color: 'var(--danger-ink)', fontSize: 13, lineHeight: 1.5,
            }}
          >
            <WifiOff size={17} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>
              <strong>Sem sinal.</strong> Nada do que você escrever agora vai ser
              guardado — espere a rede voltar e registre de novo.
            </span>
          </div>
        )}

        <main style={{ flex: 1, minHeight: 0 }}>
          <Outlet />
        </main>

        <footer
          style={{
            flexShrink: 0, padding: '16px 18px 26px',
            fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.55,
            textAlign: 'center',
          }}
        >
          Esta tela precisa de rede para gravar. O que você registrar aqui aparece
          na hora para o escritório.
        </footer>

        {trocandoNome && (
          <DialogoDeNome
            atual={exibido}
            doCadastro={nomeDoServidor}
            personalizado={!!como}
            aoFechar={() => setTrocandoNome(false)}
            aoGuardar={guardar}
          />
        )}
      </div>
    </ContextoDeCampo.Provider>
  )
}

/** **Por que trocar o nome existe.** Quem assume a frente é escrito no quadro
 *  como rótulo de texto — "Mestre Antônio", "Equipe da laje" —, e esse rótulo
 *  nem sempre é o nome do login. Sem esta saída, a pessoa cujo cadastro diverge
 *  veria a frente vazia para sempre e concluiria que o sistema a esqueceu. */
function DialogoDeNome({
  atual, doCadastro, personalizado, aoFechar, aoGuardar,
}: {
  atual: string
  doCadastro: string
  personalizado: boolean
  aoFechar: () => void
  aoGuardar: (nome: string) => void
}) {
  const [nome, setNome] = useState(atual)

  return (
    <Modal
      titulo="Com que nome você aparece no quadro"
      onClose={aoFechar}
      largura={420}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Cancelar</Btn>
          <Btn variant="primary" onClick={() => aoGuardar(nome)}>Usar este nome</Btn>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
        <p style={{ fontSize: 13.5, color: 'var(--ink-2)', lineHeight: 1.6, margin: 0 }}>
          O escritório escreve quem assume cada frente na reunião da semana. Se o
          nome de lá for diferente do seu cadastro, escreva-o aqui — é por ele
          que o seu trabalho é encontrado. Acento e maiúscula não fazem diferença.
        </p>

        <input
          value={nome}
          autoFocus
          onChange={(e) => setNome(e.target.value)}
          placeholder={doCadastro || 'Seu nome no quadro'}
          style={{
            width: '100%', padding: '13px 14px', borderRadius: 10, fontSize: 17,
            border: '1px solid var(--line)', background: 'var(--surface)',
            color: 'var(--ink)', fontFamily: 'inherit',
          }}
        />

        {/* Aparece sempre que o nome foi trocado, mesmo sem sabermos qual é o
            do cadastro: quem abriu a tela já com a escolha guardada nunca viu o
            nome original, e é justamente essa pessoa que precisa da volta. */}
        {personalizado && (
          <button
            type="button"
            onClick={() => aoGuardar('')}
            style={{
              alignSelf: 'flex-start', background: 'none', border: 'none',
              padding: '8px 0', cursor: 'pointer', fontSize: 13,
              color: 'var(--brand)', fontFamily: 'inherit', textAlign: 'left',
            }}
          >
            Voltar ao nome do meu cadastro
          </button>
        )}
      </div>
    </Modal>
  )
}
