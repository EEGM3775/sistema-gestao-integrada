import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowUpRight, CheckCircle2, ChevronLeft, ClipboardCheck, Lock, ShieldCheck, XCircle,
} from 'lucide-react'
import { Btn, Card, Empty, Loading, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { dateToBR, maxCalendarioISO, maxTodayISO, minCalendarioISO } from '@/utils/dates'
import {
  useCancelarNc, useConcluirPlanoDeAcao, useCriarPlanoDeAcao, useEncerrarNc,
  useGerarRestricaoDaNc, useNc, useRegistrarEficacia,
} from '../hooks'
import { dataHora, emDias, primeiraFrase } from '../formato'
import { TOM_DA_GRAVIDADE, TOM_DO_STATUS_DA_NC } from '../vocabulario'
import { FotoProtegida } from './FotoProtegida'
import { Ajuda, Campo, Escolhas, FaixaDeErro, Grupo, Linha } from './Formulario'
import type { NaoConformidade, PlanoAcao, TipoPlanoAcao } from '../types'
import { entrada } from '../estilos'



/** **O defeito e o laço que o fecha**, numa página só.
 *
 *  Plano de ação e verificação de eficácia não são assuntos separados: são
 *  passos do mesmo laço, e por isso moram aqui, um embaixo do outro, na ordem
 *  em que acontecem. O servidor diz o que falta (`estado.falta`) e se já se
 *  pode encerrar (`estado.pode_encerrar`) — a tela lê, não recalcula.
 *
 *  **Só a eficácia encerra.** O botão de encerrar não existe enquanto ninguém
 *  voltou à frente e registrou que o conserto pegou; "concluí a ação" é
 *  declaração de quem executou, e é exatamente por isso que não fecha nada. */
export function DocumentoDaNc({
  ncId, obraId, aoVoltar,
}: { ncId: number; obraId: number; aoVoltar: () => void }) {
  const { hasPermission } = useAuth()
  const nc = useNc(ncId)
  const podeTratar = hasPermission('pdca.nc.tratar')
  const podeVerificar = hasPermission('pdca.nc.verificar_eficacia')
  const podeTravar = hasPermission('pdca.restricao.edit')

  if (nc.isLoading) return <Loading o="o defeito" />
  if (nc.isError || !nc.data) {
    return (
      <Card>
        <Empty>
          Este defeito não foi encontrado nesta obra — talvez o endereço seja de
          outra. <Voltar aoVoltar={aoVoltar} />
        </Empty>
      </Card>
    )
  }

  const dados = nc.data
  const aberta = dados.status === 'aberta' || dados.status === 'em_tratamento'
  const acoes = dados.acoes ?? []
  const eficacias = dados.eficacias ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 920 }}>
      <Voltar aoVoltar={aoVoltar} />

      <Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
          <Pill kind={TOM_DA_GRAVIDADE[dados.gravidade]}>
            {dados.gravidade_rotulo.split(' — ')[0]}
          </Pill>
          <Pill kind={TOM_DO_STATUS_DA_NC[dados.status]}>{dados.status_rotulo}</Pill>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--ink-3)' }}>
            NC {dados.nc_id}
          </span>
        </div>

        <h2 style={{ margin: '10px 0 0', fontSize: 17, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.4 }}>
          {dados.descricao}
        </h2>

        <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 6, lineHeight: 1.6 }}>
          {[dados.local_rotulo, dados.atividade_nome && `${dados.atividade_codigo ?? ''} ${dados.atividade_nome}`.trim()]
            .filter(Boolean).join(' · ') || 'Sem local nem atividade apontados'}
          <br />
          Aberta em {dataHora(dados.aberta_em)}
          {dados.aberta_por && ` por ${dados.aberta_por}`}
          {dados.gravidade_rotulo.includes(' — ') && (
            <> · {dados.gravidade_rotulo.split(' — ')[1]}</>
          )}
        </div>

        {aberta && dados.estado.falta && (
          <div
            style={{
              marginTop: 12, padding: '9px 12px', borderRadius: 'var(--r-sm)',
              background: 'var(--accent-soft)', color: 'var(--accent-ink)',
              fontSize: 13, fontWeight: 650,
            }}
          >
            Próximo passo: {dados.estado.falta}
          </div>
        )}

        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 14, alignItems: 'flex-start' }}>
          {dados.foto && <FotoProtegida url={dados.foto} alt="Foto do defeito" />}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12.5, minWidth: 220 }}>
            {dados.verificacao && (
              <Link
                to={`/app/pdca/o/${obraId}/qualidade?ficha=${dados.verificacao}`}
                style={linkDeIntegracao}
              >
                <ClipboardCheck size={14} />
                Veio de uma ficha de verificação
                <ArrowUpRight size={13} />
              </Link>
            )}
            <RestricaoDaNc nc={dados} obraId={obraId} podeTravar={podeTratar && podeTravar} />
          </div>
        </div>
      </Card>

      <PlanoDeAcao
        nc={dados}
        acoes={acoes}
        podeTratar={podeTratar && aberta}
      />

      <Eficacia
        nc={dados}
        podeVerificar={podeVerificar && aberta}
        historico={eficacias}
      />

      {aberta && (
        <Fechamento nc={dados} podeVerificar={podeVerificar} podeTratar={podeTratar} />
      )}

      {!aberta && (
        <Card>
          <div style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6 }}>
            {dados.status === 'encerrada' ? 'Encerrada' : 'Cancelada'} em{' '}
            {dataHora(dados.encerrada_em)}
            {dados.encerrada_por && ` por ${dados.encerrada_por}`}.
            {dados.nota_encerramento && (
              <div style={{ color: 'var(--ink-3)', marginTop: 4 }}>“{dados.nota_encerramento}”</div>
            )}
          </div>
        </Card>
      )}
    </div>
  )
}

