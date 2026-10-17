import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Plus, X } from 'lucide-react'
import apiClient from '@/api/apiClient'
import type {
  ClienteEmpreendimento, ClienteEmpreendimentoFormData, IndiceEconomico,
  MeioPagamento, SimulacaoPlano, TipoDeMeio, TipoMeioPagamento, Unidade,
} from '@/types'
import { buscarUnidadesDisponiveis } from '@/modules/empreendimentos/hooks/useUnidades'
import { SeletorDeEmpreendimento } from '@/components/malha'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { validateISO_Pagamento, minCalendarioISO, maxCalendarioISO } from '@/utils/dates'

/**
 * A venda de uma unidade — escolher **qual** e montar a proposta.
 *
 * A identificação da unidade não se digita aqui: ela é cadastro do
 * empreendimento (aba Unidades), e este formulário só escolhe uma das que estão
 * à venda.
 *
 * O preço parte do **valor de tabela** da unidade, menos o desconto, e o valor
 * negociado é dividido numa **lista livre de meios de pagamento** — entrada,
 * financiamento direto, anuais, banco, FGTS, permuta, cartão, outro — quantos a
 * negociação tiver. A conta é feita **no backend** (`/simular/`), a cada
 * mudança: repetir a fórmula aqui criaria duas matemáticas para o mesmo
 * contrato, e a da tela seria a que o cliente vê.
 */
interface Props {
  open: boolean
  clienteId: number
  onClose: () => void
  onSave: (data: ClienteEmpreendimentoFormData) => Promise<void>
  initial?: ClienteEmpreendimento | null
}

/**
 * Um meio no formulário. `valorTexto` é o que está no campo, com máscara; nas
 * anuais ele é o valor **de cada** uma, que é como o vendedor fala ("duas
 * anuais de 10 mil"), e o `valor` do meio é o total delas.
 */
interface MeioForm extends MeioPagamento {
  chave: number
  valorTexto: string
  /** Nas parcelas com datas livres, cada linha como está nos campos. */
  linhas: LinhaLivre[]
}

interface LinhaLivre {
  chave: number
  vencimento: string
  valorTexto: string
}

interface FormState extends Omit<ClienteEmpreendimentoFormData, 'meios'> {
  meios: MeioForm[]
}

/** A ordem em que "+ Adicionar" sugere o próximo meio: a de uma venda típica. */
const SUGESTAO: TipoMeioPagamento[] = [
  'entrada', 'financiamento_direto', 'anuais', 'financiamento_bancario', 'fgts',
  'datas_livres', 'permuta', 'cartao', 'outro', 'a_vista',
]

const NOME_DA_LINHA: Record<string, string> = {
  a_vista: 'À vista', entrada: 'Entrada', parcela: 'Parcela', balao: 'Anual',
  livre: 'Data livre', cartao: 'Cartão',
}

