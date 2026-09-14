import { useEffect, useMemo, useState } from 'react'
import { ExternalLink, Lock, Plus, X } from 'lucide-react'
import { Btn, Pill } from '@/components/malha'
import { dateFromBR, dateToBR, maskDate, validateISO_Vigencia } from '@/utils/dates'
import { FieldError, type FieldErrors } from '@/utils/formErrors'
import {
  useCalendarios, useEtapasDaObra, useItensOrcados, useLocaisDaObra, useOrcamentosDaObra,
  useResponsaveis,
} from '../hooks'
import type { Atividade, Precedencia, TipoPrecedencia } from '../types'

const TIPOS: { valor: TipoPrecedencia; rotulo: string; ajuda: string }[] = [
  { valor: 'FS', rotulo: 'TI — término/início', ajuda: 'A sucessora começa depois que esta termina. É a mais comum.' },
  { valor: 'SS', rotulo: 'II — início/início', ajuda: 'As duas começam juntas, com a defasagem do atraso.' },
  { valor: 'FF', rotulo: 'TT — término/término', ajuda: 'As duas terminam juntas.' },
  { valor: 'SF', rotulo: 'IT — início/término', ajuda: 'Rara: a sucessora termina quando esta começa.' },
]

interface Props {
  atividade: Atividade
  obra: number
  precedencias: Precedencia[]
  porId: Map<number, Atividade>
  editavel: boolean
  podeVerOrcamento: boolean
  onFechar: () => void
  onSalvar: (payload: Partial<Atividade>) => void
  onCriarPrecedencia: (origem: number, tipo: TipoPrecedencia, atraso: number) => void
  onAtualizarPrecedencia: (id: number, payload: Partial<Precedencia>) => void
  onExcluirPrecedencia: (id: number) => void
}

/**
 * O inspetor — onde a atividade mostra tudo o que a grade não cabe.
 *
 * A ordem dos blocos é a ordem das perguntas de quem planeja: *quando ela
 * acontece*, *do que ela depende*, *a que ela se amarra no resto do sistema* e
 * *quanto ela pesa*. Não é um formulário de cadastro com os campos na ordem do
 * modelo — essa ordem é do banco, não de quem trabalha.
 */
