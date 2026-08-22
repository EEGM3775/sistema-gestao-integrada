import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  Building2, CheckCheck, DraftingCompass, FileWarning, Lock, Mic, Search, Sun, X,
} from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { useObras } from '@/modules/obras/hooks/useObras'
import { Btn, Card, Empty, Loading, Pill, Spinner } from '@/components/malha'
import { contemSemAcento } from '@/utils/texto'
import { useAcervo, usePublicarPendentes, useReprocessar } from '../hooks'
import {
  alternarFavorito, gravarMinhaObra, gravarModoSol, lerFavoritos, lerMinhaObra, lerModoSol,
  lerRecentes, porMaisVistas, registrarAbertura, type AberturaRecente,
} from '../preferencias'
import { usePapel } from '../visao'
import type { Documento } from '../types'
import { CartaoPrancha } from '../cartao'
import { Visualizador } from '../visualizador/Visualizador'
import { FiltroDeDisciplina } from './Disciplinas'
import { EnviarPranchas } from './EnviarPranchas'
import { useDitado } from './grade'

/**
 * Prancheta — **uma tela só**, e é o desenho inteiro do módulo.
 *
 * As seis abas (Início · Pranchas · Histórico · Acervo · Conversões · Formatos)
 * acabaram aqui, e não por economia: quatro delas eram o **mesmo** `useAcervo`
 * com filtros diferentes, e as outras duas falavam de uma prancha específica —
 * quem pergunta "quem mandou esta revisão?" está olhando para ela.
 *
 * Sobraram três gestos, que é o que existe de verdade no canteiro:
 *
 * 1. **achar a prancha** — esta grade, ordenada por favorita → mais aberta →
 *    resto, com busca por voz porque quem tem dificuldade de escrever
 *    "hidrossanitário" consegue falar;
 * 2. **olhar** — o visualizador de tela cheia, que não mudou;
 * 3. **pôr projeto novo dentro** — o único gesto que não é de nenhuma prancha, e
 *    por isso é um botão e não uma tela.
 *
 * **O encarregado e o engenheiro veem a mesma grade.** O que muda é o que ela
 * carrega: quem não governa o acervo não vê os chips de estado nem o botão de
 * envio, e **prancha que não abre nem aparece** — não é dele resolver. Quem
 * governa vê tudo, com o contador clicável que filtra a própria grade, no lugar
 * do cockpit que seria mais uma parada no caminho.
 */
const MODO_SOL: CSSProperties = {
  '--ground': '#FFFFFF', '--surface': '#FFFFFF', '--surface-2': '#FFFFFF', '--inset': '#FFFFFF',
  '--ink': '#000000', '--ink-2': '#000000', '--ink-3': '#333333',
  '--line': '#1A1A1A', '--line-2': '#1A1A1A',
  '--accent': '#8A4B00', '--accent-strong': '#7A3E00', '--accent-soft': '#FFEFCC', '--accent-ink': '#4A2900',
  '--good': '#0B6B4A', '--good-soft': '#D9F2E7', '--good-ink': '#04402C',
  '--info': '#0B4FA8', '--info-soft': '#DCE8FA', '--info-ink': '#0A3570',
  '--danger': '#A81F27', '--danger-soft': '#FADEDF', '--danger-ink': '#6E1319',
  '--net': '#04585F', '--net-soft': '#D6EDEF', '--net-ink': '#033A3F',
  '--glass': '#FFFFFF',
  '--shadow-sm': 'none', '--shadow-md': 'none', '--shadow-lg': '0 10px 30px rgba(0,0,0,.3)',
} as CSSProperties

/** O recorte que os chips de estado aplicam. `''` = a grade inteira. */
type Recorte = '' | 'nao_abrem' | 'sem_publicar'

let toastTimer: number | undefined

