import { useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, Check, CheckCheck, Download, FileDown, FileWarning, Upload, X,
} from 'lucide-react'

import { Btn } from '../Btn'
import { Modal } from '../Modal'
import { Pill } from '../Pill'
import { Spinner } from '../States'
import {
  aplicarImportacao, baixarModelo, baixarRecusadas, descartarImportacao, importar,
  marcarLinhas, remapearImportacao, salvarMapa,
} from './api'
import type {
  LinhaConferencia, PedidoDeDePara, RecursoImpExp, ResumoImportacao, SituacaoLinha,
} from './api'
import { useConferencia, useMapas, useRecurso } from './hooks'

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

type Passo = 'destino' | 'lendo' | 'de_para' | 'conferencia'

interface Props {
  recurso: string
  /**
   * Valores de destino (o `contexto_requerido` da declaração), já resolvidos
   * pela tela que hospeda o wizard — é ela que sabe qual banco/orçamento está
   * selecionado.
   */
  contexto?: Record<string, unknown>
  rotulo?: string
  tam?: 'sm' | 'md'
  onConcluida?: (resumo: ResumoImportacao) => void
}

/**
 * IE.0c — o Importar de todo módulo: upload → de-para → **conferência** → decisão.
 *
 * Promoção do `ConferenciaImportacao` do Orçamento (ORC.5b), generalizada: onde
 * lá havia colunas de preço fixas no JSX, aqui a tabela é montada das colunas
 * que o **recurso declarou**. A régua não mudou, e é ela que justifica a tela:
 * **nada foi gravado ainda** (R1). Um arquivo com coluna trocada que entra
 * inteiro só aparece semanas depois, como dado estranho no meio de algo já
 * aprovado, e aí ninguém sabe de onde veio.
 *
 * Some quando a pessoa não tem acesso total ao recurso, como o {@link BotaoExportar}.
 */