const linkDeIntegracao = {
  display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--brand)',
  textDecoration: 'none', fontWeight: 650,
} as const

function Voltar({ aoVoltar }: { aoVoltar: () => void }) {
  return (
    <button
      type="button"
      onClick={aoVoltar}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 3, alignSelf: 'flex-start',
        background: 'none', border: 'none', padding: 0, cursor: 'pointer',
        fontSize: 12, color: 'var(--ink-3)',
      }}
    >
      <ChevronLeft size={13} />
      Todos os defeitos
    </button>
  )
}

/** O seam com o Last Planner, **visível**: se o defeito já parou o serviço,
 *  a tela diz e leva à semana; se não parou e pode parar, oferece. */
function RestricaoDaNc({
  nc, obraId, podeTravar,
}: { nc: NaoConformidade; obraId: number; podeTravar: boolean }) {
  const gerar = useGerarRestricaoDaNc()
  const [abrindo, setAbrindo] = useState(false)
  const [prazo, setPrazo] = useState('')
  const [responsavel, setResponsavel] = useState('')
  const [erro, setErro] = useState<string | null>(null)

  if (nc.restricao) {
    const aberta = nc.restricao_status === 'aberta'
    return (
      <Link to={`/app/pdca/o/${obraId}/semana`} style={linkDeIntegracao}>
        <Lock size={14} />
        {aberta ? 'Parou a frente no quadro da semana' : 'Parou a frente — já liberada'}
        <ArrowUpRight size={13} />
      </Link>
    )
  }

  const aberta = nc.status === 'aberta' || nc.status === 'em_tratamento'
  if (!aberta || !podeTravar) return null

  if (!nc.atividade) {
    return (
      <span style={{ color: 'var(--ink-3)', lineHeight: 1.5 }}>
        Sem atividade apontada, este defeito não tem como parar a frente no quadro.
      </span>
    )
  }

  if (!abrindo) {
    return (
      <Btn tam="sm" onClick={() => setAbrindo(true)} style={{ alignSelf: 'flex-start' }}>
        <Lock size={13} />
        Parar a frente até consertar
      </Btn>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: 10, border: '1px solid var(--line)', borderRadius: 'var(--r-sm)' }}>
      <span style={{ fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.5 }}>
        A atividade sai do quadro da semana até a restrição ser removida.
      </span>
      <Campo rotulo="Prazo para liberar">
        <input
          type="date" value={prazo} min={minCalendarioISO} max={maxCalendarioISO}
          onChange={(e) => setPrazo(e.target.value)} style={entrada}
        />
      </Campo>
      <Campo rotulo="Quem resolve">
        <input value={responsavel} onChange={(e) => setResponsavel(e.target.value)} style={entrada} />
      </Campo>
      <FaixaDeErro>{erro}</FaixaDeErro>
      <div style={{ display: 'flex', gap: 6 }}>
        <Btn tam="sm" onClick={() => setAbrindo(false)}>Voltar</Btn>
        <Btn
          tam="sm" variant="primary" disabled={gerar.isPending}
          onClick={async () => {
            setErro(null)
            try {
              await gerar.mutateAsync({
                id: nc.nc_id, corpo: { prazo: prazo || null, responsavel: responsavel.trim() },
              })
              setAbrindo(false)
            } catch (e) {
              setErro(primeiraFrase(e))
            }
          }}
        >
          Parar a frente
        </Btn>
      </div>
    </div>
  )
}

