import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, CheckCircle2, CircleDot, Cloud, CloudOff,
  ListPlus, RotateCcw, Save, Send, Trash2,
} from 'lucide-react'
import { Btn, CampoMoeda, Card, Empty, Loading, Modal, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { apiDecimalToCents, centsToApiDecimal } from '@/utils/money'
import { parseApiErrors } from '@/utils/formErrors'
import {
  useAtestarMedicao, useCancelarMedicao, useContrato, useContextoDeMedicao,
  useCronogramas, useExcluirMedicao, useMedicao, useRetificarMedicao,
  useSalvarCabecalho, useSalvarDeducoes, useSalvarLinhas, useSubmeterMedicao,
} from '../hooks'
import { useAutosave, rotuloDoSalvamento } from '../autosave'
import GradeDeMedicao, { useGradeEditavel } from '../components/GradeDeMedicao'
import PainelDeDeducoes, { useDeducoes } from '../components/PainelDeDeducoes'
import BoletimDeMedicao from '../components/BoletimDeMedicao'
import MemoriaDeCalculo from '../components/MemoriaDeCalculo'
import { CORES_MEDICAO } from '../components/cores'
import type { LinhaDaGrade } from '../types'

/**
 * **A medição — um documento, com endereço próprio e dois modos.**
 *
 * Antes, o boletim era um `?medicao=14` que reconfigurava um card no meio da
 * tela do contrato, abaixo da planilha contratual inteira. Três defeitos vinham
 * daí, e os três somem aqui:
 *
 * 1. **Os números mudavam conforme o caminho de entrada.** A grade montava
 *    `saldo = contratado − já medido` no navegador, a partir de uma prévia que
 *    só era buscada quando *não* havia medição aberta. Pelo link direto, "já
 *    medido" saía negativo e a trava de excesso — que compara contra o saldo —
 *    desligava. Agora tudo vem de `/medicoes/{id}/contexto/`.
 * 2. **Digitar e submeter perdia a digitação.** "Salvar grade" e "Submeter"
 *    eram botões independentes, e submeter mandava só o id: o documento era
 *    aprovado com os números antigos, sem erro e sem aviso. Agora a grade grava
 *    sozinha, o selo diz o estado, e submeter grava antes de submeter.
 * 3. **Aprovada, a medição aparecia como planilha de digitação em cinza.** Um
 *    documento congelado é um **boletim**: só as linhas medidas, as parcelas do
 *    pagamento, a escada de atesto com quem assinou, e imprimível.
 */

export default function MedicaoPage() {
  const { contratoId, medicaoId, obraId } = useParams()
  const id = Number(medicaoId)
  const contrato = Number(contratoId)
  const navegar = useNavigate()
  const { hasPermission } = useAuth()
  const podeApurar = hasPermission('pdca.medicao.apurar')
  const podeAtestar = hasPermission('pdca.medicao.atestar')

  const medicao = useMedicao(id)
  const contextoQ = useContextoDeMedicao(id)
  const contratoQ = useContrato(contrato)
  const cronogramas = useCronogramas({ obra: Number(obraId), status: 'vigente' })

  const [erro, setErro] = useState<string | null>(null)
  const [avisos, setAvisos] = useState<string[]>([])
  const [memoria, setMemoria] = useState<LinhaDaGrade | null>(null)

  const m = medicao.data
  const c = contratoQ.data
  const contexto = contextoQ.data
  const rascunho = m?.status === 'rascunho'
  const editavel = Boolean(rascunho && podeApurar)
  const administracao = c?.regime === 'administracao'

  // --- a grade e o seu autosave --------------------------------------------
  // `'documento'`: a grade de um documento aberto começa no que está gravado
  // nele — inclusive no zero de uma linha que o gestor decidiu não medir.
  const grade = useGradeEditavel(contexto?.linhas, 'documento')
  const salvarLinhas = useSalvarLinhas(contrato)
  const autosaveGrade = useAutosave({
    valor: grade.paraEnviar,
    assinatura: grade.assinaturaAtual,
    ativo: editavel && !administracao && Boolean(contexto),
    salvar: linhas => salvarLinhas.mutateAsync({ id, linhas }),
  })

  // --- as deduções e o seu autosave ----------------------------------------
  const deducoes = useDeducoes(m?.deducoes)
  const salvarDeducoes = useSalvarDeducoes(contrato)
  const autosaveDeducoes = useAutosave({
    valor: deducoes.paraEnviar,
    assinatura: deducoes.assinatura,
    ativo: editavel && Boolean(m),
    salvar: linhas => salvarDeducoes.mutateAsync({ id, deducoes: linhas }),
  })

  // --- o cabeçalho (custo do regime de administração) ----------------------
  const [custo, setCusto] = useState(0)
  const [custoPronto, setCustoPronto] = useState(false)
  useEffect(() => {
    if (m && !custoPronto) {
      setCusto(apiDecimalToCents(m.custo_reembolsavel))
      setCustoPronto(true)
    }
  }, [m, custoPronto])
  const salvarCabecalho = useSalvarCabecalho(contrato)
  const autosaveCusto = useAutosave({
    valor: custo,
    assinatura: String(custo),
    ativo: editavel && administracao && custoPronto,
    salvar: v => salvarCabecalho.mutateAsync({
      id, custo_reembolsavel: centsToApiDecimal(v),
    }),
  })

  const submeter = useSubmeterMedicao(contrato)
  const atestar = useAtestarMedicao(contrato)
  const retificar = useRetificarMedicao(contrato)
  const cancelar = useCancelarMedicao(contrato)
  const excluir = useExcluirMedicao(contrato)

  const pendente = useMemo(
    () => [autosaveGrade, autosaveDeducoes, autosaveCusto]
      .some(a => a.estado === 'pendente' || a.estado === 'salvando' || a.estado === 'erro'),
    [autosaveGrade, autosaveDeducoes, autosaveCusto],
  )

  const voltar = `/app/pdca/obra/${obraId}/contratos/${contratoId}`

  async function comErro<T>(acao: () => Promise<T>): Promise<T | undefined> {
    setErro(null)
    try { return await acao() } catch (e) {
      const campos = parseApiErrors(e)
      setErro(Object.values(campos).join(' · ') || 'Não deu para concluir.')
      return undefined
    }
  }

  if (medicao.isLoading || contratoQ.isLoading) return <Loading o="a medição" />
  if (!m || !c) return <Empty>Medição não encontrada.</Empty>

  return (
    <div style={{ padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Link
        to={voltar}
        className="sem-impressao"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--ink-3)', fontSize: 13, textDecoration: 'none' }}
      >
        <ArrowLeft size={14} /> Contrato {c.numero}
      </Link>

      {erro && <Faixa tom="danger">{erro}</Faixa>}
      {avisos.length > 0 && (
        <Faixa tom="accent">
          {avisos.map((a, i) => <div key={i}>{a}</div>)}
        </Faixa>
      )}

      {/* --- Modo BOLETIM: o documento congelado ------------------------- */}
      {!rascunho ? (
        <>
          <Card>
            <BoletimDeMedicao medicao={m} contrato={c} contexto={contexto} />
          </Card>

          <div className="sem-impressao" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            {m.status === 'em_aprovacao' && podeAtestar && (
              <>
                <BotaoReprovar
                  onConfirmar={motivo => comErro(() => atestar.mutateAsync({
                    id, aprovar: false, observacao: motivo,
                  }))}
                />
                <Btn
                  variant="brand"
                  onClick={() => comErro(() => atestar.mutateAsync({ id, aprovar: true }))}
                >
                  <CheckCircle2 size={15} /> Atestar
                </Btn>
              </>
            )}
            {m.status === 'em_aprovacao' && podeApurar && (
              <Btn onClick={() => comErro(() => cancelar.mutateAsync({ id }))}>
                Cancelar medição
              </Btn>
            )}
            {m.status === 'aprovada' && podeApurar && (
              <BotaoRetificar
                onConfirmar={motivo => comErro(() => retificar.mutateAsync({ id, motivo }))
                  .then(nova => {
                    if (nova) navegar(`${voltar}/medicoes/${nova.medicao_id}`)
                  })}
              />
            )}
          </div>
        </>
      ) : (
        /* --- Modo APURAR: a grade viva ---------------------------------- */
        <>
          <Card>
            <div style={{
              display: 'flex', justifyContent: 'space-between', gap: 16,
              flexWrap: 'wrap', alignItems: 'flex-start',
            }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <h1 style={{ margin: 0, fontSize: 20 }}>Medição {m.numero}</h1>
                  <Pill kind={CORES_MEDICAO[m.status]}>{m.status_rotulo}</Pill>
                  {m.retifica != null && (
                    <Pill kind="accent">retifica a medição {m.retifica}</Pill>
                  )}
                </div>
                <p style={{ margin: '5px 0 0', fontSize: 13, color: 'var(--ink-2)' }}>
                  {data(m.periodo_inicio)} a {data(m.periodo_fim)} ·{' '}
                  {c.fornecedor_nome} · {c.regime_rotulo}
                </p>
              </div>
              <SeloDeSalvamento
                estados={[autosaveGrade, autosaveDeducoes, autosaveCusto]}
              />
            </div>

            {m.retifica != null && (
              <p style={{
                margin: '12px 0 0', fontSize: 12.5, color: 'var(--ink-2)',
                background: 'var(--surface-2)', padding: '9px 11px', borderRadius: 8,
              }}>
                <strong>Esta é uma retificadora e nasceu vazia.</strong> Lance só as
                linhas que mudam, com a <strong>diferença</strong> — negativa para
                devolver quantidade medida a mais. O que você digitar aqui soma ao
                que a medição original pagou.
              </p>
            )}
          </Card>

          {administracao ? (
            <Card>
              <h2 style={{ margin: '0 0 4px', fontSize: 15 }}>Custo do período</h2>
              <p style={{ margin: '0 0 12px', fontSize: 13, color: 'var(--ink-2)', maxWidth: 620 }}>
                Quanto a obra custou de{' '}
                {data(m.periodo_inicio)} a {data(m.periodo_fim)} — mão de obra,
                material e equipamento que este contrato manda reembolsar. Confira
                com a folha, as notas e o material aplicado no período.
                {m.taxa_administracao_aplicada != null && (
                  <> Sobre esse valor entra a taxa de{' '}
                    {Number(m.taxa_administracao_aplicada)}%.</>
                )}
              </p>
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div style={{ width: 200 }}>
                  <label style={rotulo}>Custo reembolsável</label>
                  <CampoMoeda centavos={custo} aoMudar={setCusto} disabled={!editavel} />
                </div>
                <div>
                  <label style={rotulo}>Taxa de administração</label>
                  <div style={{ fontFamily: 'var(--mono)', fontSize: 15, padding: '7px 0' }}>
                    {Number(m.taxa_administracao_aplicada ?? 0)}%
                  </div>
                </div>
                <div>
                  <label style={rotulo}>Bruto</label>
                  <div style={{ fontFamily: 'var(--mono)', fontSize: 17, padding: '4px 0', color: 'var(--brand)' }}>
                    {dinheiro(m.totais.bruto)}
                  </div>
                </div>
              </div>
            </Card>
          ) : (
            <Card>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end',
                gap: 12, flexWrap: 'wrap', marginBottom: 12,
              }}>
                <div>
                  <h2 style={{ margin: 0, fontSize: 15 }}>Grade da medição</h2>
                  <p style={{ margin: '3px 0 0', fontSize: 12.5, color: 'var(--ink-3)', maxWidth: 560 }}>
                    O contrato inteiro aparece aqui de propósito: "não medi isto"
                    precisa ser uma decisão visível, e não uma linha que sumiu.
                  </p>
                </div>
              </div>

              {contextoQ.isLoading ? (
                <Loading o="a grade" />
              ) : (
                <GradeDeMedicao
                  linhas={contexto?.linhas ?? []}
                  valores={grade.valores}
                  onMudar={grade.mudar}
                  totais={m.totais}
                  somenteLeitura={!editavel}
                  mostrarEstoque
                  onVerMemoria={setMemoria}
                  acaoVazia={
                    <Btn variant="brand" onClick={() => navegar(voltar)}>
                      <ListPlus size={15} /> Cadastrar a planilha contratual
                    </Btn>
                  }
                />
              )}
            </Card>
          )}

          <Card>
            <h2 style={{ margin: '0 0 4px', fontSize: 15 }}>Deduções</h2>
            <p style={{ margin: '0 0 12px', fontSize: 12.5, color: 'var(--ink-3)', maxWidth: 640 }}>
              O que sai do bruto e <strong>não volta</strong>: imposto retido,
              amortização de adiantamento, multa. A retenção contratual não entra
              aqui — ela é cláusula do contrato e volta pela liberação de retenção.
            </p>
            <PainelDeDeducoes
              linhas={deducoes.linhas}
              setLinhas={deducoes.setLinhas}
              totais={m.totais}
              somenteLeitura={!editavel}
            />
          </Card>

          {editavel && (
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
              <Btn
                onClick={() => comErro(() => excluir.mutateAsync(id)).then(() => navegar(voltar))}
              >
                <Trash2 size={14} /> Descartar
              </Btn>
              <Btn onClick={() => { void autosaveGrade.salvarAgora(); void autosaveDeducoes.salvarAgora() }}>
                <Save size={14} /> Salvar agora
              </Btn>
              <Btn
                variant="brand"
                disabled={grade.temExcesso || submeter.isPending}
                title={grade.temExcesso ? 'Há linhas acima do saldo contratado.' : undefined}
                onClick={async () => {
                  // **Grava antes de submeter.** É a correção do defeito que
                  // deu origem a esta tela: submeter mandava só o id, e o
                  // documento era aprovado com os números anteriores.
                  const ok = await Promise.all([
                    autosaveGrade.salvarAgora(),
                    autosaveDeducoes.salvarAgora(),
                    autosaveCusto.salvarAgora(),
                  ])
                  if (ok.some(v => !v)) {
                    setErro('A gravação não terminou — não dá para submeter o que não está salvo.')
                    return
                  }
                  const r = await comErro(() => submeter.mutateAsync({ id }))
                  if (r) setAvisos(r.avisos)
                }}
              >
                <Send size={15} /> Submeter
              </Btn>
            </div>
          )}
        </>
      )}

      {memoria && (
        <MemoriaDeCalculo
          linha={memoria}
          obraId={Number(obraId)}
          cronogramaId={cronogramas.data?.results?.[0]?.cronograma_id}
          onClose={() => setMemoria(null)}
          observacao={grade.valores[memoria.item_contrato_id]?.observacao ?? ''}
          onObservacao={
            editavel
              ? texto => grade.mudar(memoria.item_contrato_id, 'observacao', texto)
              : undefined
          }
        />
      )}

      {pendente && (
        <div style={{ height: 1 }} aria-hidden />
      )}
    </div>
  )
}

/** O selo de gravação. **Sempre visível**: uma tela que só avisa quando falha
 *  deixa a pessoa sem saber se o silêncio é bom. */
function SeloDeSalvamento({ estados }: { estados: ReturnType<typeof useAutosave>[] }) {
  const pior = estados.find(e => e.estado === 'erro')
    ?? estados.find(e => e.estado === 'salvando')
    ?? estados.find(e => e.estado === 'pendente')
    ?? estados.find(e => e.estado === 'salvo')
    ?? estados[0]
  const cor = pior.estado === 'erro' ? 'var(--danger-ink)'
    : pior.estado === 'pendente' ? 'var(--accent-ink)' : 'var(--ink-3)'
  const Icone = pior.estado === 'erro' ? CloudOff
    : pior.estado === 'salvando' ? CircleDot : Cloud
  return (
    <div
      className="sem-impressao"
      title="A grade grava sozinha quando você para de digitar. Submeter grava antes de enviar."
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: cor }}
    >
      <Icone size={14} />
      {rotuloDoSalvamento(pior)}
    </div>
  )
}

