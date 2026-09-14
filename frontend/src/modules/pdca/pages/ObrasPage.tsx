import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CalendarClock, CalendarDays, GanttChartSquare, Library, Plus } from 'lucide-react'
import { Btn, Card, Empty, Loading, Modal, Pill } from '@/components/malha'
import type { PillKind } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { maxVigenciaISO, minVigenciaISO, validateISO_Vigencia } from '@/utils/dates'
import { useCalendarios, useCriarCronograma, useCronogramas, useModelos, useObras } from '../hooks'
import { ModalAplicarModelo } from '../components/PlanoModelo'
import type { Cronograma, StatusCronograma } from '../types'

const CORES: Record<StatusCronograma, PillKind> = {
  vigente: 'good',
  rascunho: 'accent',
  substituido: 'slate',
}

export default function ObrasPage() {
  const navegar = useNavigate()
  const { hasPermission } = useAuth()
  const podeCriar = hasPermission('pdca.cronograma.edit')
  const obras = useObras()
  const cronogramas = useCronogramas({ page_size: 200 })
  const [criando, setCriando] = useState(false)
  const [aplicandoEm, setAplicandoEm] = useState<{ obra: number; nome: string } | null>(null)
  //: Só para decidir se o botão de aplicar nasce ativo. A biblioteca inteira só
  //: é carregada quando alguém abre o modal — a lista de obras não precisa dela.
  const modelos = useModelos(podeCriar)
  const temModelos = modelos.data ? modelos.data.length > 0 : undefined

  const planoDaObra = useMemo(() => {
    const mapa = new Map<number, Cronograma>()
    for (const c of cronogramas.data?.results ?? []) {
      const atual = mapa.get(c.obra)
      if (!atual || c.versao > atual.versao) mapa.set(c.obra, c)
    }
    return mapa
  }, [cronogramas.data])

  if (obras.isLoading || cronogramas.isLoading) return <Loading o="as obras e os cronogramas" />

  const lista = obras.data ?? []

  return (
    <div style={{ padding: '26px 24px', display: 'flex', flexDirection: 'column', gap: 18 }}>
      <header style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26 }}>Planejamento</h1>
          <p style={{ margin: '6px 0 0', color: 'var(--ink-2)', fontSize: 14, maxWidth: 620 }}>
            O plano de tempo da obra: estrutura analítica, precedências, caminho crítico e linha de
            base. A unidade de trabalho aqui é a <strong>obra</strong> — escolha uma para abrir o
            cronograma dela.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Btn onClick={() => navegar('/app/pdca/expediente')} title="Quando a empresa e as obras trabalham">
            <CalendarDays size={15} /> Expediente
          </Btn>
          {podeCriar && (
            <Btn variant="brand" onClick={() => setCriando(true)}><Plus size={15} /> Novo cronograma</Btn>
          )}
        </div>
      </header>

      {lista.length === 0 ? (
        <Empty>Nenhuma obra cadastrada. O cronograma pertence a uma obra — cadastre a obra primeiro.</Empty>
      ) : (
        <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))' }}>
          {lista.map(obra => {
            const plano = planoDaObra.get(obra.obra_id)
            return (
              <Card key={obra.obra_id}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                    <h3 style={{ margin: 0, fontSize: 15.5 }}>{obra.nome_obra}</h3>
                    {plano && <Pill kind={CORES[plano.status]}>{plano.status_rotulo}</Pill>}
                  </div>

                  {plano ? (
                    <>
                      <dl style={linhaDados}>
                        <div><dt>Versão</dt><dd className="num">v{plano.versao}</dd></div>
                        <div><dt>Atividades</dt><dd className="num">{plano.atividades_count}</dd></div>
                        <div>
                          <dt>Término</dt>
                          <dd className="num">{plano.termino_calculado ? formatar(plano.termino_calculado) : 'sem cálculo'}</dd>
                        </div>
                      </dl>
                      <Btn variant="ghost" onClick={() => navegar(`/app/pdca/obra/${obra.obra_id}/cronograma/${plano.cronograma_id}`)}>
                        <GanttChartSquare size={15} /> Abrir o cronograma
                      </Btn>
                    </>
                  ) : (
                    <>
                      <p style={{ margin: 0, fontSize: 13, color: 'var(--ink-3)' }}>
                        Esta obra ainda não tem plano de tempo.
                      </p>
                      {podeCriar && (
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                          <Btn variant="ghost" onClick={() => setCriando(true)}>
                            <CalendarClock size={15} /> Criar do zero
                          </Btn>
                          {/* O caminho que o dono pediu: o empreendimento de 300
                              unidades não se planeja 300 vezes. */}
                          <Btn
                            variant="brand"
                            disabled={temModelos === false}
                            title={temModelos === false
                              ? 'A empresa ainda não tem plano modelo — salve um cronograma pronto na biblioteca'
                              : 'Aplicar um padrão da biblioteca da empresa'}
                            onClick={() => setAplicandoEm({ obra: obra.obra_id, nome: obra.nome_obra })}
                          >
                            <Library size={15} /> Aplicar modelo
                          </Btn>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {criando && <ModalNovoCronograma aoFechar={() => setCriando(false)} />}

      {aplicandoEm && (
        <ModalAplicarModelo
          obra={aplicandoEm.obra}
          obraNome={aplicandoEm.nome}
          aoFechar={() => setAplicandoEm(null)}
          aoAplicar={novo => {
            setAplicandoEm(null)
            navegar(`/app/pdca/obra/${novo.obra}/cronograma/${novo.cronograma_id}`)
          }}
        />
      )}
    </div>
  )
}

function ModalNovoCronograma({ aoFechar }: { aoFechar: () => void }) {
  const navegar = useNavigate()
  const obras = useObras()
  const [obra, setObra] = useState<number | ''>('')
  //: `para_obra` e não `obra`: o filtro exato casaria só os calendários DESTA
  //: obra e esconderia os da empresa — que são os que existem para valer em
  //: todas (D118). A regra do servidor é a mesma do cálculo: o da obra, mais os
  //: da empresa, nunca o de uma obra vizinha.
  const calendarios = useCalendarios(obra ? { para_obra: obra } : {})
  const criar = useCriarCronograma()
  const [form, setForm] = useState({ descricao: '', data_inicio: '', calendario: '' as number | '' })
  const [erros, setErros] = useState<FieldErrors>({})

  const enviar = async () => {
    setErros({})
    try {
      const criado = await criar.mutateAsync({
        obra: Number(obra),
        descricao: form.descricao,
        data_inicio: form.data_inicio,
        calendario: form.calendario === '' ? null : Number(form.calendario),
      })
      navegar(`/app/pdca/obra/${criado.obra}/cronograma/${criado.cronograma_id}`)
    } catch (err) {
      setErros(parseApiErrors(err))
    }
  }

  const opcoes = calendarios.data ?? []

  return (
    <Modal titulo="Novo cronograma" onClose={aoFechar}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '4px 2px' }}>
        <FormErrorBanner errors={erros} />

        <label style={campo}>
          <span>Obra</span>
          <select value={obra} onChange={e => { setObra(e.target.value === '' ? '' : Number(e.target.value)); setForm(f => ({ ...f, calendario: '' })) }}>
            <option value="">Selecione…</option>
            {(obras.data ?? []).map(o => <option key={o.obra_id} value={o.obra_id}>{o.nome_obra}</option>)}
          </select>
          <FieldError msg={erros.obra} />
        </label>

        <label style={campo}>
          <span>Descrição</span>
          <input value={form.descricao} onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))}
            placeholder="Plano de execução — obra completa" />
          <FieldError msg={erros.descricao} />
        </label>

        <label style={campo}>
          <span>Início do plano</span>
          <input type="date" value={form.data_inicio}
            min={minVigenciaISO()} max={maxVigenciaISO()}
            onChange={e => setForm(f => ({ ...f, data_inicio: e.target.value }))}
            onBlur={e => {
              const erro = validateISO_Vigencia(e.target.value)
              if (erro) setErros(p => ({ ...p, data_inicio: erro }))
            }} />
          <FieldError msg={erros.data_inicio} />
        </label>

        <label style={campo}>
          <span>Calendário de trabalho</span>
          <select value={form.calendario} onChange={e => setForm(f => ({ ...f, calendario: e.target.value === '' ? '' : Number(e.target.value) }))}>
            <option value="">Sem calendário</option>
            {opcoes.map(c => (
              <option key={c.calendario_id} value={c.calendario_id}>
                {c.nome}{c.padrao ? ' (padrão da empresa)' : ''}
              </option>
            ))}
          </select>
          <FieldError msg={erros.calendario} />
          {obra !== '' && !calendarios.isLoading && opcoes.length === 0 ? (
            // Select com uma opção só ("Sem calendário") e nenhuma explicação é
            // como o plano nasce sem prazo sem ninguém perceber. O expediente é
            // cadastro que alguém faz uma vez — e o caminho fica a um clique.
            <small style={{ color: 'var(--accent-ink)', fontSize: 11.5, lineHeight: 1.6 }}>
              Esta empresa ainda não tem expediente cadastrado. Sem ele o plano até nasce, mas o
              CPM não calcula — converter duração em data exige saber quando se trabalha.{' '}
              <Link to="/app/pdca/expediente" style={{ color: 'var(--brand)' }}>
                Cadastrar o expediente
              </Link>{' '}
              leva um minuto e vale para todas as obras.
            </small>
          ) : (
            <small style={{ color: 'var(--ink-3)', fontSize: 11.5 }}>
              Sem calendário o CPM não calcula — converter duração em data exige saber quando a
              empresa trabalha.
            </small>
          )}
        </label>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn variant="ghost" onClick={aoFechar}>Cancelar</Btn>
          <Btn onClick={enviar} disabled={!obra || !form.descricao || !form.data_inicio || criar.isPending}>
            {criar.isPending ? 'Criando…' : 'Criar'}
          </Btn>
        </div>
      </div>
    </Modal>
  )
}

const campo: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 5, fontSize: 13 }
const linhaDados: React.CSSProperties = { display: 'flex', gap: 18, margin: 0, fontSize: 12.5 }

function formatar(iso: string): string {
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}
