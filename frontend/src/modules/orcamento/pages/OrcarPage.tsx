import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle, Calculator, CheckCircle2, ChevronRight, Copy as CopyIcon, Download, ExternalLink,
  FileSpreadsheet, FolderPlus, GitBranch, Lock, Percent, Plus, RefreshCw, RotateCcw, Ruler, Search,
  Trash2, TrendingUp, Upload,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import PaginaShell from '../components/PaginaShell'
import MedicaoDrawer from '../components/MedicaoDrawer'
import GradeOrcamento, { type ColunaEditavel, type EdicaoCelula } from '../components/GradeOrcamento'
import InserirItemModal, { type Escolha } from '../components/InserirItemModal'
import { Aviso, Btn, Card, CAPS, Empty, Field, inp, Loading, Modal, mono, Pill, Select, Seletor, Spinner, Drawer, Info } from '../ui'
import { brl, mesBR, num, paraDecimal, pct, STATUS_ESTADO } from '../lib'
import { baixarExportacao } from '../api/orcamentoApi'
import {
  useAnalitica, useAprovar, useArvore, useBasesResumo, useCriarItem, useEditarCelula,
  useExplodir, useItemDoCatalogo, useMemoria, useObras, usePrecoReal, useRecalcular,
  useRemoverItem, useRevisar, useAplicarPrecoReal, useAtualizarOrcamento,
  useAplicarReprecificacao, useDesfazerReprecificacao, useDuplicarOrcamento,
  useGerarPreviaReprecificacao, useHistoricoReprecificacao,
} from '../hooks'
import type { ItemOrcado, ObraOpt, PreviaReprecificacao } from '../types'

type Modo = 'sintetico' | 'analitico'

