import { useFieldArray, useFormContext, useWatch, Controller } from 'react-hook-form'
import { Plus, Trash2 } from 'lucide-react'
import { MoneyInput } from '../shared/MoneyInput'
import { MoneyDisplay } from '../shared/MoneyDisplay'
import { useCentrosCusto } from '../../hooks/useCentrosCusto'
import { FieldError } from '@/utils/formErrors'

/**
 * Rateio por centro de custo (docs/modulos/moduloerp.md §3.2/§13 — D.1.1).
 *
 * `useFieldArray` controla a lista de linhas; a soma precisa bater com o
 * `valorCents` da conta — a validação em si vive no schema (`_validar_rateios`
 * espelhado em `schemas.ts`), aqui só exibimos a diferença para orientar o usuário.
 */

interface RateioFieldProps {
  /** Nome do array no formulário — `"rateios"` tanto em `ContaPagarForm` quanto em `ContaReceberForm`. */
  name?: 'rateios'
  /** Campo do valor total da conta — usado para mostrar a diferença restante. */
  totalFieldName?: 'valorCents'
}

const selectStyle: React.CSSProperties = {
  border: '1.5px solid #e2e8f0', borderRadius: '8px', padding: '8px 10px',
  fontSize: '0.875rem', fontFamily: 'var(--font-body)', color: 'var(--color-text)',
  background: '#FFFFFF', outline: 'none', cursor: 'pointer', flex: '1 1 auto', minWidth: 0,
}

export function RateioField({ name = 'rateios', totalFieldName = 'valorCents' }: RateioFieldProps) {
  const { control, register, formState: { errors } } = useFormContext()
  const { fields, append, remove } = useFieldArray({ control, name })
  const centrosCusto = useCentrosCusto()

  const valorTotal = useWatch({ control, name: totalFieldName }) as number | undefined
  const rateios = useWatch({ control, name }) as { valorCents?: number }[] | undefined
  const somaRateios = (rateios ?? []).reduce((acc, r) => acc + (r.valorCents ?? 0), 0)
  const diferenca = (valorTotal ?? 0) - somaRateios

  const rateiosError = (errors as Record<string, { message?: string } | undefined>)[name]

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span style={{ fontSize: '0.8rem', fontWeight: 600, fontFamily: 'var(--font-body)', color: 'var(--color-brand)' }}>
          Rateio por centro de custo
        </span>
        <button
          type="button"
          onClick={() => append({ centro_custo: undefined as unknown as number, valorCents: 0 })}
          className="flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-lg transition-colors duration-150"
          style={{ color: 'var(--color-brand)', cursor: 'pointer' }}
        >
          <Plus size={14} /> Adicionar linha
        </button>
      </div>

      {fields.length === 0 && (
        <p className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-body)' }}>
          Opcional — sem rateio, o valor integral fica sem centro de custo associado.
        </p>
      )}

      {fields.map((field, index) => (
        <div key={field.id} className="flex items-center gap-2">
          <select
            {...register(`${name}.${index}.centro_custo` as const, { valueAsNumber: true })}
            style={selectStyle}
            disabled={centrosCusto.isLoading}
            defaultValue=""
          >
            <option value="" disabled>Centro de custo…</option>
            {(centrosCusto.data ?? []).map(cc => (
              <option key={cc.centro_custo_id} value={cc.centro_custo_id}>
                {cc.codigo ? `${cc.codigo} — ${cc.nome}` : cc.nome}
              </option>
            ))}
          </select>

          <Controller
            control={control}
            name={`${name}.${index}.valorCents` as const}
            render={({ field: { value, onChange } }) => (
              <div style={{ width: '160px' }}>
                <MoneyInput valueCents={value ?? 0} onChangeCents={onChange} />
              </div>
            )}
          />

          <button
            type="button"
            onClick={() => remove(index)}
            aria-label="Remover linha de rateio"
            className="p-2 rounded-lg shrink-0 transition-colors duration-150"
            style={{ color: 'var(--color-text-muted)', cursor: 'pointer' }}
            onMouseEnter={e => (e.currentTarget.style.color = 'var(--color-danger)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--color-text-muted)')}
          >
            <Trash2 size={15} />
          </button>
        </div>
      ))}

      {fields.length > 0 && (
        <div className="flex items-center justify-end gap-2 text-xs" style={{ fontFamily: 'var(--font-body)' }}>
          <span style={{ color: 'var(--color-text-muted)' }}>
            {diferenca === 0 ? 'Rateio cobre o valor total.' : diferenca > 0 ? 'Falta ratear:' : 'Rateio excede o valor em:'}
          </span>
          {diferenca !== 0 && <MoneyDisplay cents={Math.abs(diferenca)} />}
        </div>
      )}

      <FieldError msg={rateiosError?.message} />
    </div>
  )
}
