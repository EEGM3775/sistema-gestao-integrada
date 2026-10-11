import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertTriangle, ArrowUpRight, ChevronLeft, Clock, FileText, Lock, Paperclip, Search, ShieldAlert,
} from 'lucide-react'
import { Btn, Card, CampoInteiro, Empty, Loading, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { useFileUpload } from '@/hooks/useFileUpload'
import { abrirEmNovaAba } from '@/lib/arquivo'
import { dateToBR, maxCalendarioISO, maxTodayISO, minCalendarioISO } from '@/utils/dates'
import { dataHora, emDias, primeiraFrase } from '../formato'
import {
  useAnexarNaOcorrencia, useClassificarOcorrencia, useEncerrarOcorrencia,
  useInterditarFrente, useInvestigarOcorrencia, useOcorrencia, useRegistrarCat,
} from '../hooks'
import { Campo, Escolhas, FaixaDeErro, Grupo, Linha } from './Formulario'
import { entrada } from '../estilos'
import { TOM_DO_STATUS_DA_OCORRENCIA } from '../vocabulario'
import type {
  ClassificacaoOcorrencia, EspecieAnexo, Ocorrencia, PrazoDaCat, TipoCat,
} from '../types'

/** **O fato de segurança, e os verbos que ele separa.**
 *
 *  A CAT vem primeiro porque é a única coisa com prazo em lei. Classificar é
 *  de outra pessoa — quem é medido não classifica a própria medida —, o bloco
 *  clínico só abre para quem tem o verbo clínico, e investigar põe o fato na
 *  mesma máquina de tratamento dos defeitos, sem duplicá-la. */
export function DocumentoDaOcorrencia({
  ocorrenciaId, obraId, aoVoltar,
}: { ocorrenciaId: number; obraId: number; aoVoltar: () => void }) {
  const consulta = useOcorrencia(ocorrenciaId)

  if (consulta.isLoading) return <Loading o="a ocorrência" />
  if (consulta.isError || !consulta.data) {
    return <Card><Empty>Esta ocorrência não foi encontrada nesta obra.</Empty></Card>
  }

  const o = consulta.data
  const aberta = o.status === 'aberta' || o.status === 'em_investigacao'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 920 }}>
      <button
        type="button" onClick={aoVoltar}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 3, alignSelf: 'flex-start',
          background: 'none', border: 'none', padding: 0, cursor: 'pointer',
          fontSize: 12, color: 'var(--ink-3)',
        }}
      >
        <ChevronLeft size={13} />
        Todas as ocorrências
      </button>

      <Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
          <Pill kind={o.exige_cat ? 'danger' : 'slate'}>{o.tipo_rotulo.split(' (')[0]}</Pill>
          <Pill kind={TOM_DO_STATUS_DA_OCORRENCIA[o.status]}>{o.status_rotulo}</Pill>
          <Pill kind={o.classificacao === 'pendente' ? 'accent' : 'slate'}>{o.classificacao_rotulo}</Pill>
        </div>
        <h2 style={{ margin: '10px 0 0', fontSize: 17, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.4 }}>
          {o.descricao}
        </h2>
        <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 6, lineHeight: 1.6 }}>
          {dataHora(o.ocorrido_em)}
          {[o.local_rotulo, o.atividade_codigo].filter(Boolean).map((t) => ` · ${t}`).join('')}
          {o.acidentado_label && <> · {o.acidentado_label}</>}
          <br />
          Registrada por {o.registrada_por || 'não informado'}
          {o.agente_causador && <> · causa apontada: {o.agente_causador}</>}
        </div>
      </Card>

      {o.exige_cat && <BlocoDaCat ocorrencia={o} />}
      <Classificacao ocorrencia={o} aberta={aberta} />
      <BlocoClinico ocorrencia={o} />
      <Tratamento ocorrencia={o} obraId={obraId} aberta={aberta} />
      <Anexos ocorrencia={o} aberta={aberta} />
      {aberta && <Encerramento ocorrencia={o} />}
      {!aberta && (
        <Card>
          <div style={{ fontSize: 13, color: 'var(--ink-2)' }}>
            {o.status_rotulo} em {dataHora(o.encerrada_em)}
            {o.encerrada_por && ` por ${o.encerrada_por}`}.
            {o.nota_encerramento && <div style={{ color: 'var(--ink-3)', marginTop: 4 }}>“{o.nota_encerramento}”</div>}
          </div>
        </Card>
      )}
    </div>
  )
}

