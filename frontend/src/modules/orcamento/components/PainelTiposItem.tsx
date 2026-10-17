import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Check, Pencil, Plus, Tags, Trash2 } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Aviso, Btn, Card, CAPS, Empty, Field, inp, Loading, Modal, mono, Pill } from '../ui'
import {
  useAtualizarTipoItem, useCriarTipoItem, useNaturezasItem, useRemoverTipoItem, useTiposItem,
} from '../hooks'
import type { FlagsTipoItem, NaturezaComPadroes, NaturezaItem, TipoItemProprio } from '../types'

/** O que cada flag muda, em uma linha — porque marcar caixa que não se entende
 *  é o jeito mais rápido de configurar errado. O texto fala do **efeito no
 *  sistema**, não do nome do campo: "tem saldo no Estoque" diz mais que
 *  "estocável". */
const FLAGS: { chave: keyof FlagsTipoItem; rotulo: string; efeito: string }[] = [
  {
    chave: 'leva_encargo_social', rotulo: 'Leva encargo social',
    efeito: 'A parcela deste item na composição é multiplicada pelo percentual de encargos do orçamento.',
  },
  {
    chave: 'compravel', rotulo: 'Comprável',
    efeito: 'Entra na relação de compra e pode virar demanda no Suprimentos.',
  },
  {
    chave: 'estocavel', rotulo: 'Estocável',
    efeito: 'Tem saldo no Estoque: entra, sai e é contado no inventário.',
  },
  {
    chave: 'consumivel', rotulo: 'Consumível',
    efeito: 'Baixa contra a obra e a etapa quando é aplicado.',
  },
  {
    chave: 'vendavel', rotulo: 'Vendável',
    efeito: 'Pode ser vendido — uso comercial, fora do custo da obra.',
  },
  {
    chave: 'rastreavel', rotulo: 'Rastreável',
    efeito: 'Exige lote e validade em toda movimentação.',
  },
]

/** O que o formulário edita — o tipo salvo traz `tipo_item_id`, o rótulo da
 *  natureza e a contagem de uso, que são do servidor. */
type FormTipo = Omit<TipoItemProprio, 'tipo_item_id' | 'natureza_nome' | 'itens_com_este_tipo'>

const VAZIO: FormTipo = {
  codigo: '', nome: '', descricao: '', natureza: 'material' as NaturezaItem, ativo: true,
  leva_encargo_social: false, compravel: true, estocavel: true,
  vendavel: false, consumivel: true, rastreavel: false,
}

function paraCodigo(nome: string): string {
  return nome.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 30)
}

/** Os tipos de item **da empresa**.
 *
 *  A lista de naturezas é fechada de propósito — ela é o que decide conta
 *  (encargo social incide sobre mão de obra e não sobre material; o que é
 *  comprável entra na relação de compra; o que é estocável tem saldo). O que a
 *  empresa cria é o **nome que ela usa** dizendo de qual natureza aquilo é.
 *
 *  Por isso o formulário pergunta a natureza **primeiro** e já preenche o resto
 *  com o padrão dela: quem não conhece as flags sai com um tipo coerente sem
 *  tocar em nenhuma, e quem conhece ajusta o que precisa. A combinação que não
 *  fecha (encargo social em natureza que não é mão de obra) é bloqueada com o
 *  motivo na tela — no orçamento ela sairia como preço errado, não como erro.
 */
