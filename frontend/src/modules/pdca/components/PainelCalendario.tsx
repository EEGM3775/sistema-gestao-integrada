import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Btn, Card, Empty, Loading, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { dateToBR, maxCalendarioISO, minCalendarioISO } from '@/utils/dates'
import { expedientes } from '../api/montagemApi'
import { pdcaKeys } from '../api/queryKeys'
import { useCalendarios } from '../hooks'
import { mensagemDe } from '../montagem'
import type { CalendarioTrabalho, LocalidadeDosFeriados } from '../types'

type CampoDoDia =
  | 'trabalha_segunda' | 'trabalha_terca' | 'trabalha_quarta' | 'trabalha_quinta'
  | 'trabalha_sexta' | 'trabalha_sabado' | 'trabalha_domingo'

const DIAS: { campo: CampoDoDia; sigla: string; nome: string }[] = [
  { campo: 'trabalha_segunda', sigla: 'S', nome: 'Segunda' },
  { campo: 'trabalha_terca', sigla: 'T', nome: 'Terça' },
  { campo: 'trabalha_quarta', sigla: 'Q', nome: 'Quarta' },
  { campo: 'trabalha_quinta', sigla: 'Q', nome: 'Quinta' },
  { campo: 'trabalha_sexta', sigla: 'S', nome: 'Sexta' },
  { campo: 'trabalha_sabado', sigla: 'S', nome: 'Sábado' },
  { campo: 'trabalha_domingo', sigla: 'D', nome: 'Domingo' },
]

const ESTILO_CAMPO = {
  fontSize: 12.5, padding: '5px 8px', background: 'var(--surface)', color: 'var(--ink)',
  border: '1px solid var(--line)', borderRadius: 'var(--r-sm)',
} as const

/** O expediente é o que converte duração em data. Mora dentro do posto que o
 *  consome — configuração com item de menu próprio vira assunto, e assunto
 *  vira porta. Aqui ele também **nasce**: sem expediente o plano não calcula
 *  prazo, e mandar a pessoa a outro lugar cadastrá-lo era um beco sem saída. */
