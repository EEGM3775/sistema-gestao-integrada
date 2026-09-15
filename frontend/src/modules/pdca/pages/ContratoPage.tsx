import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft, Banknote, CalendarClock, FilePlus2, HandCoins, Pencil, Receipt,
  ScrollText, Wallet,
} from 'lucide-react'
import { Btn, CampoMoeda, Card, Empty, Loading, Modal, Num, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { apiDecimalToCents, centsToApiDecimal } from '@/utils/money'
import { parseApiErrors } from '@/utils/formErrors'
import {
  useContrato, useItensDoContrato, useLiberacoes, useLiberarRetencao,
  useMedicoes, useObras, useSaldoDoContrato,
} from '../hooks'
import PlanilhaContratual from '../components/PlanilhaContratual'
import PainelAditivos from '../components/PainelAditivos'
import { ModalContrato } from '../components/FormContrato'
import { CORES_MEDICAO } from '../components/cores'
import type { Medicao } from '../types'

/**
 * **O cockpit do contrato — onde se decide, não onde se digita.**
 *
 * A primeira escrita desta página fazia tudo numa rolagem só: planilha
 * contratual, prévia editável, grade da medição aberta, histórico e retenção,
 * 740 linhas. A medição não tinha endereço — era um `?medicao=` que
 * reconfigurava um card no meio da tela —, e a grade montava saldo no navegador
 * a partir de uma prévia que nem sempre existia (ver a nota da `MedicaoPage`).
 *
 * Agora esta tela responde três perguntas, e só elas:
 *
 * 1. **quanto vale este contrato hoje** — contratado original, aditivos,
 *    medido nas três faixas, saldo e retenção;
 * 2. **o que espera decisão** — a fila, no topo, porque é o que traz o gestor
 *    aqui (régua do frontend §1.6);
 * 3. **o que já aconteceu** — medições, aditivos e liberações, cada um com
 *    endereço próprio para abrir.
 *
 * Medir é na `PreviaDeMedicaoPage` e na `MedicaoPage`. Uma tela, um gesto.
 */

const dinheiro = (v: string | number | null | undefined) =>
  v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const hoje = () => new Date().toISOString().slice(0, 10)
const data = (v: string) => v.split('-').reverse().join('/')

export default function ContratoPage() {
  const { contratoId, obraId } = useParams()
  const id = Number(contratoId)
  const navegar = useNavigate()
  const { hasPermission } = useAuth()
  const podeApurar = hasPermission('pdca.medicao.apurar')
  const podeAtestar = hasPermission('pdca.medicao.atestar')
  const podeEditar = hasPermission('pdca.contrato.edit')

  const [params] = useSearchParams()
  const [editando, setEditando] = useState(false)
  const [liberando, setLiberando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  const obras = useObras()
  const contrato = useContrato(id)
  const itens = useItensDoContrato(id)
  const saldo = useSaldoDoContrato(id)
  const medicoes = useMedicoes({ contrato: id })
  const liberacoes = useLiberacoes({ contrato: id })
  const liberar = useLiberarRetencao(id)

  const base = `/app/pdca/obra/${obraId}/contratos/${contratoId}`

  /**
   * **O endereço antigo continua funcionando.** `?medicao=14` era o link que o
   * gestor colava no grupo da obra; ele agora leva ao documento, em vez de
   * reconfigurar um card no meio desta tela.
   *
   * A dependência é a **string**, não o objeto de `useSearchParams`: o React
   * Router devolve uma instância nova a cada renderização, e depender dela
   * fazia o efeito rodar sempre — `navigate` a cada render, renderização a cada
   * `navigate`. A aba travava (31 requisições em 5 s na reprodução), que é o
   * "trava tudo" que o dono viu.
   */
  const medicaoNaUrl = params.get('medicao')
  useEffect(() => {
    if (medicaoNaUrl) navegar(`${base}/medicoes/${medicaoNaUrl}`, { replace: true })
  }, [medicaoNaUrl, base, navegar])

  if (contrato.isLoading || itens.isLoading) return <Loading o="o contrato" />
  if (!contrato.data) return <Empty>Contrato não encontrado.</Empty>

  const c = contrato.data
  const vigente = c.status === 'vigente'
  const lista = medicoes.data?.results ?? []
  const s = saldo.data

  const esperandoAtesto = lista.filter(m => m.status === 'em_aprovacao')
  const rascunhos = lista.filter(m => m.status === 'rascunho')
  const liberavel = s ? Number(s.retencao.disponivel) : 0

  async function comErro<T>(acao: () => Promise<T>) {
    setErro(null)
    try { return await acao() } catch (e) {
      setErro(Object.values(parseApiErrors(e)).join(' · ') || 'Não deu para concluir.')
      return undefined
    }
  }

  return (
    <div style={{ padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Link
        to={`/app/pdca/obra/${obraId}/contratos`}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--ink-3)', fontSize: 13, textDecoration: 'none' }}
      >
        <ArrowLeft size={14} /> Contratos da obra
      </Link>

      {/* --- Cabeçalho: o contrato e o saldo derivado --------------------- */}
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <h1 style={{ margin: 0, fontSize: 21 }}>{c.numero}</h1>
              <Pill kind={vigente ? 'good' : 'slate'}>{c.status_rotulo}</Pill>
              <Pill kind="info">{c.regime_rotulo}</Pill>
              {c.regime_publico && (
                <Pill kind="info">
                  Público{c.limite_acrescimo_percentual ? ` · até +${Number(c.limite_acrescimo_percentual)}%` : ''}
                </Pill>
              )}
            </div>
            <p style={{ margin: '6px 0 0', color: 'var(--ink-2)', fontSize: 13.5 }}>
              {c.fornecedor_nome} · {c.obra_nome}
            </p>
            <p style={{ margin: '3px 0 0', color: 'var(--ink-3)', fontSize: 12.5, maxWidth: 640 }}>
              {c.objeto}
            </p>
            <p style={{ margin: '3px 0 0', color: 'var(--ink-3)', fontSize: 12.5 }}>
              Vigência {data(c.data_inicio)}
              {c.data_fim ? ` a ${data(c.data_fim)}` : ' · sem fim definido'}
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', flexWrap: 'wrap' }}>
            {podeApurar && vigente && (
              <Btn variant="brand" onClick={() => navegar(`${base}/previa`)}>
                <FilePlus2 size={15} /> Medir período
              </Btn>
            )}
            {podeEditar && (
              <Btn onClick={() => setEditando(true)}><Pencil size={14} /> Editar</Btn>
            )}
          </div>
        </div>

        {s && (
          <div style={{
            display: 'flex', gap: 26, flexWrap: 'wrap', marginTop: 16, paddingTop: 14,
            borderTop: '1px solid var(--line)',
          }}>
            <Cifra
              rotulo="Contratado"
              valor={dinheiro(s.valor_contratado)}
              nota={
                Number(s.valor_aditivado) !== 0
                  ? `${dinheiro(s.valor_original)} + ${dinheiro(s.valor_aditivado)} de aditivo`
                  : undefined
              }
            />
            <Cifra rotulo="Medido e aprovado" valor={dinheiro(s.medido_aprovado)} />
            {Number(s.medido_em_aprovacao) > 0 && (
              <Cifra
                rotulo="Na escada"
                valor={dinheiro(s.medido_em_aprovacao)}
                nota="Já ocupa saldo do contrato"
              />
            )}
            {Number(s.medido_rascunho) > 0 && (
              <Cifra
                rotulo="Em rascunho"
                valor={dinheiro(s.medido_rascunho)}
                nota="Não ocupa saldo — é intenção"
                atenuada
              />
            )}
            {Number(s.material_estocado) > 0 && (
              <Cifra
                rotulo="Material na obra"
                valor={dinheiro(s.material_estocado)}
                nota="Pago e ainda não aplicado"
                atenuada
              />
            )}
            <Cifra rotulo="Saldo" valor={dinheiro(s.saldo)} forte />
            <Cifra
              rotulo="Itens fechados"
              valor={`${s.itens_fechados} / ${s.itens}`}
            />
          </div>
        )}
      </Card>

      {erro && (
        <div style={{
          padding: '10px 12px', borderRadius: 8, fontSize: 13,
          background: 'var(--danger-soft)', color: 'var(--danger-ink)',
        }}>
          {erro}
        </div>
      )}

      {/* --- A fila de decisão -------------------------------------------
          Vem antes de tudo porque é o que traz o gestor a esta tela. Cada item
          é um link para o lugar onde a decisão acontece — a régua do §1.6: o
          cockpit não informa, ele encaminha. */}
      {(esperandoAtesto.length > 0 || rascunhos.length > 0
        || (liberavel > 0 && podeAtestar) || (s?.aditivos_abertos ?? 0) > 0
        || (s?.periodo_sugerido && vigente && podeApurar)) && (
        <Card>
          <h2 style={{ margin: '0 0 10px', fontSize: 15 }}>Esperando decisão</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {esperandoAtesto.map(m => (
              <ItemDaFila
                key={m.medicao_id}
                tom="info"
                onIr={() => navegar(`${base}/medicoes/${m.medicao_id}`)}
                titulo={`Medição ${m.numero} espera atesto`}
                detalhe={`${data(m.periodo_inicio)}–${data(m.periodo_fim)} · ${
                  dinheiro(m.totais.liquido)}${
                  m.escada?.nivel ? ` · parada em ${m.escada.nivel}` : ''}`}
                acao={podeAtestar ? 'Atestar' : 'Ver'}
              />
            ))}
            {rascunhos.map(m => (
              <ItemDaFila
                key={m.medicao_id}
                tom="slate"
                onIr={() => navegar(`${base}/medicoes/${m.medicao_id}`)}
                titulo={`Medição ${m.numero} em rascunho`}
                detalhe={`${data(m.periodo_inicio)}–${data(m.periodo_fim)} · ainda não submetida`}
                acao="Continuar"
              />
            ))}
            {(s?.aditivos_abertos ?? 0) > 0 && (
              <ItemDaFila
                tom="accent"
                titulo={`${s?.aditivos_abertos} aditivo(s) em aberto`}
                detalhe="Aditivo não move saldo nenhum enquanto não é aprovado"
                acao="Ver abaixo"
              />
            )}
            {liberavel > 0 && podeAtestar && (
              <ItemDaFila
                tom="good"
                onIr={() => setLiberando(true)}
                titulo={`${dinheiro(liberavel)} de retenção disponíveis`}
                detalhe={c.retencao_condicao_liberacao || 'Sem condição escrita no contrato'}
                acao="Liberar"
              />
            )}
            {s?.periodo_sugerido && vigente && podeApurar && rascunhos.length === 0 && (
              <ItemDaFila
                tom="brand"
                onIr={() => navegar(`${base}/previa`)}
                titulo="Próximo período a medir"
                detalhe={`${data(s.periodo_sugerido.inicio)} a ${data(s.periodo_sugerido.fim)}${
                  s.periodo_sugerido.ultima_medicao
                    ? ` · segue a medição ${s.periodo_sugerido.ultima_medicao.numero}`
                    : ' · primeira medição deste contrato'}`}
                acao="Medir"
              />
            )}
          </div>
        </Card>
      )}

      <div style={{ display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))' }}>
        {/* --- Medições --------------------------------------------------- */}
        <Card>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <ScrollText size={15} style={{ color: 'var(--ink-3)' }} />
            <h2 style={{ margin: 0, fontSize: 15 }}>Medições</h2>
            <span style={{ color: 'var(--ink-3)', fontSize: 12.5 }}>{lista.length}</span>
          </div>
          {lista.length === 0 ? (
            <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>
              Nenhuma medição ainda.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {lista.map(m => (
                <LinhaMedicao
                  key={m.medicao_id}
                  medicao={m}
                  onAbrir={() => navegar(`${base}/medicoes/${m.medicao_id}`)}
                />
              ))}
            </div>
          )}
        </Card>

        {/* --- Retenção -------------------------------------------------- */}
        <Card>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <HandCoins size={15} style={{ color: 'var(--ink-3)' }} />
            <h2 style={{ margin: 0, fontSize: 15 }}>Retenção</h2>
            {Number(c.retencao_percentual) > 0 && (
              <Pill kind="info">
                {Number(c.retencao_percentual)}% · {c.retencao_natureza_rotulo}
              </Pill>
            )}
          </div>

          {Number(c.retencao_percentual) === 0 ? (
            <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>
              Este contrato não retém nada.
            </p>
          ) : (
            <>
              {s && (
                <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', marginBottom: 12 }}>
                  <Cifra rotulo="Retido" valor={dinheiro(s.retencao.retido)} />
                  <Cifra rotulo="Já liberado" valor={dinheiro(s.retencao.liberado)} atenuada />
                  <Cifra rotulo="Disponível" valor={dinheiro(s.retencao.disponivel)} forte />
                </div>
              )}
              {c.retencao_condicao_liberacao && (
                <p style={{
                  fontSize: 12.5, color: 'var(--ink-2)', background: 'var(--surface-2)',
                  padding: '8px 10px', borderRadius: 8, margin: '0 0 12px',
                }}>
                  <strong>Libera quando:</strong> {c.retencao_condicao_liberacao}
                </p>
              )}

              {(liberacoes.data ?? []).length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 12 }}>
                  {(liberacoes.data ?? []).map(l => (
                    <div key={l.liberacao_id} style={{
                      display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5,
                      padding: '6px 8px', border: '1px solid var(--line)', borderRadius: 7,
                    }}>
                      <Pill kind={CORES_MEDICAO[l.status]}>{l.status_rotulo}</Pill>
                      <span style={{ color: 'var(--ink-2)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {l.condicao_atendida}
                      </span>
                      <Num>{dinheiro(l.valor)}</Num>
                    </div>
                  ))}
                </div>
              )}

              {podeAtestar && liberavel > 0 && (
                <Btn onClick={() => setLiberando(true)}>
                  <Wallet size={14} /> Liberar retenção
                </Btn>
              )}
            </>
          )}
        </Card>
      </div>

      {c.regime === 'administracao' && (
        <Card>
          <h2 style={{ margin: '0 0 6px', fontSize: 15 }}>
            Como este contrato é medido
          </h2>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--ink-2)', maxWidth: 680 }}>
            <strong>Por administração:</strong> a cada período você informa{' '}
            <strong>quanto a obra custou</strong> — mão de obra, material e
            equipamento — e o empreiteiro recebe isso mais a taxa
            {c.taxa_administracao ? ` de ${Number(c.taxa_administracao)}%` : ''}.
            A planilha abaixo serve de <strong>referência de custo</strong>: ela
            não é medida linha a linha.
          </p>
          <p style={{ margin: '8px 0 0', fontSize: 12.5, color: 'var(--ink-3)', maxWidth: 680 }}>
            Se o combinado é pagar por <strong>quantidade executada</strong>, o
            regime deste contrato é <strong>preço unitário</strong> — troque em
            "Editar" enquanto não houver medição aprovada, e a grade de medição
            aparece.
          </p>
        </Card>
      )}

      {/* --- Aditivos ---------------------------------------------------- */}
      <Card>
        <PainelAditivos
          contratoId={id}
          itens={itens.data ?? []}
          contratoEditavel={c.status !== 'encerrado' && c.status !== 'cancelado'}
        />
      </Card>

      {/* --- A planilha contratual ---------------------------------------
          É a régua do contrato, e fica por último: depois do primeiro aditivo,
          quem manda na quantidade é ele, não esta tabela. */}
      <Card>
        <PlanilhaContratual
          contratoId={id}
          obraId={Number(obraId)}
          itens={itens.data ?? []}
          regime={c.regime}
          valorGlobal={c.valor_global}
          editavel={c.planilha_editavel}
          podeEditar={podeEditar}
        />
        {/* **A régua é do servidor.** Ela fecha quando alguém já mediu contra a
            planilha — e não quando o contrato sai do rascunho, que foi a
            primeira tentativa desta trava e deixou contrato vigente sem itens
            impossível de preencher. */}
        {!c.planilha_editavel && (
          <p style={{
            margin: '10px 0 0', fontSize: 12.5, color: 'var(--ink-2)',
            background: 'var(--surface-2)', padding: '9px 11px', borderRadius: 8,
            display: 'flex', gap: 7, alignItems: 'flex-start',
          }}>
            <CalendarClock size={14} style={{ flexShrink: 0, marginTop: 1, color: 'var(--ink-3)' }} />
            <span>{c.planilha_fechada_porque}</span>
          </p>
        )}
        {c.planilha_editavel && c.status !== 'rascunho' && (
          <p style={{ margin: '10px 0 0', fontSize: 12, color: 'var(--ink-3)' }}>
            A planilha ainda se edita porque nenhuma medição foi feita contra
            ela. Depois da primeira, mudar quantidade, preço ou incluir item
            passa a ser <strong>aditivo</strong>.
          </p>
        )}
      </Card>

      {editando && (
        <ModalContrato
          obras={obras.data ?? []}
          contrato={c}
          onClose={() => setEditando(false)}
          onPronto={() => setEditando(false)}
        />
      )}

      {liberando && s && (
        <ModalLiberacao
          disponivel={s.retencao.disponivel}
          condicao={c.retencao_condicao_liberacao}
          onClose={() => setLiberando(false)}
          onConfirmar={async (valor, quando, condicao) => {
            const ok = await comErro(() => liberar.mutateAsync({
              valor, data: quando, condicao_atendida: condicao,
            }))
            if (ok) setLiberando(false)
          }}
        />
      )}
    </div>
  )
}

function ItemDaFila({ titulo, detalhe, acao, tom, onIr }: {
  titulo: string
  detalhe: string
  acao: string
  tom: 'info' | 'good' | 'accent' | 'slate' | 'brand'
  onIr?: () => void
}) {
  const cor = {
    info: 'var(--accent-ink)', good: 'var(--good-ink)', accent: 'var(--accent-ink)',
    slate: 'var(--ink-3)', brand: 'var(--brand)',
  }[tom]
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
      padding: '9px 11px', borderRadius: 9,
      border: '1px solid var(--line)', borderLeft: `3px solid ${cor}`,
    }}>
      <div style={{ flex: 1, minWidth: 180 }}>
        <div style={{ fontSize: 13.5, fontWeight: 500 }}>{titulo}</div>
        <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>{detalhe}</div>
      </div>
      {onIr && <Btn tam="sm" onClick={onIr}>{acao}</Btn>}
    </div>
  )
}

