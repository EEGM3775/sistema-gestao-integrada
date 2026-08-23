/** ORC.8 — a carga da base oficial num clique.
 *
 *  **Por que este painel mora na tela de Bases e não numa área de admin:** o
 *  lugar onde alguém percebe que a base está velha é olhando as publicações
 *  disponíveis. Mandar essa pessoa para outro menu para consertar o que ela
 *  acabou de ver seria separar o problema da solução por uma navegação.
 *
 *  Ele só aparece para `is_platform_admin`, e quem decide isso é o **backend**:
 *  `cargas/estado/` responde 403 para o resto, e a ausência do dado é o que
 *  esconde o painel. Não há checagem de papel escrita aqui — se houvesse, seriam
 *  duas regras dizendo quem pode, e um dia elas discordariam.
 */
import { useState } from 'react'
import {
  AlertTriangle, CheckCircle2, CloudDownload, HelpCircle, Link2, RefreshCw, Upload,
} from 'lucide-react'
import {
  Aviso, Btn, Card, CAPS, Field, inp, Info, Loading, mono, Pill, SectHead, Select,
} from '../ui'
import { dataBR, FONTE_ROTULO, mesBR } from '../lib'
import {
  useCargas, useDispararCarga, useEnviarArquivoDaCarga, useEstadoDaCarga,
  useRepetirCarga, useSalvarFonteOficial,
} from '../hooks'
import type { CargaBase, EstadoCarga, FonteOficial } from '../types'

/** Cada estado com a cor que ele merece — e `aguardando` é âmbar, não vermelho:
 *  a carga não falhou, ela **perguntou**. */
const TOM: Record<EstadoCarga, 'slate' | 'info' | 'amber' | 'good' | 'danger'> = {
  pendente: 'slate', baixando: 'info', lendo: 'info', gravando: 'info',
  aguardando: 'amber', concluida: 'good', falhou: 'danger',
}

function EstadoDaCorrida({ carga }: { carga: CargaBase }) {
  return (
    <Pill kind={TOM[carga.estado]} pulse={carga.em_andamento}>
      {carga.estado_nome}
    </Pill>
  )
}

function ResumoDaCorrida({ carga }: { carga: CargaBase }) {
  const resumo = carga.resumo || {}
  const publicacoes = resumo.publicacoes ?? []
  if (!publicacoes.length && !carga.erro) return null
  return (
    <div style={{ marginTop: 9 }}>
      {publicacoes.length > 0 && (
        <>
          {/* **Resumo antes de gravar**, não conferência linha a linha: a
              importação é idempotente e conferir 800 mil linhas seria teatro. O
              que resolve é dizer quantos itens entram por publicação — e é aí
              que se percebe o arquivo errado. */}
          <div style={{ ...CAPS, fontSize: 9, marginBottom: 5 }}>
            {publicacoes.length} publicação(ões) · planilha {resumo.planilha || '—'}
            {resumo.aba_analitica
              ? ` · analítica "${resumo.aba_analitica}" (${resumo.linhas_analiticas ?? 0} linhas)`
              : ' · sem aba analítica'}
          </div>
          <div style={{
            maxHeight: 168, overflowY: 'auto', border: '1px solid var(--line)',
            borderRadius: 6, background: 'var(--inset)',
          }}>
            {publicacoes.map(p => (
              <div key={`${p.uf}-${p.regime}`} style={{
                display: 'flex', gap: 10, padding: '4px 10px', fontSize: 11.5,
                borderBottom: '1px solid var(--line)',
              }}>
                <b style={{ width: 26 }}>{p.uf}</b>
                <span style={{ width: 84, color: 'var(--ink-3)' }}>{p.regime}</span>
                <span style={{ ...mono }}>{p.insumos} insumos</span>
                <span style={{ ...mono, color: 'var(--ink-3)' }}>{p.composicoes} composições</span>
              </div>
            ))}
          </div>
        </>
      )}
      {(resumo.avisos ?? []).map(aviso => (
        <div key={aviso} style={{ fontSize: 11.5, color: 'var(--accent-ink)', marginTop: 5 }}>
          {aviso}
        </div>
      ))}
    </div>
  )
}

