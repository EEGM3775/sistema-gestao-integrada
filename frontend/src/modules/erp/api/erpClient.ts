import apiClient from '@/api/apiClient'
import { ligarCamadaDoErp } from '@/modules/entidades/entidadeAtiva'

ligarCamadaDoErp(apiClient)

/** Reexporta o `apiClient` autenticado — todo endpoint do ERP cai sob `/erp/`
 *  e leva a entidade escolhida na barra de camada (docs/modulos/entidades.md §6). */
export const erpClient = apiClient
export const ERP_BASE = 'erp/'
