import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft, GitBranch, Hash, Library, LineChart, ListTree, Play, Redo2, Search, TrendingUp,
  Undo2, Upload,
} from 'lucide-react'
import { Btn, Card, Loading, Modal, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { dateFromBR, dateToBR } from '@/utils/dates'
import {
  useCalcularCpm, useAtualizarPrecedencia, useExcluirAtividade, useExcluirPrecedencia,
  useEscritaEmLote, useGantt, usePublicar, useReplanejar, useReprogramar, useSalvarAtividade,
  useRenumerarEap, useSalvarPrecedencia, useStatusModulo,
} from '../hooks'
import { useHistorico } from '../historico'
import {
  diferencaDePredecessoras, interpretarPredecessoras, primeiraMensagem, proximoCodigo,
  textoDePredecessoras,
} from '../lib'
import { ROTULOS_DE_FILTRO } from '../types'
import type {
  Atividade, CampoEditavel, EdicaoCelula, Filtro, PayloadGantt, Precedencia, TipoPrecedencia,
} from '../types'
import GanttCronograma, { type AcaoEmBloco } from '../components/GanttCronograma'
import InspetorAtividade from '../components/InspetorAtividade'
import PainelLinhaDeBase from '../components/PainelLinhaDeBase'
import PainelCurvaS from '../components/PainelCurvaS'
import PainelAvanco from '../components/PainelAvanco'
import { ModalSalvarComoModelo } from '../components/PlanoModelo'
import type { GestoDeEstrutura } from '../components/GradeWbs'

type Lente = 'gantt' | 'avanco' | 'base' | 'plano'

/** As quatro lentes do plano, na ordem do ciclo: montar → executar → conferir.
 *  **Avanço** entra entre o Gantt e a linha de base porque é o que acontece
 *  entre planejar e comparar — e é a lente que o engenheiro de obra abre todo
 *  dia, enquanto as outras três são de quem planeja e de quem confere. */
const LENTES: { chave: Lente; rotulo: string; icone: React.ReactNode }[] = [
  { chave: 'gantt', rotulo: 'Cronograma', icone: <ListTree size={14} /> },
  { chave: 'avanco', rotulo: 'Avanço', icone: <TrendingUp size={14} /> },
  { chave: 'base', rotulo: 'Linha de base', icone: <GitBranch size={14} /> },
  { chave: 'plano', rotulo: 'Curva S e rede', icone: <LineChart size={14} /> },
]

export default function CronogramaPage() {
  const { cronogramaId } = useParams()
  const id = Number(cronogramaId)
  const navegar = useNavigate()
  const [busca, setBusca] = useSearchParams()
  const { hasPermission, hasModule } = useAuth()

  const podeEditar = hasPermission('pdca.cronograma.edit')
  const podePublicar = hasPermission('pdca.cronograma.publicar')
  const podeReplanejar = hasPermission('pdca.cronograma.replanejar')
  const podeVerOrcamento = hasModule('orcamento')
  //: Ler o avanço e apontá-lo são permissões diferentes (planta §8), e a tela
  //: respeita as duas: sem a de leitura a lente nem aparece; sem a de apontar
  //: ela abre, mostra e não deixa digitar — que é a informação certa para quem
  //: confere sem poder lançar.
  const podeVerAvanco = hasPermission('pdca.avanco.view')
  const podeApontar = hasPermission('pdca.avanco.apontar')

  const gantt = useGantt(id)
  const status = useStatusModulo()
  const dados = gantt.data

  const [lente, setLente] = useState<Lente>('gantt')
  const [filtro, setFiltro] = useState('')
  const [filtros, setFiltros] = useState<ReadonlySet<Filtro>>(new Set())
  const [selecionadas, setSelecionadas] = useState<ReadonlySet<number>>(new Set())
  const [inspecionando, setInspecionando] = useState<number | null>(null)
  const [menu, setMenu] = useState<{ atividade: Atividade; x: number; y: number } | null>(null)
  const [replanejando, setReplanejando] = useState(false)
  const [salvandoModelo, setSalvandoModelo] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [aviso, setAviso] = useState('')
  const [erro, setErro] = useState('')
  const [trabalhando, setTrabalhando] = useState('')

  const historico = useHistorico()

  //: O payload mais recente, lido de dentro de comandos assíncronos. Sem ele,
  //: desfazer um gesto usaria a foto do plano de quando o gesto foi criado.
  const atual = useRef<PayloadGantt | undefined>(undefined)
  atual.current = dados

  const salvar = useSalvarAtividade(id)
  const excluir = useExcluirAtividade(id)
  const reprogramar = useReprogramar(id)
  const criarPrec = useSalvarPrecedencia(id)
  const atualizarPrec = useAtualizarPrecedencia(id)
  const excluirPrec = useExcluirPrecedencia(id)
  const lote = useEscritaEmLote(id)
  const renumerarEap = useRenumerarEap(id)
  //: O teto por chamada é do dono e mora no `payment/planos.py`; a tela o lê do
  //: `status/` do módulo. Sem o status carregado ainda, um bloco conservador —
  //: melhor mandar duas requisições a mais que colher um 400 no fim da espera.
  const tetoDoLote = status.data?.tetos?.linhas_por_lote ?? 100
  const calcular = useCalcularCpm(id)
  const publicar = usePublicar(id)
  const replanejar = useReplanejar(id)

  const editavel = !!dados?.cronograma.editavel && podeEditar

  // -------------------------------------------------------------------------
  // Um passo do plano = uma escrita e a sua inversa
  // -------------------------------------------------------------------------

  /** Uma escrita de atividade. Recebe `Record` e não `Partial<Atividade>` porque
   *  metade dos passos monta a carga com **chave computada** (`{ [campo]: valor }`),
   *  e o molde estreito ali obrigaria um `as` em cada ponto de chamada — que é
   *  exatamente onde um `as` deixa de proteger e passa a esconder. */
  const patch = useCallback(
    (idAtividade: number, payload: Record<string, unknown>) =>
      salvar.mutateAsync({ id: idAtividade, payload: payload as Partial<Atividade> }).then(() => undefined),
    [salvar],
  )

  /** Editar um campo é o passo mais comum, e o mais simples de inverter: o
   *  mesmo PATCH com o valor de antes. */
  const editarCampo = useCallback(
    (a: Atividade, campo: keyof Atividade, novo: unknown, anterior: unknown, rotulo: string) =>
      historico.executar({
        rotulo,
        fazer: () => patch(a.atividade_id, { [campo]: novo }),
        desfazer: () => patch(a.atividade_id, { [campo]: anterior }),
      }),
    [historico, patch],
  )

  /**
   * Aplicar um texto de predecessoras. É idempotente de propósito: ele lê a rede
   * como ela está **agora** e faz só a diferença até o texto pedido. É o que
   * permite que desfazer seja "aplicar o texto anterior" — sem guardar id de
   * precedência, que muda a cada recriação.
   */
  const aplicarPredecessoras = useCallback(async (idAtividade: number, texto: string) => {
    const payload = atual.current
    if (!payload) return
    const alvo = payload.atividades.find(a => a.atividade_id === idAtividade)
    if (!alvo) return
    const porCodigo = new Map(payload.atividades.map(a => [a.codigo, a]))
    const lido = interpretarPredecessoras(texto, porCodigo, alvo)
    if (!lido.ok) throw new Error(lido.erro)

    const atuais = payload.precedencias.filter(p => p.destino === idAtividade)
    const { criar, atualizar, excluir: remover } = diferencaDePredecessoras(atuais, lido.itens)
    for (const p of remover) await excluirPrec.mutateAsync(p)
    for (const p of atualizar) await atualizarPrec.mutateAsync(p)
    for (const p of criar) {
      await criarPrec.mutateAsync({
        origem: p.origem, destino: idAtividade, tipo: p.tipo, atraso_dias: p.atraso_dias,
      })
    }
  }, [criarPrec, atualizarPrec, excluirPrec])

  /** O que a grade manda quando alguém confirma uma célula. Converter aqui, e
   *  não no componente, mantém a grade sem opinião sobre o domínio: ela sabe
   *  desenhar e navegar, não o que é um peso ou uma data. */
  const editarCelula = useCallback((a: Atividade, campo: CampoEditavel, valor: string) => {
    setErro('')
    if (campo === 'predecessoras') {
      const antes = textoDePredecessoras(a, atual.current?.precedencias ?? [], new Map(
        (atual.current?.atividades ?? []).map(x => [x.atividade_id, x]),
      ))
      historico.executar({
        rotulo: 'rede de ' + a.codigo,
        fazer: () => aplicarPredecessoras(a.atividade_id, valor),
        desfazer: () => aplicarPredecessoras(a.atividade_id, antes),
      })
      return
    }
    if (campo === 'duracao_dias') {
      const novo = valor === '' ? null : Number(valor.replace(/\D/g, ''))
      if (novo != null && (!Number.isFinite(novo) || novo < 1)) {
        setErro('A duração é em dias úteis e precisa ser de ao menos 1.')
        return
      }
      editarCampo(a, 'duracao_dias', novo, a.duracao_dias, 'duração de ' + a.codigo)
      return
    }
    if (campo === 'nao_comecar_antes_de') {
      const iso = valor ? dateFromBR(valor) : ''
      if (valor && !iso) { setErro('Data inválida — use DD/MM/AAAA.'); return }
      editarCampo(a, 'nao_comecar_antes_de', iso || null, a.nao_comecar_antes_de, 'restrição de ' + a.codigo)
      return
    }
    if (campo === 'peso_informado') {
      const limpo = valor.replace(/\./g, '').replace(',', '.')
      const novo = limpo === '' ? null : limpo
      if (novo != null && !Number.isFinite(Number(novo))) { setErro('O peso precisa ser um número.'); return }
      editarCampo(a, 'peso_informado', novo, a.peso_informado, 'peso de ' + a.codigo)
      return
    }
    editarCampo(a, campo, valor, a[campo], campo + ' de ' + a.codigo)
  }, [aplicarPredecessoras, editarCampo, historico])

  /** Colar da planilha. Vai em **blocos** para o endpoint de lote, que aplica
   *  cada bloco dentro de uma transação: sem isso, metade de um bloco colado
   *  ficaria visível para quem estivesse olhando a mesma obra. O passo é um só
   *  no desfazer — quem colou 200 linhas quer voltar 200 de uma vez. */
  const colar = useCallback((edicoes: EdicaoCelula[]) => {
    const anteriores = edicoes.map(e => ({
      id: e.atividade.atividade_id,
      campo: e.campo,
      valor: e.campo === 'predecessoras'
        ? textoDePredecessoras(e.atividade, atual.current?.precedencias ?? [], new Map(
          (atual.current?.atividades ?? []).map(x => [x.atividade_id, x]),
        ))
        : e.atividade[e.campo as keyof Atividade],
    }))

    const aplicar = async (lista: { id: number; campo: string; valor: unknown }[]) => {
      // As predecessoras saem do lote de propósito: elas não são um campo da
      // atividade, são um diff da rede — cada uma vira até três escritas em
      // tabelas diferentes, e espremê-las no `lote/` obrigaria o endpoint a
      // conhecer o grafo. São poucas num bloco colado; vão pelo caminho normal.
      const rede = lista.filter(i => i.campo === 'predecessoras')
      const celulas = lista.filter(i => i.campo !== 'predecessoras')
      setTrabalhando('Aplicando ' + lista.length + ' células…')
      try {
        for (const bloco of fatiar(celulas, tetoDoLote)) {
          await lote.mutateAsync(bloco.map(i => ({
            atividade: i.id,
            campos: { [i.campo]: i.valor },
          })))
        }
        for (const item of rede) {
          await aplicarPredecessoras(item.id, String(item.valor ?? ''))
        }
      } finally {
        setTrabalhando('')
      }
    }

    historico.executar({
      rotulo: 'colar ' + edicoes.length + ' células',
      fazer: () => aplicar(edicoes.map(e => ({
        id: e.atividade.atividade_id,
        campo: e.campo,
        valor: converter(e.campo, e.valor),
      }))),
      desfazer: () => aplicar(anteriores),
    })
  }, [aplicarPredecessoras, historico, lote, tetoDoLote])

  // -------------------------------------------------------------------------
  // Gestos de estrutura
  // -------------------------------------------------------------------------

  const irmaosDe = useCallback((pai: number | null) =>
    (dados?.atividades ?? []).filter(a => (a.pai ?? null) === pai).sort((x, y) => x.ordem - y.ordem),
  [dados])

  /** Indentar, promover e reordenar. Inserir e excluir moram logo abaixo: eles
   *  criam e destroem linha, e a inversa deles não é um PATCH. */
  const mover = useCallback(async (qual: GestoDeEstrutura, a: Atividade) => {
    setErro('')
    const irmaos = irmaosDe(a.pai ?? null)
    const entre = irmaos.findIndex(x => x.atividade_id === a.atividade_id)

    if (qual === 'indentar') {
      // Indentar é virar filha do irmão de cima. É a definição do MS Project, e
      // a única que não exige escolher um pai numa lista de 500 atividades.
      const novoPai = irmaos[entre - 1]
      if (!novoPai) { setErro('Não há irmã acima para receber esta atividade.'); return }
      const ordem = irmaosDe(novoPai.atividade_id).length
      await historico.executar({
        rotulo: 'indentar ' + a.codigo,
        fazer: () => patch(a.atividade_id, { pai: novoPai.atividade_id, ordem }),
        desfazer: () => patch(a.atividade_id, { pai: a.pai, ordem: a.ordem }),
      })
      return
    }

    if (qual === 'outdentar') {
      const pai = a.pai ? (dados?.atividades ?? []).find(x => x.atividade_id === a.pai) : null
      if (!pai) { setErro('Esta atividade já está na raiz.'); return }
      const ordem = (pai.ordem ?? 0) + 1
      await historico.executar({
        rotulo: 'promover ' + a.codigo,
        fazer: () => patch(a.atividade_id, { pai: pai.pai ?? null, ordem }),
        desfazer: () => patch(a.atividade_id, { pai: a.pai, ordem: a.ordem }),
      })
      return
    }

    if (qual === 'subir' || qual === 'descer') {
      const destino = entre + (qual === 'subir' ? -1 : 1)
      if (destino < 0 || destino >= irmaos.length) {
        setErro('A atividade já é a ' + (qual === 'subir' ? 'primeira' : 'última') + ' entre as irmãs.')
        return
      }
      // Reescreve a ordem das irmãs inteiras, e não só a troca do par. O campo
      // `ordem` nasce 0 para todo mundo (é o default do modelo), e trocar dois
      // zeros não move nada na tela: a árvore desempata por código e a linha
      // volta para onde estava. Renumerar a fileira é o único gesto que sempre
      // resulta no que o usuário viu acontecer.
      const nova = [...irmaos]
      nova.splice(destino, 0, ...nova.splice(entre, 1))
      // Escreve **todas** as irmãs, sem comparar com a ordem que a lista traz:
      // depois do primeiro passo esse número é a foto de antes, e pular a linha
      // que "já estaria certa" segundo a foto é justamente o que faria o
      // desfazer deixar uma delas no lugar errado.
      const aplicar = (lista: Atividade[]) => async () => {
        for (let i = 0; i < lista.length; i++) await patch(lista[i].atividade_id, { ordem: i })
      }
      await historico.executar({
        rotulo: (qual === 'subir' ? 'subir ' : 'descer ') + a.codigo,
        fazer: aplicar(nova),
        desfazer: aplicar(irmaos),
      })
      return
    }
  }, [dados, historico, irmaosDe, patch])

  /** Inserir uma irmã logo abaixo. O código vem sugerido do pai, e a ordem é a
   *  da linha de baixo — quem monta EAP digita de cima para baixo. */
  const inserir = useCallback(async (referencia: Atividade) => {
    const irmaos = irmaosDe(referencia.pai ?? null)
    const criada = { id: 0 }
    const payload: Partial<Atividade> = {
      cronograma: id,
      pai: referencia.pai,
      codigo: proximoCodigo(
        referencia.pai ? (dados?.atividades ?? []).find(a => a.atividade_id === referencia.pai) ?? null : null,
        irmaos,
      ),
      nome: 'Nova atividade',
      duracao_dias: 1,
      ordem: referencia.ordem + 1,
    }
    await historico.executar({
      rotulo: 'inserir atividade',
      fazer: async () => {
        const nova = await salvar.mutateAsync({ payload })
        criada.id = nova.atividade_id
      },
      desfazer: async () => {
        if (criada.id) await excluir.mutateAsync(criada.id)
      },
    })
  }, [dados, excluir, historico, id, irmaosDe, salvar])

  /**
   * Excluir. A folha volta inteira — a atividade e as setas que chegavam nela,
   * recriadas pelo código, que é estável. **A sintética não volta**: apagar um
   * galho leva as filhas junto (cascata no banco), e prometer desfazer isso
   * seria prometer recompor uma subárvore que a tela não guardou. Em vez de
   * mentir, o passo avisa e não entra na pilha.
   */
  const remover = useCallback(async (a: Atividade) => {
    const payload = atual.current
    if (!payload) return
    const filhas = payload.atividades.filter(x => x.pai === a.atividade_id)

    if (filhas.length) {
      const quantas = filhas.length
      const confirma = window.confirm(
        'Excluir "' + a.codigo + ' ' + a.nome + '" apaga também ' + quantas +
        (quantas === 1 ? ' atividade abaixo dela' : ' atividades abaixo dela') +
        ' e as ligações delas. Este passo NÃO pode ser desfeito. Continuar?',
      )
      if (!confirma) return
      try {
        await excluir.mutateAsync(a.atividade_id)
        historico.limpar()
        setAviso('Galho excluído. O histórico de desfazer foi zerado — ele não recompõe subárvore.')
      } catch (e) {
        setErro(primeiraMensagem(e))
      }
      return
    }

    const ligacoes = payload.precedencias.filter(
      p => p.origem === a.atividade_id || p.destino === a.atividade_id,
    )
    const codigosDe = new Map(payload.atividades.map(x => [x.atividade_id, x.codigo]))
    const salvas = ligacoes.map(p => ({
      origemCodigo: codigosDe.get(p.origem) ?? '',
      destinoCodigo: codigosDe.get(p.destino) ?? '',
      tipo: p.tipo,
      atraso_dias: p.atraso_dias,
    }))
    const recriada = { id: 0 }

    await historico.executar({
      rotulo: 'excluir ' + a.codigo,
      fazer: () => excluir.mutateAsync(a.atividade_id).then(() => undefined),
      desfazer: async () => {
        const nova = await salvar.mutateAsync({
          payload: {
            cronograma: id, pai: a.pai, codigo: a.codigo, nome: a.nome, ordem: a.ordem,
            duracao_dias: a.duracao_dias, eh_marco: a.eh_marco,
            nao_comecar_antes_de: a.nao_comecar_antes_de, calendario: a.calendario,
            local: a.local, etapa: a.etapa, item_orcado: a.item_orcado,
            responsavel: a.responsavel, peso_informado: a.peso_informado,
            observacao: a.observacao,
          },
        })
        recriada.id = nova.atividade_id
        const porCodigo = new Map((atual.current?.atividades ?? []).map(x => [x.codigo, x.atividade_id]))
        porCodigo.set(a.codigo, nova.atividade_id)
        for (const p of salvas) {
          const origem = porCodigo.get(p.origemCodigo)
          const destino = porCodigo.get(p.destinoCodigo)
          if (origem && destino) {
            await criarPrec.mutateAsync({ origem, destino, tipo: p.tipo, atraso_dias: p.atraso_dias })
          }
        }
      },
    })
  }, [criarPrec, excluir, historico, id, salvar])

  /**
   * As ações sobre o conjunto selecionado.
   *
   * Tudo aqui é **um** passo no desfazer: quem indentou doze linhas quer voltar
   * doze, não clicar doze vezes. E a ordem importa em duas delas — indentar de
   * cima para baixo, porque cada uma vira filha da irmã acima, e excluir de
   * baixo para cima, para não remover o pai antes das filhas.
   */
  const emBloco = useCallback(async (acao: AcaoEmBloco, valor?: number) => {
    setErro('')
    const payload = atual.current
    if (!payload) return
    const escolhidas = payload.atividades
      .filter(a => selecionadas.has(a.atividade_id))
      .sort((x, y) => x.codigo.localeCompare(y.codigo, 'pt-BR', { numeric: true }))
    if (escolhidas.length < 2) return

    if (acao === 'duracao') {
      const folhas = escolhidas.filter(a => !a.tem_filhos && !a.eh_marco)
      if (!folhas.length || !valor) return
      const antes = folhas.map(a => ({ atividade: a.atividade_id, campos: { duracao_dias: a.duracao_dias } }))
      await historico.executar({
        rotulo: 'duração de ' + folhas.length + ' atividades',
        fazer: () => lote.mutateAsync(
          folhas.map(a => ({ atividade: a.atividade_id, campos: { duracao_dias: valor } })),
        ).then(() => undefined),
        desfazer: () => lote.mutateAsync(antes).then(() => undefined),
      })
      return
    }

    if (acao === 'cadeia') {
      // Cada folha termina, a seguinte começa. É a sequência que o planejador
      // desenha com doze cliques no Gantt — e a ordem é a da EAP, que é como
      // ele leu a lista antes de selecionar.
      const folhas = escolhidas.filter(a => !a.tem_filhos && !a.eh_marco)
      if (folhas.length < 2) { setErro('A cadeia liga folhas: sintéticas e marcos ficam de fora.'); return }
      const criadas: number[] = []
      await historico.executar({
        rotulo: 'ligar ' + folhas.length + ' em cadeia',
        fazer: async () => {
          criadas.length = 0
          for (let i = 0; i < folhas.length - 1; i++) {
            const nova = await criarPrec.mutateAsync({
              origem: folhas[i].atividade_id,
              destino: folhas[i + 1].atividade_id,
              tipo: 'FS', atraso_dias: 0,
            })
            criadas.push(nova.precedencia_id)
          }
        },
        desfazer: async () => {
          for (const id of [...criadas].reverse()) await excluirPrec.mutateAsync(id)
          criadas.length = 0
        },
      })
      return
    }

    if (acao === 'excluir') {
      const comFilhas = escolhidas.filter(a => a.tem_filhos)
      if (comFilhas.length) {
        setErro(
          'A seleção tem ' + comFilhas.length + ' sintética(s). Excluir um galho leva as filhas '
          + 'junto e não é desfeito — faça uma de cada vez, pelo menu da linha.',
        )
        return
      }
      if (!window.confirm('Excluir ' + escolhidas.length + ' atividades e as ligações delas?')) return
      setTrabalhando('Excluindo ' + escolhidas.length + ' atividades…')
      try {
        for (const a of [...escolhidas].reverse()) await excluir.mutateAsync(a.atividade_id)
        historico.limpar()
        setSelecionadas(new Set())
        setAviso(escolhidas.length + ' atividades excluídas. O histórico foi zerado — exclusão não volta.')
      } catch (e) {
        setErro(primeiraMensagem(e))
      } finally {
        setTrabalhando('')
      }
      return
    }

    // Indentar e promover: de cima para baixo, uma a uma, pelo caminho normal —
    // cada uma depende do estado que a anterior deixou.
    const ordenadas = acao === 'indentar' ? escolhidas : [...escolhidas].reverse()
    setTrabalhando((acao === 'indentar' ? 'Indentando ' : 'Promovendo ') + ordenadas.length + ' linhas…')
    try {
      for (const a of ordenadas) await mover(acao, a)
    } finally {
      setTrabalhando('')
    }
  }, [criarPrec, excluir, excluirPrec, historico, lote, mover, selecionadas])

  const aoGesto = useCallback((qual: GestoDeEstrutura, a: Atividade) => {
    if (qual === 'inserir') { void inserir(a); return }
    if (qual === 'excluir') { void remover(a); return }
    void mover(qual, a)
  }, [inserir, mover, remover])

  // -------------------------------------------------------------------------
  // Gestos do Gantt e verbos do plano
  // -------------------------------------------------------------------------

  const aoReprogramar = useCallback((idAtividade: number, payload: { nao_comecar_antes_de?: string | null; duracao_dias?: number }) => {
    const a = atual.current?.atividades.find(x => x.atividade_id === idAtividade)
    if (!a) return
    const antes = 'duracao_dias' in payload
      ? { duracao_dias: a.duracao_dias ?? 1 }
      : { nao_comecar_antes_de: a.nao_comecar_antes_de }
    historico.executar({
      rotulo: ('duracao_dias' in payload ? 'esticar ' : 'arrastar ') + a.codigo,
      fazer: () => reprogramar.mutateAsync({ id: idAtividade, ...payload }).then(() => undefined),
      desfazer: () => reprogramar.mutateAsync({ id: idAtividade, ...antes }).then(() => undefined),
    })
  }, [historico, reprogramar])

  const aoLigar = useCallback((origem: number, destino: number, tipo: TipoPrecedencia) => {
    const codigo = atual.current?.atividades.find(a => a.atividade_id === destino)?.codigo ?? ''
    const criada = { id: 0 }
    historico.executar({
      rotulo: 'ligar ' + codigo,
      fazer: async () => {
        const nova = await criarPrec.mutateAsync({ origem, destino, tipo, atraso_dias: 0 })
        criada.id = nova.precedencia_id
      },
      desfazer: async () => { if (criada.id) await excluirPrec.mutateAsync(criada.id) },
    })
  }, [criarPrec, excluirPrec, historico])

  const aoExcluirPrecedencia = useCallback((idPrec: number) => {
    const p = atual.current?.precedencias.find(x => x.precedencia_id === idPrec)
    if (!p) return
    const recriada = { id: 0 }
    historico.executar({
      rotulo: 'remover ligação',
      fazer: () => excluirPrec.mutateAsync(idPrec).then(() => undefined),
      desfazer: async () => {
        const nova = await criarPrec.mutateAsync({
          origem: p.origem, destino: p.destino, tipo: p.tipo, atraso_dias: p.atraso_dias,
        })
        recriada.id = nova.precedencia_id
      },
    })
  }, [criarPrec, excluirPrec, historico])

  const aoAtualizarPrecedencia = useCallback((idPrec: number, payload: Partial<Precedencia>) => {
    const p = atual.current?.precedencias.find(x => x.precedencia_id === idPrec)
    if (!p) return
    const antes: Partial<Precedencia> = { tipo: p.tipo, atraso_dias: p.atraso_dias }
    historico.executar({
      rotulo: 'ajustar ligação',
      fazer: () => atualizarPrec.mutateAsync({ id: idPrec, payload }).then(() => undefined),
      desfazer: () => atualizarPrec.mutateAsync({ id: idPrec, payload: antes }).then(() => undefined),
    })
  }, [atualizarPrec, historico])

  /**
   * Renumerar a EAP inteira, na ordem da árvore.
   *
   * Quem calcula os códigos é o **servidor**, e quem os aplica também: o código
   * é único por cronograma, então a troca exige duas passadas (todos vão para um
   * nome temporário antes de qualquer definitivo) e as duas têm de caber na
   * mesma transação. Fatiar em blocos aqui — que é o que o cliente teria de
   * fazer para respeitar o teto por chamada — faria um código do segundo bloco
   * colidir com o primeiro.
   *
   * A tela pergunta antes porque mexer no código de dezenas de atividades de uma
   * vez é irreversível na prática: os códigos antigos não voltam.
   */
  const renumerar = useCallback(async () => {
    setErro(''); setAviso('')
    try {
      const previa = await renumerarEap.mutateAsync(true)
      if (!previa.mudancas) { setAviso('A numeração da EAP já está em ordem.'); return }
      if (!window.confirm(
        'Renumerar a EAP muda o código de ' + previa.mudancas + ' atividades. Continuar?',
      )) return

      setTrabalhando('Renumerando ' + previa.mudancas + ' códigos…')
      const feito = await renumerarEap.mutateAsync(false)
      historico.limpar()
      setAviso(feito.aplicadas + ' códigos renumerados. O histórico foi zerado — a renumeração não é um passo desfeito.')
    } catch (e) {
      setErro(primeiraMensagem(e))
    } finally {
      setTrabalhando('')
    }
  }, [historico, renumerarEap])

  const rodarCpm = async () => {
    setErro(''); setAviso('')
    try {
      const r = await calcular.mutateAsync()
      setAviso(
        'CPM rodado em ' + r.segundos.toFixed(2) + ' s · ' + r.criticas.length + ' atividades no caminho crítico · término em ' + dateToBR(r.termino)
        + (r.feriados_sincronizados ? '' : ' · atenção: a base de feriados está vazia, e os feriados não entraram na conta'),
      )
    } catch (e) { setErro(primeiraMensagem(e)) }
  }

  const publicarPlano = async () => {
    if (!window.confirm('Publicar torna este plano o vigente da obra e o congela. Para mudá-lo depois, será preciso replanejar. Continuar?')) return
    setErro(''); setAviso('')
    try {
      await publicar.mutateAsync()
      historico.limpar()
      setAviso('Plano publicado. Ele é agora o cronograma vigente da obra.')
    } catch (e) { setErro(primeiraMensagem(e)) }
  }

  const replanejarPlano = async () => {
    setErro('')
    try {
      const nova = await replanejar.mutateAsync(motivo)
      setReplanejando(false)
      setMotivo('')
      historico.limpar()
      navegar('/app/pdca/obra/' + nova.obra + '/cronograma/' + nova.cronograma_id)
    } catch (e) { setErro(primeiraMensagem(e)) }
  }

  /** Ctrl+Z e Ctrl+Y na janela, e não na grade: quem acabou de arrastar uma
   *  barra no Gantt tem o foco no SVG, e um desfazer que só funciona com o foco
   *  na planilha é um desfazer que não existe quando mais se precisa dele. */
  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return
      const alvo = e.target as HTMLElement | null
      if (alvo && (alvo.tagName === 'INPUT' || alvo.tagName === 'TEXTAREA')) return
      if (e.key === 'z' && !e.shiftKey) { e.preventDefault(); void historico.desfazer() }
      else if (e.key === 'y' || (e.key === 'z' && e.shiftKey)) { e.preventDefault(); void historico.refazer() }
    }
    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  }, [historico])

  useEffect(() => {
    const q = busca.get('atividade')
    if (q) setInspecionando(Number(q))
  }, [busca])

  const inspecionada = useMemo(
    () => dados?.atividades.find(a => a.atividade_id === inspecionando) ?? null,
    [dados, inspecionando],
  )

  if (gantt.isLoading) return <Loading o="o cronograma" />
  if (gantt.isError || !dados) {
    return (
      <div style={{ padding: 26 }}>
        <Card style={{ padding: 20 }}>
          <strong>Não foi possível abrir este cronograma.</strong>
          <p style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 6 }}>
            Ele pode ter sido substituído por um replanejamento, ou o seu acesso ao módulo mudou.
          </p>
          <Btn onClick={() => navegar('/app/pdca')} style={{ marginTop: 12 }}>
            <ArrowLeft size={14} /> Voltar às obras
          </Btn>
        </Card>
      </div>
    )
  }

  const c = dados.cronograma

  // O `main` do AppShell é um flex child com `overflow-y: auto` e altura definida
  // — daí `height: 100%` aqui. Um `calc(100vh - N)` chutaria a altura do topbar e
  // deixaria a linha do tempo com uma tira de vazio embaixo.
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <header style={{ padding: '16px 22px 0', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, flexWrap: 'wrap' }}>
          <button
            onClick={() => navegar('/app/pdca')}
            style={{ border: 'none', background: 'none', color: 'var(--ink-3)', cursor: 'pointer', display: 'flex', gap: 5, alignItems: 'center', fontSize: 12.5, padding: 0 }}
          ><ArrowLeft size={14} /> Obras</button>

          <div style={{ flex: 1, minWidth: 240 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap' }}>
              <h1 style={{ margin: 0, fontSize: 20 }}>{c.obra_nome}</h1>
              <Pill kind={c.status === 'vigente' ? 'good' : c.status === 'rascunho' ? 'accent' : 'slate'}>
                v{c.versao} · {c.status_rotulo}
              </Pill>
              {c.base_versao != null && <Pill kind="info">base v{c.base_versao}</Pill>}
              {c.eh_modelo && <Pill kind="net">modelo · {c.nome_modelo}</Pill>}
            </div>
            <p style={{ margin: '4px 0 0', fontSize: 12.5, color: 'var(--ink-3)' }}>
              {c.descricao} · início em {dateToBR(c.data_inicio)}
              {c.calendario_nome ? ' · calendário ' + c.calendario_nome : ' · sem calendário'}
              {c.termino_calculado ? ' · término em ' + dateToBR(c.termino_calculado) : ' · sem cálculo'}
              {' · '}{c.atividades_count} atividades
            </p>
          </div>

          <div style={{ display: 'flex', gap: 7, alignItems: 'center', flexWrap: 'wrap' }}>
            {editavel && (
              <>
                <Btn tam="sm" onClick={() => void historico.desfazer()} disabled={!historico.podeDesfazer || historico.ocupado}
                  title={historico.podeDesfazer ? 'Desfazer ' + historico.rotuloDesfazer + ' (Ctrl+Z)' : 'Nada a desfazer'}>
                  <Undo2 size={14} />
                </Btn>
                <Btn tam="sm" onClick={() => void historico.refazer()} disabled={!historico.podeRefazer || historico.ocupado}
                  title={historico.podeRefazer ? 'Refazer ' + historico.rotuloRefazer + ' (Ctrl+Y)' : 'Nada a refazer'}>
                  <Redo2 size={14} />
                </Btn>
                <Btn tam="sm" onClick={() => void renumerar()} title="Renumerar a EAP na ordem da árvore">
                  <Hash size={14} /> Renumerar
                </Btn>
              </>
            )}
            <Btn tam="sm" onClick={rodarCpm} disabled={!podeEditar || calcular.isPending}>
              <Play size={14} /> {calcular.isPending ? 'Calculando…' : 'Calcular CPM'}
            </Btn>
            {c.status === 'rascunho' && podePublicar && (
              <Btn tam="sm" variant="brand" onClick={publicarPlano} disabled={publicar.isPending}>
                <Upload size={14} /> Publicar
              </Btn>
            )}
            {podeEditar && (
              <Btn
                tam="sm"
                onClick={() => setSalvandoModelo(true)}
                title={c.eh_modelo
                  ? 'Este plano está na biblioteca como "' + c.nome_modelo + '"'
                  : 'Guardar este plano como padrão reaplicável em obra nova'}
              >
                <Library size={14} /> {c.eh_modelo ? 'Modelo' : 'Salvar como modelo'}
              </Btn>
            )}
            {c.status === 'vigente' && podeReplanejar && (
              <Btn tam="sm" variant="brand" onClick={() => setReplanejando(true)}>
                <GitBranch size={14} /> Replanejar
              </Btn>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 2, background: 'var(--inset)', padding: 3, borderRadius: 9 }}>
            {LENTES.filter(l => l.chave !== 'avanco' || podeVerAvanco).map(l => (
              <button
                key={l.chave} onClick={() => setLente(l.chave)}
                style={{
                  border: 'none', borderRadius: 6, padding: '5px 12px', fontSize: 12.5, cursor: 'pointer',
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  background: lente === l.chave ? 'var(--surface)' : 'transparent',
                  color: lente === l.chave ? 'var(--ink)' : 'var(--ink-3)',
                  fontWeight: lente === l.chave ? 600 : 400,
                }}
              >{l.icone} {l.rotulo}</button>
            ))}
          </div>

          {lente === 'gantt' && (
            <>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, border: '1px solid var(--line)', borderRadius: 8, padding: '4px 9px' }}>
                <Search size={13} style={{ color: 'var(--ink-3)' }} />
                <input
                  value={filtro} onChange={e => setFiltro(e.target.value)}
                  placeholder="Buscar na EAP"
                  style={{ border: 'none', outline: 'none', background: 'none', fontSize: 12.5, color: 'var(--ink)', width: 170 }}
                />
              </label>
              {(Object.keys(ROTULOS_DE_FILTRO) as Filtro[]).map(chave => {
                const ligado = filtros.has(chave)
                return (
                  <button
                    key={chave} type="button" title={ROTULOS_DE_FILTRO[chave].ajuda}
                    onClick={() => setFiltros(atual => {
                      const proximo = new Set(atual)
                      if (proximo.has(chave)) proximo.delete(chave)
                      else proximo.add(chave)
                      return proximo
                    })}
                    style={{
                      border: '1px solid ' + (ligado ? 'var(--brand)' : 'var(--line)'),
                      borderRadius: 999, padding: '3px 11px', fontSize: 12, cursor: 'pointer',
                      background: ligado ? 'var(--inset)' : 'transparent',
                      color: ligado ? 'var(--ink)' : 'var(--ink-3)',
                      fontWeight: ligado ? 600 : 400,
                    }}
                  >
                    {ROTULOS_DE_FILTRO[chave].curto}
                  </button>
                )
              })}
              {filtros.size > 0 && (
                <button
                  type="button" onClick={() => setFiltros(new Set())}
                  style={{ border: 'none', background: 'none', color: 'var(--ink-3)', fontSize: 12, cursor: 'pointer' }}
                >
                  limpar
                </button>
              )}
            </>
          )}

          {!c.editavel && (
            <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
              Plano {c.status_rotulo.toLowerCase()} — somente leitura. Replaneje para abrir a próxima versão.
            </span>
          )}
          {trabalhando && <span style={{ fontSize: 12, color: 'var(--ink-2)' }}>{trabalhando}</span>}
        </div>

        {(erro || historico.erro) && <Faixa tom="erro" onFechar={() => { setErro(''); historico.limparErro() }}>{erro || historico.erro}</Faixa>}
        {aviso && <Faixa tom="aviso" onFechar={() => setAviso('')}>{aviso}</Faixa>}
      </header>

      <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
        <div style={{ flex: 1, minWidth: 0, padding: '12px 22px 16px', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: lente === 'gantt' ? 'hidden' : 'auto' }}>
          {lente === 'gantt' && (
            <GanttCronograma
              dados={dados}
              editavel={editavel}
              filtro={filtro}
              filtros={filtros}
              selecionadas={selecionadas}
              onSelecionar={ids => setSelecionadas(new Set(ids))}
              onEditarCelula={editarCelula}
              onColar={colar}
              onGesto={aoGesto}
              onMenu={(a, ancora) => setMenu({ atividade: a, x: ancora.left, y: ancora.bottom })}
              onAbrirInspetor={setInspecionando}
              onReprogramar={aoReprogramar}
              onLigar={aoLigar}
              onExcluirPrecedencia={aoExcluirPrecedencia}
              onAviso={setAviso}
              onEmBloco={(acao, valor) => void emBloco(acao, valor)}
            />
          )}

          {lente === 'avanco' && podeVerAvanco && (
            <PainelAvanco
              cronograma={c}
              atividades={dados.atividades}
              avanco={dados.avanco}
              podeApontar={podeApontar}
              tetoDoLote={status.data?.tetos?.apontamentos_por_lote ?? 50}
            />
          )}

          {lente === 'base' && (
            <PainelLinhaDeBase
              comparacao={dados.base}
              terminoAtual={c.termino_calculado}
              versaoAtual={c.versao}
            />
          )}

          {lente === 'plano' && (
            <PainelCurvaS
              cronogramaId={id}
              atividades={dados.atividades}
              precedencias={dados.precedencias}
              cobertura={dados.cobertura_orcamento}
              avanco={dados.avanco}
              podeVerOrcamento={podeVerOrcamento}
              obra={c.obra}
            />
          )}
        </div>

        {inspecionada && (
          <InspetorAtividade
            atividade={inspecionada}
            obra={c.obra}
            precedencias={dados.precedencias}
            porId={new Map(dados.atividades.map(a => [a.atividade_id, a]))}
            editavel={editavel}
            podeVerOrcamento={podeVerOrcamento}
            onFechar={() => { setInspecionando(null); busca.delete('atividade'); setBusca(busca, { replace: true }) }}
            onSalvar={payload => {
              const antes: Partial<Atividade> = {}
              for (const chave of Object.keys(payload) as (keyof Atividade)[]) {
                (antes as Record<string, unknown>)[chave] = inspecionada[chave]
              }
              historico.executar({
                rotulo: 'editar ' + inspecionada.codigo,
                fazer: () => patch(inspecionada.atividade_id, payload),
                desfazer: () => patch(inspecionada.atividade_id, antes),
              })
            }}
            onCriarPrecedencia={(origem, tipo, atraso) => {
              const criada = { id: 0 }
              historico.executar({
                rotulo: 'ligar ' + inspecionada.codigo,
                fazer: async () => {
                  const nova = await criarPrec.mutateAsync({
                    origem, destino: inspecionada.atividade_id, tipo, atraso_dias: atraso,
                  })
                  criada.id = nova.precedencia_id
                },
                desfazer: async () => { if (criada.id) await excluirPrec.mutateAsync(criada.id) },
              })
            }}
            onAtualizarPrecedencia={aoAtualizarPrecedencia}
            onExcluirPrecedencia={aoExcluirPrecedencia}
          />
        )}
      </div>

      {menu && (
        <MenuDaAtividade
          atividade={menu.atividade} x={menu.x} y={menu.y} editavel={editavel}
          onFechar={() => setMenu(null)}
          onAcao={acao => {
            setMenu(null)
            if (acao === 'inspecionar') setInspecionando(menu.atividade.atividade_id)
            else aoGesto(acao, menu.atividade)
          }}
        />
      )}

      {salvandoModelo && (
        <ModalSalvarComoModelo cronograma={c} aoFechar={() => setSalvandoModelo(false)} />
      )}

      {replanejando && (
        <Modal titulo="Replanejar o cronograma" onClose={() => setReplanejando(false)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 4 }}>
            <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6, margin: 0 }}>
              A versão vigente vira <strong>linha de base</strong> e uma nova cópia editável nasce como
              rascunho. O motivo fica gravado: é o que explica, seis meses depois, por que o prazo mudou.
            </p>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 5, fontSize: 13 }}>
              <span>Motivo do replanejamento</span>
              <textarea
                rows={3} value={motivo} onChange={e => setMotivo(e.target.value)}
                placeholder="Ex.: chuva acima da média em março e atraso na entrega das esquadrias"
              />
            </label>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <Btn onClick={() => setReplanejando(false)}>Cancelar</Btn>
              <Btn variant="brand" onClick={replanejarPlano} disabled={!motivo.trim() || replanejar.isPending}>
                {replanejar.isPending ? 'Replanejando…' : 'Replanejar'}
              </Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------