function Secao({
  titulo, icone, children, destaque,
}: { titulo: string; icone?: React.ReactNode; children: React.ReactNode; destaque?: boolean }) {
  return (
    <Card style={destaque ? { borderColor: 'var(--danger-ink)' } : undefined}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 10 }}>
        {icone}
        <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>{titulo}</span>
      </div>
      {children}
    </Card>
  )
}

/** O prazo da CAT, decidido pelo servidor — e a frase diz quantos dias,
 *  porque "vencido" sozinho não separa ontem de dois meses. */
export function SeloDaCat({ prazo }: { prazo: PrazoDaCat }) {
  if (!prazo.exige) return null
  if (prazo.emitida) return <Pill kind="good">CAT comunicada</Pill>
  const hoje = new Date()
  hoje.setHours(12, 0, 0, 0)
  const vence = new Date(`${prazo.vence_em}T12:00:00`)
  const dias = Math.round((vence.getTime() - hoje.getTime()) / 86_400_000)
  const texto = prazo.vencido
    ? `${emDias(dias)} em atraso`
    : prazo.imediata ? 'imediata' : dias === 0 ? 'vence hoje' : `faltam ${emDias(dias)}`
  return (
    <Pill kind={prazo.vencido || prazo.imediata || dias <= 0 ? 'danger' : 'accent'} title={prazo.base_legal}>
      <Clock size={11} />
      CAT {texto}
    </Pill>
  )
}