function Secao({
  titulo, sub, children,
}: { titulo: string; sub?: string; children: React.ReactNode }) {
  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>{titulo}</span>
        {sub && <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>{sub}</span>}
      </div>
      {children}
    </Card>
  )
}

/** O 5W2H. `o que` é o único obrigatório — os outros cinco são o que faz a
 *  ação ser cobrável, e a tela os pede sem exigir. */
function PlanoDeAcao({
  nc, acoes, podeTratar,
}: { nc: NaoConformidade; acoes: PlanoAcao[]; podeTratar: boolean }) {
  const criar = useCriarPlanoDeAcao()
  const concluir = useConcluirPlanoDeAcao()
  const [aberto, setAberto] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const vazio = { tipo: 'corretiva' as TipoPlanoAcao, o_que: '', por_que: '', onde: '', quando: '', quem: '', como: '', quanto: '' }
  const [form, setForm] = useState(vazio)
  const set = (campo: keyof typeof vazio, valor: string) => setForm((f) => ({ ...f, [campo]: valor }))

  return (
    <Secao
      titulo="Plano de ação"
      sub={acoes.length ? `${nc.estado.acoes_concluidas} de ${acoes.length} executadas` : undefined}
    >
      {acoes.length === 0 && !aberto && (
        <p style={{ margin: '0 0 10px', fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.6 }}>
          Ninguém pegou este defeito ainda. O plano diz quem conserta o quê, e até quando.
        </p>
      )}

      {acoes.map((acao) => {
        const vencida = acao.dias_para_o_prazo != null && acao.dias_para_o_prazo < 0
        const emAberto = acao.status === 'planejada' || acao.status === 'em_execucao'
        return (
          <div
            key={acao.plano_id}
            style={{
              display: 'flex', gap: 12, alignItems: 'flex-start', padding: '10px 0',
              borderTop: '1px solid var(--line-2)',
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <Pill kind={acao.tipo === 'preventiva' ? 'info' : 'slate'}>
                  {acao.tipo_rotulo.split(' — ')[0]}
                </Pill>
                <Pill kind={acao.status === 'concluida' ? 'good' : vencida ? 'danger' : 'slate'}>
                  {acao.status_rotulo}
                </Pill>
                {vencida && emAberto && (
                  <span style={{ fontSize: 11.5, color: 'var(--danger-ink)' }}>
                    {emDias(acao.dias_para_o_prazo ?? 0)} em atraso
                  </span>
                )}
              </div>
              <div style={{ fontSize: 13.5, color: 'var(--ink)', marginTop: 5, lineHeight: 1.45 }}>
                {acao.o_que}
              </div>
              <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 3, lineHeight: 1.55 }}>
                {[
                  acao.quem && `quem: ${acao.quem}`,
                  acao.quando && `até ${dateToBR(acao.quando)}`,
                  acao.onde && `onde: ${acao.onde}`,
                  acao.como && `como: ${acao.como}`,
                  acao.por_que && `por quê: ${acao.por_que}`,
                  acao.quanto && `quanto: ${acao.quanto}`,
                ].filter(Boolean).join(' · ') || 'sem responsável nem prazo'}
              </div>
            </div>
            {podeTratar && emAberto && (
              <Btn
                tam="sm" disabled={concluir.isPending}
                onClick={async () => {
                  setErro(null)
                  try { await concluir.mutateAsync(acao.plano_id) } catch (e) { setErro(primeiraFrase(e)) }
                }}
              >
                <CheckCircle2 size={13} />
                Executada
              </Btn>
            )}
          </div>
        )
      })}

      {podeTratar && !aberto && (
        <Btn tam="sm" variant={acoes.length ? 'ghost' : 'primary'} onClick={() => setAberto(true)} style={{ marginTop: 8 }}>
          {acoes.length ? 'Acrescentar ação' : 'Montar o plano de ação'}
        </Btn>
      )}

      {aberto && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10, paddingTop: 12, borderTop: '1px solid var(--line-2)' }}>
          <Grupo rotulo="Tipo">
            <Escolhas
              valor={form.tipo}
              aoEscolher={(v) => set('tipo', v)}
              opcoes={[
                { valor: 'corretiva', rotulo: 'Corretiva — conserta o que saiu errado' },
                { valor: 'preventiva', rotulo: 'Preventiva — evita que volte' },
              ]}
            />
          </Grupo>
          <Campo rotulo="O que será feito">
            <textarea rows={2} value={form.o_que} onChange={(e) => set('o_que', e.target.value)} style={{ ...entrada, resize: 'vertical' }} />
          </Campo>
          <Linha>
            <Campo rotulo="Quem">
              <input value={form.quem} onChange={(e) => set('quem', e.target.value)} style={entrada} />
            </Campo>
            <Campo rotulo="Até quando">
              <input type="date" value={form.quando} min={minCalendarioISO} max={maxCalendarioISO} onChange={(e) => set('quando', e.target.value)} style={entrada} />
            </Campo>
            <Campo rotulo="Onde">
              <input value={form.onde} onChange={(e) => set('onde', e.target.value)} style={entrada} />
            </Campo>
          </Linha>
          <Linha>
            <Campo rotulo="Como" larga>
              <input value={form.como} onChange={(e) => set('como', e.target.value)} style={entrada} />
            </Campo>
            <Campo rotulo="Por quê">
              <input value={form.por_que} onChange={(e) => set('por_que', e.target.value)} style={entrada} />
            </Campo>
            <Campo rotulo="Quanto custa">
              <input value={form.quanto} onChange={(e) => set('quanto', e.target.value)} style={entrada} />
              <Ajuda>Texto livre — uma estimativa basta.</Ajuda>
            </Campo>
          </Linha>
          <FaixaDeErro>{erro}</FaixaDeErro>
          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
            <Btn tam="sm" onClick={() => { setAberto(false); setErro(null) }}>Voltar</Btn>
            <Btn
              tam="sm" variant="primary" disabled={!form.o_que.trim() || criar.isPending}
              onClick={async () => {
                setErro(null)
                try {
                  await criar.mutateAsync({
                    nao_conformidade: nc.nc_id, tipo: form.tipo, o_que: form.o_que.trim(),
                    por_que: form.por_que.trim(), onde: form.onde.trim(),
                    quando: form.quando || null, quem: form.quem.trim(),
                    como: form.como.trim(), quanto: form.quanto.trim(),
                  })
                  setForm(vazio)
                  setAberto(false)
                } catch (e) {
                  setErro(primeiraFrase(e))
                }
              }}
            >
              Gravar ação
            </Btn>
          </div>
        </div>
      )}

      {!aberto && <FaixaDeErro>{erro}</FaixaDeErro>}
    </Secao>
  )
}

