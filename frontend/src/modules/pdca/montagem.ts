import { useCallback, useSyncExternalStore } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/apiClient'
import { parseApiErrors } from '@/utils/formErrors'
import * as api from './api/pdcaApi'
import { etapasDaObra, nomeLivre, plano, precedencias, renomearEtapa } from './api/montagemApi'
import { pdcaKeys } from './api/queryKeys'
import { lerPredecessoras, rotuloDaLigacao } from './importacao'
import type { Atividade, PayloadGantt, Precedencia, TipoPrecedencia } from './types'

/* --------------------------------------------------------------------------
 * A montagem do plano: as operações que a grade, o Gantt e o Inspetor fazem
 * sobre o mesmo cronograma, com **desfazer**, **seleção de várias linhas** e
 * **recálculo automático**.
 *
 * Fica num store do módulo, e não num estado de componente, porque a grade e o
 * Inspetor são irmãos na casca do posto: o Ctrl+Z da grade desfaz o que o
 * Inspetor fez, e a seleção da grade é o que o Inspetor edita em massa.
 *
 * **O desfazer é dado, não função.** *Decisão do dono, 09/10/2026:* ele vale
 * "enquanto estou na tela ou até eu finalizar o plano" — então a pilha é uma
 * lista de operações inversas serializáveis, guardada por plano no navegador:
 * sobrevive a recarregar a página e a trocar de posto, e zera ao publicar.
 * Excluir também volta: a tela fotografa a subárvore antes de apagar, e o
 * inverso é `restaurar-linhas/`, que devolve o mapa de ids antigos → novos para
 * o resto da pilha continuar apontando certo. As ligações são guardadas pelo
 * **par** (origem, destino), e não pelo id da seta, pelo mesmo motivo.
 * ------------------------------------------------------------------------ */

type Corpo = Record<string, unknown>

export interface Retrato {
  pai: number | null
  posicao: number
  atividades: Corpo[]
  ligacoes: { origem: number; destino: number; tipo: TipoPrecedencia; atraso_dias: number }[]
}

type Op =
  | { op: 'patch'; id: number; corpo: Corpo }
  | { op: 'reprogramar'; id: number; corpo: Corpo }
  | { op: 'remover'; id: number }
  | { op: 'removerEtapa'; etapa: number }
  | { op: 'mover'; id: number; pai: number | null; posicao: number | null }
  | { op: 'ligar'; origem: number; destino: number; tipo: TipoPrecedencia; atraso: number }
  | { op: 'desligarPar'; origem: number; destino: number }
  | { op: 'alterarPar'; origem: number; destino: number; tipo: TipoPrecedencia; atraso: number }
  | { op: 'predecessoras'; destino: number; itens: { origem: number; tipo: TipoPrecedencia; atraso: number }[] }
  | { op: 'renomearEtapa'; etapa: number; nome: string }
  | { op: 'restaurar'; retrato: Retrato }

interface Passo {
  rotulo: string
  ops: Op[]
}

interface Estado {
  cronogramaId: number | null
  pilha: Passo[]
  ocupado: number
  erro: string | null
  /** Por que o prazo não foi recalculado (sem calendário, ciclo…), ou nulo. */
  avisoDoCalculo: string | null
  /** As linhas marcadas para agir em lote (Ctrl/Shift+clique na grade). */
  marcadas: number[]
}

const VAZIO: Omit<Estado, 'cronogramaId'> = {
  pilha: [], ocupado: 0, erro: null, avisoDoCalculo: null, marcadas: [],
}
let estado: Estado = { cronogramaId: null, ...VAZIO }
const ouvintes = new Set<() => void>()
const TETO_DA_PILHA = 100

const chaveDaPilha = (id: number) => `pdca.plano.desfazer.v1.${id}`

function lerPilha(id: number): Passo[] {
  try {
    const bruto = localStorage.getItem(chaveDaPilha(id))
    const lida = bruto ? JSON.parse(bruto) : []
    return Array.isArray(lida) ? lida : []
  } catch {
    return []
  }
}

