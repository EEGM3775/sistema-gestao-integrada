import { z } from 'zod'

/**
 * Schemas zod dos formulários de lançamento (D.1.1 — primeiro uso de RHF+zod
 * no projeto). Valores monetários no formulário ficam em **centavos inteiros**
 * (`*Cents`, ver `utils/money.ts` e `MoneyInput`) — só viram string decimal
 * (`centsToApiDecimal`) na borda, ao montar o payload para a API.
 */

const rateioSchema = z.object({
  centro_custo: z.number({ error: 'Selecione um centro de custo.' }).int().positive(),
  valorCents: z.number().int().min(1, 'Informe um valor maior que zero.'),
})

/** Garante que a soma dos rateios bate com o valor total — espelha `_validar_rateios` do backend. */
function refinarRateios<T extends { valorCents: number; rateios?: { centro_custo: number; valorCents: number }[] }>(
  data: T, ctx: z.RefinementCtx,
) {
  const rateios = data.rateios ?? []
  if (rateios.length === 0) return

  const centros = rateios.map(r => r.centro_custo)
  if (new Set(centros).size !== centros.length) {
    ctx.addIssue({ code: 'custom', path: ['rateios'], message: 'Cada centro de custo só pode aparecer uma vez no rateio.' })
    return
  }

  const soma = rateios.reduce((acc, r) => acc + r.valorCents, 0)
  if (soma !== data.valorCents) {
    ctx.addIssue({ code: 'custom', path: ['rateios'], message: 'A soma dos rateios deve ser igual ao valor da conta.' })
  }
}

export const contaPagarSchema = z.object({
  fornecedor: z.number({ error: 'Selecione um fornecedor.' }).int().positive(),
  empreendimento: z.number().int().positive().nullable().optional(),
  obra: z.number().int().positive().nullable().optional(),
  etapa: z.number().int().positive().nullable().optional(),
  descricao: z.string().min(1, 'Informe uma descrição.').max(255, 'Máximo de 255 caracteres.'),
  valorCents: z.number().int().min(1, 'Informe um valor maior que zero.'),
  data_emissao: z.string().nullable().optional(),
  data_vencimento: z.string().min(1, 'Informe a data de vencimento.'),
  data_agendamento: z.string().nullable().optional(),
  rateios: z.array(rateioSchema).optional(),
}).superRefine(refinarRateios)

export type ContaPagarFormValues = z.infer<typeof contaPagarSchema>

export const contaReceberSchema = z.object({
  cliente: z.number({ error: 'Selecione um cliente.' }).int().positive(),
  empreendimento: z.number().int().positive().nullable().optional(),
  obra: z.number().int().positive().nullable().optional(),
  descricao: z.string().min(1, 'Informe uma descrição.').max(255, 'Máximo de 255 caracteres.'),
  valorCents: z.number().int().min(1, 'Informe um valor maior que zero.'),
  data_emissao: z.string().nullable().optional(),
  data_vencimento: z.string().min(1, 'Informe a data de vencimento.'),
  data_agendamento: z.string().nullable().optional(),
  rateios: z.array(rateioSchema).optional(),
}).superRefine(refinarRateios)

export type ContaReceberFormValues = z.infer<typeof contaReceberSchema>

/** Espelha `BaixaSerializer` — único caminho de quitação manual, com os mesmos limites do backend. */
export const baixaSchema = z.object({
  valorCents: z.number().int().min(1, 'Informe um valor maior que zero.'),
  data: z.string().min(1, 'Informe a data da baixa.'),
  jurosCents: z.number().int().min(0).optional(),
  multaCents: z.number().int().min(0).optional(),
  descontoCents: z.number().int().min(0).optional(),
  meio_pagamento: z.string().optional(),
})

export type BaixaFormValues = z.infer<typeof baixaSchema>
