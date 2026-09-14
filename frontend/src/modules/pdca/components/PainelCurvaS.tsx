import { useId, useMemo, useState } from 'react'
import { ExternalLink, Lock } from 'lucide-react'
import { Card, KpiTile, Loading, SectionHead } from '@/components/malha'
// A paleta dos gráficos é do sistema, não do Orçamento: aqueles hexadecimais
// passaram por validação de luminosidade, croma e daltonismo nos dois temas, e
// forká-los aqui produziria duas curvas S com cores diferentes na mesma
// plataforma. Quando a Malha tiver a camada de gráficos, os dois vêm de lá.
import { COR_SERIE, GraficoEstilos } from '@/modules/orcamento/components/graficos'
import { useCurvaS } from '../hooks'
import { estatisticasDoPlano, hojeIso } from '../lib'
import type {
  Atividade, AvancoDoCronograma, CoberturaOrcamento, CurvaS, Granularidade, PontoCurvaS,
  Precedencia,
} from '../types'

interface Props {
  cronogramaId: number
  atividades: Atividade[]
  precedencias: Precedencia[]
  cobertura: CoberturaOrcamento
  avanco: AvancoDoCronograma
  podeVerOrcamento: boolean
  obra: number
}

const GRANULARIDADES: { chave: Granularidade; rotulo: string }[] = [
  { chave: 'dia', rotulo: 'Dia' },
  { chave: 'semana', rotulo: 'Semana' },
  { chave: 'mes', rotulo: 'Mês' },
]

/**
 * A leitura de desempenho — curva S **prevista × realizada**, o retrato da rede
 * e a cobertura de custo. É o que se olha na reunião de obra, e por isso todo
 * número aqui carrega o denominador: uma curva desenhada sobre 12 das 300
 * atividades é bonita e mente.
 *
 * **A curva vem do servidor** (PDCA.2). Até a fatia anterior ela era calculada
 * aqui, distribuindo o peso linearmente nos dias corridos da barra — aproximação
 * declarada, porque o calendário mora lá. Com a realizada na mesma tela isso
 * deixou de servir: o desvio entre as duas carregaria o erro de fim de semana da
 * aproximação. Agora o previsto é distribuído nos **dias úteis do calendário de
 * cada atividade**, que é a régua com que o CPM produziu as datas.
 */
export default function PainelCurvaS({
  cronogramaId, atividades, precedencias, cobertura, avanco, podeVerOrcamento, obra,
}: Props) {
  const [granularidade, setGranularidade] = useState<Granularidade>('semana')
  const [moeda, setMoeda] = useState<'fisica' | 'financeira'>('fisica')
  const curva = useCurvaS(cronogramaId, granularidade)
  const stats = useMemo(() => estatisticasDoPlano(atividades, precedencias), [atividades, precedencias])
  const dados = curva.data

  const temFinanceira = !!dados?.base_financeira
  const moedaEfetiva = temFinanceira ? moeda : 'fisica'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18, padding: '4px 2px 20px' }}>
      <GraficoEstilos />

      <Kpis avanco={avanco} curva={dados} />

      <Card style={{ padding: 16 }}>
        <SectionHead
          sub={
            dados && dados.granularidade !== dados.granularidade_pedida
              ? `Agrupado por ${rotuloDe(dados.granularidade).toLowerCase()} — o período pedido geraria mais pontos do que o gráfico comporta`
              : 'Peso acumulado ao longo do tempo: o que estava previsto e o que foi apontado'
          }
          right={
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {temFinanceira && (
                <Alternador
                  opcoes={[
                    { chave: 'fisica', rotulo: 'Físico' },
                    { chave: 'financeira', rotulo: 'R$' },
                  ]}
                  valor={moeda}
                  onMudar={v => setMoeda(v as 'fisica' | 'financeira')}
                />
              )}
              <Alternador
                opcoes={GRANULARIDADES.map(g => ({ chave: g.chave, rotulo: g.rotulo }))}
                valor={granularidade}
                onMudar={v => setGranularidade(v as Granularidade)}
              />
            </div>
          }
        >
          Curva S
        </SectionHead>

        {curva.isLoading && !dados ? (
          <Loading o="a curva" />
        ) : !dados || dados.pontos.length === 0 ? (
          <p style={{ fontSize: 12.5, color: 'var(--ink-3)', margin: '10px 0 0', lineHeight: 1.6 }}>
            {dados?.motivo_vazio || 'Nada a acumular ainda.'}
          </p>
        ) : (
          <>
            <Curva pontos={dados.pontos} moeda={moedaEfetiva} base={dados.base_financeira} />
            <Legenda dados={dados} moeda={moedaEfetiva} />
          </>
        )}
      </Card>

      <section style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(148px, 1fr))' }}>
        <KpiTile label="Atividades" valor={String(stats.atividades)} base={stats.folhas + ' folhas'} />
        <KpiTile label="No caminho crítico" valor={String(stats.criticas)} base={stats.marcos + ' marcos'} />
        <KpiTile
          label="Duração"
          valor={stats.duracaoDiasCorridos == null ? '—' : stats.duracaoDiasCorridos + ' d'}
          base="corridos, do início ao fim"
        />
        <KpiTile
          label="Folga média"
          valor={stats.folgaMedia == null ? 'sem cálculo' : stats.folgaMedia + ' d'}
          base="das folhas não críticas"
        />
        <KpiTile
          label="Densidade da rede"
          valor={stats.densidade == null ? '—' : String(stats.densidade)}
          base="ligações por folha"
        />
        <KpiTile
          label="Folhas sem ligação"
          valor={String(stats.folhasSemLigacao)}
          base={stats.folhasSemLigacao ? 'flutuam no plano' : 'a rede está fechada'}
        />
      </section>

      <Cobertura cobertura={cobertura} podeVer={podeVerOrcamento} obra={obra} />
    </div>
  )
}