export default function PainelTiposItem() {
  const { hasPermission } = useAuth()
  const podeVer = hasPermission('cadastro.tipo_item.view')
  const podeEditar = hasPermission('cadastro.tipo_item.edit')

  const { data: tipos, isLoading } = useTiposItem(podeVer)
  const { data: naturezas } = useNaturezasItem(podeVer)
  const criar = useCriarTipoItem()
  const atualizar = useAtualizarTipoItem()
  const remover = useRemoverTipoItem()

  const [editando, setEditando] = useState<TipoItemProprio | 'novo' | null>(null)
  const [recado, setRecado] = useState('')

  useEffect(() => {
    if (!recado) return
    const t = setTimeout(() => setRecado(''), 3800)
    return () => clearTimeout(t)
  }, [recado])

  if (!podeVer) {
    return (
      <Empty>
        Você não tem permissão para ver os tipos de item. Definir tipo muda como o sistema calcula
        todos os itens que o usam — é permissão à parte (<b>cadastro.tipo_item</b>), entregue pelo
        administrador da empresa.
      </Empty>
    )
  }

  return (
    <>
      <Aviso>
        <Tags size={15} style={{ flex: 'none', marginTop: 1 }} />
        <span style={{ minWidth: 0 }}>
          As <b>naturezas</b> (material, mão de obra, equipamento, encargos complementares…) são as da
          SINAPI e não se criam: é delas que sai o cálculo — encargo social incide sobre mão de obra e
          sobre mais nada. O que se cria aqui é o <b>nome que a empresa usa</b> — "Andaime locado",
          "Verba de mobilização" — dizendo de qual natureza aquilo é.
        </span>
      </Aviso>

      <div style={{ height: 14 }} />

      {isLoading ? <Loading texto="Carregando os tipos…" /> : !tipos?.length ? (
        <Empty acao={podeEditar
          ? <Btn variant="primary" onClick={() => setEditando('novo')}><Plus size={14} />Criar tipo</Btn>
          : undefined}>
          Nenhum tipo próprio ainda. Os itens seguem as oito naturezas da SINAPI, que já cobrem a
          maioria das obras — crie um tipo só quando o vocabulário da sua empresa precisar de um nome
          que a fonte não tem.
        </Empty>
      ) : (
        <div style={{ display: 'grid', gap: 8 }}>
          {tipos.map(t => (
            <Card key={t.tipo_item_id} style={{ display: 'flex', alignItems: 'center', gap: 13, padding: '12px 15px' }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 13.5, fontWeight: 650, color: 'var(--ink)' }}>{t.nome}</span>
                  <span style={{ ...mono, fontSize: 11, color: 'var(--ink-3)' }}>{t.codigo}</span>
                  {!t.ativo && <Pill kind="slate">inativo</Pill>}
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 3 }}>
                  natureza <b style={{ color: 'var(--ink-2)' }}>{t.natureza_nome}</b> · {resumoDeEfeito(t)}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ ...CAPS, fontSize: 9 }}>itens usando</div>
                <div style={{ ...mono, fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>
                  {t.itens_com_este_tipo}
                </div>
              </div>
              {podeEditar && (
                <>
                  <Btn tam="sm" onClick={() => setEditando(t)}><Pencil size={13} />Editar</Btn>
                  <Btn
                    tam="sm"
                    variant="perigo"
                    disabled={t.itens_com_este_tipo > 0 || remover.isPending}
                    title={t.itens_com_este_tipo > 0
                      ? `${t.itens_com_este_tipo} item(ns) usam este tipo — troque-os antes de excluir.`
                      : 'Excluir tipo'}
                    onClick={async () => {
                      await remover.mutateAsync(t.tipo_item_id)
                      setRecado('Tipo excluído.')
                    }}
                  ><Trash2 size={13} /></Btn>
                </>
              )}
            </Card>
          ))}
          {podeEditar && (
            <button
              onClick={() => setEditando('novo')}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
                border: '1px dashed var(--line)', background: 'none', borderRadius: 'var(--r-md)',
                padding: '11px 14px', cursor: 'pointer', color: 'var(--ink-3)', fontSize: 12.5, fontWeight: 650,
              }}
            ><Plus size={14} />Novo tipo de item</button>
          )}
        </div>
      )}

      {editando && naturezas && (
        <ModalTipoItem
          tipo={editando === 'novo' ? null : editando}
          naturezas={naturezas}
          salvando={criar.isPending || atualizar.isPending}
          onFechar={() => setEditando(null)}
          onSalvar={async dados => {
            if (editando === 'novo') {
              await criar.mutateAsync(dados)
              setRecado('Tipo criado. Ele já aparece no cadastro de item.')
            } else {
              await atualizar.mutateAsync({ id: editando.tipo_item_id, payload: dados })
              setRecado(editando.itens_com_este_tipo > 0
                ? `Tipo atualizado — ${editando.itens_com_este_tipo} item(ns) passam a seguir a regra nova.`
                : 'Tipo atualizado.')
            }
            setEditando(null)
          }}
        />
      )}

      {recado && (
        <div style={{
          position: 'fixed', bottom: 22, left: '50%', zIndex: 95,
          background: 'var(--brand)', color: 'var(--brand-ink)', padding: '9px 17px',
          borderRadius: 999, fontSize: 12.5, fontWeight: 650, boxShadow: 'var(--shadow-lg)',
        }}>{recado}</div>
      )}
    </>
  )
}

/** A frase que resume o que um item deste tipo passa a fazer no sistema. É ela
 *  que o usuário lê antes de salvar — a lista de caixas marcadas não conta a
 *  mesma história. */