function mudar(parcial: Partial<Estado>) {
  estado = { ...estado, ...parcial }
  if ('pilha' in parcial && estado.cronogramaId != null) {
    try {
      if (estado.pilha.length) localStorage.setItem(chaveDaPilha(estado.cronogramaId), JSON.stringify(estado.pilha))
      else localStorage.removeItem(chaveDaPilha(estado.cronogramaId))
    } catch { /* sem armazenamento: a pilha vale só nesta aba */ }
  }
  ouvintes.forEach((o) => o())
}

function assinar(o: () => void) {
  ouvintes.add(o)
  return () => { ouvintes.delete(o) }
}

export function mensagemDe(e: unknown, padrao = 'Não foi possível concluir.'): string {
  const erros = parseApiErrors(e)
  return erros._form ?? Object.values(erros)[0] ?? padrao
}

/** Troca, em toda operação, os ids antigos pelos que a restauração devolveu. */
function remapear<T>(valor: T, mapa: Map<number, number>): T {
  const ids = new Set(['id', 'pai', 'origem', 'destino'])
  const andar = (v: unknown, chave?: string): unknown => {
    if (Array.isArray(v)) return v.map((x) => andar(x))
    if (v && typeof v === 'object') {
      return Object.fromEntries(Object.entries(v as Corpo).map(([k, x]) => [k, andar(x, k)]))
    }
    if (typeof v === 'number' && chave && ids.has(chave)) return mapa.get(v) ?? v
    return v
  }
  return andar(valor) as T
}

async function ligacoesDoPar(origem: number, destino: number): Promise<Precedencia[]> {
  const { data } = await apiClient.get('/pdca/precedencias/', { params: { origem, destino, page_size: 50 } })
  return Array.isArray(data) ? data : data.results ?? []
}

/** Deixa as predecessoras de `destino` exatamente como `itens`. */
async function aplicarPredecessoras(
  destino: number, itens: { origem: number; tipo: TipoPrecedencia; atraso: number }[],
) {
  const { data } = await apiClient.get('/pdca/precedencias/', { params: { destino, page_size: 500 } })
  const atuais: Precedencia[] = Array.isArray(data) ? data : data.results ?? []
  const desejadas = new Map(itens.map((i) => [i.origem, i]))
  for (const p of atuais) {
    const quer = desejadas.get(p.origem)
    if (!quer) await precedencias.remover(p.precedencia_id)
    else if (quer.tipo !== p.tipo || quer.atraso !== p.atraso_dias) {
      await precedencias.atualizar(p.precedencia_id, { tipo: quer.tipo, atraso_dias: quer.atraso })
    }
  }
  for (const [origem, i] of desejadas) {
    if (!atuais.some((p) => p.origem === origem)) {
      await precedencias.criar({ origem, destino, tipo: i.tipo, atraso_dias: i.atraso })
    }
  }
}

async function rodar(op: Op, cronogramaId: number): Promise<Map<number, number> | null> {
  switch (op.op) {
    case 'patch': await api.atividades.atualizar(op.id, op.corpo as Partial<Atividade>); return null
    case 'reprogramar': await plano.reprogramar(op.id, op.corpo); return null
    case 'remover': await api.atividades.remover(op.id); return null
    case 'removerEtapa': await apiClient.delete(`/etapas-obras/${op.etapa}/`); return null
    case 'mover': await plano.mover(op.id, op.pai, op.posicao); return null
    case 'ligar':
      await precedencias.criar({ origem: op.origem, destino: op.destino, tipo: op.tipo, atraso_dias: op.atraso })
      return null
    case 'desligarPar':
      for (const p of await ligacoesDoPar(op.origem, op.destino)) await precedencias.remover(p.precedencia_id)
      return null
    case 'alterarPar':
      for (const p of await ligacoesDoPar(op.origem, op.destino)) {
        await precedencias.atualizar(p.precedencia_id, { tipo: op.tipo, atraso_dias: op.atraso })
      }
      return null
    case 'predecessoras': await aplicarPredecessoras(op.destino, op.itens); return null
    case 'renomearEtapa': await renomearEtapa(op.etapa, op.nome); return null
    case 'restaurar': {
      const { mapa } = await plano.restaurar(cronogramaId, op.retrato)
      return new Map(Object.entries(mapa).map(([k, v]) => [Number(k), v]))
    }
  }
}

