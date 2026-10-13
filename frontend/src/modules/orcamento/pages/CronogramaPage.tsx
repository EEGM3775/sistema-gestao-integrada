import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertTriangle, CalendarRange, CheckCircle2, ExternalLink, Info as InfoIcon, Trash2, Wand2 } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import PaginaShell from '../components/PaginaShell'
import { CurvaSGrafico, GraficoEstilos } from '../components/graficos'
import { Aviso, Btn, Card, CAPS, Empty, Field, inp, KIND, Kpi, Loading, Modal, mono, Pill, SectHead, Select, Seletor } from '../ui'
import { brl, brlCurto, mesBR, num, paraDecimal, paraEdicao, pct } from '../lib'
import {
  useAtualizarParcela, useCronograma, useDesembolsoInsumos, useDistribuirCronograma,
  useEtapasDaObra, useObras, useOrcamentos, usePlanejarEtapa, useRemoverEtapaDoCronograma, useVincularEtapa,
} from '../hooks'
import type { Cronograma, CurvaEtapa, EtapaPlanejada } from '../types'

type Aba = 'etapas' | 'grade' | 'insumos'

const CURVAS: { valor: CurvaEtapa; rotulo: string }[] = [
  { valor: 'linear', rotulo: 'Linear' },
  { valor: 's', rotulo: 'Curva S' },
  { valor: 'inicio', rotulo: 'Carregada no início' },
  { valor: 'fim', rotulo: 'Carregada no fim' },
]
const ROTULO_CURVA: Record<CurvaEtapa, string> = {
  linear: 'Linear', s: 'Curva S', inicio: 'Início', fim: 'Fim', manual: 'Manual',
}

/** `AAAA-MM-DD` → `DD/MM/AAAA` sem passar por `Date` — o fuso transformaria
 *  o dia 3 em dia 2 no navegador de Brasília. */
const dia = (iso: string | null) => (iso ? iso.split('-').reverse().join('/') : '—')
const ordinal = (iso: string) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10))

/** **Cronograma** — o físico-financeiro do orçamento, por etapa.
 *
 *  *Decisão do dono, 10/10/2026:* o orçamento planeja **só etapas** — quando
 *  cada uma começa, quando termina, como o custo se espalha e quanta mão de obra
 *  ela orça. A grade etapa × mês sai **calculada** disso; o detalhe (serviço,
 *  frente, sequência, avanço) é do PDCA, que gera as atividades daqui e
 *  compara o executado com este plano. */
