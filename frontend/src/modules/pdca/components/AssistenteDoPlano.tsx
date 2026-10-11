import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, ArrowRight, Calculator, ClipboardPaste, FileSpreadsheet, LayoutTemplate, ListTree, Plus, Trash2,
} from 'lucide-react'
import { Btn, Card, Pill } from '@/components/malha'
import { maxCalendarioISO, minCalendarioISO } from '@/utils/dates'
import * as api from '../api/pdcaApi'
import {
  etapasDaObra, nomeLivre, plano as planoApi, type LinhaImportada,
} from '../api/montagemApi'
import { pdcaKeys } from '../api/queryKeys'
import { useCalendarios } from '../hooks'
import { mensagemDe } from '../montagem'
import { FormularioDeExpediente } from './PainelCalendario'

export type Origem = 'zero' | 'orcamento' | 'modelo' | 'colar'

/** O que fazer quando o plano existir: abrir o diálogo do orçamento ou o de
 *  colar, que precisam do cronograma já criado. */
export type Seguimento = 'orcamento' | 'colar' | null

interface EtapaRascunho {
  nome: string
  atividades: { nome: string; duracao: string }[]
}

const SUGESTOES = [
  'Serviços preliminares', 'Fundação', 'Estrutura', 'Alvenaria', 'Instalações',
  'Cobertura', 'Revestimentos', 'Esquadrias', 'Pintura', 'Limpeza e entrega',
]

const ESTILO_CAMPO = {
  fontSize: 13, padding: '6px 9px', background: 'var(--surface)', color: 'var(--ink)',
  border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
} as const

/** O caminho guiado para o primeiro plano da obra — para quem não quer começar
 *  por uma planilha em branco. Termina na grade completa, onde tudo se ajusta. */