export default function InspetorAtividade({
  atividade, obra, precedencias, porId, editavel, podeVerOrcamento, onFechar,
  onSalvar, onCriarPrecedencia, onAtualizarPrecedencia, onExcluirPrecedencia,
}: Props) {
  const [form, setForm] = useState(() => paraFormulario(atividade))
  const [erros, setErros] = useState<FieldErrors>({})
  const [buscaItem, setBuscaItem] = useState('')
  const [buscaResponsavel, setBuscaResponsavel] = useState('')
  const [orcamento, setOrcamento] = useState<number | null>(null)

  useEffect(() => {
    setForm(paraFormulario(atividade))
    setErros({})
  }, [atividade])

  const locais = useLocaisDaObra(obra)
  const etapas = useEtapasDaObra(obra)
  const calendarios = useCalendarios()
  const orcamentos = useOrcamentosDaObra(podeVerOrcamento ? obra : undefined)
  const itens = useItensOrcados(orcamento ?? undefined, buscaItem)
  const responsaveis = useResponsaveis(buscaResponsavel, buscaResponsavel.length >= 2)

  useEffect(() => {
    if (orcamento == null && orcamentos.data?.length) setOrcamento(orcamentos.data[0].orcamento_id)
  }, [orcamentos.data, orcamento])

  const entrando = useMemo(
    () => precedencias.filter(p => p.destino === atividade.atividade_id),
    [precedencias, atividade.atividade_id],
  )
  const saindo = useMemo(
    () => precedencias.filter(p => p.origem === atividade.atividade_id),
    [precedencias, atividade.atividade_id],
  )
  const candidatas = useMemo(
    () => [...porId.values()]
      .filter(a => !a.tem_filhos && a.atividade_id !== atividade.atividade_id)
      .filter(a => !entrando.some(p => p.origem === a.atividade_id))
      .sort((x, y) => x.codigo.localeCompare(y.codigo, 'pt-BR', { numeric: true })),
    [porId, atividade.atividade_id, entrando],
  )

  const salvar = () => {
    const iso = form.nao_comecar_antes_de ? dateFromBR(form.nao_comecar_antes_de) : ''
    if (form.nao_comecar_antes_de && !iso) {
      setErros({ nao_comecar_antes_de: 'Data inválida.' })
      return
    }
    const erroData = iso ? validateISO_Vigencia(iso) : null
    if (erroData) {
      setErros({ nao_comecar_antes_de: erroData })
      return
    }
    onSalvar({
      nome: form.nome,
      codigo: form.codigo,
      duracao_dias: form.eh_marco ? null : (form.duracao_dias === '' ? null : Number(form.duracao_dias)),
      eh_marco: form.eh_marco,
      nao_comecar_antes_de: iso || null,
      local: form.local,
      etapa: form.etapa,
      item_orcado: form.item_orcado,
      responsavel: form.responsavel,
      calendario: form.calendario,
      peso_informado: form.peso_informado === '' ? null : form.peso_informado,
      observacao: form.observacao,
    })
  }

  return (
    <aside style={{
      width: 380, flex: '0 0 380px', borderLeft: '1px solid var(--line)',
      background: 'var(--surface)', display: 'flex', flexDirection: 'column',
      height: '100%', minHeight: 0,
    }}>
      <header style={{
        display: 'flex', alignItems: 'flex-start', gap: 10, padding: '14px 16px',
        borderBottom: '1px solid var(--line)',
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <code style={{ fontSize: 12, color: 'var(--ink-3)' }}>{atividade.codigo}</code>
            {atividade.critica
              ? <Pill kind="danger">Caminho crítico</Pill>
              : atividade.folga_total != null && <Pill kind="slate">{atividade.folga_total} d de folga</Pill>}
            {atividade.tem_filhos && <Pill kind="info">Sintética</Pill>}
          </div>
          <strong style={{ fontSize: 14.5, lineHeight: 1.3 }}>{atividade.nome}</strong>
        </div>
        <button
          onClick={onFechar} aria-label="Fechar o inspetor"
          style={{ border: 'none', background: 'none', color: 'var(--ink-3)', cursor: 'pointer', padding: 2 }}
        ><X size={16} /></button>
      </header>

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 18 }}>
        <Bloco titulo="Quando">
          <Grade>
            <Leitura rotulo="Início cedo" valor={data(atividade.inicio_cedo)} />
            <Leitura rotulo="Término cedo" valor={data(atividade.termino_cedo)} />
            <Leitura rotulo="Início tarde" valor={data(atividade.inicio_tarde)} />
            <Leitura rotulo="Término tarde" valor={data(atividade.termino_tarde)} />
            <Leitura rotulo="Folga total" valor={atividade.folga_total == null ? 'sem cálculo' : atividade.folga_total + ' d'} />
            <Leitura rotulo="Folga livre" valor={atividade.folga_livre == null ? 'sem cálculo' : atividade.folga_livre + ' d'} />
          </Grade>

          {!atividade.tem_filhos && (
            <>
              <label style={campo}>
                <span>Duração (dias úteis)</span>
                <input
                  type="number" min={1} value={form.duracao_dias} disabled={!editavel || form.eh_marco}
                  onChange={e => setForm(f => ({ ...f, duracao_dias: e.target.value }))}
                />
              </label>
              <label style={{ ...campo, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox" checked={form.eh_marco} disabled={!editavel}
                  onChange={e => setForm(f => ({ ...f, eh_marco: e.target.checked, duracao_dias: e.target.checked ? '' : f.duracao_dias }))}
                />
                <span>É um marco (instante, sem duração)</span>
              </label>
            </>
          )}

          <label style={campo}>
            <span>Não começar antes de</span>
            <input
              value={form.nao_comecar_antes_de} disabled={!editavel} placeholder="DD/MM/AAAA"
              onChange={e => setForm(f => ({ ...f, nao_comecar_antes_de: maskDate(e.target.value) }))}
            />
            <FieldError msg={erros.nao_comecar_antes_de} />
            <small style={ajuda}>
              A restrição ancora a atividade que depende do mundo — licença com data, equipamento
              importado. O CPM não a puxa para antes disso.
            </small>
          </label>

          <label style={campo}>
            <span>Calendário próprio</span>
            <select
              value={form.calendario ?? ''} disabled={!editavel}
              onChange={e => setForm(f => ({ ...f, calendario: e.target.value ? Number(e.target.value) : null }))}
            >
              <option value="">Herda o do cronograma</option>
              {(calendarios.data ?? []).map(c => (
                <option key={c.calendario_id} value={c.calendario_id}>{c.nome}</option>
              ))}
            </select>
            <small style={ajuda}>Para a frente de turno da noite ou a que para na chuva.</small>
          </label>
        </Bloco>

        <Bloco titulo="Do que depende">
          {atividade.tem_filhos ? (
            <p style={ajuda}>
              A sintética não entra no grafo: ela é o intervalo das filhas. A rede se liga nas folhas.
            </p>
          ) : (
            <>
              {entrando.length === 0 && (
                <p style={ajuda}>
                  Sem predecessora. A atividade começa na âncora do plano — e uma folha solta no meio
                  de uma rede costuma ser esquecimento, não decisão.
                </p>
              )}
              {entrando.map(p => (
                <div key={p.precedencia_id} style={linhaRede}>
                  <code style={{ fontSize: 11.5, width: 74, color: 'var(--ink-2)' }}>
                    {porId.get(p.origem)?.codigo ?? p.origem_codigo}
                  </code>
                  <select
                    value={p.tipo} disabled={!editavel}
                    onChange={e => onAtualizarPrecedencia(p.precedencia_id, { tipo: e.target.value as TipoPrecedencia })}
                    style={{ flex: 1, minWidth: 0 }}
                    title={TIPOS.find(t => t.valor === p.tipo)?.ajuda}
                  >
                    {TIPOS.map(t => <option key={t.valor} value={t.valor}>{t.rotulo}</option>)}
                  </select>
                  <input
                    type="number" value={p.atraso_dias} disabled={!editavel} title="Atraso em dias úteis"
                    onChange={e => onAtualizarPrecedencia(p.precedencia_id, { atraso_dias: Number(e.target.value) })}
                    style={{ width: 56 }}
                  />
                  {editavel && (
                    <button
                      onClick={() => onExcluirPrecedencia(p.precedencia_id)} aria-label="Remover a ligação"
                      style={{ border: 'none', background: 'none', color: 'var(--ink-3)', cursor: 'pointer', padding: 2 }}
                    ><X size={14} /></button>
                  )}
                </div>
              ))}

              {editavel && (
                <NovaPrecedencia candidatas={candidatas} onCriar={onCriarPrecedencia} />
              )}

              {saindo.length > 0 && (
                <div style={{ marginTop: 6 }}>
                  <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>Empurra: </span>
                  <span style={{ fontSize: 12 }}>
                    {saindo.map(p => porId.get(p.destino)?.codigo ?? p.destino_codigo).join(' · ')}
                  </span>
                </div>
              )}
            </>
          )}
        </Bloco>

        <Bloco titulo="A que se amarra">
          <label style={campo}>
            <span>Local da obra</span>
            <select
              value={form.local ?? ''} disabled={!editavel}
              onChange={e => setForm(f => ({ ...f, local: e.target.value ? Number(e.target.value) : null }))}
            >
              <option value="">Sem local</option>
              {(locais.data ?? []).map(l => (
                <option key={l.local_id} value={l.local_id}>{l.codigo} {l.nome}</option>
              ))}
            </select>
            {locais.isError && <small style={ajuda}>Não foi possível ler a árvore de locais desta obra.</small>}
          </label>

          <label style={campo}>
            <span>Etapa da obra</span>
            <select
              value={form.etapa ?? ''} disabled={!editavel}
              onChange={e => setForm(f => ({ ...f, etapa: e.target.value ? Number(e.target.value) : null }))}
            >
              <option value="">Sem etapa</option>
              {(etapas.data ?? []).map(et => (
                <option key={et.etapa_id} value={et.etapa_id}>{et.nome_etapa}</option>
              ))}
            </select>
            {etapas.isError
              ? <small style={ajuda}><Lock size={10} /> Sem acesso ao cadastro de obras para listar as etapas.</small>
              : <small style={ajuda}>O vínculo é opcional — é ele que traduz a WBS para a dimensão que Orçamento e SIL já compartilham.</small>}
          </label>
        </Bloco>

        <Bloco titulo="Quanto pesa">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Leitura
              rotulo="Peso efetivo"
              valor={atividade.peso == null
                ? 'sem apuração'
                : atividade.peso_origem === 'orcado'
                  ? Number(atividade.peso).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
                  : Number(atividade.peso).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}
            />
            {atividade.peso_origem === 'orcado' && <Pill kind="good">vem do orçamento</Pill>}
            {atividade.peso_origem === 'informado' && <Pill kind="slate">informado</Pill>}
          </div>

          {!podeVerOrcamento ? (
            <p style={ajuda}>
              <Lock size={10} /> O módulo Orçamento não está no plano desta empresa. Sem ele, o peso
              da atividade é o informado à mão.
            </p>
          ) : (
            <>
              <label style={campo}>
                <span>Orçamento da obra</span>
                <select value={orcamento ?? ''} onChange={e => setOrcamento(e.target.value ? Number(e.target.value) : null)}>
                  {(orcamentos.data ?? []).map(o => (
                    <option key={o.orcamento_id} value={o.orcamento_id}>{o.descricao} (v{o.versao})</option>
                  ))}
                </select>
                {orcamentos.data?.length === 0 && <small style={ajuda}>Esta obra ainda não tem orçamento.</small>}
              </label>

              <label style={campo}>
                <span>Item orçado</span>
                {form.item_orcado ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ flex: 1, fontSize: 12.5 }}>{atividade.item_orcado_rotulo || 'Item vinculado'}</span>
                    <a
                      href={'/app/orcamento/orcar?orcamento=' + (orcamento ?? '')}
                      style={{ color: 'var(--brand)', display: 'flex' }} title="Abrir no Orçamento"
                    ><ExternalLink size={13} /></a>
                    {editavel && (
                      <button
                        onClick={() => setForm(f => ({ ...f, item_orcado: null }))}
                        style={{ border: 'none', background: 'none', color: 'var(--ink-3)', cursor: 'pointer' }}
                        aria-label="Desvincular"
                      ><X size={14} /></button>
                    )}
                  </div>
                ) : (
                  <>
                    <input
                      value={buscaItem} disabled={!editavel} placeholder="Buscar item por código ou descrição"
                      onChange={e => setBuscaItem(e.target.value)}
                    />
                    {buscaItem.length >= 2 && (
                      <div style={listaBusca}>
                        {(itens.data ?? []).slice(0, 12).map(item => (
                          <button
                            key={item.item_orcado_id} type="button"
                            onClick={() => { setForm(f => ({ ...f, item_orcado: item.item_orcado_id })); setBuscaItem('') }}
                            style={opcaoBusca}
                          >
                            <code style={{ color: 'var(--ink-3)' }}>{item.codigo_eap}</code> {item.descricao}
                          </button>
                        ))}
                        {itens.data?.length === 0 && <span style={ajuda}>Nada encontrado neste orçamento.</span>}
                      </div>
                    )}
                  </>
                )}
                <small style={ajuda}>
                  Vinculada, a atividade vale o que o item vale — e o avanço vira dinheiro sem digitação.
                </small>
              </label>
            </>
          )}

          <label style={campo}>
            <span>Peso informado</span>
            <input
              type="number" step="0.01" value={form.peso_informado}
              disabled={!editavel || !!form.item_orcado}
              onChange={e => setForm(f => ({ ...f, peso_informado: e.target.value }))}
            />
            <small style={ajuda}>
              {form.item_orcado
                ? 'Ignorado enquanto houver vínculo com o orçamento.'
                : 'Sem vínculo e sem peso, a atividade não pondera o avanço do pai — e a tela diz "sem apuração", não zero.'}
            </small>
          </label>
        </Bloco>

        <Bloco titulo="Quem e o quê">
          <label style={campo}>
            <span>Responsável</span>
            {form.responsavel ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ flex: 1, fontSize: 12.5 }}>{atividade.responsavel_nome || 'Responsável definido'}</span>
                {editavel && (
                  <button
                    onClick={() => setForm(f => ({ ...f, responsavel: null }))}
                    style={{ border: 'none', background: 'none', color: 'var(--ink-3)', cursor: 'pointer' }}
                    aria-label="Remover responsável"
                  ><X size={14} /></button>
                )}
              </div>
            ) : (
              <>
                <input
                  value={buscaResponsavel} disabled={!editavel} placeholder="Buscar por nome"
                  onChange={e => setBuscaResponsavel(e.target.value)}
                />
                {responsaveis.isError && <small style={ajuda}><Lock size={10} /> Sem acesso ao RH para listar funcionários.</small>}
                {buscaResponsavel.length >= 2 && !responsaveis.isError && (
                  <div style={listaBusca}>
                    {(responsaveis.data ?? []).slice(0, 10).map(r => (
                      <button
                        key={r.funcionario_id} type="button" style={opcaoBusca}
                        onClick={() => { setForm(f => ({ ...f, responsavel: r.funcionario_id })); setBuscaResponsavel('') }}
                      >{r.nome_completo}</button>
                    ))}
                  </div>
                )}
              </>
            )}
          </label>

          <label style={campo}>
            <span>Observação</span>
            <textarea
              rows={3} value={form.observacao} disabled={!editavel}
              onChange={e => setForm(f => ({ ...f, observacao: e.target.value }))}
            />
          </label>
        </Bloco>
      </div>

      {editavel && (
        <footer style={{ padding: '12px 16px', borderTop: '1px solid var(--line)', display: 'flex', gap: 8 }}>
          <Btn variant="brand" onClick={salvar} style={{ flex: 1, justifyContent: 'center' }}>Salvar</Btn>
          <Btn onClick={() => setForm(paraFormulario(atividade))}>Descartar</Btn>
        </footer>
      )}
    </aside>
  )
}