export default function PranchetaPage() {
  const { user, hasModule } = useAuth()
  const usuario = user?.id ?? 'anonimo'
  const temPrancheta = hasModule('prancheta')
  const papel = usePapel()

  const { data: obras, loading: carregandoObras } = useObras()
  const [obra, setObra] = useState<number | null>(null)
  const [trocandoObra, setTrocandoObra] = useState(false)

  const [busca, setBusca] = useState('')
  const [disciplina, setDisciplina] = useState('')
  const [recorte, setRecorte] = useState<Recorte>('')
  const [abertoId, setAbertoId] = useState<number | null>(null)
  const [toast, setToast] = useState('')

  const [favoritos, setFavoritos] = useState<number[]>([])
  const [recentes, setRecentes] = useState<AberturaRecente[]>([])
  const [modoSol, setModoSol] = useState(false)

  useEffect(() => {
    setFavoritos(lerFavoritos(usuario))
    setRecentes(lerRecentes(usuario))
    setModoSol(lerModoSol(usuario))
  }, [usuario])

  /** Qual obra abrir — a do aparelho, escolhida uma vez e lembrada. */
  useEffect(() => {
    if (obra !== null || !obras.length) return
    const daMemoria = lerMinhaObra(usuario)
    const valida = daMemoria && obras.some((o) => o.obra_id === daMemoria) ? daMemoria : null
    if (valida) setObra(valida)
    else if (papel.visao === 'responsavel') setObra(obras[0].obra_id)
  }, [obras, obra, usuario, papel.visao])

  const { data: acervo, isLoading, isError } = useAcervo(temPrancheta ? obra : null)
  const reprocessar = useReprocessar(obra)

  const say = (m: string) => {
    setToast(m)
    window.clearTimeout(toastTimer)
    toastTimer = window.setTimeout(() => setToast(''), 4200)
  }

  const escolherObra = (id: number) => {
    setObra(id)
    gravarMinhaObra(usuario, id)
    setTrocandoObra(false)
    setBusca('')
    setDisciplina('')
    setRecorte('')
  }

  const abrir = (documento: Documento) => {
    setAbertoId(documento.documento_id)
    setRecentes(registrarAbertura(usuario, {
      documento_id: documento.documento_id,
      obra: documento.obra,
      codigo: documento.codigo,
      titulo: documento.titulo,
      disciplina_rotulo: documento.disciplina_rotulo,
    }))
  }

  const favoritar = (documento: Documento) =>
    setFavoritos(alternarFavorito(usuario, documento.documento_id))

  /**
   * **Deduplicado por id**, e é obrigatório desde a PRA.9c: a prancha que é
   * arquitetura *e* elétrica aparece nos dois grupos do acervo — de propósito,
   * é o que "várias disciplinas" significa —, e um `flatMap` cru a mostraria
   * duas vezes na grade, com duas estrelas de favorito discordando entre si.
   */
  const todos = useMemo(() => {
    const porId = new Map<number, Documento>()
    for (const grupo of acervo?.disciplinas ?? []) {
      for (const documento of grupo.documentos) porId.set(documento.documento_id, documento)
    }
    return [...porId.values()]
  }, [acervo])

  /**
   * A ordem **é** a navegação — foi ela que substituiu as abas Início e Pranchas.
   *
   * Favorita primeiro (a planta baixa que se consulta o dia inteiro), depois o
   * que este aparelho mais abriu, depois o resto por código. Sem título de seção:
   * rola e acaba. Quem procura uma prancha que ainda não conhece usa a busca, que
   * é o caminho de exceção — e a estrela vai promovendo o uso real de cada um.
   */
  const ordenados = useMemo(() => {
    const posicaoRecente = new Map(
      porMaisVistas(recentes).map((r, i) => [r.documento_id, i]),
    )
    const peso = (d: Documento) => {
      if (favoritos.includes(d.documento_id)) return 0
      if (posicaoRecente.has(d.documento_id)) return 1
      return 2
    }
    return [...todos].sort((a, b) => {
      const pa = peso(a)
      const pb = peso(b)
      if (pa !== pb) return pa - pb
      if (pa === 1) {
        return (posicaoRecente.get(a.documento_id) ?? 0) - (posicaoRecente.get(b.documento_id) ?? 0)
      }
      return a.codigo.localeCompare(b.codigo, 'pt-BR', { numeric: true })
    })
  }, [todos, favoritos, recentes])

  /** O que **não abre** — e por isso não chega ao campo. */
  const naoAbrem = useMemo(
    () => todos.filter((d) => {
      const c = d.vigente?.conversao
      return c?.estado === 'erro' && !c.problema_no_arquivo
    }),
    [todos],
  )
  const semPublicar = useMemo(() => todos.filter((d) => !d.vigente && !!d.pendente), [todos])

  const visiveis = useMemo(() => {
    const termo = busca.trim()
    return ordenados.filter((d) => {
      // **A régua do campo:** prancha que não abre não entra na grade de quem
      // executa. Ele não tem verbo para resolvê-la, e um cartão com triângulo de
      // defeito no andaime só produz "o sistema não funciona".
      if (!papel.podeGerir && !d.vigente?.conversao.visualizador) return false
      // Casa **qualquer** disciplina da prancha, não só a principal: filtrar por
      // elétrica e esconder a planta de forro que também é elétrica seria o
      // mesmo que não ter classificado.
      if (disciplina && !(d.disciplinas ?? []).some((x) => x.codigo === disciplina)) return false
      if (recorte === 'nao_abrem' && !naoAbrem.includes(d)) return false
      if (recorte === 'sem_publicar' && !semPublicar.includes(d)) return false
      if (!termo) return true
      // Sem acento: a busca por voz do canteiro entrega "hidraulica" tanto
      // quanto "hidráulica", e o acervo tem as duas grafias (ver `utils/texto.ts`).
      return contemSemAcento(
        [d.codigo, d.titulo, d.disciplina_rotulo, d.projetista, d.etapa_nome ?? ''].join(' '),
        termo,
      )
    })
  }, [ordenados, busca, disciplina, recorte, naoAbrem, semPublicar, papel.podeGerir])

  /**
   * **O recorte não pode sobreviver ao que o criou** — foi o beco sem saída de
   * 14/08: publicar tudo zerava `semPublicar`, o chip sumia (a faixa some quando
   * as duas contagens são zero) e o `recorte` continuava `'sem_publicar'`. A grade
   * filtrava para nada, mostrando "Nenhuma prancha com esse recorte" **sem o botão
   * que a desligaria** — e a tela parecia travada num cache antigo.
   *
   * A lição é mais geral que o defeito: filtro cuja única forma de desligar é um
   * controle condicional precisa se desligar sozinho quando o controle sai. O
   * `Empty` abaixo ganhou o verbo pelo mesmo motivo — nenhuma tela deste módulo
   * deve terminar num aviso sem saída.
   */
  useEffect(() => {
    if (recorte === 'nao_abrem' && !naoAbrem.length) setRecorte('')
    if (recorte === 'sem_publicar' && !semPublicar.length) setRecorte('')
  }, [recorte, naoAbrem.length, semPublicar.length])

  const limparRecortes = () => { setBusca(''); setDisciplina(''); setRecorte('') }
  const filtrando = !!busca || !!disciplina || !!recorte

  /** Favoritas em seção própria — só quando nada está recortando a grade. */
  const separarFavoritos = !filtrando && favoritos.length > 0
  const favoritas = useMemo(
    () => (separarFavoritos ? visiveis.filter((d) => favoritos.includes(d.documento_id)) : []),
    [visiveis, favoritos, separarFavoritos],
  )
  const demais = useMemo(
    () => (separarFavoritos ? visiveis.filter((d) => !favoritos.includes(d.documento_id)) : visiveis),
    [visiveis, favoritos, separarFavoritos],
  )

  /** A fileira só oferece disciplina que TEM prancha aqui — filtrar por vazio dá tela vazia. */
  const gruposDeDisciplina = useMemo(
    () => (acervo?.disciplinas ?? [])
      .filter((g) => g.documentos.length)
      .map((g) => ({
        disciplina: g.disciplina,
        rotulo: g.rotulo ?? g.documentos[0]?.disciplina_rotulo ?? g.disciplina,
        cor: g.cor ?? g.documentos[0]?.disciplina_cor ?? 'var(--line)',
        total: g.documentos.length,
      })),
    [acervo],
  )

  const aberto = useMemo(
    () => (abertoId === null ? null : todos.find((d) => d.documento_id === abertoId) ?? null),
    [todos, abertoId],
  )
  const obraAtual = obras.find((o) => o.obra_id === obra)

  return (
    <div style={{ ...(modoSol ? MODO_SOL : {}), background: 'var(--ground)', minHeight: '100%' }}>
      <div style={{ maxWidth: 1180, margin: '0 auto', padding: '14px 14px 72px' }}>
        <header style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <div style={{ width: 40, height: 40, borderRadius: 'var(--r-md)', flex: 'none', display: 'grid', placeItems: 'center', background: 'var(--info-soft)', color: 'var(--info-ink)' }}>
            <DraftingCompass size={21} />
          </div>
          <div style={{ minWidth: 0 }}>
            <h1 style={{ fontFamily: 'var(--display)', fontSize: 20, fontWeight: 800, color: 'var(--ink)', lineHeight: 1.1 }}>
              Prancheta
            </h1>
            <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
              {papel.podeGerir ? 'o projeto das suas obras' : 'o projeto da sua obra'}
            </span>
          </div>

          <button
            onClick={() => { const v = !modoSol; setModoSol(v); gravarModoSol(usuario, v) }}
            aria-pressed={modoSol}
            title="Modo sol — contraste máximo para tela sob luz direta"
            style={{
              marginLeft: 'auto', minWidth: 48, minHeight: 48, display: 'grid', placeItems: 'center',
              borderRadius: 'var(--r-md)', cursor: 'pointer',
              border: `2px solid ${modoSol ? 'var(--accent-strong)' : 'var(--line)'}`,
              background: modoSol ? 'var(--accent-soft)' : 'var(--surface)',
              color: modoSol ? 'var(--accent-ink)' : 'var(--ink-3)',
            }}
          >
            <Sun size={20} />
          </button>
        </header>

        {!temPrancheta ? (
          <PranchetaBloqueada />
        ) : carregandoObras ? (
          <Loading o="as obras" />
        ) : !obras.length ? (
          <Empty>
            Nenhuma obra cadastrada — e o projeto pendura na obra. Comece em{' '}
            <Link to="/app/obras" style={{ color: 'var(--accent-ink)', fontWeight: 700 }}>Obras</Link>.
          </Empty>
        ) : obra === null || trocandoObra ? (
          <EscolhaDeObra
            obras={obras}
            gere={papel.podeGerir}
            atual={obra}
            onEscolher={escolherObra}
            onCancelar={obra !== null ? () => setTrocandoObra(false) : undefined}
          />
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
              <span
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 8, minHeight: 44, padding: '0 14px',
                  borderRadius: 999, background: 'var(--surface)', border: '2px solid var(--line)',
                  fontSize: 14, fontWeight: 700, color: 'var(--ink)', maxWidth: '100%',
                }}
              >
                <Building2 size={16} style={{ color: 'var(--ink-3)', flex: 'none' }} />
                <span className="truncate">{obraAtual?.nome_obra ?? `Obra ${obra}`}</span>
              </span>

              {papel.podeGerir ? (
                <Btn onClick={() => setTrocandoObra(true)} style={{ minHeight: 44 }}>Trocar de obra</Btn>
              ) : (
                <button
                  onClick={() => setTrocandoObra(true)}
                  style={{ background: 'none', border: 'none', padding: 0, fontSize: 12.5, color: 'var(--ink-3)', cursor: 'pointer', textDecoration: 'underline' }}
                >
                  não é esta a minha obra
                </button>
              )}

              {papel.podeGerir && obra !== null && (
                <span style={{ marginLeft: 'auto' }}>
                  <EnviarPranchas obra={obra} say={say} />
                </span>
              )}
            </div>

            <BuscaDePrancha valor={busca} aoMudar={setBusca} aoAvisar={say} />

            {acervo && (
              <FiltroDeDisciplina
                grupos={gruposDeDisciplina}
                escolhida={disciplina}
                aoEscolher={setDisciplina}
                podeGerir={papel.podeGerir}
              />
            )}

            {/* **O cockpit inteiro, em dois chips.** Contador clicável que filtra a
                própria grade — o número leva ao lugar em vez de contar de longe,
                que era o defeito das faixas de fila na antiga aba Início. */}
            {papel.podeGerir && !!acervo && (
              <ChipsDeEstado
                naoAbrem={naoAbrem.length}
                semPublicar={semPublicar.length}
                recorte={recorte}
                /**
                 * Ligar um chip **limpa disciplina e busca**, e não é conveniência:
                 * os contadores contam o acervo inteiro, e a grade cruzava os dois
                 * eixos — o chip dizia "4 esperando publicação" e a grade mostrava
                 * zero porque havia uma disciplina marcada. Pior: prancha recém-
                 * enviada entra em *Outra*, então era justamente o que acabou de
                 * subir que sumia. Um recorte de estado é uma pergunta diferente
                 * da de disciplina; ligá-lo troca de pergunta.
                 */
                aoRecortar={(r) => {
                  const proximo = r === recorte ? '' : r
                  setRecorte(proximo)
                  if (proximo) { setDisciplina(''); setBusca('') }
                }}
                obra={obra}
                podePublicar={papel.podePublicar}
                say={say}
              />
            )}

            {isLoading && <Loading o="as pranchas da obra" />}
            {isError && (
              <Empty>
                Não foi possível carregar as pranchas desta obra. Se persistir, confirme com o
                administrador se o seu usuário tem a permissão de leitura do projeto.
              </Empty>
            )}

            {/* **Vazio com verbo.** Um aviso sem saída, ocupando a tela, é um
                bloqueio com texto explicativo — foi assim que o recorte órfão
                pareceu travamento. Se há filtro, o botão o desfaz. */}
            {acervo && !visiveis.length && (
              <Empty>
                {filtrando ? (
                  <span style={{ display: 'grid', gap: 12, justifyItems: 'center' }}>
                    Nenhuma prancha com esse recorte.
                    <Btn variant="primary" onClick={limparRecortes} style={{ minHeight: 44 }}>
                      Ver todas as pranchas
                    </Btn>
                  </span>
                ) : papel.podeGerir
                  ? 'Nenhuma prancha nesta obra ainda — envie os arquivos do projeto para começar.'
                  : 'Nenhuma prancha publicada nesta obra ainda. Quem responde pelo acervo precisa publicá-las.'}
              </Empty>
            )}

            {acervo && !!favoritas.length && (
              <Secao titulo="Favoritas" sub="marcadas neste aparelho">
                <GradeDeCartoes
                  documentos={favoritas}
                  favoritos={favoritos}
                  onAbrir={abrir}
                  onFavoritar={favoritar}
                />
              </Secao>
            )}

            {acervo && !!demais.length && (
              separarFavoritos ? (
                <Secao titulo="Todas as pranchas" sub={`${demais.length} nesta obra`}>
                  <GradeDeCartoes
                    documentos={demais}
                    favoritos={favoritos}
                    onAbrir={abrir}
                    onFavoritar={favoritar}
                  />
                </Secao>
              ) : (
                <GradeDeCartoes
                  documentos={demais}
                  favoritos={favoritos}
                  onAbrir={abrir}
                  onFavoritar={favoritar}
                />
              )
            )}
          </>
        )}
      </div>

      {/* Abre a vigente quando existe; senão o rascunho — quem governa o acervo
          precisa ver o que subiu **antes** de decidir publicá-lo, e era isso que
          obrigava a ir à aba Acervo só para conferir um desenho. */}
      {aberto && (aberto.vigente ?? aberto.pendente) && (
        <Visualizador
          documento={aberto}
          revisao={(aberto.vigente ?? aberto.pendente)!}
          onFechar={() => setAbertoId(null)}
          podeReprocessar={papel.podeReprocessar}
          say={say}
          onReprocessar={() =>
            reprocessar.mutate((aberto.vigente ?? aberto.pendente)!.revisao_id, {
              onSuccess: (d) => { say(d.detail); setAbertoId(null) },
              onError: () => say('Nenhum motor do seu plano converte este formato.'),
            })
          }
        />
      )}

      {toast && (
        <div
          role="status"
          style={{
            position: 'fixed', bottom: 20, left: '50%', transform: 'translateX(-50%)', zIndex: 96,
            padding: '13px 18px', borderRadius: 'var(--r-md)', background: 'var(--surface)',
            border: '2px solid var(--line)', boxShadow: 'var(--shadow-lg)', fontSize: 14,
            color: 'var(--ink)', maxWidth: 'min(94vw, 560px)',
          }}
        >
          {toast}
        </div>
      )}
    </div>
  )
}

