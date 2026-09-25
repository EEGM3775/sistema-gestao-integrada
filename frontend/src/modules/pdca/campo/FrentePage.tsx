import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle, Camera, ChevronRight, ClipboardList, Hammer, HardHat, Lock,
  MessagesSquare, Unlock,
} from 'lucide-react'
import { Loading, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { dateToBR } from '@/utils/dates'
import { emDias, percentual } from '../formato'
import { useMinhasFrentes, useRemoverRestricao } from '../hooks'
import { intervaloDaSemana } from '../semana'
import { SemPermissaoAviso } from '../components/SemPermissaoAviso'
import { useCampo } from './contexto'
import { DialogoDeDestrave } from './DialogoDeDestrave'
import type {
  BlocoDaFrente, CompromissoDaFrente, ConsertoDaFrente, FichaDaFrente,
  PrazoDaLinha, TravaDaFrente,
} from '../types'

/** **A home do campo: a minha frente de hoje.** Nada mais.
 *
 *  O que eu assumi nesta semana, o que está no meu nome para destravar, e o que
 *  vence hoje. Uma decisão por toque, alvo de dedo com luva. */
export default function FrentePage() {
  const { como, definirNomeDoServidor } = useCampo()
  const frente = useMinhasFrentes({ como: como || undefined })

  useEffect(() => {
    //: O nome que o cabeçalho mostra é o que o **servidor** procurou, e só vale
    //: como "o do meu cadastro" quando não mandamos nenhum — com `como`, a
    //: resposta devolve o próprio `como` de volta.
    if (!como && frente.data?.quem) definirNomeDoServidor(frente.data.quem)
  }, [como, frente.data?.quem, definirNomeDoServidor])

  if (frente.isLoading) return <Loading o="a sua frente de hoje" />

  if (frente.isError || !frente.data) {
    return (
      <Aviso tom="danger">
        Não foi possível carregar a sua frente. Confira o sinal e puxe a tela
        para baixo para tentar de novo.
      </Aviso>
    )
  }

  const dados = frente.data

  return (
    <div style={{ padding: '14px 14px 4px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
        Semana de {intervaloDaSemana(dados.semana_inicio, dados.semana_fim)}
      </div>

      {dados.sem_nome_porque && <Aviso tom="accent">{dados.sem_nome_porque}</Aviso>}

      {dados.sem_permissao.length > 0 && (
        <SemPermissaoAviso itens={dados.sem_permissao} />
      )}

      {dados.compromissos && <BlocoDeCompromissos bloco={dados.compromissos} />}

      {dados.restricoes && <BlocoDeTravas bloco={dados.restricoes} />}

      <TambemNoSeuNome acoes={dados.acoes} fichas={dados.fichas} />

      <Registrar obra={obraUnica(dados.compromissos?.linhas ?? [])} />
    </div>
  )
}

/** A obra da frente, **quando é uma só** — é o que os três atos de registro
 *  recebem preenchido. O mestre que cobre duas escolhe na própria tela. */
function obraUnica(linhas: CompromissoDaFrente[]): number | null {
  const obras = new Set(linhas.map((l) => l.obra))
  return obras.size === 1 ? [...obras][0] : null
}

/** **Os três atos que nascem no campo** e que o escritório só lê: o defeito
 *  (abre pela câmera), a ocorrência e o diálogo antes do turno. Cada um some
 *  para quem não tem a permissão — um botão que leva a um cadeado é pior que
 *  nenhum. */
function Registrar({ obra }: { obra: number | null }) {
  const { hasPermission } = useAuth()
  const sufixo = obra ? `?obra=${obra}` : ''
  const atos = [
    { para: `/campo/defeito${sufixo}`, rotulo: 'Defeito com foto', icone: Camera, pode: hasPermission('pdca.nc.abrir') },
    { para: `/campo/ocorrencia${sufixo}`, rotulo: 'Ocorrência de segurança', icone: HardHat, pode: hasPermission('pdca.ocorrencia.registrar') },
    { para: `/campo/dds${sufixo}`, rotulo: 'Diálogo de segurança', icone: MessagesSquare, pode: hasPermission('pdca.dds.registrar') },
  ].filter((a) => a.pode)
  if (atos.length === 0) return null

  return (
    <section>
      <div
        style={{
          fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase',
          color: 'var(--ink-3)', fontWeight: 700, marginBottom: 9,
        }}
      >
        Registrar
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 9 }}>
        {atos.map(({ para, rotulo, icone: Icone }) => (
          <Link
            key={para}
            to={para}
            style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              gap: 8, minHeight: 92, padding: 12, textAlign: 'center',
              background: 'var(--surface)', border: '1px solid var(--line)',
              borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-sm)',
              color: 'var(--ink)', textDecoration: 'none', fontSize: 14.5, fontWeight: 650,
            }}
          >
            <Icone size={24} style={{ color: 'var(--ink-2)' }} />
            {rotulo}
          </Link>
        ))}
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */

