import { lazy, Suspense } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CalendarCheck2, Gauge, LineChart, Package, Wallet } from 'lucide-react'
import { Card, Empty, Loading } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { usePdca } from '../contexto'
import { usePlanoEmEdicao } from '../hooks'
import { PainelAvanco } from '../components/PainelAvanco'
import { PainelControleDeCusto } from '../components/PainelControleDeCusto'
import { PainelDeMateriais } from '../components/PainelDeMateriais'

const HojePage = lazy(() => import('./HojePage'))
const SemanaPage = lazy(() => import('./SemanaPage'))

type Aba = 'hoje' | 'semana' | 'avanco' | 'custo' | 'materiais'

const ABAS: { chave: Aba; rotulo: string; icone: typeof Gauge; permissao: string }[] = [
  { chave: 'hoje', rotulo: 'Hoje', icone: Gauge, permissao: 'pdca.cronograma.view' },
  { chave: 'semana', rotulo: 'Semana', icone: CalendarCheck2, permissao: 'pdca.programacao.view' },
  { chave: 'avanco', rotulo: 'Avanço', icone: LineChart, permissao: 'pdca.cronograma.view' },
  { chave: 'custo', rotulo: 'Custo', icone: Wallet, permissao: 'pdca.cronograma.view' },
  { chave: 'materiais', rotulo: 'Materiais', icone: Package, permissao: 'pdca.cronograma.view' },
]

/** **CONTROLE** — a obra contra o plano.
 *
 *  *Decisão do dono, 10/10/2026:* o posto absorve o **Hoje** (a fila de decisão
 *  do dia) e a **Semana** (programação e PPC), e recebe o que o Orçamento
 *  tinha de execução: o **custo** (orçado × comprometido × aplicado × medido ×
 *  realizado, valor agregado e o custo final projetado) e os **materiais
 *  gastos** (orçado × aplicado × esperado pelo avanço). O avanço físico-
 *  financeiro contra o cronograma do Orçamento também mora aqui. A aba fica na
 *  URL (`?aba=custo`): o link colado abre onde estava. */
export default function ControlePage() {
  const { obraId, planoEscolhido } = usePdca()
  const { hasPermission } = useAuth()
  const [params, setParams] = useSearchParams()
  const aba: Aba = ABAS.find((a) => a.chave === params.get('aba'))?.chave ?? 'hoje'
  const { plano, vigente } = usePlanoEmEdicao(obraId, planoEscolhido)
  const referencia = vigente ?? plano

  const trocar = (a: Aba) => setParams((atual) => {
    const nova = new URLSearchParams(atual)
    if (a === 'hoje') nova.delete('aba')
    else nova.set('aba', a)
    return nova
  })
  const atual = ABAS.find((a) => a.chave === aba)!

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{
        display: 'flex', gap: 4, padding: '10px 22px 0', borderBottom: '1px solid var(--line)',
        background: 'var(--surface)', flexWrap: 'wrap',
      }}>
        {ABAS.map(({ chave, rotulo, icone: Icone, permissao }) => {
          const ativa = chave === aba
          return (
            <button
              key={chave}
              type="button"
              onClick={() => trocar(chave)}
              title={hasPermission(permissao) ? undefined : `Requer a permissão “${permissao}”.`}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 13px',
                fontSize: 12.5, fontWeight: ativa ? 700 : 550, cursor: 'pointer', background: 'transparent',
                border: 'none', borderBottom: `2px solid ${ativa ? 'var(--accent)' : 'transparent'}`,
                color: ativa ? 'var(--ink)' : 'var(--ink-3)', marginBottom: -1,
                opacity: hasPermission(permissao) ? 1 : 0.5,
              }}
            >
              <Icone size={14} />{rotulo}
            </button>
          )
        })}
      </div>

      {!hasPermission(atual.permissao) ? (
        <div style={{ padding: '24px 26px', maxWidth: 620 }}>
          <Card><Empty>Esta aba requer a permissão “{atual.permissao}”. Peça ao administrador da empresa.</Empty></Card>
        </div>
      ) : (
        <Suspense fallback={<Loading o="o controle da obra" />}>
          {aba === 'hoje' && <HojePage />}
          {aba === 'semana' && <SemanaPage />}
          {aba === 'avanco' && (referencia
            ? <div style={{ padding: '18px 22px' }}><PainelAvanco cronogramaId={referencia.cronograma_id} obraId={obraId} /></div>
            : <SemPlano />)}
          {aba === 'custo' && <PainelControleDeCusto obraId={obraId} cronogramaId={referencia?.cronograma_id} />}
          {aba === 'materiais' && <PainelDeMateriais obraId={obraId} />}
        </Suspense>
      )}
    </div>
  )
}

function SemPlano() {
  return (
    <div style={{ padding: '24px 26px', maxWidth: 620 }}>
      <Card><Empty>Esta obra ainda não tem plano. O avanço é apontado contra as atividades do plano — monte-o no posto Plano.</Empty></Card>
    </div>
  )
}
