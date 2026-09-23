import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarDays, GanttChartSquare, Layers, TrendingUp } from 'lucide-react'
import { Btn, Card, Empty, Loading, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { dateToBR } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import { linhasVisiveis, todosOsPais } from '../arvore'
import { usePdca } from '../contexto'
import {
  useCalcularPlano, useGantt, useLinhaDeBalanco, usePlanoCorrente,
  usePublicarPlano, useSalvarAtividade,
} from '../hooks'
import { GanttSvg, type Zoom } from '../components/GanttSvg'
import { GradeEap } from '../components/GradeEap'
import { LinhaDeBalancoSvg } from '../components/LinhaDeBalancoSvg'
import { PainelCalendario } from '../components/PainelCalendario'
import { PainelLocais } from '../components/PainelLocais'

type Vista = 'cronograma' | 'ritmo' | 'locais' | 'expediente'

const VISTAS: { chave: Vista; rotulo: string; icone: typeof GanttChartSquare }[] = [
  { chave: 'cronograma', rotulo: 'Cronograma', icone: GanttChartSquare },
  { chave: 'ritmo', rotulo: 'Ritmo', icone: TrendingUp },
  { chave: 'locais', rotulo: 'Locais', icone: Layers },
  { chave: 'expediente', rotulo: 'Expediente', icone: CalendarDays },
]

/** O posto do planejamento. Quatro vistas sobre **o mesmo plano**, trocáveis sem
 *  trocar de rota — a lição de que o cronograma tem leituras diferentes por
 *  papel, e não telas diferentes. */
export default function PlanoPage() {
  const { obraId, selecao, selecionar } = usePdca()
  const { hasPermission } = useAuth()
  const [vista, setVista] = useState<Vista>('cronograma')
  const [zoom, setZoom] = useState<Zoom>('semana')
  const [mostrarBase, setMostrarBase] = useState(true)
  const [fechados, setFechados] = useState<Set<number>>(new Set())
  const [erro, setErro] = useState<string | null>(null)

  const { plano, isLoading: carregandoPlanos } = usePlanoCorrente(obraId)
  const gantt = useGantt(plano?.cronograma_id)
  const balanco = useLinhaDeBalanco(plano?.cronograma_id, vista === 'ritmo')

  const salvar = useSalvarAtividade(plano?.cronograma_id)
  const calcular = useCalcularPlano(plano?.cronograma_id)
  const publicar = usePublicarPlano(plano?.cronograma_id)

  const atividades = useMemo(() => gantt.data?.atividades ?? [], [gantt.data])
  const linhas = useMemo(() => linhasVisiveis(atividades, fechados), [atividades, fechados])

  useEffect(() => { setFechados(new Set()) }, [plano?.cronograma_id])

  if (carregandoPlanos) return <Loading o="o plano da obra" />

  if (!plano) {
    return (
      <div style={{ padding: '24px 26px', maxWidth: 620 }}>
        <Card>
          <Empty>
            <span style={{ lineHeight: 1.6 }}>
              Esta obra ainda não tem plano. O planejamento começa montando a
              estrutura do que será feito e em que ordem.
            </span>
            <Link to={`/app/obras/${obraId}`} style={{ textDecoration: 'none' }}>
              <Btn variant="primary">Abrir a obra</Btn>
            </Link>
          </Empty>
        </Card>
      </div>
    )
  }

  const podeEditar = hasPermission('pdca.cronograma.edit') && plano.editavel
  const podePublicar = hasPermission('pdca.cronograma.publicar') && plano.status === 'rascunho'
  const selecionada = selecao?.tipo === 'atividade' ? selecao.id : null

  function alternar(id: number) {
    setFechados((atual) => {
      const novo = new Set(atual)
      if (novo.has(id)) novo.delete(id)
      else novo.add(id)
      return novo
    })
  }

  async function executar(acao: () => Promise<unknown>) {
    setErro(null)
    try {
      await acao()
    } catch (e) {
      const erros = parseApiErrors(e)
      setErro(erros._form ?? Object.values(erros)[0] ?? 'Não foi possível concluir.')
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
          padding: '12px 18px', borderBottom: '1px solid var(--line)',
          background: 'var(--surface)', flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontSize: 15, fontWeight: 750, color: 'var(--ink)' }}>Plano</span>
          <Pill kind={plano.status === 'vigente' ? 'good' : 'accent'}>
            {plano.status_rotulo} · v{plano.versao}
          </Pill>
          {plano.termino_calculado ? (
            <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
              termina em{' '}
              <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>
                {dateToBR(plano.termino_calculado)}
              </span>
            </span>
          ) : (
            <span style={{ fontSize: 12, color: 'var(--ink-3)', fontStyle: 'italic' }}>
              sem prazo — o plano ainda não foi calculado
            </span>
          )}
        </div>

        <span style={{ flex: 1 }} />

        <div style={{ display: 'flex', gap: 2, background: 'var(--inset)', borderRadius: 'var(--r-sm)', padding: 2 }}>
          {VISTAS.map(({ chave, rotulo, icone: Icone }) => (
            <button
              key={chave}
              type="button"
              onClick={() => setVista(chave)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: vista === chave ? 'var(--surface)' : 'transparent',
                border: 'none', borderRadius: 5, cursor: 'pointer',
                padding: '5px 10px', fontSize: 12, fontWeight: 650,
                color: vista === chave ? 'var(--ink)' : 'var(--ink-3)',
                boxShadow: vista === chave ? 'var(--shadow-sm)' : 'none',
              }}
            >
              <Icone size={13} />
              {rotulo}
            </button>
          ))}
        </div>

        {hasPermission('pdca.cronograma.edit') && (
          <Btn
            tam="sm"
            onClick={() => executar(() => calcular.mutateAsync(plano.cronograma_id))}
            disabled={calcular.isPending}
          >
            {calcular.isPending ? 'Calculando…' : 'Calcular'}
          </Btn>
        )}
        {podePublicar && (
          <Btn
            tam="sm"
            variant="primary"
            onClick={() => executar(() => publicar.mutateAsync(plano.cronograma_id))}
            disabled={publicar.isPending}
          >
            {publicar.isPending ? 'Publicando…' : 'Publicar'}
          </Btn>
        )}
      </div>

      {erro && (
        <div
          style={{
            padding: '9px 18px', background: 'var(--danger-soft)',
            color: 'var(--danger-ink)', fontSize: 12.5, flexShrink: 0,
          }}
        >
          {erro}
        </div>
      )}

      {plano.status === 'vigente' && (
        <div
          style={{
            padding: '7px 18px', background: 'var(--inset)', flexShrink: 0,
            fontSize: 12, color: 'var(--ink-3)', borderBottom: '1px solid var(--line-2)',
          }}
        >
          Este plano está vigente e não se edita. Para mudá-lo, replaneje — é o que
          guarda a versão atual como referência do combinado.
        </div>
      )}

      {vista === 'cronograma' && (
        <BarraDoCronograma
          zoom={zoom}
          setZoom={setZoom}
          mostrarBase={mostrarBase}
          setMostrarBase={setMostrarBase}
          temBase={gantt.data?.base.tem_base ?? false}
          aoExpandirTudo={() => setFechados(new Set())}
          aoRecolherTudo={() => setFechados(new Set(todosOsPais(atividades)))}
        />
      )}

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        {gantt.isLoading && <Loading o="o cronograma" />}

        {gantt.isError && (
          <div style={{ padding: 26 }}>
            <Card>
              <Empty>
                Não foi possível carregar o cronograma. Verifique a conexão e tente de novo.
              </Empty>
            </Card>
          </div>
        )}

        {gantt.data && vista === 'cronograma' && (
          atividades.length === 0 ? (
            <div style={{ padding: '24px 26px', maxWidth: 620 }}>
              <Card>
                <Empty>
                  Este plano ainda não tem atividades. Monte a estrutura do que será
                  feito para o cronograma existir.
                </Empty>
              </Card>
            </div>
          ) : (
            <div style={{ display: 'flex', minWidth: 'max-content' }}>
              <GradeEap
                linhas={linhas}
                avanco={gantt.data.avanco}
                selecionada={selecionada}
                editavel={podeEditar}
                salvando={salvar.isPending}
                aoSelecionar={(id) => selecionar({ tipo: 'atividade', id })}
                aoAlternar={alternar}
                aoSalvar={(id, corpo) => executar(() => salvar.mutateAsync({ id, corpo }))}
              />
              <GanttSvg
                linhas={linhas}
                precedencias={gantt.data.precedencias}
                base={gantt.data.base}
                avanco={gantt.data.avanco}
                zoom={zoom}
                mostrarBase={mostrarBase && gantt.data.base.tem_base}
                selecionada={selecionada}
                aoSelecionar={(id) => selecionar({ tipo: 'atividade', id })}
              />
            </div>
          )
        )}

        {vista === 'ritmo' && (
          <div style={{ padding: '18px 22px' }}>
            {balanco.isLoading && <Loading o="a linha de balanço" />}
            {balanco.data && <LinhaDeBalancoSvg dados={balanco.data} />}
          </div>
        )}

        {vista === 'locais' && (
          <div style={{ padding: '18px 22px', maxWidth: 780 }}>
            <PainelLocais obraId={obraId} />
          </div>
        )}

        {vista === 'expediente' && (
          <div style={{ padding: '18px 22px' }}>
            <PainelCalendario obraId={obraId} />
          </div>
        )}
      </div>
    </div>
  )
}