export default function CronogramaPage() {
  const { hasPermission } = useAuth()
  const [params, setParams] = useSearchParams()
  const orcamentoId = params.get('orcamento') ? Number(params.get('orcamento')) : undefined
  const [aba, setAba] = useState<Aba>('etapas')
  const [distribuindo, setDistribuindo] = useState(false)
  const [recado, setRecado] = useState('')

  const { data: obras } = useObras()
  const [obraId, setObraId] = useState<number | ''>('')
  const { data: listaOrcamentos } = useOrcamentos({ page_size: 200, ordering: '-versao' })
  const { data: cronograma, isLoading } = useCronograma(orcamentoId)
  const distribuir = useDistribuirCronograma()

  const orcamentos = useMemo(() => listaOrcamentos?.results ?? [], [listaOrcamentos])
  const daObra = useMemo(
    () => (obraId === '' ? orcamentos : orcamentos.filter(o => o.obra === obraId)),
    [orcamentos, obraId],
  )
  const orcamento = orcamentos.find(o => o.orcamento_id === orcamentoId)
  const podeEditar = hasPermission('orcamento.orcamento.edit') && !!cronograma?.editavel

  useEffect(() => {
    if (orcamento && obraId === '') setObraId(orcamento.obra)
  }, [orcamento, obraId])

  useEffect(() => {
    if (!recado) return
    const t = setTimeout(() => setRecado(''), 3600)
    return () => clearTimeout(t)
  }, [recado])

  const selecionar = (id: number | '') => {
    const proximo = new URLSearchParams(params)
    if (id === '') proximo.delete('orcamento')
    else proximo.set('orcamento', String(id))
    setParams(proximo, { replace: true })
  }

  const seletor = (
    <>
      <Select value={obraId} onChange={e => setObraId(e.target.value ? Number(e.target.value) : '')} style={{ maxWidth: 200 }}>
        <option value="">Todas as obras</option>
        {obras?.map(o => <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>)}
      </Select>
      <Select value={orcamentoId ?? ''} onChange={e => selecionar(e.target.value ? Number(e.target.value) : '')} style={{ maxWidth: 250 }}>
        <option value="">Selecione o orçamento</option>
        {daObra.map(o => <option key={o.orcamento_id} value={o.orcamento_id}>{o.descricao} · v{o.versao}</option>)}
      </Select>
      {orcamentoId && (
        <Seletor
          compacto
          valor={aba}
          onChange={setAba}
          opcoes={[
            { valor: 'etapas' as Aba, rotulo: 'Etapas no tempo' },
            { valor: 'grade' as Aba, rotulo: 'Grade físico-financeira' },
            // ORC.7 — a grade por etapa responde ao financeiro ("quanto sai em
            // setembro?"); esta responde a quem compra ("quantas toneladas de
            // aço preciso ter em obra em setembro?").
            { valor: 'insumos' as Aba, rotulo: 'Desembolso por insumo' },
          ]}
        />
      )}
    </>
  )

  const semNada = !!cronograma && cronograma.etapas.length === 0

  const acoes = orcamentoId && podeEditar && !semNada
    ? <Btn tam="sm" variant="primary" onClick={() => setDistribuindo(true)}><Wand2 size={13} />Planejar todas</Btn>
    : null

  return (
    <PaginaShell pagina="cronograma" seletor={seletor} acoes={acoes}>
      <GraficoEstilos />
      <div style={{ padding: '18px 22px 40px', overflowY: 'auto' }}>
        {!orcamentoId ? (
          <Empty>Selecione um orçamento para montar o cronograma físico-financeiro da obra.</Empty>
        ) : isLoading || !cronograma ? (
          <Loading texto="Carregando o cronograma…" />
        ) : semNada ? (
          <Empty acao={orcamento && (
            <Link to={`/app/orcamento/orcar/orcamento/${orcamento.orcamento_id}`} style={{ textDecoration: 'none' }}>
              <Btn variant="primary">Abrir a planilha</Btn>
            </Link>
          )}>
            <b>Nenhuma etapa com valor neste orçamento.</b> O cronograma é por etapa do orçamento: crie as
            etapas (os grupos de 1º nível) na planilha em Orçar e volte aqui.
          </Empty>
        ) : (
          <>
            <Resumo cronograma={cronograma} obra={orcamento?.obra} orcamentoId={orcamentoId} />

            {!cronograma.validacao.consistente && (
              <Aviso tom="danger">
                <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
                <span>
                  Etapa com distribuição manual que não fecha 100%:{' '}
                  {cronograma.validacao.problemas.map(p => `${p.etapa_nome} ${pct(p.soma_percentual, 2)}`).join(' · ')}.
                </span>
              </Aviso>
            )}

            {aba === 'etapas' && (
              <QuadroDeEtapas
                cronograma={cronograma} orcamentoId={orcamentoId} obraId={orcamento?.obra} podeEditar={podeEditar}
                avisar={setRecado}
              />
            )}
            {aba === 'grade' && (
              <GradeFisicoFinanceira cronograma={cronograma} podeEditar={podeEditar} avisar={setRecado} />
            )}
            {aba === 'insumos' && <PainelDesembolso orcamentoId={orcamentoId} />}
          </>
        )}
      </div>

      {distribuindo && orcamentoId && (
        <ModalDistribuir
          salvando={distribuir.isPending}
          algumaPlanejada={!!cronograma?.etapas.some(e => e.planejada)}
          onFechar={() => setDistribuindo(false)}
          onDistribuir={async (inicio, fim, curva, soSemPlano) => {
            const r = await distribuir.mutateAsync({ id: orcamentoId, inicio, fim, curva, so_sem_plano: soSemPlano })
            setDistribuindo(false)
            const n = r.etapas.filter(e => e.planejada).length
            setRecado(n > 0
              ? 'Etapas planejadas — ajuste início, término e curva de cada uma.'
              : 'Nada foi planejado: o orçamento não tem etapa com valor. Crie as etapas na planilha em Orçar.')
          }}
        />
      )}

      {recado && (
        <div style={{
          position: 'fixed', bottom: 22, left: '50%', zIndex: 95, animation: 'orcToast .22s ease both',
          background: 'var(--brand)', color: 'var(--brand-ink)', padding: '9px 17px',
          borderRadius: 999, fontSize: 12.5, fontWeight: 650, boxShadow: 'var(--shadow-lg)',
        }}>{recado}</div>
      )}
    </PaginaShell>
  )
}