export function PainelCalendario({ obraId }: { obraId: number }) {
  const { data, isLoading, isError } = useCalendarios(obraId)
  const { hasPermission } = useAuth()
  const pode = hasPermission('pdca.calendario.edit')
  const [criando, setCriando] = useState(false)

  if (isLoading) return <Loading o="os expedientes" />
  if (isError) {
    return (
      <Card>
        <Empty>Não foi possível carregar os expedientes. Tente de novo.</Empty>
      </Card>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {(!data || data.length === 0) && !criando && (
        <Card>
          <Empty>
            <span style={{ lineHeight: 1.6 }}>
              Ainda não há expediente. É ele que diz em que dias a obra trabalha — sem ele o plano não
              calcula datas.
            </span>
            {pode && <Btn variant="primary" onClick={() => setCriando(true)}>Cadastrar o expediente</Btn>}
          </Empty>
        </Card>
      )}
      {criando && (
        <Card>
          <FormularioDeExpediente obraId={obraId} aoConcluir={() => setCriando(false)} aoCancelar={() => setCriando(false)} />
        </Card>
      )}
      {data && data.length > 0 && !criando && pode && (
        <div><Btn tam="sm" onClick={() => setCriando(true)}>+ Novo expediente</Btn></div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
        {(data ?? []).map((cal) => <CartaoDoExpediente key={cal.calendario_id} cal={cal} obraId={obraId} pode={pode} />)}
      </div>
    </div>
  )
}

/** "· de Nazaré/BA (endereço da obra)" — de onde são os feriados que o prazo pula. */
function rotuloDoLugar(lugar: LocalidadeDosFeriados | null | undefined, daEmpresa: boolean): string {
  if (!lugar || lugar.fonte === 'nacional') {
    return daEmpresa
      ? ' · os do lugar de cada obra que o usa'
      : ' · só os nacionais (o endereço da obra não diz cidade/UF)'
  }
  const onde = lugar.cidade ? `${lugar.cidade}/${lugar.uf}` : lugar.uf
  return ` · de ${onde}${lugar.fonte === 'obra' ? ' (endereço da obra)' : ''}`
}

function CartaoDoExpediente({ cal, obraId, pode }: { cal: CalendarioTrabalho; obraId: number; pode: boolean }) {
  const qc = useQueryClient()
  const [nova, setNova] = useState<{ data: string; trabalha: boolean; motivo: string } | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  // O Gantt também: o dia que mudou pode cair dentro de uma barra já calculada.
  const atualizar = () => Promise.all([
    qc.invalidateQueries({ queryKey: pdcaKeys.calendarios(obraId) }),
    qc.invalidateQueries({ queryKey: pdcaKeys.cronogramas.raiz() }),
  ])

  async function guardar() {
    if (!nova?.data) return
    setErro(null)
    try {
      await expedientes.criarExcecao({ calendario: cal.calendario_id, ...nova, motivo: nova.motivo.trim() })
      setNova(null)
      await atualizar()
    } catch (e) {
      setErro(mensagemDe(e))
    }
  }

  return (
    <Card>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          <span style={{ flex: 1, fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>{cal.nome}</span>
          <Pill kind={cal.obra ? 'accent' : 'slate'}>{cal.obra ? 'desta obra' : 'da empresa'}</Pill>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {DIAS.map((d) => {
            const trabalha = Boolean(cal[d.campo])
            return (
              <span
                key={d.campo}
                title={`${d.nome}: ${trabalha ? 'trabalha' : 'não trabalha'}`}
                style={{
                  width: 24, height: 24, borderRadius: 5, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 10.5, fontWeight: 700, fontFamily: 'var(--mono)',
                  background: trabalha ? 'var(--accent-soft)' : 'var(--inset)',
                  color: trabalha ? 'var(--accent-ink)' : 'var(--ink-3)',
                }}
              >
                {d.sigla}
              </span>
            )
          })}
        </div>
        <div style={{ display: 'flex', gap: 14, fontSize: 12, color: 'var(--ink-2)' }}>
          <span><span style={{ color: 'var(--ink-3)' }}>Jornada </span><span style={{ fontFamily: 'var(--mono)' }}>{cal.horas_por_dia} h</span></span>
          <span style={{ color: cal.considera_feriados ? 'var(--ink-2)' : 'var(--ink-3)' }}>
            {cal.considera_feriados ? `Respeita feriados${rotuloDoLugar(cal.localidade_feriados, cal.obra == null)}` : 'Ignora feriados'}
          </span>
        </div>

        <div style={{ borderTop: '1px solid var(--line-2)', paddingTop: 9, display: 'flex', flexDirection: 'column', gap: 5 }}>
          <div style={{ fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-3)', fontWeight: 700 }}>
            Exceções ({cal.excecoes.length}) — recesso, chuva, mutirão de sábado
          </div>
          {cal.excecoes.map((e) => (
            <div key={e.excecao_id} style={{ display: 'flex', gap: 8, fontSize: 11.5, alignItems: 'center' }}>
              <span style={{ fontFamily: 'var(--mono)', color: 'var(--ink-2)' }}>{dateToBR(e.data)}</span>
              <span style={{ color: e.trabalha ? 'var(--good-ink)' : 'var(--danger-ink)' }}>{e.trabalha ? 'trabalha' : 'para'}</span>
              <span style={{ color: 'var(--ink-3)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.motivo}</span>
              {pode && (
                <button
                  type="button"
                  aria-label="Remover exceção"
                  title="Remover exceção"
                  onClick={async () => { await expedientes.removerExcecao(e.excecao_id); await atualizar() }}
                  style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--ink-3)' }}
                >
                  ×
                </button>
              )}
            </div>
          ))}
          {pode && (nova ? (
            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', alignItems: 'center' }}>
              <input type="date" min={minCalendarioISO} max={maxCalendarioISO} value={nova.data} onChange={(e) => setNova({ ...nova, data: e.target.value })} style={ESTILO_CAMPO} />
              <select value={nova.trabalha ? '1' : '0'} onChange={(e) => setNova({ ...nova, trabalha: e.target.value === '1' })} style={ESTILO_CAMPO}>
                <option value="0">para</option>
                <option value="1">trabalha</option>
              </select>
              <input value={nova.motivo} onChange={(e) => setNova({ ...nova, motivo: e.target.value })} placeholder="Motivo" style={{ ...ESTILO_CAMPO, flex: 1, minWidth: 100 }} />
              <Btn tam="sm" variant="primary" onClick={guardar} disabled={!nova.data}>Guardar</Btn>
              <Btn tam="sm" onClick={() => setNova(null)}>Cancelar</Btn>
            </div>
          ) : (
            <div><Btn tam="sm" onClick={() => setNova({ data: '', trabalha: false, motivo: '' })}>+ Exceção</Btn></div>
          ))}
          {erro && <span style={{ fontSize: 11.5, color: 'var(--danger-ink)' }}>{erro}</span>}
        </div>
      </div>
    </Card>
  )
}

/** O cadastro do expediente — usado aqui e no assistente que monta o plano. */
export function FormularioDeExpediente(
  { obraId, aoConcluir, aoCancelar }:
  { obraId: number; aoConcluir: (cal: CalendarioTrabalho) => void; aoCancelar?: () => void },
) {
  const qc = useQueryClient()
  const [nome, setNome] = useState('Expediente da obra')
  const [daEmpresa, setDaEmpresa] = useState(false)
  const [horas, setHoras] = useState('8')
  const [feriados, setFeriados] = useState(true)
  const [dias, setDias] = useState<Record<CampoDoDia, boolean>>({
    trabalha_segunda: true, trabalha_terca: true, trabalha_quarta: true, trabalha_quinta: true,
    trabalha_sexta: true, trabalha_sabado: false, trabalha_domingo: false,
  })
  const [erro, setErro] = useState<string | null>(null)
  const [gravando, setGravando] = useState(false)

  async function criar() {
    setErro(null)
    setGravando(true)
    try {
      const cal = await expedientes.criar({
        nome: nome.trim(), obra: daEmpresa ? null : obraId,
        horas_por_dia: horas.replace(',', '.'), considera_feriados: feriados, ...dias,
      })
      await qc.invalidateQueries({ queryKey: pdcaKeys.calendarios(obraId) })
      aoConcluir(cal)
    } catch (e) {
      setErro(mensagemDe(e))
    } finally {
      setGravando(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <label style={{ fontSize: 12.5, display: 'flex', gap: 8, alignItems: 'center' }}>
        Nome
        <input value={nome} onChange={(e) => setNome(e.target.value)} style={{ ...ESTILO_CAMPO, flex: 1 }} />
      </label>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>Dias trabalhados</span>
        {DIAS.map((d) => (
          <label key={d.campo} style={{ fontSize: 12, display: 'inline-flex', gap: 3, alignItems: 'center' }}>
            <input type="checkbox" checked={dias[d.campo]} onChange={(e) => setDias({ ...dias, [d.campo]: e.target.checked })} />
            {d.nome.slice(0, 3)}
          </label>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center' }}>
        <label style={{ fontSize: 12.5, display: 'flex', gap: 6, alignItems: 'center' }}>
          Jornada
          <input value={horas} onChange={(e) => setHoras(e.target.value)} inputMode="decimal" style={{ ...ESTILO_CAMPO, width: 50, textAlign: 'right' }} />
          h/dia
        </label>
        <label style={{ fontSize: 12.5, display: 'flex', gap: 6, alignItems: 'center' }}>
          <input type="checkbox" checked={feriados} onChange={(e) => setFeriados(e.target.checked)} />
          Não trabalha em feriado
        </label>
        <label style={{ fontSize: 12.5, display: 'flex', gap: 6, alignItems: 'center' }}>
          <input type="checkbox" checked={daEmpresa} onChange={(e) => setDaEmpresa(e.target.checked)} />
          Vale para todas as obras da empresa
        </label>
      </div>
      {erro && <span style={{ fontSize: 12, color: 'var(--danger-ink)' }}>{erro}</span>}
      <div style={{ display: 'flex', gap: 8 }}>
        <Btn variant="primary" onClick={criar} disabled={gravando || nome.trim().length < 2}>
          {gravando ? 'Gravando…' : 'Cadastrar expediente'}
        </Btn>
        {aoCancelar && <Btn onClick={aoCancelar}>Cancelar</Btn>}
      </div>
    </div>
  )
}
