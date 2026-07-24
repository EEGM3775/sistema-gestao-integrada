// Chaves de cache do React Query para o SCM. Raiz única `['scm']` — os verbos de
// domínio invalidam a raiz inteira (afetam vários recursos).
type Params = Record<string, unknown>

function root(name: string) {
  return {
    all: ['scm', name] as const,
    list: (p: Params = {}) => ['scm', name, 'list', p] as const,
    detail: (id: number) => ['scm', name, 'detail', id] as const,
  }
}

export const scmKeys = {
  all: ['scm'] as const,
  dashboard: (mes?: string) => ['scm', 'dashboard', mes ?? 'atual'] as const,
  produtos: root('produtos'),
  centrosCusto: root('centros-custo'),
  ofertas: root('ofertas'),
  faixas: root('faixas'),
  demandas: root('demandas'),
  itensDemanda: root('itens-demanda'),
  cotacoes: root('cotacoes'),
  propostas: root('propostas'),
  itensProposta: root('itens-proposta'),
  pedidos: root('pedidos'),
  itensPedido: root('itens-pedido'),
  recebimentos: root('recebimentos'),
  avaliacoes: root('avaliacoes'),
}