function BlocoDeCompromissos({ bloco }: { bloco: BlocoDaFrente<CompromissoDaFrente> }) {
  return (
    <section>
      <Titulo icone={<Hammer size={15} />} bloco={bloco} />
      {bloco.linhas.length === 0 ? (
        <Vazio>{bloco.vazio_porque}</Vazio>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          {bloco.linhas.map((linha) => (
            <Link
              key={linha.item}
              to={`/campo/apontar/${linha.atividade}?item=${linha.item}${linha.local ? `&local=${linha.local}` : ''}`}
              style={{
                display: 'block', textDecoration: 'none', color: 'inherit',
                background: 'var(--surface)', border: '1px solid var(--line)',
                borderRadius: 'var(--r-md)', padding: '13px 14px',
                minHeight: 48, boxShadow: 'var(--shadow-sm)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 16, fontWeight: 700, color: 'var(--ink)',
                      lineHeight: 1.35,
                    }}
                  >
                    {linha.nome}
                  </div>
                  <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 3 }}>
                    {linha.obra_nome}
                    {linha.local_rotulo && ` · ${linha.local_rotulo}`}
                  </div>
                </div>
                <ChevronRight size={20} style={{ color: 'var(--ink-3)', flexShrink: 0, marginTop: 2 }} />
              </div>

              <div
                style={{
                  display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 9,
                  fontSize: 13, color: 'var(--ink-2)',
                }}
              >
                {linha.previsto && (
                  <span>
                    assumiu{' '}
                    <strong className="num" style={{ color: 'var(--ink)' }}>
                      {percentual(linha.previsto)}
                    </strong>
                  </span>
                )}
                {linha.previsto && <span style={{ color: 'var(--ink-3)' }}>·</span>}
                <span>
                  {linha.apontou ? (
                    <>
                      já apontou{' '}
                      <strong className="num" style={{ color: 'var(--good-ink)' }}>
                        {percentual(linha.apontado)}
                      </strong>
                    </>
                  ) : (
                    <span style={{ color: 'var(--ink-3)' }}>ainda sem apontamento</span>
                  )}
                </span>
              </div>

              {(linha.restricoes_abertas > 0 || linha.ncs_abertas > 0 || linha.vezes_arrastado > 0) && (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 9 }}>
                  {linha.restricoes_abertas > 0 && (
                    <Pill kind="danger">
                      <Lock size={11} />
                      {linha.restricoes_abertas} trava{linha.restricoes_abertas > 1 ? 's' : ''}
                    </Pill>
                  )}
                  {linha.ncs_abertas > 0 && (
                    <Pill kind="accent">
                      {linha.ncs_abertas} defeito{linha.ncs_abertas > 1 ? 's' : ''} aberto{linha.ncs_abertas > 1 ? 's' : ''}
                    </Pill>
                  )}
                  {linha.vezes_arrastado > 0 && (
                    <Pill kind="info">{linha.vezes_arrastado + 1}ª semana</Pill>
                  )}
                </div>
              )}
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}

function BlocoDeTravas({ bloco }: { bloco: BlocoDaFrente<TravaDaFrente> }) {
  const { hasPermission } = useAuth()
  const [destravando, setDestravando] = useState<TravaDaFrente | null>(null)
  const remover = useRemoverRestricao(undefined)
  const podeDestravar = hasPermission('pdca.restricao.remover')

  if (bloco.linhas.length === 0) return null

  return (
    <section>
      <Titulo
        icone={<Unlock size={15} />}
        bloco={bloco}
        verbo={podeDestravar
          ? undefined
          : 'Avise o escritório quando alguma destas sair.'}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {bloco.linhas.map((linha) => (
          <div
            key={linha.restricao}
            style={{
              background: 'var(--surface)', border: '1px solid var(--line)',
              borderRadius: 'var(--r-md)', padding: '13px 14px',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
              <Pill kind="slate">{linha.tipo_rotulo}</Pill>
              <SeloDePrazo prazo={linha.prazo} />
            </div>
            <div
              style={{
                fontSize: 15, fontWeight: 650, color: 'var(--ink)',
                lineHeight: 1.4, marginTop: 8,
              }}
            >
              {linha.descricao}
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 4 }}>
              trava {linha.nome}
              {linha.local_rotulo && ` · ${linha.local_rotulo}`}
            </div>

            {podeDestravar && (
              <button
                type="button"
                onClick={() => setDestravando(linha)}
                style={{
                  marginTop: 11, width: '100%', minHeight: 48,
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  gap: 7, borderRadius: 10, cursor: 'pointer',
                  background: 'var(--accent)', color: '#1A1204', border: 'none',
                  fontSize: 15, fontWeight: 700, fontFamily: 'inherit',
                }}
              >
                <Unlock size={17} />
                Já está resolvida
              </button>
            )}
          </div>
        ))}
      </div>

      {destravando && (
        <DialogoDeDestrave
          trava={destravando}
          salvando={remover.isPending}
          aoFechar={() => setDestravando(null)}
          aoConfirmar={async (nota) => {
            await remover.mutateAsync({ id: destravando.restricao, nota })
            setDestravando(null)
          }}
        />
      )}
    </section>
  )
}

/** O que também está no nome da pessoa. **A ficha se responde daqui** — um
 *  toque abre a primeira pergunta sem resposta. O conserto do plano de ação
 *  continua sendo fechado no escritório, e a tela diz isso em vez de pôr um
 *  botão que não leva a lugar nenhum. Some quando não há nada, porque aviso
 *  que aparece sempre ensina a ignorar a tela. */
function TambemNoSeuNome({
  acoes, fichas,
}: {
  acoes: BlocoDaFrente<ConsertoDaFrente> | null
  fichas: BlocoDaFrente<FichaDaFrente> | null
}) {
  const consertos = acoes?.linhas ?? []
  const pendentes = fichas?.linhas ?? []
  if (consertos.length === 0 && pendentes.length === 0) return null

  return (
    <section>
      <div
        style={{
          fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase',
          color: 'var(--ink-3)', fontWeight: 700, marginBottom: 9,
          display: 'flex', alignItems: 'center', gap: 7,
        }}
      >
        <ClipboardList size={15} />
        Também está no seu nome
      </div>

      <div
        style={{
          background: 'var(--surface)', border: '1px solid var(--line)',
          borderRadius: 'var(--r-md)', overflow: 'hidden',
        }}
      >
        {consertos.map((conserto) => (
          <Linha
            key={`a${conserto.acao}`}
            titulo={conserto.o_que}
            detalhe={conserto.onde || conserto.defeito}
            prazo={conserto.prazo}
          />
        ))}
        {pendentes.map((ficha) => (
          <Link
            key={`f${ficha.verificacao}`}
            to={`/campo/ficha/${ficha.verificacao}`}
            style={{ display: 'block', textDecoration: 'none', color: 'inherit' }}
          >
            <Linha
              titulo={ficha.modelo_nome}
              detalhe={`${ficha.por_responder} pergunta${ficha.por_responder === 1 ? '' : 's'} sem resposta${ficha.onde ? ` · ${ficha.onde}` : ''} · tocar para responder`}
              prazo={null}
              desde={ficha.dias}
            />
          </Link>
        ))}
      </div>

      {consertos.length > 0 && (
        <p style={{ fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.55, margin: '9px 2px 0' }}>
          Quando um conserto estiver feito, avise o escritório — é lá que ele se dá por executado.
        </p>
      )}
    </section>
  )
}

function Linha({
  titulo, detalhe, prazo, desde,
}: {
  titulo: string
  detalhe: string
  prazo: PrazoDaLinha | null
  desde?: number
}) {
  return (
    <div
      style={{
        padding: '11px 13px', borderTop: '1px solid var(--line-2)',
        display: 'flex', alignItems: 'flex-start', gap: 10,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13.5, color: 'var(--ink)', lineHeight: 1.4 }}>
          {titulo}
        </div>
        {detalhe && (
          <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 2 }}>
            {detalhe}
          </div>
        )}
      </div>
      {prazo ? <SeloDePrazo prazo={prazo} /> : desde != null ? (
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)', flexShrink: 0 }}>
          há {emDias(desde)}
        </span>
      ) : null}
    </div>
  )
}

