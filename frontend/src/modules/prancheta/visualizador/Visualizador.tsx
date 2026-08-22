import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import {
  AlertTriangle, Clock3, Download, ExternalLink, Globe2, Hash, Layers, Lock, Map as MapIcon,
  MessageSquare, ServerCrash, Timer, X,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { Btn, Pill, Spinner } from '@/components/malha'
import { anexarPontoDeVista, baixarParaDisco, priorizarNaFila } from '../api'
import {
  useArquivoBlob,
  useCalibrar,
  useComentar,
  useCriarMarcacao,
  useCriarMedicao,
  useImportarBcf,
  useMarcacoes,
  useMedicoes,
  useMudarSituacao,
  useRenomearDesenho,
} from '../hooks'
import { PresencaChip } from '../cartao'
import type { Conversao, Desenho, Documento, Ponto, RevisaoResumo } from '../types'
import { usePapel } from '../visao'
import { Camada } from './Camada'
import { Minimapa } from './Minimapa'
import { BarraDeModos, DialogoCalibrar, DialogoNovaMarcacao, PainelMarcacoes } from './Marcacoes'
import { GavetaDeRevisoes } from './Revisoes'
import { capturarRecorte, MINIMO_DE_PONTOS } from './marcar'
import type { Modo } from './marcar'
import { carregarSnap, IndiceDeSnap } from './snap'
import type { Achado } from './snap'
import { Vista2D } from './Vista2D'

/** O 3D só é baixado por quem abre um modelo — ver o cabeçalho de `Vista3D`. */
const Vista3D = lazy(() => import('./Vista3D').then((m) => ({ default: m.Vista3D })))

/**
 * A tela do canteiro: uma prancha, inteira, sem mais nada em volta.
 *
 * É sobreposição de tela cheia e não um painel na página porque o gesto que
 * importa aqui é **olhar o desenho** — no celular, qualquer coluna ao lado rouba
 * a metade útil da tela. Fecha no `Esc` e no botão, como o `Modal` da Malha.
 *
 * O que ela desenha é decidido pelo `conversao` que o backend já resolveu
 * (`estado`, `tipo` e `nativo`): a tela não repete a tabela de formatos, e um
 * formato novo no `formatos.py` aparece aqui sem tocar neste arquivo.
 */
export function Visualizador({
  documento,
  revisao,
  onFechar,
  onReprocessar,
  podeReprocessar,
  say,
}: {
  documento: Documento
  revisao: RevisaoResumo
  onFechar: () => void
  onReprocessar?: () => void
  podeReprocessar?: boolean
  /** O aviso da página — publicar e atualizar arquivo acontecem aqui dentro agora. */
  say: (m: string) => void
}) {
  const { conversao } = revisao
  const papel = usePapel()

  // --- PRA.1c: qual folha está aberta ---------------------------------------
  // A revisão pode trazer várias. `ordem` e não índice porque é ela que sobrevive
  // a uma reconversão — o índice do array mudaria se uma folha vazia deixasse de
  // ser emitida, e a pessoa voltaria para outro desenho.
  const folhas = revisao.desenhos ?? []
  const [ordemAberta, setOrdemAberta] = useState(1)
  const desenhoAberto = folhas.find((d) => d.ordem === ordemAberta) ?? folhas[0] ?? null
  // Trocar de prancha volta ao primeiro desenho: manter a ordem anterior abriria
  // "Desenho 3" de um arquivo que tem dois.
  useEffect(() => { setOrdemAberta(1) }, [revisao.revisao_id])

  // A folha manda quando existe; `conversao.visualizador` continua respondendo
  // por PDF, imagem e 3D, que não têm folha separável.
  const fonte = desenhoAberto?.visualizador ?? conversao.visualizador
  const { objeto, erro, carregando } = useArquivoBlob(fonte)

  // A régua é a da folha aberta, com o campo de compatibilidade da revisão como
  // reserva para quem ainda não tem desenho (revisão convertida antes desta
  // fatia, e o PDF).
  const escalaValor = desenhoAberto?.escala_valor ?? revisao.escala_valor ?? null
  const escalaUnidade = desenhoAberto?.escala_unidade || revisao.escala_unidade || 'm'
  const escalaOrigem = desenhoAberto?.escala_origem ?? revisao.escala_origem ?? ''

  // --- PRA.3: marcar e medir ------------------------------------------------
  const [modo, setModo] = useState<Modo>('navegar')
  const [emCurso, setEmCurso] = useState<Ponto[]>([])
  const [ancoraPendente, setAncoraPendente] = useState<Ponto | null>(null)
  const [calibrando, setCalibrando] = useState(false)
  const [painelAberto, setPainelAberto] = useState(false)
  const [selecionada, setSelecionada] = useState<number | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)

  // --- PRA.10: o snap de medição ---------------------------------------------
  // O índice vive em `ref` e não em estado: ele muda a cada movimento do
  // ponteiro e re-renderizar a árvore inteira a 60 Hz por causa disso travaria
  // a prancha justamente enquanto se mede. Só a MIRA é estado, porque só ela
  // aparece na tela.
  const indiceSnap = useRef<IndiceDeSnap | null>(null)
  const [mira, setMira] = useState<Achado | null>(null)
  const [snapParcial, setSnapParcial] = useState(false)
  /**
   * **O snap desligável** (pedido do dono, 16/08/2026).
   *
   * Ligado é o padrão porque é ele que faz a cota valer: sem mira, o ponto
   * gravado é o do dedo, e numa folha onde 1 px vale 4 cm isso é medida errada
   * com cara de medida conferida. Mas grudar é atrapalhar quando o que se quer é
   * apontar um lugar **sem** vértice — o meio de um vão, um ponto no terreno —,
   * e aí a ajuda vira teimosia. É a mesma régua do minimapa e da ressalva do
   * D46: ferramenta que não se desliga vira estorvo no dia seguinte.
   */
  const [snapLigado, setSnapLigado] = useState(true)

  const snapUrl = desenhoAberto?.snap?.url ?? null
  useEffect(() => {
    // Trocar de folha troca de geometria. Zerar ANTES de buscar é o que impede
    // a mira de grudar, por um instante, no traço da folha anterior.
    indiceSnap.current = null
    setMira(null)
    setSnapParcial(false)
    if (!snapUrl) return

    let vigente = true
    void carregarSnap(snapUrl).then((indice) => {
      // A folha pode ter mudado enquanto o sidecar de 5 MB descia. Sem esta
      // guarda, a resposta atrasada da folha antiga sobrescreveria a atual.
      if (!vigente || !indice) return
      indiceSnap.current = indice
      setSnapParcial(indice.truncado)
    })
    return () => { vigente = false }
  }, [snapUrl])

  /** Onde o próximo clique vai cair, dado onde o cursor está. */
  const aoPairar = (p: Ponto | null, escalaDaTela: number) => {
    const indice = indiceSnap.current
    // `snapLigado` entra na MESMA guarda do índice ausente, e não num `if` à
    // parte: desligado e inexistente produzem a mesma tela — sem mira — e o
    // clique cai no ponto do dedo pelo mesmo caminho já provado.
    if (!p || !indice || !snapLigado || modo === 'navegar') {
      setMira((atual) => (atual ? null : atual))
      return
    }
    const achado = indice.procurar(p, escalaDaTela)
    // Comparar antes de setar corta a maior parte dos renders: o ponteiro anda
    // muitos pixels dentro do alcance do MESMO vértice, e cada movimento
    // produziria um render idêntico ao anterior.
    setMira((atual) =>
      atual?.ponto.x === achado?.ponto.x && atual?.ponto.y === achado?.ponto.y
        ? atual
        : achado,
    )
  }

  const filtro = { revisao: revisao.revisao_id }
  const marcacoes = useMarcacoes(filtro, papel.podeVerMarcacao)
  const medicoes = useMedicoes(papel.podeVerMarcacao ? revisao.revisao_id : null)
  const criar = useCriarMarcacao(documento.obra)
  const medir = useCriarMedicao(documento.obra)
  const calibrar = useCalibrar(documento.obra)
  const comentar = useComentar(documento.obra)
  const mudarSituacao = useMudarSituacao(documento.obra)
  const importar = useImportarBcf(documento.obra)
  const renomear = useRenomearDesenho(documento.obra)
  const [gavetaAberta, setGavetaAberta] = useState(false)
  /**
   * A gaveta das **entregas** — o que era o Histórico, o Acervo e as Conversões.
   *
   * Fica aqui e não numa aba porque as três respondiam perguntas sobre *esta*
   * prancha, e a pessoa que as faz está olhando para ela. Abre por cima do
   * desenho, como a das folhas, pelo mesmo motivo: coluna fixa no celular do
   * canteiro rouba metade do que se veio ver.
   */
  const [entregasAbertas, setEntregasAbertas] = useState(false)

  /**
   * A sobreposição só existe onde NÓS desenhamos a prancha.
   *
   * O PDF abre no leitor do próprio browser dentro de um `<iframe>`, e não há
   * como pôr camada sobre ele — a única derivada de PDF é a miniatura de 600 px,
   * declarada em `motores/documento.py` como "reconhecer a prancha, não ler a
   * cota": marcar sobre ela seria apontar num lugar que ninguém consegue
   * conferir. O 3D também fica de fora por ora (o ponto de vista do BCF ali é
   * câmera, não ponto na folha — é fatia própria).
   *
   * Nos dois casos a marcação continua funcionando **sem âncora**: dá para
   * apontar, conversar, resolver e exportar em BCF. O que não dá é fincar o pino
   * — e a tela diz isso, em vez de oferecer um gesto que erra o alvo.
   */
  const ehPdf = conversao.nativo && revisao.formato === 'pdf'
  const eh3d = conversao.tipo === 'modelo_3d'
  const podeSobrepor = Boolean(objeto) && !ehPdf && !eh3d

  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      // O Esc desfaz uma camada por vez: sair do modo de medição não deve
      // fechar a prancha inteira junto.
      if (modo !== 'navegar') {
        setModo('navegar')
        setEmCurso([])
        return
      }
      if (painelAberto) {
        setPainelAberto(false)
        return
      }
      if (entregasAbertas) {
        setEntregasAbertas(false)
        return
      }
      onFechar()
    }
    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  }, [onFechar, modo, painelAberto, entregasAbertas])

  const trocarModo = (novo: Modo) => {
    setModo(novo)
    setEmCurso([])
    if (novo !== 'navegar') setPainelAberto(false)
  }

  const apontar = (bruto: Ponto) => {
    // **A mira manda no clique.** Se o ponto gravado fosse o do dedo e não o do
    // vértice, a mira viraria enfeite: mostraria o canto certo e mediria o lugar
    // errado. Numa folha onde 1 px vale 4 cm, é o suficiente para a cota sair
    // com 8 cm de erro e cara de medida conferida.
    const p = mira?.ponto ?? bruto
    if (modo === 'marcar') {
      setAncoraPendente(p)
      return
    }
    const proximos = [...emCurso, p]
    setEmCurso(proximos)
    // Calibrar tem exatamente dois pontos: ao segundo, pergunta o valor. Deixar
    // acumular vértices daria a impressão de que a régua sai de uma polilinha.
    if (modo === 'calibrar' && proximos.length === MINIMO_DE_PONTOS.calibrar) {
      setCalibrando(true)
    }
  }

  const concluirMedida = async () => {
    if (modo !== 'distancia' && modo !== 'area') return
    await medir.mutateAsync({
      revisao: revisao.revisao_id,
      desenho: desenhoAberto?.desenho_id ?? null,
      tipo: modo === 'area' ? 'area' : 'distancia',
      pontos: emCurso,
    })
    setEmCurso([])
  }

  const registrarMarcacao = async (dados: {
    titulo: string; descricao: string; tipo: string; prioridade: string
  }) => {
    if (!ancoraPendente) return
    const marcacao = await criar.mutateAsync({
      revisao: revisao.revisao_id,
      desenho: desenhoAberto?.desenho_id ?? null,
      ancora: ancoraPendente,
      ...dados,
    })
    // O recorte vai depois, e a falha dele é engolida de propósito: um ponto de
    // vista sem imagem ainda é válido no BCF, e perder o apontamento inteiro
    // para salvar a foto seria trocar o essencial pelo acessório.
    try {
      const recorte = await capturarRecorte(imgRef.current, ancoraPendente)
      await anexarPontoDeVista(marcacao.marcacao_id, recorte)
    } catch {
      /* segue sem imagem */
    }
    setAncoraPendente(null)
    setModo('navegar')
    setPainelAberto(true)
    setSelecionada(marcacao.marcacao_id)
  }

  const aplicarCalibracao = async (distancia: number, unidade: string) => {
    if (!desenhoAberto) return
    await calibrar.mutateAsync({
      // O id é o da FOLHA, não o da revisão: a régua é por folha desde que uma
      // revisão passou a poder trazer várias. Mandar o da revisão calibraria a
      // folha cujo id coincidisse — um erro que o TypeScript não pega, porque os
      // dois são `number`.
      id: desenhoAberto.desenho_id,
      a: emCurso[0],
      b: emCurso[1],
      distancia_real: distancia,
      unidade,
    })
    setCalibrando(false)
    setEmCurso([])
    setModo('navegar')
  }

  const lista = marcacoes.data?.results ?? []
  const abertas = lista.filter((m) => m.aberta).length

  // D46 — a prancha abre e mesmo assim pode estar ilegível. Dispensável porque
  // quem já entendeu o problema vai querer olhar o pouco que há, e uma faixa
  // fixa sobre uma prancha pequena tiraria justamente o que sobrou dela.
  const [avisoVisivel, setAvisoVisivel] = useState(true)

  /**
   * O localizador (D97). Nasce **aberto** quando o arquivo tem mais de uma
   * folha, que é exatamente o caso em que a pessoa não sabe onde está o que ela
   * procura — abrir fechado seria esconder a resposta atrás de um botão que ela
   * ainda não sabe que existe. Com folha única o componente nem monta.
   */
  const [mapaAberto, setMapaAberto] = useState(true)
  useEffect(() => { setMapaAberto(true) }, [revisao.revisao_id])

  const irParaFolha = (ordem: number) => {
    setOrdemAberta(ordem)
    // O mesmo zelo da gaveta de folhas: os vértices em curso são normalizados
    // pela largura DAQUELA folha, e carregá-los para a seguinte mediria com a
    // régua errada num lugar que não é o mesmo.
    setEmCurso([])
    setModo('navegar')
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 95, background: 'var(--bg)',
        display: 'flex', flexDirection: 'column',
      }}
    >
      <header
        style={{
          display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
          borderBottom: '1px solid var(--line)', background: 'var(--glass)',
          backdropFilter: 'blur(14px)', flex: 'none',
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span className="num" style={{ fontSize: 12, fontWeight: 700, color: 'var(--ink-3)' }}>
              {documento.codigo}
            </span>
            <Pill kind={revisao.situacao === 'vigente' ? 'good' : 'slate'}>
              {revisao.revisao}
              {revisao.situacao === 'vigente' ? ' · vigente' : ` · ${revisao.situacao}`}
            </Pill>
            <Pill kind="slate">{revisao.formato_rotulo}</Pill>
          </div>
          <h2
            className="truncate"
            style={{ fontFamily: 'var(--display)', fontSize: 15, fontWeight: 700, color: 'var(--ink)', marginTop: 2 }}
          >
            {documento.titulo}
          </h2>
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Quem mais está com esta prancha aberta. O slot é permanente; o dado
              acende quando o heartbeat existir (`presenca.ts`) — até lá, o chip
              diz "em breve" em vez de contar você mesmo como companhia. */}
          <span className="hidden md:inline-flex"><PresencaChip revisaoId={revisao.revisao_id} /></span>

          {/* As folhas deste arquivo. Só aparece com mais de uma — com uma só,
              seria um interruptor ligado a nada (a lição do D5). O rótulo mostra
              a folha aberta, para a pessoa saber onde está sem abrir a lista. */}
          {/* O interruptor do localizador. Só aparece com mais de uma folha —
              com uma, o mapa não teria o que mapear (a lição do D5: interruptor
              ligado a nada). Fica ao lado da gaveta porque as duas respondem à
              mesma pergunta por caminhos diferentes: a lista diz *quais* são, o
              mapa diz *onde* estão. */}
          {folhas.length > 1 && (
            <Btn
              onClick={() => setMapaAberto((a) => !a)}
              title={mapaAberto
                ? 'Esconder o mapa dos desenhos'
                : 'Mostrar onde estão os desenhos deste arquivo'}
              variant={mapaAberto ? 'primary' : 'ghost'}
              style={{ minHeight: 46, minWidth: 46, justifyContent: 'center' }}
              aria-pressed={mapaAberto}
            >
              <MapIcon size={16} />
            </Btn>
          )}

          {folhas.length > 1 && (
            <Btn
              onClick={() => setGavetaAberta((a) => !a)}
              title="Trocar de desenho"
              variant={gavetaAberta ? 'primary' : 'ghost'}
              style={{ minHeight: 46 }}
            >
              <Layers size={16} />
              <span className="hidden sm:inline truncate" style={{ maxWidth: 160 }}>
                {desenhoAberto?.rotulo ?? 'Desenhos'}
              </span>
              <Pill kind={gavetaAberta ? 'slate' : 'accent'}>{folhas.length}</Pill>
            </Btn>
          )}

          {/* PRA.3 — a caixa de apontamentos. Sem `marcacao.view` o botão SOME:
              há cliente que compra o acervo para o campo consultar sem abrir a
              conversa técnica para todo mundo. Com a permissão, o contador de
              abertas fica no próprio botão — é a fila de decisão à mão. */}
          {papel.podeVerMarcacao && (
            <Btn
              onClick={() => { setPainelAberto((a) => !a); setModo('navegar') }}
              title="Apontamentos desta prancha"
              variant={painelAberto ? 'primary' : 'ghost'}
              style={{ minHeight: 46 }}
            >
              <MessageSquare size={16} />
              <span className="hidden sm:inline">Apontamentos</span>
              {abertas > 0 && <Pill kind={painelAberto ? 'slate' : 'accent'}>{abertas}</Pill>}
            </Btn>
          )}

          {/* **As entregas desta prancha** — quem mandou, quando, quem publicou, o
              que a conversão fez e o botão de atualizar o arquivo. Substituiu três
              abas, e mora aqui porque as três falavam desta prancha. O rótulo
              mostra a revisão na tela, para saber onde se está sem abrir a lista. */}
          <Btn
            onClick={() => { setEntregasAbertas((a) => !a); setGavetaAberta(false) }}
            title="Entregas desta prancha — revisões, datas e quem publicou"
            variant={entregasAbertas ? 'primary' : 'ghost'}
            style={{ minHeight: 46 }}
          >
            <Clock3 size={16} />
            <span className="hidden sm:inline">Entregas</span>
            <Pill kind={entregasAbertas ? 'slate' : 'accent'}>{documento.total_revisoes}</Pill>
          </Btn>

          {/* Alvos de 46 px: a mesma régua dos cartões — mão suja, luva, andaime. */}
          {revisao.arquivo_url && (
            <Btn
              onClick={() => baixarParaDisco(revisao.arquivo_url as string, `${documento.codigo}-${revisao.revisao}`)}
              title="Baixar o arquivo original, como o projetista entregou"
              style={{ minHeight: 46 }}
            >
              <Download size={16} /> <span className="hidden sm:inline">Original</span>
            </Btn>
          )}
          <Btn onClick={onFechar} aria-label="Fechar" style={{ minHeight: 46, minWidth: 46, justifyContent: 'center' }}>
            <X size={18} />
          </Btn>
        </div>
      </header>

      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        {carregando && <Aviso icone={<Spinner />} titulo="Abrindo a prancha…" />}

        {!carregando && erro && (
          <Aviso
            icone={<ServerCrash size={30} />}
            titulo={erro}
            detalhe="O registro existe no acervo, mas o arquivo não voltou do servidor."
          />
        )}

        {!carregando && !erro && objeto && (
          ehPdf ? (
            // PDF vai para o leitor do próprio browser: reimplementá-lo daria um
            // visualizador pior justamente no formato que nunca dependeu de nós.
            <iframe
              src={objeto}
              title={`${documento.codigo} ${revisao.revisao}`}
              style={{ width: '100%', height: '100%', border: 0, background: 'var(--inset)' }}
            />
          ) : eh3d ? (
            <Suspense fallback={<Aviso icone={<Spinner />} titulo="Carregando o visualizador 3D…" />}>
              <Vista3D src={objeto} />
            </Suspense>
          ) : (
            <Vista2D
              src={objeto}
              titulo={`${documento.codigo} ${revisao.revisao}`}
              desenhando={modo !== 'navegar'}
              mira={mira}
              ancora={emCurso[emCurso.length - 1] ?? null}
              // `por_folha` como guarda e não `mundo &&`: folha antiga chega com
              // `{}`, que é objeto verdadeiro — e aí o leitor mostraria
              // `undefined + x·undefined` como se fosse coordenada de desenho.
              mundo={desenhoAberto?.mundo?.por_folha
                ? (desenhoAberto.mundo as { origem_x: number; origem_y: number; por_folha: number })
                : null}
              aoApontar={apontar}
              aoPairar={aoPairar}
              aoCarregarImagem={(img) => { imgRef.current = img }}
            >
              {(enq) => (
                <Camada
                  enq={enq}
                  marcacoes={lista}
                  medicoes={medicoes.data?.results ?? []}
                  emCurso={emCurso}
                  modo={modo}
                  escala={escalaValor}
                  unidade={escalaUnidade}
                  selecionada={selecionada}
                  aoSelecionar={(id) => { setSelecionada(id); if (id) setPainelAberto(true) }}
                  mira={mira}
                />
              )}
            </Vista2D>
          )
        )}

        {!carregando && !erro && !objeto && (
          <SemDesenho
            revisao={revisao}
            onReprocessar={onReprocessar}
            podeReprocessar={podeReprocessar}
          />
        )}

        {/* A ressalva sobre uma prancha que ABRIU. Fica por cima do desenho, e
            não no lugar dele: o pouco que há para ver continua sendo o que o
            engenheiro veio ver — o que não pode é ele concluir sozinho que o
            sistema não presta. O botão Original já está no cabeçalho. */}
        {objeto && !erro && conversao.aviso && avisoVisivel && (
          <RessalvaDaPrancha
            aviso={conversao.aviso}
            aoFechar={() => setAvisoVisivel(false)}
          />
        )}

        {entregasAbertas && (
          <GavetaDeRevisoes
            documento={documento}
            revisaoAberta={revisao.revisao_id}
            aoFechar={() => setEntregasAbertas(false)}
            say={say}
          />
        )}

        {/* O localizador do D97 — a vista de cima do arquivo inteiro, com cada
            desenho no lugar em que ele está no terreno. Fica sobre a prancha
            porque é dela que ele fala, e some com um clique. */}
        {podeSobrepor && mapaAberto && (
          <Minimapa
            folhas={folhas}
            ordemAberta={desenhoAberto?.ordem ?? 1}
            aoAbrir={irParaFolha}
            aoFechar={() => setMapaAberto(false)}
          />
        )}

        {gavetaAberta && folhas.length > 1 && (
          <GavetaDeFolhas
            folhas={folhas}
            ordemAberta={desenhoAberto?.ordem ?? 1}
            aoAbrir={(ordem) => {
              irParaFolha(ordem)
              setGavetaAberta(false)
            }}
            aoFechar={() => setGavetaAberta(false)}
            aoRenomear={(id, nome) => renomear.mutateAsync({ id, nome })}
            podeRenomear={papel.podeCalibrar}
          />
        )}

        {podeSobrepor && (papel.podeMarcar || papel.podeCalibrar) && (
          <BarraDeModos
            modo={modo}
            aoTrocar={trocarModo}
            emCurso={emCurso}
            aoDesfazer={() => setEmCurso((p) => p.slice(0, -1))}
            aoConcluir={() => void concluirMedida()}
            aoCancelar={() => trocarModo('navegar')}
            escala={escalaValor}
            unidade={escalaUnidade}
            origem={escalaOrigem}
            podeMarcar={papel.podeMarcar}
            podeCalibrar={papel.podeCalibrar}
            ocupado={medir.isPending}
            snap={!!desenhoAberto?.snap}
            snapParcial={snapParcial}
            snapLigado={snapLigado}
            aoTrocarSnap={() => {
              setSnapLigado((ligado) => !ligado)
              // A mira some junto: deixá-la na tela depois de desligar diria que
              // o próximo clique ainda vai grudar nela — que é justamente o que
              // acabou de ser desligado.
              setMira(null)
            }}
          />
        )}

        {painelAberto && papel.podeVerMarcacao && (
          <PainelMarcacoes
            marcacoes={lista}
            carregando={marcacoes.isLoading}
            selecionada={selecionada}
            aoSelecionar={setSelecionada}
            aoComentar={(id, texto) => comentar.mutateAsync({ id, texto })}
            aoMudarSituacao={(id, situacao) => mudarSituacao.mutateAsync({ id, situacao })}
            aoImportarBcf={(arquivo) =>
              importar.mutateAsync({ revisao: revisao.revisao_id, arquivo })
            }
            podeMarcar={papel.podeMarcar}
            podeResolver={papel.podeResolver}
            aoFechar={() => setPainelAberto(false)}
          />
        )}

        {/* O limite declarado, e não escondido: onde não desenhamos a prancha,
            o pino não existe — mas o apontamento continua existindo. */}
        {painelAberto && !podeSobrepor && papel.podeMarcar && (
          <p
            style={{
              position: 'absolute', left: 12, bottom: 12, maxWidth: 320, margin: 0,
              padding: '10px 12px', fontSize: 11.5, lineHeight: 1.5, color: 'var(--ink-2)',
              background: 'var(--glass)', backdropFilter: 'blur(14px)',
              border: '1px solid var(--line)', borderRadius: 'var(--r-md)', zIndex: 2,
            }}
          >
            {ehPdf
              ? 'Nesta prancha em PDF dá para apontar, conversar e exportar em BCF — mas não fincar o pino nem medir: o PDF abre no leitor do navegador, onde não há como sobrepor camada.'
              : 'No modelo 3D o apontamento vale, mas o ponto de vista ainda não é capturado — ele chega numa fatia própria.'}
          </p>
        )}
      </div>

      {ancoraPendente && (
        <DialogoNovaMarcacao
          salvando={criar.isPending}
          aoCancelar={() => { setAncoraPendente(null); setModo('navegar') }}
          aoSalvar={(dados) => void registrarMarcacao(dados)}
        />
      )}

      {calibrando && emCurso.length >= 2 && (
        <DialogoCalibrar
          salvando={calibrar.isPending}
          origem={escalaOrigem}
          aoCancelar={() => { setCalibrando(false); setEmCurso([]); setModo('navegar') }}
          aoSalvar={(distancia, unidade) => void aplicarCalibracao(distancia, unidade)}
        />
      )}
    </div>
  )
}