export default function OrcarPage() {
  const { hasPermission } = useAuth()
  // A planilha é um **lugar**, e não um filtro: o id vem da rota. É o que faz o
  // voltar do navegador, o link colável e a trilha do cabeçalho existirem sem
  // ninguém programar nenhum dos três.
  const { orcamentoId: naRota } = useParams()
  const navigate = useNavigate()
  const orcamentoId = naRota ? Number(naRota) : undefined

  const { data: obras } = useObras()
  const { data: arvore, isLoading: carregandoArvore } = useArvore(orcamentoId)
  const { data: bases } = useBasesResumo()

  // Sintético é o padrão: é a planilha que se lê e que vai para o edital. Abrir
  // a composição da obra inteira é ato deliberado — e custa uma consulta a mais.
  const [modo, setModo] = useState<Modo>('sintetico')
  const { data: analitica, isLoading: carregandoAnalitica } = useAnalitica(orcamentoId, modo === 'analitico')
  const [filtro, setFiltro] = useState('')
  const [inserindo, setInserindo] = useState(false)
  const [ajustandoTaxas, setAjustandoTaxas] = useState(false)
  const [revisando, setRevisando] = useState(false)
  const [menu, setMenu] = useState<{ item: ItemOrcado; x: number; y: number } | null>(null)
  const [memoriaDe, setMemoriaDe] = useState<ItemOrcado | null>(null)
  const [medicaoDe, setMedicaoDe] = useState<ItemOrcado | null>(null)
  const [precoDe, setPrecoDe] = useState<ItemOrcado | null>(null)
  const [recado, setRecado] = useState('')
  const [duplicando, setDuplicando] = useState(false)
  const [reprecificando, setReprecificando] = useState(false)
  const [exportando, setExportando] = useState(false)

  const editarCelula = useEditarCelula(orcamentoId)
  const criarItem = useCriarItem()
  const itemDoCatalogo = useItemDoCatalogo()
  const removerItem = useRemoverItem()
  const recalcular = useRecalcular()
  const aprovar = useAprovar()
  const revisar = useRevisar()
  const explodir = useExplodir()
  const atualizarOrcamento = useAtualizarOrcamento()

  const orcamento = arvore?.orcamento
  const podeEditar = hasPermission('orcamento.orcamento.edit') && !!orcamento?.editavel
  const podeAprovar = hasPermission('orcamento.orcamento.aprovar')
  const podeRevisar = hasPermission('orcamento.orcamento.revisar')

  useEffect(() => {
    if (!recado) return
    const t = setTimeout(() => setRecado(''), 3800)
    return () => clearTimeout(t)
  }, [recado])

  useEffect(() => {
    if (!menu) return
    const fechar = () => setMenu(null)
    document.addEventListener('click', fechar)
    return () => document.removeEventListener('click', fechar)
  }, [menu])

  /** Trocar de planilha é trocar de endereço: quem revisou ou duplicou sai
   *  daqui com um link que continua valendo. */
  const abrir = (id: number) => navigate(`/app/orcamento/orcar/orcamento/${id}`)

  async function explodirLinha(item: ItemOrcado) {
    try {
      await explodir.mutateAsync(item.item_orcado_id)
      setRecado('Composição explodida — custo unitário refeito pelos insumos.')
    } catch {
      setRecado('Este item não tem composição cadastrada no catálogo.')
    }
  }

  async function inserirEscolhas(escolhas: Escolha[]) {
    if (!orcamentoId) return
    for (const escolha of escolhas) {
      await itemDoCatalogo.mutateAsync({
        orcamento: orcamentoId,
        item: escolha.itemCatalogoId,
        quantidade: '1',
      })
    }
    setInserindo(false)
    setRecado(`${escolhas.length} linha(s) inserida(s) — digite as quantidades na grade.`)
  }

  async function adicionarGrupo() {
    if (!orcamentoId) return
    await criarItem.mutateAsync({
      orcamento: orcamentoId,
      tipo_linha: 'sintetico',
      descricao: 'Nova etapa',
      ordem: (arvore?.itens.filter(i => i.pai === null).length ?? 0) + 1,
    })
    setRecado('Etapa criada. Renomeie na grade e arraste itens para dentro pelo menu da linha.')
  }

  const totais = useMemo(() => {
    if (!orcamento) return null
    const direto = Number(orcamento.custo_direto_total)
    const total = Number(orcamento.valor_total)
    return { direto, total, bdiValor: total - direto }
  }, [orcamento])

  // Trilha, e não seletor: cada nível é um endereço, e voltar é subir um nível
  // — o desenho de qualquer sistema com lista e detalhe. O seletor antigo não
  // tinha volta possível (escolher "todas as obras" era reescrito na hora pela
  // obra do orçamento aberto), porque filtro não é lugar nenhum.
  const seletor = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
      <nav style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12.5, minWidth: 0 }}>
        <Link to="/app/orcamento/orcar" style={{ color: 'var(--ink-3)', textDecoration: 'none', fontWeight: 650 }}>
          Obras
        </Link>
        {orcamento && (
          <>
            <ChevronRight size={13} style={{ color: 'var(--ink-3)', flex: 'none' }} />
            <Link
              to={`/app/orcamento/orcar/obra/${orcamento.obra}`}
              style={{
                color: 'var(--ink-3)', textDecoration: 'none', fontWeight: 650,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 200,
              }}
            >{orcamento.obra_nome}</Link>
            <ChevronRight size={13} style={{ color: 'var(--ink-3)', flex: 'none' }} />
            <span style={{
              fontWeight: 650, color: 'var(--ink)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 260,
            }}>
              {orcamento.descricao} <span style={{ ...mono, color: 'var(--ink-3)' }}>v{orcamento.versao}</span>
            </span>
          </>
        )}
      </nav>
      {orcamento && (
        <Seletor
          compacto
          valor={modo}
          onChange={setModo}
          opcoes={[
            { valor: 'sintetico' as Modo, rotulo: 'Sintético' },
            { valor: 'analitico' as Modo, rotulo: 'Analítico' },
          ]}
        />
      )}
    </div>
  )

  const acoes = orcamento ? (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
      <div style={{ position: 'relative' }}>
        <Search size={13} style={{ position: 'absolute', left: 8, top: 7, color: 'var(--ink-3)' }} />
        <input
          value={filtro}
          onChange={e => setFiltro(e.target.value)}
          placeholder="Filtrar linhas"
          style={{ ...inp, width: 168, paddingLeft: 27, padding: '5px 9px 5px 27px', fontSize: 12 }}
        />
      </div>
      {podeEditar && <Btn tam="sm" variant="primary" onClick={() => setInserindo(true)}><Plus size={13} />Item</Btn>}
      {podeEditar && <Btn tam="sm" onClick={adicionarGrupo}><FolderPlus size={13} />Etapa</Btn>}
      {podeEditar && <Btn tam="sm" onClick={() => setAjustandoTaxas(true)}><Percent size={13} />BDI e encargos</Btn>}
      {podeEditar && (
        <Btn tam="sm" onClick={() => recalcular.mutate(orcamento.orcamento_id)} disabled={recalcular.isPending}>
          <Calculator size={13} />Recalcular
        </Btn>
      )}
      {orcamento.status === 'rascunho' && podeAprovar && (
        <Btn tam="sm" variant="brand" onClick={() => aprovar.mutate(orcamento.orcamento_id)} disabled={aprovar.isPending}>
          <CheckCircle2 size={13} />Aprovar
        </Btn>
      )}
      {orcamento.status === 'aprovado' && podeRevisar && (
        <Btn tam="sm" variant="brand" onClick={() => setRevisando(true)}><GitBranch size={13} />Revisar</Btn>
      )}
      {podeEditar && <Btn tam="sm" onClick={() => setReprecificando(true)}><RefreshCw size={13} />Reprecificar</Btn>}
      {hasPermission('orcamento.orcamento.edit') && (
        <Btn tam="sm" onClick={() => setDuplicando(true)}><CopyIcon size={13} />Duplicar</Btn>
      )}
      {hasPermission('orcamento.relatorio.view') && (
        <Btn tam="sm" onClick={() => setExportando(true)}><Download size={13} />Exportar</Btn>
      )}
    </div>
  ) : null

  return (
    <PaginaShell pagina="orcar" seletor={seletor} acoes={acoes} semRolagem>
      {carregandoArvore && !arvore ? (
        <Loading texto="Abrindo a planilha…" />
      ) : !orcamento ? (
        <div style={{ padding: 26, overflowY: 'auto' }}>
          <Empty acao={
            <Link to="/app/orcamento/orcar" style={{ textDecoration: 'none' }}>
              <Btn variant="primary">Ver as obras</Btn>
            </Link>
          }>
            Esta planilha não existe mais, ou você não tem acesso a ela. Volte para a lista e escolha
            a obra.
          </Empty>
        </div>
      ) : (
        <>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', flex: 'none',
            padding: '8px 18px', background: 'var(--surface-2)', borderBottom: '1px solid var(--line)', fontSize: 12,
          }}>
            <Pill kind={STATUS_ESTADO[orcamento.status].kind} pulse={STATUS_ESTADO[orcamento.status].pulse}>
              {STATUS_ESTADO[orcamento.status].label}
            </Pill>
            <span style={{ color: 'var(--ink-3)' }}>
              <b style={{ color: 'var(--ink-2)' }}>{orcamento.obra_nome}</b> · v{orcamento.versao}
            </span>
            <span style={{ color: 'var(--ink-3)' }}>
              base <b style={{ color: 'var(--ink-2)' }}>{orcamento.base_rotulo ?? 'não vinculada'}</b> · data-base {mesBR(orcamento.data_base)}
            </span>
            <span style={{ color: 'var(--ink-3)' }}>
              encargos <b style={{ ...mono, color: 'var(--ink-2)' }}>{pct(orcamento.encargos_sociais_percentual, 2)}</b> {orcamento.regime_encargos}
            </span>
            <span style={{ color: 'var(--ink-3)' }}>
              BDI <b style={{ ...mono, color: 'var(--ink-2)' }}>{pct(orcamento.bdi_percentual, 2)}</b>
            </span>
            <div style={{ flex: 1 }} />
            <Link to={`/app/obras/${orcamento.obra}`} style={{ color: 'var(--net-ink)', fontSize: 11.5, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              ficha da obra <ExternalLink size={11} />
            </Link>
            <Link to={`/app/orcamento/controlar?obra=${orcamento.obra}`} style={{ color: 'var(--net-ink)', fontSize: 11.5, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              quatro colunas <ExternalLink size={11} />
            </Link>
            {!orcamento.editavel && (
              <Pill kind="slate" title="Orçamento congelado: crie uma revisão para alterar"><Lock size={11} />somente leitura</Pill>
            )}
          </div>

          {arvore && arvore.itens.length === 0 ? (
            <div style={{ padding: 26 }}>
              <Empty acao={podeEditar ? (
                <div style={{ display: 'flex', gap: 8 }}>
                  <Btn variant="primary" onClick={() => setInserindo(true)}><Plus size={14} />Inserir item</Btn>
                  <Btn onClick={adicionarGrupo}><FolderPlus size={14} />Criar etapa</Btn>
                </div>
              ) : undefined}>
                A planilha está vazia. Comece criando as etapas da EAP (Serviços preliminares,
                Infraestrutura, Estrutura…) ou puxando serviços direto da base de preço.
              </Empty>
            </div>
          ) : (
            <GradeOrcamento
              itens={arvore?.itens ?? []}
              totalOrcamento={orcamento.valor_total}
              bdiPadrao={orcamento.bdi_percentual}
              dataBaseOrcamento={orcamento.data_base}
              editavel={podeEditar}
              modo={modo}
              filtro={filtro}
              insumos={analitica}
              carregandoInsumos={carregandoAnalitica}
              onExplodir={podeEditar ? explodirLinha : undefined}
              onEditar={(item, coluna: ColunaEditavel, valor) =>
                editarCelula.mutate({ id: item.item_orcado_id, payload: { [coluna]: valor } as Partial<ItemOrcado> })}
              onColar={(edicoes: EdicaoCelula[]) => {
                for (const e of edicoes) {
                  editarCelula.mutate({ id: e.item.item_orcado_id, payload: { [e.coluna]: e.valor } as Partial<ItemOrcado> })
                }
                setRecado(`${edicoes.length} célula(s) coladas do Excel.`)
              }}
              onAbrirLinha={item => setMemoriaDe(item)}
              onMenu={(item, ancora) => setMenu({ item, x: ancora.left - 210, y: ancora.bottom + 4 })}
            />
          )}

          {totais && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 26, flexWrap: 'wrap', flex: 'none',
              padding: '9px 20px', background: 'var(--surface)', borderTop: '1px solid var(--line)',
            }}>
              <span style={{ ...CAPS }}>Custo direto <b style={{ ...mono, fontSize: 14, color: 'var(--ink-2)', marginLeft: 6 }}>{brl(totais.direto)}</b></span>
              <span style={{ ...CAPS }}>BDI <b style={{ ...mono, fontSize: 14, color: 'var(--accent-ink)', marginLeft: 6 }}>{brl(totais.bdiValor)}</b></span>
              <span style={{ ...CAPS }}>Linhas <b style={{ ...mono, fontSize: 14, color: 'var(--ink-2)', marginLeft: 6 }}>{arvore?.itens.length ?? 0}</b></span>
              <div style={{ flex: 1 }} />
              <span style={{ ...CAPS, fontSize: 11 }}>Total do orçamento</span>
              <span style={{ ...mono, fontSize: 21, fontWeight: 800, color: 'var(--ink)' }}>{brl(totais.total)}</span>
            </div>
          )}
        </>
      )}

      {menu && (
        <div
          onClick={e => e.stopPropagation()}
          style={{
            position: 'fixed', left: Math.max(8, menu.x), top: menu.y, zIndex: 60, minWidth: 218,
            background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-md)',
            boxShadow: 'var(--shadow-lg)', padding: 5,
          }}
          className="orc-modal"
        >
          {[
            { rotulo: 'Memória de cálculo', icone: <FileSpreadsheet size={13} />, acao: () => setMemoriaDe(menu.item) },
            // ORC.7 — a memória do outro lado: o preço já abria em insumos, a
            // quantidade não abria em nada.
            {
              rotulo: 'Memória do quantitativo', icone: <Ruler size={13} />,
              off: menu.item.tipo_linha === 'sintetico',
              acao: () => setMedicaoDe(menu.item),
            },
            { rotulo: 'Preço real (SCM / SIL)', icone: <TrendingUp size={13} />, acao: () => setPrecoDe(menu.item), off: !menu.item.item },
            {
              rotulo: 'Explodir composição', icone: <GitBranch size={13} />, off: !podeEditar || !menu.item.item,
              acao: () => explodirLinha(menu.item),
            },
            {
              rotulo: 'Adicionar sub-item', icone: <Plus size={13} />, off: !podeEditar,
              acao: async () => {
                await criarItem.mutateAsync({
                  orcamento: menu.item.orcamento, pai: menu.item.item_orcado_id,
                  tipo_linha: 'analitico', descricao: 'Novo item', unidade: 'un', quantidade: '1',
                })
                setRecado('Sub-item criado.')
              },
            },
            {
              rotulo: 'Excluir linha', icone: <Trash2 size={13} />, perigo: true, off: !podeEditar,
              acao: async () => { await removerItem.mutateAsync(menu.item.item_orcado_id); setRecado('Linha excluída.') },
            },
          ].map(op => (
            <button
              key={op.rotulo}
              disabled={op.off}
              onClick={() => { setMenu(null); op.acao() }}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'left',
                border: 'none', background: 'none', padding: '7px 10px', borderRadius: 'var(--r-sm)',
                fontSize: 12.5, fontWeight: 600, cursor: op.off ? 'not-allowed' : 'pointer',
                opacity: op.off ? 0.42 : 1, color: op.perigo ? 'var(--danger-ink)' : 'var(--ink-2)',
              }}
            >{op.icone}{op.rotulo}</button>
          ))}
        </div>
      )}

      {inserindo && (
        <InserirItemModal
          onFechar={() => setInserindo(false)}
          onInserir={inserirEscolhas}
          inserindo={itemDoCatalogo.isPending}
        />
      )}

      {memoriaDe && <DrawerMemoria item={memoriaDe} onFechar={() => setMemoriaDe(null)} />}
      {medicaoDe && (
        <MedicaoDrawer
          itemOrcado={medicaoDe.item_orcado_id}
          descricao={medicaoDe.descricao}
          unidade={medicaoDe.unidade}
          podeEditar={podeEditar}
          onClose={() => setMedicaoDe(null)}
        />
      )}
      {precoDe && (
        <DrawerPrecoReal
          item={precoDe}
          podeAplicar={podeEditar}
          onFechar={() => setPrecoDe(null)}
          onAplicado={() => { setPrecoDe(null); setRecado('Preço real adotado no lugar do referencial.') }}
        />
      )}

      {ajustandoTaxas && orcamento && (
        <Modal
          titulo="BDI e encargos sociais"
          onClose={() => setAjustandoTaxas(false)}
          rodape={<Btn onClick={() => setAjustandoTaxas(false)}>Fechar</Btn>}
        >
          <FormTaxas
            bdi={orcamento.bdi_percentual}
            encargos={orcamento.encargos_sociais_percentual}
            regime={orcamento.regime_encargos}
            salvando={atualizarOrcamento.isPending}
            onSalvar={async dados => {
              await atualizarOrcamento.mutateAsync({ id: orcamento.orcamento_id, payload: dados as Partial<typeof orcamento> })
              await recalcular.mutateAsync(orcamento.orcamento_id)
              setAjustandoTaxas(false)
              setRecado('Taxas atualizadas e planilha recalculada.')
            }}
          />
        </Modal>
      )}

      {revisando && orcamento && (
        <ModalRevisar
          salvando={revisar.isPending}
          onFechar={() => setRevisando(false)}
          onRevisar={async (tipo, motivo) => {
            const nova = await revisar.mutateAsync({ id: orcamento.orcamento_id, tipo, motivo })
            setRevisando(false)
            abrir(nova.orcamento_id)
            setRecado(`Versão v${nova.versao} criada a partir da aprovada.`)
          }}
        />
      )}

      {duplicando && orcamento && (
        <ModalDuplicar
          orcamento={orcamento}
          obras={obras ?? []}
          onFechar={() => setDuplicando(false)}
          onDuplicado={(id, aviso) => {
            setDuplicando(false)
            abrir(id)
            setRecado(aviso || 'Orçamento duplicado em rascunho.')
          }}
        />
      )}

      {reprecificando && orcamento && (
        <ModalReprecificar
          orcamentoId={orcamento.orcamento_id}
          bases={bases ?? []}
          onFechar={() => setReprecificando(false)}
          onRecado={setRecado}
        />
      )}

      {exportando && orcamento && (
        <ModalExportar
          orcamentoId={orcamento.orcamento_id}
          onFechar={() => setExportando(false)}
          onRecado={setRecado}
        />
      )}

      {recado && (
        <div style={{
          position: 'fixed', bottom: 22, left: '50%', zIndex: 95, animation: 'orcToast .22s ease both',
          background: 'var(--brand)', color: 'var(--brand-ink)', padding: '9px 17px',
          borderRadius: 999, fontSize: 12.5, fontWeight: 650, boxShadow: 'var(--shadow-lg)',
        }}>{recado}</div>
      )}
    </PaginaShell>
  )
}