type AcaoDoMenu = GestoDeEstrutura | 'inspecionar'

function MenuDaAtividade({ atividade, x, y, editavel, onAcao, onFechar }: {
  atividade: Atividade
  x: number
  y: number
  editavel: boolean
  onAcao: (acao: AcaoDoMenu) => void
  onFechar: () => void
}) {
  useEffect(() => {
    const fechar = () => onFechar()
    window.addEventListener('pointerdown', fechar)
    return () => window.removeEventListener('pointerdown', fechar)
  }, [onFechar])

  const itens: { acao: AcaoDoMenu; rotulo: string; atalho?: string; some?: boolean }[] = [
    { acao: 'inspecionar', rotulo: 'Abrir o inspetor', atalho: 'duplo clique' },
    { acao: 'inserir', rotulo: 'Inserir atividade abaixo', atalho: 'Insert', some: !editavel },
    { acao: 'indentar', rotulo: 'Indentar', atalho: 'Alt+→', some: !editavel },
    { acao: 'outdentar', rotulo: 'Promover', atalho: 'Alt+←', some: !editavel },
    { acao: 'subir', rotulo: 'Subir', atalho: 'Alt+↑', some: !editavel },
    { acao: 'descer', rotulo: 'Descer', atalho: 'Alt+↓', some: !editavel },
    { acao: 'excluir', rotulo: 'Excluir', atalho: 'Ctrl+Del', some: !editavel },
  ]

  return (
    <div
      onPointerDown={e => e.stopPropagation()}
      style={{
        position: 'fixed', left: Math.min(x, window.innerWidth - 250), top: y + 4, zIndex: 80,
        background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 10,
        boxShadow: 'var(--shadow-md)', padding: 6, minWidth: 230,
      }}
    >
      <div style={{ padding: '4px 8px 6px', fontSize: 11, color: 'var(--ink-3)', borderBottom: '1px solid var(--line)', marginBottom: 4 }}>
        {atividade.codigo} {atividade.nome}
      </div>
      {itens.filter(i => !i.some).map(i => (
        <button
          key={i.acao} onClick={() => onAcao(i.acao)}
          style={{
            display: 'flex', width: '100%', alignItems: 'center', justifyContent: 'space-between',
            gap: 12, border: 'none', background: 'none', cursor: 'pointer', padding: '6px 8px',
            fontSize: 12.5, color: i.acao === 'excluir' ? 'var(--danger-ink)' : 'var(--ink)',
            borderRadius: 6, textAlign: 'left',
          }}
        >
          {i.rotulo}
          {i.atalho && <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>{i.atalho}</span>}
        </button>
      ))}
    </div>
  )
}

