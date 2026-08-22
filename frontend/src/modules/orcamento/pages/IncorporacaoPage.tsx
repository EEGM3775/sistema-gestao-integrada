import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Building2, Calculator, FileText, Info as InfoIcon, Scale } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import PaginaShell from '../components/PaginaShell'
import { Aviso, Btn, Card, CAPS, Empty, EmBreve, Info, Kpi, Loading, mono, Pill, SectHead, Select, Seletor } from '../ui'
import { brl, brlCurto, mesBR, num, pct } from '../lib'
import { useObras, useParametricos, usePavimentos, useQuadrosNBR, useUnidades } from '../hooks'

type Aba = 'parametrico' | 'quadros'

interface QuadroI {
  titulo: string
  pavimentos: Record<string, string | number>[]
  area_real_global: string
  area_equivalente_global: string
}
interface QuadroII {
  titulo: string
  unidades: Record<string, string | number | null>[]
  area_real_total: string
  area_equivalente_total: string
}
interface QuadroIII {
  titulo: string
  custo_global: string
  fonte_do_custo: string
  area_real_global: string
  area_equivalente_global: string
  custo_por_m2_equivalente: string | null
  custo_por_m2_real: string | null
}
interface QuadroIV {
  titulo: string
  custo_global: string
  fonte_do_custo: string
  soma_coeficientes: string
  unidades: Record<string, string | number>[]
}
interface Dossie {
  obra: number
  quadros: Record<string, unknown>
  indisponivel: Record<string, string>
  descritivos_faltando: string[]
}

