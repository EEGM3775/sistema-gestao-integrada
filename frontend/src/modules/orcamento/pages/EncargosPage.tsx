import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Download, Info as InfoIcon, Lock, Plus, Trash2,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import PaginaShell from '../components/PaginaShell'
import {
  Aviso, Btn, Card, CAPS, Empty, inp, Kpi, Loading, mono, Pill, SectHead,
  Select,
} from '../ui'
import { paraDecimal, pct } from '../lib'
import {
  useAtualizarRubrica, useCriarQuadroEncargos, useOrcamentos, useQuadroEncargos,
  useQuadrosEncargos, useRemoverQuadroEncargos,
} from '../hooks'
import { baixarExportacao } from '../api/orcamentoApi'
import type { QuadroEncargos, TipoMaoDeObra } from '../types'

/** A página onde o **preço** ganha parâmetro: os encargos sobre a folha.
 *
 *  *Decisão do dono, 10/10/2026:* o reajuste contratual saiu daqui — é cláusula
 *  de contrato, e mora no contrato do PDCA (medição do empreiteiro e do
 *  contratante). O Orçamento só planeja. */
export default function EncargosPage() {
  const { hasPermission } = useAuth()
  const [params, setParams] = useSearchParams()
  const orcamentoId = params.get('orcamento') ? Number(params.get('orcamento')) : undefined
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
    </>
  )

  return (
    <PaginaShell
      pagina="encargos"
      seletor={seletor}
      acoes={orcamentoId ? (
        <>
          <Btn
            onClick={() => baixarExportacao(orcamentoId, { peca: 'encargos' })}
            title="Baixar a peça em XLSX — é o anexo que acompanha a planilha na proposta"
          >
            <Download size={14} />Quadro de encargos
          </Btn>
          <Btn onClick={() => baixarExportacao(orcamentoId, { peca: 'composicao-bdi' })}>
            <Download size={14} />Composição do BDI
          </Btn>
        </>
      ) : undefined}
    >
      <div style={{ padding: '18px 20px 30px', display: 'grid', gap: 14 }}>
        {recado && <Aviso tom="info">{recado}</Aviso>}

        {!orcamentoId && (
          <Empty>
            Escolha um orçamento acima. Os encargos são parâmetros <b>daquela</b> planilha —
            o quadro de uma obra em Sergipe não serve para uma em São Paulo. O reajuste contratual
            mora no contrato, no PDCA.
          </Empty>
        )}

        {orcamentoId && (
          <PainelEncargos
            orcamentoId={orcamentoId}
            podeEditar={podeEditar}
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