function Resumo({ cronograma, obra, orcamentoId }: { cronograma: Cronograma; obra?: number; orcamentoId: number }) {
  const planejadas = cronograma.etapas.filter(e => e.planejada)
  const inicio = planejadas.map(e => e.inicio as string).sort()[0]
  const termino = planejadas.map(e => e.termino as string).sort().at(-1)
  const horas = cronograma.etapas.reduce((s, e) => s + Number(e.horas_mao_de_obra ?? 0), 0)
  const cobertura = Number(cronograma.valor_orcamento) > 0
    ? (Number(cronograma.total) / Number(cronograma.valor_orcamento)) * 100 : 0
  return (
    <Card style={{ display: 'flex', gap: 28, flexWrap: 'wrap', alignItems: 'flex-end', padding: '16px 20px' }}>
      <Kpi rotulo="No tempo" valor={brlCurto(cronograma.total)} apoio={`${pct(cobertura, 1)} do orçamento (${brlCurto(cronograma.valor_orcamento)})`} />
      <Kpi rotulo="Etapas planejadas" valor={`${planejadas.length}/${cronograma.etapas.length}`}
        tom={planejadas.length < cronograma.etapas.length ? KIND.amber[1] : undefined}
        apoio={planejadas.length < cronograma.etapas.length ? 'falta planejar' : 'todas no tempo'} />
      <Kpi rotulo="Prazo" valor={inicio ? `${mesBR(inicio)} → ${mesBR(termino)}` : '—'}
        apoio={`${cronograma.competencias.length} mês(es) de desembolso`} />
      <Kpi rotulo="Mão de obra orçada" valor={horas > 0 ? `${num(horas, 2)} Hh` : '—'}
        apoio={horas > 0 ? 'das composições abertas' : 'abra as composições em Orçar'} />
      <Kpi rotulo="Expediente" valor={cronograma.expediente === 'expediente_da_obra' ? 'Da obra' : 'Seg–sex'}
        apoio={cronograma.expediente === 'expediente_da_obra'
          ? `${cronograma.horas_por_dia} h/dia · PDCA`
          : 'sem expediente no PDCA — feriados nacionais'} />
      {obra && (
        <div style={{ marginLeft: 'auto' }}>
          <Link to={`/app/pdca/o/${obra}/plano?do_orcamento=${orcamentoId}`} style={{ textDecoration: 'none' }}>
            <Btn tam="sm"><ExternalLink size={13} />Gerar o plano no PDCA</Btn>
          </Link>
        </div>
      )}
    </Card>
  )
}