/**
 * A faixa do topo — o arquivo abriu, e ainda assim há o que dizer.
 *
 * O dono do acervo pediu que ela continuasse existindo mesmo com a lista lateral:
 * quem abre a primeira folha de um arquivo de cinquenta precisa **saber que há
 * cinquenta** sem ter de procurar. A frase vem do backend (`conversao.aviso`),
 * não é montada aqui — quem decide o que declarar é o motor, e refazer o critério
 * em TypeScript daria duas respostas para o mesmo arquivo no primeiro ajuste.
 */
function RessalvaDaPrancha({
  aviso, aoFechar,
}: {
  aviso: NonNullable<Conversao['aviso']>
  aoFechar: () => void
}) {
  return (
    <div
      role="status"
      style={{
        position: 'absolute', top: 12, left: 12, right: 12, zIndex: 3,
        display: 'flex', alignItems: 'flex-start', gap: 10, maxWidth: 620,
        margin: '0 auto', padding: '11px 12px',
        background: 'var(--glass)', backdropFilter: 'blur(14px)',
        border: '1px solid color-mix(in srgb,var(--accent) 40%,var(--line))',
        borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-md)',
      }}
    >
      {/* O ícone segue o `codigo`, e não mais o `georreferenciado`: com três
          avisos possíveis, a bandeira do mundo ou a pilha de folhas em cima de
          "hachura simplificada" faria o leitor procurar folha que não há. */}
      {(() => {
        const Icone = aviso.codigo === 'hachura_simplificada'
          ? Hash : aviso.georreferenciado ? Globe2 : Layers
        return <Icone size={17} style={{ flex: 'none', marginTop: 1, color: 'var(--accent-ink)' }} />
      })()}
      <div style={{ minWidth: 0 }}>
        <strong style={{ display: 'block', fontSize: 12.5, fontWeight: 700, color: 'var(--ink)' }}>
          {aviso.titulo}
        </strong>
        <p style={{ margin: '3px 0 0', fontSize: 11.5, lineHeight: 1.5, color: 'var(--ink-2)' }}>
          {aviso.mensagem}
        </p>
      </div>
      <button
        onClick={aoFechar}
        aria-label="Dispensar o aviso"
        style={{
          flex: 'none', marginLeft: 'auto', width: 30, height: 30, display: 'grid',
          placeItems: 'center', cursor: 'pointer', background: 'transparent',
          border: 0, color: 'var(--ink-3)', borderRadius: 'var(--r-sm)',
        }}
      >
        <X size={15} />
      </button>
    </div>
  )
}

