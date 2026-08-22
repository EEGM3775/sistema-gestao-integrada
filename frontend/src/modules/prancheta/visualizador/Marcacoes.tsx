import { useState } from 'react'
import type { ReactNode } from 'react'
import {
  Check, Hand, MapPin, MessageSquare, Move3d, Ruler, Square, Undo2, Upload, X,
} from 'lucide-react'
import { Btn, Modal, Pill, Spinner } from '@/components/malha'
import type { Marcacao, OrigemEscala, Ponto } from '../types'
import { corDaSituacao } from './marcar'
import type { Modo } from './marcar'
import { MINIMO_DE_PONTOS, rotuloDaMedida } from './marcar'

/**
 * A caixa de ferramentas e o painel de apontamentos do visualizador.
 *
 * Duas regras de tela que valem registro, porque são a diferença entre uma
 * ferramenta de escritório e uma de canteiro:
 *
 * 1. **Alvos grandes e poucos.** Cinco modos, botões de 46 px, rótulo visível a
 *    partir do tablet. Uma barra de dez ferramentas com ícone de 24 px é
 *    inutilizável de luva em cima de andaime — a régua é a mesma da PRA.2.
 * 2. **O que a pessoa não pode fazer não vira botão morto.** Sem
 *    `marcacao.edit`, os modos de marcar/medir não aparecem (a leitura continua
 *    inteira); sem `marcacao.resolver`, o botão de encerrar some em vez de
 *    aparecer e dar 403 — o 403 é a rede de segurança, não a interface.
 */

const FERRAMENTAS: { modo: Modo; rotulo: string; icone: ReactNode; dica: string }[] = [
  { modo: 'navegar', rotulo: 'Mover', icone: <Hand size={17} />, dica: 'Arrastar e ampliar a prancha' },
  { modo: 'marcar', rotulo: 'Marcar', icone: <MapPin size={17} />, dica: 'Apontar um problema no desenho' },
  { modo: 'distancia', rotulo: 'Medir', icone: <Ruler size={17} />, dica: 'Distância entre pontos' },
  { modo: 'area', rotulo: 'Área', icone: <Square size={17} />, dica: 'Área de um trecho' },
  { modo: 'calibrar', rotulo: 'Escala', icone: <Move3d size={17} />, dica: 'Definir a escala por uma cota conhecida' },
]

