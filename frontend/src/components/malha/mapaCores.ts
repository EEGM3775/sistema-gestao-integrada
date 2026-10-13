/**
 * Cores e halos do `<Mapa>` — num arquivo à parte para a LEGENDA usar a mesma
 * tabela que pinta o pin. Uma legenda com a sua própria lista de cores é a
 * próxima divergência esperando acontecer.
 */

/** Cor do pin por tipo de local. */
export const COR_TIPO: Record<string, string> = {
  obra: '#E79A22', empreendimento: '#274D8C', fornecedor: '#1D9AA6',
  local_estoque: '#3E9C6E', unidade: '#8C5BD6', avulso: '#8892A6',
}

/** Raio do halo por precisão (px). É a incerteza em escala visual. */
export const HALO_PRECISAO: Record<string, number> = {
  exata: 0, endereco: 7, cep: 13, municipio: 22, desconhecida: 0,
}