export function WizardImportacao({
  recurso, contexto, rotulo = 'Importar', tam = 'sm', onConcluida,
}: Props) {
  const { recurso: declaracao } = useRecurso(recurso)
  const [aberto, setAberto] = useState(false)
  const [passo, setPasso] = useState<Passo>('destino')
  const [importacaoId, setImportacaoId] = useState<number>()
  const [pedidoDePara, setPedidoDePara] = useState<PedidoDeDePara | null>(null)
  const [arquivo, setArquivo] = useState<File | null>(null)
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)

  if (!declaracao?.importa) return null

  function fechar() {
    setAberto(false)
    setPasso('destino')
    setImportacaoId(undefined)
    setPedidoDePara(null)
    setArquivo(null)
    setErro('')
  }

  async function enviar(escolhido: File, dePara?: Record<string, number>) {
    setErro('')
    setOcupado(true)
    setArquivo(escolhido)
    try {
      const resumo = await importar({ recurso, arquivo: escolhido, contexto, dePara })
      setImportacaoId(resumo.importacao_id)
      setPedidoDePara(null)
      setPasso(resumo.status === 'lendo' ? 'lendo' : 'conferencia')
    } catch (e) {
      const resposta = (e as { response?: { status?: number; data?: unknown } })?.response
      const dados = resposta?.data as (PedidoDeDePara & { detail?: string }) | undefined
      if (resposta?.status === 422 && dados?.code === 'colunas_nao_reconhecidas') {
        // R4 — o motor não adivinha: mostra o que viu e deixa o operador mapear.
        setPedidoDePara(dados)
        setPasso('de_para')
      } else {
        setErro(dados?.detail ?? 'Não foi possível ler este arquivo.')
      }
    } finally {
      setOcupado(false)
    }
  }

  return (
    <>
      <Btn tam={tam} onClick={() => setAberto(true)}>
        <Upload size={13} />{rotulo}
      </Btn>

      {aberto && (
        <Modal
          titulo={`Importar · ${declaracao.rotulo}`}
          largura={passo === 'conferencia' ? 940 : 620}
          onClose={fechar}
        >
          {erro && (
            <div style={{
              marginBottom: 13, padding: '9px 12px', borderRadius: 'var(--r-sm)',
              background: 'var(--danger-soft)', color: 'var(--danger-ink)', fontSize: 12.5,
            }}>{erro}</div>
          )}

          {passo === 'destino' && (
            <PassoArquivo
              declaracao={declaracao} recurso={recurso} ocupado={ocupado} onEnviar={enviar}
            />
          )}
          {passo === 'lendo' && (
            <PassoLendo
              id={importacaoId}
              onPronta={resumo => {
                // O job também pode parar pedindo o de-para (R4): o arquivo
                // grande é justamente o de origem mais estranha.
                if (resumo.aguarda_de_para) {
                  setPedidoDePara({
                    code: 'colunas_nao_reconhecidas',
                    detail: resumo.mensagem,
                    cabecalhos_vistos: resumo.cabecalhos_vistos,
                    obrigatorias: resumo.obrigatorias,
                    colunas: resumo.colunas_do_recurso,
                  })
                  setPasso('de_para')
                } else {
                  setPasso('conferencia')
                }
              }}
            />
          )}
          {passo === 'de_para' && pedidoDePara && (
            <PassoDePara
              pedido={pedidoDePara} recurso={recurso} ocupado={ocupado}
              onMapear={async mapa => {
                // Se o lote já existe (veio do job), o arquivo está guardado no
                // servidor: relê de lá em vez de pedir o upload de novo.
                if (importacaoId) {
                  setOcupado(true)
                  try {
                    await remapearImportacao(importacaoId, mapa)
                    setPedidoDePara(null)
                    setPasso('lendo')
                  } finally { setOcupado(false) }
                } else if (arquivo) {
                  enviar(arquivo, mapa)
                }
              }}
            />
          )}
          {passo === 'conferencia' && importacaoId && (
            <PassoConferencia
              id={importacaoId}
              declaracao={declaracao}
              onFechar={fechar}
              onConcluida={resumo => { onConcluida?.(resumo); fechar() }}
            />
          )}
        </Modal>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// 1. Arquivo (e o modelo, que é a R2 na mão do usuário)
// ---------------------------------------------------------------------------

function PassoArquivo({ declaracao, recurso, ocupado, onEnviar }: {
  declaracao: RecursoImpExp
  recurso: string
  ocupado: boolean
  onEnviar: (arquivo: File) => void
}) {
  const campo = useRef<HTMLInputElement>(null)
  const aceita = declaracao.formatos_entrada.map(f => `.${f}`).join(',')

  return (
    <div>
      <p style={{ margin: '0 0 14px', fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
        O arquivo é lido e conferido <b>linha a linha antes de gravar</b>. Você decide o que
        entra — nada é aplicado sem a sua confirmação.
      </p>

      <div
        onClick={() => campo.current?.click()}
        style={{
          display: 'grid', placeItems: 'center', gap: 9, padding: '30px 18px',
          border: '1px dashed var(--line)', borderRadius: 'var(--r-md)',
          background: 'var(--inset)', cursor: ocupado ? 'wait' : 'pointer', textAlign: 'center',
        }}
      >
        {ocupado ? <Spinner /> : <Upload size={24} style={{ color: 'var(--ink-3)' }} />}
        <span style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>
          {ocupado ? 'Lendo o arquivo…' : 'Escolher arquivo'}
        </span>
        <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
          Aceita {declaracao.formatos_entrada.join(', ').toUpperCase()}
        </span>
      </div>
      <input
        ref={campo} type="file" accept={aceita} style={{ display: 'none' }}
        onChange={e => { const f = e.target.files?.[0]; if (f) onEnviar(f); e.target.value = '' }}
      />

      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, marginTop: 15,
        paddingTop: 13, borderTop: '1px solid var(--line-2)', flexWrap: 'wrap',
      }}>
        <span style={{ flex: 1, minWidth: 220, fontSize: 11.5, color: 'var(--ink-3)' }}>
          Primeira vez? Baixe o modelo — é a mesma declaração que valida a importação, então o
          que sai daqui entra sem recusa.
        </span>
        <Btn tam="sm" onClick={() => baixarModelo(recurso)}>
          <FileDown size={13} />Baixar modelo
        </Btn>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 2. Job em andamento (R10)
// ---------------------------------------------------------------------------

function PassoLendo({ id, onPronta }: {
  id?: number
  onPronta: (resumo: ResumoImportacao) => void
}) {
  const { data } = useConferencia(id, '')
  if (data && data.status !== 'lendo') {
    // Sai do passo assim que o worker termina — inclusive para `erro`, que a
    // conferência sabe mostrar, e para o pedido de de-para da R4.
    queueMicrotask(() => onPronta(data))
  }
  const pct = data?.progresso ?? 0
  return (
    <div style={{ display: 'grid', gap: 13, padding: '10px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
        <Spinner size={18} />
        <div style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
          Arquivo grande — está sendo lido em segundo plano.
          <span style={{ display: 'block', color: 'var(--ink-3)', marginTop: 2 }}>
            {data?.processadas?.toLocaleString('pt-BR') ?? 0} linha(s) classificadas até agora.
          </span>
        </div>
      </div>
      <div style={{ height: 6, borderRadius: 999, background: 'var(--inset)', overflow: 'hidden' }}>
        <div style={{
          width: `${Math.max(pct, 4)}%`, height: '100%', background: 'var(--accent)',
          transition: 'width .4s',
        }} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 3. De-para manual (R4)
// ---------------------------------------------------------------------------

function PassoDePara({ pedido, recurso, ocupado, onMapear }: {
  pedido: PedidoDeDePara
  recurso: string
  ocupado: boolean
  onMapear: (mapa: Record<string, number>) => void
}) {
  const cabecalhos = pedido.cabecalhos_vistos[0] ?? []
  const [mapa, setMapa] = useState<Record<string, number>>({})
  const [nomeDoMapa, setNomeDoMapa] = useState('')
  const { data: salvos } = useMapas(recurso, true)

  const faltam = pedido.colunas.filter(c => c.obrigatoria && mapa[c.campo] === undefined)

  return (
    <div>
      <div style={{
        display: 'flex', gap: 9, padding: '10px 12px', marginBottom: 14,
        borderRadius: 'var(--r-sm)', background: 'var(--inset)', fontSize: 12.5,
        color: 'var(--ink-2)', lineHeight: 1.5,
      }}>
        <AlertTriangle size={15} style={{ flex: 'none', marginTop: 2, color: 'var(--ink-3)' }} />
        <span>
          Não reconheci as colunas deste arquivo — e prefiro perguntar a adivinhar.
          Diga qual coluna é cada campo.
        </span>
      </div>

      {!!salvos?.length && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ ...CAPS, marginBottom: 6 }}>Mapas salvos</div>
          <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>
            {salvos.map(m => (
              <Btn key={m.mapa_id} tam="sm" onClick={() => onMapear(m.mapa)}>{m.nome}</Btn>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gap: 9 }}>
        {pedido.colunas.map(coluna => (
          <label key={coluna.campo} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ flex: '0 0 40%', fontSize: 12.5, color: 'var(--ink)' }}>
              {coluna.rotulo}
              {coluna.obrigatoria && <b style={{ color: 'var(--danger-ink)' }}> *</b>}
            </span>
            <select
              value={mapa[coluna.campo] ?? ''}
              onChange={e => setMapa(m => {
                const proximo = { ...m }
                if (e.target.value === '') delete proximo[coluna.campo]
                else proximo[coluna.campo] = Number(e.target.value)
                return proximo
              })}
              style={{
                flex: 1, padding: '6px 10px', fontSize: 12.5, color: 'var(--ink)',
                background: 'var(--surface)', border: '1px solid var(--line)',
                borderRadius: 'var(--r-sm)',
              }}
            >
              <option value="">— não importar —</option>
              {cabecalhos.map((titulo, i) => (
                <option key={`${titulo}-${i}`} value={i}>
                  coluna {i + 1}: {titulo || '(sem título)'}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>

      <div style={{
        display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap',
        marginTop: 15, paddingTop: 13, borderTop: '1px solid var(--line-2)',
      }}>
        <input
          value={nomeDoMapa}
          onChange={e => setNomeDoMapa(e.target.value)}
          placeholder="Salvar este de-para como…"
          style={{
            flex: 1, minWidth: 190, padding: '6px 10px', fontSize: 12.5, color: 'var(--ink)',
            background: 'var(--surface)', border: '1px solid var(--line)',
            borderRadius: 'var(--r-sm)',
          }}
        />
        <Btn
          tam="sm"
          disabled={!nomeDoMapa.trim() || !Object.keys(mapa).length}
          onClick={() => salvarMapa(recurso, nomeDoMapa.trim(), mapa).then(() => setNomeDoMapa(''))}
        >
          Salvar mapa
        </Btn>
        <Btn
          tam="sm" variant="primary" disabled={ocupado || faltam.length > 0}
          onClick={() => onMapear(mapa)}
          title={faltam.length ? `Falta mapear: ${faltam.map(c => c.rotulo).join(', ')}` : undefined}
        >
          <Check size={13} />Conferir arquivo
        </Btn>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 4. Conferência — R1, o ponto do módulo inteiro
// ---------------------------------------------------------------------------

function PassoConferencia({ id, declaracao, onFechar, onConcluida }: {
  id: number
  declaracao: RecursoImpExp
  onFechar: () => void
  onConcluida: (resumo: ResumoImportacao) => void
}) {
  const [filtro, setFiltro] = useState<'' | SituacaoLinha>('')
  const [selecao, setSelecao] = useState<Set<number>>(new Set())
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)

  const { data, isLoading } = useConferencia(id, filtro)
  const linhas = useMemo(() => data?.linhas ?? [], [data])

  async function comErro(acao: () => Promise<void>) {
    setErro('')
    setOcupado(true)
    try { await acao() } catch (e) {
      const detalhe = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErro(detalhe ?? 'Não foi possível concluir a operação.')
    } finally { setOcupado(false) }
  }

  if (isLoading || !data) {
    return <div style={{ padding: 30, textAlign: 'center' }}><Spinner /></div>
  }

  if (data.status === 'erro') {
    return (
      <div>
        <div style={{
          display: 'flex', gap: 9, padding: '10px 12px', borderRadius: 'var(--r-sm)',
          background: 'var(--danger-soft)', color: 'var(--danger-ink)', fontSize: 12.5,
        }}>
          <FileWarning size={15} style={{ flex: 'none', marginTop: 2 }} />
          <span><b>{data.arquivo}</b> — {data.mensagem}</span>
        </div>
        <div style={{ marginTop: 13 }}><Btn onClick={onFechar}>Fechar</Btn></div>
      </div>
    )
  }

  const filtros: { valor: '' | SituacaoLinha; rotulo: string }[] = [
    { valor: '', rotulo: `Todas (${data.total})` },
    { valor: 'nova', rotulo: `Novas (${data.novas})` },
    { valor: 'duplicada', rotulo: `Já existem (${data.duplicadas})` },
    { valor: 'invalida', rotulo: `Inválidas (${data.invalidas})` },
  ]

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontSize: 13, fontWeight: 650, color: 'var(--ink)' }}>{data.arquivo}</div>
          <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
            {data.total} linhas lidas · <b>nada foi gravado ainda</b>
          </div>
        </div>
        <Pill kind="good">{data.novas} novas</Pill>
        <Pill kind="info">{data.duplicadas} já existem</Pill>
        <Pill kind="danger">{data.invalidas} inválidas</Pill>
      </div>

      {erro && (
        <div style={{
          marginBottom: 11, padding: '9px 12px', borderRadius: 'var(--r-sm)',
          background: 'var(--danger-soft)', color: 'var(--danger-ink)', fontSize: 12.5,
        }}>{erro}</div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap', marginBottom: 10 }}>
        {filtros.map(f => (
          <Btn
            key={f.valor || 'todas'} tam="sm"
            variant={filtro === f.valor ? 'primary' : 'ghost'}
            onClick={() => setFiltro(f.valor)}
          >{f.rotulo}</Btn>
        ))}
        <div style={{ flex: 1 }} />
        <span style={CAPS}>{selecao.size} selecionada(s)</span>
      </div>

      <div style={{
        maxHeight: 400, overflow: 'auto', border: '1px solid var(--line)',
        borderRadius: 'var(--r-sm)',
      }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead>
            <tr>
              {['', '#', 'Situação', ...declaracao.colunas.map(c => c.rotulo), 'Observação']
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
                  colSpan={declaracao.colunas.length + 4}
                  style={{ padding: 24, textAlign: 'center', color: 'var(--ink-3)' }}
                >
                  Nenhuma linha nesta situação.
                </td>
              </tr>
            ) : linhas.map(linha => (
              <LinhaTabela
                key={linha.linha_id}
                linha={linha}
                colunas={declaracao.colunas}
                marcada={selecao.has(linha.linha_id)}
                onAlternar={() => setSelecao(s => {
                  const p = new Set(s)
                  if (p.has(linha.linha_id)) p.delete(linha.linha_id); else p.add(linha.linha_id)
                  return p
                })}
              />
            ))}
          </tbody>
        </table>
      </div>

      <div style={{
        display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap',
        marginTop: 13, paddingTop: 13, borderTop: '1px solid var(--line)',
      }}>
        <span style={{ flex: 1, minWidth: 190, fontSize: 11.5, color: 'var(--ink-3)' }}>
          Linhas inválidas nunca são gravadas, mesmo se selecionadas.
        </span>
        {data.invalidas > 0 && (
          <Btn tam="sm" onClick={() => baixarRecusadas(id)}>
            <Download size={13} />Baixar recusadas
          </Btn>
        )}
        <Btn tam="sm" variant="perigo" disabled={ocupado} onClick={() => comErro(async () => {
          onConcluida(await descartarImportacao(id))
        })}>
          <X size={13} />Negar tudo
        </Btn>
        <Btn
          tam="sm" disabled={ocupado || selecao.size === 0}
          onClick={() => comErro(async () => {
            await marcarLinhas(id, false)
            await marcarLinhas(id, true, [...selecao])
            onConcluida(await aplicarImportacao(id))
          })}
        >
          <Check size={13} />Confirmar seleção ({selecao.size})
        </Btn>
        <Btn tam="sm" variant="primary" disabled={ocupado} onClick={() => comErro(async () => {
          await marcarLinhas(id, true)
          onConcluida(await aplicarImportacao(id))
        })}>
          <CheckCheck size={13} />Confirmar tudo
        </Btn>
      </div>
    </div>
  )
}

function LinhaTabela({ linha, colunas, marcada, onAlternar }: {
  linha: LinhaConferencia
  colunas: RecursoImpExp['colunas']
  marcada: boolean
  onAlternar: () => void
}) {
  const celula = {
    padding: '6px 11px', borderBottom: '1px solid var(--line-2)',
    maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const,
  }
  return (
    <tr
      onClick={onAlternar}
      style={{
        cursor: 'pointer',
        background: marcada ? 'var(--accent-soft)' : undefined,
        opacity: linha.situacao === 'invalida' ? 0.72 : 1,
      }}
    >
      <td style={celula}>
        <input type="checkbox" checked={marcada} readOnly style={{ accentColor: 'var(--accent)' }} />
      </td>
      <td style={{ ...celula, ...mono, color: 'var(--ink-3)' }}>{linha.numero}</td>
      <td style={celula}>
        <Pill kind={KIND[linha.situacao]}>{NOME_SITUACAO[linha.situacao]}</Pill>
      </td>
      {colunas.map(coluna => {
        const valor = linha.valores[coluna.campo]
        const numerica = coluna.tipo === 'Decimal' || coluna.tipo === 'int'
        return (
          <td
            key={coluna.campo}
            style={{
              ...celula,
              ...(numerica ? { ...mono, textAlign: 'right' } : {}),
              color: valor === '' || valor === null ? 'var(--ink-3)' : 'var(--ink)',
            }}
            title={String(valor ?? '')}
          >
            {valor === '' || valor === null ? '—' : String(valor)}
          </td>
        )
      })}
      <td style={{ ...celula, fontSize: 11.5, color: 'var(--ink-3)' }}>{linha.motivo}</td>
    </tr>
  )
}
