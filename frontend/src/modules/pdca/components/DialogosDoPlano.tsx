import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Btn, Modal, Pill } from '@/components/malha'
import {
  plano as planoApi, type LinhaImportada, type ResumoDoOrcamento,
} from '../api/montagemApi'
import { lerColagem, lerXmlDoProject, type Leitura } from '../importacao'
import { mensagemDe, type Montagem } from '../montagem'
import type { Atividade, Precedencia, TipoPrecedencia } from '../types'

const ESTILO_CAMPO = {
  fontSize: 12.5, padding: '5px 8px', background: 'var(--surface)', color: 'var(--ink)',
  border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
} as const

/* -- Colar do Excel / abrir o XML do MS Project --------------------------- */

export function DialogoDeImportacao(
  { cronogramaId, montagem, textoInicial, aoFechar }: {
    cronogramaId: number
    montagem: Montagem
    textoInicial?: string
    aoFechar: () => void
  },
) {
  const [texto, setTexto] = useState(textoInicial ?? '')
  const [arquivo, setArquivo] = useState<Leitura | null>(null)
  const [nomeArquivo, setNomeArquivo] = useState('')
  const [referencia, setReferencia] = useState<'codigo' | 'linha' | null>(null)
  const [resultado, setResultado] = useState<string | null>(null)
  const [avisos, setAvisos] = useState<string[]>([])
  const [erro, setErro] = useState<string | null>(null)

  const leitura: Leitura = useMemo(
    () => arquivo ?? lerColagem(texto),
    [arquivo, texto],
  )
  const ref = referencia ?? leitura.referencia
  const temPredecessoras = leitura.linhas.some((l) => l.predecessoras)

  async function abrirArquivo(f: File) {
    setErro(null)
    setNomeArquivo(f.name)
    const nome = f.name.toLowerCase()
    if (nome.endsWith('.mpp')) {
      setArquivo(null)
      setErro('O arquivo .mpp não abre fora do MS Project. No Project: Arquivo › Salvar como › XML, e traga o .xml.')
      return
    }
    const conteudo = await f.text()
    if (nome.endsWith('.xml')) setArquivo(lerXmlDoProject(conteudo))
    else {
      // CSV do Excel em português separa por ponto e vírgula.
      const tabulado = conteudo.includes('\t') ? conteudo : conteudo.replace(/;/g, '\t')
      setArquivo(null)
      setTexto(tabulado)
    }
  }

  async function trazer() {
    setErro(null)
    const linhas: LinhaImportada[] = leitura.linhas
    const r = await montagem.executar(() => planoApi.importarLinhas(cronogramaId, linhas, ref))
    if (r) {
      setResultado(`${r.criadas} linha(s) e ${r.ligacoes} ligação(ões) entraram no plano.`)
      setAvisos(r.avisos.concat(r.avisos_total > r.avisos.length ? [`… e mais ${r.avisos_total - r.avisos.length}.`] : []))
    } else {
      setErro(montagem.ultimoErro() ?? 'Não foi possível trazer as linhas.')
    }
  }

  return (
    <Modal
      titulo="Trazer linhas para o plano"
      onClose={aoFechar}
      largura={820}
      rodape={resultado ? (
        <Btn variant="primary" onClick={aoFechar}>Fechar</Btn>
      ) : (
        <>
          <Btn onClick={aoFechar}>Cancelar</Btn>
          <Btn variant="primary" onClick={trazer} disabled={montagem.ocupado || leitura.linhas.length === 0}>
            {montagem.ocupado ? 'Trazendo…' : `Trazer ${leitura.linhas.length} linha(s)`}
          </Btn>
        </>
      )}
    >
      {resultado ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 13.5, color: 'var(--good-ink)' }}>{resultado}</div>
          {avisos.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: 'var(--ink-2)' }}>
              {avisos.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>
            Cole aqui as linhas copiadas do Excel ou do MS Project (com ou sem cabeçalho), ou abra o
            arquivo <strong>.xml</strong> do Project (Arquivo › Salvar como › XML) ou um <strong>.csv</strong>.
            As colunas reconhecidas são: código/EAP, nível, nome, duração, predecessoras e início.
            O recuo do nome vira nível, e as linhas entram no fim do plano.
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <label style={{ ...ESTILO_CAMPO, cursor: 'pointer' }}>
              Abrir arquivo…
              <input
                type="file"
                accept=".xml,.csv,.txt,.tsv,.mpp"
                style={{ display: 'none' }}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void abrirArquivo(f) }}
              />
            </label>
            {nomeArquivo && <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>{nomeArquivo}</span>}
            {arquivo && <Btn tam="sm" onClick={() => { setArquivo(null); setNomeArquivo('') }}>Voltar para colar</Btn>}
          </div>
          {!arquivo && (
            <textarea
              autoFocus
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder={'1\tFundação\n1.1\tEstacas\t10\n1.2\tBlocos\t8\t1.1\n2\tEstrutura\n2.1\tPilares térreo\t5\t1.2FS+2'}
              rows={7}
              style={{ ...ESTILO_CAMPO, fontFamily: 'var(--mono)', fontSize: 12, resize: 'vertical' }}
            />
          )}
          {temPredecessoras && (
            <label style={{ fontSize: 12.5, display: 'flex', gap: 8, alignItems: 'center' }}>
              As predecessoras apontam para
              <select value={ref} onChange={(e) => setReferencia(e.target.value as 'codigo' | 'linha')} style={ESTILO_CAMPO}>
                <option value="codigo">o código da EAP (1.2, 2.3…)</option>
                <option value="linha">o número da linha (Id do MS Project)</option>
              </select>
            </label>
          )}
          {leitura.avisos.map((a, i) => <div key={i} style={{ fontSize: 12, color: 'var(--accent-ink)' }}>{a}</div>)}
          {erro && <div style={{ fontSize: 12.5, color: 'var(--danger-ink)' }}>{erro}</div>}
          {leitura.linhas.length > 0 && <Previa linhas={leitura.linhas} />}
        </div>
      )}
    </Modal>
  )
}

