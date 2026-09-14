import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, CalendarDays, ExternalLink, Plus, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Btn, Card, Empty, Loading, Pill, SectionHead } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { dateFromBR, dateToBR, maskDate, validateISO_Vigencia } from '@/utils/dates'
import { FieldError, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import {
  useCalendario, useDiasUteis, useExcluirCalendario, useExcluirExcecao, useExpediente,
  useObras, useSalvarCalendario, useSalvarExcecao,
} from '../hooks'
import type { Calendario } from '../types'

const DIAS = [
  ['trabalha_segunda', 'Seg'], ['trabalha_terca', 'Ter'], ['trabalha_quarta', 'Qua'],
  ['trabalha_quinta', 'Qui'], ['trabalha_sexta', 'Sex'], ['trabalha_sabado', 'Sáb'],
  ['trabalha_domingo', 'Dom'],
] as const

type ChaveDia = (typeof DIAS)[number][0]

/**
 * O expediente da empresa e das obras — a tela que faltava da PDCA.0.
 *
 * O backend do calendário existe desde a fundação e o CPM depende dele para
 * converter duração em data; até aqui, porém, só dava para **escolher** um
 * calendário existente. Declarar o recesso de fim de ano ou o mutirão de sábado
 * exigia o `/admin`, que é do desenvolvedor — não de quem planeja.
 *
 * A régua da tela é a mesma do resto do módulo: nada de configuração cega. Cada
 * calendário traz a **conferência** ao lado (quantos dias úteis numa janela real,
 * quais feriados caem nela), porque expediente é a coisa mais fácil de configurar
 * errado e a mais cara de descobrir errado — o erro só aparece como "o prazo não
 * bate", três meses depois.
 */
export default function ExpedientePage() {
  const navegar = useNavigate()
  const { hasPermission } = useAuth()
  const podeEditar = hasPermission('pdca.calendario.edit')

  const lista = useExpediente()
  const obras = useObras()
  const [selecionado, setSelecionado] = useState<number | null>(null)
  const [criando, setCriando] = useState(false)

  useEffect(() => {
    if (selecionado == null && lista.data?.length) setSelecionado(lista.data[0].calendario_id)
  }, [lista.data, selecionado])

  if (lista.isLoading) return <Loading o="os calendários de trabalho" />

  const calendarios = lista.data ?? []

  return (
    <div style={{ padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <header style={{ display: 'flex', alignItems: 'flex-start', gap: 14, flexWrap: 'wrap' }}>
        <button
          onClick={() => navegar('/app/pdca')}
          style={{ border: 'none', background: 'none', color: 'var(--ink-3)', cursor: 'pointer', display: 'flex', gap: 5, alignItems: 'center', fontSize: 12.5, padding: 0, marginTop: 6 }}
        ><ArrowLeft size={14} /> Obras</button>
        <div style={{ flex: 1, minWidth: 260 }}>
          <h1 style={{ margin: 0, fontSize: 22 }}>Expediente</h1>
          <p style={{ margin: '5px 0 0', fontSize: 13, color: 'var(--ink-2)', maxWidth: 680, lineHeight: 1.6 }}>
            Quando a empresa e cada obra trabalham. É daqui que o CPM tira a conversão de
            <strong> duração em data</strong> — cinco dias úteis a partir de uma sexta terminam na
            quinta seguinte, e é este cadastro que sabe disso.
          </p>
        </div>
        {podeEditar && (
          <Btn variant="brand" onClick={() => { setCriando(true); setSelecionado(null) }}>
            <Plus size={15} /> Novo calendário
          </Btn>
        )}
      </header>

      {calendarios.length === 0 && !criando ? (
        <Empty>
          Nenhum calendário cadastrado. Sem um deles, o CPM recusa calcular — em vez de inventar que
          a obra trabalha de segunda a sexta.
        </Empty>
      ) : (
        <div style={{ display: 'grid', gap: 16, gridTemplateColumns: 'minmax(230px, 280px) 1fr', alignItems: 'start' }}>
          <Card style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 3 }}>
            {calendarios.map(c => (
              <button
                key={c.calendario_id} type="button" onClick={() => { setSelecionado(c.calendario_id); setCriando(false) }}
                style={{
                  textAlign: 'left', border: 'none', borderRadius: 8, padding: '9px 11px', cursor: 'pointer',
                  background: selecionado === c.calendario_id && !criando ? 'var(--inset)' : 'transparent',
                  color: 'var(--ink)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
                  <CalendarDays size={13} style={{ color: 'var(--ink-3)' }} />
                  <strong style={{ fontSize: 13 }}>{c.nome}</strong>
                  {c.padrao && <Pill kind="good">padrão</Pill>}
                </div>
                <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
                  {c.obra_nome ?? 'toda a empresa'}
                </span>
              </button>
            ))}
          </Card>

          {criando ? (
            <EditorDeCalendario
              obras={(obras.data ?? []).map(o => ({ id: o.obra_id, nome: o.nome_obra }))}
              podeEditar={podeEditar}
              aoSalvar={novo => { setCriando(false); setSelecionado(novo.calendario_id) }}
              aoCancelar={() => setCriando(false)}
            />
          ) : selecionado != null ? (
            <DetalheDoCalendario id={selecionado} podeEditar={podeEditar} aoExcluir={() => setSelecionado(null)} />
          ) : null}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------

function DetalheDoCalendario({ id, podeEditar, aoExcluir }: {
  id: number
  podeEditar: boolean
  aoExcluir: () => void
}) {
  const calendario = useCalendario(id)
  const excluir = useExcluirCalendario()
  const [erro, setErro] = useState('')

  if (calendario.isLoading || !calendario.data) return <Loading o="o calendário" />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <EditorDeCalendario
        calendario={calendario.data}
        podeEditar={podeEditar}
        aoExcluir={() => {
          if (!window.confirm('Excluir o calendário "' + calendario.data?.nome + '"?')) return
          setErro('')
          excluir.mutate(id, {
            onSuccess: aoExcluir,
            // O 409 do `PROTECT` chega aqui com o motivo pronto: é um plano que
            // depende deste expediente, e a mensagem já nomeia quantos.
            onError: e => setErro(parseApiErrors(e).detail || 'Não foi possível excluir.'),
          })
        }}
      />
      {erro && (
        <div style={{
          fontSize: 12.5, lineHeight: 1.5, padding: '9px 12px', borderRadius: 8,
          background: 'var(--danger-soft)', color: 'var(--danger-ink)',
        }}>{erro}</div>
      )}
      <Excecoes calendario={calendario.data} podeEditar={podeEditar} />
      <Conferencia calendario={calendario.data} />
    </div>
  )
}

function EditorDeCalendario({ calendario, obras = [], podeEditar, aoSalvar, aoCancelar, aoExcluir }: {
  calendario?: Calendario
  obras?: { id: number; nome: string }[]
  podeEditar: boolean
  aoSalvar?: (c: Calendario) => void
  aoCancelar?: () => void
  aoExcluir?: () => void
}) {
  const salvar = useSalvarCalendario()
  const [erros, setErros] = useState<FieldErrors>({})
  const [form, setForm] = useState(() => ({
    nome: calendario?.nome ?? '',
    obra: calendario?.obra ?? ('' as number | ''),
    padrao: calendario?.padrao ?? false,
    considera_feriados: calendario?.considera_feriados ?? true,
    uf: calendario?.uf ?? '',
    ibge: calendario?.ibge ?? '',
    dias: Object.fromEntries(
      DIAS.map(([chave]) => [chave, calendario ? calendario[chave] : chave !== 'trabalha_sabado' && chave !== 'trabalha_domingo']),
    ) as Record<ChaveDia, boolean>,
  }))

  useEffect(() => {
    if (!calendario) return
    setForm({
      nome: calendario.nome, obra: calendario.obra ?? '', padrao: calendario.padrao,
      considera_feriados: calendario.considera_feriados, uf: calendario.uf, ibge: calendario.ibge,
      dias: Object.fromEntries(DIAS.map(([c]) => [c, calendario[c]])) as Record<ChaveDia, boolean>,
    })
    setErros({})
  }, [calendario])

  const nenhumDia = !Object.values(form.dias).some(Boolean)

  const enviar = () => {
    setErros({})
    salvar.mutate(
      {
        id: calendario?.calendario_id,
        payload: {
          nome: form.nome.trim(),
          obra: form.obra === '' ? null : form.obra,
          padrao: form.padrao,
          considera_feriados: form.considera_feriados,
          uf: form.uf.toUpperCase().slice(0, 2),
          ibge: form.ibge,
          ...form.dias,
        },
      },
      { onSuccess: c => aoSalvar?.(c), onError: e => setErros(parseApiErrors(e)) },
    )
  }

  return (
    <Card style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <SectionHead
        sub="Os dias em que se trabalha — e o que o CPM desconta"
        right={aoExcluir && podeEditar ? (
          <Btn tam="sm" variant="perigo" onClick={aoExcluir}><Trash2 size={13} /> Excluir</Btn>
        ) : undefined}
      >
        {calendario ? calendario.nome : 'Novo calendário'}
      </SectionHead>

      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: '1fr 1fr' }}>
        <label style={campo}>
          <span>Nome</span>
          <input
            value={form.nome} disabled={!podeEditar} maxLength={120}
            onChange={e => setForm(f => ({ ...f, nome: e.target.value }))}
            placeholder="Ex.: Expediente da Torre A"
          />
          <FieldError msg={erros.nome} />
        </label>
        <label style={campo}>
          <span>Alcance</span>
          <select
            value={form.obra} disabled={!podeEditar || !!calendario}
            onChange={e => setForm(f => ({ ...f, obra: e.target.value === '' ? '' : Number(e.target.value) }))}
          >
            <option value="">Toda a empresa</option>
            {obras.map(o => <option key={o.id} value={o.id}>{o.nome}</option>)}
            {calendario?.obra != null && <option value={calendario.obra}>{calendario.obra_nome}</option>}
          </select>
          <small style={ajuda}>
            O calendário da obra vence o da empresa; a atividade pode ter o seu, para a frente de
            turno da noite.
          </small>
        </label>
      </div>

      <div>
        <span style={{ ...campo, fontSize: 12.5, marginBottom: 6, display: 'block' }}>Dias trabalhados</span>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {DIAS.map(([chave, rotulo]) => (
            <button
              key={chave} type="button" disabled={!podeEditar}
              onClick={() => setForm(f => ({ ...f, dias: { ...f.dias, [chave]: !f.dias[chave] } }))}
              style={{
                width: 52, padding: '7px 0', borderRadius: 8, fontSize: 12.5, cursor: podeEditar ? 'pointer' : 'default',
                border: '1px solid ' + (form.dias[chave] ? 'var(--brand)' : 'var(--line)'),
                background: form.dias[chave] ? 'var(--brand)' : 'transparent',
                color: form.dias[chave] ? 'var(--brand-ink)' : 'var(--ink-3)',
                fontWeight: form.dias[chave] ? 650 : 400,
              }}
            >{rotulo}</button>
          ))}
        </div>
        {nenhumDia && (
          <p style={{ ...ajuda, color: 'var(--danger-ink)', marginTop: 6 }}>
            Um calendário sem nenhum dia útil não é um calendário — é uma obra que nunca anda.
          </p>
        )}
        <FieldError msg={erros.non_field_errors || erros.detail} />
      </div>

      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: '1fr 1fr 1fr' }}>
        <label style={{ ...campo, gridColumn: '1 / -1', flexDirection: 'row', alignItems: 'flex-start', gap: 8 }}>
          <input
            type="checkbox" checked={form.considera_feriados} disabled={!podeEditar}
            onChange={e => setForm(f => ({ ...f, considera_feriados: e.target.checked }))}
            style={{ marginTop: 2 }}
          />
          <span>
            Descontar feriados
            <small style={{ ...ajuda, display: 'block' }}>
              Desligue na obra de turno contínuo — refinaria e usina não param no feriado, e
              descontá-lo ali daria um prazo maior que o real.
            </small>
          </span>
        </label>
        <label style={campo}>
          <span>UF (feriados estaduais)</span>
          <input
            value={form.uf} disabled={!podeEditar || !form.considera_feriados} maxLength={2}
            onChange={e => setForm(f => ({ ...f, uf: e.target.value.toUpperCase() }))}
            placeholder="SP"
          />
        </label>
        <label style={campo}>
          <span>Código IBGE (municipais)</span>
          <input
            value={form.ibge} disabled={!podeEditar || !form.considera_feriados} maxLength={7}
            onChange={e => setForm(f => ({ ...f, ibge: e.target.value.replace(/\D/g, '') }))}
            placeholder="3550308"
          />
          <small style={ajuda}>Sem o município, o feriado da cidade não sai da conta.</small>
        </label>
        <label style={{ ...campo, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <input
            type="checkbox" checked={form.padrao} disabled={!podeEditar}
            onChange={e => setForm(f => ({ ...f, padrao: e.target.checked }))}
          />
          <span>Padrão da empresa</span>
        </label>
      </div>

      {podeEditar && (
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          {aoCancelar && <Btn onClick={aoCancelar}>Cancelar</Btn>}
          <Btn variant="brand" onClick={enviar} disabled={!form.nome.trim() || nenhumDia || salvar.isPending}>
            {salvar.isPending ? 'Salvando…' : calendario ? 'Salvar' : 'Criar calendário'}
          </Btn>
        </div>
      )}
    </Card>
  )
}

/** As exceções — o dia que foge da regra. Sem elas, toda parada de obra viraria
 *  edição do calendário inteiro, e o cronograma de janeiro passaria a recontar
 *  dezembro. */
function Excecoes({ calendario, podeEditar }: { calendario: Calendario; podeEditar: boolean }) {
  const salvar = useSalvarExcecao(calendario.calendario_id)
  const excluir = useExcluirExcecao()
  const [form, setForm] = useState({ data: '', trabalha: false, motivo: '' })
  const [erros, setErros] = useState<FieldErrors>({})

  const excecoes = [...(calendario.excecoes ?? [])].sort((a, b) => a.data.localeCompare(b.data))

  const adicionar = () => {
    const iso = dateFromBR(form.data)
    if (!iso) { setErros({ data: 'Use DD/MM/AAAA.' }); return }
    const erro = validateISO_Vigencia(iso)
    if (erro) { setErros({ data: erro }); return }
    setErros({})
    salvar.mutate(
      { data: iso, trabalha: form.trabalha, motivo: form.motivo.trim() },
      {
        onSuccess: () => setForm({ data: '', trabalha: false, motivo: '' }),
        onError: e => setErros(parseApiErrors(e)),
      },
    )
  }

  return (
    <Card style={{ padding: 18 }}>
      <SectionHead sub="O recesso, a parada de chuva, o mutirão de sábado">Exceções</SectionHead>

      {excecoes.length === 0 ? (
        <p style={ajuda}>Nenhuma exceção — o calendário segue a regra da semana o ano inteiro.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 12 }}>
          {excecoes.map(e => (
            <div key={e.excecao_id} style={{
              display: 'flex', alignItems: 'center', gap: 10, fontSize: 12.5,
              padding: '6px 8px', borderRadius: 7, background: 'var(--inset)',
            }}>
              <span className="num" style={{ width: 86 }}>{dateToBR(e.data)}</span>
              <Pill kind={e.trabalha ? 'good' : 'slate'}>{e.trabalha ? 'trabalha' : 'parado'}</Pill>
              <span style={{ flex: 1, color: 'var(--ink-2)' }}>{e.motivo || '—'}</span>
              {podeEditar && (
                <button
                  onClick={() => excluir.mutate(e.excecao_id)} aria-label="Remover a exceção"
                  style={{ border: 'none', background: 'none', color: 'var(--ink-3)', cursor: 'pointer', display: 'flex' }}
                ><Trash2 size={13} /></button>
              )}
            </div>
          ))}
        </div>
      )}

      {podeEditar && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label style={{ ...campo, width: 120 }}>
            <span>Data</span>
            <input
              value={form.data} placeholder="DD/MM/AAAA"
              onChange={e => setForm(f => ({ ...f, data: maskDate(e.target.value) }))}
            />
          </label>
          <label style={{ ...campo, flex: 1, minWidth: 180 }}>
            <span>Motivo</span>
            <input
              value={form.motivo} maxLength={200}
              onChange={e => setForm(f => ({ ...f, motivo: e.target.value }))}
              placeholder="Ex.: recesso de fim de ano"
            />
          </label>
          <label style={{ ...campo, flexDirection: 'row', alignItems: 'center', gap: 7, paddingBottom: 7 }}>
            <input
              type="checkbox" checked={form.trabalha}
              onChange={e => setForm(f => ({ ...f, trabalha: e.target.checked }))}
            />
            <span>Trabalha neste dia</span>
          </label>
          <Btn onClick={adicionar} disabled={!form.data || salvar.isPending}>
            <Plus size={14} /> Adicionar
          </Btn>
        </div>
      )}
      <FieldError msg={erros.data || erros.detail || erros.non_field_errors} />
      <p style={{ ...ajuda, marginTop: 10 }}>
        A exceção vence tudo: o feriado e a regra da semana. É como o mutirão de sábado entra e como
        a parada de chuva sai.
      </p>
    </Card>
  )
}

/**
 * A conferência — e o vínculo com o módulo Calendário.
 *
 * Expediente é a coisa mais fácil de configurar errado e a mais cara de
 * descobrir errado: o erro só aparece como *"o prazo não bate"*, três meses
 * depois. Então a tela não se contenta em salvar — ela **prova**: numa janela
 * real, quantos dias úteis dá, e quais feriados saíram da conta.
 *
 * É aqui que os dois módulos conversam na tela: os feriados são do
 * [Calendário](../../calendar), não do PDCA, e a base deles é global e nasce
 * vazia. Um calendário que promete descontá-los sobre uma base vazia devolve a
 * conta sem eles — número errado com cara de certo —, e por isso o aviso é
 * grande e o caminho para lá está a um clique.
 */
function Conferencia({ calendario }: { calendario: Calendario }) {
  const hoje = new Date()
  const [janela, setJanela] = useState(() => ({
    inicio: isoDe(hoje),
    fim: isoDe(new Date(hoje.getFullYear(), hoje.getMonth() + 3, hoje.getDate())),
  }))
  const conta = useDiasUteis(calendario.calendario_id, janela.inicio, janela.fim)

  const proporcao = useMemo(() => {
    if (!conta.data?.dias_corridos) return null
    return Math.round((conta.data.dias_uteis / conta.data.dias_corridos) * 100)
  }, [conta.data])

  return (
    <Card style={{ padding: 18 }}>
      <SectionHead
        sub="O que este expediente produz numa janela real"
        right={
          <a
            href="/app/calendario"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--brand)' }}
          >
            Módulo Calendário <ExternalLink size={12} />
          </a>
        }
      >
        Conferência
      </SectionHead>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 14 }}>
        <label style={{ ...campo, width: 150 }}>
          <span>De</span>
          <input type="date" value={janela.inicio} onChange={e => setJanela(j => ({ ...j, inicio: e.target.value }))} />
        </label>
        <label style={{ ...campo, width: 150 }}>
          <span>Até</span>
          <input type="date" value={janela.fim} onChange={e => setJanela(j => ({ ...j, fim: e.target.value }))} />
        </label>
      </div>

      {conta.isLoading && <p style={ajuda}>Contando…</p>}
      {conta.data && (
        <>
          <div style={{ display: 'flex', gap: 22, flexWrap: 'wrap', alignItems: 'baseline' }}>
            <span style={{ fontSize: 26, fontWeight: 700 }} className="num">{conta.data.dias_uteis}</span>
            <span style={{ fontSize: 13, color: 'var(--ink-2)' }}>
              dias úteis em {conta.data.dias_corridos} corridos
              {proporcao != null && <span style={{ color: 'var(--ink-3)' }}> · {proporcao}% do período</span>}
            </span>
          </div>

          {!conta.data.feriados_sincronizados && calendario.considera_feriados && (
            <div style={{
              marginTop: 12, padding: '10px 12px', borderRadius: 8, fontSize: 12.5, lineHeight: 1.55,
              background: 'var(--danger-soft)', color: 'var(--danger-ink)',
            }}>
              <strong>A base de feriados está vazia.</strong> Este calendário promete descontá-los, e a
              conta acima saiu <strong>sem nenhum</strong> — o prazo que o CPM devolver será menor que
              o real. Quem enche essa base é o módulo Calendário.
            </div>
          )}

          {conta.data.feriados.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--ink-3)', fontWeight: 700 }}>
                Feriados que saíram da conta
              </span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 7 }}>
                {conta.data.feriados.map(f => (
                  <span key={f.data} style={{
                    fontSize: 12, padding: '3px 9px', borderRadius: 999,
                    background: 'var(--inset)', color: 'var(--ink-2)',
                  }}>
                    <span className="num">{dateToBR(f.data)}</span> · {f.nome}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  )
}

const isoDe = (d: Date) =>
  d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')

const campo: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 5, fontSize: 12.5 }
const ajuda: React.CSSProperties = { fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5, margin: 0 }