export default function IncorporacaoPage() {
  const { hasPermission } = useAuth()
  const [aba, setAba] = useState<Aba>('parametrico')
  const [obraId, setObraId] = useState<number | ''>('')

  const { data: obras } = useObras()
  const { data: parametricos, isLoading: carregandoParam } = useParametricos(obraId || undefined)
  const { data: pavimentos } = usePavimentos(aba === 'quadros' ? (obraId || undefined) : undefined)
  const { data: unidades } = useUnidades(aba === 'quadros' ? (obraId || undefined) : undefined)
  const { data: nbrBruto, isLoading: carregandoNbr } = useQuadrosNBR(aba === 'quadros' ? (obraId || undefined) : undefined)

  const podeVer = hasPermission('orcamento.relatorio.view')
  const nbr = nbrBruto as unknown as Dossie | undefined

  const parametrico = useMemo(() => parametricos?.[0], [parametricos])

  const seletor = (
    <>
      <Select value={obraId} onChange={e => setObraId(e.target.value ? Number(e.target.value) : '')} style={{ maxWidth: 230 }}>
        <option value="">Selecione a obra</option>
        {obras?.map(o => <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>)}
      </Select>
      <Seletor
        compacto
        valor={aba}
        onChange={setAba}
        opcoes={[
          { valor: 'parametrico' as Aba, rotulo: 'Paramétrico (CUB)' },
          { valor: 'quadros' as Aba, rotulo: 'Quadros NBR 12721' },
        ]}
      />
    </>
  )

  if (!podeVer) {
    return (
      <PaginaShell pagina="incorporacao">
        <div style={{ padding: 26 }}>
          <Empty>Esta página exige a permissão <code style={{ ...mono }}>orcamento.relatorio.view</code>.</Empty>
        </div>
      </PaginaShell>
    )
  }

  const quadroI = nbr?.quadros?.I as QuadroI | undefined
  const quadroII = nbr?.quadros?.II as QuadroII | undefined
  const quadroIII = nbr?.quadros?.III as QuadroIII | undefined
  const quadroIV = nbr?.quadros?.IV as QuadroIV | undefined

  return (
    <PaginaShell pagina="incorporacao" seletor={seletor}>
      <div style={{ padding: '18px 22px 40px', overflowY: 'auto' }}>
        {!obraId ? (
          <Empty>
            Escolha a obra. Esta página resolve os dois momentos da incorporação: a <b>estimativa
            rápida</b> na viabilidade (área × CUB, antes de existir planilha) e os <b>quadros da NBR
            12721</b>, que são condição para registrar o memorial em cartório.
          </Empty>
        ) : aba === 'parametrico' ? (
          <>
            <SectHead>Estimativa paramétrica por CUB</SectHead>
            {carregandoParam ? <Loading /> : !parametrico ? (
              <Empty acao={<EmBreve><Calculator size={11} />Cadastro pelo backend</EmBreve>}>
                Esta obra ainda não tem paramétrico. O cálculo é <b>área equivalente × CUB do mês</b>,
                mais um percentual de adicionais (elevador, fundação especial, projetos) — a conta que
                se faz antes de existir planilha, para decidir se o terreno fecha.
              </Empty>
            ) : (
              <>
                <Card style={{ display: 'flex', gap: 28, flexWrap: 'wrap', padding: '16px 20px' }}>
                  <Kpi rotulo="Custo estimado" valor={brlCurto(parametrico.custo_estimado)} apoio={parametrico.descricao} />
                  <Kpi rotulo="Área equivalente" valor={<span style={{ ...mono }}>{num(parametrico.area_equivalente, 2)} m²</span>} apoio={`área real ${num(parametrico.area_real, 2)} m²`} />
                  <Kpi rotulo="CUB" valor={brl(parametrico.cub_m2)} apoio={`${parametrico.cub_uf} · ${mesBR(parametrico.cub_mes)}`} />
                  <Kpi rotulo="Adicionais" valor={pct(parametrico.percentual_adicionais, 1)} apoio={brl(parametrico.valor_adicionais)} />
                  <Kpi rotulo="Projeto-padrão" valor={<span style={{ fontSize: 15 }}>{parametrico.projeto_padrao_nome}</span>} apoio="NBR 12721" />
                </Card>

                <Aviso tom="info">
                  <InfoIcon size={15} style={{ flex: 'none', marginTop: 1 }} />
                  <span>
                    O paramétrico é <b>estimativa</b>, não régua: quem manda no controle de custo é a
                    planilha analítica aprovada. O valor dele serve para a viabilidade e, quando não há
                    planilha, como base de custo do Quadro III.
                  </span>
                </Aviso>

                <SectHead>Paramétrico × analítico</SectHead>
                <ComparativoParametrico parametroId={parametrico.parametro_id} obraId={Number(obraId)} />
              </>
            )}
          </>
        ) : (
          <>
            {carregandoNbr ? <Loading texto="Montando o dossiê…" /> : (
              <>
                <SectHead right={
                  nbr && Object.keys(nbr.indisponivel).length > 0
                    ? <Pill kind="amber">{Object.keys(nbr.indisponivel).length} quadro(s) sem base</Pill>
                    : <Pill kind="good">I–IV calculados</Pill>
                }>
                  Dossiê da NBR 12721
                </SectHead>

                {nbr && Object.entries(nbr.indisponivel).length > 0 && (
                  <Aviso tom="amber">
                    <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
                    <span>
                      {Object.entries(nbr.indisponivel).map(([q, motivo]) => (
                        <span key={q} style={{ display: 'block' }}><b>Quadro {q}:</b> {motivo}</span>
                      ))}
                    </span>
                  </Aviso>
                )}

                {quadroIII && (
                  <Card style={{ display: 'flex', gap: 28, flexWrap: 'wrap', padding: '16px 20px', marginTop: 10 }}>
                    <Kpi rotulo="Custo global" valor={brlCurto(quadroIII.custo_global)} apoio={`fonte: ${quadroIII.fonte_do_custo}`} />
                    <Kpi rotulo="Custo / m² equivalente" valor={brl(quadroIII.custo_por_m2_equivalente)} apoio={`${num(quadroIII.area_equivalente_global, 2)} m² eq.`} />
                    <Kpi rotulo="Custo / m² real" valor={brl(quadroIII.custo_por_m2_real)} apoio={`${num(quadroIII.area_real_global, 2)} m² reais`} />
                  </Card>
                )}

                <SectHead>Quadro I — áreas por pavimento</SectHead>
                {!quadroI || quadroI.pavimentos.length === 0 ? (
                  <Empty acao={<EmBreve><Building2 size={11} />Cadastro de pavimentos pelo backend</EmBreve>}>
                    Nenhum pavimento cadastrado. O Quadro I é a base de todos os outros — sem área
                    equivalente não há rateio nem custo por m².
                  </Empty>
                ) : (
                  <TabelaQuadro
                    colunas={['Pavimento', 'Coberta padrão', 'Coberta diferente', 'Coef.', 'Descoberta', 'Coef.', 'Área real', 'Área equiv.']}
                    chaves={['nome', 'area_coberta_padrao', 'area_coberta_diferente', 'coeficiente_coberta_diferente', 'area_descoberta', 'coeficiente_descoberta', 'area_real', 'area_equivalente']}
                    linhas={quadroI.pavimentos}
                    rodape={['Global', '', '', '', '', '', quadroI.area_real_global, quadroI.area_equivalente_global]}
                    unidade="m²"
                  />
                )}

                <SectHead right={pavimentos ? <span style={{ ...CAPS }}>{pavimentos.length} pavimento(s)</span> : undefined}>
                  Quadro II — áreas das unidades autônomas
                </SectHead>
                {!quadroII || quadroII.unidades.length === 0 ? (
                  <Empty acao={<EmBreve>Cadastro de unidades pelo backend</EmBreve>}>
                    Nenhuma unidade autônoma cadastrada.
                  </Empty>
                ) : (
                  <TabelaQuadro
                    colunas={['Unidade', 'Tipo', 'Pavimento', 'Privativa padrão', 'Privativa dif.', 'Real privativa', 'Uso comum', 'Real total', 'Equiv. privativa', 'Coef. prop.', 'Fração ideal']}
                    chaves={['designacao', 'tipo', 'pavimento', 'area_privativa_padrao', 'area_privativa_diferente', 'area_real_privativa', 'area_uso_comum', 'area_real_total', 'area_equivalente_privativa', 'coeficiente_proporcionalidade', 'fracao_ideal']}
                    linhas={quadroII.unidades}
                    rodape={['Total', '', '', '', '', quadroII.area_real_total, '', '', quadroII.area_equivalente_total, '', '']}
                  />
                )}

                {quadroIV && quadroIV.unidades.length > 0 && (
                  <>
                    <SectHead right={<span style={{ ...CAPS }}>Σ coeficientes {num(quadroIV.soma_coeficientes, 4)}</span>}>
                      Quadro IV — rateio do custo por unidade
                    </SectHead>
                    <TabelaQuadro
                      colunas={['Unidade', 'Equiv. privativa', 'Coef. prop.', 'Fração ideal', 'Custo estimado']}
                      chaves={['designacao', 'area_equivalente_privativa', 'coeficiente_proporcionalidade', 'fracao_ideal', 'custo_estimado']}
                      linhas={quadroIV.unidades}
                      moeda={['custo_estimado']}
                    />
                    <Aviso tom="info">
                      <Scale size={15} style={{ flex: 'none', marginTop: 1 }} />
                      <span>
                        <b>Coeficiente de proporcionalidade ≠ fração ideal.</b> O coeficiente sai do
                        cálculo (área equivalente da unidade sobre o total) e rateia o <i>custo</i>; a
                        fração ideal é decisão jurídica do incorporador sobre o <i>terreno</i>, e por isso
                        continua editável. Confundir os dois é exigência certa no cartório.
                      </span>
                    </Aviso>
                  </>
                )}

                <SectHead right={
                  nbr && nbr.descritivos_faltando.length > 0
                    ? <Pill kind="amber">{nbr.descritivos_faltando.length} faltando</Pill>
                    : undefined
                }>
                  Quadros V a VIII — descritivos
                </SectHead>
                <Card>
                  <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap', marginBottom: 12 }}>
                    {['V', 'VI', 'VII', 'VIII'].map(q => {
                      const presente = !!nbr?.quadros?.[q]
                      return <Pill key={q} kind={presente ? 'good' : 'slate'}>Quadro {q} · {presente ? 'preenchido' : 'vazio'}</Pill>
                    })}
                  </div>
                  <Aviso tom="info">
                    <FileText size={15} style={{ flex: 'none', marginTop: 1 }} />
                    <span>
                      Estes quatro são <b>descrição técnica do projetista</b>, não cálculo — memorial de
                      acabamentos, equipamentos e dependências. O sistema não gera conteúdo para eles de
                      propósito: texto automático num documento que vai a cartório vira memorial que não
                      corresponde à obra.
                    </span>
                  </Aviso>
                </Card>

                <SectHead>De onde vem o custo</SectHead>
                <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap' }}>
                  <Link to={`/app/orcamento/orcar`} style={{ textDecoration: 'none' }}>
                    <Card className="orc-lift" style={{ padding: '11px 15px', minWidth: 210 }}>
                      <div style={{ ...CAPS }}>Planilha analítica</div>
                      <div style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 600 }}>Orçamento aprovado da obra</div>
                      <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>preferida como base do Quadro III</div>
                    </Card>
                  </Link>
                  <Card style={{ padding: '11px 15px', minWidth: 210 }}>
                    <div style={{ ...CAPS }}>Paramétrico</div>
                    <div style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 600 }}>Área equivalente × CUB</div>
                    <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>usado quando não há planilha aprovada</div>
                  </Card>
                  <Link to={`/app/obras/${obraId}`} style={{ textDecoration: 'none' }}>
                    <Card className="orc-lift" style={{ padding: '11px 15px', minWidth: 210 }}>
                      <div style={{ ...CAPS }}>Obra</div>
                      <div style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 600 }}>Ficha e etapas</div>
                      <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{unidades?.length ?? 0} unidade(s) cadastrada(s)</div>
                    </Card>
                  </Link>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </PaginaShell>
  )
}