function SeloDePrazo({ prazo }: { prazo: PrazoDaLinha | null }) {
  if (!prazo) {
    return (
      <span style={{ fontSize: 11.5, color: 'var(--ink-3)', fontStyle: 'italic' }}>
        sem prazo
      </span>
    )
  }
  const dias = prazo.dias_restantes
  const texto = prazo.vencido
    ? `${emDias(dias)} em atraso`
    : dias === 0 ? 'vence hoje' : `faltam ${emDias(dias)}`
  return (
    <span style={{ flexShrink: 0 }}>
      <Pill
        kind={prazo.vencido ? 'danger' : dias <= 1 ? 'accent' : 'slate'}
        title={dateToBR(prazo.vence_em)}
      >
        {prazo.vencido && <AlertTriangle size={11} />}
        {texto}
      </Pill>
    </span>
  )
}

/** **Mensagem que manda fazer algo mostra o caminho** (convenções §12). O
 *  servidor manda o verbo que fecha o bloco, mas quem não tem a permissão não
 *  tem o botão — e anunciar "diga como foi removida" a quem não pode remover é
 *  mandar procurar um botão que não existe. Nesse caso o `verbo` é substituído
 *  pela frase que diz a quem pedir. */
function Titulo({
  icone, bloco, verbo,
}: {
  icone: React.ReactNode
  bloco: BlocoDaFrente<unknown>
  verbo?: string
}) {
  return (
    <div style={{ marginBottom: 9 }}>
      <div
        style={{
          fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase',
          color: 'var(--ink-3)', fontWeight: 700,
          display: 'flex', alignItems: 'center', gap: 7,
        }}
      >
        {icone}
        {bloco.rotulo}
        {bloco.linhas.length > 0 && (
          <span style={{ fontFamily: 'var(--mono)', letterSpacing: 0 }}>
            {bloco.linhas.length}
          </span>
        )}
      </div>
      {bloco.linhas.length > 0 && (
        <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 3 }}>
          {verbo ?? bloco.o_que_fazer}
        </div>
      )}
      {bloco.truncada && (
        <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 3 }}>
          Mostrando {bloco.linhas.length} de {bloco.total}.
        </div>
      )}
    </div>
  )
}

function Vazio({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        background: 'var(--surface)', border: '1px dashed var(--line)',
        borderRadius: 'var(--r-md)', padding: '18px 16px',
        fontSize: 13.5, color: 'var(--ink-3)', lineHeight: 1.6,
      }}
    >
      {children}
    </div>
  )
}

function Aviso({ tom, children }: { tom: 'danger' | 'accent'; children: React.ReactNode }) {
  return (
    <div
      style={{
        padding: '12px 14px', borderRadius: 'var(--r-md)', fontSize: 13.5,
        lineHeight: 1.55, background: `var(--${tom}-soft)`, color: `var(--${tom}-ink)`,
      }}
      role="alert"
    >
      {children}
    </div>
  )
}