function rotuloDe(g: Granularidade): string {
  return GRANULARIDADES.find(x => x.chave === g)?.rotulo ?? g
}

/**
 * Os quatro números que resumem a leitura — e o **desvio**, que é o único que
 * responde à pergunta da reunião. Ele compara o realizado com o previsto **na
 * mesma data**, e não com o previsto total: adiantado de 3 pontos no meio da
 * obra e 3 pontos no fim são situações opostas.
 */
function Kpis({ avanco, curva }: { avanco: AvancoDoCronograma; curva?: CurvaS }) {
  const hoje = hojeIso()
  const ateHoje = curva?.pontos.filter(p => p.iso <= hoje) ?? []
  const ultimo = ateHoje[ateHoje.length - 1]
  const realizado = avanco.fisico
  const previstoHoje = ultimo?.previsto ?? null
  const desvio = realizado != null && previstoHoje != null ? realizado - previstoHoje : null

  return (
    <section style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(168px, 1fr))' }}>
      <KpiTile
        label="Avanço físico"
        valor={realizado == null ? 'sem apuração' : realizado.toFixed(1) + '%'}
        base={
          avanco.folhas_sem_peso
            ? `${avanco.folhas - avanco.folhas_sem_peso} de ${avanco.folhas} folhas ponderam`
            : `sobre ${avanco.folhas} folhas`
        }
      />
      <KpiTile
        label="Previsto até hoje"
        valor={previstoHoje == null ? '—' : previstoHoje.toFixed(1) + '%'}
        base="pelo plano vigente"
      />
      <KpiTile
        label="Desvio"
        valor={desvio == null ? '—' : (desvio >= 0 ? '+' : '') + desvio.toFixed(1) + ' pp'}
        base={desvio == null ? 'sem base de comparação' : desvio >= 0 ? 'adiantado' : 'atrasado'}
      />
      <KpiTile
        label="Realizado em R$"
        valor={
          avanco.financeiro
            ? Number(avanco.financeiro.realizado).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
            : 'sem vínculo'
        }
        base={
          avanco.financeiro
            ? `de ${Number(avanco.financeiro.orcado).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })} orçados`
            : 'nenhuma folha vinculada ao orçamento'
        }
        origem={avanco.financeiro ? 'Orçamento' : undefined}
      />
    </section>
  )
}

function Legenda({ dados, moeda }: { dados: CurvaS; moeda: 'fisica' | 'financeira' }) {
  return (
    <div style={{ marginTop: 10, fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.7 }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginRight: 14 }}>
        <span style={{ width: 14, height: 3, background: COR_SERIE[0], borderRadius: 2 }} /> Previsto
      </span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginRight: 14 }}>
        <span style={{ width: 14, height: 3, background: COR_SERIE[2], borderRadius: 2 }} /> Realizado
      </span>
      {dados.ultimo_apontamento ? (
        <>A linha do realizado termina no último apontamento ({dados.ultimo_apontamento.split('-').reverse().join('/')}) — continuar reta até o fim do plano diria "em dia" onde ninguém apontou.</>
      ) : (
        <>Nada apontado ainda: a linha do realizado aparece com o primeiro apontamento de avanço.</>
      )}
      {dados.folhas_sem_peso > 0 && (
        <> Fora da conta: <strong>{dados.folhas_sem_peso}</strong> {dados.folhas_sem_peso === 1 ? 'folha sem peso' : 'folhas sem peso'}.</>
      )}
      {moeda === 'financeira' && (
        <> A curva em R$ cobre só as folhas vinculadas ao orçamento.</>
      )}
    </div>
  )
}

