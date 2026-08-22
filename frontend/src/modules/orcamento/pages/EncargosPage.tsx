import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  AlertTriangle, Calculator, CheckCircle2, Download, Info as InfoIcon, Lock, Plus, Trash2,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import PaginaShell from '../components/PaginaShell'
import {
  Aviso, Btn, Card, CAPS, Empty, Field, inp, Kpi, Loading, Modal, mono, Pill, SectHead,
  Select, Seletor,
} from '../ui'
import { brl, mesBR, paraDecimal, pct } from '../lib'
import {
  useAplicarReajuste, useAtualizarRubrica, useCriarFormulaReajuste, useCriarParcelaReajuste,
  useCriarQuadroEncargos, useFormulasReajuste, useIndices, useOrcamentos, usePreviaReajuste,
  useQuadroEncargos, useQuadrosEncargos, useRemoverParcelaReajuste, useRemoverQuadroEncargos,
} from '../hooks'
import { baixarExportacao } from '../api/orcamentoApi'
import type { QuadroEncargos, TipoMaoDeObra } from '../types'

type Aba = 'encargos' | 'reajuste'

/** A página onde o **preço** ganha parâmetro: encargos sobre a folha e correção
 *  contratual. As duas peças moram juntas porque respondem à mesma pergunta do
 *  analista — "de onde veio esse percentual?" — e porque nenhuma delas mexe em
 *  quantidade, que é assunto da grade. */
