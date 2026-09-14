import { useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, History, Info, Send, Undo2 } from 'lucide-react'
import { Btn, Card, Empty, Loading, Pill, SectionHead } from '@/components/malha'
import { dateToBR } from '@/utils/dates'
import { useApontamentos, useApontarEmLote, useEstornar } from '../hooks'
import { daIso, hojeIso, paraIso, primeiraMensagem, somarDias } from '../lib'
import type {
  Apontamento, Atividade, AvancoDoCronograma, Cronograma, LinhaDeApontamento,
} from '../types'

interface Props {
  cronograma: Cronograma
  atividades: Atividade[]
  avanco: AvancoDoCronograma
  podeApontar: boolean
  tetoDoLote: number
}

/** O recorte da fila. Não são "filtros de tabela": cada um responde a uma
 *  pergunta que o engenheiro faz na segunda-feira olhando a obra. */
type Recorte = 'abertas' | 'atrasadas' | 'semana' | 'todas'

const RECORTES: { chave: Recorte; rotulo: string; ajuda: string }[] = [
  { chave: 'abertas', rotulo: 'Em execução', ajuda: 'Deveriam estar acontecendo hoje pelo plano' },
  { chave: 'atrasadas', rotulo: 'Vencidas', ajuda: 'O término previsto passou e o avanço não fechou' },
  { chave: 'semana', rotulo: 'Começam em 7 dias', ajuda: 'Entram na próxima semana — o que precisa estar liberado' },
  { chave: 'todas', rotulo: 'Todas as folhas', ajuda: 'O plano inteiro, inclusive o que nem começou' },
]

/**
 * **A grade da semana** — o cockpit do avanço.
 *
 * O gesto que ela serve é um só e é concreto: na segunda-feira de manhã o
 * engenheiro abre as frentes que deveriam estar acontecendo, digita quanto cada
 * uma andou e manda **de uma vez**. Por isso a tela abre já filtrada no que está
 * em execução (e não na lista inteira do plano), por isso a coluna de digitação
 * fica à direita do que se precisa saber para preenchê-la — previsto, avanço
 * atual, situação — e por isso o envio é uma transação só: metade da semana no
 * sistema e metade no caderno é pior que nada gravado.
 *
 * O que se digita é o **delta**, não o acumulado. É a diferença entre "andou 15%
 * esta semana" e "está em 65%", e a primeira é a pergunta que alguém no canteiro
 * sabe responder olhando o serviço.
 */
