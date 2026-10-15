import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Navigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Calculator, CalendarDays, ChevronDown, ClipboardPaste, Columns3, Diamond, GanttChartSquare, Keyboard, Layers, LayoutTemplate, Link2, ListTree, Plus, TrendingUp, Truck, Undo2, X,
} from 'lucide-react'
import { BotaoExportar, Btn, Card, Empty, Loading, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { dateToBR } from '@/utils/dates'
import * as api from '../api/pdcaApi'
import { buscarFuncionarios, plano as planoApi, precedencias } from '../api/montagemApi'
import { linhasVisiveis, todosOsPais } from '../arvore'
import { usePdca } from '../contexto'
import {
  useCalendarios, useDescartarRascunho, useGantt, useLinhaDeBalanco, useLocais, usePlanoEmEdicao,
  usePublicarPlano, useReplanejar, useRestricoes,
} from '../hooks'
import { useMontagem } from '../montagem'
import type { Atividade, Cronograma, Precedencia, Restricao } from '../types'
import { AssistenteDoPlano, type Seguimento } from '../components/AssistenteDoPlano'
import { CampoData } from '../components/CampoData'
import {
  AvisoDoOrcamento, DialogoDeExclusao, DialogoDeImportacao, DialogoDeModelo, DialogoDoOrcamento, EditorDeLigacao,
} from '../components/DialogosDoPlano'
import { GanttSvg } from '../components/GanttSvg'
import { GradeEap } from '../components/GradeEap'
import { janelaDoPlano } from '../arvore'
import {
  COLUNAS, COLUNAS_PADRAO, ESCALAS, ZOOM_MAX, ZOOM_MIN, type ColunaId, type Zoom,
} from '../grade'
import { LinhaDeBalancoSvg } from '../components/LinhaDeBalancoSvg'
import { PainelCalendario } from '../components/PainelCalendario'
import { PainelLocais } from '../components/PainelLocais'
import { PainelSuprimentos } from '../components/PainelSuprimentos'

type Vista = 'cronograma' | 'suprimentos' | 'ritmo' | 'locais' | 'expediente'
type Dialogo = { tipo: 'importar'; texto?: string } | { tipo: 'orcamento'; orcamento?: number } | { tipo: 'modelo' } | null

const VISTAS: { chave: Vista; rotulo: string; icone: typeof GanttChartSquare }[] = [
  { chave: 'cronograma', rotulo: 'Cronograma', icone: GanttChartSquare },
  { chave: 'suprimentos', rotulo: 'Suprimentos', icone: Truck },
  { chave: 'ritmo', rotulo: 'Ritmo', icone: TrendingUp },
  { chave: 'locais', rotulo: 'Locais', icone: Layers },
  { chave: 'expediente', rotulo: 'Expediente', icone: CalendarDays },
]

const CHAVE_COLUNAS = 'pdca.plano.colunas'
const CHAVE_ZOOM = 'pdca.plano.zoom'

function zoomGuardado(): Zoom {
  try {
    const lido = Number(localStorage.getItem(CHAVE_ZOOM))
    if (Number.isFinite(lido) && lido >= ZOOM_MIN && lido <= ZOOM_MAX) return lido
  } catch { /* sem armazenamento: usa o padrão */ }
  return 7
}

function colunasGuardadas(): ColunaId[] {
  try {
    const bruto = localStorage.getItem(CHAVE_COLUNAS)
    const lidas = bruto ? (JSON.parse(bruto) as ColunaId[]) : null
    if (Array.isArray(lidas) && lidas.includes('nome')) return lidas
  } catch { /* sem armazenamento: usa o padrão */ }
  return COLUNAS_PADRAO
}

/** O posto do planejamento. Quatro vistas sobre **o mesmo plano**, e a
 *  montagem inteira aqui dentro: o assistente para a obra sem plano, a grade
 *  no molde do MS Project, o Gantt que se arrasta e se liga, colar do Excel,
 *  abrir o XML do Project, gerar do orçamento, trazer um modelo — tudo com
 *  desfazer e com o prazo recalculado a cada gesto. */
export default function PlanoPage() {
  const { obraId, selecao, selecionar, planoEscolhido, escolherPlano } = usePdca()
  const { hasPermission } = useAuth()
  // A vista mora na URL (`?vista=locais`): o Inspetor e os avisos levam direto
  // a ela, e voltar no navegador volta à vista anterior.
  const [params, setParams] = useSearchParams()
  const vista: Vista = VISTAS.find((v) => v.chave === params.get('vista'))?.chave ?? 'cronograma'
  const setVista = (v: Vista) => setParams((atual) => {
    const nova = new URLSearchParams(atual)
    if (v === 'cronograma') nova.delete('vista')
    else nova.set('vista', v)
    return nova
  })
  const [zoom, setZoom] = useState<Zoom>(zoomGuardado)
  const rolagem = useRef<HTMLDivElement>(null)
  const [mostrarBase, setMostrarBase] = useState(true)
  const [fechados, setFechados] = useState<Set<number>>(new Set())
  const [colunas, setColunas] = useState<ColunaId[]>(colunasGuardadas)
  const [dialogo, setDialogo] = useState<Dialogo>(null)
  const [ligacao, setLigacao] = useState<{ p: Precedencia; ponto: { x: number; y: number } } | null>(null)
  const [seguimento, setSeguimento] = useState<Seguimento>(null)
  const [menuAberto, setMenuAberto] = useState(false)
  const [excluindo, setExcluindo] = useState<Atividade[] | null>(null)
  const [atalhos, setAtalhos] = useState(false)
  const ancoraMontar = useRef<HTMLSpanElement>(null)
  const [replanejando, setReplanejando] = useState(false)
  const [motivo, setMotivo] = useState('')

  const {
    plano, planos, vigente, rascunho, isLoading: carregandoPlanos,
  } = usePlanoEmEdicao(obraId, planoEscolhido)
  const gantt = useGantt(plano?.cronograma_id)
  const balanco = useLinhaDeBalanco(plano?.cronograma_id, vista === 'ritmo')
  const publicar = usePublicarPlano(plano?.cronograma_id)
  const replanejar = useReplanejar(plano?.cronograma_id)
  const descartar = useDescartarRascunho()
  const { data: locais = [] } = useLocais(obraId, vista === 'cronograma')
  const { data: calendarios = [] } = useCalendarios(obraId)
  const { data: restricoes = [] } = useRestricoes(obraId)
  const funcionarios = useQuery({
    queryKey: ['pdca', 'funcionarios'], queryFn: buscarFuncionarios,
    staleTime: 5 * 60_000, retry: false, enabled: colunas.includes('responsavel'),
  })

  const atividades = useMemo(() => gantt.data?.atividades ?? [], [gantt.data])
  const rede = useMemo(() => gantt.data?.precedencias ?? [], [gantt.data])
  const linhas = useMemo(() => linhasVisiveis(atividades, fechados), [atividades, fechados])
  // As restrições pendem do plano em execução; no rascunho, a linha mostra as
  // da gêmea (mesmo código EAP) — que é para onde elas vão ao publicar.
  const restricoesPorAtividade = useMemo(() => {
    const ids = new Set(atividades.map((a) => a.atividade_id))
    const porCodigo = new Map(atividades.map((a) => [a.codigo, a.atividade_id]))
    const m = new Map<number, Restricao[]>()
    for (const r of restricoes) {
      const alvo = ids.has(r.atividade) ? r.atividade : porCodigo.get(r.atividade_codigo)
      if (alvo != null) m.set(alvo, [...(m.get(alvo) ?? []), r])
    }
    return m
  }, [restricoes, atividades])
  useEffect(() => {
    try { localStorage.setItem(CHAVE_ZOOM, String(zoom)) } catch { /* idem */ }
  }, [zoom])

  const montagem = useMontagem({ cronogramaId: plano?.cronograma_id, obraId, atividades, precedencias: rede })

  // O que a pessoa recolheu fica recolhido — por plano, e entre uma visita e outra.
  const chaveRecolhidas = plano ? `pdca.plano.recolhidas.${plano.cronograma_id}` : null
  useEffect(() => {
    if (!chaveRecolhidas) return
    try {
      const lidas = JSON.parse(localStorage.getItem(chaveRecolhidas) ?? '[]')
      setFechados(new Set(Array.isArray(lidas) ? lidas : []))
    } catch { setFechados(new Set()) }
  }, [chaveRecolhidas])
  useEffect(() => {
    if (!chaveRecolhidas) return
    try { localStorage.setItem(chaveRecolhidas, JSON.stringify([...fechados])) } catch { /* idem */ }
  }, [chaveRecolhidas, fechados])
  useEffect(() => {
    try { localStorage.setItem(CHAVE_COLUNAS, JSON.stringify(colunas)) } catch { /* idem */ }
  }, [colunas])

  // O que o assistente deixou para depois de o plano existir.
  useEffect(() => {
    if (!plano || !seguimento) return
    setDialogo(seguimento === 'orcamento' ? { tipo: 'orcamento' } : { tipo: 'importar' })
    setSeguimento(null)
  }, [plano, seguimento])

  // Vindo do botão "Gerar o plano no PDCA" do cronograma do Orçamento.
  const doOrcamento = params.get('do_orcamento')
  useEffect(() => {
    if (!plano || !doOrcamento) return
    setDialogo({ tipo: 'orcamento', orcamento: Number(doOrcamento) || undefined })
    const proximo = new URLSearchParams(params)
    proximo.delete('do_orcamento')
    setParams(proximo, { replace: true })
  }, [plano, doOrcamento, params, setParams])

  // Ctrl+Z em qualquer lugar do posto: Gantt, Inspetor, depois de um diálogo.
  // Só o campo de **texto** em que se está digitando fica com o Ctrl+Z dele
  // (desfazer a última letra); seletor, caixa de marcar e botão não seguram.
  const desfazerRef = useRef(montagem.desfazer)
  desfazerRef.current = montagem.desfazer
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.defaultPrevented || !(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'z' || e.shiftKey) return
      const alvo = e.target as HTMLElement
      const digitando = alvo.closest('textarea, [contenteditable="true"]')
        || (alvo instanceof HTMLInputElement && ['text', 'search', 'number', 'email', 'url', 'tel', ''].includes(alvo.type))
      if (digitando) return
      e.preventDefault()
      void desfazerRef.current()
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [])

  const vistaAntiga = params.get('vista')
  if (vistaAntiga === 'avanco' || vistaAntiga === 'custo') {
    return <Navigate to={`../controle?aba=${vistaAntiga}`} replace />
  }

  if (carregandoPlanos) return <Loading o="o plano da obra" />

  if (!plano) {
    if (!hasPermission('pdca.cronograma.edit')) {
      return (
        <div style={{ padding: '24px 26px', maxWidth: 620 }}>
          <Card><Empty>Esta obra ainda não tem plano, e você não tem permissão para criá-lo.</Empty></Card>
        </div>
      )
    }
    return <AssistenteDoPlano obraId={obraId} aoConcluir={setSeguimento} />
  }

  const cronogramaId = plano.cronograma_id
  const podeEditar = hasPermission('pdca.cronograma.edit') && plano.editavel
  const podePublicar = hasPermission('pdca.cronograma.publicar') && plano.status === 'rascunho'
  const selecionada = selecao?.tipo === 'atividade' ? selecao.id : null
  const atual = atividades.find((a) => a.atividade_id === selecionada) ?? null

  function alternar(id: number) {
    setFechados((agora) => {
      const novo = new Set(agora)
      if (novo.has(id)) novo.delete(id)
      else novo.add(id)
      return novo
    })
  }

  async function excluir(lista: Atividade[]) {
    setExcluindo(null)
    const ids = new Set(lista.flatMap((a) => [a, ...montagem.descendentes(a)]).map((a) => a.atividade_id))
    if (selecionada != null && ids.has(selecionada)) selecionar(null)
    await montagem.excluirVarias(lista)
  }

  async function criar(tipo: 'etapa' | 'atividade' | 'marco') {
    setMenuAberto(false)
    let nova: Atividade | undefined
    if (tipo === 'etapa') {
      const ultimaRaiz = [...linhas].reverse().find((l) => l.atividade.pai == null)?.atividade ?? null
      nova = await montagem.inserir({ pai: null, depoisDe: ultimaRaiz })
    } else if (tipo === 'marco') {
      nova = await montagem.inserir({
        pai: atual?.pai != null ? atividades.find((x) => x.atividade_id === atual.pai) ?? null : null,
        depoisDe: atual, marco: true,
      })
    } else if (atual && atual.tem_filhos) {
      nova = await montagem.inserir({ pai: atual })
    } else {
      nova = await montagem.inserir({
        pai: atual?.pai != null ? atividades.find((x) => x.atividade_id === atual.pai) ?? null : null,
        depoisDe: atual,
      })
    }
    if (nova) selecionar({ tipo: 'atividade', id: nova.atividade_id })
  }

  /** Cada etapa (raiz) começa quando a anterior termina. */
  async function encadearEtapas() {
    setMenuAberto(false)
    await montagem.executar(async () => {
      const fresco = await api.cronogramas.gantt(cronogramaId)
      const raizes = fresco.atividades
        .filter((a) => a.pai == null && !a.eh_marco)
        .sort((x, y) => (x.ordem - y.ordem) || x.codigo.localeCompare(y.codigo, 'pt-BR', { numeric: true }))
      for (let i = 1; i < raizes.length; i++) {
        const ja = fresco.precedencias.some((p) => p.origem === raizes[i - 1].atividade_id && p.destino === raizes[i].atividade_id)
        if (!ja) {
          await precedencias.criar({ origem: raizes[i - 1].atividade_id, destino: raizes[i].atividade_id })
        }
      }
    })
  }

  const avisoDeCalendario = !plano.calendario && atividades.some((a) => !a.calendario)
  /** A escala que faz o plano inteiro caber na largura visível ao lado da grade. */
  function caberNaTela() {
    const janela = janelaDoPlano(atividades)
    const visivel = rolagem.current?.clientWidth
    if (!janela || !visivel) return
    const grade = COLUNAS.filter((c) => colunas.includes(c.id)).reduce((s, c) => s + c.largura, 0) + 60
    setZoom(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, (visivel - grade - 48) / janela.dias)))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
          padding: '10px 18px', borderBottom: '1px solid var(--line)', background: 'var(--surface)', flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontSize: 15, fontWeight: 750, color: 'var(--ink)' }}>Plano</span>
          <Pill kind={plano.status === 'vigente' ? 'good' : plano.status === 'rascunho' ? 'accent' : 'slate'}>
            {plano.status_rotulo} · v{plano.versao}
          </Pill>
          {planos.length > 1 && (
            <select
              aria-label="Versão do plano"
              title="Trocar a versão que esta tela mostra"
              value={plano.cronograma_id}
              onChange={(e) => { selecionar(null); escolherPlano(Number(e.target.value)) }}
              style={{
                fontSize: 12, padding: '3px 6px', background: 'var(--surface)', color: 'var(--ink-2)',
                border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
              }}
            >
              {planos.map((c) => (
                <option key={c.cronograma_id} value={c.cronograma_id}>
                  v{c.versao} · {c.status_rotulo.toLowerCase()}{rotuloDaVersao(c, vigente, rascunho)}
                </option>
              ))}
            </select>
          )}
          {plano.eh_modelo && <Pill kind="info">modelo: {plano.nome_modelo}</Pill>}
        </div>

        <ConfiguracaoDoPlano
          inicio={plano.data_inicio}
          calendario={plano.calendario}
          calendarios={calendarios}
          termino={plano.termino_calculado}
          editavel={podeEditar}
          aoMudar={(corpo) => montagem.executar(() => planoApi.atualizar(cronogramaId, corpo))}
          aoCadastrarExpediente={() => setVista('expediente')}
        />

        <span style={{ flex: 1 }} />

        {/* A EAP desta versão do plano, com as datas calculadas. */}
        <BotaoExportar recurso="pdca.atividade" recorte={{ cronograma: cronogramaId }} />

        <div style={{ display: 'flex', gap: 2, background: 'var(--inset)', borderRadius: 'var(--r-sm)', padding: 2 }}>
          {VISTAS.map(({ chave, rotulo, icone: Icone }) => (
            <button
              key={chave}
              type="button"
              onClick={() => setVista(chave)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: vista === chave ? 'var(--surface)' : 'transparent',
                border: 'none', borderRadius: 5, cursor: 'pointer', padding: '5px 10px', fontSize: 12, fontWeight: 650,
                color: vista === chave ? 'var(--ink)' : 'var(--ink-3)',
                boxShadow: vista === chave ? 'var(--shadow-sm)' : 'none',
              }}
            >
              <Icone size={13} />
              {rotulo}
            </button>
          ))}
        </div>

        {podeEditar && (
          <>
            <Btn
              tam="sm"
              onClick={() => void montagem.desfazer()}
              disabled={!montagem.podeDesfazer || montagem.ocupado}
              title={montagem.proximoDesfazer ? `Desfazer: ${montagem.proximoDesfazer} (Ctrl+Z)` : 'Nada para desfazer'}
            >
              <Undo2 size={13} /> Desfazer
            </Btn>
            <span ref={ancoraMontar} style={{ display: 'inline-flex' }}>
              <Btn tam="sm" variant="brand" onClick={() => setMenuAberto((v) => !v)} aria-expanded={menuAberto}>
                <Plus size={13} /> Montar <ChevronDown size={12} />
              </Btn>
              {menuAberto && (
                <Flutuante ancora={ancoraMontar} largura={300} aoFechar={() => setMenuAberto(false)}>
                  <ItemDeMenu icone={<ListTree size={14} />} rotulo="Nova etapa" dica="no fim do plano" aoClicar={() => criar('etapa')} />
                  <ItemDeMenu icone={<Plus size={14} />} rotulo="Nova atividade" dica={atual ? (atual.tem_filhos ? `dentro de ${atual.codigo}` : `abaixo de ${atual.codigo}`) : 'no fim'} aoClicar={() => criar('atividade')} />
                  <ItemDeMenu icone={<Diamond size={13} />} rotulo="Novo marco" dica={atual ? `abaixo de ${atual.codigo}` : 'no fim'} aoClicar={() => criar('marco')} />
                  <Separador />
                  <ItemDeMenu icone={<ClipboardPaste size={14} />} rotulo="Colar do Excel / abrir MS Project" dica="linhas com hierarquia e predecessoras" aoClicar={() => { setMenuAberto(false); setDialogo({ tipo: 'importar' }) }} />
                  <ItemDeMenu icone={<Calculator size={14} />} rotulo="Trazer do orçamento" dica="as etapas do cronograma físico-financeiro" aoClicar={() => { setMenuAberto(false); setDialogo({ tipo: 'orcamento' }) }} />
                  <ItemDeMenu icone={<LayoutTemplate size={14} />} rotulo="Modelos" dica="trazer um padrão, ou salvar este" aoClicar={() => { setMenuAberto(false); setDialogo({ tipo: 'modelo' }) }} />
                  <Separador />
                  <ItemDeMenu icone={<Link2 size={14} />} rotulo="Encadear as etapas" dica="cada etapa começa quando a anterior termina" aoClicar={encadearEtapas} />
                </Flutuante>
              )}
            </span>
          </>
        )}
        {!podeEditar && hasPermission('pdca.cronograma.edit') && plano.status !== 'vigente' && (
          <Btn tam="sm" onClick={() => setDialogo({ tipo: 'modelo' })}><LayoutTemplate size={13} /> Modelos</Btn>
        )}
        {podePublicar && (
          <Btn
            tam="sm"
            variant="primary"
            onClick={() => montagem.executar(async () => { await publicar.mutateAsync(cronogramaId); montagem.zerarPilha() }, { recalcular: false })}
            disabled={publicar.isPending || atividades.length === 0}
            title="Publicar torna este plano o combinado da obra (linha de base)"
          >
            {publicar.isPending ? 'Publicando…' : 'Publicar'}
          </Btn>
        )}
      </div>

      {montagem.erro && (
        <Faixa tom="erro" aoFechar={montagem.limparErro}>{montagem.erro}</Faixa>
      )}
      {(gantt.data?.fora_do_expediente?.total ?? 0) > 0 && (() => {
        const fora = gantt.data!.fora_do_expediente!
        const dias = new Map<string, string>()
        for (const a of fora.atividades) for (const d of a.dias) dias.set(d.data, d.motivo)
        const lista = [...dias.entries()].sort(([x], [y]) => x.localeCompare(y))
        const citados = lista.slice(0, 3).map(([d, m]) => `${dateToBR(d)} (${m})`).join(', ')
        return (
          <Faixa tom="aviso">
            O expediente mudou depois do último cálculo:{' '}
            {citados ? <strong>{citados}{lista.length > 3 ? ` e mais ${lista.length - 3}` : ''}</strong> : 'um dia mudou'}
            {' '}cai dentro de {fora.total} {fora.total === 1 ? 'atividade' : 'atividades'} desta versão
            ({fora.atividades.slice(0, 3).map((a) => a.codigo).join(', ')}{fora.total > 3 ? '…' : ''}),
            {' '}e as datas ainda contam esse dia como de obra.{' '}
            {podeEditar ? (
              <button type="button" style={LINK} onClick={() => void montagem.executar(async () => undefined)}>
                Recalcular o prazo
              </button>
            ) : plano.status === 'rascunho'
              ? 'Quem edita o plano precisa recalcular o prazo.'
              : `A v${plano.versao} está congelada — as datas dela não mudam sozinhas. Para o prazo considerar este dia, replaneje (nova versão).`}
          </Faixa>
        )
      })()}
      {(montagem.avisoDoCalculo || avisoDeCalendario) && atividades.length > 0 && (
        <Faixa tom="aviso">
          {avisoDeCalendario
            ? 'O prazo não é calculado enquanto o plano não tiver expediente. Escolha o expediente no topo'
            : `O prazo não foi recalculado: ${montagem.avisoDoCalculo}`}
          {avisoDeCalendario && (
            <>
              {calendarios.length === 0 && ', ou cadastre um em '}
              {calendarios.length === 0 && (
                <button type="button" onClick={() => setVista('expediente')} style={LINK}>Expediente</button>
              )}
              .
            </>
          )}
        </Faixa>
      )}

      {plano.status === 'rascunho' && vigente && (
        <div style={{ ...FAIXA_DA_VERSAO, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ flex: 1, minWidth: 240 }}>
            <strong style={{ color: 'var(--ink-2)' }}>Rascunho v{plano.versao}</strong>
            {plano.cronograma_id === rascunho?.cronograma_id && plano.versao > vigente.versao
              ? <> — o replanejamento da v{vigente.versao}{plano.motivo_replanejamento ? ` (“${plano.motivo_replanejamento}”)` : ''}. </>
              : <> — uma sobra: a versão em montagem é outra. </>}
            Tudo aqui se edita; a obra continua seguindo a v{vigente.versao} até você publicar.
            Restrições e avanço valem para o plano em execução e passam para esta versão ao publicar.
          </span>
          <Btn tam="sm" onClick={() => { selecionar(null); escolherPlano(vigente.cronograma_id) }}>Ver a v{vigente.versao} vigente</Btn>
          {hasPermission('pdca.cronograma.edit') && (
            <Btn
              tam="sm"
              variant="perigo"
              disabled={descartar.isPending}
              onClick={() => {
                if (!window.confirm(`Descartar o rascunho v${plano.versao}? O que foi montado nele se perde; a v${vigente.versao} vigente não muda.`)) return
                void montagem.executar(async () => {
                  await descartar.mutateAsync(cronogramaId)
                  selecionar(null)
                  escolherPlano(null)
                  montagem.zerarPilha()
                }, { recalcular: false })
              }}
            >
              Descartar rascunho
            </Btn>
          )}
        </div>
      )}

      {plano.status === 'substituido' && (
        <div style={FAIXA_DA_VERSAO}>
          <strong style={{ color: 'var(--ink-2)' }}>Versão antiga (v{plano.versao})</strong> — só leitura: é a linha de base
          de uma versão posterior.{' '}
          <button type="button" style={LINK} onClick={() => { selecionar(null); escolherPlano(null) }}>Voltar à versão atual</button>
        </div>
      )}

      {plano.status === 'vigente' && rascunho && rascunho.versao > plano.versao && (
        <div style={{ ...FAIXA_DA_VERSAO, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ flex: 1, minWidth: 240 }}>
            <strong style={{ color: 'var(--ink-2)' }}>v{plano.versao} vigente</strong> — o combinado da obra; datas e estrutura
            não se editam aqui. O replanejamento está na <strong>v{rascunho.versao}</strong>, em rascunho.
          </span>
          <Btn tam="sm" variant="primary" onClick={() => { selecionar(null); escolherPlano(rascunho.cronograma_id) }}>
            Abrir o rascunho v{rascunho.versao}
          </Btn>
        </div>
      )}

      {plano.status === 'vigente' && !(rascunho && rascunho.versao > plano.versao) && (
        <div style={FAIXA_DA_VERSAO}>
          {replanejando ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <input
                autoFocus
                value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                placeholder="Por que o plano muda? (fica no histórico)"
                style={{ fontSize: 12.5, padding: '4px 8px', width: 320, background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', color: 'var(--ink)' }}
              />
              <Btn
                tam="sm"
                variant="primary"
                disabled={replanejar.isPending || motivo.trim().length < 3}
                onClick={() => montagem.executar(async () => {
                  const nova = await replanejar.mutateAsync({ id: cronogramaId, motivo: motivo.trim() })
                  setReplanejando(false)
                  setMotivo('')
                  montagem.zerarPilha()
                  // A tela vai para a versão nova — é nela que se trabalha.
                  selecionar(null)
                  escolherPlano(nova.cronograma_id)
                }, { recalcular: false })}
              >
                {replanejar.isPending ? 'Replanejando…' : 'Criar nova versão'}
              </Btn>
              <Btn tam="sm" onClick={() => { setReplanejando(false); setMotivo('') }}>Cancelar</Btn>
            </span>
          ) : (
            <>
              <strong style={{ color: 'var(--ink-2)' }}>v{plano.versao} vigente</strong> — o combinado da obra. Datas, durações e
              estrutura não se editam aqui (restrições e avanço, sim). Para mudar o plano, replaneje: abre-se a
              v{plano.versao + 1} em rascunho e esta fica como linha de base.{' '}
              {hasPermission('pdca.cronograma.replanejar') && (
                <Btn tam="sm" onClick={() => setReplanejando(true)} style={{ marginLeft: 8 }}>Replanejar</Btn>
              )}
            </>
          )}
        </div>
      )}

      <AvisoDoOrcamento cronogramaId={cronogramaId} montagem={montagem} editavel={podeEditar} />

      {vista === 'cronograma' && atividades.length > 0 && (
        <BarraDoCronograma
          zoom={zoom}
          setZoom={setZoom}
          aoCaber={caberNaTela}
          mostrarBase={mostrarBase}
          setMostrarBase={setMostrarBase}
          temBase={gantt.data?.base.tem_base ?? false}
          colunas={colunas}
          setColunas={setColunas}
          editavel={podeEditar}
          atalhos={atalhos}
          setAtalhos={setAtalhos}
          aoExpandirTudo={() => setFechados(new Set())}
          aoRecolherTudo={() => setFechados(new Set(todosOsPais(atividades)))}
        />
      )}

      <div ref={rolagem} style={{ flex: 1, minHeight: 0, overflow: 'auto', position: 'relative' }}>
        {gantt.isLoading && <Loading o="o cronograma" />}
        {gantt.isError && (
          <div style={{ padding: 26 }}>
            <Card><Empty>Não foi possível carregar o cronograma. Verifique a conexão e tente de novo.</Empty></Card>
          </div>
        )}

        {gantt.data && vista === 'cronograma' && (
          atividades.length === 0 ? (
            <PlanoVazio
              editavel={podeEditar}
              ocupado={montagem.ocupado}
              aoDigitar={() => criar('etapa')}
              aoOrcamento={() => setDialogo({ tipo: 'orcamento' })}
              aoModelo={() => setDialogo({ tipo: 'modelo' })}
              aoColar={() => setDialogo({ tipo: 'importar' })}
            />
          ) : (
            <div style={{ display: 'flex', minWidth: 'max-content' }}>
              <GradeEap
                linhas={linhas}
                avanco={gantt.data.avanco}
                colunas={colunas}
                selecionada={selecionada}
                editavel={podeEditar}
                montagem={montagem}
                locais={locais}
                funcionarios={funcionarios.isError ? null : funcionarios.data ?? []}
                restricoesPorAtividade={restricoesPorAtividade}
                aoSelecionar={(id) => selecionar({ tipo: 'atividade', id })}
                aoAlternar={alternar}
                aoColar={(texto) => setDialogo({ tipo: 'importar', texto })}
                aoExcluir={(lista) => { if (lista.length) setExcluindo(lista) }}
              />
              <GanttSvg
                linhas={linhas}
                precedencias={rede}
                base={gantt.data.base}
                avanco={gantt.data.avanco}
                zoom={zoom}
                expedientes={gantt.data.expedientes}
                mostrarBase={mostrarBase && gantt.data.base.tem_base}
                selecionada={selecionada}
                editavel={podeEditar}
                restricoesPorAtividade={restricoesPorAtividade}
                ligacaoSelecionada={ligacao?.p.precedencia_id ?? null}
                marcadas={new Set(montagem.marcadas)}
                aoSelecionar={(id) => { montagem.limparMarcas(); selecionar({ tipo: 'atividade', id }) }}
                aoReprogramar={(id, corpo) => {
                  const a = atividades.find((x) => x.atividade_id === id)
                  if (a) void montagem.reprogramar(a, corpo)
                }}
                aoLigar={(origem, destino, tipo) => { void montagem.ligar(origem, destino, tipo) }}
                aoClicarLigacao={(p, ponto) => setLigacao({ p, ponto })}
              />
            </div>
          )
        )}

        {vista === 'suprimentos' && (
          <div style={{ padding: '18px 22px' }}><PainelSuprimentos cronogramaId={cronogramaId} obraId={obraId} planoEditavel={podeEditar} /></div>
        )}
        {vista === 'ritmo' && (
          <div style={{ padding: '18px 22px' }}>
            {balanco.isLoading && <Loading o="a linha de balanço" />}
            {balanco.data && <LinhaDeBalancoSvg dados={balanco.data} />}
          </div>
        )}
        {vista === 'locais' && (
          <div style={{ padding: '18px 22px', maxWidth: 780 }}><PainelLocais obraId={obraId} /></div>
        )}
        {vista === 'expediente' && (
          <div style={{ padding: '18px 22px' }}><PainelCalendario obraId={obraId} /></div>
        )}
      </div>

      {dialogo?.tipo === 'importar' && (
        <DialogoDeImportacao cronogramaId={cronogramaId} montagem={montagem} textoInicial={dialogo.texto} aoFechar={() => setDialogo(null)} />
      )}
      {dialogo?.tipo === 'orcamento' && (
        <DialogoDoOrcamento
          cronogramaId={cronogramaId}
          montagem={montagem}
          orcamentoInicial={dialogo.orcamento}
          aoFechar={() => setDialogo(null)}
          aoGerar={(encadear) => { if (encadear) void encadearEtapas() }}
        />
      )}
      {dialogo?.tipo === 'modelo' && (
        <DialogoDeModelo
          cronogramaId={cronogramaId}
          montagem={montagem}
          ehModelo={plano.eh_modelo}
          nomeModelo={plano.nome_modelo}
          aoFechar={() => setDialogo(null)}
        />
      )}
      {excluindo && (
        <DialogoDeExclusao
          lista={excluindo}
          montagem={montagem}
          precedencias={rede}
          restricoesPorAtividade={restricoesPorAtividade}
          obraSegue={plano.status === 'vigente' || !vigente}
          aoConfirmar={() => { void excluir(excluindo) }}
          aoFechar={() => setExcluindo(null)}
        />
      )}
      {ligacao && (
        <EditorDeLigacao
          ligacao={ligacao.p}
          ponto={ligacao.ponto}
          atividades={atividades}
          montagem={montagem}
          editavel={podeEditar}
          aoFechar={() => setLigacao(null)}
        />
      )}
    </div>
  )
}

