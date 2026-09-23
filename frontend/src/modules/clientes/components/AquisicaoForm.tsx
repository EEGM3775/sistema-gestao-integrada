import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { X } from 'lucide-react'
import apiClient from '@/api/apiClient'
import type {
  ClienteEmpreendimento, ClienteEmpreendimentoFormData, CondicoesPagamento,
  Empreendimento, IndiceEconomico, SimulacaoPlano, Unidade,
} from '@/types'
import { buscarUnidadesDisponiveis } from '@/modules/empreendimentos/hooks/useUnidades'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { validateISO_Pagamento, minCalendarioISO, maxCalendarioISO } from '@/utils/dates'

/**
 * A venda de uma unidade — escolher **qual** e montar a proposta.
 *
 * A identificação da unidade não se digita mais aqui: ela é cadastro do
 * empreendimento (aba Unidades), e este formulário só escolhe uma das que estão
 * à venda. Era daí que vinha o conflito — rótulo livre e campos estruturados
 * preenchidos na venda podiam divergir, e o mesmo lote podia ser vendido duas
 * vezes.
 *
 * O preço parte do **valor de tabela** da unidade e o que o cliente paga sai de
 * uma conta: desconto → entrada (sem juros) → saldo em N parcelas por Price ou
 * SAC → balões. A conta é feita **no backend** (`/simular/`), a cada mudança:
 * repetir a fórmula aqui criaria duas matemáticas para o mesmo contrato, e a da
 * tela seria a que o cliente vê.
 */
interface Props {
  open: boolean
  clienteId: number
  onClose: () => void
  onSave: (data: ClienteEmpreendimentoFormData) => Promise<void>
  initial?: ClienteEmpreendimento | null
}

/**
 * A regra de o que cada condição de pagamento comporta **vem do backend**
 * (`GET /api/clientes-empreendimentos/condicoes/`), e não daqui.
 *
 * A condição é a primeira pergunta da venda porque é ela que diz quais campos
 * existem: perguntar juros e sistema de amortização numa venda à vista não é só
 * ruído — é convidar o vendedor a preencher um prazo que o contrato não tem, e
 * depois ninguém sabe se o que está gravado é o combinado.
 *
 * Esta tabela morava aqui, em paralelo à do motor de cálculo. Duas cópias da
 * mesma regra é uma que um dia discorda da outra, e a que discorda em silêncio é
 * a da tela — porque ela some do rastro. Agora existe uma só, no mesmo lugar que
 * grava o carnê (`clientes/plano_pagamento.py::CONDICOES`).
 */
interface RegraDaCondicao {
  codigo: CondicoesPagamento
  rotulo: string
  entrada: boolean
  parcelas: boolean
  baloes: boolean
  /** O que sobra do valor negociado é quitado por fora (banco, permuta, cartão). */
  quitaFora: boolean
  nota: string
}

/** Enquanto o catálogo não chega, o formulário não some — mostra tudo e não
 *  apaga nada. Permissivo de propósito: o backend valida de qualquer forma, e
 *  esconder campo por causa de uma requisição lenta seria pior. */
const REGRA_PROVISORIA: RegraDaCondicao = {
  codigo: 'outro', rotulo: 'Outro',
  entrada: true, parcelas: true, baloes: true, quitaFora: false,
  nota: 'Carregando as regras desta condição…',
}