/** As duas curvas em SVG próprio: viewBox normalizado, barra do período atrás e
 *  as linhas acumuladas na frente. A dica segue o ponteiro porque ler percentual
 *  acumulado sem saber o período é ler metade da informação. */
function Curva({ pontos, moeda, base }: {
  pontos: PontoCurvaS[]
  moeda: 'fisica' | 'financeira'
  base: string | null
}) {
  const id = useId()
  const [foco, setFoco] = useState<number | null>(null)
  const passo = pontos.length > 1 ? 100 / (pontos.length - 1) : 100

  // Em R$ o eixo continua sendo percentual: o que muda é a **base** — o
  // acumulado sobre o orçado vinculado. Desenhar reais no eixo Y obrigaria a
  // uma escala de milhões que esconde o que o gráfico existe para mostrar (o
  // ritmo), e o valor absoluto está no KPI e na dica.
  const totalReais = Number(base ?? 0)
  const valor = (p: PontoCurvaS, serie: 'previsto' | 'realizado'): number | null => {
    if (moeda === 'fisica') return serie === 'previsto' ? p.previsto : p.realizado
    const bruto = serie === 'previsto' ? p.previsto_reais : p.realizado_reais
    if (bruto == null || totalReais <= 0) return null
    return (Number(bruto) / totalReais) * 100
  }
  const periodo = (p: PontoCurvaS) => p.previsto_periodo
  const maiorPeriodo = Math.max(...pontos.map(periodo), 1)

  const caminho = (serie: 'previsto' | 'realizado') => {
    const partes: string[] = []
    pontos.forEach((p, n) => {
      const v = valor(p, serie)
      if (v == null) return
      partes.push((partes.length === 0 ? 'M' : 'L') + n * passo + ',' + (100 - v))
    })
    return partes.join(' ')
  }

  const linhaPrevisto = caminho('previsto')
  const linhaRealizado = caminho('realizado')
  const area = linhaPrevisto ? linhaPrevisto + ' L100,100 L0,100 Z' : ''
  const p = foco == null ? null : pontos[foco]

  return (
    <div>
      <div style={{ position: 'relative', height: 250 }}>
        <svg
          viewBox="0 0 100 100" preserveAspectRatio="none" aria-labelledby={id}
          style={{ width: '100%', height: '100%', display: 'block' }}
          onMouseLeave={() => setFoco(null)}
          onMouseMove={e => {
            const caixa = e.currentTarget.getBoundingClientRect()
            const razao = (e.clientX - caixa.left) / caixa.width
            setFoco(Math.max(0, Math.min(pontos.length - 1, Math.round(razao * (pontos.length - 1)))))
          }}
        >
          <title id={id}>Curva S: previsto e realizado acumulados ao longo do tempo</title>
          {[0, 25, 50, 75, 100].map(y => (
            <line key={y} x1="0" y1={100 - y} x2="100" y2={100 - y} stroke="var(--line)" strokeWidth="0.3" vectorEffect="non-scaling-stroke" />
          ))}
          {pontos.map((ponto, n) => (
            <rect
              key={ponto.iso}
              x={Math.max(n * passo - passo * 0.32, 0)} width={Math.max(passo * 0.64, 0.4)}
              y={100 - (periodo(ponto) / maiorPeriodo) * 30} height={(periodo(ponto) / maiorPeriodo) * 30}
              fill={COR_SERIE[1]} opacity={foco === n ? 0.5 : 0.2}
            />
          ))}
          {area && <path d={area} fill={COR_SERIE[0]} opacity={0.08} />}
          {linhaPrevisto && (
            <path d={linhaPrevisto} fill="none" stroke={COR_SERIE[0]} strokeWidth="2" vectorEffect="non-scaling-stroke" />
          )}
          {linhaRealizado && (
            <path d={linhaRealizado} fill="none" stroke={COR_SERIE[2]} strokeWidth="2.4" vectorEffect="non-scaling-stroke" />
          )}
          {foco != null && (
            <line x1={foco * passo} y1="0" x2={foco * passo} y2="100" stroke={COR_SERIE[0]} strokeWidth="1" strokeDasharray="3 2" vectorEffect="non-scaling-stroke" />
          )}
        </svg>

        {p && (
          <div style={{
            position: 'absolute', top: 6, right: 6, background: 'var(--surface)',
            border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', padding: '7px 11px',
            fontSize: 12, color: 'var(--ink)', pointerEvents: 'none', lineHeight: 1.6,
          }}>
            <b>{p.rotulo}</b><br />
            previsto {p.previsto.toFixed(1)}%<br />
            realizado {p.realizado == null ? '—' : p.realizado.toFixed(1) + '%'}<br />
            {moeda === 'financeira' && p.previsto_reais && (
              <span style={{ color: 'var(--ink-3)' }}>
                {Number(p.realizado_reais ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                {' de '}
                {Number(p.previsto_reais).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
              </span>
            )}
          </div>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10.5, color: 'var(--ink-3)', marginTop: 4 }}>
        <span>{pontos[0].rotulo}</span>
        <span>{pontos[pontos.length - 1].rotulo}</span>
      </div>
    </div>
  )
}

function Alternador({ opcoes, valor, onMudar }: {
  opcoes: { chave: string; rotulo: string }[]
  valor: string
  onMudar: (v: string) => void
}) {
  return (
    <div style={{ display: 'flex', gap: 2, background: 'var(--inset)', padding: 2, borderRadius: 8 }}>
      {opcoes.map(o => (
        <button
          key={o.chave} type="button" onClick={() => onMudar(o.chave)}
          style={{
            border: 'none', borderRadius: 6, padding: '3px 10px', fontSize: 11.5, cursor: 'pointer',
            background: valor === o.chave ? 'var(--surface)' : 'transparent',
            color: valor === o.chave ? 'var(--ink)' : 'var(--ink-3)',
            fontWeight: valor === o.chave ? 600 : 400,
          }}
        >{o.rotulo}</button>
      ))}
    </div>
  )
}

/**
 * A cobertura do orçamento — a integração com o módulo vizinho aparecendo na
 * tela, e não só no banco. O número que importa não é "quanto está vinculado",
 * é **quanto ficou de fora**: cobertura de 40% com um total bonito ao lado é a
 * forma mais comum de um sistema de gestão mentir sem errar uma conta.
 */
function Cobertura({ cobertura, podeVer, obra }: {
  cobertura: CoberturaOrcamento
  podeVer: boolean
  obra: number
}) {
  const { folhas, com_item_orcado: orcadas, com_peso_informado: informadas, sem_peso: semPeso } = cobertura
  const fatia = (n: number) => (folhas ? (n / folhas) * 100 : 0)

  return (
    <Card style={{ padding: 16 }}>
      <SectionHead
        sub="Quantas folhas do cronograma têm régua de custo"
        right={podeVer ? (
          <a
            href={'/app/orcamento/orcar?obra=' + obra}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--brand)' }}
          >
            Abrir o orçamento <ExternalLink size={12} />
          </a>
        ) : (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--ink-3)' }}>
            <Lock size={12} /> Orçamento não contratado
          </span>
        )}
      >
        Cobertura do orçamento
      </SectionHead>

      {folhas === 0 ? (
        <p style={{ fontSize: 12.5, color: 'var(--ink-3)', margin: 0 }}>O cronograma ainda não tem folhas.</p>
      ) : (
        <>
          <div style={{ display: 'flex', height: 12, borderRadius: 999, overflow: 'hidden', background: 'var(--inset)' }}>
            <span style={{ width: fatia(orcadas) + '%', background: 'var(--good)' }} />
            <span style={{ width: fatia(informadas) + '%', background: 'var(--accent)' }} />
            <span style={{ width: fatia(semPeso) + '%', background: 'var(--line)' }} />
          </div>

          <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginTop: 10, fontSize: 12 }}>
            <Fatia cor="var(--good)" rotulo="Vinculadas ao orçamento" valor={orcadas} total={folhas} />
            <Fatia cor="var(--accent)" rotulo="Peso informado à mão" valor={informadas} total={folhas} />
            <Fatia cor="var(--line)" rotulo="Sem peso" valor={semPeso} total={folhas} />
          </div>

          <p style={{ fontSize: 12, color: 'var(--ink-2)', margin: '12px 0 0', lineHeight: 1.6 }}>
            Valor orçado que o cronograma alcança:{' '}
            <strong>
              {Number(cobertura.valor_orcado_vinculado).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
            </strong>
            {semPeso > 0 && (
              <> — e {semPeso} {semPeso === 1 ? 'folha fica' : 'folhas ficam'} fora de qualquer ponderação de avanço.</>
            )}
          </p>
        </>
      )}
    </Card>
  )
}

function Fatia({ cor, rotulo, valor, total }: { cor: string; rotulo: string; valor: number; total: number }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--ink-2)' }}>
      <span style={{ width: 10, height: 10, borderRadius: 3, background: cor }} />
      {rotulo}: <strong>{valor}</strong>
      <span style={{ color: 'var(--ink-3)' }}>de {total}</span>
    </span>
  )
}