function ComparativoParametrico({ parametroId, obraId }: { parametroId: number; obraId: number }) {
  const [dados, setDados] = useState<{ parametrico: string; analitico: string | null; desvio: string | null; desvio_pct: string | null; detalhe?: string } | null>(null)
  const [carregando, setCarregando] = useState(false)

  return (
    <Card>
      {!dados ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ flex: 1, minWidth: 240, fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.55 }}>
            Comparar a estimativa com a planilha aprovada é o que calibra a próxima viabilidade — se o
            paramétrico erra sempre para menos, o percentual de adicionais está baixo.
          </span>
          <Btn tam="sm" disabled={carregando} onClick={async () => {
            setCarregando(true)
            try {
              const { compararParametrico } = await import('../api/orcamentoApi')
              const r = await compararParametrico(parametroId)
              setDados(r as unknown as typeof dados)
            } finally { setCarregando(false) }
          }}>
            <Scale size={13} />Comparar
          </Btn>
        </div>
      ) : dados.analitico === null ? (
        <Aviso tom="amber">
          <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
          {dados.detalhe ?? 'A obra ainda não tem orçamento analítico aprovado para comparar.'}{' '}
          <Link to={`/app/orcamento/orcar/obra/${obraId}`} style={{ color: 'inherit', fontWeight: 700 }}>Montar a planilha</Link>.
        </Aviso>
      ) : (
        <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
          <Info k="Paramétrico" v={brl(dados.parametrico)} m />
          <Info k="Analítico aprovado" v={brl(dados.analitico)} m />
          <Info k="Desvio" v={
            <span style={{ color: Number(dados.desvio) > 0 ? 'var(--danger-ink)' : 'var(--good-ink)' }}>
              {brl(dados.desvio)} {dados.desvio_pct ? `(${pct(dados.desvio_pct, 1)})` : ''}
            </span>
          } m />
        </div>
      )}
    </Card>
  )
}