function BotaoRetificar({ onConfirmar }: { onConfirmar: (motivo: string) => void }) {
  const [aberto, setAberto] = useState(false)
  const [motivo, setMotivo] = useState('')
  return (
    <>
      <Btn onClick={() => setAberto(true)}><RotateCcw size={14} /> Retificar</Btn>
      {aberto && (
        <Modal
          titulo="Retificar medição"
          onClose={() => setAberto(false)}
          rodape={
            <>
              <Btn onClick={() => setAberto(false)}>Cancelar</Btn>
              <Btn
                variant="brand"
                disabled={!motivo.trim()}
                onClick={() => { onConfirmar(motivo); setAberto(false) }}
              >
                Abrir retificadora
              </Btn>
            </>
          }
        >
          <p style={{ fontSize: 13, color: 'var(--ink-2)', marginTop: 0 }}>
            Medição aprovada não se edita — a correção é um documento novo que
            aponta para ela. A retificadora <strong>nasce vazia</strong>: você
            lança só as linhas que mudam, com a diferença (negativa para devolver
            quantidade medida a mais).
          </p>
          <label style={rotulo}>Motivo</label>
          <textarea
            value={motivo}
            onChange={e => setMotivo(e.target.value)}
            rows={3}
            placeholder="Ex.: o item 1.1 mediu 300 m² e a conferência em campo apurou 250 m²."
            style={{ ...campo, resize: 'vertical' }}
          />
        </Modal>
      )}
    </>
  )
}

