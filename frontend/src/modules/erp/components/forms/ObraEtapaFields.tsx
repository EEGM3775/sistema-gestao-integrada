import { useEffect, useRef } from 'react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'
import { Field } from './FormField'
import { selectStyle } from './formStyles'
import { SeletorDeObra } from '@/components/malha'
import { useEtapaOptions } from '../../hooks/useEntityOptions'

/**
 * Obra (e etapa) da conta — D.1.4, financeiro por obra.
 *
 * É o que leva a conta à DRE da obra e à coluna *realizado* do Orçamento. A
 * etapa só aparece com obra escolhida, lista só as etapas dela, e é limpa ao
 * trocar de obra — a API recusa etapa de outra obra.
 */
export function ObraEtapaFields({ comEtapa, obraNome }: { comEtapa: boolean; obraNome?: string | null }) {
  const { control, setValue } = useFormContext<{ obra?: number | null; etapa?: number | null }>()
  const obra = useWatch({ control, name: 'obra' })
  const obraInicial = useRef(obra)
  const etapas = useEtapaOptions(comEtapa ? obra ?? null : null)
  const obraAnterior = useRef(obra)
  useEffect(() => {
    if (comEtapa && obraAnterior.current !== obra) setValue('etapa', null)
    obraAnterior.current = obra
  }, [comEtapa, obra, setValue])

  const numero = (v: string) => (v === '' ? null : Number(v))
  return (
    <div className={comEtapa ? 'grid grid-cols-2 gap-3' : ''}>
      <Field label="Obra (opcional)">
        <Controller
          control={control}
          name="obra"
          render={({ field }) => (
            // Busca no servidor (F2): a lista inteira de obras não vem mais.
            <SeletorDeObra
              valor={field.value ?? null}
              rotuloAtual={field.value != null && field.value === obraInicial.current ? obraNome : undefined}
              aoMudar={id => field.onChange(id ?? null)}
              permiteLimpar
              placeholder="Sem obra — busque para escolher"
              aria-label="Obra"
              style={selectStyle}
            />
          )}
        />
      </Field>
      {comEtapa && (
        <Field label="Etapa (opcional)">
          <Controller
            control={control}
            name="etapa"
            render={({ field }) => (
              <select style={selectStyle} disabled={!obra} value={field.value == null ? '' : String(field.value)}
                onChange={e => field.onChange(numero(e.target.value))} onBlur={field.onBlur}>
                <option value="">{obra ? 'Sem etapa' : 'Escolha a obra primeiro'}</option>
                {(etapas.data ?? []).map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
            )}
          />
        </Field>
      )}
    </div>
  )
}
