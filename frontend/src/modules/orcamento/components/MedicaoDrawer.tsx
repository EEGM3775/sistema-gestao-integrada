import { useState } from 'react'
import { AlertTriangle, ClipboardPaste, Info as InfoIcon, Plus, Trash2 } from 'lucide-react'
import { Aviso, Btn, CAPS, Drawer, Empty, Field, inp, Kpi, Loading, mono, Pill, SectHead } from '../ui'
import { num, paraDecimal } from '../lib'
import {
  useCriarMedicao, useMedicoesEmLote, useMemoriaQuantitativo, useRemoverMedicao,
} from '../hooks'
import type { LinhaMedicao } from '../types'

/** A memória de cálculo **da quantidade** — o que faltava do outro lado.
 *
 *  O preço da linha já abria em insumos e respondia "por que este m³ custa
 *  R$ 412,80?". A quantidade era um Decimal digitado e não respondia a nada, e
 *  numa conferência de proposta é ela que se questiona primeiro: o preço vem de
 *  tabela pública, a quantidade vem do projeto de quem orçou. */
export default function MedicaoDrawer({ itemOrcado, descricao, unidade, podeEditar, onClose }: {
  itemOrcado: number
  descricao: string
  unidade: string
  podeEditar: boolean
  onClose: () => void
}) {
  const { data: memoria, isLoading } = useMemoriaQuantitativo(itemOrcado)
  const criar = useCriarMedicao()
  const remover = useRemoverMedicao()
  const emLote = useMedicoesEmLote()
  const [colando, setColando] = useState(false)
  const [bloco, setBloco] = useState('')
  const [erro, setErro] = useState('')

  const acrescentar = async (dados: Partial<LinhaMedicao>) => {
    setErro('')
    try {
      await criar.mutateAsync({ item_orcado: itemOrcado, ...dados })
    } catch (e) {
      const detalhe = (e as { response?: { data?: { detail?: string; formula?: string } } })?.response?.data
      setErro(detalhe?.detail ?? detalhe?.formula ?? 'Não consegui gravar a parcial.')
    }
  }

  /** Colar do Excel: `descrição<TAB>n<TAB>a<TAB>b<TAB>c` por linha. É o caminho
   *  real — quem levanta quantitativo já tem a planilha aberta ao lado. */
  const colar = async () => {
    setErro('')
    const linhas = bloco.split('\n').map(l => l.trim()).filter(Boolean).map(linha => {
      const campos = linha.split(/\t|;/).map(c => c.trim())
      const [texto, n, a, b, c] = campos
      return {
        descricao: texto ?? '',
        repeticoes: paraDecimal(n || '1'),
        comprimento: a ? paraDecimal(a) : null,
        largura: b ? paraDecimal(b) : null,
        altura: c ? paraDecimal(c) : null,
      }
    })
    if (!linhas.length) return
    try {
      await emLote.mutateAsync({ item_orcado: itemOrcado, linhas })
      setColando(false)
      setBloco('')
    } catch (e) {
      const detalhe = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErro(detalhe ?? 'Não consegui gravar o bloco. Confira o formato das colunas.')
    }
  }

  return (
    <Drawer titulo={`Memória do quantitativo — ${descricao}`} onClose={onClose} largura={760}>
      {isLoading && <Loading texto="Carregando as parciais…" />}

      {memoria && (
        <>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
            <Kpi rotulo="Somado" valor={`${num(memoria.total_somado)} ${unidade}`} />
            <Kpi rotulo="Subtraído" valor={`${num(memoria.total_subtraido)} ${unidade}`} />
            <Kpi
              rotulo="Quantidade"
              valor={`${num(memoria.quantidade)} ${unidade}`}
              tom="accent"
              apoio={memoria.derivada ? 'derivada das parciais' : 'digitada'}
            />
          </div>

          {memoria.derivada && !memoria.confere && (
            <Aviso tom="danger">
              <AlertTriangle size={13} style={{ verticalAlign: -2, marginRight: 4 }} />
              A soma das parciais ({num(memoria.total)}) não bate com a quantidade da linha
              ({num(memoria.quantidade)}). Recalcule antes de entregar.
            </Aviso>
          )}

          {memoria.derivada && (
            <Aviso tom="info">
              A quantidade desta linha agora é <b>derivada</b>: ela é a soma das parciais abaixo e a
              grade a mostra bloqueada. Duas pontas graváveis divergem — sempre.
            </Aviso>
          )}

          {erro && <Aviso tom="danger">{erro}</Aviso>}

          <SectHead
            right={podeEditar ? (
              <Btn tam="sm" onClick={() => setColando(v => !v)}>
                <ClipboardPaste size={13} />Colar do Excel
              </Btn>
            ) : undefined}
          >
            Parciais
          </SectHead>

          {colando && (
            <div style={{ marginBottom: 12 }}>
              <Field
                label="Cole o bloco"
                dica="Uma parcial por linha: descrição · n · a · b · c, separados por tabulação ou ponto-e-vírgula."
              >
                <textarea
                  autoFocus
                  rows={5}
                  style={{ ...inp, ...mono, width: '100%', resize: 'vertical' }}
                  value={bloco}
                  onChange={e => setBloco(e.target.value)}
                  placeholder={'Parede eixo B\t2\t3,50\t2,80\nParede eixo C\t1\t4,20\t2,80'}
                />
              </Field>
              <Btn variant="primary" tam="sm" onClick={colar}>Gravar o bloco</Btn>
            </div>
          )}

          {!memoria.linhas.length && (
            <Empty>
              Sem parciais. A quantidade continua sendo o número digitado — que calcula certo e não
              responde de onde veio. Uma parede de 19,60 m² conferida é <span style={mono}>2 × 3,50 × 2,80</span>.
            </Empty>
          )}

          {!!memoria.linhas.length && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                <thead>
                  <tr style={{ color: 'var(--ink-3)', textAlign: 'left' }}>
                    <th style={{ padding: '5px 6px' }}>Parcial</th>
                    <th style={{ padding: '5px 6px', textAlign: 'right', width: 60 }}>n</th>
                    <th style={{ padding: '5px 6px', textAlign: 'right', width: 76 }}>a</th>
                    <th style={{ padding: '5px 6px', textAlign: 'right', width: 76 }}>b</th>
                    <th style={{ padding: '5px 6px', textAlign: 'right', width: 76 }}>c</th>
                    <th style={{ padding: '5px 6px', textAlign: 'right', width: 100 }}>Total</th>
                    {podeEditar && <th style={{ width: 36 }} />}
                  </tr>
                </thead>
                <tbody>
                  {memoria.linhas.map(linha => (
                    <tr key={linha.medicao} style={{ borderTop: '1px solid var(--line)' }}>
                      <td style={{ padding: '5px 6px' }}>
                        {linha.sinal === -1 && <span style={{ color: 'var(--danger-ink, crimson)', marginRight: 4 }}>(−)</span>}
                        {linha.descricao || <span style={{ color: 'var(--ink-3)' }}>parcial</span>}
                        {linha.formula && (
                          <Pill kind="info" title="Fórmula livre — substitui n × a × b × c">
                            <span style={mono}>{linha.formula}</span>
                          </Pill>
                        )}
                        {linha.referencia_projeto && (
                          <span style={{ ...CAPS, marginLeft: 6, color: 'var(--ink-3)' }}>
                            {linha.referencia_projeto}
                          </span>
                        )}
                      </td>
                      <td style={{ ...mono, padding: '5px 6px', textAlign: 'right' }}>{num(linha.repeticoes)}</td>
                      <td style={{ ...mono, padding: '5px 6px', textAlign: 'right' }}>{linha.comprimento ? num(linha.comprimento) : '—'}</td>
                      <td style={{ ...mono, padding: '5px 6px', textAlign: 'right' }}>{linha.largura ? num(linha.largura) : '—'}</td>
                      <td style={{ ...mono, padding: '5px 6px', textAlign: 'right' }}>{linha.altura ? num(linha.altura) : '—'}</td>
                      <td style={{ ...mono, padding: '5px 6px', textAlign: 'right', fontWeight: 650 }}>{num(linha.total)}</td>
                      {podeEditar && (
                        <td style={{ padding: '5px 6px' }}>
                          <Btn tam="sm" onClick={() => remover.mutate(linha.medicao)}><Trash2 size={12} /></Btn>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {podeEditar && <NovaParcial onGravar={acrescentar} />}

          <p style={{ ...CAPS, color: 'var(--ink-3)', lineHeight: 1.6, marginTop: 14 }}>
            <InfoIcon size={12} style={{ verticalAlign: -2, marginRight: 4 }} />
            Dimensão em branco é <b>ausência</b>, não zero: uma parcial de contagem pura
            (<span style={mono}>n = 12 unidades</span>) vale 12, e não 0. A subtração é sinal, não
            número negativo — o vão fica gravado como 0,80 × 2,10 e entra somando com sinal.
          </p>
        </>
      )}
    </Drawer>
  )
}

function NovaParcial({ onGravar }: { onGravar: (d: Partial<LinhaMedicao>) => void }) {
  const [aberta, setAberta] = useState(false)
  const [formulaLivre, setFormulaLivre] = useState(false)

  if (!aberta) {
    return (
      <Btn tam="sm" style={{ marginTop: 10 }} onClick={() => setAberta(true)}>
        <Plus size={13} />Nova parcial
      </Btn>
    )
  }

  return (
    <form
      style={{ marginTop: 12, display: 'grid', gap: 8 }}
      onSubmit={e => {
        e.preventDefault()
        const d = new FormData(e.currentTarget)
        const texto = (k: string) => String(d.get(k) ?? '').trim()
        onGravar({
          descricao: texto('descricao'),
          sinal: d.get('sinal') === '-1' ? -1 : 1,
          repeticoes: paraDecimal(texto('repeticoes') || '1'),
          comprimento: texto('a') ? paraDecimal(texto('a')) : null,
          largura: texto('b') ? paraDecimal(texto('b')) : null,
          altura: texto('c') ? paraDecimal(texto('c')) : null,
          formula: formulaLivre ? texto('formula') : '',
          referencia_projeto: texto('referencia'),
        })
        setAberta(false)
      }}
    >
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px', gap: 8 }}>
        <Field label="Onde é"><input name="descricao" style={inp} placeholder="Parede eixo B" /></Field>
        <Field label="Sinal">
          <select name="sinal" style={inp}>
            <option value="1">+ soma</option>
            <option value="-1">− subtrai</option>
          </select>
        </Field>
      </div>

      {formulaLivre ? (
        <Field label="Fórmula" dica="Aritmética livre: + − × ÷ e parênteses. Substitui n × a × b × c.">
          <input name="formula" style={{ ...inp, ...mono }} placeholder="(3,5*2,8)-0,8*2,1" />
        </Field>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
          <Field label="n"><input name="repeticoes" style={{ ...inp, ...mono }} defaultValue="1" /></Field>
          <Field label="a"><input name="a" style={{ ...inp, ...mono }} /></Field>
          <Field label="b"><input name="b" style={{ ...inp, ...mono }} /></Field>
          <Field label="c"><input name="c" style={{ ...inp, ...mono }} /></Field>
        </div>
      )}

      <Field label="Referência de projeto" dica="Prancha, folha ou elemento — o rastro da conferência.">
        <input name="referencia" style={inp} placeholder="ARQ-04" />
      </Field>

      <div style={{ display: 'flex', gap: 8 }}>
        <Btn variant="primary" tam="sm" type="submit">Gravar</Btn>
        <Btn tam="sm" type="button" onClick={() => setFormulaLivre(v => !v)}>
          {formulaLivre ? 'Usar n × a × b × c' : 'Usar fórmula livre'}
        </Btn>
        <Btn tam="sm" type="button" onClick={() => setAberta(false)}>Cancelar</Btn>
      </div>
    </form>
  )
}