export function AssistenteDoPlano(
  { obraId, aoConcluir }: { obraId: number; aoConcluir: (seguimento: Seguimento) => void },
) {
  const qc = useQueryClient()
  const { data: calendarios = [], isLoading: carregandoCal } = useCalendarios(obraId)
  const { data: modelos = [] } = useQuery({ queryKey: ['pdca', 'modelos-de-plano'], queryFn: planoApi.modelos })

  const [passo, setPasso] = useState(0)
  const [inicio, setInicio] = useState(() => new Date().toISOString().slice(0, 10))
  const [calendario, setCalendario] = useState<number | null>(null)
  const [criandoCal, setCriandoCal] = useState(false)
  const [origem, setOrigem] = useState<Origem>('zero')
  const [modelo, setModelo] = useState<number | null>(null)
  const [etapas, setEtapas] = useState<EtapaRascunho[]>([])
  const [encadearEtapas, setEncadearEtapas] = useState(true)
  const [encadearDentro, setEncadearDentro] = useState(true)
  const [gravando, setGravando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  useEffect(() => {
    if (calendario == null && calendarios.length) {
      setCalendario((calendarios.find((c) => c.obra === obraId) ?? calendarios[0]).calendario_id)
    }
  }, [calendarios, calendario, obraId])

  const passos = origem === 'zero'
    ? ['Início e expediente', 'Ponto de partida', 'Etapas e atividades', 'Sequência', 'Criar']
    : ['Início e expediente', 'Ponto de partida', 'Criar']
  const ultimo = passos.length - 1

  function podeAvancar(): boolean {
    if (passo === 0) return !!inicio && calendario != null
    if (passo === 1) return origem !== 'modelo' || modelo != null
    if (passos[passo] === 'Etapas e atividades') return etapas.some((e) => e.nome.trim())
    return true
  }

  async function criar() {
    setErro(null)
    setGravando(true)
    try {
      if (origem === 'modelo' && modelo != null) {
        await planoApi.aplicarModelo(modelo, { obra: obraId, data_inicio: inicio, calendario, descricao: 'Plano da obra' })
        await recalcularDaObra()
        aoConcluir(null)
        return
      }
      const novo = await api.cronogramas.criar({ obra: obraId, descricao: 'Plano da obra', data_inicio: inicio, calendario })
      if (origem === 'zero') await montarDoZero(novo.cronograma_id)
      try { await api.cronogramas.calcular(novo.cronograma_id) } catch { /* o posto mostra o motivo */ }
      await qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.raiz() })
      await qc.invalidateQueries({ queryKey: [...pdcaKeys.raiz, 'etapas', obraId] })
      aoConcluir(origem === 'orcamento' ? 'orcamento' : origem === 'colar' ? 'colar' : null)
    } catch (e) {
      setErro(mensagemDe(e, 'Não foi possível criar o plano.'))
    } finally {
      setGravando(false)
    }
  }

  async function recalcularDaObra() {
    const lista = await api.cronogramas.listar({ obra: obraId })
    const criado = lista.sort((a, b) => b.versao - a.versao)[0]
    if (criado) { try { await api.cronogramas.calcular(criado.cronograma_id) } catch { /* idem */ } }
    await qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.raiz() })
  }

  /** As etapas e atividades digitadas viram linhas com código e predecessoras,
   *  numa importação só; depois cada etapa é ligada à etapa da obra. */
  async function montarDoZero(cronogramaId: number) {
    const validas = etapas
      .map((e) => ({ ...e, nome: e.nome.trim(), atividades: e.atividades.filter((a) => a.nome.trim()) }))
      .filter((e) => e.nome)
    const linhas: LinhaImportada[] = []
    validas.forEach((e, i) => {
      const cod = String(i + 1)
      const temFilhas = e.atividades.length > 0
      const anterior = i > 0 ? String(i) : null
      linhas.push({
        codigo: cod, nome: e.nome, nivel: 1,
        duracao_dias: temFilhas ? null : '5',
        // Fase depois de fase: a etapa seguinte começa quando a anterior termina.
        predecessoras: encadearEtapas && anterior ? anterior : '',
      })
      e.atividades.forEach((a, j) => {
        linhas.push({
          codigo: `${cod}.${j + 1}`, nome: a.nome.trim(), nivel: 2,
          duracao_dias: String(Math.max(1, Math.round(Number(a.duracao.replace(',', '.')) || 1))),
          predecessoras: encadearDentro && j > 0 ? `${cod}.${j}` : '',
        })
      })
    })
    if (linhas.length === 0) return
    await planoApi.importarLinhas(cronogramaId, linhas, 'codigo')

    // A etapa do plano é a etapa da obra: liga cada raiz à de mesmo nome (ou cria).
    const existentes = await etapasDaObra.listar(obraId)
    const { atividades } = await api.cronogramas.gantt(cronogramaId)
    let ordem = existentes.reduce((m, e) => Math.max(m, e.ordem), 0)
    for (const raiz of atividades.filter((a) => a.pai == null)) {
      let etapa = existentes.find((e) => e.nome_etapa.trim().toLowerCase() === raiz.nome.trim().toLowerCase())
      if (!etapa) {
        ordem += 1
        etapa = await etapasDaObra.criar(obraId, nomeLivre(raiz.nome, existentes.map((e) => e.nome_etapa)), ordem)
        existentes.push(etapa)
      }
      await api.atividades.atualizar(raiz.atividade_id, { etapa: etapa.etapa_id })
    }
  }

  return (
    <div style={{ padding: '24px 26px', maxWidth: 860, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div style={{ fontSize: 18, fontWeight: 750, color: 'var(--ink)' }}>Montar o plano da obra</div>
        <div style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 4 }}>
          Alguns passos para o primeiro esqueleto. Depois tudo se ajusta na planilha e no Gantt.
        </div>
      </div>

      <ol style={{ display: 'flex', gap: 6, listStyle: 'none', padding: 0, margin: 0, flexWrap: 'wrap' }}>
        {passos.map((p, i) => (
          <li key={p}>
            <Pill kind={i === passo ? 'accent' : i < passo ? 'good' : 'slate'}>{i + 1}. {p}</Pill>
          </li>
        ))}
      </ol>

      <Card>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: 4 }}>
          {passo === 0 && (
            <>
              <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13 }}>
                A obra começa em
                <input type="date" min={minCalendarioISO} max={maxCalendarioISO} value={inicio} onChange={(e) => setInicio(e.target.value)} style={ESTILO_CAMPO} />
              </label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <span style={{ fontSize: 13 }}>Em que dias a obra trabalha (expediente)</span>
                {carregandoCal && <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Carregando…</span>}
                {calendarios.length > 0 && !criandoCal && (
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <select value={calendario ?? ''} onChange={(e) => setCalendario(Number(e.target.value))} style={ESTILO_CAMPO}>
                      {calendarios.map((c) => (
                        <option key={c.calendario_id} value={c.calendario_id}>{c.nome}{c.obra ? '' : ' (da empresa)'}</option>
                      ))}
                    </select>
                    <Btn tam="sm" onClick={() => setCriandoCal(true)}>+ Novo expediente</Btn>
                  </div>
                )}
                {!carregandoCal && (calendarios.length === 0 || criandoCal) && (
                  <div style={{ background: 'var(--inset)', padding: 12, borderRadius: 'var(--r-sm)' }}>
                    <FormularioDeExpediente
                      obraId={obraId}
                      aoConcluir={(cal) => { setCalendario(cal.calendario_id); setCriandoCal(false) }}
                      aoCancelar={calendarios.length ? () => setCriandoCal(false) : undefined}
                    />
                  </div>
                )}
              </div>
            </>
          )}

          {passo === 1 && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 10 }}>
              <CartaoDeOrigem ativo={origem === 'zero'} aoEscolher={() => setOrigem('zero')} icone={<ListTree size={18} />}
                titulo="Digitar etapas e atividades" texto="Um passo a passo: as fases da obra, os serviços de cada uma e a ordem." />
              <CartaoDeOrigem ativo={origem === 'orcamento'} aoEscolher={() => setOrigem('orcamento')} icone={<Calculator size={18} />}
                titulo="Do orçamento da obra" texto="As etapas do cronograma do orçamento, com datas, valor e Hh — o detalhe é seu." />
              <CartaoDeOrigem ativo={origem === 'modelo'} aoEscolher={() => setOrigem('modelo')} icone={<LayoutTemplate size={18} />}
                titulo="De um plano modelo" texto="Repete a estrutura, as durações e a sequência de um padrão da empresa." />
              <CartaoDeOrigem ativo={origem === 'colar'} aoEscolher={() => setOrigem('colar')} icone={<ClipboardPaste size={18} />}
                titulo="Colar do Excel ou MS Project" texto="Cola as linhas ou abre o XML do Project, com hierarquia e predecessoras." />
              {origem === 'modelo' && (
                <div style={{ gridColumn: '1 / -1', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {modelos.length === 0 ? (
                    <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
                      A biblioteca de modelos está vazia. Escolha outro caminho; depois de montar, dá para salvar este plano como modelo.
                    </span>
                  ) : modelos.map((m) => (
                    <label key={m.cronograma_id} style={{ display: 'flex', gap: 8, fontSize: 13, alignItems: 'center' }}>
                      <input type="radio" name="modelo" checked={modelo === m.cronograma_id} onChange={() => setModelo(m.cronograma_id)} />
                      {m.nome_modelo} <span style={{ color: 'var(--ink-3)' }}>· {m.atividades_count} linhas</span>
                    </label>
                  ))}
                </div>
              )}
              {(origem === 'orcamento' || origem === 'colar') && (
                <div style={{ gridColumn: '1 / -1', fontSize: 12.5, color: 'var(--ink-3)' }}>
                  O plano é criado e, em seguida, abre a tela de {origem === 'orcamento' ? 'escolher o orçamento' : 'colar as linhas'}.
                </div>
              )}
            </div>
          )}

          {passos[passo] === 'Etapas e atividades' && (
            <EditorDeEtapas etapas={etapas} setEtapas={setEtapas} />
          )}

          {passos[passo] === 'Sequência' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
              <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input type="checkbox" checked={encadearEtapas} onChange={(e) => setEncadearEtapas(e.target.checked)} />
                Uma etapa começa quando a anterior termina (fundação → estrutura → alvenaria…)
              </label>
              <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input type="checkbox" checked={encadearDentro} onChange={(e) => setEncadearDentro(e.target.checked)} />
                Dentro de cada etapa, as atividades seguem uma depois da outra
              </label>
              <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>
                Sobreposições (começar a pintura 3 dias depois do reboco começar, por exemplo) se ajustam depois
                na coluna Predecessoras ou puxando a seta no Gantt.
              </span>
            </div>
          )}

          {passo === ultimo && (
            <div style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6 }}>
              Início em <strong>{inicio.split('-').reverse().join('/')}</strong>, expediente{' '}
              <strong>{calendarios.find((c) => c.calendario_id === calendario)?.nome ?? '—'}</strong>.
              {origem === 'zero' && (
                <> {etapas.filter((e) => e.nome.trim()).length} etapa(s) e{' '}
                  {etapas.reduce((s, e) => s + e.atividades.filter((a) => a.nome.trim()).length, 0)} atividade(s).</>
              )}
              {origem === 'modelo' && <> A partir do modelo <strong>{modelos.find((m) => m.cronograma_id === modelo)?.nome_modelo}</strong>.</>}
              {origem === 'orcamento' && <> Em seguida, escolha o orçamento.</>}
              {origem === 'colar' && <> Em seguida, cole as linhas ou abra o arquivo.</>}
            </div>
          )}

          {erro && <div style={{ fontSize: 12.5, color: 'var(--danger-ink)' }}>{erro}</div>}

          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Btn onClick={() => setPasso((p) => Math.max(0, p - 1))} disabled={passo === 0 || gravando}>
              <ArrowLeft size={13} /> Voltar
            </Btn>
            {passo < ultimo ? (
              <Btn variant="primary" onClick={() => setPasso((p) => p + 1)} disabled={!podeAvancar()}>
                Próximo <ArrowRight size={13} />
              </Btn>
            ) : (
              <Btn variant="primary" onClick={criar} disabled={gravando || calendario == null}>
                <FileSpreadsheet size={13} /> {gravando ? 'Criando…' : 'Criar o plano'}
              </Btn>
            )}
          </div>
        </div>
      </Card>
    </div>
  )
}

