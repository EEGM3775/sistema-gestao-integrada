import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useQueries } from '@tanstack/react-query'
import { AlertTriangle, Check, CheckCheck, FolderUp, Upload, Wand2, X } from 'lucide-react'

import { Btn } from '../Btn'
import { Modal } from '../Modal'
import { Pill } from '../Pill'
import { Spinner } from '../States'
import {
  aplicarImportacao, arquivoComCaminho, consultarImportacao, corrigirLinhas,
  descartarImportacao, importarArquivos,
} from './api'
import type {
  LimitesDoPlano, LinhaConferencia, RecursoImpExp, ResumoImportacao, SituacaoLinha,
} from './api'
import { impexpKeys, useRecurso } from './hooks'

const KIND: Record<SituacaoLinha, 'good' | 'info' | 'danger'> = {
  nova: 'good', duplicada: 'info', invalida: 'danger',
}
const NOME_SITUACAO: Record<SituacaoLinha, string> = {
  nova: 'nova', duplicada: 'já existe', invalida: 'inválida',
}
const CAPS = {
  fontSize: 10.5, fontWeight: 700, letterSpacing: '.07em',
  textTransform: 'uppercase' as const, color: 'var(--ink-3)',
}
const mono = { fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' as const }

/**
 * Arquivos por remessa. **Não é estilo, é o teto do Django**
 * (`DATA_UPLOAD_MAX_NUMBER_FILES`, 100 desde a 5.1): uma pasta de acervo passa
 * disso com folga, e o servidor recusaria a requisição inteira em vez de o
 * arquivo. Dez é o mesmo tamanho que o
 * [carregar_acervo_dwg.py](../../../../../testes/e2e/carregar_acervo_dwg.py)
 * usa há três passadas de medição, e mantém cada remessa reenviável sozinha.
 */
const POR_REMESSA = 10

type Passo = 'escolher' | 'enviando' | 'conferencia'

interface Remessa {
  indice: number
  arquivos: string[]
  resumo?: ResumoImportacao
  erro?: string
}

interface Props {
  recurso: string
  /** O destino, resolvido pela tela que hospeda o wizard (a obra, no acervo). */
  contexto?: Record<string, unknown>
  rotulo?: string
  tam?: 'sm' | 'md'
  onConcluida?: (aplicadas: number) => void
  /**
   * A regra que só o módulo sabe, dita **no passo de escolher** — acima dos dois
   * cartões, antes de alguém abrir o seletor de arquivos.
   *
   * O wizard sabe dizer o que este destino recebe e até quantos MB, porque isso
   * está declarado no `Recurso`. O que ele não sabe é o que o arquivo **vira**
   * ao entrar: no acervo da Prancheta, `ARQ-PLB-001_R02.dwg` é a prancha
   * `ARQ-PLB-001` na revisão `R02`, e mandar o mesmo código de novo é revisão
   * nova em vez de prancha duplicada. Isso morava numa janela anterior, que a
   * pessoa abria só para clicar em "Enviar pasta" e abrir a segunda — um clique
   * e uma janela para nada. Cabendo aqui, o gesto tem uma janela só.
   */
  ajuda?: ReactNode
}

/**
 * IE.3c — o **Enviar arquivos** de todo módulo: pasta → conferência → decisão.
 *
 * O irmão do {@link WizardImportacao}, e existe separado dele pela mesma razão
 * que a porta do backend é um endpoint próprio e não um `if` dentro do outro
 * ([views.py](../../../../../backend/funcoesimpexp/views.py)): as duas naturezas
 * divergem em tudo que a tela faz. Lá a unidade de decisão é a **linha** de uma
 * planilha e o passo do meio é o de-para; aqui a unidade é o **arquivo**, o
 * gesto de origem é escolher uma **pasta**, e o que se confere é o que a
 * plataforma adivinhou do caminho dela.
 *
 * **A régua R1 vale sobre o conjunto, não sobre a remessa.** O envio é picado em
 * remessas por causa do teto de arquivos por requisição, mas a decisão é uma só:
 * as remessas ficam todas em `CONFERINDO` — nenhum documento criado — até
 * "Confirmar tudo". Aplicar remessa a remessa enquanto o resto sobe daria um
 * acervo pela metade se a pessoa fechasse a aba no meio, que é exatamente o que
 * a conferência existe para impedir.
 *
 * Some quando a pessoa não pode operar o recurso, como o {@link BotaoExportar} —
 * quem decide é `/api/impexp/recursos/`, não uma prop.
 */
export function WizardArquivos({
  recurso, contexto, rotulo = 'Enviar arquivos', tam = 'sm', onConcluida, ajuda,
}: Props) {
  const { recurso: declaracao, limites } = useRecurso(recurso)
  const [aberto, setAberto] = useState(false)
  const [passo, setPasso] = useState<Passo>('escolher')
  const [remessas, setRemessas] = useState<Remessa[]>([])
  const [enviadas, setEnviadas] = useState(0)
  const [pctRemessa, setPctRemessa] = useState(0)
  const [erro, setErro] = useState('')
  const [total, setTotal] = useState(0)

  // A porta de arquivo é outra: um recurso tabular aqui abriria um seletor de
  // pasta sobre um endpoint que só aceita uma planilha.
  if (!declaracao?.importa || declaracao.natureza !== 'arquivo') return null

  function fechar() {
    setAberto(false)
    setPasso('escolher')
    setRemessas([])
    setEnviadas(0)
    setPctRemessa(0)
    setTotal(0)
    setErro('')
  }

  async function enviar(escolhidos: File[]) {
    setErro('')
    setPasso('enviando')
    setTotal(escolhidos.length)
    setEnviadas(0)

    const feitas: Remessa[] = []
    for (let inicio = 0; inicio < escolhidos.length; inicio += POR_REMESSA) {
      const janela = escolhidos.slice(inicio, inicio + POR_REMESSA)
      const remessa: Remessa = {
        indice: feitas.length + 1,
        arquivos: janela.map(arquivoComCaminho),
      }
      setPctRemessa(0)
      try {
        remessa.resumo = await importarArquivos({
          recurso, arquivos: janela, contexto, onProgresso: setPctRemessa,
        })
      } catch (e) {
        // **Uma remessa recusada não derruba o lote inteiro.** O 402 é por
        // arquivo (formato não contratado, peso acima do teto) e mata os dez
        // que viajavam com ele; parar tudo aqui faria um `.bak` esquecido na
        // pasta custar o acervo todo. A remessa fica marcada, com o motivo, e a
        // conferência mostra o que entrou.
        const resposta = (e as { response?: { status?: number; data?: Recusa } })?.response
        remessa.erro = mensagemDaRecusa(resposta?.data) ?? 'Remessa recusada pelo servidor.'
      }
      feitas.push(remessa)
      setRemessas([...feitas])
      setEnviadas(Math.min(inicio + janela.length, escolhidos.length))
    }

    if (!feitas.some(r => r.resumo)) {
      setErro(feitas[0]?.erro ?? 'Nenhum arquivo foi aceito.')
      setPasso('escolher')
      return
    }
    setPasso('conferencia')
  }

  return (
    <>
      <Btn tam={tam} onClick={() => setAberto(true)}>
        <FolderUp size={13} />{rotulo}
      </Btn>

      {aberto && (
        <Modal
          titulo={`Enviar arquivos · ${declaracao.rotulo}`}
          // **A conferência é uma planilha, não um aviso.** São 11 colunas
          // (situação, hash, arquivo, caminho, formato, tamanho, obra,
          // disciplina, código, revisão, observação), e em 960 px cada uma sobra
          // com ~80 px — nome de arquivo e caminho, que é o que a pessoa lê para
          // decidir, ficavam ilegíveis. Aqui a régua é a janela, com um teto para
          // a linha não virar um trilho de dois metros no monitor ultrawide.
          largura={passo === 'conferencia' ? 1760 : 620}
          alto={passo === 'conferencia'}
          onClose={passo === 'enviando' ? () => undefined : fechar}
        >
          {erro && (
            <div style={{
              marginBottom: 13, padding: '9px 12px', borderRadius: 'var(--r-sm)', flex: 'none',
              background: 'var(--danger-soft)', color: 'var(--danger-ink)', fontSize: 12.5,
            }}>{erro}</div>
          )}

          {passo === 'escolher' && (
            <PassoEscolher
              declaracao={declaracao} limites={limites} onEnviar={enviar} ajuda={ajuda}
            />
          )}
          {passo === 'enviando' && (
            <PassoEnviando
              enviadas={enviadas} total={total} pctRemessa={pctRemessa} remessas={remessas}
            />
          )}
          {passo === 'conferencia' && (
            <PassoConferencia
              declaracao={declaracao}
              remessas={remessas}
              onFechar={fechar}
              onConcluida={aplicadas => { onConcluida?.(aplicadas); fechar() }}
            />
          )}
        </Modal>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// 1. Escolher a pasta — e dizer o teto ANTES, não no 402
// ---------------------------------------------------------------------------

interface Peneirado {
  aceitos: File[]
  /** Estava na pasta e este destino não recebe — não sobe, e não é erro dele. */
  fora: File[]
  /** Formato certo, peso acima do teto declarado do plano. */
  pesados: { arquivo: File; teto: number }[]
}

function PassoEscolher({ declaracao, limites, onEnviar, ajuda }: {
  declaracao: RecursoImpExp
  limites?: LimitesDoPlano
  onEnviar: (arquivos: File[]) => void
  ajuda?: ReactNode
}) {
  const campoPasta = useRef<HTMLInputElement>(null)
  const campoArquivos = useRef<HTMLInputElement>(null)
  const [peneira, setPeneira] = useState<Peneirado | null>(null)

  /**
   * Os formatos que ESTE destino recebe, cada um com o teto que a **porta dele**
   * vai aplicar.
   *
   * `tetos_mb` ganha do `limites.formatos[].max_mb` porque o segundo é o teto da
   * planilha, e usá-lo aqui foi o D83: a tela recusava sozinha, com a frase do
   * plano, um DWG de 64,9 MB que o servidor aceita até 150. O `??` só cobre
   * catálogo de backend antigo, que não traz o campo.
   */
  const recebidos = useMemo(() => {
    const doDestino = new Set(declaracao.formatos_arquivo)
    return (limites?.formatos ?? [])
      .filter(f => doDestino.has(f.codigo))
      .map(f => ({ ...f, max_mb: declaracao.tetos_mb?.[f.codigo] ?? f.max_mb }))
  }, [declaracao.formatos_arquivo, declaracao.tetos_mb, limites])

  const extensoes = useMemo(
    () => recebidos.flatMap(f => f.extensoes),
    [recebidos],
  )

  function peneirar(lista: FileList | null) {
    const todos = Array.from(lista ?? [])
    const resultado: Peneirado = { aceitos: [], fora: [], pesados: [] }
    for (const arquivo of todos) {
      const nome = arquivo.name.toLowerCase()
      // A extensão peneira **aqui**, e o servidor decide de verdade pelos bytes.
      // Não é validação duplicada: é o que evita mandar 300 MB de `.docx` de uma
      // pasta de projeto para receber um 400 que já se sabia.
      const formato = recebidos.find(f => f.extensoes.some(e => nome.endsWith(e)))
      if (!formato) { resultado.fora.push(arquivo); continue }
      if (formato.max_mb && arquivo.size > formato.max_mb * 1024 * 1024) {
        resultado.pesados.push({ arquivo, teto: formato.max_mb })
        continue
      }
      resultado.aceitos.push(arquivo)
    }
    setPeneira(resultado)
  }

  const mb = (bytes: number) => (bytes / 1048576).toFixed(bytes > 10485760 ? 0 : 1)
  const somados = peneira ? peneira.aceitos.reduce((s, a) => s + a.size, 0) : 0

  return (
    <div>
      {/* A regra do módulo vem ANTES da genérica: quem abriu isto quer saber o
          que o arquivo dele vira, e só depois como escolhê-lo. */}
      {ajuda && <div style={{ marginBottom: 14 }}>{ajuda}</div>}

      <p style={{ margin: '0 0 14px', fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
        Escolha a <b>pasta</b> do acervo. É o caminho dentro dela — e não só o nome do arquivo —
        que diz a disciplina, o código e a revisão de cada prancha. Tudo é conferido{' '}
        <b>antes de gravar</b>: nada entra sem a sua confirmação.
      </p>

      <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap' }}>
        <div
          onClick={() => campoPasta.current?.click()}
          style={{
            flex: '1 1 240px', display: 'grid', placeItems: 'center', gap: 8,
            padding: '26px 16px', border: '1px dashed var(--line)',
            borderRadius: 'var(--r-md)', background: 'var(--inset)', cursor: 'pointer',
            textAlign: 'center',
          }}
        >
          <FolderUp size={24} style={{ color: 'var(--ink-3)' }} />
          <span style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>
            Escolher pasta
          </span>
          <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
            com as subpastas, como está no seu computador
          </span>
        </div>
        <div
          onClick={() => campoArquivos.current?.click()}
          style={{
            flex: '1 1 180px', display: 'grid', placeItems: 'center', gap: 8,
            padding: '26px 16px', border: '1px dashed var(--line)',
            borderRadius: 'var(--r-md)', background: 'var(--inset)', cursor: 'pointer',
            textAlign: 'center',
          }}
        >
          <Upload size={24} style={{ color: 'var(--ink-3)' }} />
          <span style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>
            Escolher arquivos
          </span>
          <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>soltos, sem pasta</span>
        </div>
      </div>

      <input
        ref={campoPasta} type="file" multiple style={{ display: 'none' }}
        // `webkitdirectory` não está na tipagem do React porque não é padrão —
        // é, na prática, o único jeito de um navegador entregar uma árvore de
        // pastas, e Chrome, Firefox, Safari e Edge o implementam.
        {...{ webkitdirectory: '', directory: '' }}
        onChange={e => { peneirar(e.target.files); e.target.value = '' }}
      />
      <input
        ref={campoArquivos} type="file" multiple accept={extensoes.join(',')}
        style={{ display: 'none' }}
        onChange={e => { peneirar(e.target.files); e.target.value = '' }}
      />

      {/* O teto dito ANTES da escolha — parte 3 do método do gov.br. */}
      <div style={{ marginTop: 13, fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.6 }}>
        Este destino recebe{' '}
        {recebidos.length
          ? recebidos.map(f => `${f.rotulo} (até ${f.max_mb} MB)`).join(' · ')
          : declaracao.formatos_arquivo.join(', ').toUpperCase()}
        {limites?.plano ? ` — plano ${limites.plano}.` : '.'}
      </div>

      {peneira && (
        <div style={{
          marginTop: 14, paddingTop: 13, borderTop: '1px solid var(--line)',
          display: 'grid', gap: 9,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Pill kind="good">{peneira.aceitos.length} para enviar</Pill>
            {peneira.fora.length > 0 && (
              <Pill kind="slate">{peneira.fora.length} fora deste destino</Pill>
            )}
            {peneira.pesados.length > 0 && (
              <Pill kind="danger">{peneira.pesados.length} acima do teto</Pill>
            )}
            <span style={{ ...mono, fontSize: 11.5, color: 'var(--ink-3)' }}>
              {mb(somados)} MB · {Math.ceil(peneira.aceitos.length / POR_REMESSA)} remessa(s)
            </span>
          </div>

          {peneira.pesados.length > 0 && (
            <div style={{
              display: 'flex', gap: 8, padding: '9px 12px', borderRadius: 'var(--r-sm)',
              background: 'var(--danger-soft)', color: 'var(--danger-ink)', fontSize: 12,
              lineHeight: 1.5,
            }}>
              <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
              <span>
                Ficam de fora por peso, e o motivo é o plano, não o arquivo:{' '}
                {peneira.pesados.slice(0, 3).map(p => (
                  `${p.arquivo.name} (${mb(p.arquivo.size)} MB, teto ${p.teto})`
                )).join(' · ')}
                {peneira.pesados.length > 3 && ` e mais ${peneira.pesados.length - 3}`}.
              </span>
            </div>
          )}

          <div style={{ display: 'flex', gap: 9, justifyContent: 'flex-end' }}>
            <Btn tam="sm" onClick={() => setPeneira(null)}>Trocar seleção</Btn>
            <Btn
              tam="sm" variant="primary" disabled={!peneira.aceitos.length}
              onClick={() => onEnviar(peneira.aceitos)}
            >
              <Upload size={13} />Enviar {peneira.aceitos.length} arquivo(s)
            </Btn>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// 2. Envio — remessa a remessa, e a barra diz de qual
// ---------------------------------------------------------------------------

function PassoEnviando({ enviadas, total, pctRemessa, remessas }: {
  enviadas: number
  total: number
  pctRemessa: number
  remessas: Remessa[]
}) {
  const pct = total ? Math.round((enviadas / total) * 100) : 0
  const recusadas = remessas.filter(r => r.erro).length
  return (
    <div style={{ display: 'grid', gap: 13, padding: '8px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
        <Spinner size={18} />
        <div style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
          Enviando remessa {remessas.length + (enviadas < total ? 1 : 0)} de{' '}
          {Math.ceil(total / POR_REMESSA)}.
          <span style={{ display: 'block', color: 'var(--ink-3)', marginTop: 2 }}>
            {enviadas} de {total} arquivos no servidor — <b>nada gravado ainda</b>.
          </span>
        </div>
      </div>
      <div style={{ height: 6, borderRadius: 999, background: 'var(--inset)', overflow: 'hidden' }}>
        <div style={{
          width: `${Math.max(pct, 3)}%`, height: '100%', background: 'var(--accent)',
          transition: 'width .3s',
        }} />
      </div>
      <div style={{ ...CAPS, display: 'flex', gap: 10 }}>
        <span>remessa atual {pctRemessa}%</span>
        {recusadas > 0 && (
          <span style={{ color: 'var(--danger-ink)' }}>{recusadas} remessa(s) recusada(s)</span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 3. Conferência — R1 sobre o conjunto inteiro
// ---------------------------------------------------------------------------

function PassoConferencia({ declaracao, remessas, onFechar, onConcluida }: {
  declaracao: RecursoImpExp
  remessas: Remessa[]
  onFechar: () => void
  onConcluida: (aplicadas: number) => void
}) {
  const [filtro, setFiltro] = useState<'' | SituacaoLinha>('')
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [aplicando, setAplicando] = useState(0)

  const ids = useMemo(
    () => remessas.map(r => r.resumo?.importacao_id).filter((v): v is number => !!v),
    [remessas],
  )

  const consultas = useQueries({
    queries: ids.map(id => ({
      queryKey: impexpKeys.importacao(id, ''),
      queryFn: () => consultarImportacao(id),
    })),
  })

  const carregando = consultas.some(c => c.isLoading)
  const detalhes = consultas.map(c => c.data).filter(Boolean)

  const soma = (campo: 'total' | 'novas' | 'duplicadas' | 'invalidas') =>
    detalhes.reduce((s, d) => s + (d?.[campo] ?? 0), 0)

  const linhas = useMemo(() => {
    const todas = detalhes.flatMap(d => d?.linhas ?? [])
    return filtro ? todas.filter(l => l.situacao === filtro) : todas
  }, [detalhes, filtro])

  const recusadas = remessas.filter(r => r.erro)

  /** As colunas que o RECURSO abriu para correção — a tela não escolhe. */
  const editaveis = useMemo(
    () => declaracao.colunas.filter(c => c.editavel),
    [declaracao.colunas],
  )

  /**
   * R19 — corrige o palpite de uma linha, sem reenviar o arquivo.
   *
   * A linha vive numa das N remessas, e o endpoint é por importação: descobre-se
   * qual pelo `linhas` que já está carregado. Invalida a consulta daquela
   * remessa só — recarregar as outras piscaria a tabela inteira por causa de uma
   * célula.
   */
  async function corrigir(linhaId: number, campo: string, valor: string) {
    const dono = detalhes.find(d => (d?.linhas ?? []).some(l => l.linha_id === linhaId))
    const importacaoId = dono?.importacao_id
    if (!importacaoId) return
    setErro('')
    try {
      await corrigirLinhas(importacaoId, { [campo]: valor }, [linhaId])
      await consultas[ids.indexOf(importacaoId)]?.refetch()
    } catch (e) {
      const detalhe = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErro(detalhe ?? 'Não foi possível corrigir esta linha.')
    }
  }

  /** O mesmo valor em TODAS as linhas — a remessa homogênea em dois toques. */
  async function corrigirTodas(campo: string, valor: string) {
    setErro('')
    setOcupado(true)
    try {
      for (const id of ids) await corrigirLinhas(id, { [campo]: valor })
      await Promise.all(consultas.map(c => c.refetch()))
    } catch (e) {
      const detalhe = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErro(detalhe ?? 'Não foi possível aplicar a todos.')
    } finally { setOcupado(false) }
  }

  async function decidir(acao: 'aplicar' | 'descartar') {
    setErro('')
    setOcupado(true)
    setAplicando(0)
    let aplicadas = 0
    try {
      for (const [i, id] of ids.entries()) {
        setAplicando(i + 1)
        const resumo = acao === 'aplicar'
          ? await aplicarImportacao(id)
          : await descartarImportacao(id)
        aplicadas += resumo.aplicadas ?? 0
      }
      onConcluida(acao === 'aplicar' ? aplicadas : 0)
    } catch (e) {
      const detalhe = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      // Metade aplicada é estado real, e esconder isso mandaria a pessoa
      // reenviar o que já entrou. O acervo é a fonte: ele mostra o que existe.
      setErro(
        `${detalhe ?? 'Não foi possível concluir.'} ` +
        `${aplicadas} arquivo(s) já haviam entrado quando parou.`,
      )
    } finally { setOcupado(false) }
  }

  /**
   * A roda anda para o lado quando só há para onde ir para o lado.
   *
   * **O relato que motivou isto:** com um arquivo só na conferência, a lista não
   * tem o que rolar na vertical — mas tem onze colunas e sobra tabela para a
   * direita. O gesto que a pessoa faz é girar a roda, e a roda **não rola na
   * horizontal**: nada acontece, e as colunas da direita (código, revisão,
   * observação) ficam inalcançáveis sem arrastar a barra de baixo.
   *
   * A tradução só vale quando **não há rolagem vertical nenhuma** aqui. Havendo,
   * a roda continua sendo da vertical — sequestrá-la nos dois eixos quebraria o
   * gesto normal de percorrer trezentos arquivos, que é o caso comum. `Shift +
   * roda` já é horizontal pelo navegador e passa direto.
   *
   * Listener nativo e não `onWheel`: em React o `onWheel` é passivo e o
   * `preventDefault()` não pega — a página rolaria junto. (Mesma armadilha já
   * documentada em `Vista2D.tsx`.)
   */
  const rolagem = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const caixa = rolagem.current
    if (!caixa) return
    const aoRodar = (e: WheelEvent) => {
      if (e.shiftKey || e.deltaX) return
      const temVertical = caixa.scrollHeight > caixa.clientHeight + 1
      const temHorizontal = caixa.scrollWidth > caixa.clientWidth + 1
      if (temVertical || !temHorizontal) return
      e.preventDefault()
      caixa.scrollLeft += e.deltaY
    }
    caixa.addEventListener('wheel', aoRodar, { passive: false })
    return () => caixa.removeEventListener('wheel', aoRodar)
    // `carregando` na lista: enquanto ele é `true` a caixa nem existe no DOM, e
    // um efeito com dependência vazia amarraria o listener a um `ref` nulo e
    // nunca mais tentaria — a rolagem lateral só funcionaria por acidente de
    // ordem de renderização.
  }, [carregando])

  if (carregando) {
    return <div style={{ padding: 30, textAlign: 'center' }}><Spinner /></div>
  }

  const filtros: { valor: '' | SituacaoLinha; rotulo: string }[] = [
    { valor: '', rotulo: `Todos (${soma('total')})` },
    { valor: 'nova', rotulo: `Novos (${soma('novas')})` },
    { valor: 'duplicada', rotulo: `Já existem (${soma('duplicadas')})` },
    { valor: 'invalida', rotulo: `Inválidos (${soma('invalidas')})` },
  ]

  return (
    // `flex: 1` e não `height: 100%`: este bloco é filho direto do miolo do
    // `Modal alto`, que já é coluna flex. Altura percentual dentro de flex
    // depende de o pai ter altura resolvida, e quebra em silêncio no dia em que
    // alguém enfiar um wrapper aqui; `flex: 1` + `minHeight: 0` não depende disso.
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      {/* **Cabeçalho em UMA fileira.** Ele ocupava três — título, contadores e
          filtros —, e como os filtros já dizem o mesmo número que as pastilhas
          ("Novos (1)" e "1 novos"), a repetição custava duas fileiras da altura
          útil para não informar nada. O que sobra da altura é da lista, que é o
          que a pessoa veio ler. */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
        marginBottom: 10, flex: 'none',
      }}>
        <div style={{ minWidth: 0 }}>
          <span style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>
            {soma('total')} arquivo(s) em {ids.length} remessa(s)
          </span>
          <span style={{ fontSize: 11.5, color: 'var(--ink-3)', marginLeft: 8 }}>
            no servidor, conferidos e <b>ainda não gravados</b>
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
          {filtros.map(f => (
            <Btn
              key={f.valor || 'todos'} tam="sm"
              variant={filtro === f.valor ? 'primary' : 'ghost'}
              onClick={() => setFiltro(f.valor)}
            >{f.rotulo}</Btn>
          ))}
        </div>
        {soma('invalidas') > 0 && (
          <Pill kind="danger">{soma('invalidas')} inválidos</Pill>
        )}
      </div>

      {erro && (
        <div style={{
          marginBottom: 11, padding: '9px 12px', borderRadius: 'var(--r-sm)', flex: 'none',
          background: 'var(--danger-soft)', color: 'var(--danger-ink)', fontSize: 12.5,
        }}>{erro}</div>
      )}

      {recusadas.length > 0 && (
        <div style={{
          display: 'flex', gap: 8, marginBottom: 11, padding: '9px 12px', flex: 'none',
          borderRadius: 'var(--r-sm)', background: 'var(--danger-soft)',
          color: 'var(--danger-ink)', fontSize: 12, lineHeight: 1.5,
        }}>
          <AlertTriangle size={15} style={{ flex: 'none', marginTop: 1 }} />
          <span>
            {recusadas.length} remessa(s) não chegaram ao servidor —{' '}
            {recusadas[0].erro} Os arquivos delas não estão na conta acima.
          </span>
        </div>
      )}

      {/* R19 — o atalho da remessa homogênea. Sem ele, trezentos arquivos da
          mesma disciplina custariam trezentas interações, e a correção linha a
          linha viraria um recurso que existe e ninguém usa. */}
      <div style={{ flex: 'none' }}>
        {editaveis.map(coluna => (
          <AplicarEmTodas
            key={coluna.campo}
            coluna={coluna}
            total={soma('total')}
            ocupado={ocupado}
            aoAplicar={(valor) => void corrigirTodas(coluna.campo, valor)}
          />
        ))}
      </div>

      {/* **A lista fica com toda a altura que sobrar** — `flex: 1` com
          `minHeight: 0`. Era `maxHeight: 400` fixo, e 400 px é a altura errada nas
          duas pontas: no monitor grande desperdiça meia tela, e na tela baixa
          espreme a lista contra um cabeçalho que não encolhe. */}
      <div
        ref={rolagem}
        style={{
          flex: 1, minHeight: 0, overflow: 'auto', overscrollBehavior: 'contain',
          border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
        }}
      >
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead>
            <tr>
              {['Situação', ...declaracao.colunas.map(c => c.rotulo), 'Observação']
                .map((titulo, i) => (
                  <th key={`${titulo}-${i}`} style={{
                    ...CAPS, padding: '8px 11px', textAlign: 'left', whiteSpace: 'nowrap',
                    borderBottom: '1px solid var(--line)', background: 'var(--surface-2)',
                    position: 'sticky', top: 0, zIndex: 1,
                  }}>{titulo}</th>
                ))}
            </tr>
          </thead>
          <tbody>
            {linhas.length === 0 ? (
              <tr>
                <td
                  colSpan={declaracao.colunas.length + 2}
                  style={{ padding: 24, textAlign: 'center', color: 'var(--ink-3)' }}
                >
                  Nenhum arquivo nesta situação.
                </td>
              </tr>
            ) : linhas.map(linha => (
              <LinhaArquivo
                key={linha.linha_id}
                linha={linha}
                colunas={declaracao.colunas}
                aoCorrigir={corrigir}
              />
            ))}
          </tbody>
        </table>
      </div>

      <div style={{
        display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap', flex: 'none',
        marginTop: 13, paddingTop: 13, borderTop: '1px solid var(--line)',
      }}>
        <span style={{ flex: 1, minWidth: 190, fontSize: 11.5, color: 'var(--ink-3)' }}>
          {ocupado
            ? `Aplicando remessa ${aplicando} de ${ids.length}…`
            : 'Arquivos inválidos nunca são gravados. Os repetidos já estão no acervo.'}
        </span>
        <Btn tam="sm" disabled={ocupado} onClick={onFechar}>Fechar sem decidir</Btn>
        <Btn tam="sm" variant="perigo" disabled={ocupado} onClick={() => decidir('descartar')}>
          <X size={13} />Negar tudo
        </Btn>
        <Btn
          tam="sm" variant="primary" disabled={ocupado || !soma('novas')}
          onClick={() => decidir('aplicar')}
        >
          {ocupado ? <Spinner size={13} /> : <CheckCheck size={13} />}
          Confirmar tudo ({soma('novas')})
        </Btn>
      </div>
    </div>
  )
}

function LinhaArquivo({ linha, colunas, aoCorrigir }: {
  linha: LinhaConferencia
  colunas: RecursoImpExp['colunas']
  aoCorrigir?: (linhaId: number, campo: string, valor: string) => void
}) {
  const celula = { padding: '6px 11px', borderBottom: '1px solid var(--line-2)' }

  /**
   * O corte vai num `<div>` dentro da célula, **não na célula**.
   *
   * `max-width` num `<td>` de tabela com `table-layout: auto` é conselho, não
   * regra: o algoritmo dimensiona a coluna pelo conteúdo e ignora o limite, e
   * com `white-space: nowrap` o `overflow: hidden` nunca chega a ter o que
   * cortar. Era o que fazia o hash — 64 caracteres — abrir uma coluna de ~440 px
   * e empurrar Código, Revisão e Observação para fora da tela, espremendo
   * justamente o nome do arquivo, que é o que a pessoa lê para decidir. Num
   * filho de bloco o limite vale, e a coluna passa a caber no que se pede.
   *
   * O valor inteiro continua no `title` da célula — o hash existe para conferir,
   * e conferir é passar o mouse ou copiar, não ler 64 caracteres na horizontal.
   */
  const corte = (largura: number) => ({
    maxWidth: largura, overflow: 'hidden', textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  })
  return (
    <tr style={{ opacity: linha.situacao === 'invalida' ? 0.72 : 1 }}>
      <td style={celula}>
        <Pill kind={KIND[linha.situacao]}>{NOME_SITUACAO[linha.situacao]}</Pill>
      </td>
      {colunas.map(coluna => {
        const valor = linha.valores[coluna.campo]
        const numerica = coluna.tipo === 'int' || coluna.tipo === 'Decimal'

        // **R19 — a célula que o recurso abriu.** Linha inválida não é editável:
        // ela não vai ser gravada de todo jeito, e oferecer a correção sugeriria
        // que corrigir o palpite conserta um arquivo que o motor recusou.
        if (coluna.editavel && aoCorrigir && linha.situacao !== 'invalida') {
          return (
            <td key={coluna.campo} style={{ ...celula, padding: '4px 8px', overflow: 'visible' }}>
              <CelulaEscolha
                coluna={coluna}
                valor={valor == null ? '' : String(valor)}
                aoMudar={(novo) => aoCorrigir(linha.linha_id, coluna.campo, novo)}
              />
            </td>
          )
        }

        return (
          <td
            key={coluna.campo}
            title={valor == null ? '' : String(valor)}
            style={{
              ...celula,
              ...(numerica || coluna.campo === 'hash' ? mono : {}),
              textAlign: numerica ? 'right' : 'left',
              color: valor == null || valor === '' ? 'var(--ink-3)' : 'var(--ink)',
            }}
          >
            {/* Larguras por natureza da coluna, não por nome: o hash é conferência
                (cabe o começo), o texto livre é leitura (cabe o nome do arquivo) e
                o número nunca é longo o bastante para precisar de corte. */}
            <div style={corte(coluna.campo === 'hash' ? 110 : numerica ? 140 : 300)}>
              {valor == null || valor === '' ? '—' : String(valor)}
            </div>
          </td>
        )
      })}
      <td style={{ ...celula, color: 'var(--ink-3)' }} title={linha.motivo || ''}>
        <div style={corte(240)}>{linha.motivo || '—'}</div>
      </td>
    </tr>
  )
}

/**
 * "Aplicar a todos" de uma coluna editável — a faixa acima da tabela.
 *
 * Reusa a própria `CelulaEscolha` como controle: o gesto de escolher é o mesmo
 * da linha, e dois controles diferentes para a mesma decisão fariam a pessoa
 * aprender duas vezes.
 */
function AplicarEmTodas({ coluna, total, ocupado, aoAplicar }: {
  coluna: RecursoImpExp['colunas'][number]
  total: number
  ocupado: boolean
  aoAplicar: (valor: string) => void
}) {
  const [valor, setValor] = useState('')

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap', marginBottom: 10,
      padding: '8px 11px', borderRadius: 'var(--r-sm)',
      background: 'var(--inset)', border: '1px solid var(--line)',
    }}>
      <span style={{ fontSize: 12, fontWeight: 650, color: 'var(--ink-2)' }}>
        {coluna.rotulo} de todos:
      </span>
      <div style={{ flex: '1 1 180px', minWidth: 0, maxWidth: 280 }}>
        <CelulaEscolha coluna={coluna} valor={valor} aoMudar={setValor} />
      </div>
      <Btn
        tam="sm"
        disabled={!valor || ocupado}
        onClick={() => aoAplicar(valor)}
        title={`Substitui ${coluna.rotulo.toLowerCase()} em todos os arquivos`}
      >
        <Wand2 size={13} /> Aplicar aos {total}
      </Btn>
      <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
        o palpite de cada arquivo continua editável na linha
      </span>
    </div>
  )
}

/**
 * A célula que se corrige — genérica, porque o motor não sabe o que é disciplina.
 *
 * Tudo o que ela conhece vem da declaração da coluna: as `opcoes` (com `cor`
 * opcional, que vira a bolinha) e o `multipla`, que decide se marcar acumula ou
 * troca. Sem `opcoes` é texto livre, e aí é um `<input>`.
 *
 * É um `<select>` nativo no caso simples e um painel de caixas no múltiplo: a
 * tabela já rola nos dois eixos, e um popover posicionado à mão dentro dela
 * brigaria com o `sticky` do cabeçalho. O nativo resolve o caso comum sem esse
 * custo, e o múltiplo abre **abaixo** da célula, dentro do fluxo.
 */
function CelulaEscolha({ coluna, valor, aoMudar }: {
  coluna: RecursoImpExp['colunas'][number]
  valor: string
  aoMudar: (valor: string) => void
}) {
  const [aberto, setAberto] = useState(false)
  const gatilho = useRef<HTMLDivElement>(null)
  const painel = useRef<HTMLDivElement>(null)
  const [lugar, setLugar] = useState<{ top: number; left: number; width: number } | null>(null)
  const opcoes = coluna.opcoes ?? null
  const marcados = valor ? valor.split(',').map(v => v.trim()).filter(Boolean) : []

  /**
   * O painel abre num **portal**, com coordenada `fixed` medida do gatilho.
   *
   * Aberto `position: absolute` dentro da célula, ele era filho do container que
   * rola — e isso custava três coisas de uma vez:
   *
   * 1. **Inventava rolagem vertical.** Os 240 px do painel entravam no
   *    `scrollHeight` da tabela, então abrir a disciplina fazia aparecer uma
   *    barra lateral que o conteúdo não pedia — foi o "o lateral só fica ativo
   *    quando disciplina tá aberto" que se relatou.
   * 2. **Era cortado** na borda do container, na linha de baixo.
   * 3. Obrigava ao véu de tela cheia para fechar no clique fora, e o véu (também
   *    `fixed`) engolia a roda em toda a tela.
   *
   * No `body` nada disso acontece: o painel não pertence a container nenhum, a
   * tabela volta a ter a rolagem que o conteúdo dela pede, e fechar no clique
   * fora vira um `mousedown` no documento — **sem** fechar na roda, que é o que
   * o dono pediu: com o ponteiro fora, rola o que está fora, e a escolha
   * continua aberta.
   *
   * É o mesmo desenho do seletor da Prancheta (`pages/Disciplinas.tsx`), que já
   * se comporta como esperado — e agora os dois têm a mesma explicação.
   */
  const posicionar = useCallback(() => {
    const r = gatilho.current?.getBoundingClientRect()
    if (!r) return
    const largura = Math.max(r.width, 210)
    const alturaEstimada = 250
    const paraCima = r.bottom + alturaEstimada > window.innerHeight && r.top > alturaEstimada
    setLugar({
      top: paraCima ? Math.max(8, r.top - alturaEstimada - 6) : r.bottom + 4,
      left: Math.min(Math.max(8, r.left), Math.max(8, window.innerWidth - largura - 8)),
      width: largura,
    })
  }, [])

  useLayoutEffect(() => { if (aberto) posicionar() }, [aberto, posicionar])

  useEffect(() => {
    if (!aberto) return
    const fora = (e: MouseEvent) => {
      const alvo = e.target as Node
      if (gatilho.current?.contains(alvo) || painel.current?.contains(alvo)) return
      setAberto(false)
    }
    const tecla = (e: KeyboardEvent) => { if (e.key === 'Escape') setAberto(false) }
    document.addEventListener('mousedown', fora)
    document.addEventListener('keydown', tecla)
    // Captura no `scroll`: a rolagem que move o gatilho é a da tabela, que não
    // borbulha até o `window`. Sem isto o painel ficaria parado no ar enquanto a
    // linha dele some — o preço de tirá-lo do fluxo, e o que o paga.
    window.addEventListener('scroll', posicionar, true)
    window.addEventListener('resize', posicionar)
    return () => {
      document.removeEventListener('mousedown', fora)
      document.removeEventListener('keydown', tecla)
      window.removeEventListener('scroll', posicionar, true)
      window.removeEventListener('resize', posicionar)
    }
  }, [aberto, posicionar])

  if (!opcoes) {
    return (
      <input
        defaultValue={valor}
        onBlur={(e) => { if (e.target.value !== valor) aoMudar(e.target.value) }}
        style={{
          width: '100%', minHeight: 30, padding: '2px 6px', fontSize: 12.5,
          color: 'var(--ink)', background: 'var(--surface)',
          border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
        }}
      />
    )
  }

  if (!coluna.multipla) {
    return (
      <select
        value={valor}
        onChange={(e) => aoMudar(e.target.value)}
        style={{
          width: '100%', minHeight: 30, padding: '2px 4px', fontSize: 12.5,
          color: 'var(--ink)', background: 'var(--surface)',
          border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
        }}
      >
        <option value="">—</option>
        {opcoes.map(o => <option key={o.valor} value={o.valor}>{o.rotulo}</option>)}
      </select>
    )
  }

  const rotulos = marcados
    .map(v => opcoes.find(o => o.valor === v)?.rotulo ?? v)
    .join(', ')

  return (
    <div ref={gatilho} style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={() => setAberto(a => !a)}
        title={rotulos}
        style={{
          display: 'flex', alignItems: 'center', gap: 6, width: '100%', minHeight: 30,
          padding: '2px 6px', cursor: 'pointer', textAlign: 'left', fontSize: 12.5,
          color: marcados.length ? 'var(--ink)' : 'var(--ink-3)', background: 'var(--surface)',
          border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
        }}
      >
        <span style={{ display: 'inline-flex', gap: 3, flex: 'none' }}>
          {marcados.slice(0, 3).map(v => {
            const cor = opcoes.find(o => o.valor === v)?.cor
            return cor ? (
              <span key={v} style={{ width: 9, height: 9, borderRadius: 3, background: cor, border: '1px solid rgba(0,0,0,.25)' }} />
            ) : null
          })}
        </span>
        <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {rotulos || 'escolher'}
        </span>
      </button>

      {aberto && lugar && createPortal(
        <div
          ref={painel}
          style={{
            position: 'fixed', top: lugar.top, left: lugar.left, minWidth: lugar.width,
            zIndex: 120, maxHeight: 240, overflowY: 'auto',
            // Com o ponteiro aqui dentro a roda é desta lista até o fim dela, e
            // não escorrega para a tabela atrás no último item.
            overscrollBehavior: 'contain', padding: 5,
            display: 'grid', gap: 2, borderRadius: 'var(--r-sm)',
            background: 'var(--surface)', border: '2px solid var(--line)',
            boxShadow: 'var(--shadow-lg)',
          }}
        >
            {opcoes.map(o => {
              const on = marcados.includes(o.valor)
              return (
                <button
                  key={o.valor}
                  type="button"
                  onClick={() => aoMudar(
                    (on ? marcados.filter(v => v !== o.valor) : [...marcados, o.valor]).join(','),
                  )}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 7, minHeight: 32, width: '100%',
                    padding: '0 8px', cursor: 'pointer', textAlign: 'left', border: 0,
                    borderRadius: 'var(--r-sm)', fontSize: 12.5, fontWeight: on ? 700 : 500,
                    background: on ? 'var(--inset)' : 'transparent', color: 'var(--ink)',
                  }}
                >
                  {o.cor && (
                    <span style={{ width: 11, height: 11, borderRadius: 3, background: o.cor, flex: 'none', border: '1px solid rgba(0,0,0,.25)' }} />
                  )}
                  <span style={{ flex: 1, minWidth: 0 }}>{o.rotulo}</span>
                  {on && <Check size={13} />}
                </button>
              )
            })}
        </div>,
        document.body,
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------

interface Recusa {
  detail?: string
  code?: string
  arquivo?: string
  arquivos?: string
}

/**
 * A frase do servidor, com o **nome do arquivo** quando ele o mandou.
 *
 * O 402 da porta identifica o culpado (`arquivo`), e sem isso a tela diria "o
 * plano não abre este formato" sobre dez arquivos, deixando a pessoa procurar
 * qual dos dez — que é a experiência que o campo `arquivo` existe para evitar.
 */
function mensagemDaRecusa(dados?: Recusa): string | undefined {
  if (!dados) return undefined
  const detalhe = dados.detail ?? dados.arquivos
  if (!detalhe) return undefined
  return dados.arquivo ? `${dados.arquivo}: ${detalhe}` : detalhe
}
