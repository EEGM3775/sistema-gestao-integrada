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
import { apiDecimalToCents, centsToApiDecimal, formatBRL } from '@/utils/money'
import { FormErrorBanner, parseApiErrors } from '@/utils/formErrors'
import { AvisoDeTrava, TextoTravado } from './trava'
import { AvisoIntercompany, EntidadeField } from './EntidadeField'
import { entidadeAtiva } from '@/modules/entidades/entidadeAtiva'
import { ObraEtapaFields } from './ObraEtapaFields'
import { distribuirErros, errosSemLugar } from './distribuirErros'
import type { ContaPagar, ContaPagarPayload } from '../../types'

import { dateToBR, minCalendarioISO, maxCalendarioISO } from '@/utils/dates'

/** Lançamento de conta a pagar — criação e edição (D.1.1 §13). */

const EMPTY_VALUES: ContaPagarFormValues = {
  entidade: null,
  fornecedor: undefined as unknown as number,
  empreendimento: null,
  obra: null,
  etapa: null,
  descricao: '',
  valorCents: 0,
  data_emissao: '',
  data_vencimento: '',
  data_agendamento: '',
  rateios: [],
}

function toFormValues(conta: ContaPagar): ContaPagarFormValues {
  return {
    entidade: conta.entidade,
    fornecedor: conta.fornecedor ?? (undefined as unknown as number),
    empreendimento: conta.empreendimento,
    obra: conta.obra,
    etapa: conta.etapa,
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
  const travados = new Set(initial?.campos_travados ?? [])
  // A pessoa da conta pode não estar entre as opções carregadas (a lista vem
  // limitada): sem ela no select, o valor some e o formulário não salva.
  const opcoesFornecedor = [...(fornecedorOptions.data ?? [])]
  if (initial?.fornecedor && !opcoesFornecedor.some(o => o.id === initial.fornecedor)) {
    opcoesFornecedor.unshift({ id: initial.fornecedor, label: initial.fornecedor_nome || `#${initial.fornecedor}` })
  }

  const methods = useForm<ContaPagarFormValues>({
    resolver: zodResolver(contaPagarSchema),
    // O título novo nasce na entidade que a barra do ERP está mostrando.
    defaultValues: initial ? toFormValues(initial) : { ...EMPTY_VALUES, entidade: entidadeAtiva() },
  })
  const { register, control, handleSubmit, setError, formState: { errors, isSubmitting } } = methods

  const submit = handleSubmit(async values => {
    setApiError(null)
    try {
      // A entidade só vai quando a pessoa a escolheu ou trocou: sem ela, a
      // regra decide — e trocar a obra de um título sem baixa troca a dona.
      const entidade = values.entidade ?? null
      const mandaEntidade = !travados.has('entidade') && (initial ? entidade !== initial.entidade : entidade !== null)
      await onSubmit({
        ...(mandaEntidade ? { entidade } : {}),
        fornecedor: values.fornecedor,
        empreendimento: values.empreendimento ?? null,
        obra: values.obra ?? null,
        etapa: values.etapa ?? null,
        descricao: values.descricao,
        valor: centsToApiDecimal(values.valorCents),
        data_emissao: values.data_emissao || null,
        data_vencimento: values.data_vencimento,
        data_agendamento: values.data_agendamento || null,
        rateios: (values.rateios ?? []).map(r => ({ centro_custo: r.centro_custo, valor: centsToApiDecimal(r.valorCents) })),
      })
    } catch (err) {
      setApiError(distribuirErros(parseApiErrors(err), Object.keys(EMPTY_VALUES), (campo, msg) =>
        setError(campo as keyof ContaPagarFormValues, { message: msg })))
    }
  }, invalidos => setApiError(errosSemLugar(invalidos)))

  if (initial?.natureza) {
    return (
      <div className="flex flex-col gap-4">
        <AvisoIntercompany contraparte={initial.contraparte_nome} natureza={initial.natureza_nome} />
        <div className="flex justify-end">
          <button type="button" onClick={onCancel} style={buttonSecondaryStyle}>Fechar</button>
        </div>
      </div>
    )
  }

  return (
    <FormProvider {...methods}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <AvisoDeTrava motivo={initial?.travado_porque ?? ''} />
        <EntidadeField travada={travados.has('entidade')} nomeAtual={initial?.entidade_nome} />
        <Field label="Fornecedor" error={errors.fornecedor?.message}>
          {travados.has('fornecedor') ? (
            <TextoTravado>{opcoesFornecedor.find(o => o.id === initial?.fornecedor)?.label ?? '—'}</TextoTravado>
          ) : (
            <select style={selectStyle} disabled={fornecedorOptions.isLoading} defaultValue="" {...register('fornecedor', { valueAsNumber: true })}>
            <option value="" disabled>Selecione um fornecedor…</option>
            {opcoesFornecedor.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
          )}
        </Field>

        <Field label="Empreendimento (opcional)">
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
                <option value="">Sem empreendimento</option>
                {(empreendimentoOptions.data ?? []).map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
            )}
          />
        </Field>

        <ObraEtapaFields comEtapa />

        <Field label="Descrição" error={errors.descricao?.message}>
          <input type="text" style={inputStyle} placeholder="Ex.: Compra de cimento — NF 1234" {...register('descricao')} />
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