function CartaoDeOrigem(
  { ativo, aoEscolher, icone, titulo, texto }:
  { ativo: boolean; aoEscolher: () => void; icone: React.ReactNode; titulo: string; texto: string },
) {
  return (
    <button
      type="button"
      onClick={aoEscolher}
      aria-pressed={ativo}
      style={{
        textAlign: 'left', display: 'flex', flexDirection: 'column', gap: 6, padding: 12, cursor: 'pointer',
        background: ativo ? 'var(--accent-soft)' : 'var(--surface)', color: 'var(--ink)',
        border: `1.5px solid ${ativo ? 'var(--accent)' : 'var(--line)'}`, borderRadius: 'var(--r-md)',
      }}
    >
      <span style={{ color: ativo ? 'var(--accent-ink)' : 'var(--ink-2)' }}>{icone}</span>
      <span style={{ fontSize: 13, fontWeight: 700 }}>{titulo}</span>
      <span style={{ fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.45 }}>{texto}</span>
    </button>
  )
}

function EditorDeEtapas(
  { etapas, setEtapas }: { etapas: EtapaRascunho[]; setEtapas: (e: EtapaRascunho[]) => void },
) {
  const mudar = (i: number, e: EtapaRascunho) => setEtapas(etapas.map((x, j) => (j === i ? e : x)))
  const usadas = new Set(etapas.map((e) => e.nome.trim().toLowerCase()))
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: 12.5, color: 'var(--ink-3)' }}>Sugestões:</span>
        {SUGESTOES.filter((s) => !usadas.has(s.toLowerCase())).map((s) => (
          <Btn key={s} tam="sm" onClick={() => setEtapas([...etapas, { nome: s, atividades: [] }])}>+ {s}</Btn>
        ))}
      </div>
      {etapas.map((e, i) => (
        <div key={i} style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', padding: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ink-3)', width: 20 }}>{i + 1}</span>
            <input value={e.nome} onChange={(ev) => mudar(i, { ...e, nome: ev.target.value })} placeholder="Nome da etapa" style={{ ...ESTILO_CAMPO, flex: 1, fontWeight: 650 }} />
            <button type="button" aria-label="Tirar a etapa" title="Tirar a etapa" onClick={() => setEtapas(etapas.filter((_, j) => j !== i))} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--ink-3)' }}>
              <Trash2 size={14} />
            </button>
          </div>
          {e.atividades.map((a, j) => (
            <div key={j} style={{ display: 'flex', gap: 6, alignItems: 'center', paddingLeft: 26 }}>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--ink-3)', width: 28 }}>{i + 1}.{j + 1}</span>
              <input
                autoFocus={j === e.atividades.length - 1 && !a.nome}
                value={a.nome}
                onChange={(ev) => mudar(i, { ...e, atividades: e.atividades.map((x, k) => (k === j ? { ...x, nome: ev.target.value } : x)) })}
                onKeyDown={(ev) => {
                  if (ev.key === 'Enter') { ev.preventDefault(); mudar(i, { ...e, atividades: [...e.atividades, { nome: '', duracao: '5' }] }) }
                }}
                placeholder="Atividade (Enter adiciona a próxima)"
                style={{ ...ESTILO_CAMPO, flex: 1 }}
              />
              <input
                value={a.duracao}
                onChange={(ev) => mudar(i, { ...e, atividades: e.atividades.map((x, k) => (k === j ? { ...x, duracao: ev.target.value } : x)) })}
                inputMode="numeric"
                aria-label="Duração em dias úteis"
                style={{ ...ESTILO_CAMPO, width: 56, textAlign: 'right' }}
              />
              <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>dias</span>
              <button type="button" aria-label="Tirar a atividade" onClick={() => mudar(i, { ...e, atividades: e.atividades.filter((_, k) => k !== j) })} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--ink-3)' }}>
                ×
              </button>
            </div>
          ))}
          <div style={{ paddingLeft: 26 }}>
            <Btn tam="sm" onClick={() => mudar(i, { ...e, atividades: [...e.atividades, { nome: '', duracao: '5' }] })}>
              <Plus size={12} /> Atividade
            </Btn>
          </div>
        </div>
      ))}
      <div>
        <Btn onClick={() => setEtapas([...etapas, { nome: '', atividades: [] }])}><Plus size={13} /> Etapa</Btn>
      </div>
    </div>
  )
}
