import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowDown, ArrowUp, Calculator, CheckCircle2, ChevronRight, Copy as CopyIcon,
  Download, ExternalLink, FileSpreadsheet, FolderPlus, GitBranch, Indent, Library, Lock, Outdent,
  HelpCircle, PanelRight, Percent, Plus, RefreshCw, Redo2, Replace, RotateCcw, Ruler, Search,
  Sigma, Trash2, TrendingUp,
  Undo2, Unlock, Upload, X,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import PaginaShell from '../components/PaginaShell'
import MedicaoDrawer from '../components/MedicaoDrawer'
import GradeOrcamento, {
  type AcaoRapida, type Alvo, type ColunaEditavel, type ColunaInsumo, type EdicaoCelula,
  type OperacaoDeBloco, type PedidoDeMover,
} from '../components/GradeOrcamento'
import InserirItemModal, { type Escolha } from '../components/InserirItemModal'
import PainelDeBanco from '../components/PainelDeBanco'
import SeletorDeBase from '../components/SeletorDeBase'
import { Aviso, Btn, Card, CAPS, Empty, Field, inp, Loading, Modal, mono, Pill, Select, Seletor, Spinner, Drawer, Info } from '../ui'
import { brl, mesBR, num, paraDecimal, pct, STATUS_ESTADO } from '../lib'
import * as api from '../api/orcamentoApi'
import { baixarExportacao } from '../api/orcamentoApi'
import {
  useAnalitica, useAprovar, useArvore, useBasesResumo, useCriarItem, useEditarCelula,
  useExplodir, useItemDoCatalogo, useMemoria, useObras, usePrecoReal, useRecalcular,
  useRevisar, useAplicarPrecoReal, useAtualizarOrcamento,
  useAplicarReprecificacao, useDesfazerReprecificacao, useDuplicarOrcamento,
  useGerarPreviaReprecificacao, useHistoricoReprecificacao,
  // ORC.10
  useAplicarPercentual, useArredondarItens, useCriarInsumo, useDestravarOrcamento,
  useDuplicarItens, useEditarInsumo, useExcluirItens, useMoverItens, usePromoverComposicao,
  useRemoverInsumo, useRestaurarItens, useSubstituirTexto,
} from '../hooks'
import { useHistorico } from '../historico'
import type {
  BaseResumo, CategoriaInsumo, InsumoReferencia, ItemOrcado, ItemOrcadoInsumo, ObraOpt,
  PreviaReprecificacao,
} from '../types'

import { minCalendarioISO, maxCalendarioISO } from '@/utils/dates'
import { contemSemAcento } from '@/utils/texto'
import { useAjudaDaTela, useAssistente } from '@/components/assistente/contexto'
import type { AjudaDaTela } from '@/components/assistente/contexto'

/** O que a planilha sabe fazer, dito em português.
 *
 *  **Mora fora do componente de propósito.** O objeto precisa ser estável — se
 *  fosse recriado a cada render, a publicação no assistente entraria em laço.
 *  Constante de módulo resolve isso sem `useMemo` e sem dependência nenhuma.
 *
 *  As `dicas` são as quatro coisas que alguém precisa saber para não ficar preso
 *  na primeira tentativa; os `grupos` são a referência inteira. A ordem das
 *  dicas é a ordem em que a pessoa esbarra nos problemas: primeiro ela quer
 *  digitar, depois mexer numa linha, depois em várias, depois desfazer.
 */