function maskCurrency(v: string) {
  const digits = v.replace(/\D/g, '')
  if (!digits) return ''
  return (parseInt(digits, 10) / 100).toLocaleString('pt-BR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })
}

const currencyToDecimal = (v: string) => v.replace(/\./g, '').replace(',', '.')

const brl = (v?: string | number | null) =>
  v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

const decimalParaTexto = (v: string | number) =>
  Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** Soma em centavos inteiros: somar reais em ponto flutuante erra o centavo
 *  que decide se a conta fecha. */
const centavos = (v: string | number) => Math.round(Number(v || 0) * 100)

const hojeISO = () => new Date().toISOString().slice(0, 10)

/** Mesmo passo do backend: mês seguinte, com o dia 31 caindo no fim do mês curto. */
function somarMeses(iso: string, meses: number) {
  const [ano, mes, dia] = iso.split('-').map(Number)
  const alvo = new Date(ano, mes - 1 + meses, 1)
  const ultimo = new Date(alvo.getFullYear(), alvo.getMonth() + 1, 0).getDate()
  alvo.setDate(Math.min(dia, ultimo))
  return alvo.toISOString().slice(0, 10)
}

let proximaChave = 1

function vencimentoPadrao(tipo: TipoMeioPagamento, dataCompra: string) {
  const base = dataCompra || hojeISO()
  if (tipo === 'financiamento_direto') return somarMeses(base, 1)
  if (tipo === 'anuais') return somarMeses(base, 12)
  return base
}

function novaLinha(vencimento: string, valorTexto = ''): LinhaLivre {
  return { chave: proximaChave++, vencimento, valorTexto }
}

function novoMeio(tipo: TipoMeioPagamento, dataCompra: string): MeioForm {
  return {
    chave: proximaChave++,
    tipo,
    valor: '0',
    valorTexto: '',
    descricao: '',
    parcelas: tipo === 'financiamento_direto' ? 12 : 1,
    primeiro_vencimento: vencimentoPadrao(tipo, dataCompra),
    juros_mensal: '0',
    sistema_amortizacao: 'price',
    periodicidade: 'anual',
    linhas: tipo === 'datas_livres' ? [novaLinha(somarMeses(dataCompra || hojeISO(), 1))] : [],
  }
}

function meioDaApi(m: MeioPagamento): MeioForm {
  const cada = m.tipo === 'anuais' && m.parcelas > 0 ? Number(m.valor) / m.parcelas : Number(m.valor)
  return {
    ...m,
    chave: proximaChave++,
    valorTexto: decimalParaTexto(cada),
    descricao: m.descricao ?? '',
    primeiro_vencimento: m.primeiro_vencimento ?? '',
    linhas: (m.cronograma ?? []).map(l => novaLinha(l.vencimento, decimalParaTexto(l.valor))),
  }
}

/** O total do meio a partir do que está nos campos — nas anuais, cada ×
 *  quantas; nas datas livres, a soma das linhas. */
function valorDoMeio(m: Pick<MeioForm, 'tipo' | 'valorTexto' | 'parcelas' | 'linhas'>) {
  if (m.tipo === 'datas_livres') {
    const soma = m.linhas.reduce((s, l) => s + centavos(currencyToDecimal(l.valorTexto) || '0'), 0)
    return (soma / 100).toFixed(2)
  }
  const digitado = currencyToDecimal(m.valorTexto) || '0'
  if (m.tipo !== 'anuais') return digitado
  return ((centavos(digitado) * Math.max(1, m.parcelas || 1)) / 100).toFixed(2)
}

const EMPTY = (clienteId: number): FormState => ({
  cliente: clienteId,
  unidade: '',
  data_compra: hojeISO(),
  observacoes_compra: '',
  desconto_percentual: '0',
  desconto_valor: '0',
  meios: [novoMeio('entrada', hojeISO())],
  indice_correcao: '',
  periodicidade_correcao: 'anual',
  data_base_correcao: '',
  multa_atraso_percentual: '',
  juros_mora_mensal_percentual: '',
})

function toForm(a: ClienteEmpreendimento): FormState {
  return {
    cliente: a.cliente,
    unidade: a.unidade,
    data_compra: a.data_compra,
    observacoes_compra: a.observacoes_compra ?? '',
    desconto_percentual: a.desconto_percentual,
    desconto_valor: a.desconto_valor,
    meios: (a.meios ?? []).map(meioDaApi),
    indice_correcao: a.indice_correcao ?? '',
    periodicidade_correcao: a.periodicidade_correcao ?? 'anual',
    data_base_correcao: a.data_base_correcao ?? '',
    multa_atraso_percentual: a.multa_atraso_percentual ?? '',
    juros_mora_mensal_percentual: a.juros_mora_mensal_percentual ?? '',
  }
}

/** O meio como a API recebe: sem o que é só do formulário. */
function meioParaApi(m: MeioForm): MeioPagamento {
  return {
    tipo: m.tipo,
    valor: m.valor,
    descricao: m.descricao,
    parcelas: m.parcelas,
    primeiro_vencimento: m.primeiro_vencimento || null,
    juros_mensal: m.juros_mensal || '0',
    sistema_amortizacao: m.sistema_amortizacao,
    periodicidade: m.periodicidade,
    cronograma: m.tipo === 'datas_livres'
      ? m.linhas.map(l => ({ vencimento: l.vencimento, valor: currencyToDecimal(l.valorTexto) || '0' }))
      : [],
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
const notaCls: React.CSSProperties = {
  fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: 4,
}
const SectionTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p style={{
    fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em',
    textTransform: 'uppercase', color: 'var(--color-text-muted)',
    marginTop: '10px', marginBottom: '-2px', fontFamily: 'var(--font-body)',
  }}>{children}</p>
)

const AquisicaoForm: React.FC<Props> = ({ open, clienteId, onClose, onSave, initial }) => {
  const [form, setForm] = useState<FormState>(EMPTY(clienteId))
  const [empSelecionado, setEmpSelecionado] = useState<number | ''>('')
  const [unidades, setUnidades] = useState<Unidade[]>([])
  const [carregandoUnidades, setCarregandoUnidades] = useState(false)
  const [simulacao, setSimulacao] = useState<SimulacaoPlano | null>(null)
  const [erroSimulacao, setErroSimulacao] = useState<string | null>(null)
  const [negociado, setNegociado] = useState<string | null>(null)
  const [verCarne, setVerCarne] = useState(false)
  const [saving, setSaving] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [indices, setIndices] = useState<IndiceEconomico[]>([])
  const [tipos, setTipos] = useState<TipoDeMeio[]>([])
  const [tetoMeios, setTetoMeios] = useState(12)

  useEffect(() => {
    apiClient.get('/indices-economicos/')
      .then(r => setIndices(r.data))
      .catch(() => setIndices([]))
    apiClient.get('/clientes-empreendimentos/condicoes/')
      .then(r => {
        setTipos(r.data.meios ?? [])
        if (r.data.tetoMeios) setTetoMeios(r.data.tetoMeios)
      })
      .catch(() => setTipos([]))
  }, [])

  useEffect(() => {
    if (initial) {
      setForm(toForm(initial))
      setEmpSelecionado(initial.empreendimento)
    } else {
      setForm(EMPTY(clienteId))
      setEmpSelecionado('')
    }
    setSimulacao(null)
    setErroSimulacao(null)
    setNegociado(null)
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
  // do backend — a mesma que grava o contrato depois. O negociado volta mesmo
  // quando os meios ainda não fecham, para a barra dizer quanto falta.
  const timer = useRef<number | undefined>(undefined)
  const simular = useCallback(() => {
    if (!form.unidade) { setSimulacao(null); setNegociado(null); return }
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(async () => {
      try {
        const { data } = await apiClient.post('/clientes-empreendimentos/simular/', {
          unidade: form.unidade,
          desconto_percentual: form.desconto_percentual || 0,
          desconto_valor: form.desconto_valor || 0,
          data_compra: form.data_compra || null,
          meios: form.meios.map(meioParaApi),
        })
        setSimulacao(data)
        setNegociado(data.valorNegociado)
        setErroSimulacao(null)
      } catch (err) {
        setSimulacao(null)
        const dados = (err as { response?: { data?: { detail?: string; valorNegociado?: string } } })
          ?.response?.data
        setNegociado(dados?.valorNegociado ?? null)
        setErroSimulacao(dados?.detail ?? 'Não foi possível calcular a proposta.')
      }
    }, 350)
  }, [form])

  useEffect(() => {
    simular()
    return () => window.clearTimeout(timer.current)
  }, [simular])

  if (!open) return null

  const set = (campo: keyof FormState, valor: string | number) =>
    setForm(anterior => ({ ...anterior, [campo]: valor }))

  const tipoDe = (codigo: TipoMeioPagamento) => tipos.find(t => t.codigo === codigo)

  const alterarMeio = (chave: number, mudanca: Partial<MeioForm>) =>
    setForm(anterior => ({
      ...anterior,
      meios: anterior.meios.map(m => {
        if (m.chave !== chave) return m
        const novo = { ...m, ...mudanca }
        return { ...novo, valor: valorDoMeio(novo) }
      }),
    }))

  /** Trocar o tipo apaga o que o novo não comporta — o backend repete a
   *  limpeza ao gravar, porque a tela não é a única porta. O valor fica: quem
   *  troca "entrada" por "à vista" está corrigindo o nome, não a conta. A
   *  descrição não fica: o nome do banco não explica um "outro". */
  const trocarTipo = (m: MeioForm, codigo: TipoMeioPagamento) => {
    const regra = tipoDe(codigo)
    const cada = m.tipo === 'anuais' || m.tipo === 'datas_livres' ? m.valor : currencyToDecimal(m.valorTexto) || '0'
    const texto = Number(cada) > 0 ? decimalParaTexto(cada) : ''
    alterarMeio(m.chave, {
      tipo: codigo,
      valorTexto: texto,
      parcelas: regra?.parcelas ? (codigo === 'financiamento_direto' ? Math.max(m.parcelas, 12) : m.parcelas) : 1,
      juros_mensal: regra?.juros ? m.juros_mensal : '0',
      descricao: '',
      primeiro_vencimento: regra?.vencimento ? vencimentoPadrao(codigo, form.data_compra) : '',
      // Virar "datas livres" leva o valor para a primeira linha: quem troca o
      // tipo está reorganizando o mesmo dinheiro, não recomeçando.
      linhas: codigo === 'datas_livres'
        ? [novaLinha(somarMeses(form.data_compra || hojeISO(), 1), texto)]
        : [],
    })
  }

  const alterarLinha = (m: MeioForm, chave: number, mudanca: Partial<LinhaLivre>) =>
    alterarMeio(m.chave, { linhas: m.linhas.map(l => (l.chave === chave ? { ...l, ...mudanca } : l)) })

  /** A linha nova nasce um mês depois da última — o passo mais comum, que a
   *  pessoa corrige quando a data combinada é outra. */
  const adicionarLinha = (m: MeioForm) => {
    const ultima = m.linhas[m.linhas.length - 1]?.vencimento
    alterarMeio(m.chave, {
      linhas: [...m.linhas, novaLinha(somarMeses(ultima || form.data_compra || hojeISO(), 1))],
    })
  }

  const removerLinha = (m: MeioForm, chave: number) =>
    alterarMeio(m.chave, { linhas: m.linhas.filter(l => l.chave !== chave) })

  const adicionarMeio = () => setForm(anterior => {
    const usados = new Set(anterior.meios.map(m => m.tipo))
    const tipo = SUGESTAO.find(t => !usados.has(t)) ?? 'outro'
    return { ...anterior, meios: [...anterior.meios, novoMeio(tipo, anterior.data_compra)] }
  })

  const removerMeio = (chave: number) =>
    setForm(anterior => ({ ...anterior, meios: anterior.meios.filter(m => m.chave !== chave) }))

  const distribuido = form.meios.reduce((soma, m) => soma + centavos(m.valor), 0)
  const falta = negociado == null ? null : centavos(negociado) - distribuido

  /** Põe neste meio o que falta para fechar o negociado. Nas anuais, divide
   *  pela quantidade — e o centavo que não divide fica aparecendo na barra. */
  const usarRestante = (m: MeioForm) => {
    if (falta == null) return
    const livre = falta + centavos(m.valor)
    if (livre <= 0) return
    if (m.tipo === 'datas_livres') {
      // Nas datas livres, o acerto vai na última linha: as outras são datas e
      // valores que a pessoa digitou um a um, e não se mexe nelas.
      const ultima = m.linhas[m.linhas.length - 1]
      if (!ultima) return
      const resto = falta + centavos(currencyToDecimal(ultima.valorTexto) || '0')
      if (resto > 0) alterarLinha(m, ultima.chave, { valorTexto: decimalParaTexto(resto / 100) })
      return
    }
    const cada = m.tipo === 'anuais' ? Math.floor(livre / Math.max(1, m.parcelas)) : livre
    alterarMeio(m.chave, { valorTexto: decimalParaTexto(cada / 100) })
  }

  const temSac = form.meios.some(m => m.tipo === 'financiamento_direto' && m.sistema_amortizacao === 'sac')
  const temPrazo = form.meios.some(m =>
    m.tipo === 'financiamento_direto' || m.tipo === 'anuais' || m.tipo === 'datas_livres'
    || (m.tipo === 'entrada' && m.parcelas > 1))
  const repetidos = new Set(
    form.meios.map(m => m.tipo).filter((t, i, todos) => todos.indexOf(t) !== i),
  )

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
        meios: form.meios.map(meioParaApi),
        indice_correcao: form.indice_correcao === '' ? null : form.indice_correcao,
        data_base_correcao: form.data_base_correcao || null,
        // Em branco, o backend aplica o padrão do contrato.
        multa_atraso_percentual: form.multa_atraso_percentual || undefined,
        juros_mora_mensal_percentual: form.juros_mora_mensal_percentual || undefined,
      } as unknown as ClienteEmpreendimentoFormData)
      onClose()
    } catch (err) {
      setFieldErrors(parseApiErrors(err))
    } finally {
      setSaving(false)
    }
  }

  const resumoDe = (ordem: number) => simulacao?.meios?.find(r => r.ordem === ordem)
  const temForaDoCarne = (simulacao?.meios ?? []).some(r => !r.noCarne)

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.3)' }} onClick={onClose} />
      <div className="fixed top-0 right-0 h-full z-50 flex flex-col"
        style={{ width: '560px', maxWidth: '100vw', background: '#FFFFFF', boxShadow: '-4px 0 24px rgba(0,0,0,0.12)', overflow: 'hidden' }}>

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
            {/* Busca no servidor (F2). Vazio = as unidades à venda de todos. */}
            <SeletorDeEmpreendimento
              valor={empSelecionado === '' ? null : empSelecionado}
              aoMudar={id => {
                setEmpSelecionado(id ?? '')
                set('unidade', '')
              }}
              permiteLimpar
              placeholder="Todos — busque para filtrar"
              aria-label="Empreendimento"
              style={inputCls}
            />
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

          <SectionTitle>Proposta</SectionTitle>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={labelCls}>Desconto (%)</label>
              <input style={inputCls} value={form.desconto_percentual} inputMode="decimal"
                onChange={e => set('desconto_percentual', e.target.value.replace(',', '.'))} />
            </div>
            <div>
              <label style={labelCls}>Desconto (R$)</label>
              <input style={inputCls} placeholder="0,00"
                value={Number(form.desconto_valor) > 0 ? decimalParaTexto(form.desconto_valor) : ''}
                onChange={e => set('desconto_valor', currencyToDecimal(maskCurrency(e.target.value)) || '0')} />
            </div>
          </div>

          {/* A lista livre: cada meio traz só os campos que ele comporta, e a
              regra de quais são vem do backend. */}
          <SectionTitle>Meios de pagamento</SectionTitle>
          <BarraDeDistribuicao negociado={negociado} distribuido={distribuido} />

          {form.meios.map((m, i) => {
            const regra = tipoDe(m.tipo)
            const resumo = resumoDe(i + 1)
            return (
              <div key={m.chave} style={{ border: '1.5px solid #e2e8f0', borderRadius: 10, padding: '10px 12px' }}
                className="flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                    {i + 1}.
                  </span>
                  <select style={{ ...inputCls, fontWeight: 600 }} value={m.tipo}
                    aria-label={`Forma de pagamento do meio ${i + 1}`}
                    disabled={tipos.length === 0}
                    onChange={e => trocarTipo(m, e.target.value as TipoMeioPagamento)}>
                    {tipos.length === 0 && <option value={m.tipo}>Carregando…</option>}
                    {tipos.map(t => <option key={t.codigo} value={t.codigo}>{t.rotulo}</option>)}
                  </select>
                  <button type="button" onClick={() => removerMeio(m.chave)}
                    title="Remover este meio" aria-label={`Remover o meio ${i + 1}`}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', padding: 4 }}>
                    <X size={16} />
                  </button>
                </div>

                {regra?.cronograma ? (
                  /* Datas livres: uma linha por parcela, data e valor. O total
                     do meio é a soma — não há campo de valor à parte para
                     discordar dela. */
                  <div className="flex flex-col gap-1.5">
                    <div className="grid gap-2" style={{ gridTemplateColumns: '1fr 1fr 24px' }}>
                      <span style={{ ...labelCls, marginBottom: 0 }}>Vencimento</span>
                      <span style={{ ...labelCls, marginBottom: 0 }}>Valor (R$)</span>
                      <span />
                    </div>
                    {m.linhas.map((l, n) => (
                      <div key={l.chave} className="grid gap-2 items-center" style={{ gridTemplateColumns: '1fr 1fr 24px' }}>
                        <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputCls}
                          value={l.vencimento} aria-label={`Vencimento da parcela ${n + 1}`}
                          onChange={e => alterarLinha(m, l.chave, { vencimento: e.target.value })} />
                        <input style={inputCls} value={l.valorTexto} placeholder="0,00" inputMode="numeric"
                          aria-label={`Valor da parcela ${n + 1}`}
                          onChange={e => alterarLinha(m, l.chave, { valorTexto: maskCurrency(e.target.value) })} />
                        <button type="button" onClick={() => removerLinha(m, l.chave)}
                          title="Remover esta parcela" aria-label={`Remover a parcela ${n + 1}`}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)', padding: 0 }}>
                          <X size={14} />
                        </button>
                      </div>
                    ))}
                    <div className="flex items-center gap-4">
                      <button type="button" onClick={() => adicionarLinha(m)}
                        className="inline-flex items-center gap-1"
                        style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                          fontSize: '0.72rem', fontWeight: 600, color: 'var(--color-brand)' }}>
                        <Plus size={13} /> Adicionar parcela
                      </button>
                      {falta != null && falta !== 0 && m.linhas.length > 0 && (
                        <button type="button" onClick={() => usarRestante(m)}
                          style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                            fontSize: '0.72rem', fontWeight: 600, color: 'var(--color-brand)' }}>
                          {falta > 0 ? 'Restante na última' : 'Ajustar a última ao negociado'}
                        </button>
                      )}
                      <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                        {m.linhas.length} parcela{m.linhas.length !== 1 ? 's' : ''} · <strong>{brl(m.valor)}</strong>
                      </span>
                    </div>
                  </div>
                ) : (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label style={labelCls}>
                      {m.tipo === 'anuais'
                        ? (Number(m.juros_mensal) > 0 ? 'Principal de cada (R$)' : 'Valor de cada (R$)')
                        : m.tipo === 'cartao' ? 'Valor no cartão (R$)' : 'Valor (R$)'}
                    </label>
                    <input style={inputCls} value={m.valorTexto} placeholder="0,00" inputMode="numeric"
                      onChange={e => alterarMeio(m.chave, { valorTexto: maskCurrency(e.target.value) })} />
                    {falta != null && falta !== 0 && (falta > 0 || centavos(m.valor) > 0) && (
                      <button type="button" onClick={() => usarRestante(m)}
                        style={{ background: 'none', border: 'none', padding: 0, marginTop: 4, cursor: 'pointer',
                          fontSize: '0.72rem', fontWeight: 600, color: 'var(--color-brand)' }}>
                        {falta > 0 ? 'Usar o restante' : 'Ajustar ao negociado'}
                      </button>
                    )}
                  </div>
                  {regra?.parcelas && (
                    <div>
                      <label style={labelCls}>{regra.rotuloParcelas}</label>
                      <input type="number" min={1} style={inputCls} value={m.parcelas}
                        onChange={e => alterarMeio(m.chave, { parcelas: Number(e.target.value) })} />
                    </div>
                  )}
                </div>
                )}

                {(regra?.sistema || regra?.periodicidade || (regra?.juros && (m.tipo !== 'entrada' || m.parcelas > 1)) || regra?.vencimento) && (
                  <div className="grid grid-cols-3 gap-3">
                    {regra?.sistema && (
                      <div>
                        <label style={labelCls}>Sistema</label>
                        <select style={inputCls} value={m.sistema_amortizacao}
                          onChange={e => alterarMeio(m.chave, { sistema_amortizacao: e.target.value as MeioForm['sistema_amortizacao'] })}>
                          <option value="price">Price (fixa)</option>
                          <option value="sac">SAC (decrescente)</option>
                        </select>
                      </div>
                    )}
                    {regra?.periodicidade && (
                      <div>
                        <label style={labelCls}>A cada</label>
                        <select style={inputCls} value={m.periodicidade}
                          onChange={e => alterarMeio(m.chave, { periodicidade: e.target.value as MeioForm['periodicidade'] })}>
                          <option value="anual">12 meses</option>
                          <option value="semestral">6 meses</option>
                        </select>
                      </div>
                    )}
                    {/* A entrada só pergunta juros quando é parcelada — e parte de
                        zero: a entrada curta é vendida sem juros. */}
                    {regra?.juros && (m.tipo !== 'entrada' || m.parcelas > 1) && (
                      <div>
                        <label style={labelCls}>
                          {m.tipo === 'entrada' || m.tipo === 'anuais' ? 'Juros (% a.m.)' : 'Juros (% a.m.)'}
                        </label>
                        <input style={inputCls} value={m.juros_mensal} inputMode="decimal"
                          onChange={e => alterarMeio(m.chave, { juros_mensal: e.target.value.replace(',', '.') })} />
                      </div>
                    )}
                    {regra?.vencimento && (
                      <div>
                        <label style={labelCls}>{regra.rotuloVencimento}</label>
                        <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputCls}
                          value={m.primeiro_vencimento ?? ''}
                          onChange={e => alterarMeio(m.chave, { primeiro_vencimento: e.target.value })} />
                      </div>
                    )}
                  </div>
                )}

                {regra?.descricao && (
                  <div>
                    <label style={labelCls}>
                      {regra.rotuloDescricao}{regra.descricao === 'obrigatoria' ? ' *' : ''}
                    </label>
                    {regra.descricao === 'obrigatoria' ? (
                      <textarea required style={{ ...inputCls, minHeight: 56, resize: 'vertical' }}
                        value={m.descricao}
                        placeholder={m.tipo === 'outro'
                          ? 'Ex.: 5 cheques pré-datados de R$ 4.000, a partir de 10/03'
                          : 'Ex.: Gol 2019, placa ABC1D23, avaliado pela tabela FIPE'}
                        onChange={e => alterarMeio(m.chave, { descricao: e.target.value })} />
                    ) : (
                      <input style={inputCls} value={m.descricao}
                        onChange={e => alterarMeio(m.chave, { descricao: e.target.value })} />
                    )}
                  </div>
                )}

                <p style={{ ...notaCls, marginTop: 0 }}>
                  {regra?.nota}
                  {m.tipo === 'anuais' && m.parcelas > 1 && Number(m.valor) > 0 && (
                    <> {Number(m.juros_mensal) > 0 ? 'Principal' : 'Total'} das {m.parcelas}: <strong>{brl(m.valor)}</strong>.</>
                  )}
                  {m.tipo === 'anuais' && resumo && Number(resumo.juros) > 0 && (
                    <> Cada anual sai por <strong>{brl(resumo.primeiraParcela)}</strong>.</>
                  )}
                  {resumo && Number(resumo.juros) > 0 && (
                    <> Juros deste meio: <strong>{brl(resumo.juros)}</strong>.</>
                  )}
                  {repetidos.has(m.tipo) && <> No boleto, esta série sai numerada à parte.</>}
                </p>
              </div>
            )
          })}

          <button type="button" onClick={adicionarMeio}
            disabled={form.meios.length >= tetoMeios || tipos.length === 0}
            className="flex items-center justify-center gap-1.5"
            style={{
              padding: '8px 12px', borderRadius: 10, border: '1.5px dashed #cbd5e1',
              background: 'none', cursor: form.meios.length >= tetoMeios ? 'not-allowed' : 'pointer',
              fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-brand)', fontFamily: 'var(--font-body)',
              opacity: form.meios.length >= tetoMeios ? 0.5 : 1,
            }}>
            <Plus size={15} /> Adicionar meio de pagamento
          </button>
          <FieldError msg={fieldErrors.meios} />

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
                {/* Cada meio pelo nome do dinheiro: "Financiado pelo banco —
                    Caixa", e não um "quitado fora do carnê" que não diz de
                    onde ele vem. */}
                {(simulacao.meios ?? []).map(r => (
                  <Linha key={r.ordem}
                    rotulo={r.detalhe ? `${r.rotulo} · ${r.detalhe}` : r.rotulo}
                    valor={brl(r.valor)} />
                ))}
                {Number(simulacao.totalJuros) > 0 && (
                  <Linha rotulo="Juros do plano" valor={brl(simulacao.totalJuros)} />
                )}
                <Linha
                  rotulo={temForaDoCarne ? 'A receber pela construtora' : 'Total a pagar'}
                  valor={brl(simulacao.total)}
                  destaque
                />
                {Number(simulacao.primeiraParcela) > 0 && (
                  <Linha
                    rotulo={temSac ? 'Parcela mensal (1ª → última)' : 'Parcela mensal'}
                    valor={temSac
                      ? `${brl(simulacao.primeiraParcela)} → ${brl(simulacao.ultimaParcela)}`
                      : brl(simulacao.primeiraParcela)}
                    destaque
                  />
                )}
              </div>
              {simulacao.parcelas.length > 0 && (
                <button type="button" onClick={() => setVerCarne(v => !v)}
                  style={{
                    marginTop: 10, background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                    fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-brand)',
                  }}>
                  {verCarne ? 'Ocultar' : `Ver os ${simulacao.parcelas.length} títulos a receber`}
                </button>
              )}
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
                        <tr key={`${p.meio}-${p.tipo}-${p.numero}-${i}`} style={{ borderTop: '1px solid #e2e8f0' }}>
                          <td style={{ padding: '3px 4px' }}>{p.numero}</td>
                          <td style={{ padding: '3px 4px' }}>
                            {NOME_DA_LINHA[p.tipo] ?? p.tipo}
                            {p.meio && form.meios[p.meio - 1] && repetidos.has(form.meios[p.meio - 1].tipo) && (
                              <span style={{ color: 'var(--color-text-muted)' }}> (meio {p.meio})</span>
                            )}
                          </td>
                          {/* A data pagável, com a do contrato ao lado quando
                              as duas diferem. */}
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
                            {p.tipo === 'parcela' || Number(p.juros) > 0 ? brl(p.saldo) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {/* O ajuste de dia útil dito na tela, com a ressalva de quando a
                  base de feriados nunca foi sincronizada. */}
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
          {temPrazo && (
            <>
              <SectionTitle>Correção monetária</SectionTitle>
              <p style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: -6 }}>
                Reajuste conta do <strong>aniversário da data-base</strong>, não da data do boleto —
                o boleto só carrega o valor já corrigido. Vale para todo título em aberto,
                inclusive a entrada parcelada. Sem índice, o contrato é nominal.
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

          {temPrazo && (
            <>
              <SectionTitle>Atraso</SectionTitle>
              <p style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: -6 }}>
                O que a segunda via de uma parcela vencida soma ao saldo: multa uma vez e juros por dia de atraso.
                Em branco, vale o padrão (2% de multa e 1% ao mês). Venda a consumidor: multa de até 2%.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label style={labelCls}>Multa por atraso (%)</label>
                  <input style={inputCls} inputMode="decimal" placeholder="2,00" value={form.multa_atraso_percentual.replace('.', ',')}
                    onChange={e => set('multa_atraso_percentual', e.target.value.replace(',', '.').replace(/[^0-9.]/g, ''))} />
                  <FieldError msg={fieldErrors.multa_atraso_percentual} />
                </div>
                <div>
                  <label style={labelCls}>Juros de mora (% ao mês)</label>
                  <input style={inputCls} inputMode="decimal" placeholder="1,00" value={form.juros_mora_mensal_percentual.replace('.', ',')}
                    onChange={e => set('juros_mora_mensal_percentual', e.target.value.replace(',', '.').replace(/[^0-9.]/g, ''))} />
                  <FieldError msg={fieldErrors.juros_mora_mensal_percentual} />
                </div>
              </div>
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

/** Quanto do negociado os meios já cobrem — e quanto falta ou passa. */
function BarraDeDistribuicao({ negociado, distribuido }: { negociado: string | null; distribuido: number }) {
  if (negociado == null) {
    return (
      <p style={notaCls}>
        Escolha a unidade: a soma dos meios de pagamento tem de fechar o valor negociado.
      </p>
    )
  }
  const total = centavos(negociado)
  const falta = total - distribuido
  const pct = total > 0 ? Math.min(100, (distribuido / total) * 100) : 0
  const cor = falta === 0 ? '#15803d' : falta < 0 ? '#b91c1c' : '#b45309'
  return (
    <div>
      <div style={{ height: 6, borderRadius: 999, background: '#e2e8f0', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: cor, transition: 'width .2s' }} />
      </div>
      <p style={{ ...notaCls, color: cor, fontWeight: 600 }}>
        {brl(distribuido / 100)} de {brl(total / 100)}
        {falta === 0 && ' — a conta fecha.'}
        {falta > 0 && ` — faltam ${brl(falta / 100)}.`}
        {falta < 0 && ` — passam ${brl(-falta / 100)} do negociado.`}
      </p>
    </div>
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
