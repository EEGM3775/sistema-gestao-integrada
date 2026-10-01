import { useState } from 'react'
import { useForm, FormProvider, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2, RefreshCw } from 'lucide-react'
import { MoneyInput } from '../shared/MoneyInput'
import { RateioField } from './RateioField'
import { Field } from './FormField'
import { inputStyle, selectStyle, buttonPrimaryStyle, buttonSecondaryStyle } from './formStyles'
import { contaReceberSchema, type ContaReceberFormValues } from './schemas'
import { useClienteOptions, useEmpreendimentoOptions } from '../../hooks/useEntityOptions'
import { apiDecimalToCents, centsToApiDecimal, formatBRL } from '@/utils/money'
import { FormErrorBanner, parseApiErrors } from '@/utils/formErrors'
import { AvisoDeTrava, TextoTravado } from './trava'
import { distribuirErros, errosSemLugar } from './distribuirErros'
import type { ContaReceber, ContaReceberPayload } from '../../types'

import { dateToBR, minCalendarioISO, maxCalendarioISO } from '@/utils/dates'

/**
 * Lançamento de conta a receber — criação e edição (D.1.1 §13).
 *
 * A emissão de NF (serviço/produto) não entra aqui — é uma ação própria do
 * detalhe da conta (`emitir-nfse`/`emitir-nfe`), disparada só após o lançamento.
 */

const EMPTY_VALUES: ContaReceberFormValues = {
  cliente: undefined as unknown as number,
  empreendimento: null,
  descricao: '',
  valorCents: 0,
  data_emissao: '',
  data_vencimento: '',
  data_agendamento: '',
  rateios: [],
}

function toFormValues(conta: ContaReceber): ContaReceberFormValues {
  return {
    cliente: conta.cliente ?? (undefined as unknown as number),
    empreendimento: conta.empreendimento,
    descricao: conta.descricao,
    valorCents: apiDecimalToCents(conta.valor),
    data_emissao: conta.data_emissao ?? '',
    data_vencimento: conta.data_vencimento,
    data_agendamento: conta.data_agendamento ?? '',
    rateios: conta.rateios.map(r => ({ centro_custo: r.centro_custo, valorCents: apiDecimalToCents(r.valor) })),
  }
}

interface ContaReceberFormProps {
  initial?: ContaReceber | null
  onSubmit: (payload: ContaReceberPayload) => Promise<unknown>
  onCancel: () => void
}