export default function EncargosPage() {
  const { hasPermission } = useAuth()
  const [params, setParams] = useSearchParams()
  const orcamentoId = params.get('orcamento') ? Number(params.get('orcamento')) : undefined
  const [aba, setAba] = useState<Aba>('encargos')
  const [recado, setRecado] = useState('')

  const { data: lista } = useOrcamentos({ page_size: 200, ordering: '-versao' })
  const orcamentos = useMemo(() => lista?.results ?? [], [lista])
  const orcamento = orcamentos.find(o => o.orcamento_id === orcamentoId)
  const podeEditar = hasPermission('orcamento.orcamento.edit') && !!orcamento?.editavel

  useEffect(() => {
    if (!recado) return
    const t = setTimeout(() => setRecado(''), 4000)
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
      <Select value={orcamentoId ?? ''} onChange={e => selecionar(e.target.value ? Number(e.target.value) : '')}>
        <option value="">Escolha o orçamento…</option>
        {orcamentos.map(o => (
          <option key={o.orcamento_id} value={o.orcamento_id}>
            {o.descricao} · v{o.versao} ({o.status})
          </option>
        ))}
      </Select>
      <Seletor
        compacto
        valor={aba}
        onChange={setAba}
        opcoes={[
          { valor: 'encargos', rotulo: 'Encargos sociais' },
          { valor: 'reajuste', rotulo: 'Reajuste contratual' },
        ]}
      />
    </>
  )

  return (
    <PaginaShell
      pagina="encargos"
      seletor={seletor}
      acoes={orcamentoId ? (
        <Btn
          onClick={() => baixarExportacao(orcamentoId, {
            peca: aba === 'encargos' ? 'encargos' : 'composicao-bdi',
          })}
          title="Baixar a peça em XLSX — é o anexo que acompanha a planilha na proposta"
        >
          <Download size={14} />{aba === 'encargos' ? 'Quadro de encargos' : 'Composição do BDI'}
        </Btn>
      ) : undefined}
    >
      <div style={{ padding: '18px 20px 30px', display: 'grid', gap: 14 }}>
        {recado && <Aviso tom="info">{recado}</Aviso>}

        {!orcamentoId && (
          <Empty>
            Escolha um orçamento acima. Encargos e reajuste são parâmetros <b>daquela</b> planilha —
            o quadro de uma obra em Sergipe não serve para uma em São Paulo, e a fórmula de reajuste
            é cláusula do contrato específico.
          </Empty>
        )}

        {orcamentoId && aba === 'encargos' && (
          <PainelEncargos
            orcamentoId={orcamentoId}
            podeEditar={podeEditar}
            aoAvisar={setRecado}
          />
        )}

        {orcamentoId && aba === 'reajuste' && (
          <PainelReajuste
            orcamentoId={orcamentoId}
            podeRevisar={hasPermission('orcamento.orcamento.revisar')}
            aoAvisar={setRecado}
          />
        )}
      </div>
    </PaginaShell>
  )
}

// ---------------------------------------------------------------------------
// Encargos
// ---------------------------------------------------------------------------

function PainelEncargos({ orcamentoId, podeEditar, aoAvisar }: {
  orcamentoId: number
  podeEditar: boolean
  aoAvisar: (t: string) => void
}) {
  const { data: quadros, isLoading } = useQuadrosEncargos(orcamentoId)
  const [selecionado, setSelecionado] = useState<number | undefined>(undefined)
  const criar = useCriarQuadroEncargos()
  const remover = useRemoverQuadroEncargos()

  const atual = selecionado ?? quadros?.[0]?.encargos_id
  const { data: quadro } = useQuadroEncargos(atual)

  const temHorista = quadros?.some(q => q.tipo_mao_de_obra === 'horista')
  const temMensalista = quadros?.some(q => q.tipo_mao_de_obra === 'mensalista')

  const criarDoModelo = async (tipo: TipoMaoDeObra) => {
    try {
      const novo = await criar.mutateAsync({ orcamento: orcamentoId, tipo_mao_de_obra: tipo })
      setSelecionado(novo.encargos_id)
      aoAvisar(
        `Quadro ${tipo} criado a partir do modelo. As alíquotas do grupo A são lei; ` +
        'as dos grupos B e C são valores de partida — confira com a publicação vigente.',
      )
    } catch { aoAvisar('Não consegui criar o quadro.') }
  }

  if (isLoading) return <Loading texto="Carregando os quadros…" />

  if (!quadros?.length) {
    return (
      <Card>
        <SectHead>Nenhum quadro de encargos</SectHead>
        <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6, margin: '0 0 12px' }}>
          Este orçamento usa o percentual digitado no cabeçalho. Isso calcula certo e{' '}
          <b>reprova em análise de proposta</b>: o analista não pergunta quanto, pergunta de onde —
          grupo A (obrigações sobre a folha), B (encargos que recebem a incidência de A),
          C (indenizatórios) e D (as reincidências).
        </p>
        {podeEditar ? (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Btn variant="primary" onClick={() => criarDoModelo('horista')}>
              <Plus size={14} />Quadro do horista
            </Btn>
            <Btn onClick={() => criarDoModelo('mensalista')}>
              <Plus size={14} />Quadro do mensalista
            </Btn>
          </div>
        ) : (
          <Pill kind="slate"><Lock size={11} />Sem permissão de edição</Pill>
        )}
      </Card>
    )
  }

  return (
    <>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        {quadros.map(q => (
          <Btn
            key={q.encargos_id}
            variant={q.encargos_id === atual ? 'primary' : 'ghost'}
            onClick={() => setSelecionado(q.encargos_id)}
          >
            {q.tipo_nome}
            <span style={{ ...mono, opacity: 0.85 }}>{pct(q.percentual_calculado)}</span>
            {q.padrao && <Pill kind="good">padrão</Pill>}
          </Btn>
        ))}
        {podeEditar && !temHorista && (
          <Btn onClick={() => criarDoModelo('horista')}><Plus size={14} />Horista</Btn>
        )}
        {podeEditar && !temMensalista && (
          <Btn onClick={() => criarDoModelo('mensalista')}><Plus size={14} />Mensalista</Btn>
        )}
      </div>

      {quadro && (
        <QuadroDetalhe
          quadro={quadro}
          podeEditar={podeEditar}
          aoRemover={async () => {
            if (!window.confirm('Remover este quadro? O percentual do cabeçalho fica como está.')) return
            await remover.mutateAsync(quadro.encargos)
            setSelecionado(undefined)
            aoAvisar('Quadro removido.')
          }}
        />
      )}
    </>
  )
}

