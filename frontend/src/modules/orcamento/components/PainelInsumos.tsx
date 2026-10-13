import { useState } from 'react'
import { Download, Info as InfoIcon, ShoppingCart } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Aviso, Btn, Card, CAPS, Empty, Kpi, Loading, mono, Pill, SectHead, Seletor } from '../ui'
import { brl, CLASSE_KIND, num, pct } from '../lib'
import { Pareto } from './graficos'
import { baixarExportacao } from '../api/orcamentoApi'
import { useCurvaAbcInsumos, useGerarDemandaDoOrcamento, useRelacaoInsumos } from '../hooks'
import { useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/apiClient'
import { orcKeys } from '../api/queryKeys'

type Visao = 'relacao' | 'abc'

const CATEGORIAS = [
  { valor: '', rotulo: 'Todas' },
  { valor: 'material', rotulo: 'Material' },
  { valor: 'mao_de_obra', rotulo: 'Mão de obra' },
  { valor: 'equipamento', rotulo: 'Equipamento' },
  // ORC.9 — EPI, exame, alimentação e transporte deixaram de se esconder dentro
  // de "material": eles acompanham a hora de mão de obra e não levam encargo.
  { valor: 'encargos_complementares', rotulo: 'Enc. complementares' },
]

/** O orçamento visto **por insumo**, que é a dimensão que a planilha não mostra.
 *
 *  A curva ABC de serviços diz onde negociar *escopo*; esta diz onde negociar
 *  *preço*. O aço diluído em nove serviços nunca aparece como item A por lá, e é
 *  item A da obra. A relação, do lado, é literalmente a lista de compra — e o
 *  botão que a leva ao SCM fecha o primeiro elo do laço orçado→comprometido. */
export default function PainelInsumos({ orcamentoId }: { orcamentoId: number }) {
  const { hasPermission } = useAuth()
  const [visao, setVisao] = useState<Visao>('relacao')
  const [categoria, setCategoria] = useState('')
  const [recado, setRecado] = useState('')

  const { data: relacao, isLoading: carregandoRelacao } = useRelacaoInsumos(
    orcamentoId, categoria || undefined,
  )
  const { data: abc, isLoading: carregandoAbc } = useCurvaAbcInsumos(orcamentoId)
  const gerarDemanda = useGerarDemandaDoOrcamento()
  const qc = useQueryClient()
  const [explodindo, setExplodindo] = useState(false)

  const dados = visao === 'relacao' ? relacao : abc
  const carregando = visao === 'relacao' ? carregandoRelacao : carregandoAbc

  if (carregando) return <Loading texto="Consolidando os insumos…" />
  if (!dados) return <Empty>Escolha um orçamento.</Empty>

  const cobertura = Number(dados.cobertura_pct ?? 0)

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <Seletor
          compacto
          valor={visao}
          onChange={setVisao}
          opcoes={[
            { valor: 'relacao', rotulo: 'Relação de insumos' },
            { valor: 'abc', rotulo: 'Curva ABC de insumos' },
          ]}
        />
        {visao === 'relacao' && (
          <Seletor compacto valor={categoria} onChange={setCategoria} opcoes={CATEGORIAS.map(c => ({ valor: c.valor, rotulo: c.rotulo }))} />
        )}
        <div style={{ flex: 1 }} />
        <Btn
          onClick={() => baixarExportacao(orcamentoId, {
            peca: visao === 'relacao' ? 'relacao-insumos' : 'curva-abc-insumos',
          })}
        >
          <Download size={14} />Exportar
        </Btn>
        {visao === 'relacao' && hasPermission('scm.demanda.edit') && (
          <Btn
            variant="primary"
            title="Cria uma demanda de compra em rascunho no SCM com estas quantidades"
            onClick={async () => {
              try {
                const r = await gerarDemanda.mutateAsync({ orcamento: orcamentoId, tipo: 'material' })
                setRecado(
                  `Demanda #${r.demanda} criada em rascunho com ${r.itens} itens. ` +
                  'O comprador confere e corta o que já tem em estoque antes de abrir.',
                )
              } catch (e) {
                const detalhe = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
                setRecado(detalhe ?? 'Não consegui gerar a demanda.')
              }
            }}
          >
            <ShoppingCart size={14} />Gerar demanda de compra
          </Btn>
        )}
      </div>

      {recado && <Aviso tom="info">{recado}</Aviso>}

      {/* A cobertura dita curta, com o gesto ao lado — e não um parágrafo que
          manda a pessoa a outro lugar. Abrir as composições que faltam é aqui
          mesmo, sem mexer em preço (achado do dono, 10/10/2026). */}
      {cobertura < 100 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', fontSize: 12.5, color: 'var(--ink-3)' }}>
          <span>
            {dados.linhas_explodidas} de {dados.linhas_analiticas} linhas entram na lista ({pct(dados.cobertura_pct)} do custo).
          </span>
          {hasPermission('orcamento.item.edit') && (
            <Btn
              disabled={explodindo}
              onClick={async () => {
                setExplodindo(true)
                try {
                  const r = (await apiClient.post<{ explodidas: number; sem_composicao: number }>(
                    `orcamento/orcamentos/${orcamentoId}/explodir-pendentes/`,
                  )).data
                  await qc.invalidateQueries({ queryKey: orcKeys.all })
                  setRecado(r.sem_composicao > 0
                    ? `${r.explodidas} linhas abertas; ${r.sem_composicao} não têm composição no catálogo.`
                    : `${r.explodidas} linhas abertas.`)
                } catch {
                  setRecado('Não consegui abrir as composições.')
                } finally {
                  setExplodindo(false)
                }
              }}
            >
              {explodindo ? 'Abrindo…' : 'Abrir as que faltam'}
            </Btn>
          )}
        </div>
      )}

      {visao === 'abc' && abc && (
        <Card>
          <SectHead>Onde está o dinheiro, por insumo</SectHead>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
            {(['A', 'B', 'C'] as const).map(classe => (
              <Kpi
                key={classe}
                rotulo={`Classe ${classe}`}
                valor={brl(abc.resumo[classe]?.valor ?? '0')}
                apoio={`${abc.resumo[classe]?.itens ?? 0} insumos · ${pct(abc.resumo[classe]?.pct ?? '0')}`}
              />
            ))}
          </div>
          <Pareto
            itens={abc.itens.slice(0, 20).map(i => ({
              rotulo: i.descricao,
              valor: Number(i.valor),
              acumuladoPct: Number(i.pct_acumulado),
              classe: i.classe,
            }))}
          />
        </Card>
      )}

      <Card pad={false}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr style={{ color: 'var(--ink-3)', textAlign: 'left' }}>
                {visao === 'abc' && <th style={{ padding: '8px 10px', width: 54 }}>Classe</th>}
                <th style={{ padding: '8px 10px', width: 100 }}>Código</th>
                <th style={{ padding: '8px 10px' }}>Insumo</th>
                <th style={{ padding: '8px 10px', width: 54 }}>Und</th>
                <th style={{ padding: '8px 10px', width: 110 }}>Natureza</th>
                <th style={{ padding: '8px 10px', textAlign: 'right', width: 120 }}>Quantidade</th>
                <th style={{ padding: '8px 10px', textAlign: 'right', width: 110 }}>Custo unit.</th>
                <th style={{ padding: '8px 10px', textAlign: 'right', width: 130 }}>Valor</th>
                <th style={{ padding: '8px 10px', textAlign: 'right', width: 70 }}>%</th>
                <th style={{ padding: '8px 10px', textAlign: 'right', width: 70 }} title="Em quantos serviços este insumo aparece">
                  Serv.
                </th>
              </tr>
            </thead>
            <tbody>
              {dados.itens.map((linha, indice) => (
                <tr key={`${linha.item ?? linha.descricao}-${indice}`} style={{ borderTop: '1px solid var(--line)' }}>
                  {visao === 'abc' && (
                    <td style={{ padding: '6px 10px' }}>
                      <Pill kind={CLASSE_KIND[(linha as { classe: 'A' | 'B' | 'C' }).classe]}>
                        {(linha as { classe: string }).classe}
                      </Pill>
                    </td>
                  )}
                  <td style={{ ...mono, padding: '6px 10px', color: 'var(--ink-3)' }}>
                    {linha.codigo_referencia || '—'}
                  </td>
                  <td style={{ padding: '6px 10px' }}>{linha.descricao}</td>
                  <td style={{ padding: '6px 10px', color: 'var(--ink-3)' }}>{linha.unidade}</td>
                  <td style={{ padding: '6px 10px', color: 'var(--ink-3)' }}>
                    {linha.rotulo_categoria ?? linha.categoria}
                  </td>
                  <td style={{ ...mono, padding: '6px 10px', textAlign: 'right' }}>{num(linha.quantidade)}</td>
                  <td style={{ ...mono, padding: '6px 10px', textAlign: 'right' }}>{brl(linha.custo_unitario_medio)}</td>
                  <td style={{ ...mono, padding: '6px 10px', textAlign: 'right', fontWeight: 650 }}>{brl(linha.valor)}</td>
                  <td style={{ ...mono, padding: '6px 10px', textAlign: 'right', color: 'var(--ink-3)' }}>{pct(linha.pct)}</td>
                  <td style={{ ...mono, padding: '6px 10px', textAlign: 'right', color: 'var(--ink-3)' }}>{linha.servicos}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!dados.itens.length && (
          <div style={{ padding: 20 }}>
            <Empty>
              Nenhum insumo consolidado. Explodir as composições das linhas é o passo que falta —
              sem isso o orçamento sabe quanto custa cada serviço e não sabe quanto de cada material
              a obra consome.
            </Empty>
          </div>
        )}
      </Card>

      <p style={{ ...CAPS, color: 'var(--ink-3)', lineHeight: 1.6 }}>
        <InfoIcon size={12} style={{ verticalAlign: -2, marginRight: 4 }} />
        Custo unitário é o <b>médio ponderado</b> entre as ocorrências: o mesmo insumo pode ter
        entrado em duas linhas com datas-base diferentes depois de uma reprecificação parcial, e
        mostrar só o primeiro esconderia a divergência.
      </p>
    </div>
  )
}