/**
 * A busca, com **ditado**.
 *
 * O microfone não é enfeite: o encarregado que não escreve "hidrossanitário"
 * consegue dizê-lo, e é a diferença entre achar a prancha e desistir dela. Só
 * aparece onde o navegador suporta (`useDitado`) — botão que não funciona é pior
 * do que botão que não existe, ainda mais para quem não vai ler o motivo.
 */
function BuscaDePrancha({
  valor, aoMudar, aoAvisar,
}: {
  valor: string
  aoMudar: (v: string) => void
  aoAvisar: (m: string) => void
}) {
  const ditado = useDitado((texto) => aoMudar(texto), aoAvisar)

  return (
    <div style={{ position: 'relative', marginBottom: 12 }}>
      <Search
        size={19}
        style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--ink-3)' }}
      />
      <input
        value={valor}
        onChange={(e) => aoMudar(e.target.value)}
        placeholder="Buscar prancha"
        inputMode="search"
        style={{
          width: '100%', minHeight: 54, paddingLeft: 44,
          paddingRight: (valor ? 48 : 0) + (ditado.suportado ? 52 : 8),
          borderRadius: 'var(--r-md)', border: '2px solid var(--line)',
          background: 'var(--surface)', color: 'var(--ink)', fontSize: 16, fontWeight: 500,
        }}
      />
      <span style={{ position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)', display: 'flex' }}>
        {valor && (
          <button
            onClick={() => aoMudar('')}
            aria-label="Limpar busca"
            style={{ width: 44, height: 44, display: 'grid', placeItems: 'center', cursor: 'pointer', background: 'none', border: 'none', color: 'var(--ink-3)' }}
          >
            <X size={20} />
          </button>
        )}
        {ditado.suportado && (
          <button
            onClick={ditado.alternar}
            aria-label="Buscar falando"
            title="Buscar falando"
            aria-pressed={ditado.ouvindo}
            style={{
              width: 44, height: 44, display: 'grid', placeItems: 'center', cursor: 'pointer',
              borderRadius: 'var(--r-sm)', border: 'none',
              background: ditado.ouvindo ? 'var(--danger-soft)' : 'transparent',
              color: ditado.ouvindo ? 'var(--danger-ink)' : 'var(--ink-3)',
            }}
          >
            <Mic size={20} />
          </button>
        )}
      </span>
    </div>
  )
}