/* -- Peças do posto --------------------------------------------------------- */

const LINK = {
  background: 'none', border: 'none', padding: 0, color: 'var(--brand)', cursor: 'pointer',
  textDecoration: 'underline', font: 'inherit',
} as const

const FAIXA_DA_VERSAO = {
  padding: '7px 18px', background: 'var(--inset)', flexShrink: 0, fontSize: 12, color: 'var(--ink-3)',
  borderBottom: '1px solid var(--line-2)', lineHeight: 1.5,
} as const

/** O que cada versão é, em uma palavra, na lista do seletor. */
function rotuloDaVersao(c: Cronograma, vigente?: Cronograma, rascunho?: Cronograma): string {
  if (c.cronograma_id === vigente?.cronograma_id) return ' (o combinado)'
  if (c.cronograma_id === rascunho?.cronograma_id && (!vigente || c.versao > vigente.versao)) return ' (em montagem)'
  if (c.status === 'rascunho') return ' (sobra — pode descartar)'
  return ''
}

function Faixa(
  { tom, children, aoFechar }: { tom: 'erro' | 'aviso'; children: React.ReactNode; aoFechar?: () => void },
) {
  return (
    <div
      role={tom === 'erro' ? 'alert' : 'status'}
      style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '8px 18px', flexShrink: 0, fontSize: 12.5,
        background: tom === 'erro' ? 'var(--danger-soft)' : 'var(--accent-soft)',
        color: tom === 'erro' ? 'var(--danger-ink)' : 'var(--accent-ink)',
      }}
    >
      <span style={{ flex: 1 }}>{children}</span>
      {aoFechar && (
        <button type="button" onClick={aoFechar} aria-label="Fechar aviso" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', display: 'flex' }}>
          <X size={14} />
        </button>
      )}
    </div>
  )
}