function maskCurrency(v: string) {
  const digits = v.replace(/\D/g, '')
  if (!digits) return ''
  return (parseInt(digits, 10) / 100).toLocaleString('pt-BR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })
}

const currencyToDecimal = (v: string) => v.replace(/\./g, '').replace(',', '.')

const brl = (v?: string | null) =>
  v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const hojeISO = () => new Date().toISOString().slice(0, 10)

/** Mesmo passo do backend: mês seguinte, com o dia 31 caindo no fim do mês curto. */
function somarMeses(iso: string, meses: number) {
  const [ano, mes, dia] = iso.split('-').map(Number)
  const alvo = new Date(ano, mes - 1 + meses, 1)
  const ultimo = new Date(alvo.getFullYear(), alvo.getMonth() + 1, 0).getDate()
  alvo.setDate(Math.min(dia, ultimo))
  return alvo.toISOString().slice(0, 10)
}

const EMPTY = (clienteId: number): ClienteEmpreendimentoFormData => ({
  cliente: clienteId,
  unidade: '',
  data_compra: hojeISO(),
  condicoes_pagamento: 'financiamento_direto',
  observacoes_compra: '',
  desconto_percentual: '0',
  desconto_valor: '0',
  entrada_valor: '0',
  entrada_parcelas: 1,
  entrada_primeiro_vencimento: hojeISO(),
  sistema_amortizacao: 'price',
  juros_mensal: '0',
  num_parcelas: 0,
  primeiro_vencimento: somarMeses(hojeISO(), 1),
  balao_valor: '0',
  balao_quantidade: 0,
  balao_periodicidade: 'anual',
  balao_primeiro_vencimento: '',
  indice_correcao: '',
  periodicidade_correcao: 'anual',
  data_base_correcao: '',
})

function toForm(a: ClienteEmpreendimento): ClienteEmpreendimentoFormData {
  return {
    cliente: a.cliente,
    unidade: a.unidade,
    data_compra: a.data_compra,
    condicoes_pagamento: a.condicoes_pagamento,
    observacoes_compra: a.observacoes_compra ?? '',
    desconto_percentual: a.desconto_percentual,
    desconto_valor: a.desconto_valor,
    entrada_valor: a.entrada_valor,
    entrada_parcelas: a.entrada_parcelas,
    entrada_primeiro_vencimento: a.entrada_primeiro_vencimento ?? a.data_compra,
    sistema_amortizacao: a.sistema_amortizacao,
    juros_mensal: a.juros_mensal,
    num_parcelas: a.num_parcelas,
    primeiro_vencimento: a.primeiro_vencimento ?? somarMeses(a.data_compra, 1),
    balao_valor: a.balao_valor,
    balao_quantidade: a.balao_quantidade,
    balao_periodicidade: a.balao_periodicidade,
    balao_primeiro_vencimento: a.balao_primeiro_vencimento ?? '',
    indice_correcao: a.indice_correcao ?? '',
    periodicidade_correcao: a.periodicidade_correcao ?? 'anual',
    data_base_correcao: a.data_base_correcao ?? '',
  }
}

const inputCls: React.CSSProperties = {
  width: '100%', padding: '8px 12px', borderRadius: '8px',
  border: '1.5px solid #e2e8f0', fontFamily: 'var(--font-body)',
  fontSize: '0.875rem', color: 'var(--color-text)', background: '#FFFFFF',
  outline: 'none', boxSizing: 'border-box',
}
const labelCls: React.CSSProperties = {
  display: 'block', fontSize: '0.75rem', fontWeight: 600,
  marginBottom: '4px', color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)',
}
const SectionTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p style={{
    fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em',
    textTransform: 'uppercase', color: 'var(--color-text-muted)',
    marginTop: '10px', marginBottom: '-2px', fontFamily: 'var(--font-body)',
  }}>{children}</p>
)