function QuadroDetalhe({ quadro, podeEditar, aoRemover }: {
  quadro: QuadroEncargos
  podeEditar: boolean
  aoRemover: () => void
}) {
  const atualizar = useAtualizarRubrica()
  const [editando, setEditando] = useState<{ id: number; valor: string } | null>(null)

  const salvar = async () => {
    if (!editando) return
    await atualizar.mutateAsync({
      id: editando.id, payload: { percentual: paraDecimal(editando.valor) },
    })
    setEditando(null)
  }

  return (
    <Card>
      <SectHead
        right={
          podeEditar ? (
            <Btn tam="sm" onClick={aoRemover}><Trash2 size={13} />Remover quadro</Btn>
          ) : undefined
        }
      >
        {quadro.nome}
      </SectHead>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <Kpi rotulo="Grupo A" valor={pct(quadro.grupos.find(g => g.grupo === 'A')?.subtotal ?? '0')} />
        <Kpi rotulo="Grupo B" valor={pct(quadro.grupos.find(g => g.grupo === 'B')?.subtotal ?? '0')} />
        <Kpi rotulo="Grupo C" valor={pct(quadro.grupos.find(g => g.grupo === 'C')?.subtotal ?? '0')} />
        <Kpi rotulo="Grupo D" valor={pct(quadro.grupos.find(g => g.grupo === 'D')?.subtotal ?? '0')} apoio="reincidências" />
        <Kpi rotulo="Total" valor={pct(quadro.total)} tom="accent" apoio="A + B + C + D" />
      </div>

      {quadro.regime === 'desonerado' && (
        <Aviso tom="info">
          Regime <b>desonerado</b>: a contribuição patronal de 20% não está na folha — ela virou CPRB
          sobre a receita e por isso vive na composição do <b>BDI</b>, não aqui. A rubrica A1 está
          ausente de propósito; zerá-la sugeriria uma contribuição apurada em zero.
        </Aviso>
      )}

      <div style={{ display: 'grid', gap: 14, marginTop: 12 }}>
        {quadro.grupos.map(grupo => (
          <div key={grupo.grupo}>
            <div style={{ ...CAPS, marginBottom: 6 }}>{grupo.rotulo}</div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr style={{ color: 'var(--ink-3)', textAlign: 'left' }}>
                  <th style={{ padding: '4px 6px', width: 60 }}>Cód.</th>
                  <th style={{ padding: '4px 6px' }}>Rubrica</th>
                  <th style={{ padding: '4px 6px', textAlign: 'right', width: 110 }}>Alíquota</th>
                  <th style={{ padding: '4px 6px', width: 260 }}>Cálculo</th>
                </tr>
              </thead>
              <tbody>
                {grupo.rubricas.map(r => (
                  <tr key={r.rubrica} style={{ borderTop: '1px solid var(--line)' }}>
                    <td style={{ ...mono, padding: '5px 6px', color: 'var(--ink-3)' }}>{r.codigo}</td>
                    <td style={{ padding: '5px 6px' }}>{r.descricao}</td>
                    <td style={{ padding: '5px 6px', textAlign: 'right' }}>
                      {editando?.id === r.rubrica ? (
                        <input
                          autoFocus
                          style={{ ...inp, ...mono, width: 88, textAlign: 'right' }}
                          value={editando.valor}
                          onChange={e => setEditando({ id: r.rubrica, valor: e.target.value })}
                          onBlur={salvar}
                          onKeyDown={e => {
                            if (e.key === 'Enter') salvar()
                            if (e.key === 'Escape') setEditando(null)
                          }}
                        />
                      ) : (
                        <button
                          disabled={!podeEditar || r.derivada}
                          onClick={() => setEditando({ id: r.rubrica, valor: r.percentual })}
                          title={r.derivada
                            ? 'Derivada — sai da conta ao lado, não da digitação'
                            : 'Clique para editar'}
                          style={{
                            ...mono, border: 'none', background: 'transparent', fontSize: 12.5,
                            color: r.derivada ? 'var(--ink-3)' : 'var(--ink)',
                            cursor: podeEditar && !r.derivada ? 'pointer' : 'default',
                          }}
                        >
                          {pct(r.percentual)}
                          {r.derivada && <Lock size={10} style={{ marginLeft: 4, opacity: 0.7 }} />}
                        </button>
                      )}
                    </td>
                    <td style={{ ...mono, padding: '5px 6px', fontSize: 11.5, color: 'var(--ink-3)' }}>
                      {r.conta}
                    </td>
                  </tr>
                ))}
                <tr style={{ borderTop: '1px solid var(--line-2)', fontWeight: 700 }}>
                  <td />
                  <td style={{ padding: '6px' }}>Subtotal {grupo.grupo}</td>
                  <td style={{ ...mono, padding: '6px', textAlign: 'right' }}>{pct(grupo.subtotal)}</td>
                  <td />
                </tr>
              </tbody>
            </table>
          </div>
        ))}
      </div>

      <p style={{ fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.6, marginTop: 14 }}>
        <InfoIcon size={12} style={{ verticalAlign: -2, marginRight: 4 }} />
        O grupo D é <b>derivado</b> e por isso vem bloqueado: A×B/100 e FGTS×aviso prévio/100. Digitá-lo
        à mão fecha uma conta plausível e errada, e o erro não aparece em lugar nenhum. As alíquotas
        do grupo A são legais; as dos grupos B e C dependem da publicação, da UF e do acordo coletivo —
        confira-as antes de entregar a proposta.
      </p>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Reajuste
// ---------------------------------------------------------------------------

function PainelReajuste({ orcamentoId, podeRevisar, aoAvisar }: {
  orcamentoId: number
  podeRevisar: boolean
  aoAvisar: (t: string) => void
}) {
  const { data: formulas, isLoading } = useFormulasReajuste(orcamentoId)
  const { data: indices } = useIndices()
  const [competencia, setCompetencia] = useState('')
  const [novaParcela, setNovaParcela] = useState(false)
  const [confirmando, setConfirmando] = useState(false)

  const formula = formulas?.[0]
  const { data: previa, error: erroPrevia } = usePreviaReajuste(formula?.formula_id, competencia)
  const criarFormula = useCriarFormulaReajuste()
  const criarParcela = useCriarParcelaReajuste()
  const removerParcela = useRemoverParcelaReajuste()
  const aplicar = useAplicarReajuste()

  if (isLoading) return <Loading texto="Carregando a fórmula…" />

  if (!formula) {
    return (
      <Card>
        <SectHead>Nenhuma fórmula de reajuste</SectHead>
        <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6, margin: '0 0 12px' }}>
          Reajustar não é reprecificar. A <b>reprecificação</b> troca o preço unitário pela cotação de
          outra publicação, item a item — muda a composição do custo. O <b>reajuste</b> multiplica tudo
          por um fator contratual, sem tocar em composição, e é ato de contrato.
        </p>
        <Btn
          variant="primary"
          onClick={async () => {
            await criarFormula.mutateAsync({
              orcamento: orcamentoId,
              nome: 'Reajuste contratual',
              data_base: new Date().toISOString().slice(0, 10),
              parcela_fixa: '0',
            })
            aoAvisar('Fórmula criada. Agora monte a cesta: a soma dos pesos com a parcela fixa precisa fechar em 1.')
          }}
        >
          <Plus size={14} />Criar a fórmula
        </Btn>
      </Card>
    )
  }

  return (
    <>
      <Card>
        <SectHead
          right={
            <Pill kind={formula.fecha ? 'good' : 'danger'}>
              {formula.fecha
                ? <><CheckCircle2 size={11} />a + Σp = 1</>
                : <><AlertTriangle size={11} />a + Σp = {formula.soma_pesos}</>}
            </Pill>
          }
        >
          {formula.nome} · data-base {mesBR(formula.data_base)}
        </SectHead>

        <p style={{ ...mono, fontSize: 12.5, color: 'var(--ink-2)', margin: '0 0 12px' }}>
          R = V × [ a + Σ pᵢ × (Iᵢ,t ÷ Iᵢ,0) ]
        </p>

        {!formula.fecha && (
          <Aviso tom="danger">
            A fórmula não fecha em 1. Um peso a menos não é erro de digitação inofensivo — vira
            <b> desconto disfarçado de correção monetária</b>, e o resultado continua sendo um número
            plausível. O cálculo do fator recusa enquanto não fechar.
          </Aviso>
        )}

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, marginTop: 10 }}>
          <thead>
            <tr style={{ color: 'var(--ink-3)', textAlign: 'left' }}>
              <th style={{ padding: '4px 6px' }}>Parcela</th>
              <th style={{ padding: '4px 6px' }}>Índice</th>
              <th style={{ padding: '4px 6px', textAlign: 'right', width: 90 }}>Peso</th>
              <th style={{ width: 40 }} />
            </tr>
          </thead>
          <tbody>
            <tr style={{ borderTop: '1px solid var(--line)' }}>
              <td style={{ padding: '5px 6px' }}>Parcela não reajustável (a)</td>
              <td style={{ padding: '5px 6px', color: 'var(--ink-3)' }}>—</td>
              <td style={{ ...mono, padding: '5px 6px', textAlign: 'right' }}>{formula.parcela_fixa}</td>
              <td />
            </tr>
            {formula.parcelas.map(p => (
              <tr key={p.parcela_id} style={{ borderTop: '1px solid var(--line)' }}>
                <td style={{ padding: '5px 6px' }}>{p.rotulo || p.indice_nome}</td>
                <td style={{ ...mono, padding: '5px 6px' }}>{p.indice_codigo}</td>
                <td style={{ ...mono, padding: '5px 6px', textAlign: 'right' }}>{p.peso}</td>
                <td style={{ padding: '5px 6px' }}>
                  <Btn tam="sm" onClick={() => removerParcela.mutate(p.parcela_id)}>
                    <Trash2 size={12} />
                  </Btn>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <Btn tam="sm" style={{ marginTop: 8 }} onClick={() => setNovaParcela(true)}>
          <Plus size={13} />Acrescentar parcela
        </Btn>
      </Card>

      <Card>
        <SectHead>Prévia do reajuste</SectHead>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <Field label="Competência do reajuste" dica="O mês do aniversário do contrato.">
            <input
              type="month"
              style={inp}
              value={competencia.slice(0, 7)}
              onChange={e => setCompetencia(e.target.value ? `${e.target.value}-01` : '')}
            />
          </Field>
          {previa && (
            <>
              <Kpi rotulo="Fator" valor={previa.memoria.fator} tom="accent" />
              <Kpi rotulo="Variação" valor={pct(previa.memoria.variacao_pct)} />
              <Kpi rotulo="Total antes" valor={brl(previa.total_antes)} />
              <Kpi rotulo="Total depois" valor={brl(previa.total_depois)} tom="accent" />
              <Kpi rotulo="Δ" valor={brl(previa.delta)} />
            </>
          )}
        </div>

        {erroPrevia && (
          <Aviso tom="amber">
            {(erroPrevia as { response?: { data?: { detail?: string } } })?.response?.data?.detail
              ?? 'Não consegui calcular o fator para essa competência.'}
          </Aviso>
        )}

        {previa && (
          <>
            <div style={{ ...CAPS, margin: '14px 0 6px' }}>Memória do fator</div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr style={{ color: 'var(--ink-3)', textAlign: 'left' }}>
                  <th style={{ padding: '4px 6px' }}>Parcela</th>
                  <th style={{ padding: '4px 6px', textAlign: 'right' }}>Peso</th>
                  <th style={{ padding: '4px 6px', textAlign: 'right' }}>I₀</th>
                  <th style={{ padding: '4px 6px', textAlign: 'right' }}>I_t</th>
                  <th style={{ padding: '4px 6px', textAlign: 'right' }}>Razão</th>
                  <th style={{ padding: '4px 6px', textAlign: 'right' }}>Contribuição</th>
                </tr>
              </thead>
              <tbody>
                {previa.memoria.parcelas.map(p => (
                  <tr key={p.parcela} style={{ borderTop: '1px solid var(--line)' }}>
                    <td style={{ padding: '5px 6px' }}>{p.rotulo} <span style={{ ...mono, color: 'var(--ink-3)' }}>{p.indice}</span></td>
                    <td style={{ ...mono, padding: '5px 6px', textAlign: 'right' }}>{p.peso}</td>
                    <td style={{ ...mono, padding: '5px 6px', textAlign: 'right' }}>{p.indice_base}</td>
                    <td style={{ ...mono, padding: '5px 6px', textAlign: 'right' }}>{p.indice_reajuste}</td>
                    <td style={{ ...mono, padding: '5px 6px', textAlign: 'right' }}>{p.razao}</td>
                    <td style={{ ...mono, padding: '5px 6px', textAlign: 'right' }}>{p.contribuicao}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {previa.exige_revisao && (
              <Aviso tom="amber">
                Este orçamento está <b>aprovado</b>. Aplicar o reajuste cria a <b>versão seguinte</b> com
                revisão do tipo reequilíbrio — a régua congelada continua congelada, porque o SIL já
                compara consumo contra ela.
              </Aviso>
            )}

            <div style={{ marginTop: 12 }}>
              <Btn
                variant="primary"
                disabled={!podeRevisar}
                onClick={() => setConfirmando(true)}
                title={podeRevisar ? undefined : 'Requer orcamento.orcamento.revisar'}
              >
                <Calculator size={14} />Aplicar o reajuste
              </Btn>
            </div>
          </>
        )}
      </Card>

      {novaParcela && (
        <Modal titulo="Nova parcela da cesta" onClose={() => setNovaParcela(false)}>
          <form
            onSubmit={async e => {
              e.preventDefault()
              const dados = new FormData(e.currentTarget)
              await criarParcela.mutateAsync({
                formula: formula.formula_id,
                indice: Number(dados.get('indice')),
                peso: paraDecimal(String(dados.get('peso') ?? '0')),
                rotulo: String(dados.get('rotulo') ?? ''),
              })
              setNovaParcela(false)
            }}
            style={{ display: 'grid', gap: 10 }}
          >
            <Field label="Índice">
              <Select name="indice" required>
                {indices?.map(i => (
                  <option key={i.indice_id} value={i.indice_id}>{i.codigo} — {i.nome}</option>
                ))}
              </Select>
            </Field>
            <Field label="Peso (p)" dica="Fração de 0 a 1. A soma com a parcela fixa precisa fechar em 1.">
              <input name="peso" style={{ ...inp, ...mono }} defaultValue="0,00" />
            </Field>
            <Field label="Rótulo" dica="Como o edital nomeia a parcela: 'Mão de obra', 'Materiais'.">
              <input name="rotulo" style={inp} />
            </Field>
            <Btn variant="primary" type="submit">Acrescentar</Btn>
          </form>
        </Modal>
      )}

      {confirmando && previa && (
        <Modal titulo="Aplicar o reajuste" onClose={() => setConfirmando(false)}>
          <p style={{ fontSize: 13, lineHeight: 1.6, color: 'var(--ink-2)' }}>
            Fator <b style={mono}>{previa.memoria.fator}</b> sobre {previa.itens.length} linhas.
            O total vai de <b>{brl(previa.total_antes)}</b> para <b>{brl(previa.total_depois)}</b>.
            {previa.exige_revisao && ' Isto criará a versão seguinte do orçamento.'}
          </p>
          <p style={{ fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.6 }}>
            A procedência do preço <b>não muda</b>: a linha continua declarando a fonte e a data-base
            originais, corrigidas por contrato. Dizer que virou preço de outra publicação seria rastro falso.
          </p>
          <Btn
            variant="primary"
            onClick={async () => {
              const r = await aplicar.mutateAsync({ formula: formula.formula_id, competencia })
              setConfirmando(false)
              aoAvisar(
                r.gerou_revisao
                  ? `Reajuste aplicado na versão ${r.versao}, com revisão registrada.`
                  : `Reajuste aplicado em ${r.linhas_reajustadas} linhas.`,
              )
            }}
          >
            Confirmar
          </Btn>
        </Modal>
      )}
    </>
  )
}