function LinhaMedicao({ medicao, onAbrir }: { medicao: Medicao; onAbrir: () => void }) {
  return (
    <button
      onClick={onAbrir}
      style={{
        display: 'flex', alignItems: 'center', gap: 10, textAlign: 'left',
        padding: '8px 10px', borderRadius: 8, cursor: 'pointer', width: '100%',
        border: '1px solid var(--line)', background: 'var(--surface)',
        color: 'var(--ink)', fontSize: 13,
      }}
    >
      <span style={{ fontWeight: 600, fontFamily: 'var(--mono)' }}>#{medicao.numero}</span>
      <Pill kind={CORES_MEDICAO[medicao.status]}>{medicao.status_rotulo}</Pill>
      <span style={{ color: 'var(--ink-3)', fontSize: 12 }}>
        {data(medicao.periodo_inicio)} – {data(medicao.periodo_fim)}
      </span>
      <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
        {/* O título do ERP aparece como leitura — o PDCA não paga (§7). */}
        {medicao.conta_pagar_ref && (
          <span
            title={`Gerou o título ${medicao.conta_pagar_ref} no financeiro. Quem decide quando o dinheiro sai é o ERP.`}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 3, color: 'var(--good-ink)', fontSize: 11.5 }}
          >
            <Receipt size={12} /> {medicao.conta_pagar_ref}
          </span>
        )}
        <Num>{dinheiro(medicao.totais.liquido)}</Num>
      </span>
    </button>
  )
}