function BotaoReprovar({ onConfirmar }: { onConfirmar: (motivo: string) => void }) {
  const [aberto, setAberto] = useState(false)
  const [motivo, setMotivo] = useState('')
  return (
    <>
      <Btn variant="perigo" onClick={() => setAberto(true)}>Reprovar</Btn>
      {aberto && (
        <Modal
          titulo="Reprovar medição"
          onClose={() => setAberto(false)}
          rodape={
            <>
              <Btn onClick={() => setAberto(false)}>Voltar</Btn>
              <Btn
                variant="perigo"
                disabled={!motivo.trim()}
                onClick={() => { onConfirmar(motivo); setAberto(false) }}
              >
                Reprovar
              </Btn>
            </>
          }
        >
          <p style={{ fontSize: 13, color: 'var(--ink-2)', marginTop: 0 }}>
            <strong>Diga por quê.</strong> Reprovar devolve o documento a quem o
            montou; sem o motivo, ele volta com o mesmo problema — e a reprovação
            fica registrada na escada sem explicar nada a quem a ler depois.
          </p>
          <label style={rotulo}>Motivo</label>
          <textarea
            value={motivo}
            onChange={e => setMotivo(e.target.value)}
            rows={3}
            placeholder="Ex.: o item 3.2 mede 400 m² e o diário registra 280 m² executados."
            style={{ ...campo, resize: 'vertical' }}
          />
        </Modal>
      )}
    </>
  )
}

function Faixa({ tom, children }: { tom: 'danger' | 'accent'; children: React.ReactNode }) {
  return (
    <div
      className="sem-impressao"
      style={{
        padding: '10px 12px', borderRadius: 8, fontSize: 13,
        display: 'flex', gap: 8, alignItems: 'flex-start',
        background: tom === 'danger' ? 'var(--danger-soft)' : 'var(--accent-soft)',
        color: tom === 'danger' ? 'var(--danger-ink)' : 'var(--accent-ink)',
      }}
    >
      <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 2 }} />
      <div>{children}</div>
    </div>
  )
}

const data = (v: string) => v.split('-').reverse().join('/')
const dinheiro = (v: string | number | null | undefined) =>
  v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const rotulo: React.CSSProperties = {
  display: 'block', fontSize: 11.5, color: 'var(--ink-3)', marginBottom: 4,
}
const campo: React.CSSProperties = {
  width: '100%', padding: '8px 10px', borderRadius: 8,
  border: '1px solid var(--line)', background: 'var(--surface)',
  color: 'var(--ink)', fontSize: 13.5,
}
