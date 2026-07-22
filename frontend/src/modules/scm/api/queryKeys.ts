// Fábrica de chaves do TanStack Query para o SCM. Uma raiz por recurso; a raiz
// serve de alvo de invalidação após create/update/delete e verbos de domínio.

type Params = Record<string, unknown>

function resourceKeys(name: string) {
  return {
    all: ['scm', name] as const,
    list: (params: Params = {}) => ['scm', name, 'list', params] as const,
    detail: (id: number) => ['scm', name, 'detail', id] as const,
  }
}

export const scmKeys = {
  all: ['scm'] as const,
  produtos: resourceKeys('produtos'),
  centrosCusto: resourceKeys('centros-custo'),
  ofertas: resourceKeys('ofertas'),
  faixas: resourceKeys('faixas'),
  demandas: resourceKeys('demandas'),
  itensDemanda: resourceKeys('itens-demanda'),
  cotacoes: resourceKeys('cotacoes'),
  propostas: resourceKeys('propostas'),
  itensProposta: resourceKeys('itens-proposta'),
  pedidos: resourceKeys('pedidos'),
  itensPedido: resourceKeys('itens-pedido'),
  recebimentos: resourceKeys('recebimentos'),
  avaliacoes: resourceKeys('avaliacoes'),
  dashboard: ['scm', 'dashboard'] as const,
}