function ConfiguracaoDoPlano(
  { inicio, calendario, calendarios, termino, editavel, aoMudar, aoCadastrarExpediente }: {
    inicio: string | null
    calendario: number | null
    calendarios: { calendario_id: number; nome: string; obra: number | null }[]
    termino: string | null
    editavel: boolean
    aoMudar: (corpo: { data_inicio?: string; calendario?: number | null }) => unknown
    aoCadastrarExpediente: () => void
  },
) {
  const estilo = {
    fontSize: 12, padding: '3px 6px', background: 'var(--surface)', color: 'var(--ink)',
    border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
  } as const
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: 'var(--ink-3)', flexWrap: 'wrap' }}>
      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        início
        {editavel ? (
          <CampoData valor={inicio} rotulo="Início do plano" aoGravar={(iso) => aoMudar({ data_inicio: iso })} estilo={estilo} />
        ) : <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>{inicio ? dateToBR(inicio) : '—'}</span>}
      </label>
      <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        expediente
        {editavel ? (
          <select
            value={calendario ?? ''}
            onChange={(e) => {
              if (e.target.value === 'novo') { aoCadastrarExpediente(); return }
              aoMudar({ calendario: e.target.value ? Number(e.target.value) : null })
            }}
            style={{ ...estilo, borderColor: calendario ? 'var(--line)' : 'var(--danger)' }}
          >
            <option value="">escolha…</option>
            {calendarios.map((c) => <option key={c.calendario_id} value={c.calendario_id}>{c.nome}</option>)}
            <option value="novo">+ Cadastrar expediente…</option>
          </select>
        ) : <span style={{ color: 'var(--ink-2)' }}>{calendarios.find((c) => c.calendario_id === calendario)?.nome ?? '—'}</span>}
      </label>
      {termino ? (
        <span>termina em <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)', fontWeight: 650 }}>{dateToBR(termino)}</span></span>
      ) : (
        <span style={{ fontStyle: 'italic' }}>sem prazo calculado</span>
      )}
    </div>
  )
}