export function BarraDeModos({
  modo,
  aoTrocar,
  emCurso,
  aoDesfazer,
  aoConcluir,
  aoCancelar,
  escala,
  unidade,
  origem,
  podeMarcar,
  podeCalibrar,
  ocupado,
  snap,
  snapParcial,
  snapLigado,
  aoTrocarSnap,
}: {
  modo: Modo
  aoTrocar: (m: Modo) => void
  emCurso: Ponto[]
  aoDesfazer: () => void
  aoConcluir: () => void
  aoCancelar: () => void
  escala: number | null
  unidade: string
  origem: OrigemEscala
  podeMarcar: boolean
  podeCalibrar: boolean
  ocupado: boolean
  /** Esta folha tem índice de snap carregado (PRA.10). */
  snap: boolean
  /** O teto do plano cortou o índice: a mira existe, mas não em toda a prancha. */
  snapParcial: boolean
  /** A pessoa quer a mira agora? Existir e estar ligado são coisas diferentes. */
  snapLigado: boolean
  aoTrocarSnap: () => void
}) {
  const disponiveis = FERRAMENTAS.filter((f) => {
    if (f.modo === 'navegar') return true
    // "Escala" vira "Corrigir escala" quando o desenho já declarou a sua: o
    // gesto é o mesmo, mas a decisão é outra — substituir o que o arquivo diz,
    // e não preencher um vazio.
    if (f.modo === 'calibrar') return podeCalibrar
    return podeMarcar
  })
  const suficiente = emCurso.length >= MINIMO_DE_PONTOS[modo]
  const medindo = modo === 'distancia' || modo === 'area'

  return (
    <div
      style={{
        position: 'absolute', left: 12, top: 12, display: 'flex', flexDirection: 'column',
        gap: 8, alignItems: 'flex-start', zIndex: 2,
      }}
    >
      <div
        style={{
          display: 'flex', gap: 4, padding: 4, background: 'var(--glass)',
          backdropFilter: 'blur(14px)', border: '1px solid var(--line)',
          borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-sm)',
        }}
      >
        {disponiveis.map((f) => (
          <button
            key={f.modo}
            onClick={() => aoTrocar(f.modo)}
            title={f.modo === 'calibrar' ? dicaDaEscala(origem) : f.dica}
            aria-pressed={modo === f.modo}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer',
              minHeight: 46, padding: '0 12px', borderRadius: 'var(--r-sm)',
              border: '1px solid transparent', fontSize: 12.5, fontWeight: 650,
              background: modo === f.modo ? 'var(--accent)' : 'transparent',
              color: modo === f.modo ? 'var(--accent-ink)' : 'var(--ink-2)',
            }}
          >
            {f.icone}
            <span className="hidden md:inline">{f.rotulo}</span>
          </button>
        ))}
      </div>

      {/* Instrução do modo + o valor vivo. A instrução some no modo de navegar:
          "arraste para mover" é ruído para quem já está arrastando. */}
      {modo !== 'navegar' && (
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
            padding: '8px 12px', maxWidth: 340, background: 'var(--glass)',
            backdropFilter: 'blur(14px)', border: '1px solid var(--line)',
            borderRadius: 'var(--r-md)', fontSize: 12, color: 'var(--ink-2)',
          }}
        >
          <span>{instrucao(modo, emCurso.length, escala, origem)}</span>
          {/* **O estado do snap é dito, não deduzido.** Sem mira, quem conhece
              CAD conclui que a ferramenta é pior do que é; com mira parcial,
              conclui que ela está quebrada. As duas conclusões custam um
              chamado, e as duas são evitadas por uma palavra. */}
          {/* **O selo virou interruptor.** Ele já dizia o estado; passar a
              aceitar o clique custou uma linha e resolve o caso em que a mira
              atrapalha — apontar um lugar SEM vértice, o meio de um vão, um
              ponto no terreno. Alvo de 32 px e `aria-pressed` porque isto é um
              botão de dois estados, e no canteiro ele é apertado com luva. */}
          {snap && (
            <button
              onClick={aoTrocarSnap}
              aria-pressed={snapLigado}
              title={
                !snapLigado
                  ? 'A mira está desligada: o ponto marcado é o do dedo. Clique para ligar.'
                  : snapParcial
                    ? 'A prancha passou do teto de pontos do seu plano: a mira gruda '
                      + 'na maior parte do desenho, não em todo ele. Clique para desligar.'
                    : 'A mira gruda em extremidade, meio, centro e cruzamento. '
                      + 'Clique para desligar.'
              }
              style={{
                display: 'inline-flex', alignItems: 'center', minHeight: 32,
                padding: 0, border: 0, background: 'transparent', cursor: 'pointer',
              }}
            >
              <Pill kind={!snapLigado ? 'slate' : snapParcial ? 'accent' : 'good'}>
                {!snapLigado ? 'snap desligado' : snapParcial ? 'snap parcial' : 'snap'}
              </Pill>
            </button>
          )}
          {medindo && suficiente && (
            <strong className="num" style={{ color: 'var(--ink)' }}>
              {rotuloDaMedida(emCurso, modo, escala, unidade)}
            </strong>
          )}
          <span style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
            {emCurso.length > 0 && (
              <Btn tam="sm" onClick={aoDesfazer} title="Remover o último ponto">
                <Undo2 size={13} />
              </Btn>
            )}
            {suficiente && modo !== 'marcar' && (
              <Btn tam="sm" variant="primary" onClick={aoConcluir} disabled={ocupado}>
                {ocupado ? <Spinner /> : <Check size={13} />} Concluir
              </Btn>
            )}
            <Btn tam="sm" onClick={aoCancelar} title="Sair deste modo">
              <X size={13} />
            </Btn>
          </span>
        </div>
      )}
    </div>
  )
}

function dicaDaEscala(origem: OrigemEscala): string {
  if (origem === 'desenho') {
    return 'Corrigir a escala — o desenho já declara a dele, e conferir uma cota substitui essa leitura'
  }
  if (origem === 'calibrada') return 'Recalibrar a escala por outra cota conhecida'
  return 'Definir a escala por uma cota conhecida'
}