function Faixa({ tom, children, onFechar }: { tom: 'erro' | 'aviso'; children: React.ReactNode; onFechar: () => void }) {
  const erro = tom === 'erro'
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 12px', borderRadius: 8,
      fontSize: 12.5, lineHeight: 1.5,
      background: erro ? 'var(--danger-soft)' : 'var(--inset)',
      color: erro ? 'var(--danger-ink)' : 'var(--ink-2)',
      border: '1px solid ' + (erro ? 'var(--danger-soft)' : 'var(--line)'),
    }}>
      <span style={{ flex: 1 }}>{children}</span>
      <button onClick={onFechar} style={{ border: 'none', background: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}>×</button>
    </div>
  )
}

/** O valor colado vira o que a API espera. A conversão vive aqui, e não na
 *  grade, pelo mesmo motivo da edição de célula: a planilha não conhece o
 *  domínio. */
function converter(campo: CampoEditavel, valor: string): unknown {
  if (campo === 'duracao_dias') return valor === '' ? null : Number(valor.replace(/\D/g, ''))
  if (campo === 'nao_comecar_antes_de') return valor ? dateFromBR(valor) || null : null
  if (campo === 'peso_informado') {
    const limpo = valor.replace(/\./g, '').replace(',', '.')
    return limpo === '' ? null : limpo
  }
  return valor
}

/** Divide em blocos do tamanho que o servidor aceita por chamada. */
function fatiar<T>(lista: T[], tamanho: number): T[][] {
  const blocos: T[][] = []
  for (let i = 0; i < lista.length; i += tamanho) blocos.push(lista.slice(i, i + tamanho))
  return blocos
}