function PlanoVazio(
  { editavel, ocupado, aoDigitar, aoOrcamento, aoModelo, aoColar }: {
    editavel: boolean; ocupado: boolean
    aoDigitar: () => void; aoOrcamento: () => void; aoModelo: () => void; aoColar: () => void
  },
) {
  if (!editavel) {
    return (
      <div style={{ padding: '24px 26px', maxWidth: 620 }}>
        <Card><Empty>Este plano ainda não tem atividades.</Empty></Card>
      </div>
    )
  }
  const opcoes = [
    { icone: <ListTree size={18} />, titulo: 'Digitar na planilha', texto: 'Cria a primeira etapa e segue pelo teclado: Insert cria a próxima linha, Tab recua.', acao: aoDigitar },
    { icone: <Calculator size={18} />, titulo: 'Trazer do orçamento', texto: 'As etapas do cronograma do orçamento, com datas, valor e Hh — o detalhe é seu.', acao: aoOrcamento },
    { icone: <LayoutTemplate size={18} />, titulo: 'Trazer um modelo', texto: 'Estrutura, durações e sequência de um padrão da empresa.', acao: aoModelo },
    { icone: <ClipboardPaste size={18} />, titulo: 'Colar do Excel / MS Project', texto: 'Cole as linhas, ou abra o XML do Project.', acao: aoColar },
  ]
  return (
    <div style={{ padding: '24px 26px', maxWidth: 860, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 14, color: 'var(--ink-2)' }}>O plano está vazio. Por onde começar?</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 10 }}>
        {opcoes.map((o) => (
          <button
            key={o.titulo}
            type="button"
            disabled={ocupado}
            onClick={o.acao}
            style={{
              textAlign: 'left', display: 'flex', flexDirection: 'column', gap: 6, padding: 14, cursor: 'pointer',
              background: 'var(--surface)', color: 'var(--ink)', border: '1px solid var(--line)', borderRadius: 'var(--r-md)',
            }}
          >
            <span style={{ color: 'var(--accent-ink)' }}>{o.icone}</span>
            <span style={{ fontSize: 13, fontWeight: 700 }}>{o.titulo}</span>
            <span style={{ fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.45 }}>{o.texto}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

/** Painel que flutua sobre a **tela inteira**, preso ao botão que o abriu e
 *  sempre dentro da janela. Ancorado ao botão com `position: absolute`, ele
 *  herdava a pilha do cabeçalho: com a janela estreita o botão quebrava para a
 *  esquerda e o menu abria por baixo do trilho dos postos e das abas. */
function Flutuante(
  { ancora, largura, children, aoFechar, papel = 'menu' }: {
    ancora: React.RefObject<HTMLElement | null>
    largura: number
    children: React.ReactNode
    aoFechar: () => void
    papel?: 'menu' | 'dialog'
  },
) {
  const [pos, setPos] = useState<{ left: number; top: number; maxHeight: number } | null>(null)
  useEffect(() => {
    const medir = () => {
      const r = ancora.current?.getBoundingClientRect()
      if (!r) return
      const margem = 8
      const left = Math.max(margem, Math.min(r.right - largura, window.innerWidth - largura - margem))
      const top = r.bottom + 4
      setPos({ left, top, maxHeight: Math.max(160, window.innerHeight - top - margem) })
    }
    medir()
    const fora = (e: MouseEvent) => {
      const alvo = e.target as HTMLElement
      if (!alvo.closest('[data-flutuante-do-plano]') && !ancora.current?.contains(alvo)) aoFechar()
    }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') aoFechar() }
    window.addEventListener('resize', medir)
    window.addEventListener('scroll', medir, true)
    window.addEventListener('mousedown', fora)
    window.addEventListener('keydown', esc)
    return () => {
      window.removeEventListener('resize', medir)
      window.removeEventListener('scroll', medir, true)
      window.removeEventListener('mousedown', fora)
      window.removeEventListener('keydown', esc)
    }
  }, [ancora, largura, aoFechar])
  if (!pos) return null
  return createPortal(
    <div
      data-flutuante-do-plano
      role={papel}
      style={{
        position: 'fixed', left: pos.left, top: pos.top, maxHeight: pos.maxHeight, overflowY: 'auto',
        zIndex: 90, width: largura, background: 'var(--surface)', border: '1px solid var(--line)',
        borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-lg)', padding: papel === 'menu' ? 4 : 10,
      }}
    >
      {children}
    </div>,
    document.body,
  )
}

function ItemDeMenu(
  { icone, rotulo, dica, aoClicar }: { icone: React.ReactNode; rotulo: string; dica?: string; aoClicar: () => void },
) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={aoClicar}
      style={{
        display: 'flex', gap: 10, alignItems: 'flex-start', width: '100%', textAlign: 'left',
        background: 'transparent', border: 'none', borderRadius: 'var(--r-sm)', padding: '7px 8px',
        cursor: 'pointer', color: 'var(--ink)',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--inset)' }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
    >
      <span style={{ color: 'var(--ink-2)', marginTop: 1 }}>{icone}</span>
      <span style={{ display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontSize: 12.5, fontWeight: 650 }}>{rotulo}</span>
        {dica && <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{dica}</span>}
      </span>
    </button>
  )
}

function Separador() {
  return <div style={{ height: 1, background: 'var(--line-2)', margin: '4px 6px' }} />
}

function BarraDoCronograma(
  {
    zoom, setZoom, aoCaber, mostrarBase, setMostrarBase, temBase, colunas, setColunas, editavel,
    atalhos, setAtalhos, aoExpandirTudo, aoRecolherTudo,
  }: {
    zoom: Zoom
    setZoom: (z: Zoom) => void
    aoCaber: () => void
    mostrarBase: boolean
    setMostrarBase: (v: boolean) => void
    temBase: boolean
    colunas: ColunaId[]
    setColunas: (c: ColunaId[]) => void
    editavel: boolean
    atalhos: boolean
    setAtalhos: (v: boolean) => void
    aoExpandirTudo: () => void
    aoRecolherTudo: () => void
  },
) {
  const [escolhendo, setEscolhendo] = useState(false)
  const ancoraColunas = useRef<HTMLSpanElement>(null)
  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
        padding: '7px 18px', borderBottom: '1px solid var(--line-2)', background: 'var(--surface-2)', flexShrink: 0,
        position: 'relative',
      }}
    >
      <EscalaDoGantt zoom={zoom} setZoom={setZoom} aoCaber={aoCaber} />

      <label
        title={temBase ? undefined : 'Aparece depois de publicar e replanejar'}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: temBase ? 'var(--ink-2)' : 'var(--ink-3)', cursor: temBase ? 'pointer' : 'not-allowed' }}
      >
        <input type="checkbox" checked={mostrarBase && temBase} disabled={!temBase} onChange={(e) => setMostrarBase(e.target.checked)} />
        Linha de base
      </label>

      <span style={{ flex: 1 }} />

      <div style={{ display: 'flex', gap: 6, position: 'relative' }}>
        <Btn tam="sm" onClick={aoExpandirTudo}>Expandir tudo</Btn>
        <Btn tam="sm" onClick={aoRecolherTudo}>Recolher tudo</Btn>
        <span ref={ancoraColunas} style={{ display: 'inline-flex' }}>
          <Btn tam="sm" onClick={() => setEscolhendo((v) => !v)}><Columns3 size={13} /> Colunas</Btn>
        </span>
        <Btn tam="sm" onClick={() => setAtalhos(!atalhos)} title="Atalhos de teclado"><Keyboard size={13} /></Btn>
        {escolhendo && (
          <Flutuante ancora={ancoraColunas} largura={190} papel="dialog" aoFechar={() => setEscolhendo(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {COLUNAS.map((c) => (
              <label key={c.id} style={{ fontSize: 12.5, display: 'flex', gap: 6, alignItems: 'center', color: c.fixa ? 'var(--ink-3)' : 'var(--ink)' }}>
                <input
                  type="checkbox"
                  disabled={c.fixa}
                  checked={colunas.includes(c.id)}
                  onChange={(e) => setColunas(e.target.checked
                    ? COLUNAS.filter((x) => x.id === c.id || colunas.includes(x.id)).map((x) => x.id)
                    : colunas.filter((x) => x !== c.id))}
                />
                {c.rotulo}
              </label>
            ))}
            <Btn tam="sm" onClick={() => setEscolhendo(false)}>Fechar</Btn>
          </div>
          </Flutuante>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11, color: 'var(--ink-3)' }}>
        <Legenda cor="var(--brand)" texto="previsto" />
        <Legenda cor="var(--good)" texto="executado" />
        <Legenda cor="var(--danger)" texto="crítica" />
        {temBase && <Legenda cor="var(--ink-3)" texto="base" />}
        <Legenda cor="var(--danger-soft)" texto="feriado / recesso" />
      </div>

      {atalhos && (
        <div
          style={{
            flexBasis: '100%', display: 'flex', flexWrap: 'wrap', gap: '4px 18px', fontSize: 11.5, color: 'var(--ink-2)',
            paddingTop: 6, borderTop: '1px dashed var(--line-2)',
          }}
        >
          {(editavel ? [
            ['setas', 'andar entre células'], ['Enter / F2 / digitar', 'editar a célula'],
            ['Enter (editando)', 'grava e desce'], ['Tab (editando)', 'grava e vai à direita'],
            ['Insert ou Shift+Enter', 'nova linha abaixo'], ['Ctrl+Enter', 'nova linha dentro'],
            ['Tab', 'recuar (entra na de cima)'], ['Shift+Tab', 'avançar (sai do grupo)'],
            ['Alt+↑ / Alt+↓', 'subir / descer'], ['Delete', 'excluir'], ['Ctrl+Z', 'desfazer'],
            ['Ctrl+V', 'colar do Excel'], ['Espaço', 'abrir / fechar etapa'],
            ['Gantt: arrastar a barra', 'muda a data'], ['Gantt: puxar a ponta', 'muda a duração'],
            ['Gantt: puxar o pino', 'liga a outra barra'], ['Gantt: clicar na seta', 'muda ou desliga'],
            ['Predecessoras', '1.2; 1.3SS+2; 4FF-1'],
          ] : [['setas', 'andar entre linhas'], ['Espaço', 'abrir / fechar etapa']]).map(([k, v]) => (
            <span key={k}><strong style={{ fontFamily: 'var(--mono)', fontWeight: 650 }}>{k}</strong> — {v}</span>
          ))}
        </div>
      )}
    </div>
  )
}

