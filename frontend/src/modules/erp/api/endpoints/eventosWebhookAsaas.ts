import { erpClient } from '../erpClient'
import type { EventoWebhookAsaas } from '../../types'

/**
 * Timeline de eventos do webhook Asaas de um boleto (D.1.2) — endpoint
 * somente leitura sob `funcoescobrancas` (`/api/erp/cobrancas/eventos/`,
 * registrado fora do prefixo `ERP_BASE` porque o app que possui
 * `EventoWebhookAsaas` é o adaptador de cobranças, não o `moduloerp`).
 * Lista pequena por boleto — sem paginação no backend (`pagination_class = None`).
 */
export async function fetchEventosWebhookAsaasPorBoleto(boletoId: number): Promise<EventoWebhookAsaas[]> {
  const { data } = await erpClient.get<EventoWebhookAsaas[]>('erp/cobrancas/eventos/', {
    params: { boleto: boletoId },
  })
  return data
}