// ---------------------------------------------------------------------------

function NovaPrecedencia({ candidatas, onCriar }: {
  candidatas: Atividade[]
  onCriar: (origem: number, tipo: TipoPrecedencia, atraso: number) => void
}) {
  const [origem, setOrigem] = useState<number | ''>('')
  const [tipo, setTipo] = useState<TipoPrecedencia>('FS')
  const [atraso, setAtraso] = useState('0')

  return (
    <div style={{ ...linhaRede, marginTop: 4 }}>
      <select value={origem} onChange={e => setOrigem(e.target.value ? Number(e.target.value) : '')} style={{ flex: 1, minWidth: 0 }}>
        <option value="">Adicionar predecessora…</option>
        {candidatas.map(a => (
          <option key={a.atividade_id} value={a.atividade_id}>{a.codigo} {a.nome}</option>
        ))}
      </select>
      <select value={tipo} onChange={e => setTipo(e.target.value as TipoPrecedencia)} style={{ width: 74 }}>
        {TIPOS.map(t => <option key={t.valor} value={t.valor}>{t.valor}</option>)}
      </select>
      <input type="number" value={atraso} onChange={e => setAtraso(e.target.value)} style={{ width: 56 }} title="Atraso em dias úteis" />
      <button
        disabled={origem === ''} aria-label="Criar a ligação"
        onClick={() => { if (origem !== '') { onCriar(origem, tipo, Number(atraso) || 0); setOrigem(''); setAtraso('0') } }}
        style={{
          border: 'none', background: 'none', cursor: origem === '' ? 'not-allowed' : 'pointer',
          color: origem === '' ? 'var(--ink-3)' : 'var(--brand)', padding: 2, display: 'flex',
        }}
      ><Plus size={15} /></button>
    </div>
  )
}