/**
 * A lista de folhas — o "três traços" que abre por cima do desenho.
 *
 * **É uma gaveta e não uma coluna fixa** pela régua da §9.1: no celular do
 * canteiro qualquer coluna permanente rouba metade da tela, e o que a pessoa veio
 * fazer é olhar o desenho. Só aparece quando há mais de uma folha — com uma só, o
 * botão seria um interruptor ligado a nada.
 *
 * O nome é editável aqui mesmo, e não numa tela de cadastro, porque quem descobre
 * que "Desenho 3" é a planta de cobertura é justamente quem acabou de abri-la.
 */
function GavetaDeFolhas({
  folhas, ordemAberta, aoAbrir, aoFechar, aoRenomear, podeRenomear,
}: {
  folhas: Desenho[]
  ordemAberta: number
  aoAbrir: (ordem: number) => void
  aoFechar: () => void
  aoRenomear: (id: number, nome: string) => Promise<unknown>
  podeRenomear: boolean
}) {
  const [editando, setEditando] = useState<number | null>(null)
  const [rascunho, setRascunho] = useState('')

  const salvar = async (desenho: Desenho) => {
    setEditando(null)
    if (rascunho.trim() !== desenho.nome) await aoRenomear(desenho.desenho_id, rascunho.trim())
  }

  return (
    <div
      style={{
        position: 'absolute', top: 0, right: 0, bottom: 0, zIndex: 6, width: 'min(320px, 86vw)',
        display: 'flex', flexDirection: 'column',
        background: 'var(--surface)', borderLeft: '1px solid var(--line)',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      <header style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '12px 14px',
        borderBottom: '1px solid var(--line)', flex: 'none',
      }}>
        <Layers size={16} style={{ color: 'var(--accent-ink)' }} />
        <strong style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink)' }}>
          Desenhos deste arquivo
        </strong>
        <span className="num" style={{ fontSize: 11, color: 'var(--ink-3)' }}>{folhas.length}</span>
        <button
          onClick={aoFechar}
          aria-label="Fechar a lista"
          style={{
            marginLeft: 'auto', width: 32, height: 32, display: 'grid', placeItems: 'center',
            cursor: 'pointer', background: 'transparent', border: 0, color: 'var(--ink-3)',
          }}
        >
          <X size={16} />
        </button>
      </header>

      <div style={{ overflowY: 'auto', padding: 8, display: 'grid', gap: 6 }}>
        {folhas.map((d) => {
          const aberto = d.ordem === ordemAberta
          return (
            <div
              key={d.desenho_id}
              style={{
                display: 'grid', gap: 4, padding: '10px 12px', borderRadius: 'var(--r-sm)',
                background: aberto ? 'color-mix(in srgb,var(--accent) 12%,transparent)' : 'transparent',
                border: `1px solid ${aberto ? 'var(--accent)' : 'var(--line)'}`,
              }}
            >
              {editando === d.desenho_id ? (
                <input
                  autoFocus
                  value={rascunho}
                  onChange={(e) => setRascunho(e.target.value)}
                  onBlur={() => void salvar(d)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void salvar(d)
                    if (e.key === 'Escape') setEditando(null)
                  }}
                  placeholder={`Desenho ${d.ordem}`}
                  maxLength={120}
                  style={{
                    width: '100%', minHeight: 34, padding: '4px 8px', fontSize: 13,
                    color: 'var(--ink)', background: 'var(--inset)',
                    border: '1px solid var(--accent)', borderRadius: 'var(--r-sm)',
                  }}
                />
              ) : (
                <button
                  onClick={() => aoAbrir(d.ordem)}
                  title={`Abrir — ${d.tracos.toLocaleString('pt-BR')} traços`}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, minHeight: 34, width: '100%',
                    padding: 0, cursor: 'pointer', textAlign: 'left', background: 'transparent',
                    border: 0, fontSize: 13, fontWeight: aberto ? 700 : 600, color: 'var(--ink)',
                  }}
                >
                  <span className="truncate" style={{ flex: 1 }}>{d.rotulo}</span>
                  <span className="num" style={{ fontWeight: 500, fontSize: 11, color: 'var(--ink-3)' }}>
                    {d.tracos.toLocaleString('pt-BR')}
                  </span>
                </button>
              )}

              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 }}>
                {/* Dado honesto: a folha sem régua diz que não tem, em vez de
                    deixar a pessoa supor que o metro está lá. */}
                <span className="num" style={{ color: 'var(--ink-3)' }}>
                  {d.tem_escala
                    ? `${d.escala_valor?.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} ${d.escala_unidade} de largura`
                    : 'sem escala'}
                </span>
                {podeRenomear && editando !== d.desenho_id && (
                  <button
                    onClick={() => { setEditando(d.desenho_id); setRascunho(d.nome) }}
                    style={{
                      marginLeft: 'auto', minHeight: 28, padding: '0 8px', cursor: 'pointer',
                      fontSize: 11, color: 'var(--ink-2)', background: 'transparent',
                      border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
                    }}
                  >
                    {d.nome ? 'Renomear' : 'Dar nome'}
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/**
 * Quando não há o que desenhar, o motivo é o produto.
 *
 * Os quatro casos são deliberadamente diferentes: **comprar** (limite de plano),
 * **esperar** (conversão em curso), **avisar-nos** (motor fora da imagem) e **ir
 * ao outro módulo** (o dono do dado não é a Prancheta). Fundi-los num "não foi
 * possível abrir" mandaria o mestre de obras abrir chamado por um upsell — ou o
 * dono comprar um plano por causa de um binário que falta no servidor.
 */
/**
 * **A espera com forma** (D98/PRA.11) — onde o arquivo está, quanto já saiu, e
 * o botão de subi-lo na fila da própria empresa.
 *
 * A tela dizia "Convertendo o arquivo…" e mais nada. Num DWG de 40 MB isso
 * ficava assim por meia hora, e quem olhava concluía que o sistema tinha morrido
 * — a queixa que abriu a fila. Três números resolvem: a posição (*"3º da fila"*),
 * o andamento em folhas (*"12 de 40"*, contáveis de verdade, ao contrário de uma
 * porcentagem inventada) e as voltas (*"2ª passada"*, que explica por que um
 * arquivo pesado sai da frente e volta).
 *
 * **O aviso antes do botão é o pedido literal do dono** — *"faça um aviso do que
 * está acontecendo e se ele quer passar"*. Ele diz o que vai acontecer com um
 * número do servidor: subir este atrasa outros N arquivos **seus**, e nenhum de
 * fora. Sem esse número, seria o botão que todo mundo aperta sempre.
 */
function NaFila({ conversao }: { conversao: Conversao }) {
  const qc = useQueryClient()
  const fila = conversao.fila
  const [subindo, setSubindo] = useState(false)
  const [confirmando, setConfirmando] = useState(false)

  if (!fila) {
    // Sem linha na fila: conversão síncrona, job anterior a esta fatia, ou a
    // corrida entre o worker terminar e a tela perguntar. A frase de sempre, que
    // continua verdadeira — nunca uma posição inventada.
    return (
      <Aviso
        icone={<Spinner />}
        titulo="Convertendo o arquivo…"
        detalhe="A conversão roda em segundo plano; esta tela se atualiza sozinha quando terminar."
      />
    )
  }

  const rodando = fila.situacao === 'despachada'
  const partes: string[] = []
  if (fila.folhas_prontas > 0) {
    partes.push(
      `${fila.folhas_prontas} de ${fila.folhas_prontas + fila.folhas_restantes} folhas prontas`,
    )
  }
  if (fila.voltas > 0) partes.push(`${fila.voltas + 1}ª passada`)

  const subir = async () => {
    setSubindo(true)
    try {
      await priorizarNaFila(fila.tarefa_id)
      await qc.invalidateQueries({ queryKey: ['prancheta'] })
    } finally {
      setSubindo(false)
      setConfirmando(false)
    }
  }

  return (
    <Aviso
      icone={<Spinner />}
      titulo={rodando ? 'Convertendo o arquivo…' : `${fila.posicao}º da fila de conversão`}
      detalhe={
        rodando
          ? [
              'A conversão está rodando agora.',
              ...partes,
            ].join(' · ')
          : [
              'A frota de conversão está ocupada. Este arquivo entra assim que uma vaga abrir.',
              ...partes,
            ].join(' · ')
      }
      acao={
        fila.pode_priorizar ? (
          confirmando ? (
            <span style={{ display: 'grid', gap: 9, justifyItems: 'center' }}>
              <span style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.6, maxWidth: 380 }}>
                Subindo este arquivo, ele passa na frente de{' '}
                <strong>
                  {fila.na_frente_da_empresa} arquivo
                  {fila.na_frente_da_empresa > 1 ? 's' : ''} da sua empresa
                </strong>{' '}
                que estão esperando há mais tempo. Nenhum arquivo de outra empresa
                é atrasado.
              </span>
              <span style={{ display: 'flex', gap: 8 }}>
                <Btn onClick={() => setConfirmando(false)}>Deixar como está</Btn>
                <Btn variant="primary" disabled={subindo} onClick={() => void subir()}>
                  {subindo ? <Spinner /> : null} Passar na frente
                </Btn>
              </span>
            </span>
          ) : (
            <Btn onClick={() => setConfirmando(true)}>
              <Timer size={15} /> Passar na frente da fila
            </Btn>
          )
        ) : undefined
      }
    />
  )
}