function ModalDuplicar({ orcamento, obras, onFechar, onDuplicado }: {
  orcamento: { orcamento_id: number; descricao: string; obra: number }
  obras: ObraOpt[]
  onFechar: () => void
  onDuplicado: (id: number, aviso: string) => void
}) {
  const duplicar = useDuplicarOrcamento()
  const [obra, setObra] = useState(String(orcamento.obra))
  const [descricao, setDescricao] = useState(`${orcamento.descricao} (cópia)`)
  const mudouObra = Number(obra) !== orcamento.obra

  return (
    <Modal
      titulo="Duplicar orçamento"
      onClose={onFechar}
      rodape={
        <>
          <Btn onClick={onFechar}>Cancelar</Btn>
          <Btn variant="primary" disabled={duplicar.isPending} onClick={async () => {
            const r = await duplicar.mutateAsync({
              id: orcamento.orcamento_id, obra: Number(obra), descricao: descricao.trim(),
            })
            onDuplicado(r.orcamento, r.aviso_etapa || `Cópia criada: ${r.total_itens} linhas.`)
          }}>Duplicar</Btn>
        </>
      }
    >
      <Aviso>
        <CopyIcon size={15} style={{ flex: 'none', marginTop: 1 }} />
        Duplicar é diferente de <b>revisar</b>: a cópia nasce como planilha nova em rascunho e não
        rebaixa o original. É como se reaproveita o orçamento de uma obra parecida.
      </Aviso>
      <div style={{ height: 14 }} />
      <Field label="Obra de destino">
        <Select value={obra} onChange={e => setObra(e.target.value)} style={{ width: '100%', maxWidth: 'none' }}>
          {obras.map(o => <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>)}
        </Select>
      </Field>
      <Field label="Descrição">
        <input value={descricao} onChange={e => setDescricao(e.target.value)} style={inp} />
      </Field>
      {mudouObra && (
        <Aviso tom="amber">
          <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
          Mudando de obra, a <b>apropriação por etapa não vai junto</b> — etapa pertence a uma obra
          específica, e carregá-la faria o orçado casar com o aplicado da obra errada. Reatribua as
          etapas na cópia.
        </Aviso>
      )}
    </Modal>
  )
}