export default function PainelAvanco({
  cronograma, atividades, avanco, podeApontar, tetoDoLote,
}: Props) {
  const [recorte, setRecorte] = useState<Recorte>('abertas')
  const [data, setData] = useState(hojeIso())
  const [rascunho, setRascunho] = useState<Record<number, string>>({})
  const [erro, setErro] = useState('')
  const [feito, setFeito] = useState('')

  const lote = useApontarEmLote(cronograma.cronograma_id)
  const hoje = hojeIso()
  const emSeteDias = paraIso(somarDias(daIso(hoje), 7))

  const folhas = useMemo(() => {
    const comFilhos = new Set(atividades.filter(a => a.pai != null).map(a => a.pai as number))
    return atividades.filter(a => !comFilhos.has(a.atividade_id))
  }, [atividades])

  const linhas = useMemo(() => {
    const enriquecidas = folhas.map(a => {
      const dados = avanco.por_atividade[String(a.atividade_id)]
      const atual = dados?.avanco ?? 0
      const comecou = !!a.inicio_cedo && a.inicio_cedo <= hoje
      const venceu = !!a.termino_cedo && a.termino_cedo < hoje
      return {
        atividade: a,
        atual,
        semPeso: dados?.peso == null,
        lancamentos: dados?.lancamentos ?? 0,
        concluida: atual >= 100,
        atrasada: venceu && atual < 100,
        emExecucao: comecou && !venceu && atual < 100,
        entraEmBreve: !!a.inicio_cedo && a.inicio_cedo > hoje && a.inicio_cedo <= emSeteDias,
      }
    })
    const filtradas = enriquecidas.filter(l => {
      if (recorte === 'todas') return true
      if (recorte === 'atrasadas') return l.atrasada
      if (recorte === 'semana') return l.entraEmBreve
      return l.emExecucao || l.atrasada
    })
    // Crítica primeiro, depois a que venceu há mais tempo: é a ordem em que o
    // engenheiro decide onde põe a equipe, e não a ordem da EAP.
    return filtradas.sort((x, y) => {
      if (x.atividade.critica !== y.atividade.critica) return x.atividade.critica ? -1 : 1
      if (x.atrasada !== y.atrasada) return x.atrasada ? -1 : 1
      return (x.atividade.termino_cedo ?? '').localeCompare(y.atividade.termino_cedo ?? '')
    })
  }, [folhas, avanco, recorte, hoje, emSeteDias])

  const preenchidas = Object.entries(rascunho)
    .map(([id, valor]) => ({ id: Number(id), valor: valor.trim().replace(',', '.') }))
    .filter(l => l.valor !== '' && Number.isFinite(Number(l.valor)) && Number(l.valor) !== 0)

  const enviar = async () => {
    setErro(''); setFeito('')
    if (!preenchidas.length) {
      setErro('Nada para apontar: digite o avanço de ao menos uma frente.')
      return
    }
    if (preenchidas.length > tetoDoLote) {
      setErro(`São ${preenchidas.length} frentes e o limite por envio é ${tetoDoLote}. Mande em dois blocos.`)
      return
    }
    const payload: LinhaDeApontamento[] = preenchidas.map(l => ({
      atividade: l.id, data, percentual: l.valor,
    }))
    try {
      const saida = await lote.mutateAsync(payload)
      setRascunho({})
      setFeito(
        `${saida.apontamentos} ${saida.apontamentos === 1 ? 'frente apontada' : 'frentes apontadas'} em ${dateToBR(data)}`
        + (saida.etapas_sincronizadas
          ? ` · ${saida.etapas_sincronizadas} ${saida.etapas_sincronizadas === 1 ? 'etapa da obra atualizada' : 'etapas da obra atualizadas'}`
          : ''),
      )
    } catch (e) {
      setErro(primeiraMensagem(e))
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '4px 2px 20px' }}>
      <Card style={{ padding: 16 }}>
        <SectionHead
          sub="Digite quanto cada frente andou — o que entra é o avanço do período, não o acumulado"
          right={
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--ink-3)' }}>
                Data do avanço
                <input
                  type="date" value={data} max={hoje}
                  onChange={e => setData(e.target.value)}
                  style={{
                    border: '1px solid var(--line)', borderRadius: 7, padding: '4px 8px',
                    fontSize: 12.5, background: 'var(--surface)', color: 'var(--ink)',
                  }}
                />
              </label>
              <Btn
                tam="sm" variant="brand"
                onClick={() => void enviar()}
                disabled={!podeApontar || lote.isPending || !preenchidas.length}
                title={podeApontar ? 'Grava tudo numa transação só' : 'Você não tem a permissão de apontar avanço'}
              >
                <Send size={14} />
                {lote.isPending ? 'Apontando…' : `Apontar ${preenchidas.length || ''}`.trim()}
              </Btn>
            </div>
          }
        >
          Apontamento da semana
        </SectionHead>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          {RECORTES.map(r => (
            <button
              key={r.chave} type="button" title={r.ajuda} onClick={() => setRecorte(r.chave)}
              style={{
                border: '1px solid ' + (recorte === r.chave ? 'var(--brand)' : 'var(--line)'),
                borderRadius: 999, padding: '3px 11px', fontSize: 12, cursor: 'pointer',
                background: recorte === r.chave ? 'var(--inset)' : 'transparent',
                color: recorte === r.chave ? 'var(--ink)' : 'var(--ink-3)',
                fontWeight: recorte === r.chave ? 600 : 400,
              }}
            >{r.rotulo}</button>
          ))}
        </div>

        {!cronograma.calculado_em && (
          <Aviso tom="aviso">
            Este plano ainda não foi calculado: sem as datas do CPM, a fila não sabe o que deveria
            estar acontecendo hoje. Rode <strong>Calcular CPM</strong> e volte.
          </Aviso>
        )}
        {cronograma.status !== 'vigente' && (
          <Aviso tom="aviso">
            Só o plano <strong>vigente</strong> recebe avanço — este está {cronograma.status_rotulo.toLowerCase()}.
            Publicar o plano é o que transforma a régua em compromisso, e é contra ela que o avanço é medido.
          </Aviso>
        )}
        {erro && <Aviso tom="erro">{erro}</Aviso>}
        {feito && <Aviso tom="bom">{feito}</Aviso>}

        {linhas.length === 0 ? (
          <Empty>
            {recorte === 'abertas'
              ? 'Nenhuma frente deveria estar em execução hoje pelo plano vigente — troque o recorte para ver o resto.'
              : 'Nada neste recorte. Troque o filtro para ver outras frentes do plano.'}
          </Empty>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr style={{ color: 'var(--ink-3)', textAlign: 'left' }}>
                  <Th style={{ width: 92 }}>EAP</Th>
                  <Th>Frente</Th>
                  <Th style={{ width: 170 }}>Previsto</Th>
                  <Th style={{ width: 118 }}>Situação</Th>
                  <Th style={{ width: 168 }}>Avanço acumulado</Th>
                  <Th style={{ width: 132, textAlign: 'right' }}>Avanço do período</Th>
                </tr>
              </thead>
              <tbody>
                {linhas.map(l => (
                  <tr key={l.atividade.atividade_id} style={{ borderTop: '1px solid var(--line)' }}>
                    <Td style={{ fontFamily: 'var(--font-mono, monospace)', color: 'var(--ink-2)' }}>
                      {l.atividade.codigo}
                    </Td>
                    <Td>
                      <div style={{ color: 'var(--ink)' }}>{l.atividade.nome}</div>
                      <div style={{ display: 'flex', gap: 6, marginTop: 3, flexWrap: 'wrap' }}>
                        {/* Integração visível: o que conversa no backend conversa
                            na tela. A etapa vem do cadastro de obra e o item
                            orçado do Orçamento — e é por eles que este avanço
                            chega ao resumo da obra e ao dinheiro. */}
                        {l.atividade.etapa_nome && <Chip>{l.atividade.etapa_nome}</Chip>}
                        {l.atividade.local_rotulo && <Chip>{l.atividade.local_rotulo}</Chip>}
                        {l.atividade.item_orcado_rotulo && <Chip>R$ · {l.atividade.item_orcado_rotulo}</Chip>}
                        {l.semPeso && <Chip alerta>sem peso — não pondera a obra</Chip>}
                      </div>
                    </Td>
                    <Td style={{ color: 'var(--ink-3)' }}>
                      {l.atividade.inicio_cedo && l.atividade.termino_cedo
                        ? `${dateToBR(l.atividade.inicio_cedo)} a ${dateToBR(l.atividade.termino_cedo)}`
                        : 'sem data — rode o CPM'}
                    </Td>
                    <Td>
                      {l.concluida ? <Pill kind="good">concluída</Pill>
                        : l.atrasada ? <Pill kind="danger">vencida</Pill>
                        : l.atividade.critica ? <Pill kind="accent">crítica</Pill>
                        : l.emExecucao ? <Pill kind="info">em execução</Pill>
                        : <Pill kind="slate">a iniciar</Pill>}
                    </Td>
                    <Td>
                      <Barra valor={l.atual} />
                    </Td>
                    <Td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <input
                          inputMode="decimal" placeholder="0"
                          value={rascunho[l.atividade.atividade_id] ?? ''}
                          disabled={!podeApontar || cronograma.status !== 'vigente'}
                          onChange={e => setRascunho(atual => ({
                            ...atual, [l.atividade.atividade_id]: e.target.value,
                          }))}
                          title={
                            l.atividade.eh_marco
                              ? 'Marco: 100 para cumprir, -100 para desfazer'
                              : `Restam ${(100 - l.atual).toFixed(1)} pontos para fechar esta frente`
                          }
                          style={{
                            width: 74, textAlign: 'right', border: '1px solid var(--line)',
                            borderRadius: 7, padding: '5px 8px', fontSize: 12.5,
                            background: 'var(--surface)', color: 'var(--ink)',
                          }}
                        />
                        <span style={{ color: 'var(--ink-3)' }}>%</span>
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p style={{ fontSize: 11.5, color: 'var(--ink-3)', margin: '12px 0 0', lineHeight: 1.7 }}>
          <Info size={12} style={{ verticalAlign: -2 }} /> O avanço do período é um <strong>delta</strong>:
          15 numa frente que está em 50% a leva a 65%. Ele sobe a árvore ponderado pelo peso, alimenta a
          curva S realizada e atualiza o percentual da etapa da obra. Errou? O lançamento não se apaga —
          estorna-se abaixo, com motivo.
        </p>
      </Card>

      <Historico cronograma={cronograma} podeApontar={podeApontar} />
    </div>
  )
}

/**
 * O livro, na ordem em que foi escrito. **O estorno aparece como linha**, e não
 * como sumiço do lançamento errado: quem confere a medição daqui a dois anos
 * precisa ver o que foi apontado, o que foi corrigido e por quê.
 */
function Historico({ cronograma, podeApontar }: { cronograma: Cronograma; podeApontar: boolean }) {
  const [pagina, setPagina] = useState(1)
  const consulta = useApontamentos({
    cronograma: cronograma.cronograma_id, ordering: '-registrado_em', page: pagina, page_size: 25,
  })
  const estornar = useEstornar(cronograma.cronograma_id)
  const [erro, setErro] = useState('')

  const pedirEstorno = async (a: Apontamento) => {
    const motivo = window.prompt(
      `Estornar ${a.percentual}% de ${a.atividade_codigo}?\n\n`
      + 'O lançamento continua no livro e a correção aponta para ele. O motivo é obrigatório:',
    )
    if (motivo == null) return
    setErro('')
    try {
      await estornar.mutateAsync({ id: a.apontamento_id, motivo })
    } catch (e) {
      setErro(primeiraMensagem(e))
    }
  }

  const itens = consulta.data?.results ?? []

  return (
    <Card style={{ padding: 16 }}>
      <SectionHead sub="Append-only: corrigir é estornar, e as duas linhas ficam">
        <History size={13} style={{ verticalAlign: -2, marginRight: 6 }} />
        Histórico de apontamentos
      </SectionHead>

      {erro && <Aviso tom="erro">{erro}</Aviso>}

      {consulta.isLoading ? (
        <Loading o="o histórico" />
      ) : itens.length === 0 ? (
        <Empty>Nenhum apontamento ainda — a curva realizada aparece com o primeiro avanço.</Empty>
      ) : (
        <>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {itens.map(a => {
              const negativo = Number(a.percentual) < 0
              return (
                <div
                  key={a.apontamento_id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12, padding: '9px 0',
                    borderTop: '1px solid var(--line)', fontSize: 12.5,
                    opacity: a.estornado ? 0.55 : 1,
                  }}
                >
                  <span style={{ width: 84, color: 'var(--ink-3)' }}>{dateToBR(a.data)}</span>
                  <span
                    className="num"
                    style={{
                      width: 74, textAlign: 'right', fontWeight: 700,
                      color: negativo ? 'var(--danger-ink)' : 'var(--good-ink)',
                      textDecoration: a.estornado ? 'line-through' : undefined,
                    }}
                  >
                    {negativo ? '' : '+'}{Number(a.percentual).toFixed(2)}%
                  </span>
                  <span style={{ minWidth: 0, flex: 1 }}>
                    <span style={{ fontFamily: 'var(--font-mono, monospace)', color: 'var(--ink-2)' }}>
                      {a.atividade_codigo}
                    </span>{' '}
                    {a.atividade_nome}
                    {a.observacao && (
                      <span style={{ color: 'var(--ink-3)' }}> — {a.observacao}</span>
                    )}
                  </span>
                  {a.estorna && <Pill kind="danger">estorno</Pill>}
                  {a.estornado && <Pill kind="slate">estornado</Pill>}
                  {a.origem !== 'web' && <Pill kind="net">{a.origem_rotulo}</Pill>}
                  <span style={{ width: 130, color: 'var(--ink-3)', textAlign: 'right' }}>
                    {a.apontado_por || '—'}
                  </span>
                  <Btn
                    tam="sm"
                    disabled={!podeApontar || a.estornado || !!a.estorna || estornar.isPending}
                    onClick={() => void pedirEstorno(a)}
                    title={
                      a.estornado ? 'Já estornado'
                        : a.estorna ? 'Estorno não se estorna — aponte o avanço de novo'
                        : 'Corrigir com um lançamento de sinal contrário'
                    }
                  >
                    <Undo2 size={13} /> Estornar
                  </Btn>
                </div>
              )
            })}
          </div>

          {(consulta.data?.next || pagina > 1) && (
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
              <Btn tam="sm" disabled={pagina <= 1} onClick={() => setPagina(p => p - 1)}>Anterior</Btn>
              <Btn tam="sm" disabled={!consulta.data?.next} onClick={() => setPagina(p => p + 1)}>Próxima</Btn>
            </div>
          )}
        </>
      )}
    </Card>
  )
}

function Barra({ valor }: { valor: number }) {
  const largura = Math.max(0, Math.min(valor, 100))
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, width: '100%' }}>
      <span style={{ flex: 1, height: 7, borderRadius: 999, background: 'var(--inset)', overflow: 'hidden' }}>
        <span style={{
          display: 'block', height: '100%', width: largura + '%',
          background: largura >= 100 ? 'var(--good)' : 'var(--brand)',
        }} />
      </span>
      <span className="num" style={{ width: 46, textAlign: 'right', color: 'var(--ink-2)' }}>
        {valor.toFixed(1)}%
      </span>
    </span>
  )
}

