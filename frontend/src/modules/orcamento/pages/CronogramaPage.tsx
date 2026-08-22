import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertTriangle, CalendarRange, CheckCircle2, Info as InfoIcon, Wand2 } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import PaginaShell from '../components/PaginaShell'
import { CurvaSGrafico, GraficoEstilos } from '../components/graficos'
import { Aviso, Btn, Card, CAPS, Empty, Field, inp, Kpi, Loading, Modal, mono, Pill, SectHead, Select, Seletor } from '../ui'
import { brl, brlCurto, mesBR, num, paraDecimal, paraEdicao, pct } from '../lib'
import {
  useAtualizarParcela, useCronograma, useCurvaS, useDesembolsoInsumos, useDistribuirCronograma,
  useObras, useOrcamentos,
} from '../hooks'

type Aba = 'grade' | 'curva' | 'insumos'

export default function CronogramaPage() {
  const { hasPermission } = useAuth()
  const [params, setParams] = useSearchParams()
  const orcamentoId = params.get('orcamento') ? Number(params.get('orcamento')) : undefined
  const [aba, setAba] = useState<Aba>('grade')
  const [distribuindo, setDistribuindo] = useState(false)
  const [editando, setEditando] = useState<{ parcela: number; valor: string } | null>(null)
  const [recado, setRecado] = useState('')

  const { data: obras } = useObras()
  const [obraId, setObraId] = useState<number | ''>('')
  const { data: listaOrcamentos } = useOrcamentos({ page_size: 200, ordering: '-versao' })
  const { data: cronograma, isLoading } = useCronograma(orcamentoId)
  const { data: curvaS } = useCurvaS(orcamentoId)
  const distribuir = useDistribuirCronograma()
  const atualizarParcela = useAtualizarParcela()

  const orcamentos = useMemo(() => listaOrcamentos?.results ?? [], [listaOrcamentos])
  const daObra = useMemo(
    () => (obraId === '' ? orcamentos : orcamentos.filter(o => o.obra === obraId)),
    [orcamentos, obraId],
  )
  const orcamento = orcamentos.find(o => o.orcamento_id === orcamentoId)
  const podeEditar = hasPermission('orcamento.orcamento.edit') && !!orcamento?.editavel

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

  const somaPorCompetencia = useMemo(() => {
    if (!cronograma) return {}
    const soma: Record<string, number> = {}
    for (const linha of cronograma.linhas) {
      for (const [competencia, celula] of Object.entries(linha.parcelas)) {
        soma[competencia] = (soma[competencia] ?? 0) + Number(celula.valor_previsto)
      }
    }
    return soma
  }, [cronograma])

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
            { valor: 'grade' as Aba, rotulo: 'Grade física-financeira' },
            { valor: 'curva' as Aba, rotulo: 'Curva S' },
            // ORC.7 — a grade por etapa responde ao financeiro ("quanto sai em
            // setembro?"); esta responde a quem compra ("quantas toneladas de
            // aço preciso ter em obra em setembro?").
            { valor: 'insumos' as Aba, rotulo: 'Desembolso por insumo' },
          ]}
        />
      )}
    </>
  )

  const acoes = orcamentoId && podeEditar
    ? <Btn tam="sm" variant="primary" onClick={() => setDistribuindo(true)}><Wand2 size={13} />Distribuir no tempo</Btn>
    : null

  return (
    <PaginaShell pagina="cronograma" seletor={seletor} acoes={acoes}>
      <GraficoEstilos />
      <div style={{ padding: '18px 22px 40px', overflowY: 'auto' }}>
        {!orcamentoId ? (
          <Empty>Selecione um orçamento para montar o cronograma físico-financeiro.</Empty>
        ) : isLoading ? (
          <Loading texto="Carregando o cronograma…" />
        ) : !cronograma || cronograma.competencias.length === 0 ? (
          <Empty acao={podeEditar
            ? <Btn variant="primary" onClick={() => setDistribuindo(true)}><Wand2 size={14} />Gerar distribuição linear</Btn>
            : undefined}>
            Este orçamento ainda não tem cronograma. Gere a <b>distribuição linear</b> entre duas
            competências — é o ponto de partida que o setor usa, e você ajusta célula a célula depois.
          </Empty>
        ) : (
          <>
            <Card style={{ display: 'flex', gap: 28, flexWrap: 'wrap', padding: '16px 20px' }}>
              <Kpi rotulo="Total distribuído" valor={brlCurto(cronograma.total)} apoio={`${cronograma.competencias.length} competência(s)`} />
              <Kpi rotulo="Total do orçamento" valor={brlCurto(orcamento?.valor_total)} apoio="com BDI" />
              <Kpi
                rotulo="Consistência"
                valor={cronograma.validacao.consistente
                  ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 17 }}><CheckCircle2 size={17} color="var(--good)" />100%</span>
                  : <span style={{ color: 'var(--danger-ink)', fontSize: 17 }}>{cronograma.validacao.problemas.length} etapa(s)</span>}
                apoio={cronograma.validacao.consistente ? 'toda etapa soma 100%' : 'soma diferente de 100%'}
              />
              {curvaS && (
                <Kpi rotulo="Realizado acumulado" valor={brlCurto(curvaS.total_realizado)}
                  apoio={<Link to="/app/sil" style={{ color: 'var(--net-ink)', textDecoration: 'none' }}>consumo físico do SIL ↗</Link>} />
              )}
            </Card>

            {!cronograma.validacao.consistente && (
              <Aviso tom="danger">
                <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
                <span>
                  Há etapa cuja distribuição não fecha 100%:{' '}
                  {cronograma.validacao.problemas.map(p => `${p.soma_percentual}% (faltam ${p.diferenca})`).join(' · ')}.
                  Enquanto não fechar, a curva S subestima o previsto.
                </span>
              </Aviso>
            )}

            {aba === 'grade' && (
              <>
                <SectHead right={
                  <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                    {podeEditar ? 'clique numa célula para ajustar o percentual' : 'somente leitura'}
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
                        <tr key={linha.etapa ?? 'geral'} className="orc-linha">
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
                                        setRecado('Percentual atualizado — valor previsto e curva S refeitos.')
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
                        <td style={{
                          padding: '9px 13px', borderTop: '2px solid var(--line)', ...CAPS,
                          position: 'sticky', left: 0, background: 'var(--surface-2)',
                        }}>Desembolso previsto</td>
                        {cronograma.competencias.map(c => (
                          <td key={c} style={{
                            padding: '9px 11px', borderTop: '2px solid var(--line)', textAlign: 'right',
                            ...mono, fontWeight: 700, color: 'var(--ink)', background: 'var(--surface-2)',
                          }}>{brlCurto(somaPorCompetencia[c] ?? 0)}</td>
                        ))}
                        <td style={{
                          padding: '9px 13px', borderTop: '2px solid var(--line)', textAlign: 'right',
                          ...mono, fontWeight: 800, color: 'var(--ink)', background: 'var(--surface-2)',
                        }}>{brl(cronograma.total)}</td>
                      </tr>
                    </tbody>
                  </table>
                </Card>

                <Aviso tom="info">
                  <InfoIcon size={15} style={{ flex: 'none', marginTop: 1 }} />
                  <span>
                    O planejador digita <b>percentual</b>, não valor — é o que sobrevive a uma mudança de
                    preço na planilha. A linha de baixo é o <b>desembolso previsto</b> do mês, que alimenta
                    o fluxo de caixa projetado no{' '}
                    <Link to="/app/erp" style={{ color: 'inherit', fontWeight: 700 }}>ERP</Link>.
                    Gantt, precedências e avanço medido são do módulo <b>PDCA</b>, não daqui.
                  </span>
                </Aviso>
              </>
            )}

            {aba === 'insumos' && orcamentoId && <PainelDesembolso orcamentoId={orcamentoId} />}

            {aba === 'curva' && (
              <>
                <SectHead>Curva S — previsto × realizado acumulado</SectHead>
                {!curvaS || curvaS.serie.length === 0 ? (
                  <Empty>Sem série para desenhar. Distribua o cronograma primeiro.</Empty>
                ) : (
                  <>
                    <Card>
                      <CurvaSGrafico
                        altura={260}
                        serie={curvaS.serie.map(p => ({
                          competencia: mesBR(p.competencia),
                          previstoPct: Number(p.previsto_pct_acumulado ?? 0),
                          realizadoPct: Number(p.realizado_pct_acumulado ?? 0),
                          previsto: Number(p.previsto_acumulado),
                          realizado: Number(p.realizado_acumulado),
                        }))}
                      />
                    </Card>

                    <SectHead>Mês a mês</SectHead>
                    <Card pad={false} style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                        <thead>
                          <tr>
                            {['Competência', 'Previsto', 'Previsto acum.', '% acum.', 'Realizado', 'Realizado acum.', '% acum.', 'Desvio acum.'].map((h, i) => (
                              <th key={h} style={{
                                ...CAPS, padding: '9px 12px', textAlign: i === 0 ? 'left' : 'right',
                                borderBottom: '1px solid var(--line)', background: 'var(--surface-2)',
                              }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {curvaS.serie.map(p => {
                            const desvio = Number(p.desvio_acumulado)
                            return (
                              <tr key={p.competencia} className="orc-linha">
                                <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', fontWeight: 600, color: 'var(--ink)' }}>{mesBR(p.competencia)}</td>
                                <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono }}>{brl(p.previsto)}</td>
                                <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: 'var(--ink-3)' }}>{brl(p.previsto_acumulado)}</td>
                                <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: 'var(--ink-3)' }}>{pct(p.previsto_pct_acumulado, 1)}</td>
                                <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono }}>{brl(p.realizado)}</td>
                                <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: 'var(--ink-3)' }}>{brl(p.realizado_acumulado)}</td>
                                <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: 'var(--ink-3)' }}>{pct(p.realizado_pct_acumulado, 1)}</td>
                                <td style={{
                                  padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono,
                                  color: desvio > 0 ? 'var(--danger-ink)' : desvio < 0 ? 'var(--good-ink)' : 'var(--ink-3)',
                                }}>{brl(p.desvio_acumulado)}</td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </Card>
                    <p style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 10 }}>
                      O realizado da curva S é <b>consumo físico</b> apropriado pelo SIL por obra e etapa
                      ({curvaS.fonte_realizado}) — não é desembolso de caixa. Desvio positivo = gastou-se
                      material adiante do planejado.
                    </p>
                  </>
                )}
              </>
            )}
          </>
        )}
      </div>

      {distribuindo && orcamentoId && (
        <ModalDistribuir
          salvando={distribuir.isPending}
          onFechar={() => setDistribuindo(false)}
          onDistribuir={async (inicio, fim) => {
            await distribuir.mutateAsync({ id: orcamentoId, inicio, fim })
            setDistribuindo(false)
            setRecado('Distribuição linear gerada — ajuste as células que precisarem.')
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

function ModalDistribuir({ salvando, onFechar, onDistribuir }: {
  salvando: boolean; onFechar: () => void; onDistribuir: (inicio: string, fim: string) => void
}) {
  const [inicio, setInicio] = useState('')
  const [fim, setFim] = useState('')
  const [erro, setErro] = useState('')
  return (
    <Modal
      titulo="Distribuir o custo no tempo"
      onClose={onFechar}
      rodape={
        <>
          <Btn onClick={onFechar}>Cancelar</Btn>
          <Btn variant="primary" disabled={salvando} onClick={() => {
            if (!inicio || !fim) { setErro('Informe as duas competências.'); return }
            if (fim < inicio) { setErro('A competência final não pode ser anterior à inicial.'); return }
            onDistribuir(`${inicio}-01`, `${fim}-01`)
          }}>Gerar</Btn>
        </>
      }
    >
      {erro && <Aviso tom="danger">{erro}</Aviso>}
      <Aviso>
        <CalendarRange size={15} style={{ flex: 'none', marginTop: 1 }} />
        Gera a distribuição <b>linear</b> entre os dois meses: ponto de partida, não verdade. É assim
        que as ferramentas do mercado funcionam — o planejador ajusta as células depois.
      </Aviso>
      <div style={{ height: 14 }} />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Field label="Competência inicial">
          <input type="month" value={inicio} onChange={e => setInicio(e.target.value)} style={{ ...inp, ...mono }} />
        </Field>
        <Field label="Competência final">
          <input type="month" value={fim} onChange={e => setFim(e.target.value)} style={{ ...inp, ...mono }} />
        </Field>
      </div>
      <Pill kind="slate">Substitui a distribuição atual do orçamento</Pill>
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