/** O quadro que o planejador edita: uma linha por etapa, com a faixa no tempo. */
function QuadroDeEtapas({ cronograma, orcamentoId, obraId, podeEditar, avisar }: {
  cronograma: Cronograma; orcamentoId: number; obraId?: number; podeEditar: boolean; avisar: (t: string) => void
}) {
  const { data: etapasDaObra } = useEtapasDaObra(obraId)
  const planejadas = cronograma.etapas.filter(e => e.planejada)
  const janela = planejadas.length
    ? {
        de: Math.min(...planejadas.map(e => ordinal(e.inicio as string))),
        ate: Math.max(...planejadas.map(e => ordinal(e.termino as string))),
      }
    : null

  return (
    <>
      <SectHead right={
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
          {podeEditar ? 'datas e curva por etapa — a grade é refeita na hora' : 'somente leitura'}
        </span>
      }>
        Etapas no tempo
      </SectHead>
      <Card pad={false} style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, minWidth: 1240 }}>
          <thead>
            <tr>
              {['Etapa', 'Etapa da obra', 'Valor', 'Hh orçado', 'Início', 'Término', 'Curva', 'Dias úteis', 'Equipe média', 'No tempo', ''].map((h, i) => (
                <th key={i} style={{
                  ...CAPS, padding: '9px 11px', textAlign: i <= 1 || i >= 4 && i <= 6 || i === 9 ? 'left' : 'right',
                  borderBottom: '1px solid var(--line)', background: 'var(--surface-2)',
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cronograma.etapas.map(etapa => (
              <LinhaDeEtapa
                key={etapa.grupo} etapa={etapa} orcamentoId={orcamentoId} podeEditar={podeEditar}
                etapasDaObra={etapasDaObra ?? []} janela={janela} avisar={avisar}
              />
            ))}
          </tbody>
        </table>
      </Card>
      <Aviso tom="info">
        <InfoIcon size={15} style={{ flex: 'none', marginTop: 1 }} />
        <span>
          O valor de cada etapa se espalha pelos <b>dias úteis</b> entre o início e o término, na forma da curva.
          A equipe média é o Hh orçado dividido pelos dias e pela jornada do expediente da obra. O <b>detalhe</b> —
          serviços, sequência, avanço apontado — é do PDCA, que gera as atividades a partir destas etapas e compara
          o executado com este plano.
        </span>
      </Aviso>
    </>
  )
}

function LinhaDeEtapa({ etapa, orcamentoId, podeEditar, etapasDaObra, janela, avisar }: {
  etapa: EtapaPlanejada; orcamentoId: number; podeEditar: boolean
  etapasDaObra: { etapa_id: number; nome_etapa: string }[]
  janela: { de: number; ate: number } | null; avisar: (t: string) => void
}) {
  const planejar = usePlanejarEtapa()
  const remover = useRemoverEtapaDoCronograma()
  const vincular = useVincularEtapa()
  const [inicio, setInicio] = useState(etapa.inicio ?? '')
  const [termino, setTermino] = useState(etapa.termino ?? '')
  const [curva, setCurva] = useState<CurvaEtapa>(etapa.curva ?? 'linear')
  const [erro, setErro] = useState('')

  useEffect(() => {
    setInicio(etapa.inicio ?? '')
    setTermino(etapa.termino ?? '')
    setCurva(etapa.curva ?? 'linear')
  }, [etapa.inicio, etapa.termino, etapa.curva])

  const mudou = inicio !== (etapa.inicio ?? '') || termino !== (etapa.termino ?? '') || curva !== (etapa.curva ?? 'linear')
  const salvar = async () => {
    if (!inicio || !termino) { setErro('Informe as duas datas.'); return }
    if (termino < inicio) { setErro('Término antes do início.'); return }
    setErro('')
    try {
      await planejar.mutateAsync({ id: orcamentoId, grupo: etapa.grupo, inicio, termino, curva: curva === 'manual' ? undefined : curva })
      avisar(`${etapa.etapa_nome}: no tempo.`)
    } catch (e) {
      const detalhe = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setErro(detalhe ?? 'Não foi possível salvar.')
    }
  }

  const td = { padding: '7px 11px', borderBottom: '1px solid var(--line-2)' } as const
  const barra = janela && etapa.planejada && etapa.inicio && etapa.termino
    ? (() => {
        const total = Math.max(janela.ate - janela.de, 1)
        const esq = ((ordinal(etapa.inicio) - janela.de) / total) * 100
        const larg = Math.max(((ordinal(etapa.termino) - ordinal(etapa.inicio)) / total) * 100, 1.5)
        return { esq, larg }
      })()
    : null

  return (
    <tr className="orc-linha">
      <td style={{ ...td, fontWeight: 600, color: 'var(--ink)' }}>
        <span style={{ ...mono, fontSize: 11, color: 'var(--ink-3)', marginRight: 6 }}>{etapa.codigo}</span>
        {etapa.etapa_nome}
        {erro && <div style={{ fontSize: 11, color: 'var(--danger-ink)', fontWeight: 500 }}>{erro}</div>}
      </td>
      <td style={td}>
        {podeEditar ? (
          // Opcional: o cronograma não depende do vínculo. Ele serve para o orçado
          // casar com o aplicado do SIL e com o plano do PDCA.
          <Select
            value={etapa.etapa ?? ''} disabled={vincular.isPending} style={{ width: 170 }}
            title="Ligar esta etapa a uma etapa da obra é opcional"
            onChange={async e => {
              const alvo = e.target.value ? Number(e.target.value) : null
              await vincular.mutateAsync({ id: orcamentoId, grupo: etapa.grupo, etapa: alvo })
              avisar(alvo ? `${etapa.etapa_nome}: ligada à etapa da obra.` : `${etapa.etapa_nome}: sem ligação com a obra.`)
            }}
          >
            <option value="">— sem vínculo —</option>
            {etapasDaObra.map(o => <option key={o.etapa_id} value={o.etapa_id}>{o.nome_etapa}</option>)}
          </Select>
        ) : (etapa.etapa_obra_nome ?? <span style={{ color: 'var(--ink-3)' }}>—</span>)}
      </td>
      <td style={{ ...td, textAlign: 'right', ...mono }}>{brl(etapa.valor)}</td>
      <td style={{ ...td, textAlign: 'right', ...mono, color: etapa.horas_mao_de_obra ? 'var(--ink)' : 'var(--ink-3)' }}>
        {etapa.horas_mao_de_obra ? num(etapa.horas_mao_de_obra, 2) : '—'}
      </td>
      <td style={td}>
        {podeEditar
          ? <input type="date" value={inicio} onChange={e => setInicio(e.target.value)} style={{ ...inp, ...mono, padding: '5px 7px', width: 140 }} />
          : <span style={mono}>{dia(etapa.inicio)}</span>}
      </td>
      <td style={td}>
        {podeEditar
          ? <input type="date" value={termino} min={inicio || undefined} onChange={e => setTermino(e.target.value)} style={{ ...inp, ...mono, padding: '5px 7px', width: 140 }} />
          : <span style={mono}>{dia(etapa.termino)}</span>}
      </td>
      <td style={td}>
        {podeEditar ? (
          <Select value={curva} onChange={e => setCurva(e.target.value as CurvaEtapa)} style={{ width: 150 }}>
            {curva === 'manual' && <option value="manual">Manual (células)</option>}
            {CURVAS.map(c => <option key={c.valor} value={c.valor}>{c.rotulo}</option>)}
          </Select>
        ) : etapa.curva ? <Pill kind={etapa.curva === 'manual' ? 'amber' : 'slate'}>{ROTULO_CURVA[etapa.curva]}</Pill> : '—'}
      </td>
      <td style={{ ...td, textAlign: 'right', ...mono }}>{etapa.dias_uteis ?? '—'}</td>
      <td style={{ ...td, textAlign: 'right', ...mono, color: etapa.equipe_media ? 'var(--ink)' : 'var(--ink-3)' }}
        title={etapa.equipe_media ? 'pessoas em média, no período' : 'precisa de Hh orçado e do expediente da obra no PDCA'}>
        {etapa.equipe_media ?? '—'}
      </td>
      <td style={{ ...td, minWidth: 160 }}>
        {barra ? (
          <div style={{ position: 'relative', height: 10, background: 'var(--surface-2)', borderRadius: 5 }}>
            <div style={{
              position: 'absolute', left: `${barra.esq}%`, width: `${barra.larg}%`, top: 0, bottom: 0,
              background: 'var(--accent)', borderRadius: 5, opacity: etapa.curva === 'manual' ? 0.55 : 1,
            }} />
          </div>
        ) : <Pill kind="amber">não planejada</Pill>}
      </td>
      <td style={{ ...td, textAlign: 'right', whiteSpace: 'nowrap' }}>
        {podeEditar && mudou && (
          <Btn tam="sm" variant="primary" disabled={planejar.isPending} onClick={salvar}>Salvar</Btn>
        )}
        {podeEditar && etapa.planejada && !mudou && (
          <Btn tam="sm" title="Tirar do cronograma" disabled={remover.isPending}
            onClick={async () => {
              await remover.mutateAsync({ id: orcamentoId, grupo: etapa.grupo })
              avisar(`${etapa.etapa_nome}: fora do cronograma.`)
            }}>
            <Trash2 size={13} />
          </Btn>
        )}
      </td>
    </tr>
  )
}

/** A grade etapa × mês, **calculada**. Editar uma célula passa a etapa para a
 *  curva manual — a mudança de data seguinte não apaga o ajuste. */
function GradeFisicoFinanceira({ cronograma, podeEditar, avisar }: {
  cronograma: Cronograma; podeEditar: boolean; avisar: (t: string) => void
}) {
  const atualizarParcela = useAtualizarParcela()
  const [editando, setEditando] = useState<{ parcela: number; valor: string } | null>(null)

  if (cronograma.competencias.length === 0) {
    return <Empty>Nenhuma etapa no tempo ainda. Planeje as etapas na primeira aba.</Empty>
  }
  const mensal = Object.fromEntries(cronograma.mensal.map(m => [m.competencia, m]))
  const celulaTotal = { ...CAPS, padding: '9px 11px', borderTop: '2px solid var(--line)', background: 'var(--surface-2)' } as const

  return (
    <>
      <SectHead right={
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
          {podeEditar ? 'clique numa célula para ajuste fino (a etapa vira manual)' : 'somente leitura'}
        </span>
      }>
        Distribuição por etapa e competência
      </SectHead>

      <Card pad={false} style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: 12.5, minWidth: 100 + cronograma.competencias.length * 96 }}>
          <thead>
            <tr>
              <th style={{
                ...CAPS, padding: '10px 13px', textAlign: 'left', borderBottom: '1px solid var(--line)',
                background: 'var(--surface-2)', position: 'sticky', left: 0, zIndex: 2, minWidth: 220,
              }}>Etapa</th>
              {cronograma.competencias.map(c => (
                <th key={c} style={{
                  ...CAPS, padding: '10px 11px', textAlign: 'right', borderBottom: '1px solid var(--line)',
                  background: 'var(--surface-2)', minWidth: 96,
                }}>{mesBR(c)}</th>
              ))}
              <th style={{
                ...CAPS, padding: '10px 13px', textAlign: 'right', borderBottom: '1px solid var(--line)',
                background: 'var(--surface-2)',
              }}>Total</th>
            </tr>
          </thead>
          <tbody>
            {cronograma.linhas.map(linha => (
              <tr key={linha.grupo ?? 'geral'} className="orc-linha">
                <td style={{
                  padding: '8px 13px', borderBottom: '1px solid var(--line-2)', fontWeight: 600,
                  color: 'var(--ink)', position: 'sticky', left: 0, background: 'var(--surface)', zIndex: 1,
                }}>{linha.etapa_nome}</td>
                {cronograma.competencias.map(c => {
                  const celula = linha.parcelas[c]
                  if (!celula) return <td key={c} style={{ padding: '8px 11px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', color: 'var(--ink-3)' }}>—</td>
                  const emEdicao = editando?.parcela === celula.parcela_id
                  return (
                    <td
                      key={c}
                      onClick={() => podeEditar && !emEdicao && setEditando({ parcela: celula.parcela_id, valor: paraEdicao(celula.percentual) })}
                      style={{
                        padding: emEdicao ? 0 : '8px 11px', borderBottom: '1px solid var(--line-2)',
                        textAlign: 'right', cursor: podeEditar ? 'cell' : 'default',
                      }}
                    >
                      {emEdicao ? (
                        <input
                          autoFocus
                          value={editando.valor}
                          onChange={e => setEditando({ ...editando, valor: e.target.value })}
                          onBlur={async () => {
                            const valor = paraDecimal(editando.valor)
                            setEditando(null)
                            if (valor !== celula.percentual) {
                              await atualizarParcela.mutateAsync({ id: celula.parcela_id, payload: { percentual: valor } })
                              avisar('Célula ajustada — a etapa passou para distribuição manual.')
                            }
                          }}
                          onKeyDown={e => {
                            if (e.key === 'Escape') setEditando(null)
                            if (e.key === 'Enter') e.currentTarget.blur()
                          }}
                          style={{
                            width: '100%', border: '2px solid var(--accent)', outline: 'none', textAlign: 'right',
                            padding: '6px 9px', fontSize: 12.5, background: 'var(--surface)', color: 'var(--ink)', ...mono,
                          }}
                        />
                      ) : (
                        <>
                          <div style={{ ...mono, color: 'var(--ink)' }}>{pct(celula.percentual, 1)}</div>
                          <div style={{ ...mono, fontSize: 10.5, color: 'var(--ink-3)' }}>{brlCurto(celula.valor_previsto)}</div>
                        </>
                      )}
                    </td>
                  )
                })}
                <td style={{ padding: '8px 13px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, fontWeight: 700, color: 'var(--ink)' }}>
                  {brl(linha.total)}
                </td>
              </tr>
            ))}
            <tr>
              <td style={{ ...celulaTotal, padding: '9px 13px', position: 'sticky', left: 0 }}>Desembolso previsto</td>
              {cronograma.competencias.map(c => (
                <td key={c} style={{ ...celulaTotal, textAlign: 'right', ...mono, fontWeight: 700, color: 'var(--ink)', textTransform: 'none' }}>
                  {brlCurto(mensal[c]?.valor ?? 0)}
                </td>
              ))}
              <td style={{ ...celulaTotal, padding: '9px 13px', textAlign: 'right', ...mono, fontWeight: 800, color: 'var(--ink)', textTransform: 'none' }}>{brl(cronograma.total)}</td>
            </tr>
            <tr>
              <td style={{ ...celulaTotal, borderTop: 'none', padding: '6px 13px', position: 'sticky', left: 0 }}>Acumulado</td>
              {cronograma.competencias.map(c => (
                <td key={c} style={{ ...celulaTotal, borderTop: 'none', padding: '6px 11px', textAlign: 'right', ...mono, color: 'var(--ink-3)', textTransform: 'none' }}>
                  {pct(mensal[c]?.pct_acumulado ?? 0, 1)}
                </td>
              ))}
              <td style={{ ...celulaTotal, borderTop: 'none' }} />
            </tr>
          </tbody>
        </table>
      </Card>

      <SectHead>Curva S do planejado</SectHead>
      <Card>
        <CurvaSGrafico
          altura={220}
          soPrevisto
          serie={cronograma.mensal.map(m => ({
            competencia: mesBR(m.competencia),
            previstoPct: Number(m.pct_acumulado),
            realizadoPct: 0,
            previsto: Number(m.acumulado),
            realizado: 0,
          }))}
        />
      </Card>
      <p style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
        <CheckCircle2 size={13} />
        O executado contra esta curva — previsto × realizado, físico e financeiro — é lido no PDCA.
      </p>
    </>
  )
}

function ModalDistribuir({ salvando, algumaPlanejada, onFechar, onDistribuir }: {
  salvando: boolean; algumaPlanejada: boolean; onFechar: () => void
  onDistribuir: (inicio: string, fim: string, curva: CurvaEtapa, soSemPlano: boolean) => void
}) {
  const [inicio, setInicio] = useState('')
  const [fim, setFim] = useState('')
  const [curva, setCurva] = useState<CurvaEtapa>('s')
  const [soSemPlano, setSoSemPlano] = useState(algumaPlanejada)
  const [erro, setErro] = useState('')
  return (
    <Modal
      titulo="Planejar as etapas no tempo"
      onClose={onFechar}
      rodape={
        <>
          <Btn onClick={onFechar}>Cancelar</Btn>
          <Btn variant="primary" disabled={salvando} onClick={() => {
            if (!inicio || !fim) { setErro('Informe as duas datas.'); return }
            if (fim < inicio) { setErro('O término não pode ser anterior ao início.'); return }
            onDistribuir(inicio, fim, curva, soSemPlano)
          }}>Planejar</Btn>
        </>
      }
    >
      {erro && <Aviso tom="danger">{erro}</Aviso>}
      <Aviso>
        <CalendarRange size={15} style={{ flex: 'none', marginTop: 1 }} />
        Dá a toda etapa o mesmo período e a mesma curva — é o ponto de partida. Quem vem antes de quem é
        decisão sua: ajuste início e término etapa a etapa depois.
      </Aviso>
      <div style={{ height: 14 }} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Field label="Início">
          <input type="date" value={inicio} onChange={e => setInicio(e.target.value)} style={{ ...inp, ...mono }} />
        </Field>
        <Field label="Término">
          <input type="date" value={fim} min={inicio || undefined} onChange={e => setFim(e.target.value)} style={{ ...inp, ...mono }} />
        </Field>
      </div>
      <div style={{ height: 12 }} />
      <Field label="Curva">
        <Select value={curva} onChange={e => setCurva(e.target.value as CurvaEtapa)}>
          {CURVAS.map(c => <option key={c.valor} value={c.valor}>{c.rotulo}</option>)}
        </Select>
      </Field>
      {algumaPlanejada && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, marginTop: 12, color: 'var(--ink-2)' }}>
          <input type="checkbox" checked={soSemPlano} onChange={e => setSoSemPlano(e.target.checked)} />
          Só as etapas ainda não planejadas (mantém as que você já ajustou)
        </label>
      )}
    </Modal>
  )
}

