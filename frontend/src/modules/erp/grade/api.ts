import { erpClient, ERP_BASE } from '../api/erpClient'
import type { Filtros, PaginaGrade, RespostaGrupos } from './tipos'

/** Linhas por página da rolagem infinita — abaixo do `PAGINA_MAXIMA["erp"]` do `planos.py`. */
export const LINHAS_POR_PAGINA = 100
/** Quantas linhas um grupo aberto traz antes de pedir "abrir só este grupo". */
export const LINHAS_POR_GRUPO = 200

function limpar(filtros: Filtros): Record<string, string | number> {
  const saida: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(filtros)) {
    if (v !== undefined && v !== null && v !== '') saida[k] = v
  }
  return saida
}

export async function buscarPagina<T>(
  recurso: string, filtros: Filtros, ordenar: string, page: number, pageSize = LINHAS_POR_PAGINA,
): Promise<PaginaGrade<T>> {
  const { data } = await erpClient.get<PaginaGrade<T>>(`${ERP_BASE}${recurso}/`, {
    params: { ...limpar(filtros), ordering: ordenar, page, page_size: pageSize },
  })
  return data
}

export async function buscarGrupos(recurso: string, filtros: Filtros, por: string[]): Promise<RespostaGrupos> {
  const { data } = await erpClient.get<RespostaGrupos>(`${ERP_BASE}${recurso}/grupos/`, {
    params: { ...limpar(filtros), por: por.join(',') },
  })
  return data
}