export interface OpcoesDaMontagem {
  cronogramaId: number | undefined
  obraId: number
  atividades: Atividade[]
  precedencias: Precedencia[]
}

export function useMontagem({ cronogramaId, obraId, atividades, precedencias: rede }: OpcoesDaMontagem) {
  const qc = useQueryClient()
  const snap = useSyncExternalStore(assinar, () => estado)

  if (cronogramaId != null && estado.cronogramaId !== cronogramaId) {
    // Cada plano tem a sua pilha; trocar de obra traz a pilha daquele plano.
    estado = { cronogramaId, ...VAZIO, pilha: lerPilha(cronogramaId) }
  }

  const invalidar = useCallback(() => {
    if (cronogramaId == null) return
    qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.gantt(cronogramaId) })
    qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.balanco(cronogramaId) })
    qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.daObra(obraId) })
    qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'etapas', obraId] })
  }, [qc, cronogramaId, obraId])

  /** Tira linhas da tela **antes** de o servidor responder: a exclusão não
   *  espera três idas e voltas para a pessoa ver o resultado. */
  const tirarDaTela = useCallback((ids: Set<number>) => {
    if (cronogramaId == null) return
    qc.setQueryData<PayloadGantt>(pdcaKeys.cronogramas.gantt(cronogramaId), (velho) => velho && ({
      ...velho,
      atividades: velho.atividades.filter((a) => !ids.has(a.atividade_id)),
      precedencias: velho.precedencias.filter((p) => !ids.has(p.origem) && !ids.has(p.destino)),
    }))
  }, [qc, cronogramaId])

  const recalcular = useCallback(async () => {
    if (cronogramaId == null) return
    try {
      await api.cronogramas.calcular(cronogramaId)
      mudar({ avisoDoCalculo: null })
    } catch (e) {
      mudar({ avisoDoCalculo: mensagemDe(e, 'O prazo não pôde ser recalculado.') })
    }
  }, [cronogramaId])

  /** Roda a ação, empilha o inverso, recalcula o CPM e atualiza a tela. O erro
   *  vai para a faixa do posto em vez de estourar no componente. */
  const executar = useCallback(async <T,>(
    acao: () => Promise<T>,
    opcoes: { desfazer?: (r: T) => Passo | null; recalcular?: boolean } = {},
  ): Promise<T | undefined> => {
    mudar({ ocupado: estado.ocupado + 1, erro: null })
    try {
      const resultado = await acao()
      const passo = opcoes.desfazer?.(resultado)
      if (passo && passo.ops.length) mudar({ pilha: [...estado.pilha, passo].slice(-TETO_DA_PILHA) })
      if (opcoes.recalcular !== false) await recalcular()
      return resultado
    } catch (e) {
      mudar({ erro: mensagemDe(e) })
      return undefined
    } finally {
      mudar({ ocupado: Math.max(0, estado.ocupado - 1) })
      invalidar()
    }
  }, [recalcular, invalidar])

  const desfazer = useCallback(async () => {
    const passo = estado.pilha[estado.pilha.length - 1]
    if (!passo || estado.ocupado || cronogramaId == null) return
    mudar({ pilha: estado.pilha.slice(0, -1), ocupado: estado.ocupado + 1, erro: null })
    try {
      let ops = [...passo.ops]
      while (ops.length) {
        const [op, ...resto] = ops
        const mapa = await rodar(op, cronogramaId)
        ops = resto
        if (mapa && mapa.size) {
          ops = remapear(ops, mapa)
          mudar({ pilha: remapear(estado.pilha, mapa) })
        }
      }
      await recalcular()
    } catch (e) {
      mudar({ erro: `Não foi possível desfazer "${passo.rotulo}": ${mensagemDe(e)}` })
    } finally {
      mudar({ ocupado: Math.max(0, estado.ocupado - 1) })
      invalidar()
    }
  }, [cronogramaId, recalcular, invalidar])

  /* -- helpers da árvore ------------------------------------------------- */

  const porId = new Map(atividades.map((a) => [a.atividade_id, a]))
  const irmas = (pai: number | null, sem?: number) => atividades
    .filter((a) => (a.pai ?? null) === pai && a.atividade_id !== sem)
    .sort((x, y) => (x.ordem - y.ordem) || x.codigo.localeCompare(y.codigo, 'pt-BR', { numeric: true }))
  const posicaoDe = (a: Atividade) => irmas(a.pai ?? null).findIndex((x) => x.atividade_id === a.atividade_id)
  const ordemNaTela = (lista: Atividade[]) => [...lista].sort(
    (x, y) => x.codigo.localeCompare(y.codigo, 'pt-BR', { numeric: true }),
  )
  const descendentes = (a: Atividade): Atividade[] => {
    const saida: Atividade[] = []
    const descer = (id: number) => atividades.filter((x) => x.pai === id).forEach((f) => { saida.push(f); descer(f.atividade_id) })
    descer(a.atividade_id)
    return saida
  }
  /** Só as de cima: marcar a etapa e uma filha dela é agir sobre a etapa. */
  const soAsDeCima = (lista: Atividade[]) => {
    const ids = new Set(lista.map((a) => a.atividade_id))
    return lista.filter((a) => {
      let p = a.pai
      while (p != null) { if (ids.has(p)) return false; p = porId.get(p)?.pai ?? null }
      return true
    })
  }

  /** A etapa do plano (raiz) é a etapa da obra: renomear uma renomeia a outra,
   *  salvo se outra atividade usa a mesma etapa. */
  const etapaDaRaiz = (a: Atividade) => (
    !a.pai && a.etapa != null && !atividades.some((x) => x.etapa === a.etapa && x.atividade_id !== a.atividade_id)
      ? a.etapa : null
  )

  function retratar(a: Atividade): Retrato {
    const sub = [a, ...descendentes(a)]
    const ids = new Set(sub.map((x) => x.atividade_id))
    const campos = [
      'nome', 'ordem', 'duracao_dias', 'eh_marco', 'nao_comecar_antes_de', 'calendario', 'local',
      'etapa', 'item_orcado', 'responsavel', 'peso_informado', 'antecedencia_compra_dias', 'observacao',
    ] as const
    return {
      pai: a.pai ?? null,
      posicao: posicaoDe(a),
      atividades: sub.map((x) => ({
        id: x.atividade_id, pai: x.pai ?? null,
        ...Object.fromEntries(campos.map((c) => [c, x[c as keyof Atividade] ?? null])),
      })),
      ligacoes: rede
        .filter((p) => ids.has(p.origem) || ids.has(p.destino))
        .map((p) => ({ origem: p.origem, destino: p.destino, tipo: p.tipo, atraso_dias: p.atraso_dias })),
    }
  }

  /* -- operações --------------------------------------------------------- */

  function salvar(a: Atividade, corpo: Partial<Atividade>, rotulo = 'editar') {
    return salvarVarias([a], corpo, rotulo)
  }

  /** O mesmo campo em várias linhas — a edição em lote do painel de seleção. */
  function salvarVarias(lista: Atividade[], corpo: Partial<Atividade>, rotulo = 'editar') {
    const inversas: Op[] = []
    return executar(async () => {
      for (const a of lista) {
        const anterior = Object.fromEntries(Object.keys(corpo).map((k) => [k, a[k as keyof Atividade] ?? null]))
        const etapa = corpo.nome ? etapaDaRaiz(a) : null
        if (etapa != null && corpo.nome) {
          await renomearEtapa(etapa, corpo.nome)
          inversas.push({ op: 'renomearEtapa', etapa, nome: a.nome })
        }
        await api.atividades.atualizar(a.atividade_id, corpo)
        inversas.push({ op: 'patch', id: a.atividade_id, corpo: anterior })
      }
    }, { desfazer: () => ({ rotulo, ops: inversas }) })
  }

  /** Data e duração pelo gesto da barra — o servidor já recalcula. */
  function reprogramar(a: Atividade, corpo: { nao_comecar_antes_de?: string | null; duracao_dias?: number }) {
    const anterior: Corpo = {}
    if ('nao_comecar_antes_de' in corpo) anterior.nao_comecar_antes_de = a.nao_comecar_antes_de
    if ('duracao_dias' in corpo) anterior.duracao_dias = a.duracao_dias
    return executar(() => plano.reprogramar(a.atividade_id, corpo), {
      recalcular: false,
      desfazer: () => ({ rotulo: 'reprogramar', ops: [{ op: 'reprogramar', id: a.atividade_id, corpo: anterior }] }),
    })
  }

  async function inserir(opcoes: {
    pai: Atividade | null; depoisDe?: Atividade | null; nome?: string
    duracao?: number; marco?: boolean
  }): Promise<Atividade | undefined> {
    if (cronogramaId == null) return undefined
    const { pai, depoisDe = null, marco = false } = opcoes
    let etapaCriada: number | null = null
    return executar(async () => {
      let nome = opcoes.nome ?? (marco ? 'Novo marco' : pai ? 'Nova atividade' : 'Nova etapa')
      if (!pai && !marco) {
        // A etapa do plano nasce ligada à etapa da obra, criada junto.
        const existentes = await etapasDaObra.listar(obraId)
        nome = nomeLivre(nome, existentes.map((e) => e.nome_etapa))
        const ordem = existentes.reduce((m, e) => Math.max(m, e.ordem), 0) + 1
        etapaCriada = (await etapasDaObra.criar(obraId, nome, ordem)).etapa_id
      }
      return plano.inserir(cronogramaId, {
        pai: pai?.atividade_id ?? null,
        depois_de: depoisDe?.atividade_id ?? null,
        nome, eh_marco: marco, duracao_dias: marco ? null : (opcoes.duracao ?? 1), etapa: etapaCriada,
      })
    }, {
      desfazer: (nova) => ({
        rotulo: 'criar',
        ops: [
          { op: 'remover', id: nova.atividade_id },
          ...(etapaCriada != null ? [{ op: 'removerEtapa' as const, etapa: etapaCriada }] : []),
        ],
      }),
    })
  }

  /** Exclui (com o que está dentro) e guarda o retrato para o Ctrl+Z. */
  function excluirVarias(lista: Atividade[]) {
    const alvos = ordemNaTela(soAsDeCima(lista))
    const retratos = alvos.map(retratar)
    const sumir = new Set(alvos.flatMap((a) => [a, ...descendentes(a)]).map((a) => a.atividade_id))
    tirarDaTela(sumir)
    mudar({ marcadas: estado.marcadas.filter((id) => !sumir.has(id)) })
    return executar(async () => {
      for (const a of alvos) await api.atividades.remover(a.atividade_id)
    }, {
      desfazer: () => ({
        rotulo: alvos.length > 1 ? `excluir ${alvos.length} linhas` : 'excluir',
        // Volta na ordem em que estavam: cada uma reencontra a sua posição.
        ops: retratos.map((retrato) => ({ op: 'restaurar' as const, retrato })),
      }),
    })
  }

  function excluir(a: Atividade) {
    return excluirVarias([a])
  }

  function moverVarios(
    movimentos: { a: Atividade; pai: number | null; posicao: number | null }[], rotulo: string,
  ) {
    const voltas: Op[] = movimentos.map(({ a }) => ({
      op: 'mover', id: a.atividade_id, pai: a.pai ?? null, posicao: posicaoDe(a),
    }))
    return executar(async () => {
      for (const m of movimentos) await plano.mover(m.a.atividade_id, m.pai, m.posicao)
    }, { desfazer: () => ({ rotulo, ops: voltas }) })
  }

  function mover(a: Atividade, pai: number | null, posicao: number | null, rotulo = 'mover') {
    return moverVarios([{ a, pai, posicao }], rotulo)
  }

  /** Tab: as linhas entram na irmã de cima da primeira, no fim, em ordem. */
  function recuarVarias(lista: Atividade[]) {
    const alvos = ordemNaTela(soAsDeCima(lista))
    if (!alvos.length) return
    const marcadas = new Set(alvos.map((a) => a.atividade_id))
    const movimentos: { a: Atividade; pai: number | null; posicao: number | null }[] = []
    for (const a of alvos) {
      const lista2 = irmas(a.pai ?? null)
      const i = lista2.findIndex((x) => x.atividade_id === a.atividade_id)
      const acima = lista2.slice(0, i).reverse().find((x) => !marcadas.has(x.atividade_id))
      if (!acima) { mudar({ erro: `Não há linha acima de ${a.codigo}, no mesmo nível, para entrar.` }); return }
      if (acima.eh_marco) { mudar({ erro: 'Um marco é um instante e não agrupa atividades.' }); return }
      movimentos.push({ a, pai: acima.atividade_id, posicao: null })
    }
    return moverVarios(movimentos, alvos.length > 1 ? `recuar ${alvos.length} linhas` : 'recuar')
  }

  /** Shift+Tab: as linhas saem do grupo e ficam logo abaixo dele, em ordem. */
  function avancarVarias(lista: Atividade[]) {
    const alvos = ordemNaTela(soAsDeCima(lista)).filter((a) => a.pai != null)
    if (!alvos.length) return
    const contagem = new Map<number, number>()
    const movimentos = alvos.map((a) => {
      const pai = porId.get(a.pai as number)!
      const k = contagem.get(pai.atividade_id) ?? 0
      contagem.set(pai.atividade_id, k + 1)
      return { a, pai: pai.pai ?? null, posicao: posicaoDe(pai) + 1 + k }
    })
    return moverVarios(movimentos, alvos.length > 1 ? `avançar ${alvos.length} linhas` : 'avançar')
  }

  const recuar = (a: Atividade) => recuarVarias([a])
  const avancar = (a: Atividade) => avancarVarias([a])

  function deslocar(a: Atividade, delta: -1 | 1) {
    const lista = irmas(a.pai ?? null)
    const i = lista.findIndex((x) => x.atividade_id === a.atividade_id)
    const j = i + delta
    if (j < 0 || j >= lista.length) return
    return mover(a, a.pai ?? null, j, delta < 0 ? 'subir' : 'descer')
  }

  /** O gesto de arrastar: antes, depois ou dentro do alvo — uma linha ou as marcadas. */
  function soltar(arrastadas: Atividade[], alvo: Atividade, onde: 'antes' | 'depois' | 'dentro') {
    const lista = ordemNaTela(soAsDeCima(arrastadas)).filter((a) => a.atividade_id !== alvo.atividade_id)
    if (!lista.length) return
    for (const a of lista) {
      if ([a, ...descendentes(a)].some((x) => x.atividade_id === alvo.atividade_id)) {
        mudar({ erro: 'Uma linha não pode ir para dentro dela mesma.' })
        return
      }
    }
    if (onde === 'dentro') {
      if (alvo.eh_marco) { mudar({ erro: 'Um marco é um instante e não agrupa atividades.' }); return }
      return moverVarios(lista.map((a) => ({ a, pai: alvo.atividade_id, posicao: null })), 'mover')
    }
    const sem = new Set(lista.map((a) => a.atividade_id))
    const irmasDoAlvo = irmas(alvo.pai ?? null).filter((x) => !sem.has(x.atividade_id))
    const base = irmasDoAlvo.findIndex((x) => x.atividade_id === alvo.atividade_id) + (onde === 'antes' ? 0 : 1)
    return moverVarios(lista.map((a, k) => ({ a, pai: alvo.pai ?? null, posicao: base + k })), 'mover')
  }

  function ligar(origem: number, destino: number, tipo: TipoPrecedencia = 'FS', atraso = 0) {
    return executar(() => precedencias.criar({ origem, destino, tipo, atraso_dias: atraso }), {
      desfazer: () => ({ rotulo: 'ligar', ops: [{ op: 'desligarPar', origem, destino }] }),
    })
  }

  function desligar(p: Precedencia) {
    return executar(() => precedencias.remover(p.precedencia_id), {
      desfazer: () => ({
        rotulo: 'desligar',
        ops: [{ op: 'ligar', origem: p.origem, destino: p.destino, tipo: p.tipo, atraso: p.atraso_dias }],
      }),
    })
  }

  function alterarLigacao(p: Precedencia, corpo: { tipo?: TipoPrecedencia; atraso_dias?: number }) {
    return executar(() => precedencias.atualizar(p.precedencia_id, corpo), {
      desfazer: () => ({
        rotulo: 'alterar ligação',
        ops: [{ op: 'alterarPar', origem: p.origem, destino: p.destino, tipo: p.tipo, atraso: p.atraso_dias }],
      }),
    })
  }

  /** O texto da coluna Predecessoras de uma atividade, na grafia da grade. */
  function textoDasPredecessoras(a: Atividade): string {
    return rede
      .filter((p) => p.destino === a.atividade_id)
      .map((p) => rotuloDaLigacao(porId.get(p.origem)?.codigo ?? '?', p.tipo, p.atraso_dias))
      .join('; ')
  }

  /** Reescreve as predecessoras pelo texto digitado. */
  async function definirPredecessoras(a: Atividade, texto: string) {
    const lido = lerPredecessoras(texto)
    if (typeof lido === 'string') { mudar({ erro: lido }); return }
    const porCodigo = new Map(atividades.map((x) => [x.codigo, x]))
    for (const l of lido) {
      if (!porCodigo.has(l.ref)) { mudar({ erro: `A atividade ${l.ref} não existe neste plano.` }); return }
    }
    const novas = lido.map((l) => ({
      origem: porCodigo.get(l.ref)!.atividade_id, tipo: l.tipo as TipoPrecedencia, atraso: l.atraso,
    }))
    const antigas = rede.filter((p) => p.destino === a.atividade_id)
      .map((p) => ({ origem: p.origem, tipo: p.tipo, atraso: p.atraso_dias }))
    return executar(() => aplicarPredecessoras(a.atividade_id, novas), {
      desfazer: () => ({
        rotulo: 'predecessoras',
        ops: [{ op: 'predecessoras', destino: a.atividade_id, itens: antigas }],
      }),
    })
  }

  /** Encadeia em sequência (FS) as linhas dadas, na ordem da tela. */
  function encadear(lista: Atividade[], rotulo = 'encadear') {
    const ordenadas = ordemNaTela(lista)
    const criadas: Op[] = []
    return executar(async () => {
      for (let i = 1; i < ordenadas.length; i++) {
        const origem = ordenadas[i - 1].atividade_id
        const destino = ordenadas[i].atividade_id
        if (!rede.some((p) => p.origem === origem && p.destino === destino)) {
          await precedencias.criar({ origem, destino, tipo: 'FS', atraso_dias: 0 })
          criadas.push({ op: 'desligarPar', origem, destino })
        }
      }
    }, { desfazer: () => ({ rotulo, ops: criadas }) })
  }

  /** Tira as ligações entre as linhas dadas (as que vão de uma a outra delas). */
  function desligarEntre(lista: Atividade[]) {
    const ids = new Set(lista.map((a) => a.atividade_id))
    const alvo = rede.filter((p) => ids.has(p.origem) && ids.has(p.destino))
    return executar(async () => {
      for (const p of alvo) await precedencias.remover(p.precedencia_id)
    }, {
      desfazer: () => ({
        rotulo: 'desligar',
        ops: alvo.map((p) => ({ op: 'ligar' as const, origem: p.origem, destino: p.destino, tipo: p.tipo, atraso: p.atraso_dias })),
      }),
    })
  }

  /* -- seleção de várias linhas ------------------------------------------ */

  const marcadas = snap.marcadas.map((id) => porId.get(id)).filter((a): a is Atividade => !!a)

  return {
    ...snap,
    ocupado: snap.ocupado > 0,
    podeDesfazer: snap.pilha.length > 0,
    proximoDesfazer: snap.pilha[snap.pilha.length - 1]?.rotulo ?? null,
    limparErro: () => mudar({ erro: null }),
    /** O erro **agora**, e não o do último render — quem acabou de chamar
     *  `executar` num diálogo lê por aqui. */
    ultimoErro: () => estado.erro,
    avisar: (erro: string) => mudar({ erro }),
    zerarPilha: () => mudar({ pilha: [] }),
    linhasMarcadas: marcadas,
    marcar: (ids: number[]) => mudar({ marcadas: [...new Set(ids)] }),
    limparMarcas: () => { if (estado.marcadas.length) mudar({ marcadas: [] }) },
    executar, desfazer, recalcular, invalidar,
    salvar, salvarVarias, reprogramar, inserir, excluir, excluirVarias, mover,
    recuar, avancar, recuarVarias, avancarVarias, deslocar, soltar,
    ligar, desligar, alterarLigacao, textoDasPredecessoras, definirPredecessoras, encadear, desligarEntre,
    descendentes,
  }
}

export type Montagem = ReturnType<typeof useMontagem>