/** A volta à frente. **Evidência é obrigatória**: um "sim" sem dizer o que se
 *  olhou é carimbo. O "não" devolve o defeito ao tratamento — não fecha nada. */
function Eficacia({
  nc, podeVerificar, historico,
}: {
  nc: NaoConformidade
  podeVerificar: boolean
  historico: NonNullable<NaoConformidade['eficacias']>
}) {
  const registrar = useRegistrarEficacia()
  const [data, setData] = useState(maxTodayISO())
  const [eficaz, setEficaz] = useState<'sim' | 'nao' | null>(null)
  const [evidencia, setEvidencia] = useState('')
  const [erro, setErro] = useState<string | null>(null)

  const tudoExecutado = nc.estado.acoes > 0 && nc.estado.acoes_concluidas === nc.estado.acoes
  const esperando = tudoExecutado && !nc.estado.eficacia_verificada

  return (
    <Secao titulo="Eficácia" sub="só ela encerra o defeito">
      {historico.length === 0 && (
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.6 }}>
          {tudoExecutado
            ? 'O plano foi executado. Falta alguém voltar à frente e dizer se o conserto pegou.'
            : 'Confere-se depois que o plano for executado.'}
        </p>
      )}

      {historico.map((e) => (
        <div key={e.eficacia_id} style={{ display: 'flex', gap: 9, padding: '8px 0', borderTop: '1px solid var(--line-2)' }}>
          {e.eficaz
            ? <ShieldCheck size={16} style={{ color: 'var(--good-ink)', flexShrink: 0, marginTop: 1 }} />
            : <XCircle size={16} style={{ color: 'var(--danger-ink)', flexShrink: 0, marginTop: 1 }} />}
          <div style={{ fontSize: 12.5, lineHeight: 1.55 }}>
            <strong style={{ color: 'var(--ink)' }}>
              {e.eficaz ? 'Funcionou' : 'Não funcionou — voltou ao tratamento'}
            </strong>
            <span style={{ color: 'var(--ink-3)' }}> · {dateToBR(e.data)}{e.verificada_por && ` · ${e.verificada_por}`}</span>
            <div style={{ color: 'var(--ink-2)' }}>{e.evidencia}</div>
          </div>
        </div>
      ))}

      {podeVerificar && esperando && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10, paddingTop: 12, borderTop: '1px solid var(--line-2)' }}>
          <Grupo rotulo="O conserto pegou?">
            <Escolhas
              valor={eficaz}
              aoEscolher={setEficaz}
              opcoes={[
                { valor: 'sim', rotulo: 'Sim, funcionou', tom: 'good' },
                { valor: 'nao', rotulo: 'Não, voltou a acontecer', tom: 'danger' },
              ]}
            />
          </Grupo>
          <Linha>
            <Campo rotulo="Conferido em">
              <input type="date" value={data} min={minCalendarioISO} max={maxCalendarioISO} onChange={(e) => setData(e.target.value)} style={entrada} />
            </Campo>
            <Campo rotulo="O que você olhou" larga>
              <input value={evidencia} onChange={(e) => setEvidencia(e.target.value)} style={entrada} placeholder="Ex.: prumo conferido com nível laser nos 4 cantos" />
            </Campo>
          </Linha>
          <FaixaDeErro>{erro}</FaixaDeErro>
          <Btn
            variant="primary" tam="sm" style={{ alignSelf: 'flex-end' }}
            disabled={eficaz == null || !evidencia.trim() || !data || registrar.isPending}
            onClick={async () => {
              setErro(null)
              try {
                await registrar.mutateAsync({
                  id: nc.nc_id,
                  corpo: { data, eficaz: eficaz === 'sim', evidencia: evidencia.trim() },
                })
                setEficaz(null)
                setEvidencia('')
              } catch (e) {
                setErro(primeiraFrase(e))
              }
            }}
          >
            Registrar a verificação
          </Btn>
        </div>
      )}

      {!podeVerificar && esperando && (
        <p style={{ margin: '8px 0 0', fontSize: 12, color: 'var(--ink-3)' }}>
          Conferir a eficácia é de quem tem a permissão de verificar — quem montou
          o plano não assina que ele funcionou.
        </p>
      )}
    </Secao>
  )
}