function Bloco({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <h3 style={{
        margin: 0, fontSize: 11, fontWeight: 700, letterSpacing: '.05em',
        textTransform: 'uppercase', color: 'var(--ink-3)',
      }}>{titulo}</h3>
      {children}
    </section>
  )
}

const Grade = ({ children }: { children: React.ReactNode }) => (
  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 12px' }}>{children}</div>
)

function Leitura({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <span style={{ fontSize: 10.5, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '.04em' }}>{rotulo}</span>
      <span style={{ fontSize: 13 }}>{valor}</span>
    </div>
  )
}

function paraFormulario(a: Atividade) {
  return {
    codigo: a.codigo,
    nome: a.nome,
    duracao_dias: a.duracao_dias == null ? '' : String(a.duracao_dias),
    eh_marco: a.eh_marco,
    nao_comecar_antes_de: a.nao_comecar_antes_de ? dateToBR(a.nao_comecar_antes_de) : '',
    local: a.local,
    etapa: a.etapa,
    item_orcado: a.item_orcado,
    responsavel: a.responsavel,
    calendario: a.calendario,
    peso_informado: a.peso_informado == null ? '' : String(a.peso_informado),
    observacao: a.observacao ?? '',
  }
}

const data = (iso: string | null) => (iso ? dateToBR(iso) : 'sem cálculo')

const campo: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }
const ajuda: React.CSSProperties = { fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.45 }
const linhaRede: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 6 }
const listaBusca: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 190, overflow: 'auto',
  border: '1px solid var(--line)', borderRadius: 8, padding: 4,
}
const opcaoBusca: React.CSSProperties = {
  textAlign: 'left', border: 'none', background: 'none', cursor: 'pointer',
  padding: '5px 6px', fontSize: 12, color: 'var(--ink)', borderRadius: 6,
}