/** O desembolso na granularidade do **insumo** (ORC.7).
 *
 *  A distribuição é herdada da etapa, não inventada: o insumo cai nas
 *  competências que o planejador já distribuiu, na proporção do valor que ele
 *  tem em cada uma. Uma curva própria por insumo seria planejamento fabricado —
 *  e o módulo não fabrica dado. */
function PainelDesembolso({ orcamentoId }: { orcamentoId: number }) {
  const [categoria, setCategoria] = useState('')
  const { data, isLoading } = useDesembolsoInsumos(orcamentoId, categoria || undefined)

  if (isLoading) return <Loading texto="Distribuindo os insumos no tempo…" />
  if (!data) return <Empty>Sem dados.</Empty>

  return (
    <>
      <SectHead
        right={
          <Seletor
            compacto
            valor={categoria}
            onChange={setCategoria}
            opcoes={[
              { valor: '', rotulo: 'Todas' },
              { valor: 'material', rotulo: 'Material' },
              { valor: 'equipamento', rotulo: 'Equipamento' },
              { valor: 'mao_de_obra', rotulo: 'Mão de obra' },
            ]}
          />
        }
      >
        Quanto de cada insumo cai em cada mês
      </SectHead>

      {!data.insumos.length && !data.sem_distribuicao.length && (
        <Empty>
          Nenhum insumo consolidado. Explodir as composições em <b>Orçar</b> é o passo que falta —
          sem isso o cronograma sabe quanto sai em cada mês, e não sabe <i>de quê</i>.
        </Empty>
      )}

      {!!data.insumos.length && (
        <Card pad={false} style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr style={{ color: 'var(--ink-3)', textAlign: 'left' }}>
                <th style={{ padding: '8px 10px', position: 'sticky', left: 0, background: 'var(--surface)' }}>Insumo</th>
                <th style={{ padding: '8px 10px', width: 54 }}>Und</th>
                <th style={{ padding: '8px 10px', textAlign: 'right', width: 110 }}>Total</th>
                {data.competencias.map(c => (
                  <th key={c} style={{ padding: '8px 10px', textAlign: 'right', minWidth: 108 }}>{mesBR(c)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.insumos.map((linha, i) => (
                <tr key={`${linha.item ?? linha.descricao}-${i}`} style={{ borderTop: '1px solid var(--line)' }}>
                  <td style={{ padding: '6px 10px', position: 'sticky', left: 0, background: 'var(--surface)' }}>
                    {linha.descricao}
                  </td>
                  <td style={{ padding: '6px 10px', color: 'var(--ink-3)' }}>{linha.unidade}</td>
                  <td style={{ ...mono, padding: '6px 10px', textAlign: 'right', fontWeight: 650 }}>
                    {num(linha.quantidade_total)}
                  </td>
                  {data.competencias.map(c => {
                    const mes = linha.meses[c]
                    return (
                      <td key={c} style={{ ...mono, padding: '6px 10px', textAlign: 'right' }}>
                        {mes ? (
                          <>
                            {num(mes.quantidade)}
                            <span style={{ display: 'block', fontSize: 10.5, color: 'var(--ink-3)' }}>
                              {brlCurto(mes.valor)}
                            </span>
                          </>
                        ) : <span style={{ color: 'var(--ink-3)' }}>—</span>}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {!!data.sem_distribuicao.length && (
        <Aviso tom="amber">
          <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
          <span>
            <b>{data.sem_distribuicao.length}</b> insumo(s) ficaram fora da grade: as etapas das linhas
            em que aparecem não têm cronograma distribuído. {data.nota_sem_distribuicao}
          </span>
        </Aviso>
      )}
    </>
  )
}