function BarraDoCronograma(
  { zoom, setZoom, mostrarBase, setMostrarBase, temBase, aoExpandirTudo, aoRecolherTudo }: {
    zoom: Zoom
    setZoom: (z: Zoom) => void
    mostrarBase: boolean
    setMostrarBase: (v: boolean) => void
    temBase: boolean
    aoExpandirTudo: () => void
    aoRecolherTudo: () => void
  },
) {
  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
        padding: '7px 18px', borderBottom: '1px solid var(--line-2)',
        background: 'var(--surface-2)', flexShrink: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }}>
          Escala
        </span>
        {(['dia', 'semana', 'mes'] as Zoom[]).map((z) => (
          <button
            key={z}
            type="button"
            onClick={() => setZoom(z)}
            style={{
              background: zoom === z ? 'var(--surface)' : 'transparent',
              border: `1px solid ${zoom === z ? 'var(--line)' : 'transparent'}`,
              borderRadius: 5, cursor: 'pointer', padding: '3px 9px',
              fontSize: 11.5, fontWeight: 650,
              color: zoom === z ? 'var(--ink)' : 'var(--ink-3)',
            }}
          >
            {z === 'mes' ? 'mês' : z}
          </button>
        ))}
      </div>

      <label
        title={temBase ? undefined : 'Este plano ainda não tem versão anterior para comparar'}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          fontSize: 12, color: temBase ? 'var(--ink-2)' : 'var(--ink-3)',
          cursor: temBase ? 'pointer' : 'not-allowed',
        }}
      >
        <input
          type="checkbox"
          checked={mostrarBase && temBase}
          disabled={!temBase}
          onChange={(e) => setMostrarBase(e.target.checked)}
        />
        Linha de base
      </label>

      <span style={{ flex: 1 }} />

      <div style={{ display: 'flex', gap: 6 }}>
        <Btn tam="sm" onClick={aoExpandirTudo}>Expandir tudo</Btn>
        <Btn tam="sm" onClick={aoRecolherTudo}>Recolher tudo</Btn>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11, color: 'var(--ink-3)' }}>
        <Legenda cor="var(--brand)" texto="previsto" />
        <Legenda cor="var(--good)" texto="executado" />
        <Legenda cor="var(--danger)" texto="crítica" />
        {temBase && <Legenda cor="var(--ink-3)" texto="base" />}
      </div>
    </div>
  )
}

function Legenda({ cor, texto }: { cor: string; texto: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <span style={{ width: 10, height: 6, borderRadius: 2, background: cor, display: 'inline-block' }} />
      {texto}
    </span>
  )
}