function BlocoDaCat({ ocorrencia }: { ocorrencia: Ocorrencia }) {
  const { hasPermission } = useAuth()
  const registrar = useRegistrarCat()
  const pode = hasPermission('pdca.ocorrencia.emitir_cat')
  const prazo = ocorrencia.prazo_cat
  const [tipo, setTipo] = useState<TipoCat>(ocorrencia.classificacao === 'obito' ? 'obito' : 'inicial')
  const [emitida, setEmitida] = useState(maxTodayISO())
  const [protocolo, setProtocolo] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  if (!prazo.exige) return null

  return (
    <Secao
      titulo="Comunicação de acidente (CAT)"
      icone={<ShieldAlert size={16} style={{ color: 'var(--danger-ink)' }} />}
      destaque={!prazo.emitida}
    >
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <SeloDaCat prazo={prazo} />
        <span style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
          {prazo.imediata
            ? 'Em caso de morte, a comunicação é imediata.'
            : `Vence em ${dateToBR(prazo.vence_em)} — 1º dia útil depois do acidente.`}
        </span>
      </div>
      {!prazo.feriados_carregados && !prazo.emitida && (
        <p style={{ margin: '6px 0 0', fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
          O prazo pula sábado e domingo, mas os feriados nacionais ainda não foram
          carregados no sistema — se houver feriado no caminho, o prazo real é um dia depois.
        </p>
      )}

      {prazo.emitida ? (
        <div style={{ fontSize: 13, color: 'var(--ink-2)', marginTop: 10, lineHeight: 1.6 }}>
          {ocorrencia.cat_tipo && <>CAT {ocorrencia.cat_tipo === 'obito' ? 'de óbito' : ocorrencia.cat_tipo} · </>}
          emitida em {dateToBR(ocorrencia.cat_emitida_em ?? '')}
          {ocorrencia.cat_protocolo ? <> · protocolo <strong>{ocorrencia.cat_protocolo}</strong></> : ' · sem protocolo anotado'}
          {ocorrencia.cat_registrada_por && <> · anotado por {ocorrencia.cat_registrada_por}</>}
        </div>
      ) : pode ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 12 }}>
          <Grupo rotulo="Tipo de CAT">
            <Escolhas
              valor={tipo} aoEscolher={setTipo}
              opcoes={[
                { valor: 'inicial', rotulo: 'Inicial' },
                { valor: 'reabertura', rotulo: 'Reabertura' },
                { valor: 'obito', rotulo: 'Comunicação de óbito' },
              ]}
            />
          </Grupo>
          <Linha>
            <Campo rotulo="Emitida em">
              <input type="date" value={emitida} min={minCalendarioISO} max={maxCalendarioISO}
                onChange={(e) => setEmitida(e.target.value)} style={entrada} />
            </Campo>
            <Campo rotulo="Protocolo" larga>
              <input value={protocolo} onChange={(e) => setProtocolo(e.target.value)} style={entrada} />
            </Campo>
          </Linha>
          <p style={{ margin: 0, fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
            A transmissão ao eSocial é feita pela folha. Aqui fica o registro de que
            a CAT foi comunicada, com o protocolo que prova.
          </p>
          <FaixaDeErro>{erro}</FaixaDeErro>
          {aviso && <div style={{ fontSize: 12.5, color: 'var(--accent-ink)' }}>{aviso}</div>}
          <Btn
            variant="primary" style={{ alignSelf: 'flex-end' }}
            disabled={!emitida || registrar.isPending}
            onClick={async () => {
              setErro(null)
              setAviso(null)
              try {
                const r = await registrar.mutateAsync({
                  id: ocorrencia.ocorrencia_id,
                  corpo: { tipo, emitida_em: emitida, protocolo: protocolo.trim() },
                })
                if (!r.dentro_do_prazo) {
                  setAviso('Registrada fora do prazo legal. O registro fica, com a data verdadeira.')
                }
              } catch (e) {
                setErro(primeiraFrase(e))
              }
            }}
          >
            Registrar a CAT
          </Btn>
        </div>
      ) : (
        <p style={{ margin: '10px 0 0', fontSize: 12.5, color: 'var(--ink-3)' }}>
          Quem registra a CAT é o RH ou quem tem a permissão de comunicar acidente.
        </p>
      )}
    </Secao>
  )
}

/** Classificar é o verbo estreito. Afastamento sem dias é classificação pela
 *  metade — e o servidor recusa com a frase; aqui o botão só espera o número. */
function Classificacao({ ocorrencia, aberta }: { ocorrencia: Ocorrencia; aberta: boolean }) {
  const { hasPermission } = useAuth()
  const classificar = useClassificarOcorrencia()
  const pode = hasPermission('pdca.ocorrencia.classificar') && aberta
  const semVitima = ocorrencia.tipo === 'quase_acidente' || ocorrencia.tipo === 'incidente'
  type Escolha = Exclude<ClassificacaoOcorrencia, 'pendente'>
  const [valor, setValor] = useState<Escolha | null>(
    ocorrencia.classificacao === 'pendente' ? null : ocorrencia.classificacao,
  )
  const [perdidos, setPerdidos] = useState(ocorrencia.dias_perdidos ?? 0)
  const [debitados, setDebitados] = useState(ocorrencia.dias_debitados ?? 6000)
  const [erro, setErro] = useState<string | null>(null)

  const opcoes: { valor: Escolha; rotulo: string; tom?: 'slate' | 'accent' | 'danger' }[] = semVitima
    ? [{ valor: 'sem_afastamento', rotulo: 'Sem afastamento', tom: 'slate' }]
    : [
        { valor: 'sem_afastamento', rotulo: 'Sem afastamento', tom: 'slate' },
        { valor: 'com_afastamento', rotulo: 'Com afastamento', tom: 'accent' },
        { valor: 'obito', rotulo: 'Óbito', tom: 'danger' },
      ]

  return (
    <Secao titulo="Classificação">
      {ocorrencia.classificacao !== 'pendente' && (
        <div style={{ fontSize: 13, color: 'var(--ink-2)', marginBottom: pode ? 10 : 0 }}>
          {ocorrencia.classificacao_rotulo}
          {ocorrencia.dias_perdidos != null && ` · ${ocorrencia.dias_perdidos} dias perdidos`}
          {ocorrencia.dias_debitados != null && ` · ${ocorrencia.dias_debitados} dias debitados`}
          {ocorrencia.classificada_por && <span style={{ color: 'var(--ink-3)' }}> · por {ocorrencia.classificada_por}</span>}
        </div>
      )}
      {!pode && ocorrencia.classificacao === 'pendente' && (
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-3)' }}>
          Ainda não classificada. Quem classifica é o técnico de segurança — não quem
          registrou, porque quem é medido não classifica a própria medida.
        </p>
      )}
      {pode && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <Escolhas valor={valor} aoEscolher={setValor} opcoes={opcoes} />
          {semVitima && (
            <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
              Sem vítima não há afastamento. Se alguém se feriu, o tipo registrado está errado.
            </span>
          )}
          {valor === 'com_afastamento' && (
            <Campo rotulo="Dias perdidos">
              <CampoInteiro valor={perdidos} aoMudar={setPerdidos} min={0} aria-label="Dias perdidos" />
            </Campo>
          )}
          {valor === 'obito' && (
            <Campo rotulo="Dias debitados">
              <CampoInteiro valor={debitados} aoMudar={setDebitados} min={0} aria-label="Dias debitados" />
            </Campo>
          )}
          <FaixaDeErro>{erro}</FaixaDeErro>
          <Btn
            tam="sm" variant="primary" style={{ alignSelf: 'flex-start' }}
            disabled={!valor || classificar.isPending}
            onClick={async () => {
              if (!valor) return
              setErro(null)
              try {
                await classificar.mutateAsync({
                  id: ocorrencia.ocorrencia_id,
                  corpo: {
                    classificacao: valor,
                    dias_perdidos: valor === 'com_afastamento' ? perdidos : null,
                    dias_debitados: valor === 'obito' ? debitados : null,
                  },
                })
              } catch (e) {
                setErro(primeiraFrase(e))
              }
            }}
          >
            {ocorrencia.classificacao === 'pendente' ? 'Classificar' : 'Reclassificar'}
          </Btn>
        </div>
      )}
    </Secao>
  )
}