function resumoDeEfeito(flags: FlagsTipoItem): string {
  const partes = [
    flags.leva_encargo_social ? 'leva encargo social' : 'sem encargo social',
    flags.compravel ? 'entra na compra' : 'fora da compra',
    flags.estocavel ? 'tem saldo em estoque' : 'sem saldo em estoque',
  ]
  if (flags.consumivel) partes.push('baixa por obra')
  if (flags.rastreavel) partes.push('exige lote/validade')
  return partes.join(' · ')
}

function ModalTipoItem({ tipo, naturezas, salvando, onFechar, onSalvar }: {
  tipo: TipoItemProprio | null
  naturezas: NaturezaComPadroes[]
  salvando: boolean
  onFechar: () => void
  onSalvar: (dados: Partial<TipoItemProprio>) => Promise<void>
}) {
  const [form, setForm] = useState<FormTipo>(() => (tipo ? { ...tipo } : { ...VAZIO }))
  const [erro, setErro] = useState('')
  const [codigoTocado, setCodigoTocado] = useState(Boolean(tipo))

  const natureza = useMemo(
    () => naturezas.find(n => n.valor === form.natureza),
    [naturezas, form.natureza],
  )
  const padroes = natureza?.padroes
  const foraDoPadrao = padroes
    ? FLAGS.some(f => form[f.chave] !== padroes[f.chave])
    : false
  const encargoBloqueado = form.natureza !== 'mao_de_obra'

  /** Trocar a natureza **repõe** os padrões dela. É a parte que evita o tipo
   *  meio-configurado: quem muda de "material" para "mão de obra" e mantinha as
   *  flags de material sairia com um pedreiro estocável. */
  const escolherNatureza = (valor: NaturezaItem) => {
    const alvo = naturezas.find(n => n.valor === valor)
    setForm(f => ({ ...f, natureza: valor, ...(alvo ? alvo.padroes : {}) }))
  }

  return (
    <Modal
      titulo={tipo ? `Editar tipo — ${tipo.nome}` : 'Novo tipo de item'}
      largura={640}
      onClose={onFechar}
      rodape={
        <>
          <Btn onClick={onFechar}>Cancelar</Btn>
          <Btn variant="primary" disabled={salvando} onClick={async () => {
            const nome = form.nome.trim()
            const codigo = (form.codigo || paraCodigo(nome)).trim()
            if (!nome || !codigo) { setErro('Informe o nome do tipo.'); return }
            if (form.leva_encargo_social && encargoBloqueado) {
              setErro('Encargo social só em natureza "Mão de obra".'); return
            }
            setErro('')
            try {
              await onSalvar({ ...form, nome, codigo })
            } catch (e) {
              const dados = (e as { response?: { data?: Record<string, unknown> } })?.response?.data
              const primeiro = dados && Object.values(dados)[0]
              const detalhe = Array.isArray(primeiro) ? String(primeiro[0]) : primeiro ? String(primeiro) : null
              setErro(detalhe ?? 'Não foi possível salvar o tipo.')
            }
          }}>{tipo ? 'Salvar' : 'Criar tipo'}</Btn>
        </>
      }
    >
      {erro && <Aviso tom="danger">{erro}</Aviso>}

      {tipo && tipo.itens_com_este_tipo > 0 && (
        <>
          <Aviso tom="amber">
            <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
            <span style={{ minWidth: 0 }}>
              <b>{tipo.itens_com_este_tipo} item(ns)</b> já usam este tipo. Mudar a natureza muda como
              todos eles são calculados dali em diante — orçamentos <b>em rascunho</b> acompanham no
              próximo recálculo; os já aprovados não se mexem.
            </span>
          </Aviso>
          <div style={{ height: 14 }} />
        </>
      )}

      {/* Passo 1 — a natureza, que é o que decide conta. */}
      <div style={{ ...CAPS, fontSize: 9, marginBottom: 7 }}>1 · Natureza (é ela que decide o cálculo)</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(190px,1fr))', gap: 6 }}>
        {naturezas.map(n => {
          const marcada = n.valor === form.natureza
          return (
            <button
              key={n.valor}
              onClick={() => escolherNatureza(n.valor)}
              style={{
                textAlign: 'left', padding: '8px 10px', cursor: 'pointer',
                borderRadius: 'var(--r-sm)',
                border: `1px solid ${marcada ? 'var(--accent)' : 'var(--line)'}`,
                background: marcada ? 'var(--accent-soft)' : 'var(--surface)',
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {marcada && <Check size={12} style={{ color: 'var(--accent-ink)' }} />}
                <span style={{ fontSize: 12.5, fontWeight: 650, color: 'var(--ink)' }}>{n.rotulo}</span>
              </span>
              <span style={{ display: 'block', fontSize: 11, color: 'var(--ink-3)', marginTop: 2 }}>
                {resumoDeEfeito(n.padroes)}
              </span>
            </button>
          )
        })}
      </div>

      <div style={{ height: 16 }} />

      {/* Passo 2 — o nome da casa. */}
      <div style={{ ...CAPS, fontSize: 9, marginBottom: 7 }}>2 · Como a empresa chama</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 200px', gap: '0 14px' }}>
        <Field label="Nome">
          <input
            autoFocus
            value={form.nome}
            onChange={e => setForm(f => ({
              ...f,
              nome: e.target.value,
              codigo: codigoTocado ? f.codigo : paraCodigo(e.target.value),
            }))}
            placeholder="Ex.: Andaime locado"
            style={inp}
          />
        </Field>
        <Field label="Código" dica="Em branco, sai do nome. É o identificador que não muda.">
          <input
            value={form.codigo}
            onChange={e => { setCodigoTocado(true); setForm(f => ({ ...f, codigo: paraCodigo(e.target.value) })) }}
            style={{ ...inp, ...mono }}
          />
        </Field>
        <div style={{ gridColumn: '1 / -1' }}>
          <Field label="Descrição" dica="Aparece para quem escolhe o tipo no cadastro de item.">
            <input
              value={form.descricao}
              onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))}
              placeholder="Ex.: Estrutura de andaime alugada por mês, sem operador."
              style={inp}
            />
          </Field>
        </div>
      </div>

      {/* Passo 3 — as flags, já preenchidas pela natureza. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '4px 0 7px' }}>
        <span style={{ ...CAPS, fontSize: 9 }}>3 · O que o sistema faz com ele</span>
        {foraDoPadrao && (
          <button
            onClick={() => padroes && setForm(f => ({ ...f, ...padroes }))}
            style={{
              border: 'none', background: 'none', cursor: 'pointer', padding: 0,
              color: 'var(--net-ink)', fontSize: 11.5, fontWeight: 650, textDecoration: 'underline',
            }}
          >voltar ao padrão de {natureza?.rotulo?.toLowerCase()}</button>
        )}
      </div>
      <div style={{ display: 'grid', gap: 5 }}>
        {FLAGS.map(f => {
          const bloqueada = f.chave === 'leva_encargo_social' && encargoBloqueado
          const marcada = Boolean(form[f.chave])
          return (
            <label
              key={f.chave}
              title={bloqueada
                ? 'Encargo social incide sobre salário: só natureza "Mão de obra" pode levá-lo. '
                  + 'Se o custo já vem com encargo dentro (serviço de terceiro), deixe desmarcado.'
                : undefined}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 9, padding: '7px 10px',
                borderRadius: 'var(--r-sm)', border: '1px solid var(--line)',
                background: bloqueada ? 'var(--inset)' : 'var(--surface)',
                opacity: bloqueada ? 0.55 : 1,
                cursor: bloqueada ? 'not-allowed' : 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={marcada && !bloqueada}
                disabled={bloqueada}
                onChange={e => setForm(v => ({ ...v, [f.chave]: e.target.checked }))}
                style={{ marginTop: 2, accentColor: 'var(--accent)' }}
              />
              <span style={{ minWidth: 0 }}>
                <span style={{ display: 'block', fontSize: 12.5, fontWeight: 650, color: 'var(--ink)' }}>
                  {f.rotulo}
                  {padroes && form[f.chave] !== padroes[f.chave] && !bloqueada && (
                    <span style={{ ...CAPS, fontSize: 8.5, marginLeft: 7, color: 'var(--accent-ink)' }}>
                      fora do padrão
                    </span>
                  )}
                </span>
                <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.45 }}>
                  {f.efeito}
                </span>
              </span>
            </label>
          )
        })}
      </div>

      <div style={{ height: 12 }} />
      <div style={{
        padding: '9px 12px', borderRadius: 'var(--r-sm)', background: 'var(--inset)',
        fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.5,
      }}>
        <b>Resumo:</b> um item deste tipo {resumoDeEfeito(form)}.
      </div>

      {!form.ativo && (
        <>
          <div style={{ height: 10 }} />
          <Aviso tom="amber">
            <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
            Tipo inativo não aparece para escolher em item novo. Os itens que já o usam continuam
            como estão.
          </Aviso>
        </>
      )}
      <div style={{ height: 10 }} />
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--ink-2)' }}>
        <input
          type="checkbox"
          checked={form.ativo}
          onChange={e => setForm(f => ({ ...f, ativo: e.target.checked }))}
          style={{ accentColor: 'var(--accent)' }}
        />
        Ativo — disponível para escolher em item novo
      </label>
    </Modal>
  )
}