/** A escala **contínua** do Gantt: atalhos (dia, semana, mês, trimestre), o
 *  deslizante para o meio-termo, −/+ e "caber" — o plano inteiro na largura
 *  da tela. O deslizante anda em escala logarítmica: o passo de 1 para 2 px por
 *  dia vale tanto quanto o de 20 para 40, que é como o olho percebe o zoom. */
function EscalaDoGantt(
  { zoom, setZoom, aoCaber }: { zoom: Zoom; setZoom: (z: Zoom) => void; aoCaber: () => void },
) {
  const limitar = (z: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z))
  const perto = (px: number) => Math.abs(Math.log(zoom / px)) < 0.08
  const botao = (ativo: boolean) => ({
    background: ativo ? 'var(--surface)' : 'transparent',
    border: `1px solid ${ativo ? 'var(--line)' : 'transparent'}`,
    borderRadius: 5, cursor: 'pointer', padding: '3px 8px', fontSize: 11.5, fontWeight: 650,
    color: ativo ? 'var(--ink)' : 'var(--ink-3)',
  }) as const
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
      <span style={{ fontSize: 10.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700, marginRight: 2 }}>Escala</span>
      {ESCALAS.map((e) => (
        <button key={e.rotulo} type="button" onClick={() => setZoom(e.px)} style={botao(perto(e.px))}>{e.rotulo}</button>
      ))}
      <button type="button" aria-label="Afastar" title="Afastar" onClick={() => setZoom(limitar(zoom / 1.25))} style={botao(false)}>−</button>
      <input
        type="range"
        aria-label="Escala do Gantt (pixels por dia)"
        min={Math.log(ZOOM_MIN)} max={Math.log(ZOOM_MAX)} step={0.01}
        value={Math.log(zoom)}
        onChange={(e) => setZoom(limitar(Math.exp(Number(e.target.value))))}
        style={{ width: 110, accentColor: 'var(--brand)' }}
      />
      <button type="button" aria-label="Aproximar" title="Aproximar" onClick={() => setZoom(limitar(zoom * 1.25))} style={botao(false)}>+</button>
      <button type="button" onClick={aoCaber} title="O plano inteiro na largura da tela" style={botao(false)}>caber</button>
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