function ModalLiberacao({ disponivel, condicao, onClose, onConfirmar }: {
  disponivel: string
  condicao: string
  onClose: () => void
  onConfirmar: (valor: string, data: string, condicao: string) => void
}) {
  // Centavos inteiros, como todo dinheiro da casa (`utils/money.ts`). Nasce com
  // o saldo cheio: liberar tudo é o caso comum, e digitar o número de novo só
  // acrescenta uma chance de errar.
  const [centavos, setCentavos] = useState(apiDecimalToCents(disponivel))
  const [quando, setQuando] = useState(hoje())
  const [texto, setTexto] = useState('')
  const acima = centavos > apiDecimalToCents(disponivel)

  return (
    <Modal
      titulo="Liberar retenção"
      onClose={onClose}
      rodape={
        <>
          <Btn onClick={onClose}>Cancelar</Btn>
          <Btn
            variant="brand"
            disabled={!texto.trim() || acima || centavos <= 0}
            onClick={() => onConfirmar(centsToApiDecimal(centavos), quando, texto)}
          >
            <Banknote size={15} /> Solicitar liberação
          </Btn>
        </>
      }
    >
      <p style={{ fontSize: 13, color: 'var(--ink-2)', marginTop: 0 }}>
        Disponível: <strong>{dinheiro(disponivel)}</strong>. A liberação sobe uma
        escada de atesto própria — quem ateste medição confere serviço executado;
        quem libera caução confere <strong>condição contratual cumprida</strong>.
      </p>
      {condicao && (
        <p style={{
          fontSize: 12.5, color: 'var(--ink-2)', background: 'var(--surface-2)',
          padding: '8px 10px', borderRadius: 8,
        }}>
          <strong>A cláusula deste contrato diz:</strong> {condicao}
        </p>
      )}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <label style={rotuloCampo}>Valor</label>
          <CampoMoeda centavos={centavos} aoMudar={setCentavos} />
          {acima && (
            <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--danger-ink)' }}>
              Acima do disponível.
            </p>
          )}
        </div>
        <div style={{ flex: 1 }}>
          <label style={rotuloCampo}>Data</label>
          <input type="date" value={quando} onChange={e => setQuando(e.target.value)} style={campoModal} />
        </div>
      </div>
      <label style={rotuloCampo}>Condição atendida</label>
      <textarea
        value={texto}
        onChange={e => setTexto(e.target.value)}
        rows={3}
        placeholder="Declare o que foi cumprido — ex.: obra recebida definitivamente em 20/12/2026, termo anexo."
        style={{ ...campoModal, resize: 'vertical' }}
      />
      <p style={{ margin: '5px 0 0', fontSize: 12, color: 'var(--ink-3)' }}>
        Valor liberado sem a condição escrita é exatamente o que uma auditoria de
        contrato registra como achado.
      </p>
    </Modal>
  )
}

