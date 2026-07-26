import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle, ArrowUpRight, Building2, CalendarRange, Database, FileSpreadsheet,
  Layers, Lock, PieChart, TrendingUp,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Aviso, Btn, Card, CAPS, Empty, Kpi, Loading, mono, Num, OrcStyles, Pill, SectHead } from '../ui'
import { brl, brlCurto, dataBR, mesBR, pct, STATUS_ESTADO } from '../lib'
import { useBasesResumo, useControle, useOrcamentos } from '../hooks'
import { PAGINAS, type ChavePagina } from '../paginas'
import type { ControleLinha, Orcamento } from '../types'

const ICONES: Record<ChavePagina, typeof Layers> = {
  orcar: FileSpreadsheet,
  controlar: Layers,
  cronograma: CalendarRange,
  bases: Database,
  incorporacao: Building2,
}

interface Decisao {
  id: string
  urgencia: 'danger' | 'amber' | 'info'
  titulo: string
  detalhe: string
  paraOnde: string
  rotuloAcao: string
}

function montarFila(orcamentos: Orcamento[], controle: ControleLinha[]): Decisao[] {
  const fila: Decisao[] = []

  for (const linha of controle) {
    if (!linha.estourado || linha.orcado === null) continue
    const excesso = Number(linha.comprometido) - Number(linha.orcado)
    fila.push({
      id: `estouro-${linha.obra}`,
      urgencia: 'danger',
      titulo: `${linha.obra_nome} comprometeu acima do orçado`,
      detalhe: `${brl(linha.comprometido)} comprometidos contra ${brl(linha.orcado)} orçados — ${brl(excesso)} de excesso já contratado.`,
      paraOnde: `/app/orcamento/controlar?obra=${linha.obra}`,
      rotuloAcao: 'Ver as quatro colunas',
    })
  }

  for (const linha of controle) {
    if (linha.orcamento !== null || linha.orcado !== null) continue
    fila.push({
      id: `sem-regua-${linha.obra}`,
      urgencia: 'amber',
      titulo: `${linha.obra_nome} não tem orçamento aprovado`,
      detalhe: `Já há ${brl(linha.comprometido)} comprometidos e ${brl(linha.aplicado)} aplicados sem régua de custo para comparar.`,
      paraOnde: '/app/orcamento/orcar',
      rotuloAcao: 'Montar a planilha',
    })
  }

  for (const orcamento of orcamentos) {
    if (orcamento.status !== 'rascunho') continue
    if (orcamento.total_itens === 0) {
      fila.push({
        id: `vazio-${orcamento.orcamento_id}`,
        urgencia: 'info',
        titulo: `${orcamento.descricao} está vazio`,
        detalhe: `Rascunho v${orcamento.versao} de ${orcamento.obra_nome} criado em ${dataBR(orcamento.criado_em)}, ainda sem nenhuma linha.`,
        paraOnde: `/app/orcamento/orcar?orcamento=${orcamento.orcamento_id}`,
        rotuloAcao: 'Abrir a planilha',
      })
    } else {
      fila.push({
        id: `rascunho-${orcamento.orcamento_id}`,
        urgencia: 'info',
        titulo: `${orcamento.descricao} aguarda aprovação`,
        detalhe: `Rascunho v${orcamento.versao} com ${orcamento.total_itens} linhas e ${brl(orcamento.valor_total)}. Enquanto não for aprovado, não vale como régua de custo.`,
        paraOnde: `/app/orcamento/orcar?orcamento=${orcamento.orcamento_id}`,
        rotuloAcao: 'Revisar e aprovar',
      })
    }
  }

  const ordem = { danger: 0, amber: 1, info: 2 }
  return fila.sort((a, b) => ordem[a.urgencia] - ordem[b.urgencia])
}