/** **A primeira PII do módulo.** Lesão, CID e atestado vêm mascarados do
 *  servidor para quem não tem o verbo clínico; a tela diz por quê, em vez de
 *  mostrar bolinhas que parecem defeito. */
function BlocoClinico({ ocorrencia }: { ocorrencia: Ocorrencia }) {
  const { hasPermission } = useAuth()
  if (!ocorrencia.exige_cat && !ocorrencia.parte_do_corpo && !ocorrencia.natureza_lesao) return null
  const pode = hasPermission('pdca.ocorrencia.dado_medico')

  return (
    <Secao titulo="Lesão e saúde" icone={<Lock size={14} style={{ color: 'var(--ink-3)' }} />}>
      <div style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.7 }}>
        {ocorrencia.parte_do_corpo
          ? <>Parte do corpo: {ocorrencia.parte_do_corpo}{ocorrencia.lateralidade && ` (${ocorrencia.lateralidade})`}</>
          : <span style={{ color: 'var(--ink-3)' }}>Parte do corpo não informada.</span>}
      </div>
      {pode ? (
        <div style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.7 }}>
          Natureza da lesão: {ocorrencia.natureza_lesao || '—'}
          <br />CID-10: {ocorrencia.cid10 || '—'}
          <br />Atestado: {ocorrencia.atestado_dias != null && ocorrencia.atestado_dias !== '' ? `${ocorrencia.atestado_dias} dias` : '—'}
          {ocorrencia.houve_internacao && <><br />Houve internação.</>}
        </div>
      ) : (
        <p style={{ margin: '6px 0 0', fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.55 }}>
          Diagnóstico, CID e atestado são dado de saúde e ficam visíveis só para quem
          tem a permissão clínica. Para classificar o acidente, ninguém precisa deles.
        </p>
      )}
    </Secao>
  )
}

/** Os dois seams **visíveis**: se o fato já entrou na máquina de tratamento, e
 *  se ele já parou o serviço. */
