import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, FilePlus2, Info, ListPlus } from 'lucide-react'
import { Btn, Card, Empty, Loading, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { parseApiErrors } from '@/utils/formErrors'
import {
  useAbrirMedicao, useContrato, useCronogramas, usePeriodoSugerido, useProposta,
} from '../hooks'
import GradeDeMedicao, { useGradeEditavel } from '../components/GradeDeMedicao'
import MemoriaDeCalculo from '../components/MemoriaDeCalculo'
import type { LinhaDaGrade } from '../types'

/**
 * **A prévia — olhar antes de decidir, sem gravar nada.**
 *
 * Ela existe separada do documento por um motivo de produto: o gesto do gestor
 * é *olhar* o período antes de abrir o boletim, e abrir uma medição só para ver
 * a proposta encheria o contrato de rascunhos que ele teria de apagar depois —
 * cada um deixando uma linha na lixeira.
 *
 * **E é somente leitura, de propósito.** A tela antiga deixava editar a prévia
 * *e* editar o rascunho: duas superfícies de digitação para o mesmo número, com
 * o que se digitava na prévia sendo carregado na abertura. Quem conferisse na
 * prévia e voltasse depois não sabia mais qual dos dois estados era o
 * documento. Aqui a régua é uma só: **só se digita dentro de um documento**.
 *
 * O período nasce **encadeado** na última medição (dia seguinte ao fim dela),
 * porque medição de obra é uma corrente — abrir sempre em "1º do mês → hoje"
 * produzia sobreposição no mês medido quinzenalmente e buraco no mês em que a
 * medição atrasou.
 */
export default function PreviaDeMedicaoPage() {
  const { contratoId, obraId } = useParams()
  const id = Number(contratoId)
  const navegar = useNavigate()
  const { hasPermission } = useAuth()
  const podeApurar = hasPermission('pdca.medicao.apurar')

  const contrato = useContrato(id)
  const sugerido = usePeriodoSugerido(id)
  const cronogramas = useCronogramas({ obra: Number(obraId), status: 'vigente' })

  const [inicio, setInicio] = useState('')
  const [fim, setFim] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [memoria, setMemoria] = useState<LinhaDaGrade | null>(null)

  useEffect(() => {
    if (sugerido.data && !inicio) {
      setInicio(sugerido.data.inicio)
      setFim(sugerido.data.fim)
    }
  }, [sugerido.data, inicio])

  const administracao = contrato.data?.regime === 'administracao'
  // No regime de administração a proposta não tem o que dizer: o que se paga é
  // custo declarado. Pedi-la seria gastar uma chamada para mostrar zeros.
  const proposta = useProposta(
    inicio && fim && !administracao ? id : undefined, inicio, fim,
  )
  const grade = useGradeEditavel(proposta.data?.linhas)
  const abrir = useAbrirMedicao(id)

  if (contrato.isLoading) return <Loading o="o contrato" />
  if (!contrato.data) return <Empty>Contrato não encontrado.</Empty>

  const c = contrato.data
  const vigente = c.status === 'vigente'
  const voltar = `/app/pdca/obra/${obraId}/contratos/${contratoId}`
  const ultima = sugerido.data?.ultima_medicao

  return (
    <div style={{ padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Link
        to={voltar}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--ink-3)', fontSize: 13, textDecoration: 'none' }}
      >
        <ArrowLeft size={14} /> Contrato {c.numero}
      </Link>

      <Card>
        <div style={{
          display: 'flex', justifyContent: 'space-between', gap: 16,
          flexWrap: 'wrap', alignItems: 'flex-end',
        }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 20 }}>Prévia da medição</h1>
            <p style={{ margin: '5px 0 0', fontSize: 13, color: 'var(--ink-2)', maxWidth: 620 }}>
              O que se mediria neste período, a partir do avanço apontado no
              cronograma. <strong>Nada é gravado</strong> até você abrir a medição.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <Periodo rotulo="De" valor={inicio} onMudar={setInicio} />
            <Periodo rotulo="Até" valor={fim} onMudar={setFim} />
          </div>
        </div>

        {ultima && (
          <p style={{
            margin: '12px 0 0', fontSize: 12.5, color: 'var(--ink-2)',
            display: 'flex', gap: 7, alignItems: 'center', flexWrap: 'wrap',
          }}>
            <Info size={14} style={{ color: 'var(--ink-3)' }} />
            A medição <strong>{ultima.numero}</strong> foi até{' '}
            {data(ultima.periodo_fim)} — este período começa no dia seguinte.
            {inicio && inicio <= ultima.periodo_fim && (
              <Pill kind="danger">
                sobrepõe a medição {ultima.numero}
              </Pill>
            )}
          </p>
        )}
      </Card>

      {erro && (
        <div style={{
          padding: '10px 12px', borderRadius: 8, fontSize: 13,
          background: 'var(--danger-soft)', color: 'var(--danger-ink)',
          display: 'flex', gap: 8, alignItems: 'flex-start',
        }}>
          <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 2 }} />
          <div>{erro}</div>
        </div>
      )}

      <Card>
        {/* **Administração não mede quantidade.** Mostrar a grade de itens aqui
            era oferecer um instrumento que não vale nesse regime: células que
            não digitam, uma proposta que não vira dinheiro e um aviso de "sem
            vínculo" que não tem o que resolver. O dono colou exatamente uma
            dessas células dizendo *"a parte mais importante da medição não
            consigo editar"*. */}
        {administracao ? (
          <div style={{ padding: '4px 2px' }}>
            <p style={{ margin: 0, fontSize: 13.5, color: 'var(--ink-2)', maxWidth: 680 }}>
              Neste contrato paga-se o <strong>custo da obra no período</strong> mais
              a taxa
              {c.taxa_administracao ? ` de ${Number(c.taxa_administracao)}%` : ''} —
              e não quantidade executada. Não há o que conferir antes: o custo é
              informado ao abrir a medição.
            </p>
            <p style={{ margin: '10px 0 0', fontSize: 12.5, color: 'var(--ink-3)', maxWidth: 680 }}>
              Quer pagar por quantidade medida? Então o regime deste contrato é{' '}
              <strong>preço unitário</strong> — dá para trocar em "Editar", no
              contrato, enquanto não houver medição aprovada.
            </p>
          </div>
        ) : (
        <>
        {proposta.data && proposta.data.cobertura.sem_vinculo > 0 && (
          <p style={{
            margin: '0 0 12px', fontSize: 12.5, color: 'var(--ink-2)',
            background: 'var(--surface-2)', padding: '8px 10px', borderRadius: 8,
          }}>
            <strong>{proposta.data.cobertura.sem_vinculo}</strong> de{' '}
            {proposta.data.cobertura.itens} itens não têm atividade nem item orçado
            ligados, então o sistema não consegue propor quantidade para eles —
            ligue o item a uma frente do cronograma, ou digite a quantidade depois
            de abrir a medição.{' '}
            {proposta.data.cobertura.codigos_sem_vinculo.length > 0 && (
              <span style={{ color: 'var(--ink-3)' }}>
                ({proposta.data.cobertura.codigos_sem_vinculo.join(', ')})
              </span>
            )}
          </p>
        )}

        {proposta.isLoading ? (
          <Loading o="a proposta" />
        ) : (
          <>
            <GradeDeMedicao
              linhas={proposta.data?.linhas ?? []}
              valores={grade.valores}
              onMudar={grade.mudar}
              totais={null}
              somenteLeitura
              onVerMemoria={setMemoria}
              acaoVazia={
                <Btn variant="brand" onClick={() => navegar(voltar)}>
                  <ListPlus size={15} /> Cadastrar a planilha contratual
                </Btn>
              }
            />
            <p style={{ margin: '10px 0 0', fontSize: 12.5, color: 'var(--ink-3)' }}>
              Esta grade é <strong>leitura</strong> — a prévia não grava nada. Os
              números ficam editáveis no documento, depois de abrir a medição.
            </p>
          </>
        )}
        </>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 14 }}>
          {podeApurar && (
            <Btn
              variant="brand"
              disabled={!vigente || abrir.isPending || !inicio || !fim}
              title={!vigente ? 'Só contrato vigente aceita medição.' : undefined}
              onClick={async () => {
                setErro(null)
                try {
                  const nova = await abrir.mutateAsync({ contrato: id, inicio, fim })
                  navegar(`${voltar}/medicoes/${nova.medicao_id}`)
                } catch (e) {
                  setErro(
                    Object.values(parseApiErrors(e)).join(' · ')
                    || 'Não deu para abrir a medição.',
                  )
                }
              }}
            >
              <FilePlus2 size={15} /> Abrir medição do período
            </Btn>
          )}
        </div>
      </Card>

      {memoria && (
        <MemoriaDeCalculo
          linha={memoria}
          obraId={Number(obraId)}
          cronogramaId={cronogramas.data?.results?.[0]?.cronograma_id}
          onClose={() => setMemoria(null)}
        />
      )}
    </div>
  )
}

function Periodo({ rotulo, valor, onMudar }: {
  rotulo: string; valor: string; onMudar: (v: string) => void
}) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)', marginBottom: 3 }}>
        {rotulo}
      </label>
      <input
        type="date"
        value={valor}
        onChange={e => onMudar(e.target.value)}
        style={{
          padding: '7px 9px', borderRadius: 8, border: '1px solid var(--line)',
          background: 'var(--surface)', color: 'var(--ink)', fontSize: 13,
        }}
      />
    </div>
  )
}

const data = (v: string) => v.split('-').reverse().join('/')