function instrucao(modo: Modo, colocados: number, escala: number | null, origem: OrigemEscala): string {
  if (modo === 'marcar') return 'Toque no ponto onde está o problema.'
  if (modo === 'calibrar') {
    return colocados < 2
      ? 'Trace sobre uma cota conhecida, de ponta a ponta.'
      : 'Agora informe quanto essa distância mede.'
  }
  /**
   * A frase muda com a procedência porque a confiança na medida muda junto.
   * "Escala do desenho" é o caso do CAD: veio do arquivo, é o mesmo metro do
   * AutoCAD. Sem escala, a tela avisa em vez de deixar o número parecer metro.
   */
  const semEscala = escala
    ? origem === 'desenho' ? ' Escala lida do desenho.' : ''
    : ' A prancha ainda não tem escala.'
  if (modo === 'area') {
    return colocados < 3 ? `Toque nos cantos do trecho.${semEscala}` : `Toque para continuar.${semEscala}`
  }
  return colocados < 2 ? `Toque nos dois extremos.${semEscala}` : `Toque para continuar.${semEscala}`
}

/**
 * A caixa de apontamentos: lista à direita, detalhe embaixo dela.
 *
 * É gaveta sobre a prancha e não uma coluna ao lado por causa do celular: no
 * canteiro a metade útil da tela é o desenho, e uma coluna fixa roubaria
 * justamente ela. Em tela larga a gaveta cabe sem cobrir o desenho todo.
 */
export function PainelMarcacoes({
  marcacoes,
  carregando,
  selecionada,
  aoSelecionar,
  aoComentar,
  aoMudarSituacao,
  aoImportarBcf,
  podeMarcar,
  podeResolver,
  aoFechar,
}: {
  marcacoes: Marcacao[]
  carregando: boolean
  selecionada: number | null
  aoSelecionar: (id: number | null) => void
  aoComentar: (id: number, texto: string) => Promise<unknown>
  aoMudarSituacao: (id: number, situacao: string) => Promise<unknown>
  /** Traz de volta o que o escritório respondeu. Vive AQUI, e não no cockpit,
   *  porque o BCF não diz a qual prancha nossa o tópico pertence — só esta tela
   *  sabe a revisão de destino, e adivinhá-la penduraria a marcação no desenho
   *  errado. */
  aoImportarBcf: (arquivo: File) => Promise<unknown>
  podeMarcar: boolean
  podeResolver: boolean
  aoFechar: () => void
}) {
  const atual = marcacoes.find((m) => m.marcacao_id === selecionada) ?? null

  return (
    <aside
      style={{
        position: 'absolute', right: 0, top: 0, bottom: 0, width: 'min(380px, 92vw)',
        display: 'flex', flexDirection: 'column', zIndex: 3,
        background: 'var(--surface)', borderLeft: '1px solid var(--line)',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      <header
        style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '12px 14px',
          borderBottom: '1px solid var(--line)', flex: 'none',
        }}
      >
        <strong style={{ fontFamily: 'var(--display)', fontSize: 14, color: 'var(--ink)' }}>
          Apontamentos
        </strong>
        <Pill kind="slate">{marcacoes.length}</Pill>
        <span style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
          {podeMarcar && <BotaoImportarBcf aoImportar={aoImportarBcf} />}
          <Btn
            onClick={aoFechar}
            aria-label="Fechar apontamentos"
            style={{ minHeight: 40, minWidth: 40, justifyContent: 'center' }}
          >
            <X size={16} />
          </Btn>
        </span>
      </header>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {carregando && (
          <p style={{ padding: 16, color: 'var(--ink-3)', fontSize: 13 }}>
            <Spinner /> Carregando…
          </p>
        )}

        {!carregando && marcacoes.length === 0 && (
          <p style={{ padding: 16, color: 'var(--ink-3)', fontSize: 13, lineHeight: 1.5 }}>
            Nenhum apontamento nesta prancha.
            {podeMarcar && ' Use “Marcar” e toque onde está o problema.'}
          </p>
        )}

        {marcacoes.map((m) => (
          <ItemMarcacao
            key={m.marcacao_id}
            marcacao={m}
            aberta={m.marcacao_id === selecionada}
            aoAbrir={() => aoSelecionar(m.marcacao_id === selecionada ? null : m.marcacao_id)}
          />
        ))}
      </div>

      {atual && (
        <Detalhe
          marcacao={atual}
          aoComentar={aoComentar}
          aoMudarSituacao={aoMudarSituacao}
          podeMarcar={podeMarcar}
          podeResolver={podeResolver}
        />
      )}
    </aside>
  )
}