const AJUDA_DA_PLANILHA: AjudaDaTela = {
  tela: 'Planilha orçamentária',
  // A primeira dica é a que responde a dúvida número um. Ela mudou de conteúdo
  // quando os três pontos viraram ícones: antes explicava o que havia atrás do
  // ⋮, agora conta que os verbos estão na própria linha — porque a pergunta
  // deixou de ser "o que é isso" e passou a ser "onde ficam".
  dicas: [
    'Passe o mouse numa linha e os ícones das ações aparecem à direita, cada um '
      + 'a um clique: memória de cálculo, memória do quantitativo, duplicar e '
      + 'excluir. A chave inglesa abre o resto (preço real, explodir composição, '
      + 'travar preço), e o botão direito do mouse abre o mesmo menu.',
    'Para digitar numa célula, clique nela e comece a escrever — ou aperte Enter '
      + 'para abrir. Tab e as setas andam pela grade, como no Excel.',
    'Clique numa linha para marcá-la. Shift marca a faixa, Ctrl soma uma linha, e '
      + 'a barra que aparece embaixo age sobre tudo o que estiver marcado.',
    'Errou? Ctrl+Z desfaz e Ctrl+Y refaz — inclusive exclusão. A pilha vale '
      + 'enquanto esta planilha estiver aberta.',
    'Alt com as setas reorganiza a EAP: ← e → tiram e põem nível, ↑ e ↓ movem a '
      + 'linha. Arrastar com o mouse faz o mesmo.',
  ],
  grupos: [
    {
      titulo: 'Digitar na grade',
      itens: [
        { gesto: 'clique + digitar', faz: 'abre a célula já com o que você escreveu' },
        { gesto: 'Enter ou F2', faz: 'abre a célula para editar' },
        { gesto: 'Tab · Shift+Tab', faz: 'anda para a célula seguinte ou anterior' },
        { gesto: '↑ ↓ ← →', faz: 'move o cursor pela grade' },
        { gesto: 'Esc', faz: 'cancela a edição da célula' },
        { gesto: 'Ctrl+V', faz: 'cola um bloco vindo do Excel a partir da célula com foco' },
        { gesto: 'digitar no código', faz: 'assume o código EAP à mão (aparece um cadeado)' },
      ],
    },
    {
      titulo: 'Escolher linhas',
      itens: [
        { gesto: 'clique na linha', faz: 'marca só ela' },
        { gesto: 'Shift+clique', faz: 'marca a faixa entre a última marcada e esta' },
        { gesto: 'Ctrl+clique', faz: 'soma ou tira uma linha da marcação' },
        { gesto: 'Ctrl+Shift+clique', faz: 'soma a faixa inteira ao que já estava marcado' },
        { gesto: 'Shift+↑ ↓', faz: 'estende a marcação pelo teclado' },
        { gesto: 'Ctrl+A', faz: 'marca tudo o que está à vista (respeita o filtro)' },
        { gesto: 'caixa do cabeçalho', faz: 'marca ou desmarca tudo o que está à vista' },
        { gesto: 'Esc', faz: 'limpa a marcação' },
      ],
    },
    {
      titulo: 'Organizar a EAP',
      itens: [
        { gesto: 'arrastar a linha', faz: 'move; solte no meio para entrar dentro, na borda para ficar acima ou abaixo' },
        { gesto: 'Alt+→', faz: 'indenta — pendura na linha de cima' },
        { gesto: 'Alt+←', faz: 'desindenta — sobe um nível' },
        { gesto: 'Alt+↑ · Alt+↓', faz: 'sobe ou desce a linha entre as irmãs' },
        { gesto: 'espaço', faz: 'recolhe ou expande a etapa' },
        { gesto: 'Delete', faz: 'pede a exclusão do que está marcado (pergunta antes)' },
      ],
    },
    {
      titulo: 'Agir sobre várias de uma vez',
      itens: [
        { gesto: 'barra de baixo', faz: 'aparece com a marcação: mover, duplicar, ±%, arredondar, excluir' },
        { gesto: '±% + Enter', faz: 'aplica o percentual no custo ou na quantidade das marcadas' },
        { gesto: 'linha com traço ao lado', faz: 'vai junto por pender de uma marcada — o diálogo de excluir conta quantas' },
      ],
    },
    {
      titulo: 'Ações de uma linha',
      itens: [
        { gesto: 'passar o mouse', faz: 'acende os ícones das ações à direita da linha' },
        { gesto: 'ícone de planilha', faz: 'memória de cálculo — de que insumos o preço é feito' },
        { gesto: 'ícone de régua', faz: 'memória do quantitativo — de onde veio a quantidade' },
        { gesto: 'ícone de cópia', faz: 'duplica a linha com o que pende dela' },
        { gesto: 'ícone de lixeira', faz: 'exclui (pergunta antes)' },
        { gesto: 'chave inglesa', faz: 'as demais ações: preço real, explodir, sub-item, travar preço, descrição detalhada, salvar composição' },
        { gesto: 'botão direito', faz: 'abre o mesmo menu da chave inglesa' },
      ],
    },
    {
      titulo: 'Composição do serviço',
      itens: [
        { gesto: 'aba Analítico', faz: 'abre a composição de cada serviço embaixo dele' },
        { gesto: 'duplo clique no insumo', faz: 'edita coeficiente, preço, descrição ou unidade' },
        { gesto: '+ somar insumo', faz: 'acrescenta um insumo à composição' },
        { gesto: '⋮ → Salvar composição no banco', faz: 'guarda a composição ajustada no banco da empresa' },
      ],
    },
    {
      titulo: 'Desfazer, procurar e trazer preço',
      itens: [
        { gesto: 'Ctrl+Z · Ctrl+Y', faz: 'desfaz e refaz, inclusive exclusão' },
        { gesto: 'Filtrar linhas', faz: 'esconde o que não casa; a marcação passa a respeitar o filtro' },
        { gesto: 'botão de substituir', faz: 'localiza e substitui na descrição (não entra no Ctrl+Z)' },
        { gesto: 'botão do painel', faz: 'abre o banco de preço ao lado, para arrastar itens para a planilha' },
        { gesto: '?', faz: 'abre e fecha esta lista' },
      ],
    },
  ],
}

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
  // ORC.10d — a seleção mora aqui, e não na grade, porque a barra de lote age
  // sobre ela e precisa saber o tamanho para aparecer.
  const [selecao, setSelecao] = useState<ReadonlySet<number>>(new Set())
  const [substituindo, setSubstituindo] = useState(false)
  const [destravando, setDestravando] = useState(false)
  const [insumoNovoDe, setInsumoNovoDe] = useState<ItemOrcado | null>(null)
  const [textoLongoDe, setTextoLongoDe] = useState<ItemOrcado | null>(null)
  // ORC.10f — o banco acoplado. Fechado por padrão: a grade é o módulo, e a
  // tela não deve nascer com 318px a menos sem alguém ter pedido.
  // O que está prestes a ser excluído, esperando confirmação. `null` = nada
  // pendente. Guarda os ids, e não a seleção, porque o excluir do menu da linha
  // usa o mesmo caminho e pode agir sobre uma linha que não está marcada.
  const [aExcluir, setAExcluir] = useState<number[] | null>(null)
  const [painelAberto, setPainelAberto] = useState(false)
  const [doBanco, setDoBanco] = useState<InsumoReferencia | null>(null)

  const editarCelula = useEditarCelula(orcamentoId)
  const criarItem = useCriarItem()
  const itemDoCatalogo = useItemDoCatalogo()
  const recalcular = useRecalcular()
  const aprovar = useAprovar()
  const revisar = useRevisar()
  const explodir = useExplodir()
  const atualizarOrcamento = useAtualizarOrcamento()
  // ORC.10
  const moverItens = useMoverItens()
  const duplicarItens = useDuplicarItens()
  const excluirItens = useExcluirItens()
  const restaurarItens = useRestaurarItens()
  const aplicarPercentual = useAplicarPercentual()
  const arredondarItens = useArredondarItens()
  const substituirTexto = useSubstituirTexto()
  const criarInsumo = useCriarInsumo()
  const editarInsumo = useEditarInsumo()
  const removerInsumo = useRemoverInsumo()
  const promoverComposicao = usePromoverComposicao()
  const destravarOrcamento = useDestravarOrcamento()
  const historico = useHistorico()

  const orcamento = arvore?.orcamento
  const podeEditar = hasPermission('orcamento.orcamento.edit') && !!orcamento?.editavel
  const podeAprovar = hasPermission('orcamento.orcamento.aprovar')
  const podeRevisar = hasPermission('orcamento.orcamento.revisar')
  const podeDestravar = hasPermission('orcamento.orcamento.destravar')
  const podePromover = hasPermission('orcamento.banco.edit')
  const marcados = useMemo(() => [...selecao], [selecao])

  // Publica a ajuda desta tela no assistente da plataforma. Só quando há
  // planilha aberta: na lista de obras as dicas falariam de uma grade que não
  // está na frente de ninguém.
  const { abrirPainel } = useAssistente()
  useAjudaDaTela(orcamentoId ? AJUDA_DA_PLANILHA : null)

  /** O **escopo real** de qualquer gesto sobre a seleção.
   *
   *  Marcar uma etapa e apertar Excluir leva os serviços dela: o servidor faz
   *  isso desde sempre (apagar uma etapa sem o conteúdo não é apagar, é
   *  desmontar), e a tela não dizia. A barra contava "1 linha selecionada" e
   *  sumiam doze — pior ainda quando a etapa está **recolhida** e os doze nem
   *  estão à vista.
   *
   *  `valor` é o total com BDI que sai do orçamento, somado só nas **raízes** da
   *  seleção: somar raiz e descendente contaria o mesmo dinheiro duas vezes, que
   *  é a mesma razão de `recalcular_orcamento` somar só as raízes. */
  const escopo = useMemo(() => {
    const itens = arvore?.itens ?? []
    if (!itens.length || selecao.size === 0) {
      return { raizes: [] as ItemOrcado[], descendentes: new Set<number>(), valor: 0 }
    }
    const filhosDe = new Map<number | null, number[]>()
    for (const i of itens) {
      const lista = filhosDe.get(i.pai)
      if (lista) lista.push(i.item_orcado_id)
      else filhosDe.set(i.pai, [i.item_orcado_id])
    }
    const descendentes = new Set<number>()
    const pilha = [...selecao]
    while (pilha.length) {
      const atual = pilha.pop() as number
      for (const filho of filhosDe.get(atual) ?? []) {
        if (descendentes.has(filho)) continue
        descendentes.add(filho)
        pilha.push(filho)
      }
    }
    // Marcado que está dentro de outro marcado não é raiz — a subárvore dele já
    // vai pela do ancestral, e contá-lo dobraria o valor.
    const raizes = itens.filter(
      i => selecao.has(i.item_orcado_id) && !descendentes.has(i.item_orcado_id),
    )
    const valor = raizes.reduce((soma, i) => soma + Number(i.total_com_bdi || 0), 0)
    // O que já estava marcado não conta de novo como "vai junto".
    for (const id of selecao) descendentes.delete(id)
    return { raizes, descendentes, valor }
  }, [arvore, selecao])

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

  // --- ORC.10: seleção, estrutura, lote e desfazer ------------------------

  /** A planilha trocou de endereço: a seleção e a pilha são daquela planilha. */
  const limparHistorico = historico.limpar
  useEffect(() => {
    setSelecao(new Set())
    limparHistorico()
  }, [orcamentoId, limparHistorico])

  /** Tira da seleção o que não existe mais.
   *
   *  Sem isto a seleção vira um saco de fantasmas: excluir, desfazer (que
   *  **recria com ids novos**) ou receber a árvore de novo deixavam ids mortos
   *  marcados. A barra contava linhas que não estão na tela, e o primeiro verbo
   *  de lote levava o id morto ao servidor, que responde 400 dizendo que a
   *  linha não é deste orçamento — mensagem correta para uma pergunta que a
   *  tela não devia ter feito. */
  useEffect(() => {
    const vivos = arvore?.itens
    if (!vivos) return
    setSelecao(atual => {
      if (atual.size === 0) return atual
      const existentes = new Set(vivos.map(i => i.item_orcado_id))
      const podada = [...atual].filter(id => existentes.has(id))
      return podada.length === atual.size ? atual : new Set(podada)
    })
  }, [arvore])

  /** Atalhos globais da planilha. `Ctrl+Z`/`Ctrl+Y` só saem daqui — a grade não
   *  os captura porque o foco pode estar no filtro, no menu ou em lugar nenhum,
   *  e um desfazer que depende de onde está o cursor não é desfazer. */
  useEffect(() => {
    const aoTeclar = (e: globalThis.KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return
      const alvo = e.target as HTMLElement | null
      // Dentro de um campo de texto, Ctrl+Z é do campo — o navegador desfaz a
      // digitação, que é o que a pessoa espera ali.
      if (alvo && /^(INPUT|TEXTAREA|SELECT)$/.test(alvo.tagName)) return
      const tecla = e.key.toLowerCase()
      if (tecla === 'z' && !e.shiftKey) {
        e.preventDefault()
        historico.desfazer().then(r => r && setRecado(`Desfeito: ${r}.`))
      } else if (tecla === 'y' || (tecla === 'z' && e.shiftKey)) {
        e.preventDefault()
        historico.refazer().then(r => r && setRecado(`Refeito: ${r}.`))
      } else if (tecla === 'a' && podeEditar) {
        // **Só o que está à vista.** Antes marcava a planilha inteira ignorando
        // o filtro: quem procura "alvenaria", vê três linhas e manda marcar
        // tudo, marcava quatrocentas — e o gesto seguinte costuma ser Excluir.
        e.preventDefault()
        const busca = filtro.trim()
        const visiveis = (arvore?.itens ?? []).filter(
          i => !busca
            || contemSemAcento(i.descricao, busca)
            || contemSemAcento(i.codigo_referencia, busca)
            || contemSemAcento(i.codigo_eap, busca),
        )
        setSelecao(new Set(visiveis.map(i => i.item_orcado_id)))
      }
    }
    document.addEventListener('keydown', aoTeclar)
    return () => document.removeEventListener('keydown', aoTeclar)
  }, [historico, arvore, podeEditar, filtro])

  function selecionar(ids: number[], modo: 'trocar' | 'alternar' | 'faixa' | 'somar-faixa') {
    setSelecao(atual => {
      // `trocar` e `faixa` **substituem**; `somar-faixa` acrescenta a faixa ao
      // que já havia (Ctrl+Shift), e `alternar` liga/desliga uma linha (Ctrl).
      // São quatro gestos distintos, e tratá-los como dois — que era o caso —
      // deixava sem resposta o pedido mais comum em planilha grande: marcar
      // três trechos separados da EAP.
      if (modo === 'trocar' || modo === 'faixa') return new Set(ids)
      const proximo = new Set(atual)
      if (modo === 'somar-faixa') {
        for (const id of ids) proximo.add(id)
        return proximo
      }
      for (const id of ids) {
        if (proximo.has(id)) proximo.delete(id)
        else proximo.add(id)
      }
      return proximo
    })
  }

  /** Guarda o estado de origem das linhas que vão se mexer, para o desfazer.
   *
   *  Só `pai` e `ordem`: é o que `mover` altera. Devolver a árvore inteira ao
   *  desfazer seria mais seguro e muito mais caro — e `mover` já renumera a
   *  ordem densa, então repor pai e posição recompõe o mesmo arranjo. */
  function posicoesDe(ids: number[]) {
    const mapa = new Map((arvore?.itens ?? []).map(i => [i.item_orcado_id, i]))
    return ids.map(id => {
      const item = mapa.get(id)
      return { id, pai: item?.pai ?? null, ordem: item?.ordem ?? 0 }
    })
  }

  async function reporPosicoes(origem: { id: number; pai: number | null; ordem: number }[]) {
    if (!orcamentoId) return
    // De trás para frente: repondo o último primeiro, cada `posicao` guardada
    // continua valendo quando chega a vez do anterior.
    for (const p of [...origem].sort((a, b) => b.ordem - a.ordem)) {
      await moverItens.mutateAsync({
        orcamento: orcamentoId, itens: [p.id], pai: p.pai, posicao: p.ordem,
      })
    }
  }

  function aoFalhar(e: unknown, padrao: string) {
    const dados = (e as { response?: { data?: Record<string, unknown> } })?.response?.data
    const detalhe = dados?.detail ?? (dados && Object.values(dados)[0])
    setRecado(
      Array.isArray(detalhe) ? String(detalhe[0]) : detalhe ? String(detalhe) : padrao,
    )
  }

  async function moverBloco(pedido: PedidoDeMover) {
    if (!orcamentoId) return
    const origem = posicoesDe(pedido.itens)
    try {
      await moverItens.mutateAsync({ orcamento: orcamentoId, ...pedido })
      historico.registrar({
        rotulo: `mover ${pedido.itens.length} linha(s)`,
        desfazer: () => reporPosicoes(origem),
        refazer: async () => { await moverItens.mutateAsync({ orcamento: orcamentoId, ...pedido }) },
      })
    } catch (e) {
      aoFalhar(e, 'Não foi possível mover.')
    }
  }

  async function operacaoDeBloco(operacao: OperacaoDeBloco, itens: number[]) {
    if (!orcamentoId) return
    const origem = posicoesDe(itens)
    const nome = {
      indentar: 'indentar', desindentar: 'desindentar', cima: 'subir', baixo: 'descer',
    }[operacao]
    try {
      await moverItens.mutateAsync({ orcamento: orcamentoId, itens, operacao })
      historico.registrar({
        rotulo: `${nome} ${itens.length} linha(s)`,
        desfazer: () => reporPosicoes(origem),
        refazer: async () => { await moverItens.mutateAsync({ orcamento: orcamentoId, itens, operacao }) },
      })
    } catch (e) {
      aoFalhar(e, 'Não foi possível reorganizar.')
    }
  }

  /** Edição de célula com desfazer. O valor anterior vem da própria linha, que
   *  é a cópia que a tela está exibindo — e é o que o Ctrl+Z precisa repor. */
  function editarLinha(item: ItemOrcado, coluna: ColunaEditavel, valor: string) {
    const anterior = String(item[coluna] ?? '')
    // Digitar por cima do código EAP **é** o ato de assumi-lo à mão. Pedir uma
    // segunda confirmação faria o primeiro gesto parecer quebrado (digita, o
    // recálculo renumera, some).
    const extra = coluna === 'codigo_eap' ? { eap_manual: true } : {}
    const aplicar = (v: string, manual?: boolean) => editarCelula.mutateAsync({
      id: item.item_orcado_id,
      payload: {
        [coluna]: v,
        ...(coluna === 'codigo_eap' ? { eap_manual: manual ?? true } : {}),
      } as Partial<ItemOrcado>,
    })
    editarCelula.mutate({
      id: item.item_orcado_id,
      payload: { [coluna]: valor, ...extra } as Partial<ItemOrcado>,
    })
    historico.registrar({
      rotulo: `editar ${coluna === 'codigo_eap' ? 'código' : coluna}`,
      desfazer: async () => { await aplicar(anterior, item.eap_manual) },
      refazer: async () => { await aplicar(valor) },
    })
  }

  async function duplicarSelecao() {
    if (!orcamentoId || !marcados.length) return
    try {
      const r = await duplicarItens.mutateAsync({ orcamento: orcamentoId, itens: marcados })
      setRecado(`${r.criadas} linha(s) duplicada(s).`)
      historico.registrar({
        rotulo: `duplicar ${r.criadas} linha(s)`,
        desfazer: async () => { await excluirItens.mutateAsync({ orcamento: orcamentoId, itens: r.itens }) },
        refazer: async () => { await duplicarItens.mutateAsync({ orcamento: orcamentoId, itens: marcados }) },
      })
    } catch (e) {
      aoFalhar(e, 'Não foi possível duplicar.')
    }
  }

  /** Exclui de verdade — só é chamado depois do diálogo confirmar.
   *
   *  **Desfazer e refazer são simétricos**, e isso custou um detalhe: `restaurar`
   *  recria as linhas com **ids novos** (o banco não reaproveita chave primária),
   *  então um refazer que tentasse reexcluir pelos ids antigos não acharia nada.
   *  A saída é o próprio `restaurar` devolver os ids que criou: o refazer exclui
   *  *esses*, e o desfazer seguinte volta a guardar o material novo. A pilha
   *  passa a andar para os dois lados quantas vezes se quiser, que é o que
   *  Ctrl+Z e Ctrl+Y prometem.
   */
  async function excluirAgora(ids: number[]) {
    if (!orcamentoId || !ids.length) return
    try {
      const r = await excluirItens.mutateAsync({ orcamento: orcamentoId, itens: ids })
      setSelecao(new Set())
      setRecado(`${r.excluidas} linha(s) excluída(s) — Ctrl+Z desfaz.`)

      // `material` é o que recria as linhas; ele é **substituído** a cada
      // exclusão do ciclo, porque cada rodada de restaurar gera ids diferentes.
      let material = r.desfazer
      let ultimosIds = ids
      const passo = {
        rotulo: `excluir ${r.excluidas} linha(s)`,
        desfazer: async () => {
          const volta = await restaurarItens.mutateAsync({
            orcamento: orcamentoId, linhas: material,
          })
          ultimosIds = volta.itens
        },
        refazer: async () => {
          const denovo = await excluirItens.mutateAsync({
            orcamento: orcamentoId, itens: ultimosIds,
          })
          material = denovo.desfazer
        },
      }
      historico.registrar(passo)
    } catch (e) {
      aoFalhar(e, 'Não foi possível excluir.')
    }
  }

  /** Pede a exclusão — quem confirma é o diálogo, que diz o que vai embora. */
  function pedirExclusao(ids: number[]) {
    if (!ids.length) return
    setAExcluir(ids)
  }

  function excluirSelecao() {
    pedirExclusao(marcados)
  }

  async function percentualNaSelecao(percentual: string, campo: 'custo_unitario' | 'quantidade') {
    if (!orcamentoId || !marcados.length) return
    const inverso = String(100 / (1 + Number(percentual) / 100) - 100)
    try {
      const r = await aplicarPercentual.mutateAsync({
        orcamento: orcamentoId, itens: marcados, percentual, campo,
      })
      setRecado(`${percentual}% aplicado em ${r.afetadas} linha(s).`)
      historico.registrar({
        rotulo: `aplicar ${percentual}%`,
        // O inverso de +10% é −9,0909…%, e não −10%: é a razão que se desfaz,
        // não a diferença. Usar −10% deixaria a planilha alguns centavos abaixo
        // do original a cada ida e volta.
        desfazer: async () => {
          await aplicarPercentual.mutateAsync({
            orcamento: orcamentoId, itens: marcados, percentual: inverso, campo,
          })
        },
        refazer: async () => {
          await aplicarPercentual.mutateAsync({
            orcamento: orcamentoId, itens: marcados, percentual, campo,
          })
        },
      })
    } catch (e) {
      aoFalhar(e, 'Não foi possível aplicar o percentual.')
    }
  }

  async function arredondarSelecao(casas: number, campo: 'custo_unitario' | 'quantidade') {
    if (!orcamentoId || !marcados.length) return
    try {
      const r = await arredondarItens.mutateAsync({
        orcamento: orcamentoId, itens: marcados, casas, campo,
      })
      // Arredondar não entra na pilha: o inverso não existe (a casa descartada
      // se perdeu), e oferecer um desfazer que não devolve o número seria pior
      // que não oferecer nenhum.
      setRecado(`${r.afetadas} linha(s) arredondada(s) — não há como desfazer.`)
    } catch (e) {
      aoFalhar(e, 'Não foi possível arredondar.')
    }
  }

  // --- ORC.10c: a composição -----------------------------------------------

  async function mexerNoInsumo(insumo: ItemOrcadoInsumo, coluna: ColunaInsumo, valor: string) {
    const anterior = String(insumo[coluna] ?? '')
    try {
      await editarInsumo.mutateAsync({ id: insumo.insumo_id, payload: { [coluna]: valor } })
      historico.registrar({
        rotulo: `editar insumo (${coluna})`,
        desfazer: async () => {
          await editarInsumo.mutateAsync({ id: insumo.insumo_id, payload: { [coluna]: anterior } })
        },
        refazer: async () => {
          await editarInsumo.mutateAsync({ id: insumo.insumo_id, payload: { [coluna]: valor } })
        },
      })
    } catch (e) {
      aoFalhar(e, 'Não foi possível alterar a composição.')
    }
  }

  /** Soltou um item do painel do banco sobre uma linha — ORC.10f.
   *
   *  São dois passos porque são duas coisas: `do-catalogo` sabe criar a linha
   *  com o snapshot e o preço da publicação de onde ela veio (ORC.10a), e
   *  `mover` sabe pousá-la na posição exata com a EAP renumerada. Fundir os
   *  dois num endpoint só duplicaria a lógica de árvore que já está testada.
   */
  async function soltarDoBanco(alvo: Alvo) {
    const referencia = doBanco
    setDoBanco(null)
    if (!referencia || !orcamentoId || !arvore) return
    const destino = arvore.itens.find(i => i.item_orcado_id === alvo.id)
    if (!destino) return
    try {
      const adocao = await api.adotarLote([referencia.referencia_id])
      const adotado = adocao.itens?.[0]
      if (!adotado) {
        setRecado(
          'O código já existe no seu catálogo descrevendo outro insumo — confira em Bases & bancos.',
        )
        return
      }
      const paiDestino = alvo.zona === 'dentro' ? destino.item_orcado_id : destino.pai
      const linha = await itemDoCatalogo.mutateAsync({
        orcamento: orcamentoId,
        item: adotado.item_id,
        quantidade: '1',
        pai: paiDestino,
        base: referencia.base,
      })
      if (alvo.zona !== 'dentro') {
        const irmaos = arvore.itens
          .filter(i => i.pai === destino.pai)
          .sort((a, b) => a.ordem - b.ordem || a.item_orcado_id - b.item_orcado_id)
        const indice = irmaos.findIndex(i => i.item_orcado_id === destino.item_orcado_id)
        await moverItens.mutateAsync({
          orcamento: orcamentoId,
          itens: [linha.item_orcado_id],
          pai: paiDestino,
          posicao: alvo.zona === 'antes' ? indice : indice + 1,
        })
      }
      setRecado(`${referencia.codigo} inserido — digite a quantidade na grade.`)
    } catch (e) {
      aoFalhar(e, 'Não foi possível inserir o item arrastado.')
    }
  }

  /** Os quatro verbos que a linha oferece direto, sem passar por menu.
   *
   *  São os mesmos handlers do menu — de propósito: dois caminhos para o mesmo
   *  verbo têm de fazer a mesma coisa, inclusive perguntar antes de excluir e
   *  entrar na pilha do Ctrl+Z. Duplicar aqui age **só nesta linha** mesmo
   *  havendo seleção: o gesto foi dado na linha, e a barra de lote é quem age
   *  sobre a seleção. Excluir é a exceção, e ela está declarada lá embaixo. */
  async function acaoRapida(item: ItemOrcado, acao: AcaoRapida) {
    if (acao === 'memoria') { setMemoriaDe(item); return }
    if (acao === 'quantitativo') { setMedicaoDe(item); return }
    if (acao === 'excluir') {
      // Dentro da seleção, o gesto vale para ela inteira — clicar na lixeira de
      // uma das dez linhas marcadas para apagar só aquela seria o contrário do
      // que o dedo acabou de dizer. Fora, vale só para a linha.
      pedirExclusao(selecao.has(item.item_orcado_id) ? marcados : [item.item_orcado_id])
      return
    }
    if (!orcamentoId) return
    try {
      const r = await duplicarItens.mutateAsync({
        orcamento: orcamentoId, itens: [item.item_orcado_id],
      })
      setRecado(`${r.criadas} linha(s) duplicada(s).`)
    } catch (e) {
      aoFalhar(e, 'Não foi possível duplicar.')
    }
  }

  async function tirarInsumo(insumo: ItemOrcadoInsumo) {
    try {
      await removerInsumo.mutateAsync(insumo.insumo_id)
      setRecado('Insumo retirado — o custo unitário foi refeito.')
    } catch (e) {
      aoFalhar(e, 'Não foi possível retirar o insumo.')
    }
  }


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
        // ORC.10a — de onde o item foi pescado é de onde o preço vem. Sem isto
        // o servidor cai na publicação do cabeçalho, que é a regra antiga.
        base: escolha.baseId ?? null,
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
      {podeEditar && (
        <>
          <Btn
            tam="sm"
            disabled={!historico.podeDesfazer || historico.ocupado}
            title={historico.proximoDesfazer ? `Desfazer: ${historico.proximoDesfazer} (Ctrl+Z)` : 'Nada a desfazer'}
            onClick={() => historico.desfazer().then(r => r && setRecado(`Desfeito: ${r}.`))}
          ><Undo2 size={13} /></Btn>
          <Btn
            tam="sm"
            disabled={!historico.podeRefazer || historico.ocupado}
            title={historico.proximoRefazer ? `Refazer: ${historico.proximoRefazer} (Ctrl+Y)` : 'Nada a refazer'}
            onClick={() => historico.refazer().then(r => r && setRecado(`Refeito: ${r}.`))}
          ><Redo2 size={13} /></Btn>
        </>
      )}
      {podeEditar && <Btn tam="sm" variant="primary" onClick={() => setInserindo(true)}><Plus size={13} />Item</Btn>}
      {podeEditar && <Btn tam="sm" onClick={adicionarGrupo}><FolderPlus size={13} />Etapa</Btn>}
      {podeEditar && (
        <Btn tam="sm" onClick={() => setSubstituindo(true)} title="Localizar e substituir na descrição">
          <Replace size={13} />
        </Btn>
      )}
      {/* Com texto, e não só o ponto de interrogação: este é o botão que existe
          justamente porque o resto não se explicava sozinho — seria irônico
          escondê-lo atrás de um ícone. */}
      <Btn
        tam="sm"
        onClick={abrirPainel}
        title="Tudo o que dá para fazer nesta planilha (tecla ?)"
      ><HelpCircle size={13} />Ajuda</Btn>
      {podeEditar && (
        <Btn
          tam="sm"
          variant={painelAberto ? 'primary' : 'ghost'}
          onClick={() => setPainelAberto(a => !a)}
          title="Banco de preço ao lado, para arrastar itens direto para a planilha"
        ><PanelRight size={13} /></Btn>
      )}
      {/* O botão diz "Base" primeiro porque é o que alguém vem procurar quando
          a planilha entrou zerada — e era justamente o que não existia. */}
      {podeEditar && <Btn tam="sm" onClick={() => setAjustandoTaxas(true)}><Percent size={13} />Base, BDI e encargos</Btn>}
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
      {/* Ao lado de Revisar, e depois dele: revisar continua sendo o caminho
          quando o escopo muda — ele versiona, e é o que a obra pública exige.
          Destravar é para o erro achado logo depois de aprovar. */}
      {orcamento.status === 'aprovado' && podeDestravar && (
        <Btn tam="sm" onClick={() => setDestravando(true)} title="Reabrir para edição, com motivo registrado">
          <Unlock size={13} />Destravar
        </Btn>
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
            <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
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
              selecao={selecao}
              afetados={escopo.descendentes}
              onSelecionar={selecionar}
              onExcluirSelecao={podeEditar ? excluirSelecao : undefined}
              onAcaoRapida={acaoRapida}
              onMover={podeEditar ? moverBloco : undefined}
              onOperacao={podeEditar ? operacaoDeBloco : undefined}
              onEditarInsumo={podeEditar ? mexerNoInsumo : undefined}
              onNovoInsumo={podeEditar ? setInsumoNovoDe : undefined}
              onRemoverInsumo={podeEditar ? tirarInsumo : undefined}
              onEditar={editarLinha}
              onColar={(edicoes: EdicaoCelula[]) => {
                for (const e of edicoes) {
                  editarCelula.mutate({ id: e.item.item_orcado_id, payload: { [e.coluna]: e.valor } as Partial<ItemOrcado> })
                }
                setRecado(`${edicoes.length} célula(s) coladas do Excel.`)
              }}
              onAbrirLinha={item => setMemoriaDe(item)}
              onMenu={(item, ancora) => setMenu({ item, x: ancora.left - 210, y: ancora.bottom + 4 })}
              arrastandoDeFora={doBanco !== null}
              onSoltarDeFora={soltarDoBanco}
            />
            </div>
            {painelAberto && podeEditar && (
              <PainelDeBanco
                baseDoOrcamento={orcamento.base_referencial ?? null}
                onArrastar={setDoBanco}
                onSoltarFora={() => setDoBanco(null)}
                onFechar={() => setPainelAberto(false)}
              />
            )}
            </div>
          )}

          {/* **A barra só existe quando há seleção.** Uma barra permanente com
              botões cinzas ocuparia altura da grade o tempo todo para dizer "não
              dá" — e a grade é o módulo. Aparecendo com a seleção, ela também
              serve de recibo de que o clique pegou. */}
          {podeEditar && marcados.length > 0 && (
            <BarraDeLote
              quantidade={marcados.length}
              vaoJunto={escopo.descendentes.size}
              ocupado={
                moverItens.isPending || duplicarItens.isPending || excluirItens.isPending
                || aplicarPercentual.isPending || arredondarItens.isPending
              }
              onLimpar={() => setSelecao(new Set())}
              onOperacao={op => operacaoDeBloco(op, marcados)}
              onDuplicar={duplicarSelecao}
              onExcluir={excluirSelecao}
              onPercentual={percentualNaSelecao}
              onArredondar={arredondarSelecao}
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
              rotulo: 'Duplicar linha', icone: <CopyIcon size={13} />, off: !podeEditar,
              acao: async () => {
                if (!orcamentoId) return
                const r = await duplicarItens.mutateAsync({
                  orcamento: orcamentoId, itens: [menu.item.item_orcado_id],
                })
                setRecado(`${r.criadas} linha(s) duplicada(s).`)
              },
            },
            {
              rotulo: menu.item.preco_travado ? 'Destravar preço' : 'Travar preço',
              icone: menu.item.preco_travado ? <Unlock size={13} /> : <Lock size={13} />,
              off: !podeEditar || menu.item.tipo_linha === 'sintetico',
              acao: () => {
                editarCelula.mutate({
                  id: menu.item.item_orcado_id,
                  payload: { preco_travado: !menu.item.preco_travado } as Partial<ItemOrcado>,
                })
                setRecado(menu.item.preco_travado
                  ? 'Preço destravado — volta a entrar em reprecificação e lote.'
                  : 'Preço travado — reprecificação e lote não encostam nesta linha.')
              },
            },
            {
              rotulo: 'Descrição detalhada', icone: <FileSpreadsheet size={13} />, off: !podeEditar,
              acao: () => setTextoLongoDe(menu.item),
            },
            {
              rotulo: 'Salvar composição no banco', icone: <Library size={13} />,
              off: !podePromover,
              acao: async () => {
                try {
                  const r = await promoverComposicao.mutateAsync({ item: menu.item.item_orcado_id })
                  setRecado(`Composição gravada em "${r.banco_nome}" com o código ${r.codigo}.`)
                } catch (e) {
                  aoFalhar(e, 'Não foi possível gravar a composição no banco.')
                }
              },
            },
            {
              // **Mesmo caminho do lote**, e não o `removerItem` de antes: aquele
              // apagava na hora, sem perguntar e **sem entrar na pilha do
              // Ctrl+Z** — o caminho mais usado era o único irrecuperável. Uma
              // linha ou cinquenta, o gesto é o mesmo e a promessa também.
              rotulo: 'Excluir linha', icone: <Trash2 size={13} />, perigo: true, off: !podeEditar,
              acao: () => pedirExclusao(
                selecao.has(menu.item.item_orcado_id) ? marcados : [menu.item.item_orcado_id],
              ),
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
          baseDoOrcamento={orcamento?.base_referencial ?? null}
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
          titulo="Base de preço, BDI e encargos"
          onClose={() => setAjustandoTaxas(false)}
          rodape={<Btn onClick={() => setAjustandoTaxas(false)}>Fechar</Btn>}
        >
          <FormTaxas
            bdi={orcamento.bdi_percentual}
            encargos={orcamento.encargos_sociais_percentual}
            regime={orcamento.regime_encargos}
            base={orcamento.base_referencial}
            bases={bases ?? []}
            temLinhas={(arvore?.itens.length ?? 0) > 0}
            salvando={atualizarOrcamento.isPending}
            onSalvar={async dados => {
              await atualizarOrcamento.mutateAsync({ id: orcamento.orcamento_id, payload: dados as Partial<typeof orcamento> })
              await recalcular.mutateAsync(orcamento.orcamento_id)
              setAjustandoTaxas(false)
              setRecado(
                dados.base_referencial !== orcamento.base_referencial
                  ? 'Base de preço trocada — os próximos itens virão dela. Use Reprecificar para atualizar as linhas que já estão na planilha.'
                  : 'Taxas atualizadas e planilha recalculada.',
              )
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

      {aExcluir && arvore && (
        <ModalExcluir
          ids={aExcluir}
          itens={arvore.itens}
          salvando={excluirItens.isPending}
          onFechar={() => setAExcluir(null)}
          onConfirmar={async () => {
            const ids = aExcluir
            setAExcluir(null)
            await excluirAgora(ids)
          }}
        />
      )}

      {substituindo && orcamento && (
        <ModalSubstituir
          escopo={marcados.length}
          salvando={substituirTexto.isPending}
          onFechar={() => setSubstituindo(false)}
          onSubstituir={async (procurar, trocarPor, soNaSelecao) => {
            const r = await substituirTexto.mutateAsync({
              orcamento: orcamento.orcamento_id, procurar, trocar_por: trocarPor,
              itens: soNaSelecao && marcados.length ? marcados : null,
            })
            setSubstituindo(false)
            setRecado(`${r.afetadas} descrição(ões) alterada(s).`)
          }}
        />
      )}

      {destravando && orcamento && (
        <ModalDestravar
          salvando={destravarOrcamento.isPending}
          onFechar={() => setDestravando(false)}
          onDestravar={async motivo => {
            await destravarOrcamento.mutateAsync({ id: orcamento.orcamento_id, motivo })
            setDestravando(false)
            setRecado('Planilha reaberta em rascunho — o motivo ficou registrado nela.')
          }}
        />
      )}

      {insumoNovoDe && orcamento && (
        <ModalNovoInsumo
          linha={insumoNovoDe}
          salvando={criarInsumo.isPending}
          onFechar={() => setInsumoNovoDe(null)}
          onCriar={async dados => {
            await criarInsumo.mutateAsync({ ...dados, item_orcado: insumoNovoDe.item_orcado_id })
            setInsumoNovoDe(null)
            setRecado('Insumo somado — o custo unitário foi refeito pela composição.')
          }}
        />
      )}

      {textoLongoDe && (
        <ModalTextoLongo
          linha={textoLongoDe}
          salvando={editarCelula.isPending}
          onFechar={() => setTextoLongoDe(null)}
          onSalvar={async texto => {
            await editarCelula.mutateAsync({
              id: textoLongoDe.item_orcado_id,
              payload: { texto_longo: texto } as Partial<ItemOrcado>,
            })
            setTextoLongoDe(null)
            setRecado('Descrição detalhada salva — ela vai junto nas peças exportadas.')
          }}
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
  // Resumo inteiro, e não `{base_id, rotulo}`: o seletor encadeado escolhe por
  // fonte, UF, mês e regime — eixos que o rótulo pronto não devolve.
  bases: BaseResumo[]
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
            <SeletorDeBase
              bases={bases}
              valor={baseDestino === '' ? '' : Number(baseDestino)}
              onChange={v => setBaseDestino(v === '' ? '' : String(v))}
              rotuloVazio="Selecione"
              style={{ width: '100%' }}
            />
          </Field>
          <Field label="Só linhas com preço até (data de corte)" dica="Opcional. Linha com preço mais novo que isto não é tocada — preserva o que já foi renegociado à mão.">
            <input type="date" min={minCalendarioISO} max={maxCalendarioISO} value={somenteAte} onChange={e => setSomenteAte(e.target.value)} style={{ ...inp, ...mono }} />
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

function FormTaxas({ bdi, encargos, regime, base, bases, temLinhas, salvando, onSalvar }: {
  bdi: string; encargos: string; regime: string; salvando: boolean
  base: number | null
  bases: BaseResumo[]
  /** Muda o texto do aviso: planilha vazia não tem preço velho para conviver
   *  com o novo, e prometer "use Reprecificar" ali seria recado sem serventia. */
  temLinhas: boolean
  onSalvar: (dados: {
    bdi_percentual: string; encargos_sociais_percentual: string; regime_encargos: string
    base_referencial: number | null
  }) => void
}) {
  const [form, setForm] = useState({ bdi, encargos, regime, base })
  const trocouBase = form.base !== base
  return (
    <>
      {/* **A base é editável depois, e é aqui que ela mora.** Antes só dava
          para escolher publicação na criação do orçamento — e quem deixasse o
          padrão "Sem base — preço digitado à mão" ficava sem saída: todo item
          entrava a zero e o único jeito de consertar era descobrir, por acaso,
          que Reprecificar grava uma base. */}
      <Field
        label="Base de preço"
        dica="De onde o preço dos PRÓXIMOS itens será copiado. A data-base do orçamento acompanha a publicação escolhida."
      >
        <SeletorDeBase
          bases={bases}
          valor={form.base ?? ''}
          onChange={v => setForm(f => {
            // O regime acompanha a publicação escolhida — senão o orçamento
            // ficaria dizendo "onerado" apoiado numa base desonerada, que é o
            // mesmo custo contado de dois jeitos. Continua editável logo
            // abaixo: quem tem motivo para divergir, diverge à vista.
            const escolhida = bases.find(b => b.base_id === v)
            return { ...f, base: v === '' ? null : v, regime: escolhida?.regime_encargos ?? f.regime }
          })}
          rotuloVazio="Sem base — preço digitado à mão"
          style={{ width: '100%' }}
        />
      </Field>
      {trocouBase && (
        <Aviso tom="amber">
          <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
          <span>
            {temLinhas
              ? <>As linhas que já estão na planilha <b>mantêm o preço atual</b> — trocar a base muda de
                  onde vêm os <b>próximos</b> itens. Para atualizar as existentes use <b>Reprecificar</b>,
                  que mostra prévia e permite desfazer.</>
              : <>A planilha está vazia, então é só escolher: os itens que você inserir já virão com
                  preço desta publicação.</>}
          </span>
        </Aviso>
      )}
      <Field label="BDI (%)" dica="Percentual resultante que multiplica cada linha analítica. A composição analítica do Acórdão 2622/2013-TCU fica na aba de BDI.">
        <input value={form.bdi} onChange={e => setForm(f => ({ ...f, bdi: e.target.value }))} style={{ ...inp, ...mono }} />
      </Field>
      <Field label="Encargos sociais (%)" dica="Incide só sobre mão de obra na explosão da composição.">
        <input value={form.encargos} onChange={e => setForm(f => ({ ...f, encargos: e.target.value }))} style={{ ...inp, ...mono }} />
      </Field>
      <Field label="Regime">
        <Select value={form.regime} onChange={e => setForm(f => ({ ...f, regime: e.target.value }))} style={{ width: '100%', maxWidth: 'none' }}>
          <option value="onerado">Onerado (não desonerado)</option>
          <option value="desonerado">Desonerado</option>
          {/* Faltava, e a SINAPI publica: é o preço **sem encargos sociais**,
              sobre o qual se aplica o quadro analítico do ORC.7. Sem esta
              opção, um orçamento apoiado numa publicação "sem" não conseguia
              declarar o próprio regime. */}
          <option value="sem">Sem encargos</option>
          <option value="na">Não se aplica</option>
        </Select>
      </Field>
      <Btn variant="primary" disabled={salvando} onClick={() => onSalvar({
        bdi_percentual: paraDecimal(form.bdi),
        encargos_sociais_percentual: paraDecimal(form.encargos),
        regime_encargos: form.regime,
        base_referencial: form.base,
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


/** A barra que aparece com a seleção — ORC.10d.
 *
 *  **Por que ela existe, e não só o menu da linha.** O menu age sobre uma linha;
 *  o que falta na planilha é agir sobre um trecho: mover dez serviços para outra
 *  etapa, tirar 3% de um capítulo inteiro, apagar um bloco importado errado. É
 *  o gesto que separa uma grade de um formulário, e é o que o Arquimedes e o
 *  Volare oferecem numa barra igual a esta.
 *
 *  **Por que ela some.** Barra permanente com botões cinzas ocuparia altura da
 *  grade o tempo todo para dizer "não dá" — e a grade é o módulo (§8 da planta).
 *  Aparecendo com a seleção, ela também é o recibo de que o clique pegou.
 */
function BarraDeLote({
  quantidade, vaoJunto, ocupado, onLimpar, onOperacao, onDuplicar, onExcluir, onPercentual,
  onArredondar,
}: {
  quantidade: number
  /** Descendentes que acompanham a seleção sem estarem marcados. A barra diz o
   *  número porque era justamente ele que sumia: "1 linha selecionada" com doze
   *  saindo é a conta que faz alguém perder um capítulo inteiro. */
  vaoJunto: number
  ocupado: boolean
  onLimpar: () => void
  onOperacao: (operacao: OperacaoDeBloco) => void
  onDuplicar: () => void
  onExcluir: () => void
  onPercentual: (percentual: string, campo: 'custo_unitario' | 'quantidade') => void
  onArredondar: (casas: number, campo: 'custo_unitario' | 'quantidade') => void
}) {
  const [percentual, setPercentual] = useState('')
  const [campo, setCampo] = useState<'custo_unitario' | 'quantidade'>('custo_unitario')

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', flex: 'none',
      padding: '7px 16px', background: 'var(--accent-soft)',
      borderTop: '1px solid var(--accent)', fontSize: 12,
    }}>
      <span style={{ ...CAPS, color: 'var(--accent-ink)' }}>
        {quantidade} linha(s) selecionada(s)
        {vaoJunto > 0 && ` · ${vaoJunto} vão junto`}
      </span>

      <span style={{ width: 1, height: 18, background: 'var(--line)' }} />

      <Btn tam="sm" disabled={ocupado} title="Subir (Alt+↑)" onClick={() => onOperacao('cima')}>
        <ArrowUp size={13} />
      </Btn>
      <Btn tam="sm" disabled={ocupado} title="Descer (Alt+↓)" onClick={() => onOperacao('baixo')}>
        <ArrowDown size={13} />
      </Btn>
      <Btn tam="sm" disabled={ocupado} title="Indentar — pendurar na linha de cima (Alt+→)" onClick={() => onOperacao('indentar')}>
        <Indent size={13} />
      </Btn>
      <Btn tam="sm" disabled={ocupado} title="Desindentar — subir um nível (Alt+←)" onClick={() => onOperacao('desindentar')}>
        <Outdent size={13} />
      </Btn>

      <span style={{ width: 1, height: 18, background: 'var(--line)' }} />

      <Btn tam="sm" disabled={ocupado} onClick={onDuplicar}><CopyIcon size={13} />Duplicar</Btn>

      <span style={{ width: 1, height: 18, background: 'var(--line)' }} />

      <Select
        value={campo}
        onChange={e => setCampo(e.target.value as 'custo_unitario' | 'quantidade')}
        style={{ maxWidth: 130, fontSize: 12 }}
      >
        <option value="custo_unitario">Custo unit.</option>
        <option value="quantidade">Quantidade</option>
      </Select>
      <input
        value={percentual}
        onChange={e => setPercentual(e.target.value)}
        onKeyDown={e => {
          if (e.key !== 'Enter' || !percentual.trim()) return
          onPercentual(paraDecimal(percentual), campo)
          setPercentual('')
        }}
        placeholder="±%"
        title="Percentual sobre a seleção. Negativo desconta. Enter aplica."
        style={{ ...inp, ...mono, width: 78, padding: '5px 8px', fontSize: 12 }}
      />
      <Btn
        tam="sm"
        disabled={ocupado || !percentual.trim()}
        onClick={() => { onPercentual(paraDecimal(percentual), campo); setPercentual('') }}
      ><Percent size={13} />Aplicar</Btn>
      <Btn
        tam="sm"
        disabled={ocupado}
        title="Arredondar para 2 casas. Não há desfazer — a casa descartada se perde."
        onClick={() => onArredondar(2, campo)}
      ><Sigma size={13} />Arredondar</Btn>

      <div style={{ flex: 1 }} />

      <Btn tam="sm" variant="perigo" disabled={ocupado} onClick={onExcluir}>
        <Trash2 size={13} />Excluir
      </Btn>
      <Btn tam="sm" onClick={onLimpar} title="Limpar seleção"><X size={13} /></Btn>
    </div>
  )
}

/** Localizar e substituir — ORC.10f.
 *
 *  Só na **descrição**, e o texto do diálogo diz isso. Substituição cega em
 *  campo numérico ou em código de referência é o tipo de conveniência que
 *  corrompe uma planilha inteira em um clique, e o Ctrl+Z da grade não alcança
 *  mil linhas gravadas de uma vez.
 */
function ModalSubstituir({ escopo, salvando, onFechar, onSubstituir }: {
  /** Quantas linhas estão marcadas — zero esconde a opção de limitar à seleção. */
  escopo: number
  salvando: boolean
  onFechar: () => void
  onSubstituir: (procurar: string, trocarPor: string, soNaSelecao: boolean) => Promise<void>
}) {
  const [procurar, setProcurar] = useState('')
  const [trocarPor, setTrocarPor] = useState('')
  const [soNaSelecao, setSoNaSelecao] = useState(escopo > 0)
  const [erro, setErro] = useState('')

  return (
    <Modal
      titulo="Localizar e substituir"
      onClose={onFechar}
      rodape={
        <>
          <Btn onClick={onFechar}>Cancelar</Btn>
          <Btn
            variant="primary"
            disabled={salvando || !procurar.trim()}
            onClick={async () => {
              setErro('')
              try {
                await onSubstituir(procurar, trocarPor, soNaSelecao)
              } catch {
                setErro('Não foi possível substituir.')
              }
            }}
          >Substituir</Btn>
        </>
      }
    >
      {erro && <Aviso tom="danger">{erro}</Aviso>}
      <Aviso tom="amber">
        <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
        Age só na <b>descrição</b> das linhas, e <b>não entra no Ctrl+Z</b> — uma substituição pode
        tocar centenas de linhas de uma vez. Confira o texto antes.
      </Aviso>
      <div style={{ height: 14 }} />
      <Field label="Procurar">
        <input autoFocus value={procurar} onChange={e => setProcurar(e.target.value)} style={inp} />
      </Field>
      <Field label="Trocar por" dica="Vazio apaga o trecho encontrado.">
        <input value={trocarPor} onChange={e => setTrocarPor(e.target.value)} style={inp} />
      </Field>
      {escopo > 0 && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12.5, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={soNaSelecao}
            onChange={e => setSoNaSelecao(e.target.checked)}
            style={{ accentColor: 'var(--accent)' }}
          />
          Só nas {escopo} linha(s) selecionada(s)
        </label>
      )}
    </Modal>
  )
}

/** Reabrir a planilha aprovada — ORC.10e. */
function ModalDestravar({ salvando, onFechar, onDestravar }: {
  salvando: boolean
  onFechar: () => void
  onDestravar: (motivo: string) => Promise<void>
}) {
  const [motivo, setMotivo] = useState('')
  const [erro, setErro] = useState('')

  return (
    <Modal
      titulo="Destravar a planilha aprovada"
      onClose={onFechar}
      rodape={
        <>
          <Btn onClick={onFechar}>Cancelar</Btn>
          <Btn
            variant="primary"
            disabled={salvando || !motivo.trim()}
            onClick={async () => {
              setErro('')
              try {
                await onDestravar(motivo.trim())
              } catch {
                setErro('Não foi possível destravar.')
              }
            }}
          >Destravar em rascunho</Btn>
        </>
      }
    >
      {erro && <Aviso tom="danger">{erro}</Aviso>}
      <Aviso tom="amber">
        <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
        <span>
          Destravar <b>não cria versão</b>. Se o escopo mudou — aditivo, supressão, reequilíbrio —,
          o caminho é <b>Revisar</b>, que versiona e deixa o par de valores registrado. Use isto
          para o erro achado logo depois de aprovar.
        </span>
      </Aviso>
      <div style={{ height: 14 }} />
      <Field label="Motivo" dica="Fica registrado na planilha e acompanha as peças exportadas.">
        <textarea
          autoFocus
          value={motivo}
          onChange={e => setMotivo(e.target.value)}
          rows={3}
          placeholder="Ex.: quantidade da placa de obra digitada com uma casa a mais."
          style={{ ...inp, resize: 'vertical', fontFamily: 'var(--sans)' }}
        />
      </Field>
    </Modal>
  )
}

/** Somar um insumo à composição da linha — ORC.10c. */
function ModalNovoInsumo({ linha, salvando, onFechar, onCriar }: {
  linha: ItemOrcado
  salvando: boolean
  onFechar: () => void
  onCriar: (dados: {
    descricao: string; unidade: string; categoria: CategoriaInsumo
    coeficiente: string; custo_unitario: string
  }) => Promise<void>
}) {
  const [form, setForm] = useState({
    descricao: '', unidade: '', categoria: 'material' as CategoriaInsumo,
    coeficiente: '1', custo_unitario: '',
  })
  const [erro, setErro] = useState('')

  return (
    <Modal
      titulo={`Somar insumo — ${linha.descricao}`}
      onClose={onFechar}
      rodape={
        <>
          <Btn onClick={onFechar}>Cancelar</Btn>
          <Btn
            variant="primary"
            disabled={salvando}
            onClick={async () => {
              if (!form.descricao.trim() || !form.unidade.trim()) {
                setErro('Descrição e unidade são obrigatórias.')
                return
              }
              setErro('')
              try {
                await onCriar({
                  descricao: form.descricao.trim(),
                  unidade: form.unidade.trim(),
                  categoria: form.categoria,
                  coeficiente: paraDecimal(form.coeficiente),
                  custo_unitario: paraDecimal(form.custo_unitario || '0'),
                })
              } catch {
                setErro('Não foi possível somar o insumo.')
              }
            }}
          >Somar à composição</Btn>
        </>
      }
    >
      {erro && <Aviso tom="danger">{erro}</Aviso>}
      <Aviso>
        <GitBranch size={15} style={{ flex: 'none', marginTop: 1 }} />
        <span>
          O custo unitário da linha passa a ser a <b>soma da composição</b>. Insumo de mão de obra
          recebe os encargos sociais do orçamento por cima — é o servidor que aplica, para a soma
          da composição e o preço da linha não divergirem.
        </span>
      </Aviso>
      <div style={{ height: 14 }} />
      <Field label="Descrição">
        <input
          autoFocus
          value={form.descricao}
          onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))}
          placeholder="Ex.: Pedreiro com encargos complementares"
          style={inp}
        />
      </Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Field label="Unidade">
          <input
            value={form.unidade}
            onChange={e => setForm(f => ({ ...f, unidade: e.target.value }))}
            placeholder="H, M2, KG…"
            style={inp}
          />
        </Field>
        <Field label="Natureza" dica="Só mão de obra recebe encargo social.">
          <Select
            value={form.categoria}
            onChange={e => setForm(f => ({ ...f, categoria: e.target.value as CategoriaInsumo }))}
            style={{ width: '100%', maxWidth: 'none' }}
          >
            <option value="material">Material</option>
            <option value="mao_de_obra">Mão de obra</option>
            <option value="equipamento">Equipamento</option>
            <option value="encargos_complementares">Encargos complementares</option>
            <option value="outro">Outro</option>
          </Select>
        </Field>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <Field label="Coeficiente" dica={`Consumo por ${linha.unidade || 'unidade'} do serviço.`}>
          <input
            value={form.coeficiente}
            onChange={e => setForm(f => ({ ...f, coeficiente: e.target.value }))}
            style={{ ...inp, ...mono }}
          />
        </Field>
        <Field label="Custo unitário do insumo">
          <input
            value={form.custo_unitario}
            onChange={e => setForm(f => ({ ...f, custo_unitario: e.target.value }))}
            placeholder="0,00"
            style={{ ...inp, ...mono }}
          />
        </Field>
      </div>
    </Modal>
  )
}

/** A especificação do serviço — o "pliego" do Arquimedes (ORC.10e). */
function ModalTextoLongo({ linha, salvando, onFechar, onSalvar }: {
  linha: ItemOrcado
  salvando: boolean
  onFechar: () => void
  onSalvar: (texto: string) => Promise<void>
}) {
  const [texto, setTexto] = useState(linha.texto_longo ?? '')

  return (
    <Modal
      titulo={`Descrição detalhada — ${linha.codigo_eap}`}
      largura={680}
      onClose={onFechar}
      rodape={
        <>
          <Btn onClick={onFechar}>Cancelar</Btn>
          <Btn variant="primary" disabled={salvando} onClick={() => onSalvar(texto)}>Salvar</Btn>
        </>
      }
    >
      <Aviso>
        <FileSpreadsheet size={15} style={{ flex: 'none', marginTop: 1 }} />
        A especificação que acompanha o serviço na peça — material, norma, acabamento, critério de
        medição. A <b>Observação</b> da linha continua sendo o bilhete curto; isto é documento.
      </Aviso>
      <div style={{ height: 14 }} />
      <div style={{ fontSize: 12.5, color: 'var(--ink-3)', marginBottom: 8 }}>{linha.descricao}</div>
      <textarea
        autoFocus
        value={texto}
        onChange={e => setTexto(e.target.value)}
        rows={14}
        style={{ ...inp, resize: 'vertical', fontFamily: 'var(--sans)', lineHeight: 1.5 }}
      />
    </Modal>
  )
}


/** Confirmar a exclusão — ORC.10d, revisto.
 *
 *  **Por que ele existe.** Excluir era imediato: marcar uma etapa e apertar o
 *  botão tirava a etapa e tudo que pendia dela, sem uma palavra. Em planilha
 *  recolhida isso é pior ainda — os doze serviços que somem não estavam nem à
 *  vista. O Ctrl+Z cobria o engano, mas contar com o desfazer para tornar
 *  aceitável um gesto destrutivo é trocar a ordem das coisas: primeiro se
 *  entende o que vai acontecer, depois se tem como voltar.
 *
 *  **O que ele mostra, e por quê.** Três números que respondem às três
 *  perguntas de quem está com o dedo no botão: *quantas linhas eu escolhi*,
 *  *quantas vêm junto sem eu ter escolhido* e *quanto sai do total*. O valor é
 *  somado só nas **raízes** da seleção — somar raiz e descendente contaria o
 *  mesmo dinheiro duas vezes, pela mesma razão que o recálculo da planilha soma
 *  só as raízes. E a lista nomeia as primeiras: número sem nome não deixa
 *  ninguém reconhecer que marcou a etapa errada.
 */
function ModalExcluir({ ids, itens, salvando, onFechar, onConfirmar }: {
  ids: number[]
  itens: ItemOrcado[]
  salvando: boolean
  onFechar: () => void
  onConfirmar: () => void | Promise<void>
}) {
  const escolhidos = new Set(ids)

  const { raizes, descendentes, valor } = useMemo(() => {
    const filhosDe = new Map<number | null, number[]>()
    for (const i of itens) {
      const lista = filhosDe.get(i.pai)
      if (lista) lista.push(i.item_orcado_id)
      else filhosDe.set(i.pai, [i.item_orcado_id])
    }
    const abaixo = new Set<number>()
    const pilha = [...escolhidos]
    while (pilha.length) {
      const atual = pilha.pop() as number
      for (const filho of filhosDe.get(atual) ?? []) {
        if (abaixo.has(filho)) continue
        abaixo.add(filho)
        pilha.push(filho)
      }
    }
    const topo = itens.filter(i => escolhidos.has(i.item_orcado_id) && !abaixo.has(i.item_orcado_id))
    for (const id of escolhidos) abaixo.delete(id)
    return {
      raizes: topo,
      descendentes: abaixo,
      valor: topo.reduce((soma, i) => soma + Number(i.total_com_bdi || 0), 0),
    }
  }, [itens, ids]) // eslint-disable-line react-hooks/exhaustive-deps

  const total = raizes.length + descendentes.size
  const MOSTRA = 8

  return (
    <Modal
      titulo={total === 1 ? 'Excluir esta linha?' : `Excluir ${total} linhas?`}
      onClose={onFechar}
      rodape={
        <>
          <Btn onClick={onFechar}>Cancelar</Btn>
          <Btn variant="perigo" disabled={salvando} onClick={onConfirmar}>
            <Trash2 size={14} />
            {total === 1 ? 'Excluir a linha' : `Excluir as ${total} linhas`}
          </Btn>
        </>
      }
    >
      {descendentes.size > 0 && (
        <Aviso tom="amber">
          <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
          <span>
            <b>{descendentes.size} linha(s) vão junto</b> por pendurarem no que você marcou
            {' '}— inclusive o que estiver recolhido e fora da vista. Excluir uma etapa sem o
            conteúdo dela não seria excluir, seria desmontar.
          </span>
        </Aviso>
      )}

      <div style={{ height: descendentes.size > 0 ? 14 : 0 }} />

      <div style={{
        display: 'flex', gap: 22, flexWrap: 'wrap', padding: '10px 12px',
        background: 'var(--inset)', borderRadius: 'var(--r-sm)', marginBottom: 14,
      }}>
        <span style={{ ...CAPS }}>
          Marcadas <b style={{ ...mono, fontSize: 14, color: 'var(--ink)', marginLeft: 6 }}>{raizes.length}</b>
        </span>
        <span style={{ ...CAPS }}>
          Vão junto <b style={{ ...mono, fontSize: 14, color: 'var(--ink)', marginLeft: 6 }}>{descendentes.size}</b>
        </span>
        <div style={{ flex: 1 }} />
        <span style={{ ...CAPS }}>
          Sai do total
          <b style={{ ...mono, fontSize: 14, color: 'var(--danger-ink)', marginLeft: 6 }}>{brl(valor)}</b>
        </span>
      </div>

      <div style={{ ...CAPS, marginBottom: 6 }}>O que você marcou</div>
      <div style={{
        maxHeight: 220, overflowY: 'auto', border: '1px solid var(--line)',
        borderRadius: 'var(--r-sm)',
      }}>
        {raizes.slice(0, MOSTRA).map(i => (
          <div
            key={i.item_orcado_id}
            style={{
              display: 'flex', alignItems: 'center', gap: 9, padding: '6px 10px',
              borderBottom: '1px solid var(--line-2)', fontSize: 12.5,
            }}
          >
            <span style={{ ...mono, fontSize: 11, color: 'var(--ink-3)', flex: 'none', minWidth: 52 }}>
              {i.codigo_eap}
            </span>
            <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {i.descricao}
            </span>
            {i.tipo_linha === 'sintetico' && (
              <span style={{
                ...CAPS, fontSize: 8.5, padding: '1px 5px', borderRadius: 3, flex: 'none',
                background: 'var(--accent-soft)', color: 'var(--accent-ink)',
              }}>etapa</span>
            )}
            <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-2)', flex: 'none' }}>
              {brl(i.total_com_bdi)}
            </span>
          </div>
        ))}
        {raizes.length > MOSTRA && (
          <div style={{ padding: '6px 10px', fontSize: 12, color: 'var(--ink-3)' }}>
            e mais {raizes.length - MOSTRA} linha(s).
          </div>
        )}
      </div>

      <div style={{ marginTop: 12, fontSize: 12, color: 'var(--ink-3)' }}>
        Dá para voltar com <b>Ctrl+Z</b> enquanto esta planilha estiver aberta. As linhas
        restauradas voltam com a mesma forma e os mesmos valores, mas com <b>identificadores
        novos</b> — o banco não reaproveita chave.
      </div>
    </Modal>
  )
}