/** Seção com título — só existe quando há mais de um grupo a separar. */
function Secao({ titulo, sub, children }: { titulo: string; sub?: string; children: ReactNode }) {
  return (
    <section style={{ display: 'grid', gap: 12, marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 17, fontWeight: 800, color: 'var(--ink)', letterSpacing: '-0.015em' }}>
          {titulo}
        </h2>
        {sub && <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>· {sub}</span>}
      </div>
      {children}
    </section>
  )
}

function GradeDeCartoes({
  documentos, favoritos, onAbrir, onFavoritar,
}: {
  documentos: Documento[]
  favoritos: number[]
  onAbrir: (d: Documento) => void
  onFavoritar: (d: Documento) => void
}) {
  return (
    <div style={{ display: 'grid', gap: 14, gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
      {documentos.map((d) => (
        <CartaoPrancha
          key={d.documento_id}
          documento={d}
          favorito={favoritos.includes(d.documento_id)}
          onAbrir={onAbrir}
          onFavoritar={onFavoritar}
        />
      ))}
    </div>
  )
}

/** Os dois números que dizem o que está travando o campo — e filtram a grade. */
function ChipsDeEstado({
  naoAbrem, semPublicar, recorte, aoRecortar, obra, podePublicar, say,
}: {
  naoAbrem: number
  semPublicar: number
  recorte: Recorte
  aoRecortar: (r: Recorte) => void
  obra: number
  podePublicar: boolean
  say: (m: string) => void
}) {
  const publicarPendentes = usePublicarPendentes(obra)
  if (!naoAbrem && !semPublicar) return null

  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
      {!!naoAbrem && (
        <ChipEstado
          on={recorte === 'nao_abrem'}
          onClick={() => aoRecortar('nao_abrem')}
          icone={<FileWarning size={15} />}
          tom="danger"
        >
          {naoAbrem} não abre{naoAbrem > 1 ? 'm' : ''}
        </ChipEstado>
      )}
      {!!semPublicar && (
        <>
          <ChipEstado
            on={recorte === 'sem_publicar'}
            onClick={() => aoRecortar('sem_publicar')}
            icone={<CheckCheck size={15} />}
            tom="accent"
          >
            {semPublicar} esperando publicação
          </ChipEstado>
          {podePublicar && (
            <Btn
              variant="primary"
              disabled={publicarPendentes.isPending}
              onClick={() => publicarPendentes.mutate(undefined, {
                onSuccess: (r) => say(
                  r.publicadas
                    ? `${r.publicadas} prancha${r.publicadas > 1 ? 's' : ''} publicada${r.publicadas > 1 ? 's' : ''} — já abre${r.publicadas > 1 ? 'm' : ''} no canteiro.`
                    : 'Nenhuma revisão em rascunho para publicar.',
                ),
                onError: () => say('Não foi possível publicar agora.'),
              })}
              style={{ minHeight: 44 }}
            >
              {publicarPendentes.isPending ? <Spinner /> : <CheckCheck size={15} />}
              Publicar todas
            </Btn>
          )}
        </>
      )}
    </div>
  )
}

function ChipEstado({
  on, onClick, icone, tom, children,
}: {
  on: boolean
  onClick: () => void
  icone: React.ReactNode
  tom: 'danger' | 'accent'
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={on}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 8, minHeight: 44, padding: '0 14px',
        cursor: 'pointer', borderRadius: 999, fontSize: 13.5, fontWeight: 700,
        border: `2px solid ${on ? `var(--${tom}-ink)` : `var(--${tom})`}`,
        background: on ? `var(--${tom}-soft)` : 'var(--surface)',
        color: `var(--${tom}-ink)`,
      }}
    >
      {icone}{children}
    </button>
  )
}

