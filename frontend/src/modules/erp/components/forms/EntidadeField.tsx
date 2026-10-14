import { Controller, useFormContext } from 'react-hook-form'
import { Handshake } from 'lucide-react'
import { useContextoEntidades } from '@/modules/entidades/api'
import { Field } from './FormField'
import { selectStyle } from './formStyles'
import { TextoTravado } from './trava'

/**
 * A dona do título (docs/modulos/entidades.md §2). Só aparece com mais de uma
 * entidade do grupo; em branco, vale a regra — a da obra, a dona do
 * empreendimento, ou a matriz. Travada depois da baixa: o dinheiro saiu do
 * caixa dela.
 */
export function EntidadeField({ travada, nomeAtual }: { travada: boolean; nomeAtual?: string }) {
  const contexto = useContextoEntidades()
  const { control } = useFormContext<{ entidade?: number | null }>()
  if (!contexto.data || contexto.data.modo_simples) return null
  return (
    <Field label="Entidade (CNPJ dono do título)">
      {travada ? (
        <TextoTravado>{nomeAtual || '—'}</TextoTravado>
      ) : (
        <Controller
          control={control}
          name="entidade"
          render={({ field }) => (
            <select
              style={selectStyle}
              value={field.value == null ? '' : String(field.value)}
              onChange={e => field.onChange(e.target.value === '' ? null : Number(e.target.value))}
              onBlur={field.onBlur}
            >
              <option value="">Automático — pela obra ou pelo empreendimento</option>
              {contexto.data.entidades.map(e => <option key={e.entidade} value={e.entidade}>{e.nome}</option>)}
            </select>
          )}
        />
      )}
    </Field>
  )
}

/** O título entre entidades não se edita: ele acompanha o título de origem. */
export function AvisoIntercompany({ contraparte, natureza }: { contraparte: string; natureza: string }) {
  return (
    <div className="flex items-start gap-2 text-sm"
      style={{ padding: '10px 12px', borderRadius: 'var(--r-md)', background: 'var(--info-soft)', color: 'var(--info-ink)' }}>
      <Handshake size={16} style={{ flex: 'none', marginTop: 2 }} />
      <span>
        Título intercompany com <strong>{contraparte}</strong> ({natureza.toLowerCase()}). Ele nasce e muda junto
        com o título de origem — para mudar valor ou vencimento, edite a origem. Aqui se dá a baixa, ou se compensa
        no encontro de contas.
      </span>
    </div>
  )
}