function Previa({ linhas }: { linhas: LinhaImportada[] }) {
  const mostrar = linhas.slice(0, 40)
  return (
    <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', maxHeight: 280, overflow: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: 'var(--surface-2)', textAlign: 'left' }}>
            {['#', 'Código', 'Nome', 'Dur.', 'Predecessoras', 'Início'].map((t) => (
              <th key={t} style={{ padding: '4px 8px', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-3)' }}>{t}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {mostrar.map((l, i) => (
            <tr key={i} style={{ borderTop: '1px solid var(--line-2)' }}>
              <td style={{ padding: '3px 8px', color: 'var(--ink-3)', fontFamily: 'var(--mono)' }}>{i + 1}</td>
              <td style={{ padding: '3px 8px', fontFamily: 'var(--mono)' }}>{l.codigo ?? ''}</td>
              <td style={{ padding: '3px 8px', paddingLeft: 8 + ((l.nivel ?? (l.codigo ? l.codigo.split('.').length : 1)) - 1) * 14 }}>
                {l.eh_marco ? '◆ ' : ''}{l.nome}
              </td>
              <td style={{ padding: '3px 8px', fontFamily: 'var(--mono)' }}>{l.duracao_dias ?? ''}</td>
              <td style={{ padding: '3px 8px', fontFamily: 'var(--mono)' }}>{l.predecessoras ?? ''}</td>
              <td style={{ padding: '3px 8px', fontFamily: 'var(--mono)' }}>{l.nao_comecar_antes_de ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {linhas.length > mostrar.length && (
        <div style={{ padding: '6px 8px', fontSize: 11.5, color: 'var(--ink-3)' }}>… e mais {linhas.length - mostrar.length} linhas.</div>
      )}
    </div>
  )
}

/* -- Do orçamento --------------------------------------------------------- */

export function DialogoDoOrcamento(
  { cronogramaId, montagem, aoFechar, aoGerar, orcamentoInicial }: {
    cronogramaId: number
    montagem: Montagem
    aoFechar: () => void
    /** Depois de gerar: a página pode encadear as etapas, se pedido. */
    aoGerar?: (encadear: boolean) => void
    /** Vindo do botão "Gerar o plano no PDCA" do cronograma do Orçamento. */
    orcamentoInicial?: number | null
  },
) {
  const { data: orcamentos, isLoading, error } = useQuery({
    queryKey: ['pdca', 'orcamentos-do-plano', cronogramaId],
    queryFn: () => planoApi.orcamentos(cronogramaId),
  })
  const [escolhido, setEscolhido] = useState<number | null>(orcamentoInicial ?? null)
  const [duracao, setDuracao] = useState('5')
  const [encadear, setEncadear] = useState(false)
  const [previa, setPrevia] = useState<ResumoDoOrcamento | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  useEffect(() => {
    if (escolhido == null && orcamentos?.length) {
      setEscolhido(orcamentos.find((o) => !o.ja_no_plano)?.orcamento_id ?? null)
    }
  }, [orcamentos, escolhido])

  useEffect(() => {
    if (escolhido == null) return
    setPrevia(null)
    setErro(null)
    planoApi.gerarDoOrcamento(cronogramaId, { orcamento: escolhido, simular: true })
      .then(setPrevia).catch((e) => setErro(mensagemDe(e)))
  }, [cronogramaId, escolhido])

  async function gerar() {
    if (escolhido == null) return
    setErro(null)
    const r = await montagem.executar(() => planoApi.gerarDoOrcamento(cronogramaId, {
      orcamento: escolhido,
      duracao_padrao: Math.max(1, Math.round(Number(duracao) || 1)),
    }))
    if (r) { aoGerar?.(encadear); aoFechar() } else setErro(montagem.ultimoErro())
  }

  return (
    <Modal
      titulo="Trazer as etapas do orçamento"
      onClose={aoFechar}
      largura={620}
      rodape={(
        <>
          <Btn onClick={aoFechar}>Cancelar</Btn>
          <Btn variant="primary" onClick={gerar} disabled={montagem.ocupado || escolhido == null || !previa}>
            {montagem.ocupado ? 'Gerando…' : previa ? `Trazer ${previa.linhas} etapa(s)` : 'Trazer'}
          </Btn>
        </>
      )}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>
          Do orçamento vêm as <strong>etapas</strong> do cronograma físico-financeiro: cada uma vira uma
          atividade com o início planejado lá, a duração em dias úteis deste expediente, o valor da etapa
          (que pesa o avanço financeiro) e o Hh orçado. O detalhe — serviços, frentes, sequência — você
          monta aqui, ligando ou não à planilha.
        </div>
        {isLoading && <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Procurando orçamentos da obra…</span>}
        {error && <span style={{ fontSize: 12.5, color: 'var(--danger-ink)' }}>{mensagemDe(error)}</span>}
        {orcamentos && orcamentos.length === 0 && (
          <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
            Esta obra ainda não tem orçamento. Monte-o no módulo Orçamento, ou comece o plano colando do Excel.
          </span>
        )}
        {orcamentos?.map((o) => (
          <label key={o.orcamento_id} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, opacity: o.ja_no_plano ? 0.55 : 1 }}>
            <input
              type="radio"
              name="orcamento"
              disabled={o.ja_no_plano}
              checked={escolhido === o.orcamento_id}
              onChange={() => setEscolhido(o.orcamento_id)}
            />
            <span style={{ flex: 1 }}>
              {o.descricao} <span style={{ color: 'var(--ink-3)' }}>v{o.versao} · {o.etapas_no_tempo} etapa(s) no tempo</span>
            </span>
            <Pill kind={o.status === 'aprovado' ? 'good' : 'slate'}>{o.ja_no_plano ? 'já no plano' : o.status_rotulo}</Pill>
          </label>
        ))}
        {orcamentos && orcamentos.length > 0 && (
          <>
            {previa && previa.sem_plano > 0 && (
              <label style={{ fontSize: 12.5, display: 'flex', gap: 6, alignItems: 'center' }}>
                Etapa ainda sem datas no Orçamento entra com
                <input value={duracao} onChange={(e) => setDuracao(e.target.value)} inputMode="numeric" style={{ ...ESTILO_CAMPO, width: 52, textAlign: 'right' }} />
                dias úteis
              </label>
            )}
            <label style={{ fontSize: 12.5, display: 'flex', gap: 6, alignItems: 'center' }}>
              <input type="checkbox" checked={encadear} onChange={(e) => setEncadear(e.target.checked)} />
              Encadear as etapas em sequência (ignora as datas planejadas no Orçamento)
            </label>
            {previa && (
              <div style={{ fontSize: 12.5, color: 'var(--ink-2)', background: 'var(--inset)', padding: '8px 10px', borderRadius: 'var(--r-sm)' }}>
                Vão entrar <strong>{previa.linhas}</strong> etapa(s) da v{previa.versao}:{' '}
                <strong>{previa.planejadas}</strong> com datas do cronograma do orçamento
                {previa.sem_plano > 0 && <>, <strong>{previa.sem_plano}</strong> ainda sem datas</>}.
              </div>
            )}
          </>
        )}
        {erro && <span style={{ fontSize: 12.5, color: 'var(--danger-ink)' }}>{erro}</span>}
      </div>
    </Modal>
  )
}

/** O "copia e avisa" (decisão do dono, 10/10/2026): o plano não muda sozinho
 *  quando o cronograma do orçamento muda — avisa, e o planejador decide trazer. */
export function AvisoDoOrcamento(
  { cronogramaId, montagem, editavel }: { cronogramaId: number; montagem: Montagem; editavel: boolean },
) {
  const { data: situacao, refetch } = useQuery({
    queryKey: ['pdca', 'situacao-do-orcamento', cronogramaId],
    queryFn: () => planoApi.situacaoDoOrcamento(cronogramaId),
  })
  const [resultado, setResultado] = useState<string | null>(null)
  if (!situacao?.mudou) {
    return resultado
      ? <div style={{ ...FAIXA, background: 'var(--good-soft)', color: 'var(--good-ink)' }}>{resultado}</div>
      : null
  }
  const motivo = situacao.motivo === 'nova_versao'
    ? `O orçamento ganhou a v${situacao.vigente_versao} (este plano veio da v${situacao.origem_versao}).`
    : `O cronograma do orçamento v${situacao.origem_versao} foi editado depois que as etapas vieram para cá.`

  async function atualizar() {
    const r = await montagem.executar(() => planoApi.atualizarDoOrcamento(cronogramaId, {
      orcamento: situacao?.atualizar_de ?? null,
    }))
    if (r) {
      const fora = r.fora_do_orcamento.length
      setResultado(
        `Etapas atualizadas da v${r.versao}: ${r.atualizadas} ajustada(s), ${r.criadas} nova(s)`
        + (fora ? ` · ${fora} etapa(s) do plano não estão mais no orçamento — decida se ficam.` : '.'),
      )
      void refetch()
    }
  }

  return (
    <div style={{ ...FAIXA, background: 'var(--accent-soft)', color: 'var(--accent-ink)' }}>
      <span style={{ flex: 1 }}>{motivo} Datas e valores das etapas podem ter mudado.</span>
      {situacao.pode_atualizar
        ? <Btn tam="sm" variant="primary" disabled={!!montagem.ocupado} onClick={atualizar}>Trazer a mudança</Btn>
        : editavel ? null : <span style={{ fontSize: 12 }}>Replaneje (versão nova do plano) para trazer.</span>}
    </div>
  )
}

const FAIXA = {
  display: 'flex', alignItems: 'center', gap: 12, padding: '8px 14px', fontSize: 12.5,
  borderRadius: 'var(--r-sm)', margin: '10px 22px 0',
} as const

/* -- Modelos -------------------------------------------------------------- */

export function DialogoDeModelo(
  { cronogramaId, montagem, ehModelo, nomeModelo, aoFechar }: {
    cronogramaId: number
    montagem: Montagem
    ehModelo: boolean
    nomeModelo: string | null
    aoFechar: () => void
  },
) {
  const [aba, setAba] = useState<'trazer' | 'salvar'>('trazer')
  const { data: modelos = [], isLoading } = useQuery({
    queryKey: ['pdca', 'modelos-de-plano'],
    queryFn: planoApi.modelos,
  })
  const [nome, setNome] = useState(nomeModelo ?? '')
  const [mensagem, setMensagem] = useState<string | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const outros = modelos.filter((m) => m.cronograma_id !== cronogramaId)

  async function trazer(modeloId: number) {
    setErro(null)
    const r = await montagem.executar(() => planoApi.anexarModelo(cronogramaId, modeloId))
    if (r) { setMensagem(`${r.criadas} linhas do modelo entraram no fim do plano.`) } else setErro(montagem.ultimoErro())
  }

  async function salvar() {
    setErro(null)
    const r = await montagem.executar(() => planoApi.marcarModelo(cronogramaId, nome.trim()), { recalcular: false })
    if (r) setMensagem(`Este plano agora é o modelo "${r.nome_modelo}" da empresa — dá para trazê-lo em outras obras.`)
    else setErro(montagem.ultimoErro())
  }

  return (
    <Modal titulo="Planos modelo" onClose={aoFechar} largura={600} rodape={<Btn onClick={aoFechar}>Fechar</Btn>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', gap: 4 }}>
          <Btn tam="sm" variant={aba === 'trazer' ? 'primary' : 'ghost'} onClick={() => { setAba('trazer'); setMensagem(null) }}>Trazer um modelo</Btn>
          <Btn tam="sm" variant={aba === 'salvar' ? 'primary' : 'ghost'} onClick={() => { setAba('salvar'); setMensagem(null) }}>Salvar este plano como modelo</Btn>
        </div>
        {mensagem && <div style={{ fontSize: 13, color: 'var(--good-ink)' }}>{mensagem}</div>}
        {erro && <div style={{ fontSize: 12.5, color: 'var(--danger-ink)' }}>{erro}</div>}
        {aba === 'trazer' ? (
          <>
            <div style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
              A estrutura, as durações e a sequência do modelo entram no fim deste plano. As datas
              saem do início e do expediente desta obra.
            </div>
            {isLoading && <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Carregando a biblioteca…</span>}
            {!isLoading && outros.length === 0 && (
              <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
                A biblioteca está vazia. Monte um plano e use "Salvar este plano como modelo".
              </span>
            )}
            {outros.map((m) => (
              <div key={m.cronograma_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: '1px solid var(--line-2)' }}>
                <span style={{ flex: 1, fontSize: 13 }}>
                  {m.nome_modelo}
                  <span style={{ color: 'var(--ink-3)', fontSize: 12 }}> · {m.atividades_count} linhas{m.obra_nome ? ` · de ${m.obra_nome}` : ''}</span>
                </span>
                <Btn tam="sm" onClick={() => trazer(m.cronograma_id)} disabled={montagem.ocupado}>Trazer</Btn>
              </div>
            ))}
          </>
        ) : (
          <>
            <div style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
              O modelo guarda a estrutura, as durações e a sequência deste plano, sem datas, locais nem
              itens de orçamento — esses são de cada obra.
            </div>
            <label style={{ fontSize: 12.5, display: 'flex', gap: 8, alignItems: 'center' }}>
              Nome do modelo
              <input autoFocus value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Torre residencial 12 pavimentos" style={{ ...ESTILO_CAMPO, flex: 1 }} />
            </label>
            <div>
              <Btn variant="primary" onClick={salvar} disabled={montagem.ocupado || nome.trim().length < 3}>
                {ehModelo ? 'Renomear o modelo' : 'Salvar como modelo'}
              </Btn>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}

/* -- Excluir — no diálogo do sistema, não no popup do navegador ------------ */

export function DialogoDeExclusao(
  { lista, montagem, precedencias, restricoesPorAtividade, obraSegue, aoConfirmar, aoFechar }: {
    lista: Atividade[]
    montagem: Montagem
    precedencias: Precedencia[]
    restricoesPorAtividade: Map<number, unknown[]>
    /** Este plano governa as etapas da obra (é o vigente, ou o primeiro rascunho). */
    obraSegue: boolean
    aoConfirmar: () => void
    aoFechar: () => void
  },
) {
  const todas = useMemo(() => {
    const ids = new Set<number>()
    for (const a of lista) for (const x of [a, ...montagem.descendentes(a)]) ids.add(x.atividade_id)
    return ids
  }, [lista, montagem])
  const dentro = todas.size - lista.length
  const ligacoes = precedencias.filter((p) => todas.has(p.origem) || todas.has(p.destino)).length
  const restricoes = [...todas].reduce((s, id) => s + (restricoesPorAtividade.get(id)?.length ?? 0), 0)
  const raizes = lista.filter((a) => a.pai == null && !a.eh_marco).length
  const titulo = lista.length === 1 ? `Excluir "${lista[0].nome}"?` : `Excluir ${lista.length} linhas?`

  return (
    <Modal
      titulo={titulo}
      onClose={aoFechar}
      largura={480}
      rodape={(
        <>
          <Btn onClick={aoFechar}>Cancelar</Btn>
          <Btn variant="perigo" autoFocus onClick={aoConfirmar}>Excluir</Btn>
        </>
      )}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.55 }}>
        {lista.length > 1 && (
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {lista.slice(0, 6).map((a) => (
              <li key={a.atividade_id}><span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-3)' }}>{a.codigo}</span> {a.nome}</li>
            ))}
            {lista.length > 6 && <li>… e mais {lista.length - 6}.</li>}
          </ul>
        )}
        <span>
          {dentro > 0 && <>Vão junto <strong>{dentro}</strong> atividade(s) que estão dentro. </>}
          {ligacoes > 0 && <>Saem <strong>{ligacoes}</strong> ligação(ões). </>}
          Dá para desfazer com <strong>Ctrl+Z</strong> até publicar o plano.
        </span>
        {raizes > 0 && (
          <span>
            {obraSegue
              ? <>{raizes === 1 ? 'A etapa sai' : `As ${raizes} etapas saem`} também das <strong>etapas da obra</strong> (vão para a lixeira e voltam com o desfazer).</>
              : <>As etapas da obra seguem a versão vigente: {raizes === 1 ? 'esta etapa sai' : 'estas etapas saem'} de lá quando este rascunho for publicado.</>}
          </span>
        )}
        {restricoes > 0 && (
          <span style={{ color: 'var(--accent-ink)' }}>
            {restricoes} restrição(ões) registrada(s) nessas linhas não voltam com o desfazer.
          </span>
        )}
      </div>
    </Modal>
  )
}

/* -- A seta clicada no Gantt ---------------------------------------------- */

export function EditorDeLigacao(
  { ligacao, ponto, atividades, montagem, editavel, aoFechar }: {
    ligacao: Precedencia
    ponto: { x: number; y: number }
    atividades: Atividade[]
    montagem: Montagem
    editavel: boolean
    aoFechar: () => void
  },
) {
  const [tipo, setTipo] = useState<TipoPrecedencia>(ligacao.tipo)
  const [atraso, setAtraso] = useState(String(ligacao.atraso_dias))
  const origem = atividades.find((a) => a.atividade_id === ligacao.origem)
  const destino = atividades.find((a) => a.atividade_id === ligacao.destino)

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') aoFechar()
      if (e.key === 'Delete' && editavel && !(e.target instanceof HTMLInputElement)) {
        void montagem.desligar(ligacao).then(aoFechar)
      }
    }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [aoFechar, editavel, ligacao, montagem])

  return (
    <div
      role="dialog"
      aria-label="Ligação"
      style={{
        position: 'fixed', left: Math.min(ponto.x + 8, window.innerWidth - 300), top: Math.min(ponto.y + 8, window.innerHeight - 200),
        zIndex: 60, width: 280, background: 'var(--surface)', border: '1px solid var(--line)',
        borderRadius: 'var(--r-md)', boxShadow: 'var(--shadow-lg)', padding: 12,
        display: 'flex', flexDirection: 'column', gap: 8,
      }}
    >
      <div style={{ fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.45 }}>
        <strong>{origem?.codigo}</strong> {origem?.nome}
        <br />→ <strong>{destino?.codigo}</strong> {destino?.nome}
      </div>
      {editavel ? (
        <>
          <div style={{ display: 'flex', gap: 6 }}>
            <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoPrecedencia)} style={{ ...ESTILO_CAMPO, flex: 1 }}>
              <option value="FS">termina → começa (FS)</option>
              <option value="SS">começa → começa (SS)</option>
              <option value="FF">termina → termina (FF)</option>
              <option value="SF">começa → termina (SF)</option>
            </select>
            <input value={atraso} onChange={(e) => setAtraso(e.target.value)} title="Defasagem em dias (negativo antecipa)" style={{ ...ESTILO_CAMPO, width: 50, textAlign: 'right' }} />
          </div>
          <div style={{ display: 'flex', gap: 6, justifyContent: 'space-between' }}>
            <Btn tam="sm" variant="perigo" onClick={async () => { await montagem.desligar(ligacao); aoFechar() }}>Desligar</Btn>
            <span style={{ display: 'flex', gap: 6 }}>
              <Btn tam="sm" onClick={aoFechar}>Fechar</Btn>
              <Btn
                tam="sm"
                variant="primary"
                onClick={async () => {
                  await montagem.alterarLigacao(ligacao, { tipo, atraso_dias: Math.round(Number(atraso.replace(',', '.')) || 0) })
                  aoFechar()
                }}
              >
                Salvar
              </Btn>
            </span>
          </div>
        </>
      ) : (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{ligacao.tipo}{ligacao.atraso_dias ? ` ${ligacao.atraso_dias > 0 ? '+' : ''}${ligacao.atraso_dias}d` : ''}</span>
          <Btn tam="sm" onClick={aoFechar}>Fechar</Btn>
        </div>
      )}
    </div>
  )
}
