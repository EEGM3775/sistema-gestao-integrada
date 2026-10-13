import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertTriangle, ArrowUpRight, TrendingUp } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import PaginaShell from '../components/PaginaShell'
import PainelInsumos from '../components/PainelInsumos'
import { BarrasHorizontais, GraficoEstilos, Pareto } from '../components/graficos'
import { Aviso, Card, CAPS, Empty, Loading, mono, Pill, SectHead, Select, Seletor } from '../ui'
import { brl, CLASSE_KIND, num, pct } from '../lib'
import { useCurvaABC, useObras, useOrcamentos, usePorCategoria } from '../hooks'

type Aba = 'abc' | 'insumos' | 'composicao'

/** **Analisar** — onde está o dinheiro do que foi **orçado**.
 *
 *  *Decisão do dono, 10/10/2026:* o Orçamento só planeja. As quatro colunas
 *  (orçado × comprometido × aplicado × realizado), a curva S do executado e o
 *  material gasto foram para o posto **Controle** do PDCA, que é execução.
 *  Aqui ficam as análises do planejado: a curva ABC dos serviços (onde negociar
 *  escopo), a relação e a ABC dos insumos (onde negociar preço — e de onde a
 *  compra nasce no Suprimentos) e a composição do custo por natureza. */
export default function AnalisarPage() {
  const { hasPermission } = useAuth()
  const [params, setParams] = useSearchParams()
  const obraParam = params.get('obra') ? Number(params.get('obra')) : undefined
  const orcamentoParam = params.get('orcamento') ? Number(params.get('orcamento')) : undefined
  const [aba, setAba] = useState<Aba>('abc')

  const { data: obras } = useObras()
  const { data: lista } = useOrcamentos({ page_size: 200, ordering: '-versao' })
  const orcamentos = useMemo(() => lista?.results ?? [], [lista])
  const daObra = useMemo(
    () => (obraParam ? orcamentos.filter(o => o.obra === obraParam) : orcamentos),
    [orcamentos, obraParam],
  )
  // Sem escolha explícita, o aprovado da obra; senão a versão mais nova.
  const orcamentoDaObra = useMemo(() => {
    if (orcamentoParam) return orcamentos.find(o => o.orcamento_id === orcamentoParam)
    if (!obraParam) return undefined
    return daObra.find(o => o.status === 'aprovado') ?? daObra[0]
  }, [orcamentos, daObra, obraParam, orcamentoParam])

  useEffect(() => {
    if (orcamentoDaObra && !obraParam) {
      const proximo = new URLSearchParams(params)
      proximo.set('obra', String(orcamentoDaObra.obra))
      setParams(proximo, { replace: true })
    }
  }, [orcamentoDaObra, obraParam, params, setParams])

  const id = orcamentoDaObra?.orcamento_id
  const { data: abc, isLoading: carregandoAbc } = useCurvaABC(aba === 'abc' ? id : undefined)
  const { data: categorias, isLoading: carregandoCat } = usePorCategoria(aba === 'composicao' ? id : undefined)

  const mudar = (chave: 'obra' | 'orcamento', valor: number | '') => {
    const proximo = new URLSearchParams(params)
    if (valor === '') proximo.delete(chave)
    else proximo.set(chave, String(valor))
    if (chave === 'obra') proximo.delete('orcamento')
    setParams(proximo, { replace: true })
  }

  const seletor = (
    <>
      <Select value={obraParam ?? ''} onChange={e => mudar('obra', e.target.value ? Number(e.target.value) : '')} style={{ maxWidth: 220 }}>
        <option value="">Selecione a obra</option>
        {obras?.map(o => <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>)}
      </Select>
      {obraParam && (
        <Select value={id ?? ''} onChange={e => mudar('orcamento', e.target.value ? Number(e.target.value) : '')} style={{ maxWidth: 240 }}>
          {daObra.map(o => <option key={o.orcamento_id} value={o.orcamento_id}>{o.descricao} · v{o.versao} · {o.status}</option>)}
        </Select>
      )}
      <Seletor
        compacto
        valor={aba}
        onChange={setAba}
        opcoes={[
          { valor: 'abc' as Aba, rotulo: 'Curva ABC', travado: !id, motivo: 'Escolha uma obra' },
          // ORC.7 — a dimensão que a planilha não mostra. A ABC de serviços diz
          // onde negociar escopo; esta diz onde negociar preço.
          { valor: 'insumos' as Aba, rotulo: 'Insumos', travado: !id, motivo: 'Escolha uma obra' },
          { valor: 'composicao' as Aba, rotulo: 'Composição do custo', travado: !id, motivo: 'Escolha uma obra' },
        ]}
      />
    </>
  )

  if (!hasPermission('orcamento.relatorio.view')) {
    return (
      <PaginaShell pagina="analisar">
        <div style={{ padding: 26 }}>
          <Empty>
            As análises do orçamento exigem a permissão <code style={{ ...mono }}>orcamento.relatorio.view</code>.
            Peça a um administrador do tenant em Papéis e Acessos.
          </Empty>
        </div>
      </PaginaShell>
    )
  }

  return (
    <PaginaShell pagina="analisar" seletor={seletor}>
      <GraficoEstilos />
      <div style={{ padding: '18px 22px 40px', overflowY: 'auto' }}>
        {obraParam && (
          <Link to={`/app/pdca/o/${obraParam}/controle?aba=custo`} style={{ textDecoration: 'none' }}>
            <Card className="orc-lift" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px', marginBottom: 14 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>Controle da execução no PDCA</div>
                <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                  orçado × comprometido × aplicado × medido × realizado, valor agregado e o material gasto desta obra
                </div>
              </div>
              <ArrowUpRight size={15} style={{ color: 'var(--ink-3)' }} />
            </Card>
          </Link>
        )}
        {!id ? (
          <Empty>Escolha a obra para analisar o orçamento dela.</Empty>
        ) : (
          <>
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

            {aba === 'insumos' && <PainelInsumos orcamentoId={id} />}

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
    </PaginaShell>
  )
}