/** A escolha da obra — tela cheia, botões grandes, uma decisão por vez. */
function EscolhaDeObra({
  obras, gere, atual, onEscolher, onCancelar,
}: {
  obras: { obra_id: number; nome_obra: string; endereco: string }[]
  gere: boolean
  atual: number | null
  onEscolher: (id: number) => void
  onCancelar?: () => void
}) {
  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <div>
        <h2 style={{ fontFamily: 'var(--display)', fontSize: 19, fontWeight: 800, color: 'var(--ink)' }}>
          {gere ? 'Escolha a obra' : 'Em qual obra você está?'}
        </h2>
        <p style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 4, maxWidth: 560, lineHeight: 1.5 }}>
          {gere
            ? 'Você responde pelos empreendimentos, então pode alternar quando quiser.'
            : 'A Prancheta vai mostrar só o projeto desta obra, para não misturar material de outra. Este aparelho lembra a escolha.'}
        </p>
      </div>

      <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
        {obras.map((o) => (
          <button
            key={o.obra_id}
            onClick={() => onEscolher(o.obra_id)}
            style={{
              minHeight: 82, padding: '14px 16px', textAlign: 'left', cursor: 'pointer',
              borderRadius: 'var(--r-md)', background: 'var(--surface)',
              border: `2px solid ${o.obra_id === atual ? 'var(--accent-strong)' : 'var(--line)'}`,
              display: 'grid', gap: 4, alignContent: 'center',
            }}
          >
            <strong style={{ fontSize: 15.5, fontWeight: 700, color: 'var(--ink)' }}>{o.nome_obra}</strong>
            <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>{o.endereco}</span>
          </button>
        ))}
      </div>

      {onCancelar && <Btn onClick={onCancelar} style={{ minHeight: 48, justifyContent: 'center' }}>Cancelar</Btn>}
    </div>
  )
}

