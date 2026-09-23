import { useState } from 'react'
import { useForm, FormProvider, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
import { MoneyInput } from '../shared/MoneyInput'
import { RateioField } from './RateioField'
import { Field } from './FormField'
import { inputStyle, selectStyle, buttonPrimaryStyle, buttonSecondaryStyle } from './formStyles'
import { contaPagarSchema, type ContaPagarFormValues } from './schemas'
import { useFornecedorOptions, useEmpreendimentoOptions } from '../../hooks/useEntityOptions'
import { apiDecimalToCents, centsToApiDecimal } from '@/utils/money'
import { FormErrorBanner, parseApiErrors } from '@/utils/formErrors'
import type { ContaPagar, ContaPagarPayload } from '../../types'

import { minCalendarioISO, maxCalendarioISO } from '@/utils/dates'

/** Lançamento de conta a pagar — criação e edição (D.1.1 §13). */

const EMPTY_VALUES: ContaPagarFormValues = {
  fornecedor: undefined as unknown as number,
  empreendimento: null,
  descricao: '',
  valorCents: 0,
  data_emissao: '',
  data_vencimento: '',
  data_agendamento: '',
  rateios: [],
}

function toFormValues(conta: ContaPagar): ContaPagarFormValues {
  return {
    fornecedor: conta.fornecedor ?? (undefined as unknown as number),
    empreendimento: conta.empreendimento,
    descricao: conta.descricao,
    valorCents: apiDecimalToCents(conta.valor),
    data_emissao: conta.data_emissao ?? '',
    data_vencimento: conta.data_vencimento,
    data_agendamento: conta.data_agendamento ?? '',
    rateios: conta.rateios.map(r => ({ centro_custo: r.centro_custo, valorCents: apiDecimalToCents(r.valor) })),
  }
}

interface ContaPagarFormProps {
  initial?: ContaPagar | null
  onSubmit: (payload: ContaPagarPayload) => Promise<unknown>
  onCancel: () => void
}

export function ContaPagarForm({ initial, onSubmit, onCancel }: ContaPagarFormProps) {
  const fornecedorOptions = useFornecedorOptions(true)
  const empreendimentoOptions = useEmpreendimentoOptions(true)
  const [apiError, setApiError] = useState<string | null>(null)

  const methods = useForm<ContaPagarFormValues>({
    resolver: zodResolver(contaPagarSchema),
    defaultValues: initial ? toFormValues(initial) : EMPTY_VALUES,
  })
  const { register, control, handleSubmit, setError, formState: { errors, isSubmitting } } = methods

  const submit = handleSubmit(async values => {
    setApiError(null)
    try {
      await onSubmit({
        fornecedor: values.fornecedor,
        empreendimento: values.empreendimento ?? null,
        descricao: values.descricao,
        valor: centsToApiDecimal(values.valorCents),
        data_emissao: values.data_emissao || null,
        data_vencimento: values.data_vencimento,
        data_agendamento: values.data_agendamento || null,
        rateios: (values.rateios ?? []).map(r => ({ centro_custo: r.centro_custo, valor: centsToApiDecimal(r.valorCents) })),
      })
    } catch (err) {
      const parsed = parseApiErrors(err)
      const { _form, ...campo } = parsed
      for (const [field, msg] of Object.entries(campo)) {
        if (field in EMPTY_VALUES) setError(field as keyof ContaPagarFormValues, { message: msg })
      }
      setApiError(_form ?? (Object.keys(campo).length ? null : 'Não foi possível salvar a conta.'))
    }
  })

  return (
    <FormProvider {...methods}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Fornecedor" error={errors.fornecedor?.message}>
          <select style={selectStyle} disabled={fornecedorOptions.isLoading} defaultValue="" {...register('fornecedor', { valueAsNumber: true })}>
            <option value="" disabled>Selecione um fornecedor…</option>
            {(fornecedorOptions.data ?? []).map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        </Field>

        <Field label="Obra/empreendimento (opcional)">
          <select
            style={selectStyle}
            disabled={empreendimentoOptions.isLoading}
            defaultValue=""
            {...register('empreendimento', { setValueAs: v => (v === '' ? null : Number(v)) })}
          >
            <option value="">Sem vínculo com obra</option>
            {(empreendimentoOptions.data ?? []).map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        </Field>

        <Field label="Descrição" error={errors.descricao?.message}>
          <input type="text" style={inputStyle} placeholder="Ex.: Compra de cimento — NF 1234" {...register('descricao')} />
        </Field>

        <Field label="Valor" error={errors.valorCents?.message}>
          <Controller
            control={control}
            name="valorCents"
            render={({ field }) => <MoneyInput valueCents={field.value} onChangeCents={field.onChange} />}
          />
        </Field>

        <div className="grid grid-cols-3 gap-3">
          <Field label="Emissão" error={errors.data_emissao?.message}>
            <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputStyle} {...register('data_emissao')} />
          </Field>
          <Field label="Vencimento" error={errors.data_vencimento?.message}>
            <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputStyle} {...register('data_vencimento')} />
          </Field>
          <Field label="Agendamento" error={errors.data_agendamento?.message}>
            <input type="date" min={minCalendarioISO} max={maxCalendarioISO} style={inputStyle} {...register('data_agendamento')} />
          </Field>
        </div>

        <RateioField />

        {apiError && <FormErrorBanner errors={{ _form: apiError }} />}

        <div className="flex items-center justify-end gap-2 pt-2">
          <button type="button" onClick={onCancel} style={buttonSecondaryStyle}>Cancelar</button>
          <button type="submit" disabled={isSubmitting} style={{ ...buttonPrimaryStyle, opacity: isSubmitting ? 0.7 : 1 }}>
            {isSubmitting
              ? <span className="flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Salvando…</span>
              : initial ? 'Salvar alterações' : 'Lançar conta'}
          </button>
        </div>
      </form>
    </FormProvider>
  )
}