const rotuloCampo: React.CSSProperties = {
  display: 'block', fontSize: 12.5, color: 'var(--ink-2)', marginBottom: 4,
}
const campoModal: React.CSSProperties = {
  width: '100%', padding: '8px 10px', borderRadius: 8,
  border: '1px solid var(--line)', background: 'var(--surface)',
  color: 'var(--ink)', fontSize: 13.5,
}

function Cifra({ rotulo, valor, nota, forte, atenuada }: {
  rotulo: string; valor: string; nota?: string; forte?: boolean; atenuada?: boolean
}) {
  return (
    <div>
      <div style={{ fontSize: 11.5, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '.04em' }}>
        {rotulo}
      </div>
      <div style={{
        fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
        fontSize: forte ? 20 : 15.5, fontWeight: forte ? 600 : 500,
        // `--brand`, e **não** `--brand-ink`: o segundo é `#FFFFFF` — a tinta
        // para usar *sobre* a cor da marca, não uma tinta da marca. Usá-lo aqui
        // pintava de branco, sobre superfície clara, justamente o número mais
        // importante da tela (o saldo do contrato), deixando-o invisível.
        color: atenuada ? 'var(--ink-3)' : forte ? 'var(--brand)' : 'var(--ink)',
      }}>
        {valor}
      </div>
      {nota && (
        <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 1 }}>{nota}</div>
      )}
    </div>
  )
}
