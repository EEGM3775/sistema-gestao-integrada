import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertTriangle, ExternalLink, Info as InfoIcon, Layers, TrendingUp } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import PaginaShell from '../components/PaginaShell'
import {
  BarrasHorizontais, COR_SERIE, CurvaSGrafico, GraficoEstilos, Legenda, Pareto, TrilhoQuatroColunas,
} from '../components/graficos'
import { Aviso, Btn, Card, CAPS, Drawer, Empty, Info, Kpi, Loading, mono, Pill, SectHead, Select, Seletor } from '../ui'
import { brl, brlCurto, CLASSE_KIND, mesBR, num, pct } from '../lib'

import {
  useControle, useCurvaABC, useCurvaS, useObras, useOrcamentos, usePorCategoria,
} from '../hooks'
import type { ControleLinha } from '../types'

type Aba = 'colunas' | 'abc' | 'composicao'

export default function ControlarPage() {
  const { hasPermission } = useAuth()
  const [params, setParams] = useSearchParams()
  const obraParam = params.get('obra') ? Number(params.get('obra')) : undefined
  const [aba, setAba] = useState<Aba>('colunas')
  const [detalhe, setDetalhe] = useState<ControleLinha | null>(null)

  const { data: obras } = useObras()
  const { data: linhas, isLoading, isError } = useControle(obraParam)
  const { data: listaOrcamentos } = useOrcamentos({ page_size: 200, status: 'aprovado' })

  const podeVer = hasPermission('orcamento.relatorio.view')

  const orcamentoDaObra = useMemo(() => {
    if (!obraParam) return undefined
    return listaOrcamentos?.results.find(o => o.obra === obraParam)
  }, [listaOrcamentos, obraParam])

  const { data: abc, isLoading: carregandoAbc } = useCurvaABC(aba === 'abc' ? orcamentoDaObra?.orcamento_id : undefined)
  const { data: categorias, isLoading: carregandoCat } = usePorCategoria(aba === 'composicao' ? orcamentoDaObra?.orcamento_id : undefined)
  const { data: curvaS } = useCurvaS(obraParam ? orcamentoDaObra?.orcamento_id : undefined)

  const trocarObra = (id: number | '') => {
    const proximo = new URLSearchParams(params)
    if (id === '') proximo.delete('obra')
    else proximo.set('obra', String(id))
    setParams(proximo, { replace: true })
  }

  const totais = useMemo(() => {
    const lista = linhas ?? []
    return {
      orcado: lista.reduce((s, l) => s + Number(l.orcado ?? 0), 0),
      comprometido: lista.reduce((s, l) => s + Number(l.comprometido), 0),
      aplicado: lista.reduce((s, l) => s + Number(l.aplicado), 0),
      realizado: lista.reduce((s, l) => s + Number(l.realizado), 0),
      estouradas: lista.filter(l => l.estourado).length,
      semRegua: lista.filter(l => l.orcado === null).length,
    }
  }, [linhas])

  const seletor = (
    <>
      <Select value={obraParam ?? ''} onChange={e => trocarObra(e.target.value ? Number(e.target.value) : '')} style={{ maxWidth: 230 }}>
        <option value="">Todas as obras</option>
        {obras?.map(o => <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>)}
      </Select>
      <Seletor
        compacto
        valor={aba}
        onChange={setAba}
        opcoes={[
          { valor: 'colunas' as Aba, rotulo: 'Quatro colunas' },
          { valor: 'abc' as Aba, rotulo: 'Curva ABC', travado: !obraParam, motivo: 'Escolha uma obra' },
          { valor: 'composicao' as Aba, rotulo: 'Composição do custo', travado: !obraParam, motivo: 'Escolha uma obra' },
        ]}
      />
    </>
  )

  if (!podeVer) {
    return (
      <PaginaShell pagina="controlar">
        <div style={{ padding: 26 }}>
          <Empty>
            O controle de custo exige a permissão <code style={{ ...mono }}>orcamento.relatorio.view</code>.
            Peça a um administrador do tenant em Papéis e Acessos.
          </Empty>
        </div>
      </PaginaShell>
    )
  }

  return (
    <PaginaShell pagina="controlar" seletor={seletor}>
      <GraficoEstilos />
      <div style={{ padding: '18px 22px 40px', overflowY: 'auto' }}>
        {isError && <Aviso tom="danger"><AlertTriangle size={15} />Não foi possível apurar o controle de custo agora.</Aviso>}
        {isLoading ? <Loading texto="Apurando as quatro colunas…" /> : (linhas ?? []).length === 0 ? (
          <Empty>Nenhuma obra com movimento para apurar.</Empty>
        ) : (
          <>
            <Card style={{ display: 'flex', gap: 28, flexWrap: 'wrap', padding: '16px 20px' }}>
              <Kpi rotulo="Orçado" valor={brlCurto(totais.orcado)} apoio="régua aprovada vigente" />
              <Kpi rotulo="Comprometido" valor={brlCurto(totais.comprometido)} tom={COR_SERIE[0]}
                apoio={<Link to="/app/scm" style={{ color: 'var(--net-ink)', textDecoration: 'none' }}>pedidos do SCM ↗</Link>} />
              <Kpi rotulo="Aplicado" valor={brlCurto(totais.aplicado)} tom={COR_SERIE[1]}
                apoio={<Link to="/app/sil" style={{ color: 'var(--net-ink)', textDecoration: 'none' }}>consumo do SIL ↗</Link>} />
              <Kpi rotulo="Realizado" valor={brlCurto(totais.realizado)} tom={COR_SERIE[2]}
                apoio={<Link to="/app/erp" style={{ color: 'var(--net-ink)', textDecoration: 'none' }}>pago no ERP ↗</Link>} />
              <Kpi rotulo="Saldo orçamentário" valor={brlCurto(totais.orcado - totais.comprometido)} apoio="orçado − comprometido" />
              {totais.estouradas > 0 && (
                <Kpi rotulo="Estouradas" valor={totais.estouradas} tom="var(--danger-ink)" apoio="comprometido acima do orçado" />
              )}
            </Card>

            <Aviso tom="info">
              <InfoIcon size={15} style={{ flex: 'none', marginTop: 1 }} />
              <span>
                As quatro <b>não se somam</b> — são quatro ângulos sobre o mesmo dinheiro. Comprometido
                acima do orçado é estouro contratado antes de acontecer; aplicado muito acima do
                realizado é passivo a pagar; realizado acima do aplicado é adiantamento a fornecedor.
                {linhas?.[0]?.nota_realizado ? <> <b>Cobertura do realizado:</b> {linhas[0].nota_realizado}</> : (
                  <> O <b>realizado</b> cobre o que passou por pedido de compra — despesa lançada direto no
                  ERP é amarrada a empreendimento, não a obra.</>
                )}
              </span>
            </Aviso>

            {aba === 'colunas' && (
              <>
                <SectHead right={<Legenda itens={[
                  { cor: COR_SERIE[0], rotulo: 'Comprometido' },
                  { cor: COR_SERIE[1], rotulo: 'Aplicado' },
                  { cor: COR_SERIE[2], rotulo: 'Realizado' },
                  { cor: 'var(--ink)', rotulo: 'Orçado (marca)' },
                ]} />}>
                  Orçado × comprometido × aplicado × realizado
                </SectHead>

                <Card pad={false} style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, minWidth: 940 }}>
                    <thead>
                      <tr>
                        {['Obra', 'Consumo', 'Orçado', 'Comprometido', 'Aplicado', 'Realizado', 'Saldo', '%', ''].map((h, i) => (
                          <th key={h} style={{
                            ...CAPS, padding: '10px 13px', textAlign: i >= 2 && i <= 7 ? 'right' : 'left',
                            borderBottom: '1px solid var(--line)', background: 'var(--surface-2)',
                            position: 'sticky', top: 0, zIndex: 1,
                          }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {linhas?.map(l => (
                        <tr key={l.obra} className="orc-linha">
                          <td style={{ padding: '9px 13px', borderBottom: '1px solid var(--line-2)', fontWeight: 600, color: 'var(--ink)' }}>
                            {l.obra_nome}
                            {l.orcamento_versao && <span style={{ ...mono, fontSize: 10.5, color: 'var(--ink-3)', marginLeft: 6 }}>v{l.orcamento_versao}</span>}
                          </td>
                          <td style={{ padding: '6px 13px', borderBottom: '1px solid var(--line-2)' }}>
                            <TrilhoQuatroColunas
                              orcado={l.orcado === null ? null : Number(l.orcado)}
                              comprometido={Number(l.comprometido)}
                              aplicado={Number(l.aplicado)}
                              realizado={Number(l.realizado)}
                            />
                          </td>
                          <td style={{ padding: '9px 13px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: 'var(--ink)' }}>
                            {l.orcado === null ? <Pill kind="amber">sem régua</Pill> : brl(l.orcado)}
                          </td>
                          <td style={{ padding: '9px 13px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: COR_SERIE[0] }}>{brl(l.comprometido)}</td>
                          <td style={{ padding: '9px 13px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: COR_SERIE[1] }}>{brl(l.aplicado)}</td>
                          <td style={{ padding: '9px 13px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: COR_SERIE[2] }}>{brl(l.realizado)}</td>
                          <td style={{
                            padding: '9px 13px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono,
                            color: l.estourado ? 'var(--danger-ink)' : 'var(--ink-2)', fontWeight: l.estourado ? 700 : 500,
                          }}>{l.saldo === null ? '—' : brl(l.saldo)}</td>
                          <td style={{ padding: '9px 13px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono }}>
                            {l.consumido_pct === null ? '—' : pct(l.consumido_pct, 1)}
                          </td>
                          <td style={{ padding: '9px 13px', borderBottom: '1px solid var(--line-2)' }}>
                            <Btn tam="sm" onClick={() => setDetalhe(l)}>Abrir</Btn>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>

                {obraParam && curvaS && curvaS.serie.length > 0 && (
                  <>
                    <SectHead right={
                      <Link to={`/app/orcamento/cronograma?orcamento=${orcamentoDaObra?.orcamento_id ?? ''}`}
                        style={{ fontSize: 12, color: 'var(--ink-3)', textDecoration: 'none' }}>
                        editar cronograma ↗
                      </Link>
                    }>
                      Curva S — previsto × realizado
                    </SectHead>
                    <Card>
                      <CurvaSGrafico serie={curvaS.serie.map(p => ({
                        competencia: mesBR(p.competencia),
                        previstoPct: Number(p.previsto_pct_acumulado ?? 0),
                        realizadoPct: Number(p.realizado_pct_acumulado ?? 0),
                        previsto: Number(p.previsto_acumulado),
                        realizado: Number(p.realizado_acumulado),
                      }))} />
                    </Card>
                  </>
                )}
              </>
            )}

            {aba === 'abc' && (
              <>
                <SectHead>Curva ABC do orçado — onde está o dinheiro</SectHead>
                {carregandoAbc ? <Loading /> : !abc || abc.itens.length === 0 ? (
                  <Empty>Este orçamento ainda não tem linhas analíticas para classificar.</Empty>
                ) : (
                  <>
                    <Card style={{ marginBottom: 12 }}>
                      <Pareto itens={abc.itens.slice(0, 40).map(i => ({
                        rotulo: `${i.codigo_eap} ${i.descricao}`,
                        valor: Number(i.valor),
                        acumuladoPct: Number(i.pct_acumulado),
                        classe: i.classe,
                      }))} />
                      {abc.itens.length > 40 && (
                        <p style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 8 }}>
                          Gráfico mostra os 40 itens de maior peso; a tabela abaixo lista todos os {abc.itens.length}.
                        </p>
                      )}
                    </Card>
                    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
                      {(['A', 'B', 'C'] as const).map(classe => {
                        const r = abc.resumo[classe]
                        if (!r) return null
                        return (
                          <Card key={classe} style={{ minWidth: 180 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
                              <Pill kind={CLASSE_KIND[classe]}>Classe {classe}</Pill>
                              <span style={{ ...CAPS }}>{r.itens} itens</span>
                            </div>
                            <div style={{ ...mono, fontSize: 17, fontWeight: 700, color: 'var(--ink)' }}>{brl(r.valor)}</div>
                            <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{pct(r.pct, 1)} do orçamento</div>
                          </Card>
                        )
                      })}
                    </div>
                    <Card pad={false} style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                        <thead>
                          <tr>
                            {['Classe', 'Item', 'Descrição', 'Und', 'Quantidade', 'Valor', '%', '% acum.'].map((h, i) => (
                              <th key={h} style={{
                                ...CAPS, padding: '9px 12px', textAlign: i >= 4 ? 'right' : 'left',
                                borderBottom: '1px solid var(--line)', background: 'var(--surface-2)',
                              }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {abc.itens.map(i => (
                            <tr key={i.item_orcado} className="orc-linha">
                              <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)' }}>
                                <Pill kind={CLASSE_KIND[i.classe]}>{i.classe}</Pill>
                              </td>
                              <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', ...mono, color: 'var(--ink-3)' }}>{i.codigo_eap}</td>
                              <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', color: 'var(--ink-2)' }}>{i.descricao}</td>
                              <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', color: 'var(--ink-3)' }}>{i.unidade}</td>
                              <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono }}>{num(i.quantidade, 2)}</td>
                              <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: 'var(--ink)' }}>{brl(i.valor)}</td>
                              <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: 'var(--ink-3)' }}>{pct(i.pct, 2)}</td>
                              <td style={{ padding: '7px 12px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: 'var(--ink-3)' }}>{pct(i.pct_acumulado, 2)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </Card>
                  </>
                )}
              </>
            )}

            {aba === 'composicao' && (
              <>
                <SectHead>Composição do custo por natureza do insumo</SectHead>
                {carregandoCat ? <Loading /> : !categorias || categorias.categorias.length === 0 ? (
                  <Empty>
                    Nenhuma linha deste orçamento foi explodida em insumos ainda. Use <b>Explodir
                    composição</b> no menu da linha, em Orçar, para abrir a composição em coeficientes —
                    é o que alimenta esta leitura.
                  </Empty>
                ) : (
                  <>
                    {Number(categorias.cobertura_pct) < 99 && (
                      <Aviso tom="amber">
                        <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
                        <span>
                          Este gráfico fala de <b>{pct(categorias.cobertura_pct, 1)}</b> do custo direto —
                          só as linhas já explodidas em insumos entram. O resto da planilha tem preço
                          fechado, sem memória de cálculo.
                        </span>
                      </Aviso>
                    )}
                    <div style={{ height: 12 }} />
                    <Card>
                      <BarrasHorizontais
                        total={Number(categorias.total)}
                        dados={categorias.categorias.map(c => ({ rotulo: c.rotulo, valor: Number(c.valor) }))}
                      />
                      <p style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 14, display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                        <TrendingUp size={13} style={{ flex: 'none', marginTop: 1 }} />
                        Obra intensiva em material se ganha comprando melhor (Suprimentos); intensiva em
                        mão de obra se ganha planejando melhor. Encargos sociais incidem só sobre a
                        parcela de mão de obra.
                      </p>
                    </Card>
                  </>
                )}
              </>
            )}
          </>
        )}
      </div>

      {detalhe && (
        <Drawer titulo={`${detalhe.obra_nome} · controle de custo`} onClose={() => setDetalhe(null)}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 18 }}>
            <Info k="Orçado (custo direto)" v={detalhe.orcado === null ? 'sem régua aprovada' : brl(detalhe.orcado)} m />
            <Info k="Orçado com BDI" v={brl(detalhe.orcado_com_bdi)} m />
            <Info k="Comprometido" v={brl(detalhe.comprometido)} m />
            <Info k="Aplicado" v={brl(detalhe.aplicado)} m />
            <Info k="Realizado" v={brl(detalhe.realizado)} m />
            <Info k="Saldo" v={detalhe.saldo === null ? '—' : brl(detalhe.saldo)} m />
          </div>

          {detalhe.estourado && (
            <Aviso tom="danger">
              <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
              Comprometido ultrapassou o orçado em {brl(Number(detalhe.comprometido) - Number(detalhe.orcado ?? 0))}.
              O excesso já está contratado — revise o orçamento ou renegocie os pedidos abertos.
            </Aviso>
          )}

          <SectHead>Para onde ir</SectHead>
          <div style={{ display: 'grid', gap: 8 }}>
            {[
              { to: `/app/orcamento/orcar?orcamento=${detalhe.orcamento ?? ''}`, rotulo: 'Planilha orçamentária', apoio: 'ajustar quantidades e preços', off: !detalhe.orcamento },
              { to: '/app/scm', rotulo: 'Suprimentos', apoio: 'pedidos que formam o comprometido' },
              { to: '/app/sil', rotulo: 'Estoque & Logística', apoio: 'consumo por obra e etapa que forma o aplicado' },
              { to: '/app/erp', rotulo: 'ERP / Financeiro', apoio: 'contas a pagar que formam o realizado' },
              { to: `/app/obras/${detalhe.obra}`, rotulo: 'Ficha da obra', apoio: 'etapas e avanço físico' },
            ].map(l => l.off ? null : (
              <Link key={l.rotulo} to={l.to} style={{ textDecoration: 'none' }}>
                <Card className="orc-lift" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px' }}>
                  <Layers size={15} style={{ color: 'var(--accent-ink)' }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>{l.rotulo}</div>
                    <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{l.apoio}</div>
                  </div>
                  <ExternalLink size={13} style={{ color: 'var(--ink-3)' }} />
                </Card>
              </Link>
            ))}
          </div>
        </Drawer>
      )}
    </PaginaShell>
  )
}