const AquisicaoForm: React.FC<Props> = ({ open, clienteId, onClose, onSave, initial }) => {
  const [form, setForm] = useState<ClienteEmpreendimentoFormData>(EMPTY(clienteId))
  const [empreendimentos, setEmpreendimentos] = useState<Empreendimento[]>([])
  const [empSelecionado, setEmpSelecionado] = useState<number | ''>('')
  const [unidades, setUnidades] = useState<Unidade[]>([])
  const [carregandoUnidades, setCarregandoUnidades] = useState(false)
  const [displayEntrada, setDisplayEntrada] = useState('')
  const [displayBalao, setDisplayBalao] = useState('')
  const [simulacao, setSimulacao] = useState<SimulacaoPlano | null>(null)
  const [erroSimulacao, setErroSimulacao] = useState<string | null>(null)
  const [verCarne, setVerCarne] = useState(false)
  const [saving, setSaving] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [indices, setIndices] = useState<IndiceEconomico[]>([])
  const [condicoes, setCondicoes] = useState<RegraDaCondicao[]>([])

  useEffect(() => {
    apiClient.get('/empreendimentos/')
      .then(r => setEmpreendimentos(r.data.results ?? r.data))
      .catch(() => {})
    apiClient.get('/indices-economicos/')
      .then(r => setIndices(r.data))
      .catch(() => setIndices([]))
    apiClient.get('/clientes-empreendimentos/condicoes/')
      .then(r => setCondicoes(r.data.condicoes ?? []))
      .catch(() => setCondicoes([]))
  }, [])

  useEffect(() => {
    if (initial) {
      setForm(toForm(initial))
      setDisplayEntrada(Number(initial.entrada_valor).toLocaleString('pt-BR', { minimumFractionDigits: 2 }))
      setDisplayBalao(Number(initial.balao_valor).toLocaleString('pt-BR', { minimumFractionDigits: 2 }))
      setEmpSelecionado(initial.empreendimento)
    } else {
      setForm(EMPTY(clienteId))
      setDisplayEntrada('')
      setDisplayBalao('')
      setEmpSelecionado('')
    }
    setSimulacao(null)
    setErroSimulacao(null)
    setVerCarne(false)
    setFieldErrors({})
  }, [initial, open, clienteId])

  // As unidades à venda do empreendimento escolhido. Ao editar, a unidade atual
  // entra na lista mesmo estando "vendida" — senão sumiria do próprio formulário.
  useEffect(() => {
    if (!open) return
    setCarregandoUnidades(true)
    buscarUnidadesDisponiveis(
      empSelecionado === '' ? undefined : empSelecionado,
      undefined,
      initial?.unidade,
    )
      .then(setUnidades)
      .catch(() => setUnidades([]))
      .finally(() => setCarregandoUnidades(false))
  }, [open, empSelecionado, initial?.unidade])

  const unidadeEscolhida = useMemo(
    () => unidades.find(u => u.unidade_id === form.unidade) ?? null,
    [unidades, form.unidade],
  )

  // Simulação ao vivo, com folga para o usuário terminar de digitar. A conta é
  // do backend — a mesma que grava o contrato depois.
  const timer = useRef<number | undefined>(undefined)
  const simular = useCallback(() => {
    if (!form.unidade) { setSimulacao(null); return }
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(async () => {
      try {
        const { data } = await apiClient.post('/clientes-empreendimentos/simular/', {
          unidade: form.unidade,
          desconto_percentual: form.desconto_percentual || 0,
          desconto_valor: form.desconto_valor || 0,
          entrada_valor: form.entrada_valor || 0,
          entrada_parcelas: form.entrada_parcelas || 1,
          entrada_primeiro_vencimento: form.entrada_primeiro_vencimento || null,
          sistema_amortizacao: form.sistema_amortizacao,
          juros_mensal: form.juros_mensal || 0,
          num_parcelas: form.num_parcelas || 0,
          primeiro_vencimento: form.primeiro_vencimento || null,
          balao_valor: form.balao_valor || 0,
          balao_quantidade: form.balao_quantidade || 0,
          balao_periodicidade: form.balao_periodicidade,
          balao_primeiro_vencimento: form.balao_primeiro_vencimento || null,
          data_compra: form.data_compra || null,
          // Sem a condição, o backend calcularia um "à vista" como venda sem
          // plano e devolveria erro de saldo sem parcela — o painel mostraria
          // falha numa proposta que é válida.
          condicoes_pagamento: form.condicoes_pagamento,
        })
        setSimulacao(data)
        setErroSimulacao(null)
      } catch (err) {
        setSimulacao(null)
        const detalhe = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        setErroSimulacao(detalhe ?? 'Não foi possível calcular a proposta.')
      }
    }, 350)
  }, [form])

  useEffect(() => {
    simular()
    return () => window.clearTimeout(timer.current)
  }, [simular])

  if (!open) return null

  const set = (campo: keyof ClienteEmpreendimentoFormData, valor: string | number) =>
    setForm(anterior => ({ ...anterior, [campo]: valor }))

  const plano = condicoes.find(c => c.codigo === form.condicoes_pagamento) ?? REGRA_PROVISORIA

  /** Trocar a condição apaga o que ela não comporta. Sem isso, mudar de
   *  "financiamento direto" para "à vista" deixaria 60 parcelas gravadas num
   *  contrato que a tela mostra como pagamento único — e o carnê sairia com
   *  elas. O backend repete a limpeza (`normalizar_por_condicao`), porque a tela
   *  não é a única porta; aqui ela é imediata, para o vendedor ver o efeito. */
  const trocarCondicao = (valor: string) => {
    const novo = condicoes.find(c => c.codigo === valor) ?? REGRA_PROVISORIA
    setForm(anterior => ({
      ...anterior,
      condicoes_pagamento: valor as CondicoesPagamento,
      ...(novo.entrada ? {} : { entrada_valor: '0', entrada_parcelas: 1 }),
      ...(novo.parcelas ? {} : { num_parcelas: 0, juros_mensal: '0' }),
      ...(novo.baloes ? {} : { balao_valor: '0', balao_quantidade: 0, balao_primeiro_vencimento: '' }),
    }))
    if (!novo.entrada) setDisplayEntrada('')
    if (!novo.baloes) setDisplayBalao('')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setFieldErrors({})
    try {
      // "Sem correção" e "data-base = a da compra" são ausência, não string
      // vazia — o DRF recusaria '' num FK e num DateField nulável.
      await onSave({
        ...form,
        cliente: clienteId,
        indice_correcao: form.indice_correcao === '' ? null : form.indice_correcao,
        data_base_correcao: form.data_base_correcao || null,
      } as unknown as ClienteEmpreendimentoFormData)
      onClose()
    } catch (err) {
      setFieldErrors(parseApiErrors(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.3)' }} onClick={onClose} />
      <div className="fixed top-0 right-0 h-full z-50 flex flex-col"
        style={{ width: '520px', background: '#FFFFFF', boxShadow: '-4px 0 24px rgba(0,0,0,0.12)', overflow: 'hidden' }}>

        <div className="flex items-center justify-between px-6 py-4 shrink-0"
          style={{ borderBottom: '1px solid #e2e8f0' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: '1rem', color: 'var(--color-brand)' }}>
            {initial ? 'Editar Aquisição' : 'Nova Aquisição'}
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        <form id="aquisicao-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-3">
          <FormErrorBanner errors={fieldErrors} />

          <SectionTitle>Unidade</SectionTitle>
          <div>
            <label style={labelCls}>Empreendimento</label>
            <select style={inputCls} value={empSelecionado}
              onChange={e => {
                setEmpSelecionado(e.target.value === '' ? '' : Number(e.target.value))
                set('unidade', '')
              }}>
              <option value="">Todos</option>
              {empreendimentos.map(emp => (
                <option key={emp.empreendimento_id} value={emp.empreendimento_id}>{emp.empreendimento}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={labelCls}>Unidade *</label>
              <select required style={inputCls} value={form.unidade}
                onChange={e => set('unidade', Number(e.target.value))}>
                <option value="">
                  {carregandoUnidades ? 'Carregando…' : 'Selecione a unidade…'}
                </option>
                {unidades.map(u => (
                  <option key={u.unidade_id} value={u.unidade_id}>
                    {u.rotulo} — {u.empreendimento_nome} ({brl(u.valor_base)})
                  </option>
                ))}
              </select>
              <FieldError msg={fieldErrors.unidade} />
              {!carregandoUnidades && unidades.length === 0 && (
                <p style={{ fontSize: '0.72rem', color: '#b45309', marginTop: 4 }}>
                  Nenhuma unidade à venda. Cadastre unidades na aba Unidades do empreendimento.
                </p>
              )}
            </div>
            <div>
              <label style={labelCls}>Data da compra *</label>
              <input required type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputCls} value={form.data_compra}
                onChange={e => { set('data_compra', e.target.value); setFieldErrors(p => ({ ...p, data_compra: '' })) }}
                onBlur={e => { const err = validateISO_Pagamento(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_compra: err })) }} />
              <FieldError msg={fieldErrors.data_compra} />
            </div>
          </div>

          {unidadeEscolhida && (
            <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
              Valor de tabela: <strong style={{ color: 'var(--color-text)' }}>{brl(unidadeEscolhida.valor_base)}</strong>
              {unidadeEscolhida.area_privativa && ` · ${Number(unidadeEscolhida.area_privativa).toLocaleString('pt-BR')} m²`}
            </p>
          )}

          {/* A condição vem antes do plano porque é ela que decide quais campos
              o plano tem. */}
          <SectionTitle>Condições de pagamento</SectionTitle>
          <div>
            <label style={labelCls}>Como o cliente paga *</label>
            <select required style={inputCls} value={form.condicoes_pagamento}
              disabled={condicoes.length === 0}
              onChange={e => trocarCondicao(e.target.value)}>
              {condicoes.length === 0 && <option value="">Carregando condições…</option>}
              {condicoes.map(o => <option key={o.codigo} value={o.codigo}>{o.rotulo}</option>)}
            </select>
            <FieldError msg={fieldErrors.condicoes_pagamento} />
            <p style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: 4 }}>
              {plano.nota}
            </p>
          </div>

          <SectionTitle>Proposta</SectionTitle>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={labelCls}>Desconto (%)</label>
              <input style={inputCls} value={form.desconto_percentual} inputMode="decimal"
                onChange={e => set('desconto_percentual', e.target.value.replace(',', '.'))} />
            </div>
            {plano.entrada && (
              <div>
                <label style={labelCls}>
                  {form.condicoes_pagamento === 'cartao' ? 'Valor no cartão (R$)' : 'Entrada / ATO (R$)'}
                </label>
                <input style={inputCls} value={displayEntrada} placeholder="0,00"
                  onChange={e => {
                    const mascarado = maskCurrency(e.target.value)
                    setDisplayEntrada(mascarado)
                    set('entrada_valor', currencyToDecimal(mascarado) || '0')
                  }} />
              </div>
            )}
          </div>

          {plano.entrada && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label style={labelCls}>Entrada em (x)</label>
                <input type="number" min={1} max={36} style={inputCls} value={form.entrada_parcelas}
                  onChange={e => set('entrada_parcelas', Number(e.target.value))} />
              </div>
              <div>
                <label style={labelCls}>1º venc. da entrada</label>
                <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputCls} value={form.entrada_primeiro_vencimento}
                  onChange={e => set('entrada_primeiro_vencimento', e.target.value)} />
              </div>
            </div>
          )}

          {plano.parcelas && (
            <>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label style={labelCls}>Sistema</label>
                  <select style={inputCls} value={form.sistema_amortizacao}
                    onChange={e => set('sistema_amortizacao', e.target.value)}>
                    <option value="price">Price (parcela fixa)</option>
                    <option value="sac">SAC (decrescente)</option>
                  </select>
                </div>
                <div>
                  <label style={labelCls}>Juros (% ao mês)</label>
                  <input style={inputCls} value={form.juros_mensal} inputMode="decimal"
                    onChange={e => set('juros_mensal', e.target.value.replace(',', '.'))} />
                </div>
                <div>
                  <label style={labelCls}>Nº de parcelas</label>
                  <input type="number" min={0} max={480} style={inputCls} value={form.num_parcelas}
                    onChange={e => set('num_parcelas', Number(e.target.value))} />
                </div>
              </div>
              <div>
                <label style={labelCls}>1º venc. das parcelas</label>
                <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputCls} value={form.primeiro_vencimento}
                  onChange={e => set('primeiro_vencimento', e.target.value)} />
              </div>
            </>
          )}

          {plano.baloes && (
            <>
              {/* O nome de mercado é "anual/intercalada" — quase todo loteamento
                  tem uma por ano, casada com o 13º. */}
              <SectionTitle>Parcelas anuais (intercaladas)</SectionTitle>
              <p style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: -6 }}>
                Reforços que somam à mensal do mês em que caem. Abatem o saldo antes do
                parcelamento, então não pagam juros.
              </p>
              <div className="grid grid-cols-4 gap-3">
                <div style={{ gridColumn: 'span 2' }}>
                  <label style={labelCls}>Valor de cada (R$)</label>
                  <input style={inputCls} value={displayBalao} placeholder="0,00"
                    onChange={e => {
                      const mascarado = maskCurrency(e.target.value)
                      setDisplayBalao(mascarado)
                      set('balao_valor', currencyToDecimal(mascarado) || '0')
                    }} />
                </div>
                <div>
                  <label style={labelCls}>Quantas</label>
                  <input type="number" min={0} max={40} style={inputCls} value={form.balao_quantidade}
                    onChange={e => set('balao_quantidade', Number(e.target.value))} />
                </div>
                <div>
                  <label style={labelCls}>A cada</label>
                  <select style={inputCls} value={form.balao_periodicidade}
                    onChange={e => set('balao_periodicidade', e.target.value)}>
                    <option value="anual">12 meses</option>
                    <option value="semestral">6 meses</option>
                  </select>
                </div>
              </div>
              {form.balao_quantidade > 0 && (
                <div>
                  <label style={labelCls}>1º vencimento da anual</label>
                  <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputCls} value={form.balao_primeiro_vencimento}
                    onChange={e => set('balao_primeiro_vencimento', e.target.value)} />
                </div>
              )}
            </>
          )}

          {/* ── O resultado da conta ── */}
          {erroSimulacao && (
            <div style={{
              background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10,
              padding: '10px 12px', fontSize: '0.78rem', color: '#b91c1c',
            }}>
              {erroSimulacao}
            </div>
          )}

          {simulacao && (
            <div style={{ background: '#f8fafc', borderRadius: 10, padding: '12px 14px' }}>
              <div className="grid grid-cols-2 gap-y-1.5 gap-x-4" style={{ fontSize: '0.78rem' }}>
                <Linha rotulo="Valor de tabela" valor={brl(simulacao.valorTabela)} />
                <Linha rotulo="Desconto" valor={`− ${brl(simulacao.desconto)}`} />
                <Linha rotulo="Negociado (à vista)" valor={brl(simulacao.valorNegociado)} destaque />
                {/* Só entra no resumo o que a condição comporta: uma linha
                    "Juros do plano — R$ 0,00" numa venda à vista faz o leitor
                    procurar o juro que não existe. */}
                {plano.entrada && <Linha rotulo="Entrada" valor={brl(simulacao.entrada)} />}
                {plano.baloes && Number(simulacao.baloes) > 0 && (
                  <Linha rotulo="Anuais" valor={brl(simulacao.baloes)} />
                )}
                {plano.parcelas && <Linha rotulo="Saldo financiado" valor={brl(simulacao.saldoFinanciado)} />}
                {plano.parcelas && <Linha rotulo="Juros do plano" valor={brl(simulacao.totalJuros)} />}
                {/* O que o comprador paga, mas não à construtora e não por
                    boleto: o saldo que o banco quita, o bem da permuta, a parte
                    que passou na maquininha. Não é desconto nem dívida
                    esquecida — e sem esta linha a venda não fechava, porque o
                    motor a recusava por "sobrou saldo sem parcela". */}
                {Number(simulacao.foraDoCarne ?? 0) > 0 && (
                  <Linha rotulo="Quitado fora do carnê" valor={brl(simulacao.foraDoCarne)} />
                )}
                <Linha
                  rotulo={Number(simulacao.foraDoCarne ?? 0) > 0 ? 'Total no carnê' : 'Total a pagar'}
                  valor={brl(simulacao.total)}
                  destaque
                />
                {Number(simulacao.primeiraParcela) > 0 && (
                  <Linha
                    rotulo={form.sistema_amortizacao === 'sac' ? 'Parcela (1ª → última)' : 'Parcela mensal'}
                    valor={form.sistema_amortizacao === 'sac'
                      ? `${brl(simulacao.primeiraParcela)} → ${brl(simulacao.ultimaParcela)}`
                      : brl(simulacao.primeiraParcela)}
                    destaque
                  />
                )}
              </div>
              <button type="button" onClick={() => setVerCarne(v => !v)}
                style={{
                  marginTop: 10, background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                  fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-brand)',
                }}>
                {verCarne ? 'Ocultar' : `Ver as ${simulacao.parcelas.length} parcelas`}
              </button>
              {verCarne && (
                <div style={{ maxHeight: 220, overflowY: 'auto', marginTop: 8 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.72rem' }}>
                    <thead>
                      <tr style={{ color: 'var(--color-text-muted)', textAlign: 'left' }}>
                        <th style={{ padding: '3px 4px' }}>#</th>
                        <th style={{ padding: '3px 4px' }}>Tipo</th>
                        <th style={{ padding: '3px 4px' }}>Vencimento</th>
                        <th style={{ padding: '3px 4px', textAlign: 'right' }}>Valor</th>
                        <th style={{ padding: '3px 4px', textAlign: 'right' }}>Saldo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {simulacao.parcelas.map((p, i) => (
                        <tr key={`${p.tipo}-${p.numero}-${i}`} style={{ borderTop: '1px solid #e2e8f0' }}>
                          <td style={{ padding: '3px 4px' }}>{p.numero}</td>
                          <td style={{ padding: '3px 4px' }}>
                            {p.tipo === 'entrada' ? 'Entrada' : p.tipo === 'balao' ? 'Balão' : 'Parcela'}
                          </td>
                          {/* A data pagável, com a do contrato ao lado quando
                              as duas diferem. Mostrar só a ajustada faria o
                              vendedor procurar, no contrato, um dia 7 que a tela
                              insiste em chamar de 9. */}
                          <td style={{ padding: '3px 4px' }} title={p.ajusteMotivo || undefined}>
                            {p.vencimento.split('-').reverse().join('/')}
                            {p.vencimentoContratual && p.vencimentoContratual !== p.vencimento && (
                              <span style={{ color: 'var(--color-text-muted)' }}>
                                {' '}(era {p.vencimentoContratual.slice(8, 10)}/{p.vencimentoContratual.slice(5, 7)}
                                {p.ajusteMotivo ? `, ${p.ajusteMotivo}` : ''})
                              </span>
                            )}
                          </td>
                          <td style={{ padding: '3px 4px', textAlign: 'right' }}>{brl(p.valor)}</td>
                          <td style={{ padding: '3px 4px', textAlign: 'right', color: 'var(--color-text-muted)' }}>
                            {p.tipo === 'parcela' ? brl(p.saldo) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {/* O ajuste de dia útil dito na tela, com a ressalva de quando a
                  base de feriados nunca foi sincronizada: "ajustado para o
                  próximo dia útil" sem feriados carregados é meia verdade, e
                  meia verdade sobre vencimento vira boleto pago em atraso. */}
              {Number(simulacao.parcelasAjustadas ?? 0) > 0 && (
                <p style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)', marginTop: 8 }}>
                  {simulacao.parcelasAjustadas} parcela{simulacao.parcelasAjustadas !== 1 ? 's' : ''} caí
                  {simulacao.parcelasAjustadas !== 1 ? 'am' : 'a'} em fim de semana ou feriado e
                  {simulacao.parcelasAjustadas !== 1 ? ' foram' : ' foi'} para o próximo dia útil
                  {simulacao.calendario?.uf ? ` (feriados de ${simulacao.calendario.uf}` : ' (feriados nacionais'}
                  {simulacao.calendario?.municipio ? ' e do município' : ''}).
                </p>
              )}
              {simulacao.calendario && !simulacao.calendario.feriadosCarregados && (
                <p style={{ fontSize: '0.7rem', color: '#b45309', marginTop: 6 }}>
                  A base de feriados ainda não foi sincronizada: os vencimentos desviam de
                  sábado e domingo, mas <strong>não</strong> de feriado.
                </p>
              )}
              <p style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)', marginTop: 8 }}>
                Salvar registra a proposta. As parcelas só entram no financeiro pelo botão
                <strong> Gerar parcelas</strong>, depois de você conferir.
              </p>
            </div>
          )}

          {/* Só faz sentido em contrato com prazo: pagamento único não atravessa
              o tempo, então não há o que corrigir. */}
          {(plano.parcelas || plano.baloes) && (
            <>
              <SectionTitle>Correção monetária</SectionTitle>
              <p style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: -6 }}>
                Reajuste conta do <strong>aniversário da data-base</strong>, não da data do boleto —
                o boleto só carrega o valor já corrigido. Sem índice, o contrato é nominal.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label style={labelCls}>Índice</label>
                  <select style={inputCls} value={form.indice_correcao}
                    onChange={e => set('indice_correcao', e.target.value === '' ? '' : Number(e.target.value))}>
                    <option value="">Sem correção</option>
                    {indices.map(i => (
                      <option key={i.id} value={i.id} disabled={!i.ultimaCompetencia}>
                        {i.nome}
                        {i.ultimaCompetencia
                          ? ` — até ${i.ultimaCompetencia.slice(0, 7).split('-').reverse().join('/')}`
                          : ' — sem série carregada'}
                      </option>
                    ))}
                  </select>
                  <FieldError msg={fieldErrors.indice_correcao} />
                </div>
                {form.indice_correcao !== '' && (
                  <div>
                    <label style={labelCls}>Periodicidade</label>
                    <select style={inputCls} value={form.periodicidade_correcao}
                      onChange={e => set('periodicidade_correcao', e.target.value)}>
                      <option value="anual">Anual (aniversário do contrato)</option>
                      <option value="mensal">Mensal (INCC de obra)</option>
                    </select>
                  </div>
                )}
              </div>
              {form.indice_correcao !== '' && (
                <div>
                  <label style={labelCls}>Data-base</label>
                  <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputCls} value={form.data_base_correcao}
                    onChange={e => set('data_base_correcao', e.target.value)} />
                  <p style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)', marginTop: 4 }}>
                    Em branco, vale a data da compra — que é o usual.
                  </p>
                </div>
              )}
            </>
          )}

          <SectionTitle>Contrato</SectionTitle>
          <div>
            <label style={labelCls}>Observações</label>
            <textarea style={{ ...inputCls, minHeight: '64px', resize: 'vertical' }}
              value={form.observacoes_compra}
              onChange={e => set('observacoes_compra', e.target.value)} />
            <FieldError msg={fieldErrors.observacoes_compra} />
          </div>
        </form>

        <div className="flex items-center justify-end gap-3 px-6 py-4 shrink-0"
          style={{ borderTop: '1px solid #e2e8f0' }}>
          <button type="button" onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'none', border: '1.5px solid #e2e8f0', cursor: 'pointer',
              color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
            Cancelar
          </button>
          <button form="aquisicao-form" type="submit" disabled={saving || !form.unidade}
            className="px-5 py-2 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--color-brand)', color: '#FFFFFF', border: 'none',
              cursor: saving || !form.unidade ? 'not-allowed' : 'pointer',
              opacity: saving || !form.unidade ? 0.6 : 1,
              fontFamily: 'var(--font-body)' }}>
            {saving ? 'Salvando…' : initial ? 'Salvar' : 'Registrar aquisição'}
          </button>
        </div>
      </div>
    </>
  )
}

function Linha({ rotulo, valor, destaque }: { rotulo: string; valor: string; destaque?: boolean }) {
  return (
    <>
      <span style={{ color: 'var(--color-text-muted)' }}>{rotulo}</span>
      <span style={{
        textAlign: 'right', fontVariantNumeric: 'tabular-nums',
        fontWeight: destaque ? 700 : 500,
        color: destaque ? 'var(--color-brand)' : 'var(--color-text)',
      }}>
        {valor}
      </span>
    </>
  )
}

export default AquisicaoForm