function ModalReprecificar({ orcamentoId, bases, onFechar, onRecado }: {
  orcamentoId: number
  bases: { base_id: number; rotulo: string }[]
  onFechar: () => void
  onRecado: (m: string) => void
}) {
  const [baseDestino, setBaseDestino] = useState('')
  const [somenteAte, setSomenteAte] = useState('')
  const [previa, setPrevia] = useState<PreviaReprecificacao | null>(null)
  const [selecao, setSelecao] = useState<Set<number>>(new Set())
  const [erro, setErro] = useState('')

  const gerar = useGerarPreviaReprecificacao()
  const aplicar = useAplicarReprecificacao()
  const desfazer = useDesfazerReprecificacao()
  const { data: historico } = useHistoricoReprecificacao(orcamentoId)

  const aplicaveis = (historico ?? []).filter(l => l.status === 'aplicada')
  const ultimo = aplicaveis[0]

  async function comErro(acao: () => Promise<void>) {
    setErro('')
    try { await acao() } catch (e) {
      const detalhe = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErro(detalhe ?? 'Não foi possível concluir a operação.')
    }
  }

  return (
    <Modal
      titulo="Reprecificar — trocar a data-base"
      onClose={onFechar}
      largura={previa ? 880 : 560}
      rodape={
        <>
          <Btn onClick={onFechar}>Fechar</Btn>
          {previa && previa.linhas.length > 0 && (
            <>
              <Btn disabled={aplicar.isPending || selecao.size === 0} onClick={() => comErro(async () => {
                await aplicar.mutateAsync({ lote: previa.reprecificacao, linhas: [...selecao] })
                onFechar()
                onRecado(`${selecao.size} linha(s) reprecificadas.`)
              })}>Aplicar seleção ({selecao.size})</Btn>
              <Btn variant="primary" disabled={aplicar.isPending} onClick={() => comErro(async () => {
                await aplicar.mutateAsync({ lote: previa.reprecificacao })
                onFechar()
                // `linhas.length` contaria também as que não têm preço novo, e o
                // recado prometeria um efeito maior do que o que aconteceu.
                onRecado(
                  `${previa.linhas_afetadas} linha(s) reprecificadas` +
                  (previa.linhas_descontinuadas
                    ? ` · ${previa.linhas_descontinuadas} sem preço na publicação, mantida(s) na data-base anterior.`
                    : '.')
                )
              })}>Aplicar tudo</Btn>
            </>
          )}
        </>
      }
    >
      {erro && <Aviso tom="danger">{erro}</Aviso>}

      {!previa ? (
        <>
          <Aviso>
            <RefreshCw size={15} style={{ flex: 'none', marginTop: 1 }} />
            Escolha <b>qualquer publicação</b> — para frente ou para trás. Em licitação a data-base é
            a do edital, e ela costuma ser passada.
          </Aviso>
          <div style={{ height: 14 }} />
          <Field label="Publicação de destino">
            <Select value={baseDestino} onChange={e => setBaseDestino(e.target.value)} style={{ width: '100%', maxWidth: 'none' }}>
              <option value="">Selecione</option>
              {bases.map(b => <option key={b.base_id} value={b.base_id}>{b.rotulo}</option>)}
            </Select>
          </Field>
          <Field label="Só linhas com preço até (data de corte)" dica="Opcional. Linha com preço mais novo que isto não é tocada — preserva o que já foi renegociado à mão.">
            <input type="date" value={somenteAte} onChange={e => setSomenteAte(e.target.value)} style={{ ...inp, ...mono }} />
          </Field>
          <Btn variant="primary" disabled={!baseDestino || gerar.isPending} onClick={() => comErro(async () => {
            const p = await gerar.mutateAsync({
              orcamento: orcamentoId,
              base_destino: Number(baseDestino),
              somente_ate: somenteAte || null,
            })
            setPrevia(p)
            // A descontinuada fica **de fora** da seleção. O backend já a recusa,
            // mas marcá-la aqui faria o contador de "Aplicar seleção (N)" prometer
            // um efeito que não existe — e é justamente sobre essas linhas que o
            // usuário precisa de clareza.
            setSelecao(new Set(p.linhas.filter(l => !l.descontinuado).map(l => l.linha)))
          })}>Ver a prévia</Btn>

          {aplicaveis.length > 0 && (
            <>
              <div style={{ height: 18 }} />
              <div style={{ ...CAPS, marginBottom: 7 }}>Histórico</div>
              {aplicaveis.map(lote => (
                <Card key={lote.reprecificacao_id} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '10px 13px', marginBottom: 7 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, color: 'var(--ink)' }}>{lote.destino_rotulo ?? '—'}</div>
                    <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                      {lote.linhas_afetadas} linhas · {brl(lote.delta)} ·{' '}
                      {new Date(lote.aplicada_em ?? lote.criado_em).toLocaleDateString('pt-BR')}
                    </div>
                  </div>
                  {ultimo?.reprecificacao_id === lote.reprecificacao_id && (
                    <Btn tam="sm" disabled={desfazer.isPending} onClick={() => comErro(async () => {
                      await desfazer.mutateAsync(lote.reprecificacao_id)
                      onRecado('Reprecificação desfeita — preços e procedência restaurados.')
                      onFechar()
                    })}><RotateCcw size={12} />Desfazer</Btn>
                  )}
                </Card>
              ))}
              <p style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                Só o lote mais recente pode ser desfeito — desfazer fora de ordem deixaria a planilha
                com preços de lotes diferentes.
              </p>
            </>
          )}
        </>
      ) : previa.linhas.length === 0 ? (
        <Aviso tom="amber">
          <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
          Nenhuma linha muda de preço nesta publicação. Ou os preços são iguais, ou as linhas não têm
          código de referência para casar.
        </Aviso>
      ) : (
        <>
          {previa.linhas_descontinuadas > 0 && (
            /* A regra do dono (22/08/2026): item que a publicação de destino não
               tem **não** vira preço zero e **não** é excluído — o sistema avisa
               quais são e mantém a data-base antiga naquelas linhas. O aviso
               precisa estar aqui, antes de aplicar, e não só na grade depois. */
            <Aviso tom="amber">
              <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
              <span>
                <b>{previa.linhas_descontinuadas} item(ns) não têm preço nesta publicação.</b>{' '}
                Eles não são zerados nem removidos: mantêm o preço e a data-base que já tinham,
                e ficam marcados abaixo com o motivo. O total da planilha passa a misturar duas
                datas-base — e a grade continua apontando essas linhas depois.
              </span>
            </Aviso>
          )}

          <div style={{ display: 'flex', gap: 22, flexWrap: 'wrap', marginBottom: 13 }}>
            <Info k="Total antes" v={brl(previa.total_antes)} m />
            <Info k="Total depois" v={brl(previa.total_depois)} m />
            <Info k="Diferença" v={
              <span style={{ color: Number(previa.delta) > 0 ? 'var(--danger-ink)' : 'var(--good-ink)' }}>
                {brl(previa.delta)} {previa.delta_pct ? `(${pct(previa.delta_pct, 2)})` : ''}
              </span>
            } m />
            <Info k="Linhas" v={previa.linhas_afetadas} m />
          </div>
          <div style={{ maxHeight: 340, overflowY: 'auto', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr>
                  {['', 'Item', 'Descrição', 'Antes', 'Depois', 'Δ %', 'Δ total'].map((h, i) => (
                    <th key={h || i} style={{
                      ...CAPS, padding: '7px 10px', textAlign: i >= 3 ? 'right' : 'left',
                      borderBottom: '1px solid var(--line)', background: 'var(--surface-2)',
                      position: 'sticky', top: 0,
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {previa.linhas.map(linha => {
                  const marcada = selecao.has(linha.linha)
                  const subiu = Number(linha.delta_unitario) > 0
                  // Sem preço novo: não se clica, não se aplica, e a linha diz por quê.
                  const semPreco = linha.descontinuado
                  return (
                    <tr
                      key={linha.linha}
                      className={semPreco ? undefined : 'orc-linha'}
                      onClick={semPreco ? undefined : () => setSelecao(s => {
                        const p = new Set(s)
                        if (p.has(linha.linha)) p.delete(linha.linha)
                        else p.add(linha.linha)
                        return p
                      })}
                      style={{
                        cursor: semPreco ? 'default' : 'pointer',
                        background: semPreco
                          ? 'var(--accent-soft)'
                          : marcada ? 'var(--accent-soft)' : undefined,
                      }}
                    >
                      <td style={{ padding: '6px 10px', borderBottom: '1px solid var(--line-2)' }}>
                        {semPreco
                          ? <AlertTriangle size={13} style={{ color: 'var(--accent-ink)' }} />
                          : <input type="checkbox" checked={marcada} readOnly style={{ accentColor: 'var(--accent)' }} />}
                      </td>
                      <td style={{ padding: '6px 10px', borderBottom: '1px solid var(--line-2)', ...mono, color: 'var(--ink-3)' }}>{linha.codigo_eap}</td>
                      <td style={{ padding: '6px 10px', borderBottom: '1px solid var(--line-2)', maxWidth: 300 }}>
                        <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {linha.descricao}
                        </div>
                        {semPreco && (
                          <div style={{ fontSize: 11, color: 'var(--accent-ink)', whiteSpace: 'normal', marginTop: 2 }}>
                            {linha.motivo}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: '6px 10px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: 'var(--ink-3)' }}>{brl(linha.custo_antes)}</td>
                      <td style={{ padding: '6px 10px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: semPreco ? 'var(--accent-ink)' : 'var(--ink)' }}>
                        {/* Nem zero, nem vazio: o preço continua sendo o que era, e a
                            data-base dele é a informação que decide a leitura da planilha. */}
                        {semPreco
                          ? `mantido · ${linha.data_base_antes ? mesBR(linha.data_base_antes) : 'sem data'}`
                          : brl(linha.custo_depois)}
                      </td>
                      <td style={{ padding: '6px 10px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: subiu ? 'var(--danger-ink)' : 'var(--good-ink)' }}>
                        {semPreco ? '—' : linha.delta_pct ? `${subiu ? '+' : ''}${pct(linha.delta_pct, 1)}` : '—'}
                      </td>
                      <td style={{ padding: '6px 10px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: subiu ? 'var(--danger-ink)' : 'var(--good-ink)' }}>
                        {semPreco ? '—' : brl(linha.delta_total)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 9 }}>
            Nada foi aplicado ainda. Depois de aplicar, o lote fica no histórico com um
            <b> desfazer</b> que restaura preço e procedência.
          </p>
        </>
      )}
    </Modal>
  )
}

function ModalExportar({ orcamentoId, onFechar, onRecado }: {
  orcamentoId: number; onFechar: () => void; onRecado: (m: string) => void
}) {
  const [baixando, setBaixando] = useState('')
  const [erro, setErro] = useState('')

  const baixar = async (rotulo: string, params: Parameters<typeof baixarExportacao>[1]) => {
    setErro('')
    setBaixando(rotulo)
    try {
      const nome = await baixarExportacao(orcamentoId, params)
      onRecado(`${nome} baixado.`)
      onFechar()
    } catch {
      setErro('Não foi possível gerar o arquivo. Se for PDF, o servidor precisa do WeasyPrint.')
    } finally {
      setBaixando('')
    }
  }

  const opcoes: { rotulo: string; apoio: string; params: Parameters<typeof baixarExportacao>[1] }[] = [
    { rotulo: 'Planilha sintética (XLSX)', apoio: 'a planilha inteira, um serviço por linha, com o custo fechado', params: { formato: 'xlsx', nivel: 'sintetico' } },
    { rotulo: 'Planilha analítica (XLSX)', apoio: 'cada serviço aberto nos insumos que formam o custo', params: { formato: 'xlsx', nivel: 'analitico' } },
    { rotulo: 'Planilha analítica (PDF)', apoio: 'para arquivar e assinar — layout fixo', params: { formato: 'pdf', nivel: 'analitico' } },
    { rotulo: 'Curva ABC (XLSX)', apoio: 'a lista que vai para a negociação de compra', params: { peca: 'curva-abc' } },
    { rotulo: 'Cronograma (XLSX)', apoio: 'etapas × competências e o desembolso previsto', params: { peca: 'cronograma' } },
  ]

  return (
    <Modal titulo="Exportar" onClose={onFechar} rodape={<Btn onClick={onFechar}>Fechar</Btn>}>
      {erro && <Aviso tom="danger">{erro}</Aviso>}
      <div style={{ display: 'grid', gap: 8 }}>
        {opcoes.map(o => (
          <Card
            key={o.rotulo}
            className="orc-lift"
            onClick={() => !baixando && baixar(o.rotulo, o.params)}
            style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '11px 14px', cursor: 'pointer' }}
          >
            <Download size={15} style={{ color: 'var(--accent-ink)' }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>{o.rotulo}</div>
              <div style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{o.apoio}</div>
            </div>
            {baixando === o.rotulo && <Spinner />}
          </Card>
        ))}
      </div>
      <div style={{ height: 12 }} />
      <p style={{ fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.55 }}>
        Toda peça sai com o cabeçalho completo — obra, versão, data-base, regime de encargos e BDI.
        Planilha de custo sem data-base declarada não é conferível.
      </p>
    </Modal>
  )
}

function DrawerMemoria({ item, onFechar }: { item: ItemOrcado; onFechar: () => void }) {
  const { data, isLoading, isError } = useMemoria(item.item_orcado_id)
  return (
    <Drawer titulo={`Memória de cálculo · ${item.descricao}`} onClose={onFechar}>
      {isLoading ? <Loading /> : isError || !data ? (
        <Aviso tom="amber">
          Esta linha ainda não foi explodida em insumos. Use <b>Explodir composição</b> no menu da
          linha para abrir a composição do catálogo em coeficientes.
        </Aviso>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14, marginBottom: 16 }}>
            <Info k="Unidade" v={data.unidade || '—'} />
            <Info k="Custo unitário" v={brl(data.custo_unitario)} m />
            <Info k="Soma da composição" v={brl(data.total_composicao)} m />
          </div>
          <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginBottom: 14 }}>
            {Object.entries(data.por_categoria).map(([categoria, resumo]) => (
              <Pill key={categoria} kind="slate">{categoria}: {brl(resumo.valor)} ({pct(resumo.pct, 0)})</Pill>
            ))}
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr>
                {['Insumo', 'Und', 'Coef.', 'Custo unit.', 'Parcela'].map((h, i) => (
                  <th key={h} style={{ ...CAPS, textAlign: i >= 2 ? 'right' : 'left', padding: '6px 7px', borderBottom: '1px solid var(--line)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.insumos.map(i => (
                <tr key={i.insumo_id}>
                  <td style={{ padding: '6px 7px', borderBottom: '1px solid var(--line-2)', color: 'var(--ink-2)' }}>{i.descricao}</td>
                  <td style={{ padding: '6px 7px', borderBottom: '1px solid var(--line-2)', color: 'var(--ink-3)' }}>{i.unidade}</td>
                  <td style={{ padding: '6px 7px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono }}>{num(i.coeficiente)}</td>
                  <td style={{ padding: '6px 7px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono }}>{brl(i.custo_unitario)}</td>
                  <td style={{ padding: '6px 7px', borderBottom: '1px solid var(--line-2)', textAlign: 'right', ...mono, color: 'var(--ink)' }}>{brl(i.custo_no_item)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Drawer>
  )
}

function DrawerPrecoReal({ item, podeAplicar, onFechar, onAplicado }: {
  item: ItemOrcado; podeAplicar: boolean; onFechar: () => void; onAplicado: () => void
}) {
  const { data, isLoading } = usePrecoReal(item.item_orcado_id)
  const aplicar = useAplicarPrecoReal()
  const referencia = Number(item.custo_unitario)

  const linha = (rotulo: string, valor: string | null, origem: 'scm' | 'sil', apoio: string, destino: string) => {
    const n = valor === null ? null : Number(valor)
    const delta = n === null || referencia === 0 ? null : ((n - referencia) / referencia) * 100
    return (
      <Card style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 10 }}>
        <div style={{ flex: 1 }}>
          <div style={{ ...CAPS }}>{rotulo}</div>
          <div style={{ ...mono, fontSize: 19, fontWeight: 700, color: n === null ? 'var(--ink-3)' : 'var(--ink)' }}>
            {n === null ? 'sem histórico' : brl(valor)}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
            {apoio} · <Link to={destino} style={{ color: 'var(--net-ink)', textDecoration: 'none' }}>abrir módulo ↗</Link>
          </div>
        </div>
        {delta !== null && (
          <Pill kind={delta > 0 ? 'danger' : 'good'}>
            {delta > 0 ? '+' : ''}{delta.toFixed(1)}% vs. tabela
          </Pill>
        )}
        {podeAplicar && n !== null && (
          <Btn tam="sm" variant="primary" disabled={aplicar.isPending}
            onClick={async () => { await aplicar.mutateAsync({ id: item.item_orcado_id, origem }); onAplicado() }}>
            Adotar
          </Btn>
        )}
      </Card>
    )
  }

  return (
    <Drawer titulo={`Preço real · ${item.descricao}`} onClose={onFechar}>
      {isLoading ? <Loading /> : !data ? (
        <Aviso tom="amber">Esta linha não está ligada a um item do catálogo, então não há histórico de compra ou de estoque para comparar.</Aviso>
      ) : (
        <>
          <Card style={{ marginBottom: 14, background: 'var(--inset)' }}>
            <div style={{ ...CAPS }}>Preço de tabela na planilha</div>
            <div style={{ ...mono, fontSize: 19, fontWeight: 700, color: 'var(--ink)' }}>{brl(item.custo_unitario)}</div>
            <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
              {item.fonte_referencia || 'própria'} {item.codigo_referencia} · data-base {mesBR(item.data_base_preco)}
            </div>
          </Card>
          {linha('Preço médio pago (Suprimentos)', data.scm.preco_medio,
            'scm', `${num(data.scm.quantidade_comprada, 2)} comprados`, '/app/scm')}
          {linha('Custo médio em estoque', data.sil.custo_medio,
            'sil', `${num(data.sil.quantidade_em_estoque, 2)} em estoque`, '/app/sil')}
          <Aviso>
            Adotar o preço real troca o snapshot desta linha e marca a fonte como própria. O preço da
            base referencial fica registrado na observação — orçamento aprovado é régua histórica.
          </Aviso>
        </>
      )}
    </Drawer>
  )
}

function FormTaxas({ bdi, encargos, regime, salvando, onSalvar }: {
  bdi: string; encargos: string; regime: string; salvando: boolean
  onSalvar: (dados: { bdi_percentual: string; encargos_sociais_percentual: string; regime_encargos: string }) => void
}) {
  const [form, setForm] = useState({ bdi, encargos, regime })
  return (
    <>
      <Field label="BDI (%)" dica="Percentual resultante que multiplica cada linha analítica. A composição analítica do Acórdão 2622/2013-TCU fica na aba de BDI.">
        <input value={form.bdi} onChange={e => setForm(f => ({ ...f, bdi: e.target.value }))} style={{ ...inp, ...mono }} />
      </Field>
      <Field label="Encargos sociais (%)" dica="Incide só sobre mão de obra na explosão da composição.">
        <input value={form.encargos} onChange={e => setForm(f => ({ ...f, encargos: e.target.value }))} style={{ ...inp, ...mono }} />
      </Field>
      <Field label="Regime">
        <Select value={form.regime} onChange={e => setForm(f => ({ ...f, regime: e.target.value }))} style={{ width: '100%', maxWidth: 'none' }}>
          <option value="onerado">Onerado</option>
          <option value="desonerado">Desonerado</option>
          <option value="na">Não se aplica</option>
        </Select>
      </Field>
      <Btn variant="primary" disabled={salvando} onClick={() => onSalvar({
        bdi_percentual: paraDecimal(form.bdi),
        encargos_sociais_percentual: paraDecimal(form.encargos),
        regime_encargos: form.regime,
      })}>Salvar e recalcular</Btn>
    </>
  )
}

/** Os quatro tipos existem porque **não** são a mesma coisa para quem lê a
 *  planilha depois: dois mexem no escopo, um mexe no preço sem mexer no escopo,
 *  e um conserta erro. Escolher errado aqui vira histórico de revisão errado no
 *  contrato — e o histórico é o que se mostra numa auditoria. */
const TIPOS_REVISAO = [
  { valor: 'aditivo', rotulo: 'Aditivo', efeito: 'Acrescenta serviço ou quantidade ao aprovado. O valor sobe.' },
  { valor: 'supressao', rotulo: 'Supressão', efeito: 'Retira serviço ou quantidade do aprovado. O valor desce.' },
  { valor: 'reequilibrio', rotulo: 'Reequilíbrio', efeito: 'Mesmo escopo, preço corrigido — a variação de custo quebrou a equação.' },
  { valor: 'correcao', rotulo: 'Correção', efeito: 'Conserta erro da planilha (quantidade, item trocado) sem mudar o combinado.' },
]

function ModalRevisar({ salvando, onFechar, onRevisar }: {
  salvando: boolean; onFechar: () => void; onRevisar: (tipo: string, motivo: string) => void
}) {
  const [tipo, setTipo] = useState('aditivo')
  const [motivo, setMotivo] = useState('')
  const [erro, setErro] = useState('')
  return (
    <Modal
      titulo="Revisar orçamento aprovado"
      largura={580}
      onClose={onFechar}
      rodape={
        <>
          <Btn onClick={onFechar}>Cancelar</Btn>
          <Btn variant="primary" disabled={salvando} onClick={() => {
            if (!motivo.trim()) { setErro('Escreva o motivo — é ele que justifica a revisão no histórico.'); return }
            onRevisar(tipo, motivo.trim())
          }}>Criar próxima versão</Btn>
        </>
      }
    >
      {erro && <Aviso tom="danger">{erro}</Aviso>}

      {/* Três fatos, três linhas. Antes era um parágrafo só com os três dentro,
          e o do meio — o que garante que a medição já feita não se mexe — era
          justamente o que se perdia na leitura. */}
      <Aviso tom="amber">
        <Upload size={15} style={{ flex: 'none', marginTop: 1 }} />
        <span style={{ minWidth: 0 }}>
          <b>O que acontece ao confirmar:</b>
          <ul style={{ margin: '5px 0 0', paddingLeft: 17, lineHeight: 1.65 }}>
            <li>Nasce uma versão nova, em <b>rascunho</b>, com a árvore inteira copiada.</li>
            <li>A versão atual passa a <b>superada</b> — continua consultável e continua sendo a régua do momento em que valeu.</li>
            <li>Medições já feitas <b>não</b> mudam de base: elas seguem apontando para a versão contra a qual foram medidas.</li>
          </ul>
        </span>
      </Aviso>

      <div style={{ height: 16 }} />

      <div style={{ ...CAPS, fontSize: 9, marginBottom: 7 }}>Tipo da revisão</div>
      <div style={{ display: 'grid', gap: 6 }}>
        {TIPOS_REVISAO.map(t => {
          const marcado = tipo === t.valor
          return (
            <button
              key={t.valor}
              onClick={() => setTipo(t.valor)}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 9, width: '100%', textAlign: 'left',
                padding: '9px 11px', cursor: 'pointer',
                borderRadius: 'var(--r-sm)',
                border: `1px solid ${marcado ? 'var(--accent)' : 'var(--line)'}`,
                background: marcado ? 'var(--accent-soft)' : 'var(--surface)',
              }}
            >
              <span style={{
                flex: 'none', width: 13, height: 13, marginTop: 2, borderRadius: 99,
                border: `2px solid ${marcado ? 'var(--accent)' : 'var(--line-2)'}`,
                background: marcado ? 'var(--accent)' : 'transparent',
                boxShadow: marcado ? 'inset 0 0 0 2px var(--surface)' : undefined,
              }} />
              <span style={{ minWidth: 0 }}>
                <span style={{ display: 'block', fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>{t.rotulo}</span>
                <span style={{ display: 'block', fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>{t.efeito}</span>
              </span>
            </button>
          )
        })}
      </div>

      <div style={{ height: 16 }} />

      <Field
        label="Motivo"
        dica="Fica gravado no histórico da revisão, junto com o valor antes e depois — é o que responde 'por que este contrato mudou?' meses depois."
      >
        <textarea
          value={motivo}
          onChange={e => setMotivo(e.target.value)}
          rows={3}
          placeholder="Ex.: Aditivo de 120 m² de laje por alteração de projeto aprovada em 12/07."
          style={{ ...inp, resize: 'vertical', fontFamily: 'var(--sans)', lineHeight: 1.5 }}
        />
      </Field>
    </Modal>
  )
}