export default function PainelCargaOficial() {
  const { data: estado, isLoading, isError } = useEstadoDaCarga()
  const { data: historico } = useCargas({ page_size: 8 }, !isError)
  const disparar = useDispararCarga()
  const enviar = useEnviarArquivoDaCarga()
  const repetir = useRepetirCarga()
  const salvarFonte = useSalvarFonteOficial()

  const [editando, setEditando] = useState<Partial<FonteOficial> | null>(null)
  const [competencia, setCompetencia] = useState('')
  const [fonteEscolhida, setFonteEscolhida] = useState('sinapi')
  const [recado, setRecado] = useState('')

  // 403 = não é dono da plataforma. O painel simplesmente não existe para essa
  // pessoa; a tela de bases segue inteira sem ele.
  if (isError) return null
  if (isLoading || !estado) return <Loading texto="Conferindo a carga oficial…" />

  const emAndamento = estado.em_andamento
  const fonte = estado.fontes.find(f => f.fonte === fonteEscolhida)
  const podeBaixar = !!fonte?.template_url && !!fonte?.carga_automatica

  const aoDisparar = async (somenteResumo: boolean) => {
    setRecado('')
    const nova = await disparar.mutateAsync({
      fonte: fonteEscolhida,
      competencia: competencia || undefined,
      somente_resumo: somenteResumo,
    })
    setRecado(
      `Carga #${nova.carga_id} na fila — ${nova.fonte_nome} ${mesBR(nova.competencia)}.`,
    )
  }

  const aoEnviar = async (arquivo: File, somenteResumo: boolean) => {
    setRecado('')
    const nova = await enviar.mutateAsync({
      fonte: fonteEscolhida,
      competencia: competencia || undefined,
      arquivo,
      somente_resumo: somenteResumo,
    })
    setRecado(`Arquivo recebido — carga #${nova.carga_id} na fila.`)
  }

  return (
    <>
      <SectHead right={<Pill kind="net">dono da plataforma</Pill>}>
        Carga da base oficial
      </SectHead>

      <Card style={{ padding: '14px 16px', marginBottom: 11 }}>
        <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <Field label="Fonte">
            <Select value={fonteEscolhida} onChange={e => setFonteEscolhida(e.target.value)}>
              {estado.fontes.length === 0 && <option value="sinapi">SINAPI</option>}
              {estado.fontes.map(f => (
                <option key={f.fonte} value={f.fonte}>{FONTE_ROTULO[f.fonte] ?? f.fonte_nome}</option>
              ))}
            </Select>
          </Field>
          <Field
            label="Competência"
            dica="Vazio usa o mês que a defasagem da fonte indica — a SINAPI publica M por volta do dia 10 de M+1."
          >
            <input
              type="month" value={competencia} onChange={e => setCompetencia(e.target.value)}
              placeholder={fonte?.competencia_sugerida?.slice(0, 7)} style={{ ...inp, width: 150 }}
            />
          </Field>

          <Btn
            variant="primary"
            disabled={!podeBaixar || !!emAndamento || disparar.isPending}
            onClick={() => aoDisparar(false)}
            title={
              podeBaixar ? 'Baixa o pacote oficial e grava as publicações'
                : 'Cadastre o template da URL desta fonte primeiro'
            }
          >
            <CloudDownload size={14} />Carregar agora
          </Btn>
          <Btn
            disabled={!podeBaixar || !!emAndamento || disparar.isPending}
            onClick={() => aoDisparar(true)}
            title="Lê e conta o que entraria, sem gravar nada"
          >
            Só conferir
          </Btn>

          {/* **Plano B**: o mês em que a Caixa muda o layout ou aperta o WAF não
              pode parar a carga. */}
          <label>
            <input
              type="file" accept=".zip,.xlsx" style={{ display: 'none' }}
              disabled={!!emAndamento || enviar.isPending}
              onChange={e => {
                const arquivo = e.target.files?.[0]
                if (arquivo) void aoEnviar(arquivo, false)
                e.target.value = ''
              }}
            />
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5,
              padding: '7px 11px', border: '1px solid var(--line)', borderRadius: 7,
              cursor: emAndamento ? 'not-allowed' : 'pointer', color: 'var(--ink-2)',
            }}>
              <Upload size={14} />Enviar o arquivo
            </span>
          </label>

          <Btn tam="sm" onClick={() => setEditando(fonte ?? { fonte: fonteEscolhida as FonteOficial['fonte'] })}>
            <Link2 size={13} />Endereço da fonte
          </Btn>
        </div>

        {/* Nenhuma fonte cadastrada ainda. Sem esta frase os dois botões apareceriam
            desligados sem explicação — e o motivo não é falta de permissão, é que
            ninguém disse ainda de onde o arquivo vem. */}
        {estado.fontes.length === 0 && (
          <Aviso tom="info">
            <Link2 size={15} style={{ flex: 'none', marginTop: 1 }} />
            <span>
              Nenhuma fonte oficial cadastrada. Abra <b>Endereço da fonte</b> e cole o
              template da URL do pacote — ele aceita <span style={mono}>{'{ano_mes}'}</span> e
              companhia, e fica editável de propósito: o endereço da Caixa já mudou uma vez,
              e o conserto tem de ser uma caixa de texto, não um deploy.
            </span>
          </Aviso>
        )}
        {fonte && !fonte.carga_automatica && (
          <Aviso tom="info">
            <HelpCircle size={15} style={{ flex: 'none', marginTop: 1 }} />
            <span>
              O motor ainda não lê o formato de <b>{FONTE_ROTULO[fonte.fonte] ?? fonte.fonte_nome}</b>.
              O arquivo largo (27 UFs em colunas) é o da Caixa; as outras bases continuam
              entrando pelo comando <span style={mono}>importar_base_referencial</span>,
              um arquivo por UF.
            </span>
          </Aviso>
        )}
        {fonte && fonte.carga_automatica && !fonte.template_url && (
          <Aviso tom="amber">
            <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
            <span>
              Esta fonte não tem <b>template de URL</b> cadastrado, e sem ele nada é baixado —
              um job que adivinha endereço é um job que um dia importa dado errado com a
              confiança de um robô. O envio manual do arquivo continua valendo.
            </span>
          </Aviso>
        )}
        {recado && <div style={{ fontSize: 12, color: 'var(--accent-ink)', marginTop: 8 }}>{recado}</div>}
      </Card>

      {emAndamento && (
        <Card style={{ padding: '13px 15px', marginBottom: 11, borderColor: 'var(--accent)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 6 }}>
            <EstadoDaCorrida carga={emAndamento} />
            <b style={{ fontSize: 13.5 }}>
              {emAndamento.fonte_nome} · {mesBR(emAndamento.competencia)}
            </b>
            <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)', marginLeft: 'auto' }}>
              {emAndamento.mb_lidos > 0 ? `${emAndamento.mb_lidos} MB` : ''}
            </span>
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
            {emAndamento.etapa || 'na fila…'}
          </div>
        </Card>
      )}

      <SectHead>Últimas cargas</SectHead>
      {!historico || historico.results.length === 0 ? (
        <Card style={{ padding: 16, fontSize: 12.5, color: 'var(--ink-3)' }}>
          Nenhuma carga registrada ainda.
        </Card>
      ) : historico.results.map(carga => (
        <Card key={carga.carga_id} style={{ padding: '12px 15px', marginBottom: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap' }}>
            <EstadoDaCorrida carga={carga} />
            <b style={{ fontSize: 13 }}>{carga.fonte_nome} · {mesBR(carga.competencia)}</b>
            <span style={{ ...CAPS, fontSize: 9 }}>{carga.origem_nome}</span>
            {carga.somente_resumo && <Pill kind="slate">só conferência</Pill>}
            <span style={{ fontSize: 11.5, color: 'var(--ink-3)', marginLeft: 'auto' }}>
              {dataBR(carga.criada_em)} · {carga.solicitada_por_nome || '—'}
            </span>
          </div>

          {carga.estado === 'concluida' && !carga.somente_resumo && (
            <div style={{ fontSize: 12, color: 'var(--good-ink)', marginTop: 5, display: 'flex', gap: 6 }}>
              <CheckCircle2 size={13} style={{ flex: 'none', marginTop: 2 }} />
              <span>
                {carga.total_publicacoes} publicações · {carga.total_insumos} insumos ·{' '}
                {carga.total_composicoes} composições · {carga.total_analitica} linhas analíticas
              </span>
            </div>
          )}

          {carga.estado === 'aguardando' && (
            /* Não é falha: é uma pergunta. A base-mãe é global — o que entra
               aqui todos os tenants enxergam —, e classe traduzida errado é
               alavanca de preço para a plataforma inteira de uma vez. */
            <Aviso tom="amber">
              <HelpCircle size={15} style={{ flex: 'none', marginTop: 1 }} />
              <div style={{ flex: 1 }}>
                <div style={{ whiteSpace: 'pre-wrap', fontSize: 12.5 }}>{carga.erro}</div>
                <Btn
                  tam="sm" style={{ marginTop: 8 }} disabled={repetir.isPending || !!emAndamento}
                  onClick={() => repetir.mutateAsync({ id: carga.carga_id })}
                >
                  <RefreshCw size={13} />Declarei a tradução — repetir
                </Btn>
                <Btn
                  tam="sm" style={{ marginTop: 8, marginLeft: 7 }}
                  disabled={repetir.isPending || !!emAndamento}
                  onClick={() => repetir.mutateAsync({ id: carga.carga_id, aceitar_sem_classe: true })}
                >
                  Aceitar pela unidade
                </Btn>
              </div>
            </Aviso>
          )}

          {carga.estado === 'falhou' && (
            <Aviso tom="danger">
              <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
              <div style={{ flex: 1 }}>
                <div style={{ whiteSpace: 'pre-wrap', fontSize: 12.5 }}>{carga.erro}</div>
                {carga.url_origem && (
                  <div style={{ ...mono, fontSize: 11, color: 'var(--ink-3)', marginTop: 4, wordBreak: 'break-all' }}>
                    {carga.url_origem}
                  </div>
                )}
                <Btn
                  tam="sm" style={{ marginTop: 8 }} disabled={repetir.isPending || !!emAndamento}
                  onClick={() => repetir.mutateAsync({ id: carga.carga_id })}
                >
                  <RefreshCw size={13} />Tentar de novo
                </Btn>
              </div>
            </Aviso>
          )}

          <ResumoDaCorrida carga={carga} />
        </Card>
      ))}

      {editando && (
        <FormularioDaFonte
          fonte={editando}
          salvando={salvarFonte.isPending}
          onFechar={() => setEditando(null)}
          onSalvar={async payload => {
            await salvarFonte.mutateAsync({ id: editando.fonte_id, payload })
            setEditando(null)
          }}
        />
      )}
    </>
  )
}

/** A caixa de texto que substitui um deploy.
 *
 *  A URL da Caixa **já mudou uma vez** — o padrão por UF morreu em 12/2024. Com o
 *  template compilado no código, o conserto seria um release no meio do mês.
 */
function FormularioDaFonte({ fonte, salvando, onFechar, onSalvar }: {
  fonte: Partial<FonteOficial>
  salvando: boolean
  onFechar: () => void
  onSalvar: (payload: Partial<FonteOficial>) => Promise<void>
}) {
  const [form, setForm] = useState<Partial<FonteOficial>>({
    template_url: '', pagina_referencia: '', dia_do_mes: 0, defasagem_meses: 1,
    ativa: true, observacao: '', ...fonte,
  })
  const alterar = (campo: keyof FonteOficial) => (valor: unknown) =>
    setForm(f => ({ ...f, [campo]: valor }))

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 60,
      display: 'grid', placeItems: 'center', padding: 20,
    }} onClick={onFechar}>
      <Card
        onClick={(e: React.MouseEvent) => e.stopPropagation()}
        style={{ width: 'min(620px, 100%)', padding: '18px 20px', maxHeight: '86vh', overflowY: 'auto' }}
      >
        <b style={{ fontSize: 15 }}>Endereço da fonte — {FONTE_ROTULO[form.fonte as FonteOficial['fonte']] ?? form.fonte}</b>

        <div style={{ display: 'grid', gap: 11, marginTop: 13 }}>
          <Field
            label="Template da URL"
            dica="Aceita {ano}, {mes}, {ano_mes}, {uf} e {regime}. O nacional não usa {uf}."
          >
            <input
              value={form.template_url ?? ''} style={inp}
              placeholder="https://…/SINAPI_ref_{ano_mes}.zip"
              onChange={e => alterar('template_url')(e.target.value)}
            />
          </Field>
          <Field
            label="Página de referência"
            dica="Visitada antes do download e enviada como Referer — o WAF da Caixa recusa hit frio no arquivo."
          >
            <input
              value={form.pagina_referencia ?? ''} style={inp}
              placeholder="https://www.caixa.gov.br/…/Paginas/downloads.aspx"
              onChange={e => alterar('pagina_referencia')(e.target.value)}
            />
          </Field>
          <div style={{ display: 'flex', gap: 11, flexWrap: 'wrap' }}>
            <Field label="Dia do mês" dica="0 = sem agendamento; só o botão.">
              <input
                type="number" min={0} max={28} value={form.dia_do_mes ?? 0}
                style={{ ...inp, width: 96 }}
                onChange={e => alterar('dia_do_mes')(Number(e.target.value))}
              />
            </Field>
            <Field label="Defasagem (meses)" dica="A SINAPI publica o mês M por volta do dia 10 de M+1.">
              <input
                type="number" min={0} max={6} value={form.defasagem_meses ?? 1}
                style={{ ...inp, width: 96 }}
                onChange={e => alterar('defasagem_meses')(Number(e.target.value))}
              />
            </Field>
            <Field label="Na varredura">
              <Select
                value={form.ativa ? 'sim' : 'nao'}
                onChange={e => alterar('ativa')(e.target.value === 'sim')}
              >
                <option value="sim">Ativa</option>
                <option value="nao">Desligada</option>
              </Select>
            </Field>
          </div>
          <Field label="Observação">
            <textarea
              value={form.observacao ?? ''} rows={2} style={{ ...inp, resize: 'vertical' }}
              onChange={e => alterar('observacao')(e.target.value)}
            />
          </Field>
        </div>

        <Info k="Competência sugerida" v={form.competencia_sugerida ? mesBR(form.competencia_sugerida) : '—'} />

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 15 }}>
          <Btn onClick={onFechar}>Cancelar</Btn>
          <Btn variant="primary" disabled={salvando} onClick={() => void onSalvar(form)}>
            Salvar
          </Btn>
        </div>
      </Card>
    </div>
  )
}