function Fechamento({
  nc, podeVerificar, podeTratar,
}: { nc: NaoConformidade; podeVerificar: boolean; podeTratar: boolean }) {
  const encerrar = useEncerrarNc()
  const cancelar = useCancelarNc()
  const [nota, setNota] = useState('')
  const [cancelando, setCancelando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [erro, setErro] = useState<string | null>(null)

  if (!(podeVerificar && nc.estado.pode_encerrar) && !podeTratar) return null

  return (
    <Card>
      {podeVerificar && nc.estado.pode_encerrar && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <Campo rotulo="Nota de encerramento (opcional)" larga>
            <input value={nota} onChange={(e) => setNota(e.target.value)} style={entrada} />
          </Campo>
          <Btn
            variant="primary" disabled={encerrar.isPending}
            onClick={async () => {
              setErro(null)
              try { await encerrar.mutateAsync({ id: nc.nc_id, nota: nota.trim() }) } catch (e) { setErro(primeiraFrase(e)) }
            }}
          >
            Encerrar o defeito
          </Btn>
        </div>
      )}

      {podeTratar && (
        cancelando ? (
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap', marginTop: 10 }}>
            <Campo rotulo="Por que não era defeito" larga>
              <input value={motivo} onChange={(e) => setMotivo(e.target.value)} style={entrada} autoFocus />
            </Campo>
            <Btn onClick={() => setCancelando(false)}>Voltar</Btn>
            <Btn
              variant="perigo" disabled={!motivo.trim() || cancelar.isPending}
              onClick={async () => {
                setErro(null)
                try { await cancelar.mutateAsync({ id: nc.nc_id, motivo: motivo.trim() }) } catch (e) { setErro(primeiraFrase(e)) }
              }}
            >
              Cancelar o registro
            </Btn>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setCancelando(true)}
            style={{
              marginTop: podeVerificar && nc.estado.pode_encerrar ? 10 : 0,
              background: 'none', border: 'none', padding: 0, cursor: 'pointer',
              fontSize: 12, color: 'var(--ink-3)', textDecoration: 'underline',
            }}
          >
            Não era um defeito? Cancele o registro dizendo por quê.
          </button>
        )
      )}
      <div style={{ marginTop: erro ? 10 : 0 }}><FaixaDeErro>{erro}</FaixaDeErro></div>
    </Card>
  )
}