/**
 * Sobe o `.bcfzip` que voltou do escritório.
 *
 * O resumo ("12 novas, 3 atualizadas") é o produto tanto quanto as linhas: é o
 * que diz a quem subiu se o arquivo era o que ele achava que era. Um "importado
 * com sucesso" genérico esconderia justamente o caso em que nada entrou porque o
 * projetista mandou o pacote errado.
 */
function BotaoImportarBcf({ aoImportar }: { aoImportar: (a: File) => Promise<unknown> }) {
  const [ocupado, setOcupado] = useState(false)
  const [erro, setErro] = useState('')

  const escolher = async (arquivo: File | undefined) => {
    if (!arquivo) return
    setOcupado(true)
    setErro('')
    try {
      await aoImportar(arquivo)
    } catch (e) {
      const resposta = (e as { response?: { status?: number; data?: { detail?: string } } }).response
      setErro(
        resposta?.status === 402
          ? 'A troca em BCF está no plano Profissional.'
          : resposta?.data?.detail || 'Não foi possível ler o arquivo.',
      )
    } finally {
      setOcupado(false)
    }
  }

  return (
    <label
      title="Importar marcações de um arquivo BCF do projetista"
      style={{ display: 'inline-flex' }}
    >
      <input
        type="file"
        accept=".bcf,.bcfzip"
        style={{ display: 'none' }}
        onChange={(e) => { void escolher(e.target.files?.[0]); e.target.value = '' }}
      />
      <span
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer',
          minHeight: 40, padding: '0 10px', fontSize: 12, fontWeight: 650,
          color: erro ? 'var(--danger-ink)' : 'var(--ink-2)',
          background: 'var(--surface)', border: '1px solid var(--line)',
          borderRadius: 'var(--r-sm)',
        }}
      >
        {ocupado ? <Spinner /> : <Upload size={14} />}
        <span className="hidden md:inline">{erro || 'BCF'}</span>
      </span>
    </label>
  )
}