export default function HubPage() {
  const { hasPermission } = useAuth()
  const { data: pagina, isLoading: carregandoOrc, isError: erroOrc } = useOrcamentos({ page_size: 100, ordering: '-criado_em' })
  const podeVerControle = hasPermission('orcamento.relatorio.view')
  const { data: controle, isLoading: carregandoCtrl } = useControle(undefined)
  const { data: bases } = useBasesResumo()

  const orcamentos = useMemo(() => pagina?.results ?? [], [pagina])
  const linhas = useMemo(() => (podeVerControle ? controle ?? [] : []), [controle, podeVerControle])
  const fila = useMemo(() => montarFila(orcamentos, linhas), [orcamentos, linhas])

  const aprovados = orcamentos.filter(o => o.status === 'aprovado')
  const totalAprovado = aprovados.reduce((soma, o) => soma + Number(o.valor_total || 0), 0)
  const rascunhos = orcamentos.filter(o => o.status === 'rascunho').length
  const obrasEstouradas = linhas.filter(l => l.estourado).length
  const comprometidoTotal = linhas.reduce((soma, l) => soma + Number(l.comprometido || 0), 0)
  const aplicadoTotal = linhas.reduce((soma, l) => soma + Number(l.aplicado || 0), 0)

  if (carregandoOrc) return <Loading texto="Carregando o Orçamento…" />

  return (
    <div className="orc-tela" style={{ padding: '22px 24px 40px', background: 'var(--ground)', minHeight: '100%' }}>
      <OrcStyles />

      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, flexWrap: 'wrap', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontFamily: 'var(--display)', fontSize: 25, fontWeight: 800, color: 'var(--ink)', letterSpacing: '-0.01em' }}>
            Orçamento
          </h1>
          <p style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 3, maxWidth: 620, lineHeight: 1.55 }}>
            A régua de custo da obra: monta-se aqui, congela-se na aprovação e é contra ela que
            Suprimentos, Estoque e Financeiro são medidos.
          </p>
        </div>
        <div style={{ flex: 1 }} />
        <Link to="/app/orcamento/orcar" style={{ textDecoration: 'none' }}>
          <Btn variant="primary"><FileSpreadsheet size={15} />Abrir a planilha</Btn>
        </Link>
      </div>

      <Card style={{ display: 'flex', gap: 30, flexWrap: 'wrap', padding: '17px 20px', marginBottom: 8 }}>
        <Kpi rotulo="Orçado aprovado" valor={brlCurto(totalAprovado)} apoio={`${aprovados.length} orçamento(s) vigente(s)`} />
        <Kpi rotulo="Em rascunho" valor={<Num forte>{rascunhos}</Num>} apoio="ainda não valem como régua" />
        {podeVerControle ? (
          <>
            <Kpi
              rotulo="Comprometido"
              valor={brlCurto(comprometidoTotal)}
              apoio={<Link to="/app/scm" style={{ color: 'var(--net-ink)', textDecoration: 'none' }}>pedidos do Suprimentos ↗</Link>}
            />
            <Kpi
              rotulo="Aplicado"
              valor={brlCurto(aplicadoTotal)}
              apoio={<Link to="/app/sil" style={{ color: 'var(--net-ink)', textDecoration: 'none' }}>consumo do Estoque ↗</Link>}
            />
            <Kpi
              rotulo="Obras estouradas"
              valor={<Num forte tom={obrasEstouradas ? 'var(--danger-ink)' : undefined}>{obrasEstouradas}</Num>}
              apoio={carregandoCtrl ? 'apurando…' : 'comprometido acima do orçado'}
            />
          </>
        ) : (
          <div style={{ alignSelf: 'center' }}>
            <Pill kind="slate"><Lock size={11} />Indicadores de controle exigem <code style={{ ...mono, fontSize: 11 }}>orcamento.relatorio.view</code></Pill>
          </div>
        )}
      </Card>

      {erroOrc && <Aviso tom="danger"><AlertTriangle size={15} />Não foi possível carregar os orçamentos agora.</Aviso>}

      <SectHead right={fila.length > 0 ? <Pill kind={fila[0].urgencia === 'danger' ? 'danger' : 'amber'}>{fila.length}</Pill> : undefined}>
        Requer sua decisão
      </SectHead>

      {fila.length === 0 ? (
        <Card style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '15px 18px', fontSize: 13, color: 'var(--ink-2)' }}>
          <span style={{ width: 8, height: 8, borderRadius: 999, background: 'var(--good)' }} />
          Nada pendente: todo orçamento está aprovado e nenhuma obra comprometeu acima da régua.
        </Card>
      ) : (
        <div style={{ display: 'grid', gap: 9 }}>
          {fila.slice(0, 6).map(d => (
            <Card key={d.id} pad={false} style={{ display: 'flex', alignItems: 'stretch', overflow: 'hidden' }}>
              <span style={{
                width: 4, flex: 'none',
                background: d.urgencia === 'danger' ? 'var(--danger)' : d.urgencia === 'amber' ? 'var(--accent)' : 'var(--info)',
              }} />
              <div style={{ flex: 1, minWidth: 0, padding: '13px 16px' }}>
                <div style={{ fontSize: 13.5, fontWeight: 650, color: 'var(--ink)' }}>{d.titulo}</div>
                <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginTop: 3, lineHeight: 1.5 }}>{d.detalhe}</div>
              </div>
              <Link to={d.paraOnde} style={{ alignSelf: 'center', padding: '0 14px', textDecoration: 'none' }}>
                <Btn tam="sm">{d.rotuloAcao}<ArrowUpRight size={13} /></Btn>
              </Link>
            </Card>
          ))}
          {fila.length > 6 && (
            <span style={{ fontSize: 12, color: 'var(--ink-3)', paddingLeft: 4 }}>
              +{fila.length - 6} pendência(s) além destas.
            </span>
          )}
        </div>
      )}

      <SectHead>Onde você quer trabalhar</SectHead>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(268px,1fr))', gap: 12 }}>
        {PAGINAS.map(p => {
          const Icone = ICONES[p.chave]
          const liberada = hasPermission(p.permissao)
          const conteudo = (
            <Card
              className={liberada ? 'orc-lift' : undefined}
              style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 9, opacity: liberada ? 1 : 0.55, cursor: liberada ? 'pointer' : 'not-allowed' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                <span style={{
                  width: 32, height: 32, borderRadius: 'var(--r-sm)', display: 'grid', placeItems: 'center',
                  background: 'var(--accent-soft)', color: 'var(--accent-ink)', flex: 'none',
                }}>
                  <Icone size={17} />
                </span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontFamily: 'var(--display)', fontSize: 15, fontWeight: 700, color: 'var(--ink)' }}>{p.titulo}</div>
                  <div style={{ ...CAPS, fontSize: 10 }}>{p.verbo}</div>
                </div>
                {!liberada && <span style={{ marginLeft: 'auto', color: 'var(--ink-3)' }}><Lock size={14} /></span>}
              </div>
              <p style={{ fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.55, margin: 0 }}>{p.resumo}</p>
            </Card>
          )
          return liberada
            ? <Link key={p.chave} to={p.rota} style={{ textDecoration: 'none' }}>{conteudo}</Link>
            : <div key={p.chave} title={`Exige a permissão ${p.permissao}`}>{conteudo}</div>
        })}
      </div>

      <SectHead right={<Link to="/app/orcamento/orcar" style={{ fontSize: 12, color: 'var(--ink-3)', textDecoration: 'none' }}>ver todos ↗</Link>}>
        Orçamentos recentes
      </SectHead>
      {orcamentos.length === 0 ? (
        <Empty acao={<Link to="/app/orcamento/orcar" style={{ textDecoration: 'none' }}><Btn variant="primary" tam="sm">Criar o primeiro orçamento</Btn></Link>}>
          Nenhum orçamento cadastrado ainda. A planilha começa escolhendo a obra e a base de preço —
          e é ela que faz o Estoque saber se o consumo está dentro do previsto.
        </Empty>
      ) : (
        <Card pad={false} style={{ overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                {['Obra', 'Descrição', 'Versão', 'Base / data-base', 'Status', 'Custo direto', 'Total c/ BDI'].map((h, i) => (
                  <th key={h} style={{
                    ...CAPS, padding: '10px 14px', textAlign: i >= 5 ? 'right' : 'left',
                    borderBottom: '1px solid var(--line)', background: 'var(--surface-2)',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orcamentos.slice(0, 8).map(o => {
                const estado = STATUS_ESTADO[o.status]
                return (
                  <tr key={o.orcamento_id} className="orc-linha">
                    <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--line-2)', color: 'var(--ink-2)' }}>{o.obra_nome}</td>
                    <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--line-2)' }}>
                      <Link to={`/app/orcamento/orcar?orcamento=${o.orcamento_id}`} style={{ color: 'var(--ink)', fontWeight: 600, textDecoration: 'none' }}>
                        {o.descricao}
                      </Link>
                    </td>
                    <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--line-2)', ...mono, color: 'var(--ink-3)' }}>v{o.versao}</td>
                    <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--line-2)', fontSize: 12.5, color: 'var(--ink-3)' }}>
                      {o.base_rotulo ?? 'sem base'} · {mesBR(o.data_base)}
                    </td>
                    <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--line-2)' }}>
                      <Pill kind={estado.kind} pulse={estado.pulse}>{estado.label}</Pill>
                    </td>
                    <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: 'var(--ink-2)' }}>
                      {brl(o.custo_direto_total)}
                    </td>
                    <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, fontWeight: 700, color: 'var(--ink)' }}>
                      {brl(o.valor_total)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}

      <SectHead right={<Link to="/app/orcamento/bases" style={{ fontSize: 12, color: 'var(--ink-3)', textDecoration: 'none' }}>gerir bases ↗</Link>}>
        Bases de preço disponíveis
      </SectHead>
      {!bases || bases.length === 0 ? (
        <Aviso tom="amber">
          <Database size={15} style={{ flex: 'none', marginTop: 1 }} />
          <span>
            Nenhuma base referencial importada. Sem SINAPI, ORSE ou um banco próprio, a planilha só
            aceita item do catálogo da empresa com preço digitado à mão.
            {' '}<Link to="/app/orcamento/bases" style={{ color: 'inherit', fontWeight: 700 }}>Importar uma base</Link>.
          </span>
        </Aviso>
      ) : (
        <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap' }}>
          {bases.slice(0, 8).map(b => (
            <Card key={b.base_id} style={{ padding: '11px 14px', minWidth: 190 }}>
              <div style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>{b.rotulo}</div>
              <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 3, ...mono }}>
                {b.insumos} insumos · {b.composicoes} composições
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--accent-ink)', marginTop: 4 }}>
                {b.adotados_no_catalogo} já adotado(s) no seu catálogo
              </div>
            </Card>
          ))}
        </div>
      )}

      {podeVerControle && linhas.length > 0 && (
        <>
          <SectHead right={<Link to="/app/orcamento/controlar" style={{ fontSize: 12, color: 'var(--ink-3)', textDecoration: 'none' }}>abrir controle ↗</Link>}>
            Consumo do orçado por obra
          </SectHead>
          <div style={{ display: 'grid', gap: 7 }}>
            {linhas.slice(0, 6).map(l => {
              const consumido = l.consumido_pct === null ? null : Number(l.consumido_pct)
              return (
                <Card key={l.obra} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '11px 15px' }}>
                  <span style={{ flex: '0 0 190px', fontSize: 13, fontWeight: 600, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {l.obra_nome}
                  </span>
                  <div style={{ flex: 1, minWidth: 120, height: 8, borderRadius: 999, background: 'var(--inset)', overflow: 'hidden' }}>
                    <div style={{
                      width: `${Math.min(consumido ?? 0, 100)}%`, height: '100%', borderRadius: 999,
                      background: l.estourado ? 'var(--danger)' : (consumido ?? 0) > 85 ? 'var(--accent)' : 'var(--good)',
                    }} />
                  </div>
                  <span style={{ ...mono, fontSize: 12.5, color: 'var(--ink-2)', flex: '0 0 62px', textAlign: 'right' }}>
                    {consumido === null ? '—' : pct(consumido, 1)}
                  </span>
                  <span style={{ ...mono, fontSize: 12.5, color: 'var(--ink-3)', flex: '0 0 120px', textAlign: 'right' }}>
                    {l.orcado === null ? 'sem régua' : brl(l.saldo)}
                  </span>
                  {l.estourado && <Pill kind="danger"><TrendingUp size={11} />estourado</Pill>}
                </Card>
              )
            })}
          </div>
          <p style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 11.5, color: 'var(--ink-3)', marginTop: 10 }}>
            <PieChart size={13} />
            Consumo = comprometido ÷ orçado. O que já virou pedido de compra não está mais disponível,
            mesmo que a nota ainda não tenha chegado.
          </p>
        </>
      )}
    </div>
  )
}