/**
 * Sem o entitlement, a tela **explica o módulo** em vez de dar 403 — a rota fica
 * aberta de propósito (docs/frontend.md §3.2). Nada aqui é promessa: cada linha
 * descreve o que já roda hoje para quem assina.
 */
function PranchetaBloqueada() {
  return (
    <Card style={{ display: 'grid', gap: 14, padding: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Lock size={18} style={{ color: 'var(--ink-3)' }} />
        <strong style={{ fontFamily: 'var(--display)', fontSize: 17, color: 'var(--ink)' }}>
          A Prancheta não está no seu plano
        </strong>
      </div>
      <p style={{ fontSize: 14, color: 'var(--ink-2)', lineHeight: 1.6, maxWidth: 680 }}>
        É o projeto da obra aberto <strong>no celular, em campo</strong>, sem depender de alguém
        exportar PDF: o arquivo do projetista sobe como veio — DWG, DXF, IFC, PDF — e o servidor o
        converte para uma prancha que abre no navegador. Cada entrega é uma <strong>revisão</strong>,
        e só uma fica vigente: é ela que o canteiro executa.
      </p>
      <ul style={{ display: 'grid', gap: 8, fontSize: 13.5, color: 'var(--ink-2)', paddingLeft: 18, listStyle: 'disc' }}>
        <li>Uma grade de miniaturas: favoritas primeiro, busca por voz, feita para tela ao sol.</li>
        <li>DWG e DXF viram desenho vetorial; IFC vira modelo 3D navegável.</li>
        <li>O arquivo cria a prancha — arrastar o projeto para dentro é o cadastro.</li>
        <li>Publicar é ato com alçada própria — quem executa não decide qual desenho vale.</li>
        <li>Cada entrega guarda quem enviou, quem publicou e quando.</li>
      </ul>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <Pill kind="slate">entitlement <code>prancheta</code></Pill>
        <Link to="/app/dashboard"><Btn>Voltar ao início</Btn></Link>
      </div>
    </Card>
  )
}