function ItemMarcacao({
  marcacao, aberta, aoAbrir,
}: {
  marcacao: Marcacao
  aberta: boolean
  aoAbrir: () => void
}) {
  return (
    <button
      onClick={aoAbrir}
      style={{
        display: 'block', width: '100%', textAlign: 'left', cursor: 'pointer',
        padding: '11px 14px', minHeight: 60, border: 'none',
        borderBottom: '1px solid var(--line)',
        background: aberta ? 'var(--surface-2)' : 'transparent',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <Pill kind={corDaSituacao(marcacao.situacao)}>{marcacao.situacao_rotulo}</Pill>
        {marcacao.prioridade === 'Critical' && <Pill kind="danger">Crítica</Pill>}
        {marcacao.origem === 'bcf' && <Pill kind="net">BCF</Pill>}
        {/* Marcação viva sobre desenho que já não vale: é pergunta, não lixo. */}
        {marcacao.revisao_superada && marcacao.aberta && (
          <Pill kind="danger">revisão superada</Pill>
        )}
      </div>
      <p
        style={{
          margin: '5px 0 0', fontSize: 13.5, fontWeight: 620, color: 'var(--ink)',
          lineHeight: 1.35,
        }}
      >
        {marcacao.titulo}
      </p>
      <p style={{ margin: '3px 0 0', fontSize: 11.5, color: 'var(--ink-3)' }}>
        {marcacao.criado_por_nome}
        {marcacao.responsavel_nome && ` → ${marcacao.responsavel_nome}`}
        {marcacao.comentarios.length > 0 && ` · ${marcacao.comentarios.length} resposta(s)`}
      </p>
    </button>
  )
}

function Detalhe({
  marcacao, aoComentar, aoMudarSituacao, podeMarcar, podeResolver,
}: {
  marcacao: Marcacao
  aoComentar: (id: number, texto: string) => Promise<unknown>
  aoMudarSituacao: (id: number, situacao: string) => Promise<unknown>
  podeMarcar: boolean
  podeResolver: boolean
}) {
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)

  const enviar = async () => {
    if (!texto.trim()) return
    setEnviando(true)
    try {
      await aoComentar(marcacao.marcacao_id, texto.trim())
      setTexto('')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div
      style={{
        flex: 'none', maxHeight: '52%', overflowY: 'auto', padding: 14,
        borderTop: '2px solid var(--line)', background: 'var(--surface-2)',
      }}
    >
      {marcacao.descricao && (
        <p style={{ margin: '0 0 10px', fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.5 }}>
          {marcacao.descricao}
        </p>
      )}

      {marcacao.medicoes.length > 0 && (
        <p style={{ margin: '0 0 10px', fontSize: 12, color: 'var(--ink-2)' }}>
          {marcacao.medicoes.map((m) => (
            <span key={m.medicao_id} className="num" style={{ marginRight: 10 }}>
              {m.tipo_rotulo}: {m.valor.toFixed(2).replace('.', ',')} {m.unidade || '(sem escala)'}
            </span>
          ))}
        </p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
        {marcacao.comentarios.map((c) => (
          <div key={c.comentario_id} style={{ fontSize: 12.5, lineHeight: 1.45 }}>
            <strong style={{ color: 'var(--ink)' }}>{c.autor_nome}</strong>
            <span style={{ color: 'var(--ink-3)' }}> · {new Date(c.criado_em).toLocaleDateString('pt-BR')}</span>
            <p style={{ margin: '2px 0 0', color: 'var(--ink-2)' }}>{c.texto}</p>
          </div>
        ))}
      </div>

      {podeMarcar && (
        <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
          <input
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void enviar() }}
            placeholder="Responder…"
            style={{
              flex: 1, minHeight: 44, padding: '0 10px', fontSize: 13,
              background: 'var(--surface)', color: 'var(--ink)',
              border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
            }}
          />
          <Btn onClick={() => void enviar()} disabled={enviando || !texto.trim()} style={{ minHeight: 44 }}>
            {enviando ? <Spinner /> : <MessageSquare size={15} />}
          </Btn>
        </div>
      )}

      {/* Encerrar é verbo de alçada: sem a permissão o botão SOME, em vez de
          aparecer e dar 403. O 403 é a rede de segurança, não a interface. */}
      {podeResolver && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {marcacao.aberta ? (
            <>
              <Btn tam="sm" onClick={() => void aoMudarSituacao(marcacao.marcacao_id, 'In Progress')}>
                Em andamento
              </Btn>
              <Btn tam="sm" variant="primary"
                   onClick={() => void aoMudarSituacao(marcacao.marcacao_id, 'Resolved')}>
                <Check size={13} /> Resolvida
              </Btn>
            </>
          ) : (
            <Btn tam="sm" onClick={() => void aoMudarSituacao(marcacao.marcacao_id, 'Open')}>
              Reabrir
            </Btn>
          )}
        </div>
      )}
    </div>
  )
}

/** Formulário curto do apontamento novo — o mínimo que o BCF exige. */
export function DialogoNovaMarcacao({
  aoSalvar, aoCancelar, salvando,
}: {
  aoSalvar: (dados: { titulo: string; descricao: string; tipo: string; prioridade: string }) => void
  aoCancelar: () => void
  salvando: boolean
}) {
  const [titulo, setTitulo] = useState('')
  const [descricao, setDescricao] = useState('')
  const [tipo, setTipo] = useState('Issue')
  const [prioridade, setPrioridade] = useState('Normal')

  return (
    <Modal
      titulo="Novo apontamento"
      onClose={aoCancelar}
      rodape={
        <>
          <Btn onClick={aoCancelar}>Cancelar</Btn>
          <Btn
            variant="primary"
            disabled={!titulo.trim() || salvando}
            onClick={() => aoSalvar({ titulo: titulo.trim(), descricao, tipo, prioridade })}
          >
            {salvando ? <Spinner /> : <Check size={14} />} Registrar
          </Btn>
        </>
      }
    >
      <Campo rotulo="O que está errado">
        <input
          autoFocus
          value={titulo}
          onChange={(e) => setTitulo(e.target.value)}
          placeholder="Ex.: viga V12 encosta na alvenaria do eixo 3"
          style={entrada}
        />
      </Campo>
      <Campo rotulo="Detalhe (opcional)">
        <textarea
          value={descricao}
          onChange={(e) => setDescricao(e.target.value)}
          rows={3}
          style={{ ...entrada, minHeight: 72, padding: 10, resize: 'vertical' }}
        />
      </Campo>
      <div style={{ display: 'flex', gap: 10 }}>
        <Campo rotulo="Tipo">
          <select value={tipo} onChange={(e) => setTipo(e.target.value)} style={entrada}>
            <option value="Issue">Problema</option>
            <option value="Clash">Interferência</option>
            <option value="Request">Solicitação</option>
            <option value="Inquiry">Dúvida</option>
            <option value="Comment">Observação</option>
          </select>
        </Campo>
        <Campo rotulo="Prioridade">
          <select value={prioridade} onChange={(e) => setPrioridade(e.target.value)} style={entrada}>
            <option value="Low">Baixa</option>
            <option value="Normal">Normal</option>
            <option value="High">Alta</option>
            <option value="Critical">Crítica</option>
          </select>
        </Campo>
      </div>
      <p style={{ margin: '10px 0 0', fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
        O recorte da prancha vai junto — é ele que leva o apontamento para o
        software do projetista, porque o BCF não guarda ponto numa folha 2D.
      </p>
    </Modal>
  )
}

/** Pergunta quanto medem os dois pontos traçados. A régua da prancha sai daqui. */
export function DialogoCalibrar({
  aoSalvar, aoCancelar, salvando, origem,
}: {
  aoSalvar: (distancia: number, unidade: string) => void
  aoCancelar: () => void
  salvando: boolean
  origem: OrigemEscala
}) {
  const [valor, setValor] = useState('')
  const numero = Number(valor.replace(',', '.'))
  const valido = Number.isFinite(numero) && numero > 0

  return (
    <Modal
      titulo={origem === 'desenho' ? 'Corrigir a escala da prancha' : 'Definir a escala da prancha'}
      onClose={aoCancelar}
      largura={420}
      rodape={
        <>
          <Btn onClick={aoCancelar}>Cancelar</Btn>
          <Btn variant="primary" disabled={!valido || salvando} onClick={() => aoSalvar(numero, 'm')}>
            {salvando ? <Spinner /> : <Check size={14} />} Aplicar
          </Btn>
        </>
      }
    >
      <Campo rotulo="Quanto mede, em metros, a distância que você traçou?">
        <input
          autoFocus
          inputMode="decimal"
          value={valor}
          onChange={(e) => setValor(e.target.value)}
          placeholder="Ex.: 3,50"
          style={entrada}
        />
      </Campo>
      <p style={{ margin: '10px 0 0', fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
        {origem === 'desenho' && (
          <>
            Esta prancha já mede em metro pela unidade que o <strong>próprio
            desenho</strong> declara. Confirmar aqui substitui essa leitura pela
            sua, e a partir daí nenhuma reconversão volta a mexer nela.{' '}
          </>
        )}
        A escala vale para <strong>todas</strong> as medidas desta prancha. As
        medidas já tiradas <strong>não mudam</strong> — elas passam a aparecer
        marcadas como tiradas com outra régua.
      </p>
    </Modal>
  )
}

const entrada: React.CSSProperties = {
  width: '100%', minHeight: 44, padding: '0 10px', fontSize: 13.5,
  background: 'var(--surface-2)', color: 'var(--ink)',
  border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
}

function Campo({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <label style={{ display: 'block', marginBottom: 12, flex: 1 }}>
      <span
        style={{
          display: 'block', marginBottom: 5, fontSize: 11.5, fontWeight: 650,
          color: 'var(--ink-3)',
        }}
      >
        {rotulo}
      </span>
      {children}
    </label>
  )
}