function Chip({ children, alerta }: { children: React.ReactNode; alerta?: boolean }) {
  return (
    <span style={{
      fontSize: 10.5, padding: '1px 7px', borderRadius: 999,
      background: alerta ? 'var(--danger-soft)' : 'var(--inset)',
      color: alerta ? 'var(--danger-ink)' : 'var(--ink-3)',
      whiteSpace: 'nowrap', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis',
    }}>
      {children}
    </span>
  )
}

function Aviso({ tom, children }: { tom: 'erro' | 'aviso' | 'bom'; children: React.ReactNode }) {
  const cores = {
    erro: { bg: 'var(--danger-soft)', fg: 'var(--danger-ink)', icone: <AlertTriangle size={13} /> },
    aviso: { bg: 'var(--accent-soft)', fg: 'var(--accent-ink)', icone: <AlertTriangle size={13} /> },
    bom: { bg: 'var(--good-soft)', fg: 'var(--good-ink)', icone: <CheckCircle2 size={13} /> },
  }[tom]
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 8, background: cores.bg, color: cores.fg,
      borderRadius: 'var(--r-sm)', padding: '8px 11px', fontSize: 12.5, marginBottom: 12,
      lineHeight: 1.6,
    }}>
      <span style={{ marginTop: 2 }}>{cores.icone}</span>
      <span>{children}</span>
    </div>
  )
}

function Th({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <th style={{
      fontSize: 10.5, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 700,
      padding: '0 10px 8px 0', ...style,
    }}>{children}</th>
  )
}

function Td({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <td style={{ padding: '9px 10px 9px 0', verticalAlign: 'top', ...style }}>{children}</td>
}
