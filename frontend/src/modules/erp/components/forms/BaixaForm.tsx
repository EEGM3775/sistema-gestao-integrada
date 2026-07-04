import { useState } from 'react'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
import { MoneyInput } from '../shared/MoneyInput'
import { MoneyDisplay } from '../shared/MoneyDisplay'
import { Field } from './FormField'
import { inputStyle, buttonPrimaryStyle, buttonSecondaryStyle } from './formStyles'
import { baixaSchema, type BaixaFormValues } from './schemas'
import { apiDecimalToCents, centsToApiDecimal } from '@/utils/money'
import { FormErrorBanner, parseApiErrors } from '@/utils/formErrors'
import type { BaixaPayload } from '../../types'

/**
 * Quitação manual (total ou parcial) de uma `ContaPagar`/`ContaReceber` —
 * mesmo formulário para os dois lados (D.1.1 §13: `dar_baixa()` compartilhado
 * no backend). Pré-preenche com o saldo em aberto; juros/multa/desconto somam
 * ao valor pago para compor o `total_devido` no backend.
 */

const today = () => new Date().toISOString().slice(0, 10)

interface BaixaFormProps {
  /** Saldo em aberto da conta (string decimal da API) — vira o valor sugerido da baixa. */
  saldoAberto: string
  onSubmit: (payload: BaixaPayload) => Promise<unknown>
  onCancel: () => void
}

export function BaixaForm({ saldoAberto, onSubmit, onCancel }: BaixaFormProps) {
  const saldoCents = apiDecimalToCents(saldoAberto)
  const [apiError, setApiError] = useState<string | null>(null)

  const {
    register, control, handleSubmit, setError,
    formState: { errors, isSubmitting },
  } = useForm<BaixaFormValues>({
    resolver: zodResolver(baixaSchema),
    defaultValues: {
      valorCents: saldoCents,
      data: today(),
      jurosCents: 0,
      multaCents: 0,
      descontoCents: 0,
      meio_pagamento: '',
    },
  })

  const submit = handleSubmit(async values => {
    setApiError(null)
    try {
      await onSubmit({
        valor: centsToApiDecimal(values.valorCents),
        data: values.data,
        juros: centsToApiDecimal(values.jurosCents ?? 0),
        multa: centsToApiDecimal(values.multaCents ?? 0),
        desconto: centsToApiDecimal(values.descontoCents ?? 0),
        meio_pagamento: values.meio_pagamento || undefined,
      })
    } catch (err) {
      const parsed = parseApiErrors(err)
      const { _form, ...campo } = parsed
      for (const [field, msg] of Object.entries(campo)) {
        if (field in baixaSchema.shape) setError(field as keyof BaixaFormValues, { message: msg })
      }
      setApiError(_form ?? (Object.keys(campo).length ? null : 'Não foi possível registrar a baixa.'))
    }
  })

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <p className="text-sm" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
        Saldo em aberto: <MoneyDisplay cents={saldoCents} />
      </p>

      <Field label="Valor pago" error={errors.valorCents?.message}>
        <Controller
          control={control}
          name="valorCents"
          render={({ field }) => <MoneyInput valueCents={field.value} onChangeCents={field.onChange} />}
        />
      </Field>

      <Field label="Data do pagamento" error={errors.data?.message}>
        <input type="date" style={inputStyle} {...register('data')} />
      </Field>

      <div className="grid grid-cols-3 gap-3">
        <Field label="Juros" error={errors.jurosCents?.message}>
          <Controller
            control={control}
            name="jurosCents"
            render={({ field }) => <MoneyInput valueCents={field.value ?? 0} onChangeCents={field.onChange} />}
          />
        </Field>
        <Field label="Multa" error={errors.multaCents?.message}>
          <Controller
            control={control}
            name="multaCents"
            render={({ field }) => <MoneyInput valueCents={field.value ?? 0} onChangeCents={field.onChange} />}
          />
        </Field>
        <Field label="Desconto" error={errors.descontoCents?.message}>
          <Controller
            control={control}
            name="descontoCents"
            render={({ field }) => <MoneyInput valueCents={field.value ?? 0} onChangeCents={field.onChange} />}
          />
        </Field>
      </div>

      <Field label="Meio de pagamento" error={errors.meio_pagamento?.message}>
        <input
          type="text"
          placeholder="PIX, boleto, transferência…"
          style={inputStyle}
          {...register('meio_pagamento')}
        />
      </Field>

      {apiError && <FormErrorBanner errors={{ _form: apiError }} />}

      <div className="flex items-center justify-end gap-2 pt-2">
        <button type="button" onClick={onCancel} style={buttonSecondaryStyle}>Cancelar</button>
        <button type="submit" disabled={isSubmitting} style={{ ...buttonPrimaryStyle, opacity: isSubmitting ? 0.7 : 1 }}>
          {isSubmitting
            ? <span className="flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Confirmando…</span>
            : 'Confirmar baixa'}
        </button>
      </div>
    </form>
  )
}