function Tratamento({
  ocorrencia, obraId, aberta,
}: { ocorrencia: Ocorrencia; obraId: number; aberta: boolean }) {
  const { hasPermission } = useAuth()
  const navigate = useNavigate()
  const investigar = useInvestigarOcorrencia()
  const interditar = useInterditarFrente()
  const [prazo, setPrazo] = useState('')
  const [interditando, setInterditando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  const podeInvestigar = aberta && hasPermission('pdca.ocorrencia.registrar') && hasPermission('pdca.nc.abrir')
  const podeInterditar = aberta && hasPermission('pdca.ocorrencia.classificar') && hasPermission('pdca.restricao.edit')
  const link = { display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--brand)', textDecoration: 'none', fontWeight: 650, fontSize: 13 } as const

  return (
    <Secao titulo="Investigação e frente">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {ocorrencia.nao_conformidade ? (
          <Link to={`/app/pdca/o/${obraId}/qualidade?nc=${ocorrencia.nao_conformidade}`} style={link}>
            <Search size={14} />
            Em investigação no defeito NC {ocorrencia.nao_conformidade}
            {ocorrencia.nc_status === 'encerrada' && ' — encerrado'}
            <ArrowUpRight size={13} />
          </Link>
        ) : podeInvestigar ? (
          <div>
            <Btn
              tam="sm" disabled={investigar.isPending}
              onClick={async () => {
                setErro(null)
                try {
                  const r = await investigar.mutateAsync(ocorrencia.ocorrencia_id)
                  navigate(`/app/pdca/o/${obraId}/qualidade?nc=${r.nc}`)
                } catch (e) {
                  setErro(primeiraFrase(e))
                }
              }}
            >
              <Search size={13} />
              Investigar a causa
            </Btn>
            <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 5, lineHeight: 1.5 }}>
              Abre um defeito com plano de ação e verificação de eficácia — o mesmo
              laço da qualidade.
            </div>
          </div>
        ) : (
          <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Ainda sem investigação aberta.</span>
        )}

        {ocorrencia.restricao ? (
          <Link to={`/app/pdca/o/${obraId}/controle?aba=semana`} style={link}>
            <Lock size={14} />
            {ocorrencia.restricao_status === 'aberta'
              ? 'Frente interditada no quadro da semana'
              : 'Frente interditada — já liberada'}
            <ArrowUpRight size={13} />
          </Link>
        ) : podeInterditar ? (
          ocorrencia.atividade == null ? (
            <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
              Sem serviço apontado, não há frente para interditar.
            </span>
          ) : interditando ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <Campo rotulo="Até quando (opcional)">
                <input type="date" value={prazo} min={minCalendarioISO} max={maxCalendarioISO}
                  onChange={(e) => setPrazo(e.target.value)} style={entrada} />
              </Campo>
              <Btn tam="sm" onClick={() => setInterditando(false)}>Voltar</Btn>
              <Btn
                tam="sm" variant="perigo" disabled={interditar.isPending}
                onClick={async () => {
                  setErro(null)
                  try {
                    await interditar.mutateAsync({ id: ocorrencia.ocorrencia_id, prazo: prazo || null })
                    setInterditando(false)
                  } catch (e) {
                    setErro(primeiraFrase(e))
                  }
                }}
              >
                Interditar a frente
              </Btn>
            </div>
          ) : (
            <Btn tam="sm" variant="perigo" onClick={() => setInterditando(true)} style={{ alignSelf: 'flex-start' }}>
              <AlertTriangle size={13} />
              Interditar a frente
            </Btn>
          )
        ) : null}
        <FaixaDeErro>{erro}</FaixaDeErro>
      </div>
    </Secao>
  )
}

const ESPECIES: { valor: EspecieAnexo; rotulo: string; clinico?: boolean }[] = [
  { valor: 'cena', rotulo: 'Foto da cena' },
  { valor: 'boletim', rotulo: 'Boletim de ocorrência' },
  { valor: 'lista_presenca', rotulo: 'Lista de presença' },
  { valor: 'atestado', rotulo: 'Atestado médico', clinico: true },
  { valor: 'outro', rotulo: 'Outro' },
]