function SemDesenho({
  revisao,
  onReprocessar,
  podeReprocessar,
}: {
  revisao: RevisaoResumo
  onReprocessar?: () => void
  podeReprocessar?: boolean
}) {
  const { conversao } = revisao

  if (conversao.estado === 'convertendo') {
    // **A espera ganhou forma** (D98/PRA.11). "Convertendo o arquivo…" por meia
    // hora é indistinguível de travado — foi essa a queixa que abriu a fila. Com
    // a `fila` no ar, a mesma tela diz onde o arquivo está, quanto já saiu e
    // oferece o botão de subi-lo na fila da própria empresa.
    return <NaFila conversao={conversao} />
  }

  if (conversao.estado === 'erro' && conversao.exige_upgrade) {
    return (
      <Aviso
        icone={<Lock size={30} />}
        titulo="Este arquivo exige o motor de alta fidelidade"
        detalhe="O motor incluído no seu plano não abre esta versão do arquivo. O plano com o motor premium converte, e a revisão já enviada é reaproveitada — nada precisa ser subido de novo."
      />
    )
  }

  if (conversao.estado === 'erro') {
    return (
      <Aviso
        icone={<AlertTriangle size={30} />}
        titulo="A conversão falhou"
        detalhe={conversao.detalhe || 'A falha é nossa, não do seu arquivo nem do seu plano.'}
        acao={
          podeReprocessar && onReprocessar ? (
            <Btn variant="primary" onClick={onReprocessar}>Tentar converter de novo</Btn>
          ) : undefined
        }
      />
    )
  }

  // **Não é falta de motor, é falta de job** (D81). O texto diz o que houve sem
  // culpar o arquivo nem o plano — os dois estão certos —, e traz o verbo: quem
  // pode reprocessar resolve daqui, sem subir o arquivo de novo.
  if (conversao.estado === 'nao_agendada') {
    return (
      <Aviso
        icone={<Timer size={30} />}
        titulo="A conversão desta prancha ainda não foi enfileirada"
        detalhe="O arquivo está no acervo e o motor que o abre existe no seu plano — o que não aconteceu foi o processamento. Reprocessar resolve; nada precisa ser enviado de novo."
        acao={
          podeReprocessar && onReprocessar ? (
            <Btn variant="primary" onClick={onReprocessar}>Converter agora</Btn>
          ) : undefined
        }
      />
    )
  }

  if (conversao.estado === 'outro_modulo') {
    return (
      <Aviso
        icone={<ExternalLink size={30} />}
        titulo="Este arquivo é lido por outro módulo"
        detalhe={`O formato ${revisao.formato_rotulo} pertence ao módulo ${conversao.dono ?? 'correspondente'} — é lá que ele vira mapa ou nuvem de pontos.`}
        acao={conversao.dono === 'modulomaps'
          ? <Link to="/app/maps"><Btn variant="primary">Abrir em Mapas &amp; Território</Btn></Link>
          : undefined}
      />
    )
  }

  // **Este ramo é o último, e por isso é o que mais precisa de saída.** Os três
  // acima oferecem ação (reprocessar, ir ao Maps); este oferecia só a frase — e
  // como o visualizador ocupa a tela, ficar nele era ficar preso, sem sequer o
  // download que a própria frase promete. Um aviso sem verbo, na tela inteira, é
  // um bloqueio com texto explicativo.
  return (
    <Aviso
      icone={<AlertTriangle size={30} />}
      titulo="Ainda não há visualizador para este formato"
      detalhe={`O ${revisao.formato_rotulo} está no acervo e pode ser baixado, mas o motor que o abre no navegador ainda não existe aqui.`}
      acao={revisao.arquivo_url ? (
        <Btn
          variant="primary"
          onClick={() => baixarParaDisco(revisao.arquivo_url as string, revisao.revisao)}
        >
          Baixar o arquivo
        </Btn>
      ) : undefined}
    />
  )
}

function Aviso({
  icone, titulo, detalhe, acao,
}: {
  icone: ReactNode
  titulo: string
  detalhe?: string
  acao?: ReactNode
}) {
  return (
    <div
      style={{
        height: '100%', display: 'grid', placeItems: 'center', alignContent: 'center',
        gap: 12, padding: 28, textAlign: 'center', color: 'var(--ink-3)',
      }}
    >
      <span style={{ color: 'var(--ink-3)' }}>{icone}</span>
      <strong style={{ fontSize: 15, color: 'var(--ink)', fontWeight: 700 }}>{titulo}</strong>
      {detalhe && <p style={{ fontSize: 13, maxWidth: 460, lineHeight: 1.5 }}>{detalhe}</p>}
      {acao}
    </div>
  )
}