function TabelaQuadro({ colunas, chaves, linhas, rodape, unidade, moeda }: {
  colunas: string[]
  chaves: string[]
  linhas: Record<string, string | number | null>[]
  rodape?: (string | number)[]
  unidade?: string
  moeda?: string[]
}) {
  const formatar = (chave: string, valor: string | number | null) => {
    if (valor === null || valor === undefined || valor === '') return '—'
    if (moeda?.includes(chave)) return brl(String(valor))
    if (typeof valor === 'string' && /^-?\d+([.,]\d+)?$/.test(valor)) {
      return `${num(valor, 2)}${unidade && chave.startsWith('area') ? ` ${unidade}` : ''}`
    }
    return String(valor)
  }

  return (
    <Card pad={false} style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, minWidth: colunas.length * 108 }}>
        <thead>
          <tr>
            {colunas.map((c, i) => (
              <th key={c} style={{
                ...CAPS, padding: '9px 12px', textAlign: i === 0 ? 'left' : 'right',
                borderBottom: '1px solid var(--line)', background: 'var(--surface-2)',
              }}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {linhas.map((linha, n) => (
            <tr key={n} className="orc-linha">
              {chaves.map((chave, i) => (
                <td key={chave} style={{
                  padding: '7px 12px', borderBottom: '1px solid var(--line-2)',
                  textAlign: i === 0 ? 'left' : 'right',
                  color: i === 0 ? 'var(--ink)' : 'var(--ink-2)',
                  fontWeight: i === 0 ? 600 : 400,
                  ...(i === 0 ? {} : mono),
                }}>{formatar(chave, linha[chave] as string | number | null)}</td>
              ))}
            </tr>
          ))}
          {rodape && (
            <tr>
              {rodape.map((v, i) => (
                <td key={i} style={{
                  padding: '9px 12px', borderTop: '2px solid var(--line)', textAlign: i === 0 ? 'left' : 'right',
                  background: 'var(--surface-2)', fontWeight: 700, color: 'var(--ink)',
                  ...(i === 0 ? { ...CAPS } : mono),
                }}>{v === '' ? '' : i === 0 ? v : `${num(String(v), 2)}${unidade ? ` ${unidade}` : ''}`}</td>
              ))}
            </tr>
          )}
        </tbody>
      </table>
    </Card>
  )
}