/** Os arquivos. O atestado sai por uma porta própria, que exige o verbo
 *  clínico — por isso só quem o tem vê a opção de enviá-lo. */
function Anexos({ ocorrencia, aberta }: { ocorrencia: Ocorrencia; aberta: boolean }) {
  const { hasPermission } = useAuth()
  const anexar = useAnexarNaOcorrencia()
  const { validate } = useFileUpload()
  const podeEnviar = aberta && hasPermission('pdca.ocorrencia.registrar')
  const clinico = hasPermission('pdca.ocorrencia.dado_medico')
  const [especie, setEspecie] = useState<EspecieAnexo>('cena')
  const [erro, setErro] = useState<string | null>(null)

  return (
    <Secao titulo="Anexos" icone={<Paperclip size={14} style={{ color: 'var(--ink-3)' }} />}>
      {ocorrencia.anexos.length === 0 && (
        <p style={{ margin: '0 0 8px', fontSize: 12.5, color: 'var(--ink-3)' }}>Nenhum arquivo ainda.</p>
      )}
      {ocorrencia.anexos.map((a) => (
        <div key={a.anexo_id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '6px 0', borderTop: '1px solid var(--line-2)', fontSize: 12.5 }}>
          <FileText size={14} style={{ color: 'var(--ink-3)' }} />
          <span style={{ flex: 1, color: 'var(--ink)' }}>
            {a.especie_rotulo}{a.descricao && ` — ${a.descricao}`}
          </span>
          <span style={{ color: 'var(--ink-3)' }}>{dataHora(a.enviado_em)}</span>
          {a.arquivo && (
            <Btn tam="sm" onClick={() => { void abrirEmNovaAba(a.arquivo as string) }}>Abrir</Btn>
          )}
        </div>
      ))}
      {podeEnviar && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginTop: 10 }}>
          <select
            value={especie}
            onChange={(e) => setEspecie(e.target.value as EspecieAnexo)}
            aria-label="Tipo de anexo"
            style={{ ...entrada, width: 'auto' }}
          >
            {ESPECIES.filter((e) => !e.clinico || clinico).map((e) => (
              <option key={e.valor} value={e.valor}>{e.rotulo}</option>
            ))}
          </select>
          <input
            type="file"
            aria-label="Arquivo do anexo"
            disabled={anexar.isPending}
            onChange={async (e) => {
              const arquivo = e.target.files?.[0]
              e.target.value = ''
              if (!arquivo) return
              const problema = validate(arquivo)
              if (problema) { setErro(problema); return }
              setErro(null)
              try {
                await anexar.mutateAsync({ ocorrencia: ocorrencia.ocorrencia_id, especie, arquivo })
              } catch (err) {
                setErro(primeiraFrase(err))
              }
            }}
            style={{ fontSize: 12.5 }}
          />
        </div>
      )}
      <div style={{ marginTop: erro ? 8 : 0 }}><FaixaDeErro>{erro}</FaixaDeErro></div>
    </Secao>
  )
}

/** Encerrar recusa por cima de frente interditada e de classificação pendente
 *  — e é o servidor quem diz; a tela mostra a frase dele. */
function Encerramento({ ocorrencia }: { ocorrencia: Ocorrencia }) {
  const { hasPermission } = useAuth()
  const encerrar = useEncerrarOcorrencia()
  const [nota, setNota] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  if (!hasPermission('pdca.ocorrencia.classificar')) return null

  return (
    <Card>
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <Campo rotulo="Nota de encerramento (opcional)" larga>
          <input value={nota} onChange={(e) => setNota(e.target.value)} style={entrada} />
        </Campo>
        <Btn
          variant="primary" disabled={encerrar.isPending}
          onClick={async () => {
            setErro(null)
            try {
              await encerrar.mutateAsync({ id: ocorrencia.ocorrencia_id, nota: nota.trim() })
            } catch (e) {
              setErro(primeiraFrase(e))
            }
          }}
        >
          Encerrar a ocorrência
        </Btn>
      </div>
      <div style={{ marginTop: erro ? 10 : 0 }}><FaixaDeErro>{erro}</FaixaDeErro></div>
    </Card>
  )
}