export function ContaReceberForm({ initial, onSubmit, onCancel }: ContaReceberFormProps) {
  const clienteOptions = useClienteOptions(true)
  const empreendimentoOptions = useEmpreendimentoOptions(true)
  const [apiError, setApiError] = useState<string | null>(null)
  const travados = new Set(initial?.campos_travados ?? [])
  // A pessoa da conta pode não estar entre as opções carregadas (a lista vem
  // limitada): sem ela no select, o valor some e o formulário não salva.
  const opcoesCliente = [...(clienteOptions.data ?? [])]
  if (initial?.cliente && !opcoesCliente.some(o => o.id === initial.cliente)) {
    opcoesCliente.unshift({ id: initial.cliente, label: initial.cliente_nome || `#${initial.cliente}` })
  }

  const methods = useForm<ContaReceberFormValues>({
    resolver: zodResolver(contaReceberSchema),
    defaultValues: initial ? toFormValues(initial) : EMPTY_VALUES,
  })
  const { register, control, handleSubmit, setError, watch, formState: { errors, isSubmitting } } = methods

  // Item 57 (revisão de 01/10/2026): com boleto vivo no Asaas, mudar valor ou
  // vencimento reemite o boleto — dito antes de salvar, e confirmado ao salvar.
  // O boleto do banco (CNAB) e o cliente já vêm travados pela API.
  const boletoVivo = initial?.boletos.find(b =>
    b.canal === 'asaas' && Boolean(b.gateway_id) && ['EMITIDO', 'VENCIDO', 'AGUARDANDO'].includes(b.status))
  const valorAtual = watch('valorCents')
  const vencimentoAtual = watch('data_vencimento')
  const reemiteBoleto = Boolean(boletoVivo && initial && (
    valorAtual !== apiDecimalToCents(initial.valor) || vencimentoAtual !== initial.data_vencimento))

  const submit = handleSubmit(async values => {
    setApiError(null)
    try {
      await onSubmit({
        cliente: values.cliente,
        empreendimento: values.empreendimento ?? null,
        descricao: values.descricao,
        valor: centsToApiDecimal(values.valorCents),
        data_emissao: values.data_emissao || null,
        data_vencimento: values.data_vencimento,
        data_agendamento: values.data_agendamento || null,
        rateios: (values.rateios ?? []).map(r => ({ centro_custo: r.centro_custo, valor: centsToApiDecimal(r.valorCents) })),
        ...(reemiteBoleto ? { atualizar_boleto: true } : {}),
      })
    } catch (err) {
      setApiError(distribuirErros(parseApiErrors(err), Object.keys(EMPTY_VALUES), (campo, msg) =>
        setError(campo as keyof ContaReceberFormValues, { message: msg })))
    }
  }, invalidos => setApiError(errosSemLugar(invalidos)))

  return (
    <FormProvider {...methods}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <AvisoDeTrava motivo={initial?.travado_porque ?? ''} />
        <Field label="Cliente" error={errors.cliente?.message}>
          {travados.has('cliente') ? (
            <TextoTravado>{opcoesCliente.find(o => o.id === initial?.cliente)?.label ?? '—'}</TextoTravado>
          ) : (
            <select style={selectStyle} disabled={clienteOptions.isLoading} defaultValue="" {...register('cliente', { valueAsNumber: true })}>
            <option value="" disabled>Selecione um cliente…</option>
            {opcoesCliente.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
          )}
        </Field>

        <Field label="Obra/empreendimento (opcional)">
          {/* Controlado, não registrado: o `<select>` nativo devolvia "" para
              "sem obra" (a validação reprovava sem mensagem — item 57) e perdia a
              obra gravada quando o valor chegava antes das opções. */}
          <Controller
            control={control}
            name="empreendimento"
            render={({ field }) => (
              <select
                style={selectStyle}
                value={field.value == null ? '' : String(field.value)}
                onChange={e => field.onChange(e.target.value === '' ? null : Number(e.target.value))}
                onBlur={field.onBlur}
              >
                <option value="">Sem vínculo com obra</option>
                {(empreendimentoOptions.data ?? []).map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
            )}
          />
        </Field>

        <Field label="Descrição" error={errors.descricao?.message}>
          <input type="text" style={inputStyle} placeholder="Ex.: Medição 03 — contrato 2025/014" {...register('descricao')} />
        </Field>

        <Field label="Valor" error={errors.valorCents?.message}>
          <Controller
            control={control}
            name="valorCents"
            render={({ field }) => travados.has('valor')
              ? <TextoTravado>{formatBRL(field.value)}</TextoTravado>
              : <MoneyInput valueCents={field.value} onChangeCents={field.onChange} />}
          />
        </Field>

        <div className="grid grid-cols-3 gap-3">
          <Field label="Emissão" error={errors.data_emissao?.message}>
            <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputStyle} {...register('data_emissao')} />
          </Field>
          <Field label="Vencimento" error={errors.data_vencimento?.message}>
            {travados.has('data_vencimento')
              ? <TextoTravado>{dateToBR(initial?.data_vencimento ?? '')}</TextoTravado>
              : <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputStyle} {...register('data_vencimento')} />}
          </Field>
          <Field label="Agendamento" error={errors.data_agendamento?.message}>
            <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputStyle} {...register('data_agendamento')} />
          </Field>
        </div>

        <RateioField />

        {reemiteBoleto && boletoVivo && (
          <div role="note" className="flex gap-2 text-sm"
            style={{ padding: '10px 12px', borderRadius: 'var(--r-md)', background: 'var(--accent-soft)', color: 'var(--accent-ink)', lineHeight: 1.45 }}>
            <RefreshCw size={15} style={{ flex: 'none', marginTop: 2 }} />
            <span>
              Esta conta tem o boleto de <strong>{dateToBR(boletoVivo.data_vencimento)}</strong> ({formatBRL(apiDecimalToCents(boletoVivo.valor))}) no Asaas.
              Ao salvar, ele é <strong>cancelado</strong> e um boleto novo é emitido com o valor e o vencimento corrigidos
              (o vencimento ainda anda para o próximo dia útil). Mande o boleto novo ao cliente.
            </span>
          </div>
        )}

        {apiError && <FormErrorBanner errors={{ _form: apiError }} />}

        <div className="flex items-center justify-end gap-2 pt-2">
          <button type="button" onClick={onCancel} style={buttonSecondaryStyle}>Cancelar</button>
          <button type="submit" disabled={isSubmitting} style={{ ...buttonPrimaryStyle, opacity: isSubmitting ? 0.7 : 1 }}>
            {isSubmitting
              ? <span className="flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Salvando…</span>
              : initial ? (reemiteBoleto ? 'Salvar e reemitir o boleto' : 'Salvar alterações') : 'Lançar conta'}
          </button>
        </div>
      </form>
    </FormProvider>
  )
}
